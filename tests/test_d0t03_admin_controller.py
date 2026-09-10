from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timezone
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


def closed_accounts() -> dict:
    return {
        login: {"login": login, "id": reviewer_id, "type": "User"}
        for login, reviewer_id in module.REVIEWER_ACCOUNTS.items()
    }


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
                    {
                        "type": "User",
                        "reviewer": {
                            "id": reviewer_id,
                            "login": login,
                            "type": "User",
                        },
                    }
                    for login, reviewer_id in module.REVIEWER_ACCOUNTS.items()
                ],
            }
        ],
    }


def closed_probe_packet(main_sha: str) -> dict:
    roles = {
        role: [{"id": 1000 + index, "login": f"{role}-identity"}]
        for index, role in enumerate(module.SEPARATED_ROLES)
    }
    role_lookup = {role: values[0] for role, values in roles.items()}
    probes = []
    for index, (probe_id, (result, operation, role)) in enumerate(
        module.PROBE_EXPECTATIONS.items()
    ):
        actor = role_lookup[role]
        probes.append(
            {
                "id": probe_id,
                "result": result,
                "operation": operation,
                "actor_id": actor["id"],
                "actor_login": actor["login"],
                "actor_role": role,
                "observed_at": "2026-09-10T11:30:00Z",
                "subject_sha": main_sha,
                "evidence_api_url": (
                    "https://api.github.com/repos/"
                    "TrillionniumFoundation/trillionnium-os-desktop/"
                    f"actions/runs/{10000 + index}/attempts/1"
                ),
                "evidence_sha256": f"{index + 1:064x}",
            }
        )
    return {
        "schema_version": 2,
        "repository": module.REPOSITORY,
        "main_sha": main_sha,
        "issued_at": "2026-09-10T12:00:00Z",
        "attestor": {
            "id": 999999,
            "login": "independent-attestor",
            "role": "independent_governance_attestor",
        },
        "probes": probes,
        "role_identities": roles,
    }


class D0T03ControllerTests(unittest.TestCase):
    def test_static_configuration_is_closed(self) -> None:
        self.assertEqual(module.static_configuration_errors(), [])

    def test_required_checks_are_bound_to_github_actions_app(self) -> None:
        rules = {item["type"]: item for item in module.ruleset_payload()["rules"]}
        ruleset_checks = rules["required_status_checks"]["parameters"][
            "required_status_checks"
        ]
        self.assertEqual(
            {item["integration_id"] for item in ruleset_checks},
            {module.GITHUB_ACTIONS_APP_ID},
        )
        classic = module.branch_protection_payload()["required_status_checks"]["checks"]
        self.assertEqual(
            {item["app_id"] for item in classic},
            {module.GITHUB_ACTIONS_APP_ID},
        )

    def test_ruleset_rejects_missing_duplicate_wrong_and_unexpected_bindings(self) -> None:
        for mutate in ("missing", "duplicate", "wrong_app", "unexpected"):
            with self.subTest(mutate=mutate):
                payload = module.ruleset_payload()
                rules = {item["type"]: item for item in payload["rules"]}
                checks = rules["required_status_checks"]["parameters"][
                    "required_status_checks"
                ]
                if mutate == "missing":
                    checks.pop()
                elif mutate == "duplicate":
                    checks.append(dict(checks[0]))
                elif mutate == "wrong_app":
                    checks[0]["integration_id"] = 7
                else:
                    checks.append(
                        {
                            "context": "attacker/check",
                            "integration_id": module.GITHUB_ACTIONS_APP_ID,
                        }
                    )
                self.assertTrue(module.verify_ruleset(payload))

    def test_protection_verifier_accepts_exact_closed_readback(self) -> None:
        branch, protection = closed_protection()
        self.assertEqual(module.verify_protection(branch, protection), [])

    def test_protection_rejects_legacy_context_only_and_wrong_app(self) -> None:
        branch, protection = closed_protection()
        protection["required_status_checks"].pop("checks")
        protection["required_status_checks"]["contexts"] = list(module.REQUIRED_CHECKS)
        errors = module.verify_protection(branch, protection)
        self.assertTrue(any("bindings are absent" in error for error in errors))
        branch, protection = closed_protection()
        protection["required_status_checks"]["checks"][0]["app_id"] = -1
        errors = module.verify_protection(branch, protection)
        self.assertTrue(any("not GitHub Actions" in error for error in errors))

    def test_protection_rejects_absent_null_string_and_malformed_critical_controls(self) -> None:
        for key, expected in (
            ("required_signatures", True),
            ("allow_force_pushes", False),
            ("allow_deletions", False),
        ):
            for value in ("absent", None, "false", {}, {"other": expected}):
                with self.subTest(key=key, value=value):
                    branch, protection = closed_protection()
                    if value == "absent":
                        protection.pop(key)
                    else:
                        protection[key] = value
                    self.assertTrue(module.verify_protection(branch, protection))

    def test_environment_requires_exact_resolved_user_set(self) -> None:
        accounts = closed_accounts()
        for name in module.ENVIRONMENTS:
            self.assertEqual(
                module.verify_environment(name, closed_environment(name), accounts),
                [],
            )

    def test_environment_rejects_extra_duplicate_team_and_account_mismatch(self) -> None:
        cases = []
        extra = closed_environment("qualification")
        extra["protection_rules"][0]["reviewers"].append(
            {
                "type": "User",
                "reviewer": {"id": 7, "login": "attacker", "type": "User"},
            }
        )
        cases.append(extra)
        duplicate = closed_environment("qualification")
        duplicate["protection_rules"][0]["reviewers"].append(
            dict(duplicate["protection_rules"][0]["reviewers"][0])
        )
        cases.append(duplicate)
        team = closed_environment("qualification")
        team["protection_rules"][0]["reviewers"][0] = {
            "type": "Team",
            "reviewer": {"id": module.REVIEWERS[0], "login": "team", "type": "Team"},
        }
        cases.append(team)
        for environment in cases:
            with self.subTest(environment=environment):
                self.assertTrue(
                    module.verify_environment(
                        "qualification", environment, closed_accounts()
                    )
                )
        accounts = closed_accounts()
        accounts["Franksudoman"]["id"] = 1
        self.assertTrue(
            module.verify_environment(
                "qualification", closed_environment("qualification"), accounts
            )
        )

    def test_probe_packet_requires_verified_external_signature(self) -> None:
        packet = closed_probe_packet("a" * 40)
        errors = module.validate_probe_evidence(
            packet,
            "a" * 40,
            now=datetime(2026, 9, 10, 12, 5, tzinfo=timezone.utc),
        )
        self.assertTrue(any("signature" in error for error in errors))
        self.assertTrue(any("public-key digest" in error for error in errors))
        self.assertEqual(
            module.validate_probe_evidence(
                packet,
                "a" * 40,
                signature_verified=True,
                public_key_sha256="b" * 64,
                now=datetime(2026, 9, 10, 12, 5, tzinfo=timezone.utc),
            ),
            [],
        )

    def test_probe_rejects_mutable_url_unrelated_subject_actor_role_and_stale_time(self) -> None:
        mutations = ("url", "subject", "actor", "role", "stale")
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                packet = closed_probe_packet("a" * 40)
                probe = packet["probes"][0]
                if mutation == "url":
                    probe["evidence_api_url"] = "https://github.com/example/issues/1"
                elif mutation == "subject":
                    probe["subject_sha"] = "c" * 40
                elif mutation == "actor":
                    probe["actor_id"] = 42
                elif mutation == "role":
                    probe["actor_role"] = "reviewer"
                else:
                    packet["issued_at"] = "2026-09-01T00:00:00Z"
                errors = module.validate_probe_evidence(
                    packet,
                    "a" * 40,
                    signature_verified=True,
                    public_key_sha256="b" * 64,
                    now=datetime(2026, 9, 10, 12, 5, tzinfo=timezone.utc),
                )
                self.assertTrue(errors)

    def test_probe_rejects_attestor_role_overlap_and_extra_fields(self) -> None:
        packet = closed_probe_packet("a" * 40)
        packet["attestor"]["id"] = packet["role_identities"]["author"][0]["id"]
        packet["forged"] = True
        errors = module.validate_probe_evidence(
            packet,
            "a" * 40,
            signature_verified=True,
            public_key_sha256="b" * 64,
            now=datetime(2026, 9, 10, 12, 5, tzinfo=timezone.utc),
        )
        self.assertTrue(any("top-level" in error for error in errors))
        self.assertTrue(any("not independent" in error for error in errors))

    def test_detached_signature_verifier_binds_external_key_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            packet = root / "packet.json"
            signature = root / "packet.sig"
            public_key = root / "probe.pub"
            packet.write_text("{}\n", encoding="utf-8")
            signature.write_bytes(b"signature")
            public_key.write_bytes(b"public-key")
            expected = hashlib.sha256(public_key.read_bytes()).hexdigest()
            calls = []

            def runner(command, **kwargs):
                calls.append(command)
                return subprocess.CompletedProcess(command, 0, "Verified OK", "")

            self.assertEqual(
                module.verify_detached_signature(
                    packet,
                    signature,
                    public_key,
                    expected,
                    runner=runner,
                ),
                expected,
            )
            self.assertEqual(calls[0][0:3], ["openssl", "dgst", "-sha256"])
            with self.assertRaises(module.GovernanceError):
                module.verify_detached_signature(
                    packet,
                    signature,
                    public_key,
                    "0" * 64,
                    runner=runner,
                )

    def test_strict_json_rejects_duplicates_and_non_json_constants(self) -> None:
        with self.assertRaises(module.GovernanceError):
            module.strict_json('{"a":1,"a":2}')
        for value in ("NaN", "Infinity", "-Infinity"):
            with self.subTest(value=value), self.assertRaises(module.GovernanceError):
                module.strict_json('{"value":' + value + "}")


if __name__ == "__main__":
    unittest.main()
