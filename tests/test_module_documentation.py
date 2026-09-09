from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_module_documentation_under_test",
    ROOT / "tools/validate_module_documentation.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class ModuleDocumentationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name) / "repository"
        shutil.copytree(ROOT, self.root, symlinks=True)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def validate(self) -> list[str]:
        return VALIDATOR.validate(self.root)

    def registry(self) -> dict:
        return json.loads((self.root / "manifests/modules.v1.json").read_text())

    def write_registry(self, value: dict) -> None:
        (self.root / "manifests/modules.v1.json").write_text(
            json.dumps(value, indent=2) + "\n", encoding="utf-8"
        )

    def test_current_repository_passes(self) -> None:
        self.assertEqual(VALIDATOR.validate(ROOT), [])

    def test_missing_required_section_fails(self) -> None:
        registry = self.registry()
        readme = self.root / registry["modules"][0]["documentation"]
        text = readme.read_text()
        readme.write_text(text.replace("## Security invariants", "## Security notes", 1))
        errors = self.validate()
        self.assertTrue(any("Security invariants" in error for error in errors), errors)

    def test_stale_status_projection_fails(self) -> None:
        registry = self.registry()
        readme = self.root / registry["modules"][0]["documentation"]
        text = readme.read_text()
        readme.write_text(text.replace("Status: `", "Status: `stale-", 1))
        errors = self.validate()
        self.assertTrue(any("status projection" in error for error in errors), errors)

    def test_workspace_registry_drift_fails(self) -> None:
        registry = self.registry()
        registry["modules"][0]["path"] = "apps/renamed"
        registry["modules"][0]["documentation"] = "apps/renamed/README.md"
        self.write_registry(registry)
        errors = self.validate()
        self.assertTrue(any("workspace order" in error for error in errors), errors)

    def test_binary_inventory_drift_fails(self) -> None:
        registry = self.registry()
        registry["modules"][0]["binaries"][0]["path"] = "src/other.rs"
        self.write_registry(registry)
        errors = self.validate()
        self.assertTrue(any("binary inventory" in error for error in errors), errors)

    def test_feature_inventory_drift_fails(self) -> None:
        registry = self.registry()
        registry["modules"][0]["features"] = ["forged"]
        self.write_registry(registry)
        errors = self.validate()
        self.assertTrue(any("features do not match" in error for error in errors), errors)

    def test_symlinked_documentation_fails(self) -> None:
        registry = self.registry()
        readme = self.root / registry["modules"][0]["documentation"]
        target = readme.with_suffix(".real.md")
        readme.rename(target)
        try:
            readme.symlink_to(target.name)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        errors = self.validate()
        self.assertTrue(any("traverses a symlink" in error for error in errors), errors)

    def test_duplicate_json_member_fails(self) -> None:
        path = self.root / "manifests/modules.v1.json"
        text = path.read_text()
        path.write_text(
            text.replace(
                '"schema": "trillionnium.desktop.modules.v1",',
                '"schema": "trillionnium.desktop.modules.v1",\n  '
                '"schema": "trillionnium.desktop.modules.v1",',
                1,
            )
        )
        errors = self.validate()
        self.assertTrue(any("duplicate JSON member" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
