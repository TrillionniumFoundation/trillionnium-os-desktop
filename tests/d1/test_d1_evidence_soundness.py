from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]


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
        self.assertNotIn("git push", runner)
        self.assertNotIn("gh workflow run", runner)


if __name__ == "__main__":
    unittest.main()
