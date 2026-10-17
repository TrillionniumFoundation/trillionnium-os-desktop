#!/usr/bin/env python3
"""Exercise boot evidence binding with archived raw bytes and disposable tools."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

BUILD = Path(__file__).resolve().parents[1]
CHECKER = BUILD / "check-boot.py"
RECORDER = Path(os.environ.get("A01_SNAPSHOT_RECORDER_SOURCE", str(BUILD / "record-qemu.py")))
SPEC = importlib.util.spec_from_file_location("a01_snapshot_recorder", RECORDER)
SNAPSHOT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SNAPSHOT)
REAL_SERIAL = BUILD / "evidence/2026-10-16/acceptance/boot/serial.log"
MODES = ((), ("-O",), ("-I",), ("-I", "-O"))
MARKERS = (
    b"OSTD initialized. Preparing components.", b"TRILLIONNIUM_A01_INIT_BEGIN",
    b"TRILLIONNIUM_A01_CPU_COUNT=1", b"Successfully booted.", b"TRILLIONNIUM_A01_BOOT_OK",
)
FAKE_QEMU = """#!/usr/bin/python3
import hashlib
import json
import os
from pathlib import Path
import sys
import time
if '--version' in sys.argv:
    if os.environ.get('FIXTURE_VERSION_MARKER'):
        Path(os.environ['FIXTURE_VERSION_MARKER']).write_text('version probe executed\\n')
    if os.environ.get('FIXTURE_DELETE_AFTER_VERSION') == '1':
        Path(sys.argv[0]).unlink()
    print('disposable QEMU recorder fixture; no guest executed')
    raise SystemExit(0)
loaded = {}
for option in ('-kernel', '-initrd', '-bios'):
    if option in sys.argv:
        path = Path(sys.argv[sys.argv.index(option)+1])
        raw = path.read_bytes()
        loaded[option] = {'path':str(path), 'size':len(raw), 'sha256':hashlib.sha256(raw).hexdigest()}
Path(os.environ['FIXTURE_LOADED']).write_text(json.dumps({'argv':sys.argv, 'artifacts':loaded}))
for name in json.loads(os.environ.get('FIXTURE_REPLACE_SOURCES', '[]')):
    path = Path(name)
    replacement = path.with_name(path.name + '.replacement')
    replacement.write_bytes(b'atomic replacement of original source after fake QEMU read\\n')
    replacement.replace(path)
if os.environ.get('FIXTURE_TAMPER_SNAPSHOT') == '1':
    path = Path(sys.argv[sys.argv.index('-kernel')+1])
    path.chmod(0o600)
    path.write_bytes(b'deliberately corrupted live artifact\\n')
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
        setting = os.environ.get("A01_SNAPSHOT_TEST_OUT")
        self.root = Path(setting) / self._testMethodName if setting else Path(temporary.name)
        if setting:
            self.root.mkdir(parents=True, exist_ok=False)
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

    def run_recorder(self, no_serial=False, timeout=False, replace_sources=False,
                     tamper_snapshot=False, artifact_args=None, delete_binary=False,
                     bios_override=None, data_override=None):
        tools = self.root / "tools"
        tools.mkdir(exist_ok=True)
        binary = tools / "qemu-system-x86_64"
        binary.write_text(FAKE_QEMU)
        binary.chmod(0o755)
        selected_log = self.inputs / "selected-serial.raw"
        (self.inputs / "qemu.log").write_bytes(b"stale unrelated default file")
        environment = os.environ.copy()
        environment.pop("A01_QEMU_BIOS", None)
        environment.pop("A01_QEMU_DATA_DIR", None)
        if bios_override is not None:
            environment["A01_QEMU_BIOS"] = bios_override
        if data_override is not None:
            environment["A01_QEMU_DATA_DIR"] = data_override
        environment.update({
            "PATH": str(tools) + os.pathsep + environment.get("PATH", ""),
            "A01_QEMU_EVIDENCE": str(self.directory / "qemu.json"),
            "A01_QEMU_TIMEOUT": "1" if timeout else "5",
            "FIXTURE_SERIAL_SOURCE": str(REAL_SERIAL), "FIXTURE_SERIAL_DEST": str(selected_log),
            "FIXTURE_NO_SERIAL": "1" if no_serial else "0", "FIXTURE_TIMEOUT": "1" if timeout else "0",
            "FIXTURE_LOADED": str(self.root / "loaded.json"),
            "FIXTURE_VERSION_MARKER": str(self.root / "version-started"),
            "FIXTURE_REPLACE_SOURCES": json.dumps([str(self.inputs / item["path"])
                for item in self.record["artifacts"].values()] if replace_sources else []),
            "FIXTURE_TAMPER_SNAPSHOT": "1" if tamper_snapshot else "0",
            "FIXTURE_DELETE_AFTER_VERSION": "1" if delete_binary else "0",
        })
        argv = [sys.executable, "-I", *(["-O"] if sys.flags.optimize else []), str(RECORDER)]
        if artifact_args is None:
            for option, artifact in self.record["artifacts"].items():
                argv.extend((option, artifact["path"]))
        else:
            argv.extend(artifact_args)
        argv.extend(("-chardev", "stdio,id=other,logfile=unrelated.log", "-serial", "chardev:serial",
                     "-chardev", "stdio,id=serial,signal=off,logfile=selected-serial.raw"))
        result = subprocess.run(argv, cwd=self.inputs, env=environment, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, text=True, timeout=10)
        self._recorder_calls = getattr(self, "_recorder_calls", 0) + 1
        prefix = self.root / f"recorder-{self._recorder_calls:03d}"
        prefix.with_suffix(".log").write_text(result.stdout)
        prefix.with_suffix(".json").write_text(json.dumps({"argv": argv, "cwd": str(self.inputs),
            "selected_environment": {key: environment[key] for key in environment
                if key.startswith(("FIXTURE_", "A01_QEMU_"))}, "returncode": result.returncode,
            "source_sha256": hashlib.sha256(RECORDER.read_bytes()).hexdigest()}, indent=2) + "\n")
        return result, json.loads((self.directory / "qemu.json").read_text()), selected_log

    def test_recorder_binds_complete_actual_chardev_log_and_inputs(self):
        result, record, selected_log = self.run_recorder()
        self.assertEqual(result.returncode, 33, result.stdout)
        self.assertEqual(record["serial_path"], str(selected_log))
        self.assertEqual(record["serial_sha256"], hashlib.sha256(self.raw_serial).hexdigest())
        self.assertEqual(record["serial_size"], len(self.raw_serial))
        for option, original in self.record["artifacts"].items():
            artifact = record["artifacts"][option]
            self.assertEqual(artifact["sha256"], original["sha256"])
            self.assertEqual(artifact["size"], original["size"])
            self.assertEqual(artifact["source"]["requested_path"], original["path"])
            self.assertEqual(artifact["source"]["path"], str(self.inputs / original["path"]))
            self.assertNotEqual(artifact["path"], artifact["source"]["path"])
        self.check(True)
        self.check(True, live=True)

    def test_recorder_explicit_private_bios_with_spaces_uses_selected_snapshot(self):
        private = self.root / "private firmware with spaces" / "bios 256k.bin"
        private.parent.mkdir()
        private.write_bytes(b"private firmware bytes selected explicitly")
        for missing_original in (False, True):
            with self.subTest(missing_original=missing_original):
                if missing_original:
                    (self.inputs / "bios.bin").unlink()
                result, record, _ = self.run_recorder(bios_override=str(private))
                self.assertEqual(result.returncode, 33, result.stdout)
                self.assertEqual(record["bios_selection"], {
                    "origin": "A01_QEMU_BIOS", "original_requested_path": "bios.bin",
                    "selected_path": str(private),
                })
                original = record["requested_qemu_args"]
                self.assertEqual(original[original.index("-bios") + 1], "bios.bin")
                artifact = record["artifacts"]["-bios"]
                self.assertEqual(artifact["source"]["requested_path"], str(private))
                self.assertEqual(artifact["source"]["path"], str(private))
                self.assertEqual(artifact["sha256"], hashlib.sha256(private.read_bytes()).hexdigest())
                self.assertNotEqual(artifact["path"], str(private))
                loaded = json.loads((self.root / "loaded.json").read_text())
                self.assertEqual(loaded["artifacts"]["-bios"]["path"], artifact["path"])
                self.assertEqual(loaded["artifacts"]["-bios"]["sha256"], artifact["sha256"])
                self.check(True, live=True)

    def test_recorder_rejects_invalid_explicit_bios_before_any_tool_execution(self):
        for value in ("", "bios.bin", str(self.root / "missing-private-bios"), str(self.inputs)):
            with self.subTest(value=value):
                result, record, _ = self.run_recorder(bios_override=value)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertEqual(record["stage"], "artifact_preparation_failed")
                self.assertIsNone(record["raw_exit_code"])
                self.assertEqual(record["bios_selection"]["origin"], "A01_QEMU_BIOS")
                self.assertEqual(record["bios_selection"]["selected_path"], value)
                self.assertFalse((self.root / "version-started").exists())
                self.assertFalse((self.root / "loaded.json").exists())
                self.assertEqual(record["artifacts"], {})
                self.assertEqual(list(self.directory.glob("artifacts-*")), [])

    def test_recorder_explicit_private_data_directory_with_spaces_appends_one_L(self):
        private = self.root / "private QEMU data with spaces"
        private.mkdir()
        result, record, _ = self.run_recorder(data_override=str(private))
        self.assertEqual(result.returncode, 33, result.stdout)
        self.assertEqual(record["data_selection"], {
            "origin": "A01_QEMU_DATA_DIR", "original_requested_paths": [],
            "selected_path": str(private), "appended": True,
        })
        self.assertNotIn("-L", record["requested_qemu_args"])
        loaded = json.loads((self.root / "loaded.json").read_text())
        self.assertEqual(loaded["argv"].count("-L"), 1)
        self.assertEqual(loaded["argv"][loaded["argv"].index("-L") + 1], str(private))
        for option in ("-kernel", "-initrd", "-bios"):
            self.assertEqual(loaded["artifacts"][option]["path"], record["artifacts"][option]["path"])
        self.check(True, live=True)

    def test_recorder_rejects_invalid_or_ambiguous_data_directory_before_tools(self):
        private = self.root / "private data"
        private.mkdir()
        normal = ["-kernel", "kernel.elf", "-initrd", "initramfs.cpio.gz", "-bios", "bios.bin"]
        for value, arguments in (("", None), ("relative-data", None),
                (str(self.root / "missing-data"), None), (str(self.inputs / "bios.bin"), None),
                (str(private), normal + ["-L", "original requested data"])):
            with self.subTest(value=value, arguments=arguments):
                result, record, _ = self.run_recorder(data_override=value, artifact_args=arguments)
                self.assertEqual(result.returncode, 1, result.stdout)
                self.assertEqual(record["stage"], "artifact_preparation_failed")
                self.assertIsNone(record["raw_exit_code"])
                self.assertEqual(record["data_selection"]["origin"], "A01_QEMU_DATA_DIR")
                self.assertFalse(record["data_selection"]["appended"])
                self.assertFalse((self.root / "version-started").exists())
                self.assertFalse((self.root / "loaded.json").exists())
                self.assertEqual(record["artifacts"], {})
                self.assertEqual(list(self.directory.glob("artifacts-*")), [])

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

    def test_recorder_snapshots_survive_atomic_replacement_of_all_source_paths(self):
        result, record, _ = self.run_recorder(replace_sources=True)
        command = [sys.executable, "-I", *(["-O"] if sys.flags.optimize else []),
                   str(CHECKER), str(self.directory), "--live-artifacts"]
        live = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, timeout=10)
        loaded = json.loads((self.root / "loaded.json").read_text())
        (self.root / "replacement-observation.json").write_text(json.dumps({
            "kind": "actual_recorder_cli_with_fake_QEMU_no_guest",
            "source_sha256": hashlib.sha256(RECORDER.read_bytes()).hexdigest(),
            "recorder_exit": result.returncode, "live_checker_argv": command,
            "live_checker_exit": live.returncode, "live_checker_output": live.stdout,
            "fake_QEMU_loaded": loaded, "record": record,
            "replaced_sources": {option: hashlib.sha256((self.inputs / artifact["path"]).read_bytes()).hexdigest()
                for option, artifact in self.record["artifacts"].items()}}, indent=2) + "\n")
        self.assertEqual(result.returncode, 33, result.stdout)
        self.assertEqual(live.returncode, 0, live.stdout)
        for option, original in self.record["artifacts"].items():
            artifact = record["artifacts"][option]
            self.assertEqual(loaded["artifacts"][option]["sha256"], original["sha256"])
            self.assertEqual(loaded["artifacts"][option]["path"], artifact["path"])
            self.assertEqual(artifact["source"]["sha256"], original["sha256"])
            self.assertNotEqual(artifact["path"], str(self.inputs / original["path"]))
            self.assertNotEqual(hashlib.sha256((self.inputs / original["path"]).read_bytes()).hexdigest(),
                                original["sha256"])

    def test_recorder_rejects_missing_duplicate_and_valueless_artifacts_before_version_probe(self):
        normal = ["-kernel", "kernel.elf", "-initrd", "initramfs.cpio.gz", "-bios", "bios.bin"]
        for index in (0, 2, 4):
            for kind, arguments in (
                ("missing", normal[:index] + normal[index + 2:]),
                ("duplicate", normal + normal[index:index + 2]),
                ("valueless", normal[:index] + normal[index + 2:] + [normal[index]]),
                ("empty", normal[:index + 1] + [""] + normal[index + 2:]),
            ):
                with self.subTest(option=normal[index], kind=kind):
                    result, record, _ = self.run_recorder(artifact_args=arguments)
                    self.assertEqual(result.returncode, 1, result.stdout)
                    self.assertEqual(record["stage"], "artifact_preparation_failed")
                    self.assertIn("error", record)
                    self.assertIsNone(record["raw_exit_code"])
                    self.assertFalse((self.root / "version-started").exists())
                    self.assertFalse((self.root / "loaded.json").exists())
                    self.assertEqual(list(self.directory.glob("artifacts-*")), [])

    def test_capture_rejects_in_place_mutation_and_path_replacement_during_fd_read(self):
        source = self.inputs / "changing-input"
        for mode in ("in-place", "replace"):
            with self.subTest(mode=mode):
                source.write_bytes(b"stable original bytes")
                destination = self.directory / (mode + ".snapshot")
                original_read, fired = SNAPSHOT.os.read, []

                def mutate_after_read(descriptor, count):
                    data = original_read(descriptor, count)
                    if not fired:
                        fired.append(True)
                        if mode == "in-place":
                            source.write_bytes(b"changed during open FD read")
                        else:
                            replacement = source.with_suffix(".new")
                            replacement.write_bytes(b"replacement inode during open FD read")
                            replacement.replace(source)
                    return data

                with mock.patch.object(SNAPSHOT.os, "read", side_effect=mutate_after_read):
                    with self.assertRaisesRegex(ValueError, "changed"):
                        SNAPSHOT.capture_artifact(source, destination)
                self.assertTrue(fired)

    def test_capture_exclusive_creation_preserves_existing_snapshot_bytes(self):
        source, destination = self.inputs / "kernel.elf", self.directory / "existing.snapshot"
        destination.write_bytes(b"pre-existing snapshot must survive")
        with self.assertRaises(FileExistsError):
            SNAPSHOT.capture_artifact(source, destination)
        self.assertEqual(destination.read_bytes(), b"pre-existing snapshot must survive")

    def test_recorder_rejects_nonregular_source_with_explicit_failure_record(self):
        result, record, _ = self.run_recorder(artifact_args=["-kernel", str(self.inputs),
            "-initrd", "initramfs.cpio.gz", "-bios", "bios.bin"])
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(record["stage"], "artifact_preparation_failed")
        self.assertIn("regular file", record["error"])
        self.assertFalse((self.root / "version-started").exists())
        self.assertFalse((self.root / "loaded.json").exists())

    def test_recorder_detects_snapshot_tampering_after_raw_guest_exit_without_source_fallback(self):
        result, record, _ = self.run_recorder(tamper_snapshot=True)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(record["raw_exit_code"], 33)
        self.assertEqual(record["stage"], "artifact_verification_failed")
        self.assertIn("error", record)
        self.assertEqual(record["recorder_exit_code"], 1)
        self.assertNotEqual(record["artifacts"]["-kernel"]["path"], str(self.inputs / "kernel.elf"))
        self.check(False, live=True)

    def test_recorder_creates_distinct_private_snapshot_directories_without_reuse(self):
        first_result, first, _ = self.run_recorder()
        first_bytes = {option: Path(artifact["path"]).read_bytes()
                       for option, artifact in first["artifacts"].items()}
        second_result, second, _ = self.run_recorder()
        self.assertEqual(first_result.returncode, 33, first_result.stdout)
        self.assertEqual(second_result.returncode, 33, second_result.stdout)
        self.assertNotEqual(first["snapshot_directory"]["path"], second["snapshot_directory"]["path"])
        for record in (first, second):
            directory = Path(record["snapshot_directory"]["path"])
            self.assertEqual(directory.parent, self.directory)
            self.assertEqual(directory.stat().st_mode & 0o777, 0o700)
            for option, artifact in record["artifacts"].items():
                self.assertEqual(Path(artifact["path"]).parent, directory)
                self.assertEqual(Path(artifact["path"]).read_bytes(), first_bytes[option])
                self.assertEqual(Path(artifact["path"]).stat().st_mode & 0o777, 0o400)

    def test_recorder_launch_failure_retains_explicit_failure_record_and_snapshots(self):
        result, record, _ = self.run_recorder(delete_binary=True)
        self.assertEqual(result.returncode, 1, result.stdout)
        self.assertEqual(record["stage"], "qemu_failed")
        self.assertIn("error", record)
        self.assertIsNone(record["raw_exit_code"])
        self.assertEqual(record["recorder_exit_code"], 1)
        self.assertEqual(len(record["artifacts"]), 3)
        self.assertTrue(all(Path(item["path"]).is_file() for item in record["artifacts"].values()))


class RecorderTimeoutTests(unittest.TestCase):
    """In-process launch mocks; no QEMU, SDK or guest is executed."""

    def exercise_timeout(self, value, accepted):
        with tempfile.TemporaryDirectory(prefix="a01-timeout-validation-") as temporary:
            root = Path(temporary)
            argv = [str(RECORDER)]
            for option, name in SNAPSHOT.ARTIFACT_NAMES.items():
                artifact = root / name
                artifact.write_bytes(("host-only input " + option).encode())
                argv.extend((option, str(artifact)))
            destination = root / "qemu.json"
            child = mock.MagicMock()
            child.pid, child.wait.return_value = 12345, 33
            launch = mock.MagicMock()
            launch.return_value.__enter__.return_value = child
            with mock.patch.dict(os.environ, {"A01_QEMU_EVIDENCE": str(destination),
                                               "A01_QEMU_TIMEOUT": value}, clear=True), \
                    mock.patch.object(SNAPSHOT.sys, "argv", argv), \
                    mock.patch.object(SNAPSHOT.shutil, "which", return_value=__file__), \
                    mock.patch.object(SNAPSHOT.subprocess, "check_output", return_value="host mock") as version, \
                    mock.patch.object(SNAPSHOT.subprocess, "Popen", launch):
                status = SNAPSHOT.main()
            record = json.loads(destination.read_text())
            self.assertEqual(record["timeout_requested"], value)
            if accepted:
                self.assertEqual(status, 33, record)
                launch.assert_called_once()
                child.wait.assert_called_once_with(timeout=int(value))
                self.assertEqual(record["timeout_seconds"], int(value))
                self.assertEqual(record["raw_exit_code"], 33)
            else:
                self.assertEqual(status, 1, record)
                launch.assert_not_called()
                version.assert_not_called()
                self.assertEqual(record["stage"], "artifact_preparation_failed")
                self.assertIsNone(record["raw_exit_code"])
                self.assertIn("A01_QEMU_TIMEOUT", record["error"])
                self.assertFalse(record["artifacts"])
                self.assertNotIn("qemu_pid", record)

    def test_invalid_timeout_is_rejected_before_any_tool_or_snapshot(self):
        for value in ("", "garbage", "nan", "inf", "-inf", "1.5", "0", "-1", "9" * 1000):
            with self.subTest(value=value[:40]):
                self.exercise_timeout(value, False)

    def test_positive_integer_timeout_is_parsed_before_launch_and_recorded(self):
        for value in ("1", "300"):
            with self.subTest(value=value):
                self.exercise_timeout(value, True)


if __name__ == "__main__":
    unittest.main(verbosity=2)
