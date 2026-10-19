#!/usr/bin/env python3
"""Split explicit immutable archives into verified 1.5 MiB transport parts."""

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


PART_BYTES = 1572864


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    config = json.loads(args.config.read_text())
    parts_root = root / "archive-parts"
    assert not parts_root.exists()
    assert not (root / "archive-parts.json").exists()
    archives = []
    for item in config["archives"]:
        relative = PurePosixPath(item["path"])
        assert not relative.is_absolute() and ".." not in relative.parts
        assert len(PurePosixPath(item["key"]).parts) == 1 and item["key"] not in {"", ".", ".."}
        path = root / relative
        assert not path.is_symlink() and path.is_file()
        before = path.read_bytes()
        assert len(before) > PART_BYTES
        directory = parts_root / item["key"]
        directory.mkdir(parents=True, exist_ok=False)
        chunks = []
        total = hashlib.sha256()
        for index, offset in enumerate(range(0, len(before), PART_BYTES)):
            data = before[offset:offset + PART_BYTES]
            target = directory / f"{index:03d}.part"
            target.write_bytes(data)
            copied = target.read_bytes()
            assert copied == data
            total.update(copied)
            chunks.append({"index": index, "path": target.relative_to(root).as_posix(), "bytes": len(data), "sha256": sha(data)})
        assert path.read_bytes() == before
        assert total.hexdigest() == sha(before)
        archives.append({"path": relative.as_posix(), "bytes": len(before), "sha256": sha(before), "parts": chunks})
    manifest = {"schema": "r10.archive-parts.v1", "part_bytes": PART_BYTES, "archives": archives, "method": "Consecutive original bytes, with every part and reconstructed whole SHA-256 checked. No archive compression, member or original byte is changed."}
    manifest_path = root / "archive-parts.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    result = {"schema": "r10.archive-parts-execution.v1", "completed_at_utc": datetime.now(timezone.utc).isoformat(), "manifest": {"path": "archive-parts.json", "bytes": manifest_path.stat().st_size, "sha256": sha(manifest_path.read_bytes())}, "archive_count": len(archives), "parts_count": sum(len(a["parts"]) for a in archives), "all_original_archives_unchanged": True, "all_part_bytes_and_roundtrip_hashes_verified": True, "archive_recompression": False}
    args.receipt.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result))


if __name__ == "__main__":
    main()
