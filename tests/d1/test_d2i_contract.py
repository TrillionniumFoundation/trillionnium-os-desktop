from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


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


if __name__ == "__main__":
    unittest.main()