#!/usr/bin/env python3
"""One independently bound, user-authorized CEAir upgrade through native install.

Run only after reviewing this source, as root: python3 -B -I install_ceair_bound_r1.py
The unchanged pinned collect_readonly.py must be adjacent. No arguments, target
overrides, retries, UI, grants, ADB, task removal, or lifecycle commands exist.
This deliberately creates a NEW CEAir-only install scope, not a Bili R5 scope.
The existing baseline's identity-only qualification is never modified.

The native client transfers an APK descriptor to the existing daemon. Reviewed
denialwm/droidloom@246bae669a4d8f7dacc8824e927db144f4362347 apk.rs uses
cmd package install -r --user 0 -S <bytes>; no -g/-d, uninstall or launch.
The daemon enforces its existing SO_PEERCRED/active-cell checks. A complete
native response, fresh installed bytes, retained data-directory identity and
unchanged Main are all required for success. Client timeout is UNKNOWN and
never implies that the independent daemon's package operation has stopped.

Native binding is inherited from the successful Beike r3 worker and the
exact stat tuples observed in job 1a1b07a3192-fc05-70bb. Beike r2's CLI
uid==0 condition was an added assumption;
the existing current-baseline guard contains no such CLI ownership rule.
The measured CLI is UID/GID 1000:1000, mode 0755. The daemon remains
UID/GID 0:0 and matches the running daemon's executable and pinned baseline.
"""
import sys
sys.dont_write_bytecode = True

import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import selectors
import signal
import stat
import subprocess
import time
import types


BASE_SHA = "04dcc9337aa61ed663e3ce3dea8ab13a963c4826588fcd1c25554466ed30acd1"
BASE_BYTES = 48526
PACKAGE = "com.rytong.ceair"
UID = 10145
USER = 0
OLD_VERSION = 238
OLD_BYTES = 220958172
OLD_SHA = "20774ddb560e94b91459606bdaadbafdba4194f85418ddeca991d20c5fe728c7"
OLD_CODE_PATH = "/data/app/~~AKsOfEjEFKb2oq9Z48CtXg==/com.rytong.ceair-cPwRSiCUKdHQTxGHg9jw5g=="
NEW_VERSION = 239
NEW_NAME = "9.5.16"
NEW_BYTES = 220804847
NEW_SHA = "a6da8d746f98cae884f6b0137b5c7e8412836adf75530b763dae1536c75522ce"
SIGNER = "b48f75514e956be6bd7d56f1701136c8d76f19459bd724ac52390a572bc0ecbf"
STAGING = "/home/alex/work/pocket4-eight-apps-upgrade-20261106-r1"
CANDIDATE_PATH = "/home/alex/work/pocket4-eight-apps-upgrade-20261106-r1/com.rytong.ceair.apk"
VERIFIER_DIR = "/home/alex/work/pocket4-eight-apps-upgrade-20261106-r1/com.rytong.ceair-signature-verify-r1"
VERIFIER_CANONICAL_SHA = "2d01623642a90464da7c2b5baea2ca1ff73b4e1683d8bc491d0c3b76c916c564"
FLOW_NAME = "com.rytong.ceair-bound-install-r1"
FLOW_PATH = STAGING + "/" + FLOW_NAME
LOCK_PATH = "/run/lock/android-digitalis-actions.lock"
CLI_PATH = "/usr/bin/droidloomctl"
CLI_SHA = "f81e0223f6b256584d07a5e8fbc72f3f4c764ab53a88469b45b587c101e12c79"
CLI_BYTES = 1705648
DAEMON_PATH = "/usr/bin/droidloomd"
DAEMON_SHA = "4c57f3e9e92a39f2aef700d77b56c108a88d9ba3ba3cfe82b2613b363514ef30"
DAEMON_BYTES = 1920440

# Exact Python integers from the original diagnostic stdout, without a JS-number roundtrip.
NATIVE_METADATA_EVIDENCE_SHA = "b5d5de222759b562b21c1f1739bc008e782589dab0af99a44778040bf62fb410"
NATIVE_FILE_METADATA = {
    "/usr/bin/droidloomctl": {
        "st_ctime_ns": 1793735282143426356,
        "st_dev": 66306,
        "st_gid": 1000,
        "st_ino": 108004277,
        "st_mode": 33261,
        "st_mtime_ns": 1789132464000000000,
        "st_nlink": 1,
        "st_size": 1705648,
        "st_uid": 1000
    },
    "/usr/bin/droidloomd": {
        "st_ctime_ns": 1793546009221331408,
        "st_dev": 66306,
        "st_gid": 0,
        "st_ino": 108005832,
        "st_mode": 33261,
        "st_mtime_ns": 1793546009220184891,
        "st_nlink": 1,
        "st_size": 1920440,
        "st_uid": 0
    }
}
NATIVE_PARENT_IDENTITIES = {
    "/usr": {
        "st_dev": 66306,
        "st_gid": 0,
        "st_ino": 108003329,
        "st_mode": 16877,
        "st_uid": 0
    },
    "/usr/bin": {
        "st_dev": 66306,
        "st_gid": 0,
        "st_ino": 108003330,
        "st_mode": 16877,
        "st_uid": 0
    }
}
SOCKET_PATH = "/run/droidloom/control.sock"
MAIN_HOST_PID = 3588089
MEITUAN = "com.sankuai.meituan.takeoutnew"
PRIOR_BILI_FLOW = "/home/alex/work/pocket4-bilibili-owned-qa-r9-flow-474d7477074ea01fbc986e0d867924c1"
PRIOR_PINS = {
    "scope.json": (1006, "ac6dea24873125a8ac322306786f9f5760fd20b0f1c8d06bc80a498e33eddc50"),
    "steps/launch-01/result.json": (5202, "037076b15c27611f83815ad243280a1ec8eae82416616c928c9106e17f7a12ca"),
    "steps/launch-01/command-004.stdout": (495, "2957db51935e4687990181acd1e9a395fb24326c4289725b67d2d48724024fc8"),
    "steps/launch-01/prelaunch-stacks.txt": (665, "4828128d5f155cfcbdd15b713ae6430eef36735163ca5ed53dd59a7409670e76"),
}
ENV = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}
MAX_OUTPUT = 1024 * 1024
MAX_RESULT = 256 * 1024
INSTALL_TIMEOUT = 260


class Rejected(RuntimeError):
    pass


def need(value, code):
    if not value:
        raise Rejected(code)


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("ascii")


def error_record(error):
    # These exceptions carry fixed codes only; no arbitrary private file text.
    row = {"code": str(error) if isinstance(error, Rejected) else type(error).__name__}
    if hasattr(error, "code"):
        row["code"] = error.code
    if isinstance(error, OSError):
        row["errno"] = error.errno
    return row


def load_base():
    path = Path(__file__).resolve().with_name("collect_readonly.py")
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
             before.st_size == BASE_BYTES, "PINNED_READER_FILE_METADATA_DIFFERS")
        raw = os.read(fd, BASE_BYTES + 1)
        need(len(raw) == BASE_BYTES and os.read(fd, 1) == b"" and sha(raw) == BASE_SHA,
             "PINNED_READER_BYTES_DIFFER")
        after = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_mode", "st_nlink", "st_uid", "st_gid",
                  "st_size", "st_mtime_ns", "st_ctime_ns")
        need(all(getattr(before, k) == getattr(after, k) for k in fields), "PINNED_READER_CHANGED")
    finally:
        os.close(fd)
    module = types.ModuleType("pocket4_ceair_unchanged_readonly_primitives")
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def digest_fd(c, fd, budget, expected_size, expected_sha=None):
    before = c.metadata(fd)
    need(stat.S_ISREG(before["st_mode"]) and before["st_nlink"] == 1 and
         before["st_size"] == expected_size, "HELD_REGULAR_FILE_SIZE_DIFFERS")
    os.lseek(fd, 0, os.SEEK_SET)
    digest, count = hashlib.sha256(), 0
    while True:
        budget.check()
        data = os.read(fd, 1024 * 1024)
        if not data:
            break
        count += len(data)
        need(count <= expected_size, "HELD_FILE_GREW")
        digest.update(data)
    value = digest.hexdigest()
    need(count == expected_size and c.metadata(fd) == before and
         (expected_sha is None or value == expected_sha), "HELD_FILE_BYTES_OR_IDENTITY_DIFFER")
    os.lseek(fd, 0, os.SEEK_SET)
    return {"bytes": count, "sha256": value, "stat": c.public_metadata(before)}


class Store:
    """New root-private claim; all output uses the held directory descriptor."""
    def __init__(self, c, root_fd, fds):
        self.c, self.fds = c, fds
        self.parent = c.open_beneath(root_fd, STAGING, os.O_RDONLY | os.O_DIRECTORY, fds)
        os.mkdir(FLOW_NAME, 0o700, dir_fd=self.parent)  # Exclusive one-shot claim.
        self.fd = fds.own(os.open(FLOW_NAME, os.O_RDONLY | os.O_DIRECTORY |
                                 os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self.parent))
        self.identity = c.metadata(self.fd)
        need(self.identity["st_uid"] == 0 and stat.S_IMODE(self.identity["st_mode"]) == 0o700,
             "PRIVATE_ROOT_FLOW_REQUIRED")
        self.lock = self.create("flow.lock", 0o600)
        fcntl.flock(self.lock, fcntl.LOCK_EX | fcntl.LOCK_NB)

    def create(self, name, mode=0o600):
        need(name and "/" not in name and name not in (".", ".."), "OUTPUT_LEAF_REQUIRED")
        return self.fds.own(os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                                    os.O_CLOEXEC | os.O_NOFOLLOW, mode, dir_fd=self.fd))

    def write(self, name, raw):
        fd = self.create(name)
        try:
            view = memoryview(raw)
            while view:
                count = os.write(fd, view)
                need(count > 0, "OUTPUT_SHORT_WRITE")
                view = view[count:]
            os.fsync(fd)
        finally:
            self.fds.close(fd)
        os.fsync(self.fd)
        return {"path": FLOW_PATH + "/" + name, "bytes": len(raw), "sha256": sha(raw)}

    def json(self, name, value):
        raw = json.dumps(value, indent=2, ensure_ascii=True, sort_keys=True,
                         allow_nan=False).encode("ascii") + b"\n"
        need(len(raw) <= MAX_RESULT, "RESULT_SIZE_BOUND")
        return self.write(name, raw)

    def copy(self, name, source_fd, size, expected_sha, budget):
        before = self.c.metadata(source_fd)
        need(stat.S_ISREG(before["st_mode"]) and before["st_nlink"] == 1 and
             before["st_size"] == size, "COPY_SOURCE_METADATA_DIFFERS")
        target = self.create(name)
        try:
            os.lseek(source_fd, 0, os.SEEK_SET)
            digest, count = hashlib.sha256(), 0
            while True:
                budget.check()
                data = os.read(source_fd, 1024 * 1024)
                if not data:
                    break
                count += len(data)
                need(count <= size, "COPY_SOURCE_GREW")
                digest.update(data)
                view = memoryview(data)
                while view:
                    written = os.write(target, view)
                    need(written > 0, "COPY_SHORT_WRITE")
                    view = view[written:]
            need(count == size and digest.hexdigest() == expected_sha and
                 self.c.metadata(source_fd) == before, "COPY_SOURCE_CHANGED")
            os.fchmod(target, 0o400)
            os.fsync(target)
        finally:
            self.fds.close(target)
        os.fsync(self.fd)
        fd = self.fds.own(os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                                 dir_fd=self.fd))
        row = digest_fd(self.c, fd, budget, size, expected_sha)
        need(row["stat"]["uid"] == 0 and row["stat"]["mode"] & 0o777 == 0o400,
             "PRIVATE_READONLY_ARCHIVE_REQUIRED")
        return fd, {"path": FLOW_PATH + "/" + name, **row}

    def verify_path(self):
        current = self.fds.own(os.open(FLOW_NAME, os.O_RDONLY | os.O_DIRECTORY |
                                      os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=self.parent))
        try:
            row = self.c.metadata(current)
            need(all(row[k] == self.identity[k] for k in
                     ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode")), "FLOW_PATH_REPLACED")
        finally:
            self.fds.close(current)


def acquire_action_lock(c, root_fd, fds):
    fd = c.open_beneath(root_fd, LOCK_PATH, os.O_RDWR | os.O_NONBLOCK, fds)
    row = c.metadata(fd)
    need(stat.S_ISREG(row["st_mode"]) and row["st_nlink"] == 1 and
         row["st_uid"] == 0, "EXISTING_ROOT_OWNED_ACTION_LOCK_REQUIRED")
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    current = c.open_beneath(root_fd, LOCK_PATH, os.O_RDONLY, fds)
    try:
        need(c.metadata(current) == row, "ACTION_LOCK_PATH_REPLACED")
    finally:
        fds.close(current)
    return fd, c.public_metadata(row)


def verifier(c, host):
    raw, source = host.read(VERIFIER_DIR + "/result.json", 65536)
    value = c.json_object(raw)
    need(sha(canonical(value)) == VERIFIER_CANONICAL_SHA, "ACTUAL_VERIFIER_RESULT_DIFFERS")
    need(value.get("schema") == "pocket4-official-apk-verification-v1" and
         value.get("package") == PACKAGE and value.get("signature_verified") is True and
         value.get("held_file_and_path_unchanged") is True and
         value.get("signer_matches_historical_installed_reference") is True and
         value.get("signer_certificate_sha256") == [SIGNER] and
         value.get("status") == "VERIFIED_OFFICIAL_CANDIDATE_NOT_INSTALLED" and
         value.get("manifest") == {"package": PACKAGE, "version_code": NEW_VERSION,
             "version_name": NEW_NAME, "min_sdk": "24", "target_sdk": "33",
             "native_abis": ["arm64-v8a"]} and
         value.get("apk", {}).get("path") == CANDIDATE_PATH and
         value["apk"].get("bytes") == NEW_BYTES and value["apk"].get("sha256") == NEW_SHA,
         "OFFICIAL_CANDIDATE_NOT_VERIFIED_FOR_EXACT_TARGET")
    commands = value.get("commands")
    need(type(commands) is list and {x.get("name") for x in commands} ==
         {"apksigner", "aapt-badging"} and len(commands) == 2, "VERIFIER_COMMAND_SET_DIFFERS")
    artifacts = []
    for command in commands:
        need(command.get("returncode") == 0 and command.get("joined") is True and
             command.get("timed_out") is False, "VERIFIER_COMMAND_NOT_SUCCESSFUL")
        for stream in ("stdout", "stderr"):
            _, artifact = host.read(VERIFIER_DIR + "/" + command["name"] + "." + stream,
                                    1024 * 1024, pin=command[stream + "_sha256"])
            artifacts.append(artifact)
    return value, {"result": source, "canonical_sha256": VERIFIER_CANONICAL_SHA,
                   "verification_outputs": artifacts}


def preserve_prior_unknown(c, host):
    rows = {}
    for name, (size, digest) in PRIOR_PINS.items():
        raw, row = host.read(PRIOR_BILI_FLOW + "/" + name, 65536, pin=digest)
        need(row["bytes"] == size, "ORIGINAL_BILI_RECEIPT_SIZE_DIFFERS")
        rows[name] = row
        if name == "steps/launch-01/result.json":
            value = c.json_object(raw)
            need(value.get("ok") is False and value.get("action_attempted") is True and
                 value.get("outcome_unknown") is True and
                 value.get("held_binding_released") is True and
                 value.get("action_lock_released") is True, "BILI_UNKNOWN_RECEIPT_DIFFERS")
    for name in ("launch-scope.json", "reconciliations/launch-01.json"):
        need(host.optional(PRIOR_BILI_FLOW + "/" + name, 65536) is None,
             "BILI_UNKNOWN_SCOPE_OR_RECONCILIATION_CHANGED")
    return rows


def snapshot(c, reader, budget):
    raw, pm_source = reader.read(c.PACKAGES_PATH, c.MAX_METADATA)
    projected = c.package_projection(c.parse_xml(raw, budget.check))
    need(PACKAGE in projected and MEITUAN in projected, "SCOPED_PACKAGES_NOT_PRESENT")
    app = projected[PACKAGE]
    need(app["uid"] == UID and app["android_user"] == USER and
         app["package_manager_signing"]["certificate_sha256"] == [SIGNER],
         "INSTALLED_TARGET_UID_OR_SIGNER_DIFFERS")
    names = reader.directory(app["code_path"], lambda name: name.endswith(".apk"))
    need(names == ["base.apk"], "STANDALONE_BASE_APK_SET_REQUIRED")
    _, apk = reader.read(app["code_path"] + "/base.apk", c.MAX_APK, apk=True)
    raw, restrictions_source = reader.read(c.RESTRICTIONS_PATH, c.MAX_METADATA)
    restrictions = c.restrictions_projection(c.parse_xml(raw, budget.check)).get(PACKAGE, {
        "coverage": False, "recorded_fields": {}, "absent_fields_not_defaulted": True})
    permissions, meituan_location, sources = [], [], []
    for path in c.PERMISSION_PATHS:
        observed = reader.optional(path, c.MAX_METADATA)
        if observed is None:
            sources.append({"path": path, "status": "ABSENT"})
            continue
        data, source = observed
        root = c.parse_xml(data, budget.check)
        sources.append(source)
        permissions.append({"source": path, **c.permission_projection(root, PACKAGE, UID)})
        other = c.permission_projection(root, MEITUAN, projected[MEITUAN]["uid"])
        meituan_location.append({"source": path, "coverage": other["coverage"],
            "effective_grant_state": "UNKNOWN", "entries": [x for x in other["entries"]
                if x["name"] in c.LOCATION_PERMISSIONS]})
    return {"target": app, "base_apk": apk, "restrictions": restrictions,
            "permission_observations": permissions,
            "effective_permission_state": "UNKNOWN_SAVED_SOURCES_NOT_LIVE_AUTHORITY",
            "meituan_location_saved_observations": meituan_location,
            "other_original_package_identities": {k: v for k, v in projected.items() if k != PACKAGE},
            "metadata_sources": {"packages": pm_source, "restrictions": restrictions_source,
                                  "permissions": sources}}


def data_identity(c, fd):
    row = c.metadata(fd)
    need(stat.S_ISDIR(row["st_mode"]) and row["st_uid"] == UID, "TARGET_DATA_DIRECTORY_OWNER_DIFFERS")
    return {key.removeprefix("st_"): row[key] for key in
            ("st_dev", "st_ino", "st_uid", "st_gid", "st_mode")}


def bind_data(c, safe_root, held, fds):
    rows = []
    for path in ("/data/user/0/" + PACKAGE, "/data/user_de/0/" + PACKAGE):
        # Original pinned openat2 IN_ROOT resolves Android user-zero aliases
        # safely inside this root; NO_MAGICLINKS rejects procfs escape.
        fd = fds.own(safe_root.open_in_root(held.root_fd, path, os.O_PATH | os.O_DIRECTORY))
        rows.append({"path": path, "identity": data_identity(c, fd), "fd": fd})
    return rows


def recheck_data(c, safe_root, held, fds, rows):
    out = []
    for row in rows:
        need(data_identity(c, row["fd"]) == row["identity"], "HELD_DATA_DIRECTORY_CHANGED")
        current = fds.own(safe_root.open_in_root(held.root_fd, row["path"], os.O_PATH | os.O_DIRECTORY))
        try:
            value = data_identity(c, current)
            need(value == row["identity"], "DATA_DIRECTORY_REPLACED_OR_OWNER_CHANGED")
            out.append({"path": row["path"], "identity": value})
        finally:
            fds.close(current)
    return out


def validate_native_file_metadata(path, value):
    need(path in NATIVE_FILE_METADATA and value == NATIVE_FILE_METADATA[path] and
         stat.S_ISREG(value["st_mode"]) and not value["st_mode"] & 0o022 and
         value["st_nlink"] == 1 and 0 < value["st_size"] <= 32 * 1024 * 1024,
         "NATIVE_EXECUTABLE_BOUND_METADATA_DIFFERS")


def validate_native_parent_identity(path, value):
    need(path in NATIVE_PARENT_IDENTITIES and
         {key: value.get(key) for key in NATIVE_PARENT_IDENTITIES[path]} == NATIVE_PARENT_IDENTITIES[path],
         "NATIVE_PARENT_DIRECTORY_IDENTITY_DIFFERS")


def native_parent_observations(c, host, fds):
    rows = {}
    for path in NATIVE_PARENT_IDENTITIES:
        fd = c.open_beneath(host.root_fd, path, os.O_PATH | os.O_DIRECTORY, fds)
        try:
            value = c.metadata(fd)
            validate_native_parent_identity(path, value)
            rows[path] = {"stat": c.public_metadata(value),
                          "pinned_identity_fields": list(NATIVE_PARENT_IDENTITIES[path])}
        finally:
            fds.close(fd)
    return rows


def native_bind(c, host, baseline, fds, budget):
    rows, handles = {"parent_directories": native_parent_observations(c, host, fds)}, {}
    rows["metadata_evidence"] = {"job_id": "1a1b07a3192-fc05-70bb",
        "original_stdout_sha256": NATIVE_METADATA_EVIDENCE_SHA,
        "bound_to_measured_deployment_stat_tuples": True}
    for path in (CLI_PATH, DAEMON_PATH):
        fd = host.open_file(path)
        handles[path] = fd
        meta = c.metadata(fd)
        validate_native_file_metadata(path, meta)
        row = digest_fd(c, fd, budget, meta["st_size"])
        if path == CLI_PATH:
            need(row["bytes"] == CLI_BYTES and row["sha256"] == CLI_SHA,
                 "OBSERVED_LIVE_NATIVE_CLIENT_BINARY_DIFFERS")
        if path == DAEMON_PATH:
            need(row["bytes"] == DAEMON_BYTES and row["sha256"] == DAEMON_SHA,
                 "OBSERVED_LIVE_DAEMON_BINARY_DIFFERS")
        host.observed[path] = meta
        rows[path] = row
    processes = baseline["all_seven_processes"]["binding"]["processes"]
    matches = [(role, row) for role, row in processes.items() if row.get("executable") == DAEMON_PATH]
    need(len(matches) == 1, "BASELINE_NATIVE_DAEMON_ROLE_NOT_UNIQUE")
    role, daemon = matches[0]
    proc = fds.own(os.open("/proc/" + str(daemon["host_pid"]),
                           os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC))
    live_exe = fds.own(os.open("exe", os.O_RDONLY | os.O_CLOEXEC, dir_fd=proc))
    need(c.metadata(live_exe) == c.metadata(handles[DAEMON_PATH]), "DAEMON_RUNNING_EXE_DIFFERS_FROM_PATH")
    socket_fd = c.open_beneath(host.root_fd, SOCKET_PATH, os.O_PATH, fds)
    socket_identity = c.metadata(socket_fd)
    need(stat.S_ISSOCK(socket_identity["st_mode"]) and socket_identity["st_uid"] == 0,
         "ROOT_NATIVE_CONTROL_SOCKET_REQUIRED")
    rows["daemon_process"] = {"role": role, **daemon}
    rows["caller"] = {"uid": os.getuid(), "euid": os.geteuid(),
        "routing_observation_job": "1a1b0675dba-fc05-7047",
        "root_and_uid1000_same_explicit_socket_returned_Main_host_pid": MAIN_HOST_PID}
    rows["socket"] = {"path": SOCKET_PATH, "stat": c.public_metadata(socket_identity)}
    return handles, rows, socket_identity


def verify_native(c, host, fds, budget, handles, rows, socket_identity):
    native_parent_observations(c, host, fds)
    for path, fd in handles.items():
        validate_native_file_metadata(path, c.metadata(fd))
        need(digest_fd(c, fd, budget, rows[path]["bytes"], rows[path]["sha256"]) == rows[path],
             "HELD_NATIVE_EXECUTABLE_CHANGED")
        host.check_path(path, c.metadata(fd))
    fd = c.open_beneath(host.root_fd, SOCKET_PATH, os.O_PATH, fds)
    try:
        need(c.metadata(fd) == socket_identity, "NATIVE_CONTROL_SOCKET_REPLACED")
    finally:
        fds.close(fd)


def run_command(store, cli_fd, argv, name, seconds, budget, extra_fds=()):
    """One owned client; never signal Main, daemon, or an observed Android PID."""
    budget.check()
    row = {"name": name, "argv": list(argv), "executable": CLI_PATH,
           "execution_from_held_cli_fd": True, "started_utc": now(),
           "automatic_retry": False, "timeout_seconds": seconds,
           "spawned": False, "joined": False, "timed_out": False,
           "group_termination_requested": False, "native_daemon_worker_joined_by_this_client": False}
    proc, error = None, None
    selector, streams = selectors.DefaultSelector(), []
    output = {"stdout": bytearray(), "stderr": bytearray()}
    try:
        proc = subprocess.Popen(argv, executable="/proc/self/fd/" + str(cli_fd),
            pass_fds=(cli_fd, *extra_fds), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, env=ENV, close_fds=True, start_new_session=True)
        row["spawned"] = True
        row["client_pid"] = proc.pid
        streams = [proc.stdout, proc.stderr]
        for stream_name, stream in zip(("stdout", "stderr"), streams):
            os.set_blocking(stream.fileno(), False)
            selector.register(stream, selectors.EVENT_READ, stream_name)
        deadline = min(budget.deadline, time.monotonic() + seconds)
        while selector.get_map():
            remaining = deadline - time.monotonic()
            need(remaining > 0, "NATIVE_CLIENT_TIMEOUT")
            for key, unused in selector.select(min(0.2, remaining)):
                raw = os.read(key.fileobj.fileno(), 65536)
                if not raw:
                    selector.unregister(key.fileobj)
                    continue
                need(len(output[key.data]) + len(raw) <= MAX_OUTPUT, "NATIVE_CLIENT_OUTPUT_BOUND")
                output[key.data].extend(raw)
        proc.wait(timeout=max(0.001, deadline - time.monotonic()))
    except BaseException as failure:
        error = failure
        row["timed_out"] = isinstance(failure, subprocess.TimeoutExpired) or str(failure) == "NATIVE_CLIENT_TIMEOUT"
        if proc is not None and proc.returncode is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
                row["group_termination_requested"] = True
            except ProcessLookupError:
                pass
            except OSError as failure2:
                row["termination_error"] = error_record(failure2)
            try:
                proc.wait(timeout=5)
            except BaseException as failure2:
                row["join_error"] = error_record(failure2)
    finally:
        selector.close()
        for stream in streams:
            stream.close()
        row["joined"] = bool(proc is not None and proc.returncode is not None)
        row["returncode"] = proc.returncode if proc is not None else None
        row["ended_utc"] = now()
        for stream_name, data in output.items():
            row[stream_name] = store.write(name + "." + stream_name, bytes(data))
        if error is not None:
            row["error"] = error_record(error)
        row["output_capture_complete"] = error is None
        store.json(name + ".json", row)
    return bytes(output["stdout"]), row


def checked_response(c, raw, command):
    need(command["spawned"] and command["joined"] and not command["timed_out"] and
         command["returncode"] == 0 and command["output_capture_complete"] and
         "error" not in command, "NATIVE_COMMAND_NOT_SUCCESSFUL")
    response = c.json_object(raw)
    need(response.get("ok") is True and response.get("state") == "running" and
         response.get("host_pid") == MAIN_HOST_PID, "NATIVE_RESPONSE_NOT_BOUND_TO_CURRENT_MAIN")
    return response


def validate_pre(snapshot_value):
    app, apk = snapshot_value["target"], snapshot_value["base_apk"]
    need(app["package"] == PACKAGE and app["uid"] == UID and
         app["version_code"] == OLD_VERSION and app["code_path"] == OLD_CODE_PATH and
         apk["bytes"] == OLD_BYTES and apk["sha256"] == OLD_SHA and
         NEW_VERSION > app["version_code"], "EXACT_OLD_TARGET_OR_MONOTONIC_UPGRADE_REQUIRED")


def validate_post(before, after):
    app, apk = after["target"], after["base_apk"]
    need(app["package"] == PACKAGE and app["uid"] == UID and app["version_code"] == NEW_VERSION and
         app["package_manager_signing"]["certificate_sha256"] == [SIGNER] and
         apk["bytes"] == NEW_BYTES and apk["sha256"] == NEW_SHA,
         "INSTALLED_NEW_VERSION_BYTES_UID_OR_SIGNER_DIFFERS")
    need(before["other_original_package_identities"] == after["other_original_package_identities"],
         "OTHER_ORIGINAL_PACKAGE_IDENTITY_CHANGED")
    need(before["meituan_location_saved_observations"] == after["meituan_location_saved_observations"],
         "MEITUAN_SAVED_LOCATION_OBSERVATION_CHANGED")


def main():
    result = {"schema": "pocket4-independent-ceair-bound-install-v1", "package": PACKAGE,
        "android_user": USER, "uid": UID, "flow": FLOW_PATH, "started_utc": now(),
        "user_authorized_operation": "upgrade_exact_official_CEAir_candidate_preserving_data",
        "automatic_retry": False, "action_attempted": False, "outcome_unknown": False,
        "install_verified": False, "business_ready": False, "production_ready": False,
        "UI_actions": 0, "permission_grant_commands": 0, "App_launches": 0,
        "ADB_commands": 0, "lifecycle_commands": 0, "task_removals": 0,
        "other_package_mutation_requests": 0, "baseline_or_source_contract_modifications": 0,
        "old_bili_unknown_reconciled": False, "errors": [], "commands": []}
    c = fds = budget = host = guard = held = store = lock = None
    native_handles = native_rows = socket_identity = None
    data_rows = None
    try:
        need(len(sys.argv) == 1 and sys.platform.startswith("linux") and
             os.getuid() == os.geteuid() == 0, "ROOT_LINUX_NO_ARGUMENTS_REQUIRED")
        c = load_base()
        fds, budget = c.Descriptors(), c.Budget(seconds=450)
        root_fd = fds.own(os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC))
        host = c.Reader(root_fd, fds, budget)
        lock, result["action_lock_identity"] = acquire_action_lock(c, root_fd, fds)
        host.observed[LOCK_PATH] = c.metadata(lock)
        store = Store(c, root_fd, fds)
        _, result["worker_source"] = host.read(str(Path(__file__).resolve()), 128 * 1024)
        store.json("claim.json", {"schema": "pocket4-one-shot-install-claim-v1", "package": PACKAGE,
            "started_utc": result["started_utc"], "pid": os.getpid(), "automatic_retry": False})
        raw, result["guard_source"] = host.read(c.GUARD_PATH, 65536, pin=c.GUARD_SHA)
        guard = types.ModuleType("pocket4_ceair_pinned_current_guard")
        guard.__file__ = c.GUARD_PATH
        exec(compile(raw, c.GUARD_PATH, "exec"), guard.__dict__)
        result["guard_before"] = c.validate_guard_result(guard.current_guard())
        baseline = guard.current_baseline()
        held = c.HeldAndroidRoot(baseline, fds, budget)
        unused_policy, unused_epoch, safe_root = guard.source_modules()
        result["prior_bili_unknown_pins"] = preserve_prior_unknown(c, host)
        verified, result["official_verifier"] = verifier(c, host)
        candidate_fd = host.open_file(CANDIDATE_PATH)
        candidate_meta = c.metadata(candidate_fd)
        need(candidate_meta == verified["apk"]["stat"], "VERIFIED_CANDIDATE_FILE_IDENTITY_CHANGED")
        result["candidate_source"] = digest_fd(c, candidate_fd, budget, NEW_BYTES, NEW_SHA)
        host.observed[CANDIDATE_PATH] = candidate_meta
        installed_reader = c.Reader(held.root_fd, fds, budget)
        result["before"] = snapshot(c, installed_reader, budget)
        validate_pre(result["before"])
        data_rows = bind_data(c, safe_root, held, fds)
        result["data_before"] = recheck_data(c, safe_root, held, fds, data_rows)
        old_fd = installed_reader.open_file(OLD_CODE_PATH + "/base.apk")
        _, result["preserved_previous_apk"] = store.copy("previous-base.apk", old_fd, OLD_BYTES, OLD_SHA, budget)
        staged_fd, result["private_candidate_apk"] = store.copy("candidate-base.apk", candidate_fd, NEW_BYTES, NEW_SHA, budget)
        native_handles, native_rows, socket_identity = native_bind(c, host, baseline, fds, budget)
        result["native_binding"] = native_rows
        cli_fd = native_handles[CLI_PATH]
        raw, command = run_command(store, cli_fd, (CLI_PATH, "install", "--help"),
                                   "native-install-help", 10, budget)
        result["commands"].append(command)
        need(command["returncode"] == 0 and command["joined"] and
             command["output_capture_complete"] and b"<APK>" in raw and b"--user" in raw,
             "EXISTING_NATIVE_INSTALL_INTERFACE_NOT_CONFIRMED")
        raw, command = run_command(store, cli_fd,
            (CLI_PATH, "--socket", SOCKET_PATH, "--json", "status"), "native-status-before", 15, budget)
        result["commands"].append(command)
        result["native_status_before"] = checked_response(c, raw, command)
        held.verify()
        installed_reader.recheck()
        host.recheck()
        recheck_data(c, safe_root, held, fds, data_rows)
        verify_native(c, host, fds, budget, native_handles, native_rows, socket_identity)
        result["guard_before_install"] = c.validate_guard_result(guard.current_guard())
        need(result["guard_before_install"] == result["guard_before"], "PREINSTALL_MAIN_GUARD_CHANGED")
        store.verify_path()
        scope = {"schema": "pocket4-explicit-CEAir-install-scope-v1", "epoch_sha256": c.EPOCH,
            "baseline_sha256": c.BASELINE_SHA, "qualification_sha256": c.QUALIFICATION_SHA,
            "reader_sha256": BASE_SHA, "worker_source": result["worker_source"],
            "package": PACKAGE, "android_user": USER, "uid": UID,
            "from_version_code": OLD_VERSION, "to_version_code": NEW_VERSION,
            "from_apk_sha256": OLD_SHA, "to_apk_sha256": NEW_SHA,
            "signer_certificate_sha256": SIGNER, "data_directories": result["data_before"],
            "native_artifacts": native_rows, "official_verifier": result["official_verifier"],
            "only_mutation": "native_install_of_held_official_CEAir_APK",
            "UI_admitted": False, "permission_grants_admitted": False,
            "lifecycle_actions_admitted": False, "other_packages_admitted": False,
            "Bili_scope_borrowed": False, "prior_Bili_unknown_retained": True,
            "user_authorization": "existing_explicit_all_App_upgrade_and_new_process_binding_instruction"}
        result["scope"] = store.json("scope.json", scope)
        argv = (CLI_PATH, "--socket", SOCKET_PATH, "--json", "install",
                "/proc/self/fd/" + str(staged_fd), "--user", "0")
        store.json("intent.json", {"scope_sha256": result["scope"]["sha256"], "argv": list(argv),
            "candidate_sha256": NEW_SHA, "committed_utc": now(), "automatic_retry": False,
            "may_have_been_attempted_if_final_receipt_missing": True})
        result["action_attempted"] = True
        result["outcome_unknown"] = True
        raw, command = run_command(store, cli_fd, argv, "native-install", INSTALL_TIMEOUT,
                                   budget, extra_fds=(staged_fd,))
        result["commands"].append(command)
        # Always retain the client response before inspecting a possibly failed
        # operation. A client join is not a claim that the daemon was joined.
        try:
            result["native_install_response"] = checked_response(c, raw, command)
            result["native_install_response_confirmed"] = True
        except BaseException as error:
            result["errors"].append({"stage": "native_install_response", **error_record(error)})
        result["guard_after_command"] = c.validate_guard_result(guard.current_guard(action_attempted=True))
        need(result["guard_after_command"] == result["guard_before"], "POSTINSTALL_MAIN_GUARD_CHANGED")
        held.verify()
        fresh_reader = c.Reader(held.root_fd, fds, budget)
        result["after"] = snapshot(c, fresh_reader, budget)
        result["data_after"] = recheck_data(c, safe_root, held, fds, data_rows)
        fresh_reader.recheck()
        held.verify()
        validate_post(result["before"], result["after"])
        result["new_installed_bytes_readback_verified"] = True
        result["data_directory_identity_retained"] = True
        result["other_original_package_identity_unchanged"] = True
        result["meituan_saved_location_observations_unchanged"] = True
        need(digest_fd(c, staged_fd, budget, NEW_BYTES, NEW_SHA) ==
             {k: result["private_candidate_apk"][k] for k in ("bytes", "sha256", "stat")},
             "PRIVATE_CANDIDATE_CHANGED_AFTER_INSTALL")
    except BaseException as error:
        result["errors"].append({"stage": "operation", **error_record(error)})
    finally:
        if guard is not None:
            try:
                result["guard_after"] = c.validate_guard_result(
                    guard.current_guard(action_attempted=result["action_attempted"]))
                need(result.get("guard_before") == result["guard_after"], "FINAL_MAIN_GUARD_CHANGED")
                if held is not None:
                    held.verify()
                if native_handles is not None:
                    verify_native(c, host, fds, budget, native_handles, native_rows, socket_identity)
                    result["native_artifacts_unchanged"] = True
                host.recheck()
                result["prior_bili_unknown_preserved"] = "prior_bili_unknown_pins" in result
            except BaseException as error:
                result["errors"].append({"stage": "final_guard", **error_record(error)})
        if store is not None:
            try:
                store.verify_path()
            except BaseException as error:
                result["errors"].append({"stage": "flow_path", **error_record(error)})
        # Save a durable pre-release result while both coordinator locks remain
        # held. The final result separately records descriptor/lock release.
        if store is not None:
            try:
                result["ended_utc"] = now()
                store.json("operation-result.json", result)
            except BaseException as error:
                result["errors"].append({"stage": "durable_operation_receipt", **error_record(error)})
        if lock is not None:
            try:
                fcntl.flock(lock, fcntl.LOCK_UN)
                result["action_lock_released"] = True
            except BaseException as error:
                result["errors"].append({"stage": "release_action_lock", **error_record(error)})
        if fds is not None:
            # Retain only the output descriptor until the final receipt is
            # durable; close it explicitly after writing, then emit stdout.
            keep = store.fd if store is not None else None
            for fd in tuple(fds.live):
                if fd != keep:
                    try:
                        fds.close(fd)
                    except BaseException as error:
                        result["errors"].append({"stage": "close_owned_fd", **error_record(error)})
            result["owned_descriptors_before_final_receipt"] = fds.report()
        result["install_verified"] = bool(result.get("native_install_response_confirmed") and
            result.get("new_installed_bytes_readback_verified") and result.get("native_artifacts_unchanged") and
            result.get("data_directory_identity_retained") and result.get("guard_after") and not result["errors"])
        result["outcome_unknown"] = bool(result["action_attempted"] and not result["install_verified"])
        result["status"] = ("CEAIR_UPGRADE_VERIFIED_BUSINESS_QA_PENDING" if result["install_verified"] else
            "INSTALL_OUTCOME_UNKNOWN_NO_AUTOMATIC_RETRY" if result["action_attempted"] else
            "PREINSTALL_REJECTED_NO_INSTALL_REQUEST")
        result["ended_utc"] = now()
        if budget is not None:
            result["elapsed_seconds"] = round(time.monotonic() - budget.started, 6)
        if store is not None:
            try:
                # Store.write only needs its held output directory at this point.
                result["final_receipt"] = store.json("result.json", result)
            except BaseException as error:
                result["errors"].append({"stage": "final_receipt", **error_record(error)})
                result["install_verified"] = False
                result["outcome_unknown"] = result["action_attempted"]
            try:
                fds.close(store.fd)
            except BaseException as error:
                result["errors"].append({"stage": "close_output_directory", **error_record(error)})
        if fds is not None:
            fds.close_remaining()
            result["owned_descriptors_final"] = fds.report()
            if fds.live or fds.close_errors or fds.acquired != fds.closed:
                result["errors"].append({"stage": "final_descriptor_report", "code": "OWNED_DESCRIPTORS_NOT_ALL_CLOSED"})
                result["install_verified"] = False
                result["outcome_unknown"] = result["action_attempted"]
        if result["errors"]:
            result["install_verified"] = False
            result["outcome_unknown"] = result["action_attempted"]
            result["status"] = ("INSTALL_OUTCOME_UNKNOWN_NO_AUTOMATIC_RETRY" if result["action_attempted"] else
                                "PREINSTALL_REJECTED_NO_INSTALL_REQUEST")
        raw = canonical(result)
        need(len(raw) <= MAX_RESULT, "FINAL_STDOUT_BOUND")
        print(raw.decode("ascii"), flush=True)
    return 0 if result["install_verified"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
