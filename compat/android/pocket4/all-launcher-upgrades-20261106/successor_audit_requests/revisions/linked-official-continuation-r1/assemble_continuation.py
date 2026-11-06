#!/usr/bin/env python3
"""Local assembly only: original b06-b13, after the actual full b05 correction.

No remote calls, Main observations, claims, or changes to the original ledger.
Existing generated files must match byte for byte; never overwrite a revision.
"""
import ast
import difflib
import hashlib
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
OLD = HERE.parent / "b05-official-tool-repair-r1"
ORIGINAL = PROJECT / "successor_audit_requests/final-upgrades-r1"
LEDGER = "successor_audit_requests/actual/batches-final-r1"
OLD_PLAN_SHA = "d288affedc2eae8d28f2d7083df4c89d756e51ba8e5ebfb2264f9d3c6d783139"
OLD_SOURCE_SHA = "b4d27e1364feb28cab6634c77ed764e15359720025192117ecc8cb84d4391e1a"
REPAIR_JOB = "1a1b289b789-fc05-7e7e"
REPAIR_RESULT = {"path": "/home/alex/work/pocket4-successor-apk-audit-20261106-b05-official-tool-repair-r1-01/result.json", "bytes": 276285, "sha256": "3d0c794f4e2ac04ee6c67c22cd62ae4d560fc3c11e5f8faa7e514145f6a421f1"}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n").encode("ascii")


def checked(path, size=None, digest=None):
    raw = path.read_bytes()
    assert size is None or len(raw) == size, path
    assert digest is None or sha(raw) == digest, path
    return raw


def write(name, raw):
    raw = raw.encode("utf-8") if isinstance(raw, str) else raw
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == raw, "EXISTING_NEW_REVISION_DIFFERS: " + name
    else:
        with path.open("xb") as out:
            out.write(raw)
    return {"file": name, "bytes": len(raw), "sha256": sha(raw)}


def pin(path):
    raw = path.read_bytes()
    return {"file": str(path.relative_to(PROJECT)), "bytes": len(raw), "sha256": sha(raw)}


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


def delta(name, before, after):
    return write(name, "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
        fromfile="actual-successful-b05/" + name, tofile="linked-b06-b13/" + name)))


def main():
    original = json.loads(checked(ORIGINAL / "REQUEST_MANIFEST.json", 17548, OLD_PLAN_SHA))
    old_scope = json.loads(checked(PROJECT / "successor_install/actual/douyin-01/app-scope-after.private.json", 57340,
                                 "489129d6e39a5aebc410ebcf74706279a99ff6751a15bd0a6b324ddd007e01a4"))
    scope = json.loads(checked(PROJECT / "successor_audit_requests/explicit47_scope_r2/actual-readback/app-scope.private.json", 58854,
                             "44f9ce783000a672c270e98afdaeb74bd79654508bfacae6793316ff4252e52f"))
    repair = json.loads(checked(OLD / "actual/worker.stdout.original.json", 276704,
                              "b0c876c40165fc10c515fa0db8f8b7a916e969a92fba531375a7a226e97ad8d7"))
    assert repair["final_receipt"] == REPAIR_RESULT and repair["corrective_audit_complete"] is True
    batches = {}
    for row in original["batches"][5:]:
        n = row["batch"]
        assert n in range(6, 14)
        assert all(old_scope["apps"][p] == scope["apps"][p] for p in row["packages"])
        count = sum(len(scope["apps"][p]["apks"]) for p in row["packages"])
        total = sum(a["bytes"] for p in row["packages"] for a in scope["apps"][p]["apks"])
        assert (count, total) == (row["APK_count"], row["logical_APK_bytes"])
        batches[str(n)] = {"packages": row["packages"], "APK_count": count, "logical_APK_bytes": total,
                           "original_request_sha256": row["request"]["sha256"]}
    assert len(batches) == 8 and sum(len(r["packages"]) for r in batches.values()) == 31
    assert sum(r["APK_count"] for r in batches.values()) == 65
    lineage = {"original_plan_sha256": OLD_PLAN_SHA, "original_failed_b05_job_id": "1a1b16f06d5-fc05-78b1",
               "original_b05_state": "failed", "original_b05_exit_code": 1, "corrective_job_id": REPAIR_JOB,
               "corrective_result": REPAIR_RESULT, "corrective_source_sha256": OLD_SOURCE_SHA,
               "corrective_authoritative_terminal_sha256": "c0d5d07a7be5d7ccbbbdc0451a4ac1a553bf690a1956b84ba7891aedc7f8652c"}
    before = checked(OLD / "audit_original_b05.py", 62604, OLD_SOURCE_SHA).decode()
    source = before
    doc = ast.get_source_segment(source, ast.parse(source).body[0])
    source = once(source, doc, '''"""The eight original unclaimed batches after the independently settled b05 repair.

The original failed job is preserved. Only the fixed original b06-b13 package
groups are accepted. The successful b05 tool/parser, held APKs, signatures,
19+7 dependency bindings, RUNPATH absence checks, typed guard and owned lifetime
remain unchanged. No UI, Android command, permission change or installation.
"""''')
    source = assignment(source, "OUTPUT_PREFIX", "/home/alex/work/pocket4-successor-apk-audit-20261106-linked-official-r1-")
    source = assignment(source, "REPAIR_PACKAGES", batches).replace("REPAIR_PACKAGES", "PENDING_BATCHES")
    source = assignment(source, "REPAIR_LINEAGE", lineage).replace("REPAIR_LINEAGE", "CONTINUATION_LINEAGE")
    source = once(source, "REPAIR_APK_COUNT = 6\nREPAIR_LOGICAL_APK_BYTES = 341931165", "CORRECTIVE_RESULT = " + repr(REPAIR_RESULT))
    source = once(source, '"repair_of"}, "CLOSED_B05_CORRECTIVE_REQUEST_SCHEMA")',
                  '"continuation_of", "original_batch"}, "CLOSED_LINKED_REMAINING_BATCH_REQUEST_SCHEMA")')
    source = source.replace('"pocket4-original-b05-official-tool-repair-request-v1"', '"pocket4-linked-official-remaining-batch-request-v1"')
    source = once(source, '''    need(request["packages"] == PENDING_BATCHES and request["repair_of"] == CONTINUATION_LINEAGE,
         "EXACT_ORIGINAL_B05_FOUR_PACKAGE_CORRECTIVE_SCOPE_REQUIRED")''', '''    need(type(request["original_batch"]) is int and str(request["original_batch"]) in PENDING_BATCHES,
         "ONLY_ORIGINAL_UNCLAIMED_BATCHES_06_TO_13")
    batch = PENDING_BATCHES[str(request["original_batch"])]
    need(request["packages"] == batch["packages"] and request["continuation_of"] == CONTINUATION_LINEAGE and
         request["output_root"] == OUTPUT_PREFIX + "b%02d" % request["original_batch"],
         "EXACT_LINKED_ORIGINAL_BATCH_SCOPE_REQUIRED")''')
    source = once(source, 'len(expected) == REPAIR_APK_COUNT', 'len(expected) == PENDING_BATCHES[str(result["original_batch"])]["APK_count"]')
    source = source.replace('"pocket4-original-b05-corrective-apk-audit-v1"', '"pocket4-linked-official-remaining-apk-audit-v1"')
    source = once(source, '    validate_request(request)\n    need(os.getuid()', '    validate_request(request)\n    batch = PENDING_BATCHES[str(request["original_batch"])]\n    need(os.getuid()')
    source = once(source, '"all_45_Launcher_apps_reobserved": False, "repair_of": CONTINUATION_LINEAGE,',
                  '"all_45_Launcher_apps_reobserved": False, "continuation_of": CONTINUATION_LINEAGE,\n        "original_batch": request["original_batch"],')
    first = '        need(prior_failed.get("packages") == PENDING_BATCHES and\n'
    last = '        result["all_original_b05_APKs_and_app_identities_match_scope"] = True\n'
    start = source.index(first); end = source.index(last, start) + len(last)
    source = source[:start] + '''        corrective_raw = core.pinned_record(CORRECTIVE_RESULT, MAX_RESULT)
        corrective = core.parse(corrective_raw)
        need(corrective.get("schema") == "pocket4-original-b05-corrective-apk-audit-v1" and
             corrective.get("status") == "ORIGINAL_B05_CORRECTIVE_APK_AUDIT_VERIFIED" and
             corrective.get("corrective_audit_complete") is True and corrective.get("errors") == [] and
             corrective.get("original_failed_audit_reclassified") is False and
             corrective.get("original_batch_05_gate_advanced") is False and
             corrective.get("collector_source", {}).get("sha256") == CONTINUATION_LINEAGE["corrective_source_sha256"],
             "EXACT_ACTUAL_B05_CORRECTIVE_PUBLICATION_REQUIRED")
        need(sum(len(row["apks"]) for row in expected.values()) == batch["APK_count"], "COMPLETE_ORIGINAL_BATCH_APK_COUNT_REQUIRED")
        result["corrective_publication_reference"] = CORRECTIVE_RESULT
        result["corrective_terminal_checked_by_local_coordinator_not_this_worker"] = True
''' + source[end:]
    source = once(source, 'total == REPAIR_LOGICAL_APK_BYTES', 'total == batch["logical_APK_bytes"]')
    source = source.replace('"EXACT_B05_SCOPED_APK_SET_BOUND"', '"EXACT_ORIGINAL_PENDING_BATCH_APK_SET_BOUND"')
    source = once(source, '        result["original_failed_result_artifact"] = store.write("original-b05-failed-result.json", prior_failed_raw)\n',
                  '        result["corrective_publication_artifact"] = store.write("actual-b05-corrective-result.json", corrective_raw)\n        result["original_failed_result_artifact"] = store.write("original-b05-failed-result.json", prior_failed_raw)\n')
    source = once(source, '        core.pinned_record(ORIGINAL_FAILED_RESULT, MAX_RESULT)\n',
                  '        core.pinned_record(ORIGINAL_FAILED_RESULT, MAX_RESULT)\n        core.pinned_record(CORRECTIVE_RESULT, MAX_RESULT)\n')
    source = source.replace('3 * REPAIR_APK_COUNT', '3 * batch["APK_count"]').replace('6 * REPAIR_APK_COUNT', '6 * batch["APK_count"]')
    source = source.replace('"corrective_audit_complete"', '"linked_batch_audit_complete"')
    # The actual b05 publication still has its original key/schema.
    source = once(source, 'corrective.get("linked_batch_audit_complete")', 'corrective.get("corrective_audit_complete")')
    source = once(source, '            result.get("all_original_b05_APKs_and_app_identities_match_scope") is True)',
                  '            result.get("corrective_publication_reference") == CORRECTIVE_RESULT)')
    source = once(source, '        result["inference_limit"] = "Complete current original-b05 APK/manifest/signature audit; the old failed job and gate remain unchanged. Badging does not prove all resource-table health, effective grants, or business readiness."',
                  '        result["inference_limit"] = "One original remaining batch, same current APK/manifest/signature scope and explicit b05 corrective lineage. The old failed b05 remains failed. Badging does not prove all resource-table health, effective grants, or business readiness."')
    source = source.replace('"ORIGINAL_B05_CORRECTIVE_APK_AUDIT_VERIFIED" if result["linked_batch_audit_complete"] else "ORIGINAL_B05_CORRECTIVE_AUDIT_INCOMPLETE_NO_RETRY"',
                            '"LINKED_ORIGINAL_BATCH_APK_AUDIT_VERIFIED" if result["linked_batch_audit_complete"] else "LINKED_ORIGINAL_BATCH_AUDIT_INCOMPLETE_NO_RETRY"')
    source = source.replace('"pocket4-original-b05-corrective-audit-entry-rejection-v1"', '"pocket4-linked-remaining-audit-entry-rejection-v1"')
    marker = '        result["resource_table_integrity_fully_proved"] = False\n'
    export = '''        # Preserve every full observation losslessly, under the same private store.
        # At 16 APKs the duplicate directory records otherwise exceed MAX_RESULT.
        try:
            if store is not None and "official_private_layout" in result:
                layout = result["official_private_layout"]
                layout_raw = canonical(layout) + b"\\n"
                need(len(layout_raw) <= MAX_RESULT, "FULL_LAYOUT_EVIDENCE_BYTE_BOUND")
                layout_pin = store.write("official-layout-observations.private.json", layout_raw)
                result["official_private_layout"] = {"artifact": layout_pin,
                    "observation_count": len(observations),
                    "all_observations_complete": all(row.get("complete") is True and
                        row.get("all_five_search_directories_and_thirty_candidates_proved") is True for row in observations),
                    "owned_directory_descriptors": layout["owned_directory_descriptors"],
                    "full_original_observations_persisted_and_read_back": True}
            else:
                result["linked_batch_audit_complete"] = False
        except BaseException as error:
            result["errors"].append({"stage": "full_layout_evidence_publication", "type": type(error).__name__, "reason": str(error)[:160]})
            result["all_manifests_and_signatures_verified"] = False
            result["linked_batch_audit_complete"] = False
'''
    source = once(source, marker, export + marker)
    assert "REPAIR_APK_COUNT" not in source and "REPAIR_PACKAGES" not in source and 'request["repair_of"]' not in source
    compile(source, "audit_remaining_batches.py", "exec")
    worker = write("audit_remaining_batches.py", source)
    delta("collector-against-actual-b05.diff", before, source)
    inherited = ["read_bootstrap", "Store", "bind_tools", "recheck_tools", "run_tool", "badging_manifest", "xml_permissions",
                 "parse_signature", "validate_candidate", "verify_candidate_inventory", "verify_actual_proof",
                 "bind_static_dependencies", "recheck_static_aliases", "verify_official_host_proof",
                 "bind_existing_official_layout", "add_official_tool_binding", "all_apk_evidence_verified"]
    assert all(definition(source, name) == definition(before, name) for name in inherited)
    oldwrapper = checked(OLD / "owned_readonly_lifetime.py", 17492, "608f0babd455c535ec6c0876ebfcfbe3dbf229340c498197fc161a08cea30467").decode()
    oldstage = checked(OLD / "stage_and_run_b05_repair.py", 6621, "01cadd78daee01867ba0b7ec56109a93049ca8bb313adfcb51d4ecab51068dcf").decode()
    base_request = json.loads(checked(OLD / "request.review-only.json", 2942, "4457641abbf45499b3431ee8b7d7749389412c71e2fa668ff61dce3b57ecd870"))
    packet_template = json.loads((OLD / "process-request.review-only.json").read_bytes())
    plan_rows = []
    wrapper_functions = [n.name for n in ast.parse(oldwrapper).body if isinstance(n, ast.FunctionDef) and n.name != "worker_gate"]
    for n in range(6, 14):
        batch = batches[str(n)]
        folder = "batch-%02d" % n
        stage_root = "/home/alex/work/pocket4-linked-official-audit-source-20261106-r1-b%02d" % n
        output = "/home/alex/work/pocket4-successor-apk-audit-20261106-linked-official-r1-b%02d" % n
        request = {k: v for k, v in base_request.items() if k != "repair_of"}
        request.update(schema="pocket4-linked-official-remaining-batch-request-v1", packages=batch["packages"], output_root=output,
                       original_batch=n, continuation_of=lineage)
        reqpin = write(folder + "/request.review-only.json", canonical(request))
        remote_req = {"path": stage_root + "/request.review-only.json", "bytes": reqpin["bytes"], "sha256": reqpin["sha256"]}
        remote_worker = {"path": stage_root + "/audit_remaining_batches.py", "bytes": worker["bytes"], "sha256": worker["sha256"]}
        cfg = next(ast.literal_eval(x.value) for x in ast.parse(oldwrapper).body if isinstance(x, ast.Assign) and
                   any(isinstance(t, ast.Name) and t.id == "CONFIG" for t in x.targets))
        cfg.update(stage_root=stage_root, worker=remote_worker, request=remote_req)
        wrapper = assignment(oldwrapper, "CONFIG", cfg)
        gate = definition(wrapper, "worker_gate")
        gate = gate.replace('"pocket4-original-b05-corrective-apk-audit-v1"', '"pocket4-linked-official-remaining-apk-audit-v1"')
        gate = gate.replace('"ORIGINAL_B05_CORRECTIVE_APK_AUDIT_VERIFIED"', '"LINKED_ORIGINAL_BATCH_APK_AUDIT_VERIFIED"')
        gate = gate.replace('"corrective_audit_complete"', '"linked_batch_audit_complete"')
        gate = gate.replace('len(value.get("commands", [])) == 18', 'len(value.get("commands", [])) == ' + str(3 * batch["APK_count"]))
        gate = gate.replace(repr(base_request["packages"]), repr(batch["packages"]))
        first = '        need(value.get("repair_of") == '
        last = '        need(value.get("original_failed_audit_reclassified") is False'
        a, b = gate.index(first), gate.index(last)
        gate = gate[:a] + '''        need(value.get("continuation_of") == ''' + repr(lineage) + ''' and
             value.get("original_batch") == ''' + str(n) + ''' and value.get("request") == ''' + repr(request) + ''' and
             value.get("corrective_publication_reference") == ''' + repr(REPAIR_RESULT) + ''' and
             value.get("legacy_badging_reexecuted") is False, "EXACT_LINKED_ORIGINAL_PENDING_BATCH")
        layout = value.get("official_private_layout", {})
        need(layout.get("observation_count") == ''' + str(2 + 6 * batch["APK_count"]) + ''' and
             layout.get("all_observations_complete") is True and
             layout.get("full_original_observations_persisted_and_read_back") is True and
             layout.get("artifact", {}).get("path") == ''' + repr(output + "/official-layout-observations.private.json") + ''' and
             type(layout["artifact"].get("bytes")) is int and 0 < layout["artifact"]["bytes"] <= 524288 and
             re.fullmatch("[0-9a-f]{64}", layout["artifact"].get("sha256", "")) is not None,
             "COMPLETE_PERSISTED_LAYOUT_OBSERVATIONS_REQUIRED")
''' + gate[b:]
        wrapper = once(wrapper, definition(wrapper, "worker_gate"), gate)
        assert all(definition(wrapper, name) == definition(oldwrapper, name) for name in wrapper_functions)
        compile(wrapper, "owned_readonly_lifetime.py", "exec")
        wp = write(folder + "/owned_readonly_lifetime.py", wrapper)
        files = [{"name": "owned_readonly_lifetime.py", "bytes": wp["bytes"], "sha256": wp["sha256"]},
                 {"name": "audit_remaining_batches.py", "bytes": worker["bytes"], "sha256": worker["sha256"]},
                 {"name": "request.review-only.json", "bytes": reqpin["bytes"], "sha256": reqpin["sha256"]}]
        stage = assignment(assignment(oldstage, "ROOT", stage_root), "FILES", files)
        compile(stage, "stage_and_run.py", "exec")
        sp = write(folder + "/stage_and_run.py", stage)
        payload = {"schema": "pocket4-calendar-official-comparison-source-stage-v1", "files": [
            {"name": "owned_readonly_lifetime.py", "text": wrapper}, {"name": "audit_remaining_batches.py", "text": source},
            {"name": "request.review-only.json", "text": canonical(request).decode()}]}
        stdin = canonical(payload)
        assert len(stdin) <= 262144
        write(folder + "/stage.stdin.original.json", stdin)
        packet = dict(packet_template)
        packet.update(idempotency_key="sidecar-evidence-20261106-linked-official-audit-r1-b%02d" % n,
                      args=packet_template["args"][:-1] + [stage], stdin=stdin.decode())
        pp = write(folder + "/process-request.review-only.json", canonical(packet))
        if n == 6:
            delta("owned-gate-against-actual-b05.diff", oldwrapper, wrapper)
            delta("stager-against-actual-b05.diff", oldstage, stage)
        plan_rows.append({"batch": n, **batch, "output_root": output, "source_root": stage_root,
            "request": remote_req, "local_request_file": reqpin["file"], "collector": remote_worker,
            "wrapper": {"path": stage_root + "/owned_readonly_lifetime.py", "bytes": wp["bytes"], "sha256": wp["sha256"]},
            "local_wrapper_file": wp["file"], "stager": sp, "process_request": pp,
            "suggested_new_idempotency_key": packet["idempotency_key"], "process_limits": {k: packet[k] for k in ("cpu_quota_percent", "memory_max_bytes", "nice", "timeout_seconds")}})
    evidence = [pin(OLD / name) for name in ("audit_original_b05.py", "owned_readonly_lifetime.py", "request.review-only.json",
        "process-request.review-only.json", "actual/start.original.txt", "actual/status-01.original.txt",
        "actual/stdout.original.jsonl", "actual/worker.stdout.original.json")]
    failure = [pin(PROJECT / LEDGER / "batch-05" / name) for name in
               ("intent.json", "submitted-job.json", "terminal.original.json", "stdout.original.json", "artifact.original.json", "gate-status.stdout.original.json")]
    plan = {"schema": "pocket4-original-ledger-linked-b05-repair-continuation-v1", "original_plan": pin(ORIGINAL / "REQUEST_MANIFEST.json"),
        "original_state_dir": LEDGER, "original_failed_b05_preserved": True, "continuation_of": lineage,
        "corrective_evidence": evidence, "original_failed_evidence": failure, "new_collector": worker,
        "guard": base_request["guard"], "app_scope": base_request["app_scope"], "runtime_epoch_sha256": original["runtime_epoch_sha256"],
        "scope_local_file": "successor_audit_requests/explicit47_scope_r2/actual-readback/app-scope.private.json",
        "all_original_pending_package_rows_equal_new_scope": True, "batches": plan_rows,
        "pending_packages": 31, "pending_APK_count": 65, "preserved_original_batches": [1, 2, 3, 4, 5],
        "worker_internal_deadline_seconds": 840, "owned_child_deadline_seconds": 1000,
        "no_claims_or_remote_processes_created_by_assembler": True, "automatic_retry": False,
        "production_ready": False, "effective_permission_grants": "UNKNOWN_NOT_QUERIED"}
    planpin = write("CONTINUATION_PLAN.json", canonical(plan))
    print(json.dumps({"worker": worker, "plan": planpin, "unchanged_worker_definitions": inherited,
                      "unchanged_owned_lifetime_functions": wrapper_functions, "prepared_batches": 8,
                      "runtime_jobs_submitted": 0, "ledger_claims_created": 0}, sort_keys=True))


if __name__ == "__main__":
    main()
