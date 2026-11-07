#!/usr/bin/env python3
"""Local deterministic assembly using the real installed-helper49 original inputs.

Creates reviewed source/process requests, never claims or submits any job.
Existing artifacts must match byte for byte; no frozen revision is overwritten.
"""
import sys
sys.dont_write_bytecode = True
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path
import types

HERE = Path(__file__).resolve().parent
PREP = HERE.parent
PROJECT = HERE.parents[2]
OLD = PROJECT / "successor_audit_requests/effective_permissions_45_capture_r1"


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")


def module(path):
    raw = path.read_bytes()
    value = types.ModuleType(path.stem)
    value.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), value.__dict__)
    return value


def definition(text, name):
    found = [node for node in ast.parse(text).body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name]
    need(len(found) == 1, "EXACT_DEFINITION:" + name)
    return ast.get_source_segment(text, found[0])


def once(text, before, after):
    need(text.count(before) == 1, "EXACT_SOURCE_FRAGMENT:" + before[:100])
    return text.replace(before, after, 1)


def assignment(text, name, value):
    found = [node for node in ast.parse(text).body if isinstance(node, ast.Assign) and
             any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    need(len(found) == 1, "EXACT_ASSIGNMENT:" + name)
    node = found[0]
    need(node.col_offset == 0, "TOP_LEVEL_CONSTANT_REQUIRED")
    lines = text.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [name + " = " + repr(value) + "\n"]
    return "".join(lines)


def literal(text, name):
    node = next(node for node in ast.parse(text).body if isinstance(node, ast.Assign) and
                any(isinstance(target, ast.Name) and target.id == name for target in node.targets))
    return ast.literal_eval(node.value)


def pin(path, root=PROJECT):
    raw = path.read_bytes()
    return {"file": str(path.relative_to(root)), "bytes": len(raw), "sha256": sha(raw)}


def write(name, raw):
    raw = raw.encode("utf-8") if isinstance(raw, str) else raw
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        need(path.is_file() and not path.is_symlink() and path.read_bytes() == raw, "EXISTING_CANDIDATE_DIFFERS:" + name)
    else:
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
        try:
            view = memoryview(raw)
            while view:
                count = os.write(fd, view)
                need(count > 0, "LOCAL_WRITE_PROGRESS")
                view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        need(path.read_bytes() == raw, "LOCAL_READBACK_CHANGED")
    return {"file": name, "bytes": len(raw), "sha256": sha(raw)}


def diff(name, before, after):
    return write(name, "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
        fromfile="preserved-original45/" + name, tofile="actual49-fixed46/" + name)))


def main():
    preparation_raw = (PREP / "PREPARATION_PINS.json").read_bytes()
    need((len(preparation_raw), sha(preparation_raw)) == (3779, "e8daa699db1a8b1b35588c8e12b550e236e99a4e8537c6538ade6df989516cd1"), "FROZEN_PREPARATION_MANIFEST_CHANGED")
    for row in json.loads(preparation_raw)["files"]:
        raw = (PREP / row["path"]).read_bytes()
        need((len(raw), sha(raw)) == (row["bytes"], row["sha256"]), "FROZEN_PREPARATION_FILE_CHANGED:" + row["path"])
    binder = module(HERE / "bind_actual_scope49.py")
    actual = binder.validate_binding()
    summary, scope = actual["summary"], actual["scope"]
    source = module(PREP / "prepare_unsealed.py")
    original = json.loads(source.source("original_partition"))
    groups = [row["packages"] for row in original["batches"]] + [["com.example.ndk_tests"]]
    need(len(groups) == 14 and sorted(p for group in groups for p in group) == actual["launchers"], "FIXED14_COMPLETE46_REQUIRED")
    normal = (PREP / "worker.normal.template.py").read_text()
    microg = (PREP / "worker.microg.template.py").read_text()
    transport_template = (PREP / "transport.template.py").read_text()
    old_owner = source.source("owner").decode()
    old_stage = (OLD / "batch-01/stage_and_run_services.py").read_text()
    need((len(old_stage.encode()), sha(old_stage.encode())) == (6916, "594d96ad1e1445104ca5ec67e82bdcbfcd57b20cb0ec3a64cba19604f5584e0a"), "ORIGINAL_STAGER_CHANGED")
    old_gate = (OLD / "permission_capture_gate.py").read_text()
    need((len(old_gate.encode()), sha(old_gate.encode())) == (27120, "dc4fffb3f11e8428db732b96cd1925f0bdce239cdce81ff64ab369dc14c751f4"), "ORIGINAL_GATE_CHANGED")
    help_raw = (OLD / "batch-01/inputs/cmd-appops-help.original.txt").read_bytes()
    need((len(help_raw), sha(help_raw)) == (1309, "95e3137d6acd3d920eb74f5d726a59232e6db9cb4efe8a4fedd6139074cb56cc"), "ACTUAL_APPOPS_HELP_CHANGED")
    gate_fragment = (HERE / "owned_worker_gate.py.inc").read_text().rstrip()
    need(definition(gate_fragment, "worker_gate") == gate_fragment, "EXACT_ONE_OWNED_GATE_DEFINITION")
    guard = json.loads(source.source("old_plan"))["guard"]
    packages = sorted(scope["apps"])
    rows, inheritance = [], []
    for number, targets in enumerate(groups, 1):
        name = "batch-%02d" % number
        stage_root = "/home/alex/work/pocket4-launcher46-permissions-source-20261107-r1-b%02d" % number
        output_root = "/home/alex/work/pocket4-launcher46-permissions-observation-20261107-r1-b%02d" % number
        key = "pocket4-fixed46-permissions-20261107-r1-b%02d" % number
        commands = source.command_list(targets)
        identities = [{k: scope["apps"][p][k] for k in ("package", "uid", "version_code")} for p in targets]
        transport = assignment(transport_template, "READ_ONLY_COMMANDS", tuple(tuple(c) for c in commands))
        tp = write(name + "/readonly_services_transport.py", transport)
        remote_transport = {"path": stage_root + "/readonly_services_transport.py", "bytes": tp["bytes"], "sha256": tp["sha256"]}
        help_pin = {"path": stage_root + "/inputs/cmd-appops-help.original.txt", "bytes": len(help_raw), "sha256": sha(help_raw)}
        write(name + "/inputs/cmd-appops-help.original.txt", help_raw)
        worker = microg if number == 2 else normal
        for k, v in (("GUARD", guard), ("STAGE", stage_root), ("OUTPUT", output_root), ("TRANSPORT", remote_transport), ("APP_OPS_HELP", help_pin),
                     ("APP_SCOPE", summary["scope"]), ("PACKAGES", packages), ("NEW_HELPER", summary["new_helper"]),
                     ("SOURCE_SEALED", True), ("TARGET_PACKAGES", targets), ("BATCH_NUMBER", number)):
            worker = assignment(worker, k, v)
        compile(worker, name + "/observe_current_services.py", "exec")
        wp = write(name + "/observe_current_services.py", worker)
        remote_worker = {"path": stage_root + "/observe_current_services.py", "bytes": wp["bytes"], "sha256": wp["sha256"]}
        request = {"schema": "pocket4-fixed46-launcher-permission-capture-request-v1", "guard": guard,
            "app_scope": summary["scope"], "packages": packages, "worker": remote_worker, "transport": remote_transport,
            "output_root": output_root, "target_packages": targets, "target_user": 0, "batch": number, "appops_help": help_pin}
        rp = write(name + "/request.review-only.json", canonical(request))
        remote_request = {"path": stage_root + "/request.review-only.json", "bytes": rp["bytes"], "sha256": rp["sha256"]}
        policy = literal(microg, "CAPTURE_POLICY") if number == 2 else None
        capture_binding = {"guard": actual["expected_guard"], "app_scope": summary["scope"], "packages": packages,
            "batch": number, "targets": targets, "identities": identities, "command_count": len(commands),
            "native_comparison": {"actual_framework_resolver_reference_job": "1a1b307f521-fc05-807a", "expected_count": 46,
                "observed_count": 46, "added_components": [], "missing_components": [], "framework_resolver_requeried_by_this_worker": False},
            "microg_capture_policy": policy}
        cfg = literal(old_owner, "CONFIG")
        cfg.update(stage_root=stage_root, worker=remote_worker, request=remote_request)
        owner = assignment(old_owner, "CONFIG", cfg)
        owner = once(owner, "SELF_PIN = None", "CAPTURE_BINDING = " + repr(capture_binding) + "\nSELF_PIN = None")
        owner = once(owner, definition(owner, "worker_gate"), gate_fragment)
        original_defs = [node.name for node in ast.parse(old_owner).body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name != "worker_gate"]
        need(all(definition(owner, n) == definition(old_owner, n) for n in original_defs), "OWNED_LIFETIME_CHANGED")
        compile(owner, name + "/owned_readonly_lifetime.py", "exec")
        op = write(name + "/owned_readonly_lifetime.py", owner)
        files = [{"name": filename, "bytes": item["bytes"], "sha256": item["sha256"]} for filename, item in
                 (("owned_readonly_lifetime.py", op), ("observe_current_services.py", wp), ("readonly_services_transport.py", tp),
                  ("request.review-only.json", rp), ("inputs/cmd-appops-help.original.txt", help_pin))]
        stage = assignment(assignment(old_stage, "ROOT", stage_root), "FILES", files)
        sp = write(name + "/stage_and_run_services.py", stage)
        payload = {"schema": "pocket4-fixed-launcher-permission-source-stage-v1", "files":
                   [{"name": item["name"], "text": (HERE / name / item["name"]).read_text()} for item in files]}
        stdin = canonical(payload)
        need(len(stdin) <= 262144, "ORIGINAL_STAGE_STDIN_BOUND")
        write(name + "/stage.stdin.original.json", stdin)
        packet = {"host": "pocket4", "executable": "/usr/bin/sudo", "args": ["-n", "/usr/bin/python3", "-I", "-B", "-c", stage],
            "cwd": "/", "stdin": stdin.decode(), "cpu_quota_percent": 100, "memory_max_bytes": 1073741824,
            "nice": 10, "timeout_seconds": 1100, "idempotency_key": key}
        pp = write(name + "/process-request.review-only.json", canonical(packet))
        rows.append({"batch": number, "original_partition_batch": number if number <= 13 else None, "targets": targets,
            "target_identities": identities, "Android_commands": commands, "native_operations": ["status", "applications", "status"],
            "worker": remote_worker, "worker_file": wp["file"], "transport": remote_transport, "transport_file": tp["file"],
            "wrapper": {"path": stage_root + "/owned_readonly_lifetime.py", "bytes": op["bytes"], "sha256": op["sha256"]},
            "wrapper_file": op["file"], "request": remote_request, "request_file": rp["file"], "stager": sp,
            "process_request": pp, "source_root": stage_root, "output_root": output_root, "idempotency_key": key,
            "stage_files": files, "microg_capture_policy": policy})
        if number in (1, 2, 14):
            diff(name + "/worker-against-unsealed-template.diff", microg if number == 2 else normal, worker)
            diff(name + "/owned-against-original-b01.diff", old_owner, owner)
            diff(name + "/stager-against-original-b01.diff", old_stage, stage)
        inheritance.append({"batch": number, "all_worker_definitions_equal_frozen_template": True,
            "all_transport_definitions_equal_frozen_template": True, "owned_definitions_unchanged": original_defs,
            "stager_definitions_unchanged": [node.name for node in ast.parse(stage).body if isinstance(node, ast.FunctionDef)],
            "changed_owned_definition": "worker_gate", "microg_budget_only": number == 2})
    plan = {"schema": "pocket4-fixed46-permission-raw-capture-plan-v1", "target_packages": [p for group in groups for p in group],
        "original_partition": source.pin(source.source("original_partition")) | {"file": source.PINS["original_partition"][0]},
        "original_gate": pin(OLD / "permission_capture_gate.py"), "binding_validator": pin(HERE / "bind_actual_scope49.py", HERE),
        "owner_gate_fragment": pin(HERE / "owned_worker_gate.py.inc", HERE),
        "templates": {"worker_normal": pin(PREP / "worker.normal.template.py"), "worker_microg": pin(PREP / "worker.microg.template.py"),
            "transport": pin(PREP / "transport.template.py"), "stager": pin(OLD / "batch-01/stage_and_run_services.py")},
        "actual49_binding": summary, "app_scope": summary["scope"], "guard": guard,
        "runtime_epoch_sha256": scope["runtime_epoch_sha256"], "batches": rows,
        "identity_context_packages": 49, "service_target_packages": 46, "total_Android_readonly_commands": 106,
        "role_status": "UNKNOWN_NOT_QUERIED", "raw_capture_is_semantic_grant_proof": False,
        "source_only": True, "remote_jobs_submitted": 0, "claims_created": 0, "automatic_retry": False,
        "worker_total_deadline_seconds": 900, "per_command_seconds": 30, "default_stream_bytes": 262144,
        "exact_microg_second_stdout_bytes": 2097152, "production_ready": False, "private_body_exported_in_worker_stdout": False,
        "runtime_ledger_relative_path": "successor_audit_requests/actual/permissions-fixed46-r1",
        "preserved_old45_stop": [source.pin(source.source(key)) | {"file": source.PINS[key][0]}
                                 for key in ("old_b03_artifact", "old_b03_terminal", "old_b03_stop")]}
    mp = write("CAPTURE_PLAN.json", canonical(plan))
    write("SOURCE_INHERITANCE.json", canonical({"actual49_binding": summary, "rows": inheritance,
        "unsealed_preparation": pin(PREP / "PREPARATION_PINS.json"), "new_Main_actions": 0, "claims_created": 0}))
    gate = assignment(assignment(old_gate, "PLAN_SHA", mp["sha256"]), "PLAN_BYTES", mp["bytes"])
    gate = once(gate, "PROJECT = HERE.parents[1]", "PROJECT = HERE.parents[2]")
    gate = once(gate, 'LEDGER = PROJECT / "successor_audit_requests/actual/permissions-fixed45-r1"',
                'LEDGER = PROJECT / "successor_audit_requests/actual/permissions-fixed46-r1"')
    gate = gate.replace("fixed 13 permission raw-capture jobs", "fixed 14 permission raw-capture jobs")
    gate = gate.replace("these 45 service targets", "these 46 service targets")
    gate = once(gate, definition(gate, "load_closure"), (HERE / "gate_closure.py.inc").read_text().rstrip())
    stream = definition(gate, "stream_pair")
    stream = once(stream, "def stream_pair(command, record, root, prefix):", "def stream_pair(command, record, root, prefix, stdout_limit=262144):\n    need(type(stdout_limit) is int and stdout_limit in (262144, 2097152), \"CLOSED_STREAM_BUDGET_REQUIRED\")")
    stream = once(stream, 'type(pin["bytes"]) is int and 0 <= pin["bytes"] <= 262144',
                  'type(pin["bytes"]) is int and 0 <= pin["bytes"] <= (stdout_limit if name == "stdout" else 262144)')
    gate = once(gate, definition(gate, "stream_pair"), stream)
    service = definition(gate, "service_gate")
    service = once(service, '    root = request["output_root"]', '    need(baseline is False, "HISTORICAL45_PILOT_IS_NOT_A_NEW46_RESULT")\n    root = request["output_root"]')
    service = service.replace("FULL_47_CURRENT_IDENTITY_GUARDS_REQUIRED", "FULL_49_CURRENT_IDENTITY_GUARDS_REQUIRED")
    service = service.replace("native_catalog_matches_actual45_component_reference", "native_catalog_matches_actual46_component_reference")
    service = once(service, '"actual_framework_resolver_reference_job": "1a1b22e95d0-fc05-7cd4", "expected_count": 45, "observed_count": 45',
                   '"actual_framework_resolver_reference_job": "1a1b307f521-fc05-807a", "expected_count": 46, "observed_count": 46')
    service = once(service, '        stream_pair(row, row, root, "android-%02d" % index)',
        '''        microg = request["batch"] == 2 and request["target_packages"] == ["com.google.android.gms"]
        limits = {"stdout": 2097152 if microg and index == 2 else 262144, "stderr": 262144}
        if microg:
            need(row.get("capture_limits") == limits, "EXACT_MICROG_STREAM_LIMIT_INTENT_REQUIRED")
        else:
            need("capture_limits" not in row, "DEFAULT_STREAM_BUDGET_MUST_NOT_GAIN_EXCEPTION")
        stream_pair(row, row, root, "android-%02d" % index, limits["stdout"])''')
    gate = once(gate, definition(gate, "service_gate"), service)
    gate = gate.replace('"whole_47_current_identity_checked"', '"whole_49_current_identity_checked"')
    gate = gate.replace("range(1, 14)", "range(1, 15)").replace("range(number + 1, 14)", "range(number + 1, 15)")
    gate = gate.replace("ALL_45_RAW_CAPTURES_COMPLETE", "ALL_46_RAW_CAPTURES_COMPLETE")
    gate = gate.replace("SOURCE_CLOSURE_AND_ACTUAL_PILOT_BASELINE_VERIFIED", "SOURCE_CLOSURE_AND_ACTUAL49_INSTALL_READBACK_VERIFIED")
    gate = once(gate, '"batches": 13, "target_packages": 45, "Android_commands": 103', '"batches": 14, "target_packages": 46, "Android_commands": 106')
    compile(gate, "permission_capture_gate.py", "exec")
    gp = write("permission_capture_gate.py", gate)
    diff("serial-gate-against-original45.diff", old_gate, gate)
    coordinator = (OLD / "root_local_coordinator.py").read_text()
    need((len(coordinator.encode()), sha(coordinator.encode())) == (5606, "75465f43a213610800dd3c02f980b04c25638ebb2e67b3f2a3de1b492b647024"), "ORIGINAL_LOCAL_COORDINATOR_CHANGED")
    coord = assignment(assignment(coordinator, "GATE_SHA", gp["sha256"]), "PLAN_SHA", mp["sha256"])
    coord = once(coord, "PROJECT = HERE.parents[1]", "PROJECT = HERE.parents[2]")
    coord = coord.replace("actual/permissions-fixed45-r1", "actual/permissions-fixed46-r1")
    coord = once(coord, "assert 1 <= number <= 13", "assert 1 <= number <= 14")
    write("root_local_coordinator.py", coord)
    diff("coordinator-against-original45.diff", coordinator, coord)
    index = {"schema": "pocket4-permission46-ordered-request-index-v1", "plan": mp, "gate": gp,
        "actual49_scope": summary["scope"], "new_results": 0, "claims_created": 0, "remote_jobs_submitted": 0,
        "old45_STOP3_preserved": plan["preserved_old45_stop"], "rows": [{k: row[k] for k in
            ("batch", "targets", "target_identities", "process_request", "request", "idempotency_key", "source_root", "output_root")}
            for row in rows]}
    ip = write("REQUEST_INDEX.json", canonical(index))
    print(json.dumps({"plan": mp, "gate": gp, "request_index": ip, "batches": 14, "targets": 46,
        "protected_packages": 49, "commands": 106, "remote_jobs_submitted": 0, "claims_created": 0,
        "production_ready": False}, sort_keys=True))


if __name__ == "__main__":
    main()
