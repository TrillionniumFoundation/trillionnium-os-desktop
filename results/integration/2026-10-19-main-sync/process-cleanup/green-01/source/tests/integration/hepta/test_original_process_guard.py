"""Real disposable Linux children + signal spies; no Agentd, Rust build or device.

Never create actual PID/PGID reuse. Kernel WNOWAIT and ECHILD observations prove
the identity boundary while all deliberately stale signal attempts are mocked.
"""

import ctypes
import json
import os
from pathlib import Path
import select
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import run_original_agentd as gate


def successful_leader_writer_fixture():
    """Isolate subreaper state and own both real fixture children completely."""
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        raise OSError(ctypes.get_errno(), "fixture subreaper unavailable")
    writer_source = r'''
import os, pathlib, socket, sys
plugins = pathlib.Path(sys.argv[2])
plugins.mkdir()
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
    channel.settimeout(10)
    channel.connect(sys.argv[1])
    channel.sendall(str(os.getpid()).encode() + b"\n")
    if channel.recv(1) != b"S":
        raise SystemExit(91)
    print("writer-ready", flush=True)
    while True:
        request = channel.recv(1)
        if not request:
            break
        if request != b"W":
            raise SystemExit(92)
        (plugins / "after-leader-exit").write_bytes(b"owned-writer-still-active")
        channel.sendall(b"written")
'''
    leader_source = r'''
import os, subprocess, sys
writer = subprocess.Popen([sys.executable, "-c", sys.argv[1], sys.argv[2], sys.argv[3]],
                          stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True)
if writer.stdout.readline() != "writer-ready\n":
    raise SystemExit(93)
writer.stdout.close()
os._exit(0)  # Deliberately leave the same-group writer for the guard to clean.
'''
    report = {"signals": [], "writer_wrote_after_leader_exit": False}
    state = {"group": None, "writer_pid": None, "writer_pidfd": None, "channel": None}
    original_wait = gate.ChildGroup.wait_exit
    original_reap = gate.ChildGroup.reap
    real_killpg = os.killpg

    with tempfile.TemporaryDirectory(prefix="hp-guard-", dir="/tmp") as temporary:
        root = Path(temporary)
        listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        listener.settimeout(3)
        listener.bind(str(root / "control.sock"))
        listener.listen(1)

        def writer_exited():
            poller = select.poll()
            poller.register(state["writer_pidfd"], select.POLLIN)
            return bool(poller.poll(0))

        def wait_with_handshake(group, timeout):
            state["group"] = group
            channel, _ = listener.accept()
            state["channel"] = channel
            channel.settimeout(3)
            payload = b""
            while not payload.endswith(b"\n"):
                chunk = channel.recv(32)
                if not chunk or len(payload) + len(chunk) > 32:
                    raise RuntimeError("fixture writer identity handshake failed")
                payload += chunk
            pid = int(payload)
            peer, uid, _ = struct.unpack("3i", channel.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            if peer != pid or uid != os.geteuid() or os.getpgid(pid) != group.process.pid:
                raise RuntimeError("fixture writer is not the owned same-group peer")
            state["writer_pid"] = pid
            state["writer_pidfd"] = os.pidfd_open(pid)
            report["leader_pid"] = group.process.pid
            report["writer_pid"] = pid
            report["writer_group_matches_leader"] = True
            channel.sendall(b"S")  # Only now may the leader exit successfully.
            return original_wait(group, timeout)

        def anchored_signal(pid, signum):
            status = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
            if status is None or (status.si_pid, status.si_code, status.si_status) != (pid, os.CLD_EXITED, 0):
                raise RuntimeError("successful leader lost its WNOWAIT signal anchor")
            report["signals"].append(int(signum))
            return real_killpg(pid, signum)

        def checked_reap(group):
            status = os.waitid(os.P_PID, group.process.pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
            if status is None or status.si_code != os.CLD_EXITED or status.si_status != 0:
                raise RuntimeError("successful leader lost its pre-reap identity")
            report["leader_waitable_at_reap_boundary"] = True
            report["writer_exited_before_leader_reap"] = writer_exited()
            if not report["writer_exited_before_leader_reap"]:
                state["channel"].sendall(b"W")
                acknowledgment = b""
                while len(acknowledgment) < len(b"written"):
                    chunk = state["channel"].recv(len(b"written") - len(acknowledgment))
                    if not chunk:
                        raise RuntimeError("fixture writer closed before confirming its real write")
                    acknowledgment += chunk
                if acknowledgment != b"written":
                    raise RuntimeError("fixture writer did not confirm its real write")
                report["writer_wrote_after_leader_exit"] = (
                    root / "plugins/after-leader-exit"
                ).read_bytes() == b"owned-writer-still-active"
            return original_reap(group)

        try:
            with patch.object(gate.ChildGroup, "wait_exit", new=wait_with_handshake), \
                 patch.object(gate.ChildGroup, "reap", new=checked_reap), \
                 patch.object(gate.os, "killpg", side_effect=anchored_signal):
                gate.bounded_command(
                    [sys.executable, "-c", leader_source, writer_source,
                     str(root / "control.sock"), str(root / "plugins")],
                    root, {"PATH": "/usr/bin:/bin"}, root / "command.log", 5,
                )
            report["command_returned_success"] = True
            report["leader_exit_code"] = state["group"].process.returncode
            try:
                os.waitid(os.P_PID, report["leader_pid"], os.WEXITED | os.WNOWAIT | os.WNOHANG)
            except ChildProcessError:
                report["leader_reaped"] = True
            else:
                report["leader_reaped"] = False
        finally:
            group = state["group"]
            if group is not None and group.armed:
                # Patches have ended. Keep the real guard's owned anchor while
                # cleaning an early fixture failure, before releasing its peer.
                gate.terminate_group(group)
            if state["writer_pidfd"] is not None:
                if not writer_exited():
                    signal.pidfd_send_signal(state["writer_pidfd"], signal.SIGKILL)
                poller = select.poll()
                poller.register(state["writer_pidfd"], select.POLLIN)
                if not poller.poll(3000):
                    raise RuntimeError("owned fixture writer did not exit for cleanup")
                status = os.waitid(os.P_PID, state["writer_pid"], os.WEXITED | os.WNOWAIT | os.WNOHANG)
                if status is None:
                    raise RuntimeError("fixture writer is not the adopted waitable child")
                report["writer_wait_status"] = {"code": status.si_code, "status": status.si_status}
                pid, status = os.waitpid(state["writer_pid"], 0)
                report["writer_reaped"] = pid == state["writer_pid"]
                os.close(state["writer_pidfd"])
            # This fresh fixture process owns only this descendant tree. Reap
            # any adopted child from an early handshake failure too; never
            # signal an unverified PID or leave a successful fixture with a
            # waitable child. The normal path already reaped both identities.
            cleanup_deadline = time.monotonic() + 3
            while True:
                try:
                    status = os.waitid(os.P_ALL, 0, os.WEXITED | os.WNOWAIT | os.WNOHANG)
                except ChildProcessError:
                    report["fixture_children_all_reaped"] = True
                    break
                if status is not None:
                    os.waitpid(status.si_pid, 0)
                elif time.monotonic() >= cleanup_deadline:
                    raise RuntimeError("owned fixture descendant cleanup remained incomplete")
                else:
                    time.sleep(0.01)  # Bounded cleanup polling, never readiness.
            if state["channel"] is not None:
                state["channel"].close()
            listener.close()
    print(json.dumps(report, sort_keys=True), flush=True)


class OriginalProcessGuardTests(unittest.TestCase):
    def setUp(self):
        self.assertTrue(gate.child_anchor_available(), "Linux waitable-child profile required")
        self.temp = tempfile.TemporaryDirectory(prefix="hepta-guard-test-")
        self.root = Path(self.temp.name)
        self.children = []
        self.consumed = {}
        self.real_spawn = subprocess.Popen
        self.real_killpg = os.killpg

    def tearDown(self):
        # Only these newly spawned test children. Never signal a PID after an
        # ECHILD result, including if an assertion in the tested code failed.
        for child in self.children:
            if child.returncode is not None:
                continue
            try:
                os.waitid(os.P_PID, child.pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
            except ChildProcessError:
                if child.pid in self.consumed:
                    child.returncode = self.consumed[child.pid]
                continue
            try:
                self.real_killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            # All signals are complete before this final test-owned reap.
            child.wait(timeout=2)
        self.temp.cleanup()

    def spawn(self, *args, **kwargs):
        child = self.real_spawn(*args, **kwargs)
        self.children.append(child)
        return child

    def command(self, source, timeout=2):
        return gate.bounded_command(
            [sys.executable, "-c", source], self.root, {"PATH": "/usr/bin:/bin"},
            self.root / "command.log", timeout,
        )

    def consume(self, pid):
        actual, status = os.waitpid(pid, 0)
        self.assertEqual(actual, pid)
        self.consumed[pid] = os.waitstatus_to_exitcode(status)

    def test_failed_real_leader_remains_waitable_until_every_group_signal_finishes(self):
        observed = []

        def signal_spy(pid, signum):
            status = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
            self.assertIsNotNone(status, "exit-1 leader must still be waitable")
            self.assertEqual((status.si_pid, status.si_code, status.si_status), (pid, os.CLD_EXITED, 1))
            observed.append(signum)
            # Already exited own child; do not send a signal in this proof.

        with patch.object(gate.subprocess, "Popen", side_effect=self.spawn), \
             patch.object(gate.os, "killpg", side_effect=signal_spy), \
             patch.object(gate, "GROUP_GRACE_SECONDS", 0.02):
            with self.assertRaisesRegex(gate.GateError, "command_failed_exit_1"):
                self.command("raise SystemExit(1)")
        self.assertEqual(observed, [signal.SIGTERM, signal.SIGKILL])
        self.assertEqual(self.children[0].returncode, 1)
        with self.assertRaises(ChildProcessError):
            os.waitid(os.P_PID, self.children[0].pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)

    def test_timeout_signals_only_anchored_real_child_then_reaps(self):
        observed = []

        def anchored_signal(pid, signum):
            # None means our live waitable child; a result means its unreaped
            # exit. Either pins the ID. ECHILD would fail this test immediately.
            os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
            observed.append(signum)
            return self.real_killpg(pid, signum)

        started = time.monotonic()
        with patch.object(gate.subprocess, "Popen", side_effect=self.spawn), \
             patch.object(gate.os, "killpg", side_effect=anchored_signal), \
             patch.object(gate, "GROUP_GRACE_SECONDS", 0.02):
            with self.assertRaisesRegex(gate.GateError, "command_deadline_exceeded"):
                self.command("import time; time.sleep(10)", timeout=0.1)
        self.assertEqual(observed, [signal.SIGTERM, signal.SIGKILL])
        self.assertLess(time.monotonic() - started, 2)
        self.assertIsNotNone(self.children[0].returncode)

    def test_real_echild_before_cleanup_permanently_disarms_the_group(self):
        original_wait = gate.ChildGroup.wait_exit
        groups = []

        def competing_reaper(group, timeout):
            groups.append(group)
            self.consume(group.process.pid)
            return original_wait(group, timeout)  # Actual Linux ECHILD.

        with patch.object(gate.subprocess, "Popen", side_effect=self.spawn), \
             patch.object(gate.ChildGroup, "wait_exit", new=competing_reaper), \
             patch.object(gate.os, "killpg", side_effect=AssertionError("stale PGID signal")) as signal_spy:
            with self.assertRaisesRegex(gate.GateError, "child_identity_lost"):
                self.command("pass")
            signal_spy.assert_not_called()
        self.assertFalse(groups[0].armed)
        # A later valid-looking kernel result cannot resurrect the revoked
        # anchor. This is a stub, not an attempt to cause real number reuse.
        with patch.object(gate.os, "waitid", return_value=object()) as wait_spy, \
             patch.object(gate.os, "killpg") as signal_spy, \
             patch.object(gate.os, "waitpid") as reap_spy:
            for action in [lambda: groups[0].signal_group(signal.SIGKILL), groups[0].reap]:
                with self.assertRaisesRegex(gate.GateError, "child_identity_lost"):
                    action()
            wait_spy.assert_not_called()
            signal_spy.assert_not_called()
            reap_spy.assert_not_called()

    def test_real_echild_between_term_and_kill_blocks_escalation(self):
        observed = []

        def reaper_at_signal_boundary(pid, signum):
            status = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
            self.assertIsNotNone(status)
            observed.append(signum)
            self.consume(pid)
            # Mock the signal; consume only our own exited child to model a
            # contract-violating competing reaper. Do not send a stale signal.

        with patch.object(gate.subprocess, "Popen", side_effect=self.spawn), \
             patch.object(gate.os, "killpg", side_effect=reaper_at_signal_boundary), \
             patch.object(gate, "GROUP_GRACE_SECONDS", 0.02):
            with self.assertRaisesRegex(gate.GateError, "child_identity_lost"):
                self.command("raise SystemExit(1)")
        self.assertEqual(observed, [signal.SIGTERM], "SIGKILL must not follow identity loss")

    def test_nonwaitable_sigchld_disposition_is_rejected_before_spawn(self):
        original = signal.getsignal(signal.SIGCHLD)
        try:
            for disposition in [signal.SIG_IGN, lambda _sig, _frame: None]:
                with self.subTest(disposition=repr(disposition)):
                    signal.signal(signal.SIGCHLD, disposition)
                    with patch.object(gate.subprocess, "Popen") as spawn:
                        with self.assertRaisesRegex(gate.GateError, "waitable_child_anchor_required_before_spawn"):
                            self.command("pass")
                        spawn.assert_not_called()
                        self.assertFalse((self.root / "command.log").exists())
        finally:
            signal.signal(signal.SIGCHLD, original)

    def test_success_cleans_group_only_while_actual_exit_zero_leader_is_waitable(self):
        observed = []

        def anchored_signal(pid, signum):
            status = os.waitid(os.P_PID, pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)
            self.assertIsNotNone(status)
            self.assertEqual((status.si_pid, status.si_code, status.si_status), (pid, os.CLD_EXITED, 0))
            observed.append(signum)
            return self.real_killpg(pid, signum)

        with patch.object(gate.subprocess, "Popen", side_effect=self.spawn), \
             patch.object(gate.os, "killpg", side_effect=anchored_signal), \
             patch.object(gate, "GROUP_GRACE_SECONDS", 0.02):
            self.command("pass")
        self.assertEqual(observed, [signal.SIGTERM, signal.SIGKILL])
        self.assertEqual(self.children[0].returncode, 0)
        with self.assertRaises(ChildProcessError):
            os.waitid(os.P_PID, self.children[0].pid, os.WEXITED | os.WNOWAIT | os.WNOHANG)

    def test_successful_leader_cannot_leave_a_same_group_plugin_writer(self):
        # The fixture owns a private subreaper process; the unittest process
        # does not change subreaper state or claim any unrelated descendants.
        child = self.spawn(
            [sys.executable, "-B", str(Path(__file__).resolve()), "--successful-writer-fixture"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, start_new_session=True,
        )
        stdout, stderr = child.communicate(timeout=25)
        self.assertEqual(child.returncode, 0, stderr)
        self.assertEqual(stderr, "")
        proof = json.loads(stdout)
        print("owned successful-leader writer proof: " + json.dumps(proof, sort_keys=True), flush=True)
        self.assertTrue(proof["writer_group_matches_leader"])
        self.assertTrue(proof["leader_waitable_at_reap_boundary"])
        self.assertTrue(proof["command_returned_success"])
        self.assertEqual(proof["leader_exit_code"], 0)
        self.assertTrue(proof["leader_reaped"])
        self.assertTrue(proof["writer_reaped"])
        self.assertTrue(proof["fixture_children_all_reaped"])
        self.assertTrue(proof["writer_exited_before_leader_reap"],
                        "successful leader left a live same-group writer at the reap boundary")
        self.assertFalse(proof["writer_wrote_after_leader_exit"])
        self.assertEqual(proof["writer_wait_status"], {"code": os.CLD_KILLED, "status": signal.SIGTERM})
        self.assertEqual(proof["signals"], [signal.SIGTERM, signal.SIGKILL])


if __name__ == "__main__":
    if sys.argv[1:] == ["--successful-writer-fixture"]:
        successful_leader_writer_fixture()
    else:
        unittest.main()
