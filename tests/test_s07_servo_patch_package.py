from __future__ import annotations

import hashlib
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests/lab-d3-servo-retained-node-action.v1.json"
VERIFIER = ROOT / "tools/verify_d3_servo_patch.py"


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
        return json.loads(MANIFEST.read_text(encoding="utf-8"))

    def run_verifier(
        self,
        *,
        manifest: Path = MANIFEST,
        root: Path = ROOT,
        output: Path,
        base_output: Path | None = None,
        hardening_output: Path | None = None,
        transport_output: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        command = [
            "python3", str(VERIFIER), "--manifest", str(manifest),
            "--root", str(root), "--output", str(output),
        ]
        if base_output:
            command.extend(["--base-output", str(base_output)])
        if hardening_output:
            command.extend(["--hardening-output", str(hardening_output)])
        if transport_output:
            command.extend(["--transport-hardening-output", str(transport_output)])
        return subprocess.run(
            command, cwd=ROOT, text=True, capture_output=True, check=False,
        )

    def test_manifest_split_is_closed_and_ordered(self) -> None:
        manifest = self.load_manifest()
        base_paths = [item["path"] for item in manifest["patch"]["parts"]]
        hardening_paths = [item["path"] for item in manifest["hardening"]["parts"]]
        transport_paths = [item["path"] for item in manifest["transport_hardening"]["parts"]]
        self.assertEqual(
            base_paths,
            [
                "manifests/servo-patches/d3-retained-node-action-v1/000.patch",
                "manifests/servo-patches/d3-retained-node-action-v1/001.patch",
                "manifests/servo-patches/d3-retained-node-action-v1/002.patch",
                "manifests/servo-patches/d3-retained-node-action-v1/003.patch",
                "manifests/servo-patches/d3-retained-node-action-v1/004.patch",
                "manifests/servo-patches/d3-retained-node-action-v1/005.patch",
                "manifests/servo-patches/d3-retained-node-action-v1/006.patch",
            ],
        )
        self.assertEqual(
            hardening_paths,
            ["manifests/servo-patches/d3-retained-node-action-v1/007.patch"],
        )
        self.assertEqual(
            transport_paths,
            ["manifests/servo-patches/d3-retained-node-action-v1/008.patch"],
        )
        self.assertTrue(set(base_paths).isdisjoint(set(hardening_paths)))
        self.assertTrue(set(hardening_paths).isdisjoint(set(transport_paths)))
        self.assertIn("file-disjoint", manifest["hardening"]["purpose"])
        self.assertIn("first-hop", manifest["transport_hardening"]["purpose"])

    def test_patch_integrity_and_closed_changed_paths(self) -> None:
        manifest = self.load_manifest()
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "combined.patch"
            base_output = Path(directory) / "base.patch"
            hardening_output = Path(directory) / "hardening.patch"
            transport_output = Path(directory) / "transport.patch"
            result = self.run_verifier(
                output=output,
                base_output=base_output,
                hardening_output=hardening_output,
                transport_output=transport_output,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            record = json.loads(result.stdout)
            self.assertTrue(record["ok"])
            self.assertEqual(record["sha256"], digest(output.read_bytes()))
            self.assertEqual(record["base_sha256"], digest(base_output.read_bytes()))
            self.assertEqual(
                record["transport_hardening_sha256"],
                digest(transport_output.read_bytes()),
            )
            base = concatenate([
                (ROOT / item["path"]).read_bytes()
                for item in manifest["patch"]["parts"]
            ])
            hardening = concatenate([
                (ROOT / item["path"]).read_bytes()
                for item in manifest["hardening"]["parts"]
            ])
            transport = concatenate([
                (ROOT / item["path"]).read_bytes()
                for item in manifest["transport_hardening"]["parts"]
            ])
            self.assertEqual(base_output.read_bytes(), base)
            self.assertEqual(transport_output.read_bytes(), transport)
            self.assertEqual(
                hardening_output.read_bytes(), concatenate([hardening, transport])
            )
            self.assertEqual(
                output.read_bytes(), concatenate([base, hardening, transport])
            )
        self.assertEqual(
            set(record["changed_paths"]),
            {
                "components/constellation/constellation.rs",
                "components/constellation/pipeline.rs",
                "components/layout/accessibility_tree.rs",
                "components/paint/painter.rs",
                "components/script/script_thread.rs",
                "components/servo/proxies.rs",
                "components/servo/tests/accessibility.rs",
                "components/servo/webview.rs",
                "components/shared/constellation/Cargo.toml",
                "components/shared/constellation/lib.rs",
                "components/shared/layout/Cargo.toml",
                "ports/servoshell/desktop/headed_window.rs",
                "ports/servoshell/webdriver.rs",
            },
        )

    def test_public_embedder_contract_and_headless_forwarding_are_present(self) -> None:
        manifest = self.load_manifest()
        all_parts = (
            manifest["patch"]["parts"]
            + manifest["hardening"]["parts"]
            + manifest["transport_hardening"]["parts"]
        )
        additions = "\n".join(
            line[1:]
            for item in all_parts
            for line in (ROOT / item["path"]).read_text(encoding="utf-8").splitlines()
            if line.startswith("+") and not line.startswith("+++")
        )
        mandatory = (
            "PerformAccessibilityAction(",
            "GenericCallback<AccessibilityActionResult>",
            "target_tree: TreeId",
            "target_node: NodeId",
            "supports_action(Action::Click)",
            "get_node_for_accesskit_id",
            "is_connected()",
            "has_css_layout_box()",
            "target_tree != accesskit::TreeId::ROOT",
            "active_document_accesskit_tree_id()",
            "send_accessibility_action",
            "ConstellationDisconnected",
            "accessibility_action_normal_enqueue_completes_once",
            "accessibility_action_already_disconnected_completes_once",
            "accessibility_action_receiver_drop_after_precheck_completes_once",
            "accessibility_action_dropped_callback_receiver_does_not_panic",
        )
        for token in mandatory:
            with self.subTest(token=token):
                self.assertIn(token, additions)
        self.assertNotIn("TODO(#4344): Forward action to Servo", additions)
        self.assertNotIn("get_node_by_opaque_id", additions)
        self.assertNotIn("opaque_node_for_id", additions)

    def test_hostile_patch_mutations_fail_closed(self) -> None:
        original = self.load_manifest()
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            source_part = ROOT / original["hardening"]["parts"][0]["path"]
            copied_part = work / "parts/007.patch"
            copied_part.parent.mkdir(parents=True)
            copied_part.write_bytes(source_part.read_bytes())
            manifest = json.loads(json.dumps(original))
            manifest["hardening"]["parts"][0]["path"] = "parts/007.patch"
            manifest_path = work / "manifest.json"
            manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
            copied_part.write_bytes(copied_part.read_bytes() + b"\n# tampered\n")
            output = work / "tampered.patch"
            result = self.run_verifier(manifest=manifest_path, root=work, output=output)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("digest mismatch", result.stderr)
            self.assertFalse(output.exists())

    def test_hostile_manifest_and_path_mutations_fail_closed(self) -> None:
        original = self.load_manifest()
        with tempfile.TemporaryDirectory() as directory:
            work = Path(directory)
            for item in (
                original["patch"]["parts"]
                + original["hardening"]["parts"]
                + original["transport_hardening"]["parts"]
            ):
                source = ROOT / item["path"]
                destination = work / item["path"]
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source.read_bytes())
            mutations = {
                "duplicate_allowed_path": lambda value: value["patch"]["allowed_paths"].append(value["patch"]["allowed_paths"][0]),
                "escape_part_path": lambda value: value["patch"]["parts"][0].update({"path": "../escape.patch"}),
                "remove_transport_stage": lambda value: value.pop("transport_hardening"),
                "weaken_abi": lambda value: value["upstream"].update({"accesskit": "0.25.0"}),
                "remove_qualification": lambda value: value["qualification"].update({"prospective_merge_applies_complete_package": False}),
            }
            for name, mutate in mutations.items():
                with self.subTest(name=name):
                    manifest = json.loads(json.dumps(original))
                    mutate(manifest)
                    manifest_path = work / f"{name}.json"
                    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
                    output = work / f"{name}.patch"
                    result = self.run_verifier(manifest=manifest_path, root=work, output=output)
                    self.assertNotEqual(result.returncode, 0)
                    self.assertFalse(output.exists())

    def test_duplicate_json_members_fail_closed(self) -> None:
        original = MANIFEST.read_text(encoding="utf-8")
        mutated = original.replace(
            '"schema": "trillionnium.lab.servo-patch.v1",',
            '"schema": "trillionnium.lab.servo-patch.v1",\n'
            '  "schema": "trillionnium.lab.servo-patch.v1",',
            1,
        )
        with tempfile.TemporaryDirectory() as directory:
            manifest_path = Path(directory) / "duplicate.json"
            output = Path(directory) / "duplicate.patch"
            manifest_path.write_text(mutated, encoding="utf-8")
            result = self.run_verifier(manifest=manifest_path, root=ROOT, output=output)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("duplicate JSON key", result.stderr)
            self.assertFalse(output.exists())

    def test_upstream_pin_and_claim_ceiling_are_exact(self) -> None:
        manifest = self.load_manifest()
        self.assertEqual(
            manifest["upstream"],
            {
                "repository": "servo/servo",
                "commit": "670ae8a70801b162e186f81cbb5bdd2d59c39108",
                "accesskit": "0.24.0",
            },
        )
        self.assertEqual(
            manifest["claim_ceiling"],
            "real-servo-test-harness-not-installed-product-runtime",
        )
        self.assertEqual(
            manifest["carrier_base_commit"],
            "f0e947e5e7267a3fcdd0a7d5437c0ae00c09ebfe",
        )

    def test_current_repository_validators_pass(self) -> None:
        commands = (
            ["python3", "tools/validate_repository.py"],
            ["python3", "tools/validate_project_truth.py"],
        )
        for command in commands:
            with self.subTest(command=command):
                result = subprocess.run(
                    command, cwd=ROOT, text=True, capture_output=True, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
