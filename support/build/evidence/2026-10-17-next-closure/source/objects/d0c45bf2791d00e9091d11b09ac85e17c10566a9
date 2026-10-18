#!/usr/bin/env python3
"""Remove a captured owned manifest while preserving concurrent replacements.

The inherited regular-file descriptor pins the owned inode. The public pathname
is moved into fresh private custody before its identity is inspected. A foreign
entry is restored without overwriting any newer public entry, or retained for
recovery. This does not guarantee continuous occupancy of the public pathname.
"""
import argparse
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import stat
import sys
import tempfile


def capture_candidate(manifest, candidate):
    """Atomically capture the current public entry without a preceding stat."""
    os.rename(manifest, candidate)


def restore_no_replace(candidate, manifest):
    """Restore atomically; unavailable renameat2 is an error, never a fallback."""
    libc = ctypes.CDLL(None, use_errno=True)
    try:
        renameat2 = libc.renameat2
    except AttributeError as error:
        raise OSError(errno.ENOSYS, "renameat2(RENAME_NOREPLACE) is unavailable") from error
    renameat2.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    renameat2.restype = ctypes.c_int
    result = renameat2(-100, os.fsencode(candidate), -100, os.fsencode(manifest), 1)
    if result != 0:
        number = ctypes.get_errno()
        raise OSError(number, os.strerror(number), os.fspath(manifest))


def entry_record(info):
    kind = ("regular" if stat.S_ISREG(info.st_mode) else
            "symlink" if stat.S_ISLNK(info.st_mode) else
            "directory" if stat.S_ISDIR(info.st_mode) else "other")
    return {"device": info.st_dev, "inode": info.st_ino,
            "mode": format(info.st_mode, "06o"), "type": kind}


def failed(record, outcome, error, retained_path=None):
    record.update(passed=False, outcome=outcome, error=f"{type(error).__name__}: {error}")
    if isinstance(error, OSError):
        record["errno"] = error.errno
    if retained_path is not None:
        record["retained_path"] = os.fspath(retained_path)
    return record


def clean_manifest(manifest, owned_fd):
    """Return a result record; callers use passed to select the exit status."""
    manifest = Path(manifest)
    record = {"schema": 1, "manifest": os.fspath(manifest), "owned_fd": owned_fd,
              "passed": False, "outcome": "not_started",
              "continuous_public_path_occupancy_guaranteed": False}
    try:
        if not manifest.is_absolute() or manifest.name in ("", ".", "..") or ".." in manifest.parts:
            raise ValueError("manifest must be an absolute path naming one directory entry")
        anchor = os.fstat(owned_fd)
        if not stat.S_ISREG(anchor.st_mode):
            raise ValueError("owned descriptor must pin a regular manifest inode")
        record["anchor"] = entry_record(anchor)
    except (Exception, KeyboardInterrupt) as error:
        return failed(record, "invalid_anchor_or_path", error)

    try:
        custody = Path(tempfile.mkdtemp(prefix=".a01-manifest-custody-", dir=manifest.parent))
        record["custody"] = os.fspath(custody)
        candidate = custody / "manifest"
        record["candidate"] = os.fspath(candidate)
        os.chmod(custody, 0o700)
    except (Exception, KeyboardInterrupt) as error:
        return failed(record, "custody_creation_failed", error, record.get("custody"))

    try:
        capture_candidate(manifest, candidate)
    except FileNotFoundError:
        try:
            os.rmdir(custody)
        except (Exception, KeyboardInterrupt) as error:
            return failed(record, "absent_custody_cleanup_failed", error, custody)
        record.update(passed=True, outcome="absent", custody_removed=True)
        return record
    except (Exception, KeyboardInterrupt) as error:
        # Do not attempt recursive cleanup or unlink an entry after an uncertain
        # capture. The custody path is kept for inspection, even if empty.
        return failed(record, "capture_failed", error, custody)

    try:
        captured = os.lstat(candidate)
        record["captured"] = entry_record(captured)
    except (Exception, KeyboardInterrupt) as error:
        return failed(record, "captured_entry_inspection_failed", error, custody)

    matching = (stat.S_ISREG(captured.st_mode)
                and (captured.st_dev, captured.st_ino) == (anchor.st_dev, anchor.st_ino))
    if matching:
        try:
            os.unlink(candidate)
        except (Exception, KeyboardInterrupt) as error:
            return failed(record, "owned_remove_failed", error, candidate)
        try:
            os.rmdir(custody)
        except (Exception, KeyboardInterrupt) as error:
            return failed(record, "owned_removed_custody_cleanup_failed", error, custody)
        record.update(passed=True, outcome="owned_removed", custody_removed=True)
        return record

    try:
        restore_no_replace(candidate, manifest)
    except (Exception, KeyboardInterrupt) as error:
        # EEXIST, ENOSYS and every other restoration error preserve the captured
        # foreign entry. Never fall back to replacing the public pathname.
        return failed(record, "foreign_retained", error, candidate)
    try:
        os.rmdir(custody)
    except (Exception, KeyboardInterrupt) as error:
        return failed(record, "foreign_restored_custody_cleanup_failed", error, custody)
    record.update(passed=True, outcome="foreign_restored", custody_removed=True)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--owned-fd", type=int, required=True)
    arguments = parser.parse_args()
    helper_file = Path(__file__).resolve()
    try:
        helper_sha256 = hashlib.sha256(helper_file.read_bytes()).hexdigest()
    except OSError as error:
        print(f"cannot record manifest cleanup helper source: {error}", file=sys.stderr)
        return 1
    record = clean_manifest(arguments.manifest, arguments.owned_fd)
    record.update(helper_file=os.fspath(helper_file), helper_sha256=helper_sha256)
    print(json.dumps(record, sort_keys=True))
    if not record["passed"]:
        message = f"manifest cleanup failed ({record['outcome']}): {record.get('error', 'unknown error')}"
        if "retained_path" in record:
            message += f"; retained for recovery: {record['retained_path']}"
        print(message, file=sys.stderr)
    return int(not record["passed"])


if __name__ == "__main__":
    raise SystemExit(main())
