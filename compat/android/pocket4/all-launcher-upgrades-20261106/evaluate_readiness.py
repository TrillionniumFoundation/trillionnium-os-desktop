#!/usr/bin/env python3
"""Offline audit of supplied, content-addressed evidence; never an Android runner.

This program reads JSON only. It does NOT verify APK bytes itself: acceptance needs
the recorded full-APK verifier result AND a separately reviewed publisher trust
anchor in the policy. It cannot authenticate invented evidence. Keep the original
referenced reports until their failures/unknowns have been resolved and receipted.

Usage: evaluate_readiness.py evidence.json [--manifest regression_manifest.json]
       evaluate_readiness.py --template
Exit codes: 0 = ready; 1 = blocked; 2 = invalid input. No files are deleted.
The template is deliberately UNKNOWN, not an example of a successful device run.
"""

import argparse
import copy
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit


SCHEMA = "pocket4-all-launcher-evidence-v1"
POLICY_SCHEMA = "pocket4-all-launcher-regression-policy-v1"
ROSTER_SHA = "ee08889a49ac84fa19d6b3d4c159e6a600eb2772d8375eb065fa1585e68543d1"
HISTORICAL_PACKAGES = frozenset((
    "com.Hyatt.hyt", "com.enflick.android.TextNow", "com.lianjia.beike",
    "com.rytong.airchina", "com.rytong.ceair", "com.sankuai.meituan.takeoutnew",
    "com.szzc", "tv.danmaku.bili",
))
CHECKS = ("startup", "login_or_guest", "core", "network", "storage",
          "permissions", "integrity", "soak", "restart", "fault_recovery")
HELPERS = ("sidecar_sha256", "ui_automator_sha256", "chinese_input_sha256",
           "location_sha256")
LOCATION = frozenset(("android.permission.ACCESS_FINE_LOCATION",
                      "android.permission.ACCESS_COARSE_LOCATION"))
DEFAULT_POLICY = Path(__file__).with_name("regression_manifest.json")


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                    separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def known(value):
    return isinstance(value, str) and value.strip().lower() not in ("", "unknown", "none", "null", "pending", "n/a")


def sha(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def integer(value, minimum=0):
    return type(value) is int and value >= minimum


def timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo is not None else None
    except (AttributeError, TypeError, ValueError):
        return None


def unique_strings(value, nonempty=True):
    return (isinstance(value, list) and (bool(value) or not nonempty)
            and all(known(x) for x in value) and len(value) == len(set(value)))


def hashes(value):
    return unique_strings(value) and all(sha(x) for x in value)


def canonical_path(value):
    return (isinstance(value, str) and value.startswith("/") and value != "/"
            and not any(c in value for c in "\x00\n\r*?[]")
            and all(part not in ("", ".", "..") for part in value[1:].split("/")))


def paths_overlap(left, right):
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def launcher_component(value, package):
    return (isinstance(value, str) and value.startswith(package + "/")
            and re.fullmatch(r"\.?[A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*",
                             value[len(package) + 1:]) is not None)


class Audit:
    def __init__(self, evidence, policy):
        self.evidence = evidence
        self.policy = policy
        self.errors = []
        self.references = evidence.get("references", {}) if isinstance(evidence, dict) else {}
        if not isinstance(self.references, dict):
            self.references = {}

    def need(self, condition, path, reason):
        if not condition:
            self.errors.append({"path": path, "reason": reason})
        return bool(condition)

    def obj(self, value, path):
        if not isinstance(value, dict):
            self.need(False, path, "object_required; missing/null/unknown cannot pass")
            return {}
        return value

    def refs(self, ids, path, kinds, binding=None):
        if not self.need(unique_strings(ids), path, "nonempty_unique_evidence_references_required"):
            return
        observed = set()
        for ref_id in ids:
            ref = self.obj(self.references.get(ref_id), path + "." + ref_id)
            self.need(known(ref.get("uri")) and sha(ref.get("sha256"))
                      and timestamp(ref.get("captured_at")) is not None,
                      path + "." + ref_id, "reference_requires_uri_sha256_and_timezone_timestamp")
            if known(ref.get("kind")):
                observed.add(ref["kind"])
            if binding is not None:
                self.need(ref.get("binding") == binding, path + "." + ref_id,
                          "referenced_report_has_stale_runtime_app_or_helper_binding")
        for kind in kinds:
            self.need(kind in observed, path, "required_evidence_kind_missing:" + kind)

    def record(self, value, path, binding, kinds):
        value = self.obj(value, path)
        self.need(value.get("status") == "pass", path, "explicit_pass_required")
        self.need(value.get("scope") == "production", path, "historical_or_test_cell_is_not_production_evidence")
        self.need(value.get("binding") == binding, path, "runtime_app_or_helper_identity_mismatch")
        self.refs(value.get("evidence_refs"), path + ".evidence_refs", kinds, binding)
        return value

    def true(self, record, fields, path):
        for name in fields:
            self.need(record.get(name) is True, path + "." + name, "explicit_true_required")

    def false(self, record, fields, path):
        for name in fields:
            self.need(record.get(name) is False, path + "." + name, "explicit_false_required")

    def official_url(self, url, allowed_hosts, path):
        try:
            parsed = urlsplit(url)
            valid = parsed.scheme == "https" and parsed.hostname in allowed_hosts and not parsed.username
        except (TypeError, ValueError, AttributeError):
            valid = False
        self.need(valid, path, "reviewed_official_https_source_required")

    def runtime(self):
        r = self.obj(self.evidence.get("runtime"), "runtime")
        identity = self.obj(r.get("identity"), "runtime.identity")
        identity_fields = {"target", "runtime", "cell", "epoch_sha256", "baseline_sha256", "qualification_sha256", "config_sha256"}
        self.need(set(identity) == identity_fields and all(sha(identity.get(k)) for k in identity_fields if k.endswith("sha256"))
                  and all(known(identity.get(k)) for k in ("target", "runtime", "cell")), "runtime.identity", "complete_runtime_identity_required")
        self.need(identity == self.policy.get("required_runtime_identity"), "runtime.identity",
                  "current_qualified_runtime_pin_mismatch; old_epochs_are_not_reauthorized")
        helpers = self.obj(r.get("helpers"), "runtime.helpers")
        self.need(set(helpers) == set(HELPERS) and all(sha(helpers.get(k)) for k in HELPERS),
                  "runtime.helpers", "all_existing_helper_artifact_identities_required")
        self.need(r.get("qualified_helpers") == helpers, "runtime.qualified_helpers", "helper_identity_not_qualified")
        binding = {"runtime_identity_sha256": digest(identity), "helper_identity_sha256": digest(helpers)}
        q = self.record(r.get("qualification"), "runtime.qualification", binding, ["runtime_qualification", "helper_attestation"])
        self.true(q, ["identity_qualified", "framework_exit_cause_resolved"], "runtime.qualification")
        admission = self.record(r.get("admission"), "runtime.admission", binding, ["runtime_admission"])
        self.true(admission, ["ui_runtime_admitted", "install_runtime_admitted"], "runtime.admission")
        self.false(admission, ["adb_used", "read_only_organ_adapter_expanded", "security_constraint_bypassed"], "runtime.admission")
        self.need(admission.get("transport") == "existing_sidecar_container_ui_automator", "runtime.admission.transport",
                  "retain_existing_sidecar_and_container_UI_Automator")
        for phase in ("before", "after"):
            self.record(r.get("guard_" + phase), "runtime.guard_" + phase, binding, ["current_runtime_guard"])
        reboot = self.record(r.get("restart_requalification"), "runtime.restart_requalification", binding,
                             ["runtime_restart_trace", "runtime_qualification"])
        self.need(sha(reboot.get("previous_epoch_sha256"))
                  and reboot.get("previous_epoch_sha256") != identity.get("epoch_sha256"),
                  "runtime.restart_requalification", "actual_runtime_restart_and_new_qualified_epoch_required")
        self.true(reboot, ["old_epoch_retired", "new_epoch_requalified", "recovered_without_bypass"], "runtime.restart_requalification")
        self.need(integer(r.get("android_api"), 1), "runtime.android_api", "observed_android_API_required")
        return binding, r

    def inventory(self, binding):
        inv = self.record(self.evidence.get("launcher_inventory"), "launcher_inventory", binding, ["current_launcher_query"])
        self.need(inv.get("origin") == "current_runtime_query", "launcher_inventory.origin", "reference_targets_are_not_live_inventory")
        self.true(inv, ["complete", "all_query_processes_joined"], "launcher_inventory")
        self.need(type(inv.get("query_exit_code")) is int and inv["query_exit_code"] == 0,
                  "launcher_inventory.query_exit_code", "successful_complete_resolved_launcher_query_required")
        self.need(inv.get("action") == "android.intent.action.MAIN" and inv.get("category") == "android.intent.category.LAUNCHER",
                  "launcher_inventory", "full_MAIN_LAUNCHER_resolution_required")
        self.need(inv.get("android_user") == 0 and type(inv.get("android_user")) is int,
                  "launcher_inventory.android_user", "current_scope_is_Android_user_0")
        rows = inv.get("rows")
        if not self.need(isinstance(rows, list) and bool(rows), "launcher_inventory.rows", "actual_resolved_launcher_rows_required"):
            rows = []
        canonical, packages = [], set()
        for n, value in enumerate(rows):
            row = self.obj(value, "launcher_inventory.rows." + str(n))
            package, components = row.get("package"), row.get("components")
            valid = known(package) and unique_strings(components) and row.get("app_class") in ("system", "third_party")
            self.need(valid, "launcher_inventory.rows." + str(n), "package_components_and_app_class_required")
            if valid:
                self.need(package not in packages, "launcher_inventory.rows", "duplicate_package")
                self.need(all(launcher_component(c, package) for c in components), "launcher_inventory.rows", "resolved_component_package_or_activity_class_invalid")
                packages.add(package)
                canonical.append({"package": package, "components": sorted(components), "app_class": row["app_class"]})
        canonical.sort(key=lambda row: row["package"])
        self.need(inv.get("resolved_set_sha256") == digest(canonical), "launcher_inventory.resolved_set_sha256", "resolved_launcher_set_digest_mismatch")
        self.need(HISTORICAL_PACKAGES <= packages, "launcher_inventory.rows", "historical_eight_apps_must_remain_covered")
        return packages

    def framework(self, binding):
        f = self.record(self.evidence.get("framework"), "framework", binding,
                        ["framework_artifact_verification", "framework_lifecycle_test"])
        self.true(f, ["latest_official_for_target", "source_and_build_verified", "publisher_trust_verified",
                      "native_engine_mapping_verified", "lifecycle_passed"], "framework")
        self.need(known(f.get("version")) and known(f.get("source_revision")) and hashes(f.get("artifact_sha256s")),
                  "framework", "concrete_current_framework_version_source_and_artifacts_required")
        self.need(f.get("unresolved_failures") == [], "framework.unresolved_failures", "framework_failures_or_unknowns_unresolved")
        trust = self.obj(self.policy.get("framework_trust"), "policy.framework_trust")
        self.need(trust.get("status") == "verified_official", "policy.framework_trust", "framework_source_trust_unknown")
        self.refs(f.get("provenance_refs"), "framework.provenance_refs", ["official_framework_provenance"])
        allowed = trust.get("accepted_provenance_sha256s", [])
        self.need(hashes(allowed) and any(self.references.get(x, {}).get("kind") == "official_framework_provenance"
                                       and self.references.get(x, {}).get("sha256") in allowed
                                       for x in (f.get("provenance_refs") or []) if isinstance(x, str)),
                  "framework.provenance_refs", "framework_provenance_not_independently_pinned")
        return f.get("artifact_sha256s") if hashes(f.get("artifact_sha256s")) else []

    def artifact(self, app, rule, identity, binding, android_api, path):
        c = self.obj(app.get("official_candidate"), path + ".official_candidate")
        self.need(c.get("status") == "artifact_verified", path + ".official_candidate", "store_page_alone_is_not_a_verified_artifact")
        self.true(c, ["latest_stable_for_target", "complete_apk_set_obtained", "installed_apk_set_equal"], path + ".official_candidate")
        self.official_url(c.get("source_url"), rule.get("official_hosts", []), path + ".official_candidate.source_url")
        self.refs(c.get("release_refs"), path + ".official_candidate.release_refs", ["official_release"])
        self.refs(c.get("artifact_manifest_refs"), path + ".official_candidate.artifact_manifest_refs", ["complete_apk_manifest"], binding)
        self.need(c.get("version_name") == identity.get("version_name") and c.get("version_code") == identity.get("version_code"),
                  path + ".official_candidate", "installed_version_is_not_the_verified_latest_candidate")
        latest = rule.get("latest_candidate_pin", {})
        self.need(isinstance(latest, dict) and known(latest.get("version_name")) and c.get("version_name") == latest.get("version_name"),
                  path + ".official_candidate", "latest_official_candidate_is_unknown_or_changed; refresh_reviewed_policy_pin")
        trust = self.obj(rule.get("vendor_trust"), path + ".policy.vendor_trust")
        sets = trust.get("allowed_signer_sets")
        sets_valid = isinstance(sets, list) and bool(sets) and all(hashes(s) for s in sets)
        self.need(trust.get("status") == "verified_official" and sets_valid,
                  path + ".policy.vendor_trust", "independent_official_publisher_signer_anchor_required")
        provenance = self.obj(trust.get("provenance"), path + ".policy.vendor_trust.provenance")
        self.need(sha(provenance.get("sha256")) and provenance.get("kind") == "official_publisher_signer_provenance",
                  path + ".policy.vendor_trust.provenance", "publisher_anchor_needs_content_addressed_official_evidence")
        self.official_url(provenance.get("uri"), rule.get("official_hosts", []), path + ".policy.vendor_trust.provenance.uri")
        signers = identity.get("signer_sha256s")
        self.need(hashes(signers) and sets_valid and sorted(signers) in [sorted(s) for s in sets],
                  path + ".official_candidate", "valid_crypto_signature_is_insufficient_if_publisher_signer_is_wrong")
        apks = c.get("apks")
        if not self.need(isinstance(apks, list) and bool(apks), path + ".official_candidate.apks", "full_base_and_required_splits_required"):
            apks = []
        observed_hashes, splits = [], []
        for n, value in enumerate(apks):
            p = path + ".official_candidate.apks." + str(n)
            apk = self.obj(value, p)
            self.need(sha(apk.get("sha256")) and integer(apk.get("bytes"), 1) and known(apk.get("split_name")), p, "APK_bytes_hash_size_and_split_name_required; use_base_for_base_APK")
            self.need(apk.get("package") == identity.get("package") and apk.get("version_code") == identity.get("version_code"), p, "APK_manifest_identity_mismatch")
            observed_hashes.append(apk.get("sha256"))
            splits.append(apk.get("split_name"))
            sig = self.obj(apk.get("signature"), p + ".signature")
            self.true(sig, ["verified", "full_apk_checked", "held_file_unchanged", "verifier_joined"], p + ".signature")
            self.need(type(sig.get("tool_exit_code")) is int and sig["tool_exit_code"] == 0
                      and sig.get("timed_out") is False and sig.get("tool") == "apksigner", p + ".signature", "successful_complete_apksigner_verification_required")
            self.need(hashes(sig.get("signer_sha256s")) and sig.get("signer_sha256s") == signers, p + ".signature", "base_split_or_current_signer_mismatch")
            schemes = sig.get("verified_schemes", {})
            self.need(isinstance(schemes, dict) and any(schemes.get(s) is True for s in ("v1", "v2", "v3", "v3.1", "v4")), p + ".signature", "no_verified_signature_scheme")
            self.refs(sig.get("evidence_refs"), p + ".signature.evidence_refs", ["apk_signature_verification"], binding)
            if apk.get("split_name") == "base":
                self.need(integer(apk.get("min_sdk"), 1) and integer(android_api, 1) and apk["min_sdk"] <= android_api,
                          p + ".min_sdk", "candidate_minimum_Android_not_supported_or_unknown")
        self.need(unique_strings(observed_hashes) and sorted(observed_hashes) == sorted(identity.get("apk_sha256s") or []),
                  path + ".official_candidate.apks", "complete_installed_artifact_set_mismatch")
        self.need(unique_strings(splits) and splits.count("base") == 1, path + ".official_candidate.apks", "exactly_one_base_and_unique_splits_required")

    def app(self, package, app, binding, android_api):
        path = "apps." + package
        app = self.obj(app, path)
        rule = self.policy.get("apps", {}).get(package, {})
        self.need(rule.get("core_definition_status") == "defined" and bool(rule.get("core_flows")),
                  path + ".policy", "app_specific_core_flow_definition_unknown; generic_schema_is_not_coverage")
        identity = self.obj(app.get("current_identity"), path + ".current_identity")
        self.need(identity.get("package") == package and integer(identity.get("uid"), 1)
                  and identity.get("android_user") == 0 and type(identity.get("android_user")) is int
                  and integer(identity.get("version_code"), 1) and known(identity.get("version_name"))
                  and hashes(identity.get("apk_sha256s")) and hashes(identity.get("signer_sha256s")),
                  path + ".current_identity", "current_installed_package_user_UID_version_APKs_signers_required")
        self.need(app.get("identity_before") == identity and app.get("identity_after") == identity,
                  path, "installation_UID_or_version_or_APK_identity_changed; rerun_all_checks")
        bound = dict(binding, app_identity_sha256=digest(identity))
        identity_record = self.record(app.get("identity_verification"), path + ".identity_verification", bound,
                                      ["installed_package_identity", "native_runtime_mapping"])
        self.true(identity_record, ["native_runtime_mapping_verified"], path + ".identity_verification")
        self.artifact(app, rule, identity, bound, android_api, path)
        checks = self.obj(app.get("checks"), path + ".checks")
        self.need(set(checks) == set(CHECKS), path + ".checks", "all_required_checks_and_no_unrecognized_check_names_required")
        kinds = {
            "startup": ["runtime_log", "ui_hierarchy"], "login_or_guest": ["runtime_log", "ui_hierarchy", "session_authorization"],
            "core": ["runtime_log", "ui_hierarchy"], "network": ["app_network_trace"], "storage": ["app_storage_readback"],
            "permissions": ["permission_snapshot_before", "permission_snapshot_after"], "integrity": ["integrity_and_security_trace"],
            "soak": ["continuous_soak_trace", "resource_budget_evaluation"], "restart": ["app_restart_trace"],
            "fault_recovery": ["app_fault_recovery_trace"],
        }
        records = {name: self.record(checks.get(name), path + ".checks." + name, bound, kinds[name]) for name in CHECKS}
        self.true(records["startup"], ["responsive_first_screen", "no_crash_or_anr"], path + ".checks.startup")
        auth = records["login_or_guest"]
        self.need(auth.get("mode") in rule.get("allowed_session_modes", []), path + ".checks.login_or_guest", "usable_authorized_login_or_guest_session_required")
        self.true(auth, ["session_usable", "session_authorized"], path + ".checks.login_or_guest")
        if package == "tv.danmaku.bili":
            self.false(auth, ["accept_executed", "historical_test_consent_reused"], path + ".checks.login_or_guest")
            self.need(auth.get("authorization_cell") == self.policy["required_runtime_identity"]["cell"]
                      and auth.get("authorization_cell") != "p4-bili-m30-cell-20261010",
                      path + ".checks.login_or_guest", "historical_Bilibili_cell_never_proves_production_authorization")
        flows = self.obj(records["core"].get("flows"), path + ".checks.core.flows")
        self.need(set(flows) == set(rule.get("core_flows", {})), path + ".checks.core.flows", "all_app_specific_public_core_flows_required")
        for name in rule.get("core_flows", {}):
            flow = self.record(flows.get(name), path + ".checks.core.flows." + name, bound, ["runtime_log", "ui_hierarchy"])
            self.true(flow, ["expected_outcome_observed"], path + ".checks.core.flows." + name)
            self.need(known(flow.get("actual_outcome")), path + ".checks.core.flows." + name, "actual_business_outcome_required")
            if rule.get("requires_authorized_test_peer") is True:
                self.refs(flow.get("test_peer_authorization_refs"), path + ".checks.core.flows." + name + ".test_peer_authorization_refs",
                          ["explicit_test_peer_authorization"], bound)
        self.true(records["network"], ["app_level_dns_tls_response_verified", "error_path_verified"], path + ".checks.network")
        self.false(records["network"], ["tls_or_integrity_bypass_used"], path + ".checks.network")
        self.true(records["storage"], ["app_read_write_readback_verified", "data_survives_restart"], path + ".checks.storage")
        permissions = records["permissions"]
        self.true(permissions, ["required_permission_path_verified", "denied_permission_path_verified", "no_unauthorized_grants"], path + ".checks.permissions")
        before, after, grants = (permissions.get(x) for x in ("grants_before", "grants_after", "active_grants"))
        for field, value in (("grants_before", before), ("grants_after", after), ("active_grants", grants)):
            self.need(unique_strings(value, nonempty=False), path + ".checks.permissions." + field, "explicit_observed_permission_list_required")
        if all(unique_strings(x, nonempty=False) for x in (before, after, grants)):
            if package == "com.sankuai.meituan.takeoutnew":
                self.need(not (LOCATION & (set(grants) | (set(after) - set(before)))), path + ".checks.permissions", "Meituan_FINE_or_COARSE_location_must_not_be_actively_granted")
            if grants or set(after) != set(before):
                self.refs(permissions.get("change_authorization_refs"), path + ".checks.permissions.change_authorization_refs", ["permission_change_authorization"], bound)
        self.true(records["integrity"], ["commercial_integrity_clear", "effective_security_constraints_preserved"], path + ".checks.integrity")
        self.false(records["integrity"], ["integrity_or_other_security_bypass_used"], path + ".checks.integrity")
        soak = records["soak"]
        threshold = self.policy["proposed_acceptance_thresholds"]["continuous_soak_seconds"]
        start, finish = timestamp(soak.get("started_at")), timestamp(soak.get("finished_at"))
        self.need(start is not None and finish is not None and (finish - start).total_seconds() >= threshold,
                  path + ".checks.soak", "continuous_soak_wall_time_below_proposed_threshold_or_unknown")
        self.need(integer(soak.get("active_monitor_seconds"), threshold) and integer(soak.get("sample_count"), 3),
                  path + ".checks.soak", "continuous_runtime_and_resource_observation_required")
        self.true(soak, ["continuous_probe_coverage", "resource_budget_met", "core_still_usable"], path + ".checks.soak")
        self.need(type(soak.get("crashes")) is int and soak["crashes"] == 0 and type(soak.get("anrs")) is int and soak["anrs"] == 0,
                  path + ".checks.soak", "soak_crash_or_ANR_or_unknown")
        for name, field, minimum, evidence_kind in (
                ("restart", "cycles", self.policy["proposed_acceptance_thresholds"]["app_restart_cycles"], "app_restart_trace"),
                ("fault_recovery", "network_cycles", self.policy["proposed_acceptance_thresholds"]["network_recovery_cycles"], "app_fault_recovery_trace")):
            cycles = records[name].get(field)
            if not self.need(isinstance(cycles, list) and len(cycles) >= minimum, path + ".checks." + name, "insufficient_observed_recovery_cycles"):
                cycles = []
            ids = []
            for n, cycle in enumerate(cycles):
                p = path + ".checks." + name + "." + str(n)
                cycle = self.record(cycle, p, bound, [evidence_kind])
                ids.append(cycle.get("cycle_id"))
                self.true(cycle, ["core_resumed", "data_preserved"], p)
                if name == "restart":
                    self.need(sha(cycle.get("before_process_identity_sha256")) and sha(cycle.get("after_process_identity_sha256"))
                              and cycle["before_process_identity_sha256"] != cycle["after_process_identity_sha256"], p, "actual_process_restart_required")
                else:
                    self.true(cycle, ["offline_observed", "online_observed"], p)
            self.need(unique_strings(ids), path + ".checks." + name, "distinct_recovery_cycle_ids_required")
        self.true(records["fault_recovery"], ["process_death_recovered", "no_security_bypass"], path + ".checks.fault_recovery")
        return identity.get("apk_sha256s") if hashes(identity.get("apk_sha256s")) else []

    def cleanup(self, binding, current_artifacts):
        keep = self.record(self.evidence.get("retention"), "retention", binding,
                           ["final_source", "final_configuration", "reproduction_manifest", "resolution_ledger", "final_lightweight_receipt", "exact_cleanup_plan", "current_artifact_path_inventory"])
        self.true(keep, ["final_source_exists", "final_configuration_exists", "reproduction_manifest_exists",
                         "original_failure_evidence_preserved_until_settlement", "unknown_and_failure_items_settled"], "retention")
        self.need(keep.get("unresolved_items") == [], "retention.unresolved_items", "unresolved_failure_or_unknown_forbids_cleanup")
        current_paths = keep.get("current_artifact_paths")
        current_paths_valid = (isinstance(current_paths, list) and bool(current_paths)
                               and all(isinstance(x, dict) and canonical_path(x.get("path")) and sha(x.get("sha256"))
                                       for x in current_paths))
        self.need(current_paths_valid and {x["sha256"] for x in current_paths} == current_artifacts,
                  "retention.current_artifact_paths", "complete_current_framework_and_APK_path_inventory_required")
        deletions = keep.get("obsolete_artifacts")
        if not self.need(isinstance(deletions, list), "retention.obsolete_artifacts", "explicit_exact_obsolete_artifact_list_required"):
            return
        allowed_kinds = {"obsolete_framework", "obsolete_app", "obsolete_build", "experiment", "intermediate"}
        protected_uris = {self.references[x].get("uri") for x in (keep.get("evidence_refs") or [])
                          if x in self.references and self.references[x].get("kind") in ("final_source", "final_configuration", "reproduction_manifest", "final_lightweight_receipt")}
        protected_paths = {p for p in protected_uris if canonical_path(p)}
        if current_paths_valid:
            protected_paths.update(x["path"] for x in current_paths)
        for n, item in enumerate(deletions):
            p = "retention.obsolete_artifacts." + str(n)
            item = self.obj(item, p)
            self.need(canonical_path(item.get("path")) and item.get("artifact_type") == "regular_file"
                      and sha(item.get("sha256")) and item.get("kind") in allowed_kinds,
                      p, "exact_canonical_regular_file_path_hash_and_obsolete_kind_required; enumerate_files_not_directory_trees")
            self.need(item.get("sha256") not in current_artifacts and item.get("path") not in protected_uris
                      and (not canonical_path(item.get("path")) or not any(paths_overlap(item["path"], old) for old in protected_paths)),
                      p, "cleanup_must_not_target_current_or_retained_final_artifacts")


def _evaluate(evidence, policy):
    audit = Audit(evidence, policy)
    evidence = audit.obj(evidence, "evidence")
    audit.need(policy.get("schema") == POLICY_SCHEMA, "policy.schema", "unsupported_policy_schema")
    audit.need(policy.get("scope") == "all_current_launcher_apps_and_framework", "policy.scope", "full_current_launcher_and_framework_scope_required")
    audit.need(set(policy.get("historical_eight_packages", [])) == HISTORICAL_PACKAGES,
               "policy.historical_eight_packages", "historical_roster_changed")
    audit.need(evidence.get("schema") == SCHEMA, "schema", "unsupported_evidence_schema")
    audit.need(evidence.get("historical_roster_sha256") == ROSTER_SHA, "historical_roster_sha256", "historical_roster_source_pin_mismatch")
    audit.need(timestamp(evidence.get("collected_at")) is not None, "collected_at", "timezone_timestamp_required")
    binding, runtime = audit.runtime()
    before_inventory = len(audit.errors)
    packages = audit.inventory(binding)
    inventory_complete = before_inventory == 0 and len(audit.errors) == before_inventory
    current_artifacts = set(audit.framework(binding))
    apps = audit.obj(evidence.get("apps"), "apps")
    audit.need(set(apps) == packages, "apps", "app_evidence_must_equal_the_actual_resolved_launcher_package_set")
    global_ready = not audit.errors
    results = {}
    for package in sorted(packages | set(apps) | HISTORICAL_PACKAGES):
        start = len(audit.errors)
        current_artifacts.update(audit.app(package, apps.get(package), binding, runtime.get("android_api")))
        local_errors = audit.errors[start:]
        results[package] = {"status": "pass" if global_ready and not local_errors else "blocked",
                            "blockers": local_errors,
                            "global_gates_passed": global_ready}
    production_ready = not audit.errors and bool(packages)
    readiness_errors = list(audit.errors)
    audit.cleanup(binding, current_artifacts)
    cleanup_errors = audit.errors[len(readiness_errors):]
    return {"schema": "pocket4-all-launcher-readiness-decision-v1", "scope": "all_current_launcher_apps_and_framework",
            "input_sha256": digest(evidence), "policy_sha256": digest(policy),
            "all_launcher_inventory_complete": inventory_complete,
            "resolved_launcher_package_count": len(packages), "historical_eight_is_only_a_subset": True,
            "production_ready": production_ready, "cleanup_eligible": production_ready and not cleanup_errors,
            "actions_executed": [], "blockers": readiness_errors, "cleanup_blockers": cleanup_errors,
            "apps": results,
            "limitations": "Offline adjudication of supplied reports, not a live guard, APK verifier, installer, UI runner, or deletion authorization. Unknown/untrusted/missing evidence is blocking."}


def evaluate(evidence, policy):
    try:
        return _evaluate(evidence, policy)
    except (ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
        return {"schema": "pocket4-all-launcher-readiness-decision-v1", "production_ready": False,
                "cleanup_eligible": False, "all_launcher_inventory_complete": False, "actions_executed": [],
                "blockers": [{"path": "evidence_or_policy", "reason": "invalid_structure:" + str(error)}],
                "cleanup_blockers": [{"path": "cleanup", "reason": "invalid_evidence_never_allows_cleanup"}], "apps": {}}


def unknown_record(**extra):
    return dict(status="unknown", scope="unknown", binding=None, evidence_refs=[], **extra)


def make_template(policy):
    """A schema-shaped UNKNOWN input. It is not a runtime observation."""
    r = {"identity": copy.deepcopy(policy["required_runtime_identity"]), "helpers": dict.fromkeys(HELPERS),
         "qualified_helpers": None, "android_api": None,
         "qualification": unknown_record(identity_qualified=None, framework_exit_cause_resolved=None),
         "admission": unknown_record(ui_runtime_admitted=None, install_runtime_admitted=None, adb_used=None,
                                     read_only_organ_adapter_expanded=None, security_constraint_bypassed=None, transport=None),
         "guard_before": unknown_record(), "guard_after": unknown_record(),
         "restart_requalification": unknown_record(previous_epoch_sha256=None, old_epoch_retired=None,
                                                   new_epoch_requalified=None, recovered_without_bypass=None)}
    apps = {}
    for package in policy["historical_eight_packages"]:
        identity = {"package": package, "android_user": 0, "uid": None, "version_name": None, "version_code": None,
                    "apk_sha256s": None, "signer_sha256s": None}
        checks = {name: unknown_record() for name in CHECKS}
        checks["startup"].update(responsive_first_screen=None, no_crash_or_anr=None)
        checks["login_or_guest"].update(mode=None, session_usable=None, session_authorized=None)
        if package == "tv.danmaku.bili":
            checks["login_or_guest"].update(accept_executed=None, historical_test_consent_reused=None, authorization_cell=None)
        checks["core"]["flows"] = {name: unknown_record(expected_outcome_observed=None, actual_outcome=None)
                                    for name in policy["apps"][package]["core_flows"]}
        if policy["apps"][package].get("requires_authorized_test_peer") is True:
            for flow in checks["core"]["flows"].values():
                flow["test_peer_authorization_refs"] = []
        checks["network"].update(app_level_dns_tls_response_verified=None, error_path_verified=None, tls_or_integrity_bypass_used=None)
        checks["storage"].update(app_read_write_readback_verified=None, data_survives_restart=None)
        checks["permissions"].update(required_permission_path_verified=None, denied_permission_path_verified=None,
                                      no_unauthorized_grants=None, grants_before=None, grants_after=None, active_grants=None,
                                      change_authorization_refs=[])
        checks["integrity"].update(commercial_integrity_clear=None, effective_security_constraints_preserved=None,
                                  integrity_or_other_security_bypass_used=None)
        checks["soak"].update(started_at=None, finished_at=None, active_monitor_seconds=None, sample_count=None,
                             continuous_probe_coverage=None, resource_budget_met=None, core_still_usable=None, crashes=None, anrs=None)
        checks["restart"]["cycles"] = []
        checks["fault_recovery"].update(network_cycles=[], process_death_recovered=None, no_security_bypass=None)
        apps[package] = {"current_identity": identity, "identity_before": None, "identity_after": None,
                         "identity_verification": unknown_record(native_runtime_mapping_verified=None),
                         "official_candidate": {"status": "unknown", "latest_stable_for_target": None,
                             "complete_apk_set_obtained": None, "installed_apk_set_equal": None, "source_url": None,
                             "version_name": None, "version_code": None, "release_refs": [], "artifact_manifest_refs": [], "apks": []},
                         "checks": checks}
    return {"schema": SCHEMA, "historical_roster_sha256": ROSTER_SHA, "collected_at": None,
            "template_only": True, "runtime": r, "references": {},
            "launcher_inventory": unknown_record(origin=None, complete=None, all_query_processes_joined=None,
                query_exit_code=None, android_user=0, action="android.intent.action.MAIN",
                category="android.intent.category.LAUNCHER", rows=[], resolved_set_sha256=None),
            "framework": unknown_record(version=None, source_revision=None, artifact_sha256s=None,
                latest_official_for_target=None, source_and_build_verified=None, publisher_trust_verified=None,
                native_engine_mapping_verified=None, lifecycle_passed=None, unresolved_failures=None, provenance_refs=[]),
            "apps": apps, "retention": unknown_record(final_source_exists=None, final_configuration_exists=None,
                reproduction_manifest_exists=None, original_failure_evidence_preserved_until_settlement=None,
                unknown_and_failure_items_settled=None, unresolved_items=None, current_artifact_paths=None, obsolete_artifacts=None)}


def strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_JSON_key:" + key)
        result[key] = value
    return result


def load_json(path):
    def reject_constant(value):
        raise ValueError("nonfinite_JSON_number:" + value)
    return json.loads(Path(path).read_text(encoding="utf-8"), object_pairs_hook=strict_object,
                      parse_constant=reject_constant)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", nargs="?")
    parser.add_argument("--manifest", default=str(DEFAULT_POLICY))
    parser.add_argument("--template", action="store_true", help="print an UNKNOWN schema-shaped input; collect no evidence")
    args = parser.parse_args()
    try:
        policy = load_json(args.manifest)
        if args.template:
            print(json.dumps(make_template(policy), ensure_ascii=False, indent=2))
            return 0
        if not args.evidence:
            parser.error("provide one evidence JSON file, or --template")
        result = evaluate(load_json(args.evidence), policy)
    except (OSError, ValueError, TypeError, KeyError, AttributeError, OverflowError) as error:
        print(json.dumps({"schema": "pocket4-all-launcher-readiness-decision-v1", "production_ready": False,
                          "cleanup_eligible": False, "all_launcher_inventory_complete": False,
                          "actions_executed": [], "error": str(error)}, ensure_ascii=False, indent=2))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["production_ready"] else 1


if __name__ == "__main__":
    sys.exit(main())
