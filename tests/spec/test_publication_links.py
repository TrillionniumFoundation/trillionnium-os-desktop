#!/usr/bin/env python3
"""Regression checks for published Markdown links and their archive binding."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[2]
REPORT = ROOT / "results/integration/2026-10-19-g1b-usage"
VALIDATOR = REPORT / "source-publication/validate-publication.py"
spec = importlib.util.spec_from_file_location("publication_validator", VALIDATOR)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class PublicationLinks(unittest.TestCase):
    def test_supported_destinations_and_code_exclusion(self):
        cases = [
            ("[a](file.md)", ["file.md"]),
            ("![x](images/a.png)", ["images/a.png"]),
            ("[a](<space path.md>)", ["space path.md"]),
            (r"[a](foo\)bar.md)", [r"foo\)bar.md"]),
            ('[a](foo.md "title")', ["foo.md"]),
            ("[a](foo.md 'title')", ["foo.md"]),
            ("[a](one.md) [b](two.md)", ["one.md", "two.md"]),
            ("[a][ref]\n[ref]: file.md", ["file.md"]),
            ("`[a](ignored.md)` [b](visible.md)", ["visible.md"]),
            ("```md\n[a](ignored.md)\n```\n[b](visible.md)", ["visible.md"]),
            ("~~~md\n[a](ignored.md)\n~~~\n[b](visible.md)", ["visible.md"]),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(validator.link_destinations(text), expected)

    def test_parenthesized_path_is_not_truncated(self):
        self.assertEqual(
            validator.link_destinations("[report](reports/run(1).md)"),
            ["reports/run(1).md"],
        )

    def test_malformed_destination_finishes_within_watchdog(self):
        # This family timed out at only 28 repetitions before the correction.
        # A separate process bounds a regression without leaving a stuck thread.
        result = subprocess.run(
            [sys.executable, "-I", "-B", *(["-O"] * sys.flags.optimize),
             str(Path(__file__).resolve()), "--probe"],
            input="[](" + "(\\)" * 100_000,
            text=True,
            capture_output=True,
            timeout=3,
            check=True,
        )
        self.assertEqual(json.loads(result.stdout), [])

    def test_successor_manifest_binds_only_the_corrected_validator(self):
        manifest = json.loads((REPORT / "files-manifest.json").read_text())
        rows = manifest["files"]
        self.assertEqual(manifest["file_count"], len(rows))
        self.assertEqual(len(rows), 288)
        self.assertEqual(manifest["total_bytes"], sum(row["bytes"] for row in rows))
        self.assertEqual(manifest["total_bytes"], 5_398_580)
        validator_rows = [
            row for row in rows
            if row["path"] == "source-publication/validate-publication.py"
        ]
        self.assertEqual(len(validator_rows), 1)
        raw = VALIDATOR.read_bytes()
        self.assertEqual(validator_rows[0]["bytes"], len(raw))
        self.assertEqual(validator_rows[0]["sha256"], hashlib.sha256(raw).hexdigest())
        other_rows = [row for row in rows if row not in validator_rows]
        encoded = json.dumps(other_rows, sort_keys=True, separators=(",", ":")).encode()
        # The other 287 historical identities remain exactly as published.
        self.assertEqual(
            hashlib.sha256(encoded).hexdigest(),
            "7e12f49cccd984b7d7c527093b613172594b7908f1dd4a2c87c0493188b85f5f",
        )
        historical = json.loads((REPORT / "publication-validation.json").read_text())
        self.assertEqual(
            historical["validator_sha256"],
            "e42de9e6d03f0b3e6bbf57545c15cf6977dbf7ca9f6373ecc2e20a34e48c126f",
        )


if __name__ == "__main__":
    if sys.argv[1:] == ["--probe"]:
        print(json.dumps(validator.link_destinations(sys.stdin.read())))
    else:
        unittest.main()
