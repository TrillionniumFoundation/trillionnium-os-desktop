from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


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
        self.assertIn(
            "actual_content_process_crash_callback_observed",
            contract["promotion_requires"],
        )
        self.assertIn("exact_main_rerun_after_merge", contract["promotion_requires"])

    def test_guest_runtime_is_networkless_and_unprivileged(self) -> None:
        service = (
            ROOT
            / "packaging/debian/image/d2i-overlay/etc/systemd/system/trillionnium-d2i-runtime.service"
        ).read_text()
        self.assertIn("User=hepta-desktop", service)
        self.assertIn("PrivateNetwork=yes", service)
        self.assertIn("RestrictAddressFamilies=AF_UNIX", service)
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
        legacy_runtime = ROOT / "runtime/servo/hepta_workspace_runtime.rs"
        self.assertFalse(
            legacy_runtime.exists(),
            "superseded runtime source must not reintroduce an in-process injector",
        )
        runtime_readme = (ROOT / "runtime/README.md").read_text()
        self.assertIn("experiments/servo-headed-runtime/src/main.rs", runtime_readme)
        self.assertIn("runtime_internal_injector: false", runtime_readme)
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
        self.assertIn("injector_count", injector)
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
        self.assertIn("PASS_DETERMINISTIC_INPUT_INJECTION", prepare)
        self.assertIn("E2FSPROGS_FAKE_TIME", prepare)
        self.assertIn("-nic none", boot)
        self.assertIn("trillionnium-d2i-acceptance.target", boot)
        self.assertIn("cmp -s", workflow)
        self.assertIn("run-d1-pipeline.sh", workflow)
        self.assertIn("run-d2i-boot-test.sh", workflow)
        self.assertIn("actual_content_process_crash_proven", workflow)
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
