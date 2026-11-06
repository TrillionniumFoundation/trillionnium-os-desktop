#!/usr/bin/env python3
"""Checkpoint03 receipt validation only; no Main, shell, network or Git actions."""
import base64
import copy
import hashlib
import json
import re
from pathlib import Path

R2_PREFIX = "recovery/independent_repair_r2/actual-execute-01/"
R2_JOB = "1a1b0f80e39-fc05-7479"
R2_STDOUT = (4946, "f5a2416411710e3ce1c0a740d51a6ca7f9d9898fa3184f27b14594ead5c26723")
R2_TERMINAL = (731, "64aa9114dce9acee4ac9c796690f0fb153157b1ff528d613f800da87f3392b69")
WRAPPER_SHA = "df2365c026cc578048ce22ebd1b22bfefc25ccc144146683d845ec828c61bf1f"
WORKERS = {
    "ad4227b4c63033018bd1147c3c589b2632168766306791696aabc53583229c96",
    "7fe3d12fd280539939c930970755e9f33ab7cda51f08a03cc54eb5f9c52508eb",
}
CORE_ROLES = {"android_init", "composer", "launcher", "surfaceflinger", "system_server", "zygote64"}


def need(condition, message):
    if not condition:
        raise ValueError("checkpoint03:" + message)


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def parse(raw):
    def pairs(items):
        value = {}
        for key, item in items:
            need(key not in value, "duplicate_JSON_key:" + key)
            value[key] = item
        return value
    def constant(value):
        raise ValueError("nonfinite_JSON_number:" + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def read(root, name):
    raw = (root / name).read_bytes()
    need(len(raw) <= 32 * 1024 * 1024, "receipt_size_bound:" + name)
    return parse(raw)


def pin(root, name):
    path = root / name
    need(path.is_file() and not path.is_symlink(), "regular_local_evidence_required:" + name)
    raw = path.read_bytes()
    return {"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def matches(actual, expected):
    return all(actual[key] == expected[key] for key in ("bytes", "sha256"))


def check_terminal(root, name, stdout_name, state=None, exit_code=None, job=None):
    value = read(root, name)
    need(isinstance(value, dict) and isinstance(value.get("job_id"), str), "terminal_identity")
    if job is not None:
        need(value["job_id"] == job, "terminal_job_changed")
    if state is not None:
        need(value.get("state") == state and value.get("exit_code") == exit_code, "terminal_not_success")
    need(all(value.get(k) is True for k in ("output_complete", "output_durable", "terminal_publication_confirmed")), "terminal_not_durable_complete")
    need(value.get("automatic_retry") is False and value.get("timed_out") is False and value.get("cancelled", False) is False, "terminal_retry_timeout_or_cancel")
    raw_pin = pin(root, stdout_name)
    logs = value.get("log_bytes", {}).get("stdout", {})
    if logs:
        need(logs.get("stored") == logs.get("seen") == raw_pin["bytes"], "stdout_length_not_complete")
    return value


def closed(value, label):
    need(value["acquired"] == value["closed"] and value["remaining"] == 0 and value["errors"] == [], label + "_FD_not_closed")


def successor_recovery(root):
    result_name, terminal_name = R2_PREFIX + "stdout.raw.jsonl", R2_PREFIX + "terminal.raw.json"
    need((pin(root, result_name)["bytes"], pin(root, result_name)["sha256"]) == R2_STDOUT, "exact_R2_stdout_pin")
    need((pin(root, terminal_name)["bytes"], pin(root, terminal_name)["sha256"]) == R2_TERMINAL, "exact_R2_terminal_pin")
    raw = (root / result_name).read_bytes()
    lines = raw.splitlines()
    need(len(lines) == 2, "R2_bootstrap_and_one_final_result")
    bootstrap, value = map(parse, lines)
    need(bootstrap["mode"] == "execute" and bootstrap["bootstrap_Main_actions"] == 0
         and bootstrap["bootstrap_FDs_after"] == bootstrap["bootstrap_FDs_before"], "R2_bootstrap_not_host_only_or_FD_leak")
    check_terminal(root, terminal_name, result_name, "succeeded", 0, R2_JOB)
    need(value["schema"] == "pocket4-independent-native-lifecycle-repair-result-v2" and value["mode"] == "execute", "actual_R2_execute_schema")
    need(value["ok"] is True and value["errors"] == [] and value["outcome_unknown"] is False, "R2_not_settled_success")
    for key in ("identity_qualified", "retirement_proved", "original_r2_pre_stop_pidfd_deaths_proved",
                "all_46_app_bytes_and_data_identities_unchanged", "all_historical_evidence_preserved",
                "preflight_passed", "stop_attempted", "stop_receipt_confirmed", "start_attempted", "start_receipt_confirmed",
                "original_r1_outcome_remains_unknown"):
        need(value[key] is True, "R2_required_fact:" + key)
    for key in ("original_r1_replayed", "original_r1_pre_restart_pidfd_evidence_recreated", "automatic_retry",
                "UI_or_install_runtime_admitted", "production_ready"):
        need(value[key] is False, "R2_forbidden_claim:" + key)
    for key in ("Android_commands", "UI_actions", "installs", "namespace_entries", "permission_changes"):
        need(type(value[key]) is int and value[key] == 0, "R2_unexpected_action:" + key)
    need(value["target_count"] == 46 and value["signal_syscalls"] == 1, "R2_exact_scope_or_signal_count")
    for key in ("observation_fds", "lease_fds"):
        closed(value[key], key)
    linked = {}
    for key in ("baseline", "current_guard", "initial_app_scope", "qualification", "retirement_proof",
                "transition", "wrapper_activation", "stop_receipt", "start_receipt"):
        name = R2_PREFIX + Path(value[key]["path"]).name
        need(matches(pin(root, name), value[key]), "linked_R2_receipt_pin:" + key)
        linked[key] = name
    baseline = read(root, linked["baseline"])
    qualification = read(root, linked["qualification"])
    scope = read(root, linked["initial_app_scope"])
    transition = read(root, linked["transition"])
    retired = read(root, linked["retirement_proof"])
    wrapper = read(root, linked["wrapper_activation"])
    epoch = value["runtime_epoch_sha256"]
    need(epoch == baseline["runtime_epoch_sha256"] == qualification["runtime_epoch_sha256"] == scope["runtime_epoch_sha256"], "successor_epoch_chain")
    need(qualification["identity_qualified"] is True and qualification["initial_app_scope_unchanged"] is True, "qualification_not_complete")
    need(qualification["old_native_pidfd_evidence_origin"] == "original_r2_pre_stop_pidfds" and qualification["old_native_pidfd_deaths_proved"] is True, "wrong_pidfd_generation")
    need(qualification["original_r1_outcome_remains_unknown"] is True and qualification["original_r1_pre_restart_pidfd_evidence_recreated"] is False, "original_R1_relabelled")
    need(qualification["UI_or_install_runtime_admitted"] is False and qualification["production_ready"] is False, "qualification_not_blanket_admission")
    need(matches(qualification["baseline"], value["baseline"]) and matches(qualification["initial_app_scope"], value["initial_app_scope"]), "qualification_reference_chain")
    samples = value["sample_monotonic_ns"]
    need(samples == qualification["sample_monotonic_ns"] == baseline["sample_monotonic_ns"], "triple_samples_changed")
    need(len(samples) == 3 and all(type(x) is int for x in samples) and samples[0] < samples[1] < samples[2]
         and 10_000_000_000 <= samples[2] - samples[0] <= 90_000_000_000, "triple_sample_window")
    need(set(retired["old_pidfd_deaths"]) == CORE_ROLES and retired["old_pidfd_deaths"] == transition["old_pidfd_deaths"], "six_original_R2_pidfd_deaths")
    need(all(x["original_pre_stop_r2_pidfd_readable"] is True for x in retired["old_pidfd_deaths"].values())
         and retired["intermediate_parent"]["original_pre_stop_r2_pidfd_readable"] is True, "retirement_pidfd_evidence")
    empty = retired["both_namespace_empty_samples"]
    need(len(empty) == 2 and all(len(x["members"]) == 2 and all(v == [] for v in x["members"].values()) for x in empty), "both_old_namespaces_not_empty")
    need(transition["transition_origin"] == "repaired_lifecycle_r2" and transition["original_r1_replayed"] is False, "transition_origin")
    roles = baseline["runtime"]["held"]["process_snapshot"]["binding"]["processes"]
    need(set(roles) == CORE_ROLES | {"daemon", "presenter"}, "eight_actual_roles_required")
    owner = roles["launcher"]["host_pid"]
    need(owner == transition["actual_successor_launcher"]["host_pid"] == wrapper["owner"]["host_pid"], "new_owner_chain")
    need(wrapper["android_init"]["host_pid"] == roles["android_init"]["host_pid"]
         and wrapper["android_init"]["namespace_pids"][-1] == 1, "actual_new_PID1")
    need(wrapper["source_sha256"] == WRAPPER_SHA and wrapper["actual_kill_child_argument"] == "--kill-child=KILL"
         and wrapper["PDEATHSIG_supported_by_same_source_real_tests"] is True
         and wrapper["PDEATHSIG_read_from_production_proc"] is False, "wrapper_activation_evidence")
    need(baseline["wrapper_child_death_fix_activated"] is True and baseline["UI_or_install_runtime_admitted"] is False, "baseline_identity_only")
    for key, wanted in (("stop_receipt", "stopped"), ("start_receipt", "running")):
        receipt = read(root, linked[key])
        command = receipt["command"]
        need(command["complete"] is True and command["joined"] is True and command["returncode"] == 0
             and command["errors"] == [] and command["termination_attempted"] is False, "native_lifecycle_command_not_complete")
        out = base64.b64decode(receipt["stdout_base64"], validate=True)
        need(len(out) == command["stdout_bytes"] and hashlib.sha256(out).hexdigest() == command["stdout_sha256"], "native_stdout_pin")
        native = parse(out)
        need(native["ok"] is True and native["state"] == wanted, "native_lifecycle_response")
        if key == "start_receipt":
            need(native["host_pid"] == owner, "native_start_owner")
    need(len(scope["apps"]) == 46 and "local.pocket4.actions.v2" in scope["apps"], "initial_46_app_scope")
    original = read(root, "recovery/execute-r1-result.json")
    need(original["outcome_unknown"] is True and original["identity_qualified"] is False and original["ok"] is False, "original_R1_must_remain_UNKNOWN")
    return {
        "state": "R2_STOP_RETIRE_START_SUCCEEDED_ACTUAL_SUCCESSOR_IDENTITY_QUALIFIED",
        "job_id": R2_JOB, "evidence": pin(root, result_name), "terminal": pin(root, terminal_name),
        "runtime_epoch_sha256": epoch, "framework_epoch_sha256": value["framework_epoch_sha256"],
        "identity_qualified": True, "UI_or_install_runtime_admitted": False, "production_ready": False,
        "old_guard_runtime_usable": False, "per_app_explicit_scope_required": True,
        "original_R1_outcome_remains_unknown": True, "original_R1_replayed": False,
        "original_R2_pre_stop_six_role_pidfd_deaths": True, "intermediate_parent_pidfd_death": True,
        "both_predecessor_namespaces_empty": True, "all_46_app_bytes_and_data_identities_unchanged": True,
        "stop_commands": 1, "start_commands": 1, "exact_owned_init_signal_calls": 1,
        "sample_monotonic_ns": samples, "sample_span_seconds": (samples[-1] - samples[0]) / 1e9,
        "observation_fds": value["observation_fds"], "lease_fds": value["lease_fds"],
        "current_guard": value["current_guard"], "qualification": value["qualification"],
        "baseline": value["baseline"], "initial_app_scope": value["initial_app_scope"],
        "current_guard_local": pin(root, linked["current_guard"]),
        "wrapper_child_death_fix_activated": baseline["wrapper_child_death_fix_activated"],
        "framework_exit_cause_resolved": baseline["framework_exit_cause_resolved"],
        "future_runtime_stop_regression_proved": baseline["future_runtime_stop_regression_proved"],
        "native_framework_incarnation_fix_deployed": baseline["native_framework_incarnation_fix_deployed"],
        "source_artifacts": {k: pin(root, n) for k, n in linked.items()},
        "actual_owner_host_pid": owner, "actual_roles": {k: {"host_pid": v["host_pid"], "start_ticks": v["start_ticks"]} for k, v in roles.items()},
        "actual_initial_app_scope": scope,
    }


def successor_installations(root, recovery):
    entries, incomplete = [], []
    directory = root / "successor_install/actual"
    for child in sorted(directory.iterdir()) if directory.exists() else []:
        if not child.is_dir() or child.is_symlink():
            continue
        if child.name == "source-r2-controls":
            # The known host-test directory has no install request/result.
            # Its files are retained in the source/evidence checkpoint list.
            continue
        stdout_name = str((child / "stdout.raw.jsonl").relative_to(root))
        terminal_name = str((child / "terminal.raw.json").relative_to(root))
        if not (root / stdout_name).is_file() or not (root / terminal_name).is_file():
            incomplete.append({"directory": str(child.relative_to(root)), "state": "MISSING_COMPLETE_STDOUT_OR_TERMINAL_NOT_COUNTED"})
            continue
        lines = (root / stdout_name).read_bytes().splitlines()
        need(len(lines) == 2, "installer_request_stage_and_single_final_result")
        bootstrap, value = map(parse, lines)
        need(bootstrap["schema"] == "pocket4-explicit-install-request-stage-v1"
             and bootstrap["bootstrap_Main_actions"] == 0
             and bootstrap["bootstrap_FDs_after"] == bootstrap["bootstrap_FDs_before"], "install_bootstrap_host_only_and_FD_close")
        if value.get("schema") not in ("pocket4-successor-native-upgrade-result-v1", "pocket4-successor-install-entry-rejection-v1"):
            continue
        term = check_terminal(root, terminal_name, stdout_name)
        entries.append((value, term, stdout_name, terminal_name, bootstrap))
    entries.sort(key=lambda x: (x[0].get("started_utc", ""), x[1]["job_id"]))
    updates, attempts = {}, []
    initial = recovery["actual_initial_app_scope"]["apps"]
    current = copy.deepcopy(initial)
    owner = recovery["actual_owner_host_pid"]
    for value, term, stdout_name, terminal_name, bootstrap in entries:
        package = value.get("package")
        attempt = {"package": package, "job_id": term["job_id"], "evidence": pin(root, stdout_name),
                   "terminal": pin(root, terminal_name), "state": value.get("status", value["schema"]),
                   "action_attempted": value.get("action_attempted"), "outcome_unknown": value.get("outcome_unknown"),
                   "errors": value.get("errors", [value["error"]] if "error" in value else []),
                   "counted_as_upgrade": False}
        attempts.append(attempt)
        if value.get("install_verified") is not True:
            if value.get("action_attempted") is False:
                need(value.get("outcome_unknown") is False, "no_action_rejection_cannot_be_claimed_unknown")
                need(term["exit_code"] != 0 and term["state"] != "succeeded", "rejection_terminal_mismatch")
            continue
        need(term["state"] == "succeeded" and term["exit_code"] == 0, "install_success_requires_durable_success")
        need(value["schema"] == "pocket4-successor-native-upgrade-result-v1" and package in current, "install_package_outside_initial_scope")
        need(value["status"] == "INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING" and value["action_attempted"] is True
             and value["outcome_unknown"] is False and value["automatic_retry"] is False and value["errors"] == [], "installed_result_not_verified")
        for key in ("data_directory_identity_retained", "new_installed_bytes_readback_verified", "non_target_packages_unchanged", "native_artifacts_unchanged", "old_unknown_evidence_preserved"):
            need(value[key] is True, "install_missing_fact:" + key)
        need(value["business_ready"] is False and value["production_ready"] is False, "installation_is_not_business_PASS")
        for key in ("ADB_commands", "UI_actions", "permission_grants", "lifecycle_commands", "business_data_content_reads"):
            need(type(value[key]) is int and value[key] == 0, "unexpected_installer_action:" + key)
        need(value["worker_source"]["sha256"] in WORKERS, "unreviewed_installer_revision")
        need(matches(value["worker_source"], bootstrap["source"]), "install_source_chain")
        # The bootstrap pins original JSON bytes; Store.json reserializes the
        # same parsed request canonically. Their SHA may legitimately differ.
        request_name = str((root / stdout_name).parent.relative_to(root) / "request.private.json")
        if (root / request_name).is_file():
            need(matches(pin(root, request_name), bootstrap["request"]), "original_request_bytes_changed")
            request_bytes = canonical(read(root, request_name)) + b"\n"
            need(len(request_bytes) == value["request_artifact"]["bytes"]
                 and hashlib.sha256(request_bytes).hexdigest() == value["request_artifact"]["sha256"], "canonical_request_content_changed")
            attempt["original_and_canonical_request_verified_locally"] = True
        else:
            attempt["original_and_canonical_request_verified_locally"] = False
            attempt["request_original_reference"] = bootstrap["request"]
            attempt["request_canonical_reference"] = value["request_artifact"]
        for key in ("observation_fds", "lease_fds"):
            closed(value[key], key)
        guard = value["guard_before"]
        need(guard == value["guard_after"] and guard["schema"] == "pocket4-successor-main-guard-v1"
             and guard["runtime_epoch_sha256"] == recovery["runtime_epoch_sha256"]
             and guard["Main_epoch_sha256"] == recovery["framework_epoch_sha256"]
             and guard["baseline_sha256"] == recovery["baseline"]["sha256"], "install_guard_epoch_changed")
        need(guard["UI_or_install_runtime_admitted"] is False and guard["production_ready"] is False
             and guard["runtime_only_app_scopes_checked_separately"] is True, "blanket_admission_not_allowed")
        need(value["before"] == current[package], "install_chain_predecessor_bytes_or_identity_changed")
        after, before = value["after"], value["before"]
        need(after["package"] == package and after["uid"] == before["uid"]
             and after["version_code"] > before["version_code"]
             and after["package_manager_certificate_sha256"] == before["package_manager_certificate_sha256"]
             and after["data_directories"] == before["data_directories"], "install_UID_signer_data_or_version_chain")
        need(value["data_after"] == value["data_before"]
             and value["meituan_location_after"] == value["meituan_location_before"], "data_or_Meituan_location_changed")
        need(len(after["apks"]) == 1 and matches(after["apks"][0], value["private_candidate_apk"]), "installed_full_candidate_byte_mismatch")
        for key in ("native_before", "native_install_response"):
            need(value[key]["ok"] is True and value[key]["state"] == "running" and value[key]["host_pid"] == owner, "native_owner_changed")
        commands = value["commands"]
        installs = [c for c in commands if c["name"] == "native-install"]
        need(len(installs) == 1, "exactly_one_native_install")
        need(all(c["spawned"] is True and c["joined"] is True and c["returncode"] == 0
                 and c["timed_out"] is False and c["output_capture_complete"] is True for c in commands), "install_commands_not_complete")
        need(installs[0]["argv"][:6] == ["/usr/bin/droidloomctl", "--socket", "/run/droidloom/control.sock", "--json", "install", installs[0]["argv"][5]]
             and installs[0]["argv"][5].startswith("/proc/self/fd/") and installs[0]["argv"][6:] == ["--user", "0"], "normal_single_held_APK_install_argv")
        final = value["final_receipt"]
        original_result = {k: v for k, v in value.items() if k != "final_receipt"}
        final_bytes = canonical(original_result) + b"\n"
        need(len(final_bytes) == final["bytes"] and hashlib.sha256(final_bytes).hexdigest() == final["sha256"], "original_final_receipt_content_pin")
        if value["worker_source"]["sha256"] == "7fe3d12fd280539939c930970755e9f33ab7cda51f08a03cc54eb5f9c52508eb":
            need(value["previous_complete_APK_set_retained"] is True
                 and len(value["previous_apks_retained"]) == len(before["apks"]), "R2_complete_old_set_not_retained")
            retained = value["previous_apks_retained"]
            need([r["original"] for r in retained] == before["apks"]
                 and all(matches(r["retained"], r["original"]) for r in retained)
                 and len({r["retained"]["path"] for r in retained}) == len(retained)
                 and value["previous_complete_APK_set_bytes"] == sum(a["bytes"] for a in before["apks"]),
                 "R2_retained_old_set_bytes_or_identity_mismatch")
            manifest = value["complete_candidate_manifest"]
            need(manifest["schema"] == "pocket4-complete-single-apk-manifest-v1"
                 and all(manifest[k] is True for k in ("candidate_bytes_and_path_unchanged", "manifest_root_observed",
                     "split_marker_absent", "uses_split_element_absent", "feature_split_not_requested", "required_splits_not_requested"))
                 and manifest["Android_commands"] == 0
                 and matches(manifest["candidate"], value["private_candidate_apk"]), "R2_complete_candidate_proof_missing")
            attempt["retained_previous_APK_count"] = len(retained)
            attempt["retained_previous_APK_bytes"] = value["previous_complete_APK_set_bytes"]
            attempt["explicit_install_scope_schema"] = "pocket4-successor-explicit-install-scope-v2"
        else:
            need(len(before["apks"]) == 1 and matches(value["previous_apk_retained"], before["apks"][0]),
                 "R1_previous_APK_not_retained")
            attempt["retained_previous_APK_count"] = 1
            attempt["retained_previous_APK_bytes"] = before["apks"][0]["bytes"]
            attempt["explicit_install_scope_schema"] = "pocket4-successor-explicit-install-scope-v1"
        attempt["versioned_app_scope_reference"] = value["next_app_scope"]
        attempt["versioned_app_scope_schema"] = "pocket4-versioned-app-scope-v1"
        attempt["counted_as_upgrade"] = True
        updates[package] = {"evidence": pin(root, stdout_name), "terminal": pin(root, terminal_name),
                            "job_id": term["job_id"], "actual": value}
        current[package] = after
        scope_name = str((root / stdout_name).parent.relative_to(root) / "app-scope-after.private.json")
        if (root / scope_name).is_file():
            need(matches(pin(root, scope_name), value["next_app_scope"]), "saved_post_install_scope_pin_changed")
            saved_scope = read(root, scope_name)
            need(saved_scope["schema"] == "pocket4-versioned-app-scope-v1"
                 and saved_scope["runtime_epoch_sha256"] == recovery["runtime_epoch_sha256"]
                 and saved_scope["apps"] == current, "saved_post_install_scope_not_complete_current_chain")
            attempt["versioned_app_scope_locally_verified"] = pin(root, scope_name)
    return updates, attempts, incomplete, current


def additional_candidates(root):
    """Only real complete verifier reports; public store metadata is not promoted."""
    output = {}
    paths = set((root / "reference").rglob("*verification*.jsonl"))
    restored_s33 = root / "reference/official-s24-s33-restored/s33/stdout.raw.jsonl"
    if restored_s33.is_file():
        paths.add(restored_s33)
    for path in sorted(paths):
        if path.is_symlink():
            continue
        name = str(path.relative_to(root))
        terminal_name = name.replace("-verification.stdout.raw.jsonl", "-verification-terminal.raw.json")
        if path == restored_s33:
            terminal_name = str(path.parent.relative_to(root) / "terminal.raw.json")
        if terminal_name == name or not (root / terminal_name).is_file():
            continue
        term = check_terminal(root, terminal_name, name, "succeeded", 0)
        for line in path.read_bytes().splitlines():
            value = parse(line)
            if not isinstance(value, dict) or value.get("schema") != "pocket4-official-apk-verification-v1":
                continue
            if value.get("status") != "VERIFIED_OFFICIAL_CANDIDATE_NOT_INSTALLED":
                continue
            for key in ("signature_verified", "held_file_and_path_unchanged", "signer_matches_historical_installed_reference",
                        "strictly_newer_than_current_stored_version_reference", "matches_latest_observed_store_version"):
                need(value.get(key) is True, "candidate_missing_fact:" + key)
            need(value["manifest"]["package"] == value["package"] and value["claimed_latest_usable"] is False
                 and value["production_ready"] is False, "candidate_not_runtime_PASS")
            need(len(value["commands"]) == 2 and {c["name"] for c in value["commands"]} == {"apksigner", "aapt-badging"}
                 and all(c["joined"] is True and c["returncode"] == 0 and c["timed_out"] is False for c in value["commands"]), "candidate_verifier_not_complete")
            package = value["package"]
            row = {"evidence": pin(root, name), "actual": value, "terminal": pin(root, terminal_name), "job_id": term["job_id"]}
            if path == restored_s33:
                saved_name = str(path.parent.relative_to(root) / "result.json")
                need(read(root, saved_name) == value, "S33_saved_result_differs_from_durable_stdout")
                for command in value["commands"]:
                    for channel in ("stdout", "stderr"):
                        channel_name = str(path.parent.relative_to(root) / (command["name"] + "." + channel))
                        need(pin(root, channel_name)["sha256"] == command[channel + "_sha256"],
                             "S33_actual_verifier_stream_changed")
                row["saved_result"] = pin(root, saved_name)
            old = output.get(package)
            if old is None or value["manifest"]["version_code"] > old["actual"]["manifest"]["version_code"]:
                output[package] = row
            elif value["manifest"]["version_code"] == old["actual"]["manifest"]["version_code"]:
                need(matches(value["apk"], old["actual"]["apk"]), "same_version_candidate_byte_conflict")
    return output


def safe_additional_files(root):
    """Public source/metadata receipts only; never binaries or personal UI data."""
    prefixes = ("readiness_all_launcher", "successor_install", "successor_apk_audit",
                "recovery/compat_wrapper_repair", "recovery/independent_repair_r2",
                "recovery/lifecycle_independent_review", "reference/official-s22",
                "reference/official-s24-s33-restored")
    # These root-private files contain public process/package qualification metadata,
    # not credentials or UI/business data; preserving their exact bytes is necessary.
    public_private = {R2_PREFIX + n for n in ("baseline.private.json", "qualification.private.json",
        "initial-app-scope.private.json", "actual-transition.private.json", "retired-lifecycle.private.json",
        "wrapper-activation.private.json", "native-stop-receipt.private.json", "native-start-receipt.private.json")}
    # This exact filename is emitted by the reviewed installer and contains
    # package/process metadata only. The install parser validates its pin and
    # complete current App map before checkpoint construction reaches here.
    public_private.update(str(p.relative_to(root)) for p in
        (root / "successor_install/actual").glob("*/app-scope-after.private.json"))
    allowed_suffixes = {".py", ".rs", ".java", ".kt", ".json", ".jsonl", ".md", ".patch", ".diff", ".txt", ".sh", ".stderr", ".stdout"}
    files, excluded = [], []
    for prefix in prefixes:
        directory = root / prefix
        if not directory.is_dir():
            continue
        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue
            name = str(path.relative_to(root))
            lower = name.lower()
            private = ".private." in lower and name not in public_private
            secret_ui = re.search(r"(^|[/_.-])(screenshot|hierarchy|uitree|ui_tree|ui_dump|credential|token|secret)([/_.-]|$)", lower)
            binary = path.suffix.lower() not in allowed_suffixes and path.name != "AndroidManifest.xml"
            if path.is_symlink() or "__pycache__" in path.parts or private or secret_ui or binary:
                excluded.append(name)
                continue
            files.append(name)
    files += [n for n in ("checkpoint03_extension.py", "test_checkpoint03_extension.py", "CHECKPOINT03_LOCAL_TESTS.json") if (root / n).is_file()]
    for candidate in additional_candidates(root).values():
        files += [candidate["evidence"]["path"], candidate["terminal"]["path"]]
    return sorted(set(files)), sorted(set(excluded))


def enrich_status(root, status, candidates):
    recovery = successor_recovery(root)
    updates, attempts, incomplete, current_apps = successor_installations(root, recovery)
    extra_candidates = additional_candidates(root)
    candidates.update(extra_candidates)
    original_completed = {row["package"] for row in status["apps"] if "install_job_id" in row}
    initial_scope_ref = recovery["initial_app_scope"]
    for row in status["apps"]:
        package = row["package"]
        actual = current_apps[package]
        row.update(current_runtime_revalidated=True,
                   current_runtime_binding_scope="ACTUAL_R2_46_TARGET_SCOPE_PLUS_VALIDATED_SEQUENTIAL_INSTALL_RECEIPTS",
                   current_runtime_epoch_sha256=recovery["runtime_epoch_sha256"],
                   current_framework_epoch_sha256=recovery["framework_epoch_sha256"],
                   current_runtime_data_directories=actual["data_directories"],
                   current_runtime_apks=actual["apks"],
                   current_runtime_package_certificates=actual["package_manager_certificate_sha256"],
                   installed_version_code=actual["version_code"], uid=actual["uid"], code_path=actual["code_path"],
                   installed_observation_scope="CURRENT_QUALIFIED_RUNTIME_APP_SCOPE_NOT_FRESH_LAUNCHER_RESOLVER",
                   runtime_gate="CURRENT_IDENTITY_QUALIFIED_EXPLICIT_PER_APP_SCOPE_REQUIRED",
                   business_qa="UNKNOWN_NOT_RUN_IN_THIS_CHECKPOINT", production_ready=False, cleanup_eligible=False)
        row["r2_initial_scope_reference"] = initial_scope_ref
        if package in extra_candidates:
            c = extra_candidates[package]
            value = c["actual"]
            row["candidate"] = {
                "manifest": value["manifest"], "status": value["status"], "signature_verified": True,
                "signer_matches_historical_installed_reference": True, "matches_latest_observed_store_version": True,
                "evidence": c["evidence"], "terminal": c["terminal"], "apk": value["apk"]}
            row["upgrade_state"] = "VERIFIED_CANDIDATE_REQUIRES_EXPLICIT_CURRENT_SCOPE_INSTALL"
        if package in updates:
            update = updates[package]
            result, after = update["actual"], update["actual"]["after"]
            candidate = candidates.get(package, {}).get("actual", {})
            manifest = candidate.get("manifest", {})
            matched = (manifest.get("package") == package and manifest.get("version_code") == after["version_code"]
                       and candidate.get("signature_verified") is True
                       and isinstance(candidate.get("apk"), dict) and matches(candidate["apk"], after["apks"][0]))
            row.update(installed_version_name=manifest.get("version_name") if matched else None,
                version_name_authority="EXACT_VERIFIED_CANDIDATE_BYTES_EQUAL_CURRENT_INSTALL" if matched else "CURRENT_CODE_AND_APK_VERIFIED_VERSION_NAME_NOT_LOCALLY_RECOVERED",
                upgrade_state="INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING",
                installed_apk=after["apks"][0], data_directory_identity_retained=True,
                install_receipt=update["evidence"], install_terminal=update["terminal"],
                install_job_id=update["job_id"], install_finished_utc=result["ended_utc"],
                installed_observation_epoch_sha256=result["guard_after"]["Main_epoch_sha256"],
                data_directories=result["data_after"], install_outcome_unknown=False,
                install_observation_fds=result["observation_fds"], install_lease_fds=result["lease_fds"],
                install_action_lock_released=True, versioned_app_scope_after=result["next_app_scope"])
        if package == "tv.danmaku.bili":
            row["guest_accept_in_current_cell_authorized"] = False
            row["original_task873_launch_UNKNOWN_unchanged"] = True
        if package == "com.sankuai.meituan.takeoutnew":
            row["location_grants_authorized"] = False
            row["upgrade_state"] = "BLOCKED_OFFICIAL_SIGNER_DIFFERS_FROM_CURRENT_RESIGNED_APP"
    recovery_public = {k: v for k, v in recovery.items() if k != "actual_initial_app_scope"}
    status.update(schema="pocket4-all-launcher-progress-checkpoint-v3", checkpoint=3,
        scope="ALL_45_REFERENCE_LAUNCHERS_AWAITING_FRESH_COMPLETE_RESOLVER",
        runtime_epoch_sha256=recovery["runtime_epoch_sha256"],
        framework_epoch_sha256=recovery["framework_epoch_sha256"],
        last_qualified_runtime_epoch_sha256=recovery["framework_epoch_sha256"],
        current_runtime_identity_qualified=True, runtime_actions_frozen=False,
        UI_or_install_runtime_admitted=False, per_app_explicit_current_scope_required=True,
        current_runtime_repair_phase=recovery["state"],
        installed_and_verified_updates=len(original_completed | set(updates)),
        pre_successor_verified_upgrades=len(original_completed),
        successor_verified_upgrade_packages=len(updates),
        successor_successful_install_jobs=sum(a["counted_as_upgrade"] for a in attempts),
        successor_install_attempts=attempts, incomplete_successor_receipts=incomplete,
        native_recovery_r2=recovery_public,
        latest_verified_successor_workstream_candidates=sorted(set(extra_candidates) | ({"tv.danmaku.bili"} if "tv.danmaku.bili" in candidates else set())),
        whole_app_production_passes=0, production_ready_app_count=0,
        current_scope_warning="45 is the historical observed launcher catalogue; current complete MAIN/LAUNCHER resolver still required. 46 includes local.pocket4.actions.v2 and is not a 46-launcher claim.")
    status["native_recovery"]["historical_attempt_only"] = True
    status["independent_orphan_retirement"]["historical_attempt_only"] = True
    status["current_cell_readonly_observation"]["historical_intermediate_observation_only"] = True
    status["framework"].update(current_runtime_identity_qualified=True,
        framework_exit_cause_resolved=recovery["framework_exit_cause_resolved"],
        future_runtime_stop_regression_proved=recovery["future_runtime_stop_regression_proved"],
        native_framework_incarnation_fix_deployed=recovery["native_framework_incarnation_fix_deployed"],
        wrapper_child_death_fix_activated=True)
    status["qa_successor"]["historical_source_stage_only"] = True
    status["qa_current"] = {
        "current_runtime_identity_qualified": True, "helper_build_install_and_UI_scope_require_new_receipts": True,
        "business_qa": "UNKNOWN_NOT_RUN", "production_ready": False,
        "source_stage_reference": status["qa_successor"]["evidence"],
        "note": "Historical host Stage controls are not actual successor helper build/install/UI acceptance."}
    readiness = root / "readiness_all_launcher/SOURCE_PINS.json"
    if readiness.is_file():
        source = read(root, str(readiness.relative_to(root)))
        need(source["schema"] == "pocket4-all-launcher-readiness-source-closure-v1", "readiness_source_schema")
        for name, expected in source["files"].items():
            need(matches(pin(root, "readiness_all_launcher/" + name), expected), "readiness_source_changed:" + name)
        controls = read(root, "readiness_all_launcher/LOCAL_TEST_RESULT.json")
        pending = read(root, "readiness_all_launcher/CURRENT_STATE.json")
        need(controls["exit_code"] == 0 and controls["failures"] == controls["errors"] == controls["skipped"] == 0
             and controls["device_qa_executed"] is False, "readiness_local_controls_not_passing")
        need(pending["catalog_packages"] == 45 and pending["catalog_core_cases"] == 136 and pending["network_profiles"] == 12
             and pending["production_ready_app_count"] == 0 and pending["actions_executed"] == [], "UNKNOWN_template_scope_changed")
        status["readiness_all_launcher"] = {
            "source": pin(root, "readiness_all_launcher/SOURCE_PINS.json"),
            "local_tests": pin(root, "readiness_all_launcher/LOCAL_TEST_RESULT.json"),
            "template_state": pin(root, "readiness_all_launcher/CURRENT_STATE.json"),
            "packages": 45, "core_cases": 136, "network_profiles": 12,
            "local_boundary_tests_passed": controls["tests_run"],
            "device_qa_executed": False, "production_ready_app_count": 0,
            "entry": "readiness_all_launcher/evaluate_all.py", "frozen_original_eight_gate_preserved": True}
    return status


def installed_version_label(row):
    if row.get("installed_version_name"):
        return row["installed_version_name"]
    if "install_job_id" in row:
        return "未读新 manifest"
    if row.get("version_name_reference"):
        return "参考 " + str(row["version_name_reference"])
    return "未读取 manifest"


def render_report(status, rows):
    r2 = status["native_recovery_r2"]
    cases = status.get("readiness_all_launcher", {})
    failures = [a for a in status["successor_install_attempts"] if not a["counted_as_upgrade"]]
    failed = "; ".join(str(a["package"]) + ": " + str(a["state"]) for a in failures) or "无新增非成功安装回执"
    installed_rows = [a for a in status["apps"] if "install_job_id" in a]
    installs = "、".join(a["launcher_name"] + " " + installed_version_label(a) + " / " + str(a["installed_version_code"]) for a in installed_rows)
    return f"""# Pocket4 全 Launcher 升级检查点 03

记录时间：{status['generated_utc']}。任务尚未完成。

## 当前实际状态

已经有 **{status['installed_and_verified_updates']} 个不同 App 完成真实升级和字节读回**：{installs}。其中原正常运行 epoch 下完成 {status['pre_successor_verified_upgrades']} 项，新 successor 下有 {status['successor_successful_install_jobs']} 个已验证成功安装 job，覆盖 {status['successor_verified_upgrade_packages']} 个包。完整业务、长时、重启和故障恢复验收仍为 **0/45**，清理与回收空间均为 **0**。

这 45 包是历史已观察的 launcher 参考目录；当前 runtime 的完整 MAIN/LAUNCHER resolver 仍需实测。生命周期的 46 项 scope 包含 45 个参考 launcher 和 local.pocket4.actions.v2。不能据此把任务范围写成 46 个 launcher，或遗漏之后 resolver 新发现的包。当前 reDroid 已退役，没有可迁移旧 PASS 的新容器目标。

## 生命周期修复与新资格

原 native restart r1 的 job **1a1b0a21e45-fc05-71db** 保持 failed/UNKNOWN 原文。之后 exact orphan retirement 独立成功，只对旧 init 的精确 held pidfd 发一次信号，没有重写 r1 或补造它的原始 pidfd 证据。

新的独立 r2 **stop → 原六角色与中间 parent 退出 → 唯一 start → 新资格** 已实际成功，job **{r2['job_id']}** durable success / exit 0。旧/中间两个 namespace 两次均无成员；原 r2 pre-stop pidfd 证明六角色及 parent 死亡。两次 native 生命周期命令均正常结束，收据与实际新 owner **{r2['actual_owner_host_pid']}** 一致；精确 owned init 信号共 **1 次**。新进程、classpath、配置和 46 包 bytes/data 身份形成实际 successor baseline。3 次观测跨约 **{r2['sample_span_seconds']:.3f} 秒**，观察 FD **{r2['observation_fds']['closed']}/{r2['observation_fds']['acquired']}**、lease FD **{r2['lease_fds']['closed']}/{r2['lease_fds']['acquired']}** 全部关闭。

- Runtime epoch：`{r2['runtime_epoch_sha256']}`
- Framework epoch：`{r2['framework_epoch_sha256']}`
- 新 guard：`{r2['current_guard']['sha256']}`
- Qualification：`{r2['qualification']['sha256']}`
- Baseline：`{r2['baseline']['sha256']}`

修复后的 Python wrapper 已在真实新 lineage 激活，实际 unshare 参数是 `--kill-child=KILL`；同一源码的真实隔离 host PID namespace 控制证明 parent-death 链。报告未声称从生产 /proc 读得 PDEATHSIG。

当前仅 **identity_qualified=true**。真实 baseline 仍明确记录 framework_exit_cause_resolved={str(r2['framework_exit_cause_resolved']).lower()}、future_runtime_stop_regression_proved={str(r2['future_runtime_stop_regression_proved']).lower()}、native_framework_incarnation_fix_deployed={str(r2['native_framework_incarnation_fix_deployed']).lower()}，没有把短时资格当完整 framework 或长期稳定性验收。UI/install blanket admission 仍为 false；已成功的安装使用独立明确的当前 App scope。后续每项安装或 QA 都要新 scope 与实际 guard 校验。旧 epoch worker 和旧 guard 不可复用。

## 实际安装与候选

原四项升级的原始收据和终态保留；其 APK/data 身份在 r2 新 scope 中再次固定。新增安装逐项核对原始 bootstrap/final 两行 stdout、durable terminal、真实新 guard、安装前后 UID/签名/data 与完整候选字节、其他包不变、美团位置观察不变、正常 native install 只有一次，以及全部 FD 收口。successor_install/actual 下的新成功收据会由同一入口验证后累加，不按计划或口头数量增加。

未计入成功的实际记录：**{failed}**。无动作拒绝不会被计成升级，未来成功也不会改写该拒绝。任何执行后 UNKNOWN 仍单列保留。

本地已完整验签的 successor 候选工作集合：{', '.join(status['latest_verified_successor_workstream_candidates'])}。候选验证与成功安装分别记录；网页版本、国际商店 metadata 或下载未完成不升级为完整 APK 事实。尚未发现可取得且可安装的适用最新版时继续 UNKNOWN。

Bili 当前 Main 没有 Accept 授权，独立历史 cell p4-bili-m30-cell-20261010 的 guest Accept 不迁移；原 task873 launch UNKNOWN 原样保留。美团外卖不主动开启位置权限，现有重签名与正式发行方签名冲突继续阻断合法覆盖升级。商业完整性、正常签名/UID、合法账号和受控通信对端、真实硬件均须保留有效约束。

## 全量回归入口

原八包 evaluator/manifest 保持原字节。新增 `readiness_all_launcher/evaluate_all.py` 固定这些源并接入 **45 包 / 136 core case / 12 profile**；本地 **{cases.get('local_boundary_tests_passed', 0)} 项**边界控制通过，UNKNOWN 模板实际判定为 0 production。它只审阅提供的证据，没有执行设备 QA。

Fresh resolver 新增/缺失包、无效结构、旧 helper、缺账号/对端、缺硬件、N/A、短于3600秒、少于3次 App重启或适用故障恢复、Bili Accept、美团主动位置授权、完整性绕过等都阻断。离线/电话/Thread/IME 根据真实本地或服务契约取证，不硬填商业 App 的自有 DNS/TLS。3600秒与3/3次是本轮提出的下限，不是历史已通过事实。

已有 QA source Stage 4 项 host 文件控制保留。当前新 helper 的实际生成、构建、安装与逐包 UI 资格仍需独立实际回执；不把旧 Stage 测试或 source closure 当新的 helper/App PASS。

## 逐包当前记录

版本名有完整候选 bytes 对应时才继承其已验签 manifest；否则明确是历史参考或待读取。当前 UID/code/APK/data scope 经 r2 与后续成功安装链核对，仍未代替新的完整 launcher resolver 或业务回归。

| Launcher 名称 | 包名 | 已安装版本名 / code | 已取候选版本 | 状态 |
|---|---|---|---|---|
""" + "\n".join(rows) + """

## 复现、保留与清理

`python3 -B build_checkpoint.py` 只读取已有回执、原始字节和 source pins，再原子写出进度；不执行 Android、Git 或删除。nanosecond/monotonic 整数由 Python 原样解析。缺终态、日志不完整、版本/UID/数据/epoch不一致、出错或未知不会计入成功。

`GIT_CHECKPOINT_FILES_NEXT.json` 列出已有分支下一 checkpoint 的来源/配置/复现入口和公开元数据收据；排除 pycache、APK/二进制及私人 UI/凭据内容。root-private 命名的有限资格元数据按明确清单保留，不据文件名丢掉生命周期证据。此清单不提交 Git、不删除排除对象、不改冻结 manifest。

整个当前 launcher 集合、最终 framework、所有实际功能与长期/恢复检查达到 production ready 后，才进入已授权的旧 framework/App/实验/中间版本清理。当前没有执行该清理，回收 0 字节。最终保留可工作的源、精确 source-lock、配置/安全边界、实际包/签名/来源清单和复现/故障结算收据。
"""
