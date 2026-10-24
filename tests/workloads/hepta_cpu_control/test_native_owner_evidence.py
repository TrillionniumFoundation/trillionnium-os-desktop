"""Adversarial parser tests with inert records; these are never guest evidence."""
import copy
import hashlib
import json
import unittest

import native_owner_evidence as evidence


NONCE = "9a" * 32
ELF = {"bytes": 4096, "entry": 0x400000}


def sha(label):
    return hashlib.sha256(label.encode()).hexdigest()


class InertRecords:
    def __init__(self, scenario):
        self.scenario = scenario
        self.records = []
        self.boot = [1] * 16
        self.spaces = {"manager": [2] * 16, "recovery": [3] * 16}
        self.pids = {"root": 1, "manager": 2, "workload": 3, "recovery": 4}
        self.agent = "00000000-0000-4000-8000-000000000123"
        self.linux_boot = "11111111-2222-4333-8444-555555555555"
        self.current = {}
        self.material = {}
        self.frontiers = {lane: {"authority_epoch": 7, "revocation_revision": 1,
                                 "state_sha256": list(bytes.fromhex(sha("initial-" + lane)))}
                          for lane in evidence.FRONTIER_LANES}
        self.time = 1_000_000_000
        self.total = 1_000_000
        self.heartbeat = 1
        self.revision = 1
        self.cap = evidence.CAP_NS
        self.operations = {}
        processes = {}
        for role, role_id in evidence.ROLE_IDS.items():
            uid = 0 if role == "root" else (60002 if role == "workload" else 60001)
            processes[role] = {"role": role_id, "pid": self.pids[role], "ppid": 0 if role == "root" else 1,
                               "start_ticks": 20 + self.pids[role], "uids": [uid] * 4, "gids": [uid] * 4,
                               "groups": [0] if role == "root" else [],
                               "caps": {key: (1 << 41) - 1 if role == "root" else 0 for key in evidence.CAPABILITIES},
                               "nnp": 0 if role == "root" else 1, "sid": self.pids[role] if role == "workload" else 1}
        self.add("roles", {"bootstrap_version": 3, "bootstrap_bytes": 200, "native_boot_id": self.boot,
                           "manager_space": self.spaces["manager"], "recovery_space": self.spaces["recovery"],
                           "linux_boot_id": self.linux_boot, "processes": processes})
        self.add("state", {"source": "/dev/vda", "target": "/state", "filesystem": "ext2", "mount_device": 254,
                           "store_device": 254, "store_inode": 11, "root_material_device": 254, "root_material_inode": 12})
        self.add("boundary", {"workload_signal_checks": [
            {"pid": self.pids[role], "signal": sig, "rc": -1, "errno": 1}
            for role in ("root", "manager", "recovery") for sig in (0, 9)],
            "workload_host_path_checks": [{"kind": kind, "rc": -1, "errno": 13} for kind in ("host-store", "root-material")],
            "workload_device_open_errno": 13, "root_manage_status": 2, "root_history_status": 2})
        self.current["manager"] = self.checkpoint("manager", 1, 0, sha("initial-state"))
        self.material["manager"] = sha("initial-material")
        self.owner_ready("manager")
        if scenario == "steady-state-v1":
            for index, (name, cap) in enumerate((("lower", 25_000_000), ("pause", 0), ("resume", evidence.CAP_NS)), 1):
                self.operation(name, "manager", index, cap)
                self.source_terminal(name, "manager")
                self.ack(name, "manager")
                self.window(name, "manager")
        else:
            self.operation("pending-retirement", "manager", 1, 25_000_000)
            self.source_terminal("pending-retirement", "manager")
            self.recovery()
        final = "manager" if scenario == "steady-state-v1" else "recovery"
        self.add("complete", {"root_pid": 1, "operation_count": len(self.operations), "final_owner_pid": self.pids[final],
                              "final_current_token": self.current[final]["token"]})

    def add(self, event, payload):
        self.records.append(copy.deepcopy({"schema_version": 1, "scenario": self.scenario, "nonce": NONCE,
                                            "event": event, "sequence": len(self.records) + 1, "payload": payload}))

    def checkpoint(self, role, generation, counter, state_digest):
        epoch = 1 if role == "manager" else 2
        return {"token": {"publisher_epoch": epoch, "counter": counter, "head_sha256": sha(f"token-{role}-{counter}")},
                "head": {"schema_version": 1, "owner_agent_id": self.agent, "publisher_epoch": epoch,
                         "counter": counter, "last_mutation_sequence": 0, "writer_binding": {
                             "lease_id": "original-writer", "generation": generation, "authority_epoch": 7,
                             "owner_epoch": 10 + generation, "authority_grant_digest": sha(f"grant-{generation}"),
                             "fencing_token_digest": sha(f"fence-{generation}"), "expires_at_unix_seconds": 1000 + generation},
                         "peer_lifetime": {"uid": 60001, "pid": self.pids[role], "boot_id": self.linux_boot,
                                           "process_start_ticks": 20 + self.pids[role]}, "phase": "current",
                         "last_current": {"profile": "hepta:cognitive:exact-current-cut:v1", "owner_agent_id": self.agent,
                                          "schema_digest": sha("original-schema"), "state_digest": state_digest},
                         "proposal": None, "last_request": None}}

    def owner_ready(self, role):
        self.add("owner_ready", {"role": role, "pid": self.pids[role], "agent_id": self.agent,
                                 "spawn_generation": 1 if role == "manager" else 5,
                                 "issuer_key_sha256": sha("same-canonical-issuer"), "writer_proof_sha256": sha("proof-" + role),
                                 "current": self.current[role], "material_sha256": self.material[role],
                                 **self.frontiers, "owner_lock_device": 254, "owner_lock_inode": 15})

    def usage(self, role, advance=0):
        self.time += advance
        if advance and self.cap:
            self.total += 1000
            self.heartbeat += 1
        return {"boot_id": self.boot, "observer_space_id": self.spaces[role], "revision": self.revision,
                "sample_boottime_ns": self.time, "cumulative_cpu_ns": self.total,
                "window_start_ns": self.time // evidence.PERIOD_NS * evidence.PERIOD_NS,
                "window_consumed_ns": 0, "active_cap_ns": self.cap, "active_period_ns": evidence.PERIOD_NS,
                "event_sequence": self.revision, "dropped_events": 0, "heartbeat": self.heartbeat}

    def operation(self, name, role, sequence, cap, reject=False):
        before = self.usage(role, evidence.PERIOD_NS)
        req = {"schema_version": 1, "delivery": {"boot_id": self.boot, "space_id": self.spaces[role],
                                                "sequence": f"{sequence:016x}"},
               "manage_slot": 2, "manage_generation": 1, "expected_revision": self.revision,
               "period_ns": evidence.PERIOD_NS, "cap_ns": cap}
        raw_request = evidence.canonical(req)
        self.operations[name] = {"request": req, "request_json": raw_request, "key": "original-k-" + name,
                                 "local_event_id": "event-" + name}
        self.add("prepared", {"operation": name, "pid": self.pids[role], "occurrence_key": "original-k-" + name,
                              "request_json": raw_request, "payload_sha256": sha(raw_request)})
        self.frontiers["device_frontier"]["state_sha256"] = list(bytes.fromhex(sha("claim-" + name)))
        if reject:
            observed = {"state": "not_applied", "status": 2}
        else:
            observed = {"state": "applied", "stable_object_id": [4] * 16, "previous_revision": self.revision,
                        "revision": self.revision + 1, "effective_ns": self.time + 1, "consumed_ns": 0}
            self.revision += 1
            self.cap = cap
        after = self.usage(role, evidence.PERIOD_NS)
        raw_terminal = evidence.canonical({"schema_version": 1, "request": req, "observation": observed})
        self.operations[name].update(terminal_json=raw_terminal, observation=observed)
        self.add("native_result", {"operation": name, "pid": self.pids[role], "terminal_json": raw_terminal,
                                  "before": before, "after": after})

    def source_terminal(self, name, role, recovered=False):
        op = self.operations[name]
        if not recovered:
            old = self.current[role]
            self.current[role] = self.checkpoint(role, old["head"]["writer_binding"]["generation"],
                                                  old["head"]["counter"] + 1, sha("state-" + name))
            self.material[role] = sha("material-" + name)
        self.add("source_terminal", {"operation": name, "pid": self.pids[role], "occurrence_key": op["key"],
                                     "state": "committed" if op["observation"]["state"] == "applied" else "rejected",
                                     "terminal_json": op["terminal_json"], "local_event_id": op["local_event_id"],
                                     "current": self.current[role], "material_sha256": self.material[role], **self.frontiers})

    def ack(self, name, role):
        op = self.operations[name]
        through = int(op["request"]["delivery"]["sequence"], 16)
        self.add("history_ack", {"operation": name, "pid": self.pids[role], "delivery": op["request"]["delivery"],
                                 "source_owner": self.agent, "source_generation": self.current[role]["head"]["writer_binding"]["generation"],
                                 "retired_through": through, "next_sequence": through + 1, "current_token": self.current[role]["token"]})

    def window(self, name, role):
        first = self.usage(role, evidence.PERIOD_NS)
        second = self.usage(role, 2 * evidence.PERIOD_NS)
        self.add("usage_window", {"operation": name, "pid": self.pids[role], "first": first, "second": second})

    def recovery(self):
        current = self.current["manager"]
        self.add("manager_retired", {"pid": 2, "start_ticks": 22, "root_pid": 1, "root_start_ticks": 21,
                                     "signal": 9, "wait_kind": "signaled", "wait_value": 9, "pidfd_revents": 1,
                                     "old_current_token": current["token"], "old_material_sha256": self.material["manager"]})
        stable = int.from_bytes(bytes([4] * 16), "little")
        self.time = 7_000_000_000
        self.revision += 1
        self.cap = evidence.CAP_NS
        stats = {"usage_usec": self.total // 1000, "hepta_watchdog_armed": 1, "hepta_watchdog_ticks": 100,
                 "hepta_watchdog_due_ns": 6_000_000_000, "hepta_watchdog_expires_ns": 31_000_000_000,
                 "hepta_watchdog_status": 1, "hepta_watchdog_evaluated_ns": 6_000_000_000,
                 "hepta_job_stop_available": 1, "hepta_job_stopped": 0, "hepta_user_pause_intent_available": 0,
                 "hepta_watchdog_stable_id_low": stable & ((1 << 64) - 1), "hepta_watchdog_stable_id_high": stable >> 64,
                 "hepta_watchdog_previous_revision": self.revision - 1, "hepta_watchdog_revision": self.revision,
                 "hepta_watchdog_effective_ns": 6_000_000_000, "hepta_watchdog_consumed_ns": 0}
        first = "".join(f"{key} {value}\n" for key, value in stats.items())
        stats["hepta_watchdog_ticks"] += 1
        second = "".join(f"{key} {value}\n" for key, value in stats.items())
        self.add("watchdog", {"first_cpu_stat": first, "second_cpu_stat": second, "usage": self.usage("recovery")})
        self.add("local_lease_retired", {"lease_id": "original-writer", "generation": 1, "mode": "expired",
                                         "observed_unix_seconds": 1001, "expires_at_unix_seconds": 1001})
        adopted = self.checkpoint("recovery", 2, current["head"]["counter"] + 1,
                                  current["head"]["last_current"]["state_digest"])
        self.add("material_adopted", {"previous": current, "successor": adopted, "material_sha256": self.material["manager"]})
        self.current["recovery"] = self.checkpoint("recovery", 2, adopted["head"]["counter"] + 1, sha("new-owner-lease-state"))
        self.material["recovery"] = sha("new-owner-lease-material")
        self.owner_ready("recovery")
        old = self.operations["pending-retirement"]
        self.add("reconciled", {"operation": "pending-retirement", "pid": 4, "occurrence_key": old["key"],
                                "request_json": old["request_json"], "terminal_json": old["terminal_json"],
                                "usage": self.usage("recovery", evidence.PERIOD_NS)})
        self.source_terminal("pending-retirement", "recovery", recovered=True)
        self.ack("pending-retirement", "recovery")
        self.operation("used-recovery-allowance", "recovery", 1, evidence.CAP_NS, reject=True)
        self.source_terminal("used-recovery-allowance", "recovery")
        self.ack("used-recovery-allowance", "recovery")
        self.window("used-recovery-allowance", "recovery")

    def event(self, name, occurrence=0):
        return [record for record in self.records if record["event"] == name][occurrence]["payload"]

    def raw(self):
        kernel = [f"[hepta-g2] trusted initial image committed: bytes={ELF['bytes']} entry={ELF['entry']:#x}"] * 4
        kernel.append("[hepta-g2] initial roles activated: root=1 manager=2 workload=3 recovery=4 workload_uid=60002 bootstrap_version=3 bytes=200 hepta_durability=false")
        return ("\n".join(kernel + [evidence.PREFIX + json.dumps(record, separators=(",", ":")) for record in self.records]) + "\n").encode()

    def evaluate(self):
        return evidence.evaluate(self.raw(), 33, False, False, self.scenario, NONCE, ELF)


class NativeOwnerEvidenceTests(unittest.TestCase):
    def assert_rejected(self, records):
        with self.assertRaises(ValueError):
            records.evaluate()

    def test_two_finite_shapes_never_claim_unimplemented_g2(self):
        for scenario in evidence.SCENARIOS:
            with self.subTest(scenario=scenario):
                result = InertRecords(scenario).evaluate()
                self.assertTrue(result["passed"])
                self.assertFalse(result["g2_complete"])
                self.assertFalse(result["grant_renewal_verified"])
                self.assertFalse(result["power_loss_verified"])
                self.assertFalse(result["after_effect_crash_verified"])

    def test_previous_read_usage_probe_cannot_pass(self):
        raw = b'G1D_COMPLETE native_manage=true history=true hepta_durability=false hardware=false\n'
        with self.assertRaises(ValueError):
            evidence.evaluate(raw, 33, False, False, evidence.SCENARIOS[0], NONCE, ELF)

    def test_missing_fourth_image_old_v2_and_malformed_image_fail(self):
        records = InertRecords(evidence.SCENARIOS[0])
        raw = records.raw()
        for changed in (raw.split(b"\n", 1)[1], raw.replace(b"[hepta-g2]", b"[hepta-g1d]"),
                        raw.replace(b"bytes=4096", b"bytes=4095", 1)):
            with self.subTest(changed=changed[:100]), self.assertRaises(ValueError):
                evidence.evaluate(changed, 33, False, False, evidence.SCENARIOS[0], NONCE, ELF)

    def test_foreign_nonce_event_replay_missing_and_unknown_events_fail(self):
        for mutation in ("nonce", "sequence", "drop", "unknown", "duplicate"):
            records = InertRecords(evidence.SCENARIOS[0])
            if mutation == "nonce": records.records[5]["nonce"] = "00" * 32
            if mutation == "sequence": records.records[5]["sequence"] = 1
            if mutation == "drop": del records.records[5]
            if mutation == "unknown": records.records[5]["event"] = "read_usage_passed"
            if mutation == "duplicate": records.records.insert(6, copy.deepcopy(records.records[5]))
            with self.subTest(mutation=mutation): self.assert_rejected(records)

    def test_duplicate_json_keys_and_nonfinite_or_boolean_numbers_fail(self):
        records = InertRecords(evidence.SCENARIOS[0])
        raw = records.raw()
        for changed in (raw.replace(b'"schema_version":1', b'"schema_version":1,"schema_version":1', 1),
                        raw.replace(b'"bootstrap_version":3', b'"bootstrap_version":true', 1),
                        raw.replace(b'"bootstrap_version":3', b'"bootstrap_version":NaN', 1)):
            with self.subTest(changed=changed[:100]), self.assertRaises(ValueError):
                evidence.evaluate(changed, 33, False, False, evidence.SCENARIOS[0], NONCE, ELF)

    def test_process_parent_uid_caps_and_identity_are_actual_not_labels(self):
        for role, field, value in (("manager", "ppid", 0), ("workload", "uids", [60001] * 4),
                                   ("recovery", "nnp", 0), ("manager", "groups", [0]),
                                   ("root", "pid", 2), ("workload", "sid", 1)):
            records = InertRecords(evidence.SCENARIOS[0])
            records.event("roles")["processes"][role][field] = value
            with self.subTest(role=role, field=field): self.assert_rejected(records)
        records = InertRecords(evidence.SCENARIOS[0])
        records.event("roles")["processes"]["manager"]["caps"]["bounding"] = 1
        self.assert_rejected(records)

    def test_actual_workload_signal_private_path_and_root_slot_denials_required(self):
        for field in ("workload_signal_checks", "workload_host_path_checks", "root_manage_status"):
            records = InertRecords(evidence.SCENARIOS[0])
            boundary = records.event("boundary")
            if type(boundary[field]) is list: boundary[field][0]["rc"] = 0
            else: boundary[field] = 0
            with self.subTest(field=field): self.assert_rejected(records)

    def test_another_boot_delivery_rebound_k_and_changed_payload_refused(self):
        for mutation in ("boot", "sequence", "key", "bytes"):
            records = InertRecords(evidence.SCENARIOS[0])
            prepared = records.event("prepared", 1)
            if mutation == "key": prepared["occurrence_key"] = records.event("prepared")["occurrence_key"]
            elif mutation == "bytes": prepared["request_json"] += " "
            else:
                req = json.loads(prepared["request_json"])
                req["delivery"]["boot_id" if mutation == "boot" else "sequence"] = [5] * 16 if mutation == "boot" else "0000000000000001"
                prepared["request_json"] = evidence.canonical(req)
                prepared["payload_sha256"] = sha(prepared["request_json"])
            with self.subTest(mutation=mutation): self.assert_rejected(records)

    def test_history_cannot_retire_before_original_durable_terminal(self):
        records = InertRecords(evidence.SCENARIOS[0])
        source = next(index for index, item in enumerate(records.records) if item["event"] == "source_terminal")
        records.records[source], records.records[source + 1] = records.records[source + 1], records.records[source]
        for index, item in enumerate(records.records, 1): item["sequence"] = index
        self.assert_rejected(records)

    def test_unknown_dirty_or_other_writer_current_cannot_prove_terminal(self):
        for mutation in ("phase", "peer", "writer", "old_cut", "state"):
            records = InertRecords(evidence.SCENARIOS[0])
            value = records.event("source_terminal")
            if mutation == "phase": value["current"]["head"]["phase"] = "dirty"
            if mutation == "peer": value["current"]["head"]["peer_lifetime"]["pid"] = 4
            if mutation == "writer": value["current"]["head"]["writer_binding"]["owner_epoch"] += 1
            if mutation == "old_cut": value["current"] = copy.deepcopy(records.event("owner_ready")["current"])
            if mutation == "state": value["state"] = "indeterminate"
            with self.subTest(mutation=mutation): self.assert_rejected(records)

    def test_zero_budget_must_stop_real_cpu_and_heartbeat_for_two_periods(self):
        for mutation in ("cpu", "heartbeat", "short", "cap"):
            records = InertRecords(evidence.SCENARIOS[0])
            window = records.event("usage_window", 1)
            if mutation == "cpu": window["second"]["cumulative_cpu_ns"] += 1
            if mutation == "heartbeat": window["second"]["heartbeat"] += 1
            if mutation == "short": window["second"]["sample_boottime_ns"] = window["first"]["sample_boottime_ns"]
            if mutation == "cap": window["second"]["active_cap_ns"] = 1
            with self.subTest(mutation=mutation): self.assert_rejected(records)

    def test_native_apply_cannot_reset_counters_or_invent_an_unrelated_revision(self):
        for key, value in (("revision", 44), ("cumulative_cpu_ns", 0), ("dropped_events", 1), ("active_cap_ns", 4)):
            records = InertRecords(evidence.SCENARIOS[0])
            records.event("native_result")["after"][key] = value
            with self.subTest(key=key): self.assert_rejected(records)

    def test_process_death_is_not_old_local_lease_retirement(self):
        records = InertRecords(evidence.SCENARIOS[1])
        records.event("local_lease_retired")["observed_unix_seconds"] = 1000
        self.assert_rejected(records)
        records = InertRecords(evidence.SCENARIOS[1])
        records.event("manager_retired")["pidfd_revents"] = 8
        self.assert_rejected(records)

    def test_original_material_and_canonical_generation_cannot_be_reset(self):
        for mutation in ("material", "cut", "generation", "issuer", "spawn", "frontier"):
            records = InertRecords(evidence.SCENARIOS[1])
            owner = records.event("owner_ready", 1)
            if mutation == "material": records.event("material_adopted")["material_sha256"] = "ab" * 32
            if mutation == "cut": records.event("material_adopted")["successor"]["head"]["last_current"]["state_digest"] = "ab" * 32
            if mutation == "generation": owner["current"]["head"]["writer_binding"]["generation"] = 1
            if mutation == "issuer": owner["issuer_key_sha256"] = "ab" * 32
            if mutation == "spawn": owner["spawn_generation"] = 1
            if mutation == "frontier": owner["device_frontier"] = records.event("owner_ready")["device_frontier"]
            with self.subTest(mutation=mutation): self.assert_rejected(records)

    def test_frontier_requires_the_actual_dto_and_byte_array(self):
        for changed in ({"sequence": 1}, {"authority_epoch": 7, "revocation_revision": 1, "state_sha256": "ab" * 32},
                        {"authority_epoch": 7, "revocation_revision": 0, "state_sha256": [1] * 32},
                        {"authority_epoch": 7, "revocation_revision": 1, "state_sha256": [True] * 32},
                        {"authority_epoch": 7, "revocation_revision": 1, "state_sha256": [0] * 32}):
            records = InertRecords(evidence.SCENARIOS[0])
            records.event("owner_ready")["device_frontier"] = changed
            with self.subTest(changed=changed): self.assert_rejected(records)

    def test_dispatch_claim_and_recovery_preserve_exact_consumer_frontiers(self):
        for mutation in ("unclaimed", "notes-mutated", "epoch-changed", "recovery-new-claim"):
            records = InertRecords(evidence.SCENARIOS[1])
            source = records.event("source_terminal")
            if mutation == "unclaimed": source["device_frontier"] = records.event("owner_ready")["device_frontier"]
            if mutation == "notes-mutated": source["notes_frontier"]["state_sha256"] = [8] * 32
            if mutation == "epoch-changed": source["device_frontier"]["authority_epoch"] += 1
            if mutation == "recovery-new-claim": records.event("source_terminal", 1)["device_frontier"]["state_sha256"] = [9] * 32
            with self.subTest(mutation=mutation): self.assert_rejected(records)

    def test_watchdog_receipt_does_not_replace_old_manager_delivery(self):
        records = InertRecords(evidence.SCENARIOS[1])
        recovered = records.event("reconciled")
        terminal = json.loads(recovered["terminal_json"])
        terminal["observation"]["revision"] = recovered["usage"]["revision"]
        recovered["terminal_json"] = evidence.canonical(terminal)
        self.assert_rejected(records)

    def test_watchdog_delay_status_receipt_mutation_and_second_effect_refused(self):
        for mutation in ("delay", "status", "receipt", "effect"):
            records = InertRecords(evidence.SCENARIOS[1])
            watchdog = records.event("watchdog")
            if mutation == "delay": watchdog["first_cpu_stat"] = watchdog["first_cpu_stat"].replace("hepta_watchdog_due_ns 6000000000", "hepta_watchdog_due_ns 7000000000")
            if mutation == "status": watchdog["first_cpu_stat"] = watchdog["first_cpu_stat"].replace("hepta_watchdog_status 1", "hepta_watchdog_status 2")
            if mutation == "receipt": watchdog["second_cpu_stat"] = watchdog["second_cpu_stat"].replace("hepta_watchdog_revision 3", "hepta_watchdog_revision 4")
            if mutation == "effect": records.event("native_result", 1)["after"]["revision"] += 1
            with self.subTest(mutation=mutation): self.assert_rejected(records)

    def test_timeout_error_output_unknown_tail_and_partial_record_never_pass(self):
        records = InertRecords(evidence.SCENARIOS[0])
        for code, timed_out, excessive in ((0, False, False), (33, True, False), (33, False, True), (True, False, False)):
            with self.subTest(code=code, timed_out=timed_out, excessive=excessive), self.assertRaises(ValueError):
                evidence.evaluate(records.raw(), code, timed_out, excessive, records.scenario, NONCE, ELF)
        for extra in (b"HEPTA_G2_FAIL reason=test\n", b"Kernel panic\n", b"HEPTA_G2_EVIDENCE_V1 {\n"):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                evidence.evaluate(records.raw() + extra, 33, False, False, records.scenario, NONCE, ELF)


if __name__ == "__main__":
    unittest.main()
