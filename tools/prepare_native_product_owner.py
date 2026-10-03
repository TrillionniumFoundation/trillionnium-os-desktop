#!/usr/bin/env python3
"""Prepare only the reviewed actual Servo consumer target on pristine exact PIN.

This is source assembly, never runtime/installed qualification. It applies no
S07/S08 action patch and executes no downloaded payload. A generated lock must
be checked separately before any --locked compile or actual test execution.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import stat
import subprocess
import secrets
import tomllib
try:
    from .artifact_evidence import open_file, open_managed_file
except ImportError:
    from artifact_evidence import open_file, open_managed_file

PIN = "670ae8a70801b162e186f81cbb5bdd2d59c39108"
ROOT = Path(__file__).resolve().parents[1]
MAX_SOURCE = 2 * 1024 * 1024
PIN_FILES = {
    "rustfmt.toml": "9bac67039cd8f892bb9c1ff0780e6e1f2f8dbd8b6787552e4c827f9363452eda",
    "Cargo.lock": "656009c8ff251607e66541c8ae1c36d3d5ac5ed8662b2c67d01bca544c4f035a",
    "Cargo.toml": "1543c16e43cc716a4e32ec0b541dce9b072ee171acefd611e9ca2c450f27c020",
    "components/servo/Cargo.toml": "0d8133a3297ad62c0a828e94eee4fdc44e866be83fdaed7cf6099cc350f5c9ef",
    "components/servo/tests/common/mod.rs": "68584772ab7e99754c2b7059b8f88a22b287fcf475ab72bea717fda00e289b42",
}
SOURCES = {
    "experiments/servo-product-owner/src/native_owner.rs": "components/servo/tests/trillionnium_native_owner.rs",
    "experiments/servo-product-owner/src/connected_tests.rs": "components/servo/tests/trillionnium_product_owner.rs",
}
DEPS = {
    "hepta-agent-transport": "crates/hepta-agent-transport",
    "hepta-browser-actor": "crates/hepta-browser-actor",
    "hepta-browser-codec": "crates/hepta-browser-codec",
    "hepta-peer-attestation": "crates/hepta-peer-attestation",
    "hepta-session-core": "crates/hepta-session-core",
    "hepta-agent-port": "crates/hepta-agent-port",
    "hepta-browserd": "apps/hepta-browserd",
}
FORMAT_CONFIG = "experiments/servo-product-owner/rustfmt.toml"

def read(path: Path) -> bytes:
    with open_managed_file(path.absolute()) as stream:
        before = stream.stat()
        if before.st_size > MAX_SOURCE:
            raise ValueError("source exceeds its byte bound")
        data = stream.read(MAX_SOURCE + 1)
        after = stream.stat()
        current = path.lstat()
        identity = lambda item: (item.st_dev, item.st_ino, item.st_mode, item.st_uid, item.st_nlink, item.st_size, item.st_mtime_ns, item.st_ctime_ns)
        if identity(before) != identity(after) or identity(current) != identity(after) or after.st_nlink != 1 or len(data) != before.st_size:
            raise ValueError("source changed while reading")
        return data

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", "-C", str(root), *args], text=True, timeout=30).strip()

class _SourceDescriptor:
    """One descriptor owner; finalization closes descriptors only, never paths.

    Ordinary Python-line interruption before the native close still releases
    the detached owned descriptor. A close already attempted is never retried:
    it may have succeeded before an exception and its integer may be reused.
    This is not a guarantee about C/opcode windows or repeated cleanup faults.
    """
    def __init__(self) -> None:
        self.fd: int | None = None

    def close(self) -> None:
        descriptor = None
        close_attempted = False
        try:
            descriptor, self.fd = self.fd, None
            if descriptor is not None:
                close_attempted = True; os.close(descriptor)
        finally:
            if descriptor is not None and not close_attempted:
                os.close(descriptor)

    def __del__(self) -> None:
        try: self.close()
        except BaseException: pass


def write_source(destination: Path, data: bytes, previous: bytes | None = None) -> None:
    # Owners enter the cleanup collection before any native open. Transfer of
    # the current parent never loses ownership of an older directory descriptor.
    owned: list[_SourceDescriptor] = []
    parent = None
    staged = None
    temporary = ".native-owner-" + secrets.token_hex(16)
    try:
        parent = _SourceDescriptor(); owned.append(parent)
        parent.fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        for component in destination.absolute().parent.parts[1:]:
            if component in {".", ".."}: raise ValueError("noncanonical source destination")
            following = _SourceDescriptor(); owned.append(following)
            following.fd = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent.fd)
            parent.close()
            parent = following
        parent_identity = os.fstat(parent.fd)
        if previous is None:
            try: os.stat(destination.name, dir_fd=parent.fd, follow_symlinks=False)
            except FileNotFoundError: pass
            else: raise ValueError("assembled target already exists")
        elif read(destination) != previous:
            raise ValueError("PIN manifest changed before source assembly")
        staged = _SourceDescriptor(); owned.append(staged)
        staged.fd = os.open(temporary, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600, dir_fd=parent.fd)
        original = os.fstat(staged.fd)
        offset = 0
        while offset < len(data):
            count = os.write(staged.fd, data[offset:])
            if count <= 0: raise ValueError("source assembly short write")
            offset += count
        os.fsync(staged.fd)
        named = os.stat(temporary, dir_fd=parent.fd, follow_symlinks=False)
        current_parent = destination.parent.lstat()
        if not stat.S_ISREG(named.st_mode) or named.st_nlink != 1 or named.st_size != len(data) or (named.st_dev, named.st_ino) != (original.st_dev, original.st_ino) or (current_parent.st_dev, current_parent.st_ino) != (parent_identity.st_dev, parent_identity.st_ino):
            raise ValueError("staged source/parent custody changed")
        if previous is None:
            os.link(temporary, destination.name, src_dir_fd=parent.fd, dst_dir_fd=parent.fd, follow_symlinks=False)
            os.unlink(temporary, dir_fd=parent.fd)
        else:
            if read(destination) != previous: raise ValueError("PIN input changed before publication")
            os.replace(temporary, destination.name, src_dir_fd=parent.fd, dst_dir_fd=parent.fd)
        os.fsync(parent.fd)
        named = os.stat(destination.name, dir_fd=parent.fd, follow_symlinks=False)
        if (named.st_dev, named.st_ino, named.st_nlink, named.st_size) != (original.st_dev, original.st_ino, 1, len(data)) or read(destination) != data:
            raise ValueError("source publication readback differs")
    finally:
        # Shared owners, rather than duplicated integers, make transfer and
        # finalization idempotent. Attempt all retained closes after an error.
        descriptors, owned = owned, []
        failure = None
        if staged is not None and staged.fd is not None:
            try:
                original = os.fstat(staged.fd)
                if parent is not None and parent.fd is not None:
                    try: named = os.stat(temporary, dir_fd=parent.fd, follow_symlinks=False)
                    except FileNotFoundError: pass
                    else:
                        if (named.st_dev, named.st_ino) == (original.st_dev, original.st_ino):
                            os.unlink(temporary, dir_fd=parent.fd)
            except BaseException as error: failure = error
        for descriptor in reversed(descriptors):
            try: descriptor.close()
            except BaseException as error:
                if failure is None: failure = error
        if failure is not None: raise failure


def verify_format_config(upstream: Path, root: Path = ROOT) -> str:
    original = read(upstream / "rustfmt.toml")
    local = read(root / FORMAT_CONFIG)
    if digest(original) != PIN_FILES["rustfmt.toml"] or local != original:
        raise ValueError("native owner formatting configuration differs from exact PIN")
    return digest(original)


def prepare(upstream: Path, root: Path = ROOT) -> dict:
    upstream = upstream.absolute()
    root = root.absolute()
    if git(upstream, "rev-parse", "HEAD") != PIN or git(upstream, "status", "--porcelain=v1"):
        raise ValueError("upstream must be pristine exact PIN")
    for path, expected in PIN_FILES.items():
        if digest(read(upstream / path)) != expected:
            raise ValueError("upstream original API/manifests differ from PIN")
    formatter_configuration_sha256 = verify_format_config(upstream, root)
    inputs = {source: read(root / source) for source in SOURCES}
    manifest = read(upstream / "components/servo/Cargo.toml")
    cargo = tomllib.loads(manifest.decode("utf-8"))
    if any(name in cargo.get("dev-dependencies", {}) for name in DEPS):
        raise ValueError("product dependencies are already present")
    extra = "\n# Explicit immutable/read-only consumer qualification graph; no installed activation.\n"
    for name, relative in DEPS.items():
        # JSON/TOML quoting supplies real strings; this value is never shell text.
        extra += f"\n[dev-dependencies.{name}]\npath = {json.dumps(str(root / relative))}\n"
    extra += '\n[[test]]\nname = "trillionnium_product_owner"\npath = "tests/trillionnium_product_owner.rs"\n'
    for source, target in SOURCES.items():
        write_source(upstream / target, inputs[source])
    write_source(upstream / "components/servo/Cargo.toml", manifest + extra.encode("utf-8"), manifest)
    expected_outputs = {target: inputs[source] for source, target in SOURCES.items()}
    expected_outputs["components/servo/Cargo.toml"] = manifest + extra.encode("utf-8")
    for name, expected in expected_outputs.items():
        if read(upstream / name) != expected:
            raise ValueError("assembled source readback does not match input")
    return {"schema": "trillionnium.native-owner-source-assembly.v1", "servo_commit": PIN,
            "source_sha256": {name: digest(data) for name, data in inputs.items()},
            "formatter_configuration_sha256": formatter_configuration_sha256,
            "qualification": "not_executed", "installed_activation": False}

def verify_lock(before: Path, after: Path) -> dict:
    old = tomllib.loads(read(before).decode("utf-8"))
    new = tomllib.loads(read(after).decode("utf-8"))
    identity = lambda package: (package["name"], package["version"], package.get("source"), package.get("checksum"))
    if digest(read(before)) != PIN_FILES["Cargo.lock"]:
        raise ValueError("baseline lock does not bind pristine exact PIN")
    old_registry = {identity(p) for p in old["package"] if p.get("source")}
    new_registry = {identity(p) for p in new["package"] if p.get("source")}
    approved_libc = {
        ("libc", "0.2.186", "registry+https://github.com/rust-lang/crates.io-index", "68ab91017fe16c622486840e4c83c9a37afeff978bd239b5293d61ece587de66"),
        ("libc", "0.2.189", "registry+https://github.com/rust-lang/crates.io-index", "3eaf3ede3fee6db1a4c2ee091bf8a8b4dccdc6d17f656fb07896ee72867612f2"),
    }
    if not (old_registry ^ new_registry) <= approved_libc:
        raise ValueError("unreviewed third-party dependency resolution drift")
    old_local = {identity(p) for p in old["package"] if not p.get("source")}
    new_local = {identity(p) for p in new["package"] if not p.get("source")}
    permitted = set(DEPS) | {"hepta-browser-actor-simulation", "hepta-browser-contracts", "trillionnium-contract-core"}
    if not old_local <= new_local or any(name not in permitted or version != "0.1.0" for name, version, _, _ in new_local - old_local):
        raise ValueError("unreviewed local package identity change")
    def normalize(values):
        return sorted("libc" if value.startswith("libc ") else value for value in values)
    by_identity = {identity(p): p for p in new["package"]}
    if len(by_identity) != len(new["package"]):
        raise ValueError("duplicate package identity")
    for package in new["package"]:
        if package["name"] == "libc" and (identity(package) not in approved_libc or set(package) != {"name", "version", "source", "checksum"}):
            raise ValueError("unreviewed libc package fields or dependency edges")
    for package in old["package"]:
        if package["name"] == "libc":
            continue
        updated = by_identity.get(identity(package))
        if updated is None:
            raise ValueError("original package disappeared")
        for key in set(package) | set(updated):
            if key == "dependencies":
                expected = normalize(package.get(key, []))
                actual = normalize(updated.get(key, []))
                if package["name"] == "servo":
                    actual = [value for value in actual if value.split(" ")[0] not in DEPS]
                if actual != expected:
                    raise ValueError("original package dependency edges changed")
            elif updated.get(key) != package.get(key):
                raise ValueError("original package fields changed")
    return {"schema": "trillionnium.native-owner-lock-binding.v1", "original_sha256": digest(read(before)),
            "assembled_sha256": digest(read(after)), "actual_servo_execution": False}

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("prepare"); build.add_argument("--upstream", required=True, type=Path)
    lock = sub.add_parser("verify-lock"); lock.add_argument("--before", required=True, type=Path); lock.add_argument("--after", required=True, type=Path)
    args = parser.parse_args()
    result = prepare(args.upstream) if args.command == "prepare" else verify_lock(args.before, args.after)
    print(json.dumps(result, sort_keys=True))
    return 0
if __name__ == "__main__":
    raise SystemExit(main())
