#!/usr/bin/env python3
"""Run legacy project invariants plus the single closed status projection gate."""

from __future__ import annotations

import contextlib
import importlib.util
import io
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


_BASE = _load("_validate_project_truth_base", TOOLS / "_validate_project_truth_base.py")
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
    # The legacy validator keeps every non-status invariant. Its old prose
    # heuristic is deliberately disabled: the mandatory closed-record gate
    # below is the sole authority for integrated status projection.
    _BASE.check_status_documents = lambda _project: None
    stdout = io.StringIO()
    stderr = io.StringIO()
    with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
        base_result = _BASE.main()

    status_errors = _STATUS.validate_repository(ROOT)
    if base_result != 0:
        sys.stderr.write(stderr.getvalue())
    for error in status_errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if base_result != 0 or status_errors:
        print(
            "project truth validation failed "
            f"(legacy={base_result}, structured_status={len(status_errors)})",
            file=sys.stderr,
        )
        return 1
    print("project truth validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
