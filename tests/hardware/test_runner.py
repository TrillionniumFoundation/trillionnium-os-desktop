"""Subprocess runner behavior under synthetic exit, corruption, and timeout."""
import json
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cuda_gemm
import run_isolated_cuda as lab

BDF = "0000:03:00.0"


def fake_good():
    return {
        "schema": "a09.cuda-gemm.v1", "status": "passed_on_reported_cuda_environment",
        "test": "gemm16_f32", "dimension": [cuda_gemm.N] * 3,
        "input_a_sha256": cuda_gemm.GOLDEN_INPUT_A,
        "input_b_sha256": cuda_gemm.GOLDEN_INPUT_B,
        "driver_api": "CUDA Driver API", "compiler": "NVRTC",
        "expected_output_sha256": cuda_gemm.GOLDEN_OUTPUT,
        "actual_output_sha256": cuda_gemm.GOLDEN_OUTPUT,
        "no_cpu_fallback": True, "device_access_attempted": True,
        "device_memory_allocated": True, "cuda_kernel_launched": True,
        "synchronization_completed": True, "results_copied": True,
        "resources_released": True,
        "device": {"device_name": "NVIDIA GeForce RTX 4060", "device_bdf": BDF,
                   "device_index": 0, "cuda_driver_api_version": 12040,
                   "nvrtc_version": "12.4", "compute_capability": "8.9"},
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

    def test_cuda_runtime_version_and_compute_capability_are_required(self):
        invalids = (
            ("compute_capability", "8.6"),
            ("compute_capability", "garbled"),
            ("cuda_driver_api_version", 0),
            ("cuda_driver_api_version", True),
            ("nvrtc_version", ""),
            ("nvrtc_version", "invalid"),
            ("device_index", -1),
            ("device_index", False),
        )
        for key, value in invalids:
            with self.subTest(key=key, value=value):
                evidence = fake_good()
                evidence["device"][key] = value
                code, result = lab.run_lab(
                    BDF, "RTX 4060", True,
                    runner=Mock(return_value=self.result(evidence))
                )
                self.assertEqual(code, 1)
                self.assertIn("CUDA device runtime", result["error"])
                self.assertFalse(result["host_asterinas_execution_attested"])

    def test_missing_runtime_metadata_is_not_a_gpu_pass(self):
        for key in ("compute_capability", "nvrtc_version",
                    "device_index", "cuda_driver_api_version"):
            with self.subTest(key=key):
                evidence = fake_good()
                evidence["device"].pop(key)
                code, result = lab.run_lab(
                    BDF, "RTX 4060", True,
                    runner=Mock(return_value=self.result(evidence))
                )
                self.assertEqual(code, 1)
                self.assertEqual(result["status"], "failed_false_positive_child")

    def test_wrong_gpu_bdf_fails_even_if_child_says_success(self):
        payload = fake_good()
        payload["device"]["device_bdf"] = "0000:05:00.0"
        code, result = lab.run_lab(BDF, "RTX 4060", True,
                                   runner=Mock(return_value=self.result(payload)))
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "failed_false_positive_child")

    def test_requested_gpu_model_must_not_match_ti_variant(self):
        payload = fake_good()
        payload["device"]["device_name"] = "NVIDIA GeForce RTX 4060 Ti"
        code, result = lab.run_lab(BDF, "RTX 4060", True,
                                   runner=Mock(return_value=self.result(payload)))
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "failed_false_positive_child")

    def test_malformed_gpu_identity_types_are_denied_without_crash(self):
        for field, invalid in (("device_bdf", None), ("device_bdf", 1234),
                               ("device_name", None), ("device_name", ["RTX 4060"])):
            with self.subTest(field=field):
                payload = fake_good()
                payload["device"][field] = invalid
                code, result = lab.run_lab(
                    BDF, "RTX 4060", True, runner=Mock(return_value=self.result(payload))
                )
                self.assertEqual(code, 1)
                self.assertEqual(result["status"], "failed_false_positive_child")

    def test_fake_or_incomplete_cleanup_fails(self):
        payload = fake_good()
        payload["resources_released"] = False
        code, result = lab.run_lab(BDF, "RTX 4060", True,
                                   runner=Mock(return_value=self.result(payload)))
        self.assertEqual(code, 1)

    def test_duplicate_child_json_key_rejected_before_acceptance(self):
        malformed = '{"schema":"a09.cuda-gemm.v1","schema":"a09.cuda-gemm.v1"}'
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, malformed, ""))
        code, result = lab.run_lab(BDF, "RTX 4060", True, runner=runner)
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "failed_unparseable_child")
        self.assertIn("duplicate JSON key", result["error"])

    def test_nonfinite_child_json_is_unparseable_not_computation_success(self):
        runner = Mock(return_value=subprocess.CompletedProcess(
            [], 0, '{"schema":"a09.cuda-gemm.v1","value":NaN}', ""
        ))
        code, result = lab.run_lab(BDF, "RTX 4060", True, runner=runner)
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "failed_unparseable_child")
        self.assertIn("non-finite JSON", result["error"])

    def test_unparseable_success_fails(self):
        runner = Mock(return_value=subprocess.CompletedProcess([], 0, "hello", ""))
        code, result = lab.run_lab(BDF, "RTX 4060", True, runner=runner)
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "failed_unparseable_child")

    def test_modified_fixed_input_or_shape_cannot_report_cuda_success(self):
        for key, bad in (("input_a_sha256", "0" * 64),
                         ("input_b_sha256", "0" * 64),
                         ("dimension", [8, 8, 8]),
                         ("test", "cpu_gemm"),
                         ("driver_api", "software"),
                         ("compiler", "fake-compiler")):
            with self.subTest(key=key):
                payload = fake_good()
                payload[key] = bad
                code, result = lab.run_lab(
                    BDF, "RTX 4060", True,
                    runner=Mock(return_value=self.result(payload))
                )
                self.assertEqual(code, 1)
                self.assertEqual(result["status"], "failed_false_positive_child")

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

    def test_overlong_child_output_never_claims_device_recovery(self):
        runner = Mock(side_effect=lab.OutputLimitExceeded("synthetic log flood"))
        code, result = lab.run_lab(BDF, "RTX 4060", True, runner=runner)
        self.assertEqual(code, 1)
        self.assertEqual(result["status"], "failed_output_limit_device_effect_unknown")
        self.assertEqual(result["device_effect_if_failure"], "unknown")
        self.assertFalse(result["DMA_quiescence_attested"])
        self.assertFalse(result["recovery_verified"])

    def test_default_runner_is_bounded_not_unlimited_pipe_capture(self):
        with patch.object(lab, "run_bounded",
                          return_value=self.result({"error": "libcuda unavailable"}, 2)) as run:
            code, record = lab.run_lab(BDF, "RTX 4060", True)
        self.assertEqual(code, 2)
        self.assertEqual(record["status"], "blocked")
        run.assert_called_once()
        self.assertEqual(run.call_args.kwargs["timeout"], 30)
        self.assertEqual(run.call_args.kwargs["check"], False)

    def test_rejected_invocation_retains_complete_fail_closed_evidence_schema(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / "rejected.json"
            with patch.object(sys, "argv", ["run_isolated_cuda.py", "--require-bdf",
                                            BDF, "--output", str(output)]):
                self.assertEqual(lab.main(), 2)
            record = json.loads(output.read_text())
        self.assertEqual(record["status"], "blocked")
        self.assertFalse(record["attempted_device_access"])
        for field in ("guest_kernel_identity_attested", "DMA_quiescence_attested",
                      "recovery_verified", "physical_gpu_passthrough_attested"):
            self.assertIs(record[field], False)
        self.assertEqual(record["device_effect_if_failure"], "unknown")
        self.assertIsNone(record["child_evidence"])


if __name__ == "__main__":
    unittest.main()
