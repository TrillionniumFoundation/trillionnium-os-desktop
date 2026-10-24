"""Inert rejection-test records; never original execution or qualification.

No signer, lease owner, Process, device, build or VM is run by these helpers.
Their synthetic values exercise the strict parser and cannot satisfy the
independent source/build/actual-QEMU/retained-file campaign admissions.
"""
import copy
import hashlib

import native_owner_activation_evidence as oracle
import native_owner_continuity_types as t
import native_owner_evidence as e
import native_owner_activation_witness as witness
from native_owner_continuity_test_records import ContinuityRecords
from test_native_owner_evidence import ELF, InertRecords, NONCE, sha


class ActivationRecords(ContinuityRecords):
    def __init__(self, scenario, agent=None):
        seed = InertRecords("steady-state-v1")
        self.__dict__.update(copy.deepcopy(seed.__dict__))
        self.scenario = scenario
        self.agent = agent or self.agent
        self.records = self.records[:4]
        for record in self.records:
            record["scenario"] = scenario
        self.event("owner_ready")["agent_id"] = self.agent
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
        self.owner_epoch, self.issuer_sequence = 11, 1
        self.active_role, self.last_lifecycle = "manager", 1
        self.launch_pids = {**self.pids, "history": 0}
        self.authorities["manager"] = self.authority(None)
        self.current["manager"] = self.new_current("manager", 1, 0, sha("inert-activation-initial-state"))
        self.event("owner_ready").update(current=self.current["manager"],
                                         writer_proof_sha256=t.sha(self.authorities["manager"]["proof"]))
        self.emit_owner()
        self.effect("before-partial-activation")
        self.release()
        self.failed_activation()
        self.operation("after-partial-activation", "manager", 1, 35_000_000)
        self.source_terminal("after-partial-activation", "manager")
        self.ack("after-partial-activation", "manager")
        self.window("after-partial-activation", "manager")
        self.add("complete", {"root_pid": 1, "operation_count": 2, "final_owner_pid": self.pids["manager"],
                              "final_current_token": self.current["manager"]["token"]})

    def authority(self, previous):
        value = super().authority(previous)
        value["writer"]["owner_epoch"] = self.owner_epoch
        proof = value["proof"]
        proof["claims"]["owner_epoch"] = self.owner_epoch
        proof["claims"]["sequence"] = self.issuer_sequence
        if previous is not None:
            root = {"uid": 0, "pid": 1, "boot_id": self.linux_boot, "process_start_ticks": 21}
            lease = value["writer"]["authority_lease"]
            lease["binding"]["payload_sha256"] = list(bytes.fromhex(witness.commitment(
                value["writer"], previous, root, self.authority_peer)))
            proof["claims"]["authority_lease_sha256"] = t.sha(lease)
        proof_hash = t.sha(proof)
        value["binding"].update(owner_epoch=self.owner_epoch, authority_grant_digest=proof_hash,
            fencing_token_digest=hashlib.sha256(hashlib.sha256(b"hepta:production-authority-token-grant:v2\0"
                + proof_hash.encode() + proof["signature_hex"].encode()).digest()).hexdigest())
        return value

    def failed_activation(self):
        released, material = self.current["manager"], self.material["manager"]
        self.spawn, self.local_generation, self.owner_epoch, self.issuer_sequence = self.last_lifecycle + 1, 2, 12, 3
        self.time = 2_000_000_000
        self.authority_peer = self.peer("recovery")
        failed = self.authorities["recovery"] = self.authority(released)
        previous = released
        installed = self.scenario == oracle.SCENARIOS[1]
        if installed:
            previous = self.new_current("recovery", released["head"]["publisher_epoch"] + 1,
                                        released["head"]["counter"] + 1,
                                        released["head"]["last_current"]["state_digest"])
        failed_peer = self.peer("recovery")
        # Future/current selection is complete in this inert example; Root
        # and both writer leases are all explicitly retired before reentry.
        leases = sorted([self.authorities["manager"]["root"], self.authorities["manager"]["writer"]["authority_lease"],
                         failed["root"], failed["writer"]["authority_lease"]], key=lambda value: value["lease_id"])
        observed = 1_002_000
        revoked = []
        for index, lease in enumerate(leases):
            reason = t.sha(["native-root-failed-activation-retirement.v1",
                            e.ordered(failed_peer, e.PEER_KEYS, "inert failed peer"),
                            e.ordered(previous["token"], e.TOKEN_KEYS, "inert failed cut"),
                            oracle.canonical_lease(lease)])
            revoked.append({"lease_id": lease["lease_id"], "authority_epoch": lease["authority_epoch"],
                            "previous_lease_revision": lease["revision"], "lease_revision": lease["revision"] + 1,
                            "store_revision": 10 + index + 1, "reason_sha256": list(bytes.fromhex(reason)),
                            "revoked_at_unix_ms": observed + index})
        expiry = previous["head"]["writer_binding"]["expires_at_unix_seconds"] * 1000
        reconciliation = {"failed_spawn_generation": self.spawn, "failed_peer": failed_peer,
            "fault": {"point": "after_material" if installed else "after_proof", "peer": failed_peer,
                      "spawn_generation": self.spawn, "pidfd_revents": 1, "wait_kind": "signaled", "wait_value": 9,
                      "observed_boottime_ns": self.time},
            "registry_failed": {"schema_version": 1, "agent_id": self.agent, "generation": self.spawn + 1, "lifecycle": "failed"},
            "mode": "installed" if installed else "unactivated", "previous": previous,
            "canonical_writer": failed["writer"], "canonical_proof_sha256": t.sha(failed["proof"]),
            "issuer_sequence": self.issuer_sequence,
            "registry_before": {"principal_id": self.agent, "store_revision": 10,
                                "observed_unix_ms": observed, "leases": leases},
            "revocations_applied": revoked,
            "registry_after": {"principal_id": self.agent, "store_revision": 10 + len(leases),
                               "observed_unix_ms": observed + len(leases), "leases": []},
            "observed_unix_ms": expiry, "local_expiry_unix_ms": expiry, **self.frontiers}
        self.add("activation_recovery_prepared", {"failure": "inert original activation failure",
            "supervisor": {"active": False, "healthy": False, "runtime_generation": None,
                           "spawn_generation": None, "process_system_id": None}, "reconciliation": reconciliation})
        self.last_lifecycle = self.spawn + 1
        self.time = 23_000_000_000
        watchdog = {"stable_object_id": [4] * 16, "previous_revision": self.revision,
                    "revision": self.revision + 1, "effective_ns": 7_000_000_000, "consumed_ns": 0}
        self.revision, self.cap = watchdog["revision"], e.CAP_NS
        self.launch(watchdog=watchdog)
        self.spawn, self.local_generation, self.owner_epoch, self.issuer_sequence = self.last_lifecycle + 1, 3 if installed else 2, 13, 5
        self.authority_peer = self.peer("manager")
        self.authorities["manager"] = self.authority(previous)
        adopted = self.new_current("manager", previous["head"]["publisher_epoch"] + 1,
                                   previous["head"]["counter"] + 1, previous["head"]["last_current"]["state_digest"])
        self.add("material_adopted", {"previous": released, "successor": adopted, "material_sha256": material})
        self.current["manager"] = copy.deepcopy(adopted)
        self.advance_current("manager", "after-failure-ready")
        self.emit_owner()

    def evaluate(self):
        return oracle.evaluate(self.raw(), 33, False, False, self.scenario, NONCE, ELF)
