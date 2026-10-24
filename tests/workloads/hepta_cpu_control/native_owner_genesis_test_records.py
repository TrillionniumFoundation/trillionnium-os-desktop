"""Inert parser adversaries only: never native output or source-build evidence.

There is no signer, Root, daemon, QEMU, authority registry or effect here. The
separate actual runner cannot consume these records as build/physical inputs.
"""
import copy
import hashlib
import struct

import native_owner_continuity_types as types
import native_owner_evidence as e
import native_owner_genesis_evidence as oracle
import native_owner_genesis_record as record
import native_owner_genesis_types as t
import native_owner_genesis_witness as witness
import native_owner_prior_boot_authority as authority
import native_owner_prior_boot_types as fixed
from native_owner_continuity_test_records import ContinuityRecords
from test_native_owner_evidence import ELF, InertRecords, NONCE, sha


def observed(identity, directory, value, inode):
    payload = e.canonical(value)
    raw = e.canonical({"schema_version": 1, "observation_id": identity, "payload": list(payload.encode())}).encode()
    return {"observation_id": identity, "path": directory + "/" + fixed.cut_filename(identity), "device": 254,
            "inode": inode, "record_bytes": len(raw), "record_sha256": hashlib.sha256(raw).hexdigest(),
            "payload_json": payload, "payload_sha256": sha(payload)}


def no_head_state(previous=None):
    boot = list(range(1, 17)) if previous is None else list(range(17, 33))
    spaces = {name: boot[:8] + list(index.to_bytes(8, "little")) for name, index in (("manager", 2), ("recovery", 3))}
    root = {"uid": 0, "pid": 1, "boot_id": fixed.uuid(boot), "process_start_ticks": 21}
    raw = bytearray(200)
    raw[:8] = b"HOS2BOOT"
    for offset, value in {8: 3, 16: 4, 24: 200, 144: 2, 152: 3, 160: 4, 168: e.CAP_NS,
                          176: e.PERIOD_NS, 184: e.LEASE_NS, 192: 1}.items():
        struct.pack_into("<Q", raw, offset, value)
    raw[96:112], raw[112:128], raw[128:144] = bytes(boot), bytes(spaces["manager"]), bytes(spaces["recovery"])
    policies = [{"subject_id": fixed.AGENT, "destination_id": "hos2.cpu-budget.v1", "scope_sha256": list(hashlib.sha256(
        b"hepta.hos2.cpu-budget.scope.v1\0" + bytes(boot) + bytes(spaces[name]) + struct.pack("<QQ", 2, 1)).digest()),
        "lifetime_ms": 5000} for name in ("manager", "recovery")]
    now = 2_001_000 if previous is None else 2_003_000
    if previous is None:
        anchor = {"profile": "hepta:cognitive:exact-current-cut:v1", "owner_agent_id": fixed.AGENT,
                  "schema_digest": sha("original-schema"), "state_digest": sha("inert-initial-no-head-state")}
        saved = {"schema_version": 1, "initial_root": root, "initial_cut": anchor, "issuer_id": fixed.SIGNER,
                 "verifying_key": [19] * 32, "policies": policies}
        binding = {"principal_id": fixed.AGENT, "operation_class": "runtime.agentd.production_operation",
                   "destination_id": "hos2.cpu-budget.v1", "scope_sha256": policies[0]["scope_sha256"],
                   "payload_sha256": list(hashlib.sha256(b"native-root-installation-observation-only").digest())}
        bootstrap = {"schema_version": 1, "required_bind": {"mountpoint": fixed.PROTECTED,
            "source_path": fixed.BASE + "/protected-source", "device": 254, "inode": 30}, "signer_id": fixed.SIGNER,
            "policies": policies, "lease_id": "native-cpu-root-installation", "lease_binding": binding, "lease_lifetime_ms": 120000}
        intent = {"schema_version": 1, "initial_root": root, "initial_kernel_boot": boot, "initial_cut": anchor, "bootstrap": bootstrap}
        old = {"schema_version": 1, "lease_id": "native-cpu-root-installation", "authority_epoch": 1, "revision": 1,
               "binding": binding, "issued_at_unix_ms": now - 10, "expires_at_unix_ms": now - 10 + 120000}
        registry = {"authority_epoch": 1, "store_revision": 2, "leases": {old["lease_id"]: old},
                    "revocations": {}, "retired_revisions": {}}
        fixed_fields = {"installation": {"path": fixed.PIN_PATH, "device": 254, "inode": 20, "bytes": 256,
                        "sha256": sha("inert-installed-public-pin"), "expected_verifying_key": [19] * 32},
            "intent": observed(t.INTENT_ID, fixed.PROTECTED, intent, 31),
            "genesis": observed(record.identity(), record.DIRECTORY, saved, 32),
            "initial_material": {"path": oracle.authority_path(anchor), "sha256": sha("inert-retained-initial-sqlite"),
                                 "device": 254, "inode": 40, "cut": anchor},
            "source_database": {"path": t.INITIAL_DATABASE, "device": 254, "inode": 11},
            "registry_frontier": authority.lease_frontier(registry)}
        leases = [old]
    else:
        fixed_fields = {name: copy.deepcopy(previous[name]) for name in
                        ("installation", "intent", "genesis", "initial_material", "source_database", "registry_frontier")}
        leases = copy.deepcopy(previous["registry"]["leases"])
    return {"root": root, "kernel_boot": boot, "bootstrap_page": list(raw), **fixed_fields,
            "clock": {"projection": {"schema_version": 1, "boot_id": root["boot_id"], "anchor_boottime_ns": 1_000_000_000,
                       "anchor_unix_ms": now, "ceiling_unix_ms": now + 1000}, "observed_unix_ms": now},
            "registry": {"principal_id": fixed.AGENT, "store_revision": 2, "observed_unix_ms": now, "leases": leases},
            "issuer": {"signer_id": fixed.SIGNER, "policies": policies,
                       "head": {"authority_epoch": 1, "revision": 1, "revoked_grant_ids": []},
                       "sequence": 0, "writer_authorization": None},
            "fleet_lifecycle": {"schema_version": 1, "agent_id": fixed.AGENT, "generation": 0, "lifecycle": "stopped"},
            "observed_boottime_ns": 1_000_000_100}


class GenesisRecords(ContinuityRecords):
    def __init__(self, previous=None, stopped=None, scenario=t.SCENARIO):
        seed = InertRecords("steady-state-v1")
        self.__dict__.update(copy.deepcopy(seed.__dict__))
        self.scenario = scenario
        self.mode = dict(zip(t.SCENARIOS, ("before_writer", "writer_reserved", "before_head")))[scenario]
        self.records = []
        self.previous, self.stopped = previous, stopped
        self.phase = "fresh" if previous is None else "retained"
        self.installation = no_head_state(None if previous is None else previous["observed_installation"])
        self.boot = self.installation["kernel_boot"]
        self.linux_boot = self.installation["root"]["boot_id"]
        self.agent = fixed.AGENT
        self.spawn = 1 if previous is None or self.mode == "before_writer" else 3
        self.predecessor = None if previous is None or self.mode == "before_writer" else self.old_proof(previous)
        self.owner_epoch = 1 if self.predecessor is None else 2
        self.proof_sequence = self.owner_epoch
        self.local_generation, self.generation = 1, 0
        self.active_role = "manager"
        if previous is None:
            self.initial_cut()
            return
        if self.mode != "before_writer":
            self.retirement = self.retire_old(stopped)
            self.installation["issuer"] = copy.deepcopy(previous["observed_installation"]["issuer"])
            self.installation["issuer"].update(sequence=1, writer_authorization=self.predecessor)
            self.installation["fleet_lifecycle"].update(generation=1, lifecycle="starting")
        self.spaces = t.root_bootstrap(self.installation["bootstrap_page"], self.boot)
        self.time, self.total, self.heartbeat, self.revision, self.cap = 1_000_000_000, 1000000, 1, 1, e.CAP_NS
        self.operations = {}
        self.authorities = {"manager": self.authority(None)}
        anchor = self.installation["initial_material"]["cut"]
        first = self.new_current("manager", 1, 1, anchor["state_digest"])
        self.current = {"manager": self.new_current("manager", 1, 2, sha("inert-working-first-lease"))}
        self.material = {"manager": sha("inert-working-first-material")}
        initial = authority.final_use_frontier(self.installation["issuer"]["head"], [])
        self.frontiers = {lane: copy.deepcopy(initial) for lane in e.FRONTIER_LANES}
        self.add("genesis_reopened", self.installation)
        roles = copy.deepcopy(seed.event("roles"))
        roles.update(native_boot_id=self.boot, manager_space=self.spaces["manager"], recovery_space=self.spaces["recovery"],
                     linux_boot_id=self.linux_boot)
        self.add("roles", roles)
        self.state = copy.deepcopy(seed.event("state"))
        self.state["store_inode"] = 16
        self.add("state", self.state)
        self.add("boundary", seed.event("boundary"))
        self.owner_ready("manager")
        self.records[-1]["payload"].update(spawn_generation=self.spawn,
            issuer_key_sha256=hashlib.sha256(bytes([19] * 32)).hexdigest(),
            writer_proof_sha256=types.sha(self.authorities["manager"]["proof"]))
        saved = e.json_value(self.installation["genesis"]["payload_json"])
        resumed = {"initial_root": saved["initial_root"], "initial_kernel_boot": previous["native_boot_id"],
                   "initial_cut": saved["initial_cut"], "genesis_sha256": self.installation["genesis"]["payload_sha256"],
                   "issuer_id": fixed.SIGNER, "verifying_key": saved["verifying_key"],
                   "scopes": [item["scope_sha256"] for item in self.installation["issuer"]["policies"]]}
        if self.mode != "before_writer":
            resumed["unactivated_writer"] = {"writer": previous["first_candidate"]["writer"],
                "proof": self.predecessor, "peer": previous["first_candidate"]["peer"],
                "reservation": None if self.mode == "before_head" else previous["first_reservation"]["claims"],
                "completed_reserved_proof": None if self.mode == "before_head" else self.predecessor,
                "retirement": self.retirement}
        auth = self.authorities["manager"]
        self.add("genesis_first_owner", {"resumed": resumed, "first_checkpoint": first,
            "root_lease": auth["root"], "writer": auth["writer"], "writer_proof": auth["proof"],
            "current": self.current["manager"], "material_sha256": self.material["manager"],
            "fleet_lifecycle": {"schema_version": 1, "agent_id": fixed.AGENT, "generation": self.spawn + 1, "lifecycle": "running"},
            "transport": {"pid": 2, "database_path": fixed.BASE + "/fleet/agents/" + fixed.AGENT
                + "/cognitive/cognitive_recovered_v1_" + "ab" * 32 + ".sqlite3", "database_device": 254, "database_inode": 16,
                "ioctl_counts": {"install_ioctl_count": 0, "query_ioctl_count": 0}, "startup_retained": []},
            "activation": self.activation(auth)})
        self.effect(oracle.OPERATION)
        terminal_token = copy.deepcopy(self.current["manager"]["token"])
        self.release()
        self.add("complete", {"root_pid": 1, "operation_count": 1, "final_owner_pid": 2, "final_current_token": terminal_token})

    @staticmethod
    def old_proof(previous):
        if previous["cut_mode"] == "before_head":
            return copy.deepcopy(previous["first_writer_proof"])
        return {"claims": copy.deepcopy(previous["first_reservation"]["claims"]), "signature_hex": "ab" * 64}

    def activation(self, auth):
        saved = {"payload_sha256": self.installation["genesis"]["payload_sha256"]}
        expected = witness.expected(auth["writer"], saved, self.installation["root"], self.peer("manager"), self.predecessor)
        return {"writer": auth["writer"], "peer": self.peer("manager"),
                "activation": observed(expected["observation_id"], record.DIRECTORY, expected["payload"],
                                       50 if self.phase == "fresh" else 51)}

    def initial_cut(self):
        if self.mode == "before_writer":
            self.add("genesis_cut", {"phase": "before_writer", "cut": self.installation,
                                     "wait_until_boottime_ns": 121_000_000_000})
            return
        auth = self.authority(None)
        writer = auth["writer"]
        state = self.installation
        state["registry"]["observed_unix_ms"] = writer["authority_lease"]["issued_at_unix_ms"] + 1
        state["registry"]["store_revision"] = 3
        state["registry"]["leases"].append(writer["authority_lease"])
        state["registry"]["leases"].sort(key=lambda item: item["lease_id"])
        physical = {"authority_epoch": 1, "store_revision": 3,
                    "leases": {item["lease_id"]: copy.deepcopy(item) for item in state["registry"]["leases"]},
                    "revocations": {}, "retired_revisions": {}}
        state["registry_frontier"] = authority.lease_frontier(physical)
        state["fleet_lifecycle"].update(generation=1, lifecycle="starting")
        candidate = self.activation(auth)
        common = {"phase": self.mode, "observed_boottime_ns": state["observed_boottime_ns"] + 1,
                  "wait_until_boottime_ns": 121_000_000_000}
        if self.mode == "before_head":
            state["issuer"].update(sequence=1, writer_authorization=auth["proof"])
            self.add("genesis_cut", {**common, "cut": state, "candidate": candidate, "writer_proof": auth["proof"]})
        else:
            reserve = {"schema_version": 1, "purpose": {"kind": "initial"}, "previous_sequence": 0,
                       "expected_state_sha256": types.sha(state["issuer"]), "verifying_key": [19] * 32,
                       "admitted_at_unix_ms": state["registry"]["observed_unix_ms"],
                       "signing_bytes_sha256": hashlib.sha256(witness.SIGNING_DOMAIN + e.canonical(auth["proof"]["claims"]).encode()).hexdigest(),
                       "claims": auth["proof"]["claims"]}
            actual = {**copy.deepcopy(state["issuer"]), "sequence": 1, "writer_reservation": reserve}
            self.add("genesis_cut", {**common, "before": {"before_admission": state, "candidate": candidate},
                                     "reserved_issuer": actual})

    def retire_old(self, stopped):
        physical = copy.deepcopy(stopped["root_authority"]["registry"])
        now = self.installation["registry"]["observed_unix_ms"]
        before = {"principal_id": fixed.AGENT, "store_revision": physical["store_revision"],
                  "observed_unix_ms": now, "leases": [copy.deepcopy(value) for _, value in sorted(physical["leases"].items())
                    if value["expires_at_unix_ms"] > now]}
        revocations = []
        for issued in before["leases"]:
            reason = types.sha(["native.original.unpublished-retirement.v1", self.installation["root"],
                self.installation["genesis"]["payload_sha256"],
                [self.previous["first_candidate"]["writer"], self.predecessor], issued])
            receipt = {"lease_id": issued["lease_id"], "authority_epoch": 1, "previous_lease_revision": 1,
                       "lease_revision": 2, "store_revision": physical["store_revision"] + 1,
                       "reason_sha256": list(bytes.fromhex(reason)), "revoked_at_unix_ms": now}
            revocations.append(receipt)
            physical["leases"][issued["lease_id"]]["revision"] = 2
            physical["revocations"][issued["lease_id"]] = {"schema_version": 1, **{key: value for key, value in receipt.items()
                if key != "previous_lease_revision"}}
            physical["store_revision"] += 1
        after = {"principal_id": fixed.AGENT, "store_revision": physical["store_revision"], "observed_unix_ms": now, "leases": []}
        self.installation["registry"] = copy.deepcopy(after)
        self.installation["registry_frontier"] = authority.lease_frontier(physical)
        return {"registry_before": before, "revocations_applied": revocations, "registry_after": after}

    def authority(self, _):
        state = self.installation
        binding = e.json_value(state["intent"]["payload_json"])["bootstrap"]["lease_binding"]
        now = state["registry"]["observed_unix_ms"] + 1
        suffix = self.linux_boot + "." + str(self.spawn)
        root = {"schema_version": 1, "lease_id": "native-cpu.root." + suffix, "authority_epoch": 1,
                "revision": 1, "binding": binding, "issued_at_unix_ms": now, "expires_at_unix_ms": now + 120000}
        lease = {"schema_version": 1, "lease_id": "native-cpu.writer." + suffix, "authority_epoch": 1,
                 "revision": 1, "binding": {"principal_id": fixed.AGENT, "operation_class": "runtime.agentd.production_writer",
                     "destination_id": "cognitive.owner:" + fixed.AGENT, "scope_sha256": list(bytes.fromhex(types.sha([
                         fixed.AGENT, fixed.BASE + "/fleet/agents/" + fixed.AGENT + "/cognitive"]))),
                     "payload_sha256": [0] * 32},
                 "issued_at_unix_ms": now + 1, "expires_at_unix_ms": now + 1 + 20000}
        writer = {"registered_agent_id": fixed.AGENT, "spawn_generation": self.spawn, "owner_epoch": self.owner_epoch,
                  "local_lease_id": "native-cpu-original-writer", "local_lease_generation": 1, "authority_lease": lease}
        lease["binding"]["payload_sha256"] = list(bytes.fromhex(witness.commitment(writer,
            state["genesis"]["payload_sha256"], state["root"], self.peer("manager"), self.predecessor)))
        claims = {"schema_version": 1, "issuer_id": fixed.SIGNER, "sequence": self.proof_sequence,
                  **writer, "authority_lease_sha256": types.sha(lease)}
        proof = {"claims": claims, "signature_hex": "ab" * 64}
        digest = types.sha(proof)
        fence = hashlib.sha256(hashlib.sha256(b"hepta:production-authority-token-grant:v2\0"
            + digest.encode() + proof["signature_hex"].encode()).digest()).hexdigest()
        return {"root": root, "writer": writer, "proof": proof,
                "binding": {"lease_id": "native-cpu-original-writer", "generation": 1, "authority_epoch": 1,
                    "owner_epoch": self.owner_epoch, "authority_grant_digest": digest, "fencing_token_digest": fence,
                    "expires_at_unix_seconds": lease["expires_at_unix_ms"] // 1000}}

    def raw(self):
        return InertRecords.raw(self)

    def evaluate(self):
        observed = {"raw_exit_code": -9 if self.phase == "fresh" else 33, "timed_out": False, "serial_excessive": False}
        return oracle.evaluate(self.raw(), observed, NONCE, ELF, self.phase, self.previous, self.stopped,
                               scenario=self.scenario)


def pair(scenario=t.SCENARIO):
    first = GenesisRecords(scenario=scenario)
    previous = first.evaluate()
    # Parser-only seam, not physical evidence. The actual runner supplies its
    # independently inspected original ext2/SQLite/WAL result, never this value.
    state = previous["observed_installation"]
    registry = {"authority_epoch": 1, "store_revision": state["registry"]["store_revision"],
                "leases": {item["lease_id"]: copy.deepcopy(item) for item in state["registry"]["leases"]},
                "revocations": {}, "retired_revisions": {}}
    stopped = {"original_no_head_initial_material_physically_verified": True,
               "root_authority": {"registry": registry}}
    second = GenesisRecords(previous, stopped, scenario)
    return first, second
