"""Strict original-owner continuity transcripts over actual finite Process roles.

The shared original operation/Current/retirement/window checks consume the same
raw events. This module advances only parser state derived from actual bootstrap,
Supervisor and writer DTOs. It has no owner, issuer or native effect operation.
"""
import hashlib

import native_owner_evidence as base
import native_owner_continuity_types as types
from native_owner_continuity_kernel import Launches
from native_owner_successor_wire import initial_bootstrap, initial_expiry_upper_bound, launch_receipt, successor_bootstrap


OWNER_KEYS = ("role", "pid", "kernel_bootstrap", "supervisor", "root_lease", "writer", "writer_proof", "current",
              "material_sha256", "device_frontier", "notes_frontier", "usage")


class Continuity:
    def __init__(self, context, markers):
        self.c = context
        self.initial_pids = dict(context.role_pids)
        self.initial_spaces = dict(context.spaces)
        self.initial_ready = context.owners["manager"]
        self.agent = self.initial_ready["agent_id"]
        self.launches = Launches(context.boot_id, self.initial_pids, self.initial_spaces, markers)
        self.active = None
        self.previous = None
        self.owner_processes = []
        self.seen_lifetimes = set()
        self.seen_root_leases = set()
        self.seen_writer_leases = set()
        self.last_lifecycle_generation = None
        self.last_stopped_line = -1
        self.adoption = None
        self.adoption_line = None
        self.last_usage = None
        self.last_effect = None
        self.policy_retirement = None
        self.observed_watchdog = None
        self.retirements = []
        self.root_binding = None

    def sample(self, value, role, expected_revision=None, expected_cap=None):
        current = base.usage(value, self.c.boot_id, self.c.spaces[role])
        if self.last_usage is not None:
            base.progression(self.last_usage, current)
        if expected_revision is not None:
            base.require(current["revision"] == expected_revision and current["active_cap_ns"] == expected_cap,
                         "current CPU state differs from the original retained effect/owner cut")
        elif self.last_effect is not None:
            effect = self.last_effect["observation"]
            base.require((current["revision"], current["active_cap_ns"])
                         in ((effect["revision"], self.last_effect["request"]["cap_ns"]),
                             (effect["revision"] + 1, base.CAP_NS)),
                         "owner handoff reset CPU state or added an unaccounted native effect")
        self.last_usage = current
        self.c.retain_usage(current)
        return current

    def adopt(self):
        self.adoption_line = self.c.next_line()
        value = base.obj(self.c.take("material_adopted"), ("previous", "successor", "material_sha256"), "original physical handoff")
        previous = self.c.currents[self.previous["role"]]
        base.require(value["previous"] == previous and value["material_sha256"] == self.c.materials[self.previous["role"]],
                     "successor replaced the independent previous Current or physical material")
        # The actual next bootstrap and Current below authenticate this peer;
        # no PID, start tick or original owner is invented here.
        successor = value["successor"]
        base.require(type(successor) is dict and type(successor.get("head")) is dict,
                     "complete original adoption receipt required")
        peer = base.obj(successor["head"]["peer_lifetime"], base.PEER_KEYS, "actual adopted publisher")
        adopted = base.checkpoint(successor, peer, self.agent)
        old, new = previous["head"], adopted["head"]
        base.require(new["publisher_epoch"] == old["publisher_epoch"] + 1
                     and new["counter"] == old["counter"] + 1 and new["last_current"] == old["last_current"]
                     and new["last_mutation_sequence"] == 0 and new["last_request"] is None,
                     "original material adoption changed the canonical cut or successor transaction")
        self.adoption = adopted

    def owner(self, role, initial=False):
        launched = self.launches.current
        retirement = None
        if self.c.peek() == "kernel_launch_saved":
            line = self.c.next_line()
            previous_kernel_generation = self.launches.current["generation"]
            launched, retirement = self.launches.saved_event(self.c.take("kernel_launch_saved"), line,
                                                             self.last_stopped_line, self.adoption_line)
            if retirement["policy_retired"] and launched["generation"] != previous_kernel_generation:
                self.check_policy_cut(retirement)
                self.observed_watchdog = None
        value = base.obj(self.c.take("continuity_owner"), OWNER_KEYS, "complete actual continuity owner")
        base.require(value["role"] == role and type(value["pid"]) is int,
                     "actual continuation role differs from the original Supervisor flow")
        if launched["generation"] == 0:
            bootstrap = initial_bootstrap(value["kernel_bootstrap"], self.c.boot_id, role, self.initial_pids, self.initial_spaces)
        else:
            base.require(retirement is not None, "each actual successor Host must return its exact saved Root observation")
            bootstrap = successor_bootstrap(value["kernel_bootstrap"], self.c.boot_id, launched)
            base.require(bootstrap["role"] == {"manager": 1, "recovery": 3, "history_only": 5}[role],
                         "actual bootstrap role differs from the activated original Host")
            if role == "history_only":
                base.require(bytes(bootstrap["local_space"]) not in self.launches.seen_namespaces,
                             "history-only image reused an older actual capability namespace")
                self.launches.seen_namespaces.add(bytes(bootstrap["local_space"]))
        base.require(value["pid"] == bootstrap["pid"], "continuation belongs to another actual final Process")
        peer = base.obj(value["current"]["head"]["peer_lifetime"], base.PEER_KEYS, "actual continuation peer")
        base.require(peer["uid"] == 60001 and type(peer["uid"]) is int and peer["pid"] == value["pid"]
                     and type(peer["pid"]) is int and peer["boot_id"] == self.c.peers["root"]["boot_id"],
                     "original continuation peer changed UID, PID or Linux boot")
        base.integer(peer["process_start_ticks"], "actual continuation start ticks", 1)
        lifetime = (peer["pid"], peer["boot_id"], peer["process_start_ticks"])
        base.require(lifetime not in self.seen_lifetimes, "a previous actual owner lifetime was reused")
        if launched["generation"] == 0:
            base.require(peer == self.c.peers[role], "initial actual peer differs from original four-role evidence")
        else:
            base.require(all(peer != self.c.initial_peers[name] for name in ("manager", "recovery")),
                         "successor reused an original initial Process lifetime")
        current = base.checkpoint(value["current"], peer, self.agent)
        auth = types.authority(value["root_lease"], value["writer"], value["writer_proof"], current, self.agent)
        writer, root = auth["writer"], auth["root"]
        expected_root_id = ("native-cpu-root-installation" if initial
                            else "native-cpu-root-writer-" + str(writer["local_lease_generation"]))
        base.require(root["lease_id"] == expected_root_id
                     and writer["authority_lease"]["lease_id"] == "native-cpu-writer-" + str(writer["local_lease_generation"])
                     and root["lease_id"] not in self.seen_root_leases
                     and writer["authority_lease"]["lease_id"] not in self.seen_writer_leases,
                     "a prior finite original lease was reused or silently extended")
        actual_frontiers = {key: base.frontier(value[key], key) for key in base.FRONTIER_LANES}
        base.require(all(item["authority_epoch"] == root["authority_epoch"] for item in actual_frontiers.values()),
                     "Root/writer and original consumers belong to different authority epochs")
        if initial:
            base.require(role == "manager" and self.active is None and self.previous is None
                         and current == self.c.currents["manager"]
                         and writer["spawn_generation"] == self.initial_ready["spawn_generation"]
                         and auth["proof_sha256"] == self.initial_ready["writer_proof_sha256"]
                         and actual_frontiers == self.c.frontiers["manager"]
                         and value["material_sha256"] == self.c.materials["manager"],
                         "initial full writer/session evidence differs from original owner readiness")
        else:
            base.require(self.previous is not None and self.adoption is not None, "original predecessor release/crash material is missing")
            previous = self.c.currents[self.previous["role"]]
            old_binding = previous["head"]["writer_binding"]
            base.checkpoint(self.adoption, peer, self.agent)
            base.require(current["head"]["publisher_epoch"] == self.adoption["head"]["publisher_epoch"]
                         and current["head"]["counter"] >= self.adoption["head"]["counter"]
                         and current["head"]["writer_binding"] == self.adoption["head"]["writer_binding"]
                         and current["head"]["last_current"]["schema_digest"] == previous["head"]["last_current"]["schema_digest"]
                         and writer["local_lease_id"] == old_binding["lease_id"]
                         and writer["local_lease_generation"] == old_binding["generation"] + 1
                         and writer["owner_epoch"] == old_binding["owner_epoch"] + 1
                         and writer["authority_lease"]["authority_epoch"] == old_binding["authority_epoch"]
                         and auth["proof_sha256"] != old_binding["authority_grant_digest"]
                         and writer["spawn_generation"] == self.last_lifecycle_generation + 1
                         and actual_frontiers == self.c.frontiers[self.previous["role"]],
                         "successor reset the original writer, lifecycle, Current or consumer lineage")
            old_auth = self.previous.get("authority")
            if old_auth is not None:
                base.require(auth["proof"]["claims"]["issuer_id"] == old_auth["proof"]["claims"]["issuer_id"]
                             and auth["proof"]["claims"]["sequence"] > old_auth["proof"]["claims"]["sequence"]
                             and root["issued_at_unix_ms"] >= old_auth["root"]["issued_at_unix_ms"]
                             and writer["authority_lease"]["binding"]["scope_sha256"]
                                 == old_auth["writer"]["authority_lease"]["binding"]["scope_sha256"],
                             "canonical original issuer, sequence or writer scope was reset")
            predecessor_cut = base.ordered(previous["head"]["last_current"], base.CUT_KEYS, "canonical original predecessor cut")
            payload = types.sha([predecessor_cut, writer["spawn_generation"], writer["local_lease_generation"]])
            base.require(bytes(writer["authority_lease"]["binding"]["payload_sha256"]).hex() == payload,
                         "successor writer lease does not bind the exact original cut and two original generations")
        if self.root_binding is None:
            self.root_binding = root["binding"]
        original_root_scope = hashlib.sha256(b"hepta.hos2.cpu-budget.scope.v1\0" + bytes(self.c.boot_id)
                                            + bytes(self.initial_spaces["manager"])
                                            + (2).to_bytes(8, "little") + (1).to_bytes(8, "little")).digest()
        base.require(root["binding"] == self.root_binding
                     and bytes(root["binding"]["scope_sha256"]) == original_root_scope
                     and bytes(root["binding"]["payload_sha256"]) == hashlib.sha256(b"native-root-installation-observation-only").digest(),
                     "Root finite observation lease changed its original binding or became an effect grant")
        lifecycle = types.supervisor(value["supervisor"], writer["spawn_generation"], value["pid"], True)
        base.digest(value["material_sha256"], "actual continuation physical material")
        self.c.role_pids[role] = value["pid"]
        self.c.peers[role] = peer
        if role == "manager":
            new_space = bootstrap["local_space"]
            if new_space != self.c.spaces["manager"]:
                self.c.native_sequence["manager"] = 0
            self.c.spaces["manager"] = new_space
            self.c.spaces["recovery"] = bootstrap["history_spaces"][1]
            self.c.native_sequence["recovery"] = 0
        elif role in ("recovery", "history_only"):
            self.c.spaces[role] = bootstrap["local_space"]
        # A parser projection of the actual registered Agent, not an invented
        # owner_ready event or registration accepted by a producer.
        self.c.owners[role] = {"agent_id": self.agent, "spawn_generation": writer["spawn_generation"]}
        self.c.currents[role] = current
        self.c.materials[role] = value["material_sha256"]
        self.c.frontiers[role] = actual_frontiers
        if role == "history_only":
            base.require(value["usage"] is None, "history-only Process fabricated CPU observation authority")
        elif initial:
            self.sample(value["usage"], role, 1, base.CAP_NS)
        elif retirement is not None and role == "manager":
            expected_revision, expected_cap = self.policy_state(retirement)
            self.sample(value["usage"], role, expected_revision, expected_cap)
        else:
            self.sample(value["usage"], role)
        self.active = {"role": role, "pid": value["pid"], "peer": peer, "bootstrap": bootstrap,
                       "authority": auth, "supervisor": lifecycle, "kernel_generation": launched["generation"]}
        self.seen_lifetimes.add(lifetime)
        self.seen_root_leases.add(root["lease_id"])
        self.seen_writer_leases.add(writer["authority_lease"]["lease_id"])
        self.owner_processes.append({"role": role, "peer_lifetime": peer, "kernel_launch_generation": launched["generation"],
                                     "spawn_generation": writer["spawn_generation"], "local_writer_generation": writer["local_lease_generation"]})
        self.adoption = None
        return value

    def operation(self, name, with_ack=True, with_window=True):
        base.require(self.active is not None and self.active["role"] == "manager", "only the actual Manager may prepare a new CPU effect")
        self.c.prepared(name, "manager", 25_000_000)
        operation = self.c.operations[name]
        request = operation["request"]
        base.require([request["manage_slot"], request["manage_generation"]] == self.active["bootstrap"]["manage_handle"]
                     and operation["key"] == "native-cpu:" + types.sha(request["delivery"]) + ":" + name,
                     "actual original K or effect handle differs from this final Manager image")
        self.c.native_result(name, "applied")
        self.c.source_terminal(name, "manager")
        if with_ack:
            self.c.acknowledge(name, "manager")
        if with_window:
            self.c.window(name, "manager", 25_000_000, operation["observation"]["revision"])
        self.last_usage = self.c.current_usage()
        self.last_effect = operation
        return operation

    def release(self):
        role = self.active["role"]
        value = base.obj(self.c.take("owner_released"), ("pid", "peer_lifetime", "receipt", "current", "material_sha256",
                                                       "device_frontier", "notes_frontier"), "actual original writer release")
        base.require(value["pid"] == self.active["pid"] and type(value["pid"]) is int and value["peer_lifetime"] == self.active["peer"],
                     "release observation came from another actual live publisher")
        current = base.checkpoint(value["current"], self.active["peer"], self.agent)
        old = self.c.currents[role]
        base.require(current["head"]["writer_binding"] == old["head"]["writer_binding"]
                     and current["head"]["publisher_epoch"] == old["head"]["publisher_epoch"]
                     and current["head"]["counter"] > old["head"]["counter"]
                     and current["head"]["last_current"]["schema_digest"] == old["head"]["last_current"]["schema_digest"]
                     and current["head"]["last_current"]["state_digest"] != old["head"]["last_current"]["state_digest"],
                     "successful release lacks its newly acknowledged original Current transaction")
        receipt = types.released(value["receipt"], current, self.agent)
        actual_frontiers = {key: base.frontier(value[key], key) for key in base.FRONTIER_LANES}
        base.require(actual_frontiers == self.c.frontiers[role], "ordinary release changed an original FinalUse frontier")
        self.c.currents[role] = current
        self.c.materials[role] = base.digest(value["material_sha256"], "released physical material")
        self.last_stopped_line = self.c.next_line()
        stopped = base.obj(self.c.take("owner_stopped"), ("pid", "peer_lifetime", "release_generation", "supervisor"),
                           "actual original Supervisor release/reap")
        base.require(stopped["pid"] == self.active["pid"] and type(stopped["pid"]) is int
                     and stopped["peer_lifetime"] == self.active["peer"]
                     and type(stopped["release_generation"]) is int and stopped["release_generation"] == receipt["generation"],
                     "original reap does not name the successfully released publisher and lease")
        stopped_snapshot = types.supervisor(stopped["supervisor"], self.active["authority"]["writer"]["spawn_generation"],
                                            self.active["pid"], False, prior=self.active["supervisor"])
        self.last_lifecycle_generation = stopped_snapshot["events"][-1]["generation"]
        self.previous = self.active
        self.active = None

    def check_policy_cut(self, retired):
        base.require(self.last_effect is not None, "a CPU policy was retired before its original Manager effect")
        effect = self.last_effect["observation"]
        receipt = retired["resource_receipt"]
        if receipt is not None:
            base.require(receipt["stable_object_id"] == effect["stable_object_id"]
                         and receipt["previous_revision"] == effect["revision"]
                         and receipt["effective_ns"] >= effect["effective_ns"],
                         "final old-owner watchdog cut replaced the original CPU history")
            if self.observed_watchdog is not None:
                base.require(receipt == self.observed_watchdog, "actual final owner cut lost or recomputed the observed watchdog receipt")
        elif self.observed_watchdog is not None:
            raise ValueError("old policy retirement lost its independently observed restored watchdog")
        self.retirements.append(retired)

    def policy_state(self, retired):
        base.require(retired["policy_retired"] and self.last_effect is not None, "fresh pair lacks the old original policy cut")
        receipt = retired["resource_receipt"]
        return ((receipt["revision"], base.CAP_NS) if receipt is not None
                else (self.last_effect["observation"]["revision"], self.last_effect["request"]["cap_ns"]))


def run(scenario, context, markers):
    continuity = Continuity(context, markers)
    if scenario == "successor-renewal-v1":
        from native_owner_continuity_scenarios import renewal
        flags = renewal(continuity)
    elif scenario == "history-only-after-both-owner-exit-v1":
        from native_owner_continuity_scenarios import history
        flags = history(continuity)
    else:
        raise ValueError("unsupported original continuity scenario")
    observations = continuity.launches.finish()
    return {**flags, "passed": False, "continuity_transcript_verified": True,
            "original_native_owner_cycle_verified": False, "same_boot_authenticated_successor_verified": False,
            "root_launch_files_verified": False, "root_launch_observations_expected": observations,
            "initial_role_pids": continuity.initial_pids, "actual_owner_processes": continuity.owner_processes,
            "actual_policy_retirements": continuity.retirements,
            "grant_renewal_verified": False, "repeated_recovery_verified": False,
            "unbounded_persistent_cpu_verified": False, "cross_boot_unknown_preservation_verified": False,
            "power_loss_verified": False, "g2_complete": False, "production_ready": False}
