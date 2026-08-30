from __future__ import annotations

from contextlib import redirect_stderr
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_governance_integrity_under_test",
    ROOT / "tools/validate_governance_integrity.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VALIDATOR
SPEC.loader.exec_module(VALIDATOR)


class StrictYamlParserTests(unittest.TestCase):
    def assert_rejected(self, source: str) -> None:
        with self.assertRaises(VALIDATOR.YamlParseError):
            VALIDATOR.parse_yaml_strict(source, source="fixture.yml")

    def test_duplicate_block_and_flow_keys_are_rejected(self) -> None:
        self.assert_rejected("permissions:\n  contents: read\n  contents: none\n")
        self.assert_rejected("permissions: {contents: read, contents: none}\n")
        self.assert_rejected("'permissions': read\npermissions: none\n")

    def test_alias_merge_anchor_and_tag_syntax_is_rejected(self) -> None:
        for source in (
            "defaults: &defaults\n  run: echo ok\n",
            "defaults: *defaults\n",
            "defaults:\n  <<: *defaults\n",
            "value: !!str read\n",
        ):
            with self.subTest(source=source):
                self.assert_rejected(source)

    def test_flow_style_and_quoted_keys_are_normalized(self) -> None:
        model = VALIDATOR.parse_yaml_strict(
            "'on': [pull_request, push]\n"
            "permissions: { 'contents': read }\n"
            "jobs: {build: {steps: [{uses: 'actions/checkout@aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'}]}}\n",
            source="fixture.yml",
        )
        self.assertEqual(model["on"], ["pull_request", "push"])
        self.assertEqual(model["permissions"], {"contents": "read"})
        self.assertEqual(model["jobs"]["build"]["steps"][0]["uses"], "actions/checkout@" + "a" * 40)

    def test_expression_operators_are_not_mistaken_for_anchors(self) -> None:
        model = VALIDATOR.parse_yaml_strict(
            "env:\n  ROLE: ${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}\n",
            source="fixture.yml",
        )
        self.assertIn("&&", model["env"]["ROLE"])


class GovernanceModelTests(unittest.TestCase):
    SHA = "a" * 40

    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.old_root = VALIDATOR.ROOT
        VALIDATOR.ROOT = self.root

    def tearDown(self) -> None:
        VALIDATOR.ROOT = self.old_root
        self.temporary.cleanup()

    def workflow(self, **changes):
        model = {
            "name": "fixture",
            "on": {"pull_request": {"branches": ["main"]}},
            "permissions": {"contents": "read"},
            "jobs": {
                "build": {
                    "name": "build",
                    "steps": [
                        {
                            "name": "checkout",
                            "uses": f"actions/checkout@{self.SHA}",
                            "with": {"persist-credentials": False},
                        },
                        {"run": "printf 'ok\\n'"},
                    ],
                }
            },
        }
        model.update(changes)
        return model

    def reject(self, model, name="fixture.yml"):
        path = self.root / name
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            VALIDATOR.validate_workflow(path, model)

    def test_flow_write_permission_is_rejected(self) -> None:
        model = self.workflow(permissions={"contents": "write"})
        self.reject(model)

    def test_pull_request_target_is_rejected_even_in_flow_form(self) -> None:
        model = self.workflow(**{"on": ["pull_request_target"]})
        self.reject(model)

    def test_mutable_and_compact_action_references_are_rejected(self) -> None:
        for value in (
            "actions/checkout@main",
            "actions/checkout@v4",
            "actions/checkout@" + "A" * 40,
        ):
            with self.subTest(value=value):
                model = self.workflow(
                    jobs={
                        "build": {
                            "steps": [
                                {
                                    "uses": value,
                                    "with": {"persist-credentials": False},
                                }
                            ]
                        }
                    }
                )
                self.reject(model)

    def test_checkout_must_explicitly_drop_credentials(self) -> None:
        model = self.workflow(
            jobs={
                "build": {
                    "steps": [
                        {"uses": f"actions/checkout@{self.SHA}", "with": {}}
                    ]
                }
            }
        )
        self.reject(model)
        for value in (0, 1, "False", "TRUE"):
            with self.subTest(value=value):
                model = self.workflow(
                    jobs={
                        "build": {
                            "steps": [
                                {
                                    "uses": f"actions/checkout@{self.SHA}",
                                    "with": {"persist-credentials": value},
                                }
                            ]
                        }
                    }
                )
                self.reject(model)

    def test_checkout_owner_case_cannot_bypass_credential_guard(self) -> None:
        model = self.workflow(
            jobs={
                "build": {
                    "steps": [
                        {
                            "uses": f"Actions/Checkout@{self.SHA}",
                            "with": {},
                        }
                    ]
                }
            }
        )
        self.reject(model)

    def test_conditional_jobs_and_steps_are_limited_to_diagnostics(self) -> None:
        for condition in (
            False,
            True,
            "false",
            "always()",
            "failure()",
            "${{ github.event_name == 'push' }}",
        ):
            with self.subTest(condition=condition):
                model = self.workflow(
                    jobs={
                        "build": {
                            "if": condition,
                            "steps": [{"run": "printf 'ok\\n'"}],
                        }
                    }
                )
                self.reject(model)
        for condition in ("always()", "failure()"):
            with self.subTest(condition=condition):
                model = self.workflow(
                    jobs={
                        "build": {
                            "steps": [
                                {
                                    "if": condition,
                                    "name": "Upload bounded diagnostic artifact",
                                    "uses": f"actions/upload-artifact@{self.SHA}",
                                }
                            ],
                        }
                    }
                )
                VALIDATOR.validate_workflow(self.root / "fixture.yml", model)
        self.reject(
            self.workflow(
                jobs={
                    "build": {
                        "steps": [
                            {
                                "if": "always()",
                                "name": "Run required gate",
                                "run": "printf 'gate\\n'",
                            }
                        ]
                    }
                }
            )
        )

    def test_local_node_and_docker_actions_are_rejected_without_runtime_scanner(
        self,
    ) -> None:
        for using, metadata in (
            ("node20", "  main: index.js\n"),
            ("docker", "  image: Dockerfile\n"),
        ):
            with self.subTest(using=using):
                action = self.root / ".github/actions/local"
                action.mkdir(parents=True)
                (action / "action.yml").write_text(
                    "name: local\n"
                    "runs:\n"
                    f"  using: {using}\n"
                    + metadata,
                    encoding="utf-8",
                )
                if using.startswith("node"):
                    (action / "index.js").write_text(
                        "require('child_process').exec('git push')\n",
                        encoding="utf-8",
                    )
                model = self.workflow(
                    jobs={"build": {"steps": [{"uses": "./.github/actions/local"}]}}
                )
                self.reject(model)
                import shutil

                shutil.rmtree(action)

    def test_git_and_github_mutation_forms_are_rejected(self) -> None:
        commands = (
            "git -C . push origin main",
            "git update-ref refs/heads/main deadbeef",
            "gh api --method POST https://api.github.com/repos/example/repo",
            "curl --request POST https://api.github.com/repos/example/repo",
            "requests.post('https://api.github.com/repos/example/repo')",
            "subprocess.run(['git', 'push', 'origin', 'main'])",
        )
        for command in commands:
            with self.subTest(command=command):
                model = self.workflow(jobs={"build": {"steps": [{"run": command}]}})
                self.reject(model)

    def test_path_qualified_case_insensitive_git_and_helper_mutations_are_rejected(
        self,
    ) -> None:
        commands = (
            "/usr/bin/git push origin main",
            "GIT -C . PUSH origin main",
            "git.exe --git-dir /tmp/repo push origin main",
            "/usr/libexec/git-receive-pack repo.git",
            "git-upload-pack repo.git",
            "subprocess.run(['/usr/bin/git', '-C', '.', 'push', 'origin', 'main'])",
            "subprocess.call(['GIT.EXE', '--git-dir', '/tmp/repo', 'PUSH'])",
            "subprocess.Popen(['git-receive-pack', 'repo.git'])",
            "os.system('git -C . push origin main')",
            'system("/usr/bin/git --git-dir /tmp/repo update-ref refs/heads/main deadbeef")',
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(VALIDATOR._contains_mutation(command))
                model = self.workflow(jobs={"build": {"steps": [{"run": command}]}})
                self.reject(model)

    def test_dynamic_shell_git_mutation_forms_are_rejected(self) -> None:
        commands = (
            "x=git; $x push origin main",
            "g=/usr/bin/git; ${g} --git-dir /tmp/repo push origin main",
            "git push${IFS}origin${IFS}main",
            "git\n push origin main",
            "git -C .\n push origin main",
            "bash -c 'x=git; $x push origin main'",
            "bash -c 'git\n push origin main'",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertTrue(VALIDATOR._contains_mutation(command))
                model = self.workflow(jobs={"build": {"steps": [{"run": command}]}})
                self.reject(model)
        for command in (
            "x=git; $x status --short",
            "git fetch${IFS}origin${IFS}main",
        ):
            with self.subTest(command=command):
                self.assertFalse(VALIDATOR._contains_mutation(command))

    def test_tokenized_read_only_git_and_python_calls_remain_allowed(self) -> None:
        commands = (
            "/usr/bin/git -C . fetch --no-tags origin main",
            "GIT.EXE --git-dir /tmp/repo STATUS --short",
            "subprocess.run(['/usr/bin/git', '--git-dir', '/tmp/repo', 'status'])",
            "subprocess.check_call(['git', 'log', '--oneline'])",
            "os.system('git log --oneline')",
        )
        for command in commands:
            with self.subTest(command=command):
                self.assertFalse(VALIDATOR._contains_mutation(command))
                model = self.workflow(jobs={"build": {"steps": [{"run": command}]}})
                VALIDATOR.validate_workflow(self.root / "fixture.yml", model)

    def test_required_gate_commands_must_not_be_comments_or_echo_arguments(self) -> None:
        source = (ROOT / ".github/workflows/governance-integrity.yml").read_text(
            encoding="utf-8"
        )
        model = VALIDATOR.parse_yaml_strict(source, source="governance-integrity.yml")
        run = "\n".join(
            [
                "# python3 tools/validate_governance_integrity.py",
                "# python3 tools/validate_repository.py",
                "# python3 tools/validate_project_truth.py",
                "# cargo fmt --all --check",
                "# cargo check --workspace --all-targets --locked",
                "# cargo clippy --workspace --all-targets --locked -- -D warnings",
                "# cargo test --workspace --all-targets --locked",
            ]
        )
        model["jobs"]["governance_integrity"]["steps"] = [{"run": run}]
        self.reject(model, name="governance-integrity.yml")
        model["jobs"]["governance_integrity"]["steps"] = [
            {"run": "echo python3 tools/validate_governance_integrity.py"}
        ]
        self.reject(model, name="governance-integrity.yml")
        model["jobs"]["governance_integrity"]["steps"] = [
            {
                "if": "always()",
                "name": "Collect diagnostic output",
                "run": "python3 tools/validate_governance_integrity.py",
            }
        ]
        self.reject(model, name="governance-integrity.yml")

    def test_required_gate_shell_wrapper_handles_long_command_tokens(self) -> None:
        command = "cargo clippy --workspace --all-targets --locked -- -D warnings"
        wrapped = "bash -c '" + command + "'"
        self.assertTrue(VALIDATOR._has_command_invocation([wrapped], command))
        self.assertFalse(
            VALIDATOR._has_command_invocation(["echo '" + command + "'"], command)
        )

    def test_read_only_git_commands_remain_allowed(self) -> None:
        model = self.workflow(
            jobs={"build": {"steps": [{"run": "git -C . fetch --no-tags origin main"}]}}
        )
        VALIDATOR.validate_workflow(self.root / "fixture.yml", model)

    def test_local_reusable_workflow_is_path_checked(self) -> None:
        workflows = self.root / ".github/workflows"
        workflows.mkdir(parents=True)
        local = workflows / "safe.yml"
        local.write_text(
            "name: safe\n"
            "on: {workflow_call: {}}\n"
            "permissions: {contents: read}\n"
            "jobs: {safe: {steps: [{run: echo ok}]}}\n",
            encoding="utf-8",
        )
        model = self.workflow(
            jobs={"call": {"uses": "./.github/workflows/safe.yml"}}
        )
        # The reference is accepted only after lexical/path validation.  The
        # caller's job still has no executable steps because it is reusable.
        VALIDATOR.validate_workflow(self.root / "fixture.yml", model)
        self.reject(
            self.workflow(jobs={"call": {"uses": "./.github/workflows/../evil.yml"}})
        )
        for unsafe in (
            "./.github/workflows//safe.yml",
            "./.github/workflows/./safe.yml",
            "./.github/workflows/safe.yml/",
        ):
            with self.subTest(unsafe=unsafe):
                self.reject(self.workflow(jobs={"call": {"uses": unsafe}}))

    def test_remote_reusable_workflow_reference_has_exact_path_shape(self) -> None:
        valid = f"owner/repository/.github/workflows/gate.yml@{self.SHA}"
        VALIDATOR._validate_uses(
            valid,
            workflow_path=self.root / "fixture.yml",
            reusable=True,
            location="job call",
        )
        for value in (
            f"owner/repository/.github/workflows/nested/gate.yml@{self.SHA}",
            f"owner/repository/.github/workflows/gate.yml/extra@{self.SHA}",
        ):
            with self.subTest(value=value), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                VALIDATOR._validate_uses(
                    value,
                    workflow_path=self.root / "fixture.yml",
                    reusable=True,
                    location="job call",
                )

    def test_local_composite_action_is_followed_for_mutations(self) -> None:
        action = self.root / ".github/actions/local"
        action.mkdir(parents=True)
        (action / "action.yml").write_text(
            "name: local\n"
            "runs:\n"
            "  using: composite\n"
            "  steps:\n"
            "    - run: git -C . push origin main\n",
            encoding="utf-8",
        )
        model = self.workflow(
            jobs={
                "build": {
                    "steps": [
                        {"uses": "./.github/actions/local"},
                    ]
                }
            }
        )
        self.reject(model)

    def test_governance_workflow_is_unconditional_and_runs_all_gates(self) -> None:
        source = (ROOT / ".github/workflows/governance-integrity.yml").read_text(
            encoding="utf-8"
        )
        model = VALIDATOR.parse_yaml_strict(source, source="governance-integrity.yml")
        path = self.root / "governance-integrity.yml"
        VALIDATOR.validate_workflow(path, model)

        missing = {
            **model,
            "jobs": {
                "governance_integrity": {
                    **model["jobs"]["governance_integrity"],
                    "steps": [{"run": "true"}],
                }
            },
        }
        self.reject(missing, name="governance-integrity.yml")

        target = {**model, "on": ["pull_request_target"]}
        self.reject(target, name="governance-integrity.yml")

        write = {**model, "permissions": {"contents": "write"}}
        self.reject(write, name="governance-integrity.yml")

    def test_root_probe_is_a_hard_failure(self) -> None:
        probe = self.root / "__probe__"
        probe.write_text("residue", encoding="utf-8")
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            VALIDATOR.assert_source_inventory()

    def test_root_inventory_rejects_unregistered_files(self) -> None:
        for name in VALIDATOR.EXPECTED_ROOT_FILES:
            (self.root / name).write_text("fixture", encoding="utf-8")
        (self.root / "unexpected.txt").write_text("residue", encoding="utf-8")
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            VALIDATOR.assert_source_inventory()

    def test_codeowners_required_paths_and_identities_are_fail_closed(self) -> None:
        (self.root / ".github").mkdir()
        (self.root / "manifests").mkdir()
        (self.root / ".github/CODEOWNERS").write_text(
            "* @Tomasrgbsf @ProfHepta\n", encoding="utf-8"
        )
        manifest = json.loads(
            (ROOT / "manifests/repository-governance.v1.json").read_text(
                encoding="utf-8"
            )
        )
        (self.root / "manifests/repository-governance.v1.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            VALIDATOR._validate_codeowners_source()

    def test_manifest_contract_parity_is_fail_closed(self) -> None:
        manifests = self.root / "manifests"
        manifests.mkdir()
        manifest = json.loads(
            (ROOT / "manifests/repository-governance.v1.json").read_text(
                encoding="utf-8"
            )
        )
        contract = json.loads(
            (ROOT / "contracts/repository-governance.v1.json").read_text(
                encoding="utf-8"
            )
        )
        contract["dynamic_acceptance_required"] = contract[
            "dynamic_acceptance_required"
        ][:-1]
        (manifests / "repository-governance.v1.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        old_root = VALIDATOR.ROOT
        VALIDATOR.ROOT = self.root
        try:
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                VALIDATOR._validate_manifest_parity(contract)
        finally:
            VALIDATOR.ROOT = old_root

    def test_manifest_policy_sections_must_match_contract(self) -> None:
        manifests = self.root / "manifests"
        manifests.mkdir()
        manifest = json.loads(
            (ROOT / "manifests/repository-governance.v1.json").read_text(
                encoding="utf-8"
            )
        )
        contract = json.loads(
            (ROOT / "contracts/repository-governance.v1.json").read_text(
                encoding="utf-8"
            )
        )
        (manifests / "repository-governance.v1.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        old_root = VALIDATOR.ROOT
        VALIDATOR.ROOT = self.root
        try:
            for section in ("actions", "release"):
                mutated = json.loads(json.dumps(contract))
                key = next(iter(mutated[section]))
                value = mutated[section][key]
                mutated[section][key] = not value if isinstance(value, bool) else "mutated"
                with self.subTest(section=section), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                    VALIDATOR._validate_manifest_parity(mutated)
            mutated = json.loads(json.dumps(contract))
            mutated["main_branch"]["linear_history_required"] = False
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                VALIDATOR._validate_manifest_parity(mutated)
        finally:
            VALIDATOR.ROOT = old_root

    def test_contract_policy_booleans_require_json_boolean_types(self) -> None:
        contract = json.loads(
            (ROOT / "contracts/repository-governance.v1.json").read_text(
                encoding="utf-8"
            )
        )
        contract["main_branch"]["pull_request_required"] = 1
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            VALIDATOR._validate_contract(contract)

    def test_manifest_main_branch_rejects_extra_policy_keys(self) -> None:
        manifests = self.root / "manifests"
        manifests.mkdir()
        manifest = json.loads(
            (ROOT / "manifests/repository-governance.v1.json").read_text(
                encoding="utf-8"
            )
        )
        manifest["main_branch"]["unexpected_bypass"] = True
        (manifests / "repository-governance.v1.json").write_text(
            json.dumps(manifest), encoding="utf-8"
        )
        contract = json.loads(
            (ROOT / "contracts/repository-governance.v1.json").read_text(
                encoding="utf-8"
            )
        )
        old_root = VALIDATOR.ROOT
        VALIDATOR.ROOT = self.root
        try:
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                VALIDATOR._validate_manifest_parity(contract)
        finally:
            VALIDATOR.ROOT = old_root

    def test_workflow_inventory_rejects_nested_or_unregistered_workflows(self) -> None:
        workflows = self.root / ".github/workflows"
        workflows.mkdir(parents=True)
        workflow = workflows / "only.yml"
        workflow.write_text("name: only\n", encoding="utf-8")
        old_root = VALIDATOR.ROOT
        old_workflow_root = VALIDATOR.WORKFLOW_ROOT
        old_registry = VALIDATOR.EXPECTED_REQUIRED_WORKFLOWS
        VALIDATOR.ROOT = self.root
        VALIDATOR.WORKFLOW_ROOT = workflows
        VALIDATOR.EXPECTED_REQUIRED_WORKFLOWS = (".github/workflows/only.yml",)
        try:
            self.assertEqual(VALIDATOR._workflow_inventory(), [workflow])
            nested = workflows / "nested"
            nested.mkdir()
            (nested / "extra.yml").write_text("name: extra\n", encoding="utf-8")
            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                VALIDATOR._workflow_inventory()
        finally:
            VALIDATOR.ROOT = old_root
            VALIDATOR.WORKFLOW_ROOT = old_workflow_root
            VALIDATOR.EXPECTED_REQUIRED_WORKFLOWS = old_registry


class RealTreeRegressionTests(unittest.TestCase):
    def test_real_tree_governance_gate_passes(self) -> None:
        self.assertEqual(VALIDATOR.main(), 0)


if __name__ == "__main__":
    unittest.main()
