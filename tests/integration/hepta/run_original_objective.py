#!/usr/bin/env python3
"""Build a small original-owner probe, or execute it with explicit input ELFs.

No Agentd, issuer, endpoint, production configuration or device is discovered.
--prepare-only writes an external probe manifest without compiling or launching.
--execute uses the original Agentd input and a fresh private temporary fleet.
"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile
import tomllib

import run_original_agentd as original

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BINARY = "hepta-original-objective-probe"
SOURCES = ["original_objective_probe.rs", "original_objective_owner.rs",
           "original_objective_fixture.rs", "original_objective_profile.json",
           "original_objective_session.rs"]
CHECKS = ["compiled_original_admission", "exact_replay_same_publication",
          "explicit_abstain_durable_without_run", "invalid_signature_owner_rejected",
          "body_generation_fenced_before_send", "revoked_issuer_owner_rejected",
          "owner_restart_retains_historical_journal", "old_spawn_not_accepted",
          "original_journal_matches_receipts", "controlled_stop"]
SESSION_PHASES = ["compiled_run_projected", "old_endpoint_run_stale",
                  "replacement_run_projection_missing"]
RUN_FIELDS = ["run_id", "revision", "phase", "authority_epoch", "generation",
              "terminal_observed", "idempotent"]


def prepare_runner(source, runner):
    omission = original.prepare_runner(source, runner)
    # Reuse the validated external package/lock identities and dev-small profile.
    # This binary name is distinct from the existing observer-only executable.
    upstream = tomllib.loads((source / "codex-rs/Cargo.toml").read_text())
    dependencies = []
    for directory in ["hepta-agent-protocol", "hepta-authbus", "hepta-objective",
                      "hepta-types", "hepta-evidence", "hepta-learning-ledger", "state",
                      "utils/absolute-path"]:
        name = "codex-utils-absolute-path" if directory == "utils/absolute-path" else "codex-" + directory
        dependencies.append(json.dumps(name) + "=" + original.toml_value({"path": str(source / "codex-rs" / directory)}))
    for name in ["chrono", "ed25519-dalek"]:
        dependencies.append(name + "=" + original.toml_value(upstream["workspace"]["dependencies"][name]))
    tokio = upstream["workspace"]["dependencies"]["tokio"]
    tokio = {"version": tokio} if isinstance(tokio, str) else dict(tokio)
    tokio["features"] = sorted(set(tokio.get("features", []) + ["rt-multi-thread", "time", "net"]))
    dependencies.append("tokio=" + original.toml_value(tokio))
    manifest = (runner / "Cargo.toml").read_text().replace(
        "[dependencies]\n", "[dependencies]\n" + "\n".join(dependencies) + "\n", 1)
    manifest += f'\n[[bin]]\nname="{BINARY}"\npath="src/main.rs"\n'
    (runner / "Cargo.toml").write_text(manifest)
    for name in SOURCES:
        target = "main.rs" if name == "original_objective_probe.rs" else name
        shutil.copyfile(HERE / name, runner / "src" / target)
    return omission


def verify_records(records, session_enabled):
    checks = [entry.get("check") for entry in records if entry.get("event") == "objective_check"]
    passes = [entry for entry in records if entry.get("event") == "acceptance_pass"]
    if checks != CHECKS or len(passes) != 1 or passes[0].get("checks") != CHECKS:
        raise original.GateError("objective_check_records_incomplete")
    result = passes[0]
    if result.get("original_commit") != original.PIN or result.get("isolated_test_issuer") is not True:
        raise original.GateError("objective_original_identity_missing")
    for field in ["production_issuer", "model_turn", "operations_dispatch", "device_effect",
                  "canonical_intelligence", "historical_run_resumed"]:
        if result.get(field) is not False:
            raise original.GateError("objective_evidence_scope_changed")
    submissions = [entry for entry in records if entry.get("event") == "submission_observed"]
    if len(submissions) != 7:
        raise original.GateError("objective_submission_records_incomplete")
    verify_publication_and_fence_records(records, submissions)
    phases = [entry.get("phase") for entry in records
              if entry.get("event") == "objective_session_phase_observed"]
    stops = [entry for entry in records if entry.get("event") == "objective_session_stopped"]
    if result.get("session_projection") is not session_enabled:
        raise original.GateError("objective_session_projection_scope_changed")
    if phases != (SESSION_PHASES if session_enabled else []) or len(stops) != (2 if session_enabled else 0):
        raise original.GateError("objective_session_phase_records_incomplete")
    if any(entry.get("signal") != 9 for entry in stops):
        raise original.GateError("objective_session_stop_not_confirmed")
    if session_enabled:
        verify_session_records(records, submissions, stops)


def require_record(condition, issue):
    if not condition:
        raise original.GateError(issue)


def run_fields(value):
    return {name: value[name] for name in RUN_FIELDS}


def valid_digest(value):
    return (isinstance(value, str) and len(value) == 64
            and all(char in "0123456789abcdef" for char in value)
            and value != "0" * 64)


def verify_publication_and_fence_records(records, submissions):
    """Keep original journal binding and sent-unknown fencing independently visible."""
    try:
        core = {entry["check"]: entry["evidence"] for entry in records
                if entry.get("event") == "objective_check"}
        journal = core["original_journal_matches_receipts"]
        recovered = journal["records"]
        require_record(isinstance(recovered, list) and len(recovered) == 2
                       and journal["acknowledged_sequence"] == 2,
                       "objective_publication_records_incomplete")
        for number, (submission, check, record) in enumerate(zip(
                [submissions[0], submissions[2]],
                ["compiled_original_admission", "explicit_abstain_durable_without_run"],
                recovered, strict=True), 1):
            receipt = core[check]["receipt"]
            require_record(submission["result"]["status"] == "admitted"
                           and submission["result"]["receipt"] == receipt
                           and record["run_id"] == receipt["run_id"]
                           and valid_digest(receipt["publication_digest"])
                           and record["publication_digest"] == receipt["publication_digest"]
                           and valid_digest(receipt["chain_digest"])
                           and record["chain_digest"] == receipt["chain_digest"]
                           and type(record["journal_sequence"]) is int
                           and record["journal_sequence"] == number
                           and record["publication_binding_checked"] is True
                           and record["changed_publication_digest_rejected"] is True,
                           "objective_receipt_not_bound_to_original_journal")
        require_record(journal["first_acknowledged_chain_digest"] == recovered[0]["chain_digest"]
                       and journal["acknowledged_chain_digest"] == recovered[1]["chain_digest"],
                       "objective_publication_chain_disagreement")
        last = submissions[6]["result"]
        fence = core["old_spawn_not_accepted"]
        restart = core["owner_restart_retains_historical_journal"]
        post = fence["post_request_owner"]
        initial = submissions[0]["result"]["identity"]
        require_record(last["status"] == fence["transport_status"] == "submit_unknown"
                       and last["issue"] == fence["issue"] == "objective_protocol_mismatch"
                       and type(last["bytes_written"]) is int and last["bytes_written"] > 0
                       and last["bytes_written"] == last["request_frame_bytes"]
                       == fence["bytes_written"] == fence["request_frame_bytes"]
                       and last["identity"]["agent_id"] == initial["agent_id"]
                       and last["identity"]["spawn_generation"] == restart["old_spawn"]
                       and last["identity"]["peer_pid"] == restart["new_pid"]
                       and post["agent_id"] == initial["agent_id"]
                       and post["spawn_generation"] == restart["new_spawn"]
                       and post["health"]["process_id"] == restart["new_pid"]
                       and post["health"]["ready"] is True
                       and post["health"]["lifecycle"] == "running"
                       and fence["post_request_run"] is None
                       and fence["journal_unchanged"] is True,
                       "objective_old_spawn_not_proven_sent_to_live_replacement")
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise original.GateError("objective_publication_or_fence_record_structure_invalid") from error


def verify_session_records(records, submissions, stops):
    """Validate cross-process identity relationships, not only pass labels."""
    try:
        phases = [entry for entry in records if entry.get("event") == "objective_session_phase_observed"]
        first, stale, replacement = phases
        admitted = submissions[0]["result"]
        expected = first["evidence"]["original_run"]
        core = {entry["check"]: entry["evidence"] for entry in records
                if entry.get("event") == "objective_check"}
        require_record(admitted["status"] == "admitted"
                       and admitted["receipt"] == core["compiled_original_admission"]["receipt"]
                       and admitted["receipt"]["disposition"] == "compiled"
                       and expected["run_id"] == admitted["receipt"]["run_id"]
                       and expected["generation"] == admitted["receipt"]["response_generation"]
                       and expected["phase"] == "admitted" and expected["terminal_observed"] is False
                       and expected["revision"] == admitted["identity"]["objective_revision"]
                       and expected["authority_epoch"] == admitted["identity"]["authority_epoch"],
                       "session_run_does_not_match_original_admission")
        for number, phase in enumerate(phases, 1):
            instance = phase["session_instance"]
            snapshot = phase["snapshot"]
            require_record(phase["sequence"] == number and phase["phase"] == SESSION_PHASES[number - 1]
                           and isinstance(instance, str) and len(instance) == 32
                           and all(char in "0123456789abcdef" for char in instance)
                           and type(phase["session_pid"]) is int and phase["session_pid"] > 0
                           and type(phase["worker_tid"]) is int and phase["worker_tid"] > 0
                           and snapshot["session_instance"] == instance
                           and snapshot["type"] == "snapshot" and snapshot["tasks"] == []
                           and phase["ack"] == {"sequence": number, "phase": phase["phase"], "session_instance": instance}
                           and phase["capture_ack_is_coordination_only"] is True,
                           "session_phase_identity_or_scope_invalid")
            require_record(Path(phase["runtime_dir"]).is_absolute()
                           and phase["runtime_dir"] == first["runtime_dir"]
                           and phase["session_socket_path"] == str(Path(first["runtime_dir"]) / "trillionnium-ui/session.sock")
                           and phase["original"]["agent_id"] == admitted["identity"]["agent_id"]
                           and phase["original"]["active"] is True and phase["original"]["healthy"] is True,
                           "session_runtime_or_original_owner_identity_changed")
        require_record(all(stale[field] == first[field] for field in ["session_pid", "session_instance", "worker_tid"])
                       and replacement["session_instance"] != first["session_instance"],
                       "session_replaced_without_explicit_boundary")
        restart = core["owner_restart_retains_historical_journal"]
        require_record(first["original"]["spawn_generation"] == admitted["identity"]["spawn_generation"] == restart["old_spawn"]
                       and first["original"]["process_id"] == admitted["identity"]["peer_pid"] == restart["old_pid"]
                       and stale["original"] == replacement["original"]
                       and stale["original"]["spawn_generation"] == restart["new_spawn"] > restart["old_spawn"]
                       and stale["original"]["process_id"] == restart["new_pid"] != restart["old_pid"],
                       "session_original_restart_identity_disagreement")
        initial_run = first["snapshot"]["hepta"]["run"]
        require_record(initial_run["run_id"] == expected["run_id"] and initial_run["connection"] == "observed"
                       and initial_run["error_code"] is None and initial_run["observation_gap"] is False
                       and run_fields(initial_run["last_observation"]) == run_fields(expected)
                       and initial_run["last_observation"]["observation_sequence"] > 0
                       and 0 < initial_run["last_observation"]["sampled_unix_ms"] <= initial_run["last_attempt_unix_ms"] <= first["recorded_unix_ms"]
                       and first["recorded_unix_ms"] - initial_run["last_observation"]["sampled_unix_ms"] <= 7_000,
                       "session_initial_run_projection_invalid")
        prior = stale["evidence"]["first_stale_snapshot"]
        stale_run = stale["snapshot"]["hepta"]["run"]
        require_record(prior["session_instance"] == first["session_instance"]
                       and stale_run["connection"] == prior["hepta"]["run"]["connection"] == "stale"
                       and stale_run["observation_gap"] is True
                       and stale_run["last_observation"] == prior["hepta"]["run"]["last_observation"]
                       and run_fields(stale_run["last_observation"]) == run_fields(expected)
                       and stale_run["last_attempt_unix_ms"] == prior["hepta"]["run"]["last_attempt_unix_ms"]
                       and stale_run["error_code"] == prior["hepta"]["run"]["error_code"]
                       and stale_run["error_code"] in ["protocol_mismatch", "generation_fenced", "owner_rejected"]
                       and stale["snapshot"]["hepta"]["last_attempt_unix_ms"] > prior["hepta"]["last_attempt_unix_ms"]
                       and stale["evidence"]["retained_run_unchanged_across_failed_samples"] is True,
                       "session_stale_run_not_preserved")
        missing = replacement["snapshot"]["hepta"]["run"]
        require_record(missing["run_id"] == expected["run_id"] and missing["connection"] == "projection_missing"
                       and missing["error_code"] == "run_projection_missing" and missing["last_observation"] is None
                       and missing["observation_gap"] is False
                       and replacement["evidence"]["missing_projection_is_not_non_admission"] is True,
                       "session_missing_projection_semantics_changed")
        for phase in [first, replacement]:
            health = phase["snapshot"]["hepta"]
            require_record(health["connection"] == "observed"
                           and health["last_observation"]["agent_id"] == phase["original"]["agent_id"]
                           and health["last_observation"]["spawn_generation"] == phase["original"]["spawn_generation"]
                           and health["last_observation"]["health"]["process_id"] == phase["original"]["process_id"]
                           and health["last_observation"]["health"]["ready"] is True
                           and health["last_observation"]["health"]["lifecycle"] == "running",
                           "session_health_does_not_match_original_owner")
        for stop, phase in zip(stops, [stale, replacement], strict=True):
            require_record(all(stop[field] == phase[field] for field in ["session_pid", "session_instance", "worker_tid"])
                           and records.index(stop) > records.index(phase), "session_stop_identity_disagreement")
        require_record(records.index(stops[0]) < records.index(replacement), "session_replacement_started_before_owned_stop")
    except (KeyError, TypeError, ValueError, IndexError) as error:
        raise original.GateError("objective_session_record_structure_invalid") from error


def binary_record(path):
    path = path.resolve(strict=True)
    if not path.is_file() or not os.access(path, os.X_OK):
        raise original.GateError("native_input_not_executable")
    with path.open("rb") as stream:
        if stream.read(4) != b"\x7fELF":
            raise original.GateError("native_input_not_elf")
    return {"path": str(path), "bytes": path.stat().st_size, "sha256": original.sha256(path)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hepta-source", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True, help="New directory outside either source checkout")
    parser.add_argument("--target-dir", type=Path, help="Shared original target cache; does not launch an Agentd build")
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--rustup", default=shutil.which("rustup") or "rustup")
    parser.add_argument("--agentd-bin", type=Path)
    parser.add_argument("--observer-bin", type=Path)
    parser.add_argument("--submitter-bin", type=Path)
    parser.add_argument("--probe-bin", type=Path, help="Optional prebuilt probe; caller must bind its build to SOURCES")
    parser.add_argument("--session-bin", type=Path)
    parser.add_argument("--ctl-bin", type=Path)
    parser.add_argument("--session-phase-dir", type=Path, help="New private directory for optional renderer capture/ack coordination")
    parser.add_argument("--session-ack-seconds", type=int, default=60)
    args = parser.parse_args()
    report = {"recorded_at_utc": datetime.now(timezone.utc).isoformat(),
              "schema": "hepta.original-objective-probe.v1", "status": "preflight",
              "runtime_executed": False, "steps": [], "source_sha256": {
                  name: original.sha256(HERE / name) for name in
                  SOURCES + ["run_original_objective.py", "run_original_agentd.py"]}}
    work = args.work_dir.resolve()
    code = 1
    owned_work = False
    try:
        source = args.hepta_source.resolve(strict=True)
        report["upstream"] = original.verify_source(source)
        if work.exists() or work.is_relative_to(source) or work.is_relative_to(ROOT):
            raise original.GateError("work_must_be_new_and_outside_source_checkouts")
        if args.prepare_only and args.execute:
            raise original.GateError("prepare_only_cannot_execute")
        session_enabled = args.session_bin is not None or args.ctl_bin is not None
        if session_enabled and (not args.execute or args.session_bin is None or args.ctl_bin is None):
            raise original.GateError("session_projection_requires_execute_and_both_native_inputs")
        if args.session_phase_dir and not session_enabled:
            raise original.GateError("session_phase_directory_requires_native_session_inputs")
        if not 1 <= args.session_ack_seconds <= 120:
            raise original.GateError("session_ack_seconds_out_of_range")
        work.mkdir(mode=0o700)
        owned_work = True
        runner = work / "probe"
        report["patch_omission"] = prepare_runner(source, runner)
        report["runner"] = str(runner)
        report["runner_binary"] = BINARY
        report["session_projection_requested"] = session_enabled
        report["native_input_source_binding"] = "caller_supplied_build_provenance_required_for_each_elf"
        target = args.target_dir.resolve() if args.target_dir else work / "target"
        report["target"] = str(target)
        if args.prepare_only:
            report["status"] = "prepared_not_built_or_executed"
        else:
            offline = ["--offline"] if args.offline else []
            if not args.probe_bin:
                steps = [
                    ("probe-resolution", ["metadata", *offline, "--format-version", "1"]),
                    ("probe-locked-metadata", ["metadata", "--locked", *offline, "--format-version", "1"]),
                    ("probe-build", ["build", "--locked", *offline, "--profile", "dev-small", "--bin", BINARY, "-j1"]),
                ]
                lock_hash = None
                for label, cargo_args in steps:
                    command = [args.rustup, "run", original.UPSTREAM_TOOLCHAIN, "cargo", *cargo_args]
                    report["steps"].append({"label": label, "command": command})
                    original.bounded_command(command, runner, original.build_environment(target), work / f"{label}.log", 3600)
                    report["lock_validation"] = original.verify_runner_lock(source, runner)
                    current = original.sha256(runner / "Cargo.lock")
                    if lock_hash is not None and current != lock_hash:
                        raise original.GateError("resolved_probe_lock_changed")
                    lock_hash = current
                report["resolved_lock_sha256"] = lock_hash
                probe = target / "dev-small" / BINARY
            else:
                probe = args.probe_bin
                report["prebuilt_probe_requires_caller_build_binding"] = True
            report["status"] = "probe_built_runtime_not_executed" if not args.probe_bin else "prebuilt_probe_runtime_not_executed"
            report["binaries"] = {"probe": binary_record(probe)}
            if args.execute:
                for name in ["agentd", "observer", "submitter"]:
                    path = getattr(args, name + "_bin")
                    if path is None:
                        raise original.GateError("execution_requires_three_explicit_native_binaries")
                    report["binaries"][name] = binary_record(path)
                if session_enabled:
                    for name in ["session", "ctl"]:
                        report["binaries"][name] = binary_record(getattr(args, name + "_bin"))
                report["runtime_executed"] = True
                log = work / "runtime.log"
                with tempfile.TemporaryDirectory(prefix="ho-", dir="/tmp") as root:
                    command = [report["binaries"][name]["path"] for name in ["probe", "agentd", "observer", "submitter"]] + [root]
                    if session_enabled:
                        for name in ["session", "ctl"]:
                            command += ["--" + name + "-bin", report["binaries"][name]["path"]]
                        if args.session_phase_dir:
                            command += ["--session-phase-dir", str(args.session_phase_dir.resolve()),
                                        "--session-ack-seconds", str(args.session_ack_seconds)]
                    report["runtime_command"] = command
                    environment = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HEPTA_COGNITIVE_RETRIEVAL_MODE": "compatibility"}
                    try:
                        timeout = 240 + (3 * args.session_ack_seconds if args.session_phase_dir else 0)
                        original.bounded_command(command, ROOT, environment, log, timeout)
                    finally:
                        evidence = Path(root) / "probe-evidence"
                        if evidence.is_dir():
                            shutil.copytree(evidence, work / "runtime-evidence")
                            for ordinal in [1, 2]:
                                session_log = Path(root) / "objective-ui" / f"session-{ordinal}.log"
                                if session_log.is_file():
                                    shutil.copyfile(session_log, work / "runtime-evidence" / f"session-{ordinal}.log")
                if log.stat().st_size > 1024 * 1024:
                    raise original.GateError("runtime_log_bound_exceeded")
                records = [json.loads(line) for line in log.read_text().splitlines() if line.startswith("{")]
                verify_records(records, session_enabled)
                report["runtime_records"] = records
                for binary in report["binaries"].values():
                    if original.sha256(Path(binary["path"])) != binary["sha256"]:
                        raise original.GateError("native_input_changed_during_execution")
                report["status"] = "passed"
        original.verify_source(source)
        code = 0
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
    if owned_work:
        with (work / "report.json").open("x") as stream:
            json.dump(report, stream, indent=2)
            stream.write("\n")
    print(json.dumps(report, indent=2))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
