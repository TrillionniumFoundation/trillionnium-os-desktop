#!/usr/bin/env python3
"""Local assembler; requires the actual complete read-back of the admitted 48 scope."""
import argparse
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent.parent
BASE = PROJECT / "successor_audit_requests/revisions/b13-fixture-version-repair-r1"
S48 = PROJECT / "successor_audit_requests/explicit48_scope_r1"
STAGE = "/home/alex/work/pocket4-ndk-current-apk-audit-source-20261106-r1"
OUTPUT = "/home/alex/work/pocket4-ndk-current-apk-audit-20261106-r1"


def need(value, why):
    if not value:
        raise RuntimeError(why)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pinned(path, size, digest):
    raw = path.read_bytes()
    need(len(raw) == size and sha(raw) == digest, "EXACT_LOCAL_INPUT:" + str(path))
    return raw


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode()


def put(name, raw):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(raw)
    return {"path": STAGE + "/" + name, "bytes": len(raw), "sha256": sha(raw)}


def replace_once(source, old, new):
    need(source.count(old) == 1, "UNIQUE_REPLACEMENT:" + old[:100])
    return source.replace(old, new, 1)


def definitions(source):
    lines = source.splitlines(True)
    return {node.name: "".join(lines[node.lineno - 1:node.end_lineno]) for node in ast.parse(source).body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))}


def literal_constant(node):
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        left, right = literal_constant(node.left), literal_constant(node.right)
        need(type(left) is int and type(right) is int, "INTEGER_BYTE_LIMIT_EXPRESSION_ONLY")
        return left * right
    return ast.literal_eval(node)


OWNED_GATE = r'''
def worker_gate(value, returned):
    need(returned == 0 and value.get("schema") == "pocket4-independent-ndk-apk-signature-metadata-v1" and
         value.get("status") == "NDK_CURRENT_APK_SIGNATURE_AND_METADATA_VERIFIED" and
         value.get("ndk_audit_complete") is True and value.get("errors") == [] and
         value.get("automatic_retry") is False and value.get("production_ready") is False and
         value.get("process_FDs_before") == value.get("process_FDs_after"), "NDK_COMPLETE_WORKER_GATE")
    guard = value.get("guard_before", {})
    need(guard.get("schema") == "pocket4-successor-main-guard-v1" and
         guard.get("runtime_epoch_sha256") == "a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9" and
         value.get("guard_after") == guard and retired(value.get("owned_descriptors_final")), "NDK_RUNTIME_AND_FD_GATE")
    need(value.get("packages") == ["com.example.ndk_tests"] and len(value.get("protected_packages", [])) == 48 and
         value.get("scope_guard_before") == value.get("scope_guard_after") and
         value["scope_guard_before"].get("packages") == value["protected_packages"] and
         value["scope_guard_before"].get("app_scope_sha256") == "b184299ce0a39a998752ed980a43192b396099f780bcf60bcfe53d0edf92ffe4" and
         value.get("scope_qualification", {}).get("normal_owned_joint_validated") is True and
         value["scope_qualification"].get("scope_is_signature_evidence") is False,
         "EXACT_48_PROTECTION_WITH_INDEPENDENT_NEW_SIGNATURE")
    fields = ("snapshot_consistent", "all_commands_succeeded", "all_primary_commands_succeeded",
              "all_manifests_and_signatures_verified", "all_tool_children_joined", "official_badging_stderr_empty",
              "official_layout_descriptors_closed", "official_layout_before_and_after_all_commands", "action_lock_released")
    need(all(value.get(key) is True for key in fields) and value.get("unjoined_tool_pids") == [] and
         len(value.get("commands", [])) == 3 and len(value.get("apps", [])) == 1,
         "NDK_THREE_ORDINARY_TOOLS_AND_COMPLETE_RESOURCE_RETIREMENT")
    app = value["apps"][0]
    need(app.get("package") == "com.example.ndk_tests" and app.get("uid") == 10162 and app.get("PM_version_code") == 0 and
         len(app.get("apks", [])) == 1 and app["apks"][0].get("bytes") == 1397258 and
         app["apks"][0].get("sha256") == "b3bf438dedbcdd5f3ac871733a273b3cece446db6be308df73f95b08cb46d164" and
         app["apks"][0].get("held_bytes_and_full_stat_and_path_unchanged") is True and
         app["apks"][0].get("parse_errors") == [] and
         all(app.get(key) is True for key in ("complete_APK_set_observed", "one_base_manifest_observed",
             "all_APKs_signature_verified", "all_current_signers_equal_PM_records",
             "all_manifests_match_PM_identity", "all_permission_names_decoded")), "NDK_APK_AND_METADATA_COMPLETE")
    signature = app["apks"][0]["signature"]
    need(signature.get("cryptographic_verification_performed") is True and signature.get("verified") is True and
         signature.get("API_minimum_override_used") is False and signature.get("integrity_check_bypassed") is False and
         signature.get("signer_certificate_sha256") == ["a899ddfa8c4b57a962c2bb1ae885a44bd904d7b63f6fd301abf514edf70ad72c"],
         "NDK_NORMAL_SIGNATURE_NOT_API_OVERRIDE")
    need([row.get("name") for row in value["commands"]] == ["apksigner", "badging", "manifest"] and
         all(row.get("returncode") == 0 and row.get("joined") is True and row.get("pipes_closed") is True and
             row.get("output_capture_complete") is True and row.get("timed_out") is False and
             row.get("own_group_kill_requested") is False and not row.get("error") and not row.get("retirement_error")
             for row in value["commands"]), "THREE_NORMAL_UNSIGNALLED_TOOL_EXITS_REQUIRED")
    layout = value.get("official_private_layout", {})
    need(layout.get("encoding") == "zlib-base64" and layout.get("observation_count") == 8 and
         layout.get("all_observations_complete") is True and layout.get("full_original_observations_persisted_and_read_back") is True and
         layout.get("owned_directory_descriptors", {}).get("acquired") == 11 and
         layout["owned_directory_descriptors"].get("closed") == 11 and layout["owned_directory_descriptors"].get("errors") == [],
         "COMPLETE_ACTUAL_OFFICIAL_TOOL_LAYOUT_EVIDENCE")
    need(value.get("vendor_artifact_source_trust") == "UNKNOWN" and value.get("original_failures_reclassified") is False and
         value.get("old_ledger_modified") is False and value.get("UI_or_install_admitted") is False and
         value.get("effective_permission_grants") == "UNKNOWN_NOT_QUERIED" and
         value.get("resource_table_integrity_fully_proved") is False and
         value.get("success_gate_requires_outer_final_stdout_and_authoritative_terminal") is True,
         "APK_IDENTITY_AND_SIGNATURE_DO_NOT_QUALIFY_OTHER_DOMAINS")
    need(all(type(value.get(key)) is int and value[key] == 0 for key in
             ("UI_actions", "App_launches", "permission_changes", "installs", "Android_namespace_commands", "ADB_commands",
              "business_data_content_reads", "native_commands", "new_scopes_published")), "NDK_READ_ONLY_ACTION_BOUNDARY")
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--actual-scope-file", required=True)
    args = parser.parse_args()
    scope_raw = pinned(Path(args.actual_scope_file), 59957, "b184299ce0a39a998752ed980a43192b396099f780bcf60bcfe53d0edf92ffe4")
    scope = json.loads(scope_raw)
    scope_worker_raw = pinned(S48 / "actual/worker.stdout.original.json", 10290, "aaa24285be227f4ad52fe63e5a2a06af63f7bab571fb5cf4d99e6d0ab02f12d1")
    scope_worker = json.loads(scope_worker_raw)
    need(sorted(scope["apps"]) == scope_worker["packages"] and len(scope["apps"]) == 48 and
         scope["runtime_epoch_sha256"] == scope_worker["guard_before"]["runtime_epoch_sha256"] and
         scope["fresh_signature_verification_performed"] is False, "ACTUAL_SCOPE_48_RAW_REQUIRED")
    scope_stdout = pinned(S48 / "actual/stdout.original.jsonl", 22547, "ae494d741522c8ff5efcfe7c36b256790c1387e6ee62824b9538a7ec785494ae")
    scope_terminal = pinned(S48 / "actual/status-01.original.json", 733, "76d9c72989ac5af982c25692bb06acb0c4e815742a24b19efbc7a3e836328ea1")
    old = pinned(BASE / "audit_fixture_version_repair.py", 75666, "5eb184f3ae89749a00c5bbe3459f6a9bacd3bfdcc0cdcae7ba0ac90140013a71").decode()
    old_owned = pinned(BASE / "owned_readonly_lifetime.py", 24219, "626105be852ff8da2acaffe5bbd5aac5c4fec7e5b22a736f5bbceb9dacbc2689").decode()
    old_stage = pinned(S48 / "stage_and_run_explicit48_r1.py", 7044, "00c1ba731d27c46af9d588294bff0c150cc54b9b88b5b36a532033653eb64158").decode()
    fns = definitions(old)
    tree = ast.parse(old); lines = old.splitlines(True)
    const = {}
    const_text = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name.isupper():
                const[name] = literal_constant(node.value)
                const_text[name] = "".join(lines[node.lineno - 1:node.end_lineno])
    kept_constants = ["DEPS", "ENV", "STAT", "MAX_APK", "MAX_BATCH_BYTES", "MAX_TOOL_OUTPUT", "MAX_RESULT", "ACTUAL_GUARD",
                      "ACTUAL_CANDIDATE", "ACTUAL_PROOF", "ACTUAL_PROOF_TERMINAL", "PROOF_JOB", "ANDROID_VERSION_DEFAULT_REFERENCE",
                      "OFFICIAL_HOST_JOB", "OFFICIAL_HOST_SOURCE", "OFFICIAL_HOST_STDOUT", "OFFICIAL_HOST_TERMINAL",
                      "OFFICIAL_CANDIDATE", "OFFICIAL_TOOL_ROOT"]
    previous_request = json.loads((BASE / "request.review-only.json").read_bytes())
    inputs = {"SCOPE_STDOUT": put("inputs/scope48.stdout.original.jsonl", scope_stdout),
              "SCOPE_TERMINAL": put("inputs/scope48.terminal.original.json", scope_terminal)}
    new_constants = {"STAGE": STAGE, "OUTPUT_PREFIX": OUTPUT, "ACTUAL_SCOPE": scope_worker["observation"]["app_scope"],
                     "PROTECTED_PACKAGES": sorted(scope["apps"]), "NDK_EXPECTED": scope["apps"]["com.example.ndk_tests"],
                     "ACTUAL_INVENTORY": previous_request["legacy_candidate_inventory"],
                     "SCOPE_JOB": "1a1b31300b9-fc05-8095",
                     "SCOPE_STAGE": "/home/alex/work/pocket4-explicit-48-scope-source-20261106-r1",
                     "SCOPE_VALIDATOR": {"path": "/home/alex/work/pocket4-explicit-48-scope-source-20261106-r1/owned_readonly_lifetime.py",
                                         "bytes": 17291, "sha256": "f42eaeab2bea2f9a697b705e5903aac6257d7c94698ee85cbc97bbf78b25064e"}, **inputs}
    kept = ["validate_candidate", "verify_candidate_inventory", "verify_actual_proof", "bind_static_dependencies", "recheck_static_aliases",
            "need", "now", "sha", "canonical", "read_bootstrap", "Store", "bind_tools", "recheck_tools", "run_tool", "badging_manifest",
            "xml_permissions", "parse_signature", "verify_official_host_proof", "bind_existing_official_layout", "add_official_tool_binding",
            "all_apk_evidence_verified"]
    imports = "".join("".join(lines[node.lineno - 1:node.end_lineno]) for node in tree.body if isinstance(node, (ast.Import, ast.ImportFrom)))
    source = '#!/usr/bin/env python3\n"""One current NDK APK: ordinary signature and metadata tools, full48 identity protection; no UI or install."""\n'
    source += imports + "\nsys.dont_write_bytecode = True\n\n"
    source += "\n".join(const_text[name] for name in kept_constants) + "\n"
    source += "".join(name + " = " + repr(value) + "\n" for name, value in new_constants.items()) + "\n\n"
    source += "\n\n\n".join(fns[name].rstrip() for name in kept) + "\n\n\n"
    source += (HERE / "ndk_contract.fragment.py").read_text() + "\n\n"
    audit = fns["audit"]
    audit = replace_once(audit, '    batch = PENDING_BATCHES[str(request["original_batch"])]',
                         '    batch = {"APK_count": 1, "logical_APK_bytes": 1397258}')
    start = audit.index('    result = {'); end = audit.index('    raw = read_bootstrap(', start)
    audit = audit[:start] + '''    result = {"schema": "pocket4-independent-ndk-apk-signature-metadata-v1", "started_utc": now(),
        "packages": request["packages"], "protected_packages": PROTECTED_PACKAGES, "request": request,
        "original_failures_reclassified": False, "old_ledger_modified": False,
        "scope_claimed_as_signature_evidence": False, "vendor_artifact_source_trust": "UNKNOWN",
        "UI_or_install_admitted": False, "all_current_launcher_APKs_reaudited": False,
        "UI_actions": 0, "App_launches": 0, "permission_changes": 0, "installs": 0,
        "Android_namespace_commands": 0, "ADB_commands": 0, "business_data_content_reads": 0,
        "native_commands": 0, "new_scopes_published": 0,
        "automatic_retry": False, "production_ready": False, "snapshot_consistent": False,
        "effective_permission_grants": "UNKNOWN_NOT_QUERIED", "apps": [], "commands": [], "errors": []}
''' + audit[end:]
    old_check = '        need(scope.get("schema") == "pocket4-versioned-app-scope-v1" and scope.get("runtime_epoch_sha256") == baseline["runtime_epoch_sha256"] and set(request["packages"]) <= set(scope["apps"]), "SAME_SUCCESSOR_APP_SCOPE_REQUIRED")'
    audit = replace_once(audit, old_check, '''        need(scope.get("schema") == "pocket4-versioned-app-scope-v1" and
             scope.get("runtime_epoch_sha256") == baseline["runtime_epoch_sha256"] and
             sorted(scope["apps"]) == PROTECTED_PACKAGES and scope["apps"][NDK_EXPECTED["package"]] == NDK_EXPECTED,
             "EXACT_CURRENT_48_SCOPE_AND_DISCOVERED_NDK_ROW")
        result["scope_guard_before"] = guard.check_app_scope(request["app_scope"], PROTECTED_PACKAGES)
        scope_validator_raw = core.pinned_record(SCOPE_VALIDATOR)
        scope_validator = types.ModuleType("actual48_pure_qualification_validator"); scope_validator.__file__ = SCOPE_VALIDATOR["path"]
        exec(compile(scope_validator_raw, scope_validator.__file__, "exec"), scope_validator.__dict__)
        scope_stdout_raw = core.pinned_record(SCOPE_STDOUT)
        scope_terminal_raw = core.pinned_record(SCOPE_TERMINAL)
        result["scope_qualification"] = validate_scope_qualification(scope_stdout_raw, scope_terminal_raw, scope_validator)''')
    start = audit.index('        prior_b13_raw = '); end = audit.index('        runtime = baseline["runtime"]', start)
    audit = audit[:start] + '''        need(sum(len(row["apks"]) for row in expected.values()) == 1, "EXACT_ONE_CURRENT_NDK_APK")
        total = sum(apk["bytes"] for row in expected.values() for apk in row["apks"])
        need(total == 1397258 and 0 < total <= MAX_BATCH_BYTES, "FIXED_COMPLETE_NDK_APK_BYTE_COUNT")
''' + audit[end:]
    for line in ['        result["corrective_publication_artifact"] = store.write("actual-b05-corrective-result.json", corrective_raw)\n',
                 '        result["original_failed_result_artifact"] = store.write("original-b05-failed-result.json", prior_failed_raw)\n',
                 '        result["original_passed_control_artifact"] = store.write("original-b01-passed-result.json", prior_control_raw)\n']:
        audit = replace_once(audit, line, "")
    audit = replace_once(audit, '        result["candidate_proof_artifact"]',
                         '        result["scope_joint_artifact"] = store.write("scope48.stdout.original.jsonl", scope_stdout_raw)\n'
                         '        result["scope_terminal_artifact"] = store.write("scope48.terminal.original.json", scope_terminal_raw)\n'
                         '        result["candidate_proof_artifact"]')
    audit = replace_once(audit, 'manifest_with_exact_fixture_default(outputs["badging"], outputs["manifest"], package, row, apk, item.get("signature"))',
                         'ndk_manifest_with_observed_absence(outputs["badging"], outputs["manifest"], row, apk, item.get("signature"))')
    audit = replace_once(audit, '        core.verify_runtime(pool, held, runtime)\n        result["guard_after"]',
                         '        core.verify_runtime(pool, held, runtime)\n'
                         '        result["scope_guard_after"] = guard.check_app_scope(request["app_scope"], PROTECTED_PACKAGES)\n'
                         '        need(result["scope_guard_after"] == result["scope_guard_before"], "COMPLETE_48_PROTECTION_CHANGED")\n'
                         '        result["guard_after"]')
    for line in ['        core.pinned_record(B13_FAILED_RESULT, MAX_RESULT)\n', '        core.pinned_record(ORIGINAL_FAILED_RESULT, MAX_RESULT)\n',
                 '        core.pinned_record(CORRECTIVE_RESULT, MAX_RESULT)\n', '        core.pinned_record(ORIGINAL_CONTROL_RESULT, MAX_RESULT)\n']:
        audit = replace_once(audit, line, "")
    audit = replace_once(audit, '        core.pinned_record(OFFICIAL_HOST_SOURCE, 131072)\n',
                         '        core.pinned_record(OFFICIAL_HOST_SOURCE, 131072)\n'
                         '        core.pinned_record(SCOPE_STDOUT)\n        core.pinned_record(SCOPE_TERMINAL)\n        core.pinned_record(SCOPE_VALIDATOR)\n')
    start = audit.index('        fixture_manifest = '); end = audit.index('        # Preserve every full observation', start)
    audit = audit[:start] + '''        result["ndk_audit_complete"] = (result["all_manifests_and_signatures_verified"] and
            result["all_primary_commands_succeeded"] and result["official_badging_stderr_empty"] and
            result.get("official_layout_descriptors_closed") is True and result["official_layout_before_and_after_all_commands"] and
            result.get("scope_guard_before") == result.get("scope_guard_after") and
            result.get("scope_qualification", {}).get("normal_owned_joint_validated") is True)
''' + audit[end:]
    audit = audit.replace('corrective_batch13_audit_complete', 'ndk_audit_complete')
    old_limit = next(line for line in audit.splitlines() if 'result["inference_limit"] =' in line)
    audit = replace_once(audit, old_limit,
                         '        result["inference_limit"] = "Current exact NDK APK normal cryptographic verification and manifest metadata only. PM signer equality does not authenticate package origin or authorize an upgrade. The 48-package identity scope, original FAILED/STOP/UNKNOWN records, permissions, UI and production gates remain unchanged. Resources are not fully validated by badging."')
    audit = audit.replace('B13_FIXTURE_VERSION_CORRECTIVE_AUDIT_VERIFIED', 'NDK_CURRENT_APK_SIGNATURE_AND_METADATA_VERIFIED')
    audit = audit.replace('B13_FIXTURE_VERSION_CORRECTIVE_AUDIT_INCOMPLETE_NO_RETRY', 'NDK_CURRENT_APK_AUDIT_INCOMPLETE_NO_RETRY')
    source += audit + "\n\n\n"
    main_text = fns['main'].replace('pocket4-b13-version-repair-entry-rejection-v1', 'pocket4-ndk-apk-audit-entry-rejection-v1')
    main_text = main_text.replace('corrective_batch13_audit_complete', 'ndk_audit_complete')
    source += main_text + '\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'
    compile(source, "audit_ndk_current.py", "exec")
    worker_pin = put("audit_ndk_current.py", source.encode())
    module = {}; exec(compile(source, "local_unexecuted_ndk_source", "exec"), module)
    request = {"schema": "pocket4-ndk-current-apk-signature-metadata-request-v1", "guard": const['ACTUAL_GUARD'],
               "app_scope": new_constants['ACTUAL_SCOPE'], "packages": ["com.example.ndk_tests"], "protected_packages": new_constants['PROTECTED_PACKAGES'],
               "output_root": OUTPUT, "official_release_assets": None,
               "legacy_candidate_aapt2": const['ACTUAL_CANDIDATE'], "legacy_candidate_inventory": new_constants['ACTUAL_INVENTORY'],
               "legacy_candidate_proof": const['ACTUAL_PROOF'], "legacy_candidate_terminal": const['ACTUAL_PROOF_TERMINAL'],
               "official_candidate_aapt2": const['OFFICIAL_CANDIDATE'], "official_host_stdout": const['OFFICIAL_HOST_STDOUT'],
               "official_host_terminal": const['OFFICIAL_HOST_TERMINAL'], "scope_joint_stdout": inputs['SCOPE_STDOUT'],
               "scope_terminal": inputs['SCOPE_TERMINAL'], "scope_validator": new_constants['SCOPE_VALIDATOR']}
    module['validate_request'](request)
    request_pin = put("request.review-only.json", canonical(request))
    config = {'schema': 'pocket4-owned-readonly-observation-config-v1', 'kind': 'ndk', 'stage_root': STAGE,
              'worker': worker_pin, 'request': request_pin,
              'prior_unexecuted_source': {'bytes': 75666, 'sha256': '5eb184f3ae89749a00c5bbe3459f6a9bacd3bfdcc0cdcae7ba0ac90140013a71',
                  'preserved': True, 'meaning': 'Actual b13 source and receipts remain preserved; this inherited field name does not reclassify it as unexecuted.'}}
    owned = old_owned
    owned = replace_once(owned, next(line for line in owned.splitlines() if line.startswith('CONFIG = ')), 'CONFIG = ' + repr(config))
    owned = owned.replace('("explicit47", "calendar")', '("explicit47", "ndk")').replace('CONFIG["kind"] == "calendar"', 'CONFIG["kind"] == "ndk"')
    nodes = definitions(owned)
    owned = replace_once(owned, nodes['worker_gate'], OWNED_GATE.strip())
    compile(owned, 'owned_readonly_lifetime.py', 'exec')
    owned_pin = put('owned_readonly_lifetime.py', owned.encode())
    names = ['owned_readonly_lifetime.py', 'audit_ndk_current.py', 'request.review-only.json',
             'inputs/scope48.stdout.original.jsonl', 'inputs/scope48.terminal.original.json']
    files = [{'name': name, 'bytes': len((HERE/name).read_bytes()), 'sha256': sha((HERE/name).read_bytes())}for name in names]
    stager = replace_once(old_stage, next(line for line in old_stage.splitlines() if line.startswith('ROOT=')), 'ROOT=' + repr(STAGE))
    stager = replace_once(stager, next(line for line in stager.splitlines() if line.startswith('FILES=')), 'FILES=' + repr(files))
    stager = stager.replace('one explicit 48-package identity observation', 'one independent NDK signature and metadata audit')
    stager = stager.replace('pocket4-explicit48-owned-scope-source-stage-v1', 'pocket4-ndk-apk-audit-source-stage-v1')
    stager = stager.replace('pocket4-explicit48-owned-scope-source-stage-result-v1', 'pocket4-ndk-apk-audit-source-stage-result-v1')
    stager_pin = put('stage_and_run.py', stager.encode())
    payload = {'schema': 'pocket4-ndk-apk-audit-source-stage-v1', 'files': [{'name': name, 'text': (HERE/name).read_text()}for name in names]}
    stdin = canonical(payload); need(len(stdin) <= 262144, 'ORIGINAL_STAGE_INPUT_CAP_PRESERVED')
    stdin_pin = put('stage.stdin.original.json', stdin)
    packet = {'host': 'pocket4', 'executable': '/usr/bin/sudo', 'args': ['-n','/usr/bin/python3','-I','-B','-c',stager],
              'cwd': '/home/alex/work', 'stdin': stdin.decode(), 'idempotency_key': 'app-history-20261106-ndk-current-apk-signature-metadata-r1',
              'timeout_seconds': 1100, 'memory_max_bytes': 1073741824, 'cpu_quota_percent': 100, 'nice': 10}
    packet_pin = put('process-request.review-only.json', canonical(packet))
    for name, before, after in [('collector-against-actual-b13.diff',old,source),('owned-against-actual-b13.diff',old_owned,owned),
                                ('stager-against-actual48.diff',old_stage,stager)]:
        put(name, ''.join(difflib.unified_diff(before.splitlines(True),after.splitlines(True),fromfile='actual-frozen-source',tofile='independent-ndk-r1')).encode())
    defs_new = definitions(source); preserved = []
    for name in kept:
        need(defs_new[name] == fns[name], 'HELPER_DEFINITION_CHANGED:' + name)
        preserved.append({'name':name,'bytes':len(defs_new[name].encode()),'sha256':sha(defs_new[name].encode())})
    owned_before,owned_after = definitions(old_owned),definitions(owned)
    common = ['need','canonical','pin_bytes','load','retired','child','combined','publish','main']
    for name in common:need(owned_before[name]==owned_after[name], 'OWNED_LIFETIME_CHANGED:' + name)
    put('INHERITANCE.json',canonical({'schema':'pocket4-ndk-audit-source-inheritance-v1','remote_executed':False,
        'actual_scope_input':{'bytes':len(scope_raw),'sha256':sha(scope_raw)}, 'collector_preserved_definitions':preserved,
        'owned_preserved_definitions':[{'name':n,'bytes':len(owned_after[n].encode()),'sha256':sha(owned_after[n].encode())}for n in common],
        'tool_argv_contract':'exact original three-command lists; no min-sdk override or APK edits',
        'worker':worker_pin,'owned':owned_pin,'stager':stager_pin,'stdin':stdin_pin,'process_request':packet_pin,'stage_files':files}))
    print(json.dumps({'worker':worker_pin,'owned':owned_pin,'stager':stager_pin,'stdin':stdin_pin,'packet':packet_pin,'remote_executed':False},sort_keys=True))


if __name__ == '__main__':
    main()
