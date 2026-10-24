"""Consume the two frozen original continuity scenarios without new effects."""
import native_owner_evidence as base
import native_owner_continuity_types as types
from native_owner_successor_wire import initial_expiry_upper_bound, launch_receipt


def renewal(flow):
    c = flow.c
    origin = base.obj(c.take("renewal_origin"), ("initial_usage", "after_boottime_ns", "initial_root_lease", "initial_writer"),
                      "actual initial renewal observation")
    initial = flow.sample(origin["initial_usage"], "manager", 1, base.CAP_NS)
    threshold = initial_expiry_upper_bound(initial["sample_boottime_ns"], include_recovery=True)
    base.require(type(origin["after_boottime_ns"]) is int and origin["after_boottime_ns"] == threshold,
                 "renewal changed the conservative bound beyond both original finite grants")
    flow.owner("manager", initial=True)
    base.require(origin["initial_root_lease"] == flow.active["authority"]["root"]
                 and origin["initial_writer"] == flow.active["authority"]["writer"],
                 "initial CPU sample and original finite writer/session observations differ")
    fresh = set()
    for cycle in range(1, 65):
        generation = flow.active["kernel_generation"]
        if generation:
            fresh.add(generation)
        operation = flow.operation("continued-control")
        if c.peek() == "renewal_endpoint":
            endpoint = base.obj(c.take("renewal_endpoint"), ("initial_sample_boottime_ns", "after_boottime_ns", "actual_terminal_json",
                                "occurrence_key", "delivery", "fresh_kernel_generations", "root_lease", "writer"),
                                "actual original continued-control endpoint")
            base.require(type(endpoint["initial_sample_boottime_ns"]) is int
                         and endpoint["initial_sample_boottime_ns"] == initial["sample_boottime_ns"]
                         and type(endpoint["after_boottime_ns"]) is int and endpoint["after_boottime_ns"] == threshold
                         and endpoint["actual_terminal_json"] == operation["terminal"]
                         and endpoint["occurrence_key"] == operation["key"]
                         and base.delivery(endpoint["delivery"]) == operation["request"]["delivery"]
                         and type(endpoint["fresh_kernel_generations"]) is list
                         and all(type(item) is int for item in endpoint["fresh_kernel_generations"])
                         and endpoint["fresh_kernel_generations"] == sorted(fresh) and len(fresh) >= 2
                         and generation in fresh and operation["observation"]["effective_ns"] > threshold
                         and endpoint["root_lease"] == flow.active["authority"]["root"]
                         and endpoint["writer"] == flow.active["authority"]["writer"],
                         "fresh actual Applied receipt did not cross both initial grants on the same original CPU")
            return {"bounded_renewal_transcript_verified": True, "history_only_transcript_verified": False,
                    "initial_manager_sample_boottime_ns": initial["sample_boottime_ns"],
                    "initial_grants_conservative_expiry_upper_bound_ns": threshold,
                    "endpoint_effective_boottime_ns": operation["observation"]["effective_ns"],
                    "manager_cycles": cycle, "fresh_kernel_generations": sorted(fresh),
                    "original_finite_lease_durations_preserved": True}
        # Preserve every original K in parser state before the producer uses
        # its same operation label in another actual native namespace.
        c.operations[operation["key"]] = c.operations.pop("continued-control")
        flow.release()
        flow.adopt()
        flow.owner("recovery")
        base.require(flow.active["kernel_generation"] == generation,
                     "original finite pair skipped its real Recovery slot")
        flow.release()
        flow.adopt()
        flow.owner("manager")
        base.require(flow.active["kernel_generation"] == generation + 1,
                     "continued Manager did not come from the next actual fresh kernel pair")
    raise ValueError("no actual continued-control effect crossed both initial grants within 64 original Manager cycles")


def initial_busy(flow, stage, previous=None):
    value = base.obj(flow.c.take("launch_refused"), ("stage", "expected_generation", "errno", "launch_receipt"),
                     "actual original launcher refusal")
    base.require(value["stage"] == stage and type(value["expected_generation"]) is int
                 and value["expected_generation"] == 0 and type(value["errno"]) is int and value["errno"] == 16,
                 "live/unreaped original images did not block a real new Advance with EBUSY")
    receipt = launch_receipt(value["launch_receipt"], flow.c.boot_id)
    base.require(receipt["mode"] == 1 and receipt["generation"] == 0
                 and all(receipt["pids"][key] == pid for key, pid in flow.initial_pids.items())
                 and receipt["history_spaces"] == [flow.initial_spaces["manager"], flow.initial_spaces["recovery"]]
                 and (previous is None or value["launch_receipt"] == previous),
                 "refused Advance changed the actual original launch receipt or history")
    return value["launch_receipt"]


def history(flow):
    c = flow.c
    name = "history-pending-retirement"
    c.prepared(name, "manager", 25_000_000)
    old = c.operations[name]
    base.require([old["request"]["manage_slot"], old["request"]["manage_generation"]] == [2, 1]
                 and old["key"] == "native-cpu:" + types.sha(old["request"]["delivery"]) + ":" + name,
                 "initial Manager changed its original K/D/handle binding")
    c.native_result(name, "applied")
    c.source_terminal(name, "manager")
    flow.last_effect, flow.last_usage = old, c.current_usage()
    before = initial_busy(flow, "live")
    for role in ("recovery", "manager"):
        retired = base.obj(c.take("initial_owner_retired"), ("role", "peer_lifetime", "pidfd_revents", "wait_kind", "wait_value", "signal"),
                           "actual initial owner SIGKILL/WNOWAIT observation")
        base.require(retired["role"] == role and retired["peer_lifetime"] == c.initial_peers[role]
                     and all(type(retired[key]) is int for key in ("pidfd_revents", "wait_value", "signal"))
                     and retired["pidfd_revents"] == 1 and retired["wait_kind"] == "signaled"
                     and retired["wait_value"] == retired["signal"] == 9,
                     "both actual original privileged images were not observed dead through their held pidfds")
    initial_busy(flow, "unreaped", before)
    watchdog = base.obj(c.take("history_watchdog"), ("first_cpu_stat", "second_cpu_stat"), "actual original history watchdog")
    first, second = base.cpu_stat(watchdog["first_cpu_stat"]), base.cpu_stat(watchdog["second_cpu_stat"])
    base.require(all(first[key] == second[key] for key in first if key.startswith("hepta_watchdog_") and key != "hepta_watchdog_ticks")
                 and second["hepta_watchdog_ticks"] >= first["hepta_watchdog_ticks"],
                 "original restored watchdog receipt changed between physical observations")
    stable = list((second["hepta_watchdog_stable_id_low"] | (second["hepta_watchdog_stable_id_high"] << 64)).to_bytes(16, "little"))
    effect = old["observation"]
    base.require(stable == effect["stable_object_id"] and second["hepta_watchdog_previous_revision"] == effect["revision"]
                 and second["hepta_watchdog_effective_ns"] >= effect["effective_ns"],
                 "independent watchdog result replaced the retained old delivery terminal")
    flow.observed_watchdog = {"stable_object_id": stable, "previous_revision": second["hepta_watchdog_previous_revision"],
                              "revision": second["hepta_watchdog_revision"], "effective_ns": second["hepta_watchdog_effective_ns"],
                              "consumed_ns": second["hepta_watchdog_consumed_ns"]}
    lease = base.obj(c.take("local_lease_retired"), ("lease_id", "generation", "mode", "observed_unix_seconds", "expires_at_unix_seconds"),
                     "original crashed writer lease expiry")
    original_writer = c.currents["manager"]["head"]["writer_binding"]
    base.require(lease["mode"] == "expired" and lease["lease_id"] == original_writer["lease_id"]
                 and type(lease["generation"]) is int and lease["generation"] == original_writer["generation"]
                 and type(lease["expires_at_unix_seconds"]) is int
                 and lease["expires_at_unix_seconds"] == original_writer["expires_at_unix_seconds"]
                 and base.integer(lease["observed_unix_seconds"], "actual original expiry observation", 1) >= lease["expires_at_unix_seconds"],
                 "both process deaths were incorrectly treated as an original writer release")
    flow.last_stopped_line = c.next_line()
    reaped = base.obj(c.take("initial_recovery_reaped"), ("peer_lifetime", "registry", "driver_fault", "supervisor"),
                      "actual original failed Recovery-slot transaction")
    base.require(reaped["peer_lifetime"] == c.initial_peers["recovery"]
                 and types.text(reaped["driver_fault"], "actual original driver fault", 8192)
                     .endswith("kernel-initial child is no longer alive"),
                 "unexpected driver failure cannot qualify a dead original Recovery slot")
    registry = base.obj(reaped["registry"], ("schema_version", "agent_id", "generation", "lifecycle"), "original failed lifecycle registry")
    base.require(type(registry["schema_version"]) is int and registry["schema_version"] == 1
                 and registry["agent_id"] == flow.agent and registry["lifecycle"] == "failed",
                 "original failed-slot CAS was skipped or replaced")
    spawn = flow.initial_ready["spawn_generation"]
    snapshot = types.supervisor(reaped["supervisor"], spawn, flow.initial_pids["manager"], False, failed_recovery=True)
    events = snapshot["events"]
    lifecycle = [(event["generation"], event["details"]["state"]) for event in events if event["kind"] == "lifecycle"]
    exits = [event for event in events if event["kind"] == "exited"]
    base.require(lifecycle == [(spawn, "starting"), (spawn + 1, "running"), (spawn + 2, "failed"),
                               (spawn + 3, "starting"), (spawn + 4, "failed")]
                 and type(registry["generation"]) is int and registry["generation"] == spawn + 4
                 and len(exits) == 1 and exits[0]["generation"] == spawn + 2
                 and exits[0]["details"] == {"success": False, "code": None}
                 and sum(event["kind"] == "spawned" for event in events) == 1,
                 "actual initial Recovery failure did not preserve the original Supervisor lifecycle and consuming reap")
    # record_fault() uses generation zero after a failed spawn leaves no
    # runtime. The original producer filters snapshot events by initial spawn;
    # its separately retained TickReport fault above is the actual evidence.
    flow.last_lifecycle_generation = registry["generation"]
    flow.previous = {"role": "manager", "pid": flow.initial_pids["manager"], "peer": c.initial_peers["manager"]}
    flow.adopt()
    flow.owner("history_only")
    base.require(flow.active["kernel_generation"] == 1 and flow.launches.current["mode"] == 2,
                 "unretired original history did not receive the first actual history-only image")
    reconciled = base.obj(c.take("reconciled"), ("operation", "pid", "occurrence_key", "request_json", "terminal_json", "usage"),
                          "original history-only D observation")
    base.require(reconciled["operation"] == name and type(reconciled["pid"]) is int
                 and reconciled["pid"] == flow.active["pid"] and reconciled["occurrence_key"] == old["key"]
                 and reconciled["request_json"] == old["request_json"] and reconciled["terminal_json"] == old["terminal"]
                 and reconciled["usage"] is None,
                 "history-only reconciliation replayed an effect, fabricated ReadUsage or substituted a watchdog terminal")
    base.terminal(reconciled["terminal_json"], old["request"])
    c.source_terminal(name, "history_only")
    c.acknowledge(name, "history_only")
    flow.release()
    flow.adopt()
    flow.owner("manager")
    base.require(flow.active["kernel_generation"] == 2 and flow.launches.current["mode"] == 1,
                 "fully retired original history did not admit the actual fresh second-generation pair")
    fresh = flow.operation("fresh-control-after-history")
    done = base.obj(c.take("history_only_complete"), ("old_delivery", "old_occurrence_key", "actual_terminal_json", "fresh_delivery",
                   "fresh_occurrence_key", "kernel_launch_generation"), "actual original history-only completion")
    base.require(base.delivery(done["old_delivery"]) == old["request"]["delivery"] and done["old_occurrence_key"] == old["key"]
                 and done["actual_terminal_json"] == fresh["terminal"]
                 and base.delivery(done["fresh_delivery"]) == fresh["request"]["delivery"]
                 and done["fresh_occurrence_key"] == fresh["key"]
                 and type(done["kernel_launch_generation"]) is int and done["kernel_launch_generation"] == 2,
                 "history-only completion substituted another original K/D or new Manager effect")
    return {"history_only_transcript_verified": True, "bounded_renewal_transcript_verified": False,
            "both_initial_owners_actual_exit_and_reap_observed": True,
            "original_history_query_without_cpu_authority_observed": True,
            "old_terminal_preserved_after_watchdog": True, "fresh_kernel_generations": [2],
            "original_finite_lease_durations_preserved": True}
