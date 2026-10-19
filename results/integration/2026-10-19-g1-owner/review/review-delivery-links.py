#!/usr/bin/env python3
"""Resolve current delivery Markdown targets against its explicit source and archives."""

import argparse
import hashlib
import json
import posixpath
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlsplit


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--source-head", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    source = args.source_head
    assert re.fullmatch(r"[0-9a-f]{40}", source)
    prefix = "results/integration/2026-10-19-g1-owner/"
    result_root = repo / prefix
    overlays = {"docs/INDEX.md", "docs/STATUS.md"}
    transport = json.loads((result_root / "publication-transport.json").read_text())
    omitted_archive = prefix + transport["g1_archive"]["path_after_restoration"]
    omitted_archives = {omitted_archive: {"bytes": transport["g1_archive"]["bytes"], "sha256": transport["g1_archive"]["sha256"], "transport_manifest": prefix + "publication-transport.json"}}
    for current in sorted(result_root.glob("g1-remote-ci-*/publication-transport.json")):
        ci_transport = json.loads(current.read_text())
        relative = current.parent.relative_to(repo).as_posix() + "/"
        item = ci_transport["original_archive"]
        omitted_archives[relative + item["path"]] = {"bytes": item["bytes"], "sha256": item["sha256"], "transport_manifest": current.relative_to(repo).as_posix()}
    archive_targets = {}
    for name in ["g1-evidence", "hepta-security", "hepta-bazel-followup", "g1-ci-host-correction", "hepta-fleet-main-remote-ci", "hepta-scoped-ci-storage-fix"]:
        package = result_root / name
        manifest_path = package / "files-manifest.json"
        manifest = json.loads(manifest_path.read_text())
        archive = prefix + name + "/raw-evidence.tar.xz"
        for entry in manifest["files"]:
            path = prefix + name + "/" + entry["path"]
            archive_targets[path] = {"archive": archive, "archive_delivery": "restore_from_parts_before_extraction" if archive == omitted_archive else "archive_body_directly_delivered", "member": entry["path"], "bytes": entry["bytes"], "sha256": entry["sha256"]}

    git_cache = {}

    def fixed(path):
        if path not in git_cache:
            process = subprocess.run(["git", "show", f"{source}:{path}"], cwd=repo, capture_output=True)
            git_cache[path] = process.stdout if process.returncode == 0 else None
        return git_cache[path]

    def resolve(path):
        if path in omitted_archives:
            return {"resolution": "restorable_archive_parts_only_not_in_Git", **omitted_archives[path]}
        if path.startswith(prefix) or path in overlays:
            item = repo / path
            if item.is_file():
                data = item.read_bytes()
                return {"resolution": "present_delivery_file", "bytes": len(data), "sha256": sha(data)}
            if item.is_dir():
                return {"resolution": "present_delivery_directory"}
        else:
            data = fixed(path)
            if data is not None:
                return {"resolution": "present_fixed_source", "bytes": len(data), "sha256": sha(data), "source_commit": source}
        if path in archive_targets:
            return {"resolution": "archive_member_only_extract_first", **archive_targets[path]}
        members = [value for key, value in archive_targets.items() if key.startswith(path.rstrip("/") + "/")]
        if members:
            archives = sorted({value["archive"] for value in members})
            return {"resolution": "archive_directory_only_extract_first", "archives": archives, "member_count": len(members)}
        return {"resolution": "missing"}

    documents = [("docs/INDEX.md", (repo / "docs/INDEX.md").read_bytes(), "entire_current_index")]
    status = (repo / "docs/STATUS.md").read_bytes()
    old_header = "## 2026-10-19：整合 Runtime 修复与已合入的原 owner 历史扩展".encode()
    assert old_header in status
    documents.append(("docs/STATUS.md", status[:status.index(old_header)], "new_R10_prefix_only_history_not_rescanned"))
    documents += [(path.relative_to(repo).as_posix(), path.read_bytes(), "delivered_primary_markdown") for path in sorted(result_root.rglob("*.md"))]
    targets = []
    for path, data, scope in documents:
        for label, href in re.findall(r"\[([^\]]+)\]\(([^\s)]+)\)", data.decode()):
            parsed = urlsplit(href)
            record = {"from": path, "scan_scope": scope, "label": label, "href": href}
            if parsed.scheme or parsed.netloc:
                record["resolution"] = "external_not_refetched"
            else:
                relative = unquote(parsed.path)
                target = posixpath.normpath(posixpath.join(posixpath.dirname(path), relative)) if relative else path
                record["target"] = target
                if target.startswith("/") or target.startswith("../"):
                    record["resolution"] = "historical_absolute_or_outside_path_not_portable"
                else:
                    record.update(resolve(target))
                if parsed.fragment:
                    record["fragment"] = parsed.fragment
                    record["fragment_check"] = "not_part_of_file_presence_gate"
            targets.append(record)
    counts = {kind: sum(item["resolution"] == kind for item in targets) for kind in sorted({item["resolution"] for item in targets})}
    missing = [item for item in targets if item["resolution"] in {"missing", "historical_absolute_or_outside_path_not_portable"}]
    receipt = {
        "schema": "r10.delivery-markdown-target-review.v1",
        "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
        "fixed_product_source": source,
        "delivery_overlay": {"files": sorted(overlays), "new_results_prefix": prefix, "publication_state": "explicit_local_files_over_fixed_source_not_a_claim_of_main_integration"},
        "documents": [{"path": path, "scan_scope": scope, "bytes_scanned": len(data), "sha256_scanned": sha(data)} for path, data, scope in documents],
        "target_counts": counts,
        "targets": targets,
        "blocking_unresolved": missing,
        "archive_only_links_explained_in_main_README": True,
        "all_local_markdown_links_already_clickable": counts.get("archive_member_only_extract_first", 0) == 0 and counts.get("archive_directory_only_extract_first", 0) == 0 and counts.get("restorable_archive_parts_only_not_in_Git", 0) == 0 and not missing,
        "limits": ["Archive-only links are not counted as present local files. They require extraction at the archive root described in the delivery README.", "The complete incoming e15 STATUS body and links inside compressed raw documents are not re-audited by this scope.", "External sites and fragments are not refetched or validated by this local file target check; separate raw API snapshots retain their own observation scope.", "The new G1/A04 manuals resolve at the immutable integrated product commit. Later local reappearance of an explicitly omitted original archive copy does not make it a delivered Git file."],
        "products_reexecuted": False,
        "status": "passed_explicit_target_and_archive_resolution" if not missing else "failed_unresolved_targets",
    }
    args.output.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "documents": len(documents), "target_counts": counts, "blocking_unresolved": missing}, ensure_ascii=False))
    if missing:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
