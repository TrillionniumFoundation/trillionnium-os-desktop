"""Versioned contract/API regressions; never native or installed evidence."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import tempfile
import unittest
from tools import verify_configured_retained_bootstrap as verifier

ROOT = Path(__file__).resolve().parents[1]

class ConfiguredRetainedBootstrapContractTests(unittest.TestCase):
    def text(self):
        return (ROOT / verifier.SOURCE).read_text(encoding="utf-8")
    def contract(self):
        return verifier.load(ROOT / verifier.CONTRACT)

    def test_actual_four_public_signatures_and_versioned_closed_contract_match(self):
        verifier.validate()
        self.assertEqual(len(verifier.SIGNATURES), 4)
        self.assertEqual(set(self.contract()["api"]), set(verifier.SIGNATURES))

    def test_unknown_missing_and_reordered_semantic_fields_refuse(self):
        value = self.contract()
        mutants = []
        missing = copy.deepcopy(value); del missing["authority"]["role_selections"]
        mutants.append(missing)
        unknown = copy.deepcopy(value); unknown["authority"]["caller_approved"] = False
        mutants.append(unknown)
        for key in verifier.SIGNATURES:
            missing = copy.deepcopy(value); del missing["api"][key]
            mutants.append(missing)
        reordered = copy.deepcopy(value)
        reordered["verification"]["host_cases"].reverse()
        mutants.append(reordered)
        for mutant in mutants:
            with self.subTest(mutant=mutant):
                with self.assertRaises(ValueError): verifier.check(mutant, self.text())

    def test_false_claims_and_original_bounds_reject_numeric_boolean_aliases(self):
        for group, field, values in [
            ("authority", "principal_from_caller", [0, True, "false"]),
            ("scope", "accepted_seconds_maximum", [20.0, True, 21]),
            ("scope", "renewed_budget", [0, True]),
            ("scope", "local_refusal_proves_remote_custodian_cleanup", [0, True]),
            ("non_claims", "actual_servo_execution", [0, True]),
            ("non_claims", "installed_service_wired", [0, True]),
            ("non_claims", "signing_release_production_ready", [0, True]),
        ]:
            for wrong in values:
                with self.subTest(group=group, field=field, wrong=wrong):
                    value = self.contract(); value[group][field] = wrong
                    with self.assertRaises(ValueError): verifier.check(value, self.text())

    def test_signature_contract_cannot_approve_caller_authority_or_borrowed_consumption(self):
        for before, after in [
            ("connection: RootPathControlConnection", "connection: bool"),
            ("document: ApprovedPolicyDocument", "document: TaskFlowPrincipal"),
            ("pub fn into_admission(mut self)", "pub fn into_admission(&mut self)"),
            ("pub fn original_deadline(&mut self)", "pub fn original_deadline(&self)"),
        ]:
            with self.subTest(before=before):
                text = self.text(); self.assertIn(before, text)
                # The document type also occurs in private storage. Change
                # its final occurrence, the public constructor parameter.
                changed = after.join(text.rsplit(before, 1))
                with self.assertRaises(ValueError): verifier.check(self.contract(), changed)
                value = self.contract()
                for api in value["api"].values():
                    api["signature"] = api["signature"].replace(before, after)
                with self.assertRaises(ValueError): verifier.check(value, changed)

    def test_new_public_factory_or_changed_opaque_state_refuse(self):
        for text in [
            self.text() + "\npub fn split_pair() {}\n",
            self.text() + "\npub struct CallerApprovedPrincipal {}\n",
            self.text().replace("    receiver: RootPathAttestedHandoffReceiver", "    pub receiver: RootPathAttestedHandoffReceiver", 1),
            self.text().replace("    document: ApprovedPolicyDocument", "    document: TaskFlowPrincipal", 1),
        ]:
            with self.assertRaises(ValueError): verifier.check(self.contract(), text)

    def test_comments_and_literals_cannot_supply_public_api_inventory(self):
        source = self.text()
        verifier.check(self.contract(), source + '\n// pub fn split_pair() {}\nconst TEXT: &str = "pub struct Principal {}";\n')
        changed = source.replace("pub fn into_admission(mut self)", "fn into_admission(mut self)", 1)
        with self.assertRaises(ValueError):
            verifier.check(self.contract(), changed + "\n// pub fn into_admission(mut self) -> Result<ApprovedRetainedAdmission, ProductDispatchError> {}\n")

    def test_duplicate_json_fields_and_non_finite_json_refuse_before_contract_check(self):
        original = json.dumps(self.contract())
        with tempfile.TemporaryDirectory(prefix="configured-bootstrap-contract-") as directory:
            path = Path(directory) / "contract.json"
            for before, after in [
                ('"default_activation": false', '"default_activation": false, "default_activation": false'),
                ('"accepted_seconds_maximum": 20', '"accepted_seconds_maximum": 20, "accepted_seconds_maximum": 20'),
                ('"accepted_seconds_maximum": 20', '"accepted_seconds_maximum": NaN'),
                ('"accepted_seconds_maximum": 20', '"accepted_seconds_maximum": 1e999'),
            ]:
                with self.subTest(before=before, after=after):
                    self.assertIn(before, original)
                    path.write_text(original.replace(before, after, 1), encoding="utf-8")
                    with self.assertRaises(ValueError): verifier.load(path)

    def test_existing_host_case_names_are_inventory_only(self):
        value = self.contract()
        self.assertEqual(len(value["verification"]["host_cases"]), 4)
        self.assertFalse(value["non_claims"]["actual_servo_execution"])
        self.assertFalse(value["non_claims"]["installed_service_wired"])
        for case in value["verification"]["host_cases"]:
            self.assertIn('"' + case + '"', (ROOT / value["verification"]["host_kernel"]).read_text())

if __name__ == "__main__":
    unittest.main()
