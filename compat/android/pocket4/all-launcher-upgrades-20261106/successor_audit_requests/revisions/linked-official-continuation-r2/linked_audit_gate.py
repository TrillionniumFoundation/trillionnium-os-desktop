#!/usr/bin/env python3
"""Local continuation of the ORIGINAL audit ledger after one exact b05 repair.

This program never submits a process. Original b01-b04 use the original gate.
The failed b05 is checked as failed, together with the actual independent full
correction. Only the original eight remaining groups can then be claimed, once,
in the original ledger. Missing, failed or unknown later jobs stop progression.
"""
import sys
sys.dont_write_bytecode = True
import argparse
import ast
import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
GATE_FILE = "successor_audit_requests/revisions/gate-r2-terminal-protocol/audit_serial_gate.py"
GATE_SHA = "59568b064ea70628ae78a04755f3866d771a82b2907ded11122b2cdb1751c59d"
ORIGINAL_PLAN = "successor_audit_requests/final-upgrades-r1/REQUEST_MANIFEST.json"
ORIGINAL_PLAN_SHA = "d288affedc2eae8d28f2d7083df4c89d756e51ba8e5ebfb2264f9d3c6d783139"
LEDGER = "successor_audit_requests/actual/batches-final-r1"
REPAIR = "successor_audit_requests/revisions/b05-official-tool-repair-r1"
REPAIR_JOB = "1a1b289b789-fc05-7e7e"
FAILED_JOB = "1a1b16f06d5-fc05-78b1"
REPAIR_STDOUT_SHA = "75b1114536b0cc3079e13a4d1ca7463b37f756bb0d6b2b24e051b6395fd5722a"
REPAIR_WORKER_SHA = "b0c876c40165fc10c515fa0db8f8b7a916e969a92fba531375a7a226e97ad8d7"
REPAIR_TERMINAL_SHA = "c0d5d07a7be5d7ccbbbdc0451a4ac1a553bf690a1956b84ba7891aedc7f8652c"
FAILED_WORKER_SHA = "e8fb751780f88ba3d79cb51f5975f5426d1cd6df586563d035824b3b69789d10"
EMPTY_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
RESULT_TAIL = ("final_receipt", "owned_descriptors_final", "process_FDs_before", "process_FDs_after",
               "success_gate_requires_outer_final_stdout_and_authoritative_terminal")


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


def original_gate():
    path = PROJECT / GATE_FILE
    raw = path.read_bytes()
    need(len(raw) == 15151 and sha(raw) == GATE_SHA, "ORIGINAL_FROZEN_GATE_CHANGED")
    return module(raw, path, "pinned_original_audit_gate_r2")


def local_pin(g, row, root=PROJECT, limit=1048576):
    need(type(row) is dict and set(row) == {"file", "bytes", "sha256"} and
         type(row["file"]) is str and not row["file"].startswith("/") and
         all(part not in ("", ".", "..") for part in row["file"].split("/")), "CLOSED_LOCAL_EVIDENCE_PIN")
    raw = g.read(root / row["file"], limit)
    need(type(row["bytes"]) is int and len(raw) == row["bytes"] and sha(raw) == row["sha256"], "PINNED_LOCAL_EVIDENCE_CHANGED")
    return raw


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


def result_file_gate(g, result, root):
    body = dict(result)
    receipt = body["final_receipt"]
    for key in RESULT_TAIL:
        need(key in body, "ALL_STDOUT_ONLY_RESULT_TAIL_FIELDS_REQUIRED")
        body.pop(key)
    raw = g.canonical(body) + b"\n"
    need(receipt == {"path": root + "/result.json", "bytes": len(raw), "sha256": sha(raw)},
         "EXACT_DURABLE_RESULT_PUBLICATION_REQUIRED")
    return receipt


def owned_gate(g, raw, terminal, job, wrapper, files, root):
    terminal_gate(g, terminal, job, raw)
    lines = raw.splitlines()
    need(len(lines) == 2, "EXACT_STAGE_PLUS_OWNED_OUTER_PROTOCOL")
    stage, outer = (g.parse(line) for line in lines)
    need(stage.get("schema") == "pocket4-calendar-official-comparison-source-stage-result-v1" and
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


def apk_projection(apks):
    return sorted(({key: a[key] for key in ("path", "bytes", "sha256", "file")} for a in apks), key=lambda a: a["path"])


def layout_gate(g, result, apk_count, private=False):
    value = result["official_private_layout"]
    if private:
        need(set(value) == {"artifact", "encoding", "data", "observation_count", "all_observations_complete",
                           "owned_directory_descriptors", "full_original_observations_persisted_and_read_back"} and
             value["encoding"] == "zlib-base64" and value["all_observations_complete"] is True and
             value["full_original_observations_persisted_and_read_back"] is True, "FULL_LAYOUT_RECORD_PACKAGING_REQUIRED")
        pin = value["artifact"]
        envelope = {"encoding": value["encoding"], "data": value["data"], "artifact_bytes": pin["bytes"], "artifact_sha256": pin["sha256"]}
        full, raw = g.decode_artifact(g.canonical(envelope))
        need(pin["path"] == result["request"]["output_root"] + "/official-layout-observations.private.json" and
             g.canonical(full) + b"\n" == raw and value["observation_count"] == len(full["observations"]) and
             value["owned_directory_descriptors"] == full["owned_directory_descriptors"], "LOSSLESS_COMPLETE_LAYOUT_PUBLICATION_REQUIRED")
        value = full
    need(len(value["observations"]) == 2 + 6 * apk_count and
         value["owned_directory_descriptors"] == {"acquired": 11, "closed": 11, "errors": [], "evidence_store_descriptor_borrowed_not_closed_here": True} and
         value.get("existing_directories_only") is True and value.get("new_directories_created") == 0,
         "COMPLETE_BEFORE_AFTER_LAYOUT_COUNT_AND_FD_RETIREMENT")
    stages = ["fresh_readonly_rebind_before_APK_tools"]
    for pi, app in enumerate(result["apps"]):
        for ai, apk in enumerate(app["apks"]):
            for name in ("apksigner", "badging", "manifest"):
                stages += [f"before-p{pi:02d}-a{ai:02d}-{name}", f"after-p{pi:02d}-a{ai:02d}-{name}"]
    stages += ["after_all_APK_tools_and_file_checks"]
    need([r["stage"] for r in value["observations"]] == stages, "EXACT_PER_COMMAND_LAYOUT_OBSERVATION_ORDER")
    baseline = None
    for observation in value["observations"]:
        need(observation.get("complete") is True and observation.get("all_five_search_directories_and_thirty_candidates_proved") is True,
             "INCOMPLETE_OFFICIAL_LAYOUT_OBSERVATION")
        directories = observation["directories"]
        missing = [m for d in directories for m in d["missing_needed"]]
        need(len(directories) == 7 and len({d["path"] for d in directories}) == 7 and len(missing) == 30 and
             all(m["outcome"] == "ENOENT" for m in missing) and sum(bool(d["missing_needed"]) for d in directories) == 5,
             "FIVE_SEARCH_DIRECTORIES_THIRTY_TRUE_ENOENT_REQUIRED")
        need(all(d["stat"]["st_uid"] == 0 and d["stat"]["st_gid"] == 0 and d["stat"]["st_mode"] & 0o777 == 0o700 for d in directories),
             "PRIVATE_OFFICIAL_DIRECTORY_METADATA")
        if baseline is None:
            baseline = directories
        need(directories == baseline, "CONTROLLED_TOOL_TREE_CHANGED_WITHIN_AUDIT")


def complete_apk_gate(g, result, request, count, size, scope, source, private_layout=False):
    need(result.get("request") == request and result.get("packages") == request["packages"] and result.get("errors") == [] and
         result.get("effective_permission_grants") == "UNKNOWN_NOT_QUERIED" and result.get("resource_table_integrity_fully_proved") is False and
         result.get("all_45_Launcher_apps_reobserved") is False and result.get("legacy_badging_reexecuted") is False,
         "PRECISE_SCOPE_AND_INFERENCE_BOUNDARIES_REQUIRED")
    need(result["collector_source"] == {"path": request["output_root"] + "/collector-source.py", "bytes": source["bytes"], "sha256": source["sha256"]},
         "ACTUAL_REVIEWED_COLLECTOR_BYTES_REQUIRED")
    need(result.get("legacy_static_dependency_file_count") == 19 and result.get("official_static_dependency_file_count") == 7 and
         result["official_host_qualification"]["candidate"] == request["official_candidate_aapt2"] and
         result["official_host_qualification"]["job_id"] == "1a1b257ba27-fc05-7da0" and
         result["official_host_qualification"]["static_graph_is_actual_loader_mapping_proof"] is False,
         "ACTUAL_SAME_19_PLUS_7_TOOL_BINDINGS_REQUIRED")
    need([a["package"] for a in result["apps"]] == request["packages"] and
         sum(len(a["apks"]) for a in result["apps"]) == count and
         sum(a["bytes"] for app in result["apps"] for a in app["apks"]) == size,
         "EVERY_ORIGINAL_BASE_AND_SPLIT_REQUIRED")
    flat = []
    for pi, app in enumerate(result["apps"]):
        current = scope["apps"][app["package"]]
        need(app["uid"] == current["uid"] and app["PM_version_code"] == current["version_code"] and
             app["code_path"] == current["code_path"] and app["data_directories"] == current["data_directories"] and
             app["PM_certificate_sha256"] == current["package_manager_certificate_sha256"] and
             apk_projection(app["apks"]) == apk_projection(current["apks"]), "COMPLETE_ACTUAL_APK_UID_DATA_SCOPE_CHANGED")
        fields = ("complete_APK_set_observed", "one_base_manifest_observed", "all_APKs_signature_verified", "all_current_signers_equal_PM_records",
                  "all_manifests_match_PM_identity", "all_permission_names_decoded")
        need(all(app.get(k) is True for k in fields), "ACTUAL_APP_MANIFEST_OR_SIGNATURE_INCOMPLETE")
        for ai, apk in enumerate(app["apks"]):
            need(apk.get("parse_errors") == [] and apk.get("held_bytes_and_full_stat_and_path_unchanged") is True and
                 apk.get("manifest_matches_PM_package_and_version") is True and apk["signature"].get("verified") is True and
                 apk["signature"]["signer_certificate_sha256"] == sorted(current["package_manager_certificate_sha256"]) and
                 apk["signature"].get("current_signers_equal_PM_certificate_record") is True and
                 apk["declared_permissions"].get("all_names_decoded") is True, "INDIVIDUAL_APK_PROOF_INCOMPLETE")
            need([c["name"] for c in apk["commands"]] == ["apksigner", "badging", "manifest"], "THREE_FIXED_APK_COMMANDS_REQUIRED")
            for command in apk["commands"]:
                need(command.get("package") == app["package"] and command.get("apk_path") == apk["path"] and
                     type(command.get("returncode")) is int and command["returncode"] == 0 and
                     all(command.get(k) is True for k in ("spawned", "joined", "pipes_closed", "output_capture_complete")) and
                     all(command.get(k) is False for k in ("automatic_retry", "own_group_kill_requested", "timed_out")) and
                     not command.get("error") and not command.get("retirement_error"), "EVERY_COMMAND_NORMAL_COMPLETE_AND_JOINED")
                for stream in ("stdout", "stderr"):
                    receipt = command[stream]
                    need(set(receipt) == {"path", "bytes", "sha256"} and
                         receipt["path"] == request["output_root"] + f"/p{pi:02d}-a{ai:02d}-{command['name']}.{stream}" and
                         type(receipt["bytes"]) is int and 0 <= receipt["bytes"] <= 4194304 and
                         re.fullmatch("[0-9a-f]{64}", receipt["sha256"]), "EXACT_RAW_COMMAND_STREAM_RECEIPT_REQUIRED")
                if command["name"] == "badging":
                    need(command["stderr"]["bytes"] == 0 and command["stderr"]["sha256"] == EMPTY_SHA, "OFFICIAL_BADGING_STDERR_NOT_EMPTY")
                flat.append(command)
    need(flat == result["commands"] and len(flat) == 3 * count, "FULL_ORDERED_COMMAND_EVIDENCE_REQUIRED")
    layout_gate(g, result, count, private_layout)
    return result_file_gate(g, result, request["output_root"])


def old_claim(g, row, folder):
    intent = g.parse(g.read(folder / "intent.json", 65536))
    submitted = g.parse(g.read(folder / "submitted-job.json", 65536))
    need(intent.get("schema") == "pocket4-audit-coordinator-intent-v1" and intent.get("plan_sha256") == ORIGINAL_PLAN_SHA and
         intent.get("request") == row["request"] and intent.get("idempotency_key") == row["suggested_new_idempotency_key"] and
         set(submitted) == {"job_id", "idempotency_key", "request_sha256", "plan_sha256"} and
         submitted["idempotency_key"] == intent["idempotency_key"] and submitted["request_sha256"] == row["request"]["sha256"] and
         submitted["plan_sha256"] == ORIGINAL_PLAN_SHA, "ORIGINAL_LEDGER_CLAIM_CHANGED")
    return submitted


def check_preserved_history(g, plan, original, requests, scope):
    completed = []
    state_dir = PROJECT / LEDGER
    need(plan["original_state_dir"] == LEDGER and state_dir.is_dir() and not state_dir.is_symlink(), "ORIGINAL_LEDGER_ONLY_NO_FRESH_LEDGER")
    for row in original["batches"][:4]:
        folder = state_dir / ("batch-%02d" % row["batch"])
        submitted = old_claim(g, row, folder)
        completed.append(g.check_success(original, row, requests[row["batch"]], g.parse(g.read(folder / "terminal.original.json", 65536)),
                                        submitted, g.read(folder / "stdout.original.json", 1048576)))
    for row in plan["original_failed_evidence"]:
        local_pin(g, row)
    folder = state_dir / "batch-05"
    submitted = old_claim(g, original["batches"][4], folder)
    need(submitted["job_id"] == FAILED_JOB, "ONE_ORIGINAL_B05_FAILURE_JOB_REQUIRED")
    stdout = g.read(folder / "stdout.original.json", 1048576)
    terminal = g.parse(g.read(folder / "terminal.original.json", 65536))
    terminal_gate(g, terminal, FAILED_JOB, stdout, "failed", 1)
    failed, raw_failed = g.decode_artifact(stdout)
    need(sha(raw_failed) == FAILED_WORKER_SHA and g.read(folder / "artifact.original.json", 524288) == raw_failed and
         failed.get("status") == "APK_AUDIT_INCOMPLETE_REVIEW_RAW_EVIDENCE" and failed.get("all_commands_succeeded") is False and
         failed.get("all_manifests_and_signatures_verified") is False and failed.get("errors") == [] and
         failed.get("request") == requests[5] and failed.get("snapshot_consistent") is True and failed.get("action_lock_released") is True,
         "PRESERVED_ORIGINAL_FAILED_B05_REQUIRED")
    bad = [row for row in failed["commands"] if row.get("returncode") != 0]
    need(len(failed["commands"]) == 18 and len(bad) == 1 and bad[0].get("package") == "com.android.calendar" and
         bad[0].get("name") == "badging" and bad[0].get("returncode") == 1 and
         all(c.get("joined") is True and c.get("pipes_closed") is True and c.get("output_capture_complete") is True and
             c.get("timed_out") is False for c in failed["commands"]), "EXACT_SETTLED_OLD_TOOL_FAILURE_REQUIRED")
    old_gate = g.parse(g.read(folder / "gate-status.stdout.original.json", 65536))
    need(old_gate["state"] == "STOP_NO_RETRY" and old_gate["reason"] == "AUTHORITATIVE_SUCCESSFUL_DURABLE_TERMINAL_REQUIRED",
         "OLD_GATE_STOP_MUST_REMAIN_UNCHANGED")
    evidence = {r["file"]: local_pin(g, r) for r in plan["corrective_evidence"]}
    need(set(evidence) == {REPAIR + "/" + n for n in ("audit_original_b05.py", "owned_readonly_lifetime.py", "request.review-only.json",
         "process-request.review-only.json", "actual/start.original.txt", "actual/status-01.original.txt", "actual/stdout.original.jsonl", "actual/worker.stdout.original.json")},
         "COMPLETE_FIXED_CORRECTIVE_EVIDENCE_SET_REQUIRED")
    raw = evidence[REPAIR + "/actual/stdout.original.jsonl"]
    raw_terminal = evidence[REPAIR + "/actual/status-01.original.txt"]
    need(len(raw) == 36287 and sha(raw) == REPAIR_STDOUT_SHA and sha(raw_terminal) == REPAIR_TERMINAL_SHA,
         "ACTUAL_COMPLETE_B05_CORRECTIVE_JOB_ONLY")
    wrapper_raw = evidence[REPAIR + "/owned_readonly_lifetime.py"]
    need(len(wrapper_raw) == 17492 and sha(wrapper_raw) == "608f0babd455c535ec6c0876ebfcfbe3dbf229340c498197fc161a08cea30467",
         "ACTUAL_CORRECTIVE_OWNED_LIFETIME_SOURCE")
    wrapper = module(wrapper_raw, PROJECT / REPAIR / "owned_readonly_lifetime.py", "actual_b05_owned_source")
    worker_raw = evidence[REPAIR + "/audit_original_b05.py"]
    request_raw = evidence[REPAIR + "/request.review-only.json"]
    request = g.parse(request_raw)
    files = [{"name": name, "bytes": len(value), "sha256": sha(value)} for name, value in
             (("owned_readonly_lifetime.py", wrapper_raw), ("audit_original_b05.py", worker_raw), ("request.review-only.json", request_raw))]
    result, artifact, outer = owned_gate(g, raw, g.parse(raw_terminal), REPAIR_JOB, wrapper, files, wrapper.CONFIG["stage_root"])
    need(sha(artifact) == REPAIR_WORKER_SHA and artifact == evidence[REPAIR + "/actual/worker.stdout.original.json"] and
         result["request"] == request and request["guard"] == plan["guard"] and request["app_scope"] == plan["app_scope"] and
         result["repair_of"]["original_job_id"] == FAILED_JOB and result["repair_of"]["original_plan_sha256"] == ORIGINAL_PLAN_SHA and
         result["repair_of"]["original_request_sha256"] == original["batches"][4]["request"]["sha256"],
         "CORRECTION_MUST_BIND_THIS_EXACT_ORIGINAL_FAILURE")
    receipt = complete_apk_gate(g, result, request, 6, 341931165, scope, {"bytes": len(worker_raw), "sha256": sha(worker_raw)})
    need(receipt == plan["continuation_of"]["corrective_result"] and
         result["original_failure_reference"]["sha256"] == "55530bc50556775f1ca3870923b47f83340b2382c7636e163f0ecc74f2cfd2dd" and
         result["original_passed_control_reference"]["sha256"] == "4e1e6126869e1f2476574a5576cbec9d661a76350fae41ffe77ed792d2a94477",
         "ORIGINAL_FAILURE_CONTROL_AND_CORRECTIVE_PUBLICATION_LINEAGE_REQUIRED")
    for old, new in zip(failed["apps"], result["apps"]):
        need(all(old[k] == new[k] for k in ("package", "uid", "PM_version_code", "code_path", "PM_certificate_sha256", "data_directories")) and
             apk_projection(old["apks"]) == apk_projection(new["apks"]), "REPAIR_CANNOT_REPLACE_ANY_ORIGINAL_APK")
    return completed, {"batch": 5, "original_job_id": FAILED_JOB, "original_state": "FAILED_PRESERVED",
        "original_gate_state": "STOP_NO_RETRY_PRESERVED", "corrective_job_id": REPAIR_JOB,
        "corrective_state": "COMPLETE_INDEPENDENT_CORRECTION_VERIFIED", "corrective_artifact_sha256": sha(artifact),
        "corrective_final_receipt": receipt, "original_result_reclassified": False, "corrective_tool_commands": 18,
        "corrective_APKs": 6, "corrective_FDs_closed": result["owned_descriptors_final"]["closed"],
        "corrective_original_child_retirement_proved": True}


def load_plan(path, digest):
    g = original_gate()
    need(path.resolve() == HERE / "CONTINUATION_PLAN.json", "EXACT_REVIEWED_LINKED_PLAN_PATH_ONLY")
    raw = g.read(path, 262144)
    need(sha(raw) == digest, "FROZEN_CONTINUATION_PLAN_CHANGED")
    plan = g.parse(raw)
    need(plan.get("schema") == "pocket4-original-ledger-linked-b05-repair-continuation-v1" and
         plan.get("original_failed_b05_preserved") is True and plan.get("automatic_retry") is False and
         plan.get("pending_packages") == 31 and plan.get("pending_APK_count") == 65 and
         plan.get("preserved_original_batches") == [1, 2, 3, 4, 5], "ONE_EXPLICIT_ORIGINAL_LEDGER_CONTINUATION")
    need(plan["original_plan"] == {"file": ORIGINAL_PLAN, "bytes": 17548, "sha256": ORIGINAL_PLAN_SHA}, "ORIGINAL_PLAN_REFERENCE_CHANGED")
    original, old_requests = g.load_plan(PROJECT / ORIGINAL_PLAN, ORIGINAL_PLAN_SHA)
    scope_raw = g.read(PROJECT / plan["scope_local_file"], 131072)
    need(len(scope_raw) == plan["app_scope"]["bytes"] and sha(scope_raw) == plan["app_scope"]["sha256"] and
         plan["app_scope"]["sha256"] == "44f9ce783000a672c270e98afdaeb74bd79654508bfacae6793316ff4252e52f" and
         plan["guard"] == original["guard"] and plan["runtime_epoch_sha256"] == original["runtime_epoch_sha256"], "SAME_ACTUAL_SUCCESSOR_47_REFERENCE_REQUIRED")
    scope = g.parse(scope_raw)
    source = local_pin(g, plan["new_collector"], HERE, 131072)
    collector = module(source, HERE / plan["new_collector"]["file"], "reviewed_pending_collector_validation_only")
    need([r["batch"] for r in plan["batches"]] == list(range(6, 14)), "ORIGINAL_REMAINING_BATCH_ORDER_REQUIRED")
    requests, wrappers = {}, {}
    for row in plan["batches"]:
        n = row["batch"]
        previous = original["batches"][n - 1]
        need(all(row[k] == previous[k] for k in ("batch", "packages", "APK_count", "logical_APK_bytes")) and
             row["original_request_sha256"] == previous["request"]["sha256"] and
             row["collector"] == {"path": row["source_root"] + "/audit_remaining_batches.py", "bytes": len(source), "sha256": sha(source)},
             "ORIGINAL_PACKAGE_PARTITION_AND_COMPLETE_APK_STANDARD_REQUIRED")
        request_raw = g.read(HERE / row["local_request_file"], 65536)
        need(len(request_raw) == row["request"]["bytes"] and sha(request_raw) == row["request"]["sha256"], "EXACT_NEW_REQUEST_PIN")
        request = g.parse(request_raw)
        collector.validate_request(request)
        need(request["continuation_of"] == plan["continuation_of"] and request["original_batch"] == n and
             request["packages"] == row["packages"] and request["output_root"] == row["output_root"], "LINKED_REQUEST_SCOPE_MISMATCH")
        wrapper_raw = g.read(HERE / row["local_wrapper_file"], 65536)
        need(len(wrapper_raw) == row["wrapper"]["bytes"] and sha(wrapper_raw) == row["wrapper"]["sha256"], "EXACT_PENDING_OWNED_WRAPPER")
        wrapper = module(wrapper_raw, HERE / row["local_wrapper_file"], "pending_owned_wrapper_%02d" % n)
        need(wrapper.CONFIG["worker"] == row["collector"] and wrapper.CONFIG["request"] == row["request"] and
             wrapper.CONFIG["stage_root"] == row["source_root"], "EXACT_WRAPPER_SOURCE_AND_REQUEST_BINDING")
        packet = g.parse(local_pin(g, row["process_request"], HERE, 262144))
        stager = local_pin(g, row["stager"], HERE, 65536).decode()
        need(packet["host"] == "pocket4" and packet["cwd"] == "/home/alex/work" and packet["executable"] == "/usr/bin/sudo" and
             packet["args"] == ["-n", "/usr/bin/python3", "-I", "-B", "-c", stager] and
             packet["idempotency_key"] == row["suggested_new_idempotency_key"] == "sidecar-evidence-20261106-linked-official-audit-r2-b%02d" % n and
             {k: packet[k] for k in ("cpu_quota_percent", "memory_max_bytes", "nice", "timeout_seconds")} ==
             {"cpu_quota_percent": 100, "memory_max_bytes": 1073741824, "nice": 10, "timeout_seconds": 1100}, "ONE_EXACT_REVIEWED_BOUNDED_PROCESS_REQUEST")
        payload = g.parse(packet["stdin"])
        need(payload == {"schema": "pocket4-calendar-official-comparison-source-stage-v1", "files": [
            {"name": "owned_readonly_lifetime.py", "text": wrapper_raw.decode()},
            {"name": "audit_remaining_batches.py", "text": source.decode()},
            {"name": "request.review-only.json", "text": request_raw.decode()}]}, "EXACT_STAGED_SOURCE_AND_REQUEST_TEXT")
        requests[n], wrappers[n] = request, wrapper
    return g, plan, original, old_requests, scope, requests, wrappers


def inspect(g, plan, plan_sha, original, old_requests, scope, requests, wrappers):
    completed, correction = check_preserved_history(g, plan, original, old_requests, scope)
    state_dir = PROJECT / LEDGER
    existing = {p.name for p in state_dir.iterdir()}
    need(existing <= {"batch-%02d" % n for n in range(1, 14)}, "UNEXPECTED_ORIGINAL_LEDGER_ENTRY")
    for row in plan["batches"]:
        n = row["batch"]
        folder = state_dir / ("batch-%02d" % n)
        if not folder.exists():
            need(not any((state_dir / ("batch-%02d" % later)).exists() for later in range(n + 1, 14)), "OUT_OF_ORDER_ORIGINAL_LEDGER_NO_ADVANCE")
            return {"state": "NEXT_READY_AFTER_VERIFIED_ORIGINAL_B05_CORRECTION", "completed": completed,
                    "original_b05_and_independent_correction": correction, "next": row,
                    "original_ledger": LEDGER, "automatic_retry": False, "runtime_jobs_submitted": 0,
                    "production_ready": False, "effective_permission_grants": "UNKNOWN_NOT_QUERIED"}
        need(folder.is_dir() and not folder.is_symlink(), "ORIGINAL_LEDGER_BATCH_DIRECTORY_REQUIRED")
        intent = g.parse(g.read(folder / "intent.json", 65536))
        need(intent.get("schema") == "pocket4-original-ledger-linked-audit-intent-v1" and intent.get("batch") == n and
             intent.get("plan_sha256") == plan_sha and intent.get("original_plan_sha256") == ORIGINAL_PLAN_SHA and
             intent.get("corrective_job_id") == REPAIR_JOB and intent.get("request") == row["request"] and
             intent.get("process_request") == row["process_request"] and intent.get("idempotency_key") == row["suggested_new_idempotency_key"] and
             intent.get("automatic_retry") is False, "IMMUTABLE_LINKED_ORIGINAL_LEDGER_CLAIM_CHANGED")
        required = ("submitted-job.json", "terminal.original.json", "stdout.original.jsonl", "artifact.original.json")
        if not all((folder / name).is_file() for name in required):
            return {"state": "STOP_UNSETTLED_BATCH", "batch": n, "completed": completed,
                    "original_b05_and_independent_correction": correction, "idempotency_key": intent["idempotency_key"],
                    "automatic_retry": False, "runtime_jobs_submitted": 0,
                    "next_action": "Reconcile this one existing submission with unchanged key; no new key or later claim."}
        submitted = g.parse(g.read(folder / "submitted-job.json", 65536))
        need(set(submitted) == {"job_id", "idempotency_key", "request_sha256", "plan_sha256", "original_plan_sha256", "corrective_job_id"} and
             type(submitted["job_id"]) is str and submitted["job_id"] and submitted["idempotency_key"] == intent["idempotency_key"] and
             submitted["request_sha256"] == row["request"]["sha256"] and submitted["plan_sha256"] == plan_sha and
             submitted["original_plan_sha256"] == ORIGINAL_PLAN_SHA and submitted["corrective_job_id"] == REPAIR_JOB,
             "ACTUAL_LINKED_SUBMISSION_BINDING_REQUIRED")
        files = [{"name": "owned_readonly_lifetime.py", "bytes": row["wrapper"]["bytes"], "sha256": row["wrapper"]["sha256"]},
                 {"name": "audit_remaining_batches.py", "bytes": row["collector"]["bytes"], "sha256": row["collector"]["sha256"]},
                 {"name": "request.review-only.json", "bytes": row["request"]["bytes"], "sha256": row["request"]["sha256"]}]
        raw = g.read(folder / "stdout.original.jsonl", 1048576)
        value, artifact, outer = owned_gate(g, raw, g.parse(g.read(folder / "terminal.original.json", 65536)), submitted["job_id"],
                                          wrappers[n], files, row["source_root"])
        need(g.read(folder / "artifact.original.json", 524288) == artifact, "EXACT_DECODED_ORIGINAL_WORKER_ARTIFACT")
        receipt = complete_apk_gate(g, value, requests[n], row["APK_count"], row["logical_APK_bytes"], scope, row["collector"], True)
        completed.append({"batch": n, "job_id": submitted["job_id"], "artifact_bytes": len(artifact), "artifact_sha256": sha(artifact),
                          "final_receipt": receipt, "FDs_closed": value["owned_descriptors_final"]["closed"],
                          "all_tool_children_joined": True, "original_child_pidfd_retirement_proved": True,
                          "full_layout_observations_verified": 2 + 6 * row["APK_count"]})
    return {"state": "ALL_ORIGINAL_45_LAUNCHER_APK_COVERAGE_SETTLED_WITH_PRESERVED_B05_FAILURE", "completed": completed,
            "original_b05_and_independent_correction": correction, "packages": 45, "APK_count": 85,
            "automatic_retry": False, "production_ready": False, "effective_permission_grants": "UNKNOWN_NOT_QUERIED"}


def claim(g, plan_sha, decision):
    need(decision["state"] == "NEXT_READY_AFTER_VERIFIED_ORIGINAL_B05_CORRECTION", "ONLY_NEXT_UNCLAIMED_ORIGINAL_BATCH")
    row = decision["next"]
    state_dir = PROJECT / LEDGER
    folder = state_dir / ("batch-%02d" % row["batch"])
    folder.mkdir(mode=0o700)
    intent = {"schema": "pocket4-original-ledger-linked-audit-intent-v1", "batch": row["batch"],
              "plan_sha256": plan_sha, "original_plan_sha256": ORIGINAL_PLAN_SHA, "corrective_job_id": REPAIR_JOB,
              "request": row["request"], "process_request": row["process_request"], "idempotency_key": row["suggested_new_idempotency_key"],
              "created_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(), "automatic_retry": False}
    path = folder / "intent.json"
    with path.open("xb") as handle:
        handle.write(g.canonical(intent) + b"\n"); handle.flush(); os.fsync(handle.fileno())
    for directory in (folder, state_dir, state_dir.parent):
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    return {**decision, "state": "CLAIMED_ONE_LINKED_ORIGINAL_BATCH_FOR_COORDINATOR", "intent_path": str(path), "process_started_by_gate": False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("status", "claim-next"))
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--plan-sha256", required=True)
    args = parser.parse_args()
    try:
        g, plan, original, old_requests, scope, requests, wrappers = load_plan(args.plan, args.plan_sha256)
        decision = inspect(g, plan, args.plan_sha256, original, old_requests, scope, requests, wrappers)
        if args.operation == "claim-next":
            decision = claim(g, args.plan_sha256, decision)
        print(json.dumps(decision, sort_keys=True, ensure_ascii=True), flush=True)
        return 2 if decision["state"].startswith("STOP_") else 0
    except BaseException as error:
        print(json.dumps({"state": "STOP_NO_RETRY", "reason": str(error)[:300], "type": type(error).__name__,
                          "runtime_jobs_submitted": 0, "automatic_retry": False}, sort_keys=True), flush=True)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
