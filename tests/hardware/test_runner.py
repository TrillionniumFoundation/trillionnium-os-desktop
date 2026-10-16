"""Subprocess runner behavior under synthetic exit, corruption, and timeout."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cuda_gemm
import run_isolated_cuda as lab

BDF = "0000:03:00.0"


def fake_good():
    return {
        "schema": "a09.cuda-gemm.v1", "status": "passed_on_reported_cuda_environment",
        "expected_output_sha256": cuda_gemm.GOLDEN_OUTPUT,
        "actual_output_sha256": cuda_gemm.GOLDEN_OUTPUT,
        "no_cpu_fallback": True, "device_access_attempted": True,
        "device_memory_allocated": True, "cuda_kernel_launched": True,
        "synchronization_completed": True, "results_copied": True,
        "resources_released": True,
        "device": {"device_name": "NVIDIA GeForce RTX 4060", "device_bdf": BDF},
    }


class LabRunnerTests(unittest.TestCase):
    def result(self, payload, returncode=0):
        return subprocess.CompletedProcess(args=[], returncode=returncode,
                                           stdout=json.dumps(payload), stderr="")

    def test_missing_lab_opt_in_never_starts_child(self):
        runner = Mock()
        with self.assertRaises(lab.Blocked):
            lab.run_lab(BDF, "RTX 4060", False, runner=runner)
        runner.assert_not_called()

    def test_missing_bdf_never_starts_child(self):
        runner = Mock()
        with self.assertRaises(lab.Blocked):
            lab.run_lab("", "RTX 4060", True, runner=runner)
        runner.assert_not_called()

    def test_timeout_leaves_device_effect_unknown(self):
        runner = Mock(side_effect=subprocess.TimeoutExpired(cmd="cuda", timeout=1))
        code, result = lab.run_lab(BDF, "RTX 4060", True, timeout_seconds=1, runner=runner)
        self.assertEqual(code, 4)
        self.assertEqual(result["status"], "timed_out_device_effect_unknown")
        self.assertFalse(result["DMA_quiescence_attested"])
        self.assertFalse(result["recovery_verified"])
        self.assertEqual(result["device_effect_if_failure"], "unknown")

    def test_child_gpu_missing_blocks(self):
        runner = Mock(return_value=self.result({"schema": "a09.cuda-gemm.v1", "error": "libcuda missing"}, 2))
        code, result = lab.run_lab(BDF, "RTX 4060", True, runner=runner)
        self.assertEqual(code, 2)
        self.assertEqual(result["status"], "blocked")

    def test_valid_synthetic_report_still_does_not_attest_host(self):
        runner = Mock(return_value=self.result(fake_good()))
        code, result = lab.run_lab(BDF, "RTX 4060", True, runner=runner)
        self.assertEqual(code, 0)
        self.assertEqual(result["status"], "guest_cuda_reported_pass_not_asterinas_attestation")
        self.assertFalse(result["host_asterinas_execution_attested"])
        self.assertFalse(result["physical_gpu_passthrough_attested"])
        self.assertFalse(result["DMA_quiescence_attested"])
        self.assertEqual(runner.call_args.kwargs["check"], False)
        self.assertNotIn("shell", runner.call_args.kwargs)

    def test_wrong_gpu_bdf_fails_even_if_child_says_success(self):
        payload = fake_good()
        payload["device"]["device_bdf"] = "0000:05:00.0"
        code, result = lab.run_lab(BDF, "RTX 4060", True,
                                   runner=Mock(return_value=self.result(payload)))
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "failed_false_positive_child")

    def test_fake_or_incomplete_cleanup_fails(self):
        payload = fake_good()
        payload["resources_released"] = False
        code, result = lab.run_lab(BDF, "RTX 4060", True,
                                   runner=Mock(return_value=self.result(payload)))
        self.assertEqual(code, 1)

    def test_unparseable_success_fails(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, "hello", ""))
        code, result = lab.run_lab(BDF, "RTX 4060", True, runner=runner)
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "failed_unparseable_child")

    def test_numeric_corruption_fails(self):
        payload = fake_good()
        payload["actual_output_sha256"] = "0" * 64
        code, result = lab.run_lab(BDF, "RTX 4060", True,
                                   runner=Mock(return_value=self.result(payload)))
        self.assertEqual(code, 1)
        self.assertIn("actual_output_sha256", result["error"])

    def test_device_error_is_unknown_effect(self):
        payload = {"schema": "a09.cuda-gemm.v1", "error": "CUDA_ERROR_LAUNCH_FAILED"}
        code, result = lab.run_lab(BDF, "RTX 4060", True,
                                   runner=Mock(return_value=self.result(payload, 1)))
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "failed_device_effect_unknown")


if __name__ == "__main__":
    unittest.main()
