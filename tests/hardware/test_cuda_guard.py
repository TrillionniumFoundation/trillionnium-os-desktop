"""CPU-only safety tests: deliberately mock GPU compute; never claim real CUDA execution."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cuda_gemm as gemm


class GuardTests(unittest.TestCase):
    def invoke(self, args):
        stream = io.StringIO()
        with patch.object(sys, "argv", ["cuda_gemm.py"] + args), contextlib.redirect_stdout(stream):
            status = gemm.main()
        return status, json.loads(stream.getvalue())

    def test_direct_gpu_function_without_opt_in_cannot_load_cuda(self):
        with patch.object(gemm, "library") as loader:
            with self.assertRaises(gemm.Blocked):
                gemm.gpu_gemm("RTX 4060", "0000:01:00.0")
        loader.assert_not_called()

    def test_naked_command_cannot_load_cuda(self):
        with patch.object(gemm, "gpu_gemm") as call:
            rc, report = self.invoke([])
        self.assertEqual(rc, 2)
        self.assertIn("--isolated-lab", report["error"])
        self.assertFalse(report["device_access_attempted"])
        call.assert_not_called()

    def test_assertion_without_pinned_bdf_blocks(self):
        with patch.object(gemm, "gpu_gemm") as call:
            rc, report = self.invoke(["--isolated-lab"])
        self.assertEqual(rc, 2)
        self.assertIn("--require-bdf", report["error"])
        call.assert_not_called()

    def test_invalid_bdf_blocks(self):
        with patch.object(gemm, "gpu_gemm") as call:
            rc, report = self.invoke(["--isolated-lab", "--require-bdf", "../../dev/nvidia0"])
        self.assertEqual(rc, 2)
        self.assertFalse(report["device_access_attempted"])
        call.assert_not_called()

    def test_actual_bdf_and_lab_assertion_reach_cuda(self):
        with patch.object(gemm, "gpu_gemm", side_effect=gemm.Blocked("GPU not visible")) as call:
            rc, report = self.invoke(["--isolated-lab", "--require-bdf", "0000:01:00.0"])
        self.assertEqual(rc, 2)
        self.assertTrue(report["device_access_attempted"])
        self.assertFalse(report["asterinas_execution_verified"])
        call.assert_called_once_with("RTX 4060", "0000:01:00.0", lab_isolated=True)

    def test_synthetic_perfect_output_does_not_attest_new_kernel(self):
        # Mock only; NOT hardware validation.
        with patch.object(gemm, "gpu_gemm", return_value=({"device_name": "mock", "device_bdf": "0000:01:00.0"},
                                                            gemm.reference(*gemm.inputs()))):
            rc, report = self.invoke(["--isolated-lab", "--require-bdf", "0000:01:00.0"])
        self.assertEqual(rc, 0)
        self.assertEqual(report["status"], "passed_on_reported_cuda_environment")
        self.assertFalse(report["host_kernel_attested"])
        self.assertFalse(report["guest_kernel_attested"])
        self.assertFalse(report["actual_gpu_location_attested"])

    def test_changed_golden_blocks_before_cuda(self):
        with patch.object(gemm, "GOLDEN_OUTPUT", "0" * 64), patch.object(gemm, "gpu_gemm") as call:
            rc, report = self.invoke(["--isolated-lab", "--require-bdf", "0000:01:00.0"])
        self.assertEqual(rc, 1)
        self.assertIn("golden", report["error"])
        call.assert_not_called()


if __name__ == "__main__":
    unittest.main()
