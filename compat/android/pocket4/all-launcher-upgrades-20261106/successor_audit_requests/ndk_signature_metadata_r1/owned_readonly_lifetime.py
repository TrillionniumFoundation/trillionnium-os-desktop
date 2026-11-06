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
CONFIG = {'schema': 'pocket4-owned-readonly-observation-config-v1', 'kind': 'ndk', 'stage_root': '/home/alex/work/pocket4-ndk-current-apk-audit-source-20261106-r1', 'worker': {'path': '/home/alex/work/pocket4-ndk-current-apk-audit-source-20261106-r1/audit_ndk_current.py', 'bytes': 75213, 'sha256': '745a85c39be224d9f62fc6700ac71d9f3f4110f60ecca2e217b970bb643ea1fc'}, 'request': {'path': '/home/alex/work/pocket4-ndk-current-apk-audit-source-20261106-r1/request.review-only.json', 'bytes': 4396, 'sha256': 'c9d690b68771e84f99575c326b25c98b863d171516bf62f6d6043b9c3e5df4d0'}, 'prior_unexecuted_source': {'bytes': 75666, 'sha256': '5eb184f3ae89749a00c5bbe3459f6a9bacd3bfdcc0cdcae7ba0ac90140013a71', 'preserved': True, 'meaning': 'Actual b13 source and receipts remain preserved; this inherited field name does not reclassify it as unexecuted.'}}
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
         CONFIG["schema"] == "pocket4-owned-readonly-observation-config-v1" and CONFIG["kind"] in ("explicit47", "ndk"),
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
    if CONFIG["kind"] == "ndk":
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
    need(returned == 0 and value.get("schema") == "pocket4-independent-ndk-apk-signature-metadata-v1" and
         value.get("status") == "NDK_CURRENT_APK_SIGNATURE_AND_METADATA_VERIFIED" and
         value.get("ndk_audit_complete") is True and value.get("errors") == [] and
         value.get("automatic_retry") is False and value.get("production_ready") is False and
         value.get("process_FDs_before") == value.get("process_FDs_after"), "NDK_COMPLETE_WORKER_GATE")
    guard = value.get("guard_before", {})
    need(guard.get("schema") == "pocket4-successor-main-guard-v1" and
         guard.get("runtime_epoch_sha256") == "a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9" and
         value.get("guard_after") == guard and retired(value.get("owned_descriptors_final")), "NDK_RUNTIME_AND_FD_GATE")
    need(value.get("packages") == ["com.example.ndk_tests"] and len(value.get("protected_packages", [])) == 48 and
         value.get("scope_guard_before") == value.get("scope_guard_after") and
         value["scope_guard_before"].get("packages") == value["protected_packages"] and
         value["scope_guard_before"].get("app_scope_sha256") == "b184299ce0a39a998752ed980a43192b396099f780bcf60bcfe53d0edf92ffe4" and
         value.get("scope_qualification", {}).get("normal_owned_joint_validated") is True and
         value["scope_qualification"].get("scope_is_signature_evidence") is False,
         "EXACT_48_PROTECTION_WITH_INDEPENDENT_NEW_SIGNATURE")
    fields = ("snapshot_consistent", "all_commands_succeeded", "all_primary_commands_succeeded",
              "all_manifests_and_signatures_verified", "all_tool_children_joined", "official_badging_stderr_empty",
              "official_layout_descriptors_closed", "official_layout_before_and_after_all_commands", "action_lock_released")
    need(all(value.get(key) is True for key in fields) and value.get("unjoined_tool_pids") == [] and
         len(value.get("commands", [])) == 3 and len(value.get("apps", [])) == 1,
         "NDK_THREE_ORDINARY_TOOLS_AND_COMPLETE_RESOURCE_RETIREMENT")
    app = value["apps"][0]
    need(app.get("package") == "com.example.ndk_tests" and app.get("uid") == 10162 and app.get("PM_version_code") == 0 and
         len(app.get("apks", [])) == 1 and app["apks"][0].get("bytes") == 1397258 and
         app["apks"][0].get("sha256") == "b3bf438dedbcdd5f3ac871733a273b3cece446db6be308df73f95b08cb46d164" and
         app["apks"][0].get("held_bytes_and_full_stat_and_path_unchanged") is True and
         app["apks"][0].get("parse_errors") == [] and
         all(app.get(key) is True for key in ("complete_APK_set_observed", "one_base_manifest_observed",
             "all_APKs_signature_verified", "all_current_signers_equal_PM_records",
             "all_manifests_match_PM_identity", "all_permission_names_decoded")), "NDK_APK_AND_METADATA_COMPLETE")
    signature = app["apks"][0]["signature"]
    need(signature.get("cryptographic_verification_performed") is True and signature.get("verified") is True and
         signature.get("API_minimum_override_used") is False and signature.get("integrity_check_bypassed") is False and
         signature.get("signer_certificate_sha256") == ["a899ddfa8c4b57a962c2bb1ae885a44bd904d7b63f6fd301abf514edf70ad72c"],
         "NDK_NORMAL_SIGNATURE_NOT_API_OVERRIDE")
    need([row.get("name") for row in value["commands"]] == ["apksigner", "badging", "manifest"] and
         all(row.get("returncode") == 0 and row.get("joined") is True and row.get("pipes_closed") is True and
             row.get("output_capture_complete") is True and row.get("timed_out") is False and
             row.get("own_group_kill_requested") is False and not row.get("error") and not row.get("retirement_error")
             for row in value["commands"]), "THREE_NORMAL_UNSIGNALLED_TOOL_EXITS_REQUIRED")
    layout = value.get("official_private_layout", {})
    need(layout.get("encoding") == "zlib-base64" and layout.get("observation_count") == 8 and
         layout.get("all_observations_complete") is True and layout.get("full_original_observations_persisted_and_read_back") is True and
         layout.get("owned_directory_descriptors", {}).get("acquired") == 11 and
         layout["owned_directory_descriptors"].get("closed") == 11 and layout["owned_directory_descriptors"].get("errors") == [],
         "COMPLETE_ACTUAL_OFFICIAL_TOOL_LAYOUT_EVIDENCE")
    need(value.get("vendor_artifact_source_trust") == "UNKNOWN" and value.get("original_failures_reclassified") is False and
         value.get("old_ledger_modified") is False and value.get("UI_or_install_admitted") is False and
         value.get("effective_permission_grants") == "UNKNOWN_NOT_QUERIED" and
         value.get("resource_table_integrity_fully_proved") is False and
         value.get("success_gate_requires_outer_final_stdout_and_authoritative_terminal") is True,
         "APK_IDENTITY_AND_SIGNATURE_DO_NOT_QUALIFY_OTHER_DOMAINS")
    need(all(type(value.get(key)) is int and value[key] == 0 for key in
             ("UI_actions", "App_launches", "permission_changes", "installs", "Android_namespace_commands", "ADB_commands",
              "business_data_content_reads", "native_commands", "new_scopes_published")), "NDK_READ_ONLY_ACTION_BOUNDARY")

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
