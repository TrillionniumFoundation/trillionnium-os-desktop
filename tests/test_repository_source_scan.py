from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
SPEC = importlib.util.spec_from_file_location(
    "repository_source_scan_under_test", ROOT / "tools/_validate_repository_impl.py"
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class RepositorySourceScanTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.root_patch = patch.object(VALIDATOR, "ROOT", self.root)
        self.root_patch.start()
        VALIDATOR.ERRORS.clear()

    def tearDown(self):
        self.root_patch.stop()
        self.temporary.cleanup()

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_build_and_git_metadata_cannot_pollute_source_inventory(self):
        self.write("contracts/product.json", '{"schema":"product"}')
        self.write("new-module/input.json", '{"schema":"new"}')
        for directory in (".git", "target", ".cache", "build", "out", "evidence/local"):
            self.write(f"{directory}/broken.json", "invalid generated JSON")
            (self.root / directory / "generated-link").symlink_to("missing")
        self.assertEqual(
            [str(path.relative_to(self.root)) for path in VALIDATOR.source_paths() if path.is_file()],
            ["contracts/product.json", "new-module/input.json"],
        )

    def test_generated_directory_names_inside_product_source_are_still_checked(self):
        path = self.write("apps/build/contract.json", '{"a":1,"a":2}')
        self.assertIn(path, list(VALIDATOR.source_paths()))
        self.assertEqual(VALIDATOR.load_json(path), {})
        self.assertIn("duplicate", VALIDATOR.ERRORS[-1])

    def test_duplicate_non_finite_and_invalid_utf8_are_rejected(self):
        for text in ('{"enabled":false,"enabled":true}', '{"n":NaN}', '{"n":1e999}'):
            with self.subTest(text=text):
                path = self.write("contracts/hostile.json", text)
                self.assertEqual(VALIDATOR.load_json(path), {})
                self.assertTrue(VALIDATOR.ERRORS)
                VALIDATOR.ERRORS.clear()
        path.write_bytes(b"\xff")
        self.assertEqual(VALIDATOR.load_json(path), {})
        self.assertTrue(VALIDATOR.ERRORS)

    def test_size_bound_is_applied_before_decoding(self):
        path = self.write("contracts/oversized.json", " " * 65)
        with patch.object(VALIDATOR, "MAX_JSON_BYTES", 64):
            self.assertEqual(VALIDATOR.load_json(path), {})
        self.assertIn("exceeds", VALIDATOR.ERRORS[-1])

    def test_parent_symlink_and_non_regular_json_cannot_be_read(self):
        with tempfile.TemporaryDirectory() as external:
            outside = Path(external)
            (outside / "data.json").write_text('{"escaped":true}')
            (self.root / "contracts").symlink_to(outside, target_is_directory=True)
            self.assertEqual(VALIDATOR.load_json(self.root / "contracts/data.json"), {})
            self.assertIn("symlinked", VALIDATOR.ERRORS[-1])
        path = self.root / "directory.json"
        path.mkdir()
        self.assertEqual(VALIDATOR.load_json(path), {})
        self.assertTrue(VALIDATOR.ERRORS)

    def test_source_symlink_is_reported_without_traversing_its_target(self):
        with tempfile.TemporaryDirectory() as external:
            outside = Path(external)
            (outside / "not-source.json").write_text("invalid")
            (self.root / "apps").symlink_to(outside, target_is_directory=True)
            self.assertNotIn(self.root / "apps/not-source.json", list(VALIDATOR.source_paths()))
            with patch.object(VALIDATOR, "REQUIRED_PATHS", []):
                VALIDATOR.check_filesystem_shape()
            self.assertTrue(any("symlinks are forbidden" in error for error in VALIDATOR.ERRORS))


if __name__ == "__main__":
    unittest.main()
