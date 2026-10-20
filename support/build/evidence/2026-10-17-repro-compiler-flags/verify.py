#!/usr/bin/env python3
"""Reassemble and verify the complete frozen native mechanism evidence."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import tarfile
import tempfile


def read_regular(path):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise ValueError(f"not a private regular file: {path}")
        with os.fdopen(fd, "rb", closefd=False) as stream:
            value = stream.read()
        after = os.fstat(fd)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if tuple(getattr(before, k) for k in fields) != tuple(getattr(after, k) for k in fields):
            raise ValueError(f"input changed while reading: {path}")
        return value
    finally:
        os.close(fd)


def canonical(name):
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in ("..", ".") for part in path.parts) or str(path) != name:
        raise ValueError(f"unsafe archive path: {name}")
    return name


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def checksums(raw):
    result = {}
    for line in raw.decode().splitlines():
        digest, name = line.split("  ", 1)
        canonical(name)
        if len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest) or name in result:
            raise ValueError("invalid or duplicate checksum entry")
        result[name] = digest
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="optionally create a NEW verified tar.gz; existing paths are refused")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    outer = checksums(read_regular(root / "SHA256SUMS"))
    for name, expected in outer.items():
        if sha(read_regular(root / name)) != expected:
            raise ValueError(f"outer checksum mismatch: {name}")
    archive_info = json.loads(read_regular(root / "archive.json"))
    manifest = json.loads(read_regular(root / "member-manifest.json"))
    expected_members = manifest["members"]
    if len(expected_members) != archive_info["regular_member_count"]:
        raise ValueError("member count descriptors disagree")
    total = 0
    archive_hash = hashlib.sha256()
    with tempfile.TemporaryFile() as assembled:
        for part in archive_info["parts"]:
            raw = read_regular(root / canonical(part["path"]))
            if len(raw) != part["size"] or sha(raw) != part["sha256"] or len(raw) > 2 * 1024 * 1024:
                raise ValueError("chunk integrity or size failure")
            assembled.write(raw)
            archive_hash.update(raw)
            total += len(raw)
        if total != archive_info["compressed_size"] or archive_hash.hexdigest() != archive_info["sha256"]:
            raise ValueError("reassembled archive differs")
        assembled.seek(0)
        observed = {}
        inner_sum = None
        with tarfile.open(fileobj=assembled, mode="r|gz") as archive:
            count = 0
            for info in archive:
                if count >= len(expected_members):
                    raise ValueError("unexpected extra tar member")
                expected = expected_members[count]
                if info.name != canonical(expected["path"]) or not info.isfile() or info.size != expected["size"]:
                    raise ValueError(f"tar member type, order, name or size differs: {info.name}")
                if (info.uid, info.gid, info.mtime, info.mode, info.uname, info.gname) != (0, 0, 0, 0o644, "", ""):
                    raise ValueError("non-deterministic tar metadata")
                source = archive.extractfile(info)
                digest = hashlib.sha256()
                retained = bytearray() if info.name == "SHA256SUMS" else None
                read = 0
                while True:
                    data = source.read(65536)
                    if not data:
                        break
                    read += len(data)
                    digest.update(data)
                    if retained is not None:
                        retained.extend(data)
                if read != expected["size"] or digest.hexdigest() != expected["sha256"]:
                    raise ValueError(f"tar payload mismatch: {info.name}")
                observed[info.name] = digest.hexdigest()
                if retained is not None:
                    inner_sum = bytes(retained)
                count += 1
        if count != len(expected_members) or len(observed) != count or inner_sum is None:
            raise ValueError("incomplete or duplicate archive members")
        declared = checksums(inner_sum)
        if set(declared) != set(observed) - {"SHA256SUMS"}:
            raise ValueError("frozen inner checksum coverage differs")
        if any(observed[name] != digest for name, digest in declared.items()):
            raise ValueError("frozen inner checksum mismatch")
        if sha(inner_sum) != archive_info["inner_sha256sums_sha256"]:
            raise ValueError("inner checksum file differs from frozen source")
        if args.output:
            fd = os.open(args.output, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
            with os.fdopen(fd, "wb") as destination:
                assembled.seek(0)
                shutil.copyfileobj(assembled, destination, 65536)
        print(json.dumps({"verified": True, "outer_entries": len(outer),
                          "regular_members": count, "inner_entries": len(declared),
                          "archive_sha256": archive_hash.hexdigest(), "compressed_size": total,
                          "output_created": str(args.output) if args.output else None}, sort_keys=True))


if __name__ == "__main__":
    main()
