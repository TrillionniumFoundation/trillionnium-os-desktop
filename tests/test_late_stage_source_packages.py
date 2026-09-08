from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_late_stage_source_packages_under_test",
    ROOT / "tools/validate_late_stage_source_packages.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class LateStageSourceInventoryTests(unittest.TestCase):
    def test_complete_d4_through_d9_source_inventory(self) -> None:
        result = VALIDATOR.validate()
        self.assertEqual(result["status"], "PASS_SOURCE_INVENTORY")
        self.assertEqual(result["packages"], ["D4-01", "D5-01", "D6-01", "D7-01", "D8-01", "D9-01"])
        self.assertTrue(result["source_packages_present"])
        self.assertGreaterEqual(len(result["authority_hardening_source_checks"]), 12)
        self.assertIn(
            "write_ahead_receipt_sink", result["authority_hardening_source_checks"]
        )
        self.assertFalse(result["runtime_integration_claimed"])
        self.assertFalse(result["physical_evidence_claimed"])
        self.assertFalse(result["release_promotion_claimed"])
        self.assertFalse(result["promotion_authoritative"])

    def test_mutable_action_reference_is_rejected(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "unsafe.yml"
            path.write_text(
                "permissions:\n  contents: read\nsteps:\n  - uses: actions/checkout@main\n    with:\n      persist-credentials: false\n",
                encoding="utf-8",
            )
            with self.assertRaises(VALIDATOR.ValidationError):
                VALIDATOR.validate_workflow(path)


if __name__ == "__main__":
    unittest.main()
