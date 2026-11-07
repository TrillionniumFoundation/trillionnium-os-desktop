#!/usr/bin/env python3
"""Local actual-evidence/claim controls. Never invokes a capture or device tool."""
import sys
sys.dont_write_bytecode = True
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[2]


def need(test, code):
    if not test:
        raise RuntimeError(code)


def census():
    result = {}
    for name in os.listdir("/proc/self/fd"):
        fd = int(name)
        try:
            info = os.fstat(fd)
            link = os.readlink("/proc/self/fd/" + name)
            result[name] = {"link": link, "stat": [getattr(info, key) for key in
                ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_rdev")],
                "fd_flags": fcntl.fcntl(fd, fcntl.F_GETFD), "status_flags": fcntl.fcntl(fd, fcntl.F_GETFL)}
        except OSError as error:
            need(error.errno == 9 and not Path("/proc/self/fd/" + name).exists(), "FD_CENSUS_AMBIGUOUS")
    return result


def rejects(operation, reason):
    try:
        operation()
    except RuntimeError as error:
        need(reason in str(error), "WRONG_REJECTION:" + str(error))
        return str(error)
    raise RuntimeError("NEGATIVE_CONTROL_WAS_ACCEPTED")


def main():
    before = census()
    path = HERE / "permission_capture_gate.py"
    gate = types.ModuleType("reviewed46_local_gate")
    gate.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), "exec"), gate.__dict__)
    g, plan, loaded = gate.load_closure()
    cases = []
    need(len(loaded) == 14 and len(plan["target_packages"]) == 46 and
         sum(len(row["Android_commands"]) for row in plan["batches"]) == 106,
         "FULL14_SOURCE_CLOSURE_REQUIRED")
    need(loaded[14]["row"]["targets"] == ["com.example.ndk_tests"] and
         all(loaded[number]["request"]["packages"] == loaded[1]["request"]["packages"] for number in loaded) and
         len(loaded[1]["request"]["packages"]) == 49, "FULL49_AND_NDK14_REQUIRED")
    cases.append({"name": "actual_installer_readback_original13_ndk14_exact_source_closure", "pass": True})
    need(not gate.LEDGER.exists(), "REAL46_LEDGER_ALREADY_EXISTS_NO_TEST_CLAIM")
    state = gate.inspect(g, plan, loaded)
    need(state["state"] == "NEXT_READY" and state["next"]["batch"] == 1 and not gate.LEDGER.exists(), "READONLY_STATUS_CREATED_STATE")
    cases.append({"name": "real_new_ledger_status_has_no_claim_or_submission", "pass": True})
    with tempfile.TemporaryDirectory(prefix="permission46-owned-local-control-") as temp:
        ledger = Path(temp) / "ledger"
        state = gate.inspect(g, plan, loaded, ledger)
        claimed = gate.claim(g, state, ledger)
        need(claimed["state"] == "CLAIMED_NOT_SUBMITTED" and claimed["batch"] == 1 and
             claimed["processes_submitted"] == 0 and (ledger / "batch-01/intent.json").is_file(), "ACTUAL_LOCAL_OEXCL_CLAIM_FAILED")
        stopped = gate.inspect(g, plan, loaded, ledger)
        need(stopped["state"] == "STOP_UNSETTLED_BATCH" and stopped["batch"] == 1, "UNSETTLED_INTENT_MUST_STOP")
        rejects(lambda: gate.claim(g, stopped, ledger), "NO_CLAIM_AFTER_FAILED_UNKNOWN_OR_COMPLETE")
        need(not (ledger / "batch-02").exists(), "NO_ADVANCE_WHILE_UNSETTLED")
        cases.append({"name": "own_temporary_claim_is_durable_and_unsettled_stops_next_claim", "pass": True})
    failed = json.loads((PROJECT / "successor_audit_requests/actual/permissions-fixed45-r1/batch-03/terminal.original.json").read_bytes())
    rejects(lambda: gate.terminal_gate(g, failed, failed["job_id"], b""), "EXACT_SUCCESSFUL_DURABLE_TERMINAL_REQUIRED")
    cases.append({"name": "actual_old45_failed_terminal_is_not_success", "pass": True})
    actual_path = PROJECT / "successor_audit_requests/revisions/permissions-microg-b02-correction-r1/actual/artifact.original.json"
    actual_raw = actual_path.read_bytes()
    need(len(actual_raw) == 40751 and hashlib.sha256(actual_raw).hexdigest() ==
         "60006128ea7afdfd2fe81b3f408147d948cbedf2a0a4c5a4011b03f34989a5e3", "ACTUAL_MICROG_CONTROL_CHANGED")
    actual = json.loads(actual_raw)
    row = actual["android_commands"][1]
    root = row["stdout"]["path"].rsplit("/", 1)[0]
    need(row["stdout"]["bytes"] == 1478016, "ACTUAL_LARGE_CAPTURE_REQUIRED")
    gate.stream_pair(row, row, root, "android-02", 2097152)
    rejects(lambda: gate.stream_pair(row, row, root, "android-02"), "RAW_STREAM_PIN_MUST_MATCH_ACTUAL_COMMAND_CAPTURE")
    cases.append({"name": "actual_1478016_microg_stream_uses_only_explicit_2mib_limit_default_rejects", "pass": True})
    rejects(lambda: loaded[2]["wrapper"].worker_gate(actual, 0), "RAW_PERMISSION_SERVICE_CAPTURE_AND_RETIREMENT_GATE_FAILED")
    cases.append({"name": "actual_old_microg_pass_cannot_qualify_new49_capture", "pass": True})
    for pin in plan["preserved_old45_stop"]:
        gate.local_pin(g, pin)
    for number, item in loaded.items():
        expected = item["wrapper"].CAPTURE_BINDING["microg_capture_policy"]
        need((expected is not None) == (number == 2), "ONLY_BATCH02_HAS_BUDGET_EXCEPTION")
    cases.append({"name": "old_stop_exact_and_only_microg_batch_has_exception", "pass": True})
    after = census()
    need(before == after, "WHOLE_LOCAL_FD_IDENTITY_SET_CHANGED")
    print(json.dumps({"schema": "pocket4-fixed46-bound-local-controls-v1", "ok": True, "cases": cases,
        "uid": os.getuid(), "euid": os.geteuid(), "whole_process_descriptors_before": before,
        "whole_process_descriptors_after": after, "Main_commands": 0, "remote_submissions": 0,
        "actual_ledger_claims_created": 0, "own_temporary_claims_created": 1,
        "permission_observations_created": 0, "production_ready": False}, ensure_ascii=True, sort_keys=True))


if __name__ == "__main__":
    main()
