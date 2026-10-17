"""CPU-host-only tests for deterministic QEMU QueryAbi input/guest setup."""
import gzip
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_queryabi_guest as replay


class QueryAbiReplayInputs(unittest.TestCase):
    @staticmethod
    def original(marker=replay.BOOT_MARKER, strict=True):
        init = (b"#!/bin/sh\nset -eu\n" if strict else b"#!/bin/sh\n") + marker + b"\n"
        base = [
            ("init", [1, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0], init),
            ("bin", [2, 0o040755, 0, 0, 2, 0, 0, 0, 0, 0, 0, 0, 0], b""),
        ]
        return gzip.compress(replay.pack(base), mtime=0)

    def test_guest_probe_is_injected_once_before_real_boot_marker(self):
        out = replay.build_guest_initramfs(self.original(), b"ELF synthetic probe")
        self.assertEqual(out, replay.build_guest_initramfs(self.original(), b"ELF synthetic probe"))
        entries = replay.unpack(gzip.decompress(out))
        self.assertEqual(len(entries), 3)
        init = next(x[2] for x in entries if x[0] == "init")
        self.assertEqual(init.count(b"/bin/hos2-queryabi"), 1)
        self.assertLess(init.index(b"/bin/hos2-queryabi"), init.index(replay.BOOT_MARKER))
        self.assertEqual(next(x[2] for x in entries if x[0] == "bin/hos2-queryabi"),
                         b"ELF synthetic probe")

    def test_fail_closed_missing_or_ambiguous_init_marker(self):
        for marker in (b"echo not-the-pinned-marker", replay.BOOT_MARKER * 2):
            with self.subTest(marker=marker), self.assertRaises(ValueError):
                replay.build_guest_initramfs(self.original(marker), b"ELF")

    def test_fail_closed_when_init_is_not_strict(self):
        with self.assertRaises(ValueError):
            replay.build_guest_initramfs(self.original(strict=False), b"ELF")

    def test_fail_closed_on_invalid_initramfs_and_oversized_probe(self):
        with self.assertRaises((ValueError, OSError, EOFError)):
            replay.build_guest_initramfs(b"broken", b"ELF")
        with self.assertRaises(ValueError):
            replay.build_guest_initramfs(self.original(), b"X" * (16 * 1024 * 1024 + 1))

    def test_cannot_self_authorize_a_different_kernel_hash(self):
        args = [
            "--kernel-elf", "/nonexistent-no-read",
            "--expected-kernel-sha256", "0" * 64,
            "--a01-initramfs", "/nonexistent-no-read",
            "--output", "/nonexistent-no-create",
        ]
        with self.assertRaisesRegex(ValueError, "unknown kernel candidate"):
            replay.main(args)

    def test_fail_closed_on_duplicated_guest_probe(self):
        entries = replay.unpack(gzip.decompress(self.original()))
        entries.append(("bin/hos2-queryabi",
                        [3, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0], b"old"))
        with self.assertRaises(ValueError):
            replay.build_guest_initramfs(gzip.compress(replay.pack(entries)), b"ELF")


if __name__ == "__main__":
    unittest.main()
