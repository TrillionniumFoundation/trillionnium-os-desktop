"""Inert schema adversaries; no record here is native execution evidence.

These deliberately constructed records test acceptance/rejection of the frozen
producer DTO. They cannot supply source/build/ELF/guest artifacts to the runner.
"""
import copy
import hashlib
import struct
import unittest

import native_owner_copyout as copyout
import native_owner_evidence as evidence
from native_owner_fault_wire import expected_install_wire
from test_native_owner_evidence import InertRecords, sha


class InertCopyoutRecords(InertRecords):
    def __init__(self, scenario, monitor_first=False):
        super().__init__("steady-state-v1")
        self.scenario = scenario
        self.records = self.records[:4]
        for record in self.records:
            record["scenario"] = scenario
        ready = self.records[3]["payload"]
        self.current = {"manager": copy.deepcopy(ready["current"])}
        self.material = {"manager": ready["material_sha256"]}
        self.frontiers = {lane: copy.deepcopy(ready[lane]) for lane in evidence.FRONTIER_LANES}
        self.time, self.total, self.heartbeat, self.revision, self.cap = 1_000_000_000, 1_000_000, 1, 1, evidence.CAP_NS
        self.operations = {}
        live = scenario == "lost-copyout-live-v1"
        name = "lost-copyout-live" if live else "lost-before-terminal"
        self.operation(name, "manager", 1, 25_000_000)
        observed = self.records.pop()["payload"]
        op = self.operations[name]
        key = "native-cpu:" + sha(evidence.canonical(op["request"]["delivery"])) + ":" + name
        op["key"] = key
        self.records[-1]["payload"]["occurrence_key"] = key
        diagnostic = {"install_ioctl_count": 1, "selected_ioctl_count": 1, "efault_count": 1,
                      "request_sha256": list(hashlib.sha256(expected_install_wire(op["request_json"])).digest()),
                      "request_bytes": 96, "response_capacity": 128, "syscall_return": -1, "errno": 14}
        faulted = {"install_ioctl_count": 1, "selected_ioctl_count": 1, "efault_count": 1,
                   "armed": False, "last": diagnostic}
        fresh = {"install_ioctl_count": 0, "selected_ioctl_count": 0, "efault_count": 0,
                 "armed": False, "last": None}
        if live:
            scope = b"hepta.hos2.cpu-budget.scope.v1\0" + bytes([1] * 16 + [2] * 16) + struct.pack("<QQ", 2, 1)
            receipt = {"request": {"schema_version": 1, "namespace": "production_durable_writer",
                "lease_id": "original-writer", "occurrence_key": key, "topic": copyout.TOPIC,
                "payload_json": op["request_json"], "payload_sha256": sha(op["request_json"]), "idempotency_key": key,
                "operation_scope_sha256": hashlib.sha256(scope).hexdigest(), "operation_subject_id": self.agent,
                "operation_destination_id": copyout.DESTINATION, "operation_semantic_sha256": sha("inert-semantic"),
                "operation_policy_generation": 7, "expected_predecessor_sha256": None,
                "operation_digest": sha("inert-operation-digest")},
                "state": "indeterminate", "target_disposition": "indeterminate", "target_receipt": None,
                "target_reason": "inert actual-EFAULT-shaped diagnostic", "local_event_id": "inert-unknown-event",
                "external_effect": False}
            self.add("copyout_indeterminate", {"operation": name, "pid": 2, "occurrence_key": key,
                "receipt": receipt, "before": observed["before"], "after": observed["after"], "copyout": faulted})
        else:
            current = self.checkpoint("manager", 1, 1, sha("inert-pre-effect-unknown"))
            self.current["manager"] = current
            self.material["manager"] = sha("inert-unknown-material")
            observed_at = self.time + 1
            self.add("copyout_boundary", {"operation": name, "pid": 2, "occurrence_key": key,
                "request_json": op["request_json"], "payload_sha256": sha(op["request_json"]),
                "before": observed["before"], "diagnostic": diagnostic, "observed_boottime_ns": observed_at,
                "pending_until_boottime_ns": observed_at + 2_000_000_000, "current": current,
                "material_sha256": self.material["manager"], **self.frontiers})
            self.add("manager_retired", {"pid": 2, "start_ticks": 22, "root_pid": 1, "root_start_ticks": 21,
                "signal": 9, "wait_kind": "signaled", "wait_value": 9, "pidfd_revents": 1,
                "old_current_token": current["token"], "old_material_sha256": self.material["manager"],
                "kill_boottime_ns": observed_at + 1})
            stable = int.from_bytes(bytes([4] * 16), "little")
            self.time, self.revision, self.cap = 7_000_000_000, 3, evidence.CAP_NS
            stats = {"usage_usec": self.total // 1000, "hepta_watchdog_armed": 1, "hepta_watchdog_ticks": 100,
                "hepta_watchdog_due_ns": 6_000_000_000, "hepta_watchdog_expires_ns": 31_000_000_000,
                "hepta_watchdog_status": 1, "hepta_watchdog_evaluated_ns": 6_000_000_000,
                "hepta_job_stop_available": 1, "hepta_job_stopped": 0, "hepta_user_pause_intent_available": 0,
                "hepta_watchdog_stable_id_low": stable & ((1 << 64) - 1), "hepta_watchdog_stable_id_high": stable >> 64,
                "hepta_watchdog_previous_revision": 2, "hepta_watchdog_revision": 3,
                "hepta_watchdog_effective_ns": 6_000_000_000, "hepta_watchdog_consumed_ns": 0}
            first = "".join(f"{key} {value}\n" for key, value in stats.items())
            stats["hepta_watchdog_ticks"] += 1
            second = "".join(f"{key} {value}\n" for key, value in stats.items())
            self.add("watchdog", {"first_cpu_stat": first, "second_cpu_stat": second, "usage": self.usage("recovery")})
            self.add("local_lease_retired", {"lease_id": "original-writer", "generation": 1, "mode": "expired",
                "observed_unix_seconds": 1001, "expires_at_unix_seconds": 1001})
            adopted = self.checkpoint("recovery", 2, 2, current["head"]["last_current"]["state_digest"])
            self.add("material_adopted", {"previous": current, "successor": adopted,
                "material_sha256": self.material["manager"]})
            self.current["recovery"] = self.checkpoint("recovery", 2, 3,
                sha("inert-monitor-terminal" if monitor_first else "inert-new-owner-lease"))
            self.material["recovery"] = sha("inert-new-owner-material")
            self.owner_ready("recovery")
            self.add("copyout_recovery_startup", {"pid": 4, "occurrence_key": key,
                "capture_point": "original_recovery_before_monitor", "captured": [{"occurrence_key": key,
                    "topic": copyout.TOPIC, "payload_json": op["request_json"], "state": "indeterminate"}],
                "copyout": fresh})
        final = "manager" if live else "recovery"
        self.add("copyout_reconciled", {"operation": name, "pid": self.pids[final], "occurrence_key": key,
            "request_json": op["request_json"], "receipt": {"lease_id": "original-writer", "occurrence_key": key,
                "state": "committed", "event_id": op["local_event_id"], "external_effect": False},
            "terminal_json": op["terminal_json"], "usage": self.usage(final, evidence.PERIOD_NS),
            "before_state": "committed" if monitor_first else "indeterminate", "before_payload_json": op["request_json"],
            "reconciled_count": 0 if monitor_first else 1, "copyout": faulted if live else fresh})
        self.source_terminal(name, final, recovered=monitor_first and not live)
        self.ack(name, final)
        self.window(name, final)
        self.add("complete", {"root_pid": 1, "operation_count": 1, "final_owner_pid": self.pids[final],
            "final_current_token": self.current[final]["token"]})


class NativeOwnerCopyoutTests(unittest.TestCase):
    def reject(self, records):
        with self.assertRaises(ValueError):
            records.evaluate()

    def test_frozen_shapes_and_actual_monitor_order_have_only_finite_scope(self):
        self.assertEqual(evidence.SCENARIOS, ("steady-state-v1", "manager-exit-after-terminal-v1"))
        for scenario in evidence.COPYOUT_SCENARIOS:
            for monitor_first in (False, True):
                with self.subTest(scenario=scenario, monitor_first=monitor_first):
                    result = InertCopyoutRecords(scenario, monitor_first).evaluate()
                    self.assertEqual(result["operation_count"], 1)
                    self.assertEqual(result["after_effect_crash_verified"], scenario == "manager-exit-before-terminal-v1")
                    self.assertTrue(result["copyout_observer_without_install_replay_verified"])
                    for key in ("grant_renewal_verified", "repeated_recovery_verified", "cross_boot_unknown_preservation_verified",
                                "power_loss_verified", "unbounded_persistent_cpu_verified", "production_ready", "g2_complete"):
                        self.assertFalse(result[key])

    def test_fault_requires_exact_actual_errno_return_frame_capacity_and_count(self):
        for key, wrong in (("errno", 5), ("syscall_return", 0), ("request_bytes", 95), ("response_capacity", 88),
                           ("install_ioctl_count", 2), ("selected_ioctl_count", 0), ("efault_count", True),
                           ("request_sha256", [0] * 32)):
            for scenario, event in (("lost-copyout-live-v1", "copyout_indeterminate"),
                                    ("manager-exit-before-terminal-v1", "copyout_boundary")):
                records = InertCopyoutRecords(scenario)
                value = records.event(event)
                value = value["copyout"]["last"] if event == "copyout_indeterminate" else value["diagnostic"]
                value[key] = wrong
                with self.subTest(scenario=scenario, key=key): self.reject(records)

    def test_original_indeterminate_receipt_is_not_a_success_or_new_domain(self):
        for where, key, wrong in (("receipt", "state", "committed"), ("receipt", "target_disposition", "committed"),
                ("receipt", "target_receipt", "fabricated terminal"), ("receipt", "target_reason", None),
                ("receipt", "external_effect", True), ("request", "idempotency_key", "other-k"),
                ("request", "namespace", "other-writer"), ("request", "topic", "notes"),
                ("request", "operation_scope_sha256", "0" * 64), ("request", "operation_subject_id", "other-agent"),
                ("request", "operation_destination_id", "other-destination"), ("request", "operation_policy_generation", 8),
                ("request", "expected_predecessor_sha256", "0" * 64)):
            records = InertCopyoutRecords("lost-copyout-live-v1")
            value = records.event("copyout_indeterminate")["receipt"]
            if where == "request": value = value["request"]
            value[key] = wrong
            with self.subTest(where=where, key=key): self.reject(records)

    def test_one_original_key_payload_and_namespace_cannot_be_rebound(self):
        for event, key, wrong in (("prepared", "occurrence_key", "other-k"),
                ("copyout_reconciled", "request_json", "{}"), ("copyout_reconciled", "before_payload_json", "{}"),
                ("copyout_reconciled", "pid", 2), ("complete", "operation_count", 2)):
            records = InertCopyoutRecords("manager-exit-before-terminal-v1")
            records.event(event)[key] = wrong
            with self.subTest(event=event, key=key): self.reject(records)

    def test_crash_requires_held_callback_window_and_same_actual_pidfd_exit(self):
        for kind in ("before", "at-deadline", "extended", "empty", "bool", "other-pid", "reaped-only", "wrong-signal"):
            records = InertCopyoutRecords("manager-exit-before-terminal-v1")
            boundary, exited = records.event("copyout_boundary"), records.event("manager_retired")
            if kind == "before": exited["kill_boottime_ns"] = boundary["observed_boottime_ns"] - 1
            if kind == "at-deadline": exited["kill_boottime_ns"] = boundary["pending_until_boottime_ns"]
            if kind == "extended": boundary["pending_until_boottime_ns"] += 1
            if kind == "empty": boundary["pending_until_boottime_ns"] = boundary["observed_boottime_ns"]
            if kind == "bool": exited["kill_boottime_ns"] = True
            if kind == "other-pid": exited["pid"] = 4
            if kind == "reaped-only": exited["pidfd_revents"] = 0
            if kind == "wrong-signal": exited["wait_value"] = 15
            with self.subTest(kind=kind): self.reject(records)

    def test_unknown_is_from_factory_before_monitor_and_never_an_install_replay(self):
        for kind in ("late", "committed", "other-k", "other-payload", "duplicate", "install", "arm", "diagnostic"):
            records = InertCopyoutRecords("manager-exit-before-terminal-v1")
            value = records.event("copyout_recovery_startup")
            if kind == "late": value["capture_point"] = "after_monitor"
            if kind == "committed": value["captured"][0]["state"] = "committed"
            if kind == "other-k": value["captured"][0]["occurrence_key"] = "other-k"
            if kind == "other-payload": value["captured"][0]["payload_json"] = "{}"
            if kind == "duplicate": value["captured"].append(copy.deepcopy(value["captured"][0]))
            if kind == "install": value["copyout"]["install_ioctl_count"] = 1
            if kind == "arm": value["copyout"]["armed"] = True
            if kind == "diagnostic": value["copyout"]["last"] = records.event("copyout_boundary")["diagnostic"]
            with self.subTest(kind=kind): self.reject(records)

    def test_observer_state_count_event_and_descriptor_cannot_be_substituted(self):
        for scenario in evidence.COPYOUT_SCENARIOS:
            for kind in ("state-count", "count-bool", "outcome-k", "external-effect", "new-event", "new-install", "new-arm"):
                records = InertCopyoutRecords(scenario)
                value = records.event("copyout_reconciled")
                if kind == "state-count": value["before_state"] = "committed"
                if kind == "count-bool": value["reconciled_count"] = True
                if kind == "outcome-k": value["receipt"]["occurrence_key"] = "other-k"
                if kind == "external-effect": value["receipt"]["external_effect"] = True
                if kind == "new-event": records.event("source_terminal")["local_event_id"] = "new-terminal-event"
                if kind == "new-install": value["copyout"]["install_ioctl_count"] += 1
                if kind == "new-arm": value["copyout"]["armed"] = True
                with self.subTest(scenario=scenario, kind=kind): self.reject(records)

    def test_old_applied_result_is_distinct_from_watchdog_current_usage(self):
        for kind in ("late-effect", "watchdog-revision", "foreign-stable", "rewound-usage", "reset-frontier"):
            records = InertCopyoutRecords("manager-exit-before-terminal-v1")
            value = records.event("copyout_reconciled")
            terminal = evidence.json_value(value["terminal_json"])
            if kind == "late-effect": terminal["observation"]["effective_ns"] = 6_000_000_000
            if kind == "watchdog-revision": terminal["observation"]["revision"] = 3
            if kind == "foreign-stable": terminal["observation"]["stable_object_id"] = [9] * 16
            if kind == "rewound-usage": value["usage"]["revision"] = 2
            if kind == "reset-frontier": records.event("source_terminal")["device_frontier"]["state_sha256"] = [8] * 32
            value["terminal_json"] = evidence.canonical(terminal)
            with self.subTest(kind=kind): self.reject(records)

    def test_future_case_unknown_field_or_missing_boundary_is_not_accepted(self):
        for kind in ("unknown-field", "missing-boundary", "future-case"):
            records = InertCopyoutRecords("manager-exit-before-terminal-v1")
            if kind == "unknown-field": records.event("copyout_boundary")["passed"] = True
            if kind == "missing-boundary": del records.records[5]
            if kind == "future-case":
                records.scenario = "cross-boot-without-source-terminal-v1"
                for value in records.records: value["scenario"] = records.scenario
            with self.subTest(kind=kind): self.reject(records)


if __name__ == "__main__":
    unittest.main()
