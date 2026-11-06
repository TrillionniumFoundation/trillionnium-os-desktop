#!/usr/bin/env python3
"""Read two proposed host aapt2 paths and the already pinned aapt closure.

Never execute a candidate, invoke Android, take an action lock, or read an
existing Main process. Existence and ELF headers do not establish provenance,
compatibility, or permission to run a candidate.
"""
import hashlib
import json
import os
import stat
import struct
import sys
import time

sys.dont_write_bytecode = True
STAT = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink",
        "st_size", "st_mtime_ns", "st_ctime_ns")
PARENT_ID = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink")
MAX_CANDIDATE = 64 * 1024 * 1024
DEPS = {
    "path": "/home/alex/work/pocket4-app-identities-20261105-r12-01/dependencies.json",
    "sha256": "dfe1182d8e0da4d3d6e842736378539df33e03a87cf0ed9ab4bbe9ae1f26c041",
}
AAPT = {
    "path": "/usr/lib/android-sdk/build-tools/debian/aapt",
    "bytes": 30680,
    "sha256": "d9c0d90fc4bcf03d57cbf4fe19ca66c80280ac760c53245c8678b9837844b972",
}
CANDIDATES = (
    "/usr/lib/android-sdk/build-tools/debian/aapt2",
    "/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source/prebuilts/sdk/tools/linux/bin/aapt2",
)


def need(value, reason):
    if not value:
        raise RuntimeError(reason)


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("ascii")


def metadata(fd):
    value = os.fstat(fd)
    return {key: getattr(value, key) for key in STAT}


def path_parts(path):
    need(type(path) is str and path.startswith("/"), "ABSOLUTE_PATH_REQUIRED")
    parts = path[1:].split("/")
    need(all(part not in ("", ".", "..") for part in parts), "CANONICAL_PATH_REQUIRED")
    return parts


class HeldPath:
    """Own only descriptors opened by this reader; never close by scanning."""
    def __init__(self, path):
        self.path, self.parts = path, path_parts(path)
        self.fds, self.parents, self.fd, self.missing = [], [], None, None

    def open(self):
        parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        self.fds.append(parent)
        self.parents.append({"path": "/", "fd": parent, "stat": metadata(parent)})
        for index, name in enumerate(self.parts[:-1]):
            try:
                parent = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            except FileNotFoundError:
                self.missing = {"parent_fd": self.parents[-1]["fd"], "name": name,
                                "component": "/" + "/".join(self.parts[:index + 1])}
                return self
            self.fds.append(parent)
            self.parents.append({"path": "/" + "/".join(self.parts[:index + 1]), "fd": parent, "stat": metadata(parent)})
        try:
            self.fd = os.open(self.parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        except FileNotFoundError:
            self.missing = {"parent_fd": parent, "name": self.parts[-1], "component": self.path}
            return self
        self.fds.append(self.fd)
        return self

    def verify_parent_paths(self):
        new = []
        try:
            parent = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            new.append(parent)
            for index, row in enumerate(self.parents):
                if index:
                    parent = os.open(self.parts[index - 1], os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
                    new.append(parent)
                current, held = metadata(parent), metadata(row["fd"])
                need(all(current[key] == held[key] == row["stat"][key] for key in PARENT_ID), "PARENT_IDENTITY_CHANGED")
        finally:
            errors = []
            for fd in reversed(new):
                try:
                    os.close(fd)
                except OSError:
                    errors.append(fd)
            need(not errors, "PARENT_RECHECK_FD_CLOSE_FAILED")

    def close(self):
        errors = []
        for fd in reversed(self.fds):
            try:
                os.close(fd)
            except OSError:
                errors.append(fd)
        self.fds.clear()
        need(not errors, "OWNED_FD_CLOSE_FAILED")


def read_regular(path, limit, require_root=False, expected=None):
    held = HeldPath(path)
    try:
        held.open()
        parents = [{"path": row["path"], "stat": row["stat"]} for row in held.parents]
        if held.missing is not None:
            try:
                os.stat(held.missing["name"], dir_fd=held.missing["parent_fd"], follow_symlinks=False)
            except FileNotFoundError:
                pass
            else:
                raise RuntimeError("MISSING_COMPONENT_CHANGED_DURING_OBSERVATION")
            held.verify_parent_paths()
            return {"path": path, "status": "ABSENT_AT_OBSERVATION", "missing_component": held.missing["component"],
                    "parents": parents, "parent_identity_rechecked": True}, None
        before = metadata(held.fd)
        need(stat.S_ISREG(before["st_mode"]) and before["st_nlink"] == 1, "REGULAR_SINGLE_LINK_FILE_REQUIRED")
        need(not require_root or before["st_uid"] == 0, "PINNED_DEPENDENCY_ROOT_OWNER_REQUIRED")
        need(0 < before["st_size"] <= limit, "FILE_SIZE_BOUND")
        digest, head, body, count = hashlib.sha256(), bytearray(), bytearray(), 0
        end = time.monotonic() + 20
        while count <= limit:
            need(time.monotonic() < end, "BOUNDED_READ_DEADLINE")
            part = os.read(held.fd, min(65536, limit + 1 - count))
            if not part:
                break
            count += len(part)
            digest.update(part)
            head.extend(part[:max(0, 64 - len(head))])
            if limit <= 262144:
                body.extend(part)
        need(count == before["st_size"] and metadata(held.fd) == before, "HELD_FILE_CHANGED")
        again = os.open(held.parts[-1], os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=held.parents[-1]["fd"])
        try:
            need(metadata(again) == before, "FILE_PATH_CHANGED")
        finally:
            os.close(again)
        held.verify_parent_paths()
        row = {"path": path, "status": "OBSERVED_REGULAR_FILE", "bytes": count, "sha256": digest.hexdigest(),
               "stat": before, "parents": parents, "held_file_and_path_full_stat_rechecked": True,
               "parent_identity_rechecked": True, "header_64_hex": bytes(head).hex()}
        if expected is not None:
            need(row["sha256"] == expected["sha256"] and ("bytes" not in expected or row["bytes"] == expected["bytes"]), "EXISTING_PIN_CHANGED")
        return row, bytes(body) if limit <= 262144 else None
    finally:
        held.close()


def elf_header(row):
    raw = bytes.fromhex(row["header_64_hex"])
    value = {"elf": raw[:4] == b"\x7fELF", "host_x86_64_header": False, "execution_performed": False}
    if len(raw) >= 64 and value["elf"]:
        value.update(elf_class=raw[4], data_encoding=raw[5], identification_version=raw[6])
        if raw[4:7] == b"\x02\x01\x01":
            kind, machine, version = struct.unpack_from("<HHI", raw, 16)
            value.update(elf_type=kind, machine=machine, header_version=version,
                         host_x86_64_header=kind in (2, 3) and machine == 62 and version == 1)
    return value


def main():
    need(os.getuid() == os.geteuid() == 0, "EXISTING_AUTHORIZED_ROOT_READER_REQUIRED")
    before = len(os.listdir("/proc/self/fd"))
    result = {"schema": "pocket4-two-proposed-aapt2-host-candidates-v1", "ok": False, "candidates": [], "errors": [],
              "tool_execution_authorized_by_this_result": False, "candidate_provenance_verified": False,
              "candidate_compatibility_verified": False, "candidate_executions": 0,
              "Main_reads": 0, "Android_commands": 0, "native_commands": 0, "namespace_entries": 0,
              "action_lock_acquired": False, "installs": 0, "UI_actions": 0, "permission_changes": 0,
              "existing_files_modified": False, "automatic_retry": False,
              "original_failed_audit_reclassified": False, "process_FDs_before": before}
    try:
        dependencies, raw = read_regular(DEPS["path"], 262144, True, DEPS)
        need(raw is not None, "EXISTING_DEPENDENCIES_ABSENT")
        deps = json.loads(raw)
        expected_aapt = {"declared_path": AAPT["path"], "resolved_path": AAPT["path"],
                         "bytes": AAPT["bytes"], "sha256": AAPT["sha256"]}
        need(deps["files"]["aapt"] == expected_aapt, "EXISTING_AAPT_DEPENDENCY_DIFFERS")
        result["fixed_dependencies"] = dependencies
        result["aapt2_already_declared_in_fixed_dependencies"] = any("aapt2" in key.lower() for key in deps["files"])
        original, unused = read_regular(AAPT["path"], 262144, True, AAPT)
        need(original["status"] == "OBSERVED_REGULAR_FILE", "EXISTING_AAPT_ABSENT")
        result["original_aapt"] = original
        for path in CANDIDATES:
            try:
                row, unused = read_regular(path, MAX_CANDIDATE)
                row["path_basis"] = "explicit_proposed_candidate_not_previously_observed"
                if row["status"] == "OBSERVED_REGULAR_FILE":
                    row["elf_header"] = elf_header(row)
                    row["provenance"] = "UNKNOWN_NOT_ESTABLISHED_BY_PATH_OR_HEADER"
                result["candidates"].append(row)
            except (OSError, RuntimeError) as error:
                result["candidates"].append({"path": path, "status": "NOT_INSPECTED_SAFELY", "type": type(error).__name__,
                                             "reason": str(error)[:200], "errno": getattr(error, "errno", None)})
                result["errors"].append({"path": path, "type": type(error).__name__})
        result["ok"] = len(result["candidates"]) == len(CANDIDATES) and not result["errors"]
    except BaseException as error:
        result["errors"].append({"type": type(error).__name__, "reason": str(error)[:200]})
    result["process_FDs_after"] = len(os.listdir("/proc/self/fd"))
    if result["process_FDs_after"] != before:
        result["errors"].append({"reason": "HOST_READER_DESCRIPTOR_DIFFERENCE"})
        result["ok"] = False
    raw = canonical(result)
    need(len(raw) <= 65536, "RESULT_BYTE_BOUND")
    print(raw.decode("ascii"), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
