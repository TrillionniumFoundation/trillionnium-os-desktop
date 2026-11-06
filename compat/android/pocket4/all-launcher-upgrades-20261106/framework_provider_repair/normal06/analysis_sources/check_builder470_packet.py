#!/usr/bin/env python3
"""Local packet and pure admission checks; no host subprocess or Android action."""
from pathlib import Path
import ast
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "builder470-hostprep-r1"
sha = lambda b: hashlib.sha256(b).hexdigest()
read_json = lambda p: json.loads(p.read_bytes())
plan = read_json(PACKET / "execution-plan.json")
checks = []

def yes(name, condition):
    assert condition, name
    checks.append({"name": name, "result": "PASS", "scope": "OFFLINE_ONLY"})

for item in plan["files"]:
    data = (PACKET / item["path"]).read_bytes()
    assert len(data) == item["bytes"] and sha(data) == item["sha256"], item["path"]
yes("eight_exact_packet_artifacts", len(plan["files"]) == 8)
source = (PACKET / "compile_builder470.py").read_text()
tree = ast.parse(source)
stage = (PACKET / "stage_builder470.py").read_text()
ast.parse(stage)
stage_transport = (PACKET / "stage_transport.py").read_text()
compile_transport = (PACKET / "compile_transport.py").read_text()
ast.parse(stage_transport)
ast.parse(compile_transport)
yes("four_python_sources_parse_without_execution", True)
functions = {n.name: ast.get_source_segment(source, n) for n in tree.body if isinstance(n, ast.FunctionDef)}
for item in plan["helper_provenance"]:
    body = functions[item["name"]].encode()
    assert len(body) == item["bytes"] and sha(body) == item["sha256"]
yes("twenty_six_previous_qualified_helpers_unchanged", len(plan["helper_provenance"]) == 26)
stage_request = read_json(PACKET / "exact-stage-request.json")
compile_request = read_json(PACKET / "exact-compile-request.json")
wire = (PACKET / "stage-stdin.json").read_bytes()
yes("stage_request_exact_stdin_and_transport", stage_request["stdin"].encode() == wire and stage_request["args"][3] == stage_transport and stage_request["args"][4:] == ["--stage-only-once"])
yes("compile_request_exact_transport", compile_request["args"][3] == compile_transport and compile_request["args"][4:] == ["--execute-once"])
yes("stage_transport_fixed_complete_hash", str(len(wire)) in stage_transport and sha(wire) in stage_transport and sha(stage.encode()) in stage_transport)
yes("compile_transport_fixed_source_hash", str(len(source.encode())) in compile_transport and sha(source.encode()) in compile_transport)
packet = json.loads(wire)
yes("packet_complete_schema_and_stage", set(packet) == {"schema", "stage", "files"} and packet["schema"] == 1 and packet["stage"] == stage)
stage_ast = ast.parse(stage)
pins = next(ast.literal_eval(n.value) for n in stage_ast.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "FILE_PINS" for t in n.targets))
yes("packet_exact_eleven_files", len(pins) == len(packet["files"]) == 11 and set(pins) == set(packet["files"]))
for name, text in packet["files"].items():
    assert pins[name] == {"bytes": len(text.encode()), "sha256": sha(text.encode())}, name
yes("all_inner_files_bound_to_stage", True)
yes("candidate_manifest_exact_498_and_225_to_242_lock", len(json.loads(packet["files"]["candidate-source-manifest.json"])) == 498 and len(json.loads(packet["files"]["overlay/android/manifest/m2-role-ingress-provider3-source-lock.json"])["projects"]) == 242)
yes("no_whole_aosp_copy_or_runtime_binding", plan["whole_AOSP_source_copy"] is False and plan["Main_or_Android_reads_or_writes"] == 0 and "Old 46-scope is not complete" in plan["normal06_framework_request"])
yes("one_gib_one_cpu_owned_request_budget", all(r["memory_max_bytes"] == 1024**3 and r["cpu_quota_percent"] == 100 for r in [stage_request, compile_request]))

# Execute only explicitly selected pure functions. No imported harness, resource
# observation, subreaper, subprocess, inventory, packet stage, or main is run.
chosen = ["require", "parse_admission_meminfo", "memory_admission", "owned_resource_gate", "validate_focused_result"]
module = ast.Module(body=[n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in chosen], type_ignores=[])
scope = {"re": re, "MEMORY_MAX": 1024**3, "SWAP_MAX": 0, "MIN_AVAILABLE": 3*1024**3, "FAKEROOT_TEST": "native_generation::tests::staging_replaces_the_whole_apex_and_preserves_its_metadata"}
exec(compile(module, "<pure-hostprep-admission-controls>", "exec"), scope)
owned = {"memory.max": str(1024**3), "cpu.max": "100000 100000", "memory.swap.max": "0", "memory.swap.current": "0"}
memory = {"MemTotal": 32*1024**3, "MemAvailable": 3*1024**3, "SwapTotal": 8*1024**3, "SwapFree": 8*1024**3, "SwapCached": 0}
scope["memory_admission"](memory, owned)
yes("exact_three_gib_boundary_admitted_by_pure_function", True)

def denied(name, function):
    try:
        function()
    except RuntimeError:
        yes(name, True)
    else:
        raise AssertionError("expected rejection: " + name)

denied("one_byte_below_rust_admission_rejected", lambda: scope["memory_admission"]({**memory, "MemAvailable": 3*1024**3-1}, owned))
denied("nonzero_owned_swap_rejected", lambda: scope["memory_admission"](memory, {**owned, "memory.swap.current": "1"}))
denied("wrong_owned_ram_budget_rejected", lambda: scope["memory_admission"](memory, {**owned, "memory.max": str(2*1024**3)}))
denied("wrong_owned_cpu_budget_rejected", lambda: scope["memory_admission"](memory, {**owned, "cpu.max": "200000 100000"}))
denied("duplicate_meminfo_required_field_rejected", lambda: scope["parse_admission_meminfo"](b"MemTotal: 33554432 kB\nMemAvailable: 3145728 kB\nMemAvailable: 3145728 kB\nSwapTotal: 0 kB\nSwapFree: 0 kB\nSwapCached: 0 kB\n"))
denied("owned_oom_kill_rejected", lambda: scope["owned_resource_gate"]("oom 1\noom_kill 1\noom_group_kill 0\n"))
name = "native_role_ingress::tests::systemui_extension_rejects_missing_provider_wrong_revision_or_scope"
stdout = f"running 1 test\ntest {name} ... ok\ntest result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 208 filtered out; finished in 0.01s\n"
log = ("ok " + name + "\n").encode()
scope["validate_focused_result"](name, 18, stdout, log, 209)
yes("exact_independent_libtest_result_contract", True)
denied("stdout_only_success_without_libtest_rejected", lambda: scope["validate_focused_result"](name, 18, stdout, b"", 209))
denied("wrong_filtered_test_count_rejected", lambda: scope["validate_focused_result"](name, 18, stdout.replace("208 filtered", "205 filtered"), log, 209))
denied("duplicate_test_summary_rejected", lambda: scope["validate_focused_result"](name, 18, stdout+stdout, log, 209))
tests = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "TESTS" for t in n.targets))
yes("nineteen_explicit_distinct_tests_include_new_lock_case", len(tests) == len(set(tests)) == 19 and name in tests)
yes("rust_version_comparison_uses_actual_newline", any(isinstance(n, ast.Constant) and n.value == "release: 1.93.0\n" for n in ast.walk(tree)))
receipt = {"schema": "pocket4-builder470-packet-offline-controls-v1", "execution_plan_sha256": sha((PACKET / "execution-plan.json").read_bytes()), "checks": checks, "passed": len(checks), "Rust_compiler_or_tests_run": False, "Main_or_Android_actions": 0, "remote_actions": 0, "Soong_run": False, "actual_resource_admission": "UNKNOWN_NOT_OBSERVED", "runtime_qualification": "UNKNOWN_NOT_OBSERVED", "production_ready": False}
data = (json.dumps(receipt, indent=2) + "\n").encode()
p = PACKET / "offline-controls.json"
p.write_bytes(data)
print(json.dumps({"path": str(p), "passed": len(checks), "bytes": len(data), "sha256": sha(data)}))
