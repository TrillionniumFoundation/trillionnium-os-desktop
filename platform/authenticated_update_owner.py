"""Additive signed-journal custody; no restart replay or installed boot authority."""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import os
import re
import sys
from pathlib import Path

_MODULE = "hepta_durable_update_owner_v1"
if _MODULE not in sys.modules:
    _spec = importlib.util.spec_from_file_location(_MODULE, Path(__file__).with_name("durable_update_owner.py"))
    if _spec is None or _spec.loader is None:
        raise RuntimeError("bundled durable owner unavailable")
    durable = importlib.util.module_from_spec(_spec)
    sys.modules[_MODULE] = durable
    _spec.loader.exec_module(durable)
else:
    durable = sys.modules[_MODULE]
recovery = durable.recovery

EVENT_SCHEMA = "trillionnium.desktop.durable-update-event.v2"
SCHEMA = "trillionnium.desktop.authenticated-update-owner.v2"
CAPSULE_SCHEMA = "trillionnium.desktop.update-signature-capsule.v2"
MAX_EXACT_BYTES = 16 * 1024
MAX_DIRECTORY_ENTRIES = durable.MAX_EVENTS + 3
_CAPSULE = re.compile(r"update-signature-([0-9a-f]{64})\.json\Z", re.ASCII)
_CAPSULE_FIELDS = {"schema", "operation_id", "owner_id", "configuration", "signature_admission", "manifest_bytes_b64", "signature_bytes_b64"}
_REFERENCE_FIELDS = {"name", "sha256", "manifest_bytes_sha256", "signature_sha256"}


def _legacy_event(event: dict | None) -> dict | None:
    """Closed v2 envelope projection for the unchanged v1 semantic validator."""
    if event is None:
        return None
    durable._fields(event, durable._EVENT_FIELDS)
    if event["schema"] == durable.EVENT_SCHEMA:
        return event
    if event["schema"] != EVENT_SCHEMA:
        raise durable.DurableRecoveryRequired("unknown durable event profile")
    result = {**event, "schema": durable.EVENT_SCHEMA}
    operation = event["operation"]
    if operation is not None:
        durable._fields(operation, durable._OP_FIELDS | {"signature_capsule"})
        reference = durable._fields(operation["signature_capsule"], _REFERENCE_FIELDS)
        if reference["name"] != f"update-signature-{durable._hash(operation['operation_id'])}.json":
            raise durable.DurableRecoveryRequired("signature capsule name differs from its operation")
        for field in ("sha256", "manifest_bytes_sha256", "signature_sha256"):
            durable._hash(reference[field])
        result["operation"] = {key: value for key, value in operation.items() if key != "signature_capsule"}
    return result


def _decode(value: object) -> bytes:
    if type(value) is not str or len(value) > 4 * ((MAX_EXACT_BYTES + 2) // 3):
        raise durable.DurableRecoveryRequired("signature capsule encoding exceeds its bound")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, UnicodeError) as error:
        raise durable.DurableRecoveryRequired("signature capsule encoding is invalid") from error
    if not 1 <= len(decoded) <= MAX_EXACT_BYTES or base64.b64encode(decoded).decode("ascii") != value:
        raise durable.DurableRecoveryRequired("signature capsule bytes are empty, noncanonical or oversized")
    return decoded


def _capsule(value: dict, digest: str, event: dict) -> tuple[bytes, bytes]:
    durable._fields(value, _CAPSULE_FIELDS)
    operation = event["operation"]
    reference = durable._fields(operation["signature_capsule"], _REFERENCE_FIELDS)
    if value["schema"] != CAPSULE_SCHEMA or value["operation_id"] != operation["operation_id"] or value["owner_id"] != event["owner_id"] or not durable._same(value["configuration"], event["configuration"]) or not durable._same(value["signature_admission"], operation["signature_admission"]) or digest != reference["sha256"]:
        raise durable.DurableRecoveryRequired("signature capsule has different operation, policy, roots or event bytes")
    payload, signature = _decode(value["manifest_bytes_b64"]), _decode(value["signature_bytes_b64"])
    if hashlib.sha256(payload).hexdigest() != reference["manifest_bytes_sha256"] or hashlib.sha256(signature).hexdigest() != reference["signature_sha256"] or reference["signature_sha256"] != operation["signature_admission"]["signature_sha256"]:
        raise durable.DurableRecoveryRequired("signature capsule byte digests differ from the event")
    if not durable._same(recovery._strict_object(payload, recovery.MAX_MANIFEST_BYTES), operation["manifest"]):
        raise durable.DurableRecoveryRequired("signature capsule exact manifest differs from the event manifest")
    if hashlib.sha256(recovery.manifest_signing_bytes(payload)).hexdigest() != operation["signature_admission"]["signing_preimage_sha256"]:
        raise durable.DurableRecoveryRequired("signature capsule signing domain differs from admission")
    return payload, signature


class AuthenticatedUpdateOwner(durable.DurableUpdateOwner):
    """New v2 source journal, retaining exact signed bytes before intent.

    Legacy v1 records remain structural history. A v1 unfinished session never
    becomes cryptographic readback, and neither profile resumes an operation.
    """
    _event_schema = EVENT_SCHEMA
    _diagnostic_schema = SCHEMA
    _directory_entry_limit = MAX_DIRECTORY_ENTRIES
    _pending_capsule = None

    def _validate_event(self, event, previous, digest, sequence):
        if previous is not None and previous["schema"] != event["schema"] and event["kind"] != "owner_open":
            raise durable.DurableRecoveryRequired("durable profile changed within an owner operation")
        super()._validate_event(_legacy_event(event), _legacy_event(previous), digest, sequence)
        if previous is not None and event["kind"] not in {"owner_open", "owner_clean", "manifest_verified"} and not durable._same(event["operation"], previous["operation"]):
            raise durable.DurableRecoveryRequired("signature capsule reference changed between phases")

    def _history_extra_names(self, names):
        capsules = {name for name in names if _CAPSULE.fullmatch(name)}
        if len(capsules) > 1:
            raise durable.DurableRecoveryRequired("signature capsule count exceeds its bound")
        return capsules

    def _validate_history_extra(self, history, retained):
        names = self._history_extra_names(self._inventory(self._state._check_root()))
        expected = {}
        for event, _ in history:
            if event["schema"] == EVENT_SCHEMA and event["operation"] is not None:
                reference = event["operation"]["signature_capsule"]
                expected.setdefault(reference["name"], event)
        if not expected and self._pending_capsule is not None:
            # Only the current owner can hold this transient adoption. A crash
            # with a capsule but no v2 event is unknown evidence on restart.
            expected[self._pending_capsule["operation"]["signature_capsule"]["name"]] = self._pending_capsule
        if names != set(expected):
            raise durable.DurableRecoveryRequired("signature capsule lacks its complete durable operation")
        for name, event in expected.items():
            value, digest = self._read(name, retained=retained)
            _capsule(value, digest, event)

    def _prepare_operation(self, operation, payload, signature, fault):
        if type(payload) is str:
            payload = payload.encode("utf-8")
        if type(payload) is not bytes or type(signature) is not bytes or not 1 <= len(payload) <= MAX_EXACT_BYTES or not 1 <= len(signature) <= MAX_EXACT_BYTES:
            raise durable.DurableRecoveryRequired("v2 exact manifest and signature require bounded byte envelopes")
        value = {"schema": CAPSULE_SCHEMA, "operation_id": operation["operation_id"], "owner_id": self._owner_id,
            "configuration": self._configuration, "signature_admission": operation["signature_admission"],
            "manifest_bytes_b64": base64.b64encode(payload).decode("ascii"),
            "signature_bytes_b64": base64.b64encode(signature).decode("ascii")}
        name = f"update-signature-{operation['operation_id']}.json"
        digest = hashlib.sha256(recovery._canonical(value)).hexdigest()
        operation = {**operation, "signature_capsule": {"name": name, "sha256": digest,
            "manifest_bytes_sha256": hashlib.sha256(payload).hexdigest(), "signature_sha256": hashlib.sha256(signature).hexdigest()}}
        self._pending_capsule = {"owner_id": self._owner_id, "configuration": self._configuration, "operation": operation}
        root = self._state._check_root()
        try:
            os.stat(name, dir_fd=root, follow_symlinks=False)
        except FileNotFoundError:
            pass
        else:
            raise durable.DurableRecoveryRequired("signature capsule cannot replace prior evidence")
        written = self._state.write(name, value, fault=fault)
        actual, observed = self._read(name)
        if observed != written or observed != digest:
            raise durable.DurableRecoveryRequired("complete signature capsule publication was not confirmed")
        _capsule(actual, observed, self._pending_capsule)
        return operation
