from __future__ import annotations

import base64
import copy
import json
import os
import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from hardware_evidence_verifier import (  # noqa: E402
    HardwareEvidenceError,
    create_fixture_bundle,
    sha256,
    signed_payload,
    verify_evidence,
)
from hardware_verification_receipt import (  # noqa: E402
    HardwareReceiptError,
    verify_hardware_verification_receipt,
)
from trusted_app_bundle import ed25519_sign_fixture  # noqa: E402

SEED = bytes.fromhex(
    "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
)


class HardwareEvidenceVerifierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(
            (ROOT / "contracts/hardware-beta-qualification.v1.json").read_text()
        )

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.evidence, self.trust = create_fixture_bundle(
            self.contract, self.root, SEED
        )
        self.now_epoch = 500

    def resign(self) -> None:
        self.evidence["signature"]["value_base64"] = base64.b64encode(
            ed25519_sign_fixture(SEED, signed_payload(self.evidence))
        ).decode("ascii")

    def artifact(self, role: str) -> dict:
        return next(item for item in self.evidence["artifacts"] if item["role"] == role)

    def artifact_path(self, role: str) -> Path:
        return self.root / self.artifact(role)["path"]

    def refresh_artifact(self, role: str) -> None:
        record = self.artifact(role)
        data = self.artifact_path(role).read_bytes()
        record["bytes"] = len(data)
        record["sha256"] = sha256(data)
        identity_fields = {
            "sbom": "sbom_sha256",
            "licenses": "licenses_sha256",
            "provenance": "provenance_sha256",
            "known_limitations": "known_limitations_sha256",
        }
        if role in identity_fields:
            self.evidence["artifact_identity"][identity_fields[role]] = record[
                "sha256"
            ]
        self.resign()

    def write_json_role(self, role: str, value: dict) -> None:
        self.artifact_path(role).write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.refresh_artifact(role)

    def read_json_role(self, role: str) -> dict:
        return json.loads(self.artifact_path(role).read_text())

    def write_metrics(self, records: list[dict]) -> None:
        self.artifact_path("metrics_samples").write_text(
            "".join(json.dumps(item, sort_keys=True) + "\n" for item in records),
            encoding="utf-8",
        )
        self.refresh_artifact("metrics_samples")

    def fixture_metrics(self) -> list[dict]:
        return [
            json.loads(line)
            for line in self.artifact_path("metrics_samples")
            .read_text()
            .splitlines()
            if line
        ]

    def physicalize(self, *, complete_metrics: bool = True) -> None:
        thresholds = self.contract["thresholds"]
        self.evidence["environment_kind"] = "physical_hardware"
        self.evidence["lab"]["signer_role"] = "independent_hardware_lab"
        key = self.trust["labs"]["fixture-lab"]["keys"][
            "fixture-lab-key-1"
        ]
        key["signer_role"] = "independent_hardware_lab"
        key["production_enrolled"] = True
        self.evidence["started_at_epoch"] = 100
        self.evidence["ended_at_epoch"] = (
            100 + thresholds["final_stability_seconds_min"]
        )
        self.now_epoch = self.evidence["ended_at_epoch"] + 10
        if complete_metrics:
            start = self.evidence["started_at_epoch"]
            end = self.evidence["ended_at_epoch"]
            gap = thresholds["maximum_sample_gap_seconds"]
            timestamps = list(range(start, end + 1, gap))
            if timestamps[-1] != end:
                timestamps.append(end)
            records = [
                {
                    "timestamp_epoch": timestamp,
                    "rss_mib": 600.0 + index * 0.001,
                    "fd_count": 128,
                    "pid_count": 64,
                    "native_input_latency_ms": 10.0,
                    "agent_observe_latency_ms": 50.0,
                    "agent_act_latency_ms": 80.0,
                }
                for index, timestamp in enumerate(timestamps)
            ]
            self.write_metrics(records)
        else:
            self.resign()

    def make_physical_cycles_complete(self) -> None:
        thresholds = self.contract["thresholds"]
        value = self.read_json_role("cycle_results")
        value["cold_boot_ready_ms"] = [10000] * thresholds[
            "cold_boot_cycles_min"
        ]
        value["compositor_to_first_frame_ms"] = [1000] * thresholds[
            "cold_boot_cycles_min"
        ]
        value["content_crash_recovery_ms"] = [1000] * thresholds[
            "content_crash_recovery_cycles_min"
        ]
        value["suspend_resume_ms"] = [2000] * thresholds[
            "suspend_resume_cycles_min"
        ]
        value["update_commit_results"] = [
            {"cycle": index + 1, "status": "PASS"}
            for index in range(thresholds["update_commit_cycles_min"])
        ]
        value["update_rollback_results"] = [
            {"cycle": index + 1, "status": "PASS"}
            for index in range(thresholds["update_rollback_cycles_min"])
        ]
        value["power_loss_results"] = [
            {"cycle": index + 1, "status": "PASS"}
            for index in range(thresholds["power_loss_cycles_min"])
        ]
        self.write_json_role("cycle_results", value)

    def make_physical_subsystems_complete(self) -> None:
        value = self.read_json_role("subsystem_results")
        thresholds = self.contract["thresholds"]
        for category, minimum_key in (
            ("accessibility", "accessibility_scenarios_min"),
            ("ime", "ime_scenarios_min"),
            ("display", "multi_monitor_scenarios_min"),
        ):
            records = value["results"][category]
            minimum = thresholds[minimum_key]
            base, remainder = divmod(minimum, len(records))
            for index, record in enumerate(records.values()):
                record["cases"] = base + (1 if index < remainder else 0)
        self.write_json_role("subsystem_results", value)

    def make_physical_security_complete(self) -> None:
        value = self.read_json_role("security_results")
        minimum = self.contract["thresholds"]["security_scenarios_min"]
        records = value["categories"]
        base, remainder = divmod(minimum, len(records))
        total = 0
        for index, record in enumerate(records.values()):
            record["cases"] = base + (1 if index < remainder else 0)
            total += record["cases"]
        value["scenario_count"] = total
        self.write_json_role("security_results", value)

    def make_complete_physical_shape(self) -> None:
        self.physicalize()
        self.make_physical_cycles_complete()
        self.make_physical_subsystems_complete()
        self.make_physical_security_complete()
        self.resign()

    def verify(self, *, require_physical: bool = False) -> dict:
        return verify_evidence(
            self.evidence,
            self.root,
            self.trust,
            self.contract,
            now_epoch=self.now_epoch,
            require_physical=require_physical,
        )

    def assert_rejected(self, reason: str, callback) -> None:
        with self.assertRaises(HardwareEvidenceError) as captured:
            callback()
        self.assertEqual(captured.exception.reason, reason)

    def test_valid_fixture_is_format_only_and_not_promotion_eligible(self) -> None:
        result = self.verify()
        self.assertEqual(result["status"], "PASS_FIXTURE_FORMAT_ONLY")
        self.assertFalse(result["policy_eligible"])
        self.assertFalse(result["physical_hardware_run_completed_by_this_source_gate"])
        self.assertFalse(result["hardware_beta_promoted"])
        self.assertFalse(result["release_ready"])
        verify_hardware_verification_receipt(result)

    def test_fixture_cannot_satisfy_physical_gate(self) -> None:
        self.assert_rejected(
            "PHYSICAL_HARDWARE_EVIDENCE_REQUIRED",
            lambda: self.verify(require_physical=True),
        )

    def test_physical_duration_independent_role_and_production_key_required(self) -> None:
        self.evidence["environment_kind"] = "physical_hardware"
        self.resign()
        self.assert_rejected(
            "FINAL_STABILITY_DURATION_NOT_MET",
            lambda: self.verify(require_physical=True),
        )
        self.evidence["ended_at_epoch"] = (
            self.evidence["started_at_epoch"]
            + self.contract["thresholds"]["final_stability_seconds_min"]
        )
        self.now_epoch = self.evidence["ended_at_epoch"] + 1
        self.resign()
        self.assert_rejected(
            "INDEPENDENT_HARDWARE_LAB_ROLE_REQUIRED",
            lambda: self.verify(require_physical=True),
        )
        self.evidence["lab"]["signer_role"] = "independent_hardware_lab"
        key = self.trust["labs"]["fixture-lab"]["keys"][
            "fixture-lab-key-1"
        ]
        key["signer_role"] = "independent_hardware_lab"
        self.resign()
        self.assert_rejected(
            "PRODUCTION_HARDWARE_LAB_KEY_REQUIRED",
            lambda: self.verify(require_physical=True),
        )

    def test_signature_tamper_and_wrong_profile_rejected(self) -> None:
        raw = bytearray(base64.b64decode(self.evidence["signature"]["value_base64"]))
        raw[0] ^= 1
        self.evidence["signature"]["value_base64"] = base64.b64encode(raw).decode()
        self.assert_rejected(
            "HARDWARE_EVIDENCE_SIGNATURE_REJECTED", self.verify
        )
        self.evidence, self.trust = create_fixture_bundle(
            self.contract, self.root, SEED
        )
        self.evidence["hardware_profile_id"] = "other-profile"
        self.resign()
        self.assert_rejected("HARDWARE_PROFILE_MISMATCH", self.verify)

    def test_incomplete_bom_and_critical_outcome_rejected(self) -> None:
        self.evidence["bom"].pop("gpu_driver")
        self.resign()
        self.assert_rejected("HARDWARE_BOM_FIELD_SET_MISMATCH", self.verify)
        self.evidence, self.trust = create_fixture_bundle(
            self.contract, self.root, SEED
        )
        self.evidence["critical_outcomes"]["network_policy_bypasses"] = 1
        self.resign()
        self.assert_rejected(
            "CRITICAL_OUTCOME_ZERO_TOLERANCE_VIOLATION", self.verify
        )

    def test_artifact_identity_role_digest_mismatch_rejected(self) -> None:
        self.evidence["artifact_identity"]["sbom_sha256"] = "0" * 64
        self.resign()
        self.assert_rejected(
            "ARTIFACT_IDENTITY_ROLE_DIGEST_MISMATCH", self.verify
        )

    def test_missing_extra_symlink_and_digest_artifacts_rejected(self) -> None:
        self.artifact_path("boot_logs").unlink()
        self.assert_rejected("EVIDENCE_ARTIFACT_MISSING", self.verify)

        self.evidence, self.trust = create_fixture_bundle(
            self.contract, self.root, SEED
        )
        (self.root / "unlisted.txt").write_text("extra\n")
        self.assert_rejected("EVIDENCE_ARTIFACT_SET_MISMATCH", self.verify)

        if hasattr(os, "symlink"):
            self.evidence, self.trust = create_fixture_bundle(
                self.contract, self.root, SEED
            )
            target = self.artifact_path("boot_logs")
            data = target.read_bytes()
            target.unlink()
            sibling = self.root / "real-boot-log.txt"
            sibling.write_bytes(data)
            os.symlink(sibling.name, target)
            self.assert_rejected("EVIDENCE_ARTIFACT_SYMLINK_REJECTED", self.verify)

        self.evidence, self.trust = create_fixture_bundle(
            self.contract, self.root, SEED
        )
        self.artifact_path("boot_logs").write_text("tampered\n")
        self.assert_rejected("EVIDENCE_ARTIFACT_SIZE_MISMATCH", self.verify)

    def test_metrics_timestamp_order_gap_and_thresholds_enforced(self) -> None:
        records = self.fixture_metrics()
        records[1]["timestamp_epoch"] = records[0]["timestamp_epoch"]
        self.write_metrics(records)
        self.assert_rejected(
            "METRIC_TIMESTAMPS_NOT_STRICTLY_INCREASING", self.verify
        )

        self.evidence, self.trust = create_fixture_bundle(
            self.contract, self.root, SEED
        )
        records = self.fixture_metrics()
        records[1]["timestamp_epoch"] = (
            records[0]["timestamp_epoch"]
            + self.contract["thresholds"]["maximum_sample_gap_seconds"]
            + 1
        )
        for index in range(2, len(records)):
            records[index]["timestamp_epoch"] = records[index - 1][
                "timestamp_epoch"
            ] + 1
        self.write_metrics(records)
        self.assert_rejected("METRIC_SAMPLE_GAP_EXCEEDED", self.verify)

        for field, reason, value in (
            ("rss_mib", "HARDWARE_METRIC_THRESHOLD_EXCEEDED", 5000),
            ("fd_count", "HARDWARE_METRIC_THRESHOLD_EXCEEDED", 5000),
            ("pid_count", "HARDWARE_METRIC_THRESHOLD_EXCEEDED", 600),
            ("native_input_latency_ms", "HARDWARE_METRIC_THRESHOLD_EXCEEDED", 200),
            ("agent_observe_latency_ms", "HARDWARE_METRIC_THRESHOLD_EXCEEDED", 600),
            ("agent_act_latency_ms", "HARDWARE_METRIC_THRESHOLD_EXCEEDED", 1200),
        ):
            self.evidence, self.trust = create_fixture_bundle(
                self.contract, self.root, SEED
            )
            records = self.fixture_metrics()
            for record in records:
                record[field] = value
            self.write_metrics(records)
            self.assert_rejected(reason, self.verify)

    def test_physical_metric_sample_count_and_coverage_enforced(self) -> None:
        self.physicalize(complete_metrics=False)
        key = self.trust["labs"]["fixture-lab"]["keys"][
            "fixture-lab-key-1"
        ]
        key["production_enrolled"] = True
        self.resign()
        self.assert_rejected(
            "METRIC_SAMPLE_COUNT_TOO_LOW",
            lambda: self.verify(require_physical=True),
        )

    def test_cycle_thresholds_and_physical_minimums_enforced(self) -> None:
        cycles = self.read_json_role("cycle_results")
        cycles["cold_boot_ready_ms"] = [
            self.contract["thresholds"]["cold_boot_ready_ms_max"] + 1
        ]
        self.write_json_role("cycle_results", cycles)
        self.assert_rejected("COLD_BOOT_THRESHOLD_EXCEEDED", self.verify)

        self.evidence, self.trust = create_fixture_bundle(
            self.contract, self.root, SEED
        )
        self.physicalize()
        self.make_physical_subsystems_complete()
        self.make_physical_security_complete()
        self.resign()
        self.assert_rejected(
            "HARDWARE_CYCLE_MINIMUM_NOT_MET",
            lambda: self.verify(require_physical=True),
        )

    def test_subsystem_scenario_and_physical_case_minimums_enforced(self) -> None:
        subsystems = self.read_json_role("subsystem_results")
        subsystems["results"]["input"].pop("touchpad")
        self.write_json_role("subsystem_results", subsystems)
        self.assert_rejected("SUBSYSTEM_SCENARIO_SET_MISMATCH", self.verify)

        self.evidence, self.trust = create_fixture_bundle(
            self.contract, self.root, SEED
        )
        self.physicalize()
        self.make_physical_cycles_complete()
        self.make_physical_security_complete()
        self.resign()
        self.assert_rejected(
            "ACCESSIBILITY_SCENARIO_MINIMUM_NOT_MET",
            lambda: self.verify(require_physical=True),
        )

    def test_security_category_minimum_and_zero_tolerance_enforced(self) -> None:
        security = self.read_json_role("security_results")
        security["network_policy_bypasses"] = 1
        self.write_json_role("security_results", security)
        self.assert_rejected(
            "SECURITY_ZERO_TOLERANCE_VIOLATION", self.verify
        )

        self.evidence, self.trust = create_fixture_bundle(
            self.contract, self.root, SEED
        )
        self.physicalize()
        self.make_physical_cycles_complete()
        self.make_physical_subsystems_complete()
        self.resign()
        self.assert_rejected(
            "SECURITY_SCENARIO_MINIMUM_NOT_MET",
            lambda: self.verify(require_physical=True),
        )

    def test_known_limitations_require_independent_review_record(self) -> None:
        self.evidence["known_limitations"] = []
        self.resign()
        self.assert_rejected("KNOWN_LIMITATIONS_REVIEW_REQUIRED", self.verify)
        self.evidence, self.trust = create_fixture_bundle(
            self.contract, self.root, SEED
        )
        self.evidence["known_limitations"][0]["reviewer_role"] = "author"
        self.resign()
        self.assert_rejected(
            "KNOWN_LIMITATION_REVIEWER_ROLE_INVALID", self.verify
        )

    def test_complete_physical_shape_is_policy_eligible_but_not_promoted(self) -> None:
        self.make_complete_physical_shape()
        result = self.verify(require_physical=True)
        self.assertEqual(result["status"], "PASS_PHYSICAL_POLICY_ELIGIBILITY")
        self.assertTrue(result["policy_eligible"])
        self.assertFalse(result["physical_hardware_run_completed_by_this_source_gate"])
        self.assertFalse(result["independent_hardware_lab_signature_obtained_by_this_source_gate"])
        self.assertFalse(result["hardware_beta_promoted"])
        self.assertFalse(result["release_ready"])
        verify_hardware_verification_receipt(result)

    def test_verification_receipt_tamper_is_rejected(self) -> None:
        result = self.verify()
        tampered = copy.deepcopy(result)
        tampered["metrics"]["rss_peak_mib"] += 1
        with self.assertRaisesRegex(
            HardwareReceiptError,
            "HARDWARE_VERIFICATION_RECEIPT_HASH_MISMATCH",
        ):
            verify_hardware_verification_receipt(tampered)


if __name__ == "__main__":
    unittest.main()
