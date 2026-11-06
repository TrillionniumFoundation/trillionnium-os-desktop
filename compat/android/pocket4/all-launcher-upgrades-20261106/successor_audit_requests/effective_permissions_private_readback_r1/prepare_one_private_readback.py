#!/usr/bin/env python3
"""Prepare one exact two-log host reader after that target's real capture PASS.

Local source generation only. It never submits or claims a process, reads raw
private service bodies, or accepts a caller-supplied remote pathname.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
CAPTURE = PROJECT / "successor_audit_requests/effective_permissions_45_capture_r1"
OLD = PROJECT / "successor_audit_requests/beike_permission_pilot_r1/raw-readback-r1"
GATE_SHA = "dc4fffb3f11e8428db732b96cd1925f0bdce239cdce81ff64ab369dc14c751f4"
OLD_READER_SHA = "222a42555dead8c8cf72a8de175b6318618db1e2ddab6ee6ddd6eccc7263e5c1"
OLD_PACKET_SHA = "902310c86c1bd26cc96d3cd5216f00beea7f15b3a4722f460f6571fb3ba9de35"


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def write(folder, name, raw):
    raw = raw.encode() if isinstance(raw, str) else raw
    with (folder / name).open("xb") as stream:
        stream.write(raw)
    need((folder / name).read_bytes() == raw, "NEW_LOCAL_SOURCE_READBACK")
    return {"file": name, "bytes": len(raw), "sha256": sha(raw)}


def definitions(source):
    return {node.name: ast.get_source_segment(source, node) for node in ast.parse(source).body if isinstance(node, ast.FunctionDef)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=int, required=True)
    parser.add_argument("--package", required=True)
    args = parser.parse_args()
    gate_path = CAPTURE / "permission_capture_gate.py"
    raw = gate_path.read_bytes()
    need(len(raw) == 27120 and sha(raw) == GATE_SHA, "EXACT_REVIEWED_CAPTURE_GATE_REQUIRED")
    gate = types.ModuleType("fixed_capture_local_gate"); gate.__file__ = str(gate_path)
    exec(compile(raw, str(gate_path), "exec"), gate.__dict__)
    g, capture_plan, loaded = gate.load_closure()
    need(1 <= args.batch <= 13 and args.package in loaded[args.batch]["row"]["targets"], "ONE_EXACT_FIXED_TARGET_REQUIRED")
    state = gate.inspect(g, capture_plan, loaded)
    completed = next((row for row in state["completed"] if row["batch"] == args.batch), None)
    need(completed is not None, "ACTUAL_SUCCESSFUL_DURABLE_CAPTURE_REQUIRED_BEFORE_READBACK")
    batch = loaded[args.batch]["row"]
    pi = batch["targets"].index(args.package)
    reports = [row for row in completed["service_reports"] if row["target_package"] == args.package]
    need([row["service"] for row in reports] == ["package-dump-package", "appops-get-user0"] and
         all(row["target_user"] == 0 and row["complete"] is True and row["joined"] is True and row["returncode"] == 0 and
             row["stream_artifacts_complete"] is True for row in reports), "TWO_ORIGINAL_COMPLETE_SERVICE_STREAMS_REQUIRED")
    pins = tuple(row["stdout"] for row in reports)
    for index, pin in zip((2 + 2 * pi, 3 + 2 * pi), pins):
        need(set(pin) == {"path", "bytes", "sha256"} and pin["path"] == batch["output_root"] + "/android-%02d.stdout" % index and
             type(pin["bytes"]) is int and 0 <= pin["bytes"] <= 262144, "ONLY_TWO_PINNED_CURRENT_CAPTURE_STDOUT_PATHS")
    old_raw = (OLD / "read_pinned_private_permission_logs.py").read_bytes()
    packet_raw = (OLD / "process-request.review-only.json").read_bytes()
    need(len(old_raw) == 3720 and sha(old_raw) == OLD_READER_SHA and len(packet_raw) == 4091 and sha(packet_raw) == OLD_PACKET_SHA,
         "EXACT_ACTUAL_PILOT_READER_AND_HOST_PROCESS_TEMPLATE_REQUIRED")
    old = old_raw.decode()
    node = next(n for n in ast.parse(old).body if isinstance(n, ast.Assign) and
                any(isinstance(t, ast.Name) and t.id == "PINS" for t in n.targets))
    source = old.replace(ast.get_source_segment(old, node), "PINS = " + repr(pins), 1)
    source = source.replace("Read two exact existing Beike service logs; private raw output, no Main command.",
                            "Read two exact settled target service logs; private raw output, no Main command.")
    source = source.replace("pocket4-two-exact-beike-private-service-logs-v1", "pocket4-two-exact-fixed45-private-service-logs-v1")
    source = source.replace("'permission_observation_job':'1a1b279845c-fc05-7e2e'", "'permission_observation_job':" + repr(completed["job_id"]) +
                            ", 'permission_capture_batch':" + str(args.batch) + ", 'target_package':" + repr(args.package))
    keep = [name for name in definitions(old) if name != "main"]
    need(all(definitions(old)[name] == definitions(source)[name] for name in keep), "ORIGINAL_PINNED_READER_DEFINITIONS_CHANGED")
    compile(source, "read_pinned_private_permission_logs.py", "exec")
    folder = HERE / ("batch-%02d-p%02d" % (args.batch, pi))
    folder.mkdir(mode=0o700)
    rp = write(folder, "read_pinned_private_permission_logs.py", source)
    dp = write(folder, "reader-against-actual-pilot-reader.diff", "".join(difflib.unified_diff(old.splitlines(True), source.splitlines(True),
               fromfile="actual-pilot-private-reader", tofile="one-settled-fixed45-target-private-reader")))
    packet = g.parse(packet_raw)
    packet["idempotency_key"] = "sidecar-evidence-20261106-fixed-permission-logs-r1-b%02d-p%02d" % (args.batch, pi)
    packet["args"][-1] = source
    pp = write(folder, "process-request.review-only.json", canonical(packet))
    private_root = PROJECT.parent / "p4_private_ui/fixed45-permissions-r1" / folder.name
    plan = {"schema": "pocket4-one-target-private-permission-log-readback-plan-v1", "source_only": True,
        "batch": args.batch, "package": args.package, "source_capture_job": completed["job_id"],
        "source_capture_artifact_sha256": completed["artifact_sha256"], "source_capture_terminal_sha256": completed["terminal_sha256"],
        "source_capture_outer_stdout_sha256": completed["outer_stdout_sha256"], "source_capture_joint_gate_passed": True,
        "gate_sha256": GATE_SHA, "capture_plan_sha256": gate.PLAN_SHA, "reader": rp, "process_request": pp, "diff": dp,
        "fixed_files": pins, "maximum_one_file_bytes": 262144, "actual_combined_raw_bytes": sum(p["bytes"] for p in pins),
        "unchanged_reader_definitions": keep, "source_reader_reference": {"file": str((OLD / "read_pinned_private_permission_logs.py").relative_to(PROJECT)),
            "bytes": len(old_raw), "sha256": OLD_READER_SHA, "actual_successful_readback_job": "1a1b27e6086-fc05-7e44"},
        "private_destination_required": str(private_root), "private_destination_created_by_this_preparer": False,
        "private_items": ["complete reader stdout", "all process_read bodies", "both decoded service logs"],
        "public_items": ["source", "fixed input pins", "process request", "start and terminal metadata", "hash-only readback receipt"],
        "reader_requires_durable0_full_stdout_and_FD_retirement": True,
        "whole_process_FD_gate_is_original_count_check": True, "individual_held_and_path_file_FD_identity_is_full_stat": True,
        "raw_output_repository_publication_admitted": False, "raw_semantics_interpreted_here": False,
        "arbitrary_remote_path_accepted": False, "remote_jobs": 0, "ledger_claims": 0,
        "Main_reads": 0, "Android_commands": 0, "permission_changes": 0}
    mp = write(folder, "READBACK_PLAN.json", canonical(plan))
    print(json.dumps({"folder": str(folder), "plan": mp, "reader": rp, "process_request": pp,
                      "target": args.package, "source_capture_job": completed["job_id"], "remote_jobs": 0, "ledger_claims": 0}, indent=2))


if __name__ == "__main__":
    main()
