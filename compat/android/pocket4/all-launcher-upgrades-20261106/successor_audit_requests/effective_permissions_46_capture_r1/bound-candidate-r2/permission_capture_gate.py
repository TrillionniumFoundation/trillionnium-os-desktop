#!/usr/bin/env python3
"""Local-only serial gate for the fixed 14 permission raw-capture jobs.

This separate observation ledger never changes the APK-audit ledger. No process
submission, Android command, permission mutation, or interpretation occurs here.
The actual successful Beike pilot proves the source/lifetime baseline only; it
does not count as a new result for any of these 46 service targets.
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
PLAN_SHA = 'ae7570780e890f0855b2dc98ff4b5b387e52048deef4dcb9f33e2983e1735e58'
PLAN_BYTES = 54870
PRIMITIVES_FILE = "successor_audit_requests/revisions/gate-r2-terminal-protocol/audit_serial_gate.py"
PRIMITIVES_SHA = "59568b064ea70628ae78a04755f3866d771a82b2907ded11122b2cdb1751c59d"
EMPTY_SHA = hashlib.sha256(b"").hexdigest()
LEDGER = PROJECT / "successor_audit_requests/actual/permissions-fixed46-r1"
STAGE_SCHEMA = "pocket4-fixed-launcher-permission-source-stage-result-v1"
JOB_ID = re.compile(r"[0-9a-f]+-[0-9a-f]+-[0-9a-f]+")


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


def primitives():
    path = PROJECT / PRIMITIVES_FILE
    raw = path.read_bytes()
    need(len(raw) == 15151 and sha(raw) == PRIMITIVES_SHA, "FROZEN_LOCAL_PARSER_PRIMITIVES_CHANGED")
    return module(raw, path, "original_local_json_and_zlib_primitives")


def local_pin(g, row, root=PROJECT, limit=1048576):
    need(type(row) is dict and set(row) == {"file", "bytes", "sha256"} and
         type(row["file"]) is str and not row["file"].startswith("/") and
         all(part not in ("", ".", "..") for part in row["file"].split("/")), "CLOSED_LOCAL_PIN_REQUIRED")
    raw = g.read(root / row["file"], limit)
    need(type(row["bytes"]) is int and len(raw) == row["bytes"] and sha(raw) == row["sha256"], "LOCAL_PIN_CHANGED")
    return raw


def remote_local_pin(g, pin, relative, root=HERE):
    return local_pin(g, {"file": relative, "bytes": pin["bytes"], "sha256": pin["sha256"]}, root)


def constants(raw):
    values = {}
    for node in ast.parse(raw).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            try:
                values[node.targets[0].id] = ast.literal_eval(node.value)
            except (ValueError, TypeError):
                pass
    return values


def definitions(raw):
    source = raw.decode("utf-8")
    return {node.name: ast.get_source_segment(source, node) for node in ast.parse(source).body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))}


def terminal_gate(g, terminal, job, raw):
    need(JOB_ID.fullmatch(job) is not None and terminal.get("job_id") == job and terminal.get("state") == "succeeded" and
         type(terminal.get("exit_code")) is int and terminal["exit_code"] == 0 and
         all(terminal.get(k) is True for k in ("output_complete", "output_durable", "terminal_publication_confirmed")) and
         all(terminal.get(k) is False for k in ("timed_out", "automatic_retry", "cancelled")) and
         g.exact_stream_values(terminal.get("log_truncated"), False) and
         g.exact_stream_values(terminal.get("log_errors"), None), "EXACT_SUCCESSFUL_DURABLE_TERMINAL_REQUIRED")
    sizes = terminal.get("log_bytes", {})
    need(sizes.get("stdout") == {"seen": len(raw), "stored": len(raw)} and
         sizes.get("stderr") == {"seen": 0, "stored": 0}, "COMPLETE_RAW_STDOUT_AND_EMPTY_STDERR_REQUIRED")


def owned_gate(g, raw, terminal, job, wrapper, files, root, stage_schema=STAGE_SCHEMA):
    terminal_gate(g, terminal, job, raw)
    lines = raw.splitlines()
    need(len(lines) == 2, "EXACT_STAGE_PLUS_OWNED_PROTOCOL_REQUIRED")
    stage, outer = (g.parse(line) for line in lines)
    need(stage.get("schema") == stage_schema and stage.get("source_stage_ok") is True and
         stage.get("source_root") == root and stage.get("files") == files and
         type(stage.get("bootstrap_FDs_before")) is int and stage["bootstrap_FDs_before"] == stage.get("bootstrap_FDs_after") and
         stage.get("worker_about_to_exec_once") is True and stage.get("automatic_retry") is False and
         all(type(stage.get(k)) is int and stage[k] == 0 for k in
             ("stage_Main_reads", "stage_UI_actions", "stage_installs", "stage_namespace_entries")), "EXACT_SUCCESSFUL_STAGE_REQUIRED")
    need(outer.get("schema") == "pocket4-owned-readonly-observation-result-v1" and outer.get("ok") is True and
         outer.get("status") == "READONLY_OBSERVATION_AND_OWNED_LIFETIME_VERIFIED" and outer.get("kind") == "services" and
         outer.get("errors") == [] and outer.get("automatic_retry") is False and outer.get("old_results_reclassified") is False and
         outer.get("production_ready") is False and outer.get("inner_result_alone_qualifies") is False and
         outer.get("library_FD_retired_by_original_held_owned_child_exit") is True and
         all(type(outer.get(k)) is int and outer[k] == 0 for k in ("UI_actions", "installs", "permission_changes")),
         "FULL_OWNED_OUTER_SUCCESS_REQUIRED")
    child = outer["child_result"]
    need(wrapper.combined(outer["child_lifecycle"], child, b""), "ORIGINAL_CHILD_PIDFD_RETIREMENT_REQUIRED")
    need(outer["child_stderr"] == {"path": root + "/child.stderr.original", "bytes": 0, "sha256": EMPTY_SHA}, "OWNED_CHILD_STDERR_NOT_EMPTY")
    child_raw = g.canonical(child) + b"\n"
    need(outer["child_stdout"] == {"path": root + "/child.stdout.original.json", "bytes": len(child_raw), "sha256": sha(child_raw)},
         "EXACT_ORIGINAL_CHILD_PUBLICATION_REQUIRED")
    need(child.get("worker_invoked") is True and type(child.get("worker_returncode")) is int and child["worker_returncode"] == 0 and
         child.get("manual_library_FD_close") is False and type(child.get("unknown_FDs_closed")) is int and child["unknown_FDs_closed"] == 0 and
         child.get("result_requires_parent_pidfd_retirement") is True and child.get("production_ready") is False and
         child.get("frozen_descriptors_before_worker") == child.get("frozen_descriptors_after_worker") == child.get("final_descriptors"),
         "FULL_DESCRIPTOR_IDENTITIES_AND_NO_MANUAL_CLOSE_REQUIRED")
    initial, frozen = child["bootstrap_initial_descriptors"], child["frozen_descriptors_before_worker"]
    library = child["bootstrap_library_resource"]
    need(set(initial) == {"0", "1", "2"} and len(frozen) == 4 and
         all(frozen[k] == v for k, v in initial.items()) and library.get("manual_close_performed") is False and
         library.get("lifetime_owner_from_reviewed_primary_source") == "libffi_process_global" and
         frozen.get(str(library["descriptor"]["fd"])) == library["descriptor"], "EXACT_PROVED_LIBRARY_LIFETIME_REQUIRED")
    worker_raw = child["worker_stdout_original"].encode("utf-8")
    need(len(worker_raw) == child["worker_stdout_bytes"] and sha(worker_raw) == child["worker_stdout_sha256"] and
         outer["worker_stdout"] == {"path": root + "/worker.stdout.original.jsonl", "bytes": len(worker_raw), "sha256": sha(worker_raw)},
         "ORIGINAL_WORKER_STREAM_PIN_REQUIRED")
    result, artifact = g.decode_artifact(worker_raw)
    wrapper.worker_gate(result, child["worker_returncode"])
    return result, artifact, outer


def clean_command(command):
    need(type(command.get("returncode")) is int and command["returncode"] == 0 and
         all(command.get(k) is True for k in ("complete", "joined", "stdout_eof", "stderr_eof")) and
         command.get("termination_attempted") is False and command.get("errors") == [] and
         type(command.get("host_pid")) is int and command["host_pid"] > 0, "EVERY_COMMAND_MUST_COMPLETE_NORMALLY")


def stream_pair(command, record, root, prefix, stdout_limit=262144):
    need(type(stdout_limit) is int and stdout_limit in (262144, 2097152), "CLOSED_STREAM_BUDGET_REQUIRED")
    need(record.get("stream_artifacts_complete") is True, "EVERY_RAW_STREAM_MUST_BE_PUBLISHED")
    for name in ("stdout", "stderr"):
        pin = record[name]
        need(set(pin) == {"path", "bytes", "sha256"} and pin["path"] == root + "/" + prefix + "." + name and
             type(pin["bytes"]) is int and 0 <= pin["bytes"] <= (stdout_limit if name == "stdout" else 262144) and
             re.fullmatch(r"[0-9a-f]{64}", pin["sha256"]) is not None and
             command.get(name + "_bytes") == pin["bytes"] and command.get(name + "_sha256") == pin["sha256"],
             "RAW_STREAM_PIN_MUST_MATCH_ACTUAL_COMMAND_CAPTURE")
        if pin["bytes"] == 0:
            need(pin["sha256"] == EMPTY_SHA, "EMPTY_STREAM_HASH_MISMATCH")


def service_gate(result, request, commands, identities, expected_guard, baseline=False):
    need(baseline is False, "HISTORICAL45_PILOT_IS_NOT_A_NEW46_RESULT")
    root = request["output_root"]
    request_raw = json.dumps(request, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii") + b"\n"
    need(result.get("request") == {"path": root + "/request.json", "bytes": len(request_raw), "sha256": sha(request_raw)} and
         result.get("packages") == request["packages"] and
         result.get("app_scope_reference") == request["app_scope"] and result.get("guard_before") == expected_guard and
         result.get("guard_after") == expected_guard, "ACTUAL_REQUEST_OR_RUNTIME_SCOPE_CHANGED")
    scope = result["scope_guard_before"]
    need(scope == result["scope_guard_after"] and scope.get("schema") == "pocket4-app-scope-guard-v1" and
         scope.get("app_scope_sha256") == request["app_scope"]["sha256"] and scope.get("packages") == request["packages"] and
         scope.get("runtime_epoch_sha256") == expected_guard["runtime_epoch_sha256"] and
         scope.get("current_apk_paths_and_file_identities_match") is True and scope.get("new_signature_verification_performed") is False and
         scope.get("UI_or_install_runtime_admitted") is False, "FULL_49_CURRENT_IDENTITY_GUARDS_REQUIRED")
    if not baseline:
        need(result.get("target_identities_from_pinned_scope") == identities and
             result.get("target_packages") == request["target_packages"] and result.get("batch") == request["batch"], "EXACT_FIXED_TARGET_IDENTITIES_REQUIRED")
        comparison = result.get("native_catalog_comparison", {})
        need(result.get("native_catalog_matches_actual46_component_reference") is True and comparison == {
            "actual_framework_resolver_reference_job": "1a1b307f521-fc05-807a", "expected_count": 46, "observed_count": 46,
            "added_components": [], "missing_components": [], "framework_resolver_requeried_by_this_worker": False}, "CURRENT_NATIVE_CATALOG_CHANGED")
    native_argv = ["/usr/bin/sudo", "-n", "-u", "#1000", "--", "/usr/bin/env", "XDG_RUNTIME_DIR=/run/user/1000",
                   "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus", "/usr/bin/droidloomctl", "--socket", "/run/droidloom/control.sock", "--json"]
    need(len(result["native_commands"]) == 3 and result["native_before"] == result["native_after"] and
         result["native_before"].get("ok") is True and result["native_before"].get("state") == "running", "SAME_NATIVE_CELL_REQUIRED")
    for index, (row, operation) in enumerate(zip(result["native_commands"], ("status", "applications", "status")), 1):
        command = row["command"]
        clean_command(command)
        need(row.get("caller_uid") == 1000 and row.get("operation") == operation and command.get("argv") == native_argv + [operation],
             "EXACT_NATIVE_READONLY_CALLER_AND_ARGV_REQUIRED")
        stream_pair(command, row, root, "native-%02d" % index)
    need(len(result["android_commands"]) == len(commands), "ALL_CLOSED_ANDROID_COMMANDS_REQUIRED")
    for index, (row, command) in enumerate(zip(result["android_commands"], commands), 1):
        clean_command(row)
        microg = request["batch"] == 2 and request["target_packages"] == ["com.google.android.gms"]
        limits = {"stdout": 2097152 if microg and index == 2 else 262144, "stderr": 262144}
        if microg:
            need(row.get("capture_limits") == limits, "EXACT_MICROG_STREAM_LIMIT_INTENT_REQUIRED")
        else:
            need("capture_limits" not in row, "DEFAULT_STREAM_BUDGET_MUST_NOT_GAIN_EXCEPTION")
        stream_pair(row, row, root, "android-%02d" % index, limits["stdout"])
        suffix = ["/system/xbin/su", "2000", "/system/bin/timeout", "-k", "2", "25"] + command
        need(row.get("argv", [])[-len(suffix):] == suffix, "EXACT_BOUND_READONLY_ANDROID_SUFFIX_REQUIRED")
    help_row = result["android_commands"][0]
    need(result["help_results"] == {"package": {"stdout": help_row["stdout"], "stderr": help_row["stderr"], "returncode": 0}},
         "REAL_PACKAGE_HELP_RECEIPT_REQUIRED")
    reports = []
    targets = [request["target_package"]] if baseline else request["target_packages"]
    for pi, package in enumerate(targets):
        for index, service in ((1 + 2 * pi, "package-dump-package"), (2 + 2 * pi, "appops-get-user0")):
            row = result["android_commands"][index]
            expected = {"service": service, "argv": commands[index], "stdout": row["stdout"], "stderr": row["stderr"],
                        "returncode": 0, "complete": True, "joined": True, "stream_artifacts_complete": True,
                        "interpretation_status": "RAW_CAPTURE_ONLY_NOT_INTERPRETED"}
            if not baseline:
                expected.update(target_package=package, target_user=0)
            reports.append(expected)
    need(result["service_reports"] == reports, "COMPLETE_ORDERED_TARGET_SERVICE_REPORTS_REQUIRED")
    need(result["owned_descriptors_final"] == result["observation_FDs_final"], "ALL_OBSERVATION_FDS_ACCOUNTED")
    return reports


def load_closure():
    g = primitives()
    raw = g.read(HERE / "CAPTURE_PLAN.json", 262144)
    need(len(raw) == PLAN_BYTES and sha(raw) == PLAN_SHA, "FROZEN_PERMISSION46_PLAN_CHANGED")
    plan = g.parse(raw)
    need(plan["schema"] == "pocket4-fixed46-permission-raw-capture-plan-v1" and len(plan["batches"]) == 14 and
         plan["identity_context_packages"] == 49 and plan["service_target_packages"] == 46 and
         plan["runtime_ledger_relative_path"] == str(LEDGER.relative_to(PROJECT)) and
         plan["total_Android_readonly_commands"] == 106 and plan["automatic_retry"] is False,
         "EXACT_NEW46_PERMISSION_TASK_PLAN_REQUIRED")
    old_raw = local_pin(g, plan["original_gate"])
    old = module(old_raw, PROJECT / plan["original_gate"]["file"], "preserved45_source_baseline_only")
    _, old_plan, old_loaded = old.load_closure()
    binding_raw = local_pin(g, plan["binding_validator"], HERE)
    bound = module(binding_raw, HERE / plan["binding_validator"]["file"], "exact_actual49_binding_validator").validate_binding()
    need(bound["summary"] == plan["actual49_binding"] and bound["summary"]["scope"] == plan["app_scope"] and
         bound["expected_guard"] == old_loaded[1]["expected_guard"] and plan["guard"] == old_plan["guard"],
         "REAL_INSTALL_AND_SCOPE_READBACK_OR_ORIGINAL_RUNTIME_BASELINE_CHANGED")
    scope, components = bound["scope"], bound["components"]
    original = g.parse(local_pin(g, plan["original_partition"]))
    groups = [row["packages"] for row in original["batches"]] + [["com.example.ndk_tests"]]
    targets = [package for group in groups for package in group]
    need(len(groups) == 14 and len(targets) == len(set(targets)) == 46 and
         targets == plan["target_packages"] and sorted(targets) == bound["launchers"] and
         len(scope["apps"]) == 49 and len(components) == 46 and
         plan["runtime_epoch_sha256"] == scope["runtime_epoch_sha256"],
         "ORIGINAL13_PLUS_NDK14_AND_ACTUAL46_MEMBERSHIP_REQUIRED")
    for pin in plan["preserved_old45_stop"]:
        local_pin(g, pin)
    templates = {key: local_pin(g, pin) for key, pin in plan["templates"].items()}
    old_owner = remote_local_pin(g, old_plan["batches"][0]["wrapper"],
                                 "successor_audit_requests/effective_permissions_45_capture_r1/" + old_plan["batches"][0]["wrapper_file"], PROJECT)
    baseline_defs = definitions(old_owner)
    loaded = {}
    for number, row in enumerate(plan["batches"], 1):
        group = groups[number - 1]
        need(type(row["batch"]) is int and row["batch"] == number and row["targets"] == group and
             row["original_partition_batch"] == (number if number <= 13 else None), "EXACT_PARTITION_MEMBERSHIP_REQUIRED")
        folder = "batch-%02d/" % number
        needed_commands = [["/system/bin/cmd", "package", "help"]]
        for package in group:
            needed_commands.extend((["/system/bin/cmd", "package", "dump-package", package],
                                    ["/system/bin/cmd", "appops", "get", "--user", "0", package]))
        stage_root = "/home/alex/work/pocket4-launcher46-permissions-source-20261107-r2-b%02d" % number
        output_root = "/home/alex/work/pocket4-launcher46-permissions-observation-20261107-r2-b%02d" % number
        need(row["Android_commands"] == needed_commands and row["native_operations"] == ["status", "applications", "status"] and
             row["source_root"] == stage_root and row["output_root"] == output_root and
             row["idempotency_key"] == "pocket4-fixed46-permissions-20261107-r2-b%02d" % number,
             "CLOSED_FIXED_QUERY_LIST_AND_UNIQUE_ROOTS_AND_KEY_REQUIRED")
        sources = [remote_local_pin(g, row[key], row[key + "_file"]) for key in ("worker", "transport", "wrapper")]
        request = g.parse(remote_local_pin(g, row["request"], row["request_file"]))
        wc, tc, oc = map(constants, sources)
        identities = [{key: scope["apps"][p][key] for key in ("package", "uid", "version_code")} for p in group]
        help_pin = {"path": stage_root + "/inputs/cmd-appops-help.original.txt", "bytes": 1309,
                    "sha256": "95e3137d6acd3d920eb74f5d726a59232e6db9cb4efe8a4fedd6139074cb56cc"}
        need(request == {"schema": "pocket4-fixed46-launcher-permission-capture-request-v1", "guard": plan["guard"],
            "app_scope": plan["app_scope"], "packages": sorted(scope["apps"]), "worker": row["worker"], "transport": row["transport"],
            "output_root": output_root, "target_packages": group, "target_user": 0, "batch": number, "appops_help": help_pin},
            "EXACT49_REQUEST_REQUIRED")
        need(row["target_identities"] == identities and wc["SOURCE_SEALED"] is True and wc["NEW_HELPER"] == bound["summary"]["new_helper"] and
             wc["TARGET_PACKAGES"] == group and wc["BATCH_NUMBER"] == number and wc["ACTUAL46_COMPONENTS"] == components and
             list(wc["LAUNCHERS"]) == bound["launchers"] and wc["PACKAGES"] == sorted(scope["apps"]) and
             wc["APP_SCOPE"] == plan["app_scope"] and wc["GUARD"] == plan["guard"] and
             wc["STAGE"] == stage_root and wc["OUTPUT"] == output_root and wc["TRANSPORT"] == row["transport"] and
             wc["APP_OPS_HELP"] == help_pin and [list(c) for c in tc["READ_ONLY_COMMANDS"]] == needed_commands and
             tc["EXPLICIT_SCOPE_SHA256"] == plan["app_scope"]["sha256"] and
             tc["FRAMEWORK_EPOCH_SHA256"] == bound["expected_guard"]["Main_epoch_sha256"] ==
                 constants(templates["transport"])["FRAMEWORK_EPOCH_SHA256"] and
             tc["HELD_HELPER_SHA256"] == wc["HELPER_SHA"] == constants(templates["transport"])["HELD_HELPER_SHA256"] and
             tc["ANDROID_APP_SHA256"] == constants(templates["transport"])["ANDROID_APP_SHA256"] and
             oc["CONFIG"]["worker"] == row["worker"] and oc["CONFIG"]["request"] == row["request"] and
             oc["CONFIG"]["kind"] == "services" and oc["CONFIG"]["stage_root"] == stage_root,
             "EXACT_SCOPE_TARGETS_TRANSPORT_AND_WRAPPER_REQUIRED")
        template = templates["worker_microg" if number == 2 else "worker_normal"]
        need(definitions(sources[0]) == definitions(template) and definitions(sources[1]) == definitions(templates["transport"]),
             "FROZEN_WORKER_OR_TRANSPORT_DEFINITION_CHANGED")
        owner_defs = definitions(sources[2])
        need(set(owner_defs) == set(baseline_defs) and all(owner_defs[name] == baseline_defs[name]
             for name in baseline_defs if name != "worker_gate") and
             owner_defs["worker_gate"] == definitions(local_pin(g, plan["owner_gate_fragment"], HERE))["worker_gate"],
             "ORIGINAL_OWNED_LIFETIME_OR_REVIEWED_NEW_GATE_CHANGED")
        policy = constants(templates["worker_microg"])["CAPTURE_POLICY"] if number == 2 else None
        expected_binding = {"guard": bound["expected_guard"], "app_scope": plan["app_scope"], "packages": sorted(scope["apps"]),
            "batch": number, "targets": group, "identities": identities, "command_count": len(needed_commands),
            "native_comparison": {"actual_framework_resolver_reference_job": "1a1b307f521-fc05-807a", "expected_count": 46,
                "observed_count": 46, "added_components": [], "missing_components": [], "framework_resolver_requeried_by_this_worker": False},
            "microg_capture_policy": policy}
        need(oc["CAPTURE_BINDING"] == expected_binding and row["microg_capture_policy"] == policy,
             "EXACT_OWNED_CAPTURE_BINDING_REQUIRED")
        stager_raw = local_pin(g, row["stager"], HERE)
        stage_constants = constants(stager_raw)
        need(stage_constants["ROOT"] == stage_root and stage_constants["FILES"] == row["stage_files"] and
             definitions(stager_raw) == definitions(templates["stager"]), "EXACT_ORIGINAL_SOURCE_STAGE_REQUIRED")
        payload_raw = g.read(HERE / folder / "stage.stdin.original.json", 262144)
        payload = g.parse(payload_raw)
        need(set(payload) == {"schema", "files"} and payload["schema"] == "pocket4-fixed-launcher-permission-source-stage-v1" and
             len(payload["files"]) == len(row["stage_files"]) == 5, "EXACT_STAGE_PAYLOAD_REQUIRED")
        for item, pin in zip(payload["files"], row["stage_files"]):
            body = item["text"].encode("utf-8")
            need(set(item) == {"name", "text"} and item["name"] == pin["name"] and len(body) == pin["bytes"] and sha(body) == pin["sha256"] and
                 g.read(HERE / folder / pin["name"], 262144) == body, "FULL_STAGE_TEXT_MUST_MATCH_REVIEWED_SOURCE")
        packet = g.parse(local_pin(g, row["process_request"], HERE))
        need(packet == {"host": "pocket4", "executable": "/usr/bin/sudo", "args": ["-n", "/usr/bin/python3", "-I", "-B", "-c", stager_raw.decode()],
            "cwd": "/", "stdin": payload_raw.decode(), "cpu_quota_percent": 100, "memory_max_bytes": 1073741824, "nice": 10,
            "timeout_seconds": 1100, "idempotency_key": row["idempotency_key"]}, "EXACT_SINGLE_EXISTING_HOST_PROCESS_REQUEST_REQUIRED")
        wrapper = module(sources[2], HERE / row["wrapper_file"], "batch46_%02d_local_gate" % number)
        loaded[number] = {"row": row, "request": request, "wrapper": wrapper, "expected_guard": bound["expected_guard"]}
    return g, plan, loaded


def load_record(g, item, folder):
    row = item["row"]
    intent = g.parse(g.read(folder / "intent.json", 65536))
    expected = {"schema": "pocket4-permission-capture-intent-v1", "plan_sha256": PLAN_SHA, "batch": row["batch"],
                "request": row["request"], "process_request": row["process_request"], "idempotency_key": row["idempotency_key"],
                "automatic_retry": False}
    need(intent == expected, "IMMUTABLE_SINGLE_BATCH_CLAIM_CHANGED")
    required = ("submitted-job.json", "terminal.original.json", "stdout.original.jsonl")
    if not all((folder / name).exists() for name in required):
        return None
    submitted = g.parse(g.read(folder / "submitted-job.json", 65536))
    need(set(submitted) == {"job_id", "idempotency_key", "request_sha256", "process_request_sha256", "plan_sha256"} and
         JOB_ID.fullmatch(submitted["job_id"]) is not None and submitted["idempotency_key"] == row["idempotency_key"] and
         submitted["request_sha256"] == row["request"]["sha256"] and submitted["process_request_sha256"] == row["process_request"]["sha256"] and
         submitted["plan_sha256"] == PLAN_SHA, "EXACT_ACTUAL_SUBMISSION_BINDING_REQUIRED")
    terminal_raw = g.read(folder / "terminal.original.json", 65536)
    raw = g.read(folder / "stdout.original.jsonl", 524288)
    result, artifact, outer = owned_gate(g, raw, g.parse(terminal_raw), submitted["job_id"], item["wrapper"], row["stage_files"], row["source_root"])
    reports = service_gate(result, item["request"], row["Android_commands"], row["target_identities"], item["expected_guard"])
    completed = {"batch": row["batch"], "job_id": submitted["job_id"], "target_packages": row["targets"],
        "artifact_bytes": len(artifact), "artifact_sha256": sha(artifact), "outer_stdout_sha256": sha(raw), "terminal_sha256": sha(terminal_raw),
        "whole_49_current_identity_checked": True, "service_reports": reports,
        "observation_FDs_closed": result["observation_FDs_final"]["closed"], "lease_FDs_closed": result["lease_FDs_final"]["closed"],
        "original_owned_child_pidfd_retirement_verified": True,
        "interpretation_status": "RAW_CAPTURE_ONLY_NOT_INTERPRETED", "role_status": "UNKNOWN_NOT_QUERIED", "production_ready": False}
    return completed, result, artifact, outer


def inspect(g, plan, loaded, ledger=LEDGER):
    if ledger.exists():
        need(ledger.is_dir() and not ledger.is_symlink(), "REGULAR_LOCAL_LEDGER_DIRECTORY_REQUIRED")
    existing = {path.name for path in ledger.iterdir()} if ledger.exists() else set()
    need(existing <= {"batch-%02d" % n for n in range(1, 15)}, "UNEXPECTED_PERMISSION_LEDGER_ENTRY")
    completed = []
    for number in range(1, 15):
        folder = ledger / ("batch-%02d" % number)
        if not folder.exists():
            need(not any((ledger / ("batch-%02d" % n)).exists() for n in range(number + 1, 15)), "OUT_OF_ORDER_PERMISSION_BATCH")
            return {"state": "NEXT_READY", "completed": completed, "next": loaded[number]["row"], "automatic_retry": False,
                    "raw_capture_is_semantic_grant_proof": False, "claims_created_by_status": 0}
        need(folder.is_dir() and not folder.is_symlink(), "REGULAR_BATCH_DIRECTORY_REQUIRED")
        try:
            observation = load_record(g, loaded[number], folder)
            if observation is None:
                return {"state": "STOP_UNSETTLED_BATCH", "batch": number, "completed": completed, "automatic_retry": False,
                        "idempotency_key": loaded[number]["row"]["idempotency_key"], "reconcile_original_submission_only": True}
            completed.append(observation[0])
        except (RuntimeError, KeyError, ValueError, TypeError, OSError) as error:
            return {"state": "STOP_FAILED_OR_UNVERIFIED_BATCH", "batch": number, "completed": completed, "automatic_retry": False,
                    "error": {"type": type(error).__name__, "reason": str(error)[:256]}, "original_failure_must_remain": True}
    return {"state": "ALL_46_RAW_CAPTURES_COMPLETE", "completed": completed, "automatic_retry": False,
            "raw_capture_is_semantic_grant_proof": False, "role_status": "UNKNOWN_NOT_QUERIED", "production_ready": False}


def claim(g, state, ledger=LEDGER):
    need(state["state"] == "NEXT_READY", "NO_CLAIM_AFTER_FAILED_UNKNOWN_OR_COMPLETE")
    row = state["next"]
    if not ledger.exists():
        os.mkdir(ledger, 0o700)
    need(ledger.is_dir() and not ledger.is_symlink(), "REGULAR_LOCAL_LEDGER_DIRECTORY_REQUIRED")
    folder = ledger / ("batch-%02d" % row["batch"])
    os.mkdir(folder, 0o700)
    intent = {"schema": "pocket4-permission-capture-intent-v1", "plan_sha256": PLAN_SHA, "batch": row["batch"],
              "request": row["request"], "process_request": row["process_request"], "idempotency_key": row["idempotency_key"], "automatic_retry": False}
    fd = os.open(folder / "intent.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        body = memoryview(g.canonical(intent) + b"\n")
        while body:
            count = os.write(fd, body); need(count > 0, "CLAIM_WRITE_PROGRESS"); body = body[count:]
        os.fsync(fd)
    finally:
        os.close(fd)
    for directory in (folder, ledger, ledger.parent):
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    need(g.parse(g.read(folder / "intent.json", 65536)) == intent, "CLAIM_READBACK_CHANGED")
    return {"state": "CLAIMED_NOT_SUBMITTED", "batch": row["batch"], "folder": str(folder), "intent": intent,
            "process_request_file": str(HERE / row["process_request"]["file"]), "processes_submitted": 0,
            "automatic_retry": False, "next_claim_requires_original_job_settlement": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("validate", "status", "claim-next"))
    args = parser.parse_args()
    g, plan, loaded = load_closure()
    if args.action == "validate":
        result = {"state": "SOURCE_CLOSURE_AND_ACTUAL49_INSTALL_READBACK_VERIFIED", "plan_sha256": PLAN_SHA,
                  "batches": 14, "target_packages": 46, "Android_commands": 106, "claims_created": 0, "processes_submitted": 0,
                  "new_target_observations": 0, "semantic_permissions_interpreted": 0, "production_ready": False}
    else:
        result = inspect(g, plan, loaded)
        if args.action == "claim-next":
            result = claim(g, result)
    print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False))
    return 0 if not result["state"].startswith("STOP_") else 1


if __name__ == "__main__":
    raise SystemExit(main())
