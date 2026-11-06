#!/usr/bin/env python3
"""Local evidence linkage only. No claim, submission, device command or ledger write.

The original b05 and b13 remain failed. This independently links their complete
corrective observations to the original thirteen groups and the actual resolver.
It does not turn APK evidence into permission, resource or business readiness.
"""
import sys
sys.dont_write_bytecode = True
import hashlib
import json
import os
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
OLD = PROJECT / "successor_audit_requests/revisions/linked-official-continuation-r2"
REPAIR = PROJECT / "successor_audit_requests/revisions/b13-fixture-version-repair-r1"
LEDGER = PROJECT / "successor_audit_requests/actual/batches-final-r1"
OLD_GATE_SHA = "0befe9f69aa46608a6cec8505c1fed41cd8fca1f9045693c43a83dbb4fa00d8e"
OLD_PLAN_SHA = "e26ff7e5c1739d2e30eab340df9072ab34a433362b9e8c869b905e25c1af18b3"
REPAIR_REVIEW_SHA = "468baa34967ba488ececfeab394baae753d5e2266d019536413202708cb3fb72"
REPAIR_PLAN_SHA = "8a9fbdd675072fd0f5a95aba99d5e8b86bc0c4a1ebea185ade486885be47de6a"
REPAIR_JOB = "1a1b2ba9875-fc05-7f80"
FAILED_JOB = "1a1b2ab7980-fc05-7f3a"
NEW_STDOUT = (29446, "b49af29667adb5774191a6e800cbdb52909a53c492a3719adedfe2ec527e953d")
NEW_ARTIFACT = (79075, "abe92b4b425e3c5dfccb67b90bd742070ebd91a0e43d294b889695b87352aa20")
NEW_TERMINAL = (733, "ff9912fb05f6a08e4794137b11cfb5d62dd649f8db77d23709a62a796a2cf7a1")
RESOLVER_FILE = PROJECT / "successor_audit_requests/current_services_r4/actual/worker.stdout.original.json"
RESOLVER_PIN = (79176, "185c6b0900aab78228e44788ea28b10d71c39cfeee8846fcb8c99c13a9f123fc")
EMPTY_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
INPUT_CLOSURE_SHA = "6f6a3c8c17aca62f83839f941048eb6723c5bc05a23b9db47ea8c0f2ba469822"


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def load_module(raw, path, name):
    value = types.ModuleType(name)
    value.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), value.__dict__)
    return value


def read_pin(path, size, digest):
    need(path.is_file() and not path.is_symlink(), "REGULAR_LOCAL_EVIDENCE_REQUIRED")
    raw = path.read_bytes()
    need(len(raw) == size and sha(raw) == digest, "EXACT_LOCAL_EVIDENCE_PIN_REQUIRED")
    return raw


def input_closure():
    path = HERE / "INPUT_CLOSURE.json"
    raw = path.read_bytes()
    need(sha(raw) == INPUT_CLOSURE_SHA, "FROZEN_INPUT_CLOSURE_CHANGED")
    value = json.loads(raw)
    need(value.get("schema") == "pocket4-b13-linked-coverage-input-closure-v1" and
         value.get("local_only") is True and len(value["files"]) == value["file_count"], "EXACT_INPUT_CLOSURE_SCHEMA")
    seen = set()
    for row in value["files"]:
        need(set(row) == {"file", "bytes", "sha256"} and not row["file"].startswith("/") and
             all(p not in ("", ".", "..") for p in row["file"].split("/")) and row["file"] not in seen,
             "ONE_CLOSED_REPOSITORY_INPUT_PATH")
        seen.add(row["file"])
        read_pin(PROJECT / row["file"], row["bytes"], row["sha256"])
    return {"file": str(path.relative_to(PROJECT)), "bytes": len(raw), "sha256": sha(raw), "file_count": len(seen)}


def load_context():
    old_raw = read_pin(OLD / "linked_audit_gate.py", 34438, OLD_GATE_SHA)
    old = load_module(old_raw, OLD / "linked_audit_gate.py", "exact_original_linked_gate")
    g, plan, original, old_requests, scope, requests, wrappers = old.load_plan(OLD / "CONTINUATION_PLAN.json", OLD_PLAN_SHA)
    review_raw = read_pin(REPAIR / "SOURCE_REVIEW.json", 3872, REPAIR_REVIEW_SHA)
    review = g.parse(review_raw)
    need(review["file_count"] == len(review["files"]) == 18 and review["state"] == "SOURCE_FROZEN_NOT_EXECUTED",
         "PRESERVED_PRE_EXECUTION_REVIEW_NOT_RETROACTIVELY_REWRITTEN")
    for pin in review["files"]:
        old.local_pin(g, pin, REPAIR, 262144)
    repair_plan = g.parse(read_pin(REPAIR / "REPAIR_PLAN.json", 5717, REPAIR_PLAN_SHA))
    for pin in repair_plan["input_references"]:
        old.local_pin(g, pin, PROJECT, 524288)
    request_raw = old.local_pin(g, repair_plan["request_local"], REPAIR)
    request = g.parse(request_raw)
    worker_pin, wrapper_pin = repair_plan["collector"], repair_plan["wrapper"]
    collector = load_module(read_pin(REPAIR / "audit_fixture_version_repair.py", worker_pin["bytes"], worker_pin["sha256"]),
                            REPAIR / "audit_fixture_version_repair.py", "exact_fixture_parser_only")
    wrapper = load_module(read_pin(REPAIR / "owned_readonly_lifetime.py", wrapper_pin["bytes"], wrapper_pin["sha256"]),
                          REPAIR / "owned_readonly_lifetime.py", "exact_corrective_joint_gate_only")
    collector.validate_request(request)
    need(wrapper.CONFIG["worker"] == worker_pin and wrapper.CONFIG["request"] == repair_plan["request"] and
         wrapper.CONFIG["stage_root"] == repair_plan["source_root"] and
         request["packages"] == requests[13]["packages"] and request["guard"] == plan["guard"] and
         request["app_scope"] == plan["app_scope"] and request["original_b13_failure"] == repair_plan["original_b13_failure"],
         "FIXED_CORRECTIVE_SOURCE_REQUEST_AND_SAME_47_REFERENCE")
    packet = g.parse(old.local_pin(g, repair_plan["process_request"], REPAIR, 262144))
    stager = old.local_pin(g, repair_plan["stager"], REPAIR).decode()
    payload = g.parse(packet["stdin"])
    need(packet["host"] == "pocket4" and packet["cwd"] == "/home/alex/work" and packet["executable"] == "/usr/bin/sudo" and
         packet["args"] == ["-n", "/usr/bin/python3", "-I", "-B", "-c", stager] and
         packet["idempotency_key"] == "sidecar-evidence-20261106-b13-fixture-version-correction-r1" and
         payload["schema"] == "pocket4-b13-version-repair-source-stage-v1", "EXACT_CORRECTIVE_PROCESS_SOURCE_CLOSURE")
    need(len(payload["files"]) == 3, "EXACT_THREE_STAGED_FILES")
    for item, pin in zip(payload["files"], repair_plan["stage_files"]):
        raw = item["text"].encode()
        need(set(item) == {"name", "text"} and item["name"] == pin["name"] and
             raw == read_pin(REPAIR / pin["name"], pin["bytes"], pin["sha256"]), "EXACT_EMBEDDED_CORRECTIVE_SOURCE")
    start = g.parse(g.read(REPAIR / "actual/start.original.txt", 65536))
    job = start["job"]
    need(start.get("audit_recorded") is True and start.get("launch", {}).get("ok") is True and
         job.get("id") == REPAIR_JOB and job.get("launch_state") == "launched" and job.get("launch_error") is None and
         all(job.get(k) == packet[k] for k in ("host", "cwd", "executable", "args", "idempotency_key")) and
         job.get("env_keys") == [] and job.get("system_jobctl") is False, "ACTUAL_CORRECTIVE_SUBMISSION_BOUND_TO_FROZEN_PACKET")
    return {"old": old, "g": g, "plan": plan, "original": original, "old_requests": old_requests, "scope": scope,
            "requests": requests, "wrappers": wrappers, "repair_plan": repair_plan, "request": request,
            "collector": collector, "wrapper": wrapper}


def linked_claim(ctx, row):
    g, old = ctx["g"], ctx["old"]
    folder = LEDGER / ("batch-%02d" % row["batch"])
    need(folder.is_dir() and not folder.is_symlink(), "ORIGINAL_LEDGER_BATCH_DIRECTORY_REQUIRED")
    intent = g.parse(g.read(folder / "intent.json", 65536))
    submitted = g.parse(g.read(folder / "submitted-job.json", 65536))
    need(intent.get("schema") == "pocket4-original-ledger-linked-audit-intent-v1" and intent.get("batch") == row["batch"] and
         intent.get("plan_sha256") == OLD_PLAN_SHA and intent.get("original_plan_sha256") == old.ORIGINAL_PLAN_SHA and
         intent.get("corrective_job_id") == old.REPAIR_JOB and intent.get("request") == row["request"] and
         intent.get("process_request") == row["process_request"] and intent.get("idempotency_key") == row["suggested_new_idempotency_key"] and
         intent.get("automatic_retry") is False, "IMMUTABLE_LINKED_ORIGINAL_LEDGER_CLAIM_CHANGED")
    need(set(submitted) == {"job_id", "idempotency_key", "request_sha256", "plan_sha256", "original_plan_sha256", "corrective_job_id"} and
         type(submitted["job_id"]) is str and submitted["job_id"] and submitted["idempotency_key"] == intent["idempotency_key"] and
         submitted["request_sha256"] == row["request"]["sha256"] and submitted["plan_sha256"] == OLD_PLAN_SHA and
         submitted["original_plan_sha256"] == old.ORIGINAL_PLAN_SHA and submitted["corrective_job_id"] == old.REPAIR_JOB,
         "ACTUAL_LINKED_SUBMISSION_BINDING_REQUIRED")
    return folder, submitted


def stage_files(row):
    return [{"name": name, "bytes": row[field]["bytes"], "sha256": row[field]["sha256"]} for name, field in
            (("owned_readonly_lifetime.py", "wrapper"), ("audit_remaining_batches.py", "collector"), ("request.review-only.json", "request"))]


def original_first_twelve(ctx):
    old, g = ctx["old"], ctx["g"]
    completed, b05 = old.check_preserved_history(g, ctx["plan"], ctx["original"], ctx["old_requests"], ctx["scope"])
    need({p.name for p in LEDGER.iterdir()} == {"batch-%02d" % n for n in range(1, 14)}, "ORIGINAL_THIRTEEN_GROUP_LEDGER_REQUIRED")
    verified = {}
    for n in range(1, 5):
        raw = g.read(LEDGER / ("batch-%02d" % n) / "stdout.original.json", 1048576)
        value, artifact = g.decode_artifact(raw)
        need(g.read(LEDGER / ("batch-%02d" % n) / "artifact.original.json", 524288) == artifact, "EXACT_EARLY_ORIGINAL_ARTIFACT")
        verified[n] = (value, completed[n - 1]["job_id"], artifact)
    b05_value = g.parse(g.read(PROJECT / old.REPAIR / "actual/worker.stdout.original.json", 524288))
    verified[5] = (b05_value, old.REPAIR_JOB, g.read(PROJECT / old.REPAIR / "actual/worker.stdout.original.json", 524288))
    for row in ctx["plan"]["batches"]:
        n = row["batch"]
        if n == 13:
            break
        folder, submitted = linked_claim(ctx, row)
        raw = g.read(folder / "stdout.original.jsonl", 1048576)
        value, artifact, outer = old.owned_gate(g, raw, g.parse(g.read(folder / "terminal.original.json", 65536)),
            submitted["job_id"], ctx["wrappers"][n], stage_files(row), row["source_root"])
        need(artifact == g.read(folder / "artifact.original.json", 524288), "EXACT_DECODED_ORIGINAL_WORKER_ARTIFACT")
        receipt = old.complete_apk_gate(g, value, ctx["requests"][n], row["APK_count"], row["logical_APK_bytes"],
                                        ctx["scope"], row["collector"], True)
        completed.append({"batch": n, "job_id": submitted["job_id"], "artifact_bytes": len(artifact), "artifact_sha256": sha(artifact),
            "final_receipt": receipt, "FDs_closed": value["owned_descriptors_final"]["closed"], "all_tool_children_joined": True,
            "original_child_pidfd_retirement_proved": True, "full_layout_observations_verified": 2 + 6 * row["APK_count"]})
        verified[n] = (value, submitted["job_id"], artifact)
    need(set(verified) == set(range(1, 13)), "ALL_PRIOR_TWELVE_GROUPS_REQUIRED")
    return completed, b05, verified


def failed_original_b13(ctx):
    g, old = ctx["g"], ctx["old"]
    row = ctx["plan"]["batches"][-1]
    folder, submitted = linked_claim(ctx, row)
    need(submitted["job_id"] == FAILED_JOB, "EXACT_ORIGINAL_FAILED_B13_JOB")
    raw = g.read(folder / "stdout.original.jsonl", 1048576)
    terminal = g.parse(g.read(folder / "terminal.original.json", 65536))
    old.terminal_gate(g, terminal, FAILED_JOB, raw, "failed", 1)
    lines = raw.splitlines()
    need(len(lines) == 2, "COMPLETE_FAILED_STAGE_AND_OUTER_STREAM")
    stage, outer = [g.parse(line) for line in lines]
    need(stage.get("schema") == "pocket4-calendar-official-comparison-source-stage-result-v1" and
         stage.get("source_stage_ok") is True and stage.get("source_root") == row["source_root"] and
         stage.get("files") == stage_files(row) and stage.get("bootstrap_FDs_before") == stage.get("bootstrap_FDs_after") and
         stage.get("worker_about_to_exec_once") is True and stage.get("automatic_retry") is False and
         all(type(stage.get(k)) is int and stage[k] == 0 for k in
             ("stage_Main_reads", "stage_UI_actions", "stage_installs", "stage_namespace_entries")), "ORIGINAL_FAILED_STAGE_CLOSURE")
    need(outer.get("schema") == "pocket4-owned-readonly-observation-result-v1" and outer.get("kind") == "calendar" and
         outer.get("ok") is False and outer.get("status") == "READONLY_OBSERVATION_OR_LIFETIME_INCOMPLETE_NO_RETRY" and
         outer.get("errors") == [{"reason": "ORIGINAL_PIDFD_AND_CHILD_JOINT_GATE_FAILED", "type": "RuntimeError"}] and
         all(outer.get(k) is False for k in ("automatic_retry", "old_results_reclassified", "production_ready", "inner_result_alone_qualifies")) and
         all(type(outer.get(k)) is int and outer[k] == 0 for k in ("UI_actions", "installs", "permission_changes")),
         "ORIGINAL_FAILED_OUTER_MUST_REMAIN_FAILED")
    life, child = outer["child_lifecycle"], outer["child_result"]
    need(type(life.get("returncode")) is int and life["returncode"] == 1 and
         all(life.get(k) is True for k in ("pidfd_acquired", "pidfd_exit_observed", "pidfd_closed", "parent_descriptors_restored")) and
         life.get("owned_child_sigkill_count") == 0 and life.get("timeout") is False and life.get("errors") == [],
         "ORIGINAL_FAILED_CHILD_NORMAL_RETIREMENT_STILL_REQUIRED")
    need(child.get("schema") == "pocket4-owned-readonly-observation-child-v1" and child.get("kind") == "calendar" and
         child.get("ok") is False and child.get("errors") == [{"reason": "ORIGINAL_WORKER_DID_NOT_PASS", "type": "RuntimeError"}] and
         child.get("worker_invoked") is True and type(child.get("worker_returncode")) is int and child["worker_returncode"] == 1 and
         child.get("manual_library_FD_close") is False and child.get("unknown_FDs_closed") == 0 and
         child.get("result_requires_parent_pidfd_retirement") is True and child.get("production_ready") is False and
         "frozen_descriptors_after_worker" not in child and child["frozen_descriptors_before_worker"] == child["final_descriptors"],
         "PRESERVED_FAILED_CHILD_NOT_INVENTED_SUCCESS_CENSUS")
    initial, frozen, library = child["bootstrap_initial_descriptors"], child["frozen_descriptors_before_worker"], child["bootstrap_library_resource"]
    need(set(initial) == {"0", "1", "2"} and len(frozen) == 4 and all(frozen[k] == v for k, v in initial.items()) and
         library.get("manual_close_performed") is False and library.get("lifetime_owner_from_reviewed_primary_source") == "libffi_process_global" and
         frozen.get(str(library["descriptor"]["fd"])) == library["descriptor"], "ORIGINAL_FAILED_KNOWN_LIBRARY_LIFETIME")
    child_raw = g.canonical(child) + b"\n"
    need(outer["child_stdout"] == {"path": row["source_root"] + "/child.stdout.original.json", "bytes": len(child_raw), "sha256": sha(child_raw)} and
         outer["child_stderr"] == {"path": row["source_root"] + "/child.stderr.original", "bytes": 0, "sha256": EMPTY_SHA},
         "ORIGINAL_FAILED_CHILD_STREAMS_UNCHANGED")
    worker_raw = child["worker_stdout_original"].encode()
    need(len(worker_raw) == child["worker_stdout_bytes"] and sha(worker_raw) == child["worker_stdout_sha256"] and
         outer["worker_stdout"] == {"path": row["source_root"] + "/worker.stdout.original.jsonl", "bytes": len(worker_raw), "sha256": sha(worker_raw)},
         "ORIGINAL_FAILED_WORKER_STREAM_UNCHANGED")
    value, artifact = g.decode_artifact(worker_raw)
    failure = ctx["repair_plan"]["original_b13_failure"]
    need(artifact == g.read(folder / "artifact.original.json", 524288) and len(artifact) == failure["worker_artifact_bytes"] and
         sha(artifact) == failure["worker_artifact_sha256"] and value.get("request") == ctx["requests"][13] and
         value.get("schema") == "pocket4-linked-official-remaining-apk-audit-v1" and
         value.get("status") == "LINKED_ORIGINAL_BATCH_AUDIT_INCOMPLETE_NO_RETRY" and value.get("linked_batch_audit_complete") is False and
         value.get("all_manifests_and_signatures_verified") is False and value.get("errors") == [] and
         all(value.get(k) is True for k in ("all_commands_succeeded", "all_primary_commands_succeeded", "all_tool_children_joined",
                                           "snapshot_consistent", "action_lock_released")), "EXACT_ORIGINAL_MANIFEST_PARSE_FAILURE")
    errors = [(app["package"], error) for app in value["apps"] for apk in app["apks"] for error in apk["parse_errors"]]
    need(errors == [("local.pocket4.fixture", {"field": "manifest", "reason": "AAPT_PACKAGE_VERSION_REQUIRED", "type": "RuntimeError"})],
         "ONLY_OBSERVED_EMPTY_FIXTURE_VERSION_FAILURE")
    need(value["apps"][0]["base_manifest"] is None and value["apps"][0]["one_base_manifest_observed"] is False and
         value["apps"][0]["all_manifests_match_PM_identity"] is False, "FAILED_FIXTURE_MANIFEST_CANNOT_BE_BACKFILLED")
    need(value["guard_before"] == value["guard_after"] and
         value["guard_before"]["runtime_epoch_sha256"] == ctx["plan"]["runtime_epoch_sha256"] and
         ctx["wrappers"][13].retired(value["owned_descriptors_final"]) and
         value.get("process_FDs_before") == value.get("process_FDs_after") and
         all(type(value.get(k)) is int and value[k] == 0 for k in
             ("UI_actions", "App_launches", "permission_changes", "installs", "Android_namespace_commands", "ADB_commands", "business_data_content_reads")) and
         value.get("automatic_retry") is False and value.get("production_ready") is False,
         "ORIGINAL_FAILED_GUARD_RESOURCE_RETIREMENT_AND_ACTION_BOUNDARY")
    basic_apk_checks(ctx, value, allow_failed_fixture=True)
    old.layout_gate(g, value, 3, True)
    receipt = old.result_file_gate(g, value, row["output_root"])
    need(receipt == failure["failed_publication"], "ORIGINAL_FAILED_PUBLICATION_UNCHANGED")
    stop = g.parse(g.read(folder / "gate-status.stdout.original.json", 65536))
    need(stop == {"automatic_retry": False, "reason": "EXACT_DURABLE_TERMINAL_REQUIRED", "runtime_jobs_submitted": 0,
                  "state": "STOP_NO_RETRY", "type": "RuntimeError"}, "ORIGINAL_LINKED_GATE_STOP_UNCHANGED")
    return value, {"job_id": FAILED_JOB, "state": "failed", "exit_code": 1, "gate_state": "STOP_NO_RETRY",
        "artifact_bytes": len(artifact), "artifact_sha256": sha(artifact), "final_receipt": receipt,
        "original_child_normal_exit_and_pidfd_retirement": True, "original_result_reclassified": False}


def terminal_gate(g, terminal, job, raw_stdout, state="succeeded", code=0):
    need(terminal.get("job_id") == job and terminal.get("state") == state and
         type(terminal.get("exit_code")) is int and terminal["exit_code"] == code and
         all(terminal.get(k) is True for k in ("output_complete", "output_durable", "terminal_publication_confirmed")) and
         all(terminal.get(k) is False for k in ("timed_out", "automatic_retry", "cancelled")) and
         g.exact_stream_values(terminal.get("log_truncated"), False) and
         g.exact_stream_values(terminal.get("log_errors"), None), "EXACT_DURABLE_TERMINAL_REQUIRED")
    sizes = terminal.get("log_bytes", {})
    need(sizes.get("stdout") == {"seen": len(raw_stdout), "stored": len(raw_stdout)} and
         sizes.get("stderr") == {"seen": 0, "stored": 0}, "COMPLETE_ORIGINAL_STDOUT_AND_EMPTY_STDERR_REQUIRED")


# repair_owned_gate below is the frozen original owned_gate with only its new
# source-stage schema changed. No success, stream or lifetime condition changes.
def repair_owned_gate(g, raw, terminal, job, wrapper, files, root):
    terminal_gate(g, terminal, job, raw)
    lines = raw.splitlines()
    need(len(lines) == 2, "EXACT_STAGE_PLUS_OWNED_OUTER_PROTOCOL")
    stage, outer = (g.parse(line) for line in lines)
    need(stage.get("schema") == "pocket4-b13-version-repair-source-stage-result-v1" and
         stage.get("source_stage_ok") is True and stage.get("source_root") == root and stage.get("files") == files and
         type(stage.get("bootstrap_FDs_before")) is int and stage["bootstrap_FDs_before"] == stage.get("bootstrap_FDs_after") and
         stage.get("worker_about_to_exec_once") is True and stage.get("automatic_retry") is False and
         all(type(stage.get(k)) is int and stage[k] == 0 for k in
             ("stage_Main_reads", "stage_UI_actions", "stage_installs", "stage_namespace_entries")), "EXACT_SUCCESSFUL_SOURCE_STAGE_REQUIRED")
    need(outer.get("schema") == "pocket4-owned-readonly-observation-result-v1" and outer.get("ok") is True and
         outer.get("status") == "READONLY_OBSERVATION_AND_OWNED_LIFETIME_VERIFIED" and outer.get("kind") == "calendar" and
         outer.get("errors") == [] and outer.get("automatic_retry") is False and outer.get("old_results_reclassified") is False and
         outer.get("production_ready") is False and outer.get("inner_result_alone_qualifies") is False and
         outer.get("library_FD_retired_by_original_held_owned_child_exit") is True and
         all(type(outer.get(k)) is int and outer[k] == 0 for k in ("UI_actions", "installs", "permission_changes")),
         "FULL_OWNED_OUTER_SUCCESS_REQUIRED")
    child = outer["child_result"]
    need(wrapper.combined(outer["child_lifecycle"], child, b""), "HELD_ORIGINAL_CHILD_RETIREMENT_REQUIRED")
    need(outer["child_stderr"] == {"path": root + "/child.stderr.original", "bytes": 0, "sha256": EMPTY_SHA},
         "NO_OWNED_CHILD_STDERR")
    child_raw = g.canonical(child) + b"\n"
    need(outer["child_stdout"] == {"path": root + "/child.stdout.original.json", "bytes": len(child_raw), "sha256": sha(child_raw)},
         "ORIGINAL_CHILD_PUBLICATION_PIN_REQUIRED")
    need(child.get("worker_invoked") is True and child.get("worker_returncode") == 0 and
         child.get("manual_library_FD_close") is False and type(child.get("unknown_FDs_closed")) is int and
         child["unknown_FDs_closed"] == 0 and child.get("result_requires_parent_pidfd_retirement") is True and
         child.get("production_ready") is False and
         child.get("frozen_descriptors_before_worker") == child.get("frozen_descriptors_after_worker") == child.get("final_descriptors"),
         "FULL_DESCRIPTOR_IDENTITIES_AND_NO_MANUAL_CLOSE_REQUIRED")
    initial, frozen = child["bootstrap_initial_descriptors"], child["frozen_descriptors_before_worker"]
    library = child["bootstrap_library_resource"]
    need(set(initial) == {"0", "1", "2"} and len(frozen) == 4 and
         all(frozen[k] == v for k, v in initial.items()) and library.get("manual_close_performed") is False and
         library.get("lifetime_owner_from_reviewed_primary_source") == "libffi_process_global" and
         frozen.get(str(library["descriptor"]["fd"])) == library["descriptor"], "EXACT_PROVED_LIBRARY_LIFETIME_BINDING")
    worker_stdout = child["worker_stdout_original"].encode("utf-8")
    need(len(worker_stdout) == child["worker_stdout_bytes"] and sha(worker_stdout) == child["worker_stdout_sha256"] and
         outer["worker_stdout"] == {"path": root + "/worker.stdout.original.jsonl", "bytes": len(worker_stdout), "sha256": sha(worker_stdout)},
         "ORIGINAL_WORKER_STREAM_PIN_REQUIRED")
    result, artifact = g.decode_artifact(worker_stdout)
    wrapper.worker_gate(result, child["worker_returncode"])
    return result, artifact, outer


def basic_apk_checks(ctx, value, allow_failed_fixture=False):
    """Cross-check all observed byte/stat/UID/data/signature/command rows, including early groups."""
    old, scope = ctx["old"], ctx["scope"]
    flat = []
    for app in value["apps"]:
        current = scope["apps"][app["package"]]
        need(app["uid"] == current["uid"] and app["PM_version_code"] == current["version_code"] and
             app["code_path"] == current["code_path"] and app["data_directories"] == current["data_directories"] and
             app["PM_certificate_sha256"] == current["package_manager_certificate_sha256"] and
             old.apk_projection(app["apks"]) == old.apk_projection(current["apks"]), "EVERY_COVERED_APK_UID_DATA_MATCHES_CURRENT_REFERENCE")
        for apk in app["apks"]:
            is_failed_fixture = allow_failed_fixture and app["package"] == "local.pocket4.fixture"
            need(apk.get("held_bytes_and_full_stat_and_path_unchanged") is True and
                 apk["signature"].get("verified") is True and apk["signature"].get("cryptographic_verification_performed") is True and
                 apk["signature"].get("API_minimum_override_used") is False and apk["signature"].get("integrity_check_bypassed") is False and
                 apk["signature"].get("current_signers_equal_PM_certificate_record") is True and
                 apk["signature"]["signer_certificate_sha256"] == sorted(current["package_manager_certificate_sha256"]) and
                 apk["declared_permissions"].get("all_names_decoded") is True, "FULL_ORIGINAL_SIGNATURE_AND_HELD_APK_PROOF")
            if not is_failed_fixture:
                need(apk.get("parse_errors") == [] and apk.get("manifest_matches_PM_package_and_version") is True and
                     apk["manifest"]["package"] == app["package"] and apk["manifest"]["long_version_code"] == current["version_code"],
                     "EVERY_COVERED_MANIFEST_MUST_MATCH_PM")
            need([c["name"] for c in apk["commands"]] == ["apksigner", "badging", "manifest"], "THREE_COMMANDS_PER_APK")
            for command in apk["commands"]:
                need(command.get("package") == app["package"] and command.get("apk_path") == apk["path"] and
                     type(command.get("returncode")) is int and command["returncode"] == 0 and
                     all(command.get(k) is True for k in ("spawned", "joined", "pipes_closed", "output_capture_complete")) and
                     all(command.get(k) is False for k in ("automatic_retry", "own_group_kill_requested", "timed_out")) and
                     not command.get("error") and not command.get("retirement_error"), "NORMAL_JOINED_COMPLETE_TOOL_COMMAND_REQUIRED")
                flat.append(command)
    need(value["commands"] == flat, "COMPLETE_ORDERED_COMMAND_ARRAY_REQUIRED")


def correction_gate(ctx, raw, terminal, original_failure):
    old, g, plan = ctx["old"], ctx["g"], ctx["repair_plan"]
    value, artifact, outer = repair_owned_gate(g, raw, terminal, REPAIR_JOB, ctx["wrapper"], plan["stage_files"], plan["source_root"])
    need(value.get("original_b13_failure") == plan["original_b13_failure"] and
         value.get("original_b13_failed_publication_reference") == original_failure["final_receipt"] and
         value.get("continuation_of") == ctx["plan"]["continuation_of"] and
         value.get("corrective_publication_reference") == ctx["plan"]["continuation_of"]["corrective_result"] and
         value.get("original_failure_reference", {}).get("sha256") == "55530bc50556775f1ca3870923b47f83340b2382c7636e163f0ecc74f2cfd2dd" and
         value.get("original_passed_control_reference", {}).get("sha256") == "4e1e6126869e1f2476574a5576cbec9d661a76350fae41ffe77ed792d2a94477",
         "EXACT_OLD_B05_AND_B13_FAILURE_AND_CORRECTION_LINEAGE_REQUIRED")
    receipt = old.complete_apk_gate(g, value, ctx["request"], 3, 108766, ctx["scope"], plan["collector"], True)
    basic_apk_checks(ctx, value)
    raw_dir = PROJECT / "successor_audit_requests/diagnostics/b13-fixture-manifest-raw-readback-r1/actual"
    collector = ctx["collector"]
    badging = read_pin(raw_dir / "p00-a00-badging.stdout", collector.FIXTURE_BADGING_PIN["bytes"], collector.FIXTURE_BADGING_PIN["sha256"])
    xml = read_pin(raw_dir / "p00-a00-manifest.stdout", collector.FIXTURE_XML_PIN["bytes"], collector.FIXTURE_XML_PIN["sha256"])
    app, apk = value["apps"][0], value["apps"][0]["apks"][0]
    expected = ctx["scope"]["apps"]["local.pocket4.fixture"]
    parsed = collector.manifest_with_exact_fixture_default(badging, xml, app["package"], expected, expected["apks"][0], apk["signature"])
    need(apk["manifest"] == parsed == app["base_manifest"] and
         {k: apk["commands"][1]["stdout"][k] for k in ("bytes", "sha256")} == collector.FIXTURE_BADGING_PIN and
         {k: apk["commands"][2]["stdout"][k] for k in ("bytes", "sha256")} == collector.FIXTURE_XML_PIN,
         "FRESH_RAW_STREAM_PINS_AND_EXACT_FIXTURE_ABSENT_VERSION_PROOF_REQUIRED")
    return value, artifact, {"batch": 13, "original_failed_job": FAILED_JOB, "corrective_job_id": REPAIR_JOB,
        "state": "COMPLETE_INDEPENDENT_CORRECTION_VERIFIED", "artifact_bytes": len(artifact), "artifact_sha256": sha(artifact),
        "final_receipt": receipt, "corrective_APKs": 3, "corrective_tool_commands": 9,
        "full_layout_observations_verified": 20, "corrective_FDs_closed": value["owned_descriptors_final"]["closed"],
        "corrective_original_child_retirement_proved": True, "original_result_reclassified": False,
        "fixture_declared_version_code": None, "fixture_declared_version_name": None, "fixture_effective_PM_version_code": 0}


def linked_coverage(ctx):
    completed, b05, verified = original_first_twelve(ctx)
    failed_value, failure = failed_original_b13(ctx)
    raw = read_pin(REPAIR / "actual/stdout.original.jsonl", *NEW_STDOUT)
    terminal = ctx["g"].parse(read_pin(REPAIR / "actual/terminal.original.json", *NEW_TERMINAL))
    value, artifact, b13 = correction_gate(ctx, raw, terminal, failure)
    need(artifact == read_pin(REPAIR / "actual/artifact.original.json", *NEW_ARTIFACT), "ACTUAL_CORRECTIVE_ARTIFACT_REQUIRED")
    for before, after in zip(failed_value["apps"], value["apps"]):
        need(all(before[k] == after[k] for k in ("package", "uid", "PM_version_code", "code_path", "PM_certificate_sha256", "data_directories")) and
             ctx["old"].apk_projection(before["apks"]) == ctx["old"].apk_projection(after["apks"]), "NO_FAILED_APK_REPLACED_BY_CORRECTION")
    verified[13] = (value, REPAIR_JOB, artifact)
    resolver = ctx["g"].parse(read_pin(RESOLVER_FILE, *RESOLVER_PIN))
    need(resolver.get("ok") is True and resolver.get("status") == "CURRENT_PM_AND_MAIN_LAUNCHER_OBSERVED" and
         resolver.get("errors") == [] and resolver.get("enumeration_samples_equal") is True and
         resolver.get("current_scope_47_unchanged") is True and resolver["guard_before"]["runtime_epoch_sha256"] == ctx["plan"]["runtime_epoch_sha256"] and
         resolver["guard_after"] == resolver["guard_before"] and resolver["catalog_comparison"]["framework_only_components"] == [] and
         resolver["catalog_comparison"]["native_only_components"] == [], "ACTUAL_SAME_EPOCH_RESOLVER_REFERENCE_REQUIRED")
    components = resolver["MAIN_LAUNCHER_components"]
    original_packages = [package for row in ctx["original"]["batches"] for package in row["packages"]]
    need(len(components) == 45 and len({row["component"] for row in components}) == 45 and
         set(original_packages) == {row["package"] for row in components} and len(original_packages) == len(set(original_packages)) == 45,
         "ACTUAL_RESOLVER_AND_ORIGINAL_UNIQUE_45_PARTITION_REQUIRED")
    rows, apk_count, command_count = [], 0, 0
    for n in range(1, 14):
        result, job, raw_artifact = verified[n]
        basic_apk_checks(ctx, result)
        need(result["packages"] == ctx["original"]["batches"][n - 1]["packages"], "ONE_ORIGINAL_FIXED_GROUP_PER_SUCCESSFUL_OBSERVATION")
        for app in result["apps"]:
            manifest = app["base_manifest"]
            rows.append({"package": app["package"], "component": next(r["component"] for r in components if r["package"] == app["package"]),
                "original_batch": n, "qualification_job": job, "artifact_sha256": sha(raw_artifact), "uid": app["uid"],
                "PM_version_code": app["PM_version_code"], "declared_version_name": manifest["version_name"],
                "declared_version_code": manifest["version_code"], "min_sdk": manifest["min_sdk"], "target_sdk": manifest["target_sdk"],
                "APK_count": len(app["apks"]), "APK_sha256": [a["sha256"] for a in app["apks"]],
                "PM_certificate_sha256": app["PM_certificate_sha256"],
                "APK_bytes_manifest_declared_permissions_and_PM_signer_verified": True,
                "effective_grants_proved_by_this_APK_audit": False, "production_ready": False})
            apk_count += len(app["apks"])
        command_count += len(result["commands"])
    need([r["package"] for r in rows] == original_packages and len(rows) == 45 and apk_count == 85 and command_count == 255,
         "COMPLETE_45_PACKAGE_85_APK_255_COMMAND_COVERAGE_REQUIRED")
    return {"schema": "pocket4-independent-linked-launcher-APK-coverage-v1", "state": "ALL_45_LAUNCHER_APK_OBSERVATIONS_JOINTLY_LINKED",
        "ok": True, "runtime_epoch_sha256": ctx["plan"]["runtime_epoch_sha256"], "scope47_reference": ctx["plan"]["app_scope"],
        "observed_packages": 45, "observed_APKs": apk_count, "successful_tool_commands": command_count, "packages": rows,
        "original_ledger": str(LEDGER.relative_to(PROJECT)), "original_ledger_written": False, "original_ledger_final_gate_state": "STOP_NO_RETRY",
        "original_first_twelve_completion_evidence": completed, "original_b05_and_independent_correction": b05,
        "original_b13_failure_preserved": failure, "independent_b13_correction": b13,
        "resolver_reference": {"file": str(RESOLVER_FILE.relative_to(PROJECT)), "bytes": RESOLVER_PIN[0], "sha256": RESOLVER_PIN[1],
                               "job_id": "1a1b22e95d0-fc05-7cd4", "PM_user0_installed_non_APEX_APK_packages": 205},
        "full_47_scope_is_reference_not_claim_of_47_APK_audits": True, "helper_packages_not_in_Launcher_audit":
            sorted(set(ctx["scope"]["apps"]) - set(original_packages)),
        "resource_table_integrity_fully_proved": False, "effective_grants_proved_by_this_APK_audit": False,
        "business_QA_completed_by_this_audit": False, "production_ready": False, "cleanup_admitted": False,
        "local_validation_only": True, "runtime_jobs_submitted": 0, "ledger_claims": 0, "automatic_retry": False}


def main():
    before = len(os.listdir("/proc/self/fd"))
    try:
        closure = input_closure()
        value = linked_coverage(load_context())
        need(input_closure() == closure, "INPUT_FILES_CHANGED_DURING_LOCAL_VALIDATION")
        after = len(os.listdir("/proc/self/fd"))
        need(before == after, "LOCAL_VALIDATOR_DESCRIPTOR_LEAK")
        value.update(input_closure=closure, local_FDs_before=before, local_FDs_after=after)
        print(canonical(value).decode(), flush=True)
        return 0
    except BaseException as error:
        print(canonical({"schema": "pocket4-independent-linked-launcher-APK-coverage-v1", "ok": False,
            "state": "STOP_NO_LINKED_COVERAGE", "reason": str(error)[:512], "type": type(error).__name__,
            "original_ledger_written": False, "runtime_jobs_submitted": 0, "ledger_claims": 0,
            "automatic_retry": False, "production_ready": False}).decode(), flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
