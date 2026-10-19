"""Real ORIGINAL Linux child regressions for strict reference collection.

These are not Asterinas or Hepta results. Previously Python json.loads
accepted duplicate keys/NaN and a valid stdout masked stderr diagnostics.
"""
import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("a04_reference_runner", HERE / "run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class LinuxReferenceObservation(unittest.TestCase):
    def actual_child(self, program):
        with tempfile.TemporaryDirectory(prefix="a04-reference-output-") as root:
            return runner.run_case("probe", [sys.executable, "-c", program], Path(root))

    def test_valid_single_line_and_zero_exit(self):
        result = self.actual_child('print(\'{"ok":true,"errno":0}\')')
        self.assertEqual(result, {"status": "pass", "exit_code": 0,
                                  "facts": {"ok": True, "errno": 0}, "error": None})

    def test_duplicate_success_key_not_accepted(self):
        result = self.actual_child('print(\'{"ok":false,"ok":true}\')')
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["error"], "invalid stdout: ValueError")

    def test_nonfinite_number_not_accepted(self):
        result = self.actual_child('print(\'{"ok":true,"rate":NaN}\')')
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["error"], "invalid stdout: ValueError")

    def test_stderr_warning_invalidates_matching_stdout(self):
        program = 'import sys; sys.stderr.write("loader error\\n"); print(\'{"ok":true}\')'
        result = self.actual_child(program)
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["error"], "unexpected stderr")
        self.assertNotIn("loader error", str(result))

    def test_extra_stdout_is_not_silently_ignored(self):
        result = self.actual_child('print(\'{"ok":true}\'); print("unexpected line")')
        self.assertEqual(result["status"], "fail")

    def test_nonzero_exit_is_failure_even_with_correct_json(self):
        result = self.actual_child('import sys; print(\'{"ok":true}\'); sys.exit(7)')
        self.assertEqual(result["status"], "fail")
        self.assertEqual(result["exit_code"], 7)
        self.assertEqual(result["error"], "nonzero exit")

    def test_rust_build_receipt_binds_lock_manifest_and_elf(self):
        """A blocked Tokio runtime must retain the successful build identity."""
        with tempfile.TemporaryDirectory(prefix="a04-rust-build-") as root:
            binary_dir = Path(root)
            build = SimpleNamespace(returncode=0, stderr="")
            elf = {"sha256": "e" * 64, "size": 123, "interpreter": "/lib64/ld-linux-x86-64.so.2",
                   "needed": ["libc.so.6"]}
            runtime = {"status": "not_run", "reason": "host AF_UNIX policy"}
            with patch.object(runner.shutil, "which", return_value="/usr/bin/cargo"), \
                 patch.object(runner, "command", return_value=build) as command, \
                 patch.object(runner, "inspect_elf", return_value=elf), \
                 patch.object(runner, "run_case", return_value=runtime):
                result = runner.run_rust("auto", binary_dir, binary_dir / "scratch", {})
            self.assertEqual(result["status"], "not_run")
            self.assertEqual(result["reason"], "host AF_UNIX policy")
            self.assertEqual(result["build"]["binary"], elf)
            self.assertEqual(result["build"]["manifest_sha256"],
                             runner.digest(runner.HERE / "rust" / "Cargo.toml"))
            self.assertEqual(result["build"]["cargo_lock_sha256"],
                             runner.digest(runner.HERE / "rust" / "Cargo.lock"))
            self.assertEqual(command.call_args.args[0][1:4], ["build", "--offline", "--locked"])


if __name__ == "__main__":
    unittest.main()
