#!/usr/bin/env python3
"""Create a separate, review-only diagnostic from the preserved r1 draft."""
from pathlib import Path
import ast
import difflib
import hashlib
import json
import os

ROOT = Path(__file__).resolve().parent
BASE = ROOT.parents[1]
PROOF = BASE / "diagnostics/aapt2-provenance-interface-r1/candidate-r2/actual"
INV = BASE / "diagnostics/aapt2-candidate-inventory-r1"
STAGE = "/home/alex/work/pocket4-calendar-aapt2-diagnostic-source-20261106-r2"


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def save(path, raw):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        assert path.read_bytes() == raw, "REFUSE_EXISTING_DIFFERENT_FILE"
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as out:
        out.write(raw)
        out.flush()
        os.fsync(out.fileno())


def main():
    old = (ROOT / "diagnose_calendar_with_observed_aapt2.py").read_bytes()
    assert len(old) == 36675 and digest(old) == "bd8119e8eed6fd5119de9dadac0c668c7eb485520189c216bdc123fa9bebb290"
    text = old.decode()

    def change(before, after):
        nonlocal text
        assert text.count(before) == 1, ("PATCH_COUNT", before[:80], text.count(before))
        text = text.replace(before, after)

    proof_raw = (PROOF / "artifact.original.json").read_bytes()
    terminal_raw = (PROOF / "terminal.original.json").read_bytes()
    assert len(proof_raw) == 54192 and digest(proof_raw) == "f9c289f7d28f836c51d845b4c851c1dbac0e8f326d658c7b98106b6ee327f192"
    assert len(terminal_raw) == 730 and digest(terminal_raw) == "f797f008a250a386ca905e9b7e9065ac2f85cad2168be702c3ad01209d341802"
    actual = json.loads(proof_raw)
    candidate = actual["candidate"]
    change('Candidate source for review only until the actual tool inventory and interface\nare reviewed and a fresh exact request is sealed. The old b05 failure stays\nunchanged. Aapt2 replaces badging only; the original Java signature verifier\nand aapt XML reader, typed guard, held APK/data checks, action lock, and all\nresource retirement requirements remain in force. No Android command or UI.',
           'Independent comparison of two exact APKs, using the actual observed Debian\nAAPT2 version/help/dependency evidence. The prior host help job remains failed\n(exit 1); it is not reclassified. Original aapt badging is retained as a\ncomparison alongside new aapt2 badging, the original signature verifier and\nXML reader. Typed runtime/held APK/data, lock and retirement requirements\nremain in force. No Android command, UI, grant, install or original gate change.')
    change('calendar-aapt2-diagnostic-"', 'calendar-aapt2-comparison-r2-"')
    start = text.index('CANDIDATE_PATHS = (')
    end = text.index('ORIGINAL_FAILED_RESULT =', start)
    text = text[:start] + ('ACTUAL_CANDIDATE = ' + repr(candidate) + '\n'
        + 'ACTUAL_PROOF = ' + repr({"path": STAGE + "/inputs/aapt2-proof.outer.original.json", "bytes": len(proof_raw), "sha256": digest(proof_raw)}) + '\n'
        + 'ACTUAL_PROOF_TERMINAL = ' + repr({"path": STAGE + "/inputs/aapt2-proof.terminal.original.json", "bytes": len(terminal_raw), "sha256": digest(terminal_raw)}) + '\n'
        + 'PROOF_JOB = "1a1b1cdd0e7-fc05-7ae1"\n') + text[end:]
    change('need(candidate["path"] in CANDIDATE_PATHS and type(candidate["bytes"]) is int and 0 < candidate["bytes"] <= 64 * 1024 * 1024, "REVIEWED_HOST_CANDIDATE_BOUND")',
           'need(candidate == ACTUAL_CANDIDATE, "EXACT_ACTUAL_CANDIDATE_BYTES_AND_INTEGER_STAT_REQUIRED")')
    extra = '''
def verify_actual_proof(proof, terminal, candidate):
    """Use exact observed facts; the old exit-1 help job remains failed."""
    validate_candidate(candidate)
    need(proof.get("schema") == "pocket4-existing-dpkg-aapt2-host-proof-and-interface-v1", "ACTUAL_PROOF_SCHEMA")
    need(proof.get("candidate") == candidate, "PROOF_CANDIDATE_DIFFERS")
    need(terminal.get("job_id") == PROOF_JOB and terminal.get("state") == "failed" and terminal.get("exit_code") == 1,
         "PRESERVE_ACTUAL_FAILED_HELP_JOB")
    need(all(terminal.get(key) is True for key in ("output_complete", "output_durable", "terminal_publication_confirmed")),
         "PROOF_AUTHORITATIVE_TERMINAL_REQUIRED")
    need(all(terminal.get(key) is False for key in ("automatic_retry", "timed_out", "cancelled")), "PROOF_TERMINAL_NOT_SETTLED")
    need(terminal.get("log_truncated") == {"stdout": False, "stderr": False} and
         terminal.get("log_errors") == {"stdout": None, "stderr": None} and
         terminal.get("log_synced") == {"stdout": True, "stderr": True}, "PROOF_LOG_COMPLETENESS")
    need(proof.get("ok") is False and proof.get("status") == "HOST_PROOF_OR_INTERFACE_INCOMPLETE_NO_RETRY" and
         proof.get("errors") == [], "ORIGINAL_PROOF_FAILURE_MUST_REMAIN")
    need(proof.get("process_FDs_before") == proof.get("process_FDs_after") == 4 and
         proof.get("all_owned_tool_children_joined") is True and proof.get("all_bound_host_files_unchanged") is True,
         "PROOF_IDENTITY_OR_RETIREMENT_INCOMPLETE")
    need(proof.get("installed_dpkg_candidate_membership_and_checksum_match") is True,
         "ACTUAL_DPKG_MEMBERSHIP_CHECKSUM_REQUIRED")
    need(all(type(proof.get(key)) is int and proof[key] == 0 for key in
         ("APK_reads", "APK_tool_inputs", "Android_commands", "App_launches", "Main_reads", "UI_actions", "installs",
          "namespace_entries", "native_commands", "permission_changes")) and proof.get("action_lock_acquired") is False,
         "PROOF_ACTION_BOUNDARY_CHANGED")
    commands = proof.get("commands")
    need(type(commands) is list and len(commands) == 2 and proof.get("candidate_executions") == 2, "EXACT_TWO_HOST_COMMANDS")
    for command, tail, code in zip(commands, (["version"], ["dump", "badging", "--help"]), (0, 1)):
        need(command.get("argv") == [candidate["path"], *tail] and command.get("returncode") == code,
             "ACTUAL_INTERFACE_COMMAND_DIFFERS")
        need(command.get("joined") is True and command.get("pipes_closed") is True and
             command.get("output_capture_complete") is True and command.get("timed_out") is False and
             not command.get("error") and not command.get("retirement_error"), "PROOF_CHILD_NOT_SETTLED")
        for stream in ("stdout", "stderr"):
            raw = bytes.fromhex(command[stream + "_original_hex"])
            need(len(raw) == command[stream]["bytes"] and sha(raw) == command[stream]["sha256"], "PROOF_LOG_PIN_CHANGED")
    need(commands[1]["stderr"]["bytes"] == 199 and commands[1]["stderr"]["sha256"] ==
         "c5fb01d0065654135344c1ba9a082c3524363d154fec18f114e0dfef5caa711b", "EXACT_ACTUAL_BADGING_USAGE_REQUIRED")
    graph = proof.get("static_dependency_graph")
    need(type(graph) is list and len(graph) == proof.get("static_dependency_file_count") == 19,
         "ACTUAL_NINETEEN_FILE_STATIC_GRAPH_REQUIRED")
    need(len({row["file"]["resolved_path"] for row in graph}) == len(graph), "STATIC_FILE_PATH_NOT_UNIQUE")
    need(all(row["static_elf"]["additional_loader_directives"] == [] for row in graph), "UNREVIEWED_LOADER_DIRECTIVE")
    return {"job_id": PROOF_JOB, "prior_job_state": "failed", "prior_job_exit_code": 1,
            "prior_job_reclassified": False, "version_returncode": 0, "help_returncode": 1,
            "actual_usage_observed": True, "dpkg_membership_and_checksum_observed": True,
            "distribution_signature_reverified": False, "static_graph_is_runtime_loader_proof": False}


def bind_static_dependencies(core, pool, rows, end, proof):
    aliases = []
    for index, item in enumerate(proof["static_dependency_graph"]):
        need(time.monotonic() < end, "DIAGNOSTIC_DEADLINE_BEFORE_DEPENDENCY_BIND")
        pin = item["file"]
        need(str(Path(pin["declared_path"]).resolve()) == pin["resolved_path"], "ACTUAL_STATIC_DEPENDENCY_RESOLUTION_CHANGED")
        fd = core.open_host(pool, pin["resolved_path"])
        value = core.hash_fd(fd, 512 * 1024 * 1024, min(end, time.monotonic() + 45))
        need(value == {key: pin[key] for key in ("bytes", "sha256", "file")}, "ACTUAL_STATIC_DEPENDENCY_BYTES_OR_STAT_CHANGED")
        rows["aapt2-static-" + str(index)] = {"pin": pin, "fd": fd, "observed": value}
        aliases.extend(item.get("resolved_needed", []))
        if item.get("resolved_interpreter") is not None:
            aliases.append(item["resolved_interpreter"])
    recheck_static_aliases(aliases, end)
    return aliases


def recheck_static_aliases(aliases, end):
    for pin in aliases:
        need(time.monotonic() < end, "DIAGNOSTIC_DEADLINE_BEFORE_ALIAS_RECHECK")
        need(str(Path(pin["declared_path"]).resolve()) == pin["resolved_path"], "ACTUAL_LOADER_ALIAS_CHANGED")

'''
    change('\n\ndef need(value, reason):', '\n\n' + extra + '\ndef need(value, reason):')
    change('    for row in rows.values():\n        pin, expected, fd', '    for row in rows.values():\n        need(time.monotonic() < end, "DIAGNOSTIC_DEADLINE_BEFORE_TOOL_RECHECK")\n        pin, expected, fd')
    change('"output_root", "official_release_assets", "candidate_aapt2", "candidate_inventory"}',
           '"output_root", "official_release_assets", "candidate_aapt2", "candidate_inventory", "candidate_proof", "candidate_terminal"}')
    change('request["schema"] == "pocket4-independent-calendar-aapt2-diagnostic-request-v1"', 'request["schema"] == "pocket4-independent-calendar-aapt2-comparison-request-v2"')
    change('    validate_candidate(request["candidate_aapt2"])', '    validate_candidate(request["candidate_aapt2"])\n    need(request["candidate_proof"] == ACTUAL_PROOF and request["candidate_terminal"] == ACTUAL_PROOF_TERMINAL, "EXACT_ACTUAL_PROOF_PINS_REQUIRED")')
    change('result.get("all_commands_succeeded") is True', 'result.get("all_primary_commands_succeeded") is True')
    change('"schema": "pocket4-independent-calendar-aapt2-resource-diagnostic-v1"', '"schema": "pocket4-independent-calendar-aapt2-resource-comparison-v2"')
    change('        inventory_raw = core.pinned_record(request["candidate_inventory"], 65536)',
           '        proof_raw = core.pinned_record(request["candidate_proof"], 131072)\n        terminal_raw = core.pinned_record(request["candidate_terminal"], 65536)\n        proof = core.parse(proof_raw)\n        result["actual_prior_host_proof"] = verify_actual_proof(proof, core.parse(terminal_raw), request["candidate_aapt2"])\n        inventory_raw = core.pinned_record(request["candidate_inventory"], 65536)')
    change('        tools = bind_tools(core, pool, end, request["candidate_aapt2"])',
           '        result["candidate_proof_artifact"] = store.write("prior-host-proof.outer.original.json", proof_raw)\n        result["candidate_terminal_artifact"] = store.write("prior-host-proof.terminal.original.json", terminal_raw)\n        tools = bind_tools(core, pool, end, request["candidate_aapt2"])\n        aliases = bind_static_dependencies(core, pool, tools, end, proof)')
    change('("manifest", [tools["aapt"]["pin"]["resolved_path"], "dump", "xmltree", source, "AndroidManifest.xml"])]',
           '("manifest", [tools["aapt"]["pin"]["resolved_path"], "dump", "xmltree", source, "AndroidManifest.xml"]),\n                        ("legacy-badging", [tools["aapt"]["pin"]["resolved_path"], "dump", "badging", source])]')
    change('                        streams = run_tool(argv, (fd, tools["apksigner_jar"]["fd"]), command, end)',
           '                        recheck_static_aliases(aliases, end)\n                        need(time.monotonic() + 5 < end, "DIAGNOSTIC_DEADLINE_BEFORE_CHILD_SPAWN")\n                        streams = run_tool(argv, (fd, tools["apksigner_jar"]["fd"]), command, end)')
    change('                        need(command.get("joined") is True and command.get("pipes_closed") is True, "TOOL_CHILD_RETIREMENT_NOT_PROVED")',
           '                        need(command.get("joined") is True and command.get("pipes_closed") is True, "TOOL_CHILD_RETIREMENT_NOT_PROVED")\n                        need(command.get("output_capture_complete") is True and not command.get("timed_out") and not command.get("error") and not command.get("retirement_error"), "TOOL_OBSERVATION_INCOMPLETE")\n                        recheck_static_aliases(aliases, end)')
    change('        recheck_tools(core, pool, tools, end, True)', '        recheck_static_aliases(aliases, end)\n        recheck_tools(core, pool, tools, end, True)')
    change('        core.pinned_record(request["candidate_inventory"], 65536)',
           '        core.pinned_record(request["candidate_inventory"], 65536)\n        core.pinned_record(request["candidate_proof"], 131072)\n        core.pinned_record(request["candidate_terminal"], 65536)')
    change('        result["all_manifests_and_signatures_verified"] = all_apk_evidence_verified(result, request["packages"])',
           '        primary = [x for x in result["commands"] if x.get("name") != "legacy-badging"]\n        legacy = [x for x in result["commands"] if x.get("name") == "legacy-badging"]\n        result["all_primary_commands_succeeded"] = len(primary) == 6 and all(x.get("returncode") == 0 and not x.get("timed_out") and x.get("output_capture_complete") and not x.get("error") for x in primary)\n        result["legacy_badging_observations_complete"] = len(legacy) == 2 and all(x.get("joined") is True and x.get("pipes_closed") is True and x.get("output_capture_complete") is True and not x.get("timed_out") and not x.get("error") for x in legacy)\n        result["legacy_badging_returncodes"] = {x["package"]: x.get("returncode") for x in legacy}\n        result["all_manifests_and_signatures_verified"] = all_apk_evidence_verified(result, request["packages"]) and result["legacy_badging_observations_complete"]\n        result["same_APK_bytes_new_parser_succeeded"] = result["all_manifests_and_signatures_verified"]\n        result["old_aapt_resource_compatibility_limitation_supported_by_comparison"] = (result["same_APK_bytes_new_parser_succeeded"] and result["legacy_badging_returncodes"] == {"com.android.calendar": 1, "org.fcitx.fcitx5.android": 0})\n        result["inference_limit"] = "Only these two exact APKs and observed tool identities; the old b05 and host-proof failures remain unchanged. No all-App compatibility, business readiness or gate advancement."')
    change('"INDEPENDENT_TWO_APK_RESOURCE_DIAGNOSTIC_VERIFIED"', '"INDEPENDENT_TWO_APK_RESOURCE_COMPARISON_COMPLETE"')
    change('    result["same_APK_bytes_new_parser_succeeded"] = result["all_manifests_and_signatures_verified"]\n    result["old_aapt_resource_compatibility_limitation_supported_by_comparison"] = result["all_manifests_and_signatures_verified"]\n    result["inference_limit"] = "Only these two exact APKs and two actual tool byte identities; no general all-App compatibility or business readiness claim."\n', '')
    change('    os.umask(0o077)\n    try:', '    os.umask(0o077)\n    process_fds_before = len(os.listdir("/proc/self/fd"))\n    try:')
    change('    raw = canonical(result)\n    need(len(raw) <= MAX_RESULT, "STDOUT_ARTIFACT_BOUND")',
           '    result["process_FDs_before"] = process_fds_before\n    result["process_FDs_after"] = len(os.listdir("/proc/self/fd"))\n    if result["process_FDs_before"] != result["process_FDs_after"]:\n        result.setdefault("errors", []).append({"reason": "FINAL_PROCESS_FD_DIFFERENCE"})\n        result["all_manifests_and_signatures_verified"] = False\n        result["same_APK_bytes_new_parser_succeeded"] = False\n        result["old_aapt_resource_compatibility_limitation_supported_by_comparison"] = False\n        result["status"] = "FINAL_PROCESS_FD_DIFFERENCE"\n    result["success_gate_requires_outer_final_stdout_and_authoritative_terminal"] = True\n    raw = canonical(result)\n    need(len(raw) <= MAX_RESULT, "STDOUT_ARTIFACT_BOUND")')
    # Any late receipt/FD failure invalidates derived new-parser conclusions too.
    change('        result["owned_descriptors_final"] = pool.summary()',
           '        result["owned_descriptors_final"] = pool.summary()\n        if not result["all_manifests_and_signatures_verified"]:\n            result["same_APK_bytes_new_parser_succeeded"] = False\n            result["old_aapt_resource_compatibility_limitation_supported_by_comparison"] = False')
    ast.parse(text)
    out = ROOT / "candidate-r2"
    source = text.encode()
    save(out / "diagnose_calendar_and_fcitx.py", source)
    save(out / "against-preserved-draft-r1.diff", ''.join(difflib.unified_diff(old.decode().splitlines(True), text.splitlines(True), fromfile="preserved-draft-r1", tofile="candidate-r2")).encode())
    # Copy only exact authoritative original bytes; no numeric reserialization.
    save(out / "inputs/aapt2-proof.outer.original.json", proof_raw)
    save(out / "inputs/aapt2-proof.terminal.original.json", terminal_raw)
    inv = (INV / "actual.stdout.original.json").read_bytes() if (INV / "actual.stdout.original.json").exists() else None
    if inv is None:
        possibilities = [p for p in INV.rglob("*") if p.is_file() and p.stat().st_size == 9876]
        selected = [p for p in possibilities if digest(p.read_bytes()) == "60ee9c47cb1719343a1667d306e26086d66f2376d62b8c5251f4e64446887341"]
        assert len(selected) >= 1, "MISSING_ACTUAL_INVENTORY_RAW"
        inv = selected[0].read_bytes()
    assert len(inv) == 9876 and digest(inv) == "60ee9c47cb1719343a1667d306e26086d66f2376d62b8c5251f4e64446887341"
    save(out / "inputs/inventory.original.json", inv)
    scope = {"path": "/home/alex/work/pocket4-successor-native-install-20261106-douyin-01/app-scope-after.private.json", "bytes": 57340, "sha256": "489129d6e39a5aebc410ebcf74706279a99ff6751a15bd0a6b324ddd007e01a4"}
    request = {"schema": "pocket4-independent-calendar-aapt2-comparison-request-v2", "guard": {"path": "/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/current_baseline_guard.py", "bytes": 3213, "sha256": "d84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3"}, "app_scope": scope, "packages": ["com.android.calendar", "org.fcitx.fcitx5.android"], "output_root": "/home/alex/work/pocket4-successor-apk-audit-20261106-calendar-aapt2-comparison-r2-01", "official_release_assets": None, "candidate_aapt2": candidate, "candidate_inventory": {"path": STAGE + "/inputs/inventory.original.json", "bytes": len(inv), "sha256": digest(inv)}, "candidate_proof": {"path": STAGE + "/inputs/aapt2-proof.outer.original.json", "bytes": len(proof_raw), "sha256": digest(proof_raw)}, "candidate_terminal": {"path": STAGE + "/inputs/aapt2-proof.terminal.original.json", "bytes": len(terminal_raw), "sha256": digest(terminal_raw)}}
    save(out / "request.review-only.json", (json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n").encode())
    print(json.dumps({"source": str(out / "diagnose_calendar_and_fcitx.py"), "bytes": len(source), "sha256": digest(source), "runtime_executed": False}))


if __name__ == "__main__":
    main()
