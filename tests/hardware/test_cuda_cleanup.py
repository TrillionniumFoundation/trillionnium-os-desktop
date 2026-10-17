"""CPU-only CUDA cleanup contract tests; no device is opened."""
import ctypes as C
import unittest
from cuda_gemm import GpuError, cleanup_device_resources


class FakeCuda:
    def __init__(self, fail=None):
        self.calls = []
        self.fail = fail

    def call(self, name, argtypes, *args):
        self.calls.append(name)
        if name == self.fail:
            raise GpuError("synthetic CUDA cleanup failure")


class CudaCleanupTests(unittest.TestCase):
    @staticmethod
    def resources():
        return [C.c_uint64(3), C.c_uint64(5)], C.c_void_p(7), C.c_void_p(11)

    def test_uncertain_submission_does_not_explicitly_release_dma(self):
        cuda = FakeCuda()
        ptrs, module, ctx = self.resources()
        errors = cleanup_device_resources(cuda, ptrs, module, ctx, True, False)
        self.assertEqual(cuda.calls, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("UNKNOWN_DMA_EFFECT", errors[0])

    def test_synchronized_submission_releases_in_reverse_order(self):
        cuda = FakeCuda()
        ptrs, module, ctx = self.resources()
        self.assertEqual(cleanup_device_resources(cuda, ptrs, module, ctx, True, True), [])
        self.assertEqual(cuda.calls, [
            "cuMemFree_v2", "cuMemFree_v2", "cuModuleUnload", "cuCtxDestroy_v2"
        ])

    def test_prelaunch_failure_can_cleanup(self):
        cuda = FakeCuda()
        ptrs, module, ctx = self.resources()
        self.assertEqual(cleanup_device_resources(cuda, ptrs, module, ctx, False, False), [])
        self.assertEqual(len(cuda.calls), 4)

    def test_cleanup_failure_never_claims_success(self):
        cuda = FakeCuda(fail="cuMemFree_v2")
        ptrs, module, ctx = self.resources()
        errors = cleanup_device_resources(cuda, ptrs, module, ctx, True, True)
        self.assertEqual(len(errors), 2)
        self.assertIn("cuCtxDestroy_v2", cuda.calls)

    def test_uninitialized_context_requires_no_cleanup(self):
        cuda = FakeCuda()
        errors = cleanup_device_resources(
            cuda, [], C.c_void_p(), C.c_void_p(), False, False
        )
        self.assertEqual(errors, [])
        self.assertEqual(cuda.calls, [])


if __name__ == "__main__":
    unittest.main()
