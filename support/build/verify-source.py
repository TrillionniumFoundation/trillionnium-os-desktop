#!/usr/bin/env python3
"""Verify the vendored Asterinas inputs against the original Git tree.

Use --pristine for the initial import. Later kernel development may change
Rust sources, while the default check continues to protect build input pins.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "kernel/asterinas"
PINNED_COMMIT = "c4b7ed575b7b32773475b194d2ad41fb6d03765b"
PINNED_TREE = "96605cf64aeae2d34f29b97e85eff9315fe10a8e"
PINNED_TOOLCHAIN = "nightly-2026-07-21"
BUILD_INPUTS = {"Cargo.lock", "osdk/Cargo.lock", "rust-toolchain.toml", "Makefile", "OSDK.toml", "LICENSE-MPL"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pristine", action="store_true")
    args = parser.parse_args()
    lock = json.loads((ROOT / "support/upstream-lock.json").read_text())["kernel"]
    assert (lock["commit"], lock["tree"], lock["toolchain"]) == (
        PINNED_COMMIT, PINNED_TREE, PINNED_TOOLCHAIN
    ), "fixed upstream inputs changed; coordinate with A00"
    assert (ROOT / "README.md").stat().st_size == 0, "root README must be empty"
    entries = subprocess.check_output(
        ["git", "ls-tree", "-rz", PINNED_TREE], cwd=ROOT
    ).split(b"\0")
    checked, errors, inputs = 0, [], {}
    for entry in filter(None, entries):
        metadata, raw_name = entry.split(b"\t", 1)
        mode, kind, expected = metadata.decode().split()
        name = os.fsdecode(raw_name)
        if not args.pristine and name not in BUILD_INPUTS and not name.endswith("Cargo.toml"):
            continue
        path = SOURCE / name
        try:
            info = path.lstat()
            if mode == "120000":
                assert stat.S_ISLNK(info.st_mode), "expected symlink"
                content = os.fsencode(os.readlink(path))
            else:
                assert kind == "blob" and stat.S_ISREG(info.st_mode), "expected regular file"
                actual_mode = "100755" if info.st_mode & 0o111 else "100644"
                assert actual_mode == mode, f"mode {actual_mode} != {mode}"
                content = path.read_bytes()
            actual = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
            assert actual == expected, f"blob {actual} != {expected}"
            checked += 1
            if name in BUILD_INPUTS:
                inputs[name] = hashlib.sha256(content).hexdigest()
        except (OSError, AssertionError) as error:
            errors.append(f"{name}: {error}")
    report = {"commit": PINNED_COMMIT, "tree": PINNED_TREE,
              "toolchain": PINNED_TOOLCHAIN, "pristine": args.pristine,
              "checked_files": checked, "input_sha256": inputs, "errors": errors,
              "passed": not errors}
    print(json.dumps(report, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
