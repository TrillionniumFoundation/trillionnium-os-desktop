"""Real temporary Git DAGs, not runtime/authority qualification tests."""

import copy
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "organ_release_profile", Path(__file__).with_name("organ_release_profile.py"))
profile = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(profile)


def git(repo, *args, input_bytes=None):
    return subprocess.run(["git", "-C", str(repo), *args], input=input_bytes,
                          check=True, capture_output=True).stdout.strip().decode()


def write(repo, path, content):
    file = repo / path
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_bytes(content)


def commit(repo, message):
    git(repo, "add", "--all")
    git(repo, "commit", "--quiet", "-m", message)
    return git(repo, "rev-parse", "HEAD")


class SourceCombinationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.os = self.root / "os"
        self.hepta = self.root / "hepta"
        self.mapping = {
            "schema_version": 1,
            "sources": {
                "os": {role: f"os/{role}.rs" for role in profile.OS_ROLES},
                "hepta": {role: f"hepta/{role}.rs" for role in profile.HEPTA_ROLES},
            },
            "goldens": {role: {"os": f"goldens/{role}.json", "hepta": f"goldens/{role}.json"}
                        for role in profile.GOLDEN_ROLES},
        }
        for name, repo in (("os", self.os), ("hepta", self.hepta)):
            repo.mkdir()
            git(repo, "init", "--quiet")
            git(repo, "config", "user.name", "Source fixture")
            git(repo, "config", "user.email", "source-fixture@example.invalid")
            git(repo, "config", "commit.gpgsign", "false")
            for role, path in self.mapping["sources"][name].items():
                write(repo, path, (role + " source\n").encode())
            for role, paths in self.mapping["goldens"].items():
                write(repo, paths[name], ('{"fixture": "' + role + '"}\n').encode())
            commit(repo, "owner sources and original goldens")
        owner = git(self.hepta, "rev-parse", "HEAD")
        # Only tests replace the original owner constant; the CLI has no override.
        self.owner_patch = patch.object(profile, "HISTORY_OWNER", owner)
        self.owner_patch.start()
        self.addCleanup(self.owner_patch.stop)
        write(self.hepta, "later-source.txt", b"later release\n")
        commit(self.hepta, "release descendant")

    def inputs(self, hepta=None):
        hepta = hepta or self.hepta
        return (profile.Repository(self.os, "os"), profile.Repository(hepta, "hepta"),
                git(self.os, "rev-parse", "HEAD"), git(self.os, "rev-parse", "HEAD^{tree}"),
                git(hepta, "rev-parse", "HEAD"), git(hepta, "rev-parse", "HEAD^{tree}"), self.mapping)

    def build(self, hepta=None):
        return profile.create_manifest(*self.inputs(hepta))

    def upgrade_to_v2(self):
        SourceCombinationTests.upgrade_to_version(self, 2)

    def upgrade_to_version(self, version):
        self.mapping["schema_version"] = version
        os_roles, hepta_roles, golden_roles = profile.roles_for_version(version)
        for name, roles in (("os", os_roles), ("hepta", hepta_roles)):
            for role in roles - set(self.mapping["sources"][name]):
                path = f"{name}/{role}.rs"
                self.mapping["sources"][name][role] = path
                write(getattr(self, name), path, (role + " source\n").encode())
        for role in golden_roles - set(self.mapping["goldens"]):
            paths = {name: f"goldens/{role}.json" for name in ("os", "hepta")}
            self.mapping["goldens"][role] = paths
            for name, path in paths.items():
                write(getattr(self, name), path, ('{"fixture":"' + role + '"}\n').encode())
        commit(self.os, "review expanded Desktop and kernel source roles")
        commit(self.hepta, "review original Root and native owner source roles")

    def verify(self, manifest):
        os_repo, hepta_repo, head, tree, _, _, mapping = self.inputs()
        return profile.verify_manifest(manifest, os_repo, hepta_repo, head, tree, mapping)

    def test_clean_pair_pins_one_hepta_and_proves_owner(self):
        manifest, receipt = self.build()
        self.assertEqual(receipt["source_checks"], "passed")
        self.assertEqual(manifest["hepta"]["commit"], git(self.hepta, "rev-parse", "HEAD"))
        self.assertEqual(manifest["production"]["activation"], "disabled")
        self.assertFalse(manifest["production"]["effects_authorized"])
        self.assertEqual(len(manifest["production"]["unconfigured"]), 7)
        self.assertEqual(self.verify(manifest)["os"], receipt["os"])

    def test_v2_pair_binds_new_lanes_and_preserves_disabled_authority(self):
        self.upgrade_to_v2()
        manifest, receipt = self.build()
        self.assertEqual(manifest["schema_version"], 2)
        self.assertEqual(receipt["schema_version"], 2)
        self.assertEqual({item["role"] for item in manifest["sources"]["hepta"]}, profile.HEPTA_ROLES_V2)
        self.assertEqual({item["role"] for item in manifest["goldens"]}, profile.GOLDEN_ROLES_V2)
        self.assertEqual(manifest["production"], profile.PRODUCTION)
        self.assertEqual(self.verify(manifest)["source_checks"], "passed")

    def test_v2_cannot_omit_root_writer_or_desktop_golden_or_downgrade(self):
        self.upgrade_to_v2()
        original = copy.deepcopy(self.mapping)
        for mutate in (
            lambda value: value["sources"]["hepta"].pop("root_writer"),
            lambda value: value["goldens"].pop("desktop_x11"),
            lambda value: value.update(schema_version=1),
        ):
            self.mapping = copy.deepcopy(original)
            mutate(self.mapping)
            with self.assertRaises(profile.ProfileError):
                self.build()

    def test_v2_desktop_wire_byte_drift_is_rejected(self):
        self.upgrade_to_v2()
        path = self.mapping["goldens"]["desktop_x11"]["hepta"]
        write(self.hepta, path, (self.hepta / path).read_bytes() + b" ")
        commit(self.hepta, "drift desktop golden")
        with self.assertRaisesRegex(profile.ProfileError, "golden byte mismatch: desktop_x11"):
            self.build()

    def test_noninteger_or_unknown_schema_is_rejected(self):
        for version in (True, 1.0, 2.0, 3.0, "2", None, 0, 4):
            self.mapping["schema_version"] = version
            with self.subTest(version=version), self.assertRaisesRegex(profile.ProfileError, "unsupported source map"):
                self.build()

    def test_v3_native_owner_pair_keeps_exact_full_roles_and_protocol_goldens(self):
        self.upgrade_to_version(3)
        manifest, receipt = self.build()
        self.assertEqual(manifest["schema_version"], 3)
        self.assertEqual(receipt["schema_version"], 3)
        for side, roles in (("os", profile.OS_ROLES_V3), ("hepta", profile.HEPTA_ROLES_V3)):
            self.assertEqual({entry["role"] for entry in manifest["sources"][side]}, roles)
        self.assertEqual({entry["role"] for entry in manifest["goldens"]}, profile.GOLDEN_ROLES_V2)
        self.assertEqual(self.verify(manifest)["source_checks"], "passed")
        self.assertEqual(manifest["production"], profile.PRODUCTION)

    def test_v3_cannot_omit_publishers_downgrade_or_alias_a_required_source(self):
        self.upgrade_to_version(3)
        original = copy.deepcopy(self.mapping)
        for mutate in (
            lambda value: value["sources"]["hepta"].pop("root_composition"),
            lambda value: value["sources"]["hepta"].pop("cognitive_current_publisher"),
            lambda value: value.update(schema_version=2),
            lambda value: value["sources"]["hepta"].update(
                cognitive_current_publisher=value["sources"]["hepta"]["root_composition"]),
        ):
            self.mapping = copy.deepcopy(original)
            mutate(self.mapping)
            with self.assertRaises(profile.ProfileError):
                self.build()

    def test_v3_ipc_owner_probe_and_oracle_cannot_be_omitted_or_aliased(self):
        self.upgrade_to_version(3)
        original = copy.deepcopy(self.mapping)
        for role in ("kernel_pipe_buffer_owner", "kernel_ipc_memory_probe",
                     "kernel_ipc_source_profile_oracle"):
            for mutation in ("omit", "alias"):
                self.mapping = copy.deepcopy(original)
                entries = self.mapping["sources"]["os"]
                if mutation == "omit":
                    entries.pop(role)
                else:
                    entries[role] = entries["kernel_page_budget"]
                with self.subTest(role=role, mutation=mutation), self.assertRaises(profile.ProfileError):
                    self.build()

    def test_v3_ipc_owner_byte_change_requires_a_new_manifest(self):
        self.upgrade_to_version(3)
        manifest, _ = self.build()
        path = self.mapping["sources"]["os"]["kernel_pipe_buffer_owner"]
        write(self.os, path, b"changed physical buffer admission\n")
        commit(self.os, "change IPC admission owner")
        with self.assertRaisesRegex(profile.ProfileError, "manifest mismatch"):
            self.verify(manifest)

    def test_wrong_os_head_rejected(self):
        args = list(self.inputs())
        args[2] = "0" * 40
        with self.assertRaisesRegex(profile.ProfileError, "HEAD mismatch"):
            profile.create_manifest(*args)

    def test_wrong_os_tree_rejected(self):
        args = list(self.inputs())
        args[3] = "0" * 40
        with self.assertRaisesRegex(profile.ProfileError, "tree mismatch"):
            profile.create_manifest(*args)

    def test_wrong_hepta_head_rejected(self):
        args = list(self.inputs())
        args[4] = profile.HISTORY_OWNER
        with self.assertRaisesRegex(profile.ProfileError, "HEAD mismatch"):
            profile.create_manifest(*args)

    def test_tracked_dirty_rejected(self):
        write(self.os, self.mapping["sources"]["os"]["notes_app"], b"changed\n")
        with self.assertRaisesRegex(profile.ProfileError, "dirty checkout"):
            self.build()

    def test_untracked_dirty_rejected(self):
        write(self.hepta, "unreviewed-source.rs", b"untracked\n")
        with self.assertRaisesRegex(profile.ProfileError, "dirty checkout"):
            self.build()

    def test_hidden_worktree_modification_rejected(self):
        path = self.mapping["sources"]["os"]["notes_app"]
        git(self.os, "update-index", "--assume-unchanged", path)
        write(self.os, path, b"hidden change\n")
        with self.assertRaisesRegex(profile.ProfileError, "prevent clean proof"):
            self.build()

    def test_committed_golden_byte_mismatch_rejected(self):
        path = self.mapping["goldens"]["notes_target"]["hepta"]
        write(self.hepta, path, (self.hepta / path).read_bytes() + b" ")
        commit(self.hepta, "semantically equal JSON but different golden bytes")
        with self.assertRaisesRegex(profile.ProfileError, "golden byte mismatch"):
            self.build()

    def test_committed_missing_golden_rejected(self):
        (self.os / self.mapping["goldens"]["notes_bootstrap"]["os"]).unlink()
        commit(self.os, "remove golden")
        with self.assertRaisesRegex(profile.ProfileError, "required regular source file missing"):
            self.build()

    def test_committed_missing_original_owner_source_rejected(self):
        (self.hepta / self.mapping["sources"]["hepta"]["durable_writer"]).unlink()
        commit(self.hepta, "remove owner")
        with self.assertRaisesRegex(profile.ProfileError, "required regular source file missing"):
            self.build()

    def test_missing_history_object_rejected(self):
        with patch.object(profile, "HISTORY_OWNER", "1" * 40):
            with self.assertRaisesRegex(profile.ProfileError, "owner object missing"):
                self.build()

    def test_present_nonancestor_rejected(self):
        tree = git(self.hepta, "rev-parse", "HEAD^{tree}")
        unrelated = git(self.hepta, "commit-tree", tree, "-m", "unrelated root")
        with patch.object(profile, "HISTORY_OWNER", unrelated):
            with self.assertRaisesRegex(profile.ProfileError, "ancestry unproven or nonancestor"):
                self.build()

    def test_shallow_unknown_ancestry_rejected_even_when_object_present(self):
        shallow = self.root / "shallow-unknown"
        git(self.root, "clone", "--quiet", "--depth", "1", self.hepta.as_uri(), str(shallow))
        raw = subprocess.run(["git", "-C", str(self.hepta), "cat-file", "commit", profile.HISTORY_OWNER],
                             capture_output=True, check=True).stdout
        git(shallow, "hash-object", "-w", "-t", "commit", "--stdin", input_bytes=raw)
        with self.assertRaisesRegex(profile.ProfileError, "ancestry unproven or nonancestor"):
            self.build(shallow)

    def test_shallow_proven_ancestry_allowed(self):
        shallow = self.root / "shallow-proven"
        git(self.root, "clone", "--quiet", "--depth", "2", self.hepta.as_uri(), str(shallow))
        _, receipt = self.build(shallow)
        self.assertTrue(receipt["original_history_proof"]["shallow_repository"])

    def test_source_change_under_new_os_pin_requires_new_manifest(self):
        manifest, _ = self.build()
        write(self.os, self.mapping["sources"]["os"]["notes_app"], b"new implementation\n")
        commit(self.os, "change reviewed source")
        with self.assertRaisesRegex(profile.ProfileError, "manifest mismatch"):
            self.verify(manifest)

    def test_manifest_can_be_committed_without_self_reference(self):
        manifest, before = self.build()
        write(self.os, "release-profile.json", profile.canonical(manifest))
        commit(self.os, "store reviewed source-only profile")
        after = self.verify(manifest)
        self.assertNotEqual(before["os"]["commit"], after["os"]["commit"])
        self.assertEqual(before["hepta"], after["hepta"])

    def test_string_configuration_cannot_enable_production(self):
        manifest, _ = self.build()
        edited = copy.deepcopy(manifest)
        edited["production"] = {"activation": "enabled", "effects_authorized": True,
                                "unconfigured": [], "provider": "production"}
        with self.assertRaisesRegex(profile.ProfileError, "manifest mismatch"):
            self.verify(edited)

    def test_unresolved_mapping_fails(self):
        self.mapping["sources"]["hepta"]["durable_writer"] = None
        with self.assertRaisesRegex(profile.ProfileError, "source map unresolved"):
            self.build()

    def test_no_output_inside_source_repositories(self):
        with self.assertRaisesRegex(profile.ProfileError, "outside both source repositories"):
            profile.write_new_outside(self.os / "new-profile.json", b"{}", self.inputs()[:2])

    def test_cli_receipt_hashes_the_same_manifest_bytes_it_verified(self):
        manifest, _ = self.build()
        raw = profile.canonical(manifest)
        path = self.root / "manifest.json"
        path.write_bytes(raw)
        mapping = self.root / "map.json"
        mapping.write_bytes(profile.canonical(self.mapping))
        receipt = self.root / "verified.json"
        verify = profile.verify_manifest

        def change_after_verification(*args):
            result = verify(*args)
            path.write_bytes(b'{"unverified":"replacement bytes"}\n')
            return result

        with patch.object(profile, "verify_manifest", side_effect=change_after_verification):
            result = profile.main([
                "verify", "--os-repo", str(self.os), "--hepta-repo", str(self.hepta),
                "--os-head", git(self.os, "rev-parse", "HEAD"),
                "--os-tree", git(self.os, "rev-parse", "HEAD^{tree}"),
                "--source-map", str(mapping), "--manifest", str(path),
                "--receipt", str(receipt),
            ])
        self.assertEqual(result, 0)
        self.assertEqual(profile.load_json(receipt)["manifest_sha256"], profile.sha256(raw))


class CheckedInSourceMapTests(unittest.TestCase):
    def test_v3_os_paths_are_distinct_tracked_regular_sources(self):
        release = Path(__file__).resolve().parent
        mapping = profile.load_json(release / "organ_source_map_v3.json")
        profile.check_map(mapping)
        repo = profile.Repository(release.parents[1], "os")
        for role, path in mapping["sources"]["os"].items():
            with self.subTest(role=role, path=path):
                repo.file(path)


if __name__ == "__main__":
    unittest.main()
