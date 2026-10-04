from __future__ import annotations

import json
import hashlib
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
RUNTIME = ROOT / "runtime/servo/hepta_workspace_runtime.rs"


class D2IContractTests(unittest.TestCase):
    def test_contract_has_callback_independent_causal_proof(self) -> None:
        contract = json.loads(
            (ROOT / "contracts/d2i-integrated-image.v1.json").read_text()
        )
        self.assertEqual(contract["work_package"], "D2I-01")
        self.assertTrue(contract["image"]["byte_for_byte_equality_required"])
        self.assertEqual(contract["boot"]["network"], "none")
        runtime = contract["runtime"]
        self.assertEqual(
            runtime["fault_mechanism"],
            "external SIGKILL of exact PID/start-time identity",
        )
        self.assertTrue(runtime["zero_process_intermediate_required"])
        self.assertTrue(runtime["distinct_replacement_identity_required"])
        self.assertFalse(runtime["servo_crash_callback_required"])
        self.assertTrue(runtime["popup_denial_required"])
        self.assertTrue(runtime["external_navigation_denial_required"])
        self.assertIn("image-local Servo dispatch", runtime["input_claim"])
        ceiling = contract["claim_ceiling"]
        self.assertFalse(ceiling["browser_actor"])
        self.assertFalse(ceiling["release_readiness"])
        self.assertIn("protected_main", contract["promotion_requires"])
        self.assertIn("exact_main_rerun_after_merge", contract["promotion_requires"])

    def test_guest_runtime_is_networkless_and_unprivileged(self) -> None:
        service = (
            ROOT
            / "packaging/debian/image/d2i-overlay/etc/systemd/system/trillionnium-d2i-runtime.service"
        ).read_text()
        self.assertIn("User=hepta-desktop", service)
        self.assertIn("PrivateNetwork=yes", service)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", service)
        self.assertIn("WAYLAND_DISPLAY=wayland-0", service)
        self.assertIn("HEPTA_D0A02_OUTPUT=/var/lib/trillionnium-d2i", service)

    def test_portable_proof_contract_preserves_typed_observations_and_claim_ceiling(self) -> None:
        contract = json.loads((ROOT / "contracts/d2i-integrated-image.v1.json").read_text())
        self.assertEqual(contract["portable_verification"], {
            "d1_source_count_exact_integer_required": True,
            "d1_claim_ceiling": "closed_six_false_booleans",
            "d1_staged_document_binding": "recursive_exact_types",
            "process_identity_nested_integer_types_required": True,
            "process_record_field_sets": "closed",
            "source_archive_rebuilds_declared_git_tree": True,
            "ime_composition_events_sent": 3,
            "minimum_recovered_frame_count": 2,
            "simulated_recovery_allowed": False,
            "guest_runtime_and_screenshot_digests_required": True,
            "guest_runtime_facts_must_agree": True,
            "receipt_claims_and_ceiling": "closed_exact_boolean_maps",
            "rehashed_negative_fixture_is_guest_evidence": False,
        })

    def test_permanent_gate_is_read_only_and_unfiltered(self) -> None:
        workflow = (ROOT / ".github/workflows/d2i-integrated-image.yml").read_text()
        runner = (ROOT / "tools/run_d2i_integrated_image.sh").read_text()
        self.assertIn("branches: [main]", workflow)
        self.assertNotIn("paths:", workflow)
        self.assertIn("contents: read", workflow)
        self.assertNotIn("contents: write", workflow)
        self.assertNotIn("git push", workflow)
        self.assertNotIn("git push", runner)
        self.assertIn("pr_synthetic_merge", runner)
        self.assertIn("exact_main_push", runner)

    def test_d1_subreceipt_receives_complete_identity_interface(self) -> None:
        runner = (ROOT / "tools/run_d2i_integrated_image.sh").read_text()
        required_exports = [
            "TESTED_SHA",
            "TESTED_TREE_SHA",
            "BASE_SHA",
            "CANDIDATE_HEAD_SHA",
            "EVIDENCE_ROLE",
            "PROMOTION_AUTHORITATIVE",
            "TESTED_TOPOLOGY",
            "SOURCE_REF",
            "SOURCE_REF_NAME",
        ]
        for name in required_exports:
            self.assertIn(f"printf '{name}=%s", runner)
        self.assertIn("topology=pr_merge_commit", runner)
        self.assertIn("topology=exact_push_commit", runner)
        self.assertIn("topology=manual_checkout", runner)
        self.assertIn("run_d1_final_qualification.sh enforce-evidence", runner)
        self.assertLess(
            runner.index("printf 'SOURCE_REF=%s"),
            runner.index("step_run_d1()"),
        )

    def test_combined_gate_reclaims_servo_tree_and_preserves_failures(self) -> None:
        workflow = (ROOT / ".github/workflows/d2i-integrated-image.yml").read_text()
        reclaim = (ROOT / "tools/reclaim_d2i_servo_workspace.sh").read_text()
        diagnostics = (ROOT / "tools/collect_d2i_failure_diagnostics.sh").read_text()

        reclaim_step = "bash tools/reclaim_d2i_servo_workspace.sh"
        d1_step = "bash tools/run_d2i_integrated_image.sh run-d1"
        diagnostics_step = "bash tools/collect_d2i_failure_diagnostics.sh"
        self.assertIn(reclaim_step, workflow)
        self.assertIn(diagnostics_step, workflow)
        self.assertLess(workflow.index(reclaim_step), workflow.index(d1_step))
        self.assertIn("continue-on-error: true", workflow)

        self.assertIn("rm -rf --one-file-system servo-source", reclaim)
        self.assertIn("headed-runtime digest changed", reclaim)
        self.assertIn("PASS_SERVO_BUILD_TREE_RECLAIMED", reclaim)
        self.assertIn("available_bytes_before", reclaim)
        self.assertIn("available_bytes_after", reclaim)

        self.assertIn("/tmp/trillionnium-d1", diagnostics)
        self.assertIn("MAX_BYTES = 4 * 1024 * 1024", diagnostics)
        self.assertIn("tail_truncated", diagnostics)
        self.assertIn("diagnostics_only_not_qualification_evidence", diagnostics)

    def test_runtime_and_host_verifier_reject_callback_as_authority(self) -> None:
        transform = (ROOT / "tools/prepare_d2i_runtime.py").read_text()
        boot_transform = (ROOT / "tools/prepare_d2i_boot_runner.py").read_text()
        acceptance = (
            ROOT
            / "packaging/debian/image/d2i-overlay/usr/local/libexec/trillionnium-d2i-acceptance"
        ).read_text()
        self.assertIn("zero_content_processes_after_termination", transform)
        self.assertIn("replacement_process_distinct", transform)
        self.assertIn("crash_callback_required", transform)
        self.assertIn("callback_required", boot_transform)
        self.assertIn('"crash_callback_required": false', acceptance)
        self.assertNotIn("actual_crash_callbacks >= 1", acceptance)

    def test_host_gate_builds_d1_and_one_exact_integrated_image(self) -> None:
        prepare = (ROOT / "tests/qemu/prepare-d2i-image.sh").read_text()
        boot = (ROOT / "tests/qemu/run-d2i-boot-test.base.sh").read_text()
        runner = (ROOT / "tools/run_d2i_integrated_image.sh").read_text()
        self.assertIn("PASS_DETERMINISTIC_INPUT_INJECTION", prepare)
        self.assertIn("E2FSPROGS_FAKE_TIME", prepare)
        self.assertIn("-nic none", boot)
        self.assertIn("trillionnium-d2i-acceptance.target", boot)
        self.assertIn("run_d1_final_qualification.sh run-pipeline", runner)
        self.assertIn("cmp -s", runner)
        self.assertIn("verify_d2i_artifact.py", runner)


class D2IInputSourceTests(unittest.TestCase):
    """Execute the tracked sequencing/evidence code, without a Servo claim."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        cls.work = Path(cls.temporary.name)
        cls.generated = cls.work / "runtime.rs"
        cls.record = cls.work / "transformation.json"
        subprocess.run(
            ["python3", str(ROOT / "tools/prepare_d2i_runtime.py"),
             "--source", str(RUNTIME), "--output", str(cls.generated),
             "--evidence", str(cls.record)],
            check=True, capture_output=True, text=True, timeout=20,
        )
        cls.source = cls.generated.read_text()
        module = cls.source.split("// BEGIN QUALIFICATION INPUT SEQUENCE:", 1)[1]
        module = module.split("\n", 1)[1].split("// END QUALIFICATION INPUT SEQUENCE", 1)[0]
        # Compile the actual tracked Rust module, including its six behavioral
        # tests. Missing Rust fails this corpus; there is no skipped substitute.
        test_source = cls.work / "input_tests.rs"
        test_source.write_text(module)
        cls.input_tests = cls.work / "input_tests"
        compilation = subprocess.run(
            ["rustc", "--edition=2024", "--test", str(test_source),
             "-o", str(cls.input_tests)],
            capture_output=True, text=True, timeout=30,
        )
        if compilation.returncode:
            raise AssertionError(compilation.stderr)

        # Compile the exact generated JSON writer in a process harness. Cells
        # are its real source state; no native window or frame is manufactured.
        declaration = cls.source.split("struct RuntimeState {", 1)[1].split("\n}", 1)[0]
        fields = re.findall(r"^    (\w+): Cell<(\w+)>,", declaration, re.M)
        writer = cls.source.split("    fn write_evidence(&self, status: &str) {", 1)[1]
        writer = "    fn write_evidence(&self, status: &str) {" + writer.split("\n    fn drive", 1)[0]
        declarations = "\n".join(f"    {name}: Cell<{kind}>," for name, kind in fields)
        initializers = "\n".join(
            f"        {name}: Cell::new({'false' if kind == 'bool' else '0'}),"
            for name, kind in fields
        )
        harness = '''use std::cell::{Cell, RefCell};
use std::{env, fs};
use std::path::PathBuf;
use std::time::Instant;
const TRUSTED_TITLE: &str = "TrillionniumOS Trusted Workspace";
struct RuntimeState {
    output: PathBuf,
    started_at: Instant,
    webview: RefCell<Option<()>>,
FIELDS
}
impl RuntimeState {
@@SOURCE_WRITER@@
}
fn main() {
    let args: Vec<String> = env::args().collect();
    let state = RuntimeState {
        output: PathBuf::from(&args[1]), started_at: Instant::now(),
        webview: RefCell::new(Some(())),
INITIALIZERS
    };
    state.generation.set(1);
    state.frame_count.set(218);
    state.presented_frame.set(218);
    state.input_events_sent.set(12);
    state.input_events_handled.set(2);
    if args[2] != "initial" {
        state.generation.set(2);
        state.recovery_started.set(true);
        state.content_process_termination_observed.set(true);
        state.recovery_frame_baseline.set(217);
        state.presented_frame.set(if args[2] == "unpainted" { 217 } else { 218 });
    }
    state.write_evidence("HOST_JSON_WRITER_TEST_ONLY");
}
'''.replace("FIELDS", declarations).replace("INITIALIZERS", initializers).replace("@@SOURCE_WRITER@@", writer)
        evidence_source = cls.work / "evidence.rs"
        evidence_source.write_text(harness)
        cls.evidence_writer = cls.work / "evidence_writer"
        compilation = subprocess.run(
            ["rustc", "--edition=2024", str(evidence_source),
             "-o", str(cls.evidence_writer)],
            capture_output=True, text=True, timeout=30,
        )
        if compilation.returncode:
            raise AssertionError(compilation.stderr)

    def test_actual_rust_sequence_behavior(self) -> None:
        result = subprocess.run(
            [str(self.input_tests)], check=True, capture_output=True,
            text=True, timeout=20,
        )
        self.assertIn("6 passed", result.stdout)

    def test_observed_json_never_claims_initial_or_unpainted_recovery(self) -> None:
        for scenario, expected in [("initial", False), ("unpainted", False), ("recovered", True)]:
            with self.subTest(scenario=scenario):
                output = self.work / scenario
                output.mkdir()
                subprocess.run(
                    [str(self.evidence_writer), str(output), scenario],
                    check=True, capture_output=True, text=True, timeout=10,
                )
                fact = json.loads((output / "runtime-ready.json").read_text())
                self.assertIs(fact["trusted_chrome_survived_recovery"], expected)
                self.assertEqual(fact["status"], "HOST_JSON_WRITER_TEST_ONLY")
                self.assertEqual(fact["input_events_handled"], 2)

    def test_transformation_is_digest_bound_and_deterministic(self) -> None:
        record = json.loads(self.record.read_text())
        self.assertEqual(record["source_sha256"], hashlib.sha256(RUNTIME.read_bytes()).hexdigest())
        self.assertEqual(record["output_sha256"], hashlib.sha256(self.generated.read_bytes()).hexdigest())
        output = self.work / "second.rs"
        subprocess.run(
            ["python3", str(ROOT / "tools/prepare_d2i_runtime.py"),
             "--source", str(RUNTIME), "--output", str(output),
             "--evidence", str(self.work / "second.json")],
            check=True, capture_output=True, text=True, timeout=20,
        )
        self.assertEqual(output.read_bytes(), self.generated.read_bytes())

    def test_deadline_and_input_gate_are_before_all_evidence_early_returns(self) -> None:
        drive = self.source.split("    fn drive(", 1)[1].split("\n}\n", 1)[0]
        self.assertLess(drive.index("qualification_input::DEADLINE"), drive.index("spin_event_loop()"))
        self.assertEqual(drive.count("qualification_input::DEADLINE"), 2)
        self.assertLess(drive.rindex("qualification_input::DEADLINE"), drive.index("send_qualification_input()"))
        self.assertLess(drive.index("qualification_inputs.borrow().complete()"), drive.index("request_page_input_evidence()"))
        self.assertEqual(self.source.count("state.drive(true)"), 1)
        about_to_wait = self.source.split("    fn about_to_wait(", 1)[1]
        self.assertIn("state.drive(true)", about_to_wait)
        self.assertIn("self.input_events_handled.get() >= 3", drive)
        self.assertIn("self.ime_composition_events_sent.get() == 3", drive)
        recovery = self.source.split("    fn begin_recovery(", 1)[1].split("    fn request_recovery_screenshot", 1)[0]
        self.assertIn("qualification_input::Sequence::new(2)", recovery)
        self.assertIn("self.input_events_handled.set(0)", recovery)
        self.assertIn("self.pending_move.set(None)", recovery)
        self.assertNotIn("started_at =", recovery)
        self.assertIn("state.generation.get() != generation || !state.current_webview(&current)", self.source)
        self.assertIn("self.pending_move.get() == Some(event_id)", self.source)

    def test_source_shape_drift_refuses_publication(self) -> None:
        drift = self.work / "drift.rs"
        drift.write_text(RUNTIME.read_text().replace(
            "fn notify_crashed(&self, webview: WebView,", "fn notify_crashed(&self, _webview: WebView,", 1,
        ))
        output, evidence = self.work / "refused.rs", self.work / "refused.json"
        result = subprocess.run(
            ["python3", str(ROOT / "tools/prepare_d2i_runtime.py"),
             "--source", str(drift), "--output", str(output), "--evidence", str(evidence)],
            capture_output=True, text=True, timeout=20,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("navigation delegate", result.stderr)
        self.assertFalse(output.exists())
        self.assertFalse(evidence.exists())

    def test_guest_and_host_require_observed_recovery_and_original_input_floor(self) -> None:
        guest = (ROOT / "packaging/debian/image/d2i-overlay/usr/local/libexec/trillionnium-d2i-acceptance").read_text()
        self.assertIn("for key in trusted_chrome_survived_recovery", guest)
        self.assertIn("${handled:-0} -ge 3", guest)
        host = self.work / "boot.sh"
        subprocess.run(
            ["python3", str(ROOT / "tools/prepare_d2i_boot_runner.py"),
             "--source", str(ROOT / "tests/qemu/run-d2i-boot-test.base.sh"),
             "--output", str(host), "--evidence", str(self.work / "boot.json")],
            check=True, capture_output=True, text=True, timeout=20,
        )
        text = host.read_text()
        self.assertIn('assert runtime["trusted_chrome_survived_recovery"] is True', text)
        self.assertIn('assert runtime["input_events_handled"] >= 3', text)


if __name__ == "__main__":
    unittest.main()
