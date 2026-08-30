from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "verify_receipt_journal_under_test",
    ROOT / "tools/verify_receipt_journal.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class ReceiptJournalAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        VALIDATOR.ERRORS.clear()

    def test_contract_requires_exact_false_claim_ceiling(self) -> None:
        contract = json.loads(
            (ROOT / "contracts/receipt-journal.v1.json").read_text(encoding="utf-8")
        )
        VALIDATOR.audit_contract(contract)
        self.assertEqual(VALIDATOR.ERRORS, [])

        malformed = json.loads(json.dumps(contract))
        del malformed["claim_ceiling"]["product_ready"]
        VALIDATOR.ERRORS.clear()
        VALIDATOR.audit_contract(malformed)
        self.assertTrue(any("claim_ceiling keys" in error for error in VALIDATOR.ERRORS))

    def test_receipt_schema_accepts_d6_and_historical_d5_only(self) -> None:
        schema = json.loads(
            (ROOT / "contracts/receipt.v1.schema.json").read_text(encoding="utf-8")
        )
        pattern = schema["properties"]["plan_revision"]["pattern"]
        self.assertEqual(pattern, VALIDATOR.RECEIPT_PLAN_REVISION_PATTERN)
        self.assertRegex("2026-08-29-d6", pattern)
        self.assertRegex("2026-08-28-d5", pattern)
        for unsupported in ("2026-08-28-d6", "2026-08-29-d5", "2026-08-27-d4"):
            self.assertIsNone(re.fullmatch(pattern, unsupported))

    def test_receipt_schema_digest_binding_is_current(self) -> None:
        contract = json.loads(
            (ROOT / "contracts/receipt-journal.v1.json").read_text(encoding="utf-8")
        )
        binding = contract["receipt_envelope_schema"]
        self.assertEqual(binding["path"], VALIDATOR.RECEIPT_SCHEMA_RELATIVE)
        self.assertEqual(binding["sha256"], VALIDATOR.RECEIPT_SCHEMA_SHA256)
        VALIDATOR.ERRORS.clear()
        VALIDATOR.audit_contract(contract)
        self.assertEqual(VALIDATOR.ERRORS, [])

    def test_contract_binds_canonical_and_forensic_exports(self) -> None:
        contract = json.loads(
            (ROOT / "contracts/receipt-journal.v1.json").read_text(encoding="utf-8")
        )
        exports = contract["exports"]
        self.assertEqual(exports["public_receipt_envelope"], "export_redacted_jsonl")
        self.assertEqual(
            exports["public_receipt_envelope_schema"],
            "contracts/receipt.v1.schema.json",
        )
        self.assertEqual(
            exports["forensic_lifecycle_export"], "export_journal_redacted_jsonl"
        )
        VALIDATOR.ERRORS.clear()
        malformed = json.loads(json.dumps(contract))
        malformed["exports"]["public_receipt_envelope"] = "export_journal_redacted_jsonl"
        VALIDATOR.audit_contract(malformed)
        self.assertTrue(any("public receipt export" in error for error in VALIDATOR.ERRORS))

    def test_structural_chain_api_and_regressions_are_required(self) -> None:
        source = (ROOT / "crates/hepta-session-core/src/receipt_journal.rs").read_text(
            encoding="utf-8"
        )
        public_api = (ROOT / "crates/hepta-session-core/src/lib.rs").read_text(
            encoding="utf-8"
        )
        VALIDATOR.audit_source(source, public_api)
        self.assertEqual(VALIDATOR.ERRORS, [])

        VALIDATOR.ERRORS.clear()
        VALIDATOR.audit_source(source.replace("pub fn inspect_chain", "// pub fn inspect_chain", 1), public_api)
        self.assertTrue(any("inspect_chain API" in error for error in VALIDATOR.ERRORS))

    def test_comments_and_literals_cannot_satisfy_forbidden_authority_check(self) -> None:
        masked = VALIDATOR.mask_rust_non_code(
            '// TcpListener WebDriver std::process::Command\n'
            'let text = "TcpListener WebDriver";\n'
            'fn safe() {}\n'
        )
        self.assertNotIn("TcpListener", masked)
        self.assertNotIn("WebDriver", masked)

    def test_d0c06_generated_artifact_is_historical_and_fail_closed(self) -> None:
        artifact = json.loads(
            (ROOT / VALIDATOR.D0C06_GENERATED_EVIDENCE_RELATIVE).read_text(
                encoding="utf-8"
            )
        )
        VALIDATOR.audit_generated_evidence(artifact)
        self.assertEqual(VALIDATOR.ERRORS, [])
        self.assertEqual(
            artifact["validated_source_head"], VALIDATOR.D0C06_HISTORICAL_SOURCE_HEAD
        )
        self.assertEqual(
            artifact["validated_tree_sha"], VALIDATOR.D0C06_HISTORICAL_TREE_SHA
        )
        self.assertEqual(
            artifact["evidence_lifecycle"], VALIDATOR.D0C06_EVIDENCE_LIFECYCLE
        )
        self.assertIs(artifact["merge_ready"], False)
        self.assertEqual(
            set(artifact["claim_ceiling"]), VALIDATOR.EXPECTED_CLAIM_CEILING
        )
        self.assertTrue(all(value is False for value in artifact["claim_ceiling"].values()))

    def test_d0c06_generated_artifact_rejects_claim_or_hash_drift(self) -> None:
        artifact = json.loads(
            (ROOT / VALIDATOR.D0C06_GENERATED_EVIDENCE_RELATIVE).read_text(
                encoding="utf-8"
            )
        )
        artifact["claim_ceiling"]["product_ready"] = True
        artifact["input_hashes"]["Cargo.lock"] = "0" * 64
        VALIDATOR.audit_generated_evidence(artifact)
        self.assertTrue(
            any("claim_ceiling.product_ready" in error for error in VALIDATOR.ERRORS)
        )
        self.assertTrue(
            any("input_hashes.Cargo.lock" in error for error in VALIDATOR.ERRORS)
        )


if __name__ == "__main__":
    unittest.main()
