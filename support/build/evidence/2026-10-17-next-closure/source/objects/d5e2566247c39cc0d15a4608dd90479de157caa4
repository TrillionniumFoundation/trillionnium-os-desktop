#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Package a static BusyBox and the fixed upstream smoke test without Nix/cpio."""

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path
import stat
import struct
import tempfile


APPLETS = (
    "cat", "chmod", "echo", "grep", "ln", "mkdir", "mount", "poweroff",
    "script", "sh", "sleep", "test", "uname",
)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def check_static_x86_64_elf(data):
    """Reject a dynamically linked initramfs input before packaging it."""
    if len(data) < 64 or data[:7] != b"\x7fELF\x02\x01\x01":
        raise ValueError("BusyBox must be an ELF64 little-endian executable")
    if struct.unpack_from("<H", data, 18)[0] != 62:
        raise ValueError("BusyBox must target x86_64 (ELF machine 62)")
    if struct.unpack_from("<H", data, 16)[0] not in (2, 3):
        raise ValueError("BusyBox must be executable (ET_EXEC or static ET_DYN)")
    offset = struct.unpack_from("<Q", data, 32)[0]
    size, count = struct.unpack_from("<HH", data, 54)
    if size < 56 or count == 0 or offset + size * count > len(data):
        raise ValueError("BusyBox has an invalid ELF program-header table")
    for index in range(count):
        if struct.unpack_from("<I", data, offset + size * index)[0] == 3:
            raise ValueError("BusyBox has PT_INTERP; supply a static BusyBox")


def cpio_entry(name, mode, data, inode):
    name_bytes = name.encode("utf-8") + b"\0"
    fields = (
        inode, mode, 0, 0, 2 if stat.S_ISDIR(mode) else 1, 0, len(data),
        0, 0, 0, 0, len(name_bytes), 0,
    )
    if any(value < 0 or value > 0xFFFFFFFF for value in fields):
        raise ValueError("newc header field is out of range")
    header = b"070701" + b"".join(f"{value:08x}".encode() for value in fields)
    record = header + name_bytes
    record += b"\0" * (-len(record) % 4)
    record += data
    return record + b"\0" * (-len(data) % 4)


def atomic_write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as output:
            temporary_path = Path(output.name)
            output.write(data)
        os.chmod(temporary_path, 0o644)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--busybox", type=Path, default=Path("/usr/bin/busybox"))
    parser.add_argument("--upstream", type=Path, required=True,
                        help="the fixed complete Asterinas source directory")
    parser.add_argument("--output", type=Path, required=True,
                        help="destination .cpio.gz file")
    parser.add_argument("--manifest", type=Path, required=True)
    args = parser.parse_args()
    if args.output.resolve() == args.manifest.resolve():
        parser.error("--output and --manifest must differ")

    busybox = args.busybox.read_bytes()
    check_static_x86_64_elf(busybox)
    local_init = Path(__file__).with_name("init").read_bytes()
    boot_hello = (args.upstream / "test/initramfs/src/boot_hello.sh").read_bytes()

    entries = []
    for directory in ("bin", "dev", "etc", "proc", "root", "sbin", "sys", "test", "tmp"):
        mode = 0o1777 if directory == "tmp" else 0o755
        entries.append((directory, stat.S_IFDIR | mode, b"", None))
    entries.extend((
        ("bin/busybox", stat.S_IFREG | 0o755, busybox, None),
        ("init", stat.S_IFREG | 0o755, local_init, None),
        ("test/boot_hello.sh", stat.S_IFREG | 0o755, boot_hello, None),
    ))
    for applet in APPLETS:
        entries.append((f"bin/{applet}", stat.S_IFLNK | 0o777, b"busybox", "busybox"))

    archive = bytearray()
    manifest_entries = []
    for inode, (name, mode, data, link) in enumerate(entries, 1):
        archive.extend(cpio_entry(name, mode, data, inode))
        manifest_entries.append({
            "path": name,
            "type": "directory" if stat.S_ISDIR(mode) else "symlink" if link else "file",
            "mode": f"{mode:06o}",
            "uid": 0,
            "gid": 0,
            "mtime": 0,
            "size": len(data),
            "sha256": sha256(data),
            "link": link,
        })
    archive.extend(cpio_entry("TRAILER!!!", 0, b"", len(entries) + 1))
    archive.extend(b"\0" * (-len(archive) % 512))
    compressed = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=compressed, mtime=0) as output:
        output.write(archive)
    image = compressed.getvalue()
    manifest = {
        "schema": 1,
        "format": "newc+gzip",
        "architecture": "x86_64",
        "cpio_mtime": 0,
        "gzip_mtime": 0,
        "image_size": len(image),
        "image_sha256": sha256(image),
        "uncompressed_size": len(archive),
        "uncompressed_sha256": sha256(archive),
        "busybox_sha256": sha256(busybox),
        "upstream_smoke_test": "test/initramfs/src/boot_hello.sh",
        "upstream_smoke_test_sha256": sha256(boot_hello),
        "entries": manifest_entries,
    }
    atomic_write(args.output, image)
    atomic_write(args.manifest, (json.dumps(manifest, indent=2) + "\n").encode())
    print(f"initramfs: {len(image)} bytes, sha256={sha256(image)}")


if __name__ == "__main__":
    main()
