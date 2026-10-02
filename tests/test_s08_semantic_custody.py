from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import tempfile
import unittest
from pathlib import Path

from tools import verify_s08_semantic_custody as verifier

ROOT = Path(__file__).resolve().parents[1]


class S08SemanticCustodySourceTests(unittest.TestCase):
    def copied(self) -> Path:
        temporary = tempfile.TemporaryDirectory(prefix="s08-semantic-source-test-")
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        paths = [verifier.MANIFEST, verifier.PATCH, verifier.PREREQUISITE,
                 "experiments/servo-s08-runtime/semantic-source-check/Cargo.toml",
                 "experiments/servo-s08-runtime/semantic-source-check/Cargo.lock"]
        for relative in paths:
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / relative, path)
        return root

    def mutate_manifest(self, root: Path, change) -> None:
        path = root / verifier.MANIFEST
        value = json.loads(path.read_text())
        change(value)
        path.write_text(json.dumps(value) + "\n")

    def test_current_source_profile_is_closed(self) -> None:
        manifest, parsed = verifier.verify(ROOT)
        self.assertEqual(list(parsed), verifier.ALLOWED_PATHS)
        self.assertEqual(manifest["original_stimulus"], verifier.ORIGINAL_STIMULUS)

    def test_bounds_version_and_boolean_aliases_refuse(self) -> None:
        for key, value in [("version", True), ("version", 1.0), ("version", 2),
                           ("maximum_name_bytes", 1024.0), ("maximum_name_bytes", 2048),
                           ("maximum_ancestry_nodes", 17)]:
            with self.subTest(key=key, value=value):
                root = self.copied()
                self.mutate_manifest(root, lambda m: m["semantic_schema"].__setitem__(key, value))
                with self.assertRaises(ValueError): verifier.verify(root)

    def test_original_request_receipt_click_gates_cannot_shrink(self) -> None:
        for key, value in [("agentport_requests", 9), ("servo_commands", 8),
                           ("durable_receipt_facts", 29), ("positive_dom_clicks", True),
                           ("s07_patch_and_test_bodies_unchanged", False)]:
            root = self.copied()
            self.mutate_manifest(root, lambda m: m["original_stimulus"].__setitem__(key, value))
            with self.assertRaises(ValueError): verifier.verify(root)

    def test_no_source_or_installed_authority_promotion(self) -> None:
        for key in ["source_fixtures_are_servo_proof", "installed_product_activation",
                    "final_script_peer_control_custody", "external_effect_authority", "release"]:
            root = self.copied()
            self.mutate_manifest(root, lambda m: m["claim_ceiling"].__setitem__(key, True))
            with self.assertRaises(ValueError): verifier.verify(root)

    def test_closed_manifest_duplicate_and_unknown_fields_refuse(self) -> None:
        root = self.copied()
        self.mutate_manifest(root, lambda m: m.__setitem__("caller_verified", True))
        with self.assertRaises(ValueError): verifier.verify(root)
        root = self.copied()
        path = root / verifier.MANIFEST
        path.write_text(path.read_text().replace('"schema":', '"schema":"duplicate", "schema":', 1))
        with self.assertRaises(ValueError): verifier.verify(root)

    def test_nested_profile_shapes_and_pinned_dependency_mutations_refuse(self) -> None:
        for key, value in [("patch", None), ("patch", [[]]), ("standalone_source_check", []),
                           ("semantic_schema", 1), ("required_negative_cases", {})]:
            root = self.copied()
            self.mutate_manifest(root, lambda m: m.__setitem__(key, value))
            with self.assertRaises(ValueError): verifier.verify(root)
        root = self.copied()
        path = root / "experiments/servo-s08-runtime/semantic-source-check/Cargo.toml"
        path.write_text(path.read_text().replace('sha2="=0.11.0"', 'sha2="=0.10.9"'))
        self.mutate_manifest(root, lambda m: m["standalone_source_check"].__setitem__("manifest_sha256", hashlib.sha256(path.read_bytes()).hexdigest()))
        with self.assertRaises(ValueError): verifier.verify(root)

    def test_patch_rebinding_cannot_add_redirect_or_undeclared_path(self) -> None:
        for before, after in [("+++ b/components/servo/webview.rs", "+++ b/components/servo/other.rs"),
                              ("a/Cargo.lock b/Cargo.lock", "a/Cargo.lock b/../outside")]:
            root = self.copied()
            patch = root / verifier.PATCH
            patch.write_text(patch.read_text().replace(before, after, 1))
            self.mutate_manifest(root, lambda m: m["patch"].__setitem__("sha256", hashlib.sha256(patch.read_bytes()).hexdigest()))
            with self.assertRaises(ValueError): verifier.verify(root)

    def test_bound_mutation_rehashed_patch_still_refuses(self) -> None:
        root = self.copied()
        patch = root / verifier.PATCH
        patch.write_text(patch.read_text().replace("MAX_ACCESSIBILITY_NAME_BYTES: usize = 1024", "MAX_ACCESSIBILITY_NAME_BYTES: usize = 2048"))
        module = verifier.apply_exact(None, verifier.parse_patch(patch.read_bytes())["components/shared/base/accessibility_semantics.rs"])
        def rebind(m):
            m["patch"]["sha256"] = hashlib.sha256(patch.read_bytes()).hexdigest()
            for row in m["patch"]["source_pins"]:
                if row["path"].endswith("/accessibility_semantics.rs"):
                    row["semantic_sha256"] = hashlib.sha256(module).hexdigest()
        self.mutate_manifest(root, rebind)
        with self.assertRaises(ValueError): verifier.verify(root)

    def test_final_comparison_removed_rehash_refuses(self) -> None:
        root = self.copied()
        patch = root / verifier.PATCH
        patch.write_text(patch.read_text().replace("if current != expected", "if false"))
        self.mutate_manifest(root, lambda m: m["patch"].__setitem__("sha256", hashlib.sha256(patch.read_bytes()).hexdigest()))
        with self.assertRaises(ValueError): verifier.verify(root)

    def test_exact_transformer_rejects_offset_context_and_count_drift(self) -> None:
        source = b"alpha\nbeta\n"
        good = ["@@ -1,2 +1,2 @@\n", " alpha\n", "-beta\n", "+gamma\n"]
        self.assertEqual(verifier.apply_exact(source, good), b"alpha\ngamma\n")
        for changed in [["@@ -2,2 +1,2 @@\n", *good[1:]],
                        [good[0], " unknown\n", *good[2:]],
                        ["@@ -1,3 +1,2 @@\n", *good[1:]],
                        ["@@ -1,2 +2,2 @@\n", *good[1:]]]:
            with self.assertRaises(ValueError): verifier.apply_exact(source, changed)

    def test_real_path_custody_rejects_symlink_hardlink_and_fifo(self) -> None:
        for kind in ("symlink", "hardlink", "fifo"):
            root = self.copied()
            path = root / verifier.PATCH
            original = path.read_bytes()
            path.unlink()
            victim = root / "outside"
            victim.write_bytes(original)
            if kind == "symlink": path.symlink_to(victim)
            elif kind == "hardlink": os.link(victim, path)
            else: os.mkfifo(path, 0o600)
            with self.assertRaises((ValueError, OSError)): verifier.verify(root)
            self.assertTrue(stat.S_ISREG(victim.stat().st_mode))
            self.assertEqual(victim.read_bytes(), original)

    def result(self) -> dict:
        return {"schema": "trillionnium.desktop.s08-semantic-result.v1", "servo_commit": verifier.PIN,
                "case_count": 7, "cases": [{"case": c, "refusal": r, "dom_click_count": 0}
                                             for c, r in verifier.NEGATIVES.items()],
                "final_same_script_task_check": True, "installed_image_proven": False,
                "final_peer_control_custody_proven": False}

    def write_result(self, value: dict) -> Path:
        root = self.copied()
        path = root / "semantic-result.json"
        path.write_text(json.dumps(value) + "\n")
        return path

    def test_complete_result_fixture_is_only_parser_evidence(self) -> None:
        verifier.verify_result(self.write_result(self.result()))

    def test_actual_result_negative_gate_types_counts_and_claims(self) -> None:
        for key, value in [("case_count", 7.0), ("case_count", True),
                           ("final_same_script_task_check", 1), ("installed_image_proven", True),
                           ("final_peer_control_custody_proven", True)]:
            document = self.result(); document[key] = value
            with self.assertRaises(ValueError): verifier.verify_result(self.write_result(document))
        for value in [False, 0.0, 1]:
            document = self.result(); document["cases"][0]["dom_click_count"] = value
            with self.assertRaises(ValueError): verifier.verify_result(self.write_result(document))

    def test_actual_result_missing_case_wrong_refusal_and_extra_field(self) -> None:
        for change in [lambda m: m["cases"].pop(),
                       lambda m: m["cases"][0].__setitem__("refusal", "Dispatched"),
                       lambda m: m["cases"][0].__setitem__("caller_checked", True),
                       lambda m: m.__setitem__("runtime_proven", True)]:
            document = self.result(); change(document)
            with self.assertRaises(ValueError): verifier.verify_result(self.write_result(document))

    def test_real_result_byte_bound_and_duplicate_field_refuse(self) -> None:
        path = self.write_result(self.result())
        path.write_bytes(path.read_bytes() + b" " * verifier.MAX_RESULT_BYTES)
        with self.assertRaises(ValueError): verifier.verify_result(path)
        path = self.write_result(self.result())
        path.write_text(path.read_text().replace('"case_count": 7', '"case_count": 7, "case_count": 7', 1))
        with self.assertRaises(ValueError): verifier.verify_result(path)

    def test_original_s07_patch_and_test_parts_are_unmodified(self) -> None:
        manifest = json.loads((ROOT / verifier.PREREQUISITE).read_text())
        for section in [manifest["patch"], manifest["hardening"]]:
            for row in section["parts"]:
                self.assertEqual(hashlib.sha256((ROOT / row["path"]).read_bytes()).hexdigest(), row["sha256"])

    def test_workflow_requires_pristine_exact_pin_and_all_runtime_corpora(self) -> None:
        text = (ROOT / ".github/workflows/s08-servo-vertical-slice.yml").read_text()
        for marker in ["verify_s08_semantic_custody.py --check-upstream servo", "--fuzz=0",
                       "test_retained_accessibility", "HEPTA_S08_SEMANTIC_RESULTS",
                       "--result", "real_servo_agent_port_browser_actor_receipt_chain",
                       '"agent_port_requests": 10', '"servo_commands": 9',
                       '"durable_receipt_records": 30',
                       "refs/pull/${{ github.event.pull_request.number }}/merge"]:
            self.assertIn(marker, text)


if __name__ == "__main__":
    unittest.main()
