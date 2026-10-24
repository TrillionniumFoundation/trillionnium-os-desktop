"""Two real transcripts for the separately enabled original no-head campaign.

Transcript checks deliberately never qualify a native run. The runner must
also bind both actual VM exits, one inherited raw descriptor, original builds
and both stopped physical original stores before reporting that finite case.
"""
import hashlib

import native_owner_continuity_types as types
import native_owner_evidence as e
import native_owner_genesis_record as genesis
import native_owner_genesis_types as t
import native_owner_genesis_witness as witness
import native_owner_prior_boot_authority as authority
import native_owner_prior_boot_types as fixed


FIRST_OWNER_KEYS = ("resumed", "first_checkpoint", "root_lease", "writer", "writer_proof", "current",
                    "material_sha256", "fleet_lifecycle", "transport", "activation")
RESUMED_KEYS = ("initial_root", "initial_kernel_boot", "initial_cut", "genesis_sha256", "issuer_id", "verifying_key", "scopes")
OPERATION = "first-control-after-genesis"


def bounded_result(phase, nonce, observed, scenario):
    return {"schema": "hepta.original-no-head-transcript.v1", "scenario": scenario, "phase": phase,
            "nonce": nonce, "passed": False, "genesis_transcript_verified": True,
            "observed_installation": observed["state"], "saved_initial_intent": observed["intent"],
            "saved_genesis": observed["genesis"], "native_boot_id": observed["state"]["kernel_boot"],
            "linux_boot_id": observed["state"]["root"]["boot_id"], "spaces": observed["spaces"],
            "installation": observed["state"]["installation"], "checkpoint_absence_physically_verified": False,
            "same_physical_disk_reboot_verified": False, "original_no_head_recovery_verified": False,
            "writer_reservation_recovery_verified": False, "proof_before_head_recovery_verified": False,
            "kill_within_guest_wait_window_proven": False, "power_loss_verified": False,
            "original_native_owner_cycle_verified": False, "g2_complete": False, "production_ready": False}


def fresh(raw, record, nonce, elf_info, scenario):
    e.require(type(record["raw_exit_code"]) is int and record["raw_exit_code"] == -9
              and record["timed_out"] is False and record["serial_excessive"] is False,
              "first no-head VM must actually exit from the recorded SIGKILL")
    lines, events = e._parse(raw, scenario, nonce, False, genesis=True)
    images = [(index, e.IMAGE.fullmatch(line)) for index, line in enumerate(lines) if e.IMAGE.fullmatch(line)]
    active = [(index, e.ACTIVATION.fullmatch(line)) for index, line in enumerate(lines) if e.ACTIVATION.fullmatch(line)]
    e.require(len(images) == 4 and len(active) == 1
              and all(int(match[1]) == elf_info["bytes"] and int(match[2], 16) == elf_info["entry"] for _, match in images)
              and max(index for index, _ in images) < active[0][0] < events[0][0]
              and tuple(map(int, active[0][1].groups())) == (1, 2, 3, 4)
              and not any(line.startswith("[hepta-g2]") and not e.IMAGE.fullmatch(line)
                          and not e.ACTIVATION.fullmatch(line) for line in lines),
              "first no-head cut lacks the four actual admitted immutable final Processes")
    e.require(len(events) == 1 and events[0][1]["event"] == "genesis_cut",
              "the no-head VM started a writer or emitted a later/missing original owner event")
    value = events[0][1]["payload"]
    mode = dict(zip(t.SCENARIOS, ("before_writer", "writer_reserved", "before_head")))[scenario]
    fields = {"before_writer": ("phase", "cut", "wait_until_boottime_ns"),
              "writer_reserved": ("phase", "before", "reserved_issuer", "observed_boottime_ns", "wait_until_boottime_ns"),
              "before_head": ("phase", "cut", "candidate", "writer_proof", "observed_boottime_ns", "wait_until_boottime_ns")}[mode]
    e.obj(value, fields, "actual original unpublished installation cut")
    e.require(value["phase"] == mode, "another original interruption was substituted for the requested cut")
    before = None
    if mode == "writer_reserved":
        before = e.obj(value["before"], ("before_admission", "candidate"), "explicit original pre-admission observation")
    observed = t.state(value["cut"] if before is None else before["before_admission"], mode=mode)
    cut_state = observed["state"]
    sampled = cut_state["observed_boottime_ns"] if mode == "before_writer" else e.integer(
        value["observed_boottime_ns"], "actual original reserve/signature cut time", cut_state["observed_boottime_ns"])
    until = e.integer(value["wait_until_boottime_ns"], "actual unchanged original wait deadline", sampled + 1)
    e.require(until - sampled <= 120_000_000_000, "no-head wait exceeded the original finite Root budget")
    actual_issuer = cut_state["issuer"]
    candidate, first_proof, reservation, activation = None, None, None, None
    if mode != "before_writer":
        candidate = (before if before is not None else value)["candidate"]
        e.obj(candidate, ("writer", "peer", "activation"), "actual unpublished first-candidate observation")
        writer = candidate["writer"]
        activation = witness.observed(candidate, observed["genesis"], cut_state["root"], candidate["peer"], writer,
                                      cut_state["installation"]["device"])
        e.require(writer["spawn_generation"] == writer["owner_epoch"] == 1
                  and writer["authority_lease"] in cut_state["registry"]["leases"],
                  "original first-candidate admission is not the actual first Supervisor and published finite lease")
        if mode == "writer_reserved":
            actual_issuer = value["reserved_issuer"]
            reservation = witness.pending(actual_issuer, cut_state["issuer"], writer,
                                           cut_state["installation"]["expected_verifying_key"])
        else:
            first_proof = witness.proof(value["writer_proof"])
            e.require(first_proof == actual_issuer["writer_authorization"] and first_proof["claims"]["sequence"] == 1
                      and {key: first_proof["claims"][key] for key in types.REGISTRATION_KEYS} == writer,
                      "before-head cut did not retain its exact actual canonical signed first candidate")
    result = bounded_result("fresh", nonce, observed, scenario)
    result.update(cut_event=value, cut_mode=mode, actual_cut_issuer=actual_issuer,
                  first_candidate=candidate, first_writer_proof=first_proof, first_reservation=reservation,
                  genesis_activations_expected=[] if activation is None else [activation],
                  raw_serial_sha256=hashlib.sha256(raw).hexdigest(), raw_serial_bytes=len(raw),
                  event_count=1, source_terminal_observed=False, original_checkpoint_observed=False,
                  original_host_writer_observed=False, canonical_writer_proof_observed=first_proof is not None)
    return result


class GenesisTranscript:
    def __init__(self, nonce, previous, stopped, scenario):
        e.digest(nonce, "fresh same-disk campaign nonce")
        e.require(type(previous) is dict and previous.get("genesis_transcript_verified") is True
                  and previous.get("phase") == "fresh" and previous.get("nonce") == nonce and previous.get("scenario") == scenario
                  and type(stopped) is dict and stopped.get("original_no_head_initial_material_physically_verified") is True,
                  "second boot requires the complete actual first cut and independent stopped no-head store")
        self.nonce, self.previous, self.stopped, self.scenario = nonce, previous, stopped, scenario
        self.mode = dict(zip(t.SCENARIOS, ("before_writer", "writer_reserved", "before_head")))[scenario]
        self.observed = None

    def begin(self, take):
        self.observed = t.state(take("genesis_reopened"), self.previous["observed_installation"], mode=self.mode)

    def finish(self, s):
        observed = self.observed["state"]
        e.require(s.boot_id == observed["kernel_boot"] and s.linux_boot == observed["root"]["boot_id"]
                  and s.peers["root"] == observed["root"] and s.spaces == self.observed["spaces"]
                  and s.role_pids == {"root": 1, "manager": 2, "workload": 3, "recovery": 4}
                  and s.state["mount_device"] == observed["installation"]["device"],
                  "original first owner is detached from the actual cold-open Root/boot/storage")
        owner = s.owners["manager"]
        e.require(owner["agent_id"] == fixed.AGENT and owner["spawn_generation"] > 0
                  and owner["issuer_key_sha256"] == hashlib.sha256(bytes(observed["installation"]["expected_verifying_key"])).hexdigest(),
                  "cold first owner changed the original Agent, first Supervisor generation or pinned issuer")
        initial = authority.final_use_frontier(observed["issuer"]["head"], [])
        e.require(s.frontiers["manager"] == {lane: initial for lane in e.FRONTIER_LANES},
                  "first original Host reset initial authority or consumed an unreported FinalUse claim")
        value = e.obj(s.take("genesis_first_owner"), FIRST_OWNER_KEYS, "actual original first checkpoint/owner")
        saved = self.observed["genesis"]
        payload = saved["payload"]
        import native_owner_genesis_recovery as recovery
        resumed, predecessor = recovery.resumed(value["resumed"], self.mode, self.previous, self.stopped, self.observed)
        current = e.checkpoint(value["current"], s.peers["manager"], fixed.AGENT)
        first = e.checkpoint(value["first_checkpoint"], s.peers["manager"], fixed.AGENT)
        e.require(current == s.currents["manager"] and value["material_sha256"] == s.materials["manager"]
                  and first["head"]["counter"] == first["head"]["publisher_epoch"] == 1
                  and first["head"]["last_mutation_sequence"] == 0 and first["head"]["last_request"] is None
                  and first["head"]["last_current"] == payload["initial_cut"]
                  and first["head"]["writer_binding"] == current["head"]["writer_binding"]
                  and current["head"]["publisher_epoch"] == 1 and current["head"]["counter"] >= 1
                  and current["head"]["last_current"]["schema_digest"] == payload["initial_cut"]["schema_digest"],
                  "actual first head is not original counter/epoch/local generation one over the retained material")
        auth = types.authority(value["root_lease"], value["writer"], value["writer_proof"], current, fixed.AGENT)
        writer, root = auth["writer"], auth["root"]
        suffix = s.linux_boot + "." + str(owner["spawn_generation"])
        epoch = 1 if predecessor is None else predecessor["claims"]["owner_epoch"] + 1
        sequence = 1 if predecessor is None else predecessor["claims"]["sequence"] + 1
        e.require(writer["spawn_generation"] == owner["spawn_generation"] and writer["owner_epoch"] == epoch
                  and writer["local_lease_generation"] == 1
                  and writer["local_lease_id"] == "native-cpu-original-writer"
                  and root["lease_id"] == "native-cpu.root." + suffix
                  and writer["authority_lease"]["lease_id"] == "native-cpu.writer." + suffix
                  and root["binding"] == self.observed["intent"]["bootstrap"]["lease_binding"]
                  and root["issued_at_unix_ms"] >= observed["registry"]["observed_unix_ms"]
                  and auth["proof"]["claims"]["issuer_id"] == fixed.SIGNER
                  and auth["proof"]["claims"]["sequence"] == sequence
                  and auth["proof_sha256"] == owner["writer_proof_sha256"],
                  "actual first proof reset or invented its original canonical sequence, finite leases or Supervisor identity")
        if predecessor is None:
            e.require(writer["spawn_generation"] == 1, "unused original Fleet did not start its actual first generation")
        else:
            e.require(writer["spawn_generation"] == predecessor["claims"]["spawn_generation"] + 2 == 3,
                      "replacement reused the actually retired original Supervisor generation")
        activation = witness.observed(value["activation"], saved, s.peers["root"], s.peers["manager"], writer,
                                      observed["installation"]["device"], predecessor)
        t.lifecycle(value["fleet_lifecycle"], writer["spawn_generation"] + 1, "running")
        transport = fixed.transport(value["transport"], s.role_pids["manager"], s.state["store_device"], installs=0, queries=0)
        e.require(transport["database_inode"] == s.state["store_inode"]
                  and transport["database_path"] != t.INITIAL_DATABASE
                  and transport["database_inode"] != observed["source_database"]["inode"],
                  "actual original recovery factory failed to select its independent new working database")
        op = s.prepared(OPERATION, "manager", 25_000_000)
        e.require(op["request"]["delivery"]["sequence"] == "0000000000000001"
                  and op["key"] == "native-cpu:" + hashlib.sha256(e.canonical(op["request"]["delivery"]).encode()).hexdigest() + ":" + OPERATION,
                  "new first original effect changed its exact K/D occurrence identity")
        s.native_result(OPERATION, "applied")
        s.source_terminal(OPERATION, "manager")
        s.acknowledge(OPERATION, "manager")
        s.window(OPERATION, "manager", 25_000_000, op["observation"]["revision"])
        terminal_current, terminal_material = s.currents["manager"], s.materials["manager"]
        release = e.obj(s.take("owner_released"), ("pid", "peer_lifetime", "receipt", "current", "material_sha256",
                                                  "device_frontier", "notes_frontier"), "actual original first writer release")
        e.require(type(release["pid"]) is int and release["pid"] == 2 and release["peer_lifetime"] == s.peers["manager"],
                  "original release belongs to another Process")
        released = e.checkpoint(release["current"], s.peers["manager"], fixed.AGENT)
        new, old = released["head"], terminal_current["head"]
        e.require(new["writer_binding"] == old["writer_binding"] and new["publisher_epoch"] == old["publisher_epoch"]
                  and new["counter"] > old["counter"] and new["last_current"]["schema_digest"] == old["last_current"]["schema_digest"]
                  and new["last_current"]["state_digest"] != old["last_current"]["state_digest"],
                  "original successful release lacks its independently acknowledged new Current transaction")
        types.released(release["receipt"], released, fixed.AGENT)
        e.digest(release["material_sha256"], "actual original released physical material")
        e.require({lane: e.frontier(release[lane], "released " + lane) for lane in e.FRONTIER_LANES}
                  == s.frontiers["manager"], "original release changed an exact FinalUse claim")
        stopped = e.obj(s.take("owner_stopped"), ("pid", "peer_lifetime", "release_generation", "supervisor"),
                        "actual first original Supervisor stop/reap")
        e.require(type(stopped["pid"]) is int and stopped["pid"] == 2 and stopped["peer_lifetime"] == s.peers["manager"]
                  and type(stopped["release_generation"]) is int and stopped["release_generation"] == 1,
                  "actual first writer did not stop/reap its released original generation")
        # The prefix is copied from the actual final snapshot. The original
        # checker verifies all eight transactions; no activation is generated.
        snapshot = e.obj(stopped["supervisor"], types.SNAPSHOT_KEYS, "actual stopped original Supervisor")
        e.require(type(snapshot["events"]) is list and len(snapshot["events"]) == 8,
                  "complete original Starting/Running/Draining/Stopped events required")
        types.supervisor(snapshot, writer["spawn_generation"], 2, False, prior={"events": snapshot["events"][:4]})
        complete = e.obj(s.take("complete"), ("root_pid", "operation_count", "final_owner_pid", "final_current_token"),
                         "original finite no-head recovery completion")
        e.require(all(type(complete[key]) is int for key in ("root_pid", "operation_count", "final_owner_pid"))
                  and (complete["root_pid"], complete["operation_count"], complete["final_owner_pid"]) == (1, 1, 2)
                  and complete["final_current_token"] == terminal_current["token"] and op.get("retired") is True,
                  "completion replaced the original source-terminal acknowledgement or omitted retirement")
        result = bounded_result("retained", self.nonce, self.observed, self.scenario)
        result.update(first_owner_event=value, cut_mode=self.mode, actual_state=s.state, original_owner=owner, peers=s.peers,
                      retired_first_proof=predecessor, genesis_activations_expected=[*self.previous["genesis_activations_expected"], activation],
                      original_authority=auth, first_checkpoint=first, first_operation=op,
                      source_terminal_current=terminal_current, source_terminal_material_sha256=terminal_material,
                      release_event=release, stopped_event=stopped, complete_event=complete,
                      source_database=transport, final_current=released,
                      final_material_path=authority_path(released["head"]["last_current"]),
                      final_material_sha256=release["material_sha256"], final_frontiers=s.frontiers["manager"],
                      source_terminal_before_retirement_verified=True, bounded_cpu_window_observed=True,
                      graceful_release_and_reap_observed=True, activation_witnesses_expected=[])
        return result


def authority_path(cut):
    return fixed.AUTHORITY + "/material/" + types.sha(e.ordered(cut, e.CUT_KEYS, "actual exact material cut")) \
        + "/agents/" + fixed.AGENT + "/cognitive/cognitive_1.sqlite3"


def evaluate(raw, record, nonce, elf_info, phase, previous=None, stopped=None, *, scenario=t.SCENARIO):
    e.require(scenario in t.SCENARIOS, "fixed original no-head scenario required")
    e.require(phase in ("fresh", "retained"), "actual no-head boot phase required")
    if phase == "fresh":
        e.require(previous is None and stopped is None, "first no-head VM cannot borrow prior evidence")
        return fresh(raw, record, nonce, elf_info, scenario)
    return e._evaluate_boot(raw, record["raw_exit_code"], record["timed_out"], record["serial_excessive"],
                            scenario, nonce, elf_info, None, genesis=GenesisTranscript(nonce, previous, stopped, scenario))


def cut_line_reader(nonce, scenario=t.SCENARIO):
    e.require(scenario in t.SCENARIOS, "fixed original no-head scenario required")
    """The host callback only reads the fixed original event before SIGKILL."""
    e.digest(nonce, "fresh campaign nonce")
    def inspect(line):
        if not line.startswith(e.PREFIX.encode()):
            return None
        e.require(len(line) <= e.MAX_EVENT_BYTES + 2, "actual no-head cut exceeds original event bound")
        raw = line.removesuffix(b"\n").removesuffix(b"\r").decode("utf-8")
        value = e.obj(e.json_value(raw[len(e.PREFIX):]),
                      ("schema_version", "scenario", "nonce", "event", "sequence", "payload"), "actual no-head cut envelope")
        e.require(type(value["schema_version"]) is int and value["schema_version"] == 1
                  and value["scenario"] == scenario and value["nonce"] == nonce
                  and value["event"] == "genesis_cut" and type(value["sequence"]) is int and value["sequence"] == 1,
                  "actual first no-head event is not the single fixed original cut")
        mode = dict(zip(t.SCENARIOS, ("before_writer", "writer_reserved", "before_head")))[scenario]
        fields = {"before_writer": ("phase", "cut", "wait_until_boottime_ns"),
                  "writer_reserved": ("phase", "before", "reserved_issuer", "observed_boottime_ns", "wait_until_boottime_ns"),
                  "before_head": ("phase", "cut", "candidate", "writer_proof", "observed_boottime_ns", "wait_until_boottime_ns")}[mode]
        payload = e.obj(value["payload"], fields, "actual no-head cut payload")
        e.require(payload["phase"] == mode, "another original cut cannot stand in for the requested no-head boundary")
        state = payload["cut"] if mode != "writer_reserved" else e.obj(payload["before"],
            ("before_admission", "candidate"), "actual pre-admission observation")["before_admission"]
        e.obj(state, t.STATE_KEYS, "complete actual original initialization cut")
        now = state["observed_boottime_ns"] if mode == "before_writer" else payload["observed_boottime_ns"]
        e.integer(now, "actual original cut time", 1)
        e.integer(payload["wait_until_boottime_ns"], "actual unchanged wait deadline", now + 1)
        return value
    return inspect
