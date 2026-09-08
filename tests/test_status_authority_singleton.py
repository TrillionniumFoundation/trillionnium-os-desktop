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
SPEC = importlib.util.spec_from_file_location("validate_status_authority_singleton", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class StatusAuthoritySingletonTests(unittest.TestCase):
    def make_root(self) -> Path:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        for relative in MODULE.ACTIVE_AUTHORITY_PATHS:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            content = MODULE.PROJECTION_MARKER + "\n" if relative == "docs/CURRENT_STATE.md" else "stub\n"
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

    def test_missing_active_authority_is_rejected(self) -> None:
        root = self.make_root()
        missing = root / MODULE.ACTIVE_AUTHORITY_PATHS[0]
        missing.unlink()
        self.assertIn(
            f"active status authority path must be a regular file: {MODULE.ACTIVE_AUTHORITY_PATHS[0]}",
            MODULE.validate(root),
        )

    def test_projection_must_name_the_sole_authority(self) -> None:
        root = self.make_root()
        (root / "docs/CURRENT_STATE.md").write_text(
            "<!-- generated from another model -->\n", encoding="utf-8"
        )
        self.assertTrue(
            any("sole generated authority" in error for error in MODULE.validate(root))
        )


if __name__ == "__main__":
    unittest.main()
