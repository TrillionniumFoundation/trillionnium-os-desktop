#!/usr/bin/env python3
"""Explicit immutable-fixture host qualification; never product authority.

Actual systemd, pidfd, /proc and pidfd_getfd are mandatory. Missing support is
an error. The inspector runs as root solely to duplicate stopped unit FDs; the
renderer has zero caps and no_new_privs. It never emits cmdline or IPC tokens.
"""
from __future__ import annotations

import argparse
import ast
from contextlib import ExitStack
import ctypes
import hashlib
import json
import os
from pathlib import Path
import re
import select
import signal
import socket
import stat
import subprocess
import threading
import time
import uuid

try:
    from .browser_codec_reference_security import load_json_strict
    from .check_servo_resource_gate import validate as validate_resource
    from .artifact_evidence import open_file
except ImportError:
    from browser_codec_reference_security import load_json_strict
    from check_servo_resource_gate import validate as validate_resource
    from artifact_evidence import open_file

ROOT = Path(__file__).absolute().parents[1]
PROFILE = "immutable-origin-v1"
PIN = "670ae8a70801b162e186f81cbb5bdd2d59c39108"
ORIGIN = "https://fixture.netns-qualification.invalid"
MAX_BYTES = 2 * 1024 * 1024
MAX_FDS = 256
ERRNOS = {1, 13, 97}
SOURCE_PATHS = (".github/workflows/servo-headed-runtime.yml", "tools/run_servo_headed_runtime_gate.sh",
    "tools/servo_namespace_qualification.py", "tools/check_servo_resource_gate.py", "tools/browser_codec_reference_security.py",
    "tools/artifact_evidence.py",
    "experiments/servo-headed-runtime/src/main.rs", "experiments/servo-headed-runtime/src/input_ownership.rs",
    "experiments/servo-headed-runtime/src/resource_gate.rs", "experiments/servo-headed-runtime/src/network_confinement.rs",
    "experiments/servo-headed-runtime/fixture/index.html", "manifests/servo.lock.json",
    "contracts/native-direct-inet-qualification.v1.json")
COMPILED_PATHS = ("trillionnium_headed_runtime.rs", "input_ownership.rs", "resource_gate.rs", "network_confinement.rs",
                  "trillionnium_headed_fixture.html")
IDENTITY_KEYS = {"pid", "ppid", "pgid", "session", "start_time", "state"}
ENTRY_KEYS = {"schema", "profile", "role", "pid", "start_time", "network_namespace_inode",
    "cap_effective", "cap_bounding", "cap_ambient", "no_new_privileges", "seccomp_filter_observed",
    "tcp_ipv4_errno", "udp_ipv4_errno", "tcp_ipv6_errno", "udp_ipv6_errno", "unix_payload_roundtrip",
    "descriptor_inventory", "entry_stop_requested", "source_qualification_only", "installed_qualified", "production_ready"}
REFUSAL_KEYS = {"schema", "profile", "role", "pid", "start_time", "network_namespace_inode", "reason",
    "entry_stop_requested", "engine_started", "source_qualification_only", "installed_qualified", "production_ready"}
HOST_KEYS = {"schema", "unit", "control_group", "main_pid", "role", "identity", "executable_identity",
    "network_namespace_inode", "outside_network_namespace_inode", "caps", "no_new_privileges", "seccomp",
    "unit_properties", "descriptor_inventory", "pidfd_retained", "entry_stopped", "content_argument_observed",
    "renderer_uid", "renderer_gid", "read_write_paths", "temporary_directory", "source_qualification_only", "installed_qualified", "production_ready"}
TEMP_KEYS = {"path", "device", "inode", "uid", "mode"}
LAUNCH_KEYS = {"schema", "case", "unit", "main_pid", "binary_identity", "binary_sha256", "outside_namespace",
    "entries", "exit_code", "owned_unit_stopped", "exact_processes_exited", "qualification_nonce_enabled",
    "per_pair_ack_pacing", "renderer_uid", "renderer_gid", "renderer_path", "temporary_directory",
    "temporary_directory_removed", "source_qualification_only", "installed_qualified", "production_ready"}
PROPERTIES = {"PrivateNetwork": "yes", "RestrictAddressFamilies": "AF_UNIX", "NoNewPrivileges": "yes",
    "CapabilityBoundingSet": "", "RestrictNamespaces": "yes", "SystemCallArchitectures": "native",
    "ProtectSystem": "strict", "ProtectHome": "read-only", "PrivateTmp": "no"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def exact(value: object, expected: object, label: str) -> None:
    require(type(value) is type(expected) and value == expected, label)


def exact_tree(value: object, expected: object, label: str) -> None:
    require(type(value) is type(expected), label)
    if type(expected) is dict:
        require(set(value) == set(expected), label)
        for key in expected:
            exact_tree(value[key], expected[key], label)
    elif type(expected) is list:
        require(len(value) == len(expected), label)
        for actual, required in zip(value, expected):
            exact_tree(actual, required, label)
    else:
        require(value == expected, label)


def closed(value: object, keys: set[str], label: str) -> dict:
    require(type(value) is dict and set(value) == keys, label)
    return value


def integer(value: object, label: str, minimum: int = 1) -> int:
    require(type(value) is int and minimum <= value <= 2**64 - 1, label)
    return value


def snapshot(value: os.stat_result) -> tuple:
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns)


def hash_regular(path: Path, limit: int = 4 * 1024**3) -> str:
    descriptor = open_file(path.absolute())
    try:
        before = os.fstat(descriptor)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == os.getuid()
            and before.st_mode & 0o022 == 0 and 0 < before.st_size <= limit, "compiled/source input unsafe")
        digest = hashlib.sha256()
        total = 0
        deadline = time.monotonic() + 60
        while True:
            block = os.read(descriptor, 1024 * 1024)
            if not block:
                break
            digest.update(block)
            total += len(block)
            require(total <= limit and time.monotonic() < deadline, "compiled/source input hash exceeded bounds")
        require(snapshot(os.fstat(descriptor)) == snapshot(before) and total == before.st_size, "compiled/source input changed")
        named = open_file(path.absolute())
        try:
            require(snapshot(os.fstat(named)) == snapshot(before), "compiled/source input name changed")
        finally:
            os.close(named)
        return digest.hexdigest()
    finally:
        os.close(descriptor)


class _StagingDescriptor:
    """Empty before acquisition; descriptor cleanup never acts on pathnames."""
    def __init__(self):
        self.fd = None

    def close(self):
        descriptor = None
        close_attempted = False
        try:
            descriptor, self.fd = self.fd, None
            if descriptor is not None:
                # Keep the attempt mark and native call on one traceable line.
                # A line interruption before this call can retire the local FD;
                # an attempted close must never retry a potentially reused FD.
                close_attempted = True; os.close(descriptor)
        except BaseException:
            if descriptor is not None and not close_attempted:
                os.close(descriptor)
            raise

    def __del__(self):
        try:
            self.close()
        except BaseException:
            pass


class _StagingPath:
    """Retain every NOFOLLOW ancestor and the opened leaf until retirement."""
    def __init__(self):
        self.owners = []
        self.path = None

    @classmethod
    def open(cls, path: Path, *, directory=False):
        value = cls()
        value.path = path.absolute()
        require(".." not in value.path.parts, "staging path is not canonical")
        parts = value.path.parts[1:]
        require(bool(parts) or directory, "staging input is not a file")
        try:
            root = _StagingDescriptor()
            value.owners.append(root)
            root.fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
            for index, part in enumerate(parts):
                owner = _StagingDescriptor()
                parent = value.owners[-1].fd
                value.owners.append(owner)
                flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
                if directory or index < len(parts) - 1:
                    flags |= os.O_DIRECTORY
                owner.fd = os.open(part, flags, dir_fd=parent)
            return value
        except BaseException:
            value.close()
            raise

    @property
    def fd(self):
        require(bool(self.owners) and self.owners[-1].fd is not None, "staging descriptor retired")
        return self.owners[-1].fd

    def identities(self):
        return [(item.st_dev, item.st_ino) for item in (os.fstat(owner.fd) for owner in self.owners)]

    def close(self):
        error = None
        while self.owners:
            owner = self.owners.pop()
            try:
                owner.close()
            except BaseException as failure:
                if error is None:
                    error = failure
        if error is not None:
            raise error

    def __del__(self):
        try:
            self.close()
        except BaseException:
            pass


class _StagedExecutable:
    """Private single-link copy of an explicitly supplied Cargo executable.

    Only this compiled-input admission accepts multiple source hard links.
    Source/portable readers retain their strict single-link rule. Cleanup is
    creator-only, and a failed unit corpus retains the private file for review.
    """
    LIMIT = 4 * 1024**3
    BUDGET = 60

    def __init__(self, source: Path, *, artifact_root: Path | None = None):
        self.owner_pid = os.getpid()
        self.source = None
        self.parent = None
        self.root = None
        self.copy = _StagingDescriptor()
        self.path = None
        self.source_snapshot = None
        self.copy_snapshot = None
        self.digest = None
        try:
            self.source = _StagingPath.open(source)
            before = os.fstat(self.source.fd)
            require(stat.S_ISREG(before.st_mode) and before.st_uid == os.getuid()
                and before.st_nlink >= 1 and before.st_mode & 0o022 == 0
                and before.st_mode & 0o100 != 0 and 0 < before.st_size <= self.LIMIT,
                "compiled executable source unsafe")
            self.source_snapshot = snapshot(before)
            # The unit does not enable PrivateTmp. Use the explicit runner work
            # directory, outside the uploaded artifacts, rather than /tmp.
            parent = Path(os.environ.get("RUNNER_TEMP", str(ROOT.parent))).absolute()
            excluded = [ROOT / "artifacts"]
            if artifact_root is not None:
                excluded.append(Path(os.path.abspath(artifact_root)))
            require(not any(parent.is_relative_to(path) for path in excluded),
                    "executable staging must be outside artifact output")
            self.parent = _StagingPath.open(parent, directory=True)
            name = ".hepta-netns-exec-" + uuid.uuid4().hex
            os.mkdir(name, 0o700, dir_fd=self.parent.fd)
            self.root = _StagingPath.open(parent / name, directory=True)
            require(self.root.identities()[:-1] == self.parent.identities(), "staging parent changed")
            self._check_root()
            self.path = parent / name / "runtime"
            self.copy.fd = os.open("runtime", os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                                   0o500, dir_fd=self.root.fd)
            value = hashlib.sha256()
            total = 0
            deadline = time.monotonic() + self.BUDGET
            while True:
                require(time.monotonic() < deadline, "executable staging deadline expired")
                block = os.read(self.source.fd, 1024 * 1024)
                require(time.monotonic() < deadline, "executable staging deadline expired")
                if not block:
                    break
                total += len(block)
                require(total <= self.LIMIT, "executable staging byte limit exceeded")
                value.update(block)
                pending = memoryview(block)
                while pending:
                    require(time.monotonic() < deadline, "executable staging deadline expired")
                    written = os.write(self.copy.fd, pending)
                    require(time.monotonic() < deadline, "executable staging deadline expired")
                    require(written > 0, "executable staging short write")
                    pending = pending[written:]
            require(total == before.st_size and snapshot(os.fstat(self.source.fd)) == self.source_snapshot,
                    "compiled executable source changed during copy")
            os.fchmod(self.copy.fd, 0o500)
            os.fsync(self.copy.fd)
            os.fsync(self.root.fd)
            self.copy_snapshot = snapshot(os.fstat(self.copy.fd))
            self.digest = value.hexdigest()
            readonly = _StagingDescriptor()
            readonly.fd = os.open("runtime", os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                  dir_fd=self.root.fd)
            require(snapshot(os.fstat(readonly.fd)) == self.copy_snapshot, "staged executable changed before read-only retention")
            writable, self.copy = self.copy, readonly
            writable.close()  # A retained writable FD would make exec fail ETXTBSY.
            self.verify()
            require(time.monotonic() < deadline, "executable staging deadline expired")
        except BaseException:
            self.close(remove=True)
            raise

    def _creator(self):
        require(os.getpid() == self.owner_pid, "staging owner inherited by child")

    def _check_root(self):
        metadata = os.fstat(self.root.fd)
        require(stat.S_ISDIR(metadata.st_mode) and metadata.st_uid == os.getuid()
                and stat.S_IMODE(metadata.st_mode) == 0o700, "staging directory unsafe")
        current = _StagingPath.open(self.root.path, directory=True)
        try:
            require(current.identities() == self.root.identities(), "staging directory path changed")
        finally:
            current.close()

    def _source_current(self):
        require(snapshot(os.fstat(self.source.fd)) == self.source_snapshot, "compiled executable source changed")
        current = _StagingPath.open(self.source.path)
        try:
            require(current.identities() == self.source.identities()
                and snapshot(os.fstat(current.fd)) == self.source_snapshot, "compiled executable source name changed")
        finally:
            current.close()

    def verify(self):
        self._creator()
        deadline = time.monotonic() + self.BUDGET
        self._source_current()
        self._check_root()
        metadata = os.fstat(self.copy.fd)
        require(snapshot(metadata) == self.copy_snapshot and metadata.st_uid == os.getuid()
            and metadata.st_nlink == 1 and stat.S_IMODE(metadata.st_mode) == 0o500,
            "staged executable metadata changed")
        current = _StagingPath.open(self.path)
        try:
            require(current.identities()[:-1] == self.root.identities()
                and snapshot(os.fstat(current.fd)) == self.copy_snapshot, "staged executable name changed")
        finally:
            current.close()
        require(hash_regular(self.path, self.LIMIT) == self.digest, "staged executable bytes changed")
        require(time.monotonic() < deadline, "compiled executable recheck deadline expired")
        value = hashlib.sha256()
        position = 0
        while position < self.source_snapshot[5]:
            require(time.monotonic() < deadline, "compiled executable recheck deadline expired")
            block = os.pread(self.source.fd, min(1024 * 1024, self.source_snapshot[5] - position), position)
            require(time.monotonic() < deadline, "compiled executable recheck deadline expired")
            require(bool(block), "compiled executable recheck truncated")
            value.update(block)
            position += len(block)
        self._source_current()
        require(value.hexdigest() == self.digest, "compiled executable source bytes changed")
        require(time.monotonic() < deadline, "compiled executable recheck deadline expired")
        return self.digest

    def close(self, *, remove=False):
        self._creator()
        error = None
        try:
            if remove and self.root is not None:
                self._check_root()
                if self.path is not None and self.copy is not None and self.copy.fd is not None:
                    current = _StagingPath.open(self.path)
                    try:
                        require(current.identities()[:-1] == self.root.identities()
                            and (os.fstat(current.fd).st_dev, os.fstat(current.fd).st_ino)
                            == (os.fstat(self.copy.fd).st_dev, os.fstat(self.copy.fd).st_ino),
                            "staged executable cleanup name changed")
                    finally:
                        current.close()
                    os.unlink("runtime", dir_fd=self.root.fd)
                require(not os.listdir(self.root.fd), "staging directory contains foreign entries")
                os.rmdir(self.root.path.name, dir_fd=self.parent.fd)
        except BaseException as failure:
            error = failure
        finally:
            for name in ("copy", "root", "parent", "source"):
                owner = getattr(self, name, None)
                setattr(self, name, None)
                if owner is not None:
                    try:
                        owner.close()
                    except BaseException as failure:
                        if error is None:
                            error = failure
        if error is not None:
            raise error

    def __enter__(self):
        self.verify()
        return self

    def __exit__(self, kind, value, traceback):
        self.close(remove=kind is None)

    def __del__(self):
        # Never unlink from GC or from a copied process. Detach first, and close
        # only these descriptor copies, without mutating the parent's paths.
        for name in ("copy", "root", "parent", "source"):
            owner = getattr(self, name, None)
            setattr(self, name, None)
            if owner is not None:
                try:
                    owner.close()
                except BaseException:
                    pass


def validate_temporary_directory(value: object, uid: int) -> dict:
    value = closed(value, TEMP_KEYS, "temporary directory fields")
    require(type(value["path"]) is str and re.fullmatch(r"/tmp/hn-[a-f0-9]{24}", value["path"]),
            "temporary directory is not a short owned profile path")
    integer(value["device"], "temporary directory device", 0)
    integer(value["inode"], "temporary directory inode")
    integer(value["uid"], "temporary directory UID")
    exact(value["uid"], uid, "temporary directory owner differs from renderer")
    exact(value["mode"], 0o700, "temporary directory is not private0700")
    return value


class _PrivateTemporaryDirectory:
    """Short retained directory for one unit; GC never removes pathnames."""
    MAX_ENTRIES = 256
    MAX_BYTES = 32 * 1024 * 1024
    MAX_DEPTH = 4

    def __init__(self):
        self.owner_pid = os.getpid()
        self.parent = self.root = None
        self.path = None
        self.identity = None
        try:
            self.parent = _StagingPath.open(Path("/tmp"), directory=True)
            parent = os.fstat(self.parent.fd)
            require(parent.st_uid == 0 and stat.S_IMODE(parent.st_mode) == 0o1777,
                    "temporary parent is not the actual root-owned sticky directory")
            self.path = Path("/tmp") / ("hn-" + uuid.uuid4().hex[:24])
            os.mkdir(self.path.name, 0o700, dir_fd=self.parent.fd)
            self.root = _StagingPath.open(self.path, directory=True)
            require(self.root.identities()[:-1] == self.parent.identities(), "temporary parent changed")
            metadata = os.fstat(self.root.fd)
            self.identity = {"path": str(self.path), "device": metadata.st_dev, "inode": metadata.st_ino,
                             "uid": metadata.st_uid, "mode": stat.S_IMODE(metadata.st_mode)}
            self.verify()
        except BaseException:
            self.close(remove=self.identity is not None)
            raise

    def verify(self) -> dict:
        require(os.getpid() == self.owner_pid, "temporary owner inherited across fork")
        validate_temporary_directory(self.identity, os.getuid())
        current = _StagingPath.open(self.path, directory=True)
        try:
            require(current.identities() == self.root.identities(), "temporary directory pathname changed")
            metadata = os.fstat(current.fd)
            require(stat.S_ISDIR(metadata.st_mode) and {"path": str(self.path), "device": metadata.st_dev,
                "inode": metadata.st_ino, "uid": metadata.st_uid, "mode": stat.S_IMODE(metadata.st_mode)} == self.identity,
                "temporary directory custody changed")
        finally:
            current.close()
        return dict(self.identity)

    def _remove_owned_tree(self) -> None:
        """Bounded retained-inode tree, after the unit and every observed process retire."""
        self.verify()
        owners, records = [], []
        total = enumerated = 0
        deadline = time.monotonic() + 5
        try:
            def scan(parent_fd, depth):
                nonlocal total, enumerated
                require(time.monotonic() < deadline, "temporary cleanup deadline expired")
                require(depth <= self.MAX_DEPTH, "temporary cleanup depth exceeded")
                children = []
                with os.scandir(parent_fd) as entries:
                    while True:
                        require(time.monotonic() < deadline, "temporary cleanup deadline expired")
                        entry = next(entries, None)
                        require(time.monotonic() < deadline, "temporary cleanup deadline expired")
                        if entry is None:
                            break
                        enumerated += 1
                        require(enumerated <= self.MAX_ENTRIES, "temporary cleanup entry bound exceeded")
                        name = entry.name
                        require(time.monotonic() < deadline, "temporary cleanup deadline expired")
                        owner = _StagingDescriptor(); owners.append(owner)
                        owner.fd = os.open(name, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent_fd)
                        before = os.fstat(owner.fd)
                        kind = "directory" if stat.S_ISDIR(before.st_mode) else "leaf"
                        require((stat.S_ISDIR(before.st_mode) or stat.S_ISREG(before.st_mode) or stat.S_ISSOCK(before.st_mode))
                            and before.st_uid == os.getuid() and before.st_mode & 0o022 == 0,
                            "temporary cleanup refuses foreign or unsafe contents")
                        require(kind == "directory" or before.st_nlink == 1, "temporary cleanup refuses aliased contents")
                        total += before.st_size if stat.S_ISREG(before.st_mode) else 0
                        require(total <= self.MAX_BYTES, "temporary cleanup byte bound exceeded")
                        record = {"name": name, "parent": parent_fd, "owner": owner, "before": before,
                                  "kind": kind, "children": []}
                        records.append(record); children.append(record)
                        if kind == "directory":
                            directory = _StagingDescriptor(); owners.append(directory)
                            directory.fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                                   dir_fd=parent_fd)
                            require(snapshot(os.fstat(directory.fd)) == snapshot(before), "temporary child changed")
                            record["children"] = scan(directory.fd, depth + 1)
                return children
            scan(self.root.fd, 1)
            self.verify()
            # A foreign substitution found during the complete scan causes no deletion.
            for record in records:
                require(time.monotonic() < deadline, "temporary cleanup deadline expired")
                require(snapshot(os.stat(record["name"], dir_fd=record["parent"], follow_symlinks=False))
                    == snapshot(record["before"]) == snapshot(os.fstat(record["owner"].fd)),
                    "temporary cleanup name changed")
            for record in reversed(records):
                require(time.monotonic() < deadline, "temporary cleanup deadline expired")
                self.verify()
                named = os.stat(record["name"], dir_fd=record["parent"], follow_symlinks=False)
                before = record["before"]
                if record["kind"] == "directory":
                    require((named.st_dev, named.st_ino, named.st_mode, named.st_uid)
                        == (before.st_dev, before.st_ino, before.st_mode, before.st_uid),
                        "temporary cleanup directory replaced")
                    os.rmdir(record["name"], dir_fd=record["parent"])
                else:
                    require(snapshot(named) == snapshot(before) == snapshot(os.fstat(record["owner"].fd)),
                            "temporary cleanup leaf replaced")
                    os.unlink(record["name"], dir_fd=record["parent"])
            self.verify()
            with os.scandir(self.root.fd) as entries:
                require(time.monotonic() < deadline, "temporary cleanup deadline expired")
                first = next(entries, None)
                require(time.monotonic() < deadline, "temporary cleanup deadline expired")
                require(first is None, "temporary directory contains foreign names")
            require(time.monotonic() < deadline, "temporary cleanup deadline expired")
            os.rmdir(self.path.name, dir_fd=self.parent.fd)
            require(time.monotonic() < deadline, "temporary cleanup deadline expired after final removal")
        finally:
            pending, owners = owners, []
            error = None
            for owner in reversed(pending):
                try: owner.close()
                except BaseException as failure:
                    if error is None: error = failure
            if error is not None: raise error

    def _close_descriptors(self):
        pending = [self.root, self.parent]
        self.root = self.parent = None
        error = None
        for owner in pending:
            if owner is not None:
                try: owner.close()
                except BaseException as failure:
                    if error is None: error = failure
        if error is not None: raise error

    def close(self, *, remove=False):
        require(os.getpid() == self.owner_pid, "temporary owner inherited across fork")
        try:
            if remove: self._remove_owned_tree()
        finally:
            self._close_descriptors()

    def __del__(self):
        try: self._close_descriptors()
        except BaseException: pass


class Packet:
    """Complete, bounded original bytes, rechecked before any result receipt."""
    def __init__(self, root: Path):
        self.root = root.absolute()
        self.observed: dict[str, tuple[tuple, str]] = {}

    def read(self, name: str, limit: int = MAX_BYTES) -> bytes:
        require(type(name) is str and re.fullmatch(r"[A-Za-z0-9_.-]+", name) is not None,
                "packet filename is not canonical")
        path = self.root / name
        descriptor = open_file(path.absolute())
        try:
            before = os.fstat(descriptor)
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_uid == os.getuid()
                    and before.st_mode & 0o022 == 0 and 0 < before.st_size <= limit, "packet metadata unsafe")
            chunks, total = [], 0
            while True:
                block = os.read(descriptor, min(65536, limit + 1 - total))
                if not block:
                    break
                chunks.append(block)
                total += len(block)
                require(total <= limit, "packet exceeded bound")
            require(snapshot(os.fstat(descriptor)) == snapshot(before) and total == before.st_size,
                    "packet changed during read")
            named = open_file(path.absolute())
            try:
                require(snapshot(os.fstat(named)) == snapshot(before), "packet pathname changed")
            finally:
                os.close(named)
            data = b"".join(chunks)
            current = (snapshot(before), hashlib.sha256(data).hexdigest())
            require(name not in self.observed or self.observed[name] == current, "packet changed across reads")
            self.observed[name] = current
            return data
        finally:
            os.close(descriptor)

    def json(self, name: str) -> object:
        return load_json_strict(self.read(name).decode("utf-8"))

    def finish(self) -> dict:
        for name in tuple(self.observed):
            self.read(name, 16 * 1024 * 1024)
        return {name: value[1] for name, value in sorted(self.observed.items())}


def command(arguments: list[str], *, timeout: float = 5, environment: dict | None = None) -> str:
    result = subprocess.run(arguments, env=environment, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            timeout=timeout, check=True, text=True)
    require(len(result.stdout.encode()) <= MAX_BYTES and len(result.stderr.encode()) <= MAX_BYTES,
            "host command output exceeded bound")
    return result.stdout.strip()


def write_json(path: Path, value: object) -> None:
    # All destinations belong to the host's freshly created private directory.
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.write((json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())


def proc_bytes(pid: int, name: str, limit: int = 32768) -> bytes:
    with open(f"/proc/{pid}/{name}", "rb", buffering=0) as stream:
        value = stream.read(limit + 1)
    require(0 < len(value) <= limit, "proc record exceeded bound")
    return value


def process_stat(pid: int) -> dict:
    integer(pid, "process PID invalid", 2)
    value = proc_bytes(pid, "stat").decode().rsplit(")", 1)[1].split()
    result = {"pid": pid, "ppid": int(value[1]), "pgid": int(value[2]), "session": int(value[3]),
              "start_time": int(value[19]), "state": value[0]}
    for key in IDENTITY_KEYS - {"state"}:
        integer(result[key], "process identity invalid", 0 if key == "ppid" else 1)
    return result


def ns_inode(pid: int) -> int:
    match = re.fullmatch(r"net:\[([1-9][0-9]*)\]", os.readlink(f"/proc/{pid}/ns/net"))
    require(match is not None, "noncanonical network namespace")
    return integer(int(match[1]), "network namespace invalid")


def unit_properties(unit: str) -> dict:
    require(re.fullmatch(r"hepta-netns-[a-f0-9]{32}\.service", unit) is not None, "unit name is not owned")
    names = (*PROPERTIES, "MainPID", "ControlGroup", "User", "Group", "ReadWritePaths", "Result", "ExecMainCode", "ExecMainStatus", "ActiveState")
    value = command(["sudo", "-n", "systemctl", "show", unit, *(f"--property={name}" for name in names)])
    result = dict(line.split("=", 1) for line in value.splitlines())
    require(set(result) == set(names), "unit property fields absent")
    return result


def _validate_host(value: object, role: str, executable: dict, outside: int, main_pid: int,
                   *, standalone_negative: bool = False, renderer_identity: tuple[int, int] | None = None,
                   renderer_path: str | None = None, temporary_directory: dict | None = None) -> dict:
    value = closed(value, HOST_KEYS, "host observation fields invalid")
    exact(value["schema"], "trillionnium.desktop.netns-host-observation.v1", "host schema")
    exact(value["role"], role, "host role")
    require(type(value["unit"]) is str and re.fullmatch(r"hepta-netns-[a-f0-9]{32}\.service", value["unit"]), "host unit")
    exact(value["control_group"], "/system.slice/" + value["unit"], "host unit cgroup")
    exact(value["main_pid"], main_pid, "host MainPID")
    integer(main_pid, "host MainPID integer", 2)
    identity = closed(value["identity"], IDENTITY_KEYS, "host identity fields")
    for key in IDENTITY_KEYS - {"state"}:
        integer(identity[key], "host identity integer", 0 if key == "ppid" else 1)
    exact(identity["state"], "T", "host process was not stopped")
    if role == "embedder" or standalone_negative:
        exact(identity["pid"], main_pid, "host native PID")
        exact(identity["ppid"], 1, "host native is not actual systemd child")
    else:
        exact(identity["ppid"], main_pid, "content is not native direct child")
        require(identity["pid"] != main_pid, "content identity aliases native owner")
    binary = closed(value["executable_identity"], {"device", "inode"}, "host binary fields")
    integer(binary["device"], "host binary device", 0)
    integer(binary["inode"], "host binary inode")
    require(binary == executable, "host executable differs from before-launch binary")
    integer(value["network_namespace_inode"], "host namespace integer")
    exact(value["outside_network_namespace_inode"], outside, "host outside namespace")
    require(value["network_namespace_inode"] != outside, "host still sees outside namespace")
    exact(value["caps"], {"CapEff": "0000000000000000", "CapBnd": "0000000000000000", "CapAmb": "0000000000000000"}, "host capabilities")
    exact(value["no_new_privileges"], 1, "host NNP")
    exact(value["seccomp"], 2, "host seccomp")
    exact(value["unit_properties"], PROPERTIES, "host confinement unit properties")
    integer(value["renderer_uid"], "host renderer UID")
    integer(value["renderer_gid"], "host renderer GID")
    temporary = validate_temporary_directory(value["temporary_directory"], value["renderer_uid"])
    if temporary_directory is not None:
        exact_tree(temporary, temporary_directory, "host temporary directory differs from retained launch")
    require(type(value["read_write_paths"]) is str, "host writer path")
    paths = value["read_write_paths"].split(" ")
    require(len(paths) == 2 and len(set(paths)) == 2 and temporary["path"] in paths
        and all(path.startswith("/") and not re.search(r"\s|\.\.", path) for path in paths), "host writer paths invalid")
    if renderer_identity is not None:
        exact(value["renderer_uid"], renderer_identity[0], "host renderer UID differs from launch")
        exact(value["renderer_gid"], renderer_identity[1], "host renderer GID differs from launch")
    if renderer_path is not None:
        require(set(paths) == {renderer_path, temporary["path"]}, "host renderer may write outside approved output and private temporary")
    for key, expected in (("pidfd_retained", True), ("entry_stopped", True), ("content_argument_observed", role == "content"),
                          ("source_qualification_only", True), ("installed_qualified", False), ("production_ready", False)):
        exact(value[key], expected, "host qualification ceiling")
    inventory = value["descriptor_inventory"]
    require(type(inventory) is list and 0 < len(inventory) <= MAX_FDS, "host descriptor bound")
    seen = set()
    for raw in inventory:
        item = closed(raw, {"fd", "device", "inode", "kind", "socket_domain"}, "host descriptor fields")
        fd = integer(item["fd"], "host FD integer", 0)
        require(fd not in seen and fd <= 2**31 - 1, "host FD duplicate/overflow")
        seen.add(fd)
        integer(item["device"], "host FD device", 0)
        integer(item["inode"], "host FD inode")
        require(item["kind"] in {"socket", "pipe", "character_device", "file"}, "host FD kind")
        if item["kind"] == "socket":
            integer(item["socket_domain"], "host actual socket domain")
        else:
            exact(item["socket_domain"], None, "host nonsocket carries domain")
    return value


def validate_binding(entry: object, host: object, executable: dict, outside: int, main_pid: int,
                     *, inherited_family: int | None = None, renderer_identity: tuple[int, int] | None = None,
                     renderer_path: str | None = None, temporary_directory: dict | None = None) -> None:
    keys = REFUSAL_KEYS if inherited_family is not None else ENTRY_KEYS
    entry = closed(entry, keys, "entry closed fields")
    exact(entry["profile"], PROFILE, "entry profile")
    require(entry["role"] in {"embedder", "content"}, "entry role")
    host = _validate_host(host, entry["role"], executable, outside, main_pid,
                          standalone_negative=inherited_family is not None,
                          renderer_identity=renderer_identity, renderer_path=renderer_path,
                          temporary_directory=temporary_directory)
    for key in ("pid", "start_time"):
        integer(entry[key], "entry identity integer", 2 if key == "pid" else 1)
        exact(entry[key], host["identity"][key], "entry identity differs from actual retained host process")
    exact(entry["network_namespace_inode"], host["network_namespace_inode"], "entry namespace differs from actual host")
    for key, expected in (("entry_stop_requested", True), ("source_qualification_only", True),
                          ("installed_qualified", False), ("production_ready", False)):
        exact(entry[key], expected, "entry claim ceiling")
    sockets = [item for item in host["descriptor_inventory"] if item["kind"] == "socket"]
    if inherited_family is not None:
        require(type(inherited_family) is int and inherited_family in {socket.AF_INET, socket.AF_INET6}, "negative family")
        exact(entry["schema"], "trillionnium.desktop.netns-refusal.v1", "refusal schema")
        exact(entry["reason"], "entry_descriptor_inventory_refused", "refusal cause")
        exact(entry["engine_started"], False, "refusal engine started")
        require(any(item["fd"] == 0 and item["socket_domain"] == inherited_family for item in sockets),
                "negative does not independently prove original inherited INET FD")
        require(all(item["socket_domain"] in {socket.AF_UNIX, inherited_family} for item in sockets), "unexpected negative domain")
        return
    exact(entry["schema"], "trillionnium.desktop.netns-entry.v1", "entry schema")
    require(all(item["socket_domain"] == socket.AF_UNIX for item in sockets), "host observed an INET/non-UNIX socket")
    for key, expected in (("cap_effective", 0), ("cap_bounding", 0), ("cap_ambient", 0),
                          ("no_new_privileges", True), ("seccomp_filter_observed", True), ("unix_payload_roundtrip", True)):
        exact(entry[key], expected, "entry kernel/Unix claim")
    for key in ("tcp_ipv4_errno", "udp_ipv4_errno", "tcp_ipv6_errno", "udp_ipv6_errno"):
        require(type(entry[key]) is int and entry[key] in ERRNOS, "routing/no-support failure is not protocol refusal")
    inventory = entry["descriptor_inventory"]
    require(type(inventory) is list and 0 < len(inventory) <= MAX_FDS, "entry FD bound")
    observed = {item["fd"]: item for item in host["descriptor_inventory"]}
    seen = set()
    for raw in inventory:
        item = closed(raw, {"fd", "device", "inode", "kind"}, "entry FD fields")
        fd = integer(item["fd"], "entry FD integer", 0)
        require(fd not in seen and fd in observed, "entry FD duplicate or not retained by host")
        seen.add(fd)
        integer(item["inode"], "entry FD inode")
        integer(item["device"], "entry FD device", 0)
        exact(item["device"], observed[fd]["device"], "entry FD differs from actual host duplicated device")
        exact(item["inode"], observed[fd]["inode"], "entry FD differs from actual host duplicated inode")
        expected = "unix_socket" if observed[fd]["kind"] == "socket" else observed[fd]["kind"]
        exact(item["kind"], expected, "entry FD type differs from actual host")


def inspect_stopped(request: dict) -> dict:
    """Root test helper: retained actual kernel process, never asserted identity."""
    require(os.geteuid() == 0, "independent FD observer requires root test profile")
    request = closed(request, {"unit", "pid", "start_time", "main_pid", "role", "binary_identity", "outside_namespace",
        "standalone_negative", "renderer_uid", "renderer_gid", "renderer_path", "temporary_directory"}, "inspect request")
    require(type(request["standalone_negative"]) is bool, "inspect negative profile type")
    pid = integer(request["pid"], "inspect PID", 2)
    deadline = time.monotonic() + 4
    descriptor = os.pidfd_open(pid)
    retained_temporary = None
    try:
        require(not select.select([descriptor], [], [], 0)[0], "inspected process already exited")
        before = process_stat(pid)
        require(before["state"] == "T" and before["start_time"] == request["start_time"], "inspect incarnation not stopped")
        properties = unit_properties(request["unit"])
        require(int(properties["MainPID"]) == request["main_pid"], "actual unit MainPID drift")
        actual_cgroup = proc_bytes(pid, "cgroup").decode().strip()
        require(actual_cgroup == "0::" + properties["ControlGroup"], "process not in actual owned cgroup")
        status = dict(line.split(":", 1) for line in proc_bytes(pid, "status").decode().splitlines() if ":" in line)
        caps = {key: status[key].strip() for key in ("CapEff", "CapBnd", "CapAmb")}
        for name, expected in (("Uid", request["renderer_uid"]), ("Gid", request["renderer_gid"])):
            integer(expected, "inspect renderer identity")
            require([int(item) for item in status[name].split()] == [expected] * 4, "actual renderer UID/GID differs from owner")
        exact(properties["User"], str(request["renderer_uid"]), "unit user mismatch")
        exact(properties["Group"], str(request["renderer_gid"]), "unit group mismatch")
        temporary = validate_temporary_directory(request["temporary_directory"], request["renderer_uid"])
        environment = proc_bytes(pid, "environ", 256 * 1024).split(b"\x00")
        require([value for value in environment if value.startswith(b"TMPDIR=")]
            == [b"TMPDIR=" + temporary["path"].encode()], "actual process TMPDIR differs from retained launch")
        del environment
        retained_temporary = _StagingPath.open(Path(temporary["path"]), directory=True)
        metadata = os.fstat(retained_temporary.fd)
        require(stat.S_ISDIR(metadata.st_mode) and {"path": temporary["path"], "device": metadata.st_dev,
            "inode": metadata.st_ino, "uid": metadata.st_uid, "mode": stat.S_IMODE(metadata.st_mode)} == temporary,
            "actual temporary directory differs from retained owner")
        arguments = proc_bytes(pid, "cmdline", 256 * 1024).split(b"\x00")
        content = arguments.count(b"--content-process") == 1
        del arguments  # The opaque content IPC token never leaves this process.
        exe = os.stat(f"/proc/{pid}/exe")
        binary = {"device": exe.st_dev, "inode": exe.st_ino}
        namespace = ns_inode(pid)
        names = sorted(int(name) for name in os.listdir(f"/proc/{pid}/fd"))
        require(0 < len(names) <= MAX_FDS, "actual FD inventory exceeds bound")
        libc = ctypes.CDLL(None, use_errno=True)
        require(os.uname().machine in {"x86_64", "aarch64"}, "pidfd_getfd syscall ABI unsupported")
        rows = []
        for fd in names:
            require(time.monotonic() < deadline, "actual host FD inventory expired")
            duplicate = libc.syscall(438, descriptor, fd, 0)
            if duplicate < 0:
                raise OSError(ctypes.get_errno(), "required actual pidfd_getfd failed")
            try:
                metadata = os.fstat(duplicate)
                named = os.stat(f"/proc/{pid}/fd/{fd}")
                require((metadata.st_dev, metadata.st_ino, metadata.st_mode) == (named.st_dev, named.st_ino, named.st_mode), "FD identity drift")
                domain = None
                if stat.S_ISSOCK(metadata.st_mode):
                    # socket.socket owns only this duplicate, not the unit FD.
                    with socket.socket(fileno=duplicate) as copied:
                        duplicate = -1
                        domain = copied.getsockopt(socket.SOL_SOCKET, socket.SO_DOMAIN)
                    kind = "socket"
                elif stat.S_ISFIFO(metadata.st_mode):
                    kind = "pipe"
                elif stat.S_ISCHR(metadata.st_mode):
                    kind = "character_device"
                else:
                    kind = "file"
                rows.append({"fd": fd, "device": metadata.st_dev, "inode": metadata.st_ino,
                             "kind": kind, "socket_domain": domain})
            finally:
                if duplicate >= 0:
                    os.close(duplicate)
        require(names == sorted(int(name) for name in os.listdir(f"/proc/{pid}/fd")), "stopped FD names drift")
        require(process_stat(pid) == before and ns_inode(pid) == namespace, "process changed during independent observation")
        current_temporary = _StagingPath.open(Path(temporary["path"]), directory=True)
        try:
            metadata = os.fstat(current_temporary.fd)
            require(current_temporary.identities() == retained_temporary.identities()
                and {"path": temporary["path"], "device": metadata.st_dev, "inode": metadata.st_ino,
                     "uid": metadata.st_uid, "mode": stat.S_IMODE(metadata.st_mode)} == temporary,
                "actual temporary directory changed during independent observation")
        finally:
            current_temporary.close()
        require(not select.select([descriptor], [], [], 0)[0] and time.monotonic() < deadline, "observation ended after exit/deadline")
        value = {"schema": "trillionnium.desktop.netns-host-observation.v1", "unit": request["unit"],
            "control_group": properties["ControlGroup"], "main_pid": request["main_pid"], "role": request["role"],
            "identity": before, "executable_identity": binary, "network_namespace_inode": namespace,
            "outside_network_namespace_inode": ns_inode(os.getpid()), "caps": caps,
            "no_new_privileges": int(status["NoNewPrivs"].strip()), "seccomp": int(status["Seccomp"].strip()),
            "unit_properties": {key: properties[key] for key in PROPERTIES}, "descriptor_inventory": rows,
            "renderer_uid": request["renderer_uid"], "renderer_gid": request["renderer_gid"], "read_write_paths": properties["ReadWritePaths"],
            "temporary_directory": temporary,
            "pidfd_retained": True, "entry_stopped": True, "content_argument_observed": content,
            "source_qualification_only": True, "installed_qualified": False, "production_ready": False}
        _validate_host(value, request["role"], request["binary_identity"], request["outside_namespace"], request["main_pid"],
                       standalone_negative=request["standalone_negative"], renderer_identity=(request["renderer_uid"], request["renderer_gid"]),
                       renderer_path=request["renderer_path"], temporary_directory=temporary)
        return value
    finally:
        try:
            if retained_temporary is not None:
                retained_temporary.close()
        finally:
            os.close(descriptor)


class Canary:
    """Outside actual dual-stack listener, bounded observed connections/data."""
    def __init__(self):
        self.stop = threading.Event()
        self.rows: list[dict] = []
        self.sockets: list[socket.socket] = []
        self.threads: list[threading.Thread] = []
        self.nonce = uuid.uuid4().hex
        try:
            for family, address in ((socket.AF_INET, "127.0.0.1"), (socket.AF_INET6, "::1")):
                listener = socket.socket(family, socket.SOCK_STREAM)
                self.sockets.append(listener)
                if family == socket.AF_INET6:
                    listener.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
                listener.bind((address, 0))
                listener.listen(8)
                listener.settimeout(0.1)
                thread = threading.Thread(target=self._listen, args=(listener, family), daemon=True)
                thread.start()
                self.threads.append(thread)
            self.positive("before")
        except BaseException:
            self.close()
            raise

    def _listen(self, listener: socket.socket, family: int) -> None:
        while not self.stop.is_set():
            try:
                connection, _ = listener.accept()
            except socket.timeout:
                continue
            except OSError:
                return
            with connection:
                connection.settimeout(0.5)
                try:
                    received = connection.recv(128)
                    self.rows.append({"family": int(family), "payload_hex": received.hex()})
                    connection.sendall(b"canary-ack")
                except OSError:
                    self.rows.append({"family": int(family), "payload_hex": ""})
            if len(self.rows) > 16:
                self.stop.set()

    def endpoints(self) -> dict:
        return {"ipv4": "127.0.0.1:" + str(self.sockets[0].getsockname()[1]),
                "ipv6": "[::1]:" + str(self.sockets[1].getsockname()[1])}

    def positive(self, phase: str) -> None:
        for listener in self.sockets:
            with socket.socket(listener.family, socket.SOCK_STREAM) as client:
                client.settimeout(1)
                client.connect(listener.getsockname())
                client.sendall((self.nonce + ":" + phase).encode())
                require(client.recv(32) == b"canary-ack", "outside canary actual payload not acknowledged")

    def finish(self) -> dict:
        try:
            self.positive("after")
        finally:
            self.close()
        expected = [{"family": int(family), "payload_hex": (self.nonce + ":" + phase).encode().hex()}
                    for phase in ("before", "after") for family in (socket.AF_INET, socket.AF_INET6)]
        require(self.rows == expected, "outside canary observed a non-control connection/payload")
        return {"schema": "trillionnium.desktop.netns-canary.v1", "nonce": self.nonce,
            "outside_network_namespace_inode": ns_inode(os.getpid()), "positive_controls": expected,
            "actual_connections": self.rows, "unexpected_connections": 0, "source_qualification_only": True,
            "installed_qualified": False, "production_ready": False}

    def close(self) -> None:
        self.stop.set()
        listeners, self.sockets = self.sockets, []
        threads, self.threads = self.threads, []
        errors = []
        for listener in listeners:
            try:
                listener.close()
            except BaseException as error:
                errors.append(error)
        for thread in threads:
            try:
                thread.join(timeout=1)
                require(not thread.is_alive(), "outside canary listener failed to retire")
            except BaseException as error:
                errors.append(error)
        if errors:
            raise ValueError("outside canary cleanup failed") from errors[0]


class Unit:
    """Exact private transient service, with retained handles for all entries."""
    def __init__(self, binary: Path, output: Path, environment: dict, *, content_negative: bool = False,
                 inherited: socket.socket | None = None):
        self.owner_pid = os.getpid()
        self.binary = binary.absolute()
        metadata = binary.stat()
        self.binary_identity = {"device": metadata.st_dev, "inode": metadata.st_ino}
        self.host_output = output
        self.output = output / "renderer"
        self.packet = Packet(self.output)
        self.unit = "hepta-netns-" + uuid.uuid4().hex + ".service"
        self.outside = ns_inode(os.getpid())
        self.stop = threading.Event()
        self._continuation_lock = threading.Lock()
        self.handles: dict[int, int] = {}
        self.observations: dict[str, dict] = {}
        self.error: BaseException | None = None
        self.main_pid = 0
        self.forwarder: subprocess.Popen | None = None
        self.thread: threading.Thread | None = None
        self.temporary = None
        self.temporary_identity = None
        self.log = (self.output / "runtime.log").open("xb")
        self.inherited_family = int(inherited.family) if inherited else None
        try:
            self.temporary = _PrivateTemporaryDirectory()
            self.temporary_identity = self.temporary.verify()
            require(not re.search(r"\s", str(self.output.absolute())), "renderer path contains unsupported whitespace")
            require("TMPDIR" not in environment, "ambient temporary directory is not approved")
            environment = {**environment, "TMPDIR": str(self.temporary.path)}
            args = ["sudo", "-n", "systemd-run", "--quiet", "--wait", "--pipe", "--unit", self.unit,
                "--property", f"User={os.getuid()}", "--property", f"Group={os.getgid()}",
                "--property", "PrivateNetwork=yes", "--property", "RestrictAddressFamilies=AF_UNIX",
                "--property", "RestrictNamespaces=yes", "--property", "SystemCallArchitectures=native",
                "--property", "CapabilityBoundingSet=", "--property", "AmbientCapabilities=",
                "--property", "NoNewPrivileges=yes", "--property", "KillMode=control-group",
                "--property", "ProtectSystem=strict", "--property", "ProtectHome=read-only",
                "--property", "PrivateTmp=no",
                "--property", "ReadWritePaths=" + str(self.output.absolute()) + " " + str(self.temporary.path),
                "--property", "RuntimeMaxSec=180", "--property", "TimeoutStopSec=5",
                "--property", "RemainAfterExit=yes",
                "--property", "LimitFSIZE=16777216", "--property", "UMask=0077",
                "--property", f"WorkingDirectory={ROOT}"]
            for key, value in environment.items():
                require(re.fullmatch(r"[A-Z_][A-Z_0-9]*", key) is not None and "\n" not in value and "\x00" not in value,
                        "unit environment invalid")
                args += ["--setenv", key + "=" + value]
            args += ["--", str(binary)]
            if content_negative:
                args += ["--content-process", "qualification-invalid-token-never-consumed"]
            self.forwarder = subprocess.Popen(args, stdin=inherited if inherited else subprocess.DEVNULL,
                stdout=self.log, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 8
            while not self.main_pid:
                require(self.forwarder.poll() is None and time.monotonic() < deadline, "transient native service did not start")
                properties = unit_properties(self.unit)
                self.main_pid = int(properties["MainPID"])
                if not self.main_pid:
                    time.sleep(0.02)
            self.thread = threading.Thread(target=self._observe, daemon=True)
            self.temporary.verify()
            self.thread.start()
        except BaseException:
            self.close()
            raise

    def _check_owner(self) -> None:
        require(os.getpid() == self.owner_pid, "unit owner inherited across fork")
        if self.error is not None:
            raise ValueError("independent namespace observation failed") from self.error

    def _observe(self) -> None:
        try:
            while not self.stop.is_set():
                self._check_owner()
                names = sorted(path.name for path in self.output.iterdir()
                    if re.fullmatch(r"namespace-(entry|refusal)-[1-9][0-9]*-[1-9][0-9]*\.json", path.name))
                require(len(names) <= 3, "namespace entry bound exceeded")
                for name in names:
                    if name in self.observations:
                        continue
                    entry = self.packet.json(name)
                    require(type(entry) is dict, "namespace entry is not object")
                    pid, started = integer(entry.get("pid"), "namespace entry PID", 2), integer(entry.get("start_time"), "namespace entry start")
                    require(name == f"namespace-{'refusal' if self.inherited_family else 'entry'}-{pid}-{started}.json", "namespace entry name drift")
                    require(pid not in self.handles, "namespace process was observed twice")
                    descriptor = os.pidfd_open(pid)
                    self.handles[pid] = descriptor
                    deadline = time.monotonic() + 2
                    while process_stat(pid)["state"] != "T":
                        require(not select.select([descriptor], [], [], 0)[0] and time.monotonic() < deadline,
                                "entry did not reach actual host stop")
                        time.sleep(0.005)
                    request = {"unit": self.unit, "pid": pid, "start_time": started, "main_pid": self.main_pid,
                        "role": entry.get("role"), "binary_identity": self.binary_identity, "outside_namespace": self.outside,
                        "standalone_negative": self.inherited_family is not None, "renderer_uid": os.getuid(), "renderer_gid": os.getgid(),
                        "renderer_path": str(self.output.absolute()), "temporary_directory": self.temporary.verify()}
                    result = subprocess.run(["sudo", "-n", "python3", str(Path(__file__).absolute()), "inspect"],
                        input=json.dumps(request), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5, check=True)
                    require(len(result.stdout.encode()) <= MAX_BYTES and len(result.stderr.encode()) <= MAX_BYTES,
                            "inspector output exceeded bound")
                    host = load_json_strict(result.stdout)
                    validate_binding(entry, host, self.binary_identity, self.outside, self.main_pid,
                                     inherited_family=self.inherited_family, renderer_identity=(os.getuid(), os.getgid()),
                                     renderer_path=str(self.output.absolute()), temporary_directory=self.temporary.verify())
                    require(process_stat(pid) == host["identity"] and not select.select([descriptor], [], [], 0)[0],
                            "stopped owner changed before exact pidfd continuation")
                    self.packet.read(name)
                    host_name = "host-" + name
                    write_json(self.host_output / host_name, host)
                    self.observations[name] = {"entry": name, "host": host_name, "pid": pid, "start_time": started, "role": entry["role"]}
                    with self._continuation_lock:
                        self._check_owner()
                        require(not self.stop.is_set(), "unit retired before exact continuation")
                        signal.pidfd_send_signal(descriptor, signal.SIGCONT)
                self.stop.wait(0.01)
        except BaseException as error:
            self.error = error

    def wait_for(self, predicate, seconds: float):
        deadline = time.monotonic() + seconds
        while True:
            self._check_owner()
            value = predicate()
            if value:
                return value
            require(self.forwarder is not None and self.forwarder.poll() is None, "actual namespace service exited before readiness")
            require(time.monotonic() < deadline, "bounded namespace readiness expired")
            time.sleep(0.02)

    def wait_exit(self, seconds: float) -> int:
        deadline = time.monotonic() + seconds
        while True:
            self._check_owner()
            require(self.forwarder is not None, "namespace service was not launched")
            props = unit_properties(self.unit)
            if props["MainPID"] == "0":
                require(props["ExecMainCode"] == "1", "native must exit normally rather than timeout/signal")
                status = int(props["ExecMainStatus"])
                return status
            require(time.monotonic() < deadline, "bounded namespace service exit expired")
            time.sleep(0.02)

    def close(self) -> None:
        require(os.getpid() == self.owner_pid, "inherited child may not stop parent's unit")
        with self._continuation_lock:
            self.stop.set()
        errors = []
        # Only this unguessable unit name is stopped; no numeric process group
        # or unrelated descendant is ever used as cleanup authority.
        try:
            command(["sudo", "-n", "systemctl", "stop", self.unit], timeout=8)
        except BaseException as error:
            errors.append(error)
        if self.thread is not None:
            try:
                self.thread.join(timeout=8)
            except BaseException as error:
                errors.append(error)
        observer_retired = self.thread is None or not self.thread.is_alive()
        if not observer_retired:
            errors.append(ValueError("namespace observation thread failed to retire"))
        try:
            if self.forwarder is not None:
                self.forwarder.wait(timeout=5)
            inactive = subprocess.run(["sudo", "-n", "systemctl", "is-active", self.unit],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
            require(inactive.returncode in {3, 4} and inactive.stdout.strip() in {"inactive", "failed", "unknown"},
                    "owned unit remains active")
        except BaseException as error:
            errors.append(error)
        # The observer alone inserts/uses handles. A failed join must not close
        # a descriptor that the still-live observer could use after FD reuse.
        handles = {}
        if observer_retired:
            handles, self.handles = self.handles, {}
        for descriptor in handles.values():
            try:
                require(bool(select.select([descriptor], [], [], 0)[0]), "retained namespace process survives unit stop")
            except BaseException as error:
                errors.append(error)
            finally:
                try:
                    os.close(descriptor)
                except BaseException as error:
                    errors.append(error)
        try:
            self.log.close()
            subprocess.run(["sudo", "-n", "systemctl", "reset-failed", self.unit], stdout=subprocess.PIPE,
                           stderr=subprocess.PIPE, timeout=5, check=False)
        except BaseException as error:
            errors.append(error)
        temporary = getattr(self, "temporary", None)
        if temporary is not None:
            try:
                temporary.close(remove=not errors)
            except BaseException as error:
                errors.append(error)
            self.temporary = None
        if errors:
            raise ValueError("namespace cleanup did not confirm exact process exit") from errors[0]


def _retire_case(unit, helper, xvfb, helpers: dict, inherited, canary: Canary, output: Path) -> None:
    """Attempt every owned cleanup; an error never yields a success receipt."""
    errors = []
    actions = []
    if unit is not None:
        actions.append(unit.close)
    actions.extend(lambda child=child: helpers["cleanup"](child) for child in (helper, xvfb))
    if inherited is not None:
        actions.append(inherited.close)
    for action in actions:
        try:
            action()
        except BaseException as error:
            errors.append(error)
    try:
        write_json(output / "outside-canary.json", canary.finish())
    except BaseException as error:
        errors.append(error)
    if errors:
        raise ValueError("namespace case cleanup failed") from errors[0]


def load_native_helpers(mode: str) -> dict:
    """Only function definitions from this tested source; no shell-body effects."""
    source = (ROOT / "tools/run_servo_headed_runtime_gate.sh").read_text()
    marker = "step_run_native_burst_v1() {" if mode == "burst" else "step_run_held_gestures_v1() {"
    body = source.split(marker, 1)[1].split("python3 - <<'PY'", 1)[1].split("\nPY\n", 1)[0]
    tree = ast.parse(body)
    wanted = {"command", "pointer", "unique_window", "process_stat", "members", "spawn", "anchored_identity",
              "observe_exit", "cleanup", "wait_for"}
    if mode == "burst":
        wanted.add("verify_queue")
    else:
        wanted.add("verify_case")
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in wanted]
    require({node.name for node in functions} == wanted, "native helper inventory changed")
    namespace = {"require": require, "Path": Path, "ctypes": ctypes, "subprocess": subprocess,
        "os": os, "signal": signal, "time": time, "re": re,
        "failure": "native held gesture withdrawn; fresh Servo owner recovery is required"}
    exec(compile(ast.Module(body=functions, type_ignores=[]), str(ROOT / "tools/run_servo_headed_runtime_gate.sh"), "exec"), namespace)
    return namespace


def validate_canary(value: object, outside: int) -> None:
    value = closed(value, {"schema", "nonce", "outside_network_namespace_inode", "positive_controls",
        "actual_connections", "unexpected_connections", "source_qualification_only", "installed_qualified", "production_ready"}, "canary fields")
    exact(value["schema"], "trillionnium.desktop.netns-canary.v1", "canary schema")
    exact(value["outside_network_namespace_inode"], outside, "canary namespace")
    require(type(value["nonce"]) is str and re.fullmatch(r"[a-f0-9]{32}", value["nonce"]), "canary nonce")
    expected = [{"family": int(family), "payload_hex": (value["nonce"] + ":" + phase).encode().hex()}
        for phase in ("before", "after") for family in (socket.AF_INET, socket.AF_INET6)]
    for key in ("positive_controls", "actual_connections"):
        rows = value[key]
        require(type(rows) is list and len(rows) == 4, "canary missing dual-stack before/after positives")
        for row, required in zip(rows, expected):
            closed(row, {"family", "payload_hex"}, "canary event fields")
            exact(row["family"], required["family"], "canary family")
            exact(row["payload_hex"], required["payload_hex"], "unexpected outside canary payload")
    for key, required in (("unexpected_connections", 0), ("source_qualification_only", True),
                          ("installed_qualified", False), ("production_ready", False)):
        exact(value[key], required, "canary ceiling")


def validate_runtime(packet: Packet, native: dict) -> dict:
    """DOM and exact ACK remain independent; namespace cannot replace either."""
    report = packet.json("runtime-result.json")
    require(type(report) is dict, "namespace actual runtime absent")
    exact(report["schema"], "trillionnium.desktop.d0a02-headed-runtime.v1", "runtime schema")
    exact(report["status"], "PASS_HEADED_LOCAL_FIXTURE_ONLY", "runtime status")
    exact(report["servo_commit"], PIN, "runtime pin")
    for key in ("window_created", "trusted_chrome_separate_from_content", "chrome_initial_pixels_verified",
        "chrome_crash_pixels_verified", "chrome_recovery_pixels_verified", "content_crash_observed", "trusted_window_survived_content_crash"):
        exact(report[key], True, "runtime mandatory gate " + key)
    for key, required in (("logical_content_webview_peak", 1), ("initial_generation", 1), ("recovery_generation", 2),
                          ("native_button_events", 6), ("synthetic_ime_composition_events", 3)):
        exact(report[key], required, "runtime integer gate " + key)
    for key, minimum in (("native_pointer_events", 1), ("native_wheel_events", 1), ("native_keyboard_events", 2),
        ("native_ime_events", 1), ("input_handled_callbacks", 12), ("input_method_controls", 1),
        ("popup_requests_denied", 1), ("external_navigation_requests_denied", 1)):
        integer(report[key], "runtime count " + key, minimum)
    initial, recovery = report["initial_page_evidence"], report["recovery_page_evidence"]
    for page, generation in ((initial, 1), (recovery, 2)):
        require(type(page) is dict, "runtime DOM absent")
        exact(page["generation"], generation, "actual DOM generation")
        exact(page["loaded"], True, "actual DOM load")
    exact(initial["pointerDowns"], 3, "actual DOM original three Down")
    exact(initial["documentClickEvents"], 3, "actual DOM original three click EVENTS")
    for key in ("clicks", "wheels", "pointerMoves"):
        integer(initial[key], "actual DOM count " + key)
    exact(initial["inputEventOrderOverflow"], False, "actual DOM overflow")
    order = initial["inputEventOrder"]
    require(type(order) is list and len(order) == 9, "actual DOM event order length")
    for index, row in enumerate(order):
        closed(row, {"sequence", "type", "button", "x", "y"}, "actual DOM event fields")
        expected = {"sequence": index + 1, "type": ["pointerdown", "pointerup", "click"][index % 3],
            "button": 0, "x": [200, 400, 200][index // 3], "y": [68, 100, 68][index // 3]}
        for key in expected:
            exact(row[key], expected[key], "actual DOM event type/value " + key)
    require(type(initial["keyDowns"]) is list and all(type(item) is str for item in initial["keyDowns"])
        and "k" in [item.lower() for item in initial["keyDowns"]]
        and "x" not in [item.lower() for item in initial["keyDowns"]], "actual native key/chrome gate")
    exact(initial["popupAttempted"], True, "actual popup probe")
    exact(initial["externalNavigationAttempted"], True, "actual navigation probe")
    authority = {"fixture_listener_loopback_only": False, "external_navigation_performed": False,
        "webdriver_listener_started": False, "browser_actor_started": False, "agent_port_enabled": False,
        "persistent_credentials_used": False, "product_ready": False}
    closed(report["authority"], set(authority), "namespace runtime ceiling fields")
    for key, required in authority.items():
        exact(report["authority"][key], required, "namespace runtime ceiling")
    fault = report["fault_injection"]
    require(type(fault) is dict, "runtime fault absent")
    exact(fault["mechanism"], "requested_SIGKILL", "fault mechanism")
    exact(fault["generation"], 1, "fault generation")
    integer(fault["pid"], "fault PID", 2)
    integer(fault["start_time"], "fault start")
    exact(fault["exact_termination_observed"], True, "fault termination")
    selected = {"generation": 1, "pid": fault["pid"], "start_time": fault["start_time"]}
    for name, expected in (("content-process-identity.json", selected), ("content-sigkill-sent.json", {**selected, "signal": "SIGKILL"})):
        receipt = closed(packet.json(name), set(expected), "actual fault receipt fields")
        for key, required in expected.items():
            exact(receipt[key], required, "actual fault receipt type/value")
    helper = load_native_helpers("burst")
    queue = helper["verify_queue"](packet.json("native-input-queue.json"), native)
    counts = queue["accepted_event_counts"]
    exact(report["input_handled_callbacks"], queue["total_matching_engine_acks"], "actual total ACK binding")
    for key, required in (("native_pointer_events", counts["move"]), ("native_button_events", counts["down"] + counts["up"]),
        ("native_keyboard_events", counts["key"]), ("native_wheel_events", counts["wheel"])):
        exact(report[key], required, "actual counter/ACK binding")
    exact(packet.read("fixture-origin.txt").decode().strip(), ORIGIN, "immutable fixture origin")
    validate_resource(packet.json("resource-gate-result.json"), report, ORIGIN, namespace_immutable_qualification=True)
    for name in ("content-generation-1.png", "content-generation-2.png", "workspace-generation-1.png",
        "workspace-crash-placeholder.png", "workspace-generation-2.png"):
        require(packet.read(name, 16 * 1024 * 1024).startswith(b"\x89PNG\r\n\x1a\n"), "actual native screenshot absent")
    return {"selected_fault_identity": selected, "matching_native_button_ids": queue["accepted_native_button_event_ids"],
        "actual_dom_downs": 3, "actual_dom_document_click_events": 3, "actual_dom_order": order}


def verify_packet(directory: Path, case: str) -> dict:
    host_packet = Packet(directory)
    packet = Packet(directory / "renderer")
    launch = closed(host_packet.json("namespace-launch.json"), LAUNCH_KEYS, "launch fields")
    exact(launch["schema"], "trillionnium.desktop.netns-launch.v1", "launch schema")
    exact(launch["case"], case, "launch case")
    main_pid = integer(launch["main_pid"], "launch MainPID", 2)
    outside = integer(launch["outside_namespace"], "launch outside namespace")
    renderer_identity = (integer(launch["renderer_uid"], "launch renderer UID"), integer(launch["renderer_gid"], "launch renderer GID"))
    require(type(launch["renderer_path"]) is str and launch["renderer_path"].endswith("/" + case + "/renderer"), "launch renderer path")
    temporary = validate_temporary_directory(launch["temporary_directory"], renderer_identity[0])
    exact(launch["temporary_directory_removed"], True, "temporary directory was not retired after the unit")
    binary = closed(launch["binary_identity"], {"device", "inode"}, "launch binary fields")
    integer(binary["device"], "launch binary device", 0)
    integer(binary["inode"], "launch binary inode")
    require(type(launch["binary_sha256"]) is str and re.fullmatch(r"[a-f0-9]{64}", launch["binary_sha256"]), "launch binary digest")
    for key, required in (("owned_unit_stopped", True), ("exact_processes_exited", True), ("qualification_nonce_enabled", False),
                          ("per_pair_ack_pacing", False), ("source_qualification_only", True), ("installed_qualified", False), ("production_ready", False)):
        exact(launch[key], required, "launch closure/ceiling")
    inherited = None
    if case.startswith("inherited-"):
        require(case in {"inherited-embedder-ipv4", "inherited-embedder-ipv6", "inherited-content-ipv4", "inherited-content-ipv6"}, "unknown inherited negative")
        inherited = int(socket.AF_INET6 if case.endswith("ipv6") else socket.AF_INET)
    else:
        require(case in {"burst", "chrome", "window-leave", "focus-loss", "kernel-fixture"}, "unknown namespace case")
    entries = launch["entries"]
    expected_length = 3 if case == "burst" else 1 if inherited or case == "kernel-fixture" else 2
    require(type(entries) is list and len(entries) == expected_length, "missing/unexpected native/content entries")
    actual_entry_names = {path.name for path in packet.root.iterdir() if path.name.startswith(("namespace-entry-", "namespace-refusal-"))}
    require(actual_entry_names == {item.get("entry") for item in entries if type(item) is dict}, "entry inventory drift/unknown generation")
    observed = []
    for summary in entries:
        summary = closed(summary, {"entry", "host", "pid", "start_time", "role"}, "entry summary fields")
        entry = packet.json(summary["entry"])
        host = host_packet.json(summary["host"])
        exact(summary["host"], "host-" + summary["entry"], "host file binding")
        validate_binding(entry, host, binary, outside, main_pid, inherited_family=inherited,
                         renderer_identity=renderer_identity, renderer_path=launch["renderer_path"], temporary_directory=temporary)
        exact(host["unit"], launch["unit"], "entry changed actual unit")
        for key in ("pid", "start_time", "role"):
            exact(summary[key], entry[key], "summary differs from actual entry")
        prefix = "refusal" if inherited is not None else "entry"
        exact(summary["entry"], f"namespace-{prefix}-{entry['pid']}-{entry['start_time']}.json", "entry canonical name")
        observed.append((entry, host))
    require(len({entry["pid"] for entry, _ in observed}) == len(entries), "reused namespace process PID")
    require(len({entry["network_namespace_inode"] for entry, _ in observed}) == 1, "content escaped the native network namespace")
    validate_canary(host_packet.json("outside-canary.json"), outside)
    if inherited is not None:
        exact(launch["exit_code"], 1, "inherited negative must exit 1")
        exact(observed[0][0]["role"], "content" if "content" in case else "embedder", "negative entry role")
        require(not (packet.root / "runtime-result.json").exists() and not (packet.root / "input-ready").exists(), "inherited negative entered Servo/runtime")
        detail = {"inherited_socket_domain": inherited, "engine_started": False}
    elif case == "kernel-fixture":
        exact(launch["exit_code"], 0, "kernel fixture exit")
        exact(observed[0][0]["role"], "embedder", "kernel fixture role")
        require(not (packet.root / "runtime-result.json").exists(), "kernel fixture is not Servo evidence")
        detail = {"actual_servo_executed": False}
    else:
        exact(observed[0][0]["role"], "embedder", "first entry must actual native")
        require(all(entry["role"] == "content" for entry, _ in observed[1:]), "following entries are not actual content")
        owner = observed[0][1]["identity"]
        for _, host in observed[1:]:
            exact(host["identity"]["pgid"], owner["pgid"], "content process group differs")
            exact(host["identity"]["session"], owner["session"], "content process session differs")
        if case == "burst":
            exact(launch["exit_code"], 0, "actual namespace burst exit")
            detail = validate_runtime(packet, owner)
            selected = detail["selected_fault_identity"]
            require(any(entry["pid"] == selected["pid"] and entry["start_time"] == selected["start_time"] for entry, _ in observed[1:]),
                    "requested fault lacks actual entry/retained host incarnation")
        else:
            helpers = load_native_helpers("held")
            helpers["read_json"] = lambda path: packet.json(path.name)
            detail = helpers["verify_case"](packet.root, case, launch["exit_code"])
    packet.read("runtime.log", 16 * 1024 * 1024)
    if case in {"burst", "chrome", "window-leave", "focus-loss"}:
        stimulus = host_packet.json("namespace-stimulus.json")
        if case == "burst":
            closed(stimulus, {"case", "argv", "requested_button_pairs", "extra_button_pairs", "per_pair_ack_pacing", "qualification_nonce_enabled"}, "burst stimulus fields")
            exact(stimulus["requested_button_pairs"], 3, "burst exact requested original pairs")
            exact(stimulus["extra_button_pairs"], 0, "burst no extra pairs")
            exact(stimulus["per_pair_ack_pacing"], False, "burst no ACK pacing")
            args = stimulus["argv"]
            require(type(args) is list and len(args) == 39 and all(type(item) is str for item in args), "burst exact original stimulus shape")
            window = args[4]
            require(re.fullmatch(r"[1-9][0-9]*", window) is not None, "actual native stimulus window")
            exact_tree(args, ["xdotool", "mousemove", "--sync", "--window", window, "200", "132", "mousedown", "1", "mouseup", "1",
                "mousemove", "--sync", "--window", window, "400", "164", "mousedown", "1", "mouseup", "1",
                "mousemove", "--sync", "--window", window, "200", "132", "mousedown", "1", "mouseup", "1",
                "key", "--delay", "0", "k", "click", "--delay", "0", "5"], "burst original three pairs changed")
        else:
            closed(stimulus, {"case", "withdrawal_argv", "native_button_down_count", "synthetic_mouse_up_injected", "qualification_nonce_enabled"}, "held stimulus fields")
            exact(stimulus["native_button_down_count"], 1, "held original Down")
            exact(stimulus["synthetic_mouse_up_injected"], False, "held synthetic Up")
            require(type(stimulus["withdrawal_argv"]) is list and all(type(item) is str for item in stimulus["withdrawal_argv"])
                and "mouseup" not in stimulus["withdrawal_argv"], "held withdrawal added Up")
        exact(stimulus["case"], case, "stimulus case")
        exact(stimulus["qualification_nonce_enabled"], False, "namespace default input profile")
    return {"schema": "trillionnium.desktop.netns-case-verification.v1", "case": case, "detail": detail,
        "raw_sha256": {**host_packet.finish(), **{"renderer/" + name: digest for name, digest in packet.finish().items()}},
        "source_qualification_only": True, "installed_qualified": False, "production_ready": False}


def run_case(binary: Path, output: Path, case: str) -> dict:
    import traceback
    output.mkdir(mode=0o700)
    os.chmod(output, 0o700)
    runtime_output = output / "renderer"
    runtime_output.mkdir(mode=0o700)
    binary_hash = hash_regular(binary)
    before = binary.stat()
    binary_identity = {"device": before.st_dev, "inode": before.st_ino}
    (runtime_output / "home").mkdir(mode=0o700)
    inherited = None
    unit = None
    xvfb = helper = None
    helpers = load_native_helpers("burst" if case == "burst" else "held")
    canary = Canary()
    try:
        with ExitStack() as stack:
            environment = {"HEPTA_D0A02_OUTPUT": str(runtime_output.absolute()), "HEPTA_D0A02_NETNS_PROFILE": PROFILE,
                "HEPTA_NETNS_CANARY_IPV4": canary.endpoints()["ipv4"], "HEPTA_NETNS_CANARY_IPV6": canary.endpoints()["ipv6"],
                "HOME": str((runtime_output / "home").absolute()), "PATH": "/usr/bin:/bin", "RUST_BACKTRACE": "1"}
            negative = case.startswith("inherited-")
            if negative:
                family = socket.AF_INET6 if case.endswith("ipv6") else socket.AF_INET
                inherited = socket.socket(family, socket.SOCK_STREAM)
            elif case != "kernel-fixture":
                display_file = stack.enter_context((output / "display-number").open("x"))
                display_log = stack.enter_context((output / "xvfb.log").open("x"))
                xvfb, _ = helpers["spawn"](["Xvfb", "-displayfd", str(display_file.fileno()), "-screen", "0", "1280x900x24", "-nolisten", "tcp"],
                    dict(os.environ), display_log, pass_fds=(display_file.fileno(),))
                number = helpers["wait_for"](lambda: (output / "display-number").read_text().strip(), 10, xvfb)
                require(re.fullmatch(r"[0-9]+", number) is not None, "actual Xvfb display invalid")
                environment["DISPLAY"] = ":" + number
            unit = Unit(binary, output, environment, content_negative="content" in case, inherited=inherited)
            require(unit.binary_identity == binary_identity, "binary changed before actual service launch")
            if not negative and case != "kernel-fixture":
                unit.wait_for(lambda: (runtime_output / "input-ready").is_file(), 60)
                actual_env = dict(os.environ, DISPLAY=environment["DISPLAY"])
                actual_env.pop("WAYLAND_DISPLAY", None)
                window = unit.wait_for(lambda: helpers["unique_window"](actual_env, "TrillionniumOS Desktop.*D0A-02", unit.main_pid), 10)
                command(["xdotool", "windowfocus", "--sync", str(window)], environment=actual_env)
                require(command(["xdotool", "getwindowfocus"], environment=actual_env) == str(window), "namespace native actual focus")
                require(helpers["pointer"](actual_env)["button_mask"] == 0, "fresh namespace X11 server holds a button")
                if case == "burst":
                    args = ["xdotool", "mousemove", "--sync", "--window", str(window), "200", "132", "mousedown", "1", "mouseup", "1",
                        "mousemove", "--sync", "--window", str(window), "400", "164", "mousedown", "1", "mouseup", "1",
                        "mousemove", "--sync", "--window", str(window), "200", "132", "mousedown", "1", "mouseup", "1",
                        "key", "--delay", "0", "k", "click", "--delay", "0", "5"]
                    write_json(output / "namespace-stimulus.json", {"case": case, "argv": args, "requested_button_pairs": 3,
                        "extra_button_pairs": 0, "per_pair_ack_pacing": False, "qualification_nonce_enabled": False})
                    command(args, environment=actual_env, timeout=10)
                    require(helpers["pointer"](actual_env)["button_mask"] == 0, "actual namespace original pairs did not release")
                else:
                    helper_window = None
                    if case == "focus-loss":
                        title = "HEPTA namespace focus withdrawal " + uuid.uuid4().hex
                        log = stack.enter_context((output / "focus-helper.log").open("x"))
                        helper, _ = helpers["spawn"](["xmessage", "-title", title, "-geometry", "120x50+1100+10", "-buttons", "Close:0", "Native focus withdrawal"], actual_env, log)
                        helper_window = helpers["wait_for"](lambda: helpers["unique_window"](actual_env, "^" + title + "$"), 10, helper)
                    command(["xdotool", "mousemove", "--sync", "--window", str(window), "200", "132"], environment=actual_env)
                    time.sleep(0.2)
                    command(["xdotool", "mousedown", "1"], environment=actual_env)
                    time.sleep(0.2)
                    require(helpers["pointer"](actual_env)["button_mask"] == 0x100, "namespace actual held Down absent")
                    if case == "chrome":
                        args = ["xdotool", "mousemove", "--sync", "--window", str(window), "10", "10"]
                    elif case == "window-leave":
                        geometry = dict(line.split("=", 1) for line in command(["xdotool", "getwindowgeometry", "--shell", str(window)], environment=actual_env).splitlines())
                        x, y, width = (int(geometry[key]) for key in ("X", "Y", "WIDTH"))
                        outside_x = x + width + 20 if x + width + 20 < 1280 else x - 20
                        require(0 <= outside_x < 1280 and 0 <= y + 132 < 900, "namespace outside coordinate invalid")
                        args = ["xdotool", "mousemove", "--sync", str(outside_x), str(y + 132)]
                    else:
                        args = ["xdotool", "windowfocus", "--sync", str(helper_window)]
                    command(args, environment=actual_env)
                    require(helpers["pointer"](actual_env)["button_mask"] == 0x100, "namespace withdrawal invented physical Up")
                    write_json(output / "namespace-stimulus.json", {"case": case, "withdrawal_argv": args,
                        "native_button_down_count": 1, "synthetic_mouse_up_injected": False, "qualification_nonce_enabled": False})
            exit_code = unit.wait_exit(150 if case == "burst" else 30)
            unit.close()
            launch = {"schema": "trillionnium.desktop.netns-launch.v1", "case": case, "unit": unit.unit,
                "main_pid": unit.main_pid, "binary_identity": binary_identity, "binary_sha256": binary_hash,
                "outside_namespace": unit.outside, "entries": list(unit.observations.values()), "exit_code": exit_code,
                "renderer_uid": os.getuid(), "renderer_gid": os.getgid(), "renderer_path": str(runtime_output.absolute()),
                "temporary_directory": unit.temporary_identity, "temporary_directory_removed": True,
                "owned_unit_stopped": True, "exact_processes_exited": True, "qualification_nonce_enabled": False,
                "per_pair_ack_pacing": False, "source_qualification_only": True, "installed_qualified": False, "production_ready": False}
            unit = None
            after = binary.stat()
            require((before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
                    and binary_hash == hash_regular(binary), "binary changed during namespace case")
            write_json(output / "namespace-launch.json", launch)
    except BaseException:
        write_json(output / "harness-failure.json", {"status": "FAIL", "diagnostic": traceback.format_exc()[-16384:],
            "source_qualification_only": True, "installed_qualified": False, "production_ready": False})
        raise
    finally:
        _retire_case(unit, helper, xvfb, helpers, inherited, canary, output)
    result = verify_packet(output, case)
    write_json(output / "namespace-verification.json", result)
    return result


def source_binding(binary: Path) -> dict:
    identity = {key.lower(): os.environ[key] for key in ("BASE_SHA", "CANDIDATE_HEAD_SHA", "TESTED_SHA", "TESTED_TREE_SHA",
        "EVIDENCE_MODE", "GITHUB_REPOSITORY", "GITHUB_EVENT_NAME")}
    require(identity["tested_sha"] == command(["git", "rev-parse", "HEAD"])
        and identity["tested_tree_sha"] == command(["git", "rev-parse", "HEAD^{tree}"]), "namespace source checkout drift")
    require(identity["github_repository"].lower() == "trillionniumfoundation/trillionnium-os-desktop", "namespace source repository")
    command(["git", "diff", "--exit-code", "HEAD", "--", *SOURCE_PATHS])
    for name in SOURCE_PATHS:
        exact(command(["git", "hash-object", "--", name]), command(["git", "rev-parse", "HEAD:" + name]),
              "namespace input is not the tested Git blob")
    compiled = {name: hash_regular(ROOT / "servo-source/ports/servoshell/examples" / name, MAX_BYTES) for name in COMPILED_PATHS}
    exact(compiled["trillionnium_headed_runtime.rs"], os.environ["FORMATTED_OVERLAY_SHA256"], "namespace actual formatted overlay")
    return {"evidence_identity": identity, "source_sha256": {name: hash_regular(ROOT / name, MAX_BYTES) for name in SOURCE_PATHS},
        "compiled_overlay_sha256": compiled, "compiled_native_binary_sha256": hash_regular(binary)}


def verify_corpus(output: Path) -> dict:
    packet = Packet(output)
    value = closed(packet.json("namespace-corpus.json"), {"schema", "status", "actual_servo_executed", "cases", "source_binding",
        "source_qualification_only", "host_unix_proxy_confinement", "approved_unix_peer_policy", "installed_all_protocol_confinement",
        "late_scm_rights_authority_qualified", "lifetime_socket_authority_qualified",
        "installed_qualified", "production_ready"}, "corpus fields")
    exact(value["schema"], "trillionnium.desktop.netns-corpus.v1", "corpus schema")
    require(type(value["actual_servo_executed"]) is bool, "corpus actual engine type")
    actual_servo = value["actual_servo_executed"]
    expected_status = "PASS_EXPLICIT_NATIVE_DIRECT_INET_QUALIFICATION_ONLY" if actual_servo else "PASS_HOST_KERNEL_FIXTURE_ONLY"
    exact(value["status"], expected_status, "corpus status")
    for key, expected in (("source_qualification_only", True), ("host_unix_proxy_confinement", False), ("approved_unix_peer_policy", False),
        ("late_scm_rights_authority_qualified", False), ("lifetime_socket_authority_qualified", False),
        ("installed_all_protocol_confinement", False), ("installed_qualified", False), ("production_ready", False)):
        exact(value[key], expected, "corpus claim ceiling")
    cases = ["burst", "chrome", "window-leave", "focus-loss"] if actual_servo else ["kernel-fixture"]
    cases += [f"inherited-{role}-ipv{version}" for role in ("embedder", "content") for version in (4, 6)]
    require(type(value["cases"]) is list and len(value["cases"]) == len(cases), "corpus case set")
    observed = []
    binaries = set()
    units, incarnations, temporary_paths = set(), set(), set()
    for case, recorded in zip(cases, value["cases"]):
        observed_case = verify_packet(output / case, case)
        exact_tree(recorded, observed_case, "corpus case differs from complete raw facts")
        observed.append(observed_case)
        launch = Packet(output / case).json("namespace-launch.json")
        require(launch["unit"] not in units and (launch["main_pid"], launch["entries"][0]["start_time"]) not in incarnations,
                "corpus reused a unit or original process incarnation")
        units.add(launch["unit"])
        require(launch["temporary_directory"]["path"] not in temporary_paths, "corpus reused a private temporary directory")
        temporary_paths.add(launch["temporary_directory"]["path"])
        incarnations.add((launch["main_pid"], launch["entries"][0]["start_time"]))
        binaries.add(launch["binary_sha256"])
    require(len(binaries) == 1, "corpus changed compiled binary between cases")
    if actual_servo:
        binding = closed(value["source_binding"], {"evidence_identity", "source_sha256", "compiled_overlay_sha256", "compiled_native_binary_sha256"}, "source binding fields")
        exact(binding["compiled_native_binary_sha256"], next(iter(binaries)), "corpus binary differs from actual compiled source binding")
        for name, keys in (("source_sha256", set(SOURCE_PATHS)), ("compiled_overlay_sha256", set(COMPILED_PATHS))):
            closed(binding[name], keys, "source digest path inventory")
            require(all(type(item) is str and re.fullmatch(r"[a-f0-9]{64}", item) for item in binding[name].values()), "source digest type")
        identity = closed(binding["evidence_identity"], {"base_sha", "candidate_head_sha", "tested_sha", "tested_tree_sha", "evidence_mode", "github_repository", "github_event_name"}, "source identity fields")
        for key in ("base_sha", "candidate_head_sha", "tested_sha", "tested_tree_sha"):
            require(type(identity[key]) is str and re.fullmatch(r"[a-f0-9]{40}", identity[key]), "source object identity")
        require(identity["github_event_name"] in {"push", "pull_request", "workflow_dispatch"}
            and identity["evidence_mode"] in {"candidate_branch_push", "pr_synthetic_merge", "exact_main_push", "manual_exact_object"}, "source event lane")
        require(type(identity["github_repository"]) is str
            and identity["github_repository"].lower() == "trillionniumfoundation/trillionnium-os-desktop", "source repository")
        if identity["github_event_name"] == "pull_request":
            exact(identity["evidence_mode"], "pr_synthetic_merge", "source PR mode")
        else:
            require(identity["tested_sha"] == identity["candidate_head_sha"], "source exact-head identity")
            if identity["github_event_name"] == "workflow_dispatch":
                exact(identity["evidence_mode"], "manual_exact_object", "source manual mode")
            else:
                require(identity["evidence_mode"] in {"candidate_branch_push", "exact_main_push"}, "source push mode")
    else:
        exact(value["source_binding"], None, "kernel-only fixture cannot identify a compiled Servo object")
    return {"schema": "trillionnium.desktop.netns-offline-verification.v1", "status": expected_status,
        "case_count": len(observed), "corpus_sha256": packet.finish()["namespace-corpus.json"],
        "source_qualification_only": True, "installed_qualified": False, "production_ready": False}


def validate_contract(value: object | None = None) -> None:
    """Fixed reviewed profile. This interface has no refresh or promotion mode."""
    if value is None:
        descriptor = open_file(ROOT / "contracts/native-direct-inet-qualification.v1.json")
        with os.fdopen(descriptor, "rb") as stream:
            data = stream.read(65537)
            require(len(data) <= 65536, "namespace contract exceeded bound")
        value = load_json_strict(data.decode())
    expected = {
        "schema": "trillionnium.desktop.native-direct-inet-qualification-contract.v1",
        "status": "SOURCE_ONLY_EXPLICIT_QUALIFICATION_PROCEDURE", "profile": PROFILE,
        "activation": {"default_enabled": False, "environment_key": "HEPTA_D0A02_NETNS_PROFILE",
            "environment_value": PROFILE, "product_activation_allowed": False},
        "fixture": {"origin": ORIGIN, "holds_inet_listener": False, "trusted_app_admission": False, "signed_app_qualification": False},
        "limits": {"entry_absolute_budget_seconds": 10, "maximum_entry_fds": 256, "maximum_entry_proc_bytes": 8192,
            "maximum_packet_bytes": 2097152, "maximum_runtime_log_bytes": 16777216, "host_observation_budget_seconds": 4,
            "unit_runtime_max_seconds": 180, "unit_stop_timeout_seconds": 5},
        "systemd_properties": PROPERTIES,
        "temporary_directory": {"path_pattern": "/tmp/hn-[a-f0-9]{24}", "maximum_absolute_path_bytes": 32,
            "mode": 0o700, "creator_pid_guard": True, "nofollow_retained_inode_required": True,
            "actual_process_TMPDIR_observed": True, "read_write_paths": "exact renderer plus retained private temporary directory",
            "whole_host_tmp_writable": False, "PrivateTmp_enabled": False, "GC_removes_paths": False,
            "cleanup_after_exact_unit_retirement": True, "cleanup_maximum_entries": 256,
            "cleanup_maximum_enumerated_names_before_refusal": 257, "cleanup_root_empty_maximum_names": 1,
            "cleanup_maximum_bytes": 33554432, "cleanup_maximum_depth": 4, "cleanup_absolute_budget_seconds": 5},
        "authority": {"entry_stop_before_engine_start": True, "actual_retained_pidfd_required": True,
            "actual_pidfd_getfd_required": True, "actual_complete_host_fd_inventory_required": True,
            "socket_domain_alone_is_peer_approval": False, "host_records_outside_renderer_write_root": True,
            "systemd_unit_name_owns_cleanup": True, "caller_asserted_identity_authority": False},
        "required_cases": ["burst", "chrome", "window-leave", "focus-loss"] +
            [f"inherited-{role}-ipv{version}" for role in ("embedder", "content") for version in (4, 6)],
        "kernel_fixture_cases": ["kernel-fixture"] +
            [f"inherited-{role}-ipv{version}" for role in ("embedder", "content") for version in (4, 6)],
        "record_fields": {"entry": sorted(ENTRY_KEYS), "refusal": sorted(REFUSAL_KEYS), "host": sorted(HOST_KEYS),
            "temporary_directory": sorted(TEMP_KEYS), "launch": sorted(LAUNCH_KEYS),
            "process_identity": sorted(IDENTITY_KEYS), "entry_fd": ["device", "fd", "inode", "kind"],
            "host_fd": ["device", "fd", "inode", "kind", "socket_domain"]},
        "source_paths": list(SOURCE_PATHS), "compiled_overlay_files": list(COMPILED_PATHS),
        "claim_ceiling": {"installed_qualified": False, "production_ready": False, "installed_all_protocol_confinement": False,
            "host_unix_proxy_confinement": False, "approved_unix_peer_policy": False,
            "late_scm_rights_authority_qualified": False, "lifetime_socket_authority_qualified": False,
            "arbitrary_file_descriptor_authority_qualified": False, "approved_external_egress": False,
            "physical_hardware_input_qualified": False, "wayland_scaling_qualified": False, "installed_browser_actor": False},
        "qualification": {"servo_commit": PIN, "missing_support_is_failure": True, "skip_is_success": False,
            "actual_native_compile_and_corpus_required": True, "kernel_fixture_is_native_qualification": False,
            "default_rapid_pairs": 3, "default_rapid_document_click_events": 3, "held_cases_synthetic_up_allowed": False,
            "qualification_nonce_enabled": False, "qualification_results_embedded_in_contract": False}}
    exact_tree(value, expected, "namespace fixed profile/claim/field set drift")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("inspect", "run", "verify", "verify-corpus", "kernel-fixture", "validate-contract"))
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--case", choices=("burst", "chrome", "window-leave", "focus-loss", "kernel-fixture",
        "inherited-embedder-ipv4", "inherited-embedder-ipv6", "inherited-content-ipv4", "inherited-content-ipv6"))
    args = parser.parse_args()
    validate_contract()
    if args.mode == "validate-contract":
        return 0
    if args.mode == "inspect":
        import sys
        data = sys.stdin.buffer.read(32769)
        require(len(data) <= 32768, "inspect request exceeded bound")
        print(json.dumps(inspect_stopped(load_json_strict(data.decode())), sort_keys=True, allow_nan=False))
    elif args.mode == "verify-corpus":
        require(args.output is not None, "corpus verification requires output")
        print(json.dumps(verify_corpus(args.output), sort_keys=True, allow_nan=False))
    elif args.mode == "verify":
        require(args.output is not None and args.case is not None, "verify requires exact case/output")
        print(json.dumps(verify_packet(args.output, args.case), sort_keys=True, allow_nan=False))
    else:
        require(args.output is not None and args.binary is not None, "run requires explicit binary/output")
        os.umask(0o077)
        require(not args.output.exists(), "namespace corpus must be fresh")
        args.output.mkdir(mode=0o700, parents=True)
        cases = ["kernel-fixture"] if args.mode == "kernel-fixture" else ["burst", "chrome", "window-leave", "focus-loss"]
        cases += [f"inherited-{role}-ipv{version}" for role in ("embedder", "content") for version in (4, 6)]
        with _StagedExecutable(args.binary.absolute(), artifact_root=args.output) as executable:
            binding = source_binding(executable.path) if args.mode == "run" else None
            results = []
            for case in cases:
                executable.verify()
                results.append(run_case(executable.path, args.output / case, case))
            executable.verify()
            if binding is not None:
                exact_tree(source_binding(executable.path), binding, "compiled/source object changed during namespace corpus")
        write_json(args.output / "namespace-corpus.json", {"schema": "trillionnium.desktop.netns-corpus.v1",
            "status": "PASS_HOST_KERNEL_FIXTURE_ONLY" if args.mode == "kernel-fixture" else "PASS_EXPLICIT_NATIVE_DIRECT_INET_QUALIFICATION_ONLY",
            "actual_servo_executed": args.mode == "run", "cases": results, "source_qualification_only": True,
            "source_binding": binding, "host_unix_proxy_confinement": False, "approved_unix_peer_policy": False,
            "late_scm_rights_authority_qualified": False, "lifetime_socket_authority_qualified": False,
            "installed_all_protocol_confinement": False,
            "installed_qualified": False, "production_ready": False})
        verify_corpus(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
