"""Fast subprocess-boundary checks for mutation toolchain evidence.

No real Cargo or Rust compiler is executed. The production runner still constructs
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
            self.assertEqual(env["RUSTC_WRAPPER"], "")
            self.assertEqual(env["RUSTC_WORKSPACE_WRAPPER"], "")
            self.assertFalse(any(name in env for name in (
                "CARGO_BUILD_RUSTC", "CARGO_BUILD_RUSTC_WRAPPER",
                "CARGO_BUILD_RUSTC_WORKSPACE_WRAPPER",
            )))
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
            for key in ("baseline", "baseline_semantic_edges", "baseline_profile_boundaries",
                        "baseline_response_snapshot", "baseline_negative_vectors"):
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
                         {"RUSTUP_TOOLCHAIN": "nightly-2026-07-21", "RUSTC": sys.executable,
                          "RUSTC_WRAPPER": "", "RUSTC_WORKSPACE_WRAPPER": ""})
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

    def test_successful_probes_with_unisolated_compiler_environment_are_invalid(self):
        probe = {"returncode": 0, "timed_out": False, "stdout": "pinned"}
        for key, value in (("RUSTC", None), ("RUSTC_WRAPPER", None),
                           ("RUSTC_WRAPPER", "/untrusted/wrapper"),
                           ("RUSTC_WORKSPACE_WRAPPER", None),
                           ("RUSTC_WORKSPACE_WRAPPER", "/untrusted/workspace-wrapper")):
            with self.subTest(key=key, value=value):
                env = mutations.suite_environment(self.env, self.root)
                if value is None:
                    env.pop(key)
                else:
                    env[key] = value
                with patch.object(mutations, "run_command", return_value=probe):
                    identity = mutations.toolchain_identity(self.cargo, self.root, 1, env)
                self.assertFalse(identity["valid"])
                self.assertFalse(mutations.same_toolchain(identity, identity))

    def isolated_fake_cargo_suite(self, explicit_rustc):
        """Exercise real subprocesses with a Cargo environment precedence fixture.

        No Rust code is compiled. A trap executable records any wrapper or
        alternate compiler invocation, including a configured wrapper exposed
        by deleting rather than explicitly clearing the canonical variable.
        """
        tools = self.root / "tools"
        tools.mkdir()
        trap_marker = self.root / "unexpected-wrapper-or-compiler"
        compiler_marker = self.root / "selected-compiler"

        def executable(name, body):
            path = tools / name
            path.write_text(f"#!{sys.executable}\n" + body, encoding="utf-8")
            path.chmod(0o755)
            return str(path)

        trap = executable("trap", (
            "from pathlib import Path\n"
            f"Path({str(trap_marker)!r}).write_text('intercepted')\n"
            "raise SystemExit(44)\n"
        ))
        rustc = executable("rustc", (
            "from pathlib import Path\n"
            f"with Path({str(compiler_marker)!r}).open('a') as output:\n"
            "    output.write('selected\\n')\n"
            "print('rustc pinned\\nrelease: 1.99.0-nightly')\n"
        ))
        cargo = executable("cargo", (
            "import os, subprocess, sys\n"
            "if sys.argv[1:] == ['--version']:\n"
            "    print('cargo pinned')\n"
            "    raise SystemExit(0)\n"
            "for name in ('RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER'):\n"
            f"    wrapper = os.environ.get(name, os.environ.get('CARGO_BUILD_' + name, {trap!r}))\n"
            "    if wrapper:\n"
            "        subprocess.run([wrapper], check=True)\n"
            "compiler = os.environ.get('RUSTC') or os.environ.get('CARGO_BUILD_RUSTC') or 'rustc'\n"
            "subprocess.run([compiler, '-vV'], check=True, capture_output=True, text=True)\n"
            "if '--no-run' not in sys.argv:\n"
            f"    print({self.passing_output!r}, end='')\n"
        ))
        env = self.env.copy()
        env.update(PATH=str(tools) + os.pathsep + env.get("PATH", os.defpath),
                   RUSTC_WRAPPER=trap, RUSTC_WORKSPACE_WRAPPER=trap,
                   CARGO_BUILD_RUSTC=trap, CARGO_BUILD_RUSTC_WRAPPER=trap,
                   CARGO_BUILD_RUSTC_WORKSPACE_WRAPPER=trap)
        if explicit_rustc:
            env["RUSTC"] = rustc
        else:
            env.pop("RUSTC", None)
        reference_cwd = self.root / "reference"
        reference_cwd.mkdir()
        reference = mutations.toolchain_identity(
            cargo, reference_cwd, 3, mutations.suite_environment(env, reference_cwd)
        )
        result = mutations.run_suite(
            self.root / "suite", {"src/lib.rs": b""}, {}, "// source",
            cargo, 3, "mutation_kill", env, reference,
        )
        self.assertTrue(reference["valid"])
        self.assertTrue(mutations.baseline_passed(result), result)
        self.assertFalse(trap_marker.exists(), "an ambient wrapper/compiler executed")
        self.assertEqual(compiler_marker.read_text().splitlines(), ["selected"] * 5)
        self.assertEqual(result["toolchain_identity"]["rustc_path"], rustc)
        effective = result["toolchain_identity"]["effective_environment"]
        self.assertEqual(effective["RUSTC"], rustc if explicit_rustc else "rustc")
        self.assertEqual(effective["RUSTC_WRAPPER"], "")
        self.assertEqual(effective["RUSTC_WORKSPACE_WRAPPER"], "")

    def test_snapshot_source_mutants_target_existing_guards_and_complete_suite(self):
        source = (Path(__file__).resolve().parents[2] / "libs/os-abi/src/lib.rs").read_text(
            encoding="utf-8"
        )
        self.assertEqual(len(mutations.SNAPSHOT_MUTANTS), 4)
        self.assertEqual(mutations.EXPECTED_MUTANT_COUNT, 20)
        self.assertEqual(mutations.SUITES["response_snapshot"],
                         (5, mutations.SNAPSHOT_TESTS))
        self.assertEqual(len(set(mutations.SNAPSHOT_TESTS)), 5)
        names = set()
        for name, designated, changes in mutations.SNAPSHOT_MUTANTS:
            with self.subTest(name=name):
                self.assertNotIn(name, names)
                names.add(name)
                self.assertIn(designated, mutations.SNAPSHOT_TESTS)
                self.assertEqual(len(changes), 1)
                mutated = mutations.mutated_profile_source(source, changes)
                self.assertNotEqual(mutated, source)
                for old, new in changes:
                    self.assertEqual(source.count(old), 1)
                    self.assertEqual(mutated.count(new), 1)

    def test_cumulative_bound_mutant_changes_both_decoder_and_encoder(self):
        source = (Path(__file__).resolve().parents[2] / "libs/os-abi/src/lib.rs").read_text(
            encoding="utf-8"
        )
        variants = [item for item in mutations.PROFILE_MUTANTS
                    if item[0] == "accept_prior_window_cpu_sum"]
        self.assertEqual(len(variants), 1)
        name, designated, changes = variants[0]
        self.assertEqual(designated,
                         "read_usage_rejects_impossible_or_misaligned_cpu_snapshots")
        self.assertEqual(len(changes), 2)
        for original, replacement in changes:
            with self.subTest(original=original):
                self.assertEqual(source.count(original), 1)
                self.assertEqual(replacement, "|| false")
                 self.assertIn("cumulative_cpu_ns - window_consumed_ns > window_start_ns", original)
        mutated = mutations.mutated_profile_source(source, changes)
        self.assertNotEqual(mutated, source)

    def test_negative_wire_source_mutants_are_real_unique_changes(self):
        source = (Path(__file__).resolve().parents[2] / "libs/os-abi/src/lib.rs").read_text(
            encoding="utf-8"
        )
        self.assertEqual(len(mutations.NEGATIVE_MUTANTS), 3)
        self.assertEqual(mutations.SUITES["negative_vectors"],
                         (21, mutations.NEGATIVE_TESTS))
        self.assertEqual(len(set(mutations.NEGATIVE_TESTS)), 2)
        for name, designated, changes in mutations.NEGATIVE_MUTANTS:
            with self.subTest(name=name):
                self.assertIn(designated, mutations.NEGATIVE_TESTS)
                self.assertEqual(len(changes), 1)
                self.assertNotEqual(mutations.mutated_profile_source(source, changes), source)
                for before, after in changes:
                    self.assertEqual(source.count(before), 1)
                    self.assertEqual(source.count(after), 0)

    def test_inherited_and_configured_wrappers_cannot_intercept_explicit_compiler(self):
        self.isolated_fake_cargo_suite(explicit_rustc=True)

    def test_cargo_build_rustc_cannot_bypass_default_compiler_probe(self):
        self.isolated_fake_cargo_suite(explicit_rustc=False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
