#!/usr/bin/env python3
"""Apply the pinned reader correction to an isolated exact native checkout."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


NATIVE_FILES = {
    "Cargo.lock",
    "runtime/droidloom-applications/Cargo.toml",
    "runtime/droidloom-applications/src/release.rs",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--native-root", type=Path, required=True)
    args = parser.parse_args()
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

    actual_files = {str(p.relative_to(packet)) for p in packet.rglob("*")
                    if p.is_file() and p.name != "source-manifest.json"}
    if actual_files != set(manifest["files"]):
        raise RuntimeError("packet file inventory differs")
    for name, expected in manifest["files"].items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise RuntimeError("invalid packet path")
        check_file(packet / relative, expected)
    if git("rev-parse", "HEAD").decode().strip() != manifest["native_base_commit"]:
        raise RuntimeError("native checkout commit differs")
    if git("rev-parse", "HEAD^{tree}").decode().strip() != manifest["native_base_tree"]:
        raise RuntimeError("native checkout tree differs")
    if git("status", "--porcelain", "--untracked-files=all"):
        raise RuntimeError("native checkout must be clean")
    if len(git("ls-files", "-z").split(b"\0")) - 1 != 2118:
        raise RuntimeError("complete native source inventory required")
    if set(manifest["native_files"]) != NATIVE_FILES:
        raise RuntimeError("native patch file inventory differs")
    for name, expected in manifest["native_files"].items():
        check_file(root / name, expected["before"])
    patch = str(packet / "native-frozen-read.patch")
    git("apply", "--check", patch)
    git("apply", patch)
    for name, expected in manifest["native_files"].items():
        check_file(root / name, expected["after"])
    changed = {name.decode() for name in git("diff", "--name-only", "-z").split(b"\0") if name}
    if changed != NATIVE_FILES or git("ls-files", "--others", "--exclude-standard", "-z"):
        raise RuntimeError("unexpected native source changes")
    git("diff", "--check")
    print(json.dumps({"native_base_commit": manifest["native_base_commit"],
                      "native_base_tree": manifest["native_base_tree"],
                      "verified_native_files": sorted(changed),
                      "status": "applied-and-verified", "Android_actions": 0}))


if __name__ == "__main__":
    main()
