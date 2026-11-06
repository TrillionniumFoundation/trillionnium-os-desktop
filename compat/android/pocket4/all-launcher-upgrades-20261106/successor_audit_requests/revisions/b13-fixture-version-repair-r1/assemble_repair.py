#!/usr/bin/env python3
"""Local source preparation only; preserve the failed b13 and all old gates."""
import sys
sys.dont_write_bytecode = True
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
OLD = HERE.parent / "linked-official-continuation-r2"
FAILED = PROJECT / "successor_audit_requests/actual/batches-final-r1/batch-13"
RAW = PROJECT / "successor_audit_requests/diagnostics/b13-fixture-manifest-raw-readback-r1/actual"
STAGE = "/home/alex/work/pocket4-b13-fixture-version-repair-source-20261106-r1"
OUTPUT_PREFIX = "/home/alex/work/pocket4-successor-apk-audit-20261106-b13-fixture-version-repair-r1-"
OUTPUT = OUTPUT_PREFIX + "b13"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return (json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n").encode()


def checked(path, size, digest):
    raw = path.read_bytes()
    assert len(raw) == size and sha(raw) == digest, path
    return raw


def write(name, raw):
    raw = raw.encode() if isinstance(raw, str) else raw
    path = HERE / name
    if path.exists():
        assert path.read_bytes() == raw, "FROZEN_NEW_FILE_CHANGED: " + name
    else:
        with path.open("xb") as stream:
            stream.write(raw)
    assert path.read_bytes() == raw
    return {"file": name, "bytes": len(raw), "sha256": sha(raw)}


def once(text, old, new):
    assert text.count(old) == 1, old[:150]
    return text.replace(old, new, 1)


def definition(text, name):
    node = next(n for n in ast.parse(text).body if isinstance(n, (ast.FunctionDef, ast.ClassDef)) and n.name == name)
    return ast.get_source_segment(text, node)


def literal(text, name):
    node = next(n for n in ast.parse(text).body if isinstance(n, ast.Assign) and
                any(isinstance(t, ast.Name) and t.id == name for t in n.targets))
    return ast.literal_eval(node.value)


def assignment(text, name, value):
    node = next(n for n in ast.parse(text).body if isinstance(n, ast.Assign) and
                any(isinstance(t, ast.Name) and t.id == name for t in n.targets))
    return once(text, ast.get_source_segment(text, node), name + " = " + repr(value))


def diff(name, before, after):
    return write(name, "".join(difflib.unified_diff(before.splitlines(True), after.splitlines(True),
                 fromfile="original-linked-b13/" + name, tofile="independent-b13-version-repair/" + name)))


def pin_local(path):
    body = path.read_bytes()
    return {"file": str(path.relative_to(PROJECT)), "bytes": len(body), "sha256": sha(body)}


def main():
    old = checked(OLD / "audit_remaining_batches.py", 67206,
                  "e92ee6edc129e0488c7ae13c2c853c804436bcb799f4413f84eab06a529d1e44").decode()
    failed_raw = checked(FAILED / "artifact.original.json", 72536,
                         "db979e50d6bfa1e0c83fd7ae876239b48bdca3b4be80bfb5cce6e24f30948d33")
    failed = json.loads(failed_raw)
    terminal_raw = (FAILED / "terminal.original.json").read_bytes()
    assert sha(terminal_raw) == "0bb294937184c5c01f49e8e344ea2b6396e1b31788c10388220ff11a3db95508"
    terminal = json.loads(terminal_raw)
    assert terminal["job_id"] == "1a1b2ab7980-fc05-7f3a" and terminal["state"] == "failed" and terminal["exit_code"] == 1
    assert all(terminal[k] is True for k in ("output_complete", "output_durable", "terminal_publication_confirmed"))
    assert failed["status"] == "LINKED_ORIGINAL_BATCH_AUDIT_INCOMPLETE_NO_RETRY" and not failed["linked_batch_audit_complete"]
    assert len(failed["commands"]) == 9 and all(c["returncode"] == 0 for c in failed["commands"])
    assert failed["apps"][0]["apks"][0]["parse_errors"] == [{"field": "manifest", "reason": "AAPT_PACKAGE_VERSION_REQUIRED", "type": "RuntimeError"}]
    scope_path = PROJECT / "successor_audit_requests/explicit47_scope_r2/actual-readback/app-scope.private.json"
    scope = json.loads(checked(scope_path, 58854, "44f9ce783000a672c270e98afdaeb74bd79654508bfacae6793316ff4252e52f"))
    fixture = scope["apps"]["local.pocket4.fixture"]
    assert fixture["uid"] == 10115 and fixture["version_code"] == 0 and len(fixture["apks"]) == 1
    badging = {"bytes": 686, "sha256": "28b2cf92369048b078c8fbf337bf8ae08173f49768e946baee8421bb0d0860b5"}
    xml = {"bytes": 1244, "sha256": "2deafdbfa41af5daf85f7980a82491408b1472bcb5aafb0904fa1ea72e9b351f"}
    checked(RAW / "p00-a00-badging.stdout", **{"size": badging["bytes"], "digest": badging["sha256"]})
    checked(RAW / "p00-a00-manifest.stdout", **{"size": xml["bytes"], "digest": xml["sha256"]})
    reference = {"origin": "AOSP primary source, not an assertion of exact live ELF provenance",
        "commit": "13f9d65c456ee75c488b5d5eccdaa277437528ef", "blob": "73df5e8e7b1bbf943a03c852bb5fa1ff8b10fa89",
        "url": "https://android.googlesource.com/platform/frameworks/base.git/+/13f9d65c456ee75c488b5d5eccdaa277437528ef/core/java/com/android/internal/pm/parsing/pkg/PackageImpl.java",
        "symbol": "PackageImpl constructor", "versionCode_default": 0, "versionCodeMajor_default": 0,
        "method": "TypedArray.getInteger(attribute, defaultValue)",
        "versionName_omission_is_null_reference": "https://android.googlesource.com/platform/frameworks/base.git/+/main/core/java/android/content/pm/PackageInfo.java",
        "typed_version_name": "nullable; no invented display name"}
    write("ANDROID_DEFAULT_SEMANTICS.json", canonical(reference))
    old_request_raw = checked(OLD / "batch-13/request.review-only.json", 3318,
                              "675999fa3c72bb7cde1ad50a008a62bc09141ebfd2f0848a11fb6c707bf0ba5b")
    old_request = json.loads(old_request_raw)
    failure = {"job_id": terminal["job_id"], "state": "failed", "exit_code": 1,
        "authoritative_terminal_sha256": sha(terminal_raw), "worker_artifact_bytes": len(failed_raw),
        "worker_artifact_sha256": sha(failed_raw), "failed_publication": failed["final_receipt"],
        "original_request_sha256": sha(old_request_raw), "original_failed_source_sha256": sha(old.encode())}
    constants = "\n".join(name + " = " + repr(value) for name, value in (
        ("FIXTURE_SCOPE", fixture), ("FIXTURE_BADGING_PIN", badging), ("FIXTURE_XML_PIN", xml),
        ("ANDROID_VERSION_DEFAULT_REFERENCE", reference), ("B13_FAILURE_LINEAGE", failure),
        ("B13_FAILED_RESULT", failed["final_receipt"]))) + "\n"
    source = assignment(old, "OUTPUT_PREFIX", OUTPUT_PREFIX)
    source = assignment(source, "PENDING_BATCHES", {"13": literal(old, "PENDING_BATCHES")["13"]})
    begin = source.index('"""'); end = source.index('"""', begin + 3) + 3
    source = source[:begin] + '"""Independent full b13 correction for one exact fixture with absent version attributes.\n\nOriginal b13 remains FAILED. All three current APK sets are reobserved with the\noriginal signatures, tools, guards, layout and owned-lifetime requirements.\nOnly the fixed signed fixture may use the proven Android absent-version default.\nNo APK edit, install, UI, permission change, Android command or old gate update.\n"""' + source[end:]
    source = once(source, "\ndef validate_candidate(candidate):", "\n" + constants + "\ndef validate_candidate(candidate):")
    fragment = (HERE / "fixture_manifest_adapter.fragment.py").read_text()
    source = once(source, "\ndef xml_permissions(raw):", "\n" + fragment + "\n\ndef xml_permissions(raw):")
    source = once(source, '"continuation_of", "original_batch"}', '"continuation_of", "original_batch", "original_b13_failure"}')
    source = source.replace("pocket4-linked-official-remaining-batch-request-v1", "pocket4-independent-b13-fixture-version-repair-request-v1")
    source = source.replace("ONLY_ORIGINAL_UNCLAIMED_BATCHES_06_TO_13", "ONLY_INDEPENDENT_CORRECTION_OF_EXACT_FAILED_BATCH_13")
    source = once(source, 'request["packages"] == batch["packages"] and request["continuation_of"] == CONTINUATION_LINEAGE and',
                  'request["packages"] == batch["packages"] and request["continuation_of"] == CONTINUATION_LINEAGE and\n         request["original_b13_failure"] == B13_FAILURE_LINEAGE and')
    source = source.replace("pocket4-linked-official-remaining-apk-audit-v1", "pocket4-independent-b13-fixture-version-corrective-audit-v1")
    source = once(source, '"original_batch": request["original_batch"],', '"original_batch": request["original_batch"],\n        "original_b13_failure": B13_FAILURE_LINEAGE, "original_batch_13_gate_advanced": False,')
    source = once(source, 'prior_failed_raw = core.pinned_record(ORIGINAL_FAILED_RESULT, MAX_RESULT)',
        'prior_b13_raw = core.pinned_record(B13_FAILED_RESULT, MAX_RESULT)\n        prior_b13 = core.parse(prior_b13_raw)\n        need(prior_b13.get("original_batch") == 13 and prior_b13.get("linked_batch_audit_complete") is False and\n             prior_b13.get("status") == "LINKED_ORIGINAL_BATCH_AUDIT_INCOMPLETE_NO_RETRY", "ORIGINAL_B13_FAILURE_MUST_REMAIN")\n        result["original_b13_failed_publication_reference"] = B13_FAILED_RESULT\n        prior_failed_raw = core.pinned_record(ORIGINAL_FAILED_RESULT, MAX_RESULT)')
    source = once(source, '("manifest", lambda: badging_manifest(outputs["badging"]))',
                  '("manifest", lambda: manifest_with_exact_fixture_default(outputs["badging"], outputs["manifest"], package, row, apk, item.get("signature")))')
    source = once(source, '        core.pinned_record(ORIGINAL_FAILED_RESULT, MAX_RESULT)',
                  '        core.pinned_record(B13_FAILED_RESULT, MAX_RESULT)\n        core.pinned_record(ORIGINAL_FAILED_RESULT, MAX_RESULT)')
    source = source.replace('"linked_batch_audit_complete"', '"corrective_batch13_audit_complete"')
    # The only reference to the prior record must retain that record's schema.
    source = once(source, 'prior_b13.get("corrective_batch13_audit_complete")', 'prior_b13.get("linked_batch_audit_complete")')
    needle = '        result["corrective_batch13_audit_complete"] = (result["all_manifests_and_signatures_verified"] and'
    source = once(source, needle,
        '        fixture_manifest = result["apps"][0].get("base_manifest") if result["apps"] else None\n'
        '        result["fixture_absent_version_default_applied"] = bool(fixture_manifest and\n'
        '            fixture_manifest.get("effective_version_code_source") == "ANDROID_ABSENT_ATTRIBUTE_DEFAULT_CONFIRMED_WITH_FIXED_PM_ZERO" and\n'
        '            fixture_manifest.get("version_code") is None and fixture_manifest.get("version_name") is None and\n'
        '            fixture_manifest.get("version_code_raw") == fixture_manifest.get("version_name_raw") == "" and\n'
        '            fixture_manifest.get("long_version_code") == 0)\n'
        '        result["corrective_batch13_audit_complete"] = (result["fixture_absent_version_default_applied"] and\n'
        '            result["all_manifests_and_signatures_verified"] and')
    source = source.replace('"LINKED_ORIGINAL_BATCH_APK_AUDIT_VERIFIED"', '"B13_FIXTURE_VERSION_CORRECTIVE_AUDIT_VERIFIED"')
    source = once(source, 'else "LINKED_ORIGINAL_BATCH_AUDIT_INCOMPLETE_NO_RETRY"', 'else "B13_FIXTURE_VERSION_CORRECTIVE_AUDIT_INCOMPLETE_NO_RETRY"')
    source = source.replace("pocket4-linked-remaining-audit-entry-rejection-v1", "pocket4-b13-version-repair-entry-rejection-v1")
    source = once(source, '"One original remaining batch, same current APK/manifest/signature scope and explicit b05 corrective lineage. The old failed b05 remains failed. Badging does not prove all resource-table health, effective grants, or business readiness."',
                  '"Independent full correction of the exact failed b13. The original b05 and b13 failures remain unchanged. Only the fixed signed fixture uses Android absent-version default 0 while raw empty values and null declaration stay preserved. This does not prove all resource health, effective grants, business readiness or rewrite the old ledger."')
    compile(source, "audit_fixture_version_repair.py", "exec")
    old_names = [n.name for n in ast.parse(old).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
    unchanged = [name for name in old_names if name not in ("validate_request", "audit", "main")]
    assert all(definition(old, name) == definition(source, name) for name in unchanged)
    wp = write("audit_fixture_version_repair.py", source)
    diff("collector-against-original-linked-b13.diff", old, source)
    request = dict(old_request)
    request.update(schema="pocket4-independent-b13-fixture-version-repair-request-v1", output_root=OUTPUT, original_b13_failure=failure)
    rp = write("request.review-only.json", canonical(request))
    old_wrapper = (OLD / "batch-13/owned_readonly_lifetime.py").read_text()
    config = literal(old_wrapper, "CONFIG")
    config["stage_root"] = STAGE
    config["worker"] = {"path": STAGE + "/audit_fixture_version_repair.py", "bytes": wp["bytes"], "sha256": wp["sha256"]}
    config["request"] = {"path": STAGE + "/request.review-only.json", "bytes": rp["bytes"], "sha256": rp["sha256"]}
    wrapper = assignment(old_wrapper, "CONFIG", config)
    gate = definition(wrapper, "worker_gate")
    request_node = next(n for n in ast.walk(ast.parse(gate)) if isinstance(n, ast.Compare) and isinstance(n.left, ast.Call) and
                        isinstance(n.left.func, ast.Attribute) and n.left.func.attr == "get" and
                        n.left.args and isinstance(n.left.args[0], ast.Constant) and n.left.args[0].value == "request")
    original_dict = ast.get_source_segment(gate, request_node.comparators[0])
    gate = once(gate, original_dict, repr(request))
    gate = gate.replace("pocket4-linked-official-remaining-apk-audit-v1", "pocket4-independent-b13-fixture-version-corrective-audit-v1")
    gate = gate.replace("LINKED_ORIGINAL_BATCH_APK_AUDIT_VERIFIED", "B13_FIXTURE_VERSION_CORRECTIVE_AUDIT_VERIFIED")
    gate = gate.replace('"linked_batch_audit_complete"', '"corrective_batch13_audit_complete", "fixture_absent_version_default_applied"')
    gate = gate.replace(old_request["output_root"] + "/official-layout-observations.private.json", OUTPUT + "/official-layout-observations.private.json")
    gate = once(gate, 'value.get("original_failed_audit_reclassified") is False and value.get("original_batch_05_gate_advanced") is False,',
        'value.get("original_failed_audit_reclassified") is False and value.get("original_batch_05_gate_advanced") is False and\n'
        '             value.get("original_batch_13_gate_advanced") is False and value.get("original_b13_failure") == ' + repr(failure) + ' and\n'
        '             value.get("original_b13_failed_publication_reference") == ' + repr(failed["final_receipt"]) + ',')
    wrapper = once(wrapper, definition(wrapper, "worker_gate"), gate)
    kept_wrapper = [n.name for n in ast.parse(old_wrapper).body if isinstance(n, ast.FunctionDef) and n.name != "worker_gate"]
    assert all(definition(old_wrapper, n) == definition(wrapper, n) for n in kept_wrapper)
    compile(wrapper, "owned_readonly_lifetime.py", "exec")
    op = write("owned_readonly_lifetime.py", wrapper)
    diff("owned-wrapper-against-original-linked-b13.diff", old_wrapper, wrapper)
    files = [{"name": name, "bytes": pin["bytes"], "sha256": pin["sha256"]} for name, pin in
             (("owned_readonly_lifetime.py", op), ("audit_fixture_version_repair.py", wp), ("request.review-only.json", rp))]
    old_stage = (OLD / "batch-13/stage_and_run.py").read_text()
    stage = assignment(assignment(old_stage, "ROOT", STAGE), "FILES", files)
    stage = stage.replace("New exact source/input stage, then one explicit two-APK parser comparison.",
                          "New exact source/input stage, then one independent full three-APK b13 version correction.")
    stage = stage.replace("pocket4-calendar-official-comparison-source-stage-v1", "pocket4-b13-version-repair-source-stage-v1")
    stage = stage.replace("pocket4-calendar-official-comparison-source-stage-result-v1", "pocket4-b13-version-repair-source-stage-result-v1")
    sp = write("stage_and_run.py", stage)
    diff("stager-against-original-linked-b13.diff", old_stage, stage)
    diff("request-against-original-linked-b13.diff", canonical(old_request).decode(), canonical(request).decode())
    payload = {"schema": "pocket4-b13-version-repair-source-stage-v1", "files": [
        {"name": row["name"], "text": (HERE / row["name"]).read_text()} for row in files]}
    payload_raw = canonical(payload)
    assert len(payload_raw) <= 262144
    write("stage.stdin.original.json", payload_raw)
    old_packet = json.loads((OLD / "batch-13/process-request.review-only.json").read_bytes())
    packet = dict(old_packet)
    packet.update(idempotency_key="sidecar-evidence-20261106-b13-fixture-version-correction-r1",
                  args=old_packet["args"][:-1] + [stage], stdin=payload_raw.decode())
    pp = write("process-request.review-only.json", canonical(packet))
    plan = {"schema": "pocket4-independent-b13-fixture-version-repair-plan-v1", "source_only": True, "remote_jobs": 0,
        "original_b13_failure": failure, "request": {"path": STAGE + "/request.review-only.json", "bytes": rp["bytes"], "sha256": rp["sha256"]},
        "request_local": rp, "collector": config["worker"], "wrapper": {"path": STAGE + "/owned_readonly_lifetime.py", "bytes": op["bytes"], "sha256": op["sha256"]},
        "stager": sp, "process_request": pp, "stage_files": files, "source_root": STAGE, "output_root": OUTPUT,
        "package_count": 3, "APK_count": 3, "APK_bytes": 108766, "primary_commands_required": 9, "official_layout_observations_required": 20,
        "full47_scope_is_fixed_reference": True, "actual_bound_packages": request["packages"], "all47_reobserved_by_this_worker": False,
        "preserved_collector_definitions": unchanged, "preserved_owned_wrapper_definitions": kept_wrapper,
        "input_references": [pin_local(OLD / "audit_remaining_batches.py"), pin_local(OLD / "batch-13/owned_readonly_lifetime.py"),
            pin_local(OLD / "batch-13/stage_and_run.py"), pin_local(OLD / "batch-13/request.review-only.json"),
            pin_local(FAILED / "artifact.original.json"), pin_local(FAILED / "stdout.original.jsonl"), pin_local(FAILED / "terminal.original.json"),
            pin_local(FAILED / "gate-status.stdout.original.json"), pin_local(scope_path), pin_local(RAW / "p00-a00-badging.stdout"), pin_local(RAW / "p00-a00-manifest.stdout")],
        "baseline_old_gate_kept_STOP": True, "completion_requires_new_actual_outer_and_durable_terminal": True,
        "source_parser_controls_do_not_verify_fresh_runtime_signature": True, "production_ready": False}
    mp = write("REPAIR_PLAN.json", canonical(plan))
    print(json.dumps({"plan": mp, "worker": wp, "wrapper": op, "request": rp, "packet": pp,
                      "preserved_collector_definitions": len(unchanged), "preserved_owned_definitions": len(kept_wrapper), "remote_jobs": 0}, indent=2))


if __name__ == "__main__":
    main()
