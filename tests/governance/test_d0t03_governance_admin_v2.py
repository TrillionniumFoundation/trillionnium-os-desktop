from __future__ import annotations

import copy
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from d0t03_governance_admin_v2 import (  # noqa: E402
    GovernanceError,
    REQUIRED_CONTEXTS,
    Team,
    apply_plan,
    branch_protection_payload,
    branch_ruleset_payload,
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


class D0T03GovernanceAdminV2Tests(unittest.TestCase):
    def assert_rejected(self, reason: str, callback) -> None:
        with self.assertRaises(GovernanceError) as captured:
            callback()
        self.assertEqual(captured.exception.reason, reason)

    def test_required_contexts_are_unique_and_include_v2_gate(self) -> None:
        self.assertEqual(len(REQUIRED_CONTEXTS), len(set(REQUIRED_CONTEXTS)))
        self.assertIn(
            "d0t03-governance-admin-v2 / d0t03-governance-plan-v2",
            REQUIRED_CONTEXTS,
        )
        protection = branch_protection_payload()
        self.assertEqual(
            protection["required_status_checks"]["contexts"], REQUIRED_CONTEXTS
        )
        self.assertTrue(protection["required_status_checks"]["strict"])
        self.assertTrue(protection["enforce_admins"])
        self.assertFalse(protection["allow_force_pushes"])
        self.assertFalse(protection["allow_deletions"])
        reviews = protection["required_pull_request_reviews"]
        self.assertEqual(reviews["required_approving_review_count"], 2)
        self.assertTrue(reviews["dismiss_stale_reviews"])
        self.assertTrue(reviews["require_code_owner_reviews"])
        self.assertTrue(reviews["require_last_push_approval"])

    def test_ruleset_payloads_use_only_documented_top_level_fields(self) -> None:
        allowed = {
            "name",
            "target",
            "enforcement",
            "bypass_actors",
            "conditions",
            "rules",
        }
        for payload in (branch_ruleset_payload(), tag_ruleset_payload()):
            self.assertEqual(set(payload), allowed)
            self.assertEqual(payload["enforcement"], "active")
            self.assertEqual(payload["bypass_actors"], [])
            self.assertNotIn("metadata", payload)

    def test_branch_ruleset_matches_protection_semantics(self) -> None:
        ruleset = branch_ruleset_payload()
        self.assertEqual(ruleset["target"], "branch")
        self.assertEqual(
            ruleset["conditions"]["ref_name"]["include"], ["~DEFAULT_BRANCH"]
        )
        by_type = {rule["type"]: rule for rule in ruleset["rules"]}
        self.assertIn("deletion", by_type)
        self.assertIn("non_fast_forward", by_type)
        self.assertIn("required_linear_history", by_type)
        review = by_type["pull_request"]["parameters"]
        self.assertEqual(review["required_approving_review_count"], 2)
        self.assertTrue(review["dismiss_stale_reviews_on_push"])
        self.assertTrue(review["require_code_owner_review"])
        self.assertTrue(review["require_last_push_approval"])
        self.assertTrue(review["required_review_thread_resolution"])
        self.assertEqual(review["allowed_merge_methods"], ["squash"])
        checks = by_type["required_status_checks"]["parameters"]
        self.assertTrue(checks["strict_required_status_checks_policy"])
        self.assertEqual(
            [item["context"] for item in checks["required_status_checks"]],
            REQUIRED_CONTEXTS,
        )

    def test_tag_ruleset_protects_only_release_prefix_without_bypass(self) -> None:
        ruleset = tag_ruleset_payload()
        self.assertEqual(ruleset["target"], "tag")
        self.assertEqual(
            ruleset["conditions"]["ref_name"]["include"],
            ["refs/tags/desktop-v*"],
        )
        self.assertEqual(
            {rule["type"] for rule in ruleset["rules"]},
            {"creation", "deletion", "non_fast_forward"},
        )

    def test_workflow_and_environment_policies_are_fail_closed(self) -> None:
        workflow = workflow_permissions_payload()
        self.assertEqual(workflow["default_workflow_permissions"], "read")
        self.assertFalse(workflow["can_approve_pull_request_reviews"])
        environment = environment_payload([103, 102])
        self.assertTrue(environment["prevent_self_review"])
        self.assertEqual(
            environment["reviewers"],
            [{"type": "Team", "id": 102}, {"type": "Team", "id": 103}],
        )
        self.assertTrue(
            environment["deployment_branch_policy"]["protected_branches"]
        )
        self.assertFalse(
            environment["deployment_branch_policy"]["custom_branch_policies"]
        )

    def test_environment_requires_two_distinct_teams(self) -> None:
        self.assert_rejected(
            "TWO_DISTINCT_ENVIRONMENT_REVIEW_TEAMS_REQUIRED",
            lambda: environment_payload([101]),
        )
        self.assert_rejected(
            "TWO_DISTINCT_ENVIRONMENT_REVIEW_TEAMS_REQUIRED",
            lambda: environment_payload([101, 101]),
        )

    def test_people_preflight_rejects_single_person_and_role_overlap(self) -> None:
        security = Team("security-reviewers", 101, ("author", "sec-1", "sec-2"))
        governance = Team(
            "governance-reviewers", 102, ("author", "gov-1", "gov-2")
        )
        release = Team("release-approvers", 103, ("rel-1", "rel-2"))
        result = validate_people("author", security, governance, release)
        self.assertEqual(result["security_reviewers"], ["sec-1", "sec-2"])
        self.assertEqual(result["governance_reviewers"], ["gov-1", "gov-2"])
        self.assertEqual(result["release_reviewers"], ["rel-1", "rel-2"])
        self.assert_rejected(
            "TWO_DISTINCT_NON_AUTHOR_SECURITY_REVIEWERS_REQUIRED",
            lambda: validate_people(
                "author",
                Team("security-reviewers", 101, ("author", "sec-1")),
                governance,
                release,
            ),
        )
        self.assert_rejected(
            "SECURITY_AND_RELEASE_ROLE_SEPARATION_REQUIRED",
            lambda: validate_people(
                "author",
                security,
                governance,
                Team("release-approvers", 103, ("sec-1", "rel-2")),
            ),
        )

    def test_plan_is_closed_and_never_claims_settings_or_review(self) -> None:
        plan = fixture_plan()
        self.assertEqual(
            plan["schema"], "trillionnium.desktop.d0t03-governance-plan.v2"
        )
        self.assertEqual(len(plan["operations"]), 5)
        methods_paths = [
            (operation["method"], operation["path"])
            for operation in plan["operations"]
        ]
        self.assertEqual(len(methods_paths), len(set(methods_paths)) + 1)
        # The only repeated path is the rulesets collection: one branch and one tag ruleset.
        repeated = [path for _method, path in methods_paths if methods_paths.count(("POST", path)) > 1]
        self.assertTrue(repeated)
        self.assertFalse(plan["claim_ceiling"]["settings_applied"])
        self.assertFalse(plan["claim_ceiling"]["dynamic_negative_probes_passed"])
        self.assertFalse(plan["claim_ceiling"]["independent_review_completed"])
        self.assertFalse(plan["claim_ceiling"]["release_key_custody_proven"])

    def test_apply_requires_exact_confirmation_and_preserves_order(self) -> None:
        plan = fixture_plan()
        client = FakeClient()
        self.assert_rejected(
            "EXACT_REPOSITORY_CONFIRMATION_REQUIRED",
            lambda: apply_plan(client, plan, "other/repository"),
        )
        self.assertEqual(client.calls, [])
        results = apply_plan(client, plan, plan["repository"])
        self.assertEqual(len(results), len(plan["operations"]))
        self.assertEqual(
            [(method, path) for method, path, _payload in client.calls],
            [
                (operation["method"], operation["path"])
                for operation in plan["operations"]
            ],
        )


if __name__ == "__main__":
    unittest.main()
