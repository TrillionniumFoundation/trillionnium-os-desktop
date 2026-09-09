#!/usr/bin/env python3
"""Remove a self-contradictory literal from the one-shot S06 document generator."""
from pathlib import Path

path = Path("tools/s06_product_authority_autofix.py")
text = path.read_text(encoding="utf-8")
old = "- a product `BrowserActor<R>` or constructor accepting a runtime value;"
new = "- a product actor parameterized by a caller runtime or constructor accepting a runtime value;"
if text.count(old) != 1:
    raise SystemExit(f"expected one generic actor negative guarantee, found {text.count(old)}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
