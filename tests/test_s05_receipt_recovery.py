from __future__ import annotations

import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReceiptRecoverySliceTests(unittest.TestCase):
    def test_contract_never_claims_execution_or_automatic_replay(self) -> None:
        contract = json.loads((ROOT / "contracts/receipt-journal.v1.json").read_text())
        self.assertTrue(all(value is False for value in contract["claim_ceiling"].values()))
        self.assertEqual(
            contract["effect_recovery"]["potential_external_effect"],
            "never_automatic",
        )
        self.assertFalse(
            contract["effect_recovery"]["journal_executes_or_replays_operations"]
        )

    def test_managed_store_requires_atomic_durable_publication(self) -> None:
        source = (
            ROOT / "crates/hepta-session-core/src/receipt_journal/managed.rs"
        ).read_text()
        for marker in (
            "sync_all",
            "rename",
            "verify_current",
            "stabilize_open",
            "check_live_state",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("let _ = next.file.sync_all()", source)

    def test_chain_recovery_and_process_corpus_are_present(self) -> None:
        required = (
            "crates/hepta-session-core/src/receipt_journal/chain.rs",
            "crates/hepta-session-core/src/receipt_journal/persistence_tests.rs",
            "crates/hepta-session-core/tests/journal_chain_process_recovery.rs",
            "crates/hepta-session-core/tests/journal_persistence_process.rs",
        )
        for relative in required:
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_legacy_migration_is_one_way_and_bounded(self) -> None:
        contract = json.loads(
            (ROOT / "contracts/legacy-receipt-migration.v1.json").read_text()
        )
        encoded = json.dumps(contract, sort_keys=True)
        for marker in (
            "SOURCE_CANDIDATE",
            "migration",
            "reject_preserve_no_resume",
        ):
            self.assertIn(marker.lower(), encoded.lower())
        self.assertNotIn("automatic_external_effect_replay", encoded)

    def test_receipt_schema_rejects_unbounded_free_form_authority(self) -> None:
        schema = json.loads((ROOT / "contracts/receipt.v1.schema.json").read_text())
        encoded = json.dumps(schema, sort_keys=True)
        self.assertIn("additionalProperties", encoded)
        self.assertIn("maxLength", encoded)
        self.assertNotIn("shell_command", encoded)


if __name__ == "__main__":
    unittest.main()
