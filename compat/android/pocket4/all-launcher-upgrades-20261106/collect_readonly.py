#!/usr/bin/env python3
"""Read-only inventory for the eight original Pocket4 Apps; no device actions.

Run with python3 -B -I. No arguments, shell, subprocess, network, namespace entry,
settings change, permission grant, install, restart, or file-output entry exists.
The pinned current guard admits identity observations only. This script does not
turn that qualification into UI/install or whole-App production qualification.

ABX0 protocol sources inspected before implementation (AOSP, Apache-2.0):
https://android.googlesource.com/platform/frameworks/libs/modules-utils/+/refs/heads/main/java/com/android/modules/utils/BinaryXmlSerializer.java
https://android.googlesource.com/platform/prebuilts/fullsdk/sources/+/88c7ff1cd72d6305ec59f97aadc2198cc2dc3592/android-34/com/android/modules/utils/BinaryXmlPullParser.java
https://android.googlesource.com/platform/frameworks/libs/modules-utils/+/a7b03ede3ec19ec0b5621efa2a2b2300465d74e0/java/com/android/modules/utils/FastDataInput.java
https://android.googlesource.com/platform/frameworks/base/+/3fb46661abbb2802602ec6be1620cc01c7b2034c/services/permission/java/com/android/server/permission/access/permission/AppIdPermissionPersistence.kt

This is an independently implemented bounded reader, not Android's parser.
It deliberately requires a complete document and rejects entity/DTD/PI events.
Raw permission flags are observations, not a grant-policy interpreter.
"""
import sys
sys.dont_write_bytecode = True

import collections
import contextlib
import errno
import hashlib
import json
import math
import os
import re
import signal
import stat
import struct
import time
import types
import xml.parsers.expat

GUARD_PATH = "/home/alex/work/pocket4-main-current-baseline-01/current_baseline_guard.py"
GUARD_SHA = "0ee54ef97c073857609aedb4670395db084ceacc7d28558315647ab2ffbef679"
EPOCH = "734fab42fa57e7289a5a88c24d3d4e00e9326d74fefbe523d1c280e0e6d38bc2"
QUALIFICATION_SHA = "f37b2eb00db80c398c9a4f9fd895628b6c7ecc827ccf9699c2242fa5ba862ed6"
BASELINE_SHA = "163e3e3914f4ccbb103f50ee83e15588d5c6e962fe8d14176ed48b2dd77c3266"
ROSTER_SHA = "ee08889a49ac84fa19d6b3d4c159e6a600eb2772d8375eb065fa1585e68543d1"
INIT_PID = 3588093
ROOT_IDENTITY = (106, 1)
HISTORY_ROOT = "/home/alex/work/pocket4-app-identities-20261105-r12-01/result-01"
HISTORY = {
    "com.Hyatt.hyt": ("app-00.json", "de9c08a737431abdb614d6ed481b0a224ae944d1020b9b08e47803a3d116ff1b"),
    "com.enflick.android.TextNow": ("app-16.json", "436c86a50a68a59681238d2676bda491d8a7b40b3fd2a314557981ab1d7b60b0"),
    "com.lianjia.beike": ("app-22.json", "a176c2e7de8e1a5fa4af0132713c200a9f426489c48beeb86ef8e114c49ad031"),
    "com.rytong.airchina": ("app-25.json", "4ff7afdcc60f1dc9f230ca2982a0131def4a651e5a2fa98fd06d808e6f0d0524"),
    "com.rytong.ceair": ("app-26.json", "39928518c3edb01d76fb58ad082050751cf2cc73d052c285ed57859b968da0bf"),
    "com.sankuai.meituan.takeoutnew": ("app-27.json", "49af2770488ab1bb0e661e78b202d6a650d367446b4d9a91e5e53a0c1c8ef134"),
    "com.szzc": ("app-30.json", "c27c03aae131784a0ca1d512a8623007e750ee2fa1192c67eb2365f00f77809b"),
    "tv.danmaku.bili": ("app-44.json", "4de28cde956c59e0622197f784488aa63707094b5ab0fb92ae07177e25083170"),
}
PACKAGES_PATH = "/data/system/packages.xml"
RESTRICTIONS_PATH = "/data/system/users/0/package-restrictions.xml"
PERMISSION_PATHS = (
    "/data/misc_de/0/apexdata/com.android.permission/runtime-permissions.xml",
    "/data/misc_de/0/apexdata/com.android.permission/access.abx",
    "/data/system/users/0/runtime-permissions.xml",
    "/data/system/users/0/access.abx",
)
PERMISSION_NAMES = frozenset(("access.abx", "access.abx.backup", "access.abx.reservecopy",
                            "runtime-permissions.xml", "runtime-permissions.xml.bak"))
LOCATION_PERMISSIONS = (
    "android.permission.ACCESS_COARSE_LOCATION",
    "android.permission.ACCESS_FINE_LOCATION",
    "android.permission.ACCESS_BACKGROUND_LOCATION",
)
MAX_METADATA = 2 * 1024 * 1024
MAX_APK = 512 * 1024 * 1024
MAX_APK_TOTAL = 4 * 1024 * 1024 * 1024
MAX_STDOUT = 65536
READ_SECONDS = 180
NAME = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,255}\Z")
DIGEST = re.compile(r"[0-9a-f]{64}\Z")
STAT_FIELDS = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
               "st_size", "st_mtime_ns", "st_ctime_ns")


class Rejected(RuntimeError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def need(condition, code):
    if not condition:
        raise Rejected(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def error_record(error):
    # Never serialize an exception message, path, XML attribute or source body.
    out = {"code": error.code if isinstance(error, Rejected) else type(error).__name__}
    if isinstance(error, OSError):
        out["errno"] = error.errno
    return out


def metadata(fd):
    row = os.fstat(fd)
    return {key: getattr(row, key) for key in STAT_FIELDS}


def public_metadata(row):
    return {key.removeprefix("st_"): value for key, value in row.items()}


class Budget:
    def __init__(self, seconds=READ_SECONDS):
        self.started = time.monotonic()
        self.deadline = self.started + seconds
        self.apk_bytes = 0

    def check(self):
        need(time.monotonic() < self.deadline, "READ_DEADLINE_EXCEEDED")

    def apk(self, count):
        self.check()
        self.apk_bytes += count
        need(self.apk_bytes <= MAX_APK_TOTAL, "APK_TOTAL_BYTE_BOUND")


class Descriptors:
    def __init__(self):
        self.live = set()
        self.acquired = self.closed = self.close_attempts = self.peak = 0
        self.close_errors = []

    def own(self, fd):
        need(fd not in self.live, "DESCRIPTOR_ALREADY_TRACKED")
        self.live.add(fd)
        self.acquired += 1
        self.peak = max(self.peak, len(self.live))
        need(len(self.live) <= 96, "OWNED_DESCRIPTOR_BOUND")
        return fd

    def close(self, fd):
        need(fd in self.live, "UNOWNED_DESCRIPTOR_CLOSE")
        self.live.remove(fd)
        self.close_attempts += 1
        try:
            os.close(fd)
            self.closed += 1
        except OSError as error:
            self.close_errors.append(error_record(error))
            raise Rejected("DESCRIPTOR_CLOSE_FAILED") from error

    def close_remaining(self):
        for fd in tuple(self.live):
            try:
                self.close(fd)
            except OSError:
                pass
            except Rejected:
                pass

    def report(self):
        return {"acquired": self.acquired, "closed": self.closed,
                "close_attempts": self.close_attempts, "peak": self.peak,
                "remaining": len(self.live), "errors": self.close_errors}


def path_parts(path):
    need(isinstance(path, str) and 1 < len(path) <= 2048 and
         path.startswith("/") and not path.startswith("//") and
         "\0" not in path and "\\" not in path, "ABSOLUTE_FIXED_PATH_REQUIRED")
    parts = path[1:].split("/")
    need(all(x and x not in (".", "..") and len(x.encode("utf-8")) <= 255 for x in parts),
         "NONCANONICAL_PATH")
    return parts


def open_beneath(root_fd, path, flags, fds):
    """Every path component is opened without following symlinks."""
    parts = path_parts(path)
    parents = []
    parent = root_fd
    try:
        for part in parts[:-1]:
            parent = fds.own(os.open(part, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC |
                                    os.O_NOFOLLOW, dir_fd=parent))
            parents.append(parent)
        return fds.own(os.open(parts[-1], flags | os.O_CLOEXEC | os.O_NOFOLLOW,
                              dir_fd=parent))
    finally:
        for fd in reversed(parents):
            fds.close(fd)


class Reader:
    def __init__(self, root_fd, fds, budget):
        self.root_fd, self.fds, self.budget = root_fd, fds, budget
        self.observed = {}
        self.absent = set()
        self.directories = {}

    def open_file(self, path):
        return open_beneath(self.root_fd, path,
                            os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOATIME", 0), self.fds)

    def check_path(self, path, expected):
        fd = self.open_file(path)
        try:
            need(metadata(fd) == expected, "CURRENT_PATH_INODE_OR_METADATA_CHANGED")
        finally:
            self.fds.close(fd)

    def read(self, path, limit, *, pin=None, apk=False):
        self.budget.check()
        fd = self.open_file(path)
        try:
            before = metadata(fd)
            need(stat.S_ISREG(before["st_mode"]) and before["st_nlink"] == 1 and
                 0 <= before["st_size"] <= limit, "SINGLE_REGULAR_FILE_BOUND")
            if apk:
                need(0 < before["st_size"] <= MAX_APK and
                     self.budget.apk_bytes + before["st_size"] <= MAX_APK_TOTAL,
                     "APK_SIZE_OR_TOTAL_BOUND")
            digest = hashlib.sha256()
            chunks = []
            count = 0
            while True:
                self.budget.check()
                part = os.read(fd, min(1024 * 1024, limit + 1 - count))
                if not part:
                    break
                count += len(part)
                need(count <= limit, "FILE_GREW_PAST_BOUND")
                if apk:
                    self.budget.apk(len(part))
                else:
                    chunks.append(part)
                digest.update(part)
            need(count == before["st_size"] and metadata(fd) == before,
                 "HELD_FILE_CHANGED_DURING_READ")
            self.check_path(path, before)
            value = digest.hexdigest()
            need(pin is None or value == pin, "EXTERNAL_FILE_PIN_CHANGED")
            previous = self.observed.get(path)
            need(previous is None or previous == before, "PREVIOUSLY_OBSERVED_FILE_CHANGED")
            self.observed[path] = before
            return (None if apk else b"".join(chunks),
                    {"path": path, "bytes": count, "sha256": value,
                     "stat": public_metadata(before), "held_and_path_unchanged": True})
        finally:
            self.fds.close(fd)

    def optional(self, path, limit):
        try:
            return self.read(path, limit)
        except FileNotFoundError:
            self.absent.add(path)
            return None

    def directory(self, path, predicate, *, remember=True):
        self.budget.check()
        fd = open_beneath(self.root_fd, path, os.O_RDONLY | os.O_DIRECTORY, self.fds)
        try:
            before = metadata(fd)
            need(stat.S_ISDIR(before["st_mode"]), "DIRECTORY_REQUIRED")
            # Bound the directory inventory before retaining any selected names.
            names = os.listdir(fd)
            need(len(names) <= 4096, "DIRECTORY_ENTRY_BOUND")
            selected = sorted(name for name in names if predicate(name))
            need(metadata(fd) == before, "DIRECTORY_CHANGED_DURING_LIST")
            again = open_beneath(self.root_fd, path, os.O_RDONLY | os.O_DIRECTORY, self.fds)
            try:
                need(metadata(again) == before and
                     sorted(name for name in os.listdir(again) if predicate(name)) == selected,
                     "DIRECTORY_PATH_OR_ENTRIES_CHANGED")
            finally:
                self.fds.close(again)
            if remember:
                self.directories[path] = (before, selected, predicate)
            return selected
        finally:
            self.fds.close(fd)

    def recheck(self):
        for path, expected in self.observed.items():
            self.budget.check()
            self.check_path(path, expected)
        for path in self.absent:
            self.budget.check()
            try:
                fd = self.open_file(path)
            except FileNotFoundError:
                continue
            else:
                self.fds.close(fd)
                raise Rejected("PREVIOUSLY_ABSENT_SOURCE_APPEARED")
        for path, (expected, names, predicate) in self.directories.items():
            current = self.directory(path, predicate, remember=False)
            need(current == names, "DIRECTORY_APK_SET_CHANGED")
            fd = open_beneath(self.root_fd, path, os.O_RDONLY | os.O_DIRECTORY, self.fds)
            try:
                need(metadata(fd) == expected, "DIRECTORY_IDENTITY_CHANGED")
            finally:
                self.fds.close(fd)


class HeldAndroidRoot:
    def __init__(self, baseline, fds, budget):
        self.fds, self.budget = fds, budget
        self.expected = baseline["framework_epoch"]["binding"]["processes"]["init"]
        need(baseline["framework_epoch"]["sha256"] == EPOCH and
             self.expected["host_pid"] == INIT_PID and
             baseline["process_roots"]["android_init"] == {
                 "device": ROOT_IDENTITY[0], "inode": ROOT_IDENTITY[1]},
             "FIXED_INIT_ROOT_BASELINE_REQUIRED")
        self.proc_fd = fds.own(os.open("/proc/" + str(INIT_PID),
                                     os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC |
                                     os.O_NOFOLLOW))
        self.proc_stat = metadata(self.proc_fd)
        # /proc/<pinned pid>/root is the sole intentional procfs magic link.
        self.root_fd = fds.own(os.open("root", os.O_PATH | os.O_DIRECTORY |
                                      os.O_CLOEXEC, dir_fd=self.proc_fd))
        self.verify()

    def proc_bytes(self, leaf):
        fd = self.fds.own(os.open(leaf, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
                                 dir_fd=self.proc_fd))
        try:
            self.budget.check()
            raw = os.read(fd, 65537)
            need(len(raw) <= 65536 and os.read(fd, 1) == b"", "PROC_METADATA_BOUND")
            return raw
        finally:
            self.fds.close(fd)

    def verify(self):
        self.budget.check()
        raw = self.proc_bytes("stat").decode("utf-8", "strict")
        end = raw.rfind(")")
        need(end > 0, "INIT_STAT_FORMAT")
        fields = raw[end + 2:].split()
        need(len(fields) >= 20 and fields[0] not in ("Z", "X") and
             int(raw[:raw.index("(")].strip()) == INIT_PID and
             int(fields[1]) == self.expected["parent_host_pid"] and
             int(fields[19]) == self.expected["start_ticks"], "INIT_BIRTH_OR_PARENT_CHANGED")
        values = dict(line.split(":", 1) for line in self.proc_bytes("status").decode().splitlines()
                      if ":" in line)
        need([int(x) for x in values["Uid"].split()] == self.expected["uids"] and
             [int(x) for x in values["NSpid"].split()] == self.expected["namespace_pids"],
             "INIT_UID_OR_PID_NAMESPACE_CHANGED")
        need([x.decode("utf-8", "strict") for x in self.proc_bytes("cmdline").split(b"\0") if x] ==
             self.expected["cmdline"] and
             self.proc_bytes("cgroup").decode().splitlines() == self.expected["cgroup"] and
             os.readlink("exe", dir_fd=self.proc_fd) == self.expected["executable"],
             "INIT_EXECUTABLE_OR_CGROUP_CHANGED")
        for name, expected in self.expected["namespaces"].items():
            need(name in ("pid", "mnt", "user") and
                 os.readlink("ns/" + name, dir_fd=self.proc_fd) == expected,
                 "INIT_NAMESPACE_CHANGED")
        row = os.fstat(self.root_fd)
        need((row.st_dev, row.st_ino) == ROOT_IDENTITY, "HELD_ANDROID_ROOT_CHANGED")
        current = self.fds.own(os.open("/proc/" + str(INIT_PID), os.O_RDONLY | os.O_DIRECTORY |
                                     os.O_CLOEXEC | os.O_NOFOLLOW))
        try:
            now = metadata(current)
            need((now["st_dev"], now["st_ino"]) ==
                 (self.proc_stat["st_dev"], self.proc_stat["st_ino"]), "INIT_PROC_PATH_REPLACED")
            root = self.fds.own(os.open("root", os.O_PATH | os.O_DIRECTORY |
                                       os.O_CLOEXEC, dir_fd=current))
            try:
                rs = os.fstat(root)
                need((rs.st_dev, rs.st_ino) == ROOT_IDENTITY, "CURRENT_ANDROID_ROOT_CHANGED")
            finally:
                self.fds.close(root)
        finally:
            self.fds.close(current)


class Node:
    __slots__ = ("tag", "attrs", "children")

    def __init__(self, tag):
        self.tag, self.attrs, self.children = tag, {}, []


def modified_utf8(raw):
    """Strict MUTF-8 code units, plus Android ART's supported four-byte form."""
    units, at = [], 0
    while at < len(raw):
        first = raw[at]
        at += 1
        if 0 < first < 0x80:
            value = first
        else:
            if 0xC0 <= first <= 0xDF:
                count, value, minimum = 1, first & 0x1F, 0x80
            elif 0xE0 <= first <= 0xEF:
                count, value, minimum = 2, first & 0x0F, 0x800
            elif 0xF0 <= first <= 0xF4:
                count, value, minimum = 3, first & 7, 0x10000
            else:
                raise Rejected("ABX_INVALID_UTF8_LEAD")
            need(at + count <= len(raw), "ABX_TRUNCATED_UTF8")
            for char in raw[at:at + count]:
                need(char & 0xC0 == 0x80, "ABX_INVALID_UTF8_CONTINUATION")
                value = (value << 6) | (char & 0x3F)
            at += count
            need(value >= minimum or (count == 1 and first == 0xC0 and value == 0),
                 "ABX_OVERLONG_UTF8")
            need(value <= 0x10FFFF, "ABX_UTF8_OUT_OF_RANGE")
        units.append(value)
    chars, at = [], 0
    while at < len(units):
        value = units[at]
        at += 1
        if 0xD800 <= value <= 0xDBFF:
            need(at < len(units) and 0xDC00 <= units[at] <= 0xDFFF,
                 "ABX_UNPAIRED_UTF16_SURROGATE")
            value = 0x10000 + ((value - 0xD800) << 10) + units[at] - 0xDC00
            at += 1
        else:
            need(not 0xDC00 <= value <= 0xDFFF, "ABX_UNPAIRED_UTF16_SURROGATE")
        chars.append(chr(value))
    return "".join(chars)


class Abx:
    def __init__(self, raw, check=lambda: None):
        need(type(raw) is bytes and 4 <= len(raw) <= MAX_METADATA and raw[:4] == b"ABX\0",
             "ABX0_MAGIC_OR_DOCUMENT_BOUND")
        self.raw, self.at, self.refs, self.check = raw, 4, [], check

    def take(self, length):
        need(0 <= length <= 65535 and self.at + length <= len(self.raw), "ABX_TRUNCATED_VALUE")
        value = self.raw[self.at:self.at + length]
        self.at += length
        return value

    def ushort(self):
        return struct.unpack(">H", self.take(2))[0]

    def utf(self):
        return modified_utf8(self.take(self.ushort()))

    def intern(self):
        index = self.ushort()
        if index == 65535:
            value = self.utf()
            if len(self.refs) < 65535:
                self.refs.append(value)
            return value
        need(index < len(self.refs), "ABX_UNDEFINED_STRING_REFERENCE")
        return self.refs[index]

    def value(self, kind):
        if kind == 0x10:
            return None
        if kind == 0x20:
            return self.utf()
        if kind == 0x30:
            return self.intern()
        if kind in (0x40, 0x50):
            return self.take(self.ushort())
        if kind in (0x60, 0x70):
            return struct.unpack(">i", self.take(4))[0]
        if kind in (0x80, 0x90):
            return struct.unpack(">q", self.take(8))[0]
        if kind in (0xA0, 0xB0):
            result = struct.unpack(">f" if kind == 0xA0 else ">d", self.take(4 if kind == 0xA0 else 8))[0]
            need(math.isfinite(result), "ABX_NONFINITE_ATTRIBUTE")
            return result
        if kind in (0xC0, 0xD0):
            return kind == 0xC0
        raise Rejected("ABX_UNKNOWN_ATTRIBUTE_TYPE")

    def parse(self):
        root, stack, accepting_attrs = None, [], False
        seen_start, ended, events, nodes = False, False, 0, 0
        while self.at < len(self.raw):
            events += 1
            need(events <= 200000, "ABX_EVENT_BOUND")
            if events % 128 == 0:
                self.check()
            event = self.take(1)[0]
            token, kind = event & 15, event & 240
            if token == 15:
                need(stack and accepting_attrs, "ABX_ATTRIBUTE_OUTSIDE_START_TAG")
                key = self.intern()
                need(NAME.fullmatch(key) and len(stack[-1].attrs) < 256 and
                     key not in stack[-1].attrs, "ABX_INVALID_OR_DUPLICATE_ATTRIBUTE")
                stack[-1].attrs[key] = self.value(kind)
                continue
            accepting_attrs = False
            if token == 0:
                need(kind == 0x10 and not seen_start and events == 1 and root is None,
                     "ABX_MISPLACED_START_DOCUMENT")
                seen_start = True
            elif token == 1:
                need(kind == 0x10 and root is not None and not stack and self.at == len(self.raw),
                     "ABX_INCOMPLETE_OR_TRAILING_DOCUMENT")
                ended = True
                break
            elif token == 2:
                need(kind == 0x30 and len(stack) < 64, "ABX_START_TAG_TYPE_OR_DEPTH")
                name = self.intern()
                need(NAME.fullmatch(name), "ABX_INVALID_TAG_NAME")
                node = Node(name)
                nodes += 1
                need(nodes <= 50000, "ABX_NODE_BOUND")
                if stack:
                    stack[-1].children.append(node)
                else:
                    need(root is None, "ABX_MULTIPLE_ROOTS")
                    root = node
                stack.append(node)
                accepting_attrs = True
            elif token == 3:
                need(kind == 0x30 and stack, "ABX_UNEXPECTED_END_TAG")
                name = self.intern()
                need(stack[-1].tag == name, "ABX_MISMATCHED_END_TAG")
                stack.pop()
            elif token in (4, 5, 7, 9):
                need(kind in (0x10, 0x20), "ABX_TEXT_TYPE")
                text = "" if kind == 0x10 else self.utf()
                # Text is never exposed. These metadata schemas use attributes.
                need(token == 9 or bool(stack) or not text.strip(), "ABX_TEXT_OUTSIDE_ROOT")
            elif token in (6, 8, 10):
                raise Rejected("ABX_ENTITY_DTD_OR_PI_FORBIDDEN")
            else:
                raise Rejected("ABX_UNKNOWN_EVENT")
        need(ended and root is not None and not stack, "ABX_MISSING_COMPLETE_END_DOCUMENT")
        return root


def parse_xml(raw, check=lambda: None):
    need(type(raw) is bytes and 0 < len(raw) <= MAX_METADATA, "XML_DOCUMENT_BOUND")
    if raw.startswith(b"ABX"):
        return Abx(raw, check).parse()
    # No entity expansion, including predefined/numeric references, is needed
    # for these persisted permission attributes; refuse every such document.
    need(b"&" not in raw and b"\0" not in raw, "XML_ENTITY_OR_NUL_FORBIDDEN")
    raw.decode("utf-8", "strict")
    parser = xml.parsers.expat.ParserCreate("UTF-8")
    parser.SetParamEntityParsing(xml.parsers.expat.XML_PARAM_ENTITY_PARSING_NEVER)
    root, stack, counts = [], [], [0, 0]

    def forbidden(*unused):
        raise Rejected("XML_ENTITY_DTD_OR_PI_FORBIDDEN")

    def start(name, attrs):
        counts[0] += 1
        check()
        need(counts[0] <= 50000 and len(stack) < 64 and len(attrs) <= 256 and
             NAME.fullmatch(name) and all(NAME.fullmatch(key) for key in attrs),
             "XML_STRUCTURE_BOUND")
        node = Node(name)
        node.attrs.update(attrs)
        if stack:
            stack[-1].children.append(node)
        else:
            need(not root, "XML_MULTIPLE_ROOTS")
            root.append(node)
        stack.append(node)

    def end(name):
        need(stack and stack[-1].tag == name, "XML_MISMATCHED_END_TAG")
        stack.pop()

    def text(value):
        counts[1] += len(value)
        need(counts[1] <= MAX_METADATA and (stack or not value.strip()), "XML_TEXT_BOUND")

    parser.StartElementHandler, parser.EndElementHandler = start, end
    parser.CharacterDataHandler = text
    parser.StartDoctypeDeclHandler = forbidden
    parser.EntityDeclHandler = forbidden
    parser.ExternalEntityRefHandler = forbidden
    parser.ProcessingInstructionHandler = forbidden
    try:
        parser.Parse(raw, True)
    except xml.parsers.expat.ExpatError as error:
        raise Rejected("MALFORMED_XML") from error
    need(len(root) == 1 and not stack, "XML_INCOMPLETE_DOCUMENT")
    return root[0]


def walk(root):
    pending = [root]
    while pending:
        node = pending.pop()
        yield node
        pending.extend(reversed(node.children))


def integer(value, code):
    if type(value) is int:
        return value
    need(type(value) is str and re.fullmatch(r"-?(?:0|[1-9][0-9]{0,18})", value), code)
    result = int(value, 10)
    need(-(1 << 63) <= result < (1 << 63), code)
    return result


def small_text(value, code, maximum=256):
    need(type(value) is str and len(value.encode("utf-8")) <= maximum and
         "\0" not in value, code)
    return value


def cert_digests(root):
    # Android's certificate-index table can be shared across package records.
    # Decode solely to SHA256, and never return certificate DER or hex.
    result = {}
    for node in walk(root):
        if node.tag != "cert" or "index" not in node.attrs or "key" not in node.attrs:
            continue
        index = integer(node.attrs["index"], "CERT_INDEX_TYPE")
        need(0 <= index < 65535, "CERT_INDEX_BOUND")
        key = node.attrs["key"]
        if type(key) is bytes:
            raw = key
        else:
            need(type(key) is str and len(key) % 2 == 0 and
                 0 < len(key) <= 131070 and re.fullmatch(r"[0-9a-fA-F]+", key),
                 "CERT_HEX_ENCODING")
            raw = bytes.fromhex(key)
        need(0 < len(raw) <= 65535, "CERT_BYTE_BOUND")
        digest = sha(raw)
        need(index not in result or result[index] == digest, "CONFLICTING_CERT_INDEX")
        result[index] = digest
    return result


def package_projection(root):
    need(root.tag == "packages", "PACKAGES_ROOT_REQUIRED")
    certs, result = cert_digests(root), {}
    for node in root.children:
        package = node.attrs.get("name")
        if node.tag != "package" or package not in HISTORY:
            continue
        need(package not in result, "DUPLICATE_TARGET_PACKAGE")
        uid_keys = [key for key in ("userId", "sharedUserId") if key in node.attrs]
        need(len(uid_keys) == 1, "PACKAGE_UID_AMBIGUOUS_OR_MISSING")
        uid = integer(node.attrs[uid_keys[0]], "PACKAGE_UID_TYPE")
        need(10000 <= uid < 100000, "PACKAGE_USER_ZERO_APPID_BOUND")
        versions = [integer(node.attrs[key], "PACKAGE_VERSION_TYPE")
                    for key in ("version", "versionCode") if key in node.attrs]
        need(versions and len(set(versions)) == 1 and 0 <= versions[0] < (1 << 63),
             "PACKAGE_VERSION_AMBIGUOUS_OR_MISSING")
        code_path = small_text(node.attrs.get("codePath"), "PACKAGE_CODE_PATH", 2048)
        path_parts(code_path)
        need(code_path.startswith("/data/app/"), "TARGET_CODE_PATH_OUTSIDE_DATA_APP")
        signing = [child for child in node.children if child.tag == "sigs"]
        need(len(signing) <= 1, "MULTIPLE_PACKAGE_SIGNATURE_RECORDS")
        signing_value = {"status": "UNKNOWN_NO_PACKAGE_MANAGER_RECORD",
                         "certificate_sha256": [], "cryptographic_verification_performed": False}
        if signing:
            items = [child for child in signing[0].children if child.tag == "cert"]
            count = integer(signing[0].attrs.get("count"), "SIGNATURE_COUNT_TYPE")
            need(0 < count <= 32 and len(items) == count, "SIGNATURE_COUNT_MISMATCH")
            indices = [integer(item.attrs.get("index"), "SIGNATURE_INDEX_TYPE") for item in items]
            need(len(indices) == len(set(indices)), "DUPLICATE_PACKAGE_CERT_INDEX")
            if all(index in certs for index in indices):
                signing_value.update(status="PACKAGE_MANAGER_CERTIFICATE_DIGESTS_ONLY",
                                     certificate_sha256=sorted(certs[index] for index in indices))
        abi = {key: small_text(node.attrs[key], "PACKAGE_ABI_BOUND", 64)
               for key in ("primaryCpuAbi", "secondaryCpuAbi", "cpuAbiOverride") if key in node.attrs}
        result[package] = {"package": package, "metadata_present": True, "android_user": 0,
                           "uid": uid, "version_code": versions[0], "code_path": code_path,
                           "package_manager_abi": abi, "package_manager_signing": signing_value}
    return result


def restrictions_projection(root):
    need(root.tag == "package-restrictions", "RESTRICTIONS_ROOT_REQUIRED")
    result = {}
    allowed = ("installed", "hidden", "suspended", "stopped", "enabled", "notLaunched")
    for node in root.children:
        package = node.attrs.get("name")
        if node.tag != "pkg" or package not in HISTORY:
            continue
        need(package not in result, "DUPLICATE_RESTRICTION_PACKAGE")
        values = {}
        for key in allowed:
            if key not in node.attrs:
                continue
            value = node.attrs[key]
            need(type(value) in (str, int, bool) and
                 (type(value) is not str or len(value) <= 64), "RESTRICTION_VALUE_TYPE")
            values[key] = value
        result[package] = {"coverage": True, "recorded_fields": values,
                           "absent_fields_not_defaulted": True}
    return result


def permission_projection(root, package, uid):
    """Return scoped stored data; absence or raw flags never mean denied."""
    containers = []
    if root.tag == "runtime-permissions":
        for node in root.children:
            if node.tag == "package" and node.attrs.get("name") == package:
                containers.append(("legacy_package", node))
    elif root.tag == "access":
        for section in root.children:
            if section.tag == "app-id-permissions":
                for node in section.children:
                    if node.tag == "app-id" and integer(node.attrs.get("id"), "PERMISSION_APPID_TYPE") == uid:
                        containers.append(("access_app_id", node))
    need(len(containers) <= 1, "DUPLICATE_PERMISSION_SUBJECT")
    out = {"coverage": bool(containers), "effective_grant_state": "UNKNOWN",
           "absent_permissions_not_denied": True, "entries": []}
    if not containers:
        out["reason"] = "NO_SCOPED_RECORD_IN_THIS_SOURCE"
        return out
    kind, node = containers[0]
    out["schema"] = kind
    out["reason"] = ("RAW_ACCESS_FLAGS_WITHOUT_QUALIFIED_GRANT_INTERPRETER" if kind == "access_app_id"
                     else "SAVED_EXPLICIT_VALUES_ONLY_NOT_LIVE_SERVICE_AUTHORITY")
    seen = set()
    for child in node.children:
        if child.tag != ("permission" if kind == "access_app_id" else "item"):
            continue
        name = small_text(child.attrs.get("name"), "PERMISSION_NAME_BOUND", 256)
        # Preserve the exact persisted value. The observed Beike build contains
        # a leading-space permission name; stripping it would falsely equate it
        # with android.permission.VIBRATE. Lexical shape is not grant authority.
        need(name not in seen and len(seen) < 256,
             "PERMISSION_NAME_OR_COUNT")
        seen.add(name)
        entry = {"name": name}
        if not NAME.fullmatch(name):
            entry["noncanonical_name_preserved"] = True
        if "flags" in child.attrs:
            value = child.attrs["flags"]
            need(type(value) is int or (type(value) is str and
                 len(value) <= 32 and re.fullmatch(r"[0-9a-fA-FxX+-]+", value)),
                 "PERMISSION_FLAG_TYPE")
            entry["flags"] = value
        if kind == "legacy_package" and "granted" in child.attrs:
            value = child.attrs["granted"]
            need(type(value) is bool or value in ("true", "false"), "PERMISSION_GRANT_TYPE")
            entry["stored_granted"] = value if type(value) is bool else value == "true"
        out["entries"].append(entry)
    out["entries"].sort(key=lambda item: item["name"])
    return out


def json_object(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            need(key not in result, "DUPLICATE_JSON_KEY")
            result[key] = value
        return result
    def invalid(unused):
        raise Rejected("NONFINITE_JSON_VALUE")
    value = json.loads(raw.decode("utf-8", "strict"), object_pairs_hook=pairs,
                       parse_constant=invalid)
    need(type(value) is dict, "HISTORICAL_JSON_OBJECT_REQUIRED")
    return value


def historical_projection(package, current, history, source_pin):
    """Content-addressed reference only; never emit a fresh verifier result."""
    need(history.get("package") == package and history.get("android_user") == 0 and
         type(history.get("apks")) is list and 0 < len(history["apks"]) <= 32,
         "HISTORICAL_APP_SCOPE")
    old = history["apks"]
    for row in old:
        need(type(row.get("bytes")) is int and 0 < row["bytes"] <= MAX_APK and
             type(row.get("sha256")) is str and DIGEST.fullmatch(row["sha256"]),
             "HISTORICAL_APK_IDENTITY_TYPE")
    old_counts = collections.Counter((row["bytes"], row["sha256"]) for row in old)
    new_counts = collections.Counter((row["bytes"], row["sha256"]) for row in current["apks"])
    matched = old_counts == new_counts
    identity = history.get("identity", {})
    comparison = {"source_sha256": source_pin, "all_base_and_split_bytes_identical": matched,
                  "package_uid_equal": identity.get("uid") == current["uid"],
                  "package_version_code_equal": identity.get("version_code") == current["version_code"],
                  "history_finished_utc": history.get("finished_utc")}
    result = {"comparison": comparison,
              "signature": {"status": "UNKNOWN_CURRENT_CONTENT_NOT_FULLY_MATCHED",
                            "new_signature_verification_performed": False,
                            "source_sha256": source_pin},
              "manifest_metadata": {"status": "UNKNOWN_CURRENT_CONTENT_NOT_FULLY_MATCHED"}}
    if not matched:
        return result
    # A complete bijection is required to inherit per-split metadata safely.
    need(all(count == 1 for count in old_counts.values()), "HISTORICAL_SPLITS_NOT_UNIQUE")
    old_by_digest = {(row["bytes"], row["sha256"]): row for row in old}
    cert_sets, signatures_good, base_rows = [], True, []
    for observed in current["apks"]:
        previous = old_by_digest[(observed["bytes"], observed["sha256"])]
        manifest = previous.get("manifest", {})
        need(manifest.get("package") == package, "HISTORICAL_MANIFEST_PACKAGE_MISMATCH")
        selected = {}
        for key in ("package", "version_name", "split_name", "declared_min_sdk", "declared_target_sdk"):
            value = manifest.get(key)
            need(value is None or (type(value) is str and len(value) <= 256),
                 "HISTORICAL_MANIFEST_STRING_BOUND")
            selected[key] = value
        version = manifest.get("version_code")
        need(type(version) is int and 0 <= version < (1 << 63), "HISTORICAL_MANIFEST_VERSION_TYPE")
        selected["version_code"] = version
        abis = manifest.get("embedded_native_abis", [])
        need(type(abis) is list and len(abis) <= 8 and all(type(x) is str and
             re.fullmatch(r"[A-Za-z0-9_-]{1,32}", x) for x in abis), "HISTORICAL_ABI_BOUND")
        selected["embedded_native_abis"] = abis
        observed["historical_manifest_for_identical_bytes"] = selected
        if observed["name"] == "base.apk":
            need(manifest.get("split_name") is None, "BASE_APK_MATCHES_HISTORICAL_SPLIT")
            base_rows.append(selected)
        else:
            need(type(manifest.get("split_name")) is str and manifest["split_name"],
                 "SPLIT_APK_MATCHES_HISTORICAL_BASE")
        signature = previous.get("signature", {})
        certs = signature.get("signer_certificate_sha256", [])
        need(type(certs) is list and len(certs) <= 32 and
             all(type(x) is str and DIGEST.fullmatch(x) for x in certs), "HISTORICAL_CERT_DIGEST_TYPE")
        cert_sets.append(tuple(sorted(certs)))
        signatures_good &= (signature.get("status") == "VERIFIED" and
            signature.get("verified") is True and signature.get("joined") is True and
            signature.get("timed_out") is False and signature.get("tool_exit_code") == 0 and
            previous.get("held_file_unchanged") is True and bool(certs))
    need(len(base_rows) == 1, "EXACTLY_ONE_HISTORICAL_BASE_REQUIRED")
    result["manifest_metadata"] = {
        "status": "HISTORICAL_MANIFEST_FOR_IDENTICAL_CURRENT_APK_BYTES",
        "base": base_rows[0], "fresh_manifest_parser_executed": False}
    pm_certs = current["package_manager_signing"]["certificate_sha256"]
    same_certs = len(set(cert_sets)) == 1
    certificate_match = bool(pm_certs) and same_certs and tuple(sorted(pm_certs)) == cert_sets[0]
    result["comparison"]["package_manager_certificates_match_history"] = (
        certificate_match if pm_certs else None)
    signatures_good &= (same_certs and history.get("signature_complete") is True and
                        history.get("base_split_certificates_equal") is True and
                        history.get("current_path_inode_readback_equal") is True)
    if pm_certs and not certificate_match:
        result["signature"]["status"] = "CONFLICT_PACKAGE_MANAGER_CERTIFICATE_RECORD"
    elif signatures_good:
        result["signature"].update(
            status="HISTORICAL_VERIFIED_REFERENCE_FOR_IDENTICAL_APK_BYTES",
            signer_certificate_sha256=list(cert_sets[0]))
    else:
        result["signature"]["status"] = "UNKNOWN_HISTORICAL_VERIFICATION_INCOMPLETE"
    return result


def validate_guard_result(value):
    need(type(value) is dict and value.get("schema") == "pocket4-current-main-guard-v1" and
         value.get("Main_epoch_sha256") == EPOCH and
         value.get("current_baseline_sha256") == BASELINE_SHA and
         value.get("current_baseline_qualification_sha256") == QUALIFICATION_SHA and
         all(value.get(key) is True for key in ("seven_processes_match", "three_host_processes_match",
             "resource_limits_match", "current_executable_and_root_backing_match")) and
         value.get("framework_exit_cause_resolved") is False and value.get("production_ready") is False,
         "PINNED_CURRENT_GUARD_RESULT_REQUIRED")
    return value


def collect():
    fds, budget = Descriptors(), Budget()
    result = {
        "schema": "pocket4-original-eight-readonly-inventory-v1",
        "scope": {"name": "original-eight-subset", "current_launcher_resolver_proven": False,
                  "all_launcher_inventory": False},
        "roster_source_sha256": ROSTER_SHA, "packages": list(HISTORY),
        "epoch_sha256": EPOCH, "guard_source_sha256": GUARD_SHA,
        "identity_qualification_only": True, "UI_or_install_runtime_admitted": False,
        "new_signature_verification_performed": False, "production_ready": False,
        "Android_commands": 0, "namespace_entries": 0, "App_launches": 0,
        "permission_changes": 0, "writes": 0, "automatic_retry": False,
        "read_limits": {"seconds": READ_SECONDS, "single_apk_bytes": MAX_APK,
                        "total_apk_bytes": MAX_APK_TOTAL, "stdout_bytes": MAX_STDOUT},
        "apps": [], "errors": [], "snapshot_consistent": False,
    }
    guard, host, android, held = None, None, None, None
    old_handler, old_timer = None, None
    try:
        need(os.getuid() == os.geteuid() == 0 and sys.platform.startswith("linux"),
             "EXACT_ROOT_LINUX_READER_REQUIRED")
        need(len(sys.argv) == 1, "NO_RUNTIME_OVERRIDE_ARGUMENTS")
        root = fds.own(os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC))
        host = Reader(root, fds, budget)
        raw, _ = host.read(GUARD_PATH, 65536, pin=GUARD_SHA)
        guard = types.ModuleType("pocket4_pinned_current_guard")
        guard.__file__ = GUARD_PATH
        exec(compile(raw, GUARD_PATH, "exec"), guard.__dict__)
        result["guard_before"] = validate_guard_result(guard.current_guard())
        baseline = guard.current_baseline()
        held = HeldAndroidRoot(baseline, fds, budget)
        del baseline
        android = Reader(held.root_fd, fds, budget)
        def expired(unused_signum, unused_frame):
            raise Rejected("READ_DEADLINE_EXCEEDED")
        old_handler = signal.signal(signal.SIGALRM, expired)
        old_timer = signal.setitimer(signal.ITIMER_REAL, max(0.001, budget.deadline - time.monotonic()))
        need(old_timer == (0.0, 0.0), "PREEXISTING_PROCESS_ALARM")
        metadata_sources = {}
        packages_raw, metadata_sources["packages"] = android.read(PACKAGES_PATH, MAX_METADATA)
        package_nodes = parse_xml(packages_raw, budget.check)
        projected = package_projection(package_nodes)
        del packages_raw, package_nodes
        restrictions_raw, metadata_sources["restrictions"] = android.read(RESTRICTIONS_PATH, MAX_METADATA)
        restrictions = restrictions_projection(parse_xml(restrictions_raw, budget.check))
        del restrictions_raw
        permission_sources = []
        for path in PERMISSION_PATHS:
            observed = android.optional(path, MAX_METADATA)
            if observed is None:
                permission_sources.append({"path": path, "status": "ABSENT", "document": None})
                continue
            raw, source = observed
            source["status"] = "READ"
            source["format"] = "ABX0" if raw.startswith(b"ABX\0") else "XML"
            try:
                document = parse_xml(raw, budget.check)
                source["root_tag"] = document.tag
                source["scoped_schema_supported"] = document.tag in ("access", "runtime-permissions")
            except (Rejected, UnicodeError) as error:
                source["status"] = "UNPARSED"
                source["error"] = error_record(error)
                document = None
            permission_sources.append({**source, "document": document})
            del raw
        result["fixed_permission_names_present"] = android.directory(
            "/data/system/users/0", lambda name: name in PERMISSION_NAMES)
        result["metadata_sources"] = metadata_sources
        result["permission_sources"] = [{key: value for key, value in source.items() if key != "document"}
                                        for source in permission_sources]
        for package, (history_name, history_sha) in HISTORY.items():
            budget.check()
            held.verify()
            if package not in projected:
                result["apps"].append({"package": package, "metadata_present": False,
                                       "status": "UNKNOWN_PACKAGE_NOT_IN_CURRENT_METADATA",
                                       "effective_permission_state": "UNKNOWN"})
                continue
            current = projected[package]
            current["user_restrictions"] = restrictions.get(package, {
                "coverage": False, "recorded_fields": {}, "absent_fields_not_defaulted": True})
            names = android.directory(current["code_path"], lambda name: name.endswith(".apk"))
            need(0 < len(names) <= 32 and "base.apk" in names and
                 all(re.fullmatch(r"[A-Za-z0-9_.-]+\.apk", name) for name in names),
                 "EXACT_BASE_AND_SPLIT_APK_SET_REQUIRED")
            current["apks"] = []
            for name in sorted(names, key=lambda value: (value != "base.apk", value)):
                _, artifact = android.read(current["code_path"] + "/" + name, MAX_APK, apk=True)
                # Do not repeat a long absolute path for each split.
                artifact.pop("path")
                artifact["name"] = name
                current["apks"].append(artifact)
            history_raw, historical_source = host.read(HISTORY_ROOT + "/" + history_name, 262144,
                                                       pin=history_sha)
            history = json_object(history_raw)
            current["historical_evidence"] = historical_projection(package, current, history, history_sha)
            current["historical_evidence"]["source_path"] = historical_source["path"]
            del history_raw, history
            observations = []
            for source in permission_sources:
                if source["document"] is None:
                    observations.append({"source": source["path"], "coverage": False,
                        "effective_grant_state": "UNKNOWN",
                        "reason": "SOURCE_" + source["status"], "entries": []})
                else:
                    observations.append({"source": source["path"], **permission_projection(
                        source["document"], package, current["uid"])})
            current["permission_observations"] = observations
            current["effective_permission_state"] = "UNKNOWN_SAVED_SOURCES_NOT_LIVE_AUTHORITY"
            current["location_permission_observations"] = [
                {"permission": permission, "effective_grant_state": "UNKNOWN",
                 "stored_observations": [
                     {"source": observed["source"], **entry}
                     for observed in observations for entry in observed["entries"]
                     if entry["name"] == permission]}
                for permission in LOCATION_PERMISSIONS]
            current["App_runtime_or_business_qualification"] = "NOT_EXECUTED"
            result["apps"].append(current)
        # Recheck every metadata/history/APK path and the complete APK name sets.
        held.verify()
        android.recheck()
        host.recheck()
        held.verify()
        result["all_paths_and_apk_sets_rechecked"] = True
    except BaseException as error:
        result["errors"].append(error_record(error))
    finally:
        if old_handler is not None:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)
            if old_timer and old_timer != (0.0, 0.0):
                signal.setitimer(signal.ITIMER_REAL, *old_timer)
        if guard is not None:
            try:
                result["guard_after"] = validate_guard_result(guard.current_guard())
                need(result.get("guard_before") == result["guard_after"], "GUARD_RESULTS_CHANGED")
            except BaseException as error:
                result["errors"].append({"stage": "final_guard", **error_record(error)})
        fds.close_remaining()
        result["observation_fds"] = fds.report()
        if fds.close_errors or fds.live or fds.acquired != fds.closed:
            result["errors"].append({"code": "OWNED_DESCRIPTORS_NOT_ALL_CLOSED"})
    result["apk_bytes_read"] = budget.apk_bytes
    result["elapsed_seconds"] = round(time.monotonic() - budget.started, 6)
    result["all_eight_packages_observed"] = (
        len(result["apps"]) == len(HISTORY) and all(app["metadata_present"] for app in result["apps"]))
    result["snapshot_consistent"] = bool(not result["errors"] and
        result.get("all_paths_and_apk_sets_rechecked") and result.get("guard_after"))
    result["status"] = "READONLY_SNAPSHOT_COMPLETE" if result["snapshot_consistent"] else "FAILED_OR_INCOMPLETE_READONLY_SNAPSHOT"
    # Facts from partial reads remain observations; none acquire current-snapshot
    # credit unless the single global snapshot_consistent result is true.
    return result


def main():
    result = collect()
    raw = json.dumps(result, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
                     allow_nan=False).encode("ascii")
    if len(raw) + 1 > MAX_STDOUT:
        result = {"schema": "pocket4-original-eight-readonly-inventory-v1",
                  "status": "FAILED_OUTPUT_BOUND", "snapshot_consistent": False,
                  "production_ready": False, "UI_or_install_runtime_admitted": False,
                  "suppressed_output_bytes": len(raw), "suppressed_output_sha256": sha(raw),
                  "errors": [{"code": "STDOUT_BOUND"}], "observation_fds": result["observation_fds"]}
        raw = json.dumps(result, sort_keys=True, separators=(",", ":")).encode("ascii")
    sys.stdout.buffer.write(raw + b"\n")
    sys.stdout.buffer.flush()
    return 0 if result.get("snapshot_consistent") else 1


if __name__ == "__main__":
    raise SystemExit(main())

