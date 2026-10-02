"""Fail-closed S11 A/B update and recovery mechanism candidate.

The module verifies detached signatures against externally approved roots,
streams complete images into private regular-file inactive slots, and owns a
bounded state machine. It does not download, sign, activate a bootloader or claim
an installed update. Ambiguous publication requires durable reconciliation.
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
import subprocess
import threading
import time
from dataclasses import dataclass
from enum import Enum
from functools import wraps
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
MAX_SIGNATURE_BYTES = 64 * 1024
MAX_PUBLIC_KEY_BYTES = 64 * 1024
SIGNATURE_DOMAIN = b"trillionnium.desktop.update-manifest-signature.v1\x00"
OPENSSL_ENV = {"PATH": "/usr/bin:/bin", "OPENSSL_CONF": "/dev/null", "LC_ALL": "C"}
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


class _ProcessThreadOwner:
    """Authority stays in its creating process and thread, including after fork."""

    _ownership_error = StateRefused

    def _bind_owner(self) -> None:
        self._owner_pid = os.getpid()
        self._owner_thread = threading.current_thread()

    def _check_owner(self) -> None:
        if os.getpid() != self._owner_pid or threading.current_thread() is not self._owner_thread:
            raise self._ownership_error("update authority requires its creating process and thread")


def _owner_guard(method):
    @wraps(method)
    def invoke(self, *args, **kwargs):
        self._check_owner()
        return method(self, *args, **kwargs)
    return invoke


class _OwnedDescriptor:
    """One private FD owner; undelivered helper returns have descriptor-only GC.

    This is deliberately not an int subclass. Explicit close detaches ownership
    before the syscall, so later GC cannot close another owner's reused number.
    """

    __slots__ = ("_fd",)

    def __init__(self):
        # Construct before acquiring any FD. A Python constructor-entry or first
        # field-assignment interruption must not strand an already opened integer.
        self._fd: int | None = None

    def fileno(self) -> int:
        descriptor = self._fd
        return -1 if descriptor is None else descriptor

    def __index__(self) -> int:
        return self.fileno()

    def close(self) -> None:
        descriptor = getattr(self, "_fd", None)
        self._fd = None
        if descriptor is not None:
            os.close(descriptor)

    def __del__(self) -> None:
        try:
            self.close()
        except BaseException:
            pass


def _close_owned_descriptors(owned: list[int | _OwnedDescriptor]) -> None:
    """Detach before each close; attempt every owned FD once even on interruption.

    A failed close may already have released its number. Retrying that integer
    can close another owner's newly allocated descriptor, so it is never retried.
    """
    first_error: BaseException | None = None
    while owned:
        descriptor = owned.pop()
        try:
            if isinstance(descriptor, _OwnedDescriptor):
                descriptor.close()
            else:
                os.close(descriptor)
        except BaseException as error:
            if first_error is None:
                first_error = error
    if first_error is not None:
        raise first_error


def _open_directory_components(components: tuple[str, ...], label: str) -> _OwnedDescriptor:
    owned = [_OwnedDescriptor()]
    try:
        owned[0]._fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        for component in components:
            if component in {".", ".."}:
                raise StateRefused(f"{label} path contains traversal")
            next_directory = _OwnedDescriptor()
            owned.append(next_directory)
            next_directory._fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                         dir_fd=owned[0])
            # The new directory is owned before the previous one is detached.
            # If close releases the old number and then raises, finally closes
            # only the next directory, never that old, potentially reused number.
            previous = owned.pop(0)
            previous.close()
        return owned.pop()
    finally:
        _close_owned_descriptors(owned)


def _sealed_snapshot(name: str, data: bytes) -> _OwnedDescriptor:
    """Immutable inherited verifier input, never a mutable filesystem pathname."""
    descriptor = _OwnedDescriptor()
    try:
        descriptor._fd = os.memfd_create(name, os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        view = memoryview(data)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                raise OSError("verifier snapshot write made no progress")
            view = view[written:]
        fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS,
                    fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor
    except BaseException:
        descriptor.close()
        raise


class PublicationIndeterminate(UpdateError):
    """The final state pathname may already contain the intended bytes."""

    def __init__(self, digest: str, cause: BaseException):
        super().__init__(
            "atomic state replacement was attempted; reconcile its outcome before retry"
        )
        self.digest = digest
        self.cause = cause


class ImagePublicationIndeterminate(PublicationIndeterminate):
    def __init__(self, slot: str, digest: str, cause: BaseException):
        super().__init__(digest, cause)
        self.target_slot = slot


def _open_image(path: Path) -> _OwnedDescriptor:
    """Acquire one bounded regular image without following any component."""
    absolute = Path(path).absolute()
    owned: list[_OwnedDescriptor] = []
    try:
        owned.append(_open_directory_components(absolute.parts[1:-1], "image"))
        image = _OwnedDescriptor()
        owned.append(image)
        image._fd = os.open(absolute.name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=owned[0])
        _image_metadata(owned[-1])
        directory = owned.pop(0)
        directory.close()
        # Transfer the image only after its directory close succeeds. A directory
        # close interruption must not abandon the still-owned image descriptor.
        return owned.pop()
    except OSError as error:
        raise StateRefused("image path is absent or unsafe") from error
    finally:
        _close_owned_descriptors(owned)


def _image_metadata(descriptor: int) -> os.stat_result:
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_size <= 0 or metadata.st_size > MAX_IMAGE_BYTES:
        raise StateRefused("image must be a nonempty bounded regular file with one hard link")
    return metadata


def _image_digest(descriptor: int, *, expected_bytes: int | None = None) -> tuple[str, int]:
    before = _image_metadata(descriptor)
    if expected_bytes is not None and before.st_size != expected_bytes:
        raise StateRefused("whole-image length does not match the manifest")
    digest = hashlib.sha256()
    offset = 0
    while offset < before.st_size:
        chunk = os.pread(descriptor, min(1024 * 1024, before.st_size - offset), offset)
        if not chunk:
            raise StateRefused("image was truncated during complete verification")
        digest.update(chunk)
        offset += len(chunk)
    after = _image_metadata(descriptor)
    if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
        raise StateRefused("image identity or bytes changed during complete verification")
    return digest.hexdigest(), offset


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
    if value > ((1 << 63) - 1 if maximum is None else maximum):
        raise ManifestRefused(f"{label} exceeds its bound")
    return value


def manifest_signing_bytes(payload: bytes | str) -> bytes:
    """Exact versioned signing preimage; signature digest is envelope metadata."""
    value = _strict_object(payload, MAX_MANIFEST_BYTES)
    if set(value) != MANIFEST_FIELDS or value["schema"] != MANIFEST_SCHEMA:
        raise ManifestRefused("signed manifest fields or schema are invalid")
    return SIGNATURE_DOMAIN + _canonical({key: value[key] for key in sorted(value) if key != "signature_sha256"})


@dataclass(frozen=True)
class UpdateTrustRoot:
    """Approved configuration supplied outside the manifest and repository.

    This object does not approve a key: the protected provisioning authority
    supplies the signer identity, PEM digest, validity and minimum version.
    """

    signer_id: str
    public_key_pem: bytes
    expected_public_key_sha256: str
    minimum_version: int
    valid_from_unix: int
    valid_until_unix: int
    revoked: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.signer_id, str) or _ID.fullmatch(self.signer_id) is None:
            raise ManifestRefused("approved signer identity is invalid")
        if not isinstance(self.public_key_pem, bytes) or not self.public_key_pem or len(self.public_key_pem) > MAX_PUBLIC_KEY_BYTES:
            raise ManifestRefused("approved public key is empty or over limit")
        _hash(self.expected_public_key_sha256, "approved public key")
        if hashlib.sha256(self.public_key_pem).hexdigest() != self.expected_public_key_sha256:
            raise ManifestRefused("public key does not match the externally pinned trust root")
        _positive_int(self.minimum_version, "approved minimum_version")
        _positive_int(self.valid_from_unix, "approved valid_from_unix")
        _positive_int(self.valid_until_unix, "approved valid_until_unix")
        if self.valid_until_unix <= self.valid_from_unix or type(self.revoked) is not bool:
            raise ManifestRefused("approved trust-root validity or revocation is invalid")


@dataclass(frozen=True)
class SignatureAdmission:
    signer_id: str
    public_key_sha256: str
    signature_sha256: str
    signing_preimage_sha256: str
    trust_policy_sha256: str
    minimum_version: int
    verified_unix: int
    _seal: object

    def __post_init__(self) -> None:
        if self._seal is not _SEAL:
            raise ManifestRefused("signature admission was not verified")


class ExternalUpdateSignatureVerifier(_ProcessThreadOwner):
    """Offline verification with approved roots; no signing or network path."""

    _ownership_error = ManifestRefused

    def __init__(self, roots: tuple[UpdateTrustRoot, ...]):
        self._bind_owner()
        if type(roots) is not tuple or not roots or len(roots) > 32 or any(type(root) is not UpdateTrustRoot for root in roots):
            raise ManifestRefused("one bounded externally supplied trust-root set is required")
        if len({root.signer_id for root in roots}) != len(roots):
            raise ManifestRefused("approved signer identities are duplicated")
        self._roots = {root.signer_id: root for root in roots}
        policy = [{"signer_id": root.signer_id, "public_key_sha256": root.expected_public_key_sha256,
                   "minimum_version": root.minimum_version, "valid_from_unix": root.valid_from_unix,
                   "valid_until_unix": root.valid_until_unix, "revoked": root.revoked}
                  for root in sorted(roots, key=lambda root: root.signer_id)]
        self.policy_sha256 = hashlib.sha256(_canonical({"roots": policy})).hexdigest()

    @_owner_guard
    def _root(self, signer_id: str, now_unix: int) -> UpdateTrustRoot:
        _positive_int(now_unix, "now_unix")
        if not isinstance(signer_id, str) or _ID.fullmatch(signer_id) is None:
            raise ManifestRefused("manifest signer identity is invalid")
        root = self._roots.get(signer_id)
        if root is None or root.revoked:
            raise ManifestRefused("manifest signer is unknown or revoked")
        if now_unix < root.valid_from_unix or now_unix >= root.valid_until_unix:
            raise ManifestRefused("approved signer is outside its validity window")
        return root

    @_owner_guard
    def verify(self, payload: bytes | str, signature: bytes, *, now_unix: int) -> SignatureAdmission:
        value = _strict_object(payload, MAX_MANIFEST_BYTES)
        preimage = manifest_signing_bytes(payload)
        root = self._root(value["signer_id"], now_unix)
        if not isinstance(signature, bytes) or not signature or len(signature) > MAX_SIGNATURE_BYTES:
            raise ManifestRefused("detached update signature is empty or over limit")
        signature_digest = hashlib.sha256(signature).hexdigest()
        if value["signature_sha256"] != signature_digest:
            raise ManifestRefused("detached update signature digest does not match the envelope")
        # No caller command, verifier callback, private key or repository key is
        # accepted. The only process is the system offline OpenSSL verifier.
        executable = Path("/usr/bin/openssl")
        try:
            metadata = executable.lstat()
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != 0 or stat.S_IMODE(metadata.st_mode) & 0o022:
                raise ManifestRefused("system signature verifier executable is not trusted")
            snapshot_owners = []
            try:
                for name, data in (("update-preimage", preimage), ("update-signature", signature),
                                   ("update-public-key", root.public_key_pem)):
                    snapshot_owners.append(_sealed_snapshot(name, data))
                snapshots = tuple(snapshot.fileno() for snapshot in snapshot_owners)
                manifest_fd, signature_fd, key_fd = snapshots
                result = subprocess.run([str(executable), "dgst", "-sha256", "-verify", f"/proc/self/fd/{key_fd}",
                                         "-signature", f"/proc/self/fd/{signature_fd}", f"/proc/self/fd/{manifest_fd}"],
                                        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL, env=OPENSSL_ENV,
                                        pass_fds=tuple(snapshots), timeout=15, check=False)
            finally:
                _close_owned_descriptors(snapshot_owners)
        except (OSError, AttributeError, subprocess.TimeoutExpired) as error:
            raise ManifestRefused("offline update signature verification is unavailable") from error
        if result.returncode != 0:
            raise ManifestRefused("detached update signature verification failed")
        return SignatureAdmission(root.signer_id, root.expected_public_key_sha256, signature_digest,
                                  hashlib.sha256(preimage).hexdigest(), self.policy_sha256,
                                  root.minimum_version, now_unix, _SEAL)

    @_owner_guard
    def revalidate(self, admission: SignatureAdmission, *, now_unix: int) -> None:
        if admission._seal is not _SEAL or admission.trust_policy_sha256 != self.policy_sha256:
            raise ManifestRefused("signature admission belongs to a stale trust policy")
        root = self._root(admission.signer_id, now_unix)
        if now_unix < admission.verified_unix:
            raise ManifestRefused("update clock regressed after signature admission")
        if root.expected_public_key_sha256 != admission.public_key_sha256:
            raise ManifestRefused("signature admission trust root was replaced")


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
    signature_admission: SignatureAdmission
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
    operation_id: str
    journal_identity: tuple[int, int, int, int]
    _seal: object

    def __post_init__(self) -> None:
        if self._seal is not _SEAL:
            raise StateRefused("reconciliation fact was not issued by the journal adapter")


@dataclass(frozen=True)
class DispatchBinding:
    manifest_sha256: str
    sequence: int
    operation_id: str
    operation: str
    target_slot: str
    image_sha256: str


@dataclass(frozen=True)
class ImageStageReceipt:
    target_slot: str
    image_sha256: str
    image_bytes: int
    manifest_sha256: str
    signature_sha256: str
    production_activation_enabled: bool = False


@dataclass(frozen=True)
class RecoveryDecision:
    operator_uid: int
    manifest_sha256: str
    sequence: int
    source_image_sha256: str
    action: str = "rollback_only_no_replay"


class UpdateCoordinator(_ProcessThreadOwner):
    """Single-operation, fail-closed A/B update coordinator."""

    def __init__(
        self,
        *,
        active_slot: str,
        current_version: int,
        current_image_sha256: str,
        max_boot_failures: int = MAX_BOOT_FAILURES,
        signature_verifier: ExternalUpdateSignatureVerifier | None = None,
        protected_rollback_floor: int | None = None,
        clock: Callable[[], int] | None = None,
        recovery_operator_uids: frozenset[int] = frozenset(),
        journal_authority: "DurableUpdateJournal | None" = None,
    ) -> None:
        self._bind_owner()
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
        if signature_verifier is not None and type(signature_verifier) is not ExternalUpdateSignatureVerifier:
            raise StateRefused("signature verifier configuration is invalid")
        if signature_verifier is not None:
            signature_verifier._check_owner()
        floor = current_version if protected_rollback_floor is None else protected_rollback_floor
        if type(floor) is not int or floor <= 0 or floor > current_version:
            raise StateRefused("externally protected rollback floor is invalid")
        self.protected_rollback_floor = floor
        self._signature_verifier = signature_verifier
        self._clock = clock if clock is not None else lambda: int(time.time())
        if not isinstance(recovery_operator_uids, frozenset) or any(type(uid) is not int or uid < 0 for uid in recovery_operator_uids):
            raise StateRefused("approved recovery operator UID set is invalid")
        self._recovery_operator_uids = recovery_operator_uids
        if journal_authority is not None and type(journal_authority) is not DurableUpdateJournal:
            raise StateRefused("durable journal authority configuration is invalid")
        if journal_authority is not None:
            journal_authority._check_owner()
        self._journal_authority = journal_authority
        self.phase = Phase.IDLE
        self.sequence = 0
        self.boot_failures = 0
        self._ticket: ManifestTicket | None = None
        self._effect_reconciliation_required = False
        self._image_publication_pending: ManifestTicket | None = None
        self._pending_dispatch: DispatchBinding | None = None
        self._reconciliation_fact: JournalReconciliation | None = None
        self._health_permit: HealthPermit | None = None

    @property
    @_owner_guard
    def effect_reconciliation_required(self) -> bool:
        return self._effect_reconciliation_required

    @_owner_guard
    def _require(self, ticket: ManifestTicket, *phases: Phase) -> UpdateManifest:
        if (
            ticket._seal is not _SEAL
            or self._ticket is not ticket
            or ticket.sequence != self.sequence
            or self.phase not in phases
        ):
            raise StateRefused("ticket, sequence, or phase is stale")
        return ticket.manifest

    @_owner_guard
    def verify_manifest(
        self, payload: bytes | str, *, now_unix: int, signature: bytes | None = None
    ) -> ManifestTicket:
        if self.phase not in {Phase.IDLE, Phase.COMMITTED}:
            raise StateRefused("another update transaction is active")
        if self._effect_reconciliation_required:
            raise StateRefused("possible prior dispatch requires reconciliation")
        if self._signature_verifier is None:
            raise ManifestRefused("update admission is disabled without externally approved trust roots")
        now_unix = self._trusted_now(now_unix)
        manifest = UpdateManifest.parse(
            payload,
            now_unix=now_unix,
            active_slot=self.active_slot,
            current_version=self.current_version,
            current_image_sha256=self.current_image_sha256,
        )
        admission = self._signature_verifier.verify(payload, signature, now_unix=now_unix)
        if manifest.rollback_floor < max(self.protected_rollback_floor, admission.minimum_version):
            raise ManifestRefused("manifest weakens the protected rollback floor")
        sequence = self.sequence + 1
        if sequence > (1 << 63) - 1:
            raise StateRefused("update sequence exhausted")
        self.sequence = sequence
        ticket = ManifestTicket(manifest, sequence, admission, _SEAL)
        self._ticket = ticket
        self._health_permit = None
        self._image_publication_pending = None
        self.phase = Phase.VERIFIED
        self.boot_failures = 0
        return ticket

    @_owner_guard
    def _trusted_now(self, requested: int) -> int:
        _positive_int(requested, "now_unix")
        now = _positive_int(self._clock(), "trusted clock")
        if abs(requested - now) > 5:
            raise ManifestRefused("caller time does not match the configured trusted clock")
        return now

    @_owner_guard
    def _revalidate_admission(self, ticket: ManifestTicket, *, now_unix: int) -> None:
        if self._signature_verifier is None:
            raise ManifestRefused("update admission is disabled")
        now_unix = self._trusted_now(now_unix)
        self._signature_verifier.revalidate(ticket.signature_admission, now_unix=now_unix)
        if now_unix >= ticket.manifest.expires_unix:
            raise ManifestRefused("admitted manifest expired before staging or boot")
        if ticket.manifest.rollback_floor < self.protected_rollback_floor:
            raise ManifestRefused("admitted manifest weakens the protected rollback floor")

    @_owner_guard
    def stage_image(self, ticket: ManifestTicket, image: bytes, *, now_unix: int) -> None:
        manifest = self._require(ticket, Phase.VERIFIED)
        self._revalidate_admission(ticket, now_unix=now_unix)
        if not isinstance(image, bytes):
            raise StateRefused("image must be immutable bytes")
        if len(image) != manifest.target_image_bytes:
            raise StateRefused("whole-image length does not match the manifest")
        if hashlib.sha256(image).hexdigest() != manifest.target_image_sha256:
            raise StateRefused("whole-image digest does not match the manifest")
        self.phase = Phase.STAGED

    @_owner_guard
    def arm_first_boot(self, ticket: ManifestTicket, *, now_unix: int) -> None:
        self._require(ticket, Phase.STAGED)
        self._revalidate_admission(ticket, now_unix=now_unix)
        self._health_permit = None
        self.phase = Phase.BOOT_PENDING

    @_owner_guard
    def stage_image_file(
        self, ticket: ManifestTicket, image_path: Path, slot_store: "ImageSlotStore", *,
        now_unix: int, fault: Callable[[str], None] | None = None,
    ) -> ImageStageReceipt:
        manifest = self._require(ticket, Phase.VERIFIED)
        self._revalidate_admission(ticket, now_unix=now_unix)
        if type(slot_store) is not ImageSlotStore or slot_store.active_slot != self.active_slot:
            raise StateRefused("slot store does not bind the coordinator active slot")
        descriptor = _open_image(image_path)
        publication_attempted = False
        try:
            digest, _ = _image_digest(descriptor, expected_bytes=manifest.target_image_bytes)
            if digest != manifest.target_image_sha256:
                raise StateRefused("whole-image digest does not match the manifest")
            def authorize_publication() -> None:
                self._require(ticket, Phase.VERIFIED)
                self._revalidate_admission(ticket, now_unix=self._clock())
            def record_publication_attempt() -> None:
                nonlocal publication_attempted
                # Record intent before entering the replace call, including the
                # window after that call returns and before this method resumes.
                publication_attempted = True
                self._image_publication_pending = ticket
                self.phase = Phase.RECOVERY_REQUIRED
            try:
                receipt = slot_store._publish_verified_image(ticket, descriptor, authorize_publication,
                                                             record_publication_attempt, fault=fault)
            except ImagePublicationIndeterminate:
                self._image_publication_pending = ticket
                self.phase = Phase.RECOVERY_REQUIRED
                raise
            except BaseException as error:
                if self._image_publication_pending is ticket:
                    self.phase = Phase.RECOVERY_REQUIRED
                    raise ImagePublicationIndeterminate(manifest.target_slot, manifest.target_image_sha256, error) from error
                raise
        finally:
            try:
                _close_owned_descriptors([descriptor])
            except BaseException as error:
                if publication_attempted or self._image_publication_pending is ticket:
                    self._image_publication_pending = ticket
                    self.phase = Phase.RECOVERY_REQUIRED
                    raise ImagePublicationIndeterminate(manifest.target_slot, manifest.target_image_sha256, error) from error
                raise
        self.phase = Phase.STAGED
        self._image_publication_pending = None
        return receipt

    @_owner_guard
    def request_operator_rollback(self, ticket: ManifestTicket, source_image_path: Path) -> RecoveryDecision:
        """Authenticate a local operator and authorize rollback without replay.

        This transitions policy only; it neither clears a possible-effect latch
        nor changes bootloader state, deletes receipts or writes an image.
        """
        manifest = self._require(ticket, Phase.VERIFIED, Phase.STAGED, Phase.BOOT_PENDING,
                                 Phase.HEALTH_PENDING, Phase.ROLLBACK_PENDING, Phase.RECOVERY_REQUIRED)
        uid = os.geteuid()
        if uid not in self._recovery_operator_uids:
            raise StateRefused("local recovery operator is not externally approved")
        if self._effect_reconciliation_required:
            raise StateRefused("possible effect requires journal reconciliation before operator rollback")
        descriptor = _open_image(source_image_path)
        try:
            digest, _ = _image_digest(descriptor)
        finally:
            descriptor.close()
        if digest != manifest.source_image_sha256 or manifest.source_version < self.protected_rollback_floor:
            raise RecoveryRequired("operator rollback source does not match protected source identity")
        self.phase = Phase.ROLLBACK_PENDING
        self._health_permit = None
        return RecoveryDecision(uid, manifest.manifest_sha256, ticket.sequence, digest)

    @_owner_guard
    def reconcile_image_publication(self, ticket: ManifestTicket, slot_store: "ImageSlotStore", *, now_unix: int) -> ImageStageReceipt:
        self._require(ticket, Phase.RECOVERY_REQUIRED)
        if self._image_publication_pending is not ticket:
            raise StateRefused("no indeterminate image publication belongs to this transaction")
        if self._effect_reconciliation_required:
            raise StateRefused("possible effect requires journal reconciliation before image reconciliation")
        self._revalidate_admission(ticket, now_unix=now_unix)
        if type(slot_store) is not ImageSlotStore or slot_store.active_slot != self.active_slot:
            raise StateRefused("slot store does not bind the coordinator active slot")
        receipt = slot_store.reconcile_image(ticket)
        self._revalidate_admission(ticket, now_unix=self._clock())
        self._image_publication_pending = None
        self.phase = Phase.STAGED
        return receipt

    @_owner_guard
    def record_booted_image(
        self, ticket: ManifestTicket, *, slot: str, image_sha256: str
    ) -> None:
        manifest = self._require(ticket, Phase.BOOT_PENDING)
        self._health_permit = None
        if slot != manifest.target_slot or image_sha256 != manifest.target_image_sha256:
            self.phase = Phase.RECOVERY_REQUIRED
            raise RecoveryRequired("booted slot identity does not match the staged image")
        self.phase = Phase.HEALTH_PENDING

    @_owner_guard
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
        permit = HealthPermit(
            manifest.manifest_sha256,
            ticket.sequence,
            health_receipt_sha256,
            _SEAL,
        )
        self._health_permit = permit
        return permit

    @_owner_guard
    def commit(self, permit: HealthPermit) -> None:
        ticket = self._ticket
        if (
            permit._seal is not _SEAL
            or self._health_permit is not permit
            or ticket is None
            or self.phase != Phase.HEALTH_PENDING
            or permit.sequence != ticket.sequence
            or permit.manifest_sha256 != ticket.manifest.manifest_sha256
        ):
            raise StateRefused("commit permit is stale or unrelated")
        manifest = ticket.manifest
        self._revalidate_admission(ticket, now_unix=self._clock())
        self.active_slot = manifest.target_slot
        self.current_version = manifest.target_version
        self.current_image_sha256 = manifest.target_image_sha256
        self.protected_rollback_floor = max(self.protected_rollback_floor, manifest.rollback_floor)
        self.phase = Phase.COMMITTED
        self.boot_failures = 0
        self._ticket = None
        self._health_permit = None
        self._image_publication_pending = None

    @_owner_guard
    def record_boot_failure(self, ticket: ManifestTicket) -> Phase:
        self._require(ticket, Phase.BOOT_PENDING, Phase.HEALTH_PENDING)
        self._health_permit = None
        self.boot_failures += 1
        if self.boot_failures >= self.max_boot_failures:
            self.phase = Phase.ROLLBACK_PENDING
        else:
            self.phase = Phase.BOOT_PENDING
        return self.phase

    @_owner_guard
    def rollback(self, ticket: ManifestTicket, *, recovered_image_sha256: str) -> None:
        manifest = self._require(ticket, Phase.ROLLBACK_PENDING)
        if recovered_image_sha256 != manifest.source_image_sha256 or manifest.source_version < self.protected_rollback_floor:
            self.phase = Phase.RECOVERY_REQUIRED
            raise RecoveryRequired("rollback did not restore the exact source image")
        self.phase = Phase.IDLE
        self.boot_failures = 0
        self._ticket = None
        self._health_permit = None
        self._image_publication_pending = None

    @_owner_guard
    def mark_possible_dispatch(self, ticket: ManifestTicket) -> DispatchBinding:
        self._require(
            ticket,
            Phase.VERIFIED,
            Phase.STAGED,
            Phase.BOOT_PENDING,
            Phase.HEALTH_PENDING,
        )
        if self._effect_reconciliation_required:
            raise StateRefused("a possible dispatch already requires reconciliation")
        binding = DispatchBinding(ticket.manifest.manifest_sha256, ticket.sequence, secrets.token_hex(32),
                                  self.phase.value, ticket.manifest.target_slot, ticket.manifest.target_image_sha256)
        self._pending_dispatch = binding
        self._health_permit = None
        self._effect_reconciliation_required = True
        self.phase = Phase.RECOVERY_REQUIRED
        return binding

    @_owner_guard
    def verify_journal_reconciliation(self, ticket: ManifestTicket) -> JournalReconciliation:
        self._require(ticket, Phase.RECOVERY_REQUIRED)
        binding = self._pending_dispatch
        if not self._effect_reconciliation_required or binding is None or self._journal_authority is None:
            raise StateRefused("reconciliation requires a configured durable journal authority and pending operation")
        digest, status, identity = self._journal_authority.confirm_dispatch(binding)
        fact = JournalReconciliation(ticket.manifest.manifest_sha256, ticket.sequence, digest, status,
                                     binding.operation_id, identity, _SEAL)
        self._reconciliation_fact = fact
        return fact

    @_owner_guard
    def reconcile_possible_dispatch(self, fact: JournalReconciliation) -> None:
        ticket = self._ticket
        if (
            fact._seal is not _SEAL
            or ticket is None
            or not self._effect_reconciliation_required
            or fact.sequence != ticket.sequence
            or fact.manifest_sha256 != ticket.manifest.manifest_sha256
            or self._reconciliation_fact is not fact
            or self._pending_dispatch is None
            or fact.operation_id != self._pending_dispatch.operation_id
            or self._journal_authority is None
        ):
            raise StateRefused("journal reconciliation is stale or unrelated")
        digest, status, identity = self._journal_authority.confirm_dispatch(self._pending_dispatch)
        if (digest, status, identity) != (fact.journal_record_sha256, fact.status, fact.journal_identity):
            raise StateRefused("durable journal fact changed before reconciliation")
        self._effect_reconciliation_required = False
        self._pending_dispatch = None
        self._reconciliation_fact = None
        self.phase = Phase.ROLLBACK_PENDING

    @_owner_guard
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


class AtomicStateStore(_ProcessThreadOwner):
    """Descriptor-pinned private state publication with an exclusive lease."""

    def __init__(self, root: Path):
        self._bind_owner()
        self._root_fd: _OwnedDescriptor | None = None
        self._lease_fd: int | None = None
        self.root = Path(root).absolute()
        try:
            self._root_fd = self._open_root()
        except OSError as error:
            raise StateRefused("state root cannot be opened without following links") from error
        metadata = os.fstat(self._root_fd)
        mode = stat.S_IMODE(metadata.st_mode)
        if not stat.S_ISDIR(metadata.st_mode) or mode & 0o077:
            self._release_descriptors()
            raise StateRefused("state root must be a private 0700-style directory")
        if metadata.st_uid not in {0, os.geteuid()}:
            self._release_descriptors()
            raise StateRefused("state root owner is not trusted")
        self._identity = (metadata.st_dev, metadata.st_ino)

    @_owner_guard
    def _open_root(self) -> _OwnedDescriptor:
        return _open_directory_components(self.root.parts[1:], "state root")

    def close(self) -> None:
        # fork copies share the same flock open-file description. LOCK_UN in
        # either process would release the parent's lease. Closing only this
        # process's descriptors releases the lease after the last copy closes.
        if os.getpid() == self._owner_pid:
            self._check_owner()
        self._release_descriptors()

    def _release_descriptors(self) -> None:
        # Clear ownership before close, including partially constructed objects.
        # A stale integer must never close a subsequently reused descriptor.
        lease, root = getattr(self, "_lease_fd", None), getattr(self, "_root_fd", None)
        self._lease_fd = self._root_fd = None
        _close_owned_descriptors([descriptor for descriptor in (root, lease) if descriptor is not None])

    def __del__(self) -> None:
        # GC may run in another thread or in a fork child. Cleanup holds no
        # authority and never commits, reconciles, writes or explicitly unlocks.
        try:
            self._release_descriptors()
        except BaseException:
            pass

    @_owner_guard
    def __enter__(self) -> "AtomicStateStore":
        self.acquire()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @_owner_guard
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
            current_fd.close()
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
        # Borrow the integer only while this store retains its sole FD owner.
        return fd.fileno()

    @_owner_guard
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
            self._lease_fd = fd
        except BaseException as error:
            self._lease_fd = None
            _close_owned_descriptors([fd])
            if isinstance(error, OSError) and error.errno in {errno.EACCES, errno.EAGAIN}:
                raise CoordinatorBusy("another update coordinator holds the lease") from error
            raise

    @staticmethod
    def _name(name: str) -> str:
        if not isinstance(name, str) or name.startswith(".") or "\x00" in name or "\\" in name:
            raise StateRefused("state name is reserved or malformed")
        path = PurePosixPath(name)
        if path.is_absolute() or len(path.parts) != 1 or path.parts[0] in {"", ".", ".."} or path.as_posix() != name:
            raise StateRefused("state name must be one safe basename")
        return path.parts[0]

    @_owner_guard
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
        publication_attempted = False
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
            publication_attempted = True
            os.replace(temp, name, src_dir_fd=root_fd, dst_dir_fd=root_fd)
            if fault:
                fault("after_atomic_replace")
            self._check_staged_file(root_fd, name, temp_fd, data)
            os.fsync(root_fd)
            if fault:
                fault("after_directory_fsync")
            self._check_root()
            self._check_staged_file(root_fd, name, temp_fd, data)
            return digest
        except BaseException as error:
            if publication_attempted:
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
                try:
                    _close_owned_descriptors([temp_fd])
                except BaseException as error:
                    if publication_attempted:
                        raise PublicationIndeterminate(digest, error) from error
                    raise

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

    @_owner_guard
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

class ImageSlotStore(AtomicStateStore):
    """Leased regular-file A/B staging; no block device or bootloader API.

    The caller provisions the private root and exact active-slot file. Slot
    authority and the protected floor must come from the installed adapter;
    this source mechanism never discovers or activates production slots.
    """

    def __init__(self, root: Path, *, active_slot: str):
        if active_slot not in {"A", "B"}:
            raise StateRefused("active image slot is invalid")
        super().__init__(root)
        self._active_slot = active_slot

    @property
    @_owner_guard
    def active_slot(self) -> str:
        return self._active_slot

    @_owner_guard
    def write(self, name: str, value: dict[str, Any], *, fault: Callable[[str], None] | None = None) -> str:
        if name in {"slot-A.img", "slot-B.img"}:
            raise StateRefused("image slots cannot be overwritten through the state API")
        return super().write(name, value, fault=fault)

    @_owner_guard
    def _open_slot(self, root_fd: int, name: str) -> _OwnedDescriptor:
        descriptor = _OwnedDescriptor()
        try:
            descriptor._fd = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=root_fd)
        except OSError as error:
            raise StateRefused("image slot pathname is absent or unsafe") from error
        try:
            self._private_image(descriptor)
            return descriptor
        except BaseException:
            descriptor.close()
            raise

    @staticmethod
    def _private_image(descriptor: int) -> os.stat_result:
        metadata = _image_metadata(descriptor)
        if metadata.st_uid not in {0, os.geteuid()} or stat.S_IMODE(metadata.st_mode) != 0o600:
            raise StateRefused("image slot custody is not private and trusted")
        return metadata

    @_owner_guard
    def _bound_image(self, root_fd: int, name: str, descriptor: int, digest: str, size: int | None = None) -> None:
        retained = self._private_image(descriptor)
        named_fd = self._open_slot(root_fd, name)
        try:
            named = os.fstat(named_fd)
            if (named.st_dev, named.st_ino) != (retained.st_dev, retained.st_ino):
                raise StateRefused("image slot pathname was substituted")
            actual, _ = _image_digest(descriptor, expected_bytes=size)
            if actual != digest:
                raise StateRefused("complete image slot bytes were substituted")
            final = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
            if (final.st_dev, final.st_ino) != (retained.st_dev, retained.st_ino):
                raise StateRefused("image slot pathname changed during verification")
            self._private_image(descriptor)
        finally:
            named_fd.close()

    @_owner_guard
    def _inactive_identity(self, root_fd: int, name: str) -> tuple[int, int] | None:
        try:
            os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        except FileNotFoundError:
            return None
        descriptor = self._open_slot(root_fd, name)
        try:
            metadata = os.fstat(descriptor)
            return metadata.st_dev, metadata.st_ino
        finally:
            descriptor.close()

    @_owner_guard
    def _require_image_ticket(self, ticket: ManifestTicket) -> UpdateManifest:
        if self._lease_fd is None:
            raise CoordinatorBusy("exclusive coordinator lease is required for image staging")
        if not isinstance(ticket, ManifestTicket) or ticket._seal is not _SEAL or ticket.signature_admission._seal is not _SEAL:
            raise StateRefused("image staging requires an admitted signed manifest")
        if ticket.manifest.target_slot == self.active_slot:
            raise StateRefused("active image slot cannot be staged")
        return ticket.manifest

    @staticmethod
    def _receipt(manifest: UpdateManifest) -> ImageStageReceipt:
        return ImageStageReceipt(manifest.target_slot, manifest.target_image_sha256, manifest.target_image_bytes,
                                 manifest.manifest_sha256, manifest.signature_sha256)

    @_owner_guard
    def _publish_verified_image(self, ticket: ManifestTicket, source_fd: int,
                                authorize_publication: Callable[[], None],
                                record_publication_attempt: Callable[[], None], *,
                                fault: Callable[[str], None] | None = None) -> ImageStageReceipt:
        manifest = self._require_image_ticket(ticket)
        root_fd = self._check_root()
        active_name = f"slot-{self.active_slot}.img"
        target_name = f"slot-{manifest.target_slot}.img"
        active_fd = self._open_slot(root_fd, active_name)
        temp = f".{target_name}.{os.getpid()}.{secrets.token_hex(16)}.tmp"
        temp_fd: int | None = None
        temp_identity: tuple[int, int] | None = None
        publication_attempted = False
        try:
            self._bound_image(root_fd, active_name, active_fd, manifest.source_image_sha256)
            initial_target = self._inactive_identity(root_fd, target_name)
            actual, _ = _image_digest(source_fd, expected_bytes=manifest.target_image_bytes)
            if actual != manifest.target_image_sha256:
                raise StateRefused("complete candidate image was substituted before staging")
            authorize_publication()
            if fault:
                fault("before_temp_create")
            self._check_root()
            authorize_publication()
            temp_fd = os.open(temp, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=root_fd)
            os.fchmod(temp_fd, 0o600)
            metadata = os.fstat(temp_fd)
            temp_identity = metadata.st_dev, metadata.st_ino
            if fault:
                fault("after_temp_create")
            source_before = _image_metadata(source_fd)
            if source_before.st_size != manifest.target_image_bytes:
                raise StateRefused("complete candidate image length changed before staging")
            digest = hashlib.sha256()
            offset = 0
            while offset < manifest.target_image_bytes:
                chunk = os.pread(source_fd, min(1024 * 1024, manifest.target_image_bytes - offset), offset)
                if not chunk:
                    raise StateRefused("candidate image was truncated during staging")
                digest.update(chunk)
                written = 0
                while written < len(chunk):
                    count = os.write(temp_fd, chunk[written:])
                    if count <= 0:
                        raise StateRefused("image staging made no write progress")
                    written += count
                offset += len(chunk)
            source_after = _image_metadata(source_fd)
            if (source_before.st_dev, source_before.st_ino, source_before.st_size, source_before.st_mtime_ns, source_before.st_ctime_ns) != (source_after.st_dev, source_after.st_ino, source_after.st_size, source_after.st_mtime_ns, source_after.st_ctime_ns) or digest.hexdigest() != manifest.target_image_sha256:
                raise StateRefused("complete candidate image changed during staging")
            if fault:
                fault("after_complete_write")
            os.fsync(temp_fd)
            if fault:
                fault("after_file_fsync")
            authorize_publication()
            self._check_root()
            self._bound_image(root_fd, active_name, active_fd, manifest.source_image_sha256)
            if self._inactive_identity(root_fd, target_name) != initial_target:
                raise StateRefused("inactive slot pathname changed before publication")
            self._bound_image(root_fd, temp, temp_fd, manifest.target_image_sha256, manifest.target_image_bytes)
            authorize_publication()
            publication_attempted = True
            record_publication_attempt()
            os.replace(temp, target_name, src_dir_fd=root_fd, dst_dir_fd=root_fd)
            if fault:
                fault("after_atomic_replace")
            self._bound_image(root_fd, target_name, temp_fd, manifest.target_image_sha256, manifest.target_image_bytes)
            os.fsync(root_fd)
            if fault:
                fault("after_directory_fsync")
            self._check_root()
            self._bound_image(root_fd, active_name, active_fd, manifest.source_image_sha256)
            self._bound_image(root_fd, target_name, temp_fd, manifest.target_image_sha256, manifest.target_image_bytes)
            return self._receipt(manifest)
        except BaseException as error:
            if publication_attempted:
                raise ImagePublicationIndeterminate(manifest.target_slot, manifest.target_image_sha256, error) from error
            if temp_identity is not None:
                try:
                    metadata = os.stat(temp, dir_fd=root_fd, follow_symlinks=False)
                    if (metadata.st_dev, metadata.st_ino) == temp_identity:
                        os.unlink(temp, dir_fd=root_fd)
                except FileNotFoundError:
                    pass
            raise
        finally:
            try:
                _close_owned_descriptors([descriptor for descriptor in (temp_fd, active_fd) if descriptor is not None])
            except BaseException as error:
                if publication_attempted:
                    raise ImagePublicationIndeterminate(manifest.target_slot, manifest.target_image_sha256, error) from error
                raise

    @_owner_guard
    def reconcile_image(self, ticket: ManifestTicket) -> ImageStageReceipt:
        """Confirm and fsync an existing publication; never rewrite or replay."""
        manifest = self._require_image_ticket(ticket)
        root_fd = self._check_root()
        active_name = f"slot-{self.active_slot}.img"
        target_name = f"slot-{manifest.target_slot}.img"
        active_fd = self._open_slot(root_fd, active_name)
        target_fd: _OwnedDescriptor | None = None
        try:
            target_fd = self._open_slot(root_fd, target_name)
            self._bound_image(root_fd, active_name, active_fd, manifest.source_image_sha256)
            self._bound_image(root_fd, target_name, target_fd, manifest.target_image_sha256, manifest.target_image_bytes)
            os.fsync(target_fd)
            os.fsync(root_fd)
            self._check_root()
            self._bound_image(root_fd, active_name, active_fd, manifest.source_image_sha256)
            self._bound_image(root_fd, target_name, target_fd, manifest.target_image_sha256, manifest.target_image_bytes)
            return self._receipt(manifest)
        except BaseException as error:
            raise ImagePublicationIndeterminate(manifest.target_slot, manifest.target_image_sha256, error) from error
        finally:
            try:
                _close_owned_descriptors([descriptor for descriptor in (target_fd, active_fd) if descriptor is not None])
            except BaseException as error:
                raise ImagePublicationIndeterminate(manifest.target_slot, manifest.target_image_sha256, error) from error


class DurableUpdateJournal(AtomicStateStore):
    """Explicitly provisioned private journal authority, never caller facts.

    A trusted dispatch adapter writes closed operation records into this root.
    The coordinator only reads and syncs them under the retained lease. Installed
    receipt-chain/monotonic authority must provision and protect this root.
    """

    @_owner_guard
    def confirm_dispatch(self, binding: DispatchBinding) -> tuple[str, str, tuple[int, int, int, int]]:
        if self._lease_fd is None:
            raise CoordinatorBusy("durable journal reconciliation requires its exclusive lease")
        if not isinstance(binding, DispatchBinding) or _HASH.fullmatch(binding.operation_id) is None:
            raise StateRefused("pending dispatch binding is invalid")
        root_fd = self._check_root()
        name = f"dispatch-{binding.operation_id}.json"
        try:
            descriptor = os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=root_fd)
        except OSError as error:
            raise StateRefused("authoritative operation journal is absent or unsafe") from error
        try:
            before = os.fstat(descriptor)
            self._record_custody(before)
            data = bytearray()
            while len(data) <= MAX_STATE_BYTES:
                chunk = os.pread(descriptor, min(65536, MAX_STATE_BYTES + 1 - len(data)), len(data))
                if not chunk:
                    break
                data.extend(chunk)
            if len(data) != before.st_size or len(data) > MAX_STATE_BYTES:
                raise StateRefused("complete journal record length changed or exceeded its bound")
            try:
                record = _strict_object(bytes(data), MAX_STATE_BYTES)
            except ManifestRefused as error:
                raise StateRefused("authoritative journal record is malformed") from error
            expected = {"schema": "trillionnium.desktop.update-dispatch-journal.v1",
                        "manifest_sha256": binding.manifest_sha256, "sequence": binding.sequence,
                        "operation_id": binding.operation_id, "operation": binding.operation,
                        "target_slot": binding.target_slot, "image_sha256": binding.image_sha256}
            if set(record) != set(expected) | {"status"}:
                raise StateRefused("authoritative journal record field set is not exact")
            if any(type(record[key]) is not type(value) or record[key] != value for key, value in expected.items()):
                raise StateRefused("journal does not bind this manifest, sequence and dispatched operation")
            if not isinstance(record["status"], str) or record["status"] not in {"terminal", "indeterminate"}:
                raise StateRefused("journal has no terminal or indeterminate operation fact")
            self._check_record(root_fd, name, descriptor, before)
            os.fsync(descriptor)
            os.fsync(root_fd)
            self._check_root()
            self._check_record(root_fd, name, descriptor, before)
            return hashlib.sha256(data).hexdigest(), record["status"], (*self._identity, before.st_dev, before.st_ino)
        finally:
            os.close(descriptor)

    @staticmethod
    def _record_custody(metadata: os.stat_result) -> None:
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_uid not in {0, os.geteuid()} or stat.S_IMODE(metadata.st_mode) != 0o600 or not 0 < metadata.st_size <= MAX_STATE_BYTES:
            raise StateRefused("journal record is not a private bounded one-link regular authority file")

    @_owner_guard
    def _check_record(self, root_fd: int, name: str, descriptor: int, before: os.stat_result) -> None:
        after = os.fstat(descriptor)
        self._record_custody(after)
        if (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns):
            raise StateRefused("journal identity or bytes changed during verification")
        named = os.stat(name, dir_fd=root_fd, follow_symlinks=False)
        self._record_custody(named)
        if (named.st_dev, named.st_ino) != (before.st_dev, before.st_ino):
            raise StateRefused("authoritative journal pathname was replaced")
