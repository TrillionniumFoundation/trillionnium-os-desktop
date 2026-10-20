#!/usr/bin/env python3
"""Preserve existing generated state under the stable lock, then pin a worktree."""
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import sys

work = Path(__file__).resolve().parent / "a01-next6-build"
head = sys.argv[1]
receipt = {"schema": 1, "utc": datetime.now(timezone.utc).isoformat(), "requested_head": head}
with (work / "support/build/out-kernel.lock").open("a") as lock:
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    subprocess.run(["git", "diff", "--exit-code", "HEAD", "--"], cwd=work, check=True)
    receipt["before_head"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=work, text=True).strip()
    manifest = work / "kernel/asterinas/kernel/OSDK.toml"
    if manifest.exists() or manifest.is_symlink():
        custody = work / "support/build/out/next7-preserved-manifest"
        custody.mkdir(mode=0o700, exist_ok=False)
        destination = custody / "OSDK.toml"
        info = manifest.lstat()
        receipt["preserved_manifest"] = {
            "old_path": str(manifest), "new_path": str(destination),
            "device": info.st_dev, "inode": info.st_ino, "size": info.st_size,
            "mode": stat.S_IFMT(info.st_mode),
            "sha256": hashlib.sha256(manifest.read_bytes()).hexdigest() if stat.S_ISREG(info.st_mode) else None,
        }
        os.rename(manifest, destination)
        if (destination.lstat().st_dev, destination.lstat().st_ino) != (info.st_dev, info.st_ino):
            raise SystemExit("preserved manifest identity changed; inspect retained state")
    subprocess.run(["git", "switch", "--detach", head], cwd=work, check=True)
    receipt["after_head"] = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=work, text=True).strip()
    receipt["after_tree"] = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=work, text=True).strip()
    receipt["git_status"] = subprocess.check_output(["git", "status", "--short"], cwd=work, text=True)
    receipt["generated_manifest_absent_at_check"] = not (manifest.exists() or manifest.is_symlink())
    receipt["target_cache_retained"] = True
    source = subprocess.run([sys.executable, "-I", "support/build/verify-source.py"], cwd=work,
                            capture_output=True, text=True)
    receipt["fixed_source_verification"] = {"exit_code": source.returncode, "stdout": source.stdout, "stderr": source.stderr}
    path = Path(__file__).resolve().parent / "next7-worktree-sync.json"
    path.write_text(json.dumps(receipt, indent=2) + "\n")
    if source.returncode or receipt["after_head"] != head:
        raise SystemExit("worktree source verification failed")
    print(json.dumps(receipt, indent=2))
