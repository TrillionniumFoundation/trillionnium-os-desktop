#!/usr/bin/env python3
"""Bounded read-only diagnostics of one already owned Android cgroup.

This module never admits an Android epoch or changes the original epoch guard.
All candidate PIDs come from the exact private daemon's cgroup subtree.  A
reused/moved PID is checked against that scope before its argv is retained.
"""
from pathlib import Path
import json
import os
import stat
import time


MAX_PIDS = 4096
MAX_CGROUPS = 8192
MAX_REPORT_BYTES = 2 * 1024 * 1024
MAX_SECONDS = 8
FILE_LIMITS = {"stat": 8192, "status": 65536, "cmdline": 4096,
               "cgroup": 16384, "cgroup.procs": 65536}
LINK_LIMIT = 4096


class CensusError(RuntimeError):
    pass


def bounded_read(path, limit):
    chunks = []
    size = 0
    with Path(path).open("rb", buffering=0) as stream:
        while True:
            raw = stream.read(min(65536, limit + 1 - size))
            if not raw:
                return b"".join(chunks)
            chunks.append(raw)
            size += len(raw)
            if size > limit:
                raise CensusError("file exceeds explicit byte bound: " + Path(path).name)


def bounded_link(path):
    value = os.readlink(path)
    if len(value.encode("utf-8", "surrogateescape")) > LINK_LIMIT:
        raise CensusError("link exceeds explicit byte bound: " + Path(path).name)
    return value


def error_record(error, operation):
    return {"operation": operation, "type": type(error).__name__,
            "errno": getattr(error, "errno", None), "message": str(error)[:512]}


def unified_group(raw):
    rows = [line[3:] for line in raw.decode("utf-8", "strict").splitlines()
            if line.startswith("0::")]
    if len(rows) != 1 or not rows[0].startswith("/"):
        raise CensusError("unified cgroup identity is absent or ambiguous")
    return rows[0]


def inside(group, root):
    return group == root or group.startswith(root + "/")


def proc_stat(raw):
    text = raw.decode("utf-8", "strict")
    fields = text[text.rindex(")") + 2:].split()
    return int(text.split("(", 1)[0]), int(fields[1]), int(fields[19]), fields[0]


def candidate(pid, group, namespace):
    """Read only an enumerated PID; exclude other scopes before argv/exe."""
    path = Path("/proc") / str(pid)
    operation = "scope-before"
    try:
        first_group = unified_group(bounded_read(path / "cgroup", FILE_LIMITS["cgroup"]))
        if not inside(first_group, group):
            return {"host_pid": pid, "state": "outside-owned-cgroup-before-read"}
        first_stat = proc_stat(bounded_read(path / "stat", FILE_LIMITS["stat"]))
        operation = "pid-namespace"
        pid_namespace = bounded_link(path / "ns/pid")
        if pid_namespace != namespace:
            return {"host_pid": pid, "state": "different-pid-namespace",
                    "cgroup": first_group, "pid_namespace": pid_namespace}
        operation = "status"
        status = dict(line.split(":", 1) for line in
                      bounded_read(path / "status", FILE_LIMITS["status"]).decode("utf-8", "strict").splitlines()
                      if ":" in line)
        operation = "argv"
        argv = [x.decode("utf-8", "strict") for x in
                bounded_read(path / "cmdline", FILE_LIMITS["cmdline"]).split(b"\0") if x]
        operation = "exe-and-mount-namespace"
        executable = bounded_link(path / "exe")
        mount_namespace = bounded_link(path / "ns/mnt")
        operation = "scope-after"
        second_group_raw = bounded_read(path / "cgroup", FILE_LIMITS["cgroup"])
        second_group = unified_group(second_group_raw)
        second_stat = proc_stat(bounded_read(path / "stat", FILE_LIMITS["stat"]))
        if (first_group != second_group or not inside(second_group, group) or
                first_stat[:3] != second_stat[:3] or first_stat[0] != pid or
                first_stat[3] in "ZX" or second_stat[3] in "ZX" or
                bounded_link(path / "ns/pid") != namespace):
            # Do not retain argv/exe from an unbound/moved/reused process.
            return {"host_pid": pid, "state": "identity-or-scope-changed-during-read"}
        uids = [int(x) for x in status["Uid"].split()]
        namespace_pids = [int(x) for x in status["NSpid"].split()]
        if len(uids) != 4 or not namespace_pids:
            raise CensusError("candidate credentials or PID identity incomplete")
        return {"host_pid": pid, "state": "observed-in-owned-cgroup-and-pid-namespace",
                "identity": {"host_pid": pid, "parent_host_pid": first_stat[1],
                             "start_ticks": first_stat[2], "namespace_pids": namespace_pids,
                             "uids": uids, "cmdline": argv, "executable": executable,
                             "namespaces": {"pid": namespace, "mnt": mount_namespace},
                             "cgroup": second_group_raw.decode("utf-8", "strict").splitlines()}}
    except (OSError, ValueError, KeyError, IndexError, UnicodeError, CensusError) as error:
        return {"host_pid": pid, "state": "read-error", "error": error_record(error, operation)}


def group_identity(path):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or stat.S_ISLNK(info.st_mode):
        raise CensusError("cgroup path is not an actual directory")
    return {"device": info.st_dev, "inode": info.st_ino}


def init_identity(init_pid, group):
    namespace = bounded_link(Path("/proc") / str(init_pid) / "ns/pid")
    observed = candidate(init_pid, group, namespace)
    if "identity" not in observed:
        raise CensusError("initial process read failed: " + json.dumps(observed, sort_keys=True))
    value = observed["identity"]
    if (value["host_pid"] != init_pid or value["executable"] != "/system/bin/init" or
            not value["cmdline"] or value["cmdline"][0] != "/init" or
            value["namespace_pids"][-1] != 1 or value["uids"] != [0] * 4):
        raise CensusError("owned Android init identity differs")
    return value


def enumerate_owned_pids(root, deadline):
    """Read actual directories without following cgroup symlinks."""
    errors = []
    directories = [root]
    pids = set()
    visited = 0
    error_bytes = 0
    while directories:
        deadline()
        current = directories.pop()
        visited += 1
        if visited > MAX_CGROUPS:
            raise CensusError("cgroup count bound exceeded")
        try:
            group_identity(current)
            raw = bounded_read(current / "cgroup.procs", FILE_LIMITS["cgroup.procs"])
            for value in raw.split():
                pid = int(value)
                if pid <= 0:
                    raise CensusError("invalid cgroup process ID")
                pids.add(pid)
                if len(pids) > MAX_PIDS:
                    raise CensusError("PID count bound exceeded")
            with os.scandir(current) as entries:
                for entry in entries:
                    if entry.is_symlink():
                        raise CensusError("unexpected cgroup symlink")
                    if entry.is_dir(follow_symlinks=False):
                        directories.append(Path(entry.path))
                        if len(directories) + visited > MAX_CGROUPS:
                            raise CensusError("cgroup count bound exceeded")
        except FileNotFoundError as error:
            # Retain churn, never synthesize the missing membership.
            item = error_record(error, "enumerate-owned-cgroup")
            error_bytes += len(json.dumps(item).encode())
            if error_bytes > MAX_REPORT_BYTES // 8:
                raise CensusError("cgroup exception byte bound exceeded")
            errors.append(item)
    return sorted(pids), visited, errors


def collect(guard, init_pid, group):
    started = time.monotonic_ns()
    report = {"schema": 1, "kind": "owned-private-framework-census-r2",
              "started_monotonic_ns": started, "group": group,
              "bounds": {"pids": MAX_PIDS, "cgroups": MAX_CGROUPS,
                         "report_bytes": MAX_REPORT_BYTES, "seconds": MAX_SECONDS,
                         "file_bytes": FILE_LIMITS, "link_bytes": LINK_LIMIT},
              "records": [], "enumeration_errors": [], "automatic_retry": False,
              "does_not_admit_an_epoch": True, "complete": False}
    # Reserve space for exception records, both init identities, role PID
    # lists and scope metadata; rows receive the remaining bounded budget.
    spent = MAX_REPORT_BYTES // 4

    def deadline():
        if time.monotonic_ns() - started > MAX_SECONDS * 1_000_000_000:
            raise CensusError("census time bound exceeded")

    try:
        if (not isinstance(group, str) or not group.startswith("/system.slice/") or
                len(Path(group).parts) != 3 or not group.endswith("-daemon.service") or
                ".." in Path(group).parts):
            raise CensusError("exact private daemon cgroup required")
        root = Path("/sys/fs/cgroup") / group.lstrip("/")
        report["cgroup_before"] = group_identity(root)
        initial = init_identity(init_pid, group)
        report["init_before"] = initial
        namespace = initial["namespaces"]["pid"]
        pids, visited, enumeration_errors = enumerate_owned_pids(root, deadline)
        report["enumeration_errors"] = enumeration_errors
        report["enumerated_cgroups"] = visited
        report["enumerated_pids"] = sorted(pids)
        for pid in sorted(pids):
            deadline()
            row = candidate(pid, group, namespace)
            cost = len(json.dumps(row, sort_keys=True).encode())
            if spent + cost > MAX_REPORT_BYTES:
                raise CensusError("report byte bound exceeded")
            spent += cost
            report["records"].append(row)
        report["role_matches"] = {
            role: [row["host_pid"] for row in report["records"]
                   if "identity" in row and tuple(row["identity"]["cmdline"]) == spec[0]]
            for role, spec in guard["ROLES"].items()}
        report["cgroup_after"] = group_identity(root)
        report["init_after"] = init_identity(init_pid, group)
        report["scope_stable"] = (report["cgroup_before"] == report["cgroup_after"] and
                                  report["init_before"] == report["init_after"])
        deadline()
        report["complete"] = report["scope_stable"] and not report["enumeration_errors"]
    except (OSError, ValueError, KeyError, IndexError, UnicodeError, CensusError) as error:
        report["error"] = error_record(error, "collect-owned-census")
        if "init_before" in report and "init_after" not in report:
            try:
                report["init_after"] = init_identity(init_pid, group)
                report["init_unchanged_after_collection_error"] = report["init_before"] == report["init_after"]
            except (OSError, ValueError, KeyError, IndexError, UnicodeError, CensusError) as after_error:
                report["init_after_error"] = error_record(after_error, "init-after-collection-error")
    report["finished_monotonic_ns"] = time.monotonic_ns()
    if len(json.dumps(report, sort_keys=True).encode()) > MAX_REPORT_BYTES:
        return {"schema": 1, "kind": report["kind"], "group": group,
                "complete": False, "error": {"type": "CensusError", "message": "complete report byte bound exceeded"},
                "records_retained": False, "started_monotonic_ns": started,
                "finished_monotonic_ns": report["finished_monotonic_ns"]}
    return report


def capture_initial(scope, guard_check, *, now=time.monotonic, sleep=time.sleep,
                    budget_seconds=30):
    """Wait only for an initial strict epoch, before any probe mutation.

    Only the original missing/ambiguous-role error permits another read.  No
    epoch is replaced, no case is invoked here, and every failed read remains
    in a create-only receipt.  Other guard failures propagate immediately.
    """
    if scope["PRIVATE_EPOCH"] is not None:
        raise CensusError("a private epoch is already fixed; recapture is prohibited")
    if budget_seconds != 30:
        raise CensusError("initial-readiness budget must remain exactly 30 seconds")
    started = now()
    deadline = started + budget_seconds
    attempt = 0
    while True:
        guard_check()
        daemon = [row for row in scope["ROWS"] if row["role"] == "daemon"]
        if len(daemon) != 1:
            raise CensusError("one exact owned daemon required")
        census = collect(scope["EPOCH_GUARD"], scope["INIT"]["pid"], daemon[0]["group"])
        prefix = "private-framework-initial-" + str(attempt)
        scope["save"](prefix + "-census.json", census)
        if not census["complete"]:
            raise CensusError("incomplete or unstable private framework census")
        guard_check()
        if now() >= deadline:
            raise CensusError("initial epoch readiness deadline expired before strict capture")
        try:
            epoch = scope["current_guest_epoch"]()
        except scope["EPOCH_GUARD"]["EpochError"] as error:
            receipt = {"attempt": attempt, "error": repr(error), "guard_receipt": error.receipt(),
                       "elapsed_seconds": now() - started, "probe_actions_attempted": False,
                       "original_epoch_guard_unchanged": True, "retry_is_read_only_initial_readiness":
                       error.code == "FRAMEWORK_PROCESS_SET_AMBIGUOUS_OR_MISSING"}
            scope["save"](prefix + "-capture-error.json", receipt)
            guard_check()
            if error.code != "FRAMEWORK_PROCESS_SET_AMBIGUOUS_OR_MISSING" or now() >= deadline:
                raise
            sleep(min(1.0, max(0.0, deadline - now())))
            # No next observation starts after the fixed deadline.  Its last
            # individual bounded read can finish after it; no action can.
            if now() >= deadline:
                raise
            attempt += 1
            continue
        guard_check()
        if now() > deadline or epoch["binding"]["processes"]["init"] != census["init_after"]:
            raise CensusError("initial epoch was captured outside its time or init binding")
        scope["PRIVATE_EPOCH"] = epoch
        guard_check()
        scope["save"]("private-framework-epoch.json", epoch)
        scope["save"]("private-framework-initial-readiness.json", {
            "state": "FIRST_STRICT_PRIVATE_EPOCH_FIXED", "attempts": attempt + 1,
            "elapsed_seconds": now() - started, "epoch_sha256": epoch["sha256"],
            "probe_actions_attempted": False, "automatic_case_retry": False,
            "original_epoch_guard_unchanged": True, "will_not_recapture_after_action": True})
        return epoch
