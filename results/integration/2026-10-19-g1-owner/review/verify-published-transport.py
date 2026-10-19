#!/usr/bin/env python3
"""Restore the published parts when the large G1 archive body is absent from Git."""

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path


def identity(path):
    assert path.is_file() and not path.is_symlink()
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
    assert not output.exists()
    transport_path = root / "publication-transport.json"
    transport = json.loads(transport_path.read_text())
    g1 = transport["g1_archive"]
    assert not (root / g1["path_after_restoration"]).exists()
    manifest_path = root / "archive-parts.json"
    manifest = json.loads(manifest_path.read_text())
    helper = root / "review/restore-r10-archives.py"
    expected = {item["path"]: {"bytes": item["bytes"], "sha256": item["sha256"]} for item in manifest["archives"]}
    retained = [transport_path, manifest_path, helper, root / "g1-evidence/files-manifest.json", root / "g1-evidence/artifact-manifest.json"]
    before = {str(path): identity(path) for path in retained}
    started = datetime.now(timezone.utc).isoformat()
    argv = [sys.executable, "-I", str(helper), "--manifest", str(manifest_path), "--output-root", str(output)]
    process = subprocess.run(argv, capture_output=True, text=True)
    receipt = {
        "schema": "r10.parts-only-publication-roundtrip.v1",
        "started_at_utc": started,
        "finished_at_utc": datetime.now(timezone.utc).isoformat(),
        "argv": argv,
        "returncode": process.returncode,
        "stdout": process.stdout,
        "stderr": process.stderr,
        "source_G1_archive_body_absent_before": True,
        "helper": {"path": "review/restore-r10-archives.py", **identity(helper)},
        "parts_manifest": {"path": "archive-parts.json", **identity(manifest_path)},
        "transport_manifest": {"path": "publication-transport.json", **identity(transport_path)},
        "restored": [],
        "product_or_tests_reexecuted": False,
        "status": "failed",
    }
    try:
        assert process.returncode == 0, process.stderr
        result = json.loads(process.stdout)
        assert result["status"] == "verified" and result["verify_only"] is False
        assert len(result["archives"]) == len(expected) == 2
        for item in result["archives"]:
            assert item["restored"] is True and item["existing_archive_verified"] is False
            assert item["all_part_identities_verified"] is True
            observed = identity(output / item["path"])
            assert observed == expected[item["path"]]
            comparison_path = Path(g1["preserved_original_path"]) if item["path"] == g1["path_after_restoration"] else root / item["path"]
            assert identity(comparison_path) == observed
            receipt["restored"].append({"path": item["path"], **observed, "parts": item["parts"], "original_byte_identity_rechecked": True})
        assert not (root / g1["path_after_restoration"]).exists()
        assert all(identity(Path(path)) == record for path, record in before.items())
        receipt["source_G1_archive_body_still_absent_after"] = True
        receipt["helper_and_all_manifests_unchanged"] = True
        receipt["status"] = "passed_parts_only_Git_publication_restoration"
    finally:
        args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "source_G1_body_absent": True, "restored": receipt["restored"]}))


if __name__ == "__main__":
    main()
