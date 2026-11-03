"""Run only the fixed supervisor with ordinary child processes owned here."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import build_original_entry as build


class OwnedCommandTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.output = self.root / "evidence"
        self.output.mkdir()
        self.target = self.root / "target"
        self.target.mkdir()
        self.report = {"commands": [], "g2_complete": False}
        self.children, self.signals = [], []
        self.popen, self.killpg, self.waitid = subprocess.Popen, os.killpg, os.waitid

    def start(self, *args, **kwargs):
        child = self.popen(*args, **kwargs)
        self.children.append(child)
        self.addCleanup(self.collect, child)
        return child

    def collect(self, child):
        if child.returncode is None:
            child.kill()
            child.wait(timeout=5)

    def signal_owned(self, pid, sig):
        self.assertEqual(pid, self.children[0].pid)
        self.assertIsNone(self.children[0].returncode)
        self.waitid(os.P_PID, pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        with self.assertRaisesRegex(ValueError, "already leased"):
            with build.target_lease(self.target):
                self.fail("target lease released before owned child cleanup")
        self.signals.append((pid, sig))
        return self.killpg(pid, sig)

    def command(self, source, timeout=3):
        build.run([sys.executable, "-I", "-B", "-c", source], self.root, build.BASE_ENV,
                  self.output, "owned.log", self.report, timeout)

    def test_normal_child_exit_preserves_output_without_group_signal(self):
        with patch.object(build.subprocess, "Popen", side_effect=self.start), \
                patch.object(build.os, "killpg", side_effect=self.signal_owned), build.target_lease(self.target):
            self.command('print("owned command complete")')
        self.assertEqual(self.signals, [])
        self.assertEqual(self.children[0].returncode, 0)
        self.assertEqual((self.output / "owned.log").read_text(), "owned command complete\n")
        self.assertTrue(self.report["commands"][0]["completed"])

    def test_timeout_signals_owned_group_once_and_reaps_before_lease_release(self):
        with patch.object(build.subprocess, "Popen", side_effect=self.start), \
                patch.object(build.os, "killpg", side_effect=self.signal_owned), build.target_lease(self.target), \
                self.assertRaisesRegex(ValueError, "original command failed"):
            self.command("import time; time.sleep(2)", timeout=0.15)
        self.assertEqual(self.signals, [(self.children[0].pid, signal.SIGKILL)])
        self.assertEqual(self.children[0].returncode, -signal.SIGKILL)
        self.assertTrue(self.report["commands"][0]["timed_out"])
        self.assertFalse(json.loads((self.output / "result.json").read_text())["g2_complete"])
        with build.target_lease(self.target):
            pass

    def test_interruptions_clean_owned_child_and_retain_failure(self):
        for interruption in (KeyboardInterrupt, SystemExit):
            with self.subTest(interruption=interruption.__name__):
                self.children.clear()
                self.signals.clear()
                self.report = {"commands": [], "g2_complete": False}
                (self.output / "owned.log").unlink(missing_ok=True)
                interrupted = False

                def observe(*args, **kwargs):
                    nonlocal interrupted
                    if not interrupted:
                        interrupted = True
                        raise interruption("ordinary cancellation")
                    return self.waitid(*args, **kwargs)

                with patch.object(build.subprocess, "Popen", side_effect=self.start), \
                        patch.object(build.os, "killpg", side_effect=self.signal_owned), \
                        patch.object(build.os, "waitid", side_effect=observe), build.target_lease(self.target), \
                        self.assertRaises(interruption):
                    self.command("import time; time.sleep(2)")
                self.assertEqual(self.signals, [(self.children[0].pid, signal.SIGKILL)])
                self.assertEqual(self.children[0].returncode, -signal.SIGKILL)
                record = json.loads((self.output / "result.json").read_text())["commands"][0]
                self.assertTrue(record["completed"])
                self.assertTrue(record["error"].startswith(interruption.__name__ + ":"))

    def test_interruption_after_normal_reap_never_signals_numeric_group(self):
        def start(*args, **kwargs):
            child = self.start(*args, **kwargs)
            original_wait = child.wait

            def reap(*args, **kwargs):
                original_wait(*args, **kwargs)
                raise KeyboardInterrupt("ordinary cancellation after child completion")

            child.wait = reap
            return child

        with patch.object(build.subprocess, "Popen", side_effect=start), \
                patch.object(build.os, "killpg", side_effect=self.signal_owned), build.target_lease(self.target), \
                self.assertRaises(KeyboardInterrupt):
            self.command("pass")
        self.assertEqual(self.signals, [])
        self.assertEqual(self.children[0].returncode, 0)
        self.assertIn("KeyboardInterrupt", self.report["commands"][0]["error"])

    def test_lost_wait_ownership_disarms_group_signalling(self):
        def already_collected(*args, **kwargs):
            self.children[0].wait(timeout=3)
            raise ChildProcessError("ordinary child already collected by its owner")

        with patch.object(build.subprocess, "Popen", side_effect=self.start), \
                patch.object(build.os, "killpg", side_effect=self.signal_owned), \
                patch.object(build.os, "waitid", side_effect=already_collected), build.target_lease(self.target), \
                self.assertRaisesRegex(ValueError, "wait ownership was lost"):
            self.command("pass")
        self.assertEqual(self.signals, [])
        self.assertEqual(self.children[0].returncode, 0)
        self.assertTrue(self.report["commands"][0]["wait_owner_lost"])

    def test_nondefault_sigchld_is_refused_before_child_creation(self):
        with patch.object(build.signal, "getsignal", return_value=signal.SIG_IGN), \
                patch.object(build.subprocess, "Popen") as start, \
                self.assertRaisesRegex(ValueError, "sole wait ownership"):
            self.command("pass")
        start.assert_not_called()
        self.assertFalse((self.output / "owned.log").exists())


if __name__ == "__main__":
    unittest.main()
