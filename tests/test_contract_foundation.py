from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ContractFoundationValidationTest(unittest.TestCase):
    def test_validator_passes_repository_state(self) -> None:
        completed = subprocess.run(
            [sys.executable, "tools/validate_contract_foundation.py"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)

    def test_revision_policy_is_machine_readable(self) -> None:
        registry = json.loads(
            (ROOT / "contracts/contract-core-constraints.v1.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(
            registry["revision_clock"]["overflow_policy"],
            "error_before_any_state_change",
        )
        self.assertEqual(
            registry["revision_clock"]["initial"],
            {
                "document_generation": 1,
                "mutation_epoch": 0,
                "semantic_snapshot_revision": 0,
                "session_generation": 1,
            },
        )


if __name__ == "__main__":
    unittest.main()
