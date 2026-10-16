"""Fast subprocess-boundary checks for mutation toolchain evidence.

No Cargo or Rust compiler is executed. The production runner still constructs
its environments, probes identities, parses test output and decides whether
the baseline/mutation evidence is usable.
"""

import contextlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import run_rust_mutations as mutations


class MutationToolchainTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="hos2-toolchain-test-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        # Existing executable paths keep identity path checks real; subprocess
        # itself is always mocked, so Python is never asked to act as Cargo.
        self.cargo = sys.executable
        self.env = os.environ.copy()
        self.env.update(RUSTUP_TOOLCHAIN="nightly-2026-07-21", RUSTC=sys.executable)
        self.calls = []
        self.rustc_calls = 0
        count, required = mutations.SUITES["mutation_kill"]
        names = list(required) + [f"other_{index}" for index in range(count - len(required))]
        self.passing_output = "".join(f"test {name} ... ok\n" for name in names)
        self.passing_output += (
            f"test result: ok. {count} passed; 0 failed; 0 ignored; "
            "0 measured; 0 filtered out;\n"
        )

    def fake_subprocess(self, failure=None, selected=True):
        def run(command, **kwargs):
            env = kwargs["env"]
            cwd = kwargs["cwd"]
            self.calls.append((command, env.copy(), cwd))
            self.assertEqual(env.get("RUSTUP_TOOLCHAIN"),
                             "nightly-2026-07-21" if selected else None)
            self.assertEqual(env["RUSTC"], sys.executable)
            self.assertEqual(env["CARGO_TARGET_DIR"], str(cwd / "target"))
            self.assertEqual(env["CARGO_TERM_COLOR"], "never")
            self.assertEqual(env["CARGO_NET_OFFLINE"], "true")
            self.assertTrue(kwargs["capture_output"])
            self.assertTrue(kwargs["text"])
            self.assertFalse(kwargs["check"])
            self.assertGreater(kwargs["timeout"], 0)
            self.assertEqual(command[0], sys.executable)
            if command[1] == "--version":
                self.assertEqual(command, [self.cargo, "--version"])
                return subprocess.CompletedProcess(command, 0, "cargo pinned", "")
            if command[1] == "-vV":
                self.assertEqual(command, [sys.executable, "-vV"])
                self.rustc_calls += 1
                if self.rustc_calls > 1 and failure == "missing":
                    raise FileNotFoundError("missing compiler")
                if self.rustc_calls > 1 and failure == "timeout":
                    raise subprocess.TimeoutExpired(command, kwargs["timeout"])
                if failure == "invalid_reference" and self.rustc_calls == 1:
                    return subprocess.CompletedProcess(command, 0, "", "")
                drift_at = 2 if failure == "before_compile_drift" else 3
                drifted = failure in ("before_compile_drift", "before_test_drift")
                version = "rustc changed" if drifted and self.rustc_calls >= drift_at else (
                    "rustc pinned\nrelease: 1.99.0-nightly"
                )
                return subprocess.CompletedProcess(command, 0, version, "")
            self.assertEqual(command[:7], [self.cargo, "test", "--offline", "--color",
                                          "never", "--test", "mutation_kill"])
            self.assertIn(command[7:], (["--no-run"], ["--", "--test-threads=1"]))
            return subprocess.CompletedProcess(
                command, 0, "" if "--no-run" in command else self.passing_output, ""
            )
        return run

    def rejected_main(self, failure):
        repo = self.root / "repo"
        for relative in mutations.INPUTS:
            destination = repo / "libs/os-abi" / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"// fixture; never compiled\n")
        for relative in mutations.FIXTURES:
            destination = repo / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(b"{}\n")
        output = io.StringIO()
        with patch.dict(os.environ, self.env, clear=True), patch.object(
            mutations.subprocess, "run", self.fake_subprocess(failure)
        ), contextlib.redirect_stdout(output):
            code = mutations.main(["--repo-root", str(repo), "--cargo", self.cargo,
                                   "--toolchain", "nightly-2026-07-21", "--timeout", "1"])
        report = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertFalse(report["success"])
        self.assertEqual(report["mutants_killed"], 0)
        self.assertEqual(report["mutants"], [])
        self.assertTrue(report["errors"])
        if failure != "invalid_reference":
            for key in ("baseline", "baseline_semantic_edges", "baseline_profile_boundaries"):
                baseline = report[key]
                self.assertFalse(baseline["compiled"])
                self.assertFalse(baseline["passed"])
                self.assertFalse(baseline["toolchain_matches_reference"])
                self.assertIsNone(baseline["test"])
                self.assertIsNone(baseline["tests"])
        return report

    def test_fixed_environment_reaches_probes_compilation_and_test(self):
        reference_cwd = self.root / "reference"
        reference_cwd.mkdir()
        with patch.object(mutations.subprocess, "run", self.fake_subprocess()):
            reference = mutations.toolchain_identity(
                self.cargo, reference_cwd, 1, mutations.suite_environment(self.env, reference_cwd)
            )
            with patch.dict(os.environ, {"RUSTUP_TOOLCHAIN": "changed-after-freeze"}):
                result = mutations.run_suite(
                    self.root / "suite", {"src/lib.rs": b""}, {}, "// source",
                    self.cargo, 1, "mutation_kill", self.env, reference,
                )
        self.assertTrue(mutations.baseline_passed(result))
        self.assertTrue(result["toolchain_matches_reference"])
        self.assertEqual(result["test_toolchain_identity"]["effective_environment"],
                         {"RUSTUP_TOOLCHAIN": "nightly-2026-07-21", "RUSTC": sys.executable})
        self.assertEqual(len(self.calls), 8)
        suite_cwd = self.root / "suite/libs/os-abi"
        self.assertTrue(all(cwd == suite_cwd for _, _, cwd in self.calls[2:]))
        self.assertTrue(all(env == self.calls[2][1] for _, env, _ in self.calls[2:]))

    def test_missing_compiler_never_counts_as_kill(self):
        report = self.rejected_main("missing")
        self.assertIn("missing compiler", report["baseline"]["toolchain_identity"]["rustc"]["error"])
        self.assertIsNone(report["baseline"]["compilation"])
        self.assertFalse(any(command[1] == "test" for command, _, _ in self.calls))

    def test_identity_timeout_never_counts_as_kill(self):
        report = self.rejected_main("timeout")
        self.assertTrue(report["baseline"]["toolchain_identity"]["rustc"]["timed_out"])
        self.assertIsNone(report["baseline"]["compilation"])
        self.assertFalse(any(command[1] == "test" for command, _, _ in self.calls))

    def test_identity_drift_before_compile_never_counts_as_kill(self):
        report = self.rejected_main("before_compile_drift")
        self.assertTrue(report["baseline"]["toolchain_identity"]["valid"])
        self.assertIsNone(report["baseline"]["compilation"])
        self.assertFalse(any(command[1] == "test" for command, _, _ in self.calls))

    def test_identity_drift_before_test_invalidates_compilation_credit(self):
        report = self.rejected_main("before_test_drift")
        baseline = report["baseline"]
        self.assertEqual(baseline["compilation"]["returncode"], 0)
        self.assertTrue(baseline["test_toolchain_identity"]["valid"])
        self.assertIn("changed between compilation and test", baseline["error"])
        self.assertEqual(sum(command[1] == "test" for command, _, _ in self.calls), 1)

    def test_unselected_toolchain_records_default_without_inventing_pin(self):
        env = self.env.copy()
        env.pop("RUSTUP_TOOLCHAIN", None)
        with patch.object(mutations.subprocess, "run", self.fake_subprocess(selected=False)):
            identity = mutations.toolchain_identity(
                self.cargo, self.root, 1, mutations.suite_environment(env, self.root)
            )
        self.assertTrue(identity["valid"])
        self.assertEqual(identity["selection"], "rustup-default")
        self.assertIsNone(identity["effective_environment"]["RUSTUP_TOOLCHAIN"])
        self.assertTrue(all("RUSTUP_TOOLCHAIN" not in env for _, env, _ in self.calls))

    def test_invalid_reference_never_matches_or_counts_as_kill(self):
        report = self.rejected_main("invalid_reference")
        reference = report["reference_toolchain_identity"]
        self.assertFalse(reference["valid"])
        self.assertFalse(mutations.same_toolchain(reference, reference))
        self.assertIsNone(report["baseline"])
        self.assertEqual(len(self.calls), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
