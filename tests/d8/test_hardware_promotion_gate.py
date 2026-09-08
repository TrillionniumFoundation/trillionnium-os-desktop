from __future__ import annotations

import base64
import copy
import json
import sys
import tempfile
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from hardware_evidence_verifier import sha256, signed_payload  # noqa: E402
from hardware_promotion_gate import (  # noqa: E402
    HardwarePromotionError,
    artifact_path,
    artifact_record,
    prepare_strict_fixture,
    verify_gate,
    verify_gate_receipt,
)
from trusted_app_bundle import ed25519_sign_fixture  # noqa: E402

SEED = bytes.fromhex(
    "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60"
)


class HardwarePromotionGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads(
            (ROOT / "contracts/hardware-beta-qualification.v1.json").read_text()
        )

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.evidence, self.trust = prepare_strict_fixture(
            self.contract, self.root, SEED
        )

    def resign(self) -> None:
        self.evidence["signature"]["value_base64"] = base64.b64encode(
            ed25519_sign_fixture(SEED, signed_payload(self.evidence))
        ).decode("ascii")

    def refresh(self, role: str) -> None:
        path = artifact_path(self.evidence, self.root, role)
        record = artifact_record(self.evidence, role)
        data = path.read_bytes()
        record["sha256"] = sha256(data)
        record["bytes"] = len(data)
        identity = {
            "sbom": "sbom_sha256",
            "licenses": "licenses_sha256",
            "provenance": "provenance_sha256",
            "known_limitations": "known_limitations_sha256",
        }
        if role in identity:
            self.evidence["artifact_identity"][identity[role]] = record[
                "sha256"
            ]
        self.resign()

    def verify(self) -> dict:
        return verify_gate(
            self.evidence,
            self.root,
            self.trust,
            self.contract,
            now_epoch=500,
            require_physical=False,
        )

    def assert_rejected(self, reason: str, callback) -> None:
        with self.assertRaises(HardwarePromotionError) as captured:
            callback()
        self.assertEqual(captured.exception.reason, reason)

    def test_strict_fixture_binds_case_totals_and_limitations(self) -> None:
        result = self.verify()
        self.assertEqual(result["status"], "PASS_FIXTURE_FORMAT_ONLY")
        accounting = result["security_case_accounting"]
        self.assertEqual(
            accounting["declared_scenario_count"],
            accounting["category_case_sum"],
        )
        self.assertEqual(result["known_limitations_binding"]["limitation_count"], 1)
        self.assertFalse(result["policy_eligible"])
        self.assertFalse(result["source_gate_generated_physical_evidence"])
        self.assertFalse(result["source_gate_enrolled_lab_key"])
        self.assertFalse(result["hardware_beta_promoted"])
        self.assertFalse(result["release_ready"])
        verify_gate_receipt(result)

    def test_security_scenario_count_must_equal_category_case_sum(self) -> None:
        path = artifact_path(self.evidence, self.root, "security_results")
        value = json.loads(path.read_text())
        value["scenario_count"] += 1
        path.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.refresh("security_results")
        self.assert_rejected("D8_SECURITY_SCENARIO_COUNT_MISMATCH", self.verify)

    def test_known_limitations_artifact_must_equal_signed_top_level_list(self) -> None:
        path = artifact_path(self.evidence, self.root, "known_limitations")
        value = json.loads(path.read_text())
        value["limitations"][0]["description"] = "forged artifact description"
        path.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.refresh("known_limitations")
        self.assert_rejected(
            "D8_KNOWN_LIMITATIONS_CROSS_ARTIFACT_MISMATCH", self.verify
        )

    def test_known_limitations_artifact_schema_is_closed(self) -> None:
        path = artifact_path(self.evidence, self.root, "known_limitations")
        value = json.loads(path.read_text())
        value["ambient_approval"] = True
        path.write_text(
            json.dumps(value, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        self.refresh("known_limitations")
        self.assert_rejected(
            "D8_KNOWN_LIMITATIONS_ARTIFACT_FIELD_SET_MISMATCH", self.verify
        )

    def test_gate_receipt_tamper_is_rejected(self) -> None:
        result = self.verify()
        tampered = copy.deepcopy(result)
        tampered["security_case_accounting"]["category_case_sum"] += 1
        self.assert_rejected(
            "D8_GATE_RECEIPT_HASH_MISMATCH",
            lambda: verify_gate_receipt(tampered),
        )


if __name__ == "__main__":
    unittest.main()
