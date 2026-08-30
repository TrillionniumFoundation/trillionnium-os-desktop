from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/agent-port-custody.yml"


def trigger_paths(text: str, event: str) -> set[str]:
    """Extract one event's YAML ``paths`` list without a YAML dependency.

    The workflow is deliberately a small, static trigger declaration.  Keeping
    this parser indentation-aware avoids accidentally collecting branch names
    or path entries from the following event while still allowing comments and
    quoted scalars in future edits.
    """

    lines = text.splitlines()
    in_event = False
    in_paths = False
    result: set[str] = set()
    for line in lines:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))
        if not in_event:
            if line == f"  {event}:":
                in_event = True
            continue
        if indent == 2 and stripped and not stripped.startswith("#"):
            break
        if not in_paths:
            if indent == 4 and stripped == "paths:":
                in_paths = True
            continue
        if indent <= 4 and stripped and not stripped.startswith("-"):
            break
        if indent < 6 or not stripped.startswith("- "):
            continue
        value = stripped[2:].strip()
        if " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if value:
            result.add(value)
    return result



class AgentPortCustodyWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow_text = WORKFLOW.read_text(encoding="utf-8")
        registry = json.loads(
            (ROOT / "manifests/gates.v1.json").read_text(encoding="utf-8")
        )
        self.registry_paths = set(
            next(gate for gate in registry["gates"] if gate["id"] == "D0C-05")[
                "invalidation_paths"
            ]
        )

    def test_registry_inputs_trigger_both_pull_request_and_main_push(self) -> None:
        pull_request = trigger_paths(self.workflow_text, "pull_request")
        push = trigger_paths(self.workflow_text, "push")
        self.assertTrue(pull_request, "pull_request paths must be discoverable")
        self.assertTrue(push, "push paths must be discoverable")
        self.assertTrue(
            self.registry_paths <= pull_request,
            f"D0C-05 registry paths missing from PR trigger: "
            f"{sorted(self.registry_paths - pull_request)}",
        )
        self.assertTrue(
            self.registry_paths <= push,
            f"D0C-05 registry paths missing from push trigger: "
            f"{sorted(self.registry_paths - push)}",
        )

    def test_validator_and_toolchain_inputs_remain_registered(self) -> None:
        required = {
            "rust-toolchain.toml",
            "manifests/cargo-external-allowlist.json",
            "manifests/rust-toolchain.lock.json",
            "tools/validate_repository.py",
            "tools/validate_project_truth.py",
            "tools/validate_d3_development_profile.py",
            "tools/verify_systemd_socket_custody.py",
            "contracts/browser-actor.v1.json",
            "tests/test_systemd_custody_validator.py",
        }
        self.assertTrue(required <= self.registry_paths)

    def test_python_regression_is_executed_by_the_gate(self) -> None:
        self.assertIn(
            "tests/test_systemd_custody_validator.py",
            trigger_paths(self.workflow_text, "pull_request"),
        )
        self.assertIn(
            "tests/test_systemd_custody_validator.py",
            trigger_paths(self.workflow_text, "push"),
        )
        self.assertIn(
            "python3 -m unittest tests.test_systemd_custody_validator -v",
            self.workflow_text,
        )


if __name__ == "__main__":
    unittest.main()
