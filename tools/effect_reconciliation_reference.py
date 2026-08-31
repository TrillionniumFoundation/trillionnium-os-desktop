#!/usr/bin/env python3
"""Deterministic D7 external-effect journal and reconciliation model.

The journal records facts only. It exposes no external-effect execution or
replay API. Once dispatch has been recorded, crash recovery can only reconcile
or require manual action.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "contracts" / "recovery-update-reconciliation.v1.json"
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
TERMINAL = {
    "terminal_success",
    "terminal_failure",
    "reconciled_applied",
    "reconciled_not_applied",
    "manual_required",
    "cancelled_before_dispatch",
}


class EffectError(ValueError):
    def __init__(self, reason: str, detail: str | None = None) -> None:
        super().__init__(reason if detail is None else f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def fail(reason: str, detail: str | None = None) -> None:
    raise EffectError(reason, detail)


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def require_digest(value: Any, reason: str) -> str:
    if not isinstance(value, str) or not HEX_64.fullmatch(value):
        fail(reason)
    return value


def require_id(value: Any, reason: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        fail(reason)
    return value


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
        self.operations: dict[str, EffectOperation] = {}
        self.idempotency_keys: dict[str, str] = {}
        self.records: list[dict[str, Any]] = []
        self.discarded_torn_tail = False

    def _event_hash(self, sequence: int, previous: str, event: dict[str, Any]) -> str:
        return digest(
            {
                "sequence": sequence,
                "previous_record_sha256": previous,
                "event": event,
            }
        )

    def _append(self, event: dict[str, Any]) -> dict[str, Any]:
        event_copy = copy.deepcopy(event)
        self._apply_event(event_copy)
        sequence = len(self.records) + 1
        previous = self.records[-1]["record_sha256"] if self.records else "0" * 64
        record = {
            "schema": "trillionnium.desktop.effect-journal-record.v1",
            "sequence": sequence,
            "previous_record_sha256": previous,
            "event": event_copy,
        }
        record["record_sha256"] = self._event_hash(sequence, previous, event_copy)
        self.records.append(record)
        return copy.deepcopy(record)

    def _operation(self, operation_id: Any) -> EffectOperation:
        operation_id = require_id(operation_id, "INVALID_OPERATION_ID")
        operation = self.operations.get(operation_id)
        if operation is None:
            fail("UNKNOWN_OPERATION", operation_id)
        return operation

    def _apply_event(self, event: dict[str, Any]) -> None:
        if not isinstance(event, dict) or "kind" not in event:
            fail("INVALID_EFFECT_EVENT")
        kind = event["kind"]
        if kind == "request":
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
                fail("REQUEST_EVENT_FIELD_SET_MISMATCH")
            operation_id = require_id(event["operation_id"], "INVALID_OPERATION_ID")
            idempotency_key = require_id(event["idempotency_key"], "INVALID_IDEMPOTENCY_KEY")
            if operation_id in self.operations:
                fail("DUPLICATE_OPERATION_ID", operation_id)
            if idempotency_key in self.idempotency_keys:
                fail("DUPLICATE_IDEMPOTENCY_KEY", idempotency_key)
            effect_kind = require_id(event["effect_kind"], "INVALID_EFFECT_KIND")
            operation = EffectOperation(
                operation_id=operation_id,
                idempotency_key=idempotency_key,
                effect_kind=effect_kind,
                payload_sha256=require_digest(event["payload_sha256"], "INVALID_PAYLOAD_DIGEST"),
                permit_sha256=require_digest(event["permit_sha256"], "INVALID_PERMIT_DIGEST"),
                subject_sha256=require_digest(event["subject_sha256"], "INVALID_SUBJECT_DIGEST"),
            )
            self.operations[operation_id] = operation
            self.idempotency_keys[idempotency_key] = operation_id
            return

        operation = self._operation(event.get("operation_id"))
        if kind == "prepare":
            if set(event) != {"kind", "operation_id"}:
                fail("PREPARE_EVENT_FIELD_SET_MISMATCH")
            if operation.state != "requested":
                fail("INVALID_EFFECT_TRANSITION", f"{operation.state}->prepared")
            operation.state = "prepared"
            return
        if kind == "cancel":
            if set(event) != {"kind", "operation_id", "reason"}:
                fail("CANCEL_EVENT_FIELD_SET_MISMATCH")
            if operation.state not in {"requested", "prepared"}:
                fail("CANCEL_AFTER_DISPATCH_FORBIDDEN")
            if not isinstance(event["reason"], str) or not event["reason"]:
                fail("CANCEL_REASON_REQUIRED")
            operation.state = "cancelled_before_dispatch"
            return
        if kind == "dispatch":
            if set(event) != {"kind", "operation_id", "dispatch_token_sha256"}:
                fail("DISPATCH_EVENT_FIELD_SET_MISMATCH")
            if operation.state != "prepared":
                fail("INVALID_EFFECT_TRANSITION", f"{operation.state}->dispatched")
            operation.dispatch_token_sha256 = require_digest(
                event["dispatch_token_sha256"], "INVALID_DISPATCH_TOKEN_DIGEST"
            )
            operation.state = "dispatched"
            return
        if kind == "terminal":
            if set(event) != {
                "kind",
                "operation_id",
                "outcome",
                "provider_receipt_sha256",
            }:
                fail("TERMINAL_EVENT_FIELD_SET_MISMATCH")
            if operation.state not in {"dispatched", "indeterminate"}:
                fail("INVALID_EFFECT_TRANSITION", f"{operation.state}->terminal")
            outcome = event["outcome"]
            if outcome not in {"success", "failure"}:
                fail("INVALID_TERMINAL_OUTCOME")
            operation.provider_receipt_sha256 = require_digest(
                event["provider_receipt_sha256"], "INVALID_PROVIDER_RECEIPT_DIGEST"
            )
            operation.state = f"terminal_{outcome}"
            return
        if kind == "indeterminate":
            if set(event) != {"kind", "operation_id", "reason"}:
                fail("INDETERMINATE_EVENT_FIELD_SET_MISMATCH")
            if operation.state != "dispatched":
                fail("INVALID_EFFECT_TRANSITION", f"{operation.state}->indeterminate")
            if not isinstance(event["reason"], str) or not event["reason"]:
                fail("INDETERMINATE_REASON_REQUIRED")
            operation.state = "indeterminate"
            return
        if kind == "reconcile":
            if set(event) != {
                "kind",
                "operation_id",
                "observation",
                "provider_receipt_sha256",
            }:
                fail("RECONCILIATION_EVENT_FIELD_SET_MISMATCH")
            if operation.state not in {"dispatched", "indeterminate"}:
                fail("RECONCILIATION_NOT_ALLOWED", operation.state)
            observation = event["observation"]
            if observation not in {"applied", "not_applied", "unknown"}:
                fail("INVALID_RECONCILIATION_OBSERVATION")
            operation.provider_receipt_sha256 = require_digest(
                event["provider_receipt_sha256"], "INVALID_PROVIDER_RECEIPT_DIGEST"
            )
            if observation == "applied":
                operation.state = "reconciled_applied"
            elif observation == "not_applied":
                operation.state = "reconciled_not_applied"
                operation.retry_requires_new_authorization = True
            else:
                operation.state = "manual_required"
            return
        fail("UNKNOWN_EFFECT_EVENT", str(kind))

    def request(
        self,
        operation_id: str,
        idempotency_key: str,
        effect_kind: str,
        payload_sha256: str,
        permit_sha256: str,
        subject_sha256: str,
    ) -> dict[str, Any]:
        return self._append(
            {
                "kind": "request",
                "operation_id": operation_id,
                "idempotency_key": idempotency_key,
                "effect_kind": effect_kind,
                "payload_sha256": payload_sha256,
                "permit_sha256": permit_sha256,
                "subject_sha256": subject_sha256,
            }
        )

    def prepare(self, operation_id: str) -> dict[str, Any]:
        return self._append({"kind": "prepare", "operation_id": operation_id})

    def cancel(self, operation_id: str, reason: str) -> dict[str, Any]:
        return self._append({"kind": "cancel", "operation_id": operation_id, "reason": reason})

    def dispatch(self, operation_id: str, dispatch_token_sha256: str) -> dict[str, Any]:
        return self._append(
            {
                "kind": "dispatch",
                "operation_id": operation_id,
                "dispatch_token_sha256": dispatch_token_sha256,
            }
        )

    def terminal(
        self, operation_id: str, outcome: str, provider_receipt_sha256: str
    ) -> dict[str, Any]:
        return self._append(
            {
                "kind": "terminal",
                "operation_id": operation_id,
                "outcome": outcome,
                "provider_receipt_sha256": provider_receipt_sha256,
            }
        )

    def indeterminate(self, operation_id: str, reason: str) -> dict[str, Any]:
        return self._append(
            {"kind": "indeterminate", "operation_id": operation_id, "reason": reason}
        )

    def reconcile(
        self,
        operation_id: str,
        observation: str,
        provider_receipt_sha256: str,
    ) -> dict[str, Any]:
        return self._append(
            {
                "kind": "reconcile",
                "operation_id": operation_id,
                "observation": observation,
                "provider_receipt_sha256": provider_receipt_sha256,
            }
        )

    def recovery_action(self, operation_id: str) -> str:
        state = self._operation(operation_id).state
        if state in {"requested", "prepared"}:
            return "PRE_EFFECT_SAFE_TO_CANCEL_OR_REPREPARE"
        if state in {"dispatched", "indeterminate"}:
            return "RECONCILE_ONLY_NEVER_AUTOMATICALLY_REPLAY"
        if state == "manual_required":
            return "MANUAL_ACTION_REQUIRED"
        if state in TERMINAL:
            return "NO_ACTION_TERMINAL"
        fail("UNKNOWN_EFFECT_STATE", state)

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema": "trillionnium.desktop.effect-journal-snapshot.v1",
            "operations": {
                key: asdict(value) for key, value in sorted(self.operations.items())
            },
            "record_count": len(self.records),
            "head_record_sha256": self.records[-1]["record_sha256"] if self.records else "0" * 64,
            "discarded_torn_tail": self.discarded_torn_tail,
            "journal_executes_operations": False,
            "automatic_replay_after_dispatch": False,
        }

    def serialize(self) -> bytes:
        return b"".join(canonical(record) for record in self.records)

    @classmethod
    def recover(cls, data: bytes) -> "EffectJournal":
        journal = cls()
        if not isinstance(data, bytes):
            fail("JOURNAL_BYTES_REQUIRED")
        complete = data
        if complete and not complete.endswith(b"\n"):
            split = complete.rfind(b"\n")
            complete = complete[: split + 1] if split >= 0 else b""
            journal.discarded_torn_tail = True
        previous = "0" * 64
        for expected_sequence, line in enumerate(complete.splitlines(), start=1):
            try:
                record = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise EffectError("EFFECT_JOURNAL_CORRUPT_RECORD") from error
            if not isinstance(record, dict) or set(record) != {
                "schema",
                "sequence",
                "previous_record_sha256",
                "event",
                "record_sha256",
            }:
                fail("EFFECT_JOURNAL_RECORD_FIELD_SET_MISMATCH")
            if record["schema"] != "trillionnium.desktop.effect-journal-record.v1":
                fail("EFFECT_JOURNAL_RECORD_SCHEMA_MISMATCH")
            if record["sequence"] != expected_sequence:
                fail("EFFECT_JOURNAL_SEQUENCE_MISMATCH")
            if record["previous_record_sha256"] != previous:
                fail("EFFECT_JOURNAL_PREVIOUS_HASH_MISMATCH")
            expected_hash = journal._event_hash(
                expected_sequence, previous, record["event"]
            )
            if record["record_sha256"] != expected_hash:
                fail("EFFECT_JOURNAL_RECORD_HASH_MISMATCH")
            journal._apply_event(copy.deepcopy(record["event"]))
            journal.records.append(copy.deepcopy(record))
            previous = expected_hash
        return journal


def self_test() -> dict[str, Any]:
    journal = EffectJournal()
    payload = hashlib.sha256(b"fixture payload").hexdigest()
    permit = hashlib.sha256(b"fixture permit").hexdigest()
    subject = hashlib.sha256(b"fixture subject").hexdigest()
    dispatch = hashlib.sha256(b"fixture dispatch token").hexdigest()
    provider = hashlib.sha256(b"fixture provider observation").hexdigest()
    journal.request("operation-1", "idempotency-1", "fixture-write", payload, permit, subject)
    journal.prepare("operation-1")
    journal.dispatch("operation-1", dispatch)
    journal.indeterminate("operation-1", "connection_lost_after_dispatch")
    if journal.recovery_action("operation-1") != "RECONCILE_ONLY_NEVER_AUTOMATICALLY_REPLAY":
        raise AssertionError("indeterminate operation was not reconciliation-only")
    journal.reconcile("operation-1", "applied", provider)
    recovered = EffectJournal.recover(journal.serialize())
    if recovered.snapshot() != journal.snapshot():
        raise AssertionError("effect journal replay diverged")
    return {
        "schema": "trillionnium.desktop.effect-reconciliation-self-test.v1",
        "status": "PASS_SOURCE_REFERENCE_ONLY",
        "record_count": len(journal.records),
        "head_record_sha256": journal.records[-1]["record_sha256"],
        "operation_state": journal.operations["operation-1"].state,
        "automatic_replay_after_dispatch": False,
        "external_effect_executor_integrated": False,
        "provider_reconciliation_integrated": False,
        "persistent_journal_integrated": False,
        "external_effects_enabled": False,
        "release_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--write-result", type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    if contract.get("status") != "SOURCE_CANDIDATE_BLOCKED_UPSTREAM_D6":
        raise SystemExit("D7 contract status widened unexpectedly")
    result = self_test()
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.write_result:
        args.write_result.parent.mkdir(parents=True, exist_ok=True)
        args.write_result.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
