"""Fail-closed Linux platform adapters for TrillionniumOS Desktop S09.

The module owns operating-system mechanism checks only. It does not grant a
browser principal, capability, external effect, update, signing, or release
authority. Every adapter returns bounded facts or raises ``PlatformError``.
"""
from __future__ import annotations

import errno
import hashlib
import ipaddress
import os
import re
import secrets
import select
import socket
import stat
import struct
import threading
import time
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Iterable, Sequence
from urllib.parse import urlsplit

MAX_PROC_STATUS_BYTES = 128 * 1024
MAX_PROC_STAT_BYTES = 64 * 1024
MAX_PROC_CGROUP_BYTES = 64 * 1024
MAX_ATOMIC_FILE_BYTES = 16 * 1024 * 1024
MAX_ENTROPY_BYTES = 4096
MAX_URL_BYTES = 4096
MAX_REDIRECTS = 10
SO_PEERCRED_BYTES = struct.calcsize("3i")


class PlatformError(RuntimeError):
    """Typed refusal for ambiguous or unsafe platform state."""


class PathRefused(PlatformError):
    """A path, file type, ownership, or size invariant failed."""


class IdentityRefused(PlatformError):
    """A process, service, or peer identity could not be bound exactly."""


class NetworkRefused(PlatformError):
    """A URL, address, redirect, or connected peer failed policy."""


class DeadlineExpired(PlatformError):
    """A timeout was invalid, expired, or not representable."""


@dataclass(frozen=True)
class AtomicWriteReceipt:
    relative_path: str
    bytes_written: int
    sha256: str
    mode: int


class PublicationIndeterminate(PlatformError):
    """The final pathname may already contain the intended durable bytes.

    Callers must reconcile through ``AtomicFileStore.reconcile`` before any
    retry. The exception never authorizes replay or replacement.
    """

    def __init__(
        self,
        receipt: AtomicWriteReceipt,
        destination_device: int | None,
        destination_inode: int | None,
        cause: BaseException,
    ) -> None:
        super().__init__(
            "atomic publication crossed the no-replace commit boundary; "
            "reconciliation is required before retry"
        )
        self.receipt = receipt
        self.destination_device = destination_device
        self.destination_inode = destination_inode
        self.cause = cause


def _safe_components(relative: str) -> tuple[str, ...]:
    path = PurePosixPath(relative)
    if path.is_absolute() or not path.parts:
        raise PathRefused("path must be non-empty and relative")
    if any(part in ("", ".", "..") for part in path.parts):
        raise PathRefused("path contains an unsafe component")
    if any("\x00" in part or "/" in part for part in path.parts):
        raise PathRefused("path contains a forbidden character")
    return path.parts


def _open_directory_chain(root_fd: int, components: Sequence[str]) -> list[int]:
    opened: list[int] = []
    current = root_fd
    try:
        for component in components:
            fd = os.open(
                component,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=current,
            )
            opened.append(fd)
            current = fd
        return opened
    except Exception:
        for fd in reversed(opened):
            os.close(fd)
        raise


def _read_regular_fd(fd: int, maximum: int) -> tuple[bytes, os.stat_result]:
    before = os.fstat(fd)
    if not stat.S_ISREG(before.st_mode):
        raise PathRefused("leaf is not a regular file")
    if before.st_size > maximum:
        raise PathRefused("file exceeds the declared byte bound")
    output = bytearray()
    while len(output) <= maximum:
        requested = min(64 * 1024, maximum + 1 - len(output))
        chunk = os.read(fd, requested)
        if not chunk:
            break
        output.extend(chunk)
    if len(output) > maximum:
        raise PathRefused("file grew beyond the declared byte bound")
    after = os.fstat(fd)
    if (after.st_dev, after.st_ino) != (before.st_dev, before.st_ino):
        raise PathRefused("file identity changed during the read")
    return bytes(output), before


def _read_bounded_regular_at(root_fd: int, relative: str, maximum: int) -> bytes:
    if maximum < 0:
        raise ValueError("maximum must be non-negative")
    components = _safe_components(relative)
    directories: list[int] = []
    leaf_fd: int | None = None
    try:
        directories = _open_directory_chain(root_fd, components[:-1])
        parent_fd = directories[-1] if directories else root_fd
        leaf_fd = os.open(
            components[-1],
            os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent_fd,
        )
        value, _ = _read_regular_fd(leaf_fd, maximum)
        return value
    finally:
        if leaf_fd is not None:
            os.close(leaf_fd)
        for fd in reversed(directories):
            os.close(fd)


def read_bounded_regular_file(root: Path, relative: str, maximum: int) -> bytes:
    """Read one file through a descriptor-pinned, component no-follow walk."""

    root_fd = os.open(
        root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    )
    try:
        return _read_bounded_regular_at(root_fd, relative, maximum)
    finally:
        os.close(root_fd)


@dataclass
class MonotonicClock:
    """Stateful monotonic clock that refuses observable regression."""

    _last_ns: int | None = None

    def now_ns(self) -> int:
        value = time.monotonic_ns()
        if value < 0:
            raise PlatformError("monotonic clock returned a negative value")
        if self._last_ns is not None and value < self._last_ns:
            raise PlatformError("monotonic clock regressed")
        self._last_ns = value
        return value

    def deadline_ns(self, timeout_ns: int) -> int:
        if timeout_ns <= 0:
            raise DeadlineExpired("timeout must be positive")
        now = self.now_ns()
        deadline = now + timeout_ns
        if deadline < now or deadline > (1 << 63) - 1:
            raise DeadlineExpired("deadline overflow")
        return deadline


class OsEntropy:
    """Bounded operating-system entropy without deterministic fallback."""

    @staticmethod
    def read(length: int) -> bytes:
        if length <= 0 or length > MAX_ENTROPY_BYTES:
            raise PlatformError("entropy request is outside the allowed range")
        try:
            value = os.getrandom(length)
        except (AttributeError, OSError) as error:
            raise PlatformError(f"operating-system entropy unavailable: {error}") from error
        if len(value) != length or value == bytes(length):
            raise PlatformError("operating-system entropy result is invalid")
        return value


def _validate_private_directory(
    metadata: os.stat_result, *, expected_identity: tuple[int, int] | None = None
) -> None:
    if not stat.S_ISDIR(metadata.st_mode):
        raise PathRefused("store root must be a directory")
    if expected_identity is not None and (metadata.st_dev, metadata.st_ino) != expected_identity:
        raise PathRefused("store root identity changed")
    if metadata.st_uid not in (0, os.geteuid()):
        raise PathRefused("store root owner is not trusted")
    if stat.S_IMODE(metadata.st_mode) & 0o022:
        raise PathRefused("store root is group/other writable")


class AtomicFileStore:
    """No-replace publication rooted in one retained directory identity."""

    def __init__(self, root: Path, maximum_bytes: int = MAX_ATOMIC_FILE_BYTES):
        if maximum_bytes <= 0:
            raise PathRefused("store byte ceiling must be positive")
        self._root_path = Path(root)
        try:
            root_fd = os.open(
                self._root_path,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            )
        except OSError as error:
            raise PathRefused("store root cannot be acquired without following links") from error
        try:
            metadata = os.fstat(root_fd)
            _validate_private_directory(metadata)
        except Exception:
            os.close(root_fd)
            raise
        self._root_fd: int | None = root_fd
        self._root_identity = (metadata.st_dev, metadata.st_ino)
        self._root_uid = metadata.st_uid
        self._root_mode = stat.S_IMODE(metadata.st_mode)
        self._maximum = maximum_bytes
        self._lock = threading.Lock()

    def close(self) -> None:
        with self._lock:
            if self._root_fd is not None:
                os.close(self._root_fd)
                self._root_fd = None

    def __enter__(self) -> "AtomicFileStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def __del__(self) -> None:
        root_fd = getattr(self, "_root_fd", None)
        if root_fd is not None:
            try:
                os.close(root_fd)
            except OSError:
                pass
            self._root_fd = None

    def _validated_root_fd(self) -> int:
        root_fd = self._root_fd
        if root_fd is None:
            raise PathRefused("store is closed")
        retained = os.fstat(root_fd)
        _validate_private_directory(retained, expected_identity=self._root_identity)
        if retained.st_uid != self._root_uid or stat.S_IMODE(retained.st_mode) != self._root_mode:
            raise PathRefused("store root custody changed")
        current_fd: int | None = None
        try:
            current_fd = os.open(
                self._root_path,
                os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            )
            current = os.fstat(current_fd)
            _validate_private_directory(current, expected_identity=self._root_identity)
            if current.st_uid != self._root_uid or stat.S_IMODE(current.st_mode) != self._root_mode:
                raise PathRefused("store root pathname custody changed")
        except OSError as error:
            raise PathRefused("store root pathname no longer names the retained directory") from error
        finally:
            if current_fd is not None:
                os.close(current_fd)
        return root_fd

    @staticmethod
    def _receipt(relative: str, data: bytes, mode: int) -> AtomicWriteReceipt:
        return AtomicWriteReceipt(
            relative_path=relative,
            bytes_written=len(data),
            sha256=hashlib.sha256(data).hexdigest(),
            mode=mode,
        )

    @staticmethod
    def _destination_identity(parent_fd: int, name: str) -> tuple[int | None, int | None]:
        fd: int | None = None
        try:
            fd = os.open(
                name,
                os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=parent_fd,
            )
            metadata = os.fstat(fd)
            return metadata.st_dev, metadata.st_ino
        except OSError:
            return None, None
        finally:
            if fd is not None:
                os.close(fd)

    @staticmethod
    def _read_destination(parent_fd: int, name: str, maximum: int) -> tuple[bytes, os.stat_result]:
        fd = os.open(
            name,
            os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=parent_fd,
        )
        try:
            return _read_regular_fd(fd, maximum)
        finally:
            os.close(fd)

    def write(self, relative: str, data: bytes, mode: int = 0o600) -> AtomicWriteReceipt:
        if not isinstance(data, bytes):
            raise TypeError("data must be bytes")
        if len(data) > self._maximum:
            raise PathRefused("atomic write exceeds the configured byte bound")
        if mode != 0o600:
            raise PathRefused("private store files must use mode 0600")
        components = _safe_components(relative)
        receipt = self._receipt(relative, data, mode)
        with self._lock:
            root_fd = self._validated_root_fd()
            directories: list[int] = []
            temp_fd: int | None = None
            temp_name = ".hepta-tmp-" + secrets.token_hex(16)
            parent_fd = root_fd
            published = False
            try:
                directories = _open_directory_chain(root_fd, components[:-1])
                parent_fd = directories[-1] if directories else root_fd
                temp_fd = os.open(
                    temp_name,
                    os.O_WRONLY
                    | os.O_CREAT
                    | os.O_EXCL
                    | os.O_NOFOLLOW
                    | os.O_CLOEXEC,
                    mode,
                    dir_fd=parent_fd,
                )
                os.fchmod(temp_fd, mode)
                view = memoryview(data)
                offset = 0
                while offset < len(view):
                    written = os.write(temp_fd, view[offset:])
                    if written <= 0:
                        raise PlatformError("atomic write made no progress")
                    offset += written
                os.fsync(temp_fd)
                metadata = os.fstat(temp_fd)
                if not stat.S_ISREG(metadata.st_mode):
                    raise PathRefused("temporary publication is not a regular file")
                if metadata.st_size != len(data):
                    raise PlatformError("temporary publication length mismatch")
                os.close(temp_fd)
                temp_fd = None

                try:
                    os.link(
                        temp_name,
                        components[-1],
                        src_dir_fd=parent_fd,
                        dst_dir_fd=parent_fd,
                        follow_symlinks=False,
                    )
                except FileExistsError as error:
                    raise PathRefused(
                        "destination exists; replacement is not authorized"
                    ) from error
                published = True
                observed, destination = self._read_destination(
                    parent_fd, components[-1], self._maximum
                )
                if observed != data or stat.S_IMODE(destination.st_mode) != mode:
                    raise PlatformError("published destination readback mismatch")
                os.fsync(parent_fd)
                os.unlink(temp_name, dir_fd=parent_fd)
                os.fsync(parent_fd)
                return receipt
            except Exception as error:
                if published:
                    device, inode = self._destination_identity(
                        parent_fd, components[-1]
                    )
                    try:
                        os.unlink(temp_name, dir_fd=parent_fd)
                    except OSError:
                        pass
                    raise PublicationIndeterminate(
                        receipt, device, inode, error
                    ) from error
                try:
                    os.unlink(temp_name, dir_fd=parent_fd)
                except OSError as cleanup_error:
                    if cleanup_error.errno != errno.ENOENT:
                        raise PlatformError(
                            "pre-publication staging cleanup failed"
                        ) from error
                raise
            finally:
                if temp_fd is not None:
                    os.close(temp_fd)
                for fd in reversed(directories):
                    os.close(fd)

    def reconcile(
        self,
        relative: str,
        *,
        expected_sha256: str,
        expected_bytes: int,
        mode: int = 0o600,
    ) -> AtomicWriteReceipt:
        """Reconcile an indeterminate publication without replacing or replaying."""

        if (
            not isinstance(expected_sha256, str)
            or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256)
            or expected_bytes < 0
            or expected_bytes > self._maximum
            or mode != 0o600
        ):
            raise PathRefused("reconciliation expectation is invalid")
        components = _safe_components(relative)
        with self._lock:
            root_fd = self._validated_root_fd()
            directories = _open_directory_chain(root_fd, components[:-1])
            try:
                parent_fd = directories[-1] if directories else root_fd
                observed, metadata = self._read_destination(
                    parent_fd, components[-1], self._maximum
                )
                if (
                    len(observed) != expected_bytes
                    or hashlib.sha256(observed).hexdigest() != expected_sha256
                    or stat.S_IMODE(metadata.st_mode) != mode
                ):
                    raise PathRefused("published destination does not match reconciliation")
                return AtomicWriteReceipt(
                    relative_path=relative,
                    bytes_written=expected_bytes,
                    sha256=expected_sha256,
                    mode=mode,
                )
            finally:
                for fd in reversed(directories):
                    os.close(fd)


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    uid: int
    gid: int
    start_time_ticks: int
    cgroup_v2_path: str
    systemd_unit: str | None


def _parse_uniform_ids(value: str, label: str) -> int:
    for line in value.splitlines():
        if line.startswith(label + ":"):
            fields = line.split(":", 1)[1].split()
            if len(fields) != 4:
                raise IdentityRefused(f"{label} field must contain four IDs")
            try:
                identifiers = [int(field, 10) for field in fields]
            except ValueError as error:
                raise IdentityRefused(f"{label} field is not numeric") from error
            if any(identifier != identifiers[0] for identifier in identifiers):
                raise IdentityRefused(f"{label} identifiers are not uniform")
            return identifiers[0]
    raise IdentityRefused(f"missing {label} field")


def _parse_start_time(value: str) -> int:
    close = value.rfind(")")
    if close < 0:
        raise IdentityRefused("proc stat has no comm terminator")
    fields = value[close + 1 :].split()
    if len(fields) <= 19:
        raise IdentityRefused("proc stat has no start-time field")
    try:
        result = int(fields[19], 10)
    except ValueError as error:
        raise IdentityRefused("proc start time is not numeric") from error
    if result <= 0:
        raise IdentityRefused("proc start time must be positive")
    return result


def _parse_cgroup(value: str) -> tuple[str, str | None]:
    paths: list[str] = []
    for line in value.splitlines():
        if not line:
            continue
        fields = line.split(":", 2)
        if len(fields) != 3:
            raise IdentityRefused("malformed cgroup row")
        hierarchy, controllers, path = fields
        if hierarchy == "0" and controllers == "":
            if not path.startswith("/") or ".." in PurePosixPath(path).parts:
                raise IdentityRefused("unsafe cgroup-v2 path")
            paths.append(path)
    if len(paths) != 1:
        raise IdentityRefused("exactly one cgroup-v2 entry is required")
    components = PurePosixPath(paths[0]).parts
    units = [part for part in components if part.endswith((".service", ".scope"))]
    return paths[0], units[-1] if units else None


def _pidfd_is_exited(pidfd: int) -> bool:
    poller = select.poll()
    poller.register(pidfd, select.POLLIN | select.POLLHUP | select.POLLERR)
    return bool(poller.poll(0))


def _open_pidfd(pid: int, proc_root: Path) -> int | None:
    if proc_root != Path("/proc") or not hasattr(os, "pidfd_open"):
        return None
    try:
        return os.pidfd_open(pid, 0)
    except OSError as error:
        raise IdentityRefused("pidfd acquisition failed") from error


def read_process_identity(pid: int, proc_root: Path = Path("/proc")) -> ProcessIdentity:
    """Read one descriptor-pinned process incarnation and revalidate it."""

    if pid <= 0:
        raise IdentityRefused("PID must be positive")
    proc_fd = os.open(
        proc_root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    )
    process_fd: int | None = None
    current_fd: int | None = None
    pidfd: int | None = None
    try:
        process_fd = os.open(
            str(pid),
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=proc_fd,
        )
        before_directory = os.fstat(process_fd)
        pidfd = _open_pidfd(pid, proc_root)
        if pidfd is not None and _pidfd_is_exited(pidfd):
            raise IdentityRefused("process exited before identity observation")

        stat_before_bytes = _read_bounded_regular_at(
            process_fd, "stat", MAX_PROC_STAT_BYTES
        )
        cgroup_before_bytes = _read_bounded_regular_at(
            process_fd, "cgroup", MAX_PROC_CGROUP_BYTES
        )
        status_bytes = _read_bounded_regular_at(
            process_fd, "status", MAX_PROC_STATUS_BYTES
        )
        cgroup_after_bytes = _read_bounded_regular_at(
            process_fd, "cgroup", MAX_PROC_CGROUP_BYTES
        )
        stat_after_bytes = _read_bounded_regular_at(
            process_fd, "stat", MAX_PROC_STAT_BYTES
        )

        after_directory = os.fstat(process_fd)
        if (after_directory.st_dev, after_directory.st_ino) != (
            before_directory.st_dev,
            before_directory.st_ino,
        ):
            raise IdentityRefused("pinned proc directory identity changed")
        current_fd = os.open(
            str(pid),
            os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=proc_fd,
        )
        current = os.fstat(current_fd)
        if (current.st_dev, current.st_ino) != (
            before_directory.st_dev,
            before_directory.st_ino,
        ):
            raise IdentityRefused("PID pathname now names a different process incarnation")
        if pidfd is not None and _pidfd_is_exited(pidfd):
            raise IdentityRefused("process exited during identity observation")

        try:
            status_text = status_bytes.decode("utf-8", "strict")
            stat_before = stat_before_bytes.decode("utf-8", "strict")
            stat_after = stat_after_bytes.decode("utf-8", "strict")
            cgroup_before = cgroup_before_bytes.decode("utf-8", "strict")
            cgroup_after = cgroup_after_bytes.decode("utf-8", "strict")
        except UnicodeDecodeError as error:
            raise IdentityRefused("proc identity file is not valid UTF-8") from error

        start_before = _parse_start_time(stat_before)
        start_after = _parse_start_time(stat_after)
        if start_before != start_after:
            raise IdentityRefused("process start time changed during observation")
        if cgroup_before != cgroup_after:
            raise IdentityRefused("process cgroup changed during observation")
        path, unit = _parse_cgroup(cgroup_after)
        return ProcessIdentity(
            pid=pid,
            uid=_parse_uniform_ids(status_text, "Uid"),
            gid=_parse_uniform_ids(status_text, "Gid"),
            start_time_ticks=start_after,
            cgroup_v2_path=path,
            systemd_unit=unit,
        )
    except OSError as error:
        raise IdentityRefused("process identity subject could not be retained") from error
    finally:
        if pidfd is not None:
            os.close(pidfd)
        if current_fd is not None:
            os.close(current_fd)
        if process_fd is not None:
            os.close(process_fd)
        os.close(proc_fd)


@dataclass(frozen=True)
class WaylandPeer:
    endpoint: str
    endpoint_device: int
    endpoint_inode: int
    runtime_device: int
    runtime_inode: int
    peer_pid: int | None
    peer_uid: int
    peer_gid: int


def connect_wayland_endpoint(
    runtime_dir: Path,
    display: str,
    expected_uid: int,
    timeout_seconds: float = 1.0,
) -> tuple[socket.socket, WaylandPeer]:
    """Connect through one descriptor-pinned Wayland socket inode."""

    if timeout_seconds <= 0:
        raise DeadlineExpired("Wayland connection timeout must be positive")
    if "/" in display or display in ("", ".", "..") or "\x00" in display:
        raise PathRefused("WAYLAND_DISPLAY must be one safe basename")
    path_flag = os.O_PATH
    runtime_fd: int | None = None
    endpoint_fd: int | None = None
    try:
        try:
            runtime_fd = os.open(
                runtime_dir,
                path_flag | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
            )
        except OSError as error:
            raise PathRefused(
                "cannot acquire XDG_RUNTIME_DIR without following links"
            ) from error
        metadata = os.fstat(runtime_fd)
        if not stat.S_ISDIR(metadata.st_mode):
            raise PathRefused("XDG_RUNTIME_DIR must be a directory")
        if metadata.st_uid != expected_uid:
            raise IdentityRefused("XDG_RUNTIME_DIR owner does not match the session")
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise IdentityRefused("XDG_RUNTIME_DIR is accessible by another identity")
        try:
            endpoint_fd = os.open(
                display,
                path_flag | os.O_NOFOLLOW | os.O_CLOEXEC,
                dir_fd=runtime_fd,
            )
        except OSError as error:
            raise PathRefused(
                "cannot acquire Wayland endpoint without following links"
            ) from error
        endpoint_metadata = os.fstat(endpoint_fd)
        if not stat.S_ISSOCK(endpoint_metadata.st_mode):
            raise PathRefused("Wayland endpoint is not a non-symlink Unix socket")
        if endpoint_metadata.st_uid != expected_uid:
            raise IdentityRefused("Wayland socket owner does not match the session")
        descriptor_path = f"/proc/self/fd/{endpoint_fd}"
        sock_type = socket.SOCK_STREAM | getattr(socket, "SOCK_CLOEXEC", 0)
        client = socket.socket(socket.AF_UNIX, sock_type)
        client.settimeout(timeout_seconds)
        try:
            client.connect(descriptor_path)
            credentials = client.getsockopt(
                socket.SOL_SOCKET, socket.SO_PEERCRED, SO_PEERCRED_BYTES
            )
            peer_pid, peer_uid, peer_gid = struct.unpack("3i", credentials)
            if peer_uid != expected_uid:
                raise IdentityRefused("Wayland compositor UID does not match the session")
            return client, WaylandPeer(
                endpoint=str(runtime_dir / display),
                endpoint_device=endpoint_metadata.st_dev,
                endpoint_inode=endpoint_metadata.st_ino,
                runtime_device=metadata.st_dev,
                runtime_inode=metadata.st_ino,
                peer_pid=peer_pid if peer_pid > 0 else None,
                peer_uid=peer_uid,
                peer_gid=peer_gid,
            )
        except Exception:
            client.close()
            raise
    finally:
        if endpoint_fd is not None:
            os.close(endpoint_fd)
        if runtime_fd is not None:
            os.close(runtime_fd)


@dataclass(frozen=True)
class HttpsTarget:
    origin: str
    hostname: str
    port: int


def _validate_host(hostname: str) -> str:
    host = hostname.rstrip(".").lower()
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        try:
            encoded = host.encode("ascii", "strict")
        except UnicodeEncodeError as error:
            raise NetworkRefused("Unicode external hostnames are not accepted") from error
        if len(encoded) > 253:
            raise NetworkRefused("external hostname exceeds the DNS byte bound")
        labels = host.split(".")
        if any(
            not label
            or len(label) > 63
            or label[0] == "-"
            or label[-1] == "-"
            or any(not (character.isalnum() or character == "-") for character in label)
            for label in labels
        ):
            raise NetworkRefused("external DNS hostname is invalid")
        return host
    return str(globally_routable(literal.compressed))


def validate_external_https(value: str) -> HttpsTarget:
    if not value or len(value.encode("utf-8")) > MAX_URL_BYTES:
        raise NetworkRefused("URL is empty or exceeds the byte bound")
    if any(ord(character) <= 0x1F or ord(character) == 0x7F for character in value):
        raise NetworkRefused("URL contains a control character")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as error:
        raise NetworkRefused("URL authority is malformed") from error
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or "\\" in parsed.netloc
    ):
        raise NetworkRefused("external URL must be credential-free HTTPS")
    host = _validate_host(parsed.hostname)
    if host == "localhost":
        raise NetworkRefused("localhost is not an external hostname")
    port = 443 if port is None else port
    if port <= 0 or port > 65535:
        raise NetworkRefused("external port is invalid")
    host_for_origin = f"[{host}]" if ":" in host else host
    suffix = "" if port == 443 else f":{port}"
    return HttpsTarget(f"https://{host_for_origin}{suffix}", host, port)


def globally_routable(address: str) -> ipaddress.IPv4Address | ipaddress.IPv6Address:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError as error:
        raise NetworkRefused("connected address is malformed") from error
    if (
        parsed.is_private
        or parsed.is_loopback
        or parsed.is_link_local
        or parsed.is_multicast
        or parsed.is_unspecified
        or parsed.is_reserved
        or not parsed.is_global
    ):
        raise NetworkRefused("connected address is not globally routable")
    return parsed


def bind_connected_peer(
    dns_answers: Iterable[str], connected_peer: str
) -> tuple[str, tuple[str, ...]]:
    approved = tuple(sorted({str(globally_routable(value)) for value in dns_answers}))
    if not approved:
        raise NetworkRefused("DNS produced no approved address")
    peer = str(globally_routable(connected_peer))
    if peer not in approved:
        raise NetworkRefused("connected peer is absent from the approved DNS set")
    return peer, approved


def validate_redirect_chain(urls: Sequence[str]) -> tuple[HttpsTarget, ...]:
    if not urls or len(urls) > MAX_REDIRECTS + 1:
        raise NetworkRefused("redirect chain length is outside the bound")
    return tuple(validate_external_https(value) for value in urls)
