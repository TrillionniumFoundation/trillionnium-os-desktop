#!/usr/bin/env python3
"""D0A evidence facade supporting non-authoritative stacked PR identities.

The detailed envelope implementation remains in
``qualify_servo_exact_pin_evidence_impl``. This entry point validates the
stacked synthetic-merge identity emitted by the preceding Git topology step,
then normalizes it to the generic envelope's stable
``pr_synthetic_merge`` role. The exact stacked base remains bound by
``BASE_SHA``; the evidence stays non-authoritative and carries no
integrated-main SHA.
"""
from __future__ import annotations

import os
from pathlib import Path
import sys

TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

import qualify_servo_exact_pin_evidence_impl as _impl
from qualify_servo_exact_pin_evidence_impl import *  # noqa: F401,F403

_original_validate = _impl.validate_identity_environment


def identity_from_environment() -> dict[str, str]:
    names = (
        "EVENT_NAME",
        "SOURCE_REF",
        "SOURCE_REF_NAME",
        "CURRENT_MAIN_SHA",
        "TESTED_SHA",
        "TESTED_TREE_SHA",
        "BASE_SHA",
        "CANDIDATE_HEAD_SHA",
        "TESTED_MERGE_SHA",
        "INTEGRATED_MAIN_SHA",
        "EVIDENCE_ROLE",
        "PROMOTION_AUTHORITATIVE",
    )
    return {name: os.environ.get(name, "") for name in names}


def validate_identity_environment(identity: dict[str, str]) -> dict[str, str]:
    role = identity.get("EVIDENCE_ROLE", "")
    if role != "stacked_pr_synthetic_merge":
        return _original_validate(identity)

    event = _impl._require_identity_text(identity, "EVENT_NAME")
    source_ref = _impl._require_identity_text(identity, "SOURCE_REF")
    source_ref_name = _impl._require_identity_text(identity, "SOURCE_REF_NAME")
    current_main_sha = _impl._require_identity_sha(identity, "CURRENT_MAIN_SHA")
    for name in (
        "TESTED_SHA",
        "TESTED_TREE_SHA",
        "BASE_SHA",
        "CANDIDATE_HEAD_SHA",
    ):
        _impl._require_identity_sha(identity, name)
    tested_sha = identity["TESTED_SHA"]
    tested_merge_sha = _impl._optional_identity_sha(identity, "TESTED_MERGE_SHA")
    integrated_main_sha = _impl._optional_identity_sha(identity, "INTEGRATED_MAIN_SHA")
    authoritative = _impl._require_identity_text(identity, "PROMOTION_AUTHORITATIVE")
    match = _impl.PR_REF_RE.fullmatch(source_ref)
    if (
        event != "pull_request"
        or match is None
        or _impl.PR_REF_NAME_RE.fullmatch(source_ref_name) is None
        or source_ref_name != f"{match.group(1)}/merge"
        or authoritative != "false"
        or not tested_merge_sha
        or tested_merge_sha != tested_sha
        or integrated_main_sha
        or identity["BASE_SHA"] == current_main_sha
    ):
        raise ValueError("D0A-01 stacked pull-request identity tuple is inconsistent")

    # The generic evidence schema intentionally has one non-authoritative PR
    # role. Stacked ancestry and exact parent order were already established by
    # qualify_servo_exact_pin_identity.py; BASE_SHA preserves the reviewed
    # stacked base. Normalize only the role vocabulary used by the envelope.
    normalized = dict(identity)
    normalized["EVIDENCE_ROLE"] = "pr_synthetic_merge"
    return normalized


_impl.identity_from_environment = identity_from_environment
_impl.validate_identity_environment = validate_identity_environment


if __name__ == "__main__":
    try:
        raise SystemExit(_impl.main())
    except Exception as error:  # noqa: BLE001 - fail-closed CLI boundary
        print(f"D0A-01 evidence envelope failed: {error}", file=__import__("sys").stderr)
        raise
