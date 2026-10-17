"""Disposable archive safety regressions: no real credentials, QEMU or devices."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

import archive as archive_module
from archive import archive, MAX_FILE_BYTES


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        setting = os.environ.get("A01_ARCHIVE_CUSTODY_OUT")
        self.root = (Path(setting) / self._testMethodName
                     if setting and self._testMethodName.startswith("test_custody_")
                     else Path(self.temp.name))
        if self.root != Path(self.temp.name):
            self.root.mkdir(parents=True, exist_ok=False)
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
        self.assertEqual((self.dest / "harness.Cargo.lock").read_text(), "decoy")
        self.assertTrue((self.dest / ".archive-incomplete").is_file())
        self.assertFalse((self.dest / "archive.json").exists())

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
        for candidate in ("archive.json", "archive.json/case.json", "evidence.sha256/case.json",
                          ".archive-incomplete/case.json"):
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

    def test_total_limit_preserves_incomplete_new_custody(self):
        (self.source / "first.json").write_bytes(b"12345")
        (self.source / "second.json").write_bytes(b"67890")
        with mock.patch.object(archive_module, "MAX_TOTAL_BYTES", 8):
            with self.assertRaises(ValueError):
                archive(self.source, self.dest)
        self.assertEqual((self.dest / "first.json").read_bytes(), b"12345")
        self.assertTrue((self.dest / ".archive-incomplete").is_file())
        self.assertFalse((self.dest / "archive.json").exists())

    def test_custody_destination_subdirectory_swap_cannot_write_outside(self):
        (self.source / "case").mkdir()
        (self.source / "case/qemu.log").write_bytes(b"disposable selected log")
        outside = self.root / "outside"
        outside.mkdir()
        (outside / "keep.txt").write_bytes(b"foreign sentinel must survive")
        original_mkdir, fired = os.mkdir, []

        def swap_after_mkdir(path, mode=0o777, *, dir_fd=None):
            result = original_mkdir(path, mode, dir_fd=dir_fd)
            if Path(path).name == "case" and not fired:
                fired.append(True)
                (self.dest / "case").rename(self.root / "held-case")
                (self.dest / "case").symlink_to(outside, target_is_directory=True)
            return result

        error = None
        with mock.patch.object(archive_module.os, "mkdir", swap_after_mkdir):
            try:
                archive(self.source, self.dest)
            except (OSError, ValueError) as caught:
                error = str(caught)
        observation = {"kind": "real_filesystem_mkdir_boundary_swap_no_VM",
            "source_sha256": hashlib.sha256(Path(archive_module.__file__).read_bytes()).hexdigest(),
            "swap_fired": bool(fired), "archive_error": error,
            "outside_entries": sorted(path.name for path in outside.iterdir()),
            "outside_keep": (outside / "keep.txt").read_text(),
            "outside_archive_file_exists": (outside / "qemu.log.gz").exists()}
        (self.root / "observation.json").write_text(json.dumps(observation, indent=2) + "\n")
        self.assertTrue(fired)
        self.assertFalse(observation["outside_archive_file_exists"], observation)
        self.assertEqual(observation["outside_entries"], ["keep.txt"])
        self.assertIsNotNone(error)
        self.assertEqual(observation["outside_keep"], "foreign sentinel must survive")

    def test_custody_failed_cleanup_cannot_erase_swapped_foreign_directory(self):
        (self.source / "first.json").write_bytes(b"12345")
        (self.source / "second.json").write_bytes(b"67890")
        original_rmtree, fired = shutil.rmtree, []

        def swap_before_rmtree(path, *args, **kwargs):
            if Path(path) == self.dest and not fired:
                fired.append(True)
                self.dest.rename(self.root / "held-bundle")
                self.dest.mkdir()
                (self.dest / "keep.txt").write_bytes(b"foreign replacement must survive")
            return original_rmtree(path, *args, **kwargs)

        with mock.patch.object(archive_module, "MAX_TOTAL_BYTES", 8), \
                mock.patch.object(shutil, "rmtree", swap_before_rmtree):
            with self.assertRaises(ValueError):
                archive(self.source, self.dest)
        observation = {"kind": "real_filesystem_path_cleanup_boundary_swap_no_VM",
            "source_sha256": hashlib.sha256(Path(archive_module.__file__).read_bytes()).hexdigest(),
            "unsafe_rmtree_called": bool(fired), "destination_exists": self.dest.exists(),
            "foreign_keep_exists": (self.dest / "keep.txt").exists(),
            "owned_incomplete_marker": (self.dest / ".archive-incomplete").is_file()}
        (self.root / "observation.json").write_text(json.dumps(observation, indent=2) + "\n")
        self.assertFalse(fired, observation)
        self.assertTrue(observation["destination_exists"])
        self.assertTrue(observation["owned_incomplete_marker"])

    def test_custody_subdirectory_swap_after_open_keeps_writes_on_pinned_fd(self):
        (self.source / "case").mkdir()
        (self.source / "case/qemu.log").write_bytes(b"owned disposable log")
        outside = self.root / "outside"
        outside.mkdir()
        original_open, fired = os.open, []

        def swap_before_file_open(path, flags, *args, **kwargs):
            if path == "qemu.log.gz" and flags & os.O_CREAT and not fired:
                fired.append(True)
                (self.dest / "case").rename(self.root / "held-case")
                (self.dest / "case").symlink_to(outside, target_is_directory=True)
            return original_open(path, flags, *args, **kwargs)

        with mock.patch.object(archive_module.os, "open", swap_before_file_open):
            with self.assertRaises(ValueError):
                archive(self.source, self.dest)
        self.assertTrue(fired)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertEqual(gzip.decompress((self.root / "held-case/qemu.log.gz").read_bytes()),
                         b"owned disposable log")
        self.assertTrue((self.dest / ".archive-incomplete").is_file())

    def test_custody_root_swap_after_open_preserves_foreign_directory_and_owned_marker(self):
        (self.source / "first.json").write_bytes(b"owned payload")
        original_open, fired = os.open, []

        def swap_before_file_open(path, flags, *args, **kwargs):
            if path == "first.json" and flags & os.O_CREAT and not fired:
                fired.append(True)
                self.dest.rename(self.root / "held-bundle")
                self.dest.mkdir()
                (self.dest / "keep.txt").write_bytes(b"foreign replacement")
            return original_open(path, flags, *args, **kwargs)

        with mock.patch.object(archive_module.os, "open", swap_before_file_open):
            with self.assertRaises(ValueError):
                archive(self.source, self.dest)
        self.assertTrue(fired)
        self.assertEqual(sorted(path.name for path in self.dest.iterdir()), ["keep.txt"])
        self.assertEqual((self.dest / "keep.txt").read_bytes(), b"foreign replacement")
        self.assertEqual((self.root / "held-bundle/first.json").read_bytes(), b"owned payload")
        self.assertTrue((self.root / "held-bundle/.archive-incomplete").is_file())

    def test_custody_exclusive_output_open_preserves_racing_existing_file(self):
        (self.source / "first.json").write_bytes(b"owned payload")
        original_open, fired = os.open, []

        def add_foreign_before_open(path, flags, *args, **kwargs):
            if path == "first.json" and flags & os.O_CREAT and not fired:
                fired.append(True)
                descriptor = original_open(path, flags, *args, **kwargs)
                with os.fdopen(descriptor, "wb") as output:
                    output.write(b"foreign entry must not be overwritten")
            return original_open(path, flags, *args, **kwargs)

        with mock.patch.object(archive_module.os, "open", add_foreign_before_open):
            with self.assertRaises(FileExistsError):
                archive(self.source, self.dest)
        self.assertTrue(fired)
        self.assertEqual((self.dest / "first.json").read_bytes(), b"foreign entry must not be overwritten")
        self.assertTrue((self.dest / ".archive-incomplete").is_file())

    def test_custody_manifest_symlink_cannot_overwrite_external_bytes(self):
        (self.source / "first.json").write_bytes(b"owned payload")
        outside = self.root / "outside.json"
        outside.write_bytes(b"foreign index stand-in")
        original_write = archive_module.ArchiveOutput.write

        def add_index_symlink(owner, relative, payload, indexed=True):
            if relative == Path("archive.json"):
                (self.dest / "archive.json").symlink_to(outside)
            return original_write(owner, relative, payload, indexed)

        with mock.patch.object(archive_module.ArchiveOutput, "write", add_index_symlink):
            with self.assertRaises(FileExistsError):
                archive(self.source, self.dest)
        self.assertEqual(outside.read_bytes(), b"foreign index stand-in")
        self.assertTrue((self.dest / ".archive-incomplete").is_file())

    def test_custody_indexes_use_exact_written_payloads_without_path_walks_or_reads(self):
        (self.source / "case").mkdir()
        (self.source / "case/qemu.log").write_bytes(b"exact raw bytes")
        with mock.patch.object(Path, "rglob", side_effect=AssertionError("path traversal forbidden")), \
                mock.patch.object(Path, "read_bytes", side_effect=AssertionError("path re-read forbidden")):
            self.assertEqual(archive(self.source, self.dest), 1)
        self.assertFalse((self.dest / ".archive-incomplete").exists())
        rows = (self.dest / "evidence.sha256").read_text().splitlines()
        self.assertEqual(len(rows), 2)
        for row in rows:
            digest, name = row.split("  ", 1)
            self.assertEqual(hashlib.sha256((self.dest / name).read_bytes()).hexdigest(), digest)

    def test_custody_symlink_destination_parent_is_not_traversed(self):
        (self.source / "first.json").write_bytes(b"owned payload")
        outside = self.root / "outside"
        outside.mkdir()
        alias = self.root / "alias"
        alias.symlink_to(outside, target_is_directory=True)
        with self.assertRaises(OSError):
            archive(self.source, alias / "bundle")
        self.assertEqual(list(outside.iterdir()), [])


if __name__ == "__main__":
    unittest.main()
