#!/usr/bin/env python3
"""Bind the fixed protected runtime result to authoritative terminal metadata."""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re

BASE = Path(__file__).resolve().parent.parent
OLD = BASE / "owner10-normal01-prepared-read-freeze-01"
OUT = BASE / "owner10-normal01-runtime-read-freeze-01"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pretty(value):
    return (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bytes", type=int, required=True)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()
    assert 0 < args.bytes <= 1048576 and re.fullmatch("[0-9a-f]{64}", args.sha256)
    manifest_raw = (OLD / "manifest.json").read_bytes()
    assert sha(manifest_raw) == "387ea3e982812c80a61306a37cceb19ec21f94e5b75334c1f73db2ee4c688ef4"
    for row in json.loads(manifest_raw)["files"]:
        raw = (OLD / row["path"]).read_bytes()
        assert len(raw) == row["bytes"] and sha(raw) == row["sha256"]
    source = (OLD / "read.py").read_text()
    assert sha(source.encode()) == "a8e0de6540c20d189d6901854731cf6785630e4942b95754698fa78a07db56b4"
    text = source
    substitutions = [
        ("prepared.json", "runtime-result.json", 4),
        ("EXPECTED_REPORT_BYTES = 55139", "EXPECTED_REPORT_BYTES = " + str(args.bytes), 1),
        ("53f327728b4daf732653a189d690f0c1d4e6374aeab5f7b9df7d666598f978e3", args.sha256, 1),
        ("fixed-owner10-normal01-prepared-read", "fixed-owner10-normal01-runtime-read", 1),
        ("externally pinned actual prepared report differs", "externally pinned actual runtime report differs", 1),
        ("held prepared directory changed", "held runtime directory changed", 1),
    ]
    for old, new, count in substitutions:
        assert text.count(old) == count, (old, text.count(old))
        text = text.replace(old, new)
    inverse = text
    for old, new, count in reversed(substitutions):
        assert inverse.count(new) == count
        inverse = inverse.replace(new, old)
    assert inverse == source
    ast.parse(text)
    compile(text, "<fixed protected NORMAL10 runtime reader>", "exec")
    request = json.loads((OLD / "request.json").read_bytes())
    assert request["stdin"] == source
    request["stdin"] = text
    request["idempotency_key"] = "p4-owner10-normal01-runtime-read01-" + sha(text.encode())[:16]
    validation = {
        "kind": "normal10_runtime_fixed_reader_binding",
        "fixed_path": "/opt/p4-owner10-normal-20261105-01-state/runtime-result.json",
        "expected_bytes": args.bytes, "expected_sha256": args.sha256,
        "preimage_reader_sha256": sha(source.encode()), "reader_sha256": sha(text.encode()),
        "only_exact_member_length_digest_and_inert_scope_literals_changed": True,
        "inverse_literal_transform_exact": True,
        "held_root_owned_FD_identity_and_double_read_gates_unchanged": True,
        "request_sha256": sha(pretty(request)), "reader_executed": False,
        "mutations": False, "runtime_qualification": False,
    }
    members = {
        "read.py": text.encode(), "request.json": pretty(request),
        "validation.json": pretty(validation),
        "source.diff": "".join(difflib.unified_diff(source.splitlines(True), text.splitlines(True),
            fromfile="normal10-prepared/read.py", tofile="normal10-runtime/read.py")).encode(),
        "freeze_runtime_reader10.py": Path(__file__).read_bytes(),
    }
    OUT.mkdir(exist_ok=False)
    rows = []
    for name, raw in members.items():
        raw.decode("utf-8")
        with (OUT / name).open("xb") as stream:
            stream.write(raw)
        rows.append({"path": name, "bytes": len(raw), "sha256": sha(raw)})
    manifest = pretty({"kind": "normal10_runtime_fixed_reader", "files": rows, "executed": False})
    with (OUT / "manifest.json").open("xb") as stream:
        stream.write(manifest)
    print(json.dumps({"root": str(OUT), "manifest_sha256": sha(manifest),
        "request_bytes": len(pretty(request)), "key": request["idempotency_key"], **validation}, indent=2))


if __name__ == "__main__":
    main()
