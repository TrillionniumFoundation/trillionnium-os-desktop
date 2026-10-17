"""Production recorder CLI with disposable QEMU tools; no VM is executed."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
DEFAULT_BIOS = Path("/usr/share/seabios/bios-256k.bin")


class PrivateToolsTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="a01-integration-private-tools-")
        self.addCleanup(temporary.cleanup)
        setting = os.environ.get("A01_INTEGRATION_PRIVATE_OUT")
        self.root = Path(setting) / self._testMethodName if setting else Path(temporary.name)
        if setting:
            self.root.mkdir(parents=True, exist_ok=False)
        project = self.root / "fixture-project"
        self.recorder = project / "support/build/osdk-integration/record-qemu.py"
        self.recorder.parent.mkdir(parents=True)
        source = Path(os.environ.get("A01_INTEGRATION_RECORDER_SOURCE", str(HERE / "record-qemu.py")))
        shutil.copyfile(source, self.recorder)
        self.shared = self.recorder.parent.parent / "record-qemu.py"
        shutil.copyfile(HERE.parent / "record-qemu.py", self.shared)
        self.work = self.root / "work"
        self.work.mkdir()
        self.kernel = self.work / "kernel input.elf"
        self.kernel.write_bytes(b"disposable kernel fixture, no guest\n")
        self.bios = self.root / "private tools with spaces/firmware chosen.bin"
        self.bios.parent.mkdir()
        self.bios.write_bytes(b"explicit private BIOS fixture\n")
        self.data = self.root / "private tools with spaces/qemu data"
        self.data.mkdir()
        self.tools = self.root / "tools"
        self.tools.mkdir()
        binary = self.tools / "qemu-system-x86_64"
        binary.write_text("#!" + sys.executable + "\n"
            "import hashlib,json,os,sys\nfrom pathlib import Path\n"
            "if '--version' in sys.argv:\n"
            " Path(os.environ['FIXTURE_VERSION_MARKER']).write_text('version called\\n')\n"
            " print('executable host QEMU fixture; no VM');raise SystemExit(0)\n"
            "loaded={}\n"
            "for option in ('-kernel','-initrd','-bios'):\n"
            " if option in sys.argv:\n"
            "  path=Path(sys.argv[sys.argv.index(option)+1]);raw=path.read_bytes()\n"
            "  loaded[option]={'path':str(path),'size':len(raw),'sha256':hashlib.sha256(raw).hexdigest()}\n"
            "for index,value in enumerate(sys.argv[:-1]):\n"
            " if value=='-chardev':\n"
            "  for field in sys.argv[index+1].split(','):\n"
            "   if field.startswith('logfile='):Path(field.split('=',1)[1]).write_bytes(b'fixture serial, no guest\\n')\n"
            "Path(os.environ['FIXTURE_EXECUTION_RECORD']).write_text(json.dumps({'argv':sys.argv,'loaded':loaded}))\n"
            "print('host fixture completed; no guest executed');raise SystemExit(33)\n")
        binary.chmod(0o755)
        self.count = 0

    def run_cli(self, extra=(), updates=None, *, private=True, default_bios=None):
        self.count += 1
        output = self.root / f"case-{self.count:03d}"
        version, execution = self.root / f"version-{self.count:03d}", self.root / f"execution-{self.count:03d}.json"
        env = os.environ.copy()
        for name in ("A01_QEMU_BIOS", "A01_QEMU_DATA_DIR", "A01_OSDK_COVERAGE_GDB", "A01_OSDK_GDB_READY"):
            env.pop(name, None)
        env.update(PATH=str(self.tools) + os.pathsep + env.get("PATH", ""),
            A01_OSDK_CASE_OUTPUT=str(output), A01_OSDK_LOCAL_TCP="0", A01_OSDK_PROFILE="osdk-native-unix-v1",
            FIXTURE_VERSION_MARKER=str(version), FIXTURE_EXECUTION_RECORD=str(execution))
        if private:
            env.update(A01_QEMU_BIOS=str(self.bios), A01_QEMU_DATA_DIR=str(self.data))
        if updates:
            env.update(updates)
        arguments = ["-kernel", str(self.kernel), *extra]
        python = [sys.executable, "-I", *(["-O"] if sys.flags.optimize else [])]
        if default_bios is None:
            command = [*python, str(self.recorder), *arguments]
        else:
            # Explicitly label the default-only fixture. The primary private
            # tests above execute the production CLI without this substitution.
            wrapper = self.root / f"default-fixture-{self.count:03d}.py"
            wrapper.write_text("import importlib.util,sys\nfrom pathlib import Path\n"
                f"s=importlib.util.spec_from_file_location('recorder',{str(self.recorder)!r})\n"
                "m=importlib.util.module_from_spec(s);s.loader.exec_module(m)\n"
                f"m.FIRMWARE=Path({str(default_bios)!r})\n"
                f"sys.argv=[{str(self.recorder)!r},*sys.argv[1:]]\nraise SystemExit(m.main())\n")
            command = [*python, str(wrapper), *arguments]
        process = subprocess.run(command, cwd=self.work, env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, timeout=10)
        record_path = output / "guests/guest-001/qemu.json"
        record = json.loads(record_path.read_text())
        observation = {"kind": "production_CLI_with_executable_host_QEMU_fixture_no_VM",
            "default_BIOS_substitution": str(default_bios) if default_bios else None,
            "argv": command, "cwd": str(self.work), "returncode": process.returncode,
            "source_sha256": hashlib.sha256(self.recorder.read_bytes()).hexdigest(),
            "shared_source_sha256": hashlib.sha256(self.shared.read_bytes()).hexdigest(),
            "selected_environment": {key: value for key, value in env.items()
                if key.startswith(("A01_QEMU_", "A01_OSDK_", "FIXTURE_"))},
            "host_default_BIOS_exists": DEFAULT_BIOS.exists(),
            "version_called": version.exists(), "QEMU_fixture_executed": execution.exists(),
            "record": record}
        (self.root / f"invocation-{self.count:03d}.json").write_text(json.dumps(observation, indent=2) + "\n")
        (self.root / f"console-{self.count:03d}.log").write_bytes(process.stdout)
        return process, record, observation, execution

    def test_private_environment_reaches_unmodified_cli_with_spaces_and_missing_requested_bios(self):
        missing = self.root / "missing upstream BIOS.bin"
        process, record, observation, execution = self.run_cli(("-bios", str(missing), "-m", "8G"))
        self.assertEqual(process.returncode, 33, process.stdout)
        self.assertFalse(missing.exists())
        self.assertTrue(observation["QEMU_fixture_executed"])
        self.assertEqual(record["artifacts"]["-bios"]["sha256"], hashlib.sha256(self.bios.read_bytes()).hexdigest())
        self.assertEqual(record["artifacts"]["-bios"]["path"], str(self.bios))
        self.assertEqual(record["argv"][record["argv"].index("-bios") + 1], str(self.bios))
        self.assertEqual(record["argv"][record["argv"].index("-L") + 1], str(self.data))
        self.assertEqual(record["bios_selection"]["origin"], "A01_QEMU_BIOS")
        self.assertEqual(record["bios_selection"]["original_requested_path"], str(DEFAULT_BIOS))
        self.assertEqual(record["data_selection"]["origin"], "A01_QEMU_DATA_DIR")
        self.assertTrue(record["data_selection"]["appended"])
        self.assertNotIn("-L", record["fixed_profile_args"])
        self.assertEqual(record["fixed_profile_args"][record["fixed_profile_args"].index("-bios") + 1], str(DEFAULT_BIOS))
        self.assertEqual(record["shared_selector_source"]["sha256"], observation["shared_source_sha256"])
        self.assertEqual(json.loads(execution.read_text())["loaded"]["-bios"], record["artifacts"]["-bios"])

    def test_invalid_private_inputs_fail_before_version_or_execution(self):
        for name, values in (
            ("A01_QEMU_BIOS", ["", "relative.bin", str(self.data), str(self.root / "missing")]),
            ("A01_QEMU_DATA_DIR", ["", "relative", str(self.bios), str(self.root / "missing")]),
        ):
            for value in values:
                with self.subTest(name=name, value=value):
                    process, record, observation, _ = self.run_cli(updates={name: value})
                    self.assertEqual(process.returncode, 125, process.stdout)
                    self.assertIsNone(record["raw_exit_code"])
                    self.assertIn(name, record["error"])
                    self.assertFalse(observation["version_called"])
                    self.assertFalse(observation["QEMU_fixture_executed"])

    def test_private_data_directory_cannot_combine_with_single_or_duplicate_L(self):
        for extra in (("-L", "original"), ("-L", "first", "-L", "second")):
            with self.subTest(extra=extra):
                process, record, observation, _ = self.run_cli(extra)
                self.assertEqual(process.returncode, 125, process.stdout)
                self.assertIn("cannot be combined with a requested -L", record["error"])
                self.assertFalse(observation["version_called"])
                self.assertFalse(observation["QEMU_fixture_executed"])

    def test_unset_environment_preserves_default_with_fixture_firmware(self):
        process, record, observation, _ = self.run_cli(private=False, default_bios=self.bios)
        self.assertEqual(process.returncode, 33, process.stdout)
        self.assertEqual(record["bios_selection"]["origin"], "requested_qemu_args")
        self.assertEqual(record["bios_selection"]["selected_path"], str(self.bios))
        self.assertEqual(record["data_selection"]["selected_path"], None)
        self.assertFalse(record["data_selection"]["appended"])
        self.assertNotIn("-L", record["argv"])

    def test_private_inputs_do_not_enable_capture_or_switch_default_UNIX_profile(self):
        process, record, observation, _ = self.run_cli(updates={"A01_OSDK_COVERAGE_GDB": "1"})
        self.assertEqual(process.returncode, 125, process.stdout)
        self.assertIn("requires the explicit v2 local TCP profile", record["error"])
        self.assertFalse(observation["version_called"])
        self.assertFalse(observation["QEMU_fixture_executed"])
        process, record, _, _ = self.run_cli(("-gdb", "unix:/tmp/disposable-original-gdb", "-S"))
        self.assertEqual(process.returncode, 33, process.stdout)
        self.assertEqual(record["profile_id"], "osdk-native-unix-v1")
        self.assertEqual(record["control_transport"], "upstream-original")
        self.assertIn("unix:/tmp/disposable-original-gdb", record["argv"])

    def test_private_inputs_preserve_network_disk_and_nonloopback_control_rejections(self):
        for extra in (("-netdev", "user,id=net0"), ("-device", "virtio-net-pci,netdev=net0"),
                      ("-drive", "file=forbidden.img"), ("-readconfig", "forbidden.conf")):
            with self.subTest(extra=extra):
                process, record, observation, _ = self.run_cli(extra)
                self.assertEqual(process.returncode, 125, process.stdout)
                self.assertIn("forbids", record["error"])
                self.assertFalse(observation["version_called"])
                self.assertFalse(observation["QEMU_fixture_executed"])
        process, record, observation, _ = self.run_cli(("-gdb", "tcp:0.0.0.0:12345", "-S"),
            {"A01_OSDK_LOCAL_TCP": "1", "A01_OSDK_PROFILE": "osdk-native-local-tcp-v1"})
        self.assertEqual(process.returncode, 125, process.stdout)
        self.assertIn("requires explicit 127.0.0.1", record["error"])
        self.assertFalse(observation["version_called"])
        self.assertFalse(observation["QEMU_fixture_executed"])


if __name__ == "__main__":
    unittest.main()
