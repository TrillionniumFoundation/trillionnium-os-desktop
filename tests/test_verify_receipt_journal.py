from __future__ import annotations

import importlib.util
import json
from pathlib import Path
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


if __name__ == "__main__":
    unittest.main()
