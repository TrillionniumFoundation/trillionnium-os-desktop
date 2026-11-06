#!/usr/bin/env python3
"""Independent local check of original Calendar/Fcitx comparison evidence."""
import base64
import hashlib
import json
from pathlib import Path
import zlib

ROOT = Path(__file__).resolve().parent
PROJECT = ROOT.parents[2]
ACTUAL = PROJECT / "successor_audit_requests/diagnostics/calendar-official-aapt2-comparison-r1/actual"
B05 = PROJECT / "successor_audit_requests/actual/batches-final-r1/batch-05"
EMPTY = hashlib.sha256(b"").hexdigest()


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pin(path):
    raw = path.read_bytes()
    return {"path": str(path.relative_to(PROJECT)), "bytes": len(raw), "sha256": sha(raw)}


def main():
    worker_raw = (ACTUAL / "worker.stdout.original.json").read_bytes()
    assert (len(worker_raw), sha(worker_raw)) == (132387, "8e577c9e4a6eb77e6ad94e9993ca91aa97af958a4c02491237b32600dd6f4dfe")
    worker = json.loads(worker_raw)
    terminal = json.loads((ACTUAL / "status-1.original.txt").read_bytes())
    assert terminal["job_id"] == "1a1b26bfb80-fc05-7dfa" and terminal["state"] == "succeeded" and terminal["exit_code"] == 0
    assert all(terminal[k] is True for k in ("output_complete", "output_durable", "terminal_publication_confirmed"))
    assert all(terminal[k] is False for k in ("timed_out", "automatic_retry", "cancelled"))
    assert terminal["log_truncated"] == {"stdout": False, "stderr": False}
    assert terminal["log_errors"] == {"stdout": None, "stderr": None}
    stdout = (ACTUAL / "stdout.original.jsonl").read_bytes()
    assert len(stdout) == terminal["log_bytes"]["stdout"]["stored"] == terminal["log_bytes"]["stdout"]["seen"]
    assert (ACTUAL / "stderr.original.bin").read_bytes() == b""
    outer = json.loads(stdout.splitlines()[-1])
    assert outer == json.loads((ACTUAL / "outer.stdout.original.json").read_bytes())
    assert outer["ok"] is True and outer["errors"] == [] and outer["automatic_retry"] is False
    life = outer["child_lifecycle"]
    assert all(life[k] is True for k in ("pidfd_acquired", "pidfd_exit_observed", "pidfd_closed", "parent_descriptors_restored"))
    assert life["returncode"] == 0 and life["owned_child_sigkill_count"] == 0 and life["timeout"] is False and life["errors"] == []
    child = outer["child_result"]
    assert child["ok"] is True and child["errors"] == [] and child["worker_returncode"] == 0
    envelope_raw = child["worker_stdout_original"].encode()
    assert len(envelope_raw) == child["worker_stdout_bytes"] and sha(envelope_raw) == child["worker_stdout_sha256"]
    envelope = json.loads(envelope_raw)
    decoded = zlib.decompress(base64.b64decode(envelope["data"], validate=True))
    assert decoded == worker_raw and len(decoded) == envelope["artifact_bytes"] and sha(decoded) == envelope["artifact_sha256"]
    assert worker["guard_before"] == worker["guard_after"]
    assert worker["guard_before"]["runtime_epoch_sha256"] == "a7c7091a9e57eb6b373aa8a9225bb2f17b4ec0f1248679b56aaadc78eb0faca9"
    assert worker["packages"] == ["com.android.calendar", "org.fcitx.fcitx5.android"]
    assert all(worker[k] is True for k in ("snapshot_consistent", "all_primary_commands_succeeded",
        "all_manifests_and_signatures_verified", "all_tool_children_joined", "action_lock_released",
        "official_badging_stderr_empty", "official_layout_descriptors_closed", "comparison_complete",
        "same_APK_bytes_new_parser_succeeded", "observed_legacy_badging_failure_is_parser_dependent"))
    assert worker["all_commands_succeeded"] is False
    assert worker["original_failed_audit_reclassified"] is False and worker["original_batch_05_gate_advanced"] is False
    assert worker["resource_table_integrity_fully_proved"] is False and worker["production_ready"] is False
    assert worker["errors"] == [] and worker["unjoined_tool_pids"] == []
    fds = worker["owned_descriptors_final"]
    assert fds == {"acquired": 6399, "closed": 6399, "remaining": 0, "errors": []}
    assert worker["process_FDs_before"] == worker["process_FDs_after"] == 5
    assert worker["legacy_static_dependency_file_count"] == 19 and worker["official_static_dependency_file_count"] == 7
    scope_path = PROJECT / "successor_audit_requests/explicit47_scope_r2/actual-readback/app-scope.private.json"
    scope_raw = scope_path.read_bytes()
    assert (len(scope_raw), sha(scope_raw)) == (58854, "44f9ce783000a672c270e98afdaeb74bd79654508bfacae6793316ff4252e52f")
    scope = json.loads(scope_raw)
    commands = worker["commands"]
    assert len(commands) == 8
    assert [r["name"] for r in commands] == ["apksigner", "badging", "manifest", "legacy-badging"] * 2
    for row in commands:
        assert row["joined"] is True and row["pipes_closed"] is True and row["output_capture_complete"] is True
        assert row["timed_out"] is False and row["own_group_kill_requested"] is False
        expected = 1 if (row["package"], row["name"]) == ("com.android.calendar", "legacy-badging") else 0
        assert row["returncode"] == expected
        if row["name"] == "badging":
            assert row["stderr"]["bytes"] == 0 and row["stderr"]["sha256"] == EMPTY
    b05_raw = (B05 / "artifact.original.json").read_bytes()
    assert (len(b05_raw), sha(b05_raw)) == (108564, "e8fb751780f88ba3d79cb51f5975f5426d1cd6df586563d035824b3b69789d10")
    b05 = json.loads(b05_raw)
    bt = json.loads((B05 / "terminal.original.json").read_bytes())
    assert bt["job_id"] == "1a1b16f06d5-fc05-78b1" and bt["state"] == "failed" and bt["exit_code"] == 1
    failures = [r for r in b05["commands"] if r["returncode"] != 0]
    assert len(failures) == 1 and failures[0]["package"] == "com.android.calendar" and failures[0]["name"] == "badging"
    old_calendar = next(a for a in b05["apps"] if a["package"] == "com.android.calendar")
    observations = []
    raw_readback = []
    for app in worker["apps"]:
        reference = scope["apps"][app["package"]]
        assert app["uid"] == reference["uid"] and app["PM_version_code"] == reference["version_code"]
        assert app["data_directories"] == reference["data_directories"]
        assert all(app[k] is True for k in ("complete_APK_set_observed", "one_base_manifest_observed", "all_APKs_signature_verified",
                 "all_current_signers_equal_PM_records", "all_manifests_match_PM_identity", "all_permission_names_decoded"))
        assert len(app["apks"]) == len(reference["apks"]) == 1
        apk = app["apks"][0]
        scope_apk = reference["apks"][0]
        assert all(apk[k] == scope_apk[k] for k in ("path", "bytes", "sha256", "file"))
        assert apk["held_bytes_and_full_stat_and_path_unchanged"] is True
        assert apk["signature"]["verified"] is True and apk["signature"]["current_signers_equal_PM_certificate_record"] is True
        if app["package"] == "com.android.calendar":
            assert all(apk[k] == old_calendar["apks"][0][k] for k in ("path", "bytes", "sha256", "file"))
        assert app["base_manifest"]["min_sdk"] is None
        raw_readback += [r["stdout"] for r in commands if r["package"] == app["package"] and r["name"] in ("badging", "manifest")]
        observations.append({
            "package": app["package"], "uid": app["uid"], "version_code": app["PM_version_code"],
            "version_name": app["base_manifest"]["version_name"], "target_sdk": app["base_manifest"]["target_sdk"],
            "min_sdk": None, "min_sdk_status": "NOT_DECODED_BY_CURRENT_PARSER_RAW_READBACK_REQUIRED",
            "native_abis": app["base_manifest"]["native_abis"], "APK_bytes": apk["bytes"], "APK_sha256": apk["sha256"],
            "signers_equal_PM": True, "declared_permission_entry_count": len(apk["declared_permissions"]["entries"]),
            "effective_permission_grants": "UNKNOWN_NOT_QUERIED",
        })
    result = {
        "schema": "pocket4-independent-official-calendar-comparison-evidence-review-v1", "ok": True,
        "job_id": terminal["job_id"], "original_worker": pin(ACTUAL / "worker.stdout.original.json"),
        "original_stdout": pin(ACTUAL / "stdout.original.jsonl"), "original_terminal": pin(ACTUAL / "status-1.original.txt"),
        "original_b05": pin(B05 / "artifact.original.json"), "original_b05_terminal": pin(B05 / "terminal.original.json"),
        "actual_bound_package_count": 2, "scope_reference_package_count": 47,
        "all47_packages_reobserved_by_this_comparison": False, "observations": observations,
        "primary_commands_returncode_0": 6, "all_8_children_joined_and_pipes_closed": True,
        "legacy_badging_returncodes": worker["legacy_badging_returncodes"],
        "official_badging_both_stderr_empty": True, "owned_descriptors_final": fds,
        "process_FDs_before": 5, "process_FDs_after": 5, "outer_held_pidfd_and_parent_FDs_retired": True,
        "exact_same_calendar_APK_as_failed_b05": True,
        "inference": "The observed legacy badging failure depends on the parser for these exact APK bytes; the official tool completes with empty stderr.",
        "resource_table_integrity_fully_proved": False, "min_sdk_both_unknown_until_actual_raw_readback": True,
        "raw_readback_required": raw_readback,
        "original_b05_failed_exit1_preserved": True, "original_gate_still_STOP": True,
        "old_gate_failure": "AUTHORITATIVE_SUCCESSFUL_DURABLE_TERMINAL_REQUIRED",
        "diagnostic_does_not_satisfy_original_collector_source_or_command_count_or_all_commands_gate": True,
        "production_ready": False, "cleanup_eligible": False, "new_runtime_jobs_submitted": 0,
    }
    raw = (json.dumps(result, sort_keys=True, ensure_ascii=True, indent=2) + "\n").encode()
    with (ROOT / "ACTUAL_COMPARISON_REVIEW.json").open("xb") as handle:
        handle.write(raw)
    print(json.dumps({"ok": True, "result": pin(ROOT / "ACTUAL_COMPARISON_REVIEW.json")}, sort_keys=True))


if __name__ == "__main__":
    main()
