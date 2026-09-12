"""Isolated projector tests; fixtures never stand in for repository qualification."""
from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "module_index_under_test", Path(__file__).absolute().parents[1] / "tools/project_module_index.py"
)
assert SPEC is not None and SPEC.loader is not None
INDEX = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INDEX)


class ModuleIndexTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.entries = []
        for name in ("alpha", "beta"):
            path = f"crates/{name}"
            entry = {"id": name, "package": name, "path": path,
                     "documentation": path + "/README.md", "status": "source_candidate",
                     "claim_ceiling": "source only; no installed image or release"}
            self.entries.append(entry)
            self.put(path + "/Cargo.toml", f'[package]\nname = "{name}"\n')
            self.put(entry["documentation"],
                     f"Status: `{entry['status']}`\nClaim ceiling: `{entry['claim_ceiling']}`\n")
        self.registry = {"schema": "trillionnium.desktop.modules.v1",
                         "plan_revision": "2026-08-29-d6", "policy": {}, "modules": self.entries}
        self.save_registry()
        self.put("manifests/project-state.v1.json", '{"active_plan_revision":"2026-08-29-d6"}')
        self.put("Cargo.toml", '[workspace]\nmembers = ["crates/alpha", "crates/beta"]\n')
        self.put(INDEX.INDEX, INDEX.render(self.root))

    def put(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")

    def save_registry(self):
        self.put(INDEX.REGISTRY, json.dumps(self.registry))

    def test_current_index_passes_and_is_deterministic(self):
        INDEX.check(self.root)
        self.assertEqual(INDEX.render(self.root), INDEX.render(self.root))

    def test_read_only_check_rejects_stale_index(self):
        self.put(INDEX.INDEX, "stale\n")
        with self.assertRaisesRegex(ValueError, "stale"):
            INDEX.check(self.root)
        self.assertEqual((self.root / INDEX.INDEX).read_text(), "stale\n")

    def test_explicit_write_regenerates(self):
        self.put(INDEX.INDEX, "stale\n")
        self.assertEqual(INDEX.main(["--root", str(self.root), "--write"]), 0)
        INDEX.check(self.root)

    def test_missing_index_is_rejected(self):
        (self.root / INDEX.INDEX).unlink()
        with self.assertRaises(ValueError):
            INDEX.check(self.root)

    def test_status_change_requires_readme_and_index(self):
        self.entries[0]["status"] = "candidate_updated"
        self.save_registry()
        with self.assertRaisesRegex(ValueError, "README"):
            INDEX.render(self.root)
        entry = self.entries[0]
        self.put(entry["documentation"],
                 f"Status: `{entry['status']}`\nClaim ceiling: `{entry['claim_ceiling']}`\n")
        with self.assertRaisesRegex(ValueError, "stale"):
            INDEX.check(self.root)

    def test_duplicate_json_members_rejected(self):
        self.put(INDEX.REGISTRY, '{"schema":1,"schema":2}')
        with self.assertRaisesRegex(ValueError, "duplicate JSON"):
            INDEX.render(self.root)

    def test_non_json_numbers_rejected(self):
        for value in ("NaN", "Infinity", "1.5"):
            with self.subTest(value=value):
                self.put(INDEX.REGISTRY, '{"schema":' + value + '}')
                with self.assertRaises(ValueError):
                    INDEX.render(self.root)

    def test_bom_rejected(self):
        self.put(INDEX.REGISTRY, '\ufeff' + json.dumps(self.registry))
        with self.assertRaises(ValueError):
            INDEX.render(self.root)

    def test_plan_revision_drift_rejected(self):
        self.registry["plan_revision"] = "other-plan"
        self.save_registry()
        with self.assertRaisesRegex(ValueError, "plan"):
            INDEX.render(self.root)

    def test_missing_and_reordered_members_rejected(self):
        for members in ([self.entries[0]], list(reversed(self.entries))):
            with self.subTest(members=members):
                self.registry["modules"] = members
                self.save_registry()
                with self.assertRaises(ValueError):
                    INDEX.render(self.root)

    def test_duplicate_workspace_members_rejected(self):
        self.put("Cargo.toml", '[workspace]\nmembers = ["crates/alpha", "crates/alpha"]\n')
        with self.assertRaisesRegex(ValueError, "duplicate"):
            INDEX.render(self.root)

    def test_package_name_drift_rejected(self):
        self.put("crates/alpha/Cargo.toml", '[package]\nname = "wrong"\n')
        with self.assertRaisesRegex(ValueError, "Cargo"):
            INDEX.render(self.root)

    def test_registry_and_index_symlinks_rejected(self):
        for relative in (INDEX.REGISTRY, INDEX.INDEX):
            with self.subTest(relative=relative):
                path = self.root / relative
                contents = path.read_bytes()
                other = self.root / "other"
                other.write_bytes(contents)
                path.unlink()
                path.symlink_to(other)
                try:
                    with self.assertRaisesRegex(ValueError, "symlink"):
                        INDEX.check(self.root)
                finally:
                    path.unlink()
                    path.write_bytes(contents)

    def test_symlinked_checkout_root_rejected(self):
        alias = self.root / "root-link"
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "symlink"):
            INDEX.render(alias)

    def test_path_traversal_rejected(self):
        for relative in ("../outside", "/absolute", "docs//file", "docs/./file", "a\\b"):
            with self.subTest(relative=relative):
                with self.assertRaises(ValueError):
                    INDEX.safe_path(self.root, relative)

    def test_control_characters_rejected(self):
        self.entries[0]["claim_ceiling"] = "source\nforged row"
        self.save_registry()
        with self.assertRaisesRegex(ValueError, "control"):
            INDEX.render(self.root)

    def test_table_metacharacters_are_escaped(self):
        self.assertEqual(INDEX.table_text("<x>|`y`\\"), "&lt;x&gt;&#124;&#96;y&#96;&#92;")

    def test_non_regular_index_is_rejected_without_reading(self):
        path = self.root / INDEX.INDEX
        path.unlink()
        os.mkfifo(path)
        with self.assertRaisesRegex(ValueError, "non-regular"):
            INDEX.check(self.root)

    def test_oversized_registry_rejected(self):
        self.put(INDEX.REGISTRY, " " * (INDEX.MAX_BYTES + 1))
        with self.assertRaisesRegex(ValueError, "oversized"):
            INDEX.render(self.root)

    def test_empty_workspace_rejected(self):
        self.put("Cargo.toml", "[workspace]\nmembers = []\n")
        with self.assertRaises(ValueError):
            INDEX.render(self.root)


if __name__ == "__main__":
    unittest.main()
