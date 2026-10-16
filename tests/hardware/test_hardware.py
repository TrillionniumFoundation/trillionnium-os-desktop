#!/usr/bin/env python3
"""CPU-only contract tests; NEVER count as accelerator execution."""
import math
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

import cuda_gemm
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "support/hardware"))
import probe


class ProbeTests(unittest.TestCase):
    def test_empty_environment_is_unknown_not_supported(self):
        with tempfile.TemporaryDirectory() as directory:
            result = probe.snapshot(Path(directory))
        self.assertEqual(result["pci_devices"], [])
        self.assertEqual(result["candidate"]["matching_visible_devices"], [])
        self.assertIsNone(result["iommu"]["usable_for_passthrough"])
        self.assertFalse(result["gpu_compute_verified"])

    def test_sysfs_ids_driver_iommu_are_observations(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dev = root / "sys/bus/pci/devices/0000:02:00.0"
            dev.mkdir(parents=True)
            for filename, content in (("vendor", "0x10de\n"), ("device", "0xabcd\n"),
                                      ("class", "0x030200\n"), ("dma_mask_bits", "48\n")):
                (dev / filename).write_text(content)
            driver = root / "sys/bus/pci/drivers/nvidia"
            driver.mkdir(parents=True)
            (dev / "driver").symlink_to(driver)
            group = root / "sys/kernel/iommu_groups/8"
            group.mkdir(parents=True)
            (dev / "iommu_group").symlink_to(group)
            result = probe.snapshot(root)
        self.assertEqual(result["candidate"]["matching_visible_devices"], ["0000:02:00.0"])
        self.assertEqual(result["pci_devices"][0]["driver"], "nvidia")
        self.assertEqual(result["pci_devices"][0]["iommu_group"], "8")
        self.assertIsNone(result["firmware_version"])
        self.assertIsNone(result["iommu"]["usable_for_passthrough"])

    def test_non_accelerator_nvidia_pci_is_not_gpu(self):
        with tempfile.TemporaryDirectory() as directory:
            dev = Path(directory) / "sys/bus/pci/devices/0000:00:01.0"
            dev.mkdir(parents=True)
            (dev / "vendor").write_text("0x10de\n")
            (dev / "class").write_text("0x020000\n")
            result = probe.snapshot(Path(directory))
        self.assertEqual(result["candidate"]["matching_visible_devices"], [])


class GemmTests(unittest.TestCase):
    def test_deterministic_f32_golden(self):
        a, b = cuda_gemm.inputs()
        self.assertEqual((len(a), len(b)), (256, 256))
        result = cuda_gemm.reference(a, b)
        self.assertEqual(cuda_gemm.digest(result),
                         "5bf61d6bb17edb58d70dd37589eeab5a02f5cc5d0c5aae5d142b06678416d847")
        self.assertIsNone(cuda_gemm.compare(result, result))

    def test_mismatch_never_passes(self):
        a, b = cuda_gemm.inputs()
        expected = cuda_gemm.reference(a, b)
        modified = expected.copy()
        modified[3] += 1
        self.assertEqual(cuda_gemm.compare(modified, expected)["index"], 3)
        modified[3] = math.nan
        self.assertEqual(cuda_gemm.compare(modified, expected)["actual"], "nan")

    def test_missing_driver_never_falls_back_to_cpu(self):
        with patch.object(cuda_gemm, "library", side_effect=cuda_gemm.Blocked("no driver")):
            with self.assertRaises(cuda_gemm.Blocked):
                cuda_gemm.gpu_gemm("RTX 4060", "")

    def test_blocked_evidence_keeps_host_provenance_and_unrun_stages_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "blocked.json"
            with patch.object(cuda_gemm, "library",
                              side_effect=cuda_gemm.Blocked("no driver")), \
                    patch.object(sys, "argv", ["cuda_gemm.py", "--output", str(output)]):
                self.assertEqual(cuda_gemm.main(supervise=False), 2)
            evidence = json.loads(output.read_text())
        self.assertEqual(evidence["schema"], "a09.cuda-gemm.v2")
        self.assertEqual(evidence["status"], "blocked")
        provenance = evidence["execution_provenance"]
        self.assertEqual(provenance["execution_layer"], "linux_worker_cuda_driver_api")
        self.assertFalse(provenance["asterinas_execution_verified"])
        self.assertTrue(provenance["process_id"] > 0)
        self.assertFalse(evidence["timeout_enforced"])
        self.assertEqual(evidence["reported_execution_kernel"],
                         f"{cuda_gemm.platform.system()} {cuda_gemm.platform.release()}")
        self.assertTrue(all(value == "not_run" for value in evidence["stages"].values()))

    def test_timeout_marks_inflight_stage_and_never_claims_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "timeout.json"

            def fake_gpu(_name, _bdf, stages):
                stages["synchronize"] = "in_progress"
                raise cuda_gemm.TimeoutExpired("test timeout")

            with patch.object(cuda_gemm, "gpu_gemm", side_effect=fake_gpu), \
                    patch.object(sys, "argv", ["cuda_gemm.py", "--output", str(output)]):
                self.assertEqual(cuda_gemm.main(supervise=False), 1)
            evidence = json.loads(output.read_text())
        self.assertEqual(evidence["status"], "timeout")
        self.assertEqual(evidence["stages"]["synchronize"], "failed")
        self.assertFalse(evidence["failure_recovery_verified"])

    def test_production_entrypoint_uses_reaped_worker_supervisor(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "supervised.json"

            def fake_worker(argv, timeout_seconds):
                self.assertGreater(timeout_seconds, 0)
                self.assertIn("--worker", argv)
                worker_output = Path(argv[argv.index("--output") + 1])
                a, b = cuda_gemm.inputs()
                evidence = cuda_gemm._base_evidence(
                    cuda_gemm.reference(a, b), a, b, timeout_seconds)
                evidence.update(status="blocked", error="no driver")
                worker_output.write_text(json.dumps(evidence), encoding="utf-8")
                return 2, {
                    "supervisor": "linux_start_new_session_killpg",
                    "worker_pid": 123,
                    "timeout_seconds": timeout_seconds,
                    "worker_reaped": True,
                    "worker_exit_code": 2,
                    "timed_out": False,
                    "effect_result_known": False,
                    "device_reset_verified": False,
                }

            with patch.object(cuda_gemm.process_supervisor, "run_worker",
                              side_effect=fake_worker), \
                    patch.object(sys, "argv", ["cuda_gemm.py", "--output", str(output)]):
                self.assertEqual(cuda_gemm.main(), 2)
            evidence = json.loads(output.read_text())
        self.assertTrue(evidence["timeout_enforced"])
        self.assertEqual(evidence["supervisor"]["worker_reaped"], True)
        self.assertEqual(evidence["execution_provenance"]["execution_layer"],
                         "linux_supervised_worker_cuda_driver_api")

    def test_unreaped_worker_is_unknown_effect_and_never_success(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "unknown.json"
            record = {
                "supervisor": "linux_start_new_session_killpg",
                "worker_pid": 456,
                "timeout_seconds": 0.01,
                "worker_reaped": False,
                "worker_exit_code": None,
                "timed_out": True,
                "effect_result_known": False,
                "device_reset_verified": False,
            }
            with patch.object(cuda_gemm.process_supervisor, "run_worker",
                              return_value=(124, record)), \
                    patch.object(sys, "argv", ["cuda_gemm.py", "--output", str(output)]):
                self.assertEqual(cuda_gemm.main(), 1)
            evidence = json.loads(output.read_text())
        self.assertEqual(evidence["status"], "timeout")
        self.assertTrue(evidence["timeout_enforced"])
        self.assertTrue(all(value == "unknown_effect"
                            for value in evidence["stages"].values()))
        self.assertFalse(evidence["failure_recovery_verified"])


if __name__ == "__main__":
    unittest.main()
