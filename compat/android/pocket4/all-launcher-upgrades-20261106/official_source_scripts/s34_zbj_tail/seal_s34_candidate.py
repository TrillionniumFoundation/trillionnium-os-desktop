#!/usr/bin/env python3
"""Freeze local s34 source/plan/packet only. Does not start a process or access a device."""
import ast
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXPECTED_SOURCE = "f3801399b9791aa3cc325cd6e7d62a26415ee32d69046ac1d1ccd818fef45c82"
BASE_SHA = "5f85b5b708d5d8bbf1714e3dd342b4161dac970c7ff2779ec6d2bfac841feedd"

def digest(raw):
    return {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}

def emit(name, raw):
    path = HERE/name
    if path.exists():
        if path.read_bytes() != raw:
            raise RuntimeError("EXISTING_DIFFERENT:" + name)
    else:
        with path.open("xb") as f:
            f.write(raw)
            f.flush()
            import os
            os.fsync(f.fileno())
    if path.read_bytes() != raw:
        raise RuntimeError("READBACK:" + name)
    return {"path": name, **digest(raw)}

def encoded(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()

source = (HERE/"resume_zbj_tail_s34_once.py").read_bytes()
base = (HERE/"base-s28.py").read_bytes()
assert digest(source)["sha256"] == EXPECTED_SOURCE
assert digest(base) == {"bytes": 14623, "sha256": BASE_SHA}
ast.parse(source)
controls = json.loads((HERE/"local-controls-final.stdout.json").read_bytes())
assert controls["success"] is True and controls["tests_run"] == 6
assert controls["failures"] == controls["errors"] == controls["skips"] == 0
assert controls["full_fd_identity_restored"] is True
assert controls["source_sha256"] == EXPECTED_SOURCE
assert controls["network_requests"] == controls["curl_executions"] == controls["Main_actions"] == 0

spec = importlib.util.spec_from_file_location("s34_frozen_source", HERE/"resume_zbj_tail_s34_once.py")
worker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(worker)
prior = (HERE/"actual-s28-package-result.json").read_bytes()
assert digest(prior) == {"bytes": 28307, "sha256":
 "d4bac41dee796ae163b4dabeccc87153d6f95c2191cde4a3eeac71fd9c2b3dde"}
actual = json.loads(prior)
assert actual["status"] == "SEGMENTED_TRANSFER_FAILED"
assert actual["segment_counts"] == {"COMPLETE": 41, "FAILED": 1, "SKIPPED_AFTER_OTHER_RANGE_FAILURE": 20}
plan = worker.tail_plan(worker.CANDIDATES[0])
proof = {"schema": "pocket4-zbj-s34-static-range-proof-v1",
         "source": {"path": "resume_zbj_tail_s34_once.py", **digest(source)},
         "actual_s28_reference": {"job_id": "1a1b0f20329-fc05-7444",
                                 "path": "actual-s28-package-result.json", **digest(prior)},
         "prior_status_preserved": "SEGMENTED_TRANSFER_FAILED",
         "original_prefix_bytes": 38387712, "reused_complete_s28_indices": list(range(41)),
         "reused_segment_bytes_each": 2097152, "verified_prefix_bytes_expected": 124370944,
         "failed_s28_index": 41, "failed_partial_bytes_excluded": 147456,
         "total_bytes": 166873622, "tail_bytes": 42502678, "range_count": 41,
         "ranges": [{"index": i, "start": s, "end": e, "bytes": e-s+1} for i,s,e in plan],
         "concurrency": 1, "attempts_per_new_range": 1, "automatic_retries": 0,
         "old_range_namespace": "S28_PREFIX_2M", "new_range_namespace": "S34_TAIL_1M_NO_CACHE",
         "same_url_as_s28": worker.CANDIDATES[0]["url"] == actual["url"],
         "current_source_identity_validation": "REQUIRED_AT_EXECUTION_NOT_OBSERVED_LOCALLY",
         "download_status": "NOT_RUN", "Android_actions": 0, "production_ready": False}
assert proof["same_url_as_s28"] is True
emit("RANGE_PROOF.json", encoded(proof))
patch = "".join(difflib.unified_diff(base.decode().splitlines(keepends=True),
    source.decode().splitlines(keepends=True), fromfile="s28/resume_zbj_missing_s28_once.py",
    tofile="s34/resume_zbj_tail_s34_once.py"))
emit("S34_FROM_S28.patch", patch.encode())
request = {"host": "pocket4", "executable": "/usr/bin/python3",
           "args": ["-B", "-I", "-c", source.decode()], "cwd": "/home/alex/work",
           "idempotency_key": "pocket4-zbj-finite-tail-s34-20261106-r1",
           "timeout_seconds": 2100, "cpu_quota_percent": 100, "memory_max_bytes": 536870912, "nice": 10}
emit("process-request.json", encoded(request))
names = ["resume_zbj_tail_s34_once.py", "base-s28.py", "actual-s28-package-result.json",
         "actual-s28-aggregate.json", "actual-s28-terminal.json", "test_s34_controls.py",
         "local-controls-final.stdout.json", "local-controls-final.stderr.txt", "RANGE_PROOF.json",
         "S34_FROM_S28.patch", "process-request.json", "README.md", "seal_s34_candidate.py"]
files = [{"path": name, **digest((HERE/name).read_bytes())} for name in names]
manifest = {"schema": "pocket4-zbj-s34-frozen-candidate-r1", "files": files,
            "local_controls_passed": True, "remote_download_submitted": False,
            "host_root": str(worker.ROOT), "idempotency_key": request["idempotency_key"],
            "download_status": "NOT_RUN", "signature_verification": "NOT_RUN",
            "Android_actions": 0, "Main_locks_or_process_fds": 0, "installs": 0, "production_ready": False,
            "worker_total_deadline_seconds": 1800, "outer_timeout_seconds": 2100,
            "original_failed_partial_reused": False,
            "candidate_gate_after_transfer": "REAL_VENDOR_SIGNATURE_PACKAGE_VERSION_ABI_BEFORE_ANY_INSTALL",
            "prior_failed_attempt_unchanged": True}
row = emit("SOURCE_PINS.json", encoded(manifest))
print(json.dumps({"manifest": row, "source": files[0],
                  "request": next(x for x in files if x["path"] == "process-request.json"),
                  "files": len(files), "remote_actions": 0}, sort_keys=True))

