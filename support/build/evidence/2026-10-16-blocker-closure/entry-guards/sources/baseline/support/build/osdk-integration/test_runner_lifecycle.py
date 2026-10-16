"""Exercise owned child groups and output-lock ordering without Rust or QEMU."""
import fcntl
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
from unittest import mock

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("a01_runner_lifecycle", HERE / "run.py")
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)

DESCENDANT = r"""
import json, os, signal, socket, sys, time
from pathlib import Path
signal.signal(signal.SIGTERM, signal.SIG_IGN)
listener = socket.socket()
listener.bind(('127.0.0.1', 0))
listener.listen(1)
Path(sys.argv[1]).write_text(json.dumps({'pid': os.getpid(), 'address': listener.getsockname()}))
time.sleep(60)
"""

LEADER = r"""
import os, subprocess, sys, time
from pathlib import Path
Path(sys.argv[3]).with_name('leader.pid').write_text(str(os.getpid()))
subprocess.Popen([sys.executable, '-I', '-c', sys.argv[1], sys.argv[2]])
while not Path(sys.argv[2]).exists():
    time.sleep(.01)
print('owned leader and descendant ready', flush=True)
while not Path(sys.argv[3]).exists():
    time.sleep(.01)
raise SystemExit(int(sys.argv[4]))
"""

WORKER = r"""
import contextlib, importlib.util, json, os, signal, sys
from pathlib import Path
spec = importlib.util.spec_from_file_location('runner_under_test', sys.argv[1])
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)
root = Path(sys.argv[2])
command = json.loads(sys.argv[3])
timeout = float(sys.argv[4])
seam = sys.argv[5] if len(sys.argv) > 5 else ''
fired = False
real_stop, real_killpg, real_signal = runner.OwnedSession.stop, runner.os.killpg, runner.signal.signal

def inject():
    global fired
    fired = True
    (root / 'signal-seam.json').write_text(json.dumps({'seam': seam, 'signal': 'SIGTERM'}))
    os.kill(os.getpid(), signal.SIGTERM)

def stop_at_entry(self, *args, **kwargs):
    if seam in ('cleanup-entry', 'normal-cleanup-entry') and not fired:
        inject()
    return real_stop(self, *args, **kwargs)

def between_group_signals(pid, number):
    result = real_killpg(pid, number)
    if seam == 'between-group-signals' and not fired and number == signal.SIGTERM:
        inject()
    return result

def record_handler_changes(number, handler):
    if handler == signal.SIG_IGN:
        (root / 'ignored-shutdown-signal').write_text(str(number))
    return real_signal(number, handler)

runner.OwnedSession.stop = stop_at_entry
runner.os.killpg = between_group_signals
runner.signal.signal = record_handler_changes
# The fallback permits the retained original runner to reproduce the old leak.
handlers = runner.interruption_handlers() if hasattr(runner, 'interruption_handlers') else contextlib.nullcontext()
with (root / 'worker.lock').open('a') as lock:
    import fcntl
    fcntl.flock(lock, fcntl.LOCK_EX)
    try:
        with handlers:
            runner.command(command, root, os.environ.copy(), root / 'command.log', timeout)
    except KeyboardInterrupt:
        raise SystemExit(130)
    except BaseException as error:
        if hasattr(error, 'signum'):
            raise SystemExit(128 + error.signum)
        raise
"""


class RunnerLifecycleTests(unittest.TestCase):
    runner_path = HERE / "run.py"

    def wait_for(self, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        while not predicate():
            self.assertLess(time.monotonic(), deadline, "owned fixture readiness deadline expired")
            time.sleep(.01)

    def exercise_exit(self, mode, leader_status=0, seam=""):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            ready, proceed = root / "ready.json", root / "proceed"
            argv = [sys.executable, "-I", "-c", LEADER, DESCENDANT, str(ready),
                    str(proceed), str(leader_status)]
            timeout = 1.5 if mode == "timeout" else 10
            with (root / "worker.log").open("wb") as output:
                worker = subprocess.Popen([sys.executable, "-I", "-c", WORKER,
                                           str(self.runner_path), str(root), json.dumps(argv),
                                           str(timeout), seam], stdout=output, stderr=subprocess.STDOUT,
                                          start_new_session=True)
                descriptor = None
                leader_descriptor = None
                try:
                    self.wait_for(ready.exists)
                    self.wait_for(lambda: "owned leader and descendant ready" in
                                  (root / "command.log").read_text())
                    child = json.loads(ready.read_text())
                    descriptor = os.pidfd_open(child["pid"])
                    leader_descriptor = os.pidfd_open(int((root / "leader.pid").read_text()))
                    poller = select.poll()
                    poller.register(descriptor, select.POLLIN)
                    self.assertFalse(poller.poll(0), "fixture descendant exited before the probe")
                    with socket.socket() as competitor:
                        with self.assertRaises(OSError):
                            competitor.bind(tuple(child["address"]))
                    if mode == "normal":
                        proceed.write_text("exit the session leader\n")
                    elif mode in ("SIGINT", "SIGTERM"):
                        os.kill(worker.pid, getattr(signal, mode))
                    status = worker.wait(timeout=8)
                    expected_signal = "SIGTERM" if seam == "normal-cleanup-entry" else \
                        mode if mode in ("SIGINT", "SIGTERM") else None
                    expected_worker = 128 + getattr(signal, expected_signal) if expected_signal else 0
                    self.assertEqual(status, expected_worker, (root / "worker.log").read_text())
                    self.assertTrue(poller.poll(2000), "TERM-ignoring descendant survived runner return")
                    with socket.socket() as competitor:
                        competitor.bind(tuple(child["address"]))
                    with (root / "worker.lock").open("a") as lock:
                        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    record = json.loads((root / "command.command.json").read_text())
                    expected_command = 124 if mode == "timeout" else expected_worker \
                        if expected_signal else leader_status
                    self.assertEqual(record["raw_exit_code"], expected_command)
                    self.assertEqual(record["timed_out"], mode == "timeout")
                    self.assertTrue(record["group_cleanup"]["leader_reaped"])
                    if expected_signal:
                        self.assertEqual(record["interrupted_by"], expected_signal)
                    if seam:
                        self.assertTrue((root / "signal-seam.json").is_file())
                        self.assertEqual(record["received_signals"], ["SIGTERM"] if
                                         seam == "normal-cleanup-entry" else ["SIGINT", "SIGTERM"])
                    self.assertFalse((root / "ignored-shutdown-signal").exists(),
                                     "cooperative cleanup must not sequentially ignore shutdown signals")
                    self.assertIn("owned leader and descendant ready", (root / "command.log").read_text())
                finally:
                    if worker.poll() is None:
                        worker.kill()
                        worker.wait(timeout=5)
                    for descriptor in (descriptor, leader_descriptor):
                        if descriptor is None:
                            continue
                        try:
                            signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        os.close(descriptor)

    def test_success_reaps_leader_after_killing_its_remaining_descendant(self):
        self.exercise_exit("normal")

    def test_failure_keeps_original_exit_and_cleans_its_remaining_descendant(self):
        self.exercise_exit("normal", 7)

    def test_timeout_cleans_term_ignoring_descendant(self):
        self.exercise_exit("timeout")

    def test_sigint_cleans_group_and_preserves_interrupted_command_record(self):
        self.exercise_exit("SIGINT")

    def test_sigterm_cleans_group_and_preserves_interrupted_command_record(self):
        self.exercise_exit("SIGTERM")

    def test_second_signal_at_cleanup_entry_cannot_skip_stop_or_record(self):
        # This entry replaces the former first SIG_IGN setup seam. The old
        # sequential handler masking is gone; an actual second TERM is latched.
        self.exercise_exit("SIGINT", seam="cleanup-entry")

    def test_second_signal_between_group_signals_cannot_skip_kill_or_reap(self):
        self.exercise_exit("SIGINT", seam="between-group-signals")

    def test_first_signal_during_normal_cleanup_is_not_silently_ignored(self):
        self.exercise_exit("normal", seam="normal-cleanup-entry")

    def test_busy_lock_does_not_create_output_or_parent_directories(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runner = root / "project/support/build/osdk-integration/run.py"
            runner.parent.mkdir(parents=True)
            shutil.copyfile(self.runner_path, runner)
            output = root / "new-parent/evidence"
            lock_path = runner.parents[1] / "out-osdk-integration.lock"
            with lock_path.open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                completed = subprocess.run([sys.executable, "-I", str(runner),
                                            "--output", str(output)], capture_output=True,
                                           text=True, timeout=5)
            self.assertNotEqual(completed.returncode, 0)
            self.assertIn("another integration runner is active", completed.stderr)
            self.assertFalse(output.parent.exists(), "lock rejection consumed a new evidence path")

    def test_existing_evidence_is_preserved_and_failed_mkdir_releases_lock(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "evidence"
            output.mkdir()
            marker = output / "failed-command.log"
            marker.write_bytes(b"retained failure evidence\n")
            lock_path = root / "runner.lock"
            with self.assertRaises(FileExistsError):
                with RUNNER.locked_output(lock_path, output):
                    self.fail("existing evidence must not enter the run")
            self.assertEqual(marker.read_bytes(), b"retained failure evidence\n")
            with lock_path.open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def test_external_reap_disarms_all_numeric_group_signals(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            with (root / "child.log").open("wb") as output:
                owned = RUNNER.OwnedSession([sys.executable, "-I", "-c", "pass"],
                                           cwd=root, env=os.environ.copy(), output=output)
                _, status = os.waitpid(owned.process.pid, 0)
                with mock.patch.object(RUNNER.os, "killpg") as killpg:
                    with self.assertRaisesRegex(RuntimeError, "externally reaped"):
                        owned.stop()
                    self.assertIsNone(owned.stop())
                    killpg.assert_not_called()
                owned.process.returncode = os.waitstatus_to_exitcode(status)

    def test_pending_sigterm_during_spawn_is_handled_after_owner_publication(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_popen = subprocess.Popen
            descriptors = []

            def pending_shutdown(*args, **kwargs):
                process = real_popen(*args, **kwargs)
                descriptors.append(os.pidfd_open(process.pid))
                os.kill(os.getpid(), signal.SIGTERM)
                return process

            try:
                with RUNNER.interruption_handlers(), \
                        mock.patch.object(RUNNER.subprocess, "Popen", side_effect=pending_shutdown):
                    with self.assertRaises(RUNNER.RunnerInterrupted) as interrupted:
                        RUNNER.command([sys.executable, "-I", "-c", "import time; time.sleep(60)"],
                                       root, os.environ.copy(), root / "spawn.log", 5)
                self.assertEqual(interrupted.exception.signum, signal.SIGTERM)
                poller = select.poll()
                poller.register(descriptors[0], select.POLLIN)
                self.assertTrue(poller.poll(2000), "spawned child escaped its published owner")
                record = json.loads((root / "spawn.command.json").read_text())
                self.assertEqual(record["raw_exit_code"], 143)
                self.assertTrue(record["group_cleanup"]["leader_reaped"])
            finally:
                for descriptor in descriptors:
                    try:
                        signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    os.close(descriptor)

    def test_owned_command_preserves_child_signal_mask_and_error_output(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            child = ("import signal; "
                     "blocked=signal.pthread_sigmask(signal.SIG_BLOCK, set()); "
                     "print('SIGTERM blocked:', signal.SIGTERM in blocked); "
                     "raise SystemExit(9)")
            with self.assertRaises(subprocess.CalledProcessError) as failed:
                RUNNER.checked_output([sys.executable, "-I", "-c", child], root,
                                      os.environ.copy(), root / "failed.log")
            self.assertEqual(failed.exception.returncode, 9)
            self.assertEqual(failed.exception.output, "SIGTERM blocked: False\n")
            self.assertEqual((root / "failed.log").read_text(), failed.exception.output)
            record = json.loads((root / "failed.command.json").read_text())
            self.assertEqual(record["raw_exit_code"], 9)
            self.assertTrue(record["group_cleanup"]["leader_reaped"])

    def test_repeated_shutdown_during_spawn_keeps_first_signal_and_reaps_owner(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            real_popen = subprocess.Popen
            descriptors = []

            def repeated_shutdown(*args, **kwargs):
                process = real_popen(*args, **kwargs)
                descriptors.append(os.pidfd_open(process.pid))
                os.kill(os.getpid(), signal.SIGTERM)
                os.kill(os.getpid(), signal.SIGINT)
                return process

            try:
                with mock.patch.object(RUNNER.subprocess, "Popen", side_effect=repeated_shutdown):
                    with self.assertRaises(RUNNER.RunnerInterrupted) as interrupted:
                        RUNNER.command([sys.executable, "-I", "-c", "import time; time.sleep(60)"],
                                       root, os.environ.copy(), root / "spawn.log", 5)
                self.assertEqual(interrupted.exception.signum, signal.SIGTERM)
                poller = select.poll()
                poller.register(descriptors[0], select.POLLIN)
                self.assertTrue(poller.poll(2000))
                record = json.loads((root / "spawn.command.json").read_text())
                self.assertEqual(record["received_signals"], ["SIGTERM", "SIGINT"])
                self.assertEqual(record["raw_exit_code"], 143)
                self.assertTrue(record["group_cleanup"]["leader_reaped"])
            finally:
                for descriptor in descriptors:
                    try:
                        signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                    os.close(descriptor)


if __name__ == "__main__":
    unittest.main()
