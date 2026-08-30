#!/usr/bin/env python3
"""Emit a canonical manifest for every D1 rootfs object and xattr."""

from __future__ import annotations

import argparse
import base64
import errno
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path
from typing import Any

CHUNK_BYTES = 1024 * 1024
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _has_symlink_component(path: Path) -> bool:
    """Return whether *path* traverses a symlink without resolving it first.

    ``Path.resolve()`` must not be used as the initial check: it erases the
    final symlink (and any symlink parent) before callers can reject it.  Walk
    the lexical path with ``lstat`` instead.  Missing trailing components are
    allowed because output paths are created by this tool.
    """

    lexical = path if path.is_absolute() else Path.cwd() / path
    current = Path(lexical.anchor)
    for component in lexical.parts:
        if component in {lexical.anchor, "", "."}:
            continue
        if component == "..":
            current = current.parent
            continue
        current /= component
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            return False
        except OSError as error:
            raise ValueError(f"cannot inspect path component: {current}") from error
        if stat.S_ISLNK(mode):
            return True
    return False


def _open_regular(path: Path, label: str) -> int:
    """Open a regular rootfs input without following a final symlink."""

    if _has_symlink_component(path):
        raise ValueError(f"{label} path contains a symlink: {path}")
    try:
        descriptor = os.open(
            path,
            os.O_RDONLY | _O_CLOEXEC | _O_NONBLOCK | _O_NOFOLLOW,
        )
    except OSError as error:
        if error.errno == errno.ENOENT:
            raise FileNotFoundError(f"{label} is absent: {path}") from error
        raise ValueError(f"{label} is absent or unreadable: {path}") from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f"{label} is not a regular file: {path}")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    descriptor = _open_regular(path, "rootfs file")
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            for chunk in iter(lambda: stream.read(CHUNK_BYTES), b""):
                digest.update(chunk)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    return digest.hexdigest()


def _write_text_atomic(path: Path, text: str) -> None:
    """Publish a generated manifest without following a destination link."""

    if _has_symlink_component(path.parent):
        raise ValueError(f"manifest parent contains a symlink: {path.parent}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if _has_symlink_component(path.parent) or path.is_symlink():
        raise ValueError(f"manifest output path contains a symlink: {path}")
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=True) as stream:
            descriptor = -1
            stream.write(text)
            stream.flush()
            try:
                os.fsync(stream.fileno())
            except OSError:
                pass
        if _has_symlink_component(path) or path.is_symlink():
            raise ValueError(f"manifest output path became a symlink: {path}")
        os.replace(temporary, path)
        temporary = None
    finally:
        if descriptor >= 0:
            os.close(descriptor)
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass


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

    if _has_symlink_component(args.root):
        raise SystemExit(f"rootfs path contains a symlink: {args.root}")
    root = args.root.absolute()
    if not root.is_dir():
        raise SystemExit(f"rootfs is missing or unsafe: {root}")
    if _has_symlink_component(args.output):
        raise SystemExit(f"manifest output path contains a symlink: {args.output}")
    output = args.output.absolute()
    manifest = build_manifest(root)
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_text_atomic(
        output,
        json.dumps(manifest, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
