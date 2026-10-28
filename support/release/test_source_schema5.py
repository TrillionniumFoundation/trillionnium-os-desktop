"""Fixed V5 association regressions; owned Git/child fixtures are not product qualification."""
import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixtures = load("schema5_original_fixtures", "test_organ_release_profile.py")
pair_tests = load("schema5_pair_fixtures", "test_check_organ_pair.py")
v4_tests = load("schema5_workflow_helpers", "test_source_schema4.py")
profile = fixtures.profile
runner = pair_tests.runner
PACKAGES = ["codex-hepta-agentd", "codex-hepta-memory", "codex-hepta-cognitive-store",
            "codex-hepta-contracts", "codex-state", "codex-hepta-agent-protocol",
            "codex-hepta-learning-ledger", "codex-git-utils", "codex-hepta-memory-extension",
            "codex-hepta-automation", "codex-hepta-fleet", "codex-hepta-supervisor", "codex-arg0",
            "codex-app-server-protocol", "codex-thread-store", "codex-core-plugins",
            "codex-rollout", "codex-file-system", "codex-rmcp-client"]
STEPS = ["ui-build", "ui-tests", "adapter-tests", "hepta-build", "hepta-root-build",
         "hepta-recovery-build", "hepta-tests"]


def install(case, fx, version=5):
    mapping = fx.profile.load_json(HERE / fx.profile.source_map_name(version))
    case.mapping = mapping
    for side in ("os", "hepta"):
        for role, path in mapping["sources"][side].items():
            fx.write(getattr(case, side), path, (side + ":" + role + " source\n").encode())
    for role, paths in mapping["goldens"].items():
        for side in ("os", "hepta"):
            fx.write(getattr(case, side), paths[side], (role + " exact golden\n").encode())
    fx.write(case.os, "support/release/" + fx.profile.source_map_name(version), fx.profile.canonical(mapping))
    fx.commit(case.os, "review fixed schema source paths")
    fx.commit(case.hepta, "review original-owner descendant source paths")


class Schema5DeclarationTests(unittest.TestCase):
    def setUp(self):
        self.mapping = profile.load_json(HERE / "organ_source_map_v5.json")

    def test_exact_role_counts_paths_seal_and_five_goldens(self):
        profile.check_map(self.mapping)
        self.assertEqual((len(self.mapping["sources"]["os"]), len(self.mapping["sources"]["hepta"])), (396, 261))
        self.assertEqual(len(self.mapping["goldens"]), 5)
        self.assertEqual(profile.sha256(profile.canonical(self.mapping)), profile.SOURCE_MAP_V5_SHA256)
        self.assertEqual(profile.source_map_name(5), "organ_source_map_v5.json")
        self.assertTrue(profile.OS_ROLES_V4 < profile.OS_ROLES_V5)
        self.assertTrue(profile.HEPTA_ROLES_V4 < profile.HEPTA_ROLES_V5)

    def test_each_new_role_is_mandatory_and_cannot_alias_another_path(self):
        for side, old in (("os", profile.OS_ROLES_V4), ("hepta", profile.HEPTA_ROLES_V4)):
            for role in sorted(set(self.mapping["sources"][side]) - old):
                for mutation in ("omit", "alias"):
                    edited = copy.deepcopy(self.mapping)
                    entries = edited["sources"][side]
                    if mutation == "omit":
                        entries.pop(role)
                    else:
                        entries[role] = next(path for name, path in entries.items() if name != role)
                    with self.subTest(side=side, role=role, mutation=mutation), self.assertRaises(profile.ProfileError):
                        profile.check_map(edited)

    def test_operator_paths_unknown_roles_keys_and_schema_tags_cannot_create_a_profile(self):
        mutations = [lambda m: m["sources"]["os"].update(unreviewed="other/file.rs"),
                     lambda m: m["sources"]["os"].update(release_schema5_oracle="other/test.py"),
                     lambda m: m.update(profile="operator-profile"),
                     lambda m: m.update(schema_version=4),
                     lambda m: m.update(schema_version=True),
                     lambda m: m.update(schema_version=5.0),
                     lambda m: m.update(schema_version="5"),
                     lambda m: m.update(schema_version=6)]
        for index, mutate in enumerate(mutations):
            edited = copy.deepcopy(self.mapping)
            mutate(edited)
            with self.subTest(mutation=index), self.assertRaises(profile.ProfileError):
                profile.check_map(edited)

    def test_old_v4_map_retagged_five_stays_unsupported(self):
        edited = profile.load_json(HERE / "organ_source_map_v4.json")
        edited["schema_version"] = 5
        with self.assertRaisesRegex(profile.ProfileError, "unsupported source map"):
            profile.check_map(edited)

    def test_duplicate_json_keys_are_not_a_second_contract(self):
        raw = profile.canonical(self.mapping).decode().replace('"schema_version": 5', '"schema_version": 5, "schema_version": 5')
        with self.assertRaisesRegex(profile.ProfileError, "duplicate JSON key"):
            profile.load_json_bytes(raw.encode(), "duplicate V5")

    def test_v4_dispatch_keeps_eighteen_while_v5_adds_the_real_oauth_owner(self):
        for version, expected in ((4, PACKAGES[:-1]), (5, PACKAGES)):
            steps = runner.host_steps(Path("/owned-os"), Path("/owned-hepta"), True, schema_version=version)
            self.assertEqual([row[0] for row in steps], STEPS)
            argv = steps[-1][3]
            actual = [argv[index + 1] for index, flag in enumerate(argv) if flag == "-p"]
            self.assertEqual(actual, expected)
            self.assertEqual(len(actual), len(set(actual)))
            self.assertEqual(argv[-6:], ["--test-threads", "2", "--retries", "0", "--cargo-profile", "dev-small"])

    def test_stable_source_summary_executes_fail_closed_for_every_matrix_result(self):
        workflow = HERE.parents[1] / ".github/workflows/organ-release-profile.yml"
        text = workflow.read_text()
        summary = text.split("  source-profile-host:\n", 1)[1].split("\n  source-profile-oracle:", 1)[0]
        self.assertIn("needs: [source-profile-oracle]", summary)
        self.assertIn("always()", summary)
        script = v4_tests.workflow_run_block(workflow, "Require every complete source-tool partition to succeed")
        for status in ("success", "failure", "cancelled", "skipped", ""):
            result = subprocess.run(["bash", "-c", script], env=dict(os.environ, ORACLE_RESULT=status),
                                    capture_output=True, timeout=30)
            with self.subTest(status=status):
                self.assertEqual(result.returncode == 0, status == "success")

    def test_manual_historical_routes_require_an_explicit_full_commit(self):
        for name, historical_job, current_job in (("organ-current-pair.yml", "historical-v4-host-pair", "original-host-pair"),
                                                   ("organ-release-profile.yml", "historical-v4-source-profile", "source-profile-oracle")):
            workflow = HERE.parents[1] / ".github/workflows" / name
            text = workflow.read_text()
            historical = text.split("  " + historical_job + ":\n", 1)[1]
            self.assertIn("github.event_name == 'workflow_dispatch' && inputs.historical_os_ref != ''", historical)
            self.assertIn("DESKTOP_SHA: ${{ inputs.historical_os_ref }}", historical)
            current = text.split("  " + current_job + ":\n", 1)[1].split("\n  " + historical_job + ":", 1)[0]
            self.assertIn("github.event_name != 'workflow_dispatch' || inputs.historical_os_ref == ''", current)
            script = v4_tests.workflow_run_block(workflow, "Validate explicit historical V4 source identity")
            for ref in ("", "main", "a" * 39, "A" * 40, "a" * 40):
                result = subprocess.run(["bash", "-c", script], env=dict(os.environ, DESKTOP_SHA=ref),
                                        capture_output=True, timeout=30)
                with self.subTest(workflow=name, ref=ref):
                    self.assertEqual(result.returncode == 0, ref == "a" * 40)

    def test_actual_ci_discovery_is_the_exact_disjoint_union_with_original_case_ids(self):
        workflow = HERE.parents[1] / ".github/workflows/organ-release-profile.yml"
        script = v4_tests.workflow_run_block(workflow, "Run the bounded exact V5 case partition without skipped tests")
        start = 'python3 "${python_flags[@]}" -I -B - <<\'PY\'\n'
        self.assertEqual(script.count(start), 1)
        python = script.split(start, 1)[1].split("\nPY", 1)[0]
        # Execute the actual discovery/seal boundary without recursively running suites.
        discovery = python.split("selected = os.environ", 1)[0]
        discovery += "\nprint('exact union', len(all_ids), 'partitions', [len(ids[name]) for name in modules])\n"
        result = subprocess.run([sys.executable, "-I", "-B", "-c", discovery], cwd=HERE.parents[1],
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("exact union", result.stdout)


class Schema5SourceTests(unittest.TestCase):
    inputs = fixtures.SourceCombinationTests.inputs
    build = fixtures.SourceCombinationTests.build
    verify = fixtures.SourceCombinationTests.verify

    def setUp(self):
        fixtures.SourceCombinationTests.setUp(self)
        install(self, fixtures)

    def test_positive_source_only_uses_typed_owner_chain_and_whole_current_proof(self):
        manifest, receipt = self.build()
        self.assertEqual(manifest["schema_version"], 5)
        self.assertEqual(profile.check_current_contract_v5(manifest, self.mapping), manifest["hepta"]["commit"])
        self.assertEqual(self.verify(manifest)["source_checks"], "passed")
        self.assertEqual(receipt["original_history_proof"]["method"], "verified_sha1_parent_path")
        for side in ("os", "hepta"):
            proof = receipt["git_object_closure"][side]
            self.assertTrue(proof["object_sha1_verified"])
            self.assertTrue(proof["tree_blob_entry_types_verified"])
            self.assertEqual(proof["missing_objects"], 0)
            self.assertEqual(receipt["current_source_proof"][side]["index_flags"], "H")
            self.assertIsNone(proof["whole_repository_history_complete"])
        self.assertEqual(manifest["production"], profile.PRODUCTION)

    def test_committed_oom_authorization_dependency_and_native_report_are_required(self):
        required = [("os", "kernel/asterinas/kernel/core/src/process/oom_adjustment.rs"),
                    ("os", "kernel/asterinas/kernel/core/src/process/namespace/user_ns.rs"),
                    ("hepta", "codex-rs/hepta-agentd/src/root_failure_report.rs")]
        for side, path in required:
            repo = getattr(self, side)
            original = (repo / path).read_bytes()
            (repo / path).unlink()
            fixtures.commit(repo, "remove a required V5 original owner")
            with self.subTest(path=path), self.assertRaisesRegex(profile.ProfileError, "required regular source file missing"):
                self.build()
            fixtures.write(repo, path, original)
            fixtures.commit(repo, "restore exact required V5 owner")

    def test_tracked_v5_map_cannot_be_replaced_even_when_caller_passes_the_reviewed_map(self):
        edited = copy.deepcopy(self.mapping)
        edited["sources"]["hepta"]["root_failure_report"] = "different/report.rs"
        fixtures.write(self.os, "support/release/organ_source_map_v5.json", profile.canonical(edited))
        fixtures.commit(self.os, "tamper with tracked V5 map")
        with self.assertRaisesRegex(profile.ProfileError, "checked-in schema5 map differs"):
            self.build()

    def test_current_reader_rejects_incomplete_rows_wrong_pin_shape_and_enabled_authority(self):
        manifest, _ = self.build()
        mutations = [lambda m: m["sources"]["os"].pop(),
                     lambda m: m["sources"]["hepta"].append(m["sources"]["hepta"][0]),
                     lambda m: m["goldens"].pop(),
                     lambda m: m["hepta"].update(commit="short"),
                     lambda m: m["production"].update(activation="enabled"),
                     lambda m: m["production"].update(effects_authorized=True),
                     lambda m: m.update(schema_version=4)]
        for index in range(7):
            mutations.append(lambda m, i=index: m["production"]["unconfigured"].pop(i))
        for index, mutate in enumerate(mutations):
            edited = copy.deepcopy(manifest)
            mutate(edited)
            with self.subTest(mutation=index), self.assertRaises(profile.ProfileError):
                profile.check_current_contract_v5(edited, self.mapping)

    def test_historical_v4_current_reader_remains_explicit_and_rejects_a_v5_declaration(self):
        manifest, _ = self.build()
        old_mapping = profile.load_json(HERE / "organ_source_map_v4.json")
        with self.assertRaisesRegex(profile.ProfileError, "requires schema4"):
            profile.check_current_contract(manifest, old_mapping)


class Schema5PairTests(unittest.TestCase):
    arguments = pair_tests.PairExecutionTests.arguments
    execute_fixture = pair_tests.PairExecutionTests.execute_fixture
    run_pair = pair_tests.PairExecutionTests.run_pair
    receipt = pair_tests.PairExecutionTests.receipt

    def setUp(self):
        pair_tests.PairExecutionTests.setUp(self)
        install(self, pair_tests.fixtures)
        with patch.object(runner.profile, "HISTORY_OWNER", self.owner):
            manifest, _ = runner.profile.create_manifest(*pair_tests.fixtures.SourceCombinationTests.inputs(self))
        self.manifest.write_bytes(runner.profile.canonical(manifest))

    def test_source_only_selects_fixed_v5_without_dispatch(self):
        with patch.object(runner, "execute_step", side_effect=AssertionError("unexpected child")):
            self.assertEqual(self.run_pair("--required-schema", "5"), 0)
        self.assertEqual(self.receipt()["qualification"], "source-only")
        self.assertEqual(self.receipt()["source"]["schema_version"], 5)
        self.assertEqual(self.receipt()["steps"], [])

    def test_owned_fixture_children_cover_nineteen_packages_and_all_seven_steps(self):
        with patch.object(runner, "execute_step", side_effect=self.execute_fixture):
            self.assertEqual(self.run_pair("--required-schema", "5", "--execute-host", "--offline"), 0)
        self.assertEqual([row[0] for row in self.dispatched], STEPS)
        expected = ["just", "test", "--locked", "--offline"] + [flag for package in PACKAGES for flag in ("-p", package)]
        self.assertEqual(self.dispatched[-1][3], expected + ["--test-threads", "2", "--retries", "0", "--cargo-profile", "dev-small"])
        self.assertEqual(self.receipt()["qualification"], "host-build-tests")  # Owned child fixture only.

    def test_failed_real_fixture_recovery_child_stops_before_owning_tests(self):
        self.fail_step = "hepta-recovery-build"
        with patch.object(runner, "execute_step", side_effect=self.execute_fixture):
            self.assertEqual(self.run_pair("--required-schema", "5", "--execute-host"), 1)
        self.assertEqual(self.dispatched[-1][0], "hepta-recovery-build")
        self.assertNotIn("hepta-tests", [row[0] for row in self.dispatched])
        self.assertEqual(self.receipt()["steps"][-1]["exit_code"], 13)
        self.assertEqual(self.receipt()["qualification"], "none")

    def test_current_v5_route_refuses_a_valid_historical_v4_before_any_child(self):
        install(self, pair_tests.fixtures, version=4)
        with patch.object(runner.profile, "HISTORY_OWNER", self.owner):
            old, _ = runner.profile.create_manifest(*pair_tests.fixtures.SourceCombinationTests.inputs(self))
        self.manifest.write_bytes(runner.profile.canonical(old))
        with patch.object(runner, "execute_step", side_effect=AssertionError("unverified child")):
            self.assertEqual(self.run_pair("--required-schema", "5", "--execute-host"), 1)
        self.assertFalse(self.output.exists())

    def test_manifest_cannot_inject_commands_packages_or_profiles(self):
        original = json.loads(self.manifest.read_text())
        for key, value in (("host_commands", [["/owned/unreviewed"]]), ("owning_packages", ["codex-hepta-agentd"]),
                           ("hepta_profile", "unlocked")):
            edited = copy.deepcopy(original)
            edited[key] = value
            self.manifest.write_bytes(runner.profile.canonical(edited))
            with self.subTest(injection=key), patch.object(runner, "execute_step", side_effect=AssertionError("unverified child")):
                self.assertEqual(self.run_pair("--required-schema", "5", "--execute-host"), 1)
            self.assertFalse(self.output.exists())


class Schema5WorkflowTests(unittest.TestCase):
    """Execute the real current YAML callers with owned Git/child fixtures."""
    execute_fixture = pair_tests.PairExecutionTests.execute_fixture
    run_ci_python = v4_tests.CurrentWorkflowTests.run_ci_python

    def setUp(self):
        pair_tests.PairExecutionTests.setUp(self)
        install(self, pair_tests.fixtures)
        paths = ["support/release/organ_release_profile.py", "support/release/check_organ_pair.py",
                 ".github/workflows/organ-current-pair.yml", ".github/workflows/organ-release-profile.yml",
                 "support/release/profiles/2026-10-27-organ-source-pre-v5-v4.json"]
        paths += ["support/release/" + profile.source_map_name(version) for version in range(1, 6)]
        for path in paths:
            pair_tests.fixtures.write(self.os, path, (HERE.parents[1] / path).read_bytes())
        pair_tests.fixtures.commit(self.os, "copy actual fixed V5 tools and current callers")
        self.manifest = self.os / "support/release/profiles/current-organ-source.json"
        self.publish_manifest(5)

    def publish_manifest(self, version):
        fx = pair_tests.fixtures
        mapping = runner.profile.load_json(HERE / runner.profile.source_map_name(version))
        with patch.object(runner.profile, "HISTORY_OWNER", self.owner):
            manifest, _ = runner.profile.create_manifest(
                runner.profile.Repository(self.os, "os"), runner.profile.Repository(self.hepta, "hepta"),
                fx.git(self.os, "rev-parse", "HEAD"), fx.git(self.os, "rev-parse", "HEAD^{tree}"),
                fx.git(self.hepta, "rev-parse", "HEAD"), fx.git(self.hepta, "rev-parse", "HEAD^{tree}"), mapping)
        fx.write(self.os, "support/release/profiles/current-organ-source.json", runner.profile.canonical(manifest))
        fx.commit(self.os, "publish a fixture source-only declaration with external OS binding")
        with patch.object(runner.profile, "HISTORY_OWNER", self.owner):
            runner.profile.verify_manifest(
                manifest, runner.profile.Repository(self.os, "os"), runner.profile.Repository(self.hepta, "hepta"),
                fx.git(self.os, "rev-parse", "HEAD"), fx.git(self.os, "rev-parse", "HEAD^{tree}"), mapping)
        return manifest

    def run_pin_reader(self):
        return self.run_ci_python(".github/workflows/organ-current-pair.yml", "Read the fixed V5 Hepta pin")

    def run_captured_pair(self, args):
        previous = Path.cwd()
        try:
            os.chdir(self.os)
            return runner.main(args)
        finally:
            os.chdir(previous)

    def current_ci_dispatch(self):
        helpers = self.root / "dispatch-helpers"
        helpers.mkdir()
        capture = self.root / "python-argv.json"
        executable = helpers / "python3"
        executable.write_text(f"#!{sys.executable}\nimport json, os, sys\n"
                              "with open(os.environ['FIXTURE_CAPTURE_ARGV'], 'x') as stream:\n"
                              "    json.dump(sys.argv[1:], stream)\n")
        executable.chmod(0o755)
        temporary = self.root / "runner-temp"
        temporary.mkdir()
        script = v4_tests.workflow_run_block(self.os / ".github/workflows/organ-current-pair.yml",
                                             "Build and test the fixed V5 original source pair")
        env = dict(os.environ, PATH=str(helpers) + os.pathsep + os.environ.get("PATH", ""),
                   FIXTURE_CAPTURE_ARGV=str(capture), GITHUB_WORKSPACE=str(self.root),
                   DESKTOP_SHA=pair_tests.fixtures.git(self.os, "rev-parse", "HEAD"), RUNNER_TEMP=str(temporary))
        subprocess.run(["bash", "-c", script], cwd=self.os, env=env, capture_output=True, check=True, timeout=30)
        args = json.loads(capture.read_text())
        self.assertEqual(args[:3], ["-I", "-B", "support/release/check_organ_pair.py"])
        self.assertEqual(args[args.index("--required-schema") + 1], "5")
        self.output = temporary / "organ-pair"
        return args[3:]

    def test_actual_current_pin_reader_emits_only_the_verified_v5_pin(self):
        result, output = self.run_pin_reader()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.read_text(), "hepta_sha=" + pair_tests.fixtures.git(self.hepta, "rev-parse", "HEAD") + "\n")
        self.publish_manifest(4)
        result, output = self.run_pin_reader()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())

    def test_actual_current_pin_reader_refuses_every_production_input_and_map_drift(self):
        original = self.manifest.read_bytes()
        mutations = [lambda m: m["production"].update(activation="enabled"),
                     lambda m: m["production"].update(effects_authorized=True),
                     lambda m: m.update(source_map_sha256="0" * 64)]
        mutations += [lambda m, i=i: m["production"]["unconfigured"].pop(i) for i in range(7)]
        for index, mutate in enumerate(mutations):
            manifest = json.loads(original)
            mutate(manifest)
            self.manifest.write_bytes(runner.profile.canonical(manifest))
            pair_tests.fixtures.commit(self.os, "reject an altered current declaration")
            result, output = self.run_pin_reader()
            with self.subTest(mutation=index):
                self.assertNotEqual(result.returncode, 0)
                self.assertFalse(output.exists())
        self.manifest.write_bytes(original)
        mapping = copy.deepcopy(self.mapping)
        mapping["sources"]["os"]["release_schema5_oracle"] = "other/oracle.py"
        pair_tests.fixtures.write(self.os, "support/release/organ_source_map_v5.json", profile.canonical(mapping))
        pair_tests.fixtures.commit(self.os, "alter the fixed current map")
        result, output = self.run_pin_reader()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())

    def test_actual_current_source_guard_checks_all_five_maps_and_rejects_activation(self):
        workflow = ".github/workflows/organ-release-profile.yml"
        step = "Require inputs and validate the fixed V5 contract"
        result, _ = self.run_ci_python(workflow, step)
        self.assertEqual(result.returncode, 0, result.stderr)
        for version in range(1, 6):
            self.assertIn(f"Committed map schema {version} passed:", result.stdout)
        self.assertIn("Committed current fixed schema5 contract passed.", result.stdout)
        manifest = json.loads(self.manifest.read_text())
        manifest["production"]["activation"] = "enabled"
        self.manifest.write_bytes(runner.profile.canonical(manifest))
        pair_tests.fixtures.commit(self.os, "refuse a production-enabled current declaration")
        result, _ = self.run_ci_python(workflow, step)
        self.assertNotEqual(result.returncode, 0)

    def test_actual_current_dispatch_runs_seven_bounded_children_and_all_nineteen_owners(self):
        args = self.current_ci_dispatch()
        with patch.object(runner.profile, "HISTORY_OWNER", self.owner), patch.object(
                runner, "execute_step", side_effect=self.execute_fixture):
            self.assertEqual(self.run_captured_pair(args), 0)
        receipt = json.loads((self.output / "pair-receipt.json").read_text())
        self.assertEqual(receipt["source"]["schema_version"], 5)
        self.assertEqual(receipt["qualification"], "host-build-tests")  # Owned fixture children only.
        self.assertEqual([row[0] for row in self.dispatched], STEPS)
        argv = self.dispatched[-1][3]
        self.assertEqual([argv[i + 1] for i, value in enumerate(argv) if value == "-p"], PACKAGES)

    def test_actual_current_dispatch_rejects_valid_historical_v4_before_any_child(self):
        self.publish_manifest(4)
        args = self.current_ci_dispatch()
        with patch.object(runner.profile, "HISTORY_OWNER", self.owner), patch.object(
                runner, "execute_step", side_effect=AssertionError("historical declaration executed")):
            self.assertEqual(self.run_captured_pair(args), 1)
        self.assertFalse(self.output.exists())


if __name__ == "__main__":
    unittest.main()
