from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests._linux_platform_adapters_legacy import LinuxPlatformAdapterTests, adapters


class AtomicPublicationRegressionTests(unittest.TestCase):
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
