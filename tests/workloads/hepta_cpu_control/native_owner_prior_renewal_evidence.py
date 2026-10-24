"""Two actual boot transcripts plus the original finite renewal sequence.

Structural success stays unqualified until the separate runner verifies both
VMs, the identical inherited state fd, the stopped SQLite/WAL and original
Root observations. This is not an owner implementation or a replay service.
"""
import hashlib

import native_owner_continuity_scenarios as scenarios
import native_owner_evidence as e
import native_owner_prior_boot_evidence as prior
import native_owner_prior_boot_types as old
from native_owner_prior_renewal_flow import RetainedContinuity, clone, observe


SCENARIO = "prior-boot-unknown-renewal-v1"


class PriorRenewalTranscript(prior.PriorBootTranscript):
    def finish(self, shared, markers):
        if self.phase == "fresh":
            e.require(markers == [], "first fault cut unexpectedly launched a subsequent native owner")
            result = super().finish(shared)
            result.update(scenario=SCENARIO, prior_renewal_transcript_verified=True,
                          bounded_prior_unknown_renewal_transcript_verified=False,
                          root_launch_observations_expected=[], original_new_operations=[], original_releases=[])
            return result
        self.s = s = shared
        initial_owner = clone(s.owners["manager"])
        e.require(self.start["kernel_boot"] == s.boot_id and old.uuid(s.boot_id) == s.linux_boot,
                  "original proc boot and native role bootstrap identify different actual boots")
        pin = self.start["installation"]
        e.require(pin["device"] == s.state["mount_device"] and initial_owner["issuer_key_sha256"]
                  == hashlib.sha256(bytes(pin["expected_verifying_key"])).hexdigest(),
                  "cold original Host issuer key is not the retained installation pin")
        cut, cold = self.cold_open()
        first = self.observe_old("before_new_effect", cut, 0, 0)
        flow = RetainedContinuity(s, markers, cut, self.previous, self.stopped)
        flags = scenarios.renewal(flow)
        final_actor = clone(flow.active)
        final_owner = {"agent_id": flow.agent, "spawn_generation": final_actor["authority"]["writer"]["spawn_generation"],
                       "writer_proof_sha256": final_actor["authority"]["proof_sha256"],
                       "issuer_key_sha256": initial_owner["issuer_key_sha256"]}
        value = e.obj(s.take("prior_boot_observed"), ("phase", "transport", "observation", "authority"),
                      "actual final old-K/Root observation after bounded renewal")
        e.require(value["phase"] == "after_renewal", "old-K observation did not follow the actual renewal endpoint")
        lifetime = tuple(final_actor["peer"][key] for key in ("pid", "boot_id", "process_start_ticks"))
        observe(value["observation"], value["transport"], final_actor["pid"], s.state["store_device"], cut,
                self.stopped["live_database"], s.frontiers["manager"], 1, flow.transports[lifetime])
        terminal_current = clone(s.currents["manager"])
        authority = old.authority(value["authority"], terminal_current, final_owner, s.linux_boot)
        e.require(authority["writer"] == final_actor["authority"]["writer"]
                  and authority["issuer_sequence"] == final_actor["authority"]["proof"]["claims"]["sequence"] + 1
                  and authority["revocations"] == cold["revocations"]
                  and authority["registry"]["store_revision"] > cold["registry_after"]["store_revision"]
                  and authority["clock"]["observed_unix_ms"] >= cold["clock"]["observed_unix_ms"],
                  "bounded renewal changed original authority identity or lost its actual final canonical highwater")
        released = flow.release()
        e.require(released["retained_prior_boot"]["observation"] == value["observation"]
                  and released["retained_prior_boot"]["transport"] == value["transport"],
                  "old-K/descriptor state changed between the final observation and actual Stop")
        complete = e.obj(s.take("complete"), ("root_pid", "operation_count", "final_owner_pid", "final_current_token"),
                         "actual bounded Unknown-preserving owner cycle completion")
        e.require(type(complete["root_pid"]) is int and complete["root_pid"] == 1
                  and type(complete["operation_count"]) is int
                  and complete["operation_count"] == len(s.operations) == len(flow.operations) == flags["manager_cycles"]
                  and type(complete["final_owner_pid"]) is int and complete["final_owner_pid"] == final_actor["pid"]
                  and complete["final_current_token"] == terminal_current["token"]
                  and all(operation.get("retired") is True for operation in s.operations.values())
                  and len(flow.releases) == 2 * len(flow.operations) - 1,
                  "actual continued effects, original ACKs or successful owner releases are incomplete")
        observations = flow.launches.finish()
        e.require(len(observations) >= 2, "actual old Unknown never survived two new kernel pairs")
        return {**flags, "scenario": SCENARIO, "phase": self.phase, "nonce": self.nonce, "passed": False,
                "prior_boot_transcript_verified": True, "prior_renewal_transcript_verified": True,
                "bounded_prior_unknown_renewal_transcript_verified": True,
                "native_boot_id": s.boot_id, "linux_boot_id": s.linux_boot, "spaces": clone(s.spaces),
                "peers": clone(s.peers), "actual_state": s.state, "original_owner": initial_owner,
                "final_original_owner": final_owner, "final_owner_authority": final_actor["authority"],
                "installation": pin, "cut": cut, "adoption_event": self.adoption,
                "initial_old_observation": first, "final_old_observation": value,
                "retained_old_observations": flow.retained_observations,
                "source_database": value["transport"], "final_current": released["current"],
                "final_material_sha256": released["material_sha256"],
                "terminal_current": terminal_current, "complete_event": complete,
                "final_authority": authority, "original_new_operations": flow.operations,
                "original_releases": flow.releases, "actual_owner_processes": flow.owner_processes,
                "actual_policy_retirements": flow.retirements, "initial_role_pids": flow.initial_pids,
                "activation_witnesses_expected": flow.activation_witnesses,
                "activation_witness_files_verified": False,
                "root_launch_observations_expected": observations, "root_launch_files_verified": False,
                "unresolved_old_drain_blockers": 1, "cross_boot_unknown_preservation_verified": False,
                "graceful_owner_release_verified": False, "unresolved_pending_handoff_verified": False,
                "kill_within_guest_callback_window_proven": False, "power_loss_verified": False,
                "original_native_owner_cycle_verified": False, "unbounded_persistent_cpu_verified": False,
                "g2_complete": False, "production_ready": False}


def evaluate(raw, record, nonce, elf_info, phase, previous=None, stopped=None):
    transcript = PriorRenewalTranscript(phase, nonce, previous, stopped)
    return e._evaluate_boot(raw, record["raw_exit_code"], record["timed_out"], record["serial_excessive"],
                            SCENARIO, nonce, elf_info, transcript)


def cut_line_reader(nonce):
    e.digest(nonce, "fresh old-boot renewal campaign nonce")

    def inspect(line):
        text = line.decode("utf-8", errors="strict").rstrip("\r\n")
        if not text.startswith(e.PREFIX):
            return None
        value = e.obj(e.json_value(text[len(e.PREFIX):]),
            ("schema_version", "scenario", "nonce", "event", "sequence", "payload"), "actual old-boot renewal event")
        e.require(type(value["schema_version"]) is int and value["schema_version"] == 1
                  and value["scenario"] == SCENARIO and value["nonce"] == nonce,
                  "actual old-boot renewal cut has another envelope or fresh nonce")
        if value["event"] != "prior_boot_cut":
            return None
        e.require(type(value["sequence"]) is int and value["sequence"] == 7
                  and type(value["payload"]) is dict, "actual original prior-boot cut is incomplete or reordered")
        return value

    return inspect
