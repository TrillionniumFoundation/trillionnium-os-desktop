#!/usr/bin/env python3
"""Verify saved output bytes and summaries; this does not execute Rust tests."""
import gzip
import hashlib
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parent
receipt = json.loads((root / "receipt.json").read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


raw_logs = {}
for name, record in receipt["logs"].items():
    payload = (root / name).read_bytes()
    require(len(payload) == record["bytes"], name + " compressed length")
    require(hashlib.sha256(payload).hexdigest() == record["sha256"], name + " compressed hash")
    require(payload[4:8] == bytes(4), name + " gzip timestamp")
    raw = gzip.decompress(payload)
    require(len(raw) == record["decompressed"]["bytes"], name + " decoded length")
    require(hashlib.sha256(raw).hexdigest() == record["decompressed"]["sha256"], name + " decoded hash")
    raw_logs[name] = raw

for run in receipt["runs"]:
    expected = run["test_summary"]
    if expected is None:
        continue
    summaries = re.findall(rb"test result: (?:ok|FAILED)\. (\d+) passed; (\d+) failed;", raw_logs[run["log"]])
    actual = {"passed": sum(int(p) for p, _ in summaries), "failed": sum(int(f) for _, f in summaries)}
    require(actual == expected, run["log"] + " recorded test summary")

print(json.dumps({"verified_saved_logs": len(raw_logs), "rust_tests_rerun": False,
                  "recorded_unique_service_tests_passed": receipt["result"]["unique_cpu_feature_service_tests"]}))
