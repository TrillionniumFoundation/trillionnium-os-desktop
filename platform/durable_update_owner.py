"""Durable, fail-closed owner for signed regular-file update staging.

This composes the concrete S11 mechanisms. It does not observe a boot, accept
caller health assertions, activate a bootloader, or recover an interrupted owner.
"""
from __future__ import annotations

import hashlib
import importlib.util
import os
import re
import secrets
import stat
import sys
import threading
import time
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Callable

# The platform directory shares a name with Python's stdlib module. Keep one
# bundled concrete type identity without changing sys.path.
_MODULE = "hepta_update_recovery_v1"
if _MODULE not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_MODULE, Path(__file__).with_name("update_recovery.py"))
    if _spec is None or _spec.loader is None:
        raise RuntimeError("bundled S11 implementation is unavailable")
    recovery = importlib.util.module_from_spec(_spec)
    sys.modules[_MODULE] = recovery
    _spec.loader.exec_module(recovery)
else:
    recovery = sys.modules[_MODULE]

SCHEMA = "trillionnium.desktop.durable-update-owner.v1"
EVENT_SCHEMA = "trillionnium.desktop.durable-update-event.v1"
RECOVERY_SCHEMA = "trillionnium.desktop.durable-update-recovery.v1"
MAX_EVENTS = 256
RECOVERY_FILE = "update-recovery-required.json"
_EVENT = re.compile(r"update-event-([0-9]{6})\.json\Z", re.ASCII)
_HASH = re.compile(r"[0-9a-f]{64}\Z", re.ASCII)
_SEAL = object()
_ZERO = "0" * 64
_EVENT_FIELDS = {"schema", "sequence", "previous_sha256", "owner_id", "kind", "phase", "observed_unix", "configuration", "operation", "stage_receipt", "production_activation_enabled", "bootloader_effect_performed"}
_CONFIG_FIELDS = {"active_slot", "current_version", "current_image_sha256", "protected_rollback_floor", "trust_policy_sha256", "state_root_identity", "slot_root_identity"}
_OP_FIELDS = {"operation_id", "owner_id", "ticket_sequence", "manifest", "signature_admission"}
_ADMISSION_FIELDS = {"signer_id", "public_key_sha256", "signature_sha256", "signing_preimage_sha256", "trust_policy_sha256", "minimum_version", "verified_unix"}
_STAGE_FIELDS = {"target_slot", "image_sha256", "image_bytes", "manifest_sha256", "signature_sha256", "production_activation_enabled"}
_MARKER_FIELDS = {"schema", "phase", "reason", "state_root_identity", "slot_root_identity", "history_count", "last_event_sha256", "operation_id", "production_activation_enabled", "bootloader_effect_performed"}
_PHASES = {"owner_open": "idle", "manifest_verified": "verified", "stage_intent": "stage_intent", "stage_completed": "staged", "arm_intent": "arm_intent", "boot_policy_armed": "boot_pending", "owner_clean": "closed"}
_NEXT = {None: {"owner_open"}, "owner_open": {"manifest_verified", "owner_clean"}, "manifest_verified": {"stage_intent"}, "stage_intent": {"stage_completed"}, "stage_completed": {"arm_intent"}, "arm_intent": {"boot_policy_armed"}, "boot_policy_armed": set(), "owner_clean": {"owner_open"}}


class DurableUpdateError(recovery.StateRefused):
    """A source owner operation or its durable identity was refused."""


class DurableRecoveryRequired(recovery.RecoveryRequired):
    """Evidence must be retained; this API never clears or replays it."""


class DurableResultUnavailable(DurableUpdateError):
    """Local durable completion is known; delivery to the caller is unknown."""


class _ScanRecord:
    """One shared fd owner, including an interrupted transfer into a scan."""

    def __init__(self, name: str, descriptor: int):
        self.name = name
        self.metadata = None
        self._descriptors = [descriptor]

    @property
    def descriptor(self) -> int:
        return self._descriptors[0]

    def close(self) -> None:
        if self._descriptors:
            # The same record can reach both finally blocks if adoption is
            # interrupted. Detach its sole integer before the actual close;
            # a close that takes effect then raises must never be retried.
            descriptor = self._descriptors.pop()
            os.close(descriptor)


def _fields(value: object, fields: set[str]) -> dict:
    if type(value) is not dict or set(value) != fields:
        raise DurableRecoveryRequired("durable update record fields are not closed")
    return value


def _hash(value: object) -> str:
    if type(value) is not str or _HASH.fullmatch(value) is None:
        raise DurableRecoveryRequired("durable update digest or identity is invalid")
    return value


def _integer(value: object, *, minimum: int = 1, maximum: int = (1 << 63) - 1) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise DurableRecoveryRequired("durable update integer is outside its bound")
    return value


def _same(left: object, right: object) -> bool:
    # Canonical bytes preserve bool/int differences in nested record fields.
    return recovery._canonical(left) == recovery._canonical(right)


def _identity(value: object) -> list[int]:
    if type(value) is not list or len(value) != 2:
        raise DurableRecoveryRequired("durable directory identity is invalid")
    for item in value:
        _integer(item, minimum=0)
    return value


def _authority_guard(method):
    @wraps(method)
    def invoke(self, *args, **kwargs):
        self._check_owner()
        if self._busy:
            raise DurableUpdateError("durable owner callbacks cannot reenter an operation")
        self._busy = True
        try:
            return method(self, *args, **kwargs)
        finally:
            self._busy = False
    return invoke


class _IssuedFact:
    def __getattribute__(self, name: str):
        if not name.startswith("_"):
            if os.getpid() != object.__getattribute__(self, "_owner_pid") or threading.current_thread() is not object.__getattribute__(self, "_owner_thread"):
                raise DurableUpdateError("issued update fact requires its creating process and thread")
        return object.__getattribute__(self, name)

    def __post_init__(self):
        if self._seal is not _SEAL:
            raise DurableUpdateError("update fact was not issued by a durable owner")


@dataclass(frozen=True)
class DurableUpdateOperation(_IssuedFact):
    operation_id: str
    manifest_sha256: str
    signature_sha256: str
    _issuer: object
    _owner_pid: int
    _owner_thread: object
    _seal: object


@dataclass(frozen=True)
class DurableUpdateResult(_IssuedFact):
    operation_id: str
    manifest_sha256: str
    event_sequence: int
    event_sha256: str
    phase: str
    target_slot: str
    image_sha256: str
    image_bytes: int
    slot_root_identity: tuple[int, int]
    production_activation_enabled: bool
    bootloader_effect_performed: bool
    _issuer: object
    _owner_pid: int
    _owner_thread: object
    _seal: object


class DurableUpdateOwner:
    """One durable owner session, with no recovery or caller health authority.

    State and slot roots are externally provisioned private directories. The
    signer verifier must be the exact bundled concrete type. All configuration,
    clock and optional fault callbacks are trusted in-process configuration.
    """

    def __init__(self, state_root: Path, slot_root: Path, *, active_slot: str,
                 current_version: int, current_image_sha256: str,
                 signature_verifier=None, protected_rollback_floor: int | None = None,
                 clock: Callable[[], int] | None = None):
        self._owner_pid = os.getpid()
        self._owner_thread = threading.current_thread()
        self._busy = False
        self._state = self._slots = None
        self._closed = False
        self._recovering = False
        self._history: list[tuple[dict, str]] = []
        self._record_identities: dict[str, tuple] = {}
        self._operation = self._ticket = None
        self._results: dict[int, DurableUpdateResult] = {}
        self._issuer = object()
        self._owner_id = secrets.token_hex(32)
        self._phase = "idle"
        self._last_unix = 0
        self._clock_source = clock if clock is not None else lambda: int(time.time())
        self._coordinator = recovery.UpdateCoordinator(active_slot=active_slot, current_version=current_version,
            current_image_sha256=current_image_sha256, signature_verifier=signature_verifier,
            protected_rollback_floor=protected_rollback_floor, clock=self._guarded_clock)
        try:
            self._state = recovery.AtomicStateStore(state_root)
            self._state.acquire()
            self._slots = recovery.ImageSlotStore(slot_root, active_slot=active_slot)
            self._slots.acquire()
            if self._state._identity == self._slots._identity:
                raise DurableUpdateError("state and image slot roots must be distinct")
            self._configuration = {"active_slot": active_slot, "current_version": current_version,
                "current_image_sha256": current_image_sha256,
                "protected_rollback_floor": self._coordinator.protected_rollback_floor,
                "trust_policy_sha256": None if signature_verifier is None else signature_verifier.policy_sha256,
                "state_root_identity": list(self._state._identity), "slot_root_identity": list(self._slots._identity)}
            try:
                history, marker = self._load_history()
                self._history = history
                if history:
                    self._last_unix = history[-1][0]["observed_unix"]
                if marker or (history and history[-1][0]["kind"] != "owner_clean"):
                    self._mark_recovery("unclean_or_unfinished_owner")
                    return
                if history and not _same(history[-1][0]["configuration"], self._configuration):
                    self._mark_recovery("configuration_changed")
                    return
                self._verify_active()
                self._append("owner_open", None, None)
            except BaseException:
                self._mark_recovery("history_or_custody_failure")
                raise
        except BaseException:
            self._closed = True
            self._release_descriptors()
            raise

    def _check_owner(self) -> None:
        if os.getpid() != self._owner_pid or threading.current_thread() is not self._owner_thread:
            raise DurableUpdateError("durable update owner requires its creating process and thread")
        if self._closed:
            raise DurableUpdateError("durable update owner is closed")
        self._state._check_root()
        self._slots._check_root()

    def _guarded_clock(self) -> int:
        if os.getpid() != self._owner_pid or threading.current_thread() is not self._owner_thread:
            raise DurableUpdateError("update clock requires its creating process and thread")
        now = recovery._positive_int(self._clock_source(), "configured trusted clock")
        if now < self._last_unix:
            self._mark_recovery("trusted_clock_regressed")
            raise DurableRecoveryRequired("trusted update clock regressed; authority remains refused")
        self._last_unix = now
        return now

    def _release_descriptors(self) -> None:
        # No explicit unlock or durable write, even in GC/foreign threads/fork.
        state, slots = self._state, self._slots
        self._state = self._slots = None
        try:
            if slots is not None:
                slots._release_descriptors()
        finally:
            if state is not None:
                state._release_descriptors()

    def __del__(self):
        try:
            self._release_descriptors()
        except BaseException:
            pass

    def __enter__(self):
        self._check_owner()
        return self

    def __exit__(self, kind, _value, _traceback):
        if kind is None:
            self.close()
        else:
            # Exceptions never acknowledge a clean session.
            self._closed = True
            self._release_descriptors()

    @property
    def phase(self) -> str:
        self._check_owner()
        return self._phase

    def _metadata(self, metadata):
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_nlink != 1 or metadata.st_uid not in {0, os.geteuid()} or stat.S_IMODE(metadata.st_mode) != 0o600 or not 0 < metadata.st_size <= recovery.MAX_STATE_BYTES:
            raise DurableRecoveryRequired("durable owner record custody is unsafe")
        return metadata.st_dev, metadata.st_ino, metadata.st_size, metadata.st_mtime_ns, metadata.st_ctime_ns

    def _read(self, name: str, *, retained: list | None = None) -> tuple[dict, str]:
        root = self._state._check_root()
        record = _ScanRecord(name, os.open(name, os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=root))
        try:
            descriptor = record.descriptor
            before = self._metadata(os.fstat(descriptor))
            if name in self._record_identities and before != self._record_identities[name]:
                raise DurableRecoveryRequired("retained durable record identity or bytes changed")
            data = bytearray()
            while len(data) <= recovery.MAX_STATE_BYTES:
                chunk = os.pread(descriptor, min(65536, recovery.MAX_STATE_BYTES + 1 - len(data)), len(data))
                if not chunk:
                    break
                data.extend(chunk)
            if len(data) != before[2] or len(data) > recovery.MAX_STATE_BYTES:
                raise DurableRecoveryRequired("durable owner record length changed")
            value = recovery._strict_object(bytes(data), recovery.MAX_STATE_BYTES)
            if bytes(data) != recovery._canonical(value):
                raise DurableRecoveryRequired("durable owner records must have canonical bytes")
            os.fsync(descriptor)
            os.fsync(root)
            self._state._check_root()
            if self._metadata(os.fstat(descriptor)) != before or self._metadata(os.stat(name, dir_fd=root, follow_symlinks=False)) != before:
                raise DurableRecoveryRequired("durable owner record was substituted during readback")
            self._record_identities[name] = before
            if retained is not None:
                record.metadata = before
                retained.append(record)
                record = None
            return value, hashlib.sha256(data).hexdigest()
        finally:
            if record is not None:
                record.close()

    def _validate_event(self, event: dict, previous: dict | None, digest: str, sequence: int) -> None:
        _fields(event, _EVENT_FIELDS)
        if event["schema"] != EVENT_SCHEMA or event["sequence"] != sequence or type(event["sequence"]) is not int or event["previous_sha256"] != digest:
            raise DurableRecoveryRequired("durable event sequence or chain binding changed")
        _hash(event["owner_id"])
        kind = event["kind"]
        if type(kind) is not str or kind not in _PHASES or event["phase"] != _PHASES[kind] or kind not in _NEXT[None if previous is None else previous["kind"]]:
            raise DurableRecoveryRequired("durable update transition is invalid")
        _integer(event["observed_unix"])
        if previous is not None and event["observed_unix"] < previous["observed_unix"]:
            raise DurableRecoveryRequired("durable trusted clock regressed in the history")
        if event["production_activation_enabled"] is not False or event["bootloader_effect_performed"] is not False:
            raise DurableRecoveryRequired("durable source claim was promoted")
        config = _fields(event["configuration"], _CONFIG_FIELDS)
        _identity(config["state_root_identity"]); _identity(config["slot_root_identity"])
        _hash(config["current_image_sha256"])
        _integer(config["current_version"]); _integer(config["protected_rollback_floor"])
        if config["active_slot"] not in {"A", "B"} or config["protected_rollback_floor"] > config["current_version"]:
            raise DurableRecoveryRequired("durable running image identity is invalid")
        if config["trust_policy_sha256"] is not None:
            _hash(config["trust_policy_sha256"])
        if config["state_root_identity"] != list(self._state._identity) or config["slot_root_identity"] != list(self._slots._identity):
            raise DurableRecoveryRequired("durable state and slot root identities differ")
        if previous is not None:
            if not _same(config, previous["configuration"]):
                raise DurableRecoveryRequired("configuration changed within the durable history")
            if kind != "owner_open" and event["owner_id"] != previous["owner_id"]:
                raise DurableRecoveryRequired("durable operation changed its issuing owner")
            if kind == "owner_open" and event["owner_id"] == previous["owner_id"]:
                raise DurableRecoveryRequired("durable owner identity was reused")
        operation = event["operation"]
        if kind in {"owner_open", "owner_clean"}:
            if operation is not None or event["stage_receipt"] is not None:
                raise DurableRecoveryRequired("a clean owner cannot hide an unfinished update")
            return
        operation = _fields(operation, _OP_FIELDS)
        _hash(operation["operation_id"])
        if operation["owner_id"] != event["owner_id"] or operation["ticket_sequence"] != 1 or type(operation["ticket_sequence"]) is not int:
            raise DurableRecoveryRequired("operation is not bound to the issuing session")
        admission = _fields(operation["signature_admission"], _ADMISSION_FIELDS)
        for key in ("public_key_sha256", "signature_sha256", "signing_preimage_sha256", "trust_policy_sha256"):
            _hash(admission[key])
        _integer(admission["minimum_version"]); _integer(admission["verified_unix"])
        if admission["verified_unix"] > event["observed_unix"]:
            raise DurableRecoveryRequired("durable signature admission occurred after the event")
        manifest = recovery.UpdateManifest.parse(recovery._canonical(operation["manifest"]), now_unix=admission["verified_unix"],
            active_slot=config["active_slot"], current_version=config["current_version"], current_image_sha256=config["current_image_sha256"])
        if admission["signer_id"] != manifest.signer_id or admission["signature_sha256"] != manifest.signature_sha256 or admission["trust_policy_sha256"] != config["trust_policy_sha256"] or manifest.rollback_floor < max(config["protected_rollback_floor"], admission["minimum_version"]):
            raise DurableRecoveryRequired("durable signature admission differs from the operation")
        if admission["signing_preimage_sha256"] != hashlib.sha256(recovery.manifest_signing_bytes(recovery._canonical(operation["manifest"]))).hexdigest():
            raise DurableRecoveryRequired("durable signing preimage differs from the manifest")
        if previous is not None and kind != "manifest_verified" and not _same(operation, previous["operation"]):
            raise DurableRecoveryRequired("durable update operation changed between phases")
        receipt = event["stage_receipt"]
        if kind in {"manifest_verified", "stage_intent"}:
            if receipt is not None:
                raise DurableRecoveryRequired("durable intent cannot claim a staging result")
        else:
            _fields(receipt, _STAGE_FIELDS)
            expected = {"target_slot": manifest.target_slot, "image_sha256": manifest.target_image_sha256,
                "image_bytes": manifest.target_image_bytes, "manifest_sha256": manifest.manifest_sha256,
                "signature_sha256": manifest.signature_sha256, "production_activation_enabled": False}
            if not _same(receipt, expected):
                raise DurableRecoveryRequired("durable staging receipt differs from the complete manifest")

    def _load_history(self) -> tuple[list[tuple[dict, str]], dict | None]:
        retained = []
        try:
            return self._scan_history(retained)
        finally:
            # Detach all integers first. A close can take effect before raising;
            # never retry its number after another file has reused it.
            owned, retained[:] = list(retained), []
            first_error = None
            for record in owned:
                try:
                    record.close()
                except BaseException as error:
                    if first_error is None:
                        first_error = error
            if first_error is not None:
                raise first_error

    def _inventory(self, root: int) -> set[str]:
        names = set()
        with os.scandir(root) as entries:
            for entry in entries:
                names.add(entry.name)
                if len(names) > MAX_EVENTS + 2:
                    raise DurableRecoveryRequired("durable owner directory exceeds its entry bound")
        return names

    def _scan_history(self, retained: list) -> tuple[list[tuple[dict, str]], dict | None]:
        root = self._state._check_root()
        names = self._inventory(root)
        expected = {".coordinator.lock"}
        events = sorted(name for name in names if _EVENT.fullmatch(name))
        if len(events) > MAX_EVENTS:
            raise DurableRecoveryRequired("durable owner history capacity exhausted")
        expected.update(events)
        if RECOVERY_FILE in names:
            expected.add(RECOVERY_FILE)
        if names != expected:
            raise DurableRecoveryRequired("durable owner history contains unknown evidence")
        result: list[tuple[dict, str]] = []
        previous = None
        digest = _ZERO
        owner_ids = set()
        for sequence, name in enumerate(events, 1):
            if name != f"update-event-{sequence:06d}.json":
                raise DurableRecoveryRequired("durable owner history has a sequence gap")
            event, actual = self._read(name, retained=retained)
            self._validate_event(event, previous, digest, sequence)
            if event["kind"] == "owner_open":
                if event["owner_id"] in owner_ids:
                    raise DurableRecoveryRequired("historical owner identity was reused")
                owner_ids.add(event["owner_id"])
            result.append((event, actual))
            previous, digest = event, actual
        marker = None
        if RECOVERY_FILE in names:
            marker, _ = self._read(RECOVERY_FILE, retained=retained)
            _fields(marker, _MARKER_FIELDS)
            if marker["schema"] != RECOVERY_SCHEMA or marker["phase"] != "recovery_required" or marker["production_activation_enabled"] is not False or marker["bootloader_effect_performed"] is not False or type(marker["reason"]) is not str:
                raise DurableRecoveryRequired("durable recovery marker is invalid")
            if marker["state_root_identity"] != list(self._state._identity) or marker["slot_root_identity"] != list(self._slots._identity):
                raise DurableRecoveryRequired("durable recovery marker has different roots")
            _integer(marker["history_count"], minimum=0, maximum=MAX_EVENTS)
            _hash(marker["last_event_sha256"])
            if marker["operation_id"] is not None:
                _hash(marker["operation_id"])
            count = marker["history_count"]
            if count > len(result):
                raise DurableRecoveryRequired("recovery marker names an absent confirmed history prefix")
            prefix = None if count == 0 else result[count - 1]
            expected_digest = _ZERO if prefix is None else prefix[1]
            expected_operation = None if prefix is None or prefix[0]["operation"] is None else prefix[0]["operation"]["operation_id"]
            if marker["last_event_sha256"] != expected_digest or marker["operation_id"] != expected_operation:
                raise DurableRecoveryRequired("recovery marker differs from the confirmed operation prefix")
        for record in retained:
            if self._metadata(os.fstat(record.descriptor)) != record.metadata or self._metadata(os.stat(record.name, dir_fd=root, follow_symlinks=False)) != record.metadata:
                raise DurableRecoveryRequired("complete durable history changed before scan completion")
        self._state._check_root()
        if names != self._inventory(root):
            raise DurableRecoveryRequired("durable owner inventory changed during complete readback")
        return result, marker

    def _append(self, kind: str, operation: dict | None, receipt: dict | None, *, fault=None) -> tuple[dict, str]:
        current, marker = self._load_history()
        if marker or len(current) >= MAX_EVENTS or not _same(current, self._history):
            raise DurableRecoveryRequired("durable history changed or cannot accept an event")
        sequence = len(current) + 1
        event = {"schema": EVENT_SCHEMA, "sequence": sequence,
            "previous_sha256": _ZERO if not current else current[-1][1], "owner_id": self._owner_id,
            "kind": kind, "phase": _PHASES[kind], "observed_unix": self._guarded_clock(), "configuration": self._configuration,
            "operation": operation, "stage_receipt": receipt,
            "production_activation_enabled": False, "bootloader_effect_performed": False}
        self._validate_event(event, None if not current else current[-1][0], event["previous_sha256"], sequence)
        name = f"update-event-{sequence:06d}.json"
        root = self._state._check_root()
        try:
            os.stat(name, dir_fd=root, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise DurableRecoveryRequired("durable event name cannot be overwritten")
        expected = self._state.write(name, event, fault=fault)
        observed, digest = self._read(name)
        if digest != expected or not _same(observed, event):
            raise DurableRecoveryRequired("durable event readback does not bind the intended operation")
        self._history.append((observed, digest))
        complete, marker = self._load_history()
        if marker or not _same(complete, self._history):
            raise DurableRecoveryRequired("complete durable history changed after publication")
        self._phase = event["phase"]
        return observed, digest

    def _mark_recovery(self, reason: str) -> None:
        self._recovering = True
        self._phase = "recovery_required"
        root = self._state._check_root()
        try:
            os.stat(RECOVERY_FILE, dir_fd=root, follow_symlinks=False)
        except FileNotFoundError:
            last = None if not self._history else self._history[-1][0]
            marker = {"schema": RECOVERY_SCHEMA, "phase": "recovery_required", "reason": reason,
                "state_root_identity": list(self._state._identity), "slot_root_identity": list(self._slots._identity),
                "history_count": len(self._history), "last_event_sha256": _ZERO if last is None else self._history[-1][1],
                "operation_id": None if last is None or last["operation"] is None else last["operation"]["operation_id"],
                "production_activation_enabled": False, "bootloader_effect_performed": False}
            expected = self._state.write(RECOVERY_FILE, marker)
            actual, digest = self._read(RECOVERY_FILE)
            if digest != expected or not _same(actual, marker):
                raise DurableRecoveryRequired("recovery publication was not confirmed")
        else:
            # Preserve the original marker, including malformed evidence. Never
            # turn a failed or stale marker into a new owner or operation.
            return

    def _require_live(self, operation: DurableUpdateOperation | None = None, *, phase: str | None = None) -> None:
        if self._recovering:
            raise DurableRecoveryRequired("persisted recovery requires external authorized diagnosis")
        try:
            history, marker = self._load_history()
        except BaseException as error:
            self._mark_recovery("live_history_readback_failed")
            raise DurableRecoveryRequired("complete durable history could not be confirmed") from error
        if marker or not _same(history, self._history):
            self._mark_recovery("live_history_changed")
            raise DurableRecoveryRequired("complete durable owner history changed")
        if phase is not None and self._phase != phase:
            raise DurableUpdateError("durable update phase is stale")
        if operation is not None and (type(operation) is not DurableUpdateOperation or operation is not self._operation or operation._issuer is not self._issuer):
            raise DurableUpdateError("operation was not issued by this durable owner")

    def _verify_active(self) -> None:
        root = self._slots._check_root()
        name = f"slot-{self._coordinator.active_slot}.img"
        descriptor = self._slots._open_slot(root, name)
        try:
            self._slots._bound_image(root, name, descriptor, self._coordinator.current_image_sha256)
        finally:
            os.close(descriptor)

    def _verify_staged(self) -> None:
        manifest = self._ticket.manifest
        self._coordinator._revalidate_admission(self._ticket, now_unix=self._coordinator._clock())
        self._verify_active()
        root = self._slots._check_root()
        name = f"slot-{manifest.target_slot}.img"
        descriptor = self._slots._open_slot(root, name)
        try:
            self._slots._bound_image(root, name, descriptor, manifest.target_image_sha256, manifest.target_image_bytes)
            os.fsync(descriptor)
            os.fsync(root)
            self._slots._check_root()
            self._slots._bound_image(root, name, descriptor, manifest.target_image_sha256, manifest.target_image_bytes)
        finally:
            os.close(descriptor)

    def _result(self, event: dict, digest: str) -> DurableUpdateResult:
        operation = event["operation"]
        manifest = self._ticket.manifest
        result = DurableUpdateResult(operation["operation_id"], manifest.manifest_sha256, event["sequence"], digest,
            event["phase"], manifest.target_slot, manifest.target_image_sha256, manifest.target_image_bytes,
            self._slots._identity, False, False, self._issuer, self._owner_pid, self._owner_thread, _SEAL)
        self._results[event["sequence"]] = result
        return result

    @_authority_guard
    def verify_manifest(self, payload: bytes | str, *, now_unix: int, signature: bytes | None = None,
                        fault=None) -> DurableUpdateOperation:
        self._require_live(phase="idle")
        ticket = self._coordinator.verify_manifest(payload, now_unix=now_unix, signature=signature)
        self._ticket = ticket
        try:
            admission = {key: getattr(ticket.signature_admission, key) for key in _ADMISSION_FIELDS}
            operation = {"operation_id": secrets.token_hex(32), "owner_id": self._owner_id,
                "ticket_sequence": ticket.sequence, "manifest": recovery._strict_object(payload, recovery.MAX_MANIFEST_BYTES),
                "signature_admission": admission}
            self._append("manifest_verified", operation, None, fault=fault)
            issued = DurableUpdateOperation(operation["operation_id"], ticket.manifest.manifest_sha256,
                ticket.manifest.signature_sha256, self._issuer, self._owner_pid, self._owner_thread, _SEAL)
            self._operation = issued
            return issued
        except BaseException as error:
            self._mark_recovery("admission_publication_failed")
            raise DurableRecoveryRequired("admission result is unavailable; never retry this owner") from error

    @_authority_guard
    def stage_image_file(self, operation: DurableUpdateOperation, image_path: Path, *, now_unix: int,
                         state_fault=None, slot_fault=None) -> DurableUpdateResult:
        self._require_live(operation, phase="verified")
        self._coordinator._revalidate_admission(self._ticket, now_unix=now_unix)
        descriptor = recovery._open_image(image_path)
        try:
            digest, size = recovery._image_digest(descriptor, expected_bytes=self._ticket.manifest.target_image_bytes)
            if digest != self._ticket.manifest.target_image_sha256:
                raise DurableUpdateError("complete candidate image differs from the admitted manifest")
        finally:
            os.close(descriptor)
        record = self._history[-1][0]["operation"]
        known_completion = False
        try:
            self._append("stage_intent", record, None, fault=state_fault)
            def guarded_cutpoint(point):
                self._check_owner()
                self._require_live(operation, phase="stage_intent")
                if slot_fault is not None:
                    slot_fault(point)
                self._check_owner()
                self._require_live(operation, phase="stage_intent")
            receipt = self._coordinator.stage_image_file(self._ticket, image_path, self._slots, now_unix=now_unix, fault=guarded_cutpoint)
            if type(receipt) is not recovery.ImageStageReceipt or receipt.image_bytes != size:
                raise DurableRecoveryRequired("concrete staging receipt has a different complete image")
            self._verify_staged()
            stage = {key: getattr(receipt, key) for key in _STAGE_FIELDS}
            event, digest = self._append("stage_completed", record, stage, fault=state_fault)
            self._verify_staged()
            self._require_live(operation, phase="staged")
            known_completion = True
            return self._result(event, digest)
        except BaseException as error:
            if known_completion:
                raise DurableResultUnavailable("local durable staging is known; caller delivery is unobserved and staging cannot replay") from error
            self._mark_recovery("staging_or_result_uncertain")
            raise DurableRecoveryRequired("staging outcome requires diagnosis; never replay") from error

    @_authority_guard
    def arm_first_boot(self, operation: DurableUpdateOperation, *, now_unix: int, fault=None) -> DurableUpdateResult:
        """Persist source boot-policy intent only; perform no bootloader effect."""
        self._require_live(operation, phase="staged")
        self._coordinator._revalidate_admission(self._ticket, now_unix=now_unix)
        self._verify_staged()
        record, stage = self._history[-1][0]["operation"], self._history[-1][0]["stage_receipt"]
        known_completion = False
        try:
            self._append("arm_intent", record, stage, fault=fault)
            self._coordinator.arm_first_boot(self._ticket, now_unix=now_unix)
            event, digest = self._append("boot_policy_armed", record, stage, fault=fault)
            self._verify_staged()
            self._require_live(operation, phase="boot_pending")
            known_completion = True
            return self._result(event, digest)
        except BaseException as error:
            if known_completion:
                raise DurableResultUnavailable("durable source boot policy is known; caller delivery is unobserved and no boot occurred") from error
            self._mark_recovery("boot_policy_or_result_uncertain")
            raise DurableRecoveryRequired("boot policy requires diagnosis; no boot was performed") from error

    @_authority_guard
    def confirm_result(self, result: DurableUpdateResult) -> DurableUpdateResult:
        self._require_live()
        if type(result) is not DurableUpdateResult or result._issuer is not self._issuer or self._results.get(result.event_sequence) is not result:
            raise DurableUpdateError("result was not issued and retained by this owner")
        event, digest = self._history[result.event_sequence - 1]
        if digest != result.event_sha256 or event["operation"]["operation_id"] != result.operation_id or result.manifest_sha256 != self._ticket.manifest.manifest_sha256:
            raise DurableRecoveryRequired("durable result binding changed")
        self._verify_staged()
        self._require_live()
        return result

    @_authority_guard
    def inspect(self) -> dict:
        """Diagnostic records, never a resumed ticket or activation permit."""
        history, marker = self._load_history()
        return {"schema": SCHEMA, "phase": "recovery_required" if marker else self._phase,
            "events": [{"sequence": event["sequence"], "kind": event["kind"], "phase": event["phase"],
                        "event_sha256": digest, "operation_id": None if event["operation"] is None else event["operation"]["operation_id"]}
                       for event, digest in history],
            "recovery_required": self._recovering or marker is not None,
            "recovery_marker_confirmed": marker is not None, "production_activation_enabled": False,
            "bootloader_effect_performed": False, "resume_or_replay_available": False}

    def close(self) -> None:
        if os.getpid() != self._owner_pid:
            self._closed = True
            self._release_descriptors()
            return
        self._check_owner()
        if self._busy:
            raise DurableUpdateError("owner cannot close during an update callback")
        self._busy = True
        try:
            if not self._recovering and self._phase == "idle":
                self._require_live(phase="idle")
                self._append("owner_clean", None, None)
            elif not self._recovering:
                self._mark_recovery("explicit_close_with_unfinished_update")
        finally:
            self._closed = True
            self._busy = False
            self._release_descriptors()
