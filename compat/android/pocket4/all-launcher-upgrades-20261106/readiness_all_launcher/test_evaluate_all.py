"""Local synthetic counterexamples, never Android evidence or real QA results."""
import copy
import unittest

import evaluate_all as gate


class SyntheticReceipts:
    def __init__(self):
        self.references = {}
        self.binding = {"runtime_identity_sha256": gate.digest("synthetic runtime"),
                        "helper_identity_sha256": gate.digest("synthetic helper"),
                        "app_identity_sha256": gate.digest("synthetic app")}

    def record(self, kinds, **values):
        ids = []
        for kind in kinds:
            key = "unit-test-only-" + str(len(self.references))
            self.references[key] = {"kind": kind, "sha256": gate.digest(key),
                                    "uri": "unit-test-only://" + key,
                                    "captured_at": "2026-11-06T12:00:00+00:00",
                                    "binding": copy.deepcopy(self.binding)}
            ids.append(key)
        return dict(status="pass", scope="production", binding=copy.deepcopy(self.binding),
                    evidence_refs=ids, **values)

    def audit(self, policy=None):
        return gate.Audit({"references": self.references}, policy or gate.make_policy())


class Boundaries(unittest.TestCase):
    def test_unknown_template_covers_45_136_12_and_never_passes(self):
        policy = gate.make_policy()
        evidence = gate.make_template(policy)
        result = gate.evaluate(evidence, policy)
        self.assertEqual(len(evidence["apps"]), 45)
        self.assertEqual(sum(len(a["catalog_checks"]["cases"]) for a in evidence["apps"].values()), 136)
        self.assertEqual(len(gate.NETWORK), 12)
        self.assertFalse(result["production_ready"])
        self.assertEqual(result["production_ready_app_count"], 0)
        self.assertEqual(set(result["apps"]), set(gate.APPS))
        self.assertTrue(all(a["status"] == gate.UNKNOWN for a in result["apps"].values()))
        self.assertFalse(any("invalid_structure" in x["reason"] for x in result["global_blockers"]))
        self.assertFalse(result["cleanup_eligible"])
        self.assertFalse(result["cleanup_authorized"])
        self.assertEqual(result["actions_executed"], [])

    def test_fresh_added_and_absent_packages_are_explicitly_blocking(self):
        packages = set(gate.APPS) | {"org.example.newlauncher"}
        packages.remove("com.android.camera2")
        audit = gate.Audit({"apps": dict.fromkeys(gate.APPS, {})}, gate.make_policy())
        added, absent = audit.scope_gate(packages)
        self.assertEqual(added, ["org.example.newlauncher"])
        self.assertEqual(absent, ["com.android.camera2"])
        self.assertTrue(any("no_silent_omission" in e["reason"] for e in audit.errors))
        evidence = gate.make_template(gate.make_policy())
        evidence["launcher_inventory"]["rows"] = [{"package": "org.example.newlauncher", "components": ["org.example.newlauncher/.Main"], "app_class": "third_party"}]
        result = gate.evaluate(evidence, gate.make_policy())
        self.assertIn("org.example.newlauncher", result["apps"])
        self.assertFalse(result["apps"]["org.example.newlauncher"]["production_ready"])

    def test_original_eight_core_and_thresholds_cannot_be_weakened(self):
        policy = gate.make_policy()
        policy["proposed_acceptance_thresholds"]["continuous_soak_seconds"] = 30
        policy["apps"]["tv.danmaku.bili"]["core_flows"] = {"startup": "only opening a page"}
        policy["apps"]["com.enflick.android.TextNow"]["allowed_session_modes"] = ["guest"]
        audit = gate.Audit({}, policy)
        audit.policy_gates()
        reasons = [x["reason"] for x in audit.errors]
        self.assertIn("acceptance_threshold_must_not_be_reduced", reasons)
        self.assertGreaterEqual(reasons.count("reviewed_core_session_or_artifact_contract_changed"), 2)

    def offline_control(self):
        fixture = SyntheticReceipts()
        row = gate.APPS["com.android.documentsui"]
        rule = copy.deepcopy(gate.make_policy()["apps"][row["package"]])
        inventory = fixture.record(["enabled_feature_configuration", "network_applicability_contract"],
            complete=True, disabled_is_not_missing_capability=True, configuration_sha256=gate.digest("synthetic local config"), enabled_branch_ids=[])
        rule["online_branch_review"] = {"status": "reviewed", "configuration_sha256": inventory["configuration_sha256"],
                                        "enabled_branch_ids": [], "proof_sha256s": [fixture.references[inventory["evidence_refs"][0]]["sha256"]]}
        kinds, fields, _ = gate.NETWORK["offline_local"]
        record = fixture.record(kinds, profile="offline_local", branch_inventory=inventory, branches={},
                                tls_or_integrity_bypass_used=False, source_or_endpoint_spoofed=False,
                                **dict.fromkeys(fields, True))
        return fixture, row, rule, record

    def test_real_local_contract_does_not_require_dns_and_cannot_invent_it(self):
        fixture, row, rule, record = self.offline_control()
        audit = fixture.audit()
        audit.network_profile(record, row, rule, fixture.binding, "network")
        self.assertEqual(audit.errors, [])
        record["app_level_dns_tls_response_verified"] = True
        audit = fixture.audit()
        audit.network_profile(record, row, rule, fixture.binding, "network")
        self.assertTrue(any("fabricate_app_owned_DNS_TLS" in x["reason"] for x in audit.errors))

    def test_missing_offline_proof_and_new_online_branch_are_not_NA(self):
        fixture, row, rule, record = self.offline_control()
        record["core_completed_while_offline"] = "N/A"
        record["branch_inventory"]["enabled_branch_ids"] = ["actual-cloud-provider"]
        audit = fixture.audit()
        audit.network_profile(record, row, rule, fixture.binding, "network")
        self.assertTrue(any(x["path"].endswith("core_completed_while_offline") for x in audit.errors))
        self.assertTrue(any("all_actual_enabled_online_branches" in x["reason"] for x in audit.errors))

    def test_controlled_peer_and_camera_absence_cannot_be_waived(self):
        policy = gate.make_policy()
        evidence = gate.make_template(policy)
        app = evidence["apps"]["com.android.camera2"]
        app["catalog_checks"]["hardware"]["0"].update(status="pass", actual_state="not_applicable")
        audit = gate.Audit(evidence, policy)
        bound = {"runtime_identity_sha256": "a" * 64, "helper_identity_sha256": "b" * 64}
        audit.catalog_app("com.android.camera2", app, bound, 37)
        self.assertTrue(any("missing_required_hardware_is_blocking_not_NA" in x["reason"] for x in audit.errors))
        app = evidence["apps"]["com.enflick.android.TextNow"]
        app["catalog_checks"]["cases"]["controlled_call"]["profiles"]["controlled_peer_receipt"] = {"status": "N/A"}
        audit = gate.Audit(evidence, policy)
        audit.catalog_app("com.enflick.android.TextNow", app, bound, 37)
        self.assertTrue(any(x["path"].endswith("explicit_communication_authorized") for x in audit.errors))

    def lifecycle_control(self):
        fixture = SyntheticReceipts()
        checks = {
            "soak": fixture.record(gate.KINDS["soak"], started_at="2026-11-06T10:00:00+00:00", finished_at="2026-11-06T11:00:00+00:00",
                active_monitor_seconds=3600, sample_count=61, continuous_probe_coverage=True, resource_budget_met=True, core_still_usable=True, crashes=0, anrs=0),
            "restart": fixture.record(gate.KINDS["restart"], cycles=[]),
            "fault_recovery": fixture.record(gate.KINDS["fault_recovery"], process_death_recovered=True, no_security_bypass=True, dependency_cycles=[]),
        }
        for i in range(3):
            checks["restart"]["cycles"].append(fixture.record(["app_restart_trace"], cycle_id="r" + str(i), core_resumed=True, data_preserved=True,
                before_process_identity_sha256=gate.digest("before" + str(i)), after_process_identity_sha256=gate.digest("after" + str(i))))
            checks["fault_recovery"]["dependency_cycles"].append(fixture.record(["app_fault_recovery_trace"], cycle_id="f" + str(i), core_resumed=True, data_preserved=True,
                dependency_kind="offline_continuity", fault_effect_observed=True, recovery_observed=True, actual_fault="Synthetic offline transition and provider rejection",
                actual_recovery="Synthetic local readback after provider recovery", offline_observed=True, online_observed=True, local_core_continued=True))
        return fixture, checks

    def test_local_lifecycle_control_and_3599_seconds_two_cycles_rejected(self):
        fixture, checks = self.lifecycle_control()
        row = gate.APPS["com.android.documentsui"]
        audit = fixture.audit()
        audit.lifecycle(checks, fixture.binding, row, "checks")
        self.assertEqual(audit.errors, [])
        checks["soak"]["active_monitor_seconds"] = 3599
        checks["soak"]["finished_at"] = "2026-11-06T10:59:59+00:00"
        checks["restart"]["cycles"].pop()
        checks["fault_recovery"]["dependency_cycles"].pop()
        audit = fixture.audit()
        audit.lifecycle(checks, fixture.binding, row, "checks")
        reasons = [x["reason"] for x in audit.errors]
        self.assertIn("continuous_soak_below_threshold_or_unknown", reasons)
        self.assertEqual(reasons.count("three_or_policy_minimum_actual_cycles_required"), 2)

    def test_stale_helper_and_IME_direct_injection_never_count(self):
        fixture, row, rule, record = self.offline_control()
        record["binding"]["helper_identity_sha256"] = gate.digest("old helper")
        audit = fixture.audit()
        audit.network_profile(record, row, rule, fixture.binding, "network")
        self.assertTrue(any("identity_mismatch" in x["reason"] for x in audit.errors))
        policy = gate.make_policy()
        evidence = gate.make_template(policy)
        app = evidence["apps"]["org.fcitx.fcitx5.android"]
        case = app["catalog_checks"]["cases"]["chinese_candidates"]
        case["profiles"]["ime_commit"]["direct_edit_injection_counted_as_IME"] = True
        audit = gate.Audit(evidence, policy)
        audit.catalog_app("org.fcitx.fcitx5.android", app, fixture.binding, 37)
        self.assertTrue(any(x["path"].endswith("direct_edit_injection_counted_as_IME") for x in audit.errors))

    def test_bili_accept_and_meituan_location_still_hit_frozen_gates(self):
        policy = gate.make_policy()
        evidence = gate.make_template(policy)
        bili = evidence["apps"]["tv.danmaku.bili"]
        bili["checks"]["login_or_guest"]["accept_executed"] = True
        mt = evidence["apps"]["com.sankuai.meituan.takeoutnew"]
        mt["checks"]["permissions"].update(grants_before=[], grants_after=["android.permission.ACCESS_FINE_LOCATION"], active_grants=["android.permission.ACCESS_FINE_LOCATION"])
        audit = gate.Audit(evidence, policy)
        binding = {"runtime_identity_sha256": "a" * 64, "helper_identity_sha256": "b" * 64}
        audit.catalog_app("tv.danmaku.bili", bili, binding, 37)
        audit.catalog_app("com.sankuai.meituan.takeoutnew", mt, binding, 37)
        self.assertTrue(any(x["path"].endswith("accept_executed") for x in audit.errors))
        self.assertTrue(any("Meituan_FINE_or_COARSE" in x["reason"] for x in audit.errors))

    def test_zero_version_code_requires_actual_manifest_not_unknown(self):
        policy = gate.make_policy()
        evidence = gate.make_template(policy)
        app = evidence["apps"]["local.pocket4.fixture"]
        identity = app["current_identity"]
        identity.update(uid=10115, version_code=0, version_name=None, version_name_state="absent_in_verified_manifest",
                        apk_sha256s=["c" * 64], signer_sha256s=["d" * 64])
        app["identity_before"] = copy.deepcopy(identity)
        app["identity_after"] = copy.deepcopy(identity)
        binding = {"runtime_identity_sha256": "a" * 64, "helper_identity_sha256": "b" * 64}
        audit = gate.Audit(evidence, policy)
        audit.local_app("local.pocket4.fixture", app, binding, 37)
        self.assertFalse(any("zero_versionCode" in x["reason"] for x in audit.errors))
        identity.pop("version_name_state")
        audit = gate.Audit(evidence, policy)
        audit.local_app("local.pocket4.fixture", app, binding, 37)
        self.assertTrue(any("zero_versionCode" in x["reason"] for x in audit.errors))

    def test_arbitrary_equal_data_dict_is_not_CE_DE_identity(self):
        policy = gate.make_policy()
        evidence = gate.make_template(policy)
        app = evidence["apps"]["local.pocket4.fixture"]
        app["catalog_checks"]["data_identity"].update(before={"placeholder": 1}, after={"placeholder": 1})
        audit = gate.Audit(evidence, policy)
        audit.catalog_app("local.pocket4.fixture", app, {"runtime_identity_sha256": "a" * 64, "helper_identity_sha256": "b" * 64}, 37)
        self.assertTrue(any("actual_UID_user_and_storage_model_required" in x["reason"] for x in audit.errors))
        self.assertTrue(any("CE_DE_absence_requires_actual_proof" in x["reason"] for x in audit.errors))

    def test_complete_inventory_under_unqualified_runtime_is_not_fresh_proof(self):
        policy = gate.make_policy()
        evidence = gate.make_template(policy)
        fixture = SyntheticReceipts()
        fixture.binding = {"runtime_identity_sha256": gate.digest(evidence["runtime"]["identity"]),
                           "helper_identity_sha256": gate.digest(evidence["runtime"]["helpers"])}
        rows = [{"package": p, "components": [p + "/.Main"], "app_class": "third_party"} for p in sorted(gate.APPS)]
        evidence["launcher_inventory"] = fixture.record(["current_launcher_query"],
            origin="current_runtime_query", complete=True, all_query_processes_joined=True,
            query_exit_code=0, android_user=0, action="android.intent.action.MAIN", category="android.intent.category.LAUNCHER",
            rows=rows, resolved_set_sha256=gate.digest(rows), query_started_at="2026-11-06T10:00:00+00:00",
            query_finished_at="2026-11-06T10:00:01+00:00", cache_bypassed=True, resolver_generation_sha256="a" * 64)
        evidence["references"] = fixture.references
        evidence["collected_at"] = "2026-11-06T12:00:00+00:00"
        audit = gate.Audit(evidence, policy)
        self.assertEqual(audit.inventory(fixture.binding), set(gate.APPS))
        self.assertEqual(audit.errors, [])
        result = gate.evaluate(evidence, policy)
        self.assertFalse(result["fresh_resolver_proven"])
        self.assertFalse(result["production_ready"])

    def test_duplicate_keys_nonfinite_and_NA_are_rejected(self):
        for raw in (b'{"x":1,"x":2}', b'{"x":NaN}', b'{"x":Infinity}'):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                gate.decode(raw)
        for value in (None, "N/A", "UNKNOWN_NOT_RUN", "NOT_APPLICABLE", "SKIPPED"):
            self.assertFalse(gate.known(value))

    def test_malformed_evidence_still_retains_newly_observed_package(self):
        policy = gate.make_policy()
        evidence = gate.make_template(policy)
        evidence["launcher_inventory"]["rows"] = [{"package": "org.example.newlauncher"}]
        policy["proposed_acceptance_thresholds"] = None
        result = gate.evaluate(evidence, policy)
        self.assertFalse(result["production_ready"])
        self.assertIn("org.example.newlauncher", result["apps"])


if __name__ == "__main__":
    unittest.main()
