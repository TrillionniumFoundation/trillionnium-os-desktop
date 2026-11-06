#!/usr/bin/env python3
"""Local controls using actual receipts; never import a Main runtime entry."""
import ast
import base64
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import zlib
sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def rejected(fn, reason):
    try:
        fn()
    except RuntimeError as error:
        assert str(error) == reason, (str(error), reason)
    else:
        raise AssertionError("EXPECTED_REJECTION: " + reason)


def snapshot(path):
    return {str(p.relative_to(path)): digest(p.read_bytes()) for p in path.rglob("*") if p.is_file()}


def main():
    before_fds = len(os.listdir("/proc/self/fd"))
    ledger = PROJECT / "successor_audit_requests/actual/batches-final-r1"
    ledger_before = snapshot(ledger)
    gate = load(HERE / "linked_audit_gate.py", "linked_gate_local_controls")
    plan_raw = (HERE / "CONTINUATION_PLAN.json").read_bytes()
    plan_sha = digest(plan_raw)
    g, plan, original, old_requests, scope, requests, wrappers = gate.load_plan(HERE / "CONTINUATION_PLAN.json", plan_sha)
    cases = []
    decision = gate.inspect(g, plan, plan_sha, original, old_requests, scope, requests, wrappers)
    assert decision["state"] == "NEXT_READY_AFTER_VERIFIED_ORIGINAL_B05_CORRECTION" and decision["next"]["batch"] == 6
    assert decision["original_b05_and_independent_correction"]["original_state"] == "FAILED_PRESERVED"
    assert not (ledger / "batch-06").exists()
    cases.append({"name": "actual_original_history_and_independent_full_correction_yield_only_unclaimed_b06", "passed": True})
    rejected(lambda: g.inspect(original, old_requests, gate.ORIGINAL_PLAN_SHA, ledger),
             "AUTHORITATIVE_SUCCESSFUL_DURABLE_TERMINAL_REQUIRED")
    cases.append({"name": "original_gate_still_rejects_unchanged_failed_b05", "passed": True})

    actual = PROJECT / gate.REPAIR / "actual"
    raw = (actual / "stdout.original.jsonl").read_bytes()
    terminal = g.parse((actual / "status-01.original.txt").read_bytes())
    no_terminal = dict(terminal, output_durable=False)
    rejected(lambda: gate.terminal_gate(g, no_terminal, gate.REPAIR_JOB, raw), "EXACT_DURABLE_TERMINAL_REQUIRED")
    rejected(lambda: gate.terminal_gate(g, terminal, gate.FAILED_JOB, raw), "EXACT_DURABLE_TERMINAL_REQUIRED")
    cases.append({"name": "unknown_or_wrong_job_terminal_cannot_settle_correction", "passed": True})

    old = PROJECT / gate.REPAIR
    wrapper = load(old / "owned_readonly_lifetime.py", "actual_owned_source_local_controls")
    stage, outer = (g.parse(line) for line in raw.splitlines())
    changed = copy.deepcopy(outer)
    changed["child_result"]["final_descriptors"]["3"]["fstat"]["st_ino"] += 1
    child_raw = g.canonical(changed["child_result"]) + b"\n"
    changed["child_stdout"].update(bytes=len(child_raw), sha256=digest(child_raw))
    changed_raw = g.canonical(stage) + b"\n" + g.canonical(changed) + b"\n"
    changed_terminal = copy.deepcopy(terminal)
    changed_terminal["log_bytes"]["stdout"] = {"seen": len(changed_raw), "stored": len(changed_raw)}
    rejected(lambda: gate.owned_gate(g, changed_raw, changed_terminal, gate.REPAIR_JOB, wrapper,
                                    stage["files"], stage["source_root"]), "FULL_DESCRIPTOR_IDENTITIES_AND_NO_MANUAL_CLOSE_REQUIRED")
    cases.append({"name": "same_descriptor_count_but_replaced_library_inode_is_rejected", "passed": True,
                  "mutations_are_in_memory_negative_fixtures_only": True})

    result = g.parse((actual / "worker.stdout.original.json").read_bytes())
    request = result["request"]
    source = {"bytes": 62604, "sha256": gate.sha((old / "audit_original_b05.py").read_bytes())}
    incomplete = copy.deepcopy(result)
    incomplete["apps"][1]["apks"].pop()
    rejected(lambda: gate.complete_apk_gate(g, incomplete, request, 6, 341931165, scope, source),
             "EVERY_ORIGINAL_BASE_AND_SPLIT_REQUIRED")
    changed_scope = copy.deepcopy(scope)
    changed_scope["apps"][request["packages"][0]]["uid"] += 1
    rejected(lambda: gate.complete_apk_gate(g, result, request, 6, 341931165, changed_scope, source),
             "COMPLETE_ACTUAL_APK_UID_DATA_SCOPE_CHANGED")
    cases.append({"name": "missing_split_or_changed_UID_is_not_corrective_coverage", "passed": True})

    full_layout = result["official_private_layout"]
    layout_raw = g.canonical(full_layout) + b"\n"
    packed = copy.deepcopy(result)
    packed["official_private_layout"] = {
        "artifact": {"path": request["output_root"] + "/official-layout-observations.private.json",
                     "bytes": len(layout_raw), "sha256": digest(layout_raw)},
        "encoding": "zlib-base64", "data": base64.b64encode(zlib.compress(layout_raw, 9)).decode(),
        "observation_count": 38, "all_observations_complete": True,
        "owned_directory_descriptors": full_layout["owned_directory_descriptors"],
        "full_original_observations_persisted_and_read_back": True}
    gate.layout_gate(g, packed, 6, True)
    bad_layout = copy.deepcopy(full_layout)
    bad_layout["observations"][0]["directories"][2]["missing_needed"][0]["outcome"] = "PRESENT"
    changed_raw = g.canonical(bad_layout) + b"\n"
    malformed = copy.deepcopy(packed)
    malformed["official_private_layout"]["artifact"].update(bytes=len(changed_raw), sha256=digest(changed_raw))
    malformed["official_private_layout"]["data"] = base64.b64encode(zlib.compress(changed_raw, 9)).decode()
    rejected(lambda: gate.layout_gate(g, malformed, 6, True), "FIVE_SEARCH_DIRECTORIES_THIRTY_TRUE_ENOENT_REQUIRED")
    projected = copy.deepcopy(full_layout)
    projected["observations"] = [copy.deepcopy(full_layout["observations"][i % 38]) for i in range(98)]
    projected_raw = g.canonical(projected) + b"\n"
    assert len(projected_raw) <= 524288
    cases.append({"name": "lossless_actual_layout_encoding_and_missing_library_check_preserved", "passed": True,
        "actual_38_observation_bytes": len(layout_raw), "actual_compressed_base64_bytes": len(packed["official_private_layout"]["data"]),
        "98_observation_capacity_fixture_bytes": len(projected_raw), "capacity_fixture_is_not_runtime_evidence": True})

    collector = load(HERE / "audit_remaining_batches.py", "pending_collector_validation_only")
    for request in requests.values():
        collector.validate_request(request)
    wrong = copy.deepcopy(requests[6]); wrong["original_batch"] = 5
    rejected(lambda: collector.validate_request(wrong), "ONLY_ORIGINAL_UNCLAIMED_BATCHES_06_TO_13")
    wrong = copy.deepcopy(requests[6]); wrong["packages"] = requests[7]["packages"]
    rejected(lambda: collector.validate_request(wrong), "EXACT_LINKED_ORIGINAL_BATCH_SCOPE_REQUIRED")
    old_text = (old / "audit_original_b05.py").read_text()
    new_text = (HERE / "audit_remaining_batches.py").read_text()
    def defs(text):
        return {n.name: ast.get_source_segment(text, n) for n in ast.parse(text).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    original_defs, new_defs = defs(old_text), defs(new_text)
    preserved = ["read_bootstrap", "Store", "bind_tools", "recheck_tools", "run_tool", "badging_manifest", "xml_permissions",
                 "parse_signature", "validate_candidate", "verify_candidate_inventory", "verify_actual_proof", "bind_static_dependencies",
                 "recheck_static_aliases", "verify_official_host_proof", "bind_existing_official_layout", "add_official_tool_binding",
                 "all_apk_evidence_verified"]
    assert all(original_defs[n] == new_defs[n] for n in preserved)
    cases.append({"name": "eight_exact_requests_and_inherited_17_definitions_preserved", "passed": True,
                  "request_count": 8, "inherited_definitions": preserved})
    assert snapshot(ledger) == ledger_before
    after_fds = len(os.listdir("/proc/self/fd"))
    assert before_fds == after_fds
    report = {"schema": "pocket4-linked-original-audit-local-controls-v1", "ok": True, "cases": cases,
              "plan_sha256": plan_sha, "gate_sha256": digest((HERE / "linked_audit_gate.py").read_bytes()),
              "collector_sha256": digest((HERE / "audit_remaining_batches.py").read_bytes()),
              "FDs_before": before_fds, "FDs_after": after_fds, "original_ledger_all_file_hashes_unchanged": True,
              "original_b05_still_failed": True, "new_claims": 0, "remote_jobs": 0, "Android_commands": 0,
              "tool_executions": 0, "UI_actions": 0, "permissions_changed": 0, "production_ready": False}
    for name, body in (("LOCAL_CONTROLS.actual.json", g.canonical(report) + b"\n"),
                       ("ACTUAL_LOCAL_STATUS.original.json", g.canonical(decision) + b"\n")):
        with (HERE / name).open("xb") as out:
            out.write(body)
    print(json.dumps(report, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
