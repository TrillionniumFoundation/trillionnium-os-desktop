"""Receipt boundary tests with structural bytes, not UI/runtime qualification."""
import copy
import tempfile
from pathlib import Path
import unittest

from qualify import digest, verify_build_binary


class BuildArtifactTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="trill-binary-receipt-")
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.raw = root / "built-shell"
        self.raw.write_bytes(b"\x7fELFstructural build with static symbol table")
        self.packaged = root / "packaged-shell"
        self.packaged.write_bytes(b"\x7fELFstructural distribution bytes")
        self.receipt = {"status": "passed", "exit_code": 0}
        for key, path in (("binaries", self.raw), ("packaged_binaries", self.packaged)):
            self.receipt[key] = {"trill-shell": {"sha256": digest(path), "bytes": path.stat().st_size}}

    def test_build_and_distribution_require_the_explicit_matching_artifact(self):
        self.assertEqual(verify_build_binary(self.receipt, self.raw), "binaries")
        self.assertEqual(verify_build_binary(self.receipt, self.packaged, packaged=True), "packaged_binaries")
        with self.assertRaises(RuntimeError):
            verify_build_binary(self.receipt, self.packaged)
        with self.assertRaises(RuntimeError):
            verify_build_binary(self.receipt, self.raw, packaged=True)

    def test_an_older_raw_receipt_cannot_qualify_a_packaged_binary(self):
        del self.receipt["packaged_binaries"]
        self.assertEqual(verify_build_binary(self.receipt, self.raw), "binaries")
        with self.assertRaises(RuntimeError):
            verify_build_binary(self.receipt, self.packaged, packaged=True)

    def test_failed_build_and_modified_same_size_package_are_rejected(self):
        failed = copy.deepcopy(self.receipt)
        failed["status"] = "failed"
        with self.assertRaises(RuntimeError):
            verify_build_binary(failed, self.raw)
        failed["status"] = "passed"
        failed["exit_code"] = 1
        with self.assertRaises(RuntimeError):
            verify_build_binary(failed, self.raw)
        old = self.packaged.read_bytes()
        self.packaged.write_bytes(old[:-1] + b"!")
        with self.assertRaises(RuntimeError):
            verify_build_binary(self.receipt, self.packaged, packaged=True)


if __name__ == "__main__":
    unittest.main()
