"""Executable regression checks for the concrete September 12 documentation bugs."""
from __future__ import annotations

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ANNEXES = (
    "PRODUCT_ARCHITECTURE.md",
    "CONTRACT_SECURITY_TESTING.md",
    "WORK_PACKAGES_AND_GATES.md",
)


def validate_annex(text: str, active_plan: str) -> bool:
    header = text.split("\n## ", 1)[0]
    return (
        header.count(f"**Applicable plan:** `{active_plan}`") == 1
        and header.count("**Source revision:** `2026-08-28-d5`") == 1
        and header.count("**Status:** inherited requirements; subordinate to d6; not current implementation status") == 1
        and "ANNEX_APPLICABILITY.md" in header
        and "normative component of the active canonical plan" not in header
    )


class DevelopmentDocumentationTests(unittest.TestCase):
    def test_all_inherited_annex_headers_match_active_plan(self) -> None:
        plan = json.loads((ROOT / "docs/MANIFEST.json").read_text())["active_plan_revision"]
        for name in ANNEXES:
            with self.subTest(annex=name):
                self.assertTrue(validate_annex((ROOT / "docs/plan" / name).read_text(), plan))

    def test_stale_or_duplicate_applicability_is_rejected(self) -> None:
        original = (ROOT / "docs/plan/PRODUCT_ARCHITECTURE.md").read_text()
        for mutated in (
            original.replace("**Applicable plan:** `2026-08-29-d6`", "**Applicable plan:** `2026-08-28-d5`"),
            original.replace("**Applicable plan:**", "**Applicable plan:** `2026-08-29-d6`\n**Applicable plan:**", 1),
            original.replace("ANNEX_APPLICABILITY.md", "missing.md"),
        ):
            with self.subTest(header=mutated[:180]):
                self.assertFalse(validate_annex(mutated, "2026-08-29-d6"))

    def test_d3_is_not_documented_as_production_activation(self) -> None:
        text = (ROOT / "docs/plan/CONTRACT_SECURITY_TESTING.md").read_text()
        self.assertNotIn("The D3 production transport", text)
        self.assertIn("D3 permits explicitly selected development-profile activation only.", text)

    def test_receipt_operations_match_machine_permission_contract(self) -> None:
        contract = json.loads((ROOT / "contracts/receipt-journal.v1.json").read_text())["managed_store"]
        self.assertEqual(contract["directory_mode"], "0700")
        self.assertEqual(contract["file_mode"], "0600")
        text = (ROOT / "crates/hepta-session-core/README.md").read_text()
        expected = f'Receipt store permissions: directories `{contract["directory_mode"]}`; files `{contract["file_mode"]}`.'
        self.assertEqual(text.count(expected), 1)
        self.assertNotIn("private 0600 journal directory", text)

    def test_private_directory_and_file_example_is_operable(self) -> None:
        contract = json.loads((ROOT / "contracts/receipt-journal.v1.json").read_text())["managed_store"]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "new-private-store"
            root.mkdir(mode=int(contract["directory_mode"], 8))
            self.assertEqual(stat.S_IMODE(root.stat().st_mode), 0o700)
            fd = os.open(root / "example", os.O_CREAT | os.O_EXCL | os.O_WRONLY, int(contract["file_mode"], 8))
            with os.fdopen(fd, "wb") as stream:
                stream.write(b"documentation permission example; not a journal\n")
            self.assertEqual(stat.S_IMODE((root / "example").stat().st_mode), 0o600)
            self.assertTrue((root / "example").read_bytes())


if __name__ == "__main__":
    unittest.main()
