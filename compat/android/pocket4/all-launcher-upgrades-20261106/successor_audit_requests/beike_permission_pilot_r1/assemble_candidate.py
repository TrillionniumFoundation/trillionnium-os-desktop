#!/usr/bin/env python3
"""Locally seal a new Beike-only raw permission-service observation.

This program reads reviewed local source and evidence only. It never invokes
the worker, native CLI, an Android command, or the remote process service.
"""
import ast
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
PREVIOUS = PROJECT / "successor_audit_requests/current_services_r4"
STAGE = "/home/alex/work/pocket4-beike-permission-pilot-source-20261106-r1"
OUTPUT = "/home/alex/work/pocket4-beike-permission-pilot-observation-20261106-r1"
KEY = "sidecar-evidence-20261106-beike-permission-raw-pilot-r1"
FOUNDATION = {
    "observe_current_services.py": (39573, "4fda5cdf8fda65155c4187a1e8e5381aba59011329c824b98ad2e0c0b8aa8f0e"),
    "owned_readonly_lifetime.py": (18837, "ad2db51aa4445e6e5b5dc07439182556d51ec629cd8487ac9d3b1e5cf947a55c"),
    "readonly_services_transport.py": (16536, "4f8a4317332a1c80796378abfd0134a3329dd6acde9f06e96d8e52b70b3029b3"),
    "stage_and_run_services.py": (6763, "01efa4fad2e4b16e04fac90cf3e3883836d0e65e9d8eff393aa82e09b10e7882"),
    "process-request.review-only.json": (95091, "0d99c817131c6243ba4be0212e923df6e4e2951466dbba67827356e6560c4e1b"),
}
COMMANDS = (
    ("/system/bin/cmd", "package", "help"),
    ("/system/bin/cmd", "package", "dump-package", "com.lianjia.beike"),
    ("/system/bin/cmd", "appops", "get", "--user", "0", "com.lianjia.beike"),
)
HELP_LOCAL = PROJECT / "successor_audit_requests/current_services_r3/help-readback-r1/cmd-appops-help.original.txt"
HELP = {"path": STAGE + "/inputs/cmd-appops-help.original.txt", "bytes": 1309,
        "sha256": "95e3137d6acd3d920eb74f5d726a59232e6db9cb4efe8a4fedd6139074cb56cc"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")


def original(name):
    raw = (PREVIOUS / name).read_bytes()
    assert (len(raw), sha(raw)) == FOUNDATION[name], name
    return raw.decode("utf-8")


def write(name, raw):
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == raw, "EXISTING_CANDIDATE_DIFFERS: " + name
    else:
        with path.open("xb") as handle:
            handle.write(raw)
    return {"path": STAGE + "/" + name, "bytes": len(raw), "sha256": sha(raw)}


def replace_once(source, before, after):
    assert source.count(before) == 1, before[:100]
    return source.replace(before, after, 1)


def assignment(source, name, value):
    nodes = [node for node in ast.parse(source).body if isinstance(node, ast.Assign) and
             any(isinstance(target, ast.Name) and target.id == name for target in node.targets)]
    assert len(nodes) == 1, name
    return replace_once(source, ast.get_source_segment(source, nodes[0]), name + " = " + repr(value))


def definition(source, name):
    nodes = [node for node in ast.parse(source).body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name == name]
    assert len(nodes) == 1, name
    return ast.get_source_segment(source, nodes[0])


def diff(name, old, new):
    write(name + "-against-actual-r4.diff", "".join(difflib.unified_diff(
        old.splitlines(True), new.splitlines(True), fromfile="preserved-actual-current_services_r4/" + name,
        tofile="independent-beike-permission-pilot-r1/" + name)))


def main():
    old_transport = original("readonly_services_transport.py")
    transport = assignment(old_transport, "READ_ONLY_COMMANDS", COMMANDS)
    transport_pin = write("readonly_services_transport.py", transport)
    diff("transport", old_transport, transport)
    help_raw = HELP_LOCAL.read_bytes()
    assert (len(help_raw), sha(help_raw)) == (HELP["bytes"], HELP["sha256"])
    assert write("inputs/cmd-appops-help.original.txt", help_raw) == HELP

    old_worker = original("observe_current_services.py")
    worker = replace_once(old_worker, "New explicit47-bound user0 PM/resolver with PackageManager help only.",
                          "New explicit47-bound Beike-only raw permission-service observation.")
    worker = assignment(worker, "STAGE", STAGE)
    worker = assignment(worker, "OUTPUT", OUTPUT)
    worker = assignment(worker, "TRANSPORT", transport_pin)
    worker = replace_once(worker, "PACKAGES = sorted((*LAUNCHERS, ACTIONS, HELPER))",
                          "PACKAGES = sorted((*LAUNCHERS, ACTIONS, HELPER))\nTARGET_PACKAGE = 'com.lianjia.beike'\nTARGET_USER = 0\nAPP_OPS_HELP = " + repr(HELP))
    worker = replace_once(worker, 'set(request) == {"schema", "guard", "app_scope", "packages", "worker", "transport", "output_root"}',
                          'set(request) == {"schema", "guard", "app_scope", "packages", "worker", "transport", "output_root",\n                                                       "target_package", "target_user", "appops_help"}')
    worker = worker.replace('"pocket4-current-readonly-services-request-v1"', '"pocket4-beike-permission-raw-observation-request-v1"')
    worker = replace_once(worker, 'request["output_root"] == OUTPUT, "EXACT_SCOPE_AND_CLOSED_OPERATION_REQUEST")',
                          'request["output_root"] == OUTPUT and request["target_package"] == TARGET_PACKAGE and\n         type(request["target_user"]) is int and request["target_user"] == TARGET_USER and\n         request["appops_help"] == APP_OPS_HELP, "EXACT_SCOPE_AND_CLOSED_OPERATION_REQUEST")')
    help_function = '''def require_help_for_closed_queries(raw):
    text = raw.decode("utf-8", "strict")
    required = ("Package manager (package) commands:", "  dump-package PACKAGE\\n",
                "    Print package manager state associated with the given PACKAGE.")
    need(all(value in text for value in required), "ACTUAL_PACKAGE_HELP_DOES_NOT_SUPPORT_EXACT_READONLY_QUERIES")
    return {"actual_help_sha256": sha(raw), "required_literals": list(required), "no_guessed_service_transaction": True}


def require_appops_help(raw):
    text = raw.decode("utf-8", "strict")
    required = ("AppOps service (appops) commands:",
                "  get [--user <USER_ID>] [--attribution <ATTRIBUTION_TAG>] <PACKAGE | UID> [<OP>]\\n",
                "    Return the mode for a particular application and optional operation.")
    need(all(value in text for value in required), "ACTUAL_APPOPS_HELP_DOES_NOT_SUPPORT_FIXED_GET")
    return {"historical_help_pin": APP_OPS_HELP, "required_literals": list(required),
            "original_help_returncode": 255, "original_failed_job": "1a1b21fcc13-fc05-7c7a",
            "original_help_failure_reclassified": False, "get_success_inferred_from_help": False}
'''.rstrip()
    worker = replace_once(worker, definition(worker, "require_help_for_closed_queries"), help_function)
    worker = worker.replace('"pocket4-current-readonly-services-observation-v1"', '"pocket4-beike-permission-raw-observation-v1"')
    worker = replace_once(worker, '"android_commands": [], "native_commands": [], "effective_permission_grants": "UNKNOWN",',
                          '"android_commands": [], "native_commands": [],\n              "effective_permission_grants": "UNKNOWN_PENDING_SERVICE_OUTPUT_INTERPRETATION",\n              "effective_AppOps_modes": "UNKNOWN_PENDING_SERVICE_OUTPUT_INTERPRETATION",\n              "role_status": "UNKNOWN_NOT_QUERIED", "service_output_semantics_verified": False,\n              "service_output_capture_complete": False, "permission_name_normalization": "NONE_RAW_BYTES_PRESERVED",\n              "target_package": TARGET_PACKAGE, "target_user": TARGET_USER,\n              "service_target_packages": [TARGET_PACKAGE], "package_dump_user_filter_applied": False,')
    worker = replace_once(worker, '"effective_AppOps_and_roles": "UNKNOWN_NOT_QUERIED", "old_Bili_unknown_reclassified": False,',
                          '"old_Bili_unknown_reclassified": False,')
    worker = replace_once(worker, 'result["scope_guard_before"] = guard.check_app_scope(APP_SCOPE, PACKAGES)',
                          'result["scope_guard_before"] = guard.check_app_scope(APP_SCOPE, PACKAGES)\n        result["target_identity_from_pinned_scope"] = {key: scope["apps"][TARGET_PACKAGE][key]\n                    for key in ("package", "uid", "version_code")}\n        result["historical_appops_get_syntax_admission"] = require_appops_help(read_root_pin(APP_OPS_HELP))')
    start = worker.index('        installed_a, installed_b = parse_packages(raw_outputs[1]), parse_packages(raw_outputs[3])\n')
    end = worker.index('        result["native_after"] = native_read("status")\n', start)
    worker = worker[:start] + '''        result["help_results"] = {"package": {"stdout": result["android_commands"][0]["stdout"],
                                                "stderr": result["android_commands"][0]["stderr"], "returncode": 0}}
''' + worker[end:]
    worker = replace_once(worker, 'for pin in (GUARD, APP_SCOPE, TRANSPORT, NATIVE_HELPERS, request["worker"]):',
                          'for pin in (GUARD, APP_SCOPE, TRANSPORT, NATIVE_HELPERS, APP_OPS_HELP, request["worker"]):')
    start = worker.index('        result.update(ok=True, current_scope_47_unchanged=True, PM_user0_installed_APK_packages_enumerated=True,\n')
    end = worker.index('    except BaseException as error:\n        result["errors"].append({"type": type(error).__name__, "reason": str(error)[:512]})\n', start)
    worker = worker[:start] + '''        need(len(result["android_commands"]) == 3 and
             all(row.get("stream_artifacts_complete") is True for row in result["android_commands"]),
             "THREE_COMPLETE_ORIGINAL_SERVICE_STREAMS_REQUIRED")
        result.update(ok=True, current_scope_47_unchanged=True, service_output_capture_complete=True,
                      PM_user0_installed_APK_packages_enumerated=False, MAIN_LAUNCHER_resolver_queried=False,
                      all_installed_APK_bytes_bound=False)
''' + worker[end:]
    worker = replace_once(worker, '    result["status"] = "CURRENT_PM_AND_MAIN_LAUNCHER_OBSERVED" if result["ok"] else "READONLY_SERVICES_INCOMPLETE_NO_RETRY"',
                          '''    result["service_reports"] = [
        {"service": service, "argv": list(transport_module.READ_ONLY_COMMANDS[index]),
         "stdout": row.get("stdout"), "stderr": row.get("stderr"), "returncode": row.get("returncode"),
         "complete": row.get("complete"), "joined": row.get("joined"),
         "stream_artifacts_complete": row.get("stream_artifacts_complete", False),
         "interpretation_status": "RAW_CAPTURE_ONLY_NOT_INTERPRETED"}
        for index, service in ((1, "package-dump-package"), (2, "appops-get-user0"))
        if len(result["android_commands"]) > index for row in (result["android_commands"][index],)]
    result["permission_queries_executed"] = any("host_pid" in row for row in result["android_commands"][1:])
    result["status"] = "BEIKE_PERMISSION_SERVICE_RAW_CAPTURE_COMPLETE" if result["ok"] else "BEIKE_PERMISSION_OBSERVATION_INCOMPLETE_NO_RETRY"''')
    worker = worker.replace('"pocket4-readonly-service-entry-rejection-v1"', '"pocket4-beike-permission-entry-rejection-v1"')
    compile(worker, "observe_current_services.py", "exec")
    worker_pin = write("observe_current_services.py", worker)
    write("worker_body.py", worker[worker.index("def write_empty_raw_stream("):])
    diff("worker", old_worker, worker)

    namespace = {"__name__": "local_permission_source_definitions", "__file__": STAGE + "/observe_current_services.py"}
    exec(compile(worker, "observe_current_services.py", "exec"), namespace)
    request = {"schema": "pocket4-beike-permission-raw-observation-request-v1", "guard": namespace["GUARD"],
               "app_scope": namespace["APP_SCOPE"], "packages": namespace["PACKAGES"], "worker": worker_pin,
               "transport": transport_pin, "output_root": OUTPUT, "target_package": "com.lianjia.beike",
               "target_user": 0, "appops_help": HELP}
    request_pin = write("request.review-only.json", canonical(request))

    old_wrapper = original("owned_readonly_lifetime.py")
    config_node = next(node for node in ast.parse(old_wrapper).body if isinstance(node, ast.Assign) and
                       any(isinstance(target, ast.Name) and target.id == "CONFIG" for target in node.targets))
    config = ast.literal_eval(config_node.value)
    config.update(stage_root=STAGE, worker=worker_pin, request=request_pin)
    wrapper = assignment(old_wrapper, "CONFIG", config)
    before = definition(wrapper, "worker_gate")
    gate = before
    gate = gate.replace('"pocket4-current-readonly-services-observation-v1"', '"pocket4-beike-permission-raw-observation-v1"')
    gate = gate.replace('"CURRENT_PM_AND_MAIN_LAUNCHER_OBSERVED"', '"BEIKE_PERMISSION_SERVICE_RAW_CAPTURE_COMPLETE"')
    gate = replace_once(gate, '''             value.get("PM_user0_installed_APK_packages_enumerated") is True and
             value.get("MAIN_LAUNCHER_resolver_queried") is True and value.get("enumeration_samples_equal") is True and
             value.get("Android_namespace_commands") == 5 and value.get("native_command_count") == 3 and
             len(value.get("android_commands", [])) == 5 and len(value.get("native_commands", [])) == 3 and''',
        '''             value.get("target_package") == "com.lianjia.beike" and type(value.get("target_user")) is int and value["target_user"] == 0 and
             value.get("target_identity_from_pinned_scope") == {"package": "com.lianjia.beike", "uid": 10143, "version_code": 3067100} and
             value.get("service_target_packages") == ["com.lianjia.beike"] and value.get("service_output_capture_complete") is True and
             value.get("PM_user0_installed_APK_packages_enumerated") is False and value.get("MAIN_LAUNCHER_resolver_queried") is False and
             value.get("Android_namespace_commands") == 3 and value.get("native_command_count") == 3 and
             len(value.get("android_commands", [])) == 3 and len(value.get("native_commands", [])) == 3 and''')
    gate = replace_once(gate, 'row.get("termination_attempted") is False and row.get("errors") == [] for row in value["android_commands"])',
                        'row.get("termination_attempted") is False and row.get("errors") == [] and\n                 row.get("stream_artifacts_complete") is True for row in value["android_commands"])')
    gate = gate.replace('"READONLY_SERVICE_ENUMERATION_AND_RETIREMENT_GATE_FAILED"', '"RAW_PERMISSION_SERVICE_CAPTURE_AND_RETIREMENT_GATE_FAILED"')
    gate = replace_once(gate, '''        need(value.get("permission_queries_executed") is False and value.get("effective_permission_grants") == "UNKNOWN" and
             value.get("effective_AppOps_and_roles") == "UNKNOWN_NOT_QUERIED" and set(value.get("help_results", {})) == {"package"} and''',
        '''        need(value.get("permission_queries_executed") is True and value.get("service_output_semantics_verified") is False and
             value.get("effective_permission_grants") == "UNKNOWN_PENDING_SERVICE_OUTPUT_INTERPRETATION" and
             value.get("effective_AppOps_modes") == "UNKNOWN_PENDING_SERVICE_OUTPUT_INTERPRETATION" and
             value.get("role_status") == "UNKNOWN_NOT_QUERIED" and value.get("package_dump_user_filter_applied") is False and
             value.get("permission_name_normalization") == "NONE_RAW_BYTES_PRESERVED" and set(value.get("help_results", {})) == {"package"} and
             len(value.get("service_reports", [])) == 2 and
             all(row.get("interpretation_status") == "RAW_CAPTURE_ONLY_NOT_INTERPRETED" for row in value["service_reports"]) and''')
    wrapper = replace_once(wrapper, before, gate)
    compile(wrapper, "owned_readonly_lifetime.py", "exec")
    wrapper_pin = write("owned_readonly_lifetime.py", wrapper)
    diff("owned-adapter", old_wrapper, wrapper)

    files = [{"name": pin["path"][len(STAGE)+1:], "bytes": pin["bytes"], "sha256": pin["sha256"]}
             for pin in (wrapper_pin, worker_pin, transport_pin, request_pin, HELP)]
    old_stage = original("stage_and_run_services.py")
    stage = old_stage.replace("New exact source/input stage, then five fixed read-only PackageManager queries.",
                              "New exact source/input stage, then three Beike permission metadata reads.")
    stage = assignment(stage, "ROOT", STAGE)
    stage = assignment(stage, "FILES", files)
    stage = stage.replace("pocket4-current-readonly-services-source-stage-v4", "pocket4-beike-permission-pilot-source-stage-v1")
    stage = stage.replace("pocket4-current-readonly-services-source-stage-result-v4", "pocket4-beike-permission-pilot-source-stage-result-v1")
    compile(stage, "stage_and_run_services.py", "exec")
    write("stage_and_run_services.py", stage)
    diff("stager", old_stage, stage)
    payload = {"schema": "pocket4-beike-permission-pilot-source-stage-v1",
               "files": [{"name": row["name"], "text": (ROOT / row["name"]).read_text()} for row in files]}
    stdin = canonical(payload)
    assert len(stdin) <= 262144
    write("stage.stdin.original.json", stdin)
    packet = json.loads(original("process-request.review-only.json"))
    packet.update(idempotency_key=KEY, args=packet["args"][:-1] + [stage], stdin=stdin.decode("ascii"))
    write("process-request.review-only.json", canonical(packet))
    print(json.dumps({"source_frozen_only": True, "remote_executed": False, "worker": worker_pin,
                      "transport": transport_pin, "wrapper": wrapper_pin, "request": request_pin,
                      "stdin_bytes": len(stdin), "idempotency_key": KEY}, sort_keys=True))


if __name__ == "__main__":
    main()
