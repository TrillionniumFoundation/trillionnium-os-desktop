#!/usr/bin/env python3
"""Fresh explicit 47-package host observation; no Android command or UI."""
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
STAGE = "/home/alex/work/pocket4-explicit-47-scope-source-20261106-r1"
OUTPUT = "/home/alex/work/pocket4-current-explicit-47-app-observation-20261106-r1"
GUARD = {"path": BASE + "/current_baseline_guard.py", "bytes": 3213,
         "sha256": "d84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3"}
READER = {"path": BASE + "/source/observe_successor_scope.py", "bytes": 7695,
          "sha256": "0a61313f518c7308f65f2654254689120df940cb0f5bd95d8873a42d6979914d"}
PARENT = {"path": "/home/alex/work/pocket4-successor-native-install-20261106-douyin-01/app-scope-after.private.json",
          "bytes": 57340, "sha256": "489129d6e39a5aebc410ebcf74706279a99ff6751a15bd0a6b324ddd007e01a4"}
CATALOG = {"path": STAGE + "/inputs/native45.original.json", "bytes": 10114,
           "sha256": "1352cb70367b09af255283dcbaecd8680c4d6bad662cf6432d01e2f2d6cabf54"}
INSTALL = {"path": STAGE + "/inputs/helper-install.stdout.original.jsonl", "bytes": 4262,
           "sha256": "68d4fcc329964f143794f5b59ce8556ddce5b7ba92546709025bd8ff52fea51a"}
TERMINAL = {"path": STAGE + "/inputs/helper-install.terminal.original.json", "bytes": 731,
            "sha256": "00d055ff77076430c9800957063a59e8ccbae249115213a09bdb32d7d71c5150"}
INSTALL_JOB = "1a1b1a29797-fc05-79fc"
HELPER = "org.droidloom.qa.successor.p8f89f253350ba2fa.r1"
HELPER_UID = 10157
HELPER_SHA = "006b3bdd64fcd8a03a4ceac0d036b3b99906140feadee61d198756cb6c55c8d9"
HELPER_CERT = "d48d103342b42791ae4e927d70258062d0de11f9acb9f32b4426aff583f27d6f"
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
PACKAGES = sorted((*LAUNCHERS, ACTIONS, HELPER))
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


def validate_inputs(catalog, installed, terminal):
    need(catalog.get("ok") is True and catalog.get("state") == "running", "ACTUAL_NATIVE_CATALOG_REQUIRED")
    apps = catalog.get("applications")
    need(type(apps) is list and len(apps) == 45 and len({x["package"] for x in apps}) == 45 and
         {x["package"] for x in apps} == set(LAUNCHERS), "EXACT_CAPTURED_NATIVE_45_REQUIRED")
    need(terminal.get("job_id") == INSTALL_JOB and terminal.get("state") == "succeeded" and terminal.get("exit_code") == 0,
         "ACTUAL_HELPER_INSTALL_TERMINAL_REQUIRED")
    need(all(terminal.get(key) is True for key in ("output_complete", "output_durable", "terminal_publication_confirmed")) and
         all(terminal.get(key) is False for key in ("automatic_retry", "timed_out", "cancelled")), "HELPER_INSTALL_NOT_SETTLED")
    need(terminal.get("log_truncated") == {"stdout": False, "stderr": False} and
         terminal.get("log_errors") == {"stdout": None, "stderr": None} and
         terminal.get("log_synced") == {"stdout": True, "stderr": True}, "HELPER_INSTALL_LOGS_INCOMPLETE")
    need(installed.get("schema") == "pocket4-successor-owned-helper-install-v1" and installed.get("ok") is True and
         installed.get("install_success_observed") is True and installed.get("outcome_unknown") is False and
         installed.get("errors") == [] and installed.get("automatic_retry") is False, "ACTUAL_SUCCESSFUL_HELPER_INSTALL_REQUIRED")
    need(installed.get("package") == HELPER and installed.get("helper_uid") == HELPER_UID and
         all(type(installed.get(key)) is int and installed[key] == 0 for key in ("UI_actions", "App_launches", "permission_grants")),
         "HELPER_PACKAGE_OR_ACTION_BOUNDARY_CHANGED")
    after = installed["installed_after_state"]
    need(after["package"] == HELPER and after["uid"] == HELPER_UID and after["bytes"] == 37008 and
         after["apk_sha256"] == HELPER_SHA and after["signer_bound_by_exact_signed_apk_bytes"] == HELPER_CERT,
         "HELPER_ACTUAL_INSTALLED_BYTES_CHANGED")
    return after


def validate_request(request):
    need(set(request) == {"schema", "guard", "reader", "parent_app_scope", "native_catalog", "helper_install", "helper_terminal",
                          "packages", "output_root", "worker"}, "CLOSED_EXPLICIT_SCOPE_REQUEST")
    need(request["schema"] == "pocket4-explicit-47-app-scope-request-v1" and request["guard"] == GUARD and
         request["reader"] == READER and request["parent_app_scope"] == PARENT and request["native_catalog"] == CATALOG and
         request["helper_install"] == INSTALL and request["helper_terminal"] == TERMINAL and request["packages"] == PACKAGES and
         len(PACKAGES) == len(set(PACKAGES)) == 47 and request["output_root"] == OUTPUT, "EXACT_EXPLICIT_47_SCOPE_REQUIRED")
    need(request["worker"]["path"] == STAGE + "/observe_explicit_47.py", "EXACT_SELF_SOURCE_PATH")


def run(request):
    validate_request(request)
    need(os.getuid() == os.geteuid() == 0, "EXISTING_HOST_ROOT_REQUIRED")
    need(str(Path(__file__).resolve()) == request["worker"]["path"], "REAL_SELF_FILE_REQUIRED")
    read_root_pin(request["worker"])
    result = {"schema": "pocket4-explicit-47-app-scope-observation-v1", "ok": False, "packages": PACKAGES,
              "native_catalog_reference_only": True, "framework_MAIN_LAUNCHER_resolver_queried": False,
              "all_Android_installed_packages_enumerated": False, "effective_grants_AppOps_roles": "UNKNOWN_NOT_QUERIED",
              "Main_UI_actions": 0, "native_commands": 0, "Android_namespace_commands": 0, "ADB_commands": 0,
              "installs": 0, "permission_changes": 0, "business_data_content_reads": 0, "old_unknown_receipts_modified": False,
              "automatic_retry": False, "UI_or_install_admitted": False, "production_ready": False, "errors": []}
    catalog_raw, install_raw, terminal_raw = (read_root_pin(pin) for pin in (CATALOG, INSTALL, TERMINAL))
    catalog, installed, terminal = parse(catalog_raw), parse(install_raw), parse(terminal_raw)
    helper_after = validate_inputs(catalog, installed, terminal)
    guard = load_source(GUARD, "explicit47_actual_runtime_guard")
    reader = load_source(READER, "explicit47_original_observer")
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
        baseline = guard.current_baseline()
        need(catalog["host_pid"] == baseline["runtime"]["held"]["process_snapshot"]["binding"]["processes"]["launcher"]["host_pid"],
             "CAPTURED_NATIVE_CATALOG_OWNER_DIFFERS")
        parent_scope = core.parse(core.pinned_record(PARENT))
        need(parent_scope["schema"] == "pocket4-versioned-app-scope-v1" and parent_scope["runtime_epoch_sha256"] == EPOCH and
             set(parent_scope["apps"]) == set(LAUNCHERS) | {ACTIONS}, "EXACT_SAME_EPOCH_PARENT_46_REQUIRED")
        observer_request = {"schema": "pocket4-successor-app-observation-request-v1", "guard": GUARD,
                            "packages": PACKAGES, "parent_app_scope": PARENT,
                            "install_or_signature_evidence": [INSTALL, TERMINAL, CATALOG],
                            "output_scope": OUTPUT + "/app-scope.private.json",
                            "output_binding": OUTPUT + "/observation-binding.private.json"}
        result["observer_request"] = core.write_new(OUTPUT + "/observer-request.json", core.canonical(observer_request) + b"\n")
        observation = reader.run(observer_request)
        need(observation.get("ok") is True, "ORIGINAL_READER_DID_NOT_QUALIFY_OBSERVATION")
        observed_fds = observation["observation_fds"]
        need(observed_fds["acquired"] == observed_fds["closed"] and observed_fds["remaining"] == 0 and observed_fds["errors"] == [],
             "ORIGINAL_READER_FDS_NOT_RETIRED")
        scope = core.parse(core.pinned_record(observation["app_scope"]))
        need(scope["runtime_epoch_sha256"] == EPOCH and set(scope["apps"]) == set(PACKAGES), "ACTUAL_SCOPE_NOT_EXACT_47")
        need(all(scope["apps"][name] == expected for name, expected in parent_scope["apps"].items()), "ORIGINAL_46_APP_IDENTITY_CHANGED")
        helper = scope["apps"][HELPER]
        need(helper["uid"] == HELPER_UID and helper["package_manager_certificate_sha256"] == [HELPER_CERT] and len(helper["apks"]) == 1,
             "ACTUAL_HELPER_PM_IDENTITY_CHANGED")
        apk = helper["apks"][0]
        need(apk["path"] == helper_after["base_apk"] and apk["bytes"] == helper_after["bytes"] and apk["sha256"] == HELPER_SHA,
             "ACTUAL_HELPER_APK_DIFFERS_FROM_INSTALLED_BYTES")
        for key, old_key in (("st_dev", "device"), ("st_ino", "inode"), ("st_uid", "uid"), ("st_gid", "gid"),
                             ("st_mode", "mode"), ("st_nlink", "nlink"), ("st_size", "bytes"), ("st_mtime_ns", "mtime_ns")):
            need(apk["file"][key] == helper_after["held_file"][old_key], "HELPER_INSTALLED_FILE_IDENTITY_CHANGED")
        need(all(row["status"] == "ABSENT" or row["status"] == "PRESENT" and row["uid"] == HELPER_UID and row["gid"] == HELPER_UID
                 for row in helper["data_directories"].values()), "HELPER_CE_DE_OWNER_CHANGED")
        after = guard.current_guard()
        need(before == after, "RUNTIME_CHANGED_DURING_EXPLICIT_SCOPE")
        for pin in (GUARD, READER, CATALOG, INSTALL, TERMINAL, request["worker"]):
            read_root_pin(pin)
        core.pinned_record(PARENT)
        current = core.open_host(pool, OUTPUT, os.O_RDONLY | os.O_DIRECTORY)
        try:
            current_identity = core.metadata(current)
            need(all(current_identity[key] == directory_identity[key] for key in
                     ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode")), "NEW_OUTPUT_DIRECTORY_IDENTITY_CHANGED")
        finally:
            pool.close(current)
        result.update(ok=True, status="EXPLICIT_47_PACKAGE_SCOPE_OBSERVED", guard_before=before, guard_after=after,
                      observation=observation, original_46_unchanged=True, new_helper_matches_actual_install=True,
                      package_count=47, APK_count=sum(len(row["apks"]) for row in scope["apps"].values()),
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
        result = {"schema": "pocket4-explicit-47-scope-entry-rejection-v1", "ok": False, "type": type(error).__name__,
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
