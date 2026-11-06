#!/usr/bin/env python3
"""Owned native-cell recovery; default preflight. See README for scope/inputs.

Only explicit execute-native-cell-restart requests one lifecycle operation.
Runtime guards never discover replacements. No Android entry or UI operation.
"""
import argparse
import fcntl
import hashlib
import json
import os
import re
import select
import selectors
import signal
import stat
import subprocess
import sys
import time
import types

sys.dont_write_bytecode = True
SOURCE_NAMES = {"successor_runtime.py", "framework_epoch.py", "held_runtime_r5.py", "readonly_abx.py", "resume_successor_qualification.py", "observe_successor_scope.py"}
FROZEN = {
    "framework_epoch.py": (8658, "f43f766f19a151d7d33ecd0c99c2e81f832fce7dcb1804e5c774e833066a6288"),
    "held_runtime_r5.py": (22691, "72cf33399ca3c280fc0c9288669f7d6c13d387e41b5fb930cf477f2b940f16b4"),
    "readonly_abx.py": (48526, "04dcc9337aa61ed663e3ce3dea8ab13a963c4826588fcd1c25554466ed30acd1"),
}
ROLE_NAMES = ("daemon", "launcher", "android_init", "presenter", "surfaceflinger", "zygote64", "system_server", "composer")
RETIRED = ("launcher", "android_init", "surfaceflinger", "zygote64", "system_server", "composer")
COMPOSER_EXE = "/vendor/bin/hw/android.hardware.graphics.composer3-service.droidloom"
ACTION_LOCK = "/run/lock/android-digitalis-actions.lock"
UNKNOWN_FLOW = "/home/alex/work/pocket4-bilibili-owned-qa-r9-flow-474d7477074ea01fbc986e0d867924c1"
CONFIG = "/etc/droidloom/cell.json"
CGROUP = "/system.slice/droidloomd.service"
ENGINE = "/system/lib64/libberberis_arm64.so"
LIMIT_NAMES = ("cpu.max", "memory.high", "memory.max", "memory.swap.max", "pids.max")
STAT_NAMES = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")
SERVICE_PROPERTIES = ("MainPID", "ControlGroup", "InvocationID", "ActiveState", "SubState", "NRestarts", "ExecMainStartTimestampMonotonic")
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C", "TZ": "UTC", "SYSTEMD_PAGER": "", "SYSTEMD_COLORS": "0"}
E = H = A = None


class Rejected(RuntimeError):
    pass


def need(condition, code):
    if not condition:
        raise Rejected(code)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def parse(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    def invalid(_):
        raise Rejected("NONFINITE_JSON_NUMBER")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=invalid)


def safe_error(error):
    result = {"type": type(error).__name__}
    if isinstance(error, OSError):
        result["errno"] = error.errno
    elif isinstance(error, Rejected) and re.fullmatch(r"[A-Z0-9_]{1,96}", str(error)):
        result["code"] = str(error)
    else:
        result["code"] = "UNEXPECTED_FAILURE_DETAILS_RETAINED_PRIVATELY"
    return result


def sha_value(value):
    return type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def metadata(fd):
    value = os.fstat(fd)
    return {key: getattr(value, key) for key in STAT_NAMES}


def path_parts(path):
    need(type(path) is str and path.startswith("/") and not path.startswith("//") and
         "\0" not in path and len(path.encode()) <= 4096 and
         all(part not in ("", ".", "..") for part in path[1:].split("/")), "CANONICAL_ABSOLUTE_PATH_REQUIRED")
    return path[1:].split("/")


class FDs:
    def __init__(self):
        self.active = set()
        self.acquired = self.closed = 0
        self.errors = []

    def own(self, fd):
        need(fd >= 3 and fd not in self.active, "UNIQUE_NONSTANDARD_FD_REQUIRED")
        self.active.add(fd)
        self.acquired += 1
        need(len(self.active) <= 160, "DESCRIPTOR_BOUND")
        return fd

    def close(self, fd):
        need(fd in self.active, "UNOWNED_DESCRIPTOR_CLOSE")
        self.active.remove(fd)
        try:
            os.close(fd)
            self.closed += 1
        except BaseException as error:
            self.errors.append(safe_error(error))
            raise

    def close_all(self):
        for fd in reversed(tuple(self.active)):
            try:
                self.close(fd)
            except BaseException:
                pass
        need(not self.errors and not self.active and self.closed == self.acquired, "DESCRIPTOR_RETIREMENT_FAILED")

    def summary(self):
        return {"acquired": self.acquired, "closed": self.closed, "remaining": len(self.active), "errors": self.errors}


def open_host(pool, path, flags=os.O_RDONLY, mode=0o400):
    parts = path_parts(path)
    parents = []
    try:
        parent = pool.own(os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC))
        parents.append(parent)
        for name in parts[:-1]:
            parent = pool.own(os.open(name, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent))
            parents.append(parent)
        return pool.own(os.open(parts[-1], flags | os.O_NOFOLLOW | os.O_CLOEXEC, mode, dir_fd=parent))
    finally:
        for fd in reversed(parents):
            pool.close(fd)


def read_fd(fd, limit, end, regular=False):
    before = metadata(fd)
    if regular:
        need(stat.S_ISREG(before["st_mode"]) and before["st_nlink"] == 1 and
             0 <= before["st_size"] <= limit, "BOUNDED_REGULAR_FILE_REQUIRED")
    chunks, count = [], 0
    while True:
        need(time.monotonic() < end, "BOUNDED_READ_DEADLINE")
        block = os.read(fd, min(65536, limit + 1 - count))
        if not block:
            break
        count += len(block)
        need(count <= limit, "BOUNDED_READ_SIZE")
        chunks.append(block)
    raw = b"".join(chunks)
    if regular:
        need(len(raw) == before["st_size"] and metadata(fd) == before, "REGULAR_FILE_CHANGED")
    return raw


def host_read(path, limit, pin=None, size=None):
    pool = FDs()
    try:
        fd = open_host(pool, path)
        before = metadata(fd)
        raw = read_fd(fd, limit, time.monotonic() + 5, True)
        again = open_host(pool, path)
        need(metadata(again) == before, "HOST_PATH_REPLACED")
        need(pin is None or digest(raw) == pin, "HOST_CONTENT_PIN_DIFFERS")
        need(size is None or len(raw) == size, "HOST_BYTE_COUNT_DIFFERS")
        return raw, before
    finally:
        pool.close_all()


def pinned_record(record, limit=4 * 1024 * 1024):
    need(type(record) is dict and set(record) <= {"path", "sha256", "bytes"} and
         {"path", "sha256"} <= set(record) and sha_value(record["sha256"]), "CONTENT_REFERENCE_REQUIRED")
    return host_read(record["path"], limit, record["sha256"], record.get("bytes"))[0]


def unknown_evidence(plan):
    for pin in plan["unknown_evidence"]:
        pinned_record(pin)
    need(not any(os.path.lexists(UNKNOWN_FLOW + path) for path in
                 ("/launch-scope.json", "/reconciliations/launch-01.json")), "UNKNOWN_LAUNCH_AUTHORITY_CHANGED")


def load_module(raw, name, path):
    module = types.ModuleType(name)
    module.__file__ = path
    exec(compile(raw, path, "exec"), module.__dict__)
    return module


def configure(source_dir, manifest_sha):
    global E, H, A
    manifest_raw, _ = host_read(source_dir + "/SOURCE_PINS.json", 65536, manifest_sha)
    manifest = parse(manifest_raw)
    need(set(manifest) == {"schema", "files"} and manifest["schema"] == "pocket4-successor-source-v1" and
         set(manifest["files"]) == SOURCE_NAMES, "EXACT_SUCCESSOR_SOURCE_CLOSURE_REQUIRED")
    encoded = {}
    for name, pin in manifest["files"].items():
        need(set(pin) == {"bytes", "sha256"}, "SOURCE_PIN_SCHEMA")
        raw, _ = host_read(source_dir + "/" + name, 65536, pin["sha256"], pin["bytes"])
        if name in FROZEN:
            need((len(raw), digest(raw)) == FROZEN[name], "FROZEN_READER_SOURCE_CHANGED")
        encoded[name] = raw
    E = load_module(encoded["framework_epoch.py"], "successor_frozen_epoch", source_dir + "/framework_epoch.py")
    H = load_module(encoded["held_runtime_r5.py"], "successor_frozen_reader", source_dir + "/held_runtime_r5.py")
    A = load_module(encoded["readonly_abx.py"], "successor_frozen_abx", source_dir + "/readonly_abx.py")
    encoded["SOURCE_PINS.json"] = manifest_raw
    return encoded


def host_pseudo(path, limit=8192):
    pool = FDs()
    try:
        return read_fd(open_host(pool, path), limit, time.monotonic() + 3)
    finally:
        pool.close_all()


def boot_id():
    return host_pseudo("/proc/sys/kernel/random/boot_id", 128).decode("ascii").strip()


def pidfd_dead(fd):
    poll = select.poll()
    poll.register(fd, select.POLLIN | select.POLLHUP | select.POLLERR)
    events = poll.poll(0)
    need(all(not mask & (select.POLLNVAL | select.POLLERR) for _, mask in events), "INVALID_PIDFD")
    return bool(events)


class HeldProcesses:
    def __init__(self, pool, roles):
        need(set(roles) == set(ROLE_NAMES) and len(set(roles.values())) == 8, "EIGHT_DISTINCT_ROLES_REQUIRED")
        self.pool, self.roles = pool, dict(roles)
        self.views_released = False
        self.pidfds, self.procs, self.roots, self.exes = {}, {}, {}, {}
        self.before = E.capture_processes(roles)
        self.extra = {}
        for role, pid in roles.items():
            self.pidfds[role] = pool.own(os.pidfd_open(pid, 0))
            proc = pool.own(os.open("/proc/" + str(pid), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC))
            self.procs[role] = proc
            self.roots[role] = pool.own(os.open("root", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=proc))
            self.exes[role] = pool.own(os.open("exe", os.O_RDONLY | os.O_CLOEXEC, dir_fd=proc))
            self.extra[role] = self.extra_identity(role)
        self.verify()

    def extra_identity(self, role):
        proc = self.procs[role]
        namespaces = {name: os.readlink("ns/" + name, dir_fd=proc) for name in (*H.NS_TYPES, "user")}
        root = os.fstat(self.roots[role])
        return {"root": {"device": root.st_dev, "inode": root.st_ino}, "namespaces": namespaces,
                "executable_file": metadata(self.exes[role]),
                "held_proc": H.proc_identity_at(proc, self.roles[role], time.monotonic() + 3)}

    def verify(self):
        need(not self.views_released, "PROCESS_VIEWS_ALREADY_RETIRED")
        for role, fd in self.pidfds.items():
            need(not pidfd_dead(fd), "HELD_ROLE_DIED")
            need(self.extra_identity(role) == self.extra[role], "HELD_ROLE_EXTRA_IDENTITY_CHANGED")
            check = self.pool.own(os.open("root", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=self.procs[role]))
            try:
                now = os.fstat(check)
                need({"device": now.st_dev, "inode": now.st_ino} == self.extra[role]["root"], "HELD_ROOT_PATH_CHANGED")
            finally:
                self.pool.close(check)
            check = self.pool.own(os.open("exe", os.O_RDONLY | os.O_CLOEXEC, dir_fd=self.procs[role]))
            try:
                need(metadata(check) == self.extra[role]["executable_file"], "HELD_EXECUTABLE_PATH_CHANGED")
            finally:
                self.pool.close(check)
        current = E.capture_processes(self.roles)
        need(current["binding"] == self.before["binding"], "FULL_HELD_IDENTITIES_CHANGED")
        return current

    def capture(self):
        snapshot = self.verify()
        return {"process_snapshot": snapshot, "extra": self.extra}

    def release_views_keep_pidfds(self):
        self.verify()
        for group in (self.exes, self.roots, self.procs):
            for fd in group.values():
                self.pool.close(fd)
        self.views_released = True
        need(E.capture_processes(self.roles)["binding"] == self.before["binding"] and
             all(not pidfd_dead(fd) for fd in self.pidfds.values()), "PRE_TRANSITION_PROCESS_IDENTITY_CHANGED")


def hash_fd(fd, limit, end):
    before = metadata(fd)
    need(stat.S_ISREG(before["st_mode"]) and before["st_nlink"] == 1 and
         0 < before["st_size"] <= limit, "ARTIFACT_BYTE_OR_SHAPE_BOUND")
    os.lseek(fd, 0, os.SEEK_SET)
    count, result = 0, hashlib.sha256()
    while True:
        need(time.monotonic() < end, "ARTIFACT_HASH_DEADLINE")
        block = os.read(fd, min(131072, before["st_size"] + 1 - count))
        if not block:
            break
        count += len(block)
        need(count <= before["st_size"], "ARTIFACT_GREW")
        result.update(block)
    need(count == before["st_size"] and metadata(fd) == before, "ARTIFACT_CHANGED_DURING_HASH")
    return {"bytes": count, "sha256": result.hexdigest(), "file": before}


def guest_read(pool, root, path, limit):
    fd = pool.own(H.open_in_root(root, path, os.O_RDONLY | os.O_NOFOLLOW))
    try:
        before = metadata(fd)
        raw = read_fd(fd, limit, time.monotonic() + 5, True)
        return raw, before
    finally:
        pool.close(fd)


def check_path(pool, root, path, expected):
    fd = pool.own(H.open_in_root(root, path, os.O_RDONLY | os.O_NOFOLLOW))
    try:
        need(metadata(fd) == expected, "OBSERVED_ARTIFACT_PATH_REPLACED")
    finally:
        pool.close(fd)


def classpaths(pool, held, hash_contents=True, expected=None):
    end = time.monotonic() + 45
    values = H.selected_classpaths(H.read_at(held.procs["zygote64"], "environ", H.ENV_LIMIT, end))
    paths = list(dict.fromkeys(path for key in H.REQUIRED_CLASSPATHS for path in values[key].split(":")))
    need(0 < len(paths) <= 256, "CLASSPATH_COUNT_BOUND")
    if expected is not None:
        need(values == expected["values"] and paths == [row["path"] for row in expected["files"]], "CLASSPATH_SET_CHANGED")
    files, total = [], 0
    for index, path in enumerate(paths):
        a = b = None
        try:
            a = pool.own(H.open_in_root(held.roots["android_init"], path))
            b = pool.own(H.open_in_root(held.roots["zygote64"], path))
            left, right = metadata(a), metadata(b)
            need(all(stat.S_ISREG(m["st_mode"]) and m["st_nlink"] == 1 and 0 < m["st_size"] <= H.FILE_LIMIT
                     for m in (left, right)), "CLASSPATH_FILE_BOUND")
            need(tuple(left[k] for k in ("st_dev", "st_ino", "st_size")) ==
                 tuple(right[k] for k in ("st_dev", "st_ino", "st_size")), "CLASSPATH_DUAL_ROOT_BACKING_DIFFERS")
            total += left["st_size"]
            need(total <= H.TOTAL_FILE_LIMIT and time.monotonic() < end, "CLASSPATH_TOTAL_OR_TIME_BOUND")
            if hash_contents:
                hashed = hash_fd(a, H.FILE_LIMIT, end)
                row = {"path": path, "bytes": hashed["bytes"], "sha256": hashed["sha256"], "init_view": left, "zygote_view": right}
            else:
                need(expected is not None and left == expected["files"][index]["init_view"] and
                     right == expected["files"][index]["zygote_view"], "CLASSPATH_FILE_IDENTITY_CHANGED")
                row = expected["files"][index]
            need(metadata(a) == left and metadata(b) == right, "CLASSPATH_CHANGED_DURING_READ")
            files.append(row)
        finally:
            if b is not None:
                pool.close(b)
            if a is not None:
                pool.close(a)
    need(H.selected_classpaths(H.read_at(held.procs["zygote64"], "environ", H.ENV_LIMIT, end)) == values,
         "CLASSPATH_ENVIRONMENT_CHANGED")
    return {"values": values, "files": files, "total_bytes": total, "paired_complete": True}


def classpath_bytes(value):
    return {"values": value["values"], "files": [{k: row[k] for k in ("path", "bytes", "sha256")} for row in value["files"]]}


def package_rows(raw, targets):
    root = A.parse_xml(raw)
    need(root.tag == "packages", "PACKAGES_ROOT_REQUIRED")
    certificates, rows = A.cert_digests(root), {}
    for node in root.children:
        name = node.attrs.get("name")
        if node.tag != "package" or name not in targets:
            continue
        need(name not in rows, "DUPLICATE_TARGET_PACKAGE")
        ids = [A.integer(node.attrs[key], "PACKAGE_UID") for key in ("userId", "sharedUserId") if key in node.attrs]
        versions = [A.integer(node.attrs[key], "PACKAGE_VERSION") for key in ("version", "versionCode") if key in node.attrs]
        need(len(ids) == 1 and 0 <= ids[0] < 100000 and versions and len(set(versions)) == 1, "PACKAGE_IDENTITY_FIELDS")
        code = node.attrs.get("codePath")
        path_parts(code)
        need(any(code.startswith(prefix) for prefix in ("/data/app/", "/system/", "/system_ext/", "/product/", "/vendor/", "/apex/")), "PACKAGE_CODE_ROOT")
        sigs = [child for child in node.children if child.tag == "sigs"]
        need(len(sigs) <= 1, "DUPLICATE_SIGNING_RECORD")
        digests = []
        if sigs:
            certs = [child for child in sigs[0].children if child.tag == "cert"]
            need(len(certs) == A.integer(sigs[0].attrs.get("count"), "CERT_COUNT") and 0 < len(certs) <= 32, "SIGNING_CERT_COUNT")
            indices = [A.integer(cert.attrs.get("index"), "CERT_INDEX") for cert in certs]
            need(len(set(indices)) == len(indices) and all(index in certificates for index in indices), "SIGNING_CERT_INDEX_MISSING")
            digests = sorted(certificates[index] for index in indices)
        rows[name] = {"package": name, "uid": ids[0], "version_code": versions[0], "code_path": code,
                      "package_manager_certificate_sha256": digests, "fresh_signature_verification": False}
    need(set(rows) == set(targets), "TARGET_PACKAGE_MISSING")
    return rows


def directory_identity(pool, root, path):
    try:
        fd = pool.own(H.open_in_root(root, path, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW))
    except FileNotFoundError:
        return {"status": "ABSENT"}
    try:
        value = os.fstat(fd)
        need(stat.S_ISDIR(value.st_mode), "APP_DATA_DIRECTORY_SHAPE")
        return {"status": "PRESENT", "device": value.st_dev, "inode": value.st_ino, "uid": value.st_uid, "gid": value.st_gid}
    finally:
        pool.close(fd)


def apk_paths(pool, root, code):
    fd = pool.own(H.open_in_root(root, code, os.O_RDONLY | os.O_NOFOLLOW))
    try:
        value = os.fstat(fd)
        if stat.S_ISREG(value.st_mode):
            need(code.endswith(".apk"), "PACKAGE_CODE_FILE_EXTENSION")
            return [code]
        need(stat.S_ISDIR(value.st_mode), "PACKAGE_CODE_PATH_SHAPE")
        names = os.listdir(fd)
        need(len(names) <= 256, "PACKAGE_DIRECTORY_ENTRY_BOUND")
        apks = sorted(name for name in names if name.endswith(".apk"))
        need(0 < len(apks) <= 32 and all(re.fullmatch(r"[A-Za-z0-9_.-]+\.apk", name) for name in apks), "APK_SET_BOUND")
        return [code + "/" + name for name in apks]
    finally:
        pool.close(fd)


def app_scope(pool, held, targets, expected=None, hash_contents=True):
    """APK identities + top-level data inode ownership only; no business data."""
    held.verify()
    root, end, total = held.roots["android_init"], time.monotonic() + 180, 0
    raw, _ = guest_read(pool, root, "/data/system/packages.xml", 2 * 1024 * 1024)
    rows = package_rows(raw, targets)
    del raw
    result = {}
    for name in sorted(targets):
        row = rows[name]
        paths = apk_paths(pool, root, row["code_path"])
        apks = []
        for path in paths:
            fd = pool.own(H.open_in_root(root, path, os.O_RDONLY | os.O_NOFOLLOW))
            try:
                if hash_contents:
                    record = hash_fd(fd, 512 * 1024 * 1024, end)
                else:
                    need(expected is not None and name in expected, "PINNED_APP_SCOPE_REQUIRED")
                    candidates = [entry for entry in expected[name]["apks"] if entry["path"] == path]
                    need(len(candidates) == 1 and metadata(fd) == candidates[0]["file"], "APP_APK_FILE_CHANGED")
                    record = {key: candidates[0][key] for key in ("bytes", "sha256", "file")}
                total += record["bytes"]
                need(total <= 16 * 1024 * 1024 * 1024 and time.monotonic() < end, "ALL_APK_TOTAL_OR_TIME_BOUND")
                apks.append({"path": path, **record})
            finally:
                pool.close(fd)
        dirs = {kind: directory_identity(pool, root, "/data/" + kind + "/0/" + name) for kind in ("user", "user_de")}
        for value in dirs.values():
            need(value["status"] == "ABSENT" or value["uid"] == row["uid"], "APP_DATA_UID_DIFFERS")
        result[name] = {**row, "apks": apks, "data_directories": dirs}
        need(apk_paths(pool, root, row["code_path"]) == paths, "APK_DIRECTORY_SET_CHANGED")
        for record in apks:
            check_path(pool, root, record["path"], record["file"])
        need({kind: directory_identity(pool, root, "/data/" + kind + "/0/" + name) for kind in dirs} == dirs, "APP_DATA_PATH_CHANGED")
    raw, _ = guest_read(pool, root, "/data/system/packages.xml", 2 * 1024 * 1024)
    need(package_rows(raw, targets) == rows, "TARGET_PACKAGE_METADATA_CHANGED")
    held.verify()
    if expected is not None and not hash_contents:
        need(result == expected, "PINNED_APP_SCOPE_CHANGED")
    return result


def app_bytes(value):
    return {name: {**{key: row[key] for key in ("package", "uid", "version_code", "code_path", "package_manager_certificate_sha256", "data_directories")},
                   "apks": [{key: apk[key] for key in ("path", "bytes", "sha256")} for apk in row["apks"]]}
            for name, row in value.items()}


def bounded_child(argv, seconds=5, limit=65536):
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
                                 cwd="/", env=ENV, close_fds=True, start_new_session=True)
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


def as_user(argv):
    return ["/usr/bin/sudo", "-n", "-u", "#1000", "--", "/usr/bin/env", "XDG_RUNTIME_DIR=/run/user/1000",
            "DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus", *argv]


def native_argv(operation):
    need(operation in ("status", "restart", "help"), "CLOSED_NATIVE_OPERATION_SET")
    arguments = ["/usr/bin/droidloomctl", "--cell", "--json"]
    if operation == "help":
        return as_user(arguments + ["--help"])
    arguments.append(operation)
    if operation == "restart":
        arguments += ["--spec", CONFIG]
    return as_user(arguments)


def native_running(raw, command):
    need(command.get("complete") is True and command.get("joined") is True and command.get("returncode") == 0,
         "NATIVE_CLIENT_NOT_JOINED_SUCCESSFULLY")
    value = parse(raw)
    need(type(value) is dict and value.get("ok") is True and value.get("state") == "running" and
         type(value.get("host_pid")) is int and value["host_pid"] > 1 and not value.get("outcome_unknown", False),
         "ACTUAL_NATIVE_RUNNING_RECEIPT_REQUIRED")
    return value


def service(user=False):
    argv = ["/usr/bin/systemctl"] + (["--user"] if user else [])
    argv += ["show", "droidloom.service" if user else "droidloomd.service", "--no-pager"]
    argv += ["--property=" + name for name in SERVICE_PROPERTIES]
    raw, _, command = bounded_child(as_user(argv) if user else argv)
    need(command["complete"], "SERVICE_QUERY_FAILED")
    rows = raw.decode("ascii").splitlines()
    need(len(rows) == len(SERVICE_PROPERTIES) and all("=" in row for row in rows), "SERVICE_PROPERTIES_SHAPE")
    values = dict(row.split("=", 1) for row in rows)
    need(set(values) == set(SERVICE_PROPERTIES) and values["MainPID"].isdigit() and int(values["MainPID"]) > 1 and
         values["ActiveState"] == "active" and values["SubState"] == "running" and
         re.fullmatch(r"[0-9a-f]{32}", values["InvocationID"]), "SERVICE_RUNNING_IDENTITY_REQUIRED")
    return values


def limits():
    return {name: host_pseudo("/sys/fs/cgroup" + CGROUP + "/" + name).decode("ascii").strip() for name in LIMIT_NAMES}


def cgroup_member(pid):
    try:
        value = host_pseudo("/proc/" + str(pid) + "/cgroup").decode("ascii").splitlines()
        return len(value) == 1 and (value[0] == "0::" + CGROUP or value[0].startswith("0::" + CGROUP + "/"))
    except (FileNotFoundError, ProcessLookupError):
        return False


def role_candidates(init_pid=None):
    """Filter cgroup before reading executable/argv."""
    end = time.monotonic() + 5
    names = os.listdir("/proc")
    need(len(names) <= 65536, "PROC_DISCOVERY_COUNT_BOUND")
    output = {key: [] for key in ("android_init", "zygote64", "system_server", "surfaceflinger", "composer")}
    ns = None if init_pid is None else os.readlink("/proc/" + str(init_pid) + "/ns/pid")
    for name in names:
        need(time.monotonic() < end, "PROC_DISCOVERY_DEADLINE")
        if not name.isdecimal() or not cgroup_member(int(name)):
            continue
        try:
            base = "/proc/" + name
            exe = os.readlink(base + "/exe")
            if ns is not None and os.readlink(base + "/ns/pid") != ns:
                continue
            if exe == "/system/bin/init":
                output["android_init"].append(int(name))
            elif exe == "/system/bin/surfaceflinger":
                output["surfaceflinger"].append(int(name))
            elif exe == COMPOSER_EXE:
                output["composer"].append(int(name))
            elif exe == "/system/bin/app_process64":
                argv = host_pseudo(base + "/cmdline", 8192).split(b"\0")
                if argv == [b"zygote64", b""]:
                    output["zygote64"].append(int(name))
                elif argv == [b"system_server", b""]:
                    output["system_server"].append(int(name))
        except (FileNotFoundError, ProcessLookupError):
            continue
    return output


def lineage(child, ancestor, maximum=8):
    chain = []
    for _ in range(maximum):
        row = E.process_identity(child)
        chain.append({key: row[key] for key in ("host_pid", "start_ticks", "parent_host_pid")})
        if child == ancestor:
            return chain
        need(row["parent_host_pid"] > 1 and row["parent_host_pid"] != child, "CELL_ANCESTRY_DIVERGED")
        child = row["parent_host_pid"]
    raise Rejected("CELL_ANCESTRY_DEPTH_BOUND")


def discover_successor(receipt, before_service, old):
    daemon = service()
    need(daemon == before_service, "NATIVE_CELL_RESTART_CHANGED_HOST_DAEMON")
    presenter = service(True)
    launcher_pid = receipt["host_pid"]
    launcher = E.process_identity(launcher_pid)
    previous = old["process_snapshot"]["binding"]["processes"]
    need(launcher["parent_host_pid"] == previous["daemon"]["host_pid"] and launcher["uids"] == [0] * 4 and
         launcher["executable"] == previous["launcher"]["executable"] and
         (launcher["host_pid"], launcher["start_ticks"]) != (previous["launcher"]["host_pid"], previous["launcher"]["start_ticks"]),
         "NEW_NATIVE_LAUNCHER_OWNERSHIP_REQUIRED")
    candidates = role_candidates()
    need(len(candidates["android_init"]) == 1, "CELL_INIT_AMBIGUOUS_OR_NOT_READY")
    init = candidates["android_init"][0]
    candidates = role_candidates(init)
    need(all(len(values) == 1 for values in candidates.values()), "NEW_FRAMEWORK_ROLES_AMBIGUOUS_OR_NOT_READY")
    roles = {key: value[0] for key, value in candidates.items()}
    roles.update(daemon=int(daemon["MainPID"]), launcher=launcher_pid, presenter=int(presenter["MainPID"]))
    lineage(init, launcher_pid)
    snapshot = E.capture_processes(roles)
    rows = snapshot["binding"]["processes"]
    need(rows["android_init"]["namespace_pids"][-1] == 1 and rows["android_init"]["uids"] == [0] * 4 and
         rows["android_init"]["cmdline"][0] == "/init", "NEW_INIT_SHAPE")
    for role in ("zygote64", "system_server", "surfaceflinger", "composer"):
        expected_parent = roles["zygote64"] if role == "system_server" else init
        need(rows[role]["parent_host_pid"] == expected_parent and rows[role]["uids"] == previous[role]["uids"] and
             rows[role]["executable"] == previous[role]["executable"] and
             rows[role]["cmdline"] == previous[role]["cmdline"] and
             rows[role]["namespaces"]["pid"] == rows["android_init"]["namespaces"]["pid"], "SUCCESSOR_ANDROID_ROLE_LINEAGE")
    need(rows["presenter"]["uids"] == [1000] * 4 and rows["presenter"]["executable"] == previous["presenter"]["executable"],
         "SUCCESSOR_OWN_USER_PRESENTER_REQUIRED")
    return roles, presenter


def take_exclusive_lock(fd):
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as error:
        raise Rejected("OTHER_ACTION_OR_FLOW_LEASE_ACTIVE") from error


def acquire_lock(pool, path, expected=None):
    fd = open_host(pool, path, os.O_RDWR)
    before = metadata(fd)
    need(stat.S_ISREG(before["st_mode"]) and before["st_nlink"] == 1 and before["st_uid"] == 0, "EXISTING_LOCK_FILE_REQUIRED")
    if expected is not None:
        need({key: before[key] for key in ("st_dev", "st_ino")} == expected, "LOCK_INODE_CHANGED")
    take_exclusive_lock(fd)
    check = open_host(pool, path, os.O_RDWR)
    try:
        need(tuple(metadata(check)[key] for key in ("st_dev", "st_ino")) ==
             tuple(before[key] for key in ("st_dev", "st_ino")), "LOCK_PATH_REPLACED")
    finally:
        pool.close(check)
    return fd, {key: before[key] for key in ("st_dev", "st_ino")}


def reviewed_drain(pool, pin):
    value = parse(pinned_record(pin, 262144))
    need(set(value) == {"schema", "boot_id", "reviewed_monotonic_ns", "unresolved_start_attempts", "workers", "flow_locks", "source_receipts", "review_scope"} and
         value["schema"] == "pocket4-owned-worker-drain-v1" and value["boot_id"] == boot_id() and
         value["unresolved_start_attempts"] == [] and value["review_scope"] == "all-known-pocket4-UI-install-observer-restart-jobs",
         "REVIEWED_COMPLETE_WORKER_DRAIN_REQUIRED")
    age = time.monotonic_ns() - value["reviewed_monotonic_ns"]
    need(type(value["reviewed_monotonic_ns"]) is int and 0 <= age <= 300_000_000_000, "DRAIN_REVIEW_TOO_OLD")
    need(type(value["source_receipts"]) is list and 0 < len(value["source_receipts"]) <= 64, "ACTUAL_JOB_RECEIPTS_REQUIRED")
    for receipt in value["source_receipts"]:
        pinned_record(receipt, 1024 * 1024)
    need(type(value["workers"]) is list and len(value["workers"]) <= 256, "WORKER_SET_BOUND")
    for row in value["workers"]:
        need(set(row) == {"host_pid", "start_ticks"} and all(type(v) is int and v > 0 for v in row.values()), "WORKER_IDENTITY_REQUIRED")
        try:
            current = E.process_identity(row["host_pid"])
        except (E.EpochError, FileNotFoundError, ProcessLookupError):
            try:
                os.stat("/proc/" + str(row["host_pid"]), follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise Rejected("WORKER_EXIT_NOT_PROVEN")
        need(current["start_ticks"] != row["start_ticks"], "KNOWN_WORKER_STILL_ALIVE")
    need(type(value["flow_locks"]) is list and len(value["flow_locks"]) <= 64, "FLOW_LOCK_SET_BOUND")
    for row in value["flow_locks"]:
        need(set(row) == {"path", "identity"} and row["path"].startswith("/home/alex/work/") and row["path"].endswith("/flow.lock"), "OWN_FLOW_LOCK_PATH_REQUIRED")
        acquire_lock(pool, row["path"], row["identity"])
    return value


def validate_plan(plan):
    required = {"schema", "old_guard", "old_epoch_sha256", "old_composer", "native_cli", "cell_config_sha256", "targets", "drain", "unknown_evidence", "output_root"}
    need(type(plan) is dict and set(plan) == required and plan["schema"] == "pocket4-owned-cell-recovery-plan-v1", "EXACT_RECOVERY_PLAN_REQUIRED")
    need(sha_value(plan["old_epoch_sha256"]) and sha_value(plan["cell_config_sha256"]), "PLAN_DIGEST_REQUIRED")
    need(plan["old_guard"]["path"] == "/home/alex/work/pocket4-main-current-baseline-01/current_baseline_guard.py" and
         plan["old_guard"]["sha256"] == "0ee54ef97c073857609aedb4670395db084ceacc7d28558315647ab2ffbef679" and
         plan["old_epoch_sha256"] == "734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2",
         "THIS_TRANSITION_REQUIRES_ORIGINAL_REVIEWED_BASELINE")
    need(plan["native_cli"] == {"path": "/usr/bin/droidloomctl", "bytes": 1705648,
         "sha256": "f81e0223f6b256584d07a5e8fbc72f3f4c764ab53a88469b45b587c101e12c79"}, "PINNED_NATIVE_CLI_REQUIRED")
    composer = plan["old_composer"]
    need(set(composer) == {"host_pid", "start_ticks", "sha256", "bytes"} and
         composer == {"host_pid": 3588896, "start_ticks": 80797154, "sha256": "a657ac25be3e64ce0b639313cf392747589a946314744b0b65c1f98415d7a06b", "bytes": 286656},
         "REVIEWED_OLD_NATIVE_OWNER_REQUIRED")
    path_parts(plan["output_root"])
    need(plan["output_root"].startswith("/home/alex/work/pocket4-cell-successor-") and
         plan["output_root"].count("/") == 4 and not os.path.lexists(plan["output_root"]), "NEW_EXCLUSIVE_SUCCESSOR_ROOT_REQUIRED")
    need(type(plan["unknown_evidence"]) is list and 0 < len(plan["unknown_evidence"]) <= 32, "UNKNOWN_LAUNCH_EVIDENCE_MUST_BE_PRESERVED")
    need(any(p.get("path") == UNKNOWN_FLOW + "/steps/launch-01/result.json" and p.get("sha256") ==
         "037076b15c27611f83815ad243280a1ec8eae82416616c928c9106e17f7a12ca" for p in plan["unknown_evidence"]), "ORIGINAL_UNKNOWN_RESULT_REQUIRED")


def create_private_root(path):
    pool = FDs()
    try:
        parent, leaf = path.rsplit("/", 1)
        fd = open_host(pool, parent, os.O_RDONLY | os.O_DIRECTORY)
        os.mkdir(leaf, 0o700, dir_fd=fd)
        os.fsync(fd)
        root = open_host(pool, path, os.O_RDONLY | os.O_DIRECTORY)
        st = os.fstat(root)
        need(st.st_uid == 0 and stat.S_IMODE(st.st_mode) == 0o700, "PRIVATE_ROOT_OWNER_REQUIRED")
        os.mkdir("source", 0o700, dir_fd=root)
        os.fsync(root)
    finally:
        pool.close_all()


def write_new(path, raw):
    need(type(raw) is bytes and 0 < len(raw) <= 8 * 1024 * 1024, "PRIVATE_ARTIFACT_SIZE_BOUND")
    pool = FDs()
    try:
        fd = open_host(pool, path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
        os.fchmod(fd, 0o400)
        count = 0
        while count < len(raw):
            written = os.write(fd, raw[count:])
            need(written > 0, "ARTIFACT_SHORT_WRITE")
            count += written
        os.fsync(fd)
        st = os.fstat(fd)
        need(st.st_uid == 0 and stat.S_IMODE(st.st_mode) == 0o400 and st.st_nlink == 1 and st.st_size == len(raw), "PRIVATE_ARTIFACT_METADATA")
        parent = open_host(pool, path.rsplit("/", 1)[0], os.O_RDONLY | os.O_DIRECTORY)
        os.fsync(parent)
    finally:
        pool.close_all()
    return {"path": path, "sha256": digest(raw), "bytes": len(raw)}


def validate_span(samples):
    need(type(samples) is list and len(samples) == 3, "EXACTLY_THREE_DOUBLE_SAMPLES_REQUIRED")
    need(all(sample["binding"] == samples[0]["binding"] for sample in samples), "SAMPLED_PROCESS_IDENTITIES_CHANGED")
    times = [sample["collected_monotonic_ns"] for sample in samples]
    need(all(type(value) is int and value > 0 for value in times) and times == sorted(set(times)) and
         10_000_000_000 <= times[-1] - times[0] <= 90_000_000_000, "EXPLICIT_TEN_TO_NINETY_SECOND_OBSERVATION_REQUIRED")
    return times


def collect_runtime(pool, held, daemon, presenter, config_sha, expected_engine):
    held.verify()
    config, config_file = host_read(CONFIG, 131072, config_sha)
    binaries = {role: hash_fd(fd, 256 * 1024 * 1024, time.monotonic() + 20) for role, fd in held.exes.items()}
    engine_fd = pool.own(H.open_in_root(held.roots["android_init"], ENGINE))
    try:
        engine = hash_fd(engine_fd, 256 * 1024 * 1024, time.monotonic() + 20)
    finally:
        pool.close(engine_fd)
    need(engine["sha256"] == expected_engine, "DEPLOYED_ENGINE_CHANGED")
    check_path(pool, held.roots["android_init"], ENGINE, engine["file"])
    cp = classpaths(pool, held)
    held.verify()
    return {"held": held.capture(), "binaries": binaries, "engine": engine, "classpath": cp,
            "cell_config": {"path": CONFIG, "bytes": len(config), "sha256": config_sha, "file": config_file},
            "daemon_service": daemon, "presenter_service": presenter, "limits": limits()}


def android_epoch(snapshot):
    rows = snapshot["binding"]["processes"]
    binding = {"boot_id": snapshot["binding"]["boot_id"], "processes": {"init": rows["android_init"],
               **{role: rows[role] for role in ("zygote64", "system_server", "surfaceflinger")}}}
    return {"schema": E.SCHEMA, "binding": binding, "sha256": digest(canonical(binding)),
            "collected_monotonic_ns": snapshot["collected_monotonic_ns"]}


def verify_runtime(pool, held, runtime):
    need(held.capture() == runtime["held"] or held.before["binding"] == runtime["held"]["process_snapshot"]["binding"], "CURRENT_RUNTIME_ROLES_CHANGED")
    need(held.extra == runtime["held"]["extra"], "CURRENT_RUNTIME_EXTRA_IDENTITIES_CHANGED")
    need(boot_id() == runtime["held"]["process_snapshot"]["binding"]["boot_id"], "RUNTIME_BOOT_CHANGED")
    raw, info = host_read(CONFIG, 131072, runtime["cell_config"]["sha256"])
    need(info == runtime["cell_config"]["file"] and len(raw) == runtime["cell_config"]["bytes"], "RUNTIME_CONFIG_PATH_CHANGED")
    need(service() == runtime["daemon_service"] and service(True) == runtime["presenter_service"], "RUNTIME_SERVICE_IDENTITY_CHANGED")
    need(limits() == runtime["limits"], "RUNTIME_RESOURCE_LIMITS_CHANGED")
    check_path(pool, held.roots["android_init"], ENGINE, runtime["engine"]["file"])
    classpaths(pool, held, False, runtime["classpath"])
    for role, fd in held.exes.items():
        need(metadata(fd) == runtime["binaries"][role]["file"], "RUNTIME_EXECUTABLE_FILE_CHANGED")
    held.verify()


def guard_source(root, manifest_sha, baseline, qualification):
    pins = {"root": root, "manifest_sha": manifest_sha, "baseline": baseline, "qualification": qualification}
    return ('''"""Pinned successor guard; no discovery, adoption or action entry."""
import hashlib,os,stat,time,types,json
PINS = ''' + repr(pins) + '''
def _read(path,limit,pin):
    parts=path[1:].split('/')
    if not path.startswith('/') or any(x in ('','.','..') for x in parts):raise RuntimeError('GUARD_PATH')
    fds=[]
    try:
        d=os.open('/',os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC);fds.append(d)
        for n in parts[:-1]:
            d=os.open(n,os.O_PATH|os.O_DIRECTORY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=d);fds.append(d)
        f=os.open(parts[-1],os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=d);fds.append(f)
        def meta(fd):
            s=os.fstat(fd)
            return tuple(getattr(s,k) for k in ('st_dev','st_ino','st_mode','st_uid','st_gid','st_nlink','st_size','st_mtime_ns','st_ctime_ns'))
        a=os.fstat(f);before=meta(f)
        if not stat.S_ISREG(a.st_mode) or a.st_nlink!=1 or not 0<a.st_size<=limit:raise RuntimeError('GUARD_FILE')
        data=b'';end=time.monotonic()+5
        while len(data)<=limit:
            if time.monotonic()>end:raise RuntimeError('GUARD_DEADLINE')
            b=os.read(f,min(65536,limit+1-len(data)))
            if not b:break
            data+=b
        if len(data)!=a.st_size or meta(f)!=before or hashlib.sha256(data).hexdigest()!=pin:raise RuntimeError('GUARD_PIN')
        g=os.open(parts[-1],os.O_RDONLY|os.O_CLOEXEC|os.O_NOFOLLOW,dir_fd=d);fds.append(g)
        if meta(g)!=before:raise RuntimeError('GUARD_PATH_REPLACED')
        return data
    finally:
        errors=[]
        for f in reversed(fds):
            try:os.close(f)
            except BaseException:errors.append(f)
        if errors:raise RuntimeError('GUARD_FD_CLOSE')
def _core():
    base=PINS['root']+'/source'
    manifest=json.loads(_read(base+'/SOURCE_PINS.json',65536,PINS['manifest_sha']))
    pin=manifest['files']['successor_runtime.py']
    raw=_read(base+'/successor_runtime.py',65536,pin['sha256'])
    m=types.ModuleType('pinned_successor_core');m.__file__=base+'/successor_runtime.py'
    exec(compile(raw,m.__file__,'exec'),m.__dict__)
    m.configure(base,PINS['manifest_sha'])
    return m
def current_baseline():
    m=_core()
    return m.parse(m.pinned_record(PINS['baseline']))
def current_guard(candidate=None,*,action_attempted=False):
    try:return _core().guard_check(PINS,candidate,action_attempted=action_attempted)
    except BaseException as e:
        e.action_attempted=action_attempted;e.outcome_unknown=action_attempted;e.automatic_retry=False
        raise
def check_app_scope(reference,packages):
    return _core().guard_check_apps(PINS,reference,packages)
''').encode()


def guard_documents(pins):
    baseline = parse(pinned_record(pins["baseline"]))
    qualification = parse(pinned_record(pins["qualification"], 65536))
    need(baseline.get("schema") == "pocket4-successor-runtime-baseline-v1" and qualification.get("schema") == "pocket4-successor-qualification-v1" and
         qualification.get("identity_qualified") is True and qualification.get("baseline") == pins["baseline"] and
         qualification.get("source_manifest_sha256") == pins["manifest_sha"] and
         qualification.get("UI_or_install_runtime_admitted") is False and qualification.get("production_ready") is False and
         qualification.get("old_native_pidfd_deaths_proved") is True and qualification.get("initial_app_scope_unchanged") is True,
         "ACTUAL_SUCCESSOR_QUALIFICATION_REQUIRED")
    need(baseline["runtime_epoch_sha256"] == digest(canonical(baseline["runtime"])) and
         qualification["runtime_epoch_sha256"] == baseline["runtime_epoch_sha256"], "RUNTIME_BASELINE_DIGEST_DIFFERS")
    times = baseline["sample_monotonic_ns"]
    need(len(times) == 3 and times == sorted(set(times)) and 10_000_000_000 <= times[-1] - times[0] <= 90_000_000_000,
         "QUALIFIED_OBSERVATION_SPAN_REQUIRED")
    for name in ("observation_fds",):
        row = qualification[name]
        need(row["acquired"] == row["closed"] and row["remaining"] == 0 and row["errors"] == [], "QUALIFICATION_FDS_NOT_RETIRED")
    return baseline, qualification


def guard_check(pins, candidate=None, *, action_attempted=False):
    baseline, _ = guard_documents(pins)
    need(candidate is None or candidate == baseline, "CACHED_BASELINE_DIFFERS")
    pool = FDs()
    try:
        runtime = baseline["runtime"]
        expected = runtime["held"]["process_snapshot"]
        held = HeldProcesses(pool, {role: row["host_pid"] for role, row in expected["binding"]["processes"].items()})
        need(held.before["binding"] == expected["binding"], "SUCCESSOR_RUNTIME_EPOCH_CHANGED")
        verify_runtime(pool, held, runtime)
    except BaseException as error:
        if action_attempted:
            error.add_note("ACTION_OUTCOME_UNKNOWN_NO_AUTOMATIC_RETRY")
        raise
    finally:
        pool.close_all()
    return {"schema": "pocket4-successor-main-guard-v1", "Main_epoch_sha256": baseline["framework_epoch"]["sha256"],
            "runtime_epoch_sha256": baseline["runtime_epoch_sha256"], "baseline_sha256": pins["baseline"]["sha256"],
            "eight_roles_including_composer_match": True, "complete_paired_classpath_matches": True,
            "resource_limits_match": True, "runtime_only_app_scopes_checked_separately": True,
            "UI_or_install_runtime_admitted": False, "production_ready": False}


def guard_check_apps(pins, reference, packages):
    baseline, _ = guard_documents(pins)
    scope = parse(pinned_record(reference))
    need(scope.get("schema") == "pocket4-versioned-app-scope-v1" and
         scope.get("runtime_epoch_sha256") == baseline["runtime_epoch_sha256"] and
         type(packages) is list and 0 < len(packages) <= 128 and len(set(packages)) == len(packages) and
         set(packages) <= set(scope["apps"]), "EXACT_APP_SCOPE_REQUIRED")
    guard_check(pins)
    pool = FDs()
    try:
        expected = baseline["runtime"]["held"]["process_snapshot"]
        held = HeldProcesses(pool, {role: row["host_pid"] for role, row in expected["binding"]["processes"].items()})
        need(held.before["binding"] == expected["binding"], "APP_SCOPE_RUNTIME_CHANGED")
        app_scope(pool, held, packages, {key: scope["apps"][key] for key in packages}, False)
    finally:
        pool.close_all()
    guard_check(pins)
    return {"schema": "pocket4-app-scope-guard-v1", "runtime_epoch_sha256": baseline["runtime_epoch_sha256"],
            "app_scope_sha256": reference["sha256"], "packages": packages, "current_apk_paths_and_file_identities_match": True,
            "new_signature_verification_performed": False, "UI_or_install_runtime_admitted": False}


def perform(plan, encoded, manifest_sha, execute=False):
    validate_plan(plan)
    need(os.getuid() == os.geteuid() == 0 and sys.platform == "linux" and os.uname().machine == "x86_64", "EXACT_ROOT_X86_64_LINUX_REQUIRED")
    pool, leases, old, output_created = FDs(), FDs(), None, False
    result = {"schema": "pocket4-owned-cell-recovery-result-v1", "ok": False, "restart_attempted": False,
              "outcome_unknown": False, "automatic_retry": False, "identity_qualified": False,
              "UI_or_install_runtime_admitted": False, "production_ready": False, "errors": [],
              "namespace_entries": 0, "Android_commands": 0, "UI_actions": 0, "installs": 0, "permission_changes": 0}
    baseline = app_document = None
    phase = "old_guard"
    try:
        guard_raw = pinned_record(plan["old_guard"], 65536)
        guard = load_module(guard_raw, "immutable_predecessor_guard", plan["old_guard"]["path"])
        old_receipt = guard.current_guard()
        need(old_receipt.get("Main_epoch_sha256") == plan["old_epoch_sha256"], "OLD_GUARD_EPOCH_DIFFERS")
        previous = guard.current_baseline()
        roles = {role: row["host_pid"] for role, row in previous["all_seven_processes"]["binding"]["processes"].items()}
        roles["composer"] = plan["old_composer"]["host_pid"]
        old = HeldProcesses(pool, roles)
        old_rows = old.before["binding"]["processes"]
        composer = old_rows["composer"]
        need(composer["start_ticks"] == plan["old_composer"]["start_ticks"] and composer["executable"] == COMPOSER_EXE and
             composer["parent_host_pid"] == roles["android_init"] and composer["namespaces"]["pid"] == old_rows["android_init"]["namespaces"]["pid"],
             "OLD_COMPOSER_LINEAGE_DIFFERS")
        phase = "drain_and_existing_leases"
        _, lock_identity = acquire_lock(leases, ACTION_LOCK)
        drain = reviewed_drain(leases, plan["drain"])
        unknown_evidence(plan)
        phase = "native_cli_and_own_cell"
        pinned_record(plan["native_cli"], 32 * 1024 * 1024)
        help_raw, _, help_command = bounded_child(native_argv("help"))
        need(help_command["complete"] and all(word in help_raw.lower() for word in (b"restart", b"status", b"droidloom")), "LIVE_NATIVE_CELL_CLI_PARSE_NOT_VERIFIED")
        status_raw, _, status_command = bounded_child(native_argv("status"))
        before_status = native_running(status_raw, status_command)
        need(before_status["host_pid"] == roles["launcher"], "ACTUAL_OWN_CELL_STATUS_DIFFERS")
        daemon, presenter = service(), service(True)
        need(int(daemon["MainPID"]) == roles["daemon"] and int(presenter["MainPID"]) == roles["presenter"] and
             daemon == previous["current_service"], "PREDECESSOR_SERVICE_LINEAGE_DIFFERS")
        target_document = parse(pinned_record(plan["targets"], 262144))
        need(set(target_document) == {"schema", "packages", "catalog_source_sha256"} and
             target_document["schema"] == "pocket4-restart-targets-v1" and sha_value(target_document["catalog_source_sha256"]), "TARGET_ROSTER_SCHEMA")
        targets = target_document["packages"]
        need(type(targets) is list and 0 < len(targets) <= 128 and len(set(targets)) == len(targets) and
             all(type(name) is str and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{1,255}", name) for name in targets), "TARGET_PACKAGE_SET_REQUIRED")
        phase = "actual_predecessor_runtime_and_app_scope"
        old_runtime = collect_runtime(pool, old, daemon, presenter, plan["cell_config_sha256"], previous["engine_sha256"])
        need(old_runtime["limits"] == previous["limits"] and classpath_bytes(old_runtime["classpath"]) == classpath_bytes(previous["classpath"]), "PREDECESSOR_RUNTIME_ARTIFACTS_CHANGED")
        for role in previous["current_process_executables"]:
            need(old_runtime["binaries"][role]["sha256"] == previous["current_process_executables"][role]["sha256"], "PREDECESSOR_EXECUTABLE_BYTES_CHANGED")
        need(old_runtime["binaries"]["composer"]["sha256"] == plan["old_composer"]["sha256"] and
             old_runtime["binaries"]["composer"]["bytes"] == plan["old_composer"]["bytes"], "PREDECESSOR_COMPOSER_BYTES_CHANGED")
        before_apps = app_scope(pool, old, targets)
        guard.current_guard()
        verify_runtime(pool, old, old_runtime)
        unknown_evidence(plan)
        result.update(preflight_passed=True, old_epoch_sha256=plan["old_epoch_sha256"], target_count=len(targets),
                      native_cell_restart_argv=native_argv("restart"), historical_unknown_results_preserved=True)
        if not execute:
            result["ok"] = True
            return result
        phase = "durable_pre_restart_checkpoint"
        root = plan["output_root"]
        create_private_root(root)
        output_created = True
        for name, raw in encoded.items():
            write_new(root + "/source/" + name, raw)
        pre = {"schema": "pocket4-lifecycle-preflight-v1", "plan": plan, "plan_sha256": digest(canonical(plan)),
               "source_manifest_sha256": manifest_sha, "old_guard_receipt": old_receipt, "runtime": old_runtime,
               "apps": before_apps, "actual_native_status": before_status, "native_status_command": status_command,
               "action_lock_identity": lock_identity, "reviewed_drain": drain, "created_monotonic_ns": time.monotonic_ns()}
        pre_pin = write_new(root + "/predecessor.private.json", canonical(pre) + b"\n")
        old.verify()
        guard.current_guard()
        pinned_record(plan["native_cli"], 32 * 1024 * 1024)
        unknown_evidence(plan)
        need(time.monotonic_ns() - drain["reviewed_monotonic_ns"] <= 300_000_000_000, "DRAIN_REVIEW_EXPIRED_BEFORE_RESTART")
        for path, identity in [(ACTION_LOCK, lock_identity)] + [(r["path"], r["identity"]) for r in drain["flow_locks"]]:
            check = open_host(pool, path, os.O_RDWR)
            try:
                need({k: metadata(check)[k] for k in ("st_dev", "st_ino")} == identity, "LEASE_PATH_CHANGED_BEFORE_RESTART")
            finally:
                pool.close(check)
        # Keep only the original pidfds across stop/start. Root/executable FDs
        # must not pin old mounts or image references during native teardown.
        old.release_views_keep_pidfds()
        attempt_pin = write_new(root + "/restart-attempted.json", canonical({"schema": "pocket4-native-restart-attempt-v1",
            "predecessor": pre_pin, "argv": native_argv("restart"), "started_monotonic_ns": time.monotonic_ns(),
            "automatic_retry": False, "old_launch_outcome": "UNKNOWN_WITH_OBSERVED_ANDROID_TASK_SIDE_EFFECT"}) + b"\n")
        result["restart_attempted"], result["outcome_unknown"] = True, True
        phase = "single_owned_native_restart"
        raw, stderr, command = bounded_child(native_argv("restart"), 45)
        receipt_pin = write_new(root + "/native-restart-receipt.private.json", canonical({"schema": "pocket4-native-restart-actual-receipt-v1",
            "attempt": attempt_pin, "command": command, "stdout_utf8": raw.decode("utf-8", "strict"),
            "stderr_utf8": stderr.decode("utf-8", "replace")}) + b"\n")
        receipt = native_running(raw, command)
        phase = "old_native_owner_pidfd_deaths"
        end = time.monotonic() + 30
        while not all(pidfd_dead(old.pidfds[role]) for role in RETIRED):
            need(time.monotonic() < end, "OLD_CELL_OR_NATIVE_OWNER_STILL_ALIVE")
            time.sleep(.1)
        death = {role: {"host_pid": old_rows[role]["host_pid"], "start_ticks": old_rows[role]["start_ticks"],
                         "original_pre_restart_pidfd_readable": True} for role in RETIRED}
        need(not pidfd_dead(old.pidfds["daemon"]), "NATIVE_CELL_RESTART_KILLED_HOST_DAEMON")
        launcher = E.process_identity(receipt["host_pid"])
        transition_pin = write_new(root + "/retired-lifecycle.private.json", canonical({"schema": "pocket4-actual-native-lifecycle-transition-v1",
            "predecessor": pre_pin, "native_receipt": receipt_pin, "boot_id": boot_id(), "old_pidfd_deaths": death,
            "actual_successor_launcher": launcher, "observed_monotonic_ns": time.monotonic_ns(),
            "old_launch_outcome": "UNKNOWN_WITH_OBSERVED_ANDROID_TASK_SIDE_EFFECT", "old_launch_replayed": False}) + b"\n")
        result["outcome_unknown"] = False
        result["old_launch_outcome"] = "UNKNOWN_WITH_OBSERVED_ANDROID_TASK_SIDE_EFFECT"
        phase = "actual_successor_discovery"
        end = time.monotonic() + 60
        while True:
            try:
                new_roles, new_presenter = discover_successor(receipt, daemon, old_runtime["held"])
                break
            except (Rejected, E.EpochError, FileNotFoundError, ProcessLookupError) as error:
                if isinstance(error, Rejected) and str(error) not in {"CELL_INIT_AMBIGUOUS_OR_NOT_READY", "NEW_FRAMEWORK_ROLES_AMBIGUOUS_OR_NOT_READY", "SERVICE_RUNNING_IDENTITY_REQUIRED", "SERVICE_QUERY_FAILED"}:
                    raise
                need(time.monotonic() < end, "SUCCESSOR_FRAMEWORK_NOT_READY_IN_BOUND")
                time.sleep(.25)
        new = HeldProcesses(pool, new_roles)
        new_rows = new.before["binding"]["processes"]
        need(new_rows["launcher"] == launcher, "SUCCESSOR_LAUNCHER_REPLACED_AFTER_RECEIPT")
        if new_rows["presenter"] != old_rows["presenter"]:
            need(pidfd_dead(old.pidfds["presenter"]), "OLD_PRESENTER_STILL_ALIVE_AFTER_REPLACEMENT")
        need(new.before["binding"]["boot_id"] == old.before["binding"]["boot_id"], "HOST_BOOT_CHANGED")
        write_new(root + "/successor-candidate.private.json", canonical({"schema": "pocket4-observed-successor-candidate-v1",
            "transition": transition_pin, "source_manifest_sha256": manifest_sha, "held": new.capture(),
            "presenter_service": new_presenter, "discovery_performed_once_after_actual_native_receipt": True}) + b"\n")
        phase = "fresh_successor_runtime_artifacts"
        runtime = collect_runtime(pool, new, daemon, new_presenter, plan["cell_config_sha256"], previous["engine_sha256"])
        need(runtime["limits"] == old_runtime["limits"] and classpath_bytes(runtime["classpath"]) == classpath_bytes(old_runtime["classpath"]), "RESTART_CHANGED_RUNTIME_ARTIFACT_BYTES")
        need(all(runtime["binaries"][role]["sha256"] == old_runtime["binaries"][role]["sha256"] for role in ROLE_NAMES), "RESTART_CHANGED_EXECUTABLE_BYTES")
        phase = "fresh_apps_unchanged_across_restart"
        after_apps = app_scope(pool, new, targets)
        need(app_bytes(after_apps) == app_bytes(before_apps), "APPS_OR_DATA_CHANGED_DURING_RESTART")
        phase = "three_double_samples"
        samples = [new.verify()]
        verify_runtime(pool, new, runtime)
        samples.append(new.verify())
        until = samples[0]["collected_monotonic_ns"] + 10_000_000_000
        while time.monotonic_ns() <= until:
            need(all(not pidfd_dead(fd) for fd in new.pidfds.values()), "SUCCESSOR_ROLE_DIED_DURING_OBSERVATION")
            time.sleep(.1)
        samples.append(new.verify())
        times = validate_span(samples)
        verify_runtime(pool, new, runtime)
        app_scope(pool, new, targets, after_apps, False)
        unknown_evidence(plan)
        need(all(pidfd_dead(old.pidfds[role]) for role in RETIRED), "ORIGINAL_PIDFD_DEATH_EVIDENCE_CHANGED")
        pinned_record(plan["native_cli"], 32 * 1024 * 1024)
        final_status_raw, _, final_status_command = bounded_child(native_argv("status"))
        need(native_running(final_status_raw, final_status_command)["host_pid"] == new_roles["launcher"], "FINAL_NATIVE_CELL_OWNER_CHANGED")
        final = new.verify()
        need(final["binding"] == samples[0]["binding"], "FINAL_SUCCESSOR_IDENTITY_CHANGED")
        runtime["held"]["process_snapshot"] = final
        runtime_sha = digest(canonical(runtime))
        framework = android_epoch(final)
        need(framework["sha256"] != plan["old_epoch_sha256"], "OLD_FRAMEWORK_EPOCH_CANNOT_BE_REAUTHORIZED")
        baseline = {"schema": "pocket4-successor-runtime-baseline-v1", "kind": "explicit-owned-cell-lifecycle-successor",
                    "runtime": runtime, "runtime_epoch_sha256": runtime_sha, "framework_epoch": framework,
                    "predecessor": pre_pin, "actual_lifecycle_transition": transition_pin,
                    "sample_monotonic_ns": times, "bounded_observation_is_not_future_stability_proof": True,
                    "framework_exit_cause_resolved": False, "native_future_epoch_retirement_fix_deployed": False,
                    "UI_or_install_runtime_admitted": False, "production_ready": False}
        app_document = {"schema": "pocket4-versioned-app-scope-v1", "runtime_epoch_sha256": runtime_sha,
                        "kind": "unchanged-across-explicit-cell-restart", "apps": after_apps,
                        "previous_app_content_sha256": digest(canonical(app_bytes(before_apps))),
                        "target_roster": plan["targets"], "fresh_signature_verification_performed": False,
                        "post_restart_launcher_resolver_enumerated": False, "UI_or_install_runtime_admitted": False}
        result.update(new_framework_epoch_sha256=framework["sha256"], runtime_epoch_sha256=runtime_sha,
                      old_native_pidfd_deaths_proved=True, initial_app_scope_unchanged=True,
                      exact_three_double_samples=True, sample_span_ns=times[-1] - times[0])
    except BaseException as error:
        result["errors"].append({"phase": phase, **safe_error(error)})
    finally:
        try:
            pool.close_all()
        except BaseException as error:
            result["errors"].append({"phase": "descriptor_retirement", **safe_error(error)})
        result["observation_fds"] = pool.summary()
        if not execute:
            try: leases.close_all()
            except BaseException as error: result["errors"].append(safe_error(error))
            result["lease_fds"] = leases.summary()
        if result["errors"]:
            result["ok"] = False
    if baseline is not None and app_document is not None and not result["errors"]:
        try:
            root = plan["output_root"]
            bpin = write_new(root + "/baseline.private.json", canonical(baseline) + b"\n")
            apin = write_new(root + "/app-scope-01.private.json", canonical(app_document) + b"\n")
            qualification = {"schema": "pocket4-successor-qualification-v1", "identity_qualified": True,
                "baseline": bpin, "initial_app_scope": apin, "runtime_epoch_sha256": baseline["runtime_epoch_sha256"],
                "source_manifest_sha256": manifest_sha, "old_native_pidfd_deaths_proved": True,
                "initial_app_scope_unchanged": True, "observation_fds": result["observation_fds"],
                "UI_or_install_runtime_admitted": False, "production_ready": False, "old_unknown_launch_replayed": False}
            qpin = write_new(root + "/qualification.json", canonical(qualification) + b"\n")
            raw_guard = guard_source(root, manifest_sha, bpin, qpin)
            compile(raw_guard, root + "/current_baseline_guard.py", "exec")
            gpin = write_new(root + "/current_baseline_guard.py", raw_guard)
            generated = load_module(raw_guard, "actual_generated_successor_guard", gpin["path"])
            result["published_guard_readback"] = generated.current_guard()
            result.update(ok=True, identity_qualified=True, baseline=bpin, qualification=qpin,
                          app_scope=apin, generated_current_guard=gpin)
        except BaseException as error:
            result["errors"].append({"phase": "successor_publication", **safe_error(error)})
    try: leases.close_all()
    except BaseException as error:
        result["ok"] = False
        result["errors"].append({"phase": "lease_retirement", **safe_error(error)})
    result["lease_fds"] = leases.summary()
    if output_created:
        try:
            write_new(plan["output_root"] + "/result.json", canonical(result) + b"\n")
        except BaseException as error:
            result["ok"] = False
            result["errors"].append({"phase": "final_result_publication", **safe_error(error)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", default="preflight", choices=("preflight", "execute-native-cell-restart"))
    parser.add_argument("--plan", required=True)
    parser.add_argument("--plan-sha256", required=True)
    parser.add_argument("--source-manifest-sha256", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        source_dir = os.path.dirname(os.path.abspath(__file__))
        encoded = configure(source_dir, args.source_manifest_sha256)
        need(host_read(__file__, 65536)[0] == encoded["successor_runtime.py"], "RUNNING_SOURCE_DIFFERS_FROM_PINNED_BUNDLE")
        plan = parse(host_read(args.plan, 262144, args.plan_sha256)[0])
        result = perform(plan, encoded, args.source_manifest_sha256, args.mode == "execute-native-cell-restart")
    except BaseException as error:
        result = {"schema": "pocket4-owned-cell-recovery-result-v1", "ok": False, "restart_attempted": False,
                  "automatic_retry": False, "errors": [safe_error(error)]}
    raw = canonical(result)
    need(len(raw) <= 65536, "PUBLIC_RESULT_BOUND")
    print(raw.decode(), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
