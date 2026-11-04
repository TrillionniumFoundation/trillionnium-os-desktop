#!/usr/bin/env python3
"""Verify the two public source layers in a temporary copy; never mutate input."""
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import tempfile

HERE = Path(__file__).resolve().parents[1]

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def checked_relative(value):
    p = PurePosixPath(value)
    if p.is_absolute() or ".." in p.parts:
        raise ValueError("unsafe source path")
    return p

def verify_tree(root, files, field):
    for name, pin in files.items():
        path = root / checked_relative(name)
        wanted = pin[field]
        if wanted is None:
            if path.exists():
                raise ValueError("unexpected upstream input: " + name)
        elif not path.is_file() or path.is_symlink() or digest(path) != wanted:
            raise ValueError("source mismatch: " + name)

def verify(upstream):
    lock = json.loads((HERE / "source-lock.json").read_text())
    upstream = upstream.resolve(strict=True)
    head = subprocess.run(["git", "-C", str(upstream), "rev-parse", "HEAD"],
                          check=True, capture_output=True, text=True).stdout.strip()
    if head != lock["upstream_commit"]:
        raise ValueError("wrong upstream commit")
    files = lock["files"]
    verify_tree(upstream, files, "upstream_sha256")
    with tempfile.TemporaryDirectory(prefix="pocket4-presenter-series-") as td:
        work = Path(td)
        for name, pin in files.items():
            if pin["upstream_sha256"] is None:
                continue
            dest = work / checked_relative(name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(upstream / name, dest)
        for layer, field in zip(lock["source_layers"],
                                ("inherited_sha256", "candidate_sha256"), strict=True):
            patch = HERE / checked_relative(layer["patch"])
            if digest(patch) != layer["sha256"]:
                raise ValueError("patch hash changed")
            subprocess.run(["git", "apply", "--check", str(patch)], cwd=work, check=True)
            subprocess.run(["git", "apply", "--whitespace=nowarn", str(patch)],
                           cwd=work, check=True)
            verify_tree(work, files, field)
        for name, pin in files.items():
            os.chmod(work / name, int(pin["mode"], 8))
        supplied = 0
        for source in (HERE / "source").rglob("*"):
            if source.is_file():
                name = source.relative_to(HERE / "source").as_posix()
                if name not in files or digest(source) != files[name]["candidate_sha256"]:
                    raise ValueError("delivered source mismatch: " + name)
                supplied += 1
        frozen = json.loads((HERE / "source-manifest.json").read_text())
        if set(frozen) != set(files) or any(
            frozen[n]["sha256"] != files[n]["candidate_sha256"] for n in files
        ):
            raise ValueError("frozen public source manifest mismatch")
    return {"ok": True, "upstream_commit": head,
            "public_files_verified_at_each_stage": len(files),
            "inherited_changed_public_files": len(lock["source_layers"][0]["changed_paths"]),
            "timing_changed_files": len(lock["source_layers"][1]["changed_paths"]),
            "delivered_final_source_files_verified": supplied,
            "excluded_private_provenance_not_required": True,
            "upstream_checkout_mutated": False, "runtime_mutated": False}

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream", type=Path, required=True)
    print(json.dumps(verify(parser.parse_args().upstream), indent=2))

