#!/usr/bin/env python3
"""Resolve one exact userspace compiler from the reviewed original source."""
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tomllib


def reviewed_channel(review):
    value = review.get("userspace_toolchain")
    if not isinstance(value, dict) or set(value) != {"channel", "manifest", "sha256"}:
        raise ValueError("explicit reviewed userspace toolchain identity required")
    if not isinstance(value["channel"], str) or re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", value["channel"]) is None:
        raise ValueError("userspace toolchain must name an exact stable Rust version")
    if value["manifest"] != "codex-rs/rust-toolchain.toml":
        raise ValueError("original Hepta toolchain manifest required")
    if not isinstance(value["sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is None:
        raise ValueError("reviewed toolchain manifest SHA256 required")
    return value["channel"]


def verify_manifest(source, review):
    channel = reviewed_channel(review)
    path = Path(source) / review["userspace_toolchain"]["manifest"]
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 64 * 1024:
        raise ValueError("bounded regular original toolchain manifest required")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != review["userspace_toolchain"]["sha256"]:
        raise ValueError("reviewed toolchain manifest digest differs")
    actual = tomllib.loads(raw.decode("utf-8"))["toolchain"]["channel"]
    if actual != channel:
        raise ValueError("original source toolchain differs from reviewed version")
    return channel


def validate_version(name, output, channel):
    """Check the actual `--version` response, not just an executable pathname."""
    if name not in ("cargo", "rustc", "rustdoc", "cargo-clippy", "clippy-driver") or not isinstance(output, str):
        raise ValueError("original Rust tool version output required")
    if name in ("cargo-clippy", "clippy-driver"):
        # Clippy's crate version is 0.<Rust major>.<Rust minor>. Its embedded
        # compiler is checked separately, including the Rust patch version.
        prefix = "clippy 0." + ".".join(channel.split(".")[:2])
    else:
        prefix = name + " " + channel
    line = output.strip()
    if "\n" in line or re.fullmatch(re.escape(prefix) + r" \([^\r\n]+\)", line) is None:
        raise ValueError("installed " + name + " differs from reviewed Rust " + channel)
    return line


CLIPPY_TOOLS = ("cargo", "rustc", "rustdoc", "cargo-clippy", "clippy-driver")


def executable_digest(path):
    if (not path.is_absolute() or path.resolve(strict=True) != path or not path.is_file()
            or path.is_symlink() or not os.access(path, os.X_OK)
            or not 0 < path.stat().st_size <= 512 * 1024**2):
        raise ValueError("bounded canonical executable required: " + str(path))
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def clippy_environment(source, review, environment):
    """Select and identify one reviewed Cargo/Clippy/compiler installation.

    Cargo searches CARGO_HOME/bin before PATH for custom subcommands. Merely
    prepending the real toolchain bin directory does not bind `cargo clippy`.
    The caller invokes the identified cargo-clippy directly; CARGO binds its
    nested Cargo, and the adjacent clippy-driver's embedded rustc is verified.
    No toolchain is installed and no user override/default is changed.
    """
    channel = verify_manifest(source, review)
    selected = subprocess.check_output(
        ["rustup", "which", "--toolchain", channel, "cargo"], text=True, timeout=30,
    ).strip()
    cargo = Path(selected)
    if not cargo.is_absolute() or "\n" in selected or cargo.name != "cargo":
        raise ValueError("rustup must identify an absolute original Cargo executable")
    cargo = cargo.resolve(strict=True)
    paths = {name: cargo.parent / name for name in CLIPPY_TOOLS}
    # Check all components before executing even a version query. In particular,
    # a symlink to a rustup proxy must not stand in for the actual driver.
    identities = {name: {"path": str(path), "sha256": executable_digest(path)}
                  for name, path in paths.items()}
    bound = dict(environment)
    bound.update(PATH=str(cargo.parent) + ":/usr/bin:/bin", RUSTUP_TOOLCHAIN=channel,
                 CARGO=str(cargo), RUSTC=str(paths["rustc"]), RUSTDOC=str(paths["rustdoc"]),
                 RUSTC_WRAPPER="", RUSTC_WORKSPACE_WRAPPER="")
    for name, path in paths.items():
        result = subprocess.run([str(path), "--version"], env=bound, capture_output=True,
                                text=True, timeout=30, check=True)
        identities[name]["version"] = validate_version(name, result.stdout, channel)
    linked = subprocess.run([str(paths["clippy-driver"]), "--rustc", "--version"],
                            env=bound, capture_output=True, text=True, timeout=30, check=True)
    linked_version = validate_version("rustc", linked.stdout, channel)
    if linked_version != identities["rustc"]["version"]:
        raise ValueError("Clippy driver embeds a different compiler from reviewed rustc")
    identities["clippy-driver"]["rustc_version"] = linked_version
    if identities["cargo-clippy"]["version"] != identities["clippy-driver"]["version"]:
        raise ValueError("Cargo Clippy and its adjacent driver have different versions")
    verify_executables(identities)
    return bound, identities


def verify_executables(identities):
    """Refuse a changed executable before/after a command or receipt freeze."""
    if set(identities) != set(CLIPPY_TOOLS):
        raise ValueError("complete Cargo/Clippy/compiler identities required")
    parents = {Path(value["path"]).parent for value in identities.values()}
    if len(parents) != 1:
        raise ValueError("Cargo/Clippy/compiler components must share one installation")
    for name, value in identities.items():
        path = Path(value["path"])
        if path.name != name or executable_digest(path) != value["sha256"]:
            raise ValueError("reviewed tool executable changed: " + name)
