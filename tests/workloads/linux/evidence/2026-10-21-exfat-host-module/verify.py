#!/usr/bin/env python3
"""Verify retained failure bytes and original receipt relationships."""
import gzip
import hashlib
import json
from pathlib import Path

root = Path(__file__).resolve().parent
receipt = json.loads((root / "receipt.json").read_text())


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


for name, record in receipt["evidence_files"].items():
    data = (root / name).read_bytes()
    require(len(data) == record["bytes"] and sha(data) == record["sha256"], name)
raw = gzip.decompress((root / "original-job.log.gz").read_bytes())
original = receipt["original_decoded_job_log"]
require(len(raw) == original["decoded_bytes"] and sha(raw) == original["decoded_sha256"], "decoded job log")
reference = json.loads((root / "failed-reference.json").read_text())
for name, key in [("failed-reference-input.json", "frozen_input_sha256"),
                  ("failed-bundle-inputs.json", "bundle_sha256"),
                  ("failed-reference.stdout.log", "stdout_sha256"),
                  ("failed-reference.stderr.log", "stderr_sha256")]:
    require(sha((root / name).read_bytes()) == reference[key], name + " original relationship")
require((root / "failed-reference.exit-code.txt").read_bytes() == b"2\n", "original exit code")
require(reference["process_exit"] == 2 and reference["timed_out"] is False,
        "failed run must remain failed")
require(reference["verdict"]["passed"] is False and not reference["verdict"]["observations"],
        "no successful observation may be synthesized")
require(b"errno=19\n" in (root / "failed-reference.stderr.log").read_bytes(), "mount refusal")
print(json.dumps({"verified_failure_files": len(receipt["evidence_files"]),
                  "original_process_exit": 2, "native_rerun_performed": False}))
