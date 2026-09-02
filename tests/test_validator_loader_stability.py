from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ValidatorLoaderStabilityTests(unittest.TestCase):
    def test_project_truth_facade_never_rewrites_or_executes_source(self) -> None:
        text = (ROOT / "tools/validate_project_truth.py").read_text(encoding="utf-8")
        for forbidden in ("exec(", "compile(", "_source.replace(", ".read_text(encoding=\"utf-8\")"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

    def test_project_truth_test_facade_never_rewrites_or_executes_source(self) -> None:
        text = (ROOT / "tests/test_validate_project_truth.py").read_text(encoding="utf-8")
        for forbidden in ("exec(", "compile(", "_source.replace("):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

    def test_d3_profile_facade_never_rewrites_or_executes_source(self) -> None:
        text = (ROOT / "tools/validate_d3_development_profile.py").read_text(
            encoding="utf-8"
        )
        for forbidden in ("exec(", "compile(", "_PARTS", ".part", "b\"\".join"):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, text)

    def test_d3_profile_implementation_is_one_reviewed_module(self) -> None:
        implementation = ROOT / "tools/_validate_d3_development_profile_impl.py"
        self.assertTrue(implementation.is_file())
        self.assertFalse(
            list(ROOT.glob("tools/_validate_d3_development_profile_impl.*.part"))
        )
        workflow = (
            ROOT / ".github/workflows/d3-integrated-runtime-evidence.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            '"tools/_validate_d3_development_profile_impl.py"', workflow
        )
        self.assertIn(
            "python3 tools/validate_d3_development_profile.py", workflow
        )

    def test_facade_exports_explicit_pr60_policy(self) -> None:
        path = ROOT / "tools/validate_project_truth.py"
        spec = importlib.util.spec_from_file_location("validator_loader_test", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.D0A02_SUPERSEDED_BY_PR, 60)
        self.assertIn("PR #60 supersedes", module.D0A02_STALE_REASON)


if __name__ == "__main__":
    unittest.main()
