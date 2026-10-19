#!/usr/bin/env python3
"""Copy the separately frozen Fleet fix evidence without changing either older package."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def record(root, relative):
    path = root / relative
    assert path.is_file() and not path.is_symlink()
    data = path.read_bytes()
    return {"path": relative, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    source = args.source.resolve()
    destination = args.destination.resolve()
    assert not destination.exists()
    manifest_data = (source / "files-manifest.json").read_bytes()
    assert hashlib.sha256(manifest_data).hexdigest() == "c42b3bc1774bd150d15ea563ce8fc088dd47c23cf0b1919350d912fa495c4232"
    manifest = json.loads(manifest_data)
    selected = [*manifest["files"], record(source, "files-manifest.json")]
    paths = sorted(entry["path"] for entry in selected)
    assert len(paths) == 20 and len(set(paths)) == 20
    assert sorted(path.relative_to(source).as_posix() for path in source.rglob("*") if path.is_file()) == paths
    assert all(record(source, entry["path"]) == entry for entry in selected)
    destination.mkdir(parents=True)
    for entry in sorted(selected, key=lambda entry: entry["path"]):
        relative = entry["path"]
        assert not Path(relative).is_absolute() and ".." not in Path(relative).parts
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((source / relative).read_bytes())
        assert record(destination, relative) == entry
    assert all(record(source, entry["path"]) == entry for entry in selected)
    result = {
        "schema": "r10.fleet-fixture-evidence-copy.v1",
        "copied_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": str(source),
        "destination": str(destination),
        "source_commit": manifest["source_commit"],
        "source_tree": manifest["source_tree"],
        "file_count": len(selected),
        "total_bytes": sum(entry["bytes"] for entry in selected),
        "all_manifest_entries_and_manifest_itself_verified": True,
        "source_files_unchanged_before_and_after_copy": True,
        "destination_bytes_equal_frozen_sources": True,
        "old_diagnostic_packages_modified": False,
        "product_worktrees_accessed": False,
        "cargo_or_clippy_or_tests_reexecuted": False,
        "files": sorted(selected, key=lambda entry: entry["path"]),
        "status": "passed_exact_frozen_evidence_copy",
    }
    args.receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "files": len(selected), "bytes": result["total_bytes"], "manifest": record(destination, "files-manifest.json")}))


if __name__ == "__main__":
    main()
