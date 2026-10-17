#!/usr/bin/env python3
"""Full wrapper cancellation with disposable TCP leases, never a kernel/VM."""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import signal
import socket
import subprocess
import sys
import time
import unittest
from unittest.mock import patch


BUILD = Path(__file__).resolve().parents[1]


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


supervisor = load(BUILD / "kernel-supervisor.py", "kernel_supervisor")
fixtures = load(Path(__file__).with_name("test_kernel_runner.py"), "kernel_runner_fixtures")


def exited(descriptor, timeout=0):
    return bool(select.select([descriptor], [], [], timeout)[0])


def lease_released(address):
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        with socket.socket() as probe:
            try:
                probe.bind(tuple(address))
                return True
            except OSError:
                time.sleep(.01)
    return False


class KernelSupervisorTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixtures.KernelRunnerTests("test_owned_manifest_removed_after_success")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def save(self, name, value, log=None):
        setting = os.environ.get("A01_KERNEL_LIFECYCLE_OUT")
        if setting:
            root = Path(setting) / name
            root.mkdir(parents=True, exist_ok=False)
            (root / "observation.json").write_text(json.dumps(value, indent=2) + "\n")
            if log is not None:
                (root / "runner.log").write_bytes(log)

    def wait_json(self, path):
        deadline = time.monotonic() + 8
        while time.monotonic() < deadline:
            try:
                return json.loads(path.read_text())
            except (FileNotFoundError, json.JSONDecodeError):
                time.sleep(.01)
        self.fail(f"host fixture did not become ready: {path}")

    def lifecycle(self, signum=None):
        fixture = self.fixture
        child_code = (
            "import json,os,signal,socket,time;from pathlib import Path;"
            "lease=socket.socket();lease.bind(('127.0.0.1',0));lease.listen(1);"
            "signal.signal(signal.SIGTERM,signal.SIG_IGN);"
            "Path('lease-child.json').write_text(json.dumps({'pid':os.getpid(),"
            "'group':os.getpgrp(),'address':lease.getsockname()}));time.sleep(60)"
        )
        fixture.write_tool("make", """#!/usr/bin/python3
import json,os,socket,subprocess,sys,time
from pathlib import Path
if '--version' in sys.argv: print('GNU Make host fixture');raise SystemExit(0)
root=Path(os.environ['MOCK_PROJECT']);os.chdir(root)
lease=socket.socket();lease.bind(('127.0.0.1',0));lease.listen(1)
child=subprocess.Popen([sys.executable,'-c',CHILD],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,pass_fds=(9,))
Path('lease-make.json').write_text(json.dumps({'pid':os.getpid(),'group':os.getpgrp(),'child_pid':child.pid,'address':lease.getsockname()}))
while not Path('release-make').exists(): time.sleep(.01)
""".replace("CHILD", repr(child_code)))
        environment = dict(fixture.environment, A01_RUN_DIR=str(fixture.root / "evidence"))
        command = ["bash", str(fixture.build / "kernel.sh"), "kernel"]
        descriptors = {}
        process = None
        record = {"kind": "kernel_supervisor_host_fixture_no_kernel_no_vm", "argv": command,
                  "signal": signal.Signals(signum).name if signum else None,
                  "source_sha256": {name: hashlib.sha256((fixture.build / name).read_bytes()).hexdigest()
                                    for name in ("kernel.sh", "kernel-supervisor.py")}}
        log = fixture.root / "supervisor.log"
        try:
            with log.open("wb") as output:
                process = subprocess.Popen(command, env=environment, stdout=output,
                                           stderr=subprocess.STDOUT, start_new_session=True)
                descriptors["supervisor"] = os.pidfd_open(process.pid)
                make = self.wait_json(fixture.root / "lease-make.json")
                child = self.wait_json(fixture.root / "lease-child.json")
                descriptors["worker"] = os.pidfd_open(make["group"])
                descriptors["make"] = os.pidfd_open(make["pid"])
                descriptors["lease_child"] = os.pidfd_open(child["pid"])
                record.update(supervisor_pid=process.pid, make=make, lease_child=child)
                self.assertNotEqual(make["group"], process.pid)
                self.assertEqual(make["group"], child["group"])
                self.assertTrue(all(not exited(fd) for fd in descriptors.values()))
                lock = fixture.build / "out-kernel.lock"
                lock_identity = (lock.stat().st_dev, lock.stat().st_ino)
                self.assertTrue((fixture.kernel / "OSDK.toml").is_file())
                if signum is not None:
                    signal.pidfd_send_signal(descriptors["supervisor"], signum)
                    # A repeat shutdown request must not unwind owned cleanup.
                    time.sleep(.01)
                    signal.pidfd_send_signal(descriptors["supervisor"], signal.SIGTERM)
                else:
                    (fixture.root / "release-make").touch()
                process.wait(timeout=6)
            states = {name: exited(fd, 2) for name, fd in descriptors.items()}
            record.update(returncode=process.returncode, pidfd_exited=states,
                          make_tcp_released=lease_released(make["address"]),
                          child_tcp_released=lease_released(child["address"]),
                          manifest_present=(fixture.kernel / "OSDK.toml").exists(),
                          stable_lock_inode=(lock.stat().st_dev, lock.stat().st_ino) == lock_identity)
            with lock.open("a") as stream:
                fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                record["workspace_lock_released"] = True
                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
            text = log.read_text()
            receipts = [json.loads(line.removeprefix("A01_KERNEL_SUPERVISOR "))
                        for line in text.splitlines() if line.startswith("A01_KERNEL_SUPERVISOR ")]
            self.assertEqual(len(receipts), 1, text)
            record["supervision_receipt"] = receipts[0]
            self.assertTrue(receipts[0]["worker_reaped"])
            self.assertFalse(receipts[0]["external_reap_disarmed"])
            self.assertEqual(process.returncode, 128 + signum if signum else 0)
            self.assertTrue(all(states.values()), states)
            self.assertTrue(record["make_tcp_released"])
            self.assertTrue(record["child_tcp_released"])
            self.assertFalse(record["manifest_present"])
            self.assertTrue(record["stable_lock_inode"])
            record["passed"] = True
        finally:
            # Failure cleanup uses only retained pidfds, never guessed global
            # PIDs/groups. Every fixture process is known through its receipt.
            for descriptor in descriptors.values():
                try:
                    signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            for descriptor in descriptors.values():
                exited(descriptor, 2)
                os.close(descriptor)
            if process is not None:
                process.wait(timeout=3)
            name = signal.Signals(signum).name.lower() if signum else "normal-descendant"
            self.save(name, record, log.read_bytes() if log.exists() else b"")

    def test_sigint_stops_full_wrapper_and_owned_descendants(self):
        self.lifecycle(signal.SIGINT)

    def test_sigterm_stops_full_wrapper_and_owned_descendants(self):
        self.lifecycle(signal.SIGTERM)

    def test_normal_worker_exit_also_closes_remaining_descendant(self):
        self.lifecycle()

    def test_worker_route_inherits_existing_outer_group(self):
        fixture = self.fixture
        fixture.write_tool("make", """#!/usr/bin/python3
import json,os,sys
from pathlib import Path
if '--version' in sys.argv: print('GNU Make host fixture');raise SystemExit(0)
Path(os.environ['MOCK_PROJECT'],'worker-group.json').write_text(json.dumps({'group':os.getpgrp()}))
""")
        env = dict(fixture.environment, A01_RUN_DIR=str(fixture.root / "evidence"), A01_KERNEL_WORKER="1")
        process = subprocess.Popen(["bash", str(fixture.build / "kernel.sh"), "kernel"],
                                   env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        output, _ = process.communicate(timeout=8)
        self.assertEqual(process.returncode, 0, output)
        self.assertEqual(json.loads((fixture.root / "worker-group.json").read_text())["group"], process.pid)
        self.assertNotIn(b"A01_KERNEL_SUPERVISOR", output)
        self.save("outer-worker-route", {"kind": "host_worker_route_no_kernel", "passed": True,
                                         "outer_group": process.pid, "A01_KERNEL_WORKER": "1"}, output)

    def test_gdb_listener_descriptor_survives_public_supervisor(self):
        fixture = self.fixture
        fixture.write_tool("make", """#!/usr/bin/python3
import json,os,socket,sys
from pathlib import Path
if '--version' in sys.argv: print('GNU Make host fixture');raise SystemExit(0)
stream=socket.socket(fileno=int(os.environ['A01_GDB_FD']))
Path(os.environ['MOCK_PROJECT'],'gdb-fd.json').write_text(json.dumps({'fd':stream.fileno(),'address':stream.getsockname(),'listening':stream.getsockopt(socket.SOL_SOCKET,socket.SO_ACCEPTCONN),'argv':sys.argv}))
""")
        with socket.socket() as original:
            original.bind(("127.0.0.1", 0))
            original.listen(1)
            descriptor = fcntl.fcntl(original.fileno(), fcntl.F_DUPFD_CLOEXEC, 64)
            try:
                env = dict(fixture.environment, A01_RUN_DIR=str(fixture.root / "evidence"),
                           A01_GDB_FD=str(descriptor), A01_GDB_PORT=str(original.getsockname()[1]))
                result = subprocess.run(["bash", str(fixture.build / "kernel.sh"), "gdb_server"],
                                        env=env, pass_fds=(descriptor,), stdout=subprocess.PIPE,
                                        stderr=subprocess.STDOUT, timeout=8)
                # The fake make did not launch a kernel; ordinary live boot
                # validation must still reject it after validating FD handoff.
                self.assertNotEqual(result.returncode, 0)
                record = json.loads((fixture.root / "gdb-fd.json").read_text())
                self.assertEqual(record["fd"], descriptor)
                self.assertEqual(record["address"], list(original.getsockname()))
                self.assertTrue(record["listening"])
                self.assertIn("gdb_server", record["argv"])
                self.save("gdb-fd-handoff", {"kind": "host_fd_handoff_no_kernel", "passed": True,
                                             "listener": record, "driver_rejected_missing_vm": True},
                          result.stdout)
            finally:
                os.close(descriptor)

    def test_signals_during_popen_preserve_first_request_and_publish_owner(self):
        real_popen = subprocess.Popen

        def during_publication(*args, **kwargs):
            process = real_popen(*args, **kwargs)
            os.kill(os.getpid(), signal.SIGINT)
            os.kill(os.getpid(), signal.SIGTERM)
            return process

        with supervisor.interruption_handlers() as shutdown:
            with patch.object(supervisor.subprocess, "Popen", side_effect=during_publication):
                owned = supervisor.OwnedWorker([sys.executable, "-c", "import time;time.sleep(60)"],
                                                env=os.environ.copy())
            raw = owned.wait(shutdown)
            self.assertTrue(owned.reaped)
            self.assertEqual(shutdown.first_signal, signal.SIGINT)
            self.assertEqual(supervisor.exit_status(raw, shutdown), 130)
            self.save("publication-seam", {"kind": "host_Popen_publication_no_kernel", "passed": True,
                                            "signals_delivered_before_Popen_return": ["SIGINT", "SIGTERM"],
                                            "first_signal": "SIGINT", "exit_code": 130,
                                            "raw_worker_exit": raw, "worker_reaped": owned.reaped})

    def test_first_shutdown_at_normal_cleanup_entry_cannot_unwind_cleanup(self):
        real_killpg = os.killpg
        signals = []

        def cleanup_seam(group, number):
            if not signals:
                os.kill(os.getpid(), signal.SIGINT)
                os.kill(os.getpid(), signal.SIGTERM)
            signals.append(number)
            return real_killpg(group, number)

        with supervisor.interruption_handlers() as shutdown:
            owned = supervisor.OwnedWorker([sys.executable, "-c", "pass"], env=os.environ.copy())
            while not owned.exited():
                time.sleep(.01)
            with patch.object(supervisor.os, "killpg", side_effect=cleanup_seam):
                raw = owned.wait(shutdown)
            self.assertTrue(owned.reaped)
            self.assertEqual(signals, [signal.SIGTERM, signal.SIGKILL])
            self.assertEqual(shutdown.first_signal, signal.SIGINT)
            self.assertEqual(supervisor.exit_status(raw, shutdown), 130)
            self.save("normal-cleanup-seam", {"kind": "host_normal_cleanup_no_kernel", "passed": True,
                                               "signals_delivered_at_first_group_signal": ["SIGINT", "SIGTERM"],
                                               "group_signals": [signal.Signals(n).name for n in signals],
                                               "first_signal": "SIGINT", "exit_code": 130,
                                               "raw_worker_exit": raw, "worker_reaped": owned.reaped})

    def test_reaped_entry_never_signals_numeric_group_again(self):
        owned = supervisor.OwnedWorker([sys.executable, "-c", "pass"], env=os.environ.copy())
        self.assertEqual(owned.wait(supervisor.ShutdownState()), 0)
        with patch.object(supervisor.os, "killpg") as killpg:
            self.assertEqual(owned.stop(), 0)
            killpg.assert_not_called()
            self.save("after-reap-disarmed", {"kind": "host_reap_identity_no_kernel", "passed": True,
                                              "second_stop_group_signal_calls": killpg.call_count,
                                              "worker_reaped": owned.reaped})

    def test_external_reap_permanently_disarms_group_signaling(self):
        owned = supervisor.OwnedWorker([sys.executable, "-c", "pass"], env=os.environ.copy())
        self.assertEqual(owned.process.wait(timeout=3), 0)
        with patch.object(supervisor.os, "killpg") as killpg:
            with self.assertRaisesRegex(RuntimeError, "externally reaped"):
                owned.stop()
            self.assertTrue(owned.external_reap)
            self.assertIsNone(owned.stop())
            killpg.assert_not_called()
            self.save("external-reap-disarmed", {"kind": "host_ECHILD_identity_no_kernel", "passed": True,
                                                  "external_reap_disarmed": owned.external_reap,
                                                  "group_signal_calls": killpg.call_count})


if __name__ == "__main__":
    unittest.main(verbosity=2)
