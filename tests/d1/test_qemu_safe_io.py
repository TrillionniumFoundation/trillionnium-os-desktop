from __future__ import annotations

import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

import qemu_safe_io  # noqa: E402


class QemuSafeIoTests(unittest.TestCase):
    def test_atomic_write_rejects_symlink_and_preserves_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "outside.txt"
            target.write_text("sentinel", encoding="utf-8")
            alias = root / "result.json"
            alias.symlink_to(target)

            with self.assertRaises(qemu_safe_io.UnsafePathError):
                qemu_safe_io.write_text(alias, "forged")
            self.assertEqual(target.read_text(encoding="utf-8"), "sentinel")

    def test_regular_reader_and_copy_reject_links_and_special_files(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source.txt"
            source.write_text("payload", encoding="utf-8")
            destination = root / "nested" / "copy.txt"
            qemu_safe_io.copy_regular(source, destination)
            self.assertEqual(destination.read_text(encoding="utf-8"), "payload")

            alias = root / "alias.txt"
            alias.symlink_to(source)
            with self.assertRaises(qemu_safe_io.UnsafePathError):
                qemu_safe_io.read_bytes(alias)

            fifo = root / "fifo"
            os.mkfifo(fifo)
            with self.assertRaises(qemu_safe_io.UnsafePathError):
                qemu_safe_io.read_bytes(fifo)

    def test_logged_command_captures_output_and_rejects_fifo(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / "stage.log"
            status = qemu_safe_io.run_logged(
                log,
                [sys.executable, "-c", "print('safe-stage')"],
            )
            self.assertEqual(status, 0)
            self.assertEqual(log.read_text(encoding="utf-8").strip(), "safe-stage")

            fifo = root / "fifo.log"
            os.mkfifo(fifo)
            with self.assertRaises(qemu_safe_io.UnsafePathError):
                qemu_safe_io.run_logged(
                    fifo,
                    [sys.executable, "-c", "print('must-not-block')"],
                )

    def test_truncate_uses_regular_descriptor(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / "new.log"
            qemu_safe_io.safe_truncate(log)
            self.assertTrue(log.is_file())
            self.assertEqual(stat.S_IFMT(log.stat().st_mode), stat.S_IFREG)

    def test_tail_retention_is_bounded_and_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            log = root / "large.log"
            log.write_bytes(b"0123456789")

            qemu_safe_io.truncate_tail(log, 4)

            self.assertEqual(log.read_bytes(), b"6789")

    def test_tail_retention_rejects_symlink_without_touching_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "target.log"
            target.write_bytes(b"0123456789")
            alias = root / "alias.log"
            alias.symlink_to(target)

            with self.assertRaises(qemu_safe_io.UnsafePathError):
                qemu_safe_io.truncate_tail(alias, 4)

            self.assertEqual(target.read_bytes(), b"0123456789")

    def test_tail_retention_rejects_negative_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            log = Path(temporary) / "large.log"
            log.write_bytes(b"payload")
            with self.assertRaises(ValueError):
                qemu_safe_io.truncate_tail(log, -1)


if __name__ == "__main__":
    unittest.main()
