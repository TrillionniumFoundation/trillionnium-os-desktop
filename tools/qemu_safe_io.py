#!/usr/bin/env python3
"""Descriptor-backed I/O helpers for the D1/D2I QEMU shell gates.

The QEMU gates run on runner-controlled output directories, but their
artifacts are later treated as machine evidence.  Keep the small set of
pathname writes in one dependency-free module so a pre-seeded symlink, FIFO,
or a late final-component replacement cannot redirect a result or make a
qualification command block indefinitely.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
from typing import Iterable, Sequence


_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)


class UnsafePathError(RuntimeError):
    """Raised when an artifact path is not a regular, link-free path."""


def has_symlink_component(path: Path) -> bool:
    """Return whether an existing lexical component of *path* is a symlink."""

    path = Path(os.fspath(path))
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
            if stat.S_ISLNK(os.lstat(current).st_mode):
                return True
        except FileNotFoundError:
            # Missing trailing components are valid for generated outputs.
            return False
        except OSError as error:
            raise UnsafePathError(f"cannot inspect path component: {current}") from error
    return False


def _require_parent(path: Path, label: str) -> Path:
    """Validate/create a real parent directory without following links."""

    path = Path(os.fspath(path))
    if has_symlink_component(path.parent):
        raise UnsafePathError(f"{label} parent contains a symlink: {path.parent}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if has_symlink_component(path.parent):
        raise UnsafePathError(f"{label} parent contains a symlink: {path.parent}")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise UnsafePathError(f"{label} parent is not a real directory: {path.parent}")
    return path


def open_regular(
    path: Path,
    label: str,
    *,
    writable: bool = False,
    truncate: bool = False,
) -> int:
    """Open one regular file with no-follow and non-blocking safeguards."""

    path = Path(os.fspath(path))
    if has_symlink_component(path):
        raise UnsafePathError(f"{label} contains a symlink: {path}")
    if writable:
        _require_parent(path, label)
        flags = os.O_WRONLY | os.O_CREAT
        if truncate:
            flags |= os.O_TRUNC
        mode = 0o644
    else:
        flags = os.O_RDONLY
        mode = 0
    flags |= _O_CLOEXEC | _O_NOFOLLOW | _O_NONBLOCK
    try:
        descriptor = os.open(path, flags, mode) if writable else os.open(path, flags)
    except OSError as error:
        raise UnsafePathError(f"{label} is absent or unsafe: {path}") from error
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise UnsafePathError(f"{label} is not a regular file: {path}")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def read_bytes(path: Path, label: str = "QEMU artifact") -> bytes:
    """Read a regular file through an O_NOFOLLOW descriptor."""

    descriptor = open_regular(path, label)
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            return stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def safe_truncate(path: Path, label: str = "QEMU log") -> None:
    """Create/truncate one regular file without following a final symlink."""

    descriptor = open_regular(path, label, writable=True, truncate=True)
    os.close(descriptor)


def truncate_tail(
    path: Path,
    max_bytes: int,
    label: str = "QEMU log",
) -> None:
    """Retain at most the last *max_bytes* of a regular file atomically.

    The source is held open while the bounded tail is read, then published via
    the same descriptor-safe temporary-file/rename path used by ``write``.
    This avoids shell redirection and ``mv`` races when diagnostic files are
    staged in an untrusted output directory.
    """

    if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
        raise ValueError("tail byte limit must be an integer")
    if max_bytes < 0:
        raise ValueError("tail byte limit must be non-negative")

    descriptor = open_regular(path, label)
    try:
        size = os.fstat(descriptor).st_size
        if size <= max_bytes:
            return
        offset = size - max_bytes
        os.lseek(descriptor, offset, os.SEEK_SET)
        remaining = max_bytes
        payload = bytearray()
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                raise OSError(f"short read while retaining tail of {path}")
            payload.extend(chunk)
            remaining -= len(chunk)
    finally:
        os.close(descriptor)

    _atomic_write(path, bytes(payload), label)


def _atomic_write(path: Path, payload: bytes, label: str) -> None:
    """Publish bytes by same-directory exclusive temporary file + rename."""

    path = _require_parent(Path(os.fspath(path)), label)
    if has_symlink_component(path):
        raise UnsafePathError(f"{label} destination contains a symlink: {path}")
    descriptor: int | None = None
    temporary_path: Path | None = None
    try:
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=path.parent
        )
        temporary_path = Path(temporary_name)
        if has_symlink_component(temporary_path):
            raise UnsafePathError(f"{label} temporary path contains a symlink")
        with os.fdopen(descriptor, "wb", closefd=True) as stream:
            descriptor = None
            stream.write(payload)
            stream.flush()
            try:
                os.fsync(stream.fileno())
            except OSError:
                # Atomic publication remains useful on filesystems without
                # fsync support (for example, some ephemeral CI mounts).
                pass
        if has_symlink_component(path):
            raise UnsafePathError(f"{label} destination contains a symlink: {path}")
        # os.replace swaps the directory entry and never follows a final link.
        os.replace(temporary_path, path)
        temporary_path = None
        if has_symlink_component(path):
            raise UnsafePathError(f"{label} destination became a symlink: {path}")
    finally:
        if descriptor is not None:
            os.close(descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def write_bytes(path: Path, payload: bytes, label: str = "QEMU artifact") -> None:
    """Atomically write bytes without following a pre-seeded output link."""

    _atomic_write(path, payload, label)


def write_text(path: Path, text: str, label: str = "QEMU artifact") -> None:
    """Atomically write UTF-8 text without following output links."""

    write_bytes(path, text.encode("utf-8"), label)


def copy_regular(
    source: Path,
    destination: Path,
    label: str = "QEMU artifact",
    *,
    sparse: bool = False,
) -> None:
    """Copy one regular file through descriptor reads and atomic publication.

    ``sparse`` keeps the image-copy behaviour of the original shell gates.
    The source is still opened first and passed as ``/proc/self/fd/N`` so a
    late pathname swap cannot change which inode ``cp`` reads.
    """

    # Hold the source descriptor for the whole copy so a late source swap
    # cannot change which bytes are digest-bound or published.
    source_descriptor = open_regular(source, f"{label} source")
    try:
        destination = _require_parent(
            Path(os.fspath(destination)), f"{label} destination"
        )
        if has_symlink_component(destination):
            raise UnsafePathError(
                f"{label} destination contains a symlink: {destination}"
            )
    except BaseException:
        os.close(source_descriptor)
        raise

    target_descriptor: int | None = None
    temporary_path: Path | None = None
    try:
        target_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
        )
        temporary_path = Path(temporary_name)
        if sparse:
            # Keep the source descriptor alive and inherited by cp.  Reading
            # through /proc/self/fd preserves sparse ext4 image holes without
            # reopening the mutable source pathname.
            os.close(target_descriptor)
            target_descriptor = None
            subprocess.run(
                [
                    "cp",
                    "--sparse=always",
                    "--",
                    f"/proc/self/fd/{source_descriptor}",
                    os.fspath(temporary_path),
                ],
                check=True,
                pass_fds=(source_descriptor,),
            )
        else:
            with os.fdopen(source_descriptor, "rb", closefd=True) as source_stream:
                source_descriptor = -1
                with os.fdopen(target_descriptor, "wb", closefd=True) as target_stream:
                    target_descriptor = None
                    while True:
                        chunk = source_stream.read(1024 * 1024)
                        if not chunk:
                            break
                        target_stream.write(chunk)
                    target_stream.flush()
                    try:
                        os.fsync(target_stream.fileno())
                    except OSError:
                        pass
        if has_symlink_component(destination):
            raise UnsafePathError(
                f"{label} destination contains a symlink: {destination}"
            )
        os.replace(temporary_path, destination)
        temporary_path = None
        if has_symlink_component(destination):
            raise UnsafePathError(f"{label} destination became a symlink: {destination}")
    finally:
        if source_descriptor >= 0:
            os.close(source_descriptor)
        if target_descriptor is not None:
            os.close(target_descriptor)
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError:
                pass


def run_logged(log_path: Path, command: Sequence[str], label: str = "QEMU stage") -> int:
    """Run *command* with stdout/stderr captured to a safe regular log."""

    if not command:
        raise ValueError("logged command is empty")
    descriptor = open_regular(log_path, f"{label} log", writable=True, truncate=True)
    status = 1
    try:
        completed = subprocess.run(
            list(command), stdout=descriptor, stderr=subprocess.STDOUT, check=False
        )
        status = completed.returncode
    finally:
        os.close(descriptor)
    if status < 0:
        return 128 + (-status)
    return status


def _cli() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="operation", required=True)

    truncate = subparsers.add_parser("truncate", help="create/truncate a log")
    truncate.add_argument("--path", required=True, type=Path)

    tail = subparsers.add_parser(
        "tail", help="atomically retain a bounded file tail"
    )
    tail.add_argument("--path", required=True, type=Path)
    tail.add_argument("--max-bytes", required=True, type=int)

    copy = subparsers.add_parser("copy", help="copy one regular artifact")
    copy.add_argument("--source", required=True, type=Path)
    copy.add_argument("--destination", required=True, type=Path)
    copy.add_argument(
        "--sparse",
        action="store_true",
        help="preserve sparse holes (for disk images)",
    )

    write = subparsers.add_parser("write", help="atomically write stdin bytes")
    write.add_argument("--path", required=True, type=Path)

    run = subparsers.add_parser("run", help="run a command with a safe log")
    run.add_argument("--log", required=True, type=Path)
    run.add_argument("command", nargs=argparse.REMAINDER)
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _cli().parse_args(list(argv) if argv is not None else None)
    try:
        if args.operation == "truncate":
            safe_truncate(args.path)
            return 0
        if args.operation == "tail":
            truncate_tail(args.path, args.max_bytes)
            return 0
        if args.operation == "copy":
            copy_regular(args.source, args.destination, sparse=args.sparse)
            return 0
        if args.operation == "write":
            write_bytes(args.path, sys.stdin.buffer.read())
            return 0
        if args.operation == "run":
            command = list(args.command)
            if command[:1] == ["--"]:
                command = command[1:]
            return run_logged(args.log, command)
    except (OSError, UnsafePathError, ValueError) as error:
        print(f"safe QEMU I/O failed: {error}", file=sys.stderr)
        return 1
    raise AssertionError(f"unknown operation: {args.operation}")


if __name__ == "__main__":
    raise SystemExit(main())
