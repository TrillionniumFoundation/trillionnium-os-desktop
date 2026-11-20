#!/usr/bin/env python3
"""Bind an Android UI flow to its init and framework process generation.

This is a read-only guard, not an Android launcher. Capture immediately before
reading UI, require the same epoch after that observation, and retain that epoch
for every action based on it. A changed epoch requires a new observation and a
new decision. It never licenses replaying an action with an unknown outcome.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Callable, TypeVar

T = TypeVar("T")
SCHEMA = "pocket4-framework-epoch-v1"
ROLES = {
    "zygote64": (("zygote64",), "/system/bin/app_process64", 0),
    "system_server": (("system_server",), "/system/bin/app_process64", 1000),
    "surfaceflinger": (("/system/bin/surfaceflinger",), "/system/bin/surfaceflinger", 1000),
}


class EpochError(RuntimeError):
    def __init__(self, code: str, *, action_attempted: bool = False):
        super().__init__(code)
        self.code = code
        self.action_attempted = action_attempted
        self.outcome_unknown = action_attempted
        self.automatic_retry = False

    def receipt(self) -> dict:
        return {"ok": False, "error": self.code,
                "action_attempted": self.action_attempted,
                "outcome_unknown": self.outcome_unknown, "automatic_retry": False}


def _stat(pid: int) -> tuple[int, int, int, str]:
    raw = Path(f"/proc/{pid}/stat").read_text()
    # comm can contain spaces and parentheses. Fields following its final ')'
    # have fixed positions: state=3, ppid=4, starttime=22.
    fields = raw[raw.rindex(")") + 2:].split()
    return int(raw.split("(", 1)[0]), int(fields[1]), int(fields[19]), fields[0]


def process_identity(pid: int) -> dict:
    if type(pid) is not int or pid <= 0:
        raise EpochError("INVALID_PROCESS_ID")
    try:
        path = Path(f"/proc/{pid}")
        before = _stat(pid)
        status = dict(line.split(":", 1) for line in (path / "status").read_text().splitlines()
                      if ":" in line)
        identity = {
            "host_pid": pid, "parent_host_pid": before[1], "start_ticks": before[2],
            "namespace_pids": [int(x) for x in status["NSpid"].split()],
            "uids": [int(x) for x in status["Uid"].split()],
            "cmdline": [x.decode("utf-8", "strict")
                        for x in (path / "cmdline").read_bytes().split(b"\0") if x],
            "executable": os.readlink(path / "exe"),
            "namespaces": {name: os.readlink(path / "ns" / name) for name in ("pid", "mnt")},
            "cgroup": (path / "cgroup").read_text().splitlines(),
        }
        after = _stat(pid)
        if before[:3] != after[:3] or after[0] != pid or before[3] in "ZX" or after[3] in "ZX":
            raise EpochError("PROCESS_IDENTITY_UNSTABLE")
        if not identity["cmdline"] or not identity["namespace_pids"] or len(identity["uids"]) != 4:
            raise EpochError("PROCESS_IDENTITY_INCOMPLETE")
        return identity
    except (OSError, ValueError, KeyError, IndexError, UnicodeError) as exc:
        raise EpochError("PROCESS_IDENTITY_UNAVAILABLE") from exc


def _digest(binding: dict) -> str:
    raw = json.dumps(binding, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def capture_processes(roles: dict[str, int]) -> dict:
    """Read an explicitly selected process set; also used by real-process tests."""
    if not roles or len(set(roles.values())) != len(roles):
        raise EpochError("INVALID_PROCESS_SET")
    started = time.monotonic_ns()
    boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    first = {role: process_identity(pid) for role, pid in sorted(roles.items())}
    second = {role: process_identity(pid) for role, pid in sorted(roles.items())}
    finished = time.monotonic_ns()
    if first != second or not 0 <= finished - started <= 5_000_000_000:
        raise EpochError("PROCESS_SET_UNSTABLE")
    if Path("/proc/sys/kernel/random/boot_id").read_text().strip() != boot:
        raise EpochError("BOOT_CHANGED")
    binding = {"boot_id": boot, "processes": second}
    return {"schema": SCHEMA, "binding": binding, "sha256": _digest(binding),
            "collected_monotonic_ns": finished}


def capture_android(init_pid: int) -> dict:
    """Discover framework processes inside an already verified Android cell.

    The caller must first validate the daemon's cell identity and resource
    limits. This guard supplements those checks; it does not replace them.
    zygote's Linux comm is often 'main', so discovery uses argv[0].
    """
    init = process_identity(init_pid)
    if (init["executable"] != "/system/bin/init" or init["cmdline"][0] != "/init"
            or init["namespace_pids"][-1] != 1 or init["uids"] != [0, 0, 0, 0]):
        raise EpochError("ANDROID_INIT_UNVERIFIED")
    matches: dict[str, list[int]] = {name: [] for name in ROLES}
    for path in Path("/proc").iterdir():
        if not path.name.isdecimal():
            continue
        try:
            argv = tuple(x.decode("utf-8", "strict")
                         for x in (path / "cmdline").read_bytes().split(b"\0") if x)
            role = next((name for name, spec in ROLES.items() if argv == spec[0]), None)
            if role and os.readlink(path / "ns/pid") == init["namespaces"]["pid"]:
                matches[role].append(int(path.name))
        except (FileNotFoundError, ProcessLookupError, PermissionError, UnicodeError):
            continue
    if any(len(pids) != 1 for pids in matches.values()):
        raise EpochError("FRAMEWORK_PROCESS_SET_AMBIGUOUS_OR_MISSING")
    snapshot = capture_processes({"init": init_pid, **{name: pids[0] for name, pids in matches.items()}})
    processes = snapshot["binding"]["processes"]
    if processes["init"] != init:
        raise EpochError("ANDROID_INIT_CHANGED")
    root_groups = [line[3:] for line in init["cgroup"] if line.startswith("0::")]
    if len(root_groups) != 1 or root_groups[0] == "/":
        raise EpochError("ANDROID_CGROUP_UNVERIFIED")
    for role, (_, executable, uid) in ROLES.items():
        identity = processes[role]
        groups = [line[3:] for line in identity["cgroup"] if line.startswith("0::")]
        parent = processes["zygote64"]["host_pid"] if role == "system_server" else init_pid
        if (identity["executable"] != executable or identity["uids"] != [uid] * 4
                or identity["parent_host_pid"] != parent
                or identity["namespaces"]["pid"] != init["namespaces"]["pid"]
                or len(groups) != 1
                or not (groups[0] == root_groups[0] or groups[0].startswith(root_groups[0] + "/"))):
            raise EpochError("FRAMEWORK_PROCESS_UNVERIFIED")
    # Apps and zygote have private mount namespaces. Pin each one's actual
    # namespace; requiring all of them to equal init's would reject valid cells.
    require_unchanged(snapshot)
    return snapshot


def require_unchanged(snapshot: dict, *, action_attempted: bool = False) -> None:
    try:
        if (snapshot.get("schema") != SCHEMA
                or snapshot.get("sha256") != _digest(snapshot["binding"])):
            raise EpochError("INVALID_EPOCH_DOCUMENT")
        roles = {role: identity["host_pid"]
                 for role, identity in snapshot["binding"]["processes"].items()}
        current = capture_processes(roles)
        if current["binding"] != snapshot["binding"]:
            raise EpochError("FRAMEWORK_EPOCH_CHANGED")
    except (EpochError, OSError, KeyError, TypeError, ValueError) as exc:
        # Never rediscover and silently adopt replacement framework processes.
        code = "INVALID_EPOCH_DOCUMENT" if isinstance(exc, EpochError) and exc.code == "INVALID_EPOCH_DOCUMENT" else "FRAMEWORK_EPOCH_CHANGED_OR_UNAVAILABLE"
        raise EpochError(code, action_attempted=action_attempted) from exc


def execute_bound(snapshot: dict, operation: Callable[[], T]) -> T:
    """Run at most once. Preserve transport errors and identify epoch changes.

    Callers should save transport receipts before returning from operation.
    A successful return proves epoch continuity, not visual/business success.
    """
    require_unchanged(snapshot, action_attempted=False)
    try:
        result = operation()
    except BaseException as operation_error:
        try:
            require_unchanged(snapshot, action_attempted=True)
        except EpochError as epoch_error:
            raise epoch_error from operation_error
        raise
    require_unchanged(snapshot, action_attempted=True)
    return result
