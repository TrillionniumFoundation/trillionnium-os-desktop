"""Fail-closed evidence and isolation checks for the single A02 acceptance entry."""

import contextlib
import copy
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
    def complete_mutation_report(self, snapshot):
        """Synthetic subprocess evidence; no compiler or mutation suite runs."""
        runner = acceptance.mutation_evidence
        repo = Path(__file__).resolve().parents[2]
        inputs, fixtures = {}, {}
        for relative in runner.INPUTS:
            source = repo / "libs/os-abi" / relative
            target = snapshot / "libs/os-abi" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            data = source.read_bytes()
            target.write_bytes(data)
            inputs[relative] = acceptance.digest(data)
        for relative in runner.FIXTURES:
            target = snapshot / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            data = (repo / relative).read_bytes()
            target.write_bytes(data)
            fixtures[relative] = acceptance.digest(data)
        identity = {
            "valid": True, "selection": "RUSTUP_TOOLCHAIN",
            "effective_environment": {"RUSTUP_TOOLCHAIN": "nightly-2026-07-21",
                                      "RUSTC": sys.executable, "RUSTC_WRAPPER": "",
                                      "RUSTC_WORKSPACE_WRAPPER": ""},
            "cargo_executable": sys.executable, "cargo_path": sys.executable,
            "rustc_executable": sys.executable, "rustc_path": sys.executable,
            "cargo": {"command": [sys.executable, "--version"], "returncode": 0,
                      "timed_out": False, "stdout": "cargo fixture"},
            "rustc": {"command": [sys.executable, "-vV"], "returncode": 0,
                      "timed_out": False, "stdout": "rustc fixture"},
        }

        def suite_result(suite, source_hash, failed=None):
            count, required = runner.SUITES[suite]
            names = list(required) + [f"other_{index}" for index in range(count - len(required))]
            output = "".join(f"test {name} ... {'FAILED' if name == failed else 'ok'}\n"
                             for name in names)
            output += (f"test result: {'FAILED' if failed else 'ok'}. "
                       f"{count - bool(failed)} passed; {int(bool(failed))} failed; "
                       "0 ignored; 0 measured; 0 filtered out;\n")
            command = [sys.executable, "test", "--offline", "--color", "never", "--test", suite]
            result = {
                "suite": suite, "expected_tests": count, "required_tests": list(required),
                "source_sha256": source_hash, "compiled": True,
                "toolchain_matches_reference": True,
                "toolchain_identity": copy.deepcopy(identity),
                "test_toolchain_identity": copy.deepcopy(identity),
                "compilation": {"command": command + ["--no-run"], "returncode": 0,
                                "timed_out": False},
                "test": {"command": command + ["--", "--test-threads=1"],
                         "returncode": 101 if failed else 0, "timed_out": False, "stdout": output},
                "tests": runner.test_outcome(output, count, required),
            }
            if failed:
                result.update(expected_failure=failed, expected_test_failed=True, killed=True)
            else:
                result["passed"] = True
            return result

        report = {
            "schema": acceptance.PINNED_MUTATION_SCHEMA, "success": True, "errors": [],
            "expected_mutants": 20, "mutants_killed": 20,
            "input_sha256": inputs, "fixture_sha256": fixtures,
            "requested_toolchain": "nightly-2026-07-21",
            "reference_toolchain_identity": identity,
            "expected_tests_by_suite": {suite: count for suite, (count, _) in runner.SUITES.items()},
            "mutants": [],
        }
        for suite, key in (
            ("mutation_kill", "baseline"), ("semantic_edges", "baseline_semantic_edges"),
            ("profile_boundaries", "baseline_profile_boundaries"),
            ("response_snapshot", "baseline_response_snapshot"),
            ("negative_vectors", "baseline_negative_vectors"),
        ):
            report[key] = suite_result(suite, inputs["src/lib.rs"])
        source = (snapshot / "libs/os-abi/src/lib.rs").read_text()
        for name, (suite, designated, source_hash) in acceptance.mutation_expectations(source).items():
            result = suite_result(suite, source_hash, designated)
            result["name"] = name
            report["mutants"].append(result)
        return report

    def test_cold_mutation_batch_can_exceed_one_cargo_command_budget(self):
        # A virtual 75-second batch consists of individually bounded commands.
        # Mock the process boundary to exercise the timeout without sleeping.
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "mutations.json"
            report = self.complete_mutation_report(root)

            def cold_batch(argv, *, timeout, **kwargs):
                if timeout < 75:
                    raise subprocess.TimeoutExpired(argv, timeout)
                self.assertEqual(argv[-2:], ["--timeout", "60"])
                evidence.write_text(json.dumps(report))
                return subprocess.CompletedProcess(argv, 0, "complete batch", "")

            with mock.patch.object(acceptance.subprocess, "run", side_effect=cold_batch):
                old_budget = acceptance.run_command(["batch"], root, {}, 60)
                result = acceptance.run_compiled_mutations(
                    sys.executable, sys.executable, "nightly-2026-07-21", root, {"RUSTC": sys.executable}, 60, 900, evidence)
            self.assertTrue(old_budget["timed_out"])
            self.assertFalse(old_budget["passed"])
            self.assertTrue(result["passed"])
            self.assertEqual(result["timeout_seconds"], 900)
            self.assertEqual(result["cargo_timeout_seconds"], 60)
            self.assertEqual(result["mutants_killed"], 20)

    def test_compiled_mutation_subreport_cannot_lower_its_own_denominator(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "mutations.json"
            complete = self.complete_mutation_report(root)
            clean_process = {"passed": True, "returncode": 0, "timed_out": False}
            cases = (
                ("hos2-rust-source-mutations-v5", 20, 20, True, False),
                (acceptance.PINNED_MUTATION_SCHEMA, 1, 1, True, False),
                (acceptance.PINNED_MUTATION_SCHEMA, 16, 16, True, False),
                (acceptance.PINNED_MUTATION_SCHEMA, 19, 19, True, False),
                (acceptance.PINNED_MUTATION_SCHEMA, True, True, True, False),
                (acceptance.PINNED_MUTATION_SCHEMA, 20, 19, True, False),
                (acceptance.PINNED_MUTATION_SCHEMA, 20, 20, False, False),
                (acceptance.PINNED_MUTATION_SCHEMA, 20, 20, True, True),
            )
            with mock.patch.object(acceptance, "run_command",
                                   side_effect=lambda *args, **kwargs: dict(clean_process)):
                for schema, expected, killed, reported_success, allowed in cases:
                    report = copy.deepcopy(complete)
                    report.update(schema=schema, success=reported_success,
                                  expected_mutants=expected, mutants_killed=killed)
                    evidence.write_text(json.dumps(report))
                    with self.subTest(schema=schema, expected=expected, killed=killed,
                                      successful=reported_success):
                        check = acceptance.run_compiled_mutations(
                            sys.executable, sys.executable, "nightly-2026-07-21",
                            root, {"RUSTC": sys.executable}, 60, 900, evidence,
                        )
                        self.assertIs(check["passed"], allowed)

    def test_compiled_mutation_summary_cannot_substitute_for_complete_kill_evidence(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "mutations.json"
            complete = self.complete_mutation_report(root)
            cases = {}
            cases["summary_only"] = {key: complete[key] for key in (
                "schema", "success", "expected_mutants", "mutants_killed")}
            for name in ("empty_mutants", "missing_baseline", "reported_error", "compiler_failure",
                         "timeout", "filtered_test", "forged_test_summary", "wrong_designated_failure",
                         "duplicate_mutant", "wrong_source", "wrong_inputs", "wrong_toolchain",
                         "boolean_compiler_exit", "boolean_test_exit", "compilation_error", "execution_error"):
                cases[name] = copy.deepcopy(complete)
            cases["empty_mutants"]["mutants"] = []
            del cases["missing_baseline"]["baseline_negative_vectors"]
            cases["reported_error"]["errors"] = ["production baseline failed"]
            cases["compiler_failure"]["mutants"][0]["compilation"]["returncode"] = 101
            cases["timeout"]["mutants"][0]["test"]["timed_out"] = True
            cases["filtered_test"]["mutants"][0]["test"]["stdout"] = (
                cases["filtered_test"]["mutants"][0]["test"]["stdout"].replace("0 filtered", "1 filtered"))
            cases["forged_test_summary"]["mutants"][0]["test"]["stdout"] = ""
            cases["wrong_designated_failure"]["mutants"][0]["expected_failure"] = "another_test"
            cases["duplicate_mutant"]["mutants"][1] = copy.deepcopy(complete["mutants"][0])
            cases["wrong_source"]["mutants"][0]["source_sha256"] = complete["baseline"]["source_sha256"]
            cases["wrong_inputs"]["input_sha256"]["src/lib.rs"] = "0" * 64
            cases["wrong_toolchain"]["mutants"][0]["test_toolchain_identity"]["rustc"]["stdout"] = "drift"
            cases["boolean_compiler_exit"]["mutants"][0]["compilation"]["returncode"] = False
            cases["boolean_test_exit"]["baseline"]["test"]["returncode"] = False
            cases["compilation_error"]["mutants"][0]["compilation"]["error"] = "compiler unavailable"
            cases["execution_error"]["mutants"][0]["test"]["error"] = "execution failed"
            clean_process = {"passed": True, "returncode": 0, "timed_out": False}
            with mock.patch.object(acceptance, "run_command",
                                   side_effect=lambda *args, **kwargs: dict(clean_process)):
                for name, report in cases.items():
                    with self.subTest(name=name):
                        evidence.write_text(json.dumps(report))
                        result = acceptance.run_compiled_mutations(
                            sys.executable, sys.executable, "nightly-2026-07-21", root, {"RUSTC": sys.executable}, 60, 900, evidence)
                        self.assertFalse(result["passed"], name)
                        self.assertTrue(result["evidence_errors"], name)

    def test_compiled_mutation_probe_facts_and_outer_tool_paths_are_required(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            complete = self.complete_mutation_report(root)
            self.assertEqual(acceptance.compiled_report_errors(
                complete, root, "nightly-2026-07-21", sys.executable,
                {"RUSTC": sys.executable}), [])

            def identities(report):
                yield report["reference_toolchain_identity"]
                for key in ("baseline", "baseline_semantic_edges", "baseline_profile_boundaries",
                            "baseline_response_snapshot", "baseline_negative_vectors"):
                    yield report[key]["toolchain_identity"]
                    yield report[key]["test_toolchain_identity"]
                for mutant in report["mutants"]:
                    yield mutant["toolchain_identity"]
                    yield mutant["test_toolchain_identity"]

            cases = {}
            for name in ("failed_probes", "timed_out_probes", "different_executables",
                         "different_resolved_paths", "different_probe_command", "renamed_suite_test"):
                cases[name] = copy.deepcopy(complete)
            for identity in identities(cases["failed_probes"]):
                for compiler in ("cargo", "rustc"):
                    identity[compiler]["returncode"] = 101
            for identity in identities(cases["timed_out_probes"]):
                for compiler in ("cargo", "rustc"):
                    identity[compiler]["timed_out"] = True
            for identity in identities(cases["different_executables"]):
                for compiler, version in (("cargo", "--version"), ("rustc", "-vV")):
                    identity[f"{compiler}_executable"] = f"/different/{compiler}"
                    identity[f"{compiler}_path"] = f"/different/{compiler}"
                    identity[compiler]["command"] = [f"/different/{compiler}", version]
                identity["effective_environment"]["RUSTC"] = "/different/rustc"
            for key in ("baseline", "baseline_semantic_edges", "baseline_profile_boundaries",
                        "baseline_response_snapshot", "baseline_negative_vectors"):
                for command in ("compilation", "test"):
                    cases["different_executables"][key][command]["command"][0] = "/different/cargo"
            for mutant in cases["different_executables"]["mutants"]:
                for command in ("compilation", "test"):
                    mutant[command]["command"][0] = "/different/cargo"
            for identity in identities(cases["different_resolved_paths"]):
                identity["cargo_path"] = "/different/cargo"
                identity["rustc_path"] = "/different/rustc"
            cases["different_probe_command"]["reference_toolchain_identity"]["cargo"]["command"] = ["echo"]
            renamed = cases["renamed_suite_test"]["mutants"][0]
            renamed["test"]["stdout"] = renamed["test"]["stdout"].replace("other_0", "omitted_test_replacement")
            count, required = acceptance.mutation_evidence.SUITES[renamed["suite"]]
            renamed["tests"] = acceptance.mutation_evidence.test_outcome(renamed["test"]["stdout"], count, required)
            for name, report in cases.items():
                with self.subTest(name=name):
                    self.assertTrue(acceptance.compiled_report_errors(
                        report, root, "nightly-2026-07-21", sys.executable,
                        {"RUSTC": sys.executable}), name)

    def test_malformed_compiled_mutation_json_is_a_failed_check(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "mutations.json"
            with mock.patch.object(acceptance, "run_command", return_value={"passed": True}):
                for invalid in ("{", "[]", "null"):
                    with self.subTest(invalid=invalid):
                        evidence.write_text(invalid)
                        result = acceptance.run_compiled_mutations(
                            sys.executable, sys.executable, "nightly-2026-07-21", root, {"RUSTC": sys.executable}, 60, 900, evidence)
                        self.assertFalse(result["passed"])

    def test_mutation_batch_timeout_cannot_pass_with_a_success_report(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "mutations.json"
            evidence.write_text(json.dumps({"schema": acceptance.PINNED_MUTATION_SCHEMA,
                                                "success": True, "expected_mutants": 20,
                                            "mutants_killed": 20}))
            with mock.patch.object(acceptance.subprocess, "run",
                                   side_effect=subprocess.TimeoutExpired("batch", 900)):
                result = acceptance.run_compiled_mutations(
                    sys.executable, sys.executable, "nightly-2026-07-21", root, {"RUSTC": sys.executable}, 60, 900, evidence)
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

    def test_nonempty_readme_does_not_override_complete_codec_acceptance(self):
        # Exercise the final acceptance predicate independently of the tools.
        # README is still source-bound; an unchanged navigation document is
        # not a codec failure after the root-documentation migration.
        def complete(_args, report, _output):
            report.update(
                original_inputs_unchanged=True,
                readme_bytes=len(b"# Project navigation\n"),
                checks=[{"name": name, "passed": True} for name in acceptance.CHECK_NAMES],
            )

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "evidence"
            with mock.patch.object(acceptance, "execute", side_effect=complete):
                with contextlib.redirect_stdout(io.StringIO()):
                    code = acceptance.main(["--output-dir", str(output)])
            report = json.loads((output / "report.json").read_text())
            self.assertEqual(code, 0)
            self.assertTrue(report["success"])
            self.assertGreater(report["readme_bytes"], 0)
            self.assertEqual(report["not_executed"], [])

    def test_nonempty_readme_cannot_hide_changed_inputs_or_incomplete_checks(self):
        for unchanged, omit, failed in ((False, None, None),
                                       (True, "clippy", None),
                                       (True, None, "compiled_mutations")):
            def incomplete(_args, report, _output):
                report.update(
                    original_inputs_unchanged=unchanged, readme_bytes=21,
                    checks=[{"name": name, "passed": name != failed}
                            for name in acceptance.CHECK_NAMES if name != omit],
                )

            with self.subTest(unchanged=unchanged, omit=omit, failed=failed):
                with tempfile.TemporaryDirectory() as temporary:
                    output = Path(temporary) / "evidence"
                    with mock.patch.object(acceptance, "execute", side_effect=incomplete):
                        with contextlib.redirect_stdout(io.StringIO()):
                            code = acceptance.main(["--output-dir", str(output)])
                    report = json.loads((output / "report.json").read_text())
                    self.assertEqual(code, 1)
                    self.assertFalse(report["success"])

    def test_missing_tool_writes_failure_report_with_unchanged_source(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            repo = root / "repo"
            for relative in acceptance.SOURCE_ROOTS:
                (repo / relative).mkdir(parents=True)
            (repo / "libs/os-abi/Cargo.toml").write_text("[package]\nname='fixture'\nversion='0.0.0'\n")
            readme = b"# Project navigation\n\nSee the pinned module guides.\n"
            (repo / "README.md").write_bytes(readme)
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
            self.assertEqual(report["readme_bytes"], len(readme))
            self.assertEqual(report["input_sha256"]["README.md"], acceptance.digest(readme))
            self.assertEqual((repo / "README.md").read_bytes(), readme)
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

# Exact current-main gate refresh marker.
