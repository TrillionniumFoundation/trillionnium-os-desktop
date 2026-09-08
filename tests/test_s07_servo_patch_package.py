import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "manifests/lab-d3-servo-retained-node-action.v1.json"
EXPECTED_BASE = "88071c23583f5f78f97a1d6a840634363408d11e"
EXPECTED_BRANCH = "codex/s07-servo-retained-node-v2"
EXPECTED_SERVO = "670ae8a70801b162e186f81cbb5bdd2d59c39108"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class ServoPatchPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))

    def test_manifest_binds_exact_successor_and_upstream(self) -> None:
        manifest = self.manifest
        self.assertEqual(manifest["schema"], "trillionnium.lab.servo-patch.v1")
        self.assertEqual(manifest["blocker"], "D3-01")
        self.assertEqual(manifest["carrier_branch"], EXPECTED_BRANCH)
        self.assertEqual(manifest["carrier_base_commit"], EXPECTED_BASE)
        self.assertEqual(manifest["upstream"]["repository"], "servo/servo")
        self.assertEqual(manifest["upstream"]["commit"], EXPECTED_SERVO)
        self.assertEqual(manifest["extracted_from"]["pull_request"], 73)

    def test_ordered_patch_parts_match_every_declared_digest(self) -> None:
        patch = self.manifest["patch"]
        hardening = self.manifest["hardening"]
        base = b""
        hardening_bytes = b""
        seen: set[str] = set()

        for record in patch["parts"]:
            path = ROOT / record["path"]
            self.assertTrue(path.is_file(), record["path"])
            self.assertNotIn(record["path"], seen)
            seen.add(record["path"])
            data = path.read_bytes()
            self.assertEqual(digest(data), record["sha256"])
            base += data

        for record in hardening["parts"]:
            path = ROOT / record["path"]
            self.assertTrue(path.is_file(), record["path"])
            self.assertNotIn(record["path"], seen)
            seen.add(record["path"])
            data = path.read_bytes()
            self.assertEqual(digest(data), record["sha256"])
            hardening_bytes += data

        self.assertEqual(digest(base), patch["sha256"])
        self.assertEqual(digest(hardening_bytes), hardening["sha256"])
        self.assertGreater(len(base), 0)
        self.assertGreater(len(hardening_bytes), 0)
        self.assertEqual(len(seen), 8)

    def test_production_verify_d3_patch_command_executes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            combined = temporary / "d3-servo.patch"
            base = temporary / "d3-servo-base.patch"
            hardening = temporary / "d3-servo-hardening.patch"
            command = [
                sys.executable,
                str(ROOT / "tools/qualify_servo_exact_pin_v3.py"),
                "verify-d3-patch",
                "--manifest",
                str(MANIFEST_PATH),
                "--root",
                str(ROOT),
                "--output",
                str(combined),
                "--base-output",
                str(base),
                "--hardening-output",
                str(hardening),
            ]
            completed = subprocess.run(
                command,
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(
                completed.returncode,
                0,
                f"stdout={completed.stdout}\nstderr={completed.stderr}",
            )
            result = json.loads(completed.stdout)
            self.assertIs(result["ok"], True)
            self.assertEqual(result["base_sha256"], self.manifest["patch"]["sha256"])
            self.assertEqual(
                result["hardening_sha256"], self.manifest["hardening"]["sha256"]
            )
            self.assertEqual(digest(base.read_bytes()), result["base_sha256"])
            self.assertEqual(
                digest(hardening.read_bytes()), result["hardening_sha256"]
            )
            self.assertEqual(digest(combined.read_bytes()), result["sha256"])
            separator = b"" if base.read_bytes().endswith(b"\n") else b"\n"
            self.assertEqual(
                combined.read_bytes(),
                base.read_bytes() + separator + hardening.read_bytes(),
            )
            self.assertEqual(
                result["changed_paths"], sorted(self.manifest["patch"]["allowed_paths"])
            )

    def test_original_exact_pin_cli_remains_available(self) -> None:
        completed = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools/qualify_servo_exact_pin_v3.py"),
                "--help",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--servo-root", completed.stdout)
        self.assertIn("--output", completed.stdout)

    def test_workflow_uses_the_executed_versioned_command(self) -> None:
        workflow = (
            ROOT / ".github/workflows/s07-servo-retained-node.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "python3 tools/qualify_servo_exact_pin_v3.py verify-d3-patch",
            workflow,
        )
        self.assertIn("exact-head-real-servo-behavior", workflow)
        self.assertIn("prospective-merge-patch-package", workflow)
        self.assertIn("refs/pull/${{ github.event.pull_request.number }}/merge", workflow)
        self.assertIn("running != ['1']", workflow)
        self.assertNotIn("RUSTFLAGS: \"-D warnings\"", workflow)

    def test_verifier_and_dispatcher_are_single_purpose(self) -> None:
        dispatcher = (ROOT / "tools/qualify_servo_exact_pin_v3.py").read_text(
            encoding="utf-8"
        )
        verifier = (ROOT / "tools/verify_d3_servo_patch.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('sys.argv[1] == "verify-d3-patch"', dispatcher)
        self.assertIn("from verify_d3_servo_patch import main", dispatcher)
        self.assertIn("from _qualify_servo_exact_pin_v3_impl import main", dispatcher)
        for required in (
            "load_patch_section",
            "verify_digest",
            "FORBIDDEN_ADDED_PATTERNS",
            "root.resolve() not in path.parents",
            "changed-path mismatch",
        ):
            self.assertIn(required, verifier)
        self.assertNotIn("subprocess", verifier)

    def test_claim_ceiling_remains_below_product_or_release(self) -> None:
        claim = self.manifest["claim_ceiling"].lower()
        for denied in (
            "installed trillionnium image",
            "physical hardware",
            "hsm signing",
            "product browseractor",
        ):
            self.assertIn(denied, claim)
        self.assertIn(
            "production verify-d3-patch cli invocation executed by the repository regression suite",
            [entry.lower() for entry in self.manifest["qualification"]["required"]],
        )


if __name__ == "__main__":
    unittest.main()
