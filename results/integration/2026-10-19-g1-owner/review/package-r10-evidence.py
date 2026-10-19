#!/usr/bin/env python3
"""Preserve already executed evidence; never runs products or changes source trees."""

import argparse
import hashlib
import io
import json
import tarfile
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


def digest(data):
    return hashlib.sha256(data).hexdigest()


def record(path, relative):
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Not a regular evidence file: {path}")
    data = path.read_bytes()
    return {"path": relative, "bytes": len(data), "sha256": digest(data)}


def verify(data, expected):
    assert len(data) == expected["bytes"], expected["path"]
    assert digest(data) == expected["sha256"], expected["path"]


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def safe_relative(name):
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or str(path) != name:
        raise ValueError(f"Unsafe archive path: {name}")
    return path


def verify_archive(root):
    artifact = json.loads((root / "artifact-manifest.json").read_text())
    for name in ["archive", "files_manifest"]:
        value = artifact[name]
        verify((root / value["path"]).read_bytes(), value)
    manifest = json.loads((root / artifact["files_manifest"]["path"]).read_text())
    entries = manifest["files"]
    assert len(entries) == manifest["entry_count"]
    names = [entry["path"] for entry in entries]
    assert names == sorted(set(names))
    expected = {entry["path"]: entry for entry in entries}
    expected[artifact["files_manifest"]["path"]] = artifact["files_manifest"]
    with tarfile.open(root / artifact["archive"]["path"], "r:xz") as archive:
        members = archive.getmembers()
        assert [m.name for m in members] == [artifact["files_manifest"]["path"]] + names
        for member in members:
            safe_relative(member.name)
            assert member.isfile() and not member.issym() and not member.islnk()
            assert member.size == expected[member.name]["bytes"]
            verify(archive.extractfile(member).read(), expected[member.name])
        for entry in artifact["primary_copies"]:
            data = (root / entry["path"]).read_bytes()
            verify(data, entry)
            assert data == archive.extractfile(entry.get("archive_entry", entry["path"])).read()
    return {"archive_entries": len(members), "primary_copies": len(artifact["primary_copies"]), "archive": artifact["archive"], "files_manifest": artifact["files_manifest"]}


def copy_frozen_package(args):
    source = args.source.resolve()
    destination = args.destination.resolve()
    assert not destination.exists(), destination
    before = sorted((record(p, p.relative_to(source).as_posix()) for p in source.rglob("*") if p.is_file()), key=lambda e: e["path"])
    verified_source = verify_archive(source)
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".frozen-package-", dir=destination.parent))
    for entry in before:
        relative = safe_relative(entry["path"])
        target = staging / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        data = (source / relative).read_bytes()
        verify(data, entry)
        target.write_bytes(data)
    assert verify_archive(staging) == verified_source
    after = sorted((record(p, p.relative_to(source).as_posix()) for p in source.rglob("*") if p.is_file()), key=lambda e: e["path"])
    assert after == before
    staging.rename(destination)
    receipt = {"schema": "r10.frozen-package-copy.v1", "completed_at_utc": datetime.now(timezone.utc).isoformat(), "source": str(source), "destination": str(destination), "files": before, "files_copied": len(before), "all_source_bytes_unchanged": True, "all_destination_bytes_identical": True, "verification": verified_source, "archive_rebuilt": False, "diagnostic_reexecuted": False}
    write_json(args.receipt, receipt)
    print(json.dumps({k: v for k, v in receipt.items() if k != "files"}))


def build_package(args):
    config = json.loads(args.config.read_text())
    destination = args.destination.resolve()
    assert not destination.exists(), destination
    source = Path(config["source_root"]).resolve()
    entries = []
    for name in config["files"]:
        safe_relative(name)
        assert not any(part in {"target", ".git", "cache", "registry", "__pycache__"} for part in PurePosixPath(name).parts)
        entries.append(record(source / name, name))
    entries.sort(key=lambda e: e["path"])
    assert len(entries) == len({entry["path"] for entry in entries})
    manifest = {"schema": "r10.g1.evidence-files.v1", "entry_count": len(entries), "total_uncompressed_file_bytes": sum(entry["bytes"] for entry in entries), "source_bindings": config["source_bindings"], "selection": config["selection"], "files": entries}
    manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode()
    manifest_record = {"path": "files-manifest.json", "bytes": len(manifest_bytes), "sha256": digest(manifest_bytes)}
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".g1-package-", dir=destination.parent))
    (staging / "files-manifest.json").write_bytes(manifest_bytes)
    primary = []
    with tarfile.open(staging / "raw-evidence.tar.xz", mode="w:xz", format=tarfile.USTAR_FORMAT, preset=6) as archive:
        for entry in [manifest_record] + entries:
            data = manifest_bytes if entry["path"] == "files-manifest.json" else (source / entry["path"]).read_bytes()
            verify(data, entry)
            info = tarfile.TarInfo(entry["path"])
            info.size = len(data)
            info.mode = 0o644
            info.uid = info.gid = info.mtime = 0
            info.uname = info.gname = ""
            archive.addfile(info, io.BytesIO(data))
            if entry["path"] in config["primary_copies"]:
                target = staging / entry["path"]
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
                primary.append({**entry, "archive_entry": entry["path"]})
    assert len(primary) == len(config["primary_copies"])
    for entry in entries:
        verify((source / entry["path"]).read_bytes(), entry)
    artifact = {"schema": "r10.g1.evidence-artifacts.v1", "archive": record(staging / "raw-evidence.tar.xz", "raw-evidence.tar.xz"), "files_manifest": manifest_record, "primary_copies": primary, "archive_format": "USTAR plus XZ preset 6; regular files only; uid/gid/mtime zero; mode 0644; sorted byte-bound evidence after the manifest", "input_snapshot_unchanged": True, "deterministic_archive": True, "products_reexecuted": False}
    write_json(staging / "artifact-manifest.json", artifact)
    verified = verify_archive(staging)
    staging.rename(destination)
    receipt = {"schema": "r10.g1.evidence-packaging-execution.v1", "completed_at_utc": datetime.now(timezone.utc).isoformat(), "config": record(args.config, args.config.name), "helper": record(Path(__file__), Path(__file__).name), "source_inputs_verified_before_and_after": True, "verification": verified, "destination": str(destination), "source_unchanged": True, "products_reexecuted": False}
    write_json(args.receipt, receipt)
    print(json.dumps(receipt))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    copy = commands.add_parser("copy-frozen")
    copy.add_argument("--source", type=Path, required=True)
    build = commands.add_parser("build")
    build.add_argument("--config", type=Path, required=True)
    for command in [copy, build]:
        command.add_argument("--destination", type=Path, required=True)
        command.add_argument("--receipt", type=Path, required=True)
    args = parser.parse_args()
    (copy_frozen_package if args.operation == "copy-frozen" else build_package)(args)


if __name__ == "__main__":
    main()
