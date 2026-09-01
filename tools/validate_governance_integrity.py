#!/usr/bin/env python3
"""Stable facade for the strict governance validator.

The reviewed implementation remains in ``_validate_governance_integrity_impl``.
This facade registers the D3 semantic-resolver workflow and its executable
source inputs without weakening the exact workflow inventory or read-only
workflow policy. It also preserves the validator's historical test contract:
regression tests may replace mutable policy globals with temporary fixtures and
every proxied helper synchronizes those values before entering the
implementation module.
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

_D3_WORKFLOW = ".github/workflows/d3-semantic-resolver-reference.yml"
if _D3_WORKFLOW in _impl.EXPECTED_REQUIRED_WORKFLOWS:
    raise RuntimeError("D3 semantic-resolver workflow is already registered upstream")
_impl.EXPECTED_REQUIRED_WORKFLOWS = (
    *_impl.EXPECTED_REQUIRED_WORKFLOWS[:12],
    _D3_WORKFLOW,
    *_impl.EXPECTED_REQUIRED_WORKFLOWS[12:],
)
_impl.REVIEWED_LOCAL_SCRIPTS = frozenset(
    {
        *_impl.REVIEWED_LOCAL_SCRIPTS,
        "tools/semantic_resolver_reference.py",
        "tests/d3/test_semantic_resolver_reference.py",
    }
)

_CANONICAL_ROOT = _impl.ROOT
_CANONICAL_WORKFLOW_ROOT = _impl.WORKFLOW_ROOT
_CANONICAL_CONTRACT_PATH = _impl.CONTRACT_PATH
_CANONICAL_EXPECTED_REQUIRED_WORKFLOWS = tuple(_impl.EXPECTED_REQUIRED_WORKFLOWS)
_CANONICAL_REVIEWED_LOCAL_SCRIPTS = frozenset(_impl.REVIEWED_LOCAL_SCRIPTS)
_MUTABLE_UPPERCASE_GLOBALS = tuple(
    name
    for name in vars(_impl)
    if name.isupper()
    and name not in {"ROOT", "WORKFLOW_ROOT", "CONTRACT_PATH"}
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

    # The original single-module validator exposed its policy constants as
    # mutable module globals. Several adversarial regression tests deliberately
    # replace those constants to build tiny fixture repositories. Mirror every
    # uppercase implementation global so the facade remains behaviorally
    # equivalent instead of silently restoring the production registry.
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
