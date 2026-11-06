#!/usr/bin/env python3
"""Independent native stop/retire/start repair. Default is preflight only.

Importing this module performs no I/O. Only main() loads the original frozen
runtime reader. The historical failed restart is never retried or rewritten.
"""
from __future__ import annotations

import argparse
import base64
import errno
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import sys
import time
import types

SOURCE = "/home/alex/work/pocket4-cell-recovery-preflight-20261106-r1/source"
MANIFEST = "b97002660594ad0ef6e7b453927b8c5b19cba49a5873bc133199d790019b1f9f"
ORIGINAL_ROOT = "/home/alex/work/pocket4-cell-successor-20261106-r1"
ORPHAN_ROOT = "/home/alex/work/pocket4-orphan-cell-retirement-20261106-r1"
WRAPPER = "/usr/local/libexec/droidloom-compat/unshare"
WRAPPER_SHA = "df2365c026cc578048ce22ebd1b22bfefc25ccc144146683d845ec828c61bf1f"
SOURCE_ROWS = {
    "unshare_wrapper.py": (6290, WRAPPER_SHA),
    "pidns_fixture.py": (1013, "da61ecac210799f4626cdc7afa83476049374f4a36e9b87ba0e6a92e664016d1"),
    "test_host_lifecycle.py": (16463, "86195ddeeed6d1a6f2ee20913e180c6259b6ff1bd36121abfd3369345a644649"),
}
ORIGINAL_PINS = {
    "predecessor.private.json": (110738, "6b781af9d0d037e14d7f4b3174937f3a101ab4cf313b7c5c34fec1c13df9dec3"),
    "native-restart-receipt.private.json": (1060, "d329733b4073662320f2c8839d8ef43053e095a9429cd810865e7f44daec2733"),
    "result.json": (1010, "eaf9a964fc33b77e3a8841a51b5b2e4cb4f15fa4edd247f943a336f8bbdcac0f"),
}
ORPHAN_PIN = {
    "path": ORPHAN_ROOT + "/result.json", "bytes": 3043,
    "sha256": "4c322a72ea61f3e7ff7e9c369c7996256beed8c74be1cd8c4b10524da285008d",
}
OBSERVATION_BYTES = 49955
OBSERVATION_SHA = "8939bf273b3feb6d5fb4360d2739e087ad42c1bb07ec692913eafee433a3d189"
KNOWN_JOBS = frozenset("""
1a1b037d386-fc05-6f27 1a1b04a230a-fc05-6f89 1a1b04ec429-fc05-6fa2
1a1b053bc6d-fc05-6fbe 1a1b0607f86-fc05-700f 1a1b063d4cc-fc05-702e
1a1b06a0f7a-fc05-705d 1a1b06daad3-fc05-7078 1a1b06e9fb8-fc05-707e
1a1b076fb52-fc05-70ad 1a1b07a3192-fc05-70bb 1a1b07b20d4-fc05-70c6
1a1b07be9b7-fc05-70ce 1a1b0802b05-fc05-70f1 1a1b082d7fd-fc05-7109
1a1b083d024-fc05-7115 1a1b092eb36-fc05-7170 1a1b0943dea-fc05-7179
1a1b097d4da-fc05-7192 1a1b09ac6ca-fc05-71a4 1a1b09dad9f-fc05-71bb
1a1b0a21e45-fc05-71db 1a1b0a790e3-fc05-71f9 1a1b0ab2fab-fc05-720f
1a1b0b7efb4-fc05-7259 1a1b0b9ff7a-fc05-7262
""".split())
FLOW_ROOTS = (
    "/home/alex/work/pocket4-bilibili-owned-qa-r9-flow-474d7477074ea01fbc986e0d867924c1",
    "/home/alex/work/pocket4-eight-apps-upgrade-20261106-r1/com.lianjia.beike-bound-install-r1",
    "/home/alex/work/pocket4-eight-apps-upgrade-20261106-r1/com.lianjia.beike-bound-install-r2",
    "/home/alex/work/pocket4-eight-apps-upgrade-20261106-r1/com.lianjia.beike-bound-install-r3",
    "/home/alex/work/pocket4-eight-apps-upgrade-20261106-r1/com.rytong.ceair-bound-install-r1",
    "/home/alex/work/pocket4-launcher-official-candidates-20261106-r2/com.rytong.airchina-bound-install-r1",
    "/home/alex/work/pocket4-launcher-official-candidates-20261106-r2/com.tencent.mm-bound-install-r1",
)
CURRENT_PIDS = {
    "launcher": (2747275, 99050420), "android_init": (2747279, 99050422),
    "zygote64": (2748689, 99051055), "system_server": (2748837, 99051107),
    "surfaceflinger": (2748708, 99051057), "composer": (2748094, 99050555),
    "daemon": (3588022, 80796995), "presenter": (3588024, 80796995),
}
CURRENT_PARENT = 2747278
EXECUTION_CLAIM = "/home/alex/work/pocket4-independent-lifecycle-r2-20261106-execution-claim.json"
STAT_KEYS = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
             "st_size", "st_mtime_ns", "st_ctime_ns")
CASE_NAMES = (
    "actual_fork_parent_mismatch_rejected_before_exec",
    "real_native_command_arguments_preserved",
    "TERM_then_supervisor_fallback",
    "wrapper_SIGKILL_without_TERM",
)


class Reject(RuntimeError):
    pass


def need(value, reason):
    if not value:
        raise Reject(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
                      allow_nan=False).encode("utf-8")


def parse(raw):
    def pairs(rows):
        out = {}
        for key, value in rows:
            need(key not in out, "DUPLICATE_JSON_KEY")
            out[key] = value
        return out
    def constant(_):
        raise Reject("NONFINITE_JSON")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def stat_record(fd):
    info = os.fstat(fd)
    return {key: getattr(info, key) for key in STAT_KEYS}


def boot_source(path, expected, maximum):
    """Bootstrap only an explicitly fixed root-owned source; no Android access."""
    need(path.startswith("/") and all(x not in ("", ".", "..") for x in path[1:].split("/")),
         "SOURCE_PATH_REQUIRED")
    fds = []
    try:
        parent = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        fds.append(parent)
        parts = path[1:].split("/")
        for name in parts[:-1]:
            parent = os.open(name, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
                             dir_fd=parent)
            fds.append(parent)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK,
                     dir_fd=parent)
        fds.append(fd)
        before = stat_record(fd)
        need(stat.S_ISREG(before["st_mode"]) and before["st_nlink"] == 1 and
             before["st_uid"] == 0 and 0 < before["st_size"] <= maximum, "ROOT_SOURCE_FILE_REQUIRED")
        data, end = bytearray(), time.monotonic() + 10
        while len(data) <= maximum:
            need(time.monotonic() < end, "SOURCE_DEADLINE")
            block = os.read(fd, min(65536, maximum + 1 - len(data)))
            if not block:
                break
            data.extend(block)
        current = os.stat(parts[-1], dir_fd=parent, follow_symlinks=False)
        need(len(data) == before["st_size"] and stat_record(fd) == before and
             {key: getattr(current, key) for key in STAT_KEYS} == before and sha(data) == expected,
             "SOURCE_BYTES_OR_IDENTITY_CHANGED")
        return bytes(data)
    finally:
        for fd in reversed(fds):
            os.close(fd)


def load_core():
    manifest_raw = boot_source(SOURCE + "/SOURCE_PINS.json", MANIFEST, 65536)
    manifest = parse(manifest_raw)
    row = manifest["files"]["successor_runtime.py"]
    raw = boot_source(SOURCE + "/successor_runtime.py", row["sha256"], 131072)
    need(len(raw) == row["bytes"], "FROZEN_CORE_LENGTH")
    module = types.ModuleType("immutable_repair_r2_core")
    module.__file__ = SOURCE + "/successor_runtime.py"
    exec(compile(raw, module.__file__, "exec"), module.__dict__)
    encoded = module.configure(SOURCE, MANIFEST)
    return module, encoded


def pin(core, row, maximum=4 * 1024 * 1024):
    need(type(row) is dict and {"path", "bytes", "sha256"} <= set(row),
         "COMPLETE_ARTIFACT_PIN_REQUIRED")
    need(type(row["bytes"]) is int and 0 < row["bytes"] <= maximum, "ARTIFACT_SIZE_BOUND")
    raw = core.pinned_record({key: row[key] for key in ("path", "bytes", "sha256")}, maximum)
    need(len(raw) == row["bytes"], "ACTUAL_ARTIFACT_SIZE_DIFFERS")
    return raw


def pin_document(core, row, maximum=4 * 1024 * 1024):
    return parse(pin(core, row, maximum))


def file_record(core, row):
    need(type(row.get("stat")) is dict and set(row["stat"]) == set(STAT_KEYS),
         "EXACT_FULL_STAT_REQUIRED")
    raw, info = core.host_read(row["path"], max(row["bytes"], 1), row["sha256"], row["bytes"])
    need(len(raw) == row["bytes"] and info == row["stat"], "DEPLOYED_FILE_PATH_OR_STAT_CHANGED")
    return {"path": row["path"], "bytes": len(raw), "sha256": sha(raw), "stat": info}


def native_argv(core, operation):
    need(operation in ("help", "start_help", "stop_help", "status", "stop", "start"),
         "CLOSED_REPAIRED_NATIVE_OPERATION_SET")
    argv = ["/usr/bin/droidloomctl", "--cell", "--json"]
    if operation == "help":
        argv += ["--help"]
    elif operation in ("start_help", "stop_help"):
        argv += [operation.removesuffix("_help"), "--help"]
    else:
        argv.append(operation)
        if operation == "start":
            argv += ["--spec", core.CONFIG]
    return core.as_user(argv)


def actual_native(raw, command, operation):
    need(operation in ("status_running", "status_stopped", "start", "stop"), "NATIVE_RESPONSE_OPERATION")
    need(command.get("complete") is True and command.get("joined") is True and
         command.get("returncode") == 0 and command.get("errors") == [] and
         command.get("stdout_eof") is True and command.get("stderr_eof") is True and
         command.get("stderr_bytes") == 0 and command.get("stdout_bytes") == len(raw) and
         command.get("stdout_sha256") == sha(raw), "NATIVE_JOIN_AND_EXACT_STDIO_REQUIRED")
    value = parse(raw)
    need(type(value) is dict and value.get("ok") is True and
         not value.get("outcome_unknown", False), "ACTUAL_NATIVE_SUCCESS_REQUIRED")
    if operation in ("stop", "status_stopped"):
        need(value.get("state") == "stopped" and value.get("host_pid") is None,
             "ACTUAL_NATIVE_STOPPED_WITH_NO_OWNER_REQUIRED")
    else:
        need(value.get("state") == "running" and type(value.get("host_pid")) is int and
             value["host_pid"] > 1, "ACTUAL_NATIVE_RUNNING_OWNER_REQUIRED")
    return value


def validate_terminal(job_id, raw, *, require_success=False):
    need(type(raw) is str and 0 < len(raw.encode("utf-8")) <= 65536, "BOUNDED_ORIGINAL_TERMINAL_TEXT")
    value = parse(raw)
    need(value.get("job_id") == job_id and value.get("state") in ("succeeded", "failed") and
         type(value.get("exit_code")) is int and value.get("output_complete") is True and
         value.get("output_durable") is True and value.get("terminal_publication_confirmed") is True and
         value.get("timed_out") is False and value.get("automatic_retry") is False,
         "AUTHORITATIVE_SETTLED_RUNTIME_TERMINAL_REQUIRED")
    need((value["state"] == "succeeded") == (value["exit_code"] == 0), "TERMINAL_STATE_EXIT_DIFFERS")
    if require_success:
        need(value["state"] == "succeeded", "WRAPPER_HOST_TEST_AND_DEPLOY_SUCCESS_REQUIRED")
    return value


def all_closed(row):
    return (type(row) is dict and type(row.get("acquired")) is int and row["acquired"] >= 0 and
            row.get("closed") == row["acquired"] and row.get("remaining") == 0 and row.get("errors") == [])


def equal_process_after_reparent(expected, current, permitted_parent):
    if type(current) is not dict or set(current) != set(expected):
        return False
    return current["parent_host_pid"] == permitted_parent and all(
        current[key] == value for key, value in expected.items() if key != "parent_host_pid")


def signal_decision(*, native_stopped, owner_dead, init_dead, parent_dead,
                    expected_init, current_init, expected_parent, current_parent):
    """A positive decision licenses only the already-held exact init pidfd."""
    need(native_stopped is True and owner_dead is True, "NATIVE_STOP_AND_OWNER_DEATH_REQUIRED")
    if init_dead and parent_dead:
        return "ALREADY_RETIRED"
    need(init_dead is False and parent_dead is False, "INCOMPLETE_ORPHAN_PAIR_REQUIRES_REVIEW")
    need(current_init == expected_init and
         equal_process_after_reparent(expected_parent, current_parent, 1),
         "EXACT_REPARENTED_INIT_AND_NATIVE_PARENT_REQUIRED")
    return "SIGNAL_EXACT_INIT_PIDFD_ONCE"


def select_namespace_init(rows, owner_pid):
    """Filter namespace PID 1; neither subcontext nor ueventd is Android init."""
    candidates = [row for row in rows if row.get("executable") == "/system/bin/init" and
                  row.get("cmdline", [None])[0] == "/init" and
                  row.get("namespace_pids", [None])[-1] == 1 and row.get("uids") == [0] * 4]
    need(len(candidates) <= 1, "SUCCESSOR_NAMESPACE_PID1_AMBIGUOUS")
    if not candidates:
        return None
    row = candidates[0]
    need(row["host_pid"] != owner_pid, "NATIVE_OWNER_CANNOT_BE_ANDROID_INIT")
    return row


def namespace_members(core, namespace):
    end = time.monotonic() + 8
    entries = os.listdir("/proc")
    need(len(entries) <= 65536, "PROC_SCAN_COUNT_BOUND")
    out = []
    for name in entries:
        need(time.monotonic() < end, "PROC_SCAN_TIME_BOUND")
        if not name.isdecimal():
            continue
        try:
            if os.readlink("/proc/" + name + "/ns/pid") == namespace:
                row = core.E._stat(int(name))
                out.append({"host_pid": row[0], "parent_host_pid": row[1],
                            "start_ticks": row[2], "state": row[3]})
        except (FileNotFoundError, ProcessLookupError):
            continue
    return out


def ns_empty_samples(core, namespaces):
    need(len(namespaces) == 2 and len(set(namespaces)) == 2, "TWO_DISTINCT_HISTORICAL_NAMESPACES")
    rows = []
    for _ in range(2):
        value = {name: namespace_members(core, name) for name in namespaces}
        need(all(not members for members in value.values()), "HISTORICAL_ANDROID_NAMESPACE_NOT_EMPTY")
        rows.append({"monotonic_ns": time.monotonic_ns(), "members": value})
        time.sleep(.05)
    return rows


class HeldParent:
    """Only a pidfd survives teardown; the parent's executable view is temporary."""
    def __init__(self, core, pool, expected, native_record):
        self.core, self.pool, self.expected = core, pool, expected
        need(core.E.process_identity(expected["host_pid"]) == expected, "PARENT_BINDING_BEFORE_PIDFD")
        self.fd = pool.own(os.pidfd_open(expected["host_pid"], 0))
        need(not core.pidfd_dead(self.fd) and core.E.process_identity(expected["host_pid"]) == expected,
             "PARENT_CHANGED_WHILE_HOLDING_PIDFD")
        procfd = core.open_host(pool, "/proc/" + str(expected["host_pid"]), os.O_PATH | os.O_DIRECTORY)
        try:
            fd = pool.own(os.open("exe", os.O_RDONLY | os.O_CLOEXEC, dir_fd=procfd))
        finally:
            pool.close(procfd)
        try:
            actual = core.hash_fd(fd, 32 * 1024 * 1024, time.monotonic() + 10)
            need(actual["sha256"] == native_record["sha256"] and actual["bytes"] == native_record["bytes"],
                 "ACTUAL_UNSHARE_PARENT_EXECUTABLE_DIFFERS")
            need(actual["file"] == native_record["stat"], "ACTUAL_UNSHARE_PARENT_INODE_DIFFERS")
        finally:
            pool.close(fd)
        self.verify()

    def verify(self):
        need(not self.core.pidfd_dead(self.fd) and
             self.core.E.process_identity(self.expected["host_pid"]) == self.expected,
             "HELD_PARENT_IDENTITY_CHANGED")


def validate_packet(core, packet):
    keys = {"schema", "source", "output_root", "current_observation", "wrapper_deployment",
            "terminals", "wrapper_jobs", "additional_settled_jobs", "coordination"}
    need(type(packet) is dict and set(packet) == keys and
         packet["schema"] == "pocket4-independent-native-repair-packet-v2", "CLOSED_R2_PACKET_REQUIRED")
    need(packet["coordination"] == {
        "all_runtime_workers_settled": True, "agents_runtime_frozen": True,
        "unresolved_runtime_start_attempts": [], "host_only_downloads_excluded": True,
    }, "EXPLICIT_CURRENT_COORDINATOR_FREEZE_REQUIRED")
    need(not os.path.lexists(EXECUTION_CLAIM), "R2_EXECUTION_ALREADY_CLAIMED_NO_RETRY")
    output = packet["output_root"]
    core.path_parts(output)
    need(output.startswith("/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-") and
         output.count("/") == 4 and not os.path.lexists(output), "FRESH_UNIQUE_R2_OUTPUT_ROOT_REQUIRED")
    observed = packet["current_observation"]
    need(observed["bytes"] == OBSERVATION_BYTES and observed["sha256"] == OBSERVATION_SHA,
         "EXACT_CURRENT_TWO_SAMPLE_OBSERVATION_REQUIRED")
    jobs = packet["wrapper_jobs"]
    need(type(jobs) is dict and set(jobs) == {"host_tests", "deployment"} and
         len(set(jobs.values())) == 2 and not (set(jobs.values()) & KNOWN_JOBS),
         "DISTINCT_ACTUAL_HOST_TEST_AND_DEPLOYMENT_JOBS_REQUIRED")
    extras = packet["additional_settled_jobs"]
    need(type(extras) is list and len(extras) <= 24 and len(set(extras)) == len(extras) and
         not (set(extras) & (KNOWN_JOBS | set(jobs.values()))), "EXPLICIT_ADDITIONAL_SETTLED_JOB_SET")
    required = KNOWN_JOBS | set(jobs.values()) | set(extras)
    need(type(packet["terminals"]) is dict and set(packet["terminals"]) == required,
         "EXACT_ALL_KNOWN_PLUS_SUBSEQUENT_TERMINAL_SET_REQUIRED")
    for job_id, raw in packet["terminals"].items():
        need(type(job_id) is str and 1 <= len(job_id) <= 128 and
             all(c in "0123456789abcdef-" for c in job_id), "DURABLE_JOB_ID_SHAPE")
        validate_terminal(job_id, raw, require_success=job_id in jobs.values())
    need(packet["source"]["path"] == os.path.abspath(__file__), "EXACT_EXECUTED_R2_SOURCE_PATH")
    pin(core, packet["source"], 262144)
    return required


def wrapper_evidence(core, deployment_pin):
    deployed = pin_document(core, deployment_pin, 262144)
    need(deployed.get("schema") == "pocket4-compat-unshare-deployment-result-v1" and
         deployed.get("ok") is True and deployed.get("new_source_runtime_activated") is False,
         "ACTUAL_INACTIVE_WRAPPER_DEPLOYMENT_RECEIPT_REQUIRED")
    for key in ("Android_commands", "namespace_entries", "UI_actions", "installs",
                "restarts", "existing_process_signals"):
        need(type(deployed.get(key)) is int and deployed[key] == 0, "DEPLOYMENT_ACTION_BOUNDARY_" + key)
    need(deployed["new_wrapper"]["path"] == WRAPPER and deployed["new_wrapper"]["bytes"] == 6290 and
         deployed["new_wrapper"]["sha256"] == WRAPPER_SHA, "EXACT_REVIEWED_WRAPPER_CANDIDATE")
    new_record = file_record(core, deployed["new_wrapper"])
    need(stat.S_ISREG(new_record["stat"]["st_mode"]) and new_record["stat"]["st_nlink"] == 1 and
         new_record["stat"]["st_uid"] == 0 and stat.S_IMODE(new_record["stat"]["st_mode"]) == 0o755,
         "DEPLOYED_ROOT_EXECUTABLE_WRAPPER_REQUIRED")
    need(deployed["old_wrapper"]["path"] == WRAPPER and
         deployed["old_wrapper"]["bytes"] == 560 and
         deployed["old_wrapper"]["sha256"] == "fe3a685034ed0dc948597436965dfd35ea183fc2b0519d9b0c5730c79d7c060b" and
         deployed["retained_old_wrapper"]["bytes"] == deployed["old_wrapper"]["bytes"] and
         deployed["retained_old_wrapper"]["sha256"] == deployed["old_wrapper"]["sha256"] and
         deployed["retained_old_wrapper"]["path"] != WRAPPER, "ORIGINAL_WRAPPER_MUST_REMAIN_RETAINED")
    file_record(core, deployed["retained_old_wrapper"])
    manifest = pin_document(core, deployed["source_manifest"], 65536)
    need(manifest.get("schema") == "pocket4-compat-wrapper-repair-source-v1" and
         set(manifest) == {"schema", "files"} and set(manifest["files"]) == set(SOURCE_ROWS),
         "EXACT_REVIEWED_WRAPPER_SOURCE_CLOSURE")
    for name, expected in SOURCE_ROWS.items():
        need(manifest["files"][name] == {"bytes": expected[0], "sha256": expected[1]},
             "WRAPPER_SOURCE_CLOSURE_DIFFERS")
    test = pin_document(core, deployed["host_test_receipt"], 524288)
    need(test.get("schema") == "pocket4-compat-wrapper-real-host-controls-v1" and
         test.get("ok") is True and test.get("errors") == [] and
         test.get("test_revision") == "r3-inline-pinned-fixture" and
         test.get("fixture_transport") == "pinned_utf8_source_via_python_c" and
         test["candidate"]["bytes"] == 6290 and test["candidate"]["sha256"] == WRAPPER_SHA and
         test.get("fixture_sha256") == SOURCE_ROWS["pidns_fixture.py"][1] and
         type(test.get("FD_count_before")) is int and
         test["FD_count_before"] == test.get("FD_count_after"), "REAL_WRAPPER_HOST_TEST_RECEIPT_REQUIRED")
    need(test.get("production_wrapper_deployed") is False and
         test.get("Pocket4_runtime_qualified") is False and
         test.get("Android_commands") == 0 and test.get("existing_namespace_entries") == 0,
         "HOST_TEST_SCOPE_MUST_EXCLUDE_MAIN")
    cases = test["cases"]
    need(type(cases) is list and len(cases) == 4 and
         [row.get("name") for row in cases] == list(CASE_NAMES) and
         all(row.get("passed") is True for row in cases), "ALL_FOUR_REAL_WRAPPER_CONTROLS_REQUIRED")
    namespaces = []
    for row in cases[-2:]:
        need(row.get("all_four_original_test_pidfds_dead") is True and
             row.get("unrelated_same_process_group_sentinel_unchanged") is True and
             row.get("native_child_signal_sent_by_test") is False and
             row.get("namespace_init_or_leaf_signal_sent_by_test") is False and
             row.get("cleanup_error") is None and
             row["pidfds"]["acquired"] == row["pidfds"]["closed"] == 5,
             "REAL_NAMESPACE_AND_UNRELATED_PROCESS_CONTROLS_REQUIRED")
        namespaces.append(row["new_pid_namespace"])
    need(len(set(namespaces)) == 2, "INDEPENDENT_REAL_NAMESPACE_TESTS_REQUIRED")
    native = deployed["native_unshare"]
    need(native["path"] == "/usr/bin/unshare" and native.get("file_capabilities_absent") is True and
         test["native_unshare"]["sha256"] == native["sha256"] and
         test["native_unshare"]["bytes"] == native["bytes"] and
         test["native_unshare"]["help_sha256"] == native["help_sha256"] and
         test["native_unshare"].get("file_capabilities_absent") is True,
         "TESTED_AND_DEPLOYED_NATIVE_UNSHARE_MUST_MATCH")
    file_record(core, native)
    return deployed, test


def original_chain(core, observation_pin):
    pins = {name: {"path": ORIGINAL_ROOT + "/" + name, "bytes": row[0], "sha256": row[1]}
            for name, row in ORIGINAL_PINS.items()}
    docs = {name: pin_document(core, row) for name, row in pins.items()}
    previous = docs["predecessor.private.json"]
    failed = docs["result.json"]
    receipt = docs["native-restart-receipt.private.json"]
    need(previous.get("schema") == "pocket4-lifecycle-preflight-v1" and
         previous.get("source_manifest_sha256") == MANIFEST and
         previous["plan_sha256"] == sha(canonical(previous["plan"])), "FIXED_R1_PREDECESSOR_REQUIRED")
    need(failed.get("schema") == "pocket4-owned-cell-recovery-result-v1" and
         failed.get("ok") is False and failed.get("preflight_passed") is True and
         failed.get("restart_attempted") is True and failed.get("outcome_unknown") is True and
         failed.get("identity_qualified") is False and failed.get("automatic_retry") is False and
         all_closed(failed["observation_fds"]) and all_closed(failed["lease_fds"]) and
         any(row.get("code") == "OLD_CELL_OR_NATIVE_OWNER_STILL_ALIVE" for row in failed["errors"]),
         "ORIGINAL_FAILED_UNKNOWN_RESTART_MUST_REMAIN_UNCHANGED")
    need(receipt.get("schema") == "pocket4-native-restart-actual-receipt-v1" and
         receipt["command"]["argv"] == core.native_argv("restart") and
         receipt["stderr_utf8"] == "", "ORIGINAL_NATIVE_RESTART_RECEIPT_REQUIRED")
    native = actual_native(receipt["stdout_utf8"].encode(), receipt["command"], "start")
    attempted = pin_document(core, receipt["attempt"], 65536)
    need(receipt["attempt"]["path"] == ORIGINAL_ROOT + "/restart-attempted.json" and
         attempted["predecessor"] == pins["predecessor.private.json"] and
         attempted["argv"] == core.native_argv("restart") and attempted.get("automatic_retry") is False,
         "ORIGINAL_RESTART_INTENT_PIN_REQUIRED")
    retired = pin_document(core, ORPHAN_PIN, 65536)
    old_rows = previous["runtime"]["held"]["process_snapshot"]["binding"]["processes"]
    need(retired.get("schema") == "pocket4-explicit-orphan-retirement-result-v1" and
         retired.get("ok") is True and retired.get("outcome_unknown") is False and
         retired.get("signal_attempted") is True and retired.get("old_namespace_members_after") == [] and
         retired.get("fresh_repair_pidfd_deaths") == {"orphan_init": True, "orphan_parent": True} and
         retired.get("original_restart_result_unchanged") is True and
         retired.get("original_pre_restart_pidfd_evidence_recreated") is False and
         retired.get("non_target_processes_unchanged") is True and
         retired["retired"]["android_init"] == old_rows["android_init"] and
         all_closed(retired["observation_fds"]) and all_closed(retired["lease_fds"]),
         "INDEPENDENT_EXACT_ORPHAN_RETIREMENT_SUCCESS_REQUIRED")
    observed = pin_document(core, observation_pin, 131072)
    need(observed.get("schema") == "pocket4-exact-cell-after-retirement-observation-v1" and
         observed.get("identity_qualified") is False and observed.get("guard_publication") is False and
         all_closed(observed["observation_fds"]), "ACTUAL_UNQUALIFIED_CURRENT_OBSERVATION_REQUIRED")
    for key in ("Android_commands", "UI_actions", "installs", "namespace_entries", "restarts", "signals"):
        need(observed[key] == 0, "CURRENT_OBSERVATION_MUST_BE_READ_ONLY")
    samples = observed["observations"]
    need(len(samples) == 2 and samples[1]["monotonic_ns"] > samples[0]["monotonic_ns"] and
         all(row.get("same_exact_init") is True for row in samples), "ORIGINAL_TWO_OBSERVATIONS_REQUIRED")
    roles = {"launcher": observed["expected_current_owner"],
             "daemon": old_rows["daemon"], "presenter": old_rows["presenter"]}
    for role, (pid, ticks) in CURRENT_PIDS.items():
        if role not in roles:
            matches = [[{k: v for k, v in row.items() if k != "state"}
                        for row in sample["roles"] if row.get("host_pid") == pid] for sample in samples]
            need(all(len(rows) == 1 for rows in matches) and matches[0] == matches[1],
                 "EXACT_CURRENT_PROCESS_MISSING_OR_CHANGED")
            roles[role] = matches[0][0]
        need(roles[role]["host_pid"] == pid and roles[role]["start_ticks"] == ticks,
             "EXACT_OBSERVED_CURRENT_PROCESS_REQUIRED")
    need(native["host_pid"] == roles["launcher"]["host_pid"] and
         roles["launcher"]["parent_host_pid"] == roles["daemon"]["host_pid"] and
         roles["android_init"] == observed["expected_current_init"] and
         roles["android_init"]["parent_host_pid"] == CURRENT_PARENT and
         roles["android_init"]["namespaces"]["pid"] == "pid:[4026533853]" and
         roles["android_init"]["namespace_pids"][-1] == 1,
         "ACTUAL_CURRENT_OWNER_AND_PID1_LINEAGE_REQUIRED")
    need(len(previous["apps"]) == 46, "ALL_46_EXISTING_APPS_REQUIRED")
    for name, version in (("com.lianjia.beike", 3067100), ("com.rytong.ceair", 239),
                          ("com.rytong.airchina", 75300), ("com.tencent.mm", 3220)):
        need(previous["apps"][name]["version_code"] == version, "FOUR_SUCCESSFUL_UPGRADES_MUST_REMAIN")
    core.unknown_evidence(previous["plan"])
    return {"pins": pins, "previous": previous, "failed": failed, "native": native,
            "orphan": retired, "observation": observed, "roles": roles,
            "attempt_pin": receipt["attempt"]}


def unchanged_history(core, chain, observation_pin):
    for row in chain["pins"].values():
        pin(core, row)
    pin(core, chain["attempt_pin"], 65536)
    pin(core, ORPHAN_PIN, 65536)
    pin(core, observation_pin, 131072)
    core.unknown_evidence(chain["previous"]["plan"])


def make_root(core, root):
    # Only a fresh sibling output, never an old flow or original restart root.
    core.path_parts(root)
    parent = root.rsplit("/", 1)[0]
    pool = core.FDs()
    try:
        pfd = core.open_host(pool, parent, os.O_RDONLY | os.O_DIRECTORY)
        os.mkdir(root.rsplit("/", 1)[1], mode=0o700, dir_fd=pfd)
        os.fsync(pfd)
        fd = core.open_host(pool, root, os.O_RDONLY | os.O_DIRECTORY)
        info = core.metadata(fd)
        need(info["st_uid"] == 0 and stat.S_IMODE(info["st_mode"]) == 0o700,
             "NEW_ROOT_PRIVATE_OUTPUT_REQUIRED")
        os.mkdir("source", mode=0o700, dir_fd=fd)
        os.mkdir("inputs", mode=0o700, dir_fd=fd)
        lock_fd = pool.own(os.open("flow.lock", os.O_RDWR | os.O_CREAT | os.O_EXCL |
                                  os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=fd))
        os.fchmod(lock_fd, 0o600)
        lock_info = core.metadata(lock_fd)
        need(stat.S_ISREG(lock_info["st_mode"]) and lock_info["st_uid"] == 0 and
             lock_info["st_nlink"] == 1 and lock_info["st_size"] == 0 and
             stat.S_IMODE(lock_info["st_mode"]) == 0o600, "NEW_OWN_FLOW_LOCK_REQUIRED")
        os.fsync(lock_fd)
        pool.close(lock_fd)
        os.fsync(fd)
    finally:
        pool.close_all()


def write_doc(core, root, name, value):
    return core.write_new(root + "/" + name, canonical(value) + b"\n")


def prepare_drain(core, leases, root, packet, chain):
    terminal_pins = []
    for job_id, raw in sorted(packet["terminals"].items()):
        terminal_pins.append(core.write_new(root + "/inputs/terminal-" + job_id + ".json",
                                           raw.encode("utf-8")))
    old = chain["previous"]["reviewed_drain"]
    locks = old["flow_locks"]
    need(len(locks) == 7 and {row["path"] for row in locks} ==
         {path + "/flow.lock" for path in FLOW_ROOTS}, "ALL_SEVEN_ORIGINAL_FLOW_LOCKS_REQUIRED")
    reviewed = {
        "schema": "pocket4-owned-worker-drain-v1", "boot_id": core.boot_id(),
        "reviewed_monotonic_ns": time.monotonic_ns(), "unresolved_start_attempts": [],
        "workers": [], "flow_locks": locks, "source_receipts": terminal_pins,
        "review_scope": "all-known-pocket4-UI-install-observer-restart-jobs",
    }
    drain_pin = write_doc(core, root, "reviewed-drain.private.json", reviewed)
    actual = core.reviewed_drain(leases, drain_pin)
    return actual, drain_pin, terminal_pins


def verify_leases(core, pool, action_identity, drain, new_flow):
    need(0 <= time.monotonic_ns() - drain["reviewed_monotonic_ns"] <= 300_000_000_000,
         "FRESH_COORDINATOR_REVIEW_EXPIRED_BEFORE_STOP")
    rows = [{"path": core.ACTION_LOCK, "identity": action_identity}, *drain["flow_locks"], new_flow]
    for row in rows:
        fd = core.open_host(pool, row["path"], os.O_RDWR)
        try:
            actual = core.metadata(fd)
            need({key: actual[key] for key in ("st_dev", "st_ino")} == row["identity"] and
                 actual["st_uid"] == 0 and actual["st_nlink"] == 1 and stat.S_ISREG(actual["st_mode"]),
                 "HELD_ACTION_OR_FLOW_LOCK_PATH_CHANGED")
        finally:
            pool.close(fd)


def native_query(core, root, name, operation, expect):
    raw, stderr, command = core.bounded_child(native_argv(core, operation), 10)
    row = {"schema": "pocket4-repair-r2-native-readonly-receipt-v1", "operation": operation,
           "command": command, "stdout_utf8": raw.decode("utf-8", "replace"),
           "stderr_utf8": stderr.decode("utf-8", "replace"), "utf8_display_only": True,
           "stdout_base64": base64.b64encode(raw).decode("ascii"),
           "stderr_base64": base64.b64encode(stderr).decode("ascii")}
    receipt_pin = write_doc(core, root, name, row)
    return actual_native(raw, command, expect), receipt_pin


def same_runtime_bytes(core, reference, actual):
    need(actual["cell_config"] == reference["cell_config"] and
         actual["limits"] == reference["limits"] and
         actual["daemon_service"] == reference["daemon_service"] and
         actual["presenter_service"] == reference["presenter_service"],
         "CONFIG_SERVICES_AND_LIMITS_MUST_MATCH_ORIGINAL")
    need(core.classpath_bytes(actual["classpath"]) == core.classpath_bytes(reference["classpath"]) and
         actual["engine"]["sha256"] == reference["engine"]["sha256"] and
         actual["engine"]["bytes"] == reference["engine"]["bytes"],
         "FRAMEWORK_OR_TRANSLATION_ENGINE_BYTES_CHANGED")
    for role in core.ROLE_NAMES:
        need(actual["binaries"][role]["sha256"] == reference["binaries"][role]["sha256"] and
             actual["binaries"][role]["bytes"] == reference["binaries"][role]["bytes"],
             "PINNED_RUNTIME_BINARY_CHANGED_" + role)


def require_owner_interpreter_prefix(argv):
    need(type(argv) is list and argv[:3] == ["/usr/bin/python3", "-I", WRAPPER],
         "CURRENT_NATIVE_OWNER_WRAPPER_INTERPRETER_PREFIX_REQUIRED")


def current_parent(core, rows, deployed):
    expected = core.E.process_identity(CURRENT_PARENT)
    need(expected["parent_host_pid"] == rows["launcher"]["host_pid"] and
         expected["host_pid"] == rows["android_init"]["parent_host_pid"] and
         expected["executable"] == "/usr/bin/unshare" and expected["uids"] == [0] * 4 and
         expected["cgroup"] == rows["launcher"]["cgroup"] and
         expected["namespaces"]["pid"] == rows["launcher"]["namespaces"]["pid"] and
         expected["namespaces"]["mnt"] == rows["android_init"]["namespaces"]["mnt"] and
         rows["launcher"]["start_ticks"] <= expected["start_ticks"] <= rows["android_init"]["start_ticks"] and
         expected["cmdline"].count("--kill-child=TERM") == 1 and
         expected["cmdline"][0] == "/usr/bin/unshare",
         "CURRENT_OLD_WRAPPER_NATIVE_PARENT_LINEAGE_REQUIRED")
    require_owner_interpreter_prefix(rows["launcher"]["cmdline"])
    file_record(core, deployed["native_unshare"])
    return expected


def survivors(core, rows, original_runtime, deployed, native_cli):
    for role in ("daemon", "presenter"):
        need(core.E.process_identity(rows[role]["host_pid"]) == rows[role],
             "UNCHANGED_NATIVE_SERVICE_PROCESS_REQUIRED_" + role)
    need(core.service() == original_runtime["daemon_service"] and
         core.service(True) == original_runtime["presenter_service"] and
         core.limits() == original_runtime["limits"], "UNCHANGED_NATIVE_SERVICES_AND_LIMITS_REQUIRED")
    raw, info = core.host_read(core.CONFIG, 131072, original_runtime["cell_config"]["sha256"])
    need(info == original_runtime["cell_config"]["file"] and
         len(raw) == original_runtime["cell_config"]["bytes"], "CELL_CONFIG_CHANGED_DURING_REPAIR")
    file_record(core, native_cli)
    file_record(core, deployed["new_wrapper"])
    file_record(core, deployed["native_unshare"])


def fixed_cli(core, original_plan):
    expected = {"path": "/usr/bin/droidloomctl", "bytes": 1705648,
                "sha256": "f81e0223f6b256584d07a5e8fbc72f3f4c764ab53a88469b45b587c101e12c79"}
    need(original_plan["native_cli"]["path"] == expected["path"] and
         original_plan["native_cli"]["sha256"] == expected["sha256"], "ORIGINAL_NATIVE_CLI_PIN_DIFFERS")
    raw, info = core.host_read(expected["path"], 32 * 1024 * 1024,
                               expected["sha256"], expected["bytes"])
    need(len(raw) == expected["bytes"] and info["st_uid"] == 1000 and info["st_gid"] == 1000 and
         info["st_dev"] == 66306 and info["st_ino"] == 108004277 and info["st_nlink"] == 1 and
         stat.S_ISREG(info["st_mode"]) and stat.S_IMODE(info["st_mode"]) == 0o755,
         "ACTUAL_PREVIOUSLY_VERIFIED_NATIVE_CLI_IDENTITY_DIFFERS")
    return {**expected, "stat": info}


def native_action(core, root, operation, predecessor_pin, previous_receipt, result):
    need(operation in ("stop", "start"), "ONLY_INDEPENDENT_STOP_AND_START_ALLOWED")
    intent = {"schema": "pocket4-independent-native-" + operation + "-intent-v2",
              "transition_origin": "repaired_lifecycle_r2", "predecessor": predecessor_pin,
              "previous_receipt": previous_receipt, "argv": native_argv(core, operation),
              "created_monotonic_ns": time.monotonic_ns(), "automatic_retry": False,
              "original_r1_outcome_remains_unknown": True, "original_r1_replayed": False}
    attempt_pin = write_doc(core, root, "native-" + operation + "-intent.private.json", intent)
    result[operation + "_attempted"] = True
    result["outcome_unknown"] = True
    raw, stderr, command = core.bounded_child(native_argv(core, operation), 60)
    receipt = {"schema": "pocket4-independent-native-" + operation + "-receipt-v2",
               "attempt": attempt_pin, "command": command,
               "stdout_utf8": raw.decode("utf-8", "replace"),
               "stderr_utf8": stderr.decode("utf-8", "replace"), "utf8_display_only": True,
               "stdout_base64": base64.b64encode(raw).decode("ascii"),
               "stderr_base64": base64.b64encode(stderr).decode("ascii")}
    receipt_pin = write_doc(core, root, "native-" + operation + "-receipt.private.json", receipt)
    result[operation + "_receipt"] = receipt_pin
    value = actual_native(raw, command, operation)
    result[operation + "_receipt_confirmed"] = True
    return value, receipt_pin


def namespace_candidates(core, allowed_executable):
    end = time.monotonic() + 8
    entries = os.listdir("/proc")
    need(len(entries) <= 65536, "SUCCESSOR_PROC_COUNT_BOUND")
    rows = []
    for name in entries:
        need(time.monotonic() < end, "SUCCESSOR_PROC_SCAN_BOUND")
        if not name.isdecimal():
            continue
        try:
            if os.readlink("/proc/" + name + "/exe") != allowed_executable:
                continue
            with open("/proc/" + name + "/cgroup", "r", encoding="ascii") as stream:
                groups = stream.read(8193)
            need(len(groups) <= 8192, "CGROUP_RECORD_BOUND")
            if not any(line == "0::" + core.CGROUP or line.startswith("0::" + core.CGROUP + "/")
                       for line in groups.splitlines()):
                continue
            rows.append(core.E.process_identity(int(name)))
        except (FileNotFoundError, ProcessLookupError):
            continue
        except core.E.EpochError:
            # A vanishing noncandidate is harmless; a selected identity is
            # captured again below and never silently replaced.
            continue
    return rows


def discover_exact_successor(core, native, before_rows, old_parent, namespaces):
    owner = core.E.process_identity(native["host_pid"])
    need(owner["host_pid"] != before_rows["launcher"]["host_pid"] and
         owner["parent_host_pid"] == before_rows["daemon"]["host_pid"] and
         owner["executable"] == before_rows["launcher"]["executable"] and
         owner["cmdline"] == before_rows["launcher"]["cmdline"] and
         owner["uids"] == before_rows["launcher"]["uids"] and
         owner["cgroup"] == before_rows["launcher"]["cgroup"],
         "NEW_RECEIPT_OWNER_MUST_BE_SAME_NATIVE_WRAPPER_ENTRY")
    end, fixed_init, last_read_error = time.monotonic() + 40, None, None
    while time.monotonic() < end:
        need(core.E.process_identity(owner["host_pid"]) == owner, "NEW_NATIVE_OWNER_CHANGED_DURING_DISCOVERY")
        if fixed_init is None:
            candidates = []
            for row in namespace_candidates(core, "/system/bin/init"):
                if row["namespaces"]["pid"] in namespaces:
                    continue
                if row["namespace_pids"][-1] != 1 or row["cmdline"][0] != "/init":
                    continue
                parent = core.E.process_identity(row["parent_host_pid"])
                if parent["parent_host_pid"] == owner["host_pid"]:
                    candidates.append(row)
            fixed_init = select_namespace_init(candidates, owner["host_pid"])
            if fixed_init is None:
                time.sleep(.2)
                continue
        need(core.E.process_identity(fixed_init["host_pid"]) == fixed_init,
             "FIRST_DISCOVERED_SUCCESSOR_PID1_CHANGED")
        try:
            android = core.E.capture_android(fixed_init["host_pid"])
        except core.E.EpochError as error:
            # Only readiness absence is waitable. A changed/replaced init fails
            # at the exact fixed identity check on the next iteration.
            last_read_error = getattr(error, "code", type(error).__name__)
            if last_read_error != "FRAMEWORK_PROCESS_SET_AMBIGUOUS_OR_MISSING":
                raise
            time.sleep(.2)
            continue
        composer_rows = [row for row in namespace_candidates(core, core.COMPOSER_EXE)
                         if row["namespaces"]["pid"] == fixed_init["namespaces"]["pid"]]
        need(len(composer_rows) <= 1, "NEW_COMPOSER_AMBIGUOUS")
        if not composer_rows:
            time.sleep(.2)
            continue
        composer = composer_rows[0]
        need(composer["parent_host_pid"] == fixed_init["host_pid"] and
             composer["uids"] == [1000] * 4, "NEW_COMPOSER_LINEAGE_REQUIRED")
        parent = core.E.process_identity(fixed_init["parent_host_pid"])
        expected_argv = ["--kill-child=KILL" if arg == "--kill-child=TERM" else arg
                         for arg in old_parent["cmdline"]]
        need(parent["parent_host_pid"] == owner["host_pid"] and parent["executable"] == "/usr/bin/unshare" and
             parent["uids"] == [0] * 4 and parent["cmdline"] == expected_argv and
             parent["cmdline"].count("--kill-child=KILL") == 1 and
             parent["namespaces"]["pid"] == owner["namespaces"]["pid"] and
             parent["namespaces"]["mnt"] == fixed_init["namespaces"]["mnt"],
             "ACTUAL_NEW_WRAPPER_NATIVE_CHILD_KILL_POLICY_REQUIRED")
        rows = {"daemon": before_rows["daemon"], "presenter": before_rows["presenter"],
                "launcher": owner, "android_init": fixed_init, "composer": composer}
        rows.update({name: android["binding"]["processes"][name]
                     for name in ("zygote64", "system_server", "surfaceflinger")})
        need(set(rows) == set(core.ROLE_NAMES), "ALL_EIGHT_SUCCESSOR_ROLES_REQUIRED")
        for role in core.RETIRED:
            need((rows[role]["host_pid"], rows[role]["start_ticks"]) !=
                 (before_rows[role]["host_pid"], before_rows[role]["start_ticks"]),
                 "OLD_RETIRED_ROLE_CANNOT_BE_SUCCESSOR")
        need(core.E.process_identity(owner["host_pid"]) == owner and
             core.E.process_identity(parent["host_pid"]) == parent, "NEW_NATIVE_LINEAGE_CHANGED")
        return rows, parent, android
    raise Reject("FIXED_SUCCESSOR_FRAMEWORK_NOT_READY_" + str(last_read_error))


def original_pidfd_deaths(core, held, parent):
    rows = held.before["binding"]["processes"]
    need(all(core.pidfd_dead(held.pidfds[role]) for role in core.RETIRED) and
         core.pidfd_dead(parent.fd), "ALL_ORIGINAL_R2_PRE_STOP_PIDFDS_MUST_BE_DEAD")
    return {role: {"host_pid": rows[role]["host_pid"], "start_ticks": rows[role]["start_ticks"],
                   "original_pre_stop_r2_pidfd_readable": True} for role in core.RETIRED}


def retire_current(core, root, held, parent, original_runtime, deployed, native_cli,
                   stop_receipt, namespaces, result):
    rows = held.before["binding"]["processes"]
    need(held.views_released is True, "ALL_OLD_RUNTIME_VIEWS_MUST_BE_RELEASED")
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if all(core.pidfd_dead(held.pidfds[name]) for name in core.RETIRED) and core.pidfd_dead(parent.fd):
            break
        time.sleep(.1)
    owner_dead = core.pidfd_dead(held.pidfds["launcher"])
    init_dead = core.pidfd_dead(held.pidfds["android_init"])
    parent_dead = core.pidfd_dead(parent.fd)
    signal_pin = None
    if not all(core.pidfd_dead(held.pidfds[name]) for name in core.RETIRED) or not parent_dead:
        current_init = None if init_dead else core.E.process_identity(rows["android_init"]["host_pid"])
        current_parent = None if parent_dead else core.E.process_identity(parent.expected["host_pid"])
        decision = signal_decision(
            native_stopped=result["stop_receipt_confirmed"], owner_dead=owner_dead,
            init_dead=init_dead, parent_dead=parent_dead, expected_init=rows["android_init"],
            current_init=current_init, expected_parent=parent.expected, current_parent=current_parent)
        need(decision == "SIGNAL_EXACT_INIT_PIDFD_ONCE", "UNRESOLVED_NON_INIT_RETIRED_ROLE_REQUIRES_REVIEW")
        survivors(core, rows, original_runtime, deployed, native_cli)
        stopped, _ = native_query(core, root, "native-status-before-exact-retirement.private.json",
                                   "status", "status_stopped")
        need(stopped["state"] == "stopped", "NATIVE_OWNER_MUST_REMAIN_STOPPED")
        signal_intent = {"schema": "pocket4-r2-exact-init-retirement-intent-v1",
                         "stop_receipt": stop_receipt, "target": rows["android_init"],
                         "native_parent": parent.expected, "signal": "SIGKILL", "target_kind": "held_pidfd",
                         "created_monotonic_ns": time.monotonic_ns(), "max_signal_syscalls": 1,
                         "killpg": False, "automatic_retry": False}
        intent_pin = write_doc(core, root, "exact-init-signal-intent.private.json", signal_intent)
        # Identity and original fd are rechecked after durable intent, immediately
        # before the only permitted target signal.
        need(not core.pidfd_dead(held.pidfds["android_init"]) and
             core.E.process_identity(rows["android_init"]["host_pid"]) == rows["android_init"] and
             equal_process_after_reparent(parent.expected,
                 core.E.process_identity(parent.expected["host_pid"]), 1),
             "EXACT_SIGNAL_TARGET_CHANGED_AFTER_DURABLE_INTENT")
        result["signal_attempted"] = True
        result["signal_syscalls"] = 1
        signal_error = None
        try:
            signal.pidfd_send_signal(held.pidfds["android_init"], signal.SIGKILL, None, 0)
        except ProcessLookupError:
            need(core.pidfd_dead(held.pidfds["android_init"]), "PIDFD_SIGNAL_ESRCH_WITHOUT_DEATH")
            signal_error = "TARGET_EXITED_BEFORE_SIGNAL_DELIVERY"
        signal_pin = write_doc(core, root, "exact-init-signal-receipt.private.json", {
            "schema": "pocket4-r2-exact-init-retirement-receipt-v1", "intent": intent_pin,
            "signal_syscalls": 1, "signal": "SIGKILL", "held_target": rows["android_init"],
            "syscall_returned": signal_error is None, "exit_before_delivery": signal_error is not None,
            "automatic_retry": False, "finished_monotonic_ns": time.monotonic_ns(),
        })
    deadline = time.monotonic() + 30
    while not (all(core.pidfd_dead(held.pidfds[name]) for name in core.RETIRED) and core.pidfd_dead(parent.fd)):
        need(time.monotonic() < deadline, "R2_ORIGINAL_PRE_STOP_PROCESS_DEATH_NOT_PROVED")
        time.sleep(.1)
    deaths = original_pidfd_deaths(core, held, parent)
    empty = ns_empty_samples(core, namespaces)
    survivors(core, rows, original_runtime, deployed, native_cli)
    _, status_pin = native_query(core, root, "native-status-retired.private.json", "status", "status_stopped")
    proof = {"schema": "pocket4-r2-original-pre-stop-retirement-proof-v1",
             "transition_origin": "repaired_lifecycle_r2", "stop_receipt": stop_receipt,
             "signal_receipt": signal_pin, "old_pidfd_deaths": deaths,
             "intermediate_parent": {"identity": parent.expected, "original_pre_stop_r2_pidfd_readable": True},
             "both_namespace_empty_samples": empty, "actual_native_stopped_status": status_pin,
             "original_r1_outcome_remains_unknown": True,
             "original_r1_pre_restart_pidfd_evidence_recreated": False,
             "created_monotonic_ns": time.monotonic_ns()}
    proof_pin = write_doc(core, root, "retired-lifecycle.private.json", proof)
    result["retirement_proved"] = True
    result["outcome_unknown"] = False
    result["retirement_proof"] = proof_pin
    return proof, proof_pin


def run(core, encoded, packet, execute=False):
    need(os.getuid() == os.geteuid() == 0 and sys.platform == "linux" and
         os.uname().machine == "x86_64" and hasattr(signal, "pidfd_send_signal"),
         "ROOT_X86_64_LINUX_WITH_PIDFD_REQUIRED")
    validate_packet(core, packet)
    root = packet["output_root"]
    pool, leases = core.FDs(), core.FDs()
    result = {"schema": "pocket4-independent-native-lifecycle-repair-result-v2", "ok": False,
              "transition_origin": "repaired_lifecycle_r2", "mode": "execute" if execute else "preflight",
              "preflight_passed": False, "stop_attempted": False, "stop_receipt_confirmed": False,
              "signal_attempted": False, "signal_syscalls": 0, "retirement_proved": False,
              "start_attempted": False, "start_receipt_confirmed": False,
              "outcome_unknown": False, "automatic_retry": False, "identity_qualified": False,
              "original_r1_outcome_remains_unknown": True, "original_r1_replayed": False,
              "original_r1_pre_restart_pidfd_evidence_recreated": False,
              "UI_or_install_runtime_admitted": False, "production_ready": False,
              "Android_commands": 0, "namespace_entries": 0, "UI_actions": 0,
              "installs": 0, "permission_changes": 0, "errors": []}
    created = False
    phase = "immutable_evidence_and_private_claim"
    baseline_pin = qualification_pin = guard_pin = app_pin = None
    try:
        chain = original_chain(core, packet["current_observation"])
        deployed, test = wrapper_evidence(core, packet["wrapper_deployment"])
        previous, before_rows = chain["previous"], chain["roles"]
        reference_runtime = previous["runtime"]
        make_root(core, root)
        created = True
        for name, raw in encoded.items():
            core.write_new(root + "/source/" + name, raw)
        core.write_new(root + "/independent_repair_r2.py", pin(core, packet["source"], 262144))
        packet_pin = write_doc(core, root, "packet.private.json", packet)
        phase = "fresh_coordinated_drain_and_original_leases"
        _, action_identity = core.acquire_lock(leases, core.ACTION_LOCK, previous["action_lock_identity"])
        _, own_identity = core.acquire_lock(leases, root + "/flow.lock")
        new_flow = {"path": root + "/flow.lock", "identity": own_identity}
        drain, drain_pin, terminal_pins = prepare_drain(core, leases, root, packet, chain)
        phase = "bind_exact_current_native_owner_and_eight_roles"
        old = core.HeldProcesses(pool, {role: row["host_pid"] for role, row in before_rows.items()})
        need(old.before["binding"]["processes"] == before_rows, "ACTUAL_CURRENT_EIGHT_ROLES_DIFFER")
        android = core.E.capture_android(before_rows["android_init"]["host_pid"])
        need(android["binding"] == core.android_epoch(old.before)["binding"], "CURRENT_FRAMEWORK_LINEAGE_DIFFERS")
        parent_row = current_parent(core, before_rows, deployed)
        parent = HeldParent(core, pool, parent_row, deployed["native_unshare"])
        native_cli = fixed_cli(core, previous["plan"])
        for operation, required in (("help", (b"start", b"stop", b"status")),
                                    ("start_help", (b"--spec",)), ("stop_help", (b"stop",))):
            raw, stderr, command = core.bounded_child(native_argv(core, operation), 10)
            write_doc(core, root, "native-" + operation + ".private.json", {
                "command": command, "stdout_utf8": raw.decode("utf-8", "replace"),
                "stderr_utf8": stderr.decode("utf-8", "replace"), "utf8_display_only": True,
                "stdout_base64": base64.b64encode(raw).decode("ascii"),
                "stderr_base64": base64.b64encode(stderr).decode("ascii")})
            need(command["complete"] and all(word in raw.lower() for word in required),
                 "LIVE_NATIVE_CLOSED_OPERATION_PARSER_REQUIRED")
        status, status_pin = native_query(core, root, "native-status-before.private.json",
                                          "status", "status_running")
        need(status["host_pid"] == before_rows["launcher"]["host_pid"], "ACTUAL_CURRENT_NATIVE_OWNER_DIFFERS")
        daemon, presenter = core.service(), core.service(True)
        need(daemon == reference_runtime["daemon_service"] and presenter == reference_runtime["presenter_service"],
             "ORIGINAL_NATIVE_SERVICE_IDENTITIES_CHANGED")
        phase = "all_46_app_bytes_and_current_runtime"
        current_runtime = core.collect_runtime(pool, old, daemon, presenter,
                            reference_runtime["cell_config"]["sha256"], reference_runtime["engine"]["sha256"])
        same_runtime_bytes(core, reference_runtime, current_runtime)
        targets = sorted(previous["apps"])
        apps = core.app_scope(pool, old, targets)
        need(core.app_bytes(apps) == core.app_bytes(previous["apps"]), "PRE_STOP_ALL_46_APPS_DIFFER_FROM_REAL_R1_SCOPE")
        core.verify_runtime(pool, old, current_runtime)
        parent.verify()
        file_record(core, native_cli)
        file_record(core, deployed["new_wrapper"])
        file_record(core, deployed["native_unshare"])
        unchanged_history(core, chain, packet["current_observation"])
        old_namespace = previous["runtime"]["held"]["process_snapshot"]["binding"]["processes"]["android_init"]["namespaces"]["pid"]
        current_namespace = before_rows["android_init"]["namespaces"]["pid"]
        need(old_namespace != current_namespace and not namespace_members(core, old_namespace),
             "INDEPENDENTLY_RETIRED_ORIGINAL_NAMESPACE_REAPPEARED")
        verify_leases(core, pool, action_identity, drain, new_flow)
        pre = {"schema": "pocket4-repaired-native-preflight-v2", "transition_origin": "repaired_lifecycle_r2",
               "packet": packet_pin, "source_manifest_sha256": MANIFEST, "source": packet["source"],
               "original_restart_predecessor": chain["pins"]["predecessor.private.json"],
               "original_restart_failed_unknown": chain["pins"]["result.json"],
               "original_restart_native_receipt": chain["pins"]["native-restart-receipt.private.json"],
               "independent_orphan_retirement": ORPHAN_PIN, "current_two_sample_observation": packet["current_observation"],
               "wrapper_deployment": packet["wrapper_deployment"], "wrapper_host_test": deployed["host_test_receipt"],
               "runtime": current_runtime, "apps": apps, "target_count": len(targets),
               "intermediate_parent": parent_row, "native_cli": native_cli,
               "actual_native_status": status, "native_status_receipt": status_pin,
               "action_lock_identity": action_identity, "own_flow_lock": new_flow, "reviewed_drain": drain,
               "reviewed_drain_pin": drain_pin, "created_monotonic_ns": time.monotonic_ns()}
        pre_pin = write_doc(core, root, "predecessor.private.json", pre)
        result.update(preflight_passed=True, predecessor=pre_pin, target_count=len(targets),
                      wrapper_deployment=packet["wrapper_deployment"], drain=drain_pin,
                      all_historical_evidence_preserved=True)
        if not execute:
            result["ok"] = True
        else:
            phase = "release_all_old_views_before_native_stop"
            core.verify_runtime(pool, old, current_runtime)
            core.app_scope(pool, old, targets, apps, False)
            parent.verify()
            unchanged_history(core, chain, packet["current_observation"])
            file_record(core, native_cli)
            file_record(core, deployed["new_wrapper"])
            file_record(core, deployed["native_unshare"])
            verify_leases(core, pool, action_identity, drain, new_flow)
            claim_pin = core.write_new(EXECUTION_CLAIM, canonical({
                "schema": "pocket4-single-independent-repair-r2-execution-claim-v1",
                "predecessor": pre_pin, "packet": packet_pin, "source": packet["source"],
                "output_root": root, "created_monotonic_ns": time.monotonic_ns(),
                "automatic_retry": False,
            }) + b"\n")
            result["execution_claim"] = claim_pin
            old.release_views_keep_pidfds()
            need(set(pool.active) == set(old.pidfds.values()) | {parent.fd},
                 "ONLY_ORIGINAL_PIDFDS_MAY_SURVIVE_NATIVE_STOP")
            phase = "unique_native_stop"
            _, stop_pin = native_action(core, root, "stop", pre_pin, None, result)
            phase = "original_pre_stop_pidfd_retirement"
            retirement, retirement_pin = retire_current(core, root, old, parent, current_runtime,
                deployed, native_cli, stop_pin, [old_namespace, current_namespace], result)
            unchanged_history(core, chain, packet["current_observation"])
            original_pidfd_deaths(core, old, parent)
            survivors(core, before_rows, current_runtime, deployed, native_cli)
            phase = "unique_native_start_after_actual_retirement"
            start, start_pin = native_action(core, root, "start", pre_pin, retirement_pin, result)
            phase = "exact_new_owner_namespace_pid1_and_framework"
            next_rows, next_parent_row, next_android = discover_exact_successor(
                core, start, before_rows, parent_row, [old_namespace, current_namespace])
            new = core.HeldProcesses(pool, {role: row["host_pid"] for role, row in next_rows.items()})
            need(new.before["binding"]["processes"] == next_rows, "NEW_EIGHT_ROLE_SET_CHANGED_DURING_BIND")
            next_parent = HeldParent(core, pool, next_parent_row, deployed["native_unshare"])
            activation = {"schema": "pocket4-actual-repaired-wrapper-activation-v1",
                "deployment": packet["wrapper_deployment"], "native_start_receipt": start_pin,
                "owner": next_rows["launcher"], "native_parent": next_parent_row,
                "android_init": next_rows["android_init"], "source_path": WRAPPER,
                "source_sha256": WRAPPER_SHA, "actual_kill_child_argument": "--kill-child=KILL",
                "same_source_real_host_controls": deployed["host_test_receipt"],
                "PDEATHSIG_read_from_production_proc": False,
                "PDEATHSIG_supported_by_same_source_real_tests": True}
            activation_pin = write_doc(core, root, "wrapper-activation.private.json", activation)
            phase = "successor_runtime_and_all_apps_invariance"
            next_runtime = core.collect_runtime(pool, new, core.service(), core.service(True),
                              reference_runtime["cell_config"]["sha256"], reference_runtime["engine"]["sha256"])
            same_runtime_bytes(core, reference_runtime, next_runtime)
            next_apps = core.app_scope(pool, new, targets)
            need(core.app_bytes(next_apps) == core.app_bytes(apps), "POST_START_ALL_46_APKS_OR_DATA_IDENTITIES_CHANGED")
            core.verify_runtime(pool, new, next_runtime)
            next_parent.verify()
            original_pidfd_deaths(core, old, parent)
            ns_empty_samples(core, [old_namespace, current_namespace])
            post_status, post_status_pin = native_query(core, root, "native-status-successor.private.json",
                                                       "status", "status_running")
            need(post_status["host_pid"] == next_rows["launcher"]["host_pid"], "ACTUAL_SUCCESSOR_OWNER_CHANGED")
            phase = "three_double_samples_over_ten_seconds"
            samples = []
            for index in range(3):
                if index:
                    time.sleep(5.1)
                core.verify_runtime(pool, new, next_runtime)
                next_parent.verify()
                samples.append(new.verify())
            bindings = [row["binding"] for row in samples]
            times = [row["collected_monotonic_ns"] for row in samples]
            need(all(row == bindings[0] for row in bindings) and times == sorted(set(times)) and
                 10_000_000_000 <= times[-1] - times[0] <= 90_000_000_000,
                 "THREE_STABLE_DOUBLE_SAMPLES_OVER_REQUIRED_SPAN")
            core.app_scope(pool, new, targets, next_apps, False)
            core.verify_runtime(pool, new, next_runtime)
            next_parent.verify()
            file_record(core, native_cli)
            file_record(core, deployed["new_wrapper"])
            file_record(core, deployed["native_unshare"])
            unchanged_history(core, chain, packet["current_observation"])
            old_deaths = original_pidfd_deaths(core, old, parent)
            next_runtime["held"]["process_snapshot"] = samples[-1]
            framework = core.android_epoch(samples[-1])
            transition = {"schema": "pocket4-actual-repaired-native-lifecycle-transition-v2",
                "transition_origin": "repaired_lifecycle_r2", "predecessor": pre_pin,
                "retirement_proof": retirement_pin, "native_stop_receipt": stop_pin,
                "native_start_receipt": start_pin, "actual_successor_launcher": next_rows["launcher"],
                "actual_successor_native_parent": next_parent_row, "boot_id": core.boot_id(),
                "old_pidfd_deaths": old_deaths, "old_pidfd_death_evidence_origin": "original_r2_pre_stop_pidfds",
                "original_r1_outcome_remains_unknown": True, "original_r1_replayed": False,
                "original_r1_pre_restart_pidfd_evidence_recreated": False,
                "original_r1_failed_result": chain["pins"]["result.json"], "wrapper_activation": activation_pin,
                "old_launch_replayed": False, "actual_successor_native_status": post_status_pin}
            transition_pin = write_doc(core, root, "actual-transition.private.json", transition)
            result["transition"] = transition_pin
            phase = "close_observation_descriptors_before_qualification"
            pool.close_all()
            need(all_closed(pool.summary()), "ALL_R2_OBSERVATION_DESCRIPTORS_MUST_CLOSE")
            runtime_sha = sha(canonical(next_runtime))
            baseline = {"schema": "pocket4-successor-runtime-baseline-v1",
                "kind": "independent_native_stop_retire_start_repair_r2", "runtime": next_runtime,
                "runtime_epoch_sha256": runtime_sha, "framework_epoch": framework,
                "predecessor": pre_pin, "transition": transition_pin, "sample_monotonic_ns": times,
                "bounded_future_proof_only": True, "framework_exit_cause_resolved": False,
                "native_framework_incarnation_fix_deployed": False,
                "wrapper_child_death_fix_activated": True, "future_runtime_stop_regression_proved": False,
                "original_r1_outcome_remains_unknown": True,
                "UI_or_install_runtime_admitted": False, "production_ready": False}
            baseline_pin = write_doc(core, root, "baseline.private.json", baseline)
            appdoc = {"schema": "pocket4-versioned-app-scope-v1", "runtime_epoch_sha256": runtime_sha,
                "kind": "initial_all_46_after_independent_repair_r2", "apps": next_apps,
                "previous_app_content_sha256": sha(canonical(core.app_bytes(apps))),
                "target_roster": previous["plan"]["targets"], "fresh_signature_verification": False,
                "post_restart_resolver_verification": False, "effective_permission_grants_verified": False,
                "UI_or_install_runtime_admitted": False, "production_ready": False}
            app_pin = write_doc(core, root, "initial-app-scope.private.json", appdoc)
            qualification = {"schema": "pocket4-successor-qualification-v1", "identity_qualified": True,
                "baseline": baseline_pin, "source_manifest_sha256": MANIFEST,
                "runtime_epoch_sha256": runtime_sha, "old_native_pidfd_deaths_proved": True,
                "old_native_pidfd_evidence_origin": "original_r2_pre_stop_pidfds",
                "old_native_pidfd_retirement_proof": retirement_pin, "transition": transition_pin,
                "initial_app_scope_unchanged": True, "initial_app_scope": app_pin,
                "observation_fds": pool.summary(), "sample_monotonic_ns": times,
                "original_r1_outcome_remains_unknown": True,
                "original_r1_pre_restart_pidfd_evidence_recreated": False,
                "UI_or_install_runtime_admitted": False, "production_ready": False}
            qualification_pin = write_doc(core, root, "qualification.private.json", qualification)
            guard_raw = core.guard_source(root, MANIFEST, baseline_pin, qualification_pin)
            guard_pin = core.write_new(root + "/current_baseline_guard.py", guard_raw)
            phase = "actual_published_guard_and_app_scope_readback"
            generated = types.ModuleType("actual_repair_r2_guard")
            generated.__file__ = guard_pin["path"]
            exec(compile(guard_raw, generated.__file__, "exec"), generated.__dict__)
            check = generated.current_guard()
            need(check["runtime_epoch_sha256"] == runtime_sha and
                 check["UI_or_install_runtime_admitted"] is False, "PUBLISHED_TYPED_GUARD_READBACK")
            app_check = generated.check_app_scope(app_pin, targets)
            need(app_check["runtime_epoch_sha256"] == runtime_sha and
                 app_check["UI_or_install_runtime_admitted"] is False, "PUBLISHED_ALL_APP_SCOPE_READBACK")
            unchanged_history(core, chain, packet["current_observation"])
            result.update(ok=True, outcome_unknown=False, identity_qualified=True,
                current_guard=guard_pin, baseline=baseline_pin, qualification=qualification_pin,
                initial_app_scope=app_pin, runtime_epoch_sha256=runtime_sha, framework_epoch_sha256=framework["sha256"],
                wrapper_activation=activation_pin, original_r2_pre_stop_pidfd_deaths_proved=True,
                all_46_app_bytes_and_data_identities_unchanged=True, sample_monotonic_ns=times)
    except BaseException as error:
        result["errors"].append({"phase": phase, "type": type(error).__name__,
                                 "code": str(getattr(error, "code", error))[:240]})
        result["ok"] = False
        result["identity_qualified"] = False
        if result["start_attempted"] or (result["stop_attempted"] and not result["retirement_proved"]):
            result["outcome_unknown"] = True
    finally:
        for name, owned in (("observation_fds", pool), ("lease_fds", leases)):
            try:
                owned.close_all()
            except BaseException as error:
                result["errors"].append({"phase": "close_" + name, "type": type(error).__name__,
                                         "code": str(getattr(error, "code", error))[:240]})
                result["ok"] = result["identity_qualified"] = False
                if result["stop_attempted"]:
                    result["outcome_unknown"] = True
            result[name] = owned.summary()
        result["finished_monotonic_ns"] = time.monotonic_ns()
        if created:
            try:
                result["result_artifact_path"] = root + "/result.json"
                core.write_new(root + "/result.json", canonical(result) + b"\n")
            except BaseException as error:
                result["ok"] = result["identity_qualified"] = False
                result["errors"].append({"phase": "durable_result", "type": type(error).__name__,
                                         "code": str(getattr(error, "code", error))[:240]})
                if result["stop_attempted"]:
                    result["outcome_unknown"] = True
    return result


def argument_parser():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", required=True)
    parser.add_argument("--packet-sha256", required=True)
    parser.add_argument("--execute", action="store_true", default=False,
                        help="perform exactly one independent stop/retire/start after preflight")
    return parser


def main(argv=None):
    args = argument_parser().parse_args(argv)
    need(os.getuid() == os.geteuid() == 0, "ROOT_REQUIRED")
    os.umask(0o077)
    raw = boot_source(args.packet, args.packet_sha256, 2 * 1024 * 1024)
    packet = parse(raw)
    core, encoded = load_core()
    result = run(core, encoded, packet, execute=args.execute)
    sys.stdout.buffer.write(canonical(result) + b"\n")
    sys.stdout.buffer.flush()
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
