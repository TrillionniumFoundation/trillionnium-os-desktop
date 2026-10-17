"""Disposable archive safety regressions: no real credentials, QEMU or devices."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

import archive as archive_module
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
        # The digest manifest binds the bytes actually archived on disk.
        lines = (self.dest / "evidence.sha256").read_text().splitlines()
        self.assertEqual(len(lines), 3)
        for line in lines:
            digest, sep, name = line.partition("  ")
            self.assertEqual(sep, "  ")
            self.assertEqual(hashlib.sha256((self.dest / name).read_bytes()).hexdigest(), digest)

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

    def test_external_hardlink_is_not_silently_archived(self):
        outside = self.root / "dummy-private.json"
        outside.write_text("stand-in data; not a real secret")
        (self.source / "linked.json").hardlink_to(outside)
        with self.assertRaises(ValueError):
            archive(self.source, self.dest)
        self.assertFalse(self.dest.exists())

    def test_special_fixed_lock_cannot_follow_symlink(self):
        (self.source / "evidence.log").write_text("regular")
        (self.source / "harness").mkdir()
        outside = self.root / "dummy.lock"
        outside.write_bytes(b"dummy-lock")
        (self.source / "harness" / "Cargo.lock").symlink_to(outside)
        with self.assertRaises(ValueError):
            archive(self.source, self.dest)

    def test_special_pinned_inputs_are_archived_without_symlink_traversal(self):
        (self.source / "regular.json").write_text("ordinary")
        (self.source / "harness").mkdir()
        (self.source / "harness" / "Cargo.lock").write_text("locked deps")
        (self.source / "rust-toolchain.toml").write_text("pinned compiler")
        self.assertEqual(archive(self.source, self.dest), 3)
        self.assertEqual((self.dest / "harness.Cargo.lock").read_text(), "locked deps")
        self.assertEqual((self.dest / "rust-toolchain.toml").read_text(), "pinned compiler")

    def test_fixed_input_destination_name_collision_rejected(self):
        (self.source / "harness.Cargo.lock").write_text("decoy")
        (self.source / "harness").mkdir()
        (self.source / "harness" / "Cargo.lock").write_text("real")
        with self.assertRaises(ValueError):
            archive(self.source, self.dest)
        self.assertTrue((self.dest / ".archive-incomplete").is_file())
        self.assertFalse((self.dest / "evidence.sha256").exists())

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

    def test_reserved_index_paths_cannot_replace_evidence(self):
        for candidate in ("archive.json", "archive.json/case.json", "evidence.sha256/case.json"):
            with self.subTest(candidate=candidate), tempfile.TemporaryDirectory() as temp:
                source = Path(temp) / "source"
                source.mkdir()
                path = source / candidate
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("selected evidence must not be overwritten")
                destination = Path(temp) / "bundle"
                with self.assertRaises(ValueError):
                    archive(source, destination)
                self.assertFalse(destination.exists())

    def test_hardlink_added_between_lstat_and_open_is_rejected(self):
        file = self.source / "normal.txt"
        file.write_text("stand-in data")
        original_open = os.open

        def racing_open(name, flags, *args, **kwargs):
            if name == "normal.txt":
                os.link(file, self.root / "external-link.txt")
            return original_open(name, flags, *args, **kwargs)

        with mock.patch.object(archive_module.os, "open", racing_open):
            with self.assertRaises(ValueError):
                archive(self.source, self.dest)
        self.assertFalse(self.dest.exists())

    def test_file_changed_between_lstat_and_open_is_rejected(self):
        file = self.source / "normal.txt"
        file.write_text("before")
        original_open = os.open

        def racing_open(name, flags, *args, **kwargs):
            if name == "normal.txt":
                file.write_text("replacement contents")
            return original_open(name, flags, *args, **kwargs)

        with mock.patch.object(archive_module.os, "open", racing_open):
            with self.assertRaises(ValueError):
                archive(self.source, self.dest)
        self.assertFalse(self.dest.exists())

    def test_directory_walk_stays_on_open_root_after_path_replacement(self):
        (self.source / "normal.txt").write_text("original root")
        original_fwalk = os.fwalk

        def racing_fwalk(*args, **kwargs):
            self.source.rename(self.root / "held-original")
            self.source.mkdir()
            (self.source / "foreign.txt").write_text("replacement root")
            yield from original_fwalk(*args, **kwargs)

        with mock.patch.object(archive_module.os, "fwalk", racing_fwalk):
            self.assertEqual(archive(self.source, self.dest), 1)
        self.assertEqual((self.dest / "normal.txt").read_text(), "original root")
        self.assertFalse((self.dest / "foreign.txt").exists())

    def test_root_replaced_before_open_is_rejected(self):
        (self.source / "normal.txt").write_text("original root")
        original_open = os.open

        def racing_open(name, flags, *args, **kwargs):
            if name == self.source:
                self.source.rename(self.root / "held-original")
                self.source.mkdir()
                (self.source / "foreign.txt").write_text("replacement root")
            return original_open(name, flags, *args, **kwargs)

        with mock.patch.object(archive_module.os, "open", racing_open):
            with self.assertRaises(ValueError):
                archive(self.source, self.dest)
        self.assertFalse(self.dest.exists())

    def test_selected_fifo_is_rejected_without_blocking(self):
        os.mkfifo(self.source / "device.json")
        with self.assertRaises(ValueError):
            archive(self.source, self.dest)
        self.assertFalse(self.dest.exists())

    def test_total_limit_marks_new_bundle_incomplete_without_recursive_deletion(self):
        (self.source / "first.json").write_bytes(b"12345")
        (self.source / "second.json").write_bytes(b"67890")
        with mock.patch.object(archive_module, "MAX_TOTAL_BYTES", 8):
            with self.assertRaises(ValueError):
                archive(self.source, self.dest)
        self.assertTrue((self.dest / ".archive-incomplete").is_file())
        self.assertFalse((self.dest / "evidence.sha256").exists())


    def test_failed_cleanup_cannot_erase_a_swapped_foreign_directory(self):
        # A same-UID actor swaps an unrelated REAL directory into the output
        # path immediately before an old-style recursive failure cleanup.
        (self.source / "a-first.json").write_text("partial evidence")
        stand_in = self.root / "stand-in.json"
        stand_in.write_text("dummy")
        (self.source / "z-link.json").symlink_to(stand_in)
        foreign = self.root / "valuable"
        foreign.mkdir()
        (foreign / "keep.txt").write_text("keep me")
        from shutil import rmtree as actual_rmtree

        def substitute_and_delete(path, *args, **kwargs):
            if Path(path) == self.dest:
                self.dest.rename(self.root / "parked-partial")
                foreign.rename(self.dest)
            return actual_rmtree(path, *args, **kwargs)

        with mock.patch("shutil.rmtree", side_effect=substitute_and_delete):
            with self.assertRaises(ValueError):
                archive(self.source, self.dest)

        self.assertTrue(
            (foreign / "keep.txt").exists() or (self.dest / "keep.txt").exists(),
            "failed cleanup deleted unrelated pre-existing files",
        )

    def test_destination_subdirectory_swap_cannot_write_outside(self):
        # A same-UID actor replaces an output subdirectory after mkdir. A
        # pathname-based write follows the replacement symlink and archives
        # bytes OUTSIDE the output root; directory-FD writes must reject it.
        (self.source / "case").mkdir()
        (self.source / "case" / "evidence.json").write_bytes(b"INTERNAL_EVIDENCE")
        outside = self.root / "outside"
        outside.mkdir()
        original_mkdir = os.mkdir
        swapped = False

        def swap_after_mkdir(path, mode=0o777, *, dir_fd=None):
            nonlocal swapped
            result = original_mkdir(path, mode, dir_fd=dir_fd)
            if Path(path).name == "case" and not swapped:
                swapped = True
                (self.dest / "case").rename(self.dest / "parked-case")
                (self.dest / "case").symlink_to(outside, target_is_directory=True)
            return result

        with mock.patch.object(archive_module.os, "mkdir", side_effect=swap_after_mkdir):
            with self.assertRaises((OSError, ValueError)):
                archive(self.source, self.dest)
        self.assertTrue(swapped)
        self.assertFalse((outside / "evidence.json").exists())


if __name__ == "__main__":
    unittest.main()
