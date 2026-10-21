#!/usr/bin/env python3
"""Deterministic host-only case-directory custody races; no compiler or VM."""
from contextlib import contextmanager
import errno
import importlib.util
import json
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
SOURCE = Path(os.environ.get("A01_CASE_CLEANUP_RUNNER_SOURCE", str(HERE / "run.py")))
SPEC = importlib.util.spec_from_file_location("a01_case_cleanup", SOURCE)
RUNNER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUNNER)


class CaseCleanupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="a01-case-cleanup-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.output = self.root / "output"
        self.output.mkdir()
        self.fixed = self.root / "fixed"
        self.outside = self.root / "outside"
        (self.outside / "run_command").mkdir(parents=True)
        (self.outside / "run_command/keep").write_bytes(b"foreign payload")

    def allocate(self, **_kwargs):
        self.fixed.mkdir(mode=0o700)
        return str(self.fixed)

    @contextmanager
    def owned(self):
        custody = {}
        with mock.patch.object(RUNNER.tempfile, "mkdtemp", side_effect=self.allocate):
            with RUNNER.owned_fixed_root(self.output, custody=custody) as fixed:
                yield fixed, custody
        with self.assertRaises(OSError):
            os.fstat(custody["descriptor"])

    def make_case(self, fixed):
        path = fixed / "parent/run_command"
        (path / "nested").mkdir(parents=True)
        (path / "nested/owned").write_bytes(b"owned payload")
        return path

    def replace_case(self, path):
        moved = self.root / "moved-case"
        path.rename(moved)
        path.mkdir()
        (path / "keep").write_bytes(b"foreign replacement")
        return moved

    def preserved(self):
        record = json.loads((self.output / "fixed-root.json").read_text())
        self.assertFalse(record["contents_removed"], record)
        self.assertTrue(record["contents_preserved_for_recovery"], record)
        self.assertFalse(record["retained_empty_root"], record)
        self.assertTrue(record["preservation_reasons"], record)
        self.assertEqual((self.outside / "run_command/keep").read_bytes(), b"foreign payload")

    def test_normal_cleanup_keeps_foreign_symlink_target_and_releases_reusable_name(self):
        with self.owned() as (fixed, custody):
            for _ in range(2):
                path = self.make_case(fixed)
                (path / "external").symlink_to(self.outside, target_is_directory=True)
                before = len(os.listdir("/proc/self/fd"))
                result = RUNNER.cleanup_case_directory(path, fixed, custody)
                self.assertTrue(result["passed"], result)
                self.assertTrue(result["removed"], result)
                self.assertFalse(path.exists())
                self.assertEqual(list(Path(result["custody_path"]).iterdir()), [])
                self.assertEqual(len(os.listdir("/proc/self/fd")), before)
        record = json.loads((self.output / "fixed-root.json").read_text())
        self.assertTrue(record["case_contents_removed"])
        self.assertFalse(record["contents_removed"])
        self.assertFalse(record["retained_empty_root"])
        self.assertEqual(record["retained_directory_count"], 3)
        self.assertFalse(any(p.is_file() for p in fixed.rglob("*")))
        self.assertEqual((self.outside / "run_command/keep").read_bytes(), b"foreign payload")

    def test_absent_leaf_and_absent_parent_are_not_failures(self):
        with self.owned() as (fixed, custody):
            (fixed / "parent").mkdir()
            for path in (fixed / "parent/run_command", fixed / "missing/run_command"):
                result = RUNNER.cleanup_case_directory(path, fixed, custody)
                self.assertTrue(result["passed"], result)
                self.assertFalse(result["removed"], result)
                self.assertEqual(result["reason"], "absent")

    def test_case_replacement_between_stat_and_open_is_preserved(self):
        with self.owned() as (fixed, custody):
            path = self.make_case(fixed)
            actual_open = RUNNER.os.open
            fired = []
            def swap(name, flags, *args, **kwargs):
                if name == "run_command" and not fired:
                    fired.append(True)
                    self.replace_case(path)
                return actual_open(name, flags, *args, **kwargs)
            before = len(os.listdir("/proc/self/fd"))
            with mock.patch.object(RUNNER.os, "open", side_effect=swap):
                result = RUNNER.cleanup_case_directory(path, fixed, custody)
            self.assertTrue(fired)
            self.assertFalse(result["passed"], result)
            self.assertEqual(len(os.listdir("/proc/self/fd")), before)
        self.assertEqual((path / "keep").read_bytes(), b"foreign replacement")
        self.assertEqual((self.root / "moved-case/nested/owned").read_bytes(), b"owned payload")
        self.preserved()

    def capture_replacement(self, restore_failure=None):
        with self.owned() as (fixed, custody):
            path = self.make_case(fixed)
            actual_rename = RUNNER.rename_no_replace
            calls = []
            def swap(source, destination, source_fd, destination_fd):
                calls.append(source)
                if len(calls) == 1:
                    self.replace_case(path)
                elif restore_failure == "conflict":
                    path.mkdir()
                    (path / "newer").write_bytes(b"newer foreign entry")
                elif restore_failure == "unavailable":
                    raise OSError(errno.ENOSYS, "test renameat2 unavailable")
                return actual_rename(source, destination, source_fd, destination_fd)
            with mock.patch.object(RUNNER, "rename_no_replace", side_effect=swap):
                result = RUNNER.cleanup_case_directory(path, fixed, custody)
            self.assertFalse(result["passed"], result)
            self.assertEqual(len(calls), 2)
        self.assertEqual((self.root / "moved-case/nested/owned").read_bytes(), b"owned payload")
        self.preserved()
        return path, result

    def test_replacement_before_capture_is_restored_without_deletion(self):
        path, result = self.capture_replacement()
        self.assertTrue(result["foreign_restored"], result)
        self.assertEqual((path / "keep").read_bytes(), b"foreign replacement")

    def test_restore_conflict_retains_both_foreign_directories(self):
        path, result = self.capture_replacement("conflict")
        self.assertIn("restore_error", result)
        self.assertEqual((path / "newer").read_bytes(), b"newer foreign entry")
        self.assertEqual((Path(result["retained_path"]) / "keep").read_bytes(), b"foreign replacement")

    def test_unavailable_noreplace_never_falls_back_to_overwrite(self):
        path, result = self.capture_replacement("unavailable")
        self.assertIn("restore_error", result)
        self.assertFalse(path.exists())
        self.assertEqual((Path(result["retained_path"]) / "keep").read_bytes(), b"foreign replacement")

    def test_unexpected_regular_file_survives_helper_and_outer_finalizer(self):
        with self.owned() as (fixed, custody):
            path = fixed / "run_command"
            path.write_bytes(b"unexpected regular file")
            result = RUNNER.cleanup_case_directory(path, fixed, custody)
            self.assertFalse(result["passed"], result)
        self.assertEqual(path.read_bytes(), b"unexpected regular file")
        self.preserved()

    def test_capture_unavailable_preserves_owned_directory_and_fails(self):
        with self.owned() as (fixed, custody):
            path = self.make_case(fixed)
            with mock.patch.object(RUNNER, "rename_no_replace",
                                   side_effect=OSError(errno.ENOSYS, "unavailable")):
                result = RUNNER.cleanup_case_directory(path, fixed, custody)
            self.assertFalse(result["passed"], result)
        self.assertEqual((path / "nested/owned").read_bytes(), b"owned payload")
        self.preserved()

    def test_parent_symlink_before_open_is_never_followed(self):
        with self.owned() as (fixed, custody):
            (fixed / "parent").symlink_to(self.outside, target_is_directory=True)
            result = RUNNER.cleanup_case_directory(fixed / "parent/run_command", fixed, custody)
            self.assertFalse(result["passed"], result)
        self.assertTrue((fixed / "parent").is_symlink())
        self.preserved()

    def test_parent_replacement_between_stat_and_open_is_rejected(self):
        with self.owned() as (fixed, custody):
            path = self.make_case(fixed)
            actual_open = RUNNER.os.open
            fired = []
            def swap(name, flags, *args, **kwargs):
                if name == "parent" and not fired:
                    fired.append(True)
                    path.parent.rename(self.root / "moved-parent")
                    path.parent.symlink_to(self.outside, target_is_directory=True)
                return actual_open(name, flags, *args, **kwargs)
            with mock.patch.object(RUNNER.os, "open", side_effect=swap):
                result = RUNNER.cleanup_case_directory(path, fixed, custody)
            self.assertTrue(fired)
            self.assertFalse(result["passed"], result)
        self.assertEqual((self.root / "moved-parent/run_command/nested/owned").read_bytes(), b"owned payload")
        self.preserved()

    def test_parent_symlink_after_open_cannot_redirect_capture_or_deletion(self):
        with self.owned() as (fixed, custody):
            path = self.make_case(fixed)
            actual_rename = RUNNER.rename_no_replace
            fired = []
            def swap(source, destination, source_fd, destination_fd):
                if not fired:
                    fired.append(True)
                    path.parent.rename(self.root / "moved-parent")
                    path.parent.symlink_to(self.outside, target_is_directory=True)
                return actual_rename(source, destination, source_fd, destination_fd)
            with mock.patch.object(RUNNER, "rename_no_replace", side_effect=swap):
                result = RUNNER.cleanup_case_directory(path, fixed, custody)
            self.assertFalse(result["passed"], result)
            self.assertEqual(list(Path(result["custody_path"]).iterdir()), [])
        self.assertTrue(path.parent.is_symlink())
        self.preserved()

    def test_root_replacement_cannot_redirect_deletion(self):
        with self.owned() as (fixed, custody):
            path = self.make_case(fixed)
            fixed.rename(self.root / "moved-fixed")
            fixed.symlink_to(self.outside, target_is_directory=True)
            result = RUNNER.cleanup_case_directory(path, fixed, custody)
            self.assertFalse(result["passed"], result)
        self.assertTrue(fixed.is_symlink())
        self.assertEqual((self.root / "moved-fixed/parent/run_command/nested/owned").read_bytes(),
                         b"owned payload")
        self.preserved()

    def replacement_before_clear(self, target):
        with self.owned() as (fixed, custody):
            path = self.make_case(fixed)
            actual_clear = RUNNER.clear_owned_directory
            fired = []
            def swap(descriptor):
                if not fired:
                    fired.append(True)
                    if target == "root":
                        fixed.rename(self.root / "moved-fixed")
                        fixed.mkdir()
                        (fixed / "keep").write_bytes(b"foreign root")
                    elif target == "case":
                        path.mkdir()
                        (path / "keep").write_bytes(b"foreign case")
                    else:
                        candidate = next(fixed.glob(".a01-case-custody-*"))
                        candidate.rename(self.root / "moved-custody")
                        candidate.mkdir()
                        (candidate / "keep").write_bytes(b"foreign custody")
                return actual_clear(descriptor)
            with mock.patch.object(RUNNER, "clear_owned_directory", side_effect=swap):
                result = RUNNER.cleanup_case_directory(path, fixed, custody)
            self.assertEqual(len(fired), 1)
            self.assertFalse(result["passed"], result)
        self.preserved()
        return path, result

    def test_root_replacement_after_capture_keeps_foreign_root(self):
        self.replacement_before_clear("root")
        self.assertEqual((self.fixed / "keep").read_bytes(), b"foreign root")

    def test_new_public_case_after_capture_is_preserved_through_outer_cleanup(self):
        path, _ = self.replacement_before_clear("case")
        self.assertEqual((path / "keep").read_bytes(), b"foreign case")

    def test_custody_replacement_cannot_redirect_fd_clear(self):
        _, result = self.replacement_before_clear("custody")
        self.assertEqual((Path(result["custody_path"]) / "keep").read_bytes(), b"foreign custody")
        self.assertEqual(list((self.root / "moved-custody").iterdir()), [])

    def test_clear_failure_preserves_recovery_content_and_fails(self):
        with self.owned() as (fixed, custody):
            path = self.make_case(fixed)
            with mock.patch.object(RUNNER, "clear_owned_directory",
                                   side_effect=PermissionError("fixture refusal")):
                result = RUNNER.cleanup_case_directory(path, fixed, custody)
            self.assertFalse(result["passed"], result)
        self.assertEqual((Path(result["custody_path"]) / "nested/owned").read_bytes(), b"owned payload")
        self.preserved()

    def test_interrupt_preserves_content_closes_fds_and_keeps_failure(self):
        custody = {}
        with mock.patch.object(RUNNER.tempfile, "mkdtemp", side_effect=self.allocate):
            with self.assertRaises(KeyboardInterrupt):
                with RUNNER.owned_fixed_root(self.output, custody=custody) as fixed:
                    path = self.make_case(fixed)
                    with mock.patch.object(RUNNER, "clear_owned_directory", side_effect=KeyboardInterrupt):
                        RUNNER.cleanup_case_directory(path, fixed, custody)
        self.preserved()
        with self.assertRaises(OSError):
            os.fstat(custody["descriptor"])
        candidate = next(self.fixed.glob(".a01-case-custody-*"))
        self.assertEqual((candidate / "nested/owned").read_bytes(), b"owned payload")

    def test_replacement_after_final_absence_check_survives_outer_finalizer(self):
        with self.owned() as (fixed, custody):
            path = self.make_case(fixed)
            actual_stat = RUNNER.os.stat
            fired = []
            def late_replace(name, *args, **kwargs):
                try:
                    return actual_stat(name, *args, **kwargs)
                except FileNotFoundError:
                    if name == "run_command" and kwargs.get("dir_fd") is not None and not fired:
                        fired.append(True)
                        path.mkdir()
                        (path / "keep").write_bytes(b"foreign entry after final absence")
                    raise
            with mock.patch.object(RUNNER.os, "stat", side_effect=late_replace):
                result = RUNNER.cleanup_case_directory(path, fixed, custody)
            self.assertTrue(result["passed"], result)
            self.assertTrue(fired)
            self.assertFalse(custody["preserve_contents"])
        self.assertEqual((path / "keep").read_bytes(), b"foreign entry after final absence")
        self.assertTrue(custody["preserve_contents"])
        self.preserved()

    def test_unknown_entry_after_case_cleanup_is_preserved_and_fails_inventory(self):
        with self.owned() as (fixed, custody):
            result = RUNNER.cleanup_case_directory(self.make_case(fixed), fixed, custody)
            self.assertTrue(result["passed"], result)
            (fixed / "foreign").mkdir()
            (fixed / "foreign/keep").write_bytes(b"unknown root entry")
        self.assertEqual((fixed / "foreign/keep").read_bytes(), b"unknown root entry")
        self.assertTrue(custody["preserve_contents"])
        self.preserved()

    def test_replaced_empty_custody_is_preserved_and_fails_inventory(self):
        with self.owned() as (fixed, custody):
            result = RUNNER.cleanup_case_directory(self.make_case(fixed), fixed, custody)
            self.assertTrue(result["passed"], result)
            captured = Path(result["custody_path"])
            captured.rename(self.root / "original-empty-custody")
            captured.mkdir()
            (captured / "keep").write_bytes(b"foreign custody after cleanup")
        self.assertEqual((captured / "keep").read_bytes(), b"foreign custody after cleanup")
        self.assertTrue(custody["preserve_contents"])
        self.preserved()

    def exercise_public_runner(self, mode):
        project = self.root / "project"
        here = project / "support/build/osdk-integration"
        here.mkdir(parents=True)
        (here / "run.py").write_bytes(SOURCE.read_bytes())
        upstream = project / "kernel/asterinas"
        harness_root = upstream / "osdk"
        for directory in (harness_root / "src", harness_root / "tests",
                          upstream / "ostd/libs/align_ext"):
            directory.mkdir(parents=True)
        (upstream / "Cargo.lock").write_bytes(b"host-only lock fixture")
        harness = self.root / "integration-fixture"
        harness.write_bytes(b"never executed")
        rustup = self.root / "rustup"
        tools = rustup / "toolchains" / (RUNNER.TOOLCHAIN + "-x86_64-unknown-linux-gnu") / "bin"
        tools.mkdir(parents=True)
        for name in ("cargo", "rustc"):
            (tools / name).write_bytes(b"never executed")
        case = "commands::new::create_kernel_in_workspace"
        initial = self.fixed / "kernel_workspace"
        available = [case] + [f"host::fixture_{n}" for n in range(21)]
        args = SimpleNamespace(coverage_gdb=False, local_tcp=False,
                               upstream_coverage_lifecycle=False, target_dir=None,
                               case=[case, "host::fixture_0"], case_timeout=1)
        def checked(argv, cwd, env, output, timeout=30):
            if argv[-1] == "--list":
                value = "\n".join(name + ": test" for name in available)
            elif "-Vv" in argv and Path(argv[0]).name == "rustc":
                value = "commit-hash: 87e5904f5eb6398af6b22eac2802c78934260c48\n"
            else:
                value = "host fixture\n"
            output.write_text(value)
            return value
        def prepare(*_args, **kwargs):
            if mode == "occupied":
                initial.mkdir()
                (initial / "keep").write_bytes(b"preexisting foreign entry")
            return harness_root, kwargs["fixed_root"]
        executed = []
        def command(argv, cwd, env, output, timeout):
            if output.name == "harness-build.log":
                (self.output / "target/debug/cargo-osdk").write_bytes(b"never executed")
                output.write_text(json.dumps({"reason": "compiler-artifact",
                    "executable": str(harness), "target": {"name": "integration"}}) + "\n")
            elif output.name == "harness.log":
                executed.append(tuple(argv))
                if mode == "unexpected":
                    initial.symlink_to(self.outside, target_is_directory=True)
                elif case in argv:
                    initial.mkdir()
                    (initial / "owned").write_bytes(b"owned payload")
                (Path(env["TMPDIR"]) / "owned-temporary").write_bytes(b"owned TMPDIR payload")
                output.write_text("1 passed; 0 failed;\n")
            else:
                output.write_text("host fixture\n")
            return {"raw_exit_code": 0, "duration_seconds": 0}
        seed = self.root / "seed"
        seed.write_bytes(b"host seed fixture")
        actual_cleanup = RUNNER.cleanup_case_directory
        def cleanup(*args):
            result = actual_cleanup(*args)
            if mode == "late" and args[0] == initial:
                initial.mkdir()
                (initial / "keep").write_bytes(b"late foreign public case")
            return result
        with mock.patch.object(RUNNER, "cleanup_case_directory", side_effect=cleanup), \
                mock.patch.dict(os.environ, {"RUSTUP_HOME": str(rustup)}), \
                mock.patch.object(RUNNER.tempfile, "mkdtemp", side_effect=self.allocate), \
                mock.patch.object(RUNNER, "prepare_root_seed", return_value=(seed, {"sha256": "fixture"})), \
                mock.patch.object(RUNNER, "prepare_harness", side_effect=prepare), \
                mock.patch.object(RUNNER, "checked_output", side_effect=checked), \
                mock.patch.object(RUNNER, "command", side_effect=command):
            status = RUNNER.run_locked(args, here, project, upstream, self.output)
        self.assertEqual(status, 0 if mode == "normal" else 1)
        report = json.loads((self.output / "result.json").read_text())
        self.assertEqual(report["runner_exit_code"], status)
        self.assertEqual(report["cleanup_blocked"], mode != "normal", report)
        self.assertEqual(report["selected_cases"], 2)
        completed = 2 if mode in ("normal", "late") else 1
        self.assertEqual(len(report["cases"]), completed)
        self.assertEqual(report["completed_cases"], completed)
        self.assertEqual(report["not_run_cases"], 2 - completed)
        self.assertEqual(report["passed"], 2 if mode in ("normal", "late") else 0)
        self.assertEqual(len(executed), 0 if mode == "occupied" else completed)
        if mode != "normal":
            self.preserved()
        return initial, report

    def test_public_runner_clears_case_and_tmpdir_payloads_without_outer_recursion(self):
        initial, report = self.exercise_public_runner("normal")
        self.assertFalse(initial.exists())
        cleanup = report["fixed_root_cleanup"]
        self.assertTrue(cleanup["case_contents_removed"])
        self.assertEqual(cleanup["retained_directory_count"], 3)
        self.assertFalse(any(p.is_file() for p in self.fixed.rglob("*")))
        self.assertEqual([len(case["cleanup"]) for case in report["cases"]], [2, 1])

    def test_late_public_case_is_preserved_and_failure_reaches_aggregate(self):
        initial, report = self.exercise_public_runner("late")
        self.assertTrue(report["cleanup_blocked"])
        self.assertEqual(report["runner_exit_code"], 1)
        self.assertEqual((initial / "keep").read_bytes(), b"late foreign public case")

    def test_preexisting_case_is_blocked_and_survives_public_runner_finally(self):
        initial, report = self.exercise_public_runner("occupied")
        self.assertEqual(report["blocked"], 1)
        self.assertEqual((initial / "keep").read_bytes(), b"preexisting foreign entry")

    def test_unexpected_case_symlink_is_failed_and_survives_public_runner_finally(self):
        initial, report = self.exercise_public_runner("unexpected")
        self.assertEqual(report["failed"], 1)
        self.assertTrue(initial.is_symlink())
        self.assertFalse(report["cases"][0]["cleanup"][0]["passed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
