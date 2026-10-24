#!/usr/bin/env python3
"""Resolve one exact userspace compiler from the reviewed original source."""
import hashlib
from pathlib import Path
import re
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
    if name not in ("cargo", "rustc") or not isinstance(output, str):
        raise ValueError("original Cargo or rustc version output required")
    line = output.strip()
    if "\n" in line or re.fullmatch(re.escape(name + " " + channel) + r" \([^\r\n]+\)", line) is None:
        raise ValueError("installed " + name + " differs from reviewed Rust " + channel)
    return line
