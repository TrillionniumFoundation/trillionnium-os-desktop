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
import os
import re
import stat
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
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

    try:
        value = json.loads(text, object_pairs_hook=pairs, parse_constant=constant)
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
        if current_version <= 0 or _HASH.fullmatch(current_image_sha256) is None:
            raise StateRefused("current image identity is invalid")
        if max_boot_failures <= 0 or max_boot_failures > 16:
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
        if stable_seconds < MIN_STABLE_HEALTH_SECONDS:
            raise StateRefused("health window is not stable for the required duration")
        if _HASH.fullmatch(health_receipt_sha256) is None:
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
    """Private, descriptor-confined state with one inode-bound coordinator.

    This is a cooperating-writer mechanism, not a sandbox against root or
    arbitrary same-UID code. Existing authority paths are never repaired.
    """

    LOCK_NAME = ".coordinator.lock"
    MAX_PATH_BYTES = 4096
    MAX_PATH_COMPONENTS = 64
    MAX_STATE_DEPTH = 32
    MAX_STATE_ITEMS = 4096
    MAX_STATE_STRING_BYTES = 4096
    MAX_STATE_INTEGER = (1 << 63) - 1
    _BASENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")

    def __init__(self, root: Path):
        self._root_fd: int | None = None
        self._lease_fd: int | None = None
        self._lease_identity: tuple[int, int] | None = None
        self._pending: tuple[str, str] | None = None
        self._invalid = False
        try:
            raw = os.fspath(root)
            if not isinstance(raw, str):
                raise ValueError("root must be a text path")
            parts = raw.split("/")
            if (
                not raw.startswith("/")
                or len(raw.encode("utf-8")) > self.MAX_PATH_BYTES
                or len(parts) - 1 > self.MAX_PATH_COMPONENTS
                or any(part in {"", ".", ".."} for part in parts[1:])
                or any(ord(c) < 32 or ord(c) == 127 or c == "\\" for c in raw)
            ):
                raise ValueError("noncanonical root")
            self.root = Path(raw)
            self._components = tuple(parts[1:])
            self._root_fd = self._open_root()
            metadata = os.fstat(self._root_fd)
            self._identity = (metadata.st_dev, metadata.st_ino)
        except (OSError, TypeError, ValueError, UnicodeError) as error:
            self.close()
            raise StateRefused("state root cannot be acquired safely") from error

    @staticmethod
    def _trusted_directory(metadata: os.stat_result, *, private: bool) -> bool:
        mode = stat.S_IMODE(metadata.st_mode)
        if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid not in {0, os.geteuid()}:
            return False
        if private:
            return mode == 0o700
        # A root-owned sticky temporary directory is an explicit host-test
        # exception. Attacker-owned or ordinary writable ancestors are refused.
        return not mode & 0o022 or (
            metadata.st_uid == 0 and bool(mode & stat.S_ISVTX)
        )

    def _open_root(self) -> int:
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        directory = os.open("/", flags)
        try:
            if not self._trusted_directory(os.fstat(directory), private=False):
                raise StateRefused("untrusted state ancestor")
            for index, component in enumerate(self._components):
                child = os.open(component, flags, dir_fd=directory)
                os.close(directory)
                directory = child
                private = index == len(self._components) - 1
                if not self._trusted_directory(os.fstat(directory), private=private):
                    raise StateRefused("unsafe state directory owner or mode")
            result, directory = directory, -1
            return result
        finally:
            if directory >= 0:
                os.close(directory)

    @staticmethod
    def _private_regular(metadata: os.stat_result) -> bool:
        return (
            stat.S_ISREG(metadata.st_mode)
            and metadata.st_nlink == 1
            and stat.S_IMODE(metadata.st_mode) == 0o600
            and metadata.st_uid in {0, os.geteuid()}
        )

    def close(self) -> None:
        if self._lease_fd is not None:
            fd, self._lease_fd = self._lease_fd, None
            self._lease_identity = None
            os.close(fd)  # Closing the retained FD releases the advisory lease.
        if self._root_fd is not None:
            fd, self._root_fd = self._root_fd, None
            os.close(fd)

    def __enter__(self) -> "AtomicStateStore":
        try:
            self.acquire()
        except BaseException:
            self.close()
            raise
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _check_root(self) -> int:
        fd = self._root_fd
        if fd is None or self._invalid:
            raise StateRefused("state store is closed or its custody was lost")
        reopened: int | None = None
        try:
            current = os.fstat(fd)
            if (
                (current.st_dev, current.st_ino) != self._identity
                or not self._trusted_directory(current, private=True)
            ):
                raise StateRefused("retained state root identity or mode changed")
            reopened = self._open_root()
            observed = os.fstat(reopened)
            if (observed.st_dev, observed.st_ino) != self._identity:
                raise StateRefused("state pathname no longer identifies the retained root")
            return fd
        except (OSError, StateRefused) as error:
            self._invalid = True
            raise StateRefused("state directory custody was lost") from error
        finally:
            if reopened is not None:
                os.close(reopened)

    def _check_lease(self) -> int:
        root_fd = self._check_root()
        if self._lease_fd is None:
            raise CoordinatorBusy("exclusive coordinator lease is required")
        try:
            retained = os.fstat(self._lease_fd)
            named = os.stat(self.LOCK_NAME, dir_fd=root_fd, follow_symlinks=False)
            for metadata in (retained, named):
                if (
                    not self._private_regular(metadata)
                    or metadata.st_size != 0
                    or (metadata.st_dev, metadata.st_ino) != self._lease_identity
                ):
                    raise StateRefused("coordinator lease identity or metadata changed")
        except (OSError, StateRefused) as error:
            self._invalid = True
            raise StateRefused("coordinator lease custody was lost") from error
        return root_fd

    def acquire(self) -> None:
        root_fd = self._check_root()
        if self._lease_fd is not None:
            raise CoordinatorBusy("coordinator lease is already held")
        fd: int | None = None
        created = False
        try:
            flags = os.O_RDWR | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC
            try:
                fd = os.open(self.LOCK_NAME, flags | os.O_CREAT | os.O_EXCL,
                             0o600, dir_fd=root_fd)
                created = True
            except FileExistsError:
                fd = os.open(self.LOCK_NAME, flags, dir_fd=root_fd)
            # Only a just-created inode may have its umask-restricted mode set.
            # Never chmod a pre-existing lock before admitting its metadata.
            if created:
                os.fchmod(fd, 0o600)
            metadata = os.fstat(fd)
            if not self._private_regular(metadata) or metadata.st_size != 0:
                raise StateRefused("coordinator lock is not a private empty single-link file")
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self._lease_fd, fd = fd, None
            self._lease_identity = (metadata.st_dev, metadata.st_ino)
            self._check_lease()
        except (OSError, StateRefused) as error:
            if self._lease_fd is not None:
                os.close(self._lease_fd)
                self._lease_fd = None
                self._lease_identity = None
            if isinstance(error, OSError) and error.errno in {errno.EACCES, errno.EAGAIN}:
                raise CoordinatorBusy("coordinator lease is unavailable") from error
            raise StateRefused("coordinator lock cannot be acquired safely") from error
        finally:
            if fd is not None:
                os.close(fd)

    @classmethod
    def _name(cls, name: str) -> str:
        # No normalization: hidden lock/staging names, traversal, NULs, Unicode,
        # trailing separators and dot aliases never become a state basename.
        if not isinstance(name, str) or cls._BASENAME.fullmatch(name) is None:
            raise StateRefused("state name must be one canonical non-reserved basename")
        return name

    @classmethod
    def _validate_state(cls, value: object) -> None:
        if type(value) is not dict:
            raise StateRefused("state payload must be an object")
        pending = [(value, 1)]
        items = 0
        text_bytes = 0
        while pending:
            current, depth = pending.pop()
            items += 1
            if depth > cls.MAX_STATE_DEPTH or items > cls.MAX_STATE_ITEMS:
                raise StateRefused("state depth or aggregate item limit exceeded")
            kind = type(current)
            if kind is dict:
                if items + len(pending) + 2 * len(current) > cls.MAX_STATE_ITEMS:
                    raise StateRefused("state aggregate item limit exceeded")
                if any(type(key) is not str for key in current):
                    raise StateRefused("state keys must be strings")
                pending.extend((key, depth + 1) for key in current)
                pending.extend((item, depth + 1) for item in current.values())
            elif kind is list:
                if items + len(pending) + len(current) > cls.MAX_STATE_ITEMS:
                    raise StateRefused("state aggregate item limit exceeded")
                pending.extend((item, depth + 1) for item in current)
            elif kind is str:
                try:
                    length = len(current.encode("utf-8"))
                except UnicodeError as error:
                    raise StateRefused("state text is not valid UTF-8") from error
                text_bytes += length
                if length > cls.MAX_STATE_STRING_BYTES or text_bytes > MAX_STATE_BYTES:
                    raise StateRefused("state text exceeds its byte limit")
            elif kind is int:
                if not -cls.MAX_STATE_INTEGER <= current <= cls.MAX_STATE_INTEGER:
                    raise StateRefused("state integer exceeds its bound")
            elif current is not None and kind is not bool:
                raise StateRefused("state contains a non-integer or non-JSON value")
            if items + len(pending) > cls.MAX_STATE_ITEMS:
                raise StateRefused("state aggregate item limit exceeded")

    @classmethod
    def _decode_state(cls, data: bytes) -> dict[str, Any]:
        try:
            value = _strict_object(data, MAX_STATE_BYTES)
            cls._validate_state(value)
            return value
        except (ManifestRefused, StateRefused, RecursionError) as error:
            raise RecoveryRequired("durable state is malformed or exceeds its bounds") from error

    def _existing_leaf(self, root_fd: int, name: str) -> None:
        try:
            metadata = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            return
        if not self._private_regular(metadata) or metadata.st_size > MAX_STATE_BYTES:
            raise StateRefused("existing state leaf has unsafe metadata")

    def write(
        self,
        name: str,
        value: dict[str, Any],
        *,
        fault: Callable[[str], None] | None = None,
    ) -> str:
        root_fd = self._check_lease()
        if self._pending is not None:
            raise RecoveryRequired("prior publication requires explicit reconciliation")
        name = self._name(name)
        self._validate_state(value)
        try:
            data = _canonical(value)
        except (TypeError, ValueError, RecursionError) as error:
            raise StateRefused("state cannot be canonicalized") from error
        if not data or len(data) > MAX_STATE_BYTES:
            raise StateRefused("state payload is empty or over limit")
        digest = hashlib.sha256(data).hexdigest()
        self._existing_leaf(root_fd, name)
        temp = f".{name}.{os.getpid()}.{digest[:16]}.tmp"
        temp_fd: int | None = None
        temp_identity: tuple[int, int] | None = None
        replaced = False
        try:
            if fault:
                fault("before_temp_create")
            self._check_lease()
            temp_fd = os.open(
                temp,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
                dir_fd=root_fd,
            )
            os.fchmod(temp_fd, 0o600)
            metadata = os.fstat(temp_fd)
            temp_identity = (metadata.st_dev, metadata.st_ino)
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
            self._check_lease()
            self._existing_leaf(root_fd, name)
            staged = os.stat(temp, dir_fd=root_fd, follow_symlinks=False)
            if (
                not self._private_regular(staged)
                or (staged.st_dev, staged.st_ino) != temp_identity
                or staged.st_size != len(data)
            ):
                raise StateRefused("staged state identity changed")
            # Latch before entering the publication syscall so interruption
            # between its return and Python bookkeeping cannot permit a retry.
            replaced = True
            os.replace(temp, name, src_dir_fd=root_fd, dst_dir_fd=root_fd)
            if fault:
                fault("after_atomic_replace")
            os.fsync(root_fd)
            if fault:
                fault("after_directory_fsync")
            self._check_lease()
            published = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            if (
                not self._private_regular(published)
                or (published.st_dev, published.st_ino) != temp_identity
                or published.st_size != len(data)
            ):
                raise StateRefused("published state identity changed")
            return digest
        except BaseException as error:
            if replaced:
                self._pending = (name, digest)
                raise PublicationIndeterminate(digest, error) from error
            # Never delete a collision, another writer's file, or a substituted
            # staging inode after exclusive creation failed.
            if temp_identity is not None:
                try:
                    current = os.stat(temp, dir_fd=root_fd, follow_symlinks=False)
                    if (current.st_dev, current.st_ino) == temp_identity:
                        os.unlink(temp, dir_fd=root_fd)
                except FileNotFoundError:
                    pass
                except OSError as cleanup:
                    raise StateRefused("pre-publication cleanup failed") from cleanup
            raise
        finally:
            if temp_fd is not None:
                os.close(temp_fd)

    def _read_bytes(self, name: str, *, sync: bool = False) -> bytes:
        root_fd = self._check_root()
        fd: int | None = None
        try:
            fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
                         dir_fd=root_fd)
            metadata = os.fstat(fd)
            if not self._private_regular(metadata) or metadata.st_size > MAX_STATE_BYTES:
                raise RecoveryRequired("durable state leaf is not a private bounded regular file")
            data = bytearray()
            while len(data) <= MAX_STATE_BYTES:
                chunk = os.read(fd, min(65536, MAX_STATE_BYTES + 1 - len(data)))
                if not chunk:
                    break
                data.extend(chunk)
            if len(data) > MAX_STATE_BYTES:
                raise RecoveryRequired("durable state grew beyond its limit")
            if sync:
                os.fsync(fd)
                os.fsync(root_fd)
            after = os.fstat(fd)
            named = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            identity = (metadata.st_dev, metadata.st_ino)
            if (
                not self._private_regular(after) or not self._private_regular(named)
                or (named.st_dev, named.st_ino) != identity
                or after.st_size != len(data) or after.st_size != metadata.st_size
                or after.st_mtime_ns != metadata.st_mtime_ns
                or after.st_ctime_ns != metadata.st_ctime_ns
            ):
                raise RecoveryRequired("durable state changed during observation")
            self._check_root()
            return bytes(data)
        except OSError as error:
            raise RecoveryRequired("durable state could not be read safely") from error
        finally:
            if fd is not None:
                os.close(fd)

    def read(self, name: str) -> dict[str, Any]:
        data = self._read_bytes(self._name(name))
        return self._decode_state(data)

    def reconcile_publication(self, name: str, *, expected_sha256: str) -> dict[str, Any]:
        """Inspect/sync exact pending bytes; never rewrite or replay an update.

        This resolves only this live handle's local publication uncertainty.
        Persisted update/boot/journal reconciliation remains a separate protocol.
        """
        self._check_lease()
        name = self._name(name)
        if self._pending != (name, expected_sha256):
            raise RecoveryRequired("reconciliation does not match the pending publication")
        data = self._read_bytes(name, sync=True)
        if hashlib.sha256(data).hexdigest() != expected_sha256:
            raise RecoveryRequired("pending publication bytes do not match")
        value = self._decode_state(data)
        self._check_lease()
        self._pending = None
        return value
