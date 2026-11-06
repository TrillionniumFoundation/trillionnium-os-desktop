#!/usr/bin/env python3
"""Stage one immutable generated helper closure for the existing UID1000 build.

Only new source files/directories are created. No existing permissions, Android
state, service, application, or environment variable are modified.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys

sys.dont_write_bytecode = True


def need(ok, code):
    if not ok:
        raise RuntimeError(code)


def read(path, pin=None, maximum=1048576):
    path = Path(path)
    need(path.is_absolute() and path.resolve() == path, "CANONICAL_STAGE_INPUT")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        def meta(s):
            return tuple(getattr(s, k) for k in ("st_dev", "st_ino", "st_mode", "st_nlink", "st_size", "st_uid", "st_gid", "st_mtime_ns", "st_ctime_ns"))
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and 0 < before.st_size <= maximum, "BOUNDED_SOURCE_REQUIRED")
        chunks, count = [], 0
        while count <= maximum:
            block = os.read(fd, min(65536, maximum + 1 - count))
            if not block:
                break
            chunks.append(block)
            count += len(block)
        raw = b"".join(chunks)
        need(count == before.st_size and meta(before) == meta(os.fstat(fd)) == meta(path.lstat()), "STAGE_SOURCE_CHANGED")
        if pin is not None:
            need(hashlib.sha256(raw).hexdigest() == pin, "STAGE_INPUT_HASH_CHANGED")
        return raw
    finally:
        os.close(fd)


def write_new(path, raw):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o400)
    try:
        remaining = memoryview(raw)
        while remaining:
            n = os.write(fd, remaining)
            need(n > 0, "STAGE_WRITE_PROGRESS")
            remaining = remaining[n:]
        os.fchown(fd, 0, 1000)
        os.fchmod(fd, 0o440)
        os.fsync(fd)
    finally:
        os.close(fd)


def stage(source, expected, output):
    need(os.getuid() == os.geteuid() == 0, "ROOT_SOURCE_PUBLICATION_REQUIRED")
    need(re.fullmatch(r"/home/alex/work/pocket4-successor-qa-build-source-[0-9a-f]{32}", str(output)) and
         output.parent.resolve() == output.parent, "NEW_FIXED_BUILD_SOURCE_ROOT")
    original = read(source / "SOURCE_PINS.json", expected, 131072)
    manifest = json.loads(original)
    need(manifest["schema"] == "pocket4-successor-owned-qa-source-v1" and
         manifest["build_performed"] is False and manifest["UI_admitted"] is False and
         manifest["old_helper_qualification_inherited"] is False, "NEW_UNBUILT_HELPER_CLOSURE_REQUIRED")
    files = {}
    for name, row in manifest["files"].items():
        rel = Path(name)
        need(not rel.is_absolute() and ".." not in rel.parts and str(rel) == name, "STAGE_SOURCE_PATH")
        raw = read(source / name, row["sha256"])
        need(len(raw) == row["bytes"], "STAGE_SOURCE_LENGTH")
        files[name] = raw
    need(10 <= len(files) <= 32, "STAGE_SOURCE_COUNT")
    output.mkdir(mode=0o700)
    directories = {output}
    for name, raw in sorted(files.items()):
        path = output / name
        missing = []
        parent = path.parent
        while parent != output:
            missing.append(parent)
            parent = parent.parent
        for directory in reversed(missing):
            if directory not in directories:
                directory.mkdir(mode=0o700)
                directories.add(directory)
        write_new(path, raw)
    write_new(output / "SOURCE_PINS.json", original)
    for directory in sorted(directories, key=lambda p: len(p.parts), reverse=True):
        fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            os.fchown(fd, 0, 1000)
            os.fchmod(fd, 0o550)
            os.fsync(fd)
        finally:
            os.close(fd)
    for name, row in manifest["files"].items():
        need(len(read(output / name, row["sha256"])) == row["bytes"], "STAGED_FILE_READBACK")
    need(read(source / "SOURCE_PINS.json", expected, 131072) == original and
         read(output / "SOURCE_PINS.json", expected, 131072) == original, "FINAL_STAGE_MANIFEST_CHANGED")
    return {"ok": True, "schema": "pocket4-successor-helper-source-stage-v1", "source_manifest_sha256": expected,
            "helper_package": manifest["helper_package"], "output_source": str(output),
            "source_file_count": len(files), "new_source_owner_uid": 0, "new_source_read_group": 1000,
            "UID1000_may_modify_source": False, "build_performed": False, "Android_commands": 0,
            "UI_admitted": False, "production_ready": False}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--stage-once", action="store_true")
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--source-manifest-sha256", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    if not a.stage_once:
        print(json.dumps({"status": "PLAN_ONLY", "Android_commands": 0, "build_performed": False}))
        return 0
    os.umask(0o077)
    try:
        result = stage(a.source, a.source_manifest_sha256, a.output)
    except BaseException as e:
        result = {"ok": False, "type": type(e).__name__, "code": str(e)[:256], "Android_commands": 0, "automatic_retry": False}
    print(json.dumps(result, sort_keys=True), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
