#!/usr/bin/env python3
"""Real advisory-lock checks; mocked Cargo commands never qualify a build."""
from contextlib import ExitStack, redirect_stderr
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import prepare_inputs as preparation


class TargetCacheTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.roots = {name: self.root / name for name in ("desktop", "hepta")}
        self.original = self.root / "failed-01/original-target"
        self.observer = self.root / "failed-01/observer-target"
        for path in (*self.roots.values(), self.original, self.observer, self.root / "kernel-inputs"):
            path.mkdir(parents=True, exist_ok=True)
        self.out = self.root / "new-02"
        self.args = SimpleNamespace(original_target_cache=self.original, observer_target_cache=self.observer,
                                    kernel=self.root / "kernel-inputs/kernel.elf", fetch_dependencies=False)

    def selected(self):
        return preparation.cargo_targets(self.args, self.roots, self.out)

    def test_default_targets_remain_private_to_new_output(self):
        self.args.original_target_cache = self.args.observer_target_cache = None
        paths, record = self.selected()
        self.assertEqual(paths, {name: self.out / (name + "-target") for name in ("original", "observer")})
        self.assertFalse(record["cache_reused"])
        self.assertFalse(record["cold_build_claimed"])
        self.assertFalse(self.out.exists())

    def test_cache_choice_records_real_identity_without_authenticating_contents(self):
        paths, record = self.selected()
        self.assertEqual(paths["original"], self.original)
        self.assertTrue(record["cache_reused"])
        self.assertFalse(record["cold_build_claimed"])
        for name, path in paths.items():
            self.assertEqual(record["targets"][name]["inode"], path.stat().st_ino)
            self.assertFalse(record["targets"][name]["contents_authenticated"])

    def test_pair_missing_symlink_and_noncanonical_cache_are_rejected(self):
        self.args.observer_target_cache = None
        with self.assertRaisesRegex(ValueError, "together"):
            self.selected()
        self.args.observer_target_cache = self.observer
        alias = self.root / "alias"
        alias.symlink_to(self.original, target_is_directory=True)
        for path in (alias, self.original / "missing", self.original / "../original-target"):
            self.args.original_target_cache = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.selected()

    def test_same_nested_source_output_and_kernel_cache_are_rejected(self):
        nested = self.observer / "nested"
        nested.mkdir()
        for path in (self.observer, nested, self.roots["desktop"], self.root / "kernel-inputs", self.root):
            self.args.original_target_cache = path
            with self.subTest(path=path), self.assertRaises(ValueError):
                self.selected()
        self.args.original_target_cache = self.original
        with self.assertRaises(ValueError):
            preparation.cargo_targets(self.args, self.roots, self.original / "new-output")

    def test_real_other_process_refuses_held_cache_and_reacquires_after_close(self):
        paths, record = self.selected()
        program = (
            "from pathlib import Path; import sys; import prepare_inputs as p; "
            "path=Path(sys.argv[1]); s=path.stat(); "
            "r={'device':s.st_dev,'inode':s.st_ino}; "
            "lease=p.target_cache_lease(path,r); lease.__enter__(); lease.__exit__(None,None,None)"
        )
        def other():
            return subprocess.run([sys.executable, "-B", "-c", program, str(paths["original"])],
                                  cwd=preparation.HERE, capture_output=True, timeout=5, check=False)
        with preparation.target_cache_lease(paths["original"], record["targets"]["original"]):
            refused = other()
            self.assertNotEqual(refused.returncode, 0)
            self.assertIn(b"target cache is already leased", refused.stderr)
        accepted = other()
        self.assertEqual(accepted.returncode, 0, accepted.stderr.decode())

    def test_failed_second_lease_releases_first_and_preserves_prior_evidence(self):
        paths, record = self.selected()
        prior = self.root / "failed-01/preparation-result.json"
        prior.write_bytes(b'{"built":false,"error":"command_deadline_exceeded"}\n')
        before = prior.read_bytes()
        with preparation.target_cache_lease(paths["observer"], record["targets"]["observer"]):
            with self.assertRaisesRegex(ValueError, "already leased"):
                with ExitStack() as stack:
                    for name in ("original", "observer"):
                        stack.enter_context(preparation.target_cache_lease(paths[name], record["targets"][name]))
            with preparation.target_cache_lease(paths["original"], record["targets"]["original"]):
                pass
        self.assertEqual(prior.read_bytes(), before)

    def test_exception_releases_both_real_leases(self):
        paths, record = self.selected()
        with self.assertRaisesRegex(RuntimeError, "bounded build failed"):
            with ExitStack() as stack:
                for name in paths:
                    stack.enter_context(preparation.target_cache_lease(paths[name], record["targets"][name]))
                raise RuntimeError("bounded build failed")
        for name in paths:
            with preparation.target_cache_lease(paths[name], record["targets"][name]):
                pass

    def test_symlink_or_directory_lease_file_is_rejected_without_changing_target(self):
        paths, record = self.selected()
        target = self.root / "unchanged"
        target.write_bytes(b"unchanged")
        lock = self.original / ".hepta-native-userspace.lock"
        lock.symlink_to(target)
        with self.assertRaises(OSError):
            with preparation.target_cache_lease(paths["original"], record["targets"]["original"]):
                self.fail("unexpected lease")
        self.assertEqual(target.read_bytes(), b"unchanged")
        lock.unlink()
        lock.mkdir()
        with self.assertRaises(OSError):
            with preparation.target_cache_lease(paths["original"], record["targets"]["original"]):
                self.fail("unexpected lease")

    def test_changed_cache_inode_is_rejected(self):
        paths, record = self.selected()
        self.original.rename(self.original.with_name("old-target"))
        self.original.mkdir()
        with self.assertRaisesRegex(ValueError, "identity changed"):
            with preparation.target_cache_lease(paths["original"], record["targets"]["original"]):
                self.fail("unexpected lease")

    def test_replaced_lease_file_is_detected_before_command_or_freeze(self):
        paths, record = self.selected()
        with ExitStack() as stack:
            for name in paths:
                stack.enter_context(preparation.target_cache_lease(paths[name], record["targets"][name]))
            preparation.verify_target_caches(paths, record)
            lock = self.original / ".hepta-native-userspace.lock"
            lock.unlink()
            lock.write_bytes(b"replacement")
            with self.assertRaisesRegex(ValueError, "lease identity changed"):
                preparation.verify_target_caches(paths, record)

    def test_cache_flags_require_execute_and_both_paths(self):
        common = ["--desktop-source", str(self.roots["desktop"]), "--hepta-source", str(self.roots["hepta"]),
                  "--kernel", str(self.args.kernel), "--kernel-receipt", "/unused",
                  "--expected-kernel-receipt-sha256", "a" * 64]
        for flags in (["--original-target-cache", str(self.original)],
                      ["--original-target-cache", str(self.original), "--observer-target-cache", str(self.observer)],
                      ["--execute", "--original-target-cache", str(self.original)]):
            with self.subTest(flags=flags), self.assertRaises(SystemExit), \
                 mock.patch.object(preparation, "verify_sources", side_effect=AssertionError("unexpected source access")):
                preparation.main([*common, *flags])

    def test_cache_preserves_original_agentd_command_and_3600_second_deadline(self):
        paths, record = self.selected()
        report = {"steps": [], "cargo_targets": record,
                  "dependency_artifacts": preparation.dependency_artifacts.selected(self.args)}
        calls = []
        class GateError(Exception):
            pass
        def bounded(argv, cwd, env, log, timeout):
            calls.append((argv, cwd, env, log, timeout))
            if len(calls) == 2:
                raise GateError("controlled unit stop, not a build")
        helper = SimpleNamespace(GateError=GateError, prepare_runner=lambda *args: {}, bounded_command=bounded)
        with ExitStack() as stack, mock.patch.object(preparation, "original_helper", return_value=helper), \
             self.assertRaisesRegex(ValueError, "controlled unit stop"):
            for name in paths:
                stack.enter_context(preparation.target_cache_lease(paths[name], record["targets"][name]))
            preparation.build_userspace(self.args, self.roots, self.out, report, [], {},
                                        {"CARGO_INCREMENTAL": "0"}, {"cargo": {"path": "/fixed/cargo"}}, paths)
        self.assertEqual(calls[1][0], ["/fixed/cargo", "build", "--locked", "--offline", "--profile", "dev-small",
                                       "--no-default-features", "-p", "codex-hepta-agentd", "--bin", "codex-hepta-agentd", "-j1"])
        self.assertEqual([call[4] for call in calls], [3600, 3600])
        self.assertEqual([call[2]["CARGO_TARGET_DIR"] for call in calls], [str(self.observer), str(self.original)])
        self.assertEqual([step["command_timeout_seconds"] for step in report["steps"]], [3600, 3600])
        self.assertEqual(report["steps"][1]["cargo_target_dir"], str(self.original))

    def test_failed_step_records_failure_and_only_a_bounded_raw_log_tail(self):
        paths, record = self.selected()
        report = {"steps": [], "cargo_targets": record}
        self.out.mkdir()
        class GateError(Exception):
            pass
        def bounded(argv, cwd, environment, log, timeout):
            log.write_bytes(b"old diagnostics\n" + b"x" * 20000 + b"\nactual Cargo failure\n")
            raise GateError("command_failed_exit_101")
        helper = SimpleNamespace(GateError=GateError, prepare_runner=lambda *args: {}, bounded_command=bounded)
        diagnostics = io.StringIO()
        with ExitStack() as stack, mock.patch.object(preparation, "original_helper", return_value=helper), \
             redirect_stderr(diagnostics), self.assertRaisesRegex(ValueError, "command_failed_exit_101"):
            for name in paths:
                stack.enter_context(preparation.target_cache_lease(paths[name], record["targets"][name]))
            preparation.build_userspace(self.args, self.roots, self.out, report, [], {}, {},
                                        {"cargo": {"path": "/fixed/cargo"}}, paths)
        self.assertEqual(report["steps"][0]["status"], "failed")
        self.assertEqual(report["steps"][0]["log"], "observer.log")
        self.assertIn("command_failed_exit_101", report["steps"][0]["error"])
        self.assertNotIn("old diagnostics", diagnostics.getvalue())
        self.assertIn("actual Cargo failure", diagnostics.getvalue())
        self.assertLessEqual(len(diagnostics.getvalue()), 16 * 1024 + 1)
        self.assertTrue((self.out / "observer.log").read_bytes().startswith(b"old diagnostics\n"))
        self.assertFalse((self.out / "input-manifest.json").exists())

    def test_synthetic_success_receipt_retains_actual_command_cache_and_deadline_contract(self):
        paths, record = self.selected()
        report = {"steps": [], "cargo_targets": record,
                  "dependency_artifacts": preparation.dependency_artifacts.selected(self.args)}
        self.out.mkdir()
        self.args.kernel.write_bytes(b"unit-only kernel identity, never executed")
        self.args.kernel_receipt = self.root / "unused-kernel-receipt"
        self.args.expected_kernel_receipt_sha256 = "a" * 64
        class GateError(Exception):
            pass
        def prepare_runner(source, fixture):
            fixture.mkdir()
            (fixture / "Cargo.lock").write_text("unit-only lock")
            return {"unit_test_omission": True}
        def bounded(argv, cwd, environment, log, timeout):
            self.assertEqual(timeout, 3600)
            target = Path(environment["CARGO_TARGET_DIR"])
            if "hepta-observe" in argv:
                binary = target / "debug/hepta-observe"
            elif "codex-hepta-agentd" in argv:
                binary = target / "dev-small/codex-hepta-agentd"
            elif "build" in argv:
                binary = target / "dev-small/hepta-original-observer-probe"
            else:
                return
            binary.parent.mkdir(parents=True, exist_ok=True)
            binary.write_bytes(b"unit-only binary identity, never executed")
        helper = SimpleNamespace(GateError=GateError, prepare_runner=prepare_runner, bounded_command=bounded,
                                 verify_runner_lock=lambda *args: None)
        with ExitStack() as stack, mock.patch.object(preparation, "original_helper", return_value=helper), \
             mock.patch.object(preparation, "verify_sources", return_value=[]), \
             mock.patch.object(preparation, "kernel_receipt", return_value={}), \
             mock.patch.object(preparation.gate, "frozen_inputs"):
            for name in paths:
                stack.enter_context(preparation.target_cache_lease(paths[name], record["targets"][name]))
            preparation.build_userspace(self.args, self.roots, self.out, report, [], {}, {},
                                        {"cargo": {"path": "/fixed/cargo"}}, paths)
        receipt = json.loads((self.out / "userspace-build.json").read_text())
        self.assertTrue(receipt["cargo_targets"]["cache_reused"])
        self.assertFalse(receipt["cargo_targets"]["cold_build_claimed"])
        self.assertEqual(receipt["cargo_targets"], record)
        self.assertEqual(receipt["dependency_artifacts"], report["dependency_artifacts"])
        self.assertEqual(receipt["command_records"], report["steps"])
        self.assertEqual(receipt["command_timeout_seconds"], 3600)
        self.assertEqual(len(receipt["commands"]), 5)
        self.assertTrue(all(step["status"] == "passed" for step in receipt["command_records"]))
        self.assertFalse(receipt["runtime_executed"])


if __name__ == "__main__":
    unittest.main()
