#!/usr/bin/env python3
"""Local-only deterministic derivation from actual frozen scope/discovery sources."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
OLD = PROJECT / "successor_audit_requests/explicit47_scope_r2"
DISC = PROJECT / "successor_audit_requests/native46_discovery_r1"
STAGE = "/home/alex/work/pocket4-explicit-48-scope-source-20261106-r1"
OUTPUT = "/home/alex/work/pocket4-current-explicit-48-app-observation-20261106-r1"


def need(value, why):
    if not value:
        raise RuntimeError(why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path, size, digest):
    raw = path.read_bytes()
    need(len(raw) == size and sha(raw) == digest, "FROZEN_INPUT_CHANGED:" + str(path))
    return raw


def data(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")


def put(name, raw):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)
    return {"path": STAGE + "/" + name, "bytes": len(raw), "sha256": sha(raw)}


def replace_once(source, old, new):
    need(source.count(old) == 1, "UNIQUE_SOURCE_REPLACEMENT_REQUIRED:" + old[:100])
    return source.replace(old, new, 1)


def replace_definition(source, name, replacement):
    node = next(row for row in ast.parse(source).body if isinstance(row, ast.FunctionDef) and row.name == name)
    lines = source.splitlines(True)
    return "".join(lines[:node.lineno - 1]) + replacement.rstrip() + "\n" + "".join(lines[node.end_lineno:])


VALIDATE_INPUTS = r'''
def validate_inputs(artifact_raw, outer_raw, terminal_raw, validator):
    artifact, terminal = parse(artifact_raw), parse(terminal_raw)
    need(len(outer_raw.splitlines()) == 2, "EXACT_TWO_LINE_DISCOVERY_STAGE_AND_JOINT")
    staged, outer = [parse(line) for line in outer_raw.splitlines()]
    need(terminal.get("job_id") == DISCOVERY_JOB and terminal.get("state") == "succeeded" and
         type(terminal.get("exit_code")) is int and terminal["exit_code"] == 0,
         "ACTUAL_DISCOVERY_SUCCESSFUL_TERMINAL_REQUIRED")
    need(all(terminal.get(key) is True for key in ("output_complete", "output_durable", "terminal_publication_confirmed")) and
         all(terminal.get(key) is False for key in ("automatic_retry", "timed_out", "cancelled")), "DISCOVERY_NOT_DURABLY_SETTLED")
    need(terminal.get("log_truncated") == {"stdout": False, "stderr": False} and
         terminal.get("log_errors") == {"stdout": None, "stderr": None} and
         terminal.get("log_synced") == {"stdout": True, "stderr": True} and
         terminal.get("log_bytes") == {"stdout": {"seen": len(outer_raw), "stored": len(outer_raw)},
                                      "stderr": {"seen": 0, "stored": 0}}, "DISCOVERY_COMPLETE_ORIGINAL_STREAMS_REQUIRED")
    need(staged.get("schema") == "pocket4-native46-discovery-source-stage-result-v1" and staged.get("source_stage_ok") is True and
         staged.get("source_root") == DISCOVERY_STAGE and staged.get("automatic_retry") is False and
         staged.get("bootstrap_FDs_before") == staged.get("bootstrap_FDs_after") and
         all(type(staged.get(key)) is int and staged[key] == 0 for key in
             ("stage_Main_reads", "stage_UI_actions", "stage_installs", "stage_namespace_entries")), "EXACT_DISCOVERY_STAGE_REQUIRED")
    need(validator.CONFIG["kind"] == "services" and validator.CONFIG["stage_root"] == DISCOVERY_STAGE,
         "ACTUAL_DISCOVERY_VALIDATOR_CONFIGURATION")
    source_rows = staged.get("files")
    need(type(source_rows) is list and len(source_rows) == 7 and len({row["name"] for row in source_rows}) == 7,
         "DISCOVERY_STAGE_SOURCE_CLOSURE")
    source_by_name = {row["name"]: row for row in source_rows}
    for reference in (DISCOVERY_VALIDATOR, validator.CONFIG["worker"], validator.CONFIG["request"]):
        name = reference["path"].removeprefix(DISCOVERY_STAGE + "/")
        need(source_by_name.get(name) == {"name": name, "bytes": reference["bytes"], "sha256": reference["sha256"]},
             "DISCOVERY_STAGE_ACTUAL_SOURCE_PIN_MISMATCH")
    need(outer.get("schema") == "pocket4-owned-readonly-observation-result-v1" and outer.get("ok") is True and
         outer.get("status") == "READONLY_OBSERVATION_AND_OWNED_LIFETIME_VERIFIED" and outer.get("kind") == "services" and
         outer.get("errors") == [] and outer.get("automatic_retry") is False and outer.get("production_ready") is False and
         outer.get("inner_result_alone_qualifies") is False and outer.get("old_results_reclassified") is False and
         outer.get("library_FD_retired_by_original_held_owned_child_exit") is True and
         all(type(outer.get(key)) is int and outer[key] == 0 for key in ("UI_actions", "installs", "permission_changes")),
         "DISCOVERY_OWNED_OUTER_GATE_FAILED")
    child = outer["child_result"]
    need(validator.combined(outer["child_lifecycle"], child, b""), "DISCOVERY_OWNED_CHILD_DID_NOT_RETIRE_NORMALLY")
    need(outer["child_stderr"]["bytes"] == 0 and outer["child_stderr"]["sha256"] == sha(b"") and
         child.get("worker_invoked") is True and child.get("manual_library_FD_close") is False and
         type(child.get("unknown_FDs_closed")) is int and child["unknown_FDs_closed"] == 0 and
         child.get("production_ready") is False and child.get("result_requires_parent_pidfd_retirement") is True and
         child["frozen_descriptors_before_worker"] == child["frozen_descriptors_after_worker"] == child["final_descriptors"],
         "DISCOVERY_EXACT_FD_AND_LIBRARY_LIFETIME_REQUIRED")
    worker_raw = child["worker_stdout_original"].encode("utf-8")
    need(len(worker_raw) == child["worker_stdout_bytes"] == outer["worker_stdout"]["bytes"] and
         sha(worker_raw) == child["worker_stdout_sha256"] == outer["worker_stdout"]["sha256"],
         "DISCOVERY_ORIGINAL_WORKER_STREAM_PIN")
    envelope = parse(worker_raw)
    need(envelope["artifact_bytes"] == len(artifact_raw) == DISCOVERY["bytes"] and
         envelope["artifact_sha256"] == sha(artifact_raw) == DISCOVERY["sha256"], "DISCOVERY_COMPLETE_ARTIFACT_PIN")
    need(validator.decode_worker(worker_raw) == artifact, "DISCOVERY_DECODED_ARTIFACT_DIFFERS")
    validator.worker_gate(artifact, child["worker_returncode"])
    need(artifact["app_scope_reference"] == PARENT and artifact["packages"] == ORIGINAL_PACKAGES and
         artifact["scope_guard_before"] == artifact["scope_guard_after"] and
         artifact["scope_guard_before"]["app_scope_sha256"] == PARENT["sha256"], "EXACT_ORIGINAL_47_PROTECTION_REQUIRED")
    proposed = artifact["proposed_immutable_scope_review"]
    need(proposed["original_scope_reference"] == PARENT and proposed["original_packages"] == ORIGINAL_PACKAGES and
         proposed["additional_package"] == NEW_PACKAGE and proposed["proposed_packages"] == PACKAGES and
         proposed["proposed_count"] == 48 and proposed["new_identity_reference"] == NEW_IDENTITY and
         proposed["new_scope_published"] is False and proposed["new_runtime_or_UI_authority"] is False,
         "EXACT_NEW_48_SET_MUST_HAVE_ACTUAL_DISCOVERY")
    identity = artifact["new_package_identity"]
    need(identity["package"] == NEW_PACKAGE and type(identity["uid"]) is int and identity["uid"] == 10162 and
         type(identity["version_code"]) is int and identity["version_code"] == 0 and
         identity["fresh_signature_verification"] is False and
         identity["package_manager_certificate_sha256"] == [NEW_PM_CERT] and len(identity["apks"]) == 1 and
         identity["apks"][0]["bytes"] == 1397258 and identity["apks"][0]["sha256"] == NEW_APK_SHA,
         "ACTUAL_DISCOVERED_NDK_IDENTITY_REQUIRED")
    identity_raw = canonical(identity) + b"\n"
    need(len(identity_raw) == NEW_IDENTITY["bytes"] and sha(identity_raw) == NEW_IDENTITY["sha256"] and
         artifact["new_package_identity_receipt"] == NEW_IDENTITY, "ACTUAL_NEW_IDENTITY_RECEIPT_REQUIRED")
    rows = artifact["MAIN_LAUNCHER_components"]
    need(len(rows) == 46 and len({row["component"] for row in rows}) == 46 and
         {row["package"] for row in rows} == set(LAUNCHERS) | {NEW_PACKAGE} and
         [row["component"] for row in rows if row["package"] == NEW_PACKAGE] == [NEW_COMPONENT],
         "COMPLETE_ACTUAL_46_RESOLVER_REFERENCE_REQUIRED")
    need(artifact["native_before"] == artifact["native_after"] and artifact["native_before"].get("ok") is True and
         artifact["native_before"].get("state") == "running", "DISCOVERY_NATIVE_OWNER_NOT_STABLE")
    return artifact, identity


def validate_projection(scope, parent_scope, identity):
    need(parent_scope["schema"] == "pocket4-versioned-app-scope-v1" and parent_scope["runtime_epoch_sha256"] == EPOCH and
         sorted(parent_scope["apps"]) == ORIGINAL_PACKAGES, "EXACT_SAME_EPOCH_PARENT_47_REQUIRED")
    need(scope["schema"] == "pocket4-versioned-app-scope-v1" and scope["runtime_epoch_sha256"] == EPOCH and
         sorted(scope["apps"]) == PACKAGES and scope["parent_app_scope"] == PARENT,
         "ACTUAL_SCOPE_NOT_EXACT_48")
    need(scope["fresh_signature_verification_performed"] is False and scope["UI_or_install_runtime_admitted"] is False and
         scope["external_evidence_policy_validated_by_this_reader"] is False,
         "IDENTITY_SCOPE_MUST_NOT_PROMOTE_SIGNATURE_OR_RUNTIME_AUTHORITY")
    need(all(scope["apps"][name] == expected for name, expected in parent_scope["apps"].items()),
         "ORIGINAL_47_APP_IDENTITY_CHANGED")
    need(scope["apps"][NEW_PACKAGE] == identity, "NDK_UID_APK_SIGNER_PM_DATA_OR_FILE_IDENTITY_CHANGED")
'''

VALIDATE_REQUEST = r'''
def validate_request(request):
    need(set(request) == {"schema", "guard", "reader", "parent_app_scope", "discovery_artifact", "discovery_outer",
                          "discovery_terminal", "discovery_validator", "new_identity", "packages", "output_root", "worker"},
         "CLOSED_EXPLICIT_SCOPE_REQUEST")
    need(request["schema"] == "pocket4-explicit-48-app-scope-request-v1" and request["guard"] == GUARD and
         request["reader"] == READER and request["parent_app_scope"] == PARENT and request["discovery_artifact"] == DISCOVERY and
         request["discovery_outer"] == DISCOVERY_OUTER and request["discovery_terminal"] == DISCOVERY_TERMINAL and
         request["discovery_validator"] == DISCOVERY_VALIDATOR and request["new_identity"] == NEW_IDENTITY and
         request["packages"] == PACKAGES and len(PACKAGES) == len(set(PACKAGES)) == 48 and
         len(ORIGINAL_PACKAGES) == 47 and set(PACKAGES) - set(ORIGINAL_PACKAGES) == {NEW_PACKAGE} and
         request["output_root"] == OUTPUT, "EXACT_EXPLICIT_48_SCOPE_REQUIRED")
    need(request["worker"]["path"] == STAGE + "/observe_explicit_48.py", "EXACT_SELF_SOURCE_PATH")
'''


def main():
    old_worker = pin(OLD / "observe_explicit_47.py", 18139, "56922fbe372cf8cd2d0e39f75ddb69b16843f098d8090d65834b5737db04a656").decode()
    old_owned = pin(OLD / "owned_readonly_lifetime.py", 16637, "1b6bca427c4a01cd1a5a8ea2526f9223e884658ef3a1784f3a8fad885f004ecc").decode()
    old_stage = pin(OLD / "stage_and_run_explicit47_r2.py", 7043, "80b8f696cddbbcbf27a08134eb790bef98bb8d808337dc460e2ca2c945fc1961").decode()
    pin(DISC / "owned_readonly_lifetime.py", 20365, "c121e6eea1b5162048cbb40207aaef2861be527fed554e8bc5c44d3229524cc0")
    artifact = pin(DISC / "actual/artifact.original.json", 112546, "69482778466e03dceff2defc85fb8f68880c360a3f112e129561a8fd5e6e5400")
    outer = pin(DISC / "actual/stdout.original.jsonl", 31226, "474893612abaf6192653b31d16adb808a2d46e92cf6e1683760e532684d5fe5d")
    terminal = pin(DISC / "actual/status-01.original.json", 733, "f16d1da55f8afa0da6f91f37186fff39dc50ba12a22e54b048290e723dc797bd")
    parent = pin(OLD / "actual-readback/app-scope.private.json", 58854, "44f9ce783000a672c270e98afdaeb74bd79654508bfacae6793316ff4252e52f")
    prior = json.loads(parent)
    actual = json.loads(artifact)
    original_packages = sorted(prior["apps"])
    packages = sorted(original_packages + ["com.example.ndk_tests"])
    need(len(original_packages) == 47 and len(packages) == 48 and
         packages == actual["proposed_immutable_scope_review"]["proposed_packages"], "ACTUAL_EXACT_48_PROPOSAL")
    refs = {
        "DISCOVERY": put("inputs/discovery-artifact.original.json", artifact),
        "DISCOVERY_OUTER": put("inputs/discovery-stdout.original.jsonl", outer),
        "DISCOVERY_TERMINAL": put("inputs/discovery-terminal.original.json", terminal),
        "DISCOVERY_VALIDATOR": {"path": "/home/alex/work/pocket4-native46-discovery-source-20261106-r1/owned_readonly_lifetime.py", "bytes": 20365,
                                "sha256": "c121e6eea1b5162048cbb40207aaef2861be527fed554e8bc5c44d3229524cc0"},
        "NEW_IDENTITY": actual["new_package_identity_receipt"],
    }
    source = old_worker.replace('"""Fresh explicit 47-package host observation; no Android command or UI."""',
                                '"""Fresh explicit 48-package identity scope; no command, signature promotion or UI."""', 1)
    source = replace_once(source, 'STAGE = "/home/alex/work/pocket4-explicit-47-scope-source-20261106-r2"', "STAGE = " + repr(STAGE))
    source = replace_once(source, 'OUTPUT = "/home/alex/work/pocket4-current-explicit-47-app-observation-20261106-r2"', "OUTPUT = " + repr(OUTPUT))
    begin = source.index("PARENT = "); end = source.index("ACTIONS = ", begin)
    constants = {"PARENT": actual["app_scope_reference"], **refs,
        "DISCOVERY_JOB": "1a1b307f521-fc05-807a", "DISCOVERY_STAGE": "/home/alex/work/pocket4-native46-discovery-source-20261106-r1",
        "NEW_PACKAGE": "com.example.ndk_tests", "NEW_COMPONENT": "com.example.ndk_tests/com.example.ndk_tests.NdkTestsActivity",
        "NEW_APK_SHA": "b3bf438dedbcdd5f3ac871733a273b3cece446db6be308df73f95b08cb46d164",
        "NEW_PM_CERT": "a899ddfa8c4b57a962c2bb1ae885a44bd904d7b63f6fd301abf514edf70ad72c",
        "HELPER": "org.droidloom.qa.successor.p8f89f253350ba2fa.r1"}
    source = source[:begin] + "".join(name + " = " + repr(value) + "\n" for name, value in constants.items()) + source[end:]
    source = replace_once(source, "PACKAGES = sorted((*LAUNCHERS, ACTIONS, HELPER))",
                          "ORIGINAL_PACKAGES = sorted((*LAUNCHERS, ACTIONS, HELPER))\nPACKAGES = sorted((*ORIGINAL_PACKAGES, NEW_PACKAGE))")
    source = replace_definition(source, "validate_inputs", VALIDATE_INPUTS)
    source = replace_definition(source, "validate_request", VALIDATE_REQUEST)
    source = source.replace('"pocket4-explicit-47-app-scope-observation-v1"', '"pocket4-explicit-48-app-scope-observation-v1"')
    source = replace_once(source, '"native_catalog_reference_only": True,',
                          '"native46_resolver_and_discovery_reference_only": True, "new_signature_verification_performed": False,\n'
                          '              "vendor_artifact_source_trust": "UNKNOWN", "original_47_scope_modified": False,\n'
                          '              "original_permission_gate_modified": False, "original_b03_failure_reclassified": False,')
    begin = source.index('    catalog_raw, install_raw, terminal_raw = '); end = source.index('    core = guard._core()', begin)
    source = source[:begin] + '''    artifact_raw, outer_raw, terminal_raw = (read_root_pin(pin) for pin in (DISCOVERY, DISCOVERY_OUTER, DISCOVERY_TERMINAL))
    validator = load_source(DISCOVERY_VALIDATOR, "actual_native46_pure_joint_validator")
    discovery, new_identity = validate_inputs(artifact_raw, outer_raw, terminal_raw, validator)
    need(parse(read_root_pin(NEW_IDENTITY)) == new_identity, "ORIGINAL_DISCOVERED_IDENTITY_BYTES_CHANGED")
    guard = load_source(GUARD, "explicit48_actual_runtime_guard")
    reader = load_source(READER, "explicit48_original_observer")
''' + source[end:]
    begin = source.index('        baseline = guard.current_baseline()'); end = source.index('        observer_request = ', begin)
    source = source[:begin] + '''        need(before == discovery["guard_before"], "RUNTIME_MUST_MATCH_ACTUAL_DISCOVERY")
        baseline = guard.current_baseline()
        need(discovery["native_before"]["host_pid"] == baseline["runtime"]["held"]["process_snapshot"]["binding"]["processes"]["launcher"]["host_pid"],
             "DISCOVERY_NATIVE_OWNER_DIFFERS_FROM_CURRENT_BASELINE")
        parent_scope = core.parse(core.pinned_record(PARENT))
        need(parent_scope["schema"] == "pocket4-versioned-app-scope-v1" and parent_scope["runtime_epoch_sha256"] == EPOCH and
             sorted(parent_scope["apps"]) == ORIGINAL_PACKAGES, "EXACT_SAME_EPOCH_PARENT_47_REQUIRED")
        parent_guard_before = guard.check_app_scope(PARENT, ORIGINAL_PACKAGES)
''' + source[end:]
    source = replace_once(source, '"install_or_signature_evidence": [INSTALL, TERMINAL, CATALOG],',
                          '"install_or_signature_evidence": [DISCOVERY, DISCOVERY_OUTER, DISCOVERY_TERMINAL, NEW_IDENTITY],')
    begin = source.index('        need(scope["runtime_epoch_sha256"] == EPOCH'); end = source.index('        after = guard.current_guard()', begin)
    source = source[:begin] + '''        validate_projection(scope, parent_scope, new_identity)
        parent_guard_after = guard.check_app_scope(PARENT, ORIGINAL_PACKAGES)
        need(parent_guard_before == parent_guard_after, "ORIGINAL_47_PROTECTION_CHANGED")
        need(observation["app_scope_guard"]["packages"] == PACKAGES and
             observation["app_scope_guard"]["current_apk_paths_and_file_identities_match"] is True and
             observation["app_scope_guard"]["UI_or_install_runtime_admitted"] is False and
             observation["app_scope_guard"]["new_signature_verification_performed"] is False,
             "NEW_SCOPE_IS_IDENTITY_ONLY")
''' + source[end:]
    source = replace_once(source, 'for pin in (GUARD, READER, CATALOG, INSTALL, TERMINAL, request["worker"]):',
                          'for pin in (GUARD, READER, DISCOVERY, DISCOVERY_OUTER, DISCOVERY_TERMINAL, DISCOVERY_VALIDATOR, NEW_IDENTITY, request["worker"]):')
    source = replace_once(source, 'result.update(ok=True, status="EXPLICIT_47_PACKAGE_SCOPE_OBSERVED", guard_before=before, guard_after=after,\n'
                          '                      observation=observation, original_46_unchanged=True, new_helper_matches_actual_install=True,\n'
                          '                      package_count=47,',
                          'result.update(ok=True, status="EXPLICIT_48_PACKAGE_IDENTITY_SCOPE_OBSERVED", guard_before=before, guard_after=after,\n'
                          '                      observation=observation, original_47_unchanged=True, new_package_matches_actual_discovery=True,\n'
                          '                      parent_scope_guard_before=parent_guard_before, parent_scope_guard_after=parent_guard_after,\n'
                          '                      discovery_joint_validated=True, discovery_job_id=DISCOVERY_JOB,\n'
                          '                      discovery_inputs=[DISCOVERY, DISCOVERY_OUTER, DISCOVERY_TERMINAL], new_identity_reference=NEW_IDENTITY,\n'
                          '                      scope_requires_outer_owned_lifetime_and_durable_terminal=True, package_count=48,')
    source = source.replace('"pocket4-explicit-47-scope-entry-rejection-v1"', '"pocket4-explicit-48-scope-entry-rejection-v1"')
    compile(source, "observe_explicit_48.py", "exec")
    worker_pin = put("observe_explicit_48.py", source.encode())
    scope = {}
    exec(compile(source, "local_unexecuted_candidate", "exec"), scope)
    request = {"schema": "pocket4-explicit-48-app-scope-request-v1", "guard": scope["GUARD"], "reader": scope["READER"],
               "parent_app_scope": scope["PARENT"], "discovery_artifact": refs["DISCOVERY"], "discovery_outer": refs["DISCOVERY_OUTER"],
               "discovery_terminal": refs["DISCOVERY_TERMINAL"], "discovery_validator": refs["DISCOVERY_VALIDATOR"],
               "new_identity": refs["NEW_IDENTITY"], "packages": packages, "output_root": OUTPUT, "worker": worker_pin}
    scope["validate_request"](request)
    request_pin = put("request.review-only.json", data(request))
    owned = old_owned
    config = {"schema": "pocket4-owned-readonly-observation-config-v1", "kind": "explicit48", "stage_root": STAGE,
              "worker": worker_pin, "request": request_pin,
              "prior_unexecuted_source": {"bytes": 18139, "sha256": "6ca6c99c773e8646b50d568c95620b4731b337c3ec21f1d3efa00cbb617c93da", "preserved": True}}
    line = next(line for line in owned.splitlines() if line.startswith("CONFIG = "))
    owned = replace_once(owned, line, "CONFIG = " + repr(config))
    owned = owned.replace('("explicit47", "calendar")', '("explicit48", "calendar")')
    owned = owned.replace('CONFIG["kind"] == "explicit47"', 'CONFIG["kind"] == "explicit48"')
    owned = owned.replace('"pocket4-explicit-47-app-scope-observation-v1"', '"pocket4-explicit-48-app-scope-observation-v1"')
    owned = owned.replace('"EXPLICIT_47_PACKAGE_SCOPE_OBSERVED"', '"EXPLICIT_48_PACKAGE_IDENTITY_SCOPE_OBSERVED"')
    owned = owned.replace('value.get("package_count") == 47', 'value.get("package_count") == 48')
    owned = owned.replace('value.get("original_46_unchanged")', 'value.get("original_47_unchanged")')
    owned = owned.replace('value.get("new_helper_matches_actual_install")', 'value.get("new_package_matches_actual_discovery")')
    owned = owned.replace('"EXPLICIT47_OBSERVATION_GATE_FAILED"', '"EXPLICIT48_OBSERVATION_GATE_FAILED"')
    owned = replace_once(owned, '        actions = ("Main_UI_actions",',
                          '        need(value.get("discovery_joint_validated") is True and value.get("new_signature_verification_performed") is False and\n'
                          '             value.get("vendor_artifact_source_trust") == "UNKNOWN" and value.get("original_47_scope_modified") is False and\n'
                          '             value.get("original_permission_gate_modified") is False and value.get("original_b03_failure_reclassified") is False and\n'
                          '             value.get("scope_requires_outer_owned_lifetime_and_durable_terminal") is True and\n'
                          '             value.get("parent_scope_guard_before") == value.get("parent_scope_guard_after"),\n'
                          '             "IDENTITY_ONLY_SCOPE_WITH_ORIGINAL_FAILURE_PRESERVED")\n'
                          '        actions = ("Main_UI_actions",')
    compile(owned, "owned_readonly_lifetime.py", "exec")
    owned_pin = put("owned_readonly_lifetime.py", owned.encode())
    names = ["owned_readonly_lifetime.py", "observe_explicit_48.py", "request.review-only.json",
             "inputs/discovery-artifact.original.json", "inputs/discovery-stdout.original.jsonl", "inputs/discovery-terminal.original.json"]
    files = [{"name": name, "bytes": len((HERE / name).read_bytes()), "sha256": sha((HERE / name).read_bytes())} for name in names]
    stager = old_stage
    stager = replace_once(stager, next(line for line in stager.splitlines() if line.startswith("ROOT=")), "ROOT=" + repr(STAGE))
    stager = replace_once(stager, next(line for line in stager.splitlines() if line.startswith("FILES=")), "FILES=" + repr(files))
    stager = stager.replace("one explicit 47-package read-only observation", "one explicit 48-package identity observation")
    stager = stager.replace("pocket4-explicit47-owned-scope-source-stage-v2", "pocket4-explicit48-owned-scope-source-stage-v1")
    stager = stager.replace("pocket4-explicit47-owned-scope-source-stage-result-v2", "pocket4-explicit48-owned-scope-source-stage-result-v1")
    compile(stager, "stage_and_run_explicit48_r1.py", "exec")
    stager_pin = put("stage_and_run_explicit48_r1.py", stager.encode())
    payload = {"schema": "pocket4-explicit48-owned-scope-source-stage-v1", "files": [
        {"name": name, "text": (HERE / name).read_text()} for name in names]}
    stdin = data(payload)
    need(len(stdin) <= 262144, "ORIGINAL_STAGE_INPUT_CAP_PRESERVED")
    stdin_pin = put("stage.stdin.original.json", stdin)
    packet = {"host": "pocket4", "executable": "/usr/bin/sudo", "args": ["-n", "/usr/bin/python3", "-I", "-B", "-c", stager],
              "cwd": "/home/alex/work", "stdin": stdin.decode("ascii"),
              "idempotency_key": "app-history-20261106-explicit48-current-app-scope-r1",
              "timeout_seconds": 1100, "memory_max_bytes": 1073741824, "cpu_quota_percent": 100, "nice": 10}
    packet_pin = put("process-request.review-only.json", data(packet))
    for filename, before, after in [("worker-against-actual-explicit47.diff", old_worker, source),
                                    ("owned-against-actual-explicit47.diff", old_owned, owned),
                                    ("stager-against-actual-explicit47.diff", old_stage, stager)]:
        put(filename, "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
            fromfile="actual-explicit47-r2", tofile="candidate-explicit48-r1")).encode())
    proof = {"schema": "pocket4-explicit48-source-inheritance-v1", "no_remote_execution": True,
             "worker_unchanged_definitions": [], "owned_unchanged_definitions": [], "stager_unchanged_definitions": []}
    for label, before, after, names in [
        ("worker", old_worker, source, ["need", "sha", "canonical", "parse", "read_root_pin", "load_source"]),
        ("owned", old_owned, owned, ["need", "canonical", "pin_bytes", "load", "decode_worker", "retired", "child", "combined", "publish", "main"]),
        ("stager", old_stage, stager, ["need", "sha", "canonical", "read_file", "read_host_pin", "write_new"])]:
        def defs(text):
            lines = text.splitlines(True)
            return {n.name: "".join(lines[n.lineno - 1:n.end_lineno]).encode() for n in ast.parse(text).body if isinstance(n, ast.FunctionDef)}
        b, a = defs(before), defs(after)
        for name in names:
            need(b[name] == a[name], "FROZEN_DEFINITION_CHANGED:" + label + ":" + name)
            proof[label + "_unchanged_definitions"].append({"name": name, "bytes": len(a[name]), "sha256": sha(a[name])})
    proof.update(unchanged_scope_reader={"bytes": 7695, "sha256": "0a61313f518c7308f65f2654254689120df940cb0f5bd95d8873a42d6979914d"},
                 unchanged_original_discovery_validator=refs["DISCOVERY_VALIDATOR"], stage_files=files,
                 worker=worker_pin, owned=owned_pin, stager=stager_pin, stdin=stdin_pin, process_request=packet_pin)
    put("INHERITANCE.json", data(proof))
    print(json.dumps({"local_candidate_written": True, "worker": worker_pin, "owned": owned_pin,
                      "stager": stager_pin, "stdin": stdin_pin, "packet": packet_pin, "remote_executed": False}, sort_keys=True))


if __name__ == "__main__":
    main()
