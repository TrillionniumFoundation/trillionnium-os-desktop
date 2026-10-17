"""CPU-only child file cap regressions: never execute QEMU or write a device."""
import os
import pathlib
import resource
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import serial_limit


class BoundedSerialTests(unittest.TestCase):
    def test_child_hard_limit_blocks_unbounded_serial_output(self):
        # Keep the production child limit in the real helper; for this small
        # test redirect its 8-MiB maximum to a 1024-byte maximum.
        with tempfile.TemporaryDirectory() as directory:
            output = pathlib.Path(directory) / "serial.log"
            def tiny_limit():
                with patch.object(serial_limit, "MAX_SERIAL_BYTES", 1024):
                    serial_limit.limit_serial_file()
            code = ("import os; "
                    "os.write(1, b'X'*4096); "
                    "os.write(1, b'Y'*4096)")
            with output.open("xb") as writer:
                result = subprocess.run(
                    [sys.executable, "-c", code], stdout=writer,
                    stderr=subprocess.STDOUT, timeout=3, check=False,
                    preexec_fn=tiny_limit,
                )
            self.assertLessEqual(output.stat().st_size, 1024)
            self.assertNotEqual(result.returncode, 0,
                                "oversized guest serial must never qualify")

    def test_small_child_output_passes_and_parent_limits_are_unchanged(self):
        before = resource.getrlimit(resource.RLIMIT_FSIZE)
        with tempfile.TemporaryDirectory() as directory:
            out = pathlib.Path(directory) / "serial.log"
            with out.open("xb") as writer:
                result = subprocess.run([sys.executable, "-c",
                                         "import os;os.write(1,b'guest marker\\n')"],
                                        stdout=writer, stderr=subprocess.STDOUT,
                                        timeout=3, check=False,
                                        preexec_fn=serial_limit.limit_serial_file)
            self.assertEqual(result.returncode, 0)
            self.assertEqual(out.read_bytes(), b"guest marker\n")
        self.assertEqual(resource.getrlimit(resource.RLIMIT_FSIZE), before)

    def test_limit_never_exceeds_preexisting_stricter_hard_limit(self):
        with patch.object(serial_limit.resource, "getrlimit", return_value=(300, 512)):
            with patch.object(serial_limit.resource, "setrlimit") as setter:
                serial_limit.limit_serial_file()
                setter.assert_called_once_with(resource.RLIMIT_FSIZE, (300, 300))


if __name__ == "__main__":
    unittest.main()
