#!/usr/bin/env python3
"""Re-run the REAL read-only A05 QueryAbi guest in a disposable pinned QEMU.

This is NOT a kernel build, authorization test, native HOS2 effect write,
Hepta durability proof, or hardware sign-off. It never changes a host cgroup,
device driver, data disk, network stack, firmware, or production service.
"""
import argparse
import gzip
import io
import hashlib
import json
import os
import stat
from pathlib import Path
import re
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "organ_backend"))
from run_guest_probe import pack, unpack  # already shipped A01 newc parser

A05_PINNED_KERNEL_SHA = "54c8a7a798cbbd80f1a8ce5f0144328815e63b413e79b0133206bcaaba607e4a"
A01_INITRD_SHA = "86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3"
SEABIOS_SHA = "1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735"
EXPECTED_SUCCESS = "HEPTA_QUERYABI_OK ops=QueryAbi_only, independent_sessions=yes, denied_invalid=yes"
BOOT_MARKER = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
MAX_SERIAL_BYTES = 8 * 1024 * 1024
MAX_INPUT_BYTES = 64 * 1024 * 1024
MAX_UNPACKED_INITRAMFS_BYTES = 64 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def read_pinned_file(path, expected_hash, limit=MAX_INPUT_BYTES):
    """Bound one pinned input by its opened FD; reject link/path swaps.

    The previous is_file/stat/read_bytes sequence re-resolved the path after
    validation and could follow a replacement link or read an oversized
    regular file before comparing its digest. Hash validation alone does not
    prevent an unbounded or device-backed read.
    """
    fd = None
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC)
        with os.fdopen(fd, "rb") as stream:
            fd = None
            before = os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
                    "input must be a regular nonlinked file")
            require(0 <= before.st_size <= limit, "pinned input too large")
            data = stream.read(limit + 1)
            after = os.fstat(stream.fileno())
            require(len(data) <= limit, "pinned input exceeds size bound")
            require(len(data) == before.st_size == after.st_size,
                    "pinned input changed size while reading")
            require((before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns)
                    == (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns),
                    "pinned input changed during read")
    finally:
        if fd is not None:
            os.close(fd)
    require(digest(data) == expected_hash, f"pinned input SHA256 mismatch: {path}")
    return data


def decode_bounded_initramfs(original_gzip, max_unpacked=MAX_UNPACKED_INITRAMFS_BYTES):
    """Reject a small compressed input before it can inflate without bound."""
    require(0 < max_unpacked <= MAX_UNPACKED_INITRAMFS_BYTES,
            "invalid initramfs decompression limit")
    with gzip.GzipFile(fileobj=io.BytesIO(original_gzip), mode="rb") as stream:
        data = stream.read(max_unpacked + 1)
        require(len(data) <= max_unpacked, "initramfs decompression limit exceeded")
        # Consume one final byte to surface truncated CRC/trailer and concatenated
        # gzip members without allowing unbounded extraction.
        require(stream.read(1) == b"", "initramfs decompression limit exceeded")
    return data


def build_guest_initramfs(original_gzip, compiled_probe):
    """Repack only in memory; never extract original cpio to the host."""
    require(len(original_gzip) <= 8 * 1024 * 1024, "compressed original initramfs too large")
    require(len(compiled_probe) <= 16 * 1024 * 1024, "guest probe too large")
    entries = unpack(decode_bounded_initramfs(original_gzip))
    require(unpack(pack(entries)) == entries, "original newc roundtrip mismatch")
    require(all(e[0].lstrip("./") != "bin/hos2-queryabi" for e in entries),
            "original initramfs already has QueryAbi probe")
    modified = []
    found_init = 0
    for name, fields, content in entries:
        if name.lstrip("./") == "init":
            require(content.count(BOOT_MARKER) == 1, "init marker missing or ambiguous")
            require(b"set -eu" in content, "init lacks fail-closed shell flags")
            content = content.replace(BOOT_MARKER, b"/bin/hos2-queryabi\n" + BOOT_MARKER)
            found_init += 1
        modified.append((name, fields, content))
    require(found_init == 1, "must find exactly one original init")
    ino = max((e[1][0] for e in entries), default=0) + 1
    # Canonical newc entry. Probe binary runs as root INSIDE disposable guest.
    fields = [ino, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
    modified.append(("bin/hos2-queryabi", fields, compiled_probe))
    changed = unpack(pack(modified))
    require(len(changed) == len(entries) + 1, "repacked initramfs lost an entry")
    return gzip.compress(pack(modified), mtime=0)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kernel-elf", type=Path, required=True)
    parser.add_argument("--expected-kernel-sha256", required=True)
    parser.add_argument("--a01-initramfs", type=Path, required=True)
    parser.add_argument("--bios", type=Path, default=Path("/usr/share/seabios/bios-256k.bin"))
    parser.add_argument("--qemu", default="qemu-system-x86_64")
    parser.add_argument("--cc", default="cc")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args(argv)

    require(re.fullmatch(r"[0-9a-f]{64}", args.expected_kernel_sha256) is not None,
            "expected kernel SHA256 must be 64 lowercase hex chars")
    # Caller-supplied expected hashes are not an independent provenance check:
    # pin the exact A05 ELF already tested on the real QEMU guest.
    require(args.expected_kernel_sha256 == A05_PINNED_KERNEL_SHA,
            "unknown kernel candidate: A05 source/hash must be re-audited before replay")
    require(1 <= args.timeout <= 120, "QEMU timeout must be 1..120s")
    root = Path(__file__).resolve().parents[3]
    lock = json.loads((root / "support/upstream-lock.json").read_text(encoding="utf-8"))
    require(lock["kernel"]["commit"] == "c4b7ed575b7b32773475b194d2ad41fb6d03765b"
            and lock["kernel"]["toolchain"] == "nightly-2026-07-21"
            and lock["hepta"]["commit"] == "f8c9419df6ddeb36ff8b522a50219981fb8d9345",
            "fixed Asterinas/Hepta inputs drifted")
    kernel = read_pinned_file(args.kernel_elf, args.expected_kernel_sha256)
    original = read_pinned_file(args.a01_initramfs, A01_INITRD_SHA, 8 * 1024 * 1024)
    bios = read_pinned_file(args.bios, SEABIOS_SHA, 2 * 1024 * 1024)

    guest_source = Path(__file__).with_name("queryabi_guest.c")
    require(guest_source.is_file() and not guest_source.is_symlink(),
            "missing/symlinked real A05 guest source")
    output = args.output.absolute()
    require(not output.exists() and not output.is_symlink(),
            "output must be a new directory")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    guest_elf = output / "hos2-queryabi"
    compiler = [args.cc, "-std=c11", "-O2", "-Wall", "-Wextra",
                "-Werror", "-static", str(guest_source), "-o", str(guest_elf)]
    compile_run = subprocess.run(compiler, capture_output=True, text=True, timeout=60)
    (output / "compile.log").write_text(compile_run.stdout + compile_run.stderr, encoding="utf-8")
    require(compile_run.returncode == 0, "static guest C compilation failed")
    compiled = guest_elf.read_bytes()
    initrd = build_guest_initramfs(original, compiled)
    (output / "initramfs.cpio.gz").write_bytes(initrd)
    # Kernel and BIOS inputs remain at their original, independently hashed paths.
    args_qemu = [
        args.qemu, "-kernel", str(args.kernel_elf.absolute()),
        "-initrd", str((output / "initramfs.cpio.gz").absolute()),
        "-append", "earlycon console=ttyS0 loglevel=info SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --",
        "-machine", "q35", "-accel", "tcg", "-cpu", "max",
        "-bios", str(args.bios.absolute()), "-m", "512M", "-smp", "1",
        "-nodefaults", "-no-user-config", "-no-reboot", "-nographic",
        "-display", "none", "-monitor", "none", "-serial", "stdio",
        "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04",
    ]
    start = time.monotonic()
    timed_out = False
    serial = output / "serial.log"
    with serial.open("xb") as writer:
        try:
            completed = subprocess.run(args_qemu, stdin=subprocess.DEVNULL,
                                       stdout=writer, stderr=subprocess.STDOUT,
                                       timeout=args.timeout, check=False)
            code = completed.returncode
        except subprocess.TimeoutExpired:
            timed_out, code = True, None
    elapsed = round(time.monotonic() - start, 3)
    serial_size = serial.stat().st_size
    require(serial_size <= MAX_SERIAL_BYTES, "serial log size exceeds bounded evidence policy")
    captured = serial.read_text(encoding="utf-8", errors="replace")
    guest_ok = EXPECTED_SUCCESS in captured
    boot_ok = "TRILLIONNIUM_A01_BOOT_OK" in captured
    no_fail = "HEPTA_QUERYABI_FAIL" not in captured and "Kernel panic" not in captured
    passed = not timed_out and code == 33 and guest_ok and boot_ok and no_fail
    result = {
        "schema": "a05.queryabi-pinned-guest-replay.v1", "scope": "read_only_queryabi",
        "kernel_elf_sha256": digest(kernel), "original_a01_initramfs_sha256": digest(original),
        "bios_sha256": digest(bios), "probe_sha256": digest(compiled),
        "injected_initramfs_sha256": digest(initrd),
        "qemu_argv": args_qemu, "qemu_exit": code, "timed_out": timed_out,
        "elapsed_seconds": elapsed, "guest_queryabi_ok": guest_ok,
        "guest_boot_ok": boot_ok, "guest_failed": not no_fail,
        "no_host_network_or_disk": True,
        "native_capspace": False, "native_resource_effects": False,
        "hepta_durability": False, "production_ready": False, "passed": passed,
    }
    (output / "result.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n",
                                        encoding="utf-8")
    print(json.dumps({"passed": passed, "qemu_exit": code, "guest_queryabi_ok": guest_ok,
                      "guest_boot_ok": boot_ok, "output": str(output)}, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
