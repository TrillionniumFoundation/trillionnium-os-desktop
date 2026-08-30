from __future__ import annotations

import json
from pathlib import Path
import unittest

from tests.test_agent_port_custody_workflow import trigger_paths


ROOT = Path(__file__).resolve().parents[1]
REGISTRY = ROOT / "manifests/gates.v1.json"


class ValidatorInputCoverageTests(unittest.TestCase):
    """Keep permanent D0C gates sensitive to shared validator input changes."""

    def test_servo_evidence_validator_is_a_registered_trigger_input(self) -> None:
        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        expected_gate_ids = {
            "D0C-02": ".github/workflows/agent-transport-reference.yml",
            "D0C-03": ".github/workflows/browser-codec-reference.yml",
            "D0C-05": ".github/workflows/agent-port-custody.yml",
            "D0C-06": ".github/workflows/receipt-journal.yml",
        }
        for gate_id, workflow_name in expected_gate_ids.items():
            gate = next(item for item in registry["gates"] if item["id"] == gate_id)
            self.assertIn(
                "tools/qualify_servo_exact_pin_evidence.py",
                gate["invalidation_paths"],
                f"{gate_id} registry must invalidate on shared validator input changes",
            )
            workflow = (ROOT / workflow_name).read_text(encoding="utf-8")
            for event in ("pull_request", "push"):
                paths = trigger_paths(workflow, event)
                self.assertIn(
                    "tools/qualify_servo_exact_pin_evidence.py",
                    paths,
                    f"{gate_id} {event} trigger omits shared validator input",
                )


if __name__ == "__main__":
    unittest.main()
