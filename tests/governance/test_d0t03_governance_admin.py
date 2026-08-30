from __future__ import annotations

import copy
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from d0t03_governance_admin import (  # noqa: E402
    GovernanceError,
    REQUIRED_CONTEXTS,
    Team,
    apply_plan,
    branch_protection_payload,
    build_plan,
    environment_payload,
    fixture_plan,
    tag_ruleset_payload,
    validate_people,
    workflow_permissions_payload,
)


class FakeClient:
    def __init__(self) -> None:
        self.calls = []

    def request(self, method, path, payload=None):
        self.calls.append((method, path, copy.deepcopy(payload)))
        return {"ok": True}


class D0T03GovernanceAdminTests(unittest.TestCase):
    def assert_rejected(self, reason: str, callback) -> None:
        with self.assertRaises(GovernanceError) as captured:
            callback()
        self.assertEqual(captured.exception.reason, reason)

    def teams(self):
        return (
            Team("security-reviewers", 101, ("author", "sec-1", "sec-2")),
            Team("governance-reviewers", 102, ("author", "gov-1", "gov-2")),
            Team("release-approvers", 103, ("release-1", "release-2")),
        )

    def test_required_contexts_are_unique_and_strict(self) -> None:
        self.assertEqual(len(REQUIRED_CONTEXTS), len(set(REQUIRED_CONTEXTS)))
        protection = branch_protection_payload()
        self.assertTrue(protection["required_status_checks"]["strict"])
        self.assertEqual(
            protection["required_status_checks"]["contexts"], REQUIRED_CONTEXTS
        )
        reviews = protection["required_pull_request_reviews"]
        self.assertEqual(reviews["required_approving_review_count"], 2)
        self.assertTrue(reviews["dismiss_stale_reviews"])
        self.assertTrue(reviews["require_code_owner_reviews"])
        self.assertTrue(reviews["require_last_push_approval"])
        self.assertTrue(protection["enforce_admins"])
        self.assertTrue(protection["required_conversation_resolution"])
        self.assertFalse(protection["allow_force_pushes"])
        self.assertFalse(protection["allow_deletions"])

    def test_actions_and_environment_defaults_are_fail_closed(self) -> None:
        permissions = workflow_permissions_payload()
        self.assertEqual(permissions["default_workflow_permissions"], "read")
        self.assertFalse(permissions["can_approve_pull_request_reviews"])
        environment = environment_payload([103, 102])
        self.assertTrue(environment["prevent_self_review"])
        self.assertEqual(
            environment["reviewers"],
            [{"type": "Team", "id": 102}, {"type": "Team", "id": 103}],
        )
        self.assertTrue(
            environment["deployment_branch_policy"]["protected_branches"]
        )

    def test_environment_requires_two_distinct_teams(self) -> None:
        self.assert_rejected(
            "TWO_DISTINCT_ENVIRONMENT_REVIEW_TEAMS_REQUIRED",
            lambda: environment_payload([103]),
        )
        self.assert_rejected(
            "TWO_DISTINCT_ENVIRONMENT_REVIEW_TEAMS_REQUIRED",
            lambda: environment_payload([103, 103]),
        )

    def test_people_preflight_requires_two_non_author_members_per_role(self) -> None:
        security, governance, release = self.teams()
        result = validate_people("author", security, governance, release)
        self.assertEqual(result["security_reviewers"], ["sec-1", "sec-2"])
        self.assertEqual(result["governance_reviewers"], ["gov-1", "gov-2"])
        self.assertEqual(result["release_reviewers"], ["release-1", "release-2"])

        weak_security = Team("security-reviewers", 101, ("author", "sec-1"))
        self.assert_rejected(
            "TWO_DISTINCT_NON_AUTHOR_SECURITY_REVIEWERS_REQUIRED",
            lambda: validate_people(
                "author", weak_security, governance, release
            ),
        )
        weak_governance = Team(
            "governance-reviewers", 102, ("author", "gov-1")
        )
        self.assert_rejected(
            "TWO_DISTINCT_NON_AUTHOR_GOVERNANCE_REVIEWERS_REQUIRED",
            lambda: validate_people(
                "author", security, weak_governance, release
            ),
        )
        weak_release = Team("release-approvers", 103, ("author", "release-1"))
        self.assert_rejected(
            "TWO_DISTINCT_NON_AUTHOR_RELEASE_REVIEWERS_REQUIRED",
            lambda: validate_people(
                "author", security, governance, weak_release
            ),
        )

    def test_security_and_release_roles_must_be_disjoint(self) -> None:
        security, governance, _release = self.teams()
        overlapping = Team("release-approvers", 103, ("sec-1", "release-2"))
        self.assert_rejected(
            "SECURITY_AND_RELEASE_ROLE_SEPARATION_REQUIRED",
            lambda: validate_people(
                "author", security, governance, overlapping
            ),
        )

    def test_plan_contains_branch_environment_and_tag_controls(self) -> None:
        plan = fixture_plan()
        self.assertEqual(
            plan["schema"], "trillionnium.desktop.d0t03-governance-plan.v1"
        )
        self.assertEqual(plan["repository"], "TrillionniumFoundation/trillionnium-os-desktop")
        operations = {(item["method"], item["path"]): item for item in plan["operations"]}
        self.assertIn(
            (
                "PUT",
                "/repos/TrillionniumFoundation/trillionnium-os-desktop/branches/main/protection",
            ),
            operations,
        )
        self.assertIn(
            (
                "PUT",
                "/repos/TrillionniumFoundation/trillionnium-os-desktop/environments/production",
            ),
            operations,
        )
        rulesets = [
            item["payload"]
            for item in plan["operations"]
            if item["path"].endswith("/rulesets")
        ]
        self.assertEqual(len(rulesets), 2)
        self.assertEqual({item["target"] for item in rulesets}, {"branch", "tag"})
        self.assertFalse(plan["claim_ceiling"]["settings_applied"])
        self.assertFalse(plan["claim_ceiling"]["independent_review_completed"])
        self.assertFalse(plan["claim_ceiling"]["release_key_custody_proven"])

    def test_tag_ruleset_has_no_bypass_and_protects_release_prefix(self) -> None:
        ruleset = tag_ruleset_payload()
        self.assertEqual(ruleset["target"], "tag")
        self.assertEqual(ruleset["enforcement"], "active")
        self.assertEqual(ruleset["bypass_actors"], [])
        self.assertEqual(
            ruleset["conditions"]["ref_name"]["include"],
            ["refs/tags/desktop-v*"],
        )
        self.assertEqual(
            {rule["type"] for rule in ruleset["rules"]},
            {"creation", "deletion", "non_fast_forward"},
        )

    def test_apply_requires_exact_repository_confirmation(self) -> None:
        plan = fixture_plan()
        client = FakeClient()
        self.assert_rejected(
            "EXACT_REPOSITORY_CONFIRMATION_REQUIRED",
            lambda: apply_plan(client, plan, "wrong/repository"),
        )
        self.assertEqual(client.calls, [])

    def test_apply_uses_only_declared_operations(self) -> None:
        plan = fixture_plan()
        client = FakeClient()
        result = apply_plan(client, plan, plan["repository"])
        self.assertEqual(len(result), len(plan["operations"]))
        self.assertEqual(
            [(method, path) for method, path, _payload in client.calls],
            [(item["method"], item["path"]) for item in plan["operations"]],
        )
        for _method, _path, payload in client.calls:
            self.assertIsInstance(payload, dict)

    def test_source_author_is_removed_from_all_reviewer_sets(self) -> None:
        security = Team("security-reviewers", 101, ("author", "sec-1", "sec-2"))
        governance = Team(
            "governance-reviewers", 102, ("author", "gov-1", "gov-2")
        )
        release = Team("release-approvers", 103, ("author", "rel-1", "rel-2"))
        result = validate_people("author", security, governance, release)
        for key in (
            "security_reviewers",
            "governance_reviewers",
            "release_reviewers",
        ):
            self.assertNotIn("author", result[key])


if __name__ == "__main__":
    unittest.main()
