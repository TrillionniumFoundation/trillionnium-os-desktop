#!/usr/bin/env python3
"""Deterministic D7 reference model for external-effect reconciliation.

This source-only model never performs an external effect and never permits
automatic replay after dispatch. Its byte log is canonical, bounded and
hash-chained. A separately trusted count/head checkpoint can detect complete
suffix truncation or a rehashed replacement history; the hash chain alone is
not an authenticity proof.
"""
from __future__ import annotations

import copy
from dataclasses import asdict, dataclass
import hashlib
import json
import math
import sys
from typing import Any

SCHEMA_RECORD = "trillionnium.desktop.effect-journal-record.v1"
ZERO = "0" * 64
MAX_JOURNAL_BYTES = 16 * 1024 * 1024
MAX_RECORD_BYTES = 16 * 1024
MAX_RECORDS = 65536
MAX_REASON_BYTES = 1024


class EffectError(ValueError):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


def fail(reason: str) -> None:
    raise EffectError(reason)


def _reject_constant(_: str) -> None:
    fail("EFFECT_JOURNAL_NONFINITE_NUMBER")


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            fail("EFFECT_JOURNAL_DUPLICATE_KEY")
        value[key] = item
    return value


def strict_json_loads(data: bytes) -> Any:
    try:
        text = data.decode("utf-8", errors="strict")
        return json.loads(
            text,
            object_pairs_hook=_object_no_duplicates,
            parse_constant=_reject_constant,
        )
    except EffectError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EffectError("EFFECT_JOURNAL_INVALID_JSON") from error


def _validate_json(value: Any) -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            fail("EFFECT_JOURNAL_NONFINITE_NUMBER")
        return
    if isinstance(value, list):
        for item in value:
            _validate_json(item)
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                fail("EFFECT_JOURNAL_NONSTRING_KEY")
            _validate_json(item)
        return
    fail("EFFECT_JOURNAL_UNSUPPORTED_VALUE")


def canonical(value: Any) -> bytes:
    _validate_json(value)
    try:
        return (
            json.dumps(
                value,
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            + "\n"
        ).encode("utf-8")
    except (TypeError, ValueError, UnicodeEncodeError) as error:
        raise EffectError("EFFECT_JOURNAL_SERIALIZATION_INVALID") from error


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def is_sha(value: Any) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


def require_digest(value: Any, field: str) -> None:
    if not is_sha(value):
        fail(f"{field}_INVALID_SHA256")


def require_text(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value or "\x00" in value:
        fail(f"{field}_INVALID_TEXT")


def require_reason(value: Any) -> None:
    require_text(value, "EVENT_REASON")
    try:
        size = len(value.encode("utf-8"))
    except UnicodeEncodeError as error:
        raise EffectError("EVENT_REASON_INVALID_UTF8") from error
    if size > MAX_REASON_BYTES:
        fail("EVENT_REASON_TOO_LARGE")


ALLOWED_TRANSITIONS = {
    "requested": {"prepared", "cancelled_before_dispatch"},
    "prepared": {"dispatched", "cancelled_before_dispatch"},
    "dispatched": {
        "terminal_success",
        "terminal_failure",
        "indeterminate",
        "reconciled_applied",
        "reconciled_not_applied",
        "manual_required",
    },
    "indeterminate": {
        "terminal_success",
        "terminal_failure",
        "reconciled_applied",
        "reconciled_not_applied",
        "manual_required",
    },
}
TERMINAL_STATES = {
    "terminal_success",
    "terminal_failure",
    "cancelled_before_dispatch",
    "reconciled_applied",
    "reconciled_not_applied",
    "manual_required",
}
RECONCILIATION_EVENTS = {
    "reconciled_applied",
    "reconciled_not_applied",
    "manual_required",
}


@dataclass
class EffectOperation:
    operation_id: str
    idempotency_key: str
    effect_kind: str
    payload_sha256: str
    permit_sha256: str
    subject_sha256: str
    state: str = "requested"
    dispatch_token_sha256: str | None = None
    provider_receipt_sha256: str | None = None
    retry_requires_new_authorization: bool = False


class EffectJournal:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []
        self.operations: dict[str, EffectOperation] = {}
        self.idempotency_keys: dict[str, str] = {}
        # Keep the hardened implementation's public alias for compatibility.
        self.idempotency = self.idempotency_keys
        self.discarded_torn_tail = False
        self._serialized_bytes = 0

    @staticmethod
    def _event_hash(sequence: int, previous: str, event: dict[str, Any]) -> str:
        return digest(
            {
                "schema": SCHEMA_RECORD,
                "sequence": sequence,
                "previous_record_sha256": previous,
                "event": event,
            }
        )

    def _record_for(self, event: dict[str, Any]) -> tuple[dict[str, Any], bytes]:
        sequence = len(self.records) + 1
        if sequence > MAX_RECORDS:
            fail("EFFECT_JOURNAL_TOO_MANY_RECORDS")
        previous = self.records[-1]["record_sha256"] if self.records else ZERO
        record: dict[str, Any] = {
            "schema": SCHEMA_RECORD,
            "sequence": sequence,
            "previous_record_sha256": previous,
            "event": copy.deepcopy(event),
        }
        record["record_sha256"] = self._event_hash(sequence, previous, event)
        encoded = canonical(record)
        if len(encoded) > MAX_RECORD_BYTES:
            fail("EFFECT_JOURNAL_RECORD_TOO_LARGE")
        if self._serialized_bytes + len(encoded) > MAX_JOURNAL_BYTES:
            fail("EFFECT_JOURNAL_TOO_LARGE")
        return record, encoded

    def _append(self, event: dict[str, Any]) -> dict[str, Any]:
        # Encoding, bounds, and semantic validation all complete against copies
        # before any externally visible state changes.
        record, encoded = self._record_for(event)
        candidate_operations = copy.deepcopy(self.operations)
        candidate_idempotency = copy.deepcopy(self.idempotency_keys)
        self._apply_event(event, candidate_operations, candidate_idempotency)
        self.operations = candidate_operations
        self.idempotency_keys = candidate_idempotency
        self.idempotency = self.idempotency_keys
        self.records.append(record)
        self._serialized_bytes += len(encoded)
        return copy.deepcopy(record)

    def request(
        self,
        operation_id: str,
        idempotency_key: str,
        effect_kind: str,
        payload_sha256: str,
        permit_sha256: str,
        subject_sha256: str,
    ) -> dict[str, Any]:
        for field, value in (
            ("OPERATION_ID", operation_id),
            ("IDEMPOTENCY_KEY", idempotency_key),
            ("EFFECT_KIND", effect_kind),
        ):
            require_text(value, field)
        for field, value in (
            ("PAYLOAD_SHA256", payload_sha256),
            ("PERMIT_SHA256", permit_sha256),
            ("SUBJECT_SHA256", subject_sha256),
        ):
            require_digest(value, field)
        if operation_id in self.operations:
            fail("DUPLICATE_OPERATION_ID")
        if idempotency_key in self.idempotency_keys:
            fail("DUPLICATE_IDEMPOTENCY_KEY")
        return self._append(
            {
                "kind": "requested",
                "operation_id": operation_id,
                "idempotency_key": idempotency_key,
                "effect_kind": effect_kind,
                "payload_sha256": payload_sha256,
                "permit_sha256": permit_sha256,
                "subject_sha256": subject_sha256,
            }
        )

    def prepare(self, operation_id: str) -> dict[str, Any]:
        return self._transition(operation_id, "prepared")

    def dispatch(self, operation_id: str, dispatch_token_sha256: str) -> dict[str, Any]:
        require_digest(dispatch_token_sha256, "DISPATCH_TOKEN_SHA256")
        return self._transition(
            operation_id,
            "dispatched",
            dispatch_token_sha256=dispatch_token_sha256,
        )

    def terminal(
        self,
        operation_id: str,
        outcome: Any,
        provider_receipt_sha256: str,
    ) -> dict[str, Any]:
        if not isinstance(outcome, str) or outcome not in {"success", "failure"}:
            fail("INVALID_TERMINAL_OUTCOME")
        require_digest(provider_receipt_sha256, "PROVIDER_RECEIPT_SHA256")
        return self._transition(
            operation_id,
            f"terminal_{outcome}",
            provider_receipt_sha256=provider_receipt_sha256,
        )

    def indeterminate(self, operation_id: str, reason: Any) -> dict[str, Any]:
        require_reason(reason)
        return self._transition(operation_id, "indeterminate", reason=reason)

    def mark_indeterminate(self, operation_id: str, reason: Any) -> dict[str, Any]:
        """Compatibility alias retained for the hardened source candidate."""
        return self.indeterminate(operation_id, reason)

    def reconcile(
        self,
        operation_id: str,
        result: Any,
        provider_receipt_sha256: str,
    ) -> dict[str, Any]:
        if not isinstance(result, str) or result not in {
            "applied",
            "not_applied",
            "unknown",
        }:
            fail("INVALID_RECONCILIATION_RESULT")
        require_digest(provider_receipt_sha256, "PROVIDER_RECEIPT_SHA256")
        event = {
            "applied": "reconciled_applied",
            "not_applied": "reconciled_not_applied",
            "unknown": "manual_required",
        }[result]
        return self._transition(
            operation_id,
            event,
            provider_receipt_sha256=provider_receipt_sha256,
        )

    def cancel(self, operation_id: str, reason: Any) -> dict[str, Any]:
        require_reason(reason)
        return self._transition(
            operation_id,
            "cancelled_before_dispatch",
            reason=reason,
        )

    def _transition(
        self,
        operation_id: str,
        event_kind: str,
        **fields: Any,
    ) -> dict[str, Any]:
        require_text(operation_id, "OPERATION_ID")
        operation = self.operations.get(operation_id)
        if operation is None:
            fail("UNKNOWN_OPERATION")
        self._require_transition(operation.state, event_kind)
        return self._append(
            {"kind": event_kind, "operation_id": operation_id, **fields}
        )

    @staticmethod
    def _require_transition(state: str, event_kind: str) -> None:
        if event_kind == "cancelled_before_dispatch" and state not in {
            "requested",
            "prepared",
        }:
            fail("CANCEL_AFTER_DISPATCH_FORBIDDEN")
        if event_kind in RECONCILIATION_EVENTS and state not in {
            "dispatched",
            "indeterminate",
        }:
            fail("RECONCILIATION_NOT_ALLOWED")
        if event_kind not in ALLOWED_TRANSITIONS.get(state, set()):
            fail("INVALID_EFFECT_TRANSITION")

    @staticmethod
    def _apply_event(
        event: dict[str, Any],
        operations: dict[str, EffectOperation],
        idempotency: dict[str, str],
    ) -> None:
        if not isinstance(event, dict):
            fail("EVENT_NOT_OBJECT")
        kind = event.get("kind")
        if not isinstance(kind, str):
            fail("EVENT_KIND_INVALID")
        operation_id = event.get("operation_id")
        require_text(operation_id, "OPERATION_ID")
        if kind == "requested":
            expected = {
                "kind",
                "operation_id",
                "idempotency_key",
                "effect_kind",
                "payload_sha256",
                "permit_sha256",
                "subject_sha256",
            }
            if set(event) != expected:
                fail("REQUESTED_FIELD_SET_MISMATCH")
            require_text(event["idempotency_key"], "IDEMPOTENCY_KEY")
            require_text(event["effect_kind"], "EFFECT_KIND")
            for field in (
                "payload_sha256",
                "permit_sha256",
                "subject_sha256",
            ):
                require_digest(event[field], field.upper())
            if operation_id in operations:
                fail("DUPLICATE_OPERATION_ID")
            if event["idempotency_key"] in idempotency:
                fail("DUPLICATE_IDEMPOTENCY_KEY")
            operations[operation_id] = EffectOperation(
                operation_id=operation_id,
                idempotency_key=event["idempotency_key"],
                effect_kind=event["effect_kind"],
                payload_sha256=event["payload_sha256"],
                permit_sha256=event["permit_sha256"],
                subject_sha256=event["subject_sha256"],
            )
            idempotency[event["idempotency_key"]] = operation_id
            return

        operation = operations.get(operation_id)
        if operation is None:
            fail("UNKNOWN_OPERATION")
        EffectJournal._require_transition(operation.state, kind)
        expected = {"kind", "operation_id"}
        if kind == "dispatched":
            expected.add("dispatch_token_sha256")
            require_digest(
                event.get("dispatch_token_sha256"),
                "DISPATCH_TOKEN_SHA256",
            )
        elif kind in {
            "terminal_success",
            "terminal_failure",
            "reconciled_applied",
            "reconciled_not_applied",
            "manual_required",
        }:
            expected.add("provider_receipt_sha256")
            require_digest(
                event.get("provider_receipt_sha256"),
                "PROVIDER_RECEIPT_SHA256",
            )
        elif kind in {"indeterminate", "cancelled_before_dispatch"}:
            expected.add("reason")
            require_reason(event.get("reason"))
        if set(event) != expected:
            fail("EVENT_FIELD_SET_MISMATCH")

        operation.state = kind
        if kind == "dispatched":
            operation.dispatch_token_sha256 = event["dispatch_token_sha256"]
        elif kind in {
            "terminal_success",
            "terminal_failure",
            "reconciled_applied",
            "reconciled_not_applied",
            "manual_required",
        }:
            operation.provider_receipt_sha256 = event[
                "provider_receipt_sha256"
            ]
        if kind == "reconciled_not_applied":
            operation.retry_requires_new_authorization = True

    def operation(self, operation_id: str) -> dict[str, Any]:
        operation = self.operations.get(operation_id)
        if operation is None:
            fail("UNKNOWN_OPERATION")
        return copy.deepcopy(asdict(operation))

    def may_execute_external_effect(self, operation_id: str) -> bool:
        return self.operation(operation_id)["state"] == "prepared"

    def requires_reconciliation(self, operation_id: str) -> bool:
        return self.operation(operation_id)["state"] in {
            "dispatched",
            "indeterminate",
        }

    def automatic_replay_allowed(self, operation_id: str) -> bool:
        self.operation(operation_id)
        return False

    def recovery_action(self, operation_id: str) -> str:
        state = self.operation(operation_id)["state"]
        if state in {"requested", "prepared"}:
            return "PRE_EFFECT_SAFE_TO_CANCEL_OR_REPREPARE"
        if state in {"dispatched", "indeterminate"}:
            return "RECONCILE_ONLY_NEVER_AUTOMATICALLY_REPLAY"
        if state == "manual_required":
            return "MANUAL_ACTION_REQUIRED"
        if state in TERMINAL_STATES:
            return "NO_ACTION_TERMINAL"
        fail("UNKNOWN_EFFECT_STATE")

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema": "trillionnium.desktop.effect-journal-snapshot.v1",
            "operations": {
                key: asdict(self.operations[key])
                for key in sorted(self.operations)
            },
            "record_count": len(self.records),
            "head_record_sha256": (
                self.records[-1]["record_sha256"] if self.records else ZERO
            ),
            "discarded_torn_tail": self.discarded_torn_tail,
            "journal_executes_operations": False,
            "automatic_replay_after_dispatch": False,
        }

    def serialize(self) -> bytes:
        data = b"".join(canonical(record) for record in self.records)
        if len(data) > MAX_JOURNAL_BYTES:
            fail("EFFECT_JOURNAL_TOO_LARGE")
        return data

    @classmethod
    def recover(
        cls,
        data: bytes,
        *,
        expected_record_count: int | None = None,
        expected_head_record_sha256: str | None = None,
    ) -> "EffectJournal":
        if not isinstance(data, bytes):
            fail("JOURNAL_BYTES_REQUIRED")
        if len(data) > MAX_JOURNAL_BYTES:
            fail("EFFECT_JOURNAL_TOO_LARGE")
        if (expected_record_count is None) != (
            expected_head_record_sha256 is None
        ):
            fail("EFFECT_JOURNAL_CHECKPOINT_INCOMPLETE")
        if expected_record_count is not None:
            if (
                type(expected_record_count) is not int
                or expected_record_count < 0
                or expected_record_count > MAX_RECORDS
            ):
                fail("EFFECT_JOURNAL_CHECKPOINT_COUNT_INVALID")
            if not is_sha(expected_head_record_sha256):
                fail("EFFECT_JOURNAL_CHECKPOINT_HEAD_INVALID")

        journal = cls()
        complete = data
        if complete and not complete.endswith(b"\n"):
            boundary = complete.rfind(b"\n")
            if len(complete) - boundary - 1 > MAX_RECORD_BYTES:
                fail("EFFECT_JOURNAL_RECORD_TOO_LARGE")
            complete = complete[: boundary + 1] if boundary >= 0 else b""
            journal.discarded_torn_tail = True
        lines = complete.splitlines(keepends=True)
        if len(lines) > MAX_RECORDS:
            fail("EFFECT_JOURNAL_TOO_MANY_RECORDS")
        previous = ZERO
        for expected_sequence, line in enumerate(lines, start=1):
            if len(line) > MAX_RECORD_BYTES:
                fail("EFFECT_JOURNAL_RECORD_TOO_LARGE")
            record = strict_json_loads(line[:-1])
            if not isinstance(record, dict) or set(record) != {
                "schema",
                "sequence",
                "previous_record_sha256",
                "event",
                "record_sha256",
            }:
                fail("EFFECT_JOURNAL_RECORD_FIELD_SET_MISMATCH")
            if record["schema"] != SCHEMA_RECORD:
                fail("EFFECT_JOURNAL_RECORD_SCHEMA_MISMATCH")
            if (
                type(record["sequence"]) is not int
                or record["sequence"] != expected_sequence
            ):
                fail("EFFECT_JOURNAL_SEQUENCE_MISMATCH")
            if record["previous_record_sha256"] != previous:
                fail("EFFECT_JOURNAL_PREVIOUS_HASH_MISMATCH")
            expected_hash = cls._event_hash(
                expected_sequence,
                previous,
                record["event"],
            )
            if record["record_sha256"] != expected_hash:
                fail("EFFECT_JOURNAL_RECORD_HASH_MISMATCH")
            if canonical(record) != line:
                fail("EFFECT_JOURNAL_NONCANONICAL_RECORD")
            cls._apply_event(
                record["event"],
                journal.operations,
                journal.idempotency_keys,
            )
            journal.records.append(copy.deepcopy(record))
            journal._serialized_bytes += len(line)
            previous = expected_hash
        journal.idempotency = journal.idempotency_keys
        if expected_record_count is not None:
            actual_head = (
                journal.records[-1]["record_sha256"]
                if journal.records
                else ZERO
            )
            if (
                len(journal.records) != expected_record_count
                or actual_head != expected_head_record_sha256
            ):
                fail("EFFECT_JOURNAL_CHECKPOINT_MISMATCH")
        return journal


def self_test() -> dict[str, Any]:
    payload = hashlib.sha256(b"fixture payload").hexdigest()
    permit = hashlib.sha256(b"fixture permit").hexdigest()
    subject = hashlib.sha256(b"fixture subject").hexdigest()

    journal = EffectJournal()
    journal.request(
        "op-1",
        "idempotency-1",
        "fixture-write",
        payload,
        permit,
        subject,
    )
    journal.prepare("op-1")
    journal.dispatch(
        "op-1",
        hashlib.sha256(b"fixture dispatch token").hexdigest(),
    )
    journal.mark_indeterminate("op-1", "connection lost after write")
    if (
        journal.automatic_replay_allowed("op-1")
        or not journal.requires_reconciliation("op-1")
    ):
        fail("RECONCILIATION_INVARIANT_FAILED")
    journal.reconcile(
        "op-1",
        "applied",
        hashlib.sha256(b"fixture provider receipt").hexdigest(),
    )
    encoded = journal.serialize()
    recovered = EffectJournal.recover(
        encoded,
        expected_record_count=len(journal.records),
        expected_head_record_sha256=journal.records[-1]["record_sha256"],
    )
    if recovered.snapshot() != journal.snapshot():
        fail("RECOVERY_MISMATCH")

    negative = EffectJournal()
    negative.request(
        "op-2",
        "idempotency-2",
        "fixture-write",
        payload,
        permit,
        subject,
    )
    negative.prepare("op-2")
    negative.dispatch("op-2", hashlib.sha256(b"dispatch-2").hexdigest())
    negative.mark_indeterminate(
        "op-2",
        "provider returned no durable receipt",
    )
    negative.reconcile(
        "op-2",
        "not_applied",
        hashlib.sha256(b"not-applied").hexdigest(),
    )

    return {
        "schema": "trillionnium.desktop.effect-reconciliation-self-test.v1",
        "status": "PASS_EFFECT_RECONCILIATION_REFERENCE",
        "applied_state": journal.operations["op-1"].state.upper(),
        "not_applied_state": negative.operations["op-2"].state.upper(),
        "automatic_replay_after_dispatch": False,
        "external_effects_executed": False,
        "persistent_journal_integrated": False,
        "provider_reconciliation_integrated": False,
        "release_ready": False,
    }


def main() -> int:
    print(json.dumps(self_test(), sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
