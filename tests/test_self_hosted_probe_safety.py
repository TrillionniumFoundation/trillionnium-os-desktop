"""Static hostile checks for the tokenless self-hosted availability probes."""
from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = (
    ROOT / ".github/workflows/self-hosted-desktop-availability.yml",
    ROOT / ".github/workflows/self-hosted-fleet-availability.yml",
)


def run_blocks(text: str) -> list[str]:
    lines = text.splitlines()
    blocks: list[str] = []
    index = 0
    while index < len(lines):
        match = re.match(r"^(\s*)run:\s*\|\s*$", lines[index])
        if not match:
            index += 1
            continue
        indent = len(match.group(1))
        index += 1
        body: list[str] = []
        while index < len(lines):
            line = lines[index]
            if line.strip() and len(line) - len(line.lstrip()) <= indent:
                break
            body.append(line)
            index += 1
        blocks.append("\n".join(body))
    return blocks


class SelfHostedProbeSafetyTests(unittest.TestCase):
    def test_input_is_step_environment_data_not_generated_shell_source(self) -> None:
        for path in WORKFLOWS:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertIn("PROBE_REASON: ${{ inputs.reason }}", text)
                self.assertIn('test "${#PROBE_REASON}" -le 512', text)
                self.assertIn('"$PROBE_REASON"', text)
                self.assertIn("%q", text)
                for block in run_blocks(text):
                    self.assertNotIn("${{", block)
                    self.assertNotIn("eval ", block)
                    self.assertNotIn("bash -c", block)
                    self.assertNotIn("sh -c", block)
                    self.assertNotRegex(block, r"(^|\n)\s*(source|\.)\s+")

    def test_probe_has_no_token_checkout_mutation_or_device_enumeration(self) -> None:
        for path in WORKFLOWS:
            text = path.read_text(encoding="utf-8")
            lowered = text.lower()
            with self.subTest(path=path.name):
                self.assertIn("permissions: {}", text)
                self.assertNotIn("actions/checkout", lowered)
                self.assertNotIn("persist-credentials", lowered)
                self.assertNotIn("github.token", lowered)
                self.assertNotIn("secrets.", lowered)
                self.assertNotRegex(lowered, r"\badb\b")
                self.assertNotRegex(lowered, r"\b(curl|wget)\b")
                self.assertNotIn("upload-artifact", lowered)
                self.assertNotIn("git push", lowered)

    def test_scheduler_routes_each_probe_to_a_dedicated_runner_label(self) -> None:
        expected = {
            "self-hosted-desktop-availability.yml": (
                "runs-on: [self-hosted, linux, x64, desktop]",
            ),
            "self-hosted-fleet-availability.yml": (
                "runs-on: [self-hosted, linux, x64, rog]",
                "runs-on: [self-hosted, linux, x64, pocket4]",
            ),
        }
        generic_only = "runs-on: [self-hosted, linux, x64]"
        for path in WORKFLOWS:
            text = path.read_text(encoding="utf-8")
            with self.subTest(path=path.name):
                self.assertNotIn(generic_only, text)
                for route in expected[path.name]:
                    self.assertIn(route, text)

    def test_event_ref_and_exact_runner_checks_precede_reason_logging(self) -> None:
        expected = {
            "self-hosted-desktop-availability.yml": ("desktop",),
            "self-hosted-fleet-availability.yml": ("rog", "pocket4"),
        }
        for path in WORKFLOWS:
            text = path.read_text(encoding="utf-8")
            for runner in expected[path.name]:
                with self.subTest(path=path.name, runner=runner):
                    runner_index = text.index(f'test "$RUNNER_NAME" = {runner}')
                    event_index = text.rfind(
                        'test "$GITHUB_EVENT_NAME" = workflow_dispatch',
                        0,
                        runner_index,
                    )
                    ref_index = text.rfind(
                        'test "$GITHUB_REF" = refs/heads/main',
                        0,
                        runner_index,
                    )
                    reason_index = text.index("reason=%q", runner_index)
                    self.assertGreaterEqual(event_index, 0)
                    self.assertGreaterEqual(ref_index, 0)
                    self.assertLess(event_index, reason_index)
                    self.assertLess(ref_index, reason_index)
                    self.assertLess(runner_index, reason_index)


if __name__ == "__main__":
    unittest.main()
