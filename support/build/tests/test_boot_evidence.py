#!/usr/bin/env python3
"""Exercise boot evidence binding with archived raw bytes and disposable tools."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

BUILD = Path(__file__).resolve().parents[1]
CHECKER = BUILD / "check-boot.py"
RECORDER = BUILD / "record-qemu.py"
REAL_SERIAL = BUILD / "evidence/2026-10-16/acceptance/boot/serial.log"
MODES = ((), ("-O",), ("-I",), ("-I", "-O"))
MARKERS = (
    b"OSTD initialized. Preparing components.", b"TRILLIONNIUM_A01_INIT_BEGIN",
    b"TRILLIONNIUM_A01_CPU_COUNT=1", b"Successfully booted.", b"TRILLIONNIUM_A01_BOOT_OK",
)
FAKE_QEMU = """#!/usr/bin/python3
import os
from pathlib import Path
import sys
import time
if '--version' in sys.argv:
    print('disposable QEMU recorder fixture; no guest executed')
    raise SystemExit(0)
if os.environ.get('FIXTURE_NO_SERIAL') != '1':
    Path(os.environ['FIXTURE_SERIAL_DEST']).write_bytes(Path(os.environ['FIXTURE_SERIAL_SOURCE']).read_bytes())
if os.environ.get('FIXTURE_TIMEOUT') == '1':
    time.sleep(5)
raise SystemExit(33)
"""


class BootEvidenceTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="a01-boot-evidence-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.directory = self.root / "evidence"
        self.inputs = self.root / "inputs"
        self.directory.mkdir()
        self.inputs.mkdir()
        self.raw_serial = REAL_SERIAL.read_bytes()
        artifacts = {}
        for option, name in (("-kernel", "kernel.elf"), ("-initrd", "initramfs.cpio.gz"), ("-bios", "bios.bin")):
            raw = ("disposable input for " + option).encode()
            (self.inputs / name).write_bytes(raw)
            artifacts[option] = {"path": name, "size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
        self.record = {
            "cwd": str(self.inputs), "raw_exit_code": 33, "timed_out": False,
            "serial_sha256": hashlib.sha256(self.raw_serial).hexdigest(),
            "serial_size": len(self.raw_serial), "artifacts": artifacts,
        }
        self.write_fixture()

    def write_fixture(self, record=None, serial=None):
        (self.directory / "qemu.json").write_text(json.dumps(self.record if record is None else record))
        (self.directory / "serial.log").write_bytes(self.raw_serial if serial is None else serial)

    def check(self, accepted, live=False):
        for mode in MODES:
            with self.subTest(mode=mode, live=live):
                argv = [sys.executable, *mode, str(CHECKER), str(self.directory)]
                if live:
                    argv.append("--live-artifacts")
                result = subprocess.run(argv, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=10)
                if accepted:
                    self.assertEqual(result.returncode, 0, result.stdout)
                    self.assertIn("PASS:", result.stdout)
                else:
                    self.assertNotEqual(result.returncode, 0, result.stdout)
                    self.assertNotIn("PASS:", result.stdout)

    def rebind_serial(self, serial):
        record = json.loads(json.dumps(self.record))
        record["serial_sha256"] = hashlib.sha256(serial).hexdigest()
        record["serial_size"] = len(serial)
        self.write_fixture(record, serial)

    def test_matching_real_raw_serial_passes_in_archive_and_live_modes(self):
        self.check(True)
        self.check(True, live=True)

    def test_archived_verification_does_not_require_original_paths(self):
        shutil.rmtree(self.inputs)
        self.check(True)
        self.check(False, live=True)

    def test_missing_or_wrong_serial_sha256_is_rejected(self):
        for missing in (False, True):
            with self.subTest(missing=missing):
                record = json.loads(json.dumps(self.record))
                if missing:
                    record.pop("serial_sha256")
                else:
                    record["serial_sha256"] = "0" * 64
                self.write_fixture(record)
                self.check(False)

    def test_appended_harmless_raw_bytes_are_rejected(self):
        self.write_fixture(serial=self.raw_serial + b"\nA01 harmless audit tail\n")
        self.check(False)

    def test_replaced_or_truncated_serial_is_rejected(self):
        for serial in (b"different complete log\n" + self.raw_serial, self.raw_serial[:-1]):
            self.write_fixture(serial=serial)
            self.check(False)

    def test_inconsistent_recorded_serial_size_is_rejected(self):
        record = json.loads(json.dumps(self.record))
        record["serial_size"] += 1
        self.write_fixture(record)
        self.check(False)

    def test_missing_exit_or_timeout_result_is_rejected(self):
        for key in ("raw_exit_code", "timed_out"):
            record = json.loads(json.dumps(self.record))
            record.pop(key)
            self.write_fixture(record)
            self.check(False)

    def test_non_successful_raw_status_and_timeout_are_rejected(self):
        for status, timed_out in ((0, False), (1, False), (32, False), (34, False), (124, True), (33, True)):
            with self.subTest(status=status, timed_out=timed_out):
                record = json.loads(json.dumps(self.record))
                record.update(raw_exit_code=status, timed_out=timed_out)
                self.write_fixture(record)
                self.check(False)

    def test_missing_complete_boot_markers_are_rejected_with_matching_digest(self):
        for marker in MARKERS:
            with self.subTest(marker=marker):
                self.rebind_serial(self.raw_serial.replace(marker, b"removed marker"))
                self.check(False)

    def test_fatal_kernel_panics_are_rejected_with_matching_digest(self):
        for marker in (
            "panicked at", "An uncaught panic occurred:", "Uncaught panic:",
            "unknown panic payload! (fatal panic handling error", "Non-resettable panic!",
            "The panic handler panicked", "Panicked in `PanicGuard`, aborting the system",
        ):
            with self.subTest(marker=marker):
                # ANSI escapes must not hide a fatal marker from textual validation.
                self.rebind_serial(self.raw_serial + b"\n\x1b[31m" + marker.encode() + b"\x1b[0m\n")
                self.check(False)

    def test_missing_artifact_entries_and_hashes_are_rejected_offline(self):
        for option in ("-kernel", "-initrd", "-bios"):
            for missing_entry in (False, True):
                record = json.loads(json.dumps(self.record))
                if missing_entry:
                    record["artifacts"].pop(option)
                else:
                    record["artifacts"][option].pop("sha256")
                self.write_fixture(record)
                self.check(False)

    def test_live_artifact_bytes_are_checked_for_all_three_inputs(self):
        for option in ("-kernel", "-initrd", "-bios"):
            with self.subTest(option=option):
                path = self.inputs / self.record["artifacts"][option]["path"]
                original = path.read_bytes()
                path.write_bytes(original + b" changed")
                self.check(True)  # Archives retain metadata, not mutable host paths.
                self.check(False, live=True)
                path.write_bytes(original)

    def run_recorder(self, no_serial=False, timeout=False):
        tools = self.root / "tools"
        tools.mkdir()
        binary = tools / "qemu-system-x86_64"
        binary.write_text(FAKE_QEMU)
        binary.chmod(0o755)
        selected_log = self.inputs / "selected-serial.raw"
        (self.inputs / "qemu.log").write_bytes(b"stale unrelated default file")
        environment = os.environ.copy()
        environment.update({
            "PATH": str(tools) + os.pathsep + environment.get("PATH", ""),
            "A01_QEMU_EVIDENCE": str(self.directory / "qemu.json"),
            "A01_QEMU_TIMEOUT": "1" if timeout else "5",
            "FIXTURE_SERIAL_SOURCE": str(REAL_SERIAL), "FIXTURE_SERIAL_DEST": str(selected_log),
            "FIXTURE_NO_SERIAL": "1" if no_serial else "0", "FIXTURE_TIMEOUT": "1" if timeout else "0",
        })
        argv = [sys.executable, "-I", str(RECORDER)]
        for option, artifact in self.record["artifacts"].items():
            argv.extend((option, artifact["path"]))
        argv.extend(("-chardev", "stdio,id=other,logfile=unrelated.log", "-serial", "chardev:serial",
                     "-chardev", "stdio,id=serial,signal=off,logfile=selected-serial.raw"))
        result = subprocess.run(argv, cwd=self.inputs, env=environment, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, timeout=10)
        return result, json.loads((self.directory / "qemu.json").read_text()), selected_log

    def test_recorder_binds_complete_actual_chardev_log_and_inputs(self):
        result, record, selected_log = self.run_recorder()
        self.assertEqual(result.returncode, 33, result.stdout)
        self.assertEqual(record["serial_path"], str(selected_log))
        self.assertEqual(record["serial_sha256"], hashlib.sha256(self.raw_serial).hexdigest())
        self.assertEqual(record["serial_size"], len(self.raw_serial))
        self.assertEqual(record["artifacts"], self.record["artifacts"])
        self.check(True)
        self.check(True, live=True)

    def test_recorder_missing_selected_log_does_not_use_stale_qemu_log(self):
        result, record, _ = self.run_recorder(no_serial=True)
        self.assertEqual(result.returncode, 33, result.stdout)
        self.assertNotIn("serial_sha256", record)
        self.assertIn("serial_error", record)
        self.check(False)

    def test_recorder_timeout_is_rejected_even_with_complete_serial(self):
        result, record, _ = self.run_recorder(timeout=True)
        self.assertEqual(result.returncode, 124, result.stdout)
        self.assertTrue(record["timed_out"])
        self.assertEqual(record["serial_sha256"], hashlib.sha256(self.raw_serial).hexdigest())
        self.check(False)


if __name__ == "__main__":
    unittest.main(verbosity=2)
