#!/usr/bin/env python3
"""Stable facade for the strict governance validator.

The reviewed implementation remains in ``_validate_governance_integrity_impl``.
This facade registers the D3 semantic-resolver workflow and its executable
source inputs without weakening the exact workflow inventory or read-only
workflow policy.  It also preserves the validator's test contract: regression
tests may replace ``ROOT`` with a temporary repository and every proxied helper
will synchronize that root before entering the implementation module.
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


def _sync_globals() -> None:
    root = globals().get("ROOT", _impl.ROOT)
    if not isinstance(root, Path):
        root = Path(root)
    _impl.ROOT = root
    _impl.WORKFLOW_ROOT = root / ".github" / "workflows"
    _impl.CONTRACT_PATH = root / "contracts" / "repository-governance.v1.json"


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

# Mutable compatibility globals intentionally live in the facade.  The proxy
# synchronizes them into the implementation before every externally invoked
# helper, matching the historical single-module behavior used by tests.
ROOT = _impl.ROOT
WORKFLOW_ROOT = _impl.WORKFLOW_ROOT
CONTRACT_PATH = _impl.CONTRACT_PATH


if __name__ == "__main__":
    raise SystemExit(main())
