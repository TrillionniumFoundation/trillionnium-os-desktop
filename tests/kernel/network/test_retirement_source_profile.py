#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Source admission only; these checks execute no kernel or native guest."""
import hashlib
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_unix_stream_guest as historical
import run_unix_stream_receiving_guest as receiving
import run_unix_stream_post1138_guest as prior
import run_unix_stream_cpunode_guest as cpunode
import run_unix_stream_retirement_guest as post


class Post1138VmRetirementSourceProfile(unittest.TestCase):
    def actual(self):
        return {"files": {path: {"sha256": hashlib.sha256((HERE.parents[2] / path).read_bytes()).hexdigest()}
                          for _, path, _ in post.OWNERS}}

    def test_fixed_roles_are_unique_regular_current_sources(self):
        self.assertEqual(len(post.OWNERS), 90)
        self.assertEqual(len({r for r, _, _ in post.OWNERS}), 90)
        self.assertEqual(len({p for _, p, _ in post.OWNERS}), 90)
        for role, name, sha in post.OWNERS:
            with self.subTest(role=role):
                self.assertFalse(Path(name).is_absolute())
                self.assertNotIn("..", Path(name).parts)
                path = HERE.parents[2] / name
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), sha)

    def test_accepts_the_actual_reviewed_composition(self):
        required = post.required_sources("positive", post.PROFILE)
        self.assertEqual(post.check_sources(self.actual(), "positive", post.PROFILE), required)

    def test_every_missing_source_is_refused(self):
        actual = self.actual()
        post.check_sources(actual, "positive", post.PROFILE)
        for role, name, _ in post.OWNERS:
            with self.subTest(role=role):
                changed = {"files": dict(actual["files"])}
                del changed["files"][name]
                with self.assertRaisesRegex(ValueError, "reviewed variant input mismatch"):
                    post.check_sources(changed, "positive", post.PROFILE)

    def test_every_drifting_source_is_refused(self):
        actual = self.actual()
        post.check_sources(actual, "positive", post.PROFILE)
        for role, name, _ in post.OWNERS:
            with self.subTest(role=role):
                changed = {"files": dict(actual["files"])}
                changed["files"][name] = {"sha256": "0" * 64}
                with self.assertRaisesRegex(ValueError, "reviewed variant input mismatch"):
                    post.check_sources(changed, "positive", post.PROFILE)

    def test_duplicate_role_is_not_an_alias(self):
        role, _, sha = post.OWNERS[0]
        with patch.object(post, "OWNERS", post.OWNERS + ((role, "unique-invalid-alias", sha),)):
            with self.assertRaisesRegex(ValueError, "duplicate"):
                post.required_sources("positive", post.PROFILE)

    def test_duplicate_path_is_not_an_alias(self):
        _, name, sha = post.OWNERS[0]
        with patch.object(post, "OWNERS", post.OWNERS + (("unique-invalid-role", name, sha),)):
            with self.assertRaisesRegex(ValueError, "duplicate"):
                post.required_sources("positive", post.PROFILE)

    def test_historical_variants_and_unknown_profiles_are_refused(self):
        for variant in historical.oracle.VARIANTS:
            if variant != "positive":
                with self.subTest(variant=variant), self.assertRaises(ValueError):
                    post.required_sources(variant, post.PROFILE)
        with self.assertRaisesRegex(ValueError, "unknown production source profile"):
            post.required_sources("positive", "unknown-post-profile")

    def test_old_strict_profiles_reject_the_current_composition(self):
        actual = self.actual()
        for module, profile in [(historical, "ipc-memory-v1"), (receiving, receiving.PROFILE), (prior, prior.PROFILE), (cpunode, cpunode.PROFILE)]:
            with self.subTest(profile=profile), self.assertRaisesRegex(ValueError, "reviewed variant input mismatch"):
                module.check_sources(actual, "positive", profile)

    def test_private_engine_does_not_modify_public_historical_rules(self):
        self.assertEqual(historical.SOURCE_PROFILES, ("legacy", "ipc-memory-v1"))
        with self.assertRaises(ValueError):
            historical.required_sources("positive", post.PROFILE)
        self.assertIs(post.check_sources, post.engine.check_sources)
        for name in ("check_sources", "main", "selection_valid"):
            self.assertEqual(getattr(post.engine, name).__code__.co_code,
                             getattr(historical, name).__code__.co_code)
        for profile in historical.SOURCE_PROFILES:
            self.assertEqual(post.required_sources("positive", profile),
                             historical.required_sources("positive", profile))

    def test_engine_bytes_must_match_before_execution(self):
        data = (HERE / "run_unix_stream_guest.py").read_bytes()
        post.verify_engine(data)
        with self.assertRaises(ValueError):
            post.verify_engine(data + b"\n")

    def test_all_thirteen_component_changes_are_bound(self):
        paths = {p for _, p, _ in post.OWNERS}
        changed = {
            "kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu.rs",
            "kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/group_entity_regressions.rs",
            "kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/cpu/scheduling_route.rs",
            "kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/controller/mod.rs",
            "kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/mod.rs",
            "kernel/asterinas/kernel/core/src/fs/fs_impls/cgroupfs/systree_node.rs",
            "kernel/asterinas/kernel/core/src/sched/sched_class/affinity.rs",
            "kernel/asterinas/kernel/core/src/sched/sched_class/mod.rs",
            "kernel/asterinas/kernel/core/src/sched/sched_class/switch_tests.rs",
            "kernel/asterinas/kernel/core/src/sched/sched_class/fair/group.rs",
            "kernel/asterinas/kernel/core/src/sched/sched_class/fair/group/prepare.rs",
            "support/kernel-safety/FAIR_GROUP_ENTITIES.md",
            "docs/ASTERINAS_CPU_BANDWIDTH_N0.md",
        }
        changed.update({
            '.github/workflows/a06-kernel.yml',
            'kernel/asterinas/ostd/src/arch/x86/trap/gdt.rs',
            'kernel/asterinas/ostd/src/arch/x86/trap/gdt_tests.rs',
            'support/kernel-safety/VDSO_CPU_IDENTITY.md',
            'tests/kernel/network/run_unix_stream_post1138_guest.py',
            'tests/kernel/vdso-cpu/README.md',
            'tests/kernel/vdso-cpu/probe.c',
            'tests/kernel/vdso-cpu/run.py',
        })
        changed.update({
            'kernel/asterinas/ostd/src/mm/vm_space.rs',
            'kernel/asterinas/ostd/src/mm/page_table/mod.rs',
            'kernel/asterinas/ostd/src/mm/page_table/node/mod.rs',
            'kernel/asterinas/ostd/src/task/processor_retirement_tests.rs',
            'support/kernel-safety/VMSPACE_RETIREMENT.md',
            'tests/kernel/network/run_unix_stream_cpunode_guest.py',
            "kernel/asterinas/kernel/core/src/thread/mod.rs",
            "kernel/asterinas/ostd/src/task/mod.rs",
            "kernel/asterinas/ostd/src/task/processor.rs",
        })
        self.assertTrue(changed.issubset(paths))


if __name__ == "__main__":
    unittest.main()
