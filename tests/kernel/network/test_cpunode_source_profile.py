#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Source admission only; these checks execute no kernel or native guest."""
import base64
import gzip
import hashlib
import importlib.util
import json
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
import run_unix_stream_cpunode_guest as post


class Post1138CpunodeSourceProfile(unittest.TestCase):
    def test_cpu_fixture_rejects_preexisting_marker_aliases(self):
        spec = importlib.util.spec_from_file_location("_cpu_marker_guard_rejection", HERE.parent / "vdso-cpu/run.py")
        cpu = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cpu)
        for name in (".hepta-vdso-cpu-qa", "./.hepta-vdso-cpu-qa", "././.hepta-vdso-cpu-qa",
                     "/.hepta-vdso-cpu-qa"):
            with self.subTest(name=name):
                fields = [1, 0o100400, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
                archive = gzip.compress(cpu.runner.pack([(name, fields, b"old-fixture-only\n")]), mtime=0)
                with patch.object(cpu, "base_initramfs", return_value=archive):
                    with self.assertRaisesRegex(ValueError, "private CPU probe marker already exists"):
                        cpu.initramfs(b"synthetic-input", {}, "new-fixture-only", 1)

    def test_cpu_fixture_preserves_base_and_adds_one_private_marker(self):
        spec = importlib.util.spec_from_file_location("_cpu_marker_guard_admission", HERE.parent / "vdso-cpu/run.py")
        cpu = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cpu)
        fields = [1, 0o100644, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
        archive = gzip.compress(cpu.runner.pack([("fixture-note", fields, b"synthetic-only\n")]), mtime=0)
        original = cpu.runner.unpack(gzip.decompress(archive))
        with patch.object(cpu, "base_initramfs", return_value=archive):
            result = cpu.runner.unpack(gzip.decompress(cpu.initramfs(b"synthetic-input", {}, "new-fixture-only", 1)))
        self.assertEqual(result[:-1], original)
        self.assertEqual(len(result), len(original) + 1)
        name, actual_fields, data = result[-1]
        self.assertEqual(name, ".hepta-vdso-cpu-qa")
        self.assertEqual(actual_fields[0], max(f[0] for _, f, _ in original) + 1)
        self.assertEqual(actual_fields[1], 0o100400)
        self.assertEqual(data, b"new-fixture-only\n")

    def actual(self):
        return self.historical()

    def historical(self):
        # Real CAB Git blobs keep the historical positive independent of the
        # current checkout. Decode in memory; never extract fixture paths.
        encoded = (HERE / "controls/post1138-cpunode-v1-source.json.gz").read_bytes()
        self.assertEqual(hashlib.sha256(encoded).hexdigest(),
                         "20d09d318775fb18da6f3cbd58a5bcc063317523ac8fedf668f8358a622909e2")
        fixture = json.loads(gzip.decompress(encoded))
        self.assertEqual(fixture["schema"], "asterinas.post1138-cpunode-v1-historical-source.v1")
        self.assertEqual(fixture["source_head"], "cab93cfb2a7c5e3dddd67e63895cb5a86ff2eb33")
        self.assertEqual(fixture["source_tree"], "3f9e99c02d509576f6af1c960b2cedbca7ddc049")
        expected = {path: (role, sha) for role, path, sha in post.OWNERS}
        self.assertEqual(len(fixture["files"]), 84)
        self.assertEqual({row["path"] for row in fixture["files"]}, set(expected))
        self.assertEqual(len({row["role"] for row in fixture["files"]}), 84)
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

    def test_fixed_roles_are_unique_regular_historical_sources(self):
        self.assertEqual(len(post.OWNERS), 84)
        self.assertEqual(len({r for r, _, _ in post.OWNERS}), 84)
        self.assertEqual(len({p for _, p, _ in post.OWNERS}), 84)
        actual = self.actual()
        for role, name, sha in post.OWNERS:
            with self.subTest(role=role):
                self.assertFalse(Path(name).is_absolute())
                self.assertNotIn("..", Path(name).parts)
                path = HERE.parents[2] / name
                self.assertTrue(path.is_file())
                self.assertFalse(path.is_symlink())
                self.assertEqual(actual["files"][name]["sha256"], sha)

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
        for module, profile in [(historical, "ipc-memory-v1"), (receiving, receiving.PROFILE), (prior, prior.PROFILE)]:
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
        self.assertTrue(changed.issubset(paths))


if __name__ == "__main__":
    unittest.main()
