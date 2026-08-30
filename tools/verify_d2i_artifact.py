#!/usr/bin/env python3
"""Strict offline verifier for a D2I portable artifact directory."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def load(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"expected JSON object: {path}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("artifact", type=Path)
    args = parser.parse_args()
    root = args.artifact.resolve()
    receipt = load(root / "evidence/d2i-final-qualification.json")
    if receipt.get("status") != "PASS_D2I_EXACT_IMAGE_CANDIDATE":
        raise SystemExit("D2I receipt status is not PASS")
    outputs = receipt.get("output_digests")
    if not isinstance(outputs, dict) or not outputs:
        raise SystemExit("receipt output digest map is absent")
    for relative, expected in outputs.items():
        path = root / relative
        if not path.is_file() or path.is_symlink():
            raise SystemExit(f"declared artifact path is missing or unsafe: {relative}")
        if path.stat().st_size != expected.get("bytes"):
            raise SystemExit(f"size mismatch: {relative}")
        if digest(path) != expected.get("sha256"):
            raise SystemExit(f"digest mismatch: {relative}")
    source = load(root / "source/source-input-digests.json")
    if source.get("entry_count") != len(source.get("entries", [])):
        raise SystemExit("source manifest count mismatch")
    runtime = load(root / "d2i/qemu/runtime-ready.json")
    guest = load(root / "d2i/qemu/guest-acceptance.json")
    boot = load(root / "d2i/qemu/boot-result.json")
    if runtime.get("actual_content_process_crash_proven") is not True:
        raise SystemExit("runtime causal crash proof is absent")
    for key in (
        "signal_sent",
        "content_process_termination_observed",
        "zero_content_processes_after_termination",
        "replacement_process_distinct",
    ):
        if runtime.get(key) is not True:
            raise SystemExit(f"runtime proof field is not true: {key}")
    if runtime.get("crash_callback_required") is not False:
        raise SystemExit("runtime incorrectly requires crash callback")
    if guest.get("status") != "PASS_D1_D2_INTEGRATED_IMAGE_CANDIDATE":
        raise SystemExit("guest acceptance is not PASS")
    if boot.get("network") != "none" or boot.get("clean_poweroff") is not True:
        raise SystemExit("QEMU authority or shutdown proof is invalid")
    print(json.dumps({
        "status": "PASS",
        "verified_outputs": len(outputs),
        "source_inputs": source["entry_count"],
        "tested_sha": receipt["tested_sha"],
        "image_sha256": receipt["integrated_image_sha256"],
        "promotion_authoritative": receipt["promotion_authoritative"],
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
