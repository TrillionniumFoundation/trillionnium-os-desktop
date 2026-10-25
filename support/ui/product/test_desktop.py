"""Real filesystem/package transactions; ELF fixtures are not Rust UI tests."""
import copy
import io
import json
import os
import struct
import types
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

import desktop


class ProductTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="trill-product-test-")
        self.root = Path(self.temp.name)
        self.prefix = self.root / "installed"
        self.paths = {"bin_dir": str(self.root / "bin"), "unit_dir": str(self.root / "units"),
                      "applications_dir": str(self.root / "applications"),
                      "config": str(self.root / "config/config.json"),
                      "unit_name": "trillionnium-desktop-product-test-session.service"}
        self.package = self.make_package("a" * 40, b"first build")

    def tearDown(self):
        self.temp.cleanup()

    def make_archive(self, commit, extra=b"", member=None, sdk_profile_sha=None):
        archive = self.root / (commit[:12] + desktop.digest(extra)[:8] + ".tar.gz")
        binaries = {name: b"\x7fELFstructural fixture only" + name.encode() + extra for name in desktop.PROGRAMS}
        files = dict(binaries)
        files["PROVENANCE.txt"] = f"Source commit: {commit}\n".encode()
        if sdk_profile_sha:
            files["PROVENANCE.txt"] += f"Makepad source profile SHA256: {sdk_profile_sha}\n".encode()
        files["SHA256SUMS"] = "".join(desktop.digest(value) + "  " + key + "\n" for key, value in binaries.items()).encode()
        with tarfile.open(archive, "w:gz") as tar:
            root = tarfile.TarInfo("a10-linux-host-binaries")
            root.type = tarfile.DIRTYPE
            tar.addfile(root)
            for name, data in files.items():
                info = tarfile.TarInfo("a10-linux-host-binaries/" + name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
            if member:
                tar.addfile(member)
        return archive

    def make_package(self, commit, extra):
        archive = self.make_archive(commit, extra)
        profile = self.root / "profile.json"
        profile.write_bytes(desktop.json_bytes({"hepta": {"commit": "b" * 40},
                                               "production": {"activation": "disabled"}}))
        output = self.root / (commit[:12] + desktop.digest(extra)[:8] + "-product.tar.gz")
        desktop.pack(archive, commit, profile, output)
        extract = self.root / output.stem
        extract.mkdir()
        with tarfile.open(output) as tar:
            tar.extractall(extract, filter="data")
        return extract / "trillionnium-desktop"

    def install(self, package=None):
        return desktop.install(package or self.package, self.prefix, self.paths, lambda _unit: None)

    def test_pack_receipt_binds_the_actual_distribution_elfs(self):
        output = self.root / "receipt-product.tar.gz"
        result = desktop.pack(self.make_archive("a" * 40, b"distribution bytes"),
                              "a" * 40, self.root / "profile.json", output)
        self.assertEqual(set(result["binaries"]), set(desktop.PROGRAMS))
        with tarfile.open(output) as archive:
            for name, record in result["binaries"].items():
                data = archive.extractfile("trillionnium-desktop/bin/" + name).read()
                self.assertEqual(record, {"sha256": desktop.digest(data), "bytes": len(data)})

    def resource_fixture(self):
        resources = self.root / "resources"
        resources.mkdir()
        def record(name, field):
            data = ("resource fixture " + name).encode()
            path = resources / name
            path.parent.mkdir(exist_ok=True, parents=True)
            path.write_bytes(data)
            return {field: name, "bytes": len(data), "sha256": desktop.digest(data)}
        assets = [record(f"makepad_widgets/resources/item-{index}", "logical") for index in range(29)]
        notices = [record(f"notices/item-{index}", "path") for index in range(15)]
        source = record("sources/source.tar.gz", "file")
        source["file"] = "source.tar.gz"
        sdk = "337566c8b25d47f7e4fff6a202157b65bf183330"
        inventory = {"schema": "hepta.native-embedded-assets.v1", "makepadRevision": sdk,
                     "assets": assets, "noticeFileSha256": notices, "liberationSource": source}
        data = desktop.json_bytes(inventory)
        (resources / "NATIVE-ASSETS.json").write_bytes(data)
        dependency_files = [record(name, "path") for name in sorted(desktop.ACCESSKIT_NOTICES)]
        dependencies = {"schema": "hepta.native-dependency-notices.v1",
                        "upstreamRevision": desktop.ACCESSKIT_REVISION,
                        "crates": desktop.ACCESSKIT_CRATES, "files": dependency_files}
        dependency_bytes = desktop.json_bytes(dependencies)
        (resources / "NATIVE-DEPENDENCIES.json").write_bytes(dependency_bytes)
        source_id = "git+fixture#" + "b" * 40
        (resources / "bundle.json").write_bytes(desktop.json_bytes({
            "schema": "trill.original-makepad-bundle.v1", "heptaSource": source_id,
            "makepadSource": "git+" + desktop.native_sdk.UPSTREAM + "?rev=" + sdk + "#" + sdk,
            "assets": 29, "notices": 15,
            "inventorySha256": desktop.digest(data),
            "dependencyInventorySha256": desktop.digest(dependency_bytes), "dependencyNotices": 6,
            "accessibilitySources": {name: {"version": version, "source": source_id}
                                     for name, version in desktop.ACCESSKIT_CRATES.items()}}))
        return resources

    def test_complete_resource_bundle_is_bound_and_installed_with_relative_lookup(self):
        resources = self.resource_fixture()
        output = self.root / "with-resources.tar.gz"
        desktop.pack(self.make_archive("a" * 40, b"first build"), "a" * 40,
                     self.root / "profile.json", output, resources)
        extract = self.root / "with-resources"
        extract.mkdir()
        with tarfile.open(output) as archive:
            archive.extractall(extract, filter="data")
        self.install(extract / "trillionnium-desktop")
        release = desktop.current_release(self.prefix)
        self.assertEqual(len(desktop.native_resource_files(release / "resources")), 54)
        for name in desktop.ACCESSKIT_NOTICES:
            self.assertEqual((release / "resources" / name).read_bytes(), (resources / name).read_bytes())
        runtime = self.root / "runtime"
        runtime.mkdir(mode=0o700)
        cfg = desktop.default_config()
        cfg["renderer"] = "makepad"
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(runtime), "XDG_STATE_HOME": str(self.root / "state")}):
            env = desktop.runtime_environment(cfg, release=release)
        self.assertEqual(env["TRILL_UI_MAKEPAD_RESOURCES"], str(release / "resources"))
        (release / "resources/makepad_widgets/resources/item-0").write_bytes(b"corrupt")
        with self.assertRaisesRegex(desktop.ProductError, "resource bytes mismatch"):
            desktop.verify_package(release)

    def test_corrupt_dependency_license_is_refused_before_packaging(self):
        resources = self.resource_fixture()
        (resources / "dependency-notices/accesskit/LICENSE-MIT").write_bytes(b"changed license")
        output = self.root / "bad-license.tar.gz"
        with self.assertRaisesRegex(desktop.ProductError, "resource bytes mismatch"):
            desktop.pack(self.make_archive("a" * 40, b"first build"), "a" * 40,
                         self.root / "profile.json", output, resources)
        self.assertFalse(output.exists())

    def patched_resource_fixture(self):
        # These structural file fixtures deliberately replace only the reviewed
        # fixed byte hashes under test scope. They are never SDK build evidence.
        resources = self.resource_fixture()
        files = []
        for name in sorted(desktop.native_sdk.NOTICE_NAMES):
            data = ("synthetic SDK notice " + name).encode()
            relative = "dependency-notices/makepad/" + name
            path = resources / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            files.append({"path": relative, "bytes": len(data), "sha256": desktop.digest(data)})
        by_name = {entry["path"].rsplit("/", 1)[-1]: entry for entry in files}
        patches = [{"file": patch["file"], "bytes": by_name[patch["file"]]["bytes"],
                    "sha256": by_name[patch["file"]]["sha256"]} for patch in desktop.native_sdk.PATCHES]
        scoped = patch.multiple(desktop.native_sdk, MANIFEST_SHA256=by_name["MANIFEST.json"]["sha256"],
                                LICENSE_SHA256=by_name["LICENSE-MIT"]["sha256"], PATCHES=patches)
        scoped.start()
        self.addCleanup(scoped.stop)
        sdk = desktop.native_sdk
        profile = {"schema": "hepta.verified-original-sdk-source.v1", "native_ui_feature": "native-clipboard-sdk",
                   "upstream_repository": sdk.UPSTREAM,
                   "upstream_commit": sdk.REVISION, "patched_tree": sdk.TREE,
                   "manifest_sha256": sdk.MANIFEST_SHA256, "patches": patches,
                   "prepared_root": "/synthetic/source", "source_tree_verified": True,
                   "all_sdk_packages_same_tree": True, "dependency_edges_verified": True,
                   "effects_authority": False, "compiled": False, "runtime_qualified": False,
                   "original_metadata_sha256": "1" * 64, "candidate_metadata_sha256": "2" * 64,
                   "cargo_config_sha256": "3" * 64,
                   "resolved_packages": [{"name": name, "version": "2.0.0", "manifest": manifest}
                                         for name, manifest in sdk.REQUIRED.items()]
                       + [{"name": "unicode-segmentation", "version": "1.12.0", "manifest": "libs/unicode/Cargo.toml"}]}
        notices = {"schema": "hepta.native-sdk-notices.v1", "upstreamRepository": sdk.UPSTREAM,
                   "upstreamRevision": sdk.REVISION, "patchedTree": sdk.TREE,
                   "sourceManifestSha256": sdk.MANIFEST_SHA256, "files": files}
        notice_bytes = desktop.json_bytes(notices)
        profile_bytes = desktop.json_bytes(profile)
        (resources / "NATIVE-SDK-PATCH.json").write_bytes(notice_bytes)
        (resources / "NATIVE-SDK-SOURCE.json").write_bytes(profile_bytes)
        bundle = desktop.read_json(resources / "bundle.json")
        bundle.update(makepadSource=sdk.SOURCE_ID, sdkNotices=len(sdk.NOTICE_NAMES),
                      sdkNoticeInventorySha256=desktop.digest(notice_bytes),
                      sdkSourceProfileSha256=desktop.digest(profile_bytes))
        (resources / "bundle.json").write_bytes(desktop.json_bytes(bundle))
        binary_profile = desktop.read_json(self.root / "profile.json")
        binary_profile["makepad_sdk"] = profile
        (self.root / "profile.json").write_bytes(desktop.json_bytes(binary_profile))
        return resources, profile

    def test_prepared_sdk_sources_and_patch_notices_are_bound_to_binary_profile(self):
        resources, profile = self.patched_resource_fixture()
        self.assertEqual(len(desktop.native_resource_files(resources, "b" * 40, profile)), 61)
        profile_hash = desktop.digest((resources / "NATIVE-SDK-SOURCE.json").read_bytes())
        archive = self.make_archive("a" * 40, b"SDK structural fixture", sdk_profile_sha=profile_hash)
        output = self.root / "sdk-product.tar.gz"
        desktop.pack(archive, "a" * 40, self.root / "profile.json", output, resources)
        extracted = self.root / "sdk-product"
        extracted.mkdir()
        with tarfile.open(output) as packed:
            packed.extractall(extracted, filter="data")
        release = extracted / "trillionnium-desktop"
        desktop.verify_package(release)
        for name in desktop.native_sdk.NOTICE_PATHS:
            self.assertEqual((release / "resources" / name).read_bytes(), (resources / name).read_bytes())

    def test_unknown_path_source_is_not_an_original_sdk(self):
        resources = self.resource_fixture()
        bundle = desktop.read_json(resources / "bundle.json")
        bundle["makepadSource"] = "path+/unverified#" + desktop.native_sdk.REVISION
        (resources / "bundle.json").write_bytes(desktop.json_bytes(bundle))
        with self.assertRaisesRegex(desktop.ProductError, "Unpinned"):
            desktop.native_resource_files(resources)

    def test_sdk_resource_profile_must_match_the_binary_profile(self):
        resources, profile = self.patched_resource_fixture()
        changed = copy.deepcopy(profile)
        changed["candidate_metadata_sha256"] = "4" * 64
        with self.assertRaisesRegex(desktop.ProductError, "differs from the binary source profile"):
            desktop.native_resource_files(resources, "b" * 40, changed)
        with self.assertRaisesRegex(desktop.ProductError, "differs from the binary source profile"):
            desktop.native_resource_files(resources, "b" * 40)

    def test_sdk_candidate_requires_binary_archive_source_provenance(self):
        resources, _profile = self.patched_resource_fixture()
        output = self.root / "unbound-sdk.tar.gz"
        with self.assertRaisesRegex(desktop.ProductError, "lacks SDK source provenance"):
            desktop.pack(self.make_archive("a" * 40, b"no SDK proof"), "a" * 40,
                         self.root / "profile.json", output, resources)
        self.assertFalse(output.exists())

    def test_sdk_partial_or_changed_source_graph_is_refused(self):
        resources, profile = self.patched_resource_fixture()
        for field, replacement in (("patched_tree", "0" * 40), ("all_sdk_packages_same_tree", False),
                                   ("native_ui_feature", "native-presentation"),
                                   ("resolved_packages", profile["resolved_packages"][:-1])):
            changed = copy.deepcopy(profile)
            changed[field] = replacement
            raw = desktop.json_bytes(changed)
            (resources / "NATIVE-SDK-SOURCE.json").write_bytes(raw)
            bundle = desktop.read_json(resources / "bundle.json")
            bundle["sdkSourceProfileSha256"] = desktop.digest(raw)
            (resources / "bundle.json").write_bytes(desktop.json_bytes(bundle))
            with self.assertRaises(desktop.ProductError):
                desktop.native_resource_files(resources)

    def test_modified_sdk_patches_are_refused_even_with_a_valid_source_profile(self):
        resources, profile = self.patched_resource_fixture()
        for patch_record in desktop.native_sdk.PATCHES:
            with self.subTest(patch=patch_record["file"]):
                path = resources / "dependency-notices/makepad" / patch_record["file"]
                original = path.read_bytes()
                try:
                    path.write_bytes(b"changed")
                    with self.assertRaisesRegex(desktop.ProductError, "resource bytes mismatch"):
                        desktop.native_resource_files(resources, "b" * 40, profile)
                finally:
                    path.write_bytes(original)

    def test_second_sdk_patch_cannot_be_redeclared_by_a_self_consistent_notice(self):
        resources, profile = self.patched_resource_fixture()
        path = "dependency-notices/makepad/sdk-num-traits-path.patch"
        changed = b"different source change with a self-consistent inventory"
        (resources / path).write_bytes(changed)
        notices = desktop.read_json(resources / "NATIVE-SDK-PATCH.json")
        entry = next(entry for entry in notices["files"] if entry["path"] == path)
        entry.update(bytes=len(changed), sha256=desktop.digest(changed))
        raw = desktop.json_bytes(notices)
        (resources / "NATIVE-SDK-PATCH.json").write_bytes(raw)
        bundle = desktop.read_json(resources / "bundle.json")
        bundle["sdkNoticeInventorySha256"] = desktop.digest(raw)
        (resources / "bundle.json").write_bytes(desktop.json_bytes(bundle))
        with self.assertRaisesRegex(desktop.ProductError, "Original SDK license or patch identity differs"):
            desktop.native_resource_files(resources, "b" * 40, profile)

    def test_sdk_closure_patch_is_required_in_the_complete_notice_set(self):
        resources, profile = self.patched_resource_fixture()
        notices = desktop.read_json(resources / "NATIVE-SDK-PATCH.json")
        notices["files"] = [entry for entry in notices["files"]
                            if entry["path"] != "dependency-notices/makepad/sdk-num-traits-path.patch"]
        raw = desktop.json_bytes(notices)
        (resources / "NATIVE-SDK-PATCH.json").write_bytes(raw)
        bundle = desktop.read_json(resources / "bundle.json")
        bundle.update(sdkNotices=len(notices["files"]), sdkNoticeInventorySha256=desktop.digest(raw))
        (resources / "bundle.json").write_bytes(desktop.json_bytes(bundle))
        with self.assertRaisesRegex(desktop.ProductError, "Incomplete SDK source and patch notices"):
            desktop.native_resource_files(resources, "b" * 40, profile)

    def test_old_clipboard_only_sdk_profile_is_not_the_reviewed_closure_profile(self):
        _resources, profile = self.patched_resource_fixture()
        old = copy.deepcopy(profile)
        old.update(patched_tree="f9efec87ff9d5690b8c9fd23ea0c8f3535a9d8eb",
                   manifest_sha256="a7f36936a4101d85df78b30a7776ee85388fd004b7b8fccd0d1d3a460d859b3a",
                   patches=[{"file": "native-clipboard-read.patch", "bytes": 19919,
                             "sha256": "0edf1c0f806fec15ce29f03670e722d3eda4ec3943911537874087e8a8d4fa1f"}])
        with self.assertRaisesRegex(ValueError, "Unknown original SDK source or patch profile"):
            desktop.native_sdk.validate_profile(old)

    def test_sdk_notice_path_escape_is_rejected_before_open(self):
        resources, _profile = self.patched_resource_fixture()
        notices = desktop.read_json(resources / "NATIVE-SDK-PATCH.json")
        notices["files"][0]["path"] = "../outside"
        raw = desktop.json_bytes(notices)
        (resources / "NATIVE-SDK-PATCH.json").write_bytes(raw)
        bundle = desktop.read_json(resources / "bundle.json")
        bundle["sdkNoticeInventorySha256"] = desktop.digest(raw)
        (resources / "bundle.json").write_bytes(desktop.json_bytes(bundle))
        with self.assertRaisesRegex(desktop.ProductError, "Incomplete SDK"):
            desktop.native_resource_files(resources)

    def test_mixed_accessibility_source_is_refused(self):
        resources = self.resource_fixture()
        path = resources / "bundle.json"
        bundle = desktop.read_json(path)
        bundle["accessibilitySources"]["accesskit_unix"]["source"] = "git+fixture#" + "c" * 40
        path.write_bytes(desktop.json_bytes(bundle))
        with self.assertRaisesRegex(desktop.ProductError, "same original Hepta source"):
            desktop.native_resource_files(resources)

    def test_resource_source_must_match_binary_hepta_profile(self):
        resources = self.resource_fixture()
        with self.assertRaisesRegex(desktop.ProductError, "differs from the binary source profile"):
            desktop.native_resource_files(resources, "c" * 40)

    def test_changed_dependency_inventory_bytes_are_refused(self):
        resources = self.resource_fixture()
        path = resources / "NATIVE-DEPENDENCIES.json"
        path.write_bytes(path.read_bytes() + b"\n")
        with self.assertRaisesRegex(desktop.ProductError, "dependency inventory identity mismatch"):
            desktop.native_resource_files(resources)

    def test_dependency_notice_path_cannot_escape_or_replace_an_asset(self):
        resources = self.resource_fixture()
        path = resources / "NATIVE-DEPENDENCIES.json"
        dependencies = desktop.read_json(path)
        dependencies["files"][0]["path"] = "dependency-notices/accesskit/../../outside"
        data = desktop.json_bytes(dependencies)
        path.write_bytes(data)
        bundle = desktop.read_json(resources / "bundle.json")
        bundle["dependencyInventorySha256"] = desktop.digest(data)
        (resources / "bundle.json").write_bytes(desktop.json_bytes(bundle))
        with self.assertRaisesRegex(desktop.ProductError, "notice paths"):
            desktop.native_resource_files(resources)

    def test_same_uid_unrelated_session_pid_cannot_be_reported_ready(self):
        result = types.SimpleNamespace(stdout="101\n")
        with patch.object(desktop, "systemctl", return_value=result), patch.object(desktop.socket, "socket") as socket_factory:
            peer = socket_factory.return_value.__enter__.return_value
            peer.getsockopt.return_value = struct.pack("3i", 202, os.geteuid(), os.getegid())
            with self.assertRaisesRegex(desktop.ProductError, "not owned"):
                desktop.require_owned_session({"XDG_RUNTIME_DIR": str(self.root)}, desktop.UNIT)

    def test_unix_socket_boundary_is_measured_in_filesystem_bytes(self):
        padding = 107 - len(os.fsencode(self.root)) - 1
        endpoint = self.root / ("x" * padding)
        self.assertEqual(desktop.unix_socket_path(endpoint, "Test socket"), str(endpoint))
        with desktop.socket.socket(desktop.socket.AF_UNIX) as listener:
            listener.bind(str(endpoint))
        with self.assertRaisesRegex(desktop.ProductError, "108 bytes.*at most 107 bytes"):
            desktop.unix_socket_path(str(endpoint) + "x", "Test socket")
        with self.assertRaisesRegex(desktop.ProductError, "109 bytes.*at most 107 bytes"):
            desktop.unix_socket_path("/" + "界" * 36, "Test socket")

    def test_long_runtime_is_rejected_before_session_socket_connect(self):
        runtime = "/" + "r" * 95
        inactive = types.SimpleNamespace(returncode=0, stdout="inactive\n")
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": runtime}), \
                patch.object(desktop, "systemctl", return_value=inactive), \
                patch.object(desktop.socket, "socket") as socket_factory:
            with self.assertRaisesRegex(desktop.ProductError, "Session socket from XDG_RUNTIME_DIR.*at most 107 bytes"):
                desktop.require_stopped()
            socket_factory.assert_not_called()

    def test_configured_chat_and_observer_paths_get_clear_length_errors(self):
        path = self.root / "socket-config.json"
        for field, value, label in (
                ("chat", {"socket": "/" + "s" * 107, "root_pid": 123}, "Chat socket"),
                ("observer", {"socket": "/" + "s" * 107,
                              "agent_id": "00000000-0000-0000-0000-000000000001",
                              "spawn_generation": 1, "peer_uid": os.geteuid(), "run_id": None}, "Observer socket")):
            with self.subTest(field=field):
                cfg = desktop.default_config()
                cfg[field] = value
                desktop.atomic_write(path, desktop.json_bytes(cfg))
                with self.assertRaisesRegex(desktop.ProductError, label + ".*108 bytes.*at most 107 bytes"):
                    desktop.load_config(path)

    def test_inherited_chat_socket_limit_is_checked_before_creating_state(self):
        runtime = self.root / "runtime"
        runtime.mkdir(mode=0o700)
        state = self.root / "unused-state"
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(runtime), "XDG_STATE_HOME": str(state),
                                     "TRILL_UI_CHAT_SOCKET": "/" + "s" * 107, "TRILL_UI_CHAT_ROOT_PID": "123"}):
            with self.assertRaisesRegex(desktop.ProductError, "Chat socket.*at most 107 bytes"):
                desktop.runtime_environment(desktop.default_config())
        self.assertFalse(state.exists())

    def test_control_characters_cannot_inject_unit_directives(self):
        paths = dict(self.paths, bin_dir=str(self.root / "bad\nExecStart=unexpected"))
        with self.assertRaisesRegex(desktop.ProductError, "control characters"):
            desktop.install(self.package, self.prefix, paths, lambda _unit: None)
        self.assertFalse((Path(self.paths["unit_dir"]) / self.paths["unit_name"]).exists())

    def test_source_pair_and_inner_binary_digests_are_bound(self):
        value = desktop.verify_package(self.package)
        self.assertEqual(value["desktop_commit"], "a" * 40)
        self.assertEqual(value["hepta_commit"], "b" * 40)
        self.assertIs(value["effects_authorized"], False)
        binary = self.package / "bin/trill-session"
        binary.write_bytes(binary.read_bytes() + b"corruption")
        with self.assertRaisesRegex(desktop.ProductError, "checksum mismatch"):
            self.install()
        self.assertFalse(self.prefix.exists())

    def test_wrong_source_commit_refuses_package(self):
        archive = self.make_archive("c" * 40)
        with self.assertRaisesRegex(desktop.ProductError, "provenance mismatch"):
            desktop.pack(archive, "d" * 40, self.root / "profile.json", self.root / "wrong.tar.gz")
        self.assertFalse((self.root / "wrong.tar.gz").exists())

    def test_archive_symlink_and_traversal_are_refused(self):
        for name, kind in (("../escape", tarfile.REGTYPE),
                           ("a10-linux-host-binaries/alias", tarfile.SYMTYPE)):
            bad = tarfile.TarInfo(name)
            bad.type = kind
            bad.linkname = "/tmp/unrelated"
            archive = self.make_archive("e" * 40, name.encode(), bad)
            with self.assertRaisesRegex(desktop.ProductError, "Unsafe or unexpected"):
                desktop.pack(archive, "e" * 40, self.root / "profile.json", self.root / "bad.tar.gz")
        self.assertFalse((self.root.parent / "escape").exists())

    def test_install_keeps_code_and_user_state_separate(self):
        data = self.root / "user-state/local-context-drafts-v2.json"
        data.parent.mkdir()
        data.write_text('用户草稿')
        result = self.install()
        record, release, _manifest, cfg = desktop.installed(self.prefix)
        self.assertEqual(release.name, result["installed_release"])
        self.assertTrue((Path(self.paths["unit_dir"]) / self.paths["unit_name"]).is_file())
        self.assertIn("KillMode=control-group", (Path(self.paths["unit_dir"]) / self.paths["unit_name"]).read_text())
        self.assertEqual(Path(record["paths"]["config"]).stat().st_mode & 0o777, 0o600)
        self.assertTrue(cfg["draft_recovery"])
        self.assertEqual(data.read_text(), '用户草稿')

    def test_upgrade_and_rollback_preserve_configuration_and_drafts(self):
        self.install()
        initial = desktop.current_release(self.prefix).name
        config = Path(self.paths["config"])
        cfg = desktop.read_json(config)
        cfg["notes_state_dir"] = str(self.root / "saved-notes")
        config.write_bytes(desktop.json_bytes(cfg))
        original = config.read_bytes()
        second = self.make_package("c" * 40, b"second")
        result = self.install(second)
        self.assertEqual(result["previous_release"], initial)
        self.assertNotEqual(desktop.current_release(self.prefix).name, initial)
        self.assertEqual(config.read_bytes(), original)
        desktop.rollback(self.prefix, lambda _unit: None)
        self.assertEqual(desktop.current_release(self.prefix).name, initial)
        self.assertEqual(config.read_bytes(), original)

    def test_same_commit_different_binary_build_gets_distinct_release(self):
        second = self.make_package("a" * 40, b"different build")
        self.assertNotEqual(desktop.verify_package(second)["release_id"],
                            desktop.verify_package(self.package)["release_id"])

    def test_same_binaries_changed_profile_gets_distinct_release(self):
        archive = self.make_archive("a" * 40, b"first build")
        profile = self.root / "profile.json"
        value = desktop.read_json(profile)
        value["release_note"] = "different source-profile evidence"
        profile.write_bytes(desktop.json_bytes(value))
        output = self.root / "profile-update.tar.gz"
        result = desktop.pack(archive, "a" * 40, profile, output)
        self.assertNotEqual(result["release_id"], desktop.verify_package(self.package)["release_id"])

    def test_active_session_prevents_upgrade_before_mutation(self):
        self.install()
        previous = os.readlink(self.prefix / "current")
        record = (self.prefix / "installation.json").read_bytes()
        def active(_unit):
            raise desktop.ProductError("Session is active")
        second = self.make_package("c" * 40, b"second")
        with self.assertRaisesRegex(desktop.ProductError, "active"):
            desktop.install(second, self.prefix, self.paths, active)
        self.assertEqual(os.readlink(self.prefix / "current"), previous)
        self.assertEqual((self.prefix / "installation.json").read_bytes(), record)

    def test_unmanaged_launcher_is_not_replaced(self):
        path = Path(self.paths["bin_dir"]) / "trillionnium-desktop"
        path.parent.mkdir()
        path.write_text("unrelated launcher")
        with self.assertRaisesRegex(desktop.ProductError, "unmanaged"):
            self.install()
        self.assertEqual(path.read_text(), "unrelated launcher")
        self.assertIsNone(desktop.current_release(self.prefix))

    def test_corrupt_new_release_does_not_replace_previous(self):
        self.install()
        previous = os.readlink(self.prefix / "current")
        second = self.make_package("c" * 40, b"second")
        (second / "bin/trill-shell").write_bytes(b"broken")
        with self.assertRaises(desktop.ProductError):
            self.install(second)
        self.assertEqual(os.readlink(self.prefix / "current"), previous)

    def test_uninstall_preserves_modified_integration_and_user_config(self):
        self.install()
        path = Path(self.paths["unit_dir"]) / self.paths["unit_name"]
        path.write_text(path.read_text() + "# user change\n")
        with self.assertRaisesRegex(desktop.ProductError, "Modified integration"):
            desktop.uninstall(self.prefix, lambda _unit: None)
        self.assertIn("# user change", path.read_text())
        self.assertTrue(Path(self.paths["config"]).is_file())
        self.assertIsNotNone(desktop.current_release(self.prefix))

    def test_clean_uninstall_retains_user_data_and_config(self):
        self.install()
        config = Path(self.paths["config"])
        original = config.read_bytes()
        result = desktop.uninstall(self.prefix, lambda _unit: None)
        self.assertTrue(result["uninstalled"])
        self.assertEqual(config.read_bytes(), original)
        self.assertFalse((Path(self.paths["bin_dir"]) / "trillionnium-desktop").exists())
        self.assertFalse((self.prefix / "releases").exists())
        self.assertTrue((self.prefix / ".install.lock").is_file())

    def test_symlink_package_input_is_refused(self):
        target = self.package / "bin/trill-session"
        target.unlink()
        target.symlink_to(self.package / "bin/trill-shell")
        with self.assertRaises(OSError):
            desktop.verify_package(self.package)

    def test_unknown_config_and_partial_observer_are_rejected(self):
        self.install()
        config = Path(self.paths["config"])
        original = desktop.default_config()
        for change in ({"extra": True}, {"observer": {"socket": "/tmp/agent.sock"}},
                       {"chat": {"socket": "/tmp/chat.sock"}},
                       {"chat": {"socket": "/tmp/chat.sock", "root_pid": True}},
                       {"chat": {"socket": "relative", "root_pid": 123}},
                       {"notes_state_dir": "relative"}, {"draft_recovery": "true"}):
            cfg = copy.deepcopy(original)
            cfg.update(change)
            config.write_bytes(desktop.json_bytes(cfg))
            with self.assertRaises(desktop.ProductError):
                desktop.load_config(config)

    def test_existing_config_remains_unchanged_when_optional_chat_is_added(self):
        self.install()
        config = Path(self.paths["config"])
        legacy = desktop.default_config()
        legacy.pop("chat")
        original = desktop.json_bytes(legacy)
        config.write_bytes(original)
        self.assertIsNone(desktop.load_config(config)["chat"])
        self.assertEqual(config.read_bytes(), original)

    def test_chat_lane_pair_is_preserved_or_explicitly_overridden_without_authority(self):
        runtime = self.root / "runtime"
        runtime.mkdir(mode=0o700)
        environment = {"XDG_RUNTIME_DIR": str(runtime), "XDG_STATE_HOME": str(self.root / "state"),
                       "TRILL_UI_CHAT_SOCKET": "/run/hepta/registered-ui.sock", "TRILL_UI_CHAT_ROOT_PID": "41"}
        with patch.dict(os.environ, environment, clear=True):
            env = desktop.runtime_environment(desktop.default_config(), prepare_state=False)
            self.assertEqual(env["TRILL_UI_CHAT_ROOT_PID"], "41")
            self.assertEqual(env["TRILL_UI_CHAT_SOCKET"], environment["TRILL_UI_CHAT_SOCKET"])
            os.environ.pop("TRILL_UI_CHAT_ROOT_PID")
            with self.assertRaisesRegex(desktop.ProductError, "both TRILL_UI_CHAT"):
                desktop.runtime_environment(desktop.default_config(), prepare_state=False)
            cfg = desktop.default_config()
            cfg["chat"] = {"socket": "/run/hepta/explicit-ui.sock", "root_pid": 42}
            env = desktop.runtime_environment(cfg, prepare_state=False)
            self.assertEqual(env["TRILL_UI_CHAT_SOCKET"], cfg["chat"]["socket"])
            self.assertEqual(env["TRILL_UI_CHAT_ROOT_PID"], "42")

    def test_unsafe_config_permissions_are_rejected(self):
        self.install()
        config = Path(self.paths["config"])
        config.chmod(0o644)
        with self.assertRaisesRegex(desktop.ProductError, "0600"):
            desktop.load_config(config)

    def test_wrong_current_symlink_cannot_select_arbitrary_directory(self):
        self.install()
        (self.prefix / "current").unlink()
        (self.prefix / "current").symlink_to("../../unrelated")
        with self.assertRaisesRegex(desktop.ProductError, "release target"):
            desktop.current_release(self.prefix)

    def test_runtime_environment_is_scoped_and_notes_path_is_stable(self):
        runtime = self.root / "runtime"
        runtime.mkdir(mode=0o700)
        state = self.root / "state"
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(runtime), "XDG_STATE_HOME": str(state),
                                     "TRILL_HEPTA_AGENT_ID": "unrequested"}):
            env = desktop.runtime_environment(desktop.default_config())
        self.assertNotIn("TRILL_HEPTA_AGENT_ID", env)
        self.assertEqual(env["TRILL_NOTES_STATE_DIR"], str(state / "trillionnium-ui/notes"))
        self.assertEqual(env["TRILL_UI_DRAFT_RECOVERY"], "1")
        self.assertEqual((state / "trillionnium-ui").stat().st_mode & 0o777, 0o700)
        self.assertFalse((state / "trillionnium-ui/notes").exists())

    def test_diagnostics_do_not_create_state_but_launch_refuses_shared_parent(self):
        runtime = self.root / "runtime"
        runtime.mkdir(mode=0o700)
        state = self.root / "state"
        with patch.dict(os.environ, {"XDG_RUNTIME_DIR": str(runtime), "XDG_STATE_HOME": str(state)}):
            desktop.runtime_environment(desktop.default_config(), prepare_state=False)
            self.assertFalse(state.exists())
            (state / "trillionnium-ui").mkdir(parents=True, mode=0o755)
            with self.assertRaisesRegex(desktop.ProductError, "0700"):
                desktop.runtime_environment(desktop.default_config())
        self.assertEqual((state / "trillionnium-ui").stat().st_mode & 0o777, 0o755)

    def test_duplicate_json_keys_fail_under_optimized_python_too(self):
        path = self.root / "duplicate.json"
        path.write_text('{"renderer":"egui","renderer":"makepad"}')
        with self.assertRaisesRegex(desktop.ProductError, "Duplicate JSON"):
            desktop.read_json(path)

    def test_installation_cannot_manufacture_uninstall_path(self):
        self.install()
        record = desktop.read_json(self.prefix / "installation.json")
        unrelated = self.root / "private-file"
        unrelated.write_text("keep")
        record["integration_sha256"][str(unrelated)] = desktop.digest(b"keep")
        (self.prefix / "installation.json").write_bytes(desktop.json_bytes(record))
        with self.assertRaisesRegex(desktop.ProductError, "integration path"):
            desktop.uninstall(self.prefix, lambda _unit: None)
        self.assertEqual(unrelated.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
