"""Malformed OS-supervisor receipts must never qualify CUDA worker evidence.

Host-only failure-injection: no GPU driver, VMM, or device is opened.
"""
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

import cuda_gemm
import cuda_process_supervisor


class SupervisorReceiptTests(unittest.TestCase):
    def test_incomplete_or_untrusted_group_receipt_blocks_worker_report(self):
        defects = (
            ("status125_without_flags", None),
            ("group_incomplete", "worker_group_incomplete"),
            ("procfs_failed", "worker_group_inspection_failed"),
            ("kill_denied", "worker_group_kill_error"),
            ("identity_lost", "worker_identity_lost"),
            ("worker_unreaped", "unreaped_worker_may_remain"),
        )
        for name, key in defects:
            with self.subTest(name=name), tempfile.TemporaryDirectory() as directory:
                output = pathlib.Path(directory) / "host.json"
                record = {
                    "worker_pid": 123456, "worker_reaped": True,
                    "worker_exit_code": 0, "timed_out": False,
                    "effect_result_known": False, "device_reset_verified": False,
                }
                if key:
                    record[key] = "EPERM" if key == "worker_group_kill_error" else True
                with patch.object(cuda_process_supervisor, "available", return_value=True), \
                     patch.object(cuda_process_supervisor, "run_worker",
                                  return_value=(125, record)), \
                     patch.object(sys, "argv",
                                  ["cuda_gemm.py", "--output", str(output)]):
                    exit_code = cuda_gemm.main()
                result = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(exit_code, 1)
                self.assertEqual(result["status"], "failed")
                self.assertFalse(result["timeout_enforced"])
                self.assertFalse(result["reset_or_failure_recovery_verified"])
                self.assertIn("group/identity cleanup unverified", result["error"])


if __name__ == "__main__":
    unittest.main()
