from __future__ import annotations

import importlib.util
import json
import shutil
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "validate_s08_servo_runtime.py"
SPEC = importlib.util.spec_from_file_location("validate_s08_servo_runtime", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


class S08ServoRuntimeContractTests(unittest.TestCase):
    def test_current_tree_passes(self) -> None:
        self.assertEqual(VALIDATOR.validate(ROOT), [])

    def copied_tree(self) -> tuple[tempfile.TemporaryDirectory[str], Path]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name) / "repository"
        shutil.copytree(ROOT, root, symlinks=True)
        return temporary, root

    def test_contract_cannot_promote_installed_image(self) -> None:
        temporary, root = self.copied_tree()
        self.addCleanup(temporary.cleanup)
        path = root / "contracts/s08-servo-runtime-bridge.v1.json"
        value = json.loads(path.read_text(encoding="utf-8"))
        value["non_claims"]["installed_debian_image"] = True
        path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
        errors = VALIDATOR.validate(root)
        self.assertTrue(
            any("installed_debian_image" in error for error in errors), errors
        )

    def test_generic_or_fixture_runtime_substitution_fails(self) -> None:
        temporary, root = self.copied_tree()
        self.addCleanup(temporary.cleanup)
        path = root / "crates/hepta-browser-actor/src/servo_runtime.rs"
        path.write_text(
            path.read_text(encoding="utf-8")
            + "\n// DeterministicLocalRuntime\nimpl BrowserRequestHandler for ServoBrowserActor {}\n",
            encoding="utf-8",
        )
        errors = VALIDATOR.validate(root)
        self.assertTrue(
            any("BrowserRequestHandler" in error for error in errors), errors
        )

    def test_real_servo_action_marker_is_mandatory(self) -> None:
        temporary, root = self.copied_tree()
        self.addCleanup(temporary.cleanup)
        path = root / "experiments/servo-s08-runtime/accessibility_server.rs"
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "AccessibilityActionResult::Dispatched",
                "AccessibilityActionResult::UnsupportedAction",
            ),
            encoding="utf-8",
        )
        errors = VALIDATOR.validate(root)
        self.assertTrue(
            any("AccessibilityActionResult::Dispatched" in error for error in errors),
            errors,
        )

    def test_workflow_mutation_authority_is_rejected(self) -> None:
        temporary, root = self.copied_tree()
        self.addCleanup(temporary.cleanup)
        path = root / ".github/workflows/s08-servo-vertical-slice.yml"
        path.write_text(
            path.read_text(encoding="utf-8") + "\n# git push is forbidden\n",
            encoding="utf-8",
        )
        errors = VALIDATOR.validate(root)
        self.assertTrue(any("git push" in error for error in errors), errors)

    def test_duplicate_contract_member_is_rejected(self) -> None:
        temporary, root = self.copied_tree()
        self.addCleanup(temporary.cleanup)
        path = root / "contracts/s08-servo-runtime-bridge.v1.json"
        text = path.read_text(encoding="utf-8")
        path.write_text(
            text.replace(
                '  "schema": "trillionnium.desktop.s08-servo-runtime-bridge.v1",',
                '  "schema": "trillionnium.desktop.s08-servo-runtime-bridge.v1",\n'
                '  "schema": "duplicate",',
                1,
            ),
            encoding="utf-8",
        )
        errors = VALIDATOR.validate(root)
        self.assertTrue(any("duplicate JSON member" in error for error in errors), errors)


if __name__ == "__main__":
    unittest.main()
