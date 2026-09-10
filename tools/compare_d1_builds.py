#!/usr/bin/env python3
"""Compare two independently created D1 build outputs byte-for-byte."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


ARTIFACTS = (
    "package-lock.tsv",
    "rootfs-content-manifest.json",
    "rootfs.tar",
    "trillionnium-d1.ext4",
    "vmlinuz",
    "initrd.img",
)
MAX_REPORTED_ROOTFS_DIFFERENCES = 512


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_build(artifacts: Path) -> dict[str, object]:
    result_path = artifacts / "build-result.json"
    result = json.loads(result_path.read_text(encoding="utf-8"))
    if result.get("schema") != "trillionnium.desktop.d1-build-result.v2":
        raise ValueError(f"unexpected build result schema: {result_path}")
    if result.get("status") != "PASS_BUILD_ONLY":
        raise ValueError(f"build is not complete: {result_path}")
    for name in ARTIFACTS:
        if not (artifacts / name).is_file():
            raise FileNotFoundError(artifacts / name)
    return result


def rootfs_entries(path: Path) -> dict[str, dict[str, Any]]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if document.get("schema") != "trillionnium.desktop.d1-rootfs-manifest.v1":
        raise ValueError(f"unexpected rootfs manifest schema: {path}")
    entries = document.get("entries")
    if not isinstance(entries, list):
        raise ValueError(f"rootfs manifest entries are not a list: {path}")
    by_path: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValueError(f"rootfs manifest contains an invalid entry: {path}")
        name = entry["path"]
        if name in by_path:
            raise ValueError(f"rootfs manifest repeats path {name!r}: {path}")
        by_path[name] = entry
    if document.get("entry_count") != len(by_path):
        raise ValueError(f"rootfs manifest entry count is inconsistent: {path}")
    return by_path


def compare_rootfs_manifests(first: Path, second: Path) -> dict[str, Any]:
    first_entries = rootfs_entries(first)
    second_entries = rootfs_entries(second)
    first_paths = set(first_entries)
    second_paths = set(second_entries)
    missing_from_second = sorted(first_paths - second_paths)
    missing_from_first = sorted(second_paths - first_paths)
    changed: list[dict[str, Any]] = []
    for name in sorted(first_paths & second_paths):
        left = first_entries[name]
        right = second_entries[name]
        if left == right:
            continue
        fields = sorted(set(left) | set(right))
        changed_fields = [field for field in fields if left.get(field) != right.get(field)]
        changed.append(
            {
                "path": name,
                "changed_fields": changed_fields,
                "first": {field: left.get(field) for field in changed_fields},
                "second": {field: right.get(field) for field in changed_fields},
            }
        )
    total = len(missing_from_second) + len(missing_from_first) + len(changed)
    return {
        "equal": total == 0,
        "first_entry_count": len(first_entries),
        "second_entry_count": len(second_entries),
        "missing_from_second_count": len(missing_from_second),
        "missing_from_first_count": len(missing_from_first),
        "changed_count": len(changed),
        "difference_count": total,
        "report_truncated": total > MAX_REPORTED_ROOTFS_DIFFERENCES,
        "missing_from_second": missing_from_second[:MAX_REPORTED_ROOTFS_DIFFERENCES],
        "missing_from_first": missing_from_first[:MAX_REPORTED_ROOTFS_DIFFERENCES],
        "changed": changed[:MAX_REPORTED_ROOTFS_DIFFERENCES],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--first", required=True, type=Path)
    parser.add_argument("--second", required=True, type=Path)
    parser.add_argument("--prepared-inputs", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()

    first = args.first.resolve()
    second = args.second.resolve()
    prepared_path = args.prepared_inputs.resolve()
    prepared = json.loads(prepared_path.read_text(encoding="utf-8"))
    if prepared.get("status") not in {
        "PASS_GENERATED_SIGNED_D1_PACKAGE_LOCK",
        "PASS_COMMITTED_SIGNED_D1_PACKAGE_LOCK",
    }:
        raise ValueError("D1 prepared inputs have not passed the signed-lock gate")

    first_result = load_build(first)
    second_result = load_build(second)

    comparisons: dict[str, dict[str, object]] = {}
    all_equal = True
    for name in ARTIFACTS:
        first_path = first / name
        second_path = second / name
        first_hash = sha256(first_path)
        second_hash = sha256(second_path)
        equal = (
            first_hash == second_hash
            and first_path.stat().st_size == second_path.stat().st_size
        )
        comparisons[name] = {
            "first_sha256": first_hash,
            "second_sha256": second_hash,
            "first_bytes": first_path.stat().st_size,
            "second_bytes": second_path.stat().st_size,
            "equal": equal,
        }
        all_equal = all_equal and equal

    rootfs_diff = compare_rootfs_manifests(
        first / "rootfs-content-manifest.json",
        second / "rootfs-content-manifest.json",
    )
    if rootfs_diff["equal"] is not comparisons["rootfs-content-manifest.json"]["equal"]:
        raise RuntimeError("rootfs manifest semantic and byte equality disagree")

    invariant_fields = (
        "image_id",
        "source_date_epoch",
        "selection_sha256",
        "prepared_manifest_sha256",
        "signed_package_set_sha256",
        "package_lock",
        "rootfs_manifest",
        "rootfs_tar",
        "image",
        "kernel",
        "initrd",
        "release_marker_present",
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
        for line in (first / "package-lock.tsv").read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]
    if len(package_lines) != prepared.get("package_count"):
        raise RuntimeError("built D1 package lock count differs from prepared inputs")
    if first_result.get("signed_package_set_sha256") != prepared.get(
        "package_set_sha256"
    ):
        raise RuntimeError("build result is not bound to the signed D1 package set")

    result = {
        "schema": "trillionnium.desktop.d1-reproducibility-result.v3",
        "status": (
            "PASS_TWO_INDEPENDENT_BUILDS"
            if all_equal
            else "FAIL_BUILD_MISMATCH"
        ),
        "first": str(first),
        "second": str(second),
        "prepared_inputs_sha256": sha256(prepared_path),
        "signed_package_set_sha256": prepared["package_set_sha256"],
        "artifact_comparisons": comparisons,
        "rootfs_manifest_diff": rootfs_diff,
        "invariant_mismatches": invariant_mismatches,
        "package_count": len(package_lines),
        "reproducible": all_equal,
        "claims": {
            "two_build_rootfs_manifest_match": comparisons[
                "rootfs-content-manifest.json"
            ]["equal"],
            "two_build_rootfs_match": comparisons["rootfs.tar"]["equal"],
            "two_build_ext4_match": comparisons["trillionnium-d1.ext4"]["equal"],
            "two_build_kernel_match": comparisons["vmlinuz"]["equal"],
            "two_build_initrd_match": comparisons["initrd.img"]["equal"],
            "qemu_booted": False,
            "servo_started": False,
            "product_ready": False,
        },
    }
    args.result.parent.mkdir(parents=True, exist_ok=True)
    args.result.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not all_equal:
        raise RuntimeError(
            "D1 independent builds differ; inspect the reproducibility result"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
