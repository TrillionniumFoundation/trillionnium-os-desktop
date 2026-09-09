#!/usr/bin/env python3
"""Fix nested Python literals before the S07 generator runs."""
from pathlib import Path

path = Path("tools/s07_successor_autofix.py")
text = path.read_text(encoding="utf-8")
replacements = {
    'separator = b"" if base.read_bytes().endswith(b"\\n") else b"\\n"':
        'separator = b"" if base.read_bytes().endswith(b"\\\\n") else b"\\\\n"',
    '"refs/pull/${{ github.event.pull_request.number }}/merge",':
        '"refs/pull/${{{{ github.event.pull_request.number }}}}/merge",',
}
for old, new in replacements.items():
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected one nested literal {old!r}, found {count}")
    text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
