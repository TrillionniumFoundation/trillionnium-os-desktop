#!/usr/bin/env python3
"""Compare two independently created D1 build outputs byte-for-byte."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ARTIFACTS = (
    "package-lock.tsv",
    "rootfs.tar",
    "trillionnium-d1.ext4",
    "vmlinuz",
    "initrd.img",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_build(artifacts: Path) -> dict[str, object]:
    result_path = artifacts / "build-result.json"
    result = json.loads(result_path.read_text())
    if result.get("schema") != "trillionnium.desktop.d1-build-result.v1":
        raise ValueError(f"unexpected build result schema: {result_path}")
    if result.get("status") != "PASS_BUILD_ONLY":
        raise ValueError(f"build is not complete: {result_path}")
    for name in ARTIFACTS:
        if not (artifacts / name).is_file():
            raise FileNotFoundError(artifacts / name)
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", required=True, type=Path)
    parser.add_argument("--second", required=True, type=Path)
    parser.add_argument("--resolved-input", required=True, type=Path)
    parser.add_argument("--resolved-output", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()

    first = args.first.resolve()
    second = args.second.resolve()
    first_result = load_build(first)
    second_result = load_build(second)

    comparisons: dict[str, dict[str, object]] = {}
    all_equal = True
    for name in ARTIFACTS:
        first_path = first / name
        second_path = second / name
        first_hash = sha256(first_path)
        second_hash = sha256(second_path)
        equal = first_hash == second_hash and first_path.stat().st_size == second_path.stat().st_size
        comparisons[name] = {
            "first_sha256": first_hash,
            "second_sha256": second_hash,
            "first_bytes": first_path.stat().st_size,
            "second_bytes": second_path.stat().st_size,
            "equal": equal,
        }
        all_equal = all_equal and equal

    invariant_fields = (
        "image_id",
        "source_date_epoch",
        "selection_sha256",
        "resolved_manifest_sha256",
        "package_lock",
        "rootfs_tar",
        "image",
        "kernel",
        "initrd",
        "network_during_acceptance",
    )
    invariant_mismatches = [
        field
        for field in invariant_fields
        if first_result.get(field) != second_result.get(field)
    ]
    if invariant_mismatches:
        all_equal = False

    package_lines = [
        line
        for line in (first / "package-lock.tsv").read_text().splitlines()
        if line.strip()
    ]
    if not package_lines:
        raise RuntimeError("D1 package lock is empty")

    result = {
        "schema": "trillionnium.desktop.d1-reproducibility-result.v1",
        "status": "PASS_TWO_INDEPENDENT_BUILDS" if all_equal else "FAIL_BUILD_MISMATCH",
        "first": str(first),
        "second": str(second),
        "artifact_comparisons": comparisons,
        "invariant_mismatches": invariant_mismatches,
        "package_count": len(package_lines),
        "reproducible": all_equal,
    }
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    if not all_equal:
        raise RuntimeError(
            "D1 independent builds differ; inspect the reproducibility result before promotion"
        )

    resolved = json.loads(args.resolved_input.read_text())
    if resolved.get("status") != "PASS_SIGNED_INRELEASE":
        raise ValueError("resolved Debian manifest has not passed signature verification")
    resolved.update(
        {
            "status": "PASS_SIGNED_SNAPSHOT_AND_REPRODUCIBLE_BUILD",
            "package_lock": {
                "sha256": comparisons["package-lock.tsv"]["first_sha256"],
                "entries": len(package_lines),
            },
            "rootfs_tar": {
                "sha256": comparisons["rootfs.tar"]["first_sha256"],
                "bytes": comparisons["rootfs.tar"]["first_bytes"],
            },
            "image": {
                "sha256": comparisons["trillionnium-d1.ext4"]["first_sha256"],
                "bytes": comparisons["trillionnium-d1.ext4"]["first_bytes"],
                "format": first_result["image"]["format"],
                "label": first_result["image"]["label"],
                "uuid": first_result["image"]["uuid"],
            },
            "kernel": {
                "sha256": comparisons["vmlinuz"]["first_sha256"],
                "source_name": first_result["kernel"]["source_name"],
            },
            "initrd": {
                "sha256": comparisons["initrd.img"]["first_sha256"],
                "source_name": first_result["initrd"]["source_name"],
            },
            "two_build_reproducibility": {
                "status": "PASS",
                "result_sha256": sha256(args.result),
            },
        }
    )
    args.resolved_output.parent.mkdir(parents=True, exist_ok=True)
    args.resolved_output.write_text(json.dumps(resolved, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
