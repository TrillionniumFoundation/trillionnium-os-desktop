"""Mutation checks for actual threaded daemon wiring; not image or Servo proof."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("d3_thread_runner_test", ROOT / "tools/validate_d3_development_profile.py")
assert SPEC and SPEC.loader
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class D3SessionEngineRunnerTests(unittest.TestCase):
    def setUp(self):
        self.inputs = {k: (ROOT / p).read_text() for k, p in AUDIT.THREADED_INPUTS.items()}
        self.contract = (ROOT / AUDIT.RUNNER_CONTRACT).read_text()

    def rejects(self, key, old, new):
        inputs = self.inputs.copy()
        self.assertIn(old, inputs[key])
        inputs[key] = inputs[key].replace(old, new, 1)
        self.assertTrue(AUDIT.audit_threaded_sources(inputs, self.contract), (key, old))

    def test_exact_sources_and_contract_pass(self):
        self.assertEqual(AUDIT.audit_threaded_sources(self.inputs, self.contract), [])

    def test_missing_input_is_not_loaded_from_hidden_files(self):
        for key in self.inputs:
            inputs = self.inputs.copy()
            del inputs[key]
            self.assertTrue(AUDIT.audit_threaded_sources(inputs, self.contract), key)

    def test_direct_fixture_actor_cannot_replace_thread_endpoint(self):
        self.rejects("service", "type D3Actor = BrowserActor<EngineThreadRuntime>", "type D3Actor = BrowserActor<AtomicFixtureRuntime>")

    def test_startup_authorization_cannot_be_replaced_by_comments(self):
        for old in ("activation::require_profile(arguments)?", "activation::require_marker()?", "storage::reconcile_unresolved(&mut persistent_journal)?"):
            with self.subTest(old=old):
                self.rejects("service", old, f"/* {old} */ ignored()")

    def test_snapshot_check_must_remain_in_connection_function(self):
        self.rejects("service", "verify_continuity(current, peer, attested.snapshot())?", "Ok::<(), AnyError>(())?")
        self.rejects("service", "current.peer_snapshot != *snapshot", "false")
        self.rejects("service", "attested.snapshot().clone()", "replacement_snapshot()")

    def test_connection_still_refreshes_request_scoped_attestation(self):
        self.rejects("service", ".handle_attested(context, request, self.attestor, self.attested)", ".handle(context, request)")
        self.rejects("service", "attested.ensure_alive()?", "ignored()")

    def test_retirement_and_join_cannot_be_removed_or_commented(self):
        self.rejects("callback", "stop.retire();", "/* stop.retire(); */")
        self.rejects("callback", ".join()", "/* .join() */ .is_finished()")
        self.rejects("service", "stop.ensure_active()?", "ignored()")

    def test_accept_checks_and_blocking_stream_are_required(self):
        self.rejects("engine", "stream.set_nonblocking(false)?", "stream.set_nonblocking(true)?")
        self.rejects("engine", "stop.ensure_active()?;\n        match listener.accept()", "match listener.accept()")

    def test_contract_rejects_duplicate_keys_types_and_authority_widening(self):
        o = json.loads(self.contract)
        for key, value in (("worker_count", True), ("poll_ms", 5.0), ("exact_image_qualified", True),
                           ("servo_adapter", True), ("first_attested_snapshot_retained", False),
                           ("new_runtime_after_retirement", True)):
            changed = dict(o, **{key: value})
            self.assertTrue(AUDIT.audit_threaded_sources(self.inputs, json.dumps(changed)), key)
        for text in ('{"poll_ms":5,"poll_ms":5}', '{"poll_ms":NaN}', '[]'):
            self.assertTrue(AUDIT.audit_threaded_sources(self.inputs, text))

    def test_required_regressions_are_executable_and_not_ignored(self):
        self.rejects("service_tests", "#[test]\nfn persistent_session_rejects_recycled_pid_with_new_process_birth", "#[test]\n#[ignore]\nfn persistent_session_rejects_recycled_pid_with_new_process_birth")

    def test_document_registry_and_gate_inputs_are_linked(self):
        contract_path = AUDIT.RUNNER_CONTRACT
        doc = "docs/architecture/D3_SESSION_ENGINE_RUNNER.md"
        text = (ROOT / doc).read_text()
        for heading in ("## Scope and non-claims", "## Startup and thread ownership",
                        "## Connection and process-birth continuity", "## Shutdown and failure semantics",
                        "## Configuration and operations", "## Tests and acceptance"):
            self.assertIn(heading, text)
        module = next(m for m in json.loads((ROOT / "manifests/modules.v1.json").read_text())["modules"] if m["id"] == "hepta-d3-development")
        self.assertIn(doc, module["architecture"])
        self.assertIn(contract_path, module["contracts"])
        self.assertIn("tests/test_d3_session_engine_runner.py", module["tests"])
        self.assertEqual(module["status"], "d3_development_candidate")
        gates = json.loads((ROOT / "manifests/gates.v1.json").read_text())["gates"]
        for gate in gates:
            if gate["id"] in ("D0C-06", "D3-01"):
                self.assertIn(doc, gate["invalidation_paths"])
                self.assertIn(contract_path, gate["invalidation_paths"])
                self.assertIn("tests/test_d3_session_engine_runner.py", gate["invalidation_paths"])
        d3 = next(g for g in gates if g["id"] == "D3-01")
        self.assertEqual(d3["status"], "BLOCKED_UPSTREAM")

    def test_workflow_triggers_include_runner_and_audit_inputs(self):
        from tests.test_agent_port_custody_workflow import trigger_paths
        required = ["contracts/d3-session-engine-runner.v1.json",
                    "docs/architecture/D3_SESSION_ENGINE_RUNNER.md",
                    "tests/test_d3_session_engine_runner.py",
                    "tools/validate_d3_development_profile.py",
                    "tools/_validate_d3_development_profile_impl.py",
                    "tools/verify_receipt_journal.py",
                    "crates/hepta-d3-development/**", "crates/hepta-browser-actor/**"]
        for workflow in (".github/workflows/receipt-journal.yml", ".github/workflows/d3-integrated-runtime-evidence.yml"):
            text = (ROOT / workflow).read_text()
            for event in ("pull_request", "push"):
                paths = trigger_paths(text, event)
                for path in required:
                    self.assertIn(path, paths, (workflow, event, path))
        text = (ROOT / ".github/workflows/d3-integrated-runtime-evidence.yml").read_text()
        self.assertIn("python3 -m unittest tests.test_d3_session_engine_runner -v", text)

    def test_self_check_remains_source_wiring_not_runtime_evidence(self):
        text = self.inputs["main"]
        for key in ("engine_thread_dispatch_exercised", "servo_adapter_exercised",
                    "product_agent_port_enabled", "external_effect_authority"):
            self.assertIn('\\"' + key + '\\":false', text)
        self.assertIn('\\"engine_thread_dispatch_wired\\":true', text)
        self.assertNotIn("std::env::set_var", text)


if __name__ == "__main__":
    unittest.main()
