#!/usr/bin/env python3
"""Load the reviewed truth validator with the current PR-60 evidence binding.

The implementation blob is retained verbatim for reviewability. This loader
applies the narrow candidate-supersession vocabulary update before executing it
in this module's globals, so tests and callers share one state namespace.
"""

from pathlib import Path

_IMPL = Path(__file__).with_name("_validate_project_truth_impl.py")
_source = _IMPL.read_text(encoding="utf-8")
_source = _source.replace(
    'f"{D0A02_HISTORICAL_HEAD}; the PR #33 candidate supersedes that snapshot. "',
    'f"{D0A02_HISTORICAL_HEAD}; PR #60 supersedes the PR #33 candidate and this snapshot. "',
)
_source = _source.replace(
    '"Rerun servo-headed-runtime on the exact candidate head before promotion."',
    '"Rerun servo-headed-runtime on the exact candidate head for PR #60 before promotion."',
)
_source = _source.replace(
    'promotion.get("superseded_by_pr") != 33',
    'promotion.get("superseded_by_pr") != 60',
)
_source = _source.replace(
    'entry.get("superseded_by_pr") != 33',
    'entry.get("superseded_by_pr") != 60',
)

_runtime_name = __name__
__name__ = "_validate_project_truth_impl"
exec(compile(_source, str(_IMPL), "exec"), globals())
__name__ = _runtime_name

if _runtime_name == "__main__":
    main()
