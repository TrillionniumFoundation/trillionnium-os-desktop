#!/usr/bin/env python3
"""Deterministic D4 human/Agent collaboration reference model.

This module is deliberately pure: it owns no socket, browser, clipboard,
window, input device, credential, or external-effect authority. It specifies
admission, invalidation, preemption, and receipt semantics for later binding to
the single D3 PageOwner.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "contracts" / "human-agent-collaboration.v1.json"
MAX_HUMAN_LEASE_MS = 30_000
MAX_CLIPBOARD_BYTES = 1_048_576


def canonical(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


@dataclass(frozen=True)
class TargetRef:
    session_id: str
    page_owner_id: str
    surface_generation: int
    document_generation: int
    semantic_revision: int
    target_id: str

    @classmethod
    def from_value(cls, value: dict[str, Any]) -> "TargetRef":
        required = {
            "session_id",
            "page_owner_id",
            "surface_generation",
            "document_generation",
            "semantic_revision",
            "target_id",
        }
        if set(value) != required:
            raise ValueError("target reference fields are not canonical")
        result = cls(
            session_id=str(value["session_id"]),
            page_owner_id=str(value["page_owner_id"]),
            surface_generation=int(value["surface_generation"]),
            document_generation=int(value["document_generation"]),
            semantic_revision=int(value["semantic_revision"]),
            target_id=str(value["target_id"]),
        )
        if not result.target_id or len(result.target_id) > 256:
            raise ValueError("target_id is outside the bounded domain")
        return result


@dataclass
class Lease:
    epoch: int
    expires_at_ms: int


@dataclass
class Drag:
    actor: str
    source: TargetRef


@dataclass
class CollaborationState:
    session_id: str
    page_owner_id: str
    surface_generation: int = 1
    document_generation: int = 1
    semantic_revision: int = 0
    target_counts: dict[str, int] = field(default_factory=dict)
    active_actor: str = "none"
    human_lease: Lease | None = None
    lease_epoch: int = 0
    agent_epoch: int = 0
    human_preemption_epoch: int = 0
    focused_target: TargetRef | None = None
    ime_owner: str = "none"
    ime_target: TargetRef | None = None
    modal_stack: list[str] = field(default_factory=list)
    clipboard_version: int = 0
    clipboard_sha256: str | None = None
    clipboard_bytes: int = 0
    clipboard_writer: str | None = None
    drag: Drag | None = None
    visible: bool = True
    surface_exists: bool = True
    hidden_page_count: int = 0
    crash_count: int = 0
    navigation_count: int = 0


@dataclass(frozen=True)
class Outcome:
    admitted: bool
    reason: str
    details: dict[str, Any] = field(default_factory=dict)


class CollaborationModel:
    def __init__(self, session_id: str, page_owner_id: str) -> None:
        if not session_id or not page_owner_id:
            raise ValueError("session_id and page_owner_id are required")
        self.state = CollaborationState(session_id=session_id, page_owner_id=page_owner_id)
        self.receipts: list[dict[str, Any]] = []
        self.trace: list[dict[str, Any]] = []

    def current_ref(self, target_id: str) -> TargetRef:
        return TargetRef(
            session_id=self.state.session_id,
            page_owner_id=self.state.page_owner_id,
            surface_generation=self.state.surface_generation,
            document_generation=self.state.document_generation,
            semantic_revision=self.state.semantic_revision,
            target_id=target_id,
        )

    def state_value(self) -> dict[str, Any]:
        return asdict(self.state)

    def state_hash(self) -> str:
        return digest(self.state_value())

    def _expire_lease(self, now_ms: int) -> None:
        lease = self.state.human_lease
        if lease is not None and now_ms >= lease.expires_at_ms:
            self.state.human_lease = None
            if self.state.active_actor == "human":
                self.state.active_actor = "none"

    def _actor_allowed(self, actor: str, now_ms: int) -> Outcome | None:
        if actor not in {"human", "agent"}:
            return Outcome(False, "UNKNOWN_ACTOR")
        self._expire_lease(now_ms)
        if actor == "agent" and self.state.human_lease is not None:
            return Outcome(False, "ACTIVE_HUMAN_LEASE")
        return None

    def _validate_ref(self, raw: Any, *, modal_scoped: bool = True) -> tuple[TargetRef | None, Outcome | None]:
        if not isinstance(raw, dict):
            return None, Outcome(False, "TARGET_REFERENCE_REQUIRED")
        try:
            reference = TargetRef.from_value(raw)
        except (TypeError, ValueError) as error:
            return None, Outcome(False, "INVALID_TARGET_REFERENCE", {"error": str(error)})
        expected = self.current_ref(reference.target_id)
        identity_fields = (
            "session_id",
            "page_owner_id",
            "surface_generation",
            "document_generation",
            "semantic_revision",
        )
        for name in identity_fields:
            if getattr(reference, name) != getattr(expected, name):
                return None, Outcome(False, "STALE_TARGET_REFERENCE", {"field": name})
        count = self.state.target_counts.get(reference.target_id, 0)
        if count == 0:
            return None, Outcome(False, "TARGET_NOT_FOUND")
        if count != 1:
            return None, Outcome(False, "AMBIGUOUS_TARGET_REFERENCE", {"match_count": count})
        if modal_scoped and self.state.modal_stack:
            top = self.state.modal_stack[-1]
            if reference.target_id != top:
                return None, Outcome(False, "BACKGROUND_TARGET_BLOCKED_BY_MODAL", {"modal_target": top})
        return reference, None

    def _invalidate_document_state(self) -> None:
        self.state.semantic_revision = 0
        self.state.target_counts.clear()
        self.state.focused_target = None
        self.state.ime_owner = "none"
        self.state.ime_target = None
        self.state.modal_stack.clear()
        self.state.drag = None
        self.state.active_actor = "none"
        self.state.agent_epoch += 1

    def _apply(self, operation: dict[str, Any], now_ms: int) -> Outcome:
        kind = operation.get("kind")
        actor = str(operation.get("actor", "none"))

        if kind == "publish_semantic_snapshot":
            targets = operation.get("targets")
            if not isinstance(targets, list) or not all(isinstance(item, str) and item for item in targets):
                return Outcome(False, "INVALID_SEMANTIC_SNAPSHOT")
            if len(targets) > 4096:
                return Outcome(False, "SEMANTIC_SNAPSHOT_TOO_LARGE")
            counts: dict[str, int] = {}
            for target in targets:
                counts[target] = counts.get(target, 0) + 1
            self.state.semantic_revision += 1
            self.state.target_counts = counts
            self.state.focused_target = None
            self.state.ime_owner = "none"
            self.state.ime_target = None
            self.state.drag = None
            return Outcome(True, "SEMANTIC_SNAPSHOT_PUBLISHED", {"target_count": len(targets)})

        if kind == "acquire_human_lease":
            if actor != "human":
                return Outcome(False, "HUMAN_ACTOR_REQUIRED")
            duration = operation.get("duration_ms")
            if not isinstance(duration, int) or not 1 <= duration <= MAX_HUMAN_LEASE_MS:
                return Outcome(False, "INVALID_HUMAN_LEASE_DURATION")
            self.state.lease_epoch += 1
            self.state.agent_epoch += 1
            self.state.active_actor = "human"
            self.state.human_lease = Lease(
                epoch=self.state.lease_epoch,
                expires_at_ms=now_ms + duration,
            )
            return Outcome(True, "HUMAN_LEASE_ACQUIRED", {"lease_epoch": self.state.lease_epoch})

        if kind == "release_human_lease":
            if actor != "human":
                return Outcome(False, "HUMAN_ACTOR_REQUIRED")
            self._expire_lease(now_ms)
            if self.state.human_lease is None:
                return Outcome(False, "NO_ACTIVE_HUMAN_LEASE")
            expected_epoch = operation.get("lease_epoch")
            if expected_epoch != self.state.human_lease.epoch:
                return Outcome(False, "STALE_HUMAN_LEASE")
            self.state.human_lease = None
            if self.state.active_actor == "human":
                self.state.active_actor = "none"
            return Outcome(True, "HUMAN_LEASE_RELEASED")

        if kind == "human_input":
            if actor != "human":
                return Outcome(False, "HUMAN_ACTOR_REQUIRED")
            self.state.human_preemption_epoch += 1
            self.state.agent_epoch += 1
            self.state.active_actor = "human"
            if self.state.ime_owner == "agent":
                self.state.ime_owner = "none"
                self.state.ime_target = None
            if self.state.drag is not None and self.state.drag.actor == "agent":
                self.state.drag = None
            return Outcome(
                True,
                "HUMAN_INPUT_PREEMPTED_AGENT",
                {"preemption_epoch": self.state.human_preemption_epoch},
            )

        if kind == "agent_begin":
            blocked = self._actor_allowed(actor, now_ms)
            if blocked is not None:
                return blocked
            if actor != "agent":
                return Outcome(False, "AGENT_ACTOR_REQUIRED")
            expected_epoch = operation.get("agent_epoch")
            if expected_epoch != self.state.agent_epoch:
                return Outcome(False, "STALE_AGENT_EPOCH", {"current": self.state.agent_epoch})
            self.state.active_actor = "agent"
            return Outcome(True, "AGENT_TURN_STARTED", {"agent_epoch": self.state.agent_epoch})

        if kind in {
            "focus_target",
            "claim_ime",
            "clipboard_write",
            "clipboard_read",
            "drag_start",
            "drop",
            "open_modal",
            "close_modal",
            "navigate",
            "minimize",
            "show",
        }:
            blocked = self._actor_allowed(actor, now_ms)
            if blocked is not None:
                return blocked

        if kind == "focus_target":
            reference, rejected = self._validate_ref(operation.get("target"))
            if rejected is not None:
                return rejected
            self.state.focused_target = reference
            self.state.active_actor = actor
            return Outcome(True, "TARGET_FOCUSED")

        if kind == "claim_ime":
            reference, rejected = self._validate_ref(operation.get("target"))
            if rejected is not None:
                return rejected
            if self.state.ime_owner not in {"none", actor}:
                return Outcome(False, "IME_ALREADY_OWNED", {"owner": self.state.ime_owner})
            self.state.ime_owner = actor
            self.state.ime_target = reference
            self.state.focused_target = reference
            self.state.active_actor = actor
            return Outcome(True, "IME_OWNERSHIP_ACQUIRED")

        if kind == "release_ime":
            if actor not in {"human", "agent"}:
                return Outcome(False, "UNKNOWN_ACTOR")
            if self.state.ime_owner != actor:
                return Outcome(False, "IME_NOT_OWNED_BY_ACTOR")
            self.state.ime_owner = "none"
            self.state.ime_target = None
            return Outcome(True, "IME_OWNERSHIP_RELEASED")

        if kind == "clipboard_write":
            value = operation.get("value")
            if not isinstance(value, str):
                return Outcome(False, "CLIPBOARD_TEXT_REQUIRED")
            encoded = value.encode("utf-8")
            if len(encoded) > MAX_CLIPBOARD_BYTES:
                return Outcome(False, "CLIPBOARD_VALUE_TOO_LARGE")
            expected = operation.get("expected_version")
            if expected != self.state.clipboard_version:
                return Outcome(False, "CLIPBOARD_VERSION_MISMATCH", {"current": self.state.clipboard_version})
            self.state.clipboard_version += 1
            self.state.clipboard_sha256 = hashlib.sha256(encoded).hexdigest()
            self.state.clipboard_bytes = len(encoded)
            self.state.clipboard_writer = actor
            return Outcome(
                True,
                "MEDIATED_CLIPBOARD_WRITTEN",
                {"version": self.state.clipboard_version, "sha256": self.state.clipboard_sha256},
            )

        if kind == "clipboard_read":
            expected = operation.get("expected_version")
            if expected != self.state.clipboard_version:
                return Outcome(False, "CLIPBOARD_VERSION_MISMATCH", {"current": self.state.clipboard_version})
            return Outcome(
                True,
                "MEDIATED_CLIPBOARD_METADATA_READ",
                {
                    "version": self.state.clipboard_version,
                    "sha256": self.state.clipboard_sha256,
                    "bytes": self.state.clipboard_bytes,
                },
            )

        if kind == "drag_start":
            if self.state.drag is not None:
                return Outcome(False, "DRAG_ALREADY_ACTIVE")
            reference, rejected = self._validate_ref(operation.get("source"))
            if rejected is not None:
                return rejected
            self.state.drag = Drag(actor=actor, source=reference)
            self.state.active_actor = actor
            return Outcome(True, "DRAG_STARTED")

        if kind == "drop":
            if self.state.drag is None:
                return Outcome(False, "NO_ACTIVE_DRAG")
            if self.state.drag.actor != actor:
                return Outcome(False, "DRAG_OWNED_BY_OTHER_ACTOR")
            destination, rejected = self._validate_ref(operation.get("destination"))
            if rejected is not None:
                return rejected
            source = self.state.drag.source
            self.state.drag = None
            return Outcome(
                True,
                "MEDIATED_DROP_ADMITTED",
                {"source": source.target_id, "destination": destination.target_id},
            )

        if kind == "open_modal":
            reference, rejected = self._validate_ref(operation.get("target"), modal_scoped=False)
            if rejected is not None:
                return rejected
            if self.state.modal_stack and self.state.modal_stack[-1] == reference.target_id:
                return Outcome(False, "MODAL_ALREADY_TOPMOST")
            self.state.modal_stack.append(reference.target_id)
            self.state.focused_target = reference
            return Outcome(True, "MODAL_OPENED", {"depth": len(self.state.modal_stack)})

        if kind == "close_modal":
            target_id = operation.get("target_id")
            if not self.state.modal_stack:
                return Outcome(False, "NO_ACTIVE_MODAL")
            if target_id != self.state.modal_stack[-1]:
                return Outcome(False, "ONLY_TOPMOST_MODAL_MAY_CLOSE")
            self.state.modal_stack.pop()
            self.state.focused_target = None
            self.state.ime_owner = "none"
            self.state.ime_target = None
            return Outcome(True, "MODAL_CLOSED", {"depth": len(self.state.modal_stack)})

        if kind == "navigate":
            url = operation.get("url")
            if not isinstance(url, str) or not (
                url.startswith("hepta://fixture/") or url.startswith("http://127.0.0.1:")
            ):
                return Outcome(False, "EXTERNAL_NAVIGATION_NOT_AUTHORIZED")
            self.state.document_generation += 1
            self.state.navigation_count += 1
            self._invalidate_document_state()
            return Outcome(True, "LOCAL_FIXTURE_NAVIGATION_COMMITTED")

        if kind == "content_crash_recover":
            self.state.surface_generation += 1
            self.state.document_generation += 1
            self.state.crash_count += 1
            self.state.human_lease = None
            self._invalidate_document_state()
            return Outcome(True, "CONTENT_SURFACE_RECOVERED")

        if kind == "minimize":
            if not self.state.visible:
                return Outcome(False, "ALREADY_MINIMIZED")
            self.state.visible = False
            return Outcome(True, "SURFACE_MINIMIZED_WITHOUT_HIDDEN_PAGE")

        if kind == "show":
            if self.state.visible:
                return Outcome(False, "ALREADY_VISIBLE")
            self.state.visible = True
            return Outcome(True, "SURFACE_SHOWN")

        return Outcome(False, "UNKNOWN_OPERATION")

    def apply(self, operation: dict[str, Any], now_ms: int) -> dict[str, Any]:
        if not isinstance(operation, dict):
            raise TypeError("operation must be an object")
        if not isinstance(now_ms, int) or now_ms < 0:
            raise ValueError("now_ms must be a non-negative integer")
        before = self.state_hash()
        previous = self.receipts[-1]["receipt_hash"] if self.receipts else "0" * 64
        operation_copy = copy.deepcopy(operation)
        outcome = self._apply(operation_copy, now_ms)
        after = self.state_hash()
        receipt: dict[str, Any] = {
            "schema": "trillionnium.desktop.d4-operation-receipt.v1",
            "sequence": len(self.receipts) + 1,
            "previous_receipt_hash": previous,
            "now_ms": now_ms,
            "operation": operation_copy,
            "admitted": outcome.admitted,
            "reason": outcome.reason,
            "details": outcome.details,
            "state_before_sha256": before,
            "state_after_sha256": after,
        }
        receipt["receipt_hash"] = digest(receipt)
        self.receipts.append(receipt)
        self.trace.append({"now_ms": now_ms, "operation": operation_copy})
        self.assert_invariants()
        return copy.deepcopy(receipt)

    def assert_invariants(self) -> None:
        state = self.state
        if state.hidden_page_count != 0:
            raise AssertionError("hidden pages are forbidden")
        if not state.surface_exists:
            raise AssertionError("the single PageOwner surface must exist")
        if state.ime_owner not in {"none", "human", "agent"}:
            raise AssertionError("invalid IME owner")
        if (state.ime_owner == "none") != (state.ime_target is None):
            raise AssertionError("IME owner and target must change atomically")
        if state.drag is not None and state.drag.actor not in {"human", "agent"}:
            raise AssertionError("invalid drag actor")
        if state.human_lease is not None and state.human_lease.epoch != state.lease_epoch:
            raise AssertionError("human lease epoch drift")
        if state.surface_generation < 1 or state.document_generation < 1:
            raise AssertionError("generation counters must be positive")

    @staticmethod
    def verify_receipt_chain(receipts: Iterable[dict[str, Any]]) -> None:
        previous = "0" * 64
        for expected_sequence, original in enumerate(receipts, start=1):
            receipt = copy.deepcopy(original)
            claimed = receipt.pop("receipt_hash", None)
            if receipt.get("sequence") != expected_sequence:
                raise ValueError("receipt sequence mismatch")
            if receipt.get("previous_receipt_hash") != previous:
                raise ValueError("receipt previous hash mismatch")
            actual = digest(receipt)
            if claimed != actual:
                raise ValueError("receipt hash mismatch")
            previous = actual

    def replay(self) -> "CollaborationModel":
        replayed = CollaborationModel(self.state.session_id, self.state.page_owner_id)
        for item in self.trace:
            replayed.apply(copy.deepcopy(item["operation"]), item["now_ms"])
        self.verify_receipt_chain(replayed.receipts)
        if replayed.receipts != self.receipts:
            raise ValueError("trace replay receipts diverged")
        if replayed.state_value() != self.state_value():
            raise ValueError("trace replay state diverged")
        return replayed


def self_test() -> dict[str, Any]:
    model = CollaborationModel("session-1", "page-owner-1")
    model.apply({"kind": "publish_semantic_snapshot", "targets": ["field", "button", "modal"]}, 0)
    field = asdict(model.current_ref("field"))
    model.apply({"kind": "acquire_human_lease", "actor": "human", "duration_ms": 1000}, 10)
    blocked = model.apply({"kind": "agent_begin", "actor": "agent", "agent_epoch": 1}, 20)
    if blocked["admitted"] or blocked["reason"] != "ACTIVE_HUMAN_LEASE":
        raise AssertionError("active human lease did not block agent")
    model.apply({"kind": "human_input", "actor": "human"}, 30)
    model.apply({"kind": "claim_ime", "actor": "human", "target": field}, 40)
    model.apply({"kind": "navigate", "actor": "human", "url": "hepta://fixture/next"}, 50)
    stale = model.apply({"kind": "focus_target", "actor": "human", "target": field}, 60)
    if stale["admitted"] or stale["reason"] != "STALE_TARGET_REFERENCE":
        raise AssertionError("navigation did not invalidate target reference")
    model.replay()
    return {
        "schema": "trillionnium.desktop.d4-reference-self-test.v1",
        "status": "PASS_SOURCE_REFERENCE_ONLY",
        "operation_count": len(model.receipts),
        "final_state_sha256": model.state_hash(),
        "last_receipt_sha256": model.receipts[-1]["receipt_hash"],
        "browser_actor_runtime_integrated": False,
        "native_input_integrated": False,
        "system_clipboard_integrated": False,
        "external_effects_enabled": False,
        "release_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--write-result", type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    if contract["status"] != "SOURCE_CANDIDATE_BLOCKED_UPSTREAM_D3":
        raise SystemExit("D4 contract status widened unexpectedly")
    if any(
        contract["claim_ceiling"][key]
        for key in (
            "browser_actor_runtime_integrated",
            "native_input_integrated",
            "system_clipboard_integrated",
            "desktop_drag_drop_integrated",
            "external_navigation_enabled",
            "external_effects_enabled",
            "hardware_qualified",
            "release_ready",
        )
    ):
        raise SystemExit("D4 claim ceiling widened unexpectedly")
    result = self_test()
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.write_result:
        args.write_result.parent.mkdir(parents=True, exist_ok=True)
        args.write_result.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
