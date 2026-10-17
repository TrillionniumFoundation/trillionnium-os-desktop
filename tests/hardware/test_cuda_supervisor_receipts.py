"""CPU-only malicious CUDA worker receipts and watchdog provenance tests.

No real CUDA, PCI, KVM, VFIO or device reset. The worker supervisor is mocked
for CLI evidence tests; real process-group lifecycle tests are separate.
"""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import cuda_gemm


def clean_receipt():
    return {
        "worker_pid": 123456, "worker_reaped": True,
        "worker_exit_code": 0, "timed_out": False,
        "effect_result_known": False, "device_reset_verified": False,
    }


class ReceiptTests(unittest.TestCase):
    def invoke(self, status, record, child=None):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.json"

            def mock_worker(argv, seconds):
                if child is not None:
                    worker_output = Path(argv[argv.index("--output") + 1])
                    worker_output.write_text(json.dumps(child), encoding="utf-8")
                return status, dict(record)

            with patch.object(cuda_gemm, "timeout_available", return_value=True), \
                 patch.object(cuda_gemm.process_supervisor, "run_worker",
                              side_effect=mock_worker), \
                 patch.object(sys, "argv", ["cuda_gemm.py", "--output", str(output)]):
                exit_code = cuda_gemm.main()
            return exit_code, json.loads(output.read_text(encoding="utf-8"))

    def baseline(self):
        a, b = cuda_gemm.inputs()
        return cuda_gemm._base_evidence(
            cuda_gemm.reference(a, b), a, b, 30.0
        )

    def test_unverified_worker_group_blocks_even_if_leader_exited(self):
        cases = (
            (125, None), (0, "worker_group_incomplete"),
            (0, "worker_group_inspection_failed"),
            (0, "worker_group_kill_error"),
            (0, "worker_identity_lost"),
            (0, "unreaped_worker_may_remain"),
        )
        for status, problem in cases:
            with self.subTest(status=status, problem=problem):
                receipt = clean_receipt()
                if problem:
                    receipt[problem] = "EPERM" if problem == "worker_group_kill_error" else True
                exit_code, evidence = self.invoke(status, receipt)
                self.assertEqual(exit_code, 1)
                self.assertEqual(evidence["status"], "failed")
                self.assertFalse(evidence["timeout_enforced"])
                self.assertFalse(evidence["reset_or_failure_recovery_verified"])
                self.assertFalse(evidence["asterinas_execution_verified"])
                self.assertIn("group/identity cleanup unverified", evidence["error"])
                self.assertEqual(set(evidence["stages"].values()), {"unknown_effect"})

    def test_timed_out_worker_keeps_unknown_effect(self):
        receipt = clean_receipt()
        receipt["timed_out"] = True
        exit_code, evidence = self.invoke(124, receipt)
        self.assertEqual(exit_code, 1)
        self.assertEqual(evidence["status"], "timeout")
        self.assertEqual(set(evidence["stages"].values()), {"unknown_effect"})
        self.assertFalse(evidence["reset_or_failure_recovery_verified"])

    def test_forged_success_without_gpu_stages_fails(self):
        fake = self.baseline()
        fake["status"] = "passed_on_reported_cuda_environment"
        fake["asterinas_execution_verified"] = True
        exit_code, evidence = self.invoke(0, clean_receipt(), fake)
        self.assertEqual(exit_code, 1)
        self.assertEqual(evidence["status"], "failed")
        self.assertIn("fixed GEMM proof obligations", evidence["error"])
        self.assertFalse(evidence["asterinas_execution_verified"])

    def test_worker_result_and_exit_code_mismatch_fails(self):
        fake = self.baseline()
        fake["status"] = "blocked"
        exit_code, evidence = self.invoke(0, clean_receipt(), fake)
        self.assertEqual(exit_code, 1)
        self.assertIn("return code and evidence disagree", evidence["error"])

    def test_child_cannot_grant_itself_asterinas_or_reset_attestation(self):
        fake = self.baseline()
        fake["status"] = "blocked"
        fake["asterinas_execution_verified"] = True
        fake["vmm_passthrough_verified"] = True
        fake["physical_device_assignment_verified"] = True
        fake["reset_or_failure_recovery_verified"] = True
        fake["failure_recovery_verified"] = True
        for k in ("asterinas_execution_verified", "vmm_passthrough_verified",
                  "physical_device_assignment_verified"):
            fake["execution_provenance"][k] = True
        exit_code, evidence = self.invoke(2, clean_receipt(), fake)
        self.assertEqual(exit_code, 2)
        self.assertEqual(evidence["status"], "blocked")
        for k in ("asterinas_execution_verified", "vmm_passthrough_verified",
                  "physical_device_assignment_verified",
                  "reset_or_failure_recovery_verified",
                  "failure_recovery_verified"):
            self.assertFalse(evidence[k])
        self.assertFalse(evidence["execution_provenance"]["asterinas_execution_verified"])

    def test_worker_receipt_missing_provenance_fails(self):
        fake = self.baseline()
        del fake["execution_provenance"]
        _, evidence = self.invoke(2, clean_receipt(), fake)
        self.assertEqual(evidence["status"], "failed")

    def test_bounded_reader_rejects_symlink_fifo_and_large_file(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            real = root / "real.json"
            real.write_text('{"schema":"test"}', encoding="utf-8")
            symlink = root / "alias"
            symlink.symlink_to(real)
            with self.assertRaises(OSError):
                cuda_gemm.read_supervised_worker_report(symlink)
            fifo = root / "fifo"
            os.mkfifo(fifo)
            with self.assertRaises(ValueError):
                cuda_gemm.read_supervised_worker_report(fifo)
            big = root / "big.json"
            big.write_bytes(b"x" * (cuda_gemm.MAX_WORKER_REPORT_BYTES + 1))
            with self.assertRaises(ValueError):
                cuda_gemm.read_supervised_worker_report(big)

    def test_strict_json_rejects_duplicate_nested_keys_and_nan(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            for raw in ('{"status":"failed","status":"passed"}',
                        '{"device":{"bdf":"A","bdf":"B"}}',
                        '{"duration":NaN}', '{"duration":Infinity}'):
                with self.subTest(raw=raw):
                    path.write_text(raw, encoding="utf-8")
                    with self.assertRaises(ValueError):
                        cuda_gemm.read_supervised_worker_report(path)

    def test_valid_regular_json_reads_without_device_access(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "report.json"
            path.write_text('{"status":"blocked","device":null}', encoding="utf-8")
            self.assertEqual(
                cuda_gemm.read_supervised_worker_report(path),
                {"status": "blocked", "device": None},
            )


if __name__ == "__main__":
    unittest.main()
