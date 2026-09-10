#!/usr/bin/env python3
"""Strictly verify a staged or downloaded D1 qualification artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


RECEIPT_PATH = Path("evidence/d1-final-qualification.json")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} is not boolean")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact_root", type=Path)
    args = parser.parse_args()
    root = args.artifact_root.resolve()
    if not root.is_dir() or root.is_symlink():
        raise SystemExit(f"artifact root is missing or unsafe: {root}")

    receipt_path = root / RECEIPT_PATH
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    if receipt.get("schema") != "trillionnium.desktop.d1-final-qualification.v3":
        raise ValueError("unexpected D1 qualification receipt schema")
    if receipt.get("status") != "PASS":
        raise ValueError("D1 qualification receipt is not a pass")

    role = receipt.get("evidence_role")
    authoritative = require_bool(
        receipt.get("promotion_authoritative"), "promotion_authoritative"
    )
    if role == "exact_main_push":
        if receipt.get("ref") != "refs/heads/main" or not authoritative:
            raise ValueError("exact-main receipt does not identify authoritative main")
    elif role in {"pr_synthetic_merge", "manual_non_authoritative"}:
        if authoritative:
            raise ValueError(f"non-main evidence role {role!r} is authoritative")
    else:
        raise ValueError(f"unknown D1 evidence role: {role!r}")

    output_digests = receipt.get("output_digests")
    if not isinstance(output_digests, dict) or not output_digests:
        raise ValueError("D1 receipt has no output digest map")
    seen: set[Path] = set()
    for relative, expected in sorted(output_digests.items()):
        if not isinstance(relative, str) or not isinstance(expected, str):
            raise ValueError("D1 output digest entry is malformed")
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts or path == RECEIPT_PATH:
            raise ValueError(f"unsafe or recursive output path: {relative!r}")
        candidate = (root / path).resolve()
        try:
            candidate.relative_to(root)
        except ValueError as error:
            raise ValueError(f"output path escapes artifact root: {relative!r}") from error
        if candidate in seen:
            raise ValueError(f"duplicate output path after resolution: {relative!r}")
        seen.add(candidate)
        if not candidate.is_file() or candidate.is_symlink():
            raise FileNotFoundError(f"declared artifact output is absent: {relative}")
        actual = sha256(candidate)
        if actual != expected:
            raise ValueError(
                f"artifact digest mismatch for {relative}: expected {expected}, got {actual}"
            )

    source_manifest_path = root / "evidence/source-input-digests.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    if source_manifest.get("schema") != "trillionnium.desktop.source-input-digests.v1":
        raise ValueError("source input digest manifest has the wrong schema")
    source_digests = source_manifest.get("files")
    if not isinstance(source_digests, dict) or not source_digests:
        raise ValueError("source input digest manifest is empty")
    if source_manifest.get("file_count") != len(source_digests):
        raise ValueError("source input digest count is inconsistent")
    canonical = json.dumps(
        source_digests, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    if hashlib.sha256(canonical).hexdigest() != source_manifest.get(
        "files_sha256"
    ):
        raise ValueError("source input aggregate digest is inconsistent")
    if receipt.get("source_input_manifest_sha256") != sha256(source_manifest_path):
        raise ValueError("receipt does not bind the staged source input manifest")

    print(
        json.dumps(
            {
                "schema": "trillionnium.desktop.d1-artifact-verification.v1",
                "status": "PASS",
                "receipt": RECEIPT_PATH.as_posix(),
                "evidence_role": role,
                "promotion_authoritative": authoritative,
                "verified_output_count": len(output_digests),
                "source_input_count": len(source_digests),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
