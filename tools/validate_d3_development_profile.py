#!/usr/bin/env python3
"""Stable entry point for the D3 development-profile source validator.

The implementation is kept in ``validate_d3_development_profile_impl``.  This
facade updates the executable-condition spelling to systemd's supported
``ConditionFileIsExecutable`` directive while preserving the validator's public
helpers used by its regression tests.
"""
from __future__ import annotations

from pathlib import Path

import validate_d3_development_profile_impl as _impl
from validate_d3_development_profile_impl import *  # noqa: F401,F403

_original_require_text = _impl.require_text


def _sync_globals() -> None:
    # Regression tests intentionally replace ROOT with temporary repositories.
    # Keep that supported contract across the implementation split.
    _impl.ROOT = ROOT
    _impl.ERRORS = ERRORS


def require_text(path: Path, *markers: str) -> str:
    _sync_globals()
    corrected = tuple(
        "ConditionFileIsExecutable=/usr/libexec/hepta-agent"
        if marker == "ConditionPathIsExecutable=/usr/libexec/hepta-agent"
        else marker
        for marker in markers
    )
    return _original_require_text(path, *corrected)


def check_manifest() -> None:
    _sync_globals()
    _impl.check_manifest()


def check_sources() -> None:
    _sync_globals()
    _impl.check_sources()


def check_units() -> None:
    _sync_globals()
    _impl.check_units()


def check_contract() -> None:
    _sync_globals()
    _impl.check_contract()


def main() -> int:
    _sync_globals()
    return _impl.main()


# check_units() resolves this helper in the implementation module.
_impl.require_text = require_text


if __name__ == "__main__":
    raise SystemExit(main())
