#!/usr/bin/env python3
"""Replay pinned public patches offline; do not build or activate Android."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def digest(path):
    data = path.read_bytes()
    return len(data), hashlib.sha256(data).hexdigest()


def verify_files(work, files, phase):
    verified = {}
    for item in files:
        path = work / item["path"]
        if path.is_symlink() or not path.is_file():
            raise ValueError("source must be a regular file: " + item["path"])
        actual = digest(path)
        expected = item[phase + "_bytes"], item[phase + "_sha256"]
        if actual != expected:
            raise ValueError(phase + " source pin mismatch: " + item["path"])
        verified[item["path"]] = {"bytes": actual[0], "sha256": actual[1]}
    return verified


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path)
    args = parser.parse_args()
    here = Path(__file__).resolve().parent
    repo = (args.repo_root or here.parents[3]).resolve()
    manifest = json.loads((here / "source-chain.json").read_text())
    git = shutil.which("git")
    if git is None:
        raise RuntimeError("git is required; no dependency installation is attempted")
    patches = []
    for item in manifest["chain"]:
        path = (repo / item["path"]).resolve()
        if not path.is_relative_to(repo) or not path.is_file():
            raise ValueError("patch missing or outside checkout: " + item["path"])
        if digest(path) != (item["bytes"], item["sha256"]):
            raise ValueError("patch pin mismatch: " + item["path"])
        patches.append((item, path))
    env = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull,
               GIT_OPTIONAL_LOCKS="0", GIT_TERMINAL_PROMPT="0")
    before = None
    with tempfile.TemporaryDirectory(prefix="pocket4-identity-source-") as directory:
        work = Path(directory)

        def run(*arguments):
            subprocess.run([git, "-C", directory, "-c", "core.autocrlf=false", *arguments],
                           check=True, env=env, capture_output=True, timeout=30)

        run("init", "-q")
        for item, path in patches:
            run("apply", "--index", "--check", str(path))
            run("apply", "--index", str(path))
            if item.get("checkpoint") == "before-review":
                before = verify_files(work, manifest["files"], "before")
        if before is None:
            raise ValueError("missing identity source preimage checkpoint")
        after = verify_files(work, manifest["files"], "after")
    print(json.dumps({"schema": "pocket4-identity-source-replay-result-v1",
                      "status": "SOURCE_CHAIN_VERIFIED", "patches": len(patches),
                      "before": before, "after": after,
                      "rust_tests_executed": False, "runtime_qualified": False,
                      "production_ready": False}, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        raise SystemExit("source replay rejected: " + str(error)) from error
