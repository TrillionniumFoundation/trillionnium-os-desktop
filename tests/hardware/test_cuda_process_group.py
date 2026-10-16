"""Disposable native-process-group safety regression; never opens CUDA/VFIO."""
import os
import pathlib
import signal
import sys
import tempfile
import textwrap
import unittest

import cuda_process_supervisor as supervisor


class OrphanGroupTests(unittest.TestCase):
    def test_early_successful_worker_cannot_leave_unbounded_child(self):
        with tempfile.TemporaryDirectory() as directory:
            pid_file = pathlib.Path(directory) / "grandchild.pid"
            script = textwrap.dedent(f'''
                import subprocess,sys,time
                from pathlib import Path
                child=subprocess.Popen([sys.executable,"-c","import time;time.sleep(15)"],
                    stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,close_fds=True)
                Path({str(pid_file)!r}).write_text(str(child.pid))
                time.sleep(0.06)
            ''')
            record = None
            try:
                status, record = supervisor.run_worker([sys.executable, "-c", script], 5.0)
                self.assertTrue(pid_file.exists())
                self.assertEqual(status, 125, "worker leader success must not hide lingering group")
                self.assertTrue(record["worker_reaped"])
                self.assertTrue(record["worker_group_incomplete"])
                self.assertFalse(record["effect_result_known"])
                self.assertFalse(record["device_reset_verified"])
            finally:
                if record:
                    try:
                        os.killpg(record["worker_pid"], signal.SIGKILL)
                    except ProcessLookupError:
                        pass


if __name__ == "__main__":
    unittest.main()
