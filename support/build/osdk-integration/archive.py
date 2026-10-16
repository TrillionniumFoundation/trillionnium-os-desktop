#!/usr/bin/env python3
"""Archive integration evidence without generated example source or targets."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path, help="must not already exist")
    args = parser.parse_args()
    source = args.source.resolve()
    destination = args.destination.resolve()
    if destination.is_relative_to(source):
        raise SystemExit("archive must be outside its source tree")
    destination.mkdir(parents=True, exist_ok=False)
    entries = []
    excluded = {"target", "harness", "work", "tmp", "bin", "fixed-tmp", "__pycache__"}
    for path in sorted(source.rglob("*")):
        relative = path.relative_to(source)
        if not path.is_file() or excluded.intersection(relative.parts):
            continue
        if path.suffix not in (".log", ".json", ".patch", ".txt", ".lock", ".profraw", ".profdata"):
            continue
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        data = path.read_bytes()
        if path.suffix == ".log" or path.name.endswith(".metadata.json"):
            target = target.with_name(target.name + ".gz")
            target.write_bytes(gzip.compress(data, mtime=0))
        else:
            target.write_bytes(data)
        entries.append({"source": str(relative), "archived": str(target.relative_to(destination)),
                        "source_size": len(data), "source_sha256": hashlib.sha256(data).hexdigest()})
    for name, renamed in (("harness/Cargo.lock", "harness.Cargo.lock"),
                          ("rust-toolchain.toml", "rust-toolchain.toml")):
        path = source / name
        if path.is_file():
            shutil.copyfile(path, destination / renamed)
            entries.append({"source": name, "archived": renamed, "source_size": path.stat().st_size,
                            "source_sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    (destination / "archive.json").write_text(json.dumps({"schema": 1, "source": str(source),
        "excluded": sorted(excluded), "files": entries}, indent=2) + "\n")
    rows = [hashlib.sha256(path.read_bytes()).hexdigest() + "  " + str(path.relative_to(destination))
            for path in sorted(destination.rglob("*")) if path.is_file()]
    (destination / "evidence.sha256").write_text("\n".join(rows) + "\n")
    print(f"archived {len(entries)} evidence files to {destination}")


if __name__ == "__main__":
    main()
