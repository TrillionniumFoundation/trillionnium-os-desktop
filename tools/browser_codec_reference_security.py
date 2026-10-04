#!/usr/bin/env python3
"""Race-safe repository I/O and strict JSON helpers for codec evidence gates."""

from __future__ import annotations

import json
import math
import os
import stat
import sys
import threading
from pathlib import Path, PurePosixPath
from typing import Any, Callable, IO

ROOT = Path(__file__).resolve().parents[1]

_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_DIRECTORY = getattr(os, "O_DIRECTORY", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)

AfterComponentHook = Callable[[int, str, int], None]
_JSON_DUMPS = json.dumps
_JSON_DUMP = json.dump


def _reject_duplicate_json_keys(
    pairs: list[tuple[str, object]],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON object key: {key!r}")
        result[key] = value
    return result


def _reject_non_json_constant(value: str) -> None:
    raise ValueError(f"non-JSON numeric constant: {value}")


def _parse_finite_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed):
        raise ValueError(f"non-finite JSON number: {value}")
    return parsed


def load_json_strict(value: object) -> object:
    """Decode JSON without duplicate members or non-finite numbers."""

    options = {
        "object_pairs_hook": _reject_duplicate_json_keys,
        "parse_constant": _reject_non_json_constant,
        "parse_float": _parse_finite_float,
    }
    if hasattr(value, "read"):
        return json.load(value, **options)  # type: ignore[arg-type]
    return json.loads(value, **options)  # type: ignore[arg-type]


def strict_json_dumps(value: object, *args: object, **kwargs: object) -> str:
    """Serialize evidence with non-finite values forbidden."""

    kwargs["allow_nan"] = False
    return _JSON_DUMPS(value, *args, **kwargs)


def strict_json_dump(
    value: object,
    stream: IO[str],
    *args: object,
    **kwargs: object,
) -> None:
    kwargs["allow_nan"] = False
    _JSON_DUMP(value, stream, *args, **kwargs)


class StrictJsonProxy:
    """Small module-like proxy used by the legacy audit implementation."""

    JSONDecodeError = json.JSONDecodeError

    @staticmethod
    def dumps(value: object, *args: object, **kwargs: object) -> str:
        return strict_json_dumps(value, *args, **kwargs)

    @staticmethod
    def dump(
        value: object,
        stream: IO[str],
        *args: object,
        **kwargs: object,
    ) -> None:
        strict_json_dump(value, stream, *args, **kwargs)

    @staticmethod
    def loads(value: object, *args: object, **kwargs: object) -> object:
        if args or kwargs:
            raise TypeError("strict JSON proxy does not accept decoder overrides")
        return load_json_strict(value)

    @staticmethod
    def load(value: object, *args: object, **kwargs: object) -> object:
        if args or kwargs:
            raise TypeError("strict JSON proxy does not accept decoder overrides")
        return load_json_strict(value)


STRICT_JSON = StrictJsonProxy()


def repo_path(
    value: object,
    *,
    label: str = "repository-relative path",
    root: Path = ROOT,
) -> Path:
    """Return one canonical lexical path confined below ``root``."""

    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{label} must be a non-empty relative path")
    if "\\" in value or any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        raise ValueError(f"{label} contains unsafe characters")
    parsed = PurePosixPath(value)
    if (
        parsed.is_absolute()
        or not parsed.parts
        or any(part in {"", ".", ".."} for part in parsed.parts)
        or parsed.as_posix() != value
    ):
        raise ValueError(f"{label} must be a canonical repository-relative path")
    return root.joinpath(*parsed.parts)


def _relative_parts(root: Path, path: Path, *, label: str) -> tuple[str, ...]:
    root = Path(os.path.abspath(os.fspath(root)))
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = root / candidate
    candidate = Path(os.path.normpath(os.fspath(candidate)))
    try:
        relative = candidate.relative_to(root)
    except ValueError as error:
        raise ValueError(f"{label} escapes the pinned repository root") from error
    if not relative.parts or any(part in {"", ".", ".."} for part in relative.parts):
        raise ValueError(f"{label} is not a canonical repository file")
    return tuple(relative.parts)


class _SourceDescriptor:
    """Own one FD until close is attempted or the public API transfers it."""

    def __init__(self) -> None:
        self.fd: int | None = None

    def close(self) -> None:
        descriptor = None
        attempted = False
        try:
            descriptor, self.fd = self.fd, None
            if descriptor is not None:
                attempted = True; os.close(descriptor)
        except BaseException:
            if descriptor is not None and not attempted:
                self.fd = descriptor
            raise

    def __del__(self) -> None:
        try:
            self.close()
        except BaseException:
            pass


def _close_source_descriptors(owners: list[_SourceDescriptor]) -> None:
    failure = None
    for owner in reversed(owners):
        try:
            owner.close()
        except BaseException as error:
            if failure is None:
                failure = error
    if failure is not None:
        raise failure


def _open_regular_owned_beneath(
    root: Path,
    path: Path,
    *,
    label: str,
    after_component: AfterComponentHook | None = None,
) -> _SourceDescriptor:

    parts = _relative_parts(root, path, label=label)
    root_flags = os.O_RDONLY | _O_CLOEXEC | _O_DIRECTORY | _O_NOFOLLOW
    ancestors: list[_SourceDescriptor] = []
    current = _SourceDescriptor()
    ancestors.append(current)
    leaf_owner = _SourceDescriptor()
    try:
        try:
            current.fd = os.open(root, root_flags)
        except OSError as error:
            raise ValueError(f"{label} repository root is unsafe or unreadable") from error
        if not stat.S_ISDIR(os.fstat(current.fd).st_mode):
            raise ValueError(f"{label} repository root is not a directory")

        for index, component in enumerate(parts[:-1]):
            following = _SourceDescriptor()
            ancestors.append(following)
            try:
                following.fd = os.open(
                    component,
                    os.O_RDONLY | _O_CLOEXEC | _O_DIRECTORY | _O_NOFOLLOW,
                    dir_fd=current.fd,
                )
            except OSError as error:
                raise ValueError(
                    f"{label} parent is absent, non-directory, or symlinked: {component}"
                ) from error
            if not stat.S_ISDIR(os.fstat(following.fd).st_mode):
                raise ValueError(f"{label} parent is not a directory: {component}")
            if after_component is not None:
                after_component(index, component, following.fd)
            current.close()
            current = following

        leaf = parts[-1]
        try:
            leaf_owner.fd = os.open(
                leaf,
                os.O_RDONLY | _O_CLOEXEC | _O_NONBLOCK | _O_NOFOLLOW,
                dir_fd=current.fd,
            )
        except OSError as error:
            raise ValueError(
                f"{label} leaf is absent, unsafe, or symlinked: {leaf}"
            ) from error
        if not stat.S_ISREG(os.fstat(leaf_owner.fd).st_mode):
            raise ValueError(f"{label} is not a regular file: {path}")
        return leaf_owner
    except BaseException:
        leaf_owner.close()
        raise
    finally:
        _close_source_descriptors(ancestors)


def open_regular_beneath(
    root: Path,
    path: Path,
    *,
    label: str,
    after_component: AfterComponentHook | None = None,
) -> int:
    """Open a regular file through pinned directory descriptors.

    Every parent below ``root`` is opened relative to the pinned descriptor with
    ``O_DIRECTORY|O_NOFOLLOW``; the leaf is opened with ``O_NOFOLLOW``. A rename
    or symlink swap cannot redirect later lookup outside the opened chain.
    Managed owners retain the new parent and leaf through ordinary Python line
    interruption and owned-helper result loss. The returned raw ``int`` transfers
    close responsibility to the caller; final raw-result delivery, every native
    call/opcode window and repeated cleanup interruptions are not guaranteed.
    """

    owner = _open_regular_owned_beneath(
        root, path, label=label, after_component=after_component,
    )
    descriptor = owner.fd
    if descriptor is None:
        raise ValueError(f"{label} owned descriptor is unavailable")
    owner.fd = None; return descriptor


def _open_regular(path: Path, *, label: str) -> int:
    return open_regular_beneath(ROOT, path, label=label)


class ManagedSourceReader:
    """Keep descriptor ownership through reads and object/result delivery.

    No public method transfers or exposes the descriptor. This is ordinary
    Python object custody, not a sandbox or peer/signature authority. Native
    call/opcode gaps and repeated cleanup interruption remain outside scope.
    """

    _MAX_OPERATION_FRAMES = 1024

    def __init__(self) -> None:
        self._creator_pid = os.getpid()
        self._creator_thread = threading.current_thread()
        self._owner: _SourceDescriptor | None = None
        self._active = False

    def _check_creator(self) -> None:
        if self._creator_pid != os.getpid() or self._creator_thread is not threading.current_thread():
            raise ValueError("managed source reader requires its creator process and thread")

    def _descriptor(self) -> int:
        self._check_creator()
        if self._owner is None or self._owner.fd is None:
            raise ValueError("managed source reader is closed")
        return self._owner.fd

    def _ensure_idle(self) -> None:
        self._check_creator()
        if self._active:
            # Skip the public operation asking to enter. An older read/stat frame
            # on this thread is still executing, even if a callback has an error.
            # Exception traceback frames from a genuinely unwound operation are
            # not members of this current call chain.
            frame = sys._getframe(2)
            try:
                for _ in range(self._MAX_OPERATION_FRAMES):
                    if frame is None:
                        self._active = False
                        return
                    if frame.f_code in (ManagedSourceReader.read.__code__, ManagedSourceReader.read_some.__code__, ManagedSourceReader.stat.__code__) and frame.f_locals.get("self") is self:
                        raise ValueError("managed source reader does not allow reentrant operations")
                    frame = frame.f_back
                raise ValueError("managed source reader operation stack exceeds its check bound")
            finally:
                del frame

    def stat(self) -> os.stat_result:
        self._ensure_idle()
        try:
            self._active = True
            return os.fstat(self._descriptor())
        finally:
            self._active = False

    def read(self, size: int = -1) -> bytes:
        self._ensure_idle()
        if type(size) is not int:
            raise TypeError("managed read size must be an integer")
        if size < -1:
            raise ValueError("managed read size must be -1 or nonnegative")
        if size > sys.maxsize:
            raise OverflowError("managed read size exceeds the native integer bound")
        try:
            self._active = True
            descriptor = self._descriptor()
            remaining = None if size == -1 else size
            chunks = []
            while remaining is None or remaining:
                self._check_creator()
                chunk = os.read(descriptor, min(1024 * 1024, remaining) if remaining is not None else 1024 * 1024)
                if not chunk:
                    break
                chunks.append(chunk)
                if remaining is not None:
                    remaining -= len(chunk)
            return b"".join(chunks)
        finally:
            self._active = False

    def close(self) -> None:
        self._ensure_idle()
        if self._owner is not None:
            self._owner.close()

    def read_some(self, size: int) -> bytes:
        """Perform one native read, retaining short-read/deadline granularity.

        Size is an exact nonnegative int within sys.maxsize. This differs from
        read's fill-until-count/EOF behavior, while keeping the same owner,
        creator, non-reentry and interruption rules. No descriptor is returned.
        """
        self._ensure_idle()
        if type(size) is not int:
            raise TypeError("managed single read size must be an integer")
        if size < 0:
            raise ValueError("managed single read size must be nonnegative")
        if size > sys.maxsize:
            raise OverflowError("managed single read size exceeds the native integer bound")
        try:
            self._active = True
            return os.read(self._descriptor(), size)
        finally:
            self._active = False

    def __enter__(self) -> ManagedSourceReader:
        self._ensure_idle()
        self._descriptor()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def __del__(self) -> None:
        # A live method retains self. Actual last-reference cleanup can therefore
        # release its descriptor even when an interrupted finally left _active set.
        owner = getattr(self, "_owner", None)
        if owner is not None:
            try:
                owner.close()
            except BaseException:
                pass


def open_managed_regular_beneath(
    root: Path,
    path: Path,
    *,
    label: str,
    after_component: AfterComponentHook | None = None,
) -> ManagedSourceReader:
    """Open the same regular-file policy without transferring a raw FD."""
    reader = ManagedSourceReader()
    try:
        reader._owner = _open_regular_owned_beneath(
            root, path, label=label, after_component=after_component,
        )
        return reader
    except BaseException:
        reader.close()
        raise


def read_bytes_beneath(
    root: Path,
    path: Path,
    *,
    label: str = "source file",
    after_component: AfterComponentHook | None = None,
) -> bytes:
    with open_managed_regular_beneath(
        root,
        path,
        label=label,
        after_component=after_component,
    ) as reader:
        return reader.read()


def read_text_nofollow(path: Path, *, label: str = "source file") -> str:
    # Preserve TextIOWrapper's UTF-8 and universal-newline result semantics.
    return read_bytes_nofollow(path, label=label).decode("utf-8").replace("\r\n", "\n").replace("\r", "\n")


def read_bytes_nofollow(path: Path, *, label: str = "source file") -> bytes:
    return read_bytes_beneath(ROOT, path, label=label)


def load_json_nofollow(path: Path, *, label: str = "JSON source") -> object:
    return load_json_strict(read_text_nofollow(path, label=label))


def regular_file_exists_nofollow(path: Path, *, label: str) -> bool:
    try:
        with open_managed_regular_beneath(ROOT, path, label=label):
            return True
    except ValueError:
        return False


def sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(read_bytes_nofollow(path, label="hashed source")).hexdigest()


def git_blob_sha1(path: Path) -> str:
    import hashlib

    payload = read_bytes_nofollow(path, label="Git-blob source")
    header = f"blob {len(payload)}\0".encode("ascii")
    return hashlib.sha1(header + payload).hexdigest()
