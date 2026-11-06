#!/usr/bin/env python3
"""Local exact-source adapter for one microG capture correction; never submits."""
import sys
sys.dont_write_bytecode = True
import ast
import difflib
import hashlib
import json
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
CAPTURE = PROJECT / "successor_audit_requests/effective_permissions_45_capture_r1"
OLD = CAPTURE / "batch-02"
FAILED = PROJECT / "successor_audit_requests/actual/permissions-fixed45-r1/batch-02"
OLD_STAGE = "/home/alex/work/pocket4-launcher-permissions-source-20261106-r1-b02"
OLD_OUTPUT = "/home/alex/work/pocket4-launcher-permissions-observation-20261106-r1-b02"
STAGE = "/home/alex/work/pocket4-microg-permission-correction-source-20261106-r1"
OUTPUT = "/home/alex/work/pocket4-microg-permission-correction-observation-20261106-r1"
KEY = "sidecar-evidence-20261106-microg-b02-permission-correction-r1"
PLAN_SHA = "802c9616b99c0c753c7a31188ab7b594e5baba39d6940d963c2c1b9bd2cdb749"
FAILED_JOB = "1a1b2be17ec-fc05-7f8b"


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def write(name, raw):
    raw = raw.encode() if isinstance(raw, str) else raw
    path = HERE / name
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists():
        need(path.is_file() and not path.is_symlink() and path.read_bytes() == raw, "EXISTING_CANDIDATE_BYTES_DIFFER")
    else:
        with path.open("xb") as stream:
            stream.write(raw)
    need(path.read_bytes() == raw, "SOURCE_READBACK_REQUIRED")
    return {"file": name, "bytes": len(raw), "sha256": sha(raw)}


def remote_pin(name, raw):
    raw = raw.encode() if isinstance(raw, str) else raw
    return {"path": STAGE + "/" + name, "bytes": len(raw), "sha256": sha(raw)}


def assignment(source, name, value):
    nodes = [n for n in ast.parse(source).body if isinstance(n, ast.Assign) and
             any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]
    need(len(nodes) == 1, "ONE_EXACT_ASSIGNMENT")
    return replace(source, ast.get_source_segment(source, nodes[0]), name + " = " + repr(value))


def replace(source, old, new):
    need(source.count(old) == 1, "ONE_EXACT_REVIEWED_SOURCE_FRAGMENT")
    return source.replace(old, new, 1)


def definitions(source):
    return {n.name: ast.get_source_segment(source, n) for n in ast.parse(source).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}


def load(raw, path, name):
    module = types.ModuleType(name); module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def main():
    plan_raw = (CAPTURE / "CAPTURE_PLAN.json").read_bytes()
    need(len(plan_raw) == 47161 and sha(plan_raw) == PLAN_SHA, "ORIGINAL_CAPTURE_PLAN_CHANGED")
    plan = json.loads(plan_raw); row = plan["batches"][1]
    for field in ("stager", "process_request"):
        pin = row[field]
        raw = (CAPTURE / pin["file"]).read_bytes()
        need(len(raw) == pin["bytes"] and sha(raw) == pin["sha256"], "ORIGINAL_STAGER_OR_PACKET_CHANGED")
    sources = {}
    for pin in row["stage_files"]:
        raw = (OLD / pin["name"]).read_bytes()
        need(len(raw) == pin["bytes"] and sha(raw) == pin["sha256"], "ORIGINAL_BATCH02_SOURCE_CHANGED")
        sources[pin["name"]] = raw
    old_worker = sources["observe_current_services.py"].decode()
    old_wrapper = sources["owned_readonly_lifetime.py"].decode()
    transport = sources["readonly_services_transport.py"]
    appops_help = sources["inputs/cmd-appops-help.original.txt"]
    failure_raw = {"artifact": (FAILED / "artifact.original.json").read_bytes(),
                   "terminal": (FAILED / "terminal.original.json").read_bytes(),
                   "outer": (FAILED / "stdout.original.jsonl").read_bytes(),
                   "gate_stop": (FAILED / "gate-status.stdout.original.json").read_bytes()}
    need((len(failure_raw["artifact"]), sha(failure_raw["artifact"])) ==
         (27164, "f86711fe87e7c4976dd61cdd5c53bbfeb5f4692af773990d89db088781758cf3") and
         (len(failure_raw["outer"]), sha(failure_raw["outer"])) ==
         (18089, "ae37fe1743be6c1588d899e06e8b0ad42fa1fe625572826c9cb852ff554800f2"), "EXACT_ACTUAL_B02_FAILURE_REQUIRED")
    artifact = json.loads(failure_raw["artifact"]); terminal = json.loads(failure_raw["terminal"])
    need(terminal["job_id"] == FAILED_JOB and terminal["state"] == "failed" and terminal["exit_code"] == 1,
         "FAILED_ORIGINAL_TERMINAL_REQUIRED")
    names = {key: "inputs/original-b02-" + key.replace("_", "-") + ".json" for key in failure_raw}
    failure_inputs = {key: remote_pin(names[key], raw) for key, raw in failure_raw.items()}
    failure = {"job_id": FAILED_JOB, "state": "failed", "exit_code": 1,
        "original_capture_plan_sha256": PLAN_SHA, "original_request_sha256": row["request"]["sha256"],
        "original_worker_sha256": sha(sources["observe_current_services.py"]),
        "artifact": {"bytes": len(failure_raw["artifact"]), "sha256": sha(failure_raw["artifact"])},
        "outer_stdout": {"bytes": len(failure_raw["outer"]), "sha256": sha(failure_raw["outer"])},
        "terminal": {"bytes": len(failure_raw["terminal"]), "sha256": sha(failure_raw["terminal"])},
        "gate_stop": {"bytes": len(failure_raw["gate_stop"]), "sha256": sha(failure_raw["gate_stop"])},
        "inner_first_cause": "CHILD_OUTPUT_BOUND", "original_worker_error_label": "HOST_COMMAND_TIMEOUT",
        "command_returncode": -9, "capture_limit_bytes": 262144,
        "captured_stdout_prefix": artifact["android_commands"][1]["stdout"],
        "stdout_eof": False, "stderr_eof": False, "service_capture_complete": False,
        "AppOps_query_executed": False, "original_gate_state": "STOP_FAILED_OR_UNVERIFIED_BATCH",
        "original_failure_reclassified": False}
    commands = [("/system/bin/cmd", "package", "help"),
                ("/system/bin/cmd", "package", "dump-package", "com.google.android.gms"),
                ("/system/bin/cmd", "appops", "get", "--user", "0", "com.google.android.gms")]
    limits = [{"stdout": 262144, "stderr": 262144}, {"stdout": 2097152, "stderr": 262144}, {"stdout": 262144, "stderr": 262144}]
    policy = {"scope": "exact_microG_second_command_stdout_only", "commands": [list(c) for c in commands],
              "stream_limits": limits, "command_timeout_seconds": 30, "Android_timeout_seconds": 25,
              "total_worker_budget_seconds": 900, "other_package_limits_changed": False,
              "raw_output_private": True, "automatic_retry": False}
    worker = old_worker.replace(OLD_STAGE, STAGE).replace(OLD_OUTPUT, OUTPUT)
    worker = worker.replace("pocket4-fixed-launcher-permission-capture-request-v1", "pocket4-microg-permission-correction-request-v1")
    worker = worker.replace("pocket4-fixed-launcher-permission-raw-capture-v1", "pocket4-independent-microg-permission-correction-v1")
    worker = worker.replace("pocket4-fixed-launcher-permission-entry-rejection-v1", "pocket4-microg-permission-correction-entry-rejection-v1")
    marker = "\ndef need(value, code):"
    constants = "\nORIGINAL_FAILURE = " + repr(failure) + "\nFAILURE_INPUTS = " + repr(failure_inputs) + \
                "\nCORRECTION_COMMANDS = " + repr(tuple(commands)) + "\nCAPTURE_POLICY = " + repr(policy) + "\n"
    worker = replace(worker, marker, constants + marker)
    fragment = (HERE / "failure_and_limits.fragment.py").read_text()
    worker = replace(worker, "\ndef validate_request(request):", "\n" + fragment + "\ndef validate_request(request):")
    worker = replace(worker,
        '"target_packages", "target_user", "appops_help", "batch"}',
        '"target_packages", "target_user", "appops_help", "batch", "original_failure", "capture_policy"}')
    worker = replace(worker, 'request["appops_help"] == APP_OPS_HELP, "EXACT_SCOPE_AND_CLOSED_OPERATION_REQUEST")',
        'request["appops_help"] == APP_OPS_HELP and request["original_failure"] == ORIGINAL_FAILURE and\n'
        '         request["capture_policy"] == CAPTURE_POLICY, "EXACT_SCOPE_AND_CLOSED_OPERATION_REQUEST")')
    worker = replace(worker,
        "def held_bounded_child(argv, seconds, limit, pass_fds, host_env):",
        "def held_bounded_child(argv, seconds, limit, pass_fds, host_env, *, stdout_limit=None):")
    worker = replace(worker,
        '    need(0 < seconds <= 60 and 0 < limit <= 262144, "CHILD_BOUNDS_REQUIRED")\n    end = time.monotonic() + seconds',
        '    need(0 < seconds <= 60 and 0 < limit <= 262144, "CHILD_BOUNDS_REQUIRED")\n'
        '    need(stdout_limit is None or type(stdout_limit) is int and stdout_limit in (limit, 2097152), "CLOSED_STDOUT_LIMIT")\n'
        '    need(stdout_limit != 2097152 or limit == 262144 and tuple(argv[-4:]) == CORRECTION_COMMANDS[1],\n'
        '         "ONLY_EXACT_MICROG_DUMP_STDOUT_MAY_USE_TWO_MIB")\n'
        '    stream_limits = {"stdout": limit if stdout_limit is None else stdout_limit, "stderr": limit}\n'
        '    end = time.monotonic() + seconds')
    worker = replace(worker,
        '"returncode": None, "stdout_eof": False, "stderr_eof": False, "errors": [], "termination_attempted": False}',
        '"returncode": None, "stdout_eof": False, "stderr_eof": False, "errors": [], "termination_attempted": False,\n'
        '              "capture_limits": stream_limits}')
    worker = replace(worker, 'min(65536, limit + 1 - len(buffers[key.data]))', 'min(65536, stream_limits[key.data] + 1 - len(buffers[key.data]))')
    worker = replace(worker, 'need(len(buffers[key.data]) <= limit, "CHILD_OUTPUT_BOUND")',
                     'need(len(buffers[key.data]) <= stream_limits[key.data], "CHILD_OUTPUT_BOUND")')
    worker = replace(worker,
        '    need(os.getuid() == os.geteuid() == 0, "EXISTING_HOST_ROOT_AUTHORITY_REQUIRED")\n    guard =',
        '    need(os.getuid() == os.geteuid() == 0, "EXISTING_HOST_ROOT_AUTHORITY_REQUIRED")\n'
        '    verify_original_failure({key: read_root_pin(pin) for key, pin in FAILURE_INPUTS.items()})\n    guard =')
    worker = replace(worker, '"packages": PACKAGES, "app_scope_reference": APP_SCOPE,',
        '"packages": PACKAGES, "app_scope_reference": APP_SCOPE, "original_failure": ORIGINAL_FAILURE,\n'
        '              "capture_policy": CAPTURE_POLICY, "original_failed_capture_reclassified": False, "original_b02_ledger_advanced": False,')
    worker = replace(worker,
        '        index = len(result["android_commands"]) + 1\n        write("android-%02d.intent.json" % index,',
        '        index = len(result["android_commands"]) + 1\n        capture_limits = capture_limits_for(index, argv)\n'
        '        write("android-%02d.intent.json" % index,')
    worker = replace(worker,
        '"timeout_seconds": options["timeout"], "readonly": True, "automatic_retry": False})+b"\\n")',
        '"timeout_seconds": options["timeout"], "capture_limits": capture_limits, "readonly": True, "automatic_retry": False})+b"\\n")')
    worker = replace(worker,
        'raw, stderr, row = held_bounded_child(argv, options["timeout"], 262144, tuple(options["pass_fds"]), options["env"])',
        'raw, stderr, row = held_bounded_child(argv, options["timeout"], 262144, tuple(options["pass_fds"]), options["env"],\n'
        '                                              stdout_limit=capture_limits["stdout"])')
    worker = replace(worker,
        '        need(len(result["android_commands"]) == 1 + 2 * len(TARGET_PACKAGES) and',
        '        verify_original_failure({key: read_root_pin(pin) for key, pin in FAILURE_INPUTS.items()})\n'
        '        need([row["capture_limits"] for row in result["android_commands"]] == CAPTURE_POLICY["stream_limits"],\n'
        '             "ONLY_REVIEWED_THREE_STREAM_BUDGETS_USED")\n'
        '        need(len(result["android_commands"]) == 1 + 2 * len(TARGET_PACKAGES) and')
    worker = replace(worker,
        '    result["status"] = "FIXED_LAUNCHER_PERMISSION_SERVICE_RAW_CAPTURE_COMPLETE" if result["ok"] else "FIXED_LAUNCHER_PERMISSION_CAPTURE_INCOMPLETE_NO_RETRY"',
        '    result["corrective_b02_capture_complete"] = result["ok"]\n'
        '    result["status"] = "MICROG_PERMISSION_RAW_CAPTURE_CORRECTION_VERIFIED" if result["ok"] else "MICROG_PERMISSION_CORRECTION_INCOMPLETE_NO_RETRY"')
    worker = worker.replace('"""New explicit47-bound fixed Launcher-batch raw permission-service observation.',
                            '"""Independent microG-only correction after a precisely bounded incomplete dump.')
    compile(worker, "observe_current_services.py", "exec")
    worker_raw = worker.encode()
    request = json.loads(sources["request.review-only.json"])
    request.update(schema="pocket4-microg-permission-correction-request-v1", output_root=OUTPUT,
        worker=remote_pin("observe_current_services.py", worker_raw), transport=remote_pin("readonly_services_transport.py", transport),
        appops_help=remote_pin("inputs/cmd-appops-help.original.txt", appops_help), original_failure=failure, capture_policy=policy)
    request_raw = canonical(request)
    wrapper = old_wrapper
    config_node = next(n for n in ast.parse(wrapper).body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CONFIG" for t in n.targets))
    config = ast.literal_eval(config_node.value)
    config.update(stage_root=STAGE, worker=request["worker"], request=remote_pin("request.review-only.json", request_raw),
        prior_source={"bytes": len(sources["owned_readonly_lifetime.py"]), "sha256": sha(sources["owned_readonly_lifetime.py"]),
                      "preserved": True, "actual_prior_failed_job": FAILED_JOB, "scope_authority_not_inherited": True})
    wrapper = assignment(wrapper, "CONFIG", config)
    wrapper = wrapper.replace("pocket4-fixed-launcher-permission-raw-capture-v1", "pocket4-independent-microg-permission-correction-v1")
    wrapper = wrapper.replace("FIXED_LAUNCHER_PERMISSION_SERVICE_RAW_CAPTURE_COMPLETE", "MICROG_PERMISSION_RAW_CAPTURE_CORRECTION_VERIFIED")
    wrapper = replace(wrapper,
        '        actions = ("UI_actions", "App_launches", "installs", "permission_changes", "lifecycle_commands", "ADB_commands", "business_data_content_reads")',
        '        need(value.get("original_failure") == ' + repr(failure) + ' and\n'
        '             value.get("capture_policy") == ' + repr(policy) + ' and\n'
        '             value.get("original_failed_capture_reclassified") is False and value.get("original_b02_ledger_advanced") is False and\n'
        '             value.get("corrective_b02_capture_complete") is True and\n'
        '             [row.get("capture_limits") for row in value["android_commands"]] == ' + repr(limits) + ',\n'
        '             "EXACT_INDEPENDENT_MICROG_CORRECTION_REQUIRED")\n'
        '        for index, row in enumerate(value["android_commands"]):\n'
        '            need(tuple(row["argv"][-len(' + repr(commands) + '[index]):]) == tuple(' + repr(commands) + '[index]) and\n'
        '                 all(type(row[stream + "_bytes"]) is int and 0 <= row[stream + "_bytes"] <= row["capture_limits"][stream]\n'
        '                     for stream in ("stdout", "stderr")), "EXACT_MICROG_COMMAND_AND_STREAM_LIMITS")\n'
        '        actions = ("UI_actions", "App_launches", "installs", "permission_changes", "lifecycle_commands", "ADB_commands", "business_data_content_reads")')
    compile(wrapper, "owned_readonly_lifetime.py", "exec")
    files = [("owned_readonly_lifetime.py", wrapper.encode()), ("observe_current_services.py", worker_raw),
             ("readonly_services_transport.py", transport), ("request.review-only.json", request_raw),
             ("inputs/cmd-appops-help.original.txt", appops_help)] + [(names[k], v) for k, v in failure_raw.items()]
    stage_files = [{"name": name, "bytes": len(raw), "sha256": sha(raw)} for name, raw in files]
    for name, raw in files:
        write(name, raw)
    old_stager = (OLD / "stage_and_run_services.py").read_text()
    stager = assignment(assignment(old_stager, "ROOT", STAGE), "FILES", stage_files)
    stager = stager.replace("pocket4-fixed-launcher-permission-source-stage-v1", "pocket4-microg-permission-correction-source-stage-v1")
    stager = stager.replace("pocket4-fixed-launcher-permission-source-stage-result-v1", "pocket4-microg-permission-correction-source-stage-result-v1")
    stager = stager.replace("one fixed Launcher batch of permission metadata reads", "one independent microG permission capture correction")
    compile(stager, "stage_and_run_services.py", "exec")
    write("stage_and_run_services.py", stager)
    payload_raw = canonical({"schema": "pocket4-microg-permission-correction-source-stage-v1", "files":
                             [{"name": name, "text": raw.decode()} for name, raw in files]})
    need(len(payload_raw) <= 262144, "ORIGINAL_STAGER_INPUT_LIMIT_UNCHANGED")
    write("stage.stdin.original.json", payload_raw)
    packet = json.loads((OLD / "process-request.review-only.json").read_bytes())
    packet.update(args=["-n", "/usr/bin/python3", "-I", "-B", "-c", stager], stdin=payload_raw.decode(), idempotency_key=KEY)
    pp = write("process-request.review-only.json", canonical(packet))
    for name, before, after in (("collector-against-original-b02.diff", old_worker, worker),
         ("owned-wrapper-against-original-b02.diff", old_wrapper, wrapper), ("stager-against-original-b02.diff", old_stager, stager),
         ("request-against-original-b02.diff", json.dumps(json.loads(sources["request.review-only.json"]), sort_keys=True, indent=2)+"\n", json.dumps(request, sort_keys=True, indent=2)+"\n")):
        write(name, "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), fromfile="actual-failed-b02", tofile="independent-microg-correction-r1")))
    changed = {"held_bounded_child", "validate_request", "run", "main"}
    old_defs, new_defs = definitions(old_worker), definitions(worker)
    need(set(new_defs) - set(old_defs) == {"verify_original_failure", "capture_limits_for"} and
         all(new_defs[n] == v for n, v in old_defs.items() if n not in changed), "OTHER_WORKER_DEFINITIONS_MUST_STAY_EXACT")
    need(all(definitions(wrapper)[n] == v for n, v in definitions(old_wrapper).items() if n != "worker_gate"),
         "ORIGINAL_OWNED_LIFETIME_MUST_STAY_EXACT")
    need(transport == sources["readonly_services_transport.py"], "ORIGINAL_TRANSPORT_MUST_STAY_EXACT")
    candidate = {"schema": "pocket4-independent-microg-capture-correction-plan-v1", "source_only": True,
        "source_root": STAGE, "output_root": OUTPUT, "stage_files": stage_files, "process_request": pp,
        "worker": request["worker"], "wrapper": remote_pin("owned_readonly_lifetime.py", wrapper),
        "request": remote_pin("request.review-only.json", request_raw), "transport": request["transport"],
        "idempotency_key": KEY, "original_failure": failure, "capture_policy": policy,
        "actual_original_output_duration_ns": artifact["android_commands"][1]["finished_monotonic_ns"]-artifact["android_commands"][1]["started_monotonic_ns"],
        "original_error_label_not_rewritten": True, "original_output_prefix_not_complete_service_result": True,
        "original_scope_after_not_observed": "scope_guard_after" not in artifact,
        "old_ledger_unchanged": True, "continuation_requires_actual_new_full_joint_linkage": True,
        "unchanged_worker_definitions": sorted(set(old_defs) - changed),
        "unchanged_owned_wrapper_definitions": sorted(set(definitions(old_wrapper)) - {"worker_gate"}),
        "original_transport_full_bytes_unchanged": True,
        "remote_jobs": 0, "ledger_claims": 0, "permission_changes": 0, "production_ready": False}
    write("REPAIR_PLAN.json", canonical(candidate))
    print(json.dumps({"source_root": STAGE, "worker": candidate["worker"], "wrapper": candidate["wrapper"], "request": candidate["request"],
                      "packet": pp, "staged_bytes": len(payload_raw), "original_failure": failure, "remote_jobs": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
