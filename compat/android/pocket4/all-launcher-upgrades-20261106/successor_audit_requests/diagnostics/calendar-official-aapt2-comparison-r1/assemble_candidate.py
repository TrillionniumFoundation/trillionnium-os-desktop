#!/usr/bin/env python3
"""Seal one independent two-APK comparison from actual host-tool proof."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]
OLD = HERE.parent / "calendar-resource-parser-r1/candidate-r3"
HOST = HERE.parent / "google-maven-aapt2-host-proof-r3"
STAGE = "/home/alex/work/pocket4-calendar-official-aapt2-source-20261106-r1"
OUTPUT = "/home/alex/work/pocket4-successor-apk-audit-20261106-calendar-official-aapt2-r1-01"


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path, size, digest):
    raw = path.read_bytes()
    assert len(raw) == size and sha(raw) == digest, path
    return raw


def write(name, raw):
    if isinstance(raw, str):
        raw = raw.encode("utf-8")
    with (HERE / name).open("xb") as stream:
        stream.write(raw)
    return {"path": STAGE + "/" + name, "bytes": len(raw), "sha256": sha(raw)}


def replace_one(text, old, new):
    assert text.count(old) == 1, old[:160]
    return text.replace(old, new, 1)


def assignment(text, name, value):
    node = next(node for node in ast.parse(text).body if isinstance(node, ast.Assign) and
                any(isinstance(target, ast.Name) and target.id == name for target in node.targets))
    return replace_one(text, ast.get_source_segment(text, node), name + " = " + repr(value))


def functions(text):
    return {node.name: ast.get_source_segment(text, node) for node in ast.parse(text).body
            if isinstance(node, (ast.FunctionDef, ast.ClassDef))}


def main():
    old = read(OLD / "diagnose_calendar_and_fcitx.py", 46019,
               "e9935fd73b49a72b1bf79c098ee21486c7a35c1fddf7fa188b7a4091d1dc0c89").decode()
    old_wrapper = read(OLD / "owned_readonly_lifetime.py", 16667,
                      "6a818a4fd0a28cc2dd565acf37b709b349011aa87d587fe5cf95c10be9d1916e").decode()
    host_raw = read(HOST / "actual/worker.stdout.original.json", 34091,
                    "b827c080d7af767cab60fbd9a682eafd8dfe06d6f4375b23f62988212a4b908e")
    host_stdout = read(HOST / "actual/stdout.original.jsonl", 7092,
                       "d7785fb80d8075267b99f1ccc5537cdd12dc014f38fd72c87eb575bd899dd343")
    host_terminal = read(HOST / "actual/status-1.original.txt", 731,
                         "f456a3ee2db689339d5d60db5106904b0d2bde640663eccc222311db39f62435")
    proof = json.loads(host_raw)
    assert proof["ok"] is True and proof["original_descriptor_identities_restored"] is True
    assert json.loads(host_terminal)["job_id"] == "1a1b257ba27-fc05-7da0"
    host_source = read(HOST / "prepare_official_aapt2.py", 61830,
                       "bdae0316cd5423f60a6d1884e2131ba446c3554ee696c3c543ebf3634e743a63")
    assert proof["source"]["bytes"] == len(host_source) and proof["source"]["sha256"] == sha(host_source)
    scope_raw = read(PROJECT / "successor_audit_requests/explicit47_scope_r2/actual-readback/app-scope.private.json", 58854,
                     "44f9ce783000a672c270e98afdaeb74bd79654508bfacae6793316ff4252e52f")
    scope = {"path": "/home/alex/work/pocket4-current-explicit-47-app-observation-20261106-r2/app-scope.private.json",
             "bytes": len(scope_raw), "sha256": sha(scope_raw)}
    (HERE / "inputs").mkdir(exist_ok=False)
    input_pins = {}
    for name in ("inventory.original.json", "aapt2-proof.outer.original.json", "aapt2-proof.terminal.original.json"):
        raw = (OLD / "inputs" / name).read_bytes()
        input_pins[name] = write("inputs/" + name, raw)
    official_stdout_pin = write("inputs/official-host.stdout.original.jsonl", host_stdout)
    official_terminal_pin = write("inputs/official-host.terminal.original.json", host_terminal)
    candidate = {"path": proof["candidate"]["resolved_path"], **{key: proof["candidate"][key] for key in ("bytes", "sha256", "file")}}
    constants = {
        "OFFICIAL_HOST_JOB": "1a1b257ba27-fc05-7da0", "OFFICIAL_HOST_SOURCE": proof["source"],
        "OFFICIAL_HOST_STDOUT": official_stdout_pin, "OFFICIAL_HOST_TERMINAL": official_terminal_pin,
        "OFFICIAL_CANDIDATE": candidate, "OFFICIAL_TOOL_ROOT": proof["controlled_runpath_layout"]["output_root"]}
    old_stage = "/home/alex/work/pocket4-calendar-aapt2-diagnostic-source-20261106-r3"
    worker = old.replace(old_stage, STAGE)
    worker = worker.replace("Independent comparison of two exact APKs, using the actual observed Debian\nAAPT2 version/help/dependency evidence.",
                            "Independent comparison using the actually qualified official AAPT2 9.5.1.\nThe original Debian tool and its full nineteen-file dependency graph remain\nbound for the legacy AAPT/JDK comparison.")
    worker = assignment(worker, "OUTPUT_PREFIX", OUTPUT[:-2])
    worker = assignment(worker, "ACTUAL_SCOPE", scope)
    worker = worker.replace('"pocket4-independent-calendar-aapt2-comparison-request-v2"',
                            '"pocket4-independent-calendar-official-aapt2-comparison-request-v1"')
    worker = worker.replace('"pocket4-independent-calendar-aapt2-resource-comparison-v2"',
                            '"pocket4-independent-calendar-official-aapt2-resource-comparison-v1"')
    for name in ("candidate_aapt2", "candidate_inventory", "candidate_proof", "candidate_terminal"):
        worker = worker.replace('"' + name + '"', '"legacy_' + name + '"')
    block = "\n".join(name + " = " + repr(value) for name, value in constants.items()) + "\n\n"
    block += (HERE / "official_binding.py").read_text() + "\n\n"
    worker = replace_one(worker, "def validate_request(request):", block + "def validate_request(request):")
    worker = replace_one(worker, '"legacy_candidate_proof", "legacy_candidate_terminal"}',
                         '"legacy_candidate_proof", "legacy_candidate_terminal", "official_candidate_aapt2", "official_host_stdout", "official_host_terminal"}')
    worker = replace_one(worker, '    validate_candidate(request["legacy_candidate_aapt2"])',
                         '    validate_candidate(request["legacy_candidate_aapt2"])\n'
                         '    need(request["official_candidate_aapt2"] == OFFICIAL_CANDIDATE and request["official_host_stdout"] == OFFICIAL_HOST_STDOUT and\n'
                         '         request["official_host_terminal"] == OFFICIAL_HOST_TERMINAL, "EXACT_ACTUAL_OFFICIAL_TOOL_PROOF_REQUEST")')
    worker = replace_one(worker, '    pool, store, lock = core.FDs(), None, None',
                         '    pool, store, lock, official_layout = core.FDs(), None, None, None')
    worker = replace_one(worker, '        inventory_raw = core.pinned_record(request["legacy_candidate_inventory"], 65536)',
                         '        official_stdout_raw = core.pinned_record(request["official_host_stdout"], 131072)\n'
                         '        official_terminal_raw = core.pinned_record(request["official_host_terminal"], 65536)\n'
                         '        official_proof = verify_official_host_proof(official_stdout_raw, official_terminal_raw)\n'
                         '        result["official_host_qualification"] = {"job_id": OFFICIAL_HOST_JOB, "source": OFFICIAL_HOST_SOURCE,\n'
                         '            "candidate": OFFICIAL_CANDIDATE, "version": official_proof["version_original"],\n'
                         '            "static_graph_is_actual_loader_mapping_proof": False}\n'
                         '        inventory_raw = core.pinned_record(request["legacy_candidate_inventory"], 65536)')
    worker = replace_one(worker, '        tools = bind_tools(core, pool, end, request["legacy_candidate_aapt2"])',
                         '        result["official_host_stdout_artifact"] = store.write("official-host.stdout.original.jsonl", official_stdout_raw)\n'
                         '        result["official_host_terminal_artifact"] = store.write("official-host.terminal.original.json", official_terminal_raw)\n'
                         '        tools = bind_tools(core, pool, end, request["legacy_candidate_aapt2"])')
    worker = replace_one(worker, '        aliases = bind_static_dependencies(core, pool, tools, end, proof)',
                         '        aliases = bind_static_dependencies(core, pool, tools, end, proof)\n'
                         '        aliases += add_official_tool_binding(core, pool, tools, end, official_proof)\n'
                         '        official_layout = bind_existing_official_layout(core, pool, end, result, official_proof)\n'
                         '        result["legacy_static_dependency_file_count"] = len(proof["static_dependency_graph"])\n'
                         '        result["official_static_dependency_file_count"] = len(official_proof["static_dependency_graph"])')
    worker = replace_one(worker, '                        streams = run_tool(argv, (fd, tools["apksigner_jar"]["fd"]), command, end)',
                         '                        official_layout.verify(f"before-p{pi:02d}-a{ai:02d}-{name}", end)\n'
                         '                        need(time.monotonic() + 5 < end, "OFFICIAL_LAYOUT_POSTCHECK_DEADLINE_BEFORE_SPAWN")\n'
                         '                        streams = run_tool(argv, (fd, tools["apksigner_jar"]["fd"]), command, end)')
    worker = replace_one(worker, '                        outputs[name] = streams["stdout"]',
                         '                        official_layout.verify(f"after-p{pi:02d}-a{ai:02d}-{name}", end)\n'
                         '                        outputs[name] = streams["stdout"]')
    worker = replace_one(worker, '        core.pinned_record(ORIGINAL_FAILED_RESULT, MAX_RESULT)\n        core.pinned_record(ORIGINAL_CONTROL_RESULT, MAX_RESULT)',
                         '        core.pinned_record(ORIGINAL_FAILED_RESULT, MAX_RESULT)\n        core.pinned_record(ORIGINAL_CONTROL_RESULT, MAX_RESULT)\n'
                         '        core.pinned_record(request["official_host_stdout"], 131072)\n'
                         '        core.pinned_record(request["official_host_terminal"], 65536)\n'
                         '        core.pinned_record(OFFICIAL_HOST_SOURCE, 131072)\n'
                         '        official_layout.verify("after_all_APK_tools_and_file_checks", end)')
    worker = replace_one(worker, '    finally:\n        if lock is not None:',
                         '    finally:\n        if official_layout is not None:\n'
                         '            try:\n                official_layout.close()\n'
                         '                closure = result["official_private_layout"]["owned_directory_descriptors"]\n'
                         '                result["official_layout_descriptors_closed"] = closure["acquired"] == closure["closed"] == 11 and closure["errors"] == []\n'
                         '                need(result["official_layout_descriptors_closed"], "OFFICIAL_LAYOUT_FDS_NOT_CLOSED")\n'
                         '            except BaseException as error:\n'
                         '                result["errors"].append({"stage": "official_layout_close", "type": type(error).__name__, "reason": str(error)[:160]})\n'
                         '        if lock is not None:')
    worker = replace_one(worker, '        result["same_APK_bytes_new_parser_succeeded"] = result["all_manifests_and_signatures_verified"]',
                         '        result["official_badging_stderr_empty"] = clean_official_badging_observations(result["commands"])\n'
                         '        observations = result.get("official_private_layout", {}).get("observations", [])\n'
                         '        result["official_layout_before_and_after_all_commands"] = len(observations) == 18 and all(\n'
                         '            row.get("complete") is True and row.get("all_five_search_directories_and_thirty_candidates_proved") is True for row in observations)\n'
                         '        result["comparison_complete"] = (result["all_manifests_and_signatures_verified"] and result["official_badging_stderr_empty"] and\n'
                         '            result.get("official_layout_descriptors_closed") is True and result["official_layout_before_and_after_all_commands"])\n'
                         '        result["resource_table_integrity_fully_proved"] = False\n'
                         '        result["same_APK_bytes_new_parser_succeeded"] = result["comparison_complete"]')
    worker = worker.replace('"old_aapt_resource_compatibility_limitation_supported_by_comparison"',
                            '"observed_legacy_badging_failure_is_parser_dependent"')
    worker = replace_one(worker, '        result["inference_limit"] = "Only these two exact APKs and observed tool identities; the old b05 and host-proof failures remain unchanged. No all-App compatibility, business readiness or gate advancement."',
                         '        result["inference_limit"] = "Only exact held Calendar/Fcitx badging, manifest and signature observations. Empty latest-tool badging stderr is required, but badging alone does not prove all resource-table integrity or business readiness. All old failures and old b05 gate remain unchanged."')
    worker = replace_one(worker, '        result["status"] = "INDEPENDENT_TWO_APK_RESOURCE_COMPARISON_COMPLETE" if result["all_manifests_and_signatures_verified"] else "INDEPENDENT_RESOURCE_DIAGNOSTIC_INCOMPLETE"',
                         '        result["status"] = "OFFICIAL_TOOL_TWO_APK_COMPARISON_COMPLETE" if result["comparison_complete"] else "OFFICIAL_TOOL_RESOURCE_DIAGNOSTIC_INCOMPLETE"')
    worker = replace_one(worker, '        if not result["all_manifests_and_signatures_verified"]:\n            result["same_APK_bytes_new_parser_succeeded"] = False',
                         '        if not result["all_manifests_and_signatures_verified"]:\n            result["comparison_complete"] = False\n            result["same_APK_bytes_new_parser_succeeded"] = False')
    worker = replace_one(worker, '        result["status"] = "FINAL_PROCESS_FD_DIFFERENCE"',
                         '        result["comparison_complete"] = False\n        result["status"] = "FINAL_PROCESS_FD_DIFFERENCE"')
    worker = replace_one(worker, '    return 0 if result.get("all_manifests_and_signatures_verified") is True else 1',
                         '    return 0 if result.get("comparison_complete") is True else 1')
    compile(worker, "diagnose_calendar_and_fcitx.py", "exec")
    worker_pin = write("diagnose_calendar_and_fcitx.py", worker)
    request = json.loads((OLD / "request.review-only.json").read_bytes())
    request.update(schema="pocket4-independent-calendar-official-aapt2-comparison-request-v1", app_scope=scope, output_root=OUTPUT)
    for name in ("candidate_aapt2", "candidate_inventory", "candidate_proof", "candidate_terminal"):
        value = request.pop(name)
        if "path" in value:
            value["path"] = value["path"].replace(old_stage, STAGE)
        request["legacy_" + name] = value
    request.update(official_candidate_aapt2=candidate, official_host_stdout=official_stdout_pin, official_host_terminal=official_terminal_pin)
    request_raw = (json.dumps(request, sort_keys=True, separators=(",", ":")) + "\n").encode()
    request_pin = write("request.review-only.json", request_raw)
    wrapper = old_wrapper
    config_node = next(n for n in ast.parse(wrapper).body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "CONFIG" for t in n.targets))
    config = ast.literal_eval(config_node.value)
    config.update(stage_root=STAGE, worker=worker_pin, request=request_pin,
                  prior_unexecuted_source={"bytes": 46019, "sha256": "e9935fd73b49a72b1bf79c098ee21486c7a35c1fddf7fa188b7a4091d1dc0c89",
                                           "preserved": True, "meaning": "prior Debian comparison source and its actual outcome retained; field name is inherited"})
    wrapper = assignment(wrapper, "CONFIG", config)
    wrapper = wrapper.replace('"pocket4-independent-calendar-aapt2-resource-comparison-v2"',
                              '"pocket4-independent-calendar-official-aapt2-resource-comparison-v1"')
    wrapper = wrapper.replace('"INDEPENDENT_TWO_APK_RESOURCE_COMPARISON_COMPLETE"', '"OFFICIAL_TOOL_TWO_APK_COMPARISON_COMPLETE"')
    wrapper = replace_one(wrapper, '"legacy_badging_observations_complete", "all_manifests_and_signatures_verified", "all_tool_children_joined", "action_lock_released"))',
                          '"legacy_badging_observations_complete", "all_manifests_and_signatures_verified", "all_tool_children_joined", "action_lock_released",\n'
                          '                 "comparison_complete", "official_badging_stderr_empty", "official_layout_descriptors_closed", "official_layout_before_and_after_all_commands"))')
    compile(wrapper, "owned_readonly_lifetime.py", "exec")
    wrapper_pin = write("owned_readonly_lifetime.py", wrapper)
    files = [{"name": "owned_readonly_lifetime.py", **{k: wrapper_pin[k] for k in ("bytes", "sha256")}},
             {"name": "diagnose_calendar_and_fcitx.py", **{k: worker_pin[k] for k in ("bytes", "sha256")}},
             {"name": "request.review-only.json", **{k: request_pin[k] for k in ("bytes", "sha256")}}]
    files += [{"name": "inputs/" + name, **{k: pin[k] for k in ("bytes", "sha256")}} for name, pin in input_pins.items()]
    files += [{"name": "inputs/official-host.stdout.original.jsonl", **{k: official_stdout_pin[k] for k in ("bytes", "sha256")}},
              {"name": "inputs/official-host.terminal.original.json", **{k: official_terminal_pin[k] for k in ("bytes", "sha256")}}]
    stage = (OLD / "stage_and_run_comparison_r3.py").read_text()
    stage = assignment(assignment(stage, "ROOT", STAGE), "FILES", files)
    stage = stage.replace("pocket4-calendar-owned-comparison-source-stage-v3", "pocket4-calendar-official-comparison-source-stage-v1")
    stage = stage.replace("pocket4-calendar-owned-comparison-source-stage-result-v3", "pocket4-calendar-official-comparison-source-stage-result-v1")
    compile(stage, "stage_and_run_comparison.py", "exec")
    write("stage_and_run_comparison.py", stage)
    payload = {"schema": "pocket4-calendar-official-comparison-source-stage-v1",
               "files": [{"name": row["name"], "text": (HERE / row["name"]).read_text()} for row in files]}
    payload_raw = (json.dumps(payload, sort_keys=True, separators=(",", ":")) + "\n").encode()
    assert len(payload_raw) <= 262144
    write("stage.stdin.original.json", payload_raw)
    packet = json.loads((OLD / "process-request.review-only.json").read_bytes())
    packet.update(idempotency_key="sidecar-evidence-20261106-calendar-official-aapt2-comparison-r1", stdin=payload_raw.decode())
    assert packet["args"][:-1] == ["-n", "/usr/bin/python3", "-I", "-B", "-c"]
    packet["args"][-1] = stage
    packet_raw = (json.dumps(packet, sort_keys=True, separators=(",", ":")) + "\n").encode()
    packet_pin = write("process-request.review-only.json", packet_raw)
    for filename, first, second in (("worker-against-actual-debian-r3.diff", old, worker),
                                    ("owned-wrapper-against-actual-debian-r3.diff", old_wrapper, wrapper),
                                    ("stager-against-actual-debian-r3.diff", (OLD / "stage_and_run_comparison_r3.py").read_text(), stage)):
        write(filename, "".join(difflib.unified_diff(first.splitlines(True), second.splitlines(True), fromfile="preserved-actual-debian-r3", tofile="independent-official-comparison-r1")))
    unchanged = [name for name, body in functions(old).items() if functions(worker).get(name) == body]
    assert all(name in unchanged for name in ("verify_actual_proof", "bind_static_dependencies", "bind_tools", "recheck_tools", "run_tool", "badging_manifest", "xml_permissions", "parse_signature", "Store"))
    old_outer, new_outer = functions(old_wrapper), functions(wrapper)
    assert [name for name in old_outer if old_outer[name] != new_outer[name]] == ["worker_gate"]
    source_pins = {"worker": worker_pin, "wrapper": wrapper_pin, "request": request_pin, "process_request": packet_pin,
                   "stage_stdin_bytes": len(payload_raw), "unchanged_worker_definitions": unchanged,
                   "owned_lifetime_functions_unchanged_except_stricter_worker_gate": True,
                   "official_host_job": "1a1b257ba27-fc05-7da0", "source_prepared_not_executed": True,
                   "new_remote_jobs": 0}
    write("SOURCE_PINS.preliminary.json", json.dumps(source_pins, sort_keys=True, indent=2) + "\n")
    print(json.dumps(source_pins, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()
