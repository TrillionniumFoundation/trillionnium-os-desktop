#!/usr/bin/env python3
"""Project the Cargo module index; never mutate implementation or evidence state."""
from __future__ import annotations

import argparse
import html
import json
import os
import re
import stat
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).absolute().parents[1]
REGISTRY = "manifests/modules.v1.json"
INDEX = "docs/modules/README.md"
MAX_BYTES = 1_048_576
IDENTIFIER = re.compile(r"[a-z][a-z0-9_-]{0,127}\Z")


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def reject_number(value: str) -> None:
    raise ValueError(f"unsupported JSON number: {value}")


def safe_path(root: Path, relative: str, *, missing_leaf: bool = False) -> Path:
    """Reject noncanonical paths and symlinks, including the checkout root."""
    if not isinstance(relative, str) or not re.fullmatch(r"[A-Za-z0-9_./-]+", relative):
        raise ValueError("noncanonical source path")
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts) or Path(relative).is_absolute():
        raise ValueError("noncanonical source path")
    root = root.absolute()
    current = Path(root.anchor)
    for part in root.parts[1:]:
        current /= part
        if not stat.S_ISDIR(current.lstat().st_mode):
            raise ValueError("checkout root traverses a symlink or non-directory")
    for index, part in enumerate(parts):
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            if missing_leaf and index == len(parts) - 1:
                return current
            raise ValueError(f"missing source path: {relative}") from None
        if stat.S_ISLNK(mode):
            raise ValueError(f"symlinked source path: {relative}")
        if index < len(parts) - 1 and not stat.S_ISDIR(mode):
            raise ValueError(f"non-directory source parent: {relative}")
        if index == len(parts) - 1 and not stat.S_ISREG(mode):
            raise ValueError(f"non-regular source file: {relative}")
    return current


def read_text(root: Path, relative: str) -> str:
    path = safe_path(root, relative)
    flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise ValueError(f"invalid or oversized source file: {relative}")
        raw = source.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError(f"oversized source file: {relative}")
    return raw.decode("utf-8")


def load_json(root: Path, relative: str) -> dict[str, Any]:
    value = json.loads(
        read_text(root, relative), object_pairs_hook=unique_object,
        parse_constant=reject_number, parse_float=reject_number,
    )
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {relative}")
    return value


def load_rows(root: Path) -> tuple[str, list[dict[str, str]]]:
    registry = load_json(root, REGISTRY)
    if registry.get("schema") != "trillionnium.desktop.modules.v1":
        raise ValueError("unsupported module registry schema")
    truth = load_json(root, "manifests/project-state.v1.json")
    revision = registry.get("plan_revision")
    if not isinstance(revision, str) or revision != truth.get("active_plan_revision"):
        raise ValueError("module index plan differs from project truth")
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", revision):
        raise ValueError("invalid plan revision")
    cargo = tomllib.loads(read_text(root, "Cargo.toml"))
    members = cargo.get("workspace", {}).get("members")
    entries = registry.get("modules")
    if not isinstance(members, list) or not members or not isinstance(entries, list):
        raise ValueError("nonempty explicit workspace and module registry required")
    if any(not isinstance(path, str) for path in members) or len(set(members)) != len(members):
        raise ValueError("invalid or duplicate workspace members")
    if len(entries) != len(members) or any(not isinstance(entry, dict) for entry in entries):
        raise ValueError("module registry does not cover the workspace")
    if [entry.get("path") for entry in entries] != members:
        raise ValueError("module registry order or membership differs from Cargo")
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    for entry in entries:
        row: dict[str, str] = {}
        for field in ("id", "package", "path", "documentation", "status", "claim_ceiling"):
            value = entry.get(field)
            if not isinstance(value, str) or not value or len(value.encode("utf-8")) > 8192:
                raise ValueError(f"invalid module field: {field}")
            if any(ord(char) < 32 or ord(char) == 127 for char in value):
                raise ValueError(f"control character in module field: {field}")
            row[field] = value
        if not IDENTIFIER.fullmatch(row["id"]) or row["id"] in seen:
            raise ValueError("invalid or duplicate module identity")
        seen.add(row["id"])
        if row["package"] != row["id"] or not IDENTIFIER.fullmatch(row["status"]):
            raise ValueError("module identity or status is noncanonical")
        if row["documentation"] != row["path"] + "/README.md":
            raise ValueError("module README is not colocated with its Cargo package")
        package = tomllib.loads(read_text(root, row["path"] + "/Cargo.toml"))
        if package.get("package", {}).get("name") != row["package"]:
            raise ValueError("module package differs from Cargo")
        readme = read_text(root, row["documentation"])
        for field, label in (("status", "Status"), ("claim_ceiling", "Claim ceiling")):
            if readme.count(f"{label}: `{row[field]}`") != 1:
                raise ValueError(f"module README {field} projection is stale")
        rows.append(row)
    return revision, rows


def table_text(value: str) -> str:
    return html.escape(value, quote=False).replace("\\", "&#92;").replace("|", "&#124;").replace("`", "&#96;")


def render(root: Path) -> str:
    revision, rows = load_rows(root)
    lines = [
        "<!-- generated by tools/project_module_index.py; do not edit by hand -->",
        "# Module development documentation", "",
        f"Plan revision: `{revision}`", "",
        "This index is generated from `manifests/modules.v1.json` and checked against",
        "the exact Cargo workspace, package identities and module README projections.",
        "Run `python3 tools/project_module_index.py --write` after a reviewed registry change.",
        "`--check` is read-only and rejects any byte-level index drift.", "",
        "Coverage is limited to Cargo workspace packages. It is not whole-product",
        "documentation coverage, implementation completion, installed-image evidence,",
        "hardware qualification, signing-key custody or release authority.", "",
        "## Coverage", "",
        "| Module | Workspace path | Status | Claim ceiling |",
        "| --- | --- | --- | --- |",
    ]
    for row in rows:
        lines.append(
            f"| [`{row['id']}`](../../{row['documentation']}) | `{row['path']}` | "
            f"`{row['status']}` | {table_text(row['claim_ceiling'])} |"
        )
    lines += [
        "", "## Required contract", "",
        "The separate module-documentation gate still enforces detailed visible sections,",
        "exact binary/feature inventory, safe references and claim projection. This index",
        "generator supplements that gate; it cannot replace or weaken it.", "",
        "## Change workflow", "",
        "Update implementation, Cargo metadata, contracts, tests, module README and registry",
        "together. Regenerate this index, run `make validate` and the complete locked Rust",
        "checks, then obtain fresh independent review on the exact head and prospective",
        "merge. Only protected promotion and exact-main verification can change integrated",
        "project truth. A generated page cannot close a runtime, hardware or release gate.",
        "",
    ]
    return "\n".join(lines)


def check(root: Path) -> None:
    expected = render(root).encode("utf-8")
    actual = read_text(root, INDEX).encode("utf-8")
    if actual != expected:
        raise ValueError("module index is stale; regenerate with --write and review the diff")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--check", action="store_true")
    modes.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.write:
            result = render(args.root).encode("utf-8")
            destination = safe_path(args.root, INDEX, missing_leaf=True)
            destination.write_bytes(result)
            print("module index regenerated; no evidence or implementation state changed")
        else:
            check(args.root)
            print("module index projection passed")
        return 0
    except (OSError, ValueError, UnicodeError, tomllib.TOMLDecodeError) as error:
        print(f"MODULE-INDEX: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
