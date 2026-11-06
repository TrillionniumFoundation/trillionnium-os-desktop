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
CONFIG = {'schema': 'pocket4-owned-readonly-observation-config-v1', 'kind': 'calendar', 'stage_root': '/home/alex/work/pocket4-linked-official-audit-source-20261106-r2-b08', 'worker': {'path': '/home/alex/work/pocket4-linked-official-audit-source-20261106-r2-b08/audit_remaining_batches.py', 'bytes': 67206, 'sha256': 'e92ee6edc129e0488c7ae13c2c853c804436bcb799f4413f84eab06a529d1e44'}, 'request': {'path': '/home/alex/work/pocket4-linked-official-audit-source-20261106-r2-b08/request.review-only.json', 'bytes': 3342, 'sha256': '6bfac37f0023313c0e6489cbd2ac2d0d5f8b44bc029ef7f3142ff0322c379045'}, 'prior_unexecuted_source': {'bytes': 46019, 'sha256': 'e9935fd73b49a72b1bf79c098ee21486c7a35c1fddf7fa188b7a4091d1dc0c89', 'preserved': True, 'meaning': 'prior Debian comparison source and its actual outcome retained; field name is inherited'}}
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
    need(type(CONFIG) is dict and set(CONFIG) == {"schema", "kind", "stage_root", "worker", "request", "prior_unexecuted_source"} and
         CONFIG["schema"] == "pocket4-owned-readonly-observation-config-v1" and CONFIG["kind"] in ("explicit47", "calendar"),
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
    if CONFIG["kind"] == "calendar":
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
    else:
        need(value.get("schema") == "pocket4-linked-official-remaining-apk-audit-v1" and
             value.get("status") == "LINKED_ORIGINAL_BATCH_APK_AUDIT_VERIFIED" and
             all(value.get(key) is True for key in ("snapshot_consistent", "all_primary_commands_succeeded",
                 "all_commands_succeeded", "all_manifests_and_signatures_verified", "all_tool_children_joined", "action_lock_released",
                 "linked_batch_audit_complete", "official_badging_stderr_empty", "official_layout_descriptors_closed", "official_layout_before_and_after_all_commands")) and
             value.get("unjoined_tool_pids") == [] and len(value.get("commands", [])) == 36 and
             value.get("packages") == ['com.android.threadnetwork.demoapp', 'com.bestbuy.android', 'com.ehi.national.mobile', 'com.hertz.android.digital'], "CALENDAR_COMPARISON_GATE_FAILED")
        need(value.get("continuation_of") == {'original_plan_sha256': 'd288affedc2eae8d28f2d7083df4c89d756e51ba8e5ebfb2264f9d3c6d783139', 'original_failed_b05_job_id': '1a1b16f06d5-fc05-78b1', 'original_b05_state': 'failed', 'original_b05_exit_code': 1, 'corrective_job_id': '1a1b289b789-fc05-7e7e', 'corrective_result': {'path': '/home/alex/work/pocket4-successor-apk-audit-20261106-b05-official-tool-repair-r1-01/result.json', 'bytes': 276285, 'sha256': '3d0c794f4e2ac04ee6c67c22cd62ae4d560fc3c11e5f8faa7e514145f6a421f1'}, 'corrective_source_sha256': 'b4d27e1364feb28cab6634c77ed764e15359720025192117ecc8cb84d4391e1a', 'corrective_authoritative_terminal_sha256': 'c0d5d07a7be5d7ccbbbdc0451a4ac1a553bf690a1956b84ba7891aedc7f8652c'} and
             value.get("original_batch") == 8 and value.get("request") == {'app_scope': {'bytes': 58854, 'path': '/home/alex/work/pocket4-current-explicit-47-app-observation-20261106-r2/app-scope.private.json', 'sha256': '44f9ce783000a672c270e98afdaeb74bd79654508bfacae6793316ff4252e52f'}, 'guard': {'bytes': 3213, 'path': '/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/current_baseline_guard.py', 'sha256': 'd84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3'}, 'legacy_candidate_aapt2': {'bytes': 54512, 'file': {'st_ctime_ns': 1791415705179294996, 'st_dev': 66306, 'st_gid': 0, 'st_ino': 108138273, 'st_mode': 33261, 'st_mtime_ns': 1757926427000000000, 'st_nlink': 1, 'st_size': 54512, 'st_uid': 0}, 'path': '/usr/lib/android-sdk/build-tools/debian/aapt2', 'sha256': '0e9ff92342040acdfd03e8708512f4e02353e3ca0a2b85ea2950da659110b009'}, 'legacy_candidate_inventory': {'bytes': 9876, 'path': '/home/alex/work/pocket4-calendar-official-aapt2-source-20261106-r1/inputs/inventory.original.json', 'sha256': '60ee9c47cb1719343a1667d306e26086d66f2376d62b8c5251f4e64446887341'}, 'legacy_candidate_proof': {'bytes': 54192, 'path': '/home/alex/work/pocket4-calendar-official-aapt2-source-20261106-r1/inputs/aapt2-proof.outer.original.json', 'sha256': 'f9c289f7d28f836c51d845b4c851c1dbac0e8f326d658c7b98106b6ee327f192'}, 'legacy_candidate_terminal': {'bytes': 730, 'path': '/home/alex/work/pocket4-calendar-official-aapt2-source-20261106-r1/inputs/aapt2-proof.terminal.original.json', 'sha256': 'f797f008a250a386ca905e9b7e9065ac2f85cad2168be702c3ad01209d341802'}, 'official_candidate_aapt2': {'bytes': 6489808, 'file': {'st_ctime_ns': 1793993457351638049, 'st_dev': 66306, 'st_gid': 0, 'st_ino': 110244195, 'st_mode': 33088, 'st_mtime_ns': 1793993457351638049, 'st_nlink': 1, 'st_size': 6489808, 'st_uid': 0}, 'path': '/var/lib/pocket4-official-aapt2-host-tool-proof-20261106-r3/toolchain/platform/bin/aapt2', 'sha256': 'd0c30c343c61bfdc837abd02e195741dba7407bcb61ca34e037bcc1dc26ea06c'}, 'official_host_stdout': {'bytes': 7092, 'path': '/home/alex/work/pocket4-calendar-official-aapt2-source-20261106-r1/inputs/official-host.stdout.original.jsonl', 'sha256': 'd7785fb80d8075267b99f1ccc5537cdd12dc014f38fd72c87eb575bd899dd343'}, 'official_host_terminal': {'bytes': 731, 'path': '/home/alex/work/pocket4-calendar-official-aapt2-source-20261106-r1/inputs/official-host.terminal.original.json', 'sha256': 'f456a3ee2db689339d5d60db5106904b0d2bde640663eccc222311db39f62435'}, 'official_release_assets': None, 'output_root': '/home/alex/work/pocket4-successor-apk-audit-20261106-linked-official-r2-b08', 'packages': ['com.android.threadnetwork.demoapp', 'com.bestbuy.android', 'com.ehi.national.mobile', 'com.hertz.android.digital'], 'schema': 'pocket4-linked-official-remaining-batch-request-v1', 'original_batch': 8, 'continuation_of': {'original_plan_sha256': 'd288affedc2eae8d28f2d7083df4c89d756e51ba8e5ebfb2264f9d3c6d783139', 'original_failed_b05_job_id': '1a1b16f06d5-fc05-78b1', 'original_b05_state': 'failed', 'original_b05_exit_code': 1, 'corrective_job_id': '1a1b289b789-fc05-7e7e', 'corrective_result': {'path': '/home/alex/work/pocket4-successor-apk-audit-20261106-b05-official-tool-repair-r1-01/result.json', 'bytes': 276285, 'sha256': '3d0c794f4e2ac04ee6c67c22cd62ae4d560fc3c11e5f8faa7e514145f6a421f1'}, 'corrective_source_sha256': 'b4d27e1364feb28cab6634c77ed764e15359720025192117ecc8cb84d4391e1a', 'corrective_authoritative_terminal_sha256': 'c0d5d07a7be5d7ccbbbdc0451a4ac1a553bf690a1956b84ba7891aedc7f8652c'}} and
             value.get("corrective_publication_reference") == {'path': '/home/alex/work/pocket4-successor-apk-audit-20261106-b05-official-tool-repair-r1-01/result.json', 'bytes': 276285, 'sha256': '3d0c794f4e2ac04ee6c67c22cd62ae4d560fc3c11e5f8faa7e514145f6a421f1'} and
             value.get("legacy_badging_reexecuted") is False, "EXACT_LINKED_ORIGINAL_PENDING_BATCH")
        layout = value.get("official_private_layout", {})
        need(layout.get("observation_count") == 74 and
             layout.get("all_observations_complete") is True and
             layout.get("full_original_observations_persisted_and_read_back") is True and
             layout.get("artifact", {}).get("path") == '/home/alex/work/pocket4-successor-apk-audit-20261106-linked-official-r2-b08/official-layout-observations.private.json' and
             type(layout["artifact"].get("bytes")) is int and 0 < layout["artifact"]["bytes"] <= 524288 and
             re.fullmatch("[0-9a-f]{64}", layout["artifact"].get("sha256", "")) is not None,
             "COMPLETE_PERSISTED_LAYOUT_OBSERVATIONS_REQUIRED")
        need(value.get("original_failed_audit_reclassified") is False and value.get("original_batch_05_gate_advanced") is False,
             "ORIGINAL_FAILURE_MUST_REMAIN")
        actions = ("UI_actions", "App_launches", "permission_changes", "installs", "Android_namespace_commands", "ADB_commands", "business_data_content_reads")
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
        result["prior_unexecuted_source_preserved"] = CONFIG["prior_unexecuted_source"]
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
