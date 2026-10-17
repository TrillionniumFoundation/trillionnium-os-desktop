#!/usr/bin/env python3
"""Archive A01 OSDK test evidence without following source links or device files.

This archival helper is host-only. It never proves a kernel or QEMU test passed.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat

EXCLUDED_DIRS = frozenset({"target", "harness", "work", "tmp", "bin", "fixed-tmp", "__pycache__"})
SUFFIXES = frozenset({".log", ".json", ".patch", ".txt", ".lock", ".profraw", ".profdata", ".gdb"})
MAX_FILE_BYTES = 128 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
OPEN_FLAGS = os.O_RDONLY | os.O_CLOEXEC | os.O_NONBLOCK | os.O_NOFOLLOW
DIRECTORY_FLAGS = OPEN_FLAGS | os.O_DIRECTORY
INCOMPLETE = ".archive-incomplete"


def identity(info):
    return info.st_dev, info.st_ino


def file_identity(info):
    return (info.st_dev, info.st_ino, info.st_mode, info.st_nlink,
            info.st_size, info.st_mtime_ns, info.st_ctime_ns)


class ArchiveOutput:
    """Keep writes and failure custody on opened directories, never path cleanup."""

    def __init__(self, destination):
        self.descriptors, self.links, self.files, self.digests = [], [], [], {}
        self.directories = {}
        try:
            parent = os.open(destination.anchor, DIRECTORY_FLAGS)
            self.descriptors.append(parent)
            for name in destination.parts[1:-1]:
                try:
                    os.mkdir(name, mode=0o700, dir_fd=parent)
                except FileExistsError:
                    pass
                child = os.open(name, DIRECTORY_FLAGS, dir_fd=parent)
                self.descriptors.append(child)
                self.links.append((parent, name, child))
                parent = child
            os.mkdir(destination.name, mode=0o700, dir_fd=parent)
            created = os.stat(destination.name, dir_fd=parent, follow_symlinks=False)
            self.root_fd = os.open(destination.name, DIRECTORY_FLAGS, dir_fd=parent)
            self.descriptors.append(self.root_fd)
            self.links.append((parent, destination.name, self.root_fd))
            if identity(created) != identity(os.fstat(self.root_fd)):
                raise ValueError("archive destination changed during open")
            self.directories[()] = self.root_fd
            self.write(Path(INCOMPLETE), b"Archive incomplete; success requires this marker to be absent.\n",
                       indexed=False)
        except BaseException:
            self.close()
            raise

    def directory(self, parts):
        current = self.root_fd
        for index, name in enumerate(parts):
            key = parts[:index + 1]
            child = self.directories.get(key)
            if child is None:
                try:
                    os.mkdir(name, mode=0o700, dir_fd=current)
                except FileExistsError:
                    pass
                child = os.open(name, DIRECTORY_FLAGS, dir_fd=current)
                self.descriptors.append(child)
                self.links.append((current, name, child))
                self.directories[key] = child
            if identity(os.stat(name, dir_fd=current, follow_symlinks=False)) != identity(os.fstat(child)):
                raise ValueError("archive destination directory changed")
            current = child
        return current

    def write(self, relative, payload, indexed=True):
        if relative.is_absolute() or not relative.parts or any(part in {".", ".."} for part in relative.parts):
            raise ValueError(f"invalid archive output path: {relative}")
        parent = self.directory(relative.parts[:-1])
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW
        descriptor = os.open(relative.name, flags, mode=0o600, dir_fd=parent)
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(payload)
            stream.flush()
            captured = os.fstat(stream.fileno())
            if not stat.S_ISREG(captured.st_mode) or captured.st_nlink != 1 or captured.st_size != len(payload):
                raise ValueError(f"archive output changed during write: {relative}")
        self.files.append((parent, relative.name, file_identity(captured)))
        if indexed:
            self.digests[relative.as_posix()] = hashlib.sha256(payload).hexdigest()

    def finish(self):
        for parent, name, child in self.links:
            if identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != identity(os.fstat(child)):
                raise ValueError("archive destination directory changed before completion")
        for parent, name, expected in self.files:
            if file_identity(os.stat(name, dir_fd=parent, follow_symlinks=False)) != expected:
                raise ValueError(f"archive output changed before completion: {name}")
        os.unlink(INCOMPLETE, dir_fd=self.root_fd)

    def close(self):
        for descriptor in reversed(self.descriptors):
            os.close(descriptor)
        self.descriptors.clear()


def read_regular(directory_fd, name):
    """Bound a single openat() read to its lstat() identity; never follow links."""
    before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"evidence source is not a regular file: {name}")
    if before.st_nlink != 1:
        raise ValueError(f"hard-linked evidence source is not isolated: {name}")
    if before.st_size > MAX_FILE_BYTES:
        raise ValueError(f"evidence source is too large: {name}")
    descriptor = os.open(name, OPEN_FLAGS, dir_fd=directory_fd)
    with os.fdopen(descriptor, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (not stat.S_ISREG(opened.st_mode)
                or opened.st_nlink != 1
                or (opened.st_dev, opened.st_ino, opened.st_size,
                    opened.st_mtime_ns, opened.st_ctime_ns)
                != (before.st_dev, before.st_ino, before.st_size,
                    before.st_mtime_ns, before.st_ctime_ns)):
            raise ValueError(f"evidence source changed during open: {name}")
        data = stream.read(MAX_FILE_BYTES + 1)
        final = os.fstat(stream.fileno())
    if (final.st_nlink != 1 or len(data) > MAX_FILE_BYTES or len(data) != opened.st_size
            or opened.st_size != final.st_size or opened.st_mtime_ns != final.st_mtime_ns
            or opened.st_ctime_ns != final.st_ctime_ns):
        raise ValueError(f"evidence source grew, shrank or changed during read: {name}")
    return data


def source_files(root_fd):
    """Walk the opened root inode without following links; include two fixed extras."""
    for root, dirs, files, fd in os.fwalk(
            ".", dir_fd=root_fd, topdown=True, follow_symlinks=False):
        relative_root = Path(root)
        retained = []
        for name in sorted(dirs):
            if name in EXCLUDED_DIRS:
                continue
            mode = os.stat(name, dir_fd=fd, follow_symlinks=False).st_mode
            if not stat.S_ISDIR(mode):
                raise ValueError(f"directory symlink or special entry rejected: {relative_root / name}")
            retained.append(name)
        dirs[:] = retained
        for name in sorted(files):
            path = relative_root / name
            if path.suffix in SUFFIXES:
                yield path, read_regular(fd, name)
    for candidate, archived in (("harness/Cargo.lock", "harness.Cargo.lock"),
                                ("rust-toolchain.toml", "rust-toolchain.toml")):
        parts = Path(candidate).parts
        if len(parts) == 1:
            try:
                payload = read_regular(root_fd, parts[0])
            except FileNotFoundError:
                continue
        else:
            try:
                child = os.open(parts[0], DIRECTORY_FLAGS, dir_fd=root_fd)
            except FileNotFoundError:
                continue
            try:
                try:
                    payload = read_regular(child, parts[1])
                except FileNotFoundError:
                    continue
            finally:
                os.close(child)
        yield Path(archived), payload, candidate


def archive(source, destination):
    source = Path(source).absolute()
    destination = Path(destination).absolute()
    try:
        source_identity = source.lstat()
    except FileNotFoundError as error:
        raise ValueError("archive source must be an existing, non-symlink directory") from error
    if not stat.S_ISDIR(source_identity.st_mode):
        raise ValueError("archive source must be an existing, non-symlink directory")
    source = source.resolve()
    canonical_destination = destination.resolve(strict=False)
    if canonical_destination == source or canonical_destination.is_relative_to(source):
        raise ValueError("archive destination must be outside the source tree")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError(f"archive destination exists: {destination}")

    root_fd = os.open(source, DIRECTORY_FLAGS)
    records = []
    total = 0
    archived_names = set()
    output = None
    try:
        opened_root = os.fstat(root_fd)
        if (opened_root.st_dev, opened_root.st_ino) != (source_identity.st_dev,
                                                       source_identity.st_ino):
            raise ValueError("archive source directory changed during open")
        for item in source_files(root_fd):
            if len(item) == 3:
                archived, data, original = item
            else:
                archived, data = item
                original = str(archived)
            if archived.is_absolute() or not archived.parts or ".." in archived.parts:
                raise ValueError(f"invalid archive evidence path: {archived}")
            if archived.parts[0] in {"archive.json", "evidence.sha256", INCOMPLETE}:
                raise ValueError(f"evidence collides with archive index: {archived}")
            if archived in archived_names:
                raise ValueError(f"duplicate archive destination: {archived}")
            archived_names.add(archived)
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                raise ValueError("evidence archive exceeds total size limit")
            if output is None:
                # Delayed allocation: empty/invalid sources never create a fake bundle.
                output = ArchiveOutput(destination)
            target = archived
            if str(archived).endswith(".log") or str(archived).endswith(".metadata.json"):
                target = target.with_name(target.name + ".gz")
                payload = gzip.compress(data, mtime=0)
            else:
                payload = data
            output.write(target, payload)
            records.append({"source": original, "archived": str(target),
                            "source_size": len(data), "source_sha256": hashlib.sha256(data).hexdigest()})
        if not records:
            raise ValueError("no permitted evidence files found (archive cannot be empty)")
        output.write(Path("archive.json"), (json.dumps({"schema": 1, "source": str(source),
            "excluded": sorted(EXCLUDED_DIRS), "files": records}, indent=2) + "\n").encode())
        rows = [digest + "  " + name for name, digest in sorted(output.digests.items())]
        output.write(Path("evidence.sha256"), ("\n".join(rows) + "\n").encode())
        output.finish()
    finally:
        # A failed new archive retains its opened custody and incomplete marker.
        # Never recursively delete a pathname that another writer can replace.
        if output is not None:
            output.close()
        os.close(root_fd)
    return len(records)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path, help="must not already exist")
    args = parser.parse_args()
    count = archive(args.source, args.destination)
    print(f"archived {count} evidence files to {args.destination}")


if __name__ == "__main__":
    main()
