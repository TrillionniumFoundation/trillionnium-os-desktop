"""CPU-only NVRTC/CUDA API result-size adversarial checks; no GPU opens."""
import ctypes as C
import unittest
from unittest.mock import patch

import cuda_gemm


class CudaAllocationBoundTests(unittest.TestCase):
    def test_valid_minimum_and_exact_maximum_nvrtc_lengths(self):
        self.assertEqual(cuda_gemm.checked_nvrtc_size(1, cuda_gemm.MAX_NVRTC_LOG_BYTES, "log"), 1)
        self.assertEqual(cuda_gemm.checked_nvrtc_size(
            cuda_gemm.MAX_NVRTC_LOG_BYTES, cuda_gemm.MAX_NVRTC_LOG_BYTES, "log"
        ), cuda_gemm.MAX_NVRTC_LOG_BYTES)
        self.assertEqual(cuda_gemm.checked_nvrtc_size(
            cuda_gemm.MAX_NVRTC_PTX_BYTES, cuda_gemm.MAX_NVRTC_PTX_BYTES, "ptx"
        ), cuda_gemm.MAX_NVRTC_PTX_BYTES)

    def test_unbounded_or_zero_nvrtc_lengths_fail_before_allocation(self):
        for limit in (cuda_gemm.MAX_NVRTC_LOG_BYTES, cuda_gemm.MAX_NVRTC_PTX_BYTES):
            for candidate in (-1, 0, limit + 1, 1 << 60):
                with self.subTest(limit=limit, candidate=candidate):
                    with self.assertRaises(cuda_gemm.GpuError):
                        cuda_gemm.checked_nvrtc_size(candidate, limit, "fixture")

    def test_noninteger_sizes_rejected_including_boolean(self):
        for candidate in (None, True, 1.0, "12"):
            with self.subTest(candidate=candidate):
                with self.assertRaises(cuda_gemm.GpuError):
                    cuda_gemm.checked_nvrtc_size(candidate, 1024, "fixture")

    def test_synthetic_driver_excessive_device_count_blocks_enumeration(self):
        class FakeCuda:
            def __init__(self):
                self.calls = []

            def call(self, name, argtypes, *args):
                self.calls.append(name)
                if name == "cuDeviceGetCount":
                    C.cast(args[0], C.POINTER(C.c_int))[0] = cuda_gemm.MAX_CUDA_ENUM_DEVICES + 1

        cuda = FakeCuda()
        with patch.object(cuda_gemm, "library", return_value=object()), \
             patch.object(cuda_gemm, "Api", return_value=cuda):
            with self.assertRaises(cuda_gemm.Blocked):
                cuda_gemm.gpu_gemm("RTX 4060", "0000:01:00.0", lab_isolated=True)
        self.assertEqual(cuda.calls, ["cuInit", "cuDeviceGetCount"])


if __name__ == "__main__":
    unittest.main()
