#!/usr/bin/env python3
"""Prepare a fixed host reader only after one new46 capture fully settled.

No claim, remote submission, Main command or private service body is read here.
Every future log pin is obtained from an actual complete new-series receipt.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import difflib
import hashlib
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
GATE_SHA = "9a38444242ef45aa5f7f94d2595d7a6aa342d7249973e200ec8ea63ae42da898"
PLAN_SHA = "facee24ef983eafb0324cf34dc803f5590599ec4ae4d0126015995679b019abc"
RENDERER = {"file": "successor_audit_requests/effective_permissions_batch_readback_r2/prepare_compressed_readback.py",
            "bytes": 11301, "sha256": "ff4344162b5f552bf5c8365f1fa198ef1a8dff6259861a838872f5cf6bb69356"}


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path, digest, length=None):
    raw = path.read_bytes()
    need(sha(raw) == digest and (length is None or len(raw) == length), "EXACT_FROZEN_LOCAL_SOURCE_REQUIRED")
    module = types.ModuleType(path.stem)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def select_complete(number):
    need(type(number) is int and 1 <= number <= 14, "EXACT_NEW14_BATCH_RANGE")
    gate = load(HERE / "permission_capture_gate.py", GATE_SHA, 29733)
    need(sha((HERE / "CAPTURE_PLAN.json").read_bytes()) == PLAN_SHA, "EXACT_NEW46_CAPTURE_PLAN")
    g, plan, loaded = gate.load_closure()
    state = gate.inspect(g, plan, loaded)
    matches = [row for row in state["completed"] if row["batch"] == number]
    need(len(matches) == 1, "NO_READER_FOR_FAILED_UNKNOWN_OR_UNOBSERVED_NEW_BATCH")
    complete, row = matches[0], loaded[number]["row"]
    need(complete["target_packages"] == row["targets"] and complete.get("whole_49_current_identity_checked") is True and
         complete.get("original_owned_child_pidfd_retirement_verified") is True and
         complete.get("interpretation_status") == "RAW_CAPTURE_ONLY_NOT_INTERPRETED", "FULL_ACTUAL_NEW_CAPTURE_JOINT_REQUIRED")
    reports = complete["service_reports"]
    expected = [(p, service) for p in row["targets"] for service in ("package-dump-package", "appops-get-user0")]
    need([(r["target_package"], r["service"]) for r in reports] == expected and 2 <= len(reports) <= 8,
         "EXACT_TWO_SERVICE_LOGS_PER_ACTUAL_TARGET")
    pins, limits, mapping = [], [], []
    for index, report in enumerate(reports, 2):
        cap = 2097152 if number == 2 and index == 2 else 262144
        need(report["complete"] is True and report["joined"] is True and report["stream_artifacts_complete"] is True and
             type(report["returncode"]) is int and report["returncode"] == 0 and report["target_user"] == 0,
             "ONLY_ACTUAL_COMPLETE_SUCCESSFUL_CAPTURE_STREAMS")
        item = report["stdout"]
        need(set(item) == {"path", "bytes", "sha256"} and
             item["path"] == row["output_root"] + "/android-%02d.stdout" % index and
             type(item["bytes"]) is int and 0 <= item["bytes"] <= cap and
             type(item["sha256"]) is str and len(item["sha256"]) == 64 and
             all(c in "0123456789abcdef" for c in item["sha256"]), "EXACT_ACTUAL_LOG_PATH_HASH_AND_LIMIT")
        pins.append(dict(item)); limits.append(cap)
        mapping.append({"target_package": report["target_package"], "target_user": 0, "service": report["service"],
                        "maximum_body_bytes": cap, "pin": dict(item)})
    need(len(pins) == len({p["path"] for p in pins}) and sum(p["bytes"] for p in pins) <= 2097152,
         "ORIGINAL_BOUNDED_COMPLETE_BATCH_AGGREGATE")
    binding = {"source_capture_batch": number, "source_capture_job": complete["job_id"],
        "source_capture_artifact_sha256": complete["artifact_sha256"],
        "source_capture_outer_stdout_sha256": complete["outer_stdout_sha256"],
        "source_capture_terminal_sha256": complete["terminal_sha256"], "target_log_mapping": mapping,
        "capture_series": "NEW_FIXED46_CURRENT49", "capture_plan_sha256": PLAN_SHA,
        "app_scope": plan["app_scope"], "runtime_epoch_sha256": plan["runtime_epoch_sha256"],
        "target_identities": row["target_identities"], "raw_capture_is_semantic_grant_proof": False,
        "original_failed_capture_reclassified": False, "role_status": "UNKNOWN_NOT_QUERIED"}
    return gate, g, plan, loaded, complete, pins, limits, binding


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", required=True, type=int)
    args = parser.parse_args()
    gate, g, plan, loaded, complete, pins, limits, binding = select_complete(args.batch)
    renderer = load(PROJECT / RENDERER["file"], RENDERER["sha256"], RENDERER["bytes"])
    source, original = renderer.render_reader(pins, limits, binding)
    packet_raw = (renderer.PILOT / "process-request.review-only.json").read_bytes()
    need(len(packet_raw) == 4091 and sha(packet_raw) == renderer.PACKET_SHA, "ORIGINAL_ACTUAL_HOST_READER_PACKET")
    packet = json.loads(packet_raw)
    packet["args"][-1] = source
    packet["idempotency_key"] = "pocket4-fixed46-permission-readback-20261107-r1-b%02d" % args.batch
    parent = HERE / "readbacks"
    parent.mkdir(mode=0o700, exist_ok=True)
    need(parent.is_dir() and not parent.is_symlink(), "REGULAR_NEW_READER_PARENT")
    out = parent / ("batch-%02d" % args.batch)
    out.mkdir(mode=0o700)
    rp = renderer.write_new(out, "read_fixed_batch_private_logs.py", source)
    pp = renderer.write_new(out, "process-request.review-only.json", renderer.canonical(packet))
    dp = renderer.write_new(out, "reader-against-actual-pilot.diff", "".join(difflib.unified_diff(
        original.splitlines(True), source.splitlines(True), fromfile="actual-pilot-file-reader", tofile="new46-actual-settled-batch-reader")))
    private = PROJECT.parent / "p4_private_ui/fixed46-permissions-compressed-readback-r1" / out.name
    readback = {"schema": "pocket4-fixed-batch-compressed-private-readback-plan-v2", "source_only": True,
        "reader": rp, "process_request": pp, "diff": dp, "capture_binding": binding,
        "fixed_files": pins, "per_file_capture_limits": limits, "actual_aggregate_log_bytes": sum(p["bytes"] for p in pins),
        "maximum_aggregate_body_bytes": 2097152, "maximum_inner_result_bytes": 2 * sum(p["bytes"] for p in pins) + 32768,
        "maximum_compressed_stdout_bytes": 1048576, "complete_original_result_compressed": True,
        "partial_output_admitted": False, "five_original_per_file_functions_unchanged": True,
        "per_file_held_and_path_full_stat_checks": True, "whole_process_FD_gate_is_original_count_check": True,
        "private_destination_required": str(private), "private_stdout_name": "stdout.original.jsonl",
        "public_actual_directory": str(out / "actual-public"), "raw_output_repository_publication_admitted": False,
        "old_single_reader_and_uncompressed_batch_candidate_preserved": True,
        "existing_capture_ledger_modified": False, "remote_jobs": 0, "actual_claims": 0,
        "permission_changes": 0, "role_status": "UNKNOWN_NOT_QUERIED", "production_ready": False}
    mp = renderer.write_new(out, "READBACK_PLAN.json", renderer.canonical(readback))
    # Revalidate actual input and selected stream pins after source-only output.
    again = select_complete(args.batch)
    need(again[4:] == (complete, pins, limits, binding), "CAPTURE_CHANGED_WHILE_PREPARING_READBACK")
    print(json.dumps({"state": "ACTUAL_NEW46_BATCH_PRIVATE_READER_PREPARED_NOT_SUBMITTED", "plan": mp,
        "reader": rp, "process_request": pp, "actual_raw_log_bytes": readback["actual_aggregate_log_bytes"],
        "remote_jobs": 0, "actual_claims": 0, "permissions_interpreted": False}, sort_keys=True))


if __name__ == "__main__":
    main()
