from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools/d0t03_admin_controller.py"
spec = importlib.util.spec_from_file_location("d0t03_admin_controller", MODULE_PATH)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
try:
    spec.loader.exec_module(module)
except BaseException:
    sys.modules.pop(spec.name, None)
    raise


def closed_ruleset() -> dict:
    return module.ruleset_payload()


def closed_protection() -> tuple[dict, dict]:
    payload = module.branch_protection_payload()
    protection = {
        **payload,
        "enforce_admins": {"enabled": True},
        "required_conversation_resolution": {"enabled": True},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
        "required_signatures": {"enabled": True},
    }
    return {"name": "main", "protected": True}, protection


def closed_environment(name: str) -> dict:
    return {
        "name": name,
        "deployment_branch_policy": {
            "protected_branches": True,
            "custom_branch_policies": False,
        },
        "protection_rules": [
            {
                "type": "required_reviewers",
                "prevent_self_review": True,
                "reviewers": [
                    {"type": "User", "reviewer": {"id": reviewer}}
                    for reviewer in module.REVIEWERS
                ],
            }
        ],
    }


def closed_probe_packet(main_sha: str) -> dict:
    expected = [
        *[(probe, "rejected") for probe in module.REQUIRED_NEGATIVE_PROBES],
        *[(probe, "succeeded") for probe in module.REQUIRED_POSITIVE_PROBES],
    ]
    return {
        "schema_version": 1,
        "repository": module.REPOSITORY,
        "main_sha": main_sha,
        "observed_at": "2026-09-10T00:00:00Z",
        "probes": [
            {
                "id": probe,
                "result": result,
                "actor_id": index + 100,
                "actor_login": f"probe-{index}",
                "observed_at": "2026-09-10T00:00:00Z",
                "evidence_url": f"https://github.com/example/probe/{index}",
            }
            for index, (probe, result) in enumerate(expected)
        ],
        "role_identities": {
            role: [1000 + index]
            for index, role in enumerate(module.SEPARATED_ROLES)
        },
    }


class D0T03ControllerTests(unittest.TestCase):
    def test_static_configuration_is_closed(self) -> None:
        self.assertEqual(module.static_configuration_errors(), [])

    def test_ruleset_has_no_bypass_and_closed_pull_request_policy(self) -> None:
        payload = module.ruleset_payload()
        self.assertEqual(payload["bypass_actors"], [])
        self.assertEqual(module.verify_ruleset(payload), [])
        rules = {entry["type"]: entry for entry in payload["rules"]}
        parameters = rules["pull_request"]["parameters"]
        self.assertEqual(parameters["required_approving_review_count"], 2)
        self.assertTrue(parameters["dismiss_stale_reviews_on_push"])
        self.assertTrue(parameters["require_code_owner_review"])
        self.assertTrue(parameters["require_last_push_approval"])
        self.assertTrue(parameters["required_review_thread_resolution"])
        self.assertEqual(parameters["allowed_merge_methods"], ["merge"])

    def test_ruleset_verifier_reports_weakened_controls(self) -> None:
        payload = closed_ruleset()
        payload["enforcement"] = "disabled"
        payload["bypass_actors"] = [{"actor_id": 1}]
        payload["conditions"]["ref_name"]["include"] = []
        payload["rules"] = []
        errors = module.verify_ruleset(payload)
        self.assertGreaterEqual(len(errors), 10)

    def test_branch_payload_requires_strict_checks_and_two_current_approvals(self) -> None:
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

    def test_protection_verifier_accepts_exact_closed_readback(self) -> None:
        branch, protection = closed_protection()
        self.assertEqual(module.verify_protection(branch, protection), [])

    def test_protection_verifier_reports_every_weakened_control(self) -> None:
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
            "required_signatures": {"enabled": False},
        }
        errors = module.verify_protection(branch, protection)
        self.assertGreaterEqual(len(errors), 11)

    def test_environment_policy_and_readback_prevent_self_review(self) -> None:
        payload = module.environment_payload()
        self.assertTrue(payload["prevent_self_review"])
        self.assertEqual([entry["id"] for entry in payload["reviewers"]], list(module.REVIEWERS))
        for name in module.ENVIRONMENTS:
            self.assertEqual(module.verify_environment(name, closed_environment(name)), [])

    def test_environment_verifier_rejects_missing_reviewer_and_open_branch_policy(self) -> None:
        environment = closed_environment("qualification")
        environment["deployment_branch_policy"]["protected_branches"] = False
        environment["protection_rules"][0]["prevent_self_review"] = False
        environment["protection_rules"][0]["reviewers"].pop()
        errors = module.verify_environment("qualification", environment)
        self.assertGreaterEqual(len(errors), 3)

    def test_probe_packet_requires_all_results_and_role_separation(self) -> None:
        packet = closed_probe_packet("a" * 40)
        self.assertEqual(module.validate_probe_evidence(packet, "a" * 40), [])
        packet["probes"][0]["result"] = "succeeded"
        packet["probes"].pop()
        packet["role_identities"]["signer"] = packet["role_identities"]["author"]
        errors = module.validate_probe_evidence(packet, "a" * 40)
        self.assertTrue(any("result is not rejected" in error for error in errors))
        self.assertTrue(any("required probe" in error for error in errors))
        self.assertTrue(any("shared by roles" in error for error in errors))

    def test_probe_packet_rejects_stale_main_identity(self) -> None:
        packet = closed_probe_packet("a" * 40)
        errors = module.validate_probe_evidence(packet, "b" * 40)
        self.assertIn("probe packet is not bound to the current main SHA", errors)

    def test_strict_json_rejects_duplicates_and_non_json_constants(self) -> None:
        with self.assertRaises(module.GovernanceError):
            module.strict_json('{"a":1,"a":2}')
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value), self.assertRaises(module.GovernanceError):
                module.strict_json('{"value":' + value + "}")


if __name__ == "__main__":
    unittest.main()
