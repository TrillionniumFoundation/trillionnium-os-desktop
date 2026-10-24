"""Inert parser-only records. Nothing here is a native receipt or an owner.

These synthetic bytes exercise rejection paths and complete parser branches.
They must never enter source reviews, actual QEMU records, result archives or
native qualification. No signer, service, kernel, writer or effect runs here.
"""
import copy
import hashlib
import json
import struct

import native_owner_evidence as e
import native_owner_continuity_types as t
from native_owner_root_observation import launch_observation_id
from test_native_owner_evidence import ELF, InertRecords, NONCE, sha


def words(magic, size, values):
    raw = bytearray(size)
    raw[:8] = magic
    for offset, value in values.items():
        struct.pack_into("<Q", raw, offset, value)
    return raw


class ContinuityRecords(InertRecords):
    def __init__(self, scenario):
        seed = InertRecords("steady-state-v1")
        self.__dict__.update(copy.deepcopy(seed.__dict__))
        self.scenario = scenario
        self.records = self.records[:4]
        for record in self.records:
            record["scenario"] = scenario
        self.spaces = {"manager": self.space(2), "recovery": self.space(3)}
        self.records[0]["payload"].update(manager_space=self.spaces["manager"], recovery_space=self.spaces["recovery"])
        self.initial_pids = dict(self.pids)
        self.initial_spaces = copy.deepcopy(self.spaces)
        self.current = {"manager": self.event("owner_ready")["current"]}
        self.material = {"manager": self.event("owner_ready")["material_sha256"]}
        self.frontiers = {key: copy.deepcopy(self.event("owner_ready")[key]) for key in e.FRONTIER_LANES}
        self.time, self.total, self.heartbeat, self.revision, self.cap = 1_000_000_000, 1_000_000, 1, 1, e.CAP_NS
        self.operations, self.kernel_before, self.saved, self.authorities = {}, {}, {}, {}
        self.generation, self.local_generation, self.spawn = 0, 1, 1
        self.active_role = "manager"
        self.last_lifecycle = 1
        self.launch_pids = {**self.pids, "history": 0}
        self.authorities["manager"] = self.authority(None)
        self.current["manager"] = self.new_current("manager", 1, 0, sha("initial-state"))
        ready = self.event("owner_ready")
        ready.update(current=self.current["manager"], writer_proof_sha256=t.sha(self.authorities["manager"]["proof"]))
        if scenario == "successor-renewal-v1":
            self.renewal()
        else:
            self.history()
        self.add("complete", {"root_pid": 1, "operation_count": len(self.operations),
                              "final_owner_pid": self.pids["manager"], "final_current_token": self.current["manager"]["token"]})

    def space(self, value):
        return self.boot[:8] + list(value.to_bytes(8, "little"))

    def peer(self, role):
        return {"uid": 60001, "pid": self.pids[role], "boot_id": self.linux_boot,
                "process_start_ticks": 20 + self.pids[role]}

    def authority(self, previous):
        now = 1_000_000 + self.time // 1_000_000
        scope = hashlib.sha256(b"hepta.hos2.cpu-budget.scope.v1\0" + bytes(self.boot)
                               + bytes(self.initial_spaces["manager"]) + struct.pack("<QQ", 2, 1)).digest()
        root_binding = {"principal_id": self.agent, "operation_class": "runtime.agentd.production_operation",
                        "destination_id": "hos2.cpu-budget.v1", "scope_sha256": list(scope),
                        "payload_sha256": list(hashlib.sha256(b"native-root-installation-observation-only").digest())}
        payload = sha("inert-initial-anchor") if previous is None else t.sha(
            [previous["head"]["last_current"], self.spawn, self.local_generation])
        writer_binding = {"principal_id": self.agent, "operation_class": "runtime.agentd.production_writer",
                          "destination_id": "cognitive.owner:" + self.agent,
                          "scope_sha256": list(bytes.fromhex(sha("inert-writer-scope"))), "payload_sha256": list(bytes.fromhex(payload))}
        root = {"schema_version": 1, "lease_id": "native-cpu-root-installation" if self.local_generation == 1
                else "native-cpu.root." + self.linux_boot + "." + str(self.spawn), "authority_epoch": 7, "revision": 1,
                "binding": root_binding, "issued_at_unix_ms": now, "expires_at_unix_ms": now + 120_000}
        lease = {"schema_version": 1, "lease_id": "native-cpu.writer." + self.linux_boot + "." + str(self.spawn), "authority_epoch": 7,
                 "revision": 1, "binding": writer_binding, "issued_at_unix_ms": now, "expires_at_unix_ms": now + 20_000}
        writer = {"registered_agent_id": self.agent, "spawn_generation": self.spawn, "owner_epoch": 10 + self.local_generation,
                  "local_lease_id": "original-writer", "local_lease_generation": self.local_generation, "authority_lease": lease}
        claims = {"schema_version": 1, "issuer_id": "inert-original-issuer", "sequence": self.local_generation, **writer,
                  "authority_lease_sha256": t.sha(lease)}
        proof = {"claims": claims, "signature_hex": "ab" * 64}
        proof_hash = t.sha(proof)
        fence = hashlib.sha256(hashlib.sha256(b"hepta:production-authority-token-grant:v2\0"
                               + proof_hash.encode() + proof["signature_hex"].encode()).digest()).hexdigest()
        binding = {"lease_id": writer["local_lease_id"], "generation": self.local_generation, "authority_epoch": 7,
                   "owner_epoch": writer["owner_epoch"], "authority_grant_digest": proof_hash,
                   "fencing_token_digest": fence, "expires_at_unix_seconds": lease["expires_at_unix_ms"] // 1000}
        return {"root": root, "writer": writer, "proof": proof, "binding": binding}

    def new_current(self, role, epoch, counter, state):
        return {"token": {"publisher_epoch": epoch, "counter": counter,
                          "head_sha256": sha(f"inert-token-{role}-{self.local_generation}-{counter}")},
                "head": {"schema_version": 1, "owner_agent_id": self.agent, "publisher_epoch": epoch, "counter": counter,
                         "last_mutation_sequence": 0, "writer_binding": copy.deepcopy(self.authorities[role]["binding"]),
                         "peer_lifetime": self.peer(role), "phase": "current", "last_current": {
                             "profile": "hepta:cognitive:exact-current-cut:v1", "owner_agent_id": self.agent,
                             "schema_digest": sha("original-schema"), "state_digest": state},
                         "proposal": None, "last_request": None}}

    def advance_current(self, role, label):
        old = self.current[role]
        self.current[role] = self.new_current(role, old["head"]["publisher_epoch"], old["head"]["counter"] + 1,
                                             sha(f"inert-state-{self.local_generation}-{label}"))
        self.material[role] = sha(f"inert-material-{self.local_generation}-{label}")

    def snapshot(self, stopped=False, failed=False):
        def event(generation, kind, details=None):
            return {"generation": generation, "kind": kind, "details": details}
        s = self.spawn
        events = [event(s, "lifecycle", {"state": "starting"}), event(s, "spawned"),
                  event(s + 1, "lifecycle", {"state": "running"}), event(s + 1, "healthy")]
        if failed:
            events += [event(s + 1, "other", {"detail": "AutomaticRestartQueued { attempt: 1 }"}),
                       event(s + 2, "lifecycle", {"state": "failed"}),
                       event(s + 2, "exited", {"success": False, "code": None}),
                       event(s + 3, "lifecycle", {"state": "starting"}),
                       event(s + 4, "lifecycle", {"state": "failed"})]
        elif stopped:
            events += [event(s + 2, "lifecycle", {"state": "draining"}), event(s + 2, "stop_requested"),
                       event(s + 3, "lifecycle", {"state": "stopped"}), event(s + 3, "exited", {"success": True, "code": 0})]
        inactive = stopped or failed
        return {"active": not inactive, "healthy": not inactive, "runtime_generation": None if inactive else s + 1,
                "spawn_generation": None if inactive else s,
                "process_system_id": None if inactive else self.pids[self.active_role], "events": events}

    def bootstrap(self, role):
        role_id = {"manager": 1, "recovery": 3, "history_only": 5}[role]
        new = self.generation > 0
        raw = words(b"HOS2BOOT", 240 if new else 200, {8: 4 if new else 3, 16: role_id, 24: 240 if new else 200,
            144: self.launch_pids["manager"], 152: 3, 160: self.launch_pids["recovery"],
            168: 0 if role_id == 5 else e.CAP_NS, 176: e.PERIOD_NS, 184: 0 if role_id == 5 else e.LEASE_NS, 192: 1})
        handles = (0, 0, 0, 0, 3, 1, 4, 1) if role_id == 5 else ((1, 1, 2, 1, 3, 1, 0, 0) if role_id == 1 else (1, 1, 2, 1, 3, 1, 4, 1))
        for offset, value in zip(range(32, 96, 8), handles):
            struct.pack_into("<Q", raw, offset, value)
        raw[96:112] = bytes(self.boot)
        raw[112:128], raw[128:144] = bytes(self.spaces["manager"]), bytes(self.spaces["recovery"])
        if new:
            struct.pack_into("<Q", raw, 200, self.pids[role])
            raw[208:224] = bytes(self.spaces[role])
            struct.pack_into("<Q", raw, 224, self.generation)
        return list(raw)

    def emit_owner(self):
        role = self.active_role
        if self.generation:
            self.add("kernel_launch_saved", self.saved[self.generation])
        auth = self.authorities[role]
        self.add("continuity_owner", {"role": role, "pid": self.pids[role], "kernel_bootstrap": self.bootstrap(role),
                 "supervisor": self.snapshot(), "root_lease": auth["root"], "writer": auth["writer"], "writer_proof": auth["proof"],
                 "current": self.current[role], "material_sha256": self.material[role], **self.frontiers,
                 "usage": None if role == "history_only" else self.usage(role)})

    def operation(self, name, role, sequence, cap, reject=False):
        InertRecords.operation(self, name, role, sequence, cap, reject)
        op = self.operations[name]
        op["key"] = "native-cpu:" + t.sha(op["request"]["delivery"]) + ":" + name
        self.records[-2]["payload"]["occurrence_key"] = op["key"]
        op["local_event_id"] = "inert-event-" + str(self.local_generation)
        self.frontiers["device_frontier"]["state_sha256"] = list(bytes.fromhex(sha("inert-claim-" + str(self.local_generation))))

    def source_terminal(self, name, role, recovered=False):
        op = self.operations[name]
        if not recovered:
            self.advance_current(role, name)
        self.add("source_terminal", {"operation": name, "pid": self.pids[role], "occurrence_key": op["key"], "state": "committed",
                 "terminal_json": op["terminal_json"], "local_event_id": op["local_event_id"], "current": self.current[role],
                 "material_sha256": self.material[role], **self.frontiers})

    def effect(self, name, retire=True):
        self.operation(name, "manager", 1, 25_000_000)
        self.source_terminal(name, "manager")
        if retire:
            self.ack(name, "manager")
            self.window(name, "manager")
        return self.operations[name]

    def release(self):
        role = self.active_role
        self.advance_current(role, "release")
        binding = self.current[role]["head"]["writer_binding"]
        receipt = {"schema_version": 1, "namespace": "production_durable_writer", "owner_agent_id": self.agent,
                   **{key: binding[key] for key in ("lease_id", "generation", "authority_grant_digest", "authority_epoch", "owner_epoch")},
                   "state": "released", "lease_head_digest": sha("inert-released-lease"), "external_effect": False}
        self.add("owner_released", {"pid": self.pids[role], "peer_lifetime": self.peer(role), "receipt": receipt,
                 "current": self.current[role], "material_sha256": self.material[role], **self.frontiers})
        self.add("owner_stopped", {"pid": self.pids[role], "peer_lifetime": self.peer(role),
                 "release_generation": self.local_generation, "supervisor": self.snapshot(stopped=True)})
        self.last_lifecycle = self.spawn + 3

    def raw_launch(self, mode):
        raw = words(b"HOS2LRES", 128, {8: 1, 16: mode, 24: self.generation, 32: 1, 40: 3,
            48: self.launch_pids["manager"], 56: self.launch_pids["recovery"], 64: self.launch_pids["history"],
            72: max(0, self.generation - 1)})
        raw[80:96], raw[96:112] = bytes(self.spaces["manager"]), bytes(self.spaces["recovery"])
        return list(raw)

    def launch(self, history=False, watchdog=None):
        previous_spaces = [self.spaces["manager"], self.spaces["recovery"]]
        self.generation += 1
        pid = 10 + 2 * self.generation
        if history:
            self.pids["history_only"] = pid
            self.spaces["history_only"] = self.space(100 + self.generation)
            self.launch_pids = {"root": 1, "workload": 3, "manager": 0, "recovery": 0, "history": pid}
            marker = f"[hepta-g2] history successor activated: generation={self.generation} history={pid} workload=3 bootstrap_version=4 bytes=240 hepta_durability=false"
        else:
            self.pids.update(manager=pid, recovery=pid + 1)
            self.spaces.update(manager=self.space(10 + 2 * self.generation), recovery=self.space(11 + 2 * self.generation))
            self.launch_pids = {"root": 1, "workload": 3, "manager": pid, "recovery": pid + 1, "history": 0}
            marker = f"[hepta-g2] successor roles activated: generation={self.generation} manager={pid} workload=3 recovery={pid+1} bootstrap_version=4 bytes=240 hepta_durability=false"
        image = f"[hepta-g2] trusted initial image committed: bytes={ELF['bytes']} entry={ELF['entry']:#x}"
        self.kernel_before[len(self.records)] = [image] * (1 if history else 2) + [marker]
        retired = words(b"HOS2LWDR", 128, {8: 1, 16: self.generation, 120: 0 if history else (3 if watchdog else 1)})
        retired[88:104], retired[104:120] = map(bytes, previous_spaces)
        if watchdog:
            struct.pack_into("<Q", retired, 24, 1)
            struct.pack_into("<Q", retired, 32, watchdog["effective_ns"])
            retired[40:56] = bytes(watchdog["stable_object_id"])
            for offset, key in zip((56, 64, 72, 80), ("previous_revision", "revision", "effective_ns", "consumed_ns")):
                struct.pack_into("<Q", retired, offset, watchdog[key])
        payload = {"schema_version": 1, "operation": "kernel.g2.launch-observation.v1", "boot_id": self.boot,
                   "launch_generation": self.generation, "launch_receipt": self.raw_launch(2 if history else 1),
                   "retirement_receipt": list(retired)}
        raw = e.canonical(payload)
        self.saved[self.generation] = {key: payload[key] for key in ("boot_id", "launch_generation", "launch_receipt", "retirement_receipt")}
        self.saved[self.generation].update(observation_id=launch_observation_id(self.boot, self.generation),
                                         durable_payload_json=raw, durable_payload_sha256=sha(raw))

    def successor(self, role):
        previous = self.current[self.active_role]
        previous_material = self.material[self.active_role]
        self.spawn = self.last_lifecycle + 1
        self.local_generation += 1
        self.authorities[role] = self.authority(previous)
        adopted = self.new_current(role, previous["head"]["publisher_epoch"] + 1, previous["head"]["counter"] + 1,
                                   previous["head"]["last_current"]["state_digest"])
        self.add("material_adopted", {"previous": previous, "successor": adopted, "material_sha256": previous_material})
        self.current[role] = copy.deepcopy(adopted)
        self.advance_current(role, "ready")
        self.active_role = role
        self.emit_owner()

    def renewal(self):
        first = self.usage("manager")
        threshold = first["sample_boottime_ns"] + 330_000_000_000
        auth = self.authorities["manager"]
        self.add("renewal_origin", {"initial_usage": first, "after_boottime_ns": threshold,
                                   "initial_root_lease": auth["root"], "initial_writer": auth["writer"]})
        self.emit_owner()
        for cycle in range(3):
            op = self.effect("continued-control")
            if cycle == 2:
                auth = self.authorities["manager"]
                self.add("renewal_endpoint", {"initial_sample_boottime_ns": first["sample_boottime_ns"], "after_boottime_ns": threshold,
                    "actual_terminal_json": op["terminal_json"], "occurrence_key": op["key"], "delivery": op["request"]["delivery"],
                    "fresh_kernel_generations": [1, 2], "root_lease": auth["root"], "writer": auth["writer"]})
                break
            self.operations[op["key"]] = self.operations.pop("continued-control")
            self.release()
            self.successor("recovery")
            self.release()
            self.time = 10_000_000_000 if cycle == 0 else 340_000_000_000
            self.launch()
            self.successor("manager")

    def history(self):
        name = "history-pending-retirement"
        old = self.effect(name, retire=False)
        original_launch = self.raw_launch(1)
        for stage in ("live", "unreaped"):
            self.add("launch_refused", {"stage": stage, "expected_generation": 0, "errno": 16, "launch_receipt": original_launch})
            if stage == "live":
                for role in ("recovery", "manager"):
                    self.add("initial_owner_retired", {"role": role, "peer_lifetime": self.peer(role), "pidfd_revents": 1,
                                                       "wait_kind": "signaled", "wait_value": 9, "signal": 9})
        stable = int.from_bytes(bytes([4] * 16), "little")
        watchdog = {"stable_object_id": [4] * 16, "previous_revision": self.revision,
                    "revision": self.revision + 1, "effective_ns": 6_000_000_000, "consumed_ns": 0}
        stats = {"hepta_watchdog_armed": 1, "hepta_watchdog_ticks": 100, "hepta_watchdog_due_ns": 6_000_000_000,
                 "hepta_watchdog_expires_ns": 31_000_000_000, "hepta_watchdog_status": 1, "hepta_watchdog_evaluated_ns": 6_000_000_000,
                 "hepta_job_stop_available": 1, "hepta_job_stopped": 0, "hepta_user_pause_intent_available": 0,
                 "hepta_watchdog_stable_id_low": stable & ((1 << 64) - 1), "hepta_watchdog_stable_id_high": stable >> 64,
                 **{"hepta_watchdog_" + key: watchdog[key] for key in ("previous_revision", "revision", "effective_ns", "consumed_ns")}}
        raw = "".join(f"{key} {value}\n" for key, value in stats.items())
        self.add("history_watchdog", {"first_cpu_stat": raw, "second_cpu_stat": raw})
        binding = self.current["manager"]["head"]["writer_binding"]
        self.add("local_lease_retired", {"lease_id": binding["lease_id"], "generation": 1, "mode": "expired",
                 "observed_unix_seconds": binding["expires_at_unix_seconds"], "expires_at_unix_seconds": binding["expires_at_unix_seconds"]})
        self.add("initial_recovery_reaped", {"peer_lifetime": self.peer("recovery"),
                 "registry": {"schema_version": 1, "agent_id": self.agent, "generation": 5, "lifecycle": "failed"},
                 "driver_fault": "inert test error: kernel-initial child is no longer alive", "supervisor": self.snapshot(failed=True)})
        self.last_lifecycle, self.time, self.revision, self.cap = 5, 22_000_000_000, watchdog["revision"], e.CAP_NS
        self.launch(history=True)
        self.successor("history_only")
        self.add("reconciled", {"operation": name, "pid": self.pids["history_only"], "occurrence_key": old["key"],
                 "request_json": old["request_json"], "terminal_json": old["terminal_json"], "usage": None})
        self.source_terminal(name, "history_only", recovered=True)
        self.ack(name, "history_only")
        self.release()
        self.launch(watchdog=watchdog)
        self.successor("manager")
        fresh = self.effect("fresh-control-after-history")
        self.add("history_only_complete", {"old_delivery": old["request"]["delivery"], "old_occurrence_key": old["key"],
                 "actual_terminal_json": fresh["terminal_json"], "fresh_delivery": fresh["request"]["delivery"],
                 "fresh_occurrence_key": fresh["key"], "kernel_launch_generation": 2})

    def raw(self):
        image = f"[hepta-g2] trusted initial image committed: bytes={ELF['bytes']} entry={ELF['entry']:#x}"
        lines = [image] * 4 + ["[hepta-g2] initial roles activated: root=1 manager=2 workload=3 recovery=4 workload_uid=60002 bootstrap_version=3 bytes=200 hepta_durability=false"]
        for index, record in enumerate(self.records):
            lines.extend(self.kernel_before.get(index, []))
            lines.append(e.PREFIX + json.dumps(record, separators=(",", ":")))
        return ("\n".join(lines) + "\n").encode()
