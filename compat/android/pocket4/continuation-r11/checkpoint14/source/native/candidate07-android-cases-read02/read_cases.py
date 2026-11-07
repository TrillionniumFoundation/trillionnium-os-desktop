#!/usr/bin/env python3
"""Read sixteen fixed owned signal-case originals; never run or retry a case."""
import base64
import gzip
import hashlib
import json
import os
import stat
import sys

ROOT = "/home/alex/work/pocket4-signal-canary-combined07-9b4f271386ac6d2d"
# This actual result was independently retrieved after the unique runtime terminated.
EXPECTED_RUNTIME_SHA256 = '4e1899db8d0f82a3d80df231f10b09fed644028440a1d77e820e50413c3378d1'
EXPECTED_RUNTIME_BYTES = 30990
CASES = ("r2-svc", "r2-smc-handler", "r2-smc-default", "r3-smc-mask-edit")
SUFFIXES = (("-durable.json", 256 * 1024),
            ("-durable.claim", 16 * 1024),
            ("-instrument.stdout", 256 * 1024),
            ("-instrument-terminal.json", 16 * 1024))
FILES = tuple((label + suffix, maximum) for label in CASES for suffix, maximum in SUFFIXES)


def need(value, message):
    if not value:
        raise RuntimeError(message)


def identity(value):
    return {"device": value.st_dev, "inode": value.st_ino, "mode": value.st_mode,
            "uid": value.st_uid, "gid": value.st_gid, "nlink": value.st_nlink,
            "bytes": value.st_size, "mtime_ns": value.st_mtime_ns,
            "ctime_ns": value.st_ctime_ns}


def read_original(relative, maximum):
    path = ROOT + "/" + relative
    row = {"path": path, "relative": relative, "maximum": maximum}
    fd = None
    try:
        need(os.path.realpath(path, strict=True) == path, "fixed original path is an alias")
        row["named_before"] = identity(os.stat(path, follow_symlinks=False))
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        before = os.fstat(fd)
        row["held_before"] = identity(before)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_gid == 0 and
             before.st_nlink == 1 and before.st_mode & 0o022 == 0 and
             0 < before.st_size <= maximum, "original result type/owner/mode/size differs")
        blocks = []
        remaining = maximum + 1
        while remaining:
            block = os.read(fd, min(32768, remaining))
            if not block:
                break
            blocks.append(block)
            remaining -= len(block)
        raw = b"".join(blocks)
        row["held_after"] = identity(os.fstat(fd))
        row["named_after"] = identity(os.stat(path, follow_symlinks=False))
        need(row["named_before"] == row["held_before"] == row["held_after"] == row["named_after"]
             and len(raw) == before.st_size, "original result changed during the held read")
        row.update(state="ORIGINAL_READ", bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                   text=raw.decode("utf-8"), original_file_modified=False)
    except Exception as error:
        row.update(state="FAILED", error={"type": type(error).__name__, "message": str(error),
                   "errno": getattr(error, "errno", None), "filename": getattr(error, "filename", None)})
    finally:
        if fd is not None:
            os.close(fd)
    return row


def main():
    if sys.argv[1:] == []:
        print(json.dumps({"state": "PLAN_ONLY", "root": ROOT, "fixed_files": FILES,
                          "maximum_original_bytes": sum(n for _, n in FILES),
                          "writes": 0, "children_created": 0, "Main_actions": 0}, sort_keys=True))
        return
    need(sys.argv[1:] == ["--collect"], "only the fixed sixteen-file read is supported")
    report = {"schema": 1, "root": ROOT, "writes": 0, "children_created": 0,
              "Main_actions": 0, "new_test_execution": False, "runtime_admitted": False,
              "maximum_original_bytes": sum(n for _, n in FILES), "files": []}
    code = 1
    try:
        need(os.getuid() == os.geteuid() == 0 and os.getgid() == os.getegid() == 0,
             "root is required only to read the existing root-owned evidence")
        need(isinstance(EXPECTED_RUNTIME_SHA256, str) and len(EXPECTED_RUNTIME_SHA256) == 64 and
             isinstance(EXPECTED_RUNTIME_BYTES, int) and 0 < EXPECTED_RUNTIME_BYTES <= 4 * 1024 * 1024,
             "actual runtime result is not bound; draft collection is forbidden")
        authority = read_original("runtime-result.json", 4 * 1024 * 1024)
        need(authority["state"] == "ORIGINAL_READ", "bound runtime result failed held validation")
        need(authority["sha256"] == EXPECTED_RUNTIME_SHA256 and authority["bytes"] == EXPECTED_RUNTIME_BYTES,
             "actual runtime result differs from the independently retrieved original")
        authority.pop("text")
        report["runtime_result_authority"] = authority
        for relative, maximum in FILES:
            report["files"].append(read_original(relative, maximum))
        need(len(report["files"]) == 16 and all(r["state"] == "ORIGINAL_READ" for r in report["files"]),
             "one or more fixed original case files failed validation")
        report["state"] = "ORIGINAL_ANDROID_CASE_FILES_READ"
        code = 0
    except Exception as error:
        report.update(state="FAILED", error={"type": type(error).__name__, "message": str(error),
                      "errno": getattr(error, "errno", None), "filename": getattr(error, "filename", None)})
    encoded = (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode()
    compressed = gzip.compress(encoded, mtime=0)
    print(json.dumps({"schema": 1, "encoding": "gzip+base64", "uncompressed_bytes": len(encoded),
                      "uncompressed_sha256": hashlib.sha256(encoded).hexdigest(),
                      "compressed_sha256": hashlib.sha256(compressed).hexdigest(),
                      "payload": base64.b64encode(compressed).decode("ascii")}, sort_keys=True))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
