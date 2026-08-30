#!/usr/bin/env python3
"""Plan or apply D0T-03 GitHub governance settings.

The tool uses only the standard library, never stores a token, and defaults to
`plan`. Applying changes requires an explicit repository confirmation and a
GitHub token supplied through the environment. It refuses to proceed until
real organization teams and at least two distinct non-author human reviewers
are visible through the authenticated API.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "contracts" / "repository-governance.v1.json"
REQUIRED_CONTEXTS = [
    "desktop-ci / repository-contracts",
    "desktop-ci / rust",
    "agent-port-custody / validate-custody",
    "agent-transport-reference / reference-conformance",
    "browser-codec-reference-and-rust-gate / reference-conformance",
    "browser-codec-reference-and-rust-gate / rust",
    "receipt-journal / qualify",
    "servo-exact-pin / qualify",
    "servo-headed-runtime / qualify",
    "d1-final-qualification / qualify",
    "governance-integrity / governance-integrity",
]


class GovernanceError(ValueError):
    def __init__(self, reason: str, detail: str | None = None) -> None:
        super().__init__(reason if detail is None else f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def fail(reason: str, detail: str | None = None) -> None:
    raise GovernanceError(reason, detail)


def canonical(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def require_slug(value: str, reason: str) -> str:
    if not value or any(character not in "abcdefghijklmnopqrstuvwxyz0123456789-" for character in value):
        fail(reason, value)
    return value


def branch_protection_payload() -> dict[str, Any]:
    if len(REQUIRED_CONTEXTS) != len(set(REQUIRED_CONTEXTS)):
        fail("DUPLICATE_REQUIRED_CONTEXT")
    return {
        "required_status_checks": {
            "strict": True,
            "contexts": REQUIRED_CONTEXTS,
        },
        "enforce_admins": True,
        "required_pull_request_reviews": {
            "dismissal_restrictions": {},
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": True,
            "required_approving_review_count": 2,
            "require_last_push_approval": True,
            "bypass_pull_request_allowances": {},
        },
        "restrictions": None,
        "required_linear_history": True,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "block_creations": False,
        "required_conversation_resolution": True,
        "lock_branch": False,
        "allow_fork_syncing": False,
    }


def actions_permissions_payload() -> dict[str, Any]:
    return {
        "enabled": True,
        "allowed_actions": "selected",
        "selected_actions_url": None,
    }


def workflow_permissions_payload() -> dict[str, Any]:
    return {
        "default_workflow_permissions": "read",
        "can_approve_pull_request_reviews": False,
    }


def environment_payload(team_ids: list[int]) -> dict[str, Any]:
    if len(team_ids) < 2 or len(team_ids) != len(set(team_ids)):
        fail("TWO_DISTINCT_ENVIRONMENT_REVIEW_TEAMS_REQUIRED")
    return {
        "wait_timer": 0,
        "prevent_self_review": True,
        "reviewers": [
            {"type": "Team", "id": team_id} for team_id in sorted(team_ids)
        ],
        "deployment_branch_policy": {
            "protected_branches": True,
            "custom_branch_policies": False,
        },
    }


def branch_ruleset_payload(governance_team_id: int) -> dict[str, Any]:
    return {
        "name": "D0T-03 protected main",
        "target": "branch",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {
            "ref_name": {
                "include": ["~DEFAULT_BRANCH"],
                "exclude": [],
            }
        },
        "rules": [
            {"type": "deletion"},
            {"type": "non_fast_forward"},
            {"type": "required_linear_history"},
            {
                "type": "pull_request",
                "parameters": {
                    "required_approving_review_count": 2,
                    "dismiss_stale_reviews_on_push": True,
                    "require_code_owner_review": True,
                    "require_last_push_approval": True,
                    "required_review_thread_resolution": True,
                    "allowed_merge_methods": ["squash"],
                },
            },
            {
                "type": "required_status_checks",
                "parameters": {
                    "strict_required_status_checks_policy": True,
                    "do_not_enforce_on_create": False,
                    "required_status_checks": [
                        {"context": context} for context in REQUIRED_CONTEXTS
                    ],
                },
            },
        ],
        "metadata": {
            "governance_team_id": governance_team_id,
            "source_changes_alone_do_not_satisfy_D0T_03": True,
        },
    }


def tag_ruleset_payload() -> dict[str, Any]:
    return {
        "name": "D9 protected release tags",
        "target": "tag",
        "enforcement": "active",
        "bypass_actors": [],
        "conditions": {
            "ref_name": {
                "include": ["refs/tags/desktop-v*"],
                "exclude": [],
            }
        },
        "rules": [
            {"type": "creation"},
            {"type": "deletion"},
            {"type": "non_fast_forward"},
        ],
    }


@dataclass(frozen=True)
class Team:
    slug: str
    team_id: int
    members: tuple[str, ...]


class GitHubClient:
    def __init__(self, token: str, api_url: str = "https://api.github.com") -> None:
        if not token:
            fail("GITHUB_TOKEN_REQUIRED")
        self.token = token
        self.api_url = api_url.rstrip("/")

    def request(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None = None,
    ) -> Any:
        url = self.api_url + path
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        request = urllib.request.Request(
            url,
            method=method,
            data=data,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Trillionnium-D0T03-governance-admin",
                "Content-Type": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                body = response.read()
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise GovernanceError(
                "GITHUB_API_REQUEST_FAILED",
                f"{method} {path} status={error.code} body={detail[:2048]}",
            ) from error
        if not body:
            return None
        return json.loads(body)


def read_team(
    client: GitHubClient,
    organization: str,
    slug: str,
) -> Team:
    require_slug(slug, "INVALID_TEAM_SLUG")
    record = client.request("GET", f"/orgs/{organization}/teams/{slug}")
    members = client.request(
        "GET", f"/orgs/{organization}/teams/{slug}/members?per_page=100"
    )
    if not isinstance(record, dict) or not isinstance(record.get("id"), int):
        fail("TEAM_ID_MISSING", slug)
    if not isinstance(members, list):
        fail("TEAM_MEMBER_LIST_INVALID", slug)
    logins = tuple(sorted(member["login"] for member in members if isinstance(member, dict) and isinstance(member.get("login"), str)))
    return Team(slug=slug, team_id=record["id"], members=logins)


def validate_people(
    author: str,
    security: Team,
    governance: Team,
    release: Team,
) -> dict[str, Any]:
    if not author:
        fail("SOURCE_AUTHOR_REQUIRED")
    security_reviewers = sorted(set(security.members) - {author})
    governance_reviewers = sorted(set(governance.members) - {author})
    release_reviewers = sorted(set(release.members) - {author})
    if len(security_reviewers) < 2:
        fail("TWO_DISTINCT_NON_AUTHOR_SECURITY_REVIEWERS_REQUIRED")
    if len(governance_reviewers) < 2:
        fail("TWO_DISTINCT_NON_AUTHOR_GOVERNANCE_REVIEWERS_REQUIRED")
    if len(release_reviewers) < 2:
        fail("TWO_DISTINCT_NON_AUTHOR_RELEASE_REVIEWERS_REQUIRED")
    if not set(security_reviewers).isdisjoint(release_reviewers):
        fail("SECURITY_AND_RELEASE_ROLE_SEPARATION_REQUIRED")
    return {
        "source_author": author,
        "security_reviewers": security_reviewers,
        "governance_reviewers": governance_reviewers,
        "release_reviewers": release_reviewers,
        "security_team_id": security.team_id,
        "governance_team_id": governance.team_id,
        "release_team_id": release.team_id,
    }


def build_plan(
    owner: str,
    repo: str,
    author: str,
    security: Team,
    governance: Team,
    release: Team,
) -> dict[str, Any]:
    people = validate_people(author, security, governance, release)
    repository = f"{owner}/{repo}"
    return {
        "schema": "trillionnium.desktop.d0t03-governance-plan.v1",
        "repository": repository,
        "preflight": people,
        "operations": [
            {
                "method": "PUT",
                "path": f"/repos/{repository}/branches/main/protection",
                "payload": branch_protection_payload(),
            },
            {
                "method": "PUT",
                "path": f"/repos/{repository}/actions/permissions/workflow",
                "payload": workflow_permissions_payload(),
            },
            {
                "method": "PUT",
                "path": f"/repos/{repository}/environments/production",
                "payload": environment_payload(
                    [governance.team_id, release.team_id]
                ),
            },
            {
                "method": "POST",
                "path": f"/repos/{repository}/rulesets",
                "payload": branch_ruleset_payload(governance.team_id),
            },
            {
                "method": "POST",
                "path": f"/repos/{repository}/rulesets",
                "payload": tag_ruleset_payload(),
            },
        ],
        "manual_postconditions": [
            "CODEOWNERS uses organization teams and not individual fallback owners",
            "direct push, force push, branch deletion, self approval, stale approval, failed check, and administrator bypass probes all fail",
            "two different authorized identities complete one compliant merge",
            "production environment rejects self review and requires two different team approvals",
            "release signing and source authorship are held by separate people and offline keys",
        ],
        "claim_ceiling": {
            "settings_applied": False,
            "dynamic_negative_probes_passed": False,
            "independent_review_completed": False,
            "release_key_custody_proven": False,
        },
    }


def discover_plan(client: GitHubClient, args: argparse.Namespace) -> dict[str, Any]:
    security = read_team(client, args.owner, args.security_team)
    governance = read_team(client, args.owner, args.governance_team)
    release = read_team(client, args.owner, args.release_team)
    return build_plan(
        args.owner,
        args.repo,
        args.source_author,
        security,
        governance,
        release,
    )


def apply_plan(client: GitHubClient, plan: dict[str, Any], confirmed: str) -> list[dict[str, Any]]:
    if confirmed != plan["repository"]:
        fail("EXACT_REPOSITORY_CONFIRMATION_REQUIRED")
    results = []
    for operation in plan["operations"]:
        response = client.request(
            operation["method"], operation["path"], operation["payload"]
        )
        results.append(
            {
                "method": operation["method"],
                "path": operation["path"],
                "response_received": response is not None,
            }
        )
    return results


def fixture_plan() -> dict[str, Any]:
    return build_plan(
        "TrillionniumFoundation",
        "trillionnium-os-desktop",
        "source-author",
        Team("security-reviewers", 101, ("source-author", "sec-1", "sec-2")),
        Team("governance-reviewers", 102, ("source-author", "gov-1", "gov-2")),
        Team("release-approvers", 103, ("release-1", "release-2")),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["self-test", "plan", "apply"])
    parser.add_argument("--owner", default="TrillionniumFoundation")
    parser.add_argument("--repo", default="trillionnium-os-desktop")
    parser.add_argument("--source-author", default="Tomasrgbsf")
    parser.add_argument("--security-team", default="security-reviewers")
    parser.add_argument("--governance-team", default="governance-reviewers")
    parser.add_argument("--release-team", default="release-approvers")
    parser.add_argument("--confirm-repository")
    parser.add_argument("--token-env", default="GITHUB_TOKEN")
    parser.add_argument("--write-result", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "self-test":
            plan = fixture_plan()
            result = {
                "schema": "trillionnium.desktop.d0t03-governance-admin-self-test.v1",
                "status": "PASS_PLAN_ONLY",
                "operation_count": len(plan["operations"]),
                "required_context_count": len(REQUIRED_CONTEXTS),
                "distinct_contexts": len(REQUIRED_CONTEXTS)
                == len(set(REQUIRED_CONTEXTS)),
                "settings_applied": False,
                "independent_review_completed": False,
                "release_key_custody_proven": False,
            }
        else:
            client = GitHubClient(os.environ.get(args.token_env, ""))
            plan = discover_plan(client, args)
            if args.command == "plan":
                result = plan
            else:
                applied = apply_plan(client, plan, args.confirm_repository or "")
                result = {
                    "schema": "trillionnium.desktop.d0t03-governance-apply-result.v1",
                    "repository": plan["repository"],
                    "operations": applied,
                    "settings_requests_completed": True,
                    "dynamic_postconditions_still_required": True,
                    "independent_review_completed": False,
                    "release_key_custody_proven": False,
                }
        payload = canonical(result)
        if args.write_result:
            args.write_result.parent.mkdir(parents=True, exist_ok=True)
            args.write_result.write_text(payload, encoding="utf-8")
        print(payload, end="")
        return 0
    except GovernanceError as error:
        print(
            json.dumps(
                {"status": "REJECTED", "reason": error.reason, "detail": error.detail},
                sort_keys=True,
            ),
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
