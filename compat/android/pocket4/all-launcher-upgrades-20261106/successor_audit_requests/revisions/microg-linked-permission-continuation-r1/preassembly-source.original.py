#!/usr/bin/env python3
"""Local joint evidence gate; explicit microG correction, original b03-b13.

Status never writes a ledger. A reviewed claim only creates the next previously
unclaimed original batch directory and a separate correction-link receipt.
Original batch 02 remains FAILED and its original serial gate remains STOP.
No host process, namespace, UI, install, grant or service body read occurs here.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
ORIGINAL = PROJECT / "successor_audit_requests/effective_permissions_45_capture_r1"
CORRECTION = PROJECT / "successor_audit_requests/revisions/permissions-microg-b02-correction-r1"
ORIGINAL_GATE_SHA = "dc4fffb3f11e8428db732b96cd1925f0bdce239cdce81ff64ab369dc14c751f4"
INPUT_BYTES = 0  # replaced once by the local closure assembler before freezing
INPUT_SHA = "UNSEALED"
CORRECTION_JOB = "1a1b2d790f2-fc05-7ffb"
OLD_JOB = "1a1b2be17ec-fc05-7f8b"
ROOT = "/home/alex/work/pocket4-microg-permission-correction-observation-20261106-r1"
EMPTY_SHA = hashlib.sha256(b"").hexdigest()
LEDGER = PROJECT / "successor_audit_requests/actual/permissions-fixed45-r1"
READY = "NEXT_READY_AFTER_VERIFIED_MICROG_CORRECTION"


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def module(raw, path, name):
    value = types.ModuleType(name)
    value.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), value.__dict__)
    return value


def clean_command(command):
    need(type(command.get("returncode")) is int and command["returncode"] == 0 and
         all(command.get(k) is True for k in ("complete", "joined", "stdout_eof", "stderr_eof")) and
         command.get("termination_attempted") is False and command.get("errors") == [] and
         type(command.get("host_pid")) is int and command["host_pid"] > 0, "EVERY_COMMAND_MUST_COMPLETE_NORMALLY")


def corrective_stream_pair(command, record, root, prefix):
    need(root == ROOT, "ONLY_FIXED_CORRECTIVE_OUTPUT_ROOT")
    need(record.get("stream_artifacts_complete") is True, "EVERY_RAW_STREAM_MUST_BE_PUBLISHED")
    for name in ("stdout", "stderr"):
        cap = 2097152 if prefix == "android-02" and name == "stdout" else 262144
        pin = record[name]
        need(set(pin) == {"path", "bytes", "sha256"} and pin["path"] == root + "/" + prefix + "." + name and
             type(pin["bytes"]) is int and 0 <= pin["bytes"] <= cap and
             re.fullmatch(r"[0-9a-f]{64}", pin["sha256"]) is not None and
             command.get(name + "_bytes") == pin["bytes"] and command.get(name + "_sha256") == pin["sha256"],
             "RAW_STREAM_PIN_MUST_MATCH_ACTUAL_COMMAND_CAPTURE")
        if pin["bytes"] == 0:
            need(pin["sha256"] == EMPTY_SHA, "EMPTY_STREAM_HASH_MISMATCH")


# CORRECTIVE_SERVICE_GATE_INSERTED_FROM_FROZEN_ORIGINAL


def validate_input_closure(original, g):
    raw = g.read(HERE / "INPUT_CLOSURE.json", 262144)
    need(len(raw) == INPUT_BYTES and sha(raw) == INPUT_SHA, "FROZEN_LINKAGE_INPUT_CLOSURE_CHANGED")
    closure = g.parse(raw)
    need(closure.get("schema") == "pocket4-microg-permission-linkage-input-closure-v1" and
         closure.get("private_service_log_bodies_included") is False and
         closure["file_count"] == len(closure["files"]) and
         len({r["file"] for r in closure["files"]}) == closure["file_count"], "CLOSED_PUBLIC_INPUT_INDEX_REQUIRED")
    records = {row["file"]: original.local_pin(g, row, PROJECT) for row in closure["files"]}
    return closure, records


def read_record(records, path):
    relative = str(path.relative_to(PROJECT))
    need(relative in records, "READ_MUST_BE_IN_FIXED_INPUT_CLOSURE")
    return records[relative]


def validate_correction_source(original, g, loaded, records):
    review = g.parse(read_record(records, CORRECTION / "SOURCE_REVIEW.json"))
    for row in review["files"]:
        raw = read_record(records, CORRECTION / row["file"])
        need(len(raw) == row["bytes"] and sha(raw) == row["sha256"], "EXACT_REVIEWED_CORRECTION_CLOSURE")
    plan = g.parse(read_record(records, CORRECTION / "REPAIR_PLAN.json"))
    request_raw = read_record(records, CORRECTION / "request.review-only.json")
    request = g.parse(request_raw)
    source = read_record(records, CORRECTION / "observe_current_services.py")
    worker = module(source, CORRECTION / "observe_current_services.py", "corrective_source_local_checks_only")
    wrapper_raw = read_record(records, CORRECTION / "owned_readonly_lifetime.py")
    wrapper = module(wrapper_raw, CORRECTION / "owned_readonly_lifetime.py", "corrective_owned_gate_only")
    worker.validate_request(request)
    need(request["guard"] == loaded[2]["request"]["guard"] and request["app_scope"] == loaded[2]["request"]["app_scope"] and
         request["packages"] == loaded[2]["request"]["packages"] and request["target_packages"] == loaded[2]["row"]["targets"] and
         request["target_user"] == 0 and request["batch"] == 2 and
         request["output_root"] == ROOT and request["capture_policy"]["commands"] == loaded[2]["row"]["Android_commands"] and
         plan["original_failure"] == worker.ORIGINAL_FAILURE == request["original_failure"] and
         plan["capture_policy"] == worker.CAPTURE_POLICY == request["capture_policy"], "CORRECTION_MUST_BIND_ORIGINAL_EXACT_SCOPE_AND_COMMANDS")
    old_transport = original.remote_local_pin(g, loaded[2]["row"]["transport"], loaded[2]["row"]["transport_file"])
    need(old_transport == read_record(records, CORRECTION / "readonly_services_transport.py"), "ORIGINAL_TRANSPORT_BYTES_MUST_REMAIN")
    old_source = original.remote_local_pin(g, loaded[2]["row"]["worker"], loaded[2]["row"]["worker_file"])
    old_owned = original.remote_local_pin(g, loaded[2]["row"]["wrapper"], loaded[2]["row"]["wrapper_file"])
    for before, after, names in ((old_source, source, plan["unchanged_worker_definitions"]),
                                 (old_owned, wrapper_raw, plan["unchanged_owned_wrapper_definitions"])):
        old_defs, new_defs = original.definitions(before), original.definitions(after)
        need(all(old_defs[name] == new_defs[name] for name in names), "ORIGINAL_FROZEN_DEFINITIONS_CHANGED")
    packet = g.parse(read_record(records, CORRECTION / "process-request.review-only.json"))
    stager_raw = read_record(records, CORRECTION / "stage_and_run_services.py")
    stage = original.constants(stager_raw)
    payload = g.parse(packet["stdin"].encode())
    need(stage["ROOT"] == plan["source_root"] and stage["FILES"] == plan["stage_files"] and
         payload == g.parse(read_record(records, CORRECTION / "stage.stdin.original.json")) and
         set(payload) == {"schema", "files"} and payload["schema"] == "pocket4-microg-permission-correction-source-stage-v1" and
         len(payload["files"]) == len(plan["stage_files"]) == 9, "EXACT_CORRECTION_STAGE_AND_NINE_MEMBERS")
    for item, pin in zip(payload["files"], plan["stage_files"]):
        body = item["text"].encode("utf-8")
        need(set(item) == {"name", "text"} and item["name"] == pin["name"] and len(body) == pin["bytes"] and
             sha(body) == pin["sha256"] and body == read_record(records, CORRECTION / pin["name"]), "ACTUAL_STAGED_SOURCE_BYTES_CHANGED")
    need(packet == {"host": "pocket4", "executable": "/usr/bin/sudo", "args": ["-n", "/usr/bin/python3", "-I", "-B", "-c", stager_raw.decode()],
         "cwd": "/", "stdin": read_record(records, CORRECTION / "stage.stdin.original.json").decode(), "cpu_quota_percent": 100,
         "memory_max_bytes": 1073741824, "nice": 10, "timeout_seconds": 1100, "idempotency_key": plan["idempotency_key"]},
         "EXACT_NEW_REQUEST_NO_CHANGED_RESOURCE_POLICY")
    return plan, request, worker, wrapper, packet


def validate_old_failure(original, g, loaded, records, worker, ledger):
    folder = ledger / "batch-02"
    expected_intent = {"schema": "pocket4-permission-capture-intent-v1", "plan_sha256": original.PLAN_SHA, "batch": 2,
        "request": loaded[2]["row"]["request"], "process_request": loaded[2]["row"]["process_request"],
        "idempotency_key": loaded[2]["row"]["idempotency_key"], "automatic_retry": False}
    need(g.parse(g.read(folder / "intent.json", 65536)) == expected_intent and
         g.read(folder / "intent.json", 65536) == read_record(records, LEDGER / "batch-02/intent.json"), "ORIGINAL_FAILED_INTENT_UNCHANGED")
    submitted_raw = g.read(folder / "submitted-job.json", 65536)
    need(submitted_raw == read_record(records, LEDGER / "batch-02/submitted-job.json") and
         g.parse(submitted_raw) == {"job_id": OLD_JOB, "idempotency_key": loaded[2]["row"]["idempotency_key"],
              "request_sha256": loaded[2]["row"]["request"]["sha256"],
              "process_request_sha256": loaded[2]["row"]["process_request"]["sha256"], "plan_sha256": original.PLAN_SHA},
         "ORIGINAL_FAILED_SUBMISSION_BINDING_UNCHANGED")
    names = {"artifact": "artifact.original.json", "terminal": "terminal.original.json", "outer": "stdout.original.jsonl",
             "gate_stop": "gate-status.stdout.original.json"}
    failure = {}
    for key, name in names.items():
        raw = g.read(folder / name, 524288)
        need(raw == read_record(records, LEDGER / "batch-02" / name), "ORIGINAL_FAILED_PUBLIC_EVIDENCE_CHANGED")
        failure[key] = raw
    need(worker.verify_original_failure(failure) == worker.ORIGINAL_FAILURE, "EXACT_FAILED_PREFIX_AND_OWNED_RETIREMENT_REQUIRED")
    return worker.ORIGINAL_FAILURE


def validate_corrective_outcome(original, g, loaded, records, plan, request, wrapper, packet):
    actual = CORRECTION / "actual"
    launch = g.parse(read_record(records, actual / "start.original.txt"))
    job = launch["job"]
    need(job["id"] == CORRECTION_JOB and job["idempotency_key"] == packet["idempotency_key"] and
         job["host"] == packet["host"] and job["executable"] == packet["executable"] and job["args"] == packet["args"] and
         job["cwd"] == packet["cwd"] and job["launch_state"] == "launched" and job["launch_error"] is None and
         launch["launch"]["ok"] is True, "ACTUAL_UNIQUE_CORRECTIVE_JOB_BINDING")
    raw = read_record(records, actual / "stdout.original.jsonl")
    terminal_raw = read_record(records, actual / "terminal.original.json")
    result, artifact, outer = original.owned_gate(g, raw, g.parse(terminal_raw), CORRECTION_JOB, wrapper,
        plan["stage_files"], plan["source_root"], "pocket4-microg-permission-correction-source-stage-result-v1")
    need(artifact == read_record(records, actual / "artifact.original.json") and
         outer["child_result"]["worker_stdout_original"].encode() == read_record(records, actual / "worker.stdout.original.json"),
         "ACTUAL_ENVELOPE_AND_ARTIFACT_MUST_MATCH_ORIGINAL_RAW")
    reports = corrective_service_gate(result, request, loaded[2]["row"]["Android_commands"],
                                     loaded[2]["row"]["target_identities"], loaded[2]["expected_guard"])
    need(result["original_failure"] == plan["original_failure"] and result["capture_policy"] == plan["capture_policy"] and
         [r["capture_limits"] for r in result["android_commands"]] == plan["capture_policy"]["stream_limits"] and
         result["original_failed_capture_reclassified"] is False and result["original_b02_ledger_advanced"] is False and
         result["corrective_b02_capture_complete"] is True, "INDEPENDENT_CORRECTION_NOT_OLD_FAILURE_SUCCESS")
    completed = {"batch": 2, "job_id": CORRECTION_JOB, "target_packages": request["target_packages"],
        "artifact_bytes": len(artifact), "artifact_sha256": sha(artifact), "outer_stdout_sha256": sha(raw), "terminal_sha256": sha(terminal_raw),
        "evidence_kind": "INDEPENDENT_CORRECTION_OF_ORIGINAL_FAILED_BATCH", "original_failed_job": OLD_JOB,
        "original_failed_capture_reclassified": False, "whole_47_current_identity_checked": True, "service_reports": reports,
        "observation_FDs_closed": result["observation_FDs_final"]["closed"], "lease_FDs_closed": result["lease_FDs_final"]["closed"],
        "original_owned_child_pidfd_retirement_verified": True,
        "interpretation_status": "RAW_CAPTURE_ONLY_NOT_INTERPRETED", "role_status": "UNKNOWN_NOT_QUERIED", "production_ready": False}
    return completed, result, artifact, outer


def load_linkage(ledger=LEDGER):
    source = (ORIGINAL / "permission_capture_gate.py").read_bytes()
    need(len(source) == 27120 and sha(source) == ORIGINAL_GATE_SHA, "ORIGINAL_PERMISSION_GATE_SOURCE_CHANGED")
    original = module(source, ORIGINAL / "permission_capture_gate.py", "frozen_original_permission_gate")
    g, original_plan, loaded = original.load_closure()
    closure, records = validate_input_closure(original, g)
    plan, request, worker, wrapper, packet = validate_correction_source(original, g, loaded, records)
    first = original.load_record(g, loaded[1], ledger / "batch-01")
    need(first is not None and first[0]["job_id"] == "1a1b2b86eb1-fc05-7f76" and
         first[2] == read_record(records, LEDGER / "batch-01/artifact.original.json"), "ACTUAL_ORIGINAL_FIRST_BATCH_REQUIRED")
    old_failure = validate_old_failure(original, g, loaded, records, worker, ledger)
    old_state = original.inspect(g, original_plan, loaded, ledger)
    need(old_state["state"] == "STOP_FAILED_OR_UNVERIFIED_BATCH" and old_state["batch"] == 2 and
         old_state["completed"] == [first[0]] and old_state["original_failure_must_remain"] is True,
         "ORIGINAL_SERIAL_GATE_STILL_STOPPED_AT_FAILED_B02")
    correction = validate_corrective_outcome(original, g, loaded, records, plan, request, wrapper, packet)
    linkage = {"schema": "pocket4-explicit-microg-correction-linkage-v1", "original_capture_plan_sha256": original.PLAN_SHA,
        "original_gate_sha256": ORIGINAL_GATE_SHA, "input_closure_sha256": INPUT_SHA,
        "original_failed_job": OLD_JOB, "original_failed_artifact_sha256": old_failure["artifact"]["sha256"],
        "original_failed_terminal_sha256": old_failure["terminal"]["sha256"], "original_gate_STOP_sha256": old_failure["gate_stop"]["sha256"],
        "corrective_job": CORRECTION_JOB, "corrective_artifact_sha256": correction[0]["artifact_sha256"],
        "corrective_outer_stdout_sha256": correction[0]["outer_stdout_sha256"], "corrective_terminal_sha256": correction[0]["terminal_sha256"],
        "original_failed_capture_reclassified": False, "original_b01_b02_modified": False,
        "original_scope_and_b03_b13_requests_unchanged": True, "all_runtime_and_owned_lifetime_checks_required": True,
        "raw_capture_is_semantic_grant_proof": False, "automatic_retry": False, "production_ready": False}
    return {"original": original, "g": g, "plan": original_plan, "loaded": loaded, "linkage": linkage,
            "completed": [first[0], correction[0]], "correction": correction, "ledger": ledger}


def inspect(context):
    original, g, loaded, ledger = (context[key] for key in ("original", "g", "loaded", "ledger"))
    need(ledger.is_dir() and not ledger.is_symlink(), "REGULAR_ORIGINAL_LEDGER_REQUIRED")
    existing = {p.name for p in ledger.iterdir()}
    need(existing <= {"batch-%02d" % n for n in range(1, 14)}, "UNEXPECTED_PERMISSION_LEDGER_ENTRY")
    completed = list(context["completed"])
    common = {"linkage": context["linkage"], "completed": completed,
              "original_ledger_gate_state": "STOP_FAILED_OR_UNVERIFIED_BATCH", "original_failed_batch": 2,
              "original_failure_must_remain": True, "automatic_retry": False, "raw_capture_is_semantic_grant_proof": False,
              "role_status": "UNKNOWN_NOT_QUERIED", "production_ready": False, "claims_created_by_status": 0}
    for number in range(3, 14):
        folder = ledger / ("batch-%02d" % number)
        if not folder.exists():
            need(not any((ledger / ("batch-%02d" % n)).exists() for n in range(number + 1, 14)), "OUT_OF_ORDER_PERMISSION_BATCH")
            return {**common, "state": READY, "next": loaded[number]["row"]}
        need(folder.is_dir() and not folder.is_symlink(), "REGULAR_BATCH_DIRECTORY_REQUIRED")
        try:
            need(g.parse(g.read(folder / "correction-link.json", 65536)) == context["linkage"], "THIS_NEW_BATCH_REQUIRES_EXACT_CORRECTION_LINK")
            observation = original.load_record(g, loaded[number], folder)
            if observation is None:
                return {**common, "state": "STOP_UNSETTLED_BATCH", "batch": number,
                        "idempotency_key": loaded[number]["row"]["idempotency_key"], "reconcile_original_submission_only": True}
            completed.append(observation[0])
        except (RuntimeError, KeyError, ValueError, TypeError, OSError) as error:
            return {**common, "state": "STOP_FAILED_OR_UNVERIFIED_BATCH", "batch": number,
                    "error": {"type": type(error).__name__, "reason": str(error)[:256]}}
    need(len(completed) == 13 and len({p for row in completed for p in row["target_packages"]}) == 45,
         "EXACT_ALL_45_BATCH_COVERAGE_REQUIRED")
    return {**common, "state": "ALL_45_RAW_CAPTURES_COMPLETE_WITH_EXPLICIT_MICROG_CORRECTION"}


def write_claim_file(g, folder, name, value):
    raw = g.canonical(value) + b"\n"
    fd = os.open(folder / name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        body = memoryview(raw)
        while body:
            count = os.write(fd, body)
            need(count > 0, "CLAIM_WRITE_PROGRESS")
            body = body[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    need(g.read(folder / name, 65536) == raw, "CLAIM_READBACK_CHANGED")


def claim(context):
    # Always recompute status from the verified actuals and the current ledger.
    # No caller-supplied READY result can authorize a claim.
    state = inspect(context)
    need(state["state"] == READY, "NO_CLAIM_AFTER_FAILED_UNKNOWN_OR_COMPLETE")
    original, g, ledger = (context[key] for key in ("original", "g", "ledger"))
    row = state["next"]
    need(type(row["batch"]) is int and 3 <= row["batch"] <= 13, "NEVER_CLAIM_OR_REPLACE_OLD_B01_B02")
    folder = ledger / ("batch-%02d" % row["batch"])
    os.mkdir(folder, 0o700)
    intent = {"schema": "pocket4-permission-capture-intent-v1", "plan_sha256": original.PLAN_SHA, "batch": row["batch"],
              "request": row["request"], "process_request": row["process_request"], "idempotency_key": row["idempotency_key"], "automatic_retry": False}
    write_claim_file(g, folder, "intent.json", intent)
    write_claim_file(g, folder, "correction-link.json", context["linkage"])
    for directory in (folder, ledger, ledger.parent):
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return {"state": "CLAIMED_WITH_VERIFIED_MICROG_CORRECTION_NOT_SUBMITTED", "batch": row["batch"], "folder": str(folder),
            "intent": intent, "correction_linkage": context["linkage"],
            "process_request_file": str(ORIGINAL / row["process_request"]["file"]), "processes_submitted": 0,
            "automatic_retry": False, "old_b01_b02_modified": False, "next_claim_requires_original_job_settlement": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("status", "claim-next"))
    args = parser.parse_args()
    context = load_linkage()
    result = claim(context) if args.action == "claim-next" else inspect(context)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False))
    return 1 if result["state"].startswith("STOP_") else 0


if __name__ == "__main__":
    raise SystemExit(main())
