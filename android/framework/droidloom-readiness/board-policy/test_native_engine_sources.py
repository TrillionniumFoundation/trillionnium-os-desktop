"""Reject mixed static APK sources and false runtime/label promotion."""
import copy
import json
from pathlib import Path
import unittest
import verify_native_engine_observer as v

HERE = Path(__file__).resolve().parent


class EngineSelectedSources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads((HERE / v.CONTRACT).read_bytes())
        cls.selection, cls.signatures = [
            json.loads((HERE.parents[3] / v.SELECTED_DOCUMENTS[key]).read_bytes())
            for key in ("selection", "signature_receipt")
        ]

    def metadata(self, selection=None, signatures=None):
        return v._metadata_summary(
            self.selection if selection is None else selection,
            self.signatures if signatures is None else signatures,
            v.FIXED_PUBLIC_INPUTS,
        )

    def test_actual_joint_sources_are_41_packages_and_67_materials(self):
        proof = v.source_contract(HERE)["contents"]
        metadata = json.loads(proof["selected_public_inputs"]["metadata_contents"])
        self.assertEqual(len(metadata["rows"]), 41)
        self.assertEqual(metadata["material_count"], 67)
        self.assertEqual(metadata["selection_role_counts"], {"system": 10, "third_party": 31})
        self.assertFalse(metadata["runtime_qualified"])
        self.assertFalse(metadata["actual_seapp_label_observed"])
        self.assertTrue(all(row["actual_package_inspection"] is None
                            and row["runtime_accepted"] is False for row in metadata["rows"]))

    def test_actual_stock_minimum_and_legacy_target_are_preserved(self):
        rows = {row["package"]: row for row in self.metadata()["rows"]}
        self.assertEqual((rows["com.android.calendar"]["min_sdk"], rows["com.android.calendar"]["target_sdk"]), (37, 34))
        self.assertEqual((rows["com.android.messaging"]["min_sdk"], rows["com.android.messaging"]["target_sdk"]), (37, 24))

    def test_new_packages_use_original_rules_only_under_explicit_conditions(self):
        proof = v._conditional_summary(self.metadata(), self.contract["selected_seapp"])
        rows = {row["package"]: row for row in proof["ordinary_default_candidate_rows"]}
        self.assertEqual(rows["com.ss.android.lark"]["conditional_domain"], "untrusted_app_34")
        self.assertEqual(rows["com.ss.android.article.news"]["conditional_domain"], "untrusted_app_32")
        self.assertEqual(len(rows), 31)
        self.assertTrue(proof["selection_role_does_not_prove_conditions"])
        self.assertTrue(proof["runtime_uid_seinfo_privilege_and_label_required"])
        self.assertFalse(proof["process_type_set_extended"])
        self.assertFalse(proof["actual_seapp_label_observed"])

    def test_mixed_signature_version_or_material_is_rejected(self):
        for field in ("version_code", "signer_certificates_sha256", "material"):
            signatures = copy.deepcopy(self.signatures)
            row = signatures["rows"][0]
            if field == "version_code":
                row[field] += 1
            elif field == "signer_certificates_sha256":
                row[field] = ["0" * 64]
            else:
                row["files"][0]["sha256"] = "0" * 64
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.metadata(signatures=signatures)

    def test_duplicate_source_package_cannot_replace_a_selected_package(self):
        selection = copy.deepcopy(self.selection)
        selection["applications"][1] = copy.deepcopy(selection["applications"][0])
        with self.assertRaisesRegex(ValueError, "roster"):
            self.metadata(selection=selection)

    def test_extra_seapp_selector_or_duplicate_threshold_is_rejected(self):
        original = self.contract["selected_seapp"]["platform_contents"]
        line = next(row for row in original.splitlines()
                    if "minTargetSdkVersion=37 domain=untrusted_app " in row)
        for replacement in (original + line + "\n", original.replace(line, line + " name=foreign")):
            seapp = copy.deepcopy(self.contract["selected_seapp"])
            seapp["platform_contents"] = replacement
            with self.assertRaises(ValueError):
                v._conditional_summary(self.metadata(), seapp)

    def test_saved_metadata_cannot_claim_actual_inspection_or_acceptance(self):
        selected = copy.deepcopy(self.contract["selected_public_inputs"])
        metadata = json.loads(selected["metadata_contents"])
        metadata["rows"][0]["actual_package_inspection"] = {"accepted": True}
        metadata["rows"][0]["runtime_accepted"] = True
        selected["metadata_contents"] = v._json_contents(metadata)
        with self.assertRaisesRegex(ValueError, "static source proof"):
            v._verify_selected_documents(HERE, selected, self.contract["selected_seapp"])


if __name__ == "__main__":
    unittest.main()
