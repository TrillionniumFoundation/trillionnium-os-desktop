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
# Only the host OSDK manifest/lock differ for its safe child-FD abstraction.
# The complete kernel lock, toolchain, licenses and all other manifests retain
# their original Git identities. --pristine never accepts these derivations.
APPROVED_HOST_OSDK_INPUTS = {
    "osdk/Cargo.toml": "39b9fa3d5cc822eb718bd3b14d872f50b48b285998f77ca5ebde38561a69c9ce",
    "osdk/Cargo.lock": "1011e26a7070708d37f2062a84b309d2c228c177a9e5434bfe63917203c17a18",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pristine", action="store_true")
    args = parser.parse_args()
    lock = json.loads((ROOT / "support/upstream-lock.json").read_text())["kernel"]
    if (lock["commit"], lock["tree"], lock["toolchain"]) != (
        PINNED_COMMIT, PINNED_TREE, PINNED_TOOLCHAIN
    ):
        raise SystemExit("fixed upstream inputs changed; coordinate with A00")
    if (ROOT / "README.md").stat().st_size != 0:
        raise SystemExit("root README must be empty")
    entries = subprocess.check_output(
        ["git", "ls-tree", "-rz", PINNED_TREE], cwd=ROOT
    ).split(b"\0")
    checked, errors, inputs, derived = 0, [], {}, {}
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
                if not stat.S_ISLNK(info.st_mode):
                    raise ValueError("expected symlink")
                content = os.fsencode(os.readlink(path))
            else:
                if kind != "blob" or not stat.S_ISREG(info.st_mode):
                    raise ValueError("expected regular file")
                actual_mode = "100755" if info.st_mode & 0o111 else "100644"
                if actual_mode != mode:
                    raise ValueError(f"mode {actual_mode} != {mode}")
                content = path.read_bytes()
            actual = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
            if actual != expected:
                approved = APPROVED_HOST_OSDK_INPUTS.get(name)
                if args.pristine or approved is None or hashlib.sha256(content).hexdigest() != approved:
                    raise ValueError(f"blob {actual} != {expected}")
                derived[name] = {"upstream_git_blob": expected,
                                 "derived_git_blob": actual, "sha256": approved,
                                 "scope": "locked host OSDK FD-preservation dependency; kernel inputs unchanged"}
            checked += 1
            if name in BUILD_INPUTS:
                inputs[name] = hashlib.sha256(content).hexdigest()
        except (OSError, ValueError) as error:
            errors.append(f"{name}: {error}")
    report = {"commit": PINNED_COMMIT, "tree": PINNED_TREE,
              "toolchain": PINNED_TOOLCHAIN, "pristine": args.pristine,
              "checked_files": checked, "input_sha256": inputs, "errors": errors,
              "approved_host_osdk_derivations": derived,
              "passed": not errors}
    print(json.dumps(report, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
