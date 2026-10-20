#!/usr/bin/env python3
"""Verify symbol gzip chunks and ELF bytes, then publish a new output path."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True,
                        help="new, nonexistent gzip file path")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    manifest = json.loads((root / "symbol-storage.json").read_text())
    requested = args.output.absolute()
    require(not os.path.lexists(requested), "output already exists")
    output = requested.parent.resolve(strict=True) / requested.name
    require(not os.path.lexists(output), "output already exists")
    require(output.parent.is_dir(), "output parent directory must exist")
    chunks = manifest["chunks"]
    require(len(chunks) == manifest["chunk_count"], "chunk count mismatch")
    require([row["index"] for row in chunks] == list(range(1, len(chunks) + 1)),
            "chunk indexes must be ordered and contiguous")
    require(len({row["path"] for row in chunks}) == len(chunks), "duplicate chunk")
    fd, temporary = tempfile.mkstemp(prefix="." + output.name + ".", dir=output.parent)
    compressed_sha = hashlib.sha256()
    compressed_size = 0
    try:
        with os.fdopen(fd, "wb") as sink:
            for row in chunks:
                name = row["path"]
                require(Path(name).name == name, "chunk name must be a basename")
                source_fd = os.open(root / name, os.O_RDONLY | os.O_NOFOLLOW)
                try:
                    before = os.fstat(source_fd)
                    require(stat.S_ISREG(before.st_mode), "chunk must be regular")
                    digest = hashlib.sha256()
                    size = 0
                    while True:
                        block = os.read(source_fd, 1024 * 1024)
                        if not block:
                            break
                        sink.write(block)
                        digest.update(block)
                        compressed_sha.update(block)
                        size += len(block)
                        compressed_size += len(block)
                    after = os.fstat(source_fd)
                    require((before.st_dev, before.st_ino, before.st_size,
                             before.st_mtime_ns, before.st_ctime_ns) ==
                            (after.st_dev, after.st_ino, after.st_size,
                             after.st_mtime_ns, after.st_ctime_ns), "chunk changed during read")
                    require(size == row["bytes"] and digest.hexdigest() == row["sha256"],
                            "chunk size/SHA256 mismatch: " + name)
                finally:
                    os.close(source_fd)
            sink.flush()
            os.fsync(sink.fileno())
        require(compressed_size == manifest["gzip"]["bytes"] and
                compressed_sha.hexdigest() == manifest["gzip"]["sha256"],
                "reassembled gzip size/SHA256 mismatch")
        elf_sha = hashlib.sha256()
        elf_size = 0
        with gzip.open(temporary, "rb") as elf:
            while True:
                block = elf.read(1024 * 1024)
                if not block:
                    break
                elf_sha.update(block)
                elf_size += len(block)
        require(elf_size == manifest["elf"]["bytes"] and
                elf_sha.hexdigest() == manifest["elf"]["sha256"],
                "decompressed ELF size/SHA256 mismatch")
        # Hard-link publication cannot replace any pre-existing output path.
        os.link(temporary, output, follow_symlinks=False)
        print(json.dumps({"passed": True, "output": str(output),
                          "gzip": manifest["gzip"], "elf": manifest["elf"]}))
    finally:
        os.unlink(temporary)


if __name__ == "__main__":
    main()
