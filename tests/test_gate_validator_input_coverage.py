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

    def test_stale_evidence_and_plan_inputs_invalidate_permanent_gates(self) -> None:
        """Every tracked stale artifact and policy doc must retrigger its gate."""

        registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
        gates = {entry["id"]: entry for entry in registry["gates"]}
        expected = {
            "D0A-01": (
                ".github/workflows/servo-exact-pin.yml",
                "docs/evidence/generated/d0a01-*.json",
                "docs/plan/**",
            ),
            "D0C-02": (
                ".github/workflows/agent-transport-reference.yml",
                "docs/evidence/generated/d0c02-rust193-host-result.json",
                "docs/evidence/2026-08-28-d0c02-authenticated-uds.md",
                "docs/plan/**",
            ),
            "D0C-03": (
                ".github/workflows/browser-codec-reference.yml",
                "docs/evidence/2026-08-28-d0c03-rust-product-codec-source.md",
                "docs/plan/**",
            ),
            "D0C-05": (
                ".github/workflows/agent-port-custody.yml",
                "docs/evidence/generated/d0c05-rust193-host-result.json",
            ),
            "D0C-06": (
                ".github/workflows/receipt-journal.yml",
                "docs/plan/**",
            ),
        }
        for gate_id, values in expected.items():
            workflow_name, *inputs = values
            gate_paths = set(gates[gate_id]["invalidation_paths"])
            workflow = (ROOT / workflow_name).read_text(encoding="utf-8")
            for event in ("pull_request", "push"):
                trigger = trigger_paths(workflow, event)
                for path in inputs:
                    with self.subTest(gate_id=gate_id, event=event, path=path):
                        self.assertIn(path, gate_paths)
                        self.assertIn(path, trigger)


if __name__ == "__main__":
    unittest.main()
