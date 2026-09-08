#!/usr/bin/env python3
"""Reject coexistence of the retired status-facts model with the sole status authority."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ACTIVE_AUTHORITY_PATHS = (
    "docs/status-documents.v1.json",
    "tools/structured_status_model.py",
    "tools/structured_status.py",
    "docs/CURRENT_STATE.md",
)

RETIRED_AUTHORITY_PATHS = (
    "docs/status-facts.v1.json",
    "tools/validate_status_facts.py",
    "tests/test_status_facts.py",
    ".github/workflows/status-facts.yml",
)

PROJECTION_MARKER = (
    "<!-- generated from docs/status-documents.v1.json; do not edit by hand -->"
)


def validate(root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    for relative in ACTIVE_AUTHORITY_PATHS:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            errors.append(f"active status authority path must be a regular file: {relative}")

    for relative in RETIRED_AUTHORITY_PATHS:
        path = root / relative
        if path.exists() or path.is_symlink():
            errors.append(f"retired status authority must be absent: {relative}")

    projection = root / "docs/CURRENT_STATE.md"
    if projection.is_file() and not projection.is_symlink():
        try:
            first_line = projection.read_text(encoding="utf-8").splitlines()[0]
        except (OSError, UnicodeError, IndexError) as error:
            errors.append(f"cannot read integrated status projection: {error}")
        else:
            if first_line != PROJECTION_MARKER:
                errors.append(
                    "docs/CURRENT_STATE.md must identify docs/status-documents.v1.json "
                    "as its sole generated authority"
                )
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"status-authority singleton validation failed with {len(errors)} error(s)",
            file=sys.stderr,
        )
        return 1
    print("status-authority singleton validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
