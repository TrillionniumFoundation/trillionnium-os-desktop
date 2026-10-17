"""Regressions for the omitted and corrupted sources in A08 PR #7."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from support.android import verify_source_integrity as integrity


class SourceIntegrityTests(unittest.TestCase):
    def fixture(self, directory):
        root = Path(directory)
        for relative in integrity.REQUIRED_FILES:
            source = integrity.ROOT / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
        return root

    def assert_rejected(self, root, path, stage):
        report = integrity.check_sources(root)
        self.assertEqual(report["status"], "source_integrity_failed", report)
        self.assertFalse(report["android_on_asterinas_verified"])
        self.assertTrue(any(error["path"] == path and error["stage"] == stage
                            for error in report["errors"]), report)

    def test_complete_checkout_is_only_source_integrity(self):
        report = integrity.check_sources()
        self.assertEqual(report["errors"], [])
        self.assertFalse(report["android_on_asterinas_verified"])
        self.assertGreaterEqual(report["checked_files"], len(integrity.REQUIRED_FILES))

    def test_missing_runtime_dependencies_fail_closed(self):
        # All seven dependencies identified before full historical recovery.
        paths = (
            "support/android/generate_kernel_source_audit.py",
            "support/android/prepare_asterinas_abi.py",
            "support/android/run_asterinas_abi.py",
            "support/android/verify_launch_preflight.py",
            "tests/workloads/android/run_apk.py",
            "tests/workloads/android/run_apk_workload.py",
            "tests/workloads/android/run_native_apk.py",
        )
        for path in paths:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = self.fixture(directory)
                (root / path).unlink()
                self.assert_rejected(root, path, "presence")

    def test_missing_test_module_cannot_shrink_the_suite_silently(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            path = "tests/workloads/android/test_verified_artifacts.py"
            (root / path).unlink()
            self.assert_rejected(root, path, "presence")

    def test_invalid_utf8_in_each_previously_corrupt_blob_is_rejected(self):
        paths = ("compat/android/aosp-profile.json",
                 "support/android/capture_guest_logs.py",
                 "tests/workloads/android/test_apk.py")
        for path in paths:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = self.fixture(directory)
                with (root / path).open("ab") as stream:
                    stream.write(b"\xbb")
                self.assert_rejected(root, path, "utf8")

    def test_truncated_json_with_valid_utf8_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            path = "compat/android/aosp-profile.json"
            (root / path).write_text('{"schema":', encoding="utf-8")
            self.assert_rejected(root, path, "syntax")

    def test_truncated_python_with_valid_utf8_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            path = "support/android/capture_guest_logs.py"
            (root / path).write_text("def unfinished(", encoding="utf-8")
            self.assert_rejected(root, path, "syntax")

    def test_each_shell_script_is_checked_separately(self):
        for path in integrity.EXECUTABLE_FILES:
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = self.fixture(directory)
                (root / path).write_text("if then\n", encoding="utf-8")
                self.assert_rejected(root, path, "syntax")

    def test_removed_entrypoint_executable_mode_is_rejected(self):
        for path in ("support/android/build_asterinas_abi.sh",
                     "support/android/build_smoke_apk.sh"):
            with self.subTest(path=path), tempfile.TemporaryDirectory() as directory:
                root = self.fixture(directory)
                (root / path).chmod(0o644)
                self.assert_rejected(root, path, "mode")

    def test_new_unlisted_python_source_is_checked(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            path = "support/android/new_helper.py"
            (root / path).write_text("def unfinished(", encoding="utf-8")
            self.assert_rejected(root, path, "syntax")

    def test_cli_returns_nonzero_and_preserves_failure_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.fixture(directory)
            (root / "tests/workloads/android/test_apk.py").unlink()
            output = root / "report.json"
            result = subprocess.run(
                [sys.executable, str(integrity.ROOT / "support/android/verify_source_integrity.py"),
                 "--root", str(root), "--out", str(output)],
                capture_output=True, text=True, check=False, timeout=30,
            )
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            report = json.loads(output.read_text())
            self.assertEqual(report["status"], "source_integrity_failed")
            self.assertFalse(report["android_on_asterinas_verified"])


if __name__ == "__main__":
    unittest.main()
