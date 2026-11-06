#!/usr/bin/env python3
"""Qualify the already retrieved original receipts; no remote or build action."""
from pathlib import Path
import ast
import base64
import hashlib
import json
import re

ROOT = Path(__file__).resolve().parents[1]
PACKET = ROOT / "builder470-hostprep-r2"
READBACK = PACKET / "root-readback-01"
ACTUAL = PACKET / "actual/compile"
sha = lambda b: hashlib.sha256(b).hexdigest()
read = lambda p: json.loads(p.read_bytes())
EXPECTED_RESULT_SHA = "6599026ebe5071ecdd5f0e2d962eb96cc791041be0dee9fd59a402735a6387d8"
EXPECTED_RESOURCE_SHA = "5b4b728f90ee088141d2cd9aaa7e242ef33e58b355c790422ed858930c926031"
JOB = "1a1b1d86cb7-fc05-7b1f"
HOST_ROOT = "/home/alex/work/pocket4-native-typed-ingress-builder470-systemui-provider-compile-02-20261106"

def pin(path):
    b = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "bytes": len(b), "sha256": sha(b)}

def full_readback(name, size, digest, info_name, chunk_names):
    data = (READBACK / name).read_bytes()
    info = read(READBACK / info_name)
    assert len(data) == info["size"] == size and sha(data) == info["sha256"] == digest
    combined = b""
    for chunk_name in chunk_names:
        chunk = read(READBACK / chunk_name)
        part = base64.b64decode(chunk["data_base64"], validate=True)
        assert chunk["offset"] == len(combined) and chunk["next_offset"] == len(combined) + len(part)
        assert chunk["version"] == info["version"] and sha(part) == chunk["chunk_sha256"]
        combined += part
    assert combined == data and chunk["eof"] is True
    return json.loads(data)

terminal = read(READBACK / "terminal.original.json")
assert terminal["job_id"] == JOB and terminal["state"] == "succeeded" and terminal["exit_code"] == 0
assert all(terminal[k] is True for k in ["output_complete", "output_durable", "terminal_publication_confirmed"])
assert all(terminal[k] is False for k in ["timed_out", "cancelled", "automatic_retry"])
assert terminal["log_errors"] == {"stderr": None, "stdout": None}
assert terminal["log_synced"] == {"stderr": True, "stdout": True}
assert terminal["log_truncated"] == {"stderr": False, "stdout": False}
assert terminal["log_bytes"]["stdout"] == {"seen": 2911, "stored": 2911}
assert terminal["log_bytes"]["stderr"] == {"seen": 0, "stored": 0}
result = full_readback("result.original.json", 76136, EXPECTED_RESULT_SHA, "result_fileinfo.original.json", ["result_read_0.original.json", "result_read_1.original.json"])
resource = full_readback("resource-admission.original.json", 2746, EXPECTED_RESOURCE_SHA, "resource_fileinfo.original.json", ["resource_read.original.json"])
assert result["state"] == "RUST_BUILD_AND_19_INDEPENDENT_FOCUSED_TESTS_PASS"
assert result["tests_passed"] == 19 and result["registered_tests"] == 209
assert result["cleanup"] == {"complete": True, "children": [], "errors": []}
assert all(result[k] is True for k in ["candidate_source_unchanged_after", "baseline_source_unchanged_after", "registry_input_bytes_and_full_identities_unchanged_after", "tool_inputs_unchanged_after"])
assert all(result[k] == 0 for k in ["Main_actions", "Android_actions", "install_actions"])
assert all(result[k] is False for k in ["Soong_invoked", "runtime_authorization_enabled", "production_ready", "full_Android_Java_JNI_compiled"])
assert result["source_files"] == 498 and result["new_project_count"] == 242
assert result["source_manifest_sha256"] == result["candidate_manifest"]["sha256"] == sha((PACKET / "candidate-source-manifest.json").read_bytes()) == "f4a0e6ff82f1ecf9bd786872d99cc0b1608e1d94d0adc37761e87aed449c81bd"
assert result["candidate_manifest"]["path"] == HOST_ROOT + "/candidate-source-manifest.json" and result["candidate_manifest"]["bytes"] == 99075
assert result["builder"]["path"] == result["builder"]["resolved_path"] == HOST_ROOT + "/compile01/cargo-target/debug/droidloom-update"
assert result["builder"]["bytes"] == 34817256 and result["builder"]["sha256"] == "e1d3dd7caf023e4709c2617318de97cc17906aae595b33c4c3290358e7d0dee5"
tree = ast.parse((PACKET / "compile_builder470.py").read_text())
tests = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "TESTS" for t in n.targets))
assert result["test_names"] == tests and len(set(tests)) == 19
commands = result["commands"]
assert len(commands) == 23 and [c["label"] for c in commands[:4]] == ["rust-version", "build", "test-compile", "test-list"]
assert all(c["returncode"] == 0 and c["timed_out"] is False and c["cwd"] == HOST_ROOT + "/builder-source" for c in commands)
assert len(result["independent_result_gates"]) == 19
for index, (name, command, gate) in enumerate(zip(tests, commands[4:], result["independent_result_gates"])):
    assert command["label"] == "projection-test-" + str(index)
    assert command["focused_result_gate"] == gate
    assert gate == {"outer_results": 1, "expected_stdout_runs": 1, "registered_tests": 209, "filtered_out_per_run": 208, "exact_name": name, "summary_and_independent_result_agree": True}
    log = command["independent_libtest_result"]
    expected_log = ("ok " + name + "\n").encode()
    assert log["bytes"] == len(expected_log) and log["sha256"] == sha(expected_log)
    assert log["path"] == HOST_ROOT + "/compile01/projection-test-" + str(index) + ".libtest"
    assert command["argv"] == [result["test_executable"]["path"], "--exact", name, "--test-threads=1", "--nocapture", "--logfile", log["path"]]
dependency = result["dependency_continuity"]
assert dependency["all_source_bytes_and_full_identities_equal_before"] is True
assert dependency["recorded_files_and_archives"] == 2706 and dependency["selected_packages"] == 49 and dependency["registry_packages"] == 45 and dependency["new_dependency_fetches"] == 0
assert dependency["actual_build_packages"] == dependency["actual_test_compile_packages"] and len(dependency["actual_build_packages"]) == len(set(dependency["actual_build_packages"])) == 49
assert resource["profile"] == {"memory_max_bytes": 1073741824, "memory_swap_max_bytes": 0, "minimum_fresh_MemAvailable_bytes": 3221225472, "admission_difference_bytes": 2147483648, "global_swap_is_owned_budget": False}
assert resource["owned_observed"] == {"memory.max": "1073741824", "cpu.max": "100000 100000", "memory.swap.max": "0", "memory.swap.current": "0"}
raw_mem = resource["meminfo"]["raw_ascii"].encode()
assert len(raw_mem) == resource["meminfo"]["bytes"] and sha(raw_mem) == resource["meminfo"]["sha256"]
mem_available = int(re.search(rb"(?m)^MemAvailable:\s+(\d+) kB$", raw_mem).group(1)) * 1024
assert mem_available >= 3*1024**3
assert resource["historical_sample_used_for_admission"] is False
assert result["resource_admission"]["sha256"] == EXPECTED_RESOURCE_SHA and result["resource_admission"]["bytes"] == 2746
assert result["owned_resource_gate"]["pass"] is True
events = dict((name, int(value)) for name, value in (line.split() for line in result["memory_events"].splitlines()))
assert events == result["owned_resource_gate"]["events"] and all(events[k] == 0 for k in ["oom", "oom_kill", "oom_group_kill"])
assert result["swap_peak"] == "0" and result["memory_peak"] == "1073741824" and events["max"] == 657
stdout = (ACTUAL / "stdout.raw").read_bytes()
assert len(stdout) == 2911 and (ACTUAL / "stderr.raw").read_bytes() == b""
last = json.loads(stdout.splitlines()[-1])
assert last["state"] == result["state"] and last["result"]["bytes"] == 76136 and last["result"]["sha256"] == EXPECTED_RESULT_SHA
assert (ACTUAL / "compile-status-attempt-01.error.txt").exists() and (ACTUAL / "pending-settlement.json").exists()

summary = {
    "schema": "pocket4-builder470-actual-rust-qualification-v1",
    "state": "ACTUAL_RUST_QUALIFICATION_PASS",
    "job_id": JOB,
    "durable_exit_code": 0,
    "authoritative_terminal": pin(READBACK / "terminal.original.json"),
    "result": pin(READBACK / "result.original.json"),
    "resource_admission": pin(READBACK / "resource-admission.original.json"),
    "builder": result["builder"],
    "test_executable": result["test_executable"],
    "candidate_manifest": result["candidate_manifest"],
    "source_lock": {"path": HOST_ROOT + "/builder-source/android/manifest/m2-role-ingress-provider3-source-lock.json", "bytes": 103409, "sha256": "f5717d49fe0d4656b952bd397beab5d2fa70aa0992dd936ac31f81246c9e4772", "projects": 242},
    "commands_all_zero": 23,
    "registered_tests": 209,
    "independent_gates_passed": 19,
    "gate_names_and_expected_libtest_bytes_sha_match": True,
    "cleanup": result["cleanup"],
    "source_registry_tools_continuity": True,
    "compiled_package_count": 49,
    "registry_packages": 45,
    "registry_source_and_archive_records": 2706,
    "new_dependency_fetches": 0,
    "resource_observation": {"fresh_MemAvailable_bytes_at_Rust_admission": mem_available, "Rust_memory_max_bytes": 1073741824, "Rust_memory_peak_bytes": 1073741824, "memory_max_events": 657, "oom_events": 0, "swap_peak_bytes": 0, "cpu_affinity": result["cpu_affinity"], "headroom_claim": "Peak reached the one-GiB limit and max events were recorded; no claim of unlimited memory headroom.", "not_reusable_for_future_Soong_admission": True},
    "previous_pending_and_status_timeout_preserved": True,
    "individual_command_logs_reread_this_step": False,
    "evidence_basis": "Pinned frozen harness checked command completion, source identities and independent libtest files. Root retrieved original full result and resource bytes under version pins; this local gate independently checked those originals and expected libtest hashes. No unresolved hard gate calls for rereading all 23 command logs.",
    "new_remote_actions": 0,
    "Soong_invoked": False,
    "full_framework_Java_Android_JNI_qualified": False,
    "runtime_qualification_inherited": False,
    "production_ready": False,
    "cleanup_eligible": False,
}
body = (json.dumps(summary, indent=2) + "\n").encode()
out = ACTUAL / "qualification-final.json"
assert not out.exists(), "immutable actual qualification already exists"
out.write_bytes(body)
print(json.dumps({"path": str(out), "bytes": len(body), "sha256": sha(body), "state": summary["state"], "admitted_MemAvailable_bytes": mem_available, "commands": 23, "independent_gates": 19, "Soong_invoked": False}))
