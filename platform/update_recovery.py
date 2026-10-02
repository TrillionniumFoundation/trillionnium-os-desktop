"""Fail-closed S11 A/B update and recovery mechanism candidate.

The module validates immutable whole-image manifests and owns a bounded state
machine.  It does not download, execute, sign, publish, or claim an installed
update.  Every ambiguous transition is rejected, and a possible dispatch
requires durable reconciliation before any retry.
"""
from __future__ import annotations

import errno
import fcntl
import hashlib
import json
import math
import os
import re
import secrets
import stat
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Callable

REPOSITORY = "TrillionniumFoundation/trillionnium-os-desktop"
MANIFEST_SCHEMA = "trillionnium.desktop.update-manifest.v1"
MAX_MANIFEST_BYTES = 64 * 1024
MAX_IMAGE_BYTES = 16 * 1024 * 1024 * 1024
MAX_STATE_BYTES = 64 * 1024
MAX_FUTURE_SECONDS = 31 * 24 * 60 * 60
MIN_STABLE_HEALTH_SECONDS = 60
MAX_BOOT_FAILURES = 2
_HASH = re.compile(r"[0-9a-f]{64}\Z")
_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,127}\Z")
_SEAL = object()


class UpdateError(RuntimeError):
    """Base class for redacted update/refusal failures."""


class ManifestRefused(UpdateError):
    pass


class StateRefused(UpdateError):
    pass


class RecoveryRequired(UpdateError):
    pass


class CoordinatorBusy(UpdateError):
    pass


class PublicationIndeterminate(UpdateError):
    """The final state pathname may already contain the intended bytes."""

    def __init__(self, digest: str, cause: BaseException):
        super().__init__(
            "state publication crossed the atomic replace boundary; reconcile before retry"
        )
        self.digest = digest
        self.cause = cause


class Phase(str, Enum):
    IDLE = "idle"
    VERIFIED = "verified"
    STAGED = "staged"
    BOOT_PENDING = "boot_pending"
    HEALTH_PENDING = "health_pending"
    COMMITTED = "committed"
    ROLLBACK_PENDING = "rollback_pending"
    RECOVERY_REQUIRED = "recovery_required"


MANIFEST_FIELDS = {
    "schema",
    "repository",
    "source_version",
    "source_image_sha256",
    "target_version",
    "target_slot",
    "target_image_sha256",
    "target_image_bytes",
    "rollback_floor",
    "expires_unix",
    "signer_id",
    "signature_sha256",
}


def _strict_object(payload: bytes | str, maximum: int) -> dict[str, Any]:
    raw = payload.encode("utf-8") if isinstance(payload, str) else payload
    if not isinstance(raw, bytes) or not raw or len(raw) > maximum:
        raise ManifestRefused("JSON payload is empty, non-bytes, or over limit")
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError as error:
        raise ManifestRefused("JSON is not strict UTF-8") from error
    if text.startswith("\ufeff"):
        raise ManifestRefused("UTF-8 BOM is forbidden")

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in items:
            if key in result:
                raise ManifestRefused("duplicate JSON member")
            result[key] = value
        return result

    def constant(_: str) -> None:
        raise ManifestRefused("non-JSON numeric constant")

    def finite_float(value: str) -> float:
        number = float(value)
        if not math.isfinite(number):
            raise ManifestRefused("non-finite JSON number")
        return number

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant,
                           parse_float=finite_float)
    except (json.JSONDecodeError, ManifestRefused, ValueError) as error:
        if isinstance(error, ManifestRefused):
            raise
        raise ManifestRefused("malformed JSON") from error
    if not isinstance(value, dict):
        raise ManifestRefused("JSON root must be an object")
    return value


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(
        value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("ascii")


def _hash(value: object, label: str) -> str:
    if not isinstance(value, str) or _HASH.fullmatch(value) is None:
        raise ManifestRefused(f"{label} is not a lowercase SHA-256")
    return value


def _positive_int(value: object, label: str, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ManifestRefused(f"{label} must be a positive integer")
    if maximum is not None and value > maximum:
        raise ManifestRefused(f"{label} exceeds its bound")
    return value


@dataclass(frozen=True)
class UpdateManifest:
    repository: str
    source_version: int
    source_image_sha256: str
    target_version: int
    target_slot: str
    target_image_sha256: str
    target_image_bytes: int
    rollback_floor: int
    expires_unix: int
    signer_id: str
    signature_sha256: str
    manifest_sha256: str

    @classmethod
    def parse(
        cls,
        payload: bytes | str,
        *,
        now_unix: int,
        active_slot: str,
        current_version: int,
        current_image_sha256: str,
    ) -> "UpdateManifest":
        value = _strict_object(payload, MAX_MANIFEST_BYTES)
        if set(value) != MANIFEST_FIELDS:
            raise ManifestRefused("manifest fields are not the exact closed set")
        if value["schema"] != MANIFEST_SCHEMA or value["repository"] != REPOSITORY:
            raise ManifestRefused("manifest schema or repository identity is wrong")
        if active_slot not in {"A", "B"}:
            raise ManifestRefused("active slot is invalid")
        _positive_int(now_unix, "now_unix")
        _positive_int(current_version, "current_version")
        _hash(current_image_sha256, "current image")
        source_version = _positive_int(value["source_version"], "source_version")
        target_version = _positive_int(value["target_version"], "target_version")
        rollback_floor = _positive_int(value["rollback_floor"], "rollback_floor")
        source_digest = _hash(value["source_image_sha256"], "source image")
        target_digest = _hash(value["target_image_sha256"], "target image")
        signature_digest = _hash(value["signature_sha256"], "signature")
        target_bytes = _positive_int(
            value["target_image_bytes"], "target_image_bytes", MAX_IMAGE_BYTES
        )
        expires = _positive_int(value["expires_unix"], "expires_unix")
        signer = value["signer_id"]
        if not isinstance(signer, str) or _ID.fullmatch(signer) is None:
            raise ManifestRefused("signer identity is invalid")
        target_slot = value["target_slot"]
        if target_slot not in {"A", "B"} or target_slot == active_slot:
            raise ManifestRefused("target must be the inactive A/B slot")
        if source_version != current_version or source_digest != current_image_sha256:
            raise ManifestRefused("manifest source does not bind the running image")
        if target_version <= current_version:
            raise ManifestRefused("downgrade or same-version update is forbidden")
        if target_version < rollback_floor or current_version < rollback_floor:
            raise ManifestRefused("rollback floor is not satisfied")
        if target_digest == source_digest:
            raise ManifestRefused("target image is not distinct from the source")
        if expires <= now_unix or expires - now_unix > MAX_FUTURE_SECONDS:
            raise ManifestRefused("manifest is expired or unreasonably future-dated")
        return cls(
            repository=REPOSITORY,
            source_version=source_version,
            source_image_sha256=source_digest,
            target_version=target_version,
            target_slot=target_slot,
            target_image_sha256=target_digest,
            target_image_bytes=target_bytes,
            rollback_floor=rollback_floor,
            expires_unix=expires,
            signer_id=signer,
            signature_sha256=signature_digest,
            manifest_sha256=hashlib.sha256(_canonical(value)).hexdigest(),
        )


@dataclass(frozen=True)
class ManifestTicket:
    manifest: UpdateManifest
    sequence: int
    _seal: object

    def __post_init__(self) -> None:
        if self._seal is not _SEAL:
            raise StateRefused("manifest ticket was not issued by the coordinator")


@dataclass(frozen=True)
class HealthPermit:
    manifest_sha256: str
    sequence: int
    health_receipt_sha256: str
    _seal: object

    def __post_init__(self) -> None:
        if self._seal is not _SEAL:
            raise StateRefused("health permit was not issued by the coordinator")


@dataclass(frozen=True)
class JournalReconciliation:
    manifest_sha256: str
    sequence: int
    journal_record_sha256: str
    status: str
    _seal: object

    def __post_init__(self) -> None:
        if self._seal is not _SEAL:
            raise StateRefused("reconciliation fact was not issued by the journal adapter")


class UpdateCoordinator:
    """Single-operation, fail-closed A/B update coordinator."""

    def __init__(
        self,
        *,
        active_slot: str,
        current_version: int,
        current_image_sha256: str,
        max_boot_failures: int = MAX_BOOT_FAILURES,
    ) -> None:
        if active_slot not in {"A", "B"}:
            raise StateRefused("active slot is invalid")
        if type(current_version) is not int or current_version <= 0 or not isinstance(current_image_sha256, str) or _HASH.fullmatch(current_image_sha256) is None:
            raise StateRefused("current image identity is invalid")
        if type(max_boot_failures) is not int or max_boot_failures <= 0 or max_boot_failures > 16:
            raise StateRefused("boot failure bound is invalid")
        self.active_slot = active_slot
        self.current_version = current_version
        self.current_image_sha256 = current_image_sha256
        self.max_boot_failures = max_boot_failures
        self.phase = Phase.IDLE
        self.sequence = 0
        self.boot_failures = 0
        self._ticket: ManifestTicket | None = None
        self._effect_reconciliation_required = False

    @property
    def effect_reconciliation_required(self) -> bool:
        return self._effect_reconciliation_required

    def _require(self, ticket: ManifestTicket, *phases: Phase) -> UpdateManifest:
        if (
            ticket._seal is not _SEAL
            or self._ticket is not ticket
            or ticket.sequence != self.sequence
            or self.phase not in phases
        ):
            raise StateRefused("ticket, sequence, or phase is stale")
        return ticket.manifest

    def verify_manifest(
        self, payload: bytes | str, *, now_unix: int
    ) -> ManifestTicket:
        if self.phase not in {Phase.IDLE, Phase.COMMITTED}:
            raise StateRefused("another update transaction is active")
        if self._effect_reconciliation_required:
            raise StateRefused("possible prior dispatch requires reconciliation")
        manifest = UpdateManifest.parse(
            payload,
            now_unix=now_unix,
            active_slot=self.active_slot,
            current_version=self.current_version,
            current_image_sha256=self.current_image_sha256,
        )
        sequence = self.sequence + 1
        if sequence > (1 << 63) - 1:
            raise StateRefused("update sequence exhausted")
        self.sequence = sequence
        ticket = ManifestTicket(manifest, sequence, _SEAL)
        self._ticket = ticket
        self.phase = Phase.VERIFIED
        self.boot_failures = 0
        return ticket

    def stage_image(self, ticket: ManifestTicket, image: bytes) -> None:
        manifest = self._require(ticket, Phase.VERIFIED)
        if not isinstance(image, bytes):
            raise StateRefused("image must be immutable bytes")
        if len(image) != manifest.target_image_bytes:
            raise StateRefused("whole-image length does not match the manifest")
        if hashlib.sha256(image).hexdigest() != manifest.target_image_sha256:
            raise StateRefused("whole-image digest does not match the manifest")
        self.phase = Phase.STAGED

    def arm_first_boot(self, ticket: ManifestTicket) -> None:
        self._require(ticket, Phase.STAGED)
        self.phase = Phase.BOOT_PENDING

    def record_booted_image(
        self, ticket: ManifestTicket, *, slot: str, image_sha256: str
    ) -> None:
        manifest = self._require(ticket, Phase.BOOT_PENDING)
        if slot != manifest.target_slot or image_sha256 != manifest.target_image_sha256:
            self.phase = Phase.RECOVERY_REQUIRED
            raise RecoveryRequired("booted slot identity does not match the staged image")
        self.phase = Phase.HEALTH_PENDING

    def record_health(
        self,
        ticket: ManifestTicket,
        *,
        stable_seconds: int,
        health_receipt_sha256: str,
    ) -> HealthPermit:
        manifest = self._require(ticket, Phase.HEALTH_PENDING)
        if type(stable_seconds) is not int or stable_seconds < MIN_STABLE_HEALTH_SECONDS:
            raise StateRefused("health window is not stable for the required duration")
        if not isinstance(health_receipt_sha256, str) or _HASH.fullmatch(health_receipt_sha256) is None:
            raise StateRefused("health receipt digest is invalid")
        return HealthPermit(
            manifest.manifest_sha256,
            ticket.sequence,
            health_receipt_sha256,
            _SEAL,
        )

    def commit(self, permit: HealthPermit) -> None:
        ticket = self._ticket
        if (
            permit._seal is not _SEAL
            or ticket is None
            or self.phase != Phase.HEALTH_PENDING
            or permit.sequence != ticket.sequence
            or permit.manifest_sha256 != ticket.manifest.manifest_sha256
        ):
            raise StateRefused("commit permit is stale or unrelated")
        manifest = ticket.manifest
        self.active_slot = manifest.target_slot
        self.current_version = manifest.target_version
        self.current_image_sha256 = manifest.target_image_sha256
        self.phase = Phase.COMMITTED
        self.boot_failures = 0
        self._ticket = None

    def record_boot_failure(self, ticket: ManifestTicket) -> Phase:
        self._require(ticket, Phase.BOOT_PENDING, Phase.HEALTH_PENDING)
        self.boot_failures += 1
        if self.boot_failures >= self.max_boot_failures:
            self.phase = Phase.ROLLBACK_PENDING
        else:
            self.phase = Phase.BOOT_PENDING
        return self.phase

    def rollback(self, ticket: ManifestTicket, *, recovered_image_sha256: str) -> None:
        manifest = self._require(ticket, Phase.ROLLBACK_PENDING)
        if recovered_image_sha256 != manifest.source_image_sha256:
            self.phase = Phase.RECOVERY_REQUIRED
            raise RecoveryRequired("rollback did not restore the exact source image")
        self.phase = Phase.IDLE
        self.boot_failures = 0
        self._ticket = None

    def mark_possible_dispatch(self, ticket: ManifestTicket) -> None:
        self._require(
            ticket,
            Phase.VERIFIED,
            Phase.STAGED,
            Phase.BOOT_PENDING,
            Phase.HEALTH_PENDING,
        )
        self._effect_reconciliation_required = True
        self.phase = Phase.RECOVERY_REQUIRED

    @staticmethod
    def verify_journal_reconciliation(
        ticket: ManifestTicket, *, journal_record_sha256: str, status: str
    ) -> JournalReconciliation:
        if ticket._seal is not _SEAL or _HASH.fullmatch(journal_record_sha256) is None:
            raise StateRefused("journal reconciliation binding is invalid")
        if status not in {"terminal", "indeterminate"}:
            raise StateRefused("journal has no terminal or indeterminate fact")
        return JournalReconciliation(
            ticket.manifest.manifest_sha256,
            ticket.sequence,
            journal_record_sha256,
            status,
            _SEAL,
        )

    def reconcile_possible_dispatch(self, fact: JournalReconciliation) -> None:
        ticket = self._ticket
        if (
            fact._seal is not _SEAL
            or ticket is None
            or not self._effect_reconciliation_required
            or fact.sequence != ticket.sequence
            or fact.manifest_sha256 != ticket.manifest.manifest_sha256
        ):
            raise StateRefused("journal reconciliation is stale or unrelated")
        self._effect_reconciliation_required = False
        self.phase = Phase.ROLLBACK_PENDING

    def reconcile_startup(self, slot_digests: dict[str, str]) -> Phase:
        if set(slot_digests) != {"A", "B"}:
            self.phase = Phase.RECOVERY_REQUIRED
            raise RecoveryRequired("both exact slot identities are required")
        if any(_HASH.fullmatch(value) is None for value in slot_digests.values()):
            self.phase = Phase.RECOVERY_REQUIRED
            raise RecoveryRequired("slot identity is malformed")
        ticket = self._ticket
        if ticket is not None and self.phase in {
            Phase.STAGED,
            Phase.BOOT_PENDING,
            Phase.HEALTH_PENDING,
            Phase.ROLLBACK_PENDING,
        }:
            manifest = ticket.manifest
            if slot_digests.get(manifest.target_slot) != manifest.target_image_sha256:
                self.phase = Phase.RECOVERY_REQUIRED
                raise RecoveryRequired("pending target slot is missing or substituted")
        if slot_digests.get(self.active_slot) != self.current_image_sha256:
            self.phase = Phase.RECOVERY_REQUIRED
            raise RecoveryRequired("active slot no longer matches durable identity")
        return self.phase


class AtomicStateStore:
    """Descriptor-pinned private state publication with an exclusive lease."""

    def __init__(self, root: Path):
        self.root = Path(root).absolute()
        try:
            self._root_fd = self._open_root()
        except OSError as error:
            raise StateRefused("state root cannot be opened without following links") from error
        metadata = os.fstat(self._root_fd)
        mode = stat.S_IMODE(metadata.st_mode)
        if not stat.S_ISDIR(metadata.st_mode) or mode & 0o077:
            os.close(self._root_fd)
            raise StateRefused("state root must be a private 0700-style directory")
        if metadata.st_uid not in {0, os.geteuid()}:
            os.close(self._root_fd)
            raise StateRefused("state root owner is not trusted")
        self._identity = (metadata.st_dev, metadata.st_ino)
        self._lease_fd: int | None = None

    def _open_root(self) -> int:
        descriptor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            for component in self.root.parts[1:]:
                if component in {".", ".."}:
                    raise StateRefused("state root path contains traversal")
                next_descriptor = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=descriptor)
                os.close(descriptor)
                descriptor = next_descriptor
            return descriptor
        except BaseException:
            os.close(descriptor)
            raise

    def close(self) -> None:
        if self._lease_fd is not None:
            fcntl.flock(self._lease_fd, fcntl.LOCK_UN)
            os.close(self._lease_fd)
            self._lease_fd = None
        if getattr(self, "_root_fd", None) is not None:
            os.close(self._root_fd)
            self._root_fd = None

    def __enter__(self) -> "AtomicStateStore":
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _check_root(self) -> int:
        fd = self._root_fd
        if fd is None:
            raise StateRefused("state store is closed")
        current = os.fstat(fd)
        if (current.st_dev, current.st_ino) != self._identity:
            raise StateRefused("retained state root identity changed")
        if current.st_uid not in {0, os.geteuid()} or stat.S_IMODE(current.st_mode) & 0o077:
            raise StateRefused("state root custody is no longer private")
        try:
            current_fd = self._open_root()
        except OSError as error:
            raise StateRefused("state root pathname is no longer safe") from error
        try:
            pathname = os.fstat(current_fd)
            if (pathname.st_dev, pathname.st_ino) != self._identity:
                raise StateRefused("state root pathname no longer names the retained directory")
        finally:
            os.close(current_fd)
        if self._lease_fd is not None:
            lease = os.fstat(self._lease_fd)
            if not stat.S_ISREG(lease.st_mode) or lease.st_nlink != 1 or lease.st_uid not in {0, os.geteuid()} or stat.S_IMODE(lease.st_mode) & 0o077:
                raise StateRefused("retained coordinator lease custody changed")
            try:
                named_fd = os.open(".coordinator.lock", os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            except OSError as error:
                raise StateRefused("coordinator lease pathname is absent or unsafe") from error
            try:
                named = os.fstat(named_fd)
                if (named.st_dev, named.st_ino) != (lease.st_dev, lease.st_ino):
                    raise StateRefused("coordinator lease pathname was replaced")
            finally:
                os.close(named_fd)
        return fd

    def acquire(self) -> None:
        root_fd = self._check_root()
        if self._lease_fd is not None:
            raise CoordinatorBusy("coordinator lease is already held")
        fd = os.open(
            ".coordinator.lock",
            os.O_RDWR | os.O_CREAT | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
            dir_fd=root_fd,
        )
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_uid not in {0, os.geteuid()} or stat.S_IMODE(metadata.st_mode) != 0o600:
                raise StateRefused("coordinator lease must be a trusted regular file with one hard link")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, StateRefused) as error:
            os.close(fd)
            if isinstance(error, OSError) and error.errno in {errno.EACCES, errno.EAGAIN}:
                raise CoordinatorBusy("another update coordinator holds the lease") from error
            raise
        self._lease_fd = fd

    @staticmethod
    def _name(name: str) -> str:
        if not isinstance(name, str) or name.startswith(".") or "\x00" in name or "\\" in name:
            raise StateRefused("state name is reserved or malformed")
        path = PurePosixPath(name)
        if path.is_absolute() or len(path.parts) != 1 or path.parts[0] in {"", ".", ".."} or path.as_posix() != name:
            raise StateRefused("state name must be one safe basename")
        return path.parts[0]

    def write(
        self,
        name: str,
        value: dict[str, Any],
        *,
        fault: Callable[[str], None] | None = None,
    ) -> str:
        if self._lease_fd is None:
            raise CoordinatorBusy("exclusive coordinator lease is required")
        name = self._name(name)
        data = _canonical(value)
        if not data or len(data) > MAX_STATE_BYTES:
            raise StateRefused("state payload is empty or over limit")
        digest = hashlib.sha256(data).hexdigest()
        root_fd = self._check_root()
        temp = f".{name}.{os.getpid()}.{secrets.token_hex(16)}.tmp"
        temp_fd: int | None = None
        created = False
        temp_identity: tuple[int, int] | None = None
        replaced = False
        try:
            if fault:
                fault("before_temp_create")
            temp_fd = os.open(
                temp,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=root_fd,
            )
            created = True
            os.fchmod(temp_fd, 0o600)
            staged = os.fstat(temp_fd)
            temp_identity = (staged.st_dev, staged.st_ino)
            if fault:
                fault("after_temp_create")
            offset = 0
            while offset < len(data):
                written = os.write(temp_fd, data[offset:])
                if written <= 0:
                    raise StateRefused("state write made no progress")
                offset += written
            if fault:
                fault("after_complete_write")
            os.fsync(temp_fd)
            if fault:
                fault("after_file_fsync")
            self._check_root()
            self._check_staged_file(root_fd, temp, temp_fd, data)
            os.replace(temp, name, src_dir_fd=root_fd, dst_dir_fd=root_fd)
            replaced = True
            if fault:
                fault("after_atomic_replace")
            self._check_staged_file(root_fd, name, temp_fd, data)
            os.fsync(root_fd)
            if fault:
                fault("after_directory_fsync")
            self._check_root()
            self._check_staged_file(root_fd, name, temp_fd, data)
            return digest
        except Exception as error:
            if replaced:
                raise PublicationIndeterminate(digest, error) from error
            if created:
                try:
                    metadata = os.stat(temp, dir_fd=root_fd, follow_symlinks=False)
                    if (metadata.st_dev, metadata.st_ino) == temp_identity:
                        os.unlink(temp, dir_fd=root_fd)
                except OSError as cleanup:
                    if cleanup.errno != errno.ENOENT:
                        raise StateRefused("pre-publication cleanup failed") from error
            raise
        finally:
            if temp_fd is not None:
                os.close(temp_fd)

    @staticmethod
    def _check_staged_file(root_fd: int, name: str, retained_fd: int, data: bytes) -> None:
        retained = os.fstat(retained_fd)
        if not stat.S_ISREG(retained.st_mode) or retained.st_nlink != 1 or retained.st_uid not in {0, os.geteuid()} or stat.S_IMODE(retained.st_mode) != 0o600 or retained.st_size != len(data):
            raise StateRefused("staged state file custody changed")
        try:
            named_fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=root_fd)
        except OSError as error:
            raise StateRefused("staged state pathname was substituted") from error
        try:
            named = os.fstat(named_fd)
            if (named.st_dev, named.st_ino) != (retained.st_dev, retained.st_ino):
                raise StateRefused("staged state pathname was substituted")
            if os.pread(retained_fd, MAX_STATE_BYTES + 1, 0) != data:
                raise StateRefused("staged state bytes were substituted")
        finally:
            os.close(named_fd)

    def read(self, name: str) -> dict[str, Any]:
        name = self._name(name)
        root_fd = self._check_root()
        fd = os.open(
            name,
            os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
            dir_fd=root_fd,
        )
        try:
            metadata = os.fstat(fd)
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_uid not in {0, os.geteuid()} or stat.S_IMODE(metadata.st_mode) & 0o077 or metadata.st_size > MAX_STATE_BYTES:
                raise RecoveryRequired("durable state leaf is not a bounded regular file")
            data = bytearray()
            while len(data) <= MAX_STATE_BYTES:
                chunk = os.read(fd, min(65536, MAX_STATE_BYTES + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            if len(data) > MAX_STATE_BYTES:
                raise RecoveryRequired("durable state grew beyond its limit")
            return _strict_object(bytes(data), MAX_STATE_BYTES)
        except ManifestRefused as error:
            raise RecoveryRequired("durable state is malformed") from error
        finally:
            os.close(fd)
