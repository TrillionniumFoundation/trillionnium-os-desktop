"""Actual waitid statuses only; these do not simulate an IBus/GTK success."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import unittest

import probe_gtk_ibus as probe

ROOT = Path(__file__).resolve().parents[3]
guard = probe.load('ibus_waitid_test_guard', ROOT / 'tests/integration/hepta/run_original_agentd.py')


class WaitidObservationTests(unittest.TestCase):
    def test_actual_success_and_failure_remain_distinct_until_reap(self):
        self.assertTrue(guard.child_anchor_available())
        for code in (0, 7):
            process = subprocess.Popen([sys.executable, '-c', f'raise SystemExit({code})'],
                                       start_new_session=True)
            group = guard.ChildGroup(process)
            try:
                status = group.wait_exit(5)
                row = probe.waitid_record(status)
                self.assertEqual(row, {'pid': process.pid, 'uid': os.getuid(), 'si_code': os.CLD_EXITED,
                                      'si_status': code, 'exit_code': code, 'exited_successfully': code == 0})
                self.assertEqual(group.observe_exit(), status)
            finally:
                self.assertEqual(group.reap(), code)

    def test_actual_signal_exit_is_not_a_successful_activation(self):
        process = subprocess.Popen([sys.executable, '-c', 'import os,signal;os.kill(os.getpid(),signal.SIGTERM)'],
                                   start_new_session=True)
        group = guard.ChildGroup(process)
        try:
            row = probe.waitid_record(group.wait_exit(5))
            self.assertFalse(row['exited_successfully'])
            self.assertEqual(row['exit_code'], -signal.SIGTERM)
            self.assertEqual(row['si_code'], os.CLD_KILLED)
        finally:
            self.assertEqual(group.reap(), -signal.SIGTERM)

    def test_no_exit_and_exit_integer_cannot_be_misread_as_success(self):
        self.assertIsNone(probe.waitid_record(None))
        with self.assertRaises(TypeError):
            probe.waitid_record(0)


if __name__ == '__main__':
    unittest.main()
