import importlib.util
import os
from pathlib import Path
import struct
import sys
import tempfile
import unittest

PATH = Path(__file__).with_name("probe_ffi_bootstrap.py")
SPEC = importlib.util.spec_from_file_location("probe", PATH)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class OwnedHostControls(unittest.TestCase):
    def test_normal_owned_child_exit_proves_retirement(self):
        argv = [sys.executable, "-B", "-I", "-c",
                "import sys; assert sys.stdin.buffer.read(1)==b'R'; print('{\"ok\":true}')"]
        record, raw, err = probe.run_owned_child(argv, seconds=5)
        self.assertEqual(raw, b'{"ok":true}\n')
        self.assertEqual(err, b"")
        self.assertEqual(record["returncode"], 0)
        self.assertTrue(record["pidfd_exit_observed"])
        self.assertTrue(record["pidfd_closed"])
        self.assertTrue(record["parent_descriptors_restored"])
        self.assertFalse(record["errors"])
        self.assertEqual(record["owned_child_sigkill_count"], 0)

    def test_timeout_only_signals_held_owned_child(self):
        argv = [sys.executable, "-B", "-I", "-c",
                "import sys,time; assert sys.stdin.buffer.read(1)==b'R'; time.sleep(60)"]
        record, raw, err = probe.run_owned_child(argv, seconds=0.2)
        self.assertTrue(record["timeout"])
        self.assertEqual(record["owned_child_sigkill_count"], 1)
        self.assertEqual(record["returncode"], -9)
        self.assertTrue(record["pidfd_exit_observed"])
        self.assertTrue(record["pidfd_closed"])
        self.assertTrue(record["parent_descriptors_restored"])
        self.assertTrue(record["errors"])

    def test_wrong_library_identity_does_not_close_descriptor(self):
        with tempfile.TemporaryFile() as stream:
            stream.write(b"owned-control")
            stream.flush()
            fd = stream.fileno()
            row = probe.descriptor(fd)
            with self.assertRaisesRegex(RuntimeError, "LIBFFI_DIAGNOSTIC_IDENTITY_DIFFERS"):
                probe.library_binding(fd, row)
            self.assertEqual(os.pread(fd, 13, 0), b"owned-control")
            self.assertEqual(probe.descriptor(fd), row)

    def test_reused_fd_and_malformed_elf_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            first = Path(directory, "first")
            second = Path(directory, "second")
            first.write_bytes(b"a")
            second.write_bytes(b"b")
            fd = os.open(first, os.O_RDONLY | os.O_CLOEXEC)
            before = {str(fd): probe.descriptor(fd)}
            os.close(fd)
            replacement = os.open(second, os.O_RDONLY | os.O_CLOEXEC)
            try:
                self.assertEqual(replacement, fd)
                self.assertFalse(probe.same_descriptors(before, {str(fd): probe.descriptor(fd)}))
            finally:
                os.close(replacement)
        actual = Path(sys.executable).read_bytes()
        self.assertIsInstance(probe.elf_identity(actual), dict)
        bad = bytearray(actual)
        struct.pack_into("<Q", bad, 40, len(bad) + 1)
        with self.assertRaisesRegex(RuntimeError, "ELF_SECTION_TABLE"):
            probe.elf_identity(bytes(bad))


if __name__ == "__main__":
    unittest.main(verbosity=2)
