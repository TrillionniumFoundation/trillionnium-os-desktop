from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class D0AClaimCeilingDocumentationTests(unittest.TestCase):
    """Keep human-facing D0A-02 claim wording aligned with machine truth."""

    def test_d0a_docs_retain_both_explicit_nonclaims(self) -> None:
        for relative in ("README.md", "docs/CURRENT_STATE.md"):
            with self.subTest(path=relative):
                text = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn("no_native_clipboard", text)
                self.assertIn("no_clean_teardown", text)


if __name__ == "__main__":
    unittest.main()
