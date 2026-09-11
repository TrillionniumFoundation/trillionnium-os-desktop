from __future__ import annotations

import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests/lab-d3-servo-retained-node-action.v1.json"
VERIFIER = ROOT / "tools/verify_d3_servo_patch.py"
SECTIONS = ("patch", "hardening", "transport_hardening")
PART_PATHS = [
    f"manifests/servo-patches/d3-retained-node-action-v1/{index:03d}.patch"
    for index in range(9)
]
EXPECTED_CHANGED_PATHS = {
    "Cargo.lock",
    "components/constellation/constellation.rs",
    "components/constellation/tracing.rs",
    "components/layout/accessibility_tree.rs",
    "components/layout/layout_impl.rs",
    "components/paint/painter.rs",
    "components/script/Cargo.toml",
    "components/script/event_loop/script_thread.rs",
    "components/script/messaging.rs",
    "components/servo/lib.rs",
    "components/servo/proxies.rs",
    "components/servo/tests/accessibility.rs",
    "components/servo/webview.rs",
    "components/shared/constellation/Cargo.toml",
    "components/shared/constellation/lib.rs",
    "components/shared/layout/Cargo.toml",
    "components/shared/layout/lib.rs",
    "components/shared/script/lib.rs",
    "ports/servoshell/desktop/headed_window.rs",
}

SPEC = importlib.util.spec_from_file_location("verify_d3_servo_patch", VERIFIER)
assert SPEC is not None and SPEC.loader is not None
PATCH_VERIFIER = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = PATCH_VERIFIER
SPEC.loader.exec_module(PATCH_VERIFIER)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def concatenate(parts: list[bytes]) -> bytes:
    output = bytearray()
    for index, part in enumerate(parts):
        if index and output and not output.endswith(b"\n"):
            output.extend(b"\n")
        output.extend(part)
    return bytes(output)


class S07ServoPatchPackageTests(unittest.TestCase):
    def load_manifest(self) -> dict:
        return PATCH_VERIFIER.load_json(MANIFEST)

    @staticmethod
    def records(manifest: dict) -> list[dict]:
        return [item for name in SECTIONS for item in manifest[name]["parts"]]

    def section_bytes(self, manifest: dict, name: str, root: Path = ROOT) -> bytes:
        return b"".join((root / item["path"]).read_bytes() for item in manifest[name]["parts"])

    def package_bytes(self, manifest: dict, root: Path = ROOT) -> bytes:
        return concatenate([self.section_bytes(manifest, name, root) for name in SECTIONS])

    def copy_package(self, manifest: dict, root: Path) -> None:
        for record in self.records(manifest):
            destination = root / record["path"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes((ROOT / record["path"]).read_bytes())

    def run_verifier(
        self,
        *,
        output: Path,
        manifest: Path = MANIFEST,
        root: Path = ROOT,
        base_output: Path | None = None,
        hardening_output: Path | None = None,
        transport_output: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            sys.executable,
            str(VERIFIER),
            "--manifest",
            str(manifest),
            "--root",
            str(root),
            "--output",
            str(output),
        ]
        for flag, value in (
            ("--base-output", base_output),
            ("--hardening-output", hardening_output),
            ("--transport-hardening-output", transport_output),
        ):
            if value is not None:
                command.extend((flag, str(value)))
        return subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)

    def test_manifest_schema_parts_digests_and_allowlist_are_exact(self) -> None:
        manifest = self.load_manifest()
        self.assertEqual(set(manifest["patch"]), {"sha256", "parts", "purpose", "allowed_paths"})
        self.assertEqual(set(manifest["hardening"]), {"sha256", "parts", "purpose"})
        self.assertEqual(set(manifest["transport_hardening"]), {"sha256", "parts", "purpose"})
        self.assertEqual([item["path"] for item in self.records(manifest)], PART_PATHS)
        self.assertIn("file-disjoint", manifest["hardening"]["purpose"])
        self.assertIn("first-hop", manifest["transport_hardening"]["purpose"])

        for name in SECTIONS:
            combined = self.section_bytes(manifest, name)
            self.assertEqual(digest(combined), manifest[name]["sha256"], name)
            for record in manifest[name]["parts"]:
                self.assertEqual(
                    digest((ROOT / record["path"]).read_bytes()),
                    record["sha256"],
                    record["path"],
                )
        package = self.package_bytes(manifest)
        self.assertEqual(set(PATCH_VERIFIER.changed_paths(package)), EXPECTED_CHANGED_PATHS)
        self.assertEqual(set(manifest["patch"]["allowed_paths"]), EXPECTED_CHANGED_PATHS)

    def test_verifier_materializes_exact_ordered_package(self) -> None:
        manifest = self.load_manifest()
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            output = work / "combined.patch"
            base = work / "base.patch"
            hardened = work / "hardened.patch"
            transport = work / "transport.patch"
            result = self.run_verifier(
                output=output,
                base_output=base,
                hardening_output=hardened,
                transport_output=transport,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            record = json.loads(result.stdout)
            base_bytes = self.section_bytes(manifest, "patch")
            hardening_bytes = self.section_bytes(manifest, "hardening")
            transport_bytes = self.section_bytes(manifest, "transport_hardening")
            self.assertEqual(base.read_bytes(), base_bytes)
            self.assertEqual(transport.read_bytes(), transport_bytes)
            self.assertEqual(hardened.read_bytes(), concatenate([hardening_bytes, transport_bytes]))
            self.assertEqual(output.read_bytes(), concatenate([base_bytes, hardening_bytes, transport_bytes]))
            self.assertEqual(record["sha256"], digest(output.read_bytes()))
            self.assertEqual(set(record["changed_paths"]), EXPECTED_CHANGED_PATHS)

    def test_retained_node_and_first_hop_semantics_are_path_aware(self) -> None:
        additions = PATCH_VERIFIER.added_lines_by_path(self.package_bytes(self.load_manifest()))
        code = {
            path: PATCH_VERIFIER.strip_rust_comments(text)
            for path, text in additions.items()
            if path.endswith(".rs")
        }
        layout = code["components/layout/accessibility_tree.rs"]
        for pattern in (
            r"\bfn\s+action_target_for_id\s*\(",
            r"self\.nodes\.get\s*\(\s*&node_id\s*\)\s*\?",
            r"supports_action\s*\(\s*action\s*\)",
            r"bounds\s*\(\s*\)\.is_some\s*\(\s*\)",
        ):
            self.assertRegex(layout, pattern)

        script = code["components/script/event_loop/script_thread.rs"]
        guards = code["components/constellation/constellation.rs"] + "\n" + script
        self.assertRegex(guards, r"request\.target_tree\s*==\s*(?:accesskit::)?TreeId::ROOT")
        self.assertRegex(
            guards,
            r"request\.target_tree\s*!=\s*(?:accesskit::)?TreeId::from\s*\(\s*pipeline_id\s*\)",
        )
        refresh = script.find("window.reflow")
        resolve = script.find("accessibility_node_address", refresh)
        dispatch = script.find("fire_synthetic_pointer_event_not_trusted", resolve)
        self.assertTrue(0 <= refresh < resolve < dispatch)
        self.assertRegex(script, r"\bis_connected\s*\(\s*\)")
        self.assertRegex(script, r"\bhas_css_layout_box\s*\(\s*\)")

        webview = code["components/servo/webview.rs"]
        self.assertRegex(webview, r"\bpub\s+fn\s+perform_accessibility_action\s*\(")
        self.assertRegex(webview, r"\.send_accessibility_action\s*\(")
        proxy = code["components/servo/proxies.rs"]
        self.assertRegex(proxy, r"\btry_send\s*\(\s*message\s*\)")
        self.assertRegex(
            proxy,
            r"response\.send\s*\(\s*AccessibilityActionResult::ConstellationDisconnected\s*\)",
        )
        for name in (
            "accessibility_action_normal_enqueue_completes_once",
            "accessibility_action_already_disconnected_completes_once",
            "accessibility_action_receiver_drop_after_precheck_completes_once",
            "accessibility_action_dropped_callback_receiver_does_not_panic",
        ):
            self.assertRegex(proxy, rf"\bfn\s+{re.escape(name)}\s*\(")

        traits = code["components/shared/constellation/lib.rs"]
        self.assertIn("ConstellationDisconnected", traits)
        self.assertRegex(traits, r"GenericCallback\s*<\s*AccessibilityActionResult\s*>")
        headless = code["ports/servoshell/desktop/headed_window.rs"]
        self.assertRegex(headless, r"active_document_accesskit_tree_id\s*\(\s*\)")
        self.assertRegex(headless, r"\.perform_accessibility_action\s*\(")

        servo_tests = code["components/servo/tests/accessibility.rs"]
        for name in (
            "test_retained_accessibility_click_dispatches_exactly_once",
            "test_retained_accessibility_rejects_unadvertised_and_unsupported_requests",
            "test_retained_accessibility_rejects_replaced_node_identity",
            "test_retained_accessibility_rejects_inactive_and_stale_tree",
            "test_retained_accessibility_rejects_disabled_hidden_and_non_element_targets",
            "test_retained_accessibility_dropped_callback_does_not_duplicate_dispatch",
        ):
            self.assertRegex(servo_tests, rf"\bfn\s+{re.escape(name)}\s*\(")

        all_code = "\n".join(code.values())
        self.assertNotIn("TODO(#4344): Forward action to Servo", all_code)
        for forbidden in (
            r"\bget_node_by_opaque_id\b",
            r"\bopaque_node_for_id\b",
            r"\bstruct\s+OpaqueNode\b",
            r"\bget_opaque_node\b",
        ):
            self.assertIsNone(re.search(forbidden, all_code), forbidden)

    def test_complete_package_tamper_fails_at_intended_digest(self) -> None:
        original = self.load_manifest()
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            self.copy_package(original, work)
            manifest_path = work / "manifest.json"
            manifest_path.write_text(json.dumps(original, indent=2) + "\n", encoding="utf-8")
            target = work / original["hardening"]["parts"][0]["path"]
            target.write_bytes(target.read_bytes() + b"\n# tampered\n")
            output = work / "output.patch"
            result = self.run_verifier(manifest=manifest_path, root=work, output=output)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("digest mismatch", result.stderr)
            self.assertFalse(output.exists())

    def test_hostile_manifest_mutations_fail_closed(self) -> None:
        original = self.load_manifest()
        mutations = {
            "duplicate_allowlist": lambda value: value["patch"]["allowed_paths"].append(value["patch"]["allowed_paths"][0]),
            "missing_allowlist": lambda value: value["patch"].pop("allowed_paths"),
            "extra_hardening_field": lambda value: value["hardening"].update({"allowed_paths": []}),
            "escape_part": lambda value: value["patch"]["parts"][0].update({"path": "../escape.patch"}),
            "remove_transport": lambda value: value.pop("transport_hardening"),
            "wrong_accesskit": lambda value: value["upstream"].update({"accesskit": "0.25.0"}),
            "weaken_merge_gate": lambda value: value["qualification"].update({"prospective_merge_applies_complete_package": False}),
        }
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            self.copy_package(original, work)
            for name, mutate in mutations.items():
                with self.subTest(name=name):
                    value = json.loads(json.dumps(original))
                    mutate(value)
                    manifest_path = work / f"{name}.json"
                    manifest_path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
                    output = work / f"{name}.patch"
                    result = self.run_verifier(manifest=manifest_path, root=work, output=output)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(output.exists())

    def test_duplicate_json_members_fail_closed(self) -> None:
        text = MANIFEST.read_text(encoding="utf-8").replace(
            '"schema": "trillionnium.lab.servo-patch.v1",',
            '"schema": "trillionnium.lab.servo-patch.v1",\n  "schema": "trillionnium.lab.servo-patch.v1",',
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            manifest = work / "duplicate.json"
            output = work / "output.patch"
            manifest.write_text(text, encoding="utf-8")
            result = self.run_verifier(manifest=manifest, output=output)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("duplicate JSON key", result.stderr)
            self.assertFalse(output.exists())

    def test_pin_claim_ceiling_and_repository_truth_are_exact(self) -> None:
        manifest = self.load_manifest()
        self.assertEqual(
            manifest["upstream"],
            {
                "repository": "servo/servo",
                "commit": "670ae8a70801b162e186f81cbb5bdd2d59c39108",
                "accesskit": "0.24.0",
            },
        )
        self.assertEqual(manifest["carrier_base_commit"], "f0e947e5e7267a3fcdd0a7d5437c0ae00c09ebfe")
        self.assertEqual(manifest["claim_ceiling"], "real-servo-test-harness-not-installed-product-runtime")
        for command in (
            [sys.executable, "tools/validate_repository.py"],
            [sys.executable, "tools/validate_project_truth.py"],
        ):
            result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
