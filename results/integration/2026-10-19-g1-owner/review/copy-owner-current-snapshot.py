#!/usr/bin/env python3
"""Append the exact later owner CI snapshot and preserve the earlier frozen records."""

import argparse
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    original = args.source.read_bytes()
    digest = hashlib.sha256(original).hexdigest()
    assert digest == "44f827e2adbf792e9cb418344f6a7d4d6c3e59e55c47fe13d41b7aa1553ec1c4"
    snapshot = json.loads(original)
    head = "d32e795f0d24df89fc57745f6fae70fbd0642eba"
    assert snapshot["source_head"] == head
    pr = next(item["response"] for item in snapshot["sources"] if "merged" in item["response"])
    checks = next(item["response"]["check_runs"] for item in snapshot["sources"] if "check_runs" in item["response"])
    jobs = next(item["response"]["jobs"] for item in snapshot["sources"] if "jobs" in item["response"])
    counts = dict(Counter(item["conclusion"] if item["status"] == "completed" else item["status"] for item in checks))
    assert len(checks) == 49 and all(item["head_sha"] == head for item in checks)
    assert counts == {"failure": 8, "success": 24, "skipped": 6, "neutral": 1, "cancelled": 9, "in_progress": 1}
    assert len(jobs) == 37
    assert pr["head"]["sha"] == head and pr["state"] == "open" and pr["merged"] is False and pr["draft"] is False
    assert pr["mergeable_state"] == "blocked"
    aggregates = {117860094573, 117859935693}
    failures = [item for item in checks if item["conclusion"] == "failure"]
    assert len([item for item in failures if item["id"] in aggregates]) == 2
    assert not args.destination.exists()
    args.destination.parent.mkdir(parents=True, exist_ok=True)
    args.destination.write_bytes(original)
    assert args.destination.read_bytes() == original == args.source.read_bytes()
    receipt = {
        "schema": "r10.owner-ci-later-snapshot-copy.v1",
        "copied_at_utc": datetime.now(timezone.utc).isoformat(),
        "observed_at_utc": snapshot["observed_at_utc"],
        "source_head": head,
        "source": str(args.source),
        "destination": str(args.destination),
        "bytes": len(original),
        "sha256": digest,
        "raw_source_before_and_after_and_copy_equal": True,
        "check_count": len(checks),
        "check_state_counts": counts,
        "blocking_run_jobs": len(jobs),
        "failure_checks": [{"id": item["id"], "name": item["name"], "completed_at": item["completed_at"], "kind": "aggregate_gate" if item["id"] in aggregates else "actual_job"} for item in failures],
        "PR": {"number": pr["number"], "state": pr["state"], "draft": pr["draft"], "merged": pr["merged"], "mergeable_state": pr["mergeable_state"], "base": pr["base"]["sha"]},
        "older_frozen_snapshots_modified": False,
        "new_CI_or_product_runs": 0,
        "limits": ["Eight failing check objects include two aggregate gates and are not eight independent defects.", "New shard 1/3 state and later cancellations do not establish a cause or substitute for missing logs.", "The original 01:56 security snapshot, 02:16 root snapshot and 02:24 Bazel snapshot remain unchanged."],
        "status": "passed_exact_append_and_snapshot_classification",
    }
    args.receipt.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": receipt["status"], "bytes": len(original), "sha256": digest, "checks": counts, "PR": receipt["PR"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
