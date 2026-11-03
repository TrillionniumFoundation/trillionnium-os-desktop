#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Strict oracle shared by the Linux reference and native Unix DONTWAIT probe."""
import errno
import json
import os

KINDS = ("stream", "seqpacket", "dgram")
CASES = (
    "empty_recv_dontwait", "recv_preserves_shared_flags", "ordinary_recv_timeout",
    "ordinary_recv_wakeup", "recv_child_reaped", "full_send_dontwait",
    "send_preserves_shared_flags", "ordinary_send_wakeup",
    "send_child_reaped_payload_preserved", "wakeup_payload_readback", "final_shared_flags",
)
EXPECTED = [(kind, case) for kind in KINDS for case in CASES]
OLD_BLOCKING = {
    ("stream", "full_send_dontwait"), ("seqpacket", "full_send_dontwait"),
    ("dgram", "empty_recv_dontwait"), ("dgram", "full_send_dontwait"),
}


def check(data, exit_code, timed_out=False, *, guest=False, expect_old_blocking=False):
    errors = []
    records = []
    summaries = []
    prefix = b'{"suite":"unix_dontwait"'
    for raw in data.splitlines():
        if prefix not in raw:
            continue
        if not raw.startswith(prefix):
            errors.append("interleaved probe record")
            continue
        try:
            item = json.loads(raw)
        except (ValueError, UnicodeError):
            errors.append("invalid probe JSON")
            continue
        (summaries if item.get("summary") is True else records).append(item)
    if timed_out:
        errors.append("outer timeout is never an accepted counterexample")
    if [(v.get("socket"), v.get("case")) for v in records] != EXPECTED:
        errors.append("record inventory/order mismatch")
    want_failures = OLD_BLOCKING if expect_old_blocking else set()
    failed = set()
    for item in records:
        identity = item.get("socket"), item.get("case")
        case = identity[1]
        if set(item) != {"suite", "socket", "case", "passed", "return", "errno", "elapsed_us"}:
            errors.append("unexpected record fields")
            continue
        if any(type(item.get(k)) is not int for k in ("return", "errno", "elapsed_us")):
            errors.append("noninteger observation")
            continue
        if type(item["passed"]) is not bool or item["elapsed_us"] < 0:
            errors.append("invalid pass or elapsed field")
            continue
        ret, err, elapsed = item["return"], item["errno"], item["elapsed_us"]
        ok = item["passed"]
        if not ok:
            failed.add(identity)
        if case in ("empty_recv_dontwait", "full_send_dontwait"):
            expected_delay = identity in want_failures
            valid_delay = 375000 <= elapsed < 2000000 if expected_delay else elapsed < 250000
            if ret != -1 or err not in (errno.EAGAIN, errno.EWOULDBLOCK) or not valid_delay:
                errors.append(f"wrong nonblocking observation: {identity}")
            if ok == expected_delay:
                errors.append(f"wrong nonblocking assertion: {identity}")
        elif case == "ordinary_recv_timeout":
            if not (ok and ret == -1 and err in (errno.EAGAIN, errno.EWOULDBLOCK)
                    and 375000 <= elapsed < 2000000):
                errors.append(f"ordinary timeout changed: {identity}")
        elif case in ("ordinary_recv_wakeup", "ordinary_send_wakeup"):
            expected_size = 1 if case == "ordinary_recv_wakeup" else 1024
            if not (ok and ret == expected_size and err == 0 and 10000 <= elapsed < 750000):
                errors.append(f"ordinary wakeup changed: {identity}")
        elif "shared_flags" in case:
            if not (ok and ret >= 0 and ret == err and not ret & os.O_NONBLOCK):
                errors.append(f"shared flags changed: {identity}")
        elif "child_reaped" in case:
            if not (ok and ret > 0 and err == 0):
                errors.append(f"child failed/unreaped: {identity}")
        elif case == "wakeup_payload_readback":
            if not (ok and ret == 1024 and err == 0):
                errors.append(f"payload readback failed: {identity}")
        else:
            errors.append("unrecognized case")
    if failed != want_failures:
        errors.append("unexpected failed checks")
    summary = {"suite": "unix_dontwait", "summary": True, "checks": len(EXPECTED),
               "failures": len(want_failures)}
    if summaries != [summary]:
        errors.append("missing/duplicate/inconsistent complete summary")
    probe_exit = 1 if expect_old_blocking else 0
    if guest:
        marker = f"UNIX_DONTWAIT_PROBE_EXIT={probe_exit}".encode()
        lines = data.splitlines()
        if lines.count(marker) != 1 or sum(b"UNIX_DONTWAIT_PROBE_EXIT=" in s for s in lines) != 1:
            errors.append("missing/duplicate/wrong probe exit marker")
        if lines.count(b"TRILLIONNIUM_A01_BOOT_OK") != 1:
            errors.append("missing/duplicate ordinary boot marker")
        if exit_code != 33:
            errors.append("ordinary QEMU did not exit 33")
    elif exit_code != probe_exit:
        errors.append("unexpected Linux process exit")
    return {"passed": not errors, "checks": len(records), "errors": errors,
            "counterexample_accepted": expect_old_blocking and not errors,
            "product_passed": not expect_old_blocking and not errors}
