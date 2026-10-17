import os
import signal
import subprocess
import sys
import unittest
from unittest.mock import patch
import cuda_process_supervisor as supervisor

class GroupLifetimeTests(unittest.TestCase):
    def test_leader_remains_unreaped_until_group_kill(self):
        observed = []
        original = os.killpg
        def inspect_before_kill(pgid, signo):
            if signo == signal.SIGKILL:
                observed.append(os.path.exists(f'/proc/{pgid}/stat'))
            return original(pgid, signo)
        script = (
            'import subprocess,sys,time;'
            'subprocess.Popen([sys.executable,"-c","import time;time.sleep(5)"],'
            'stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);'
            'time.sleep(.08)'
        )
        with patch.object(supervisor.os, 'killpg', side_effect=inspect_before_kill):
            code, record = supervisor.run_worker([sys.executable,'-c',script], 2.0)
        self.assertEqual(code,125)
        self.assertTrue(observed)
        self.assertTrue(all(observed), 'leader was reaped before killpg; old PGID could be recycled')

if __name__=='__main__':unittest.main()
