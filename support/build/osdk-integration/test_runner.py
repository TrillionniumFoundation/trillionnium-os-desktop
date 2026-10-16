"""Verify timeout cleanup against a real TERM-ignoring descendant."""
import fcntl
import importlib.util
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
import unittest

spec = importlib.util.spec_from_file_location("a01_integration_runner", Path(__file__).with_name("run.py"))
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class TimeoutTests(unittest.TestCase):
    def test_descendant_releases_held_lock_before_timeout_returns(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            child = ("import fcntl,os,signal,time; from pathlib import Path; "
                     "handle=open('held.lock','w'); fcntl.flock(handle,fcntl.LOCK_EX); "
                     "signal.signal(signal.SIGTERM,signal.SIG_IGN); "
                     "Path('ready').write_text(str(os.getpid())); time.sleep(60)")
            leader = ("import subprocess,sys,time; from pathlib import Path; "
                      "subprocess.Popen([sys.executable,'-c'," + repr(child) + "]); "
                      "\nwhile not Path('ready').exists(): time.sleep(.01)\n"
                      "time.sleep(60)")
            result = runner.command([sys.executable, "-c", leader], root, os.environ.copy(),
                                    root / "case.log", 0.5)
            ready = root / "ready"
            self.assertTrue(ready.exists(), "descendant never acquired the probe lock")
            try:
                with (root / "held.lock").open("a") as held:
                    # SIGKILL delivery is asynchronous; leader reap alone does
                    # not imply its descendant has already released its files.
                    deadline = time.monotonic() + 2
                    while True:
                        try:
                            fcntl.flock(held, fcntl.LOCK_EX | fcntl.LOCK_NB)
                            break
                        except BlockingIOError:
                            if time.monotonic() >= deadline:
                                raise
                            time.sleep(.01)
                self.assertTrue(result["timed_out"])
                self.assertEqual(result["raw_exit_code"], 124)
            except BaseException:
                # Cleanup only our still-live lock holder if the regression fails.
                try:
                    os.kill(int(ready.read_text()), signal.SIGKILL)
                except ProcessLookupError:
                    pass
                raise


if __name__ == "__main__":
    unittest.main()
