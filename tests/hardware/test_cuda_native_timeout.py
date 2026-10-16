"""Adversarial native-call deadline regression (CPU only; never opens a GPU).

This currently exposes the PR #57 in-process SIGALRM limitation. The first
test must pass only once the A09 hard watchdog can interrupt/kill a native
worker independently of Python bytecode execution. A host C compiler is needed.
"""

import ctypes
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

import cuda_gemm

C_SOURCE = r"""
#define _POSIX_C_SOURCE 200809L
#include <time.h>

void foreign_busy_call(double seconds) {
    struct timespec start, now;
    clock_gettime(CLOCK_MONOTONIC, &start);
    volatile unsigned long spin = 0;
    for (;;) {
        spin++;
        if ((spin & 65535UL) == 0) {
            clock_gettime(CLOCK_MONOTONIC, &now);
            double elapsed = (now.tv_sec - start.tv_sec) +
                             (now.tv_nsec - start.tv_nsec) / 1000000000.0;
            if (elapsed >= seconds) break;
        }
    }
}
"""


class NativeDeadlineRegression(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not sys.platform.startswith("linux"):
            raise RuntimeError("A09 native deadline regression requires Linux")
        compiler = shutil.which("cc")
        if not compiler:
            raise RuntimeError("A09 native deadline regression requires a C compiler")
        cls._temp = tempfile.TemporaryDirectory(prefix="a09-native-timeout-")
        root = Path(cls._temp.name)
        source = root / "foreign.c"
        shared = root / "foreign.so"
        source.write_text(C_SOURCE, encoding="utf-8")
        subprocess.run(
            [compiler, "-std=c11", "-O2", "-fPIC", "-shared",
             str(source), "-o", str(shared)],
            check=True, capture_output=True, text=True,
        )
        cls.native = ctypes.CDLL(str(shared))
        cls.native.foreign_busy_call.argtypes = [ctypes.c_double]
        cls.native.foreign_busy_call.restype = None

    @classmethod
    def tearDownClass(cls):
        cls._temp.cleanup()

    def test_cuda_native_ctypes_call_has_real_wall_clock_deadline(self):
        """A Python exception eventually raised is NOT a hard time bound."""
        deadline = 0.03
        started = time.monotonic()
        with self.assertRaises(cuda_gemm.TimeoutExpired):
            cuda_gemm.run_bounded(
                lambda: self.native.foreign_busy_call(0.8), deadline,
            )
        elapsed = time.monotonic() - started
        # Normal scheduling margin, far less than the 0.8 s native call.
        self.assertLess(
            elapsed, 0.20,
            f"foreign call returned after {elapsed:.3f}s despite "
            f"{deadline:.3f}s deadline: SIGALRM did not kill the worker",
        )

    def test_operating_system_supervisor_control_terminates_child(self):
        """Demonstrates a viable independent deadline without GPU access."""
        started = time.monotonic()
        with self.assertRaises(subprocess.TimeoutExpired):
            subprocess.run(
                [sys.executable, "-c", "import time; time.sleep(0.8)"],
                timeout=0.03, check=True, capture_output=True,
            )
        self.assertLess(time.monotonic() - started, 0.20)


if __name__ == "__main__":
    unittest.main()
