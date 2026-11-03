#!/usr/bin/env python3
"""Adversarial host-oracle tests; fixture bytes never qualify a native guest."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("memory_guest", Path(__file__).with_name("run_g1d_user_memory_guest.py"))
memory = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(memory)
INFO = {"bytes": 8192, "entry": 0x401000}


def apply(role, cap, previous, sample, before, after):
    return (f"G1D_APPLY role={role} sequence=1 cap={cap} previous={previous} revision={previous + 1} "
            f"effective={sample + 5000} consumed={before} before_sample={sample} before_total={before} "
            f"before_start=0 before_used={before} after_sample={sample + 10000} after_total={after} "
            f"after_start=0 after_used={after}")


def prefix():
    lines = ["[hepta-g1d] trusted initial image committed: bytes=8192 entry=0x401000"] * 3
    lines += [f"[hepta-g1d] trusted role committed: role={role} pid={role}" for role in (1, 2, 3)]
    lines += ["[hepta-g1d] initial control activated: manager=1 workload=2 recovery=3 "
              "cap_ns=50000000 period_ns=100000000 lease_ns=300000000000 hepta_durability=false"]
    lines += [f"G1D_BOOT role={role} pid={role} manager=1 workload=2 recovery=3 version=2 bytes=192"
              for role in (1, 2, 3)]
    lines += ["G1DM_HOLDER kind=fork pid=4 parent=2 pages=4608",
              "G1DM_EXEC_CHILD pid=5 parent=2 uid=60001 no_boot=1",
              "G1DM_HOLDER kind=exec pid=5 parent=2 pages=4608"]
    return lines


def valid():
    lines = prefix()
    lines += [f"[hepta-user-memory] denied pid=6 address={address} current_pages=16384 limit_pages=16384"
              for address in (1073741824, 1342177280, 1610612736, 1879048192)]
    lines += ["G1DM_DENIALS pid=6 address=1073741824 pages=6000 shared_address=1342177280 "
              "cow_address=1610612736 file_address=1879048192 "
              "direct_errno=14 shared_errno=14 cow_errno=14 file_errno=14 write_errno=12",
              "G1DM_SATURATED pid=2 fork_pid=4 exec_pid=5 saturator_pid=6 holder_pages=4608 saturator_pages=6000 limit_pages=16384",
              apply(1, 0, 1, 10000000, 1000, 1100),
              "G1DM_RECOVERY_ALLOC role=3 pid=3 pages=16 workload_at_limit=1 physical_reserve=false",
              apply(3, 50000000, 2, 20000000, 1100, 1200),
              "G1DM_RECOVERY_READBACK initial=1 stopped=2 recovered=3 stopped_total=1100 paused_total=1100 cap=50000000 manager_history_terminal=1",
              "G1DM_RETRY pid=6 address=1073741824 same_mappings=1 anonymous=1 shared=1 cow=1 file_fault=1 file_write=1",
              memory.REFUND, memory.COMPLETE]
    return lines


def negative():
    return prefix() + ["G1DM_NO_LIMIT pid=6 pages=16384 held_pages=9216",
                       "G1D_FAIL at=memory_aggregate_limit line=350 errno=0 pid=1 role=1"]


def verdict(lines, code=33, timed_out=False, counterfactual=False):
    return memory.evaluate(("\n".join(lines) + "\n").encode(), code, timed_out, INFO, counterfactual)


class MemoryOracleTests(unittest.TestCase):
    def test_complete_positive_and_exact_negative_are_separate(self):
        result = verdict(valid())
        self.assertTrue(result["passed"], result)
        self.assertFalse(result["counterfactual_only"])
        self.assertFalse(verdict(negative())["passed"])
        result = verdict(negative(), counterfactual=True)
        self.assertTrue(result["passed"], result)
        self.assertFalse(result["positive_oracle_passed"])
        self.assertFalse(verdict(valid(), counterfactual=True)["passed"])

    def test_every_required_observation_is_mandatory(self):
        lines = valid()
        for index, omitted in enumerate(lines):
            with self.subTest(omitted=omitted):
                self.assertFalse(verdict(lines[:index] + lines[index + 1:])["passed"])

    def test_duplicate_records_do_not_qualify(self):
        lines = valid()
        for index, duplicate in enumerate(lines):
            with self.subTest(duplicate=duplicate):
                self.assertFalse(verdict(lines[:index] + [duplicate] + lines[index:])["passed"])

    def test_faults_must_be_exact_owner_address_and_full_limit(self):
        originals = valid()
        cases = [("denied pid=6", "denied pid=4"), ("address=1073741824 current", "address=1073745920 current"),
                 ("current_pages=16384", "current_pages=16383"), ("limit_pages=16384", "limit_pages=32768"),
                 ("shared_errno=14", "shared_errno=12"), ("write_errno=12", "write_errno=14")]
        for before, after in cases:
            with self.subTest(replacement=(before, after)):
                self.assertFalse(verdict([line.replace(before, after) for line in originals])["passed"])

    def test_family_and_exec_identity_cannot_be_substituted(self):
        for before, after in [("parent=2", "parent=3"), ("exec_pid=5", "exec_pid=4"),
                              ("saturator_pid=6", "saturator_pid=3"), ("uid=60001", "uid=0"),
                              ("no_boot=1", "no_boot=0"), ("pages=6000", "pages=9000"),
                              ("saturator_pages=6000", "saturator_pages=100")]:
            with self.subTest(replacement=(before, after)):
                self.assertFalse(verdict([line.replace(before, after) for line in valid()])["passed"])

    def test_recovery_requires_actual_independent_effect_and_readback(self):
        for before, after in [("role=3 pid=3 pages=16", "role=3 pid=2 pages=16"),
                              ("G1D_APPLY role=3", "G1D_APPLY role=1"), ("recovered=3", "recovered=2"),
                              ("paused_total=1100", "paused_total=1101"),
                              ("previous=2 revision=3", "previous=1 revision=2"),
                              ("manager_history_terminal=1", "manager_history_terminal=0")]:
            with self.subTest(replacement=(before, after)):
                self.assertFalse(verdict([line.replace(before, after) for line in valid()])["passed"])

    def test_refund_requires_same_address_and_event_order(self):
        lines = valid()
        for index, line in enumerate(lines):
            if line.startswith("G1DM_RETRY"):
                changed = lines.copy()
                changed[index] = line.replace("address=1073741824", "address=1073745920")
                self.assertFalse(verdict(changed)["passed"])
                changed = lines.copy()
                changed.insert(13, changed.pop(index))
                self.assertFalse(verdict(changed)["passed"])
        changed = lines.copy()
        a, b = next(i for i, line in enumerate(changed) if line.startswith("G1DM_RECOVERY_ALLOC")), -1
        changed[a], changed[b] = changed[b], changed[a]
        self.assertFalse(verdict(changed)["passed"])

    def test_timeout_crash_unknown_or_malformed_record_is_failure(self):
        for code, timeout in [(0, False), (1, False), (None, True), (33, True), (True, False)]:
            with self.subTest(code=code, timeout=timeout):
                self.assertFalse(verdict(valid(), code, timeout)["passed"])
                self.assertFalse(verdict(negative(), code, timeout, True)["passed"])
        for extra in ["Kernel panic", "panicked at marker", "G1DM_UNKNOWN synthetic=true",
                      "SYS_WRITE G1DM_COMPLETE malformed", "G1D_FAIL at=other line=1 errno=12 pid=6 role=2",
                      "[hepta-user-memory] denied pid=7 address=4096 current_pages=16384 limit_pages=16384"]:
            with self.subTest(extra=extra):
                self.assertFalse(verdict(valid() + [extra])["passed"])
                self.assertFalse(verdict(negative() + [extra], counterfactual=True)["passed"])

    def test_negative_rejects_any_other_failure_or_quota_outcome(self):
        for before, after in [("memory_aggregate_limit", "memory_workload_report_timeout"),
                              ("pid=1 role=1", "pid=2 role=2"), ("pages=16384", "pages=16383"),
                              ("held_pages=9216", "held_pages=4608")]:
            with self.subTest(replacement=(before, after)):
                self.assertFalse(verdict([line.replace(before, after) for line in negative()], counterfactual=True)["passed"])
        for line in valid()[13:]:
            with self.subTest(extra=line):
                self.assertFalse(verdict(negative() + [line], counterfactual=True)["passed"])


if __name__ == "__main__":
    unittest.main()
