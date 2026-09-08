from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BrowserActorSliceTests(unittest.TestCase):
    def test_workspace_registers_actor_once(self) -> None:
        cargo = (ROOT / "Cargo.toml").read_text()
        self.assertEqual(cargo.count('"crates/hepta-browser-actor"'), 2)

    def test_actor_contract_is_fail_closed(self) -> None:
        contract = json.loads((ROOT / "contracts/browser-actor.v1.json").read_text())
        actor = contract["browser_actor"]
        activation = contract["activation"]
        self.assertTrue(contract["principal_binding"]["exact_match_required"])
        self.assertEqual(contract["principal_binding"]["peer_drift"], "fail_closed_before_dispatch")
        self.assertFalse(actor["external_https_enabled"])
        self.assertFalse(actor["external_effect_authority"])
        self.assertFalse(activation["product_agent_port_enabled"])
        self.assertFalse(activation["production_release_authorized"])

    def test_engine_bridge_is_bounded_and_not_thread_spawned(self) -> None:
        contract = json.loads((ROOT / "contracts/engine-thread-dispatch.v1.json").read_text())
        self.assertEqual(contract["pending_limit"], 1)
        self.assertEqual(contract["per_request_reply_limit"], 1)
        self.assertFalse(contract["constructor_spawns_threads"])
        self.assertFalse(contract["client_cloneable"])
        self.assertFalse(contract["external_effect_authority"])
        self.assertFalse(contract["production_activation_enabled"])

    def test_event_loop_completion_cannot_be_success_on_queue(self) -> None:
        contract = json.loads((ROOT / "contracts/event-loop-completion.v1.json").read_text())
        self.assertEqual(contract["request_queue_limit"], 1)
        self.assertEqual(contract["completion_queue_limit"], 1)
        self.assertFalse(contract["queued_is_durable_success"])
        self.assertEqual(contract["callback_drop"], "browser_crashed_not_empty_success")
        self.assertFalse(contract["servo_adapter"])

    def test_incarnation_requires_fresh_entropy_and_no_resurrection(self) -> None:
        contract = json.loads((ROOT / "contracts/session-incarnation.v1.json").read_text())
        self.assertEqual(contract["entropy_bytes"], 32)
        self.assertEqual(contract["zero_entropy"], "reject")
        self.assertEqual(contract["entropy_failure"], "latched_no_identity_or_runtime_dispatch")
        self.assertFalse(contract["automatic_session_resurrection"])
        self.assertFalse(contract["reference_is_capability"])
        self.assertFalse(contract["production_activation_enabled"])

    def test_actor_source_has_no_listener_or_unsafe_fallback(self) -> None:
        source = "\n".join(
            path.read_text()
            for path in sorted((ROOT / "crates/hepta-browser-actor/src").rglob("*.rs"))
        )
        self.assertNotIn("TcpListener", source)
        self.assertNotIn("UnixListener", source)
        self.assertIn("dispatch_page_act", source)
        self.assertIn("ensure_alive", source)


if __name__ == "__main__":
    unittest.main()
