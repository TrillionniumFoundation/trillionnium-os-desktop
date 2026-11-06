#!/usr/bin/env python3
"""Local coordinator gate for 13 durable audit jobs; never start a process.

Only a new final-scope plan can be claimed. Each collector owns its action lock.
Every claimed batch must settle before another can be offered. No retry entry.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import ast
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import zlib

MAX_RESULT = 512 * 1024
COLLECTOR_SHA = "faff199c1f6218b3c01d87e44be610d6fa211de396b5e8c862c188dec59d284a"
HERE = Path(__file__).resolve().parent


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    def constant(value):
        raise RuntimeError("NONFINITE_JSON_NUMBER")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def read(path, limit):
    need(path.is_file() and not path.is_symlink(), "LOCAL_REGULAR_RECEIPT_REQUIRED")
    raw = path.read_bytes()
    need(0 < len(raw) <= limit, "LOCAL_RECEIPT_BYTE_BOUND")
    return raw


def load_plan(path, digest):
    raw = read(path, 262144)
    need(sha(raw) == digest, "FROZEN_PLAN_PIN_CHANGED")
    plan = parse(raw)
    need(plan.get("schema") == "pocket4-successor-apk-audit-prepared-requests-v1" and
         plan["collector"]["sha256"] == COLLECTOR_SHA and plan["collector"]["bytes"] == 29242,
         "EXACT_REVIEWED_COLLECTOR_PLAN_REQUIRED")
    need(plan["phase"] in ("initial-reference", "post-upgrades") and
         len(plan["batches"]) == 13 and plan["partition"]["launcher_packages"] == 45 and
         plan["partition"]["actual_scope_APK_bytes_checked_locally"] is True,
         "COMPLETE_BOUNDED_13_BATCH_PLAN_REQUIRED")
    if plan["phase"] == "post-upgrades":
        need(not plan["app_scope"]["path"].endswith("/initial-app-scope.private.json"),
             "FINAL_VERSIONED_APP_SCOPE_REQUIRED")
    source = read(HERE / "reference/audit_successor_apks.py", 65536)
    need(len(source) == 29242 and sha(source) == COLLECTOR_SHA, "LOCAL_REVIEWED_COLLECTOR_SOURCE_PIN")
    assignments = [node for node in ast.parse(source).body if isinstance(node, ast.Assign) and
                   any(isinstance(target, ast.Name) and target.id == "PACKAGES" for target in node.targets)]
    need(len(assignments) == 1, "ONE_REVIEWED_PACKAGE_ROSTER_REQUIRED")
    reviewed_packages = ast.literal_eval(assignments[0].value)
    requests, packages = {}, []
    for number, row in enumerate(plan["batches"], 1):
        name = "batch-%02d.request.json" % number
        need(row["batch"] == number and row["local_request_file"] == name, "FIXED_SERIAL_BATCH_ORDER")
        request_raw = read(path.parent / name, 65536)
        need(len(request_raw) == row["request"]["bytes"] and sha(request_raw) == row["request"]["sha256"],
             "FROZEN_REQUEST_PIN_CHANGED")
        request = parse(request_raw)
        need(set(request) == {"schema", "guard", "app_scope", "packages", "output_root", "official_release_assets"} and
             request["schema"] == "pocket4-successor-apk-audit-request-v1" and
             request["guard"] == plan["guard"] and request["app_scope"] == plan["app_scope"] and
             request["packages"] == row["packages"] and request["output_root"] == row["output_root"] and
             0 < len(request["packages"]) <= 4 and 0 < row["logical_APK_bytes"] <= 4*1024**3 and
             0 < row["APK_count"] <= 128, "ONE_PINNED_SCOPE_AND_BOUNDED_BATCH_REQUIRED")
        need(row["coordinator_only_argv"] == ["/usr/bin/python3", "-I", plan["collector"]["path"],
             "--request", row["request"]["path"], "--request-sha256", row["request"]["sha256"]],
             "ONLY_FIXED_COLLECTOR_ARGV_ALLOWED")
        need(re.fullmatch(r"pocket4-successor-apk-audit-[a-z0-9-]+-b%02d-20261106" % number,
                          row["suggested_new_idempotency_key"]), "FIXED_UNIQUE_JOB_KEY_REQUIRED")
        requests[number] = request
        packages.extend(request["packages"])
    need(len(packages) == len(set(packages)) == 45 and set(packages) == set(reviewed_packages) and
         len({r["suggested_new_idempotency_key"] for r in plan["batches"]}) == 13 and
         len({r["output_root"] for r in plan["batches"]}) == 13, "EXACT_UNIQUE_PARTITION_REQUIRED")
    return plan, requests


def decode_artifact(raw):
    envelope = parse(raw)
    need(set(envelope) == {"encoding", "artifact_bytes", "artifact_sha256", "data"} and
         envelope["encoding"] == "zlib-base64" and type(envelope["artifact_bytes"]) is int and
         0 < envelope["artifact_bytes"] <= MAX_RESULT, "EXACT_BOUNDED_WORKER_ENVELOPE_REQUIRED")
    compressed = base64.b64decode(envelope["data"], validate=True)
    need(len(compressed) <= MAX_RESULT + 1024, "COMPRESSED_ARTIFACT_BOUND")
    inflater = zlib.decompressobj()
    artifact = inflater.decompress(compressed, MAX_RESULT + 1)
    need(len(artifact) <= MAX_RESULT and inflater.eof and not inflater.unconsumed_tail and not inflater.unused_data,
         "ONE_COMPLETE_BOUNDED_ZLIB_STREAM_REQUIRED")
    need(len(artifact) == envelope["artifact_bytes"] and sha(artifact) == envelope["artifact_sha256"],
         "ORIGINAL_STDOUT_ARTIFACT_PIN_CHANGED")
    return parse(artifact), artifact


def check_success(plan, row, request, terminal, submitted, raw_stdout):
    need(terminal.get("job_id") == submitted["job_id"] and terminal.get("state") == "succeeded" and
         terminal.get("exit_code") == 0 and all(terminal.get(k) is True for k in
             ("output_complete", "output_durable", "terminal_publication_confirmed")) and
         all(terminal.get(k) is False for k in ("timed_out", "automatic_retry", "cancelled")) and
         terminal.get("log_truncated") is False and not terminal.get("log_errors"),
         "AUTHORITATIVE_SUCCESSFUL_DURABLE_TERMINAL_REQUIRED")
    result, artifact = decode_artifact(raw_stdout)
    need(result.get("schema") == "pocket4-successor-installed-apk-audit-v1" and
         result.get("status") == "ACTUAL_APK_AUDIT_VERIFIED" and result.get("request") == request and
         result.get("packages") == row["packages"] and result.get("errors") == [] and
         all(result.get(k) is True for k in ("snapshot_consistent", "all_commands_succeeded",
             "all_manifests_and_signatures_verified", "all_tool_children_joined", "action_lock_released")) and
         result.get("unjoined_tool_pids") == [], "FULL_ACTUAL_AUDIT_SUCCESS_REQUIRED")
    need(all(type(result.get(k)) is int and result[k] == 0 for k in ("UI_actions", "App_launches", "permission_changes",
             "installs", "Android_namespace_commands", "ADB_commands", "business_data_content_reads")) and
         result.get("automatic_retry") is False and result.get("production_ready") is False and
         result.get("effective_permission_grants") == "UNKNOWN_NOT_QUERIED", "READ_ONLY_AUDIT_BOUNDARY_CHANGED")
    guard = result.get("guard_before", {})
    need(guard.get("schema") == "pocket4-successor-main-guard-v1" and
         guard.get("runtime_epoch_sha256") == plan["runtime_epoch_sha256"] and
         result.get("guard_after") == guard, "SAME_SUCCESSOR_GUARD_REQUIRED")
    fds = result.get("owned_descriptors_final", {})
    need(type(fds.get("acquired")) is int and fds["acquired"] > 0 and fds.get("closed") == fds["acquired"] and
         fds.get("remaining") == 0 and fds.get("errors") == [], "ALL_OBSERVATION_AND_LEASE_FDS_CLOSED_REQUIRED")
    apps = result.get("apps", [])
    need([app.get("package") for app in apps] == row["packages"] and
         sum(len(app.get("apks", [])) for app in apps) == row["APK_count"] and
         len(result.get("commands", [])) == 3 * row["APK_count"], "EVERY_BASE_AND_SPLIT_APK_REQUIRED")
    need(all(all(app.get(field) is True for field in ("complete_APK_set_observed", "one_base_manifest_observed",
         "all_APKs_signature_verified", "all_current_signers_equal_PM_records", "all_manifests_match_PM_identity",
         "all_permission_names_decoded")) for app in apps), "MANIFEST_OR_PM_SIGNER_EVIDENCE_INCOMPLETE")
    need(result.get("collector_source", {}).get("sha256") == COLLECTOR_SHA and
         result.get("collector_source", {}).get("bytes") == 29242, "ACTUAL_COLLECTOR_SOURCE_PIN_REQUIRED")
    # The fixed collector publishes this immutable file before adding exactly these
    # two stdout-only fields. Match its published pin, without pretending to reread it remotely.
    file_result = dict(result)
    receipt = file_result.pop("final_receipt", None)
    file_result.pop("owned_descriptors_final")
    file_raw = canonical(file_result) + b"\n"
    need(type(receipt) is dict and receipt.get("path") == row["output_root"] + "/result.json" and
         receipt.get("bytes") == len(file_raw) and receipt.get("sha256") == sha(file_raw),
         "DURABLE_RESULT_PUBLICATION_PIN_REQUIRED")
    return {"batch": row["batch"], "job_id": submitted["job_id"], "artifact_bytes": len(artifact),
            "artifact_sha256": sha(artifact), "stdout_sha256": sha(raw_stdout), "final_receipt": receipt,
            "FDs_closed": fds["closed"], "all_tool_children_joined": True,
            "receipt_pin_reconstructed_from_original_stdout_not_new_remote_read": True}


def inspect(plan, requests, plan_sha, state_dir):
    completed = []
    existing = {path.name for path in state_dir.iterdir()} if state_dir.exists() else set()
    allowed = {"batch-%02d" % n for n in range(1, 14)}
    need(existing <= allowed, "UNEXPECTED_SERIAL_STATE_ENTRY")
    for row in plan["batches"]:
        number = row["batch"]
        folder = state_dir / ("batch-%02d" % number)
        if not folder.exists():
            need(not any((state_dir / ("batch-%02d" % later)).exists() for later in range(number+1, 14)),
                 "OUT_OF_ORDER_BATCH_STATE_NO_ADVANCE")
            return {"state": "NEXT_READY", "completed": completed, "next": row,
                    "worker_internal_deadline_seconds": 840, "recommended_job_timeout_seconds": 960,
                    "maximum_jobs": 13, "automatic_retry": False}
        need(folder.is_dir() and not folder.is_symlink(), "OWNED_BATCH_DIRECTORY_REQUIRED")
        intent = parse(read(folder / "intent.json", 65536))
        need(intent.get("schema") == "pocket4-audit-coordinator-intent-v1" and intent.get("plan_sha256") == plan_sha and
             intent.get("request") == row["request"] and intent.get("idempotency_key") == row["suggested_new_idempotency_key"],
             "IMMUTABLE_BATCH_CLAIM_CHANGED")
        required = ("submitted-job.json", "terminal.original.json", "stdout.original.json")
        if not all((folder / name).exists() for name in required):
            return {"state": "STOP_UNSETTLED_BATCH", "batch": number, "completed": completed,
                    "idempotency_key": intent["idempotency_key"], "automatic_retry": False,
                    "next_action": "Reconcile this existing submission and preserve its original evidence; do not create a new key."}
        submitted = parse(read(folder / "submitted-job.json", 65536))
        need(set(submitted) == {"job_id", "idempotency_key", "request_sha256", "plan_sha256"} and
             isinstance(submitted["job_id"], str) and submitted["job_id"] and
             submitted["idempotency_key"] == intent["idempotency_key"] and submitted["plan_sha256"] == plan_sha and
             submitted["request_sha256"] == row["request"]["sha256"], "ACTUAL_SUBMISSION_BINDING_REQUIRED")
        terminal = parse(read(folder / "terminal.original.json", 65536))
        stdout = read(folder / "stdout.original.json", 1024*1024)
        completed.append(check_success(plan, row, requests[number], terminal, submitted, stdout))
    return {"state": "ALL_13_APK_AUDITS_SETTLED", "completed": completed, "jobs": 13,
            "packages": 45, "production_ready": False, "effective_permission_grants": "UNKNOWN_NOT_QUERIED",
            "automatic_retry": False}


def claim(state_dir, decision, plan_sha):
    need(decision["state"] == "NEXT_READY", "ONLY_UNCLAIMED_NEXT_BATCH_CAN_BE_CLAIMED")
    row = decision["next"]
    state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    folder = state_dir / ("batch-%02d" % row["batch"])
    folder.mkdir(mode=0o700)
    intent = {"schema": "pocket4-audit-coordinator-intent-v1", "plan_sha256": plan_sha,
              "request": row["request"], "idempotency_key": row["suggested_new_idempotency_key"],
              "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "automatic_retry": False}
    path = folder / "intent.json"
    with path.open("xb") as handle:
        handle.write(canonical(intent) + b"\n"); handle.flush(); os.fsync(handle.fileno())
    for path_to_sync in (folder, state_dir, state_dir.parent):
        directory = os.open(path_to_sync, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    return {**decision, "state": "CLAIMED_FOR_ONE_COORDINATOR_SUBMISSION", "intent_path": str(path),
            "process_started_by_gate": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("status", "claim-next"))
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        plan, requests = load_plan(args.plan, args.plan_sha256)
        if plan["phase"] != "post-upgrades":
            need(args.operation == "status", "INITIAL_REFERENCE_CANNOT_BE_CLAIMED_AS_FINAL_AUDIT")
            decision = {"state": "INITIAL_REFERENCE_ONLY_WAIT_FOR_FINAL_SCOPE", "batches": 13,
                        "packages": 45, "actual_scope_capacity_checked": True, "runtime_jobs_submitted": 0}
        else:
            decision = inspect(plan, requests, args.plan_sha256, args.state_dir)
            if args.operation == "claim-next":
                decision = claim(args.state_dir, decision, args.plan_sha256)
        print(json.dumps(decision, sort_keys=True, ensure_ascii=True), flush=True)
        return 0 if decision["state"] not in ("STOP_UNSETTLED_BATCH",) else 2
    except BaseException as error:
        print(json.dumps({"state": "STOP_NO_RETRY", "reason": str(error)[:300], "type": type(error).__name__,
                          "runtime_jobs_submitted": 0, "automatic_retry": False}, sort_keys=True), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
