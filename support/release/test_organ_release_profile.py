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

    def test_shipped_mapping_includes_recovery_sources_and_golden(self):
        mapping = profile.load_json(Path(__file__).with_name("organ_source_map.json"))
        profile.check_map(mapping)
        self.assertEqual(mapping["sources"]["os"]["notes_recovery"], "ui/core/src/notes_recovery.rs")
        self.assertEqual(mapping["sources"]["os"]["notes_private_handoff"], "ui/core/src/notes_private_unix.rs")
        self.assertEqual(mapping["sources"]["hepta"]["notes_terminal_owner"],
                         "codex-rs/hepta-memory/src/production_notes_owner.rs")
        self.assertEqual(mapping["goldens"]["notes_bootstrap"]["os"], "tests/ui/notes-bootstrap-v2.json")
        self.assertEqual(mapping["goldens"]["notes_recovery"]["os"], "tests/ui/notes-recovery-v1.json")

    def test_recovery_roles_cannot_be_omitted(self):
        for repository, role in (("os", "notes_recovery"), ("os", "notes_private_handoff"),
                                 ("hepta", "notes_terminal_owner")):
            mapping = copy.deepcopy(self.mapping)
            del mapping["sources"][repository][role]
            with self.subTest(repository=repository, role=role), self.assertRaisesRegex(
                    profile.ProfileError, "source map requires exactly"):
                profile.check_map(mapping)
        mapping = copy.deepcopy(self.mapping)
        del mapping["goldens"]["notes_recovery"]
        with self.assertRaisesRegex(profile.ProfileError, "golden roles"):
            profile.check_map(mapping)

    def test_production_composition_sources_are_required_but_never_activate_trust(self):
        roles = {"production_composition": "production_composition.rs",
                 "grant_provider": "final_use_issuer.rs",
                 "grant_provider_worker": "grant_provider_worker.rs",
                 "protected_authority_inputs": "production_authority.rs"}
        shipped = profile.load_json(Path(__file__).with_name("organ_source_map.json"))
        for role, filename in roles.items():
            with self.subTest(role=role):
                self.assertEqual(shipped["sources"]["hepta"][role],
                                 "codex-rs/hepta-agentd/src/" + filename)
                missing = copy.deepcopy(self.mapping)
                del missing["sources"]["hepta"][role]
                with self.assertRaisesRegex(profile.ProfileError, "source map requires exactly"):
                    profile.check_map(missing)
        manifest, receipt = self.build()
        self.assertEqual(manifest["production"]["activation"], "disabled")
        self.assertFalse(receipt["production"]["effects_authorized"])
        self.assertIn("protected_authority_clock", manifest["production"]["unconfigured"])

    def test_app_only_readback_sources_are_required_and_remain_source_only(self):
        shipped = profile.load_json(Path(__file__).with_name("organ_source_map.json"))
        roles = {
            "session_readback": "ui/session/src/notes_readback.rs",
            "notes_recovery_helper": "ui/app-window/src/bin/trill-notes-recovery.rs",
            "root_session_readback": "services/hepta-session-host/src/product_root/session.rs",
        }
        for role, path in roles.items():
            with self.subTest(role=role):
                self.assertEqual(shipped["sources"]["os"][role], path)
                missing = copy.deepcopy(self.mapping)
                del missing["sources"]["os"][role]
                with self.assertRaisesRegex(profile.ProfileError, "source map requires exactly"):
                    profile.check_map(missing)
        manifest, receipt = self.build()
        recorded = {entry["role"]: entry for entry in manifest["sources"]["os"]}
        for role in roles:
            self.assertEqual(recorded[role]["path"], self.mapping["sources"]["os"][role])
        self.assertEqual(manifest["production"]["activation"], "disabled")
        self.assertFalse(receipt["production"]["effects_authorized"])

    def test_committed_recovery_golden_byte_mismatch_rejected(self):
        path = self.mapping["goldens"]["notes_recovery"]["hepta"]
        write(self.hepta, path, (self.hepta / path).read_bytes() + b" ")
        commit(self.hepta, "different recovery golden bytes")
        with self.assertRaisesRegex(profile.ProfileError, "golden byte mismatch: notes_recovery"):
            self.build()

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


if __name__ == "__main__":
    unittest.main()
