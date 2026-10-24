"""Explicitly inert parser adversaries, never actual QEMU/owner evidence.

These helpers create no source receipt, key, native authority or campaign
disk. They only extend the existing isolated synthetic transcript examples.
"""
import copy
import hashlib
import struct

import native_owner_continuity_types as types
import native_owner_evidence as e
import native_owner_prior_boot_store as store
import native_owner_prior_boot_types as fixed
import native_owner_prior_renewal_evidence as oracle
from native_owner_continuity_test_records import ContinuityRecords
from native_owner_prior_boot_test_records import PriorRecords
from test_native_owner_evidence import ELF, InertRecords, NONCE, sha


class RenewalRecords(PriorRecords):
    def add(self, name, value):
        self.scenario = oracle.SCENARIO
        InertRecords.add(self, name, value)

    def authority(self, previous):
        if not self.authorities:
            self.spaces = {"manager": self.space(2), "recovery": self.space(3)}
            self.initial_spaces = copy.deepcopy(self.spaces)
        result = super().authority(previous)
        if self.previous is not None:
            result["root"]["binding"]["scope_sha256"] = list(hashlib.sha256(
                b"hepta.hos2.cpu-budget.scope.v1\0" + bytes(self.previous["native_boot_id"])
                + bytes(self.previous["spaces"]["manager"]) + struct.pack("<QQ", 2, 1)).digest())
            claims = result["proof"]["claims"]
            claims["sequence"] = self.local_generation + 1 + (self.local_generation - 1) // 2
            proof_hash = types.sha(result["proof"])
            result["binding"]["authority_grant_digest"] = proof_hash
            result["binding"]["fencing_token_digest"] = hashlib.sha256(hashlib.sha256(
                b"hepta:production-authority-token-grant:v2\0" + proof_hash.encode()
                + result["proof"]["signature_hex"].encode()).digest()).hexdigest()
        return result

    def first(self):
        self.kernel_before = {}
        super().first()

    def transport(self, count):
        value = super().transport(count)
        if self.previous is not None:
            role = getattr(self, "active_role", "manager")
            value.update(pid=self.pids[role], database_inode=14 + self.local_generation,
                         database_path=fixed.BASE + "/fleet/agents/" + self.agent + "/cognitive/"
                         + "cognitive_recovered_v1_" + sha("inert-database-" + str(self.local_generation)) + ".sqlite3")
        return value

    def retained(self, phase):
        cut = self.previous["cut"]
        count = 1 if phase == "before_stop" and self.active_role == "manager" else 0
        transport = self.transport(count)
        before = {"operation": store.operation_observation(self.stopped["live_database"]["operation"]),
                  "topic": fixed.TOPIC, "payload_json": cut["payload_json"], "state": "indeterminate"}
        observation = {"pid": self.pids[self.active_role], "occurrence_key": cut["occurrence_key"],
                       "request_json": cut["payload_json"], "before": before, "after": before,
                       "refusal": "native boot changed; the old D remains unknown",
                       "calls_before": transport["ioctl_counts"], "calls_after": transport["ioctl_counts"],
                       "drain_blockers": 1, **self.frontiers}
        return copy.deepcopy({"phase": phase, "observation": observation, "transport": transport,
            "terminal_lookup": {"error_kind": "illegal_transition",
                                "reason": "HOS2 predecessor lacks complete durable native terminal evidence"}})

    def emit_owner(self):
        ContinuityRecords.emit_owner(self)
        self.records[-1]["payload"]["retained_prior_boot"] = self.retained("owner_started")

    def release(self):
        prior = self.retained("before_stop")
        ContinuityRecords.release(self)
        self.records[-2]["payload"]["retained_prior_boot"] = prior

    def second(self):
        self.kernel_before, self.saved = {}, {}
        self.active_role, self.last_lifecycle = "manager", self.spawn
        self.launch_pids = {**self.pids, "history": 0}
        self.observed("before_new_effect", 0)
        first = self.usage("manager")
        threshold = first["sample_boottime_ns"] + 330_000_000_000
        auth = self.authorities["manager"]
        self.add("renewal_origin", {"initial_usage": first, "after_boottime_ns": threshold,
                                   "initial_root_lease": auth["root"], "initial_writer": auth["writer"]})
        self.emit_owner()
        for cycle in range(3):
            operation = self.effect("continued-control")
            if cycle == 2:
                auth = self.authorities["manager"]
                self.add("renewal_endpoint", {"initial_sample_boottime_ns": first["sample_boottime_ns"],
                    "after_boottime_ns": threshold, "actual_terminal_json": operation["terminal_json"],
                    "occurrence_key": operation["key"], "delivery": operation["request"]["delivery"],
                    "fresh_kernel_generations": [1, 2], "root_lease": auth["root"], "writer": auth["writer"]})
                break
            self.operations[operation["key"]] = self.operations.pop("continued-control")
            self.release()
            self.successor("recovery")
            self.release()
            self.time = 40_000_000_000 if cycle == 0 else 400_000_000_000
            self.launch()
            self.successor("manager")
        old = self.retained("before_stop")
        final_sequence = self.authorities["manager"]["proof"]["claims"]["sequence"] + 1
        self.add("prior_boot_observed", {"phase": "after_renewal", "transport": old["transport"],
                 "observation": old["observation"], "authority": self.observation_authority(final_sequence, 24)})
        terminal = copy.deepcopy(self.current["manager"]["token"])
        self.release()
        self.add("complete", {"root_pid": 1, "operation_count": len(self.operations),
                              "final_owner_pid": self.pids["manager"], "final_current_token": terminal})

    def evaluate(self):
        record = {"raw_exit_code": -9 if self.phase == "fresh" else 33, "timed_out": False, "serial_excessive": False}
        return oracle.evaluate(self.raw(), record, NONCE, ELF, self.phase, self.previous, self.stopped)

    def raw(self):
        return ContinuityRecords.raw(self)


def pair():
    first = RenewalRecords()
    previous = first.evaluate()
    old = previous["old_operation"]
    request = old["request"]
    operation = {"operation_id": old["key"], "subject_id": fixed.AGENT, "destination_id": "hos2.cpu-budget.v1",
                 "payload_sha256": sha(old["request_json"]), "scope_sha256": hashlib.sha256(
                    b"hepta.hos2.cpu-budget.scope.v1\0" + bytes(request["delivery"]["boot_id"])
                    + bytes(request["delivery"]["space_id"]) + struct.pack("<QQ", 2, 1)).hexdigest(),
                 "policy_generation": 7, "expected_predecessor_sha256": None}
    stopped = {"old_unknown_physically_verified": True, "live_database": {"operation": operation},
               "inert_parser_test_only": True}
    return first, RenewalRecords(previous, stopped)
