#!/usr/bin/env python3
"""Local-only deterministic independent discovery candidate. No device calls."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[1]
BASE = PROJECT / "successor_audit_requests/current_services_r4"
STAGE = "/home/alex/work/pocket4-native46-discovery-source-20261106-r1"
OUTPUT = "/home/alex/work/pocket4-native46-discovery-observation-20261106-r1"
NEW_PACKAGE = "com.example.ndk_tests"
NEW_COMPONENT = NEW_PACKAGE + "/com.example.ndk_tests.NdkTestsActivity"
REFERENCE = {
    "observe_current_services.py": (39573, "4fda5cdf8fda65155c4187a1e8e5381aba59011329c824b98ad2e0c0b8aa8f0e"),
    "readonly_services_transport.py": (16536, "4f8a4317332a1c80796378abfd0134a3329dd6acde9f06e96d8e52b70b3029b3"),
    "owned_readonly_lifetime.py": (18837, "ad2db51aa4445e6e5b5dc07439182556d51ec629cd8487ac9d3b1e5cf947a55c"),
    "stage_and_run_services.py": (6763, "01efa4fad2e4b16e04fac90cf3e3883836d0e65e9d8eff393aa82e09b10e7882"),
}
INPUTS = {
    "previous_pm": ("successor_audit_requests/current_services_r4/actual/worker.stdout.original.json", 79176,
                    "185c6b0900aab78228e44788ea28b10d71c39cfeee8846fcb8c99c13a9f123fc"),
    "failed_capture": ("successor_audit_requests/actual/permissions-fixed45-r1/batch-03/artifact.original.json", 12181,
                       "f5ff1b1758803a9537bd84023146fa62ac72d8587b1dc94605868413dd2ffc08"),
    "failed_terminal": ("successor_audit_requests/actual/permissions-fixed45-r1/batch-03/terminal.original.json", 730,
                        "4a95cb262ac9b2d8d4a0437c53fde9e82ea47b4529e6fd0e79fa87b32ef24552"),
}


def need(ok, code):
    if not ok:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode() + b"\n"


def read(path, size, digest):
    raw = path.read_bytes()
    need(len(raw) == size and sha(raw) == digest, "EXACT_REFERENCE: " + str(path))
    return raw


def save(name, raw):
    path = ROOT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as stream:
        stream.write(raw)
    need(path.read_bytes() == raw, "LOCAL_WRITE_READBACK")
    return {"path": STAGE + "/" + name, "bytes": len(raw), "sha256": sha(raw)}


def assign(text, name, value):
    nodes = [n for n in ast.parse(text).body if isinstance(n, ast.Assign) and
             any(isinstance(t, ast.Name) and t.id == name for t in n.targets)]
    need(len(nodes) == 1, "UNIQUE_ASSIGNMENT: " + name)
    node = nodes[0]
    lines = text.splitlines(True)
    return "".join(lines[:node.lineno - 1]) + name + " = " + repr(value) + "\n" + "".join(lines[node.end_lineno:])


def function(text, name):
    nodes = [n for n in ast.parse(text).body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name]
    need(len(nodes) == 1, "UNIQUE_DEFINITION: " + name)
    node = nodes[0]
    return "".join(text.splitlines(True)[node.lineno - 1:node.end_lineno])


def once(text, old, new):
    need(text.count(old) == 1, "EXACT_REPLACEMENT: " + old[:100])
    return text.replace(old, new, 1)


def diff(name, before, after):
    save(name, "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
         fromfile="actual-current-services-r4", tofile="independent-native46-discovery-r1")).encode())


def main():
    sources = {name: read(BASE / name, *pin).decode() for name, pin in REFERENCE.items()}
    prior = {name: save("inputs/" + name + ".json", read(PROJECT / path, size, digest))
             for name, (path, size, digest) in INPUTS.items()}
    old_transport = sources["readonly_services_transport.py"]
    namespace = {"__name__": "local_definitions"}
    exec(compile(old_transport, "frozen_transport", "exec"), namespace)
    commands = (*namespace["READ_ONLY_COMMANDS"], ("/system/bin/cmd", "package", "dump-package", NEW_PACKAGE))
    transport = assign(old_transport, "READ_ONLY_COMMANDS", commands)
    transport_pin = save("readonly_services_transport.py", transport.encode())
    diff("transport-against-actual-r4.diff", old_transport, transport)

    old_worker = sources["observe_current_services.py"]
    worker = assign(assign(assign(old_worker, "STAGE", STAGE), "OUTPUT", OUTPUT), "TRANSPORT", transport_pin)
    worker = once(worker, "def need(value, code):", "NEW_PACKAGE = " + repr(NEW_PACKAGE) +
                  "\nNEW_COMPONENT = " + repr(NEW_COMPONENT) + "\nPRIOR = " + repr(prior) + "\n\ndef need(value, code):")
    worker = worker.replace("pocket4-current-readonly-services-request-v1", "pocket4-native46-discovery-request-v1")
    worker = worker.replace("pocket4-current-readonly-services-observation-v1", "pocket4-native46-discovery-observation-v1")
    worker = worker.replace("/observe_current_services.py", "/observe_native46.py")
    worker = once(worker, '"query-activities", "--components", "INTENT", "-a <ACTION>", "-c <CATEGORY>")',
                  '"query-activities", "--components", "INTENT", "-a <ACTION>", "-c <CATEGORY>", "dump-package PACKAGE")')
    extension = (ROOT / "discovery_functions.py.inc").read_text()
    worker = once(worker, "def run(request):", extension + "\n\ndef run(request):")
    worker = once(worker, "    validate_request(request)\n", "    validate_request(request)\n    previous = prior_observations()\n")
    worker = once(worker, '    deadline = time.monotonic() + 900\n',
                  '    result.update(original_b03_failure_preserved=True, original_permission_gate_modified=False,\n'
                  '                  new_scope_published=False, new_signature_verification_performed=False,\n'
                  '                  vendor_artifact_source_trust="UNKNOWN", permissions_interpreted=False,\n'
                  '                  prior_evidence=PRIOR, observed_started_unix_ns=time.time_ns(),\n'
                  '                  observed_started_monotonic_ns=time.monotonic_ns())\n'
                  '    new_identity = None\n    deadline = time.monotonic() + 900\n')
    worker = once(worker, '        core.app_scope(pool, held, PACKAGES, scope["apps"], False)\n',
                  '        core.app_scope(pool, held, PACKAGES, scope["apps"], False)\n'
                  '        if new_identity is not None:\n'
                  '            core.app_scope(pool, held, [NEW_PACKAGE], new_identity, False)\n')
    worker = once(worker, '        for index, argv in enumerate(transport_module.READ_ONLY_COMMANDS):',
                  '        for index, argv in enumerate(transport_module.READ_ONLY_COMMANDS[:5]):')
    anchor = '        result["catalog_comparison"] = compare_catalogs(installed_a, resolver_a, native_catalog, scope["apps"])\n'
    addition = '''        result["discovery_comparison_before"] = discovery_comparison(installed_a, resolver_a, native_catalog, previous)
        need(result["discovery_comparison_before"]["matches_only_the_observed_new_component"],
             "CURRENT_COMPLETE_ROSTERS_DIFFER_FROM_THE_NARROW_DISCOVERY_QUESTION")
        new_identity, metadata_binding = bind_new_package(core, pool, held,
            result["discovery_comparison_before"]["PM_target_rows"][0], deadline)
        result["new_package_identity"] = new_identity[NEW_PACKAGE]
        result["new_package_metadata_binding"] = metadata_binding
        result["new_package_identity_receipt"] = write("new-package-identity.private.json", canonical(new_identity)+b"\\n")
        runtime_guard()
        dump_raw = transport(list(transport_module.READ_ONLY_COMMANDS[5]), timeout=30)
        need(result["android_commands"][-1]["complete"] is True, "NEW_PACKAGE_DUMP_NOT_COMPLETE_CLEANLY")
        result["new_package_service_metadata"] = selected_dump_metadata(dump_raw, NEW_PACKAGE,
            new_identity[NEW_PACKAGE]["uid"], new_identity[NEW_PACKAGE]["version_code"])
        result["new_package_private_dump_reference"] = result["android_commands"][-1]["stdout"]
        native_catalog_after = native_read("applications")
        result["native_catalog_after"] = write("native-catalog-after.normalised.json", canonical(native_catalog_after)+b"\\n")
        result["discovery_comparison_after"] = discovery_comparison(installed_b, resolver_b, native_catalog_after, previous)
        need(result["discovery_comparison_after"] == result["discovery_comparison_before"],
             "CURRENT_NATIVE_COMPONENTS_CHANGED_DURING_DISCOVERY")
        final_metadata = new_package_metadata(core, pool, held)
        need(final_metadata["package_row"] == metadata_binding["after"]["package_row"] and
             final_metadata["safe_attributes"] == metadata_binding["after"]["safe_attributes"],
             "NEW_PACKAGE_METADATA_CHANGED_AFTER_SERVICE_READ")
        result["new_package_metadata_final"] = final_metadata
        result["proposed_immutable_scope_review"] = {
            "original_packages": PACKAGES, "additional_package": NEW_PACKAGE,
            "proposed_packages": sorted((*PACKAGES, NEW_PACKAGE)), "proposed_count": 48,
            "original_scope_reference": APP_SCOPE, "new_identity_reference": result["new_package_identity_receipt"],
            "new_scope_published": False, "new_runtime_or_UI_authority": False,
            "requires_separate_exact_signed_APK_and_scope_review": True}
'''
    worker = once(worker, anchor, anchor + addition)
    worker = once(worker, '        for pin in (GUARD, APP_SCOPE, TRANSPORT, NATIVE_HELPERS, request["worker"]):',
                  '        for pin in (GUARD, APP_SCOPE, TRANSPORT, NATIVE_HELPERS, request["worker"], *PRIOR.values()):')
    worker = once(worker, '        result.update(ok=True, current_scope_47_unchanged=True,',
                  '        result.update(ok=True, new_package_identity_observed=True,\n'
                  '                      prior_sources_unchanged=True, observed_finished_unix_ns=time.time_ns(),\n'
                  '                      observed_finished_monotonic_ns=time.monotonic_ns(), current_scope_47_unchanged=True,')
    worker = once(worker, 'enumeration_samples_equal=True, permission_queries_executed=False)',
                  'enumeration_samples_equal=True, permission_queries_executed=True,\n'
                  '                      package_dump_contains_uninterpreted_permission_sections=True)')
    worker = once(worker, '"CURRENT_PM_AND_MAIN_LAUNCHER_OBSERVED" if result["ok"] else "READONLY_SERVICES_INCOMPLETE_NO_RETRY"',
                  '"NATIVE46_AND_NEW_PACKAGE_IDENTITY_OBSERVED_NO_SCOPE_PROMOTION" if result["ok"] else "NATIVE46_DISCOVERY_INCOMPLETE_NO_RETRY"')
    compile(worker, "observe_native46.py", "exec")
    worker_pin = save("observe_native46.py", worker.encode())
    diff("worker-against-actual-r4.diff", old_worker, worker)
    space = {"__name__": "local_discovery_definitions", "__file__": STAGE + "/observe_native46.py"}
    exec(compile(worker, "observe_native46.py", "exec"), space)
    request = {"schema": "pocket4-native46-discovery-request-v1", "guard": space["GUARD"],
               "app_scope": space["APP_SCOPE"], "packages": space["PACKAGES"], "worker": worker_pin,
               "transport": transport_pin, "output_root": OUTPUT}
    request_pin = save("request.review-only.json", canonical(request))

    old_owned = sources["owned_readonly_lifetime.py"]
    owned_config = {"schema": "pocket4-owned-readonly-observation-config-v1", "kind": "services",
                    "stage_root": STAGE, "worker": worker_pin, "request": request_pin,
                    "prior_source": {"bytes": REFERENCE["owned_readonly_lifetime.py"][0],
                                     "sha256": REFERENCE["owned_readonly_lifetime.py"][1],
                                     "preserved": True, "actual_prior_execution_job": "1a1b22e95d0-fc05-7cd4",
                                     "scope_authority_not_inherited": True}}
    owned = assign(old_owned, "CONFIG", owned_config)
    owned = once(owned, 'value.get("schema") == "pocket4-current-readonly-services-observation-v1"',
                 'value.get("schema") == "pocket4-native46-discovery-observation-v1"')
    owned = once(owned, 'value.get("status") == "CURRENT_PM_AND_MAIN_LAUNCHER_OBSERVED"',
                 'value.get("status") == "NATIVE46_AND_NEW_PACKAGE_IDENTITY_OBSERVED_NO_SCOPE_PROMOTION"')
    owned = once(owned, 'value.get("Android_namespace_commands") == 5 and value.get("native_command_count") == 3',
                 'value.get("Android_namespace_commands") == 6 and value.get("native_command_count") == 4')
    owned = once(owned, 'len(value.get("android_commands", [])) == 5 and len(value.get("native_commands", [])) == 3',
                 'len(value.get("android_commands", [])) == 6 and len(value.get("native_commands", [])) == 4')
    owned = once(owned, 'value.get("permission_queries_executed") is False and',
                 'value.get("permission_queries_executed") is True and\n'
                 '             value.get("package_dump_contains_uninterpreted_permission_sections") is True and\n'
                 '             value.get("permissions_interpreted") is False and')
    anchor = '        actions = ("UI_actions", "App_launches", "installs", "permission_changes", "lifecycle_commands", "ADB_commands", "business_data_content_reads")\n'
    extra_gate = '''        proof = value.get("discovery_comparison_before", {})
        need(proof.get("matches_only_the_observed_new_component") is True and
             proof.get("current_resolver_component_count") == proof.get("current_native_component_count") == 46 and
             proof.get("added_components") == ["com.example.ndk_tests/com.example.ndk_tests.NdkTestsActivity"] and
             proof.get("missing_components") == proof.get("framework_only_components") == proof.get("native_only_components") == [] and
             value.get("discovery_comparison_after") == proof and value.get("new_package_identity_observed") is True and
             value.get("original_b03_failure_preserved") is True and value.get("prior_sources_unchanged") is True and
             value.get("original_permission_gate_modified") is False and value.get("new_scope_published") is False and
             value.get("new_signature_verification_performed") is False and value.get("vendor_artifact_source_trust") == "UNKNOWN" and
             all(row.get("command", {}).get("complete") is True and row["command"].get("joined") is True and
                 row["command"].get("returncode") == 0 and row["command"].get("errors") == [] and
                 row["command"].get("termination_attempted") is False for row in value["native_commands"]),
             "FULL_NATIVE46_DISCOVERY_AND_UNPROMOTED_SCOPE_REQUIRED")
'''
    owned = once(owned, anchor, extra_gate + anchor)
    compile(owned, "owned_readonly_lifetime.py", "exec")
    owned_pin = save("owned_readonly_lifetime.py", owned.encode())
    diff("owned-against-actual-r4.diff", old_owned, owned)

    names = ["owned_readonly_lifetime.py", "observe_native46.py", "readonly_services_transport.py",
             "request.review-only.json", *("inputs/" + name + ".json" for name in INPUTS)]
    files = [{"name": name, "bytes": len((ROOT / name).read_bytes()), "sha256": sha((ROOT / name).read_bytes())} for name in names]
    old_stage = sources["stage_and_run_services.py"]
    stage = assign(assign(old_stage, "ROOT", STAGE), "FILES", files)
    stage = stage.replace("pocket4-current-readonly-services-source-stage-v4", "pocket4-native46-discovery-source-stage-v1")
    stage = stage.replace("pocket4-current-readonly-services-source-stage-result-v4", "pocket4-native46-discovery-source-stage-result-v1")
    stage = once(stage, '"""New exact source/input stage, then five fixed read-only PackageManager queries."""',
                 '"""Independent native46 discovery; six fixed read-only PM queries, no scope promotion."""')
    compile(stage, "stage_discovery_once.py", "exec")
    stage_pin = save("stage_discovery_once.py", stage.encode())
    diff("stager-against-actual-r4.diff", old_stage, stage)
    payload = canonical({"schema": "pocket4-native46-discovery-source-stage-v1",
                         "files": [{"name": name, "text": (ROOT / name).read_bytes().decode()} for name in names]})
    need(len(payload) <= 262144, "ORIGINAL_STAGE_INPUT_LIMIT")
    payload_pin = save("stage.stdin.original.json", payload)
    process = {"host": "pocket4", "executable": "/usr/bin/sudo", "args": ["-n", "/usr/bin/python3", "-I", "-B", "-c", stage],
               "stdin": payload.decode(), "cwd": "/", "timeout_seconds": 1100, "cpu_quota_percent": 100,
               "memory_max_bytes": 1073741824, "nice": 10,
               "idempotency_key": "pocket4-native46-new-package-discovery-20261106-r1"}
    process_pin = save("process-request.review-only.json", canonical(process))
    inheritance = {"schema": "pocket4-native46-source-inheritance-v1", "device_execution": False,
                   "references": REFERENCE, "definitions": {}}
    for label, old, new, names in (
        ("worker", old_worker, worker, ("need", "sha", "canonical", "parse", "read_root_pin", "load_source", "bounded_file",
          "verify_shared_helper", "same_epoch_identity", "selected_environment", "main_classpaths", "safe_error",
          "held_bounded_child", "write_empty_raw_stream", "remember_child_streams", "parse_packages", "component",
          "parse_resolver", "compare_catalogs")),
        ("transport", old_transport, transport, tuple(n.name for n in ast.parse(old_transport).body if isinstance(n, (ast.FunctionDef, ast.ClassDef)))),
        ("owned", old_owned, owned, ("need", "canonical", "pin_bytes", "load", "enter", "decode_worker", "retired", "child", "combined", "publish", "main")),
        ("stage", old_stage, stage, ("need", "sha", "canonical", "read_file", "read_host_pin", "write_new")),
    ):
        rows = {}
        for name in names:
            before, after = function(old, name), function(new, name)
            need(before == after, "UNCHANGED_INHERITED_DEFINITION: " + label + "/" + name)
            rows[name] = {"bytes": len(after.encode()), "sha256": sha(after.encode()), "unchanged": True}
        inheritance["definitions"][label] = rows
    save("SOURCE_INHERITANCE.json", canonical(inheritance))
    print(canonical({"status": "LOCAL_CANDIDATE_ONLY_NOT_EXECUTED", "worker": worker_pin, "transport": transport_pin,
                     "owned": owned_pin, "stage": stage_pin, "payload": payload_pin, "process": process_pin}).decode(), end="")


if __name__ == "__main__":
    main()
