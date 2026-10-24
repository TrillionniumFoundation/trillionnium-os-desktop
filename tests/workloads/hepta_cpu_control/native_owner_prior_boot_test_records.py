"""Inert schema records only; these never qualify a guest or original owner.

The helpers construct no source review, build receipt, disk campaign or QEMU
process. Their intentionally synthetic values are solely parser adversaries.
"""
import copy
import hashlib
import struct

import native_owner_evidence as e
import native_owner_prior_boot_evidence as oracle
import native_owner_prior_boot_store as store
import native_owner_prior_boot_types as t
from native_owner_continuity_test_records import ContinuityRecords
from native_owner_fault_wire import expected_install_wire
from test_native_owner_evidence import ELF, InertRecords, NONCE, sha


class PriorRecords(ContinuityRecords):
    def __init__(self, previous=None, stopped=None):
        seed = InertRecords("steady-state-v1")
        self.__dict__.update(copy.deepcopy(seed.__dict__))
        self.scenario, self.phase = t.SCENARIO, "fresh" if previous is None else "retained"
        self.previous, self.stopped = previous, stopped
        self.agent = t.AGENT
        self.boot = [1 if previous is None else 4] * 16
        self.linux_boot = t.uuid(self.boot)
        self.spaces = {"manager": [2 if previous is None else 5] * 16,
                       "recovery": [3 if previous is None else 6] * 16}
        self.initial_spaces = copy.deepcopy(self.spaces)
        self.time = 1_000_000_000 if previous is None else 30_000_000_000
        self.total, self.heartbeat, self.revision, self.cap = 1_000_000, 1, 1, e.CAP_NS
        self.spawn, self.local_generation, self.generation = 1, 1 if previous is None else 2, 0
        self.operations, self.authorities = {}, {}
        self.initial_pids = dict(self.pids)
        self.frontiers = {lane: copy.deepcopy(seed.event("owner_ready")[lane]) for lane in e.FRONTIER_LANES}
        if previous is not None:
            self.frontiers = dict(zip(e.FRONTIER_LANES, copy.deepcopy(previous["cut"]["frontiers"])))
        self.authorities["manager"] = self.authority(None if previous is None else previous["cut_current"])
        initial_cut = sha("inert-prior-start") if previous is None else previous["cut_current"]["head"]["last_current"]["state_digest"]
        counter = 0 if previous is None else previous["cut_current"]["head"]["counter"] + 1
        self.current = {"manager": self.new_current("manager", self.local_generation, counter, initial_cut)}
        self.material = {"manager": sha("inert-prior-material") if previous is None else previous["cut_material_sha256"]}
        self.pin = {"path": t.PIN_PATH, "device": 254, "inode": 20, "bytes": 256,
                    "sha256": sha("inert-public-installation"), "expected_verifying_key": [9] * 32}
        self.records = []
        self.add("boot_phase", {"phase": self.phase, "kernel_boot": self.boot, "installation": self.pin})
        if previous is not None:
            self.add("prior_boot_adopted", self.cold_event())
        roles = copy.deepcopy(seed.event("roles"))
        roles.update(native_boot_id=self.boot, manager_space=self.spaces["manager"],
                     recovery_space=self.spaces["recovery"], linux_boot_id=self.linux_boot)
        self.add("roles", roles)
        self.state = copy.deepcopy(seed.event("state"))
        self.state["store_inode"] = 11 if previous is None else 16
        self.add("state", self.state)
        self.add("boundary", seed.event("boundary"))
        self.owner_ready("manager")
        ready = self.records[-1]["payload"]
        ready.update(issuer_key_sha256=hashlib.sha256(bytes(self.pin["expected_verifying_key"])).hexdigest(),
                     writer_proof_sha256=self.current["manager"]["head"]["writer_binding"]["authority_grant_digest"])
        if previous is None:
            self.first()
        else:
            self.second()

    def clock(self):
        now = 1_000_000 + self.time // 1_000_000
        return {"projection": {"schema_version": 1, "boot_id": self.linux_boot,
                "anchor_boottime_ns": self.time, "anchor_unix_ms": now, "ceiling_unix_ms": now + 1000},
                "observed_unix_ms": now}

    def observation_authority(self, sequence, revision):
        auth = self.authorities["manager"]
        leases = sorted([auth["root"], auth["writer"]["authority_lease"]], key=lambda value: value["lease_id"])
        return {"issuer_sequence": sequence, "writer_proof_sha256": self.current["manager"]["head"]["writer_binding"]["authority_grant_digest"],
                "writer": auth["writer"], "revocations": {"authority_epoch": 7, "revision": 1, "revoked_grant_ids": []},
                "registry": {"principal_id": self.agent, "store_revision": revision,
                             "observed_unix_ms": self.clock()["observed_unix_ms"], "leases": leases},
                "clock": self.clock()}

    def transport(self, count):
        path = "cognitive_1.sqlite3" if self.previous is None else "cognitive_recovered_v1_" + "b" * 64 + ".sqlite3"
        old = self.previous["cut"] if self.previous is not None else None
        return {"pid": 2, "database_path": t.BASE + "/fleet/agents/" + self.agent + "/cognitive/" + path,
                "database_device": 254, "database_inode": self.state["store_inode"],
                "ioctl_counts": {"install_ioctl_count": count, "query_ioctl_count": count},
                "startup_retained": [] if old is None else [{"occurrence_key": old["occurrence_key"], "topic": t.TOPIC,
                                                             "payload_json": old["payload_json"], "state": "indeterminate"}]}

    def first(self):
        before = self.observation_authority(1, 3)
        source = self.transport(0)
        self.operation("prior-boot-unresolved", "manager", 1, 25_000_000)
        self.records.pop()  # The actual case does not return a terminal to Root.
        op = self.operations["prior-boot-unresolved"]
        self.advance_current("manager", "inert-effect-entry")
        at = self.time + 1
        boundary = {"phase": "copyout_fault_boundary", "pid": 2, "occurrence_key": op["key"],
                    "diagnostic": {"install_ioctl_count": 1, "selected_ioctl_count": 1, "efault_count": 1,
                        "request_sha256": list(hashlib.sha256(expected_install_wire(op["request_json"])).digest()),
                        "request_bytes": 96, "response_capacity": 128, "syscall_return": -1, "errno": 14},
                    "observed_boottime_ns": at, "pending_until_boottime_ns": at + 2_000_000_000}
        cut = {"schema_version": 1, "nonce": NONCE, "kernel_boot": self.boot,
               "current_token": self.current["manager"]["token"], "occurrence_key": op["key"],
               "payload_json": op["request_json"], "material_sha256": self.material["manager"],
               "frontiers": [self.frontiers[lane] for lane in e.FRONTIER_LANES], "boundary": boundary,
               "installation": self.pin, "source_database": source,
               "authority_before_sha256": sha(e.canonical(before)), "issuer_sequence_at_cut": 2}
        raw = e.canonical(cut)
        observation_id = "native-boot-cut." + self.linux_boot + "." + NONCE
        self.add("prior_boot_cut", {"current": self.current["manager"], "material_path": t.AUTHORITY + "/material/inert.sqlite3",
                 "authority_before_dispatch": before, "observation_id": observation_id,
                 "observation_path": t.OBSERVATIONS + "/" + t.cut_filename(observation_id),
                 "durable_payload_json": raw, "durable_payload_sha256": sha(raw), "emitted_boottime_ns": at + 1})

    def cold_event(self):
        previous, cut = self.previous, self.previous["cut"]
        # All old finite writer/effect leases are already expired. Root's
        # original 120-second lease remains selected and is actually revoked
        # in the schema example; no caller-supplied time creates a lease.
        leases = [item for item in previous["cut_event"]["authority_before_dispatch"]["registry"]["leases"]
                  if item["expires_at_unix_ms"] > self.clock()["observed_unix_ms"]]
        at = self.clock()["observed_unix_ms"]
        cold = {"previous": previous["cut_current"], "previous_writer": previous["cut_event"]["authority_before_dispatch"]["writer"],
                "writer_proof_sha256": previous["original_owner"]["writer_proof_sha256"],
                "issuer_sequence": cut["issuer_sequence_at_cut"],
                "revocations": previous["cut_event"]["authority_before_dispatch"]["revocations"],
                "registry_before": {"principal_id": self.agent, "store_revision": 4,
                                    "observed_unix_ms": at, "leases": leases},
                "revocations_applied": [{"lease_id": lease["lease_id"], "authority_epoch": 7,
                    "previous_lease_revision": 1, "lease_revision": 2, "store_revision": 5 + index,
                    "reason_sha256": [8] * 32, "revoked_at_unix_ms": at} for index, lease in enumerate(leases)],
                "registry_after": {"principal_id": self.agent, "store_revision": 4 + len(leases),
                                   "observed_unix_ms": at, "leases": []}, "clock": self.clock(), **self.frontiers}
        return {"cold_open": cold, "successor": self.current["manager"],
                **{key: previous["cut_event"][key] for key in
                   ("observation_id", "observation_path", "durable_payload_json", "durable_payload_sha256")}}

    def observed(self, phase, count):
        cut = self.previous["cut"]
        before = {"operation": store.operation_observation(self.stopped["live_database"]["operation"]),
                  "topic": t.TOPIC, "payload_json": cut["payload_json"], "state": "indeterminate"}
        counts = {"install_ioctl_count": count, "query_ioctl_count": count}
        self.add("prior_boot_observed", {"phase": phase, "transport": self.transport(count), "observation": {
            "pid": 2, "occurrence_key": cut["occurrence_key"], "request_json": cut["payload_json"],
            "before": before, "after": before, "refusal": "native boot changed; the old D remains unknown",
            "calls_before": counts, "calls_after": counts, "drain_blockers": 1, **self.frontiers}})

    def second(self):
        self.observed("before_new_effect", 0)
        self.operation("new-boot-control", "manager", 1, 25_000_000)
        self.source_terminal("new-boot-control", "manager")
        self.ack("new-boot-control", "manager")
        self.window("new-boot-control", "manager")
        self.observed("after_new_effect", 1)
        self.add("prior_boot_complete", {"current": self.current["manager"],
                 "material_path": t.AUTHORITY + "/material/inert-final.sqlite3", "material_sha256": self.material["manager"],
                 "authority": self.observation_authority(4, 8), "unresolved_occurrence_key": self.previous["cut"]["occurrence_key"],
                 "drain_blockers": 1, "shutdown": "poweroff_with_unresolved_previous_boot"})

    def evaluate(self):
        record = {"raw_exit_code": -9 if self.phase == "fresh" else 33, "timed_out": False, "serial_excessive": False}
        return oracle.evaluate(self.raw(), record, NONCE, ELF, self.phase, self.previous, self.stopped)

    def raw(self):
        return InertRecords.raw(self)


def pair():
    first = PriorRecords()
    previous = first.evaluate()
    old = previous["old_operation"]
    request = old["request"]
    operation = {"operation_id": old["key"], "subject_id": t.AGENT, "destination_id": "hos2.cpu-budget.v1",
                 "payload_sha256": sha(old["request_json"]), "scope_sha256": hashlib.sha256(
                    b"hepta.hos2.cpu-budget.scope.v1\0" + bytes(request["delivery"]["boot_id"])
                    + bytes(request["delivery"]["space_id"]) + struct.pack("<QQ", 2, 1)).hexdigest(),
                 "policy_generation": 7, "expected_predecessor_sha256": None}
    # This inert marker only reaches the parser's isolated test seam. The
    # actual runner always derives it from actual stopped disk/SQLite I/O.
    stopped = {"old_unknown_physically_verified": True, "live_database": {"operation": operation},
               "inert_parser_test_only": True}
    return first, PriorRecords(previous, stopped)
