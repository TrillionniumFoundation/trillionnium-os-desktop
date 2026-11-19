"""Exact Firefox APK custody, streamed through the held Main descriptor.

This does not collect account data, build/install an APK, or weaken the old
128 MiB helper contract. The only larger body accepted is the selected,
already SDK-qualified Firefox APK. Imports perform no I/O.
"""
import hashlib
import os
from pathlib import PurePosixPath
import re
import stat
import time

PACKAGE = "org.mozilla.firefox"
VERSION_NAME = "160.0.1"
VERSION_CODE = 2016196678
APK_BYTES = 140689915
APK_SHA256 = "283b19f8313e8ce6e8a913bb178ce4a79c5cecd82c49f821de7fafb068c73fcd"
CHUNK_BYTES = 65536
HASH_SECONDS = 45


class Refused(RuntimeError):
    pass


def need(value, message):
    if not value:
        raise Refused(message)


def identity(fd):
    s = os.fstat(fd)
    return {"device": s.st_dev, "inode": s.st_ino, "mode": s.st_mode,
            "uid": s.st_uid, "gid": s.st_gid, "nlink": s.st_nlink,
            "bytes": s.st_size, "mtime_ns": s.st_mtime_ns, "ctime_ns": s.st_ctime_ns}


def canonical_apk_path(path):
    need(type(path) is str and 0 < len(path) <= 1024 and "\0" not in path,
         "EXACT_FIREFOX_INSTALLED_PATH_REQUIRED")
    parts = PurePosixPath(path).parts
    need(str(PurePosixPath(path)) == path and len(parts) == 6
         and parts[:3] == ("/", "data", "app")
         and re.fullmatch(r"~~[A-Za-z0-9_=-]+", parts[3])
         and re.fullmatch(re.escape(PACKAGE) + r"-[A-Za-z0-9_=-]+", parts[4])
         and parts[5] == "base.apk", "ONLY_EXACT_FIREFOX_BASE_APK_PATH")
    return path


def installed_metadata(raw, uid, user):
    need(type(uid) is int and type(user) is int and 0 <= user <= 999
         and uid // 100000 == user and 10000 <= uid % 100000 < 100000,
         "OBSERVED_ANDROID_UID_AND_USER_REQUIRED")
    need(type(raw) is bytes and 0 < len(raw) <= 4096, "PACKAGE_METADATA_BOUND")
    text = raw.decode("ascii", "strict")
    expected = [f"package:{PACKAGE} versionCode:{VERSION_CODE} uid:{uid}\n",
                f"package:{PACKAGE} uid:{uid} versionCode:{VERSION_CODE}\n"]
    need(text in expected, "CURRENT_FIREFOX_PACKAGE_UID_OR_VERSION_CHANGED")
    return {"package": PACKAGE, "uid": uid, "user": user, "version_code": VERSION_CODE}


def installed_path(raw):
    need(type(raw) is bytes and 0 < len(raw) <= 2048, "APK_PATH_OUTPUT_BOUND")
    text = raw.decode("ascii", "strict")
    need(text.endswith("\n") and len(text.splitlines()) == 1 and text.startswith("package:"),
         "ONE_CURRENT_FIREFOX_BASE_APK_REQUIRED")
    return canonical_apk_path(text[8:-1])


def stream_exact_fd(fd, expected, expected_sha256, deadline, *, clock=time.monotonic):
    """Generic read primitive; admission of the expected contract is separate."""
    first = identity(fd)
    need(first == expected and stat.S_ISREG(first["mode"]) and first["nlink"] == 1
         and first["bytes"] > 0, "EXACT_REGULAR_STREAM_IDENTITY_REQUIRED")
    end = min(deadline, clock() + HASH_SECONDS)
    os.lseek(fd, 0, os.SEEK_SET)
    digest = hashlib.sha256()
    count = 0
    while True:
        need(clock() < end, "FIREFOX_STREAM_HASH_DEADLINE")
        block = os.read(fd, min(CHUNK_BYTES, first["bytes"] + 1 - count))
        if not block:
            break
        count += len(block)
        need(count <= first["bytes"], "FIREFOX_APK_GREW")
        digest.update(block)
    need(count == first["bytes"] and digest.hexdigest() == expected_sha256
         and identity(fd) == first, "FIREFOX_COMPLETE_BODY_OR_IDENTITY_CHANGED")
    return {"bytes": count, "sha256": digest.hexdigest(), "stat_file": first,
            "same_fd_streamed": True, "maximum_read_bytes": CHUNK_BYTES,
            "independent_signature_execution": False}


class HeldFirefoxAPK:
    """Keep the hashed fd, recheck its named inode, and hash again on completion.

    `target` is the existing, source-bound HeldTarget from the actual Main;
    callers cannot substitute a host pathname for the guest descriptor API.
    An actual metadata reader must separately bracket each phase with cmd
    package reads. This class grants only installed-byte custody.
    """
    def __init__(self, target, artifact, *, deadline, clock=time.monotonic):
        self.target, self.clock = target, clock
        self.fd = None
        self.closed = False
        self.deadline = deadline
        need(type(deadline) in (int, float) and clock() < deadline,
             "FRESH_ABSOLUTE_CUSTODY_DEADLINE_REQUIRED")
        need(type(artifact) is dict and set(artifact) == {"guest_path", "bytes", "sha256", "stat_file"}
             and artifact["bytes"] == APK_BYTES and artifact["sha256"] == APK_SHA256,
             "ONLY_CURRENT_QUALIFIED_FIREFOX_BODY")
        self.artifact = dict(artifact, stat_file=dict(artifact["stat_file"]))
        self.path = canonical_apk_path(artifact["guest_path"])
        expected = artifact["stat_file"]
        need(set(expected) == {"device", "inode", "mode", "uid", "gid", "nlink", "bytes", "mtime_ns", "ctime_ns"}
             and all(type(v) is int and v >= 0 for v in expected.values())
             and stat.S_ISREG(expected["mode"]) and expected["nlink"] == 1
             and expected["uid"] == expected["gid"] == 1000
             and not expected["mode"] & 0o022 and expected["bytes"] == APK_BYTES,
             "ACTUAL_SINGLE_LINK_INSTALL_FILE_IDENTITY_REQUIRED")
        try:
            target.verify()
            self.fd = target.open_root(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            self.before = self._hash()
            self.verify()
        except BaseException:
            self.close()
            raise

    def _hash(self):
        need(not self.closed and self.fd is not None, "FIREFOX_CUSTODY_CLOSED")
        first = identity(self.fd)
        need(first == self.artifact["stat_file"], "ACTUAL_FIREFOX_INODE_CHANGED")
        observed = stream_exact_fd(self.fd, first, APK_SHA256, self.deadline, clock=self.clock)
        self._named(first)
        return {"guest_path": self.path, **observed}

    def _named(self, expected):
        named = self.target.open_root(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
        try:
            need(identity(named) == expected, "FIREFOX_NAMED_PATH_REPLACED")
        finally:
            os.close(named)

    def verify(self):
        need(not self.closed and self.fd is not None and self.clock() < self.deadline,
             "CURRENT_HELD_FIREFOX_CUSTODY_REQUIRED")
        self.target.verify()
        need(identity(self.fd) == self.artifact["stat_file"], "HELD_FIREFOX_METADATA_CHANGED")
        self._named(self.artifact["stat_file"])

    def revalidate(self):
        self.verify()
        after = self._hash()
        need(after == self.before, "FIREFOX_PHASE_BODY_BOOKEND_CHANGED")
        return after

    def close(self):
        self.closed = True
        if self.fd is not None:
            fd, self.fd = self.fd, None
            os.close(fd)


class CombinedCustody:
    """Use streaming Firefox custody plus the unchanged original helper guard."""
    def __init__(self, original_common, target, identities, deadline):
        targets = [row for row in identities if row.get("metadata", {}).get("package") == PACKAGE]
        helpers = [row for row in identities if row.get("metadata", {}).get("package") != PACKAGE]
        need(len(targets) == 1 and helpers and len(targets[0]["artifacts"]) == 1,
             "EXACT_FIREFOX_AND_REAL_INSTALLED_HELPER_COHORT_REQUIRED")
        self.firefox = self.helpers = None
        row = targets[0]["artifacts"][0]
        try:
            self.firefox = HeldFirefoxAPK(target, {k: row[k] for k in
                ("guest_path", "bytes", "sha256", "stat_file")}, deadline=deadline)
            self.helpers = original_common.HeldArtifacts(target, helpers)
        except BaseException:
            self.close()
            raise

    def verify(self):
        self.firefox.verify()
        self.helpers.verify()

    def revalidate(self):
        a = self.firefox.revalidate()
        b = self.helpers.revalidate()
        return {"firefox": a, "original_helpers": b}

    def close(self):
        first = None
        for obj in (self.helpers, self.firefox):
            if obj is not None:
                try:
                    obj.close()
                except BaseException as error:
                    first = first or error
        if first is not None:
            raise first


class StreamingCommon:
    """A private adapter instance; never patch the original module or its globals."""
    def __init__(self, original, deadline):
        self.original, self.deadline = original, deadline

    def __getattr__(self, name):
        return getattr(self.original, name)

    def HeldArtifacts(self, target, identities):
        return CombinedCustody(self.original, target, identities, self.deadline)
