#!/usr/bin/env python3
"""Read only the explicit original-eight + WeChat scope under the current guard.

No arguments, Android/native command, App-data content, permission change, or
install exists. The pinned original Reader/HISTORY are imported unchanged.
This observer adds one explicit metadata subject, hashes only WeChat's full
APK set, and holds its CE/DE directory identities without reading user content.
"""
import sys
sys.dont_write_bytecode = True
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import time
import types

BASE_PATH = "/home/alex/work/pocket4-launcher-upgrade-20261106-r1/source-airchina-bound-install-r1/collect_readonly.py"
BASE_SHA = "04dcc9337aa61ed663e3ce3dea8ab13a963c4826588fcd1c25554466ed30acd1"
BASE_BYTES = 48526
PACKAGE = "com.tencent.mm"
UID = 10114
VERSION = 3200
SIGNER = "0fe4ff85c215918396dadc7cd8ce6963339af33d37751a56e54c7206b63a3c7c"
ORIGINAL_EIGHT = ("com.Hyatt.hyt", "com.enflick.android.TextNow", "com.lianjia.beike",
    "com.rytong.airchina", "com.rytong.ceair", "com.sankuai.meituan.takeoutnew", "com.szzc", "tv.danmaku.bili")
READ_PACKAGES = ORIGINAL_EIGHT + (PACKAGE,)
MEITUAN = "com.sankuai.meituan.takeoutnew"
LOCK_PATH = "/run/lock/android-digitalis-actions.lock"
MAX_STDOUT = 128 * 1024


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def load_base():
    fd = os.open(BASE_PATH, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        a = os.fstat(fd)
        assert stat.S_ISREG(a.st_mode) and a.st_uid == 0 and a.st_nlink == 1 and a.st_size == BASE_BYTES
        raw = os.read(fd, BASE_BYTES + 1)
        assert len(raw) == BASE_BYTES and not os.read(fd, 1) and hashlib.sha256(raw).hexdigest() == BASE_SHA
        b = os.fstat(fd)
        assert all(getattr(a, k) == getattr(b, k) for k in ("st_dev", "st_ino", "st_mode", "st_nlink", "st_uid", "st_gid", "st_size", "st_mtime_ns", "st_ctime_ns"))
    finally:
        os.close(fd)
    c = types.ModuleType("pocket4_wechat_readonly_original_reader")
    c.__file__ = BASE_PATH
    exec(compile(raw, BASE_PATH, "exec"), c.__dict__)
    assert tuple(c.HISTORY) == ORIGINAL_EIGHT
    return c


def nine_package_projection(c, root):
    """Explicit fixed nine; original eight must equal the unchanged projection."""
    c.need(root.tag == "packages", "PACKAGES_ROOT_REQUIRED")
    certs, result = c.cert_digests(root), {}
    for node in root.children:
        package = node.attrs.get("name")
        if node.tag != "package" or package not in READ_PACKAGES:
            continue
        c.need(package not in result, "DUPLICATE_TARGET_PACKAGE")
        uid_keys = [key for key in ("userId", "sharedUserId") if key in node.attrs]
        c.need(len(uid_keys) == 1, "PACKAGE_UID_AMBIGUOUS_OR_MISSING")
        uid = c.integer(node.attrs[uid_keys[0]], "PACKAGE_UID_TYPE")
        c.need(10000 <= uid < 100000, "PACKAGE_USER_ZERO_APPID_BOUND")
        versions = [c.integer(node.attrs[key], "PACKAGE_VERSION_TYPE") for key in ("version", "versionCode") if key in node.attrs]
        c.need(versions and len(set(versions)) == 1 and 0 <= versions[0] < (1 << 63), "PACKAGE_VERSION_AMBIGUOUS_OR_MISSING")
        code_path = c.small_text(node.attrs.get("codePath"), "PACKAGE_CODE_PATH", 2048)
        c.path_parts(code_path)
        c.need(code_path.startswith("/data/app/"), "TARGET_CODE_PATH_OUTSIDE_DATA_APP")
        signing = [child for child in node.children if child.tag == "sigs"]
        c.need(len(signing) <= 1, "MULTIPLE_PACKAGE_SIGNATURE_RECORDS")
        signing_value = {"status": "UNKNOWN_NO_PACKAGE_MANAGER_RECORD", "certificate_sha256": [], "cryptographic_verification_performed": False}
        if signing:
            items = [child for child in signing[0].children if child.tag == "cert"]
            count = c.integer(signing[0].attrs.get("count"), "SIGNATURE_COUNT_TYPE")
            c.need(0 < count <= 32 and len(items) == count, "SIGNATURE_COUNT_MISMATCH")
            indices = [c.integer(item.attrs.get("index"), "SIGNATURE_INDEX_TYPE") for item in items]
            c.need(len(indices) == len(set(indices)), "DUPLICATE_PACKAGE_CERT_INDEX")
            if all(index in certs for index in indices):
                signing_value.update(status="PACKAGE_MANAGER_CERTIFICATE_DIGESTS_ONLY", certificate_sha256=sorted(certs[index] for index in indices))
        abi = {key: c.small_text(node.attrs[key], "PACKAGE_ABI_BOUND", 64) for key in ("primaryCpuAbi", "secondaryCpuAbi", "cpuAbiOverride") if key in node.attrs}
        result[package] = {"package": package, "metadata_present": True, "android_user": 0, "uid": uid, "version_code": versions[0], "code_path": code_path, "package_manager_abi": abi, "package_manager_signing": signing_value}
    c.need(set(result) == set(READ_PACKAGES), "ALL_NINE_EXPLICIT_PACKAGES_REQUIRED")
    c.need({k: result[k] for k in ORIGINAL_EIGHT} == c.package_projection(root), "UNCHANGED_ORIGINAL_EIGHT_PROJECTION_REQUIRED")
    return result


def nine_restrictions_projection(c, root):
    c.need(root.tag == "package-restrictions", "RESTRICTIONS_ROOT_REQUIRED")
    result = {}
    allowed = ("installed", "hidden", "suspended", "stopped", "enabled", "notLaunched")
    for node in root.children:
        package = node.attrs.get("name")
        if node.tag != "pkg" or package not in READ_PACKAGES:
            continue
        c.need(package not in result, "DUPLICATE_RESTRICTION_PACKAGE")
        values = {}
        for key in allowed:
            if key not in node.attrs:
                continue
            value = node.attrs[key]
            c.need(type(value) in (str, int, bool) and (type(value) is not str or len(value) <= 64), "RESTRICTION_VALUE_TYPE")
            values[key] = value
        result[package] = {"coverage": True, "recorded_fields": values, "absent_fields_not_defaulted": True}
    c.need({k: v for k, v in result.items() if k in ORIGINAL_EIGHT} == c.restrictions_projection(root), "UNCHANGED_ORIGINAL_EIGHT_RESTRICTIONS_REQUIRED")
    return result


def directory_identity(c, fd):
    row = c.metadata(fd)
    c.need(stat.S_ISDIR(row["st_mode"]) and row["st_uid"] == UID, "WECHAT_DATA_DIRECTORY_OWNER_DIFFERS")
    return {key.removeprefix("st_"): row[key] for key in ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode")}


def main():
    started = time.monotonic()
    result = {"schema": "pocket4-explicit-nine-wechat-before-readonly-v1", "started_utc": now(),
        "read_scope": list(READ_PACKAGES), "APK_hash_scope": [PACKAGE], "UI_actions": 0,
        "native_commands": 0, "Android_namespace_commands": 0, "App_launches": 0,
        "permission_changes": 0, "installs": 0, "App_data_content_reads": 0,
        "collector_file_writes": 0, "automatic_retry": False, "production_ready": False,
        "snapshot_consistent": False, "errors": []}
    c = fds = budget = guard = host = held = android = lock = None
    data = []
    try:
        assert len(sys.argv) == 1 and sys.platform.startswith("linux") and os.getuid() == os.geteuid() == 0
        c = load_base()
        fds, budget = c.Descriptors(), c.Budget()
        root_fd = fds.own(os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC))
        host = c.Reader(root_fd, fds, budget)
        lock = c.open_beneath(root_fd, LOCK_PATH, os.O_RDWR | os.O_NONBLOCK, fds)
        row = c.metadata(lock)
        c.need(stat.S_ISREG(row["st_mode"]) and row["st_nlink"] == 1 and row["st_uid"] == 0, "ORIGINAL_ROOT_ACTION_LOCK_REQUIRED")
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        host.observed[LOCK_PATH] = row
        _, result["reader_source"] = host.read(BASE_PATH, 65536, pin=BASE_SHA)
        _, result["observer_source"] = host.read(str(Path(__file__).resolve()), 65536)
        raw, result["guard_source"] = host.read(c.GUARD_PATH, 65536, pin=c.GUARD_SHA)
        guard = types.ModuleType("pocket4_wechat_readonly_pinned_guard")
        guard.__file__ = c.GUARD_PATH
        exec(compile(raw, c.GUARD_PATH, "exec"), guard.__dict__)
        result["guard_before"] = c.validate_guard_result(guard.current_guard())
        held = c.HeldAndroidRoot(guard.current_baseline(), fds, budget)
        unused_policy, unused_epoch, safe_root = guard.source_modules()
        android = c.Reader(held.root_fd, fds, budget)
        raw, source = android.read(c.PACKAGES_PATH, c.MAX_METADATA)
        result["metadata_sources"] = {"packages": source}
        projected = nine_package_projection(c, c.parse_xml(raw, budget.check))
        app = projected[PACKAGE]
        c.need(app["uid"] == UID and app["version_code"] == VERSION and app["package_manager_signing"]["certificate_sha256"] == [SIGNER], "WECHAT_CURRENT_REFERENCE_DIFFERS")
        result["target"] = app
        result["original_eight_current_identities"] = {k: projected[k] for k in ORIGINAL_EIGHT}
        result["original_eight_projection_equal"] = True
        names = android.directory(app["code_path"], lambda name: name.endswith(".apk"))
        c.need(0 < len(names) <= 64 and "base.apk" in names, "WECHAT_APK_SET_BOUND")
        result["APK_names"] = names
        result["APKs"] = [android.read(app["code_path"] + "/" + name, c.MAX_APK, apk=True)[1] for name in names]
        for path in ("/data/user/0/" + PACKAGE, "/data/user_de/0/" + PACKAGE):
            fd = fds.own(safe_root.open_in_root(held.root_fd, path, os.O_PATH | os.O_DIRECTORY))
            data.append({"path": path, "fd": fd, "identity": directory_identity(c, fd)})
        raw, source = android.read(c.RESTRICTIONS_PATH, c.MAX_METADATA)
        result["metadata_sources"]["restrictions"] = source
        result["restrictions"] = nine_restrictions_projection(c, c.parse_xml(raw, budget.check)).get(PACKAGE, {"coverage": False, "recorded_fields": {}, "absent_fields_not_defaulted": True})
        result["permission_observations"], result["meituan_location_saved_observations"], sources = [], [], []
        for path in c.PERMISSION_PATHS:
            observed = android.optional(path, c.MAX_METADATA)
            if observed is None:
                sources.append({"path": path, "status": "ABSENT"})
                continue
            raw, source = observed
            node = c.parse_xml(raw, budget.check)
            sources.append(source)
            result["permission_observations"].append({"source": path, **c.permission_projection(node, PACKAGE, UID)})
            other = c.permission_projection(node, MEITUAN, projected[MEITUAN]["uid"])
            result["meituan_location_saved_observations"].append({"source": path, "coverage": other["coverage"], "effective_grant_state": "UNKNOWN", "entries": [x for x in other["entries"] if x["name"] in c.LOCATION_PERMISSIONS]})
        result["metadata_sources"]["permissions"] = sources
        result["effective_permission_state"] = "UNKNOWN_SAVED_SOURCES_NOT_LIVE_AUTHORITY"
        for row in data:
            c.need(directory_identity(c, row["fd"]) == row["identity"], "HELD_WECHAT_DATA_DIRECTORY_CHANGED")
            current = fds.own(safe_root.open_in_root(held.root_fd, row["path"], os.O_PATH | os.O_DIRECTORY))
            try:
                c.need(directory_identity(c, current) == row["identity"], "WECHAT_DATA_PATH_CHANGED")
            finally:
                fds.close(current)
        result["data_directories"] = [{k: row[k] for k in ("path", "identity")} for row in data]
        held.verify()
        android.recheck()
        host.recheck()
        result["guard_after"] = c.validate_guard_result(guard.current_guard())
        c.need(result["guard_after"] == result["guard_before"], "CURRENT_GUARD_CHANGED")
        result["snapshot_consistent"] = True
    except BaseException as error:
        result["errors"].append({"type": type(error).__name__, "message": str(error)[:256]})
    finally:
        if lock is not None:
            try:
                fcntl.flock(lock, fcntl.LOCK_UN)
                result["action_lock_released"] = True
            except BaseException as error:
                result["errors"].append({"stage": "unlock", "type": type(error).__name__})
        if fds is not None:
            for fd in tuple(fds.live):
                try:
                    fds.close(fd)
                except BaseException as error:
                    result["errors"].append({"stage": "close", "type": type(error).__name__})
            result["owned_descriptors_final"] = fds.report()
        result["ended_utc"] = now()
        result["elapsed_seconds"] = round(time.monotonic() - started, 6)
        result["snapshot_consistent"] = bool(result["snapshot_consistent"] and not result["errors"])
        result["status"] = "READONLY_SNAPSHOT_VERIFIED" if result["snapshot_consistent"] else "READONLY_REJECTED"
        raw = json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False)
        assert len(raw.encode("ascii")) <= MAX_STDOUT
        print(raw, flush=True)
    return 0 if result["snapshot_consistent"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
