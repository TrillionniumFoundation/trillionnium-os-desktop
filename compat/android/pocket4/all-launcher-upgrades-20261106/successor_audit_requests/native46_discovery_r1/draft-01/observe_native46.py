#!/usr/bin/env python3
"""New explicit47-bound user0 PM/resolver with PackageManager help only.

This standalone source does not import or extend an existing per-App Flow or
its source contract. Frozen R5 entry/classpath primitives remain unchanged.
"""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import signal
import stat
import subprocess
import sys
import time
import types
import zlib

sys.dont_write_bytecode = True
EPOCH = "a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9"
BASE = "/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01"
GUARD = {"path": BASE + "/current_baseline_guard.py", "bytes": 3213,
         "sha256": "d84df98d55352ef9ae66753ee15f3746d9d9a64c35fddf392a08f10ba4105cb3"}
HELPER = "org.droidloom.qa.successor.p8f89f253350ba2fa.r1"
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
STAT = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
PACKAGES = sorted((*LAUNCHERS, ACTIONS, HELPER))
STAGE = '/home/alex/work/pocket4-native46-discovery-source-20261106-r1'
OUTPUT = '/home/alex/work/pocket4-native46-discovery-observation-20261106-r1'
APP_SCOPE = {'path': '/home/alex/work/pocket4-current-explicit-47-app-observation-20261106-r2/app-scope.private.json', 'bytes': 58854, 'sha256': '44f9ce783000a672c270e98afdaeb74bd79654508bfacae6793316ff4252e52f'}
TRANSPORT = {'path': '/home/alex/work/pocket4-native46-discovery-source-20261106-r1/readonly_services_transport.py', 'bytes': 16586, 'sha256': '786793e5aaa718cac509615107ceec5a22c0fde0831cb0e632343effc34e546f'}
NATIVE_HELPERS = {'path': '/home/alex/work/pocket4-successor-install-audit-source-20261106-r1/install_successor_native.py', 'bytes': 31327, 'sha256': 'ad4227b4c63033018bd1147c3c589b2632168766306791696aabc53583229c96'}

NEW_PACKAGE = 'com.example.ndk_tests'
NEW_COMPONENT = 'com.example.ndk_tests/com.example.ndk_tests.NdkTestsActivity'
PRIOR = {'previous_pm': {'path': '/home/alex/work/pocket4-native46-discovery-source-20261106-r1/inputs/previous_pm.json', 'bytes': 79176, 'sha256': '185c6b0900aab78228e44788ea28b10d71c39cfeee8846fcb8c99c13a9f123fc'}, 'failed_capture': {'path': '/home/alex/work/pocket4-native46-discovery-source-20261106-r1/inputs/failed_capture.json', 'bytes': 12181, 'sha256': 'f5ff1b1758803a9537bd84023146fa62ac72d8587b1dc94605868413dd2ffc08'}, 'failed_terminal': {'path': '/home/alex/work/pocket4-native46-discovery-source-20261106-r1/inputs/failed_terminal.json', 'bytes': 730, 'sha256': '4a95cb262ac9b2d8d4a0437c53fde9e82ea47b4529e6fd0e79fa87b32ef24552'}}

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

require = need
digest = sha

HELPER_ROOT = Path("/home/alex/work/pocket4-owned-held-ns-runner-r4-01")
HELPER_PATH = HELPER_ROOT / "held-namespace-entry"
HELPER_SOURCE = HELPER_ROOT / "held_namespace_entry.rs"
HELPER_SHA = "21ba02ff60ba07667c3b5601c1ff9cb9b2d9cce2fae9290a6f39e47c18126689"
HELPER_BYTES = 4_366_312
HELPER_SOURCE_SHA = "adf5b08f7854bec061ab8d2a208f3414339701c816218881e6550afde2e6c31c"
HELPER_QUALIFICATION = Path("/home/alex/work/pocket4-owned-held-ns-runner-r4-export-01/qualification.json")
HELPER_QUALIFICATION_SHA = "3e3dd5c9ae1b4e913d7a688bb338507162cbc211bb897658a539948ffb6f93e3"

def bounded_file(path, limit=131072):
    path = str(path)
    parts = path[1:].split("/")
    require(path.startswith("/") and not any(x in ("", ".", "..") for x in parts), "CANONICAL_SOURCE_PATH")
    fds = []
    try:
        d = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        fds.append(d)
        for part in parts[:-1]:
            d = os.open(part, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=d)
            fds.append(d)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=d)
        fds.append(fd)
        def meta(f):
            s = os.fstat(f)
            return tuple(getattr(s, k) for k in ("st_dev", "st_ino", "st_size", "st_mode", "st_uid", "st_gid", "st_nlink", "st_mtime_ns", "st_ctime_ns"))
        first = os.fstat(fd)
        before = meta(fd)
        require(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and 0 <= first.st_size <= limit, "BOUNDED_SINGLE_REGULAR_FILE")
        data, deadline = bytearray(), time.monotonic() + 10
        while len(data) <= limit:
            require(time.monotonic() < deadline, "SOURCE_READ_DEADLINE")
            chunk = os.read(fd, min(65536, limit + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        require(len(data) == first.st_size and meta(fd) == before, "SOURCE_CHANGED_DURING_READ")
        check = os.open(parts[-1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=d)
        fds.append(check)
        require(meta(check) == before, "SOURCE_PATH_REPLACED")
        return bytes(data)
    finally:
        failures = []
        for fd in reversed(fds):
            try:
                os.close(fd)
            except OSError:
                failures.append(fd)
        require(not failures, "SOURCE_FD_CLOSE_FAILED")

def verify_shared_helper():
    require(sha(bounded_file(HELPER_SOURCE)) == HELPER_SOURCE_SHA, "HELD_HELPER_SOURCE_CHANGED")
    helper = bounded_file(HELPER_PATH, HELPER_BYTES)
    require(len(helper) == HELPER_BYTES, "HELD_HELPER_BINARY_SIZE_CHANGED")
    require(sha(helper) == HELPER_SHA, "HELD_HELPER_BINARY_CHANGED")
    require(os.access(HELPER_PATH, os.X_OK), "HELD_HELPER_NOT_EXECUTABLE")
    for path in (HELPER_PATH, HELPER_SOURCE):
        require(path.lstat().st_mode & 0o022 == 0, "HELD_HELPER_WRITABLE_BY_OTHERS")
    raw = bounded_file(HELPER_QUALIFICATION)
    require(sha(raw) == HELPER_QUALIFICATION_SHA, "HELD_HELPER_QUALIFICATION_CHANGED")
    receipt = json.loads(raw)
    require(receipt.get("schema") == 1 and receipt.get("protocol") == "owned-held-namespace-entry-v1" and
            receipt.get("qualified_for_owned_namespace_entry") is True and
            receipt.get("helper_source_sha256") == HELPER_SOURCE_SHA and
            receipt.get("helper_binary_sha256") == HELPER_SHA and
            receipt.get("host_controls_passed") == 14 and
            receipt.get("six_namespace_host_entry_passed") is True and
            receipt.get("Main_readonly_entry_passed") is True and
            receipt.get("qualified_for_whole_process_tree_cleanup") is False and
            receipt.get("candidate_production_ready") is False,
            "HELD_HELPER_NOT_QUALIFIED_FOR_DECLARED_SCOPE")
    require(set(receipt.get("evidence", {})) == {"host14", "sixns", "main_readonly"},
            "HELD_HELPER_EVIDENCE_SET_CHANGED")
    for row in receipt["evidence"].values():
        require(sha(bounded_file(row["path"], 4 * 1024 * 1024)) == row["sha256"],
                "HELD_HELPER_ACTUAL_EVIDENCE_CHANGED")
        terminal = row["terminal"]
        require(terminal["state"] == "succeeded" and terminal["exit_code"] == 0 and
                terminal["cancelled"] is False and terminal["timed_out"] is False and
                terminal["output_complete"] is True and terminal["output_durable"] is True and
                terminal["terminal_publication_confirmed"] is True,
                "HELD_HELPER_EVIDENCE_TERMINAL_INCOMPLETE")
    return {"source_sha256": HELPER_SOURCE_SHA, "binary_sha256": HELPER_SHA,
            "qualification_sha256": HELPER_QUALIFICATION_SHA,
            "whole_process_tree_cleanup_qualified": False}

def same_epoch_identity(raw, expected):
    return (raw["pid"] == expected["host_pid"] and
            int(raw["start"]) == expected["start_ticks"] and
            raw["uid"] == [str(value) for value in expected["uids"]] and
            raw["ppid"] == expected["parent_host_pid"] and
            [int(value) for value in raw["nspid"]] == expected["namespace_pids"] and
            raw["exe"] == expected["executable"] and
            raw["cgroup"].splitlines() == expected["cgroup"] and
            all(raw["ns"][key] == value for key, value in expected["namespaces"].items()
                if key in raw["ns"]))

def selected_environment(raw):
    keys = {'PATH', 'BOOTCLASSPATH', 'DEX2OATBOOTCLASSPATH', 'ANDROID_ART_ROOT', 'ANDROID_ASSETS',
        'ANDROID_BOOTLOGO', 'ANDROID_DATA', 'ANDROID_I18N_ROOT', 'ANDROID_ROOT', 'ANDROID_STORAGE',
        'ANDROID_TZDATA_ROOT', 'ASEC_MOUNTPOINT', 'DOWNLOAD_CACHE', 'EXTERNAL_STORAGE',
        'LOOP_MOUNTPOINT', 'STANDALONE_SYSTEMSERVER_JARS', 'SYSTEMSERVERCLASSPATH', 'LANG'}
    found = {}
    for row in raw.split(b'\0'):
        if b'=' not in row:
            continue
        key, value = row.split(b'=', 1)
        name = key.decode('utf-8', 'strict')
        if name not in keys:
            continue
        require(name not in found and len(value) <= 65536, 'ENV_DUPLICATE_OR_BOUND')
        found[name] = value.decode('utf-8', 'strict')
    return found

def main_classpaths(held, target, framework_epoch, epoch, guard):
    """R5's two-root proof, labelled accurately for this fixed Main target."""
    guard()
    expected = framework_epoch["binding"]["processes"]["zygote64"]
    require(expected["namespaces"]["pid"] == target.expected["ns"]["pid"],
            "MAIN_ZYGOTE_PID_NAMESPACE_CHANGED")
    require(epoch.process_identity(expected["host_pid"]) == expected,
            "MAIN_ZYGOTE_CHANGED_BEFORE_ENVIRONMENT_READ")
    deadline = time.monotonic() + held.CLASSPATH_SECONDS
    view = held.HeldZygoteRoot(expected, deadline)
    primary = None
    try:
        raw = held.read_at(view.proc_fd, "environ", held.ENV_LIMIT, deadline)
        values = held.selected_classpaths(raw)
        environment = selected_environment(raw)
        del raw
        files, total = held.hash_classpaths_paired(target, view, values, deadline)
        again_raw = held.read_at(view.proc_fd, 'environ', held.ENV_LIMIT, deadline)
        again = held.selected_classpaths(again_raw)
        require(selected_environment(again_raw) == environment, 'HELD_ENVIRONMENT_CHANGED')
        del again_raw
        require(again == values, "MAIN_ZYGOTE_CLASSPATH_CHANGED_DURING_ADMISSION")
        view.verify()
        require(epoch.process_identity(expected["host_pid"]) == expected,
                "MAIN_ZYGOTE_GENERATION_CHANGED_AFTER_ENVIRONMENT_READ")
        target.verify()
        guard()
        return values, {"schema": 2, "source": "fixed Main zygote held procdir only",
            "zygote": expected, "required_keys": list(held.REQUIRED_CLASSPATHS),
            "values": values, "files": files, "total_bytes": total,
            "limits": {"environ_bytes": held.ENV_LIMIT, "path_count": held.PATH_COUNT_LIMIT,
                       "per_file_bytes": held.FILE_LIMIT, "total_file_bytes": held.TOTAL_FILE_LIMIT,
                       "deadline_seconds": held.CLASSPATH_SECONDS},
            "root": target.root_record, "zygote_root": view.root_record,
            "zygote_mount_namespace": held.fd_record(view.mnt_fd),
            "command_mount_namespace": held.fd_record(target.namespaces["mnt"]),
            "resolution_contract": "same dev/inode/size from simultaneously held init-root and zygote-root file descriptors; metadata stable around streaming hash",
            "different_mount_namespaces_permitted": True,
            "different_backing_files_permitted": False,
            "main_classpath_read": True}, environment
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            view.close()
        except BaseException as cleanup:
            if primary is None:
                raise
            primary.add_note("Main zygote root cleanup: " + type(cleanup).__name__ + ": " + str(cleanup))

def safe_error(error):
    result = {"type": type(error).__name__}
    if isinstance(error, OSError):
        result["errno"] = error.errno
    elif isinstance(error, RuntimeError) and re.fullmatch(r"[A-Z0-9_]{1,96}", str(error)):
        result["code"] = str(error)
    else:
        result["code"] = "UNEXPECTED_FAILURE_DETAILS_RETAINED_PRIVATELY"
    return result

def held_bounded_child(argv, seconds, limit, pass_fds, host_env):
    """No shell. Only the owned client process group may be killed on failure."""
    need(0 < seconds <= 60 and 0 < limit <= 262144, "CHILD_BOUNDS_REQUIRED")
    end = time.monotonic() + seconds
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    record = {"argv": list(argv), "started_monotonic_ns": time.monotonic_ns(), "joined": False,
              "returncode": None, "stdout_eof": False, "stderr_eof": False, "errors": [], "termination_attempted": False}
    child, pipes = None, []
    selector = selectors.DefaultSelector()
    try:
        child = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 cwd="/", env=host_env, pass_fds=pass_fds, close_fds=True, start_new_session=True)
        record["host_pid"] = child.pid
        for key, pipe in (("stdout", child.stdout), ("stderr", child.stderr)):
            pipes.append(pipe)
            os.set_blocking(pipe.fileno(), False)
            selector.register(pipe, selectors.EVENT_READ, key)
        while selector.get_map():
            need(time.monotonic() < end, "CHILD_TIMEOUT")
            for key, _ in selector.select(min(.1, max(0, end - time.monotonic()))):
                try:
                    data = os.read(key.fileobj.fileno(), min(65536, limit + 1 - len(buffers[key.data])))
                except BlockingIOError:
                    continue
                if not data:
                    record[key.data + "_eof"] = True
                    selector.unregister(key.fileobj)
                    continue
                buffers[key.data].extend(data)
                need(len(buffers[key.data]) <= limit, "CHILD_OUTPUT_BOUND")
        child.wait(timeout=max(.01, end - time.monotonic()))
        record["joined"], record["returncode"] = True, child.returncode
    except BaseException as error:
        record["errors"].append(safe_error(error))
    finally:
        if child is not None and child.returncode is None:
            record["termination_attempted"] = True
            try:
                os.killpg(child.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except BaseException as error:
                record["errors"].append(safe_error(error))
            try:
                child.wait(timeout=2)
                record["joined"], record["returncode"] = True, child.returncode
            except BaseException as error:
                record["errors"].append(safe_error(error))
        for pipe in pipes:
            try:
                pipe.close()
            except BaseException as error:
                record["errors"].append(safe_error(error))
        selector.close()
    for key, raw in buffers.items():
        record[key + "_bytes"] = len(raw)
        record[key + "_sha256"] = digest(raw)
    record["finished_monotonic_ns"] = time.monotonic_ns()
    record["complete"] = bool(record["joined"] and record["returncode"] == 0 and record["stdout_eof"] and
                              record["stderr_eof"] and not record["errors"] and not buffers["stderr"])
    return bytes(buffers["stdout"]), bytes(buffers["stderr"]), record

def write_empty_raw_stream(core, pool, directory, root_identity, path, raw):
    """Create only an exact empty command stream; other artifacts use frozen core."""
    name = path.rsplit("/", 1)[-1]
    need(type(raw) is bytes and raw == b"" and
         re.fullmatch(r"(?:native|android)-[0-9]{2}\.(?:stdout|stderr)", name) is not None,
         "ONLY_EMPTY_COMMAND_RAW_STREAM")
    need(all(core.metadata(directory)[key] == root_identity[key]
             for key in ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode")),
         "EMPTY_STREAM_PARENT_IDENTITY_CHANGED")
    fd = pool.own(os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                          0o400, dir_fd=directory))
    try:
        os.fchmod(fd, 0o400)
        os.fsync(fd)
        observed = os.fstat(fd)
        need(stat.S_ISREG(observed.st_mode) and observed.st_uid == root_identity["st_uid"] and
             stat.S_IMODE(observed.st_mode) == 0o400 and observed.st_nlink == 1 and observed.st_size == 0,
             "EMPTY_RAW_STREAM_METADATA")
        os.fsync(directory)
    finally:
        pool.close(fd)
    return {"path": path, "sha256": sha(raw), "bytes": 0}


def remember_child_streams(rows, row, write, prefix, raw, stderr):
    """Retain the actual child result even if an owned receipt cannot be saved."""
    rows.append(row)
    row.update(stdout=None, stderr=None, stream_artifacts_complete=False)
    try:
        row["stdout"] = write(prefix + ".stdout", raw)
        row["stderr"] = write(prefix + ".stderr", stderr)
        row["stream_artifacts_complete"] = True
    except BaseException as error:
        row["stream_artifact_error"] = safe_error(error)
        raise


def validate_request(request):
    need(type(request) is dict and set(request) == {"schema", "guard", "app_scope", "packages", "worker", "transport", "output_root"},
         "CLOSED_SERVICE_OBSERVATION_REQUEST")
    need(request["schema"] == "pocket4-native46-discovery-request-v1" and request["guard"] == GUARD and
         request["app_scope"] == APP_SCOPE and request["packages"] == PACKAGES and request["transport"] == TRANSPORT and
         request["output_root"] == OUTPUT, "EXACT_SCOPE_AND_CLOSED_OPERATION_REQUEST")
    need(request["worker"]["path"] == STAGE + "/observe_native46.py" and str(Path(__file__).resolve()) == request["worker"]["path"],
         "EXACT_REAL_SERVICE_SOURCE_REQUIRED")
    read_root_pin(request["worker"])


def parse_packages(raw):
    need(type(raw) is bytes and 0 < len(raw) <= 262144, "PACKAGE_LIST_BOUND")
    records, identities = [], set()
    for line in raw.decode("utf-8", "strict").splitlines():
        match = re.fullmatch(r"package:([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*) versionCode:(\d+) uid:(\d+(?:,\d+)*)", line)
        need(match is not None, "UNRECOGNISED_ACTUAL_PACKAGE_ROW")
        package, version, uids = match.groups()
        row = {"package": package, "version_code": int(version), "uids": [int(x) for x in uids.split(",")]}
        key = (package, row["version_code"], tuple(row["uids"]))
        need(key not in identities and 0 <= row["version_code"] < 2**63 and all(0 <= uid < 2**31 for uid in row["uids"]),
             "DUPLICATE_OR_OUT_OF_RANGE_PACKAGE_ROW")
        identities.add(key); records.append(row)
    need(0 < len(records) <= 4096, "INSTALLED_PACKAGE_COUNT_BOUND")
    return sorted(records, key=lambda row: (row["package"], row["version_code"], row["uids"]))


def component(raw):
    match = re.fullmatch(r"([A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z0-9_]+)*)/([A-Za-z0-9_.$]+)", raw)
    need(match is not None, "UNRECOGNISED_COMPONENT")
    package, name = match.groups()
    return {"package": package, "component": package + "/" + (package + name if name.startswith(".") else name),
            "original_component": raw}


def parse_resolver(raw):
    need(type(raw) is bytes and 0 < len(raw) <= 262144, "RESOLVER_OUTPUT_BOUND")
    lines = raw.decode("utf-8", "strict").splitlines()
    if lines == ["No activities found"]:
        return []
    need(0 < len(lines) <= 4096, "RESOLVER_COMPONENT_COUNT_BOUND")
    rows = [component(line) for line in lines]
    need(len({row["component"] for row in rows}) == len(rows), "DUPLICATE_RESOLVER_COMPONENT")
    return sorted(rows, key=lambda row: row["component"])


def require_help_for_closed_queries(raw):
    text = raw.decode("utf-8", "strict")
    required = ("list packages", "-U", "--show-versioncode", "--match-libraries", "--user USER_ID", "[FILTER]",
                "query-activities", "--components", "INTENT", "-a <ACTION>", "-c <CATEGORY>", "dump-package PACKAGE")
    need(all(value in text for value in required), "ACTUAL_PACKAGE_HELP_DOES_NOT_SUPPORT_EXACT_READONLY_QUERIES")
    return {"actual_help_sha256": sha(raw), "required_literals": list(required), "no_guessed_service_transaction": True}


def compare_catalogs(installed, resolver, native, apps):
    names = {row["package"] for row in installed}
    need(set(apps) <= names, "EXPLICIT47_MISSING_FROM_CURRENT_USER0_PM")
    for package, row in apps.items():
        matches = [value for value in installed if value["package"] == package and value["version_code"] == row["version_code"]]
        need(len(matches) == 1 and set(matches[0]["uids"]) == {row["uid"]}, "EXPLICIT47_CURRENT_PM_UID_OR_VERSION_CHANGED")
    native_rows = native.get("applications")
    need(type(native_rows) is list and len(native_rows) <= 4096, "NATIVE_CURRENT_CATALOG_BOUND")
    normal_native = []
    for row in native_rows:
        need(type(row) is dict and type(row.get("package")) is str and type(row.get("component")) is str,
             "CURRENT_NATIVE_APPLICATION_SCHEMA")
        parsed = component(row["component"])
        need(parsed["package"] == row["package"], "NATIVE_COMPONENT_PACKAGE_DIFFERS")
        normal_native.append(parsed)
    a = {row["component"] for row in resolver}
    b = {row["component"] for row in normal_native}
    return {"native_package_count": len({row["package"] for row in normal_native}), "native_component_count": len(normal_native),
            "PM_user0_package_count": len(names), "PM_user0_package_version_rows": len(installed),
            "MAIN_LAUNCHER_package_count": len({row["package"] for row in resolver}), "MAIN_LAUNCHER_component_count": len(resolver),
            "framework_only_components": sorted(a-b), "native_only_components": sorted(b-a),
            "PM_packages_outside_explicit47": sorted(names-set(apps)),
            "native_packages_added_since_original45": sorted({row["package"] for row in normal_native}-set(LAUNCHERS)),
            "native_packages_missing_since_original45": sorted(set(LAUNCHERS)-{row["package"] for row in normal_native}),
            "same_count_is_not_component_identity_proof": True}


def prior_observations():
    """Pinned historical inputs establish the question, never current authority."""
    values = {name: parse(read_root_pin(pin)) for name, pin in PRIOR.items()}
    previous, failed, terminal = values["previous_pm"], values["failed_capture"], values["failed_terminal"]
    need(previous.get("schema") == "pocket4-current-readonly-services-observation-v1" and
         previous.get("ok") is True and previous.get("errors") == [] and
         previous.get("status") == "CURRENT_PM_AND_MAIN_LAUNCHER_OBSERVED" and
         previous.get("enumeration_samples_equal") is True and
         previous.get("guard_before") == previous.get("guard_after") and
         previous["guard_before"]["runtime_epoch_sha256"] == EPOCH,
         "EXACT_PREVIOUS_PM_OBSERVATION_REQUIRED")
    prior_components = [row["component"] for row in previous["MAIN_LAUNCHER_components"]]
    need(len(prior_components) == len(set(prior_components)) == 45 and
         {row["package"] for row in previous["MAIN_LAUNCHER_components"]} == set(LAUNCHERS) and
         len(previous["installed_packages"]) == 205 and
         NEW_PACKAGE not in {row["package"] for row in previous["installed_packages"]},
         "EXACT_HISTORICAL_ROSTER_REQUIRED")
    need(failed.get("schema") == "pocket4-fixed-launcher-permission-raw-capture-v1" and
         failed.get("ok") is False and
         failed.get("errors") == [{"reason": "EXACT_ACTUAL45_NATIVE_COMPONENT_REFERENCE_CHANGED", "type": "RuntimeError"}] and
         failed.get("Android_namespace_commands") == 0 and failed.get("android_commands") == [] and
         failed.get("native_command_count") == 2 and
         failed.get("guard_before") == previous["guard_before"] and
         failed.get("native_catalog_comparison") == {
             "actual_framework_resolver_reference_job": "1a1b22e95d0-fc05-7cd4",
             "added_components": [NEW_COMPONENT], "expected_count": 45,
             "framework_resolver_requeried_by_this_worker": False,
             "missing_components": [], "observed_count": 46},
         "ORIGINAL_B03_FAILURE_MUST_REMAIN_EXACT")
    need(terminal.get("job_id") == "1a1b2eccc8a-fc05-8033" and
         terminal.get("state") == "failed" and terminal.get("exit_code") == 1 and
         all(terminal.get(k) is True for k in ("audit_recorded", "output_complete", "output_durable",
                                               "terminal_publication_confirmed")) and
         all(terminal.get(k) is False for k in ("automatic_retry", "cancelled", "timed_out")) and
         terminal.get("log_truncated") == {"stdout": False, "stderr": False} and
         terminal.get("log_synced") == {"stdout": True, "stderr": True} and
         terminal.get("log_errors") == {"stdout": None, "stderr": None} and
         terminal.get("log_bytes") == {"stdout": {"seen": 15781, "stored": 15781},
                                      "stderr": {"seen": 0, "stored": 0}},
         "EXACT_DURABLE_FAILED_B03_TERMINAL_REQUIRED")
    return previous


def discovery_comparison(installed, resolver, native, previous):
    """Full sets are compared before deciding whether this one-package question fits."""
    old_components = {row["component"] for row in previous["MAIN_LAUNCHER_components"]}
    current_components = {row["component"] for row in resolver}
    need(type(native.get("applications")) is list and len(native["applications"]) <= 4096,
         "DISCOVERY_NATIVE_CATALOG_BOUND")
    native_components = []
    for row in native["applications"]:
        need(type(row) is dict and type(row.get("component")) is str and type(row.get("package")) is str,
             "DISCOVERY_NATIVE_COMPONENT_SCHEMA")
        parsed = component(row["component"])
        need(parsed["package"] == row["package"], "DISCOVERY_NATIVE_COMPONENT_PACKAGE")
        native_components.append(parsed["component"])
    need(len(native_components) == len(set(native_components)), "DUPLICATE_NATIVE_DISCOVERY_COMPONENT")
    old_rows = {canonical(row) for row in previous["installed_packages"]}
    current_rows = {canonical(row) for row in installed}
    added_rows = [parse(raw) for raw in sorted(current_rows - old_rows)]
    missing_rows = [parse(raw) for raw in sorted(old_rows - current_rows)]
    new_rows = [row for row in installed if row["package"] == NEW_PACKAGE]
    expected_components = old_components | {NEW_COMPONENT}
    fits = (current_components == set(native_components) == expected_components and
            len(resolver) == len(native_components) == 46 and not missing_rows and
            len(new_rows) == len(added_rows) == 1 and added_rows == new_rows and
            len(new_rows[0]["uids"]) == 1 and 0 <= new_rows[0]["uids"][0] < 100000)
    return {"previous_resolver_reference": PRIOR["previous_pm"],
            "original_failure_reference": PRIOR["failed_capture"],
            "target_package": NEW_PACKAGE, "target_component": NEW_COMPONENT,
            "previous_component_count": len(old_components),
            "current_resolver_component_count": len(resolver),
            "current_native_component_count": len(native_components),
            "added_components": sorted(current_components - old_components),
            "missing_components": sorted(old_components - current_components),
            "framework_only_components": sorted(current_components - set(native_components)),
            "native_only_components": sorted(set(native_components) - current_components),
            "current_native_components": sorted(native_components),
            "PM_added_package_version_rows": added_rows,
            "PM_missing_package_version_rows": missing_rows,
            "PM_target_rows": new_rows,
            "matches_only_the_observed_new_component": fits,
            "native_count_alone_is_not_framework_resolver_proof": True,
            "does_not_prove_when_or_why_package_was_installed": True}


def safe_package_attributes(core, raw, package):
    root = core.A.parse_xml(raw)
    need(root.tag == "packages", "DISCOVERY_PACKAGES_ROOT")
    rows = [node for node in root.children if node.tag == "package" and node.attrs.get("name") == package]
    need(len(rows) == 1, "EXACT_NEW_PACKAGE_XML_ROW")
    allowed = ("name", "userId", "sharedUserId", "version", "versionCode", "codePath",
               "primaryCpuAbi", "secondaryCpuAbi", "nativeLibraryPath", "ft", "it", "ut",
               "firstInstallTime", "lastUpdateTime", "installer", "installerPackageName",
               "installerAttributionTag", "initiatingPackageName", "originatingPackageName", "packageSource")
    fields = {}
    for key in allowed:
        if key not in rows[0].attrs:
            fields[key] = {"status": "UNKNOWN", "reason": "ATTRIBUTE_ABSENT"}
            continue
        value = rows[0].attrs[key]
        need(type(value) in (str, int, bool) and
             (type(value) is not str or len(value.encode("utf-8")) <= 4096 and
              not any(ord(c) < 32 for c in value)), "BOUNDED_PUBLIC_PACKAGE_ATTRIBUTE")
        fields[key] = {"status": "OBSERVED_LITERAL_ATTRIBUTE", "value": value,
                       "python_type": type(value).__name__}
    return {"fields": fields, "timestamp_units_or_hex_not_inferred": True,
            "installer_value_is_not_authenticated_artifact_source": True,
            "raw_certificates_and_other_packages_not_exported": True}


def new_package_metadata(core, pool, held):
    path = "/data/system/packages.xml"
    raw, info = core.guest_read(pool, held.roots["android_init"], path, 2 * 1024 * 1024)
    row = core.package_rows(raw, [NEW_PACKAGE])[NEW_PACKAGE]
    attributes = safe_package_attributes(core, raw, NEW_PACKAGE)
    core.check_path(pool, held.roots["android_init"], path, info)
    return {"package_row": row, "safe_attributes": attributes,
            "source": {"path": path, "bytes": len(raw), "sha256": sha(raw), "file": info}}


def bind_new_package(core, pool, held, installed_row, deadline):
    """Compose frozen metadata/hash/identity primitives for this exact new package.

    Unlike the general core's 16 GiB limit, this one new package has a hard
    aggregate hash budget of 512 MiB, checked on each held FD before hashing.
    No APK or application data contents are returned or persisted.
    """
    held.verify()
    root = held.roots["android_init"]
    end, total = min(deadline - 5, time.monotonic() + 180), 0
    before = new_package_metadata(core, pool, held)
    row = before["package_row"]
    need(installed_row == {"package": NEW_PACKAGE, "version_code": row["version_code"], "uids": [row["uid"]]},
         "FRESH_PM_AND_NEW_PACKAGE_XML_IDENTITY_DIFFER")
    paths = core.apk_paths(pool, root, row["code_path"])
    apks = []
    for path in paths:
        fd = pool.own(core.H.open_in_root(root, path, os.O_RDONLY | os.O_NOFOLLOW))
        try:
            initial = core.metadata(fd)
            need(stat.S_ISREG(initial["st_mode"]) and initial["st_nlink"] == 1 and
                 0 < initial["st_size"] <= 512 * 1024 * 1024 - total and time.monotonic() < end,
                 "NEW_PACKAGE_512MIB_AGGREGATE_OR_TIME_BOUND")
            record = core.hash_fd(fd, 512 * 1024 * 1024 - total, end)
            need(record["file"] == initial, "NEW_APK_CHANGED_BEFORE_HASH")
            total += record["bytes"]
            apks.append({"path": path, **record})
        finally:
            pool.close(fd)
    dirs = {kind: core.directory_identity(pool, root, "/data/" + kind + "/0/" + NEW_PACKAGE)
            for kind in ("user", "user_de")}
    need(all(value["status"] == "ABSENT" or value["uid"] == row["uid"] for value in dirs.values()),
         "NEW_PACKAGE_DATA_DIRECTORY_UID_DIFFERS")
    identity = {NEW_PACKAGE: {**row, "apks": apks, "data_directories": dirs}}
    # This is the existing complete expected-identity contract; it checks APK
    # paths/stats, PM UID/version/signing digests and CE/DE top-level identities.
    core.app_scope(pool, held, [NEW_PACKAGE], identity, False)
    after = new_package_metadata(core, pool, held)
    need(after["package_row"] == before["package_row"] and
         after["safe_attributes"] == before["safe_attributes"], "NEW_PACKAGE_METADATA_CHANGED_DURING_BIND")
    held.verify()
    return identity, {"before": before, "after": after, "APK_hash_total_bytes": total,
                      "APK_hash_total_limit_bytes": 512 * 1024 * 1024, "APK_hash_seconds_limit": 180,
                      "raw_APK_saved": False, "data_business_content_reads": 0,
                      "fresh_signature_verification_performed": False}


def selected_dump_metadata(raw, package, uid, version_code):
    """Literal metadata inside exactly one attributed Package block only.

    Missing/ambiguous fields stay UNKNOWN. A PM versionName is labelled as a
    service observation; it is not an independently parsed APK manifest.
    Permissions, application usage, other users and business text are omitted.
    """
    keys = ("codePath", "versionCode", "versionName", "primaryCpuAbi", "secondaryCpuAbi",
            "firstInstallTime", "lastUpdateTime", "installerPackageName", "initiatingPackageName",
            "originatingPackageName", "packageSource")
    result = {"status": "UNKNOWN", "package": package, "user": 0, "UID": uid,
              "fields": {k: {"status": "UNKNOWN", "reason": "NO_ATTRIBUTED_PACKAGE_BLOCK"} for k in keys},
              "version_name_is_manifest_verified": False, "installer_is_authenticated_source": False,
              "permission_grants": "UNKNOWN_NOT_INTERPRETED", "shared_UID_membership_enumerated": False,
              "raw_dump_exported": False}
    need(type(raw) is bytes and 0 < len(raw) <= 262144, "NEW_DUMP_BOUND")
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeDecodeError:
        result["reason"] = "INVALID_UTF8"
        return result
    if any(c in text for c in ("\r", "\0", "\x0b", "\x0c", "\u0085", "\u2028", "\u2029")):
        result["reason"] = "UNRECOGNIZED_LINE_SEPARATORS"
        return result
    lines = text.split("\n")
    headers = [i for i, line in enumerate(lines) if line.startswith("  Package [" + package + "]")]
    if len(headers) != 1 or re.fullmatch(r"  Package \[" + re.escape(package) + r"\] \([0-9a-fA-F]+\):", lines[headers[0]]) is None:
        result["reason"] = "MISSING_DUPLICATE_OR_UNRECOGNIZED_TARGET_PACKAGE_HEADER"
        return result
    start = headers[0]
    end = next((i for i in range(start + 1, len(lines)) if lines[i] and not lines[i].startswith("    ")), len(lines))
    block = lines[start + 1:end]
    ids = [line for line in block if line.startswith("    appId=")]
    if ids != ["    appId=" + str(uid)]:
        result["reason"] = "PACKAGE_APPID_MISSING_DUPLICATE_OR_DIFFERENT"
        return result
    result["package_identity_matches_fresh_UID"] = True
    for key in keys:
        matches = [line for line in block if line.startswith("    " + key + "=")]
        if len(matches) != 1:
            result["fields"][key] = {"status": "UNKNOWN", "reason": "MISSING_FIELD" if not matches else "DUPLICATE_FIELD"}
            continue
        line = matches[0]
        literal = line[len("    " + key + "="):]
        if len(literal.encode("utf-8")) > 4096 or any(ord(c) < 32 for c in literal):
            result["fields"][key] = {"status": "UNKNOWN", "reason": "UNRECOGNIZED_BOUNDED_LITERAL"}
            continue
        field = {"status": "OBSERVED_LITERAL_PM_SERVICE_FIELD", "literal": literal,
                 "line_sha256": sha(line.encode("utf-8")), "normalization_applied": False}
        if key == "versionCode":
            matched = re.fullmatch(r"([0-9]+)(?: minSdk=[0-9]+ targetSdk=[0-9]+)?", literal)
            if matched is None:
                field = {"status": "UNKNOWN", "reason": "UNRECOGNIZED_VERSION_CODE_LINE", "line_sha256": sha(line.encode("utf-8"))}
            else:
                field["integer"] = int(matched[1])
                need(field["integer"] == version_code, "DUMP_AND_FRESH_PM_VERSION_CODE_DIFFER")
        result["fields"][key] = field
    result["status"] = "TARGET_PACKAGE_LITERAL_METADATA_OBSERVED_WITH_EXPLICIT_UNKNOWN_FIELDS"
    return result


def run(request):
    validate_request(request)
    previous = prior_observations()
    need(os.getuid() == os.geteuid() == 0, "EXISTING_HOST_ROOT_AUTHORITY_REQUIRED")
    guard = load_source(GUARD, "new_readonly_services_successor_guard")
    core = guard._core()
    transport_module = load_source(TRANSPORT, "new_independent_readonly_services_transport")
    native_helpers = load_source(NATIVE_HELPERS, "unchanged_native_identity_helpers_only")
    pool, leases = core.FDs(), core.FDs()
    held, target, directory, lock = None, None, None, None
    result = {"schema": "pocket4-native46-discovery-observation-v1", "ok": False, "errors": [],
              "automatic_retry": False, "production_ready": False, "UI_actions": 0, "App_launches": 0,
              "installs": 0, "permission_changes": 0, "lifecycle_commands": 0, "ADB_commands": 0,
              "business_data_content_reads": 0, "Android_namespace_commands": 0, "native_command_count": 0,
              "android_commands": [], "native_commands": [], "effective_permission_grants": "UNKNOWN",
              "packages": PACKAGES, "app_scope_reference": APP_SCOPE,
              "effective_AppOps_and_roles": "UNKNOWN_NOT_QUERIED", "old_Bili_unknown_reclassified": False,
              "compiled_Beike_scope_modified": False, "UI_or_install_admitted": False}
    result.update(original_b03_failure_preserved=True, original_permission_gate_modified=False,
                  new_scope_published=False, new_signature_verification_performed=False,
                  vendor_artifact_source_trust="UNKNOWN", permissions_interpreted=False,
                  prior_evidence=PRIOR, observed_started_unix_ns=time.time_ns(),
                  observed_started_monotonic_ns=time.monotonic_ns())
    new_identity = None
    deadline = time.monotonic() + 900
    root_identity, native_files, native_pins, location, scope = None, None, None, None, None

    def budget():
        need(time.monotonic() + 5 < deadline, "SERVICE_OBSERVATION_TOTAL_BUDGET")

    def write(name, raw):
        need(re.fullmatch(r"[A-Za-z0-9_.-]+", name) is not None, "NEW_PRIVATE_RECEIPT_NAME")
        current = core.open_host(pool, OUTPUT, os.O_PATH | os.O_DIRECTORY)
        try:
            observed = core.metadata(current)
            need(all(observed[key] == root_identity[key] for key in ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode")),
                 "OBSERVATION_OUTPUT_DIRECTORY_REPLACED")
        finally:
            pool.close(current)
        if type(raw) is bytes and raw == b"":
            pin = write_empty_raw_stream(core, pool, directory, root_identity, OUTPUT + "/" + name, raw)
        else:
            pin = core.write_new(OUTPUT + "/" + name, raw)
        need(core.pinned_record(pin, max(len(raw), 1)) == raw, "EXACT_OWNED_RECEIPT_READBACK")
        return pin

    def runtime_guard(action_attempted=False):
        budget()
        need(guard.current_guard() == result["guard_before"], "NEW_SERVICE_RUNTIME_CHANGED")
        core.verify_runtime(pool, held, baseline["runtime"])
        core.app_scope(pool, held, PACKAGES, scope["apps"], False)
        if new_identity is not None:
            core.app_scope(pool, held, [NEW_PACKAGE], new_identity, False)
        if target is not None:
            target.verify()
        read_root_pin(TRANSPORT)
        verify_shared_helper()

    def native_read(operation):
        need(operation in ("status", "applications"), "ONLY_NATIVE_READS")
        runtime_guard()
        native_helpers.recheck_native(core, pool, held, native_files, native_pins)
        argv = core.as_user([native_helpers.CLI_PATH, "--socket", native_helpers.SOCKET_PATH, "--json", operation])
        index = len(result["native_commands"]) + 1
        write("native-%02d.intent.json" % index, canonical({"argv": argv, "caller_uid": 1000, "automatic_retry": False})+b"\n")
        raw, stderr, row = core.bounded_child(argv, seconds=30, limit=262144)
        result["native_command_count"] += 1
        remember_child_streams(result["native_commands"],
                               {"operation": operation, "caller_uid": 1000, "command": row},
                               write, "native-%02d" % index, raw, stderr)
        value = core.native_running(raw, row)
        need(value["host_pid"] == owner, "ACTUAL_NATIVE_OWNER_CHANGED")
        native_helpers.recheck_native(core, pool, held, native_files, native_pins)
        runtime_guard()
        return value

    def record(kind, value):
        need(kind in ("intent", "command-result", "verified-result", "failure"), "EXACT_ORIGINAL_TRANSPORT_RECORD")
        write("transport-%02d.%s.json" % (value["sequence"], kind), canonical(value)+b"\n")

    def runner(argv, **options):
        need(set(options) == {"stdout", "stderr", "timeout", "env", "pass_fds", "close_fds"} and
             options["stdout"] == subprocess.PIPE and options["stderr"] == subprocess.PIPE and options["close_fds"] is True and
             options["env"] == transport_module.HOST_ENV and tuple(options["pass_fds"]) == (target.root_fd, *target.namespaces.values()),
             "ORIGINAL_HELD_RUNNER_PROTOCOL_REQUIRED")
        budget()
        index = len(result["android_commands"]) + 1
        write("android-%02d.intent.json" % index, canonical({"argv": list(argv), "authority_fds": list(options["pass_fds"]),
              "timeout_seconds": options["timeout"], "readonly": True, "automatic_retry": False})+b"\n")
        raw, stderr, row = held_bounded_child(argv, options["timeout"], 262144, tuple(options["pass_fds"]), options["env"])
        result["Android_namespace_commands"] += 1
        try:
            remember_child_streams(result["android_commands"], row, write, "android-%02d" % index, raw, stderr)
        finally:
            if not row["joined"]:
                target.poison_unjoined_command()
        write("android-%02d.result.json" % index, canonical(row)+b"\n")
        captured = subprocess.CompletedProcess(argv, row["returncode"], raw, stderr)
        captured.host_timed_out = row["termination_attempted"]
        captured.recorder_errors = row["errors"]
        captured.recorder_spawned = "host_pid" in row
        captured.recorder_joined = row["joined"]
        return captured

    try:
        core.create_private_root(OUTPUT)
        directory = core.open_host(pool, OUTPUT, os.O_RDONLY | os.O_DIRECTORY)
        root_identity = core.metadata(directory)
        flow = pool.own(os.open("flow.lock", os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=directory))
        try:
            os.fsync(flow)
        finally:
            pool.close(flow)
        os.fsync(directory)
        _, result["flow_lock_identity"] = core.acquire_lock(leases, OUTPUT + "/flow.lock")
        lock, result["action_lock_identity"] = core.acquire_lock(leases, core.ACTION_LOCK)
        result["guard_before"] = guard.current_guard()
        need(result["guard_before"].get("schema") == "pocket4-successor-main-guard-v1" and
             result["guard_before"]["runtime_epoch_sha256"] == EPOCH, "EXACT_TYPED_SUCCESSOR_REQUIRED")
        baseline = guard.current_baseline()
        expected = baseline["runtime"]["held"]["process_snapshot"]["binding"]
        held = core.HeldProcesses(pool, {key: row["host_pid"] for key, row in expected["processes"].items()})
        need(held.before["binding"] == expected, "ORIGINAL_EIGHT_ROLE_BINDING_REQUIRED")
        owner = expected["processes"]["launcher"]["host_pid"]
        scope = core.parse(core.pinned_record(APP_SCOPE))
        need(scope.get("schema") == "pocket4-versioned-app-scope-v1" and scope.get("runtime_epoch_sha256") == EPOCH and
             set(scope["apps"]) == set(PACKAGES), "ACTUAL_47_REFERENCE_REQUIRED")
        result["scope_guard_before"] = guard.check_app_scope(APP_SCOPE, PACKAGES)
        native_helpers.original_unknown(core)
        location = native_helpers.protected_location(core, pool, held, scope["apps"])
        native_files, native_pins = native_helpers.native_bind(core, pool, held)
        result["native_artifacts"] = native_pins
        result["request"] = write("request.json", canonical(request)+b"\n")
        runtime_guard()
        result["shared_namespace_helper_qualification"] = verify_shared_helper()
        expected_init = baseline["framework_epoch"]["binding"]["processes"]["init"]
        raw_init = held.extra["android_init"]["held_proc"]
        need(same_epoch_identity(raw_init, expected_init), "FRESH_INIT_DOES_NOT_MATCH_TYPED_EPOCH")
        target = core.H.HeldTarget(raw_init, HELPER_PATH, HELPER_SHA)
        values, classpaths, environment = main_classpaths(core.H, target, baseline["framework_epoch"], core.E, runtime_guard)
        need(values == baseline["runtime"]["classpath"]["values"], "ACTUAL_CLASSPATH_REFERENCE_CHANGED")
        result["classpath_binding"] = write("classpath-binding.private.json", canonical(classpaths)+b"\n")
        result["held_target"] = target.record
        result["native_before"] = native_read("status")
        native_catalog = native_read("applications")
        result["native_catalog"] = write("native-catalog.normalised.json", canonical(native_catalog)+b"\n")
        transport = transport_module.BoundArun(target=target, environment=environment, guard=runtime_guard, record=record,
                    epoch_sha256=baseline["framework_epoch"]["sha256"], init_pid=raw_init["pid"],
                    app_scope_sha256=APP_SCOPE["sha256"], user=0, runner=runner)
        raw_outputs = []
        for index, argv in enumerate(transport_module.READ_ONLY_COMMANDS[:5]):
            if index == 1:
                result["actual_package_help_admission"] = require_help_for_closed_queries(raw_outputs[0])
            raw = transport(list(argv), timeout=30)
            need(result["android_commands"][-1]["complete"] is True, "READONLY_COMMAND_NOT_COMPLETE_CLEANLY")
            raw_outputs.append(raw)
        installed_a, installed_b = parse_packages(raw_outputs[1]), parse_packages(raw_outputs[3])
        resolver_a, resolver_b = parse_resolver(raw_outputs[2]), parse_resolver(raw_outputs[4])
        need(installed_a == installed_b and resolver_a == resolver_b, "PM_OR_RESOLVER_CHANGED_BETWEEN_TWO_SAMPLES")
        result["installed_packages"] = installed_a
        result["MAIN_LAUNCHER_components"] = resolver_a
        result["catalog_comparison"] = compare_catalogs(installed_a, resolver_a, native_catalog, scope["apps"])
        result["discovery_comparison_before"] = discovery_comparison(installed_a, resolver_a, native_catalog, previous)
        need(result["discovery_comparison_before"]["matches_only_the_observed_new_component"],
             "CURRENT_COMPLETE_ROSTERS_DIFFER_FROM_THE_NARROW_DISCOVERY_QUESTION")
        new_identity, metadata_binding = bind_new_package(core, pool, held,
            result["discovery_comparison_before"]["PM_target_rows"][0], deadline)
        result["new_package_identity"] = new_identity[NEW_PACKAGE]
        result["new_package_metadata_binding"] = metadata_binding
        result["new_package_identity_receipt"] = write("new-package-identity.private.json", canonical(new_identity)+b"\n")
        runtime_guard()
        dump_raw = transport(list(transport_module.READ_ONLY_COMMANDS[5]), timeout=30)
        need(result["android_commands"][-1]["complete"] is True, "NEW_PACKAGE_DUMP_NOT_COMPLETE_CLEANLY")
        result["new_package_service_metadata"] = selected_dump_metadata(dump_raw, NEW_PACKAGE,
            new_identity[NEW_PACKAGE]["uid"], new_identity[NEW_PACKAGE]["version_code"])
        result["new_package_private_dump_reference"] = result["android_commands"][-1]["stdout"]
        native_catalog_after = native_read("applications")
        result["native_catalog_after"] = write("native-catalog-after.normalised.json", canonical(native_catalog_after)+b"\n")
        result["discovery_comparison_after"] = discovery_comparison(installed_b, resolver_b, native_catalog_after, previous)
        need(result["discovery_comparison_after"] == result["discovery_comparison_before"],
             "CURRENT_NATIVE_COMPONENTS_CHANGED_DURING_DISCOVERY")
        final_metadata = new_package_metadata(core, pool, held)
        need(final_metadata["package_row"] == metadata_binding["after"]["package_row"] and
             final_metadata["safe_attributes"] == metadata_binding["after"]["safe_attributes"],
             "NEW_PACKAGE_METADATA_CHANGED_AFTER_SERVICE_READ")
        result["new_package_metadata_final"] = final_metadata
        result["proposed_immutable_scope_review"] = {
            "original_packages": PACKAGES, "additional_package": NEW_PACKAGE,
            "proposed_packages": sorted((*PACKAGES, NEW_PACKAGE)), "proposed_count": 48,
            "original_scope_reference": APP_SCOPE, "new_identity_reference": result["new_package_identity_receipt"],
            "new_scope_published": False, "new_runtime_or_UI_authority": False,
            "requires_separate_exact_signed_APK_and_scope_review": True}
        result["help_results"] = {service: {"stdout": result["android_commands"][index]["stdout"], "returncode": 0}
                                  for index, service in enumerate(("package",))}
        result["native_after"] = native_read("status")
        runtime_guard()
        native_helpers.original_unknown(core)
        need(native_helpers.protected_location(core, pool, held, scope["apps"]) == location, "MEITUAN_SAVED_LOCATION_STATE_CHANGED")
        result["meituan_saved_location_unchanged"] = True
        result["scope_guard_after"] = guard.check_app_scope(APP_SCOPE, PACKAGES)
        result["guard_after"] = guard.current_guard()
        need(result["guard_after"] == result["guard_before"], "FINAL_TYPED_RUNTIME_CHANGED")
        for pin in (GUARD, APP_SCOPE, TRANSPORT, NATIVE_HELPERS, request["worker"], *PRIOR.values()):
            read_root_pin(pin)
        result.update(ok=True, new_package_identity_observed=True,
                      prior_sources_unchanged=True, observed_finished_unix_ns=time.time_ns(),
                      observed_finished_monotonic_ns=time.monotonic_ns(), current_scope_47_unchanged=True, PM_user0_installed_APK_packages_enumerated=True,
                      PM_query_includes_static_shared_and_SDK_libraries=True, PM_query_includes_uninstalled=False,
                      PM_query_includes_APEX=False, MAIN_LAUNCHER_resolver_queried=True,
                      all_installed_APK_bytes_bound=False, disabled_components_force_included=False,
                      enumeration_samples_equal=True, permission_queries_executed=False)
    except BaseException as error:
        result["errors"].append({"type": type(error).__name__, "reason": str(error)[:512]})
        details = getattr(error, "details", None)
        if type(details) is dict:
            result["transport_failure"] = details
    finally:
        if target is not None:
            try:
                target.close()
                result["held_namespace_target_closed"] = True
            except BaseException as error:
                result["errors"].append({"phase": "target_close", "type": type(error).__name__, "reason": str(error)[:256]})
        if lock is not None:
            try:
                fcntl.flock(lock, fcntl.LOCK_UN)
                result["action_lock_released"] = True
            except BaseException as error:
                result["errors"].append({"phase": "action_unlock", "type": type(error).__name__})
        for name, owned in (("observation", pool), ("lease", leases)):
            try:
                owned.close_all()
            except BaseException as error:
                result["errors"].append({"phase": name + "_FD_close", "type": type(error).__name__})
            result[name + "_FDs_final"] = owned.summary()
        result["owned_descriptors_final"] = result["observation_FDs_final"]
        if result["errors"]:
            result["ok"] = False
    result["status"] = "NATIVE46_AND_NEW_PACKAGE_IDENTITY_OBSERVED_NO_SCOPE_PROMOTION" if result["ok"] else "NATIVE46_DISCOVERY_INCOMPLETE_NO_RETRY"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--request-sha256", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    before = len(os.listdir("/proc/self/fd"))
    try:
        size = os.stat(args.request, follow_symlinks=False).st_size
        request = parse(read_root_pin({"path": args.request, "bytes": size, "sha256": args.request_sha256}))
        result = run(request)
    except BaseException as error:
        result = {"schema": "pocket4-readonly-service-entry-rejection-v1", "ok": False, "type": type(error).__name__,
                  "reason": str(error)[:512], "automatic_retry": False, "production_ready": False}
    after = len(os.listdir("/proc/self/fd"))
    result.update(process_FDs_before=before, process_FDs_after=after)
    if before != after:
        result["ok"] = False
        result.setdefault("errors", []).append({"reason": "ORIGINAL_WHOLE_PROCESS_FD_GATE_FAILED"})
    raw = canonical(result)
    need(len(raw) <= 524288, "SERVICE_ARTIFACT_BOUND")
    envelope = {"encoding": "zlib-base64", "artifact_bytes": len(raw), "artifact_sha256": sha(raw),
                "data": base64.b64encode(zlib.compress(raw, 9)).decode("ascii")}
    output = canonical(envelope)
    need(len(output) <= 98304, "SERVICE_STDOUT_BOUND")
    print(output.decode(), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
