"""Real C compilation against Linux Binder UAPI. NOT Binder runtime evidence."""
from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest

SRC = Path(__file__).with_name("binder_uapi_layout.c")


class BinderLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if shutil.which("cc") is None:
            raise unittest.SkipTest("C compiler unavailable")

    def _compile(self, target, flags=()):
        return subprocess.run(
            ["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
             *flags, str(SRC), "-o", str(target)],
            capture_output=True, text=True, check=False, timeout=30,
        )

    def test_native_uapi_layout_compiles_and_matches_constants(self):
        with tempfile.TemporaryDirectory() as td:
            exe = Path(td) / "binder-layout"
            compiled = self._compile(exe)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            result = subprocess.run([str(exe)], capture_output=True, text=True,
                                    check=False, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            record = json.loads(result.stdout)
            self.assertEqual(record["scope"], "host_linux_uapi_layout_only")
            self.assertEqual(record["arch"], "x86_64_lp64")
            self.assertEqual(record["protocol_version"], 8)
            self.assertEqual(record["write_read_size"], 48)
            self.assertEqual(record["transaction_size"], 64)
            self.assertEqual(record["transaction_secctx_size"], 72)
            self.assertEqual(record["flat_object_size"], 24)
            self.assertEqual(record["handle_cookie_size"], 12)
            self.assertEqual(record["sender_uid_offset"], 28)
            self.assertEqual(record["ioctls"], {
                "BINDER_WRITE_READ": 0xc0306201,
                "BINDER_VERSION": 0xc0046209,
                "BINDER_SET_MAX_THREADS": 0x40046205,
                "BINDER_SET_CONTEXT_MGR_EXT": 0x4018620d,
            })
            self.assertIs(record["binder_driver_verified"], False)
            self.assertIs(record["android_asterinas_verified"], False)

    def test_incompatible_32bit_binder_mode_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            result = self._compile(Path(td) / "forbidden", ("-DBINDER_IPC_32BIT",))
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("static assertion", result.stderr.lower())

    def test_layout_source_never_opens_device_or_reports_runtime_success(self):
        source = SRC.read_text()
        self.assertNotIn('open("/dev/binder"', source)
        self.assertNotIn("ioctl(", source)
        self.assertIn('"\\\"binder_driver_verified\\\":false', source)


if __name__ == "__main__":
    unittest.main()
