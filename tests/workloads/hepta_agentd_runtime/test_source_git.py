"""Exercise the source preflight against real Git repositories and hooks."""
import copy
import json
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import prepare_inputs as preparation


class SourceGitTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="hepta-f1-source-git-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name).resolve()
        self.roots = {name: self.root / name for name in ("desktop", "hepta")}
        self.sources, files = {}, []
        for name, source in self.roots.items():
            source.mkdir()
            self.git(source, "init", "-q")
            (source / "reviewed.rs").write_text("pub fn original() {}\n")
            (source / "other-tracked.rs").write_text("pub fn also_compiled() {}\n")
            if name == "hepta":
                (source / "codex-rs").mkdir()
                (source / "codex-rs/rust-toolchain.toml").write_text('[toolchain]\nchannel="1.96.0"\n')
            self.git(source, "add", ".")
            self.git(source, "commit", "-qm", "Original source fixture")
            self.sources[name] = {"head": self.git(source, "rev-parse", "HEAD"),
                                  "tree": self.git(source, "rev-parse", "HEAD^{tree}")}
            files.append({"repository": name, "path": "reviewed.rs",
                          "sha256": preparation.sha(source / "reviewed.rs"),
                          "git_blob": self.git(source, "rev-parse", "HEAD:reviewed.rs")})
        self.review = {"source_files": files, "userspace_toolchain": {
            "channel": "1.96.0", "manifest": "codex-rs/rust-toolchain.toml",
            "sha256": preparation.sha(self.roots["hepta"] / "codex-rs/rust-toolchain.toml")}}
        self.review_root = self.root / "review"
        self.review_root.mkdir()
        self.write_review()

    def git(self, source, *args, input=None):
        environment = {**preparation.gate.abi.ENV, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
        result = subprocess.run(["git", "-C", str(source), "-c", "user.name=Source test",
                                 "-c", "user.email=source-test@example.invalid", "-c", "commit.gpgSign=false", *args],
                                env=environment, input=input, text=True, capture_output=True, timeout=10, check=True)
        return result.stdout.strip()

    def write_review(self):
        (self.review_root / "source-review.json").write_text(json.dumps(self.review))

    def verify(self):
        # Only the reviewed fixture identities are selected here. Git, the
        # index, files, hashes and original toolchain validator all execute.
        with patch.object(preparation, "HERE", self.review_root), \
             patch.object(preparation.gate, "SOURCES", self.sources):
            return preparation.verify_sources(self.roots)

    def test_repository_monitor_is_not_executed_and_dirty_tracked_source_still_fails(self):
        source = self.roots["desktop"]
        marker, hook = self.root / "monitor-called", self.root / "monitor-hook"
        hook.write_text("#!/bin/sh\nprintf 'called\\n' >> " + shlex.quote(str(marker))
                        + "\nprintf 'test-token\\000'\n")
        hook.chmod(0o700)
        self.git(source, "config", "core.fsmonitor", str(hook))
        self.git(source, "config", "core.fsmonitorHookVersion", "2")
        self.git(source, "config", "core.untrackedCache", "true")
        self.git(source, "status", "--porcelain=v1", "--untracked-files=all")
        self.assertTrue(marker.is_file(), "control Git status must execute the actual configured hook")
        marker.unlink()
        index = (source / ".git/index").read_bytes()
        self.assertEqual(self.verify(), self.review["source_files"])
        self.assertFalse(marker.exists())
        self.assertEqual((source / ".git/index").read_bytes(), index)
        # This file is outside the selected blob list, so full cleanliness
        # cannot be replaced by checking only the reviewed files.
        (source / "other-tracked.rs").write_text("pub fn unreviewed_change() {}\n")
        with self.assertRaisesRegex(ValueError, "dirty desktop source"):
            self.verify()
        self.assertFalse(marker.exists())

    def test_cached_clean_status_does_not_hide_a_new_untracked_input(self):
        source = self.roots["desktop"]
        self.git(source, "config", "core.untrackedCache", "true")
        self.git(source, "status", "--porcelain=v1", "--untracked-files=all")
        (source / "new-build-input").write_text("unreviewed\n")
        with self.assertRaisesRegex(ValueError, "dirty desktop source"):
            self.verify()

    def test_real_hidden_index_flags_are_rejected_for_unlisted_tracked_files(self):
        source = self.roots["hepta"]
        (source / "other-tracked.rs").write_text("pub fn hidden_change() {}\n")
        for flag in ("assume-unchanged", "skip-worktree"):
            with self.subTest(flag=flag):
                self.git(source, "update-index", "--" + flag, "other-tracked.rs")
                self.assertEqual(self.git(source, "status", "--porcelain=v1", "--untracked-files=all"), "")
                with self.assertRaisesRegex(ValueError, "flags hide source changes"):
                    self.verify()
                self.git(source, "update-index", "--no-" + flag, "other-tracked.rs")

    def test_replacement_objects_cannot_substitute_the_reviewed_tree_or_blob(self):
        source = self.roots["desktop"]
        blob = self.git(source, "hash-object", "-w", "--stdin", input="substitute\n")
        tree = self.git(source, "mktree", input=f"100644 blob {blob}\treviewed.rs\n")
        commit = self.git(source, "commit-tree", tree, "-m", "Replacement fixture")
        self.git(source, "replace", self.sources["desktop"]["head"], commit)
        self.assertEqual(self.git(source, "rev-parse", "HEAD^{tree}"), tree)
        self.assertNotEqual(tree, self.sources["desktop"]["tree"])
        self.assertEqual(self.verify(), self.review["source_files"])
        self.assertEqual(preparation.git(source, "rev-parse", "HEAD:reviewed.rs"),
                         self.review["source_files"][0]["git_blob"])

    def test_ambient_git_routing_and_index_environment_cannot_change_the_source(self):
        inherited = {"GIT_DIR": str(self.root / "wrong-git-dir"), "GIT_WORK_TREE": str(self.root),
                     "GIT_INDEX_FILE": str(self.root / "wrong-index"),
                     "GIT_OBJECT_DIRECTORY": str(self.root / "wrong-objects"),
                     "GIT_CONFIG_COUNT": "1", "GIT_CONFIG_KEY_0": "core.fsmonitor",
                     "GIT_CONFIG_VALUE_0": str(self.root / "wrong-monitor"), "GIT_NO_REPLACE_OBJECTS": "0"}
        with patch.dict(os.environ, inherited):
            self.assertEqual(self.verify(), self.review["source_files"])
            (self.roots["desktop"] / "other-tracked.rs").write_text("changed\n")
            with self.assertRaisesRegex(ValueError, "dirty desktop source"):
                self.verify()

    def test_original_head_tree_content_and_blob_checks_remain_required(self):
        original_sources, original_review = copy.deepcopy(self.sources), copy.deepcopy(self.review)
        for field, message in (("head", "commit"), ("tree", "tree"),
                               ("sha256", "content changed"), ("git_blob", "Git blob changed")):
            with self.subTest(field=field):
                self.sources, self.review = copy.deepcopy(original_sources), copy.deepcopy(original_review)
                if field in ("head", "tree"):
                    self.sources["desktop"][field] = "0" * 40
                else:
                    self.review["source_files"][0][field] = "0" * (64 if field == "sha256" else 40)
                self.write_review()
                with self.assertRaisesRegex(ValueError, message):
                    self.verify()


if __name__ == "__main__":
    unittest.main(verbosity=2)
