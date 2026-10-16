#!/usr/bin/env python3
"""CPU-only contract tests; NEVER count as accelerator execution."""
import math
from pathlib import Path
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
                cuda_gemm.gpu_gemm("RTX 4060", "0000:01:00.0", lab_isolated=True)


if __name__ == "__main__":
    unittest.main()
