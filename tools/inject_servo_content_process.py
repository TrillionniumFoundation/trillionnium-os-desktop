#!/usr/bin/env python3
"""Deliver the single external content-process SIGKILL for the host gate.

The headed Servo runtime only publishes an identity-bound arm marker and
consumes the receipt.  Keeping dispatch here makes the host qualification
semantics match the D2I systemd helper without embedding a second kill path in
the runtime.
"""
from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import signal
import sys
import time
from typing import NoReturn

from gate_evidence_envelope import load_json_strict
from qemu_safe_io import (
    UnsafePathError,
    has_symlink_component,
    open_regular,
    write_text,
)


POLL_SECONDS = 0.05
IDENTITY_KEYS = frozenset({"generation", "pid", "start_time"})
MAX_STATE_RECORD_BYTES = 4096


def fail(state: Path, reason: str) -> NoReturn:
    print(f"D2I_HOST_EXTERNAL_INJECTOR_FAIL:{reason}", file=sys.stderr)
    try:
        write_text(
            state / "content-crash-proof-diagnostics.txt",
            f"reason={reason}\n",
            "D2I injector diagnostics",
        )
    except (OSError, UnsafePathError, ValueError):
        pass
    raise SystemExit(1)


def read_identity(path: Path) -> dict[str, int]:
    """Read one immutable, duplicate-free content-process identity record."""

    try:
        payload = _read_bounded(path, "D2I content-process identity")
        value = load_json_strict(io.BytesIO(payload))
    except (OSError, UnicodeError, ValueError, UnsafePathError, json.JSONDecodeError) as error:
        raise ValueError("D2I content-process identity is not valid JSON") from error
    if not isinstance(value, dict) or set(value) != IDENTITY_KEYS:
        raise ValueError("D2I content-process identity fields are not exact")
    for key in IDENTITY_KEYS:
        if type(value[key]) is not int:
            raise ValueError(f"D2I content-process identity.{key} is not an integer")
    identity = {key: value[key] for key in IDENTITY_KEYS}
    if identity["generation"] != 1:
        raise ValueError("D2I content-process identity generation is invalid")
    if identity["pid"] <= 1 or identity["start_time"] <= 0:
        raise ValueError("D2I content-process identity values are invalid")
    return identity


def _read_bounded(path: Path, label: str, maximum: int = MAX_STATE_RECORD_BYTES) -> bytes:
    """Read a small regular state record through one no-follow descriptor."""

    descriptor = open_regular(path, label)
    try:
        if os.fstat(descriptor).st_size > maximum:
            raise ValueError(f"{label} exceeds the {maximum}-byte limit")
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            return stream.read(maximum + 1)
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def write_receipt(path: Path, *, pid: int, start_time: int) -> None:
    """Publish the SIGKILL receipt through descriptor-backed atomic I/O."""

    write_text(
        path,
        json.dumps(
            {
                "generation": 1,
                "pid": pid,
                "signal": "SIGKILL",
                "start_time": start_time,
            },
            separators=(",", ":"),
        )
        + "\n",
        "D2I external SIGKILL receipt",
    )


def ready_marker(path: Path) -> bool:
    """Return true only for the exact regular-file arm marker."""

    try:
        return _read_bounded(path, "D2I content-crash arm marker", 128) == b"ready\n"
    except (OSError, UnsafePathError, ValueError):
        return False


def regular_file_present(path: Path, label: str) -> bool:
    """Probe a state file without following a symlink or opening a FIFO."""

    try:
        descriptor = open_regular(path, label)
        os.close(descriptor)
        return True
    except (OSError, UnsafePathError, ValueError):
        return False


def proc_stat(pid: int) -> str | None:
    try:
        return Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None


def start_time(stat: str) -> int | None:
    end = stat.rfind(")")
    if end < 0:
        return None
    fields = stat[end + 2 :].split()
    try:
        return int(fields[19])
    except (IndexError, ValueError):
        return None


def parent_pid(stat: str) -> int | None:
    end = stat.rfind(")")
    if end < 0:
        return None
    fields = stat[end + 2 :].split()
    try:
        return int(fields[1])
    except (IndexError, ValueError):
        return None


def descendants(root: int) -> list[int]:
    result: list[int] = []
    seen = {root}
    frontier = [root]
    while frontier:
        next_frontier: list[int] = []
        for parent in frontier:
            try:
                children = Path(f"/proc/{parent}/task/{parent}/children").read_text()
            except OSError:
                continue
            for token in children.split():
                try:
                    child = int(token)
                except ValueError:
                    continue
                if child in seen:
                    continue
                seen.add(child)
                result.append(child)
                next_frontier.append(child)
        frontier = next_frontier
    return result


def cmdline(pid: int) -> str:
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(
            errors="replace"
        )
    except OSError:
        return ""


def executable(pid: int) -> str | None:
    try:
        return os.path.realpath(f"/proc/{pid}/exe")
    except OSError:
        return None


def identity_matches(pid: int, expected_start: int) -> bool:
    """Re-read procfs immediately before dispatch to avoid PID reuse."""

    current = proc_stat(pid)
    return current is not None and start_time(current) == expected_start


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=float, default=240.0)
    args = parser.parse_args()
    state = args.state_dir
    if has_symlink_component(state):
        fail(state, "external_crash_state_path_unsafe")
    state.mkdir(parents=True, exist_ok=True)
    if has_symlink_component(state) or not state.is_dir() or state.is_symlink():
        fail(state, "external_crash_state_path_unsafe")
    ready = state / "content-crash-ready"
    identity_path = state / "content-process-identity.json"
    receipt = state / "content-sigkill-sent.json"
    deadline = time.monotonic() + args.timeout_seconds

    while time.monotonic() < deadline and not (
        ready_marker(ready)
        and regular_file_present(identity_path, "D2I content-process identity")
    ):
        time.sleep(POLL_SECONDS)
    if not ready_marker(ready):
        fail(state, "external_crash_arm_timeout")
    try:
        identity = read_identity(identity_path)
        generation = identity["generation"]
        expected_pid = identity["pid"]
        expected_start = identity["start_time"]
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        fail(state, "external_crash_identity_malformed")
    if generation != 1 or expected_pid <= 1 or expected_start <= 0:
        fail(state, "external_crash_identity_invalid")

    while time.monotonic() < deadline:
        matches: list[int] = []
        # The content child exposes its embedder as the direct parent.  Resolve
        # that parent from the identity-bearing process rather than relying on
        # the injector's own process tree.
        stat = proc_stat(expected_pid)
        if stat is not None:
            parent = parent_pid(stat)
            if parent is not None:
                runtime_exe = executable(parent)
                for candidate in descendants(parent):
                    text = cmdline(candidate)
                    if "--content-process" in text and executable(candidate) == runtime_exe:
                        matches.append(candidate)
                if len(matches) == 1 and matches[0] == expected_pid:
                    current = proc_stat(expected_pid)
                    if current is not None and start_time(current) == expected_start:
                        break
        time.sleep(POLL_SECONDS)
    else:
        fail(state, "external_crash_target_not_unique")

    # The uniqueness loop above may have yielded to a PID exit/reuse.  Bind
    # the final signal to a fresh procfs identity check immediately before
    # dispatch; a stale PID must never receive the qualification SIGKILL.
    if not identity_matches(expected_pid, expected_start):
        fail(state, "external_crash_target_identity_drifted")
    try:
        os.kill(expected_pid, signal.SIGKILL)
    except OSError:
        fail(state, "external_sigkill_dispatch_failed")
    try:
        write_receipt(receipt, pid=expected_pid, start_time=expected_start)
    except (OSError, UnsafePathError, ValueError):
        fail(state, "external_sigkill_receipt_write_failed")

    while time.monotonic() < deadline:
        if proc_stat(expected_pid) is None:
            print(
                f"D2I host external SIGKILL delivered: pid={expected_pid} "
                f"start_time={expected_start}"
            )
            return
        time.sleep(POLL_SECONDS)
    fail(state, "killed_content_process_still_present")


if __name__ == "__main__":
    main()
