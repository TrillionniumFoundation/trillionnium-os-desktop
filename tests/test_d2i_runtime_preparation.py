"""Exercise actual D2I preparation, not just presence of source markers.

Generated Rust and transformation receipts are temporary source-only artifacts.
No Servo process, QEMU image, listener or product activation is started here.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/prepare_d2i_runtime.py"
SOURCE = ROOT / "runtime/servo/hepta_workspace_runtime.rs"
SPEC = importlib.util.spec_from_file_location("d2i_preparer_under_test", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
PREPARER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARER)


class ExactAnchorTests(unittest.TestCase):
    def test_unique_literal_anchor_preserves_surroundings(self) -> None:
        self.assertEqual(PREPARER.sub("before anchor after", "anchor", "result", "literal"),
                         "before result after")

    def test_missing_literal_anchor_fails(self) -> None:
        with self.assertRaisesRegex(SystemExit, "found 0"):
            PREPARER.sub("before after", "anchor", "result", "literal")

    def test_duplicate_literal_anchor_fails(self) -> None:
        with self.assertRaisesRegex(SystemExit, "found 2"):
            PREPARER.sub("anchor anchor", "anchor", "result", "literal")

    def test_unique_regex_and_backreference_are_preserved(self) -> None:
        self.assertEqual(PREPARER.sub("before value=12 after", r"value=(\d+)",
                                      r"number=\1", "regex", regex=True),
                         "before number=12 after")

    def test_missing_regex_anchor_fails(self) -> None:
        with self.assertRaisesRegex(SystemExit, "found 0"):
            PREPARER.sub("other", r"value=\d+", "result", "regex", regex=True)

    def test_duplicate_regex_anchor_is_not_silently_first_match_only(self) -> None:
        with self.assertRaisesRegex(SystemExit, "found 2"):
            PREPARER.sub("value=12 value=34", r"value=\d+", "result", "regex", regex=True)

    def test_duplicate_multiline_anchor_fails(self) -> None:
        with self.assertRaisesRegex(SystemExit, "found 2"):
            PREPARER.sub("start\none\nend\nstart\ntwo\nend", r"start.*?end", "result",
                         "multiline", regex=True)

    def test_all_regex_matches_are_counted(self) -> None:
        with self.assertRaisesRegex(SystemExit, "found 3"):
            PREPARER.sub("value=1 value=2 value=3", r"value=\d+", "result", "regex", regex=True)

    def test_empty_pattern_is_not_an_insertion_authority(self) -> None:
        for regex in (False, True):
            with self.subTest(regex=regex), self.assertRaisesRegex(SystemExit, "empty"):
                PREPARER.sub("", "", "result", "empty", regex=regex)

    def test_unique_multiline_anchor_retains_dotall_semantics(self) -> None:
        self.assertEqual(PREPARER.sub("before\nstart\nbody\nend\nafter", r"start.*?end",
                                      "result", "multiline", regex=True),
                         "before\nresult\nafter")


class ActualSourcePreparationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name)
        self.original = SOURCE.read_bytes()
        self.output = self.directory / "runtime.rs"
        self.evidence = self.directory / "transformation.json"

    def run_preparer(self, source: Path) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-I", str(SCRIPT), "--source", str(source),
             "--output", str(self.output), "--evidence", str(self.evidence)],
            cwd=self.directory, capture_output=True, text=True, timeout=20, check=False,
        )

    def test_tracked_runtime_prepares_with_exact_digest_bound_output(self) -> None:
        result = self.run_preparer(SOURCE)
        self.assertEqual(result.returncode, 0, result.stderr)
        generated = self.output.read_bytes()
        record = json.loads(self.evidence.read_text())
        self.assertEqual(record["source_sha256"], hashlib.sha256(self.original).hexdigest())
        self.assertEqual(record["output_sha256"], hashlib.sha256(generated).hexdigest())
        self.assertEqual(record["status"], "PASS_DETERMINISTIC_REVIEWED_TRANSFORMATION")
        self.assertFalse(record["repository_mutated"])
        self.assertFalse(record["callback_required"])
        self.assertTrue(record["zero_process_intermediate_required"])
        self.assertTrue(record["distinct_replacement_required"])
        self.assertTrue(record["external_navigation_denied"])
        self.assertIn(b"zero_content_processes_after_termination", generated)
        self.assertIn(b"replacement_process_distinct", generated)
        self.assertEqual(SOURCE.read_bytes(), self.original)

    def test_repeated_source_preparation_is_byte_identical(self) -> None:
        first = self.run_preparer(SOURCE)
        self.assertEqual(first.returncode, 0, first.stderr)
        output, evidence = self.output.read_bytes(), self.evidence.read_bytes()
        second = self.run_preparer(SOURCE)
        self.assertEqual(second.returncode, 0, second.stderr)
        self.assertEqual(self.output.read_bytes(), output)
        self.assertEqual(self.evidence.read_bytes(), evidence)

    def test_missing_required_anchor_writes_no_success_outputs(self) -> None:
        source = self.directory / "missing.rs"
        anchor = b"KeyboardEvent, MouseButton,\n"
        self.assertEqual(self.original.count(anchor), 1)
        source.write_bytes(self.original.replace(anchor, b"KeyboardEvent,\n", 1))
        result = self.run_preparer(source)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("expected exactly one match, found 0", result.stderr)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.evidence.exists())

    def test_duplicate_regex_source_anchor_writes_no_success_outputs(self) -> None:
        source = self.directory / "duplicate.rs"
        # Duplicate a source-shape anchor, not a runtime operation or executable payload.
        source.write_bytes(self.original + b"\nfn exact_content_process_pid() -> Result<u32, String> {\n"
                           b"    unreachable!()\n}\n\nfn exact_content_process_start_time")
        result = self.run_preparer(source)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("process enumeration: expected exactly one match, found 2", result.stderr)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.evidence.exists())

    def test_failed_preparation_cannot_replace_previous_outputs(self) -> None:
        self.output.write_bytes(b"previous generated artifact\n")
        self.evidence.write_bytes(b"previous source receipt\n")
        source = self.directory / "missing.rs"
        source.write_bytes(b"not the tracked Servo runtime\n")
        result = self.run_preparer(source)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.output.read_bytes(), b"previous generated artifact\n")
        self.assertEqual(self.evidence.read_bytes(), b"previous source receipt\n")

    def test_missing_source_fails_without_output(self) -> None:
        result = self.run_preparer(self.directory / "absent.rs")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.output.exists())
        self.assertFalse(self.evidence.exists())


if __name__ == "__main__":
    unittest.main()
