#!/usr/bin/env python3
"""Finite controls for exact patch admission, independent of Rust execution."""
import importlib.util
from pathlib import Path
import unittest

SPEC = importlib.util.spec_from_file_location('materialization_verify', Path(__file__).with_name('verify.py'))
VERIFY = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFY)

BEFORE = b'first\noriginal\nlast\n'
PATCH = (b'--- a/tools/droidloom-source/src/lib.rs\n'
         b'+++ b/tools/droidloom-source/src/lib.rs\n'
         b'@@ -1,3 +1,4 @@\n first\n-original\n+changed\n+added\n last\n')


class ExactReplayTests(unittest.TestCase):
    def test_complete_exact_hunk_replays(self):
        self.assertEqual(VERIFY.strict_patch(BEFORE, PATCH), b'first\nchanged\nadded\nlast\n')

    def test_changed_preimage_or_context_is_rejected(self):
        for old in [b'first\ndrifted\nlast\n', b'changed\noriginal\nlast\n', b'first\noriginal\n']:
            with self.subTest(old=old), self.assertRaises(RuntimeError):
                VERIFY.strict_patch(old, PATCH)

    def test_offsets_counts_and_truncation_are_rejected(self):
        for bad in [PATCH.replace(b'-1,3', b'-2,3'), PATCH.replace(b'+1,4', b'+2,4'),
                    PATCH.replace(b'+1,4', b'+1,5'), PATCH[:-1]]:
            with self.subTest(patch=bad), self.assertRaises(RuntimeError):
                VERIFY.strict_patch(BEFORE, bad)

    def test_additional_file_or_path_escape_is_rejected(self):
        for bad in [PATCH + PATCH, PATCH.replace(b'b/tools/', b'b/../tools/', 1),
                    PATCH + b'--- a/other\n+++ b/other\n']:
            with self.subTest(patch=bad), self.assertRaises(RuntimeError):
                VERIFY.strict_patch(BEFORE, bad)


if __name__ == '__main__':
    unittest.main()
