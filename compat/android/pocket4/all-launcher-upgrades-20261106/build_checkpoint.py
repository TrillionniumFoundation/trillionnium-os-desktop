#!/usr/bin/env python3
"""Build a factual checkpoint from recorded Pocket4 observations, never run Android.

Nested JSON is parsed by Python so nanosecond stat integers remain exact.
Missing execution receipts stay UNKNOWN. This is not the readiness auditor.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parent


def read(name):
    return json.loads((ROOT / name).read_text())


def pin(name):
    raw = (ROOT / name).read_bytes()
    return {"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def atomic_write(name, text):
    """Never truncate the prior checkpoint if this nearly-full volume rejects a write."""
    target = ROOT / name
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
        directory = os.open(target.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def terminal(name, job_id, state, exit_code):
    value = read(name)
    assert value["job_id"] == job_id and value["state"] == state and value["exit_code"] == exit_code
    assert all(value[key] is True for key in ("output_complete", "output_durable", "terminal_publication_confirmed"))
    assert value["automatic_retry"] is False and value["timed_out"] is False
    return {"evidence": pin(name), "actual": value}


def source_closure(prefix, manifest_name):
    """Validate frozen inputs without rewriting their manifest or receipts."""
    manifest = read(prefix + "/" + manifest_name)
    names = [prefix + "/" + manifest_name]
    for name, expected in manifest["files"].items():
        actual = pin(prefix + "/" + name)
        assert actual["bytes"] == expected["bytes"] and actual["sha256"] == expected["sha256"]
        names.append(actual["path"])
    return names


def completed_upgrades():
    index_name = "reference/completed-native-upgrades-20261106.json"
    index = read(index_name)
    assert index["schema"] == "pocket4-actual-native-upgrade-handoff-v1"
    assert index["production_ready"] is False and index["cleanup_performed"] is False
    inputs = {"com.lianjia.beike": "reference/beike-install-attempt3.json",
              "com.rytong.ceair": "reference/ceair-install-attempt1.json",
              "com.rytong.airchina": "reference/airchina-install-attempt1.json",
              "com.tencent.mm": "reference/wechat-install-attempt1.json"}
    assert {row["package"] for row in index["completed_installs"]} == set(inputs)
    updates = {}
    for row in index["completed_installs"]:
        name = inputs[row["package"]]
        wrapper = read(name)
        actual = wrapper["result"]
        assert wrapper["job_id"] == row["job_id"]
        assert actual["install_verified"] is True and actual["outcome_unknown"] is False and actual["errors"] == []
        assert actual["business_ready"] is False and actual["production_ready"] is False
        assert actual["data_directory_identity_retained"] is True and actual["action_lock_released"] is True
        assert actual["after"]["base_apk"] == row["installed_APK"]
        assert actual["after"]["target"]["version_code"] == row["version_code"]
        assert actual["after"]["target"]["uid"] == row["uid"]
        assert actual["after"]["target"]["code_path"] == row["code_path"]
        assert actual["data_after"] == row["data_directories"]
        assert actual["final_receipt"] == row["remote_final_receipt"]
        fds = actual["owned_descriptors_final"]
        assert fds["acquired"] == fds["closed"] and fds["remaining"] == 0 and fds["errors"] == []
        raw_name = row["raw_stdout"]["path"].removeprefix("pocket4_eight_apps/")
        raw_pin = pin(raw_name)
        assert all(raw_pin[key] == row["raw_stdout"][key] for key in ("bytes", "sha256"))
        assert json.loads((ROOT / raw_name).read_bytes().splitlines()[-1]) == actual
        term_name = row["terminal"]["path"].removeprefix("pocket4_eight_apps/")
        term = terminal(term_name, row["job_id"], "succeeded", 0)
        assert term["evidence"]["sha256"] == row["terminal"]["sha256"]
        updates[row["package"]] = {"evidence": pin(name), "job_id": row["job_id"],
                                   "actual": actual, "summary": row, "terminal": term["evidence"]}
    return updates, pin(index_name)


def qa_source_stage():
    name = "successor_qa/actual/stage-r2.stdout.raw.jsonl"
    lines = (ROOT / name).read_bytes().splitlines()
    assert len(lines) == 1
    value = json.loads(lines[0])
    assert value["ok"] is True and value["errors"] == [] and value["source_closure_readback_passed"] is True
    assert value["source_generation_executed"] is False and value["installs"] == value["UI_actions"] == 0
    report = value["root_stage_controls"]["report"]
    assert report["caller_uid"] == 0 and report["all_required_passed"] is True
    assert len(report["cases"]) == 4 and all(case["passed"] is True and case["skipped"] is False for case in report["cases"])
    assert report["root_positive_completed"] is True and report["total_fd_count_unchanged"] is True
    assert report["generated_successor_bindings"] == report["helper_installs"] == report["actual_android_paths_opened"] == 0
    closure = source_closure("successor_qa", "GENERATOR_PINS.json")
    assert pin("successor_qa/GENERATOR_PINS.json")["sha256"] == value["generator_manifest_sha256"]
    assert pin("successor_qa/stage-generator-r2-payload.json")["sha256"] == value["payload_sha256"]
    job = "1a1b09dad9f-fc05-71bb"
    term = terminal("successor_qa/actual/stage-r2-terminal.json", job, "succeeded", 0)
    return {"state": "R2_GENERATOR_SOURCE_DEPLOYED_HOST_STAGE_PASSED_NO_SUCCESSOR_BINDING_OR_HELPER_INSTALL",
        "job_id": job, "evidence": pin(name), "terminal": term["evidence"],
        "remote_source_root": value["root"], "remote_result": value["receipt"],
        "source_closure_readback_passed": True, "generator_manifest_sha256": value["generator_manifest_sha256"],
        "payload_sha256": value["payload_sha256"], "host_stage_tests_passed": 4,
        "host_stage_tests_skipped": 0, "host_stage_cases": report["cases"],
        "actual_host_root_file_tests": True, "host_fd_count_unchanged": True,
        "source_generation_executed": False, "generated_successor_bindings": 0,
        "helper_installs": 0, "actual_android_paths_opened": 0,
        "new_runtime_identity_qualified": False, "UI_or_install_runtime_admitted": False,
        "production_ready": False}, closure


def failed_native_recovery():
    name = "recovery/execute-r1-result.json"
    value = read(name)
    assert value["restart_attempted"] is True and value["preflight_passed"] is True
    assert value["ok"] is False and value["outcome_unknown"] is True and value["identity_qualified"] is False
    assert value["errors"] == [{"code": "OLD_CELL_OR_NATIVE_OWNER_STILL_ALIVE",
        "phase": "old_native_owner_pidfd_deaths", "type": "Rejected"}]
    for kind in ("observation_fds", "lease_fds"):
        row = value[kind]
        assert row["acquired"] == row["closed"] and row["remaining"] == 0 and row["errors"] == []
    job = "1a1b0a21e45-fc05-71db"
    term = terminal("recovery/execute-r1-terminal.json", job, "failed", 1)
    diag_name = "recovery/failed-r1-diagnostic.stdout.raw.json"
    diag = read(diag_name)
    assert diag["original_result"] == value and diag["outcome_unknown_rewritten"] is False
    assert diag["identity_qualified"] is False and not any(diag["optional_successor_files"].values())
    native = json.loads(diag["original_native_restart_receipt"]["stdout_utf8"])
    current_status = json.loads(diag["current_native_status"]["stdout"])
    assert native["ok"] is True and native["state"] == "running"
    init = diag["old_roles_actual_now"]["android_init"]
    assert init["same_original_identity"] is True and init["process_state"] == "S"
    assert init["new_observation_is_not_original_pidfd_evidence"] is True
    diag_term = terminal("recovery/failed-r1-diagnostic-terminal.json", "1a1b0a790e3-fc05-71f9", "succeeded", 0)
    targets = read("recovery/targets-45-plus-actions-reference.json")
    assert value["target_count"] == len(targets["packages"]) == 46
    return {"state": "RESTART_ATTEMPTED_UNKNOWN_OLD_CELL_OR_NATIVE_OWNER_STILL_ALIVE",
        "job_id": job, "evidence": pin(name), "terminal": term["evidence"],
        "restart_attempted": True, "restart_count": 1, "preflight_passed": True,
        "native_response": native, "native_response_is_not_identity_qualification": True,
        "failure": value["errors"][0], "outcome_unknown": True, "automatic_retry": False,
        "historical_unknown_results_preserved": value["historical_unknown_results_preserved"],
        "observation_fds": value["observation_fds"], "lease_fds": value["lease_fds"],
        "target_count": 46, "extra_nonlauncher_target": "local.pocket4.actions.v2",
        "old_guard_runtime_usable": False, "successor_identity_qualified": False,
        "successor_guard_published": False, "runtime_actions_frozen": True,
        "diagnostic": {"evidence": pin(diag_name), "terminal": diag_term["evidence"],
            "current_native_status": current_status, "current_status_is_not_qualified_identity": True,
            "old_android_init": {"host_pid": init["original"]["host_pid"],
                "start_ticks": init["original"]["start_ticks"], "same_original_identity": True,
                "process_state": "S", "new_observation_not_original_pidfd_proof": True},
            "other_old_roles_absent_in_this_read": sorted(role for role, row in diag["old_roles_actual_now"].items()
                if row.get("current") is None),
            "optional_successor_files_present": diag["optional_successor_files"],
            "original_unknown_preserved": True}, "production_ready": False}


def orphan_retirement():
    """A later independent success never rewrites the original failed restart."""
    name = "recovery/orphan-retirement-r1-result.json"
    value = read(name)
    raw_name = "recovery/orphan-retirement-r1.stdout.raw.json"
    raw = read(raw_name)
    assert raw["result"] == value
    assert all(raw["artifact"][key] == pin(name)[key] for key in ("bytes", "sha256"))
    assert value["ok"] is True and value["outcome_unknown"] is False and value["errors"] == []
    assert value["signal_attempted"] is True and value["restart_count"] == 0
    assert value["fresh_repair_pidfd_deaths"] == {"orphan_init": True, "orphan_parent": True}
    assert value["old_namespace_members_after"] == [] and value["non_target_processes_unchanged"] is True
    assert value["original_restart_result_unchanged"] is True and value["original_pre_restart_pidfd_evidence_recreated"] is False
    assert value["identity_qualified"] is False and value["guard_publication"] is False
    assert value["production_ready"] is False and value["automatic_retry"] is False
    for kind in ("observation_fds", "lease_fds"):
        row = value[kind]
        assert row["acquired"] == row["closed"] and row["remaining"] == 0 and row["errors"] == []
    packet_name = "recovery/retire-orphan-packet-r1.json"
    packet = read(packet_name)
    source_name = "recovery/retire_exact_orphan_r1.py"
    assert pin(source_name)["sha256"] == packet["source_sha256"]
    assert (ROOT / source_name).read_bytes() == packet["source_text"].encode()
    assert packet["source_text"].count("signal.pidfd_send_signal(") == 1
    lineage = json.loads(packet["lineage_text"])
    observed = lineage["observations"]
    new_launcher = observed["actual_native_receipt_owner"]["identity"]
    new_init = observed["diagnostic_android_init_0"]["identity"]
    assert (new_launcher["host_pid"], new_init["host_pid"]) == (2747275, 2747279)
    assert value["retired"]["android_init"]["host_pid"] == 3588093
    assert value["retired"]["orphan_unshare_parent"]["host_pid"] == 3588092
    job = "1a1b0b7efb4-fc05-7259"
    term = terminal("recovery/orphan-retirement-r1-terminal.json", job, "succeeded", 0)
    return {"state": "EXACT_OLD_ORPHAN_RETIRED_SUCCESSOR_IDENTITY_STILL_UNQUALIFIED", "job_id": job,
        "evidence": pin(name), "raw_stdout": pin(raw_name), "terminal": term["evidence"],
        "source": pin(source_name), "packet": pin(packet_name), "remote_result": raw["artifact"],
        "verified": True, "outcome_unknown": False, "signal_target": "held_pidfd_for_old_android_init_only",
        "signal": "SIGKILL", "signal_calls": 1, "restart_count": 0,
        "retired_old_init_host_pid": 3588093, "retired_old_parent_host_pid": 3588092,
        "fresh_repair_pidfd_deaths": value["fresh_repair_pidfd_deaths"], "old_pid_namespace_members_after": [],
        "new_launcher_host_pid": new_launcher["host_pid"], "new_init_host_pid": new_init["host_pid"],
        "new_launcher_new_init_daemon_presenter_unchanged": True,
        "observation_fds": value["observation_fds"], "lease_fds": value["lease_fds"],
        "original_restart_failed_unknown_unchanged": True, "original_pre_restart_pidfd_evidence_recreated": False,
        "new_guard_published": False, "identity_qualified": False, "production_ready": False}


def checkpoint_files(timestamp, qa_closure):
    groups = {
        "latest_verified_pending_candidates": [
            "reference/" + prefix + suffix
            for prefix in ("pdd-source-s6", "jd-source-s9", "taobao-source-s10")
            for suffix in ("-verification.stdout.raw.jsonl", "-verification-terminal.raw.json")],
        "actual_current_cell_readonly_observation": [
            "recovery/observe_current_cell_after_retirement_r1.py",
            "recovery/current-cell-after-retirement-r1.stdout.raw.json",
            "recovery/current-cell-after-retirement-r1-terminal.json"],
        "derived_checkpoint": ["build_checkpoint.py", "current_status.json", "CURRENT_STATUS.md",
            "app_test_catalog.json", "reference/checkpoint-git-receipt-01.json"],
        "four_actual_upgrades": ["reference/completed-native-upgrades-20261106.json", "collect_readonly.py"],
        "wechat_actual_before_and_scope": ["observe_wechat_before_r1.py", "deploy_wechat_before_readonly_r1.py",
            "reference/wechat-before-r1.json", "reference/wechat-before-r1.stdout.jsonl", "reference/wechat-before-r1-terminal.json"],
        "qa_r2_frozen_source_and_real_host_stage": qa_closure + ["successor_qa/stage_generator_r2.py",
            "successor_qa/check_owned_stage.py", "successor_qa/README.md", "successor_qa/source-origins.json",
            "successor_qa/r2-stage-target-fix.diff", "successor_qa/stage-generator-r2-payload.json",
            "successor_qa/actual/stage-r2.stdout.raw.jsonl", "successor_qa/actual/stage-r2-terminal.json"],
        "native_restart_unknown_and_readonly_diagnostic": source_closure("recovery", "SOURCE_PINS.json") + [
            "recovery/stage_execute_once.py", "recovery/execute-packet-r1.json", "recovery/execute-r1.stdout.raw.jsonl",
            "recovery/execute-r1-result.json", "recovery/execute-r1-terminal.json", "recovery/targets-45-plus-actions-reference.json",
            "recovery/failed-r1-diagnostic.stdout.raw.json", "recovery/failed-r1-diagnostic-terminal.json", "recovery/README.md"],
        "independent_exact_orphan_retirement": ["recovery/retire_exact_orphan_r1.py", "recovery/retire-orphan-packet-r1.json",
            "recovery/orphan-retirement-r1-result.json", "recovery/orphan-retirement-r1.stdout.raw.json",
            "recovery/orphan-retirement-r1-terminal.json", "recovery/orphan-r1-local-pidfd-control.json"]}
    for stem, revision, attempt in (("beike", 3, 3), ("ceair", 1, 1), ("airchina", 1, 1), ("wechat", 1, 1)):
        groups["four_actual_upgrades"] += [f"install_{stem}_bound_r{revision}.py", f"deploy_{stem}_bound_r{revision}.py",
            f"reference/{stem}-install-attempt{attempt}.json", f"reference/{stem}-install-r{revision}.stdout.jsonl",
            f"reference/{stem}-install-r{revision}-terminal.json", f"reference/{stem}-upgrade-verified-summary.json"]
    groups["four_actual_upgrades"] += ["reference/beike-official-verification.json", "reference/ceair-official-verification.json",
        "reference/launcher-candidate-verifications-r2.json", "reference/beike-native-ownership.stdout.json",
        "reference/beike-native-install-interface.stdout.json", "install_ceair_bound_r1.py.diff",
        "install_airchina_bound_r1.py.diff", "install_wechat_bound_r1.py.diff", "deploy_wechat_bound_r1.py.review.diff"]
    optional = ["recovery/failed-r1-lineage.stdout.raw.json", "recovery/failed-r1-lineage-terminal.json",
        "recovery/reference/actual-compat-unshare-r1.py", "recovery/reference/actual-m579-droidloomctl.rs",
        "successor_qa/reference/stage-r2-execution/stage-r2-stdout.raw.json",
        "successor_qa/reference/stage-r2-execution/stage-r2-status-raw.json"]
    groups["additional_existing_raw_receipts"] = [name for name in optional if (ROOT / name).exists()]
    files = [{**pin(name), "group": group} for group, names in groups.items() for name in sorted(set(names))]
    assert len({row["path"] for row in files}) == len(files)
    staging = Path("/dev/shm/pocket4-sidecar-next-20261106")
    external = []
    for name in ("audit_successor_apks.py", "test_audit_successor_apks.py", "AUDIT_PLAN.json",
                 "official-release-apk-digests.json", "request.example.json", "local-tests.stdout.txt", "SOURCE_PINS.json"):
        path = staging / name
        if path.exists():
            raw = path.read_bytes()
            external.append({"local_path": str(path), "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                "suggested_project_relative_path": "successor_apk_audit/" + name,
                "state": "PREPARED_LOCALLY_NOT_RUN_NOT_IMPORTED_BY_THIS_SCRIPT"})
    previous = read("reference/checkpoint-git-receipt-01.json")
    result = {"schema": "pocket4-next-git-checkpoint-file-list-v1", "generated_utc": timestamp,
        "state": "PREPARED_FOR_ROOT_NO_GIT_ACTION_PERFORMED", "not_a_runtime_source_manifest": True,
        "repository": previous["repository"], "branch": previous["branch"], "previous_recorded_commit": previous["commit"],
        "files": files, "file_count": len(files), "external_prepared_artifacts_for_root_to_include": external,
        "coordination_pending": [{"path": "recovery/NATIVE_RESTART_FINDINGS.md", "owner": "app_history",
            "instruction": "Include only after its owner freezes the report; this script neither reads nor writes it."}],
        "excluded_from_submission": ["APK binaries", "archives and redundant compressed transport payloads", "__pycache__ and .pyc"],
        "excluded_files_deleted": False, "frozen_manifests_and_receipts_modified": False, "git_commit_performed": False}
    atomic_write("GIT_CHECKPOINT_FILES_NEXT.json", json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return pin("GIT_CHECKPOINT_FILES_NEXT.json")


def main():
    inventory = read("reference/current-all-launcher-metadata.json")
    catalog = read("app_test_catalog.json")
    assert len(inventory["apps"]) == len(catalog["apps"]) == 45
    assert {a["package"] for a in inventory["apps"]} == {a["package"] for a in catalog["apps"]}
    eight = {a["package"]: a for a in read("reference/current-original-eight-inventory.json")["apps"]}
    updates, upgrade_index = completed_upgrades()
    qa, qa_closure = qa_source_stage()
    recovery = failed_native_recovery()
    retired_orphan = orphan_retirement()
    candidates = {}
    for name in ("reference/beike-official-verification.json", "reference/bilibili-official-verification.json",
                 "reference/ceair-official-verification.json"):
        raw = read(name)
        value = raw.get("actual_verifier_result", raw.get("result", raw))
        if isinstance(value, dict) and "package" in value:
            candidates[value["package"]] = {"evidence": pin(name), "actual": value}
    for value in read("reference/launcher-candidate-verifications-r2.json")["results"]:
        candidates[value["package"]] = {"evidence": pin("reference/launcher-candidate-verifications-r2.json"), "actual": value}
    for prefix, job in (("pdd-source-s6", "1a1b09f8b16-fc05-71c9"),
                        ("jd-source-s9", "1a1b0a1783b-fc05-71d3"),
                        ("taobao-source-s10", "1a1b0ba0bb6-fc05-7263")):
        name = "reference/" + prefix + "-verification.stdout.raw.jsonl"
        value = json.loads((ROOT / name).read_bytes().splitlines()[-1])
        term = terminal("reference/" + prefix + "-verification-terminal.raw.json", job, "succeeded", 0)
        assert value["status"] == "VERIFIED_OFFICIAL_CANDIDATE_NOT_INSTALLED"
        assert value["signature_verified"] is True and value["held_file_and_path_unchanged"] is True
        assert value["signer_matches_historical_installed_reference"] is True
        assert value["strictly_newer_than_current_stored_version_reference"] is True
        assert value["matches_latest_observed_store_version"] is True
        assert value["manifest"]["package"] == value["package"]
        assert all(row["joined"] and row["returncode"] == 0 and not row["timed_out"] for row in value["commands"])
        candidates[value["package"]] = {"evidence": pin(name), "actual": value, "terminal": term["evidence"]}
    for package, update in updates.items():
        candidate = candidates[package]["actual"]
        assert candidate["signature_verified"] is True
        assert candidate["manifest"]["package"] == package
        assert candidate["manifest"]["version_name"] == update["summary"]["version_name"]
        assert candidate["manifest"]["version_code"] == update["summary"]["version_code"]
        assert all(candidate["apk"][key] == update["actual"]["after"]["base_apk"][key] for key in ("bytes", "sha256"))
    apps = []
    for observed in sorted(inventory["apps"], key=lambda a: a["package"]):
        package = observed["package"]
        names = observed["launcher_entries"]
        historical = observed["historical_version_name_references"]
        row = {"package": package, "launcher_name": names[0]["name"],
               "launcher_components": [v["component"] for v in names],
               "uid": observed["uid"], "installed_version_code": observed["version_code"],
               "installed_version_name": None, "version_name_reference": next((h["version_name"] for h in historical if h.get("version_name")), None),
               "version_name_authority": "HISTORICAL_REFERENCE_ONLY_CURRENT_MANIFEST_NOT_READ",
               "code_path": observed["code_path"],
               "package_manager_certificates": observed["package_manager_signing"]["certificate_sha256"],
               "permission_observation": "SAVED_STATE_COLLECTED_EFFECTIVE_RUNTIME_STATE_UNKNOWN",
               "installed_observation_scope": "LAST_QUALIFIED_OBSERVATION_BEFORE_UNSETTLED_NATIVE_RESTART",
               "current_runtime_revalidated": False,
               "runtime_gate": "FROZEN_UNKNOWN_NATIVE_RESTART_NO_NEW_QUALIFIED_IDENTITY",
               "upgrade_state": "LATEST_USABLE_UNPROVEN", "business_qa": "UNKNOWN_NOT_RUN_IN_THIS_CHECKPOINT",
               "production_ready": False, "cleanup_eligible": False}
        if package in eight:
            row["original_eight_full_byte_observation"] = True
        if package in candidates:
            c = candidates[package]
            value = c["actual"]
            row["candidate"] = {"manifest": value.get("manifest"),
                "status": value.get("status"), "signature_verified": value.get("signature_verified", False),
                "signer_matches_historical_installed_reference": value.get("signer_matches_historical_installed_reference"),
                "matches_latest_observed_store_version": value.get("matches_latest_observed_store_version"),
                "evidence": c["evidence"]}
            row["upgrade_state"] = "CANDIDATE_OBSERVED_NOT_INSTALLED"
            if value.get("status") == "VERIFIED_OFFICIAL_CANDIDATE_NOT_INSTALLED":
                row["upgrade_state"] = "VERIFIED_NEW_CANDIDATE_AWAITING_NEW_RUNTIME_INSTALL"
                row["candidate"]["apk"] = value.get("apk")
                row["candidate"]["terminal"] = c.get("terminal")
            if value.get("status") == "VERIFICATION_FAILED":
                row["upgrade_state"] = "CANDIDATE_REJECTED"
                row["candidate"]["failure"] = value.get("error")
        if package == "com.sankuai.meituan.takeoutnew":
            row["upgrade_state"] = "BLOCKED_OFFICIAL_SIGNER_DIFFERS_FROM_CURRENT_RESIGNED_APP"
            row["location_grants_authorized"] = False
        if package == "tv.danmaku.bili":
            row["upgrade_state"] = "VERIFIED_CANDIDATE_PENDING_PRIOR_LAUNCH_UNKNOWN_SETTLEMENT"
            row["guest_accept_in_current_cell_authorized"] = False
        if package in updates:
            u = updates[package]
            result = u["actual"]
            after = result["after"]
            row.update(installed_version_code=after["target"]["version_code"],
                       installed_version_name=u["summary"]["version_name"],
                       version_name_authority="EXACT_VERIFIED_APK_HASH_READ_BACK_AFTER_NATIVE_INSTALL",
                       code_path=after["target"]["code_path"], upgrade_state="INSTALLED_AND_BYTE_VERIFIED_BUSINESS_QA_PENDING",
                       installed_apk=after["base_apk"], data_directory_identity_retained=True,
                       install_receipt=u["evidence"], install_terminal=u["terminal"],
                       install_job_id=u["job_id"], install_finished_utc=result["ended_utc"],
                       installed_observation_epoch_sha256=result["guard_after"]["Main_epoch_sha256"],
                       data_directories=result["data_after"],
                       install_outcome_unknown=False, install_descriptors=result["owned_descriptors_final"],
                       install_action_lock_released=True)
        apps.append(row)
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    cell_name = "recovery/current-cell-after-retirement-r1.stdout.raw.json"
    cell = read(cell_name)
    cell_term = terminal("recovery/current-cell-after-retirement-r1-terminal.json", "1a1b0b9ff7a-fc05-7262", "succeeded", 0)
    selected = []
    for sample in cell["observations"]:
        chosen = [dict(row) for row in sample["roles"] if row["cmdline"] in (
            ["/init", "second_stage"], ["zygote64"], ["system_server"], ["/system/bin/surfaceflinger"],
            ["/vendor/bin/hw/android.hardware.graphics.composer3-service.droidloom"])]
        for row in chosen:
            row.pop("state")
        assert len(chosen) == 5
        selected.append(chosen)
    assert selected[0] == selected[1] and cell["identity_qualified"] is False
    status = {"schema": "pocket4-all-launcher-progress-checkpoint-v2", "generated_utc": timestamp,
        "scope": "ALL_45_OBSERVED_NATIVE_LAUNCHER_PACKAGES",
        "catalog_current_android_resolver_proven": inventory["catalog"]["current_android_launcher_resolution_proven"],
        "last_qualified_observed_runtime": "Pocket4 DroidLoom Android 17, SDK 37, Android user 0",
        "runtime_epoch_sha256": None, "last_qualified_runtime_epoch_sha256": inventory["epoch_sha256"],
        "current_runtime_identity_qualified": False, "old_guard_runtime_usable": False,
        "runtime_actions_frozen": True,
        "current_runtime_repair_phase": "EXACT_OLD_ORPHAN_RETIRED_AWAITING_SUCCESSOR_QUALIFICATION",
        "redroid": "RETIRED_NO_CURRENT_TARGET_NO_NEW_TEST_COVERAGE",
        "inventory_source": pin("reference/current-all-launcher-metadata.json"),
        "test_catalog_source": pin("app_test_catalog.json"),
        "completed_upgrade_index": upgrade_index,
        "installed_and_verified_updates": len(updates), "whole_app_production_passes": 0,
        "production_ready_app_count": 0, "production_ready_app_denominator": 45,
        "test_cases_planned": sum(len(a["core_cases"]) for a in catalog["apps"]) if all("core_cases" in a for a in catalog["apps"]) else catalog["actual_summary"],
        "framework": {"provider_builder_compiled_and_qualified": True,
            "normal04_soong_launched": False, "normal04_stop": "FRESH_RAM_BELOW_UNCHANGED_15_GIB_ADMISSION",
            "mem_available_bytes": 15927521280, "required_bytes": 16106127360,
            "production_ready": False},
        "native_recovery": recovery,
        "independent_orphan_retirement": retired_orphan,
        "current_cell_readonly_observation": {"evidence": pin(cell_name), "terminal": cell_term["evidence"],
            "job_id": "1a1b0b9ff7a-fc05-7262", "five_android_roles_same_in_two_samples": True,
            "roles": selected[0], "owner": cell["expected_current_owner"],
            "identity_qualified": False, "guard_publication": False},
        "qa_successor": qa,
        "cleanup": {"eligible": False, "performed": False, "bytes_reclaimed": 0,
            "condition": "All current launcher Apps and final framework genuinely qualified; unresolved outcomes settled; final working source/configuration/reproduction manifest retained"},
        "apps": apps}
    atomic_write("current_status.json", json.dumps(status, ensure_ascii=False, indent=2) + "\n")
    rows = []
    for a in apps:
        name = a["installed_version_name"] or ("参考 " + str(a["version_name_reference"]) if a["version_name_reference"] else "未读取 manifest")
        candidate = a.get("candidate", {}).get("manifest") or {}
        rows.append(f'| {a["launcher_name"].replace("|", "/")} | `{a["package"]}` | {name} / {a["installed_version_code"]} | {candidate.get("version_name", "待核实")} | {a["upgrade_state"]} |')
    body = f'''# Pocket4 全 Launcher 升级检查点

记录时间：{timestamp}。这是实际进度检查点，任务尚未完成。

## 当前结论

已核对原生 Launcher 目录中的全部 **45 个包**，现有 **{len(updates)} 个 App 完成实际升级并读回验证**：贝壳 **3.06.71 / 3067100**、东航 **9.5.16 / 239**、国航 **7.53.0 / 75300**、微信 **8.0.80 / 3220**。完整业务与长时、重启、故障恢复验收仍为 **0/45**，旧版本清理及回收空间均为 **0**。

**单次正常原生 restart 已实际执行，其原始结果仍为 UNKNOWN。** `1a1b0a21e45-fc05-71db` 的 fresh preflight 通过，native 返回 `ok:true / running`；随后原始 pidfd 退出检查未能证明全部旧角色退出，记录 `OLD_CELL_OR_NATIVE_OWNER_STILL_ALIVE`，durable terminal 为 `failed / exit 1`。失败后的第一次只读观察见原 Android init PID **3588093**、start ticks **80797014**、状态 **S**，确认为原进程身份。

**随后独立的精确 orphan 退休已成功结算。** job `1a1b0b7efb4-fc05-7259` durable success / exit 0，只向 held pidfd 固定的旧 init 发送 **1 次 SIGKILL**；新的修复 pidfd 证明旧 init **3588093** 和旧 parent **3588092** 均退出，旧 PID namespace 成员为 **0**。new launcher **2747275**、new init **2747279**、daemon 与 presenter 的身份保持不变；6/6 观察 FD 和 104/104 lease FD 关闭。它的 `outcome_unknown=false`，没有再次 restart。该独立成功记录**不改写原 restart r1 的 failed/UNKNOWN，也不补造原始重启前 pidfd 证据**。新的合格 baseline/guard 仍未发布。

因此当前 runtime 操作继续冻结，**旧 guard 已不可再用于 runtime，旧 epoch 的安装、观察或 UI worker 不得复用**。native status 当前报告的新 host PID **2747275** 仅是状态回执，不构成完整身份资格。下列安装版本是最后已验证的实际安装记录，尚未获得重启后的新身份复验。

最后已核实的目标是 Pocket4 DroidLoom Android 17 / SDK 37 / user 0。历史 reDroid 已退役，没有当前容器目标，本轮没有重建它或迁移旧测试结论。重启前目录两次原生读取一致，但其缓存是否等同 Android MAIN/LAUNCHER resolver 尚未证明；须在合格的新身份下再枚举。

## 已有实际证据

- `reference/current-all-launcher-metadata.json`：45 包 PM 版本码、UID、代码路径、证书摘要和保存的权限记录；保存状态不冒充有效运行时授权。
- `reference/current-original-eight-inventory.json`：重启前原八包完整 APK 字节核对；之后的成功升级以各安装回执覆盖早期观察。
- `reference/completed-native-upgrades-20261106.json`：四项实际升级的完整交接索引。四项均有 durable success、完整原始输出和 terminal；新 APK 字节、UID 与数据目录核对通过，`install_verified=true / outcome_unknown=false`，各自 666/666 FD 关闭、锁释放。普通原八包升级比较其他七包；微信新增明确九包投影，完整比较原八包身份，没有修改旧 collector 的 HISTORY。美团位置保存观察不变，没有引入 ADB。
- `app_test_catalog.json`：全部 45 包、136 个具体核心 case；全部为 `UNKNOWN_NOT_RUN`。本地、电话/SMS、Thread、IME 与商业联网 App 各有实际适用路径，没有用 N/A 伪造网络通过。
- `framework_provider_repair/`：真实 provider 源修复，Rust builder 实编译及 16 个 focused tests 成功。normal04 的完整 Android/Soong 构建在实际内存准入前停止：15,927,521,280 B 小于固定 16,106,127,360 B 门限，未降低门限，也未把局部编译当作 framework 部署完成。
- `successor_qa/actual/stage-r2.stdout.raw.jsonl`：QA r2 **生成器源码闭包已在目标机部署并读回**，job `1a1b09dad9f-fc05-71bb` durable success。4 项实际 root host Stage 文件测试全部通过、没有跳过，总 FD 数不变；涵盖真实写入/读回、完整或 owner 拒绝、部分写入失败、读回失败时的三个 FD 收口。它们没有打开 Android 路径。实际 successor 绑定生成数 **0**、helper 安装数 **0**、UI 动作 **0**；source generation 未执行，不能视为新身份 QA 或 App 业务通过。
- `recovery/execute-r1-result.json` 与 `recovery/execute-r1-terminal.json`：一次原生 restart 的实际未知结果。907/907 观察 FD 和 104/104 lease FD 已关闭，剩余为 0；关闭 FD 不等于重启成功。恢复范围的 46 项是 45 个 Launcher 加 `local.pocket4.actions.v2`，不会把它写成 46 个 Launcher。
- `recovery/failed-r1-diagnostic.stdout.raw.json`：失败后的独立只读观察，没有发信号、重启、安装或 UI。旧 launcher、composer、zygote64、system_server、surfaceflinger 的原 PID 在该观察时已缺失，原 init 在当时仍存活；新观察不能代替原始 pidfd 的退出证据，也未改写原 UNKNOWN。
- `recovery/orphan-retirement-r1-result.json`、原始 stdout 和 terminal：随后独立的精确旧 orphan 退休。远端结果 **3043 B / SHA-256 `4c322a72ea61f3e7ff7e9c369c7996256beed8c74be1cd8c4b10524da285008d`**，目标进程退出与非目标进程身份保持已实际核对；这一步没有安装、UI、权限修改、namespace entry 或新 guard 发布。

## 不能略过的边界与失败

Bilibili 的历史 guest Accept 只适用于 `p4-bili-m30-cell-20261010`，当前 Main 不获得 Accept 授权。此前 task 873 的 native ownership 冲突与不确定 launch 回执原样保留；不按 task ID 删除或夺取所有权。美团外卖不得主动开启位置权限；它当前重签名 APK 与官方签名不一致，不能通过重签名、卸载丢数据或绕完整性检查强行升级。

京东最初取到的错包已保留为拒绝记录；随后通过官方动态入口取得 **16.1.50 / 102918**，完整下载与签名校验通过。拼多多 **8.30.0 / 83000**、淘宝 **10.69.0 / 866** 也已完成完整 APK 验签，均比历史已安装版本新、签名与历史 PM 参考一致。这三个新候选尚未安装，须在新的合格 runtime 下重新核对当前包身份。携程官方 metadata 是 **8.97.2**、公开下载入口实际 APK manifest 仍为 **8.94.6 / 2100**；抖音真实官方下载在 deadline 前未完成。国际商店登录、商业完整性、合法测试账号/受控通信对端或硬件缺口，需要真实条件才能验收。

旧 orphan 退休后的独立只读 job `1a1b0b9ff7a-fc05-7262` 已成功：当前 init、zygote、system_server、SurfaceFlinger 和 composer 在两个样本中身份一致。它没有执行 UI、安装或 namespace entry，也没有发布新 guard；这些短时观察不会被计作生产稳定性通过。

## 逐包状态

“参考”版本名来自历史 manifest，不冒充本轮刚读取的当前 manifest。版本码来自最后有身份资格的 PM 保存记录；四个成功安装行的版本与字节在各自安装结束时已实际读回。**所有行都尚未在此次未结算重启后的 runtime 重新验证**，完整业务回归仍待执行。

| Launcher 名称 | 包名 | 已安装版本名 / code | 已取候选版本 | 状态 |
|---|---|---|---|---|
''' + "\n".join(rows) + '''

## 复现和继续执行

`build_checkpoint.py` 只汇总已经存在的 JSON 回执，不运行 Android。它读取四项实际升级索引并逐项校验原始 stdout、terminal、安装字节和数据身份，读取 QA r2 的真实 host Stage 回执，并保持原失败恢复与诊断回执原样；大整数由 Python 直接解析。报告以临时文件完整写入并 fsync 后原子替换，避免空间不足时截断已有报告。

`GIT_CHECKPOINT_FILES_NEXT.json` 是交给 root 的下次 Git checkpoint 必要文件清单，记录实际文件哈希及现有前次 commit。生成清单不会提交 Git，也不会重写冻结 source manifest。另一个 agent 的 `recovery/NATIVE_RESTART_FINDINGS.md` 等待其本人冻结后再纳入，当前脚本不读写该文件。

全部 45 包的 APK manifest/完整签名审计源码仅在本地 `/dev/shm/pocket4-sidecar-next-20261106` 准备，并通过 8 项本地边界测试；未在目标机运行。其输入必须是真实新 typed guard 与同 runtime 的 versioned App scope。当前无合格 successor guard，不能启动该采集或借用旧资格。

`evaluate_readiness.py` 是离线证据审计器，当前 `regression_manifest.json` 的具体逐包策略仍只覆盖原八包；新 45 包适用性目录还需显式接入后才可作为最终审计入口，不能把模板当作已测结果。

所有升级、恢复和 QA worker 都按具体来源、版本、runtime 和单次操作绑定。成功回执是已经执行的记录；不能重新执行旧 flow 或改旧 PASS 的 PID、epoch、版本来伪造新授权。此次 restart 已有实际副作用及 UNKNOWN，不能自动重试或把事后 status、后续 orphan 退休改写成原步骤成功。精确 orphan 退休已独立结算，接下来仍需为新 runtime 建立实际的新资格和 App scope；细节见 `recovery/README.md`。

## 结束后的空间清理

用户已授权在最终可用版本验收之后删除所有旧 Android framework、旧 App、实验产物和中间构建。此检查点尚未达到条件，**没有执行旧版本清理，回收空间为 0**。最终保留可工作的源代码、精确 source-lock、当前配置、最终包/签名/来源清单、复现入口和轻量验收/故障结算回执。实际清理必须对待删路径逐一与正在运行、最后可用版本及未结算操作依赖核对，不用通配删除推测旧版本。
'''
    atomic_write("CURRENT_STATUS.md", body)
    file_list = checkpoint_files(timestamp, qa_closure)
    print(json.dumps({"apps": len(apps), "installed_updates": len(updates), "production_passes": 0,
                      "qa_host_stage_passes": qa["host_stage_tests_passed"],
                      "recovery_outcome_unknown": recovery["outcome_unknown"], "old_guard_runtime_usable": False,
                      "independent_orphan_retirement_verified": retired_orphan["verified"],
                      "cleanup_bytes": 0, "status": pin("current_status.json"),
                      "report": pin("CURRENT_STATUS.md"), "next_checkpoint_files": file_list}))


if __name__ == "__main__":
    main()
