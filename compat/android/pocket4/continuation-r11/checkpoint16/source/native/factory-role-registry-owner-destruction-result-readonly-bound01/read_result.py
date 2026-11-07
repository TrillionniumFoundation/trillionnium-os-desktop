#!/usr/bin/env python3
"""Read one fixed root-owned snapshot result, bound only after its actual terminal."""
import base64
import gzip
import hashlib
import json
import os
import stat
import sys

PATH = "/run/pocket4-registry-owner-destruction-host-run-01-20261105/run01/result.json"
MAXIMUM = 131072
EXPECTED_BYTES = 14960
EXPECTED_SHA256 = "e30bd4e0e1451a10ace755c235755b57d1fd630c74d99a4a9cd95a6b63e70afb"


def need(value, message):
    if not value:
        raise RuntimeError(message)


def identity(value):
    return {"device": value.st_dev, "inode": value.st_ino, "mode": value.st_mode,
            "uid": value.st_uid, "gid": value.st_gid, "nlink": value.st_nlink,
            "bytes": value.st_size, "mtime_ns": value.st_mtime_ns,
            "ctime_ns": value.st_ctime_ns}


def main():
    if sys.argv[1:] == []:
        print(json.dumps({"state": "PLAN_ONLY", "path": PATH, "maximum": MAXIMUM,
                          "writes": 0, "children_created": 0, "Main_actions": 0}, sort_keys=True))
        return
    need(sys.argv[1:] == ["--collect"], "only the fixed single-file read is supported")
    fd = None
    report = {"schema": 1, "path": PATH, "maximum": MAXIMUM, "writes": 0,
              "children_created": 0, "Main_actions": 0, "new_test_execution": False}
    code = 1
    try:
        need(os.getuid() == os.geteuid() == 0 and os.getgid() == os.getegid() == 0,
             "root is required only to read the existing root-owned evidence")
        need(os.path.realpath(PATH, strict=True) == PATH, "fixed original path is an alias")
        report["named_before"] = identity(os.stat(PATH, follow_symlinks=False))
        fd = os.open(PATH, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        before = os.fstat(fd)
        report["held_before"] = identity(before)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_gid == 0 and
             before.st_nlink == 1 and before.st_mode & 0o022 == 0 and
             0 < before.st_size <= MAXIMUM, "original result type/owner/mode/size differs")
        blocks = []
        remaining = MAXIMUM + 1
        while remaining:
            block = os.read(fd, min(32768, remaining))
            if not block:
                break
            blocks.append(block)
            remaining -= len(block)
        raw = b"".join(blocks)
        report["held_after"] = identity(os.fstat(fd))
        report["named_after"] = identity(os.stat(PATH, follow_symlinks=False))
        need(report["named_before"] == report["held_before"] ==
             report["held_after"] == report["named_after"] and len(raw) == before.st_size,
             "original result changed during the held read")
        need(len(raw) == EXPECTED_BYTES and hashlib.sha256(raw).hexdigest() == EXPECTED_SHA256,
             "original snapshot result differs from the actual terminal pin")
        report.update(state="ORIGINAL_SNAPSHOT_RESULT_READ", bytes=len(raw),
                      sha256=hashlib.sha256(raw).hexdigest(), text=raw.decode("utf-8"),
                      original_file_modified=False, runtime_admitted=False)
        code = 0
    except Exception as error:
        report.update(state="FAILED", error={"type": type(error).__name__,
            "message": str(error), "errno": getattr(error, "errno", None),
            "filename": getattr(error, "filename", None)})
    finally:
        if fd is not None:
            os.close(fd)
    encoded = (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode()
    compressed = gzip.compress(encoded, mtime=0)
    print(json.dumps({"schema": 1, "encoding": "gzip+base64",
                      "uncompressed_bytes": len(encoded),
                      "uncompressed_sha256": hashlib.sha256(encoded).hexdigest(),
                      "compressed_sha256": hashlib.sha256(compressed).hexdigest(),
                      "payload": base64.b64encode(compressed).decode("ascii")}, sort_keys=True))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
