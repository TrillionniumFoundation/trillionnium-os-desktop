#!/usr/bin/env python3
"""Actual recorder CLI fixtures only; never compile Rust or execute a guest."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

BUILD = Path(__file__).resolve().parents[1]
RECORDER = Path(os.environ.get("A01_KTEST_RECORDER_SOURCE", str(BUILD / "ktest/record-qemu.py")))
SELECTOR = BUILD / "record-qemu.py"
FAKE = r'''#!/usr/bin/python3
import hashlib, json, os, sys, time
from pathlib import Path
if '--version' in sys.argv:
    Path(os.environ['FIXTURE_VERSION']).write_text('fake version probe\n')
    print('disposable QEMU fixture; no guest executed')
    raise SystemExit(0)
artifacts = {}
for option in ('-kernel', '-initrd', '-bios'):
    if option in sys.argv:
        path = Path(sys.argv[sys.argv.index(option)+1]); data = path.read_bytes()
        artifacts[option] = {'path':str(path), 'size':len(data), 'sha256':hashlib.sha256(data).hexdigest()}
Path(os.environ['FIXTURE_LOADED']).write_text(json.dumps({'argv':sys.argv, 'artifacts':artifacts, 'pid':os.getpid()}))
for arg in sys.argv:
    if arg.startswith('stdio,id=serial,signal=off,logfile='):
        Path(arg.split('logfile=',1)[1]).write_bytes(b'host CLI fixture only; no guest executed\n')
time.sleep(float(os.environ.get('FIXTURE_SLEEP_SECONDS', '0')))
raise SystemExit(33)
'''


class KtestPrivateInputsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="a01-ktest-private-")
        self.addCleanup(temporary.cleanup)
        setting = os.environ.get("A01_KTEST_PRIVATE_TEST_OUT")
        self.root = Path(setting) / self._testMethodName if setting else Path(temporary.name)
        self.root.mkdir(parents=True, exist_ok=True)
        self.tools = self.root / "tools"
        self.tools.mkdir()
        self.binary = self.tools / "qemu-system-x86_64"
        self.binary.write_text(FAKE)
        self.binary.chmod(0o755)
        self.bios = self.root / "private firmware with spaces" / "bios 256k.bin"
        self.bios.parent.mkdir()
        self.bios.write_bytes(b"private firmware fixture bytes")
        self.data = self.root / "private QEMU data with spaces"
        self.data.mkdir()
        self.kernel = self.root / "kernel with spaces.elf"
        self.kernel.write_bytes(b"kernel fixture bytes")
        self.initrd = self.root / "optional initrd.gz"
        self.initrd.write_bytes(b"optional initrd fixture bytes")
        self.request = ["-kernel", str(self.kernel), "-append", "loglevel=error console=ttyS0"]
        self.calls = 0

    def invoke(self, *, bios=None, data=None, arguments=None, timeout_value=None, sleep_seconds=None):
        env = os.environ.copy()
        env.pop("A01_QEMU_BIOS", None)
        env.pop("A01_QEMU_DATA_DIR", None)
        env.pop("A01_KTEST_TIMEOUT", None)
        env.pop("FIXTURE_SLEEP_SECONDS", None)
        env.update(PATH=str(self.tools) + os.pathsep + env.get("PATH", ""),
                   A01_KTEST_GUESTS=str(self.root / "guests"), A01_KTEST_CRATE="ostd",
                   FIXTURE_VERSION=str(self.root / "version-started"),
                   FIXTURE_LOADED=str(self.root / "loaded.json"))
        if bios is not None:
            env["A01_QEMU_BIOS"] = bios
        if data is not None:
            env["A01_QEMU_DATA_DIR"] = data
        if timeout_value is not None:
            env["A01_KTEST_TIMEOUT"] = timeout_value
        if sleep_seconds is not None:
            env["FIXTURE_SLEEP_SECONDS"] = str(sleep_seconds)
        argv = [sys.executable, "-I", *(["-O"] if sys.flags.optimize else []), str(RECORDER),
                *(self.request if arguments is None else arguments)]
        default_bios_exists = Path("/usr/share/seabios/bios-256k.bin").exists()
        result = subprocess.run(argv, cwd=self.root, env=env, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=10, text=True)
        self.calls += 1
        records = sorted((self.root / "guests").glob("guest-*/qemu.json"))
        record = json.loads(records[-1].read_text()) if records else None
        prefix = self.root / f"call-{self.calls:03d}"
        prefix.with_suffix(".log").write_text(result.stdout)
        prefix.with_suffix(".json").write_text(json.dumps({
            "argv": argv, "cwd": str(self.root), "returncode": result.returncode,
            "selected_environment": {k: v for k, v in env.items()
                                     if k.startswith(("A01_KTEST_", "A01_QEMU_", "FIXTURE_"))},
            "recorder_sha256": hashlib.sha256(RECORDER.read_bytes()).hexdigest(),
            "selector_sha256": hashlib.sha256(SELECTOR.read_bytes()).hexdigest(),
            "system_default_bios_exists_before_call": default_bios_exists,
        }, indent=2) + "\n")
        return result, record

    def rejected(self, **options):
        result, record = self.invoke(**options)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(record["stage"], "artifact_preparation_failed")
        self.assertIsNone(record["raw_exit_code"])
        self.assertNotIn("qemu_version", record)
        self.assertFalse((self.root / "version-started").exists())
        self.assertFalse((self.root / "loaded.json").exists())

    def test_private_paths_with_spaces_load_selected_bios_and_one_data_directory(self):
        arguments = self.request + ["-initrd", str(self.initrd), "-smp", "9", "-m", "99G",
                                    "-machine", "unwanted", "-device", "unwanted-device"]
        result, record = self.invoke(bios=str(self.bios), data=str(self.data), arguments=arguments)
        self.assertEqual(result.returncode, 33, result.stdout)
        self.assertEqual(record["requested_osdk_args"], arguments)
        original = record["requested_fixed_qemu_args"]
        self.assertEqual(original[original.index("-bios") + 1], "/usr/share/seabios/bios-256k.bin")
        self.assertNotIn("-L", original)
        loaded = json.loads((self.root / "loaded.json").read_text())
        argv = loaded["argv"]
        self.assertEqual(argv.count("-L"), 1)
        self.assertEqual(argv[argv.index("-L") + 1], str(self.data))
        self.assertEqual(argv[argv.index("-bios") + 1], str(self.bios))
        self.assertEqual(argv[argv.index("-smp") + 1], "1")
        self.assertEqual(argv[argv.index("-m") + 1], "512M")
        self.assertEqual(argv[argv.index("-machine") + 1], "q35")
        self.assertNotIn("unwanted-device", argv)
        self.assertEqual(record["bios_selection"]["origin"], "A01_QEMU_BIOS")
        self.assertEqual(record["data_selection"]["selected_path"], str(self.data))
        for key in ("path", "size", "sha256"):
            self.assertEqual(record["artifacts"]["-bios"][key], loaded["artifacts"]["-bios"][key])
        self.assertEqual(record["artifacts"]["-bios"]["sha256"], hashlib.sha256(self.bios.read_bytes()).hexdigest())
        self.assertEqual(record["input_selector_source"]["sha256"], hashlib.sha256(SELECTOR.read_bytes()).hexdigest())

    def test_private_bios_without_data_preserves_optional_initrd_and_fixed_profile(self):
        result, record = self.invoke(bios=str(self.bios))
        self.assertEqual(result.returncode, 33, result.stdout)
        self.assertNotIn("-L", record["argv"])
        self.assertNotIn("-initrd", record["argv"])
        self.assertFalse(record["data_selection"]["appended"])
        self.assertEqual(record["artifacts"]["-bios"]["path"], str(self.bios))

    def test_invalid_timeout_fails_before_version_probe_or_guest(self):
        for value in ("invalid", "", "0", "-1", "1.5", "9" * 1000):
            with self.subTest(value=value):
                result, record = self.invoke(bios=str(self.bios), timeout_value=value)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertEqual(record["stage"], "artifact_preparation_failed")
                self.assertEqual(record["recorder_exit_code"], 1)
                self.assertEqual(record["timeout_requested"], value)
                self.assertIsNone(record["timeout_seconds"])
                self.assertIsNone(record["raw_exit_code"])
                self.assertIsNone(record.get("qemu_pid"))
                self.assertFalse(record["timed_out"])
                self.assertNotIn("argv", record)
                self.assertNotIn("qemu_version", record)
                self.assertNotIn("Traceback", result.stdout)
                self.assertFalse((self.root / "version-started").exists())
                self.assertFalse((self.root / "loaded.json").exists())

    def test_default_and_positive_timeouts_preserve_guest_exit_and_provenance(self):
        for value in (None, "2", "90000"):
            with self.subTest(value=value):
                result, record = self.invoke(bios=str(self.bios), timeout_value=value)
                self.assertEqual(result.returncode, 33, result.stdout)
                self.assertEqual(record["stage"], "complete")
                self.assertEqual(record["raw_exit_code"], 33)
                self.assertEqual(record["recorder_exit_code"], 33)
                self.assertEqual(record["timeout_requested"], "300" if value is None else value)
                self.assertEqual(record["timeout_seconds"], 300 if value is None else int(value))
                self.assertFalse(record["timed_out"])
                loaded = json.loads((self.root / "loaded.json").read_text())
                self.assertEqual(record["artifacts"]["-bios"]["sha256"], loaded["artifacts"]["-bios"]["sha256"])
                self.assertEqual(record["qemu_sha256"], hashlib.sha256(self.binary.read_bytes()).hexdigest())
                self.assertEqual(record["input_selector_source"]["sha256"], hashlib.sha256(SELECTOR.read_bytes()).hexdigest())

    def test_valid_timeout_still_kills_and_reaps_fake_guest(self):
        result, record = self.invoke(bios=str(self.bios), timeout_value="1", sleep_seconds=30)
        self.assertEqual(result.returncode, 124, result.stdout)
        self.assertEqual(record["stage"], "complete")
        self.assertEqual(record["raw_exit_code"], 124)
        self.assertEqual(record["recorder_exit_code"], 124)
        self.assertEqual(record["timeout_requested"], "1")
        self.assertEqual(record["timeout_seconds"], 1)
        self.assertTrue(record["timed_out"])
        self.assertGreaterEqual(record["duration_seconds"], 0.9)
        loaded = json.loads((self.root / "loaded.json").read_text())
        with self.assertRaises(ProcessLookupError):
            os.kill(loaded["pid"], 0)
        serial = Path(record["argv"][record["argv"].index("-chardev") + 1].split("logfile=", 1)[1])
        self.assertEqual(record["serial_sha256"], hashlib.sha256(serial.read_bytes()).hexdigest())

    def test_four_invalid_bios_values_fail_before_any_qemu_probe(self):
        for value in ("", "relative.bin", str(self.root / "missing-bios"), str(self.data)):
            with self.subTest(value=value):
                self.rejected(bios=value, data=str(self.data))

    def test_invalid_data_or_incoming_L_conflict_fail_before_any_qemu_probe(self):
        for value, arguments in (("", None), ("relative-data", None),
                (str(self.root / "missing-data"), None), (str(self.bios), None),
                (str(self.data), self.request + ["-L", "incoming resources"])):
            with self.subTest(value=value, arguments=arguments):
                self.rejected(bios=str(self.bios), data=value, arguments=arguments)

    def test_malformed_osdk_artifact_arguments_fail_before_tools(self):
        for arguments in (["-kernel", str(self.kernel)], self.request + ["-kernel", str(self.kernel)],
                          ["-kernel"], self.request + ["-initrd"]):
            with self.subTest(arguments=arguments):
                self.rejected(bios=str(self.bios), data=str(self.data), arguments=arguments)


if __name__ == "__main__":
    unittest.main(verbosity=2)
