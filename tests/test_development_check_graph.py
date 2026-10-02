"""The aggregate runs every Python corpus once; focused entry points remain intact."""
from pathlib import Path
import shlex
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


def commands(*targets: str) -> list[list[str]]:
    result = subprocess.run(
        ["make", "--no-print-directory", "-n", *targets], cwd=ROOT,
        check=True, capture_output=True, text=True,
    )
    return [shlex.split(line) for line in result.stdout.splitlines() if line.strip() and not line.startswith("make:")]


class DevelopmentCheckGraphTests(unittest.TestCase):
    def test_aggregate_runs_all_python_discovery_roots_once(self):
        discovery = [cmd for cmd in commands("check") if "unittest" in cmd]
        self.assertEqual(discovery, [
            ["python3", "-m", "unittest", "discover", "-s", root, "-v"]
            for root in ("tests", "tests/d1", "tests/transport")
        ])

    def test_aggregate_keeps_focused_validators_and_rust_feature_matrix(self):
        aggregate = commands("check")
        focused = commands("validate", "truth")
        for cmd in focused:
            if "unittest" not in cmd:
                self.assertEqual(aggregate.count(cmd), 1, cmd)
        for target in ("fmt", "check-rust", "check-rust-features", "clippy",
                       "clippy-features", "test", "test-features", "test-doc", "self-check"):
            for cmd in commands(target):
                self.assertEqual(aggregate.count(cmd), 1, cmd)

    def test_combined_and_parallel_goals_keep_every_command_once(self):
        expected = commands("check")
        for goals in (("validate", "check", "truth"), ("check", "validate", "truth"),
                      ("-j4", "check"), ("-j4", "truth", "check", "validate")):
            self.assertCountEqual(commands(*goals), expected, goals)

    def test_focused_entry_points_still_exercise_their_regressions(self):
        self.assertEqual(sum("unittest" in cmd for cmd in commands("validate")), 5)
        self.assertEqual(sum("unittest" in cmd for cmd in commands("truth")), 1)


if __name__ == "__main__":
    unittest.main()
