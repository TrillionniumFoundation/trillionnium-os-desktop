"""A09 strict physical PCI identity fixtures; host-only, no CUDA or VFIO."""
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "support/hardware"))
from pci_identity import (canonical_bdf, canonical_nvidia_model,
                          linux_sysfs_bdf, matches_target_model)

import cuda_gemm


class PciIdentityTests(unittest.TestCase):
    def test_cuda_8_digit_and_linux_4_digit_domains_refer_to_same_device(self):
        self.assertEqual(canonical_bdf("0000:01:00.0"), "00000000:01:00.0")
        self.assertEqual(canonical_bdf("00000000:01:00.0"), "00000000:01:00.0")
        self.assertEqual(canonical_bdf("00000000:0A:1F.7"), "00000000:0a:1f.7")
        self.assertEqual(canonical_bdf("0000:0a:1f.7"), "00000000:0a:1f.7")

    def test_domain_changes_are_not_collapsed_or_truncated(self):
        self.assertNotEqual(canonical_bdf("0000:01:00.0"),
                            canonical_bdf("00010000:01:00.0"))
        self.assertNotEqual(canonical_bdf("0000:01:00.0"),
                            canonical_bdf("0001:01:00.0"))

    def test_invalid_bdf_never_normalizes_into_valid_identity(self):
        for value in (None, True, 1, "", " 0000:01:00.0",
                      "000:01:00.0", "00000:01:00.0",
                      "000000000:01:00.0", "0000:01:20.0",
                      "0000:01:00.8", "0000:ff:00.0extra",
                      "0000:01:00.0\n", "../../dev/nvidia0"):
            with self.subTest(value=value):
                self.assertIsNone(canonical_bdf(value))

    def test_exact_model_accepts_only_the_discrete_4060(self):
        for name in ("RTX 4060", "NVIDIA RTX 4060",
                     "GeForce RTX 4060", "NVIDIA GeForce RTX 4060",
                     "NVIDIA   GeForce  RTX 4060"):
            with self.subTest(name=name):
                self.assertTrue(matches_target_model(name, "RTX 4060"))

    def test_similar_models_are_never_a_4060_match(self):
        for name in ("RTX 4060 Ti", "RTX 4060 Laptop GPU",
                     "RTX 4070", "RTX 4060 SUPER", "RTX4060",
                     "Fake NVIDIA GeForce RTX 4060", 4060, None, ""):
            with self.subTest(name=name):
                self.assertFalse(matches_target_model(name, "RTX 4060"))
        self.assertIsNone(canonical_nvidia_model(None))

    def test_missing_or_malformed_bdf_refuses_cuda_before_library_loading(self):
        for value in ("", "0000:01:20.0", "0000:01:00.8"):
            with self.subTest(value=value):
                from unittest.mock import patch
                with patch.object(cuda_gemm, "library",
                                  side_effect=AssertionError("must not access CUDA")):
                    with self.assertRaises(cuda_gemm.Blocked):
                        cuda_gemm.gpu_gemm("RTX 4060", value)

    def test_requested_non_4060_refuses_cuda_before_library_loading(self):
        from unittest.mock import patch
        with patch.object(cuda_gemm, "library",
                          side_effect=AssertionError("must not access CUDA")):
            with self.assertRaises(cuda_gemm.Blocked):
                cuda_gemm.gpu_gemm("RTX 4060 Ti", "0000:01:00.0")

    def test_linux_sysfs_name_is_numeric_equivalence_not_string_width(self):
        for raw in ("0000:01:00.0", "00000000:01:00.0", "00000000:01:00.0"):
            with self.subTest(raw=raw):
                self.assertEqual(linux_sysfs_bdf(raw), "0000:01:00.0")
        self.assertEqual(linux_sysfs_bdf("00000001:0A:1F.7"), "0001:0a:1f.7")

    def test_linux_domain_not_truncated_or_slot_overflow_accepted(self):
        self.assertEqual(linux_sysfs_bdf("00010000:01:00.0"), "00010000:01:00.0")
        self.assertNotEqual(linux_sysfs_bdf("00010000:01:00.0"),
                            linux_sysfs_bdf("0000:01:00.0"))
        for value in ("0000:01:20.0", "00000000:01:20.0", None,
                      "00000:01:00.0", "0000:01:00.8"):
            self.assertIsNone(linux_sysfs_bdf(value))



if __name__ == "__main__":
    unittest.main()
