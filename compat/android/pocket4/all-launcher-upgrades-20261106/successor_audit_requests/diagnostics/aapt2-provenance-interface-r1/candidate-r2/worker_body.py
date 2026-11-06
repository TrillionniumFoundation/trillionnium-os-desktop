#!/usr/bin/env python3
"""Host-only installed AAPT2 provenance, static dependencies, and help/version.

Final source embeds the already reviewed nofollow reader and a separately
reviewed static ELF parser. No APK is opened or passed to a tool. The local
dpkg records are provenance evidence, not a new distribution signature proof.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys
import time
import types
import zlib

sys.dont_write_bytecode = True

# The source assembler supplies READER_SOURCE / READER_SHA and ELF_SOURCE /
# ELF_SHA from exact reviewed files, plus CANDIDATE from actual inventory JSON.
COLLECTOR = {
    "path": "/home/alex/work/pocket4-successor-install-audit-source-20261106-r1/audit_successor_apks.py",
    "bytes": 29242, "sha256": "faff199c1f6218b3c01d87e44be610d6fa211de396b5e8c862c188dec59d284a",
}
INVENTORY_REFERENCE = {
    "job_id": "1a1b194cd9b-fc05-79b1", "stdout_bytes": 9876,
    "stdout_sha256": "60ee9c47cb1719343a1667d306e26086d66f2376d62b8c5251f4e64446887341",
}
OUTPUT = "/home/alex/work/pocket4-aapt2-provenance-interface-20261106-r2"
SYSTEM_LIBRARY_ROOTS = ("/usr/lib", "/lib", "/lib64")
SEARCH_DIRS = ("/usr/lib/x86_64-linux-gnu/android", "/usr/lib/x86_64-linux-gnu", "/lib/x86_64-linux-gnu", "/usr/lib64", "/lib64")
MAX_FILE = 64 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_RESULT = 262144


def required(value, reason):
    if not value:
        raise RuntimeError(reason)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("ascii")


def frozen_module(source, digest, name):
    raw = source.encode("utf-8")
    required(sha(raw) == digest, "EMBEDDED_REVIEWED_SOURCE_CHANGED")
    module = types.ModuleType(name)
    module.__file__ = "<" + name + ">"
    exec(compile(raw, module.__file__, "exec"), module.__dict__)
    return module


class BoundFile:
    """Hold one root-owned host file and retain the original reader's guards."""
    def __init__(self, reader, path, limit, expected=None, resolve=False):
        self.reader, self.declared, self.limit = reader, path, limit
        self.resolved = str(Path(path).resolve(strict=True)) if resolve else path
        self.held = None
        observed, unused = reader.read_regular(self.resolved, limit, True, expected)
        required(observed["status"] == "OBSERVED_REGULAR_FILE", "REQUIRED_HOST_FILE_ABSENT")
        self.observed = observed
        try:
            self.held = reader.HeldPath(self.resolved)
            self.held.open()
            required(self.held.fd is not None and reader.metadata(self.held.fd) == observed["stat"], "HOST_FILE_CHANGED_BETWEEN_BINDINGS")
            if expected is not None and "file" in expected:
                required(observed["stat"] == expected["file"], "ACTUAL_INVENTORY_FILE_STAT_CHANGED")
            required(str(Path(self.declared).resolve(strict=True)) == self.resolved, "HOST_PATH_RESOLUTION_CHANGED")
        except BaseException:
            self.close()
            raise

    def content(self, limit):
        required(self.observed["bytes"] <= limit, "CONTENT_SIZE_BOUND")
        raw = bytearray()
        while len(raw) < self.observed["bytes"]:
            part = os.pread(self.held.fd, min(65536, self.observed["bytes"] - len(raw)), len(raw))
            required(bool(part), "HOST_PREAD_PROGRESS")
            raw.extend(part)
        required(sha(raw) == self.observed["sha256"] and self.reader.metadata(self.held.fd) == self.observed["stat"], "HOST_CONTENT_CHANGED")
        return bytes(raw)

    def recheck(self):
        required(self.reader.metadata(self.held.fd) == self.observed["stat"], "HELD_HOST_FILE_CHANGED")
        required(str(Path(self.declared).resolve(strict=True)) == self.resolved, "HOST_PATH_RESOLUTION_CHANGED")
        fresh, unused = self.reader.read_regular(self.resolved, self.limit, True)
        required(all(fresh[key] == self.observed[key] for key in ("bytes", "sha256", "stat")), "HOST_BYTES_OR_PATH_CHANGED")
        self.held.verify_parent_paths()

    def pin(self):
        return {"declared_path": self.declared, "resolved_path": self.resolved,
                "bytes": self.observed["bytes"], "sha256": self.observed["sha256"], "file": self.observed["stat"]}

    def close(self):
        if self.held is not None:
            self.held.close()
            self.held = None


class EvidenceStore:
    def __init__(self, reader):
        self.reader, self.fd, self.written = reader, None, []
        parent = reader.HeldPath(str(Path(OUTPUT).parent))
        try:
            parent.open()
            required(parent.fd is not None and stat.S_ISDIR(os.fstat(parent.fd).st_mode), "FIXED_OUTPUT_PARENT_REQUIRED")
            os.mkdir(Path(OUTPUT).name, 0o700, dir_fd=parent.fd)
            self.fd = os.open(Path(OUTPUT).name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent.fd)
            value = os.fstat(self.fd)
            required(value.st_uid == 0 and stat.S_IMODE(value.st_mode) == 0o700, "ROOT_PRIVATE_NEW_OUTPUT_REQUIRED")
            os.fsync(parent.fd)
        except BaseException:
            self.close()
            raise
        finally:
            parent.close()

    def write(self, name, raw):
        required(re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", name) and name not in (".", ".."), "SAFE_OUTPUT_NAME")
        fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400, dir_fd=self.fd)
        try:
            view = memoryview(raw)
            while view:
                count = os.write(fd, view)
                required(count > 0, "OUTPUT_WRITE_PROGRESS")
                view = view[count:]
            os.fsync(fd)
        finally:
            os.close(fd)
        os.fsync(self.fd)
        pin = {"path": OUTPUT + "/" + name, "bytes": len(raw), "sha256": sha(raw)}
        # read_regular intentionally rejects zero-sized candidate files. Empty
        # logs are read with a held direct fd instead of weakening that reader.
        check = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=self.fd)
        try:
            value = self.reader.metadata(check)
            required(stat.S_ISREG(value["st_mode"]) and value["st_uid"] == 0 and value["st_nlink"] == 1 and value["st_size"] == len(raw), "OUTPUT_READBACK_IDENTITY")
            body = bytearray()
            while len(body) < len(raw):
                part = os.read(check, min(65536, len(raw) - len(body)))
                required(bool(part), "OUTPUT_READBACK_PROGRESS")
                body.extend(part)
            required(bytes(body) == raw and self.reader.metadata(check) == value, "OUTPUT_READBACK_CHANGED")
        finally:
            os.close(check)
        self.written.append(pin)
        return pin

    def close(self):
        if self.fd is not None:
            os.close(self.fd)
            self.fd = None


def package_fields(raw):
    fields, key = {}, None
    for line in raw.decode("utf-8", "strict").splitlines():
        if line.startswith((" ", "\t")):
            required(key is not None, "DPKG_CONTINUATION_WITHOUT_FIELD")
            fields[key] += "\n" + line
        else:
            required(":" in line, "DPKG_FIELD_SYNTAX")
            key, value = line.split(":", 1)
            required(re.fullmatch(r"[A-Za-z][A-Za-z0-9-]*", key) and key not in fields, "DPKG_DUPLICATE_OR_INVALID_FIELD")
            fields[key] = value.lstrip(" ")
    return fields


def in_system_library_root(path):
    return any(path == root or path.startswith(root + "/") for root in SYSTEM_LIBRARY_ROOTS)


def search_paths(value, origin):
    if value is None:
        return []
    required(type(value) is str and len(value) <= 4096, "STATIC_SEARCH_PATH_BOUND")
    paths = []
    for entry in value.split(":"):
        required(bool(entry), "NO_CWD_LOADER_SEARCH_PATH")
        entry = entry.replace("${ORIGIN}", origin).replace("$ORIGIN", origin)
        required("$" not in entry and entry.startswith("/"), "UNSUPPORTED_LOADER_EXPANSION")
        resolved = str(Path(entry).resolve(strict=False))
        required(in_system_library_root(resolved), "SEARCH_PATH_OUTSIDE_REVIEWED_SYSTEM_LIBRARY_ROOTS")
        if resolved not in paths:
            paths.append(resolved)
    return paths


def resolve_dependency(name, dirs):
    required(type(name) is str and re.fullmatch(r"[A-Za-z0-9_+.-]{1,160}", name) and name not in (".", ".."), "BOUNDED_SONAME_REQUIRED")
    matches = {}
    for folder in dirs:
        path = Path(folder) / name
        try:
            resolved = str(path.resolve(strict=True))
        except FileNotFoundError:
            continue
        required(in_system_library_root(resolved), "DEPENDENCY_RESOLVED_OUTSIDE_SYSTEM_LIBRARY_ROOTS")
        matches.setdefault(resolved, str(path))
    required(len(matches) == 1, "STATIC_DEPENDENCY_ABSENT_OR_AMBIGUOUS")
    return next(iter(matches.values()))


def main():
    required(os.getuid() == os.geteuid() == 0, "EXISTING_AUTHORIZED_ROOT_HOST_READER_REQUIRED")
    os.umask(0o077)
    start_fds = len(os.listdir("/proc/self/fd"))
    end = time.monotonic() + 210
    files, store = [], None
    result = {"schema": "pocket4-existing-dpkg-aapt2-host-proof-and-interface-v1", "ok": False,
              "inventory_reference": INVENTORY_REFERENCE, "candidate": CANDIDATE,
              "Main_reads": 0, "Android_commands": 0, "native_commands": 0, "namespace_entries": 0,
              "action_lock_acquired": False, "APK_reads": 0, "APK_tool_inputs": 0,
              "App_launches": 0, "installs": 0, "UI_actions": 0, "permission_changes": 0,
              "existing_files_modified": False, "automatic_retry": False,
              "original_failed_audit_reclassified": False, "candidate_executions": 0,
              "process_FDs_before": start_fds, "commands": [], "errors": [],
              "official_distribution_signature_reverified": False,
              "static_dependency_observation_is_runtime_loader_proof": False}
    try:
        reader = frozen_module(READER_SOURCE, READER_SHA, "pinned_aapt2_host_reader")
        elf = frozen_module(ELF_SOURCE, ELF_SHA, "pinned_static_elf_reader")
        store = EvidenceStore(reader)
        def bind(path, limit=MAX_FILE, expected=None, resolve=False):
            required(time.monotonic() < end and len(files) < 64, "HOST_PROOF_TIME_OR_FILE_BOUND")
            item = BoundFile(reader, path, limit, expected, resolve)
            files.append(item)
            required(sum(row.observed["bytes"] for row in files) <= MAX_TOTAL, "HOST_PROOF_TOTAL_BYTES_BOUND")
            return item
        candidate = bind(CANDIDATE["path"], 262144, CANDIDATE)
        candidate_bytes = candidate.content(262144)
        candidate_md5 = hashlib.md5(candidate_bytes, usedforsecurity=False).hexdigest()
        status_file = bind("/var/lib/dpkg/status", 32 * 1024 * 1024)
        status = status_file.content(32 * 1024 * 1024)
        packages = []
        for block in status.split(b"\n\n"):
            if re.search(br"(?:^|\n)Package: aapt(?:\n|$)", block):
                fields = package_fields(block)
                if fields.get("Architecture") == "amd64" and fields.get("Status") == "install ok installed":
                    packages.append((fields, block))
        required(len(packages) == 1, "EXACT_INSTALLED_AMD64_AAPT_DPKG_RECORD_REQUIRED")
        fields, block = packages[0]
        result["installed_package"] = {key: fields[key] for key in ("Package", "Status", "Version", "Architecture", "Source", "Depends") if key in fields}
        result["installed_package"]["original_status_paragraph"] = store.write("aapt-installed-status.original.txt", block + b"\n")
        pairs = []
        for prefix in ("/var/lib/dpkg/info/aapt", "/var/lib/dpkg/info/aapt:amd64"):
            a, b = Path(prefix + ".list"), Path(prefix + ".md5sums")
            if a.exists() and b.exists():
                pairs.append((str(a), str(b)))
        required(len(pairs) == 1, "UNIQUE_INSTALLED_AAPT_DPKG_FILE_METADATA_REQUIRED")
        list_file, md5_file = (bind(path, 4 * 1024 * 1024) for path in pairs[0])
        listed = list_file.content(4 * 1024 * 1024).decode("utf-8", "strict").splitlines()
        required(listed.count(CANDIDATE["path"]) == 1, "AAPT2_NOT_EXACT_MEMBER_OF_INSTALLED_PACKAGE")
        matches = []
        for line in md5_file.content(4 * 1024 * 1024).decode("ascii", "strict").splitlines():
            match = re.fullmatch(r"([0-9a-f]{32}) [ *](.+)", line)
            required(match is not None, "DPKG_MD5_LINE_SYNTAX")
            if match[2] == CANDIDATE["path"].lstrip("/"):
                matches.append(match[1])
        required(matches == [candidate_md5], "INSTALLED_PACKAGE_AAPT2_MD5_MISMATCH")
        result["installed_dpkg_candidate_membership_and_checksum_match"] = True
        result["candidate_md5_from_actual_bytes"] = candidate_md5
        result["dpkg_metadata"] = [row.pin() for row in (status_file, list_file, md5_file)]
        static_rows, queue, seen, total = [], [candidate], {}, 0
        while queue:
            current = queue.pop(0)
            if current.resolved in seen:
                continue
            required(len(seen) < 48 and time.monotonic() < end, "STATIC_ELF_GRAPH_BOUND")
            data = elf.inspect_elf_fd(current.held.fd, current.observed["bytes"])
            required(data["additional_loader_directives"] == [], "ADDITIONAL_LOADER_DIRECTIVES_OUTSIDE_BOUND_SCOPE")
            seen[current.resolved] = data
            row = {"file": current.pin(), "static_elf": data, "resolved_needed": []}
            static_rows.append(row)
            origin = str(Path(current.resolved).parent)
            dirs = search_paths(data.get("rpath"), origin) + search_paths(data.get("runpath"), origin) + list(SEARCH_DIRS)
            for name in data["needed"]:
                declared = resolve_dependency(name, dirs)
                resolved = str(Path(declared).resolve(strict=True))
                row["resolved_needed"].append({"soname": name, "declared_path": declared, "resolved_path": resolved})
                if resolved not in seen and not any(x.resolved == resolved for x in queue):
                    queue.append(bind(declared, resolve=True))
            interpreter = data.get("interpreter")
            if interpreter is not None:
                required(interpreter.startswith("/"), "ABSOLUTE_ELF_INTERPRETER_REQUIRED")
                resolved = str(Path(interpreter).resolve(strict=True))
                required(in_system_library_root(resolved), "ELF_INTERPRETER_OUTSIDE_SYSTEM_LIBRARY_ROOTS")
                row["resolved_interpreter"] = {"declared_path": interpreter, "resolved_path": resolved}
                if resolved not in seen and not any(x.resolved == resolved for x in queue):
                    queue.append(bind(interpreter, resolve=True))
        result["static_dependency_graph"] = static_rows
        result["static_dependency_file_count"] = len(static_rows)
        result["static_graph_limitations"] = "Closed-system-path static dependency observations, not proof of the dynamic loader's selected mappings or official release provenance."
        collector_file = bind(COLLECTOR["path"], 65536, COLLECTOR)
        tool_source = collector_file.content(65536)
        runner = frozen_module(tool_source.decode("utf-8"), COLLECTOR["sha256"], "pinned_original_bounded_host_runner")
        result["bounded_runner_source"] = collector_file.pin()
        for name, tail in (("version", ["version"]), ("dump-badging-help", ["dump", "badging", "--help"])):
            for item in files:
                required(time.monotonic() < end, "HOST_TOTAL_DEADLINE_BEFORE_FILE_RECHECK")
                item.recheck()
            command = {"name": name, "APK_input": False}
            result["commands"].append(command)
            required(time.monotonic() + 5 < end, "HOST_TOTAL_DEADLINE_BEFORE_CANDIDATE_SPAWN")
            outputs = runner.run_tool([CANDIDATE["path"], *tail], (candidate.held.fd,), command, end)
            result["candidate_executions"] += int(command.get("spawned") is True)
            for stream, raw in outputs.items():
                command[stream] = store.write(name + "." + stream, raw)
                if len(raw) <= 32768:
                    command[stream + "_original_hex"] = raw.hex()
            required(command.get("joined") is True and command.get("pipes_closed") is True, "OWNED_TOOL_CHILD_RETIREMENT_NOT_PROVED")
            for item in files:
                required(time.monotonic() < end, "HOST_TOTAL_DEADLINE_BEFORE_FILE_RECHECK")
                item.recheck()
        result["all_bound_host_files_unchanged"] = True
        result["all_interface_commands_succeeded"] = len(result["commands"]) == 2 and all(
            command.get("returncode") == 0 and command.get("output_capture_complete") is True and not command.get("timed_out") and not command.get("error")
            for command in result["commands"])
        result["ok"] = result["all_interface_commands_succeeded"]
    except BaseException as error:
        result["errors"].append({"type": type(error).__name__, "reason": str(error)[:240]})
    finally:
        for item in reversed(files):
            try:
                item.close()
            except BaseException as error:
                result["errors"].append({"stage": "host_file_close", "type": type(error).__name__})
        if result["errors"]:
            result["ok"] = False
        result["all_owned_tool_children_joined"] = all(row.get("joined") is True and row.get("pipes_closed") is True for row in result["commands"])
        result["status"] = ("EXISTING_DPKG_TOOL_AND_INTERFACE_OBSERVED" if result["ok"] else
                            "HOST_PROOF_OR_INTERFACE_INCOMPLETE_NO_RETRY")
        try:
            if store is not None:
                result["new_evidence_files"] = list(store.written)
                raw = canonical(result) + b"\n"
                required(len(raw) <= MAX_RESULT, "RESULT_BOUND")
                result["final_receipt"] = store.write("result.json", raw)
        except BaseException as error:
            result["errors"].append({"stage": "final_receipt", "type": type(error).__name__, "reason": str(error)[:160]})
            result["ok"] = False
        finally:
            if store is not None:
                try:
                    store.close()
                except BaseException as error:
                    result["errors"].append({"stage": "evidence_directory_close", "type": type(error).__name__})
                    result["ok"] = False
        result["process_FDs_after"] = len(os.listdir("/proc/self/fd"))
        if result["process_FDs_after"] != start_fds:
            result["errors"].append({"reason": "HOST_PROCESS_DESCRIPTOR_DIFFERENCE"})
            result["ok"] = False
        if not result["ok"]:
            result["status"] = "HOST_PROOF_OR_INTERFACE_INCOMPLETE_NO_RETRY"
    raw = canonical(result)
    required(len(raw) <= MAX_RESULT, "STDOUT_ARTIFACT_BOUND")
    print(json.dumps({"encoding": "zlib-base64", "artifact_bytes": len(raw), "artifact_sha256": sha(raw),
                      "data": base64.b64encode(zlib.compress(raw, 9)).decode("ascii")}, separators=(",", ":")), flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
