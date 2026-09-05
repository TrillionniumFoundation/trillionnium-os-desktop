"""Source/contract wiring checks, not proof of actual Servo or image execution."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = "contracts/engine-thread-dispatch.v1.json"
SOURCE = "crates/hepta-browser-actor/src/engine_dispatch.rs"
DOCUMENT = "docs/architecture/ENGINE_THREAD_DISPATCH.md"
REQUIRED_SOURCES = [
    "crates/hepta-browser-actor/src/lib.rs",
    SOURCE,
    "crates/hepta-browser-actor/src/engine_dispatch/tests.rs",
    "crates/hepta-browser-actor/src/engine_dispatch/transport_tests.rs",
]


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate contract key: {key}")
        result[key] = value
    return result


def read_json(name):
    return json.loads((ROOT / name).read_text(), object_pairs_hook=strict_object)


class EngineThreadDispatchContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = read_json(CONTRACT)
        self.source = (ROOT / SOURCE).read_text()

    def test_claim_ceiling_does_not_promote_an_engine(self):
        self.assertEqual(self.contract["status"], "SOURCE_CANDIDATE")
        self.assertEqual(self.contract["work_package"], "D3-01")
        self.assertEqual(self.contract["evidence_ceiling"], "LOCAL_HOST_TRANSPORT_AND_FIXTURE_ENGINE_ONLY")
        for key in (
            "wire_protocol_added", "process_ipc", "servo_adapter_implemented",
            "production_activation_enabled",
            "external_effect_authority", "promotion_authoritative",
            "engine_live_state_verified_by_bridge", "native_event_loop_latency_guaranteed",
        ):
            with self.subTest(key=key):
                self.assertIs(self.contract[key], False)
        self.assertIs(self.contract["development_daemon_switched"], True)
        self.assertEqual(self.contract["development_service_binding"], "contracts/d3-session-engine-runner.v1.json")
        actor = read_json("contracts/browser-actor.v1.json")
        self.assertEqual(actor["browser_actor"]["engine_thread_dispatch"], CONTRACT)
        self.assertIs(actor["activation"]["product_agent_port_enabled"], False)

    def test_queue_and_control_contract_is_fixed_and_typed(self):
        for key, value in (("pending_limit", 1), ("per_request_reply_limit", 1), ("cancel_poll_ms", 5)):
            self.assertIs(type(self.contract[key]), int)
            self.assertEqual(self.contract[key], value)
        self.assertEqual(self.contract["deadline"], "original_monotonic_instant_no_reset")
        self.assertEqual(self.contract["queue_full"], "close_pair_no_wait_no_retry")
        self.assertEqual(self.contract["abandoned_pair"], "permanently_closed_no_late_result_reuse")
        for token in ("try_send(pending)", "receiver.recv_timeout", "control.remaining()?", "impl Drop for PendingWait"):
            self.assertIn(token, self.source)

    def test_owner_thread_affinity_and_action_hook_have_no_fallback(self):
        self.assertIs(self.contract["owner_send"], False)
        self.assertIs(self.contract["owner_sync"], False)
        self.assertIs(self.contract["client_cloneable"], False)
        self.assertIs(self.contract["constructor_spawns_threads"], False)
        self.assertIn("PhantomData<Rc<()>>", self.source)
        self.assertIn("thread::current().id()", self.source)
        self.assertEqual(self.contract["generic_act"], "unsupported")
        self.assertEqual(self.contract["atomic_action_hook"], "PageRuntime::dispatch_page_act")
        self.assertIn("return runtime.dispatch_page_act(", self.source)
        self.assertNotIn("unsafe impl", self.source)

    def test_sources_are_concrete_registered_and_not_symlinked(self):
        self.assertEqual(self.contract["required_sources"], REQUIRED_SOURCES)
        for name in REQUIRED_SOURCES + [CONTRACT, DOCUMENT]:
            path = ROOT / name
            self.assertTrue(path.is_file(), name)
            self.assertFalse(path.is_symlink(), name)
        self.assertIn("pub mod engine_dispatch;", (ROOT / REQUIRED_SOURCES[0]).read_text())
        module = next(m for m in read_json("manifests/modules.v1.json")["modules"] if m["id"] == "hepta-browser-actor")
        self.assertIn(CONTRACT, module["contracts"])
        self.assertIn(DOCUMENT, module["architecture"])
        for name in REQUIRED_SOURCES[2:] + ["tests/test_engine_thread_dispatch_contract.py"]:
            self.assertIn(name, module["tests"])
        self.assertEqual(module["status"], "d3_source_candidate")

    def test_ci_runs_rustdoc_in_addition_to_workspace_targets(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn("cargo test --locked -p hepta-browser-actor --doc", workflow)
        self.assertIn("cargo test --workspace --all-targets --locked", workflow)
        self.assertIn("cargo test --workspace --all-targets --all-features --locked", workflow)
        self.assertIn("make test-python", workflow)
        self.assertGreaterEqual(self.source.count("```compile_fail"), 2)
        self.assertIn("needs_send::<EngineThreadOwner", self.source)
        self.assertIn("needs_sync::<EngineThreadOwner", self.source)

    def test_host_test_chain_is_explicit_and_not_servo_evidence(self):
        source = (ROOT / REQUIRED_SOURCES[3]).read_text()
        for token in ("UnixStream::pair()", "PeerIdentity::from_stream", "ClientConnection::connect",
                      "serve_one_with_observer", "engine_thread_pair", "inspect_receipt_journal",
                      "ReceiptLifecycleState::Dispatched", "ReceiptLifecycleState::Indeterminate",
                      "SessionPhase::Recovering", "response_sha256"):
            self.assertIn(token, source)
        self.assertIn("NOT Servo, systemd activation or exact-image qualification", source)

    def test_d3_evidence_invalidation_retains_new_inputs(self):
        gate = next(g for g in read_json("manifests/gates.v1.json")["gates"] if g["id"] == "D3-01")
        self.assertEqual(gate["status"], "BLOCKED_UPSTREAM")
        for name in [CONTRACT, DOCUMENT, "tests/test_engine_thread_dispatch_contract.py", "crates/**", ".github/workflows/**"]:
            self.assertIn(name, gate["invalidation_paths"])
        self.assertEqual(gate["evidence_tier"], "integrated_qemu_image")

    def test_document_explains_limits_and_failure_cleanup(self):
        document = (ROOT / DOCUMENT).read_text()
        for heading in ("## Purpose and non-claims", "## Types, ownership, and call direction",
                        "## Admission and resource limits", "## Atomic action routing",
                        "## Deadline, cancellation, and failure state machine",
                        "## Executable host integration and evidence", "## Servo integration and remaining work"):
            self.assertIn(heading, document)
        self.assertIn("not a new wire protocol or a process IPC", document)
        self.assertIn("not a real-time scheduling guarantee", document)
        self.assertIn("permanently closed", document)
        self.assertIn("independent review", document)


if __name__ == "__main__":
    unittest.main()
