#!/usr/bin/env python3
"""Bind the existing input-reader patch to a complete current source replay."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess


NATIVE_FILES = {
    "Cargo.lock",
    "runtime/droidloom-applications/Cargo.toml",
    "runtime/droidloom-applications/src/release.rs",
}


def need(value, message):
    if not value:
        raise RuntimeError(message)


def content_digest(value):
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(raw).hexdigest()


def check_file(path, expected):
    before = path.lstat()
    need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1,
         "one regular source file required: " + str(path))
    raw = path.read_bytes()
    after = path.lstat()
    need((before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns)
         == (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
         "source identity changed during reading")
    need(len(raw) == expected["bytes"]
         and hashlib.sha256(raw).hexdigest() == expected["sha256"],
         "source identity differs: " + str(path))
    return raw


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], timeout=30)


def native_row(name, record):
    return {"path": name, "bytes": record["bytes"], "sha256": record["sha256"],
            "git_blob": record["git_blob"], "mode": record["git_mode"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-packet", type=Path, required=True)
    parser.add_argument("--wrapper-commit", required=True)
    parser.add_argument("--inventory-sha256", required=True)
    parser.add_argument("--native-root", type=Path, required=True)
    parser.add_argument("--verify-applied", action="store_true")
    parser.add_argument("--prior-report", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    need(not os.path.lexists(args.output), "evidence output already exists")
    need(args.verify_applied == (args.prior_report is not None),
         "after-tests verification requires its original before-tests report")
    packet = Path(__file__).resolve().parents[1]
    manifest = json.loads((packet / "source-manifest.json").read_text())
    need(manifest["schema"] == "p4-native-app-frozen-read-source-v3",
         "current packet schema required")
    actual_files = {str(p.relative_to(packet)) for p in packet.rglob("*")
                    if (p.is_file() or p.is_symlink()) and p != packet / "source-manifest.json"}
    need(actual_files == set(manifest["files"]), "packet file inventory differs")
    for name, expected in manifest["files"].items():
        relative = Path(name)
        need(not relative.is_absolute() and ".." not in relative.parts, "invalid packet path")
        check_file(packet / relative, expected)
    check_file(packet.parents[4] / manifest["ci_workflow"]["relative"], manifest["ci_workflow"])
    need(set(manifest["native_files"]) == NATIVE_FILES, "native patch inventory differs")

    public = args.source_packet.resolve(strict=True)
    wrapper = manifest["source_wrapper"]
    need(args.wrapper_commit == wrapper["commit"]
         and args.inventory_sha256 == wrapper["inventory"]["sha256"],
         "external wrapper and inventory pins differ")
    need(public.name == "runtime-current-source-r1"
         and public.parent.name == "pocket4"
         and public.parent.parent.name == "android"
         and public.parent.parent.parent.name == "compat",
         "original public capsule location required")
    wrapper_root = public.parents[3]
    need(git(wrapper_root, "rev-parse", "HEAD").decode().strip() == args.wrapper_commit
         and git(wrapper_root, "rev-parse", "HEAD^{tree}").decode().strip() == wrapper["tree"],
         "source-wrapper checkout identity differs")
    check_file(public / "FILES.sha256", wrapper["inventory"])
    verifier_path = public / "verify.py"
    check_file(verifier_path, wrapper["verifier"])

    # This fixed verifier only validates source data and writes a fresh source
    # replay. No producer module, test controller or runtime entry is imported.
    spec = importlib.util.spec_from_file_location("p4_current_source_verifier", verifier_path)
    need(spec is not None and spec.loader is not None, "source verifier import unavailable")
    verifier = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(verifier)
    need(verifier.HEAD_COMMIT is None
         and verifier.PARENT_COMMIT == manifest["source_parent_commit"]
         and verifier.PARENT_TREE == manifest["source_parent_tree"]
         and verifier.HEAD_TREE == manifest["native_tree_before"]
         and verifier.SOURCE_FILES == manifest["native_files_count"]
         and verifier.SOURCE_BYTES == manifest["native_bytes_before"],
         "complete native source generation differs")
    capsule = verifier.verify_capsule(args.inventory_sha256)
    rows = capsule["rows"]
    need(len(rows) == manifest["native_files_count"]
         and content_digest(rows) == manifest["native_rows_sha256_before"],
         "complete original native rows differ")
    by_name = {row["path"]: row for row in rows}
    for name, record in manifest["native_files"].items():
        need(by_name[name] == native_row(name, record["before"]),
             "patch input is not the current original source: " + name)
        by_name[name] = native_row(name, record["after"])
    after_rows = [by_name[name] for name in sorted(by_name)]
    need(verifier.tree_id(after_rows) == manifest["native_tree_after"]
         and sum(row["bytes"] for row in after_rows) == manifest["native_bytes_after"]
         and content_digest(after_rows) == manifest["native_rows_sha256_after"],
         "complete patched native source identity differs")

    root = args.native_root.absolute()
    if args.verify_applied:
        need(root.resolve(strict=True) == root, "canonical native source directory required")
        prior = json.loads(args.prior_report.read_text())
        need(prior["schema"] == "p4-current-frozen-read-native-bookend-v1"
             and prior["status"] == "applied-and-verified"
             and prior["source_wrapper_commit"] == args.wrapper_commit
             and prior["source_tree_after"] == manifest["native_tree_after"]
             and prior["native_rows_sha256_after"] == manifest["native_rows_sha256_after"],
             "matching original before-tests report required")
    else:
        need(not os.path.lexists(root), "native replay destination must be new")
        verifier.replay(capsule, root)
        for name, record in manifest["native_files"].items():
            check_file(root / name, record["before"])
        patch = str(packet / "native-frozen-read.patch")
        git(root, "apply", "--check", patch)
        git(root, "apply", patch)
    need(not os.path.lexists(root / ".git"), "portable producer must not contain Git metadata")
    snapshot = verifier.source_snapshot(root, after_rows, manifest["native_tree_after"])
    snapshot_sha = content_digest(snapshot)
    if args.verify_applied:
        need(snapshot_sha == prior["physical_source_snapshot_sha256"],
             "native file or directory identity changed during the Cargo commands")
    for name, record in manifest["native_files"].items():
        check_file(root / name, record["after"])

    result = {
        "schema": "p4-current-frozen-read-native-bookend-v1",
        "status": "verified-after-tests" if args.verify_applied else "applied-and-verified",
        "source_wrapper_commit": args.wrapper_commit,
        "source_wrapper_inventory_sha256": args.inventory_sha256,
        "source_parent_commit": manifest["source_parent_commit"],
        "source_parent_tree": manifest["source_parent_tree"],
        "source_commit": None,
        "source_tree_before": manifest["native_tree_before"],
        "source_tree_after": manifest["native_tree_after"],
        "verified_tracked_files": len(after_rows),
        "changed_files": sorted(NATIVE_FILES),
        "native_rows_sha256_before": manifest["native_rows_sha256_before"],
        "native_rows_sha256_after": manifest["native_rows_sha256_after"],
        "physical_source_snapshot_sha256": snapshot_sha,
        "full_original_capsule_verified": True,
        "full_original_overlay_verified": True,
        "historical_tests_counted_as_fresh": 0,
        "Android_actions": 0,
        "runtime_qualified": False,
        "production_ready": False,
    }
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
