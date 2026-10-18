#!/usr/bin/env python3
"""Validate the candidate in a new Git archive; never patch an owner worktree."""

import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import platform
import re
import subprocess
import sys
import tarfile
import time

BASE = "eef96afd4c3fcdc5bcdc2b8ba00260e1fb116b91"
TOOLCHAIN = "nightly-2026-07-21"
PATHS = ("libs/os-abi", "tests/golden")
CHANGED = tuple(
    "libs/os-abi/tests/" + name
    for name in ("mutation_kill.rs", "transport_preflight.rs", "transport_vectors.rs")
)


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def git(repo, *args):
    return subprocess.check_output(["git", "-C", str(repo), *args])


def snapshot(source, records):
    return {
        name: {"bytes": (source / name).stat().st_size,
               "sha256": sha256((source / name).read_bytes())}
        for name in records
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path,
                        help="new, nonexistent directory outside the repository")
    parser.add_argument("--cargo-home", required=True, type=Path)
    parser.add_argument("--rustup-home", required=True, type=Path)
    args = parser.parse_args()
    repo = args.repository.resolve(strict=True)
    work = args.work_dir.absolute()
    if work == repo or repo in work.parents:
        parser.error("--work-dir must be outside the repository")
    work.mkdir(parents=True, exist_ok=False)
    work = work.resolve(strict=True)
    source = work / "source"
    source.mkdir()
    logs = work / "logs"
    logs.mkdir()
    cargo_home = args.cargo_home.resolve(strict=True)
    rustup_home = args.rustup_home.resolve(strict=True)
    cargo = cargo_home / "bin/cargo"
    patch = Path(__file__).resolve().with_name("nightly-2026-07-21.patch")
    env = dict(os.environ)
    for name in ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS", "RUSTC", "RUSTC_WRAPPER",
                 "RUSTC_WORKSPACE_WRAPPER", "RUSTDOC", "RUSTDOCFLAGS", "MAKEFLAGS",
                 "MFLAGS", "MAKELEVEL", "MAKEOVERRIDES", "CARGO_ENCODED_RUSTDOCFLAGS"):
        env.pop(name, None)
    env.update(CARGO_HOME=str(cargo_home), RUSTUP_HOME=str(rustup_home),
               RUSTUP_TOOLCHAIN=TOOLCHAIN, CARGO_NET_OFFLINE="true",
               CARGO_BUILD_JOBS="2", CARGO_TARGET_DIR=str(work / "target"),
               LC_ALL="C", TZ="UTC")
    env["PATH"] = str(cargo_home / "bin") + os.pathsep + env.get("PATH", "")
    selected = {name: env.get(name) for name in (
        "CARGO_HOME", "RUSTUP_HOME", "RUSTUP_TOOLCHAIN", "CARGO_NET_OFFLINE",
        "CARGO_BUILD_JOBS", "CARGO_TARGET_DIR", "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS",
        "RUSTC", "RUSTC_WRAPPER", "RUSTC_WORKSPACE_WRAPPER", "LC_ALL", "TZ")}
    write_json(work / "environment.json", {
        "environment": selected, "platform": platform.platform(),
        "python": sys.version, "host": platform.node(),
        "euid": os.geteuid(), "base": BASE,
        "base_tree": git(repo, "rev-parse", BASE + "^{tree}").decode().strip(),
        "patch_sha256": sha256(patch.read_bytes()),
        "target_initially_absent": not (work / "target").exists(),
        "scope": "isolated host ABI tests and no_std target compile; no kernel acceptance",
    })
    records = {}
    listing = git(repo, "ls-tree", "-r", "-z", BASE, "--", *PATHS)
    for entry in listing.split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        mode, kind, blob = metadata.decode().split()
        if mode != "100644" or kind != "blob":
            raise RuntimeError("unexpected archive input mode: " + metadata.decode())
        records[name.decode()] = {"mode": mode, "git_blob": blob}
    raw_archive = git(repo, "archive", "--format=tar", BASE, *PATHS)
    (work / "source-before.tar.gz").write_bytes(gzip.compress(raw_archive, mtime=0))
    with tarfile.open(fileobj=io.BytesIO(raw_archive), mode="r:") as archive:
        for member in archive.getmembers():
            relative = PurePosixPath(member.name)
            if relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError("unsafe archive path")
            dest = source.joinpath(*relative.parts)
            if member.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            elif member.isfile() and member.name in records:
                dest.parent.mkdir(parents=True, exist_ok=True)
                data = archive.extractfile(member).read()
                framed = b"blob " + str(len(data)).encode() + b"\0" + data
                if hashlib.sha1(framed).hexdigest() != records[member.name]["git_blob"]:
                    raise RuntimeError("archive/Git mismatch: " + member.name)
                dest.write_bytes(data)
            else:
                raise RuntimeError("unexpected archive entry: " + member.name)
    before = snapshot(source, records)
    write_json(work / "source-before.json", {
        name: dict(records[name], **before[name]) for name in records
    })
    results = []

    def run(name, argv, expected=0, cwd=source):
        start = time.time_ns()
        completed = subprocess.run(argv, cwd=cwd, env=env, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
        end = time.time_ns()
        output = completed.stdout
        (logs / (name + ".log")).write_bytes(output)
        record = {"name": name, "argv": list(map(str, argv)), "cwd": str(cwd),
                  "environment": selected, "start_unix_ns": start, "end_unix_ns": end,
                  "returncode": completed.returncode, "expected_returncode": expected,
                  "log_sha256": sha256(output), "log_bytes": len(output)}
        write_json(logs / (name + ".json"), record)
        results.append(record)
        if completed.returncode != expected:
            raise RuntimeError(name + " unexpected exit " + str(completed.returncode))
        return output

    run("rustc-version", [cargo_home / "bin/rustc", "--version", "--verbose"])
    run("cargo-version", [cargo, "--version", "--verbose"])
    run("clippy-version", [cargo, "clippy", "--version"])
    run("rustfmt-version", [cargo, "fmt", "--version"])
    manifest = ["--manifest-path", "libs/os-abi/Cargo.toml"]
    baseline = run("before-clippy", [cargo, "clippy", *manifest,
                   "--all-targets", "--offline", "--", "-D", "warnings"], expected=101)
    if b"chunks_exact_to_as_chunks" not in baseline:
        raise RuntimeError("expected baseline lint absent")
    run("patch-check", ["git", "apply", "--check", "--directory=source", str(patch)], cwd=work)
    run("patch-apply", ["git", "apply", "--directory=source", str(patch)], cwd=work)
    after_patch = snapshot(source, records)
    changed = sorted(name for name in records if before[name] != after_patch[name])
    if changed != sorted(CHANGED):
        raise RuntimeError("candidate changed unexpected source paths: " + repr(changed))
    for name in changed:
        if b"chunks_exact(2)" in (source / name).read_bytes():
            raise RuntimeError("unconverted helper: " + name)
    run("after-fmt", [cargo, "fmt", *manifest, "--", "--check"])
    tests = run("after-test", [cargo, "test", *manifest, "--all-targets", "--offline"])
    counts = re.findall(rb"test result: ok\. (\d+) passed; (\d+) failed; (\d+) ignored;"
                        rb" (\d+) measured; (\d+) filtered out;", tests)
    if not counts or any(int(value) for count in counts for value in count[1:]):
        raise RuntimeError("missing test totals or unexpected non-passing tests")
    run("after-no-std", [cargo, "check", *manifest, "--target", "x86_64-unknown-none",
                         "--no-default-features", "--offline"])
    run("after-clippy", [cargo, "clippy", *manifest, "--all-targets", "--offline",
                         "--", "-D", "warnings"])
    final = snapshot(source, records)
    if final != after_patch:
        raise RuntimeError("validation modified candidate source")
    lock = source / "libs/os-abi/Cargo.lock"
    (work / "generated-Cargo.lock").write_bytes(lock.read_bytes())
    write_json(work / "source-after.json", final)
    write_json(work / "result.json", {
        "status": "validated_candidate_pending_owner_adoption", "base": BASE,
        "source_file_count": len(records), "changed_paths": changed,
        "unchanged_source_count": len(records) - len(changed),
        "library_and_golden_bytes_unchanged": all(before[name] == final[name]
             for name in records if name.startswith("libs/os-abi/src/") or
             name.startswith("tests/golden/")),
        "assertions_preserved": {
            "mutation_kill": "assert_eq!(bytes.len() % 2, 0)",
            "transport_vectors": "assert_eq!(ascii.len(), TRANSPORT_LEN * 2)",
            "transport_preflight": "no length assertion in base; iteration change only",
        },
        "tests_passed": sum(int(count[0]) for count in counts),
        "test_binaries": len(counts), "test_failed": 0, "test_ignored": 0,
        "test_filtered": 0, "baseline_clippy_exit": 101,
        "candidate_fmt_exit": 0, "candidate_test_exit": 0,
        "candidate_no_std_target_check_exit": 0, "candidate_clippy_exit": 0,
        "target": "x86_64-unknown-none", "toolchain": TOOLCHAIN,
        "generated_lock_sha256": sha256(lock.read_bytes()),
        "owner_worktree_modified": False, "owner_branch_modified": False,
        "main_blocker_closed": False, "kernel_acceptance_claimed": False,
        "commands": results,
    })
    print(json.dumps({"status": "validated_candidate_pending_owner_adoption",
                      "tests_passed": sum(int(count[0]) for count in counts),
                      "work_dir": str(work)}))


if __name__ == "__main__":
    main()
