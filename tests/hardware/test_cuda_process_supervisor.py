"""CPU-only OS watchdog contract. No CUDA device access."""
import pathlib
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import Mock, patch

import cuda_process_supervisor as supervisor


class NativeSupervisorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        root = pathlib.Path(cls.temp.name)
        src = root / 'foreign.c'
        cls.marker = root / 'entered-foreign-call.txt'
        cls.native = root / 'foreign'
        src.write_text('''#define _POSIX_C_SOURCE 200809L
#include <time.h>
#include <stdio.h>
int main(int argc, char **argv) {
  if (argc != 2) return 3;
  FILE *f = fopen(argv[1], "w"); if (!f) return 4;
  fputs("entered-foreign", f); fclose(f);
  struct timespec a, b;
  clock_gettime(CLOCK_MONOTONIC, &a);
  volatile unsigned long count = 0;
  for (;;) {
    count++;
    if ((count & 65535UL) == 0) {
      clock_gettime(CLOCK_MONOTONIC, &b);
      double elapsed = (b.tv_sec - a.tv_sec) + (b.tv_nsec - a.tv_nsec)/1e9;
      if (elapsed >= 0.8) break;
    }
  }
  return 0;
}
''', encoding='utf-8')
        subprocess.run(['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror',
                        str(src), '-o', str(cls.native)], check=True,
                       capture_output=True, text=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_native_call_is_killed_and_reaped_before_it_finishes(self):
        started = time.monotonic()
        code, info = supervisor.run_worker(
            [str(self.native), str(self.marker)], 0.05)
        elapsed = time.monotonic() - started
        self.assertTrue(self.marker.exists(), 'foreign code was never entered')
        self.assertEqual(self.marker.read_text(), 'entered-foreign')
        self.assertLess(elapsed, 0.20)
        self.assertEqual(code, 124)
        self.assertTrue(info['timed_out'])
        self.assertTrue(info['worker_reaped'])
        self.assertFalse(info['effect_result_known'])
        self.assertFalse(info['device_reset_verified'])

    def test_successful_child_is_reaped_without_claiming_gpu(self):
        code, info = supervisor.run_worker([sys.executable, '-c', 'pass'], 2.0)
        self.assertEqual(code, 0)
        self.assertTrue(info['worker_reaped'])
        self.assertFalse(info['timed_out'])
        self.assertFalse(info['device_reset_verified'])

    def test_failing_child_is_never_success(self):
        code, info = supervisor.run_worker([sys.executable, '-c', 'raise RuntimeError'], 2.0)
        self.assertNotEqual(code, 0)
        self.assertFalse(info['timed_out'])
        self.assertTrue(info['worker_reaped'])

    def test_ignored_or_custom_sigchld_rejected_before_worker_spawn(self):
        # Python programs embedding the supervisor may install a SIGCHLD
        # handler or ignore SIGCHLD. Neither setting guarantees WNOWAIT
        # will retain an unreaped leader as a safe numeric PGID anchor.
        original = signal.getsignal(signal.SIGCHLD)
        try:
            for handler in (signal.SIG_IGN, lambda _signum, _frame: None):
                with self.subTest(handler=repr(handler)):
                    signal.signal(signal.SIGCHLD, handler)
                    self.assertFalse(supervisor.available())
                    with patch.object(supervisor.subprocess, "Popen") as spawn:
                        with self.assertRaises(ValueError):
                            supervisor.run_worker(["disposable-worker"], 1.0)
                        spawn.assert_not_called()
        finally:
            signal.signal(signal.SIGCHLD, original)

    def test_externally_reaped_worker_pid_is_never_signalled_or_credited(self):
        # A competing SIGCHLD reaper / SIG_IGN may make waitid raise ECHILD.
        # In that case the PID/PGID is no longer pinned by an unreaped child
        # and can be reused; touching it could signal an unrelated process.
        simulated = Mock()
        simulated.pid = 999999
        simulated.args = ["disposable-worker"]
        with patch.object(supervisor, "available", return_value=True), \
             patch.object(supervisor.subprocess, "Popen", return_value=simulated), \
             patch.object(supervisor, "_wait_unreaped",
                          side_effect=ChildProcessError("ECHILD")), \
             patch.object(supervisor, "_kill_anchored_group") as kill_group, \
             patch.object(supervisor, "_reap") as reap:
            code, record = supervisor.run_worker(["disposable-worker"], 1.0)
        self.assertEqual(code, 125)
        self.assertTrue(record["worker_identity_lost"])
        self.assertTrue(record["unreaped_worker_may_remain"])
        self.assertFalse(record["worker_reaped"])
        self.assertFalse(record["effect_result_known"])
        self.assertFalse(record["device_reset_verified"])
        kill_group.assert_not_called()
        simulated.kill.assert_not_called()
        reap.assert_not_called()

    def test_invalid_command_or_timeout_fails_before_spawn(self):
        with self.assertRaises(ValueError):
            supervisor.run_worker('sleep 0.8', 0.05)
        with self.assertRaises(ValueError):
            supervisor.run_worker(['echo'], float('nan'))
        with self.assertRaises(ValueError):
            supervisor.run_worker(['echo'], 0)

if __name__ == '__main__':
    unittest.main()
