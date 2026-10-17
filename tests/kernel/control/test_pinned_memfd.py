"""CPU-only OS FD handoff tests; no Asterinas kernel, QEMU or hardware."""
import errno
import fcntl
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import pinned_memfd


class SealedQemuInputTests(unittest.TestCase):
    def test_mutated_original_path_cannot_change_inherited_guest_input(self):
        with tempfile.TemporaryDirectory() as directory:
            original = pathlib.Path(directory) / "untrusted-original"
            original.write_bytes(b"verified-pinned-kernel")
            pinned = original.read_bytes()  # upstream already verified SHA256
            fd = pinned_memfd.sealed_input("kernel", pinned)
            try:
                original.write_bytes(b"SWAPPED AFTER SHA256 CHECK")
                code = ("import pathlib,sys; "
                        "data=pathlib.Path(sys.argv[1]).read_bytes(); "
                        "assert data == b'verified-pinned-kernel',data")
                proc = subprocess.run(
                    [sys.executable, "-c", code, f"/proc/self/fd/{fd}"],
                    pass_fds=(fd,), check=False, capture_output=True)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertEqual(original.read_bytes(), b"SWAPPED AFTER SHA256 CHECK")
            finally:
                os.close(fd)

    def test_writes_growth_and_shrink_fail_after_sealing(self):
        fd = pinned_memfd.sealed_input("bios", b"verified-bios")
        try:
            seals = fcntl.fcntl(fd, fcntl.F_GET_SEALS)
            self.assertEqual(seals, pinned_memfd._REQUIRED_SEALS)
            with self.assertRaises(OSError) as failure:
                os.pwrite(fd, b"CORRUPT", 0)
            self.assertEqual(failure.exception.errno, errno.EPERM)
            with self.assertRaises(OSError):
                os.ftruncate(fd, 1)
            with self.assertRaises(OSError):
                os.write(fd, b"APPEND")
            self.assertEqual(os.pread(fd, 30, 0), b"verified-bios")
        finally:
            os.close(fd)

    def test_bad_identity_and_empty_input_are_rejected(self):
        for name, raw in (("other", b"data"), ("bios", b""),
                          ("initramfs", None), ("kernel", "not bytes")):
            with self.subTest(name=name, raw=raw), self.assertRaises(ValueError):
                pinned_memfd.sealed_input(name, raw)

    def test_missing_sealable_memfd_support_fails_closed(self):
        with patch.object(pinned_memfd.os, "memfd_create", None):
            with self.assertRaises(ValueError):
                pinned_memfd.sealed_input("kernel", b"never fallback to path")


if __name__ == "__main__":
    unittest.main()
