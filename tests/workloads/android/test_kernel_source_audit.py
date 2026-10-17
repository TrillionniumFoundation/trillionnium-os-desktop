import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
GENERATOR = ROOT / "support/android/generate_kernel_source_audit.py"


class KernelSourceAuditTests(unittest.TestCase):
    def test_current_snapshot_is_bound_to_project_commit_and_red(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "snapshot.json"
            result = subprocess.run(
                [sys.executable, str(GENERATOR), "--repo-root", str(ROOT), "--output", str(output)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 2, result.stdout + result.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            commit = subprocess.check_output(
                ["git", "-C", str(ROOT), "rev-parse", "HEAD"], text=True
            ).strip()
            tree = subprocess.check_output(
                ["git", "-C", str(ROOT), "rev-parse", "HEAD^{tree}"], text=True
            ).strip()
            self.assertEqual(report["project_commit"], commit)
            self.assertEqual(report["project_tree"], tree)
            self.assertEqual(report["blocking_requirements"], ["binder", "seccomp", "mac"])
            self.assertFalse(report["runtime_android_verified"])
            self.assertFalse(report["booted_android_on_asterinas"])

    def test_snapshot_records_git_blob_and_content_hash(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "snapshot.json"
            subprocess.run(
                [sys.executable, str(GENERATOR), "--repo-root", str(ROOT), "--output", str(output)],
                capture_output=True,
                check=False,
            )
            report = json.loads(output.read_text(encoding="utf-8"))
            rel = "kernel/asterinas/kernel/core/src/syscall/futex.rs"
            blob = subprocess.check_output(
                ["git", "-C", str(ROOT), "hash-object", rel], text=True
            ).strip()
            self.assertEqual(report["source_files"][rel]["git_blob"], blob)
            self.assertEqual(report["source_files"][rel]["bytes"], (ROOT / rel).stat().st_size)


if __name__ == "__main__":
    unittest.main()
