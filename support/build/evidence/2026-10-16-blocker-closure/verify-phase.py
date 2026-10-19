#!/usr/bin/env python3
"""Recheck frozen bytes without Cargo, QEMU, extraction, or output mutation."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    root = Path(__file__).resolve().parent
    counts = {}
    for manifest in [root / "SHA256SUMS", *sorted(root.glob("*/SHA256SUMS"))]:
        rows = manifest.read_text().splitlines()
        for row in rows:
            expected, name = row.split("  ", 1)
            relative = Path(name)
            require(not relative.is_absolute() and ".." not in relative.parts,
                    "unsafe checksum path")
            require(digest((manifest.parent / relative).read_bytes()) == expected,
                    "checksum mismatch: " + str(manifest.parent / relative))
        counts[str(manifest.relative_to(root))] = len(rows)
    archives = {}
    for relative in ["entry-guards/archive-manifest.json", "artifact-snapshots/archive-manifest.json",
                     "osdk/members.json", "debug-success/raw-archive-members.json"]:
        index = root / relative
        data = json.loads(index.read_text())
        expected = {row.get("path", row.get("member", row.get("archive_member"))): row
                    for row in data["members"]}
        require(len(expected) == len(data["members"]), "duplicate archive index name")
        archive = index.parent / data["archive"]
        require(digest(archive.read_bytes()) == data.get("archive_sha256", data.get("sha256")),
                "raw archive digest mismatch")
        with tarfile.open(archive, "r:gz") as source:
            members = [member for member in source.getmembers() if member.isfile()]
            require(len(members) == len(expected) and {m.name for m in members} == set(expected),
                    "raw archive member names/count mismatch")
            for member in members:
                row = expected[member.name]
                content = source.extractfile(member).read()
                require(len(content) == row.get("size", row.get("bytes"))
                        and digest(content) == row["sha256"], "raw member mismatch: " + member.name)
        archives[relative] = len(expected)
    artifacts = root / "debug-failures/artifacts"
    storage = json.loads((artifacts / "symbol-storage.json").read_text())
    parts = []
    for row in storage["chunks"]:
        content = (artifacts / row["path"]).read_bytes()
        require(len(content) == row["bytes"] and digest(content) == row["sha256"], "symbol chunk mismatch")
        parts.append(content)
    compressed = b"".join(parts)
    require(len(compressed) == storage["gzip"]["bytes"] and digest(compressed) == storage["gzip"]["sha256"],
            "complete symbol gzip mismatch")
    elf = hashlib.sha256()
    size = 0
    with gzip.GzipFile(fileobj=io.BytesIO(compressed), mode="rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            size += len(block)
            elf.update(block)
    require(size == storage["elf"]["bytes"] and elf.hexdigest() == storage["elf"]["sha256"],
            "complete symbol ELF mismatch")
    print(json.dumps({"passed": True, "checksum_rows": counts, "raw_members": archives,
                      "symbol_chunks": len(parts), "symbol_elf_bytes": size}))


if __name__ == "__main__":
    main()
