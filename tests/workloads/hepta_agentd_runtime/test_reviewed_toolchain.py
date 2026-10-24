#!/usr/bin/env python3
"""Parse real temporary manifests and compiler responses against review pins."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

import reviewed_toolchain as toolchain


class ReviewedToolchainTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.path = self.root / "codex-rs/rust-toolchain.toml"
        self.path.parent.mkdir()
        self.path.write_text('[toolchain]\nchannel = "1.96.0"\ncomponents = ["clippy", "rustfmt"]\n')
        self.review = {"userspace_toolchain": {"channel": "1.96.0", "manifest": "codex-rs/rust-toolchain.toml",
                                               "sha256": hashlib.sha256(self.path.read_bytes()).hexdigest()}}

    def test_exact_source_manifest_and_both_actual_version_formats(self):
        channel = toolchain.verify_manifest(self.root, self.review)
        for name in ("cargo", "rustc"):
            response = name + " 1.96.0 (123456789 2026-05-18)\n"
            self.assertEqual(toolchain.validate_version(name, response, channel), response.strip())

    def test_stale_review_rejects_current_source_before_build(self):
        self.review["userspace_toolchain"]["channel"] = "1.95.0"
        with self.assertRaisesRegex(ValueError, "source toolchain differs"):
            toolchain.verify_manifest(self.root, self.review)

    def test_changed_manifest_bytes_are_rejected_even_for_same_version(self):
        self.path.write_text(self.path.read_text() + '# unreviewed change\n')
        with self.assertRaisesRegex(ValueError, "manifest digest differs"):
            toolchain.verify_manifest(self.root, self.review)

    def test_symlink_cannot_substitute_the_manifest(self):
        other = self.root / "other.toml"
        self.path.rename(other)
        self.path.symlink_to(other)
        with self.assertRaisesRegex(ValueError, "regular original toolchain"):
            toolchain.verify_manifest(self.root, self.review)

    def test_unpinned_or_malformed_review_is_rejected(self):
        values = [None, {}, {**self.review["userspace_toolchain"], "extra": True}]
        for channel in ("stable", "1.96", "nightly", "1.96.0-nightly", "1.96.0\nPATH=/tmp", 196):
            value = copy.deepcopy(self.review["userspace_toolchain"])
            value["channel"] = channel
            values.append(value)
        for value in values:
            with self.subTest(value=value), self.assertRaises(ValueError):
                toolchain.reviewed_channel({"userspace_toolchain": value})

    def test_manifest_path_and_digest_must_be_exact(self):
        for key, value in (("manifest", "../toolchain.toml"), ("sha256", "0" * 63)):
            review = copy.deepcopy(self.review)
            review["userspace_toolchain"][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                toolchain.verify_manifest(self.root, review)

    def test_old_new_nightly_or_wrong_program_version_is_rejected(self):
        for name in ("cargo", "rustc"):
            for version in ("1.95.0", "1.97.0", "1.96.0-nightly"):
                with self.subTest(name=name, version=version), self.assertRaises(ValueError):
                    toolchain.validate_version(name, name + " " + version + " (hash 2026-05-18)\n", "1.96.0")
            for output in ("rustup 1.96.0 (hash date)", name + " 1.96.0 (hash date)\nextra",
                           name + " 1.96.0suffix (hash date)", name + " 1.96.0"):
                with self.subTest(name=name, output=output), self.assertRaises(ValueError):
                    toolchain.validate_version(name, output, "1.96.0")


if __name__ == "__main__":
    unittest.main()
