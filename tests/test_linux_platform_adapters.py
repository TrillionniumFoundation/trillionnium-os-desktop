from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests import _linux_platform_adapters_legacy as legacy

adapters = legacy.adapters


class LinuxPlatformAdapterTests(legacy.LinuxPlatformAdapterTests):
    """Retain the reviewed hostile corpus while extending publication coverage."""

    def test_bounded_reader_rejects_fifo_without_blocking_and_reads_procfs(self) -> None:
        super().test_bounded_reader_rejects_fifo_without_blocking_and_reads_procfs()

    def test_wayland_connection_remains_bound_across_endpoint_replacement(self) -> None:
        super().test_wayland_connection_remains_bound_across_endpoint_replacement()

    def test_literal_url_policy_matches_connected_address_policy(self) -> None:
        super().test_literal_url_policy_matches_connected_address_policy()


class AtomicPublicationRegressionTests(unittest.TestCase):
    def test_store_root_ancestor_symlink_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            parent = root / "real"
            parent.mkdir()
            (parent / "store").mkdir(mode=0o700)
            (root / "link").symlink_to(parent, target_is_directory=True)
            with self.assertRaises(adapters.PathRefused):
                adapters.AtomicFileStore(root / "link/store")

    def test_reconciliation_requires_file_and_directory_durability(self) -> None:
        data = b"durable-fact"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with adapters.AtomicFileStore(root) as store:
                store.write("current.bin", data)
                with mock.patch.object(adapters.os, "fsync", side_effect=OSError("durability unavailable")) as fsync:
                    with self.assertRaises(OSError):
                        store.reconcile("current.bin", expected_sha256=hashlib.sha256(data).hexdigest(), expected_bytes=len(data))
                    self.assertGreater(fsync.call_count, 0)

    def test_reconciliation_refuses_detached_parent_and_hardlinked_leaf(self) -> None:
        data = b"durable-fact"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "nested"
            nested.mkdir(mode=0o700)
            original_read = adapters._read_regular_fd
            with adapters.AtomicFileStore(root) as store:
                store.write("nested/current.bin", data)
                def substitute(descriptor: int, maximum: int):
                    result = original_read(descriptor, maximum)
                    nested.rename(root / "detached")
                    nested.mkdir(mode=0o700)
                    return result
                with mock.patch.object(adapters, "_read_regular_fd", substitute):
                    with self.assertRaisesRegex(adapters.PathRefused, "parent pathname"):
                        store.reconcile("nested/current.bin", expected_sha256=hashlib.sha256(data).hexdigest(), expected_bytes=len(data))
                (root / "detached").rename(root / "restored")
                os.link(root / "restored/current.bin", nested / "current.bin")
                with self.assertRaises(adapters.PathRefused):
                    store.reconcile("nested/current.bin", expected_sha256=hashlib.sha256(data).hexdigest(), expected_bytes=len(data))

    def test_staging_symlink_substitution_refuses_and_preserves_foreign_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "store"
            root.mkdir(mode=0o700)
            outside = root.parent / "outside"
            outside.write_bytes(b"attacker")
            original_fsync = os.fsync
            with adapters.AtomicFileStore(root) as store:
                def substitute(descriptor: int) -> None:
                    original_fsync(descriptor)
                    if stat.S_ISREG(os.fstat(descriptor).st_mode):
                        temporary = next(root.glob(".hepta-tmp-*"))
                        temporary.unlink()
                        temporary.symlink_to(outside)
                with mock.patch.object(adapters.os, "fsync", substitute):
                    with self.assertRaises(adapters.PathRefused):
                        store.write("current.bin", b"expected")
                self.assertFalse((root / "current.bin").exists())
                self.assertTrue(next(root.glob(".hepta-tmp-*")).is_symlink())
                self.assertEqual(outside.read_bytes(), b"attacker")

    def test_post_publication_substitution_is_indeterminate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            original_fsync = os.fsync
            with adapters.AtomicFileStore(root) as store:
                def substitute(descriptor: int) -> None:
                    original_fsync(descriptor)
                    if stat.S_ISDIR(os.fstat(descriptor).st_mode) and (root / "current.bin").exists():
                        (root / "current.bin").unlink()
                        (root / "current.bin").write_bytes(b"attacker")
                with mock.patch.object(adapters.os, "fsync", substitute):
                    with self.assertRaises(adapters.PublicationIndeterminate):
                        store.write("current.bin", b"expected")

    def test_parent_directory_substitution_cannot_publish_into_a_detached_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "nested"
            nested.mkdir(mode=0o700)
            original_fsync = os.fsync
            with adapters.AtomicFileStore(root) as store:
                def substitute(descriptor: int) -> None:
                    original_fsync(descriptor)
                    if stat.S_ISREG(os.fstat(descriptor).st_mode):
                        nested.rename(root / "saved")
                        nested.mkdir(mode=0o700)
                with mock.patch.object(adapters.os, "fsync", substitute):
                    with self.assertRaisesRegex(adapters.PathRefused, "parent pathname"):
                        store.write("nested/current.bin", b"expected")
                self.assertFalse((root / "saved/current.bin").exists())
                self.assertFalse((nested / "current.bin").exists())

    def test_noncanonical_paths_and_untrusted_parent_custody_are_refused(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "nested"
            nested.mkdir(mode=0o777)
            nested.chmod(0o777)
            with adapters.AtomicFileStore(root) as store:
                for name in ("./current.bin", "nested//current.bin", "current.bin/"):
                    with self.subTest(name=name), self.assertRaises(adapters.PathRefused):
                        store.write(name, b"private")
                with self.assertRaisesRegex(adapters.PathRefused, "writable"):
                    store.write("nested/current.bin", b"private")
                self.assertFalse((nested / "current.bin").exists())

    def test_exclusive_temp_collision_preserves_preexisting_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            stale = root / (".hepta-tmp-" + "a" * 32)
            stale.write_bytes(b"original")
            with adapters.AtomicFileStore(root) as store:
                with mock.patch.object(adapters.secrets, "token_hex", return_value="a" * 32):
                    with self.assertRaises(FileExistsError):
                        store.write("current.bin", b"replacement")
            self.assertEqual(stale.read_bytes(), b"original")
            self.assertFalse((root / "current.bin").exists())

    def test_deadlines_and_entropy_refuse_noninteger_or_nonfinite_bounds(self) -> None:
        for timeout in (float("nan"), float("inf"), 1.0, True, "1"):
            with self.subTest(timeout=timeout), self.assertRaises(adapters.DeadlineExpired):
                adapters.MonotonicClock().deadline_ns(timeout)
        for length in (1.0, True, "1", float("nan")):
            with self.subTest(length=length), self.assertRaises(adapters.PlatformError):
                adapters.OsEntropy.read(length)

    def test_atomic_file_store_refuses_existing_destination(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            destination = root / "current.bin"
            destination.write_bytes(b"original")
            destination.chmod(0o600)
            with adapters.AtomicFileStore(root) as store:
                with self.assertRaisesRegex(
                    adapters.PathRefused,
                    "destination exists; replacement is not authorized",
                ):
                    store.write("current.bin", b"replacement")
            self.assertEqual(destination.read_bytes(), b"original")
            self.assertFalse(
                any(item.name.startswith(".hepta-tmp-") for item in root.iterdir())
            )

    def test_atomic_file_store_reports_post_publication_uncertainty(self) -> None:
        data = b"durable-no-replace-fact"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with adapters.AtomicFileStore(root) as store:
                with mock.patch.object(
                    store,
                    "_read_destination",
                    side_effect=OSError("forced post-publication readback failure"),
                ):
                    with self.assertRaises(
                        adapters.PublicationIndeterminate
                    ) as raised:
                        store.write("current.bin", data)
                uncertainty = raised.exception
                self.assertEqual(uncertainty.receipt.bytes_written, len(data))
                self.assertEqual(
                    uncertainty.receipt.sha256,
                    hashlib.sha256(data).hexdigest(),
                )
                self.assertIsNotNone(uncertainty.destination_device)
                self.assertIsNotNone(uncertainty.destination_inode)
                self.assertEqual((root / "current.bin").read_bytes(), data)
                reconciled = store.reconcile(
                    "current.bin",
                    expected_sha256=hashlib.sha256(data).hexdigest(),
                    expected_bytes=len(data),
                )
                self.assertEqual(reconciled.sha256, uncertainty.receipt.sha256)
                self.assertEqual(reconciled.bytes_written, len(data))
                self.assertFalse(
                    any(item.name.startswith(".hepta-tmp-") for item in root.iterdir())
                )


if __name__ == "__main__":
    unittest.main()
