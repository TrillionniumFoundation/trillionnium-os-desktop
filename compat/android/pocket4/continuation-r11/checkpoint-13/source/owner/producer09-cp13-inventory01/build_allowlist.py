#!/usr/bin/env python3
"""Bind only additions to the exact 587-blob CP12 producer inventory."""
from pathlib import Path
import collections
import hashlib
import json

WORK = Path(__file__).resolve().parent
BASE = WORK.parent
ROOT = BASE.parent
EVIDENCE = ROOT / "root-recovery-20261104-02/evidence"
NATIVE = ROOT / "native-recovery-20261105-02"

ROOTS = {
    "peer-builder451-bound-source01": BASE / "peer-builder451-bound-source01",
    "producer08-cgroup-mount-mechanism01": BASE / "cgroup-mount-mechanism-freeze-01",
    "producer08-cgroup-mount-mechanism02": BASE / "cgroup-mount-mechanism-freeze-02",
    "producer08-cgroup-mount-mechanism03": BASE / "cgroup-mount-mechanism-freeze-03",
    "producer08-owner-normal01-cgroup-reference-reader01": BASE / "owner08-cgroup-source-read01",
    "producer08-owner-normal01-cgroup-reference01": BASE / "owner08-cgroup-analysis01/reference",
    "producer08-owner-normal01-journal-window02": BASE / "owner08-journal-window02-freeze-01",
    "producer09-bootstrap-leaf-peer01": NATIVE / "peer-leaf-source01",
    "producer09-bootstrap-leaf-source-only01": BASE / "cgroup-bootstrap-leaf-source-freeze-01",
    "producer09-cgroup-controller01": BASE / "producer09-cgroup-controller-freeze-01",
    "producer09-cgroup-handoff-source01": BASE / "cgroup-handoff-pair-freeze-01",
    "producer09-holding-abi3-peer01": NATIVE / "peer-holding-abi3-source01",
    "producer09-init-cgroup-handoff-build01-read01": BASE / "init-cgroup-handoff-build01-read-freeze-01",
    "producer09-init-cgroup-handoff-build01": BASE / "init-cgroup-handoff-build-freeze-01",
    "producer09-ordinary-request01": BASE / "producer09-ordinary-request-freeze-01",
    "producer09-owner-next-generators01": BASE / "owner09-normal-work-01",
    "producer09-owner-normal-source01": BASE / "owner09-normal-source-freeze-01",
    "producer09-owner-normal01-local-validation": BASE / "owner09-normal-work-01",
    "producer09-owner-normal01": BASE / "owner09-normal01-freeze-01",
}
EXACT_FILES = {
    "producer08-cgroup-mount-mechanism03-actual01/result.json": EVIDENCE / "owner-cgroup-mount-mechanism03/result.json",
    "producer08-cgroup-mount-mechanism03-actual01/local-source-binding-review.json": BASE / "cgroup-mount-mechanism03-actual-review01/report.json",
    "producer09-owner-normal-plan-generator01/freeze_normal09.py": BASE / "owner09-normal-work-01/freeze_normal09.py",
    "producer09-owner-normal-plan-generator01/status.json": WORK / "restored-generator-status.json",
}


def main():
    original = json.loads((WORK / "git-inventory.json").read_bytes())
    assert original["base"] == "e673748fd73cc814cfa80f31fae6c5b00d77876b"
    assert original["base_blobs"] == 587 and original["total_blobs"] == 797
    assert original["tree"] == "9c9768b1c9a612e043d640c16a818a559cab28db"
    assert len(original["additions"]) == 210
    rows = []
    for item in original["additions"]:
        relative = item["path"]
        if relative in EXACT_FILES:
            path = EXACT_FILES[relative]
        else:
            prefix, tail = relative.split("/", 1)
            path = ROOTS[prefix] / tail
        raw = path.read_bytes()
        raw.decode("utf-8")
        digest = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        assert len(raw) == item["bytes"] and digest == item["git_blob_sha1"], relative
        assert not path.is_symlink() and "/private/" not in str(path)
        rows.append({
            "path": relative, "origin_path": relative, "origin_tree": original["tree"],
            "local_path": str(path), "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "git_blob_sha1": digest, "encoding": "utf-8",
        })
    counts = dict(collections.Counter(row["path"].split("/")[0] for row in rows))
    report = {
        "schema": "pocket4-cp13-producer-additions-v1",
        "base_inventory_tree": original["base"], "base_blobs": 587,
        "base_blobs_changed": 0, "base_rows_rewritten": False,
        "source_tree": original["tree"], "source_tree_blobs": 797,
        "new_files": len(rows), "new_bytes": sum(row["bytes"] for row in rows),
        "all_git_blob_bytes_and_local_UTF8_verified": True,
        "groups": counts, "files": rows,
        "scope": {
            "mechanism02_original_actual_failure_retained": True,
            "mechanism03_actual_owned_mount_PASS": True,
            "mechanism03_not_retroactive_owner08_cause_proof": True,
            "producer09_actual_matching_Rust_compile_and_ordinary_PASS": True,
            "init_ABI3_actual_matching_Android_build_and_host_controls_PASS": True,
            "NORMAL09_prepare_frozen": True,
            "NORMAL09_runtime_executed_at_this_snapshot": False,
            "old_generator_status_is_historical": True,
            "private_raw_journals_or_binary_artifacts_included": False,
            "Main_deployed": False, "all_Apps_production_ready": False,
        },
    }
    raw = (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode()
    target = WORK / "CP13_OWNER_ADDITIONS.json"
    with target.open("xb") as stream:
        stream.write(raw)
    print(json.dumps({"path": str(target), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
        "new_files": len(rows), "new_bytes": report["new_bytes"], "old_blobs_unchanged": 587,
        "source_tree": original["tree"]}, indent=2))


if __name__ == "__main__":
    main()
