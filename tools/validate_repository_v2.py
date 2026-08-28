#!/usr/bin/env python3
"""Composable D5 repository validator used while the legacy entry point is migrated."""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def fail(message: str) -> None:
    raise SystemExit(f"repository validation failed: {message}")


def main() -> int:
    with (ROOT / "Cargo.toml").open("rb") as handle:
        cargo = tomllib.load(handle)
    members = cargo.get("workspace", {}).get("members", [])
    expected = [
        "apps/hepta-browserd",
        "crates/hepta-agent-transport",
        "crates/hepta-browser-codec",
        "crates/hepta-agent-port",
        "crates/trillionnium-contract-core",
        "crates/hepta-browser-contracts",
        "crates/hepta-session-core",
    ]
    if members != expected or cargo.get("workspace", {}).get("default-members") != expected:
        fail("workspace member graph drifted")

    for path in ROOT.rglob("*.json"):
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
            fail(f"invalid JSON {path.relative_to(ROOT)}: {error}")

    command = [sys.executable, str(ROOT / "tools/validate_d0c04_rust_product.py")]
    completed = subprocess.run(command, cwd=ROOT, check=False)
    if completed.returncode != 0:
        fail("D0C-04 product validator failed")

    for path in ROOT.rglob("*"):
        if path.is_symlink():
            fail(f"repository symlink is forbidden: {path.relative_to(ROOT)}")

    print("D5 compositional repository validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
