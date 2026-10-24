#!/usr/bin/env python3
"""Explicit, hash-pinned V8 supplier files; no ambient build overrides.

These are optional build inputs, not evidence that an ELF has run. Their bytes
are frozen under the fresh build output so a mutable supplier cache is not used
by Cargo while the original sources are being compiled.
"""
import hashlib
from pathlib import Path
import re
import shutil
import stat


KINDS = {
    "archive": ("RUSTY_V8_ARCHIVE", "rusty-v8.a.gz", 1024**3),
    "bindings": ("RUSTY_V8_SRC_BINDING_PATH", "src_binding.rs", 16 * 1024**2),
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def add_arguments(parser):
    for name in KINDS:
        parser.add_argument("--v8-" + name, type=Path,
                            help="explicit original V8 supplier file, paired with its SHA and the other file")
        parser.add_argument("--expected-v8-" + name + "-sha256")


def file_identity(path, expected, limit):
    require(isinstance(expected, str) and re.fullmatch(r"[0-9a-f]{64}", expected) is not None,
            "V8 input requires an explicit SHA-256")
    path = Path(path).absolute()
    require(not path.is_symlink() and path.resolve(strict=True) == path,
            "V8 supplier path must be canonical and not a symlink")
    metadata = path.stat()
    require(stat.S_ISREG(metadata.st_mode) and 0 < metadata.st_size <= limit,
            "V8 supplier file must be regular and bounded")
    require(sha(path) == expected, "V8 supplier SHA-256 differs")
    return {"path": str(path), "sha256": expected, "bytes": metadata.st_size}


def selected(args):
    values = {name: (getattr(args, "v8_" + name, None),
                     getattr(args, "expected_v8_" + name + "_sha256", None)) for name in KINDS}
    provided = [value is not None for pair in values.values() for value in pair]
    require(not any(provided) or all(provided),
            "both V8 files and both expected SHA-256 values are required together")
    if not any(provided):
        return {"mode": "original-build-default", "supplied": {}, "frozen": {},
                "runtime_executed": False}
    supplied = {name: file_identity(path, expected, KINDS[name][2])
                for name, (path, expected) in values.items()}
    require(supplied["archive"]["path"] != supplied["bindings"]["path"],
            "V8 archive and bindings must be distinct files")
    return {"mode": "explicit-hash-pinned-files", "supplied": supplied, "frozen": {},
            "runtime_executed": False}


def freeze(record, output):
    if not record["supplied"]:
        return {}
    directory = output / "dependency-inputs"
    directory.mkdir(mode=0o700)
    for name, item in record["supplied"].items():
        source = Path(item["path"])
        require(file_identity(source, item["sha256"], KINDS[name][2]) == item,
                "V8 supplier identity changed before freezing")
        destination = directory / KINDS[name][1]
        with source.open("rb") as stream, destination.open("xb") as target:
            shutil.copyfileobj(stream, target, 1024 * 1024)
        destination.chmod(0o444)
        record["frozen"][name] = file_identity(destination, item["sha256"], KINDS[name][2])
        require(record["frozen"][name]["bytes"] == item["bytes"],
                "V8 supplier size changed during freezing")
    verify_frozen(record)
    return {KINDS[name][0]: item["path"] for name, item in record["frozen"].items()}


def verify_frozen(record):
    require(set(record["frozen"]) == set(record["supplied"]),
            "V8 pair was not completely frozen")
    for name, item in record["frozen"].items():
        require(file_identity(Path(item["path"]), item["sha256"], KINDS[name][2]) == item,
                "frozen V8 identity changed")
        require(item["sha256"] == record["supplied"][name]["sha256"],
                "frozen V8 bytes differ from selected supplier")
