#!/usr/bin/env python3
"""Stable facade for the D0T-03 source-contract validator.

The complete reviewed implementation remains in
``_validate_d0t03_source_impl``.  This facade extends its exact required-
workflow registry with the D3 semantic-resolver reference gate while retaining
the implementation's strict path, CODEOWNERS, workflow, and claim-ceiling
checks.
"""

from __future__ import annotations

import functools
import importlib.util
import inspect
from pathlib import Path
import sys
from typing import Any, Callable

_IMPL_PATH = Path(__file__).with_name("_validate_d0t03_source_impl.py")
_SPEC = importlib.util.spec_from_file_location(
    "_trillionnium_validate_d0t03_source_impl", _IMPL_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load D0T-03 validator implementation: {_IMPL_PATH}")
_impl = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _impl
_SPEC.loader.exec_module(_impl)

_D3_WORKFLOW = ".github/workflows/d3-semantic-resolver-reference.yml"
if _D3_WORKFLOW in _impl.EXPECTED_REQUIRED_WORKFLOW_REGISTRY:
    raise RuntimeError("D3 semantic-resolver workflow is already registered upstream")
_impl.EXPECTED_REQUIRED_WORKFLOW_REGISTRY = frozenset(
    {*_impl.EXPECTED_REQUIRED_WORKFLOW_REGISTRY, _D3_WORKFLOW}
)


def _sync_globals() -> None:
    root = globals().get("ROOT", _impl.ROOT)
    if not isinstance(root, Path):
        root = Path(root)
    _impl.ROOT = root
    _impl.MANIFEST = Path(
        globals().get("MANIFEST", root / "manifests/repository-governance.v1.json")
    )
    _impl.CODEOWNERS = Path(globals().get("CODEOWNERS", root / ".github/CODEOWNERS"))
    _impl.WORKFLOW = Path(
        globals().get(
            "WORKFLOW", root / ".github/workflows/d0t03-source-contract.yml"
        )
    )


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

ROOT = _impl.ROOT
MANIFEST = _impl.MANIFEST
CODEOWNERS = _impl.CODEOWNERS
WORKFLOW = _impl.WORKFLOW
EXPECTED_REQUIRED_WORKFLOW_REGISTRY = _impl.EXPECTED_REQUIRED_WORKFLOW_REGISTRY


if __name__ == "__main__":
    raise SystemExit(main())
