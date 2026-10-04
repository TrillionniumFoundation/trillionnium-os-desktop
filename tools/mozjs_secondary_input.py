"""Finite mozjs secondary-input custody for an explicit candidate build profile.

This copies a reviewed archive into a bounded sealed Linux memfd. An API digest
correspondence is not artifact attestation, a signature or build qualification.
"""
from __future__ import annotations

import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import threading

try:
    from .artifact_evidence import open_managed_file
    from .browser_codec_reference_security import _SourceDescriptor, load_json_strict
except ImportError:
    from artifact_evidence import open_managed_file
    from browser_codec_reference_security import _SourceDescriptor, load_json_strict

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = "manifests/mozjs-secondary-input.v1.json"
MAX_MANIFEST_BYTES = 16384
MAX_ARCHIVE_BYTES = 32 * 1024 * 1024
CHUNK_BYTES = 1024 * 1024
SEALS = fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL
PROFILE = {
    "schema": "trillionnium.mozjs-secondary-input.v1",
    "servo_pin": "670ae8a70801b162e186f81cbb5bdd2d59c39108",
    "cargo_package": {"name": "mozjs_sys", "version": "140.14.0-1",
        "source": "registry+https://github.com/rust-lang/crates.io-index",
        "checksum": "4cb5edb8729da5f2b09939fcad2559ba1c54e55d222f14d485b88c7d645890d5"},
    "secondary_input": {"target": "x86_64-unknown-linux-gnu",
        "asset_id": 527403045, "name": "libmozjs-x86_64-unknown-linux-gnu.tar.gz",
        "url": "https://github.com/servo/mozjs/releases/download/mozjs-sys-v140.14.0-1/libmozjs-x86_64-unknown-linux-gnu.tar.gz",
        "bytes": 19381534,
        "sha256": "c5f93d7f9f1b450e2a608b5e7378c95ec8fa9f3689bdfe1f6ad548e434c3107b"},
    "correspondence": {"official_api_observation_sha256": "1c7cf8313eff2b28feb120c940d4e6e5197b3f65a529010108a72b23cc453e26",
        "api_size_digest_match_observed": True, "attestation_verified": False,
        "cargo_lock_covers_secondary_archive": False,
        "upstream_build_rs_sha256": "94b782be9a6ca00644c8ae85817bd6b946b993a96c59a9b7cda7cf9b095f5cf0",
        "nonzero_attestation_status_observation": "static_only_no_fault_injection"},
    "build_profile": {"status": "SOURCE_CANDIDATE_NOT_QUALIFIED",
        "toolchain": "1.97.1", "cargo_profile": "checked-release",
        "features": "bundled,js_jit", "default_features": False, "locked": True,
        "targets": {"native-owner": "trillionnium_product_owner", "approved-startup": "trillionnium_approved_connected"},
        "target_directory": "exclusive_initially_empty_per_invocation",
        "archive_binding": "sealed_memfd_parent_pid_proc_fd_path_held_until_process_group_ends",
        "timeout_seconds": 10800, "termination_grace_seconds": 5,
        "upstream_cached_archive_can_override_MOZJS_ARCHIVE": True,
        "actual_cargo_archive_consumption_proven": False},
    "claims": {"default_ci_changed": False, "artifact_attestation": False,
        "actual_native_execution": False, "installed_qualified": False,
        "human_approval": False, "production_ready": False},
}


def check_manifest(value: object) -> None:
    """Match the entire reviewed profile, including exact JSON scalar types."""
    if json.dumps(value, sort_keys=True, allow_nan=False) != json.dumps(PROFILE, sort_keys=True):
        raise ValueError("mozjs secondary-input manifest differs from reviewed profile")


def load_manifest() -> dict:
    with open_managed_file(ROOT / MANIFEST) as reader:
        before = reader.stat()
        if before.st_size > MAX_MANIFEST_BYTES:
            raise ValueError("mozjs manifest exceeds byte bound")
        raw = reader.read(MAX_MANIFEST_BYTES + 1)
        after = reader.stat()
        if _identity(before) != _identity(after) or len(raw) != before.st_size:
            raise ValueError("mozjs manifest changed during read")
    value = load_json_strict(raw.decode("utf-8", "strict"))
    check_manifest(value)
    return value


def _identity(metadata: os.stat_result) -> tuple[int, ...]:
    return (metadata.st_dev, metadata.st_ino, metadata.st_mode, metadata.st_uid,
            metadata.st_gid, metadata.st_nlink, metadata.st_size,
            metadata.st_mtime_ns, metadata.st_ctime_ns)


def _sealed_identity(metadata: os.stat_result) -> tuple[int, ...]:
    # Linux may update timestamps on a failed write against F_SEAL_WRITE.
    # Retained object/mode/size plus complete digest and all seals
    # bind immutable bytes; times remain part of the mutable source read check.
    return _identity(metadata)[:7]


class SealedArchiveLease:
    """Creator-bound owner of one immutable input; the string path is borrowed.

    No descriptor is publicly transferred. Public use requires the creating
    process/thread and an active lease. Descriptor-only finalization covers
    ordinary Python object/result loss, not every native/opcode interruption.
    """

    def __init__(self) -> None:
        self._creator_pid = os.getpid()
        self._creator_thread = threading.current_thread()
        self._owner = _SourceDescriptor()
        self._original: os.stat_result | None = None
        self._expected_size = 0
        self._expected_sha256 = ""
        self._active = False

    def _creator(self) -> None:
        if os.getpid() != self._creator_pid or threading.current_thread() is not self._creator_thread:
            raise ValueError("archive lease requires its creator process and thread")
        if self._active:
            raise ValueError("archive lease forbids reentrant operations")

    def _descriptor(self) -> int:
        if self._owner.fd is None or self._original is None:
            raise ValueError("archive lease is closed or incomplete")
        current = os.fstat(self._owner.fd)
        if _sealed_identity(current) != _sealed_identity(self._original) or not stat.S_ISREG(current.st_mode):
            raise ValueError("archive lease descriptor identity changed")
        if fcntl.fcntl(self._owner.fd, fcntl.F_GET_SEALS) != SEALS:
            raise ValueError("archive lease seals differ")
        return self._owner.fd

    def readback(self) -> dict[str, object]:
        """Read the actual stable proc path and compare all sealed bytes."""
        self._creator()
        borrowed = _SourceDescriptor()
        try:
            self._active = True
            descriptor = self._descriptor()
            path = f"/proc/{self._creator_pid}/fd/{descriptor}"
            borrowed.fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC)
            if _sealed_identity(os.fstat(borrowed.fd)) != _sealed_identity(self._original):
                raise ValueError("archive proc path does not bind retained input")
            value = hashlib.sha256(); offset = 0
            while offset < self._expected_size:
                raw = os.pread(borrowed.fd, min(CHUNK_BYTES, self._expected_size - offset), offset)
                if not raw:
                    raise ValueError("sealed archive readback was short")
                offset += len(raw); value.update(raw)
            if os.pread(borrowed.fd, 1, offset) or value.hexdigest() != self._expected_sha256:
                raise ValueError("sealed archive readback differs")
            self._descriptor()
            if _sealed_identity(os.fstat(borrowed.fd)) != _sealed_identity(self._original):
                raise ValueError("sealed archive changed during readback")
            return {"bytes": offset, "sha256": value.hexdigest(), "sealed": True}
        finally:
            try:
                borrowed.close()
            finally:
                self._active = False

    def stable_path(self) -> str:
        """Borrow a path valid only until this owner closes; never an authority."""
        self.readback()
        return f"/proc/{self._creator_pid}/fd/{self._descriptor()}"

    def _release(self) -> None:
        descriptor = self._owner.fd
        if descriptor is not None:
            try:
                metadata = os.fstat(descriptor)
            except OSError:
                self._owner.fd = None
                return
            if self._original is not None and (metadata.st_dev, metadata.st_ino) != (self._original.st_dev, self._original.st_ino):
                # A reused integer belongs to somebody else. Never close it.
                self._owner.fd = None
                return
            self._owner.close()

    def close(self) -> None:
        self._creator()
        self._release()

    def __enter__(self) -> SealedArchiveLease:
        self.readback()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.close()

    def __del__(self) -> None:
        try:
            self._release()
        except BaseException:
            pass


def _lease_archive(path: Path, expected_size: int, expected_sha256: str) -> SealedArchiveLease:
    """Private small-fixture primitive; public admission uses only reviewed manifest."""
    if type(expected_size) is not int or not 0 < expected_size <= MAX_ARCHIVE_BYTES:
        raise ValueError("archive exceeds its finite byte profile")
    lease = SealedArchiveLease()
    try:
        lease._expected_size = expected_size
        lease._expected_sha256 = expected_sha256
        lease._owner.fd = os.memfd_create("reviewed-mozjs-archive", os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        lease._original = os.fstat(lease._owner.fd)
        with open_managed_file(path.absolute()) as reader:
            before = reader.stat()
            if before.st_size != expected_size:
                raise ValueError("archive size differs from reviewed input")
            value = hashlib.sha256(); total = 0
            while total < expected_size:
                raw = reader.read_some(min(CHUNK_BYTES, expected_size - total))
                if not raw:
                    raise ValueError("archive read was short")
                total += len(raw); value.update(raw); view = memoryview(raw)
                while view:
                    count = os.write(lease._owner.fd, view)
                    if count <= 0:
                        raise ValueError("archive snapshot write made no progress")
                    view = view[count:]
            if reader.read_some(1) or value.hexdigest() != expected_sha256:
                raise ValueError("archive digest differs from reviewed input")
            after = reader.stat()
            if _identity(before) != _identity(after) or _identity(path.absolute().lstat()) != _identity(after):
                raise ValueError("archive source identity changed while copying")
        os.fchmod(lease._owner.fd, 0o400)
        fcntl.fcntl(lease._owner.fd, fcntl.F_ADD_SEALS, SEALS)
        lease._original = os.fstat(lease._owner.fd)
        lease.readback()
        return lease
    except BaseException:
        lease._release()
        raise


def lease_archive(path: Path) -> SealedArchiveLease:
    """Admit exactly the checked-in reviewed secondary archive, without download."""
    profile = load_manifest()["secondary_input"]
    return _lease_archive(path, profile["bytes"], profile["sha256"])
