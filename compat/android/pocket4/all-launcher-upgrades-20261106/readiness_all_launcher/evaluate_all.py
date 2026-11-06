#!/usr/bin/env python3
"""Offline acceptance of the reviewed 45-app catalogue; never a device runner.

The immutable eight-app evaluator remains an additional gate for those packages.
Receipts are content-addressed declarations, not self-authenticating proof: an
independent reviewer must inspect the original reports before freezing policy.
No resolver, APK verifier, installer, UI action or deletion runs here.
Revision 2 restores the source after executor loss and is tested independently.
"""
import argparse
import copy
import hashlib
import json
import sys
import types
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
PARENT = HERE.parent
PINS = {
    "evaluate_readiness.py": (39761, "d2efd3f1271ff843d7b99269efd979b475cf24b1102f4be18cc57bbaad62d2c9"),
    "regression_manifest.json": (27345, "3d5764e982a31692e77cf728cb4fa88e44c987b7f2d6dda65106741f952cf86e"),
    "app_test_catalog.json": (624217, "d16a51f06be2b4ba2b5a61991dd649d481d1fdf53ff1ccf570ea23367611cb19"),
}
SCHEMA = "pocket4-reviewed-launcher-catalog-evidence-v1"
POLICY_SCHEMA = "pocket4-reviewed-launcher-catalog-policy-v1"
DECISION_SCHEMA = "pocket4-reviewed-launcher-catalog-decision-v1"
UNKNOWN = "UNKNOWN_NOT_RUN"
MAX_JSON_BYTES = 32 * 1024 * 1024


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_JSON_key:" + key)
        result[key] = value
    return result


def decode(data):
    def reject(value):
        raise ValueError("nonfinite_JSON_number:" + value)
    return json.loads(data.decode("utf-8"), object_pairs_hook=strict_object,
                      parse_constant=reject)


def read_json(path):
    with Path(path).open("rb") as handle:
        data = handle.read(MAX_JSON_BYTES + 1)
    if len(data) > MAX_JSON_BYTES:
        raise ValueError("JSON_size_limit")
    return decode(data)


def frozen_sources():
    sources = {}
    for name, (size, expected) in PINS.items():
        with (PARENT / name).open("rb") as handle:
            data = handle.read(size + 1)
        if len(data) != size or hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("frozen_source_changed:" + name)
        sources[name] = data
    module = types.ModuleType("pocket4_frozen_eight_gate")
    module.__file__ = str(PARENT / "evaluate_readiness.py")
    exec(compile(sources["evaluate_readiness.py"], module.__file__, "exec"), module.__dict__)
    return module, decode(sources["regression_manifest.json"]), decode(sources["app_test_catalog.json"])


OLD, ORIGINAL_POLICY, CATALOG = frozen_sources()
digest, sha, integer, timestamp = OLD.digest, OLD.sha, OLD.integer, OLD.timestamp
unique_strings, hashes = OLD.unique_strings, OLD.hashes
APPS = {a["package"]: a for a in CATALOG["apps"]}
EXPECTED_COUNTS = (45, 136, 12)


def known(value):
    return (OLD.known(value) and not value.strip().upper().startswith("UNKNOWN")
            and value.strip().upper() not in ("NOT_RUN", "NOT_APPLICABLE", "NA", "SKIPPED"))


# Required observables, never declarations that a device/service actually exists.
NETWORK = {
    "vendor_https": (["app_network_trace", "vendor_business_response"],
        ["request_uid_correlated", "dns_or_verified_cache_observed", "normal_tls_validation_preserved", "response_matches_query", "error_path_verified"], "network"),
    "vendor_rtc": (["app_network_trace", "controlled_peer_receipt", "rtc_media_trace"],
        ["request_uid_correlated", "dns_or_verified_cache_observed", "normal_tls_validation_preserved", "signalling_session_verified", "text_peer_readback", "duplex_audio_verified", "normal_hangup_verified"], "network"),
    "public_media": (["app_network_trace", "media_timeline_readback"],
        ["request_uid_correlated", "dns_or_verified_cache_observed", "normal_tls_validation_preserved", "changing_frames_observed", "audio_output_observed", "playback_controls_verified"], "network"),
    "webview_https": (["webview_provider_identity", "app_network_trace", "dom_readback", "tls_negative_trace"],
        ["provider_renderer_current", "request_actor_correlated", "dns_or_verified_cache_observed", "normal_tls_validation_preserved", "dom_javascript_readback", "chinese_input_readback", "renderer_storage_persisted"], "network"),
    "offline_local": (["local_component_contract", "offline_state_trace", "local_operation_readback", "local_fault_trace"],
        ["local_data_source_verified", "core_completed_while_offline", "local_fault_recovered"], "offline_continuity"),
    "system_settings": (["system_service_readback", "offline_state_trace"],
        ["ui_service_fields_match", "offline_and_reconnected_state_refreshed", "local_fault_recovered"], "offline_continuity"),
    "local_search_with_delegation": (["search_provider_identity", "search_result_readback", "delegated_component_trace"],
        ["actual_provider_verified", "query_result_match", "executing_component_identified", "delegation_contract_resolved"], "delegated_service"),
    "cellular_telephony": (["telephony_service_identity", "controlled_peer_receipt", "telephony_failure_trace"],
        ["actual_legal_sim_or_phone_account_verified", "real_service_exchange_verified", "peer_delivery_verified", "service_fault_recovered"], "telephony_service"),
    "thread_ipv6_lan": (["thread_hardware_identity", "controlled_peer_receipt", "ipv6_exchange_trace"],
        ["radio_driver_service_available", "owned_dataset_and_border_router_verified", "ipv6_send_receive_verified", "thread_fault_recovered"], "thread_service"),
    "microg_service": (["service_source_identity", "microg_selfcheck", "controlled_local_client_receipt"],
        ["actual_services_and_failures_recorded", "enabled_api_callback_verified", "enabled_remote_services_resolved", "service_fault_recovered"], "configured_service"),
    "local_qa_contract": (["local_source_contract", "helper_attestation", "nonce_probe_readback", "offline_state_trace"],
        ["declared_protocol_verified", "current_helper_and_uid_verified", "fresh_nonce_probe_verified", "stale_identity_rejected", "offline_continuity_verified"], "offline_continuity"),
    "local_ime": (["ime_input_connection_identity", "ime_composition_trace", "ime_commit_readback", "offline_state_trace"],
        ["current_ime_and_editor_verified", "actual_key_candidate_commit_observed", "utf8_target_readback_matches", "focus_switch_recovered", "offline_chinese_input_verified"], "offline_continuity"),
}
PROFILE_KINDS = {
    "bound_action_and_readback": ["action_receipt", "ui_hierarchy", "operation_readback"],
    "current_official_artifact_and_install_identity": ["complete_apk_manifest", "apk_signature_verification", "installed_package_identity"],
    "official_artifact": ["complete_apk_manifest", "source_or_release_provenance"],
    "vendor_response": ["app_network_trace", "vendor_business_response"],
    "authorized_session": ["session_authorization", "session_result"],
    "controlled_peer_receipt": ["explicit_test_peer_authorization", "controlled_peer_receipt"],
    "controlled_local_peer": ["local_peer_identity", "local_peer_action_receipt"],
    "storage_readback": ["app_storage_readback", "data_directory_identity"],
    "permission_snapshot": ["permission_snapshot_before", "permission_snapshot_after", "permission_denial_trace"],
    "media_hardware": ["hardware_capability", "media_timeline_readback"],
    "media_store_readback": ["media_store_metadata", "decoded_fixture_readback"],
    "provider_readback": ["provider_identity", "provider_record_readback"],
    "scoped_file_roundtrip": ["scoped_uri_identity", "file_roundtrip_readback", "scoped_access_denial"],
    "notification_delivery": ["notification_trigger", "notification_delivery_readback"],
    "monotonic_timing": ["monotonic_clock_trace", "app_timer_readback"],
    "system_service_readback": ["system_service_identity", "system_service_readback"],
    "hardware_capability": ["hardware_capability", "hardware_operation_readback"],
    "delegated_component": ["delegated_component_identity", "delegated_result_readback"],
    "local_source_contract": ["local_source_contract", "source_build_install_mapping"],
    "helper_binding": ["helper_attestation", "nonce_probe_readback"],
    "ime_commit": ["ime_input_connection_identity", "ime_composition_trace", "ime_commit_readback"],
}
KINDS = {
    "startup": ["runtime_log", "ui_hierarchy"],
    "login_or_guest": ["runtime_log", "ui_hierarchy", "session_authorization"],
    "core": ["runtime_log", "ui_hierarchy"],
    "network": ["network_profile_trace"],
    "storage": ["app_storage_readback"],
    "permissions": ["permission_snapshot_before", "permission_snapshot_after"],
    "integrity": ["integrity_and_security_trace"],
    "soak": ["continuous_soak_trace", "resource_budget_evaluation"],
    "restart": ["app_restart_trace"],
    "fault_recovery": ["app_fault_recovery_trace"],
}


def contract(case):
    return {k: v for k, v in case.items() if k != "actual_result"}


def artifact_mode(row):
    kind = row["classification"]
    if kind.startswith("framework_owned_"):
        return "qualified_framework_build"
    if kind == "local_owner_built_QA":
        return "reviewed_owner_source_build"
    return "official_release"


def make_policy():
    policy = copy.deepcopy(ORIGINAL_POLICY)
    pending_identity = {key: None if key.endswith("sha256") else value
                        for key, value in ORIGINAL_POLICY["required_runtime_identity"].items()}
    policy.update(schema=POLICY_SCHEMA, required_runtime_identity=pending_identity,
                  reviewed_helpers=None, catalog_sha256=PINS["app_test_catalog.json"][1],
                  frozen_inputs={k: {"bytes": v[0], "sha256": v[1]} for k, v in PINS.items()},
                  reference_catalog_is_fresh_resolver=False)
    policy.pop("current_observation", None)
    policy["review"] = {"status": "UNKNOWN", "receipt_sha256": None,
                        "note": "Fill from reviewed actual successor/helper and artifact evidence; a template grants no admission."}
    for package, row in APPS.items():
        rule = policy["apps"].get(package)
        if rule is None:
            hosts = sorted({urlsplit(u).hostname for u in row["update_acceptance"]["authoritative_source_urls_from_existing_research"]
                            if isinstance(u, str) and urlsplit(u).scheme == "https" and urlsplit(u).hostname})
            mode = row["authentication"]["planned_mode"]
            rule = {"core_definition_status": "defined", "core_flows": {c["id"]: c["operation"] for c in row["core_cases"]},
                    "allowed_session_modes": (["no_service_login"] if mode == "no_service_login_for_planned_local_core"
                                              else ["login"] if mode == "authorized_login_required_for_core" else ["login", "guest"]),
                    "requires_authorized_test_peer": any("controlled_peer_receipt" in c["required_evidence_profiles"] for c in row["core_cases"]),
                    "official_hosts": hosts, "latest_candidate_pin": {"version_name": None, "source_url": None},
                    "vendor_trust": {"status": "unknown", "allowed_signer_sets": [], "provenance": None}}
            policy["apps"][package] = rule
        rule.update(artifact_mode=artifact_mode(row),
                    catalog_contract_sha256=digest({k: row[k] for k in ("classification", "core_cases", "network", "hardware", "test_inputs_needed")}),
                    installed_artifact_pin={"version_code": None, "apk_sha256s": None},
                    online_branch_review={"status": "unknown", "configuration_sha256": None,
                                          "enabled_branch_ids": None, "proof_sha256s": []},
                    input_nonrequirement_reviews={},
                    build_trust={"status": "unknown", "source_lock_sha256": None,
                                 "build_manifest_sha256": None, "source_revision": None,
                                 "allowed_signer_sets": [], "provenance_sha256s": []})
    return policy


def unknown_record(**extra):
    return dict(status=UNKNOWN, scope="unknown", binding=None, evidence_refs=[], **extra)


def make_template(policy):
    evidence = OLD.make_template(policy)
    evidence.update(schema=SCHEMA, catalog_sha256=PINS["app_test_catalog.json"][1],
                    template_only=True, source="UNEXECUTED_SCHEMA_TEMPLATE")
    evidence["runtime"]["identity"] = copy.deepcopy(policy["required_runtime_identity"])
    evidence["launcher_inventory"].update(query_started_at=None, query_finished_at=None,
                                          cache_bypassed=None, resolver_generation_sha256=None)
    for package, row in APPS.items():
        app = evidence["apps"].get(package)
        if app is None:
            app = {"current_identity": {"package": package, "android_user": 0, "uid": None,
                    "version_name": None, "version_code": None, "apk_sha256s": None, "signer_sha256s": None},
                   "identity_before": None, "identity_after": None,
                   "identity_verification": unknown_record(native_runtime_mapping_verified=None),
                   "official_candidate": copy.deepcopy(evidence["apps"]["com.Hyatt.hyt"]["official_candidate"]),
                   "source_candidate": unknown_record(mode=artifact_mode(row), apks=[]),
                   "checks": {name: unknown_record() for name in OLD.CHECKS}}
            app["checks"]["core"]["flows"] = {c["id"]: unknown_record(actual_outcome=None, expected_outcome_observed=None) for c in row["core_cases"]}
            app["checks"]["restart"]["cycles"] = []
            app["checks"]["fault_recovery"].update(network_cycles=[], dependency_cycles=[])
            evidence["apps"][package] = app
        app["catalog_checks"] = {
            "cases": {c["id"]: unknown_record(case_contract_sha256=digest(contract(c)), actual_outcome=None,
                        expected_outcome_observed=None, observed_step_sha256s=[],
                        profiles={p: unknown_record(actual_observation=None, verified=None) for p in sorted(set(c["required_evidence_profiles"]))})
                      for c in row["core_cases"]},
            "network": unknown_record(profile=row["network"]["profile"], branch_inventory=None, branches={}),
            "inputs": {i["id"]: unknown_record(state=UNKNOWN, actual_input_identity_sha256=None) for i in row["test_inputs_needed"]},
            "hardware": {str(i): unknown_record(requirement_sha256=digest(h), actual_state=UNKNOWN) for i, h in enumerate(row["hardware"]["requirements"])},
            "data_identity": unknown_record(before=None, after=None),
            "runtime_restart": unknown_record(previous_epoch_sha256=None, current_epoch_core_repeated=None),
            "permission_contract": unknown_record(),
            "failure_ledger": unknown_record(unresolved_items=None),
        }
    return evidence


class Audit(OLD.Audit):
    def policy_gates(self):
        expected = make_policy()
        self.need(self.policy.get("schema") == POLICY_SCHEMA, "policy.schema", "policy_schema_required")
        self.need(self.policy.get("frozen_inputs") == expected["frozen_inputs"]
                  and self.policy.get("catalog_sha256") == expected["catalog_sha256"], "policy.frozen_inputs", "immutable_input_pins_changed")
        self.need(self.policy.get("historical_roster_sha256") == OLD.ROSTER_SHA
                  and self.policy.get("historical_eight_packages") == ORIGINAL_POLICY["historical_eight_packages"], "policy.historical_subset", "original_eight_scope_changed")
        for key in ("safety_rules", "execution_policy"):
            self.need(self.policy.get(key) == ORIGINAL_POLICY[key], "policy." + key, "original_safety_and_execution_boundary_changed")
        self.need(self.policy.get("scope") == ORIGINAL_POLICY["scope"], "policy.scope", "all_current_launchers_and_framework_required")
        review = self.obj(self.policy.get("review"), "policy.review")
        self.need(review.get("status") == "reviewed" and sha(review.get("receipt_sha256")), "policy.review", "independent_reviewed_policy_required")
        thresholds = self.obj(self.policy.get("proposed_acceptance_thresholds"), "policy.thresholds")
        for key in ("continuous_soak_seconds", "app_restart_cycles", "network_recovery_cycles"):
            self.need(integer(thresholds.get(key), ORIGINAL_POLICY["proposed_acceptance_thresholds"][key]), "policy.thresholds." + key, "acceptance_threshold_must_not_be_reduced")
        self.need(thresholds.get("runtime_restart_requalification_required") is True, "policy.thresholds", "qualified_runtime_restart_remains_required")
        rules = self.obj(self.policy.get("apps"), "policy.apps")
        self.need(set(rules) == set(APPS), "policy.apps", "reviewed_catalog_policy_package_set_mismatch")
        for package, row in APPS.items():
            rule = self.obj(rules.get(package), "policy.apps." + package)
            for key in ("core_definition_status", "core_flows", "allowed_session_modes", "requires_authorized_test_peer", "artifact_mode", "catalog_contract_sha256"):
                self.need(rule.get(key) == expected["apps"][package].get(key), "policy.apps." + package + "." + key, "reviewed_core_session_or_artifact_contract_changed")
            if package in OLD.HISTORICAL_PACKAGES:
                self.need(rule.get("official_hosts") == ORIGINAL_POLICY["apps"][package]["official_hosts"],
                          "policy.apps." + package + ".official_hosts", "original_eight_official_source_boundary_changed")
        counts = (len(APPS), sum(len(a["core_cases"]) for a in APPS.values()), len({a["network"]["profile"] for a in APPS.values()}))
        self.need(counts == EXPECTED_COUNTS and set(NETWORK) == {a["network"]["profile"] for a in APPS.values()}
                  and set(PROFILE_KINDS) == set(CATALOG["evidence_profiles"]), "catalog", "unreviewed_catalog_contract_or_profile")

    def scope_gate(self, packages):
        apps = self.obj(self.evidence.get("apps"), "apps")
        added, absent = sorted(packages - set(APPS)), sorted(set(APPS) - packages)
        self.need(not added and not absent, "launcher_inventory.catalog_comparison", "fresh_resolver_catalog_delta_requires_review:" + json.dumps({"added": added, "absent": absent}, separators=(",", ":")))
        self.need(set(apps) == packages, "apps", "every_current_resolver_package_requires_evidence_no_silent_omission")
        return added, absent

    def inventory(self, binding):
        packages = super().inventory(binding)
        inv = self.obj(self.evidence.get("launcher_inventory"), "launcher_inventory")
        self.need(inv.get("cache_bypassed") is True and sha(inv.get("resolver_generation_sha256")), "launcher_inventory", "fresh_complete_resolver_not_cached_native_launcher_list_required")
        start, end, collected = (timestamp(inv.get("query_started_at")), timestamp(inv.get("query_finished_at")), timestamp(self.evidence.get("collected_at")))
        self.need(start is not None and end is not None and collected is not None and start <= end <= collected, "launcher_inventory", "actual_query_interval_and_collection_time_required")
        return packages

    def permission_checks(self, record, package, bound, path):
        self.true(record, ["required_permission_path_verified", "denied_permission_path_verified", "no_unauthorized_grants"], path)
        values = [record.get(x) for x in ("grants_before", "grants_after", "active_grants")]
        for value in values:
            self.need(unique_strings(value, nonempty=False), path, "explicit_observed_permission_lists_required")
        if all(unique_strings(x, nonempty=False) for x in values):
            before, after, active = map(set, values)
            if package == "com.sankuai.meituan.takeoutnew":
                self.need(not (OLD.LOCATION & (active | (after - before))), path, "Meituan_proactive_location_grant_forbidden")
            if active or before != after:
                self.refs(record.get("change_authorization_refs"), path, ["permission_change_authorization"], bound)

    def lifecycle(self, checks, bound, row, path):
        thresholds = self.policy["proposed_acceptance_thresholds"]
        soak = self.record(checks.get("soak"), path + ".soak", bound, KINDS["soak"])
        start, end = timestamp(soak.get("started_at")), timestamp(soak.get("finished_at"))
        self.need(start is not None and end is not None and (end - start).total_seconds() >= thresholds["continuous_soak_seconds"], path + ".soak", "continuous_soak_below_threshold_or_unknown")
        self.need(integer(soak.get("active_monitor_seconds"), thresholds["continuous_soak_seconds"]) and integer(soak.get("sample_count"), 3), path + ".soak", "continuous_resource_observation_required")
        self.true(soak, ["continuous_probe_coverage", "resource_budget_met", "core_still_usable"], path + ".soak")
        self.need(type(soak.get("crashes")) is int and soak["crashes"] == 0 and type(soak.get("anrs")) is int and soak["anrs"] == 0, path + ".soak", "crash_ANR_or_unknown")
        recovery = self.record(checks.get("fault_recovery"), path + ".fault_recovery", bound, KINDS["fault_recovery"])
        self.true(recovery, ["process_death_recovered", "no_security_bypass"], path + ".fault_recovery")
        restart = self.record(checks.get("restart"), path + ".restart", bound, KINDS["restart"])
        dependency = NETWORK[row["network"]["profile"]][2]
        field = "network_cycles" if dependency == "network" else "dependency_cycles"
        for name, record, cycle_field, threshold in (("restart", restart, "cycles", "app_restart_cycles"), ("fault_recovery", recovery, field, "network_recovery_cycles")):
            cycles = record.get(cycle_field)
            if not self.need(isinstance(cycles, list) and len(cycles) >= thresholds[threshold], path + "." + name, "three_or_policy_minimum_actual_cycles_required"):
                cycles = []
            ids = []
            for index, item in enumerate(cycles):
                p = path + "." + name + "." + str(index)
                cycle = self.record(item, p, bound, ["app_restart_trace" if name == "restart" else "app_fault_recovery_trace"])
                ids.append(cycle.get("cycle_id"))
                self.true(cycle, ["core_resumed", "data_preserved"], p)
                if name == "restart":
                    self.need(sha(cycle.get("before_process_identity_sha256")) and sha(cycle.get("after_process_identity_sha256")) and cycle["before_process_identity_sha256"] != cycle["after_process_identity_sha256"], p, "actual_process_restart_required")
                elif dependency == "network":
                    self.true(cycle, ["offline_observed", "online_observed"], p)
                else:
                    self.need(cycle.get("dependency_kind") == dependency, p, "actual_profile_specific_dependency_required")
                    self.true(cycle, ["fault_effect_observed", "recovery_observed"], p)
                    self.need(known(cycle.get("actual_fault")) and known(cycle.get("actual_recovery")), p, "actual_local_or_service_failure_and_recovery_required")
                    if dependency == "offline_continuity":
                        self.true(cycle, ["offline_observed", "online_observed", "local_core_continued"], p)
            self.need(unique_strings(ids), path + "." + name, "distinct_cycle_ids_required")

    def source_artifact(self, app, rule, identity, bound, android_api, path):
        mode = rule["artifact_mode"]
        if mode == "official_release":
            self.artifact(app, rule, identity, bound, android_api, path)
            return
        value = self.record(app.get("source_candidate"), path + ".source_candidate", bound,
                            ["source_lock", "build_manifest", "source_build_install_mapping", "complete_apk_manifest"])
        self.need(value.get("mode") == mode, path, "source_artifact_mode_mismatch")
        self.true(value, ["latest_final_source_for_target_verified", "complete_apk_set_obtained", "installed_apk_set_equal", "build_succeeded", "source_build_install_mapping_verified"], path + ".source_candidate")
        trust = self.obj(rule.get("build_trust"), path + ".policy.build_trust")
        self.need(trust.get("status") == "reviewed", path, "independently_reviewed_build_source_and_signer_required")
        for key in ("source_lock_sha256", "build_manifest_sha256"):
            self.need(sha(trust.get(key)) and value.get(key) == trust.get(key), path + "." + key, "reviewed_source_build_pin_mismatch")
        self.need(known(trust.get("source_revision")) and value.get("source_revision") == trust.get("source_revision"), path, "source_revision_unknown_or_mismatch")
        sets = trust.get("allowed_signer_sets")
        self.need(isinstance(sets, list) and bool(sets) and all(hashes(s) for s in sets)
                  and hashes(identity.get("signer_sha256s")) and sorted(identity["signer_sha256s"]) in [sorted(s) for s in sets], path, "source_build_signer_not_independently_authorized")
        self.refs(value.get("provenance_refs"), path + ".provenance_refs", ["source_build_provenance"])
        actual_provenance = [self.references.get(i, {}).get("sha256") for i in value.get("provenance_refs", [])]
        self.need(hashes(trust.get("provenance_sha256s")) and any(s in trust["provenance_sha256s"] for s in actual_provenance), path, "independently_pinned_build_provenance_required")
        if mode == "qualified_framework_build":
            framework = self.obj(self.evidence.get("framework"), "framework")
            self.need(value.get("framework_source_revision") == framework.get("source_revision") and value.get("framework_artifact_set_sha256") == digest(framework.get("artifact_sha256s")), path, "system_package_must_map_to_actual_qualified_framework")
        else:
            self.need(value.get("helper_identity_sha256") == bound["helper_identity_sha256"], path, "owner_QA_build_requires_current_helper_binding")
        apks = value.get("apks")
        if not self.need(isinstance(apks, list) and bool(apks), path, "complete_source_build_base_and_splits_required"):
            apks = []
        seen_hashes, splits = [], []
        for index, raw in enumerate(apks):
            p = path + ".source_candidate.apks." + str(index)
            apk = self.obj(raw, p)
            self.need(sha(apk.get("sha256")) and integer(apk.get("bytes"), 1) and known(apk.get("split_name")), p, "full_APK_hash_size_and_split_required")
            self.need(apk.get("package") == identity.get("package") and apk.get("version_code") == identity.get("version_code"), p, "APK_identity_mismatch")
            seen_hashes.append(apk.get("sha256"))
            splits.append(apk.get("split_name"))
            sig = self.obj(apk.get("signature"), p + ".signature")
            self.true(sig, ["verified", "full_apk_checked", "held_file_unchanged", "verifier_joined"], p)
            self.need(sig.get("tool") == "apksigner" and type(sig.get("tool_exit_code")) is int and sig["tool_exit_code"] == 0 and sig.get("timed_out") is False, p, "actual_complete_APK_verification_required")
            self.need(sig.get("signer_sha256s") == identity.get("signer_sha256s") and any(sig.get("verified_schemes", {}).get(s) is True for s in ("v1", "v2", "v3", "v3.1", "v4")), p, "verified_signature_and_expected_signer_required")
            self.refs(sig.get("evidence_refs"), p, ["apk_signature_verification"], bound)
            if apk.get("split_name") == "base":
                self.need(integer(apk.get("min_sdk"), 1) and integer(android_api, 1) and apk["min_sdk"] <= android_api, p, "min_sdk_unsupported_or_unknown")
        self.need(hashes(seen_hashes) and sorted(seen_hashes) == sorted(identity.get("apk_sha256s") or []), path, "full_installed_APK_set_mismatch")
        self.need(unique_strings(splits) and splits.count("base") == 1, path, "one_base_unique_splits_required")

    def local_app(self, package, app, binding, android_api):
        path, row, rule = "apps." + package, APPS[package], self.policy["apps"][package]
        identity = self.obj(app.get("current_identity"), path + ".current_identity")
        version = known(identity.get("version_name")) or (identity.get("version_name") is None and identity.get("version_name_state") == "absent_in_verified_manifest")
        self.need(identity.get("package") == package and integer(identity.get("uid"), 1)
                  and type(identity.get("android_user")) is int and identity["android_user"] == 0
                  and integer(identity.get("version_code"), 0) and version
                  and hashes(identity.get("apk_sha256s")) and hashes(identity.get("signer_sha256s")), path, "current_system_or_QA_identity_required_zero_versionCode_is_valid_only_if_observed")
        self.need(app.get("identity_before") == identity and app.get("identity_after") == identity, path, "current_identity_changed_rerun_required")
        bound = dict(binding, app_identity_sha256=digest(identity))
        identity_record = self.record(app.get("identity_verification"), path + ".identity_verification", bound, ["installed_package_identity", "native_runtime_mapping", "verified_manifest_metadata"])
        self.true(identity_record, ["native_runtime_mapping_verified", "complete_manifest_read"], path + ".identity_verification")
        self.source_artifact(app, rule, identity, bound, android_api, path)
        checks = self.obj(app.get("checks"), path + ".checks")
        self.need(set(checks) == set(OLD.CHECKS), path + ".checks", "all_required_common_checks_required")
        records = {k: self.record(checks.get(k), path + ".checks." + k, bound, v) for k, v in KINDS.items()}
        self.true(records["startup"], ["responsive_first_screen", "no_crash_or_anr"], path)
        session = records["login_or_guest"]
        self.need(session.get("mode") in rule["allowed_session_modes"], path, "actual_session_mode_must_match_reviewed_contract")
        self.true(session, ["session_usable", "session_authorized"], path)
        if session.get("mode") == "no_service_login":
            self.refs(session.get("local_contract_refs"), path, ["local_component_contract"], bound)
            self.true(session, ["no_service_login_contract_verified"], path)
        flows = self.obj(records["core"].get("flows"), path + ".checks.core.flows")
        self.need(set(flows) == set(rule["core_flows"]), path, "exact_defined_local_core_flows_required")
        for key in rule["core_flows"]:
            flow = self.record(flows.get(key), path + ".checks.core.flows." + key, bound, ["runtime_log", "ui_hierarchy"])
            self.true(flow, ["expected_outcome_observed"], path)
            self.need(known(flow.get("actual_outcome")), path, "actual_local_core_outcome_required")
        self.true(records["storage"], ["app_read_write_readback_verified", "data_survives_restart"], path)
        self.permission_checks(records["permissions"], package, bound, path + ".checks.permissions")
        self.true(records["integrity"], ["source_and_platform_security_clear", "effective_security_constraints_preserved"], path)
        self.false(records["integrity"], ["integrity_or_other_security_bypass_used"], path)
        self.lifecycle(checks, bound, row, path + ".checks")
        return bound

    def proof(self, value, path, bound, kinds):
        proof = self.record(value, path, bound, kinds)
        self.true(proof, ["verified"], path)
        self.need(known(proof.get("actual_observation")), path, "actual_observation_required_UNKNOWN_or_NA_is_not_evidence")
        return proof

    def network_profile(self, value, row, rule, bound, path):
        name = row["network"]["profile"]
        kinds, fields, _ = NETWORK[name]
        record = self.record(value, path, bound, kinds)
        self.need(record.get("profile") == name, path, "network_profile_mismatch")
        self.true(record, fields, path)
        self.false(record, ["tls_or_integrity_bypass_used", "source_or_endpoint_spoofed"], path)
        if row["network"]["app_owned_DNS_TLS_requirement"] != "required_for_vendor_request_path":
            self.need("app_level_dns_tls_response_verified" not in record, path, "local_or_service_proof_must_not_fabricate_app_owned_DNS_TLS")
        review = self.obj(rule.get("online_branch_review"), path + ".policy.online_branch_review")
        inventory = self.record(record.get("branch_inventory"), path + ".branch_inventory", bound, ["enabled_feature_configuration", "network_applicability_contract"])
        self.true(inventory, ["complete", "disabled_is_not_missing_capability"], path + ".branch_inventory")
        branches = self.obj(record.get("branches"), path + ".branches")
        ids = inventory.get("enabled_branch_ids")
        self.need(unique_strings(ids, nonempty=False) and set(ids) == set(branches), path, "all_actual_enabled_online_branches_require_evidence")
        self.need(review.get("status") == "reviewed" and sha(review.get("configuration_sha256"))
                  and inventory.get("configuration_sha256") == review.get("configuration_sha256")
                  and ids == review.get("enabled_branch_ids"), path, "independent_actual_configuration_and_applicability_review_required")
        self.need(hashes(review.get("proof_sha256s")) and any(self.references.get(i, {}).get("sha256") in review["proof_sha256s"] for i in inventory.get("evidence_refs", [])), path, "configuration_review_proof_not_pinned")
        for branch, raw in branches.items():
            proof = self.proof(raw, path + ".branches." + branch, bound, ["actual_transport_actor_identity", "applicable_transport_trace"])
            self.true(proof, ["actual_actor_verified", "real_response_or_callback_verified", "fault_recovery_verified", "normal_security_preserved"], path + ".branches." + branch)

    def catalog_app(self, package, value, binding, android_api):
        path, row = "apps." + package, APPS[package]
        app = self.obj(value, path)
        rule = self.policy["apps"][package]
        if row["classification"] == "third_party_commercial":
            # The original eight take their unchanged complete app gate.
            super().app(package, app, binding, android_api)
            identity = self.obj(app.get("current_identity"), path + ".current_identity")
            self.need(known(identity.get("version_name")), path + ".current_identity.version_name", "actual_version_name_required_not_UNKNOWN_placeholder")
            bound = dict(binding, app_identity_sha256=digest(identity))
        else:
            bound = self.local_app(package, app, binding, android_api)
            identity = self.obj(app.get("current_identity"), path + ".current_identity")
        pin = self.obj(rule.get("installed_artifact_pin"), path + ".policy.installed_artifact_pin")
        self.need(integer(pin.get("version_code"), 0) and pin.get("version_code") == identity.get("version_code")
                  and hashes(pin.get("apk_sha256s")) and pin.get("apk_sha256s") == identity.get("apk_sha256s"), path, "reviewed_complete_installed_artifact_pin_required_not_release_metadata")
        ext = self.obj(app.get("catalog_checks"), path + ".catalog_checks")
        cases = self.obj(ext.get("cases"), path + ".catalog_checks.cases")
        self.need(set(cases) == {c["id"] for c in row["core_cases"]}, path, "all_catalog_cases_required_no_missing_or_NA_case")
        for case in row["core_cases"]:
            p = path + ".catalog_checks.cases." + case["id"]
            record = self.record(cases.get(case["id"]), p, bound, ["action_receipt", "ui_hierarchy", "operation_readback"])
            self.need(record.get("case_contract_sha256") == digest(contract(case)), p, "case_contract_changed")
            self.true(record, ["expected_outcome_observed"], p)
            self.need(known(record.get("actual_outcome")), p, "actual_case_outcome_required")
            self.need(record.get("observed_step_sha256s") == [digest(step) for step in case["steps"]], p, "every_planned_step_requires_actual_observation")
            profiles = self.obj(record.get("profiles"), p + ".profiles")
            expected = set(case["required_evidence_profiles"])
            self.need(set(profiles) == expected, p, "all_case_specific_profiles_required")
            for profile in sorted(expected):
                proof = self.proof(profiles.get(profile), p + ".profiles." + profile, bound, PROFILE_KINDS[profile])
                if profile == "controlled_peer_receipt":
                    self.true(proof, ["explicit_communication_authorized", "owned_controlled_peer_verified", "both_sides_observed", "nonce_and_time_correlated"], p)
                elif profile == "authorized_session":
                    self.true(proof, ["authorized_session_observed", "normal_authentication_succeeded"], p)
                elif profile == "ime_commit":
                    self.true(proof, ["actual_IME_composition_and_commit", "target_utf8_readback_matches"], p)
                    self.false(proof, ["direct_edit_injection_counted_as_IME"], p)
                elif profile in ("hardware_capability", "media_hardware"):
                    self.true(proof, ["actual_hardware_available", "real_operation_verified"], p)
        self.network_profile(ext.get("network"), row, rule, bound, path + ".catalog_checks.network")
        inputs = self.obj(ext.get("inputs"), path + ".catalog_checks.inputs")
        self.need(set(inputs) == {i["id"] for i in row["test_inputs_needed"]}, path, "every_declared_input_must_be_resolved")
        for item in row["test_inputs_needed"]:
            p = path + ".catalog_checks.inputs." + item["id"]
            record = self.record(inputs.get(item["id"]), p, bound, ["test_input_contract"])
            if record.get("state") == "supplied":
                self.need(sha(record.get("actual_input_identity_sha256")), p, "input_identity_reference_required_no_secrets")
                self.true(record, ["available", "use_authorized"], p)
                if item["kind"] in ("controlled_peer", "test_account", "secret_test_input", "test_service"):
                    self.refs(record.get("authorization_refs"), p, ["explicit_test_input_authorization"], bound)
            else:
                review = rule.get("input_nonrequirement_reviews", {}).get(item["id"], {})
                self.need(record.get("state") == "not_required_by_verified_contract" and review.get("status") == "reviewed"
                          and sha(review.get("proof_sha256")) and record.get("proof_sha256") == review.get("proof_sha256"), p, "missing_input_is_UNKNOWN_not_NA_requires_independent_contract_proof")
                self.refs(record.get("applicability_refs"), p, ["actual_input_applicability"], bound)
                self.need(any(self.references.get(i, {}).get("sha256") == review.get("proof_sha256") for i in record.get("applicability_refs", [])), p, "nonrequirement_proof_pin_not_present")
                self.true(record, ["all_planned_core_cases_still_executed", "absence_not_caused_by_missing_account_hardware_or_failure"], p)
        hardware = self.obj(ext.get("hardware"), path + ".catalog_checks.hardware")
        self.need(set(hardware) == {str(i) for i in range(len(row["hardware"]["requirements"]))}, path, "every_hardware_requirement_must_be_observed")
        for index, requirement in enumerate(row["hardware"]["requirements"]):
            p = path + ".catalog_checks.hardware." + str(index)
            record = self.proof(hardware.get(str(index)), p, bound, ["hardware_capability", "hardware_operation_readback"])
            self.need(record.get("requirement_sha256") == digest(requirement) and record.get("actual_state") == "available", p, "missing_required_hardware_is_blocking_not_NA")
            self.true(record, ["all_required_components_available", "actual_core_operation_verified"], p)
            if requirement["required"] in ("audio_required_video_conditional", "conditional_on_actual_location_scope"):
                self.refs(record.get("conditional_scope_refs"), p, ["actual_hardware_scope_contract"], bound)
                self.true(record, ["optional_scope_resolved_without_waiving_required_core"], p)
        data = self.record(ext.get("data_identity"), path + ".catalog_checks.data_identity", bound, ["data_directory_identity", "storage_provider_identity"])
        self.need(isinstance(data.get("before"), dict) and bool(data["before"]) and data.get("after") == data["before"], path, "UID_CE_DE_or_actual_provider_data_identity_must_be_preserved")
        storage = self.obj(data.get("before"), path + ".catalog_checks.data_identity.before")
        self.need(type(storage.get("app_uid")) is int and storage.get("app_uid") == identity.get("uid")
                  and type(storage.get("android_user")) is int and storage["android_user"] == 0
                  and storage.get("storage_model") in ("private_data", "shared_provider", "configuration_provider"), path, "actual_UID_user_and_storage_model_required")
        for label in ("ce", "de"):
            item = self.obj(storage.get(label), path + ".catalog_checks.data_identity.before." + label)
            self.need(item.get("state") in ("present", "absent_verified"), path, "CE_DE_absence_requires_actual_proof_not_UNKNOWN")
            if item.get("state") == "present":
                self.need(integer(item.get("device"), 0) and integer(item.get("inode"), 1)
                          and type(item.get("uid")) is int and item.get("uid") == identity.get("uid"), path, "actual_CE_DE_device_inode_UID_required")
            elif item.get("state") == "absent_verified":
                self.true(data, ["storage_contract_explains_observed_absence"], path)
                self.refs(data.get("absence_contract_refs"), path, ["actual_storage_contract"], bound)
        if storage.get("storage_model") != "private_data":
            providers = storage.get("providers")
            self.need(isinstance(providers, list) and bool(providers)
                      and all(isinstance(p, dict) and known(p.get("package")) and integer(p.get("uid"), 1)
                              and known(p.get("component")) and sha(p.get("identity_sha256")) for p in providers), path, "actual_shared_or_configuration_provider_identity_required")
        self.true(data, ["actual_storage_owners_verified", "no_user_data_clear", "fixture_persistence_verified"], path)
        permission = self.record(ext.get("permission_contract"), path + ".catalog_checks.permission_contract", bound, ["verified_manifest_metadata", "permission_snapshot_before", "permission_snapshot_after", "appops_role_snapshot", "permission_denial_trace"])
        self.true(permission, ["complete_requested_and_effective_state_observed", "absent_record_not_assumed_denied", "denial_and_legal_recovery_verified", "no_unauthorized_permission_change"], path)
        reboot = self.record(ext.get("runtime_restart"), path + ".catalog_checks.runtime_restart", bound, ["runtime_restart_trace", "runtime_qualification", "app_storage_readback", "current_epoch_core_repeat"])
        previous = self.evidence.get("runtime", {}).get("restart_requalification", {}).get("previous_epoch_sha256")
        self.need(sha(previous) and reboot.get("previous_epoch_sha256") == previous, path, "actual_predecessor_epoch_required")
        self.true(reboot, ["same_installed_version_and_UID", "data_identity_preserved", "current_epoch_core_repeated", "current_epoch_fixture_readback_matches"], path)
        ledger = self.record(ext.get("failure_ledger"), path + ".catalog_checks.failure_ledger", bound, ["resolution_ledger", "integrity_and_security_trace"])
        self.need(ledger.get("unresolved_items") == [], path, "unresolved_unknown_account_integrity_hardware_or_action_blocks_readiness")
        self.true(ledger, ["original_unknown_and_failure_evidence_retained", "all_actions_joined_and_settled", "effective_security_constraints_preserved"], path)
        self.false(ledger, ["integrity_bypass_used", "consent_or_permission_scope_expanded", "unknown_replayed_as_success"], path)


def evaluate(evidence, policy):
    audit = Audit(evidence, policy)
    universe = set(APPS)
    if isinstance(evidence, dict):
        provided_apps = evidence.get("apps")
        if isinstance(provided_apps, dict):
            universe.update(p for p in provided_apps if isinstance(p, str))
        provided_inventory = evidence.get("launcher_inventory")
        if isinstance(provided_inventory, dict) and isinstance(provided_inventory.get("rows"), list):
            universe.update(row["package"] for row in provided_inventory["rows"]
                            if isinstance(row, dict) and isinstance(row.get("package"), str))
    try:
        audit.need(isinstance(evidence, dict) and evidence.get("schema") == SCHEMA, "schema", "evidence_schema_required")
        audit.need(evidence.get("template_only") is False, "template_only", "UNKNOWN_template_is_not_runtime_evidence")
        audit.need(evidence.get("catalog_sha256") == PINS["app_test_catalog.json"][1]
                   and evidence.get("historical_roster_sha256") == OLD.ROSTER_SHA, "catalog_sha256", "exact_reviewed_catalog_and_original_roster_required")
        audit.need(timestamp(evidence.get("collected_at")) is not None, "collected_at", "actual_collection_time_required")
        audit.policy_gates()
        binding, runtime = audit.runtime()
        audit.need(runtime.get("helpers") == policy.get("reviewed_helpers"), "runtime.helpers", "independent_current_helper_pin_required")
        runtime_ready = not audit.errors
        before = len(audit.errors)
        packages = audit.inventory(binding)
        inventory_complete = runtime_ready and len(audit.errors) == before
        added, absent = audit.scope_gate(packages)
        audit.framework(binding)
        global_ready = not audit.errors
        global_errors = list(audit.errors)
        supplied = audit.obj(evidence.get("apps"), "apps")
        results = {}
        for package in sorted(set(APPS) | packages | set(supplied)):
            start = len(audit.errors)
            if package not in APPS:
                audit.need(False, "apps." + package, "fresh_package_requires_catalog_contract_and_reviewed_policy_no_generic_PASS")
            else:
                audit.catalog_app(package, supplied.get(package), binding, runtime.get("android_api"))
            errors = audit.errors[start:]
            results[package] = {"status": "pass" if global_ready and not errors else UNKNOWN if evidence.get("template_only") else "blocked",
                                "production_ready": global_ready and not errors,
                                "global_gates_passed": global_ready, "blockers": errors}
        ready = global_ready and bool(packages) and not audit.errors
        return {"schema": DECISION_SCHEMA, "input_sha256": digest(evidence), "policy_sha256": digest(policy),
                "catalog_source_sha256": PINS["app_test_catalog.json"][1],
                "reviewed_catalog_packages": len(APPS), "reviewed_core_cases": EXPECTED_COUNTS[1], "network_profiles": len(NETWORK),
                "fresh_resolver_proven": inventory_complete, "resolved_package_count": len(packages),
                "catalog_delta": {"added": added, "absent": absent},
                "production_ready": ready, "production_ready_app_count": sum(a["production_ready"] for a in results.values()),
                "cleanup_eligible": False, "cleanup_authorized": False, "actions_executed": [],
                "global_blockers": global_errors, "apps": results,
                "limitations": "Offline review of supplied reports. Does not authenticate their truth or execute QA. A current guard, original receipts and independent source/publisher review remain required. Never authorizes cleanup."}
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
        return {"schema": DECISION_SCHEMA, "production_ready": False, "production_ready_app_count": 0,
                "cleanup_eligible": False, "cleanup_authorized": False, "actions_executed": [],
                "global_blockers": audit.errors + [{"path": "evidence_or_policy", "reason": "invalid_structure:" + str(error)}],
                "apps": {p: {"status": UNKNOWN, "production_ready": False} for p in sorted(universe)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", nargs="?")
    parser.add_argument("--policy", default=str(HERE / "policy.template.json"))
    parser.add_argument("--template", action="store_true")
    parser.add_argument("--policy-template", action="store_true")
    args = parser.parse_args()
    try:
        if args.policy_template:
            result, code = make_policy(), 0
        else:
            policy = read_json(args.policy)
            if args.template:
                result, code = make_template(policy), 0
            else:
                if not args.evidence:
                    parser.error("supply evidence.json or --template / --policy-template")
                result = evaluate(read_json(args.evidence), policy)
                code = 0 if result["production_ready"] else 1
        print(json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False))
        return code
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
        print(json.dumps({"schema": DECISION_SCHEMA, "production_ready": False,
                          "cleanup_eligible": False, "cleanup_authorized": False,
                          "actions_executed": [], "error": str(error)}, ensure_ascii=False))
        return 2


if __name__ == "__main__":
    sys.exit(main())
