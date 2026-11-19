#!/usr/bin/env python3
"""Host-only contract tests; no existing runtime modules are imported."""
import copy
import json
from pathlib import Path
import tempfile
import unittest

import preflight as p


class PreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.input_dir = Path(__file__).resolve().parent / "inputs"
        cls.original, cls.bookends = p.load_bundle(cls.input_dir)

    def bundle(self):
        return copy.deepcopy(self.original)

    def refused(self, docs, reason):
        with self.assertRaisesRegex(p.PreflightError, reason):
            p.build_plan(docs)

    def test_real_snapshot_scope_and_no_credit(self):
        plan = p.build_plan(self.original)
        self.assertEqual(len(plan["packages"]), 39)
        self.assertEqual(plan["counts"]["finite_prepared_case_packages"], 7)
        self.assertEqual(plan["counts"]["packages_without_selected_business_executor"], 32)
        self.assertEqual(plan["counts"]["target_identity_rebinds"], 5)
        self.assertEqual(sum(x["kind"] == "system" for x in plan["packages"]), 10)
        self.assertTrue(all(x["runtime_binding_status"] == "UNRESOLVED_BLOCK_EXECUTION" for x in plan["packages"]))
        p.no_credit(plan)
        united = next(x for x in plan["packages"] if x["package"] == "com.united.mobile.android")
        self.assertEqual(united["source_version"], "4.2.103")
        self.assertEqual(united["latest_update_pending"]["version"], "4.2.104")

    def test_pin_tamper_and_symlink_rejected_before_json(self):
        name = next(iter(p.PINS))
        data = (self.input_dir / name).read_bytes()
        with tempfile.TemporaryDirectory(prefix="p4-metadata-pin-control-") as temp:
            root = Path(temp)
            (root / name).write_bytes(data.replace(b"false", b"true ", 1))
            with self.assertRaisesRegex(p.PreflightError, "SHA"):
                p.load_bundle(root)
        with tempfile.TemporaryDirectory(prefix="p4-metadata-symlink-control-") as temp:
            root = Path(temp)
            (root / name).symlink_to(self.input_dir / name)
            with self.assertRaises(OSError):
                p.load_bundle(root)

    def test_duplicate_json_keys_rejected(self):
        with self.assertRaisesRegex(p.PreflightError, "duplicate JSON key"):
            p.parse_json(b'{"production_ready": false, "production_ready": true}')
        with self.assertRaisesRegex(p.PreflightError, "non-finite"):
            p.parse_json(b'{"version": NaN}')

    def test_required39_and_exemptions_cannot_change(self):
        for mutation in ("duplicate", "missing", "extra_exemption"):
            with self.subTest(mutation=mutation):
                docs = self.bundle()
                apps = docs["CURRENT-SOURCE-STATE.json"]["applications"]
                if mutation == "duplicate":
                    apps[-1] = copy.deepcopy(apps[0])
                elif mutation == "missing":
                    apps.pop()
                else:
                    docs["release-scope.json"]["exemptions"].append({"package": "org.mozilla.firefox"})
                self.refused(docs, {"duplicate": "state duplicate package", "missing": "state/coverage required39 mismatch", "extra_exemption": "exemption scope changed"}[mutation])

    def test_unverified_source_and_broken_registry_link_rejected(self):
        for mutation in ("unverified", "unsigned", "record", "link"):
            with self.subTest(mutation=mutation):
                docs = self.bundle()
                state = docs["CURRENT-SOURCE-STATE.json"]
                if mutation == "unverified":
                    state["applications"][0]["source_identity_verified"] = False
                elif mutation == "unsigned":
                    package = "org.mozilla.firefox"
                    next(x for x in docs["current-source-inputs.json"]["applications"] if x["package"] == package)["signature_verified"] = False
                    next(x for x in state["applications"] if x["package"] == package)["unchanged_current_registry_record"]["signature_verified"] = False
                elif mutation == "record":
                    docs["current-source-inputs.json"]["applications"][0]["version_name"] = "unverified-new-version"
                else:
                    state["current29_registry"]["sha256"] = "0" * 64
                self.refused(docs, {"unverified": "unverified source refused", "unsigned": "source signature/identity missing", "record": "state/registry record mismatch", "link": "state registry reference mismatch"}[mutation])

    def test_nested_runtime_credit_and_selector_count_refused(self):
        for mutation in ("nested_business", "production", "selector"):
            with self.subTest(mutation=mutation):
                docs = self.bundle()
                if mutation == "nested_business":
                    docs["CURRENT-SOURCE-STATE.json"]["applications"][0]["unchanged_current_registry_record"]["business_qualified"] = True
                elif mutation == "production":
                    docs["COVERAGE.json"]["rows"][0]["source_state_production_ready"] = True
                else:
                    docs["selection13.json"]["new_runtime_acceptance_count"] = 13
                self.refused(docs, "runtime/action counter refused" if mutation == "selector" else "runtime/latest promotion refused")

    def test_mismatch_cannot_be_hidden_or_forged(self):
        for mutation in ("remove", "fake_match"):
            with self.subTest(mutation=mutation):
                docs = self.bundle()
                row = next(x for x in docs["COVERAGE.json"]["rows"] if x["package"] == "com.android.documentsui")
                if mutation == "remove":
                    del row["target_profile_mismatch"]
                else:
                    row["target_profile_mismatch"]["old_sha256"] = row["target_profile_mismatch"]["current_sha256"]
                self.refused(docs, "five target identity mismatches" if mutation == "remove" else "target mismatch proof")

    def test_firefox_external_effects_or_unapproved_url_refused(self):
        for mutation in ("download", "message_send", "URL", "claim_driver"):
            with self.subTest(mutation=mutation):
                plan = p.firefox_checklist()
                if mutation in ("download", "message_send"):
                    plan["steps"].append({"id": mutation, "action": mutation, "required_observation": "unreviewed", "status": "NOT_EXECUTED"})
                elif mutation == "URL":
                    plan["pages"]["manifesto"]["url"] = "https://unreviewed.example/"
                else:
                    plan["driver_implemented"] = True
                with self.assertRaisesRegex(p.PreflightError, "Firefox plan exceeds"):
                    p.validate_firefox(plan)

    def test_output_cannot_promote_or_omit_common_gates(self):
        base = p.build_plan(self.original)
        for mutation in ("executor", "UID", "common_gate", "business"):
            with self.subTest(mutation=mutation):
                plan = copy.deepcopy(base)
                row = next(x for x in plan["packages"] if x["package"] == "org.mozilla.firefox")
                if mutation == "executor":
                    row["finite_prepared_case_source_exists"] = True
                elif mutation == "UID":
                    row["actual_runtime_bindings"]["UID"] = 10137
                elif mutation == "common_gate":
                    row["common_gate_ids"].remove("stability")
                else:
                    row["business_qualified"] = True
                with self.assertRaisesRegex(p.PreflightError, {"executor": "output cannot promote", "UID": "fabricated or omitted runtime binding", "common_gate": "output omitted a common gate", "business": "runtime/latest promotion refused"}[mutation]):
                    p.validate_plan(plan, self.original)

    def test_output_never_replaces_existing_file(self):
        with tempfile.TemporaryDirectory(prefix="p4-plan-output-control-") as temp:
            target = Path(temp) / "existing.json"
            original = b'unchanged audit artifact\n'
            target.write_bytes(original)
            with self.assertRaises(FileExistsError):
                p.write_new(target, {"production_ready": False})
            self.assertEqual(target.read_bytes(), original)

    def test_installation_prerequisites_cannot_be_omitted_or_promoted(self):
        original = p.build_plan(self.original)
        expected = self.original["CURRENT-SOURCE-STATE.json"]["required_before_installation"]
        self.assertEqual(original["required_before_installation"], expected)
        self.assertIsNot(original["required_before_installation"], expected)
        for mutation in ("all_missing", "migration_missing", "country_available", "expiry_extended", "migration_row", "migration_qualified"):
            with self.subTest(mutation=mutation):
                plan = copy.deepcopy(original)
                if mutation == "all_missing":
                    del plan["required_before_installation"]
                elif mutation == "migration_missing":
                    del plan["required_before_installation"]["Meituan_official_signer_and_existing_userdata_migration"]
                elif mutation in ("country_available", "expiry_extended"):
                    retained = plan["required_before_installation"]["fresh_official_metadata_for_retained_Play_inputs"]["com.bestbuy.android"]
                    retained["restriction" if mutation == "country_available" else "historical_expiry"] = "AVAILABLE" if mutation == "country_available" else "2026-11-20T17:44:09.086253+00:00"
                else:
                    row = next(x for x in plan["packages"] if x["package"] == p.MEITUAN)
                    row["migration_prerequisite" if mutation == "migration_row" else "signer_migration_qualified"] = "COMPLETED" if mutation == "migration_row" else True
                reason = ("runtime/latest promotion refused" if mutation == "migration_qualified" else
                          "Meituan migration prerequisite" if mutation == "migration_row" else
                          "original installation prerequisites")
                with self.assertRaisesRegex(p.PreflightError, reason):
                    p.validate_plan(plan, self.original)
        self.assertEqual(self.original["CURRENT-SOURCE-STATE.json"]["required_before_installation"], expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
