"""CPU-host-only tests for deterministic QEMU QueryAbi input/guest setup."""
import gzip
import hashlib
import os
import subprocess
import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

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


    def test_replay_rejects_gzip_expansion_over_limit(self):
        inflated = b"X" * 1025
        compressed = gzip.compress(inflated, mtime=0)
        self.assertLess(len(compressed), 1024)
        with self.assertRaisesRegex(ValueError, "decompression limit"):
            replay.decode_bounded_initramfs(compressed, max_unpacked=1024)
        self.assertEqual(
            replay.decode_bounded_initramfs(compressed, max_unpacked=1025),
            inflated,
        )

    def test_pinned_input_accepts_exact_regular_bytes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "kernel"
            data = b"synthetic pinned kernel bytes"
            path.write_bytes(data)
            self.assertEqual(
                replay.read_pinned_file(path, hashlib.sha256(data).hexdigest()),
                data,
            )

    def test_pinned_input_rejects_symlink_without_reading_outside(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            external = root / "outside"
            external.write_bytes(b"dummy outside data")
            target = root / "kernel"
            target.symlink_to(external)
            with self.assertRaises(OSError):
                replay.read_pinned_file(
                    target, hashlib.sha256(external.read_bytes()).hexdigest()
                )

    def test_pinned_input_rejects_fifo_and_oversize(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pipe = root / "fifo"
            os.mkfifo(pipe)
            with self.assertRaises(ValueError):
                replay.read_pinned_file(pipe, "0" * 64)
            oversized = root / "oversized"
            oversized.write_bytes(b"A" * 10)
            with self.assertRaises(ValueError):
                replay.read_pinned_file(
                    oversized, hashlib.sha256(b"A" * 10).hexdigest(), limit=9
                )

    def test_pinned_input_rejects_external_hard_link(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            outside = root / "outside"
            outside.write_bytes(b"stand-in only")
            alias = root / "alias"
            os.link(outside, alias)
            with self.assertRaises(ValueError):
                replay.read_pinned_file(
                    alias, hashlib.sha256(b"stand-in only").hexdigest()
                )


    def test_qemu_command_uses_immutable_inherited_fds_not_reopened_paths(self):
        # Synthetic compiler/QEMU: this tests the *host launch boundary*.
        # The original Asterinas kernel is not run in this unit test.
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result"
            kernel = b"known SHA-validated kernel stand-in"
            bios = b"known SHA-validated BIOS stand-in"
            original = self.original()
            seen_fds = ()

            def simulate_native_tools(command, **kwargs):
                nonlocal seen_fds
                if command[0] == "cc":
                    Path(command[-1]).write_bytes(b"ELF synthetic guest probe")
                    return subprocess.CompletedProcess(command, 0, "", "")
                self.assertEqual(command[0], "synthetic-qemu")
                self.assertIs(kwargs.get("preexec_fn"), replay.limit_serial_file)
                seen_fds = tuple(kwargs.get("pass_fds", ()))
                self.assertEqual(len(seen_fds), 3)
                for option, expected in (("-kernel", kernel), ("-bios", bios)):
                    fd_path = command[command.index(option) + 1]
                    self.assertTrue(fd_path.startswith("/proc/self/fd/"), fd_path)
                    fd = int(fd_path.rsplit("/", 1)[1])
                    self.assertIn(fd, seen_fds)
                    self.assertEqual(os.pread(fd, len(expected), 0), expected)
                    with self.assertRaises(OSError):
                        os.pwrite(fd, b"CORRUPT", 0)
                initrd_path = command[command.index("-initrd") + 1]
                self.assertTrue(initrd_path.startswith("/proc/self/fd/"))
                initrd_fd = int(initrd_path.rsplit("/", 1)[1])
                self.assertIn(initrd_fd, seen_fds)
                injected = os.pread(initrd_fd, os.fstat(initrd_fd).st_size, 0)
                entries = replay.unpack(gzip.decompress(injected))
                self.assertEqual(
                    next(entry[2] for entry in entries if entry[0] == "bin/hos2-queryabi"),
                    b"ELF synthetic guest probe",
                )
                kwargs["stdout"].write(
                    (replay.EXPECTED_SUCCESS + "\nTRILLIONNIUM_A01_BOOT_OK\n").encode()
                )
                return subprocess.CompletedProcess(command, 33)

            with patch.object(
                replay, "read_pinned_file", side_effect=(kernel, original, bios)
            ), patch.object(replay.subprocess, "run", side_effect=simulate_native_tools):
                self.assertEqual(
                    replay.main([
                        "--kernel-elf", "/original-kernel-path",
                        "--expected-kernel-sha256", replay.A05_PINNED_KERNEL_SHA,
                        "--a01-initramfs", "/original-initrd-path",
                        "--bios", "/original-bios-path",
                        "--qemu", "synthetic-qemu", "--output", str(output),
                    ]),
                    0,
                )
            self.assertEqual(len(seen_fds), 3)
            for fd in seen_fds:
                with self.assertRaises(OSError):
                    os.fstat(fd)
            result = __import__("json").loads((output / "result.json").read_text())
            self.assertTrue(result["passed"])
            self.assertTrue(result["guest_queryabi_ok"])

if __name__ == "__main__":
    unittest.main()
