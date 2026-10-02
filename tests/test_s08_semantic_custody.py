from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import textwrap
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
        prerequisite = json.loads((ROOT / verifier.PREREQUISITE).read_text())
        paths = [verifier.MANIFEST, verifier.PATCH, verifier.PREREQUISITE,
                 verifier.ADAPTER, verifier.WORKFLOW,
                 "experiments/servo-s08-runtime/semantic-source-check/Cargo.toml",
                 "experiments/servo-s08-runtime/semantic-source-check/Cargo.lock"]
        paths += [row["path"] for section in ("patch", "hardening")
                  for row in prerequisite[section]["parts"]]
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

    def test_closed_process_owner_profile_rejects_aliases_omission_and_claims(self) -> None:
        for key, value in [("fresh_process_per_retained_test", 1),
                           ("exact_filter_from_actual_list", False),
                           ("expected_tests_per_retained_process", True),
                           ("semantic_servo_owners", 1.0), ("semantic_servo_owners", 7),
                           ("semantic_webviews", 6), ("retained_test_names", verifier.RETAINED_TESTS[:-1]),
                           ("actual_servo_proven", True)]:
            with self.subTest(key=key, value=value):
                root = self.copied()
                self.mutate_manifest(root, lambda m: m["runtime_corpus"].__setitem__(key, value))
                with self.assertRaises(ValueError): verifier.verify(root)

    def rebind_runtime_source(self, root: Path, key: str, before: str, after: str) -> None:
        path = root / (verifier.ADAPTER if key == "adapter" else verifier.WORKFLOW)
        text = path.read_text()
        self.assertIn(before, text)
        path.write_text(text.replace(before, after, 1))
        self.mutate_manifest(root, lambda m: m["runtime_corpus"].__setitem__(key + "_sha256", hashlib.sha256(path.read_bytes()).hexdigest()))

    def test_rebound_semantic_source_cannot_reconstruct_or_select_owner_cases(self) -> None:
        for before, after in [
            ("let servo_test = build_test();\n    let cases", "let servo_test = build_test();\n    let second = build_test();\n    let cases"),
            ("s08_build_webview_and_tree(&servo_test, url)", "build_webview_and_tree(url)"),
            ("let delegate = Rc::new(WebViewDelegateImpl::default());", "let extra = build_test();\n    let delegate = Rc::new(WebViewDelegateImpl::default());"),
            ('"same_node_label",', '"omitted_label_case",'),
            ('let cases = [', 'let selected = std::env::var_os("CASE");\n    let cases = ['),
            ('"real DOM must retain zero epoch clicks"', '"fixture result is enough"'),
        ]:
            root = self.copied()
            self.rebind_runtime_source(root, "adapter", before, after)
            with self.assertRaises(ValueError): verifier.verify(root)

    def test_original_product_body_and_all_s07_parts_cannot_change(self) -> None:
        root = self.copied()
        self.rebind_runtime_source(root, "adapter", 'let mut click_count = 0_u64;', 'let mut click_count = 1_u64;')
        with self.assertRaises(ValueError): verifier.verify(root)
        root = self.copied()
        prerequisite = json.loads((root / verifier.PREREQUISITE).read_text())
        part = root / prerequisite["hardening"]["parts"][-1]["path"]
        part.write_bytes(part.read_bytes() + b"\n")
        with self.assertRaises(ValueError): verifier.verify(root)

    def test_rebound_workflow_cannot_group_skip_or_prefix_filter_originals(self) -> None:
        for before, after in [
            ('"${retained_tests[$index]}" -- --exact --nocapture', '"${retained_tests[$index]}" -- --nocapture'),
            ('for index in "${!retained_tests[@]}"; do', 'for index in 0; do'),
            ('test "${#retained_tests[@]}" -eq 6', 'test "${#retained_tests[@]}" -eq 5'),
            ('--retained-list "$retained/list.txt" --print-retained-names', '--print-retained-names'),
            ('test_trillionnium_s08_semantic_custody -- --exact --nocapture', 'test_trillionnium_s08_semantic_custody -- --nocapture'),
        ]:
            root = self.copied()
            self.rebind_runtime_source(root, "workflow", before, after)
            with self.assertRaises(ValueError): verifier.verify(root)

    def retained_fixture(self, prefix: str = "") -> tuple[Path, Path, list[str]]:
        # Only parser fixtures; these log strings do not establish any Servo execution.
        root = self.copied()
        names = [prefix + name for name in verifier.RETAINED_TESTS]
        listed = names + [prefix + verifier.SEMANTIC_TEST, prefix + "another_test"]
        listing = root / "list.txt"
        listing.write_text("\n".join(name + ": test" for name in listed) + "\n\n8 tests, 0 benchmarks\n")
        logs = root / "retained"
        logs.mkdir(mode=0o700)
        for index, name in enumerate(names):
            (logs / f"case-{index}.log").write_text(f"running 1 test\ntest {name} ... ok\n\ntest result: ok. 1 passed; 0 failed; 0 ignored; 0 measured; 7 filtered out; finished in 0.01s\n")
        return listing, logs, names

    def test_actual_inventory_uses_full_names_and_requires_exact_unique_corpus(self) -> None:
        listing, logs, names = self.retained_fixture("actual_module::")
        self.assertEqual(verifier.retained_inventory(listing), (names, 8))
        verifier.verify_retained_results(listing, logs)
        original = listing.read_text()
        for text in [original.replace(names[0] + ": test\n", ""),
                     original.replace(names[0] + ": test", names[1] + ": test"),
                     original.replace("8 tests", "7 tests"),
                     original.replace("actual_module::" + verifier.SEMANTIC_TEST, "other_semantic_test"),
                     original.replace(names[0], "actual_module::test_retained_accessibility_extra"),
                     original + "caller verified=true\n"]:
            listing.write_text(text)
            with self.assertRaises(ValueError): verifier.retained_inventory(listing)

    def test_retained_logs_refuse_zero_match_ignored_wrong_filter_and_duplicate_pass(self) -> None:
        listing, logs, names = self.retained_fixture()
        path = logs / "case-0.log"
        original = path.read_text()
        for text in [original.replace("running 1 test", "running 0 tests").replace("1 passed", "0 passed"),
                     original.replace(names[0], names[1]),
                     original.replace("... ok", "... ignored"),
                     original.replace("7 filtered out", "6 filtered out"),
                     original + original,
                     original.replace("running 1 test", "running 2 tests")]:
            path.write_text(text)
            with self.assertRaises(ValueError): verifier.verify_retained_results(listing, logs)
        path.write_text(original)
        (logs / "case-5.log").unlink()
        with self.assertRaises((ValueError, OSError)): verifier.verify_retained_results(listing, logs)

    def test_retained_inventory_and_logs_use_real_nofollow_bounded_reads(self) -> None:
        for kind in ("symlink", "hardlink", "fifo", "ancestor"):
            listing, logs, _ = self.retained_fixture()
            path = logs / "case-0.log"
            data = path.read_bytes()
            victim = listing.parent / "victim"
            victim.write_bytes(data)
            if kind == "ancestor":
                moved = logs.with_name("original-logs")
                logs.rename(moved)
                logs.symlink_to(moved, target_is_directory=True)
            else:
                path.unlink()
                if kind == "symlink": path.symlink_to(victim)
                elif kind == "hardlink": os.link(victim, path)
                else: os.mkfifo(path, 0o600)
            with self.assertRaises((ValueError, OSError)): verifier.verify_retained_results(listing, logs)
            self.assertEqual(victim.read_bytes(), data)
        listing, _, _ = self.retained_fixture()
        listing.write_bytes(b"x" * (verifier.MAX_SOURCE_BYTES + 1))
        with self.assertRaises(ValueError): verifier.retained_inventory(listing)

    def test_actual_libtest_process_fixture_reproduces_once_owner_and_separate_processes(self) -> None:
        # Real Rust processes and OnceLock, without Servo or original retained test bodies.
        # This verifies libtest names/counts and isolation, not browser semantics.
        version = subprocess.check_output(["rustc", "--version"], text=True, timeout=20).strip()
        self.assertEqual(version, "rustc 1.93.0 (254b59607 2026-01-19)")
        root = self.copied()
        source = root / "process_fixture.rs"
        source.write_text('use std::sync::OnceLock;\nstatic OWNER: OnceLock<()> = OnceLock::new();\n'
                          'fn acquire() { OWNER.set(()).expect("Already initialized"); }\n'
                          + "".join(f"#[test]\nfn {name}() {{ acquire(); }}\n" for name in verifier.RETAINED_TESTS)
                          + f"#[test]\nfn {verifier.SEMANTIC_TEST}() {{}}\n")
        executable = root / "process_fixture"
        subprocess.run(["rustc", "--edition=2024", "--test", str(source), "-o", str(executable)], capture_output=True, check=True, timeout=30)
        grouped = subprocess.run([str(executable), "test_retained_accessibility", "--test-threads=1"], capture_output=True, text=True, timeout=10)
        self.assertEqual(grouped.returncode, 101)
        self.assertIn("1 passed; 5 failed; 0 ignored", grouped.stdout)
        self.assertIn("Already initialized", grouped.stdout)
        listing = root / "list.txt"
        listing.write_bytes(subprocess.check_output([str(executable), "--list"], timeout=10))
        names, count = verifier.retained_inventory(listing)
        self.assertEqual((names, count), (verifier.RETAINED_TESTS, 7))
        for index, name in enumerate(names):
            result = subprocess.run([str(executable), name, "--exact", "--nocapture"], capture_output=True, timeout=10)
            self.assertEqual(result.returncode, 0)
            (root / f"case-{index}.log").write_bytes(result.stdout + result.stderr)
        verifier.verify_retained_results(listing, root)

    def ci_body(self) -> str:
        workflow = (ROOT / verifier.WORKFLOW).read_text()
        step = workflow.split("      - name: Validate bounded S08 results\n", 1)[1].split("      - name:", 1)[0]
        match = re.search(r"(?ms)^          python3 .* <<'PY'\n(.*?)^          PY$", step)
        self.assertIsNotNone(match)
        return textwrap.dedent(match[1])

    def ci_fixture(self) -> dict[str, dict]:
        # Complete result-parser fixtures; these are not a Servo producer or run.
        return {
            "s08-product-result.json": {
                "schema": "trillionnium.desktop.s08-product-result.v1",
                "status": "PASS_REAL_SERVO_AGENTPORT_BROWSERACTOR_RECEIPT_CHAIN",
                "agent_port_requests": 10, "servo_runtime_commands": 9, "durable_receipt_records": 30,
                "all_responses_committed": True, "unresolved_receipts": 0,
                "stale_document_rejected": True, "retained_node_click_exactly_once": True,
                "peer_identity_redacted": True, "production_agent_port_enabled": False,
                "installed_image_proven": False, "physical_hardware_proven": False, "release_proven": False,
            },
            "s08-servo-result.json": {
                "schema": "trillionnium.desktop.s08-servo-host-result.v1", "status": "PASS_EXACT_PIN_REAL_SERVO",
                "servo_commands": 9, "servo_navigation_count": 2,
                "retained_node_click_dispatched_exactly_once": True, "external_navigation_enabled": False,
                "installed_image_proven": False, "physical_hardware_proven": False, "release_proven": False,
            },
        }

    def run_ci_body(self, documents: dict[str, dict]) -> subprocess.CompletedProcess:
        with tempfile.TemporaryDirectory(prefix="s08-actual-ci-body-") as directory:
            for name, document in documents.items():
                (Path(directory) / name).write_text(json.dumps(document) + "\n")
            return subprocess.run([sys.executable, "-B", "-c", self.ci_body(), directory],
                                  capture_output=True, text=True, timeout=10)

    def test_actual_extracted_ci_body_requires_exact_scalar_types(self) -> None:
        self.assertEqual(self.run_ci_body(self.ci_fixture()).returncode, 0)
        for name, original in self.ci_fixture().items():
            for key, value in original.items():
                if type(value) is bool:
                    replacements = [int(value), float(value)]
                elif type(value) is int:
                    replacements = [float(value), True, False]
                else:
                    replacements = [0, True, None]
                for replacement in replacements:
                    with self.subTest(name=name, field=key, replacement=replacement):
                        documents = self.ci_fixture(); documents[name][key] = replacement
                        result = self.run_ci_body(documents)
                        self.assertNotEqual(result.returncode, 0, (name, key, replacement, result.stdout))
                        self.assertIn("exact scalar type required", result.stderr)

    def test_actual_extracted_ci_body_refuses_missing_and_unknown_flat_fields(self) -> None:
        for name, original in self.ci_fixture().items():
            for key in original:
                with self.subTest(name=name, missing=key):
                    documents = self.ci_fixture(); documents[name].pop(key)
                    result = self.run_ci_body(documents)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn("closed fields required", result.stderr)
            documents = self.ci_fixture(); documents[name]["caller_verified"] = True
            result = self.run_ci_body(documents)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("closed fields required", result.stderr)

    def test_rebound_workflow_cannot_omit_or_defer_ci_type_guards(self) -> None:
        for before, after in [
            ('if type(value[key]) is not type(expected_value):', 'if False:'),
            ('if set(value) != set(expected):', 'if False:'),
            ('require_scalar_types(product, expected_product, "product")', '# removed product guard'),
            ('require_scalar_types(servo, required_servo, "Servo")', '# removed Servo guard'),
            ('          require_scalar_types(product, expected_product, "product")\n          if product != expected_product:\n              raise SystemExit(f"unexpected product result: {product!r}")',
             '          if product != expected_product:\n              raise SystemExit(f"unexpected product result: {product!r}")\n          require_scalar_types(product, expected_product, "product")'),
        ]:
            root = self.copied()
            self.rebind_runtime_source(root, "workflow", before, after)
            with self.assertRaises(ValueError): verifier.verify(root)


if __name__ == "__main__":
    unittest.main()
