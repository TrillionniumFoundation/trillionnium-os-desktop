#!/usr/bin/python3.14
"""Read-only proof of the real, fresh GDM greeter's environment writer.

This is installed only by the isolated qualification fixture. It has no CLI
paths, account overrides, write operations, or root observation capability.
Acceptance must bind the one JSON record to journald's trusted boot, UID,
user-unit and invocation fields; a payload or SyslogIdentifier alone is not
evidence of a systemd invocation.
"""

import grp
import hashlib
import json
import os
import pwd
import re
import stat
import sys
import time

SCHEMA = "droidloom.fixture-gdm-greeter-proof.v1"
UNIT = "droidloom-fixture-greeter-proof.service"
MIN_UID, MAX_UID = 60578, 60705
FILE_GID = 65534
MAX_BYTES = 65536
WAIT_SECONDS = 8.0
REQUIRED_KEYS = ("USER", "LOGNAME", "HOME", "GDM_SEAT_ID")


class Rejected(Exception):
    """Only fixed, non-content error codes may leave the verifier."""


def require(value, code):
    if not value:
        raise Rejected(code)


def identity():
    uids, gids = os.getresuid(), os.getresgid()
    uid = uids[0]
    require(MIN_UID <= uid <= MAX_UID and uids == (uid, uid, uid), "not-dynamic-greeter-uid")
    session_gid = grp.getgrnam("gdm").gr_gid
    require(1 <= session_gid < 1000, "selected-gdm-group-mismatch")
    require(gids == (session_gid, session_gid, session_gid), "not-dynamic-greeter-gid")
    record = pwd.getpwuid(uid)
    name = record.pw_name
    # This is GDM 50.1's source-owned greeter name and bounded collision suffix.
    suffix = name.removeprefix("gdm-greeter-")
    require(name == "gdm-greeter" or (
        name.startswith("gdm-greeter-") and suffix.isascii() and suffix.isdecimal()
        and str(int(suffix)) == suffix and 2 <= int(suffix) <= 128
    ), "wrong-dynamic-account-name")
    home = "/run/gdm3/home/" + name
    require(record.pw_uid == uid and record.pw_gid == session_gid and record.pw_dir == home,
            "dynamic-account-record-mismatch")
    require(os.environ.get("HOME") == home, "user-manager-home-mismatch")
    invocation = os.environ.get("INVOCATION_ID", "")
    require(re.fullmatch(r"[0-9a-f]{32}", invocation) is not None
            and invocation != "0" * 32, "missing-user-unit-invocation")
    return uid, session_gid, name, home, invocation


def file_identity(value):
    return (value.st_dev, value.st_ino, value.st_mode, value.st_uid,
            value.st_gid, value.st_nlink, value.st_size,
            value.st_mtime_ns, value.st_ctime_ns)


def directory_identity(value):
    # Other normal greeter programs may create siblings. Their directory
    # mtime/size changes are not substitution of the held directory inode.
    return (value.st_dev, value.st_ino, value.st_mode,
            value.st_uid, value.st_gid)


def check_directory(fd, uid, private):
    value = os.fstat(fd)
    require(stat.S_ISDIR(value.st_mode), "non-directory-parent")
    if private:
        require(value.st_uid == uid and value.st_gid == FILE_GID
                and stat.S_IMODE(value.st_mode) == 0o700, "private-directory-metadata")
    else:
        require(value.st_uid == 0 and value.st_mode & 0o022 == 0,
                "untrusted-fixed-parent")
    return directory_identity(value)


def validate_body(data, name, home):
    require(0 < len(data) <= MAX_BYTES and data.endswith(b"\n")
            and b"\x00" not in data and b"\r" not in data, "environment-format")
    try:
        text = data.decode("utf-8", "strict")
    except UnicodeDecodeError:
        raise Rejected("environment-encoding") from None
    values = {}
    for line in text[:-1].split("\n"):
        key, separator, value = line.partition("=")
        require(separator and re.fullmatch(r"[A-Z_][A-Z0-9_]*", key)
                and key not in values, "environment-key-format")
        values[key] = value
    expected = {"USER": name, "LOGNAME": name, "HOME": home, "GDM_SEAT_ID": "seat0"}
    require(all(values.get(key) == value for key, value in expected.items()),
            "environment-required-field-mismatch")
    return hashlib.sha256(data).hexdigest()


def observe(root_fd, uid, name, home):
    """All path choices below are source-owned, relative to a held root FD.

    The root-FD parameter permits a private-tree regression without touching
    host /run. The executable always supplies its actual literal / directory.
    """
    chain, owned_fds = [], []
    leaf = None
    try:
        parent = os.dup(root_fd)
        owned_fds.append(parent)
        chain.append((parent, None, check_directory(parent, uid, False)))
        for index, component in enumerate(("run", "gdm3", "home", name, ".config", "environment.d")):
            opened = os.open(component, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                             dir_fd=parent)
            owned_fds.append(opened)
            chain.append((opened, component, check_directory(opened, uid, index >= 3)))
            parent = opened
        # NONBLOCK prevents a substituted FIFO from hanging before fstat.
        leaf = os.open("gdm.conf", os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK,
                       dir_fd=parent)
        before = os.fstat(leaf)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                and before.st_uid == uid and before.st_gid == FILE_GID
                and stat.S_IMODE(before.st_mode) == 0o600
                and 0 < before.st_size <= MAX_BYTES, "environment-file-metadata")
        chunks, total = [], 0
        while True:
            chunk = os.read(leaf, min(8192, MAX_BYTES + 1 - total))
            if not chunk:
                break
            chunks.append(chunk)
            total += len(chunk)
            require(total <= MAX_BYTES, "environment-file-too-large")
        data = b"".join(chunks)
        digest = validate_body(data, name, home)
        require(total == before.st_size and file_identity(os.fstat(leaf)) == file_identity(before),
                "environment-file-changed")
        path_leaf = os.stat("gdm.conf", dir_fd=parent, follow_symlinks=False)
        require(file_identity(path_leaf) == file_identity(before), "environment-leaf-replaced")
        for index, (fd, component, original) in enumerate(chain):
            require(check_directory(fd, uid, index >= 4) == original, "parent-metadata-changed")
            if index:
                visible = os.stat(component, dir_fd=chain[index - 1][0], follow_symlinks=False)
                require(directory_identity(visible) == original, "parent-inode-replaced")
        return {"file_bytes": total, "file_sha256": digest,
                "file_device": before.st_dev, "file_inode": before.st_ino,
                "file_owner_uid": uid, "file_owner_gid": FILE_GID,
                "file_mode": "0600", "private_directory_mode": "0700",
                "checked_environment_fields": list(REQUIRED_KEYS),
                "source_body_emitted": False}
    finally:
        if leaf is not None:
            os.close(leaf)
        for fd in reversed(owned_fds):
            os.close(fd)


def run():
    start = time.monotonic_ns()
    require(len(sys.argv) == 1 and sys.flags.isolated and sys.dont_write_bytecode,
            "non-fixed-invocation")
    uid, session_gid, name, home, invocation = identity()
    deadline = time.monotonic() + WAIT_SECONDS
    root = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        while True:
            try:
                result = observe(root, uid, name, home)
                break
            except FileNotFoundError:
                # The normal user manager can begin while PAM/session setup
                # is completing. Missing files are the only retry condition.
                require(time.monotonic() < deadline, "environment-not-created-before-deadline")
                time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
        require(time.monotonic() <= deadline, "proof-deadline-exceeded")
        # Bind the observation to the same actual IDs/NSS record and manager
        # invocation, not only to environment strings checked at entry.
        require(identity() == (uid, session_gid, name, home, invocation), "identity-changed")
        return {"schema": SCHEMA, "result": "passed", "uid": uid, "gid": session_gid,
                "pid": os.getpid(), "unit": UNIT, "invocation_id": invocation,
                "guest_clock": "CLOCK_MONOTONIC", "guest_monotonic_ns_start": start,
                "guest_monotonic_ns_end": time.monotonic_ns(),
                "requires_trusted_journal_identity": True, **result}
    finally:
        os.close(root)


def main():
    try:
        result = run()
    except Rejected as error:
        result = {"schema": SCHEMA, "result": "failed", "reason": str(error)}
    except OSError as error:
        result = {"schema": SCHEMA, "result": "failed", "reason": "os-error", "errno": error.errno}
    except (KeyError, ValueError):
        result = {"schema": SCHEMA, "result": "failed", "reason": "identity-record-error"}
    except Exception:
        result = {"schema": SCHEMA, "result": "failed", "reason": "internal-error"}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")), flush=True)
    return 0 if result["result"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
