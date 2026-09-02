#!/usr/bin/env python3
"""Stable facade for the repository consistency validator.

The reviewed validator implementation remains in
``_validate_repository_impl``. This facade extends the exact workspace and
required-path registries for the isolated D3 development and evidence-verifier
packages without weakening dependency, path, lock, evidence, or claim checks.
Mutable module globals remain compatible with the adversarial test fixtures
used by the original single-file implementation.
"""

from __future__ import annotations

import functools
import importlib.util
import inspect
from pathlib import Path
import sys
from typing import Any, Callable

_IMPL_PATH = Path(__file__).with_name("_validate_repository_impl.py")
_SPEC = importlib.util.spec_from_file_location(
    "_trillionnium_validate_repository_impl", _IMPL_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load repository validator implementation: {_IMPL_PATH}")
_impl = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _impl
_SPEC.loader.exec_module(_impl)

_D3_MEMBER = "crates/hepta-d3-development"
if _D3_MEMBER in _impl.EXPECTED_WORKSPACE_MEMBERS:
    raise RuntimeError("D3 persistent development package is already registered upstream")
_impl.EXPECTED_WORKSPACE_MEMBERS = [*_impl.EXPECTED_WORKSPACE_MEMBERS, _D3_MEMBER]
_impl.REQUIRED_PATHS = [
    *_impl.REQUIRED_PATHS,
    "crates/hepta-d3-development/Cargo.toml",
    "crates/hepta-d3-development/src/lib.rs",
    "crates/hepta-d3-development/src/bin/sessiond.rs",
    "crates/hepta-d3-development/src/sessiond/activation.rs",
    "crates/hepta-d3-development/src/sessiond/runtime.rs",
    "crates/hepta-d3-development/src/sessiond/service.rs",
    "crates/hepta-d3-development/src/sessiond/storage.rs",
    "crates/hepta-d3-development/src/bin/fixture.rs",
    "crates/hepta-d3-development/src/fixture/client.rs",
    "crates/hepta-d3-development/src/fixture/corpus.rs",
    "crates/hepta-d3-development/src/fixture/model.rs",
    "crates/hepta-d3-development/src/bin/journal_check.rs",
    "packaging/debian/systemd/hepta-browserd-agent-development.socket",
    "packaging/debian/systemd/hepta-browserd-agent-development.service",
    "tools/validate_d3_development_profile.py",
    "tools/_validate_d3_development_profile_impl.py",
    "tests/test_validate_d3_development_profile.py",
    ".github/workflows/d3-integrated-runtime-evidence.yml",
    "contracts/d3-integrated-runtime-evidence.v1.json",
    "docs/architecture/D3_INTEGRATED_RUNTIME_QUALIFICATION.md",
    "tools/verify_d3_integrated_runtime_evidence.py",
    "tools/d3_integrated_runtime_common.py",
    "tools/d3_integrated_runtime_verify.py",
    "tools/d3_integrated_runtime_fixture.py",
    "tests/d3/test_d3_integrated_runtime_evidence.py",
    "tests/test_validator_loader_stability.py",
]

_CANONICAL_ROOT = _impl.ROOT
_CANONICAL_EXPECTED_WORKSPACE_MEMBERS = list(_impl.EXPECTED_WORKSPACE_MEMBERS)
_CANONICAL_REQUIRED_PATHS = list(_impl.REQUIRED_PATHS)
_MUTABLE_UPPERCASE_GLOBALS = tuple(
    name for name in vars(_impl) if name.isupper() and name != "ROOT"
)


def _sync_globals() -> None:
    root_value = globals().get("ROOT", _CANONICAL_ROOT)
    _impl.ROOT = root_value if isinstance(root_value, Path) else Path(root_value)
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
EXPECTED_WORKSPACE_MEMBERS = _CANONICAL_EXPECTED_WORKSPACE_MEMBERS
REQUIRED_PATHS = _CANONICAL_REQUIRED_PATHS


if __name__ == "__main__":
    raise SystemExit(main())
