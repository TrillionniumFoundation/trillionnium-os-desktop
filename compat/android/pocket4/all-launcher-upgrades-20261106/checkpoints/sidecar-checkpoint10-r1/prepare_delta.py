#!/usr/bin/env python3
"""Exact public-text delta for root to merge into checkpoint10; no Git or remote."""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
INDEX_NAMES = ("checkpoint06-files.json", "checkpoint08-files.json", "checkpoint09-files.json")
PREFIXES = (
    "successor_audit_requests/diagnostics",
    "successor_audit_requests/beike_permission_pilot_r1",
    "successor_audit_requests/revisions/b05-official-tool-repair-r1",
    "successor_audit_requests/revisions/linked-official-continuation-r1",
    "successor_audit_requests/independent-pending-batches-review-r1",
    "successor_audit_requests/effective_permissions_45_design_r1",
    "checkpoints/sidecar-post09-r1",
)
LINKED = "successor_audit_requests/revisions/linked-official-continuation-r2"
PRIVATE_INPUT_HASHES = {
    "001c37aab9fe84def6d2e9d87c1e6a81d34baf74e62e2f50643c45c1077b5487",
    "f839074801868c1196b0df62916df5c31b40ef894649c522495668cfcbeb3b6d",
    "adff783d74e7f991be110134ff062edfb1992b7dd4353ff25fdfe83f823ac647",
}


def pin(path):
    assert path.is_file() and not path.is_symlink(), path
    raw = path.read_bytes()
    return {"path": str(path.relative_to(PROJECT)), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}, raw


def purpose(path):
    if "linked-official-continuation-r1/" in path:
        return "unexecuted_preserved_first_draft"
    if "linked-official-continuation-r2/" in path:
        return "frozen_linked_source_plan_local_controls_not_root_live_jobs"
    if "b05-official-tool-repair-r1/actual/" in path:
        return "actual_complete_independent_b05_corrective_job_originals"
    if "beike_permission_pilot_r1/actual/" in path or "raw-readback-r1/actual-public/" in path:
        return "public_service_receipts_and_lifetime_metadata_without_PM_AppOps_bodies"
    if "EFFECTIVE_PERMISSION_OBSERVATION.derived.json" in path:
        return "minimal_public_literal_permission_observations_with_private_input_pins"
    if "effective_permissions_45_design_r1/" in path:
        return "design_only_no_executable_requests"
    if "/actual/" in path:
        return "public_APK_manifest_tool_diagnostic_originals"
    return "source_plan_review_or_local_control"


def main():
    baseline, indices = {}, []
    for name in INDEX_NAMES:
        item, raw = pin(PROJECT / "checkpoints" / name)
        indices.append(item)
        value = json.loads(raw)
        for row in value["files"]:
            baseline[row["path"]] = row
    candidates = set()
    excluded = []
    for prefix in PREFIXES:
        directory = PROJECT / prefix
        assert directory.is_dir(), directory
        for path in directory.rglob("*"):
            if not path.is_file():
                continue
            rel = str(path.relative_to(PROJECT))
            if "__pycache__" in path.parts or path.suffix in (".pyc", ".pyo"):
                excluded.append({"path": rel, "reason": "derived_bytecode_not_source_or_original_evidence", "deleted": False})
                continue
            if "/raw-readback-r1/actual/" in rel:
                excluded.append({"path": rel, "reason": "permission_reader_raw_output_not_public", "deleted": False})
                continue
            candidates.add(path)
    # The parent is now executing b06-b13. Select the frozen closure only,
    # never sweep new root_collect/claim/actual files into this snapshot.
    closure_path = PROJECT / LINKED / "SOURCE_REVIEW.json"
    closure_pin, closure_raw = pin(closure_path)
    assert closure_pin["bytes"] == 7227 and closure_pin["sha256"] == "5533cf68bb657139a44166e29f3aa51ef29c4e59132f28e4125c1495f055ac34"
    closure = json.loads(closure_raw)
    assert len(closure["files"]) == 52
    for expected in closure["files"]:
        path = PROJECT / LINKED / expected["file"]
        item, _ = pin(path)
        assert (item["bytes"], item["sha256"]) == (expected["bytes"], expected["sha256"]), path
        candidates.add(path)
    candidates.add(closure_path)
    candidates.add(PROJECT / "successor_audit_requests/revisions/b05-official-tool-repair-r1.app-history-review.md")
    candidates.add(Path(__file__).resolve())
    candidates.add(HERE / "README.md")
    files, unchanged = [], []
    for path in sorted(candidates):
        item, raw = pin(path)
        assert "p4_private_ui" not in path.parts and path.suffix.lower() not in (".apk", ".jar", ".so", ".png", ".jpg", ".key", ".pem"), path
        assert item["sha256"] not in PRIVATE_INPUT_HASHES, path
        raw.decode("utf-8", "strict")
        assert b"\0" not in raw, path
        if item["path"] in baseline:
            previous = baseline[item["path"]]
            assert (item["bytes"], item["sha256"]) == (previous["bytes"], previous["sha256"]), ("PREVIOUS_CHECKPOINT_FILE_CHANGED", path)
            unchanged.append(item)
        else:
            files.append({**item, "purpose": purpose(item["path"])})
    document = {
        "schema": "pocket4-sidecar-checkpoint10-public-increment-v1",
        "parent_checkpoint09_commit": "0138f236da62eb85d2b7b136f47efaf00104ab9e",
        "parent_checkpoint09_tree": "ea875dadf1800ec1147de74e13aa5233bcc6656d",
        "cumulative_reference_indices": indices,
        "files": files, "file_count_excluding_this_manifest": len(files), "total_bytes": sum(r["bytes"] for r in files),
        "unchanged_previously_indexed_files_count": len(unchanged),
        "unchanged_previously_indexed_files": unchanged,
        "excluded_generated_files": excluded,
        "private_PM_AppOps_UI_body_included": False, "APK_JAR_ELF_keys_included": False,
        "frozen_linked_r2_sources_unchanged": True,
        "root_new_b06_to_b13_actuals_and_claims_outside_this_snapshot": True,
        "no_previous_failed_receipts_modified": True, "remote_jobs_submitted_by_this_script": 0,
        "runtime_claims_created_by_this_script": 0, "git_operations_performed": 0,
        "notes": [
            "Only exact public text files owned by this branch are included. No private directory was scanned.",
            "Newly frozen lifecycle/action/installer state is not inferred from this archive snapshot.",
            "The parent may separately add root-owned current b06-b13 submissions and settlement evidence.",
            "The new 45-package permissions artifact is a design only, not runnable process packets.",
        ],
    }
    raw = (json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode("ascii")
    output = HERE / "SOURCE_AND_EVIDENCE_MANIFEST.json"
    with output.open("xb") as stream:
        stream.write(raw)
    actual, reread = pin(output)
    assert reread == raw
    print(json.dumps({"manifest": actual, "files": len(files), "bytes": document["total_bytes"],
                      "previously_indexed_unchanged": len(unchanged), "excluded_bytecode_not_deleted": len(excluded),
                      "private_raw_included": False, "remote_jobs": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
