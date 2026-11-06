#!/usr/bin/env python3
"""Fixed host-only source receipt reader. No Android paths or executable input."""
import base64
import gzip
import hashlib
import json
import os
import stat
import time

ROOT = "/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-native-provider-build-04-20261106/control-source"
FILES = {
    "parent-normal03-framework_build.py": (59292, "03f0b4aecba20149ad7f1301ea823eb5e7e5ba1efa00d08c92c4fa7ecf482132"),
    "actual-work-preparation.json": (11091, "ab286f3939acfeb648a716ca15e5df348fef6b7007eb5651735fe8a7bda96b1c"),
    "actual-native-prebuilt-Android.bp": (1017, "d1eca99403572ee9d481e777febac8d4e062f44fd8844285ffc452b17beb531a"),
    "actual-builder469-result.json": (37384, "a14dde5d3a2e85fe44d90c651527c8c8402d341403ef84a7bc92b93252de72b9"),
    "actual-builder469-qualification.json": (65386, "f31bb31d29967bacdb0842eea99dae65f8b67425f26f10063c3d84099367fd64"),
    "expected-builder469-manifest.json": (97964, "d9340351c9653b10dfd0882afbff5ff4fc11dafaa6083191ed2a8fdb5c8dd934"),
    "prior-framework-inner-terminal.json": (5239, "6a525b9838f43579bc41b1106891f2f734a0c2d92b0c5cc355f7ab02b39eb2a8"),
    "prior-framework-outer-terminal.json": (24689, "273ba8a236253ee3873074a26f568144397044ebcfdd6f153ab8712b29ff70cf"),
    "actual-published-source-manifest.json": (108555, "afb23d210fda970a09482a14b9b38af1c92b5be505edd0eda2b76ce5ffc6067f"),
}
DEADLINE = time.monotonic() + 40
STAT = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns")


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def read_one(name, expected):
    need(time.monotonic() < DEADLINE, "READ_DEADLINE")
    held = []
    try:
        parent = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        held.append(parent)
        for part in ROOT[1:].split("/"):
            parent = os.open(part, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent)
            held.append(parent)
        def meta(fd):
            value = os.fstat(fd)
            return {key: getattr(value, key) for key in STAT}
        fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent)
        held.append(fd)
        before = meta(fd)
        need(stat.S_ISREG(before["st_mode"]) and before["st_nlink"] == 1 and before["st_size"] == expected[0], "FIXED_FILE_SHAPE")
        raw = b""
        while True:
            need(time.monotonic() < DEADLINE, "READ_DEADLINE")
            chunk = os.read(fd, min(32768, expected[0] + 1 - len(raw)))
            if not chunk:
                break
            raw += chunk
            need(len(raw) <= expected[0], "FIXED_FILE_BOUND")
        need(meta(fd) == before and len(raw) == expected[0] and hashlib.sha256(raw).hexdigest() == expected[1], "FIXED_FILE_CHANGED_OR_PIN")
        again = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent)
        held.append(again)
        need(meta(again) == before, "FIXED_PATH_REPLACED")
        return {"name": name, "path": ROOT + "/" + name, "bytes": len(raw), "sha256": expected[1], "stat": before, "text": raw.decode("utf-8", "strict")}
    finally:
        errors = []
        for fd in reversed(held):
            try:
                os.close(fd)
            except BaseException:
                errors.append(fd)
        need(not errors, "READ_FD_CLOSE_FAILED")


def main():
    need(os.getuid() == 1000 and os.geteuid() == 1000, "OPERATOR_UID_REQUIRED")
    rows = [read_one(name, pin) for name, pin in FILES.items()]
    payload = (json.dumps({"schema": "normal04-fixed-input-recovery-v1", "files": rows}, ensure_ascii=False, separators=(",", ":")) + "\n").encode()
    encoded = base64.b64encode(gzip.compress(payload, mtime=0)).decode("ascii")
    print(json.dumps({"schema": "normal04-fixed-input-recovery-envelope-v1", "files": len(rows), "payload_bytes": len(payload),
                      "payload_sha256": hashlib.sha256(payload).hexdigest(), "encoding": "gzip+base64", "payload": encoded,
                      "Android_reads": 0, "Main_lock_or_fds": 0, "file_writes": 0, "subprocesses": 0, "builder_started": False,
                      "automatic_retry": False}, separators=(",", ":")), flush=True)


if __name__ == "__main__":
    main()
