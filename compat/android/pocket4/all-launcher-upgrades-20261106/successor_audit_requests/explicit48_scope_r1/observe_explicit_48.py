#!/usr/bin/env python3
"""Fresh explicit 48-package identity scope; no command, signature promotion or UI."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types

sys.dont_write_bytecode = True
EPOCH = "a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9"
BASE = "/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01"
STAGE = '/home/alex/work/pocket4-explicit-48-scope-source-20261106-r1'
OUTPUT = '/home/alex/work/pocket4-current-explicit-48-app-observation-20261106-r1'
GUARD = {"path": BASE + "/current_baseline_guard.py", "bytes": 3213,
         "sha256": "d84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3"}
READER = {"path": BASE + "/source/observe_successor_scope.py", "bytes": 7695,
          "sha256": "0a61313f518c7308f65f2654254689120df940cb0f5bd95d8873a42d6979914d"}
PARENT = {'bytes': 58854, 'path': '/home/alex/work/pocket4-current-explicit-47-app-observation-20261106-r2/app-scope.private.json', 'sha256': '44f9ce783000a672c270e98afdaeb74bd79654508bfacae6793316ff4252e52f'}
DISCOVERY = {'path': '/home/alex/work/pocket4-explicit-48-scope-source-20261106-r1/inputs/discovery-artifact.original.json', 'bytes': 112546, 'sha256': '69482778466e03dceff2defc85fb8f68880c360a3f112e129561a8fd5e6e5400'}
DISCOVERY_OUTER = {'path': '/home/alex/work/pocket4-explicit-48-scope-source-20261106-r1/inputs/discovery-stdout.original.jsonl', 'bytes': 31226, 'sha256': '474893612abaf6192653b31d16adb808a2d46e92cf6e1683760e532684d5fe5d'}
DISCOVERY_TERMINAL = {'path': '/home/alex/work/pocket4-explicit-48-scope-source-20261106-r1/inputs/discovery-terminal.original.json', 'bytes': 733, 'sha256': 'f16d1da55f8afa0da6f91f37186fff39dc50ba12a22e54b048290e723dc797bd'}
DISCOVERY_VALIDATOR = {'path': '/home/alex/work/pocket4-native46-discovery-source-20261106-r1/owned_readonly_lifetime.py', 'bytes': 20365, 'sha256': 'c121e6eea1b5162048cbb40207aaef2861be527fed554e8bc5c44d3229524cc0'}
NEW_IDENTITY = {'bytes': 905, 'path': '/home/alex/work/pocket4-native46-discovery-observation-20261106-r1/new-package-identity.private.json', 'sha256': '82e5fc2fb1e5d8a48af4217d9f2f7096583e545584d39258b6f9590f5bd47e52'}
DISCOVERY_JOB = '1a1b307f521-fc05-807a'
DISCOVERY_STAGE = '/home/alex/work/pocket4-native46-discovery-source-20261106-r1'
NEW_PACKAGE = 'com.example.ndk_tests'
NEW_COMPONENT = 'com.example.ndk_tests/com.example.ndk_tests.NdkTestsActivity'
NEW_APK_SHA = 'b3bf438dedbcdd5f3ac871733a273b3cece446db6be308df73f95b08cb46d164'
NEW_PM_CERT = 'a899ddfa8c4b57a962c2bb1ae885a44bd904d7b63f6fd301abf514edf70ad72c'
HELPER = 'org.droidloom.qa.successor.p8f89f253350ba2fa.r1'
ACTIONS = "local.pocket4.actions.v2"
LAUNCHERS = (
    "com.Hyatt.hyt", "com.MobileTicket", "com.amazon.mShop.android.shopping",
    "com.android.calendar", "com.android.camera2", "com.android.contacts", "com.android.deskclock",
    "com.android.dialer", "com.android.documentsui", "com.android.gallery3d", "com.android.messaging",
    "com.android.quicksearchbox", "com.android.settings", "com.android.threadnetwork.demoapp",
    "com.bestbuy.android", "com.ehi.national.mobile", "com.enflick.android.TextNow", "com.google.android.gms",
    "com.hertz.android.digital", "com.hilton.android.hhonors", "com.ihg.apps.android", "com.jingdong.app.mall",
    "com.lianjia.beike", "com.marriott.mrt", "com.pinger.textfree", "com.rytong.airchina", "com.rytong.ceair",
    "com.sankuai.meituan.takeoutnew", "com.sdu.didi.psnger", "com.ss.android.ugc.aweme", "com.szzc",
    "com.taobao.taobao", "com.tencent.mm", "com.ubercab", "com.united.mobile.android", "com.xunmeng.pinduoduo",
    "com.zhubajie.client", "com.zillow.android.streeteasy", "ctrip.android.view", "jp.co.ana.android.tabidachi",
    "local.pocket4.fixture", "org.chromium.webview_shell", "org.droidloom.qa.editorcontract",
    "org.fcitx.fcitx5.android", "tv.danmaku.bili")
ORIGINAL_PACKAGES = sorted((*LAUNCHERS, ACTIONS, HELPER))
PACKAGES = sorted((*ORIGINAL_PACKAGES, NEW_PACKAGE))
STAT = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def parse(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            need(key not in value, "DUPLICATE_JSON_KEY")
            value[key] = item
        return value
    def invalid(value):
        raise RuntimeError("NONFINITE_JSON")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def read_root_pin(pin, limit=262144):
    need(type(pin) is dict and set(pin) == {"path", "bytes", "sha256"}, "COMPLETE_SOURCE_PIN_REQUIRED")
    path = pin["path"]
    need(type(path) is str and path.startswith("/") and all(x not in ("", ".", "..") for x in path[1:].split("/")),
         "CANONICAL_ABSOLUTE_PIN_PATH")
    need(type(pin["bytes"]) is int and 0 < pin["bytes"] <= limit and re.fullmatch("[0-9a-f]{64}", pin["sha256"]),
         "BOUNDED_EXACT_PIN_REQUIRED")
    descriptors = []
    try:
        parent = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC); descriptors.append(parent)
        parts = path[1:].split("/")
        for name in parts[:-1]:
            parent = os.open(name, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            descriptors.append(parent)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        descriptors.append(fd)
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1 and before.st_size == pin["bytes"],
             "EXACT_ROOT_OWNED_REGULAR_SOURCE_REQUIRED")
        raw, end = bytearray(), time.monotonic() + 10
        while len(raw) <= limit:
            need(time.monotonic() < end, "PIN_READ_DEADLINE")
            part = os.read(fd, min(65536, limit + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
        current = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        descriptors.append(current)
        need(len(raw) == pin["bytes"] and sha(raw) == pin["sha256"] and
             all(getattr(before, key) == getattr(os.fstat(fd), key) == getattr(os.fstat(current), key) for key in STAT),
             "PINNED_SOURCE_OR_PATH_CHANGED")
        return bytes(raw)
    finally:
        errors = []
        for fd in reversed(descriptors):
            try:
                os.close(fd)
            except OSError:
                errors.append(fd)
        need(not errors, "BOOTSTRAP_FDS_NOT_RETIRED")


def load_source(pin, name):
    raw = read_root_pin(pin)
    module = types.ModuleType(name)
    module.__file__ = pin["path"]
    exec(compile(raw, pin["path"], "exec"), module.__dict__)
    return module



def validate_inputs(artifact_raw, outer_raw, terminal_raw, validator):
    artifact, terminal = parse(artifact_raw), parse(terminal_raw)
    need(len(outer_raw.splitlines()) == 2, "EXACT_TWO_LINE_DISCOVERY_STAGE_AND_JOINT")
    staged, outer = [parse(line) for line in outer_raw.splitlines()]
    need(terminal.get("job_id") == DISCOVERY_JOB and terminal.get("state") == "succeeded" and
         type(terminal.get("exit_code")) is int and terminal["exit_code"] == 0,
         "ACTUAL_DISCOVERY_SUCCESSFUL_TERMINAL_REQUIRED")
    need(all(terminal.get(key) is True for key in ("output_complete", "output_durable", "terminal_publication_confirmed")) and
         all(terminal.get(key) is False for key in ("automatic_retry", "timed_out", "cancelled")), "DISCOVERY_NOT_DURABLY_SETTLED")
    need(terminal.get("log_truncated") == {"stdout": False, "stderr": False} and
         terminal.get("log_errors") == {"stdout": None, "stderr": None} and
         terminal.get("log_synced") == {"stdout": True, "stderr": True} and
         terminal.get("log_bytes") == {"stdout": {"seen": len(outer_raw), "stored": len(outer_raw)},
                                      "stderr": {"seen": 0, "stored": 0}}, "DISCOVERY_COMPLETE_ORIGINAL_STREAMS_REQUIRED")
    need(staged.get("schema") == "pocket4-native46-discovery-source-stage-result-v1" and staged.get("source_stage_ok") is True and
         staged.get("source_root") == DISCOVERY_STAGE and staged.get("automatic_retry") is False and
         staged.get("bootstrap_FDs_before") == staged.get("bootstrap_FDs_after") and
         all(type(staged.get(key)) is int and staged[key] == 0 for key in
             ("stage_Main_reads", "stage_UI_actions", "stage_installs", "stage_namespace_entries")), "EXACT_DISCOVERY_STAGE_REQUIRED")
    need(validator.CONFIG["kind"] == "services" and validator.CONFIG["stage_root"] == DISCOVERY_STAGE,
         "ACTUAL_DISCOVERY_VALIDATOR_CONFIGURATION")
    source_rows = staged.get("files")
    need(type(source_rows) is list and len(source_rows) == 7 and len({row["name"] for row in source_rows}) == 7,
         "DISCOVERY_STAGE_SOURCE_CLOSURE")
    source_by_name = {row["name"]: row for row in source_rows}
    for reference in (DISCOVERY_VALIDATOR, validator.CONFIG["worker"], validator.CONFIG["request"]):
        name = reference["path"].removeprefix(DISCOVERY_STAGE + "/")
        need(source_by_name.get(name) == {"name": name, "bytes": reference["bytes"], "sha256": reference["sha256"]},
             "DISCOVERY_STAGE_ACTUAL_SOURCE_PIN_MISMATCH")
    need(outer.get("schema") == "pocket4-owned-readonly-observation-result-v1" and outer.get("ok") is True and
         outer.get("status") == "READONLY_OBSERVATION_AND_OWNED_LIFETIME_VERIFIED" and outer.get("kind") == "services" and
         outer.get("errors") == [] and outer.get("automatic_retry") is False and outer.get("production_ready") is False and
         outer.get("inner_result_alone_qualifies") is False and outer.get("old_results_reclassified") is False and
         outer.get("library_FD_retired_by_original_held_owned_child_exit") is True and
         all(type(outer.get(key)) is int and outer[key] == 0 for key in ("UI_actions", "installs", "permission_changes")),
         "DISCOVERY_OWNED_OUTER_GATE_FAILED")
    child = outer["child_result"]
    need(validator.combined(outer["child_lifecycle"], child, b""), "DISCOVERY_OWNED_CHILD_DID_NOT_RETIRE_NORMALLY")
    need(outer["child_stderr"]["bytes"] == 0 and outer["child_stderr"]["sha256"] == sha(b"") and
         child.get("worker_invoked") is True and child.get("manual_library_FD_close") is False and
         type(child.get("unknown_FDs_closed")) is int and child["unknown_FDs_closed"] == 0 and
         child.get("production_ready") is False and child.get("result_requires_parent_pidfd_retirement") is True and
         child["frozen_descriptors_before_worker"] == child["frozen_descriptors_after_worker"] == child["final_descriptors"],
         "DISCOVERY_EXACT_FD_AND_LIBRARY_LIFETIME_REQUIRED")
    worker_raw = child["worker_stdout_original"].encode("utf-8")
    need(len(worker_raw) == child["worker_stdout_bytes"] == outer["worker_stdout"]["bytes"] and
         sha(worker_raw) == child["worker_stdout_sha256"] == outer["worker_stdout"]["sha256"],
         "DISCOVERY_ORIGINAL_WORKER_STREAM_PIN")
    envelope = parse(worker_raw)
    need(envelope["artifact_bytes"] == len(artifact_raw) == DISCOVERY["bytes"] and
         envelope["artifact_sha256"] == sha(artifact_raw) == DISCOVERY["sha256"], "DISCOVERY_COMPLETE_ARTIFACT_PIN")
    need(validator.decode_worker(worker_raw) == artifact, "DISCOVERY_DECODED_ARTIFACT_DIFFERS")
    validator.worker_gate(artifact, child["worker_returncode"])
    need(artifact["app_scope_reference"] == PARENT and artifact["packages"] == ORIGINAL_PACKAGES and
         artifact["scope_guard_before"] == artifact["scope_guard_after"] and
         artifact["scope_guard_before"]["app_scope_sha256"] == PARENT["sha256"], "EXACT_ORIGINAL_47_PROTECTION_REQUIRED")
    proposed = artifact["proposed_immutable_scope_review"]
    need(proposed["original_scope_reference"] == PARENT and proposed["original_packages"] == ORIGINAL_PACKAGES and
         proposed["additional_package"] == NEW_PACKAGE and proposed["proposed_packages"] == PACKAGES and
         proposed["proposed_count"] == 48 and proposed["new_identity_reference"] == NEW_IDENTITY and
         proposed["new_scope_published"] is False and proposed["new_runtime_or_UI_authority"] is False,
         "EXACT_NEW_48_SET_MUST_HAVE_ACTUAL_DISCOVERY")
    identity = artifact["new_package_identity"]
    need(identity["package"] == NEW_PACKAGE and type(identity["uid"]) is int and identity["uid"] == 10162 and
         type(identity["version_code"]) is int and identity["version_code"] == 0 and
         identity["fresh_signature_verification"] is False and
         identity["package_manager_certificate_sha256"] == [NEW_PM_CERT] and len(identity["apks"]) == 1 and
         identity["apks"][0]["bytes"] == 1397258 and identity["apks"][0]["sha256"] == NEW_APK_SHA,
         "ACTUAL_DISCOVERED_NDK_IDENTITY_REQUIRED")
    identity_raw = canonical({NEW_PACKAGE: identity}) + b"\n"
    need(len(identity_raw) == NEW_IDENTITY["bytes"] and sha(identity_raw) == NEW_IDENTITY["sha256"] and
         artifact["new_package_identity_receipt"] == NEW_IDENTITY, "ACTUAL_NEW_IDENTITY_RECEIPT_REQUIRED")
    rows = artifact["MAIN_LAUNCHER_components"]
    need(len(rows) == 46 and len({row["component"] for row in rows}) == 46 and
         {row["package"] for row in rows} == set(LAUNCHERS) | {NEW_PACKAGE} and
         [row["component"] for row in rows if row["package"] == NEW_PACKAGE] == [NEW_COMPONENT],
         "COMPLETE_ACTUAL_46_RESOLVER_REFERENCE_REQUIRED")
    need(artifact["native_before"] == artifact["native_after"] and artifact["native_before"].get("ok") is True and
         artifact["native_before"].get("state") == "running", "DISCOVERY_NATIVE_OWNER_NOT_STABLE")
    return artifact, identity


def validate_projection(scope, parent_scope, identity):
    need(parent_scope["schema"] == "pocket4-versioned-app-scope-v1" and parent_scope["runtime_epoch_sha256"] == EPOCH and
         sorted(parent_scope["apps"]) == ORIGINAL_PACKAGES, "EXACT_SAME_EPOCH_PARENT_47_REQUIRED")
    need(scope["schema"] == "pocket4-versioned-app-scope-v1" and scope["runtime_epoch_sha256"] == EPOCH and
         sorted(scope["apps"]) == PACKAGES and scope["parent_app_scope"] == PARENT,
         "ACTUAL_SCOPE_NOT_EXACT_48")
    need(scope["fresh_signature_verification_performed"] is False and scope["UI_or_install_runtime_admitted"] is False and
         scope["external_evidence_policy_validated_by_this_reader"] is False,
         "IDENTITY_SCOPE_MUST_NOT_PROMOTE_SIGNATURE_OR_RUNTIME_AUTHORITY")
    need(all(scope["apps"][name] == expected for name, expected in parent_scope["apps"].items()),
         "ORIGINAL_47_APP_IDENTITY_CHANGED")
    need(scope["apps"][NEW_PACKAGE] == identity, "NDK_UID_APK_SIGNER_PM_DATA_OR_FILE_IDENTITY_CHANGED")



def validate_request(request):
    need(set(request) == {"schema", "guard", "reader", "parent_app_scope", "discovery_artifact", "discovery_outer",
                          "discovery_terminal", "discovery_validator", "new_identity", "packages", "output_root", "worker"},
         "CLOSED_EXPLICIT_SCOPE_REQUEST")
    need(request["schema"] == "pocket4-explicit-48-app-scope-request-v1" and request["guard"] == GUARD and
         request["reader"] == READER and request["parent_app_scope"] == PARENT and request["discovery_artifact"] == DISCOVERY and
         request["discovery_outer"] == DISCOVERY_OUTER and request["discovery_terminal"] == DISCOVERY_TERMINAL and
         request["discovery_validator"] == DISCOVERY_VALIDATOR and request["new_identity"] == NEW_IDENTITY and
         request["packages"] == PACKAGES and len(PACKAGES) == len(set(PACKAGES)) == 48 and
         len(ORIGINAL_PACKAGES) == 47 and set(PACKAGES) - set(ORIGINAL_PACKAGES) == {NEW_PACKAGE} and
         request["output_root"] == OUTPUT, "EXACT_EXPLICIT_48_SCOPE_REQUIRED")
    need(request["worker"]["path"] == STAGE + "/observe_explicit_48.py", "EXACT_SELF_SOURCE_PATH")


def run(request):
    validate_request(request)
    need(os.getuid() == os.geteuid() == 0, "EXISTING_HOST_ROOT_REQUIRED")
    need(str(Path(__file__).resolve()) == request["worker"]["path"], "REAL_SELF_FILE_REQUIRED")
    read_root_pin(request["worker"])
    result = {"schema": "pocket4-explicit-48-app-scope-observation-v1", "ok": False, "packages": PACKAGES,
              "native46_resolver_and_discovery_reference_only": True, "new_signature_verification_performed": False,
              "vendor_artifact_source_trust": "UNKNOWN", "original_47_scope_modified": False,
              "original_permission_gate_modified": False, "original_b03_failure_reclassified": False, "framework_MAIN_LAUNCHER_resolver_queried": False,
              "all_Android_installed_packages_enumerated": False, "effective_grants_AppOps_roles": "UNKNOWN_NOT_QUERIED",
              "Main_UI_actions": 0, "native_commands": 0, "Android_namespace_commands": 0, "ADB_commands": 0,
              "installs": 0, "permission_changes": 0, "business_data_content_reads": 0, "old_unknown_receipts_modified": False,
              "automatic_retry": False, "UI_or_install_admitted": False, "production_ready": False, "errors": []}
    artifact_raw, outer_raw, terminal_raw = (read_root_pin(pin) for pin in (DISCOVERY, DISCOVERY_OUTER, DISCOVERY_TERMINAL))
    validator = load_source(DISCOVERY_VALIDATOR, "actual_native46_pure_joint_validator")
    discovery, new_identity = validate_inputs(artifact_raw, outer_raw, terminal_raw, validator)
    need(parse(read_root_pin(NEW_IDENTITY)) == {NEW_PACKAGE: new_identity}, "ORIGINAL_DISCOVERED_IDENTITY_BYTES_CHANGED")
    guard = load_source(GUARD, "explicit48_actual_runtime_guard")
    reader = load_source(READER, "explicit48_original_observer")
    core = guard._core()
    pool, locks = core.FDs(), []
    try:
        parent = core.open_host(pool, "/home/alex/work", os.O_RDONLY | os.O_DIRECTORY)
        try:
            leaf = Path(OUTPUT).name
            os.mkdir(leaf, 0o700, dir_fd=parent)
            os.fsync(parent)
            directory = pool.own(os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent))
        finally:
            pool.close(parent)
        directory_identity = core.metadata(directory)
        need(directory_identity["st_uid"] == 0 and stat.S_IMODE(directory_identity["st_mode"]) == 0o700, "NEW_PRIVATE_OBSERVATION_ROOT")
        flow_fd = pool.own(os.open("flow.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory))
        try:
            os.fsync(flow_fd)
        finally:
            pool.close(flow_fd)
        os.fsync(directory)
        for path in (OUTPUT + "/flow.lock", core.ACTION_LOCK):
            fd, identity = core.acquire_lock(pool, path)
            locks.append(fd)
            result.setdefault("lock_identities", []).append({"path": path, "identity": identity})
        before = guard.current_guard()
        need(before.get("schema") == "pocket4-successor-main-guard-v1" and before.get("runtime_epoch_sha256") == EPOCH,
             "CURRENT_TYPED_SUCCESSOR_REQUIRED")
        need(before == discovery["guard_before"], "RUNTIME_MUST_MATCH_ACTUAL_DISCOVERY")
        baseline = guard.current_baseline()
        need(discovery["native_before"]["host_pid"] == baseline["runtime"]["held"]["process_snapshot"]["binding"]["processes"]["launcher"]["host_pid"],
             "DISCOVERY_NATIVE_OWNER_DIFFERS_FROM_CURRENT_BASELINE")
        parent_scope = core.parse(core.pinned_record(PARENT))
        need(parent_scope["schema"] == "pocket4-versioned-app-scope-v1" and parent_scope["runtime_epoch_sha256"] == EPOCH and
             sorted(parent_scope["apps"]) == ORIGINAL_PACKAGES, "EXACT_SAME_EPOCH_PARENT_47_REQUIRED")
        parent_guard_before = guard.check_app_scope(PARENT, ORIGINAL_PACKAGES)
        observer_request = {"schema": "pocket4-successor-app-observation-request-v1", "guard": GUARD,
                            "packages": PACKAGES, "parent_app_scope": PARENT,
                            "install_or_signature_evidence": [DISCOVERY, DISCOVERY_OUTER, DISCOVERY_TERMINAL, NEW_IDENTITY],
                            "output_scope": OUTPUT + "/app-scope.private.json",
                            "output_binding": OUTPUT + "/observation-binding.private.json"}
        result["observer_request"] = core.write_new(OUTPUT + "/observer-request.json", core.canonical(observer_request) + b"\n")
        observation = reader.run(observer_request)
        need(observation.get("ok") is True, "ORIGINAL_READER_DID_NOT_QUALIFY_OBSERVATION")
        observed_fds = observation["observation_fds"]
        need(observed_fds["acquired"] == observed_fds["closed"] and observed_fds["remaining"] == 0 and observed_fds["errors"] == [],
             "ORIGINAL_READER_FDS_NOT_RETIRED")
        scope = core.parse(core.pinned_record(observation["app_scope"]))
        validate_projection(scope, parent_scope, new_identity)
        parent_guard_after = guard.check_app_scope(PARENT, ORIGINAL_PACKAGES)
        need(parent_guard_before == parent_guard_after, "ORIGINAL_47_PROTECTION_CHANGED")
        need(observation["app_scope_guard"]["packages"] == PACKAGES and
             observation["app_scope_guard"]["current_apk_paths_and_file_identities_match"] is True and
             observation["app_scope_guard"]["UI_or_install_runtime_admitted"] is False and
             observation["app_scope_guard"]["new_signature_verification_performed"] is False,
             "NEW_SCOPE_IS_IDENTITY_ONLY")
        after = guard.current_guard()
        need(before == after, "RUNTIME_CHANGED_DURING_EXPLICIT_SCOPE")
        for pin in (GUARD, READER, DISCOVERY, DISCOVERY_OUTER, DISCOVERY_TERMINAL, DISCOVERY_VALIDATOR, NEW_IDENTITY, request["worker"]):
            read_root_pin(pin)
        core.pinned_record(PARENT)
        current = core.open_host(pool, OUTPUT, os.O_RDONLY | os.O_DIRECTORY)
        try:
            current_identity = core.metadata(current)
            need(all(current_identity[key] == directory_identity[key] for key in
                     ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode")), "NEW_OUTPUT_DIRECTORY_IDENTITY_CHANGED")
        finally:
            pool.close(current)
        result.update(ok=True, status="EXPLICIT_48_PACKAGE_IDENTITY_SCOPE_OBSERVED", guard_before=before, guard_after=after,
                      observation=observation, original_47_unchanged=True, new_package_matches_actual_discovery=True,
                      parent_scope_guard_before=parent_guard_before, parent_scope_guard_after=parent_guard_after,
                      discovery_joint_validated=True, discovery_job_id=DISCOVERY_JOB,
                      discovery_inputs=[DISCOVERY, DISCOVERY_OUTER, DISCOVERY_TERMINAL], new_identity_reference=NEW_IDENTITY,
                      scope_requires_outer_owned_lifetime_and_durable_terminal=True, package_count=48, APK_count=sum(len(row["apks"]) for row in scope["apps"].values()),
                      logical_APK_bytes=sum(apk["bytes"] for row in scope["apps"].values() for apk in row["apks"]),
                      action_lock_held_through_scope_publication=True)
    except BaseException as error:
        result["errors"].append({"type": type(error).__name__, "reason": str(error)[:250]})
        result["status"] = "EXPLICIT_SCOPE_OBSERVATION_INCOMPLETE_NO_RETRY"
    finally:
        for fd in reversed(locks):
            try:
                fcntl.flock(fd, fcntl.LOCK_UN)
            except BaseException as error:
                result["errors"].append({"stage": "unlock", "type": type(error).__name__})
        result["locks_released"] = not any(row.get("stage") == "unlock" for row in result["errors"])
        try:
            pool.close_all()
        except BaseException as error:
            result["errors"].append({"stage": "FD_close", "type": type(error).__name__})
        result["owned_descriptors_final"] = pool.summary()
        if result["errors"]:
            result["ok"] = False
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--request-sha256", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    before = len(os.listdir("/proc/self/fd"))
    try:
        # Request byte size is fixed by the separately reviewed source-stage pin.
        size = os.stat(args.request, follow_symlinks=False).st_size
        request = parse(read_root_pin({"path": args.request, "bytes": size, "sha256": args.request_sha256}))
        result = run(request)
    except BaseException as error:
        result = {"schema": "pocket4-explicit-48-scope-entry-rejection-v1", "ok": False, "type": type(error).__name__,
                  "reason": str(error)[:250], "automatic_retry": False, "UI_or_install_admitted": False, "production_ready": False}
    result["process_FDs_before"] = before
    result["process_FDs_after"] = len(os.listdir("/proc/self/fd"))
    if result["process_FDs_after"] != before:
        result["ok"] = False
        result["status"] = "EXPLICIT_SCOPE_FINAL_FD_DIFFERENCE"
        result.setdefault("errors", []).append({"reason": "PROCESS_FD_DIFFERENCE"})
    raw = canonical(result)
    need(len(raw) <= 131072, "BOUNDED_RESULT")
    print(raw.decode("ascii"), flush=True)
    return 0 if result.get("ok") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())
