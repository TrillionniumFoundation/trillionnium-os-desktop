#!/usr/bin/env python3
"""Actual store-cache path and interprocess flock checks; no build is qualified."""
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

import prepare_inputs as preparation


class StoreTargetCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.source = self.root / "hepta"
        self.harness = self.root / "desktop"
        self.cache = self.root / "previous-attempt/target"
        self.out = self.root / "new-attempt"
        for path in (self.source, self.harness, self.cache):
            path.mkdir(parents=True)
        self.args = SimpleNamespace(target=self.cache)
        self.helpers = preparation.runtime_cache_helpers()

    def select(self):
        with mock.patch.object(preparation, "ROOT", self.harness):
            return preparation.cargo_target(self.args, self.source, self.out)

    def test_default_build_uses_private_new_target_without_a_reuse_claim(self):
        self.args.target = None
        target, record = self.select()
        self.assertEqual(target, self.out / "target")
        self.assertEqual(record["lease_policy"], "private-new-output")
        self.assertFalse(record["cache_reused"])
        preparation.verify_target_cache(target, record, None)
        self.assertFalse(self.out.exists())

    def test_existing_cache_records_real_identity_without_authenticating_contents(self):
        target, record = self.select()
        info = record["targets"]["store"]
        self.assertEqual(info["inode"], self.cache.stat().st_ino)
        self.assertFalse(info["contents_authenticated"])
        self.assertFalse(record["cold_build_claimed"])
        self.assertEqual(target, self.cache)
        self.assertTrue(record["cache_reused"])

    def test_missing_symlink_and_noncanonical_alias_are_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(self.cache, target_is_directory=True)
        for path in (self.cache / "absent", alias, self.cache / "../target"):
            self.args.target = path
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "existing canonical"):
                self.select()

    def test_source_harness_output_and_ancestor_overlap_are_rejected(self):
        self.out.mkdir()
        nested = self.source / "target"
        nested.mkdir()
        for path in (self.source, nested, self.harness, self.out, self.root):
            self.args.target = path
            with self.subTest(path=path), self.assertRaisesRegex(ValueError, "separate from"):
                self.select()
        self.args.target = self.cache
        self.out = self.cache / "new-output"
        with self.assertRaisesRegex(ValueError, "separate from"):
            self.select()

    def test_actual_other_process_cannot_lease_the_cache_until_release(self):
        target, record = self.select()
        code = (
            "from pathlib import Path; import sys; import prepare_inputs as p; "
            "path=Path(sys.argv[1]); s=path.stat(); "
            "r={'device':s.st_dev,'inode':s.st_ino}; "
            "lease=p.runtime_cache_helpers().target_cache_lease(path,r); "
            "lease.__enter__(); lease.__exit__(None,None,None)"
        )
        def other():
            return subprocess.run([sys.executable, "-B", "-c", code, str(target)],
                                  cwd=preparation.HERE, capture_output=True, timeout=10, check=False)
        with self.helpers.target_cache_lease(target, record["targets"]["store"]):
            preparation.verify_target_cache(target, record, self.helpers)
            blocked = other()
            self.assertNotEqual(blocked.returncode, 0)
            self.assertIn(b"target cache is already leased", blocked.stderr)
        released = other()
        self.assertEqual(released.returncode, 0, released.stderr.decode())

    def test_exception_releases_lease_and_preserves_prior_failed_evidence(self):
        target, record = self.select()
        prior = self.cache.parent / "build.json"
        prior.write_bytes(b'{"built":false,"error":"actual previous attempt"}\n')
        before = prior.read_bytes()
        with self.assertRaisesRegex(RuntimeError, "controlled failure"):
            with self.helpers.target_cache_lease(target, record["targets"]["store"]):
                raise RuntimeError("controlled failure")
        with self.helpers.target_cache_lease(target, record["targets"]["store"]):
            preparation.verify_target_cache(target, record, self.helpers)
        self.assertEqual(prior.read_bytes(), before)

    def test_changed_directory_or_lease_identity_is_rejected(self):
        target, record = self.select()
        target.rename(target.with_name("moved-target"))
        target.mkdir()
        with self.assertRaisesRegex(ValueError, "identity changed"):
            with self.helpers.target_cache_lease(target, record["targets"]["store"]):
                self.fail("changed target was leased")
        target, record = self.select()
        with self.helpers.target_cache_lease(target, record["targets"]["store"]):
            lock = target / ".hepta-native-userspace.lock"
            lock.unlink()
            lock.write_bytes(b"replacement")
            with self.assertRaisesRegex(ValueError, "identity changed"):
                preparation.verify_target_cache(target, record, self.helpers)

    def test_symlink_lease_file_is_not_followed(self):
        target, record = self.select()
        protected = self.root / "untouched"
        protected.write_bytes(b"retained")
        (target / ".hepta-native-userspace.lock").symlink_to(protected)
        with self.assertRaises(OSError):
            with self.helpers.target_cache_lease(target, record["targets"]["store"]):
                self.fail("symlink lease was followed")
        self.assertEqual(protected.read_bytes(), b"retained")

    def test_cache_flag_cannot_be_misread_as_a_readonly_preflight(self):
        with self.assertRaises(SystemExit), mock.patch.object(
            preparation, "verify_source", side_effect=AssertionError("unexpected source access")
        ):
            preparation.main(["--hepta-source", str(self.source), "--target", str(self.cache)])

    def test_offline_metadata_uses_the_prefetched_native_target_and_checks_original_lock(self):
        self.out.mkdir()
        runner = self.out / "runner"
        runner.mkdir()
        (runner / "Cargo.lock").write_bytes(b"controlled fixture lock, not build evidence")
        target, record = self.select()
        calls = []
        def bounded(command, cwd, environment, log, timeout):
            calls.append(command)
            if "build" in command:
                raise RuntimeError("controlled stop before compilation")
        report = {"commands": [], "cargo_targets": record}
        with self.helpers.target_cache_lease(target, record["targets"]["store"]), \
             mock.patch.object(preparation, "prepare_runner", return_value={}), \
             mock.patch.object(preparation.HELPER, "bounded_command", side_effect=bounded), \
             mock.patch.object(preparation, "verify_lock", return_value={}) as verify_lock, \
             self.assertRaisesRegex(RuntimeError, "controlled stop"):
            preparation.build_store(self.source, self.out, {}, report, target, {},
                                    {"cargo": {"path": "/fixed/cargo"}}, self.helpers)
        self.assertEqual(verify_lock.call_count, 2)
        for command in calls[:2]:
            self.assertEqual(command[command.index("--filter-platform") + 1], self.helpers.USERSPACE_TARGET)
            self.assertIn("--offline", command)
            self.assertNotIn("--no-deps", command)
        self.assertIn("--locked", calls[1])
        self.assertIn("--locked", calls[2])


if __name__ == "__main__":
    unittest.main()
