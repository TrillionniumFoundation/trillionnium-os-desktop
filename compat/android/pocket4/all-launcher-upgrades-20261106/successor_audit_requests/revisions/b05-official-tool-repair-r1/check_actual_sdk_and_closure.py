#!/usr/bin/env python3
"""Actual raw SDK-format checks and local closure; no runtime or APK execution."""
import ast
import hashlib
import json
import os
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[2]
OLD = PROJECT / "successor_audit_requests/diagnostics/calendar-official-aapt2-comparison-r1"
RAW = PROJECT / "successor_audit_requests/diagnostics/calendar-official-aapt2-raw-readback-r1/actual"
PINS = {
    "p00-a00-badging.stdout": (5786, "42a73692b7d066a9d0aa6572f0d2a70d8b6365c9a874229f05a8ba43c32eabcc"),
    "p00-a00-manifest.stdout": (20129, "231279b8faaadaa39a043e2001cca6e8e0c11e2d563bbdd0a0675b4b528e8150"),
    "p01-a00-badging.stdout": (4520, "a84428e59d5c538f2348d0e27c739494081eef9b82b32bd2f1aafd33d93d0e34"),
    "p01-a00-manifest.stdout": (12000, "0b10dd310ce5e142c3636fb537e136c790a7f830686d0061eb86665d1fdc6350"),
}


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pinned(path, size, digest):
    raw = path.read_bytes()
    assert (len(raw), sha(raw)) == (size, digest)
    return raw


def definitions(text):
    return {n.name: ast.get_source_segment(text, n) for n in ast.parse(text).body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}


def load(text, path):
    module = {"__name__": "local_definitions_only", "__file__": str(path)}
    exec(compile(text, str(path), "exec"), module)
    return module


def direct_xml_sdk(raw):
    """Inspect only the actual direct uses-sdk block; never a permission maxSdk."""
    stack, current, values, seen = [], False, {}, 0
    for line in raw.decode().splitlines():
        event = re.match(r"^(\s*)E: ([A-Za-z0-9_.:-]+)(?:\s|$)", line)
        if event:
            indent, tag = len(event[1]), event[2]
            while stack and stack[-1][0] >= indent:
                stack.pop()
            parent = stack[-1][1] if stack else None
            stack.append((indent, tag))
            current = tag == "uses-sdk" and parent == "manifest"
            if current:
                seen += 1
            continue
        if current:
            attr = re.fullmatch(r"\s+A: android:(minSdkVersion|targetSdkVersion|maxSdkVersion)\(0x[0-9a-fA-F]+\)=\(type 0x10\)0x([0-9a-fA-F]+)", line)
            if attr:
                assert attr[1] not in values
                values[attr[1]] = str(int(attr[2], 16))
    assert seen == 1
    return values


def main():
    before = len(os.listdir("/proc/self/fd"))
    old_raw = pinned(OLD / "diagnose_calendar_and_fcitx.py", 62331, "191692dda06eaaaa3fcbe024399985cf2ac6a547b567fd25967c96a1b31b09f6")
    new_raw = pinned(ROOT / "audit_original_b05.py", 62604, "b4d27e1364feb28cab6634c77ed764e15359720025192117ecc8cb84d4391e1a")
    old, new = old_raw.decode(), new_raw.decode()
    old_functions, new_functions = definitions(old), definitions(new)
    changed = {name for name in old_functions if old_functions[name] != new_functions[name]}
    assert changed == {"badging_manifest", "clean_official_badging_observations", "validate_request", "all_apk_evidence_verified", "audit", "main"}
    legacy_collector = (PROJECT / "successor_audit_requests/reference/audit_successor_apks.py").read_text()
    assert new_functions["all_apk_evidence_verified"] == definitions(legacy_collector)["all_apk_evidence_verified"]
    frozen_names = ("read_bootstrap", "Store", "bind_tools", "recheck_tools", "run_tool", "xml_permissions", "parse_signature",
                    "validate_candidate", "verify_candidate_inventory", "verify_actual_proof", "bind_static_dependencies",
                    "recheck_static_aliases", "verify_official_host_proof", "bind_existing_official_layout", "add_official_tool_binding")
    assert all(old_functions[name] == new_functions[name] for name in frozen_names)
    old_module, new_module = load(old, OLD / "diagnose_calendar_and_fcitx.py"), load(new, ROOT / "audit_original_b05.py")
    raw_files = {name: pinned(RAW / name, *pin) for name, pin in PINS.items()}
    actual = []
    for suffix, expected in (("00", ("37", "34")), ("01", ("23", "36"))):
        badging = raw_files["p" + suffix + "-a00-badging.stdout"]
        xml = raw_files["p" + suffix + "-a00-manifest.stdout"]
        parsed = new_module["badging_manifest"](badging)
        previous = old_module["badging_manifest"](badging)
        sdk = direct_xml_sdk(xml)
        assert previous["min_sdk"] is None
        assert (parsed["min_sdk"], parsed["target_sdk"]) == expected
        assert parsed["min_sdk"] == sdk["minSdkVersion"] and parsed["target_sdk"] == sdk["targetSdkVersion"]
        assert parsed["max_sdk"] is None and "maxSdkVersion" not in sdk
        actual.append({"package": parsed["package"], "min_sdk": parsed["min_sdk"], "target_sdk": parsed["target_sdk"],
                       "max_sdk": None, "old_original_parser_min_sdk": None, "matches_actual_direct_uses_sdk_XML": True,
                       "no_minimum_le_target_constraint_added": True, "badging_input": PINS["p" + suffix + "-a00-badging.stdout"],
                       "XML_input": PINS["p" + suffix + "-a00-manifest.stdout"]})
    raw = raw_files["p00-a00-badging.stdout"]
    original_line = b"minSdkVersion:'37'\n"
    assert raw.count(original_line) == 1
    derived_old = raw.replace(original_line, b"sdkVersion:'37'\n", 1)
    assert new_module["badging_manifest"](derived_old)["min_sdk"] == "37"
    assert new_module["badging_manifest"](raw.replace(original_line, b"", 1))["min_sdk"] is None
    mutations = [
        ("duplicate_minSdkVersion", original_line + original_line),
        ("duplicate_legacy_sdkVersion", b"sdkVersion:'37'\nsdkVersion:'37'\n"),
        ("two_aliases_same_value", original_line + b"sdkVersion:'37'\n"),
        ("two_aliases_conflicting_values", original_line + b"sdkVersion:'23'\n"),
        ("suffix_garbage", b"minSdkVersion:'37' trailing\n"),
        ("extra_quoted_value", b"minSdkVersion:'37' '1'\n"),
        ("present_but_empty", b"minSdkVersion:''\n"),
    ]
    rejected = []
    for name, line in mutations:
        try:
            new_module["badging_manifest"](raw.replace(original_line, line, 1))
        except RuntimeError as error:
            rejected.append({"derived_negative_fixture": name, "rejected": True, "reason": str(error)})
        else:
            raise AssertionError(name)
    scope_path = PROJECT / "successor_audit_requests/explicit47_scope_r2/actual-readback/app-scope.private.json"
    scope = json.loads(pinned(scope_path, 58854, "44f9ce783000a672c270e98afdaeb74bd79654508bfacae6793316ff4252e52f"))
    old_result = json.loads(pinned(PROJECT / "successor_audit_requests/actual/batches-final-r1/batch-05/artifact.original.json",
                                  108564, "e8fb751780f88ba3d79cb51f5975f5426d1cd6df586563d035824b3b69789d10"))
    expected = {package: scope["apps"][package] for package in new_module["REPAIR_PACKAGES"]}
    for previous in old_result["apps"]:
        current = expected[previous["package"]]
        assert previous["uid"] == current["uid"] and previous["PM_version_code"] == current["version_code"]
        assert previous["code_path"] == current["code_path"] and previous["data_directories"] == current["data_directories"]
        assert previous["PM_certificate_sha256"] == current["package_manager_certificate_sha256"]
        projection = lambda apks: sorted([{k: x[k] for k in ("path", "bytes", "sha256", "file")} for x in apks], key=lambda x: x["path"])
        assert projection(previous["apks"]) == projection(current["apks"])
    assert sum(len(row["apks"]) for row in expected.values()) == 6
    assert sum(apk["bytes"] for row in expected.values() for apk in row["apks"]) == 341931165
    request = json.loads((ROOT / "request.review-only.json").read_bytes())
    new_module["validate_request"](request)
    old_wrapper = (OLD / "owned_readonly_lifetime.py").read_text()
    wrapper = (ROOT / "owned_readonly_lifetime.py").read_text()
    wf_old, wf_new = definitions(old_wrapper), definitions(wrapper)
    assert {name for name in wf_old if wf_old[name] != wf_new[name]} == {"worker_gate"}
    module = load(wrapper, ROOT / "owned_readonly_lifetime.py")
    diagnostic = json.loads(pinned(OLD / "actual/worker.stdout.original.json", 132387,
                                  "8e577c9e4a6eb77e6ad94e9993ca91aa97af958a4c02491237b32600dd6f4dfe"))
    try:
        module["worker_gate"](diagnostic, 0)
    except RuntimeError as error:
        diagnostic_rejection = {"actual_two_package_diagnostic_rejected_as_b05": True, "reason": str(error)}
    else:
        raise AssertionError("two-package diagnostic cannot satisfy full b05")
    packet = json.loads((ROOT / "process-request.review-only.json").read_bytes())
    stage = (ROOT / "stage_and_run_b05_repair.py").read_text()
    compile(stage, "stage_and_run_b05_repair.py", "exec")
    assert packet["args"][-1] == stage and packet["stdin"].encode() == (ROOT / "stage.stdin.original.json").read_bytes()
    payload = json.loads(packet["stdin"])
    stage_files = ast.literal_eval(next(node.value for node in ast.parse(stage).body if isinstance(node, ast.Assign)
                                   and any(isinstance(target, ast.Name) and target.id == "FILES" for target in node.targets)))
    assert len(stage_files) == len(payload["files"]) == 3
    assert payload["schema"] == "pocket4-calendar-official-comparison-source-stage-v1"
    for expected_file, item in zip(stage_files, payload["files"]):
        content = item["text"].encode()
        assert item["name"] == expected_file["name"]
        assert (len(content), sha(content)) == (expected_file["bytes"], expected_file["sha256"])
        assert content == (ROOT / item["name"]).read_bytes()
    after = len(os.listdir("/proc/self/fd"))
    assert before == after
    result = {"schema": "pocket4-b05-corrective-sdk-and-closure-local-controls-v1", "ok": True,
              "actual_SDK_observations": actual, "derived_legacy_label_compatibility_passed": True,
              "absent_SDK_line_remains_None": True, "negative_SDK_fixtures": rejected,
              "exact_unchanged_tool_integrity_reader_and_runner_definitions": list(frozen_names),
              "changed_collector_functions": sorted(changed), "all_other_owned_lifetime_functions_unchanged": True,
              "original_four_packages_six_APKs_match_actual47_complete_identity": True, "logical_APK_bytes": 341931165,
              "primary_commands_expected": 18, "layout_verifications_expected": 38,
              "actual_diagnostic_gate_negative": diagnostic_rejection,
              "three_exact_stage_files_and_packet_verified": True,
              "local_process_FDs_before": before, "local_process_FDs_after": after,
              "Main_reads": 0, "APK_reads": 0, "tool_children_executed": 0, "runtime_jobs_submitted": 0,
              "original_b05_gate_advanced": False, "production_ready": False}
    out = (json.dumps(result, sort_keys=True, indent=2, ensure_ascii=True) + "\n").encode()
    with (ROOT / "LOCAL_CONTROLS.actual.json").open("xb") as handle:
        handle.write(out)
    print(json.dumps({"ok": True, "bytes": len(out), "sha256": sha(out)}, sort_keys=True))


if __name__ == "__main__":
    main()
