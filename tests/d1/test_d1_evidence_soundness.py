from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import verify_d1_artifact  # noqa: E402


class D1EvidenceSoundnessTests(unittest.TestCase):
    def test_permanent_gate_is_unconditional_read_only_and_non_mutating(self) -> None:
        workflow = (ROOT / ".github/workflows/d1-final-qualification.yml").read_text(
            encoding="utf-8"
        )
        trigger = workflow.split("\npermissions:\n", 1)[0]
        self.assertNotIn("paths:", trigger)
        self.assertNotIn("paths-ignore:", trigger)
        self.assertIn("pull_request:", trigger)
        self.assertIn("push:", trigger)
        self.assertIn("branches: [main]", trigger)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertNotIn("git push", workflow)
        self.assertNotIn("gh workflow run", workflow)

    def test_gate_registry_covers_actual_build_dependency_domains(self) -> None:
        registry = json.loads(
            (ROOT / "manifests/gates.v1.json").read_text(encoding="utf-8")
        )
        gate = next(item for item in registry["gates"] if item["id"] == "D1-01")
        paths = set(gate["invalidation_paths"])
        for required in {
            "Cargo.toml",
            "Cargo.lock",
            "rust-toolchain.toml",
            "apps/**",
            "crates/**",
            "contracts/**",
            "packaging/debian/**",
            "tests/d1/**",
            "tests/qemu/**",
            "tests/fixtures/**",
            "tools/**",
        }:
            self.assertIn(required, paths)

    def test_rootfs_manifest_and_portable_verifier_are_bound(self) -> None:
        builder = (ROOT / "packaging/debian/image/build-d1-image.sh").read_text(
            encoding="utf-8"
        )
        comparer = (ROOT / "tools/compare_d1_builds.py").read_text(encoding="utf-8")
        runner = (ROOT / "tools/run_d1_final_qualification.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("tools/d1_rootfs_manifest.py", builder)
        self.assertIn("rootfs-content-manifest.json", builder)
        self.assertIn("rootfs-content-manifest.json", comparer)
        self.assertIn("rootfs_manifest_diff", comparer)
        self.assertIn("tools/finalize_d1_evidence.py", runner)
        self.assertIn("tools/verify_d1_artifact.py", runner)
        self.assertIn(
            "python3 -m unittest discover -s tests -t . -p 'test_*.py' -v",
            runner,
        )
        self.assertNotIn("python3 -m unittest discover -s tests/d1", runner)
        self.assertNotIn("git push", runner)
        self.assertNotIn("gh workflow run", runner)

    def test_exact_main_push_binds_tested_object_to_fetched_main(self) -> None:
        runner = (ROOT / "tools/run_d1_final_qualification.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn('current_main=$(git rev-parse origin/main)', runner)
        self.assertIn('[[ "$tested_sha" == "$current_main" ]]', runner)

    def test_portable_verifier_requires_canonical_outputs_and_source_corpus(self) -> None:
        verifier = (ROOT / "tools/verify_d1_artifact.py").read_text(
            encoding="utf-8"
        )
        for required in (
            "REQUIRED_OUTPUT_PATHS",
            "REQUIRED_SOURCE_PATHS",
            "actual_output_paths",
            "source_input_files_sha256",
            "transport_consistency_only",
        ):
            self.assertIn(required, verifier)
        with self.assertRaises(ValueError):
            verify_d1_artifact.safe_relative("../escape", "test path")
        with self.assertRaises(ValueError):
            verify_d1_artifact.require_sha256("A" * 64, "test digest")

    def test_portable_verifier_checks_nested_result_claims(self) -> None:
        verifier = (ROOT / "tools/verify_d1_artifact.py").read_text(
            encoding="utf-8"
        )
        for required in (
            "validate_result_semantics",
            "PIPELINE_STAGE_NAMES_GENERATED",
            "reproducibility artifact comparisons",
            "QEMU boot claims",
            "acceptance AgentPort evidence",
            "prepared-input claims",
        ):
            self.assertIn(required, verifier)

    def test_snapshot_resolver_silences_curl_progress_before_write_out(self) -> None:
        resolver = (ROOT / "tools/resolve_debian_snapshot.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('"--silent"', resolver)
        self.assertIn("SNAPSHOT_HOST", resolver)

    def test_qemu_marker_audit_fails_closed_on_debugfs_failure(self) -> None:
        boot_test = (ROOT / "tests/qemu/run-d1-boot-test.sh").read_text(
            encoding="utf-8"
        )
        self.assertIn("marker_audit_status=$?", boot_test)
        self.assertIn("debugfs marker audit failed", boot_test)
        self.assertIn("File not found by ext2_lookup", boot_test)
        self.assertNotIn(
            "debugfs -R 'stat /etc/hepta/enable-agent-port' \\\n  \"$artifacts/trillionnium-d1.ext4\" > \"$marker_audit\" 2>&1 || true",
            boot_test,
        )


    def test_evidence_manifest_binds_clean_tested_git_tree(self) -> None:
        finalizer = (ROOT / "tools/finalize_d1_evidence.py").read_text(
            encoding="utf-8"
        )
        for required in (
            '"git", "ls-tree"',
            '"hash-object"',
            '"diff", "--cached"',
            '"TESTED_TREE_SHA"',
            "repository HEAD/tree drifted",
            "tracked source input drifted from tested tree",
        ):
            self.assertIn(required, finalizer)


if __name__ == "__main__":
    unittest.main()
