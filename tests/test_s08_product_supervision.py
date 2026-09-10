from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_s08_product_supervision",
    ROOT / "tools/validate_s08_product_supervision.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)

REQUIRED = (
    "apps/hepta-browserd/Cargo.toml",
    "apps/hepta-browserd/src/lib.rs",
    "apps/hepta-browserd/src/servo_product_runtime.rs",
    "docs/architecture/S08_PRODUCT_SERVO_SUPERVISION.md",
    ".github/workflows/s08-product-servo-runtime.yml",
)


class S08ProductSupervisionValidationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for relative in REQUIRED:
            source = ROOT / relative
            target = self.root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def errors(self) -> list[str]:
        return VALIDATOR.validate(self.root)

    def rewrite(self, relative: str, old: str, new: str) -> None:
        path = self.root / relative
        text = path.read_text(encoding="utf-8")
        self.assertIn(old, text)
        path.write_text(text.replace(old, new, 1), encoding="utf-8")

    def test_pristine_fixture_passes(self) -> None:
        self.assertEqual(self.errors(), [])

    def test_commented_module_declaration_is_rejected(self) -> None:
        self.rewrite(
            "apps/hepta-browserd/src/lib.rs",
            "mod servo_product_runtime;",
            "// mod servo_product_runtime;",
        )
        self.assertTrue(any("module declaration" in error for error in self.errors()))

    def test_optional_actor_dependency_is_rejected(self) -> None:
        self.rewrite(
            "apps/hepta-browserd/Cargo.toml",
            'hepta-browser-actor = { path = "../../crates/hepta-browser-actor" }',
            'hepta-browser-actor = { path = "../../crates/hepta-browser-actor", optional = true }',
        )
        self.assertTrue(any("must not be optional" in error for error in self.errors()))

    def test_wrapping_generation_is_rejected(self) -> None:
        self.rewrite(
            "apps/hepta-browserd/src/servo_product_runtime.rs",
            ".checked_add(1)",
            ".wrapping_add(1)",
        )
        errors = self.errors()
        self.assertTrue(any("checked arithmetic" in error for error in errors))

    def test_implicit_reconstruction_in_crash_path_is_rejected(self) -> None:
        self.rewrite(
            "apps/hepta-browserd/src/servo_product_runtime.rs",
            "let previous = self.generation;",
            "let _forbidden = &self.factory;\n        let previous = self.generation;",
        )
        self.assertTrue(any("must not reconstruct" in error for error in self.errors()))

    def test_duplicate_dispatch_is_rejected(self) -> None:
        self.rewrite(
            "apps/hepta-browserd/src/servo_product_runtime.rs",
            "match operation(actor) {",
            "let _ = operation(actor);\n        match operation(actor) {",
        )
        self.assertTrue(any("exactly once" in error for error in self.errors()))

    def test_hidden_document_and_write_capable_gate_are_rejected(self) -> None:
        doc = self.root / "docs/architecture/S08_PRODUCT_SERVO_SUPERVISION.md"
        doc.write_text(f"<!--\n{doc.read_text(encoding='utf-8')}\n-->\n", encoding="utf-8")
        workflow = self.root / ".github/workflows/s08-product-servo-runtime.yml"
        workflow.write_text(
            workflow.read_text(encoding="utf-8").replace("contents: read", "contents: write"),
            encoding="utf-8",
        )
        errors = self.errors()
        self.assertTrue(any("normative headings" in error for error in errors))
        self.assertTrue(any("read-only" in error for error in errors))

    def test_temporary_workflow_is_rejected(self) -> None:
        path = self.root / ".github/workflows/temporary-s08-decoy.yml"
        path.write_text("name: decoy\n", encoding="utf-8")
        self.assertTrue(any("temporary S08 workflows" in error for error in self.errors()))


if __name__ == "__main__":
    unittest.main()
