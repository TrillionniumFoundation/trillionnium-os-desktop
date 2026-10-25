#!/usr/bin/env python3
"""Freeze the reviewed initial ELF as an explicit trusted-profile build input.

This records build input provenance only. The kernel independently compares its
actual opened init snapshot to the embedded bytes and verifies final mappings.
It grants no authority to a caller-supplied path or digest.
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct


MAX_FILE_BYTES = 8 * 1024 * 1024
# x86_64 OSTD MAX_USERSPACE_VADDR leaves the final user page unmapped.
G2_USER_LIMIT = (1 << 47) - 4096
G2_LIMITS = {
    "max_file_bytes": 224 * 1024 * 1024,
    "max_mapped_bytes": 224 * 1024 * 1024,
    "max_load_segments": 16,
    "max_program_headers": 64,
    "max_tls_memsz": 64 * 1024,
    "max_tls_align": 4096,
    "workload_address_space_bytes": 256 * 1024 * 1024,
}


def inspect_g2_elf(path):
    """Inspect the frozen file; read only the ELF header and bounded PHDR table.

    This is build provenance and early rejection, never kernel authority.
    The kernel independently validates its immutable manifest and real VMAR.
    """
    size = path.stat().st_size
    if not 64 <= size <= G2_LIMITS["max_file_bytes"]:
        raise ValueError("G2 file size exceeds profile")
    with path.open("rb") as source:
        header = source.read(64)
        if len(header) != 64 or header[:7] != b"\x7fELF\x02\x01\x01":
            raise ValueError("G2 needs ELF64 little endian")
        kind, machine, version, entry, phoff = struct.unpack_from("<HHIQQ", header, 16)
        ehsize, phentsize, phnum = struct.unpack_from("<HHH", header, 52)
        if (kind, machine, version, ehsize, phentsize) != (2, 62, 1, 64, 56):
            raise ValueError("G2 needs x86_64 static ET_EXEC")
        end = phoff + phnum * phentsize
        if (not 1 <= phnum <= G2_LIMITS["max_program_headers"]
                or phoff < 64 or phoff % 8 or end > size):
            raise ValueError("G2 PHDR table bounds")
        source.seek(phoff)
        table = source.read(phnum * phentsize)
        if len(table) != phnum * phentsize:
            raise ValueError("G2 PHDR table truncated")
    loads, tls, phdr = [], None, None
    mapped = writable = 0
    executable_entry = False
    for index in range(phnum):
        typ, flags, offset, address, _, filesz, memsz, align = struct.unpack_from("<IIQQQQQQ", table, index * 56)
        if typ in (2, 3):
            raise ValueError("G2 rejects dynamic loading")
        if typ == 0x6474e551 and flags & 1:
            raise ValueError("G2 rejects executable stack requests")
        if typ not in (1, 6, 7):
            continue
        if filesz > memsz or offset + filesz > size or address + memsz > G2_USER_LIMIT:
            raise ValueError("G2 segment bounds")
        if typ == 6:
            if phdr is not None:
                raise ValueError("G2 duplicate PT_PHDR")
            phdr = (offset, address, filesz)
            continue
        if typ == 7:
            if (tls is not None or memsz > G2_LIMITS["max_tls_memsz"]
                    or not 1 <= align <= G2_LIMITS["max_tls_align"] or align & (align - 1)
                    or offset % align != address % align):
                raise ValueError("G2 TLS bounds or alignment")
            tls = {"file_bytes": filesz, "memory_bytes": memsz, "alignment": align,
                   "file_offset": offset, "virtual_address": address}
            continue
        start_page, end_page = address & ~4095, (address + memsz + 4095) & ~4095
        if (not memsz or start_page < 65536 or end_page > G2_USER_LIMIT
                or offset % 4096 != address % 4096 or not flags & 4 or flags & 3 == 3
                or flags & ~7 or len(loads) == G2_LIMITS["max_load_segments"]
                or any(start_page < old[5] and old[4] < end_page for old in loads)):
            raise ValueError("G2 LOAD layout or permissions")
        mapped += end_page - start_page
        writable += end_page - start_page if flags & 2 else 0
        if mapped > G2_LIMITS["max_mapped_bytes"]:
            raise ValueError("G2 mapped byte limit")
        executable_entry |= bool(flags & 1 and address <= entry < address + memsz)
        loads.append((offset, address, filesz, memsz, start_page, end_page))
    # Reproduce the loader's FIRST LOAD containing e_phoff, not an arbitrary
    # later mapping whose file range overlaps it.
    selected = next((load for load in loads if load[0] <= phoff < load[0] + load[2]), None)
    if not executable_entry or selected is None or end > selected[0] + selected[2]:
        raise ValueError("G2 entry or complete readable PHDR mapping missing")
    if phdr:
        offset, address, length = phdr
        if (offset != phoff or length < phnum * 56
                or address != selected[1] + phoff - selected[0]):
            raise ValueError("G2 PT_PHDR would change the static TLS base")
    if tls and tls["file_bytes"]:
        offset, address, length = tls["file_offset"], tls["virtual_address"], tls["file_bytes"]
        if not any(offset >= off and offset + length <= off + filesz
                   and address >= addr and address + length <= addr + memsz
                   and address - addr == offset - off
                   for off, addr, filesz, memsz, _, _ in loads):
            raise ValueError("G2 TLS template lacks a matching readable LOAD")
    return {"file_bytes": size, "mapped_bytes": mapped,
            "largest_load_bytes": max(end - start for _, _, _, _, start, end in loads),
            "writable_load_bytes": writable, "load_segments": len(loads),
            "program_headers": phnum, "tls": tls, "entry": entry}


def freeze_g2(source, output):
    """Bound both read length and temporary host memory; never replace an input."""
    total = 0
    digest = hashlib.sha256()
    with source.open("rb") as original, output.open("xb") as frozen:
        while True:
            chunk = original.read(min(64 * 1024, G2_LIMITS["max_file_bytes"] + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > G2_LIMITS["max_file_bytes"]:
                raise ValueError("G2 file size exceeds profile")
            frozen.write(chunk)
            digest.update(chunk)
    # Inspect the actual frozen copy, not a source that could change during IO.
    details = inspect_g2_elf(output)
    output.chmod(0o444)
    return total, digest.hexdigest(), details


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--profile", choices=("g1c-trusted-observe", "g1d-trusted-control", "g2-native-agentd"),
                        default="g1c-trusted-observe")
    args = parser.parse_args()
    source = args.input.resolve(strict=True)
    if not source.is_file():
        raise SystemExit("trusted initial input must be a regular ELF file")
    elf_profile = None
    if args.profile == "g2-native-agentd":
        size, digest, elf_profile = freeze_g2(source, args.output)
    else:
        with source.open("rb") as stream:
            content = stream.read(MAX_FILE_BYTES + 1)
        if not content or len(content) > MAX_FILE_BYTES:
            raise SystemExit("trusted initial input exceeds the 8 MiB profile")
        # Fail an obvious wrong input before compiling; the kernel owns complete
        # ELF/profile validation and does not rely on this build-time check.
        if content[:7] != b"\x7fELF\x02\x01\x01" or content[16:20] != b"\x02\x00\x3e\x00":
            raise SystemExit("trusted initial input must be little-endian x86_64 ET_EXEC")
        with args.output.open("xb") as stream:
            stream.write(content)
        args.output.chmod(0o444)
        size, digest = len(content), hashlib.sha256(content).hexdigest()
    manifest = {
        "schema": "hepta-g1c-trusted-initial-v1",
        "profile": args.profile,
        "source": str(source),
        "embedded_input": str(args.output.resolve()),
        "bytes": size,
        "sha256": digest,
        "supported_ops": 6,
        "features": 0,
        "slot": 1,
        "generation": 1,
        "cap_ns": 50_000_000,
        "period_ns": 100_000_000,
        "lease_ns": 300_000_000_000,
    }
    if args.profile in ("g1d-trusted-control", "g2-native-agentd"):
        manifest.update({
            "schema": "hepta-g1d-trusted-initial-v1",
            "supported_ops": 62,
            "bootstrap_version": 2,
            "bootstrap_bytes": 192,
            "roles": ["manager", "workload", "recovery"],
            "recovery_grace_ns": 30_000_000_000,
            "workload_address_space_bytes": 256 * 1024 * 1024,
        })
        # Role-specific slots are defined by the sealed v2 bootstrap page.
        del manifest["slot"]
        del manifest["generation"]
    if args.profile == "g2-native-agentd":
        manifest.update({"schema": "hepta-g2-trusted-initial-v1", "elf_profile": elf_profile,
                         "profile_limits": G2_LIMITS,
                         "qualification": "loader-stage-not-native-qualified",
                         "guest_memory_mib": 3072, "max_kernel_bytes": 256 * 1024 * 1024})
    with args.manifest.open("x") as stream:
        stream.write(json.dumps(manifest, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()
