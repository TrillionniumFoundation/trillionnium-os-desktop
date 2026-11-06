#!/usr/bin/env python3
"""Resume only qualification of the exact previously observed successor.

No restart/replay/rediscovery/adoption exists in this path. The failed run must
have durably recorded its real successful native restart receipt, original
pidfd deaths, and an exact eight-role successor candidate. A different process
generation fails. A missing candidate or unresolved prior job is not resumable.
"""
import argparse
import hashlib
import json
import os
import stat
import sys
import time
import types

sys.dont_write_bytecode = True


def read_pin(path, pin, limit):
    if not path.startswith("/") or any(v in ("", ".", "..") for v in path[1:].split("/")):
        raise RuntimeError("EXACT_PATH_REQUIRED")
    descriptors = []
    try:
        parent = os.open("/", os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
        descriptors.append(parent)
        parts = path[1:].split("/")
        for name in parts[:-1]:
            parent = os.open(name, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent)
            descriptors.append(parent)
        fd = os.open(parts[-1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent)
        descriptors.append(fd)
        def meta(f):
            s = os.fstat(f)
            return tuple(getattr(s, k) for k in ("st_dev", "st_ino", "st_mode", "st_uid", "st_gid", "st_nlink", "st_size", "st_mtime_ns", "st_ctime_ns"))
        before = meta(fd)
        if not stat.S_ISREG(before[2]) or before[5] != 1 or not 0 < before[6] <= limit:
            raise RuntimeError("BOUNDED_REGULAR_REQUIRED")
        output, deadline = bytearray(), time.monotonic() + 5
        while len(output) <= limit:
            if time.monotonic() >= deadline:
                raise RuntimeError("READ_DEADLINE")
            chunk = os.read(fd, min(65536, limit + 1 - len(output)))
            if not chunk:
                break
            output.extend(chunk)
        again = os.open(parts[-1], os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent)
        descriptors.append(again)
        if meta(fd) != before or meta(again) != before or len(output) != before[6] or hashlib.sha256(output).hexdigest() != pin:
            raise RuntimeError("EXACT_SOURCE_PIN_CHANGED")
        return bytes(output)
    finally:
        failures = []
        for fd in reversed(descriptors):
            try:
                os.close(fd)
            except BaseException:
                failures.append(fd)
        if failures:
            raise RuntimeError("SOURCE_DESCRIPTOR_RETIREMENT_FAILED")


def actual_chain(core, request):
    candidate = core.parse(core.pinned_record(request["candidate"]))
    failed = core.parse(core.pinned_record(request["failed_result"], 65536))
    core.need(candidate.get("schema") == "pocket4-observed-successor-candidate-v1" and
              candidate.get("discovery_performed_once_after_actual_native_receipt") is True,
              "ACTUAL_FIXED_CANDIDATE_REQUIRED")
    core.need(failed.get("schema") == "pocket4-owned-cell-recovery-result-v1" and failed.get("ok") is False and
              failed.get("restart_attempted") is True and failed.get("outcome_unknown") is False and
              failed.get("identity_qualified") is False and bool(failed.get("errors")), "SETTLED_FAILED_QUALIFICATION_REQUIRED")
    candidate_root = request["candidate"]["path"].rsplit("/", 1)[0]
    core.need(request["failed_result"]["path"] == candidate_root + "/result.json", "FAILED_RESULT_MUST_BELONG_TO_CANDIDATE")
    transition = core.parse(core.pinned_record(candidate["transition"]))
    core.need(candidate["transition"]["path"] == candidate_root + "/retired-lifecycle.private.json" and
              transition.get("schema") == "pocket4-actual-native-lifecycle-transition-v1" and
              transition.get("old_launch_replayed") is False, "ACTUAL_LIFECYCLE_TRANSITION_REQUIRED")
    previous = core.parse(core.pinned_record(transition["predecessor"]))
    core.need(transition["predecessor"]["path"] == candidate_root + "/predecessor.private.json" and
              previous.get("schema") == "pocket4-lifecycle-preflight-v1" and
              previous["plan_sha256"] == core.digest(core.canonical(previous["plan"])), "PREDECESSOR_LINEAGE_REQUIRED")
    native = core.parse(core.pinned_record(transition["native_receipt"]))
    core.need(transition["native_receipt"]["path"] == candidate_root + "/native-restart-receipt.private.json" and
              native.get("schema") == "pocket4-native-restart-actual-receipt-v1" and
              native["command"]["argv"] == core.native_argv("restart"), "ACTUAL_NATIVE_RESTART_COMMAND_REQUIRED")
    body = native["stdout_utf8"].encode()
    core.need(core.digest(body) == native["command"]["stdout_sha256"] and len(body) == native["command"]["stdout_bytes"] and
              native["stderr_utf8"] == "", "ACTUAL_NATIVE_STDOUT_HASH_REQUIRED")
    status = core.native_running(body, native["command"])
    attempt = core.parse(core.pinned_record(native["attempt"]))
    core.need(native["attempt"]["path"] == candidate_root + "/restart-attempted.json" and
              attempt.get("schema") == "pocket4-native-restart-attempt-v1" and
              attempt["predecessor"] == transition["predecessor"] and attempt["argv"] == core.native_argv("restart") and
              attempt.get("automatic_retry") is False, "ORIGINAL_RESTART_ATTEMPT_REQUIRED")
    rows = candidate["held"]["process_snapshot"]["binding"]["processes"]
    old_rows = previous["runtime"]["held"]["process_snapshot"]["binding"]["processes"]
    core.need(set(rows) == set(core.ROLE_NAMES) and rows["launcher"] == transition["actual_successor_launcher"] and
              status["host_pid"] == rows["launcher"]["host_pid"] and transition["boot_id"] == core.boot_id() ==
              candidate["held"]["process_snapshot"]["binding"]["boot_id"], "EXACT_RECORDED_SUCCESSOR_CELL_REQUIRED")
    deaths = transition["old_pidfd_deaths"]
    core.need(set(deaths) == set(core.RETIRED), "ALL_RETIRED_NATIVE_CELL_ROLES_REQUIRED")
    for role in core.RETIRED:
        old = old_rows[role]
        core.need(deaths[role] == {"host_pid": old["host_pid"], "start_ticks": old["start_ticks"],
                                  "original_pre_restart_pidfd_readable": True}, "ORIGINAL_PIDFD_DEATH_RECEIPT_REQUIRED")
        core.need((rows[role]["host_pid"], rows[role]["start_ticks"]) != (old["host_pid"], old["start_ticks"]),
                  "RETIRED_PROCESS_CANNOT_BE_SUCCESSOR")
        try:
            current = core.E.process_identity(old["host_pid"])
        except (core.E.EpochError, FileNotFoundError, ProcessLookupError):
            try:
                os.stat("/proc/" + str(old["host_pid"]), follow_symlinks=False)
            except FileNotFoundError:
                continue
            raise core.Rejected("OLD_PROCESS_ABSENCE_INDETERMINATE")
        core.need(current["start_ticks"] != old["start_ticks"], "RETIRED_NATIVE_PROCESS_STILL_LIVE")
    return candidate, transition, previous, status


def run(core, encoded, manifest_sha, request):
    core.need(os.getuid() == os.geteuid() == 0, "ROOT_REQUIRED")
    core.need(set(request) == {"schema", "candidate", "failed_result", "fresh_drain", "output_root"} and
              request["schema"] == "pocket4-resume-fixed-successor-qualification-v1", "CLOSED_RESUME_REQUEST_REQUIRED")
    output_root = request["output_root"]
    core.path_parts(output_root)
    core.need(output_root.startswith("/home/alex/work/pocket4-cell-successor-") and output_root.count("/") == 4 and
              not os.path.lexists(output_root), "NEW_RESUME_OUTPUT_ROOT_REQUIRED")
    pool, leases = core.FDs(), core.FDs()
    result = {"schema": "pocket4-resumed-successor-result-v1", "ok": False, "restart_attempted": False,
              "rediscovery": False, "automatic_retry": False, "UI_or_install_runtime_admitted": False,
              "production_ready": False, "errors": []}
    baseline = app_document = None
    phase = "actual_lifecycle_chain"
    try:
        candidate, transition, previous, native_status = actual_chain(core, request)
        core.need(candidate["source_manifest_sha256"] == previous["source_manifest_sha256"] == manifest_sha,
                  "ORIGINAL_QUALIFIER_SOURCE_CLOSURE_REQUIRED")
        core.acquire_lock(leases, core.ACTION_LOCK)
        core.reviewed_drain(leases, request["fresh_drain"])
        phase = "exact_previously_recorded_candidate"
        expected = candidate["held"]["process_snapshot"]
        held = core.HeldProcesses(pool, {role: row["host_pid"] for role, row in expected["binding"]["processes"].items()})
        core.need(held.before["binding"] == expected["binding"] and held.extra == candidate["held"]["extra"],
                  "RECORDED_SUCCESSOR_CHANGED_NO_ADOPTION")
        daemon, presenter = core.service(), core.service(True)
        core.need(daemon == previous["runtime"]["daemon_service"] and presenter == candidate["presenter_service"],
                  "RECORDED_SERVICE_LINEAGE_CHANGED")
        raw, _, command = core.bounded_child(core.native_argv("status"))
        core.need(core.native_running(raw, command)["host_pid"] == native_status["host_pid"], "CURRENT_NATIVE_OWNER_CHANGED")
        plan = previous["plan"]
        core.pinned_record(plan["native_cli"], 32 * 1024 * 1024)
        core.unknown_evidence(plan)
        phase = "actual_runtime_and_apps"
        old_runtime = previous["runtime"]
        runtime = core.collect_runtime(pool, held, daemon, presenter, plan["cell_config_sha256"], old_runtime["engine"]["sha256"])
        core.need(runtime["limits"] == old_runtime["limits"] and
                  core.classpath_bytes(runtime["classpath"]) == core.classpath_bytes(old_runtime["classpath"]) and
                  all(runtime["binaries"][role]["sha256"] == old_runtime["binaries"][role]["sha256"] for role in core.ROLE_NAMES),
                  "EXPLICIT_RESTART_ARTIFACTS_CHANGED")
        targets = sorted(previous["apps"])
        apps = core.app_scope(pool, held, targets)
        core.need(core.app_bytes(apps) == core.app_bytes(previous["apps"]), "APPS_CHANGED_SINCE_RESTART_PRE_SCOPE")
        phase = "three_new_double_observations"
        samples = [held.verify()]
        core.verify_runtime(pool, held, runtime)
        samples.append(held.verify())
        until = samples[0]["collected_monotonic_ns"] + 10_000_000_000
        while time.monotonic_ns() <= until:
            core.need(all(not core.pidfd_dead(fd) for fd in held.pidfds.values()), "RECORDED_SUCCESSOR_DIED")
            time.sleep(.1)
        samples.append(held.verify())
        times = core.validate_span(samples)
        core.verify_runtime(pool, held, runtime)
        core.app_scope(pool, held, targets, apps, False)
        core.unknown_evidence(plan)
        final = held.verify()
        core.need(final["binding"] == samples[0]["binding"], "FINAL_RECORDED_SUCCESSOR_CHANGED")
        runtime["held"]["process_snapshot"] = final
        runtime_sha = core.digest(core.canonical(runtime))
        framework = core.android_epoch(final)
        baseline = {"schema": "pocket4-successor-runtime-baseline-v1", "kind": "explicit-owned-cell-lifecycle-successor",
                    "runtime": runtime, "runtime_epoch_sha256": runtime_sha, "framework_epoch": framework,
                    "predecessor": transition["predecessor"], "actual_lifecycle_transition": candidate["transition"],
                    "resumed_fixed_candidate": request["candidate"], "prior_failed_result": request["failed_result"],
                    "sample_monotonic_ns": times, "bounded_observation_is_not_future_stability_proof": True,
                    "framework_exit_cause_resolved": False, "native_future_epoch_retirement_fix_deployed": False,
                    "UI_or_install_runtime_admitted": False, "production_ready": False}
        app_document = {"schema": "pocket4-versioned-app-scope-v1", "runtime_epoch_sha256": runtime_sha,
                        "kind": "unchanged-across-explicit-cell-restart", "apps": apps,
                        "previous_app_content_sha256": core.digest(core.canonical(core.app_bytes(previous["apps"]))),
                        "target_roster": plan["targets"], "fresh_signature_verification_performed": False,
                        "post_restart_launcher_resolver_enumerated": False, "UI_or_install_runtime_admitted": False}
    except BaseException as error:
        result["errors"].append({"phase": phase, **core.safe_error(error)})
    finally:
        try:
            pool.close_all()
        except BaseException as error:
            result["errors"].append({"phase": "descriptor_retirement", **core.safe_error(error)})
        result["observation_fds"] = pool.summary()
    if baseline is not None and app_document is not None and not result["errors"]:
        try:
            core.create_private_root(output_root)
            for name, content in encoded.items():
                core.write_new(output_root + "/source/" + name, content)
            bpin = core.write_new(output_root + "/baseline.private.json", core.canonical(baseline) + b"\n")
            apin = core.write_new(output_root + "/app-scope-01.private.json", core.canonical(app_document) + b"\n")
            q = {"schema": "pocket4-successor-qualification-v1", "identity_qualified": True, "baseline": bpin,
                 "initial_app_scope": apin, "runtime_epoch_sha256": baseline["runtime_epoch_sha256"],
                 "source_manifest_sha256": manifest_sha, "old_native_pidfd_deaths_proved": True,
                 "initial_app_scope_unchanged": True, "observation_fds": result["observation_fds"],
                 "UI_or_install_runtime_admitted": False, "production_ready": False, "old_unknown_launch_replayed": False,
                 "qualification_resumed_without_rediscovery": True}
            qpin = core.write_new(output_root + "/qualification.json", core.canonical(q) + b"\n")
            generated = core.guard_source(output_root, manifest_sha, bpin, qpin)
            gpin = core.write_new(output_root + "/current_baseline_guard.py", generated)
            guard = core.load_module(generated, "resumed_actual_guard", gpin["path"])
            guard_result = guard.current_guard()
            result.update(ok=True, identity_qualified=True, baseline=bpin, app_scope=apin, qualification=qpin,
                          generated_current_guard=gpin, published_guard_readback=guard_result)
        except BaseException as error:
            result["ok"] = False
            result["errors"].append({"phase": "resumed_publication", **core.safe_error(error)})
    try:
        leases.close_all()
    except BaseException as error:
        result["ok"] = False
        result["errors"].append({"phase": "lease_retirement", **core.safe_error(error)})
    result["lease_fds"] = leases.summary()
    if os.path.isdir(output_root):
        try:
            core.write_new(output_root + "/result.json", core.canonical(result) + b"\n")
        except BaseException as error:
            result["ok"] = False
            result["errors"].append({"phase": "result_publication", **core.safe_error(error)})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--request", required=True)
    parser.add_argument("--request-sha256", required=True)
    parser.add_argument("--source-manifest-sha256", required=True)
    args = parser.parse_args()
    os.umask(0o077)
    try:
        source = os.path.dirname(os.path.abspath(__file__))
        raw_manifest = read_pin(source + "/SOURCE_PINS.json", args.source_manifest_sha256, 65536)
        manifest = json.loads(raw_manifest)
        raw = read_pin(source + "/successor_runtime.py", manifest["files"]["successor_runtime.py"]["sha256"], 65536)
        core = types.ModuleType("resume_pinned_runtime")
        core.__file__ = source + "/successor_runtime.py"
        exec(compile(raw, core.__file__, "exec"), core.__dict__)
        encoded = core.configure(source, args.source_manifest_sha256)
        core.need(read_pin(__file__, manifest["files"]["resume_successor_qualification.py"]["sha256"], 65536) ==
                  encoded["resume_successor_qualification.py"], "RUNNING_RESUME_SOURCE_PIN_REQUIRED")
        request = core.parse(read_pin(args.request, args.request_sha256, 262144))
        result = run(core, encoded, args.source_manifest_sha256, request)
    except BaseException as error:
        result = {"ok": False, "restart_attempted": False, "rediscovery": False, "type": type(error).__name__}
    text = json.dumps(result, sort_keys=True, separators=(",", ":"), allow_nan=False)
    if len(text.encode()) > 65536:
        raise RuntimeError("PUBLIC_RESULT_BOUND")
    print(text, flush=True)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
