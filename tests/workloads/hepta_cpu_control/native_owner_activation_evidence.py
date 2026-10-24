"""Original failed-activation observations; no authority or Process is made here.

The two fixed cases retain the default six-case parser unchanged. Each reads
the actual failed canonical writer, original registry/expiry, exact physical
cut, fresh kernel image and successful original successor. Transcript-only
results remain unqualified until independent saved-file inspection succeeds.
"""
import native_owner_evidence as e
import native_owner_continuity as continuity
import native_owner_continuity_types as types
import native_owner_prior_boot_types as registry_types
import native_owner_activation_witness as witness


SCENARIOS = ("activation-after-proof-v1", "activation-after-material-v1")
FAILED_KEYS = ("failed_spawn_generation", "failed_peer", "fault", "registry_failed", "mode", "previous",
               "canonical_writer", "canonical_proof_sha256", "issuer_sequence", "registry_before",
               "revocations_applied", "registry_after", "observed_unix_ms", "local_expiry_unix_ms",
               "device_frontier", "notes_frontier")


def canonical_lease(lease):
    value = e.ordered(lease, types.LEASE_KEYS, "original lease for retirement reason")
    value["binding"] = e.ordered(value["binding"], types.BINDING_KEYS, "original retirement reason binding")
    return value


class ActivationFlow(continuity.Continuity):
    def __init__(self, context, markers, scenario):
        super().__init__(context, markers)
        self.scenario, self.failed = scenario, None
        self.failed_line = None
        self.released_current = None
        self.released_material = None

    def successor_generations(self, previous):
        e.require(self.failed is not None and previous == self.released_current,
                  "partial activation lacks its actual retained released predecessor")
        writer = self.failed["canonical_writer"]
        advance = 0 if self.failed["mode"] == "unactivated" else 1
        return writer["local_lease_generation"] + advance, writer["owner_epoch"] + 1

    def activation_predecessor(self, previous):
        e.require(self.failed is not None and previous == self.released_current,
                  "fresh activation lacks its exact failed original predecessor")
        return self.failed["previous"]

    def failure(self):
        c = self.c
        self.failed_line = c.next_line()
        event = e.obj(c.take("activation_recovery_prepared"), ("failure", "supervisor", "reconciliation"),
                      "actual original activation failure")
        e.text(event["failure"], "original Supervisor start failure", 16384)
        snapshot = e.obj(event["supervisor"], ("active", "healthy", "runtime_generation", "spawn_generation",
                                                "process_system_id"), "actual failed Supervisor state")
        e.require(snapshot["active"] is False and snapshot["healthy"] is False
                  and all(snapshot[key] is None for key in ("runtime_generation", "spawn_generation", "process_system_id")),
                  "actual failed start was reported as an active or healthy original owner")
        value = e.obj(event["reconciliation"], FAILED_KEYS, "actual original failure reconciliation")
        spawn = e.integer(value["failed_spawn_generation"], "actual failed original spawn", 1)
        e.require(spawn == self.last_lifecycle_generation + 1, "failed activation skipped its actual original Starting generation")
        failed_peer = e.obj(value["failed_peer"], e.PEER_KEYS, "actual failed original Recovery lifetime")
        e.require(failed_peer == c.initial_peers["recovery"],
                  "the fixed failure did not retire the actual initial Recovery Process")
        fault = e.obj(value["fault"], ("point", "peer", "spawn_generation", "pidfd_revents", "wait_kind",
                                       "wait_value", "observed_boottime_ns"), "actual held-pidfd activation cut")
        point = "after_proof" if self.scenario == SCENARIOS[0] else "after_material"
        e.require(fault["point"] == point and fault["peer"] == failed_peer
                  and type(fault["spawn_generation"]) is int and fault["spawn_generation"] == spawn
                  and type(fault["pidfd_revents"]) is int and fault["pidfd_revents"] == 1
                  and fault["wait_kind"] == "signaled" and type(fault["wait_value"]) is int and fault["wait_value"] == 9,
                  "an unrelated error or fabricated child exit replaced the fixed original pidfd SIGKILL/WNOWAIT")
        e.integer(fault["observed_boottime_ns"], "actual failed publisher exit time",
                  self.last_usage["sample_boottime_ns"])
        lifecycle = e.obj(value["registry_failed"], ("schema_version", "agent_id", "generation", "lifecycle"),
                          "original Failed lifecycle CAS")
        e.require(type(lifecycle["schema_version"]) is int and lifecycle["schema_version"] == 1
                  and lifecycle["agent_id"] == self.agent and lifecycle["lifecycle"] == "failed"
                  and type(lifecycle["generation"]) is int and lifecycle["generation"] == spawn + 1,
                  "original failed child did not complete the exact Starting-to-Failed transaction")
        self.released_current = c.currents[self.previous["role"]]
        self.released_material = c.materials[self.previous["role"]]
        old = self.released_current["head"]
        old_binding = old["writer_binding"]
        writer = e.obj(value["canonical_writer"], types.REGISTRATION_KEYS, "actual failed canonical registration")
        e.require(writer["registered_agent_id"] == self.agent
                  and type(writer["spawn_generation"]) is int and writer["spawn_generation"] == spawn
                  and writer["local_lease_id"] == old_binding["lease_id"]
                  and type(writer["local_lease_generation"]) is int and writer["local_lease_generation"] == old_binding["generation"] + 1
                  and type(writer["owner_epoch"]) is int and writer["owner_epoch"] == old_binding["owner_epoch"] + 1,
                  "failed canonical proof is not the original exact next local generation and owner epoch")
        issued = types.lease(writer["authority_lease"], self.agent, 20_000,
                             "runtime.agentd.production_writer", "cognitive.owner:" + self.agent)
        prior_auth = self.previous["authority"]
        e.require(issued["lease_id"] == "native-cpu.writer." + failed_peer["boot_id"] + "." + str(spawn)
                  and issued["authority_epoch"] == old_binding["authority_epoch"]
                  and issued["issued_at_unix_ms"] >= prior_auth["writer"]["authority_lease"]["issued_at_unix_ms"]
                  and issued["binding"]["scope_sha256"] == prior_auth["writer"]["authority_lease"]["binding"]["scope_sha256"],
                  "failed original writer lease changed its scope, exact physical cut, finite duration or real spawn")
        self.activation_witnesses.append(witness.expectation(writer, self.released_current, c.peers["root"],
                                                             failed_peer, self.released_material))
        proof_sha = e.digest(value["canonical_proof_sha256"], "actual failed canonical proof bytes")
        e.require(proof_sha != old_binding["authority_grant_digest"], "failed activation did not rotate its original canonical proof")
        e.integer(value["issuer_sequence"], "actual failed canonical highwater", prior_auth["proof"]["claims"]["sequence"] + 1)
        if point == "after_proof":
            e.require(value["mode"] == "unactivated" and value["previous"] == self.released_current,
                      "after-proof failure installed a head or lost the exact unused original local generation")
        else:
            e.require(value["mode"] == "installed", "after-material failure did not retain its actual installed head")
            previous = e.checkpoint(value["previous"], failed_peer, self.agent)
            head, binding = previous["head"], previous["head"]["writer_binding"]
            e.require(head["publisher_epoch"] == old["publisher_epoch"] + 1 and head["counter"] == old["counter"] + 1
                      and head["last_current"] == old["last_current"] and head["last_mutation_sequence"] == 0
                      and head["last_request"] is None and binding["lease_id"] == writer["local_lease_id"]
                      and binding["generation"] == writer["local_lease_generation"]
                      and binding["authority_epoch"] == issued["authority_epoch"] and binding["owner_epoch"] == writer["owner_epoch"]
                      and binding["authority_grant_digest"] == proof_sha
                      and binding["expires_at_unix_seconds"] == issued["expires_at_unix_ms"] // 1000
                      and binding["fencing_token_digest"] != old_binding["fencing_token_digest"],
                      "failed physical installation changed the original cut or is detached from its canonical proof")
        for lane in e.FRONTIER_LANES:
            e.require(e.frontier(value[lane], "actual failed " + lane) == c.frontiers[self.previous["role"]][lane],
                      "partial activation consumed an effect or reset an original FinalUse frontier")
        self.retirement(value, failed_peer)
        self.failed = value
        self.last_lifecycle_generation = lifecycle["generation"]
        self.last_stopped_line = self.failed_line
        self.seen_lifetimes.add((failed_peer["pid"], failed_peer["boot_id"], failed_peer["process_start_ticks"]))
        self.seen_writer_leases.add(issued["lease_id"])
        self.seen_root_leases.add("native-cpu.root." + failed_peer["boot_id"] + "." + str(spawn))
        return event

    def retirement(self, value, failed_peer):
        before = registry_types.selection(value["registry_before"], self.agent)
        after = registry_types.selection(value["registry_after"], self.agent)
        revoked = value["revocations_applied"]
        e.require(type(revoked) is list and len(revoked) == len(before["leases"]) and after["leases"] == [],
                  "failed activation left original current or future registered authority unretired")
        issued = value["canonical_writer"]["authority_lease"]
        if issued["expires_at_unix_ms"] > before["observed_unix_ms"]:
            e.require(issued in before["leases"], "complete actual selection omitted the live failed writer lease")
        revision, sample = before["store_revision"], before["observed_unix_ms"]
        for lease, receipt in zip(before["leases"], revoked):
            e.obj(receipt, registry_types.REVOKE_KEYS, "actual original failed-lease revocation")
            reason = types.sha(["native-root-failed-activation-retirement.v1",
                                e.ordered(failed_peer, e.PEER_KEYS, "actual failed publisher"),
                                e.ordered(value["previous"]["token"], e.TOKEN_KEYS, "actual retained failed cut"),
                                canonical_lease(lease)])
            e.require(receipt["lease_id"] == lease["lease_id"] and receipt["authority_epoch"] == lease["authority_epoch"]
                      and type(receipt["previous_lease_revision"]) is int and receipt["previous_lease_revision"] == lease["revision"]
                      and type(receipt["lease_revision"]) is int and receipt["lease_revision"] == lease["revision"] + 1
                      and type(receipt["store_revision"]) is int and receipt["store_revision"] == revision + 1
                      and bytes(types.digest_array(receipt["reason_sha256"], "actual revocation reason")).hex() == reason,
                      "failed original authority retirement changed its exact CAS, selected lease or cut-bound reason")
            sample = e.integer(receipt["revoked_at_unix_ms"], "actual failed original lease retirement time", sample)
            revision = receipt["store_revision"]
        e.require(after["store_revision"] == revision and after["observed_unix_ms"] >= sample,
                  "empty original authority observation did not follow every actual revocation")
        expiry = e.integer(value["local_expiry_unix_ms"], "actual original old local expiry", 1)
        e.require(expiry == value["previous"]["head"]["writer_binding"]["expires_at_unix_seconds"] * 1000,
                  "failure reconciliation extended or replaced the actual original local expiry")
        e.integer(value["observed_unix_ms"], "actual observed original local retirement", max(expiry, after["observed_unix_ms"]))

    def adopt_partial(self):
        self.adoption_line = self.c.next_line()
        value = e.obj(self.c.take("material_adopted"), ("previous", "successor", "material_sha256"),
                      "actual physical owner reentry")
        e.require(value["previous"] == self.released_current and value["material_sha256"] == self.released_material,
                  "partial activation changed the independently released original physical material")
        peer = e.obj(value["successor"]["head"]["peer_lifetime"], e.PEER_KEYS, "actual fresh adopted publisher")
        adopted = e.checkpoint(value["successor"], peer, self.agent)
        before, after = self.failed["previous"]["head"], adopted["head"]
        e.require(after["publisher_epoch"] == before["publisher_epoch"] + 1
                  and after["counter"] == before["counter"] + 1
                  and after["last_current"] == before["last_current"] == self.released_current["head"]["last_current"]
                  and after["last_mutation_sequence"] == 0 and after["last_request"] is None,
                  "fresh original adoption skipped the actual failed head or reset its retained exact cut")
        self.adoption = adopted

    def final_operation(self):
        name, cap, c = "after-partial-activation", 35_000_000, self.c
        e.require(self.active is not None and self.active["role"] == "manager", "fresh actual original Manager required")
        c.prepared(name, "manager", cap)
        operation = c.operations[name]
        request = operation["request"]
        e.require([request["manage_slot"], request["manage_generation"]] == self.active["bootstrap"]["manage_handle"]
                  and operation["key"] == "native-cpu:" + types.sha(request["delivery"]) + ":" + name,
                  "fresh reentered original K/D escaped its actual final Process handle")
        c.native_result(name, "applied")
        c.source_terminal(name, "manager")
        c.acknowledge(name, "manager")
        c.window(name, "manager", cap, operation["observation"]["revision"])
        self.last_usage, self.last_effect = c.current_usage(), operation


class ActivationTranscript:
    def __init__(self, scenario):
        e.require(scenario in SCENARIOS, "fixed original partial-activation scenario required")
        self.scenario = scenario

    def run(self, scenario, context, markers):
        e.require(scenario == self.scenario and len(markers) == 1 and markers[0]["mode"] == 1,
                  "fixed partial activation requires its one actual fresh kernel pair")
        flow = ActivationFlow(context, markers, scenario)
        flow.owner("manager", initial=True)
        first = flow.operation("before-partial-activation")
        flow.release()
        failed = flow.failure()
        flow.adopt_partial()
        owner = flow.owner("manager")
        e.require(flow.active["kernel_generation"] == 1 and flow.launches.current["mode"] == 1
                  and types.sha(owner["writer_proof"]) != flow.failed["canonical_proof_sha256"]
                  and owner["writer_proof"]["claims"]["sequence"] > flow.failed["issuer_sequence"]
                  and owner["writer"]["authority_lease"]["issued_at_unix_ms"] >= flow.failed["observed_unix_ms"],
                  "fresh original owner reused the failed proof, lease or canonical highwater")
        flow.final_operation()
        observations = flow.launches.finish()
        return {"passed": False, "continuity_transcript_verified": True, "partial_activation_transcript_verified": True,
                "partial_activation_recovery_verified": False, "original_native_owner_cycle_verified": False,
                "same_boot_authenticated_successor_verified": False, "root_launch_files_verified": False,
                "root_launch_observations_expected": observations, "actual_failed_activation": failed,
                "activation_witness_files_verified": False, "activation_witnesses_expected": flow.activation_witnesses,
                "initial_role_pids": flow.initial_pids, "actual_owner_processes": flow.owner_processes,
                "actual_policy_retirements": flow.retirements,
                "initial_local_writer_generation": flow.initial_ready["current"]["head"]["writer_binding"]["generation"],
                "failed_local_writer_generation": flow.failed["canonical_writer"]["local_lease_generation"],
                "reentered_local_writer_generation": owner["writer"]["local_lease_generation"],
                "first_delivery": first["request"]["delivery"], "final_delivery": flow.last_effect["request"]["delivery"],
                "original_finite_lease_durations_preserved": True, "grant_renewal_verified": False,
                "repeated_recovery_verified": False, "cross_boot_unknown_preservation_verified": False,
                "unbounded_persistent_cpu_verified": False, "power_loss_verified": False,
                "g2_complete": False, "production_ready": False}


def evaluate(raw, code, timed_out, excessive, scenario, nonce, elf_info):
    return e._evaluate_boot(raw, code, timed_out, excessive, scenario, nonce, elf_info,
                            None, ActivationTranscript(scenario))
