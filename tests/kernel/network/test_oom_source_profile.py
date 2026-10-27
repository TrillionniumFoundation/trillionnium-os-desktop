#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Static exact-source admission; executes no native or ordinary guest."""
import ast
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
import run_unix_stream_guest as historical
import run_unix_stream_signal_guest as signal
import run_unix_stream_oom_guest as post


class OomSourceProfile(unittest.TestCase):
    def actual(self):
        return {"files": {path: {"sha256": hashlib.sha256((ROOT / path).read_bytes()).hexdigest()}
                          for _, path, _ in post.OWNERS}}

    def test_unique_regular_literal_roles_match_current_bytes(self):
        self.assertEqual(len(post.OWNERS), post.ROLE_COUNT)
        self.assertGreater(post.ROLE_COUNT, 132)
        self.assertEqual(len({r for r, _, _ in post.OWNERS}), post.ROLE_COUNT)
        self.assertEqual(len({p for _, p, _ in post.OWNERS}), post.ROLE_COUNT)
        parsed = ast.parse((HERE / "run_unix_stream_oom_guest.py").read_text())
        owners = next(node for node in parsed.body if isinstance(node, ast.Assign)
                      and any(isinstance(t, ast.Name) and t.id == "OWNERS" for t in node.targets))
        self.assertEqual(ast.literal_eval(owners.value), post.OWNERS)
        for role, name, sha in post.OWNERS:
            with self.subTest(role=role):
                path = ROOT / name
                self.assertFalse(Path(name).is_absolute())
                self.assertNotIn("..", Path(name).parts)
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), sha)

    def test_inherits_all_132_role_paths_with_one_explicit_clone_byte_change(self):
        self.assertEqual(len(signal.OWNERS), 132)
        self.assertEqual([(role, path) for role, path, _ in post.OWNERS[:132]],
                         [(role, path) for role, path, _ in signal.OWNERS])
        changed = [(r, p) for (r, p, old), (_, _, new) in zip(signal.OWNERS, post.OWNERS) if old != new]
        self.assertEqual(changed, [("inherit.process.clone", "kernel/asterinas/kernel/core/src/process/clone.rs")])

    def test_current_composition_is_accepted(self):
        self.assertEqual(post.check_sources(self.actual(), "positive", post.PROFILE),
                         post.required_sources("positive", post.PROFILE))

    def test_each_missing_or_drifting_role_is_refused(self):
        actual = self.actual()
        for role, name, _ in post.OWNERS:
            for missing in (True, False):
                with self.subTest(role=role, missing=missing):
                    changed = {"files": dict(actual["files"])}
                    if missing:
                        del changed["files"][name]
                    else:
                        changed["files"][name] = {"sha256": "0" * 64}
                    with self.assertRaisesRegex(ValueError, "reviewed variant input mismatch"):
                        post.check_sources(changed, "positive", post.PROFILE)

    def test_duplicate_role_or_path_is_refused(self):
        role, name, sha = post.OWNERS[0]
        for row in ((role, "unique-invalid-alias", sha), ("unique-invalid-role", name, sha)):
            with patch.object(post, "OWNERS", post.OWNERS + (row,)):
                with self.assertRaisesRegex(ValueError, "duplicate"):
                    post.required_sources("positive", post.PROFILE)

    def test_historical_signal_profile_rejects_current_runtime(self):
        with self.assertRaisesRegex(ValueError, "reviewed variant input mismatch"):
            signal.check_sources(self.actual(), "positive", signal.PROFILE)
        with self.assertRaisesRegex(ValueError, "unknown production source profile"):
            post.required_sources("positive", signal.PROFILE)

    def test_unknown_profile_and_mutations_are_refused(self):
        with self.assertRaisesRegex(ValueError, "unknown production source profile"):
            post.required_sources("positive", "unknown-oom-profile")
        for variant in historical.oracle.VARIANTS:
            if variant != "positive":
                with self.subTest(variant=variant), self.assertRaises(ValueError):
                    post.required_sources(variant, post.PROFILE)

    def test_original_historical_engine_and_public_profiles_remain_exact(self):
        self.assertEqual(historical.SOURCE_PROFILES, ("legacy", "ipc-memory-v1"))
        self.assertEqual(post.ENGINE_SHA256, signal.ENGINE_SHA256)
        self.assertIs(post.check_sources, post.engine.check_sources)
        for name in ("check_sources", "main", "selection_valid"):
            self.assertEqual(getattr(post.engine, name).__code__.co_code,
                             getattr(historical, name).__code__.co_code)
        with self.assertRaises(ValueError):
            historical.required_sources("positive", post.PROFILE)

    def test_altered_engine_is_refused_before_execution(self):
        data = (HERE / "run_unix_stream_guest.py").read_bytes()
        post.verify_engine(data)
        with self.assertRaises(ValueError):
            post.verify_engine(data + b"\n")

    def test_all_runtime_changes_and_owned_guest_roles_are_bound(self):
        paths = {p for _, p, _ in post.OWNERS}
        required = {
            "kernel/asterinas/kernel/core/src/process/oom_adjustment.rs",
            "kernel/asterinas/kernel/core/src/process/oom_adjustment/tests.rs",
            "kernel/asterinas/kernel/core/src/process/clone.rs",
            "kernel/asterinas/kernel/core/src/process/mod.rs",
            "kernel/asterinas/kernel/core/src/process/process/mod.rs",
            "kernel/asterinas/kernel/core/src/process/process_vm/mod.rs",
            "kernel/asterinas/kernel/core/src/process/process/init_proc.rs",
            "kernel/asterinas/kernel/core/src/process/test_util.rs",
            "kernel/asterinas/kernel/core/src/fs/fs_impls/procfs/pid/task/oom_score_adj.rs",
            "support/kernel-safety/OOM_ADJUSTMENT.md",
            "tests/kernel/oom-adjustment/probe.c",
            "tests/kernel/oom-adjustment/run.py",
            "tests/kernel/oom-adjustment/README.md",
            "tests/kernel/network/run_unix_stream_signal_guest.py",
            "tests/kernel/network/test_signal_source_profile.py",
            "tests/kernel/network/controls/post1138-unix-signal-v2-source.json.gz",
            "kernel/asterinas/kernel/core/src/security/lsm/hooks/capability.rs",
            "kernel/asterinas/kernel/core/src/process/credentials/credentials_.rs",
            "kernel/asterinas/kernel/core/src/fs/fs_impls/procfs/template/mod.rs",
        }
        self.assertTrue(required.issubset(paths))


if __name__ == "__main__":
    unittest.main()
