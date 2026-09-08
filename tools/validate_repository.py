#!/usr/bin/env python3
"""Stable facade for the repository consistency validator.

The integrated validator remains byte-identical in ``_validate_repository_impl``.
Successor slices may register only the explicitly enumerated candidate crates
below; each candidate also adds its exact source/contract/test inventory to the
required-file gate. No arbitrary workspace member is accepted.
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
        "crates/hepta-browser-actor/src/lib.rs",
        "contracts/browser-actor.v1.json",
        "contracts/engine-thread-dispatch.v1.json",
        "contracts/event-loop-completion.v1.json",
        "contracts/session-incarnation.v1.json",
        "tests/test_s06_browser_actor.py",
        ".github/workflows/s06-browser-actor.yml",
    ),
    "crates/hepta-d3-development": (
        "crates/hepta-d3-development/Cargo.toml",
        "crates/hepta-d3-development/src/lib.rs",
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

# Re-export the implementation API. Functions retain the implementation module
# as their global namespace, including its fail-closed mutable error ledger.
for _name in dir(_impl):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_impl, _name)


if __name__ == "__main__":
    raise SystemExit(_impl.main())
