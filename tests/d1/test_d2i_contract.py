from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import finalize_d1_evidence  # noqa: E402


class D2IContractTests(unittest.TestCase):
    def test_contract_keeps_candidate_and_promotion_claims_separate(self) -> None:
        contract = json.loads(
            (ROOT / "contracts/d2i-integrated-image.v1.json").read_text()
        )
        self.assertEqual(
            contract["status"],
            "IMPLEMENTED_CANDIDATE_REQUIRES_MACHINE_EVIDENCE",
        )
        self.assertTrue(contract["image"]["byte_for_byte_equality_required"])
        self.assertEqual(contract["boot"]["network"], "none")
        self.assertTrue(contract["boot"]["product_agent_port_default_disabled"])
        ceiling = contract["claim_ceiling"]
        self.assertFalse(ceiling["actual_content_process_crash_currently_proven"])
        self.assertFalse(ceiling["release_readiness"])
        self.assertTrue(
            contract["claim_ceiling"][
                "actual_content_process_crash_can_be_proven_without_callback"
            ]
        )
        self.assertFalse(contract["runtime"]["servo_crash_callback_required"])
        self.assertEqual(
            contract["runtime"]["fault_mechanism"],
            "external SIGKILL of exact PID/start-time identity",
        )
        self.assertTrue(contract["runtime"]["zero_process_intermediate_required"])
        self.assertTrue(contract["runtime"]["distinct_replacement_identity_required"])
        for token in (
            "sigkill_success_bound_to_exact_pid_start_time",
            "old_identity_absent",
            "zero_process_intermediate",
            "distinct_replacement_identity",
        ):
            self.assertIn(token, contract["promotion_requires"])
        self.assertNotIn(
            "actual_content_process_crash_callback_observed",
            contract["promotion_requires"],
        )
        self.assertIn("exact_main_rerun_after_merge", contract["promotion_requires"])

    def test_contract_and_workflows_reject_repository_mutation_variants(self) -> None:
        contract = json.loads(
            (ROOT / "contracts/d2i-integrated-image.v1.json").read_text()
        )
        policy = contract["source_binding"]["workflow_mutation_policy"]
        self.assertFalse(policy["repository_write"])
        self.assertEqual(
            policy["repository_write_scope"],
            "remote_or_protected_source_and_promotion_refs",
        )
        self.assertTrue(policy["ephemeral_checkout_fetch_allowed"])
        self.assertEqual(
            set(policy["forbidden_git_operations"]),
            {
                "push",
                "update-ref",
                "receive-pack",
                "git-push",
                "git-update-ref",
                "git-receive-pack",
            },
        )
        self.assertEqual(
            policy["scanner"],
            "tools/finalize_d1_evidence.py:workflow_contains_git_mutation",
        )
        self.assertEqual(
            policy["permanent_scanner"],
            "tools/validate_governance_integrity.py:_contains_mutation",
        )
        self.assertTrue(policy["dynamic_forms_fail_closed"])
        self.assertEqual(
            set(policy["forbidden_dynamic_forms"]),
            {
                "shell_dynamic_git_subcommand_or_executable",
                "shell_array_alias_function_or_sourced_command",
                "shell_process_substitution_or_unquoted_heredoc_expansion",
                "shell_dynamic_github_cli_or_http_method",
                "python_dynamic_process_or_http_method",
                "python_exec_spawn_or_wrapper_command_graph",
            },
        )
        self.assertIn(
            "permanent_workflow_repository_mutation_scan",
            contract["promotion_requires"],
        )
        d1_workflow = (
            ROOT / ".github/workflows/d1-final-qualification.yml"
        ).read_text()
        d2i_workflow = (ROOT / ".github/workflows/d2i-integrated-image.yml").read_text()
        self.assertFalse(finalize_d1_evidence.workflow_contains_git_mutation(d1_workflow))
        self.assertFalse(finalize_d1_evidence.workflow_contains_git_mutation(d2i_workflow))
        for variant in (
            "git -C /tmp/repo push origin main",
            "git -C /tmp/repo update-ref refs/heads/main HEAD",
            "git -C /tmp/repo receive-pack /tmp/incoming",
            "/usr/libexec/git-core/git-receive-pack /tmp/repo",
        ):
            self.assertTrue(
                finalize_d1_evidence.workflow_contains_git_mutation(variant),
                variant,
            )

    def test_guest_runtime_is_networkless_and_unprivileged(self) -> None:
        service = (
            ROOT
            / "packaging/debian/image/d2i-overlay/etc/systemd/system/trillionnium-d2i-runtime.service"
        ).read_text()
        runtime = (
            ROOT / "experiments/servo-headed-runtime/src/main.rs"
        ).read_text()
        self.assertIn("User=hepta-desktop", service)
        self.assertIn("PrivateNetwork=yes", service)
        self.assertIn(
            "RestrictAddressFamilies=AF_UNIX AF_INET AF_INET6",
            service,
        )
        self.assertIn("127.0.0.1", runtime)
        self.assertIn("WAYLAND_DISPLAY=wayland-0", service)
        self.assertIn("HEPTA_D0A02_OUTPUT=/var/lib/trillionnium-d2i", service)
        self.assertIn("Type=simple", service)
        self.assertIn("HEPTA_D2I_HOLD_AFTER_RESULT=1", service)

    def test_external_fault_injector_is_single_and_runtime_is_observer_only(self) -> None:
        contract = json.loads(
            (ROOT / "contracts/d2i-integrated-image.v1.json").read_text()
        )
        self.assertEqual(contract["fault_injection"]["mechanism"], "external-systemd-helper")
        self.assertEqual(contract["fault_injection"]["injector_count"], 1)
        self.assertFalse(contract["fault_injection"]["runtime_internal_injector"])
        topology = contract["fault_injection"]["topology_proof"]
        self.assertTrue(topology["content_process_direct_child"])
        self.assertEqual(topology["intermediate_processes"], 0)
        self.assertEqual(topology["pre_fault_active_content_processes"], 1)
        self.assertEqual(topology["post_termination_active_content_processes"], 0)
        self.assertEqual(topology["post_recovery_active_content_processes"], 1)
        legacy_runtime = ROOT / "runtime/servo/hepta_workspace_runtime.rs"
        self.assertFalse(
            legacy_runtime.exists(),
            "superseded runtime source must not reintroduce an in-process injector",
        )
        runtime_readme = (ROOT / "runtime/README.md").read_text()
        self.assertIn("experiments/servo-headed-runtime/src/main.rs", runtime_readme)
        self.assertIn("runtime_internal_injector: false", runtime_readme)
        headed_readme = (ROOT / "experiments/servo-headed-runtime/README.md").read_text()
        self.assertIn("may surface `notify_crashed`", headed_readme)
        self.assertIn("not required for the external", headed_readme)
        self.assertNotIn("must then surface `notify_crashed`", headed_readme)
        runtime = (
            ROOT / "experiments/servo-headed-runtime/src/main.rs"
        ).read_text()
        self.assertNotIn('Command::new("/bin/kill")', runtime)
        self.assertNotIn("kill -KILL", runtime)
        self.assertIn("content-crash-ready", runtime)
        self.assertIn("content-sigkill-sent.json", runtime)
        injector = (
            ROOT
            / "packaging/debian/image/d2i-overlay/usr/local/libexec/trillionnium-d2i-content-crash-proof"
        ).read_text()
        self.assertEqual(injector.count("kill -KILL"), 1)
        # The guest D2I helper runs in a minimal D1 image whose package lock
        # intentionally does not include jq; keep parsing POSIX-only and avoid
        # introducing an undeclared runtime dependency.
        self.assertNotIn("jq", injector)
        self.assertIn("sed -n", injector)
        self.assertIn("proc_candidate_pids", injector)
        self.assertNotIn("children_of", injector)
        self.assertIn("direct PPID", injector)
        self.assertIn("runtime_exited_before_arm", injector)
        self.assertIn("injector_count", injector)
        self.assertIn("mktemp \"$state_dir/.content-sigkill-sent.XXXXXX\"", injector)
        self.assertIn("mktemp \"$state_dir/.content-process-crash-proof.XXXXXX\"", injector)
        self.assertIn("proc_start_time", injector)
        self.assertIn("zero_process_intermediate_topology", injector)
        self.assertIn("pre_fault_direct_child", injector)
        self.assertIn("post_termination_active_content_processes", injector)
        self.assertIn("post_recovery_active_content_processes", injector)
        self.assertIn("post_recovery_direct_child", injector)
        self.assertNotIn('tmp="$receipt.tmp.$$"', injector)
        self.assertNotIn('tmp="$proof.tmp.$$"', injector)
        service = (
            ROOT
            / "packaging/debian/image/d2i-overlay/etc/systemd/system/trillionnium-d2i-content-crash-proof.service"
        ).read_text()
        self.assertIn("StandardOutput=journal+console", service)
        self.assertIn("StandardError=journal+console", service)

    def test_host_gate_binds_same_image_and_no_network_qemu(self) -> None:
        prepare = (ROOT / "tests/qemu/prepare-d2i-image.sh").read_text()
        boot = (ROOT / "tests/qemu/run-d2i-boot-test.sh").read_text()
        workflow = (ROOT / ".github/workflows/d2i-integrated-image.yml").read_text()
        contract = json.loads(
            (ROOT / "contracts/d2i-integrated-image.v1.json").read_text()
        )
        self.assertIn("PASS_DETERMINISTIC_INPUT_INJECTION", prepare)
        self.assertIn("E2FSPROGS_FAKE_TIME", prepare)
        self.assertIn("-nic none", boot)
        self.assertIn("trillionnium-d2i-acceptance.target", boot)
        self.assertIn("cmp -s", workflow)
        self.assertIn("run-d1-pipeline.sh", workflow)
        self.assertIn("run-d2i-boot-test.sh", workflow)
        self.assertIn("--no-default-features", workflow)
        self.assertIn("--bin hepta-agent-portd", workflow)
        self.assertIn("test -x target/release/hepta-agent-portd", workflow)
        self.assertIn("actual_content_process_crash_proven", workflow)
        self.assertIn(
            "PASS_EXTERNAL_CONTENT_PROCESS_TERMINATION_AND_RECOVERY",
            workflow,
        )
        for token in (
            "sigkill_delivered",
            "killed_pid_disappeared",
            "killed_content_pid",
            "killed_content_start_time_ticks",
            "zero_process_intermediate_topology",
            "replacement_content_pid",
            "replacement_content_start_time_ticks",
            "runtime_replacement",
            "distinct_from_fault_target",
            "causal_crash_proof",
            "servo_crash_callback_required",
            "servo_crash_callback_observed",
        ):
            self.assertIn(token, workflow)
        self.assertNotIn(
            "actual_content_process_crash_callback_observed",
            workflow,
        )
        self.assertIn("PASS_CANDIDATE_REQUIRES_REVIEW_AND_EXACT_MAIN", workflow)
        for blocker in (
            "digest_bound_machine_evidence_committed",
            "independent_review",
            "protected_main",
            "exact_main_rerun_after_merge",
        ):
            self.assertIn(blocker, workflow)
            self.assertIn(blocker, contract["promotion_requires"])
        self.assertIn("Verify exact candidate topology and base", workflow)
        self.assertIn("git fetch --no-tags origin main", workflow)
        self.assertIn('current_main="$(git rev-parse origin/main)"', workflow)
        self.assertIn(
            '[[ "${parents[0]}" == "$current_main" ]]',
            workflow,
        )
        self.assertIn(
            "merge first parent is not the current origin/main object",
            workflow,
        )
        self.assertIn('[[ "$tested_sha" == "$current_main" ]]', workflow)
        self.assertIn(
            "D2I tested push object is not the current origin/main object",
            workflow,
        )
        self.assertIn(
            'git merge-base --is-ancestor "$EVENT_BEFORE" "${parents[0]}"',
            workflow,
        )
        self.assertNotIn(
            'main push parent does not equal event.before',
            workflow,
        )
        self.assertIn("branches: [main]", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertNotIn("git push", workflow)
        self.assertNotIn("paths:", workflow)
        self.assertIn("experiments/servo-headed-runtime/src/main.rs", workflow)
        self.assertIn("packaging/debian/image/d2i-overlay", workflow)
        self.assertIn(
            "promotion_authoritative=(event_name == 'push')",
            workflow,
        )
        self.assertIn("collect_guest_diagnostics", boot)
        self.assertIn("guest-failure-diagnostics.txt", boot)
        host_gate = (ROOT / "tools/run_servo_headed_runtime_gate.sh").read_text()
        self.assertEqual(
            host_gate.count("inject_servo_content_process.py"),
            1,
        )
        self.assertIn("external-injector.log", host_gate)

    def test_image_preparation_normalizes_ext4_mutation_metadata(self) -> None:
        """Repeated D2I preparations must not retain host-clock ext4 fields."""

        prepare = (ROOT / "tests/qemu/prepare-d2i-image.sh").read_text()
        contract = json.loads(
            (ROOT / "contracts/d2i-integrated-image.v1.json").read_text()
        )
        normalization = contract["image"]["metadata_normalization"]
        self.assertIs(type(normalization["bound_to_source_date_epoch"]), bool)
        self.assertTrue(normalization["bound_to_source_date_epoch"])
        self.assertIs(type(normalization["source_date_epoch_min"]), int)
        self.assertIs(type(normalization["source_date_epoch_max"]), int)
        self.assertEqual(normalization["source_date_epoch_min"], 1)
        self.assertEqual(normalization["source_date_epoch_max"], 4294967295)
        self.assertEqual(
            normalization["injected_inode_times"],
            ["atime", "ctime", "mtime", "crtime"],
        )
        self.assertTrue(normalization["injected_inode_generations"])
        self.assertEqual(
            normalization["parent_directory_times"],
            ["atime", "ctime", "mtime"],
        )
        self.assertEqual(
            normalization["superblock_times"],
            ["mtime", "wtime", "lastcheck", "mkfs_time"],
        )
        self.assertEqual(normalization["superblock_kbytes_written"], 0)
        self.assertIn("dumpe2fs", prepare)
        for path in (
            "/usr/libexec",
            "/etc/systemd/system",
            "/usr/local/libexec",
            "/usr/lib/trillionnium-d1",
        ):
            with self.subTest(parent_directory=path):
                self.assertIn(path, prepare)
        for token in (
            'for index in "${!injected_paths[@]}"',
            'set_inode_field $path generation $((4096 + index))',
            'set_inode_field $path atime @${source_epoch}',
            'set_inode_field $path ctime @${source_epoch}',
            'set_inode_field $path mtime @${source_epoch}',
            'set_inode_field $path crtime @${source_epoch}',
            'set_super_value mtime @${source_epoch}',
            'set_super_value wtime @${source_epoch}',
            'set_super_value lastcheck @${source_epoch}',
            'set_super_value mkfs_time @${source_epoch}',
            'set_super_value kbytes_written 0',
            'e2fsck -fn "$output_image"',
            '"metadata_normalization": {',
            'source_epoch =~ ^[1-9][0-9]*$',
            'source_epoch_max=4294967295',
            '${#source_epoch} > 10',
            'source_epoch > source_epoch_max',
        ):
            with self.subTest(token=token):
                self.assertIn(token, prepare)

        workflow = (ROOT / ".github/workflows/d2i-integrated-image.yml").read_text()
        self.assertIn("Prepare the integrated image twice and require byte equality", workflow)
        self.assertIn("tests/qemu/prepare-d2i-image.sh", workflow)
        self.assertIn("manifest_repository=\"$(jq -er '.repository' manifests/e2fsprogs-host-toolchain.v1.json)\"", workflow)
        self.assertIn("test \"$manifest_repository\" = \"https://github.com/tytso/e2fsprogs.git\"", workflow)
        self.assertIn("manifest_commit=\"$(jq -er '.commit' manifests/e2fsprogs-host-toolchain.v1.json)\"", workflow)
        self.assertIn("test \"$manifest_commit\" = \"$E2FSPROGS_COMMIT\"", workflow)
        self.assertIn("manifest_tag=\"$(jq -er '.tag' manifests/e2fsprogs-host-toolchain.v1.json)\"", workflow)
        self.assertIn("test \"$manifest_tag\" = \"v$E2FSPROGS_VERSION\"", workflow)
        self.assertIn("manifest_version=\"$(jq -er '.version' manifests/e2fsprogs-host-toolchain.v1.json)\"", workflow)
        self.assertIn("test \"$manifest_version\" = \"$E2FSPROGS_VERSION\"", workflow)
        self.assertIn("expected_metadata_normalization", workflow)
        self.assertIn("type(metadata['superblock_kbytes_written']) is int", workflow)
        self.assertIn("prep_a['metadata_normalization']", workflow)
        self.assertIn("prep_b['metadata_normalization']", workflow)
        self.assertIn("assert prep_a == prep_b", workflow)
        self.assertIn("prepared = read_json(root / 'd1/prepared/prepared-inputs.json')", workflow)
        self.assertIn("1 <= source_epoch <= 4294967295", workflow)
        self.assertIn("type(prep_a['source_date_epoch']) is int", workflow)
        self.assertIn("type(prep_b['source_date_epoch']) is int", workflow)
        self.assertIn("prep_a['source_date_epoch'] == source_epoch", workflow)
        self.assertIn("prep_b['source_date_epoch'] == source_epoch", workflow)

    def test_image_preparation_rejects_unrepresentable_source_epoch(self) -> None:
        script = ROOT / "tests/qemu/prepare-d2i-image.sh"
        common = [
            "bash",
            str(script),
            "--base-image",
            "/does/not/need/to/exist",
            "--runtime-binary",
            "/does/not/need/to/exist",
            "--overlay",
            "/does/not/need/to/exist",
            "--servo-revision",
            "0" * 40,
            "--output-image",
            "/tmp/d2i-contract-test-image",
            "--evidence",
            "/tmp/d2i-contract-test-evidence.json",
        ]
        for epoch in ("0", "4294967296", "999999999999999999999"):
            with self.subTest(epoch=epoch):
                result = subprocess.run(
                    [*common[:8], "--source-epoch", epoch, *common[8:]],
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(result.returncode, 2, result.stderr)

    def test_servo_checkout_uses_canonical_repository_and_sha_only(self) -> None:
        workflow = (ROOT / ".github/workflows/d2i-integrated-image.yml").read_text()
        self.assertIn("D2I Servo lock repository must be exactly", workflow)
        self.assertIn(
            "if re.fullmatch(r'[0-9a-f]{40}', revision) is None",
            workflow,
        )
        self.assertIn("git clone --filter=blob:none --no-checkout", workflow)
        self.assertIn("https://github.com/servo/servo", workflow)
        self.assertIn(
            'test "$SERVO_REPOSITORY" = https://github.com/servo/servo',
            workflow,
        )
        self.assertNotIn(
            '"$(python3 -c \'import json; d=json.load(open("manifests/servo.lock.json"))',
            workflow,
        )
        self.assertIn("git -C /tmp/servo fetch --depth=1 origin", workflow)
        self.assertIn('"$SERVO_REVISION"', workflow)
        self.assertIn("SERVO_REVISION: ${{ steps.servo-pin.outputs.revision }}", workflow)
        self.assertIn('--servo-revision "$SERVO_REVISION"', workflow)
        self.assertIn("source tools/reject_symlink_path.sh", workflow)
        self.assertIn('examples_parent=$(dirname -- "$examples_dir")', workflow)
        self.assertIn('mkdir -- "$examples_dir"', workflow)
        self.assertIn('reject_symlink_path "$examples_dir"', workflow)
        self.assertIn('require_regular_path "$runtime_example"', workflow)
        self.assertIn('require_regular_path "$fixture_example"', workflow)
        for script in (
            "tools/build_pinned_e2fsprogs.sh",
            "tools/run_d1_final_qualification.sh",
            "tools/run_servo_headed_runtime_gate.sh",
        ):
            self.assertIn(script, workflow)

    def test_input_digest_manifest_is_registry_derived_and_complete_for_scope(self) -> None:
        registry = json.loads(
            (ROOT / "manifests/gates.v1.json").read_text(encoding="utf-8")
        )
        gate = next(item for item in registry["gates"] if item["id"] == "D2I-01")
        paths = set(gate["invalidation_paths"])
        # These domains are consumed by the D2I workflow itself or by the
        # transitive D1/image/QEMU builders.  Keep their registry coverage
        # explicit so a new source domain cannot silently escape invalidation.
        for required in {
            "Cargo.toml",
            "Cargo.lock",
            "rust-toolchain.toml",
            "apps/**",
            "crates/**",
            "contracts/**",
            "packaging/debian/**",
            "experiments/servo-headed-runtime/**",
            "manifests/**",
            "tests/**",
            "tools/**",
            "docs/**",
            ".github/**",
            "Makefile",
            "README.md",
            "SECURITY.md",
            "CONTRIBUTING.md",
            "LICENSE",
            ".gitignore",
            ".editorconfig",
        }:
            self.assertIn(required, paths)

        workflow = (ROOT / ".github/workflows/d2i-integrated-image.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("git', 'ls-files', '--stage', '-z', '--', *pathspecs", workflow)
        self.assertIn("input_digest_scope", workflow)
        self.assertIn("external_input_pins", workflow)
        self.assertNotIn("inputs = [\n              Path('Cargo.lock')", workflow)

        contract = json.loads(
            (ROOT / "contracts/d2i-integrated-image.v1.json").read_text(
                encoding="utf-8"
            )
        )
        binding = contract["source_binding"]
        self.assertIn("tree_sha", binding["repository_tree"])
        self.assertEqual(
            binding["input_digests"]["generated_from"],
            "manifests/gates.v1.json",
        )
        self.assertTrue(binding["input_digests"]["exhaustive_for_scope"])

        architecture = (ROOT / "docs/architecture/D2I_INTEGRATED_IMAGE.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("complete checked-out repository", architecture)
        self.assertIn("invalidation pathspecs", architecture)

    def test_failure_diagnostics_are_separate_from_digest_bound_evidence(self) -> None:
        workflow = (ROOT / ".github/workflows/d2i-integrated-image.yml").read_text()
        self.assertIn(
            "diagnostics=/tmp/trillionnium-d2i/diagnostics",
            workflow,
        )
        self.assertIn(
            "path: /tmp/trillionnium-d2i/evidence",
            workflow,
        )
        self.assertIn(
            "path: /tmp/trillionnium-d2i/diagnostics",
            workflow,
        )
        self.assertNotIn(
            "cp -a /tmp/trillionnium-d2i/d1/evidence/. /tmp/trillionnium-d2i/evidence/",
            workflow,
        )
        # The canonical bundle is finalized before diagnostics are collected;
        # no post-finalization step may write into its evidence directory.
        envelope_step = workflow.index("write_envelope(evidence / 'gate-evidence-envelope.json'")
        diagnostics_step = workflow.index("Collect bounded D2I failure diagnostics")
        self.assertLess(envelope_step, diagnostics_step)

    def test_failure_diagnostics_copy_only_regular_files(self) -> None:
        workflow = (ROOT / ".github/workflows/d2i-integrated-image.yml").read_text()
        self.assertIn("source tools/reject_symlink_path.sh", workflow)
        self.assertIn("copy_diagnostic_tree()", workflow)
        self.assertIn('find -P "$source_root"', workflow)
        self.assertIn('find -P "$diagnostics"', workflow)
        self.assertIn('require_regular_path "$source"', workflow)
        self.assertIn('require_regular_path "$destination"', workflow)
        self.assertIn("cp -- \"$source\" \"$destination\"", workflow)
        self.assertNotIn(
            "cp -a /tmp/trillionnium-d2i/qemu/. \"$diagnostics/qemu/\"",
            workflow,
        )
        self.assertNotIn(
            "cp -a /tmp/trillionnium-d2i/d1/evidence/. \"$diagnostics/d1/\"",
            workflow,
        )
        # The diagnostic tree is a separate upload and must not write into the
        # digest-bound evidence directory.
        self.assertNotIn('destination_root="/tmp/trillionnium-d2i/evidence"', workflow)


if __name__ == "__main__":
    unittest.main()
