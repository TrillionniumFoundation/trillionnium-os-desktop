from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

VALIDATOR_PATH = Path(__file__).resolve().parents[1] / "tools" / "validate_module_documentation.py"
SPEC = importlib.util.spec_from_file_location("module_documentation_validator", VALIDATOR_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import {VALIDATOR_PATH}")
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class ModuleDocumentationValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        (self.root / "manifests").mkdir()
        (self.root / "docs/modules").mkdir(parents=True)
        (self.root / ".github/workflows").mkdir(parents=True)
        (self.root / "crates/example/src").mkdir(parents=True)
        (self.root / "docs/architecture").mkdir(parents=True)
        (self.root / "contracts").mkdir()
        (self.root / "tests").mkdir()

        (self.root / "Cargo.toml").write_text(
            """[workspace]
members = ["crates/example"]
default-members = ["crates/example"]
resolver = "3"
""",
            encoding="utf-8",
        )
        (self.root / "crates/example/Cargo.toml").write_text(
            """[package]
name = "example"
autobins = false
build = false
version = "0.1.0"
edition = "2024"

[features]
default = []
development = []

[[bin]]
name = "exampled"
path = "src/main.rs"
required-features = ["development"]
""",
            encoding="utf-8",
        )
        (self.root / "crates/example/src/main.rs").write_text("fn main() {}\n", encoding="utf-8")
        (self.root / "crates/example/src/lib.rs").write_text(
            "#[cfg(test)] mod tests { #[test] fn works() {} }\n", encoding="utf-8"
        )
        (self.root / "docs/architecture/EXAMPLE.md").write_text("# Example\n", encoding="utf-8")
        (self.root / "contracts/example.v1.json").write_text("{}\n", encoding="utf-8")
        (self.root / "tests/test_example.py").write_text("def test_example(): pass\n", encoding="utf-8")
        (self.root / ".github/workflows/example.yml").write_text("name: example\n", encoding="utf-8")

        body = [
            "# example",
            "",
            "**Module registry ID:** `example`  ",
            "**Workspace path:** `crates/example`  ",
            "**Owner class:** `test-owner`",
            "",
            "",
            "The registry is `manifests/modules.v1.json`.",
            "",
        ]
        for heading in VALIDATOR.REQUIRED_SECTIONS:
            body.extend([heading, "", "Detailed bounded module information. " * 18, ""])
            if heading == "## Status and claim ceiling":
                body.extend([
                    "**Current status:** `source_candidate`",
                    "**Claim ceiling:** test source only.",
                    "",
                ])
        (self.root / "crates/example/README.md").write_text(
            "\n".join(body), encoding="utf-8"
        )

        registry = {
            "schema": VALIDATOR.EXPECTED_SCHEMA,
            "plan_revision": VALIDATOR.EXPECTED_PLAN_REVISION,
            "policy": {
                "workspace_members_must_match_exactly": True,
                "module_readme_required": True,
                "minimum_readme_bytes": VALIDATOR.MINIMUM_README_BYTES,
                "required_sections": list(VALIDATOR.REQUIRED_SECTIONS),
                "binary_inventory_must_match_cargo": True,
                "explicit_binary_targets_only": True,
                "build_scripts_forbidden": True,
                "feature_inventory_must_match_cargo": True,
                "references_must_exist": True,
                "symlink_paths_forbidden": True,
                "lower_tier_never_implies_higher_tier": True,
            },
            "modules": [
                {
                    "id": "example",
                    "package": "example",
                    "path": "crates/example",
                    "kind": "library",
                    "status": "source_candidate",
                    "claim_ceiling": "test source only",
                    "owner_class": "test-owner",
                    "documentation": "crates/example/README.md",
                    "architecture": ["docs/architecture/EXAMPLE.md"],
                    "contracts": ["contracts/example.v1.json"],
                    "tests": ["tests/test_example.py"],
                    "workflows": [".github/workflows/example.yml"],
                    "binaries": [
                        {
                            "name": "exampled",
                            "path": "src/main.rs",
                            "required_features": ["development"],
                        }
                    ],
                    "features": ["default", "development"],
                }
            ],
        }
        (self.root / "manifests/modules.v1.json").write_text(
            json.dumps(registry, indent=2) + "\n", encoding="utf-8"
        )
        (self.root / "docs/modules/README.md").write_text(
            "# Modules\n\n| [`example`](../../crates/example/README.md) |\n",
            encoding="utf-8",
        )
        integration_marker = "python3 tools/validate_module_documentation.py\n"
        (self.root / "Makefile").write_text(integration_marker, encoding="utf-8")
        (self.root / ".github/workflows/ci.yml").write_text(
            integration_marker, encoding="utf-8"
        )
        (self.root / "docs/README.md").write_text(
            "[modules](modules/README.md)\n", encoding="utf-8"
        )
        (self.root / "CONTRIBUTING.md").write_text(
            "Run validate_module_documentation.py.\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def validate(self) -> list[str]:
        return VALIDATOR.validate(self.root)

    def load_registry(self) -> dict:
        return json.loads(
            (self.root / "manifests/modules.v1.json").read_text(encoding="utf-8")
        )

    def save_registry(self, registry: dict) -> None:
        (self.root / "manifests/modules.v1.json").write_text(
            json.dumps(registry, indent=2) + "\n", encoding="utf-8"
        )

    def test_implicit_binary_discovery_is_disabled(self) -> None:
        path = self.root / "crates/example/Cargo.toml"
        original = path.read_text()
        for replacement in ("", "autobins = true\n"):
            with self.subTest(replacement=replacement):
                path.write_text(original.replace("autobins = false\n", replacement))
                self.assertTrue(any("autobins" in error for error in self.validate()))
        path.write_text(original)

    def test_build_script_execution_is_disabled(self) -> None:
        path = self.root / "crates/example/Cargo.toml"
        original = path.read_text()
        for replacement in ("", "build = true\n", 'build = "custom.rs"\n'):
            with self.subTest(replacement=replacement):
                path.write_text(original.replace("build = false\n", replacement))
                self.assertTrue(any("build = false" in error for error in self.validate()))
        path.write_text(original)

    def test_orphan_build_script_is_rejected(self) -> None:
        (self.root / "crates/example/build.rs").write_text("fn main() {}\n")
        self.assertTrue(any("build script" in error for error in self.validate()))

    def test_unregistered_conventional_binary_files_are_rejected(self) -> None:
        for relative in ("src/bin/orphan.rs", "src/bin/orphan/main.rs"):
            with self.subTest(relative=relative):
                path = self.root / "crates/example" / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("fn main() {}\n")
                self.assertTrue(any("unregistered conventional binary" in error for error in self.validate()))
                path.unlink()

    def test_symlinked_binary_discovery_directory_is_rejected(self) -> None:
        source = self.root / "crates/example/src"
        (source / "bin").symlink_to(source, target_is_directory=True)
        self.assertTrue(any("symlink" in error for error in self.validate()))

    def test_valid_fixture_passes(self) -> None:
        self.assertEqual(self.validate(), [])

    def test_missing_readme_fails(self) -> None:
        (self.root / "crates/example/README.md").unlink()
        errors = self.validate()
        self.assertTrue(any("documentation is unavailable" in error for error in errors), errors)

    def test_missing_required_section_fails(self) -> None:
        path = self.root / "crates/example/README.md"
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace("## Security invariants", "## Security notes"),
            encoding="utf-8",
        )
        errors = self.validate()
        self.assertTrue(any("Security invariants" in error for error in errors), errors)

    def test_workspace_registry_drift_fails(self) -> None:
        registry = self.load_registry()
        registry["modules"][0]["path"] = "crates/renamed"
        registry["modules"][0]["documentation"] = "crates/renamed/README.md"
        self.save_registry(registry)
        errors = self.validate()
        self.assertTrue(any("must exactly match Cargo workspace order" in error for error in errors), errors)

    def test_binary_inventory_drift_fails(self) -> None:
        registry = self.load_registry()
        registry["modules"][0]["binaries"][0]["required_features"] = []
        self.save_registry(registry)
        errors = self.validate()
        self.assertTrue(any("binary inventory" in error for error in errors), errors)

    def test_feature_inventory_drift_fails(self) -> None:
        registry = self.load_registry()
        registry["modules"][0]["features"] = ["default"]
        self.save_registry(registry)
        errors = self.validate()
        self.assertTrue(any("do not match Cargo" in error for error in errors), errors)

    def test_symlinked_documentation_fails(self) -> None:
        target = self.root / "crates/example/README.real.md"
        readme = self.root / "crates/example/README.md"
        readme.rename(target)
        try:
            readme.symlink_to(target.name)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable on this platform")
        errors = self.validate()
        self.assertTrue(any("traverses a symlink" in error for error in errors), errors)

    def test_duplicate_json_member_fails(self) -> None:
        registry_path = self.root / "manifests/modules.v1.json"
        text = registry_path.read_text(encoding="utf-8")
        registry_path.write_text(
            text.replace(
                '"schema": "trillionnium.desktop.modules.v1",',
                '"schema": "trillionnium.desktop.modules.v1",\n'
                '  "schema": "trillionnium.desktop.modules.v1",',
                1,
            ),
            encoding="utf-8",
        )
        errors = self.validate()
        self.assertTrue(any("duplicate JSON member" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
