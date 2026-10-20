#!/usr/bin/env python3
"""Verify the vendored Asterinas inputs against the original Git tree.

Use --pristine for the initial import. Later kernel development may change
Rust sources, while the default check continues to protect build input pins.
Build-input derivatives are exact insertions for local owner metadata and the
default-off G1-c and permission SMP features; --pristine still requires upstream.
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
ROOT_LOCK_SEED_SHA256 = "6b5de5d78a8e794567e1b07f1e7c621079023ff7f03c6c618abb7d5c09d8e316"
BUILD_INPUTS = {"Cargo.lock", "osdk/Cargo.lock", "rust-toolchain.toml", "Makefile", "OSDK.toml", "LICENSE-MPL"}
DOWNSTREAM_MANIFEST_ADDITIONS = {
    "Cargo.toml": (
        b"# Crates under osdk/deps\n",
        b"# Downstream owner metadata only; portable-spin is not a kernel lock backend.\n"
        b'os-control = { path = "../../libs/os-control", default-features = false, features = ["portable-spin"] }\n\n'
        b"# Crates under osdk/deps\n",
    ),
    "kernel/core/Cargo.toml": (
        b"miniz_oxide.workspace = true\n",
        b"miniz_oxide.workspace = true\nos-control.workspace = true\n",
    ),
}
# Exact opt-in feature declarations. This adds no package, version, source or
# lock dependency; every other manifest byte remains pinned to the import.
G1C_FEATURE_ADDITIONS = {
    "kernel/Cargo.toml": (
        b'riscv_sv39_mode = ["aster-core/riscv_sv39_mode"]\n',
        b'riscv_sv39_mode = ["aster-core/riscv_sv39_mode"]\n'
        b'g1c-trusted-observe = ["aster-core/g1c-trusted-observe"]\n',
    ),
    "kernel/core/Cargo.toml": (
        b'riscv_sv39_mode = ["ostd/riscv_sv39_mode"]\n',
        b'riscv_sv39_mode = ["ostd/riscv_sv39_mode"]\n'
        b'# Experimental initial-image observation. Requires HEPTA_TRUSTED_INITIAL_ELF\n'
        b'# at build time; ordinary builds retain the QueryAbi-only device.\n'
        b'g1c-trusted-observe = []\n',
    ),
}
ROOT_LOCK_ADDITIONS = (
    (b' "miniz_oxide",\n "osdk-frame-allocator",\n',
     b' "miniz_oxide",\n "os-control",\n "osdk-frame-allocator",\n'),
    (b'[[package]]\nname = "osdk-frame-allocator"\n',
     b'[[package]]\nname = "os-control"\nversion = "0.1.0"\ndependencies = [\n "spin",\n]\n\n'
     b'[[package]]\nname = "osdk-frame-allocator"\n'),
)
PERMISSION_SMP_FEATURE_ADDITION = (
    b"[features]\n",
    b"[features]\n"
    b"# Dedicated two-CPU permission ktests; no effect outside cfg(ktest).\n"
    b"permission-attr-smp-ktest = []\n",
)
PERMISSION_TEST_RUNNER_FEATURE_ADDITION = (
    b"[lints]\n",
    b"[features]\n"
    b"# The generated test base supplies an entry that calls the same test runner.\n"
    b"external-entry = []\n\n"
    b"[lints]\n",
)


def derive_downstream_input(name, original):
    """Derive only exact local insertions from the original pinned Git blob."""
    if name == "Cargo.lock":
        if hashlib.sha256(original).hexdigest() != ROOT_LOCK_SEED_SHA256:
            raise ValueError("original upstream root lock seed changed")
        additions = ROOT_LOCK_ADDITIONS
    else:
        additions = ()
        if name in DOWNSTREAM_MANIFEST_ADDITIONS:
            additions += (DOWNSTREAM_MANIFEST_ADDITIONS[name],)
        if name in G1C_FEATURE_ADDITIONS:
            additions += (G1C_FEATURE_ADDITIONS[name],)
        if name == "kernel/core/Cargo.toml":
            additions += (PERMISSION_SMP_FEATURE_ADDITION,)
        if name == "osdk/deps/test-kernel/Cargo.toml":
            additions += (PERMISSION_TEST_RUNNER_FEATURE_ADDITION,)
    derived = original
    for needle, replacement in additions:
        if derived.count(needle) != 1:
            raise ValueError("fixed downstream insertion point is not unique")
        derived = derived.replace(needle, replacement)
    return derived


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
    checked, errors, inputs, downstream = 0, [], {}, {}
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
            if not args.pristine and (
                name in DOWNSTREAM_MANIFEST_ADDITIONS
                or name in G1C_FEATURE_ADDITIONS
                or name in {"Cargo.lock", "osdk/deps/test-kernel/Cargo.toml"}
            ):
                original = subprocess.check_output(["git", "cat-file", "blob", expected], cwd=ROOT)
                derived = derive_downstream_input(name, original)
                downstream[name] = {
                    "upstream_blob": expected,
                    "upstream_sha256": hashlib.sha256(original).hexdigest(),
                    "derived_sha256": hashlib.sha256(derived).hexdigest(),
                    "local_dependency": "os-control" if name in DOWNSTREAM_MANIFEST_ADDITIONS or name == "Cargo.lock" else None,
                    "optional_profile": "g1c-trusted-observe" if name in G1C_FEATURE_ADDITIONS else None,
                }
                expected = hashlib.sha1(f"blob {len(derived)}\0".encode() + derived).hexdigest()
            actual = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
            if actual != expected:
                raise ValueError(f"blob {actual} != {expected}")
            checked += 1
            if name in BUILD_INPUTS:
                inputs[name] = hashlib.sha256(content).hexdigest()
        except (OSError, ValueError) as error:
            errors.append(f"{name}: {error}")
    report = {"commit": PINNED_COMMIT, "tree": PINNED_TREE,
              "toolchain": PINNED_TOOLCHAIN, "pristine": args.pristine,
              "checked_files": checked, "input_sha256": inputs,
              "downstream_manifests": {n: v for n, v in downstream.items() if n.endswith("Cargo.toml")},
              "downstream_locks": {n: v for n, v in downstream.items() if n == "Cargo.lock"},
              "errors": errors,
              "passed": not errors}
    print(json.dumps(report, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
