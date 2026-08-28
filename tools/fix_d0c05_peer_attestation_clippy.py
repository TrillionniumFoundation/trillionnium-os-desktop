#!/usr/bin/env python3
"""Apply the Rust 1.93 write-with-newline lint correction to D0C-05 fixtures."""
from pathlib import Path

path = Path("crates/hepta-peer-attestation/src/lib.rs")
text = path.read_text(encoding="utf-8")
old = '''        write!(
            stat,
            "{pid} (fixture process) S 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 {start_time} 21 22\\n"
        )
'''
new = '''        writeln!(
            stat,
            "{pid} (fixture process) S 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 {start_time} 21 22"
        )
'''
count = text.count(old)
if count != 1:
    raise SystemExit(f"peer-attestation write marker count is {count}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("applied peer-attestation Rust 1.93 lint correction")
