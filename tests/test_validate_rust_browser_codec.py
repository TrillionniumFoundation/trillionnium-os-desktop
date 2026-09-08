from __future__ import annotations

import copy
import importlib.util
import json
import os
from fnmatch import fnmatchcase
from pathlib import Path
import re
import tempfile
import unittest

from tools.browser_codec_reference.canonical import CodecError, safe_url


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_rust_browser_codec_under_test",
    ROOT / "tools/validate_rust_browser_codec.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


def trigger_paths(workflow: str, event: str) -> list[str]:
    """Extract one event's literal path filters without a YAML dependency."""

    lines = workflow.splitlines()
    event_marker = f"{event}:"
    event_index = next(
        index
        for index, line in enumerate(lines)
        if line.strip() == event_marker and len(line) - len(line.lstrip()) == 2
    )
    event_indent = 2
    paths_index = None
    for index in range(event_index + 1, len(lines)):
        line = lines[index]
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= event_indent:
            break
        if stripped == "paths:" and indent == 4:
            paths_index = index
            break
    if paths_index is None:
        return []

    output: list[str] = []
    for line in lines[paths_index + 1 :]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent <= 4:
            break
        if not stripped.startswith("- "):
            continue
        value = stripped[2:].strip()
        if value.startswith(('"', "'")):
            value = json.loads(value) if value.startswith('"') else value.strip("'")
        output.append(value)
    return output


def contract_inputs() -> tuple[object, object, object, object, str, str]:
    return (
        VALIDATOR.load_json_nofollow(
            ROOT / "contracts/browser-codec-resource-limits.v1.json",
            label="test resource limits",
        ),
        VALIDATOR.load_json_nofollow(
            ROOT / "contracts/browser-codec.v1.json",
            label="test codec contract",
        ),
        VALIDATOR.load_json_nofollow(
            ROOT / "contracts/browser-api.v1.schema.json",
            label="test Browser API",
        ),
        VALIDATOR.load_json_nofollow(
            ROOT / "contracts/browser-wire.v1.schema.json",
            label="test Browser wire schema",
        ),
        VALIDATOR.read_text_nofollow(
            ROOT / "crates/hepta-browser-codec/src/lib.rs",
            label="test codec library",
        ),
        VALIDATOR.read_text_nofollow(
            ROOT / "crates/hepta-browser-codec/src/tests.rs",
            label="test codec tests",
        ),
    )


class CargoLockIndexTests(unittest.TestCase):
    def test_rejects_duplicate_name_version_source_identity(self) -> None:
        package = {"name": "serde", "version": "1.0.0", "source": "registry"}
        with self.assertRaisesRegex(AssertionError, "duplicate package identity"):
            VALIDATOR.index_lock_packages({"package": [package, dict(package)]})

    def test_retains_same_name_records_with_distinct_identity(self) -> None:
        packages = VALIDATOR.index_lock_packages(
            {
                "package": [
                    {"name": "serde", "version": "1.0.0", "source": "registry"},
                    {"name": "serde", "version": "1.0.1", "source": "registry"},
                ]
            }
        )
        self.assertEqual(len(packages["serde"]), 2)
        with self.assertRaisesRegex(AssertionError, "ambiguous"):
            VALIDATOR.one_lock_package(packages, "serde")


class SafeSourceReaderTests(unittest.TestCase):
    def test_strict_json_rejects_duplicate_and_non_finite_values(self) -> None:
        hostile = (
            '{"status":"PASS","status":"FAIL"}',
            '{"value":NaN}',
            '{"value":Infinity}',
            '{"value":-Infinity}',
            '{"value":1e999}',
            '{"nested":{"value":NaN}}',
            '[0,{"nested":[-Infinity]}]',
        )
        for encoded in hostile:
            with self.subTest(encoded=encoded), self.assertRaises(ValueError):
                VALIDATOR.load_json_strict(encoded)

    def test_strict_json_serialization_rejects_non_finite_values(self) -> None:
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value), self.assertRaises(ValueError):
                VALIDATOR.strict_json_dumps({"value": value}, sort_keys=True)

    def test_repo_path_rejects_absolute_and_traversal_inputs(self) -> None:
        for value in ("/etc/passwd", "../outside.json", "docs/../outside.json"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                VALIDATOR.repo_path(value)

    def test_dirfd_reader_rejects_final_component_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "trusted.json"
            target.write_text('{"status":"PASS"}\n', encoding="utf-8")
            link = root / "link.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symlink"):
                VALIDATOR.read_bytes_beneath(root, link, label="symlink regression")

    def test_parent_swap_cannot_redirect_pinned_dirfd_walk(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            top = Path(temporary)
            root = top / "repository"
            trusted = root / "nested"
            outside = top / "outside"
            trusted.mkdir(parents=True)
            outside.mkdir()
            (trusted / "evidence.json").write_bytes(b"trusted-evidence")
            (outside / "evidence.json").write_bytes(b"attacker-evidence")
            swapped = False

            def swap_after_parent_open(
                _index: int,
                component: str,
                _descriptor: int,
            ) -> None:
                nonlocal swapped
                if component != "nested" or swapped:
                    return
                trusted.rename(root / "nested-pinned")
                os.symlink(outside, trusted, target_is_directory=True)
                swapped = True

            payload = VALIDATOR.read_bytes_beneath(
                root,
                root / "nested/evidence.json",
                label="parent-swap regression",
                after_component=swap_after_parent_open,
            )
            self.assertTrue(swapped)
            self.assertEqual(payload, b"trusted-evidence")
            self.assertNotEqual(payload, b"attacker-evidence")

    def test_codec_operation_schema_git_blob_sha1_is_current(self) -> None:
        contract = VALIDATOR.load_json_nofollow(
            ROOT / "contracts/browser-codec.v1.json",
            label="codec contract test",
        )
        self.assertIsInstance(contract, dict)
        schema_path = ROOT / contract["operation_schema"]["path"]
        self.assertEqual(
            contract["operation_schema"]["git_blob_sha1"],
            VALIDATOR.git_blob_sha1(schema_path),
        )

    def test_url_policy_matches_schema_case_and_authority_boundaries(self) -> None:
        schema = VALIDATOR.load_json_nofollow(
            ROOT / "contracts/browser-api.v1.schema.json",
            label="Browser API test schema",
        )
        target_options = schema["$defs"]["navigation_target"]["oneOf"]
        local_schema = next(
            option
            for option in target_options
            if option.get("properties", {}).get("type", {}).get("const")
            == "local_http_fixture"
        )
        pattern = re.compile(local_schema["properties"]["url"]["pattern"])
        for url in (
            "http://localhost",
            "http://LOCALHOST:8080/fixture",
            "http://localhost:00000/fixture",
            "http://127.0.0.1?ready=1",
            "http://[::1]#fixture",
        ):
            with self.subTest(url=url):
                self.assertIsNotNone(pattern.search(url))
                safe_url(url, external=False)
        for url in (
            "HTTP://localhost/",
            "http://localhost:",
            "http://localhost:65536/",
            "http://[::1]:65536/",
            "http://localhost:000000/",
            "http://[::1%25lo]/",
            "http://localhost.evil.example/",
            "http://127.0.0.1:80:90/",
        ):
            with self.subTest(url=url):
                self.assertIsNone(pattern.search(url))
                with self.assertRaises(CodecError):
                    safe_url(url, external=False)
        for url in (
            "https://example.com",
            "https://EXAMPLE.COM/path",
            "https://example.com:00000/path",
        ):
            with self.subTest(url=url):
                safe_url(url, external=True)
        for url in (
            "https://example.com\\evil",
            "https://exa mple.com/",
            "https://example.com:",
            "https://example.com:000000/",
            "https://[::1%25lo]/",
            "https://[v1.fe]/",
        ):
            with self.subTest(url=url):
                with self.assertRaises(CodecError):
                    safe_url(url, external=True)


class StructuralContractTests(unittest.TestCase):
    def test_current_codec_contract_is_structurally_closed(self) -> None:
        self.assertEqual(VALIDATOR.validate_codec_contract_data(*contract_inputs()), [])

    def test_resource_registry_missing_extra_and_wrong_type_fail(self) -> None:
        mutations = []
        inputs = list(contract_inputs())
        limits = copy.deepcopy(inputs[0])
        del limits["canonical_json"]["max_json_key_utf8_bytes"]
        inputs[0] = limits
        mutations.append(inputs)

        inputs = list(contract_inputs())
        limits = copy.deepcopy(inputs[0])
        limits["canonical_json"]["unexpected"] = 1
        inputs[0] = limits
        mutations.append(inputs)

        inputs = list(contract_inputs())
        limits = copy.deepcopy(inputs[0])
        limits["canonical_json"]["max_nesting_depth"] = True
        inputs[0] = limits
        mutations.append(inputs)

        for inputs in mutations:
            self.assertTrue(VALIDATOR.validate_codec_contract_data(*inputs))

    def test_actionable_snapshot_minima_follow_exact_schema_paths(self) -> None:
        for label, clause_index in (("page_act", 1), ("element_present", 2)):
            inputs = list(contract_inputs())
            wire = copy.deepcopy(inputs[3])
            clause = wire["allOf"][clause_index]
            if label == "page_act":
                revision = clause["then"]["properties"]["operation"]["properties"][
                    "target"
                ]["properties"]["semantic_snapshot_revision"]
            else:
                revision = clause["then"]["properties"]["operation"]["properties"][
                    "condition"
                ]["properties"]["target"]["properties"][
                    "semantic_snapshot_revision"
                ]
            revision["minimum"] = 0
            wire["decoy"] = {
                "semantic_snapshot_revision": {"minimum": 1},
                "operation": label,
            }
            inputs[3] = wire
            with self.subTest(label=label):
                errors = VALIDATOR.validate_codec_contract_data(*inputs)
                self.assertTrue(any(label in error for error in errors), errors)

    def test_comment_decoys_cannot_replace_rust_constants_or_test_functions(self) -> None:
        inputs = list(contract_inputs())
        inputs[4] = inputs[4].replace(
            "pub const MAX_JSON_DEPTH: usize = 32;",
            "pub const MAX_JSON_DEPTH: usize = 31;\n// pub const MAX_JSON_DEPTH: usize = 32;",
        )
        errors = VALIDATOR.validate_codec_contract_data(*inputs)
        self.assertTrue(any("MAX_JSON_DEPTH" in error for error in errors), errors)

        inputs = list(contract_inputs())
        test_name = "constructed_json_values_enforce_depth_and_container_item_bounds"
        inputs[5] = inputs[5].replace(
            f"fn {test_name}(",
            f"fn {test_name}_disabled(",
        ) + f"\n// #[test] fn {test_name}() {{}}\n"
        errors = VALIDATOR.validate_codec_contract_data(*inputs)
        self.assertTrue(any(test_name in error for error in errors), errors)


class WorkflowInvalidationTests(unittest.TestCase):
    def test_codec_registry_and_workflow_paths_are_mutual_covers(self) -> None:
        registry = json.loads(
            (ROOT / "manifests/gates.v1.json").read_text(encoding="utf-8")
        )
        gate = next(item for item in registry["gates"] if item["id"] == "D0C-03")
        registered = set(gate["invalidation_paths"])
        workflow = (
            ROOT / ".github/workflows/browser-codec-reference.yml"
        ).read_text(encoding="utf-8")
        for event in ("pull_request", "push"):
            trigger = trigger_paths(workflow, event)
            self.assertTrue(trigger, f"{event} paths must be discoverable")
            for pattern in registered:
                self.assertTrue(
                    any(fnmatchcase(candidate, pattern) for candidate in trigger),
                    f"D0C-03 registry pattern {pattern!r} is absent from {event} trigger",
                )
            for candidate in trigger:
                self.assertTrue(
                    any(fnmatchcase(candidate, pattern) for pattern in registered),
                    f"D0C-03 trigger path {candidate!r} is absent from registry",
                )

    def test_codec_workflow_covers_registered_browser_contract_glob(self) -> None:
        registry = json.loads(
            (ROOT / "manifests/gates.v1.json").read_text(encoding="utf-8")
        )
        gate = next(item for item in registry["gates"] if item["id"] == "D0C-03")
        self.assertIn("contracts/browser-*.json", gate["invalidation_paths"])
        workflow = (
            ROOT / ".github/workflows/browser-codec-reference.yml"
        ).read_text(encoding="utf-8")
        for path in sorted(ROOT.glob("contracts/browser-*.json")):
            marker = f'"{path.relative_to(ROOT).as_posix()}"'
            self.assertGreaterEqual(workflow.count(marker), 2)

    def test_security_helpers_and_structural_validator_are_gate_inputs(self) -> None:
        workflow = (
            ROOT / ".github/workflows/browser-codec-reference.yml"
        ).read_text(encoding="utf-8")
        required_paths = (
            "tools/browser_codec_reference_security.py",
            "tools/browser_codec_reference_contract.py",
            "tools/browser_codec_reference_legacy_audit.py",
            "tests/test_validate_rust_browser_codec.py",
        )
        for event in ("pull_request", "push"):
            patterns = trigger_paths(workflow, event)
            for required in required_paths:
                self.assertTrue(
                    any(fnmatchcase(required, pattern) for pattern in patterns),
                    f"{required} is not covered by the {event} trigger",
                )
        self.assertIn("python3 tools/browser_codec_reference_contract.py", workflow)
        for required in required_paths[:3]:
            self.assertIn(required, workflow)

    def test_recorded_codec_host_evidence_is_explicitly_stale(self) -> None:
        contract = VALIDATOR.load_json_nofollow(
            ROOT / "contracts/browser-codec.v1.json",
            label="stale evidence test",
        )
        validation = contract["validation"]
        self.assertEqual(contract["status"], "HOST_VALIDATED_RUST_1_93_NO_DISPATCH")
        self.assertEqual(
            contract["evidence_lifecycle"],
            "STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN",
        )
        self.assertEqual(contract["evidence_freshness"], "STALE_EVIDENCE")
        self.assertFalse(contract["merge_ready"])
        self.assertEqual(validation["evidence_freshness"], "STALE_EVIDENCE")
        self.assertFalse(validation["merge_ready"])
        self.assertIn(
            "4cfebbe6a40ebbec32d9d1bcbfca1d513b510ebb",
            validation["stale_reason"],
        )
        self.assertIn("exact candidate head", validation["stale_reason"])


if __name__ == "__main__":
    unittest.main()
