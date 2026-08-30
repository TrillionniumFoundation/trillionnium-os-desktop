from __future__ import annotations

import json
from pathlib import Path
import unittest

from tests.test_agent_port_custody_workflow import trigger_paths


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/receipt-journal.yml"


class ReceiptJournalWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow_text = WORKFLOW.read_text(encoding="utf-8")
        registry = json.loads(
            (ROOT / "manifests/gates.v1.json").read_text(encoding="utf-8")
        )
        self.registry_paths = set(
            next(gate for gate in registry["gates"] if gate["id"] == "D0C-06")[
                "invalidation_paths"
            ]
        )

    def test_registry_and_workflow_triggers_are_kept_in_lockstep(self) -> None:
        """Every registered receipt input must invalidate both permanent runs."""

        for event in ("pull_request", "push"):
            paths = trigger_paths(self.workflow_text, event)
            self.assertTrue(paths, f"{event} paths must be discoverable")
            self.assertEqual(
                paths,
                self.registry_paths,
                f"D0C-06 {event} trigger drift: "
                f"missing={sorted(self.registry_paths - paths)}, "
                f"unregistered={sorted(paths - self.registry_paths)}",
            )

    def test_validator_and_toolchain_inputs_are_registered(self) -> None:
        required = {
            "rust-toolchain.toml",
            "manifests/cargo-external-allowlist.json",
            "manifests/rust-toolchain.lock.json",
            "manifests/repository-state.json",
            "tools/validate_repository.py",
            "tools/validate_project_truth.py",
        }
        self.assertTrue(required <= self.registry_paths)

    def test_receipt_envelope_schema_is_a_registered_input(self) -> None:
        self.assertIn("contracts/receipt.v1.schema.json", self.registry_paths)
        for event in ("pull_request", "push"):
            self.assertIn("contracts/receipt.v1.schema.json", trigger_paths(self.workflow_text, event))

    def test_historical_machine_evidence_is_a_registered_input(self) -> None:
        path = "docs/evidence/generated/d0c06-rust193-host-result.json"
        self.assertIn(path, self.registry_paths)
        for event in ("pull_request", "push"):
            self.assertIn(path, trigger_paths(self.workflow_text, event))


if __name__ == "__main__":
    unittest.main()
