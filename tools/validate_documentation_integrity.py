#!/usr/bin/env python3
"""Deterministic documentation projections; never a runtime/promotion authority."""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "manifests/modules.v1.json"
INDEX = "docs/modules/README.md"
PLAN = "2026-08-29-d6"
MAX_BYTES = 1_048_576
ANNEXES = (
    "docs/plan/PRODUCT_ARCHITECTURE.md",
    "docs/plan/CONTRACT_SECURITY_TESTING.md",
    "docs/plan/WORK_PACKAGES_AND_GATES.md",
)
ANNEX_STATUS = "**Status:** inherited d5 design annex; subordinate to the active d6 plan"
ACTIVE_LINK = "**Active plan:** [`2026-08-29-d6`](../DESKTOP_PLAN-2026-08-29-d6.md)"
PERMISSION_LINE = "Directory mode: `0700`; journal file mode: `0600`."
EXAMPLE_START = "<!-- executable-example: receipt-store-permissions -->"
EXAMPLE_END = "<!-- /executable-example: receipt-store-permissions -->"
NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\Z")
STATUS = re.compile(r"[A-Za-z0-9_]+\Z")


class InvalidDocumentation(ValueError):
    """A bounded source document is absent, malformed, stale, or unsafe."""


def read_text(root: Path, relative: str) -> str:
    """Read bounded regular UTF-8 input without following repository symlinks."""
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise InvalidDocumentation("noncanonical repository path")
    parts = relative.split("/")
    if Path(relative).is_absolute() or any(p in {"", ".", ".."} for p in parts):
        raise InvalidDocumentation("noncanonical repository path")
    current = root
    if root.is_symlink() or not root.is_dir():
        raise InvalidDocumentation("repository root must be a real directory")
    try:
        for component in parts:
            current /= component
            if stat.S_ISLNK(current.lstat().st_mode):
                raise InvalidDocumentation(f"symlink forbidden: {relative}")
        flags = os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(current, flags)
        with os.fdopen(fd, "rb") as source:
            metadata = os.fstat(source.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > MAX_BYTES:
                raise InvalidDocumentation(f"not a bounded regular file: {relative}")
            raw = source.read(MAX_BYTES + 1)
        if len(raw) > MAX_BYTES:
            raise InvalidDocumentation(f"file grew beyond byte limit: {relative}")
        return raw.decode("utf-8")
    except (OSError, UnicodeError) as error:
        raise InvalidDocumentation(f"cannot read {relative}: {type(error).__name__}") from error


def _unique(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise InvalidDocumentation(f"duplicate JSON member: {key}")
        result[key] = value
    return result


def _not_json_number(value: str) -> None:
    raise InvalidDocumentation("non-integer JSON number forbidden")


def load_registry(root: Path) -> dict[str, Any]:
    try:
        value = json.loads(read_text(root, REGISTRY), object_pairs_hook=_unique,
                           parse_float=_not_json_number, parse_constant=_not_json_number)
    except (ValueError, RecursionError) as error:
        raise InvalidDocumentation(f"invalid module registry: {error}") from error
    if not isinstance(value, dict) or value.get("schema") != "trillionnium.desktop.modules.v1":
        raise InvalidDocumentation("module registry schema mismatch")
    if value.get("plan_revision") != PLAN:
        raise InvalidDocumentation("module registry plan mismatch")
    entries = value.get("modules")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 256:
        raise InvalidDocumentation("module inventory must be nonempty and bounded")
    ids: set[str] = set()
    paths: set[str] = set()
    for item in entries:
        if not isinstance(item, dict):
            raise InvalidDocumentation("invalid module entry")
        name, path = item.get("id"), item.get("path")
        status_value, claim = item.get("status"), item.get("claim_ceiling")
        if not isinstance(name, str) or not NAME.fullmatch(name):
            raise InvalidDocumentation("invalid module identifier")
        if path not in (f"apps/{name}", f"crates/{name}"):
            raise InvalidDocumentation("module path/identifier mismatch")
        if item.get("documentation") != f"{path}/README.md":
            raise InvalidDocumentation("module documentation path mismatch")
        if name in ids or path in paths:
            raise InvalidDocumentation("duplicate module identity")
        if not isinstance(status_value, str) or not STATUS.fullmatch(status_value):
            raise InvalidDocumentation("invalid module status")
        if not isinstance(claim, str) or not 1 <= len(claim.encode("utf-8")) <= 4096:
            raise InvalidDocumentation("invalid module claim")
        if any(ord(c) < 32 or c in "`|<>" for c in claim):
            raise InvalidDocumentation("claim contains control or table markup")
        ids.add(name)
        paths.add(path)
    return value


def render_index(registry: dict[str, Any]) -> str:
    lines = [
        "<!-- generated from manifests/modules.v1.json; do not edit by hand -->",
        "# Module development documentation", "",
        "This index is a deterministic projection of the current Cargo module registry.",
        "Run `python3 tools/validate_documentation_integrity.py --render-index` to render it.",
        "The module validator separately checks workspace, API inventory, references and README contracts.",
        "Documentation coverage is source-governance evidence, not runtime or release qualification.", "",
        "## Coverage", "",
        "| Module | Workspace path | Status | Claim ceiling |",
        "| --- | --- | --- | --- |",
    ]
    for item in registry["modules"]:
        lines.append(f"| [`{item['id']}`](../../{item['documentation']}) | `{item['path']}` | "
                     f"`{item['status']}` | {item['claim_ceiling']} |")
    lines += ["", "## Required contract", "",
              "Each registered module has responsibilities, exclusions, dependency direction, public APIs,",
              "configuration, concurrency/failures, security invariants, tests, operations and compatibility rules.",
              "A matching index cannot establish that an implementation or a higher evidence tier is complete.", "",
              "## Scope beyond Cargo", "",
              "See [product subsystem coverage](PRODUCT_SUBSYSTEM_COVERAGE.md) for non-Cargo boundaries.",
              "See [d6 annex precedence](../plan/D6_ANNEX_PRECEDENCE.md) before using an inherited d5 annex.", "",
              "## Change workflow", "",
              "Change code, Cargo inventory, module README and registry together; regenerate this index;",
              "run module/documentation/repository/truth tests; obtain exact-head and prospective-merge evidence",
              "and independent review. Only protected promotion and an exact-main rerun can update integrated truth.", ""]
    return "\n".join(lines)


def permission_example(text: str) -> str:
    if text.count(EXAMPLE_START) != 1 or text.count(EXAMPLE_END) != 1:
        raise InvalidDocumentation("permission example markers missing or duplicated")
    body = text.split(EXAMPLE_START, 1)[1].split(EXAMPLE_END, 1)[0].strip()
    if not body.startswith("```python\n") or not body.endswith("\n```"):
        raise InvalidDocumentation("permission example must be a single Python fence")
    source = body[len("```python\n"):-len("\n```")]
    if "```" in source:
        raise InvalidDocumentation("nested permission example fence")
    return source + "\n"


def validate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    try:
        expected = render_index(load_registry(root))
        if read_text(root, INDEX) != expected:
            errors.append("module index is stale; regenerate from manifests/modules.v1.json")
    except InvalidDocumentation as error:
        errors.append(str(error))
    for path in ANNEXES:
        try:
            header = "\n".join(read_text(root, path).splitlines()[:24])
            if header.count(ANNEX_STATUS) != 1 or header.count(ACTIVE_LINK) != 1:
                errors.append(f"inherited annex precedence is missing or stale: {path}")
            if "normative component of the active canonical plan" in header:
                errors.append(f"superseded annex falsely claims current authority: {path}")
        except InvalidDocumentation as error:
            errors.append(str(error))
    try:
        text = read_text(root, "crates/hepta-session-core/README.md")
        if text.count(PERMISSION_LINE) != 1:
            errors.append("receipt directory/file permission contract is missing or duplicated")
        if re.search(r"0600.{0,24}journal directory", text, re.IGNORECASE):
            errors.append("0600 is a file mode, not a traversable journal-directory mode")
        permission_example(text)
        read_text(root, "docs/plan/D6_ANNEX_PRECEDENCE.md")
        read_text(root, "docs/modules/PRODUCT_SUBSYSTEM_COVERAGE.md")
    except InvalidDocumentation as error:
        errors.append(str(error))
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render-index", action="store_true", help="render to stdout; never mutates evidence")
    args = parser.parse_args()
    if args.render_index:
        try:
            print(render_index(load_registry(ROOT)), end="")
            return 0
        except InvalidDocumentation as error:
            print(f"ERROR: {error}", file=sys.stderr)
            return 1
    errors = validate()
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        return 1
    print("documentation integrity passed; source documentation only, no promotion authority")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
