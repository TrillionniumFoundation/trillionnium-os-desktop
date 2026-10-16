#!/usr/bin/env python3
"""Reconstruct the measured manifest-race runners in fresh scratch from Git."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys


BEFORE_COMMIT = "3d561fed0f106a3c7af0330e1d722d31b8ce7a9a"
FIX_COMMIT = "2c658089bb90aa5b254ddf336ef3dc1333e755c9"
BEFORE_SHA = "9176bf7bdb80aae53f75723b5c372771167d7e1c36e3e7a0786bf1472a42430f"
AFTER_SHA = "3a5a210c365a565c2d1e57def0413e5a7c33e972130e2d0879b68ed678c60740"
TEST_SHA = "8f2e1a8ae03304aa3ff40ef3f02ec9df0f3e4d49c5df4f7fe72a34113d546b3b"
CHECKER_SHA = "eceab88787bd80a169f6036f35532f183937de81045f9ea97e943ec347720f21"


def git_file(repository, commit, path):
    return subprocess.check_output(["git", "show", f"{commit}:{path}"], cwd=repository)


def checked_write(path, content, expected):
    actual = hashlib.sha256(content).hexdigest()
    if actual != expected:
        raise ValueError(f"source reconstruction mismatch for {path}: {actual} != {expected}")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path, help="must not already exist")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    before = git_file(args.repository, BEFORE_COMMIT, "support/build/kernel.sh")
    after = git_file(args.repository, FIX_COMMIT, "support/build/kernel.sh")
    # The measured fixed runner preceded the later live-artifact boot check.
    # Restore only that exact argument change; hash verification pins the bytes.
    old = b'"$run_dir" --live-artifacts'
    if after.count(old) != 1:
        raise ValueError("cannot locate the unique post-measurement boot-check change")
    after = after.replace(old, b'"$run_dir"')
    tests = git_file(args.repository, FIX_COMMIT, "support/build/tests/test_kernel_runner.py")
    checker = git_file(args.repository, BEFORE_COMMIT, "support/build/check-boot.py")
    commands = []
    for variant, runner, expected in (("before", before, BEFORE_SHA), ("after", after, AFTER_SHA)):
        build = args.output / variant / "support/build"
        checked_write(build / "kernel.sh", runner, expected)
        checked_write(build / "tests/test_kernel_runner.py", tests, TEST_SHA)
        # The injected TERM happens before make or checker invocation. This
        # helper is copied by the test fixture but never executed by that case.
        checked_write(build / "check-boot.py", checker, CHECKER_SHA)
        command = [sys.executable, "-I", str(build / "tests/test_kernel_runner.py")]
        if variant == "before":
            command.append("KernelRunnerTests.test_signal_immediately_after_manifest_publication_cleans_owned_inode")
        commands.append({"variant": variant, "argv": command, "expected_exit": 1 if variant == "before" else 0})
    print(json.dumps({"source_hashes_verified": True, "commands": commands}, indent=2))


if __name__ == "__main__":
    main()
