#!/usr/bin/env python3
"""Fixed, metadata-only observations after host input staging was refused."""
import datetime
import json
import os
import stat
import sys

PATHS = (
    "/home/alex/work",
    "/home/alex/work/pocket4-combined07-qualification-inputs-dfcacd6f6da3cf3bdbfcf797f44481c3",
    "/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01",
    "/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/qualification-inputs-dfcacd6f6da3cf3bdbfcf797f44481c3",
)


def metadata(value):
    return {"device": value.st_dev, "inode": value.st_ino,
            "mode": value.st_mode, "mode_octal": oct(stat.S_IMODE(value.st_mode)),
            "uid": value.st_uid, "gid": value.st_gid, "nlink": value.st_nlink,
            "bytes": value.st_size, "mtime_ns": value.st_mtime_ns,
            "ctime_ns": value.st_ctime_ns,
            "directory": stat.S_ISDIR(value.st_mode),
            "symlink": stat.S_ISLNK(value.st_mode)}


def error_value(error):
    return {"type": type(error).__name__, "message": str(error),
            "errno": getattr(error, "errno", None),
            "filename": getattr(error, "filename", None)}


def observe(path):
    row = {"path": path}
    fd = None
    try:
        row["named_before"] = metadata(os.stat(path, follow_symlinks=False))
        row["realpath"] = os.path.realpath(path, strict=True)
        fd = os.open(path, os.O_PATH | os.O_CLOEXEC | os.O_NOFOLLOW)
        row["held_before"] = metadata(os.fstat(fd))
        row["held_after"] = metadata(os.fstat(fd))
        row["named_after"] = metadata(os.stat(path, follow_symlinks=False))
        row["identity_stable"] = (row["named_before"] == row["held_before"] ==
                                   row["held_after"] == row["named_after"])
        row["canonical_path_equal"] = row["realpath"] == path
    except Exception as error:
        row["error"] = error_value(error)
    finally:
        if fd is not None:
            os.close(fd)
    return row


def main():
    plan = {"schema": 1, "state": "PLAN_ONLY", "paths": list(PATHS),
            "writes": 0, "file_content_reads": 0, "recursive_scans": 0,
            "children_created": 0, "Main_actions": 0}
    if sys.argv[1:] == []:
        print(json.dumps(plan, sort_keys=True))
        return
    if sys.argv[1:] != ["--collect"]:
        raise RuntimeError("only the fixed metadata collection is supported")
    plan.update(state="FIXED_METADATA_OBSERVED",
                utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
                caller={"uid": os.getuid(), "euid": os.geteuid(),
                        "gid": os.getgid(), "egid": os.getegid(),
                        "groups": os.getgroups()},
                observations=[observe(path) for path in PATHS],
                staging_or_runtime_admitted=False)
    print(json.dumps(plan, sort_keys=True))


if __name__ == "__main__":
    main()
