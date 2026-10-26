#!/usr/bin/env python3
"""Host-oracle rejection tests. Fixture bytes never qualify a real guest."""
import copy
import gzip
import importlib.util
import itertools
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location("g1d_guest", Path(__file__).with_name("run_g1d_guest.py"))
g1d = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(g1d)
NEGATIVE_SPEC = importlib.util.spec_from_file_location("g1d_workload_negative", Path(__file__).with_name("run_g1d_workload_negative.py"))
negative = importlib.util.module_from_spec(NEGATIVE_SPEC)
NEGATIVE_SPEC.loader.exec_module(negative)
INFO = {"bytes": 8192, "entry": 0x401000}


def fixture_credentials(phase, pid=2, root=False):
    values = {key: 0 for key in g1d.CREDENTIAL_KEYS}
    values.update(pid=pid, sid=2)
    for key in g1d.CREDENTIAL_KEYS[1:9]:
        values[key] = 0 if root else 60001
    if root:
        values.update(groups=1, effective=(1 << 41) - 1, permitted=(1 << 41) - 1, bounding=(1 << 41) - 1)
    else:
        values.update(nnp=1, securebits=195)
    return "G1D_WORKLOAD_CREDS phase=" + phase + " " + " ".join(key + "=" + str(values[key]) for key in g1d.CREDENTIAL_KEYS)


def fixture_workload():
    lines = [fixture_credentials("initial")]
    lines.extend(f"G1D_WORKLOAD_SIGNAL target={target} signal={signal} rc=-1 errno=1"
                 for target, signal in g1d.SIGNAL_CASES)
    lines.extend(f"G1D_WORKLOAD_BOUNDARY name={name} rc=-1 errno={error}" for name, error in g1d.BOUNDARY_CASES)
    lines.extend((fixture_credentials("after_denials"), fixture_address_space("initial", 2),
                  fixture_address_space("after_fork", 4), fixture_credentials("after_exec", pid=4),
                  fixture_address_space("after_exec", 4), g1d.WORKLOAD_ISOLATED))
    return lines


def fixture_pids():
    lines = ["G1D_PIDS_INITIAL pid=2 max=16 current=1"]
    lines.extend(f"G1D_PIDS_BOUNDARY name={name} rc=-1 errno=13" for name in g1d.PIDS_BOUNDARY_NAMES)
    lines.extend((g1d.PIDS_ROLLBACK, g1d.PIDS_DESCENDANTS,
                  "G1D_PIDS_ROLE_RESERVE role=1 pid=1 child=10 workload_current=16 root_member=1 child_exit=0",
                  "G1D_PIDS_ROLE_RESERVE role=3 pid=3 child=11 workload_current=16 root_member=1 child_exit=0",
                  g1d.PIDS_FORK_REFUND, g1d.PIDS_ZOMBIES, g1d.PIDS_THREADS,
                  "G1D_PIDS_NONLEADER_EXEC pid=12 parent=2 current=2 max=16 old_leader_refunded=1",
                  g1d.PIDS_EXEC_REFUND, g1d.PIDS_COMPLETE))
    return lines


def fixture_address_space(phase, pid):
    values = dict(pid=pid, soft=g1d.WORKLOAD_AS_BYTES, hard=g1d.WORKLOAD_AS_BYTES,
                  after_soft=g1d.WORKLOAD_AS_BYTES, after_hard=g1d.WORKLOAD_AS_BYTES,
                  oversized_bytes=g1d.WORKLOAD_AS_BYTES, oversized_rc=-1, oversized_errno=12,
                  raise_hard_rc=-1, raise_hard_errno=1, invalid_soft_rc=-1, invalid_soft_errno=22,
                  mapped_page_bytes=4096, page_roundtrip=1)
    return "G1D_WORKLOAD_ADDRESS_SPACE phase=" + phase + " " + " ".join(key + "=" + str(values[key]) for key in g1d.ADDRESS_KEYS)


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
    lines.extend((g1d.PIDS_ZOMBIE_RETAINED, g1d.PIDS_ACCOUNTING))
    lines.extend(fixture_workload())
    lines.extend(fixture_pids())
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
                  fixture_apply(1, 1025, 25_000_000, 1025, 690_000_000, 9000, 9100, 1000, 1100),
                  "G1D_PREFIX_RETIRED through=512 next=1026 old_D=retired manager_ack=denied",
                  "G1D_USER_STOP_CONFIRMED pid=2 signal=19 sample=691000000 total=9200 heartbeat=31 revision=1026",
                  "G1D_MANAGER_EXEC_BEGIN sequence=1025",
                  "G1D_EXEC_REVOKED old_fd_errno=116 no_auxv=true own_history=denied recovery_history=terminal sequence=1025",
                  fixture_apply(3, 2, 50_000_000, 1026, 695_000_000, 9200, 9200, 1200, 1200),
                  "G1D_RECOVERY_PRESERVED_USER_STOP sample_a=696000000 sample_b=916000000 total_a=9200 total_b=9200 "
                  "heartbeat_a=31 heartbeat_b=31 revision=1027",
                  "G1D_RECOVERY_SINGLE_USE_DENIED sequence=3 revision=1027 requested_cap=0 status=2",
                  "G1D_USER_RESUME_REQUIRED total=10000 heartbeat=40 revision=1027 signal=18",
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

    def test_pids_limits_threads_zombies_and_rollbacks_are_required(self):
        raw = valid_serial()
        mutations = ((b"max=16", b"max=17"), (b"current=16", b"current=15"),
                     (b"thread_errno=11", b"thread_errno=12"),
                     (b"parent_fork_errno=11", b"parent_fork_errno=0"),
                     (b"grandchildren=14", b"grandchildren=0"),
                     (b"thread_cases=2", b"thread_cases=0"),
                     (b"retained=15", b"retained=0"), (b"wnowait_refunded=0", b"wnowait_refunded=1"),
                     (b"after_one_reap=15", b"after_one_reap=16"),
                     (b"retained_leader=3", b"retained_leader=2"),
                     (b"zombie_populated=0", b"zombie_populated=1"),
                     (b"old_leader_refunded=1", b"old_leader_refunded=0"),
                     (b"memory_controller=false", b"memory_controller=true"))
        for old, new in mutations:
            with self.subTest(old=old):
                self.assertIn(old, raw)
                self.assertFalse(self.verdict(raw.replace(old, new, 1)))

    def test_pids_boundaries_and_reserve_role_identities_are_exact(self):
        raw = valid_serial()
        mutations = ((b"name=raise_limit rc=-1 errno=13", b"name=raise_limit rc=4 errno=0"),
                     (b"name=membership rc=-1 errno=13", b"name=membership rc=-1 errno=2"),
                     (b"role=1 pid=1 child=10 workload_current=16", b"role=1 pid=2 child=10 workload_current=16"),
                     (b"role=3 pid=3 child=11", b"role=3 pid=3 child=10"),
                     (b"root_member=1", b"root_member=0"),
                     (b"pid=12 parent=2", b"pid=12 parent=3"),
                     (b"pid=12 parent=2", b"pid=10 parent=2"))
        for old, new in mutations:
            with self.subTest(old=old):
                self.assertIn(old, raw)
                self.assertFalse(self.verdict(raw.replace(old, new, 1)))

    def test_pids_observations_are_ordered_and_scope_stays_bounded(self):
        raw = valid_serial()
        for marker in (g1d.PIDS_ACCOUNTING, g1d.PIDS_DESCENDANTS, g1d.PIDS_ZOMBIES, g1d.PIDS_COMPLETE):
            line = (marker + "\n").encode()
            self.assertFalse(self.verdict(raw.replace(line, b"", 1) + line), marker)
        report = g1d.evaluate_positive(raw, 33, False, INFO)["workload_pids_isolation"]
        self.assertTrue(report["passed"])
        self.assertFalse(report["memory_controller_qualified"])
        self.assertFalse(report["cgroup_removal_with_retained_tasks_supported"])

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

    def test_every_workload_identity_capability_and_exec_flag_is_measured(self):
        raw = valid_serial()
        for phase in ("initial", "after_denials", "after_exec"):
            original = next(line for line in raw.splitlines() if line.startswith(
                ("G1D_WORKLOAD_CREDS phase=" + phase + " ").encode()))
            for key in g1d.CREDENTIAL_KEYS:
                with self.subTest(phase=phase, key=key):
                    parts = original.decode().split()
                    position = next(index for index, part in enumerate(parts) if part.startswith(key + "="))
                    value = int(parts[position].split("=")[1])
                    # An exec child may legitimately have any fresh PID.
                    parts[position] = key + "=" + str(2 if phase == "after_exec" and key == "pid" else value + 1)
                    self.assertFalse(self.verdict(raw.replace(original, " ".join(parts).encode(), 1)))

    def test_workload_signal_and_process_memory_denials_cannot_be_replaced_by_labels(self):
        raw = valid_serial()
        for line in raw.splitlines():
            if line.startswith((b"G1D_WORKLOAD_SIGNAL ", b"G1D_WORKLOAD_BOUNDARY ")):
                with self.subTest(line=line):
                    self.assertFalse(self.verdict(raw.replace(line, line.replace(b"rc=-1", b"rc=0"), 1)))
                    prefix, error = line.rsplit(b"errno=", 1)
                    self.assertFalse(self.verdict(raw.replace(line, prefix + b"errno=" + str(int(error) + 1).encode(), 1)))
        initial = next(line for line in raw.splitlines() if line.startswith(b"G1D_WORKLOAD_CREDS phase=initial"))
        self.assertFalse(self.verdict(initial + b"\n" + raw.replace(initial + b"\n", b"", 1)))

    def test_address_limit_actual_enforcement_and_fork_exec_inheritance_are_required(self):
        raw = valid_serial()
        for line in raw.splitlines():
            if not line.startswith(b"G1D_WORKLOAD_ADDRESS_SPACE"):
                continue
            for word in line.split()[2:]:
                key, value = word.split(b"=", 1)
                changed = key + b"=" + str(int(value) + 1).encode()
                with self.subTest(phase=line.split()[1], field=key):
                    self.assertFalse(self.verdict(raw.replace(line, line.replace(word, changed, 1), 1)))
            self.assertFalse(self.verdict(raw.replace(line + b"\n", b"", 1) + line + b"\n"))
        self.assertFalse(self.verdict(raw.replace(b"ADDRESS_SPACE phase=after_fork", b"ADDRESS_SPACE phase=initial", 1)))

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

    def test_manager_fault_recovery_never_substitutes_for_explicit_user_continue(self):
        raw = valid_serial()
        for pattern in (g1d.USER_STOP, g1d.USER_PAUSED, g1d.RECOVERY_USED, g1d.USER_RESUME):
            line = next(line for line in raw.splitlines() if pattern.fullmatch(line.decode()))
            for word in line.split()[1:]:
                key, value = word.split(b"=", 1)
                changed = key + b"=" + str(int(value) + 1).encode()
                # Times/counters may vary inside their permitted interval.
                # Identity, state equality and fixed signal/status fields may not.
                if key in (b"sample", b"sample_a", b"sample_b", b"total", b"heartbeat"):
                    continue
                with self.subTest(pattern=pattern.pattern, field=key):
                    self.assertFalse(self.verdict(raw.replace(line, line.replace(word, changed, 1), 1)))
            self.assertFalse(self.verdict(raw.replace(line + b"\n", b"", 1) + line + b"\n"))
        for old, new in ((b"sample_b=916000000", b"sample_b=895999999"),
                         (b"total=10000 heartbeat=40", b"total=9200 heartbeat=40"),
                         (b"total=10000 heartbeat=40", b"total=10000 heartbeat=31"),
                         (b"sample=691000000", b"sample=689000000"),
                         (b"sample_a=696000000", b"sample_a=694000000")):
            self.assertFalse(self.verdict(raw.replace(old, new, 1)), (old, new))

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


def root_serial(boot_order=(3, 1, 2)):
    prefix = valid_serial(boot_order).split(b"G1D_WORKLOAD_CREDS phase=initial", 1)[0]
    lines = [fixture_credentials("initial", root=True),
             "G1D_WORKLOAD_SIGNAL target=manager signal=0 rc=0 errno=0",
             "G1D_WORKLOAD_SIGNAL target=recovery signal=0 rc=0 errno=0",
             "G1D_FAIL at=workload_privilege_boundary line=438 errno=0 pid=2 role=2",
             "G1D_RECOVERY_READY",
             "G1D_FAIL at=workload_really_running line=687 errno=0 pid=1 role=1"]
    return prefix + ("\n".join(lines) + "\n").encode()


class RootWorkloadNegativeTests(unittest.TestCase):
    def verdict(self, raw, code=33, timeout=False):
        return g1d.evaluate_root_workload(raw, code, timeout, INFO)["passed"]

    def test_exact_old_root_observation_is_required_and_positive_gate_rejects(self):
        for order in itertools.permutations((1, 2, 3)):
            raw = root_serial(order)
            self.assertTrue(self.verdict(raw))
            self.assertFalse(g1d.evaluate_positive(raw, 33, False, INFO)["passed"])
        self.assertFalse(self.verdict(valid_serial()))
        self.assertFalse(self.verdict(b"G1D_FAIL at=workload_privilege_boundary\n"))

    def test_missing_duplicate_and_malformed_raw_records_are_rejected(self):
        raw = root_serial()
        for line in raw.splitlines():
            with self.subTest(line=line):
                self.assertFalse(self.verdict(raw.replace(line + b"\n", b"", 1)))
                self.assertFalse(self.verdict(raw + line + b"\n"))
                self.assertFalse(self.verdict(raw.replace(line, line + b" extra", 1)))

    def test_every_root_credential_field_and_both_real_signal_results_are_required(self):
        raw = root_serial()
        line = next(line for line in raw.splitlines() if line.startswith(b"G1D_WORKLOAD_CREDS"))
        for key in g1d.CREDENTIAL_KEYS:
            field = next(word for word in line.split() if word.startswith((key + "=").encode()))
            changed = (key + "=" + str(int(field.split(b"=", 1)[1]) + 1)).encode()
            with self.subTest(key=key):
                self.assertFalse(self.verdict(raw.replace(line, line.replace(field, changed, 1), 1)))
        for old, new in ((b"phase=initial", b"phase=after_denials"), (b"rc=0", b"rc=-1"),
                         (b"signal=0", b"signal=9"), (b"rc=0 errno=0", b"rc=0 errno=1"),
                         (b"at=workload_privilege_boundary", b"at=workload_read_capabilities"),
                         (b"at=workload_really_running", b"at=heartbeat_read"),
                         (b"pid=2 role=2", b"pid=3 role=3"), (b"pid=1 role=1", b"pid=3 role=3")):
            self.assertFalse(self.verdict(raw.replace(old, new, 1)), (old, new))

    def test_timeout_panic_other_success_and_out_of_order_failure_are_rejected(self):
        raw = root_serial()
        for code, timeout in ((0, False), (65, False), (True, False), (33, True)):
            self.assertFalse(self.verdict(raw, code, timeout))
        for extra in (b"Kernel panic\n", b"G1D_UNREVIEWED\n", b"G1D_WORKLOAD_NO_AUTHORITY\n",
                      b"[hepta-g1d] bypassed\n", (g1d.WORKLOAD_ISOLATED + "\n").encode()):
            self.assertFalse(self.verdict(raw + extra))
        for label in (b"G1D_WORKLOAD_CREDS", b"G1D_WORKLOAD_SIGNAL target=manager", b"G1D_FAIL at=workload_privilege_boundary"):
            line = next(line for line in raw.splitlines() if line.startswith(label))
            self.assertFalse(self.verdict(raw.replace(line + b"\n", b"", 1) + line + b"\n"))

    def test_recovery_timeout_never_qualifies_the_root_mutation(self):
        raw = root_serial()
        manager_failure = next(line for line in raw.splitlines()
                               if line.startswith(b"G1D_FAIL at=workload_really_running "))
        timeout = b"G1D_FAIL at=ipc_timeout line=329 errno=2 pid=3 role=3\n"
        # An unrelated recovery timeout before PID 1 diagnoses the absent
        # heartbeat must remain inadmissible even with the intended unsafe
        # observations. The probe must fix its deadline order instead.
        self.assertFalse(self.verdict(raw.replace(manager_failure + b"\n",
                                                 timeout + manager_failure + b"\n", 1)))
        self.assertFalse(self.verdict(raw + timeout))
        self.assertFalse(self.verdict(raw.replace(manager_failure + b"\n", timeout, 1)))

    def test_frozen_source_mutation_cannot_change_probe_or_gate(self):
        original = b"before\n" + negative.BEFORE + b"after\n"
        changed = negative.mutation(original)
        self.assertEqual(changed, b"before\n" + negative.AFTER + b"after\n")
        for source in (b"absent", original + negative.BEFORE, original + negative.AFTER):
            with self.assertRaises(ValueError):
                negative.mutation(source)
        def row(data):
            return {"mode": "100644", "size": len(data), "sha256": g1d.digest(data)}
        before = {"files": {negative.SOURCE: row(original), "tests/unchanged.c": row(b"probe")}}
        after = copy.deepcopy(before)
        after["files"][negative.SOURCE] = row(changed)
        negative.verify_delta(before, after, original, changed)
        extra = copy.deepcopy(after)
        extra["files"]["tests/unchanged.c"] = row(b"forged")
        added = copy.deepcopy(after)
        added["files"]["new-input"] = row(b"new")
        mode = copy.deepcopy(after)
        mode["files"][negative.SOURCE]["mode"] = "100755"
        for invalid in (extra, added, mode, before):
            with self.assertRaises(ValueError):
                negative.verify_delta(before, invalid, original, changed)
        with self.assertRaises(ValueError):
            negative.verify_delta(before, after, original, changed + b"other edit")

    def test_formatted_credential_selection_and_current_source_remain_exact(self):
        # Formatting and explicit workload-ID construction must still select
        # exactly one reviewed workload expression in the tracked source.
        for before, after in negative.SELECTIONS:
            original = b"before\n" + before + b"after\n"
            self.assertEqual(negative.mutation(original), b"before\n" + after + b"after\n")
            for extra in (after, *(selection[0] for selection in negative.SELECTIONS)):
                with self.assertRaises(ValueError):
                    negative.mutation(original + extra)
        path = negative.ROOT / negative.SOURCE
        source = path.read_bytes()
        changed = negative.mutation(source)
        self.assertEqual(source.count(negative.IDENTIFIED_BEFORE), 1)
        self.assertEqual(changed, source.replace(negative.IDENTIFIED_BEFORE, negative.IDENTIFIED_AFTER, 1))
        self.assertNotIn(b"workload_credentials(WORKLOAD_ID)?", changed)
        self.assertEqual(path.read_bytes(), source, "the control must not edit the production source")

    def test_unreviewed_workload_identity_is_not_a_valid_mutation_target(self):
        for call in (b"workload_credentials(0)?", b"workload_credentials(OTHER_ID)?"):
            source = negative.IDENTIFIED_BEFORE.replace(b"workload_credentials(WORKLOAD_ID)?", call)
            with self.assertRaisesRegex(ValueError, "absent or ambiguous"):
                negative.mutation(source)


if __name__ == "__main__":
    unittest.main()
