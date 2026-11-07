#!/usr/bin/env python3
"""Local exact adaptation of proven decoder paths/range; no actual raw input."""
import ast
import difflib
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
SOURCE = PROJECT / "successor_audit_requests/effective_permissions_batch_readback_r2/decode_private_readback.py"


def main():
    raw = SOURCE.read_bytes()
    assert len(raw) == 10114 and hashlib.sha256(raw).hexdigest() == "3255c54a3d5f42866eab7744f4e3ab78ea2f059162ea3223812287a93042a296"
    original = raw.decode()
    source = original.replace("HERE = Path(__file__).resolve().parent\nPROJECT = HERE.parents[1]",
        "HERE = Path(__file__).resolve().parent / 'readbacks'\nPROJECT = Path(__file__).resolve().parents[3]", 1)
    source = source.replace("need(2 <= args.batch <= 13,", "need(1 <= args.batch <= 14,", 1)
    source = source.replace("fixed45-permissions-compressed-readback-r2", "fixed46-permissions-compressed-readback-r1", 1)
    def defs(text):
        return {n.name: ast.get_source_segment(text, n) for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}
    before, after = defs(original), defs(source)
    assert set(before) == set(after) and all(before[n] == after[n] for n in before if n != "main")
    compile(source, "decode_completed_readback.py", "exec")
    for name, text in (("decode_completed_readback.py", source), ("decoder-against-proven-r2.diff", "".join(
        difflib.unified_diff(original.splitlines(True), source.splitlines(True), fromfile="proven-private-decoder-r2", tofile="new46-private-decoder")))):
        with (HERE / name).open("xb") as stream:
            stream.write(text.encode())
        assert (HERE / name).read_bytes() == text.encode()
    print({"unchanged_definitions": sorted(n for n in before if n != "main"), "private_body_reads": 0, "remote_jobs": 0})


if __name__ == "__main__":
    main()
