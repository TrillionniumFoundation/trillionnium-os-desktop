#!/usr/bin/env python3
"""One fixed public meminfo observation; no build admission, child, write or retry."""
import datetime
import hashlib
import json
import os
import stat
import sys
import time

def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)

def parse_admission_meminfo(raw):
    require(isinstance(raw, bytes) and 0 < len(raw) <= 16384,
            "fixed meminfo byte bound differs")
    names = {"MemTotal", "MemAvailable", "SwapTotal", "SwapFree", "SwapCached"}
    memory = {}
    for line in raw.decode("ascii", "strict").splitlines():
        name, separator, value = line.partition(":")
        if name not in names:
            continue
        require(name not in memory, "duplicate required meminfo field")
        words = value.split()
        require(separator == ":" and len(words) == 2 and words[0].isdigit() and words[1] == "kB",
                "required meminfo field units differ")
        memory[name] = int(words[0]) * 1024
    require(set(memory) == names, "required meminfo fields incomplete")
    require(0 < memory["MemTotal"] and 0 <= memory["MemAvailable"] <= memory["MemTotal"] and
            0 <= memory["SwapFree"] <= memory["SwapTotal"] and memory["SwapCached"] >= 0,
            "required meminfo values inconsistent")
    return memory


INPUT = "/proc/meminfo"
MAX_RAW = 16384
MAX_OUTPUT = 131072
QUALIFICATION_SECONDS = 5.0
MIN_AVAILABLE = 16106127360


def identity(value):
    return [value.st_dev, value.st_ino, value.st_mode, value.st_uid, value.st_gid,
            value.st_nlink, value.st_size, value.st_mtime_ns, value.st_ctime_ns]


def observe_once():
    started = time.monotonic()
    deadline = started + QUALIFICATION_SECONDS
    record = {
        "schema": 1, "state": "FAILED", "input_path": INPUT,
        "single_observation": True, "automatic_retry": False,
        "qualification_seconds": QUALIFICATION_SECONDS,
        "qualification_clock_started_after_imports": True,
        "hard_syscall_deadline_claimed": False,
        "first_error": None, "cleanup_errors": [],
        "fd": {"acquired": False, "close_attempted": False, "closed": False},
        "identity": {}, "raw": None, "public_memory_bytes": None,
        "complete_EOF": False, "collection_complete": False,
        "minimum_MemAvailable_bytes": MIN_AVAILABLE,
        "meets_15GiB_threshold": None, "normal_build_admission_qualified": False,
        "Main_actions": 0, "Android_actions": 0, "children_started": 0,
        "file_writes": 0, "cgroup_reads_or_changes": 0,
        "future_normal_must_read_fresh_again": True}
    fd = None
    raw = b""
    try:
        require(sys.argv[1:] == ["--read-once"], "fixed read-once arguments required")
        require(os.getuid() == 1000 and os.geteuid() == 1000, "operator UID1000 required")
        named = os.stat(INPUT, follow_symlinks=False)
        record["identity"]["named_before"] = identity(named)
        require(stat.S_ISREG(named.st_mode), "fixed meminfo must be a regular proc file")
        fd = os.open(INPUT, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        record["fd"]["acquired"] = True
        record["fd"]["number"] = fd
        held = os.fstat(fd)
        record["identity"]["held_before"] = identity(held)
        require(identity(named) == identity(held), "fixed meminfo changed before held read")
        chunks = []
        total = 0
        while True:
            require(time.monotonic() <= deadline, "meminfo qualification deadline exceeded")
            chunk = os.read(fd, min(4096, MAX_RAW + 1 - total))
            if not chunk:
                record["complete_EOF"] = True
                break
            chunks.append(chunk)
            total += len(chunk)
            require(total <= MAX_RAW, "fixed meminfo byte bound differs")
        raw = b"".join(chunks)
        require(0 < len(raw) <= MAX_RAW, "fixed meminfo byte bound differs")
        held_after = os.fstat(fd)
        named_after = os.stat(INPUT, follow_symlinks=False)
        record["identity"]["held_after"] = identity(held_after)
        record["identity"]["named_after"] = identity(named_after)
        require(identity(named) == identity(held_after) == identity(named_after),
                "fixed meminfo held/named identity changed during observation")
        record["observed_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        record["observed_unix_ns_decimal"] = str(time.time_ns())
        record["raw"] = {"bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                         "ascii": raw.decode("ascii", "strict")}
        # This exact parser already ran in the fixed Normal09 46-control package.
        # Duplicate fields, wrong units, missing fields and inconsistent values fail.
        memory = parse_admission_meminfo(raw)
        record["public_memory_bytes"] = memory
        record["meets_15GiB_threshold"] = memory["MemAvailable"] >= MIN_AVAILABLE
        record["threshold_difference_bytes"] = memory["MemAvailable"] - MIN_AVAILABLE
        record["global_swap_is_owned_build_budget"] = False
        require(time.monotonic() <= deadline, "meminfo qualification deadline exceeded")
    except Exception as error:
        record["first_error"] = {"type": type(error).__name__, "message": str(error)}
    finally:
        if fd is not None:
            record["fd"]["close_attempted"] = True
            try:
                os.close(fd)
                record["fd"]["closed"] = True
            except Exception as error:
                record["cleanup_errors"].append(
                    {"operation": "close_owned_meminfo_fd", "type": type(error).__name__,
                     "message": str(error)})
            fd = None
    record["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    record["elapsed_seconds"] = time.monotonic() - started
    if time.monotonic() > deadline:
        if record["first_error"] is None:
            record["first_error"] = {"type": "TimeoutError",
                                     "message": "meminfo qualification deadline exceeded"}
        else:
            record["cleanup_errors"].append({"operation": "qualification_deadline",
                                              "message": "deadline exceeded after first failure"})
    record["all_acquired_observation_fds_closed"] = (
        not record["fd"]["acquired"] or record["fd"]["closed"])
    record["collection_complete"] = (
        record["first_error"] is None and not record["cleanup_errors"] and
        record["fd"]["acquired"] and record["fd"]["closed"] and record["complete_EOF"] and
        record["public_memory_bytes"] is not None)
    if record["collection_complete"]:
        record["state"] = "PASS"
    encoded = json.dumps(record, separators=(",", ":")) + "\n"
    if len(encoded.encode("utf-8")) > MAX_OUTPUT:
        encoded = json.dumps({"schema": 1, "state": "FAILED",
            "first_error": "fixed public output bound exceeded", "collection_complete": False,
            "automatic_retry": False, "normal_build_admission_qualified": False,
            "all_acquired_observation_fds_closed": record["all_acquired_observation_fds_closed"]}) + "\n"
        record["collection_complete"] = False
    sys.stdout.write(encoded)
    sys.stdout.flush()
    return 0 if record["collection_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(observe_once())
