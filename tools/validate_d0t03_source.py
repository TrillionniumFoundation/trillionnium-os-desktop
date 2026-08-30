#!/usr/bin/env python3
"""Validate the source-controlled half of D0T-03 without fabricating settings."""
from __future__ import annotations

import fnmatch
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests/repository-governance.v1.json"
CODEOWNERS = ROOT / ".github/CODEOWNERS"
WORKFLOW = ROOT / ".github/workflows/d0t03-source-contract.yml"
SHA = re.compile(r"^[0-9a-f]{40}$")
OWNER = re.compile(r"^@[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})(?:/[A-Za-z0-9_.-]+)?$")


@dataclass(frozen=True)
class Rule:
    pattern: str
    owners: tuple[str, ...]


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def parse_codeowners(text: str) -> list[Rule]:
    rules: list[Rule] = []
    for line_number, raw in enumerate(text.splitlines(), 1):
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if "\\" in raw or "[" in raw or "]" in raw or stripped.startswith("!"):
            fail(f"unsupported CODEOWNERS pattern syntax on line {line_number}")
        body = raw.split("#", 1)[0].strip()
        fields = body.split()
        if len(fields) < 2:
            fail(f"CODEOWNERS rule has no owner on line {line_number}")
        pattern, owner_tokens = fields[0], fields[1:]
        if any(not OWNER.fullmatch(token) for token in owner_tokens):
            fail(f"invalid CODEOWNERS owner token on line {line_number}")
        rules.append(
            Rule(
                pattern=pattern,
                owners=tuple(token[1:] for token in owner_tokens),
            )
        )
    if not rules:
        fail("CODEOWNERS has no active rules")
    return rules


def pattern_matches(pattern: str, repository_path: str) -> bool:
    path = repository_path.strip("/")
    if not path or repository_path.startswith("../") or "/../" in repository_path:
        return False
    if pattern == "*":
        return True
    anchored = pattern.startswith("/")
    candidate = pattern[1:] if anchored else pattern
    if candidate.endswith("/"):
        prefix = candidate.rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    if candidate.endswith("/**"):
        prefix = candidate[:-3].rstrip("/")
        return path == prefix or path.startswith(prefix + "/")
    if "/" not in candidate:
        return fnmatch.fnmatchcase(Path(path).name, candidate)
    if anchored:
        return fnmatch.fnmatchcase(path, candidate)
    parts = Path(path).parts
    return fnmatch.fnmatchcase(path, candidate) or any(
        fnmatch.fnmatchcase("/".join(parts[index:]), candidate)
        for index in range(1, len(parts))
    )


def effective_owners(
    rules: list[Rule], repository_path: str
) -> tuple[str, ...] | None:
    effective: tuple[str, ...] | None = None
    for rule in rules:
        if pattern_matches(rule.pattern, repository_path):
            effective = rule.owners
    return effective


def validate_rule_surface(
    rules: list[Rule], review: dict[str, object]
) -> None:
    owners = review.get("interim_codeowners", [])
    if not isinstance(owners, list) or len(owners) < 2:
        fail("at least two interim CODEOWNER identities are required")
    expected_owner_tuple = tuple(str(owner) for owner in owners)
    if len(set(expected_owner_tuple)) != len(expected_owner_tuple):
        fail("interim CODEOWNER identities must be distinct")

    declared = review.get("protected_codeowner_rules")
    if not isinstance(declared, list) or not declared:
        fail("protected CODEOWNERS rule registry is absent")
    declared_patterns: list[str] = []
    for index, item in enumerate(declared):
        if not isinstance(item, dict):
            fail(f"protected CODEOWNERS rule {index} is not an object")
        pattern = item.get("pattern")
        rule_owners = item.get("owners")
        samples = item.get("samples")
        if not isinstance(pattern, str) or not pattern:
            fail(f"protected CODEOWNERS rule {index} has no pattern")
        if (
            not isinstance(rule_owners, list)
            or tuple(rule_owners) != expected_owner_tuple
        ):
            fail(
                f"protected CODEOWNERS rule {pattern} does not use the exact approved owner set"
            )
        if (
            not isinstance(samples, list)
            or not samples
            or any(not isinstance(value, str) for value in samples)
        ):
            fail(
                f"protected CODEOWNERS rule {pattern} has no canonical sample paths"
            )
        declared_patterns.append(pattern)

    actual_patterns = [rule.pattern for rule in rules]
    if len(actual_patterns) != len(set(actual_patterns)):
        fail(
            "duplicate CODEOWNERS patterns are forbidden because ordering is security-sensitive"
        )
    if actual_patterns != declared_patterns:
        fail(
            "CODEOWNERS active-rule order differs from the canonical governance registry"
        )
    if actual_patterns[0] != "*" or actual_patterns.count("*") != 1:
        fail("the sole catch-all CODEOWNERS rule must be first")

    for rule in rules:
        if rule.owners != expected_owner_tuple:
            fail(
                f"CODEOWNERS rule {rule.pattern} must name exactly "
                + " ".join(f"@{owner}" for owner in expected_owner_tuple)
            )

    for item in declared:
        pattern = str(item["pattern"])
        for sample in item["samples"]:
            effective = effective_owners(rules, sample)
            if effective != expected_owner_tuple:
                fail(
                    f"last-match-wins owners for {sample} are {effective!r}, "
                    f"expected {expected_owner_tuple!r} from {pattern}"
                )


def self_test_codeowners_model() -> None:
    expected = ("Tomasrgbsf", "ProfHepta")
    rules = [
        Rule("*", expected),
        Rule("/.github/", expected),
    ]
    if effective_owners(rules, ".github/workflows/test.yml") != expected:
        fail("internal CODEOWNERS last-match model failed")
    shadowed = rules + [
        Rule("/.github/workflows/", ("Tomasrgbsf", "Other"))
    ]
    if effective_owners(
        shadowed, ".github/workflows/test.yml"
    ) != ("Tomasrgbsf", "Other"):
        fail(
            "internal CODEOWNERS last-match model does not observe later overrides"
        )


def main() -> int:
    self_test_codeowners_model()

    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if data.get("schema") != "trillionnium.desktop.repository-governance.v1":
        fail("unexpected governance schema")
    if data.get("work_package") != "D0T-03":
        fail("governance manifest is not bound to D0T-03")
    if data.get("status") != "SOURCE_BOOTSTRAP_READY_REPOSITORY_SETTINGS_REQUIRED":
        fail("source contract must remain fail-closed on repository settings")

    review = data.get("source_review", {})
    if not isinstance(review, dict):
        fail("source_review must be an object")
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

    rules = parse_codeowners(CODEOWNERS.read_text(encoding="utf-8"))
    validate_rule_surface(rules, review)

    branch = data.get("main_branch", {})
    if not isinstance(branch, dict):
        fail("main_branch must be an object")
    for key in ("pull_request_required", "strict_required_checks"):
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
    candidate_workflows = branch.get(
        "candidate_workflows_pending_integration", []
    )
    if not isinstance(required_workflows, list) or not required_workflows:
        fail("required workflow registry is empty")
    if len(required_workflows) != len(set(required_workflows)):
        fail("required workflow registry contains duplicates")
    if (
        not isinstance(candidate_workflows, list)
        or len(candidate_workflows) != len(set(candidate_workflows))
    ):
        fail("candidate workflow registry is invalid or duplicated")
    if set(required_workflows) & set(candidate_workflows):
        fail("a workflow cannot be both required and pending integration")
    if str(WORKFLOW.relative_to(ROOT)) not in required_workflows:
        fail("D0T-03 source workflow does not require itself")
    for relative in required_workflows:
        if (
            not isinstance(relative, str)
            or not relative.startswith(".github/workflows/")
        ):
            fail(f"invalid required workflow path: {relative!r}")
        if not (ROOT / relative).is_file():
            fail(f"required workflow is absent: {relative}")
    for relative in candidate_workflows:
        if (
            not isinstance(relative, str)
            or not relative.startswith(".github/workflows/")
        ):
            fail(f"invalid candidate workflow path: {relative!r}")

    release = data.get("release", {})
    if not isinstance(release, dict):
        fail("release must be an object")
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
    if (
        not isinstance(claims, dict)
        or not claims
        or any(value is not False for value in claims.values())
    ):
        fail("source must not claim external settings or independent review")
    if (
        data.get("claim_ceiling")
        != "source_contract_and_interim_two_identity_codeowners_only"
    ):
        fail("governance claim ceiling changed")

    workflow = WORKFLOW.read_text(encoding="utf-8")
    if "contents: read" not in workflow or "contents: write" in workflow:
        fail("D0T-03 source workflow is not read-only")
    if "persist-credentials: false" not in workflow:
        fail("D0T-03 checkout must discard credentials")
    if "\n    paths:" in workflow or "\n    paths-ignore:" in workflow:
        fail("D0T-03 source workflow must report without path filters")
    for forbidden in (
        "git push",
        "git commit",
        "update-ref",
        "contents: write",
    ):
        if forbidden in workflow:
            fail(
                f"D0T-03 source workflow contains forbidden mutation surface: {forbidden}"
            )
    for line in workflow.splitlines():
        stripped = line.strip()
        if not stripped.startswith("uses:"):
            continue
        action = stripped.split(":", 1)[1].strip()
        if action.startswith("./"):
            continue
        if "@" not in action or not SHA.fullmatch(action.rsplit("@", 1)[1]):
            fail(f"workflow action is not pinned by SHA: {action}")

    print(
        "D0T-03 source governance contract passed; repository settings remain external"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
