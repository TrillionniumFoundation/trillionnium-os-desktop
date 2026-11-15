#!/usr/bin/env python3
"""Verify the complete pinned native tree and apply its bounded-input correction."""
import argparse
import hashlib
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-root", type=Path, required=True)
    parser.add_argument("--verify-applied", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise RuntimeError("evidence output already exists")
    packet = Path(__file__).resolve().parents[1]
    manifest = json.loads((packet / "source-manifest.json").read_text())
    root = args.native_root.resolve(strict=True)

    def git(*argv):
        return subprocess.check_output(["git", "-C", str(root), *argv], timeout=30)

    def check_file(path, expected):
        if path.is_symlink() or not path.is_file():
            raise RuntimeError("regular source file required: " + str(path))
        raw = path.read_bytes()
        if len(raw) != expected["bytes"] or hashlib.sha256(raw).hexdigest() != expected["sha256"]:
            raise RuntimeError("source identity differs: " + str(path))
        return raw

    actual_files = {str(p.relative_to(packet)) for p in packet.rglob("*")
                    if (p.is_file() or p.is_symlink()) and p != packet / "source-manifest.json"}
    if actual_files != set(manifest["files"]):
        raise RuntimeError("packet file inventory differs")
    for name, expected in manifest["files"].items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("invalid packet path")
        check_file(packet / relative, expected)
    check_file(packet.parents[4] / manifest["ci_workflow"]["relative"], manifest["ci_workflow"])
    if git("rev-parse", "HEAD").decode().strip() != manifest["native_base_commit"]:
        raise RuntimeError("native checkout commit differs")
    if git("rev-parse", "HEAD^{tree}").decode().strip() != manifest["native_base_tree"]:
        raise RuntimeError("native checkout tree differs")
    index = git("ls-files", "--stage", "-z")
    if hashlib.sha256(index).hexdigest() != manifest["native_index_sha256"]:
        raise RuntimeError("complete native Git index differs")
    entries = [entry for entry in index.split(b"\0") if entry]
    if len(entries) != manifest["native_tracked_files"]:
        raise RuntimeError("complete native source inventory required")
    if set(manifest["native_files"]) != NATIVE_FILES:
        raise RuntimeError("native patch file inventory differs")

    def verify_tree(applied):
        content = []
        for entry in entries:
            fields, raw_name = entry.split(b"\t", 1)
            mode, oid, stage = fields.split()
            name = os.fsdecode(raw_name)
            relative = Path(name)
            if stage != b"0" or relative.is_absolute() or ".." in relative.parts:
                raise RuntimeError("invalid native index entry")
            path = root / relative
            st = path.lstat()
            if mode == b"120000":
                if not stat.S_ISLNK(st.st_mode):
                    raise RuntimeError("source symlink type differs: " + name)
                raw = os.fsencode(os.readlink(path))
            elif mode in (b"100644", b"100755"):
                if not stat.S_ISREG(st.st_mode) or bool(st.st_mode & 0o111) != (mode == b"100755"):
                    raise RuntimeError("source regular/executable mode differs: " + name)
                raw = path.read_bytes()
            else:
                raise RuntimeError("unsupported native index mode")
            digest = hashlib.sha256(raw).hexdigest()
            if applied and name in NATIVE_FILES:
                expected = manifest["native_files"][name]["after"]
                if len(raw) != expected["bytes"] or digest != expected["sha256"]:
                    raise RuntimeError("applied native identity differs: " + name)
            else:
                object_id = hashlib.sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
                if object_id != oid.decode():
                    raise RuntimeError("original Git blob differs: " + name)
            content.append([name, mode.decode(), len(raw), digest])
        if git("ls-files", "--others", "--exclude-standard", "-z"):
            raise RuntimeError("unexpected native untracked files")
        changed = {name.decode() for name in git("diff", "--name-only", "-z").split(b"\0") if name}
        if changed != (NATIVE_FILES if applied else set()):
            raise RuntimeError("unexpected native source changes")
        return hashlib.sha256(json.dumps(content, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()

    before = verify_tree(args.verify_applied)
    if not args.verify_applied:
        if git("status", "--porcelain", "--untracked-files=all"):
            raise RuntimeError("native checkout must be clean")
        for name, expected in manifest["native_files"].items():
            check_file(root / name, expected["before"])
        patch = str(packet / "native-frozen-read.patch")
        git("apply", "--check", patch)
        git("apply", patch)
    after = verify_tree(True)
    if git("ls-files", "--stage", "-z") != index:
        raise RuntimeError("native Git index was modified")
    git("diff", "--check")
    evidence = {"native_base_commit": manifest["native_base_commit"],
                "native_base_tree": manifest["native_base_tree"],
                "native_index_sha256": manifest["native_index_sha256"],
                "verified_tracked_files": len(entries),
                "changed_files": sorted(NATIVE_FILES),
                "content_before_sha256": before, "content_after_sha256": after,
                "status": "verified-after-tests" if args.verify_applied else "applied-and-verified",
                "Android_actions": 0, "runtime_qualified": False, "production_ready": False}
    with args.output.open("x") as stream:
        json.dump(evidence, stream, indent=2)
        stream.write("\n")
    print(json.dumps(evidence))


if __name__ == "__main__":
    main()
