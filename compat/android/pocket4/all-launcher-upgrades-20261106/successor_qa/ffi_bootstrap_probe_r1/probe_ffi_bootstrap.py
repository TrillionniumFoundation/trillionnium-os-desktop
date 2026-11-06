#!/usr/bin/env python3
"""One host-only ctypes bootstrap observation; never enters or signals Main."""
import errno
import fcntl
import gc
import hashlib
import importlib
import json
import os
from pathlib import Path
import select
import signal
import stat
import struct
import subprocess
import sys
import time
import types

LIBFFI = "/usr/lib/x86_64-linux-gnu/libffi.so.8.2.0"
HELD = "/home/alex/work/pocket4-cell-successor-repaired-r2-20261106-execute-01/source/held_runtime_r5.py"
HELD_SHA = "72cf33399ca3c280fc0c9288669f7d6c13d387e41b5fb930cf477f2b940f16b4"
EXPECTED_LIB_STAT = {
    "st_dev": 66306, "st_ino": 108020388, "st_mode": 33188,
    "st_uid": 0, "st_gid": 0, "st_nlink": 1, "st_rdev": 0,
    "st_size": 64184, "st_mtime_ns": 1774599998000000000,
    "st_ctime_ns": 1791083436303902806,
}
STAT_FIELDS = tuple(EXPECTED_LIB_STAT)
IDENTITY_FIELDS = ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_rdev")
MAX_STDOUT = 131072
MAX_STDERR = 16384
CHILD_SECONDS = 30


def require(value, code):
    if not value:
        raise RuntimeError(code)


def stat_record(value):
    return {key: getattr(value, key) for key in STAT_FIELDS}


def descriptor(fd):
    before = stat_record(os.fstat(fd))
    link = os.readlink("/proc/self/fd/" + str(fd))
    flags = fcntl.fcntl(fd, fcntl.F_GETFD)
    status_flags = fcntl.fcntl(fd, fcntl.F_GETFL)
    require(before == stat_record(os.fstat(fd)), "FD_CHANGED_DURING_OBSERVATION")
    return {"fd": fd, "link": link, "fstat": before,
            "descriptor_flags": flags, "status_flags": status_flags}


def fd_identity(row):
    return (row["link"], row["descriptor_flags"], row["status_flags"],
            tuple(row["fstat"][key] for key in IDENTITY_FIELDS))


def census():
    require(len(os.listdir("/proc/self/task")) == 1, "SINGLE_THREAD_REQUIRED")
    snapshots = []
    for unused in range(2):
        numbers = [int(value) for value in os.listdir("/proc/self/fd")]
        rows = {}
        vanished = []
        for fd in sorted(numbers):
            try:
                rows[str(fd)] = descriptor(fd)
            except OSError as exc:
                if exc.errno not in (errno.EBADF, errno.ENOENT):
                    raise
                vanished.append(fd)
        require(len(vanished) == 1, "UNEXPECTED_CENSUS_DESCRIPTOR_LIFETIME")
        snapshots.append(rows)
    require(set(snapshots[0]) == set(snapshots[1]) and
            all(fd_identity(row) == fd_identity(snapshots[1][fd])
                for fd, row in snapshots[0].items()), "UNSTABLE_FD_CENSUS")
    return snapshots[1]


def same_descriptors(before, after):
    return (set(before) == set(after) and
            all(fd_identity(row) == fd_identity(after[fd]) for fd, row in before.items()))


def public_file(path, limit, expected_sha=None):
    require(isinstance(path, str) and path.startswith("/") and "\x00" not in path,
            "ABSOLUTE_PUBLIC_FILE_REQUIRED")
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = stat_record(os.fstat(fd))
        require(stat.S_ISREG(before["st_mode"]) and 0 < before["st_size"] <= limit,
                "PUBLIC_FILE_TYPE_OR_SIZE")
        require(before["st_uid"] == 0 and not before["st_mode"] & 0o022,
                "PUBLIC_FILE_OWNER_OR_MODE")
        body = b""
        while len(body) < before["st_size"]:
            part = os.read(fd, min(65536, before["st_size"] - len(body)))
            require(part, "PUBLIC_FILE_SHORT_READ")
            body += part
        require(not os.read(fd, 1), "PUBLIC_FILE_GREW")
        digest = hashlib.sha256(body).hexdigest()
        require(expected_sha is None or digest == expected_sha, "PUBLIC_FILE_PIN")
        require(before == stat_record(os.fstat(fd)) ==
                stat_record(os.stat(path, follow_symlinks=False)), "PUBLIC_FILE_REPLACED")
        return body, {"path": path, "bytes": len(body), "sha256": digest, "file": before}
    finally:
        os.close(fd)


def elf_identity(data):
    """Read only bounded ELF64 x86-64 build-id, NEEDED and public FFI symbols."""
    require(len(data) >= 64 and data[:7] == b"\x7fELF\x02\x01\x01", "ELF64_LE_REQUIRED")
    require(struct.unpack_from("<H", data, 18)[0] == 62, "ELF_X86_64_REQUIRED")
    shoff = struct.unpack_from("<Q", data, 40)[0]
    entsize, count, nameidx = struct.unpack_from("<HHH", data, 58)
    require(entsize == 64 and 0 < count <= 4096 and nameidx < count and
            shoff + count * 64 <= len(data), "ELF_SECTION_TABLE")
    sections = [struct.unpack_from("<IIQQQQIIQQ", data, shoff + i * 64)
                for i in range(count)]

    def content(section):
        offset, size = section[4:6]
        require(offset <= len(data) and size <= len(data) - offset, "ELF_SECTION_BOUNDS")
        return data[offset:offset + size]

    def string(table, offset):
        require(0 <= offset < len(table), "ELF_STRING_OFFSET")
        end = table.find(b"\0", offset)
        require(offset <= end <= offset + 4096, "ELF_STRING_BOUND")
        return table[offset:end].decode("ascii", "strict")

    names = content(sections[nameidx])
    result = {"build_id": None, "needed": [], "ffi_symbols": [], "ctypes_init_symbol": False}
    for section in sections:
        name = string(names, section[0])
        if name == ".note.gnu.build-id":
            note = content(section)
            require(len(note) >= 16, "ELF_BUILD_ID_NOTE")
            ns, ds, kind = struct.unpack_from("<III", note)
            start = 12 + ((ns + 3) & ~3)
            require(ns == 4 and note[12:16] == b"GNU\0" and kind == 3 and
                    0 < ds <= 64 and start + ds <= len(note), "ELF_BUILD_ID_SHAPE")
            result["build_id"] = note[start:start + ds].hex()
        if section[1] in (6, 11):
            require(section[6] < count, "ELF_LINK_INDEX")
            strings = content(sections[section[6]])
            entries = content(section)
            width = 16 if section[1] == 6 else 24
            require(section[9] == width and len(entries) % width == 0 and
                    len(entries) // width <= 16384, "ELF_DYNAMIC_ENTRIES")
            for offset in range(0, len(entries), width):
                if section[1] == 6:
                    tag, value = struct.unpack_from("<qQ", entries, offset)
                    if tag == 1:
                        result["needed"].append(string(strings, value))
                else:
                    no, info, other, index, value, size = struct.unpack_from("<IBBHQQ", entries, offset)
                    symbol = string(strings, no)
                    if symbol.startswith("ffi_") or symbol.startswith("Py_ffi_"):
                        result["ffi_symbols"].append({"name": symbol, "defined": index != 0,
                                                      "value": value, "size": size})
                    if symbol == "PyInit__ctypes" and index != 0:
                        result["ctypes_init_symbol"] = True
    require(len(result["needed"]) <= 64 and len(result["ffi_symbols"]) <= 128,
            "ELF_OUTPUT_BOUND")
    return result


def library_binding(fd, observed):
    require(observed["link"] == LIBFFI and observed["fstat"] == EXPECTED_LIB_STAT,
            "LIBFFI_DIAGNOSTIC_IDENTITY_DIFFERS")
    require(observed["descriptor_flags"] == fcntl.FD_CLOEXEC and
            observed["status_flags"] & os.O_ACCMODE == os.O_RDONLY and
            not observed["status_flags"] & getattr(os, "O_PATH", 0), "LIBFFI_FD_FLAGS")
    position = os.lseek(fd, 0, os.SEEK_CUR)
    data = os.pread(fd, EXPECTED_LIB_STAT["st_size"] + 1, 0)
    require(len(data) == EXPECTED_LIB_STAT["st_size"] and
            os.lseek(fd, 0, os.SEEK_CUR) == position and
            descriptor(fd) == observed and stat_record(os.stat(LIBFFI, follow_symlinks=False)) ==
            EXPECTED_LIB_STAT, "LIBFFI_READ_CHANGED_OWNER_OR_OFFSET")
    maps_path = "/proc/self/maps"
    with open(maps_path, "rb") as stream:
        maps = stream.read(1048577)
    require(len(maps) <= 1048576, "SELF_MAPS_BOUND")
    matches = []
    for line in maps.decode("ascii", "strict").splitlines():
        fields = line.split(None, 5)
        if len(fields) == 6 and fields[5] == LIBFFI:
            major, minor = [int(value, 16) for value in fields[3].split(":")]
            require(int(fields[4]) == EXPECTED_LIB_STAT["st_ino"] and
                    os.makedev(major, minor) == EXPECTED_LIB_STAT["st_dev"], "LIBFFI_MAP_IDENTITY")
            require(not ("w" in fields[1] and "x" in fields[1]), "LIBFFI_WRITABLE_EXECUTABLE_MAP")
            matches.append({"range": fields[0], "permissions": fields[1], "offset": fields[2]})
    require(matches and len(matches) <= 32 and any("x" in row["permissions"] for row in matches),
            "LIBFFI_EXECUTABLE_MAP_MISSING")
    elf = elf_identity(data)
    defined = {row["name"] for row in elf["ffi_symbols"] if row["defined"]}
    require({"ffi_closure_alloc", "ffi_closure_free"} <= defined, "LIBFFI_CLOSURE_SYMBOLS_MISSING")
    return {"path": LIBFFI, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
            "file": observed["fstat"], "descriptor": observed, "elf": elf,
            "matching_mappings": matches, "descriptor_offset_preserved": True,
            "manual_close_performed": False,
            "lifetime_owner_from_reviewed_primary_source": "libffi_process_global"}


def child():
    result = {"schema": "pocket4-ffi-bootstrap-host-child-v1", "ok": False,
              "phases": [], "errors": [], "Main_actions": 0, "namespace_entries": 0,
              "unknown_descriptors_closed": 0, "library_descriptor_closed_manually": False}
    try:
        require(sys.stdin.buffer.read(1) == b"R", "OWNED_PARENT_RELEASE_REQUIRED")
        require(sys.version_info[:2] == (3, 14), "ACTUAL_PYTHON_314_REQUIRED")
        require("_ctypes" not in sys.modules and "ctypes" not in sys.modules, "FRESH_CTYPES_IMPORT_REQUIRED")
        baseline = census()
        require(set(baseline) == {"0", "1", "2"}, "CHILD_INHERITED_FDS")
        result["python"] = {"version": sys.version, "version_info": list(sys.version_info),
                            "executable": os.path.realpath(sys.executable)}
        result["baseline"] = baseline
        native = importlib.import_module("_ctypes")
        first = census()
        result["phases"].append({"name": "import__ctypes", "descriptors": first})
        extra = set(first) - set(baseline)
        require(len(extra) == 1 and all(fd_identity(row) == fd_identity(first[fd])
                                       for fd, row in baseline.items()), "CTYPES_IMPORT_FD_DELTA")
        libfd = int(next(iter(extra)))
        result["library"] = library_binding(libfd, first[str(libfd)])
        pyctypes = importlib.import_module("ctypes")
        second = census()
        result["phases"].append({"name": "import_ctypes", "descriptors": second})
        require(same_descriptors(first, second), "PY_CTYPES_ADDED_OR_CHANGED_FD")
        held_source, result["held_source"] = public_file(HELD, 65536, HELD_SHA)
        held = types.ModuleType("pocket4_host_only_held_import_probe")
        held.__file__ = HELD
        exec(compile(held_source, HELD, "exec"), held.__dict__)
        third = census()
        result["phases"].append({"name": "import_only_frozen_held_runtime", "descriptors": third})
        require(same_descriptors(first, third), "FROZEN_IMPORT_ADDED_OR_CHANGED_FD")
        require(held.ctypes is pyctypes, "FROZEN_CTYPES_OBJECT_DIFFERS")
        for key, path, cap in (("python_file", result["python"]["executable"], 16777216),
                               ("ctypes_python_file", os.path.realpath(pyctypes.__file__), 131072),
                               ("ctypes_extension_file", os.path.realpath(native.__file__), 4194304)):
            require(path.startswith("/usr/"), "SYSTEM_RUNTIME_FILE_REQUIRED")
            data, result[key] = public_file(path, cap)
            if key == "ctypes_extension_file":
                result[key]["elf"] = elf_identity(data)
                require("libffi.so.8" in result[key]["elf"]["needed"] and
                        result[key]["elf"]["ctypes_init_symbol"], "CTYPES_LIBFFI_ELF_LINK_MISSING")
        gc.collect()
        final = census()
        result["phases"].append({"name": "after_public_identity_reads_and_gc", "descriptors": final})
        require(same_descriptors(first, final), "FINAL_LIBRARY_LIFETIME_FD_CHANGED")
        require(library_binding(libfd, final[str(libfd)]) == result["library"], "LIBRARY_BINDING_CHANGED")
        result["no_HeldTarget_or_MainBinding_instance_created"] = True
        result["ok"] = True
    except BaseException as exc:
        result["errors"].append({"type": type(exc).__name__, "code": str(exc)[:1024]})
    raw = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    require(len(raw.encode()) <= MAX_STDOUT, "CHILD_RESULT_BOUND")
    sys.stdout.write(raw)
    return 0 if result["ok"] else 1


def run_owned_child(argv, seconds=CHILD_SECONDS):
    """Own only this directly created child. Never signal a numeric PID or group."""
    before = census()
    proc = None
    pidfd = None
    streams = []
    output = {"stdout": bytearray(), "stderr": bytearray()}
    record = {"pidfd_acquired": False, "pidfd_closed": False, "pidfd_exit_observed": False,
              "owned_child_sigkill_count": 0, "timeout": False, "errors": []}
    try:
        proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, close_fds=True)
        streams = [proc.stdin, proc.stdout, proc.stderr]
        pidfd = os.pidfd_open(proc.pid, 0)
        record.update(child_pid=proc.pid, pidfd_acquired=True)
        proc.stdin.write(b"R")
        proc.stdin.flush()
        proc.stdin.close()
        readers = {proc.stdout.fileno(): "stdout", proc.stderr.fileno(): "stderr"}
        for fd in readers:
            os.set_blocking(fd, False)
        deadline = time.monotonic() + seconds
        while readers:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                record["timeout"] = True
                raise RuntimeError("OWNED_CHILD_DEADLINE")
            for fd in select.select(list(readers), [], [], min(remaining, 0.25))[0]:
                data = os.read(fd, 65536)
                if not data:
                    readers.pop(fd)
                    continue
                name = readers[fd]
                output[name].extend(data)
                require(len(output[name]) <= (MAX_STDOUT if name == "stdout" else MAX_STDERR),
                        "OWNED_CHILD_OUTPUT_BOUND")
        proc.wait(timeout=max(0.001, deadline - time.monotonic()))
    except BaseException as exc:
        record["errors"].append({"type": type(exc).__name__, "code": str(exc)[:1024]})
    finally:
        if proc is not None and pidfd is None:
            # No release byte was sent without a pidfd. EOF makes this exact
            # owned child reject its handshake; do not signal a numeric PID.
            proc.stdin.close()
            try:
                proc.wait(timeout=5)
                record["returncode"] = proc.returncode
            except BaseException:
                record["errors"].append({"code": "UNRELEASED_CHILD_REAP_FAILED"})
        if proc is not None and pidfd is not None:
            poller = select.poll()
            poller.register(pidfd, select.POLLIN)
            if not poller.poll(0):
                try:
                    signal.pidfd_send_signal(pidfd, signal.SIGKILL, None, 0)
                    record["owned_child_sigkill_count"] += 1
                except ProcessLookupError:
                    record["exited_between_poll_and_owned_signal"] = True
                except BaseException as exc:
                    record["errors"].append({"type": type(exc).__name__, "code": "OWNED_PIDFD_SIGNAL_FAILED"})
            try:
                proc.wait(timeout=5)
                record["returncode"] = proc.returncode
                record["pidfd_exit_observed"] = bool(poller.poll(0))
            except BaseException as exc:
                record["errors"].append({"type": type(exc).__name__, "code": "OWNED_CHILD_REAP_FAILED"})
        for stream in streams:
            if stream is not None:
                stream.close()
        if pidfd is not None:
            os.close(pidfd)
            record["pidfd_closed"] = True
        record["parent_descriptors_restored"] = same_descriptors(before, census())
    return record, bytes(output["stdout"]), bytes(output["stderr"])


def main():
    require(sys.argv[1:] == ["--host-only"], "EXACT_HOST_ONLY_ARGUMENT_REQUIRED")
    record, raw, stderr = run_owned_child([sys.executable, "-B", "-I", str(Path(__file__).resolve()), "--child"])
    result = {"schema": "pocket4-ffi-bootstrap-host-probe-v1", "ok": False,
              "child_lifecycle": record, "child_stdout_bytes": len(raw),
              "child_stdout_sha256": hashlib.sha256(raw).hexdigest(),
              "child_stderr_bytes": len(stderr), "child_stderr_sha256": hashlib.sha256(stderr).hexdigest(),
              "Main_actions": 0, "namespace_entries": 0, "Main_signals": 0,
              "guards_or_Main_locks_acquired": 0, "manual_library_FD_close": False,
              "production_ready": False, "automatic_retry": False}
    try:
        result["child"] = json.loads(raw.decode("utf-8", "strict"))
        require(record["returncode"] == 0 and record["pidfd_exit_observed"] and
                record["pidfd_closed"] and record["parent_descriptors_restored"] and
                not record["timeout"] and not record["errors"] and
                record["owned_child_sigkill_count"] == 0 and not stderr and result["child"]["ok"],
                "CHILD_OBSERVATION_OR_RETIREMENT_FAILED")
        result["library_fd_retired_by_owned_process_exit"] = True
        result["ok"] = True
    except BaseException as exc:
        result["error"] = {"type": type(exc).__name__, "code": str(exc)[:1024]}
    print(json.dumps(result, sort_keys=True, separators=(",", ":")))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(child() if sys.argv[1:] == ["--child"] else main())
