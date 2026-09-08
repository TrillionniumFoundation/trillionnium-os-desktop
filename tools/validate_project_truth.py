#!/usr/bin/env python3
"""Run non-status invariants plus the sole closed status projection gate."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLS = Path(__file__).resolve().parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_NON_STATUS = _load(
    "non_status_project_truth",
    TOOLS / "non_status_project_truth.py",
)
_STATUS = _load("structured_status", TOOLS / "structured_status_repository.py")

STATUS_REGISTRY_PATH = _STATUS.STATUS_REGISTRY_PATH
STATUS_REGISTRY_SCHEMA = _STATUS.STATUS_REGISTRY_SCHEMA
INTEGRATED_STATE_SCHEMA = _STATUS.INTEGRATED_STATE_SCHEMA
EXPECTED_WORKSPACE_MEMBERS = _STATUS.EXPECTED_WORKSPACE_MEMBERS
status_projection_errors = _STATUS.status_projection_errors
render_integrated_state = _STATUS.render_integrated_state
validate_integrated_state_record = _STATUS.validate_integrated_state_record
SOURCE_STATE_PATH = _STATUS.SOURCE_STATE_PATH
SOURCE_STATE_SCHEMA = _STATUS.SOURCE_STATE_SCHEMA
validate_source_state_record = _STATUS.validate_source_state_record


def main() -> int:
    non_status_errors = _NON_STATUS.validate_non_status_repository(ROOT)
    status_errors = _STATUS.validate_repository(ROOT)

    for error in non_status_errors:
        print(f"ERROR: {error}", file=sys.stderr)
    for error in status_errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if non_status_errors or status_errors:
        print(
            "project truth validation failed "
            f"(non_status={len(non_status_errors)}, "
            f"structured_status={len(status_errors)})",
            file=sys.stderr,
        )
        return 1
    print("project truth validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
