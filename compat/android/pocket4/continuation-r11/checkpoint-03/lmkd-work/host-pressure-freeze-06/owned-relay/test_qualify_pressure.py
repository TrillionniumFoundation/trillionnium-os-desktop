#!/usr/bin/env python3
"""Synthetic evidence controls only; no kernel PSI or Android execution."""
import copy
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest

import qualify_pressure as q

NS = 1_000_000_000
SOURCE_PIN, BUILD_PIN = "a" * 64, "b" * 64


def fixture(phase="pressure"):
    nonce, generation, lease = "1" * 64, "2" * 64, "3" * 64
    budget = struct.pack("<QQQII", q.HARD, q.HIGH, 0, 0, 1).hex()
    events0 = "low 0\nhigh 0\nmax 0\noom 0\noom_kill 0\noom_group_kill 0\n"
    events1 = events0.replace("high 0", "high 5")
    psi0 = "some avg10=0.00 avg60=0.00 avg300=0.00 total=0\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=0\n"
    psi1 = psi0.replace("some avg10=0.00 avg60=0.00 avg300=0.00 total=0", "some avg10=0.00 avg60=0.00 avg300=0.00 total=900000").replace("full avg10=0.00 avg60=0.00 avg300=0.00 total=0", "full avg10=0.00 avg60=0.00 avg300=0.00 total=750000")
    active_end = 6_200_000_000 if phase == "pressure" else 8_400_000_000
    retired = active_end + NS
    final_current = 350 * q.MIB if phase == "pressure" else 416 * q.MIB
    binaries = {"actor": "4" * 64, "driver": "5" * 64, "broker": "6" * 64, "android_lmkd": q.LMKD_SHA}
    manifest = {"schema": 1, "phase": phase, "source_manifest_sha256": SOURCE_PIN,
                "matching_build_receipt_sha256": BUILD_PIN, "binaries_sha256": binaries}
    data = {
        "staging-result.json": {"ok": True, "all_source_and_copied_hashes_matched": True,
                                 "actor_sha256": binaries["actor"], "lmkd_sha256": q.LMKD_SHA},
        "inner-preflight.json": {"domain_dev": 30, "domain_ino": 40, "cgroup_dev": 30, "cgroup_ino": 40,
                                  "pid": 1, "ppid": 0, "domain_relative": "/domain", "state_noexec": True,
                                  "closed_inherited_fds": True},
        "outer-preflight.json": {"domain_dev": 30, "domain_ino": 40, "bootstrap_host_pid": 100, "child_host_pid": 101},
        "relay-projection.json": {"device": 20, "inode": 50, "uid": 1069, "gid": 1069, "mode": 0o600},
        "driver-result.json": {"ok": True, "phase": phase, "nonce": nonce, "actual_broker": True,
                               "owner_pid": 100, "init_pid": 101, "same_cell_retry_denied": True,
                               "broker_retired_and_reaped": True, "owner_and_init_exited": True,
                               "android_enrollment": True, "joined_host_audit_present": True,
                               "pressure_workload_requested": True, "domain_populated": False,
                               "installed_supervisor_changed": False, "bootstrap_rights": 16,
                               "real_pressure_verified": False},
        "phase-result.json": {"ok": True, "phase": phase, "marked_contract_rejected": True,
                              "real_protocol_verified": True, "actual_relay_hup_verified": True,
                              "nonvictim_cleanup_verified": True,
                              "pressure_workload_complete": True, "host_audit_required": True,
                              "real_pressure_verified": False, "route": "PIDFD-only minimal root",
                              "production_cgroup_kill_qualified": False, "pid_reuse_qualified": False},
        "lmkd-post-registration-pressure-file.json": {"pressure_device": 30, "pressure_inode": 44,
                                                      "cgroup_device": 30, "cgroup_inode": 40},
        "pressure-workload.json": {"phase": phase, "workload_complete": True, "host_audit_required": True,
                                   "real_pressure_verified": False, "protected_targets_alive": True,
                                   "budget_unchanged": True, "max": q.HARD, "high": q.HIGH,
                                   "first_kill_current_cap": q.CAP, "peak_observed_current": 416 * q.MIB,
                                   "final_current": final_current, "cached_bytes": 64 * q.MIB,
                                   "foreground_bytes": 128 * q.MIB, "allocator_bytes": 190 * q.MIB,
                                   "quiet_started_ns": 2 * NS, "quiet_completed_ns": 4_200_000_000,
                                   "pressure_start_ns": 4_300_000_000, "allocation_finished_ns": 4_900_000_000,
                                   "quiet_end_ns": active_end, "events_before": events0, "events_after": events1,
                                   "some_before": 0, "some_after": 900000, "full_before": 0, "full_after": 750000,
                                   "stopped_ns": 0 if phase == "pressure" else 4_250_000_000,
                                   "resume_ns": 0 if phase == "pressure" else 7_200_000_000,
                                   "cached_exit_observed_ns": 4_950_000_000 if phase == "pressure" else 0,
                                   "kill_count": 1 if phase == "pressure" else 0},
        "identities.json": {"lmkd_pid": 2, "lmkd_start": 90, "children": [
            {"label": name, "pid": i + 3, "uid": 10001 + i, "start": 100 + i, "pidfd": 10 + i, "oom_score_adj": adj}
            for i, (name, adj) in enumerate((("cached", 900), ("foreground", 0), ("protected", -1000), ("sentinel", 0), ("allocator", 0)))]},
    }
    data["target-cleanup.json"] = {"lmkd_reaped_before_nonvictim_check": True, "children": [
        {"label": target["label"], "pid": target["pid"], "uid": target["uid"], "start": target["start"],
         "known_cached_victim": phase == "pressure" and target["label"] == "cached",
         "exit_code": -1 if phase == "pressure" and target["label"] == "cached" else 0,
         "exit_signal": 9 if phase == "pressure" and target["label"] == "cached" else 0}
        for target in data["identities.json"]["children"]]}
    for state, name, granted in (("Ready", "broker-ready.json", False), ("Active", "broker-active.json", True),
                                  ("Retired", "broker-retired.json", True)):
        data[name] = {"state": state, "nonce": nonce, "generation": generation, "endpoint_device": 20,
                      "endpoint_inode": 50, "cgroup_device": 30, "cgroup_inode": 40, "budget_hex": budget,
                      "granted": granted, "faulted": False}
    regs = []
    for level, stall, trigger in ((1, 70_000, "some 70000 1000000"), (2, 700_000, "full 700000 1000000")):
        regs.append({"level": level, "window_us": 1_000_000, "stall_us": stall, "trigger": trigger,
                     "bytes_written": len(trigger), "pressure_device": 30, "pressure_inode": 44,
                     "write_started_ns": NS, "write_completed_ns": NS + 10000})
    data["broker-pressure-audit.json"] = {
        "schema": 1, "source": "actual-registration-write-and-POLLPRI-send-after-joined-retirement",
        "nonce": nonce, "authority_generation": generation, "lease_generation": lease,
        "cgroup_device": 30, "cgroup_inode": 40, "budget_hex": budget, "granted": True, "faulted": False,
        "incomplete": False, "overflow": False, "observations": 2, "packets_queued": 2, "stop_reason": 1,
        "retired_monotonic_ns": retired, "registrations": regs, "events": [
            {"level": 1, "sequence": 1, "observed_ns": 4_500_000_000, "send_completed_ns": 4_500_010_000},
            {"level": 2, "sequence": 1, "observed_ns": 4_800_000_000, "send_completed_ns": 4_800_010_000},
        ],
    }
    for name in ("quiet-before.json", "quiet-after.json", "pressure-before.json", "after-relay-hup.json",
                 "pressure-after.json" if phase == "pressure" else "stale-after.json"):
        quiet = name in ("quiet-before.json", "quiet-after.json", "pressure-before.json")
        data[name] = {"current": 352 * q.MIB if quiet else final_current, "max": str(q.HARD) + "\n",
                      "high": str(q.HIGH) + "\n", "events": events0 if quiet else events1,
                      "pressure": psi0 if quiet else psi1}
    if phase == "pressure":
        data["cached-exit.json"] = {"pid": 3, "start": 100, "si_code": 2, "si_status": 9,
                                    "observed_monotonic_ns": 4_950_000_000}
        data["cached-kill-notification.json"] = {"pid": 3, "uid": 10001, "bytes": 16, "command": 6,
                                                 "rss_kib": 65540, "observed_monotonic_ns": 5 * NS}
        data["cached-kill-diagnostic.json"] = {"pid": 3, "uid": 10001, "oom_score_adj": 900,
                                               "line": "Kill 'owned-cached' (3), uid 10001, oom_score_adj 900 to free 65540kB rss; reason: device is not responding"}
    else:
        data["pressure-relief.json"] = {"released_bytes": 190 * q.MIB, "monotonic_ns": active_end + 10_000,
                                        "current": 226 * q.MIB, "all_targets_alive": True,
                                        "kill_count": 0, "budget_changed": False}
        data["after-relay-hup.json"]["current"] = 226 * q.MIB
    assert set(data) == q.required_names(phase)
    return manifest, data


class QualificationControls(unittest.TestCase):
    def reject(self, change, phase="pressure"):
        manifest, data = fixture(phase)
        change(data)
        with self.assertRaises(q.Rejected):
            q.qualified(manifest, data, phase)

    def test_synthetic_critical_positive_scope_is_narrow(self):
        manifest, data = fixture()
        result = q.qualified(manifest, data, "pressure")
        self.assertEqual(result["qualification_status"], "pass")
        self.assertTrue(result["fresh_critical_event_correlated_with_cached_exit"])
        self.assertFalse(result["all_apps_production_ready"])
        self.assertFalse(result["external_main_unit_cleanup_fences_verified_here"])

    def test_medium_only_is_partial_and_not_critical_pass(self):
        manifest, data = fixture()
        audit = data["broker-pressure-audit.json"]
        audit["events"] = audit["events"][:1]
        audit["observations"] = audit["packets_queued"] = 1
        data["cached-kill-diagnostic.json"]["line"] = data["cached-kill-diagnostic.json"]["line"].replace("device is not responding", "low watermark is breached")
        result = q.qualified(manifest, data, "pressure")
        self.assertEqual(result["qualification_status"], "partial_medium_only")
        self.assertFalse(result["fresh_critical_event_correlated_with_cached_exit"])

    def test_stale_requires_real_events_and_keeps_targets(self):
        manifest, data = fixture("stale")
        result = q.qualified(manifest, data, "stale")
        self.assertTrue(result["stale_actual_queue_zero_kill_verified"])
        self.assertEqual(result["fresh_levels_correlated_with_cached_exit"], [])

    def test_no_real_event_or_incomplete_audit_rejected(self):
        def empty(data):
            audit = data["broker-pressure-audit.json"]
            audit["events"] = []
            audit["observations"] = audit["packets_queued"] = 0
        self.reject(empty)
        self.reject(empty, "stale")
        for key, value in (("incomplete", True), ("overflow", True), ("observations", 3), ("packets_queued", 1), ("stop_reason", 3)):
            with self.subTest(key=key):
                self.reject(lambda data, key=key, value=value: data["broker-pressure-audit.json"].update({key: value}))

    def test_changed_native_default_or_actual_write_rejected(self):
        for key, value in (("stall_us", 70000), ("trigger", "full 70000 1000000"), ("bytes_written", 1), ("pressure_inode", 45)):
            with self.subTest(key=key):
                self.reject(lambda data, key=key, value=value: data["broker-pressure-audit.json"]["registrations"][1].update({key: value}))

    def test_nonce_scope_terminal_and_owner_identity_rejected(self):
        for name, key, value in (("broker-retired.json", "nonce", "9" * 64),
                                 ("broker-active.json", "cgroup_inode", 41),
                                 ("broker-retired.json", "faulted", True),
                                 ("driver-result.json", "owner_pid", 999),
                                 ("driver-result.json", "broker_retired_and_reaped", False),
                                 ("driver-result.json", "domain_populated", True)):
            with self.subTest(name=name, key=key):
                self.reject(lambda data, name=name, key=key, value=value: data[name].update({key: value}))

    def test_replay_future_and_quiet_events_rejected(self):
        self.reject(lambda data: data["broker-pressure-audit.json"]["events"][0].update(sequence=2))
        self.reject(lambda data: data["broker-pressure-audit.json"]["events"][0].update(observed_ns=3 * NS, send_completed_ns=3 * NS + 1))
        self.reject(lambda data: data["broker-pressure-audit.json"]["events"][0].update(send_completed_ns=10 * NS))

    def test_critical_sent_after_exit_cannot_be_correlated(self):
        manifest, data = fixture()
        data["broker-pressure-audit.json"]["events"][1]["send_completed_ns"] = 5 * NS
        self.assertEqual(q.qualified(manifest, data, "pressure")["qualification_status"], "partial_medium_only")

    def test_fresh_stale_or_expiry_boundary_is_inconclusive(self):
        for observed in (6_200_000_000, 7_300_000_000):
            self.reject(lambda data, observed=observed: data["broker-pressure-audit.json"]["events"][1].update(
                observed_ns=observed, send_completed_ns=observed + 1), "stale")
        self.reject(lambda data: data["pressure-workload.json"].update(kill_count=1), "stale")
        self.reject(lambda data: data["pressure-relief.json"].update(monotonic_ns=5 * NS), "stale")

    def test_kernel_oom_budget_and_second_kill_rejected(self):
        self.reject(lambda data: data["pressure-workload.json"].update(events_after=data["pressure-workload.json"]["events_after"].replace("oom_kill 0", "oom_kill 1")))
        self.reject(lambda data: data["pressure-after.json"].update(high="max\n"))
        self.reject(lambda data: data["pressure-workload.json"].update(peak_observed_current=q.CAP + 1))
        self.reject(lambda data: data["pressure-workload.json"].update(kill_count=2))
        self.reject(lambda data: data["pressure-workload.json"].update(final_current=q.HIGH))

    def test_wrong_victim_or_priority_and_route_rejected(self):
        self.reject(lambda data: data["cached-exit.json"].update(pid=4))
        self.reject(lambda data: data["cached-kill-notification.json"].update(uid=10002))
        self.reject(lambda data: data["identities.json"]["children"][1].update(oom_score_adj=900))
        self.reject(lambda data: data["phase-result.json"].update(production_cgroup_kill_qualified=True))

    def test_late_nonvictim_exit_cannot_be_skipped_at_cleanup(self):
        self.reject(lambda data: data["target-cleanup.json"]["children"][1].update(exit_code=-1, exit_signal=9))
        self.reject(lambda data: data["target-cleanup.json"]["children"].pop())
        self.reject(lambda data: data["target-cleanup.json"].update(lmkd_reaped_before_nonvictim_check=False))
        self.reject(lambda data: data["target-cleanup.json"]["children"][0].update(known_cached_victim=True, exit_code=-1, exit_signal=9), "stale")

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaises(q.Rejected):
            q.decode(b'{"ok":true,"ok":false}')


class ExternalPinControls(unittest.TestCase):
    def prepare(self, directory):
        manifest, data = fixture()
        rows = []
        for name, value in sorted(data.items()):
            raw = json.dumps(value, sort_keys=True).encode() + b"\n"
            (directory / name).write_bytes(raw)
            rows.append({"name": name, "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
        manifest["files"] = rows
        raw = json.dumps(manifest, sort_keys=True).encode() + b"\n"
        (directory / "qualification-inputs.json").write_bytes(raw)
        return hashlib.sha256(raw).hexdigest(), manifest

    def test_external_manifest_and_complete_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            expected, _ = self.prepare(directory)
            manifest, data = q.load_evidence(directory, expected, SOURCE_PIN, "pressure")
            self.assertEqual(q.qualified(manifest, data, "pressure")["qualification_status"], "pass")
            with self.assertRaises(q.Rejected):
                q.load_evidence(directory, "f" * 64, SOURCE_PIN, "pressure")
            with self.assertRaises(q.Rejected):
                q.load_evidence(directory, expected, "c" * 64, "pressure")
            (directory / "cached-exit.json").write_text("{}\n")
            with self.assertRaises(q.Rejected):
                q.load_evidence(directory, expected, SOURCE_PIN, "pressure")

    def test_empty_or_duplicate_set_rejected_even_when_manifest_pinned(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            _, original = self.prepare(directory)
            for kind in ("empty", "duplicate", "traversal"):
                manifest = copy.deepcopy(original)
                if kind == "empty":
                    manifest["files"] = []
                elif kind == "duplicate":
                    manifest["files"][-1] = manifest["files"][0]
                else:
                    manifest["files"][0]["name"] = "../other.json"
                raw = json.dumps(manifest).encode()
                (directory / "qualification-inputs.json").write_bytes(raw)
                with self.subTest(kind=kind), self.assertRaises(q.Rejected):
                    q.load_evidence(directory, hashlib.sha256(raw).hexdigest(), SOURCE_PIN, "pressure")

    def test_symlink_cannot_replace_evidence(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            expected, _ = self.prepare(directory)
            victim = directory / "cached-exit.json"
            victim.rename(directory / "unlisted.json")
            victim.symlink_to("unlisted.json")
            with self.assertRaises(OSError):
                q.load_evidence(directory, expected, SOURCE_PIN, "pressure")


if __name__ == "__main__":
    unittest.main(verbosity=2)
