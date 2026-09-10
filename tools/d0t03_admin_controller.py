#!/usr/bin/env python3
"""Configure and verify the D0T-03 GitHub governance gate.

The controller is fail closed. Source validation never implies live policy
activation. Live closure additionally requires exact Administration readback
and a detached, independently signed probe attestation whose public-key digest
is supplied outside this source tree.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

REPOSITORY = "TrillionniumFoundation/trillionnium-os-desktop"
DEFAULT_BRANCH = "main"
RULESET_NAME = "TrillionniumOS protected default branch"
GITHUB_ACTIONS_APP_ID = 15368
REVIEWER_ACCOUNTS = {
    "Franksudoman": 273670192,
    "Tomasrgbsf": 273673612,
}
REVIEWERS = tuple(REVIEWER_ACCOUNTS.values())
ENVIRONMENTS = (
    "qualification",
    "hardware-attestation",
    "release-signing",
    "production-publication",
)
REQUIRED_CHECKS = (
    "repository-contracts",
    "rust",
    "repository-contracts-prospective-merge",
    "rust-prospective-merge",
)
REQUIRED_NEGATIVE_PROBES = (
    "direct_push_rejected",
    "force_push_rejected",
    "branch_deletion_rejected",
    "missing_required_check_rejected",
    "stale_approval_rejected",
    "missing_codeowner_rejected",
    "insufficient_approvals_rejected",
    "unresolved_conversation_rejected",
    "administrator_bypass_rejected",
    "unauthorized_environment_rejected",
    "environment_self_approval_rejected",
)
REQUIRED_POSITIVE_PROBES = (
    "authorized_protected_merge_succeeded",
    "protected_publication_succeeded",
)
SEPARATED_ROLES = (
    "author",
    "reviewer",
    "builder",
    "signer",
    "attestor",
    "promoter",
    "publisher",
)
PROBE_EXPECTATIONS = {
    "direct_push_rejected": ("rejected", "git.push.default_branch", "author"),
    "force_push_rejected": ("rejected", "git.force_push.default_branch", "author"),
    "branch_deletion_rejected": ("rejected", "git.delete.default_branch", "author"),
    "missing_required_check_rejected": (
        "rejected",
        "pull_request.merge.missing_required_check",
        "promoter",
    ),
    "stale_approval_rejected": (
        "rejected",
        "pull_request.merge.stale_approval",
        "promoter",
    ),
    "missing_codeowner_rejected": (
        "rejected",
        "pull_request.merge.missing_codeowner",
        "promoter",
    ),
    "insufficient_approvals_rejected": (
        "rejected",
        "pull_request.merge.insufficient_approvals",
        "promoter",
    ),
    "unresolved_conversation_rejected": (
        "rejected",
        "pull_request.merge.unresolved_conversation",
        "promoter",
    ),
    "administrator_bypass_rejected": (
        "rejected",
        "pull_request.merge.administrator_bypass",
        "promoter",
    ),
    "unauthorized_environment_rejected": (
        "rejected",
        "deployment.environment.unauthorized",
        "promoter",
    ),
    "environment_self_approval_rejected": (
        "rejected",
        "deployment.environment.self_approval",
        "promoter",
    ),
    "authorized_protected_merge_succeeded": (
        "succeeded",
        "pull_request.merge.authorized_protected_path",
        "promoter",
    ),
    "protected_publication_succeeded": (
        "succeeded",
        "deployment.environment.protected_publication",
        "publisher",
    ),
}
PROBE_TOP_LEVEL_FIELDS = {
    "schema_version",
    "repository",
    "main_sha",
    "issued_at",
    "attestor",
    "probes",
    "role_identities",
}
PROBE_FIELDS = {
    "id",
    "result",
    "operation",
    "actor_id",
    "actor_login",
    "actor_role",
    "observed_at",
    "subject_sha",
    "evidence_api_url",
    "evidence_sha256",
}
ATTESTOR_FIELDS = {"id", "login", "role"}
ROLE_IDENTITY_FIELDS = {"id", "login"}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
IMMUTABLE_RUN_ATTEMPT_RE = re.compile(
    r"^https://api\.github\.com/repos/"
    r"TrillionniumFoundation/trillionnium-os-desktop/"
    r"actions/runs/[1-9][0-9]*/attempts/[1-9][0-9]*$"
)
MAX_PROBE_AGE = timedelta(hours=24)
MAX_CLOCK_SKEW = timedelta(minutes=5)


class GovernanceError(RuntimeError):
    """Raised when a governance operation cannot be verified fail closed."""


@dataclass(frozen=True)
class ApiResult:
    returncode: int
    data: Any
    stderr: str


def strict_json(text: str) -> Any:
    """Decode strict JSON, rejecting duplicate members and non-JSON constants."""

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise GovernanceError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise GovernanceError(f"non-JSON numeric constant {value!r}")

    return json.loads(
        text,
        object_pairs_hook=reject_duplicates,
        parse_constant=reject_constant,
    )


def _check_binding(context: str) -> dict[str, Any]:
    return {"context": context, "integration_id": GITHUB_ACTIONS_APP_ID}


def ruleset_payload() -> dict[str, Any]:
    """Return the no-bypass repository ruleset for the default branch."""

    return {
        "name": RULESET_NAME,
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
            {"type": "required_signatures"},
            {
                "type": "pull_request",
                "parameters": {
                    "allowed_merge_methods": ["merge"],
                    "dismiss_stale_reviews_on_push": True,
                    "require_code_owner_review": True,
                    "require_last_push_approval": True,
                    "required_approving_review_count": 2,
                    "required_review_thread_resolution": True,
                },
            },
            {
                "type": "required_status_checks",
                "parameters": {
                    "do_not_enforce_on_create": False,
                    "required_status_checks": [
                        _check_binding(context) for context in REQUIRED_CHECKS
                    ],
                    "strict_required_status_checks_policy": True,
                },
            },
        ],
    }


def branch_protection_payload() -> dict[str, Any]:
    """Return the closed classic-protection payload for ``main``."""

    return {
        "required_status_checks": {
            "strict": True,
            "checks": [
                {"context": context, "app_id": GITHUB_ACTIONS_APP_ID}
                for context in REQUIRED_CHECKS
            ],
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
        "required_linear_history": False,
        "allow_force_pushes": False,
        "allow_deletions": False,
        "block_creations": False,
        "required_conversation_resolution": True,
        "lock_branch": False,
        "allow_fork_syncing": False,
    }


def environment_payload() -> dict[str, Any]:
    """Return the protected-environment policy shared by all release tiers."""

    return {
        "wait_timer": 0,
        "prevent_self_review": True,
        "reviewers": [
            {"type": "User", "id": reviewer_id}
            for reviewer_id in REVIEWER_ACCOUNTS.values()
        ],
        "deployment_branch_policy": {
            "protected_branches": True,
            "custom_branch_policies": False,
        },
    }


def repository_merge_payload() -> dict[str, Any]:
    return {
        "allow_merge_commit": True,
        "allow_squash_merge": False,
        "allow_rebase_merge": False,
        "allow_auto_merge": True,
        "delete_branch_on_merge": True,
        "allow_update_branch": True,
    }


def _run_gh(arguments: list[str], body: dict[str, Any] | None = None) -> ApiResult:
    command = ["gh", "api", *arguments]
    encoded = None
    if body is not None:
        command.extend(["--input", "-"])
        encoded = json.dumps(body, allow_nan=False)
    completed = subprocess.run(
        command,
        input=encoded,
        text=True,
        capture_output=True,
        check=False,
    )
    data: Any = None
    if completed.stdout.strip():
        data = strict_json(completed.stdout)
    return ApiResult(completed.returncode, data, completed.stderr[-4096:])


def _require_success(label: str, result: ApiResult) -> Any:
    if result.returncode != 0:
        raise GovernanceError(f"{label} failed: {result.stderr.strip()}")
    return result.data


def _rule_map(rules: Iterable[Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for entry in rules:
        if not isinstance(entry, dict) or not isinstance(entry.get("type"), str):
            raise GovernanceError("ruleset contains a malformed rule")
        rule_type = entry["type"]
        if rule_type in result:
            raise GovernanceError(f"duplicate ruleset rule {rule_type!r}")
        result[rule_type] = entry
    return result


def _verify_check_bindings(
    entries: Any,
    *,
    integration_field: str,
    label: str,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(entries, list):
        return [f"{label} check bindings are absent"]
    observed: dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append(f"{label} contains a malformed check binding")
            continue
        context = entry.get("context")
        integration_id = entry.get(integration_field)
        if not isinstance(context, str) or not context:
            errors.append(f"{label} contains a check without a context")
            continue
        if context in observed:
            errors.append(f"{label} contains duplicate context {context!r}")
            continue
        if type(integration_id) is not int:
            errors.append(f"{label} context {context!r} has no exact integration binding")
            continue
        observed[context] = integration_id
        if integration_id != GITHUB_ACTIONS_APP_ID:
            errors.append(
                f"{label} context {context!r} is bound to app {integration_id}, "
                f"not GitHub Actions app {GITHUB_ACTIONS_APP_ID}"
            )
    missing = sorted(set(REQUIRED_CHECKS) - set(observed))
    unexpected = sorted(set(observed) - set(REQUIRED_CHECKS))
    if missing:
        errors.append(f"{label} required checks missing: {missing}")
    if unexpected:
        errors.append(f"{label} unexpected checks present: {unexpected}")
    return errors


def verify_ruleset(ruleset: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if ruleset.get("name") != RULESET_NAME:
        errors.append("named repository ruleset is absent")
    if ruleset.get("target") != "branch":
        errors.append("ruleset does not target branches")
    if ruleset.get("enforcement") != "active":
        errors.append("ruleset is not active")
    if ruleset.get("bypass_actors") != []:
        errors.append("ruleset bypass actor set is not exactly empty")

    conditions = ruleset.get("conditions")
    if not isinstance(conditions, dict):
        errors.append("ruleset conditions are absent")
    else:
        ref_name = conditions.get("ref_name")
        if not isinstance(ref_name, dict):
            errors.append("ruleset ref-name condition is absent")
        else:
            if ref_name.get("include") != ["~DEFAULT_BRANCH"]:
                errors.append("ruleset default-branch include is not exact")
            if ref_name.get("exclude") != []:
                errors.append("ruleset default-branch exclusions are not empty")

    try:
        rules = _rule_map(ruleset.get("rules", []))
    except GovernanceError as error:
        errors.append(str(error))
        rules = {}
    expected_rule_types = {
        "deletion",
        "non_fast_forward",
        "required_signatures",
        "pull_request",
        "required_status_checks",
    }
    missing_rules = sorted(expected_rule_types - set(rules))
    if missing_rules:
        errors.append(f"ruleset rules missing: {missing_rules}")

    pull_request = rules.get("pull_request", {}).get("parameters")
    if not isinstance(pull_request, dict):
        errors.append("pull-request ruleset parameters are absent")
    else:
        expected = {
            "allowed_merge_methods": ["merge"],
            "dismiss_stale_reviews_on_push": True,
            "require_code_owner_review": True,
            "require_last_push_approval": True,
            "required_approving_review_count": 2,
            "required_review_thread_resolution": True,
        }
        for key, value in expected.items():
            if pull_request.get(key) != value:
                errors.append(f"ruleset pull-request control {key} is not {value!r}")

    statuses = rules.get("required_status_checks", {}).get("parameters")
    if not isinstance(statuses, dict):
        errors.append("required-status ruleset parameters are absent")
    else:
        if statuses.get("strict_required_status_checks_policy") is not True:
            errors.append("ruleset status checks are not strict with the live base")
        if statuses.get("do_not_enforce_on_create") is not False:
            errors.append("ruleset status checks are not enforced on creation")
        errors.extend(
            _verify_check_bindings(
                statuses.get("required_status_checks"),
                integration_field="integration_id",
                label="ruleset",
            )
        )
    return errors


def _require_enabled_object(
    source: dict[str, Any],
    key: str,
    expected: bool,
    errors: list[str],
) -> None:
    value = source.get(key)
    if not isinstance(value, dict) or set(value) != {"enabled"}:
        errors.append(f"{key} readback is absent or malformed")
        return
    if value.get("enabled") is not expected:
        errors.append(f"{key} enabled is not {expected}")


def verify_protection(branch: dict[str, Any], protection: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if branch.get("name") != DEFAULT_BRANCH or branch.get("protected") is not True:
        errors.append("main is not reported protected")

    checks = protection.get("required_status_checks")
    if not isinstance(checks, dict):
        errors.append("strict required status checks are absent")
    else:
        if checks.get("strict") is not True:
            errors.append("strict required status checks are absent")
        errors.extend(
            _verify_check_bindings(
                checks.get("checks"),
                integration_field="app_id",
                label="classic protection",
            )
        )
        if "checks" not in checks and checks.get("contexts"):
            errors.append("legacy context-only required checks are not admissible")

    reviews = protection.get("required_pull_request_reviews")
    if not isinstance(reviews, dict):
        errors.append("required pull-request reviews are absent")
    else:
        expected = {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": True,
            "require_last_push_approval": True,
            "required_approving_review_count": 2,
        }
        for key, value in expected.items():
            if reviews.get(key) != value:
                errors.append(f"review control {key} is not {value!r}")
        for key in ("dismissal_restrictions", "bypass_pull_request_allowances"):
            value = reviews.get(key)
            if value not in ({}, {"users": [], "teams": [], "apps": []}):
                errors.append(f"review control {key} is not empty")

    _require_enabled_object(protection, "enforce_admins", True, errors)
    _require_enabled_object(
        protection, "required_conversation_resolution", True, errors
    )
    _require_enabled_object(protection, "allow_force_pushes", False, errors)
    _require_enabled_object(protection, "allow_deletions", False, errors)
    _require_enabled_object(protection, "required_signatures", True, errors)
    return errors


def verify_reviewer_accounts(accounts: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if set(accounts) != set(REVIEWER_ACCOUNTS):
        errors.append("resolved reviewer-account set is not exact")
    for login, expected_id in REVIEWER_ACCOUNTS.items():
        account = accounts.get(login)
        if not isinstance(account, dict):
            errors.append(f"reviewer account {login} is absent")
            continue
        if account.get("login") != login:
            errors.append(f"reviewer account {login} login mismatch")
        if account.get("id") != expected_id:
            errors.append(f"reviewer account {login} id mismatch")
        if account.get("type") != "User":
            errors.append(f"reviewer account {login} is not a User")
    return errors


def _extract_environment_reviewer(entry: Any) -> tuple[int, str, str] | None:
    if not isinstance(entry, dict):
        return None
    nested = entry.get("reviewer")
    source = nested if isinstance(nested, dict) else entry
    reviewer_id = source.get("id")
    login = source.get("login")
    entry_type = entry.get("type", source.get("type"))
    source_type = source.get("type", entry_type)
    if (
        type(reviewer_id) is not int
        or not isinstance(login, str)
        or entry_type != "User"
        or source_type != "User"
    ):
        return None
    return reviewer_id, login, "User"


def verify_environment(
    name: str,
    environment: dict[str, Any],
    reviewer_accounts: dict[str, Any] | None = None,
) -> list[str]:
    errors: list[str] = []
    if environment.get("name") != name:
        errors.append(f"environment {name} identity mismatch")
    branch_policy = environment.get("deployment_branch_policy")
    if not isinstance(branch_policy, dict):
        errors.append(f"environment {name} branch policy is absent")
    else:
        if branch_policy.get("protected_branches") is not True:
            errors.append(f"environment {name} is not restricted to protected branches")
        if branch_policy.get("custom_branch_policies") is not False:
            errors.append(f"environment {name} enables custom branch policies")

    reviewer_rules = [
        rule
        for rule in environment.get("protection_rules", [])
        if isinstance(rule, dict) and rule.get("type") == "required_reviewers"
    ]
    if len(reviewer_rules) != 1:
        errors.append(
            f"environment {name} requires exactly one required-reviewer rule"
        )
        return errors
    rule = reviewer_rules[0]
    if rule.get("prevent_self_review") is not True:
        errors.append(f"environment {name} permits self review")
    raw_reviewers = rule.get("reviewers")
    if not isinstance(raw_reviewers, list):
        errors.append(f"environment {name} reviewer list is absent")
        return errors

    observed: dict[int, str] = {}
    for entry in raw_reviewers:
        extracted = _extract_environment_reviewer(entry)
        if extracted is None:
            errors.append(f"environment {name} contains a malformed or non-user reviewer")
            continue
        reviewer_id, login, _ = extracted
        if reviewer_id in observed:
            errors.append(f"environment {name} duplicates reviewer {reviewer_id}")
            continue
        observed[reviewer_id] = login
    expected_by_id = {value: key for key, value in REVIEWER_ACCOUNTS.items()}
    if observed != expected_by_id:
        missing = sorted(set(expected_by_id) - set(observed))
        extra = sorted(set(observed) - set(expected_by_id))
        if missing:
            errors.append(f"environment {name} reviewers missing: {missing}")
        if extra:
            errors.append(f"environment {name} unauthorized reviewers present: {extra}")
        for reviewer_id in sorted(set(observed) & set(expected_by_id)):
            if observed[reviewer_id] != expected_by_id[reviewer_id]:
                errors.append(
                    f"environment {name} reviewer {reviewer_id} login mismatch"
                )
    if reviewer_accounts is not None:
        errors.extend(verify_reviewer_accounts(reviewer_accounts))
    return errors


def verify_repository_settings(repository: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key, value in repository_merge_payload().items():
        if repository.get(key) is not value:
            errors.append(f"repository setting {key} is not {value}")
    return errors


def _parse_utc(value: Any, label: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value
    ):
        errors.append(f"{label} is not a strict UTC timestamp")
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(
            tzinfo=timezone.utc
        )
    except ValueError:
        errors.append(f"{label} is invalid")
        return None


def _role_index(
    roles: Any, errors: list[str]
) -> tuple[dict[str, dict[int, str]], set[int]]:
    if not isinstance(roles, dict) or set(roles) != set(SEPARATED_ROLES):
        errors.append("role_identities field set is not exact")
        return {}, set()
    result: dict[str, dict[int, str]] = {}
    all_ids: set[int] = set()
    for role in SEPARATED_ROLES:
        values = roles.get(role)
        if not isinstance(values, list) or not values:
            errors.append(f"role {role} has no bound identity")
            continue
        role_values: dict[int, str] = {}
        for value in values:
            if not isinstance(value, dict) or set(value) != ROLE_IDENTITY_FIELDS:
                errors.append(f"role {role} contains a malformed identity")
                continue
            identity = value.get("id")
            login = value.get("login")
            if type(identity) is not int or identity <= 0:
                errors.append(f"role {role} contains an invalid identity")
                continue
            if not isinstance(login, str) or not login:
                errors.append(f"role {role} contains an invalid login")
                continue
            if identity in role_values:
                errors.append(f"role {role} contains duplicate identity {identity}")
                continue
            if identity in all_ids:
                errors.append(f"identity {identity} is shared across separated roles")
            role_values[identity] = login
            all_ids.add(identity)
        result[role] = role_values
    return result, all_ids


def validate_probe_evidence(
    packet: dict[str, Any],
    main_sha: str,
    *,
    signature_verified: bool = False,
    public_key_sha256: str | None = None,
    now: datetime | None = None,
) -> list[str]:
    """Validate a detached, independently signed D0T-03 probe attestation."""

    errors: list[str] = []
    if set(packet) != PROBE_TOP_LEVEL_FIELDS:
        errors.append("probe packet top-level field set is not exact")
    if packet.get("schema_version") != 2:
        errors.append("probe schema_version is not 2")
    if packet.get("repository") != REPOSITORY:
        errors.append("probe repository identity mismatch")
    if packet.get("main_sha") != main_sha or not SHA_RE.fullmatch(main_sha):
        errors.append("probe packet is not bound to the current main SHA")
    if signature_verified is not True:
        errors.append("probe attestation detached signature is not verified")
    if not isinstance(public_key_sha256, str) or not SHA256_RE.fullmatch(
        public_key_sha256
    ):
        errors.append("probe attestation public-key digest is not externally bound")

    now_value = now or datetime.now(timezone.utc)
    issued_at = _parse_utc(packet.get("issued_at"), "probe issued_at", errors)
    if issued_at is not None:
        if issued_at > now_value + MAX_CLOCK_SKEW:
            errors.append("probe packet is from the future")
        if now_value - issued_at > MAX_PROBE_AGE:
            errors.append("probe packet is stale")

    roles, all_role_ids = _role_index(packet.get("role_identities"), errors)
    attestor = packet.get("attestor")
    if not isinstance(attestor, dict) or set(attestor) != ATTESTOR_FIELDS:
        errors.append("probe attestor identity is malformed")
    else:
        attestor_id = attestor.get("id")
        if (
            type(attestor_id) is not int
            or attestor_id <= 0
            or not isinstance(attestor.get("login"), str)
            or not attestor["login"]
            or attestor.get("role") != "independent_governance_attestor"
        ):
            errors.append("probe attestor identity is invalid")
        elif attestor_id in all_role_ids:
            errors.append("probe attestor is not independent of operational roles")

    probes = packet.get("probes")
    if not isinstance(probes, list):
        return [*errors, "probe list is absent"]
    observed: dict[str, dict[str, Any]] = {}
    for probe in probes:
        if not isinstance(probe, dict) or set(probe) != PROBE_FIELDS:
            errors.append("probe entry field set is not exact")
            continue
        probe_id = probe.get("id")
        if not isinstance(probe_id, str) or probe_id not in PROBE_EXPECTATIONS:
            errors.append(f"unknown probe id {probe_id!r}")
            continue
        if probe_id in observed:
            errors.append(f"duplicate probe {probe_id}")
            continue
        observed[probe_id] = probe

    expected_ids = set(PROBE_EXPECTATIONS)
    missing = sorted(expected_ids - set(observed))
    if missing:
        errors.append(f"required probes absent: {missing}")
    extra = sorted(set(observed) - expected_ids)
    if extra:
        errors.append(f"unexpected probes present: {extra}")

    for probe_id, probe in observed.items():
        expected_result, expected_operation, expected_role = PROBE_EXPECTATIONS[probe_id]
        if probe.get("result") != expected_result:
            errors.append(f"probe {probe_id} result is not {expected_result}")
        if probe.get("operation") != expected_operation:
            errors.append(f"probe {probe_id} operation mismatch")
        if probe.get("actor_role") != expected_role:
            errors.append(f"probe {probe_id} actor role mismatch")
        actor_id = probe.get("actor_id")
        actor_login = probe.get("actor_login")
        expected_actors = roles.get(expected_role, {})
        if (
            type(actor_id) is not int
            or actor_id not in expected_actors
            or expected_actors.get(actor_id) != actor_login
        ):
            errors.append(f"probe {probe_id} actor is not bound to role {expected_role}")
        if probe.get("subject_sha") != main_sha:
            errors.append(f"probe {probe_id} subject SHA is unrelated to current main")
        evidence_url = probe.get("evidence_api_url")
        if not isinstance(evidence_url, str) or not IMMUTABLE_RUN_ATTEMPT_RE.fullmatch(
            evidence_url
        ):
            errors.append(f"probe {probe_id} evidence URL is not an immutable run attempt")
        digest = probe.get("evidence_sha256")
        if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
            errors.append(f"probe {probe_id} evidence digest is invalid")
        observed_at = _parse_utc(
            probe.get("observed_at"), f"probe {probe_id} observed_at", errors
        )
        if observed_at is not None and issued_at is not None:
            if observed_at > issued_at + MAX_CLOCK_SKEW:
                errors.append(f"probe {probe_id} occurs after attestation issuance")
            if issued_at - observed_at > MAX_PROBE_AGE:
                errors.append(f"probe {probe_id} evidence is stale")
    return errors


def _regular_file_bytes(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise GovernanceError(f"{label} is not a regular non-symlink file")
    return path.read_bytes()


def verify_detached_signature(
    packet_path: Path,
    signature_path: Path,
    public_key_path: Path,
    expected_public_key_sha256: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    """Verify an externally rooted detached signature over exact packet bytes."""

    if not SHA256_RE.fullmatch(expected_public_key_sha256):
        raise GovernanceError("expected probe public-key digest is invalid")
    _regular_file_bytes(packet_path, "probe packet")
    _regular_file_bytes(signature_path, "probe signature")
    public_key = _regular_file_bytes(public_key_path, "probe public key")
    observed = hashlib.sha256(public_key).hexdigest()
    if observed != expected_public_key_sha256:
        raise GovernanceError("probe public-key digest does not match external trust root")
    completed = runner(
        [
            "openssl",
            "dgst",
            "-sha256",
            "-verify",
            str(public_key_path),
            "-signature",
            str(signature_path),
            str(packet_path),
        ],
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise GovernanceError(
            "probe detached signature verification failed: "
            + (completed.stderr or completed.stdout).strip()[-1024:]
        )
    return observed


def readback(api: Callable[[list[str], dict[str, Any] | None], ApiResult]) -> dict[str, Any]:
    repository = _require_success(
        "repository readback", api([f"repos/{REPOSITORY}"], None)
    )
    branch = _require_success(
        "main branch readback",
        api([f"repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}"], None),
    )
    protection = _require_success(
        "branch protection readback",
        api([f"repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}/protection"], None),
    )
    signatures = _require_success(
        "required-signatures readback",
        api(
            [
                f"repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}/"
                "protection/required_signatures"
            ],
            None,
        ),
    )
    protection = {**protection, "required_signatures": signatures}
    listed_rulesets = _require_success(
        "ruleset list readback",
        api([f"repos/{REPOSITORY}/rulesets?includes_parents=true"], None),
    )
    candidates = [
        entry
        for entry in listed_rulesets
        if isinstance(entry, dict) and entry.get("name") == RULESET_NAME
    ]
    full_rulesets: list[dict[str, Any]] = []
    for entry in candidates:
        ruleset_id = entry.get("id")
        if type(ruleset_id) is int:
            full_rulesets.append(
                _require_success(
                    f"ruleset {ruleset_id} readback",
                    api([f"repos/{REPOSITORY}/rulesets/{ruleset_id}"], None),
                )
            )

    reviewer_accounts: dict[str, Any] = {}
    for login in REVIEWER_ACCOUNTS:
        reviewer_accounts[login] = _require_success(
            f"reviewer account {login} readback",
            api([f"users/{login}"], None),
        )

    environments: dict[str, Any] = {}
    for name in ENVIRONMENTS:
        environments[name] = _require_success(
            f"environment {name} readback",
            api([f"repos/{REPOSITORY}/environments/{name}"], None),
        )

    errors = verify_repository_settings(repository)
    errors.extend(verify_protection(branch, protection))
    errors.extend(verify_reviewer_accounts(reviewer_accounts))
    if len(full_rulesets) != 1:
        errors.append(
            f"expected one active named repository ruleset, observed {len(full_rulesets)}"
        )
    else:
        errors.extend(verify_ruleset(full_rulesets[0]))
    for name, environment in environments.items():
        errors.extend(verify_environment(name, environment, reviewer_accounts))
    return {
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repository": REPOSITORY,
        "main_sha": branch.get("commit", {}).get("sha"),
        "github_actions_app_id": GITHUB_ACTIONS_APP_ID,
        "reviewer_accounts": reviewer_accounts,
        "repository_settings": repository,
        "branch": branch,
        "protection": protection,
        "rulesets": full_rulesets,
        "environments": environments,
        "verification_errors": errors,
    }


def apply(api: Callable[[list[str], dict[str, Any] | None], ApiResult]) -> None:
    current = _require_success(
        "ruleset discovery",
        api([f"repos/{REPOSITORY}/rulesets?includes_parents=false"], None),
    )
    matching = [
        item
        for item in current
        if isinstance(item, dict)
        and item.get("name") == RULESET_NAME
        and item.get("source_type") in (None, "Repository")
    ]
    if len(matching) > 1:
        raise GovernanceError("multiple repository rulesets compete for D0T-03 authority")
    if matching:
        ruleset_id = matching[0].get("id")
        if type(ruleset_id) is not int:
            raise GovernanceError("named repository ruleset has no numeric id")
        _require_success(
            "repository ruleset update",
            api(
                ["-X", "PUT", f"repos/{REPOSITORY}/rulesets/{ruleset_id}"],
                ruleset_payload(),
            ),
        )
    else:
        _require_success(
            "repository ruleset creation",
            api(["-X", "POST", f"repos/{REPOSITORY}/rulesets"], ruleset_payload()),
        )

    _require_success(
        "classic branch protection",
        api(
            [
                "-X",
                "PUT",
                f"repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}/protection",
            ],
            branch_protection_payload(),
        ),
    )
    _require_success(
        "required commit signatures",
        api(
            [
                "-X",
                "POST",
                f"repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}/"
                "protection/required_signatures",
            ],
            None,
        ),
    )
    _require_success(
        "repository merge settings",
        api(["-X", "PATCH", f"repos/{REPOSITORY}"], repository_merge_payload()),
    )
    for name in ENVIRONMENTS:
        _require_success(
            f"protected environment {name}",
            api(
                ["-X", "PUT", f"repos/{REPOSITORY}/environments/{name}"],
                environment_payload(),
            ),
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/governance/d0t03-live-readback.json"),
    )
    parser.add_argument("--probe-evidence", type=Path)
    parser.add_argument("--probe-signature", type=Path)
    parser.add_argument("--probe-public-key", type=Path)
    parser.add_argument("--expected-probe-public-key-sha256")
    parser.add_argument("--check-config", action="store_true")
    return parser.parse_args()


def _synthetic_accounts() -> dict[str, dict[str, Any]]:
    return {
        login: {"login": login, "id": reviewer_id, "type": "User"}
        for login, reviewer_id in REVIEWER_ACCOUNTS.items()
    }


def _synthetic_environment(name: str) -> dict[str, Any]:
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
                    for login, reviewer_id in REVIEWER_ACCOUNTS.items()
                ],
            }
        ],
    }


def static_configuration_errors() -> list[str]:
    errors = verify_ruleset(ruleset_payload())
    payload = branch_protection_payload()
    synthetic_protection = {
        **payload,
        "enforce_admins": {"enabled": True},
        "required_conversation_resolution": {"enabled": True},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
        "required_signatures": {"enabled": True},
    }
    errors.extend(
        verify_protection(
            {"name": DEFAULT_BRANCH, "protected": True}, synthetic_protection
        )
    )
    accounts = _synthetic_accounts()
    errors.extend(verify_reviewer_accounts(accounts))
    for name in ENVIRONMENTS:
        errors.extend(verify_environment(name, _synthetic_environment(name), accounts))
    expected_checks = {
        "repository-contracts",
        "rust",
        "repository-contracts-prospective-merge",
        "rust-prospective-merge",
    }
    if set(REQUIRED_CHECKS) != expected_checks:
        errors.append("required check inventory is not closed")
    return errors


def main() -> int:
    args = parse_args()
    if args.check_config:
        errors = static_configuration_errors()
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        print("D0T-03 controller configuration is closed and valid")
        return 0

    if args.apply:
        apply(_run_gh)
    evidence = readback(_run_gh)
    probe_packet: dict[str, Any] | None = None
    probe_errors: list[str] = []
    key_digest: str | None = None
    required_probe_paths = (
        args.probe_evidence,
        args.probe_signature,
        args.probe_public_key,
        args.expected_probe_public_key_sha256,
    )
    if any(value is None for value in required_probe_paths):
        probe_errors.append(
            "signed independent probe packet, signature, public key, or external "
            "public-key digest is absent"
        )
    else:
        try:
            key_digest = verify_detached_signature(
                args.probe_evidence,
                args.probe_signature,
                args.probe_public_key,
                args.expected_probe_public_key_sha256,
            )
            loaded = strict_json(args.probe_evidence.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                raise GovernanceError("probe evidence root must be an object")
            probe_packet = loaded
            probe_errors.extend(
                validate_probe_evidence(
                    loaded,
                    str(evidence.get("main_sha")),
                    signature_verified=True,
                    public_key_sha256=key_digest,
                )
            )
        except (OSError, UnicodeError, GovernanceError) as error:
            probe_errors.append(str(error))

    evidence["probe_evidence"] = probe_packet
    evidence["probe_public_key_sha256"] = key_digest
    evidence["probe_verification_errors"] = probe_errors
    evidence["all_gaps_closed"] = (
        not evidence["verification_errors"] and not probe_errors
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    combined = [*evidence["verification_errors"], *probe_errors]
    if combined:
        for error in combined:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(
        f"D0T-03 live governance and signed independent probes verified at "
        f"{evidence['main_sha']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
