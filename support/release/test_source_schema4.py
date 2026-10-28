"""Schema4 closed maps and owning dispatch, using real temporary Git histories."""
import copy
import fnmatch
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest
from unittest.mock import patch
import zlib

HERE = Path(__file__).resolve().parent


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, HERE / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fixtures = load("schema4_source_fixtures", "test_organ_release_profile.py")
pair_tests = load("schema4_pair_fixtures", "test_check_organ_pair.py")
profile = fixtures.profile
runner = pair_tests.runner


def install_fixed_v4(case, fx):
    # Files live at the literal reviewed paths, not a caller-supplied alias map.
    # These are tool fixtures, never original runtime/authority qualifications.
    case.mapping = fx.profile.load_json(HERE / "organ_source_map_v4.json")
    for side in ("os", "hepta"):
        repo = getattr(case, side)
        for role, path in case.mapping["sources"][side].items():
            fx.write(repo, path, (side + ":" + role + " source\n").encode())
    for role, paths in case.mapping["goldens"].items():
        for side in ("os", "hepta"):
            fx.write(getattr(case, side), paths[side], (role + " exact golden\n").encode())
    fx.write(case.os, "support/release/organ_source_map_v4.json", fx.profile.canonical(case.mapping))
    fx.commit(case.os, "review fixed schema4 OS source paths")
    fx.commit(case.hepta, "review fixed schema4 original-owner descendant paths")


class Schema4SourceTests(unittest.TestCase):
    inputs = fixtures.SourceCombinationTests.inputs
    build = fixtures.SourceCombinationTests.build
    verify = fixtures.SourceCombinationTests.verify

    def setUp(self):
        fixtures.SourceCombinationTests.setUp(self)
        install_fixed_v4(self, fixtures)

    def test_fixed_v4_pair_records_all_roles_and_disabled_boundary(self):
        manifest, receipt = self.build()
        self.assertEqual(manifest["schema_version"], 4)
        self.assertEqual(receipt["schema_version"], 4)
        for side, roles in (("os", profile.OS_ROLES_V4), ("hepta", profile.HEPTA_ROLES_V4)):
            self.assertEqual({row["role"] for row in manifest["sources"][side]}, roles)
        self.assertEqual(len(manifest["goldens"]), 5)
        self.assertEqual(manifest["production"], profile.PRODUCTION)
        self.assertEqual(self.verify(manifest)["source_checks"], "passed")

    def test_each_added_role_is_mandatory_and_cannot_alias_another_path(self):
        original = copy.deepcopy(self.mapping)
        for side, old, new in (("os", profile.OS_ROLES_V3, profile.OS_ROLES_V4),
                               ("hepta", profile.HEPTA_ROLES_V3, profile.HEPTA_ROLES_V4)):
            for role in sorted(new - old):
                for mutation in ("omit", "alias"):
                    self.mapping = copy.deepcopy(original)
                    entries = self.mapping["sources"][side]
                    if mutation == "omit":
                        entries.pop(role)
                    else:
                        entries[role] = next(path for name, path in entries.items() if name != role)
                    with self.subTest(side=side, role=role, mutation=mutation), self.assertRaises(profile.ProfileError):
                        self.build()

    def test_unknown_role_downgrade_and_operator_path_replacement_are_refused(self):
        original = copy.deepcopy(self.mapping)
        for mutate in (
            lambda m: m["sources"]["os"].update(unreviewed_owner="new/source.rs"),
            lambda m: m.update(schema_version=3),
            lambda m: m["sources"]["os"].update(kernel_cpu_scheduling_route="other/tracked.rs"),
        ):
            self.mapping = copy.deepcopy(original)
            mutate(self.mapping)
            with self.subTest(mapping=self.mapping["schema_version"]), self.assertRaises(profile.ProfileError):
                self.build()

    def test_committed_missing_source_on_either_side_is_refused(self):
        for side, role in (("os", "kernel_vdso_cpu_probe_source"),
                           ("hepta", "rollout_fixture_support")):
            repo = getattr(self, side)
            path = self.mapping["sources"][side][role]
            (repo / path).unlink()
            fixtures.commit(repo, "remove required schema4 source")
            with self.subTest(side=side), self.assertRaisesRegex(profile.ProfileError, "required regular source file missing"):
                self.build()
            fixtures.git(repo, "restore", "--source=HEAD^", "--", path)
            fixtures.commit(repo, "restore the real required source")

    def test_new_owner_byte_drift_cannot_relabel_an_old_receipt(self):
        manifest, _ = self.build()
        for side, role in (("os", "unix_cpunode_guest_runner"),
                           ("hepta", "core_plugins_startup_archive_owner"),
                           ("hepta", "rollout_fixture_support")):
            repo = getattr(self, side)
            path = self.mapping["sources"][side][role]
            fixtures.write(repo, path, (repo / path).read_bytes() + b"changed owner\n")
            fixtures.commit(repo, "change original source bytes")
            edited = copy.deepcopy(manifest)
            if side == "hepta":
                edited["hepta"] = {"commit": fixtures.git(repo, "rev-parse", "HEAD"),
                                   "tree": fixtures.git(repo, "rev-parse", "HEAD^{tree}")}
            with self.subTest(side=side, role=role), self.assertRaisesRegex(profile.ProfileError, "manifest mismatch"):
                self.verify(edited)
            manifest, _ = self.build()

    def test_v4_checked_in_map_cannot_be_replaced_by_an_external_valid_map(self):
        stored = copy.deepcopy(self.mapping)
        stored["sources"]["hepta"]["rollout_fixture_support"] = "different/tracked.rs"
        fixtures.write(self.os, "support/release/organ_source_map_v4.json", profile.canonical(stored))
        fixtures.commit(self.os, "replace checked-in source path contract")
        with self.assertRaisesRegex(profile.ProfileError, "checked-in schema4 map differs"):
            self.build()

    def test_duplicate_json_keys_and_noninteger_versions_are_refused(self):
        data = profile.canonical(self.mapping).decode()
        duplicate = data.replace('"schema_version": 4', '"schema_version": 4, "schema_version": 4')
        with self.assertRaisesRegex(profile.ProfileError, "duplicate JSON key"):
            profile.load_json_bytes(duplicate.encode(), "duplicate schema4 map")
        for version in (True, 4.0, "4", 5):
            self.mapping["schema_version"] = version
            with self.subTest(version=version), self.assertRaisesRegex(profile.ProfileError, "unsupported source map"):
                self.build()

    def test_production_tampering_and_each_missing_deployment_input_are_refused(self):
        manifest, _ = self.build()
        mutations = [lambda m: m["production"].update(activation="enabled"),
                     lambda m: m["production"].update(effects_authorized=True),
                     lambda m: m.update(qualification="production")]
        for index in range(7):
            mutations.append(lambda m, i=index: m["production"]["unconfigured"].pop(i))
        for index, mutate in enumerate(mutations):
            edited = copy.deepcopy(manifest)
            mutate(edited)
            with self.subTest(mutation=index), self.assertRaisesRegex(profile.ProfileError, "manifest mismatch"):
                self.verify(edited)

    def test_original_history_object_and_real_ancestry_are_still_required(self):
        with patch.object(profile, "HISTORY_OWNER", "1" * 40):
            with self.assertRaisesRegex(profile.ProfileError, "owner path"):
                self.build()
        unrelated = fixtures.git(self.hepta, "commit-tree", fixtures.git(self.hepta, "rev-parse", "HEAD^{tree}"),
                                 "-m", "unrelated original owner")
        with patch.object(profile, "HISTORY_OWNER", unrelated):
            with self.assertRaisesRegex(profile.ProfileError, "owner path"):
                self.build()
        shallow = self.root / "schema4-shallow-unknown"
        fixtures.git(self.root, "clone", "--quiet", "--depth", "1", self.hepta.as_uri(), str(shallow))
        raw = profile.Repository(self.hepta, "hepta").git("cat-file", "commit", profile.HISTORY_OWNER)
        fixtures.git(shallow, "hash-object", "-w", "-t", "commit", "--stdin", input_bytes=raw)
        with self.assertRaisesRegex(profile.ProfileError, "nonshallow"):
            self.build(shallow)

    def test_hidden_flags_and_dirty_sources_still_prevent_a_v4_receipt(self):
        path = self.mapping["sources"]["os"]["unix_post1138_guest_runner"]
        fixtures.git(self.os, "update-index", "--assume-unchanged", path)
        fixtures.write(self.os, path, b"hidden source drift\n")
        with self.assertRaisesRegex(profile.ProfileError, "prevent clean proof"):
            self.build()

    def test_manifest_commit_retains_explicit_os_receipt_binding_without_cycle(self):
        manifest, before = self.build()
        fixtures.write(self.os, "candidate-source-profile.json", profile.canonical(manifest))
        fixtures.commit(self.os, "commit a source-only candidate manifest")
        after = self.verify(manifest)
        self.assertNotEqual(before["os"]["commit"], after["os"]["commit"])
        self.assertEqual(manifest["os_identity_binding"],
                         "explicit_caller_head_and_tree_in_verification_receipt")
        self.assertEqual(before["hepta"], after["hepta"])
        self.assertEqual(after["production"], profile.PRODUCTION)


class Schema4OwnerClosureTests(unittest.TestCase):
    setUp = Schema4SourceTests.setUp
    inputs = fixtures.SourceCombinationTests.inputs
    build = fixtures.SourceCombinationTests.build

    def commit_object(self, repo, parents, label):
        tree = fixtures.git(repo, "rev-parse", "HEAD^{tree}")
        # Keep each known parent earlier without making an unavailable side
        # branch newer than the real owner. Equal dates can change Git's fast
        # ancestor walk order around an unavailable pre-owner parent.
        dates = [1700000000]
        for parent in parents:
            result = subprocess.run(["git", "-C", str(repo), "cat-file", "commit", parent],
                                    capture_output=True, check=False)
            match = re.search(rb"^committer .* (\d+) [+-]\d{4}$", result.stdout, re.MULTILINE)
            if match:
                dates.append(int(match.group(1)))
        stamp = max(dates) + 1
        raw = (f"tree {tree}\n" + "".join(f"parent {parent}\n" for parent in parents)
               + f"author Source fixture <source-fixture@example.invalid> {stamp} +0000\n"
               + f"committer Source fixture <source-fixture@example.invalid> {stamp} +0000\n"
               + f"\n{label}\n").encode()
        return fixtures.git(repo, "hash-object", "-w", "-t", "commit", "--stdin", input_bytes=raw)

    def use_head(self, repo, head):
        fixtures.git(repo, "update-ref", "HEAD", head)
        self.assertEqual(fixtures.git(repo, "status", "--porcelain"), "")

    def remove_object(self, repo, oid):
        path = Path(fixtures.git(repo, "rev-parse", "--git-path", f"objects/{oid[:2]}/{oid[2:]}"))
        if not path.is_absolute():
            path = repo / path
        path.unlink()  # Only the newly created temporary fixture's loose object.
        self.assertEqual(fixtures.git(repo, "status", "--porcelain"), "")

    def test_receipt_records_exact_owner_scope_without_full_repository_claim(self):
        _, receipt = self.build()
        closure = receipt.get("git_object_closure", {})
        self.assertEqual(set(closure), {"os", "hepta"})
        self.assertEqual(closure["hepta"]["scope"], "selected_owner_ancestry_path")
        self.assertEqual(closure["hepta"]["proof_version"], 2)
        self.assertEqual(receipt["original_history_proof"]["method"], "verified_sha1_parent_path")
        self.assertEqual(closure["hepta"]["owner"], profile.HISTORY_OWNER)
        self.assertEqual(closure["os"]["scope"], "current_tree")
        for proof in closure.values():
            self.assertIsNone(proof["whole_repository_history_complete"])
            self.assertEqual(proof["earlier_history"], "not_verified")
            self.assertEqual(proof["missing_objects"], 0)
            self.assertGreater(proof["object_count"], 0)

    def test_unavailable_parent_before_exact_owner_does_not_expand_the_scope(self):
        older = self.commit_object(self.hepta, [], "owned older parent before exact owner")
        owner = self.commit_object(self.hepta, [older], "exact owner with unavailable older parent")
        tip = self.commit_object(self.hepta, [owner], "descendant")
        self.use_head(self.hepta, tip)
        fixtures.git(self.hepta, "merge-base", "--is-ancestor", owner, "HEAD")
        # Validate real ancestry before removing the owned pre-owner object:
        # newer Git may inspect it even when the requested owner is present.
        self.remove_object(self.hepta, older)
        self.assertEqual(fixtures.git(self.hepta, "rev-parse", "--is-shallow-repository"), "false")
        with patch.object(profile, "HISTORY_OWNER", owner):
            _, receipt = self.build()
        self.assertEqual(receipt["source_checks"], "passed")

    def test_missing_blob_before_owner_is_outside_the_bounded_proof(self):
        fixtures.write(self.hepta, "older.txt", b"unavailable pre-owner blob\n")
        fixtures.commit(self.hepta, "older blob")
        oid = fixtures.git(self.hepta, "rev-parse", "HEAD:older.txt")
        fixtures.git(self.hepta, "rm", "--quiet", "older.txt")
        owner = fixtures.commit(self.hepta, "exact owner after removing older blob")
        tip = self.commit_object(self.hepta, [owner], "descendant of exact owner")
        self.use_head(self.hepta, tip)
        self.remove_object(self.hepta, oid)
        with patch.object(profile, "HISTORY_OWNER", owner):
            _, receipt = self.build()
        self.assertEqual(receipt["source_checks"], "passed")

    def test_missing_unselected_merge_parent_is_explicitly_unverified(self):
        tip = self.commit_object(self.hepta, [profile.HISTORY_OWNER, "1" * 40], "missing merge parent")
        self.use_head(self.hepta, tip)
        _, receipt = self.build()
        side = receipt["git_object_closure"]["hepta"]["unselected_merge_parents"]
        self.assertEqual([(row["parent"], row["verification"]) for row in side],
                         [("1" * 40, "not_verified")])

    def test_unselected_side_history_is_not_a_required_owner_path(self):
        side = self.commit_object(self.hepta, ["1" * 40], "side with missing intermediate")
        tip = self.commit_object(self.hepta, [profile.HISTORY_OWNER, side], "merge with present side tip")
        self.use_head(self.hepta, tip)
        _, receipt = self.build()
        rows = receipt["git_object_closure"]["hepta"]["unselected_merge_parents"]
        self.assertEqual([(row["parent"], row["verification"]) for row in rows],
                         [(side, "not_verified")])

    def test_unselected_external_root_does_not_falsify_the_owner_chain(self):
        other = self.commit_object(self.hepta, [], "unrelated root")
        tip = self.commit_object(self.hepta, [profile.HISTORY_OWNER, other], "merge external root")
        self.use_head(self.hepta, tip)
        _, receipt = self.build()
        rows = receipt["git_object_closure"]["hepta"]["unselected_merge_parents"]
        self.assertEqual(rows[0]["parent"], other)
        self.assertEqual(rows[0]["verification"], "not_verified")

    def test_missing_owner_tree_blob_is_refused_even_after_current_deletion(self):
        fixtures.write(self.hepta, "owner-only.txt", b"required original-owner blob\n")
        owner = fixtures.commit(self.hepta, "exact owner with its own blob")
        oid = fixtures.git(self.hepta, "rev-parse", "HEAD:owner-only.txt")
        fixtures.git(self.hepta, "rm", "--quiet", "owner-only.txt")
        fixtures.commit(self.hepta, "current tree no longer includes owner blob")
        self.remove_object(self.hepta, oid)
        with patch.object(profile, "HISTORY_OWNER", owner):
            with self.assertRaisesRegex(profile.ProfileError, "tree/blob closure"):
                self.build()

    def test_missing_historical_blob_inside_owner_range_is_refused(self):
        fixtures.write(self.hepta, "range-only.txt", b"required range blob\n")
        fixtures.commit(self.hepta, "add range blob")
        oid = fixtures.git(self.hepta, "rev-parse", "HEAD:range-only.txt")
        tree = fixtures.git(self.hepta, "rev-parse", "HEAD^{tree}")
        fixtures.git(self.hepta, "rm", "--quiet", "range-only.txt")
        fixtures.commit(self.hepta, "remove range blob from current tree")
        self.remove_object(self.hepta, oid)
        listed = fixtures.git(self.hepta, "rev-list", "--objects", "--missing=print", tree)
        self.assertIn("?" + oid, listed)  # The command exited zero despite missing data.
        with self.assertRaisesRegex(profile.ProfileError, "tree/blob closure"):
            self.build()

    def test_missing_intermediate_tree_inside_owner_range_is_refused(self):
        fixtures.write(self.hepta, "range-dir/only.txt", b"required intermediate tree\n")
        fixtures.commit(self.hepta, "add range tree")
        oid = fixtures.git(self.hepta, "rev-parse", "HEAD:range-dir")
        fixtures.git(self.hepta, "rm", "--quiet", "-r", "range-dir")
        fixtures.commit(self.hepta, "remove range tree from current checkout")
        self.remove_object(self.hepta, oid)
        with self.assertRaisesRegex(profile.ProfileError, "tree/blob closure"):
            self.build()

    def test_missing_current_unmapped_os_blob_is_refused(self):
        fixtures.write(self.os, "unmapped.txt", b"required current unmapped blob\n")
        fixtures.commit(self.os, "add current unmapped blob")
        oid = fixtures.git(self.os, "rev-parse", "HEAD:unmapped.txt")
        self.remove_object(self.os, oid)
        with self.assertRaisesRegex(profile.ProfileError, "tree/blob closure"):
            self.build()

    def test_replace_ref_cannot_invent_a_real_owner_path(self):
        original = fixtures.git(self.hepta, "rev-parse", "HEAD")
        tip = self.commit_object(self.hepta, ["1" * 40], "no real owner path")
        self.use_head(self.hepta, tip)
        fixtures.git(self.hepta, "update-ref", f"refs/replace/{tip}", original)
        with self.assertRaisesRegex(profile.ProfileError, "owner path|replacement ref"):
            self.build()

    def test_v4_shallow_flag_is_still_refused_when_ancestry_is_present(self):
        shallow = self.root / "shallow-proven-owner"
        fixtures.git(self.root, "clone", "--quiet", "--depth", "2", self.hepta.as_uri(), str(shallow))
        owner = fixtures.git(shallow, "rev-parse", "HEAD^")
        with patch.object(profile, "HISTORY_OWNER", owner):
            with self.assertRaisesRegex(profile.ProfileError, "nonshallow"):
                self.build(shallow)

    def test_complete_local_alternates_are_allowed(self):
        alternate = self.root / "complete-alternate"
        fixtures.git(self.root, "clone", "--quiet", "--shared", str(self.hepta), str(alternate))
        self.assertTrue((alternate / ".git/objects/info/alternates").is_file())
        _, receipt = self.build(alternate)
        self.assertEqual(receipt["source_checks"], "passed")


class Schema4OwnerPathProofTests(unittest.TestCase):
    setUp = Schema4OwnerClosureTests.setUp
    inputs = Schema4OwnerClosureTests.inputs
    build = Schema4OwnerClosureTests.build
    commit_object = Schema4OwnerClosureTests.commit_object
    use_head = Schema4OwnerClosureTests.use_head
    remove_object = Schema4OwnerClosureTests.remove_object

    def test_real_join_keeps_the_owner_as_second_parent_and_old_line_unknown(self):
        # Real local DAG matching de489's structure, not a mocked Git result.
        side = self.commit_object(self.hepta, ["1" * 40], "older mainline")
        tip = self.commit_object(self.hepta, [side, profile.HISTORY_OWNER], "join two histories")
        self.use_head(self.hepta, tip)
        _, receipt = self.build()
        proof = receipt["git_object_closure"]["hepta"]
        self.assertEqual(proof["path_commits_owner_to_head"], [profile.HISTORY_OWNER, tip])
        self.assertEqual(proof["path_edges"],
                         [{"child": tip, "parent": profile.HISTORY_OWNER, "parent_index": 1}])
        self.assertEqual([(r["commit"], r["parent"], r["parent_index"], r["verification"])
                          for r in proof["unselected_merge_parents"]],
                         [(tip, side, 0, "not_verified")])
        self.assertFalse(proof["all_parent_graph_verified"])
        self.assertIsNone(proof["whole_repository_history_complete"])

    def test_same_batch_missing_side_does_not_discard_the_real_owner(self):
        tip = self.commit_object(self.hepta, ["1" * 40, profile.HISTORY_OWNER], "missing first parent")
        self.use_head(self.hepta, tip)
        _, receipt = self.build()
        proof = receipt["git_object_closure"]["hepta"]
        self.assertEqual(proof["path_edges"][0]["parent_index"], 1)
        self.assertEqual(proof["unselected_merge_parents"][0]["local_object_observation"], "missing")

    def test_bfs_uses_the_first_real_parent_path_and_records_both_edges(self):
        first = self.commit_object(self.hepta, [profile.HISTORY_OWNER], "first owner descendant")
        second = self.commit_object(self.hepta, [profile.HISTORY_OWNER], "second owner descendant")
        tip = self.commit_object(self.hepta, [first, second], "two equal-length real owner paths")
        self.use_head(self.hepta, tip)
        _, receipt = self.build()
        proof = receipt["git_object_closure"]["hepta"]
        self.assertEqual(proof["path_commits_owner_to_head"], [profile.HISTORY_OWNER, first, tip])
        self.assertEqual(proof["path_edges"],
                         [{"child": first, "parent": profile.HISTORY_OWNER, "parent_index": 0},
                          {"child": tip, "parent": first, "parent_index": 0}])
        self.assertEqual(proof["unselected_merge_parents"][0]["parent"], second)

    def test_missing_unique_path_commit_is_refused(self):
        middle = self.commit_object(self.hepta, [profile.HISTORY_OWNER], "required middle")
        tip = self.commit_object(self.hepta, [middle], "unique descendant")
        self.use_head(self.hepta, tip)
        self.remove_object(self.hepta, middle)
        with self.assertRaisesRegex(profile.ProfileError, "owner path"):
            self.build()

    def test_no_owner_path_cannot_use_an_unrelated_available_root(self):
        root = self.commit_object(self.hepta, [], "other history root")
        self.use_head(self.hepta, root)
        with self.assertRaisesRegex(profile.ProfileError, "owner path"):
            self.build()

    def test_selected_chain_blob_failure_does_not_search_another_path(self):
        fixtures.write(self.hepta, "first-path-only.txt", b"required selected chain bytes\n")
        fixtures.commit(self.hepta, "first owner tree")
        first = self.commit_object(self.hepta, [profile.HISTORY_OWNER], "first owner path")
        missing = fixtures.git(self.hepta, "rev-parse", "HEAD:first-path-only.txt")
        fixtures.git(self.hepta, "rm", "--quiet", "first-path-only.txt")
        fixtures.commit(self.hepta, "complete current and alternative tree")
        second = self.commit_object(self.hepta, [profile.HISTORY_OWNER], "complete alternative")
        tip = self.commit_object(self.hepta, [first, second], "prefer first parent")
        self.use_head(self.hepta, tip)
        self.remove_object(self.hepta, missing)
        with self.assertRaisesRegex(profile.ProfileError, "tree/blob closure"):
            self.build()

    def test_selected_chain_directory_tree_failure_does_not_search_another_path(self):
        fixtures.write(self.hepta, "first-path-dir/only.txt", b"selected directory tree\n")
        fixtures.commit(self.hepta, "first path directory")
        first = self.commit_object(self.hepta, [profile.HISTORY_OWNER], "first tree path")
        missing = fixtures.git(self.hepta, "rev-parse", "HEAD:first-path-dir")
        fixtures.git(self.hepta, "rm", "--quiet", "-r", "first-path-dir")
        fixtures.commit(self.hepta, "complete alternative current tree")
        second = self.commit_object(self.hepta, [profile.HISTORY_OWNER], "complete alternative")
        tip = self.commit_object(self.hepta, [first, second], "prefer first tree path")
        self.use_head(self.hepta, tip)
        self.remove_object(self.hepta, missing)
        with self.assertRaisesRegex(profile.ProfileError, "tree/blob closure"):
            self.build()

    def test_wrong_type_side_candidate_is_fatal_even_with_an_owner_path(self):
        blob = fixtures.git(self.hepta, "hash-object", "-w", "--stdin", input_bytes=b"not a commit\n")
        tip = self.commit_object(self.hepta, [blob, profile.HISTORY_OWNER], "wrong type parent")
        self.use_head(self.hepta, tip)
        with self.assertRaisesRegex(profile.ProfileError, "commit|type"):
            self.build()

    def test_sha_correct_late_parent_header_cannot_forge_an_owner_edge(self):
        tree = fixtures.git(self.hepta, "rev-parse", "HEAD^{tree}")
        raw = (f"tree {tree}\nauthor Fixture <fixture@example.invalid> 1700000000 +0000\n"
               f"committer Fixture <fixture@example.invalid> 1700000000 +0000\n"
               f"parent {profile.HISTORY_OWNER}\n\nnot a real Git parent block\n").encode()
        tip = fixtures.git(self.hepta, "hash-object", "--literally", "-w", "-t", "commit", "--stdin",
                           input_bytes=raw)
        self.use_head(self.hepta, tip)
        with self.assertRaisesRegex(profile.ProfileError, "late parent|commit header"):
            self.build()

    def test_malformed_intermediate_cr_headers_cannot_create_git_parent_edges(self):
        tree = fixtures.git(self.hepta, "rev-parse", "HEAD^{tree}")
        other = self.commit_object(self.hepta, [], "available unrelated root")
        common = (b"author Fixture <fixture@example.invalid> 1700000000 +0000\n"
                  b"committer Fixture <fixture@example.invalid> 1700000000 +0000\n\nmalformed middle\n")
        for label, headers in (
            ("bare-tree-CR", f"tree {tree}\rparent {profile.HISTORY_OWNER}\n"),
            ("tree-CRLF", f"tree {tree}\r\nparent {profile.HISTORY_OWNER}\n"),
            ("bare-parent-CR", f"tree {tree}\nparent {other}\rparent {profile.HISTORY_OWNER}\n"),
        ):
            with self.subTest(malformed=label):
                raw = headers.encode() + common
                middle = fixtures.git(self.hepta, "hash-object", "--literally", "-w", "-t", "commit",
                                      "--stdin", input_bytes=raw)
                # Keep HEAD ordinary so Git's preliminary HEAD lookup cannot
                # substitute for validating this malformed intermediate body.
                tip = self.commit_object(self.hepta, [middle], "ordinary HEAD above malformed " + label)
                self.use_head(self.hepta, tip)
                with self.assertRaises(profile.ProfileError):
                    self.build()

    def test_historical_blob_hash_is_verified_beyond_missing_enumeration(self):
        fixtures.write(self.hepta, "historical-only.txt", b"selected historical bytes\n")
        fixtures.commit(self.hepta, "required historical object")
        blob = fixtures.git(self.hepta, "rev-parse", "HEAD:historical-only.txt")
        fixtures.git(self.hepta, "rm", "--quiet", "historical-only.txt")
        fixtures.commit(self.hepta, "historical blob no longer in current tree")
        path = self.hepta / ".git/objects" / blob[:2] / blob[2:]
        replacement = b"altered historical bytes\n"
        # This loose object belongs to this test's new TemporaryDirectory Git store.
        path.chmod(0o600)
        path.write_bytes(zlib.compress(f"blob {len(replacement)}\0".encode() + replacement))
        self.assertEqual(fixtures.git(self.hepta, "status", "--porcelain"), "")
        with self.assertRaisesRegex(profile.ProfileError, "object identity differs"):
            self.build()

    def test_truncated_owned_historical_object_fails_the_real_git_stream(self):
        fixtures.write(self.hepta, "truncated-only.txt", b"historical stream body\n" * 100)
        fixtures.commit(self.hepta, "historical stream object")
        blob = fixtures.git(self.hepta, "rev-parse", "HEAD:truncated-only.txt")
        fixtures.git(self.hepta, "rm", "--quiet", "truncated-only.txt")
        fixtures.commit(self.hepta, "complete current tree without historical file")
        path = self.hepta / ".git/objects" / blob[:2] / blob[2:]
        # Git creates even owned loose objects read-only; corrupt only this fixture.
        path.chmod(0o600)
        path.write_bytes(path.read_bytes()[:-3])  # Owned loose zlib body only.
        with self.assertRaises(profile.ProfileError):
            self.build()

    def test_selected_historical_tree_entry_kind_must_match_its_object(self):
        current_tree = fixtures.git(self.hepta, "rev-parse", "HEAD^{tree}")
        blob = fixtures.git(self.hepta, "hash-object", "-w", "--stdin", input_bytes=b"not a directory\n")
        detached = fixtures.git(self.hepta, "mktree", input_bytes=f"100644 blob {blob}\tchild\n".encode())
        for label, entry in (
            ("file-to-tree", b"100644 file\0" + bytes.fromhex(current_tree)),
            ("directory-to-blob", b"40000 directory\0" + bytes.fromhex(blob)),
            ("file-to-detached-tree", b"100644 hidden\0" + bytes.fromhex(detached)),
        ):
            with self.subTest(wrong_kind=label):
                tree = fixtures.git(self.hepta, "hash-object", "--literally", "-w", "-t", "tree",
                                    "--stdin", input_bytes=entry)
                raw = (f"tree {tree}\nparent {profile.HISTORY_OWNER}\n"
                       "author Fixture <fixture@example.invalid> 1700000000 +0000\n"
                       "committer Fixture <fixture@example.invalid> 1700000000 +0000\n\n"
                       "historical tree with a wrong-kind entry\n").encode()
                middle = fixtures.git(self.hepta, "hash-object", "--literally", "-w", "-t", "commit",
                                      "--stdin", input_bytes=raw)
                tip = self.commit_object(self.hepta, [middle], "ordinary current tree above " + label)
                self.use_head(self.hepta, tip)
                # Source-only risk probe: actual Git rev-list may already
                # refuse it. No claim that the previous gate accepted it.
                with self.assertRaises(profile.ProfileError):
                    self.build()

    def test_gitlink_is_an_unverified_external_commit_edge_without_local_target_history(self):
        foreign = "7" * 40
        self.assertNotEqual(subprocess.run(["git", "-C", str(self.hepta), "cat-file", "-e", foreign],
                                          capture_output=True).returncode, 0)
        tree = fixtures.git(self.hepta, "hash-object", "--literally", "-w", "-t", "tree", "--stdin",
                            input_bytes=b"160000 submodule\0" + bytes.fromhex(foreign))
        raw = (f"tree {tree}\nparent {profile.HISTORY_OWNER}\n"
               "author Fixture <fixture@example.invalid> 1700000000 +0000\n"
               "committer Fixture <fixture@example.invalid> 1700000000 +0000\n\n"
               "external submodule history is not a tree/blob closure input\n").encode()
        middle = fixtures.git(self.hepta, "hash-object", "-w", "-t", "commit", "--stdin", input_bytes=raw)
        tip = self.commit_object(self.hepta, [middle], "ordinary source above external gitlink")
        self.use_head(self.hepta, tip)
        _, receipt = self.build()
        proof = receipt["git_object_closure"]["hepta"]
        self.assertTrue(proof["tree_blob_entry_types_verified"])
        self.assertEqual(proof["gitlink_edge_count"], 1)
        self.assertEqual(proof["gitlink_edges_sha256"], profile.sha256(profile.canonical([
            {"tree": tree, "entry_index": 0, "commit": foreign, "verification": "not_verified"}])))
        self.assertFalse(proof["gitlink_target_objects_verified"])
        self.assertEqual(proof["gitlink_subrepository_history"], "not_verified")

    def test_current_unmapped_mode_is_checked_when_git_filemode_is_disabled(self):
        fixtures.write(self.os, "unmapped-mode.txt", b"all current source modes\n")
        fixtures.commit(self.os, "unmapped current mode")
        fixtures.git(self.os, "config", "core.filemode", "false")
        (self.os / "unmapped-mode.txt").chmod(0o755)
        self.assertEqual(fixtures.git(self.os, "status", "--porcelain"), "")
        with self.assertRaisesRegex(profile.ProfileError, "current source.*mode"):
            self.build()

    def test_git_executable_mode_requires_owner_execute_not_other_execute_bits(self):
        fixtures.write(self.os, "unmapped-owner-exec.txt", b"Git owner executable bit\n")
        path = self.os / "unmapped-owner-exec.txt"
        path.chmod(0o755)
        fixtures.commit(self.os, "tracked executable source")
        fixtures.git(self.os, "config", "core.filemode", "false")
        path.chmod(0o655)
        self.assertEqual(fixtures.git(self.os, "status", "--porcelain"), "")
        with self.assertRaisesRegex(profile.ProfileError, "current source.*mode"):
            self.build()

    def test_unmapped_bytes_are_checked_despite_a_trusted_stale_index_stat(self):
        path = self.os / "unmapped-stat.txt"
        fixtures.write(self.os, "unmapped-stat.txt", b"old\n")
        os.utime(path, (1700000000, 1700000000))
        fixtures.commit(self.os, "old tracked stat")
        fixtures.git(self.os, "config", "core.trustctime", "false")
        path.write_bytes(b"new\n")
        os.utime(path, (1700000000, 1700000000))
        self.assertEqual(fixtures.git(self.os, "status", "--porcelain"), "")
        with self.assertRaisesRegex(profile.ProfileError, "current source.*byte"):
            self.build()

    def test_current_symlink_is_bound_by_link_bytes_without_following_target(self):
        os.symlink("/nonexistent/owned-source-proof-target", self.os / "unmapped-link")
        fixtures.commit(self.os, "tracked link bytes only")
        _, receipt = self.build()
        proof = receipt["current_source_proof"]["os"]
        self.assertEqual(proof["file_count"], len(fixtures.git(self.os, "ls-files").splitlines()))
        self.assertEqual(proof["symlink_count"], 1)

    def test_v4_explicitly_rejects_an_existing_unused_replacement_ref(self):
        original = fixtures.git(self.hepta, "rev-parse", "HEAD")
        unused = self.commit_object(self.hepta, [profile.HISTORY_OWNER], "unused replacement source")
        fixtures.git(self.hepta, "update-ref", f"refs/replace/{unused}", original)
        with self.assertRaisesRegex(profile.ProfileError, "replacement ref"):
            self.build()

    def test_same_tree_new_commit_after_last_snapshot_cannot_relabel_the_pin(self):
        original = profile.Repository.snapshot_current_source
        calls = [0]

        def move_after_snapshot(repo):
            result = original(repo)
            if repo.name == "os":
                calls[0] += 1
                if calls[0] == 2:
                    old = fixtures.git(self.os, "rev-parse", "HEAD")
                    new = self.commit_object(self.os, [old], "same-tree HEAD moved after read")
                    fixtures.git(self.os, "update-ref", "HEAD", new)
            return result

        with patch.object(profile.Repository, "snapshot_current_source", move_after_snapshot):
            with self.assertRaisesRegex(profile.ProfileError, "HEAD mismatch"):
                self.build()


class Schema4TreeEntryStreamTests(unittest.TestCase):
    def test_fragmented_binary_object_ids_keep_their_real_mode_edges(self):
        modes = [(b"40000", "tree"), (b"100644", "blob"), (b"100755", "blob"),
                 (b"120000", "blob"), (b"160000", "commit")]
        # Raw SHA bytes contain NUL, newline and space. They are fixed-width
        # binary IDs, never another filename/header delimiter.
        raw_oid = bytes(range(20))
        raw = b"".join(mode + b" name with space\n\0" + raw_oid for mode, _ in modes)
        expected = [{"mode": mode.decode(), "expected_type": kind, "oid": raw_oid.hex()}
                    for mode, kind in modes]
        for width in (1, 2, 7, 20, 31, len(raw)):
            with self.subTest(read_width=width):
                parser = profile._TreeEntryStream()
                for start in range(0, len(raw), width):
                    parser.feed(raw[start:start + width])
                self.assertEqual(parser.finish(), expected)

    def test_malformed_modes_names_and_truncated_binary_ids_are_refused(self):
        oid = bytes(range(20))
        for raw in (b"100600 name\0" + oid, b"100644\0" + oid, b"100644 \0" + oid,
                    b"40000 .\0" + oid, b"40000 ..\0" + oid, b"40000 a/b\0" + oid,
                    b"100644 name", b"100644 name\0" + oid[:-1]):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                parser = profile._TreeEntryStream()
                parser.feed(raw)
                parser.finish()

    def test_incomplete_name_header_has_a_bounded_buffer(self):
        parser = profile._TreeEntryStream()
        with self.assertRaisesRegex(ValueError, "header budget"):
            parser.feed(b"100644 " + b"x" * (parser.HEADER_LIMIT + 22))


class Schema4PairTests(unittest.TestCase):
    setUp = pair_tests.PairExecutionTests.setUp
    arguments = pair_tests.PairExecutionTests.arguments
    execute_fixture = pair_tests.PairExecutionTests.execute_fixture
    run_pair = pair_tests.PairExecutionTests.run_pair
    receipt = pair_tests.PairExecutionTests.receipt

    def prepare_v4(self):
        fx = pair_tests.fixtures
        install_fixed_v4(self, fx)
        with patch.object(runner.profile, "HISTORY_OWNER", self.owner):
            manifest, _ = runner.profile.create_manifest(*fx.SourceCombinationTests.inputs(self))
        self.manifest.write_bytes(runner.profile.canonical(manifest))

    def test_v4_selects_fixed_map_without_host_execution(self):
        self.prepare_v4()
        with patch.object(runner, "execute_step", side_effect=AssertionError("unexpected execution")):
            self.assertEqual(self.run_pair("--required-schema", "4"), 0)
        self.assertEqual(self.receipt()["qualification"], "source-only")
        self.assertEqual(self.receipt()["source"]["schema_version"], 4)

    def test_v4_actual_dispatch_runs_eighteen_owners_and_original_binaries(self):
        self.prepare_v4()
        with patch.object(runner, "execute_step", side_effect=self.execute_fixture):
            self.assertEqual(self.run_pair("--required-schema", "4", "--execute-host", "--offline"), 0)
        steps = {step[0]: step for step in self.dispatched}
        argv = steps["hepta-tests"][3]
        packages = [argv[index + 1] for index, value in enumerate(argv) if value == "-p"]
        self.assertEqual(len(packages), len(set(packages)))
        self.assertEqual(len(packages), 18)
        legacy_tests = next(step[3] for step in runner.host_steps(self.os, self.hepta, True,
                                                                 schema_version=3)
                            if step[0] == "hepta-tests")
        legacy_packages = {legacy_tests[index + 1] for index, value in enumerate(legacy_tests)
                           if value == "-p"}
        self.assertEqual(set(packages), legacy_packages | {
            "codex-app-server-protocol", "codex-thread-store", "codex-core-plugins",
            "codex-rollout", "codex-file-system"})
        self.assertEqual(set(steps), {"ui-build", "ui-tests", "adapter-tests", "hepta-build",
                                     "hepta-root-build", "hepta-recovery-build", "hepta-tests"})
        self.assertEqual(self.receipt()["qualification"], "host-build-tests")
        for step in self.dispatched:
            self.assertIn("--locked", step[3])
        for name in ("hepta-build", "hepta-root-build", "hepta-recovery-build"):
            self.assertEqual(steps[name][2], "1.95.0")
            self.assertIn("dev-small", steps[name][3])

    def test_required_v4_blocks_historical_input_and_unknown_map_roles(self):
        with patch.object(runner, "execute_step", side_effect=AssertionError("unexpected execution")):
            self.assertEqual(self.run_pair("--required-schema", "4", "--execute-host"), 1)
        self.assertFalse(self.output.exists())
        self.prepare_v4()
        bad = copy.deepcopy(self.mapping)
        bad["sources"]["hepta"].pop("rollout_fixture_support")
        pair_tests.fixtures.write(self.os, "support/release/organ_source_map_v4.json",
                                  runner.profile.canonical(bad))
        pair_tests.fixtures.commit(self.os, "omit a schema4 owning helper")
        with patch.object(runner, "execute_step", side_effect=AssertionError("unexpected execution")):
            self.assertEqual(self.run_pair("--required-schema", "4", "--execute-host"), 1)
        self.assertFalse(self.output.exists())

    def test_v4_final_source_recheck_rejects_generator_drift(self):
        self.prepare_v4()

        def mutate_after_last_step(step, output, environment, timeout, targets=None):
            result = self.execute_fixture(step, output, environment, timeout, targets)
            if step[0] == "hepta-tests":
                pair_tests.fixtures.write(self.hepta, self.mapping["sources"]["hepta"]["rollout_fixture_support"],
                                         b"generated but unreviewed\n")
            return result

        with patch.object(runner, "execute_step", side_effect=mutate_after_last_step):
            self.assertEqual(self.run_pair("--required-schema", "4", "--execute-host"), 1)
        self.assertEqual(self.receipt()["qualification"], "none")
        self.assertFalse(self.receipt()["passed"])


def workflow_run_block(path, step_name):
    """Read a real literal run block without needing a YAML dependency."""
    text = path.read_text()
    marker = "      - name: " + step_name + "\n"
    if text.count(marker) != 1:
        raise AssertionError("workflow step missing or repeated: " + step_name)
    block = text.split(marker, 1)[1].split("\n      - ", 1)[0]
    script = block.split("        run: |\n", 1)[1]
    return "\n".join(line[10:] if line.startswith("          ") else line
                     for line in script.splitlines()) + "\n"


class CurrentWorkflowTests(unittest.TestCase):
    setUp_pair = pair_tests.PairExecutionTests.setUp
    execute_fixture = pair_tests.PairExecutionTests.execute_fixture

    def setUp(self):
        self.setUp_pair()
        fx = pair_tests.fixtures
        install_fixed_v4(self, fx)
        for path in ("support/release/organ_release_profile.py", "support/release/check_organ_pair.py",
                     ".github/workflows/organ-current-pair.yml",
                     ".github/workflows/organ-release-profile.yml",
                     "support/release/organ_source_map.json", "support/release/organ_source_map_v2.json",
                     "support/release/organ_source_map_v3.json"):
            fx.write(self.os, path, (HERE.parents[1] / path).read_bytes())
        fx.commit(self.os, "copy the actual reviewed release tools and CI callers")
        self.manifest = self.os / "support/release/profiles/current-organ-source.json"
        self.publish_manifest(4)

    def publish_manifest(self, version):
        mapping = self.mapping if version == 4 else runner.profile.load_json(HERE / runner.profile.source_map_name(version))
        fx = pair_tests.fixtures
        with patch.object(runner.profile, "HISTORY_OWNER", self.owner):
            manifest, _ = runner.profile.create_manifest(
                runner.profile.Repository(self.os, "os"), runner.profile.Repository(self.hepta, "hepta"),
                fx.git(self.os, "rev-parse", "HEAD"), fx.git(self.os, "rev-parse", "HEAD^{tree}"),
                fx.git(self.hepta, "rev-parse", "HEAD"), fx.git(self.hepta, "rev-parse", "HEAD^{tree}"), mapping)
        fx.write(self.os, "support/release/profiles/current-organ-source.json", runner.profile.canonical(manifest))
        fx.commit(self.os, "commit a source manifest with external OS identity binding")
        # Prove the historical fixture is really accepted with its explicit
        # mapping before testing the stricter current-only CI boundary.
        with patch.object(runner.profile, "HISTORY_OWNER", self.owner):
            runner.profile.verify_manifest(
                manifest, runner.profile.Repository(self.os, "os"), runner.profile.Repository(self.hepta, "hepta"),
                fx.git(self.os, "rev-parse", "HEAD"), fx.git(self.os, "rev-parse", "HEAD^{tree}"), mapping)
        return manifest

    def run_ci_python(self, workflow, step):
        run = workflow_run_block(self.os / workflow, step)
        start = "python3 -I -B - <<'PY'\n"
        self.assertEqual(run.count(start), 1)
        python = run.split(start, 1)[1].split("\nPY", 1)[0]
        # Only the test process substitutes its real temporary-Git ancestor,
        # exactly like the existing fixture patch; production has no override.
        prefix = ("import runpy as _fixture_runpy\n"
                  "_fixture_original = _fixture_runpy.run_path\n"
                  "def _fixture_load(*args, **kwargs):\n"
                  "    result = _fixture_original(*args, **kwargs)\n"
                  "    if 'check_current_contract' in result:\n"
                  f"        result['check_current_contract'].__globals__['HISTORY_OWNER'] = {self.owner!r}\n"
                  "    return result\n"
                  "_fixture_runpy.run_path = _fixture_load\n")
        output = self.root / "github-output"
        if output.exists():
            output.unlink()
        result = subprocess.run([sys.executable, "-I", "-B", "-c", prefix + python],
                                cwd=self.os, env=dict(os.environ, GITHUB_OUTPUT=str(output)),
                                capture_output=True, text=True, timeout=30)
        return result, output

    def run_pin_reader(self):
        return self.run_ci_python(".github/workflows/organ-current-pair.yml",
                                  "Read the single reviewed Hepta pin")

    def current_ci_dispatch(self):
        # Let bash resolve the actual workflow's quoting, Git tree expression
        # and environment. Capture only Python's argv, then run the real source
        # verifier/dispatcher with bounded fixture children as in earlier tests.
        helpers = self.root / "dispatch-helpers"
        helpers.mkdir()
        capture = self.root / "python-argv.json"
        executable = helpers / "python3"
        executable.write_text(f"#!{sys.executable}\nimport json, os, sys\n"
                              "with open(os.environ['FIXTURE_CAPTURE_ARGV'], 'x') as stream:\n"
                              "    json.dump(sys.argv[1:], stream)\n")
        executable.chmod(0o755)
        temporary = self.root / "runner-temp"
        temporary.mkdir()
        run = workflow_run_block(self.os / ".github/workflows/organ-current-pair.yml",
                                  "Build and test the complete original source pair")
        env = dict(os.environ, PATH=str(helpers) + os.pathsep + os.environ.get("PATH", ""),
                   FIXTURE_CAPTURE_ARGV=str(capture), GITHUB_WORKSPACE=str(self.root),
                   DESKTOP_SHA=pair_tests.fixtures.git(self.os, "rev-parse", "HEAD"), RUNNER_TEMP=str(temporary))
        subprocess.run(["bash", "-c", run], cwd=self.os, env=env, capture_output=True, check=True, timeout=30)
        args = json.loads(capture.read_text())
        self.assertEqual(args[:3], ["-I", "-B", "support/release/check_organ_pair.py"])
        self.output = temporary / "organ-pair"
        return args[3:]

    def run_captured_pair(self, args):
        previous = Path.cwd()
        try:
            os.chdir(self.os)
            return runner.main(args)
        finally:
            os.chdir(previous)

    def test_pin_reader_executes_current_gate_before_emitting_the_exact_pin(self):
        result, output = self.run_pin_reader()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(output.read_text(), "hepta_sha=" + pair_tests.fixtures.git(self.hepta, "rev-parse", "HEAD") + "\n")

    def test_pin_reader_rejects_missing_and_valid_historical_manifests(self):
        self.manifest.unlink()
        pair_tests.fixtures.commit(self.os, "remove current input")
        result, output = self.run_pin_reader()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())
        self.publish_manifest(3)
        result, output = self.run_pin_reader()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())

    def test_pin_reader_rejects_map_seal_and_production_tampering(self):
        original = self.manifest.read_bytes()
        map_path = self.os / "support/release/organ_source_map_v4.json"
        original_map = map_path.read_bytes()
        changes = (lambda m: m["production"].update(activation="enabled"),
                   lambda m: m["production"].update(effects_authorized=True),
                   lambda m: m["production"]["unconfigured"].pop(),
                   lambda m: m.update(source_map_sha256="0" * 64),
                   lambda m: m.update(schema_version=4.0))
        for change in changes:
            manifest = json.loads(original)
            change(manifest)
            self.manifest.write_bytes(runner.profile.canonical(manifest))
            pair_tests.fixtures.commit(self.os, "tamper current declaration")
            result, output = self.run_pin_reader()
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output.exists())
        self.manifest.write_bytes(original)
        broken = json.loads(original_map)
        broken["sources"]["os"]["release_current_pair_ci"] = "different/caller.yml"
        map_path.write_bytes(runner.profile.canonical(broken))
        pair_tests.fixtures.commit(self.os, "replace a code-owned CI path")
        result, output = self.run_pin_reader()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())

    def test_pin_reader_rejects_duplicate_json_keys_and_incomplete_git_identities(self):
        original = self.manifest.read_bytes()
        duplicate = original.replace(b'"schema_version": 4', b'"schema_version": 3, "schema_version": 4')
        self.assertNotEqual(duplicate, original)
        self.manifest.write_bytes(duplicate)
        pair_tests.fixtures.commit(self.os, "duplicate the current schema field")
        result, output = self.run_pin_reader()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())
        manifest = json.loads(original)
        manifest["hepta"]["commit"] = "main"
        self.manifest.write_bytes(runner.profile.canonical(manifest))
        pair_tests.fixtures.commit(self.os, "replace complete reviewed pin with a branch name")
        result, output = self.run_pin_reader()
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(output.exists())

    def test_profile_ci_executes_current_and_all_historical_map_checks(self):
        workflow = ".github/workflows/organ-release-profile.yml"
        step = "Require inputs and validate the committed source-map schema"
        result, _ = self.run_ci_python(workflow, step)
        self.assertEqual(result.returncode, 0, result.stderr)
        for version in (1, 2, 3, 4):
            self.assertIn(f"Committed map schema {version} passed:", result.stdout)
        self.assertIn("Committed current schema4 contract passed.", result.stdout)
        manifest = json.loads(self.manifest.read_text())
        manifest["production"]["activation"] = "enabled"
        self.manifest.write_bytes(runner.profile.canonical(manifest))
        pair_tests.fixtures.commit(self.os, "activate production in a current declaration")
        result, _ = self.run_ci_python(workflow, step)
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("Committed current schema4 contract passed.", result.stdout)

    def test_actual_ci_dispatch_qualifies_only_the_v4_fixed_host_lane(self):
        args = self.current_ci_dispatch()
        with patch.object(runner.profile, "HISTORY_OWNER", self.owner), patch.object(
                runner, "execute_step", side_effect=self.execute_fixture):
            self.assertEqual(self.run_captured_pair(args), 0)
        receipt = json.loads((self.output / "pair-receipt.json").read_text())
        self.assertEqual(receipt["source"]["schema_version"], 4)
        self.assertEqual(receipt["qualification"], "host-build-tests")
        self.assertEqual(len(self.dispatched), 7)
        argv = next(step[3] for step in self.dispatched if step[0] == "hepta-tests")
        packages = [argv[i + 1] for i, value in enumerate(argv) if value == "-p"]
        self.assertEqual(len(packages), len(set(packages)))
        self.assertEqual(len(packages), 18)

    def test_actual_ci_dispatch_rejects_valid_v3_before_any_child_or_output(self):
        self.publish_manifest(3)
        args = self.current_ci_dispatch()
        with patch.object(runner.profile, "HISTORY_OWNER", self.owner), patch.object(
                runner, "execute_step", side_effect=AssertionError("historical current input executed")):
            self.assertEqual(self.run_captured_pair(args), 1)
        self.assertFalse(self.output.exists())


class Schema4HistoricalContractTests(unittest.TestCase):
    def test_fixed_v4_map_has_distinct_real_os_sources(self):
        mapping = profile.load_json(HERE / "organ_source_map_v4.json")
        profile.check_map(mapping)
        repo = profile.Repository(HERE.parents[1], "os")
        for role, path in mapping["sources"]["os"].items():
            with self.subTest(role=role):
                repo.file(path)

    def test_previous_current_archive_keeps_the_real_v3_bytes(self):
        path = HERE / "profiles/2026-10-26-organ-source-1138-f397-v3.json"
        self.assertEqual(profile.sha256(path.read_bytes()),
                         "805fdc48788d467d3eef27f4f573ee441d3250258e019f3e67a2c60336e77e3f")
        manifest = profile.load_json(path)
        self.assertEqual(manifest["schema_version"], 3)
        self.assertEqual(manifest["hepta"]["commit"], "f397005492549817d4851ea2a4639a0bda16dfb7")
        self.assertEqual({row["role"] for row in manifest["sources"]["os"]}, profile.OS_ROLES_V3)
        self.assertEqual({row["role"] for row in manifest["sources"]["hepta"]}, profile.HEPTA_ROLES_V3)

    def test_every_mapped_source_path_can_trigger_the_current_pair_ci(self):
        workflow = (HERE.parents[1] / ".github/workflows/organ-current-pair.yml").read_text()
        groups = re.findall(r"    paths:\n((?:      - [^\n]+\n)+)", workflow)
        self.assertEqual(len(groups), 2)
        mapping = profile.load_json(HERE / "organ_source_map_v4.json")
        for group in groups:
            patterns = [json.loads('"' + line.split("'", 2)[1] + '"') for line in group.splitlines()]
            for role, path in mapping["sources"]["os"].items():
                with self.subTest(role=role):
                    self.assertTrue(any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns), path)

    def test_legacy_role_maps_archives_and_host_commands_keep_exact_contracts(self):
        # Literal values exported from the real frozen CAB Git objects. Keep
        # historical acceptance data and dispatch independent of V4 additions.
        expected = LEGACY_CONTRACT
        roles = {str(v): {"os": sorted(profile.roles_for_version(v)[0]),
                          "hepta": sorted(profile.roles_for_version(v)[1]),
                          "goldens": sorted(profile.roles_for_version(v)[2])} for v in (1, 2, 3)}
        self.assertEqual(profile.sha256(profile.canonical(roles)), expected["roles_sha256"])
        for path, digest in expected["maps_sha256"].items():
            self.assertEqual(profile.sha256((HERE / path).read_bytes()), digest)
        for path, digest in expected["archives_sha256"].items():
            self.assertEqual(profile.sha256((HERE.parents[1] / path).read_bytes()), digest)
        for version in (1, 2, 3):
            for offline in (False, True):
                for build_profile in ("dev-small", "dev"):
                    steps = runner.host_steps(Path("/os-source"), Path("/hepta-source"), offline,
                                              build_profile, version)
                    raw = (json.dumps(steps, default=str, sort_keys=True, indent=2) + "\n").encode()
                    self.assertEqual(hashlib.sha256(raw).hexdigest(),
                                     expected["dispatch_sha256"][f"{version}:{offline}:{build_profile}"])
        self.assertEqual(profile.HISTORY_OWNER, expected["history_owner"])
        self.assertEqual(profile.GOLDEN_ROLES_V4, profile.GOLDEN_ROLES_V3)
        legacy = profile.load_json(HERE / "organ_source_map_v3.json")
        current = profile.load_json(HERE / "organ_source_map_v4.json")
        migration_prefix = "codex-rs/hepta-automation/migrations/"
        migration_sources = lambda mapping: {
            role: path for role, path in mapping["sources"]["hepta"].items()
            if path.startswith(migration_prefix) and path.endswith(".sql")}
        self.assertEqual(len(migration_sources(legacy)), 19)
        self.assertEqual(migration_sources(current), migration_sources(legacy))


# Inserted from frozen CAB export, never from current runtime acceptance.
LEGACY_CONTRACT = {'archives_sha256': {'support/release/profiles/2026-10-22-organ-source.json': '260139110c06921db6a156c1f072c55d0a3218f4b8da523b509adad4471e5667',
                     'support/release/profiles/2026-10-25-organ-source-v1.json': 'a7625c0d629761994e2730a552476323ab1eafe98c587fd6f0306d3a10be8f9f',
                     'support/release/profiles/2026-10-26-organ-source-699b-f79c-v3.json': 'f8d8cd57ea92a2d8ca35706a182ee9cd1344bccde3022bd03bf3347b8576dc40',
                     'support/release/profiles/2026-10-26-organ-source-8542-fef6-v3.json': 'd76299cd6fa63f7e1fa3de21e850f696986d6348094706ac727aa3f92e10eed4',
                     'support/release/profiles/2026-10-26-organ-source-d253-e537-v3.json': '8f8096b6eab9d2c7967a1c47f191b6bd43e35d3e69b6c92cd8ea17f6c430b8e9'},
 'base': 'cab93cfb2a7c5e3dddd67e63895cb5a86ff2eb33',
 'counts': {'1': [23, 20, 4], '2': [41, 43, 5], '3': [274, 146, 5]},
 'dispatch_sha256': {'1:False:dev': '0506a9d53ee445966c9ff794aad81f82878f8b036168755409f442969c9ad3df',
                     '1:False:dev-small': '54370bb214845c652f105f89d849e04c1709a27488df7d0719f90d88af66f109',
                     '1:True:dev': 'd21d7848c57ee2e838751f26b351bbfd95c5bb2bffd6bdab120f36c73bd783a1',
                     '1:True:dev-small': 'e513acfe47a39cf50cdbe00383fc636ec41dd12082c434decd193acacd3b3201',
                     '2:False:dev': '0506a9d53ee445966c9ff794aad81f82878f8b036168755409f442969c9ad3df',
                     '2:False:dev-small': '54370bb214845c652f105f89d849e04c1709a27488df7d0719f90d88af66f109',
                     '2:True:dev': 'd21d7848c57ee2e838751f26b351bbfd95c5bb2bffd6bdab120f36c73bd783a1',
                     '2:True:dev-small': 'e513acfe47a39cf50cdbe00383fc636ec41dd12082c434decd193acacd3b3201',
                     '3:False:dev': '709b657e1ba4688827ec9e56560079c64d67c28c371e08858cea8e562ef64b57',
                     '3:False:dev-small': '1230f18e89ac9a4d2a577d68abac5471a36c121d87987191c632d038b6c6ecdb',
                     '3:True:dev': '035623e8e042a2308f7bb069f447e58a1a3e05089e0b0e92ee37c0b7f9e4f19e',
                     '3:True:dev-small': 'deb5ceb2a9a13eb1fe12ffa3319d20ab1fa9d0cca07ea20bd7201fbe93bc48b3'},
 'history_owner': '995b6fb9ef73ada7c3348b01deb28940a2c4a2d1',
 'maps_sha256': {'organ_source_map.json': 'f8807156cf493a51d4158d73640f1dd977c10d4d61a69be0db204dab3daac635',
                 'organ_source_map_v2.json': '2d3eee0787d8f0c3ea05a0a4af2eb013f44e717ab7cf855bcae4cec66de5d343',
                 'organ_source_map_v3.json': '855295047c498f98fa5afde1da79e9130ea584cddf43a72427109f784af57345'},
 'roles_sha256': '8439f89a8b3bb69cafc5868c7d59f3f567faee98a9975a9460faf6b716e7ced6'}

if __name__ == "__main__":
    unittest.main()
