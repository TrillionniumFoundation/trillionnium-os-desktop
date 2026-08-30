from __future__ import annotations

import importlib.util
import json
from fnmatch import fnmatchcase
from pathlib import Path
import tempfile
import unittest

from tests.test_agent_port_custody_workflow import trigger_paths


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "validate_rust_browser_codec_under_test",
    ROOT / "tools/validate_rust_browser_codec.py",
)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)


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
    def test_strict_json_rejects_duplicate_members(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
            VALIDATOR.load_json_strict('{"status":"PASS","status":"FAIL"}')

    def test_repo_path_rejects_absolute_and_traversal_inputs(self) -> None:
        for value in ("/etc/passwd", "../outside.json", "docs/../outside.json"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                VALIDATOR.repo_path(value)

    def test_nofollow_reader_rejects_symlinked_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "trusted.json"
            target.write_text('{"status":"PASS"}\n', encoding="utf-8")
            link = root / "link.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symlink"):
                VALIDATOR.load_json_nofollow(link)

    def test_codec_workflow_uses_confined_strict_reader_for_host_result(self) -> None:
        workflow = (
            ROOT / ".github/workflows/browser-codec-reference.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("load_json_nofollow", workflow)
        self.assertIn("repo_path(contract.get(\"rust_host_result\")", workflow)
        self.assertNotIn(
            'Path(contract["rust_host_result"]).read_text()', workflow
        )


class WorkflowInvalidationTests(unittest.TestCase):
    def test_codec_registry_and_workflow_paths_are_mutual_covers(self) -> None:
        """A changed codec input must invalidate both permanent trigger blocks."""

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
        """Keep the permanent trigger a superset of D0C-03 contract inputs.

        The gate registry intentionally uses the compact ``contracts/browser-*.json``
        pattern.  A concrete contract can be added later without anyone noticing
        that the workflow's hand-written list stopped triggering; enumerate the
        current matches and require each one in both trigger blocks.
        """

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
            self.assertGreaterEqual(
                workflow.count(marker),
                2,
                f"D0C-03 workflow must trigger for {path.name} on PR and push",
            )

    def test_python_regression_is_executed_by_the_gate(self) -> None:
        workflow = (
            ROOT / ".github/workflows/browser-codec-reference.yml"
        ).read_text(encoding="utf-8")
        self.assertIn(
            "tests/test_validate_rust_browser_codec.py",
            trigger_paths(workflow, "pull_request"),
        )
        self.assertIn(
            "tests/test_validate_rust_browser_codec.py",
            trigger_paths(workflow, "push"),
        )
        self.assertIn(
            "python3 -m unittest tests.test_validate_rust_browser_codec -v",
            workflow,
        )


if __name__ == "__main__":
    unittest.main()
