"""Mutations of the real active product files must fail before a Cargo build."""
import importlib.util
from pathlib import Path
import re
import shutil
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("product_source", Path(__file__).with_name("verify_product_source.py"))
guard = importlib.util.module_from_spec(spec)
spec.loader.exec_module(guard)


class ProductSourceTests(unittest.TestCase):
    def setUp(self):
        source = Path(__file__).resolve().parents[2]
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        paths = ["README.md", guard.SOURCE, *guard.LOCKS,
                 "ui/Cargo.toml", *guard.REQUIRED]
        for relative in paths:
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / relative, target)
        self.commit = guard.verify(self.root)["hepta_commit"]

    def mutate_revision(self, relative):
        path = self.root / relative
        path.write_text(path.read_text().replace(self.commit, "0" * 40, 1))

    def test_current_pair_is_accepted_without_runtime_claim(self):
        self.assertFalse(guard.verify(self.root)["production_authority_verified"])

    def test_one_stale_patch_or_direct_dependency_is_rejected(self):
        for relative in ["ui/Cargo.toml", *guard.REQUIRED]:
            with self.subTest(relative=relative):
                path = self.root / relative
                original = path.read_bytes()
                self.mutate_revision(relative)
                with self.assertRaises(ValueError):
                    guard.verify(self.root)
                path.write_bytes(original)

    def test_one_stale_lock_entry_in_either_workspace_is_rejected(self):
        for relative in guard.LOCKS:
            with self.subTest(relative=relative):
                path = self.root / relative
                original = path.read_bytes()
                self.mutate_revision(relative)
                with self.assertRaisesRegex(ValueError, "lock entries"):
                    guard.verify(self.root)
                path.write_bytes(original)

    def test_readme_cannot_continue_linking_a_different_source(self):
        self.mutate_revision("README.md")
        # A display label alone is not the source link. Change every occurrence.
        path = self.root / "README.md"
        path.write_text(path.read_text().replace(self.commit, "0" * 40))
        with self.assertRaisesRegex(ValueError, "README"):
            guard.verify(self.root)

    def test_named_original_dependency_cannot_become_a_local_replacement(self):
        path = self.root / "ui/core/Cargo.toml"
        path.write_text(path.read_text().replace(f'git = "{guard.UPSTREAM}"', 'path = "replacement"', 1))
        with self.assertRaisesRegex(ValueError, "selected original Hepta"):
            guard.verify(self.root)

    def test_absent_original_lock_source_is_not_an_empty_success(self):
        (self.root / guard.LOCKS[0]).write_text("version = 4\n")
        with self.assertRaisesRegex(ValueError, "missing original Hepta"):
            guard.verify(self.root)

    def test_required_manifest_cannot_disappear_from_recursive_discovery(self):
        (self.root / "ui/core/Cargo.toml").unlink()
        with self.assertRaisesRegex(ValueError, "missing required product manifest"):
            guard.verify(self.root)

    def test_required_patches_cannot_be_removed_or_replaced(self):
        for relative, name in [("ui/Cargo.toml", "accesskit"),
                               ("services/hepta-session-host/Cargo.toml", "i18n-config")]:
            path = self.root / relative
            original = path.read_text()
            line = next(line for line in original.splitlines(keepends=True)
                        if line.startswith(f"{name} = "))
            for replacement in ("", f'{name} = {{ path = "replacement" }}\n'):
                with self.subTest(relative=relative, replacement=replacement):
                    path.write_text(original.replace(line, replacement, 1))
                    with self.assertRaisesRegex(ValueError, "required original Hepta patch"):
                        guard.verify(self.root)
                    path.write_text(original)

    def test_each_required_lock_package_must_keep_one_original_source(self):
        for relative, name in [("ui/Cargo.lock", "hepta-control-core"),
                               ("services/hepta-session-host/Cargo.lock", "codex-hepta-memory")]:
            path = self.root / relative
            original = path.read_text()
            block = re.search(r'\[\[package\]\]\nname = "' + re.escape(name)
                              + r'"\n.*?(?=\n\[\[package\]\]|\Z)', original, re.S).group()
            replaced = re.sub(r'source = "[^"]+"', 'source = "git+https://example.invalid/replacement#'
                              + '0' * 40 + '"', block, count=1)
            for replacement in ("", replaced, block + "\n" + block):
                with self.subTest(relative=relative, replacement=replacement[:80]):
                    path.write_text(original.replace(block, replacement, 1))
                    with self.assertRaisesRegex(ValueError, "required original package"):
                        guard.verify(self.root)
                    path.write_text(original)

    def test_independent_kernel_history_and_target_cache_are_outside_product_scope(self):
        for relative in ("kernel/asterinas/Cargo.toml", "services/hepta-os/Cargo.toml",
                         "results/history/ui/Cargo.toml", "ui/target/cache/Cargo.toml"):
            path = self.root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('[dependencies]\nold-owner = { git = "' + guard.UPSTREAM
                            + '", rev = "' + '0' * 40 + '" }\n')
        self.assertEqual(guard.verify(self.root)["hepta_commit"], self.commit)


if __name__ == "__main__":
    unittest.main()
