from __future__ import annotations

import copy
import sys
from dataclasses import asdict
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from d4_collaboration_reference import CollaborationModel  # noqa: E402


class CollaborationReferenceTests(unittest.TestCase):
    def model_with_targets(self, targets: list[str] | None = None) -> CollaborationModel:
        model = CollaborationModel("session-a", "owner-a")
        model.apply(
            {
                "kind": "publish_semantic_snapshot",
                "targets": targets or ["field", "button", "modal", "source", "destination"],
            },
            0,
        )
        return model

    def test_human_lease_blocks_agent(self) -> None:
        model = self.model_with_targets()
        model.apply({"kind": "acquire_human_lease", "actor": "human", "duration_ms": 100}, 1)
        receipt = model.apply({"kind": "agent_begin", "actor": "agent", "agent_epoch": 1}, 2)
        self.assertFalse(receipt["admitted"])
        self.assertEqual(receipt["reason"], "ACTIVE_HUMAN_LEASE")

    def test_human_input_preempts_agent_and_invalidates_epoch(self) -> None:
        model = self.model_with_targets()
        model.apply({"kind": "agent_begin", "actor": "agent", "agent_epoch": 0}, 1)
        model.apply({"kind": "human_input", "actor": "human"}, 2)
        self.assertEqual(model.state.active_actor, "human")
        stale = model.apply({"kind": "agent_begin", "actor": "agent", "agent_epoch": 0}, 3)
        self.assertFalse(stale["admitted"])
        self.assertEqual(stale["reason"], "STALE_AGENT_EPOCH")

    def test_expired_human_lease_does_not_block_agent(self) -> None:
        model = self.model_with_targets()
        model.apply({"kind": "acquire_human_lease", "actor": "human", "duration_ms": 10}, 1)
        receipt = model.apply({"kind": "agent_begin", "actor": "agent", "agent_epoch": 1}, 11)
        self.assertTrue(receipt["admitted"])

    def test_navigation_rejects_stale_target_and_cancels_interaction_state(self) -> None:
        model = self.model_with_targets()
        field = asdict(model.current_ref("field"))
        source = asdict(model.current_ref("source"))
        model.apply({"kind": "claim_ime", "actor": "human", "target": field}, 1)
        model.apply({"kind": "drag_start", "actor": "human", "source": source}, 2)
        model.apply({"kind": "open_modal", "actor": "human", "target": asdict(model.current_ref("modal"))}, 3)
        model.apply({"kind": "navigate", "actor": "human", "url": "hepta://fixture/next"}, 4)
        self.assertIsNone(model.state.drag)
        self.assertEqual(model.state.ime_owner, "none")
        self.assertEqual(model.state.modal_stack, [])
        stale = model.apply({"kind": "focus_target", "actor": "human", "target": field}, 5)
        self.assertFalse(stale["admitted"])
        self.assertEqual(stale["reason"], "STALE_TARGET_REFERENCE")

    def test_crash_rejects_stale_target_and_clears_lease(self) -> None:
        model = self.model_with_targets()
        field = asdict(model.current_ref("field"))
        model.apply({"kind": "acquire_human_lease", "actor": "human", "duration_ms": 1000}, 1)
        model.apply({"kind": "content_crash_recover", "actor": "none"}, 2)
        self.assertIsNone(model.state.human_lease)
        stale = model.apply({"kind": "focus_target", "actor": "human", "target": field}, 3)
        self.assertFalse(stale["admitted"])
        self.assertEqual(stale["reason"], "STALE_TARGET_REFERENCE")

    def test_ambiguous_target_is_rejected(self) -> None:
        model = self.model_with_targets(["dup", "dup"])
        receipt = model.apply(
            {"kind": "focus_target", "actor": "human", "target": asdict(model.current_ref("dup"))},
            1,
        )
        self.assertFalse(receipt["admitted"])
        self.assertEqual(receipt["reason"], "AMBIGUOUS_TARGET_REFERENCE")

    def test_modal_blocks_background_target(self) -> None:
        model = self.model_with_targets()
        model.apply(
            {"kind": "open_modal", "actor": "human", "target": asdict(model.current_ref("modal"))},
            1,
        )
        blocked = model.apply(
            {"kind": "focus_target", "actor": "human", "target": asdict(model.current_ref("button"))},
            2,
        )
        self.assertFalse(blocked["admitted"])
        self.assertEqual(blocked["reason"], "BACKGROUND_TARGET_BLOCKED_BY_MODAL")

    def test_ime_is_single_owner_and_human_preempts_agent_ime(self) -> None:
        model = self.model_with_targets()
        field = asdict(model.current_ref("field"))
        model.apply({"kind": "claim_ime", "actor": "agent", "target": field}, 1)
        blocked = model.apply({"kind": "claim_ime", "actor": "human", "target": field}, 2)
        self.assertFalse(blocked["admitted"])
        self.assertEqual(blocked["reason"], "IME_ALREADY_OWNED")
        model.apply({"kind": "human_input", "actor": "human"}, 3)
        self.assertEqual(model.state.ime_owner, "none")

    def test_clipboard_uses_compare_and_swap_version(self) -> None:
        model = self.model_with_targets()
        first = model.apply(
            {"kind": "clipboard_write", "actor": "human", "expected_version": 0, "value": "alpha"},
            1,
        )
        self.assertTrue(first["admitted"])
        stale = model.apply(
            {"kind": "clipboard_write", "actor": "agent", "expected_version": 0, "value": "beta"},
            2,
        )
        self.assertFalse(stale["admitted"])
        self.assertEqual(stale["reason"], "CLIPBOARD_VERSION_MISMATCH")
        read = model.apply(
            {"kind": "clipboard_read", "actor": "agent", "expected_version": 1},
            3,
        )
        self.assertTrue(read["admitted"])
        self.assertNotIn("value", read["details"])

    def test_drag_drop_is_actor_and_reference_bound(self) -> None:
        model = self.model_with_targets()
        model.apply(
            {"kind": "drag_start", "actor": "agent", "source": asdict(model.current_ref("source"))},
            1,
        )
        wrong_actor = model.apply(
            {"kind": "drop", "actor": "human", "destination": asdict(model.current_ref("destination"))},
            2,
        )
        self.assertFalse(wrong_actor["admitted"])
        self.assertEqual(wrong_actor["reason"], "DRAG_OWNED_BY_OTHER_ACTOR")
        accepted = model.apply(
            {"kind": "drop", "actor": "agent", "destination": asdict(model.current_ref("destination"))},
            3,
        )
        self.assertTrue(accepted["admitted"])
        self.assertIsNone(model.state.drag)

    def test_crash_cancels_drag(self) -> None:
        model = self.model_with_targets()
        model.apply(
            {"kind": "drag_start", "actor": "human", "source": asdict(model.current_ref("source"))},
            1,
        )
        model.apply({"kind": "content_crash_recover", "actor": "none"}, 2)
        self.assertIsNone(model.state.drag)

    def test_minimize_does_not_create_hidden_page(self) -> None:
        model = self.model_with_targets()
        model.apply({"kind": "minimize", "actor": "human"}, 1)
        self.assertFalse(model.state.visible)
        self.assertTrue(model.state.surface_exists)
        self.assertEqual(model.state.hidden_page_count, 0)
        model.apply({"kind": "show", "actor": "agent"}, 2)
        self.assertTrue(model.state.visible)
        self.assertEqual(model.state.hidden_page_count, 0)

    def test_external_navigation_is_rejected(self) -> None:
        model = self.model_with_targets()
        receipt = model.apply(
            {"kind": "navigate", "actor": "agent", "url": "https://example.com"},
            1,
        )
        self.assertFalse(receipt["admitted"])
        self.assertEqual(receipt["reason"], "EXTERNAL_NAVIGATION_NOT_AUTHORIZED")

    def test_trace_replay_is_byte_identical(self) -> None:
        model = self.model_with_targets()
        model.apply({"kind": "human_input", "actor": "human"}, 1)
        model.apply(
            {"kind": "clipboard_write", "actor": "human", "expected_version": 0, "value": "x"},
            2,
        )
        replayed = model.replay()
        self.assertEqual(replayed.state_value(), model.state_value())
        self.assertEqual(replayed.receipts, model.receipts)

    def test_receipt_chain_detects_tampering(self) -> None:
        model = self.model_with_targets()
        model.apply({"kind": "human_input", "actor": "human"}, 1)
        tampered = copy.deepcopy(model.receipts)
        tampered[-1]["reason"] = "FORGED"
        with self.assertRaisesRegex(ValueError, "receipt hash mismatch"):
            CollaborationModel.verify_receipt_chain(tampered)


if __name__ == "__main__":
    unittest.main()
