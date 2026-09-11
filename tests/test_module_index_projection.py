"""Hostile tests for index projection; no runtime or release claims."""
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

SOURCE = Path(__file__).resolve().parents[1] / "tools/render_module_index.py"
SPEC = importlib.util.spec_from_file_location("module_index_under_test", SOURCE)
assert SPEC is not None and SPEC.loader is not None
INDEX = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(INDEX)


class ModuleIndexProjectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.registry = {"schema": "trillionnium.desktop.modules.v1", "plan_revision": "2026-08-29-d6",
                         "policy": {}, "modules": [{"id": "example", "package": "example",
                         "path": "crates/example", "documentation": "crates/example/README.md",
                         "status": "candidate_source_only"}]}
        self.write("Cargo.toml", '[workspace]\nmembers = ["crates/example"]\n')
        self.write("crates/example/Cargo.toml", '[package]\nname = "example"\nversion = "0.1.0"\n')
        self.write("crates/example/README.md", "# Example source-only module\n")
        self.save_registry()
        self.write(INDEX.INDEX, INDEX.render(self.root))

    def write(self, relative: str, text: str) -> None:
        destination = self.root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(text, encoding="utf-8")

    def save_registry(self) -> None:
        self.write(INDEX.REGISTRY, json.dumps(self.registry))

    def refused(self) -> None:
        self.assertTrue(INDEX.validate(self.root))

    def test_current_projection_is_deterministic(self) -> None:
        self.assertEqual(INDEX.validate(self.root), [])
        self.assertEqual(INDEX.render(self.root), INDEX.render(self.root))

    def test_status_change_requires_regeneration(self) -> None:
        self.registry["modules"][0]["status"] = "candidate_new_source"
        self.save_registry()
        self.refused()
        self.write(INDEX.INDEX, INDEX.render(self.root))
        self.assertEqual(INDEX.validate(self.root), [])

    def test_extra_and_missing_rows_fail(self) -> None:
        for text in (INDEX.render(self.root) + "| forged | row | pass |\n", INDEX.HEADER + INDEX.FOOTER):
            with self.subTest(text=text[-50:]):
                self.write(INDEX.INDEX, text)
                self.refused()

    def test_missing_index_fails(self) -> None:
        (self.root / INDEX.INDEX).unlink()
        self.refused()

    def test_duplicate_json_member_fails(self) -> None:
        self.write(INDEX.REGISTRY, '{"schema":"x","schema":"y"}')
        self.refused()

    def test_unknown_envelope_field_fails(self) -> None:
        self.registry["unreviewed"] = True
        self.save_registry()
        self.refused()

    def test_workspace_drift_fails(self) -> None:
        self.write("Cargo.toml", '[workspace]\nmembers = ["crates/other"]\n')
        self.refused()

    def test_package_identity_drift_fails(self) -> None:
        self.write("crates/example/Cargo.toml", '[package]\nname = "other"\n')
        self.refused()

    def test_duplicate_module_fails(self) -> None:
        self.registry["modules"].append(dict(self.registry["modules"][0]))
        self.save_registry()
        self.write("Cargo.toml", '[workspace]\nmembers = ["crates/example", "crates/example"]\n')
        self.refused()

    def test_path_traversal_fails(self) -> None:
        self.registry["modules"][0]["path"] = "crates/../example"
        self.save_registry()
        self.refused()

    def test_markdown_injection_fails(self) -> None:
        for value in ("candidate|released", "candidate\n# released", "<b>released</b>"):
            with self.subTest(value=value):
                self.registry["modules"][0]["status"] = value
                self.save_registry()
                self.refused()

    def test_non_json_numbers_fail(self) -> None:
        for value in ("NaN", "Infinity", "1.5"):
            with self.subTest(value=value):
                self.write(INDEX.REGISTRY, json.dumps(self.registry).replace('"policy": {}', f'"policy": {value}'))
                self.refused()

    def test_readme_symlink_fails(self) -> None:
        path = self.root / "crates/example/README.md"
        path.unlink()
        path.symlink_to(self.root / "Cargo.toml")
        self.refused()

    def test_index_symlink_fails(self) -> None:
        path = self.root / INDEX.INDEX
        path.unlink()
        path.symlink_to(self.root / "Cargo.toml")
        self.refused()

    def test_registry_symlink_fails(self) -> None:
        path = self.root / INDEX.REGISTRY
        path.unlink()
        path.symlink_to(self.root / "Cargo.toml")
        self.refused()

    def test_parent_symlink_fails(self) -> None:
        (self.root / "crates").rename(self.root / "actual-crates")
        (self.root / "crates").symlink_to(self.root / "actual-crates", target_is_directory=True)
        self.refused()

    def test_oversized_input_fails(self) -> None:
        self.write(INDEX.REGISTRY, " " * (INDEX.LIMIT + 1))
        self.refused()

    def test_invalid_utf8_fails(self) -> None:
        (self.root / INDEX.REGISTRY).write_bytes(b"\xff")
        self.refused()


if __name__ == "__main__":
    unittest.main()
