#!/usr/bin/env python3
"""Read exactly two protected run02 logs against the held runtime result. No writes."""
import base64
import gzip
import hashlib
import json
import os
import stat
import sys

BINDINGS = json.loads('{\n  "schema": 1,\n  "authority": {\n    "path": "/run/pocket4-role-authorization-positive-host-run-02-20261105/run01/result.json",\n    "maximum": 131072,\n    "bytes": 11715,\n    "sha256": "bc5c8e59a963828c6c59a8b1cd183e575c8903fbb4efa850369a23666dd1dcd9"\n  },\n  "rows": {\n    "stdout": {\n      "path": "/run/pocket4-role-authorization-positive-host-run-02-20261105/run01/registry.stdout",\n      "maximum": 131072,\n      "expected": {\n        "bytes": 1753,\n        "identity": [\n          28,\n          1300451,\n          33152,\n          1753,\n          1793877932728167237,\n          1793877932728167237\n        ],\n        "path": "/run/pocket4-role-authorization-positive-host-run-02-20261105/run01/registry.stdout",\n        "sha256": "4c07a66ef34850e7189aa3f0be4a61ed98cba6bc888aefe776b1f0672df8aad3"\n      }\n    },\n    "stderr": {\n      "path": "/run/pocket4-role-authorization-positive-host-run-02-20261105/run01/registry.stderr",\n      "maximum": 32768,\n      "expected": {\n        "bytes": 0,\n        "identity": [\n          28,\n          1300452,\n          33152,\n          0,\n          1793877930654150109,\n          1793877930654150109\n        ],\n        "path": "/run/pocket4-role-authorization-positive-host-run-02-20261105/run01/registry.stderr",\n        "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"\n      }\n    }\n  }\n}\n')

def need(value, message):
    if not value:
        raise RuntimeError(message)


def identity(value):
    return {"device": value.st_dev, "inode": value.st_ino, "mode": value.st_mode,
            "uid": value.st_uid, "gid": value.st_gid, "nlink": value.st_nlink,
            "bytes": value.st_size, "mtime_ns": value.st_mtime_ns,
            "ctime_ns": value.st_ctime_ns}


def read_fixed(path, maximum, expected):
    need(os.path.realpath(path, strict=True) == path, "fixed original path is an alias")
    named_before = identity(os.stat(path, follow_symlinks=False))
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        held_before = identity(before)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_gid == 0 and
             before.st_nlink == 1 and before.st_mode & 0o022 == 0 and
             0 <= before.st_size <= maximum, "original type/owner/mode/size differs")
        blocks = []
        remaining = maximum + 1
        while remaining:
            block = os.read(fd, min(32768, remaining))
            if not block:
                break
            blocks.append(block)
            remaining -= len(block)
        raw = b"".join(blocks)
        held_after = identity(os.fstat(fd))
        named_after = identity(os.stat(path, follow_symlinks=False))
        need(named_before == held_before == held_after == named_after and len(raw) == before.st_size,
             "original changed during held read")
        need(len(raw) == expected["bytes"] and hashlib.sha256(raw).hexdigest() == expected["sha256"],
             "original differs from exact runtime pin")
        if "identity" in expected:
            observed = [before.st_dev, before.st_ino, before.st_mode, before.st_size,
                        before.st_mtime_ns, before.st_ctime_ns]
            need(observed == expected["identity"], "original identity differs from actual runtime observation")
        return {"path": path, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                "named_before": named_before, "held_before": held_before,
                "held_after": held_after, "named_after": named_after, "text": raw.decode("utf-8")}
    finally:
        os.close(fd)


def error_record(error):
    return {"type": type(error).__name__, "message": str(error),
            "errno": getattr(error, "errno", None), "filename": getattr(error, "filename", None)}


def main():
    if sys.argv[1:] == []:
        print(json.dumps({"state": "PLAN_ONLY", "fixed_original_logs": 2,
                          "writes": 0, "children_created": 0, "Main_actions": 0}, sort_keys=True))
        return
    need(sys.argv[1:] == ["--collect"], "only fixed original log collection is supported")
    report = {"schema": 1, "state": "FAILED", "files": {}, "errors": [],
              "writes": 0, "children_created": 0, "Main_actions": 0,
              "new_test_execution": False, "runtime_replayed": False}
    try:
        need(os.getuid() == os.geteuid() == 0 and os.getgid() == os.getegid() == 0,
             "root only to read protected original evidence")
        authority = BINDINGS["authority"]
        observed = read_fixed(authority["path"], authority["maximum"], authority)
        parsed = json.loads(observed["text"])
        report["authority_before"] = {k: v for k, v in observed.items() if k != "text"}
        need(set(BINDINGS["rows"]) == {"stdout", "stderr"}, "fixed two log members required")
        for name, row in BINDINGS["rows"].items():
            need(row["expected"] == parsed["execution"][name] and row["path"] == row["expected"]["path"],
                 "log binding differs from actual runtime authority")
            try:
                report["files"][name] = read_fixed(row["path"], row["maximum"], row["expected"])
            except Exception as error:
                report["errors"].append({"file": name, "error": error_record(error)})
        after = read_fixed(authority["path"], authority["maximum"], authority)
        report["authority_after"] = {k: v for k, v in after.items() if k != "text"}
        need(report["authority_before"] == report["authority_after"], "runtime authority changed")
        if not report["errors"] and set(report["files"]) == {"stdout", "stderr"}:
            report["state"] = "ORIGINAL_REGISTRY_LOGS_READ"
    except Exception as error:
        report["errors"].append({"error": error_record(error)})
    encoded = (json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n").encode()
    compressed = gzip.compress(encoded, mtime=0)
    print(json.dumps({"schema": 1, "encoding": "gzip+base64",
                      "uncompressed_bytes": len(encoded),
                      "uncompressed_sha256": hashlib.sha256(encoded).hexdigest(),
                      "compressed_sha256": hashlib.sha256(compressed).hexdigest(),
                      "payload": base64.b64encode(compressed).decode("ascii")}, sort_keys=True))
    raise SystemExit(0 if report["state"] == "ORIGINAL_REGISTRY_LOGS_READ" else 1)


if __name__ == "__main__":
    main()
