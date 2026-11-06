#!/usr/bin/env python3
"""Derive a local, evidence-only Launcher matrix. No target calls or gate claims.

Successful APK batches must pass the frozen original / linked audit gates. A
failed batch may contribute attributed raw observations, never a joint PASS.
This is a report generator, not a production-readiness or mutation admission.
"""
import sys
sys.dont_write_bytecode = True
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import stat
import types

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parent
GATE = "successor_audit_requests/revisions/linked-official-continuation-r2/linked_audit_gate.py"
GATE_SHA = "0befe9f69aa46608a6cec8505c1fed41cd8fca1f9045693c43a83dbb4fa00d8e"
PLAN = "successor_audit_requests/revisions/linked-official-continuation-r2/CONTINUATION_PLAN.json"
PLAN_SHA = "e26ff7e5c1739d2e30eab340df9072ab34a433362b9e8c869b905e25c1af18b3"
PM = "successor_audit_requests/current_services_r4/actual/worker.stdout.original.json"
PM_SHA = "185c6b0900aab78228e44788ea28b10d71c39cfeee8846fcb8c99c13a9f123fc"
INDEX = "successor_audit_requests/current_pm_resolver_index-r1/CURRENT_PM_RESOLVER_INDEX.json"
INDEX_SHA = "040cada7a27006c274d0632c965ab2ae21e0cf793fcb7110090ebd4972592f7d"
SCOPE = "successor_audit_requests/explicit47_scope_r2/actual-readback/app-scope.private.json"
SCOPE_SHA = "44f9ce783000a672c270e98afdaeb74bd79654508bfacae6793316ff4252e52f"
CATALOG_SHA = "d16a51f06be2b4ba2b5a61991dd649d481d1fdf53ff1ccf570ea23367611cb19"
HISTORY = "reference/current-all-launcher-metadata.json"
HISTORY_SHA = "daf3c5b81edcdd331b5e42149d088b88c51027e647583f91df588528ed5e5200"
OFFICIAL = "reference/remaining34-source-actions.json"
OFFICIAL_SHA = "7523031c7a1ef2e17d32d786512f8e06cfc39777f350a35b7987eededdfde6b4"
PERMISSIONS = "successor_audit_requests/beike_permission_pilot_r1/EFFECTIVE_PERMISSION_OBSERVATION.derived.json"
PERMISSIONS_SHA = "aec1bf7e8df82e73f87f7392bf42321a70633980798a7f2b370cd4fdb9dce47a"
EARLY = "reference/completed-native-upgrades-20261106.json"
EARLY_SHA = "7b96af788177cff0f26948da9de6e99e613012faf0cbaf2795b568e1057f9d41"
ORIGINAL_EIGHT = frozenset(("com.Hyatt.hyt", "com.enflick.android.TextNow", "com.lianjia.beike",
    "com.rytong.airchina", "com.rytong.ceair", "com.sankuai.meituan.takeoutnew", "com.szzc", "tv.danmaku.bili"))
SUCCESSOR_INSTALLS = ("pdd-01", "taobao-01", "didi-01", "ctrip-01", "bili-01", "jd-02", "douyin-01")
EMPTY_SHA = hashlib.sha256(b"").hexdigest()


def need(value, code):
    if not value:
        raise RuntimeError(code)


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def canonical(value):
    return json.dumps(value, ensure_ascii=True, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def document(raw):
    def pairs(rows):
        value = {}
        for key, item in rows:
            need(key not in value, "DUPLICATE_JSON_KEY")
            value[key] = item
        return value
    def bad_constant(value):
        raise RuntimeError("NONFINITE_JSON_NUMBER")
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=bad_constant)


class Inputs:
    """Only read explicit project paths. Recheck every consumed byte before publish."""
    def __init__(self, root=PROJECT):
        self.root = root.resolve()
        self.rows = {}

    def read(self, relative, digest=None, size=None, limit=4194304):
        p = Path(relative)
        need(not p.is_absolute() and all(x not in (".", "..") for x in p.parts), "LOCAL_RELATIVE_INPUT_ONLY")
        path = self.root / p
        need(path.resolve().is_relative_to(self.root), "INPUT_OUTSIDE_PROJECT")
        need("p4_private_ui" not in p.parts and not p.name.endswith("bundle.private.json"), "PRIVATE_UI_INPUT_PROHIBITED")
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            before = os.fstat(fd)
            need(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= limit, "INPUT_REGULAR_BOUNDED_FILE")
            chunks, count = [], 0
            while True:
                part = os.read(fd, min(65536, limit + 1 - count))
                if not part:
                    break
                chunks.append(part); count += len(part)
                need(count <= limit, "INPUT_SIZE_LIMIT")
            raw = b"".join(chunks)
            after = os.fstat(fd)
            need(before == after and path.stat(follow_symlinks=False) == after and len(raw) == before.st_size,
                 "INPUT_CHANGED_DURING_READ")
        finally:
            os.close(fd)
        need(digest is None or sha(raw) == digest, "INPUT_SHA256_MISMATCH:" + str(p))
        need(size is None or len(raw) == size, "INPUT_LENGTH_MISMATCH:" + str(p))
        row = {"path": p.as_posix(), "bytes": len(raw), "sha256": sha(raw)}
        need(str(p) not in self.rows or self.rows[str(p)] == row, "INPUT_CHANGED_WITHIN_SNAPSHOT")
        self.rows[str(p)] = row
        return raw

    def obj(self, path, digest=None, size=None):
        return document(self.read(path, digest, size))

    def ref(self, path):
        return dict(self.rows[str(path)])

    def recheck(self):
        for row in list(self.rows.values()):
            self.read(row["path"], row["sha256"], row["bytes"])


def load_module(raw, path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(raw, str(path), "exec"), module.__dict__)
    return module


def terminal(terminal_value, raw_stdout, state="succeeded", exit_code=0, job=None):
    need(type(terminal_value.get("job_id")) is str and (job is None or terminal_value["job_id"] == job), "EXACT_JOB_ID")
    need(terminal_value.get("state") == state and type(terminal_value.get("exit_code")) is int and
         terminal_value["exit_code"] == exit_code, "AUTHORITATIVE_TERMINAL_STATE")
    need(all(terminal_value.get(k) is True for k in ("output_complete", "output_durable", "terminal_publication_confirmed")),
         "DURABLE_COMPLETE_TERMINAL")
    need(all(terminal_value.get(k) is False for k in ("automatic_retry", "cancelled", "timed_out")), "NO_RETRY_CANCEL_TIMEOUT")
    need(terminal_value.get("log_truncated") == {"stderr": False, "stdout": False} and
         terminal_value.get("log_errors") == {"stderr": None, "stdout": None}, "COMPLETE_BOTH_LOG_STREAMS")
    need(terminal_value.get("log_bytes") == {"stdout": {"seen": len(raw_stdout), "stored": len(raw_stdout)},
         "stderr": {"seen": 0, "stored": 0}}, "EXACT_ORIGINAL_STDOUT_EMPTY_STDERR")


def fds_closed(row):
    need(type(row.get("acquired")) is int and row["acquired"] == row.get("closed") and row.get("remaining") == 0 and
         row.get("errors") == [], "ALL_OWNED_FDS_CLOSED")


def apk_bytes(apks):
    return sorted((a["path"], a["bytes"], a["sha256"]) for a in apks)


def same_current_app(app, scope):
    need(app["uid"] == scope["uid"] and app["PM_version_code"] == scope["version_code"] and
         app["code_path"] == scope["code_path"] and app["PM_certificate_sha256"] == scope["package_manager_certificate_sha256"] and
         app["data_directories"] == scope["data_directories"] and apk_bytes(app["apks"]) == apk_bytes(scope["apks"]),
         "AUDIT_PACKAGE_NOT_SAME_CURRENT_47_SCOPE")
    need(sorted((a["path"], a["file"]) for a in app["apks"]) == sorted((a["path"], a["file"]) for a in scope["apks"]),
         "AUDIT_FULL_APK_STAT_CHANGED")


def same_launcher_set(pm_packages, planned_packages):
    need(len(pm_packages) == len(set(pm_packages)) and set(pm_packages) == set(planned_packages),
         "FRESH_RESOLVER_ADDED_OR_MISSING_PACKAGE_REQUIRES_EXPLICIT_SCOPE_REVISION")


def pm_snapshot(inputs, catalog, scope, decoder):
    index = inputs.obj(INDEX, INDEX_SHA, 59367)
    raw = inputs.read(PM, PM_SHA, 79176)
    worker = document(raw)
    base = str(Path(PM).parent)
    outer_raw = inputs.read(base + "/stdout.original.jsonl")
    term = inputs.obj(base + "/status-1.original.txt")
    terminal(term, outer_raw, job=index["origin_job"])
    lines = outer_raw.splitlines()
    need(len(lines) == 2, "PM_ACTUAL_STAGE_AND_OWNED_OUTER")
    outer = document(lines[-1])
    child, lifetime = outer["child_result"], outer["child_lifecycle"]
    need(outer.get("ok") is True and outer.get("status") == "READONLY_OBSERVATION_AND_OWNED_LIFETIME_VERIFIED" and
         outer.get("errors") == [] and outer.get("library_FD_retired_by_original_held_owned_child_exit") is True and
         child.get("ok") is True and child.get("errors") == [] and child.get("worker_returncode") == 0 and
         child.get("frozen_descriptors_before_worker") == child.get("frozen_descriptors_after_worker") == child.get("final_descriptors") and
         all(lifetime.get(k) is True for k in ("pidfd_acquired", "pidfd_exit_observed", "pidfd_closed", "parent_descriptors_restored")) and
         lifetime.get("returncode") == 0 and lifetime.get("errors") == [] and lifetime.get("timeout") is False and
         lifetime.get("owned_child_sigkill_count") == 0, "PM_FULL_OWNED_LIFETIME_EVIDENCE")
    wire = child["worker_stdout_original"].encode()
    need(len(wire) == child["worker_stdout_bytes"] and sha(wire) == child["worker_stdout_sha256"] and
         decoder(wire)[1] == raw, "PM_ORIGINAL_WORKER_BYTES_IN_JOINT_OUTER")
    need(index["origin_worker_result"] == inputs.ref(PM), "PM_INDEX_MUST_BIND_ACTUAL_WORKER_BYTES")
    need(worker.get("ok") is True and worker.get("status") == "CURRENT_PM_AND_MAIN_LAUNCHER_OBSERVED" and
         worker.get("errors") == [] and worker.get("enumeration_samples_equal") is True and worker.get("current_scope_47_unchanged") is True,
         "ACTUAL_TWO_SAMPLE_PM_AND_RESOLVER_REQUIRED")
    need(worker["guard_before"] == worker["guard_after"] and worker["process_FDs_before"] == worker["process_FDs_after"], "PM_GUARD_AND_PROCESS_FDS")
    for key in ("lease_FDs_final", "observation_FDs_final", "owned_descriptors_final"):
        fds_closed(worker[key])
    rows = worker["MAIN_LAUNCHER_components"]
    by_package = {}
    for row in rows:
        by_package.setdefault(row["package"], []).append(row["component"])
    same_launcher_set(list(by_package), [a["package"] for a in catalog["apps"]])
    need(len(rows) == len(by_package) == 45 and index["current_MAIN_LAUNCHER_package_count"] == 45 and
         index["native_catalog_component_set_exactly_equals_framework_resolver"] is True and
         index["two_MAIN_LAUNCHER_samples_equal"] is True and index["two_PM_samples_equal"] is True,
         "EXACT_CURRENT_RESOLVER_COVERAGE")
    comparison = worker["catalog_comparison"]
    need(all(comparison[k] == [] for k in ("framework_only_components", "native_only_components",
         "native_packages_added_since_original45", "native_packages_missing_since_original45")), "NATIVE_FRAMEWORK_COMPONENT_SET_DIFFERENCE")
    metadata = {a["package"]: a for a in worker["installed_packages"]}
    need(len(metadata) == len(worker["installed_packages"]) == 205 and worker["app_scope_reference"]["sha256"] == SCOPE_SHA,
         "PM205_AND_EXPLICIT47_DIFFERENT_SCOPES_REQUIRED")
    index_rows = {a["package"]: a for a in index["launcher_apps"]}
    need(set(index_rows) == set(by_package), "INDEX_RESOLVER_PACKAGE_MISMATCH")
    for package, components in by_package.items():
        row, scoped, indexed = metadata[package], scope["apps"][package], index_rows[package]
        need(row["uids"] == [scoped["uid"]] == indexed["current_UIDs"] and
             row["version_code"] == scoped["version_code"] == indexed["current_version_code"] and
             sorted(components) == sorted(indexed["components"]), "PM_INDEX_UID_VERSION_COMPONENT_MISMATCH")
    return index, by_package, metadata, {"worker": inputs.ref(PM), "terminal": inputs.ref(base + "/status-1.original.txt"),
        "outer_stdout": inputs.ref(base + "/stdout.original.jsonl"), "derived_index": inputs.ref(INDEX)}


def failed_batch_observations(inputs, gate, g, row, request, scope, raw, term, submitted):
    """Attribute failure evidence. This intentionally cannot return a joint PASS."""
    terminal(term, raw, "failed", 1, submitted["job_id"])
    lines = raw.splitlines()
    need(len(lines) == 2, "FAILED_BATCH_TWO_ORIGINAL_LINES")
    stage, outer = (document(line) for line in lines)
    need(stage.get("source_stage_ok") is True and stage.get("source_root") == row["source_root"], "FAILED_BATCH_STAGE_REFERENCE")
    need(outer.get("ok") is False and outer.get("status") == "READONLY_OBSERVATION_OR_LIFETIME_INCOMPLETE_NO_RETRY" and
         outer.get("production_ready") is False and outer.get("old_results_reclassified") is False, "FAILED_BATCH_MUST_REMAIN_FAILED")
    child = outer["child_result"]
    worker_raw = child["worker_stdout_original"].encode()
    need(len(worker_raw) == child["worker_stdout_bytes"] and sha(worker_raw) == child["worker_stdout_sha256"], "FAILED_WORKER_EXACT_STREAM")
    value, artifact = g.decode_artifact(worker_raw)
    path = f"{gate.LEDGER}/batch-{row['batch']:02d}/artifact.original.json"
    need(inputs.read(path) == artifact and value["request"] == request and value["packages"] == row["packages"], "FAILED_ARTIFACT_REQUEST_BINDING")
    expected_source = {"path": row["output_root"] + "/collector-source.py", "bytes": row["collector"]["bytes"],
                       "sha256": row["collector"]["sha256"]}
    need(value["collector_source"] == expected_source and len(value["apps"]) == len(row["packages"]) and
         [a["package"] for a in value["apps"]] == row["packages"], "FAILED_COLLECTOR_EXACT_SCOPE")
    for app in value["apps"]:
        same_current_app(app, scope["apps"][app["package"]])
    need(value.get("all_manifests_and_signatures_verified") is False, "FAILED_PARTIAL_NOT_COMPLETE_AUDIT")
    publication = gate.result_file_gate(g, value, row["output_root"])
    lifecycle = outer["child_lifecycle"]
    return value, {"state": "FAILED_JOINT_GATE_RAW_OBSERVATIONS_ONLY", "batch": row["batch"],
        "job_id": submitted["job_id"], "joint_qualified": False, "artifact": inputs.ref(path),
        "original_worker_status": value.get("status"), "original_outer_status": outer["status"],
        "original_outer_errors": outer["errors"], "worker_returncode": child.get("worker_returncode"),
        "observed_owned_child_retirement": lifecycle,
        "observed_child_FDs_restored": child.get("frozen_descriptors_before_worker") == child.get("final_descriptors"),
        "observed_collector_owned_descriptors": value.get("owned_descriptors_final"),
        "individual_observations_do_not_qualify_the_batch": True, "original_final_receipt": publication}


def audits(inputs):
    gate_raw = inputs.read(GATE, GATE_SHA, 34438)
    gate = load_module(gate_raw, PROJECT / GATE, "matrix_frozen_linked_gate")
    inputs.read(PLAN, PLAN_SHA, 18179)
    g, plan, original, old_requests, scope, requests, wrappers = gate.load_plan(PROJECT / PLAN, PLAN_SHA)
    # Preserve the original reader semantics while inventorying every later read.
    original_read = g.read
    def tracked_read(path, maximum):
        raw = original_read(path, maximum)
        relative = Path(path).resolve().relative_to(PROJECT.resolve()).as_posix()
        need(inputs.read(relative, sha(raw), len(raw), maximum) == raw, "FROZEN_GATE_READ_CHANGED")
        return raw
    g.read = tracked_read
    # load_plan already verified these dependencies; record their exact bytes too.
    inputs.read(gate.GATE_FILE, gate.GATE_SHA, 15151)
    inputs.read((Path(gate.GATE_FILE).parent / "reference/audit_successor_apks.py").as_posix(), g.COLLECTOR_SHA, 29242)
    inputs.read(gate.ORIGINAL_PLAN, gate.ORIGINAL_PLAN_SHA, 17548)
    inputs.read(SCOPE, SCOPE_SHA, 58854)
    original_folder = Path(gate.ORIGINAL_PLAN).parent
    for row in original["batches"]:
        inputs.read((original_folder / row["local_request_file"]).as_posix(), row["request"]["sha256"], row["request"]["bytes"])
    for key in ("corrective_evidence", "original_failed_evidence"):
        for pin in plan[key]:
            inputs.read(pin["file"], pin["sha256"], pin["bytes"])
    here = Path(PLAN).parent
    inputs.read((here / plan["new_collector"]["file"]).as_posix(), plan["new_collector"]["sha256"], plan["new_collector"]["bytes"])
    for row in plan["batches"]:
        for local, pin in ((row["local_request_file"], row["request"]), (row["local_wrapper_file"], row["wrapper"]),
                           (row["stager"]["file"], row["stager"]), (row["process_request"]["file"], row["process_request"])):
            inputs.read((here / local).as_posix(), pin["sha256"], pin["bytes"])
    completed, correction = gate.check_preserved_history(g, plan, original, old_requests, scope)
    all_apps, batches = {}, []
    def add(value, detail):
        for app in value["apps"]:
            same_current_app(app, scope["apps"][app["package"]])
            need(app["package"] not in all_apps, "DUPLICATE_CURRENT_PACKAGE_AUDIT")
            all_apps[app["package"]] = (app, detail)
        batches.append(detail)
    for row, checked in zip(original["batches"][:4], completed):
        path = f"{gate.LEDGER}/batch-{row['batch']:02d}/artifact.original.json"
        value = inputs.obj(path, checked["artifact_sha256"], checked["artifact_bytes"])
        add(value, {**checked, "state": "FROZEN_ORIGINAL_JOINT_GATE_PASSED", "joint_qualified": True, "artifact": inputs.ref(path)})
    repair_path = gate.REPAIR + "/actual/worker.stdout.original.json"
    add(inputs.obj(repair_path, gate.REPAIR_WORKER_SHA), {"batch": 5, "job_id": gate.REPAIR_JOB,
        "state": "INDEPENDENT_CORRECTION_JOINT_GATE_PASSED_ORIGINAL_FAILED_PRESERVED", "joint_qualified": True,
        "artifact": inputs.ref(repair_path), "preserved_failure_and_correction": correction})
    stopped = False
    for row in plan["batches"]:
        n = row["batch"]
        folder = Path(gate.LEDGER) / f"batch-{n:02d}"
        required = ("submitted-job.json", "terminal.original.json", "stdout.original.jsonl", "artifact.original.json", "intent.json")
        if stopped or not all((PROJECT / folder / p).is_file() for p in required):
            batches.append({"batch": n, "state": "UNKNOWN_UNSETTLED_OR_NOT_ELIGIBLE_AFTER_STOP", "joint_qualified": False,
                            "packages": row["packages"], "evidence_absence_is_not_NA": True})
            stopped = True
            continue
        intent = inputs.obj((folder / "intent.json").as_posix())
        submitted = inputs.obj((folder / "submitted-job.json").as_posix())
        term_path, raw_path = (folder / "terminal.original.json").as_posix(), (folder / "stdout.original.jsonl").as_posix()
        term, raw = inputs.obj(term_path), inputs.read(raw_path)
        need(intent.get("schema") == "pocket4-original-ledger-linked-audit-intent-v1" and intent.get("batch") == n and
             intent.get("plan_sha256") == PLAN_SHA and intent.get("original_plan_sha256") == gate.ORIGINAL_PLAN_SHA and
             intent.get("corrective_job_id") == gate.REPAIR_JOB and intent.get("request") == row["request"] and
             intent.get("process_request") == row["process_request"] and intent.get("automatic_retry") is False and
             intent.get("idempotency_key") == row["suggested_new_idempotency_key"], "EXACT_LINKED_BATCH_INTENT")
        need(set(submitted) == {"job_id", "idempotency_key", "request_sha256", "plan_sha256", "original_plan_sha256", "corrective_job_id"} and
             submitted["idempotency_key"] == intent["idempotency_key"] and submitted["request_sha256"] == row["request"]["sha256"] and
             submitted["plan_sha256"] == PLAN_SHA and submitted["original_plan_sha256"] == gate.ORIGINAL_PLAN_SHA and
             submitted["corrective_job_id"] == gate.REPAIR_JOB, "EXACT_LINKED_BATCH_SUBMISSION")
        if term.get("state") == "failed":
            value, detail = failed_batch_observations(inputs, gate, g, row, requests[n], scope, raw, term, submitted)
            detail["terminal"], detail["outer_stdout"] = inputs.ref(term_path), inputs.ref(raw_path)
            add(value, detail); stopped = True
            continue
        files = [{"name": "owned_readonly_lifetime.py", **{k: row["wrapper"][k] for k in ("bytes", "sha256")}},
                 {"name": "audit_remaining_batches.py", **{k: row["collector"][k] for k in ("bytes", "sha256")}},
                 {"name": "request.review-only.json", **{k: row["request"][k] for k in ("bytes", "sha256")}}]
        value, artifact, outer = gate.owned_gate(g, raw, term, submitted["job_id"], wrappers[n], files, row["source_root"])
        path = (folder / "artifact.original.json").as_posix()
        need(inputs.read(path) == artifact, "DECODED_AUDIT_BYTES_MUST_EQUAL_ORIGINAL_ARTIFACT")
        receipt = gate.complete_apk_gate(g, value, requests[n], row["APK_count"], row["logical_APK_bytes"], scope, row["collector"], True)
        add(value, {"batch": n, "job_id": submitted["job_id"], "state": "FROZEN_LINKED_JOINT_GATE_PASSED",
            "joint_qualified": True, "artifact": inputs.ref(path), "terminal": inputs.ref(term_path),
            "outer_stdout": inputs.ref(raw_path), "final_receipt": receipt,
            "all_tool_children_joined": True, "original_child_pidfd_retirement_proved": True,
            "full_layout_observations_verified": 2 + 6 * row["APK_count"]})
    return all_apps, batches, scope, g.decode_artifact


def retained_set(before_apks, record):
    if "previous_apks_retained" in record:
        rows = record["previous_apks_retained"]
        need(apk_bytes([r["original"] for r in rows]) == apk_bytes(before_apks), "ALL_PREVIOUS_BASE_AND_SPLITS_REQUIRED")
        for row in rows:
            need(row["original"]["bytes"] == row["retained"]["bytes"] and row["original"]["sha256"] == row["retained"]["sha256"],
                 "RETAINED_OLD_APK_BYTES_CHANGED")
        return rows
    old = record.get("previous_apk_retained", record.get("preserved_previous_apk"))
    need(len(before_apks) == 1 and type(old) is dict and old["bytes"] == before_apks[0]["bytes"] and
         old["sha256"] == before_apks[0]["sha256"], "SINGLE_OLD_APK_ONLY_WHEN_FULL_OLD_SET_IS_ONE")
    return [{"original": before_apks[0], "retained": old}]


def install_common(value, term, raw, current, old_style):
    terminal(term, raw)
    need(value.get("errors") == [] and all(value.get(k) is True for k in ("action_attempted", "install_verified",
         "new_installed_bytes_readback_verified", "data_directory_identity_retained", "native_artifacts_unchanged")) and
         all(value.get(k) is False for k in ("automatic_retry", "outcome_unknown", "production_ready", "business_ready")),
         "INSTALL_NOT_A_COMPLETE_VERIFIED_SUCCESS")
    need(value["native_install_response"]["ok"] is True and value["data_before"] == value["data_after"], "NATIVE_SUCCESS_AND_DATA_RETENTION")
    native = [c for c in value["commands"] if c["name"] == "native-install"]
    need(len(native) == 1 and native[0]["returncode"] == 0 and native[0]["joined"] is True and
         native[0]["output_capture_complete"] is True and native[0]["timed_out"] is False, "ONE_NORMAL_COMPLETE_NATIVE_INSTALL")
    need(all(c["returncode"] == 0 and c["joined"] is True and c["timed_out"] is False and
         c["automatic_retry"] is False for c in value["commands"]), "INSTALL_ALL_TOOL_COMMANDS_SETTLED")
    if old_style:
        before, after = value["before"]["target"], value["after"]["target"]
        before_apks, after_apks = [value["before"]["base_apk"]], [value["after"]["base_apk"]]
        certificate = after["package_manager_signing"]["certificate_sha256"]
        need(certificate == before["package_manager_signing"]["certificate_sha256"] and
             value.get("native_install_response_confirmed") is True and value.get("action_lock_released") is True and
             value.get("prior_bili_unknown_preserved") is True and value.get("meituan_saved_location_observations_unchanged") is True and
             value.get("other_original_package_identity_unchanged") is True, "EARLY_INSTALL_AUTHORITY_AND_BOUNDARIES")
        fds_closed(value["owned_descriptors_final"])
        epoch = value["guard_after"].get("Main_epoch_sha256", value["guard_after"].get("epoch_sha256"))
    else:
        before, after = value["before"], value["after"]
        before_apks, after_apks = before["apks"], after["apks"]
        certificate = after["package_manager_certificate_sha256"]
        need(certificate == before["package_manager_certificate_sha256"] and value.get("non_target_packages_unchanged") is True and
             value.get("old_unknown_evidence_preserved") is True and value["guard_before"] == value["guard_after"] and
             value["meituan_location_before"] == value["meituan_location_after"], "SUCCESSOR_INSTALL_AUTHORITY_AND_BOUNDARIES")
        fds_closed(value["observation_fds"]); fds_closed(value["lease_fds"])
        epoch = value["guard_after"]["runtime_epoch_sha256"]
    need(before["package"] == after["package"] == value["package"] and before["uid"] == after["uid"] == current["uid"] and
         type(before["version_code"]) is int and after["version_code"] > before["version_code"] and
         after["version_code"] == current["version_code"] and after["code_path"] == current["code_path"] and
         certificate == current["package_manager_certificate_sha256"] and apk_bytes(after_apks) == apk_bytes(current["apks"]),
         "INSTALLED_BYTES_UID_SIGNER_CODE_MUST_MATCH_CURRENT_SCOPE")
    retained = retained_set(before_apks, value)
    return {"state": "INSTALLED_AND_CURRENT_BYTES_REOBSERVED_BUSINESS_QA_PENDING", "job_id": term["job_id"],
        "package": value["package"], "install_observation_epoch": epoch, "started_utc": value.get("started_utc"),
        "ended_utc": value.get("ended_utc"), "before_version_code": before["version_code"], "after_version_code": after["version_code"],
        "uid_retained": True, "data_directory_identity_retained_within_install": True,
        "after_APKs_equal_latest_bound_scope": True, "same_installed_signer_retained": True,
        "previous_APK_count_retained": len(retained), "previous_APK_bytes_retained": sum(r["original"]["bytes"] for r in retained),
        "previous_APKs_retained": retained, "official_verifier_reference": value["official_verifier"],
        "native_install_response": value["native_install_response"], "business_QA_qualified": False,
        "latest_usable_version_qualified": False, "original_result_status": value["status"]}


def installations(inputs, scope):
    result = {}
    early = inputs.obj(EARLY, EARLY_SHA, 18026)
    need(len(early["completed_installs"]) == 4 and early["production_ready"] is False, "FOUR_ORIGINAL_INSTALL_REFERENCES")
    for row in early["completed_installs"]:
        def relative(pin):
            need(pin["path"].startswith("pocket4_eight_apps/"), "EXACT_EARLY_PROJECT_PREFIX")
            return pin["path"][len("pocket4_eight_apps/"):]
        raw_path, term_path = relative(row["raw_stdout"]), relative(row["terminal"])
        raw = inputs.read(raw_path, row["raw_stdout"]["sha256"], row["raw_stdout"]["bytes"])
        term = inputs.obj(term_path, row["terminal"]["sha256"])
        lines = [document(line) for line in raw.splitlines()]
        need(len(lines) == 2 and term["job_id"] == row["job_id"], "EARLY_RAW_STAGE_PLUS_RESULT_AND_JOB")
        value = lines[-1]
        record = install_common(value, term, raw, scope["apps"][row["package"]], True)
        record["evidence"] = {"stdout": inputs.ref(raw_path), "terminal": inputs.ref(term_path), "historical_index": inputs.ref(EARLY)}
        result[row["package"]] = record
    for name in SUCCESSOR_INSTALLS:
        root = f"successor_install/actual/{name}"
        raw_path, term_path = root + "/stdout.raw.jsonl", root + "/terminal.raw.json"
        raw, term = inputs.read(raw_path), inputs.obj(term_path)
        rows = [document(line) for line in raw.splitlines()]
        need(len(rows) == 2, "SUCCESSOR_INSTALL_STAGE_PLUS_RESULT")
        value = rows[-1]
        need(value["package"] not in result, "INSTALL_NOT_DOUBLE_COUNTED")
        record = install_common(value, term, raw, scope["apps"][value["package"]], False)
        record["evidence"] = {"stdout": inputs.ref(raw_path), "terminal": inputs.ref(term_path)}
        result[value["package"]] = record
    need(len(result) == 11, "ALL_ELEVEN_UPGRADES_REQUIRE_ORIGINAL_TERMINAL_AND_BYTES")
    root = "successor_install/actual/jd-01"
    raw, term = inputs.read(root + "/stdout.raw.jsonl"), inputs.obj(root + "/terminal.raw.json")
    terminal(term, raw, "failed", 1)
    failed = document(raw.splitlines()[-1])
    need(failed.get("action_attempted") is False and failed.get("commands") == [] and failed.get("install_verified") is False,
         "JD_FIRST_REJECTION_MUST_NOT_BECOME_INSTALL")
    result["com.jingdong.app.mall"]["preserved_prior_failed_attempt"] = {"job_id": term["job_id"],
        "status": failed["status"], "errors": failed["errors"], "action_attempted": False,
        "stdout": inputs.ref(root + "/stdout.raw.jsonl"), "terminal": inputs.ref(root + "/terminal.raw.json")}
    return result


def current_manifest(app):
    if app is None or app.get("base_manifest") is None:
        return {"state": "UNKNOWN_MANIFEST_NOT_PARSED", "version_name": None, "version_code": None,
                "min_sdk": None, "target_sdk": None, "native_abis": None, "historical_name_substituted": False}
    value = dict(app["base_manifest"])
    value["native_abis_across_all_APKs"] = sorted({abi for apk in app["apks"] for abi in apk.get("manifest", {}).get("native_abis", [])})
    return {"state": "ACTUAL_INSTALLED_BASE_MANIFEST_PARSED", **value, "historical_name_substituted": False}


def permission_projection(app):
    if app is None:
        return {"state": "UNKNOWN_NOT_OBSERVED", "per_APK": [], "counts_by_tag": {}, "grant_inference_permitted": False}
    rows, counts = [], Counter()
    for apk in app["apks"]:
        declaration = apk.get("declared_permissions")
        need(type(declaration) is dict and declaration.get("declared_manifest_only") is True and
             declaration.get("effective_permission_grants") == "UNKNOWN_NOT_QUERIED", "DECLARATIONS_CANNOT_BE_GRANTS")
        entries = declaration.get("entries", [])
        for entry in entries:
            need(type(entry.get("name")) is str and entry.get("raw_name_preserved") is True, "PERMISSION_EXACT_NAME_REQUIRED")
            counts[entry["tag"]] += 1
        rows.append({"APK_path": apk["path"], "APK_sha256": apk["sha256"], "all_names_decoded": declaration["all_names_decoded"],
                     "entries": entries})
    return {"state": "MANIFEST_DECLARATIONS_OBSERVED", "per_APK": rows, "counts_by_tag": dict(sorted(counts.items())),
        "count_is_not_unique_PM_requested_or_effective_permissions": True, "grant_inference_permitted": False}


def unknown_permissions():
    return {"state": "UNKNOWN_NOT_QUERIED", "user": 0, "requested_permissions": None, "runtime_grants": None,
        "install_permissions": None, "AppOps": None, "roles": "UNKNOWN_NOT_QUERIED", "missing_does_not_mean_denied": True,
        "permission_behavior_recovery_qualified": False}


def effective_permissions(inputs, scope):
    value = inputs.obj(PERMISSIONS, PERMISSIONS_SHA, 23716)
    need(value["package"] == "com.lianjia.beike" and value["uid"] == scope["apps"][value["package"]]["uid"] and
         value["version_code"] == scope["apps"][value["package"]]["version_code"] and value["runtime_permission_user"] == 0 and
         value["permission_changes"] == 0 and value["new_runtime_queries_in_this_derivation"] == 0 and
         value["full_raw_PM_or_AppOps_content_published"] is False and value["usage_timestamps_published"] is False,
         "ACTUAL_SAME_PACKAGE_USER0_PUBLIC_PERMISSION_DERIVATIVE")
    rows = value["user0_runtime_permission_observations"]
    need(len(rows) == 15 and sum(r["granted"] is True for r in rows) == 1 and
         all(type(r["granted"]) is bool for r in rows), "EXACT_RUNTIME_GRANT_OBSERVATIONS")
    return {"state": "USER0_PM_AND_APPOPS_LITERAL_SNAPSHOT_OBSERVED", "user": 0, "uid": value["uid"],
        "observation_job": value["observation_job"], "private_readback_job": value["private_readback_job"],
        "requested_permissions": value["requested_permissions_verbatim_after_exact_six_space_format_prefix"],
        "noncanonical_names_preserved": value["noncanonical_leading_whitespace_names_preserved"],
        "runtime_grants": rows, "install_permissions": value["install_permission_observations"],
        "AppOps": value["AppOps_reported_modes"], "roles": value["role_status"], "counts": value["counts"],
        "source": inputs.ref(PERMISSIONS), "limits": value["limits"], "missing_does_not_mean_denied": True,
        "user_denial_cause_not_inferred_from_false_grant": True, "permission_behavior_recovery_qualified": False}


def official_references(inputs, scope):
    matrix = inputs.obj(OFFICIAL, OFFICIAL_SHA, 259476)
    result = {}
    for row in matrix["apps"]:
        source = row["official_source"]
        package = row["package"]
        record = {"state": "PRIOR_OFFICIAL_SOURCE_REFERENCE_NOT_CURRENT_USABILITY_PROOF", "source_matrix": inputs.ref(OFFICIAL),
            "reference": source, "latest_usable_business_qualified": False}
        if type(source) is dict and type(source.get("evidence_ref")) is dict:
            pin = source["evidence_ref"]
            available = (PROJECT / pin["path"]).is_file()
            record["raw_prior_evidence_locally_available"] = available
            if available:
                inputs.read(pin["path"], pin["sha256"], pin["bytes"])
                record["raw_prior_evidence"] = inputs.ref(pin["path"])
            else:
                record["raw_prior_evidence_status"] = "UNAVAILABLE_LOCALLY_REFERENCE_RETAINED_NOT_RETRIEVED"
        if package in ("com.google.android.gms", "org.fcitx.fcitx5.android"):
            asset = source["asset"]
            need(asset["digest"].startswith("sha256:") and len(scope["apps"][package]["apks"]) == 1, "SINGLE_OFFICIAL_RELEASE_ASSET")
            actual = scope["apps"][package]["apks"][0]
            need(actual["bytes"] == asset["size"] and actual["sha256"] == asset["digest"][7:], "CURRENT_OFFICIAL_REFERENCE_BYTE_IDENTITY")
            record.update(state="CURRENT_APK_BYTE_IDENTICAL_TO_PRIOR_OFFICIAL_RELEASE_REFERENCE", byte_identity_rechecked_locally=True,
                          install_performed_for_this_match=False, latest_release_requeried_now=False)
        if package == "com.sankuai.meituan.takeoutnew":
            need(source["current_signer_matches"] is False and source["signer_certificate_sha256"] !=
                 scope["apps"][package]["package_manager_certificate_sha256"], "MEITUAN_SIGNER_CONFLICT_MUST_REMAIN_BLOCKED")
            record.update(state="BLOCKED_CANDIDATE_SIGNER_MISMATCH", current_PM_signer_sha256=scope["apps"][package]["package_manager_certificate_sha256"],
                          signature_or_integrity_bypass_permitted=False, proactive_location_grant_permitted=False,
                          candidate_is_not_latest_observed_store_version=True)
        result[package] = record
    return result


def beike_runtime_evidence(inputs):
    # These are already-public protocol/terminal summaries, never raw UI trees.
    specs = [
        ("owned_new_session_r1/actual-launch", "stdout.original.jsonl", "status-1.original.txt", "NATIVE_OWNED_TASK_LAUNCH_OBSERVED", "succeeded", 0),
        ("reusable_owned_ui_r1/actual-inspect-01", "stdout.original.jsonl", "status-1.original.txt", "READONLY_HELPER_INSPECTION_OBSERVED", "succeeded", 0),
        ("explore_home_search_case_r1/actual", "stdout.original.jsonl", "status-02.original.txt", "PARTIAL_CASE_FAILED_UNKNOWN_RETAINED", "failed", 1),
        ("inspect_after_search_rejection_r1/actual", "stdout.original.json", "status-01.original.txt", "INDEPENDENT_READONLY_OBSERVATION_AFTER_REJECTION", "succeeded", 0),
    ]
    records = []
    for folder, stdout_name, terminal_name, state, term_state, code in specs:
        base = "successor_qa/" + folder
        # Actual filename is pinned by this reviewed table; absence is not success.
        raw_path, term_path = base + "/" + stdout_name, base + "/" + terminal_name
        raw, term = inputs.read(raw_path), inputs.obj(term_path)
        terminal(term, raw, term_state, code)
        records.append({"state": state, "job_id": term["job_id"], "stdout": inputs.ref(raw_path), "terminal": inputs.ref(term_path),
            "does_not_qualify_core_business_or_login": True})
    reader = "successor_qa/case_failure_reader_r1/actual-public/stdout.original.json"
    raw = inputs.read(reader, "49adfc22a9aa4a35d810835534ca578282d1d76fd38a862d480f59651fc6b0b2", 34515)
    observed = document(raw)
    need(observed.get("ok") is True and observed.get("diagnosis_completed") is True and
         observed.get("old_UNKNOWN_modified") is False and observed.get("original_case_success") is False and
         observed.get("current_action_authority") is False and observed.get("whole_process_fd_identities_unchanged") is True and
         observed["diagnosis"].get("failure_remains_unknown") is True and
         observed["diagnosis"].get("all_recorded_commands_normal_zero_joined") is True and
         observed["diagnosis"].get("all_recorded_transports_verified") is True, "ACTUAL_CASE_DIAGNOSIS_MUST_KEEP_FAILURE")
    # The reader's public summary, already reviewed by root, is cited without UI.
    records.append({"state": "FIXED_FAILED_CASE_EVIDENCE_READER_COMPLETED", "source": inputs.ref(reader),
        "fact": "Step 0 close has an independent successful postcondition; step 1 helper rejected INSPECTED_TREE_OR_WINDOW_CHANGED before dispatch. The case remains FAILED and outcome_unknown=true.",
        "no_hash_field_cause_inferred": True, "no_replay_or_new_action_authority": True})
    return records


def summarize_apk(apk):
    return {key: apk[key] for key in ("path", "bytes", "sha256", "file", "signature", "parse_errors",
        "held_bytes_and_full_stat_and_path_unchanged") if key in apk} | {
        "manifest": apk.get("manifest"), "manifest_matches_PM_package_and_version": apk.get("manifest_matches_PM_package_and_version"),
        "command_evidence": [{key: c.get(key) for key in ("name", "returncode", "joined", "output_capture_complete", "timed_out",
            "started_utc", "ended_utc", "stdout", "stderr")} for c in apk["commands"]]}


def build(inputs):
    catalog = inputs.obj("app_test_catalog.json", CATALOG_SHA, 624217)
    all_audits, batches, scope, decoder = audits(inputs)
    need(len(scope["apps"]) == 47, "EXPLICIT47_NOT_205_FULL_APK_BINDINGS")
    index, components, pm, pm_refs = pm_snapshot(inputs, catalog, scope, decoder)
    need(set(all_audits) <= set(components), "AUDIT_OUTSIDE_CURRENT_RESOLVER")
    installs = installations(inputs, scope)
    history = {r["package"]: r for r in inputs.obj(HISTORY, HISTORY_SHA, 287909)["apps"]}
    official = official_references(inputs, scope)
    beike_permissions = effective_permissions(inputs, scope)
    beike_runtime = beike_runtime_evidence(inputs)
    apps = []
    for planned in sorted(catalog["apps"], key=lambda a: a["package"]):
        package = planned["package"]
        observed, batch = all_audits.get(package, (None, None))
        qualified = bool(batch and batch["joint_qualified"])
        scoped = scope["apps"][package]
        runtime_domains = {name: {"state": "UNKNOWN_NOT_QUALIFIED", "evidence_refs": [], "missing_is_not_NA": True}
                           for name in planned["actual_domain_coverage"]}
        failures = []
        if batch and not qualified:
            failures.append({"state": "FAILED_BATCH_JOINT_GATE", "batch": batch["batch"], "job_id": batch["job_id"],
                "individual_parse_errors": [e for apk in observed["apks"] for e in apk.get("parse_errors", [])],
                "individual_signature_success_is_not_complete_package_audit": True})
        if package == "com.lianjia.beike":
            runtime_domains["startup"]["narrow_actual_observations"] = beike_runtime[:2]
            runtime_domains["core"]["narrow_actual_observations"] = beike_runtime[2:]
            runtime_domains["permissions"]["narrow_actual_observation"] = beike_permissions["source"]
            failures.append({"state": "PARTIAL_CASE_FAILED_UNKNOWN_RETAINED", "reason": "INSPECTED_TREE_OR_WINDOW_CHANGED",
                "second_action_attempted": False, "first_action_independent_postcondition_observed": True,
                "overall_outcome_unknown_preserved": True, "source": beike_runtime[-1]["source"]})
        if package == "com.sankuai.meituan.takeoutnew":
            failures.append({"state": "UPGRADE_BLOCKED_SIGNER_MISMATCH", "source": inputs.ref(OFFICIAL),
                             "no_proactive_location_grant": True, "no_uninstall_or_signature_bypass": True})
        declared = permission_projection(observed)
        apps.append({"package": package, "label_reference": planned["launcher_name_observed"],
            "label_is_prior_observed_not_fresh_label_parse": True, "original_eight": package in ORIGINAL_EIGHT,
            "classification": planned["classification"], "current_MAIN_LAUNCHER_components": sorted(components[package]),
            "current_PM": {"user": 0, "UIDs": pm[package]["uids"], "version_code": pm[package]["version_code"],
                "evidence": pm_refs["worker"]}, "bound_APK_and_data_identity": scoped,
            "APK_audit": {"state": "JOINT_AUDIT_PASSED" if qualified else "FAILED_JOINT_AUDIT_WITH_ATTRIBUTED_OBSERVATIONS" if batch else "UNKNOWN_NOT_OBSERVED",
                "joint_qualified": qualified, "batch": batch, "current_manifest": current_manifest(observed),
                "APK_count": len(scoped["apks"]), "APK_bytes": sum(a["bytes"] for a in scoped["apks"]),
                "APKs": [] if observed is None else [summarize_apk(a) for a in observed["apks"]],
                "PM_signer_equality_is_not_independent_vendor_source_trust": True,
                "resource_table_integrity_fully_proved": False, "runtime_integrity_checks_bypassed": False},
            "historical_version_references": history[package].get("historical_version_name_references", []),
            "historical_version_reference_source": inputs.ref(HISTORY),
            "upgrade": installs.get(package, {"state": "NO_COMPLETED_UPGRADE_IN_THIS_ROUND", "latest_usable_version_qualified": False}),
            "official_source": official.get(package, {"state": "SEE_ACTUAL_INSTALL_VERIFIER_REFERENCE" if package in installs else "UNKNOWN_CURRENT_OFFICIAL_SOURCE_REVALIDATION"}),
            "manifest_permissions": declared,
            "effective_permissions": beike_permissions if package == "com.lianjia.beike" else unknown_permissions(),
            "runtime_acceptance": {"domains": runtime_domains, "login_or_guest_actual": "UNKNOWN_NOT_QUALIFIED",
                "planned_authentication": planned["authentication"], "planned_core_cases": planned["core_cases"],
                "planned_network": planned["network"], "planned_storage": planned["storage"], "planned_permissions": planned["permissions"],
                "planned_hardware": planned["hardware"], "inputs_needed": planned["test_inputs_needed"],
                "planned_failure_paths_are_not_actual_failures": planned["expected_failure_paths_to_exercise_or_observe"],
                "long_running_workload": planned["long_running_workload"], "thresholds": catalog["new_proposed_thresholds"],
                "runtime_targets_reference": planned["runtime_targets"], "historical_pass_transfer_to_redroid": False},
            "observed_failure_paths": failures, "production_ready": False, "cleanup_eligible": False,
            "latest_usable_version_qualified": False})
    need({a["package"] for a in apps if a["original_eight"]} == ORIGINAL_EIGHT, "EXACT_ORIGINAL_EIGHT_MEMBERSHIP")
    accepted = [a for a in apps if a["APK_audit"]["joint_qualified"]]
    attempted = [a for a in apps if a["package"] in all_audits]
    individually_signed = [a for a in attempted if all(p["signature"].get("verified") is True for p in a["APK_audit"]["APKs"])]
    summary = {"current_Launcher_packages": len(apps), "current_Launcher_components": sum(len(x) for x in components.values()),
        "PM_user0_installed_packages_enumerated": len(pm), "full_APK_bound_scope_packages": len(scope["apps"]),
        "original_eight": sum(a["original_eight"] for a in apps), "APK_audit_attempted_apps": len(attempted),
        "APK_audit_attempted_APKs": sum(a["APK_audit"]["APK_count"] for a in attempted),
        "APK_joint_audit_passed_apps": len(accepted), "APK_joint_audit_passed_APKs": sum(a["APK_audit"]["APK_count"] for a in accepted),
        "APK_joint_audit_failed_or_unknown_apps": len(apps) - len(accepted),
        "individual_signature_observed_apps_including_failed_batches": len(individually_signed),
        "completed_upgrades": len(installs), "official_reference_byte_identical_apps": sum(r.get("byte_identity_rechecked_locally") is True for r in official.values()),
        "candidate_signer_conflict_apps": sum(r["state"] == "BLOCKED_CANDIDATE_SIGNER_MISMATCH" for r in official.values()),
        "effective_permission_snapshot_apps": 1, "effective_permission_unknown_apps": len(apps) - 1,
        "planned_core_cases": sum(len(a["runtime_acceptance"]["planned_core_cases"]) for a in apps),
        "planned_network_profiles": len({a["runtime_acceptance"]["planned_network"]["profile"] for a in apps}),
        "core_business_qualified_apps": 0, "long_run_qualified_apps": 0, "restart_regression_qualified_apps": 0,
        "production_ready_apps": 0, "cleanup_eligible_apps": 0, "old_products_deleted_bytes": 0}
    return {"schema": "pocket4-all-launcher-evidence-matrix-v1", "state": "EVIDENCE_SNAPSHOT_NOT_PRODUCTION_ADMISSION",
        "summary": summary, "resolver_evidence": pm_refs, "runtime_epoch_sha256": index["runtime_epoch_sha256"],
        "current_scope_evidence": inputs.ref(SCOPE), "audit_gate_source": inputs.ref(GATE), "audit_plan": inputs.ref(PLAN),
        "batch_results": batches, "catalog_evidence": inputs.ref("app_test_catalog.json"),
        "threshold_origin": catalog["new_proposed_thresholds"],
        "boundaries": {"Main_Bilibili_Accept_authorized": False, "Bilibili_Accept_only_historical_independent_cell": "p4-bili-m30-cell-20261010",
            "Meituan_proactive_location_grant_authorized": False, "ADB_dependency_added": False,
            "signature_or_integrity_bypass_authorized": False, "missing_evidence_is_NA_or_PASS": False,
            "old_failure_or_UNKNOWN_reclassified": False, "target_calls_by_this_generator": 0, "gate_claims_by_this_generator": 0,
            "full_private_UI_or_business_raw_included": False, "reDroid_current_target": "RETIRED_NO_CURRENT_TEST_TARGET",
            "latest_usable_apps_complete": False},
        "interpretation": ["Current means the specific recorded observations, not a new live query by this generator.",
            "A successful APK signature/parser audit is not a successful login, business operation, network, storage or integrity assessment.",
            "Failed-batch individual observations remain attributed observations and cannot qualify the batch or app.",
            "Version names come only from the actual parsed base manifest. Historical names are separately retained, never substituted.",
            "Permission declarations, PM requested/install permissions, runtime grants, AppOps and roles are distinct layers.",
            "No-ABI declaration does not prove hardware or native-bridge compatibility. Offline/hardware profiles require their own real evidence.",
            "The 60-minute / three restart / three recovery thresholds are new proposed minimums, not historical passes.",
            "All current production and cleanup results remain false. No target execution occurs in this generator."], "apps": apps}


def md(value):
    def esc(s):
        return str(s).replace("|", "\\|").replace("\n", " ")
    def ref(pin, label):
        return f"[{label}](../../../{pin['path']})（{pin['bytes']} B；SHA256 `{pin['sha256']}`）"
    s = value["summary"]
    lines = ["# Pocket4 全部 Launcher App 证据矩阵", "", 
        f"实际 user 0 MAIN/LAUNCHER 集合 **{s['current_Launcher_packages']} 个 App / {s['current_Launcher_components']} 个组件**。"
        f"已尝试 {s['APK_audit_attempted_apps']} 个 App / {s['APK_audit_attempted_APKs']} 个 APK；"
        f"整批联合审计通过 **{s['APK_joint_audit_passed_apps']} 个 App / {s['APK_joint_audit_passed_APKs']} 个 APK**，"
        f"其余 {s['APK_joint_audit_failed_or_unknown_apps']} 个不能计为联合通过。", "",
        f"本轮已完成 **{s['completed_upgrades']} 次升级**；另有 {s['official_reference_byte_identical_apps']} 个 App 的当前 APK 与既有官方 release 资产摘要逐字节对应，"
        f"{s['candidate_signer_conflict_apps']} 个候选因签名冲突被阻止。**生产就绪 0，允许清理 0，已删除旧产物 0 B。**", "",
        "这是一份已记录证据的本地合并快照，不会发起设备查询、安装、UI 操作、权限更改或清理。"
        "通过 APK 审计不代表核心业务、登录或访客、网络、存储、权限恢复、长时间运行、重启或故障恢复已经通过。", "",
        "## 证据边界", "",
        "- PM 枚举包含 205 个已装包；本次 Launcher 范围是实际解析得到的 45 个。完整 APK/数据身份另有 47 包固定范围（含 2 个 helper），不能把 205 行元数据说成 205 包完整验签。",
        "- 版本名只取实际 base manifest。缺失或解析失败保留 UNKNOWN；历史版本名列于 JSON 独立字段。SDK 数值按实际工具原样保留，不修正看起来异常的 min/target 组合。",
        "- 权限声明不等于已授予权限。当前只有贝壳有独立 user 0 PM/AppOps 原文派生快照，其余有效授权保持 UNKNOWN。缺失不能推断为 denied；AppOps 未标明 UID scope 的行不被扩大解释。",
        "- 原 b05 失败原样保留；其独立纠正审计有单独真实终态。b13 的个体签名/manifest 观察不消除整批失败。",
        "- 登录、核心业务、长时、应用重启、runtime 重启后每包回归与故障恢复尚未资格化。60 分钟、3 次应用重启、3 次网络恢复是本轮提出的门槛，不能写成历史已通过。",
        "- 离线、系统、硬件 profile 按各自合同取证，不强制虚构 DNS/TLS、账号、通话或相机结果。reDroid 当前目标已退休，无当前测试结论可转移。",
        "- Main 不执行 Bili Accept；历史 Accept 只限指定独立 cell。美团位置不得主动 grant。签名、完整性、任务归属、foreground、双 hash 与 UNKNOWN 约束全部保留。", "",
        "## 当前名单、版本与 APK 结果", "",
        "“原八项”标记原定八个 App。App 标签来自此前实际 Launcher 名称记录；包名与组件来自新的 PM resolver。† 表示仅失败批中的个体观察，不能计为联合审计通过。", "",
        "| App（原八项） | 包名 | 实际版本名 / PM code | APK 数 | APK 联合结果 | 本轮升级 / 官方源状态 | Manifest 声明数 |", 
        "|---|---|---|---:|---|---|---:|"]
    for a in value["apps"]:
        audit, manifest = a["APK_audit"], a["APK_audit"]["current_manifest"]
        version = "UNKNOWN" if manifest["version_name"] is None else repr(manifest["version_name"])
        if not audit["joint_qualified"] and manifest["version_name"] is not None:
            version += " †"
        state = "通过" if audit["joint_qualified"] else "失败批，未资格化" if audit["batch"] else "UNKNOWN"
        source = a["official_source"]["state"]
        update = "升级成功，业务待验" if a["upgrade"]["state"].startswith("INSTALLED_") else "官方资产摘要同字节" if source.startswith("CURRENT_APK_BYTE_") else "候选签名冲突" if source.startswith("BLOCKED_") else "未完成新升级"
        declarations = sum(a["manifest_permissions"]["counts_by_tag"].values())
        lines.append(f"| {esc(a['label_reference'])}{' **原八项**' if a['original_eight'] else ''} | `{a['package']}` | {esc(version)} / {a['current_PM']['version_code']} | {audit['APK_count']} | {state} | {update} | {declarations} |")
    lines += ["", "Manifest 声明数包括 uses-permission 与 permission 等各类条目，也可能跨 split 重复；不是唯一权限数或有效授权数。JSON 保留每个 APK 的完整条目、原始名字、签名方案、证书 SHA256、APK 哈希及命令原文摘要。", "",
        "## 11 次真实升级与保留旧 APK", "", "| 包名 | versionCode 变化 | 保留旧 APK | 实际 job |", "|---|---:|---:|---|"]
    for a in value["apps"]:
        u = a["upgrade"]
        if u["state"].startswith("INSTALLED_"):
            lines.append(f"| `{a['package']}` | {u['before_version_code']} → {u['after_version_code']} | {u['previous_APK_count_retained']} 件 / {u['previous_APK_bytes_retained']} B | `{u['job_id']}` |")
    lines += ["", "每次成功均验证原始 stdout、完整 durable 终态、唯一 native install 正常返回、当前 scope 的 UID/code/证书/完整 APK 字节对应及数据目录身份保留。京东保留原 base + arm64 split 两件，失败的 jd-01 仍单列。旧版本只保留，未清理。", "",
        "## 权限与业务验收", "",
        "贝壳：PM requested 63 行、install 权限 26 行均报告 granted=true；user 0 runtime 权限 15 行，其中 ACCESS_LOCAL_NETWORK=true，另外 14 行 false；AppOps 58 行按原文字面归属保存；roles UNKNOWN。七个前导空格的非规范 VIBRATE 名字保留，不修剪。不据 false 推断用户拒绝原因，不据快照声称权限拒绝恢复用例通过。", "",
        "贝壳已真实启动和只读检查；两步探索的第一步关闭弹窗后独立后置观察成功，第二步在 dispatch 前因 INSPECTED_TREE_OR_WINDOW_CHANGED 被 helper 拒绝。整例 FAILED/UNKNOWN 原样保留；后续独立只读观察不等于新的点击授权，也不等于中文搜索成功。其他 App 的核心操作没有本轮完整资格化证据。", "",
        f"计划覆盖 {s['planned_core_cases']} 个核心用例 / {s['planned_network_profiles']} 个网络或离线 profile。以下每包计划仍为待执行验收合同，不能用计划文本当测试结果。", "",
        "| 包名 | 登录 / 访客计划 | 核心操作计划 | 网络或本地 profile | 业务 / 长时 / 重启 / 恢复 |", "|---|---|---|---|---|"]
    for a in value["apps"]:
        r = a["runtime_acceptance"]
        operations = "；".join(c["operation"] for c in r["planned_core_cases"])
        lines.append(f"| `{a['package']}` | {esc(r['planned_authentication']['planned_mode'])} | {esc(operations)} | `{r['planned_network']['profile']}` | UNKNOWN / UNKNOWN / UNKNOWN / UNKNOWN |")
    lines += ["", "每包 JSON 还列出适用的账号、受控对端、硬件、存储、权限与失败路径要求；未提供的输入保持 UNKNOWN，不替换为 N/A。", "",
        "## 批次状态及失败归因", "", "| 批次 | 原始状态 / 当前证据关系 | job |", "|---:|---|---|"]
    for b in value["batch_results"]:
        lines.append(f"| {b['batch']} | `{b['state']}` | `{b.get('job_id','UNKNOWN')}` |")
    lines += ["", "当前失败批的具体 package parse_errors 在 JSON 的 observed_failure_paths 与每件 APK 中保留。fixture 的 AAPT_PACKAGE_VERSION_REQUIRED 不是签名失败；版本属性的合法默认语义仍需独立源证据和新修订验证，不能在本矩阵中猜补。", "",
        "## 可复现来源", "",
        "本生成器只读取显式固定的项目证据。成功 APK 批重用冻结原 gate 与 linked gate 的原检查，未调用 claim；已读取的每份文件在输出前重新散列。INPUTS.json 记录完整输入路径、字节数与 SHA256。", "",
        ref(value["resolver_evidence"]["worker"], "实际 PM / resolver 结果"), "",
        ref(value["current_scope_evidence"], "当前 47 包字节 / UID / 数据身份"), "",
        ref(value["audit_gate_source"], "冻结 linked audit gate"), "",
        ref(value["catalog_evidence"], "45 App / 136 用例计划"), "",
        "运行：在项目根目录执行 `python3 -B audit_matrix_r1/build_matrix.py --write-snapshot`。输出到按输入摘要命名的新目录；已有相同快照只核对原字节，不覆盖。运行成功只表示本地证据矩阵生成成功。", ""]
    return "\n".join(lines).encode("utf-8")


def write_once(path, raw):
    if path.exists():
        need(path.is_file() and not path.is_symlink() and path.read_bytes() == raw, "EXISTING_SNAPSHOT_DIFFERENT_BYTES")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, 0o644)
    try:
        with os.fdopen(fd, "wb", closefd=False) as handle:
            handle.write(raw); handle.flush(); os.fsync(fd)
    finally:
        os.close(fd)
    need(path.read_bytes() == raw, "LOCAL_SNAPSHOT_READBACK")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write-snapshot", action="store_true")
    args = parser.parse_args()
    inputs = Inputs()
    inputs.read("audit_matrix_r1/build_matrix.py")
    value = build(inputs)
    inputs.recheck()
    rows = sorted(inputs.rows.values(), key=lambda r: r["path"])
    manifest = {"schema": "pocket4-local-matrix-inputs-v1", "files": rows, "all_inputs_rehashed_before_publication": True}
    input_raw = canonical(manifest) + b"\n"
    digest = sha(input_raw)
    value["input_manifest_sha256"] = digest
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False).encode() + b"\n"
    markdown = md(value)
    out = HERE / "snapshots" / digest[:20]
    if args.write_snapshot:
        out.mkdir(parents=True, exist_ok=True)
        for name, content in (("INPUTS.json", input_raw), ("EVIDENCE_MATRIX.json", raw), ("EVIDENCE_MATRIX.md", markdown)):
            write_once(out / name, content)
    print(json.dumps({"local_generation_succeeded": True, "snapshot_written": args.write_snapshot,
        "snapshot_directory": str(out), "summary": value["summary"], "input_manifest_sha256": digest,
        "files": [{"name": name, "bytes": len(content), "sha256": sha(content)} for name, content in
            (("INPUTS.json", input_raw), ("EVIDENCE_MATRIX.json", raw), ("EVIDENCE_MATRIX.md", markdown))],
        "runtime_jobs_submitted": 0, "gate_claims": 0, "production_admission_granted": False}, sort_keys=True))


if __name__ == "__main__":
    main()
