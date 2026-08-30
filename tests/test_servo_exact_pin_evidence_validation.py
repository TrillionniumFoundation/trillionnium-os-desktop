from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import qualify_servo_exact_pin_evidence as evidence  # noqa: E402


class ServoQualificationResultValidationTests(unittest.TestCase):
    def valid_result(self) -> dict[str, object]:
        compile_results: dict[str, dict[str, object]] = {}
        for name in evidence.REQUIRED_COMPILE_RESULTS:
            compile_results[name] = {
                "status": "PASS",
                "log_sha256": "a" * 64,
            }
        return {
            "schema": "trillionnium.desktop.servo-qualification-result.v2",
            "status": "PASS_COMPILE_COMPATIBILITY_ONLY",
            "servo": {
                "repository": "https://github.com/servo/servo",
                "commit": evidence.SERVO_PIN,
                "clean_checkout": True,
                "patch_count": 0,
                "source_hashes": {
                    path: "b" * 64 for path in evidence.required_servo_input_paths()
                },
            },
            "compile_results": compile_results,
            "claims": {name: False for name in evidence.REQUIRED_CLAIMS},
            "next_gate": "D0A-02 product-owned headed local-fixture runtime",
        }

    def test_canonical_result_is_accepted(self) -> None:
        evidence.validate_qualification_result(self.valid_result())

    def test_patch_count_boolean_is_rejected(self) -> None:
        result = self.valid_result()
        result["servo"]["patch_count"] = False  # type: ignore[index]
        with self.assertRaises(ValueError):
            evidence.validate_qualification_result(result)

    def test_zero_source_digest_is_rejected(self) -> None:
        result = self.valid_result()
        result["servo"]["source_hashes"]["components/servo/lib.rs"] = (  # type: ignore[index]
            "0" * 64
        )
        with self.assertRaises(ValueError):
            evidence.validate_qualification_result(result)

    def test_compile_names_and_log_digests_are_required(self) -> None:
        result = self.valid_result()
        del result["compile_results"]["official_servoshell"]  # type: ignore[index]
        with self.assertRaises(ValueError):
            evidence.validate_qualification_result(result)

        result = self.valid_result()
        result["compile_results"]["official_servoshell"]["log_sha256"] = (  # type: ignore[index]
            "0" * 64
        )
        with self.assertRaises(ValueError):
            evidence.validate_qualification_result(result)

        result = self.valid_result()
        result["compile_results"]["extra"] = {  # type: ignore[index]
            "status": "PASS",
            "log_sha256": "c" * 64,
        }
        with self.assertRaises(ValueError):
            evidence.validate_qualification_result(result)

    def test_claim_set_and_next_gate_are_canonical(self) -> None:
        result = self.valid_result()
        del result["claims"]["servo_started"]  # type: ignore[index]
        with self.assertRaises(ValueError):
            evidence.validate_qualification_result(result)

        result = self.valid_result()
        result["claims"]["unreviewed_claim"] = False  # type: ignore[index]
        with self.assertRaises(ValueError):
            evidence.validate_qualification_result(result)

        result = self.valid_result()
        result["next_gate"] = "D0A-02 forged claim"  # type: ignore[index]
        with self.assertRaises(ValueError):
            evidence.validate_qualification_result(result)

    def test_qualification_loader_rejects_duplicate_json_keys(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "qualification.json"
            path.write_text('{"status":"PASS","status":"FAIL"}\n', encoding="utf-8")
            with path.open("r", encoding="utf-8") as stream:
                with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
                    evidence.load_json_strict(stream)


if __name__ == "__main__":
    unittest.main()
