#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Reconstruct LMKD r3/r4/r5 source only; never run Android or pressure."""
import argparse, hashlib, io, json
from pathlib import Path
import shutil, subprocess, tarfile, tempfile
UPSTREAM = "c3601e823bd07c9c190f67e2f9bc7486e4978328"
HERE = Path(__file__).resolve().parents[1]

def run(argv, cwd=None):
    result = subprocess.run(argv, cwd=cwd, capture_output=True, timeout=30)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace"))
    return result.stdout

def verify(tree, manifest):
    actual = {}
    for path in tree.rglob("*"):
        if path.is_symlink():
            raise RuntimeError("Unexpected source symlink")
        if path.is_file():
            raw = path.read_bytes()
            actual[path.relative_to(tree).as_posix()] = {
                "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    if actual != manifest["files"] or len(actual) != manifest["file_count"]:
        raise RuntimeError("Source inventory/hash mismatch")
    return len(actual)

def apply(tree, patch, reverse=False):
    args = ["git", "apply"] + (["--reverse"] if reverse else [])
    run(args + ["--check", str(patch)], tree)
    run(args + [str(patch)], tree)

def reconstruct(upstream, out):
    out.mkdir()
    commit = run(["git", "-C", str(upstream), "rev-parse", UPSTREAM + "^{commit}"]).decode().strip()
    if commit != UPSTREAM:
        raise RuntimeError("Upstream commit mismatch")
    archive = run(["git", "-C", str(upstream), "archive", "--format=tar", UPSTREAM])
    original = out / "upstream"; original.mkdir()
    links = json.loads((HERE / "manifests/upstream-symlinks.json").read_text())["symlinks"]
    observed_links = {}
    with tarfile.open(fileobj=io.BytesIO(archive)) as stream:
        materialized = []
        for member in stream.getmembers():
            if member.name.startswith("/") or ".." in Path(member.name).parts:
                raise RuntimeError("Unsafe upstream archive path")
            if member.issym():
                observed_links[member.name] = member.linkname
            elif member.isfile() or member.isdir():
                materialized.append(member)
            else:
                raise RuntimeError("Unexpected upstream archive member")
        if observed_links != links:
            raise RuntimeError("Upstream symlink metadata changed")
        # The upstream formatter link escapes this small repository into AOSP
        # build/soong. Record its exact metadata; never follow or materialize it.
        stream.extractall(original, members=materialized, filter="data")
    manifests = {stage: json.loads((HERE / "manifests" / (stage + "-source.json")).read_text())
                 for stage in ("r3", "r4", "r5")}
    r4 = out / "r4"; shutil.copytree(original, r4)
    apply(r4, HERE / "patches/0001-upstream-to-r4.patch")
    counts = {"r4": verify(r4, manifests["r4"])}
    r3 = out / "r3"; shutil.copytree(r4, r3)
    apply(r3, HERE / "patches/r3-to-r4-negative-baseline.patch", reverse=True)
    counts["r3"] = verify(r3, manifests["r3"])
    r5 = out / "r5"; shutil.copytree(r4, r5)
    apply(r5, HERE / "patches/0002-r4-to-r5-pending-evidence.patch")
    counts["r5"] = verify(r5, manifests["r5"])
    supplied = 0
    for stage in ("r4", "r5"):
        for source in (HERE / ("source-" + stage)).iterdir():
            if source.is_file():
                if source.read_bytes() != (out / stage / source.name).read_bytes():
                    raise RuntimeError("Supplied source differs from reconstructed source")
                supplied += 1
    return {"schema": "pocket4-lmkd-source-reconstruction-v1", "upstream_commit": UPSTREAM,
            "full_source_file_counts": counts, "supplied_files_matched": supplied,
            "r3_reconstructed_by_inverse_delta": True, "all_regular_source_hashes_matched": True,
            "upstream_symlink_metadata_verified": observed_links,
            "external_formatter_target_materialized": False,
            "android_binary_rebuilt": False, "live_fixture_executed": False,
            "production_ready": False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-repo", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, help="New directory retaining reconstructed source trees")
    parser.add_argument("--receipt", type=Path)
    args = parser.parse_args()
    if args.out_dir:
        result = reconstruct(args.upstream_repo.resolve(), args.out_dir.resolve())
    else:
        with tempfile.TemporaryDirectory(prefix="pocket4-lmkd-source-") as folder:
            result = reconstruct(args.upstream_repo.resolve(), Path(folder) / "trees")
    text = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.receipt:
        with args.receipt.open("x") as output:
            output.write(text)
    print(text, end="")

if __name__ == "__main__":
    main()
