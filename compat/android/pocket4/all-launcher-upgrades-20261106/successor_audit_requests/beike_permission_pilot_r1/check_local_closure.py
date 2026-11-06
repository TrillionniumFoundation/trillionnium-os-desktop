#!/usr/bin/env python3
"""Read exact local help/source evidence and check the new sealed closure only."""
import ast
import hashlib
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
PREVIOUS = PROJECT / "successor_audit_requests/current_services_r4"
EXACT = {
    "observe_current_services.py": (41792, "d403da0ef75940731df19032f3b1c495edd6a21fb11990df2b5d6744e14f08c4"),
    "readonly_services_transport.py": (16102, "5207d626008df00b7594310fb2d33933b6b9a9a6ccd982e4b5b7ed070cbebd76"),
    "owned_readonly_lifetime.py": (19789, "4aece066777ca3940e83b046b38082cf2a68f7f9b036549dce6564246edbb2a5"),
}
COMMANDS = (
    ("/system/bin/cmd", "package", "help"),
    ("/system/bin/cmd", "package", "dump-package", "com.lianjia.beike"),
    ("/system/bin/cmd", "appops", "get", "--user", "0", "com.lianjia.beike"),
)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path):
    raw = path.read_bytes()
    return {"path": str(path.relative_to(PROJECT)), "bytes": len(raw), "sha256": sha(raw)}


def functions(source):
    return {node.name: ast.get_source_segment(source, node) for node in ast.parse(source).body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))}


def variables(source):
    return {target.id: ast.get_source_segment(source, node) for node in ast.parse(source).body if isinstance(node, ast.Assign)
            for target in node.targets if isinstance(target, ast.Name)}


def only_changes(old, new, expected):
    names = set(old) | set(new)
    actual = {name for name in names if old.get(name) != new.get(name)}
    assert actual == set(expected), sorted(actual)
    return sorted(names - actual)


def main():
    before = len(os.listdir("/proc/self/fd"))
    source = {name: (ROOT / name).read_text() for name in EXACT}
    for name, expected in EXACT.items():
        raw = source[name].encode()
        assert (len(raw), sha(raw)) == expected
        compile(source[name], name, "exec")
    worker = source["observe_current_services.py"]
    transport = source["readonly_services_transport.py"]
    wrapper = source["owned_readonly_lifetime.py"]
    old_worker = (PREVIOUS / "observe_current_services.py").read_text()
    old_transport = (PREVIOUS / "readonly_services_transport.py").read_text()
    old_wrapper = (PREVIOUS / "owned_readonly_lifetime.py").read_text()
    unchanged = {
        "worker_top_level_definitions": only_changes(functions(old_worker), functions(worker),
                {"validate_request", "require_help_for_closed_queries", "require_appops_help", "run", "main"}),
        "transport_definitions": only_changes(functions(old_transport), functions(transport), set()),
        "owned_lifetime_definitions": only_changes(functions(old_wrapper), functions(wrapper), {"worker_gate"}),
    }
    only_changes(variables(old_transport), variables(transport), {"READ_ONLY_COMMANDS"})
    only_changes(variables(old_wrapper), variables(wrapper), {"CONFIG"})
    run = next(node for node in ast.parse(worker).body if isinstance(node, ast.FunctionDef) and node.name == "run")
    old_run = next(node for node in ast.parse(old_worker).body if isinstance(node, ast.FunctionDef) and node.name == "run")
    inner = lambda node, text: {child.name: ast.get_source_segment(text, child) for child in node.body if isinstance(child, ast.FunctionDef)}
    unchanged["nested_runtime_native_stream_and_runner_definitions"] = only_changes(inner(old_run, old_worker), inner(run, worker), set())
    calls = {node.func.id for node in ast.walk(run) if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    assert not {"parse_packages", "parse_resolver", "compare_catalogs"} & calls
    namespace = {"__name__": "local_help_check_only", "__file__": str(ROOT / "observe_current_services.py")}
    exec(compile(worker, namespace["__file__"], "exec"), namespace)
    tn = {"__name__": "local_closed_transport_definitions", "__file__": str(ROOT / "readonly_services_transport.py")}
    exec(compile(transport, tn["__file__"], "exec"), tn)
    assert tn["READ_ONLY_COMMANDS"] == COMMANDS
    package_path = PROJECT / "successor_audit_requests/current_services_r3/help-readback-r1/cmd-package-help.original.txt"
    package_help = package_path.read_bytes()
    appops_path = ROOT / "inputs/cmd-appops-help.original.txt"
    appops_help = appops_path.read_bytes()
    assert (len(package_help), sha(package_help)) == (40229, "a58bc73742b985565a5d72b668db8d8a575d38efa49851069364a120b8735ef4")
    assert (len(appops_help), sha(appops_help)) == (1309, "95e3137d6acd3d920eb74f5d726a59232e6db9cb4efe8a4fedd6139074cb56cc")
    package_admission = namespace["require_help_for_closed_queries"](package_help)
    appops_admission = namespace["require_appops_help"](appops_help)
    negatives = []
    for function, raw, line in (
        ("require_help_for_closed_queries", package_help, b"  dump-package PACKAGE\n"),
        ("require_appops_help", appops_help,
         b"  get [--user <USER_ID>] [--attribution <ATTRIBUTION_TAG>] <PACKAGE | UID> [<OP>]\n"),
    ):
        assert raw.count(line) == 1
        try:
            namespace[function](raw.replace(line, b"", 1))
        except RuntimeError as error:
            negatives.append({"missing_exact_help_line": line.decode().rstrip("\n"), "rejected": True, "reason": str(error)})
        else:
            raise AssertionError("missing actual help syntax was accepted")
    scope_path = PROJECT / "successor_audit_requests/explicit47_scope_r2/actual-readback/app-scope.private.json"
    scope_raw = scope_path.read_bytes()
    assert (len(scope_raw), sha(scope_raw)) == (58854, "44f9ce783000a672c270e98afdaeb74bd79654508bfacae6793316ff4252e52f")
    scope = json.loads(scope_raw)
    assert set(namespace["PACKAGES"]) == set(scope["apps"]) and len(scope["apps"]) == 47
    target = {key: scope["apps"]["com.lianjia.beike"][key] for key in ("package", "uid", "version_code")}
    assert target == {"package": "com.lianjia.beike", "uid": 10143, "version_code": 3067100}
    request = json.loads((ROOT / "request.review-only.json").read_bytes())
    assert request["target_package"] == "com.lianjia.beike" and type(request["target_user"]) is int and request["target_user"] == 0
    assert request["packages"] == namespace["PACKAGES"] and request["app_scope"] == namespace["APP_SCOPE"]
    for key in ("worker", "transport", "appops_help"):
        row = request[key]
        relative = row["path"][len(namespace["STAGE"])+1:]
        raw = (ROOT / relative).read_bytes()
        assert len(raw) == row["bytes"] and sha(raw) == row["sha256"]
    packet = json.loads((ROOT / "process-request.review-only.json").read_bytes())
    prior_packet = json.loads((PREVIOUS / "process-request.review-only.json").read_bytes())
    assert packet["args"][:-1] == prior_packet["args"][:-1]
    assert packet["args"][-1] == (ROOT / "stage_and_run_services.py").read_text()
    assert packet["stdin"].encode() == (ROOT / "stage.stdin.original.json").read_bytes()
    assert packet["idempotency_key"] == "sidecar-evidence-20261106-beike-permission-raw-pilot-r1"
    assert {k: v for k, v in packet.items() if k not in {"args", "stdin", "idempotency_key"}} == {
        k: v for k, v in prior_packet.items() if k not in {"args", "stdin", "idempotency_key"}}
    stage_text = packet["args"][-1]
    compile(stage_text, "stage_and_run_services.py", "exec")
    stage_files = ast.literal_eval(next(node.value for node in ast.parse(stage_text).body if isinstance(node, ast.Assign)
                                   and any(isinstance(target, ast.Name) and target.id == "FILES" for target in node.targets)))
    payload = json.loads(packet["stdin"])
    assert payload["schema"] == "pocket4-beike-permission-pilot-source-stage-v1"
    assert len(stage_files) == len(payload["files"]) == 5
    for expected, item in zip(stage_files, payload["files"]):
        raw = item["text"].encode()
        assert item["name"] == expected["name"]
        assert len(raw) == expected["bytes"] and sha(raw) == expected["sha256"]
        assert raw == (ROOT / item["name"]).read_bytes()
    after = len(os.listdir("/proc/self/fd"))
    assert before == after
    result = {
        "schema": "pocket4-beike-permission-pilot-local-closure-review-v1", "ok": True,
        "evidence_basis": "Actual local service-help bytes and pinned actual47 App scope; no synthetic runtime PASS.",
        "closed_Android_commands": COMMANDS, "target_from_actual_scope": target,
        "actual_package_help": pin(package_path), "actual_appops_help": pin(appops_path),
        "package_help_admission": package_admission, "historical_appops_syntax_admission": appops_admission,
        "missing_syntax_negative_controls": negatives, "unchanged_exact_definitions": unchanged,
        "all_five_staged_files_match_packet_and_source_pins": True,
        "old_r2_timeout_and_r3_empty_stream_controls_rerun": False,
        "grant_mode_interpretation_tested": False, "runtime_or_Android_commands": 0, "Main_reads": 0,
        "namespace_entries": 0, "permission_changes": 0, "local_process_FDs_before": before, "local_process_FDs_after": after,
        "runtime_qualified_by_this_local_check": False, "production_ready": False,
    }
    raw = (json.dumps(result, sort_keys=True, ensure_ascii=True, indent=2) + "\n").encode()
    with (ROOT / "LOCAL_CLOSURE_REVIEW.actual.json").open("xb") as handle:
        handle.write(raw)
    print(json.dumps({"ok": True, "result": pin(ROOT / "LOCAL_CLOSURE_REVIEW.actual.json")}, sort_keys=True))


if __name__ == "__main__":
    main()
