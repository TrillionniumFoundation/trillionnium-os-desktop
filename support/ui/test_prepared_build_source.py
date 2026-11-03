"""The explicit lock variant cannot hide another source modification."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest

HERE = Path(__file__).resolve().parent


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


variant = load("variant", HERE / "prepared_build_source.py")
profile = load("profile", HERE.parent / "release/organ_release_profile.py")


class PreparedBuildSource(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        root = self.directory / "original"
        root.mkdir()
        subprocess.run(["git", "init", "-q", str(root)], check=True)
        for name, data in (("ui/Cargo.lock", b"original-git-sdk\n"),
                           (variant.LOCK, b"declared-prepared-sdk\n"),
                           ("ui/src/lib.rs", b"pub fn original() {}\n")):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(["git", "-c", "user.name=Fixture", "-c", "user.email=fixture@example.invalid",
                        "-C", str(root), "commit", "-qm", "fixture"], check=True)
        self.original = profile.Repository(root, "fixture")
        self.identity = {"commit": self.original.git("rev-parse", "HEAD").decode().strip(),
                         "tree": self.original.git("rev-parse", "HEAD^{tree}").decode().strip()}
        self.copy, self.lock, self.receipt = variant.prepare(
            self.original, self.directory / "copy", self.identity, profile.Repository,
            self.directory / "clone.log")

    def test_only_declared_lock_changes_and_original_stays_clean(self):
        variant.verify(self.copy, self.identity, self.lock)
        self.original.check(self.identity["commit"], self.identity["tree"])
        self.assertEqual(self.receipt["only_changed_path"], "ui/Cargo.lock")

    def test_rust_source_change_is_refused(self):
        (self.copy.path / "ui/src/lib.rs").write_text("pub fn changed() {}\n")
        with self.assertRaisesRegex(ValueError, "beyond its declared UI lock"):
            variant.verify(self.copy, self.identity, self.lock)

    def test_changed_declared_lock_is_refused(self):
        (self.copy.path / "ui/Cargo.lock").write_bytes(self.lock + b"changed\n")
        with self.assertRaisesRegex(ValueError, "differs from its committed input"):
            variant.verify(self.copy, self.identity, self.lock)

    def test_untracked_source_is_refused(self):
        (self.copy.path / "extra.rs").write_text("pub fn extra() {}\n")
        with self.assertRaisesRegex(ValueError, "beyond its declared UI lock"):
            variant.verify(self.copy, self.identity, self.lock)

    def test_hidden_tracked_change_is_refused(self):
        self.copy.git("update-index", "--assume-unchanged", "ui/src/lib.rs")
        with self.assertRaisesRegex(ValueError, "hidden tracked changes"):
            variant.verify(self.copy, self.identity, self.lock)

    def test_other_source_identity_is_refused(self):
        with self.assertRaisesRegex(ValueError, "identity changed"):
            variant.verify(self.copy, dict(self.identity, tree="0" * 40), self.lock)


if __name__ == "__main__":
    unittest.main()
