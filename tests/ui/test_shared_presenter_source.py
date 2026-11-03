#!/usr/bin/env python3
"""Mutation regressions for the original-package source binding gate."""
import copy
import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("presenter_guard", Path(__file__).with_name("verify_shared_presenter.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class SourceBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        paths = guard.REQUIRED_SOURCES | set(guard.PACKAGES.values()) | {
            "LICENSE", "NOTICE", "apps/hepta-control-ui/rust/robrix-ui/licenses/ROBRIX-MIT.txt"}
        self.source = {"schema": "trillionnium.original-shared-presenter.v1", "repository": guard.REPOSITORY,
                       "files": []}
        for path in sorted(paths):
            data = ("fixture only: " + path + "\n").encode()
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            self.source["files"].append(self.record(path, data))
        self.git("init", "--quiet")
        self.git("add", ".")
        self.git("-c", "user.name=Gate Fixture", "-c", "user.email=fixture@invalid", "commit", "--quiet", "-m", "fixture")
        commit = self.git("rev-parse", "HEAD")
        self.source.update(commit=commit, tree=self.git("rev-parse", "HEAD^{tree}"))
        source_id = f"git+https://github.com/{guard.REPOSITORY}?rev={commit}#{commit}"
        packages = [{"name": name, "id": name, "version": "0.1.0", "source": source_id,
                     "manifest_path": str(self.root / path)} for name, path in guard.PACKAGES.items()]
        packages.extend({"name": name, "id": name, "features": {"default": []}}
                        for name in ("trill-ui-core", "trill-shell"))
        nodes = [{"id": "hepta-robrix-ui", "features": []}]
        nodes.extend({"id": name, "features": ["hepta-shared-presenter"]}
                     for name in ("trill-ui-core", "trill-shell"))
        self.metadata = {"packages": packages, "resolve": {"nodes": nodes}}

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.root), *args], text=True).strip()

    @staticmethod
    def record(path, data):
        return {"path": path, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                "git_blob": hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()}

    def test_exact_fixture_checkout_and_packages_are_accepted(self):
        guard.validate_manifest(self.source)
        self.assertEqual(guard.check_packages(self.metadata, self.source), self.root)
        guard.check_checkout(self.root, self.source)
        guard.check_files(self.root, self.source)

    def test_changed_source_cannot_be_accepted_even_after_rehashing_manifest(self):
        item = self.source["files"][0]
        (self.root / item["path"]).write_bytes(b"edited local implementation\n")
        with self.assertRaises(ValueError):
            guard.check_files(self.root, self.source)
        item.update(self.record(item["path"], (self.root / item["path"]).read_bytes()))
        guard.check_files(self.root, self.source)
        with self.assertRaises(ValueError):
            guard.check_checkout(self.root, self.source)

    def test_wrong_commit_or_tree_is_rejected(self):
        for field in ("commit", "tree"):
            changed = copy.deepcopy(self.source)
            changed[field] = "a" * 40
            with self.assertRaises(ValueError):
                guard.check_checkout(self.root, changed)

    def test_index_flags_cannot_hide_changes_outside_review_manifest(self):
        path = "apps/hepta-control-ui/rust/core/src/additional.rs"
        target = self.root / path
        target.write_text("original fixture module\n")
        self.git("add", path)
        self.git("-c", "user.name=Gate Fixture", "-c", "user.email=fixture@invalid", "commit", "--quiet", "-m", "extra fixture module")
        self.source.update(commit=self.git("rev-parse", "HEAD"), tree=self.git("rev-parse", "HEAD^{tree}"))
        self.git("update-index", "--assume-unchanged", path)
        target.write_text("hidden local modification\n")
        self.assertEqual(self.git("status", "--porcelain=v1"), "")
        with self.assertRaises(ValueError):
            guard.check_checkout(self.root, self.source)

    def test_same_named_local_package_or_other_git_source_is_rejected(self):
        for source in (None, "git+https://github.com/unrelated/replacement#" + self.source["commit"]):
            changed = copy.deepcopy(self.metadata)
            changed["packages"][0]["source"] = source
            with self.assertRaises(ValueError):
                guard.check_packages(changed, self.source)

    def test_inactive_feature_and_unqualified_renderer_are_rejected(self):
        changed = copy.deepcopy(self.metadata)
        changed["resolve"]["nodes"][1]["features"] = []
        with self.assertRaises(ValueError):
            guard.check_packages(changed, self.source)
        changed = copy.deepcopy(self.metadata)
        changed["resolve"]["nodes"][0]["features"] = ["ui"]
        with self.assertRaises(ValueError):
            guard.check_packages(changed, self.source)

    def test_duplicate_package_or_missing_critical_source_is_rejected(self):
        changed = copy.deepcopy(self.metadata)
        changed["packages"].append(changed["packages"][0])
        with self.assertRaises(ValueError):
            guard.check_packages(changed, self.source)
        changed = copy.deepcopy(self.source)
        omitted = next(iter(guard.REQUIRED_SOURCES))
        changed["files"] = [item for item in changed["files"] if item["path"] != omitted]
        with self.assertRaises(ValueError):
            guard.validate_manifest(changed)

    def test_symlink_and_path_escape_are_rejected(self):
        item = self.source["files"][0]
        path = self.root / item["path"]
        data = path.read_bytes()
        alternate = self.root / "alternate"
        alternate.write_bytes(data)
        path.unlink()
        path.symlink_to(alternate)
        with self.assertRaises(ValueError):
            guard.check_files(self.root, self.source)
        changed = copy.deepcopy(self.source)
        changed["files"][0]["path"] = "../escape"
        with self.assertRaises(ValueError):
            guard.validate_manifest(changed)

    def test_candidate_default_enablement_is_rejected(self):
        changed = copy.deepcopy(self.metadata)
        changed["packages"][-1]["features"]["default"] = ["hepta-shared-presenter"]
        with self.assertRaises(ValueError):
            guard.check_packages(changed, self.source)

    def test_local_upstream_notices_are_exact_and_required(self):
        directory = self.root / "local-notices"
        directory.mkdir()
        for name, path in guard.LICENSE_COPIES.items():
            (directory / name).write_bytes((self.root / path).read_bytes())
        guard.check_license_copies(directory, self.source)
        target = directory / "ROBRIX-MIT.txt"
        original = target.read_bytes()
        target.write_bytes(original + b"changed")
        with self.assertRaises(ValueError):
            guard.check_license_copies(directory, self.source)
        target.unlink()
        with self.assertRaises(ValueError):
            guard.check_license_copies(directory, self.source)


if __name__ == "__main__":
    unittest.main()
