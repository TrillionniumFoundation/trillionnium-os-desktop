#!/usr/bin/env python3
"""Host-only fixed-root failure/cancellation custody, without Cargo or QEMU."""
import importlib.util
import json
import os
from pathlib import Path
import signal
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get("A01_FIXED_ROOT_RUNNER_SOURCE", str(HERE / "run.py")))
SPEC = importlib.util.spec_from_file_location("a01_fixed_cleanup", SOURCE)
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class FixedRootCleanupTests(unittest.TestCase):
    def test_public_prepare_failure_clears_owned_root(self):
        self.public_failure("adaptation")

    def test_public_offline_lock_normalization_failure_clears_owned_root(self):
        self.public_failure("normalization")

    def test_public_cancellation_clears_owned_root(self):
        self.public_failure("cancelled")

    def test_public_osdk_build_failure_clears_owned_root(self):
        self.public_failure("build")

    def test_unknown_derived_lock_is_rejected_before_any_cargo_command(self):
        self.public_failure("unknown-lock")

    def public_failure(self, mode):
        with tempfile.TemporaryDirectory(prefix="a01-fixed-cleanup-") as temporary:
            root = Path(temporary)
            output, fixed = root / "output", root / "owned-fixed"
            output.mkdir()
            project = root / "project"
            upstream = project / "kernel/asterinas"
            (upstream / "osdk/tests/util").mkdir(parents=True)
            (upstream / "rust-toolchain.toml").write_text("[toolchain]\nchannel='host-fixture'\n")
            (upstream / "osdk/tests/util/mod.rs").write_text(
                '// deliberately missing anchor\n' if mode == "adaptation" else 'env!("CARGO_MANIFEST_DIR")\n')
            (upstream / "osdk/Cargo.lock").write_bytes(
                (HERE.parents[2] / "kernel/asterinas/osdk/Cargo.lock").read_bytes())
            if mode == "unknown-lock":
                with (upstream / "osdk/Cargo.lock").open("ab") as stream:
                    stream.write(b"\n# unknown derived lock bytes\n")
            def allocate(**_kwargs):
                fixed.mkdir()
                (fixed / "large-owned-artifact").write_bytes(b"disposable host-only bytes")
                return str(fixed)
            def cancelled(*_args, **kwargs):
                if "fixed_root" not in kwargs:  # Retained original runner comparison.
                    allocate()
                    identity = fixed.stat()
                    (output / "fixed-root.json").write_text(json.dumps({"path": str(fixed),
                        "device": identity.st_dev, "inode": identity.st_ino}))
                os.kill(os.getpid(), signal.SIGTERM)
                RUNNER._active_shutdown.check()
            args = SimpleNamespace(coverage_gdb=False, local_tcp=False, target_dir=None,
                                   case=None, case_timeout=1)
            expected_error = {"adaptation": "manifest anchor changed",
                              "normalization": "lock normalization failed",
                              "build": "original OSDK source build failed",
                              "unknown-lock": "fixed derived OSDK harness seed lock differs"}
            command = mock.Mock(side_effect=[{"raw_exit_code": 0}, {"raw_exit_code": 1}]) \
                if mode == "build" else mock.Mock(return_value={"raw_exit_code": 1})
            actual_seed = RUNNER.prepare_root_seed
            with mock.patch.object(RUNNER, "prepare_root_seed", side_effect=
                    lambda _project, _output: actual_seed(HERE.parents[2], _output)), \
                    mock.patch.object(RUNNER.tempfile, "mkdtemp", side_effect=allocate), \
                    mock.patch.object(RUNNER, "checked_output", return_value=
                        "commit-hash: 87e5904f5eb6398af6b22eac2802c78934260c48\n"), \
                    mock.patch.object(RUNNER, "command", command):
                if mode == "cancelled":
                    with mock.patch.object(RUNNER, "prepare_harness", side_effect=cancelled), \
                            RUNNER.interruption_handlers():
                        with self.assertRaises(RUNNER.RunnerInterrupted) as interrupted:
                            RUNNER.run_locked(args, HERE, project, upstream, output)
                        self.assertEqual(interrupted.exception.signum, signal.SIGTERM)
                else:
                    with self.assertRaisesRegex(SystemExit, expected_error[mode]):
                        RUNNER.run_locked(args, HERE, project, upstream, output)
                self.assertEqual(command.call_count, 2 if mode == "build" else
                                 1 if mode == "normalization" else 0)
            record = json.loads((output / "fixed-root.json").read_text())
            self.assertTrue(record.get("contents_removed"), record)
            self.assertTrue(record["retained_empty_root"])
            self.assertFalse(record["removed_after_run"])
            self.assertTrue(record["named_root_identity_matches"])
            self.assertEqual(list(fixed.iterdir()), [])

    def test_normal_cleanup_uses_pinned_fd_and_preserves_symlink_target(self):
        with tempfile.TemporaryDirectory(prefix="a01-fixed-cleanup-") as temporary:
            output = Path(temporary)
            outside = output / "outside"
            outside.mkdir()
            (outside / "keep").write_bytes(b"foreign payload")
            with RUNNER.owned_fixed_root(output) as fixed:
                (fixed / "nested").mkdir()
                (fixed / "nested/owned").write_bytes(b"owned payload")
                (fixed / "external-link").symlink_to(outside, target_is_directory=True)
                identity = fixed.stat()
            try:
                self.assertEqual(list(fixed.iterdir()), [])
                self.assertEqual((fixed.stat().st_dev, fixed.stat().st_ino),
                                 (identity.st_dev, identity.st_ino))
                self.assertEqual((outside / "keep").read_bytes(), b"foreign payload")
                record = json.loads((output / "fixed-root.json").read_text())
                self.assertTrue(record["contents_removed"])
                self.assertFalse(record["foreign_replacement_preserved"])
            finally:
                fixed.rmdir()  # Test-owned fixture teardown, after the production assertion.

    def test_replacement_before_fd_custody_is_rejected_without_cleanup(self):
        with tempfile.TemporaryDirectory(prefix="a01-fixed-cleanup-") as temporary:
            output = Path(temporary)
            moved = output / "moved-original"
            actual_open = RUNNER.os.open
            fixed_path = []
            def swap_before_open(path, flags, *args, **kwargs):
                fixed = Path(path)
                if fixed.name.startswith("a01oi-"):
                    fixed_path.append(fixed)
                    fixed.rename(moved)
                    fixed.mkdir()
                    (fixed / "keep").write_bytes(b"foreign replacement")
                return actual_open(path, flags, *args, **kwargs)
            with mock.patch.object(RUNNER.os, "open", side_effect=swap_before_open):
                with self.assertRaisesRegex(ValueError, "before FD custody"):
                    with RUNNER.owned_fixed_root(output):
                        self.fail("foreign replacement was yielded to the runner")
            try:
                self.assertEqual((fixed_path[0] / "keep").read_bytes(), b"foreign replacement")
                self.assertTrue(moved.is_dir())
            finally:
                (fixed_path[0] / "keep").unlink()
                fixed_path[0].rmdir()

    def test_replaced_directory_is_preserved_while_original_fd_is_cleared(self):
        self.replacement(False)

    def test_replaced_symlink_is_preserved_while_original_fd_is_cleared(self):
        self.replacement(True)

    def replacement(self, symlink):
        with tempfile.TemporaryDirectory(prefix="a01-fixed-cleanup-") as temporary:
            output = Path(temporary)
            outside, moved = output / "outside", output / "moved-original"
            outside.mkdir()
            (outside / "keep").write_bytes(b"foreign payload")
            with RUNNER.owned_fixed_root(output) as fixed:
                (fixed / "nested").mkdir()
                (fixed / "nested/owned").write_bytes(b"owned payload")
                fixed.rename(moved)
                if symlink:
                    fixed.symlink_to(outside, target_is_directory=True)
                else:
                    fixed.mkdir()
                    (fixed / "keep").write_bytes(b"foreign replacement")
            try:
                self.assertEqual(list(moved.iterdir()), [])
                self.assertEqual((outside / "keep").read_bytes(), b"foreign payload")
                if symlink:
                    self.assertTrue(fixed.is_symlink())
                else:
                    self.assertEqual((fixed / "keep").read_bytes(), b"foreign replacement")
                record = json.loads((output / "fixed-root.json").read_text())
                self.assertTrue(record["contents_removed"])
                self.assertFalse(record["named_root_identity_matches"])
                self.assertTrue(record["foreign_replacement_preserved"])
            finally:
                if fixed.is_symlink():
                    fixed.unlink()
                else:
                    (fixed / "keep").unlink()
                    fixed.rmdir()


if __name__ == "__main__":
    unittest.main(verbosity=2)
