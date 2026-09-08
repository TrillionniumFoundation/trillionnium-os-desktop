from __future__ import annotations

import importlib.util
import json
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


def trigger_paths(text: str, event: str) -> set[str]:
    """Extract one event's YAML path list without importing another slice."""

    result: set[str] = set()
    in_event = False
    in_paths = False
    for line in text.splitlines():
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))
        if not in_event:
            in_event = line == f"  {event}:"
            continue
        if indent == 2 and stripped and not stripped.startswith("#"):
            break
        if not in_paths:
            in_paths = indent == 4 and stripped == "paths:"
            continue
        if indent <= 4 and stripped and not stripped.startswith("-"):
            break
        if indent >= 6 and stripped.startswith("- "):
            value = stripped[2:].split(" #", 1)[0].strip().strip("'\"")
            if value:
                result.add(value)
    return result


class ClosedInputTests(unittest.TestCase):
    def test_duplicate_json_and_lock_identities_fail_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "duplicate JSON object key"):
            VALIDATOR.load_json_strict('{"status":"PASS","status":"FAIL"}')
        package = {"name": "serde", "version": "1.0.0", "source": "registry"}
        with self.assertRaisesRegex(AssertionError, "duplicate package identity"):
            VALIDATOR.index_lock_packages({"package": [package, dict(package)]})

    def test_paths_and_symlinks_fail_closed(self) -> None:
        for value in ("/etc/passwd", "../outside.json", "docs/../outside.json"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                VALIDATOR.repo_path(value)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "trusted.json"
            target.write_text('{"status":"PASS"}\n', encoding="utf-8")
            link = root / "link.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symlink"):
                VALIDATOR.load_json_nofollow(link)

    def test_operation_schema_blob_identity_is_current(self) -> None:
        contract = json.loads(
            (ROOT / "contracts/browser-codec.v1.json").read_text(encoding="utf-8")
        )
        schema_path = ROOT / contract["operation_schema"]["path"]
        self.assertEqual(
            contract["operation_schema"]["git_blob_sha1"],
            VALIDATOR.git_blob_sha1(schema_path),
        )


class UrlParityTests(unittest.TestCase):
    def test_reference_and_schema_share_loopback_boundaries(self) -> None:
        schema = json.loads(
            (ROOT / "contracts/browser-api.v1.schema.json").read_text(encoding="utf-8")
        )
        target_options = schema["$defs"]["navigation_target"]["oneOf"]
        local_schema = next(
            option
            for option in target_options
            if option.get("properties", {}).get("type", {}).get("const")
            == "local_http_fixture"
        )
        pattern = re.compile(local_schema["properties"]["url"]["pattern"])
        accepted = (
            "http://localhost",
            "http://LOCALHOST:8080/fixture",
            "http://localhost:00000/fixture",
            "http://127.0.0.1?ready=1",
            "http://[::1]#fixture",
        )
        rejected = (
            "HTTP://localhost/",
            "http://localhost:",
            "http://localhost:65536/",
            "http://localhost:000000/",
            "http://[::1%25lo]/",
            "http://localhost.evil.example/",
            "http://127.0.0.1:80:90/",
        )
        for url in accepted:
            with self.subTest(url=url):
                self.assertIsNotNone(pattern.search(url))
                safe_url(url, external=False)
        for url in rejected:
            with self.subTest(url=url):
                self.assertIsNone(pattern.search(url))
                with self.assertRaises(CodecError):
                    safe_url(url, external=False)

    def test_external_authority_ambiguities_are_rejected(self) -> None:
        for url in (
            "https://example.com\\evil",
            "https://exa mple.com/",
            "https://example.com:",
            "https://example.com:000000/",
            "https://[::1%25lo]/",
            "https://[v1.fe]/",
        ):
            with self.subTest(url=url), self.assertRaises(CodecError):
                safe_url(url, external=True)


class WorkflowAndClaimTests(unittest.TestCase):
    def test_registered_inputs_trigger_both_events(self) -> None:
        registry = json.loads(
            (ROOT / "manifests/gates.v1.json").read_text(encoding="utf-8")
        )
        gate = next(item for item in registry["gates"] if item["id"] == "D0C-03")
        workflow = (
            ROOT / ".github/workflows/browser-codec-reference.yml"
        ).read_text(encoding="utf-8")
        for event in ("pull_request", "push"):
            paths = trigger_paths(workflow, event)
            self.assertTrue(paths)
            for pattern in gate["invalidation_paths"]:
                self.assertTrue(
                    any(fnmatchcase(candidate, pattern) for candidate in paths),
                    f"registered D0C-03 input {pattern!r} does not trigger {event}",
                )
            self.assertIn("tests/test_validate_rust_browser_codec.py", paths)
        self.assertIn(
            "python3 -m unittest tests.test_validate_rust_browser_codec -v",
            workflow,
        )

    def test_historical_evidence_cannot_promote_current_head(self) -> None:
        contract = json.loads(
            (ROOT / "contracts/browser-codec.v1.json").read_text(encoding="utf-8")
        )
        validation = contract["validation"]
        self.assertEqual(contract["status"], "HOST_VALIDATED_RUST_1_93_NO_DISPATCH")
        self.assertEqual(contract["evidence_freshness"], "STALE_EVIDENCE")
        self.assertFalse(contract["merge_ready"])
        self.assertEqual(validation["evidence_freshness"], "STALE_EVIDENCE")
        self.assertFalse(validation["merge_ready"])
        self.assertIn("exact candidate head", validation["stale_reason"])

    def test_workflow_uses_confined_reader_and_preserves_claim_ceiling(self) -> None:
        workflow = (
            ROOT / ".github/workflows/browser-codec-reference.yml"
        ).read_text(encoding="utf-8")
        self.assertIn("load_json_nofollow", workflow)
        self.assertIn("repo_path(contract.get(\"rust_host_result\")", workflow)
        self.assertIn(
            'assert contract["validation"]["merge_ready"] is False', workflow
        )
        self.assertNotIn('Path(contract["rust_host_result"]).read_text()', workflow)


if __name__ == "__main__":
    unittest.main()
