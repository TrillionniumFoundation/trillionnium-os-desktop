#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Counterfeit/incomplete evidence must not satisfy the native gate.

These are parser tests only; generated transcripts never qualify a kernel.
"""
import sys
from pathlib import Path
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_g1d_watchdog_guest as gate


def apply(role, previous, cap):
    return (f"G1D_APPLY role={role} sequence=1 cap={cap} previous={previous} revision={previous + 1} "
            "effective=1000000000 consumed=0 before_sample=900000000 before_total=0 before_start=900000000 "
            "before_used=0 after_sample=1100000000 after_total=0 after_start=1100000000 after_used=0")


def transcript(kind):
    lines = []
    for role in (1, 2, 3):
        lines.extend(["[hepta-g1d] trusted initial image committed: bytes=100 entry=0x400000",
                      f"[hepta-g1d] trusted role committed: role={role} pid={role}"])
    lines.append("[hepta-g1d] initial control activated: manager=1 workload=2 recovery=3 "
                 "cap_ns=50000000 period_ns=100000000 lease_ns=300000000000 hepta_durability=false")
    lines.extend(f"G1D_BOOT role={role} pid={role} manager=1 workload=2 recovery=3 version=2 bytes=192" for role in (1, 2, 3))
    lines.append(apply(1, 1, 0 if kind == "zero" else 25_000_000))
    if kind != "healthy":
        lines.append(f"G1DW_MANAGER_CLOSE case={kind} original_revision=2 failure=exec_revoke")
    if kind == "recovered":
        lines.append(apply(3, 2, 50_000_000))
    if kind == "restore":
        lines.extend(["G1DW_RECEIPT previous=2 revision=3 effective=7000000100 consumed=0 stable_low=2 stable_high=1", gate.ONE_USE])
    if kind != "healthy":
        lines.append(gate.REPEAT)
    if kind == "stopped":
        lines.append(gate.CONTINUE)
    status, cap, revision, stopped = {"restore": (1, 50_000_000, 3, 0), "healthy": (0, 25_000_000, 2, 0),
        "zero": (2, 0, 2, 0), "stopped": (3, 25_000_000, 2, 1), "recovered": (2, 50_000_000, 3, 0)}[kind]
    lines.append(f"G1DW_RESULT case={kind} status={status} cap={cap} revision={revision} due=7000000000 "
                 f"expires=32000000000 evaluated={0 if kind == 'healthy' else 7000000100} stopped={stopped} user_pause_intent_available=0")
    lines.append(f"G1DW_COMPLETE case={kind} timer=true original_owner=true durable=false reserve=false")
    return "\n".join(lines).encode()


class OracleTests(unittest.TestCase):
    def evaluate(self, raw, kind="restore", code=33, timeout=False):
        return gate.evaluate(raw, code, timeout, {"bytes": 100, "entry": 0x400000}, kind)["passed"]

    def test_all_documented_scenarios(self):
        for kind in gate.CASES:
            with self.subTest(kind=kind):
                self.assertTrue(self.evaluate(transcript(kind), kind))

    def test_failure_or_missing_tail_cannot_pass(self):
        raw = transcript("restore")
        for changed, code, timed_out in [
            (raw, 0, False), (raw, 33, True), (raw.rsplit(b"\n", 1)[0], 33, False),
            (raw + b"\nG1D_FAIL at=watchdog line=3 errno=0 pid=3 role=3", 33, False),
            (raw + b"\nKernel panic", 33, False),
        ]:
            self.assertFalse(self.evaluate(changed, code=code, timeout=timed_out))

    def test_wrong_owner_revision_deadline_or_receipt_cannot_pass(self):
        raw = transcript("restore")
        for before, after in [
            (b"G1D_APPLY role=1", b"G1D_APPLY role=3"),
            (b"G1DW_RECEIPT previous=2", b"G1DW_RECEIPT previous=1"),
            (b"effective=7000000100", b"effective=6999999999"),
            (b"expires=32000000000", b"expires=40000000000"),
            (b"evaluated=7000000100", b"evaluated=32000000000"),
            (b"status=1 cap=50000000 revision=3", b"status=1 cap=50000000 revision=4"),
            (b"stable_low=2 stable_high=1", b"stable_low=0 stable_high=0"),
        ]:
            with self.subTest(before=before):
                self.assertFalse(self.evaluate(raw.replace(before, after)))

    def test_duplicate_markers_and_new_authority_claim_are_rejected(self):
        raw = transcript("restore")
        for extra in (gate.REPEAT, gate.ONE_USE, "G1DW_CLAIM trusted_user_pause=true", "G1D_BOOT role=1 pid=1 manager=1 workload=2 recovery=3 version=2 bytes=192"):
            self.assertFalse(self.evaluate(raw + b"\n" + extra.encode()))

    def test_zero_or_stopped_must_not_be_restored(self):
        for kind in ("zero", "stopped"):
            self.assertFalse(self.evaluate(transcript("restore"), kind))
            self.assertFalse(self.evaluate(transcript(kind).replace(b"revision=2 due=", b"revision=3 due="), kind))

    def test_automatic_recovery_has_no_recovery_request(self):
        raw = transcript("restore").replace(gate.ONE_USE.encode(), apply(3, 2, 50_000_000).encode() + b"\n" + gate.ONE_USE.encode())
        self.assertFalse(self.evaluate(raw))


if __name__ == "__main__":
    unittest.main()
