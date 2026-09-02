#!/usr/bin/env python3
"""Stable facade for the strict governance validator.

The reviewed implementation remains in ``_validate_governance_integrity_impl``.
This facade registers the D3 source-reference workflow, the integrated-runtime
evidence-verifier workflow, and their reviewed local scripts without weakening
the exact workflow inventory or read-only workflow policy. It also preserves
the validator's historical test contract: regression tests may replace mutable
policy globals with temporary fixtures and every proxied helper synchronizes
those values before entering the implementation module.
"""

from __future__ import annotations

import functools
import importlib.util
import inspect
from pathlib import Path
import sys
from typing import Any, Callable

_IMPL_PATH = Path(__file__).with_name("_validate_governance_integrity_impl.py")
_SPEC = importlib.util.spec_from_file_location(
    "_trillionnium_validate_governance_integrity_impl", _IMPL_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load governance validator implementation: {_IMPL_PATH}")
_impl = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _impl
_SPEC.loader.exec_module(_impl)

_ADDITIONAL_WORKFLOWS = (
    ".github/workflows/d3-semantic-resolver-reference.yml",
    ".github/workflows/d3-integrated-runtime-evidence.yml",
)
_already_registered_workflows = sorted(
    set(_ADDITIONAL_WORKFLOWS).intersection(_impl.EXPECTED_REQUIRED_WORKFLOWS)
)
if _already_registered_workflows:
    raise RuntimeError(
        "facade workflows are already registered upstream: "
        + ", ".join(_already_registered_workflows)
    )
_impl.EXPECTED_REQUIRED_WORKFLOWS = (
    *_impl.EXPECTED_REQUIRED_WORKFLOWS[:12],
    *_ADDITIONAL_WORKFLOWS,
    *_impl.EXPECTED_REQUIRED_WORKFLOWS[12:],
)

_ADDITIONAL_REVIEWED_LOCAL_SCRIPTS = {
    "tools/semantic_resolver_reference.py",
    "tests/d3/test_semantic_resolver_reference.py",
    "tools/validate_module_documentation.py",
    "tools/verify_d3_integrated_runtime_evidence.py",
    "tools/d3_integrated_runtime_common.py",
    "tools/d3_integrated_runtime_verify.py",
    "tools/d3_integrated_runtime_fixture.py",
    "tests/d3/test_d3_integrated_runtime_evidence.py",
    "tests/test_validator_loader_stability.py",
}
_already_registered = sorted(
    _ADDITIONAL_REVIEWED_LOCAL_SCRIPTS.intersection(_impl.REVIEWED_LOCAL_SCRIPTS)
)
if _already_registered:
    raise RuntimeError(
        "facade-reviewed local scripts are already registered upstream: "
        + ", ".join(_already_registered)
    )
_impl.REVIEWED_LOCAL_SCRIPTS = frozenset(
    {*_impl.REVIEWED_LOCAL_SCRIPTS, *_ADDITIONAL_REVIEWED_LOCAL_SCRIPTS}
)

_CANONICAL_ROOT = _impl.ROOT
_CANONICAL_WORKFLOW_ROOT = _impl.WORKFLOW_ROOT
_CANONICAL_CONTRACT_PATH = _impl.CONTRACT_PATH
_CANONICAL_EXPECTED_REQUIRED_WORKFLOWS = tuple(_impl.EXPECTED_REQUIRED_WORKFLOWS)
_CANONICAL_REVIEWED_LOCAL_SCRIPTS = frozenset(_impl.REVIEWED_LOCAL_SCRIPTS)
_MUTABLE_UPPERCASE_GLOBALS = tuple(
    name
    for name in vars(_impl)
    if name.isupper() and name not in {"ROOT", "WORKFLOW_ROOT", "CONTRACT_PATH"}
)


def _selected_path(name: str, canonical: Path, derived: Path, root: Path) -> Path:
    """Honor an explicit facade override or derive a path from an overridden root."""

    value = globals().get(name, canonical)
    selected = value if isinstance(value, Path) else Path(value)
    if root != _CANONICAL_ROOT and selected == canonical:
        return derived
    return selected


def _sync_globals() -> None:
    root_value = globals().get("ROOT", _CANONICAL_ROOT)
    root = root_value if isinstance(root_value, Path) else Path(root_value)
    _impl.ROOT = root
    _impl.WORKFLOW_ROOT = _selected_path(
        "WORKFLOW_ROOT",
        _CANONICAL_WORKFLOW_ROOT,
        root / ".github" / "workflows",
        root,
    )
    _impl.CONTRACT_PATH = _selected_path(
        "CONTRACT_PATH",
        _CANONICAL_CONTRACT_PATH,
        root / "contracts" / "repository-governance.v1.json",
        root,
    )
    for name in _MUTABLE_UPPERCASE_GLOBALS:
        if name in globals():
            setattr(_impl, name, globals()[name])


def _proxy(function: Callable[..., Any]) -> Callable[..., Any]:
    @functools.wraps(function)
    def invoke(*args: Any, **kwargs: Any) -> Any:
        _sync_globals()
        return function(*args, **kwargs)

    return invoke


_EXCLUDED_EXPORTS = {
    "__builtins__",
    "__cached__",
    "__file__",
    "__loader__",
    "__name__",
    "__package__",
    "__spec__",
}
for _name, _value in vars(_impl).items():
    if _name in _EXCLUDED_EXPORTS:
        continue
    if inspect.isfunction(_value) and _value.__module__ == _impl.__name__:
        globals()[_name] = _proxy(_value)
    else:
        globals()[_name] = _value

ROOT = _CANONICAL_ROOT
WORKFLOW_ROOT = _CANONICAL_WORKFLOW_ROOT
CONTRACT_PATH = _CANONICAL_CONTRACT_PATH
EXPECTED_REQUIRED_WORKFLOWS = _CANONICAL_EXPECTED_REQUIRED_WORKFLOWS
REVIEWED_LOCAL_SCRIPTS = _CANONICAL_REVIEWED_LOCAL_SCRIPTS


if __name__ == "__main__":
    raise SystemExit(main())
