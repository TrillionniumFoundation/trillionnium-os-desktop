#!/usr/bin/env python3
"""Execute a disposable QEMU stand-in; these host tests never boot a kernel."""
import copy
import hashlib
import json
import os
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch

BUILD = Path(__file__).resolve().parents[1]
RECORDER = runpy.run_path(str(BUILD / "ktest/record-qemu.py"))
CHECK = runpy.run_path(str(BUILD / "ktest/check.py"))
FIRMWARE = Path("/usr/share/seabios/bios-256k.bin")
FAKE_QEMU = """#!{python}
import hashlib
import json
import os
from pathlib import Path
import sys
if '--version' in sys.argv:
    print('disposable QEMU stand-in; no guest executed')
    raise SystemExit(0)
argv = sys.argv
inputs = {{option: hashlib.sha256(Path(argv[argv.index(option) + 1]).read_bytes()).hexdigest()
          for option in ('-kernel', '-initrd') if option in argv}}
Path(os.environ['FIXTURE_OBSERVED']).write_text(json.dumps({{'argv': argv, 'inputs': inputs}}))
serial = argv[argv.index('-chardev') + 1].split('logfile=', 1)[1]
Path(serial).write_text('host-only recorder fixture; no guest executed\\n')
raise SystemExit(33)
"""


class KtestRecorderTests(unittest.TestCase):
    def test_actual_invocation_uses_canonical_boot_paths_and_preserves_osdk_request(self):
        for with_initrd in (False, True):
            with self.subTest(with_initrd=with_initrd), tempfile.TemporaryDirectory(
                    prefix="ktest-recorder-host-only-") as temporary:
                root = Path(temporary)
                target = root / "isolated target"
                target.mkdir()
                alias = root / "osdk-target-link"
                alias.symlink_to(target, target_is_directory=True)
                tools = root / "tools"
                tools.mkdir()
                binary = tools / "qemu-system-x86_64"
                binary.write_text(FAKE_QEMU.format(python=sys.executable))
                binary.chmod(0o755)
                requested = []
                options = ("-kernel", "-initrd") if with_initrd else ("-kernel",)
                for option in options:
                    (target / option).write_bytes(("host-only fixture " + option).encode())
                    requested.extend((option, str(alias / option)))
                requested.extend(("-append", "console=ttyS0 init=/fixture contains spaces"))
                environment = dict(os.environ, A01_KTEST_CRATE="osdk-frame-allocator",
                                   A01_KTEST_PROFILE="default", A01_KTEST_TEST_NAME="",
                                   A01_KTEST_GUESTS=str(root / "guests"), A01_KTEST_TIMEOUT="10",
                                   FIXTURE_OBSERVED=str(root / "observed.json"), PATH=str(tools))
                # Only the fixed BIOS file is synthetic. The recorder launches
                # the stand-in as a real subprocess which reads the actual boot
                # fixture files and records argv independently of the receipt.
                firmware_fixture = root / "firmware-fixture"
                firmware_fixture.write_bytes(b"host-only synthetic BIOS")
                original_stat, original_read = Path.stat, Path.read_bytes

                def fixture_stat(path, *args, **kwargs):
                    return original_stat(firmware_fixture if path == FIRMWARE else path, *args, **kwargs)

                def fixture_read(path):
                    return original_read(firmware_fixture if path == FIRMWARE else path)

                with patch.dict(os.environ, environment, clear=True), \
                        patch.object(sys, "argv", ["record-qemu.py", *requested]), \
                        patch.object(Path, "stat", fixture_stat), \
                        patch.object(Path, "read_bytes", fixture_read):
                    self.assertEqual(RECORDER["main"](), 33)
                record = json.loads((root / "guests/guest-001/qemu.json").read_text())
                observed = json.loads((root / "observed.json").read_text())
                self.assertEqual(record["requested_osdk_args"], requested)
                self.assertEqual(record["argv"], observed["argv"])
                for option in options:
                    expected = str(target / option)
                    self.assertEqual(record["argv"][record["argv"].index(option) + 1], expected)
                    self.assertEqual(record["artifacts"][option]["path"], expected)
                    self.assertEqual(record["artifacts"][option]["sha256"], observed["inputs"][option])
                    self.assertEqual(record["artifacts"][option]["sha256"],
                                     hashlib.sha256((target / option).read_bytes()).hexdigest())
                CHECK["check_fixed_n0_profile"](record, "host-only recorder fixture")
                for option in options:
                    mismatch = copy.deepcopy(record)
                    mismatch["argv"][mismatch["argv"].index(option) + 1] = str(alias / option)
                    with self.assertRaisesRegex(ValueError, "boot artifact path does not match"):
                        CHECK["check_fixed_n0_profile"](mismatch, "host-only recorder fixture")


if __name__ == "__main__":
    unittest.main(verbosity=2)
