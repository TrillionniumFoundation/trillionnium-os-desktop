"""Inert contract fixtures only. No result here is a native benchmark result."""
import copy
import contextlib
import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import comparison as gate


def h(label):
    return hashlib.sha256(label.encode()).hexdigest()


def energy(label):
    return {"microjoules": 17, "attribution": "exclusive-trial-system", "meter_profile_sha256": h(label)}


def contract_fixture():
    policy = {"source_sha256": h("inert-policy-source"), "entry_elf_sha256": h("inert-entry"),
              "configuration_sha256": h("inert-config"), "rules": dict(gate.POLICY_RULES),
              "effect_path": "original-writer/grant-provider/ProductionHos2Target", "inference_location": "none"}
    plan = {"schema": "hepta.cpu-three-policy-plan.v1", "experiment_id": "inert-unit-contract",
            "common": {
                "sources": {name: {"head": digit * 40, "tree": digit * 40}
                            for name, digit in (("desktop", "1"), ("hepta", "2"))},
                "workload": {"code_sha256": h("inert-work"), "data_sha256": h("inert-data"), "task_ids": ["a", "b"]},
                "native": {"mode": "native-control", "cpu_profile": "N0-single-cpu",
                           "kernel_sha256": h("inert-kernel"), "rootfs_sha256": h("inert-rootfs")},
                "budget": {"period_ns": 100_000_000, "maximum_cap_ns": 50_000_000, "initial_cap_ns": 25_000_000,
                           "local_cpu_cores": 2, "local_memory_bytes": 8 * 1024**3, "external_envelope_sha256": h("inert-ceiling")},
                "faults": {"profile": "none", "schedule_sha256": h("no-fault")},
                "environment": {"hardware_sha256": h("inert-host"), "background_sha256": h("inert-background"),
                                "min_temperature_millicelsius": 20_000, "max_temperature_millicelsius": 80_000},
                "collector": {"source_sha256": h("inert-collector"), "clock": "continuous-observer-monotonic-ns",
                              "scope": "whole-arm-local-and-external"}},
            "policies": {arm: copy.deepcopy(policy) for arm in gate.ARMS},
            "rounds": {"states": list(gate.STATES), "count": 1, "seed": 7}}
    plan["policies"]["fixed"]["target_cap_ns"] = 25_000_000
    plan["policies"]["hepta"].update(inference_location="external", model_configuration_sha256=h("inert-model"))
    trials = []
    for index, expected in enumerate(gate.schedule(plan)):
        start = index * 100
        external = ({"cpu_ns": 11, "peak_bytes": 12, "energy": energy("provider-meter"),
                     "provider_measurement_sha256": h("inert-provider-record")}
                    if expected["arm"] == "hepta" else None)
        trials.append({"schema": "hepta.cpu-policy-trial.v1", **expected,
                       "plan_sha256": gate.digest(plan), "common_sha256": gate.digest(plan["common"]),
                       "policy_sha256": gate.digest(plan["policies"][expected["arm"]]),
                       "budget": copy.deepcopy(plan["common"]["budget"]), "started_ns": start, "ended_ns": start + 90,
                       "temperature_before_millicelsius": 40_000, "temperature_after_millicelsius": 40_000,
                       "tasks": [{"task_id": task, "status": status, "started_ns": start, "ended_ns": start + 80,
                                  "completion_evidence_sha256": h("inert-" + task)}
                                 for task, status in (("a", "success"), ("b", "timeout"))],
                       "costs": {"local_cpu_ns": {part: int(part != "local_inference") for part in gate.CPU_PARTS},
                                 "local_memory": {"scope": "owned-subtree-peak", "peak_bytes": 32},
                                 "local_energy": energy("local-meter"), "external_inference": external,
                                 "recovery": {"status": "not-needed", "elapsed_ns": 0, "lost_work_units": 0}},
                       "raw_measurement_sha256": h("inert-raw-" + expected["trial_id"]),
                       "original_owner_evidence_sha256": h("inert-owner")})
    return plan, trials


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.plan, self.trials = contract_fixture()

    def rejected(self, text):
        result = gate.assess(self.plan, self.trials)
        self.assertFalse(result["contract_complete"])
        self.assertFalse(result["ranking_allowed"])
        self.assertIn(text, " ".join(result["contract_errors"]))

    def test_full_inert_contract_still_cannot_claim_native_comparison_or_benefit(self):
        result = gate.assess(self.plan, self.trials)
        self.assertTrue(result["contract_complete"])
        self.assertEqual(result["reported_denominators"]["hepta"], {"success": 2, "failure": 0, "timeout": 2})
        self.assertFalse(result["native_measurements_verified"])
        self.assertFalse(result["comparison_complete"])
        self.assertFalse(result["ranking_allowed"])
        self.assertIsNone(result["benefit_claim"])

    def test_dropping_hepta_arm_refuses_comparison(self):
        self.trials = [trial for trial in self.trials if trial["arm"] != "hepta"]
        self.rejected("all predeclared trials")

    def test_changed_budget_does_not_share_the_frozen_common_binding(self):
        self.trials[0]["budget"]["maximum_cap_ns"] += 1
        self.rejected("budget drift")

    def test_source_or_workload_drift_is_rejected(self):
        self.trials[0]["common_sha256"] = h("other-source")
        self.rejected("source or budget drift")

    def test_unmeasured_external_inference_is_not_zero(self):
        next(trial for trial in self.trials if trial["arm"] == "hepta")["costs"]["external_inference"] = None
        self.rejected("unknown is not zero")

    def test_shared_rapl_cannot_become_local_task_energy(self):
        self.trials[0]["costs"]["local_energy"]["attribution"] = "shared-package-rapl"
        self.rejected("shared/package RAPL")

    def test_external_package_energy_cannot_be_attributed_to_one_inference(self):
        trial = next(trial for trial in self.trials if trial["arm"] == "hepta")
        trial["costs"]["external_inference"]["energy"]["attribution"] = "provider-shared-package"
        self.rejected("shared/package RAPL")

    def test_external_cpu_and_memory_cannot_be_omitted_when_energy_exists(self):
        trial = next(trial for trial in self.trials if trial["arm"] == "hepta")
        trial["costs"]["external_inference"]["cpu_ns"] = None
        self.rejected("external inference CPU")

    def test_one_process_rss_does_not_pass_as_subtree_peak(self):
        self.trials[0]["costs"]["local_memory"]["scope"] = "one-process-rss"
        self.rejected("one-process RSS")

    def test_deleting_a_timeout_changes_the_denominator(self):
        self.trials[0]["tasks"].pop()
        self.rejected("denominator")

    def test_failure_is_retained_and_not_a_reason_to_discard_the_whole_arm(self):
        for trial in self.trials:
            trial["tasks"][0]["status"] = "failure"
        result = gate.assess(self.plan, self.trials)
        self.assertTrue(result["contract_complete"])
        self.assertEqual(result["reported_denominators"]["fixed"], {"success": 0, "failure": 2, "timeout": 2})

    def test_sorting_results_after_observing_them_cannot_rewrite_trial_order(self):
        self.trials[0], self.trials[1] = self.trials[1], self.trials[0]
        self.rejected("trial ID/arm/state/repetition")

    def test_missing_inference_cpu_category_is_not_a_free_controller(self):
        del self.trials[0]["costs"]["local_cpu_ns"]["local_inference"]
        self.rejected("disjoint complete categories")

    def test_task_clock_cannot_extend_past_its_observed_trial(self):
        self.trials[0]["tasks"][0]["ended_ns"] = self.trials[0]["ended_ns"] + 1
        self.rejected("task terminal/censoring time")

    def test_actual_hepta_configuration_is_required_even_with_three_labels(self):
        del self.plan["policies"]["hepta"]["model_configuration_sha256"]
        self.rejected("actual Hepta/model configuration")

    def test_boolean_repeat_is_not_an_exact_integer(self):
        self.trials[0]["repetition"] = False
        self.rejected("trial ID/arm/state/repetition")

    def test_native_owner_cycle_receipt_is_not_a_three_policy_trial(self):
        self.trials[0] = {"schema": "hepta.cpu-policy-native-prerequisite.v1", "ranking_allowed": False}
        self.rejected("unsupported trial schema")

    def test_relabelling_one_raw_record_does_not_create_independent_trials(self):
        self.trials[1]["raw_measurement_sha256"] = self.trials[0]["raw_measurement_sha256"]
        self.rejected("one raw trial record was reused")

    def test_actual_cli_persists_refusal_and_exits_nonzero_for_missing_arm(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "plan.json").write_text(json.dumps(self.plan))
            (root / "trials.json").write_text(json.dumps(self.trials[:-1]))
            with contextlib.redirect_stdout(io.StringIO()):
                code = gate.main(["--plan", str(root / "plan.json"), "--trials", str(root / "trials.json"),
                                  "--output", str(root / "result.json")])
            self.assertEqual(code, 2)
            result = gate.read_json(root / "result.json")
            self.assertFalse(result["contract_complete"])
            self.assertFalse(result["ranking_allowed"])

    def test_duplicate_keys_and_nonfinite_input_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bad.json"
            for raw in ('{"x":1,"x":2}', '{"x":NaN}'):
                path.write_text(raw)
                with self.assertRaises(ValueError):
                    gate.read_json(path)

    def test_retained_artifact_change_and_symlink_cannot_reuse_a_digest(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw = b"inert retained record"
            (root / "raw").write_bytes(raw)
            record = {"path": "raw", "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
            gate.artifact(root, record, "raw")
            (root / "raw").write_bytes(raw[:-1] + b"X")
            with self.assertRaisesRegex(ValueError, "bytes changed"):
                gate.artifact(root, record, "raw")
            (root / "alias").symlink_to(root / "raw")
            with self.assertRaisesRegex(ValueError, "symlink"):
                gate.artifact(root, {**record, "path": "alias"}, "raw")


if __name__ == "__main__":
    unittest.main()
