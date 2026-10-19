#!/usr/bin/env python3
"""Verify exact archive parts and optionally restore the original archive bytes."""

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path, PurePosixPath


def safe_path(root, relative):
    path = PurePosixPath(relative)
    if path.is_absolute() or ".." in path.parts or str(path) != relative:
        raise ValueError(f"Unsafe relative path: {relative}")
    result = root.joinpath(*path.parts)
    if not result.resolve().is_relative_to(root.resolve()):
        raise ValueError(f"Path escapes root: {relative}")
    return result


def identity(path):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Expected regular file: {path}")
    hasher = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        while block := stream.read(1024 * 1024):
            size += len(block)
            hasher.update(block)
    return size, hasher.hexdigest()


def restore(root, output_root, record, verify_only):
    target = safe_path(output_root, record["path"])
    parts = record["parts"]
    assert [part["index"] for part in parts] == list(range(len(parts)))
    assert len({part["path"] for part in parts}) == len(parts)
    assert sum(part["bytes"] for part in parts) == record["bytes"]
    expected = record["bytes"], record["sha256"]
    already_present = target.exists()
    if already_present:
        assert identity(target) == expected, str(target)
    temporary = None
    stream = None
    if not already_present and not verify_only:
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, name = tempfile.mkstemp(prefix=".r10-archive-", dir=target.parent)
        temporary = Path(name)
        stream = os.fdopen(descriptor, "wb")
    hasher = hashlib.sha256()
    size = 0
    try:
        for part in parts:
            source = safe_path(root, part["path"])
            assert identity(source) == (part["bytes"], part["sha256"]), part["path"]
            with source.open("rb") as input_stream:
                while block := input_stream.read(1024 * 1024):
                    hasher.update(block)
                    size += len(block)
                    if stream is not None:
                        stream.write(block)
        assert (size, hasher.hexdigest()) == expected, record["path"]
        if stream is not None:
            stream.flush()
            os.fsync(stream.fileno())
            stream.close()
            stream = None
            assert identity(temporary) == expected
            os.chmod(temporary, 0o644)
            # The temporary file and destination share a filesystem. link() fails
            # atomically if any destination appeared, so no existing file is replaced.
            os.link(temporary, target)
            temporary.unlink()
            temporary = None
    finally:
        if stream is not None:
            stream.close()
        if temporary is not None:
            temporary.unlink(missing_ok=True)
    return {"path": record["path"], "bytes": size, "sha256": hasher.hexdigest(), "parts": len(parts), "existing_archive_verified": already_present, "restored": not already_present and not verify_only, "all_part_identities_verified": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=Path("archive-parts.json"))
    parser.add_argument("--output-root", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    manifest_path = args.manifest.resolve()
    root = manifest_path.parent
    output_root = args.output_root.resolve() if args.output_root else root
    manifest = json.loads(manifest_path.read_text())
    assert manifest["schema"] == "r10.archive-parts.v1"
    results = [restore(root, output_root, record, args.verify_only) for record in manifest["archives"]]
    print(json.dumps({"status": "verified", "verify_only": args.verify_only, "archives": results}, indent=2))


if __name__ == "__main__":
    main()
