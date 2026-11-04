"""One source-owned original owner image profile; no caller-supplied budgets.

This profile admits only the already measured a39 original ELF. It does not
claim a runtime result, a whole-guest memory bound, or the legacy 8/16 MiB gate.
The kernel build script independently checks the complete digest before embed.
"""

import hashlib
import json
from pathlib import Path
import re
import struct

ROOT = Path(__file__).resolve().parents[2]
PROFILE = "g2-original-owner-a39-v1"
DESCRIPTOR_PATH = ROOT / "tests/workloads/hepta_cpu_control/original-owner-image-profile.json"
DESCRIPTOR_SHA256 = "138043c29a3d3428fb8b494d6aa40d14b0010f6793a58d1f9ca46892bca5b758"
RUST_PROFILE_PATH = ROOT / "kernel/asterinas/kernel/core/src/process/program_loader/elf/original_owner_profile.rs"
BUILD_SCHEMA = "hepta.original-owner-image-entry-build.v1"
INITIAL_MANIFEST_SCHEMA = "hepta.g2-original-owner-initial.v1"
RUNTIME_SCHEMA = "hepta.original-owner-image-runtime.v1"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def descriptor():
    # There is no external descriptor path option. This named version binds
    # the exact tracked JSON bytes and cross-checks independently compiled Rust
    # constants; an arbitrary source-review object cannot change the budget.
    content = DESCRIPTOR_PATH.read_bytes()
    require(len(content) <= 16 * 1024 and hashlib.sha256(content).hexdigest() == DESCRIPTOR_SHA256,
            "source-owned original-owner descriptor differs from its reviewed version")
    value = json.loads(content)
    require(value["schema"] == "hepta.original-owner-image-profile.v1" and value["profile"] == PROFILE,
            "original-owner descriptor profile/version differs")
    declarations = re.findall(r'\bpub const ([A-Z0-9_]+): (&str|usize)\s*=\s*("[^"\r\n]*"|[0-9_]+);',
                              RUST_PROFILE_PATH.read_text())
    constants = {name: json.loads(raw) if kind == "&str" else int(raw.replace("_", ""))
                 for name, kind, raw in declarations}
    image = value["image"]
    expected = {"PROFILE": PROFILE, "OWNER_SHA256": image["sha256"], "FILE_BYTES": image["file_bytes"],
                "MAPPED_BYTES": image["mapped_load_bytes"], "MAX_SEGMENT_BYTES": image["largest_load_range_bytes"],
                "LOAD_SEGMENTS": image["load_segments"], "INITIAL_ROLES": len(value["roles"])}
    require(len(declarations) == len(expected) and constants == expected,
            "kernel constants and source-owned original-owner descriptor differ")
    return value


def bind_source_review(review):
    value = descriptor()
    for key in ("hepta", "entry", "userspace_toolchain"):
        require(review.get(key) == value[key], "exact image profile source review differs: " + key)
    return value


def bind_build(sources, entry, lock_sha256, toolchain_manifest_sha256, toolchain):
    value = descriptor()
    require(sources.get("hepta") == value["hepta"], "image profile requires the exact original Hepta source/tree")
    selected = {key: entry.get(key) for key in ("package", "name", "kind", "path")}
    selected["sha256"] = entry.get("entry_sha256")
    require(selected == value["entry"], "image profile requires the original reviewed native owner entry")
    require(lock_sha256 == value["cargo_lock_sha256"]
            and toolchain_manifest_sha256 == value["userspace_toolchain"]["sha256"]
            and toolchain == value["userspace_toolchain"]["channel"],
            "image profile original lock or compiler identity differs")
    return value


def inspect_elf(data):
    value = descriptor()
    image = value["image"]
    require(type(data) is bytes and len(data) == image["file_bytes"], "original-owner exact file length differs")
    sha256 = hashlib.sha256(data).hexdigest()
    require(sha256 == image["sha256"], "original-owner complete image SHA-256 differs")
    # This independent host check retains the trusted loader's structural
    # restrictions. Its F/L/S values come only from the fixed descriptor above.
    require(data[:7] == b"\x7fELF\x02\x01\x01" and data[16:20] == b"\x02\x00\x3e\x00",
            "original owner must be little-endian x86_64 ET_EXEC")
    entry, phoff = struct.unpack_from("<QQ", data, 24)
    phsize, phcount = struct.unpack_from("<HH", data, 54)
    require(phsize == 56 and 1 <= phcount <= 64 and phoff + phsize * phcount <= len(data),
            "invalid original-owner program-header table")
    loads = []
    for index in range(phcount):
        kind, flags, offset, address, _, filesz, memsz, align = struct.unpack_from("<IIQQQQQQ", data, phoff + index * phsize)
        require(kind != 3, "original owner must not contain PT_INTERP")
        if kind == 0x6474E551:
            require(flags & 1 == 0, "original owner requests an executable stack")
        if kind != 1:
            continue
        require(filesz <= memsz and offset + filesz <= len(data) and memsz > 0,
                "invalid original-owner LOAD file/memory bounds")
        require(address >= 65536 and address + memsz <= (1 << 47) and flags & 4 and flags & 3 != 3,
                "invalid original-owner LOAD permissions/address")
        require(offset % 4096 == address % 4096 and align >= 4096 and align & (align - 1) == 0,
                "invalid original-owner LOAD alignment")
        start, end = address // 4096 * 4096, (address + memsz + 4095) // 4096 * 4096
        require(not any(start < old["end"] and old["start"] < end for old in loads),
                "original-owner LOAD pages overlap")
        loads.append({"start": start, "end": end, "file_end": offset + filesz,
                      "entry_inside": bool(flags & 1 and address <= entry < address + memsz)})
    require(len(loads) == image["load_segments"] and any(item["entry_inside"] for item in loads),
            "original-owner load count or executable entry differs")
    sizes = [item["end"] - item["start"] for item in loads]
    require(sum(sizes) == image["mapped_load_bytes"] and max(sizes) == image["largest_load_range_bytes"],
            "original-owner exact mapped LOAD total or largest segment differs")
    require(max(item["file_end"] for item in loads) < len(data), "original owner has no retained non-LOAD tail")
    return {"entry": entry, "bytes": len(data), "loads": loads, "sha256": sha256}


def manifest_fields():
    return {"schema": INITIAL_MANIFEST_SCHEMA,
            "image_profile_descriptor_sha256": DESCRIPTOR_SHA256,
            "image_profile_descriptor": descriptor(), "legacy_limits_unchanged": True,
            "legacy_static_profile_passed": False, "whole_guest_peak_verified": False,
            "global_memory_reserve": False, "production_ready": False}


def kernel_selection_record():
    image = descriptor()["image"]
    return ("[hepta-g2] original owner image profile selected: profile=" + PROFILE
            + " sha256=" + image["sha256"] + " file_bytes=" + str(image["file_bytes"])
            + " mapped_bytes=" + str(image["mapped_load_bytes"])
            + " max_segment_bytes=" + str(image["largest_load_range_bytes"])
            + " global_memory_reserve=false")
