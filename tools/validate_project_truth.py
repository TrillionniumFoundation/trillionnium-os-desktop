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
from datetime import datetime
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

D0A02_SUPERSEDED_BY_PR = 66
D0A02_STALE_REASON = (
    "D0A-02 headed-host evidence is bound to historical source head "
    f"{_impl.D0A02_HISTORICAL_HEAD}; PR #66 supersedes the PR #60 and PR #33 "
    "convergence candidates and this snapshot. Rerun servo-headed-runtime on "
    "the exact candidate head for PR #66 before promotion."
)
_impl.D0A02_STALE_REASON = D0A02_STALE_REASON
_impl.D0A02_SUPERSEDED_BY_PR = D0A02_SUPERSEDED_BY_PR

D3_DEVELOPMENT_BLOCKER = (
    "Servo-owned retained-node semantic action forwarding, exact integrated-image "
    "principal/dispatch/receipt evidence, and independent security review remain "
    "required before live activation"
)
D3_ACTIVATION_TRUTH = dict(_impl.D3_ACTIVATION_TRUTH)
D3_ACTIVATION_TRUTH["development_blocker"] = D3_DEVELOPMENT_BLOCKER
_impl.D3_ACTIVATION_TRUTH = D3_ACTIVATION_TRUTH

CANDIDATE_SNAPSHOT_SOURCE = "github_api_committed_snapshot_before_truth_refresh"
CANDIDATE_SNAPSHOT_FIELDS = {
    "observed_at",
    "observed_main_sha",
    "observed_candidate_pr",
    "observed_candidate_branch",
    "observed_candidate_head_sha",
    "observed_candidate_tree_sha",
    "source",
    "live_pr_or_ci_state_must_be_read_from_github",
}


def candidate_snapshot_alignment_errors(
    project: object,
    docs: object,
    repository: object,
) -> list[str]:
    """Reject copied snapshot drift and stale active-candidate bindings."""

    errors: list[str] = []
    projections = {
        "project-state": project,
        "docs manifest": docs,
        "repository-state": repository,
    }
    snapshots: dict[str, dict[str, Any]] = {}
    for label, projection in projections.items():
        if not isinstance(projection, dict):
            errors.append(f"{label} must be an object for candidate snapshot checks")
            continue
        snapshot = projection.get("candidate_state_snapshot")
        if not isinstance(snapshot, dict):
            errors.append(f"{label} candidate_state_snapshot must be an object")
            continue
        snapshots[label] = snapshot

    project_snapshot = snapshots.get("project-state")
    if project_snapshot is None:
        return errors

    for label in ("docs manifest", "repository-state"):
        snapshot = snapshots.get(label)
        if snapshot is not None and snapshot != project_snapshot:
            errors.append(
                f"{label} candidate_state_snapshot disagrees with project-state"
            )

    missing = sorted(CANDIDATE_SNAPSHOT_FIELDS - set(project_snapshot))
    unknown = sorted(set(project_snapshot) - CANDIDATE_SNAPSHOT_FIELDS)
    if missing:
        errors.append(f"candidate_state_snapshot is missing required fields: {missing}")
    if unknown:
        errors.append(f"candidate_state_snapshot has unknown fields: {unknown}")

    observed_at = project_snapshot.get("observed_at")
    if not isinstance(observed_at, str):
        errors.append("candidate_state_snapshot.observed_at must be a UTC timestamp")
    else:
        try:
            datetime.strptime(observed_at, "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            errors.append(
                "candidate_state_snapshot.observed_at must use YYYY-MM-DDTHH:MM:SSZ"
            )

    for field in (
        "observed_main_sha",
        "observed_candidate_head_sha",
        "observed_candidate_tree_sha",
    ):
        value = project_snapshot.get(field)
        if (
            not isinstance(value, str)
            or _impl.SHA40.fullmatch(value) is None
            or set(value) == {"0"}
        ):
            errors.append(
                f"candidate_state_snapshot.{field} is not a lowercase 40-hex SHA"
            )

    observed_pr = project_snapshot.get("observed_candidate_pr")
    if (
        not isinstance(observed_pr, int)
        or isinstance(observed_pr, bool)
        or not 1 <= observed_pr <= 2_000_000_000
    ):
        errors.append("candidate_state_snapshot.observed_candidate_pr is invalid")

    observed_branch = project_snapshot.get("observed_candidate_branch")
    if (
        not isinstance(observed_branch, str)
        or _impl.BRANCH_NAME.fullmatch(observed_branch) is None
        or ".." in observed_branch
        or "//" in observed_branch
        or observed_branch.endswith(("/", "."))
        or any(segment.startswith(".") for segment in observed_branch.split("/"))
    ):
        errors.append(
            "candidate_state_snapshot.observed_candidate_branch is unsafe or malformed"
        )

    if project_snapshot.get("source") != CANDIDATE_SNAPSHOT_SOURCE:
        errors.append(
            "candidate_state_snapshot.source must identify the GitHub API "
            "pre-truth-refresh snapshot"
        )
    if project_snapshot.get("live_pr_or_ci_state_must_be_read_from_github") is not True:
        errors.append(
            "candidate_state_snapshot must require live PR/CI state to be read from GitHub"
        )

    candidates = (
        project.get("source_candidate_work_packages")
        if isinstance(project, dict)
        else None
    )
    if not isinstance(candidates, list) or not candidates:
        errors.append(
            "project-state source_candidate_work_packages must be a non-empty "
            "list for snapshot alignment"
        )
        return errors

    expected = {
        "branch": project_snapshot.get("observed_candidate_branch"),
        "pr": project_snapshot.get("observed_candidate_pr"),
        "base_sha": project_snapshot.get("observed_main_sha"),
        "candidate_head_sha": project_snapshot.get("observed_candidate_head_sha"),
    }
    for index, candidate in enumerate(candidates):
        if not isinstance(candidate, dict):
            continue
        package = candidate.get("id", f"index {index}")
        for field, expected_value in expected.items():
            if candidate.get(field) != expected_value:
                errors.append(
                    f"active candidate {package!r} {field} disagrees with "
                    "candidate_state_snapshot"
                )
    return errors


_ORIGINAL_CHECK_TRUTH_ALIGNMENT = _impl.check_truth_alignment


def check_truth_alignment() -> None:
    """Run frozen truth checks plus current PR-66 snapshot policy."""

    _ORIGINAL_CHECK_TRUTH_ALIGNMENT()
    project = _impl.load_json("manifests/project-state.v1.json")
    docs = _impl.load_json("docs/MANIFEST.json")
    repository = _impl.load_json("manifests/repository-state.json")
    for error in candidate_snapshot_alignment_errors(project, docs, repository):
        _impl.fail(error)
    _impl.require_text(
        "docs/CURRENT_STATE.md",
        [_impl.PLAN_REVISION, _impl.INTEGRATED_STAGE, "PR #66"],
    )
    _impl.require_text(
        "README.md",
        [_impl.PLAN_REVISION, _impl.INTEGRATED_STAGE, "PR **#66**"],
    )


def _check_d0a02_stale_record(record: object, label: str) -> None:
    """Require historical D0A-02 evidence to advertise PR-66 staleness."""

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
            f"{label}.stale_reason must equal the canonical PR #66 exact-head rerun reason"
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
    """Synchronize historical evidence with the active PR-66 D0A-02 claim."""

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
                _impl.fail("repository-state D0A-02 evidence must retain PR #66 supersession")
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
                _impl.fail("docs manifest D0A-02 evidence must retain PR #66 supersession")
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
            _impl.fail("active D0A-02 source candidate must be bound to PR #66")
        if candidate.get("status") != "MODULE_CLOSED_CANDIDATE":
            _impl.fail("active PR #66 D0A-02 candidate must retain MODULE_CLOSED_CANDIDATE status")
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
_impl.check_truth_alignment = check_truth_alignment

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
    _impl.D3_ACTIVATION_TRUTH = D3_ACTIVATION_TRUTH
    _impl._check_d0a02_stale_record = _check_d0a02_stale_record
    _impl.check_d0a02_evidence_lifecycle = check_d0a02_evidence_lifecycle
    _impl.check_truth_alignment = check_truth_alignment


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
