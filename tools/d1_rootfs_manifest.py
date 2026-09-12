#!/usr/bin/env python3
"""Emit a canonical manifest for every D1 rootfs object and xattr."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import stat
from pathlib import Path
from typing import Any

CHUNK_BYTES = 1024 * 1024


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK_BYTES), b""):
            digest.update(chunk)
    return digest.hexdigest()


def object_type(mode: int) -> str:
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISCHR(mode):
        return "character_device"
    if stat.S_ISBLK(mode):
        return "block_device"
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISSOCK(mode):
        return "socket"
    return "unknown"


def xattrs(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    try:
        names = os.listxattr(path, follow_symlinks=False)
    except OSError as error:
        raise RuntimeError(f"cannot list xattrs for {path}: {error}") from error
    for name in sorted(names, key=os.fsencode):
        try:
            value = os.getxattr(path, name, follow_symlinks=False)
        except OSError as error:
            raise RuntimeError(f"cannot read xattr {name!r} for {path}: {error}") from error
        values[name] = base64.b64encode(value).decode("ascii")
    return values


def iter_paths(root: Path) -> list[Path]:
    paths = [root]
    for directory, names, files in os.walk(root, topdown=True, followlinks=False):
        names.sort(key=os.fsencode)
        files.sort(key=os.fsencode)
        base = Path(directory)
        paths.extend(base / name for name in names)
        paths.extend(base / name for name in files)
    return paths


def relative_name(root: Path, path: Path) -> str:
    if path == root:
        return "."
    return "./" + path.relative_to(root).as_posix()


def build_manifest(root: Path) -> dict[str, Any]:
    paths = iter_paths(root)
    inode_members: dict[tuple[int, int], list[str]] = {}
    stats: dict[Path, os.stat_result] = {}
    for path in paths:
        info = path.lstat()
        stats[path] = info
        if stat.S_ISREG(info.st_mode) and info.st_nlink > 1:
            inode_members.setdefault((info.st_dev, info.st_ino), []).append(
                relative_name(root, path)
            )
    hardlink_heads = {
        key: sorted(members, key=os.fsencode)[0]
        for key, members in inode_members.items()
    }

    entries: list[dict[str, Any]] = []
    for path in sorted(paths, key=lambda item: os.fsencode(relative_name(root, item))):
        info = stats[path]
        kind = object_type(info.st_mode)
        entry: dict[str, Any] = {
            "path": relative_name(root, path),
            "type": kind,
            "mode": format(stat.S_IMODE(info.st_mode), "04o"),
            "uid": info.st_uid,
            "gid": info.st_gid,
            "size": info.st_size,
            "nlink": info.st_nlink,
            "mtime_ns": info.st_mtime_ns,
            "xattrs": xattrs(path),
        }
        if kind == "file":
            entry["sha256"] = sha256_file(path)
            if info.st_nlink > 1:
                head = hardlink_heads[(info.st_dev, info.st_ino)]
                entry["hardlink_head"] = head
        elif kind == "symlink":
            entry["target"] = os.readlink(path)
        elif kind in {"character_device", "block_device"}:
            entry["device_major"] = os.major(info.st_rdev)
            entry["device_minor"] = os.minor(info.st_rdev)
        entries.append(entry)

    canonical_entries = json.dumps(
        entries,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {
        "schema": "trillionnium.desktop.d1-rootfs-manifest.v1",
        "entry_count": len(entries),
        "entries_sha256": hashlib.sha256(canonical_entries).hexdigest(),
        "entries": entries,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    root = args.root.resolve()
    if not root.is_dir() or root.is_symlink():
        raise SystemExit(f"rootfs is missing or unsafe: {root}")
    manifest = build_manifest(root)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
