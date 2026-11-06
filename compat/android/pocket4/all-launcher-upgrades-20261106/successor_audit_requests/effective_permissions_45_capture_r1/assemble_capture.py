#!/usr/bin/env python3
"""Local assembly of thirteen exact read-only service-capture scopes; no jobs."""
import sys
sys.dont_write_bytecode = True
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
BASE = PROJECT / "successor_audit_requests/beike_permission_pilot_r1"
FOUNDATION = {
    "observe_current_services.py": (41792, "d403da0ef75940731df19032f3b1c495edd6a21fb11990df2b5d6744e14f08c4"),
    "readonly_services_transport.py": (16102, "5207d626008df00b7594310fb2d33933b6b9a9a6ccd982e4b5b7ed070cbebd76"),
    "owned_readonly_lifetime.py": (19789, "4aece066777ca3940e83b046b38082cf2a68f7f9b036549dce6564246edbb2a5"),
}
OLD_PLAN_SHA = "d288affedc2eae8d28f2d7083df4c89d756e51ba8e5ebfb2264f9d3c6d783139"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")


def read(name):
    raw = (BASE / name).read_bytes()
    if name in FOUNDATION:
        assert (len(raw), sha(raw)) == FOUNDATION[name], name
    return raw.decode("utf-8")


def write(name, raw):
    raw = raw.encode("utf-8") if isinstance(raw, str) else raw
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == raw, "EXISTING_REVISION_DIFFERS: " + name
    else:
        with path.open("xb") as handle:
            handle.write(raw)
    return {"file": name, "bytes": len(raw), "sha256": sha(raw)}


def once(text, old, new):
    assert text.count(old) == 1, old[:120]
    return text.replace(old, new, 1)


def assignment(text, name, value):
    node = next(n for n in ast.parse(text).body if isinstance(n, ast.Assign) and
                any(isinstance(t, ast.Name) and t.id == name for t in n.targets))
    return once(text, ast.get_source_segment(text, node), name + " = " + repr(value))


def definition(text, name):
    node = next(n for n in ast.parse(text).body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name)
    return ast.get_source_segment(text, node)


def diff(name, before, after):
    return write(name, "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
        fromfile="actual-beike-pilot/" + name, tofile="fixed-45-service-capture/" + name)))


def localpin(path):
    raw = path.read_bytes()
    return {"file": str(path.relative_to(PROJECT)), "bytes": len(raw), "sha256": sha(raw)}


def main():
    oldplan_path = PROJECT / "successor_audit_requests/final-upgrades-r1/REQUEST_MANIFEST.json"
    oldplan_raw = oldplan_path.read_bytes()
    assert sha(oldplan_raw) == OLD_PLAN_SHA
    oldplan = json.loads(oldplan_raw)
    scope_path = PROJECT / "successor_audit_requests/explicit47_scope_r2/actual-readback/app-scope.private.json"
    scope_raw = scope_path.read_bytes()
    assert (len(scope_raw), sha(scope_raw)) == (58854, "44f9ce783000a672c270e98afdaeb74bd79654508bfacae6793316ff4252e52f")
    scope = json.loads(scope_raw)
    resolver_path = PROJECT / "successor_audit_requests/current_services_r4/actual/worker.stdout.original.json"
    resolver_raw = resolver_path.read_bytes()
    assert (len(resolver_raw), sha(resolver_raw)) == (79176, "185c6b0900aab78228e44788ea28b10d71c39cfeee8846fcb8c99c13a9f123fc")
    resolver = json.loads(resolver_raw)
    components = sorted(row["component"] for row in resolver["MAIN_LAUNCHER_components"])
    targets45 = [p for row in oldplan["batches"] for p in row["packages"]]
    assert len(targets45) == len(set(targets45)) == len(components) == 45
    assert {row["package"] for row in resolver["MAIN_LAUNCHER_components"]} == set(targets45)
    old_worker, old_transport, old_wrapper = (read(n) for n in
        ("observe_current_services.py", "readonly_services_transport.py", "owned_readonly_lifetime.py"))
    old_stage = read("stage_and_run_services.py")
    old_packet = json.loads(read("process-request.review-only.json"))
    old_request = json.loads(read("request.review-only.json"))
    help_raw = (BASE / "inputs/cmd-appops-help.original.txt").read_bytes()
    assert (len(help_raw), sha(help_raw)) == (1309, "95e3137d6acd3d920eb74f5d726a59232e6db9cb4efe8a4fedd6139074cb56cc")
    preserved_worker = [n.name for n in ast.parse(old_worker).body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and
                        n.name not in ("validate_request", "run", "main")]
    preserved_wrapper = [n.name for n in ast.parse(old_wrapper).body if isinstance(n, ast.FunctionDef) and n.name != "worker_gate"]
    preserved_transport = [n.name for n in ast.parse(old_transport).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
    plan_rows = []
    for previous in oldplan["batches"]:
        number, targets = previous["batch"], previous["packages"]
        name = "batch-%02d" % number
        stage_root = "/home/alex/work/pocket4-launcher-permissions-source-20261106-r1-b%02d" % number
        output_root = "/home/alex/work/pocket4-launcher-permissions-observation-20261106-r1-b%02d" % number
        identities = [{k: scope["apps"][p][k] for k in ("package", "uid", "version_code")} for p in targets]
        commands = [("/system/bin/cmd", "package", "help")]
        for package in targets:
            commands += [("/system/bin/cmd", "package", "dump-package", package),
                         ("/system/bin/cmd", "appops", "get", "--user", "0", package)]
        transport = assignment(old_transport, "READ_ONLY_COMMANDS", tuple(commands))
        tp = write(name + "/readonly_services_transport.py", transport)
        remote_transport = {"path": stage_root + "/readonly_services_transport.py", "bytes": tp["bytes"], "sha256": tp["sha256"]}
        help_pin = {"path": stage_root + "/inputs/cmd-appops-help.original.txt", "bytes": len(help_raw), "sha256": sha(help_raw)}
        write(name + "/inputs/cmd-appops-help.original.txt", help_raw)
        worker = old_worker.replace("New explicit47-bound Beike-only raw permission-service observation.",
                                    "New explicit47-bound fixed Launcher-batch raw permission-service observation.")
        for key, value in (("STAGE", stage_root), ("OUTPUT", output_root), ("TRANSPORT", remote_transport), ("APP_OPS_HELP", help_pin)):
            worker = assignment(worker, key, value)
        worker = once(worker, "TARGET_PACKAGE = 'com.lianjia.beike'", "TARGET_PACKAGES = " + repr(targets) +
                      "\nBATCH_NUMBER = " + repr(number) + "\nACTUAL45_COMPONENTS = " + repr(components))
        worker = worker.replace('"target_package", "target_user", "appops_help"}', '"target_packages", "target_user", "appops_help", "batch"}')
        worker = worker.replace('"pocket4-beike-permission-raw-observation-request-v1"', '"pocket4-fixed-launcher-permission-capture-request-v1"')
        worker = once(worker, 'request["output_root"] == OUTPUT and request["target_package"] == TARGET_PACKAGE and',
                      'request["output_root"] == OUTPUT and request["target_packages"] == TARGET_PACKAGES and\n         type(request["batch"]) is int and request["batch"] == BATCH_NUMBER and')
        worker = worker.replace('"pocket4-beike-permission-raw-observation-v1"', '"pocket4-fixed-launcher-permission-raw-capture-v1"')
        worker = once(worker, '"target_package": TARGET_PACKAGE, "target_user": TARGET_USER,\n              "service_target_packages": [TARGET_PACKAGE],',
                      '"batch": BATCH_NUMBER, "target_packages": TARGET_PACKAGES, "target_user": TARGET_USER,\n              "service_target_packages": TARGET_PACKAGES,')
        worker = once(worker, '''        result["target_identity_from_pinned_scope"] = {key: scope["apps"][TARGET_PACKAGE][key]
                    for key in ("package", "uid", "version_code")}''', '''        result["target_identities_from_pinned_scope"] = [{key: scope["apps"][package][key]
                    for key in ("package", "uid", "version_code")} for package in TARGET_PACKAGES]''')
        marker = '        result["native_catalog"] = write("native-catalog.normalised.json", canonical(native_catalog)+b"\\n")\n'
        addition = '''        native_rows = native_catalog.get("applications")
        need(type(native_rows) is list and len(native_rows) <= 4096, "CURRENT_NATIVE_CATALOG_BOUND")
        current_components = []
        for row in native_rows:
            parsed = component(row["component"])
            need(parsed["package"] == row["package"], "NATIVE_COMPONENT_PACKAGE_DIFFERS")
            current_components.append(parsed["component"])
        result["native_catalog_comparison"] = {
            "actual_framework_resolver_reference_job": "1a1b22e95d0-fc05-7cd4",
            "expected_count": 45, "observed_count": len(current_components),
            "added_components": sorted(set(current_components) - set(ACTUAL45_COMPONENTS)),
            "missing_components": sorted(set(ACTUAL45_COMPONENTS) - set(current_components)),
            "framework_resolver_requeried_by_this_worker": False}
        need(len(current_components) == len(set(current_components)) == 45 and
             sorted(current_components) == ACTUAL45_COMPONENTS, "EXACT_ACTUAL45_NATIVE_COMPONENT_REFERENCE_CHANGED")
        result["native_catalog_matches_actual45_component_reference"] = True
'''
        worker = once(worker, marker, marker + addition)
        worker = once(worker, 'need(len(result["android_commands"]) == 3 and', 'need(len(result["android_commands"]) == 1 + 2 * len(TARGET_PACKAGES) and')
        worker = worker.replace('"THREE_COMPLETE_ORIGINAL_SERVICE_STREAMS_REQUIRED"', '"COMPLETE_FIXED_BATCH_SERVICE_STREAMS_REQUIRED"')
        worker = once(worker, '''        {"service": service, "argv": list(transport_module.READ_ONLY_COMMANDS[index]),''',
                      '''        {"target_package": package, "target_user": TARGET_USER, "service": service,
         "argv": list(transport_module.READ_ONLY_COMMANDS[index]),''')
        worker = once(worker, '''        for index, service in ((1, "package-dump-package"), (2, "appops-get-user0"))''',
                      '''        for pi, package in enumerate(TARGET_PACKAGES)
        for index, service in ((1 + 2 * pi, "package-dump-package"), (2 + 2 * pi, "appops-get-user0"))''')
        worker = worker.replace('"BEIKE_PERMISSION_SERVICE_RAW_CAPTURE_COMPLETE"', '"FIXED_LAUNCHER_PERMISSION_SERVICE_RAW_CAPTURE_COMPLETE"')
        worker = worker.replace('"BEIKE_PERMISSION_OBSERVATION_INCOMPLETE_NO_RETRY"', '"FIXED_LAUNCHER_PERMISSION_CAPTURE_INCOMPLETE_NO_RETRY"')
        worker = worker.replace('"pocket4-beike-permission-entry-rejection-v1"', '"pocket4-fixed-launcher-permission-entry-rejection-v1"')
        assert "TARGET_PACKAGE]" not in worker and "TARGET_PACKAGE," not in worker
        assert all(definition(worker, n) == definition(old_worker, n) for n in preserved_worker)
        assert all(definition(transport, n) == definition(old_transport, n) for n in preserved_transport)
        compile(worker, "observe_current_services.py", "exec")
        wp = write(name + "/observe_current_services.py", worker)
        remote_worker = {"path": stage_root + "/observe_current_services.py", "bytes": wp["bytes"], "sha256": wp["sha256"]}
        request = {k: v for k, v in old_request.items() if k != "target_package"}
        request.update(schema="pocket4-fixed-launcher-permission-capture-request-v1", batch=number,
                       output_root=output_root, target_packages=targets, transport=remote_transport, worker=remote_worker, appops_help=help_pin)
        rp = write(name + "/request.review-only.json", canonical(request))
        remote_request = {"path": stage_root + "/request.review-only.json", "bytes": rp["bytes"], "sha256": rp["sha256"]}
        cfg = next(ast.literal_eval(n.value) for n in ast.parse(old_wrapper).body if isinstance(n, ast.Assign) and
                   any(isinstance(t, ast.Name) and t.id == "CONFIG" for t in n.targets))
        cfg.update(stage_root=stage_root, worker=remote_worker, request=remote_request)
        wrapper = assignment(old_wrapper, "CONFIG", cfg)
        gate = definition(wrapper, "worker_gate")
        gate = gate.replace('"pocket4-beike-permission-raw-observation-v1"', '"pocket4-fixed-launcher-permission-raw-capture-v1"')
        gate = gate.replace('"BEIKE_PERMISSION_SERVICE_RAW_CAPTURE_COMPLETE"', '"FIXED_LAUNCHER_PERMISSION_SERVICE_RAW_CAPTURE_COMPLETE"')
        gate = once(gate, 'value.get("target_package") == "com.lianjia.beike" and type(value.get("target_user")) is int and value["target_user"] == 0 and',
                    'value.get("batch") == ' + str(number) + ' and value.get("target_packages") == ' + repr(targets) + ' and\n             type(value.get("target_user")) is int and value["target_user"] == 0 and')
        gate = once(gate, 'value.get("target_identity_from_pinned_scope") == {"package": "com.lianjia.beike", "uid": 10143, "version_code": 3067100}',
                    'value.get("target_identities_from_pinned_scope") == ' + repr(identities))
        gate = once(gate, 'value.get("service_target_packages") == ["com.lianjia.beike"]', 'value.get("service_target_packages") == ' + repr(targets))
        gate = once(gate, 'value.get("Android_namespace_commands") == 3', 'value.get("Android_namespace_commands") == ' + str(len(commands)))
        gate = once(gate, 'len(value.get("android_commands", [])) == 3', 'len(value.get("android_commands", [])) == ' + str(len(commands)))
        gate = once(gate, 'len(value.get("service_reports", [])) == 2', 'len(value.get("service_reports", [])) == ' + str(2 * len(targets)))
        gate = once(gate, 'value.get("compiled_Beike_scope_modified") is False',
                    'value.get("native_catalog_matches_actual45_component_reference") is True and\n             value.get("compiled_Beike_scope_modified") is False')
        wrapper = once(wrapper, definition(wrapper, "worker_gate"), gate)
        assert all(definition(wrapper, n) == definition(old_wrapper, n) for n in preserved_wrapper)
        compile(wrapper, "owned_readonly_lifetime.py", "exec")
        op = write(name + "/owned_readonly_lifetime.py", wrapper)
        files = [{"name": filename, "bytes": row["bytes"], "sha256": row["sha256"]} for filename, row in
                 (("owned_readonly_lifetime.py", op), ("observe_current_services.py", wp),
                  ("readonly_services_transport.py", tp), ("request.review-only.json", rp), ("inputs/cmd-appops-help.original.txt", help_pin))]
        stage = assignment(assignment(old_stage, "ROOT", stage_root), "FILES", files)
        stage = stage.replace("New exact source/input stage, then three Beike permission metadata reads.",
                              "New exact source/input stage, then one fixed Launcher batch of permission metadata reads.")
        stage = stage.replace("pocket4-beike-permission-pilot-source-stage-v1", "pocket4-fixed-launcher-permission-source-stage-v1")
        stage = stage.replace("pocket4-beike-permission-pilot-source-stage-result-v1", "pocket4-fixed-launcher-permission-source-stage-result-v1")
        sp = write(name + "/stage_and_run_services.py", stage)
        payload = {"schema": "pocket4-fixed-launcher-permission-source-stage-v1", "files": [
            {"name": row["name"], "text": (HERE / name / row["name"]).read_text()} for row in files]}
        stdin = canonical(payload)
        assert len(stdin) <= 262144
        write(name + "/stage.stdin.original.json", stdin)
        packet = dict(old_packet)
        packet.update(idempotency_key="sidecar-evidence-20261106-fixed-launcher-permissions-r1-b%02d" % number,
                      args=old_packet["args"][:-1] + [stage], stdin=stdin.decode())
        pp = write(name + "/process-request.review-only.json", canonical(packet))
        if number == 1:
            for filename, before, after in (("worker-against-actual-pilot.diff", old_worker, worker),
                ("transport-against-actual-pilot.diff", old_transport, transport),
                ("owned-adapter-against-actual-pilot.diff", old_wrapper, wrapper),
                ("stager-against-actual-pilot.diff", old_stage, stage)):
                diff(filename, before, after)
        plan_rows.append({"batch": number, "original_partition_batch": number, "targets": targets,
            "target_identities": identities, "Android_commands": commands, "native_operations": ["status", "applications", "status"],
            "worker": remote_worker, "worker_file": wp["file"], "transport": remote_transport, "transport_file": tp["file"],
            "wrapper": {"path": stage_root + "/owned_readonly_lifetime.py", "bytes": op["bytes"], "sha256": op["sha256"]},
            "wrapper_file": op["file"], "request": remote_request, "request_file": rp["file"], "stager": sp,
            "process_request": pp, "source_root": stage_root, "output_root": output_root,
            "idempotency_key": packet["idempotency_key"], "stage_files": files})
    proof_names = ("observe_current_services.py", "readonly_services_transport.py", "owned_readonly_lifetime.py",
                   "actual/stdout.original.jsonl", "actual/status-01.original.txt", "actual/worker.stdout.original.json")
    manifest = {"schema": "pocket4-fixed-45-permission-raw-capture-plan-v1", "target_packages": targets45,
        "original_partition": localpin(oldplan_path), "baseline_pilot_job": "1a1b279845c-fc05-7e2e",
        "baseline_pilot_public_proof": [localpin(BASE / p) for p in proof_names],
        "app_scope": old_request["app_scope"], "app_scope_local": localpin(scope_path), "guard": old_request["guard"],
        "resolver_reference": localpin(resolver_path), "runtime_epoch_sha256": oldplan["runtime_epoch_sha256"],
        "batches": plan_rows, "identity_context_packages": 47, "service_target_packages": 45,
        "total_Android_readonly_commands": 103, "role_status": "UNKNOWN_NOT_QUERIED", "raw_capture_is_semantic_grant_proof": False,
        "source_only": True, "remote_jobs_submitted": 0, "claims_created": 0, "automatic_retry": False,
        "worker_total_deadline_seconds": 900, "per_command_seconds": 30, "per_stream_bytes": 262144,
        "production_ready": False, "private_body_exported_in_worker_stdout": False,
        "preserved_worker_definitions": preserved_worker, "preserved_transport_definitions": preserved_transport,
        "preserved_owned_definitions": preserved_wrapper,
        "runtime_ledger_relative_path": "successor_audit_requests/actual/permissions-fixed45-r1"}
    mp = write("CAPTURE_PLAN.json", canonical(manifest))
    print(json.dumps({"plan": mp, "batches": 13, "service_targets": 45, "commands": 103,
                      "remote_jobs": 0, "claims": 0, "unchanged_worker_definitions": len(preserved_worker),
                      "unchanged_transport_definitions": len(preserved_transport), "unchanged_owned_definitions": len(preserved_wrapper)}, sort_keys=True))


if __name__ == "__main__":
    main()
