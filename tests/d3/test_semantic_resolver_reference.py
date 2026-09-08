#!/usr/bin/env python3

from __future__ import annotations

import importlib.util
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "semantic_resolver_reference.py"
SPEC = importlib.util.spec_from_file_location("semantic_resolver_reference", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
resolver_module = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = resolver_module
SPEC.loader.exec_module(resolver_module)

AtomicSemanticResolver = resolver_module.AtomicSemanticResolver
Revisions = resolver_module.Revisions
ResolverError = resolver_module.ResolverError
SemanticAction = resolver_module.SemanticAction
SemanticNode = resolver_module.SemanticNode
SemanticSnapshot = resolver_module.SemanticSnapshot
fixture_snapshot = resolver_module.fixture_snapshot
fixture_target = resolver_module.fixture_target
role_action_policy = resolver_module.role_action_policy
run_self_check = resolver_module.run_self_check
validate_contract = resolver_module.validate_contract

CONTRACT_PATH = ROOT / "contracts" / "semantic-resolver.v1.json"
CONTRACT = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
POLICY = role_action_policy(CONTRACT)


class SemanticResolverReferenceTests(unittest.TestCase):
    def assert_error(self, code: str, operation) -> ResolverError:
        with self.assertRaises(ResolverError) as raised:
            operation()
        self.assertEqual(raised.exception.code, code)
        return raised.exception

    def test_contract_is_fail_closed_and_source_only(self) -> None:
        assertions = validate_contract(CONTRACT)
        self.assertTrue(all(assertions.values()))
        self.assertIn("mutation_race", CONTRACT["fail_closed_errors"])
        self.assertIn("ambiguous_target", CONTRACT["fail_closed_errors"])
        self.assertFalse(
            any("production" in claim.lower() and "no production" not in claim.lower()
                for claim in CONTRACT["claim_ceiling"])
        )

    def test_unique_current_node_is_acted_on_exactly_once(self) -> None:
        resolver = AtomicSemanticResolver(fixture_snapshot(), POLICY)
        receipt = resolver.resolve_and_act(fixture_target(), SemanticAction("click"))
        self.assertEqual(receipt.action_count, 1)
        self.assertEqual(receipt.mutation_epoch_before, 4)
        self.assertEqual(receipt.mutation_epoch_after, 5)
        self.assertEqual(resolver.snapshot().revisions.mutation_epoch, 5)

    def test_ambiguous_semantic_identity_is_never_retargeted(self) -> None:
        resolver = AtomicSemanticResolver(fixture_snapshot(duplicate=True), POLICY)
        self.assert_error(
            "ambiguous_target",
            lambda: resolver.resolve_and_act(fixture_target(), SemanticAction("click")),
        )
        self.assertEqual(resolver.snapshot().revisions.mutation_epoch, 4)

    def test_cross_frame_fallback_is_forbidden(self) -> None:
        resolver = AtomicSemanticResolver(fixture_snapshot(), POLICY)
        self.assert_error(
            "frame_mismatch",
            lambda: resolver.resolve_and_act(
                fixture_target(frame_id="frame-child"), SemanticAction("click")
            ),
        )

    def test_role_name_and_structure_are_revalidated(self) -> None:
        resolver = AtomicSemanticResolver(fixture_snapshot(), POLICY)
        self.assert_error(
            "role_drift",
            lambda: resolver.resolve_and_act(
                fixture_target(role="link"), SemanticAction("click")
            ),
        )
        self.assert_error(
            "accessible_name_drift",
            lambda: resolver.resolve_and_act(
                fixture_target(accessible_name="Authorize transfer"), SemanticAction("click")
            ),
        )
        self.assert_error(
            "structural_drift",
            lambda: resolver.resolve_and_act(
                fixture_target(structural_fingerprint="sha256:attacker-node"),
                SemanticAction("click"),
            ),
        )

    def test_revision_layers_fail_with_distinct_codes(self) -> None:
        cases = (
            ("stale_session_generation", Revisions(0, 2, 3, 4)),
            ("stale_document_generation", Revisions(1, 1, 3, 4)),
            ("stale_semantic_snapshot", Revisions(1, 2, 2, 4)),
            ("stale_mutation_epoch", Revisions(1, 2, 3, 3)),
        )
        for code, revisions in cases:
            with self.subTest(code=code):
                resolver = AtomicSemanticResolver(fixture_snapshot(), POLICY)
                self.assert_error(
                    code,
                    lambda: resolver.resolve_and_act(
                        fixture_target(revisions=revisions), SemanticAction("click")
                    ),
                )

    def test_mutation_between_resolution_and_commit_fails_closed(self) -> None:
        resolver = AtomicSemanticResolver(fixture_snapshot(), POLICY)
        self.assert_error(
            "mutation_race",
            lambda: resolver.resolve_and_act(
                fixture_target(),
                SemanticAction("click"),
                before_commit=lambda engine: engine.mutate_revisions_for_test(
                    Revisions(1, 2, 3, 5)
                ),
            ),
        )
        self.assertEqual(resolver.snapshot().revisions.mutation_epoch, 5)

    def test_node_replacement_between_resolution_and_commit_fails_closed(self) -> None:
        resolver = AtomicSemanticResolver(fixture_snapshot(), POLICY)
        replacement = SemanticNode(
            frame_id="frame-main",
            semantic_id="submit-primary",
            role="button",
            accessible_name="Submit",
            structural_fingerprint="sha256:button-v2",
        )
        # The immediate re-resolution sees structural drift; it must never act
        # on the replacement merely because semantic_id still matches.
        self.assert_error(
            "structural_drift",
            lambda: resolver.resolve_and_act(
                fixture_target(),
                SemanticAction("click"),
                before_commit=lambda engine: engine.mutate_node_for_test(
                    "submit-primary", replacement
                ),
            ),
        )
        self.assertEqual(resolver.snapshot().revisions.mutation_epoch, 4)

    def test_role_action_policy_blocks_generic_act_forwarding(self) -> None:
        resolver = AtomicSemanticResolver(fixture_snapshot(), POLICY)
        self.assert_error(
            "unsupported_action",
            lambda: resolver.resolve_and_act(
                fixture_target(), SemanticAction("set_value", "not-a-button-operation")
            ),
        )

    def test_cancellation_and_deadline_precede_action(self) -> None:
        resolver = AtomicSemanticResolver(fixture_snapshot(), POLICY)
        self.assert_error(
            "cancelled",
            lambda: resolver.resolve_and_act(
                fixture_target(), SemanticAction("click"), cancelled=True
            ),
        )
        self.assert_error(
            "deadline_exceeded",
            lambda: resolver.resolve_and_act(
                fixture_target(), SemanticAction("click"), deadline_ns=0
            ),
        )
        self.assertEqual(resolver.snapshot().revisions.mutation_epoch, 4)

    def test_textbox_mutations_obey_typed_action_policy(self) -> None:
        textbox = SemanticNode(
            frame_id="frame-main",
            semantic_id="query",
            role="textbox",
            accessible_name="Search",
            structural_fingerprint="sha256:textbox-v1",
        )
        snapshot = SemanticSnapshot(
            session_id="session-1",
            revisions=Revisions(1, 2, 3, 4),
            nodes=(textbox,),
        )
        target = fixture_target(
            semantic_id="query",
            role="textbox",
            accessible_name="Search",
            structural_fingerprint="sha256:textbox-v1",
        )
        resolver = AtomicSemanticResolver(snapshot, POLICY)
        resolver.resolve_and_act(target, SemanticAction("set_value", "hepta"))
        self.assertEqual(resolver.snapshot().nodes[0].value, "hepta")

    def test_self_check_is_deterministic_and_non_promoting(self) -> None:
        first = run_self_check(CONTRACT_PATH)
        second = run_self_check(CONTRACT_PATH)
        self.assertEqual(first, second)
        self.assertEqual(first["status"], "PASS_SOURCE_REFERENCE_ONLY")
        self.assertGreaterEqual(first["passed_case_count"], 16)
        self.assertFalse(first["servo_adapter_exercised"])
        self.assertFalse(first["browser_actor_product_dispatch_exercised"])
        self.assertFalse(first["production_agent_port_enabled"])
        self.assertFalse(first["promotion_authoritative"])


if __name__ == "__main__":
    unittest.main()
