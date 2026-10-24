"""Actual wrapper file/lock/subprocess checks; no kernel or native qualification."""
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest

import build_native_owner_kernel as builder


class ProductKernelWrapperTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()

    def test_real_resource_lock_contends_and_preserves_inode(self):
        with builder.resource_lease(self.root) as held:
            with self.assertRaisesRegex(ValueError, "already leased"):
                with builder.resource_lease(self.root):
                    self.fail("second advisory lock unexpectedly succeeded")
            inode = (self.root / builder.LOCK_NAME).stat().st_ino
            self.assertEqual(inode, held["lock_inode"])
            self.assertIs(held["noncooperating_writers_excluded"], False)
        with builder.resource_lease(self.root) as reacquired:
            self.assertEqual(reacquired["lock_inode"], inode)

    def test_path_overlap_and_symlink_aliases_are_rejected(self):
        directory = self.root / "cache"
        directory.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(directory, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "canonical directory"):
            builder.canonical_directory(alias)
        with self.assertRaisesRegex(ValueError, "overlap"):
            builder.disjoint([self.root, directory])
        with self.assertRaisesRegex(ValueError, "overlap"):
            builder.disjoint([directory, directory])

    def test_retention_preserves_source_bytes_and_permissions(self):
        source = self.root / "input"
        source.write_bytes(b"retained\r\noriginal\n")
        source.chmod(0o640)
        retained = self.root / "retained"
        identity = builder.freeze_file(source, retained, 1024)
        self.assertEqual(retained.read_bytes(), source.read_bytes())
        self.assertEqual(identity["sha256"], builder.inputs.sha(source))
        self.assertEqual(stat.S_IMODE(source.stat().st_mode), 0o640)
        self.assertEqual(stat.S_IMODE(retained.stat().st_mode), 0o444)
        self.assertNotEqual(retained.stat().st_ino, source.stat().st_ino)
        with self.assertRaisesRegex(ValueError, "must be new"):
            builder.freeze_file(source, retained, 1024)

    def test_actual_command_failure_keeps_raw_log_and_never_passes(self):
        report = {"passed": False, "steps": []}
        argv = [sys.executable, "-c", "import os; os.write(1, b'actual\\r\\nexit\\n'); raise SystemExit(7)"]
        with self.assertRaisesRegex(ValueError, "original command failed"):
            builder.command_step("failure", argv, self.root, builder.BASE_ENV, self.root, report, 5)
        step, = report["steps"]
        self.assertEqual(step["exit_code"], 7)
        self.assertEqual((self.root / "failure.log").read_bytes(), b"actual\r\nexit\n")
        self.assertEqual(step["log_sha256"], builder.inputs.sha(self.root / "failure.log"))
        self.assertIs(step["timed_out"], False)
        self.assertIs(report["passed"], False)

    def test_actual_timeout_terminates_command_and_retains_failure(self):
        report = {"passed": False, "steps": []}
        argv = [sys.executable, "-c", "import os, time; os.write(1, b'started\\n'); time.sleep(30)"]
        with self.assertRaises(subprocess.TimeoutExpired):
            builder.command_step("timeout", argv, self.root, builder.BASE_ENV, self.root, report, 0.2)
        step, = report["steps"]
        self.assertIs(step["timed_out"], True)
        self.assertIs(step["completed"], True)
        self.assertNotEqual(step["exit_code"], 0)
        self.assertIs(report["passed"], False)


if __name__ == "__main__":
    unittest.main()
