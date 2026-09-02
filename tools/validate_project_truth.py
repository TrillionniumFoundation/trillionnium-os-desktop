#!/usr/bin/env python3
"""Stable facade for the canonical project-truth validator.

The reviewed implementation is imported as Python code without rewriting its
source text.  Candidate-supersession policy that changed after the historical
implementation was frozen is expressed below as ordinary, reviewable Python
functions and constants.  No ``exec``, ``compile`` or source-string replacement
is used.
"""

from __future__ import annotations

import functools
import importlib.util
import inspect
from pathlib import Path
import sys
from typing import Any, Callable

_IMPL_PATH = Path(__file__).with_name("_validate_project_truth_impl.py")
_SPEC = importlib.util.spec_from_file_location(
    "_trillionnium_validate_project_truth_impl", _IMPL_PATH
)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"cannot load project-truth validator implementation: {_IMPL_PATH}")
_impl = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _impl
_SPEC.loader.exec_module(_impl)

D0A02_SUPERSEDED_BY_PR = 60
D0A02_STALE_REASON = (
    "D0A-02 headed-host evidence is bound to historical source head "
    f"{_impl.D0A02_HISTORICAL_HEAD}; PR #60 supersedes the PR #33 candidate "
    "and this snapshot. Rerun servo-headed-runtime on the exact candidate "
    "head for PR #60 before promotion."
)
_impl.D0A02_STALE_REASON = D0A02_STALE_REASON
_impl.D0A02_SUPERSEDED_BY_PR = D0A02_SUPERSEDED_BY_PR


def _check_d0a02_stale_record(record: object, label: str) -> None:
    """Require historical D0A-02 evidence to advertise PR-60 staleness."""

    if not isinstance(record, dict):
        _impl.fail(f"{label} must be an object")
        return
    if record.get("evidence_lifecycle") != _impl.D0A02_EVIDENCE_LIFECYCLE:
        _impl.fail(
            f"{label}.evidence_lifecycle must be "
            f"{_impl.D0A02_EVIDENCE_LIFECYCLE!r}"
        )
    if record.get("stale_reason") != D0A02_STALE_REASON:
        _impl.fail(
            f"{label}.stale_reason must equal the canonical PR #60 exact-head rerun reason"
        )
    promotion = record.get("promotion")
    if not isinstance(promotion, dict):
        _impl.fail(f"{label}.promotion must be an object with stale merge state")
        return
    if promotion.get("evidence_freshness") != "STALE_EVIDENCE":
        _impl.fail(f"{label}.promotion.evidence_freshness must be 'STALE_EVIDENCE'")
    if promotion.get("merge_ready") is not False:
        _impl.fail(f"{label}.promotion.merge_ready must be false for stale evidence")
    if promotion.get("superseded_by_pr") != D0A02_SUPERSEDED_BY_PR:
        _impl.fail(
            f"{label}.promotion.superseded_by_pr must be PR #{D0A02_SUPERSEDED_BY_PR}"
        )
    if promotion.get("stale_reason") != D0A02_STALE_REASON:
        _impl.fail(
            f"{label}.promotion.stale_reason must equal the canonical exact-head rerun reason"
        )


def check_d0a02_evidence_lifecycle(
    project: dict[str, Any], docs: dict[str, Any], repository: dict[str, Any]
) -> None:
    """Synchronize historical evidence with the active PR-60 D0A-02 claim."""

    for relative in (
        "docs/evidence/generated/d0a02-headed-runtime-evidence.json",
        "docs/evidence/generated/d0a02-headed-runtime-result.json",
    ):
        _check_d0a02_stale_record(_impl.load_json(relative), relative)

    repository_entries = repository.get("qualification_work_packages")
    if not isinstance(repository_entries, list):
        _impl.fail("repository-state qualification_work_packages must be a list")
    else:
        matches = [
            entry
            for entry in repository_entries
            if isinstance(entry, dict) and entry.get("id") == "D0A-02"
        ]
        if len(matches) != 1:
            _impl.fail(
                "repository-state must contain exactly one D0A-02 qualification evidence entry"
            )
        else:
            entry = matches[0]
            if entry.get("evidence_lifecycle") != _impl.D0A02_EVIDENCE_LIFECYCLE:
                _impl.fail("repository-state D0A-02 evidence lifecycle is not stale")
            if entry.get("merge_ready") is not False:
                _impl.fail("repository-state D0A-02 evidence must not be merge-ready")
            if entry.get("superseded_by_pr") != D0A02_SUPERSEDED_BY_PR:
                _impl.fail("repository-state D0A-02 evidence must retain PR #60 supersession")
            if entry.get("stale_reason") != D0A02_STALE_REASON:
                _impl.fail(
                    "repository-state D0A-02 entry lacks the canonical exact-head rerun reason"
                )

    checkpoint_entries = docs.get("implementation_checkpoints")
    if not isinstance(checkpoint_entries, list):
        _impl.fail("docs manifest implementation_checkpoints must be a list")
    else:
        matches = [
            entry
            for entry in checkpoint_entries
            if isinstance(entry, dict) and entry.get("id") == "TOS-D0A-02"
        ]
        if len(matches) != 1:
            _impl.fail("docs manifest must contain exactly one TOS-D0A-02 checkpoint")
        else:
            entry = matches[0]
            if entry.get("evidence_lifecycle") != _impl.D0A02_EVIDENCE_LIFECYCLE:
                _impl.fail("docs manifest D0A-02 evidence lifecycle is not stale")
            if entry.get("merge_ready") is not False:
                _impl.fail("docs manifest D0A-02 evidence must not be merge-ready")
            if entry.get("superseded_by_pr") != D0A02_SUPERSEDED_BY_PR:
                _impl.fail("docs manifest D0A-02 evidence must retain PR #60 supersession")
            if entry.get("stale_reason") != D0A02_STALE_REASON:
                _impl.fail(
                    "docs manifest D0A-02 entry lacks the canonical exact-head rerun reason"
                )

    candidates = project.get("source_candidate_work_packages")
    active = (
        [
            entry
            for entry in candidates
            if isinstance(entry, dict) and entry.get("id") == "D0A-02"
        ]
        if isinstance(candidates, list)
        else []
    )
    if len(active) != 1:
        _impl.fail("project-state must contain exactly one active D0A-02 source candidate")
    else:
        candidate = active[0]
        if candidate.get("pr") != D0A02_SUPERSEDED_BY_PR:
            _impl.fail("active D0A-02 source candidate must be bound to PR #60")
        if candidate.get("status") != "MODULE_CLOSED_CANDIDATE":
            _impl.fail("active PR #60 D0A-02 candidate must retain MODULE_CLOSED_CANDIDATE status")
        claim = candidate.get("claim_ceiling")
        if not isinstance(claim, str) or not claim.startswith(
            "headed_host_local_fixture_only"
        ):
            _impl.fail(
                "active D0A-02 candidate claim ceiling must remain headed-host/local-fixture-only"
            )


# Install the explicit policy functions into the implementation namespace so
# calls originating inside implementation functions resolve the same reviewed
# definitions as direct facade calls.
_impl._check_d0a02_stale_record = _check_d0a02_stale_record
_impl.check_d0a02_evidence_lifecycle = check_d0a02_evidence_lifecycle

_CANONICAL_ROOT = _impl.ROOT
_MUTABLE_UPPERCASE_GLOBALS = tuple(
    name for name in vars(_impl) if name.isupper() and name != "ROOT"
)


def _sync_globals() -> None:
    root_value = globals().get("ROOT", _CANONICAL_ROOT)
    _impl.ROOT = root_value if isinstance(root_value, Path) else Path(root_value)
    for name in _MUTABLE_UPPERCASE_GLOBALS:
        if name in globals():
            setattr(_impl, name, globals()[name])
    _impl.D0A02_STALE_REASON = D0A02_STALE_REASON
    _impl.D0A02_SUPERSEDED_BY_PR = D0A02_SUPERSEDED_BY_PR
    _impl._check_d0a02_stale_record = _check_d0a02_stale_record
    _impl.check_d0a02_evidence_lifecycle = check_d0a02_evidence_lifecycle


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
    if inspect.isfunction(_value) and _value.__module__ in {_impl.__name__, __name__}:
        globals()[_name] = _proxy(_value)
    else:
        globals()[_name] = _value

ROOT = _CANONICAL_ROOT
D0A02_STALE_REASON = D0A02_STALE_REASON
D0A02_SUPERSEDED_BY_PR = D0A02_SUPERSEDED_BY_PR


if __name__ == "__main__":
    raise SystemExit(main())
