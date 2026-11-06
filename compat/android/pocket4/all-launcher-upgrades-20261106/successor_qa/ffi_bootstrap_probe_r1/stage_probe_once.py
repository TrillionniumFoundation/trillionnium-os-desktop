#!/usr/bin/env python3
"""Stage the exact host-only probe in one new root-private directory, once."""
import hashlib
import json
import os
from pathlib import Path
import stat
import sys

SOURCE_BYTES = 18199
SOURCE_SHA = "c7fc2c4a9397d861e27f257e3e0788cd76f7867f006d1b873b2916303b35ce82"
ROOT = "/home/alex/work/pocket4-ffi-bootstrap-probe-20261106-r1"
STAT_KEYS = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
             "st_size", "st_mtime_ns", "st_ctime_ns")


def require(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def write_new(directory, name, data):
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                 0o600, dir_fd=directory)
    try:
        view = memoryview(data)
        while view:
            count = os.write(fd, view)
            require(count > 0, "WRITE_PROGRESS")
            view = view[count:]
        os.fchmod(fd, 0o400)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(directory)


def readback(directory, name):
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                 dir_fd=directory)
    try:
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1 and
                stat.S_IMODE(before.st_mode) == 0o400 and before.st_size == SOURCE_BYTES,
                "STAGED_ROOT_FILE_IDENTITY")
        body = bytearray()
        while len(body) <= SOURCE_BYTES:
            part = os.read(fd, min(65536, SOURCE_BYTES + 1 - len(body)))
            if not part:
                break
            body.extend(part)
        again = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
        try:
            require(len(body) == SOURCE_BYTES and sha(body) == SOURCE_SHA and
                    all(getattr(before, key) == getattr(os.fstat(fd), key) ==
                        getattr(os.fstat(again), key) for key in STAT_KEYS), "STAGED_SOURCE_OR_PATH_CHANGED")
        finally:
            os.close(again)
        return bytes(body)
    finally:
        os.close(fd)


def main():
    require(os.getuid() == os.geteuid() == 0, "ACTUAL_EXISTING_HOST_ROOT_REQUIRED")
    os.umask(0o077)
    before_count = len(os.listdir("/proc/self/fd"))
    raw = sys.stdin.buffer.read(262145)
    require(0 < len(raw) <= 262144, "BOUNDED_SOURCE_PAYLOAD")
    payload = json.loads(raw)
    require(set(payload) == {"schema", "source_text"} and
            payload["schema"] == "pocket4-ffi-bootstrap-probe-stage-input-v1", "CLOSED_STAGE_PAYLOAD")
    source = payload["source_text"].encode("utf-8")
    require(len(source) == SOURCE_BYTES and sha(source) == SOURCE_SHA, "EXACT_REVIEWED_SOURCE")
    path = ROOT + "/probe_ffi_bootstrap.py"
    compile(source, path, "exec")
    owned = []
    try:
        parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        owned.append(parent)
        for name in ("home", "alex", "work"):
            parent = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                             dir_fd=parent)
            owned.append(parent)
        leaf = Path(ROOT).name
        os.mkdir(leaf, 0o700, dir_fd=parent)
        os.fsync(parent)
        directory = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                            dir_fd=parent)
        owned.append(directory)
        meta = os.fstat(directory)
        require(meta.st_uid == 0 and stat.S_IMODE(meta.st_mode) == 0o700, "NEW_ROOT_PRIVATE_STAGE_REQUIRED")
        write_new(directory, "probe_ffi_bootstrap.py", source)
        source = readback(directory, "probe_ffi_bootstrap.py")
        current = os.open(leaf, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                          dir_fd=parent)
        owned.append(current)
        require(all(getattr(meta, key) == getattr(os.fstat(current), key)
                    for key in ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid")), "STAGE_PATH_CHANGED")
    finally:
        failed = []
        for fd in reversed(owned):
            try:
                os.close(fd)
            except OSError:
                failed.append(fd)
        require(not failed, "BOOTSTRAP_FD_CLOSE_FAILED")
    require(len(os.listdir("/proc/self/fd")) == before_count, "BOOTSTRAP_DESCRIPTOR_DIFFERENCE")
    print(json.dumps({"schema": "pocket4-ffi-bootstrap-probe-stage-v1",
                      "source": {"path": path, "bytes": SOURCE_BYTES, "sha256": SOURCE_SHA},
                      "bootstrap_FDs_before": before_count, "bootstrap_FDs_after": before_count,
                      "Main_actions": 0, "probe_not_yet_invoked": True, "automatic_retry": False},
                     sort_keys=True), flush=True)
    sys.argv = [path, "--host-only"]
    exec(compile(source, path, "exec"), {"__name__": "__main__", "__file__": path})


if __name__ == "__main__":
    main()
