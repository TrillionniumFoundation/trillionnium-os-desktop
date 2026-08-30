#!/usr/bin/env python3
"""Validate the source-controlled half of D0T-03 without fabricating settings."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests/repository-governance.v1.json"
CODEOWNERS = ROOT / ".github/CODEOWNERS"
WORKFLOW = ROOT / ".github/workflows/d0t03-source-contract.yml"
SHA = re.compile(r"^[0-9a-f]{40}$")


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("schema") != "trillionnium.desktop.repository-governance.v1":
        fail("unexpected governance schema")
    if data.get("work_package") != "D0T-03":
        fail("governance manifest is not bound to D0T-03")
    if data.get("status") != "SOURCE_BOOTSTRAP_READY_REPOSITORY_SETTINGS_REQUIRED":
        fail("source contract must remain fail-closed on repository settings")

    review = data.get("source_review", {})
    owners = review.get("interim_codeowners", [])
    if len(owners) < 2 or len(set(owners)) != len(owners):
        fail("at least two distinct interim CODEOWNER identities are required")
    if review.get("minimum_distinct_approver_identities") != 2:
        fail("minimum approval count must be exactly two")
    if review.get("organization_team_codeowners_required_for_closure") is not True:
        fail("team CODEOWNERS must remain mandatory for final closure")
    for key in (
        "stale_approvals_dismissed_required",
        "approval_after_latest_push_required",
        "code_owner_review_required",
        "all_conversations_resolved_required",
    ):
        if review.get(key) is not True:
            fail(f"review control is not fail-closed: {key}")
    if review.get("author_self_approval_counts") is not False:
        fail("author self-approval must not count")
    if review.get("author_self_merge_allowed") is not False:
        fail("author self-merge must remain forbidden")

    text = CODEOWNERS.read_text(encoding="utf-8")
    for owner in owners:
        if f"@{owner}" not in text:
            fail(f"CODEOWNERS is missing @{owner}")
    active_lines = [
        line for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    if not active_lines or any(sum(part.startswith("@") for part in line.split()) < 2 for line in active_lines):
        fail("every active CODEOWNERS rule must name at least two identities")

    branch = data.get("main_branch", {})
    for key in (
        "pull_request_required",
        "strict_required_checks",
    ):
        if branch.get(key) is not True:
            fail(f"main branch requirement is disabled: {key}")
    for key in (
        "force_push_allowed",
        "deletion_allowed",
        "administrator_bypass_allowed",
    ):
        if branch.get(key) is not False:
            fail(f"main branch escape hatch is enabled: {key}")
    required_workflows = branch.get("required_workflows", [])
    if len(required_workflows) != len(set(required_workflows)) or not required_workflows:
        fail("required workflow registry is empty or duplicated")
    for relative in required_workflows:
        # D1/D2I are candidate workflows until their reviewed merges. Their
        # absence on the bootstrap base is allowed only when explicitly named.
        path = ROOT / relative
        if not path.is_file() and relative not in {
            ".github/workflows/d1-final-qualification.yml",
            ".github/workflows/d2i-integrated-image.yml",
        }:
            fail(f"required workflow is absent: {relative}")

    release = data.get("release", {})
    if release.get("protected_environment") != "production":
        fail("production protected environment name changed")
    if release.get("minimum_independent_approvers") != 2:
        fail("release approval count must be two")
    if release.get("source_author_may_approve_release") is not False:
        fail("source author may not approve the release")
    if release.get("signing_key_available_to_pull_request_workflows") is not False:
        fail("pull-request workflows must not receive signing keys")
    if release.get("signing_and_source_authority_separated") is not True:
        fail("signing and source authority are not separated")

    claims = data.get("current_claims", {})
    if not claims or any(value is not False for value in claims.values()):
        fail("source must not claim external settings or independent review")
    if data.get("claim_ceiling") != "source_contract_and_interim_two_identity_codeowners_only":
        fail("governance claim ceiling changed")

    workflow = WORKFLOW.read_text(encoding="utf-8")
    if "contents: read" not in workflow or "contents: write" in workflow:
        fail("D0T-03 source workflow is not read-only")
    if "persist-credentials: false" not in workflow:
        fail("D0T-03 checkout must discard credentials")
    for line in workflow.splitlines():
        stripped = line.strip()
        if not stripped.startswith("uses:"):
            continue
        action = stripped.split(":", 1)[1].strip()
        if action.startswith("./"):
            continue
        if "@" not in action or not SHA.fullmatch(action.rsplit("@", 1)[1]):
            fail(f"workflow action is not pinned by SHA: {action}")

    print("D0T-03 source governance contract passed; repository settings remain external")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
