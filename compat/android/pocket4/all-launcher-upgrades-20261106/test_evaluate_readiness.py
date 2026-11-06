"""Counterexamples using in-memory synthetic declarations, never device results.

The accepting control below is intentionally fabricated unit-test input. It is
never written as evidence or a readiness report, and proves no Android behavior.
"""

import copy
import unittest

from evaluate_readiness import (CHECKS, DEFAULT_POLICY, HELPERS, HISTORICAL_PACKAGES,
                                ROSTER_SHA, SCHEMA, digest, evaluate, load_json,
                                make_template)


def synthetic_fixture():
    policy = copy.deepcopy(load_json(DEFAULT_POLICY))
    refs = {}
    when = "2026-11-06T12:00:00+00:00"

    def ref(kind, binding=None, uri=None):
        key = "synthetic-ref-" + str(len(refs))
        refs[key] = {"kind": kind, "uri": uri or "unit-test-only://" + key,
                     "sha256": digest(key), "captured_at": when}
        if binding is not None:
            refs[key]["binding"] = copy.deepcopy(binding)
        return key

    def record(binding, kinds, **values):
        return dict(status="pass", scope="production", binding=copy.deepcopy(binding),
                    evidence_refs=[ref(k, binding) for k in kinds], **values)

    runtime = {"identity": copy.deepcopy(policy["required_runtime_identity"]),
               "helpers": {name: digest("synthetic-" + name) for name in HELPERS}, "android_api": 37}
    runtime["qualified_helpers"] = copy.deepcopy(runtime["helpers"])
    binding = {"runtime_identity_sha256": digest(runtime["identity"]),
               "helper_identity_sha256": digest(runtime["helpers"])}
    runtime["qualification"] = record(binding, ["runtime_qualification", "helper_attestation"],
                                       identity_qualified=True, framework_exit_cause_resolved=True)
    runtime["admission"] = record(binding, ["runtime_admission"], ui_runtime_admitted=True,
                                   install_runtime_admitted=True, adb_used=False,
                                   read_only_organ_adapter_expanded=False, security_constraint_bypassed=False,
                                   transport="existing_sidecar_container_ui_automator")
    runtime["guard_before"] = record(binding, ["current_runtime_guard"])
    runtime["guard_after"] = record(binding, ["current_runtime_guard"])
    runtime["restart_requalification"] = record(binding, ["runtime_restart_trace", "runtime_qualification"],
                                                 previous_epoch_sha256=digest("synthetic-prior-epoch"),
                                                 old_epoch_retired=True, new_epoch_requalified=True, recovered_without_bypass=True)
    rows = [{"package": p, "components": [p + "/.SyntheticMain"], "app_class": "third_party"}
            for p in sorted(HISTORICAL_PACKAGES)]
    inventory = record(binding, ["current_launcher_query"], origin="current_runtime_query", complete=True,
                       all_query_processes_joined=True, query_exit_code=0, android_user=0,
                       action="android.intent.action.MAIN", category="android.intent.category.LAUNCHER",
                       rows=rows, resolved_set_sha256=digest(rows))
    provenance = ref("official_framework_provenance")
    policy["framework_trust"] = {"status": "verified_official", "accepted_provenance_sha256s": [refs[provenance]["sha256"]]}
    framework = record(binding, ["framework_artifact_verification", "framework_lifecycle_test"],
                       version="SYNTHETIC-NOT-A-REAL-BUILD", source_revision=digest("synthetic-source"),
                       artifact_sha256s=[digest("synthetic-framework")], latest_official_for_target=True,
                       source_and_build_verified=True, publisher_trust_verified=True,
                       native_engine_mapping_verified=True, lifecycle_passed=True,
                       unresolved_failures=[], provenance_refs=[provenance])
    apps = {}
    for ordinal, package in enumerate(sorted(HISTORICAL_PACKAGES)):
        rule = policy["apps"][package]
        version = rule["latest_candidate_pin"]["version_name"] or "synthetic-version-1"
        rule["latest_candidate_pin"]["version_name"] = version
        trusted_cert = digest("synthetic-vendor-" + package)
        official_url = "https://" + rule["official_hosts"][0] + "/synthetic-unit-test-only"
        rule["vendor_trust"] = {"status": "verified_official", "allowed_signer_sets": [[trusted_cert]],
                                 "provenance": {"kind": "official_publisher_signer_provenance",
                                                "sha256": digest("synthetic-provenance-" + package), "uri": official_url}}
        apk_hash = digest("synthetic-apk-" + package)
        identity = {"package": package, "android_user": 0, "uid": 12000 + ordinal,
                    "version_name": version, "version_code": 100 + ordinal,
                    "apk_sha256s": [apk_hash], "signer_sha256s": [trusted_cert]}
        bound = dict(binding, app_identity_sha256=digest(identity))
        signature = {"tool": "apksigner", "verified": True, "full_apk_checked": True,
                     "held_file_unchanged": True, "verifier_joined": True, "tool_exit_code": 0,
                     "timed_out": False, "signer_sha256s": [trusted_cert], "verified_schemes": {"v3": True},
                     "evidence_refs": [ref("apk_signature_verification", bound)]}
        candidate = {"status": "artifact_verified", "latest_stable_for_target": True,
                     "complete_apk_set_obtained": True, "installed_apk_set_equal": True,
                     "source_url": official_url, "version_name": version, "version_code": identity["version_code"],
                     "release_refs": [ref("official_release", uri=official_url)],
                     "artifact_manifest_refs": [ref("complete_apk_manifest", bound)],
                     "apks": [{"package": package, "version_code": identity["version_code"], "min_sdk": 29,
                               "split_name": "base", "sha256": apk_hash, "bytes": 123456, "signature": signature}]}
        checks = {
            "startup": record(bound, ["runtime_log", "ui_hierarchy"], responsive_first_screen=True, no_crash_or_anr=True),
            "login_or_guest": record(bound, ["runtime_log", "ui_hierarchy", "session_authorization"],
                                     mode="login", session_usable=True, session_authorized=True),
            "core": record(bound, ["runtime_log", "ui_hierarchy"], flows={}),
            "network": record(bound, ["app_network_trace"], app_level_dns_tls_response_verified=True,
                              error_path_verified=True, tls_or_integrity_bypass_used=False),
            "storage": record(bound, ["app_storage_readback"], app_read_write_readback_verified=True, data_survives_restart=True),
            "permissions": record(bound, ["permission_snapshot_before", "permission_snapshot_after"],
                                  required_permission_path_verified=True, denied_permission_path_verified=True,
                                  no_unauthorized_grants=True, grants_before=[], grants_after=[], active_grants=[]),
            "integrity": record(bound, ["integrity_and_security_trace"], commercial_integrity_clear=True,
                                effective_security_constraints_preserved=True, integrity_or_other_security_bypass_used=False),
            "soak": record(bound, ["continuous_soak_trace", "resource_budget_evaluation"],
                           started_at="2026-11-06T10:00:00+00:00", finished_at="2026-11-06T11:00:00+00:00",
                           active_monitor_seconds=3600, sample_count=61, continuous_probe_coverage=True,
                           resource_budget_met=True, core_still_usable=True, crashes=0, anrs=0),
            "restart": record(bound, ["app_restart_trace"], cycles=[]),
            "fault_recovery": record(bound, ["app_fault_recovery_trace"], network_cycles=[], process_death_recovered=True, no_security_bypass=True),
        }
        if package == "tv.danmaku.bili":
            checks["login_or_guest"].update(accept_executed=False, historical_test_consent_reused=False, authorization_cell="Main")
        for flow in rule["core_flows"]:
            checks["core"]["flows"][flow] = record(bound, ["runtime_log", "ui_hierarchy"],
                                                   expected_outcome_observed=True, actual_outcome="Synthetic test assertion; no operation occurred")
            if rule.get("requires_authorized_test_peer"):
                checks["core"]["flows"][flow]["test_peer_authorization_refs"] = [ref("explicit_test_peer_authorization", bound)]
        for n in range(3):
            checks["restart"]["cycles"].append(record(bound, ["app_restart_trace"], cycle_id="restart-" + str(n),
                core_resumed=True, data_preserved=True, before_process_identity_sha256=digest("before-" + str(n)),
                after_process_identity_sha256=digest("after-" + str(n))))
            checks["fault_recovery"]["network_cycles"].append(record(bound, ["app_fault_recovery_trace"],
                cycle_id="network-" + str(n), core_resumed=True, data_preserved=True, offline_observed=True, online_observed=True))
        apps[package] = {"current_identity": identity, "identity_before": copy.deepcopy(identity),
                         "identity_after": copy.deepcopy(identity), "official_candidate": candidate, "checks": checks,
                         "identity_verification": record(bound, ["installed_package_identity", "native_runtime_mapping"],
                                                         native_runtime_mapping_verified=True)}
    retention = record(binding, ["final_source", "final_configuration", "reproduction_manifest", "resolution_ledger",
                                  "final_lightweight_receipt", "exact_cleanup_plan", "current_artifact_path_inventory"],
                       final_source_exists=True, final_configuration_exists=True, reproduction_manifest_exists=True,
                       original_failure_evidence_preserved_until_settlement=True, unknown_and_failure_items_settled=True,
                       unresolved_items=[], obsolete_artifacts=[],
                       current_artifact_paths=[{"path": "/synthetic/current/" + h, "sha256": h}
                           for h in framework["artifact_sha256s"] + [a["current_identity"]["apk_sha256s"][0] for a in apps.values()]])
    return {"schema": SCHEMA, "historical_roster_sha256": ROSTER_SHA, "collected_at": when,
            "runtime": runtime, "references": refs, "launcher_inventory": inventory, "framework": framework,
            "apps": apps, "retention": retention}, policy


class ReadinessCounterexamples(unittest.TestCase):
    def setUp(self):
        self.evidence, self.policy = synthetic_fixture()

    def blocked(self, evidence, policy=None, reason=None):
        result = evaluate(evidence, policy or self.policy)
        self.assertIs(result["production_ready"], False)
        self.assertIs(result["cleanup_eligible"], False)
        if reason:
            self.assertTrue(any(reason in b["reason"] for b in result["blockers"]), result["blockers"][:5])
        return result

    def test_accepting_control_is_only_in_memory(self):
        result = evaluate(self.evidence, self.policy)
        self.assertIs(result["production_ready"], True, result["blockers"][:5])
        self.assertIs(result["cleanup_eligible"], True, result["cleanup_blockers"])
        self.assertEqual(result["actions_executed"], [])

    def test_unknown_missing_and_null_cannot_pass(self):
        actual_policy = load_json(DEFAULT_POLICY)
        result = self.blocked(make_template(actual_policy), actual_policy)
        self.assertIs(result["all_launcher_inventory_complete"], False)
        for unknown in (None, "unknown", {}):
            with self.subTest(unknown=unknown):
                evidence = copy.deepcopy(self.evidence)
                evidence["apps"]["com.Hyatt.hyt"]["checks"]["core"] = unknown
                self.blocked(evidence)
        self.blocked(None)

    def test_stale_epoch_install_UID_and_helper_mismatch(self):
        evidence = copy.deepcopy(self.evidence)
        evidence["runtime"]["identity"]["epoch_sha256"] = digest("old-epoch")
        result = self.blocked(evidence, reason="old_epochs_are_not_reauthorized")
        self.assertIs(result["all_launcher_inventory_complete"], False)
        evidence = copy.deepcopy(self.evidence)
        evidence["apps"]["com.Hyatt.hyt"]["identity_after"]["uid"] += 1
        self.blocked(evidence, reason="installation_UID")
        evidence = copy.deepcopy(self.evidence)
        evidence["runtime"]["qualified_helpers"]["ui_automator_sha256"] = digest("wrong-helper")
        self.blocked(evidence, reason="helper_identity_not_qualified")

    def test_valid_crypto_but_wrong_publisher_is_blocked(self):
        package = "com.rytong.ceair"
        app = self.evidence["apps"][package]
        old_hash = digest(app["current_identity"])
        wrong_cert = digest("a-valid-signature-from-the-wrong-publisher")
        for field in ("current_identity", "identity_before", "identity_after"):
            app[field]["signer_sha256s"] = [wrong_cert]
        app["official_candidate"]["apks"][0]["signature"]["signer_sha256s"] = [wrong_cert]
        new_hash = digest(app["current_identity"])

        def rebind(value):
            if isinstance(value, dict):
                if value.get("app_identity_sha256") == old_hash:
                    value["app_identity_sha256"] = new_hash
                for v in value.values():
                    rebind(v)
            elif isinstance(value, list):
                for v in value:
                    rebind(v)

        rebind(app)
        rebind(self.evidence["references"])
        self.assertIs(app["official_candidate"]["apks"][0]["signature"]["verified"], True)
        self.blocked(self.evidence, reason="publisher_signer_is_wrong")

    def test_meituan_location_grant_is_blocked_even_with_a_generic_authorization(self):
        p = self.evidence["apps"]["com.sankuai.meituan.takeoutnew"]["checks"]["permissions"]
        p["active_grants"] = ["android.permission.ACCESS_FINE_LOCATION"]
        p["grants_after"] = list(p["active_grants"])
        self.blocked(self.evidence, reason="Meituan_FINE_or_COARSE")

    def test_actual_launcher_set_and_historical_subset_are_both_required(self):
        evidence = copy.deepcopy(self.evidence)
        inv = evidence["launcher_inventory"]
        inv["rows"].append({"package": "com.example.new", "components": ["com.example.new/.Main"], "app_class": "system"})
        inv["rows"].sort(key=lambda row: row["package"])
        inv["resolved_set_sha256"] = digest(inv["rows"])
        self.blocked(evidence, reason="actual_resolved_launcher_package_set")
        evidence = copy.deepcopy(self.evidence)
        evidence["apps"]["com.example.extra"] = {}
        self.blocked(evidence, reason="actual_resolved_launcher_package_set")
        evidence = copy.deepcopy(self.evidence)
        evidence["launcher_inventory"]["origin"] = "historical_targets.json"
        result = self.blocked(evidence, reason="reference_targets_are_not_live_inventory")
        self.assertIs(result["all_launcher_inventory_complete"], False)
        evidence = copy.deepcopy(self.evidence)
        inv = evidence["launcher_inventory"]
        inv["rows"] = [row for row in inv["rows"] if row["package"] != "tv.danmaku.bili"]
        inv["resolved_set_sha256"] = digest(inv["rows"])
        del evidence["apps"]["tv.danmaku.bili"]
        self.blocked(evidence, reason="historical_eight_apps_must_remain_covered")

    def test_page_only_screenshots_short_soak_integrity_and_historical_consent_do_not_pass(self):
        mutations = [
            (lambda e: e["apps"]["com.Hyatt.hyt"]["official_candidate"].update(status="page_only"), "store_page_alone"),
            (lambda e: e["apps"]["com.Hyatt.hyt"]["checks"]["soak"].update(active_monitor_seconds=1), "continuous_runtime"),
            (lambda e: e["apps"]["com.Hyatt.hyt"]["checks"]["integrity"].update(commercial_integrity_clear=False), "explicit_true_required"),
            (lambda e: e["apps"]["tv.danmaku.bili"]["checks"]["login_or_guest"].update(accept_executed=True,
                 historical_test_consent_reused=True, authorization_cell="p4-bili-m30-cell-20261010"), "historical_Bilibili_cell"),
        ]
        for mutate, reason in mutations:
            with self.subTest(reason=reason):
                evidence = copy.deepcopy(self.evidence)
                mutate(evidence)
                self.blocked(evidence, reason=reason)
        evidence = copy.deepcopy(self.evidence)
        for ref in evidence["references"].values():
            if ref["kind"] in ("runtime_log", "ui_hierarchy"):
                ref["kind"] = "screenshot"
        self.blocked(evidence, reason="required_evidence_kind_missing:runtime_log")

    def test_framework_and_cleanup_require_settlement_and_current_artifact_protection(self):
        evidence = copy.deepcopy(self.evidence)
        evidence["framework"]["latest_official_for_target"] = None
        self.blocked(evidence, reason="explicit_true_required")
        for field in ("final_source_exists", "unknown_and_failure_items_settled"):
            with self.subTest(field=field):
                evidence = copy.deepcopy(self.evidence)
                evidence["retention"][field] = False
                result = evaluate(evidence, self.policy)
                self.assertIs(result["production_ready"], True)
                self.assertIs(result["cleanup_eligible"], False)
        evidence = copy.deepcopy(self.evidence)
        evidence["retention"]["obsolete_artifacts"] = [{"path": "/synthetic/current.apk", "kind": "obsolete_app",
             "sha256": evidence["apps"]["com.Hyatt.hyt"]["current_identity"]["apk_sha256s"][0]}]
        result = evaluate(evidence, self.policy)
        self.assertIs(result["cleanup_eligible"], False)
        self.assertTrue(any("current_or_retained" in b["reason"] for b in result["cleanup_blockers"]))

    def test_review_counterexamples_cannot_splice_provenance_or_delete_roots_or_fake_components(self):
        evidence = copy.deepcopy(self.evidence)
        pin = evidence["framework"]["provenance_refs"][0]
        evidence["references"][pin]["kind"] = "unrelated_report"
        other = copy.deepcopy(evidence["references"][pin])
        other.update(kind="official_framework_provenance", sha256=digest("not-the-pinned-official-report"))
        evidence["references"]["unpinned-official-report"] = other
        evidence["framework"]["provenance_refs"].append("unpinned-official-report")
        self.blocked(evidence, reason="framework_provenance_not_independently_pinned")
        evidence = copy.deepcopy(self.evidence)
        for row in evidence["launcher_inventory"]["rows"]:
            row["components"] = [row["package"] + "/"]
        evidence["launcher_inventory"]["resolved_set_sha256"] = digest(evidence["launcher_inventory"]["rows"])
        self.blocked(evidence, reason="activity_class_invalid")
        for path in ("/", "/home/alex/work/final", "/home/alex/work/final/../old"):
            with self.subTest(path=path):
                evidence = copy.deepcopy(self.evidence)
                source = next(r for r in evidence["references"].values() if r["kind"] == "final_source")
                source["uri"] = "/home/alex/work/final/source.py"
                evidence["retention"]["obsolete_artifacts"] = [{"path": path, "sha256": digest("obsolete"),
                                                                "kind": "obsolete_build", "artifact_type": "regular_file"}]
                result = evaluate(evidence, self.policy)
                self.assertIs(result["cleanup_eligible"], False)


if __name__ == "__main__":
    unittest.main()
