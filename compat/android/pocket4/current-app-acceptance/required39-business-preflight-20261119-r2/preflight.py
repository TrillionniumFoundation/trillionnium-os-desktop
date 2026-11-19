#!/usr/bin/env python3
"""Pinned, host-only required39 planning. No runtime imports or Android calls.

This program reads exactly ten bounded JSON snapshots. It never follows the
origin paths embedded in them, reads APKs, invokes another process, or admits
execution. A valid output is a blocked plan, never application acceptance.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import stat
import sys


PINS = {
    "CURRENT-SOURCE-STATE.json": (157891, "4d25fc0aafd5668cc3f0c31be157bc617732902976aad821333a02de84ff9bf7"),
    "current-source-inputs.json": (111728, "5d14f8af912f57e9c93290fa9aa3c62a686b57d82f3aa964beb5860b452df9ab"),
    "current-source-freshness.json": (105899, "894162a5bb6fc31deadd2dfb4069b7a353fad3014c131f960a9cc14b3bb4258e"),
    "source-successor-RESULT.json": (7311, "e74ebfd7f351b6b5e317bfbe84555cc914e2a09fd0648052a39786872ca8e625"),
    "release-scope.json": (2397, "7d3715d360abbdadf3206406c331d575eed4020040d7963c182af9bad85bf24d"),
    "canonical45.json": (24135, "441289f9c04b46f38e1dd6e19f23ec6e4c6729b6a6f814cab81c0ae6fbbb1e78"),
    "selection13.json": (14314, "9c5c77c387711dac2f7387a880932e40f0148939feca2a6348daa939587f9598"),
    "COVERAGE.json": (75631, "29c696b87fc075ac1c8c250efcfb5a5eb42fb0fba38f38755f09f02bab717e7a"),
    "EVIDENCE.json": (454047, "677a8c0cbd5e56a600a7ebb5f2d672d97b1a04c9cc3c9c0ba8ede348ea7f569e"),
    "latest-metadata.json": (86422, "dca1ba954f28b1f3487fe16942acb74e88d03799253fd5a8f5db4493fe61d620"),
}
EXEMPT = {"com.enflick.android.TextNow", "com.pinger.textfree", "com.ubercab"}
SYSTEM = {
    "com.android.calendar", "com.android.camera2", "com.android.contacts",
    "com.android.deskclock", "com.android.dialer", "com.android.documentsui",
    "com.android.gallery3d", "com.android.messaging", "com.android.quicksearchbox",
    "com.android.settings",
}
SELECTED = {
    "com.android.calendar": [0, 1], "com.android.camera2": [2, 3],
    "com.android.contacts": [0], "com.android.deskclock": [4, 5],
    "com.android.documentsui": [6, 7], "com.android.gallery3d": [8, 9, 10, 11, 12],
    "com.ihg.apps.android": [5],
}
MISMATCHED = SYSTEM & set(SELECTED) - {"com.android.gallery3d"}
COMMON = {"identity", "lifecycle", "stability", "data_permissions", "release_scope", "ui_observation"}
NO_CREDIT_KEYS = {
    "installed", "runtime_qualified", "business_qualified", "production_ready",
    "native_compatibility_qualified", "whole_app_business_accepted",
    "all_39_runtime_accepted", "all_39_latest_qualified", "execution_ready",
    "execution_authorized", "historical_runtime_credit_transferred",
    "full_Main_execute_or_full_runtime_seed_executed",
    "source_state_installed", "source_state_runtime_qualified",
    "source_state_business_qualified", "source_state_production_ready",
    "individual_APK_install_authorized", "individual_system_APK_installation_allowed",
    "signer_migration_qualified", "migration_execution_authorized",
}
ZERO_COUNTERS = {
    "Android_actions", "CURRENT_writes", "Main_actions", "new_runtime_acceptance_count",
    "actual_current_main_business_results_observed", "actual_runtime_acceptances",
    "runtime_acceptance_count", "business_acceptance_count", "production_ready_count",
    "execution_ready_count", "Android_calls", "user_data_reads", "credentials_reads",
}
FIREFOX = "org.mozilla.firefox"
MEITUAN = "com.sankuai.meituan.takeoutnew"
FIREFOX_PAGES = {
    "manifesto": {"url": "https://www.mozilla.org/en-US/about/manifesto/", "heading": "The Mozilla Manifesto"},
    "history": {"url": "https://www.mozilla.org/en-US/about/history/", "heading": "History of the Mozilla Project"},
}
FIREFOX_ACTIONS = (
    "admit_owned_session", "open_manifesto", "open_history_same_tab", "back",
    "forward", "open_second_owned_tab", "close_second_owned_tab",
    "normal_close_owned_task", "independent_reopen_owned_task", "owned_cleanup",
)
RUNTIME_BINDINGS = ("Main_identity", "UID", "Android_user", "framework_epoch",
                    "installed_APK_identity", "actual_engine_mapping", "helper_custody",
                    "owned_task_and_fixture", "UI_selectors")


class PreflightError(ValueError):
    pass


def require(ok: bool, message: str) -> None:
    if not ok:
        raise PreflightError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate JSON key: " + key)
        result[key] = value
    return result


def parse_json(data: bytes):
    def bad_constant(_):
        raise PreflightError("non-finite JSON number")
    return json.loads(data, object_pairs_hook=unique_object, parse_constant=bad_constant)


def identity(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid,
            st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns)


def load_bundle(directory: Path):
    """Open only fixed basenames, refuse symlinks and pin before JSON parsing."""
    directory_fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    result, observations = {}, {}
    try:
        for name, (length, digest) in PINS.items():
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=directory_fd)
            with os.fdopen(fd, "rb") as stream:
                before = os.fstat(stream.fileno())
                require(stat.S_ISREG(before.st_mode) and before.st_size == length,
                        "input type/length mismatch: " + name)
                data = stream.read(length + 1)
                after = os.fstat(stream.fileno())
            require(identity(before) == identity(after), "input changed during read: " + name)
            require(len(data) == length and hashlib.sha256(data).hexdigest() == digest,
                    "input SHA/length mismatch: " + name)
            result[name] = parse_json(data)
            observations[name] = identity(after)
    finally:
        os.close(directory_fd)
    return result, observations


def indexed(rows, label):
    require(isinstance(rows, list), label + " must be an array")
    result = {}
    for row in rows:
        require(isinstance(row, dict) and isinstance(row.get("package"), str), label + " has invalid row")
        package = row["package"]
        require(package not in result, label + " duplicate package: " + package)
        result[package] = row
    return result


def no_credit(node, path="root"):
    if isinstance(node, dict):
        for key, value in node.items():
            location = path + "." + key
            if key in NO_CREDIT_KEYS:
                historical_zero_count = (location == "COVERAGE.json.counts.execution_ready" and type(value) is int and value == 0)
                require(value is False or historical_zero_count, "runtime/latest promotion refused: " + location)
            if key in ZERO_COUNTERS:
                require(type(value) is int and value == 0, "runtime/action counter refused: " + location)
            no_credit(value, location)
    elif isinstance(node, list):
        for i, value in enumerate(node):
            no_credit(value, path + "[" + str(i) + "]")


def pinned_ref(ref, name, label):
    require(isinstance(ref, dict), label + " missing reference")
    length, digest = PINS[name]
    require(ref.get("bytes") == length and ref.get("sha256") == digest, label + " reference mismatch")


def has_body_pin(ref, label):
    require(isinstance(ref, dict) and type(ref.get("bytes")) is int and ref["bytes"] > 0,
            label + " missing positive size")
    require(isinstance(ref.get("sha256"), str) and re.fullmatch(r"[0-9a-f]{64}", ref["sha256"]) is not None,
            label + " missing SHA256")


def validate_bundle(d):
    require(set(d) == set(PINS), "snapshot set mismatch")
    state, registry, freshness = (d[n] for n in ("CURRENT-SOURCE-STATE.json", "current-source-inputs.json", "current-source-freshness.json"))
    scope, gates, selection, coverage = (d[n] for n in ("release-scope.json", "canonical45.json", "selection13.json", "COVERAGE.json"))
    result, evidence = d["source-successor-RESULT.json"], d["EVIDENCE.json"]
    # EVIDENCE contains inspected source literals, not runtime observations.
    for name in set(PINS) - {"EVIDENCE.json", "canonical45.json", "release-scope.json"}:
        no_credit(d[name], name)
    require(scope["schema"] == "pocket4-application-release-scope-v1", "scope schema mismatch")
    selection42 = scope["selected_packages"]
    require(len(selection42) == 42 and len(set(selection42)) == 42, "selected42 scope mismatch")
    exemptions = indexed(scope["exemptions"], "scope exemptions")
    require(set(exemptions) == EXEMPT and scope["exemptions"] == state["exemptions"], "exemption scope changed")
    required = set(selection42) - EXEMPT
    require(len(required) == 39 and SYSTEM <= required, "required39 partition mismatch")
    require(state["required_count"] == 39 and state["selected_count"] == 42 and state["source_evidence_count"] == 39,
            "state source counts mismatch")
    require(state["scope_id"] == scope["scope_id"], "state scope mismatch")
    require(state["individual_system_APK_installation_allowed"] is False, "standalone system installation refused")
    has_body_pin(state["full_GSI_dependency"], "full GSI metadata")
    for ref, name, label in (
        (state["current29_registry"], "current-source-inputs.json", "state registry"),
        (state["current29_freshness"], "current-source-freshness.json", "state freshness"),
        (state["source_inputs"]["registry"], "current-source-inputs.json", "state source registry"),
        (state["source_inputs"]["freshness"], "current-source-freshness.json", "state source freshness"),
        (state["source_inputs"]["scope"], "release-scope.json", "state source scope"),
        (coverage["source_state"], "CURRENT-SOURCE-STATE.json", "coverage state"),
        (coverage["canonical_gates"], "canonical45.json", "coverage canonical gates"),
        (coverage["selector"], "selection13.json", "coverage selector"),
    ):
        pinned_ref(ref, name, label)
    require(result["state"] == "PASSED", "source successor did not pass")
    for name in ("CURRENT-SOURCE-STATE.json", "current-source-inputs.json", "current-source-freshness.json"):
        pinned_ref(result["outputs"][name], name, "actual source successor output")
    apps = indexed(state["applications"], "state")
    records = indexed(registry["applications"], "registry")
    fresh = indexed(freshness["rows"], "freshness")
    rows = indexed(coverage["rows"], "coverage")
    require(set(apps) == set(rows) == required, "state/coverage required39 mismatch")
    require(set(records) == (required - SYSTEM) | {"com.android.vending"}, "registry29 plus companion mismatch")
    require(set(fresh) == required - SYSTEM, "freshness29 set mismatch")
    require(freshness["required_non_system_count"] == 29 and freshness["required_system_count"] == 10,
            "freshness partition mismatch")
    require(records["com.android.vending"] == state["retained_dependency_outside_required39"], "companion record mismatch")
    require(records["com.android.vending"]["required39_member"] is False, "companion cannot count toward39")
    require(records["com.android.vending"]["source_identity_verified"] is True and
            records["com.android.vending"]["signature_verified"] is True, "companion source unverified")
    require(state["required_before_installation"]["Meituan_official_signer_and_existing_userdata_migration"] == "PENDING" and
            records[MEITUAN]["signer_migration_qualified"] is False,
            "original Meituan signer and userdata migration remains pending")
    for package, app in apps.items():
        require(app["source_identity_verified"] is True and rows[package]["source_identity_verified"] is True,
                "unverified source refused: " + package)
        expected_kind = "system" if package in SYSTEM else "third_party"
        require(app["kind"] == rows[package]["kind"] == expected_kind, "package kind mismatch: " + package)
        if package in SYSTEM:
            require(app["individual_APK_install_authorized"] is False and
                    app["install_mode"] == "coherent_full_GSI_with_framework_and_native_dependencies",
                    "system source must use coherent full GSI")
            source = app["unchanged_original_system_record"]
            require(source["source_identity_verified"] is True and source["package"] == package,
                    "system identity unverified")
            require(bool(source["signer_certificate_sha256"]), "system signer missing")
            has_body_pin(source["apk"], "system APK metadata")
            has_body_pin(source["source_receipt"], "system receipt metadata")
            mismatch = rows[package].get("target_profile_mismatch")
            require(bool(mismatch) == (package in MISMATCHED), "five target identity mismatches must remain explicit")
            if mismatch:
                require(mismatch["old_sha256"] != source["apk"]["sha256"] == mismatch["current_sha256"],
                        "target mismatch proof disagrees with current GSI")
                require(mismatch["current_bytes"] == source["apk"]["bytes"], "current GSI APK size mismatch")
        else:
            source = app.get("current_registry_record", app.get("unchanged_current_registry_record"))
            require(source == records[package], "state/registry record mismatch: " + package)
            require(source["source_identity_verified"] is True and source["signature_verified"] is True,
                    "source signature/identity missing: " + package)
            require(source["required39_member"] is True, "required registry member refused")
            has_body_pin(source["input"], "third-party input metadata")
            require(fresh[package]["source_input_selected"] is True and
                    fresh[package]["selected_input_version"] == source["version_name"], "freshness version mismatch")
            if "selected_input_version_code" in fresh[package]:
                require(fresh[package]["selected_input_version_code"] == source["version_code"], "freshness versionCode mismatch")
        require(rows[package]["source_version"] == source["version_name"], "coverage version mismatch")
    require(gates["schema"] == "pocket4-app-release-gates-v1" and len(gates["packages"]) == 45,
            "historical canonical45 schema/count mismatch")
    require(set(gates["common_gates"]) == COMMON, "common gates changed")
    require(required - set(gates["packages"]) == {FIREFOX}, "canonical mapping gap changed")
    require(len(selection["selected_preparations"]) == 13 and selection["selection_only"] is True,
            "selector13 must remain preparation-only")
    preparations = selection["selected_preparations"]
    source_documents = {x["path"]: x for x in evidence["source_documents"]}
    require(len(source_documents) == 17 and len(evidence["selected_source_code_inspection"]) == 29,
            "bounded evidence scope mismatch")
    for ref in preparations:
        receipt = source_documents.get(ref["path"], {})
        require(all(receipt.get(k) == ref[k] for k in ("path", "bytes", "sha256")), "preparation missing audited source receipt")
    for package, row in rows.items():
        indices = SELECTED.get(package, [])
        require(row["selected_preparation_indices"] == indices, "package preparation mapping changed")
        require(row["selected_preparation_refs"] == [preparations[i] for i in indices], "selected preparation reference mismatch")
        require(bool(row["existing_implemented_scopes"]) == bool(indices), "finite source scope mapping mismatch")
        if package != FIREFOX:
            profile = gates["packages"][package]["profile"]
            require(row["canonical_profile"] == profile and
                    row["canonical_gate_ids"] == list(gates["profiles"][profile]["checks"]), "canonical gate mapping mismatch")
        else:
            require(row["canonical_profile"] is None and not row["canonical_gate_ids"], "Firefox original missing gate hidden")
    require(coverage["counts"]["prepared_finite_case_packages"] == 7 and
            coverage["counts"]["packages_without_selected_business_executor"] == 32 and
            coverage["counts"]["verified_target_APK_profile_mismatches"] == 5, "coverage count mismatch")
    united = indexed(d["latest-metadata.json"]["rows"], "latest metadata")["com.united.mobile.android"]
    require(united["selected_input_version"] == "4.2.103" and united["fresh_observation"]["version"] == "4.2.104" and
            united["comparison"] == "UPDATE_OBSERVED_REQUIRES_PAYLOAD_QUALIFICATION", "United pending update must remain explicit")
    return apps, records, rows, required, united


def firefox_checklist():
    steps = [
        ("admit_owned_session", "Resolve current Main/UID/user/epoch and verified Firefox payload; create a controlled owned test session without opening existing tabs or history.", "Record owned task/tab identifiers and review source-bound UI controls; otherwise stop."),
        ("open_manifesto", "Enter the exact Mozilla Manifesto HTTPS URL in the owned tab.", "Observe the exact final URL, normal HTTPS page and visible The Mozilla Manifesto heading; retain owned-page evidence."),
        ("open_history_same_tab", "Navigate the same owned tab to the exact Mozilla History URL.", "Observe the exact final URL and visible History of the Mozilla Project heading."),
        ("back", "Use the browser Back control exactly once.", "The same owned tab returns to the exact Manifesto URL and heading."),
        ("forward", "Use the browser Forward control exactly once.", "The same owned tab returns to the exact History URL and heading."),
        ("open_second_owned_tab", "Open a new owned tab and navigate only to the Manifesto URL.", "Exactly two test-owned tabs exist; the second has the exact Manifesto URL and heading. Do not enumerate user tabs."),
        ("close_second_owned_tab", "Close only the second test-owned tab using its recorded identity.", "Exactly one test-owned tab remains, showing the prior History page. Existing user tabs are unchanged."),
        ("normal_close_owned_task", "Normally close only the admitted test-owned Firefox task, preserving its controlled test state.", "Observe that exact owned task closing; no force-stop, clear-data or unrelated task action."),
        ("independent_reopen_owned_task", "Reopen the controlled Firefox test session as a separate launch.", "Bind the new owned task and observe the expected public page/state without reading user history; any restore mismatch remains a failure."),
        ("owned_cleanup", "Close only recorded test-owned tabs/tasks and remove only explicit owned fixtures.", "Retain success/failure evidence and show pre-existing task/data boundaries unchanged; otherwise do not claim completion."),
    ]
    return {
        "package": FIREFOX, "origin": "ADDITIVE_REVIEWABLE_CHECKLIST_ORIGINAL_CANONICAL45_UNCHANGED",
        "driver_implemented": False, "execution_authorized": False, "execution_ready": False,
        "business_qualified": False, "whole_app_business_accepted": False,
        "pages": copy.deepcopy(FIREFOX_PAGES),
        "forbidden": ["download", "login", "form_submit", "message_send", "payment", "purchase", "user_history_read", "user_tab_enumeration", "clear_data", "force_stop"],
        "steps": [{"id": key, "action": action, "required_observation": observation, "status": "NOT_EXECUTED"} for key, action, observation in steps],
        "remaining": ["Implement and independently review a source-bound UI executor", "Resolve Main/UID/user/epoch/helper and owned-session admissions", "Observe actual rendering/input/reopen behavior", "Run canonical common stability, data-preservation and release-review gates"],
    }


def validate_firefox(plan):
    require(plan == firefox_checklist(), "Firefox plan exceeds fixed public-only checklist or changes expected observations")
    require(tuple(step["id"] for step in plan["steps"]) == FIREFOX_ACTIONS, "Firefox step order mismatch")
    require(plan["pages"] == FIREFOX_PAGES, "Firefox URL scope mismatch")
    no_credit(plan, "Firefox")


def build_plan(documents):
    apps, records, rows, required, united = validate_bundle(documents)
    state, gates = documents["CURRENT-SOURCE-STATE.json"], documents["canonical45.json"]
    firefox = firefox_checklist()
    validate_firefox(firefox)
    plans = []
    for package in sorted(required):
        row, app = rows[package], apps[package]
        source = app["unchanged_original_system_record"] if package in SYSTEM else records[package]
        profile = row["canonical_profile"]
        plan = {
            "package": package, "name": row["name"], "kind": app["kind"],
            "source_identity_verified_in_fixed_receipts": True,
            "source_version": source["version_name"], "source_version_code": source["version_code"],
            "source_body_pin_metadata": copy.deepcopy(source["apk"] if package in SYSTEM else source["input"]),
            "source_bytes_reopened_here": False, "fresh_destination_custody_verified": False,
            "implementation_class": row["implementation_class"],
            "finite_prepared_case_source_exists": package in SELECTED,
            "prepared_case_scopes": copy.deepcopy(row["existing_implemented_scopes"]),
            "preparation_references_metadata_only": copy.deepcopy(row["selected_preparation_refs"]),
            "canonical_profile": profile,
            "canonical_checks": copy.deepcopy(gates["profiles"][profile]["checks"]) if profile else {},
            "common_gate_ids": list(gates["common_gates"]),
            "canonical_prerequisites": copy.deepcopy(row["canonical_prerequisites"]),
            "pending_work": copy.deepcopy(row["remaining"]),
            "actual_runtime_bindings": {key: None for key in RUNTIME_BINDINGS},
            "runtime_binding_status": "UNRESOLVED_BLOCK_EXECUTION",
            "installed": False, "runtime_qualified": False, "native_compatibility_qualified": False,
            "business_qualified": False, "production_ready": False, "whole_app_business_accepted": False,
            "execution_ready": False, "execution_authorized": False,
        }
        if package in SYSTEM:
            plan["system_install_mode"] = "coherent_full_GSI_only"
            plan["individual_APK_install_authorized"] = False
        if package in MISMATCHED:
            plan["target_profile_mismatch"] = copy.deepcopy(row["target_profile_mismatch"])
        if package == "com.android.gallery3d":
            plan["standalone_install_mode_forbidden"] = True
            plan["required_adapter"] = "Review image-installed Gallery verification/custody contract; do not invoke historical install mode."
        if package == "com.united.mobile.android":
            plan["latest_update_pending"] = copy.deepcopy(united["fresh_observation"])
            plan["latest_input_status"] = "4.2.104_METADATA_ONLY_FIXED_PAYLOAD_REMAINS_4.2.103"
        if package == MEITUAN:
            plan["signer_migration_qualified"] = records[MEITUAN]["signer_migration_qualified"]
            plan["migration_prerequisite"] = state["required_before_installation"]["Meituan_official_signer_and_existing_userdata_migration"]
            plan["migration_execution_authorized"] = False
            plan["pending_work"].append("Review and qualify preservation of existing test-signed app data before a standard official-signer transition; no uninstall, clear-data, or userdata generation change is admitted by this plan.")
        if package == FIREFOX:
            plan["additive_checklist"] = firefox
            plan["driver_implemented"] = False
        plans.append(plan)
    result = {
        "schema": "pocket4-required39-business-preflight-plan-v1",
        "state": "PLAN_PREPARED_RUNTIME_BLOCKED", "scope_id": state["scope_id"],
        "planning_only": True, "source_metadata_contract_validated": True,
        "source_snapshots": {name: {"bytes": length, "sha256": digest} for name, (length, digest) in PINS.items()},
        "receipt_scope": "Local fixed JSON snapshot verification only; no fresh source-host, APK, UID, install, Main, runtime or business observation.",
        "counts": {"required_packages": 39, "system_packages": 10, "non_system_packages": 29, "selected_preparations": 13,
                   "finite_prepared_case_packages": 7, "packages_without_selected_business_executor": 32,
                   "target_identity_rebinds": 5, "original_canonical_package_matches": 38,
                   "runtime_acceptance_count": 0, "business_acceptance_count": 0, "production_ready_count": 0, "execution_ready_count": 0},
        "exemptions": copy.deepcopy(state["exemptions"]),
        "retained_companion_not_required39": "com.android.vending",
        "common_gate_definitions": copy.deepcopy(gates["common_gates"]),
        "required_before_installation": copy.deepcopy(state["required_before_installation"]),
        "global_unresolved_gates": [
            "All installed identity/Main/UID/user/framework epoch and actual engine mappings",
            "Fresh destination custody, current source/latest release reconciliation before activation",
            "Five system target identity rebinds and current GSI Calendar/Contacts/ExternalStorage/MediaProvider contracts",
            "Coherent full-GSI installation; no independent system APK installation",
            "Gallery image-installed custody adapter; historical standalone install mode is prohibited",
            "Actual finite-case business results, failure coverage, common stability/soak and whole-App review",
            "32 packages still lack a selected business executor; Firefox gains a checklist only",
            "Account/payment/outbound-message gates remain unexecuted and require separately authorized test scope",
        ],
        "source_preservation": {"canonical45_modified": False, "selection13_modified": False, "frozen_runner_modified": False},
        "installed": False, "runtime_qualified": False, "business_qualified": False, "production_ready": False,
        "native_compatibility_qualified": False, "all_39_latest_qualified": False, "all_39_runtime_accepted": False,
        "execution_authorized": False, "Android_calls": 0, "user_data_reads": 0, "credentials_reads": 0,
        "packages": plans,
    }
    validate_plan(result, documents)
    return result


def validate_plan(plan, documents):
    no_credit(plan)
    required = set(documents["release-scope.json"]["selected_packages"]) - EXEMPT
    rows = indexed(plan["packages"], "output plan")
    require(set(rows) == required, "output required39 mismatch")
    require(sum(p["finite_prepared_case_source_exists"] is True for p in rows.values()) == 7,
            "output cannot promote unimplemented packages")
    state_apps = indexed(documents["CURRENT-SOURCE-STATE.json"]["applications"], "state")
    registry = indexed(documents["current-source-inputs.json"]["applications"], "registry")
    require(plan.get("required_before_installation") == documents["CURRENT-SOURCE-STATE.json"]["required_before_installation"],
            "original installation prerequisites changed or omitted")
    require(rows[MEITUAN].get("migration_prerequisite") == "PENDING" and
            rows[MEITUAN].get("signer_migration_qualified") is False and
            rows[MEITUAN].get("migration_execution_authorized") is False,
            "Meituan migration prerequisite changed or omitted")
    for package, row in rows.items():
        require(row["finite_prepared_case_source_exists"] is (package in SELECTED), "output source-scope promotion")
        require(set(row["common_gate_ids"]) == COMMON, "output omitted a common gate")
        require(set(row["actual_runtime_bindings"]) == set(RUNTIME_BINDINGS) and
                all(v is None for v in row["actual_runtime_bindings"].values()), "fabricated or omitted runtime binding refused")
        expected = state_apps[package]["unchanged_original_system_record"] if package in SYSTEM else registry[package]
        require(row["source_version"] == expected["version_name"] and row["source_version_code"] == expected["version_code"],
                "output payload version promotion refused")
        require(row["source_body_pin_metadata"] == expected["apk" if package in SYSTEM else "input"], "output source pin mismatch")
    validate_firefox(rows[FIREFOX]["additive_checklist"])
    require(rows[FIREFOX]["driver_implemented"] is False, "Firefox checklist cannot become an implemented driver")


def write_new(path: Path, plan):
    """No parent creation, no replacement of existing files or symlinks."""
    data = (json.dumps(plan, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    return {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path(__file__).resolve().parent / "inputs")
    parser.add_argument("--out", type=Path, required=True, help="new JSON file in an existing directory")
    args = parser.parse_args(argv)
    try:
        documents, before = load_bundle(args.input_dir)
        plan = build_plan(documents)
        _, after = load_bundle(args.input_dir)
        require(before == after, "input F9 bookends changed before output")
        output = write_new(args.out, plan)
        print(json.dumps({"state": plan["state"], "output": output, "input_bookends_equal": True,
                          "Android_calls": 0, "runtime_qualified": False, "business_qualified": False, "production_ready": False}, sort_keys=True))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(json.dumps({"state": "REFUSED_NO_ACCEPTANCE", "error_type": type(error).__name__, "reason": str(error),
                          "runtime_qualified": False, "business_qualified": False, "production_ready": False}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
