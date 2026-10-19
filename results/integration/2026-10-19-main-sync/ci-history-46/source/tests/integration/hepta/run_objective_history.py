#!/usr/bin/env python3
"""Build/run the separately pinned original-owner Objective history probe.

Uses the tracked OBJECTIVE_HISTORY_CONTRACT, never overrides the R8 PIN.
--prepare-only does not build or launch. Runtime inputs are four explicit ELFs;
storage faults are restricted to the stopped disposable qualification owner.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import tomllib

import run_original_agentd as original
import run_original_objective as objective

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CONTRACT = ROOT / "services/hepta-os/OBJECTIVE_HISTORY_CONTRACT.json"
BINARY = "hepta-objective-history-probe"
SOURCES = ["objective_history_probe.rs", "objective_history_client.rs",
           "original_objective_owner.rs", "original_objective_fixture.rs",
           "original_objective_profile.json", "run_objective_history.py",
           "run_original_objective.py", "run_original_agentd.py"]
CHECKS = ["live_compiled_publication", "live_abstain_publication",
          "retained_anchor_covers_publication", "harness_lost_response_then_history",
          "postpublication_submit_unknown_history_published",
          "wrong_anchor_unknown", "earlier_anchor_unknown", "changed_signed_request_unknown",
          "restart_projection_missing_history_published", "expired_request_history_still_published",
          "rollback_retained_anchor_unknown",
          "truncated_tail_retained_anchor_unknown", "revoked_issuer_history_still_published",
          "revoked_new_submission_rejected", "controlled_stop"]
FALSE_SCOPE = ["operations_dispatch", "device_effect", "model_turn", "production_issuer",
               "canonical_intelligence", "historical_run_resumed", "operations_k_or_d_created",
               "hepta_submit_cli_lost_reply_executed"]
NOT_EXECUTED = ["caller_anchor_co_rollback", "production_issuer", "effect_reconciliation",
                "kernel_g1", "kernel_g2"]


def need(condition, issue):
    if not condition:
        raise original.GateError(issue)


def sha_bytes(value):
    return hashlib.sha256(value).hexdigest()


def digest(value, length=64):
    return isinstance(value, str) and re.fullmatch(f"[0-9a-f]{{{length}}}", value) is not None


def git_bytes(source, ref):
    return subprocess.check_output(["git", "-C", str(source), "show", ref],
                                   stderr=subprocess.PIPE, timeout=30)


def read_contract(path):
    """Require the exact tracked document, not a working-tree PIN substitution."""
    path = path.resolve(strict=True)
    repository = Path(original.git(path.parent, "rev-parse", "--show-toplevel"))
    relative = path.relative_to(repository).as_posix()
    committed = git_bytes(repository, "HEAD:" + relative)
    need(path.read_bytes() == committed, "history_contract_not_committed_exactly")
    contract = json.loads(committed)
    need(contract.get("schema_version") == 1
         and contract.get("repository", "").removesuffix(".git").rstrip("/")
         == "https://github.com/TrillionniumFoundation/hepta-private-ci"
         and contract.get("base_commit") == original.PIN
         and digest(contract.get("commit"), 40)
         and contract["commit"] != original.PIN
         and digest(contract.get("cargo_lock_sha256"))
         and contract.get("control_schema_version") == 2
         and contract.get("profile") == "linux-local-known-objective-history"
         and contract.get("read_method_allowlist") == ["ObjectiveAdmission"]
         and contract.get("max_control_frame_bytes_including_newline") == 65_536,
         "history_contract_profile_invalid")
    files = contract.get("files")
    need(isinstance(files, list) and bool(files), "history_contract_files_missing")
    names = set()
    for entry in files:
        relative_path = entry.get("path")
        need(isinstance(relative_path, str) and relative_path.startswith("codex-rs/")
             and not Path(relative_path).is_absolute() and ".." not in Path(relative_path).parts
             and relative_path not in names and digest(entry.get("sha256")),
             "history_contract_file_binding_invalid")
        names.add(relative_path)
    return contract, {"path": str(path), "sha256": sha_bytes(committed),
                      "desktop_commit": original.git(repository, "rev-parse", "HEAD")}


def verify_source(source, contract):
    need(original.git(source, "rev-parse", "HEAD") == contract["commit"],
         "history_upstream_commit_mismatch")
    need(not original.git(source, "status", "--porcelain=v1", "--untracked-files=all"),
         "history_upstream_checkout_not_clean")
    subprocess.run(["git", "-C", str(source), "merge-base", "--is-ancestor",
                    contract["base_commit"], contract["commit"]], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=30)
    lock = original.sha256(source / "codex-rs/Cargo.lock")
    need(lock == contract["cargo_lock_sha256"], "history_upstream_lock_mismatch")
    for entry in contract["files"]:
        path = source / entry["path"]
        need(path.resolve(strict=True).is_relative_to(source)
             and original.sha256(path) == entry["sha256"]
             and path.read_bytes() == git_bytes(source, contract["commit"] + ":" + entry["path"]),
             "history_upstream_reviewed_file_mismatch")
    toolchain = tomllib.loads((source / "codex-rs/rust-toolchain.toml").read_text())
    need(toolchain["toolchain"]["channel"] == original.UPSTREAM_TOOLCHAIN,
         "history_upstream_toolchain_mismatch")
    return {"commit": contract["commit"], "tree": original.git(source, "rev-parse", "HEAD^{tree}"),
            "cargo_lock_sha256": lock, "clean_checkout": True,
            "reviewed_files": len(contract["files"])}


def prepare_runner(source, runner, binding):
    # Reuse the original crates, pinned lock identity checks and isolated owner.
    # The old R8 probe/PIN/runner are neither changed nor used as the executable.
    omission = objective.prepare_runner(source, runner)
    text = (runner / "Cargo.toml").read_text()
    text = text.replace(f'name="{objective.BINARY}"', f'name="{BINARY}"')
    parsed = tomllib.loads(text)
    tokio = dict(parsed["dependencies"]["tokio"])
    tokio["features"] = sorted(set(tokio.get("features", [])) | {"io-util"})
    text = "\n".join("tokio=" + original.toml_value(tokio) if line.startswith("tokio=") else line
                     for line in text.splitlines()) + "\n"
    (runner / "Cargo.toml").write_text(text)
    shutil.copyfile(HERE / "objective_history_probe.rs", runner / "src/main.rs")
    shutil.copyfile(HERE / "objective_history_client.rs", runner / "src/objective_history_client.rs")
    (runner / "src/objective_history_source_binding.json").write_text(
        json.dumps(binding, sort_keys=True, separators=(",", ":")) + "\n")
    return omission


def verify_records(records, binding):
    """Cross-bind the actual CLI/owner/fault records; this is not a new runtime."""
    try:
        checks = [record for record in records if record.get("event") == "objective_history_check"]
        passes = [record for record in records if record.get("event") == "acceptance_pass"]
        need([record["check"] for record in checks] == CHECKS and len(passes) == 1
             and passes[0]["checks"] == CHECKS, "history_checks_incomplete")
        passed = passes[0]
        need(passed["source_binding"] == binding and passed["isolated_test_issuer"] is True
             and all(passed[field] is False for field in FALSE_SCOPE)
             and passed["not_executed"] == NOT_EXECUTED
             and passed["objective_request_attempts"] == 5
             and passed["published_objective_requests"] == 4
             and passed["recovery_resubmissions"] == 0, "history_scope_or_source_drift")
        core = {record["check"]: record["evidence"] for record in checks}
        observed = [record for record in records if record.get("event") == "history_query_observed"]
        need(len(observed) == 13, "history_cli_queries_missing")
        for record in observed:
            result = record["result"]
            need(record["journal_unchanged"] is True and digest(record["journal_sha256"])
                 and result["schema_version"] == 1 and result["bytes_written"] > 0
                 and result["bytes_written"] == result["request_frame_bytes"]
                 and record["exit_code"] == {"historical_publication": 0, "unknown": 12}[result["status"]],
                 "history_cli_transport_or_readonly_mismatch")
        actual_results = [record["result"] for record in observed]
        for name in CHECKS[:-2]:
            need(core[name]["history"] in actual_results, "history_check_not_an_actual_cli_result")
        first = core[CHECKS[0]]["history"]
        second = core[CHECKS[1]]["history"]
        lost = core[CHECKS[3]]["history"]
        postpublication = core[CHECKS[4]]
        capacity = postpublication["history"]
        for sequence, result, disposition in [(1, first, "compiled"), (2, second, "explicit_abstain"),
                                                (3, lost, "compiled"), (4, capacity, "compiled")]:
            publication = result["publication"]
            need(result["status"] == "historical_publication"
                 and publication["publication_sequence"] == sequence
                 and publication["outcome"]["type"] == disposition
                 and all(digest(publication[field]) for field in
                         ["publication_digest", "chain_digest", "signed_body_digest", "profile_digest"]),
                 "history_publication_identity_invalid")
        need(core[CHECKS[2]]["history"]["publication"] == first["publication"]
             and core[CHECKS[2]]["history"]["anchor"] == {
                 "sequence": 2, "chain_digest": second["publication"]["chain_digest"]},
             "history_retained_anchor_disagreement")
        need(all(core[CHECKS[index]]["resubmission_count"] == 0 for index in [3, 4, 8, 9, 10, 11]),
             "history_recovery_resubmitted")
        submissions = [record for record in records if record.get("event") == "submission_observed"]
        loss_records = [record for record in records if record.get("event") == "objective_response_discarded"]
        need(len(submissions) == 4 and len(loss_records) == 1, "history_submission_attempts_drift")
        for submission in submissions:
            result = submission["result"]
            need(result["bytes_written"] > 0 and result["bytes_written"] == result["request_frame_bytes"]
                 and submission["exit_code"] == {"admitted": 0, "submit_unknown": 12}[result["status"]],
                 "history_submission_transport_mismatch")
        for index, result in [(0, first), (1, second)]:
            submission = submissions[index]["result"]
            need(core[CHECKS[index]]["submission"] == submission and submission["status"] == "admitted"
                 and submission["receipt"]["publication_digest"] == result["publication"]["publication_digest"]
                 and submission["receipt"]["chain_digest"] == result["publication"]["chain_digest"]
                 and submission["receipt"]["idempotent"] is False
                 and submission["receipt"]["response_generation"] == result["response_generation"],
                 "history_submission_receipt_not_bound")
        loss = loss_records[0]["evidence"]
        need(loss == core[CHECKS[3]]["loss"] and loss["response_bytes_read"] == 0
             and loss["response_discarded_by_harness"] is True
             and loss["hepta_submit_cli_loss_case"] is False
             and loss["submission_outcome"] == "unknown" and loss["bytes_written"] > 0
             and loss["bytes_written"] == loss["request_frame_bytes"]
             and loss["run_id"] == lost["publication"]["run_id"]
             and loss["peer_pid"] == first["identity"]["peer_pid"]
             and loss["peer_uid"] == first["identity"]["peer_uid"], "history_loss_fault_not_bound")
        rejected = submissions[2]["result"]
        active = postpublication["active_runs_before_submission"]
        need(postpublication["submission"] == rejected and rejected["status"] == "submit_unknown"
             and rejected["issue"] == "objective_owner_request_rejected"
             and rejected["identity"]["run_id"] == capacity["publication"]["run_id"]
             and postpublication["run_status"] is None
             and postpublication["source_inference"] == "original_default_run_capacity_exhausted"
             and postpublication["specific_original_error_bytes_observed"] is False
             and postpublication["active_run_ids"] == [first["publication"]["run_id"], lost["publication"]["run_id"]]
             and len(active) == 2
             and all(run["phase"] == "admitted" and run["terminal_observed"] is False for run in active),
             "history_postpublication_error_not_bound")
        for index, reason in [(5, "anchor_mismatch"), (6, "publication_outside_anchor"),
                              (7, "no_matching_publication"), (10, "anchor_missing"), (11, "anchor_missing")]:
            result = core[CHECKS[index]]["history"]
            need(result["status"] == "unknown" and result["issue"] == reason
                 and "publication" not in result, "history_unknown_promoted")
        restart = core[CHECKS[8]]
        need(restart["new_spawn"] > restart["old_spawn"] and restart["new_pid"] != restart["old_pid"]
             and restart["run_status"] is None and restart["history"]["publication"] == lost["publication"]
             and restart["history"]["identity"]["spawn_generation"] == restart["new_spawn"]
             and restart["history"]["identity"]["original_spawn_generation"] == restart["old_spawn"],
             "history_restart_identity_not_fenced")
        expiry = core[CHECKS[9]]
        need(expiry["history"]["publication"] == second["publication"]
             and expiry["history"]["identity"]["spawn_generation"] == restart["new_spawn"]
             and expiry["expires_at_ms"] == second["publication"]["expires_at_ms"]
             and expiry["observed_at_ms"] > expiry["expires_at_ms"]
             and 0 <= expiry["wait_elapsed_ms"] <= expiry["wait_bound_ms"] == 30_000
             and expiry["history"]["anchor"] == {
                 "sequence": 4, "chain_digest": capacity["publication"]["chain_digest"]},
             "history_real_expiry_not_observed")
        for index in [10, 11]:
            fault = core[CHECKS[index]]["fault"]
            need(fault["owner_confirmed_stopped_before_fault"] is True
                 and fault["new_spawn"] > fault["old_spawn"]
                 and fault["recovery_owner"] == "original_agentd"
                 and all(digest(fault[field]) for field in ["before_sha256", "injected_sha256", "recovered_sha256"])
                 and core[CHECKS[index]]["resubmission_count"] == 0, "history_fault_owner_not_stopped")
        need(core[CHECKS[10]]["fault"]["recovered_sha256"] == observed[0]["journal_sha256"]
             and core[CHECKS[10]]["fault"]["injected_sha256"] == observed[0]["journal_sha256"]
             and core[CHECKS[10]]["fault"]["before_sha256"] == observed[4]["journal_sha256"]
             and core[CHECKS[11]]["fault"]["before_sha256"] == observed[0]["journal_sha256"]
             and core[CHECKS[11]]["fault"]["recovered_sha256"] == observed[3]["journal_sha256"],
             "history_fault_did_not_recover_exact_prefix")
        need(core[CHECKS[12]]["issuer_revoked"] is True and core[CHECKS[12]]["issuer_restored"] is False
             and core[CHECKS[12]]["history"]["publication"] == first["publication"]
             and core[CHECKS[13]]["submission"] == submissions[-1]["result"]
             and submissions[-1]["result"]["status"] == "submit_unknown"
             and submissions[-1]["result"]["issue"] == "objective_owner_request_rejected"
             and core[CHECKS[13]]["journal_unchanged"] is True
             and core[CHECKS[14]]["active"] is False, "history_revoke_or_stop_missing")
    except (KeyError, IndexError, TypeError, ValueError) as error:
        raise original.GateError("history_record_shape_invalid") from error


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hepta-source", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=CONTRACT,
                        help="Exact tracked history contract; defaults to this desktop checkout")
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--target-dir", type=Path)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--rustup", default=shutil.which("rustup") or "rustup")
    for name in ["agentd", "observer", "submitter", "history", "probe"]:
        parser.add_argument("--" + name + "-bin", type=Path)
    args = parser.parse_args()
    report = {"schema": "hepta.objective-history-probe.v1", "status": "preflight",
              "recorded_at_utc": datetime.now(timezone.utc).isoformat(), "runtime_executed": False,
              "steps": [], "source_sha256": {name: original.sha256(HERE / name) for name in SOURCES}}
    work = args.work_dir.resolve()
    owned_work = False
    code = 1
    try:
        source = args.hepta_source.resolve(strict=True)
        contract, contract_record = read_contract(args.contract)
        report["contract"] = contract_record
        report["upstream"] = verify_source(source, contract)
        binding = {"commit": contract["commit"], "tree": report["upstream"]["tree"],
                   "cargo_lock_sha256": report["upstream"]["cargo_lock_sha256"],
                   "contract_sha256": contract_record["sha256"], "probe_inputs": report["source_sha256"]}
        report["compiled_source_binding"] = binding
        need(not work.exists() and not work.is_relative_to(source) and not work.is_relative_to(ROOT),
             "history_work_must_be_new_and_outside_sources")
        need(not (args.prepare_only and args.execute), "history_prepare_cannot_execute")
        work.mkdir(mode=0o700)
        owned_work = True
        runner = work / "probe"
        report["patch_omission"] = prepare_runner(source, runner, binding)
        report["runner"] = str(runner)
        target = args.target_dir.resolve() if args.target_dir else work / "target"
        report["target"] = str(target)
        if args.prepare_only:
            report["status"] = "prepared_not_built_or_executed"
        else:
            probe = args.probe_bin
            if probe is None:
                flags = ["--offline"] if args.offline else []
                lock = None
                for label, arguments in [
                    ("resolution", ["metadata", *flags, "--format-version", "1"]),
                    ("locked-metadata", ["metadata", "--locked", *flags, "--format-version", "1"]),
                    ("build", ["build", "--locked", *flags, "--profile", "dev-small", "--bin", BINARY, "-j1"]),
                ]:
                    command = [args.rustup, "run", original.UPSTREAM_TOOLCHAIN, "cargo", *arguments]
                    report["steps"].append({"label": label, "command": command})
                    original.bounded_command(command, runner, original.build_environment(target), work / f"{label}.log", 3600)
                    report["lock_validation"] = original.verify_runner_lock(source, runner)
                    current = original.sha256(runner / "Cargo.lock")
                    need(lock is None or lock == current, "history_probe_lock_changed")
                    lock = current
                report["resolved_lock_sha256"] = lock
                probe = target / "dev-small" / BINARY
            else:
                report["prebuilt_probe_requires_caller_build_binding"] = True
            report["binaries"] = {"probe": objective.binary_record(probe)}
            report["status"] = "probe_available_runtime_not_executed"
            if args.execute:
                for name in ["agentd", "observer", "submitter", "history"]:
                    path = getattr(args, name + "_bin")
                    need(path is not None, "history_execute_requires_four_explicit_binaries")
                    report["binaries"][name] = objective.binary_record(path)
                report["runtime_executed"] = True
                log = work / "runtime.log"
                with tempfile.TemporaryDirectory(prefix="hh-", dir="/tmp") as root:
                    command = [report["binaries"][name]["path"] for name in
                               ["probe", "agentd", "observer", "submitter", "history"]] + [root]
                    report["runtime_command"] = command
                    environment = {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8",
                                   "HEPTA_COGNITIVE_RETRIEVAL_MODE": "compatibility"}
                    try:
                        original.bounded_command(command, ROOT, environment, log, 240)
                    finally:
                        evidence = Path(root) / "probe-evidence"
                        if evidence.is_dir():
                            shutil.copytree(evidence, work / "runtime-evidence")
                need(log.stat().st_size <= 1024 * 1024, "history_runtime_log_bound_exceeded")
                records = [json.loads(line) for line in log.read_text().splitlines() if line.startswith("{")]
                report["runtime_records"] = records
                verify_records(records, binding)
                for binary in report["binaries"].values():
                    need(original.sha256(Path(binary["path"])) == binary["sha256"], "history_native_input_changed")
                report["status"] = "passed"
        verify_source(source, contract)
        need(read_contract(args.contract)[1] == contract_record, "history_contract_changed")
        need(report["source_sha256"] == {name: original.sha256(HERE / name) for name in SOURCES},
             "history_probe_source_changed")
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
