"""Real disposable Linux children + signal spies; no Agentd, Rust build or device.

Never create actual PID/PGID reuse. Kernel WNOWAIT and ECHILD observations prove
the identity boundary while all deliberately stale signal attempts are mocked.
"""

import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import run_original_agentd as gate


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

    def test_success_uses_actual_exit_status_and_does_not_signal_reaped_identity(self):
        with patch.object(gate.subprocess, "Popen", side_effect=self.spawn), \
             patch.object(gate.os, "killpg", side_effect=AssertionError("success cleanup must not signal")) as signal_spy:
            self.command("pass")
            signal_spy.assert_not_called()
        self.assertEqual(self.children[0].returncode, 0)


if __name__ == "__main__":
    unittest.main()
