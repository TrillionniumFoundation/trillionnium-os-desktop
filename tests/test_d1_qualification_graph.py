"""Keep D1 host qualification out of product builds without weakening S04."""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import tempfile
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("d1_graph", ROOT / "tools/validate_d1_qualification_graph.py")
assert SPEC is not None and SPEC.loader is not None
GRAPH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GRAPH)


def artifact(name: str, kind: str = "lib", features: list[str] | None = None) -> dict:
    return {"reason": "compiler-artifact", "target": {"name": name, "kind": [kind]},
            "features": features or [], "executable": "/private/build/" + name if kind != "lib" else None}


def records(qualification: bool) -> list[dict]:
    output = [artifact("hepta_peer_attestation", features=[GRAPH.QUALIFICATION_FEATURE] if qualification else [])]
    if qualification:
        output.extend([artifact("hepta_agent_port"), artifact("hepta_browser_codec"),
                       artifact("hepta-agent-d1-fixture", "example", ["fixture"])])
    else:
        output.append(artifact("hepta-agent-portd", "bin"))
    output.append({"reason": "build-finished", "success": True})
    return output


class D1QualificationGraphTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest = tomllib.loads((ROOT / GRAPH.MANIFEST).read_text())

    def test_current_source_is_closed(self) -> None:
        self.assertEqual(GRAPH.validate(ROOT), [])

    def test_restore_the_exact_original_s04_fixture_feature(self) -> None:
        self.assertEqual(self.manifest["features"], {"default": [], "fixture": ["dep:hepta-agent-port"]})

    def test_qualification_feature_cannot_widen_fixture(self) -> None:
        candidate = copy.deepcopy(self.manifest)
        candidate["features"]["fixture"].append("hepta-peer-attestation/qualification-static-attestation")
        self.assertTrue(GRAPH.validate_manifest(candidate))

    def test_default_feature_cannot_enable_fixture(self) -> None:
        candidate = copy.deepcopy(self.manifest)
        candidate["features"]["default"].append("fixture")
        self.assertTrue(GRAPH.validate_manifest(candidate))

    def test_codec_cannot_be_a_normal_dependency(self) -> None:
        candidate = copy.deepcopy(self.manifest)
        candidate["dependencies"]["hepta-browser-codec"] = candidate["dev-dependencies"]["hepta-browser-codec"]
        self.assertTrue(GRAPH.validate_manifest(candidate))

    def test_static_attestation_cannot_be_a_normal_dependency_feature(self) -> None:
        candidate = copy.deepcopy(self.manifest)
        candidate["dependencies"]["hepta-peer-attestation"]["features"] = [GRAPH.QUALIFICATION_FEATURE]
        self.assertTrue(GRAPH.validate_manifest(candidate))

    def test_qualification_dev_feature_is_required(self) -> None:
        candidate = copy.deepcopy(self.manifest)
        candidate["dev-dependencies"]["hepta-peer-attestation"]["features"] = []
        self.assertTrue(GRAPH.validate_manifest(candidate))

    def test_example_cannot_become_a_product_binary(self) -> None:
        candidate = copy.deepcopy(self.manifest)
        candidate["bin"].append(candidate["example"].pop())
        self.assertTrue(GRAPH.validate_manifest(candidate))

    def test_example_feature_guard_cannot_be_removed(self) -> None:
        candidate = copy.deepcopy(self.manifest)
        candidate["example"][0]["required-features"] = []
        self.assertTrue(GRAPH.validate_manifest(candidate))

    def test_implicit_targets_and_build_script_are_rejected(self) -> None:
        for key in ("autoexamples", "autobins", "build"):
            with self.subTest(key=key):
                candidate = copy.deepcopy(self.manifest)
                candidate["package"][key] = True
                self.assertTrue(GRAPH.validate_manifest(candidate))

    def test_target_specific_dependency_backdoor_is_rejected(self) -> None:
        candidate = copy.deepcopy(self.manifest)
        candidate["target"] = {"cfg(unix)": {"dependencies": {"hepta-browser-codec": "*"}}}
        self.assertTrue(GRAPH.validate_manifest(candidate))

    def test_product_cargo_messages_pass(self) -> None:
        self.assertEqual(GRAPH.validate_build(records(False), qualification=False), [])

    def test_qualification_cargo_messages_pass(self) -> None:
        self.assertEqual(GRAPH.validate_build(records(True), qualification=True), [])

    def test_static_attestation_feature_leak_fails(self) -> None:
        for feature in GRAPH.FORBIDDEN_PRODUCT_FEATURES:
            with self.subTest(feature=feature):
                value = records(False)
                value[0]["features"] = [feature]
                self.assertTrue(GRAPH.validate_build(value, qualification=False))

    def test_qualification_dependency_leak_fails(self) -> None:
        for name in ("hepta_agent_port", "hepta_browser_codec"):
            with self.subTest(name=name):
                value = records(False)
                value.insert(0, artifact(name))
                self.assertTrue(GRAPH.validate_build(value, qualification=False))

    def test_failed_missing_or_duplicate_build_completion_fails(self) -> None:
        for suffix in ([], [{"reason": "build-finished", "success": False}],
                       [{"reason": "build-finished", "success": 1}],
                       [{"reason": "build-finished", "success": True}] * 2):
            with self.subTest(suffix=suffix):
                self.assertTrue(GRAPH.validate_build(records(False)[:-1] + suffix, qualification=False))

    def test_missing_or_duplicate_attestation_artifact_fails(self) -> None:
        value = records(False)
        self.assertTrue(GRAPH.validate_build(value[1:], qualification=False))
        value.insert(0, copy.deepcopy(value[0]))
        self.assertTrue(GRAPH.validate_build(value, qualification=False))

    def test_wrong_selected_target_kind_fails(self) -> None:
        value = records(True)
        value[-2]["target"]["kind"] = ["bin"]
        self.assertTrue(GRAPH.validate_build(value, qualification=True))

    def test_missing_executable_or_unexpected_target_feature_fails(self) -> None:
        value = records(False)
        value[-2]["executable"] = None
        self.assertTrue(GRAPH.validate_build(value, qualification=False))
        value = records(False)
        value[-2]["features"] = ["fixture"]
        self.assertTrue(GRAPH.validate_build(value, qualification=False))

    def test_qualification_requires_compiled_dependencies(self) -> None:
        value = records(True)
        value = [r for r in value if r.get("target", {}).get("name") != "hepta_browser_codec"]
        self.assertTrue(GRAPH.validate_build(value, qualification=True))

    def test_malformed_nested_cargo_metadata_fails_without_exception(self) -> None:
        for target in (None, [], {"name": "hepta_peer_attestation", "kind": "lib"}):
            value = records(False)
            value[0]["target"] = target
            self.assertTrue(GRAPH.validate_build(value, qualification=False))
        for features in (None, "fixture", [[]], ["default", "default"]):
            value = records(False)
            value[0]["features"] = features
            self.assertTrue(GRAPH.validate_build(value, qualification=False))

    def test_non_object_cargo_record_fails(self) -> None:
        self.assertTrue(GRAPH.validate_build([[]], qualification=False))

    def test_bounded_duplicate_free_cargo_jsonl(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cargo.jsonl"
            path.write_text("\n".join(json.dumps(r) for r in records(False)))
            self.assertEqual(GRAPH.build_messages(path), records(False))
            for bad in ('{"reason":"one","reason":"two"}', '{"value":NaN}', '[1]', ''):
                path.write_text(bad)
                with self.assertRaises(ValueError):
                    GRAPH.build_messages(path)

    def test_symlink_and_fifo_metadata_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "metadata"
            target = Path(directory) / "target"
            target.write_text('{}')
            path.symlink_to(target)
            with self.assertRaises(OSError):
                GRAPH.bounded_read(path)
            path.unlink()
            os.mkfifo(path)
            with self.assertRaises(ValueError):
                GRAPH.bounded_read(path)

    def test_no_raw_peer_field_reintroduced_into_product_evidence(self) -> None:
        source = (ROOT / "crates/hepta-agent-port/src/lib.rs").read_text()
        fields = source.split("pub struct ServiceEvidence {", 1)[1].split("}", 1)[0]
        self.assertNotIn("pub peer", fields)
        fixture = (ROOT / "apps/hepta-agent-portd/examples/hepta-agent-d1-fixture.rs").read_text()
        self.assertNotIn("evidence.peer", fixture)
        self.assertIn(".refresh_snapshot(self.attestor)", fixture)
        self.assertIn("impl BrowserRequestHandler for AttestedFixtureHandler", fixture)
        self.assertIn("server_evidence_json(&evidence, peer)", fixture)
        self.assertIn("qualification evidence requires an authenticated positive PID", fixture)


if __name__ == "__main__":
    unittest.main()
