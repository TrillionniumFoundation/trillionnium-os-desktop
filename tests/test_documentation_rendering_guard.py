"""Hostile rendered-authority regressions for both documentation validators."""
from __future__ import annotations

import unittest

from tests import test_documentation_claim_projection as projection_tests


ATTACKS = (
    "<strong>Current status</strong>: `production_ready`",
    '<span class="authority">Currrent status</span>: `production_ready`',
    "<div>Claim ceiling</div>: production release ready.",
    "&lt;strong&gt;Claim cieling&lt;/strong&gt;: production release ready.",
    "Cur<!-- hidden -->rrent status: `production_ready`",
    "Cur<!-- hidden --!>rrent status: `production_ready`",
    '<bdo dir="rtl">sutats tnerruC</bdo>: `production_ready`',
    '<span style="display:none">not</span>Current status: `production_ready`',
    "\u009b[8Cstatus\u009b[14DCurrent \u009b[6C: `production_ready`",
    "\u009d2;Current status\u009c: `production_ready`",
    "\u034f" * 300 + "Claim cieling: production release ready.",
    "<" + ("x" * 5000) + ">Current status</" + ("x" * 5000) + ">: `production_ready`",
    "<a" * 5000 + "Current status: `production_ready`",
    "\u200b" * 300 + "Currrent status: `production_ready`",
    "Currrent sta\ntus: `production_ready`",
)

SAFE_PROSE = (
    "Current statistics: source-only explanatory prose.",
    "Status quo: unchanged.",
    "The current state of the prototype: unchanged.",
    "Claim estimates: explanatory prose.",
    "The ratio a∶b remains illustrative.",
    "\u2067مرحبا بالعالم\u2069: نص توضيحي عادي.",
    "מצב המערכת: טקסט הסברי רגיל.",
    "The current\nstate of the prototype: unchanged.",
    "<strong>Status quo</strong>: unchanged.",
    "<em>The current state of the prototype</em>: unchanged.",
    "\u200b" * 300 + "Current statistics: source-only explanatory prose.",
)


class DocumentationRenderingGuardTests(unittest.TestCase):
    def test_attacks_fail_both_real_validator_entrypoints(self) -> None:
        for kind in ("module", "component"):
            for declaration in ATTACKS:
                with self.subTest(kind=kind, declaration=declaration[:80]):
                    with projection_tests.fixture_for(kind) as (fixture, path, _, _):
                        path.write_text(path.read_text(encoding="utf-8") + "\n" + declaration + "\n", encoding="utf-8")
                        self.assertTrue(fixture.validate())

    def test_ordinary_multilingual_and_html_prose_remains_valid(self) -> None:
        for kind in ("module", "component"):
            for prose in SAFE_PROSE:
                with self.subTest(kind=kind, prose=prose[:80]):
                    with projection_tests.fixture_for(kind) as (fixture, path, _, _):
                        path.write_text(path.read_text(encoding="utf-8") + "\n" + prose + "\n", encoding="utf-8")
                        self.assertEqual(fixture.validate(), [])


if __name__ == "__main__":
    unittest.main()
