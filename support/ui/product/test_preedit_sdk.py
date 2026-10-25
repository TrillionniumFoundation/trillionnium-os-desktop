"""Actual candidate notice bytes in structural package fixtures, not a UI run."""
import json
from pathlib import Path
import tarfile
import unittest

import desktop
import test_desktop as fixture


def profile_fixture():
    sdk = desktop.native_sdk
    return {"schema": "hepta.verified-original-sdk-source.v1", "sdk_profile": "preedit-callbacks",
        "native_ui_feature": "native-presentation", "upstream_repository": sdk.UPSTREAM,
        "upstream_commit": sdk.REVISION, "upstream_tree": "c6e18be7754f9634492ec5251bac3e8b4f7e09b7",
        "patched_tree": sdk.PREEDIT_TREE, "manifest_sha256": sdk.PREEDIT_MANIFEST_SHA256,
        "patches": sdk.PREEDIT_PATCHES, "prepared_root": "/synthetic/prepared-source",
        "original_metadata_sha256": "a" * 64, "candidate_metadata_sha256": "b" * 64,
        "cargo_config_sha256": "c" * 64, "source_tree_verified": True,
        "all_sdk_packages_same_tree": True, "dependency_edges_verified": True,
        "effects_authority": False, "compiled": False, "runtime_qualified": False,
        "resolved_packages": [{"name": name, "version": "2.0.0", "manifest": manifest}
            for name, manifest in sdk.REQUIRED.items()] + [{"name": "unicode-segmentation",
                "version": "1.12.0", "manifest": "libs/unicode/Cargo.toml"}]}


class PreeditPackageTests(unittest.TestCase):
    def setUp(self):
        self.fixture = fixture.ProductTests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        self.root = self.fixture.root
        self.resources = self.fixture.resource_fixture()
        original = Path(__file__).resolve().parents[1] / "preedit-sdk"
        notice = json.loads((original / "NATIVE-SDK-PATCH.json").read_bytes())
        for record in notice["files"]:
            target = self.resources / record["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((original / Path(record["path"]).name).read_bytes())
        notice_bytes = (original / "NATIVE-SDK-PATCH.json").read_bytes()
        (self.resources / "NATIVE-SDK-PATCH.json").write_bytes(notice_bytes)
        self.profile = profile_fixture()
        self.profile_bytes = desktop.json_bytes(self.profile)
        (self.resources / "NATIVE-SDK-SOURCE.json").write_bytes(self.profile_bytes)
        bundle = desktop.read_json(self.resources / "bundle.json")
        bundle.update(makepadSource=desktop.native_sdk.PREEDIT_SOURCE_ID,
            sdkSourceProfileSha256=desktop.digest(self.profile_bytes),
            sdkNoticeInventorySha256=desktop.digest(notice_bytes), sdkNotices=5)
        (self.resources / "bundle.json").write_bytes(desktop.json_bytes(bundle))

    def test_exact_preedit_notices_round_trip_through_the_package(self):
        self.assertEqual(len(desktop.native_resource_files(self.resources)), 61)
        profile_path = self.root / "profile.json"
        product = desktop.read_json(profile_path)
        product["makepad_sdk"] = self.profile
        profile_path.write_bytes(desktop.json_bytes(product))
        archive = self.fixture.make_archive("a" * 40, b"preedit fixture", sdk_profile_sha=desktop.digest(self.profile_bytes))
        package = self.root / "preedit.tar.gz"
        desktop.pack(archive, "a" * 40, profile_path, package, self.resources)
        extracted = self.root / "unpacked"
        extracted.mkdir()
        with tarfile.open(package) as archive:
            archive.extractall(extracted, filter="data")
        self.assertEqual(desktop.verify_package(extracted / "trillionnium-desktop")["effects_authorized"], False)

    def test_preedit_cannot_be_relabelled_as_the_historical_clipboard_candidate(self):
        self.profile.pop("sdk_profile")
        self.profile["native_ui_feature"] = "native-clipboard-sdk"
        with self.assertRaisesRegex(ValueError, "Unknown original SDK source"):
            desktop.native_sdk.validate_profile(self.profile)
        bundle = desktop.read_json(self.resources / "bundle.json")
        bundle["makepadSource"] = desktop.native_sdk.SOURCE_ID
        (self.resources / "bundle.json").write_bytes(desktop.json_bytes(bundle))
        with self.assertRaisesRegex(desktop.ProductError, "mixed SDK"):
            desktop.native_resource_files(self.resources)

    def test_modified_actual_patch_bytes_are_rejected_before_packaging(self):
        path = self.resources / "dependency-notices/makepad/native-preedit-callbacks.patch"
        raw = path.read_bytes()
        path.write_bytes(raw[:-1] + b"!")
        with self.assertRaisesRegex(desktop.ProductError, "resource bytes mismatch"):
            desktop.native_resource_files(self.resources)

    def test_baseline_binary_profile_cannot_bind_preedit_resources(self):
        with self.assertRaisesRegex(desktop.ProductError, "differs from the binary source profile"):
            desktop.native_resource_files(self.resources, "b" * 40, None)
