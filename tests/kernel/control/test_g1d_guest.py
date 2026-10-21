#!/usr/bin/env python3
"""Host-oracle rejection tests. Fixture bytes never qualify a real guest."""
import gzip
import importlib.util
import itertools
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("g1d_guest", Path(__file__).with_name("run_g1d_guest.py"))
g1d = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(g1d)
INFO = {"bytes": 8192, "entry": 0x401000}


def fixture_apply(role, sequence, cap, previous, sample, before, after, used_before=None, used_after=None):
    start = sample // 100_000_000 * 100_000_000
    used_before = before if used_before is None else used_before
    used_after = after if used_after is None else used_after
    consumed = used_before
    return (f"G1D_APPLY role={role} sequence={sequence} cap={cap} previous={previous} revision={previous + 1} "
            f"effective={sample + 5000} consumed={consumed} before_sample={sample} before_total={before} "
            f"before_start={start} before_used={used_before} after_sample={sample + 10000} after_total={after} "
            f"after_start={start} after_used={used_after}")


def valid_serial(boot_order=(3, 1, 2)):
    lines = []
    for role in (1, 2, 3):
        lines.extend(("[hepta-g1d] trusted initial image committed: bytes=8192 entry=0x401000",
                      f"[hepta-g1d] trusted role committed: role={role} pid={role}"))
    lines.append("[hepta-g1d] initial control activated: manager=1 workload=2 recovery=3 "
                 "cap_ns=50000000 period_ns=100000000 lease_ns=300000000000 hepta_durability=false")
    lines.extend(f"G1D_BOOT role={role} pid={role} manager=1 workload=2 recovery=3 version=2 bytes=192"
                 for role in boot_order)
    lines.extend(("G1D_WORKLOAD_NO_AUTHORITY", "G1D_RECOVERY_READY",
                  "G1D_QUERYABI_OK supported_ops=62 max_request=40 max_response=64 features=0"))
    lines.extend((fixture_apply(1, 1, 25_000_000, 2, 10_000_000, 1000, 2000),
                  fixture_apply(1, 2, 25_000_000, 3, 11_000_000, 2000, 3000),
                  "G1D_SAME_VALUE_NEW_D_PRESERVES_USAGE",
                  "G1D_COPYOUT_REPLAY sequence=3 errno=14 revision=5 exact_bytes=true conflicts=2",
                  "G1D_STALE_REVISION_TERMINAL sequence=4 saved_status=5",
                  "G1D_STATIC_AND_GAP_DO_NOT_RESERVE next=5",
                  fixture_apply(1, 5, 50_000_000, 5, 12_000_000, 3000, 4000),
                  "G1D_CEILING_REFUSAL_TERMINAL sequence=6 saved_status=2",
                  "G1D_FORK_CHILD_NO_AUTHORITY", "G1D_FORK_SCM_NO_AUTHORITY"))
    lines.extend(f"G1D_LEGACY_ALIAS_DENIED kind={kind} errno=13"
                 for kind in ("cpu_max", "migrate_into", "migrate_out", "disable_controller"))
    lines.extend((fixture_apply(1, 7, 0, 6, 13_000_000, 4000, 4000),
                  "G1D_ZERO_CAP_STOPPED sample_a=240000000 sample_b=440000000 total_a=4000 total_b=4000 "
                  "heartbeat_a=12 heartbeat_b=12 revision=7",
                  fixture_apply(3, 1, 50_000_000, 7, 450_000_000, 4000, 5000, 0, 1000),
                  "G1D_INDEPENDENT_RECOVERY resumed_total=8000 revision=8 own_sequence=1",
                  fixture_apply(1, 8, 1, 8, 680_000_000, 8000, 8100, 0, 100),
                  fixture_apply(1, 9, 999, 9, 681_000_000, 8100, 8200, 100, 200),
                  fixture_apply(1, 10, 1001, 10, 682_000_000, 8200, 8300, 200, 300),
                  fixture_apply(1, 11, 50_000_000, 11, 683_000_000, 8300, 8400, 300, 400),
                  "G1D_SUBMICROSECOND_CAPS_EXACT cases=3",
                  "G1D_FULL_WINDOW capacity=1024 refused_sequence=1025 old_results=retained revision=1025",
                  fixture_apply(1, 1025, 50_000_000, 1025, 690_000_000, 9000, 9100, 1000, 1100),
                  "G1D_PREFIX_RETIRED through=512 next=1026 old_D=retired manager_ack=denied",
                  "G1D_MANAGER_EXEC_BEGIN sequence=1025",
                  "G1D_EXEC_REVOKED old_fd_errno=116 no_auxv=true own_history=denied recovery_history=terminal sequence=1025",
                  "G1D_RECOVERY_RETIRED_AFTER_MANAGER_EXEC through=1025 next=1026",
                  "G1D_RECOVERY_STOPPED", "G1D_CHILDREN_REAPED workload_signal=15 recovery_exit=0",
                  "G1D_COMPLETE native_manage=true history=true hepta_durability=false hardware=false"))
    return ("\n".join(lines) + "\n").encode()


class VerdictTests(unittest.TestCase):
    def verdict(self, raw, code=33, timed_out=False):
        return g1d.evaluate_positive(raw, code, timed_out, INFO)["passed"]

    def test_fixture_describes_the_oracle_and_independent_boot_order(self):
        for order in itertools.permutations((1, 2, 3)):
            self.assertTrue(self.verdict(valid_serial(order)), order)

    def test_complete_real_exit_is_required(self):
        for code in (None, 0, 1, 65, True, 33.0):
            self.assertFalse(self.verdict(valid_serial(), code), code)
        self.assertFalse(self.verdict(valid_serial(), 33, True))

    def test_every_fixed_record_is_required_once(self):
        for marker in g1d.MARKERS:
            line = (marker + "\n").encode()
            with self.subTest(marker=marker):
                self.assertFalse(self.verdict(valid_serial().replace(line, b"", 1)))
                self.assertFalse(self.verdict(valid_serial() + line))

    def test_every_dynamic_record_is_required_once(self):
        for line in valid_serial().splitlines():
            if not any(pattern.fullmatch(line.decode()) for pattern in g1d.DYNAMIC):
                continue
            with self.subTest(line=line):
                self.assertFalse(self.verdict(valid_serial().replace(line + b"\n", b"", 1)))
                self.assertFalse(self.verdict(valid_serial() + line + b"\n"))

    def test_all_three_sealed_images_precede_any_resume(self):
        raw = valid_serial()
        for old, new in ((b"bytes=8192", b"bytes=8193"), (b"role=2 pid=2", b"role=2 pid=3"),
                         (b"manager=1 workload=2 recovery=3", b"manager=1 workload=2 recovery=2"),
                         (b"version=2 bytes=192", b"version=1 bytes=192")):
            self.assertFalse(self.verdict(raw.replace(old, new, 1)))
        activation = next(line for line in raw.splitlines() if b"initial control activated:" in line)
        self.assertFalse(self.verdict(raw.replace(activation + b"\n", b"") + activation + b"\n"))
        role = b"[hepta-g1d] trusted role committed: role=3 pid=3\n"
        self.assertFalse(self.verdict(raw.replace(role, b"") + role))

    def test_native_revision_exact_caps_and_accounting_cannot_be_replaced(self):
        raw = valid_serial()
        mutations = ((b"previous=3 revision=4", b"previous=2 revision=3"),
                     (b"cap=999 ", b"cap=0 "), (b"cap=1001 ", b"cap=1000 "),
                     (b"consumed=2000 ", b"consumed=0 "),
                     (b"before_total=2000 ", b"before_total=500 "),
                     (b"after_total=3000 ", b"after_total=1999 "),
                     (b"before_start=0 ", b"before_start=1 "),
                     (b"effective=10005000 ", b"effective=9999999 "),
                     (b"after_used=3000\n", b"after_used=1999\n"),
                     (b"previous=1025 revision=1026", b"previous=1024 revision=1025"))
        for old, new in mutations:
            self.assertIn(old, raw)
            self.assertFalse(self.verdict(raw.replace(old, new, 1)), (old, new))

    def test_stopped_workload_and_independent_recovery_are_measured(self):
        raw = valid_serial()
        mutations = ((b"sample_b=440000000", b"sample_b=439999999"),
                     (b"total_b=4000", b"total_b=4001"),
                     (b"heartbeat_b=12", b"heartbeat_b=13"),
                     (b"heartbeat_a=12 heartbeat_b=12", b"heartbeat_a=0 heartbeat_b=0"),
                     (b"resumed_total=8000", b"resumed_total=4000"),
                     (b"revision=8 own_sequence=1", b"revision=7 own_sequence=1"),
                     (b"G1D_APPLY role=3 sequence=1", b"G1D_APPLY role=1 sequence=1"))
        for old, new in mutations:
            self.assertFalse(self.verdict(raw.replace(old, new, 1)), (old, new))

    def test_receipts_history_and_old_linux_aliases_fail_closed(self):
        raw = valid_serial()
        for old, new in ((b"errno=14 revision=5", b"errno=14 revision=4"),
                         (b"exact_bytes=true", b"exact_bytes=false"),
                         (b"kind=cpu_max errno=13", b"kind=cpu_max errno=1"),
                         (b"capacity=1024", b"capacity=128"),
                         (b"old_results=retained revision=1025", b"old_results=retained revision=1024"),
                         (b"old_fd_errno=116", b"old_fd_errno=1"),
                         (b"manager_ack=denied", b"manager_ack=allowed")):
            self.assertFalse(self.verdict(raw.replace(old, new, 1)), (old, new))

    def test_causal_order_and_no_failure_are_required(self):
        raw = valid_serial()
        for label in (b"G1D_FULL_WINDOW", b"G1D_ZERO_CAP_STOPPED", b"G1D_MANAGER_EXEC_BEGIN"):
            line = next(line for line in raw.splitlines() if line.startswith(label))
            self.assertFalse(self.verdict(raw.replace(line + b"\n", b"") + line + b"\n"))
        for extra in (b"G1D_FAIL at=assertion\n", b"G1D_FORGED_SUCCESS\n", b"Kernel panic\n",
                      b"[hepta-g1d] bypassed image verification\n"):
            self.assertFalse(self.verdict(raw + extra))

    def test_rejected_images_cannot_commit_a_role_or_resume(self):
        for reason in ("manifest-byte-mismatch", "truncated-snapshot"):
            raw = (f"[hepta-g1d] rejected initial image: {reason}\n"
                   "panicked at init: failed to run the init process\n").encode()
            self.assertTrue(g1d.evaluate_rejection(raw, 65, False, reason)["passed"])
            for line in (b"G1D_BOOT role=2\n", b"G1C_INIT_STARTED pid=1\n",
                         b"[hepta-g1d] trusted role committed: role=3 pid=3\n",
                         b"[hepta-g1d] initial control activated: manager=1\n"):
                self.assertFalse(g1d.evaluate_rejection(raw + line, 65, False, reason)["passed"])
            for code, timeout in ((33, False), (True, False), (65, True)):
                self.assertFalse(g1d.evaluate_rejection(raw, code, timeout, reason)["passed"])
            self.assertFalse(g1d.evaluate_rejection(raw * 2, 65, False, reason)["passed"])
            self.assertFalse(g1d.evaluate_rejection(b"Kernel panic\n", 65, False, reason)["passed"])


class InitramfsTests(unittest.TestCase):
    def test_three_variants_preserve_every_original_entry_and_init(self):
        init = b"#!/bin/sh\necho original-init\n"
        entries = [("init", [1, 0o100755, 0, 0, 1, 123, len(init), 0, 0, 0, 0, 5, 0], init),
                   ("test", [2, 0o40755, 0, 0, 2, 456, 0, 0, 0, 0, 0, 5, 0], b"")]
        original = gzip.compress(g1d.replay.pack(entries), mtime=0)
        probe = bytes(range(256)) * 4
        for data in (probe, probe[:-1] + bytes([probe[-1] ^ 1]), probe[:-1]):
            result = g1d.replay.unpack(gzip.decompress(g1d.build_initramfs(original, data)))
            self.assertEqual(result[:-1], entries)
            self.assertEqual(result[-1], ("test/g1d-init", [3, 0o100755, 0, 0, 1, 0, len(data),
                                                           0, 0, 0, 0, 14, 0], data))


if __name__ == "__main__":
    unittest.main()
