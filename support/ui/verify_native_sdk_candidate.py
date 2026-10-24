#!/usr/bin/env python3
"""Verify and build one committed clipboard-SDK candidate without changing its lock.

Prepare and commit the candidate Cargo.lock in a separate worktree first. This
entry point runs the same locked feature/config/profile for metadata, tests,
strict Clippy and the binary build, retaining exact inputs and failed logs.
It never edits Cargo.lock, installs the product or qualifies a physical UI.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tomllib

sys.dont_write_bytecode = True
from product import native_sdk

FEATURE = "trill-shell/hepta-native-clipboard-sdk"
HEPTA_SOURCE = "git+https://github.com/TrillionniumFoundation/hepta-private-ci"
BINARIES = ("trill-session", "trill-shell", "trill-app-window", "trill-ctl", "trill-notes-recovery")


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], timeout=30).decode().strip()


def clean_source(root):
    require(Path(git(root, "rev-parse", "--show-toplevel")).resolve() == root, "source must be its independent checkout root")
    require(not git(root, "status", "--porcelain=v1", "--untracked-files=all"), f"source checkout is not clean: {root}")
    return {"commit": git(root, "rev-parse", "HEAD"), "tree": git(root, "rev-parse", "HEAD^{tree}")}


def stable_files(paths):
    return {str(path): sha(path) for path in paths}


def ensure_stable(paths, expected):
    require(stable_files(paths) == expected, "candidate inputs changed during verification; no qualification is valid")


def cargo_commands(args, toolchain):
    prefix = [args.cargo, "+" + toolchain]
    # cargo-clippy is an external Cargo plugin: global options before its
    # name are not forwarded to its nested `cargo check` (Cargo #11031).
    # Keep --config after every subcommand, before Clippy's `--` separator.
    common = ["--config", str(args.sdk_cargo_config), "--manifest-path", str(args.source / "ui/Cargo.toml"),
              "--locked", "--features", FEATURE]
    if args.offline:
        common.append("--offline")
    compiled = [*common, "--workspace", "--profile", args.profile, "--target-dir", str(args.target_dir)]
    return [
        ("metadata", [*prefix, "metadata", *common, "--format-version", "1"]),
        ("test", [*prefix, "test", *compiled, "--all-targets"]),
        ("clippy", [*prefix, "clippy", *compiled, "--all-targets", "--", "-D", "warnings"]),
        ("build", [*prefix, "build", *compiled, "--bins"]),
    ]


def verify_graph(args, metadata, hepta_commit):
    data = json.loads(metadata)
    hepta = [p for p in data["packages"] if (p.get("source") or "").startswith(HEPTA_SOURCE)]
    require(hepta and all(p["source"].split("#")[-1] == hepta_commit for p in hepta), "resolved Hepta packages do not match the selected source commit")
    require(any(p["name"] == "hepta-robrix-ui" for p in hepta), "original native UI is missing from the resolved graph")
    verifier = args.hepta_root / "apps/hepta-control-ui/test/verify-native-clipboard-sdk.py"
    spec = importlib.util.spec_from_file_location("same_original_sdk_verifier", verifier)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    profile = module.verify(args.hepta_root, args.prepared_sdk, args.original_metadata.read_bytes(),
                            metadata, args.sdk_cargo_config.read_bytes())
    native_sdk.validate_profile(profile)
    return profile


def run(args, receipt):
    for root in (args.source, args.hepta_root, args.prepared_sdk):
        require(root.is_dir(), f"missing source directory: {root}")
    for path in (args.target_dir, args.output, args.sdk_cargo_config, args.original_metadata, args.prepared_sdk):
        require(not path.is_relative_to(args.source), "candidate build/evidence/config/SDK must stay outside the Desktop checkout")
    source = clean_source(args.source)
    hepta = clean_source(args.hepta_root)
    lock = args.source / "ui/Cargo.lock"
    require(git(args.source, "ls-files", "--error-unmatch", "ui/Cargo.lock") == "ui/Cargo.lock", "candidate lock must be committed")
    toolchain = tomllib.loads((args.source / "ui/rust-toolchain.toml").read_text())["toolchain"]["channel"]
    inputs = [lock, args.source / "ui/Cargo.toml", args.source / "ui/rust-toolchain.toml",
              args.sdk_cargo_config, args.original_metadata]
    bound = stable_files(inputs)
    env = os.environ.copy()
    env["CARGO_TARGET_DIR"] = str(args.target_dir)
    env["CARGO_BUILD_JOBS"] = str(args.jobs)
    receipt.update(desktop=source, hepta=hepta, toolchain=toolchain, feature=FEATURE, profile=args.profile,
                   source_commit=source["commit"], source_tree=source["tree"],
                   inputs_sha256=bound, target_dir=str(args.target_dir),
                   environment={key: env[key] for key in ("CARGO_TARGET_DIR", "CARGO_BUILD_JOBS", "RUSTUP_TOOLCHAIN", "RUSTFLAGS",
                                                         "CARGO_ENCODED_RUSTFLAGS", "CARGO_BUILD_TARGET", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER") if key in env})
    version = subprocess.run([args.cargo, "+" + toolchain, "--version", "--verbose"], cwd=args.source,
                             env=env, check=True, capture_output=True, timeout=30)
    (args.output / "cargo-version.txt").write_bytes(version.stdout + version.stderr)
    receipt["cargo_version"] = version.stdout.decode().strip()
    original_lock = lock.read_bytes()
    (args.output / "candidate-Cargo.lock").write_bytes(original_lock)
    profile = None
    for name, command in cargo_commands(args, toolchain):
        ensure_stable(inputs, bound)
        require(clean_source(args.source) == source and clean_source(args.hepta_root) == hepta, "source changed between verification steps")
        if profile is not None:
            require(verify_graph(args, (args.output / "metadata.stdout.log").read_bytes(), hepta["commit"]) == profile,
                    "prepared SDK source graph changed between verification steps")
        entry = {"name": name, "argv": command, "cwd": str(args.source), "started_unix": time.time(), "passed": False}
        receipt["steps"].append(entry)
        (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps({"step": name, "argv": command}), flush=True)
        with (args.output / f"{name}.stdout.log").open("wb") as stdout, (args.output / f"{name}.stderr.log").open("wb") as stderr:
            completed = subprocess.run(command, cwd=args.source, env=env, stdout=stdout, stderr=stderr, timeout=args.step_timeout)
        entry.update(exit_code=completed.returncode, duration_seconds=time.time() - entry["started_unix"])
        ensure_stable(inputs, bound)
        require(completed.returncode == 0, f"{name} failed; inspect its retained stdout/stderr; the candidate lock was not updated")
        if name == "metadata":
            profile = verify_graph(args, (args.output / "metadata.stdout.log").read_bytes(), hepta["commit"])
            (args.output / "verified-sdk-source.json").write_text(json.dumps(profile, indent=2) + "\n")
        entry["passed"] = True
    require(lock.read_bytes() == original_lock, "candidate lock changed")
    require(clean_source(args.source) == source and clean_source(args.hepta_root) == hepta, "source changed during final build")
    require(verify_graph(args, (args.output / "metadata.stdout.log").read_bytes(), hepta["commit"]) == profile,
            "prepared SDK changed during final build")
    binary_dir = args.target_dir / ("debug" if args.profile == "dev" else "release")
    target = env.get("CARGO_BUILD_TARGET")
    if target:
        binary_dir = args.target_dir / target / binary_dir.name
    binaries = {}
    for name in BINARIES:
        path = binary_dir / name
        require(path.is_file() and os.access(path, os.X_OK), f"missing real Linux binary: {path}")
        with path.open("rb") as binary:
            require(binary.read(4) == b"\x7fELF", f"built program is not a Linux ELF binary: {path}")
        binaries[name] = {"path": str(path), "bytes": path.stat().st_size, "sha256": sha(path)}
    # Keep the original native-window qualifier's build-receipt interface.
    # These fields are set only after every actual command and final source /
    # binary check succeeds; callers need not synthesize another receipt.
    receipt.update(binaries=binaries, compiled=True, passed=True, status="passed", exit_code=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--hepta-root", type=Path, required=True)
    parser.add_argument("--prepared-sdk", type=Path, required=True)
    parser.add_argument("--sdk-cargo-config", type=Path, required=True)
    parser.add_argument("--original-metadata", type=Path, required=True)
    parser.add_argument("--target-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--profile", choices=("dev", "release"), default="release")
    parser.add_argument("--cargo", default="cargo", help="rustup Cargo entry point")
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--step-timeout", type=int, default=3600)
    parser.add_argument("--offline", action="store_true")
    args = parser.parse_args()
    require(1 <= args.jobs <= 64 and 1 <= args.step_timeout <= 86400, "invalid build limits")
    for name in ("source", "hepta_root", "prepared_sdk", "sdk_cargo_config", "original_metadata", "target_dir", "output"):
        setattr(args, name, getattr(args, name).resolve())
    require(not args.output.is_relative_to(args.source), "evidence must stay outside the source checkout")
    args.output.mkdir(mode=0o700, parents=False, exist_ok=False)
    receipt = {"schema": "trillionnium.native-sdk-candidate-build.v1", "passed": False, "compiled": False,
               "status": "running", "exit_code": None, "binaries": {},
               "runtime_qualified": False, "production_authority": False, "steps": [], "runner_sha256": sha(Path(__file__).resolve())}
    try:
        run(args, receipt)
        return 0
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        receipt["error"] = f"{type(error).__name__}: {error}"
        receipt.update(status="failed", exit_code=1)
        return 1
    finally:
        (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
        print(json.dumps(receipt), flush=True)


if __name__ == "__main__":
    sys.exit(main())
