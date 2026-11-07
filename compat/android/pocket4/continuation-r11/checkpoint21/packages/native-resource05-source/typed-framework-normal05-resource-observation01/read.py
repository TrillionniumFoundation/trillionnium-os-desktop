#!/usr/bin/env python3
"""One fixed /proc/meminfo observation. No admission, build, writes or retry."""
import datetime, hashlib, json, os, stat, sys, time

PATH = "/proc/meminfo"
LIMIT = 16384
QUALIFICATION_SECONDS = 2.0
MIN_AVAILABLE = 15 * 1024**3
PLANNED_BUILD_RAM = 10 * 1024**3

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


def identity(info):
    return {name: getattr(info, "st_" + name) for name in
            ("dev", "ino", "mode", "uid", "gid", "nlink", "rdev", "size")}

def observe():
    started = time.monotonic()
    def alive():
        require(time.monotonic() - started < QUALIFICATION_SECONDS,
                "RESOURCE_OBSERVATION_QUALIFICATION_DEADLINE")
    report = {
        "schema": 1, "kind": "normal05-fixed-meminfo-observation01",
        "state": "OBSERVING", "path": PATH,
        "qualification_seconds": QUALIFICATION_SECONDS,
        "historical_failure": {
            "job_id": "1a1b0622030-fc05-701e",
            "outer_terminal_sha256": "539e0485f9787367ddf1e3c3224851a72fce9d6132941d1ce892a7e4629bf7b6",
            "resource_receipt_sha256": "3ae8a164fd6b83340308ce1d4e2656808ddb77cbfc411872c6d06b21ef10d098"},
        "planned_build_profile": {
            "memory_max_bytes": PLANNED_BUILD_RAM, "memory_swap_max_bytes": 0,
            "minimum_fresh_MemAvailable_bytes": MIN_AVAILABLE,
            "admission_difference_bytes": MIN_AVAILABLE - PLANNED_BUILD_RAM,
            "global_swap_is_owned_budget": False},
        "descriptor_acquired": False, "descriptor_close_attempted": False,
        "all_acquired_fds_closed": False, "complete": False,
        "raw_meminfo": None, "parsed_bytes": None, "threshold_observed_met": None,
        "first_error": None, "close_errors": [], "build_admission_authorized": False,
        "build_owned_limits_read": False, "normal05_request_created": False,
        "automatic_retry": False, "process_children": 0, "filesystem_writes": 0,
        "Main_actions": 0, "Android_actions": 0, "runtime_authorization_enabled": False,
        "production_ready": False}
    fd = None
    try:
        alive()
        report["named_before"] = identity(os.stat(PATH, follow_symlinks=False))
        fd = os.open(PATH, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        report["descriptor_acquired"] = True
        held = os.fstat(fd)
        report["held_before"] = identity(held)
        require(stat.S_ISREG(held.st_mode) and held.st_uid == 0 and held.st_gid == 0,
                "FIXED_MEMINFO_FILE_SHAPE")
        require(not os.get_inheritable(fd), "FIXED_MEMINFO_FD_INHERITABLE")
        require(report["held_before"] == report["named_before"], "FIXED_MEMINFO_OPEN_RACE")
        chunks, total = [], 0
        while True:
            alive()
            part = os.read(fd, LIMIT + 1 - total)
            if not part:
                break
            chunks.append(part)
            total += len(part)
            require(total <= LIMIT, "FIXED_MEMINFO_BYTE_BOUND")
        raw = b"".join(chunks)
        require(0 < len(raw) <= LIMIT, "FIXED_MEMINFO_BYTE_BOUND")
        # Preserve the complete bounded public source before its semantic parsing.
        report["raw_meminfo"] = {
            "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
            "raw_ascii": raw.decode("ascii", "strict"), "complete_EOF": True}
        report["read_completed_utc"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        report["read_completed_unix_ns_decimal"] = str(time.time_ns())
        report["held_after"] = identity(os.fstat(fd))
        report["named_after"] = identity(os.stat(PATH, follow_symlinks=False))
        require(report["named_before"] == report["held_before"] ==
                report["held_after"] == report["named_after"], "FIXED_MEMINFO_IDENTITY_CHANGED")
        values = parse_admission_meminfo(raw)
        report["parsed_bytes"] = values
        report["threshold_observed_met"] = values["MemAvailable"] >= MIN_AVAILABLE
        report["difference_from_threshold_bytes"] = values["MemAvailable"] - MIN_AVAILABLE
        alive()
    except BaseException as error:
        report["first_error"] = {"type": type(error).__name__, "error": repr(error)}
    finally:
        if fd is not None:
            report["descriptor_close_attempted"] = True
            try:
                os.close(fd)
            except BaseException as error:
                report["close_errors"].append({"type": type(error).__name__, "error": repr(error)})
        report["all_acquired_fds_closed"] = not report["close_errors"]
    report["elapsed_seconds"] = time.monotonic() - started
    if report["elapsed_seconds"] >= QUALIFICATION_SECONDS and report["first_error"] is None:
        report["first_error"] = {"type": "TimeoutError", "error": "RESOURCE_OBSERVATION_QUALIFICATION_DEADLINE"}
    report["complete"] = report["first_error"] is None and report["all_acquired_fds_closed"]
    report["state"] = "OBSERVED_NOT_BUILD_ADMISSION" if report["complete"] else "FAILED"
    return report

if __name__ == "__main__":
    report = observe()
    print(json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True), flush=True)
    sys.exit(0 if report["complete"] else 1)
