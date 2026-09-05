"""Shared origin vectors and signed-manifest identity regression tests."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from tests.d5 import test_trusted_app_bundle as fixtures
from tools import trusted_app_bundle as bundle

ROOT = Path(__file__).resolve().parents[2]


class TrustedAppOriginConformanceTests(unittest.TestCase):
    def test_shared_vectors(self) -> None:
        count = 0
        for line in (ROOT / "contracts/golden/trusted-app-origins.v1.tsv").read_text().splitlines():
            if not line or line.startswith("#"):
                continue
            app_hex, publisher_hex, expected = line.split("\t")
            app = bytes.fromhex(app_hex).decode("utf-8")
            publisher = bytes.fromhex(publisher_hex).decode("utf-8")
            with self.subTest(app=app, publisher=publisher):
                if expected == "-":
                    with self.assertRaises(bundle.VerificationError):
                        bundle.derived_origin(app, publisher)
                else:
                    self.assertEqual(bundle.derived_origin(app, publisher), expected)
            count += 1
        self.assertGreaterEqual(count, 43)

    def test_publisher_identity_prevents_same_app_origin_collision(self) -> None:
        self.assertNotEqual(bundle.derived_origin("notes", "alpha"),
                            bundle.derived_origin("notes", "beta"))

    def test_non_string_labels_are_rejected(self) -> None:
        for value in (None, True, 42, [], {}):
            for app, publisher in ((value, "publisher"), ("notes", value)):
                with self.subTest(app=app, publisher=publisher):
                    with self.assertRaises(bundle.VerificationError):
                        bundle.derived_origin(app, publisher)

    def test_contract_and_machine_origin_policy_agree(self) -> None:
        contract = json.loads((ROOT / "contracts/trusted-app-bundle.v1.json").read_text())
        manifest = json.loads((ROOT / "docs/MANIFEST.json").read_text())
        self.assertEqual(contract["format"]["manifest_schema"],
                         "trillionnium.desktop.trusted-app-manifest.v2")
        self.assertEqual(contract["origin"]["host_suffix"], ".apps.hepta.invalid")
        self.assertEqual(contract["origin"]["host_identity_fields"], ["app_id", "publisher_id"])
        self.assertFalse(contract["origin"]["trailing_slash_allowed"])
        self.assertFalse(contract["origin"]["legacy_app_only_origin_allowed"])
        self.assertEqual(manifest["trusted_app_origin_model"],
                         "distinct_synthetic_https_hosts_under_apps.hepta.invalid")

    def test_signed_bundle_rejects_legacy_origin_or_foreign_publisher(self) -> None:
        fixtures.TrustedAppBundleTests.setUpClass()
        helper = fixtures.TrustedAppBundleTests()
        for origin in ("https://notes.trusted.invalid/",
                       "https://notes.foreign.apps.hepta.invalid",
                       "https://notes.trillionnium-fixture.apps.hepta.invalid/"):
            with self.subTest(origin=origin):
                manifest, _ = fixtures.build_fixture_manifest(
                    contract=helper.contract, content=helper.base_content(), seed=fixtures.SEED_1,
                )
                manifest["synthetic_origin"] = origin
                helper.resign(manifest)
                helper.assert_rejected("SYNTHETIC_ORIGIN_MISMATCH", lambda: helper.verify(
                    manifest, helper.base_content(),
                ))

    def test_v1_manifest_cannot_silently_enter_v2_verification(self) -> None:
        fixtures.TrustedAppBundleTests.setUpClass()
        helper = fixtures.TrustedAppBundleTests()
        manifest, _ = fixtures.build_fixture_manifest(
            contract=helper.contract, content=helper.base_content(), seed=fixtures.SEED_1,
        )
        manifest["schema"] = "trillionnium.desktop.trusted-app-manifest.v1"
        helper.resign(manifest)
        helper.assert_rejected("MANIFEST_SCHEMA_MISMATCH", lambda: helper.verify(
            manifest, helper.base_content(),
        ))


if __name__ == "__main__":
    unittest.main()
