from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools/d0t03_admin_controller.py"
spec = importlib.util.spec_from_file_location("d0t03_admin_controller", MODULE_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class D0T03ControllerTests(unittest.TestCase):
    def test_payload_requires_strict_checks_and_two_current_approvals(self) -> None:
        payload = module.branch_protection_payload()
        self.assertTrue(payload["required_status_checks"]["strict"])
        self.assertEqual(
            {entry["context"] for entry in payload["required_status_checks"]["checks"]},
            set(module.REQUIRED_CHECKS),
        )
        reviews = payload["required_pull_request_reviews"]
        self.assertEqual(reviews["required_approving_review_count"], 2)
        self.assertTrue(reviews["dismiss_stale_reviews"])
        self.assertTrue(reviews["require_code_owner_reviews"])
        self.assertTrue(reviews["require_last_push_approval"])
        self.assertTrue(payload["enforce_admins"])
        self.assertFalse(payload["allow_force_pushes"])
        self.assertFalse(payload["allow_deletions"])
        self.assertTrue(payload["required_conversation_resolution"])

    def test_environment_policy_prevents_self_review(self) -> None:
        payload = module.environment_payload()
        self.assertTrue(payload["prevent_self_review"])
        self.assertEqual(
            [entry["id"] for entry in payload["reviewers"]],
            list(module.REVIEWERS),
        )
        self.assertTrue(payload["deployment_branch_policy"]["protected_branches"])
        self.assertFalse(
            payload["deployment_branch_policy"]["custom_branch_policies"]
        )

    def test_strict_json_rejects_duplicates_and_non_json_constants(self) -> None:
        with self.assertRaises(module.GovernanceError):
            module.strict_json('{"a":1,"a":2}')
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value), self.assertRaises(module.GovernanceError):
                module.strict_json('{"value":' + value + "}")

    def test_verifier_reports_every_weakened_control(self) -> None:
        branch = {"name": "main", "protected": False}
        protection = {
            "required_status_checks": {"strict": False, "checks": []},
            "required_pull_request_reviews": {
                "dismiss_stale_reviews": False,
                "require_code_owner_reviews": False,
                "require_last_push_approval": False,
                "required_approving_review_count": 1,
            },
            "enforce_admins": {"enabled": False},
            "required_conversation_resolution": {"enabled": False},
            "allow_force_pushes": {"enabled": True},
            "allow_deletions": {"enabled": True},
        }
        errors = module.verify_protection(branch, protection)
        self.assertGreaterEqual(len(errors), 10)

    def test_verifier_accepts_exact_closed_readback(self) -> None:
        branch = {"name": "main", "protected": True}
        protection = {
            "required_status_checks": {
                "strict": True,
                "checks": [
                    {"context": context} for context in module.REQUIRED_CHECKS
                ],
            },
            "required_pull_request_reviews": {
                "dismiss_stale_reviews": True,
                "require_code_owner_reviews": True,
                "require_last_push_approval": True,
                "required_approving_review_count": 2,
            },
            "enforce_admins": {"enabled": True},
            "required_conversation_resolution": {"enabled": True},
            "allow_force_pushes": {"enabled": False},
            "allow_deletions": {"enabled": False},
        }
        self.assertEqual(module.verify_protection(branch, protection), [])


if __name__ == "__main__":
    unittest.main()
