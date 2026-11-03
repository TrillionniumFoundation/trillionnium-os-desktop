"""Actual process exclusion and filesystem custody for reusable product caches."""
from pathlib import Path
import os
import select
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build_target_lease import TargetLease


class TargetLeaseTests(unittest.TestCase):
    def test_other_process_cannot_interleave_commands_and_release_allows_next_builder(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "cache"
            program = ("import sys; from pathlib import Path; "
                       f"sys.path.insert(0, {str(HERE)!r}); "
                       "from build_target_lease import TargetLease; "
                       "lease=TargetLease(Path(sys.argv[1])); "
                       "print('held',flush=True); sys.stdin.buffer.read(1); lease.close()")
            child = subprocess.Popen([sys.executable, "-I", "-B", "-c", program, str(target)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                self.assertTrue(select.select([child.stdout], [], [], 10)[0], "lease child did not report readiness")
                self.assertEqual(child.stdout.readline(), b"held\n")
                with self.assertRaisesRegex(ValueError, "Another product builder"):
                    TargetLease(target)
            finally:
                _out, error = child.communicate(input=b"x", timeout=10)
            self.assertEqual((child.returncode, error), (0, b""))
            with TargetLease(target) as lease:
                self.assertTrue(lease.path.is_file())

    def test_existing_broad_file_is_refused_without_repair(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            lock = target / ".trill-product-build.lock"
            lock.write_bytes(b"preserve original")
            lock.chmod(0o644)
            with self.assertRaisesRegex(ValueError, "custody differs"):
                TargetLease(target)
            self.assertEqual((lock.read_bytes(), lock.stat().st_mode & 0o777), (b"preserve original", 0o644))

    def test_link_does_not_redirect_the_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            original = target / "original"
            original.write_bytes(b"untouched")
            original.chmod(0o600)
            (target / ".trill-product-build.lock").symlink_to(original)
            with self.assertRaises(OSError):
                TargetLease(target)
            self.assertEqual(original.read_bytes(), b"untouched")

    def test_hard_link_cannot_alias_another_cache_lease(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            original = target / "original"
            original.touch(mode=0o600)
            os.link(original, target / ".trill-product-build.lock")
            with self.assertRaisesRegex(ValueError, "custody differs"):
                TargetLease(target)
            self.assertEqual(original.stat().st_nlink, 2)


if __name__ == "__main__":
    unittest.main()
