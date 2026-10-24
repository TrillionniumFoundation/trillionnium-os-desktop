"""Adversarial inert transcripts; none is native Hepta qualification."""
import copy
import json
from pathlib import Path
import subprocess
import sys
import unittest

import native_owner_activation_evidence as activation
import native_owner_evidence as original
from native_owner_activation_test_records import ActivationRecords
from run_native_owner_activation import accept_actual_observations
from test_native_owner_evidence import ELF, NONCE


class OriginalPartialActivationTests(unittest.TestCase):
    def test_both_complete_shapes_require_independent_actual_root_files(self):
        for scenario, generation in zip(activation.SCENARIOS, (2, 3)):
            with self.subTest(scenario=scenario):
                result = ActivationRecords(scenario).evaluate()
                self.assertTrue(result["partial_activation_transcript_verified"])
                self.assertEqual((result["initial_local_writer_generation"], result["failed_local_writer_generation"],
                                  result["reentered_local_writer_generation"]), (1, 2, generation))
                self.assertEqual(result["operation_count"], 2)
                self.assertEqual(len(result["root_launch_observations_expected"]), 1)
                for key in ("passed", "partial_activation_recovery_verified", "root_launch_files_verified",
                            "original_native_owner_cycle_verified", "grant_renewal_verified", "repeated_recovery_verified",
                            "cross_boot_unknown_preservation_verified", "unbounded_persistent_cpu_verified",
                            "power_loss_verified", "g2_complete", "production_ready"):
                    self.assertFalse(result[key], key)
                with self.assertRaises(ValueError):
                    accept_actual_observations(result, {"passed": True, "readonly_extraction": True, "actual_files": []})

    def test_actual_selected_fault_and_waitid_are_required(self):
        for scenario in activation.SCENARIOS:
            for case in ("absent", "point", "pid", "spawn", "poll", "wait", "signal", "time"):
                records = ActivationRecords(scenario)
                failed = records.event("activation_recovery_prepared")["reconciliation"]
                fault = failed["fault"]
                if case == "absent": failed["fault"] = None
                elif case == "point": fault["point"] = "after_material" if scenario == activation.SCENARIOS[0] else "after_proof"
                elif case == "pid": fault["peer"]["pid"] = 2
                elif case == "spawn": fault["spawn_generation"] += 1
                elif case == "poll": fault["pidfd_revents"] = 0
                elif case == "wait": fault["wait_kind"] = "exited"
                elif case == "signal": fault["wait_value"] = 0
                else: fault["observed_boottime_ns"] = 1
                with self.subTest(scenario=scenario, case=case), self.assertRaises(ValueError):
                    records.evaluate()

    def test_original_starting_failed_lifecycle_and_reap_are_not_skipped(self):
        for case in ("active", "pid", "healthy", "lifecycle", "generation", "new-spawn", "release", "old-reap"):
            records = ActivationRecords(activation.SCENARIOS[0])
            failed = records.event("activation_recovery_prepared")
            if case == "active": failed["supervisor"]["active"] = True
            elif case == "pid": failed["supervisor"]["process_system_id"] = 4
            elif case == "healthy": failed["supervisor"]["healthy"] = True
            elif case == "lifecycle": failed["reconciliation"]["registry_failed"]["lifecycle"] = "stopped"
            elif case == "generation": failed["reconciliation"]["registry_failed"]["generation"] += 1
            elif case == "new-spawn": records.event("continuity_owner", 1)["supervisor"]["spawn_generation"] -= 1
            elif case == "release": records.event("owner_released")["receipt"]["state"] = "active"
            else: records.event("owner_stopped")["supervisor"]["events"][-1]["details"]["success"] = False
            with self.subTest(case=case), self.assertRaises(ValueError):
                records.evaluate()

    def test_failed_canonical_writer_keeps_exact_original_cut_and_finite_scope(self):
        for case in ("generation", "epoch", "lease-id", "duration", "scope", "payload", "sequence", "proof"):
            records = ActivationRecords(activation.SCENARIOS[0])
            failed = records.event("activation_recovery_prepared")["reconciliation"]
            writer = failed["canonical_writer"]
            if case == "generation": writer["local_lease_generation"] += 1
            elif case == "epoch": writer["owner_epoch"] += 1
            elif case == "lease-id": writer["authority_lease"]["lease_id"] = "native-cpu-writer-2"
            elif case == "duration": writer["authority_lease"]["expires_at_unix_ms"] += 1
            elif case in ("scope", "payload"): writer["authority_lease"]["binding"][case + "_sha256"][0] ^= 1
            elif case == "sequence": failed["issuer_sequence"] = 1
            else: failed["canonical_proof_sha256"] = records.event("owner_released")["current"]["head"]["writer_binding"]["authority_grant_digest"]
            with self.subTest(case=case), self.assertRaises(ValueError):
                records.evaluate()

    def test_all_selected_authority_must_retire_before_the_actual_old_expiry(self):
        for case in ("missing", "live-omitted", "revision", "reason", "after", "expiry", "observed", "clock"):
            records = ActivationRecords(activation.SCENARIOS[1])
            failed = records.event("activation_recovery_prepared")["reconciliation"]
            if case == "missing": failed["revocations_applied"].pop()
            elif case == "live-omitted":
                failed["registry_before"]["leases"] = []
                failed["revocations_applied"] = []
                failed["registry_after"]["store_revision"] = failed["registry_before"]["store_revision"]
            elif case == "revision": failed["revocations_applied"][0]["previous_lease_revision"] += 1
            elif case == "reason": failed["revocations_applied"][0]["reason_sha256"][0] ^= 1
            elif case == "after": failed["registry_after"]["leases"] = copy.deepcopy(failed["registry_before"]["leases"][:1])
            elif case == "expiry": failed["local_expiry_unix_ms"] += 1
            elif case == "observed": failed["observed_unix_ms"] = failed["local_expiry_unix_ms"] - 1
            else: failed["registry_after"]["observed_unix_ms"] = failed["registry_before"]["observed_unix_ms"] - 1
            with self.subTest(case=case), self.assertRaises(ValueError):
                records.evaluate()

    def test_installed_and_unused_generations_have_distinct_physical_predecessors(self):
        for scenario in activation.SCENARIOS:
            for case in ("mode", "failed-cut", "publisher", "material", "frontier", "adopted-cut"):
                records = ActivationRecords(scenario)
                failed = records.event("activation_recovery_prepared")["reconciliation"]
                adopted = records.event("material_adopted")
                if case == "mode": failed["mode"] = "installed" if scenario == activation.SCENARIOS[0] else "unactivated"
                elif case == "failed-cut": failed["previous"]["head"]["last_current"]["state_digest"] = "ab" * 32
                elif case == "publisher":
                    adopted["successor"]["head"]["publisher_epoch"] += 1
                    adopted["successor"]["token"]["publisher_epoch"] += 1
                elif case == "material": adopted["material_sha256"] = "cd" * 32
                elif case == "frontier": failed["device_frontier"]["state_sha256"][0] ^= 1
                else: adopted["successor"]["head"]["last_current"]["state_digest"] = "ef" * 32
                with self.subTest(scenario=scenario, case=case), self.assertRaises(ValueError):
                    records.evaluate()

    def test_fresh_owner_must_rotate_failed_epoch_and_original_proof_sequence(self):
        class FailedEpochReused(ActivationRecords):
            def authority(self, previous):
                if self.spawn > 5:
                    self.owner_epoch = 12
                return super().authority(previous)

        class FailedSequenceReused(ActivationRecords):
            def authority(self, previous):
                if self.spawn > 5:
                    self.issuer_sequence = 3
                return super().authority(previous)

        for scenario in activation.SCENARIOS:
            for constructor in (FailedEpochReused, FailedSequenceReused):
                with self.subTest(scenario=scenario, constructor=constructor.__name__), self.assertRaises(ValueError):
                    constructor(scenario).evaluate()

    def test_fresh_effect_window_kernel_files_and_final_owner_cut_are_mandatory(self):
        for case in ("window", "no-cpu", "cap", "terminal", "image", "saved", "watchdog", "extra"):
            records = ActivationRecords(activation.SCENARIOS[1])
            if case == "window": records.event("usage_window", 1)["second"] = copy.deepcopy(records.event("usage_window", 1)["first"])
            elif case == "no-cpu": records.event("usage_window", 1)["second"]["cumulative_cpu_ns"] = records.event("usage_window", 1)["first"]["cumulative_cpu_ns"]
            elif case == "cap": records.event("native_result", 1)["after"]["active_cap_ns"] = 25_000_000
            elif case == "terminal": records.event("source_terminal", 1)["terminal_json"] = records.event("source_terminal")["terminal_json"]
            elif case == "image": next(iter(records.kernel_before.values())).pop(0)
            elif case == "saved": records.event("kernel_launch_saved")["durable_payload_json"] += " "
            elif case == "watchdog": records.event("kernel_launch_saved")["retirement_receipt"][56] ^= 1
            else: records.add("unexpected-success", {})
            with self.subTest(case=case), self.assertRaises(ValueError):
                records.evaluate()

    def test_original_public_six_case_and_boot_rules_do_not_accept_new_plans(self):
        self.assertEqual(len(original.SUPPORTED_SCENARIOS), 6)
        for scenario in activation.SCENARIOS:
            records = ActivationRecords(scenario)
            with self.assertRaises(ValueError):
                original.evaluate(records.raw(), 33, False, False, scenario, NONCE, ELF)
            for code, timeout, excess in ((0, False, False), (33, True, False), (33, False, True)):
                with self.subTest(scenario=scenario, code=code, timeout=timeout, excess=excess), self.assertRaises(ValueError):
                    activation.evaluate(records.raw(), code, timeout, excess, scenario, NONCE, ELF)
            while len(records.records) <= original.MAX_EVENTS:
                records.add("inert-extra", {})
            with self.assertRaisesRegex(ValueError, "bounded original-owner"):
                records.evaluate()

    def test_runner_is_disabled_until_explicit_actual_original_inputs(self):
        script = Path(__file__).with_name("run_native_owner_activation.py")
        process = subprocess.run([sys.executable, "-B", str(script)], stdin=subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, timeout=10)
        self.assertEqual(process.returncode, 0, process.stderr.decode())
        result = json.loads(process.stdout)
        for key in ("passed", "native_execution_attempted", "both_partial_activations_verified",
                    "activation_after_proof_verified", "activation_after_material_verified",
                    "original_native_owner_cycle_verified", "production_ready", "g2_complete"):
            self.assertFalse(result[key], key)
        self.assertIn("disabled", result["status"])


if __name__ == "__main__":
    unittest.main()
