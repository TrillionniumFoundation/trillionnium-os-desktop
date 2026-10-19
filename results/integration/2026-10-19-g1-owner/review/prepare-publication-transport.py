#!/usr/bin/env python3
"""Preserve the exact large G1 archive outside Git and publish its existing parts."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def identity(path):
    assert path.is_file() and not path.is_symlink(), path
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--preserved-archive", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    preserved = args.preserved_archive.resolve()
    assert not preserved.is_relative_to(root)
    original = root / "g1-evidence/raw-evidence.tar.xz"
    expected = {"bytes": 10602828, "sha256": "6a20eefe453be83e04ad74ac99e79206d20034025c30a743f9a95ce2e6b370fd"}
    assert identity(original) == expected
    assert not preserved.exists()
    retained_manifests = ["g1-evidence/files-manifest.json", "g1-evidence/artifact-manifest.json", "archive-parts.json"]
    before = {path: identity(root / path) for path in retained_manifests}
    manifest = json.loads((root / "archive-parts.json").read_text())
    entry = next(item for item in manifest["archives"] if item["path"] == "g1-evidence/raw-evidence.tar.xz")
    assert len(entry["parts"]) == 7
    combined = hashlib.sha256()
    size = 0
    for item in entry["parts"]:
        data = (root / item["path"]).read_bytes()
        assert len(data) == item["bytes"] and hashlib.sha256(data).hexdigest() == item["sha256"]
        combined.update(data)
        size += len(data)
    assert {"bytes": size, "sha256": combined.hexdigest()} == expected
    preserved.parent.mkdir(parents=True, exist_ok=True)
    preserved.write_bytes(original.read_bytes())
    assert identity(preserved) == expected == identity(original)
    original.unlink()
    assert not original.exists() and identity(preserved) == expected
    assert all(identity(root / path) == record for path, record in before.items())
    receipt = {
        "schema": "r10.publication-transport.v1",
        "prepared_at_utc": datetime.now(timezone.utc).isoformat(),
        "reason": "The parent explicitly selected a parts-only Git publication for the 10.60 MB G1 archive to avoid the publication blob API limit; the original security and Bazel archive bodies remain directly delivered.",
        "g1_archive": {"path_after_restoration": "g1-evidence/raw-evidence.tar.xz", **expected, "body_in_published_Git_tree": False, "parts_count": 7, "parts_manifest": "archive-parts.json", "preserved_original_path": str(preserved), "preserved_original_identity_verified": True, "reconstructed_parts_identity_verified": True},
        "other_archives": [{"path": "hepta-security/raw-evidence.tar.xz", "body_in_published_Git_tree": True, "also_has_parts": True}, {"path": "hepta-bazel-followup/raw-evidence.tar.xz", "body_in_published_Git_tree": True, "also_has_parts": False}],
        "unchanged_internal_manifests": [{"path": path, **record} for path, record in before.items()],
        "original_archive_bytes_changed": False,
        "archive_recompression": False,
        "frozen_execution_receipts_modified": False,
        "product_or_tests_reexecuted": False,
        "reader_action": "Run review/restore-r10-archives.py with archive-parts.json and a new output-root, then extract the restored G1 archive at its archive root. Internal artifact/files manifests describe the exact reconstructed package, not an assertion that its large body is present in Git.",
        "status": "passed_preserved_original_and_parts_only_Git_transport",
    }
    (root / "publication-transport.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "g1_archive": receipt["g1_archive"], "internal_manifests_unchanged": True}))


if __name__ == "__main__":
    main()
