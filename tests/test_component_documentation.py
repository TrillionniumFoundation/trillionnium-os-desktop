from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

VALIDATOR_PATH = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "validate_component_documentation.py"
)
SPEC = importlib.util.spec_from_file_location(
    "component_documentation_validator", VALIDATOR_PATH
)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot import {VALIDATOR_PATH}")
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class ComponentDocumentationValidatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for directory in (
            "manifests",
            "docs/components",
            "docs/architecture",
            ".github/workflows",
            "contracts",
            "tests",
            "tools",
        ):
            (self.root / directory).mkdir(parents=True, exist_ok=True)

        (self.root / "tools/main.py").write_text(
            "def main() -> int:\n    return 0\n",
            encoding="utf-8",
        )
        (self.root / "docs/architecture/TOOLS.md").write_text(
            "# Tool architecture\n", encoding="utf-8"
        )
        (self.root / "contracts/tool.v1.json").write_text(
            "{}\n", encoding="utf-8"
        )
        (self.root / "tests/test_tool.py").write_text(
            "def test_tool():\n    assert True\n", encoding="utf-8"
        )
        (self.root / ".github/workflows/tool.yml").write_text(
            "name: tool\n", encoding="utf-8"
        )

        body = [
            "# Validation toolchain",
            "",
            "**Component registry ID:** `validation-toolchain`  ",
            "**Component path:** `tools`  ",
            "**Owner class:** `repository-maintainers`  ",
            "",
            "The machine registry is `manifests/components.v1.json`.",
            "",
        ]
        for heading in VALIDATOR.REQUIRED_SECTIONS:
            body.extend(
                [
                    heading,
                    "",
                    (
                        "Detailed bounded component information covering interfaces, "
                        "authority, validation, failure handling, and operations. "
                    )
                    * 18,
                    "",
                ]
            )
            if heading == "## Status and claim ceiling":
                body.extend([
                    "Current status: `source_policy_active`.",
                    "**Claim ceiling:** source validation only.",
                    "",
                ])
        (self.root / "tools/README.md").write_text(
            "\n".join(body), encoding="utf-8"
        )

        registry = {
            "schema": VALIDATOR.EXPECTED_SCHEMA,
            "plan_revision": VALIDATOR.EXPECTED_PLAN_REVISION,
            "policy": {
                "non_cargo_components_must_match_discovery": True,
                "component_documentation_required": True,
                "minimum_documentation_bytes": VALIDATOR.MINIMUM_DOCUMENTATION_BYTES,
                "required_sections": list(VALIDATOR.REQUIRED_SECTIONS),
                "references_must_exist": True,
                "symlink_paths_forbidden": True,
                "security_invariants_required": True,
                "lower_tier_never_implies_higher_tier": True,
                "cargo_workspace_members_are_governed_by": "manifests/modules.v1.json",
                "top_level_control_files_are_governed_by": "tools/validate_repository.py",
            },
            "components": [
                {
                    "id": "validation-toolchain",
                    "path": "tools",
                    "kind": "toolchain",
                    "status": "source_policy_active",
                    "claim_ceiling": "source validation only",
                    "owner_class": "repository-maintainers",
                    "documentation": "tools/README.md",
                    "architecture": ["docs/architecture/TOOLS.md"],
                    "contracts": ["contracts/tool.v1.json"],
                    "tests": ["tests/test_tool.py"],
                    "workflows": [".github/workflows/tool.yml"],
                    "entrypoints": ["tools/main.py"],
                    "security_invariants": [
                        "Inputs are treated as data and never executed.",
                        "Missing evidence fails closed.",
                    ],
                }
            ],
        }
        (self.root / "manifests/components.v1.json").write_text(
            json.dumps(registry, indent=2) + "\n", encoding="utf-8"
        )
        (self.root / "docs/components/README.md").write_text(
            "# Components\n\n"
            "Registry: `manifests/components.v1.json`.\n\n"
            "`validation-toolchain` — `tools/README.md`.\n",
            encoding="utf-8",
        )

        command = "python3 tools/validate_component_documentation.py\n"
        (self.root / "Makefile").write_text(command, encoding="utf-8")
        (self.root / ".github/workflows/ci.yml").write_text(
            command, encoding="utf-8"
        )
        (self.root / "CONTRIBUTING.md").write_text(
            "Run validate_component_documentation.py.\n", encoding="utf-8"
        )
        (self.root / "README.md").write_text(command, encoding="utf-8")
        (self.root / "docs/README.md").write_text(
            "See [components](components/README.md).\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def validate(self) -> list[str]:
        return VALIDATOR.validate(self.root, expected_paths={"tools"})

    def load_registry(self) -> dict:
        return json.loads(
            (self.root / "manifests/components.v1.json").read_text(
                encoding="utf-8"
            )
        )

    def save_registry(self, registry: dict) -> None:
        (self.root / "manifests/components.v1.json").write_text(
            json.dumps(registry, indent=2) + "\n", encoding="utf-8"
        )

    def test_valid_fixture_passes(self) -> None:
        self.assertEqual(self.validate(), [])

    def test_missing_documentation_fails(self) -> None:
        (self.root / "tools/README.md").unlink()
        errors = self.validate()
        self.assertTrue(
            any("documentation is unavailable" in error for error in errors), errors
        )

    def test_missing_required_section_fails(self) -> None:
        path = self.root / "tools/README.md"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "## Security invariants", "## Security notes"
            ),
            encoding="utf-8",
        )
        errors = self.validate()
        self.assertTrue(any("Security invariants" in error for error in errors), errors)

    def test_discovery_registry_drift_fails(self) -> None:
        registry = self.load_registry()
        registry["components"][0]["path"] = "renamed-tools"
        registry["components"][0]["documentation"] = "renamed-tools/README.md"
        self.save_registry(registry)
        errors = self.validate()
        self.assertTrue(
            any("must exactly match non-Cargo discovery order" in error for error in errors),
            errors,
        )

    def test_duplicate_json_member_fails(self) -> None:
        path = self.root / "manifests/components.v1.json"
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace(
                f'"schema": "{VALIDATOR.EXPECTED_SCHEMA}",',
                f'"schema": "{VALIDATOR.EXPECTED_SCHEMA}",\n'
                f'  "schema": "{VALIDATOR.EXPECTED_SCHEMA}",',
                1,
            ),
            encoding="utf-8",
        )
        errors = self.validate()
        self.assertTrue(any("duplicate JSON member" in error for error in errors), errors)

    def test_symlinked_documentation_fails(self) -> None:
        readme = self.root / "tools/README.md"
        target = self.root / "tools/README.real.md"
        readme.rename(target)
        try:
            readme.symlink_to(target.name)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable on this platform")
        errors = self.validate()
        self.assertTrue(any("traverses a symlink" in error for error in errors), errors)

    def test_missing_reference_fails(self) -> None:
        registry = self.load_registry()
        registry["components"][0]["contracts"] = ["contracts/missing.v1.json"]
        self.save_registry(registry)
        errors = self.validate()
        self.assertTrue(any("contracts[0] is unavailable" in error for error in errors), errors)

    def test_short_documentation_fails(self) -> None:
        (self.root / "tools/README.md").write_text(
            "# Too short\n", encoding="utf-8"
        )
        errors = self.validate()
        self.assertTrue(any("documentation is too short" in error for error in errors), errors)

    def test_unknown_component_field_fails(self) -> None:
        registry = self.load_registry()
        registry["components"][0]["unreviewed_escape_hatch"] = True
        self.save_registry(registry)
        errors = self.validate()
        self.assertTrue(any("unknown fields" in error for error in errors), errors)

    def test_too_few_security_invariants_fails(self) -> None:
        registry = self.load_registry()
        registry["components"][0]["security_invariants"] = ["Fail closed."]
        self.save_registry(registry)
        errors = self.validate()
        self.assertTrue(
            any("security_invariants must contain at least 2" in error for error in errors),
            errors,
        )


if __name__ == "__main__":
    unittest.main()
