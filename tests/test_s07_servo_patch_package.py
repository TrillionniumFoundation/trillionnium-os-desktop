import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = ROOT / "manifests/lab-d3-servo-retained-node-action.v1.json"
EXPECTED_BASE = "f0e947e5e7267a3fcdd0a7d5437c0ae00c09ebfe"
EXPECTED_BRANCH = "codex/s07-servo-retained-node-closure-v1"
EXPECTED_SERVO = "670ae8a70801b162e186f81cbb5bdd2d59c39108"
TRANSITIVE_CLI_SOURCES = (
    "tools/qualify_servo_exact_pin_v3.py",
    "tools/_qualify_servo_exact_pin_v3_impl.py",
    "tools/qualify_servo_exact_pin.py",
    "tools/verify_d3_servo_patch.py",
)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def reject_duplicate(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


class ServoPatchPackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(
            MANIFEST_PATH.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate,
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )

    def test_manifest_binds_exact_successor_parent_and_runtime_head(self) -> None:
        manifest = self.manifest
        self.assertEqual(manifest["schema"], "trillionnium.lab.servo-patch.v1")
        self.assertEqual(manifest["blocker"], "D3-01")
        self.assertEqual(manifest["carrier_branch"], EXPECTED_BRANCH)
        self.assertEqual(manifest["carrier_base_commit"], EXPECTED_BASE)
        self.assertIn("pull_request_base_sha", manifest["carrier_parent_binding"])
        self.assertIn("runtime_exact_checkout", manifest["carrier_head_binding"])
        self.assertEqual(manifest["upstream"]["repository"], "servo/servo")
        self.assertEqual(manifest["upstream"]["commit"], EXPECTED_SERVO)
        self.assertEqual(manifest["extracted_from"]["pull_request"], 73)
        self.assertEqual(
            manifest["qualification"]["transitive_cli_sources"],
            list(TRANSITIVE_CLI_SOURCES),
        )
        self.assertTrue(
            manifest["qualification"]["prospective_merge_applies_complete_package"]
        )

    def test_ordered_patch_parts_match_every_declared_digest(self) -> None:
        patch = self.manifest["patch"]
        hardening = self.manifest["hardening"]
        base = b""
        hardening_bytes = b""
        seen = set()
        for section, accumulator in ((patch, "base"), (hardening, "hardening")):
            data = b""
            for record in section["parts"]:
                source = ROOT / record["path"]
                self.assertTrue(source.is_file(), record["path"])
                self.assertNotIn(record["path"], seen)
                seen.add(record["path"])
                chunk = source.read_bytes()
                self.assertEqual(digest(chunk), record["sha256"])
                data += chunk
            self.assertEqual(digest(data), section["sha256"])
            if accumulator == "base":
                base = data
            else:
                hardening_bytes = data
        self.assertGreater(len(base), 0)
        self.assertGreater(len(hardening_bytes), 0)
        self.assertEqual(len(seen), 8)

    def test_production_verify_d3_patch_command_executes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            temporary = Path(tmp)
            combined = temporary / "d3-servo.patch"
            base = temporary / "d3-servo-base.patch"
            hardening = temporary / "d3-servo-hardening.patch"
            completed = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "tools/qualify_servo_exact_pin_v3.py"),
                    "verify-d3-patch",
                    "--manifest", str(MANIFEST_PATH),
                    "--root", str(ROOT),
                    "--output", str(combined),
                    "--base-output", str(base),
                    "--hardening-output", str(hardening),
                ],
                cwd=ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(completed.returncode, 0, completed.stderr)
            result = json.loads(completed.stdout)
            self.assertIs(result["ok"], True)
            self.assertEqual(result["base_sha256"], self.manifest["patch"]["sha256"])
            self.assertEqual(result["hardening_sha256"], self.manifest["hardening"]["sha256"])
            self.assertEqual(digest(combined.read_bytes()), result["sha256"])
            separator = b"" if base.read_bytes().endswith(b"\n") else b"\n"
            self.assertEqual(combined.read_bytes(), base.read_bytes() + separator + hardening.read_bytes())
            self.assertEqual(result["changed_paths"], sorted(self.manifest["patch"]["allowed_paths"]))

    def test_original_exact_pin_cli_remains_available(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(ROOT / "tools/qualify_servo_exact_pin_v3.py"), "--help"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("--servo-root", completed.stdout)
        self.assertIn("--output", completed.stdout)

    def test_workflow_covers_complete_package_and_exact_tested_tree(self) -> None:
        workflow = (ROOT / ".github/workflows/s07-servo-retained-node.yml").read_text(encoding="utf-8")
        self.assertIn(f'branches: ["{EXPECTED_BRANCH}"]', workflow)
        for source in TRANSITIVE_CLI_SOURCES:
            self.assertGreaterEqual(workflow.count(f'"{source}"'), 2, source)
        for required in (
            "exact-head-real-servo-behavior",
            "prospective-merge-patch-package",
            "refs/pull/${{ github.event.pull_request.number }}/merge",
            'patch --batch --forward -d servo -p1 < "$RUNNER_TEMP/s07-hardening.patch"',
            'cmp "$RUNNER_TEMP/s07-allowed.txt" "$RUNNER_TEMP/s07-changed.txt"',
            "d3-servo-tested.patch",
            "d3-servo-tested-tree.txt",
            "tested_servo_patch_sha256",
            "tested_servo_tree",
            "s07-prospective-evidence.json",
            "running != ['1']",
        ):
            self.assertIn(required, workflow)
        self.assertNotIn('RUSTFLAGS: "-D warnings"', workflow)

    def test_verifier_and_dispatcher_are_single_purpose(self) -> None:
        dispatcher = (ROOT / "tools/qualify_servo_exact_pin_v3.py").read_text(encoding="utf-8")
        verifier = (ROOT / "tools/verify_d3_servo_patch.py").read_text(encoding="utf-8")
        implementation = (ROOT / "tools/_qualify_servo_exact_pin_v3_impl.py").read_text(encoding="utf-8")
        self.assertIn('sys.argv[1] == "verify-d3-patch"', dispatcher)
        self.assertIn("from verify_d3_servo_patch import main", dispatcher)
        self.assertIn("from _qualify_servo_exact_pin_v3_impl import main", dispatcher)
        self.assertIn("import qualify_servo_exact_pin as qualifier", implementation)
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
            "installed trillionnium browseractor",
            "physical hardware",
            "hsm signing",
            "release eligibility",
        ):
            self.assertIn(denied, claim)
        required = [entry.lower() for entry in self.manifest["qualification"]["required"]]
        self.assertIn("post-format tested servo patch digest and staged tree identity", required)
        self.assertIn("complete base plus hardening application in the prospective merge job", required)


if __name__ == "__main__":
    unittest.main()
