#!/usr/bin/env python3
"""Small host-only checks for debug socket ownership and acceptance failures."""
import hashlib
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import select
import signal
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import time
import unittest

SPEC = importlib.util.spec_from_file_location("a01_debug", Path(__file__).with_name("run.py"))
DEBUG = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(DEBUG)


class DebugTests(unittest.TestCase):
    def run_signal_fixture(self, name, signals, *, spawn_window=False, expect_leak=False):
        """Run the actual CLI against owned lock/TCP fixtures, never a VM."""
        with tempfile.TemporaryDirectory() as temporary:
            setting = os.environ.get("A01_DEBUG_LIFECYCLE_OUT")
            root = Path(setting) / name if setting else Path(temporary)
            if setting:
                root.mkdir(parents=True, exist_ok=False)
            project = root / "fixture-project"
            debug = project / "support/build/debug"
            debug.mkdir(parents=True)
            source = Path(os.environ.get("A01_DEBUG_SOURCE", str(Path(__file__).parent))) / "run.py"
            shutil.copyfile(source, debug / "run.py")
            # These placeholders serve only the CLI's source metadata phase.
            for name in ["support/build/kernel.sh", "support/build/minimal.mk",
                         "support/build/record-qemu.py", "support/build/check-boot.py",
                         "support/build/minimal/OSDK.toml", "support/build/minimal/Cargo.lock",
                         "support/upstream-lock.json", "kernel/asterinas/rust-toolchain.toml",
                         "kernel/asterinas/Cargo.lock", "kernel/asterinas/osdk/Cargo.lock",
                         "kernel/asterinas/ostd/src/boot/mod.rs"]:
                path = project / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"host lifecycle fixture; not kernel source\n")
            tools = root / "tools"
            tools.mkdir()
            for name in ["gdb", "nm", "git"]:
                path = tools / name
                path.write_text("#!/bin/sh\nprintf 'host-lifecycle-fixture\\n'\n")
                path.chmod(0o755)
            descendant = ("import json,os,signal,socket,time;from pathlib import Path;"
                          "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
                          "lease=socket.socket();lease.bind(('127.0.0.1',0));lease.listen(1);"
                          "Path(os.environ['A01_DEBUG_FIXTURE_ROOT'],'descendant.json').write_text("
                          "json.dumps({'pid':os.getpid(),'group':os.getpgrp(),'address':lease.getsockname()}));"
                          "time.sleep(60)")
            driver = root / "driver.py"
            driver.write_text(
                "import fcntl,json,os,signal,socket,subprocess,sys,time\nfrom pathlib import Path\n"
                "root=Path(os.environ['A01_DEBUG_FIXTURE_ROOT'])\n"
                "held=(root/'held.lock').open('w');fcntl.flock(held,fcntl.LOCK_EX)\n"
                "signal.signal(signal.SIGTERM,signal.SIG_IGN)\n"
                "lease=socket.socket();lease.bind(('127.0.0.1',0));lease.listen(1)\n"
                f"child=subprocess.Popen([sys.executable,'-I','-c',{descendant!r}],pass_fds=(held.fileno(),))\n"
                "while not (root/'descendant.json').exists():time.sleep(.01)\n"
                "(root/'ready.json').write_text(json.dumps({'pid':os.getpid(),'group':os.getpgrp(),"
                "'address':lease.getsockname(),'worker_route':os.environ.get('A01_KERNEL_WORKER'),"
                "'descendant':json.loads((root/'descendant.json').read_text())}))\n"
                "time.sleep(60)\n")
            (project / "support/build/kernel.sh").write_text(
                f"#!/bin/sh\nexec {sys.executable} -I {str(driver)!r}\n")
            output = root / "debug-output"
            python = [sys.executable, "-I", *(["-O"] if sys.flags.optimize else [])]
            arguments = [str(debug / "run.py"), "--output", str(output),
                         "--gdb", str(tools / "gdb"), "--nm", str(tools / "nm"), "--ready-timeout", "30"]
            command = [*python, *arguments]
            if spawn_window:
                wrapper = root / "spawn-window.py"
                wrapper.write_text(
                    "import importlib.util,os,signal,subprocess,sys,time\nfrom pathlib import Path\n"
                    f"spec=importlib.util.spec_from_file_location('debug_fixture',{str(debug / 'run.py')!r})\n"
                    "module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)\n"
                    "original=subprocess.Popen\n"
                    "def spawn(*args,**kwargs):\n child=original(*args,**kwargs)\n"
                    " if any(str(value).endswith('/kernel.sh') for value in args[0]):\n"
                    f"  ready=Path({str(root / 'ready.json')!r})\n"
                    "  deadline=time.monotonic()+5\n"
                    "  while not ready.exists():\n"
                    "   assert time.monotonic()<deadline\n   time.sleep(.01)\n"
                    "  os.kill(os.getpid(),signal.SIGTERM)\n return child\n"
                    "subprocess.Popen=spawn\n"
                    f"sys.argv={arguments!r}\nraise SystemExit(module.main())\n")
                command = [*python, str(wrapper)]
            env = os.environ.copy()
            env.update(PATH=str(tools) + os.pathsep + env.get("PATH", ""),
                       A01_DEBUG_FIXTURE_ROOT=str(root))
            observation = {"kind": "actual_debug_cli_host_lifecycle_fixture_no_build_no_vm",
                           "source_sha256": DEBUG.sha256(source), "argv": command,
                           "spawn_publication_window": spawn_window, "expected_original_leak": expect_leak}
            process, descriptors = None, []
            try:
                with (root / "console.log").open("wb") as log:
                    process = subprocess.Popen(command, cwd=project, env=env,
                                               stdout=log, stderr=subprocess.STDOUT)
                    deadline = time.monotonic() + 8
                    while not (root / "ready.json").exists():
                        self.assertLess(time.monotonic(), deadline)
                        self.assertIsNone(process.poll(), (root / "console.log").read_text())
                        time.sleep(.01)
                    ready = json.loads((root / "ready.json").read_text())
                    for role, info in [("driver", ready), ("descendant", ready["descendant"])]:
                        descriptors.append((role, os.pidfd_open(info["pid"])))
                    if not spawn_window:
                        for number in signals:
                            process.send_signal(number)
                            time.sleep(.015)
                    process.wait(timeout=6)
                exited = {role: bool(select.select([fd], [], [], 0 if expect_leak else 2)[0])
                          for role, fd in descriptors}
                lock_released = True
                with (root / "held.lock").open("a") as held:
                    try:
                        fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    except BlockingIOError:
                        lock_released = False
                leases = []
                for info in [ready, ready["descendant"]]:
                    with socket.socket() as lease:
                        try:
                            lease.bind(tuple(info["address"]))
                            leases.append(True)
                        except OSError:
                            leases.append(False)
                result = json.loads((output / "result.json").read_text()) if (output / "result.json").exists() else None
                observation.update(returncode=process.returncode, ready=ready, pidfd_exited=exited,
                                   lock_released=lock_released, tcp_leases_released=leases, result=result)
                if expect_leak:
                    self.assertEqual(process.returncode, -signal.SIGTERM)
                    self.assertFalse(any(exited.values()))
                    self.assertFalse(lock_released)
                    self.assertFalse(any(leases))
                else:
                    expected = signal.SIGTERM if spawn_window else signals[0]
                    self.assertEqual(process.returncode, 128 + expected)
                    self.assertTrue(all(exited.values()), exited)
                    self.assertTrue(lock_released)
                    self.assertTrue(all(leases))
                    self.assertFalse(result["passed"])
                    self.assertEqual(ready["worker_route"], "1")
                    self.assertEqual(result["interrupted_by"], signal.Signals(expected).name)
                    self.assertTrue(all(item["reaped"] for item in result["owned_session_cleanup"]))
                    if len(signals) == 2:
                        self.assertEqual(result["received_signals"], [signal.Signals(number).name for number in signals])
                observation["passed"] = True
            finally:
                for _, descriptor in descriptors:
                    try:
                        signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    select.select([descriptor], [], [], 3)
                    os.close(descriptor)
                if process is not None and process.poll() is None:
                    process.kill()
                    process.wait()
                (root / "observation.json").write_text(json.dumps(observation, indent=2) + "\n")

    def test_sigterm_cleans_actual_cli_owned_driver_and_descendant(self):
        self.run_signal_fixture("sigterm", [signal.SIGTERM],
                                expect_leak=os.environ.get("A01_DEBUG_EXPECT_ORIGINAL_LEAK") == "1")

    @unittest.skipIf(os.environ.get("A01_DEBUG_EXPECT_ORIGINAL_LEAK") == "1", "original baseline is SIGTERM")
    def test_sigint_then_sigterm_cannot_interrupt_cleanup(self):
        self.run_signal_fixture("sigint-then-sigterm", [signal.SIGINT, signal.SIGTERM])

    @unittest.skipIf(os.environ.get("A01_DEBUG_EXPECT_ORIGINAL_LEAK") == "1", "original baseline is SIGTERM")
    def test_signal_between_popen_spawn_and_owner_publication_cleans_child(self):
        self.run_signal_fixture("spawn-publication", [], spawn_window=True)

    def elf_fixture(self, path, code, *, machine=62, kind=2):
        entry, offset = 0xffffffff80001000, 4096
        raw = bytearray(offset + len(code))
        raw[:64] = struct.pack("<16sHHIQQQIHHHHHH", b"\x7fELF\x02\x01\x01" + b"\0" * 9,
                               kind, machine, 1, entry, 64, 0, 0, 64, 56, 1, 64, 0, 0)
        raw[64:120] = struct.pack("<IIQQQQQQ", 1, 5, offset, entry, entry,
                                  len(code), len(code), 4096)
        raw[offset:] = code
        path.write_bytes(raw)
        return entry

    def test_entry_binding_uses_executable_load_bytes_and_recorded_boot_hash(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            original, boot = root / "symbols", root / "boot.elf"
            code = bytes(range(DEBUG.ENTRY_BYTES))
            entry = self.elf_fixture(original, code)
            self.elf_fixture(boot, code, machine=3)
            ready = {"cwd": str(root), "artifacts": {"-kernel": {
                "path": "boot.elf", "size": boot.stat().st_size,
                "sha256": DEBUG.sha256(boot)}}}
            binding = DEBUG.bind_entry_artifacts(original, ready, entry)
            self.assertEqual(binding["expected_bytes"], code.hex())
            self.assertEqual(binding["boot_artifact"]["sha256"], DEBUG.sha256(boot))
            self.assertEqual(binding["symbol_artifact"]["sha256"], DEBUG.sha256(original))
            self.elf_fixture(boot, bytes(reversed(code)), machine=3)
            # Even an updated, internally consistent QEMU record cannot make
            # different symbol/boot instructions pass this binding.
            ready["artifacts"]["-kernel"]["sha256"] = DEBUG.sha256(boot)
            with self.assertRaisesRegex(ValueError, "different Rust entry bytes"):
                DEBUG.bind_entry_artifacts(original, ready, entry)
            self.elf_fixture(boot, code, machine=3)
            with self.assertRaisesRegex(ValueError, "changed after QEMU"):
                DEBUG.bind_entry_artifacts(original, ready, entry)

    def test_entry_binding_rejects_wrong_type_machine_and_truncated_elf(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "entry.elf"
            code = bytes(range(DEBUG.ENTRY_BYTES))
            for machine, kind in [(3, 2), (62, 1)]:
                entry = self.elf_fixture(path, code, machine=machine, kind=kind)
                with self.subTest(machine=machine, kind=kind), self.assertRaises(ValueError):
                    DEBUG.elf_entry_bytes(path, entry, 62)
            entry = self.elf_fixture(path, code)
            valid = path.read_bytes()
            for broken in [valid[:63], valid[:119], valid[:-1], valid[:4] + b"\x01" + valid[5:]]:
                path.write_bytes(broken)
                with self.subTest(size=len(broken)), self.assertRaises(ValueError):
                    DEBUG.elf_entry_bytes(path, entry, 62)

    def test_listener_stays_reserved_and_survives_explicit_fd_handoff(self):
        with DEBUG.own_listener() as listener:
            self.assertGreaterEqual(listener.fileno(), 64)
            self.assertEqual(listener.getsockname()[0], "127.0.0.1")
            with socket.socket() as competitor:
                with self.assertRaises(OSError):
                    competitor.bind(listener.getsockname())
            command = [sys.executable, "-I", "-c",
                       "import socket,sys,json; s=socket.socket(fileno=int(sys.argv[1])); "
                       "print(json.dumps(s.getsockname()))", str(listener.fileno())]
            copied = subprocess.check_output(command, pass_fds=(listener.fileno(),), timeout=5)
            self.assertEqual(json.loads(copied), list(listener.getsockname()))

    def test_readiness_tolerates_partial_json_without_a_probe_connection(self):
        class LiveDriver:
            def exited(self):
                return False
        with tempfile.TemporaryDirectory() as temporary, DEBUG.own_listener() as listener:
            record = Path(temporary) / "qemu.json"
            record.write_text('{"qemu_pid":')
            expected = {"qemu_pid": os.getpid(), "raw_exit_code": None, "timed_out": False,
                        "gdb_listener": {"fd": listener.fileno(), "address": list(listener.getsockname())}}
            timer = threading.Timer(0.05, lambda: record.write_text(json.dumps(expected)))
            timer.start()
            try:
                self.assertEqual(DEBUG.wait_for_qemu(record, LiveDriver(), listener, 2), expected)
                listener.setblocking(False)
                with self.assertRaises(BlockingIOError):
                    listener.accept()
            finally:
                timer.join()
            expected["raw_exit_code"] = 65
            record.write_text(json.dumps(expected))
            with self.assertRaisesRegex(ValueError, "QEMU exited"):
                DEBUG.wait_for_qemu(record, LiveDriver(), listener, 0.2)

    def test_gdb_requires_matching_rust_pc_success_and_detach(self):
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "gdb.log"
            code = bytes(range(DEBUG.ENTRY_BYTES))
            good = ("A01_GDB_RUST_ENTRY_HIT pc=0xffffffff80001000 entry=0xffffffff80001000\n"
                    "A01_GDB_RUST_ENTRY_BYTES pc=0xffffffff80001000 size=32 bytes=" + code.hex()
                    + "\nA01_GDB_DETACHED\n")
            log.write_text(good)
            address = 0xffffffff80001000
            self.assertTrue(DEBUG.accept_gdb(0, log, address, code)["detached"])
            for status, text in [(1, good), (0, "rip 0xfff0\n"),
                                 (0, good.replace("pc=0xffffffff80001000", "pc=0xfff0")),
                                 (0, good.replace("A01_GDB_DETACHED", "")),
                                 (0, good.replace(code.hex(), "ff" * DEBUG.ENTRY_BYTES)),
                                 (0, good.replace("size=32", "size=16")),
                                 (0, good.replace(code.hex(), code.hex()[:-2])),
                                 (0, good + good)]:
                with self.subTest(status=status, text=text):
                    log.write_text(text)
                    with self.assertRaises(ValueError):
                        DEBUG.accept_gdb(status, log, address, code)

    def test_detach_does_not_make_failed_or_changed_boot_pass(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            raw = b"retained boot bytes\n"
            (directory / "serial.log").write_bytes(raw)
            (directory / "run-exit-code.txt").write_text("0\n")
            record = {"raw_exit_code": 33, "timed_out": False,
                      "serial_sha256": hashlib.sha256(raw).hexdigest()}
            (directory / "qemu.json").write_text(json.dumps(record))
            self.assertEqual(DEBUG.accept_boot(0, directory)["raw_qemu_exit"], 33)
            with self.assertRaises(ValueError):
                DEBUG.accept_boot(1, directory)
            (directory / "run-exit-code.txt").write_text("1\n")
            with self.assertRaises(ValueError):
                DEBUG.accept_boot(0, directory)
            (directory / "run-exit-code.txt").write_text("0\n")
            for key, value in [("raw_exit_code", 65), ("timed_out", True), ("serial_sha256", "0" * 64)]:
                broken = dict(record, **{key: value})
                (directory / "qemu.json").write_text(json.dumps(broken))
                with self.assertRaises(ValueError):
                    DEBUG.accept_boot(0, directory)

    def test_exited_leader_does_not_leave_term_ignoring_owned_descendant(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            descendant = "import signal,time; signal.signal(signal.SIGTERM,signal.SIG_IGN); time.sleep(60)"
            child = ("import subprocess,sys,time; from pathlib import Path; "
                     "p=subprocess.Popen([sys.executable,'-I','-c',sys.argv[1]]); "
                     "Path(sys.argv[2]).write_text(str(p.pid)); time.sleep(.15)")
            with (directory / "child.log").open("w") as log:
                owned = DEBUG.OwnedSession([sys.executable, "-I", "-c", child, descendant,
                                           str(directory / "descendant.pid")],
                                          cwd=directory, env=os.environ.copy(), output=log)
                descriptor = None
                try:
                    deadline = time.monotonic() + 5
                    while not (directory / "descendant.pid").exists():
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(0.01)
                    descriptor = os.pidfd_open(int((directory / "descendant.pid").read_text()))
                    while not owned.exited():
                        self.assertLess(time.monotonic(), deadline)
                        time.sleep(0.01)
                    poller = select.poll()
                    poller.register(descriptor, select.POLLIN)
                    self.assertFalse(poller.poll(0))
                    self.assertEqual(owned.wait(2), 0)
                    self.assertTrue(poller.poll(2000))
                    self.assertEqual(owned.stop(), 0)  # disarmed after its one reap
                finally:
                    owned.stop()
                    if descriptor is not None:
                        os.close(descriptor)


class EncodedFlagEntryTests(unittest.TestCase):
    def check_encoded_rejection_and_retry(self, value):
        """Run public main/argv with explicit host substitutes for heavy work."""
        with tempfile.TemporaryDirectory() as temporary:
            name = "debug-empty" if not value else "debug-nonempty"
            setting = os.environ.get("A01_ENTRY_GUARDS_OUT")
            root = Path(setting) / name if setting else Path(temporary)
            if setting:
                root.mkdir(parents=True, exist_ok=False)
            project = root / "fixture-project"
            script = project / "support/build/debug/run.py"
            script.parent.mkdir(parents=True)
            source = Path(os.environ.get("A01_ENTRY_GUARDS_SOURCE", str(Path(__file__).with_name("run.py"))))
            shutil.copyfile(source, script)
            for relative in ["support/build/kernel.sh", "support/build/minimal.mk",
                             "support/build/record-qemu.py", "support/build/check-boot.py",
                             "support/build/minimal/OSDK.toml", "support/build/minimal/Cargo.lock",
                             "support/upstream-lock.json", "kernel/asterinas/rust-toolchain.toml",
                             "kernel/asterinas/Cargo.lock", "kernel/asterinas/osdk/Cargo.lock",
                             "kernel/asterinas/ostd/src/boot/mod.rs",
                             "kernel/asterinas/target/x86_64-unknown-none/release/asterinas-osdk-bin",
                             "host-cargo/bin/cargo-osdk"]:
                path = project / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("host entry fixture, not kernel source or ELF\n")
            output, marker = root / "output-parent/evidence", root / "work-started"
            wrapper = root / "public-entry-fixture.py"
            wrapper.write_text(
                "import importlib.util,sys,types\nfrom pathlib import Path\n"
                f"spec=importlib.util.spec_from_file_location('entry_fixture',{str(script)!r})\n"
                "module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)\n"
                "# This fixture tests entry ordering only; no tools, Cargo, GDB, or VM execute.\n"
                "class HostSession:\n"
                " def __init__(self,*args,**kwargs):\n"
                f"  Path({str(marker)!r}).write_text('host OwnedSession fixture, no child tools or VM\\n')\n"
                "  self.process=types.SimpleNamespace(pid=42);self.reaped=False;self.external_reap=False\n"
                " def wait(self,*args): self.reaped=True;return 0\n"
                " def stop(self): self.reaped=True;return 0\n"
                "module.OwnedSession=HostSession\n"
                "module.shutil.which=lambda name: sys.executable\n"
                "module.subprocess.check_output=lambda *args,**kwargs: 'host-fixture\\n'\n"
                "module.wait_for_qemu=lambda *args: {'host_fixture':True}\n"
                "module.entry_address=lambda *args: 4096\n"
                "module.bind_entry_artifacts=lambda *args: {'symbol_artifact':{'host_fixture':True},"
                "'expected_bytes':'00'*32}\n"
                "module.accept_gdb=lambda *args: {'host_fixture':True}\n"
                "module.accept_boot=lambda *args: {'host_fixture':True}\n"
                f"sys.argv=[{str(script)!r},*sys.argv[1:]]\nraise SystemExit(module.main())\n")
            command = [sys.executable, "-I", *(["-O"] if sys.flags.optimize else []),
                       str(wrapper), "--output", str(output)]
            env = os.environ.copy()
            env.update(CARGO_ENCODED_RUSTFLAGS=value, CARGO_HOME=str(project / "host-cargo"))
            observations = []
            for phase in ("encoded", "retry-unset"):
                if phase == "retry-unset":
                    env.pop("CARGO_ENCODED_RUSTFLAGS")
                result = subprocess.run(command, cwd=project, env=env, stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, timeout=10)
                (root / (phase + ".log")).write_bytes(result.stdout)
                observations.append({"phase": phase, "argv": command, "returncode": result.returncode,
                    "encoded_present": "CARGO_ENCODED_RUSTFLAGS" in env,
                    "encoded_value": env.get("CARGO_ENCODED_RUSTFLAGS"),
                    "output_exists": output.exists(), "output_parent_exists": output.parent.exists(),
                    "work_started": marker.exists()})
            (root / "observation.json").write_text(json.dumps({
                "kind": "actual_public_main_argv_with_explicit_host_debug_work_fixtures_no_build_no_vm",
                "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
                "observations": observations}, indent=2) + "\n")
            first, retry = observations
            self.assertEqual(first["returncode"], 2, (root / "encoded.log").read_text())
            self.assertIn("unset CARGO_ENCODED_RUSTFLAGS and retry", (root / "encoded.log").read_text())
            for key in ("output_exists", "output_parent_exists", "work_started"):
                self.assertFalse(first[key], key)
            self.assertEqual(retry["returncode"], 0, (root / "retry-unset.log").read_text())
            self.assertTrue(retry["work_started"])
            self.assertTrue(json.loads((output / "result.json").read_text())["passed"])

    def test_empty_encoded_flags_rejected_before_output_and_tools_then_same_argv_retries(self):
        self.check_encoded_rejection_and_retry("")

    def test_nonempty_encoded_flags_rejected_before_output_and_tools_then_same_argv_retries(self):
        self.check_encoded_rejection_and_retry("-Copt-level=0\x1f--cfg=host_fixture")


if __name__ == "__main__":
    unittest.main()
