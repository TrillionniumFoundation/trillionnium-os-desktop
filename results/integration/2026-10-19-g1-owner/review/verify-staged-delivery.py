#!/usr/bin/env python3
"""Verify that staged delivery blobs retain every intended byte, including logs."""

import argparse
import hashlib
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


PREFIX = "results/integration/2026-10-19-g1-owner/"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    root = repo / PREFIX
    assert not args.receipt.resolve().is_relative_to(root), "The receipt stays outside the commit it checks"
    manifest = json.loads((root / "delivery-manifest.json").read_text())
    terminal = {PREFIX + "delivery-manifest.json", PREFIX + "review/final-delivery-review.json"}
    paths = sorted({item["path"] for item in manifest["entries"]} | terminal)
    manifest_by_path = {item["path"]: item for item in manifest["entries"]}
    omitted = {PREFIX + name for name in manifest["parts_only_archive_publication"]["body_omitted_from_Git"]}
    assert not set(paths) & omitted
    changed = subprocess.check_output(["git", "diff", "--cached", "--name-only", "-z"], cwd=repo).decode().split("\0")
    changed = [path for path in changed if path]
    assert set(changed) <= set(paths), sorted(set(changed) - set(paths))
    stage = subprocess.check_output(["git", "ls-files", "--stage", "-z", "--", "docs/INDEX.md", "docs/STATUS.md", PREFIX], cwd=repo)
    staged = {}
    for item in stage.split(b"\0"):
        if not item:
            continue
        metadata, path = item.split(b"\t", 1)
        mode, oid, number = metadata.decode().split()
        assert number == "0"
        staged[path.decode()] = {"mode": mode, "blob": oid}
    assert sorted(staged) == paths, {"missing": sorted(set(paths) - set(staged)), "extra": sorted(set(staged) - set(paths))}
    observed = []
    for path in paths:
        absolute = repo / path
        assert absolute.is_file() and not absolute.is_symlink()
        data = absolute.read_bytes()
        mode = "100755" if absolute.stat().st_mode & 0o111 else "100644"
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        assert staged[path] == {"mode": mode, "blob": blob}, path
        record = {"path": path, "mode": mode, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
        if path in manifest_by_path:
            assert record == manifest_by_path[path], path
        observed.append({**record, "git_blob": blob})
    assert not set(staged) & omitted
    assert (repo / "README.md").read_bytes() == b""
    preservation = json.loads((root / "review/whitespace-preservation.json").read_text())
    exempt = set()
    for entry in preservation["explicit_preserved_raw_paths"]:
        assert entry["path"] in manifest_by_path
        assert all(manifest_by_path[entry["path"]][key] == entry[key] for key in ["mode", "bytes", "sha256"])
        exempt.add(entry["path"])
    assert len(exempt) == 31 and preservation["original_diagnostic_path_count"] == 30
    format_paths = sorted(set(paths) - exempt)
    difference = subprocess.run(["git", "diff", "--cached", "--check", "--", *format_paths], cwd=repo, capture_output=True, text=True)
    assert difference.returncode == 0, "Whitespace failed outside explicitly SHA-bound raw evidence paths"
    result = {
        "schema": "r10.staged-delivery-byte-review.v1",
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "head_before_docs_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo).decode().strip(),
        "staged_file_count": len(observed),
        "all_intended_files_in_index": True,
        "all_staged_changes_within_manifest_selection": True,
        "all_staged_blob_ids_match_exact_worktree_bytes_and_modes": True,
        "all_manifest_entries_match_staged_bytes_modes_and_sha256": True,
        "all_explicitly_omitted_archive_bodies_not_in_index": sorted(omitted),
        "selection_source": "delivery-manifest entries plus its two terminal files, not recursive physical-directory staging",
        "root_README_bytes": 0,
        "cached_diff_check_returncode": difference.returncode,
        "cached_diff_check_paths": format_paths,
        "explicit_raw_whitespace_preservation": {"receipt": PREFIX + "review/whitespace-preservation.json", "paths": sorted(exempt), "all_exact_manifest_identities_checked": True, "blanket_results_exclusion": False},
        "files": observed,
        "products_reexecuted": False,
        "status": "passed_complete_index_and_blob_equality",
    }
    args.receipt.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "staged_files": len(observed), "receipt": str(args.receipt)}))


if __name__ == "__main__":
    main()
