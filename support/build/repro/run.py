#!/usr/bin/env python3
"""Opt-in clean kernel build with coherent compiler/component path projection."""
import argparse
import datetime
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import pwd
import socket
import subprocess
import sys

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("a01_repro_profile", HERE / "profile.py")
profile = importlib.util.module_from_spec(spec)
spec.loader.exec_module(profile)


def fixed_rustc_version(cargo_home):
    # Match kernel.sh even when this launcher's caller defaults to stable.
    return subprocess.run([str(cargo_home / "bin/rustc"), "+nightly-2026-07-21", "-vV"],
                          check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--checkout", required=True, type=Path)
    parser.add_argument("--profile-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--action", choices=("kernel", "run_kernel"), default="run_kernel")
    args = parser.parse_args()
    checkout = profile.safe_root(args.checkout)
    source = profile.safe_root(checkout / "kernel/asterinas")
    root = profile.safe_root(args.profile_root)
    virtual = root / "virtual-asterinas"
    output = profile.safe_root(args.output)
    for left, right in ((source, root), (source, output), (root, output)):
        if left == right or left in right.parents or right in left.parents:
            raise ValueError("source, profile and output must be disjoint directories")
    if "src/" in str(virtual) + "/" or "tests/" in str(virtual) + "/":
        raise ValueError("virtual prefix conflicts with the pinned runtime's first src/tests split")
    if (source / "target").exists() or (source / "target").is_symlink():
        raise ValueError("this proof profile requires an absent kernel target directory")
    if "CARGO_ENCODED_RUSTFLAGS" in os.environ or os.environ.get("RUSTC_WRAPPER") or os.environ.get("RUSTC_WORKSPACE_WRAPPER") or os.environ.get("RUSTFLAGS"):
        raise ValueError("unset inherited compiler flags/wrappers before this explicit profile")
    raw_components, component_identity = profile.regular(source / "Components.toml")
    scripts = profile.code_hashes(HERE)
    owner = {"schema": profile.SCHEMA, "profile_root": str(root),
             "components_sha256": profile.digest(raw_components), "code_sha256": scripts,
             "embedded_builder": {"username": "a01-repro", "hostname": "a01-fixed-profile"}}
    created = False
    try:
        root.mkdir(mode=0o700)
        created = True
    except FileExistsError:
        pass
    if created:
        virtual.mkdir(mode=0o700)
        profile.exclusive(virtual / "Components.toml", raw_components, 0o400)
        profile.materialize_helpers(root / "helpers", HERE)
        profile.exclusive(root / "lock", b"")
        profile.exclusive(root / "owner.json", (json.dumps(owner, sort_keys=True) + "\n").encode())
    existing = json.loads(profile.regular(root / "owner.json")[0])
    if existing != owner:
        raise ValueError("foreign or incompatible profile directory; refusing to overwrite")
    if profile.helper_hashes(root) != {name: scripts[name] for name in profile.HELPERS}:
        raise ValueError("profile executable closure differs from its recorded source")
    before_lock = profile.snapshot(root)
    lock = os.open(root / "lock", os.O_RDWR | os.O_NOFOLLOW)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if profile.identity(os.fstat(lock)) != before_lock["lock"]["identity"]:
            raise ValueError("profile lock inode changed")
        before = profile.snapshot(root)
        if before != before_lock:
            raise ValueError("profile changed while acquiring its lock")
        if (source / "target").exists() or (source / "target").is_symlink():
            raise ValueError("kernel target appeared while acquiring the profile lock")
        output.mkdir(mode=0o700)
        (output / "metadata").mkdir(mode=0o700)
        cargo_home = Path(os.environ.get("CARGO_HOME", str(Path.home() / ".cargo")))
        real_cargo = os.path.abspath(cargo_home / "bin/cargo")
        rustc_version = fixed_rustc_version(cargo_home)
        policy = dict(owner, real_root=str(source), virtual_root=str(virtual),
                      output=str(output), real_cargo=real_cargo,
                      rustc_identity=profile.digest(rustc_version), rustc_version=rustc_version.decode(),
                      profile_snapshot=before, source_components_identity=component_identity,
                      target_absent_at_prelaunch=True, actual_host={"hostname": socket.gethostname(),
                      "username": pwd.getpwuid(os.getuid()).pw_name, "uid": os.getuid(),
                      "uname": list(os.uname())})
        policy_path = output / "policy.json"
        profile.exclusive(policy_path, (json.dumps(policy, indent=2) + "\n").encode())
        env = os.environ.copy()
        env.update(A01_REPRO_POLICY=str(policy_path), RUSTC_WRAPPER=str(root / "helpers/rustc-wrapper.py"),
                   CARGO_TARGET_DIR=str(source / "target"), CARGO_INCREMENTAL="0",
                   RUSTFLAGS=f"--remap-path-prefix={source}={virtual}",
                   ASTER_BUILD_TIMESTAMP="Thu Jan  1 00:00:00 UTC 1970",
                   SOURCE_DATE_EPOCH="0", TZ="UTC", LC_ALL="C",
                   A01_RUN_DIR=str(output / "kernel-run"))
        command = [str(checkout / "support/build/kernel.sh"), args.action]
        start = datetime.datetime.now(datetime.timezone.utc).isoformat()
        with (output / "console.log").open("xb") as log:
            result = subprocess.run(command, cwd=checkout, env=env, stdout=log, stderr=subprocess.STDOUT)
        custody_ok = profile.snapshot(root) == before
        source_ok = profile.regular(source / "Components.toml") == (raw_components, component_identity)
        code_ok = profile.code_hashes(HERE) == scripts
        status = result.returncode if result.returncode else (0 if custody_ok and source_ok and code_ok else 1)
        receipt = {"command": command, "started": start,
                   "finished": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                   "child_returncode": result.returncode, "returncode": status,
                   "profile_custody_unchanged": custody_ok, "source_components_unchanged": source_ok,
                   "profile_code_unchanged": code_ok,
                   "scope": "same-host opt-in path projection; independent-host reproduction not claimed"}
        profile.exclusive(output / "result.json", (json.dumps(receipt, indent=2) + "\n").encode())
        return status
    finally:
        os.close(lock)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as error:
        print(f"reproduction profile refused: {error}", file=sys.stderr)
        raise SystemExit(2)
