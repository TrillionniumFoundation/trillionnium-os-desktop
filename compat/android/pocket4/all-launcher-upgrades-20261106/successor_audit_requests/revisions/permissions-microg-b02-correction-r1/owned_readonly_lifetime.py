#!/usr/bin/env python3
"""Sealed host observation, with the existing proven libffi/owned-pidfd lifetime."""
import base64
import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import types
import zlib

sys.dont_write_bytecode = True
CONFIG = {'schema': 'pocket4-owned-readonly-observation-config-v1', 'kind': 'services', 'stage_root': '/home/alex/work/pocket4-microg-permission-correction-source-20261106-r1', 'worker': {'path': '/home/alex/work/pocket4-microg-permission-correction-source-20261106-r1/observe_current_services.py', 'bytes': 56665, 'sha256': 'a968ecab4f8b1837bd7f153c6c76517625b5f2ec89d5a157b19e494a5ab5f641'}, 'request': {'path': '/home/alex/work/pocket4-microg-permission-correction-source-20261106-r1/request.review-only.json', 'bytes': 4368, 'sha256': '94ca89b4b538b07b9b7598e0748138e793f1afa0ac887e6d17f53818d016a02e'}, 'prior_source': {'bytes': 19964, 'sha256': '00eb25ad44a9b8e030b670a67ca75043a0ac9870acbb9fadf6e0a51dde75c70d', 'preserved': True, 'actual_prior_failed_job': '1a1b2be17ec-fc05-7f8b', 'scope_authority_not_inherited': True}}
SELF_PIN = None
SUPPORT = {
    "path": "/home/alex/work/pocket4-beike-owned-generation-20261106-b34f158f88bbebf112840fd88df25d03/prepare_beike_owned_lifetime.py",
    "bytes": 20132, "sha256": "76b858b83c7304287fedb13f80c889e3fa7a8d6d32d4183409a5ad6fce269baf"}
STAT = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
MAX_OUTPUT = 131072


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def pin_bytes(pin, limit=262144):
    need(type(pin) is dict and set(pin) == {"path", "bytes", "sha256"} and type(pin["bytes"]) is int and
         0 <= pin["bytes"] <= limit and re.fullmatch("[0-9a-f]{64}", pin["sha256"]), "EXACT_FILE_PIN_REQUIRED")
    path = pin["path"]
    need(path.startswith("/") and all(x not in ("", ".", "..") for x in path[1:].split("/")), "CANONICAL_PIN_PATH")
    fds = []
    try:
        parent = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC); fds.append(parent)
        parts = path[1:].split("/")
        for part in parts[:-1]:
            parent = os.open(part, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent); fds.append(parent)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent); fds.append(fd)
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1 and
             not before.st_mode & 0o022 and before.st_size == pin["bytes"], "ROOT_PIN_FILE_METADATA")
        raw = bytearray()
        while len(raw) <= pin["bytes"]:
            block = os.read(fd, min(65536, pin["bytes"] + 1 - len(raw)))
            if not block:
                break
            raw.extend(block)
        current = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent); fds.append(current)
        need(len(raw) == pin["bytes"] and hashlib.sha256(raw).hexdigest() == pin["sha256"] and
             all(getattr(before, key) == getattr(os.fstat(fd), key) == getattr(os.fstat(current), key) for key in STAT),
             "PINNED_BYTES_OR_PATH_CHANGED")
        return bytes(raw)
    finally:
        errors = []
        for fd in reversed(fds):
            try:
                os.close(fd)
            except OSError:
                errors.append(fd)
        need(not errors, "PIN_READER_FDS_NOT_CLOSED")


def load(pin, name):
    module = types.ModuleType(name)
    module.__file__ = pin["path"]
    exec(compile(pin_bytes(pin), pin["path"], "exec"), module.__dict__)
    return module


def enter(mode):
    global SELF_PIN
    need(type(CONFIG) is dict and set(CONFIG) == {"schema", "kind", "stage_root", "worker", "request", "prior_source"} and
         CONFIG["schema"] == "pocket4-owned-readonly-observation-config-v1" and CONFIG["kind"] in ("explicit47", "calendar", "services"),
         "UNSEALED_NO_RUNTIME")
    need(str(Path(__file__).resolve()) == CONFIG["stage_root"] + "/owned_readonly_lifetime.py", "EXACT_REAL_NEW_SOURCE_FILE")
    need(len(sys.argv) == 6 and sys.argv[1] == mode and sys.argv[2] == "--source-sha256" and
         sys.argv[4] == "--source-bytes" and re.fullmatch("[0-9a-f]{64}", sys.argv[3]) and sys.argv[5].isdigit(),
         "EXACT_SOURCE_PINNED_ENTRY")
    SELF_PIN = {"path": str(Path(__file__).resolve()), "bytes": int(sys.argv[5]), "sha256": sys.argv[3]}
    need(os.getuid() == os.geteuid() == 0, "EXISTING_HOST_ROOT_REQUIRED")
    pin_bytes(SELF_PIN)


def decode_worker(raw):
    need(type(raw) is bytes and 0 < len(raw) <= 98304 and len(raw.splitlines()) == 1, "ONE_BOUNDED_ORIGINAL_WORKER_RESULT")
    value = json.loads(raw)
    if CONFIG["kind"] in ("calendar", "services"):
        need(set(value) == {"encoding", "artifact_bytes", "artifact_sha256", "data"} and value["encoding"] == "zlib-base64" and
             type(value["artifact_bytes"]) is int and 0 < value["artifact_bytes"] <= 524288, "CALENDAR_ARTIFACT_PROTOCOL")
        decoder = zlib.decompressobj()
        decoded = decoder.decompress(base64.b64decode(value["data"], validate=True), 524289)
        need(decoder.eof and not decoder.unconsumed_tail and not decoder.unused_data and len(decoded) == value["artifact_bytes"] and
             hashlib.sha256(decoded).hexdigest() == value["artifact_sha256"], "CALENDAR_ORIGINAL_ARTIFACT_PIN")
        value = json.loads(decoded)
    return value


def retired(row):
    return (type(row) is dict and type(row.get("acquired")) is int and row["acquired"] > 0 and
            row.get("closed") == row["acquired"] and row.get("remaining") == 0 and row.get("errors") == [])


def worker_gate(value, returned):
    need(returned == 0 and value.get("errors") == [] and value.get("automatic_retry") is False and
         value.get("production_ready") is False and value.get("process_FDs_before") == value.get("process_FDs_after"),
         "ORIGINAL_WORKER_DID_NOT_PASS")
    guard = value.get("guard_before", {})
    need(guard.get("schema") == "pocket4-successor-main-guard-v1" and
         guard.get("runtime_epoch_sha256") == "a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9" and
         value.get("guard_after") == guard and retired(value.get("owned_descriptors_final")), "ORIGINAL_RUNTIME_OR_FD_GATE_FAILED")
    if CONFIG["kind"] == "explicit47":
        need(value.get("schema") == "pocket4-explicit-47-app-scope-observation-v1" and value.get("ok") is True and
             value.get("status") == "EXPLICIT_47_PACKAGE_SCOPE_OBSERVED" and value.get("package_count") == 47 and
             value.get("original_46_unchanged") is True and value.get("new_helper_matches_actual_install") is True and
             value.get("locks_released") is True and retired(value.get("observation", {}).get("observation_fds")),
             "EXPLICIT47_OBSERVATION_GATE_FAILED")
        actions = ("Main_UI_actions", "native_commands", "Android_namespace_commands", "ADB_commands", "installs", "permission_changes",
                   "business_data_content_reads")
        need(value.get("framework_MAIN_LAUNCHER_resolver_queried") is False and value.get("all_Android_installed_packages_enumerated") is False,
             "EXPLICIT_SCOPE_MUST_NOT_CLAIM_GLOBAL_RESOLVER")
    elif CONFIG["kind"] == "calendar":
        need(value.get("schema") == "pocket4-independent-calendar-aapt2-resource-comparison-v2" and
             value.get("status") == "INDEPENDENT_TWO_APK_RESOURCE_COMPARISON_COMPLETE" and
             all(value.get(key) is True for key in ("snapshot_consistent", "all_primary_commands_succeeded",
                 "legacy_badging_observations_complete", "all_manifests_and_signatures_verified", "all_tool_children_joined", "action_lock_released")) and
             value.get("unjoined_tool_pids") == [] and len(value.get("commands", [])) == 8 and
             value.get("packages") == ["com.android.calendar", "org.fcitx.fcitx5.android"], "CALENDAR_COMPARISON_GATE_FAILED")
        need(value.get("original_failed_audit_reclassified") is False and value.get("original_batch_05_gate_advanced") is False,
             "ORIGINAL_FAILURE_MUST_REMAIN")
        actions = ("UI_actions", "App_launches", "permission_changes", "installs", "Android_namespace_commands", "ADB_commands", "business_data_content_reads")
    else:
        need(value.get("schema") == "pocket4-independent-microg-permission-correction-v1" and value.get("ok") is True and
             value.get("status") == "MICROG_PERMISSION_RAW_CAPTURE_CORRECTION_VERIFIED" and
             value.get("current_scope_47_unchanged") is True and len(value.get("packages", [])) == 47 and
             value.get("app_scope_reference", {}).get("sha256") == "44f9ce783000a672c270e98afdaeb74bd79654508bfacae6793316ff4252e52f" and
             value.get("batch") == 2 and value.get("target_packages") == ['com.google.android.gms'] and
             type(value.get("target_user")) is int and value["target_user"] == 0 and
             value.get("target_identities_from_pinned_scope") == [{'package': 'com.google.android.gms', 'uid': 10118, 'version_code': 252432034}] and
             value.get("service_target_packages") == ['com.google.android.gms'] and value.get("service_output_capture_complete") is True and
             value.get("PM_user0_installed_APK_packages_enumerated") is False and value.get("MAIN_LAUNCHER_resolver_queried") is False and
             value.get("Android_namespace_commands") == 3 and value.get("native_command_count") == 3 and
             len(value.get("android_commands", [])) == 3 and len(value.get("native_commands", [])) == 3 and
             all(row.get("complete") is True and row.get("joined") is True and row.get("returncode") == 0 and
                 row.get("termination_attempted") is False and row.get("errors") == [] and
                 row.get("stream_artifacts_complete") is True for row in value["android_commands"]) and
             value.get("held_namespace_target_closed") is True and value.get("action_lock_released") is True and
             retired(value.get("lease_FDs_final")), "RAW_PERMISSION_SERVICE_CAPTURE_AND_RETIREMENT_GATE_FAILED")
        need(value.get("permission_queries_executed") is True and value.get("service_output_semantics_verified") is False and
             value.get("effective_permission_grants") == "UNKNOWN_PENDING_SERVICE_OUTPUT_INTERPRETATION" and
             value.get("effective_AppOps_modes") == "UNKNOWN_PENDING_SERVICE_OUTPUT_INTERPRETATION" and
             value.get("role_status") == "UNKNOWN_NOT_QUERIED" and value.get("package_dump_user_filter_applied") is False and
             value.get("permission_name_normalization") == "NONE_RAW_BYTES_PRESERVED" and set(value.get("help_results", {})) == {"package"} and
             len(value.get("service_reports", [])) == 2 and
             all(row.get("interpretation_status") == "RAW_CAPTURE_ONLY_NOT_INTERPRETED" for row in value["service_reports"]) and
             value.get("native_catalog_matches_actual45_component_reference") is True and
             value.get("compiled_Beike_scope_modified") is False and value.get("old_Bili_unknown_reclassified") is False and
             value.get("meituan_saved_location_unchanged") is True and value.get("all_installed_APK_bytes_bound") is False,
             "READONLY_QUERY_MUST_NOT_CLAIM_GRANTS_OR_EXPAND_UI_AUTHORITY")
        need(value.get("original_failure") == {'job_id': '1a1b2be17ec-fc05-7f8b', 'state': 'failed', 'exit_code': 1, 'original_capture_plan_sha256': '802c9616b99c0c753c7a31188ab7b594e5baba39d6940d963c2c1b9bd2cdb749', 'original_request_sha256': 'f8913b60ae88b149f24b5bd1b5a1c4343082281ad656ea32b14c153efc6614ca', 'original_worker_sha256': '8c7d2ca5835f5cacb12f56430180fde88bac55c8cd6cfb219eece434bee19ba7', 'artifact': {'bytes': 27164, 'sha256': 'f86711fe87e7c4976dd61cdd5c53bbfeb5f4692af773990d89db088781758cf3'}, 'outer_stdout': {'bytes': 18089, 'sha256': 'ae37fe1743be6c1588d899e06e8b0ad42fa1fe625572826c9cb852ff554800f2'}, 'terminal': {'bytes': 730, 'sha256': 'bd1a4b5cc261490f0a18aeb55ce99eede71fd5a4882d174e5801a3ee00cb7ac4'}, 'gate_stop': {'bytes': 3152, 'sha256': 'd2ab87f1aa7674003db63a588e650431d7b3c147b59852fd23c8f5a8790dabc8'}, 'inner_first_cause': 'CHILD_OUTPUT_BOUND', 'original_worker_error_label': 'HOST_COMMAND_TIMEOUT', 'command_returncode': -9, 'capture_limit_bytes': 262144, 'captured_stdout_prefix': {'bytes': 262145, 'path': '/home/alex/work/pocket4-launcher-permissions-observation-20261106-r1-b02/android-02.stdout', 'sha256': '07a337b83a8fe84e25ebe608d49155ad294a9c5d83a8aa376f82353fb3914fad'}, 'stdout_eof': False, 'stderr_eof': False, 'service_capture_complete': False, 'AppOps_query_executed': False, 'original_gate_state': 'STOP_FAILED_OR_UNVERIFIED_BATCH', 'original_failure_reclassified': False} and
             value.get("capture_policy") == {'scope': 'exact_microG_second_command_stdout_only', 'commands': [['/system/bin/cmd', 'package', 'help'], ['/system/bin/cmd', 'package', 'dump-package', 'com.google.android.gms'], ['/system/bin/cmd', 'appops', 'get', '--user', '0', 'com.google.android.gms']], 'stream_limits': [{'stdout': 262144, 'stderr': 262144}, {'stdout': 2097152, 'stderr': 262144}, {'stdout': 262144, 'stderr': 262144}], 'command_timeout_seconds': 30, 'Android_timeout_seconds': 25, 'total_worker_budget_seconds': 900, 'other_package_limits_changed': False, 'raw_output_private': True, 'automatic_retry': False} and
             value.get("original_failed_capture_reclassified") is False and value.get("original_b02_ledger_advanced") is False and
             value.get("corrective_b02_capture_complete") is True and
             [row.get("capture_limits") for row in value["android_commands"]] == [{'stdout': 262144, 'stderr': 262144}, {'stdout': 2097152, 'stderr': 262144}, {'stdout': 262144, 'stderr': 262144}],
             "EXACT_INDEPENDENT_MICROG_CORRECTION_REQUIRED")
        for index, row in enumerate(value["android_commands"]):
            need(tuple(row["argv"][-len([('/system/bin/cmd', 'package', 'help'), ('/system/bin/cmd', 'package', 'dump-package', 'com.google.android.gms'), ('/system/bin/cmd', 'appops', 'get', '--user', '0', 'com.google.android.gms')][index]):]) == tuple([('/system/bin/cmd', 'package', 'help'), ('/system/bin/cmd', 'package', 'dump-package', 'com.google.android.gms'), ('/system/bin/cmd', 'appops', 'get', '--user', '0', 'com.google.android.gms')][index]) and
                 all(type(row[stream + "_bytes"]) is int and 0 <= row[stream + "_bytes"] <= row["capture_limits"][stream]
                     for stream in ("stdout", "stderr")), "EXACT_MICROG_COMMAND_AND_STREAM_LIMITS")
        actions = ("UI_actions", "App_launches", "installs", "permission_changes", "lifecycle_commands", "ADB_commands", "business_data_content_reads")
    need(all(type(value.get(key)) is int and value[key] == 0 for key in actions), "READ_ONLY_ACTION_BOUNDARY_CHANGED")


def child():
    enter("--child")
    need(sys.stdin.buffer.read(1) == b"R", "ORIGINAL_HELD_PARENT_PIDFD_RELEASE_REQUIRED")
    result = {"schema": "pocket4-owned-readonly-observation-child-v1", "kind": CONFIG["kind"], "ok": False, "errors": [],
              "worker_invoked": False, "manual_library_FD_close": False, "unknown_FDs_closed": 0,
              "production_ready": False, "result_requires_parent_pidfd_retirement": True}
    probe, frozen = None, None
    try:
        support = load(SUPPORT, "original_proven_library_bootstrap")
        probe = support.load_module(support.PROBE_SOURCE, "original_proven_pidfd_helper")
        observed = support.probe_proof()
        initial, frozen, library_fd, library = support.initialize_library(probe, observed)
        result.update(bootstrap_initial_descriptors=initial, bootstrap_library_resource=library,
                      frozen_descriptors_before_worker=frozen)
        worker = load(CONFIG["worker"], "exact_new_readonly_worker")
        pin_bytes(CONFIG["request"])
        need(probe.same_descriptors(frozen, probe.census()), "PRE_WORKER_FD_SET_CHANGED")
        args = sys.argv
        output = io.StringIO()
        returned = None
        try:
            sys.argv = [CONFIG["worker"]["path"], "--request", CONFIG["request"]["path"], "--request-sha256", CONFIG["request"]["sha256"]]
            result["worker_invoked"] = True
            with contextlib.redirect_stdout(output):
                returned = worker.main()
        finally:
            sys.argv = args
            raw = output.getvalue().encode("utf-8")
            result.update(worker_returncode=returned, worker_stdout_original=raw.decode("utf-8"),
                          worker_stdout_bytes=len(raw), worker_stdout_sha256=hashlib.sha256(raw).hexdigest())
        value = decode_worker(raw)
        worker_gate(value, returned)
        for pin in (SUPPORT, support.PROBE_SOURCE, CONFIG["worker"], CONFIG["request"], SELF_PIN):
            pin_bytes(pin)
        support.probe_proof()
        support.pin_runtime_files(probe, observed)
        final = probe.census()
        need(probe.same_descriptors(frozen, final), "FINAL_UNKNOWN_MISSING_OR_REPLACED_DESCRIPTOR")
        need(probe.library_binding(library_fd, final[str(library_fd)]) == library, "LIBRARY_RESOURCE_CHANGED_DURING_OBSERVATION")
        result["frozen_descriptors_after_worker"] = final
        result["ok"] = True
    except BaseException as error:
        result["errors"].append({"type": type(error).__name__, "reason": str(error)[:512]})
    finally:
        if probe is not None and frozen is not None:
            try:
                final = probe.census()
                result["final_descriptors"] = final
                need(probe.same_descriptors(frozen, final), "FINAL_FD_IDENTITY_MISMATCH")
            except BaseException as error:
                result["ok"] = False
                result["errors"].append({"stage": "final_census", "type": type(error).__name__, "reason": str(error)[:512]})
    raw = canonical(result)
    need(len(raw) < MAX_OUTPUT, "CHILD_OUTPUT_BOUND")
    print(raw.decode("ascii"), flush=True)
    return 0 if result["ok"] else 1


def combined(life, child_value, stderr):
    return (life.get("returncode") == 0 and life.get("pidfd_acquired") is True and life.get("pidfd_exit_observed") is True and
            life.get("pidfd_closed") is True and life.get("parent_descriptors_restored") is True and
            life.get("owned_child_sigkill_count") == 0 and life.get("timeout") is False and life.get("errors") == [] and
            not stderr and child_value.get("schema") == "pocket4-owned-readonly-observation-child-v1" and
            child_value.get("kind") == CONFIG["kind"] and child_value.get("ok") is True and child_value.get("errors") == [])


def publish(name, raw):
    need(re.fullmatch("[A-Za-z0-9_.-]+", name) is not None and len(raw) <= 262144, "BOUNDED_NEW_OWNED_RECEIPT")
    directory = os.open(CONFIG["stage_root"], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(directory)
        need(info.st_uid == 0 and stat.S_IMODE(info.st_mode) == 0o700, "ROOT_PRIVATE_STAGE_REQUIRED")
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400, dir_fd=directory)
        try:
            data = memoryview(raw)
            while data:
                count = os.write(fd, data); need(count > 0, "RECEIPT_WRITE_PROGRESS"); data = data[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(directory)
    finally:
        os.close(directory)
    pin = {"path": CONFIG["stage_root"] + "/" + name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    need(pin_bytes(pin) == raw, "RECEIPT_READBACK")
    return pin


def main():
    result = {"schema": "pocket4-owned-readonly-observation-result-v1", "ok": False, "automatic_retry": False,
              "UI_actions": 0, "installs": 0, "permission_changes": 0, "old_results_reclassified": False,
              "production_ready": False, "inner_result_alone_qualifies": False, "errors": []}
    try:
        enter("--execute-observation")
        result["kind"] = CONFIG["kind"]
        support = load(SUPPORT, "original_bootstrap_parent_support")
        probe = support.load_module(support.PROBE_SOURCE, "original_owned_pidfd_support")
        observed = support.probe_proof()
        support.pin_runtime_files(probe, observed)
        before = probe.census()
        life, raw, stderr = probe.run_owned_child([sys.executable, "-I", "-B", str(Path(__file__).resolve()), "--child",
            "--source-sha256", SELF_PIN["sha256"], "--source-bytes", str(SELF_PIN["bytes"])], seconds=1000)
        result["child_lifecycle"] = life
        result["child_stdout"] = publish("child.stdout.original.json", raw)
        result["child_stderr"] = publish("child.stderr.original", stderr)
        result["descendant_status_after_forced_worker_exit"] = (
            "UNKNOWN_REQUIRES_RECONCILIATION" if life.get("owned_child_sigkill_count") else "REQUIRES_INNER_RETIREMENT_RECEIPTS")
        child_value = json.loads(raw)
        result["child_result"] = child_value
        if isinstance(child_value.get("worker_stdout_original"), str):
            worker_raw = child_value["worker_stdout_original"].encode("utf-8")
            need(len(worker_raw) == child_value["worker_stdout_bytes"] and hashlib.sha256(worker_raw).hexdigest() == child_value["worker_stdout_sha256"],
                 "EXACT_ORIGINAL_WORKER_STDOUT_REQUIRED")
            result["worker_stdout"] = publish("worker.stdout.original.jsonl", worker_raw)
        need(combined(life, child_value, stderr), "ORIGINAL_PIDFD_AND_CHILD_JOINT_GATE_FAILED")
        worker_raw = child_value["worker_stdout_original"].encode("utf-8")
        need(len(worker_raw) == child_value["worker_stdout_bytes"] and hashlib.sha256(worker_raw).hexdigest() == child_value["worker_stdout_sha256"],
             "EXACT_ORIGINAL_WORKER_STDOUT_REQUIRED")
        worker_gate(decode_worker(worker_raw), child_value["worker_returncode"])
        for pin in (SELF_PIN, SUPPORT, support.PROBE_SOURCE, CONFIG["worker"], CONFIG["request"]):
            pin_bytes(pin)
        support.probe_proof()
        support.pin_runtime_files(probe, observed)
        need(probe.same_descriptors(before, probe.census()), "PARENT_FD_IDENTITY_NOT_RESTORED")
        result["library_FD_retired_by_original_held_owned_child_exit"] = True
        result["prior_source_preserved"] = CONFIG["prior_source"]
        result["ok"] = True
    except BaseException as error:
        result["errors"].append({"type": type(error).__name__, "reason": str(error)[:512]})
    result["status"] = "READONLY_OBSERVATION_AND_OWNED_LIFETIME_VERIFIED" if result["ok"] else "READONLY_OBSERVATION_OR_LIFETIME_INCOMPLETE_NO_RETRY"
    raw = canonical(result)
    need(len(raw) <= 262144, "PARENT_RESULT_BOUND")
    print(raw.decode("ascii"), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(child() if sys.argv[1:2] == ["--child"] else main())
