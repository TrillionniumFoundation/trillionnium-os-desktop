"""Historical metadata and cross-SDK deployment regression tests.

The retained B metadata/SDK notices are exact original bytes. Transaction tests
use synthetic ELF and asset bytes: only their package release/manifest and
resource-bundle identities are replaced in test scope. They are not actual B/C
binary runs, original Root authority, or production installation evidence.
"""
import copy
import os
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import desktop
import native_sdk
import test_desktop as fixtures
import trusted_desktop as trusted


RETAINED = Path(__file__).with_name("fixtures") / "historical-sdk-b"


class HistoricalContractTests(unittest.TestCase):
    def test_exact_retained_B_metadata_selects_only_the_fixed_installed_contract(self):
        manifest_bytes = (RETAINED / "manifest.json").read_bytes()
        manifest = desktop.read_json(RETAINED / "manifest.json")
        history = native_sdk.HISTORICAL_B
        self.assertEqual(desktop.digest(manifest_bytes), history["manifest_sha256"])
        self.assertEqual(native_sdk.historical_install_contract(manifest, desktop.digest(manifest_bytes)),
                         native_sdk.HISTORICAL_B_ID)
        for name, key in (("source-profile.json", "source_profile_sha256"),
                          ("resources/bundle.json", "bundle_sha256"),
                          ("resources/NATIVE-SDK-SOURCE.json", "sdk_source_profile_sha256"),
                          ("resources/NATIVE-SDK-PATCH.json", "sdk_notice_inventory_sha256")):
            data = (RETAINED / name).read_bytes()
            self.assertEqual(desktop.digest(data), history[key])
            self.assertEqual((len(data), desktop.digest(data)),
                             (manifest["files"][name]["bytes"], manifest["files"][name]["sha256"]))
        profile = desktop.read_json(RETAINED / "source-profile.json")["makepad_sdk"]
        bundle = desktop.read_json(RETAINED / "resources/bundle.json")
        records = native_sdk.bundle_records(RETAINED / "resources", bundle, desktop.read_json,
                                            desktop.regular_bytes, profile, bind_binary=True,
                                            installed_version=native_sdk.HISTORICAL_B_ID)
        self.assertEqual(len(records), 7)
        for name, entry in records:
            raw = (RETAINED / "resources" / name).read_bytes()
            self.assertEqual((len(raw), desktop.digest(raw)), (entry["bytes"], entry["sha256"]))

    def test_current_source_and_notice_entry_points_still_reject_retained_B(self):
        with self.assertRaisesRegex(ValueError, "Unknown original SDK source or patch profile"):
            native_sdk.validate_profile(desktop.read_json(RETAINED / "resources/NATIVE-SDK-SOURCE.json"))
        with self.assertRaisesRegex(ValueError, "does not identify the reviewed original patch"):
            native_sdk.validate_notice_inventory(desktop.read_json(RETAINED / "resources/NATIVE-SDK-PATCH.json"))
        with self.assertRaisesRegex(desktop.ProductError, "Unpinned Makepad resource sources"):
            desktop.native_resource_files(RETAINED / "resources")

    def test_history_requires_exact_manifest_source_pair_and_inventory(self):
        manifest = desktop.read_json(RETAINED / "manifest.json")
        self.assertIsNone(native_sdk.historical_install_contract(manifest, "0" * 64))
        for name in ("release_id", "desktop_commit", "hepta_commit"):
            with self.subTest(field=name):
                changed = copy.deepcopy(manifest)
                changed[name] = "0" * 40
                with self.assertRaisesRegex(ValueError, "Historical package source identity differs"):
                    native_sdk.historical_install_contract(changed, native_sdk.HISTORICAL_B["manifest_sha256"])
        changed = copy.deepcopy(manifest)
        changed["files"].pop("resources/NATIVE-SDK-SOURCE.json")
        with self.assertRaisesRegex(ValueError, "Historical package inventory differs"):
            native_sdk.historical_install_contract(changed, native_sdk.HISTORICAL_B["manifest_sha256"])
        with self.assertRaisesRegex(ValueError, "Unknown installed SDK history contract"):
            native_sdk.resource_source("arbitrary-old-profile")

    def test_rehashed_changed_profile_or_notices_cannot_become_historical_B(self):
        for changed_name, bundle_key in (("NATIVE-SDK-SOURCE.json", "sdkSourceProfileSha256"),
                                        ("NATIVE-SDK-PATCH.json", "sdkNoticeInventorySha256")):
            with self.subTest(file=changed_name), tempfile.TemporaryDirectory() as temporary:
                resources = Path(temporary)
                for name in ("NATIVE-SDK-SOURCE.json", "NATIVE-SDK-PATCH.json"):
                    shutil.copyfile(RETAINED / "resources" / name, resources / name)
                bundle = desktop.read_json(RETAINED / "resources/bundle.json")
                profile = desktop.read_json(resources / "NATIVE-SDK-SOURCE.json")
                changed = desktop.read_json(resources / changed_name)
                if changed_name == "NATIVE-SDK-SOURCE.json":
                    changed["candidate_metadata_sha256"] = "0" * 64
                else:
                    changed["files"][0]["sha256"] = "0" * 64
                raw = desktop.json_bytes(changed)
                (resources / changed_name).write_bytes(raw)
                bundle[bundle_key] = desktop.digest(raw)
                with self.assertRaisesRegex(ValueError, "Historical SDK notice/source identity differs"):
                    native_sdk.bundle_records(resources, bundle, desktop.read_json, desktop.regular_bytes,
                                              profile, bind_binary=True,
                                              installed_version=native_sdk.HISTORICAL_B_ID)

    def test_current_tree_cannot_be_mixed_with_the_historical_version(self):
        bundle = desktop.read_json(RETAINED / "resources/bundle.json")
        bundle["makepadSource"] = native_sdk.SOURCE_ID
        with self.assertRaisesRegex(ValueError, "Historical SDK source identity differs"):
            native_sdk.bundle_records(RETAINED / "resources", bundle, desktop.read_json,
                                      desktop.regular_bytes, installed_version=native_sdk.HISTORICAL_B_ID)


@unittest.skipUnless(os.geteuid() == 0, "protected deployment tests require a disposable root test process")
class HistoricalDeploymentTests(unittest.TestCase):
    def fixture(self):
        fixture = fixtures.ProductTests()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.addCleanup(fixture.tearDown)
        return fixture

    def setUp(self):
        self.old = self.fixture()
        self.real_history = copy.deepcopy(native_sdk.HISTORICAL_B)
        self.prefix = self.old.root / "root-installed"
        self.package_b = self.old.root / "historical-package"
        shutil.copytree(self.old.package, self.package_b)
        resources = self.old.resource_fixture()
        for name in ("NATIVE-SDK-SOURCE.json", "NATIVE-SDK-PATCH.json", "dependency-notices/makepad"):
            source, target = RETAINED / "resources" / name, resources / name
            if source.is_dir():
                shutil.copytree(source, target)
            else:
                shutil.copyfile(source, target)
        bundle = desktop.read_json(resources / "bundle.json")
        retained_bundle = desktop.read_json(RETAINED / "resources/bundle.json")
        for key in ("heptaSource", "makepadSource", "accessibilitySources", "sdkNotices",
                    "sdkSourceProfileSha256", "sdkNoticeInventorySha256"):
            bundle[key] = retained_bundle[key]
        (resources / "bundle.json").write_bytes(desktop.json_bytes(bundle))
        shutil.copytree(resources, self.package_b / "resources")
        shutil.copyfile(RETAINED / "source-profile.json", self.package_b / "source-profile.json")
        # Even a package-supplied Python sentinel must stay data during all transactions.
        (self.package_b / "native_sdk.py").write_text("raise RuntimeError('packaged Python was executed')\n")
        (self.package_b / "PROVENANCE.txt").write_text(
            f"Source commit: {self.real_history['desktop_commit']}\n"
            f"Makepad source profile SHA256: {self.real_history['sdk_source_profile_sha256']}\n")
        files = {}
        for path in sorted(self.package_b.rglob("*")):
            if path.is_file() and path.name != "manifest.json":
                name = path.relative_to(self.package_b).as_posix()
                data = path.read_bytes()
                mode = 0o755 if name.startswith("bin/") or name == "desktop.py" else 0o644
                path.chmod(mode)
                files[name] = {"sha256": desktop.digest(data), "bytes": len(data), "mode": mode}
        release = self.real_history["desktop_commit"][:12] + "-" + desktop.digest(desktop.json_bytes(files))[:12]
        manifest = {"schema_version": 1, "release_id": release,
                    "desktop_commit": self.real_history["desktop_commit"],
                    "hepta_commit": self.real_history["hepta_commit"],
                    "qualification": "linux-host-package", "effects_authorized": False, "files": files}
        raw = desktop.json_bytes(manifest)
        (self.package_b / "manifest.json").write_bytes(raw)
        synthetic = copy.deepcopy(self.real_history)
        synthetic.update(release_id=release, manifest_sha256=desktop.digest(raw),
                         bundle_sha256=desktop.digest((resources / "bundle.json").read_bytes()))
        scoped = patch.object(native_sdk, "HISTORICAL_B", synthetic)
        scoped.start()
        self.addCleanup(scoped.stop)
        self.selection_b = {"release_id": release, "manifest_sha256": desktop.digest(raw)}
        # Seed an already installed generation; current stage() must not admit B.
        self.prefix.mkdir(mode=0o755)
        (self.prefix / "releases").mkdir(mode=0o755)
        self.installed_b = self.prefix / "releases" / release
        shutil.copytree(self.package_b, self.installed_b)
        desktop.atomic_write(self.prefix / trusted.RECORD, desktop.json_bytes({
            "schema": "trill.native-deployment.v1", "generation": 4,
            "current": self.selection_b, "previous": None}))
        self.current = self.fixture()
        current_resources, current_profile = self.current.patched_resource_fixture()
        current_profile_sha = desktop.digest(desktop.json_bytes(current_profile))
        archive = self.current.make_archive("c" * 40, b"cross-version current fixture",
                                            sdk_profile_sha=current_profile_sha)
        output = self.current.root / "current.tar.gz"
        desktop.pack(archive, "c" * 40, self.current.root / "profile.json", output, current_resources)
        extracted = self.current.root / "current-extracted"
        extracted.mkdir()
        with tarfile.open(output) as packed:
            packed.extractall(extracted, filter="data")
        self.package_c = extracted / "trillionnium-desktop"
        self.manifest_c_sha = desktop.digest((self.package_c / "manifest.json").read_bytes())

    def stage_c(self):
        return trusted.stage(self.package_c, self.prefix, self.manifest_c_sha)

    def snapshot_b(self):
        result = {}
        for path in self.installed_b.rglob("*"):
            info = path.lstat()
            result[path.relative_to(self.installed_b).as_posix()] = (
                info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid,
                info.st_size, info.st_mtime_ns, info.st_ctime_ns,
                desktop.digest(path.read_bytes()) if path.is_file() else None)
        return result

    def test_B_to_C_to_B_to_C_preserves_B_bytes_paths_and_original_selection(self):
        before_b = self.snapshot_b()
        initial = trusted.binding(self.prefix, trusted.read_record(self.prefix))
        self.assertEqual((initial["release_id"], initial["generation"]), (self.selection_b["release_id"], 4))
        upgraded = self.stage_c()
        self.assertEqual(upgraded["generation"], 5)
        self.assertNotEqual(upgraded["program"], initial["program"])
        rolled_back = trusted.rollback(self.prefix)
        self.assertEqual((rolled_back["program"], rolled_back["resources"], rolled_back["program_sha256"]),
                         (initial["program"], initial["resources"], initial["program_sha256"]))
        self.assertEqual(rolled_back["generation"], 6)
        self.assertEqual(trusted.read_record(self.prefix)["current"], self.selection_b)
        self.assertEqual(trusted.binding(self.prefix, trusted.read_record(self.prefix)), rolled_back)
        self.assertEqual((self.stage_c()["program"], trusted.read_record(self.prefix)["generation"]),
                         (upgraded["program"], 7))
        self.assertEqual(self.snapshot_b(), before_b)
        for binding in (initial, upgraded, rolled_back):
            self.assertFalse(binding["human_authority_created"])
            self.assertFalse(binding["production_authority_verified"])

    def test_legacy_current_is_readable_but_incoming_stage_and_pack_stay_current(self):
        desktop.verify_installed_package(self.installed_b, self.selection_b)
        before = (self.prefix / trusted.RECORD).read_bytes()
        with self.assertRaisesRegex(desktop.ProductError, "Unpinned Makepad resource sources"):
            desktop.verify_package(self.package_b)
        with self.assertRaisesRegex(desktop.ProductError, "Unpinned Makepad resource sources"):
            trusted.stage(self.package_b, self.prefix, self.selection_b["manifest_sha256"])
        profile_sha = self.real_history["sdk_source_profile_sha256"]
        archive = self.old.make_archive(self.real_history["desktop_commit"], b"not a new legacy build",
                                        sdk_profile_sha=profile_sha)
        with self.assertRaisesRegex(desktop.ProductError, "Unpinned Makepad resource sources"):
            desktop.pack(archive, self.real_history["desktop_commit"], self.package_b / "source-profile.json",
                         self.old.root / "forbidden.tar.gz", self.package_b / "resources")
        self.assertEqual((self.prefix / trusted.RECORD).read_bytes(), before)
        self.assertFalse((self.old.root / "forbidden.tar.gz").exists())

    def test_undeclared_history_cannot_use_its_own_manifest_as_an_allowlist(self):
        with patch.object(native_sdk, "HISTORICAL_B", self.real_history):
            with self.assertRaisesRegex(desktop.ProductError, "Unpinned Makepad resource sources"):
                desktop.verify_installed_package(self.installed_b, self.selection_b)

    def test_mutated_current_manifest_blocks_upgrade_before_record_or_release_changes(self):
        before = (self.prefix / trusted.RECORD).read_bytes()
        releases = sorted(path.name for path in (self.prefix / "releases").iterdir())
        with (self.installed_b / "manifest.json").open("ab") as stream:
            stream.write(b"\n")
        with self.assertRaisesRegex(desktop.ProductError, "Selected native manifest differs"):
            self.stage_c()
        self.assertEqual((self.prefix / trusted.RECORD).read_bytes(), before)
        self.assertEqual(sorted(path.name for path in (self.prefix / "releases").iterdir()), releases)

    def test_corrupt_historical_bytes_block_rollback_and_preserve_current_generation(self):
        self.stage_c()
        before = (self.prefix / trusted.RECORD).read_bytes()
        names = ("resources/makepad_widgets/resources/item-0", "resources/dependency-notices/makepad/native-clipboard-read.patch",
                 "source-profile.json", "resources/NATIVE-SDK-SOURCE.json", "resources/bundle.json")
        for name in names:
            with self.subTest(file=name):
                path = self.installed_b / name
                original = path.read_bytes()
                try:
                    path.write_bytes(original + b" ")
                    with self.assertRaises((desktop.ProductError, ValueError)):
                        trusted.rollback(self.prefix)
                    self.assertEqual((self.prefix / trusted.RECORD).read_bytes(), before)
                finally:
                    path.write_bytes(original)

    def test_extra_file_and_symlink_are_not_valid_historical_inventory(self):
        extra = self.installed_b / "unlisted.py"
        extra.write_text("raise RuntimeError('must not run')\n")
        with self.assertRaisesRegex(desktop.ProductError, "Unexpected or missing historical package file"):
            trusted.binding(self.prefix, trusted.read_record(self.prefix))
        extra.unlink()
        extra.symlink_to(self.installed_b / "source-profile.json")
        with self.assertRaisesRegex(desktop.ProductError, "Historical package contains a symlink"):
            trusted.binding(self.prefix, trusted.read_record(self.prefix))

    def test_original_deployment_lock_still_blocks_cross_version_upgrade_and_rollback(self):
        before = (self.prefix / trusted.RECORD).read_bytes()
        with trusted.deployment_lock(self.prefix):
            with self.assertRaisesRegex(desktop.ProductError, "Root is active"):
                self.stage_c()
        self.assertEqual((self.prefix / trusted.RECORD).read_bytes(), before)
        self.stage_c()
        before = (self.prefix / trusted.RECORD).read_bytes()
        with trusted.deployment_lock(self.prefix):
            with self.assertRaisesRegex(desktop.ProductError, "Root is active"):
                trusted.rollback(self.prefix)
        self.assertEqual((self.prefix / trusted.RECORD).read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
