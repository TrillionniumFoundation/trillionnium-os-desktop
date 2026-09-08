from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "tools"
    / "validate_status_authority_singleton.py"
)
SPEC = importlib.util.spec_from_file_location(
    "validate_status_authority_singleton",
    MODULE_PATH,
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class StatusAuthoritySingletonTests(unittest.TestCase):
    def make_root(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for relative in (*MODULE.ACTIVE_AUTHORITY_PATHS, *MODULE.REQUIRED_SUPPORT_PATHS):
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            if relative == "docs/CURRENT_STATE.md":
                content = MODULE.PROJECTION_MARKER + "\n"
            elif relative == "tools/non_status_project_truth.py":
                content = (
                    '"""Import-only non-status library."""\n'
                    "def validate_non_status_repository(root):\n"
                    "    return []\n"
                )
            elif relative == "tools/validate_project_truth.py":
                content = (
                    'TOOLS / "non_status_project_truth.py"\n'
                    "def main():\n"
                    "    return 0\n"
                )
            else:
                content = "stub = True\n"
            path.write_text(content, encoding="utf-8")
        return root

    def test_single_active_authority_passes(self) -> None:
        self.assertEqual(MODULE.validate(self.make_root()), [])

    def test_each_retired_authority_path_is_rejected(self) -> None:
        for relative in MODULE.RETIRED_AUTHORITY_PATHS:
            with self.subTest(relative=relative):
                root = self.make_root()
                path = root / relative
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("retired\n", encoding="utf-8")
                self.assertIn(
                    f"retired status authority must be absent: {relative}",
                    MODULE.validate(root),
                )

    def test_missing_active_or_support_path_is_rejected(self) -> None:
        root = self.make_root()
        missing = root / MODULE.ACTIVE_AUTHORITY_PATHS[0]
        missing.unlink()
        self.assertTrue(
            any(
                MODULE.ACTIVE_AUTHORITY_PATHS[0] in error and "regular file" in error
                for error in MODULE.validate(root)
            )
        )

        root = self.make_root()
        missing = root / MODULE.REQUIRED_SUPPORT_PATHS[0]
        missing.unlink()
        self.assertTrue(
            any(
                MODULE.REQUIRED_SUPPORT_PATHS[0] in error and "regular file" in error
                for error in MODULE.validate(root)
            )
        )

    def test_projection_must_name_the_sole_authority(self) -> None:
        root = self.make_root()
        (root / "docs/CURRENT_STATE.md").write_text(
            "<!-- generated from another model -->\n",
            encoding="utf-8",
        )
        self.assertTrue(
            any("sole generated authority" in error for error in MODULE.validate(root))
        )

    def test_exact_retired_base_validator_regression_is_rejected(self) -> None:
        root = self.make_root()
        path = root / "tools/_validate_project_truth_base.py"
        path.write_text(
            "#!/usr/bin/env python3\n"
            "def status_projection_errors(project, registry, documents):\n"
            "    return []\n"
            "def check_status_documents(project):\n"
            "    return None\n"
            "if __name__ == '__main__':\n"
            "    raise SystemExit(0)\n",
            encoding="utf-8",
        )
        errors = MODULE.validate(root)
        self.assertTrue(any(str(path.relative_to(root)) in error for error in errors))

    def test_importable_rogue_status_validator_is_rejected(self) -> None:
        root = self.make_root()
        path = root / "tools/rogue_status.py"
        path.write_text(
            "STATUS_REGISTRY_PATH = 'docs/other-status.json'\n"
            "def status_projection_errors(project, registry, documents):\n"
            "    return []\n",
            encoding="utf-8",
        )
        errors = MODULE.validate(root)
        self.assertTrue(any("competing status semantics" in error for error in errors))

    def test_non_status_library_cannot_reintroduce_status_semantics(self) -> None:
        root = self.make_root()
        path = root / "tools/non_status_project_truth.py"
        path.write_text(
            "#!/usr/bin/env python3\n"
            "STATUS_REGISTRY_PATH = 'docs/status-documents.v1.json'\n"
            "def status_projection_errors(project, registry, documents):\n"
            "    return []\n"
            "if __name__ == '__main__':\n"
            "    raise SystemExit(0)\n",
            encoding="utf-8",
        )
        errors = MODULE.validate(root)
        self.assertTrue(any("must not be executable" in error for error in errors))
        self.assertTrue(any("must not have a __main__ path" in error for error in errors))
        self.assertTrue(any("integrated-status semantics" in error for error in errors))

    def test_wrapper_cannot_monkey_patch_retired_status_logic(self) -> None:
        root = self.make_root()
        path = root / "tools/validate_project_truth.py"
        path.write_text(
            'TOOLS / "_validate_project_truth_base.py"\n'
            "_BASE.check_status_documents = lambda project: None\n",
            encoding="utf-8",
        )
        errors = MODULE.validate(root)
        self.assertTrue(any("retired status delegation" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
