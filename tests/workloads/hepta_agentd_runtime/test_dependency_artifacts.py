#!/usr/bin/env python3
"""Real supplier files exercise explicit pair pinning and frozen-input checks."""
import argparse
from pathlib import Path
import tempfile
import unittest

import dependency_artifacts as artifacts


class DependencyArtifactsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.archive = self.root / "supplier.a.gz"
        self.bindings = self.root / "binding.rs"
        self.archive.write_bytes(b"bounded fixture archive bytes")
        self.bindings.write_bytes(b"// bounded fixture binding bytes\n")
        self.out = self.root / "out"
        self.out.mkdir()

    def args(self, *extra):
        parser = argparse.ArgumentParser()
        artifacts.add_arguments(parser)
        return parser.parse_args(list(extra))

    def pair(self):
        return self.args("--v8-archive", str(self.archive),
                         "--expected-v8-archive-sha256", artifacts.sha(self.archive),
                         "--v8-bindings", str(self.bindings),
                         "--expected-v8-bindings-sha256", artifacts.sha(self.bindings))

    def test_default_supplies_no_environment_override(self):
        record = artifacts.selected(self.args())
        self.assertEqual(record["mode"], "original-build-default")
        self.assertEqual(artifacts.freeze(record, self.out), {})
        artifacts.verify_frozen(record)
        self.assertEqual(list(self.out.iterdir()), [])

    def test_complete_pair_is_copied_readonly_and_receipted(self):
        record = artifacts.selected(self.pair())
        env = artifacts.freeze(record, self.out)
        self.assertEqual(set(env), {"RUSTY_V8_ARCHIVE", "RUSTY_V8_SRC_BINDING_PATH"})
        for name, item in record["frozen"].items():
            path = Path(item["path"])
            self.assertTrue(path.is_relative_to(self.out))
            self.assertEqual(path.stat().st_mode & 0o777, 0o444)
            self.assertEqual(artifacts.sha(path), record["supplied"][name]["sha256"])
        # Once frozen, Cargo reads retained bytes even if a supplier cache moves.
        self.archive.write_bytes(b"a future supplier update")
        artifacts.verify_frozen(record)

    def test_partial_pair_is_rejected_before_any_output(self):
        for flags in (("--v8-archive", str(self.archive)),
                      ("--v8-archive", str(self.archive), "--expected-v8-archive-sha256", artifacts.sha(self.archive)),
                      ("--expected-v8-bindings-sha256", artifacts.sha(self.bindings))):
            with self.subTest(flags=flags), self.assertRaisesRegex(ValueError, "required together"):
                artifacts.selected(self.args(*flags))
        self.assertEqual(list(self.out.iterdir()), [])

    def test_wrong_digest_rejects_real_supplier_bytes(self):
        args = self.pair()
        args.expected_v8_archive_sha256 = "0" * 64
        with self.assertRaisesRegex(ValueError, "SHA-256 differs"):
            artifacts.selected(args)

    def test_changed_supplier_between_selection_and_copy_is_rejected(self):
        record = artifacts.selected(self.pair())
        self.archive.write_bytes(b"replaced after pin check")
        with self.assertRaisesRegex(ValueError, "SHA-256 differs"):
            artifacts.freeze(record, self.out)

    def test_modified_frozen_file_is_rejected(self):
        record = artifacts.selected(self.pair())
        artifacts.freeze(record, self.out)
        path = Path(record["frozen"]["bindings"]["path"])
        path.chmod(0o644)
        path.write_bytes(b"unreviewed frozen bytes")
        with self.assertRaisesRegex(ValueError, "SHA-256 differs"):
            artifacts.verify_frozen(record)

    def test_symlink_and_alias_pair_are_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(self.archive)
        args = self.pair()
        args.v8_archive = alias
        with self.assertRaisesRegex(ValueError, "not a symlink"):
            artifacts.selected(args)
        args = self.pair()
        args.v8_bindings = self.archive
        args.expected_v8_bindings_sha256 = args.expected_v8_archive_sha256
        with self.assertRaisesRegex(ValueError, "distinct files"):
            artifacts.selected(args)

    def test_noncanonical_parent_and_malformed_digest_are_rejected(self):
        alias = self.root / "linked-output"
        alias.symlink_to(self.root, target_is_directory=True)
        args = self.pair()
        args.v8_archive = alias / self.archive.name
        with self.assertRaisesRegex(ValueError, "canonical"):
            artifacts.selected(args)
        args = self.pair()
        args.expected_v8_bindings_sha256 = "z" * 64
        with self.assertRaisesRegex(ValueError, "explicit SHA-256"):
            artifacts.selected(args)


if __name__ == "__main__":
    unittest.main()
