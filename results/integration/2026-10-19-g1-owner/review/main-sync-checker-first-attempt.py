#!/usr/bin/env python3
"""Check the new fixed main and classify upgrades from the frozen R10 delivery."""

import argparse
import hashlib
import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path


PREFIX = "results/integration/2026-10-19-g1-owner/"
INCOMING = "7e859b98c58053b88ea2baabc3e5f645fd38dca5"
INCOMING_TREE = "354adb549b064c78477932ca943309694eb54356"
PREVIOUS_MAIN = "71ce079c3218a8692476e4113b60c9d2c0d2a172"
OLD_DELIVERY = "bc309bebba52622dd165a657447306a2cf32928e"
OLD_TREE = "477f6e9fdb9be7a15c94f9d534eb8ec033ecc47b"
DOCS = {"docs/INDEX.md", "docs/STATUS.md"}
UPGRADES = {
    "docs/INDEX.md": "Retain incoming SCM entry and add current bounded source/status scope.",
    "docs/STATUS.md": "Update only the R10 prefix; retain the entire incoming e15 history suffix.",
    PREFIX + "README.md": "Update the R10 summary with the new fixed main and bounded status; keep runtime pins separate.",
    PREFIX + "module-documentation-delta.json": "Recompute explicit source7e plus authored-overlay documentation delta; archive the prior review.",
    PREFIX + "review/review-module-documentation-delta.py": "Add the read 7e A04/SCM manual changes and current main identity.",
    PREFIX + "review/delivery-links.json": "Recompute current local source/overlay and archive-member links for the new report.",
    PREFIX + "review/review-final-delivery.py": "Extend byte preservation to new incoming main links, frozen text inputs and pre-sync scope.",
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--mode", choices=["source", "preservation"], required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    root = repo / PREFIX

    def git(*argv):
        return subprocess.check_output(["git", *argv], cwd=repo)

    def tree(commit):
        result = {}
        for value in git("ls-tree", "-rz", commit).split(b"\0"):
            if value:
                metadata, name = value.split(b"\t", 1)
                mode, kind, blob = metadata.decode().split()
                result[name.decode()] = {"mode": mode, "kind": kind, "git_blob": blob}
        return result

    def record(path):
        file = repo / path
        assert file.is_file() and not file.is_symlink(), path
        data = file.read_bytes()
        mode = "100755" if file.stat().st_mode & 0o111 else "100644"
        blob = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
        return {"path": path, "mode": mode, "bytes": len(data), "sha256": sha(data), "git_blob": blob}

    assert git("rev-parse", INCOMING + "^{tree}").decode().strip() == INCOMING_TREE
    assert git("rev-parse", OLD_DELIVERY + "^{tree}").decode().strip() == OLD_TREE

    if args.mode == "source":
        incoming = tree(INCOMING)
        before = tree(PREVIOUS_MAIN)
        changed = sorted(path for path in set(incoming) | set(before) if incoming.get(path) != before.get(path))
        assert len(changed) == 37
        checked = []
        for path, expected in incoming.items():
            if path in DOCS or path.startswith(PREFIX):
                continue
            actual = record(path)
            assert expected["kind"] == "blob"
            assert all(actual[key] == expected[key] for key in ["mode", "git_blob"]), path
            checked.append(actual)
        diff = git("diff", "--name-only", INCOMING).decode().splitlines()
        assert all(path in DOCS or path.startswith(PREFIX) for path in diff), diff
        retained = []
        for path in changed:
            expected = incoming[path]
            if path == "docs/INDEX.md":
                old = git("show", INCOMING + ":" + path).decode()
                current = (repo / path).read_text()
                hrefs = lambda content: set(re.findall(r"\[[^\]]*\]\(([^)]+)\)", content))
                assert hrefs(old) <= hrefs(current)
                retained.append({"path": path, "incoming": expected, "resolution": "Only authorized INDEX prose changes; all incoming targets retained.", "incoming_distinct_targets": len(hrefs(old))})
            else:
                actual = record(path)
                assert actual["mode"] == expected["mode"] and actual["git_blob"] == expected["git_blob"]
                retained.append({**actual, "incoming": expected, "resolution": "Exact incoming bytes and mode retained."})
        # Use the complete actual G1 product input prefixes, not an assumed
        # name for a CPU file, and record the matched paths from the tree.
        g1_paths = sorted(path for path in incoming if path.startswith("libs/os-control/") or path.startswith("libs/os-abi/") or (path.startswith("kernel/asterinas/") and ("/cpu/" in path or "/cgroup/" in path or "native" in path or path.endswith("/syscall/ioctl.rs"))))
        assert g1_paths
        assert all(incoming[path] == before[path] for path in g1_paths)
        production = [path for path in changed if path.startswith("kernel/asterinas/")]
        assert len(production) == 5
        result = {
            "schema": "r10.report-main-sync-source-integration.v1",
            "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
            "incoming_main": INCOMING,
            "incoming_tree": INCOMING_TREE,
            "incoming_parents": git("show", "-s", "--format=%P", INCOMING).decode().split(),
            "previous_main": PREVIOUS_MAIN,
            "pre_sync_delivery": {"commit": OLD_DELIVERY, "tree": OLD_TREE},
            "incoming_tracked_file_count": len(incoming),
            "all_report_external_files_checked": len(checked),
            "all_report_external_file_bytes": sum(entry["bytes"] for entry in checked),
            "all_report_external_modes_and_Git_blobs_equal_incoming_main": True,
            "incoming_changes": retained,
            "incoming_changed_paths": len(changed),
            "changed_production_paths": production,
            "only_report_overlap": "docs/INDEX.md",
            "incoming_INDEX_targets_preserved": True,
            "G1_product_prefix_comparison": {"paths": g1_paths, "all_blob_and_mode_equal_previous_main": True, "meaning": "This is exact byte preservation of selected existing G1 CPU/cgroup, native, ABI and control inputs, not a new runtime qualification."},
            "root_README_bytes": len((repo / "README.md").read_bytes()),
            "runtime_scope": {"G1_full_run_head": "1c05412e2b340bbc8cd2b8a3389ae0ecce538991", "G1_full_run_tree": "2b873aa43445c8a02351f5900074a38c6fa4820d", "old_runtime_extended_to_incoming_tree": False, "PR198_scope": "Its independent source and Actions artifact review is a separate record; this helper does not run or reclassify it."},
            "no_product_execution": True,
            "status": "passed_incoming_main_exact_product_and_history_preservation",
        }
        assert result["root_README_bytes"] == 0
        output = root / "source-publication/report-main-sync/source-integration-review.json"
    else:
        old_manifest_path = "delivery-manifest.json"
        old_bytes = git("show", OLD_DELIVERY + ":" + PREFIX + old_manifest_path)
        assert (root / "review/pre-main-sync/delivery-manifest.json").read_bytes() == old_bytes
        old = json.loads(old_bytes)
        assert len(old["entries"]) == 405
        records = []
        modified = []
        for entry in old["entries"]:
            actual = record(entry["path"])
            same = all(entry[key] == actual[key] for key in ["mode", "bytes", "sha256"])
            if not same:
                assert entry["path"] in UPGRADES, entry["path"]
                modified.append(entry["path"])
            records.append({"path": entry["path"], "status": "unchanged_original_bytes_and_mode" if same else "explicit_authored_summary_or_review_upgrade", "before": entry, "after": actual, "reason": "Frozen original bytes and mode retained." if same else UPGRADES[entry["path"]]})
        result = {
            "schema": "r10.main-sync-old-delivery-entry-preservation.v1",
            "reviewed_at_utc": datetime.now(timezone.utc).isoformat(),
            "old_delivery": {"commit": OLD_DELIVERY, "tree": OLD_TREE, "manifest_path": "review/pre-main-sync/delivery-manifest.json", "manifest_bytes": len(old_bytes), "manifest_sha256": sha(old_bytes)},
            "new_product_base": INCOMING,
            "new_product_tree": INCOMING_TREE,
            "old_entries": len(records),
            "unchanged_entries": len(records) - len(modified),
            "explicitly_upgraded_entries": len(modified),
            "upgraded_paths": modified,
            "original_producer_archives_parts_manifests_receipts_not_modified": True,
            "old_terminal_files": {"paths": ["delivery-manifest.json", "review/final-delivery-review.json"], "meaning": "These two old terminal files are outside the old405 entry set, preserved in pre-main-sync; current terminal files bind this new delivery and are not treated as original producer evidence."},
            "old_QA_scope": "The archived independent QA proves bc309/tree477 only. A fresh independent fixed-Git review is required for the new delivery.",
            "records": records,
            "cargo_invocations": 0,
            "qemu_invocations": 0,
            "status": "passed_405_old_entries_preserved_or_explicitly_upgraded",
        }
        output = root / "review/main-sync-entry-preservation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "output": str(output), "old_entries": result.get("old_entries"), "upgraded_entries": result.get("explicitly_upgraded_entries"), "incoming_files": result.get("incoming_tracked_file_count")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
