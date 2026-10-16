"""Disposable archive safety regressions: no real credentials, QEMU or devices."""
import gzip
import json
from pathlib import Path
import tempfile
import unittest

from archive import archive, MAX_FILE_BYTES


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "generated"
        self.source.mkdir()
        self.dest = self.root / "bundle"

    def test_regular_log_roundtrip_and_deterministic_gzip(self):
        (self.source / "case-1").mkdir()
        (self.source / "case-1" / "qemu.log").write_bytes(b"RAW\x00serial\xff")
        (self.source / "result.json").write_text('{"ok":false}\n')
        (self.source / "work").mkdir()
        (self.source / "work" / "secrets.json").write_text("excluded")
        self.assertEqual(archive(self.source, self.dest), 2)
        manifest = json.loads((self.dest / "archive.json").read_text())
        self.assertEqual({x["source"] for x in manifest["files"]}, {"case-1/qemu.log", "result.json"})
        self.assertEqual(gzip.decompress((self.dest / "case-1/qemu.log.gz").read_bytes()),
                         b"RAW\x00serial\xff")
        self.assertFalse((self.dest / "work").exists())
        self.assertTrue((self.dest / "evidence.sha256").is_file())

    def test_missing_or_regular_file_source_rejected_without_creating_bundle(self):
        (self.root / "ordinary.txt").write_text("a")
        for candidate in (self.root / "missing", self.root / "ordinary.txt"):
            with self.subTest(candidate=candidate), self.assertRaises(ValueError):
                archive(candidate, self.dest)
            self.assertFalse(self.dest.exists())

    def test_symlink_source_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(ValueError):
            archive(alias, self.dest)

    def test_symlink_to_external_dummy_log_denied(self):
        outside = self.root / "dummy-outside.json"
        outside.write_bytes(b"dummy-not-a-credential")
        (self.source / "case.json").symlink_to(outside)
        with self.assertRaises(ValueError):
            archive(self.source, self.dest)
        self.assertFalse(self.dest.exists())

    def test_symlink_directory_denied(self):
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "log.json").write_bytes(b"dummy")
        (self.source / "peer").symlink_to(outside, target_is_directory=True)
        with self.assertRaises(ValueError):
            archive(self.source, self.dest)

    def test_special_fixed_lock_cannot_follow_symlink(self):
        (self.source / "evidence.log").write_text("regular")
        (self.source / "harness").mkdir()
        outside = self.root / "dummy.lock"
        outside.write_bytes(b"dummy-lock")
        (self.source / "harness" / "Cargo.lock").symlink_to(outside)
        with self.assertRaises(ValueError):
            archive(self.source, self.dest)

    def test_empty_archive_fails_closed(self):
        (self.source / "code.rs").write_text("no evidence")
        with self.assertRaises(ValueError):
            archive(self.source, self.dest)
        self.assertFalse(self.dest.exists())

    def test_existing_destination_is_preserved(self):
        self.dest.mkdir()
        (self.dest / "other").write_text("foreign")
        (self.source / "evidence.json").write_text("file")
        with self.assertRaises(FileExistsError):
            archive(self.source, self.dest)
        self.assertEqual((self.dest / "other").read_text(), "foreign")

    def test_bounded_read_rejects_sparse_oversize_without_allocating(self):
        file = self.source / "huge.json"
        with file.open("wb") as output:
            output.seek(MAX_FILE_BYTES)
            output.write(b"x")
        with self.assertRaises(ValueError):
            archive(self.source, self.dest)
        self.assertFalse(self.dest.exists())

    def test_unchanged_original_file_is_required(self):
        (self.source / "normal.txt").write_text("normal")
        self.assertEqual(archive(self.source, self.dest), 1)
        self.assertEqual((self.source / "normal.txt").read_text(), "normal")


if __name__ == "__main__":
    unittest.main()
