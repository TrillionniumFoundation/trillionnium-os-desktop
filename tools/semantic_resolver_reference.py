#!/usr/bin/env python3
"""Independent fail-closed reference for the D3 atomic semantic resolver.

This module deliberately owns no Servo object and performs no external effect.
It defines the minimum resolve/retain/revalidate/act semantics that a real Servo
adapter must implement as one engine-owned bounded operation.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import threading
import time
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import Final

SCHEMA: Final[str] = "trillionnium.desktop.semantic-resolver.v1"
RESULT_SCHEMA: Final[str] = "trillionnium.desktop.semantic-resolver.reference-result.v1"


class ResolverError(RuntimeError):
    """A typed fail-closed resolver error."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclasses.dataclass(frozen=True, slots=True)
class Revisions:
    session_generation: int
    document_generation: int
    semantic_snapshot_revision: int
    mutation_epoch: int

    def validate(self) -> None:
        for field in dataclasses.fields(self):
            value = getattr(self, field.name)
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise ResolverError("invalid_request", f"{field.name} must be a non-negative integer")


@dataclasses.dataclass(frozen=True, slots=True)
class SemanticNode:
    frame_id: str
    semantic_id: str
    role: str
    accessible_name: str
    structural_fingerprint: str
    value: str = ""
    checked: bool | None = None
    enabled: bool = True
    visible: bool = True

    def validate(self) -> None:
        for name in (
            "frame_id",
            "semantic_id",
            "role",
            "accessible_name",
            "structural_fingerprint",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ResolverError("invalid_snapshot", f"node {name} must be non-empty")


@dataclasses.dataclass(frozen=True, slots=True)
class SemanticSnapshot:
    session_id: str
    revisions: Revisions
    nodes: tuple[SemanticNode, ...]

    def validate(self) -> None:
        if not self.session_id:
            raise ResolverError("invalid_snapshot", "session_id must be non-empty")
        self.revisions.validate()
        for node in self.nodes:
            node.validate()


@dataclasses.dataclass(frozen=True, slots=True)
class TargetBinding:
    session_id: str
    revisions: Revisions
    frame_id: str
    semantic_id: str
    role: str
    accessible_name: str
    structural_fingerprint: str

    def validate(self) -> None:
        if not self.session_id:
            raise ResolverError("invalid_request", "session_id must be non-empty")
        self.revisions.validate()
        for name in (
            "frame_id",
            "semantic_id",
            "role",
            "accessible_name",
            "structural_fingerprint",
        ):
            value = getattr(self, name)
            if not isinstance(value, str) or not value:
                raise ResolverError("invalid_request", f"{name} must be non-empty")


@dataclasses.dataclass(frozen=True, slots=True)
class SemanticAction:
    kind: str
    value: str | bool | None = None

    def validate(self) -> None:
        if not isinstance(self.kind, str) or not self.kind:
            raise ResolverError("invalid_request", "action kind must be non-empty")


@dataclasses.dataclass(frozen=True, slots=True)
class ActionReceipt:
    session_id: str
    frame_id: str
    semantic_id: str
    action: str
    mutation_epoch_before: int
    mutation_epoch_after: int
    action_count: int


@dataclasses.dataclass(slots=True)
class _MutableNode:
    node: SemanticNode
    action_count: int = 0


class AtomicSemanticResolver:
    """In-memory model of one engine-owned resolve-and-act critical section."""

    def __init__(self, snapshot: SemanticSnapshot, role_action_policy: Mapping[str, set[str]]) -> None:
        snapshot.validate()
        self._lock = threading.RLock()
        self._session_id = snapshot.session_id
        self._revisions = snapshot.revisions
        self._nodes = [_MutableNode(node) for node in snapshot.nodes]
        self._policy = {role: frozenset(actions) for role, actions in role_action_policy.items()}
        self._focused_semantic_id: str | None = None

    def snapshot(self) -> SemanticSnapshot:
        with self._lock:
            return SemanticSnapshot(
                session_id=self._session_id,
                revisions=self._revisions,
                nodes=tuple(item.node for item in self._nodes),
            )

    def replace_snapshot(self, snapshot: SemanticSnapshot) -> None:
        snapshot.validate()
        with self._lock:
            self._session_id = snapshot.session_id
            self._revisions = snapshot.revisions
            self._nodes = [_MutableNode(node) for node in snapshot.nodes]
            self._focused_semantic_id = None

    def _check_deadline_and_cancellation(self, deadline_ns: int | None, cancelled: bool) -> None:
        if cancelled:
            raise ResolverError("cancelled", "operation was cancelled before action")
        if deadline_ns is not None and time.monotonic_ns() >= deadline_ns:
            raise ResolverError("deadline_exceeded", "operation deadline expired")

    def _check_revisions(self, expected: Revisions) -> None:
        actual = self._revisions
        checks = (
            ("stale_session_generation", expected.session_generation, actual.session_generation),
            ("stale_document_generation", expected.document_generation, actual.document_generation),
            (
                "stale_semantic_snapshot",
                expected.semantic_snapshot_revision,
                actual.semantic_snapshot_revision,
            ),
            ("stale_mutation_epoch", expected.mutation_epoch, actual.mutation_epoch),
        )
        for code, supplied, current in checks:
            if supplied != current:
                raise ResolverError(code, f"supplied={supplied} current={current}")

    def _resolve_unique(self, target: TargetBinding) -> _MutableNode:
        same_id = [item for item in self._nodes if item.node.semantic_id == target.semantic_id]
        if not same_id:
            raise ResolverError("target_not_found", "semantic_id is absent from current snapshot")
        same_frame = [item for item in same_id if item.node.frame_id == target.frame_id]
        if not same_frame:
            raise ResolverError("frame_mismatch", "semantic_id exists only in another frame")
        if len(same_frame) != 1:
            raise ResolverError("ambiguous_target", "semantic_id resolves to multiple nodes in frame")
        item = same_frame[0]
        node = item.node
        if node.role != target.role:
            raise ResolverError("role_drift", f"supplied={target.role!r} current={node.role!r}")
        if node.accessible_name != target.accessible_name:
            raise ResolverError(
                "accessible_name_drift",
                f"supplied={target.accessible_name!r} current={node.accessible_name!r}",
            )
        if node.structural_fingerprint != target.structural_fingerprint:
            raise ResolverError("structural_drift", "structural fingerprint changed")
        if not node.enabled or not node.visible:
            raise ResolverError("target_not_found", "resolved node is not actionable")
        return item

    def _validate_action(self, node: SemanticNode, action: SemanticAction) -> None:
        action.validate()
        allowed = self._policy.get(node.role, frozenset())
        if action.kind not in allowed:
            raise ResolverError(
                "unsupported_action",
                f"action {action.kind!r} is not allowed for role {node.role!r}",
            )
        if action.kind in {"set_value", "insert_text", "select_option"} and not isinstance(
            action.value, str
        ):
            raise ResolverError("invalid_request", f"{action.kind} requires a string value")
        if action.kind == "set_checked" and not isinstance(action.value, bool):
            raise ResolverError("invalid_request", "set_checked requires a boolean value")

    def resolve_and_act(
        self,
        target: TargetBinding,
        action: SemanticAction,
        *,
        deadline_ns: int | None = None,
        cancelled: bool = False,
        before_commit: Callable[["AtomicSemanticResolver"], None] | None = None,
    ) -> ActionReceipt:
        """Resolve, retain, revalidate and apply at most one action without yielding."""

        target.validate()
        with self._lock:
            self._check_deadline_and_cancellation(deadline_ns, cancelled)
            if target.session_id != self._session_id:
                raise ResolverError("session_mismatch", "target belongs to another PageOwner")
            self._check_revisions(target.revisions)
            retained = self._resolve_unique(target)
            self._validate_action(retained.node, action)

            retained_identity = retained.node
            retained_count = retained.action_count
            retained_revisions = self._revisions

            # The hook models an engine callback or malicious test mutation at
            # the final boundary. A production adapter must not yield here; the
            # immediate revalidation below is still mandatory defense-in-depth.
            if before_commit is not None:
                before_commit(self)

            self._check_deadline_and_cancellation(deadline_ns, cancelled)
            if self._session_id != target.session_id or self._revisions != retained_revisions:
                raise ResolverError("mutation_race", "PageOwner revisions changed before action")
            current = self._resolve_unique(target)
            if current is not retained or current.node != retained_identity:
                raise ResolverError("mutation_race", "retained node identity changed before action")
            if current.action_count != retained_count:
                raise ResolverError("mutation_race", "node was already acted on before commit")

            before = self._revisions.mutation_epoch
            self._apply_one(current, action)
            if current.action_count != retained_count + 1:
                raise ResolverError("mutation_race", "action cardinality was not exactly one")
            self._revisions = dataclasses.replace(self._revisions, mutation_epoch=before + 1)
            return ActionReceipt(
                session_id=self._session_id,
                frame_id=current.node.frame_id,
                semantic_id=current.node.semantic_id,
                action=action.kind,
                mutation_epoch_before=before,
                mutation_epoch_after=before + 1,
                action_count=1,
            )

    def _apply_one(self, item: _MutableNode, action: SemanticAction) -> None:
        node = item.node
        if action.kind == "focus":
            self._focused_semantic_id = node.semantic_id
        elif action.kind == "click":
            if node.role in {"checkbox", "radio"}:
                node = dataclasses.replace(node, checked=not bool(node.checked))
        elif action.kind == "set_checked":
            node = dataclasses.replace(node, checked=bool(action.value))
        elif action.kind == "set_value":
            node = dataclasses.replace(node, value=str(action.value))
        elif action.kind == "insert_text":
            node = dataclasses.replace(node, value=node.value + str(action.value))
        elif action.kind == "select_option":
            node = dataclasses.replace(node, value=str(action.value))
        else:  # pragma: no cover - policy validation makes this unreachable.
            raise ResolverError("unsupported_action", action.kind)
        item.node = node
        item.action_count += 1

    # Test-only mutation helpers intentionally require the same engine lock.
    def mutate_revisions_for_test(self, revisions: Revisions) -> None:
        with self._lock:
            revisions.validate()
            self._revisions = revisions

    def mutate_node_for_test(self, semantic_id: str, replacement: SemanticNode) -> None:
        replacement.validate()
        with self._lock:
            for item in self._nodes:
                if item.node.semantic_id == semantic_id:
                    item.node = replacement
                    return
            raise ResolverError("target_not_found", semantic_id)


def role_action_policy(contract: Mapping[str, object]) -> dict[str, set[str]]:
    raw = contract.get("role_action_policy")
    if not isinstance(raw, dict) or not raw:
        raise ResolverError("invalid_contract", "role_action_policy must be a non-empty object")
    policy: dict[str, set[str]] = {}
    for role, actions in raw.items():
        if not isinstance(role, str) or not isinstance(actions, list) or not actions:
            raise ResolverError("invalid_contract", "invalid role/action entry")
        if any(not isinstance(action, str) or not action for action in actions):
            raise ResolverError("invalid_contract", f"invalid action for role {role}")
        policy[role] = set(actions)
    return policy


def validate_contract(contract: Mapping[str, object]) -> dict[str, bool]:
    atomicity = contract.get("atomicity")
    resolution = contract.get("resolution")
    request_binding = contract.get("request_binding")
    errors = contract.get("fail_closed_errors")
    assertions = {
        "schema": contract.get("schema") == SCHEMA,
        "source_only": contract.get("status") == "SOURCE_CONTRACT_NO_SERVO_PROMOTION",
        "engine_owned": isinstance(atomicity, dict) and atomicity.get("engine_owned") is True,
        "single_operation": isinstance(atomicity, dict)
        and atomicity.get("resolve_retain_revalidate_act_without_yield") is True,
        "generic_forwarding_forbidden": isinstance(atomicity, dict)
        and atomicity.get("generic_act_forwarding_forbidden") is True,
        "unique_match": isinstance(resolution, dict)
        and resolution.get("unique_match_required") is True,
        "retargeting_forbidden": isinstance(resolution, dict)
        and resolution.get("retargeting_forbidden") is True,
        "caller_fields_are_claims": isinstance(request_binding, dict)
        and bool(request_binding.get("caller_fields_are_claims_not_resolution_results")),
        "typed_errors": isinstance(errors, list)
        and {"ambiguous_target", "structural_drift", "mutation_race"}.issubset(errors),
        "role_action_policy": bool(role_action_policy(contract)),
    }
    failed = sorted(name for name, passed in assertions.items() if not passed)
    if failed:
        raise ResolverError("invalid_contract", ", ".join(failed))
    return assertions


def fixture_snapshot(*, duplicate: bool = False) -> SemanticSnapshot:
    node = SemanticNode(
        frame_id="frame-main",
        semantic_id="submit-primary",
        role="button",
        accessible_name="Submit",
        structural_fingerprint="sha256:button-v1",
    )
    nodes = (node, node) if duplicate else (node,)
    return SemanticSnapshot(
        session_id="session-1",
        revisions=Revisions(1, 2, 3, 4),
        nodes=nodes,
    )


def fixture_target(**overrides: object) -> TargetBinding:
    values: dict[str, object] = {
        "session_id": "session-1",
        "revisions": Revisions(1, 2, 3, 4),
        "frame_id": "frame-main",
        "semantic_id": "submit-primary",
        "role": "button",
        "accessible_name": "Submit",
        "structural_fingerprint": "sha256:button-v1",
    }
    values.update(overrides)
    return TargetBinding(**values)  # type: ignore[arg-type]


def _expect_error(code: str, operation: Callable[[], object]) -> None:
    try:
        operation()
    except ResolverError as error:
        if error.code != code:
            raise AssertionError(f"expected {code}, received {error.code}") from error
    else:
        raise AssertionError(f"expected {code}")


def run_self_check(contract_path: Path) -> dict[str, object]:
    contract_bytes = contract_path.read_bytes()
    contract = json.loads(contract_bytes)
    assertions = validate_contract(contract)
    policy = role_action_policy(contract)
    passed: list[str] = []

    resolver = AtomicSemanticResolver(fixture_snapshot(), policy)
    receipt = resolver.resolve_and_act(fixture_target(), SemanticAction("click"))
    assert receipt.action_count == 1 and receipt.mutation_epoch_after == 5
    passed.append("exact_unique_action_once")

    cases: list[tuple[str, str, Callable[[], object]]] = [
        (
            "session_mismatch",
            "session_mismatch",
            lambda: AtomicSemanticResolver(fixture_snapshot(), policy).resolve_and_act(
                fixture_target(session_id="session-2"), SemanticAction("click")
            ),
        ),
        (
            "stale_session_generation",
            "stale_session_generation",
            lambda: AtomicSemanticResolver(fixture_snapshot(), policy).resolve_and_act(
                fixture_target(revisions=Revisions(0, 2, 3, 4)), SemanticAction("click")
            ),
        ),
        (
            "stale_document_generation",
            "stale_document_generation",
            lambda: AtomicSemanticResolver(fixture_snapshot(), policy).resolve_and_act(
                fixture_target(revisions=Revisions(1, 1, 3, 4)), SemanticAction("click")
            ),
        ),
        (
            "stale_semantic_snapshot",
            "stale_semantic_snapshot",
            lambda: AtomicSemanticResolver(fixture_snapshot(), policy).resolve_and_act(
                fixture_target(revisions=Revisions(1, 2, 2, 4)), SemanticAction("click")
            ),
        ),
        (
            "stale_mutation_epoch",
            "stale_mutation_epoch",
            lambda: AtomicSemanticResolver(fixture_snapshot(), policy).resolve_and_act(
                fixture_target(revisions=Revisions(1, 2, 3, 3)), SemanticAction("click")
            ),
        ),
        (
            "target_not_found",
            "target_not_found",
            lambda: AtomicSemanticResolver(fixture_snapshot(), policy).resolve_and_act(
                fixture_target(semantic_id="missing"), SemanticAction("click")
            ),
        ),
        (
            "ambiguous_target",
            "ambiguous_target",
            lambda: AtomicSemanticResolver(fixture_snapshot(duplicate=True), policy).resolve_and_act(
                fixture_target(), SemanticAction("click")
            ),
        ),
        (
            "frame_mismatch",
            "frame_mismatch",
            lambda: AtomicSemanticResolver(fixture_snapshot(), policy).resolve_and_act(
                fixture_target(frame_id="frame-child"), SemanticAction("click")
            ),
        ),
        (
            "role_drift",
            "role_drift",
            lambda: AtomicSemanticResolver(fixture_snapshot(), policy).resolve_and_act(
                fixture_target(role="link"), SemanticAction("click")
            ),
        ),
        (
            "accessible_name_drift",
            "accessible_name_drift",
            lambda: AtomicSemanticResolver(fixture_snapshot(), policy).resolve_and_act(
                fixture_target(accessible_name="Delete"), SemanticAction("click")
            ),
        ),
        (
            "structural_drift",
            "structural_drift",
            lambda: AtomicSemanticResolver(fixture_snapshot(), policy).resolve_and_act(
                fixture_target(structural_fingerprint="sha256:button-v2"),
                SemanticAction("click"),
            ),
        ),
        (
            "unsupported_action",
            "unsupported_action",
            lambda: AtomicSemanticResolver(fixture_snapshot(), policy).resolve_and_act(
                fixture_target(), SemanticAction("set_value", "unsafe")
            ),
        ),
        (
            "cancelled",
            "cancelled",
            lambda: AtomicSemanticResolver(fixture_snapshot(), policy).resolve_and_act(
                fixture_target(), SemanticAction("click"), cancelled=True
            ),
        ),
        (
            "deadline_exceeded",
            "deadline_exceeded",
            lambda: AtomicSemanticResolver(fixture_snapshot(), policy).resolve_and_act(
                fixture_target(), SemanticAction("click"), deadline_ns=0
            ),
        ),
    ]
    for name, code, operation in cases:
        _expect_error(code, operation)
        passed.append(name)

    race = AtomicSemanticResolver(fixture_snapshot(), policy)
    _expect_error(
        "mutation_race",
        lambda: race.resolve_and_act(
            fixture_target(),
            SemanticAction("click"),
            before_commit=lambda current: current.mutate_revisions_for_test(
                Revisions(1, 2, 3, 5)
            ),
        ),
    )
    passed.append("mutation_race")

    return {
        "schema": RESULT_SCHEMA,
        "status": "PASS_SOURCE_REFERENCE_ONLY",
        "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(),
        "contract_assertions": assertions,
        "passed_cases": sorted(passed),
        "passed_case_count": len(passed),
        "atomic_action_count": 1,
        "servo_adapter_exercised": False,
        "browser_actor_product_dispatch_exercised": False,
        "production_agent_port_enabled": False,
        "external_effects_performed": False,
        "promotion_authoritative": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=Path("contracts/semantic-resolver.v1.json"))
    parser.add_argument("--write-result", type=Path)
    args = parser.parse_args()
    result = run_self_check(args.contract)
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.write_result is not None:
        args.write_result.parent.mkdir(parents=True, exist_ok=True)
        args.write_result.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
