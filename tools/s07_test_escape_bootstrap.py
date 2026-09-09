#!/usr/bin/env python3
"""Fix one nested Python string escape before the S07 generator runs."""
from pathlib import Path

path = Path("tools/s07_successor_autofix.py")
text = path.read_text(encoding="utf-8")
old = 'separator = b"" if base.read_bytes().endswith(b"\\n") else b"\\n"'
new = 'separator = b"" if base.read_bytes().endswith(b"\\\\n") else b"\\\\n"'
count = text.count(old)
if count != 1:
    raise SystemExit(f"expected one nested byte-newline literal, found {count}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
