#!/usr/bin/env python3
"""Read-only Git/worktree input receipt for the A01 complete-kernel build."""
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

PIN_COMMIT = "c4b7ed575b7b32773475b194d2ad41fb6d03765b"
PIN_TREE = "96605cf64aeae2d34f29b97e85eff9315fe10a8e"
EXCLUDED = ("support/build/evidence/", "support/build/out/", "support/build/handoffs/")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--compare", type=Path)
    args = parser.parse_args()
    repo = args.repo.resolve()

    def git(*parts):
        return subprocess.check_output(["git", "-C", str(repo), *parts])

    def selected(name):
        return (name in ("README.md", "support/upstream-lock.json")
                or name.startswith(("kernel/asterinas/", "libs/os-abi/src/"))
                or name.startswith("support/build/") and not name.startswith(EXCLUDED))

    head = git("rev-parse", "HEAD").decode().strip()
    entries = []
    failures = []
    for raw_entry in git("ls-tree", "-rz", head).split(b"\0"):
        if not raw_entry:
            continue
        metadata, raw_name = raw_entry.split(b"\t", 1)
        name = os.fsdecode(raw_name)
        if not selected(name):
            continue
        mode, kind, expected = metadata.decode().split()
        entry = {"path": name, "git_mode": mode, "git_kind": kind, "git_blob": expected}
        path = repo / name
        try:
            before = path.lstat()
            if stat.S_ISLNK(before.st_mode):
                actual_mode, raw = "120000", os.fsencode(os.readlink(path))
            elif stat.S_ISREG(before.st_mode):
                actual_mode = "100755" if before.st_mode & 0o111 else "100644"
                with path.open("rb") as source:
                    opened = os.fstat(source.fileno())
                    raw = source.read()
                    finished = os.fstat(source.fileno())
                fields = lambda info: (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)
                if not fields(before) == fields(opened) == fields(finished):
                    raise ValueError("source changed during read")
            else:
                raise ValueError("source is not a regular file or Git symlink")
            after = path.lstat()
            if (before.st_dev, before.st_ino, before.st_mtime_ns, before.st_ctime_ns) != (after.st_dev, after.st_ino, after.st_mtime_ns, after.st_ctime_ns):
                raise ValueError("source pathname changed during capture")
            actual_blob = hashlib.sha1(f"blob {len(raw)}\0".encode() + raw).hexdigest()
            entry.update(worktree_mode=actual_mode, size=len(raw), sha256=hashlib.sha256(raw).hexdigest(),
                         worktree_git_blob=actual_blob, matches_git=kind == "blob" and mode == actual_mode and expected == actual_blob)
            if not entry["matches_git"]:
                failures.append(name + ": worktree bytes/mode differ from committed Git object")
        except (OSError, ValueError) as error:
            entry.update(matches_git=False, error=str(error))
            failures.append(name + ": " + str(error))
        entries.append(entry)
    entries.sort(key=lambda item: os.fsencode(item["path"]))
    staged_paths = {os.fsdecode(item) for item in git("ls-files", "-z").split(b"\0") if item}
    extra_tracked = sorted(name for name in staged_paths if selected(name) and name not in {entry["path"] for entry in entries})
    if extra_tracked:
        failures.append("selected index-only files absent from HEAD: " + repr(extra_tracked))
    observed_pin_tree = git("rev-parse", PIN_COMMIT + "^{tree}").decode().strip()
    if observed_pin_tree != PIN_TREE:
        failures.append("fixed upstream commit/tree mismatch")
    if git("rev-parse", "HEAD").decode().strip() != head:
        failures.append("HEAD changed during capture")
    payload = json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()
    report = {"schema": "trillionnium.a01.source-capture.v1", "captured_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
              "repository": str(repo), "head": head, "project_tree": git("rev-parse", head + "^{tree}").decode().strip(),
              "kernel_tree": git("rev-parse", head + ":kernel/asterinas").decode().strip(),
              "upstream_commit": PIN_COMMIT, "upstream_tree": observed_pin_tree,
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "selection": {"prefixes": ["kernel/asterinas/", "libs/os-abi/src/", "support/build/"], "excluded_prefixes": list(EXCLUDED),
                            "explicit_paths": ["README.md", "support/upstream-lock.json"], "source": "HEAD recursive Git tree; also reject selected index-only additions"},
              "git_status_porcelain": git("status", "--porcelain=v1", "--untracked-files=all").decode(),
              "file_count": len(entries), "files_sha256": hashlib.sha256(payload).hexdigest(), "files": entries,
              "extra_tracked_paths": extra_tracked, "failures": failures, "matches_git": not failures}
    if args.compare:
        previous = json.loads(args.compare.read_text())
        identities = ("head", "project_tree", "kernel_tree", "upstream_commit", "upstream_tree", "script_sha256", "selection", "files_sha256", "file_count")
        differences = [key for key in identities if previous.get(key) != report.get(key)]
        report["comparison"] = {"reference": str(args.compare.resolve()), "changed_identity_fields": differences,
                                "passed": previous.get("matches_git") is True and not failures and not differences}
    print(json.dumps(report, indent=2))
    return 0 if not failures and (not args.compare or report["comparison"]["passed"]) else 1


if __name__ == "__main__":
    sys.exit(main())
