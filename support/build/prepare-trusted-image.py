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


MAX_FILE_BYTES = 8 * 1024 * 1024


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--profile", choices=("g1c-trusted-observe", "g1d-trusted-control"),
                        default="g1c-trusted-observe")
    args = parser.parse_args()
    source = args.input.resolve(strict=True)
    if not source.is_file():
        raise SystemExit("trusted initial input must be a regular ELF file")
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
    if args.profile == "g1d-trusted-control":
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
    with args.manifest.open("x") as stream:
        stream.write(json.dumps(manifest, sort_keys=True, indent=2) + "\n")


if __name__ == "__main__":
    main()
