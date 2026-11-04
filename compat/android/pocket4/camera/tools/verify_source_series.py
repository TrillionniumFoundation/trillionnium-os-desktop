#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Check upstream hashes and apply both patches in a temporary copy of the six files."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--aosp-root", required=True, type=Path)
    parser.add_argument("--git", default="git")
    parser.add_argument("--output-json", type=Path)
    args = parser.parse_args()
    lock = json.loads((ROOT / "source-lock.json").read_text())
    for patch in lock["patches"]:
        if sha(ROOT / patch["path"]) != patch["sha256"]:
            raise SystemExit("Patch hash mismatch: " + patch["path"])
    with tempfile.TemporaryDirectory(prefix="p4-camera-source-series-") as temp:
        work = Path(temp)
        for relative, expected in lock["files"].items():
            path = PurePosixPath(relative)
            if path.is_absolute() or ".." in path.parts:
                raise SystemExit("Unsafe manifest path")
            source = args.aosp_root / relative
            if sha(source) != expected["upstream_sha256"]:
                raise SystemExit("Upstream precondition mismatch: " + relative)
            destination = work / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, destination)
        for index, patch in enumerate(lock["patches"]):
            command = [args.git, "-C", str(work), "apply", "--whitespace=error-all"]
            subprocess.run([*command, "--check", str(ROOT / patch["path"])],
                           check=True, capture_output=True, text=True, timeout=30)
            subprocess.run([*command, str(ROOT / patch["path"])],
                           check=True, capture_output=True, text=True, timeout=30)
            state = "after_zero_device_sha256" if index == 0 else "final_sha256"
            for relative, expected in lock["files"].items():
                if sha(work / relative) != expected[state]:
                    raise SystemExit("Patched source mismatch: " + relative)
        snapshot = lock["reviewed_source"]
        source_path = snapshot["path"].removeprefix("source/")
        if (work / source_path).read_bytes() != (ROOT / snapshot["path"]).read_bytes():
            raise SystemExit("Final patch result differs from published manager snapshot")
    result = {
        "schema": "pocket4-camera-source-series-verification-v1",
        "success": True,
        "upstream_files_verified": len(lock["files"]),
        "patches_verified": len(lock["patches"]),
        "final_manager_sha256": lock["reviewed_source"]["sha256"],
        "original_source_tree_modified": False,
        "full_apk_reproduction_verified": False,
    }
    rendered = json.dumps(result, indent=2) + "\n"
    if args.output_json:
        args.output_json.write_text(rendered)
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
