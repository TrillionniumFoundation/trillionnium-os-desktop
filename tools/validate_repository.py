#!/usr/bin/env python3
"""Stable facade for repository validation with closed successor registration.

The integrated validator is retained byte-for-byte in
``_validate_repository_impl.py``. This facade may append only explicitly
reviewed source-only workspace members and their required inventory. Missing or
partially added candidates therefore fail closed; arbitrary Cargo members are
never accepted.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys

_IMPL_PATH = Path(__file__).with_name("_validate_repository_impl.py")
_SPEC = importlib.util.spec_from_file_location(
    "_trillionnium_validate_repository_impl", _IMPL_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load repository validator implementation: {_IMPL_PATH}")
_impl = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _impl
_SPEC.loader.exec_module(_impl)

_CANDIDATES: dict[str, tuple[str, ...]] = {
    "crates/hepta-browser-actor": (
        "crates/hepta-browser-actor/Cargo.toml",
        "crates/hepta-browser-actor/README.md",
        "crates/hepta-browser-actor/src/lib.rs",
        "contracts/browser-actor.v1.json",
        "contracts/engine-thread-dispatch.v1.json",
        "contracts/event-loop-completion.v1.json",
        "contracts/session-incarnation.v1.json",
        "docs/architecture/BROWSER_ACTOR_AUTHORITY_BOUNDARY.md",
        "tests/test_s06_browser_actor.py",
        ".github/workflows/s06-browser-actor.yml",
    ),
    "crates/hepta-browser-actor-simulation": (
        "crates/hepta-browser-actor-simulation/Cargo.toml",
        "crates/hepta-browser-actor-simulation/README.md",
        "crates/hepta-browser-actor-simulation/src/lib.rs",
    ),
}

for member, required_paths in _CANDIDATES.items():
    manifest = _impl.ROOT / member / "Cargo.toml"
    if not manifest.is_file():
        continue
    if member in _impl.EXPECTED_WORKSPACE_MEMBERS:
        raise RuntimeError(f"candidate workspace member registered twice: {member}")
    _impl.EXPECTED_WORKSPACE_MEMBERS = [*_impl.EXPECTED_WORKSPACE_MEMBERS, member]
    _impl.REQUIRED_PATHS = [*_impl.REQUIRED_PATHS, *required_paths]

for _name in dir(_impl):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_impl, _name)


if __name__ == "__main__":
    raise SystemExit(_impl.main())
