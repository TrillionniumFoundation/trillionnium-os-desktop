#!/usr/bin/env python3
"""Read-only correlation of one externally pinned owned PSI evidence set.

This does not run a workload, inspect Main, control a unit, or manufacture an
execution receipt. The coordinator supplies the evidence/source/build pins,
binds the retained outer counters to its observed cgroup and successful unit
InvocationID/ExecMainPID, and separately proves exact cleanup and the Main fence.
"""
import argparse
import hashlib
import json
import os
import stat
import struct
import sys

MIB = 1024 * 1024
HARD, HIGH, CAP = 512 * MIB, 384 * MIB, 432 * MIB
WINDOW = 1_000_000_000
LMKD_SHA = "bd794b7b59d1047523cea6174bcd230c75aa2eececd1900b23f3f33a86061dde"
COMMON = {
    "staging-result.json", "inner-preflight.json", "outer-preflight.json",
    "relay-projection.json", "broker-ready.json", "broker-active.json",
    "broker-retired.json", "broker-pressure-audit.json", "driver-result.json",
    "phase-result.json", "identities.json", "lmkd-post-registration-pressure-file.json",
    "pressure-workload.json", "quiet-before.json", "quiet-after.json",
    "pressure-before.json", "after-relay-hup.json", "target-cleanup.json", "outer-final.json",
}


class Rejected(ValueError):
    pass


def need(condition, message):
    if not condition:
        raise Rejected(message)


def integer(value, minimum=0):
    need(type(value) is int and minimum <= value < 2**64, "bounded nonnegative integer required")
    return value


def pin(value):
    need(type(value) is str and len(value) == 64 and all(c in "0123456789abcdef" for c in value)
         and value != "0" * 64, "external canonical nonzero SHA/nonce required")
    return value


def object_pairs(pairs):
    result = {}
    for key, value in pairs:
        need(key not in result, "duplicate JSON object key")
        result[key] = value
    return result


def decode(raw):
    return json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=object_pairs)


def bounded_read(directory_fd, name):
    need("/" not in name and name not in ("", ".", ".."), "fixed evidence basename required")
    fd = os.open(name, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=directory_fd)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= 1024 * 1024, "bounded regular evidence file required")
        pieces = []
        remaining = before.st_size + 1
        while remaining:
            chunk = os.read(fd, min(remaining, 65536))
            if not chunk:
                break
            pieces.append(chunk)
            remaining -= len(chunk)
        raw = b"".join(pieces)
        after = os.fstat(fd)
        need(len(raw) == before.st_size and
             (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
             (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
             "evidence changed during held descriptor read")
        return raw
    finally:
        os.close(fd)


def required_names(phase):
    need(phase in ("pressure", "stale"), "only fixed pressure or stale phase")
    return COMMON | ({"pressure-after.json", "cached-exit.json", "cached-kill-notification.json", "cached-kill-diagnostic.json"}
                     if phase == "pressure" else {"stale-after.json", "pressure-relief.json"})


def load_evidence(directory, expected_manifest, expected_source, phase):
    pin(expected_manifest)
    pin(expected_source)
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        raw = bounded_read(fd, "qualification-inputs.json")
        need(hashlib.sha256(raw).hexdigest() == expected_manifest, "external evidence manifest pin mismatch")
        manifest = decode(raw)
        need(manifest["schema"] == 1 and manifest["phase"] == phase and
             manifest["source_manifest_sha256"] == expected_source, "external source/phase pin mismatch")
        pin(manifest["matching_build_receipt_sha256"])
        binaries = manifest["binaries_sha256"]
        need(set(binaries) == {"actor", "driver", "broker", "android_lmkd"}, "complete matching binary pin set required")
        for value in binaries.values():
            pin(value)
        need(binaries["android_lmkd"] == LMKD_SHA, "actual Android r6 binary pin changed")
        rows = manifest["files"]
        need(type(rows) is list and len(rows) == len(required_names(phase)), "complete evidence set required")
        indexed = {}
        for row in rows:
            need(set(row) == {"name", "sha256", "bytes"}, "exact evidence row schema")
            name = row["name"]
            need(name in required_names(phase) and name not in indexed, "unexpected or duplicate evidence name")
            raw = bounded_read(fd, name)
            need(integer(row["bytes"], 1) == len(raw) and pin(row["sha256"]) == hashlib.sha256(raw).hexdigest(),
                 "actual evidence byte/hash mismatch")
            indexed[name] = decode(raw)
        need(set(indexed) == required_names(phase), "missing actual evidence files")
        return manifest, indexed
    finally:
        os.close(fd)


def counters(raw):
    result = {}
    need(type(raw) is str, "raw memory.events text required")
    for line in raw.splitlines():
        fields = line.split()
        need(len(fields) == 2 and fields[0] not in result and fields[1].isascii() and fields[1].isdigit(), "invalid memory.events row")
        result[fields[0]] = integer(int(fields[1]))
    need({"high", "max", "oom", "oom_kill", "oom_group_kill"} <= set(result), "memory.events counters incomplete")
    return result


def no_oom(before, after):
    for key in ("max", "oom", "oom_kill", "oom_group_kill"):
        need(before[key] == after[key], "kernel memory max/OOM counter changed")
    need(after["high"] >= before["high"], "memory.high counter went backwards")


def psi(raw):
    result = {}
    for line in raw.splitlines():
        fields = line.split()
        need(fields and fields[0] in ("some", "full") and fields[0] not in result, "PSI row shape")
        totals = [field[6:] for field in fields[1:] if field.startswith("total=")]
        need(len(totals) == 1 and totals[0].isascii() and totals[0].isdigit(), "PSI total missing")
        result[fields[0]] = integer(int(totals[0]))
    need(set(result) == {"some", "full"}, "both actual PSI totals required")
    return result


def qualified_outer_final(outer, driver, audit, domain, phase):
    """Validate actual driver-retained counters before systemd removes the unit cgroup.

    The caller still binds this identity to its observed InvocationID/ExecMainPID,
    proves terminal success and exact cleanup, and verifies the Main epoch.
    """
    need(outer["schema"] == 1 and outer["source"] ==
         "owned-driver-after-all-child-retirement-before-exit", "joined outer resource record required")
    unit = outer["unit"]
    need(type(unit) is str and unit.startswith("p4-lmkd-relay-") and unit.endswith(".service") and
         all(c.isascii() and (c.isalnum() or c in "-.") for c in unit) and ".." not in unit,
         "exact owned outer unit name required")
    pid = integer(outer["driver_pid"], 1)
    need(outer["phase"] == phase and outer["nonce"] == driver["nonce"] == audit["nonce"] and
         driver["driver_pid"] == pid, "outer retirement phase/nonce/driver mismatch")
    identity = (integer(outer["cgroup_device"], 1), integer(outer["cgroup_inode"], 1))
    need((outer["domain_device"], outer["domain_inode"]) == domain and identity != domain,
         "outer resource record must cover its own parent of the scoped domain")
    need(integer(outer["observed_monotonic_ns"], 1) >= audit["retired_monotonic_ns"],
         "outer resources sampled before joined broker retirement")
    need(outer["limits"] == {"memory.max": str(HARD), "memory.high": "max", "memory.swap.max": "0",
                              "cpu.max": "100000 100000", "pids.max": "64"}, "outer fixed limits changed")
    events = outer["memory_events"]
    need(type(events) is dict and {"low", "high", "max", "oom", "oom_kill", "oom_group_kill"} <= set(events),
         "complete outer memory.events required")
    for value in events.values():
        integer(value)
    need(all(events[name] == 0 for name in ("max", "oom", "oom_kill", "oom_group_kill")),
         "outer max/OOM counter is nonzero")
    need(integer(outer["memory_current"]) <= integer(outer["memory_peak"], 1) < HARD and
         integer(outer["swap_current"]) == integer(outer["swap_peak"]) == 0,
         "outer final current/peak/swap violates original limits")
    need(outer["root_members"] == [] and outer["host_members"] == [pid] and
         integer(outer["pids_current"]) == 1 and
         outer["cgroup_events"] == {"populated": 1, "frozen": 0} and
         outer["domain_events"] == {"populated": 0, "frozen": 0},
         "unexpected outer member or unretired domain")
    return {"unit": unit, "driver_pid": pid, "cgroup_device": identity[0], "cgroup_inode": identity[1]}


def qualified(manifest, data, phase):
    """Pure control boundary; inputs only become trusted via load_evidence."""
    audit = data["broker-pressure-audit.json"]
    driver = data["driver-result.json"]
    result = data["phase-result.json"]
    work = data["pressure-workload.json"]
    staging = data["staging-result.json"]
    inner, outer = data["inner-preflight.json"], data["outer-preflight.json"]
    projection = data["relay-projection.json"]
    need(staging["ok"] is True and staging["all_source_and_copied_hashes_matched"] is True and
         staging["actor_sha256"] == manifest["binaries_sha256"]["actor"] and staging["lmkd_sha256"] == LMKD_SHA,
         "staging is not bound to the matching owned binaries")
    for key in ("ok", "actual_broker", "same_cell_retry_denied", "broker_retired_and_reaped",
                "owner_and_init_exited", "android_enrollment", "joined_host_audit_present", "pressure_workload_requested"):
        need(driver[key] is True, "driver completion or retained lifecycle proof missing")
    need(driver["domain_populated"] is False and driver["installed_supervisor_changed"] is False and
         driver["bootstrap_rights"] == 16 and driver["phase"] == phase, "wrong owned driver scope")
    for key in ("ok", "marked_contract_rejected", "real_protocol_verified", "actual_relay_hup_verified",
                "pressure_workload_complete", "host_audit_required", "nonvictim_cleanup_verified"):
        need(result[key] is True, "native protocol/workload/HUP evidence missing")
    need(result["phase"] == phase and result["route"] == "PIDFD-only minimal root" and
         result["production_cgroup_kill_qualified"] is False and result["pid_reuse_qualified"] is False,
         "unqualified production route was relabelled")
    need(driver["real_pressure_verified"] is False and result["real_pressure_verified"] is False and
         work["real_pressure_verified"] is False, "a component prematurely claimed aggregate qualification")
    nonce = pin(audit["nonce"])
    generation = pin(audit["authority_generation"])
    lease_generation = pin(audit["lease_generation"])
    need(nonce == driver["nonce"] and lease_generation != generation, "nonce/generation binding mismatch")
    root = (integer(audit["cgroup_device"], 1), integer(audit["cgroup_inode"], 1))
    need(root == (inner["domain_dev"], inner["domain_ino"]) == (outer["domain_dev"], outer["domain_ino"]) ==
         (inner["cgroup_dev"], inner["cgroup_ino"]), "actual namespace/cgroup scope mismatch")
    need(inner["pid"] == 1 and inner["ppid"] == 0 and inner["domain_relative"] == "/domain" and
         inner["state_noexec"] is True and inner["closed_inherited_fds"] is True, "owned namespace preflight incomplete")
    need(driver["owner_pid"] == outer["bootstrap_host_pid"] and driver["init_pid"] == outer["child_host_pid"],
         "retired driver owner/init identity mismatch")
    need(audit["budget_hex"] == struct.pack("<QQQII", HARD, HIGH, 0, 0, 1).hex(), "immutable original budget differs")
    endpoint = (projection["device"], projection["inode"])
    need(projection["uid"] == 1069 and projection["gid"] == 1069 and projection["mode"] == 0o600,
         "actual endpoint role differs")
    for state, name, granted in (("Ready", "broker-ready.json", False), ("Active", "broker-active.json", True),
                                  ("Retired", "broker-retired.json", True)):
        status = data[name]
        need(status["state"] == state and status["nonce"] == nonce and status["generation"] == generation and
             (status["cgroup_device"], status["cgroup_inode"]) == root and status["budget_hex"] == audit["budget_hex"] and
             (status["endpoint_device"], status["endpoint_inode"]) == endpoint and status["granted"] is granted and
             status["faulted"] is False, "READY/ACTIVE/RETIRED scope or grant mismatch")
    need(audit["schema"] == 1 and audit["source"] == "actual-registration-write-and-POLLPRI-send-after-joined-retirement" and
         audit["granted"] is True and audit["faulted"] is False and audit["incomplete"] is False and
         audit["overflow"] is False and audit["stop_reason"] == 1, "actual joined pressure audit incomplete/faulted")
    retired_ns = integer(audit["retired_monotonic_ns"], 1)
    outer_identity = qualified_outer_final(data["outer-final.json"], driver, audit, root, phase)
    pressure_file = data["lmkd-post-registration-pressure-file.json"]
    need((pressure_file["cgroup_device"], pressure_file["cgroup_inode"]) == root, "pressure file belongs to another domain")
    registrations = audit["registrations"]
    need(len(registrations) == 2 and {r["level"] for r in registrations} == {1, 2}, "both original registrations required")
    registered = {}
    for row in registrations:
        level = integer(row["level"], 1)
        stall, trigger = (70_000, "some 70000 1000000") if level == 1 else (700_000, "full 700000 1000000")
        need(row["window_us"] == 1_000_000 and row["stall_us"] == stall and row["trigger"] == trigger and
             row["bytes_written"] == len(trigger) and row["pressure_device"] == pressure_file["pressure_device"] and
             row["pressure_inode"] == pressure_file["pressure_inode"] and row["pressure_device"] == root[0] and
             integer(row["pressure_inode"], 1) > 0, "actual registration write/default/inode mismatch")
        need(0 < integer(row["write_started_ns"]) <= integer(row["write_completed_ns"]) <= retired_ns,
             "registration monotonic interval invalid")
        registered[level] = row
    events = audit["events"]
    need(type(events) is list and 0 < len(events) <= 64 and
         audit["observations"] == audit["packets_queued"] == len(events), "actual kernel/queued audit is incomplete or empty")
    sequence, observed = {1: 0, 2: 0}, {1: 0, 2: 0}
    for event in events:
        level = integer(event["level"], 1)
        need(level in registered and event["sequence"] == sequence[level] + 1, "event level/sequence mismatch")
        now, sent = integer(event["observed_ns"], 1), integer(event["send_completed_ns"], 1)
        need(registered[level]["write_completed_ns"] <= now <= sent <= retired_ns and
             now >= observed[level] and sent - now < WINDOW, "queued event time/freshness mismatch")
        sequence[level] += 1
        observed[level] = now
    need(work["phase"] == phase and work["workload_complete"] is True and work["host_audit_required"] is True and
         work["protected_targets_alive"] is True and work["budget_unchanged"] is True, "actual workload did not complete")
    need(work["max"] == HARD and work["high"] == HIGH and work["first_kill_current_cap"] == CAP and
         HIGH < integer(work["peak_observed_current"]) <= CAP and work["cached_bytes"] == 64 * MIB and
         work["foreground_bytes"] == 128 * MIB and 0 < integer(work["allocator_bytes"]) <= 216 * MIB,
         "pressure workload changed bounds or priority contrast")
    quiet_start, quiet_end = integer(work["quiet_started_ns"], 1), integer(work["quiet_completed_ns"], 1)
    start, finished = integer(work["pressure_start_ns"], 1), integer(work["allocation_finished_ns"], 1)
    end = integer(work["quiet_end_ns"], 1)
    need(quiet_start + 2 * WINDOW <= quiet_end <= start <= finished <= end <= retired_ns, "workload monotonic phase ordering")
    need(all(not quiet_start <= event["observed_ns"] <= quiet_end for event in events), "quiet plateau contains a real PSI event")
    before, after = counters(work["events_before"]), counters(work["events_after"])
    no_oom(before, after)
    need(after["high"] > before["high"] and work["some_after"] > work["some_before"] and
         work["full_after"] >= work["full_before"], "scoped actual PSI/high counters did not increase")
    for name in ("quiet-before.json", "quiet-after.json", "pressure-before.json", "after-relay-hup.json",
                 "pressure-after.json" if phase == "pressure" else "stale-after.json"):
        sample = data[name]
        need(sample["max"] == str(HARD) + "\n" and sample["high"] == str(HIGH) + "\n" and
             integer(sample["current"]) <= CAP, "sampled original budget/current bound differs")
        no_oom(before, counters(sample["events"]))
    need(psi(data["quiet-before.json"]["pressure"]) == psi(data["quiet-after.json"]["pressure"]) and
         data["quiet-before.json"]["current"] < HIGH and data["quiet-after.json"]["current"] < HIGH,
         "quiet occupancy/live-lease control did not remain pressure-free")
    identities = data["identities.json"]
    targets = {row["label"]: row for row in identities["children"]}
    need(len(identities["children"]) == len(targets) == 5 and set(targets) ==
         {"cached", "foreground", "protected", "sentinel", "allocator"}, "complete unique owned targets required")
    need(len({row["pid"] for row in targets.values()}) == 5, "owned target PID collision")
    for index, (name, adj) in enumerate((("cached", 900), ("foreground", 0), ("protected", -1000), ("sentinel", 0), ("allocator", 0))):
        row = targets[name]
        need(integer(row["pid"], 2) > 1 and integer(row["start"], 1) > 0 and integer(row["pidfd"], 3) >= 3 and
             row["uid"] == 10001 + index and row["oom_score_adj"] == adj, "owned UID/priority/identity mismatch")
    cleanup = data["target-cleanup.json"]
    closed = {row["label"]: row for row in cleanup["children"]}
    need(cleanup["lmkd_reaped_before_nonvictim_check"] is True and len(cleanup["children"]) == 5 and
         set(closed) == set(targets), "complete target cleanup after exact LMKD exit required")
    for name, target in targets.items():
        row = closed[name]
        known_victim = phase == "pressure" and name == "cached"
        need((row["pid"], row["uid"], row["start"]) == (target["pid"], target["uid"], target["start"]) and
             row["known_cached_victim"] is known_victim and row["exit_code"] == (-1 if known_victim else 0) and
             row["exit_signal"] == (9 if known_victim else 0), "late victim or unknown target exit during cleanup")
    levels = []
    critical_decision = False
    if phase == "pressure":
        victim, notification = data["cached-exit.json"], data["cached-kill-notification.json"]
        exit_ns = integer(work["cached_exit_observed_ns"], 1)
        need(start <= exit_ns <= end and work["stopped_ns"] == 0 and work["resume_ns"] == 0 and
             work["kill_count"] == 1 and work["final_current"] < HIGH and
             data["pressure-after.json"]["current"] < HIGH and data["after-relay-hup.json"]["current"] < HIGH,
             "single cached victim did not restore below-high headroom")
        cached = targets["cached"]
        need(victim["pid"] == cached["pid"] and victim["start"] == cached["start"] and victim["si_code"] == 2 and
             victim["si_status"] == 9 and victim["observed_monotonic_ns"] == exit_ns,
             "exact cached pidfd SIGKILL evidence differs")
        need(notification["pid"] == cached["pid"] and notification["uid"] == cached["uid"] and
             notification["bytes"] == 16 and notification["command"] == 6 and
             exit_ns <= notification["observed_monotonic_ns"] <= end and notification["rss_kib"] >= 64 * 1024,
             "actual LMK_PROCKILL identity/RSS evidence differs")
        diagnostic = data["cached-kill-diagnostic.json"]
        need(diagnostic["pid"] == cached["pid"] and diagnostic["uid"] == cached["uid"] and
             diagnostic["oom_score_adj"] == 900 and type(diagnostic["line"]) is str and
             0 < len(diagnostic["line"]) < 2048 and
             f"({cached['pid']}), uid {cached['uid']}, oom_score_adj 900 to free " in diagnostic["line"] and
             "; reason: " in diagnostic["line"], "actual native kill diagnostic identity/reason differs")
        critical_decision = diagnostic["line"].endswith("; reason: device is not responding")
        levels = sorted({event["level"] for event in events
                         if start <= event["observed_ns"] <= event["send_completed_ns"] <= exit_ns and
                         exit_ns - event["observed_ns"] < WINDOW})
        need(levels, "no actual fresh scoped PSI event before cached exit observation")
        critical = 2 in levels
        status = "pass" if critical else "partial_medium_only"
    else:
        stopped, resumed = integer(work["stopped_ns"], 1), integer(work["resume_ns"], 1)
        need(quiet_end <= stopped <= start <= finished and finished + 2 * WINDOW <= resumed and
             resumed + WINDOW <= end and work["cached_exit_observed_ns"] == 0 and work["kill_count"] == 0 and
             work["final_current"] > HIGH and data["stale-after.json"]["current"] > HIGH,
             "stale control did not retain above-high targets and zero kills")
        queued_while_stopped = [event for event in events if stopped <= event["observed_ns"] <= finished]
        need(queued_while_stopped, "no real pressure event was queued while exact LMKD was stopped")
        need(all(event["send_completed_ns"] < resumed and event["observed_ns"] + WINDOW < resumed for event in events),
             "stale queue has an unaged or later fresh event; trial inconclusive")
        relief = data["pressure-relief.json"]
        need(relief["released_bytes"] == work["allocator_bytes"] and end <= relief["monotonic_ns"] <= retired_ns and
             relief["current"] < HIGH and relief["all_targets_alive"] is True and relief["kill_count"] == 0 and
             relief["budget_changed"] is False and data["after-relay-hup.json"]["current"] < HIGH,
             "post-observation cleanup relief changed targets/budget or preceded stale observation")
        critical = any(event["level"] == 2 for event in queued_while_stopped)
        status = "pass"
    return {
        "schema": 1, "phase": phase, "qualification_status": status,
        "actual_scoped_pressure_evidence": True,
        "fresh_critical_event_correlated_with_cached_exit": phase == "pressure" and critical,
        "fresh_levels_correlated_with_cached_exit": levels,
        "native_critical_kill_decision_observed": critical_decision,
        "stale_actual_queue_zero_kill_verified": phase == "stale",
        "critical_event_observed_in_phase": critical,
        "quiet_live_lease_zero_kill_verified": True, "foreground_and_protected_preserved": True,
        "native_defaults": ["some 70000 1000000", "full 700000 1000000"],
        "nonce": nonce, "authority_generation": generation, "lease_generation": lease_generation,
        "cgroup_device": root[0], "cgroup_inode": root[1],
        "outer_final_resources_after_joined_retirement_verified": True,
        "outer_identity_for_external_unit_binding": outer_identity,
        "route": "PIDFD-only minimal root", "external_main_unit_cleanup_fences_verified_here": False,
        "production_cgroup_kill_qualified": False, "pid_reuse_qualified": False,
        "installed_supervisor_recovery_qualified": False, "all_apps_production_ready": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--source-manifest-sha256", required=True)
    parser.add_argument("--phase", required=True, choices=("pressure", "stale"))
    args = parser.parse_args()
    try:
        manifest, data = load_evidence(args.evidence_dir, args.manifest_sha256, args.source_manifest_sha256, args.phase)
        result = qualified(manifest, data, args.phase)
        result.update(evidence_manifest_sha256=args.manifest_sha256, source_manifest_sha256=args.source_manifest_sha256,
                      matching_build_receipt_sha256=manifest["matching_build_receipt_sha256"])
        print(json.dumps(result, sort_keys=True, separators=(",", ":")))
        return 0 if result["qualification_status"] == "pass" else 2
    except (Rejected, OSError, ValueError, KeyError, TypeError, UnicodeError) as error:
        print(json.dumps({"schema": 1, "phase": args.phase, "qualification_status": "rejected_or_inconclusive",
                          "error": str(error), "actual_pressure_pass": False}, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())
