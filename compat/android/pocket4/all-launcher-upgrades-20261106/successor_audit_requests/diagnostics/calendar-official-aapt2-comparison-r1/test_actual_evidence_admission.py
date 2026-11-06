#!/usr/bin/env python3
"""Read-only local evidence control; no host or Android worker entry."""
import hashlib
import json
import os
from pathlib import Path


def census():
    rows = {}
    for name in os.listdir("/proc/self/fd"):
        try:
            value = os.fstat(int(name))
            rows[name] = [os.readlink("/proc/self/fd/" + name), value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid]
        except OSError as error:
            if error.errno not in (2, 9):
                raise
    return rows


def pin(path):
    raw = path.read_bytes()
    return raw, {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def main():
    here = Path(__file__).resolve().parent
    before = census()
    raw, source = pin(here / "diagnose_calendar_and_fcitx.py")
    assert source == {"bytes": 62331, "sha256": "191692dda06eaaaa3fcbe024399985cf2ac6a547b567fd25967c96a1b31b09f6"}
    namespace = {"__name__": "local_actual_evidence_admission_only", "__file__": str(here / "diagnose_calendar_and_fcitx.py")}
    exec(compile(raw, namespace["__file__"], "exec"), namespace)
    request = json.loads((here / "request.review-only.json").read_bytes())
    namespace["validate_request"](request)
    stdout, stdout_pin = pin(here / "inputs/official-host.stdout.original.jsonl")
    terminal, terminal_pin = pin(here / "inputs/official-host.terminal.original.json")
    proof = namespace["verify_official_host_proof"](stdout, terminal)
    assert proof["candidate"]["file"]["st_ino"] == 110244195
    assert proof["candidate"]["file"]["st_ctime_ns"] == 1793993457351638049
    legacy_proof = json.loads((here / "inputs/aapt2-proof.outer.original.json").read_bytes())
    legacy_terminal = json.loads((here / "inputs/aapt2-proof.terminal.original.json").read_bytes())
    legacy_candidate = request["legacy_candidate_aapt2"]
    namespace["verify_actual_proof"](legacy_proof, legacy_terminal, legacy_candidate)
    namespace["verify_candidate_inventory"](legacy_candidate, json.loads((here / "inputs/inventory.original.json").read_bytes()))
    assert len(legacy_proof["static_dependency_graph"]) == 19 and len(proof["static_dependency_graph"]) == 7
    earlier, earlier_pin = pin(here.parent / "calendar-resource-parser-r1/candidate-r3/actual/worker.artifact.original.json")
    assert earlier_pin == {"bytes": 58074, "sha256": "6afc779a4fcfa5e8f0d59470ef101330ad1dd8f4ba4d781b121abd62df3ece90"}
    old = json.loads(earlier)
    badging = [row for row in old["commands"] if row["name"] == "badging"]
    assert len(badging) == 2 and all(row["returncode"] == 0 for row in badging)
    calendar = next(row for row in badging if row["package"] == "com.android.calendar")
    assert calendar["stderr"]["bytes"] == 2486748
    assert calendar["stderr"]["sha256"] == "256a56fc10b83a17488572225c07cc2f04a1f5a54b06db033d578f21c18df631"
    assert namespace["clean_official_badging_observations"](old["commands"]) is False
    packet = json.loads((here / "process-request.review-only.json").read_bytes())
    assert packet["args"][:-1] == ["-n", "/usr/bin/python3", "-I", "-B", "-c"]
    assert packet["args"][-1].encode() == (here / "stage_and_run_comparison.py").read_bytes()
    payload = json.loads(packet["stdin"])
    assert len(packet["stdin"].encode()) <= 262144
    for row in payload["files"]:
        assert row["text"].encode() == (here / row["name"]).read_bytes()
    after = census()
    assert before == after
    result = {
        "schema": "pocket4-official-calendar-actual-evidence-admission-control-v1", "ok": True,
        "source": source, "official_host_stdout": stdout_pin, "official_host_terminal": terminal_pin,
        "actual_official_final_stdout_and_terminal_accepted": True,
        "actual_official_stat_integer_precision_preserved": True,
        "original_failed_Debian_help_evidence_accepted_without_reclassification": True,
        "legacy19_and_official7_graphs_both_present": True,
        "prior_Calendar_result": earlier_pin,
        "actual_prior_returncode0_with_2486748_stderr_bytes_rejected_as_clean": True,
        "exact_stage_packet_closure_passed": True,
        "FDs_before": len(before), "FDs_after": len(after), "original_descriptor_identities_restored": before == after,
        "host_tools_executed": 0, "Main_reads": 0, "Android_commands": 0,
        "new_APK_observation_performed": False, "runtime_worker_invoked": False,
        "actual_new_resource_comparison_result": "NOT_OBSERVED"
    }
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))


if __name__ == "__main__":
    main()
