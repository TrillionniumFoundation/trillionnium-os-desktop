"""Actual recorder CLI with executable host fixtures; no QEMU VM or GDB runs.

Set A01_INPUT_SNAPSHOTS_OUT to preserve fixture inputs, complete invocation
records, CLI output, and all retained guest files for independent review.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import textwrap
import unittest


HERE = Path(__file__).resolve().parent
CAPTURE_PROFILE = "osdk-native-local-tcp-gdb-capture-v2"
EM62 = b"\x7fELF\x02\x01" + bytes(12) + b"\x3e\x00" + bytes(44)


def digest(data):
    return hashlib.sha256(data).hexdigest()


class InputSnapshotCliTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="a01-input-snapshots-")
        self.addCleanup(temporary.cleanup)
        retained = os.environ.get("A01_INPUT_SNAPSHOTS_OUT")
        self.root = Path(retained) / self._testMethodName if retained else Path(temporary.name)
        if retained:
            self.root.mkdir(parents=True, exist_ok=False)
        self.recorder = self.root / "fixture project/support/build/osdk-integration/record-qemu.py"
        self.recorder.parent.mkdir(parents=True)
        selected = Path(os.environ.get("A01_INTEGRATION_RECORDER_SOURCE", str(HERE / "record-qemu.py")))
        shutil.copyfile(selected, self.recorder)
        self.shared = self.recorder.parent.parent / "record-qemu.py"
        shutil.copyfile(HERE.parent / "record-qemu.py", self.shared)
        self.work = self.root / "work with spaces"
        self.work.mkdir()
        self.kernel = self.work / "original kernel.elf"
        self.bios = self.work / "original BIOS.bin"
        self.initrd = self.work / "original initramfs.cpio.gz"
        self.symbol = self.work / "original symbol.elf"
        self.initial = {"-kernel": b"host kernel input, no guest\n",
                        "-bios": b"host BIOS input, no firmware\n",
                        "-initrd": b"host initrd input, no filesystem\n"}
        for option, path in self.inputs().items():
            path.write_bytes(self.initial[option])
        self.symbol.write_bytes(EM62 + b"host symbols, no executable code\n")
        self.tools = self.root / "executable host fixtures"
        self.tools.mkdir()
        qemu = self.tools / "qemu-system-x86_64"
        qemu.write_text("#!" + sys.executable + "\n" + textwrap.dedent('''\
            import hashlib,json,os,sys,time
            from pathlib import Path
            def replace_sources(stage):
                if os.environ.get('FIXTURE_REPLACE_AT') == stage:
                    for name in json.loads(os.environ['FIXTURE_SOURCE_PATHS']):
                        path=Path(name);original=path.read_bytes()
                        replacement=b'overwritten original source, host fixture only\\n'
                        if original[:6]==b'\\x7fELF\\x02\\x01' and original[18:20]==b'\\x3e\\x00':
                            replacement=original[:64]+replacement
                        path.write_bytes(replacement)
            def tamper(stage):
                if os.environ.get('FIXTURE_TAMPER_AT') == stage:
                    target=Path(os.environ['FIXTURE_CASE'])/'guests'
                    guest=sorted(target.glob('guest-*'))[-1]
                    path=guest/'artifacts'/os.environ['FIXTURE_TAMPER_NAME']
                    path.chmod(0o600)
                    path.write_bytes(b'tampered private input\\n')
                    path.chmod(0o400)
            if '--version' in sys.argv:
                Path(os.environ['FIXTURE_VERSION_MARKER']).write_text('host fixture version probe\\n')
                replace_sources('version');tamper('version')
                print('host fake QEMU; no VM');raise SystemExit(0)
            replace_sources('run')
            loaded={}
            incoming=iter(sys.argv[1:])
            for token in incoming:
                option='-'+token.lstrip('-')
                if option=='-append':
                    next(incoming);continue
                if option in ('-kernel','-initrd','-bios'):
                    path=Path(next(incoming));data=path.read_bytes()
                    loaded[option]={'path':str(path),'size':len(data),'sha256':hashlib.sha256(data).hexdigest()}
            raw=b'host fake raw profile\\n'
            serial=b'host fixture; no VM or GDB\\n'+('#### Coverage: 0x1000 %d\\n'%len(raw)).encode()
            for index,arg in enumerate(sys.argv[:-1]):
                if arg=='-chardev':
                    for field in sys.argv[index+1].split(','):
                        if field.startswith('logfile='):
                            Path(field.split('=',1)[1]).write_bytes(serial)
            Path(os.environ['FIXTURE_EXECUTION_RECORD']).write_text(json.dumps({'argv':sys.argv,'loaded':loaded}))
            if os.environ.get('FIXTURE_WAIT_CAPTURE')=='1':
                deadline=time.monotonic()+6
                while not Path(os.environ['FIXTURE_CAPTURE_DONE']).exists():
                    if time.monotonic()>deadline:raise SystemExit(97)
                    time.sleep(.01)
            tamper('run')
            print('host fake QEMU completed; no VM');raise SystemExit(33)
            '''))
        qemu.chmod(0o755)
        self.count = 0

    def inputs(self):
        return {"-kernel": self.kernel, "-bios": self.bios, "-initrd": self.initrd}

    def run_cli(self, *, initrd=True, aliases=False, extra=(), updates=None, output=None):
        self.count += 1
        output = output or self.root / f"case-{self.count:03d}"
        version = self.root / f"version-{self.count:03d}.txt"
        execution = self.root / f"execution-{self.count:03d}.json"
        env = os.environ.copy()
        for name in ("A01_QEMU_BIOS", "A01_QEMU_DATA_DIR", "A01_OSDK_COVERAGE_GDB",
                     "A01_OSDK_GDB_READY", "A01_OSDK_COVERAGE_SYMBOL_ELF"):
            env.pop(name, None)
        env.update(PATH=str(self.tools) + os.pathsep + env.get("PATH", ""),
                   A01_OSDK_CASE_OUTPUT=str(output), A01_QEMU_BIOS=str(self.bios),
                   A01_OSDK_LOCAL_TCP="0", A01_OSDK_PROFILE="osdk-native-unix-v1",
                   A01_OSDK_GUEST_TIMEOUT="8", FIXTURE_CASE=str(output),
                   FIXTURE_VERSION_MARKER=str(version), FIXTURE_EXECUTION_RECORD=str(execution),
                   FIXTURE_SOURCE_PATHS=json.dumps([str(p) for p in self.inputs().values()]),
                   FIXTURE_CAPTURE_DONE=str(self.root / "capture-completed"))
        if updates:
            env.update(updates)
        arguments = ["--kernel" if aliases else "-kernel", str(self.kernel)]
        if initrd:
            arguments += ["--initrd" if aliases else "-initrd", str(self.initrd)]
        python = [sys.executable, "-I", *(["-O"] if sys.flags.optimize else [])]
        command = [*python, str(self.recorder), *arguments, *extra]
        existing = set((output / "guests").glob("guest-*"))
        process = subprocess.run(command, cwd=self.work, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, timeout=12)
        new = set((output / "guests").glob("guest-*")) - existing
        self.assertEqual(len(new), 1, process.stdout)
        guest = new.pop()
        record = json.loads((guest / "qemu.json").read_text())
        observation = {"kind": "actual_recorder_CLI_with_host_fake_QEMU_and_optional_fake_capture_no_VM_no_GDB",
                       "argv": command, "cwd": str(self.work), "returncode": process.returncode,
                       "recorder_sha256": digest(self.recorder.read_bytes()),
                       "shared_recorder_sha256": digest(self.shared.read_bytes()),
                       "selected_environment": {k: v for k, v in env.items()
                                                if k.startswith(("A01_", "FIXTURE_"))},
                       "version_called": version.exists(), "execution_called": execution.exists(),
                       "record": record}
        (self.root / f"invocation-{self.count:03d}.json").write_text(json.dumps(observation, indent=2) + "\n")
        (self.root / f"console-{self.count:03d}.log").write_bytes(process.stdout)
        return process, record, observation, execution

    def assert_copies(self, record, loaded, expected):
        self.assertEqual(set(record["artifacts"]), set(expected))
        for option, original in expected.items():
            # Check what the executable fixture actually loaded before using
            # any new snapshot metadata, so the old CLI's red control exposes
            # the source-replacement bug directly rather than a missing field.
            self.assertEqual(loaded[option]["sha256"], digest(original))
            artifact = record["artifacts"][option]
            self.assertEqual(set(artifact), {"path", "size", "sha256"})
            self.assertEqual(artifact, loaded[option])
            self.assertNotEqual(artifact["path"], str(self.inputs()[option]))
            private = Path(artifact["path"])
            self.assertEqual(private.read_bytes(), original)
            self.assertEqual(stat.S_IMODE(private.stat().st_mode), 0o400)
            self.assertEqual(artifact["size"], len(original))
            self.assertEqual(artifact["sha256"], digest(original))
            source = record["artifact_sources"][option]
            self.assertEqual(source["path"], str(self.inputs()[option]))
            self.assertEqual(source["sha256"], digest(original))
            self.assertEqual(record["artifact_snapshots"][option]["sha256"], artifact["sha256"])
            selected = record["selected_profile_args"]
            selected_index = next(i for i, value in enumerate(selected) if "-" + value.lstrip("-") == option)
            actual_index = next(i for i, value in enumerate(record["argv"]) if "-" + value.lstrip("-") == option)
            self.assertEqual(selected[selected_index + 1], str(self.inputs()[option]))
            self.assertEqual(record["argv"][actual_index + 1], artifact["path"])
        self.assertEqual(record["snapshot_verification"], {"before_qemu": True, "after_qemu": True})

    def test_sources_replaced_during_version_still_load_original_three_copies(self):
        process, record, _, execution = self.run_cli(updates={"FIXTURE_REPLACE_AT": "version"})
        self.assertEqual(process.returncode, 33, process.stdout)
        self.assert_copies(record, json.loads(execution.read_text())["loaded"], self.initial)
        for option, path in self.inputs().items():
            self.assertNotEqual(path.read_bytes(), self.initial[option])

    def test_sources_replaced_before_fake_execution_still_load_original_copies(self):
        process, record, _, execution = self.run_cli(updates={"FIXTURE_REPLACE_AT": "run"})
        self.assertEqual(process.returncode, 33, process.stdout)
        self.assert_copies(record, json.loads(execution.read_text())["loaded"], self.initial)
        for option, path in self.inputs().items():
            self.assertNotEqual(path.read_bytes(), self.initial[option])

    def test_double_hyphen_inputs_and_literal_append_value_keep_their_meaning(self):
        process, record, _, execution = self.run_cli(aliases=True, extra=("-append", "-kernel"),
            updates={"FIXTURE_REPLACE_AT": "version"})
        self.assertEqual(process.returncode, 33, process.stdout)
        self.assert_copies(record, json.loads(execution.read_text())["loaded"], self.initial)
        self.assertIn("--kernel", record["argv"])
        self.assertIn("--initrd", record["argv"])
        self.assertEqual(record["argv"][record["argv"].index("-append") + 1], "-kernel")

    def test_initrd_is_optional_and_mandatory_copies_still_bind_actual_cli(self):
        self.initrd.unlink()
        process, record, _, execution = self.run_cli(initrd=False)
        self.assertEqual(process.returncode, 33, process.stdout)
        self.assertNotIn("-initrd", record["argv"])
        self.assert_copies(record, json.loads(execution.read_text())["loaded"],
                           {k: v for k, v in self.initial.items() if k != "-initrd"})

    def test_multiple_guests_preserve_each_copy_after_originals_are_overwritten(self):
        output = self.root / "shared case output with spaces"
        first, a, _, loaded_a = self.run_cli(output=output)
        self.assertEqual(first.returncode, 33, first.stdout)
        saved = {k: Path(v["path"]).read_bytes() for k, v in a["artifacts"].items()}
        for path in self.inputs().values():
            path.write_bytes(b"second invocation source\n")
        expected = {k: p.read_bytes() for k, p in self.inputs().items()}
        second, b, _, loaded_b = self.run_cli(output=output, updates={"FIXTURE_REPLACE_AT": "run"})
        self.assertEqual(second.returncode, 33, second.stdout)
        self.assert_copies(a, json.loads(loaded_a.read_text())["loaded"], self.initial)
        self.assert_copies(b, json.loads(loaded_b.read_text())["loaded"], expected)
        for option in saved:
            self.assertEqual(Path(a["artifacts"][option]["path"]).read_bytes(), saved[option])
            self.assertNotEqual(a["artifacts"][option]["path"], b["artifacts"][option]["path"])
        self.assertEqual(len(list((output / "guests").glob("guest-*"))), 2)

    def test_snapshot_tampered_by_version_probe_prevents_qemu_execution(self):
        for name in ("kernel.elf", "bios.bin", "initramfs.cpio.gz"):
            with self.subTest(snapshot=name):
                process, record, observation, _ = self.run_cli(
                    updates={"FIXTURE_TAMPER_AT": "version", "FIXTURE_TAMPER_NAME": name})
                self.assertEqual(process.returncode, 125, process.stdout)
                self.assertTrue(observation["version_called"])
                self.assertFalse(observation["execution_called"])
                self.assertIsNone(record["raw_exit_code"])
                self.assertIn("private input snapshot changed", record["error"])

    def test_snapshot_tampered_after_load_preserves_raw33_and_fails_wrapper(self):
        for name in ("kernel.elf", "bios.bin", "initramfs.cpio.gz"):
            with self.subTest(snapshot=name):
                process, record, observation, execution = self.run_cli(
                    updates={"FIXTURE_TAMPER_AT": "run", "FIXTURE_TAMPER_NAME": name})
                self.assertEqual(process.returncode, 125, process.stdout)
                self.assertTrue(observation["execution_called"])
                self.assertEqual(record["raw_exit_code"], 33)
                self.assertEqual(record["wrapper_exit_code"], 125)
                self.assertEqual(record["snapshot_verification"], {"before_qemu": True, "after_qemu": False})
                self.assertIn("private input snapshot changed", record["error"])
                self.assertEqual(json.loads(execution.read_text())["loaded"], record["artifacts"])

    def test_missing_directory_and_fifo_sources_fail_before_any_probe(self):
        for option in ("-kernel", "-bios", "-initrd"):
            original = self.inputs()[option]
            for invalid in ("missing", "directory", "fifo"):
                with self.subTest(option=option, invalid=invalid):
                    original.unlink()
                    if invalid == "missing":
                        pass
                    elif invalid == "directory":
                        original.mkdir()
                    else:
                        os.mkfifo(original)
                    try:
                        process, record, observation, _ = self.run_cli()
                        self.assertEqual(process.returncode, 125, process.stdout)
                        self.assertIsNone(record["raw_exit_code"])
                        self.assertFalse(observation["version_called"])
                        self.assertFalse(observation["execution_called"])
                    finally:
                        if original.is_dir():
                            original.rmdir()
                        elif os.path.lexists(original):
                            original.unlink()
                        original.write_bytes(self.initial[option])

    def test_duplicate_and_missing_initrd_values_fail_before_probe(self):
        for initrd, extra in ((True, ("-initrd", str(self.initrd))),
                              (False, ("-initrd",)),
                              (False, ("-initrd", "")),
                              (False, ("-initrd", "-append", "not an initrd"))):
            with self.subTest(initrd=initrd, extra=extra):
                process, record, observation, _ = self.run_cli(initrd=initrd, extra=extra)
                self.assertEqual(process.returncode, 125, process.stdout)
                self.assertIsNone(record["raw_exit_code"])
                self.assertFalse(observation["version_called"])
                self.assertFalse(observation["execution_called"])

    def assert_capture_uses_private_em62_after_source_change(self, stage):
        # This executable substitutes the capture/GDB job, not the recorder.
        # It creates a valid host-only sidecar to exercise production finalization.
        capture = self.recorder.with_name("capture.py")
        capture.write_text(textwrap.dedent('''\
            import argparse,hashlib,json,os,time
            from pathlib import Path
            p=argparse.ArgumentParser()
            for name in ('endpoint','symbol-elf','serial-log','raw-output','sidecar','kernel-sha256','guest-record','timeout'):
                p.add_argument('--'+name,required=True)
            a=p.parse_args();deadline=time.monotonic()+5
            while not Path(os.environ['FIXTURE_EXECUTION_RECORD']).exists():
                if time.monotonic()>deadline:raise SystemExit(94)
                time.sleep(.01)
            symbol=Path(a.symbol_elf);data=symbol.read_bytes()
            if data[:6]!=b'\\x7fELF\\x02\\x01' or data[18:20]!=b'\\x3e\\x00':raise SystemExit(95)
            if Path(os.environ['FIXTURE_ORIGINAL_SYMBOL']).read_bytes()==data:raise SystemExit(96)
            def record(path):
                path=Path(path).resolve();raw=path.read_bytes()
                return {'path':str(path),'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}
            raw=Path(a.raw_output);raw.write_bytes(b'host fake raw profile\\n')
            serial=Path(a.serial_log).read_bytes()
            sidecar={'passed':True,'profile_id':'osdk-native-local-tcp-gdb-capture-v2',
                'gdb_exit_code':0,'guest_record':a.guest_record,'kernel_sha256':a.kernel_sha256,
                'symbol_elf':record(symbol),'raw':record(raw),
                'breakpoint':{'symbol':'ostd::arch::power::try_poweroff','resolved_address':'0x2000','actual_pc':'0x2000'},
                'announcement':{'address':'0x1000','size':raw.stat().st_size},
                'serial_prefix':{'size':len(serial),'sha256':hashlib.sha256(serial).hexdigest()},
                'fixture_only_no_real_GDB':True}
            Path(a.sidecar).write_text(json.dumps(sidecar))
            Path(os.environ['FIXTURE_CAPTURE_DONE']).write_text('host fake capture completed\\n')
            '''))
        original_symbol = self.symbol.read_bytes()
        process, record, _, execution = self.run_cli(extra=("-gdb", "tcp:127.0.0.1:0", "-S"),
            updates={"A01_OSDK_LOCAL_TCP": "1", "A01_OSDK_PROFILE": CAPTURE_PROFILE,
                     "A01_OSDK_COVERAGE_GDB": "1", "A01_OSDK_COVERAGE_SYMBOL_ELF": str(self.symbol),
                     "FIXTURE_REPLACE_AT": stage, "FIXTURE_WAIT_CAPTURE": "1",
                     "FIXTURE_ORIGINAL_SYMBOL": str(self.symbol),
                     "FIXTURE_SOURCE_PATHS": json.dumps([str(p) for p in self.inputs().values()] + [str(self.symbol)])})
        self.assertEqual(process.returncode, 33, process.stdout)
        self.assert_copies(record, json.loads(execution.read_text())["loaded"], self.initial)
        captured = record["capture"]
        private = captured["symbol_elf"]
        self.assertNotEqual(private["path"], str(self.symbol))
        self.assertEqual(Path(private["path"]).read_bytes(), original_symbol)
        self.assertEqual(private["sha256"], digest(original_symbol))
        self.assertEqual(stat.S_IMODE(Path(private["path"]).stat().st_mode), 0o400)
        self.assertNotEqual(self.symbol.read_bytes(), original_symbol)
        self.assertEqual(record["coverage_symbol_source"]["path"], str(self.symbol))
        self.assertEqual(record["coverage_symbol_source"]["sha256"], digest(original_symbol))
        self.assertEqual(captured["argv"][captured["argv"].index("--symbol-elf") + 1], private["path"])
        self.assertEqual(captured["raw_exit_code"], 0)
        self.assertTrue(captured["finalized"])
        sidecar = json.loads(Path(captured["sidecar"]["path"]).read_text())
        self.assertTrue(sidecar["fixture_only_no_real_GDB"])
        self.assertTrue(sidecar["finalized"])
        self.assertEqual(sidecar["symbol_elf"], private)

    def test_capture_cli_uses_private_em62_after_original_symbol_and_kernel_change(self):
        self.assert_capture_uses_private_em62_after_source_change("run")

    def test_capture_cli_freezes_valid_symbols_before_qemu_version_probe(self):
        self.assert_capture_uses_private_em62_after_source_change("version")


if __name__ == "__main__":
    unittest.main()
