#!/usr/bin/env python3
"""Real local Git, file and lease failures for original-entry provenance."""

import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import build_original_entry as build


class SourceAndEntryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        self.source = self.root / "source"
        self.source.mkdir()
        self.entry = self.source / "codex-rs/hepta-agentd/src/bin/native.rs"
        self.entry.parent.mkdir(parents=True)
        self.entry.write_text("fn main() {}\n")
        self.manifest = self.source / "codex-rs/hepta-agentd/Cargo.toml"
        self.manifest.write_text('[package]\nname="codex-hepta-agentd"\nversion="0.1.0"\n')
        self.git("init", "-q")
        self.git("add", ".")
        self.git("-c", "user.name=Native test", "-c", "user.email=native@example.invalid", "commit", "-qm", "source")
        self.head = self.git("rev-parse", "HEAD").strip()
        self.tree = self.git("rev-parse", "HEAD^{tree}").strip()
        self.metadata = {"workspace_members": ["original-package"], "packages": [{
            "id": "original-package", "name": build.PACKAGE, "manifest_path": str(self.manifest),
            "targets": [{"name": "native", "kind": ["bin"], "crate_types": ["bin"], "src_path": str(self.entry)}],
        }]}

    def git(self, *arguments):
        return subprocess.check_output(["/usr/bin/git", "-C", str(self.source), *arguments], text=True,
                                       stderr=subprocess.PIPE, env=build.BASE_ENV)

    def test_clean_actual_git_snapshot_matches_selected_original_entry(self):
        snapshot = build.source_snapshot(self.source, self.head, self.tree)
        target = build.select_original_target(self.metadata, self.source, "native", "bin")
        by_path = {item["path"]: item for item in snapshot["files"]}
        self.assertEqual(by_path[target["path"]]["sha256"], target["entry_sha256"])
        self.assertEqual(snapshot, build.source_snapshot(self.source, self.head, self.tree))

    def test_tracked_change_and_untracked_file_are_both_rejected(self):
        self.entry.write_text("fn main() { panic!(); }\n")
        with self.assertRaisesRegex(ValueError, "dirty"):
            build.source_snapshot(self.source, self.head, self.tree)
        self.git("checkout", "--", str(self.entry.relative_to(self.source)))
        (self.source / "replacement.rs").write_text("fn main() {}\n")
        with self.assertRaisesRegex(ValueError, "dirty"):
            build.source_snapshot(self.source, self.head, self.tree)

    def test_assume_unchanged_cannot_hide_mutated_source_bytes(self):
        self.git("update-index", "--assume-unchanged", str(self.entry.relative_to(self.source)))
        self.entry.write_text("fn main() { panic!(); }\n")
        self.assertEqual(self.git("status", "--porcelain=v1"), "")
        with self.assertRaisesRegex(ValueError, "bytes differ from Git"):
            build.source_snapshot(self.source, self.head, self.tree)

    def test_wrong_commit_and_wrong_tree_are_rejected(self):
        for head, tree in (("1" * 40, self.tree), (self.head, "2" * 40)):
            with self.subTest(head=head, tree=tree), self.assertRaises(ValueError):
                build.source_snapshot(self.source, head, tree)

    def test_external_fixture_package_and_source_are_rejected(self):
        variants = []
        external_manifest = json.loads(json.dumps(self.metadata))
        external_manifest["packages"][0]["manifest_path"] = str(self.root / "fixture/Cargo.toml")
        variants.append(external_manifest)
        external_source = json.loads(json.dumps(self.metadata))
        outside = self.root / "fixture.rs"
        outside.write_text("fn main() {}\n")
        external_source["packages"][0]["targets"][0]["src_path"] = str(outside)
        variants.append(external_source)
        for metadata in variants:
            with self.subTest(metadata=metadata), self.assertRaises(ValueError):
                build.select_original_target(metadata, self.source, "native", "bin")

    def test_required_feature_or_untracked_target_name_is_not_silently_enabled(self):
        self.metadata["packages"][0]["targets"][0]["required-features"] = ["test-issuer"]
        with self.assertRaisesRegex(ValueError, "explicit features"):
            build.select_original_target(self.metadata, self.source, "native", "bin")
        with self.assertRaisesRegex(ValueError, "does not exist"):
            build.select_original_target(self.metadata, self.source, "replacement", "bin")

    def test_busy_cache_and_linked_lease_are_rejected_without_waiting(self):
        target = self.root / "target"
        target.mkdir()
        with build.target_lease(target):
            with self.assertRaisesRegex(ValueError, "already leased"):
                with build.target_lease(target):
                    self.fail("second lease acquired")
        lock = target / ".hepta-native-userspace.lock"
        (target / "alias").hardlink_to(lock)
        with self.assertRaisesRegex(ValueError, "unaliased"):
            with build.target_lease(target):
                self.fail("aliased lease acquired")

    def test_failed_original_command_keeps_exit_and_real_log(self):
        output = self.root / "evidence"
        output.mkdir()
        report = {"commands": [], "g2_complete": False}
        with self.assertRaisesRegex(ValueError, "original command failed"):
            build.run(["/bin/sh", "-c", "echo retained-failure; exit 7"], self.root,
                      build.BASE_ENV, output, "failed.log", report, 10)
        self.assertEqual(report["commands"][0]["exit_code"], 7)
        self.assertEqual((output / "failed.log").read_text(), "retained-failure\n")
        self.assertFalse(json.loads((output / "result.json").read_text())["g2_complete"])


if __name__ == "__main__":
    unittest.main()
