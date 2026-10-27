#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Fixed-source admission checks. These host tests do not execute a guest."""
import base64
import gzip
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_unix_stream_guest as historical
import run_unix_stream_receiving_guest as receiving


class ReceivingSourceProfile(unittest.TestCase):
    def actual(self):
        # Keep this historical receiving composition's original refusal check
        # on its own real f009 bytes as later Unix owners evolve.
        return self.historical()

    def historical(self):
        # Real f009 Git blobs keep the historical positive independent of the
        # current checkout. Decode in memory; never extract fixture paths.
        encoded = (HERE / "controls/receiving-force-v1-source.json.gz").read_bytes()
        self.assertEqual(hashlib.sha256(encoded).hexdigest(),
                         "78e24888c39e163cd9af33171f490f69b4e00421d839587fb4c604bc07b4fae3")
        fixture = json.loads(gzip.decompress(encoded))
        self.assertEqual(fixture["schema"], "asterinas.receiving-force-v1-historical-source.v1")
        self.assertEqual(fixture["source_head"], "f009818a2606111ad79773d473c5acbd8cab2720")
        self.assertEqual(fixture["source_tree"], "b077d2c955dc19c9f45fcf7971808d3f38f27f3f")
        expected = {path: (role, sha) for role, path, sha in receiving.OWNERS}
        self.assertEqual(len(fixture["files"]), 70)
        self.assertEqual({row["path"] for row in fixture["files"]}, set(expected))
        self.assertEqual(len({row["role"] for row in fixture["files"]}), 70)
        result = {"files": {}}
        for row in fixture["files"]:
            path = Path(row["path"])
            self.assertFalse(path.is_absolute())
            self.assertNotIn("..", path.parts)
            self.assertIn(row["mode"], ("100644", "100755"))
            data = base64.b64decode(row["content_base64"], validate=True)
            self.assertEqual(hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest(),
                             row["git_blob"], row["path"])
            actual = hashlib.sha256(data).hexdigest()
            self.assertEqual((row["role"], actual), expected[row["path"]])
            self.assertEqual(actual, row["sha256"])
            result["files"][row["path"]] = {"sha256": actual}
        return result

    def test_public_historical_profiles_and_original_checker_are_untouched(self):
        self.assertEqual(historical.SOURCE_PROFILES, ("legacy", "ipc-memory-v1"))
        self.assertIs(receiving.check_sources, receiving.engine.check_sources)
        self.assertEqual(receiving.engine.check_sources.__code__.co_filename,
                         str(HERE / "run_unix_stream_guest.py"))
        with self.assertRaises(ValueError):
            historical.required_sources("positive", receiving.PROFILE)
        for profile in historical.SOURCE_PROFILES:
            self.assertEqual(receiving.required_sources("positive", profile),
                             historical.required_sources("positive", profile))

    def test_engine_bytes_are_bound_before_private_import(self):
        original = (HERE / "run_unix_stream_guest.py").read_bytes()
        receiving.verify_engine(original)
        with self.assertRaises(ValueError):
            receiving.verify_engine(original + b"\n")

    def test_fixed_unique_real_owner_roles_and_paths(self):
        roles = [role for role, _, _ in receiving.OWNERS]
        paths = [path for _, path, _ in receiving.OWNERS]
        self.assertEqual(len(roles), 70)
        self.assertEqual(len(set(roles)), len(roles))
        self.assertEqual(len(set(paths)), len(paths))
        for role, path, sha in receiving.OWNERS:
            with self.subTest(role=role):
                self.assertFalse(Path(path).is_absolute())
                self.assertNotIn("..", Path(path).parts)
                self.assertRegex(sha, r"^[0-9a-f]{64}$")
                self.assertTrue((HERE.parents[2] / path).is_file())
                self.assertFalse((HERE.parents[2] / path).is_symlink())
        # Production owner boundaries must not disappear behind an IPC-only name.
        for name in ("sched.sched_class.administration", "sched.sched_class.affinity",
                     "sched.sched_class.request", "sched.sched_class.transfer",
                     "cgroup.root", "ipc.page-memory", "ostd.task.processor",
                     "syscall.sched_permissions", "inherit.process.clone"):
            self.assertIn(name, roles)

    def test_receiving_profile_accepts_bound_real_historical_composition(self):
        expected = receiving.required_sources("positive", receiving.PROFILE)
        self.assertEqual(receiving.check_sources(self.historical(), "positive", receiving.PROFILE), expected)
        self.assertEqual(set(expected), {path for _, path, _ in receiving.OWNERS})

    def test_every_missing_and_drifting_owner_is_refused(self):
        actual = self.historical()
        receiving.check_sources(actual, "positive", receiving.PROFILE)
        for role, path, _ in receiving.OWNERS:
            with self.subTest(role=role, change="missing"):
                changed = {"files": dict(actual["files"])}
                del changed["files"][path]
                with self.assertRaises(ValueError):
                    receiving.check_sources(changed, "positive", receiving.PROFILE)
            with self.subTest(role=role, change="drift"):
                changed = {"files": dict(actual["files"])}
                changed["files"][path] = {"sha256": "0" * 64}
                with self.assertRaises(ValueError):
                    receiving.check_sources(changed, "positive", receiving.PROFILE)

    def test_unknown_profile_and_historical_mutations_are_refused(self):
        with self.assertRaises(ValueError):
            receiving.required_sources("positive", "invented")
        for variant in ("race-fixed", "race-stale", "aux-zero-progress"):
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                receiving.required_sources(variant, receiving.PROFILE)

    def test_old_ipc_profile_honestly_refuses_this_composition(self):
        # The frozen M5 positive receipt is never rebadged as this new product.
        with self.assertRaisesRegex(ValueError, "cgroupfs/mod.rs"):
            historical.check_sources(self.actual(), "positive", "ipc-memory-v1")
        with self.assertRaises(ValueError):
            receiving.check_sources(self.actual(), "positive", "ipc-memory-v1")

    def test_all_original_ipc_owner_paths_remain_in_new_profile(self):
        new = receiving.required_sources("positive", receiving.PROFILE)
        for name in historical.required_sources("positive", "ipc-memory-v1"):
            self.assertIn(name, new)
        # A historical cgroup owner cannot be smuggled into a new receipt.
        changed = self.historical()
        cgroup = "kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/mod.rs"
        changed["files"][cgroup] = {"sha256": historical.IPC_SOURCE_SHA[cgroup]}
        with self.assertRaises(ValueError):
            receiving.check_sources(changed, "positive", receiving.PROFILE)


if __name__ == "__main__":
    unittest.main()
