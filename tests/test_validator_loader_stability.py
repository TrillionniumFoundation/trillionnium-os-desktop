from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

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

    def test_servo_evidence_facade_loads_without_ambient_tools_path(self) -> None:
        path = ROOT / "tools/qualify_servo_exact_pin_evidence.py"
        tools = str(path.parent)
        clean_path = [entry for entry in sys.path if entry != tools]
        with patch.object(sys, "path", clean_path), patch.dict(
            sys.modules, {"qualify_servo_exact_pin_evidence_impl": None}
        ):
            # A ``None`` cache entry makes a bare import fail unless the facade
            # first establishes its sibling module search path. Remove it after
            # creating the module so normal import resolution can proceed.
            del sys.modules["qualify_servo_exact_pin_evidence_impl"]
            spec = importlib.util.spec_from_file_location(
                "servo_evidence_loader_isolation", path
            )
            assert spec is not None and spec.loader is not None
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        self.assertEqual(module.SERVO_PIN, "670ae8a70801b162e186f81cbb5bdd2d59c39108")

    def test_claim_projection_rejects_unicode_confusable_authority_labels(self) -> None:
        from tests import test_documentation_claim_projection as projection_tests

        declarations = (
            "**Currеnt status:** `production_ready`",  # Cyrillic e
            "**Сurrent status:** `production_ready`",  # Cyrillic Es
            "**Claim ceіling:** production release ready.",  # Cyrillic i
            "**Clаim ceιling:** production release ready.",  # Cyrillic a + Greek iota
            "**Сurrеnt stаtus:** `production_ready`",  # mixed Cyrillic label
            "**сяаιм сеιℓιηg:** production release ready.",  # cross-script skeleton
            "**Cúrrent status:** `production_ready`",  # composed accent
            "**C\u0338urrent status:** `production_ready`",  # combining overlay
            "**Currⅇnt status:** `production_ready`",  # compatibility confusable
        )
        for kind in ("module", "component"):
            for declaration in declarations:
                with self.subTest(kind=kind, declaration=declaration), projection_tests.fixture_for(kind) as (fixture, path, _, _):
                    self.assertEqual(fixture.validate(), [])
                    path.write_text(path.read_text(encoding="utf-8") + "\n" + declaration + "\n", encoding="utf-8")
                    self.assertTrue(fixture.validate(), "confusable authority declaration was accepted")

    def test_claim_projection_allows_multilingual_non_authority_prose(self) -> None:
        from tests import test_documentation_claim_projection as projection_tests

        additions = (
            "Résumé and ελληνική documentation remain ordinary prose.",
            "状态说明：本段不声明机器权威。",
            "The current lifecycle remains described without a declaration delimiter.",
        )
        for kind in ("module", "component"):
            with self.subTest(kind=kind), projection_tests.fixture_for(kind) as (fixture, path, _, _):
                path.write_text(path.read_text(encoding="utf-8") + "\n" + "\n".join(additions) + "\n", encoding="utf-8")
                self.assertEqual(fixture.validate(), [])

    def test_facade_exports_explicit_pr66_policy(self) -> None:
        path = ROOT / "tools/validate_project_truth.py"
        spec = importlib.util.spec_from_file_location("validator_loader_test", path)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.D0A02_SUPERSEDED_BY_PR, 66)
        self.assertIn("PR #66 supersedes", module.D0A02_STALE_REASON)


if __name__ == "__main__":
    unittest.main()
