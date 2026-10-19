"""A01 fixed-lock cold-runner preflight checks; no Rust/network required."""
import importlib.util
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[2] / "support/build/ktest"
spec = importlib.util.spec_from_file_location("a01_ktest_locks", ROOT / "prepare-locks.py")
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


class ColdRunnerPreflightTests(unittest.TestCase):
    def exercise_current_prefetch(self, *, mutate_fetch=False):
        """Run real preparation/audits; substitute only Cargo execution."""
        upstream = ROOT.parents[2] / "kernel/asterinas"
        seed = prepare.original_seed(upstream)
        bootstrap = (ROOT / "locks/ostd.Cargo.lock").read_bytes()
        working_before = (upstream / "Cargo.lock").read_bytes()
        calls = []

        def cargo(command, *, cwd, label):
            self.assertEqual(command[:2], ["cargo", "+nightly-2026-07-21"])
            self.assertNotEqual(cwd, upstream)
            self.assertNotIn("--update", command)
            self.assertFalse(cwd.is_relative_to(upstream))
            lock = cwd / "Cargo.lock"
            calls.append(command)
            if command[2] == "fetch":
                self.assertEqual(command[2:], ["fetch", "--locked"])
                self.assertEqual(lock.read_bytes(), bootstrap)
                if mutate_fetch:
                    lock.write_bytes(bootstrap + b"\n# unexpected mutation\n")
                return subprocess.CompletedProcess(command, 0, "", "")
            self.assertEqual(command[2], "metadata")
            self.assertIn("--offline", command)
            self.assertEqual(lock.read_bytes(), bootstrap if "--locked" in command else seed)
            # A Cargo-free receipt fixture: the real package and immutable-seed
            # audits still run. This does not claim dependency resolution.
            lock.write_bytes(bootstrap)
            metadata = {"packages": [], "resolve": {"nodes": []}}
            return subprocess.CompletedProcess(command, 0, json.dumps(metadata), "")

        with tempfile.TemporaryDirectory(prefix="a01-prefetch-output-") as output:
            argv = ["prepare-locks.py", "--upstream", str(upstream), "--crate", "ostd",
                    "--output-dir", output]
            with patch.object(sys, "argv", argv), \
                    patch.object(prepare, "checked_cargo", side_effect=cargo), \
                    redirect_stdout(io.StringIO()):
                if mutate_fetch:
                    with self.assertRaisesRegex(SystemExit, "locked prefetch changed its input lock"):
                        prepare.main()
                    self.assertEqual(len(calls), 1)
                else:
                    prepare.main()
                    self.assertEqual(len(calls), 3)
                    self.assertEqual((Path(output) / "ostd.Cargo.lock").read_bytes(), bootstrap)
                    report = json.loads((Path(output) / "ostd.json").read_text())
                    self.assertEqual(report["seed_sha256"], prepare.SEED_SHA256)
                    self.assertEqual(report["seed_package_count"], 234)
                    self.assertEqual(report["package_count"], 97)
                    self.assertEqual(report["external_drift"], [])
        self.assertEqual((upstream / "Cargo.lock").read_bytes(), working_before)

    def test_prefetch_audited_graph_then_normalizes_original_git_seed(self):
        self.exercise_current_prefetch()

    def test_prefetch_lock_mutation_stops_before_metadata(self):
        self.exercise_current_prefetch(mutate_fetch=True)

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
