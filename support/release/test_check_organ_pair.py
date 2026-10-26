"""Exercise pair provenance and actual command failures with temporary Git DAGs."""

import copy
import importlib.util
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name(filename))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


runner = load("check_organ_pair", "check_organ_pair.py")
fixtures = load("release_profile_tests", "test_organ_release_profile.py")


class PairExecutionTests(unittest.TestCase):
    def setUp(self):
        fixtures.SourceCombinationTests.setUp(self)
        self.output = self.root / "execution"
        fixtures.write(self.os, "support/release/organ_source_map.json",
                       runner.profile.canonical(self.mapping))
        fixtures.commit(self.os, "review source map")
        with patch.object(runner.profile, "HISTORY_OWNER", fixtures.profile.HISTORY_OWNER):
            manifest, _ = runner.profile.create_manifest(
                *fixtures.SourceCombinationTests.inputs(self))
        self.manifest = self.root / "profile.json"
        self.manifest.write_bytes(runner.profile.canonical(manifest))
        self.owner = fixtures.profile.HISTORY_OWNER
        self.dispatched = []
        self.fail_step = None
        self.real_execute_step = runner.execute_step

    def prepare_expanded_profile(self, version):
        fixtures.SourceCombinationTests.upgrade_to_version(self, version)
        fixtures.write(self.os, f"support/release/{runner.profile.source_map_name(version)}",
                       runner.profile.canonical(self.mapping))
        fixtures.commit(self.os, "review expanded source map")
        with patch.object(runner.profile, "HISTORY_OWNER", self.owner):
            manifest, _ = runner.profile.create_manifest(*fixtures.SourceCombinationTests.inputs(self))
        self.manifest.write_bytes(runner.profile.canonical(manifest))

    def execute_fixture(self, step, output, environment, timeout, targets=None):
        # Exercise real bounded child execution without requiring Cargo in this
        # temporary-Git tool test. Retain the actual code-owned dispatch separately.
        self.dispatched.append(step)
        name, cwd, toolchain, _ = step
        exit_code = 13 if name == self.fail_step else 0
        child = (name, cwd, toolchain, [sys.executable, "-c",
                 "import sys; print('fixture command'); raise SystemExit(int(sys.argv[1]))",
                 str(exit_code)])
        return self.real_execute_step(child, output, environment, timeout, targets)

    def arguments(self):
        return ["--os-repo", str(self.os), "--hepta-repo", str(self.hepta),
                "--os-head", fixtures.git(self.os, "rev-parse", "HEAD"),
                "--os-tree", fixtures.git(self.os, "rev-parse", "HEAD^{tree}"),
                "--manifest", str(self.manifest), "--output-dir", str(self.output)]

    def run_pair(self, *extra):
        with patch.object(runner.profile, "HISTORY_OWNER", self.owner):
            return runner.main(self.arguments() + list(extra))

    def receipt(self):
        return json.loads((self.output / "pair-receipt.json").read_text())

    def test_source_only_never_runs_host_commands(self):
        with patch.object(runner, "execute_step", side_effect=AssertionError("unexpected execution")):
            self.assertEqual(self.run_pair(), 0)
        self.assertEqual(self.receipt()["qualification"], "source-only")
        self.assertEqual(self.receipt()["steps"], [])

    def test_v2_selects_fixed_v2_map_and_runs_source_check(self):
        fixtures.SourceCombinationTests.upgrade_to_v2(self)
        fixtures.write(self.os, "support/release/organ_source_map_v2.json",
                       runner.profile.canonical(self.mapping))
        fixtures.commit(self.os, "review v2 source map")
        with patch.object(runner.profile, "HISTORY_OWNER", self.owner):
            manifest, _ = runner.profile.create_manifest(*fixtures.SourceCombinationTests.inputs(self))
        self.manifest.write_bytes(runner.profile.canonical(manifest))
        with patch.object(runner, "execute_step", side_effect=AssertionError("unexpected execution")):
            self.assertEqual(self.run_pair(), 0)
        self.assertEqual(self.receipt()["source"]["schema_version"], 2)
        self.assertEqual(self.receipt()["qualification"], "source-only")

    def test_default_v3_selection_cannot_fall_back_after_receiving_role_omission(self):
        self.prepare_expanded_profile(3)
        incomplete = copy.deepcopy(self.mapping)
        incomplete["sources"]["os"].pop("kernel_runtime_handoff_drop_tail_control")
        fixtures.write(self.os, "support/release/organ_source_map_v3.json",
                       runner.profile.canonical(incomplete))
        fixtures.commit(self.os, "omit required receiving control from default v3 map")
        with patch.object(runner, "execute_step", side_effect=AssertionError("unexpected execution")):
            self.assertEqual(self.run_pair("--execute-host"), 1)
        self.assertEqual(self.dispatched, [])
        self.assertFalse(self.output.exists())

    def test_wrong_pin_prevents_any_execution_or_output(self):
        manifest = json.loads(self.manifest.read_text())
        manifest["hepta"]["commit"] = "0" * 40
        self.manifest.write_text(json.dumps(manifest))
        with patch.object(runner, "execute_step", side_effect=AssertionError("unexpected execution")):
            self.assertEqual(self.run_pair("--execute-host"), 1)
        self.assertFalse(self.output.exists())

    def test_v3_selects_fixed_native_owner_map(self):
        self.prepare_expanded_profile(3)
        with patch.object(runner, "execute_step", side_effect=AssertionError("unexpected execution")):
            self.assertEqual(self.run_pair("--required-schema", "3"), 0)
        self.assertEqual(self.receipt()["source"]["schema_version"], 3)
        self.assertEqual(self.receipt()["qualification"], "source-only")

    def test_required_schema_blocks_a_valid_historical_manifest_before_execution(self):
        with patch.object(runner, "execute_step", side_effect=AssertionError("unexpected execution")):
            self.assertEqual(self.run_pair("--required-schema", "3", "--execute-host"), 1)
        self.assertFalse(self.output.exists())

    def test_v3_host_commands_cover_original_sqlite_and_root_contract_owners(self):
        steps = runner.host_steps(self.os, self.hepta, False, schema_version=3)
        tests = next(step[3] for step in steps if step[0] == "hepta-tests")
        packages = {tests[index + 1] for index, flag in enumerate(tests) if flag == "-p"}
        self.assertEqual(packages, {"codex-hepta-agentd", "codex-hepta-memory",
                                   "codex-hepta-cognitive-store", "codex-hepta-contracts", "codex-state",
                                   "codex-hepta-agent-protocol", "codex-hepta-learning-ledger",
                                   "codex-git-utils", "codex-hepta-memory-extension",
                                   "codex-hepta-automation", "codex-hepta-fleet", "codex-hepta-supervisor",
                                   "codex-arg0"})
        self.assertIn("--locked", tests)
        root = next(step[3] for step in steps if step[0] == "hepta-root-build")
        self.assertIn("hepta-authority-host", root)
        self.assertIn("--locked", root)
        recovery = next(step[3] for step in steps if step[0] == "hepta-recovery-build")
        self.assertIn("hepta-supervisor-intent-recovery", recovery)
        self.assertIn("--locked", recovery)

    def test_v3_actual_dispatch_runs_thirteen_owners_and_all_three_hepta_binaries(self):
        self.prepare_expanded_profile(3)
        with patch.object(runner, "execute_step", side_effect=self.execute_fixture):
            self.assertEqual(self.run_pair("--required-schema", "3", "--execute-host", "--offline"), 0)
        self.assertEqual([step[0] for step in self.dispatched],
                         ["ui-build", "ui-tests", "adapter-tests", "hepta-build",
                          "hepta-root-build", "hepta-recovery-build", "hepta-tests"])
        tests = self.dispatched[-1][3]
        self.assertEqual(tests, ["just", "test", "--locked", "--offline",
                         "-p", "codex-hepta-agentd", "-p", "codex-hepta-memory",
                         "-p", "codex-hepta-cognitive-store", "-p", "codex-hepta-contracts",
                         "-p", "codex-state", "-p", "codex-hepta-agent-protocol",
                         "-p", "codex-hepta-learning-ledger", "-p", "codex-git-utils",
                         "-p", "codex-hepta-memory-extension", "-p", "codex-hepta-automation",
                         "-p", "codex-hepta-fleet", "-p", "codex-hepta-supervisor",
                         "-p", "codex-arg0", "--test-threads", "2", "--retries", "0", "--cargo-profile", "dev-small"])
        binaries = {
            "hepta-build": ("codex-hepta-agentd", "codex-hepta-agentd"),
            "hepta-root-build": ("codex-hepta-agentd", "hepta-authority-host"),
            "hepta-recovery-build": ("codex-hepta-supervisor", "hepta-supervisor-intent-recovery"),
        }
        for name, cwd, toolchain, argv in self.dispatched:
            if name not in binaries:
                continue
            package, binary = binaries[name]
            with self.subTest(binary=binary):
                self.assertEqual(cwd, self.hepta)
                self.assertEqual(toolchain, "1.95.0")
                self.assertEqual(argv, ["cargo", "build", "--manifest-path", "codex-rs/Cargo.toml",
                                       "-p", package, "--bin", binary, "--profile", "dev-small",
                                       "--locked", "--offline"])
        self.assertEqual(self.receipt()["qualification"], "host-build-tests")

    def test_v3_build_only_dispatches_recovery_binary_without_claiming_tests(self):
        self.prepare_expanded_profile(3)
        with patch.object(runner, "execute_step", side_effect=self.execute_fixture):
            self.assertEqual(self.run_pair("--required-schema", "3", "--build-host"), 0)
        self.assertEqual([step[0] for step in self.dispatched],
                         ["ui-build", "hepta-build", "hepta-root-build", "hepta-recovery-build"])
        self.assertEqual(self.receipt()["qualification"], "host-builds")

    def test_v3_failed_real_recovery_build_child_cannot_qualify_or_run_tests(self):
        self.prepare_expanded_profile(3)
        self.fail_step = "hepta-recovery-build"
        with patch.object(runner, "execute_step", side_effect=self.execute_fixture):
            self.assertEqual(self.run_pair("--required-schema", "3", "--execute-host"), 1)
        self.assertEqual(self.dispatched[-1][0], "hepta-recovery-build")
        self.assertNotIn("hepta-tests", [step[0] for step in self.dispatched])
        receipt = self.receipt()
        self.assertFalse(receipt["passed"])
        self.assertEqual(receipt["qualification"], "none")
        self.assertEqual(receipt["steps"][-1]["exit_code"], 13)

    def test_v3_manifest_cannot_inject_commands_owners_binaries_or_profile(self):
        self.prepare_expanded_profile(3)
        original = json.loads(self.manifest.read_text())
        for key, value in (("host_commands", [["/fixture/attacker"]]),
                           ("owning_packages", ["codex-hepta-agentd"]),
                           ("hepta_binaries", ["codex-hepta-agentd"]),
                           ("hepta_profile", "unlocked-fixture")):
            manifest = copy.deepcopy(original)
            manifest[key] = value
            self.manifest.write_bytes(runner.profile.canonical(manifest))
            with self.subTest(injection=key), patch.object(
                    runner, "execute_step", side_effect=AssertionError("unverified execution")):
                self.assertEqual(self.run_pair("--required-schema", "3", "--execute-host"), 1)
            self.assertFalse(self.output.exists())

    def test_v3_missing_recovery_or_migration_source_blocks_before_execution(self):
        self.prepare_expanded_profile(3)
        original = json.loads(self.manifest.read_text())
        for role in ("agentd_recovered_writer_oracle", "agentd_arg0_dispatch", "supervisor_intent_recovery_cli", "supervisor_signed_recovery_oracle",
                     "supervisor_protocol_gate", "automation_migration_0016", "automation_timer_migration"):
            manifest = copy.deepcopy(original)
            manifest["sources"]["hepta"] = [entry for entry in manifest["sources"]["hepta"]
                                             if entry["role"] != role]
            self.manifest.write_bytes(runner.profile.canonical(manifest))
            with self.subTest(omitted=role), patch.object(
                    runner, "execute_step", side_effect=AssertionError("unverified execution")):
                self.assertEqual(self.run_pair("--required-schema", "3", "--execute-host"), 1)
            self.assertFalse(self.output.exists())

    def test_historical_host_dispatch_keeps_original_three_owners_and_binary(self):
        for version in (1, 2):
            if version == 2:
                self.prepare_expanded_profile(2)
            self.output = self.root / f"execution-v{version}"
            self.dispatched = []
            with self.subTest(version=version), patch.object(
                    runner, "execute_step", side_effect=self.execute_fixture):
                self.assertEqual(self.run_pair("--execute-host"), 0)
            self.assertEqual([step[0] for step in self.dispatched],
                             ["ui-build", "ui-tests", "adapter-tests", "hepta-build", "hepta-tests"])
            tests = self.dispatched[-1][3]
            self.assertEqual([tests[index + 1] for index, flag in enumerate(tests) if flag == "-p"],
                             ["codex-hepta-agentd", "codex-hepta-memory", "codex-hepta-cognitive-store"])

    def test_actual_nonzero_child_never_qualifies_pair(self):
        step = ("failure", self.os, "1.95.0", [sys.executable, "-c", "raise SystemExit(7)"])
        with patch.object(runner, "host_steps", return_value=[step]):
            self.assertEqual(self.run_pair("--execute-host"), 1)
        self.assertEqual(self.receipt()["qualification"], "none")
        self.assertEqual(self.receipt()["steps"][0]["exit_code"], 7)

    def test_generator_modifying_sources_invalidates_successful_command(self):
        step = ("generator", self.os, "1.95.0",
                [sys.executable, "-c", "from pathlib import Path; Path('generated.rs').write_text('x')"])
        with patch.object(runner, "host_steps", return_value=[step]):
            self.assertEqual(self.run_pair("--execute-host"), 1)
        self.assertFalse(self.receipt()["passed"])
        self.assertIn("dirty checkout", self.receipt()["error"])

    def test_slow_actual_child_is_stopped_and_cannot_qualify(self):
        step = ("timeout", self.os, "1.95.0",
                [sys.executable, "-c", "import time; time.sleep(60)"])
        with patch.object(runner, "host_steps", return_value=[step]):
            self.assertEqual(self.run_pair("--execute-host", "--step-timeout", "1"), 1)
        self.assertEqual(self.receipt()["qualification"], "none")
        self.assertEqual(self.receipt()["steps"][0]["error"], "step_timeout")

    def test_success_records_real_log_and_retains_source_identity(self):
        step = ("success", self.os, "1.95.0", [sys.executable, "-c", "print('actual child')"])
        with patch.object(runner, "host_steps", return_value=[step]):
            self.assertEqual(self.run_pair("--execute-host"), 0)
        receipt = self.receipt()
        self.assertEqual(receipt["qualification"], "host-build-tests")
        self.assertEqual((self.output / "success.log").read_text(), "actual child\n")
        self.assertEqual(receipt["source"]["os"]["commit"],
                         fixtures.git(self.os, "rev-parse", "HEAD"))
        self.assertEqual(receipt["production_authority"], "not_configured_by_this_tool")

    def test_receipt_hash_binds_the_manifest_bytes_actually_verified(self):
        raw = self.manifest.read_bytes()
        verify = runner.profile.verify_manifest

        def replace_after_verification(*args):
            result = verify(*args)
            self.manifest.write_bytes(b'{"different":"unverified bytes"}\n')
            return result

        with patch.object(runner.profile, "verify_manifest", side_effect=replace_after_verification):
            self.assertEqual(self.run_pair(), 0)
        self.assertEqual(self.receipt()["manifest_sha256"], runner.profile.sha256(raw))

    def test_build_only_runs_binaries_without_claiming_tests(self):
        steps = [(name, self.os, "1.95.0", [sys.executable, "-c", "print('built')"])
                 for name in ("ui-build", "ui-tests", "adapter-tests", "hepta-build", "hepta-tests")]
        with patch.object(runner, "host_steps", return_value=steps):
            self.assertEqual(self.run_pair("--build-host"), 0)
        receipt = self.receipt()
        self.assertEqual([item["name"] for item in receipt["steps"]], ["ui-build", "hepta-build"])
        self.assertEqual(receipt["qualification"], "host-builds")


if __name__ == "__main__":
    unittest.main()
