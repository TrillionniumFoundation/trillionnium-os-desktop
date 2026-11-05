#!/usr/bin/env python3
"""Bounded read-only memory observation of fixed files and this task's scopes."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import time

PREFIX = "/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/"
SCOPES = [
    {"job": "1a1a995794e-fc05-3625", "role": "nofile_Android_matching_build01",
     "path_authority": "actual matching Android coordinator before/after receipt",
     "receipt_sha256": "f3617407f8c624357f4bf9a9cc53e1e78a217b3c0b8bc9a51448c09569e2ea06"},
]
FIELDS = ("cgroup.procs", "cgroup.events", "memory.current", "memory.stat",
          "memory.swap.current", "memory.events", "memory.peak", "memory.swap.peak",
          "memory.max", "memory.high", "memory.swap.max")
DEADLINE = time.monotonic() + 24

def utc():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def identity(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns]

def error_value(error):
    return {"type": type(error).__name__, "message": str(error),
            "errno": getattr(error, "errno", None),
            "filename": getattr(error, "filename", None)}

def read_one(path, directory_fd=None):
    fd = -1
    row = {"path": str(path), "observed_utc": utc()}
    try:
        if time.monotonic() >= DEADLINE:
            raise TimeoutError("fixed observation deadline exhausted")
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                     dir_fd=directory_fd)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise RuntimeError("fixed observed object is not a regular proc/cgroup file")
        raw = os.read(fd, 32769)
        if len(raw) > 32768:
            raise RuntimeError("fixed file exceeded the 32768-byte bound")
        after = os.fstat(fd)
        named = os.stat(path, dir_fd=directory_fd, follow_symlinks=False)
        if identity(before) != identity(after) or identity(after) != identity(named):
            raise RuntimeError("fixed file identity changed during read")
        row.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                   identity=identity(before), text=raw.decode("ascii"),
                   complete=True)
    except Exception as error:
        row.update(complete=False, error=error_value(error))
    finally:
        if fd >= 0:
            os.close(fd)
    return row

def observe_scope(scope):
    path = Path(PREFIX + "hepta-runtime-job-" + scope["job"] + ".service")
    row = dict(scope, path=str(path), started_utc=utc())
    fd = -1
    try:
        for parent in (path, *path.parents):
            if not stat.S_ISDIR(parent.lstat().st_mode):
                raise RuntimeError("fixed scope path aliases a non-directory")
        fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
        before = os.fstat(fd)
        row["held_directory_identity"] = [before.st_dev, before.st_ino]
        row["files"] = {name: read_one(name, fd) for name in FIELDS}
        after = os.fstat(fd)
        named = path.lstat()
        row["directory_identity_stable"] = (
            (before.st_dev, before.st_ino, before.st_mode) ==
            (after.st_dev, after.st_ino, after.st_mode) ==
            (named.st_dev, named.st_ino, named.st_mode))
        row["all_fixed_fields_read"] = all(item["complete"] for item in row["files"].values())
    except Exception as error:
        row["error"] = error_value(error)
    finally:
        if fd >= 0:
            os.close(fd)
    row["finished_utc"] = utc()
    return row

def main():
    if os.getuid() != 1000 or os.geteuid() != 1000:
        raise RuntimeError("fixed collector requires ordinary operator UID1000")
    result = {"schema": 1, "started_utc": utc(),
              "scope": "fixed memory files and one explicitly owned Android-build job scope only",
              "source_execution": False, "process_scan": False,
              "files_written": 0, "resource_or_policy_changes": 0,
              "stop_or_kill_actions": 0, "Main_actions": 0,
              "snapshots_atomic_across_files": False,
              "missing_retired_scope_is_retained_as_observation_error": True}
    result["files"] = {name: read_one(name) for name in (
        "/proc/meminfo", "/proc/pressure/memory")}
    result["owned_scopes"] = [observe_scope(scope) for scope in SCOPES]
    result["finished_utc"] = utc()
    result["fixed_collection_completed"] = True
    print(json.dumps(result, sort_keys=True), flush=True)

if __name__ == "__main__":
    main()
