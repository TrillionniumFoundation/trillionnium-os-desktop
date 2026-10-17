"""Host-only adversarial compiler boundary; does not run QEMU or devices."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import compile_guard


class CompileGuestGuardTests(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.root = Path(self.scratch.name)
        self.elf = self.root / "probe.elf"
        self.log = self.root / "compile.log"

    def command(self, code):
        return [sys.executable, "-I", "-c", code, str(self.elf)]

    def test_valid_small_compiler_writes_exact_bounded_artifact(self):
        command = self.command("from pathlib import Path;import sys;"
                               "Path(sys.argv[1]).write_bytes(b'ELF-dummy');print('ok')")
        self.assertEqual(
            compile_guard.compile_guest_probe(command, self.elf, self.log),
            b"ELF-dummy",
        )
        self.assertEqual(self.log.read_bytes(), b"ok\n")

    def test_compiler_output_is_hard_bounded_not_captured_in_python(self):
        with patch.object(compile_guard, "MAX_COMPILER_FILE_BYTES", 1024):
            command = self.command("import os;os.write(1,b'X'*4096)")
            with self.assertRaises(ValueError):
                compile_guard.compile_guest_probe(command, self.elf, self.log)
        self.assertLessEqual(self.log.stat().st_size, 1024)

    def test_symlinked_output_must_not_read_other_local_file(self):
        other = self.root / "dummy-outside"
        other.write_bytes(b"outside")
        self.elf.symlink_to(other)
        with self.assertRaises(OSError):
            compile_guard.compile_guest_probe(self.command("pass"), self.elf, self.log)
        self.assertEqual(other.read_bytes(), b"outside")

    def test_oversized_sparse_binary_is_rejected_before_large_read(self):
        with patch.object(compile_guard, "MAX_COMPILER_FILE_BYTES", 1024):
            command = self.command(
                "import sys;f=open(sys.argv[1],'wb');f.seek(2048);f.write(b'X');f.close()"
            )
            with self.assertRaises((ValueError, OSError)):
                compile_guard.compile_guest_probe(command, self.elf, self.log)

    def test_compiler_timeout_kills_separate_process_group(self):
        command = self.command("import time;time.sleep(5)")
        started = time.monotonic()
        with self.assertRaises(TimeoutError):
            compile_guard.compile_guest_probe(command, self.elf, self.log, timeout=0.06)
        self.assertLess(time.monotonic() - started, 2)


if __name__ == "__main__":
    unittest.main()
