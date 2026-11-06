#!/usr/bin/env python3
"""Local, deterministic assembly of the explicitly scoped b05 corrective audit."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[2]
OLD = PROJECT / "successor_audit_requests/diagnostics/calendar-official-aapt2-comparison-r1"
STAGE = "/home/alex/work/pocket4-b05-official-tool-repair-source-20261106-r1"
OUTPUT = "/home/alex/work/pocket4-successor-apk-audit-20261106-b05-official-tool-repair-r1-01"
PACKAGES = ["com.MobileTicket", "com.amazon.mShop.android.shopping", "com.android.calendar", "com.android.camera2"]
LINEAGE = {"original_batch": 5, "original_job_id": "1a1b16f06d5-fc05-78b1",
           "original_plan_sha256": "d288affedc2eae8d28f2d7083df4c89d756e51ba8e5ebfb2264f9d3c6d783139",
           "original_request_sha256": "06ab902809dffe4921d5a98883e3c2caa8594e6585ed0f8fcb4f33df58d4cc98",
           "original_state": "failed", "original_exit_code": 1}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False) + "\n").encode()


def read(name, size, digest):
    raw = (OLD / name).read_bytes()
    assert (len(raw), sha(raw)) == (size, digest), name
    return raw.decode()


def write(name, raw):
    if isinstance(raw, str):
        raw = raw.encode()
    path = ROOT / name
    if path.exists():
        assert path.read_bytes() == raw, "EXISTING_NEW_SOURCE_DIFFERS: " + name
    else:
        with path.open("xb") as handle:
            handle.write(raw)
    return {"path": STAGE + "/" + name, "bytes": len(raw), "sha256": sha(raw)}


def once(text, old, new):
    assert text.count(old) == 1, old[:100]
    return text.replace(old, new, 1)


def assignment(text, name, value):
    node = next(n for n in ast.parse(text).body if isinstance(n, ast.Assign) and
                any(isinstance(t, ast.Name) and t.id == name for t in n.targets))
    return once(text, ast.get_source_segment(text, node), name + " = " + repr(value))


def function(text, name):
    node = next(n for n in ast.parse(text).body if isinstance(n, ast.FunctionDef) and n.name == name)
    return ast.get_source_segment(text, node)


def diff(name, before, after):
    write(name + ".diff", "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
        fromfile="actual-successful-official-calendar-comparison/" + name,
        tofile="new-complete-original-b05-corrective-audit/" + name)))


def main():
    old = read("diagnose_calendar_and_fcitx.py", 62331, "191692dda06eaaaa3fcbe024399985cf2ac6a547b567fd25967c96a1b31b09f6")
    node = ast.parse(old).body[0]
    source = once(old, ast.get_source_segment(old, node), '''"""Complete corrective audit of original b05 using the qualified official tool.

The four original packages and all six APKs are reobserved. The old failed
job, source and gate remain unchanged. All three primary commands for every
APK must succeed. Host tool identity, full 19+7 dependency checks, controlled
RUNPATH absence checks, typed runtime, held APKs/data, locks and owned lifetime
remain mandatory. No UI, Android command, permission change or installation.
"""''')
    source = assignment(source, "OUTPUT_PREFIX", "/home/alex/work/pocket4-successor-apk-audit-20261106-b05-official-tool-repair-r1-")
    source = assignment(source, "DIAGNOSTIC_PACKAGES", PACKAGES).replace("DIAGNOSTIC_PACKAGES", "REPAIR_PACKAGES")
    node = next(n for n in ast.parse(source).body if isinstance(n, ast.Assign) and
                any(isinstance(t, ast.Name) and t.id == "DIAGNOSTIC_APKS" for t in n.targets))
    source = once(source, ast.get_source_segment(source, node),
                  "REPAIR_LINEAGE = " + repr(LINEAGE) + "\nREPAIR_APK_COUNT = 6\nREPAIR_LOGICAL_APK_BYTES = 341931165")
    old_sdk = '''    for name, prefix in (("min_sdk", "sdkVersion:"), ("target_sdk", "targetSdkVersion:"), ("max_sdk", "maxSdkVersion:")):
        found = [line for line in text.splitlines() if line.startswith(prefix)]
        need(len(found) <= 1, "AMBIGUOUS_AAPT_SDK")
        value[name] = re.findall(r"'([^']*)'", found[0])[0] if found and re.findall(r"'([^']*)'", found[0]) else None'''
    new_sdk = '''    for name, prefixes in (("min_sdk", ("sdkVersion:", "minSdkVersion:")),
                           ("target_sdk", ("targetSdkVersion:",)), ("max_sdk", ("maxSdkVersion:",))):
        found = [line for line in text.splitlines() if line.startswith(prefixes)]
        need(len(found) <= 1, "AMBIGUOUS_AAPT_SDK")
        if found:
            parsed = re.fullmatch(r"(?:sdkVersion|minSdkVersion|targetSdkVersion|maxSdkVersion):'([^']+)'", found[0])
            need(parsed is not None, "MALFORMED_AAPT_SDK_LINE")
            value[name] = parsed[1]
        else:
            value[name] = None'''
    source = once(source, old_sdk, new_sdk)
    diff("badging-manifest-parser", function(old, "badging_manifest"), function(source, "badging_manifest"))
    source = once(source, function(source, "clean_official_badging_observations"), '''def clean_official_badging_observations(result):
    badging = [row for row in result["commands"] if row.get("name") == "badging"]
    expected = [(app["package"], apk["path"]) for app in result["apps"] for apk in app["apks"]]
    return bool(len(expected) == REPAIR_APK_COUNT and
                [(row.get("package"), row.get("apk_path")) for row in badging] == expected and
                all(row.get("returncode") == 0 and row.get("output_capture_complete") is True and
                    row.get("stderr", {}).get("bytes") == 0 and row.get("stderr", {}).get("sha256") ==
                    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855" for row in badging))''')
    source = once(source, '"official_host_stdout", "official_host_terminal"}, "CLOSED_DIAGNOSTIC_REQUEST_SCHEMA")',
                  '"official_host_stdout", "official_host_terminal", "repair_of"}, "CLOSED_B05_CORRECTIVE_REQUEST_SCHEMA")')
    source = source.replace('"pocket4-independent-calendar-official-aapt2-comparison-request-v1"', '"pocket4-original-b05-official-tool-repair-request-v1"')
    source = once(source, 'need(request["packages"] == REPAIR_PACKAGES, "EXACT_CALENDAR_AND_PASSED_FCITX_CONTROL_REQUIRED")',
                  'need(request["packages"] == REPAIR_PACKAGES and request["repair_of"] == REPAIR_LINEAGE,\\n         "EXACT_ORIGINAL_B05_FOUR_PACKAGE_CORRECTIVE_SCOPE_REQUIRED")'.replace("\\n", "\n"))
    source = once(source, 'result.get("all_primary_commands_succeeded") is True',
                  'result.get("all_commands_succeeded") is True')
    source = source.replace('"pocket4-independent-calendar-official-aapt2-resource-comparison-v1"', '"pocket4-original-b05-corrective-apk-audit-v1"')
    source = once(source, '"resource_diagnostic_covers_all_45_Launcher_apps": False, "prior_failure_inference_only": True,',
                  '"all_45_Launcher_apps_reobserved": False, "repair_of": REPAIR_LINEAGE,\\n        "legacy_badging_reexecuted": False,'.replace("\\n", "\n"))
    obsolete = '''        for package, original in DIAGNOSTIC_APKS.items():
            apks = expected[package]["apks"]
            need(len(apks) == 1 and all(apks[0][key] == original[key] for key in ("bytes", "sha256")), "DIAGNOSTIC_APKS_DIFFER_FROM_ACTUAL_B01_B05_BYTES")
'''
    source = once(source, obsolete, "")
    marker = '        result["original_failure_reference"] = ORIGINAL_FAILED_RESULT\n'
    matching = '''        need(prior_failed.get("packages") == REPAIR_PACKAGES and
             [row.get("package") for row in prior_failed["apps"]] == REPAIR_PACKAGES, "EXACT_ORIGINAL_B05_PACKAGE_SET")
        prior_apps = {row["package"]: row for row in prior_failed["apps"]}
        need(sum(len(row["apks"]) for row in expected.values()) == REPAIR_APK_COUNT, "ORIGINAL_B05_SIX_APKS_REQUIRED")
        for package in REPAIR_PACKAGES:
            previous, current = prior_apps[package], expected[package]
            need(previous["uid"] == current["uid"] and previous["PM_version_code"] == current["version_code"] and
                 previous["code_path"] == current["code_path"] and previous["data_directories"] == current["data_directories"] and
                 previous["PM_certificate_sha256"] == current["package_manager_certificate_sha256"], "ORIGINAL_B05_APP_IDENTITY_CHANGED")
            projection = lambda rows: sorted(
                ({key: apk[key] for key in ("path", "bytes", "sha256", "file")} for apk in rows), key=lambda row: row["path"])
            need(projection(previous["apks"]) == projection(current["apks"]), "ORIGINAL_B05_COMPLETE_APK_SET_CHANGED")
        result["all_original_b05_APKs_and_app_identities_match_scope"] = True
'''
    source = once(source, marker, matching + marker)
    source = once(source, '        need(0 < total <= MAX_BATCH_BYTES and all(0 < len(row["apks"]) <= 32 for row in expected.values()), "SCOPED_APK_SET_BOUND")',
                  '        need(total == REPAIR_LOGICAL_APK_BYTES and 0 < total <= MAX_BATCH_BYTES and\\n             all(0 < len(row["apks"]) <= 32 for row in expected.values()), "EXACT_B05_SCOPED_APK_SET_BOUND")'.replace("\\n", "\n"))
    source = once(source, '''                        ("manifest", [tools["aapt"]["pin"]["resolved_path"], "dump", "xmltree", source, "AndroidManifest.xml"]),
                        ("legacy-badging", [tools["aapt"]["pin"]["resolved_path"], "dump", "badging", source])]''',
                  '''                        ("manifest", [tools["aapt"]["pin"]["resolved_path"], "dump", "xmltree", source, "AndroidManifest.xml"])]''')
    first = '        primary = [x for x in result["commands"] if x.get("name") != "legacy-badging"]\n'
    last = '        result["ended_utc"] = now()\n'
    start, end = source.index(first), source.index(last, source.index(first))
    source = source[:start] + '''        result["all_primary_commands_succeeded"] = len(result["commands"]) == 3 * REPAIR_APK_COUNT and result["all_commands_succeeded"]
        result["all_manifests_and_signatures_verified"] = all_apk_evidence_verified(result, request["packages"])
        result["official_badging_stderr_empty"] = clean_official_badging_observations(result)
        observations = result.get("official_private_layout", {}).get("observations", [])
        result["official_layout_before_and_after_all_commands"] = len(observations) == 2 + 6 * REPAIR_APK_COUNT and all(
            row.get("complete") is True and row.get("all_five_search_directories_and_thirty_candidates_proved") is True for row in observations)
        result["corrective_audit_complete"] = (result["all_manifests_and_signatures_verified"] and
            result["all_primary_commands_succeeded"] and result["official_badging_stderr_empty"] and
            result.get("official_layout_descriptors_closed") is True and result["official_layout_before_and_after_all_commands"] and
            result.get("all_original_b05_APKs_and_app_identities_match_scope") is True)
        result["resource_table_integrity_fully_proved"] = False
        result["inference_limit"] = "Complete current original-b05 APK/manifest/signature audit; the old failed job and gate remain unchanged. Badging does not prove all resource-table health, effective grants, or business readiness."
''' + source[end:]
    source = once(source, '        result["status"] = "OFFICIAL_TOOL_TWO_APK_COMPARISON_COMPLETE" if result["comparison_complete"] else "OFFICIAL_TOOL_RESOURCE_DIAGNOSTIC_INCOMPLETE"',
                  '        result["status"] = "ORIGINAL_B05_CORRECTIVE_APK_AUDIT_VERIFIED" if result["corrective_audit_complete"] else "ORIGINAL_B05_CORRECTIVE_AUDIT_INCOMPLETE_NO_RETRY"')
    source = once(source, '''        if not result["all_manifests_and_signatures_verified"]:
            result["comparison_complete"] = False
            result["same_APK_bytes_new_parser_succeeded"] = False
            result["observed_legacy_badging_failure_is_parser_dependent"] = False''',
                  '''        if not result["all_manifests_and_signatures_verified"]:
            result["corrective_audit_complete"] = False''')
    source = source.replace('"pocket4-independent-calendar-aapt2-entry-rejection-v1"', '"pocket4-original-b05-corrective-audit-entry-rejection-v1"')
    source = once(source, '''        result["same_APK_bytes_new_parser_succeeded"] = False
        result["observed_legacy_badging_failure_is_parser_dependent"] = False
        result["comparison_complete"] = False''', '        result["corrective_audit_complete"] = False')
    source = once(source, 'return 0 if result.get("comparison_complete") is True else 1',
                  'return 0 if result.get("corrective_audit_complete") is True else 1')
    assert "DIAGNOSTIC_APKS" not in source and "DIAGNOSTIC_PACKAGES" not in source and "comparison_complete" not in source
    compile(source, "audit_original_b05.py", "exec")
    sourcepin = write("audit_original_b05.py", source)
    diff("collector-against-actual-comparison", old, source)

    request = json.loads((OLD / "request.review-only.json").read_bytes())
    request.update(schema="pocket4-original-b05-official-tool-repair-request-v1", packages=PACKAGES,
                   output_root=OUTPUT, repair_of=LINEAGE)
    requestpin = write("request.review-only.json", canonical(request))
    old_wrapper = read("owned_readonly_lifetime.py", 16925, "a922596684aee084ae0aa07d0acaf1a4fa3b7088caf0e18b46b3fde5ca81a7ba")
    cfg_node = next(n for n in ast.parse(old_wrapper).body if isinstance(n, ast.Assign) and
                    any(isinstance(t, ast.Name) and t.id == "CONFIG" for t in n.targets))
    cfg = ast.literal_eval(cfg_node.value)
    cfg.update(stage_root=STAGE, worker=sourcepin, request=requestpin)
    wrapper = assignment(old_wrapper, "CONFIG", cfg)
    before = function(wrapper, "worker_gate")
    gate = before.replace('"pocket4-independent-calendar-official-aapt2-resource-comparison-v1"', '"pocket4-original-b05-corrective-apk-audit-v1"')
    gate = gate.replace('"OFFICIAL_TOOL_TWO_APK_COMPARISON_COMPLETE"', '"ORIGINAL_B05_CORRECTIVE_APK_AUDIT_VERIFIED"')
    gate = gate.replace('"comparison_complete"', '"corrective_audit_complete"')
    gate = gate.replace('"legacy_badging_observations_complete"', '"all_commands_succeeded"')
    gate = gate.replace('len(value.get("commands", [])) == 8', 'len(value.get("commands", [])) == 18')
    gate = gate.replace('value.get("packages") == ["com.android.calendar", "org.fcitx.fcitx5.android"]',
                        'value.get("packages") == ' + repr(PACKAGES))
    marker = '        need(value.get("original_failed_audit_reclassified") is False and value.get("original_batch_05_gate_advanced") is False,'
    gate = once(gate, marker, '''        need(value.get("repair_of") == ''' + repr(LINEAGE) + ''' and
             value.get("all_original_b05_APKs_and_app_identities_match_scope") is True and
             value.get("legacy_badging_reexecuted") is False, "EXACT_FULL_ORIGINAL_B05_CORRECTIVE_COVERAGE")
''' + marker)
    wrapper = once(wrapper, before, gate)
    assert function(wrapper, "child") == function(old_wrapper, "child")
    compile(wrapper, "owned_readonly_lifetime.py", "exec")
    wrapperpin = write("owned_readonly_lifetime.py", wrapper)
    diff("owned-gate-against-actual-comparison", old_wrapper, wrapper)

    old_stage = read("stage_and_run_comparison.py", 7357, "026978c7faad2c50ba16ff801cf6365f0cbeb630e304026b15ed07a956a66863")
    stage = assignment(old_stage, "ROOT", STAGE)
    files = [{"name": pin["path"][len(STAGE)+1:], "bytes": pin["bytes"], "sha256": pin["sha256"]}
             for pin in (wrapperpin, sourcepin, requestpin)]
    stage = assignment(stage, "FILES", files)
    # The already-qualified stage transport/schema is retained. The new root,
    # exact three files and the new worker/request schemas bind this repair.
    compile(stage, "stage_and_run_b05_repair.py", "exec")
    stagepin = write("stage_and_run_b05_repair.py", stage)
    diff("stager-against-actual-comparison", old_stage, stage)
    # The fixed old proof files are reused in their actual existing root-private
    # locations; the new source does not move, rewrite, or republish them.
    old_packet = json.loads((OLD / "process-request.review-only.json").read_bytes())
    old_payload = json.loads(old_packet["stdin"])
    payload_schema = old_payload["schema"]
    payload = {"schema": payload_schema, "files": [{"name": row["name"], "text": (ROOT / row["name"]).read_text()} for row in files]}
    stdin = canonical(payload)
    assert len(stdin) <= 262144
    write("stage.stdin.original.json", stdin)
    assert old_packet["args"][-1] == old_stage
    old_packet.update(idempotency_key="sidecar-evidence-20261106-original-b05-official-tool-repair-r1",
                      args=old_packet["args"][:-1] + [stage], stdin=stdin.decode())
    packetpin = write("process-request.review-only.json", canonical(old_packet))
    print(json.dumps({"worker":sourcepin,"wrapper":wrapperpin,"request":requestpin,"stager":stagepin,
                      "process_request":packetpin,"stdin_bytes":len(stdin),"runtime_jobs_submitted":0},sort_keys=True))


if __name__ == "__main__":
    main()
