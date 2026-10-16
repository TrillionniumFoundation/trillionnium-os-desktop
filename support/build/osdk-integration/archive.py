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
WRITE_FLAGS = os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_CREAT | os.O_EXCL


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


def write_archive_file(root_fd, relative, payload):
    """Write a selected output using only pinned directory file descriptors."""
    if (relative.is_absolute() or not relative.parts
            or any(part in ("", ".", "..") for part in relative.parts)):
        raise ValueError(f"invalid output archive path: {relative}")
    fd = os.dup(root_fd)
    try:
        for part in relative.parts[:-1]:
            try:
                os.mkdir(part, mode=0o700, dir_fd=fd)
            except FileExistsError:
                pass
            opened = os.open(part, DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = opened
        child = os.open(relative.name, WRITE_FLAGS, 0o600, dir_fd=fd)
        with os.fdopen(child, "wb") as output:
            output.write(payload)
    finally:
        os.close(fd)


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
    created = None
    destination_fd = None
    digests = []
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
            if archived.parts[0] in {"archive.json", "evidence.sha256", ".archive-incomplete"}:
                raise ValueError(f"evidence collides with archive index: {archived}")
            if archived in archived_names:
                raise ValueError(f"duplicate archive destination: {archived}")
            archived_names.add(archived)
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                raise ValueError("evidence archive exceeds total size limit")
            if created is None:
                # Delayed allocation: empty/invalid sources never create a fake bundle.
                destination.mkdir(mode=0o700, parents=True, exist_ok=False)
                destination_fd = os.open(destination, DIRECTORY_FLAGS)
                created = os.fstat(destination_fd)
                # Never publish a partial bundle as successful evidence.
                write_archive_file(destination_fd, Path(".archive-incomplete"),
                                   b"A01 evidence archive incomplete; do not consume\n")
            output_name = archived
            payload = data
            if str(archived).endswith(".log") or str(archived).endswith(".metadata.json"):
                output_name = archived.with_name(archived.name + ".gz")
                payload = gzip.compress(data, mtime=0)
            write_archive_file(destination_fd, output_name, payload)
            digests.append((str(output_name), hashlib.sha256(payload).hexdigest()))
            records.append({"source": original, "archived": str(output_name),
                            "source_size": len(data), "source_sha256": hashlib.sha256(data).hexdigest()})
        if not records:
            raise ValueError("no permitted evidence files found (archive cannot be empty)")
        manifest = (json.dumps({"schema": 1, "source": str(source),
            "excluded": sorted(EXCLUDED_DIRS), "files": records}, indent=2) + "\n").encode()
        write_archive_file(destination_fd, Path("archive.json"), manifest)
        digests.append(("archive.json", hashlib.sha256(manifest).hexdigest()))
        rows = [digest + "  " + name for name, digest in sorted(digests)]
        write_archive_file(destination_fd, Path("evidence.sha256"), ("\n".join(rows) + "\n").encode())
        # Recheck the original pathname only to refuse success on replacement.
        # All actual writes use the FD, never the possibly replaced name.
        current = destination.lstat()
        if (not stat.S_ISDIR(current.st_mode)
                or (current.st_dev, current.st_ino) != (created.st_dev, created.st_ino)):
            raise ValueError("archive output directory replaced during write")
        os.unlink(".archive-incomplete", dir_fd=destination_fd)
    except BaseException:
        # No pathname-based recursive cleanup. An atomic directory swap after
        # stat-before-rmtree could otherwise delete an unrelated directory.
        # The private partial output remains quarantined with its marker.
        raise
    finally:
        if destination_fd is not None:
            os.close(destination_fd)
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
