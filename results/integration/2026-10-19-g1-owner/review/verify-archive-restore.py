#!/usr/bin/env python3
"""Run the delivered restoration tool in an empty review directory and bind bytes."""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def identity(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    output = args.output_root.resolve()
    assert not output.exists(), "Roundtrip output must be new and empty"
    manifest_path = root / "archive-parts.json"
    helper = root / "review/restore-r10-archives.py"
    manifest = json.loads(manifest_path.read_text())
    before = {entry["path"]: identity(root / entry["path"]) for entry in manifest["archives"]}
    started = datetime.now(timezone.utc).isoformat()
    argv = [sys.executable, "-I", str(helper), "--manifest", str(manifest_path), "--output-root", str(output)]
    process = subprocess.run(argv, capture_output=True, text=True)
    receipt = {
        "schema": "r10.archive-restoration-review.v1",
        "started_at_utc": started,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "argv": argv,
        "returncode": process.returncode,
        "stdout": process.stdout,
        "stderr": process.stderr,
        "helper": {"path": "review/restore-r10-archives.py", **identity(helper)},
        "parts_manifest": {"path": "archive-parts.json", **identity(manifest_path)},
        "source_archives_unchanged": False,
        "restored_archives": [],
        "products_reexecuted": False,
        "status": "failed",
    }
    try:
        assert process.returncode == 0, process.stderr
        observed = json.loads(process.stdout)
        assert observed["status"] == "verified" and observed["verify_only"] is False
        assert len(observed["archives"]) == len(manifest["archives"])
        for entry, actual in zip(manifest["archives"], observed["archives"], strict=True):
            expected = {"bytes": entry["bytes"], "sha256": entry["sha256"]}
            assert actual["path"] == entry["path"]
            assert actual["restored"] is True and actual["existing_archive_verified"] is False
            assert actual["all_part_identities_verified"] is True
            assert before[entry["path"]] == expected
            assert identity(root / entry["path"]) == expected
            assert identity(output / entry["path"]) == expected
            receipt["restored_archives"].append({"path": entry["path"], **expected, "parts": len(entry["parts"]), "byte_identity_with_original": True})
        assert sorted(path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()) == sorted(entry["path"] for entry in manifest["archives"])
        receipt["source_archives_unchanged"] = True
        receipt["status"] = "passed_exact_original_archive_restoration"
    finally:
        args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "archives": receipt["restored_archives"], "receipt": str(args.receipt)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
