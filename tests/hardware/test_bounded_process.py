"""CPU-only tests for the bounded GPU-lab child wrapper."""
import subprocess
import sys
import unittest
from bounded_process import OutputLimitExceeded, MAX_OUTPUT_BYTES, run_bounded


class BoundedProcessTests(unittest.TestCase):
    def run_code(self, code, timeout=3):
        return run_bounded([sys.executable, "-c", code], capture_output=True,
                           text=True, timeout=timeout, check=False)

    def test_small_json_child(self):
        result = self.run_code('print("{\\"valid\\": true}")')
        self.assertEqual(result.returncode, 0)
        self.assertIn('valid', result.stdout)

    def test_child_stdout_cannot_grow_unbounded(self):
        with self.assertRaises(OutputLimitExceeded):
            self.run_code('import sys;sys.stdout.write("x"*200000);sys.stdout.flush()')

    def test_child_stderr_cannot_grow_unbounded(self):
        with self.assertRaises(OutputLimitExceeded):
            self.run_code('import sys;sys.stderr.write("x"*200000);sys.stderr.flush()')

    def test_timeout_raises_and_kills_child_process_group(self):
        with self.assertRaises(subprocess.TimeoutExpired):
            self.run_code('import time;time.sleep(5)', timeout=0.05)

    def test_nonzero_return_and_output_are_preserved(self):
        result = self.run_code('import sys;sys.stderr.write("failed");sys.exit(17)')
        self.assertEqual(result.returncode, 17)
        self.assertEqual(result.stderr, 'failed')

    def test_invalid_capture_settings_do_not_start_child(self):
        with self.assertRaises(ValueError):
            run_bounded([sys.executable, '-c', 'pass'], capture_output=False,
                        text=True, timeout=1, check=False)
        with self.assertRaises(ValueError):
            run_bounded([sys.executable, '-c', 'pass'], capture_output=True,
                        text=True, timeout=1, check=True)

    def test_strict_size_limit_is_nonzero(self):
        self.assertEqual(MAX_OUTPUT_BYTES, 65536)


if __name__ == '__main__':
    unittest.main()
