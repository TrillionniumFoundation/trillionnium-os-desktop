"""Image workflow identity, producer/consumer parity and hostile source regressions."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    assert spec is not None and spec.loader is not None
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


IDENTITY = module("image_identity", "tools/image_workflow_identity.py")
SOURCE = module("image_source", "tools/validate_image_source_contract.py")
D2I = module("d2i_finalizer", "tools/finalize_d2i_evidence.py")


def context(mode: str = "exact-head") -> dict:
    return {
        "repository": IDENTITY.REPOSITORY, "event": "pull_request", "object": mode,
        "subject": "b" * 40 if mode == "exact-head" else "c" * 40, "tree": "d" * 40,
        "parents": ["e" * 40] if mode == "exact-head" else ["a" * 40, "b" * 40],
        "event_head": "b" * 40, "event_base": "a" * 40, "event_merge": "c" * 40,
        "live_head": "b" * 40, "live_base": "a" * 40, "live_merge": "c" * 40,
        "source_ref": "refs/pull/123/head",
    }


class ImageIdentityTests(unittest.TestCase):
    def test_multi_commit_candidate_does_not_require_immediate_base_parent(self) -> None:
        IDENTITY.validate_context(context())

    def test_prospective_merge_binds_ordered_event_parents(self) -> None:
        IDENTITY.validate_context(context("prospective-merge"))

    def test_each_live_ref_movement_invalidates_evidence(self) -> None:
        for field in ("live_base", "live_head", "live_merge"):
            for mode in ("exact-head", "prospective-merge"):
                with self.subTest(field=field, mode=mode):
                    value = context(mode)
                    value[field] = "f" * 40
                    with self.assertRaises(ValueError):
                        IDENTITY.validate_context(value)

    def test_wrong_subject_and_reordered_merge_parents_refused(self) -> None:
        value = context("prospective-merge")
        value["parents"].reverse()
        with self.assertRaises(ValueError):
            IDENTITY.validate_context(value)
        value = context()
        value["subject"] = "f" * 40
        with self.assertRaises(ValueError):
            IDENTITY.validate_context(value)

    def test_repository_unknown_fields_and_malformed_shas_refused(self) -> None:
        for field, bad in (("repository", "other/repo"), ("tree", "HEAD"), ("subject", "b" * 39),
                           ("event", "pull_request_target"), ("object", "unchecked"), ("extra", True)):
            with self.subTest(field=field):
                value = context()
                value[field] = bad
                with self.assertRaises(ValueError):
                    IDENTITY.validate_context(value)

    def test_non_branch_push_and_invented_merge_fields_refused(self) -> None:
        value = context()
        value.update(event="push", event_base=None, live_base=None, event_merge=None,
                     live_merge=None, source_ref="refs/heads/main")
        IDENTITY.validate_context(value)
        value["source_ref"] = "refs/heads/other"
        with self.assertRaises(ValueError):
            IDENTITY.validate_context(value)
        value["event"] = "workflow_dispatch"
        IDENTITY.validate_context(value)
        value["event_base"] = "a" * 40
        with self.assertRaises(ValueError):
            IDENTITY.validate_context(value)

    def test_pr_must_use_canonical_pull_head_ref(self) -> None:
        value = context()
        value["source_ref"] = "refs/heads/main"
        with self.assertRaises(ValueError):
            IDENTITY.validate_context(value)

    def test_actual_local_git_multi_commit_ref_and_movement(self) -> None:
        # No network or repository mutation: all Git objects/remotes are disposable local paths.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            work, remote = root / "work", root / "remote.git"
            work.mkdir()
            def git(*args: str, cwd=work, input_text=None) -> str:
                return subprocess.run(["git", *args], cwd=cwd, input=input_text,
                                      text=True, capture_output=True, check=True, timeout=10).stdout.strip()
            git("init", "-b", "main")
            git("config", "user.name", "Isolated identity test")
            git("config", "user.email", "test@example.invalid")
            for index in range(3):
                (work / "file").write_text(str(index))
                git("add", "file")
                git("commit", "-m", f"fixture {index}")
                if index == 0:
                    base = git("rev-parse", "HEAD")
            head, tree = git("rev-parse", "HEAD"), git("rev-parse", "HEAD^{tree}")
            merge = git("commit-tree", tree, "-p", base, "-p", head, input_text="test merge\n")
            git("update-ref", "refs/pull/7/merge", merge)
            git("clone", "--bare", str(work), str(remote), cwd=root)
            git("remote", "add", "origin", str(remote))
            def remote_ref(name, sha):
                git("--git-dir", str(remote), "update-ref", name, sha)
            remote_ref("refs/heads/main", base)
            remote_ref("refs/pull/7/head", head)
            remote_ref("refs/pull/7/merge", merge)
            env = {"GITHUB_REPOSITORY": IDENTITY.REPOSITORY, "GITHUB_EVENT_NAME": "pull_request",
                   "EXPECTED_HEAD": head, "EXPECTED_BASE": base, "EXPECTED_BASE_REF": "main",
                   "EXPECTED_MERGE": merge, "PR_NUMBER": "7"}
            result = IDENTITY.inspect(work, env)
            self.assertEqual(result["subject"], head)
            self.assertNotEqual(result["parents"], [base])
            git("checkout", "--detach", merge)
            env["IMAGE_OBJECT"] = "prospective-merge"
            self.assertEqual(IDENTITY.inspect(work, env)["parents"], [base, head])
            remote_ref("refs/heads/main", head)
            with self.assertRaises(ValueError):
                IDENTITY.inspect(work, env)


class EmbeddedD1ReceiptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.expected = {"repository": IDENTITY.REPOSITORY, "base_sha": "a" * 40,
                         "candidate_head_sha": "b" * 40, "tested_sha": "b" * 40,
                         "tree_sha": "c" * 40, "ref": "refs/heads/candidate",
                         "evidence_role": "manual_non_authoritative", "promotion_authoritative": False,
                         "workflow": {"path": SOURCE.WORKFLOW, "sha256": "d" * 64}}
        self.receipt = {**copy.deepcopy(self.expected),
                        "schema": "trillionnium.desktop.d1-final-qualification.v3", "status": "PASS",
                        "claim_ceiling": {key: False for key in (
                            "servo_started", "visible_window_created", "network_enabled_during_acceptance",
                            "secure_boot_qualified", "product_agent_port_enabled", "product_release_authorized")},
                        "product_fixture_separation": {
                            "product_default_graph_fixture_free": True, "product_handler_connected": False,
                            "production_install_map_contains_qualification_binary": False,
                            "qualification_feature": "fixture", "qualification_binary": "hepta-agent-d1-fixture"}}

    def test_non_object_receipt_is_rejected(self) -> None:
        for bad in (None, [], "PASS"):
            with self.assertRaises(ValueError):
                D2I.validate_embedded_d1_receipt(bad, self.expected)

    def test_current_v3_producer_status_is_accepted(self) -> None:
        D2I.validate_embedded_d1_receipt(self.receipt, self.expected)

    def test_old_or_invented_status_and_schema_are_rejected(self) -> None:
        for key, value in (("status", "PASS_D1_FINAL_QUALIFICATION"), ("status", "FAIL"),
                           ("schema", "trillionnium.desktop.d1-final-qualification.v2")):
            receipt = copy.deepcopy(self.receipt)
            receipt[key] = value
            with self.assertRaises(ValueError):
                D2I.validate_embedded_d1_receipt(receipt, self.expected)

    def test_each_source_identity_must_match(self) -> None:
        for key in ("repository", "base_sha", "candidate_head_sha", "tested_sha", "tree_sha", "ref", "evidence_role"):
            receipt = copy.deepcopy(self.receipt)
            receipt[key] = "different"
            with self.assertRaises(ValueError):
                D2I.validate_embedded_d1_receipt(receipt, self.expected)

    def test_no_authority_or_numeric_boolean_substitution(self) -> None:
        for value in (True, 0, 1, "false"):
            receipt = copy.deepcopy(self.receipt)
            receipt["promotion_authoritative"] = value
            with self.assertRaises(ValueError):
                D2I.validate_embedded_d1_receipt(receipt, self.expected)

    def test_current_workflow_digest_and_path_required(self) -> None:
        for field in ("path", "sha256"):
            receipt = copy.deepcopy(self.receipt)
            receipt["workflow"][field] = "stale"
            with self.assertRaises(ValueError):
                D2I.validate_embedded_d1_receipt(receipt, self.expected)

    def test_every_higher_claim_is_false_and_mandatory(self) -> None:
        for field in self.receipt["claim_ceiling"]:
            for value in (True, 0, "false"):
                receipt = copy.deepcopy(self.receipt)
                receipt["claim_ceiling"][field] = value
                with self.assertRaises(ValueError):
                    D2I.validate_embedded_d1_receipt(receipt, self.expected)
            receipt = copy.deepcopy(self.receipt)
            del receipt["claim_ceiling"][field]
            with self.assertRaises(ValueError):
                D2I.validate_embedded_d1_receipt(receipt, self.expected)

    def test_product_fixture_isolation_and_target_metadata_cannot_drift(self) -> None:
        for key, bad in (("product_default_graph_fixture_free", False), ("product_handler_connected", True),
                         ("production_install_map_contains_qualification_binary", True),
                         ("qualification_feature", "d1-qualification"), ("qualification_binary", "hepta-agent-portd")):
            receipt = copy.deepcopy(self.receipt)
            receipt["product_fixture_separation"][key] = bad
            with self.assertRaises(ValueError):
                D2I.validate_embedded_d1_receipt(receipt, self.expected)


class SourceReferenceTests(unittest.TestCase):
    def test_evidence_copy_supports_multiple_files_in_one_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first, second = root / "first", root / "second"
            first.write_bytes(b"first-evidence")
            second.write_bytes(b"second-evidence")
            D2I.copy_file(first, root / "artifact/qemu/first")
            D2I.copy_file(second, root / "artifact/qemu/second")
            self.assertEqual((root / "artifact/qemu/first").read_bytes(), first.read_bytes())
            self.assertEqual((root / "artifact/qemu/second").read_bytes(), second.read_bytes())

    def test_current_repository_image_sources_are_consistent(self) -> None:
        self.assertEqual(SOURCE.validate(ROOT), [])

    def test_hostile_source_mutations_fail(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = set(SOURCE.CONSUMERS) | {SOURCE.WORKFLOW, "manifests/gates.v1.json"}
            for relative in paths:
                destination = root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes((ROOT / relative).read_bytes())
            self.assertEqual(SOURCE.validate(root), [])
            for relative in SOURCE.CONSUMERS:
                target = root / relative
                original = target.read_text()
                target.write_text(original.replace(SOURCE.WORKFLOW, SOURCE.OBSOLETE[0]))
                self.assertTrue(SOURCE.validate(root))
                target.write_text(original)
            target = root / SOURCE.WORKFLOW
            original = target.read_text()
            for mutation in (original.replace("  pull_request:", "  pull_request:\n    paths: [docs/**]"),
                             original.replace("contents: read", "contents: write"),
                             original.replace("needs: source-contracts", "needs: missing")):
                target.write_text(mutation)
                self.assertTrue(SOURCE.validate(root))
            target.write_text(original)
            gate_path = root / "manifests/gates.v1.json"
            gates = json.loads(gate_path.read_text())
            for gate in gates["gates"]:
                if gate["id"] == "D1-01":
                    gate["invalidation_paths"].remove("crates/**")
            gate_path.write_text(json.dumps(gates))
            self.assertTrue(SOURCE.validate(root))


if __name__ == "__main__":
    unittest.main()
