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

    def first_readme(self) -> Path:
        return self.root / self.registry()["modules"][0]["documentation"]

    def test_current_repository_passes(self) -> None:
        self.assertEqual(VALIDATOR.validate(ROOT), [])

    def test_missing_required_section_fails(self) -> None:
        readme = self.first_readme()
        text = readme.read_text()
        readme.write_text(text.replace("## Security invariants", "## Security notes", 1))
        errors = self.validate()
        self.assertTrue(any("Security invariants" in error for error in errors), errors)

    def test_stale_status_projection_fails(self) -> None:
        readme = self.first_readme()
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
        readme = self.first_readme()
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

    def test_html_commented_document_is_not_visible_documentation(self) -> None:
        readme = self.first_readme()
        readme.write_text("<!--\n" + readme.read_text() + "\n-->\n", encoding="utf-8")
        errors = self.validate()
        self.assertTrue(any("visible level-2 heading" in error for error in errors), errors)

    def test_fenced_document_is_not_visible_documentation(self) -> None:
        readme = self.first_readme()
        readme.write_text(
            "```markdown\n" + readme.read_text() + "\n```\n", encoding="utf-8"
        )
        errors = self.validate()
        self.assertTrue(any("visible level-2 heading" in error for error in errors), errors)

    def test_empty_sections_with_unrelated_padding_fail(self) -> None:
        registry = self.registry()
        entry = registry["modules"][0]
        readme = self.first_readme()
        lines = ["# module", ""]
        for section in VALIDATOR.REQUIRED_SECTIONS:
            lines.extend([section, ""])
            if section == "## Status and claim ceiling":
                lines.extend(
                    [
                        f"Status: `{entry['status']}`  ",
                        f"Claim ceiling: `{entry['claim_ceiling']}`",
                        "",
                    ]
                )
        lines.append("Unrelated padding. " * 500)
        readme.write_text("\n".join(lines), encoding="utf-8")
        errors = self.validate()
        self.assertTrue(any("not substantive" in error for error in errors), errors)

    def test_required_heading_at_wrong_level_fails(self) -> None:
        readme = self.first_readme()
        readme.write_text(
            readme.read_text().replace(
                "## Security invariants", "### Security invariants", 1
            ),
            encoding="utf-8",
        )
        errors = self.validate()
        self.assertTrue(any("visible level-2 heading" in error for error in errors), errors)

    def test_commented_makefile_and_ci_mentions_are_not_execution(self) -> None:
        makefile = self.root / "Makefile"
        makefile.write_text(
            makefile.read_text().replace(
                "\t/usr/bin/python3 -I tools/validate_module_documentation.py",
                "\t# /usr/bin/python3 -I tools/validate_module_documentation.py\n\t@echo skipped",
            ),
            encoding="utf-8",
        )
        ci_path = self.root / ".github/workflows/ci.yml"
        ci_path.write_text(
            ci_path.read_text().replace(
                "        run: /usr/bin/python3 -I tools/validate_module_documentation.py",
                "        run: |\n"
                "          # /usr/bin/python3 -I tools/validate_module_documentation.py\n"
                "          printf 'skipped\\n'",
            ),
            encoding="utf-8",
        )
        errors = self.validate()
        self.assertTrue(any("Makefile validate target" in error for error in errors), errors)
        self.assertTrue(any("CI job" in error for error in errors), errors)

    def test_constant_false_ci_job_is_not_execution(self) -> None:
        ci_path = self.root / ".github/workflows/ci.yml"
        ci_path.write_text(
            ci_path.read_text().replace(
                "  repository-contracts:\n",
                "  repository-contracts:\n    if: false\n",
                1,
            ),
            encoding="utf-8",
        )
        errors = self.validate()
        self.assertTrue(any("repository-contracts" in error for error in errors), errors)

    def test_symlinked_conventional_binary_directory_fails(self) -> None:
        registry = self.registry()
        module = self.root / registry["modules"][0]["path"]
        outside = self.root / "outside-bin"
        outside.mkdir()
        (outside / "hidden.rs").write_text("fn main() {}\n", encoding="utf-8")
        target = module / "src/bin"
        if target.exists():
            shutil.rmtree(target)
        try:
            target.symlink_to(outside, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks unavailable")
        errors = self.validate()
        self.assertTrue(any("binary directory is a symlink" in error for error in errors), errors)

    def test_non_json_and_floating_policy_numbers_fail(self) -> None:
        path = self.root / "manifests/modules.v1.json"
        original = path.read_text()
        path.write_text(original.replace("3000", "NaN", 1), encoding="utf-8")
        errors = self.validate()
        self.assertTrue(any("non-JSON numeric constant" in error for error in errors), errors)
        path.write_text(original.replace("3000", "3000.0", 1), encoding="utf-8")
        errors = self.validate()
        self.assertTrue(any("floating-point value" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
