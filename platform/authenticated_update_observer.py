"""Actual persisted-signature readback; never a boot, health or replay permit."""
from __future__ import annotations

import hashlib
import importlib.util
import os
import sys
import threading
from dataclasses import dataclass
from pathlib import Path


def _load(name, path):
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, path)
        if spec is None or spec.loader is None:
            raise RuntimeError("bundled update readback unavailable")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


signed = _load("hepta_authenticated_update_owner_v2", Path(__file__).with_name("authenticated_update_owner.py"))
observer = _load("hepta_update_boot_observer_v1", Path(__file__).with_name("update_boot_observer.py"))
recovery = signed.recovery
SCHEMA = "trillionnium.desktop.authenticated-update-readback.v2"
_SEAL = object()


@dataclass(frozen=True, init=False)
class AuthenticatedUpdateReadback:
    """Creator-bound diagnostic. No update API accepts this as authority."""
    status: str
    reason_codes: tuple[str, ...]
    signatures_verified: bool
    stored_slot_images_verified: bool
    _private: bytes
    _creator_pid: int
    _creator_thread: object
    _seal: object

    def __post_init__(self):
        if self._seal is not _SEAL:
            raise recovery.StateRefused("authenticated readback was not issued by the concrete observer")

    def _check(self):
        if os.getpid() != self._creator_pid or threading.current_thread() is not self._creator_thread:
            raise recovery.StateRefused("authenticated readback requires its creating process and thread")

    def __getattribute__(self, name):
        if name in {"status", "reason_codes", "signatures_verified", "stored_slot_images_verified"}:
            self._check()
        return object.__getattribute__(self, name)

    def public_json(self) -> bytes:
        self._check()
        return observer._canonical({"schema": SCHEMA, "status": self.status, "reason_codes": list(self.reason_codes),
            "signatures_verified": self.signatures_verified, "stored_slot_images_verified": self.stored_slot_images_verified,
            "signed_boot_image_mapping": "unknown", "booted_image_verified": False, "health_qualified": False,
            "continuation_authorized": False, "production_activation_enabled": False, "bootloader_effect_performed": False})

    def private_json(self) -> bytes:
        self._check()
        return self._private


def _fact(status, reasons, *, authenticated=False, details=None):
    public = {"schema": SCHEMA, "status": status, "reason_codes": list(reasons),
        "signatures_verified": authenticated, "stored_slot_images_verified": authenticated,
        "signed_boot_image_mapping": "unknown", "booted_image_verified": False, "health_qualified": False,
        "continuation_authorized": False, "production_activation_enabled": False, "bootloader_effect_performed": False}
    private = observer._canonical({**public, "diagnostic": details})
    if len(private) + 1 > observer.MAX_DIAGNOSTIC_BYTES:
        raise observer._Refused(observer.ObservationReason.CUSTODY_UNAVAILABLE)
    value = object.__new__(AuthenticatedUpdateReadback)
    for name, field in (("status", status), ("reason_codes", tuple(reasons)),
                        ("signatures_verified", authenticated), ("stored_slot_images_verified", authenticated),
                        ("_private", private), ("_creator_pid", os.getpid()),
                        ("_creator_thread", threading.current_thread()), ("_seal", _SEAL)):
        object.__setattr__(value, name, field)
    value.__post_init__()
    return value


def _history(reader, state, slots):
    names = reader.inventory(state, signed.MAX_DIRECTORY_ENTRIES)
    events = sorted(name for name in names if observer._EVENT.fullmatch(name))
    capsules = {name for name in names if signed._CAPSULE.fullmatch(name)}
    if names != {".coordinator.lock", *events, *capsules, *({observer._MARKER} if observer._MARKER in names else set())} or len(events) > observer.MAX_EVENTS or len(capsules) > 1:
        raise observer._Refused(observer.ObservationReason.JOURNAL_INVALID)
    state_id = list(observer._directory(os.fstat(state.fd))[:2])
    slot_id = list(observer._directory(os.fstat(slots.fd))[:2])
    previous, digest, owner_ids, records, capsule_events = None, observer._ZERO, set(), [], {}
    for sequence, name in enumerate(events, 1):
        if name != f"update-event-{sequence:06d}.json":
            raise observer._Refused(observer.ObservationReason.JOURNAL_INVALID)
        event, actual = reader.record(state, name)
        observer._event(signed._legacy_event(event), signed._legacy_event(previous), digest, sequence, state_id, slot_id)
        if previous is not None and previous["schema"] != event["schema"] and event["kind"] != "owner_open":
            raise observer._Refused(observer.ObservationReason.JOURNAL_INVALID)
        if previous is not None and event["kind"] not in {"owner_open", "owner_clean", "manifest_verified"} and observer._canonical(event["operation"]) != observer._canonical(previous["operation"]):
            raise observer._Refused(observer.ObservationReason.JOURNAL_INVALID)
        if event["kind"] == "owner_open":
            if event["owner_id"] in owner_ids:
                raise observer._Refused(observer.ObservationReason.JOURNAL_INVALID)
            owner_ids.add(event["owner_id"])
        if event["schema"] == signed.EVENT_SCHEMA and event["operation"] is not None:
            reference = event["operation"]["signature_capsule"]
            capsule_events.setdefault(reference["name"], event)
        records.append((event, actual))
        previous, digest = event, actual
    if capsules != set(capsule_events):
        raise observer._Refused(observer.ObservationReason.JOURNAL_INVALID)
    exact = {}
    for name, event in capsule_events.items():
        value, actual = reader.record(state, name)
        exact[name] = signed._capsule(value, actual, event)
    marker = observer._MARKER in names
    if marker:
        value, _ = reader.record(state, observer._MARKER)
        observer._fields(value, observer._MARKER_FIELDS)
        count = observer._integer(value["history_count"], 0, observer.MAX_EVENTS)
        observer._identity(value["state_root_identity"]); observer._identity(value["slot_root_identity"])
        observer._hash(value["last_event_sha256"])
        if value["operation_id"] is not None:
            observer._hash(value["operation_id"])
        if count > len(records):
            raise observer._Refused(observer.ObservationReason.JOURNAL_INVALID)
        prefix = None if count == 0 else records[count - 1]
        operation = None if prefix is None or prefix[0]["operation"] is None else prefix[0]["operation"]["operation_id"]
        if value["schema"] != signed.durable.RECOVERY_SCHEMA or value["phase"] != "recovery_required" or type(value["reason"]) is not str or not 1 <= len(value["reason"]) <= 256 or value["production_activation_enabled"] is not False or value["bootloader_effect_performed"] is not False or value["state_root_identity"] != state_id or value["slot_root_identity"] != slot_id or value["last_event_sha256"] != (observer._ZERO if prefix is None else prefix[1]) or value["operation_id"] != operation:
            raise observer._Refused(observer.ObservationReason.JOURNAL_INVALID)
    return names, records, marker, exact


def _image(reader, slots, name, expected_sha256, expected_bytes=None):
    child, metadata = reader.file(slots, name, image=True)
    if expected_bytes is not None and metadata[6] != expected_bytes:
        raise recovery.StateRefused("stored slot length differs from the signed image")
    digest, offset = hashlib.sha256(), 0
    while offset < metadata[6]:
        reader._check()
        chunk = os.pread(child.fd, min(1024 * 1024, metadata[6] - offset), offset)
        if not chunk:
            raise recovery.StateRefused("stored slot ended before complete readback")
        offset += len(chunk)
        digest.update(chunk)
    if os.pread(child.fd, 1, offset) or digest.hexdigest() != expected_sha256:
        raise recovery.StateRefused("stored slot differs from the signed image")
    return {"sha256": digest.hexdigest(), "bytes": offset, "content_verified": True}


def _confirm_scan(reader, state, slots, names, slot_names, before):
    after = observer._kernel(reader)
    if before != after:
        raise observer._Refused(observer.ObservationReason.KERNEL_CHANGED)
    reader.confirm((state, slots))
    if names != reader.inventory(state, signed.MAX_DIRECTORY_ENTRIES) or slot_names != reader.inventory(slots, 3):
        raise observer._Refused(observer.ObservationReason.CUSTODY_UNAVAILABLE)
    return after


def inspect_authenticated_update(state_root: Path, slot_root: Path, *, signature_verifier,
                                 clock, protected_rollback_floor: int) -> AuthenticatedUpdateReadback:
    """Verify exact durable bytes with separately approved roots and local anchors.

    The clock/floor/verifier are trusted installation configuration, not caller
    health or a resumed owner. Existing roots/leases are opened read-only.
    """
    reader = observer._Reader()
    try:
        if type(signature_verifier) is not recovery.ExternalUpdateSignatureVerifier or not callable(clock):
            return _fact("observation_unavailable", ("external_signature_configuration_unavailable",))
        now = recovery._positive_int(clock(), "configured readback clock")
        floor = recovery._positive_int(protected_rollback_floor, "configured protected rollback floor")
        before = observer._kernel(reader)
        state, slots = reader.root(state_root), reader.root(slot_root)
        if observer._directory(os.fstat(state.fd))[:2] == observer._directory(os.fstat(slots.fd))[:2]:
            raise observer._Refused(observer.ObservationReason.CUSTODY_UNAVAILABLE)
        reader.lease(state); reader.lease(slots)
        names, history, marker, exact = _history(reader, state, slots)
        slot_names = reader.inventory(slots, 3)
        if slot_names != {".coordinator.lock", "slot-A.img", "slot-B.img"}:
            raise observer._Refused(observer.ObservationReason.CUSTODY_UNAVAILABLE)
        tail = None if not history else history[-1][0]
        if tail is None or tail["operation"] is None:
            _confirm_scan(reader, state, slots, names, slot_names, before)
            if marker:
                return _fact("recovery_required", ("recovery_marker_present",))
            if tail is not None and tail["kind"] != "owner_clean":
                return _fact("recovery_required", ("unfinished_owner",))
            return _fact("no_pending_update", ("no_signed_pending_operation",))
        if tail["schema"] != signed.EVENT_SCHEMA:
            _confirm_scan(reader, state, slots, names, slot_names, before)
            return _fact("pending_identity_unknown", ("legacy_detached_signature_unavailable",))
        operation, config = tail["operation"], tail["configuration"]
        original = operation["signature_admission"]
        if now < max(original["verified_unix"], tail["observed_unix"]) or floor < config["protected_rollback_floor"] or signature_verifier.policy_sha256 != config["trust_policy_sha256"]:
            raise recovery.ManifestRefused("readback time, floor or independently provisioned policy differs")
        payload, signature = exact[operation["signature_capsule"]["name"]]
        admission = signature_verifier.verify(payload, signature, now_unix=now)
        for key in signed.durable._ADMISSION_FIELDS - {"verified_unix"}:
            if getattr(admission, key) != original[key]:
                raise recovery.ManifestRefused("actual detached-signature admission differs from durable custody")
        manifest = recovery.UpdateManifest.parse(payload, now_unix=now, active_slot=config["active_slot"], current_version=config["current_version"], current_image_sha256=config["current_image_sha256"])
        if manifest.rollback_floor < max(floor, admission.minimum_version):
            raise recovery.ManifestRefused("readback manifest weakens the current protected floor")
        if tail["kind"] not in {"stage_completed", "arm_intent", "boot_policy_armed"}:
            _confirm_scan(reader, state, slots, names, slot_names, before)
            return _fact("recovery_required", ("staging_completion_unconfirmed",))
        images = {config["active_slot"]: _image(reader, slots, f"slot-{config['active_slot']}.img", config["current_image_sha256"]),
            manifest.target_slot: _image(reader, slots, f"slot-{manifest.target_slot}.img", manifest.target_image_sha256, manifest.target_image_bytes)}
        after = _confirm_scan(reader, state, slots, names, slot_names, before)
        final_now = recovery._positive_int(clock(), "configured final readback clock")
        if final_now < now or final_now >= manifest.expires_unix:
            raise recovery.ManifestRefused("readback clock regressed or signed manifest expired")
        signature_verifier.revalidate(admission, now_unix=final_now)
        reader.confirm((state, slots))
        if names != reader.inventory(state, signed.MAX_DIRECTORY_ENTRIES) or slot_names != reader.inventory(slots, 3):
            raise observer._Refused(observer.ObservationReason.CUSTODY_UNAVAILABLE)
        details = {"kernel": after, "operation_id": operation["operation_id"], "owner_id": tail["owner_id"],
            "state_root_identity": config["state_root_identity"], "slot_root_identity": config["slot_root_identity"],
            "trust_policy_sha256": admission.trust_policy_sha256, "public_key_sha256": admission.public_key_sha256,
            "signature_capsule_sha256": operation["signature_capsule"]["sha256"],
            "manifest_bytes_sha256": operation["signature_capsule"]["manifest_bytes_sha256"],
            "signature_sha256": admission.signature_sha256, "readback_verified_unix": now, "readback_completed_unix": final_now,
            "protected_rollback_floor": floor, "last_event_sha256": history[-1][1], "last_kind": tail["kind"],
            "record_count": len(history), "recovery_marker": marker, "stored_slot_images": images}
        return _fact("recovery_required" if marker else "pending_identity_unknown",
            (("recovery_marker_present",) if marker else ()) + ("signed_boot_image_mapping_unknown",), authenticated=True, details=details)
    except observer._Refused as error:
        return _fact("recovery_required" if error.reason == observer.ObservationReason.JOURNAL_INVALID else "observation_unavailable", (error.reason.value,))
    except recovery.UpdateError:
        return _fact("recovery_required", ("persisted_signature_or_image_refused",))
    except (OSError, ValueError, TypeError, KeyError, RecursionError):
        return _fact("observation_unavailable", ("custody_unavailable",))
    finally:
        reader.close()
