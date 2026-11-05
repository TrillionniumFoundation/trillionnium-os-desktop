#!/usr/bin/env python3
"""Bind the one actual protected NORMAL11 prepared report; local generator only."""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import re

BASE = Path(__file__).resolve().parent.parent
OLD = BASE / "owner10-normal01-prepared-read-freeze-01"
OUT = BASE / "owner11-normal01-prepared-read-freeze-01"


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
    text = source
    substitutions = [
        ("p4-owner10-normal-20261105-01-state", "p4-owner11-normal-20261105-01-state"),
        ("EXPECTED_REPORT_BYTES = 55139", "EXPECTED_REPORT_BYTES = " + str(args.bytes)),
        ("53f327728b4daf732653a189d690f0c1d4e6374aeab5f7b9df7d666598f978e3", args.sha256),
        ("fixed-owner10-normal01-prepared-read", "fixed-owner11-normal01-prepared-read"),
    ]
    for old, new in substitutions:
        assert text.count(old) == 1
        text = text.replace(old, new)
    inverse = text
    for old, new in reversed(substitutions):
        assert inverse.count(new) == 1
        inverse = inverse.replace(new, old)
    assert inverse == source
    ast.parse(text)
    compile(text, "<fixed protected NORMAL11 prepared reader>", "exec")
    request = json.loads((OLD / "request.json").read_bytes())
    assert request["stdin"] == source
    request["stdin"] = text
    request["idempotency_key"] = "p4-owner11-normal01-prepared-read01-" + sha(text.encode())[:16]
    validation = {
        "kind": "normal11_prepared_fixed_reader_binding",
        "fixed_path": "/opt/p4-owner11-normal-20261105-01-state/prepared.json",
        "expected_bytes": args.bytes, "expected_sha256": args.sha256,
        "preimage_reader_sha256": sha(source.encode()), "reader_sha256": sha(text.encode()),
        "only_exact_root_length_digest_and_scope_literals_changed": True,
        "inverse_literal_transform_exact": True,
        "held_root_owned_FD_identity_and_double_read_gates_unchanged": True,
        "request_sha256": sha(pretty(request)), "reader_executed": False,
        "mutations": False, "runtime_qualification": False,
    }
    members = {
        "read.py": text.encode(), "request.json": pretty(request),
        "validation.json": pretty(validation),
        "source.diff": "".join(difflib.unified_diff(source.splitlines(True), text.splitlines(True),
            fromfile="owner10/read.py", tofile="owner11/read.py")).encode(),
        "freeze_prepared_reader10.py": Path(__file__).read_bytes(),
    }
    OUT.mkdir(exist_ok=False)
    rows = []
    for name, raw in members.items():
        raw.decode("utf-8")
        with (OUT / name).open("xb") as stream:
            stream.write(raw)
        rows.append({"path": name, "bytes": len(raw), "sha256": sha(raw)})
    manifest = pretty({"kind": "normal11_prepared_fixed_reader", "files": rows, "executed": False})
    with (OUT / "manifest.json").open("xb") as stream:
        stream.write(manifest)
    print(json.dumps({"root": str(OUT), "manifest_sha256": sha(manifest),
        "request_bytes": len(pretty(request)), "key": request["idempotency_key"], **validation}, indent=2))


if __name__ == "__main__":
    main()
