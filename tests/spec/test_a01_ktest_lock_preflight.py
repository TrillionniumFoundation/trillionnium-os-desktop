"""A01 fixed-lock cold-runner preflight checks; no Rust/network required."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2] / "support/build/ktest"
spec = importlib.util.spec_from_file_location("a01_ktest_locks", ROOT / "prepare-locks.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class ColdRunnerPreflightTests(unittest.TestCase):
    def test_prefetch_only_uses_pinned_root_lock(self):
        upstream = Path("/tmp/a01-pinned-asterinas")
        with patch.object(prepare, "checked_cargo") as call:
            prepare.prefetch_locked_upstream(upstream)
        call.assert_called_once_with(
            ["cargo", "+nightly-2026-07-21", "fetch", "--locked",
             "--manifest-path", str(upstream / "Cargo.toml")],
            cwd=upstream, label="prefetch immutable Asterinas Cargo.lock",
        )
        self.assertNotIn("--offline", call.call_args.args[0])
        self.assertNotIn("--update", call.call_args.args[0])

    def test_offline_error_retains_underlying_cargo_diagnostic(self):
        argv = ["cargo", "+nightly-2026-07-21", "metadata", "--offline"]
        fake = subprocess.CompletedProcess(argv, 101, "", "error: missing pinned crate\n")
        with patch.object(prepare.subprocess, "run", return_value=fake) as run:
            with self.assertRaises(SystemExit) as raised:
                prepare.checked_cargo(argv, cwd=ROOT, label="ostd offline")
        self.assertIn("ostd offline: Cargo exit 101", str(raised.exception))
        self.assertIn("error: missing pinned crate", str(raised.exception))
        self.assertFalse(run.call_args.kwargs["check"])
        self.assertTrue(run.call_args.kwargs["capture_output"])

    def test_failure_receipt_preserves_bounded_streams(self):
        argv = ["cargo", "+nightly-2026-07-21", "metadata", "--offline"]
        fake = subprocess.CompletedProcess(argv, 101, "resolver context\n", "error: missing pinned crate\n")
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(prepare.subprocess, "run", return_value=fake):
                with self.assertRaises(prepare.CargoFailure) as raised:
                    prepare.checked_cargo(argv, cwd=ROOT, label="ostd offline")
            prepare.write_failure_report(Path(directory), raised.exception,
                                         phase="metadata", crate="ostd")
            report = prepare.json.loads((Path(directory) / prepare.FAILURE_REPORT).read_text())
        self.assertFalse(report["passed"])
        self.assertEqual(report["phase"], "metadata")
        self.assertEqual(report["crate"], "ostd")
        self.assertEqual(report["stdout"], "resolver context\n")
        self.assertEqual(report["stderr"], "error: missing pinned crate\n")
        self.assertEqual(report["returncode"], 101)

    def test_success_preserves_machine_readable_metadata(self):
        argv = ["cargo", "metadata", "--offline", "--locked"]
        fake = subprocess.CompletedProcess(argv, 0, '{"resolve":{"nodes":[]}}', "")
        with patch.object(prepare.subprocess, "run", return_value=fake):
            self.assertIs(prepare.checked_cargo(argv, cwd=ROOT, label="locked audit"), fake)

    def test_missing_cargo_fails_closed(self):
        with patch.object(prepare.subprocess, "run", side_effect=FileNotFoundError("cargo")):
            with self.assertRaisesRegex(SystemExit, "cannot start Cargo"):
                prepare.checked_cargo(["cargo", "--version"], cwd=ROOT, label="missing tool")

    def test_preflight_script_remains_executable(self):
        # This build input was executable before the A01 cold-runner patch.
        # Preserve Git's 100755 bit across integrations and reruns.
        import stat
        script = ROOT / "prepare-locks.py"
        self.assertFalse(script.is_symlink())
        self.assertTrue(script.stat().st_mode & stat.S_IXUSR)

    def test_failure_output_is_bounded(self):
        argv = ["cargo", "metadata"]
        fake = subprocess.CompletedProcess(argv, 101, "A" * 100000, "B" * 100000)
        with patch.object(prepare.subprocess, "run", return_value=fake):
            with self.assertRaises(SystemExit) as raised:
                prepare.checked_cargo(argv, cwd=ROOT, label="bounded")
        self.assertLess(len(str(raised.exception)), 26000)


if __name__ == "__main__":
    unittest.main(verbosity=2)
