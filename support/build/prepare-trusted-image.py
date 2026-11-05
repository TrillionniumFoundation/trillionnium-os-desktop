#!/usr/bin/env python3
"""Freeze the reviewed initial ELF as an explicit trusted-profile build input.

This records build input provenance only. The kernel independently compares its
actual opened init snapshot to the embedded bytes and verifies final mappings.
It grants no authority to a caller-supplied path or digest.
"""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True


MAX_FILE_BYTES = 8 * 1024 * 1024
ORIGINAL_OWNER_PROFILE = "g2-original-owner-a39-v1"
ORIGINAL_OWNER_PROFILES = (ORIGINAL_OWNER_PROFILE, "g2-original-owner-publish-v1")


def original_owner_profile(profile):
    path = Path(__file__).with_name("original_owner_image.py")
    spec = importlib.util.spec_from_file_location("trusted_original_owner_image", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.select_profile(profile)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--profile", choices=("g1c-trusted-observe", "g1d-trusted-control", "g2-trusted-daemon", *ORIGINAL_OWNER_PROFILES),
                        default="g1c-trusted-observe")
    args = parser.parse_args()
    exact = original_owner_profile(args.profile) if args.profile in ORIGINAL_OWNER_PROFILES else None
    file_limit = exact.descriptor()["image"]["file_bytes"] if exact else MAX_FILE_BYTES
    source = args.input.resolve(strict=True)
    if not source.is_file():
        raise SystemExit("trusted initial input must be a regular ELF file")
    with source.open("rb") as stream:
        content = stream.read(file_limit + 1)
    if not content or len(content) > file_limit:
        raise SystemExit("trusted initial input exceeds the exact original-owner profile" if exact
                         else "trusted initial input exceeds the 8 MiB profile")
    if exact:
        exact.inspect_elf(content)
    # Fail an obvious wrong input before compiling; the kernel owns complete
    # ELF/profile validation and does not rely on this build-time check.
    if content[:7] != b"\x7fELF\x02\x01\x01" or content[16:20] != b"\x02\x00\x3e\x00":
        raise SystemExit("trusted initial input must be little-endian x86_64 ET_EXEC")
    with args.output.open("xb") as stream:
        stream.write(content)
    args.output.chmod(0o444)
    manifest = {
        "schema": "hepta-g1c-trusted-initial-v1",
        "profile": args.profile,
        "source": str(source),
        "embedded_input": str(args.output.resolve()),
        "bytes": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
        "supported_ops": 6,
        "features": 0,
        "slot": 1,
        "generation": 1,
        "cap_ns": 50_000_000,
        "period_ns": 100_000_000,
        "lease_ns": 300_000_000_000,
    }
    if args.profile in ("g1d-trusted-control", "g2-trusted-daemon", *ORIGINAL_OWNER_PROFILES):
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
    if args.profile in ("g2-trusted-daemon", *ORIGINAL_OWNER_PROFILES):
        manifest.update({
            "schema": "hepta-g2-trusted-initial-v1",
            "bootstrap_version": 3,
            "bootstrap_bytes": 200,
            "roles": ["root", "manager", "workload", "recovery"],
            "root_role": 4,
            "root_pid_offset": 192,
            "workload_uid": 60002,
            "workload_gid": 60002,
            "manager_history_ack": True,
            "original_writer_durability_verified": False,
            "g2_complete": False,
        })
    if exact:
        manifest.update(exact.manifest_fields())
    with args.manifest.open("x") as stream:
        stream.write(json.dumps(manifest, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()
