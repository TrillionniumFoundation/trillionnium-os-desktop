#!/usr/bin/env python3
"""Verify the vendored Asterinas inputs against the original Git tree.

Use --pristine for the initial import. Later kernel development may change
Rust sources, while the default check continues to protect build input pins.
Default checks accept only the enumerated downstream owner-metadata and G1c/G1d
feature insertions plus the exact host OSDK FD-preservation inputs. The original
upstream lock remains independently pinned. --pristine accepts no derivations.
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
G1D_FEATURE_ADDITIONS = {
    "kernel/Cargo.toml": (
        b'g1c-trusted-observe = ["aster-core/g1c-trusted-observe"]\n',
        b'g1c-trusted-observe = ["aster-core/g1c-trusted-observe"]\n'
        b'g1d-trusted-control = ["aster-core/g1d-trusted-control"]\n',
    ),
    "kernel/core/Cargo.toml": (
        b'g1c-trusted-observe = []\n',
        b'g1c-trusted-observe = []\n'
        b'# G1-d reuses the exact-byte initial-image and VMAR sealing prerequisites.\n'
        b'g1d-trusted-control = ["g1c-trusted-observe"]\n',
    ),
}
ROOT_LOCK_ADDITIONS = (
    (b' "miniz_oxide",\n "osdk-frame-allocator",\n',
     b' "miniz_oxide",\n "os-control",\n "osdk-frame-allocator",\n'),
    (b'[[package]]\nname = "osdk-frame-allocator"\n',
     b'[[package]]\nname = "os-control"\nversion = "0.1.0"\ndependencies = [\n "spin",\n]\n\n'
     b'[[package]]\nname = "osdk-frame-allocator"\n'),
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
        if name in G1D_FEATURE_ADDITIONS:
            additions += (G1D_FEATURE_ADDITIONS[name],)
    derived = original
    for needle, replacement in additions:
        if derived.count(needle) != 1:
            raise ValueError("fixed downstream insertion point is not unique")
        derived = derived.replace(needle, replacement)
    return derived


# Separate, exact host-only OSDK postimages for its safe child-FD abstraction.
# They cannot authorize changes to the independently derived kernel lock,
# toolchain, licenses or any other manifest. --pristine accepts neither group.
APPROVED_HOST_OSDK_INPUTS = {
    "osdk/Cargo.toml": "39b9fa3d5cc822eb718bd3b14d872f50b48b285998f77ca5ebde38561a69c9ce",
    "osdk/Cargo.lock": "1011e26a7070708d37f2062a84b309d2c228c177a9e5434bfe63917203c17a18",
}


def inspect_local_dependency_inputs():
    """Check the actual local crate file set and record every declared input.

    Cargo discovers a package-root build.rs even when it is not named in the
    manifest. Rust sources may also include data with arbitrary extensions.
    Enumerating only tracked Rust/manifests therefore cannot establish absence
    of additional build inputs. Check the filesystem independently of ignore
    rules; the crate-root target directory is the sole build-output exclusion.
    Intended new inputs must be committed before this fixed-source build route.
    Existing Rust/data changes remain recorded without freezing development.
    """
    records, errors = {}, []
    prefix = "libs/os-control/"
    try:
        entries = subprocess.check_output(
            ["git", "ls-tree", "-rz", "HEAD", "--", "libs/os-control"], cwd=ROOT
        ).split(b"\0")
    except (OSError, subprocess.CalledProcessError) as error:
        return records, [f"libs/os-control: cannot inspect tracked inputs: {error}"]
    selected = {}
    for entry in filter(None, entries):
        metadata, raw_name = entry.split(b"\t", 1)
        name = os.fsdecode(raw_name)
        if name.startswith(prefix):
            selected[name] = metadata.decode().split()
    for required in (prefix + "Cargo.toml", prefix + "src/lib.rs"):
        if required not in selected:
            errors.append(f"{required}: required local dependency input is not tracked in HEAD")

    # Do not follow a replaced crate/ancestor directory or any directory symlink.
    # Missing/unreadable directories must fail closed rather than silently
    # reducing the set of inputs. The known output exclusion is not allowed to
    # hide HEAD-tracked inputs under target/.
    crate = ROOT / "libs/os-control"
    try:
        for directory in (ROOT / "libs", crate):
            if not stat.S_ISDIR(directory.lstat().st_mode):
                raise ValueError(f"{directory.relative_to(ROOT)} must be a real directory")
    except (OSError, ValueError) as error:
        return records, errors + [f"libs/os-control: {error}"]
    directories, pending = set(), [crate]
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as iterator:
                children = sorted(iterator, key=lambda item: item.name)
            directories.add(directory)
            for child in children:
                path = directory / child.name
                name = path.relative_to(ROOT).as_posix()
                info = child.stat(follow_symlinks=False)
                if stat.S_ISDIR(info.st_mode):
                    if (name == prefix + "target" and
                            not any(item.startswith(name + "/") for item in selected)):
                        continue
                    pending.append(path)
                elif name not in selected:
                    errors.append(f"{name}: undeclared local dependency input (not tracked in HEAD)")
        except OSError as error:
            errors.append(f"{directory.relative_to(ROOT)}: cannot inspect actual crate files: {error}")

    for name, (mode, kind, expected) in selected.items():
        try:
            path = ROOT / name
            if path.parent not in directories:
                raise ValueError("input parent is not a verified real directory")
            info = path.lstat()
            if kind != "blob" or not stat.S_ISREG(info.st_mode):
                raise ValueError("expected regular file")
            actual_mode = "100755" if info.st_mode & 0o111 else "100644"
            if actual_mode != mode:
                raise ValueError(f"mode {actual_mode} != {mode}")
            content = path.read_bytes()
            actual = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
            records[name] = {"head_git_blob": expected, "actual_git_blob": actual,
                             "sha256": hashlib.sha256(content).hexdigest(),
                             "git_mode": mode, "matches_head": actual == expected}
            if name.rsplit("/", 1)[-1] in {"Cargo.toml", "Cargo.lock"} and actual != expected:
                raise ValueError("local dependency build metadata differs from HEAD")
        except (OSError, ValueError) as error:
            errors.append(f"{name}: {error}")
    return records, errors


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
    checked, errors, inputs, downstream, host_derivations = 0, [], {}, {}, {}
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
            if not args.pristine and (name in DOWNSTREAM_MANIFEST_ADDITIONS or name in G1C_FEATURE_ADDITIONS or name in G1D_FEATURE_ADDITIONS or name == "Cargo.lock"):
                original = subprocess.check_output(["git", "cat-file", "blob", expected], cwd=ROOT)
                derived_content = derive_downstream_input(name, original)
                downstream[name] = {
                    "upstream_blob": expected,
                    "upstream_sha256": hashlib.sha256(original).hexdigest(),
                    "derived_sha256": hashlib.sha256(derived_content).hexdigest(),
                    "local_dependency": "os-control" if name in DOWNSTREAM_MANIFEST_ADDITIONS or name == "Cargo.lock" else None,
                    "optional_profile": "g1c-trusted-observe" if name in G1C_FEATURE_ADDITIONS else None,
                    "optional_profiles": [profile for additions, profile in (
                        (G1C_FEATURE_ADDITIONS, "g1c-trusted-observe"),
                        (G1D_FEATURE_ADDITIONS, "g1d-trusted-control"),
                    ) if name in additions],
                }
                expected = hashlib.sha1(f"blob {len(derived_content)}\0".encode() + derived_content).hexdigest()
            actual = hashlib.sha1(f"blob {len(content)}\0".encode() + content).hexdigest()
            if actual != expected:
                approved = APPROVED_HOST_OSDK_INPUTS.get(name)
                if args.pristine or approved is None or hashlib.sha256(content).hexdigest() != approved:
                    raise ValueError(f"blob {actual} != {expected}")
                host_derivations[name] = {"upstream_git_blob": expected,
                                 "derived_git_blob": actual, "sha256": approved,
                                 "scope": "exact host OSDK FD-preservation inputs; kernel inputs are verified separately"}
            checked += 1
            if name in BUILD_INPUTS:
                inputs[name] = hashlib.sha256(content).hexdigest()
        except (OSError, ValueError) as error:
            errors.append(f"{name}: {error}")
    local_inputs = {}
    if not args.pristine:
        local_inputs, local_errors = inspect_local_dependency_inputs()
        errors.extend(local_errors)
    report = {"commit": PINNED_COMMIT, "tree": PINNED_TREE,
              "toolchain": PINNED_TOOLCHAIN, "pristine": args.pristine,
              "checked_files": checked, "input_sha256": inputs,
              "downstream_manifests": {n: v for n, v in downstream.items() if n.endswith("Cargo.toml")},
              "downstream_locks": {n: v for n, v in downstream.items() if n == "Cargo.lock"},
              "errors": errors,
              "approved_host_osdk_derivations": host_derivations,
              "local_dependency_inputs": local_inputs,
              "local_dependency_input_scope": (
                  "All HEAD-tracked os-control crate files, with undeclared filesystem "
                  "inputs rejected independently of Git ignore rules. Only the real crate-root "
                  "target build-output directory is excluded when it has no tracked inputs. "
                  "The kernel resolves kernel/asterinas/Cargo.lock. Actual source hashes "
                  "describe this check only; they are not a compiler-time atomic snapshot."
              ),
              "passed": not errors}
    print(json.dumps(report, indent=2))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
