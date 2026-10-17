"""Exercise capture/GDB cleanup in the actual outer runner's process group.

The workload is a TCP lease held by native GDB, not a kernel or coverage test.
Set A01_CAPTURE_LIFECYCLE_OUT to retain all process and command evidence.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest


HERE = Path(__file__).resolve().parent
REAL_GDB = Path(os.environ.get("A01_GDB_REAL", shutil.which("gdb") or "/nonexistent/gdb"))


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def wait_json(path, timeout=10):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, json.JSONDecodeError):
            time.sleep(.01)
    raise AssertionError(f"process readiness timeout: {path}")


def pidfd_exited(descriptor, timeout):
    return bool(select.select([descriptor], [], [], timeout)[0])


def tcp_lease_released(address, timeout=3):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            try:
                probe.bind(tuple(address))
                return True
            except OSError:
                time.sleep(.01)
    return False


def fixture(root, recorder, capture):
    """Drive production run_capture and capture.py; substitute only the GDB job."""
    tools = root / "tools"
    tools.mkdir()
    symbol = root / "symbols.elf"
    symbol.write_bytes(b"\x7fELF\x02\x01" + bytes(12) + b"\x3e\x00" + bytes(44))
    (root / "serial.log").write_bytes(b"fixture, not a project kernel\n")
    gdb_work = ("import json,os,signal,socket,time; "
                "lease=socket.socket(); lease.bind(('127.0.0.1',0)); lease.listen(1); "
                "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                "signal.signal(signal.SIGINT,signal.SIG_IGN); "
                "open(os.environ['A01_LEASE_READY'],'w').write(json.dumps({"
                "'gdb_pid':os.getpid(),'helper_pid':os.getppid(),"
                "'group':os.getpgrp(),'address':lease.getsockname()})); time.sleep(60)")
    gdb_wrapper = ("#!/usr/bin/python3\nimport os,sys\n"
                   f"real={str(REAL_GDB)!r}\n"
                   "if '--version' in sys.argv:\n os.execv(real,[real,'--version'])\n"
                   f"os.execv(real,[real,'--batch','-nx','--quiet','-ex',{'python ' + gdb_work!r}])\n")
    (tools / "gdb").write_text(gdb_wrapper)
    (tools / "gdb").chmod(0o755)
    (tools / "nm").write_text("#!/bin/sh\nprintf 'ffffffff88001000 T ostd::arch::power::try_poweroff\\n'\n")
    (tools / "nm").chmod(0o755)
    capture_args = [sys.executable, "-I", str(capture), "--endpoint", "127.0.0.1:12345",
                    "--symbol-elf", str(symbol), "--serial-log", str(root / "serial.log"),
                    "--raw-output", str(root / "coverage.profraw"), "--sidecar", str(root / "capture.json"),
                    "--kernel-sha256", "a" * 64, "--guest-record", "fixture/qemu.json", "--timeout", "60"]
    qemu_work = ("import json,os,signal,socket,time; "
                 "lease=socket.socket(); lease.bind(('127.0.0.1',0)); lease.listen(1); "
                 "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                 "open('qemu-ready.json','w').write(json.dumps({'pid':os.getpid(),"
                 "'group':os.getpgrp(),'address':lease.getsockname()})); time.sleep(60)")
    recorder_driver = root / "recorder-driver.py"
    recorder_driver.write_text(
        "import importlib.util,json,subprocess,sys\nfrom pathlib import Path\n"
        f"spec=importlib.util.spec_from_file_location('recorder',{str(recorder)!r})\n"
        "recorder=importlib.util.module_from_spec(spec);spec.loader.exec_module(recorder)\n"
        f"qemu=subprocess.Popen([sys.executable,'-c',{qemu_work!r}])\n"
        f"metadata={{}}\nresult=recorder.run_capture(qemu,{capture_args!r},Path.cwd(),metadata,60)\n"
        "Path('recorder-result.json').write_text(json.dumps({'result':result,'capture':metadata}))\n")
    harness = root / "harness.py"
    harness.write_text("import subprocess,sys\n"
                       f"raise SystemExit(subprocess.call([sys.executable,'-I',{str(recorder_driver)!r}]))\n")
    outer = root / "outer.py"
    outer.write_text(
        "import importlib.util,json,os,sys\nfrom pathlib import Path\n"
        f"spec=importlib.util.spec_from_file_location('outer_runner',{str(HERE / 'run.py')!r})\n"
        "runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)\n"
        "try:\n with runner.interruption_handlers():\n"
        f"  result=runner.command([sys.executable,'-I',{str(harness)!r}],Path.cwd(),os.environ.copy(),Path('case.log'),float(sys.argv[1]))\n"
        "except runner.RunnerInterrupted as error:\n result={'interrupted_by':error.signum}\n"
        "Path('outer-result.json').write_text(json.dumps(result))\n")
    env = os.environ.copy()
    env["PATH"] = str(tools) + os.pathsep + env.get("PATH", "")
    env["A01_LEASE_READY"] = str(root / "gdb-ready.json")
    return outer, env, capture_args


class CaptureLifecycleTests(unittest.TestCase):
    def run_case(self, mode, baseline=False):
        self.assertTrue(REAL_GDB.is_file(), "native GDB is required for this lifecycle regression")
        root_setting = os.environ.get("A01_CAPTURE_LIFECYCLE_OUT")
        temporary = None
        if root_setting:
            root = Path(root_setting) / mode
            root.mkdir(parents=True, exist_ok=False)
        else:
            temporary = tempfile.TemporaryDirectory()
            root = Path(temporary.name)
        source = Path(os.environ.get("A01_CAPTURE_SOURCE", str(HERE)))
        outer, env, _ = fixture(root, source / "record-qemu.py", source / "capture.py")
        timeout = 4 if mode == "timeout" else 30
        descriptors = []
        process = None
        observation = {"kind": "capture_lifecycle_fixture_not_kernel", "mode": mode, "baseline": baseline,
                       "source": {name: hashlib.sha256((source / name).read_bytes()).hexdigest()
                                  for name in ("record-qemu.py", "capture.py")},
                       "real_gdb": str(REAL_GDB)}
        try:
            with (root / "outer.log").open("wb") as output:
                process = subprocess.Popen([sys.executable, "-I", str(outer), str(timeout)],
                                           cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT)
                ready = wait_json(root / "gdb-ready.json")
                qemu = wait_json(root / "qemu-ready.json")
                pids = {"helper": ready["helper_pid"], "gdb": ready["gdb_pid"], "qemu": qemu["pid"]}
                for name, pid in pids.items():
                    descriptors.append((name, os.pidfd_open(pid)))
                self.assertTrue(all(not pidfd_exited(fd, 0) for _, fd in descriptors))
                if mode != "timeout":
                    process.send_signal(signal.SIGINT if mode == "sigint" else signal.SIGTERM)
                process.wait(timeout=10)
                self.assertEqual(process.returncode, 0)
            observed = {name: pidfd_exited(fd, 3 if not baseline else 0) for name, fd in descriptors}
            gdb_released = tcp_lease_released(ready["address"], .1 if baseline else 3)
            qemu_released = tcp_lease_released(qemu["address"])
            command = json.loads((root / "case.command.json").read_text())
            observation.update({"ready": ready, "qemu": qemu, "pids": pids, "pidfd_exited": observed,
                                "gdb_tcp_lease_released": gdb_released,
                                "qemu_tcp_lease_released": qemu_released, "outer_command": command})
            if baseline:
                self.assertFalse(observed["helper"])
                self.assertFalse(observed["gdb"])
                self.assertFalse(gdb_released)
                self.assertNotEqual(ready["group"], command["group_cleanup"]["leader_pid"])
                observation["original_leak_reproduced"] = True
            else:
                self.assertTrue(all(observed.values()), observed)
                self.assertTrue(gdb_released)
                self.assertEqual(ready["group"], command["group_cleanup"]["leader_pid"])
            self.assertTrue(qemu_released)
            if mode == "timeout":
                self.assertTrue(command["timed_out"])
                self.assertEqual(command["raw_exit_code"], 124)
            else:
                self.assertEqual(command["interrupted_by"], mode.upper())
            observation["passed"] = True
        finally:
            # pidfds identify only this test's children/grandchildren, including
            # leaked original helpers. No recycled numeric PID/group is signaled.
            for _, descriptor in descriptors:
                try:
                    signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            for _, descriptor in descriptors:
                pidfd_exited(descriptor, 3)
                os.close(descriptor)
            if process is not None and process.poll() is None:
                # Let the production runner unwind and clean its owned group.
                process.terminate()
                process.wait(timeout=10)
            (root / "observation.json").write_text(json.dumps(observation, indent=2) + "\n")
            if temporary is not None:
                temporary.cleanup()

    def test_outer_timeout_reaches_capture_and_real_gdb(self):
        self.run_case("timeout", baseline=os.environ.get("A01_CAPTURE_EXPECT_ORIGINAL_LEAK") == "1")

    @unittest.skipIf(os.environ.get("A01_CAPTURE_EXPECT_ORIGINAL_LEAK") == "1", "baseline is timeout only")
    def test_outer_sigint_reaches_capture_and_real_gdb(self):
        self.run_case("sigint")

    @unittest.skipIf(os.environ.get("A01_CAPTURE_EXPECT_ORIGINAL_LEAK") == "1", "baseline is timeout only")
    def test_outer_sigterm_reaches_capture_and_real_gdb(self):
        self.run_case("sigterm")

    @unittest.skipIf(os.environ.get("A01_CAPTURE_EXPECT_ORIGINAL_LEAK") == "1", "patched helper only")
    def test_standalone_helper_term_reaps_real_gdb(self):
        self.assertTrue(REAL_GDB.is_file(), "native GDB is required for this lifecycle regression")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(os.environ["A01_CAPTURE_LIFECYCLE_OUT"]) / "standalone" \
                if os.environ.get("A01_CAPTURE_LIFECYCLE_OUT") else Path(temporary)
            if root != Path(temporary):
                root.mkdir(parents=True, exist_ok=False)
            _, env, arguments = fixture(root, HERE / "record-qemu.py", HERE / "capture.py")
            shim = load(HERE / "record-qemu.py", "standalone_recorder")
            descriptors = []
            helper = None
            observation = {"kind": "standalone_capture_term_fixture_not_kernel"}
            try:
                with (root / "helper.log").open("wb") as output:
                    helper = subprocess.Popen(arguments, cwd=root, env=env,
                                              stdout=output, stderr=subprocess.STDOUT)
                    ready = wait_json(root / "gdb-ready.json")
                    descriptors = [("helper", os.pidfd_open(helper.pid)),
                                   ("gdb", os.pidfd_open(ready["gdb_pid"]))]
                    self.assertEqual(ready["helper_pid"], helper.pid)
                    shim.stop_capture_child(helper)
                exited = {name: pidfd_exited(fd, 3) for name, fd in descriptors}
                released = tcp_lease_released(ready["address"])
                sidecar = json.loads((root / "capture.json").read_text())
                observation.update({"ready": ready, "helper_returncode": helper.returncode,
                                    "pidfd_exited": exited, "gdb_tcp_lease_released": released,
                                    "capture_sidecar": sidecar})
                self.assertEqual(helper.returncode, 1)
                self.assertTrue(all(exited.values()), exited)
                self.assertTrue(released)
                self.assertFalse(sidecar["passed"])
                self.assertEqual(sidecar["interrupted_by"], "SIGTERM")
                observation["passed"] = True
            finally:
                for _, descriptor in descriptors:
                    try:
                        signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    pidfd_exited(descriptor, 3)
                    os.close(descriptor)
                if helper is not None and helper.poll() is None:
                    helper.kill()
                    helper.wait()
                (root / "observation.json").write_text(json.dumps(observation, indent=2) + "\n")

    @unittest.skipIf(os.environ.get("A01_CAPTURE_EXPECT_ORIGINAL_LEAK") == "1", "patched recorder only")
    def test_real_helper_failure_and_qemu_status_65_never_become_33(self):
        shim = load(HERE / "record-qemu.py", "status_recorder")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(os.environ["A01_CAPTURE_LIFECYCLE_OUT"]) / "statuses" \
                if os.environ.get("A01_CAPTURE_LIFECYCLE_OUT") else Path(temporary)
            if root != Path(temporary):
                root.mkdir(parents=True, exist_ok=False)
            records = []
            for mode in ("helper_failure", "qemu_failure_65"):
                output = root / mode
                output.mkdir()
                qemu_args = "import time;time.sleep(60)" if mode == "helper_failure" else "raise SystemExit(65)"
                helper_args = "raise SystemExit(7)" if mode == "helper_failure" else "import time;time.sleep(60)"
                qemu = subprocess.Popen([sys.executable, "-c", qemu_args])
                metadata = {}
                try:
                    status = shim.run_capture(qemu, [sys.executable, "-c", helper_args], output, metadata, 3)
                    records.append({"mode": mode, "result": status, "qemu_returncode": qemu.returncode,
                                    "capture": metadata})
                    self.assertEqual(status, (125 if mode == "helper_failure" else 65, False))
                    self.assertNotEqual(status[0], 33)
                    self.assertIsNotNone(qemu.poll())
                    self.assertIsNotNone(metadata["raw_exit_code"])
                finally:
                    if qemu.poll() is None:
                        qemu.kill()
                    qemu.wait()
            (root / "observation.json").write_text(json.dumps({"kind": "real_child_supervision_no_vm",
                                                               "passed": True, "cases": records}, indent=2) + "\n")


if __name__ == "__main__":
    unittest.main()
