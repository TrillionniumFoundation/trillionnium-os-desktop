"""Read the two original prior-boot transcripts without rewriting any event.

Transcript success is deliberately not native qualification. The separate
runner must bind the actual SIGKILL, exact inherited disk inode, two stopped
physical SQLite/WAL inspections, original builds and source snapshots.
"""
import hashlib

import native_owner_evidence as e
import native_owner_prior_boot_types as t
import native_owner_activation_witness as witness
import native_owner_prior_boot_store as store


class PriorBootTranscript:
    def __init__(self, phase, nonce, previous=None, stopped=None):
        e.require(phase in ("fresh", "retained"), "actual fresh/retained prior-boot phase required")
        e.digest(nonce, "fresh campaign nonce")
        e.require((previous is None and stopped is None) if phase == "fresh" else
                  (type(previous) is dict and type(stopped) is dict
                   and previous.get("prior_boot_transcript_verified") is True
                   and stopped.get("old_unknown_physically_verified") is True),
                  "retained boot needs the actual first transcript and stopped original SQLite/WAL evidence")
        self.phase, self.nonce, self.previous, self.stopped = phase, nonce, previous, stopped
        self.start = None
        self.adoption = None

    def begin(self, take):
        self.start = e.obj(take("boot_phase"), ("phase", "kernel_boot", "installation"), "actual mounted boot phase")
        e.require(self.start["phase"] == self.phase, "actual mounted installation did not select the required boot phase")
        e.byte_id(self.start["kernel_boot"], "actual prior-boot kernel")
        t.pin(self.start["installation"])
        if self.phase == "retained":
            self.adoption = e.obj(take("prior_boot_adopted"), ("cold_open", "successor", "observation_id",
                "observation_path", "durable_payload_json", "durable_payload_sha256"), "original prior-boot physical adoption")

    def finish(self, shared):
        s = self.s = shared
        e.require(self.start["kernel_boot"] == s.boot_id and t.uuid(s.boot_id) == s.linux_boot,
                  "original proc boot and native role bootstrap identify different actual boots")
        pin = self.start["installation"]
        owner = s.owners["manager"]
        e.require(pin["device"] == s.state["mount_device"] and owner["issuer_key_sha256"]
                  == hashlib.sha256(bytes(pin["expected_verifying_key"])).hexdigest(),
                  "actual original Host issuer key is not the independently retained installation pin")
        result = self.fresh() if self.phase == "fresh" else self.retained()
        result.update(phase=self.phase, nonce=self.nonce, passed=False, prior_boot_transcript_verified=True,
                      native_boot_id=s.boot_id, linux_boot_id=s.linux_boot, spaces=s.spaces, peers=s.peers,
                      actual_state=s.state, original_owner=owner, installation=pin,
                      kill_within_guest_callback_window_proven=False,
                      cross_boot_unknown_preservation_verified=False, power_loss_verified=False,
                      original_native_owner_cycle_verified=False, g2_complete=False, production_ready=False)
        result["activation_witnesses_expected"] = [] if self.phase == "fresh" else [witness.expectation(
            result["complete_event"]["authority"]["writer"], self.previous["cut_current"], s.peers["root"],
            s.peers["manager"], self.previous["cut_material_sha256"])]
        result["activation_witness_files_verified"] = False
        return result

    def prepared(self, name):
        op = self.s.prepared(name, "manager", 25_000_000)
        e.require(op["request"]["delivery"]["sequence"] == "0000000000000001"
                  and op["key"] == "native-cpu:" + hashlib.sha256(
                      e.canonical(op["request"]["delivery"]).encode()).hexdigest() + ":" + name,
                  "actual original K/D differs from the reviewed new-namespace producer")
        return op

    def saved_record(self, event):
        cut = t.saved_cut(event["durable_payload_json"], self.nonce)
        old_linux_boot = t.uuid(cut["kernel_boot"])
        observation_id = "native-boot-cut." + old_linux_boot + "." + self.nonce
        e.require(event["observation_id"] == observation_id
                  and event["observation_path"] == t.OBSERVATIONS + "/" + t.cut_filename(observation_id)
                  and e.digest(event["durable_payload_sha256"], "actual original saved cut bytes")
                      == hashlib.sha256(event["durable_payload_json"].encode()).hexdigest(),
                  "original saved observation changed its exact old boot, path, payload bytes or nonce")
        return cut

    def fresh(self):
        s = self.s
        op = self.prepared("prior-boot-unresolved")
        value = e.obj(s.take("prior_boot_cut"), ("current", "material_path", "authority_before_dispatch", "observation_id",
            "observation_path", "durable_payload_json", "durable_payload_sha256", "emitted_boottime_ns"),
            "actual original durable VM cut")
        cut = self.saved_record(value)
        ready = s.currents["manager"]
        current = e.checkpoint(value["current"], s.peers["manager"], s.owners["manager"]["agent_id"])
        e.require(cut["kernel_boot"] == s.boot_id and cut["installation"] == self.start["installation"]
                  and cut["current_token"] == current["token"] and cut["occurrence_key"] == op["key"]
                  and cut["payload_json"] == op["request_json"]
                  and cut["boundary"]["pid"] == s.role_pids["manager"],
                  "original durable cut does not bind the actual faulting process, Current or immutable K/D")
        for key in ("writer_binding", "publisher_epoch"):
            e.require(current["head"][key] == ready["head"][key], "fault cut replaced the original writer authority")
        e.require(current["head"]["counter"] > ready["head"]["counter"]
                  and current["head"]["last_current"]["schema_digest"] == ready["head"]["last_current"]["schema_digest"]
                  and current["head"]["last_current"]["state_digest"] != ready["head"]["last_current"]["state_digest"],
                  "prepare/effect entry did not advance the actual durable Current")
        prior_frontiers = s.frontiers["manager"]
        e.require(cut["frontiers"][0] != prior_frontiers["device_frontier"]
                  and cut["frontiers"][1] == prior_frontiers["notes_frontier"],
                  "actual old Device claim or untouched Notes frontier was lost")
        for item, lane in zip(cut["frontiers"], e.FRONTIER_LANES):
            e.require(all(item[key] == prior_frontiers[lane][key] for key in ("authority_epoch", "revocation_revision")),
                      "fault scenario changed the original FinalUse revocation head")
        authority = t.authority(value["authority_before_dispatch"], ready, s.owners["manager"], s.linux_boot)
        e.require(cut["authority_before_sha256"] == hashlib.sha256(e.canonical(authority).encode()).hexdigest()
                  and cut["issuer_sequence_at_cut"] > authority["issuer_sequence"],
                  "actual original cut issuer highwater or pre-dispatch authority bytes differ")
        t.transport(cut["source_database"], s.role_pids["manager"], s.state["store_device"], installs=0, queries=0)
        emitted = e.integer(value["emitted_boottime_ns"], "actual guest durable-cut emit time", 1)
        e.require(cut["boundary"]["observed_boottime_ns"] <= emitted < cut["boundary"]["pending_until_boottime_ns"],
                  "Root emitted its cut after the unchanged original bounded callback expired")
        t.file_path(value["material_path"], t.AUTHORITY + "/material", "actual original retained material")
        return {"cut": cut, "cut_event": value, "old_operation": op, "cut_current": current,
                "cut_material_path": value["material_path"], "cut_material_sha256": cut["material_sha256"],
                "source_database": cut["source_database"], "source_terminal_observed": False}

    def cold_open(self):
        s, prior, value = self.s, self.previous, self.adoption
        cut = self.saved_record(value)
        e.require(self.start["kernel_boot"] != prior["native_boot_id"]
                  and self.start["installation"] == prior["installation"]
                  and all(value[key] == prior["cut_event"][key] for key in
                          ("observation_id", "observation_path", "durable_payload_json", "durable_payload_sha256")),
                  "retained boot reconstructed the old saved observation or reset the original installation")
        e.require(s.spaces["manager"] not in prior["spaces"].values()
                  and s.spaces["recovery"] not in prior["spaces"].values(),
                  "new actual boot reused an old management/history namespace")
        cold = e.obj(value["cold_open"], t.COLD_KEYS, "actual original open-only cold observation")
        e.require(cold["previous"] == prior["cut_current"]
                  and cold["previous_writer"] == prior["cut_event"]["authority_before_dispatch"]["writer"]
                  and cold["writer_proof_sha256"] == prior["original_owner"]["writer_proof_sha256"]
                  and type(cold["issuer_sequence"]) is int and cold["issuer_sequence"] == cut["issuer_sequence_at_cut"]
                  and cold["revocations"] == prior["cut_event"]["authority_before_dispatch"]["revocations"],
                  "cold factory did not observe the complete original key/proof/highwater/Current lineage")
        t.revocations(cold["revocations"])
        for lane, saved in zip(e.FRONTIER_LANES, cut["frontiers"]):
            e.require(e.frontier(cold[lane], "cold original " + lane) == saved
                      and s.frontiers["manager"][lane] == saved,
                      "actual ownerReady lost a retained Device or Notes FinalUse frontier")
        agent = s.owners["manager"]["agent_id"]
        e.require(agent == prior["original_owner"]["agent_id"]
                  and s.owners["manager"]["issuer_key_sha256"] == prior["original_owner"]["issuer_key_sha256"]
                  and s.owners["manager"]["writer_proof_sha256"] != prior["original_owner"]["writer_proof_sha256"]
                  and s.owners["manager"]["owner_lock_device"] == prior["original_owner"]["owner_lock_device"]
                  and s.owners["manager"]["owner_lock_inode"] == prior["original_owner"]["owner_lock_inode"],
                  "cold owner reset the original Agent, pinned key, writer lock or failed to rotate its proof")
        selected = t.selection(cold["registry_before"], agent)
        after = t.selection(cold["registry_after"], agent)
        revoked = cold["revocations_applied"]
        e.require(type(revoked) is list and len(revoked) == len(selected["leases"]) and after["leases"] == [],
                  "original cold factory did not retire its complete actual live/future lease selection")
        revision = selected["store_revision"]
        sample = selected["observed_unix_ms"]
        for old, receipt in zip(selected["leases"], revoked):
            e.obj(receipt, t.REVOKE_KEYS, "original actual revision-checked revocation receipt")
            e.require(receipt["lease_id"] == old["lease_id"]
                      and receipt["authority_epoch"] == old["authority_epoch"]
                      and receipt["previous_lease_revision"] == old["revision"]
                      and type(receipt["lease_revision"]) is int and receipt["lease_revision"] == old["revision"] + 1
                      and type(receipt["store_revision"]) is int and receipt["store_revision"] == revision + 1,
                      "original cold retirement skipped a selected lease or changed its CAS revision")
            t.original_types.digest_array(receipt["reason_sha256"], "original actual revocation reason")
            at = e.integer(receipt["revoked_at_unix_ms"], "actual original revocation time", sample)
            revision, sample = receipt["store_revision"], at
        e.require(after["store_revision"] == revision and after["observed_unix_ms"] >= sample,
                  "cold empty registry observation does not follow every actual original revocation")
        observed = t.clock(cold["clock"], s.linux_boot)
        old_writer = prior["cut_current"]["head"]["writer_binding"]
        e.require(observed["observed_unix_ms"] >= after["observed_unix_ms"]
                  and observed["observed_unix_ms"] >= old_writer["expires_at_unix_seconds"] * 1000
                  and observed["projection"]["anchor_unix_ms"] >= prior["cut_event"]["authority_before_dispatch"]
                      ["clock"]["projection"]["ceiling_unix_ms"],
                  "original cold factory bypassed retained clock highwater or old local-writer expiry")
        adopted = e.checkpoint(value["successor"], s.peers["manager"], agent)
        old, new = prior["cut_current"]["head"], adopted["head"]
        binding = new["writer_binding"]
        e.require(new["publisher_epoch"] == old["publisher_epoch"] + 1 and new["counter"] == old["counter"] + 1
                  and new["last_current"] == old["last_current"] and new["last_mutation_sequence"] == 0
                  and new["last_request"] is None and binding["lease_id"] == old_writer["lease_id"]
                  and binding["generation"] == old_writer["generation"] + 1
                  and binding["authority_epoch"] == old_writer["authority_epoch"]
                  and binding["owner_epoch"] == old_writer["owner_epoch"] + 1
                  and binding["authority_grant_digest"] != old_writer["authority_grant_digest"]
                  and binding["fencing_token_digest"] != old_writer["fencing_token_digest"],
                  "cold physical adoption did not preserve the original exact cut and canonical next-generation CAS")
        ready = s.currents["manager"]["head"]
        e.require(ready["writer_binding"] == binding and ready["publisher_epoch"] == new["publisher_epoch"]
                  and ready["counter"] >= new["counter"] and ready["last_current"]["schema_digest"] == old["last_current"]["schema_digest"],
                  "actual original ownerReady was not derived from the cold physical adoption")
        return cut, cold

    def observe_old(self, phase, cut, installs, queries, prior_transport=None):
        s = self.s
        value = e.obj(s.take("prior_boot_observed"), ("phase", "transport", "observation"), "actual old-K observation")
        e.require(value["phase"] == phase, "old-K observation crossed its actual new-effect boundary")
        transport = t.transport(value["transport"], s.role_pids["manager"], s.state["store_device"], cut, installs, queries)
        if prior_transport is not None:
            e.require(all(transport[key] == prior_transport[key] for key in t.TRANSPORT_KEYS if key != "ioctl_counts"),
                      "actual original physical writer or pre-monitor snapshot changed within the second boot")
        result = e.obj(value["observation"], ("pid", "occurrence_key", "request_json", "before", "after", "refusal",
            "calls_before", "calls_after", "drain_blockers", "device_frontier", "notes_frontier"),
            "actual original old-boot observer refusal")
        e.integer(result["pid"], "original observer PID", s.role_pids["manager"], s.role_pids["manager"])
        e.require(result["occurrence_key"] == cut["occurrence_key"] and result["request_json"] == cut["payload_json"]
                  and result["refusal"] == "native boot changed; the old D remains unknown"
                  and result["before"] == result["after"], "original old K/D changed or a different error substituted for boot refusal")
        before = e.obj(result["before"], ("operation", "topic", "payload_json", "state"), "original immutable retained operation")
        e.obj(before["operation"], t.OPERATION_KEYS, "original seven-getter OperationIntent observation")
        e.require(before["operation"] == store.operation_observation(self.stopped["live_database"]["operation"])
                  and before["topic"] == t.TOPIC and before["payload_json"] == cut["payload_json"]
                  and before["state"] == "indeterminate", "original retained semantic intent or Unknown state differs from actual stopped SQLite")
        t.counts(result["calls_before"], installs, queries)
        e.require(result["calls_before"] == result["calls_after"] == transport["ioctl_counts"],
                  "old-boot observation issued a native Install/Query or changed transport identity")
        e.integer(result["drain_blockers"], "actual unresolved original drain blocker", 1, 1)
        for lane in e.FRONTIER_LANES:
            e.require(e.frontier(result[lane], "actual original " + lane) == s.frontiers["manager"][lane],
                      "old observation reset or consumed a FinalUse claim")
        return value

    def retained(self):
        s = self.s
        cut, cold = self.cold_open()
        before = self.observe_old("before_new_effect", cut, 0, 0)
        op = self.prepared("new-boot-control")
        e.require(op["key"] != cut["occurrence_key"] and op["request"]["delivery"]["boot_id"] != cut["kernel_boot"],
                  "new effect reused the prior-boot K or D")
        s.native_result("new-boot-control", "applied")
        s.source_terminal("new-boot-control", "manager")
        s.acknowledge("new-boot-control", "manager")
        s.window("new-boot-control", "manager", 25_000_000, op["observation"]["revision"])
        after = self.observe_old("after_new_effect", cut, 1, 1, before["transport"])
        value = e.obj(s.take("prior_boot_complete"), ("current", "material_path", "material_sha256", "authority",
                     "unresolved_occurrence_key", "drain_blockers", "shutdown"), "actual unresolved-work poweroff")
        current = e.checkpoint(value["current"], s.peers["manager"], s.owners["manager"]["agent_id"])
        e.require(current == s.currents["manager"] and value["material_sha256"] == s.materials["manager"]
                  and value["unresolved_occurrence_key"] == cut["occurrence_key"]
                  and type(value["drain_blockers"]) is int and value["drain_blockers"] == 1
                  and value["shutdown"] == "poweroff_with_unresolved_previous_boot",
                  "completion released, resolved or discarded the original previous-boot Unknown")
        t.file_path(value["material_path"], t.AUTHORITY + "/material", "actual final retained material")
        authority = t.authority(value["authority"], current, s.owners["manager"], s.linux_boot)
        e.require(authority["issuer_sequence"] > cut["issuer_sequence_at_cut"]
                  and authority["revocations"] == cold["revocations"]
                  and authority["registry"]["store_revision"] > cold["registry_after"]["store_revision"]
                  and authority["clock"]["observed_unix_ms"] >= cold["clock"]["observed_unix_ms"],
                  "new original writer/effect reset issuer, registry, revocations or the retained clock highwater")
        return {"cut": cut, "adoption_event": self.adoption, "initial_old_observation": before,
                "final_old_observation": after, "new_operation": op, "complete_event": value,
                "source_database": after["transport"], "final_current": current,
                "final_material_path": value["material_path"], "final_material_sha256": value["material_sha256"],
                "new_source_terminal_observed": True, "unresolved_old_drain_blockers": 1,
                "graceful_owner_release_verified": False}


def evaluate(raw, record, nonce, elf_info, phase, previous=None, stopped=None):
    transcript = PriorBootTranscript(phase, nonce, previous, stopped)
    return e._evaluate_boot(raw, record["raw_exit_code"], record["timed_out"], record["serial_excessive"],
                            t.SCENARIO, nonce, elf_info, transcript)


def cut_line_reader(nonce):
    """Minimal fixed-schema pipe callback; no I/O before the actual SIGKILL."""
    e.digest(nonce, "fresh campaign nonce")
    def inspect(line):
        if not line.startswith(e.PREFIX.encode()):
            return None
        e.require(len(line) <= e.MAX_EVENT_BYTES + 2, "actual cut line exceeds original event bound")
        raw = line.removesuffix(b"\n").removesuffix(b"\r").decode("utf-8")
        value = e.obj(e.json_value(raw[len(e.PREFIX):]),
                      ("schema_version", "scenario", "nonce", "event", "sequence", "payload"), "actual cut envelope")
        e.require(type(value["schema_version"]) is int and value["schema_version"] == 1
                  and value["scenario"] == t.SCENARIO and value["nonce"] == nonce,
                  "actual cut envelope changed scenario or nonce")
        if value["event"] != "prior_boot_cut":
            return None
        e.integer(value["sequence"], "actual original cut sequence", 7, 7)
        e.obj(value["payload"], ("current", "material_path", "authority_before_dispatch", "observation_id",
              "observation_path", "durable_payload_json", "durable_payload_sha256", "emitted_boottime_ns"),
              "actual original cut payload")
        cut = t.saved_cut(value["payload"]["durable_payload_json"], nonce)
        e.require(cut["boundary"]["observed_boottime_ns"] <= value["payload"]["emitted_boottime_ns"]
                  < cut["boundary"]["pending_until_boottime_ns"], "guest emitted a late original cut")
        return value
    return inspect
