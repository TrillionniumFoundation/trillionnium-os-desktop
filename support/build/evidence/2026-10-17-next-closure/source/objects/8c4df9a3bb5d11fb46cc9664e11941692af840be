"""Fail-closed evidence and isolation checks for the single A02 acceptance entry."""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import run_acceptance as acceptance


class AcceptanceRunnerTests(unittest.TestCase):
    def test_cold_mutation_batch_can_exceed_one_cargo_command_budget(self):
        # A virtual 75-second batch consists of individually bounded commands.
        # Mock the process boundary to exercise the timeout without sleeping.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "mutations.json"

            def cold_batch(argv, *, timeout, **kwargs):
                if timeout < 75:
                    raise subprocess.TimeoutExpired(argv, timeout)
                self.assertEqual(argv[-2:], ["--timeout", "60"])
                evidence.write_text(json.dumps({"success": True, "expected_mutants": 12,
                                                "mutants_killed": 12}))
                return subprocess.CompletedProcess(argv, 0, "complete batch", "")

            with mock.patch.object(acceptance.subprocess, "run", side_effect=cold_batch):
                old_budget = acceptance.run_command(["batch"], root, {}, 60)
                result = acceptance.run_compiled_mutations(
                    sys.executable, "cargo", "nightly-2026-07-21", root, {}, 60, 900, evidence)
            self.assertTrue(old_budget["timed_out"])
            self.assertFalse(old_budget["passed"])
            self.assertTrue(result["passed"])
            self.assertEqual(result["timeout_seconds"], 900)
            self.assertEqual(result["cargo_timeout_seconds"], 60)
            self.assertEqual(result["mutants_killed"], 12)

    def test_mutation_batch_timeout_cannot_pass_with_a_success_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "mutations.json"
            evidence.write_text(json.dumps({"success": True, "expected_mutants": 12,
                                            "mutants_killed": 12}))
            with mock.patch.object(acceptance.subprocess, "run",
                                   side_effect=subprocess.TimeoutExpired("batch", 900)):
                result = acceptance.run_compiled_mutations(
                    sys.executable, "cargo", "nightly-2026-07-21", root, {}, 60, 900, evidence)
            self.assertTrue(result["timed_out"])
            self.assertFalse(result["passed"])

    def test_mutation_batch_budget_is_finite_and_at_least_one_command(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "evidence"
            for invalid in ("59", "3601", "nan", "inf", "0", "-1"):
                with self.subTest(timeout=invalid), contextlib.redirect_stderr(io.StringIO()):
                    with self.assertRaises(SystemExit) as raised:
                        acceptance.main(["--output-dir", str(output), "--mutation-timeout", invalid])
                    self.assertEqual(raised.exception.code, 2)
                self.assertFalse(output.exists())

    def test_python_denominator_rejects_skips_and_missing_discovered_tests(self):
        output = "test_a (sample.Case.test_a) ... ok\n\nRan 1 test in 0.001s\n\nOK\n"
        self.assertTrue(acceptance.python_outcome(output, ["sample.Case.test_a"])["complete"])
        self.assertFalse(acceptance.python_outcome(output, ["sample.Case.test_a", "sample.Case.test_b"])["complete"])
        skipped = output.replace("... ok", "... skipped 'unavailable'").replace("\nOK\n", "\nOK (skipped=1)\n")
        self.assertFalse(acceptance.python_outcome(skipped, ["sample.Case.test_a"])["complete"])

    def test_rust_denominator_rejects_filtered_and_ignored_execution(self):
        output = "test test_a ... ok\ntest result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out;\n"
        self.assertTrue(acceptance.rust_outcome(output, ["test_a"])["complete"])
        self.assertFalse(acceptance.rust_outcome(output.replace("0 filtered", "1 filtered"), ["test_a"])["complete"])
        self.assertFalse(acceptance.rust_outcome(output.replace("test_a ... ok", "test_a ... ignored"), ["test_a"])["complete"])
        self.assertFalse(acceptance.rust_outcome(output, ["test_a", "missing"])["complete"])

    def test_snapshot_refuses_symlink_escape_and_does_not_follow_it(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            for relative in acceptance.SOURCE_ROOTS:
                (repo / relative).mkdir(parents=True)
            (repo / "README.md").write_bytes(b"")
            (repo / "support").mkdir()
            (repo / "support/upstream-lock.json").write_text('{"kernel":{"toolchain":"nightly-2026-07-21"}}')
            (repo / "tests/abi/run_example.py").write_text("print('execution input')")
            (repo / "tests/golden/example.json").write_text("{}")
            (repo / "tests/abi/A02_HISTORY.md").write_text("historical report")
            (repo / "tests/abi/results").mkdir()
            (repo / "tests/abi/results/history.json").write_text("historical evidence")
            inputs = acceptance.selected_inputs(repo)
            self.assertIn("tests/abi/run_example.py", inputs)
            self.assertIn("tests/golden/example.json", inputs)
            self.assertNotIn("tests/abi/A02_HISTORY.md", inputs)
            self.assertNotIn("tests/abi/results/history.json", inputs)
            external = root / "external"
            external.write_text("must stay external")
            # Even excluded historical paths must not hide a symlink escape.
            (repo / "tests/abi/results/escape.json").symlink_to(external)
            with self.assertRaisesRegex(ValueError, "nonregular input"):
                acceptance.selected_inputs(repo)
            self.assertEqual(external.read_text(), "must stay external")

    def test_existing_output_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "evidence"
            output.mkdir()
            report = output / "report.json"
            report.write_text("existing evidence")
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(acceptance.main(["--output-dir", str(output)]), 1)
            self.assertEqual(report.read_text(), "existing evidence")

    def test_missing_tool_writes_failure_report_with_unchanged_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            for relative in acceptance.SOURCE_ROOTS:
                (repo / relative).mkdir(parents=True)
            (repo / "libs/os-abi/Cargo.toml").write_text("[package]\nname='fixture'\nversion='0.0.0'\n")
            (repo / "README.md").write_bytes(b"")
            (repo / "support").mkdir()
            (repo / "support/upstream-lock.json").write_text('{"kernel":{"toolchain":"nightly-2026-07-21"}}')
            output = root / "evidence"
            failed_command = acceptance.run_command(
                [str(root / "missing-rustup"), "--version"], repo, os.environ.copy(), 1)
            self.assertFalse(failed_command["passed"])
            self.assertIsNone(failed_command["returncode"])
            self.assertEqual(failed_command["argv"], [str(root / "missing-rustup"), "--version"])
            self.assertEqual(failed_command["cwd"], str(repo))
            self.assertIn("error", failed_command)
            with contextlib.redirect_stdout(io.StringIO()):
                code = acceptance.main(["--repo-root", str(repo), "--output-dir", str(output),
                                        "--rustup", str(root / "missing-rustup")])
            report = json.loads((output / "report.json").read_text())
            self.assertEqual(code, 1)
            self.assertFalse(report["success"])
            self.assertTrue(report["original_inputs_unchanged"])
            self.assertEqual(report["not_executed"], list(acceptance.CHECK_NAMES))
            self.assertIn("no installation or fallback", report["errors"][0])
            self.assertFalse((repo / "libs/os-abi/Cargo.lock").exists())

    def test_toolchain_pin_is_required_even_with_an_explicit_override(self):
        inputs = {"support/upstream-lock.json": b'{"kernel":{"toolchain":"nightly-2026-07-21"}}'}
        self.assertEqual(acceptance.selected_toolchain(inputs, None), "nightly-2026-07-21")
        self.assertEqual(acceptance.selected_toolchain(inputs, "1.95.0"), "1.95.0")
        with self.assertRaises(KeyError):
            acceptance.selected_toolchain({"support/upstream-lock.json": b"{}"}, "1.95.0")


if __name__ == "__main__":
    unittest.main(verbosity=2)
