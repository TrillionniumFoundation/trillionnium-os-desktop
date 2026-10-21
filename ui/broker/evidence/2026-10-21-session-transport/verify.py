#!/usr/bin/env python3
"""Verify saved bytes and source identity; do not execute Cargo or Rust tests."""
import gzip
import hashlib
import json
from pathlib import Path
import re

root = Path(__file__).resolve().parent
repository = root.parents[3]
receipt = json.loads((root / "receipt.json").read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def summary(data):
    rows = re.findall(rb"test result: (?:ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) ignored;", data)
    return dict(zip(["passed", "failed", "ignored"],
                    [sum(int(row[i]) for row in rows) for i in range(3)]))


logs = {}
for name, record in receipt["logs"].items():
    compressed = (root / name).read_bytes()
    require(len(compressed) == record["bytes"] and sha(compressed) == record["sha256"], name + " compressed bytes")
    require(compressed[4:8] == bytes(4), name + " gzip timestamp")
    raw = gzip.decompress(compressed)
    require(len(raw) == record["decompressed"]["bytes"] and sha(raw) == record["decompressed"]["sha256"], name + " decoded bytes")
    logs[name] = raw
for record in receipt["auxiliary_files"]:
    data = (root / record["path"]).read_bytes()
    require(len(data) == record["bytes"] and sha(data) == record["sha256"], record["path"] + " identity")
for record in receipt["source_inputs"]:
    data = (repository / record["path"]).read_bytes()
    require(len(data) == record["bytes"] and sha(data) == record["sha256"], record["path"] + " source identity")
    require(hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == record["git_blob"], record["path"] + " git blob")
for run in receipt["native_runs"]:
    require(run["local_commit"] == receipt["source_commit"] and run["exit_code"] == 0 and run["sources_unchanged"], "native run identity and exit")
    raw = logs[run["saved_log"]]
    require(sha(raw) == run["log"]["sha256"] and len(raw) == run["log"]["bytes"], "original native log bytes")
    if run["test_summary"] is not None:
        require(summary(raw) == run["test_summary"], "native test count")
controls = receipt["negative_controls"]
require(controls["source_commit"] == receipt["source_commit"] and controls["source_unchanged"], "negative source identity")
require(len(controls["controls"]) == 3, "three isolated controls")
for control in controls["controls"]:
    original = (repository / control["path"]).read_bytes()
    before, replacement = control["before"].encode(), control["replacement"].encode()
    require(sha(original) == control["original_sha256"] and original.count(before) == 1, "unique original mutation")
    require(sha(original.replace(before, replacement, 1)) == control["mutant_sha256"], "exact mutant bytes")
    raw = logs[control["saved_log"]]
    require(control["expected_red"] and control["exit_code"] == 101, "negative exit")
    require(control["expected_diagnostic"].encode() in raw, "negative runtime assertion")
    require(summary(raw) == {"passed": 0, "failed": 1, "ignored": 0}, "negative runtime count")
prior = receipt["prior_standalone_check"]
require(prior["exit_code"] == 101 and b"error[E0277]" in logs[prior["saved_log"]], "prior compile failure preserved")
prior_joint = receipt["prior_joint_native"]
require(prior_joint["local_commit"] != receipt["source_commit"] and prior_joint["exit_code"] == 0, "prior joint source stays separate")
require(summary(logs[prior_joint["saved_log"]]) == {"passed": 74, "failed": 0, "ignored": 0}, "prior joint count")
prior_controls = receipt["prior_negative_attempt"]["controls"]
require([row["expected_red"] for row in prior_controls] == [True, True, False], "prior attempt is not three runtime controls")
require(b"error[E0277]" in logs[prior_controls[2]["saved_log"]], "prior client control compiled unsuccessfully")
print(json.dumps({"source_commit": receipt["source_commit"], "saved_logs_verified": len(logs),
                  "final_distinct_tests": 74, "standalone_broker_tests": 33,
                  "runtime_negative_controls": 3, "rust_tests_rerun": False}))
