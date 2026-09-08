from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_project_truth_explicit_flow_key",
    ROOT / "tools/validate_project_truth.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class ExplicitFlowActionKeyTests(unittest.TestCase):
    def test_inline_explicit_uses_key_is_rejected_fail_closed(self) -> None:
        line = "      - {? uses: actions/checkout@main}"
        candidates = [line for _, line in VALIDATOR.workflow_action_lines(line)]
        self.assertEqual(candidates, [line, "uses:"])
        with self.assertRaises(ValueError):
            VALIDATOR.parse_action_uses(candidates[-1])

    def test_multiline_explicit_uses_key_is_rejected_fail_closed(self) -> None:
        text = "\n".join(
            [
                "      - {",
                "          ? uses: actions/checkout@main",
                "        }",
            ]
        )
        candidates = [line for _, line in VALIDATOR.workflow_action_lines(text)]
        self.assertIn("uses:", candidates)

    def test_explicit_key_outside_flow_map_is_rejected_fail_closed(self) -> None:
        line = "      ? uses: actions/checkout@main"
        candidates = [line for _, line in VALIDATOR.workflow_action_lines(line)]
        self.assertEqual(candidates, [line, "uses:"])
        with self.assertRaises(ValueError):
            VALIDATOR.parse_action_uses(candidates[-1])

    def test_multiline_block_explicit_key_is_rejected_fail_closed(self) -> None:
        text = "\n".join(
            [
                "      - ? uses",
                "        : actions/checkout@main",
            ]
        )
        candidates = [line for _, line in VALIDATOR.workflow_action_lines(text)]
        self.assertIn("uses:", candidates)

    def test_multiline_block_explicit_key_marker_is_rejected_fail_closed(self) -> None:
        text = "\n".join(
            [
                "      - ?",
                "          uses",
                "        : actions/checkout@main",
            ]
        )
        candidates = [line for _, line in VALIDATOR.workflow_action_lines(text)]
        self.assertIn("uses:", candidates)


if __name__ == "__main__":
    unittest.main()
