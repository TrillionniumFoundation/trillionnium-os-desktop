#!/usr/bin/env python3
"""Apply and verify D0T-03 GitHub governance controls fail closed.

Source validation is not live-governance evidence. Live closure requires exact
Administration readback, an externally rooted signed attestation from an
independent governance observer, and a stable default-branch SHA for the whole
readback/attestation transaction.
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
REVIEWER_ACCOUNTS = {"Franksudoman": 273670192, "Tomasrgbsf": 273673612}
REVIEWERS = tuple(REVIEWER_ACCOUNTS.values())
ENVIRONMENTS = (
    "qualification", "hardware-attestation", "release-signing", "production-publication"
)
REQUIRED_CHECKS = (
    "repository-contracts", "rust",
    "repository-contracts-prospective-merge", "rust-prospective-merge",
)
REQUIRED_NEGATIVE_PROBES = (
    "direct_push_rejected", "force_push_rejected", "branch_deletion_rejected",
    "missing_required_check_rejected", "stale_approval_rejected",
    "missing_codeowner_rejected", "insufficient_approvals_rejected",
    "unresolved_conversation_rejected", "administrator_bypass_rejected",
    "unauthorized_environment_rejected", "environment_self_approval_rejected",
)
REQUIRED_POSITIVE_PROBES = (
    "authorized_protected_merge_succeeded", "protected_publication_succeeded"
)
SEPARATED_ROLES = (
    "author", "reviewer", "builder", "signer", "attestor", "promoter", "publisher"
)
PROBE_EXPECTATIONS = {
    "direct_push_rejected": ("rejected", "git.push.default_branch", "author"),
    "force_push_rejected": ("rejected", "git.force_push.default_branch", "author"),
    "branch_deletion_rejected": ("rejected", "git.delete.default_branch", "author"),
    "missing_required_check_rejected": ("rejected", "pull_request.merge.missing_required_check", "promoter"),
    "stale_approval_rejected": ("rejected", "pull_request.merge.stale_approval", "promoter"),
    "missing_codeowner_rejected": ("rejected", "pull_request.merge.missing_codeowner", "promoter"),
    "insufficient_approvals_rejected": ("rejected", "pull_request.merge.insufficient_approvals", "promoter"),
    "unresolved_conversation_rejected": ("rejected", "pull_request.merge.unresolved_conversation", "promoter"),
    "administrator_bypass_rejected": ("rejected", "pull_request.merge.administrator_bypass", "promoter"),
    "unauthorized_environment_rejected": ("rejected", "deployment.environment.unauthorized", "promoter"),
    "environment_self_approval_rejected": ("rejected", "deployment.environment.self_approval", "promoter"),
    "authorized_protected_merge_succeeded": ("succeeded", "pull_request.merge.authorized_protected_path", "promoter"),
    "protected_publication_succeeded": ("succeeded", "deployment.environment.protected_publication", "publisher"),
}

# v3 deliberately makes the external attestor signature the evidence authority.
# It contains no GitHub URL or server-object digest that this controller cannot verify.
PROBE_SCHEMA_VERSION = 3
PROBE_EVIDENCE_AUTHORITY = "external_independent_governance_attestor"
PROBE_TOP_LEVEL_FIELDS = {
    "schema_version", "repository", "main_sha", "issued_at", "evidence_authority",
    "attestor", "probes", "role_identities",
}
PROBE_FIELDS = {
    "id", "result", "operation", "actor_id", "actor_login", "actor_role",
    "observed_at", "subject_sha", "observation_id",
}
ATTESTOR_FIELDS = {"id", "login", "role"}
ROLE_IDENTITY_FIELDS = {"id", "login"}
SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
OBSERVATION_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$")
MAX_PROBE_AGE = timedelta(hours=24)
MAX_CLOCK_SKEW = timedelta(minutes=5)


class GovernanceError(RuntimeError):
    """A required governance fact could not be proved."""


@dataclass(frozen=True)
class ApiResult:
    returncode: int
    data: Any
    stderr: str


def strict_json(text: str) -> Any:
    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in values:
            if key in result:
                raise GovernanceError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    def constant(value: str) -> None:
        raise GovernanceError(f"non-JSON numeric constant {value!r}")

    return json.loads(text, object_pairs_hook=pairs, parse_constant=constant)


def ruleset_payload() -> dict[str, Any]:
    checks = [
        {"context": context, "integration_id": GITHUB_ACTIONS_APP_ID}
        for context in REQUIRED_CHECKS
    ]
    return {
        "name": RULESET_NAME, "target": "branch", "enforcement": "active",
        "bypass_actors": [],
        "conditions": {"ref_name": {"include": ["~DEFAULT_BRANCH"], "exclude": []}},
        "rules": [
            {"type": "deletion"}, {"type": "non_fast_forward"},
            {"type": "required_signatures"},
            {"type": "pull_request", "parameters": {
                "allowed_merge_methods": ["merge"],
                "dismiss_stale_reviews_on_push": True,
                "require_code_owner_review": True,
                "require_last_push_approval": True,
                "required_approving_review_count": 2,
                "required_review_thread_resolution": True,
            }},
            {"type": "required_status_checks", "parameters": {
                "do_not_enforce_on_create": False,
                "required_status_checks": checks,
                "strict_required_status_checks_policy": True,
            }},
        ],
    }


def branch_protection_payload() -> dict[str, Any]:
    return {
        "required_status_checks": {"strict": True, "checks": [
            {"context": context, "app_id": GITHUB_ACTIONS_APP_ID}
            for context in REQUIRED_CHECKS
        ]},
        "enforce_admins": True,
        "required_pull_request_reviews": {
            "dismissal_restrictions": {}, "dismiss_stale_reviews": True,
            "require_code_owner_reviews": True, "required_approving_review_count": 2,
            "require_last_push_approval": True, "bypass_pull_request_allowances": {},
        },
        "restrictions": None, "required_linear_history": False,
        "allow_force_pushes": False, "allow_deletions": False,
        "block_creations": False, "required_conversation_resolution": True,
        "lock_branch": False, "allow_fork_syncing": False,
    }


def environment_payload() -> dict[str, Any]:
    return {
        "wait_timer": 0, "prevent_self_review": True,
        "reviewers": [{"type": "User", "id": value} for value in REVIEWERS],
        "deployment_branch_policy": {
            "protected_branches": True, "custom_branch_policies": False,
        },
    }


def repository_merge_payload() -> dict[str, Any]:
    return {
        "allow_merge_commit": True, "allow_squash_merge": False,
        "allow_rebase_merge": False, "allow_auto_merge": True,
        "delete_branch_on_merge": True, "allow_update_branch": True,
    }


def _run_gh(arguments: list[str], body: dict[str, Any] | None = None) -> ApiResult:
    command = ["gh", "api", *arguments]
    encoded = None
    if body is not None:
        command += ["--input", "-"]
        encoded = json.dumps(body, allow_nan=False)
    completed = subprocess.run(
        command, input=encoded, text=True, capture_output=True, check=False
    )
    data = strict_json(completed.stdout) if completed.stdout.strip() else None
    return ApiResult(completed.returncode, data, completed.stderr[-4096:])


def _require(label: str, result: ApiResult) -> Any:
    if result.returncode:
        raise GovernanceError(f"{label} failed: {result.stderr.strip()}")
    return result.data


def _rule_map(entries: Iterable[Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("type"), str):
            raise GovernanceError("ruleset contains a malformed rule")
        kind = entry["type"]
        if kind in result:
            raise GovernanceError(f"duplicate ruleset rule {kind!r}")
        result[kind] = entry
    return result


def _verify_check_bindings(entries: Any, field: str, label: str) -> list[str]:
    if not isinstance(entries, list):
        return [f"{label} check bindings are absent"]
    errors: list[str] = []
    observed: dict[str, int] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            errors.append(f"{label} contains a malformed check binding")
            continue
        context, app_id = entry.get("context"), entry.get(field)
        if not isinstance(context, str) or not context:
            errors.append(f"{label} contains a check without a context")
        elif context in observed:
            errors.append(f"{label} contains duplicate context {context!r}")
        elif type(app_id) is not int:
            errors.append(f"{label} context {context!r} has no exact integration binding")
        else:
            observed[context] = app_id
            if app_id != GITHUB_ACTIONS_APP_ID:
                errors.append(f"{label} context {context!r} is bound to foreign app {app_id}")
    if set(observed) != set(REQUIRED_CHECKS):
        errors.append(f"{label} required check set is not exact")
    return errors


def verify_ruleset(value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key, expected in (
        ("name", RULESET_NAME), ("target", "branch"), ("enforcement", "active"),
        ("bypass_actors", []),
    ):
        if value.get(key) != expected:
            errors.append(f"ruleset {key} is not exact")
    condition = value.get("conditions", {}).get("ref_name")
    if condition != {"include": ["~DEFAULT_BRANCH"], "exclude": []}:
        errors.append("ruleset default-branch condition is not exact")
    try:
        rules = _rule_map(value.get("rules", []))
    except GovernanceError as error:
        errors.append(str(error)); rules = {}
    expected_types = {
        "deletion", "non_fast_forward", "required_signatures",
        "pull_request", "required_status_checks",
    }
    if set(rules) != expected_types:
        errors.append("ruleset rule type set is not exact")
    expected_pr = {
        "allowed_merge_methods": ["merge"], "dismiss_stale_reviews_on_push": True,
        "require_code_owner_review": True, "require_last_push_approval": True,
        "required_approving_review_count": 2,
        "required_review_thread_resolution": True,
    }
    if rules.get("pull_request", {}).get("parameters") != expected_pr:
        errors.append("pull-request ruleset parameters are not exact")
    statuses = rules.get("required_status_checks", {}).get("parameters")
    if not isinstance(statuses, dict):
        errors.append("required-status ruleset parameters are absent")
    else:
        if statuses.get("strict_required_status_checks_policy") is not True:
            errors.append("ruleset status checks are not strict")
        if statuses.get("do_not_enforce_on_create") is not False:
            errors.append("ruleset checks are not enforced on creation")
        errors += _verify_check_bindings(
            statuses.get("required_status_checks"), "integration_id", "ruleset"
        )
    return errors


def _enabled(source: dict[str, Any], key: str, expected: bool, errors: list[str]) -> None:
    value = source.get(key)
    if not isinstance(value, dict) or set(value) != {"enabled"}:
        errors.append(f"{key} readback is absent or malformed")
    elif value.get("enabled") is not expected:
        errors.append(f"{key} enabled is not {expected}")


def verify_protection(branch: dict[str, Any], value: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if branch.get("name") != DEFAULT_BRANCH or branch.get("protected") is not True:
        errors.append("main is not reported protected")
    checks = value.get("required_status_checks")
    if not isinstance(checks, dict) or checks.get("strict") is not True:
        errors.append("strict required status checks are absent")
    else:
        errors += _verify_check_bindings(checks.get("checks"), "app_id", "classic protection")
        if "checks" not in checks and checks.get("contexts"):
            errors.append("legacy context-only checks are not admissible")
    reviews = value.get("required_pull_request_reviews")
    expected = {
        "dismiss_stale_reviews": True, "require_code_owner_reviews": True,
        "require_last_push_approval": True, "required_approving_review_count": 2,
    }
    if not isinstance(reviews, dict):
        errors.append("required pull-request reviews are absent")
    else:
        for key, wanted in expected.items():
            if reviews.get(key) != wanted:
                errors.append(f"review control {key} is not {wanted!r}")
        for key in ("dismissal_restrictions", "bypass_pull_request_allowances"):
            if reviews.get(key) not in ({}, {"users": [], "teams": [], "apps": []}):
                errors.append(f"review control {key} is not empty")
    for key, wanted in (
        ("enforce_admins", True), ("required_conversation_resolution", True),
        ("allow_force_pushes", False), ("allow_deletions", False),
        ("required_signatures", True),
    ):
        _enabled(value, key, wanted, errors)
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
        if (
            account.get("login") != login
            or account.get("id") != expected_id
            or account.get("type") != "User"
        ):
            errors.append(f"reviewer account {login} identity mismatch")
    return errors


def _reviewer(entry: Any) -> tuple[int, str] | None:
    if not isinstance(entry, dict):
        return None
    source = entry.get("reviewer") if isinstance(entry.get("reviewer"), dict) else entry
    if entry.get("type", source.get("type")) != "User" or source.get("type", "User") != "User":
        return None
    identity, login = source.get("id"), source.get("login")
    return (identity, login) if type(identity) is int and isinstance(login, str) else None


def verify_environment(
    name: str, value: dict[str, Any], accounts: dict[str, Any] | None = None
) -> list[str]:
    errors: list[str] = []
    if value.get("name") != name:
        errors.append(f"environment {name} identity mismatch")
    if value.get("deployment_branch_policy") != {
        "protected_branches": True, "custom_branch_policies": False
    }:
        errors.append(f"environment {name} branch policy is not exact")
    rules = [
        rule for rule in value.get("protection_rules", [])
        if isinstance(rule, dict) and rule.get("type") == "required_reviewers"
    ]
    if len(rules) != 1:
        return [*errors, f"environment {name} requires exactly one reviewer rule"]
    if rules[0].get("prevent_self_review") is not True:
        errors.append(f"environment {name} permits self review")
    raw = rules[0].get("reviewers")
    if not isinstance(raw, list):
        return [*errors, f"environment {name} reviewer list is absent"]
    observed: dict[int, str] = {}
    for entry in raw:
        item = _reviewer(entry)
        if item is None:
            errors.append(f"environment {name} contains a malformed/non-user reviewer")
        elif item[0] in observed:
            errors.append(f"environment {name} duplicates reviewer {item[0]}")
        else:
            observed[item[0]] = item[1]
    if observed != {identity: login for login, identity in REVIEWER_ACCOUNTS.items()}:
        errors.append(f"environment {name} reviewer identity set is not exact")
    if accounts is not None:
        errors += verify_reviewer_accounts(accounts)
    return errors


def verify_repository_settings(value: dict[str, Any]) -> list[str]:
    return [
        f"repository setting {key} is not {wanted}"
        for key, wanted in repository_merge_payload().items()
        if value.get(key) is not wanted
    ]


def _utc(value: Any, label: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value):
        errors.append(f"{label} is not a strict UTC timestamp"); return None
    try:
        return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        errors.append(f"{label} is invalid"); return None


def _roles(value: Any, errors: list[str]) -> tuple[dict[str, dict[int, str]], set[int]]:
    if not isinstance(value, dict) or set(value) != set(SEPARATED_ROLES):
        errors.append("role_identities field set is not exact"); return {}, set()
    result: dict[str, dict[int, str]] = {}; all_ids: set[int] = set()
    for role in SEPARATED_ROLES:
        entries = value.get(role)
        if not isinstance(entries, list) or not entries:
            errors.append(f"role {role} has no bound identity"); continue
        bound: dict[int, str] = {}
        for entry in entries:
            if not isinstance(entry, dict) or set(entry) != ROLE_IDENTITY_FIELDS:
                errors.append(f"role {role} contains a malformed identity"); continue
            identity, login = entry.get("id"), entry.get("login")
            if type(identity) is not int or identity <= 0 or not isinstance(login, str) or not login:
                errors.append(f"role {role} contains an invalid identity"); continue
            if identity in bound or identity in all_ids:
                errors.append(f"identity {identity} is duplicated or shared across roles")
            bound[identity] = login; all_ids.add(identity)
        result[role] = bound
    return result, all_ids


def validate_probe_evidence(
    packet: dict[str, Any], main_sha: str, *, signature_verified: bool = False,
    public_key_sha256: str | None = None, expected_attestor_id: int | None = None,
    expected_attestor_login: str | None = None, now: datetime | None = None,
) -> list[str]:
    """Validate v3 signed-attestor evidence without pretending to verify GitHub objects."""
    errors: list[str] = []
    if not isinstance(packet, dict) or set(packet) != PROBE_TOP_LEVEL_FIELDS:
        errors.append("probe packet top-level field set is not exact")
    if packet.get("schema_version") != PROBE_SCHEMA_VERSION:
        errors.append(f"probe schema_version is not {PROBE_SCHEMA_VERSION}")
    if packet.get("evidence_authority") != PROBE_EVIDENCE_AUTHORITY:
        errors.append("probe evidence authority is not the external independent attestor")
    if packet.get("repository") != REPOSITORY:
        errors.append("probe repository identity mismatch")
    if packet.get("main_sha") != main_sha or not SHA_RE.fullmatch(main_sha):
        errors.append("probe packet is not bound to current main")
    if signature_verified is not True:
        errors.append("probe detached signature is not verified")
    if not isinstance(public_key_sha256, str) or not SHA256_RE.fullmatch(public_key_sha256):
        errors.append("probe public-key digest is not externally bound")
    if type(expected_attestor_id) is not int or expected_attestor_id <= 0:
        errors.append("expected attestor id is not externally bound")
    if not isinstance(expected_attestor_login, str) or not expected_attestor_login:
        errors.append("expected attestor login is not externally bound")

    now_value = now or datetime.now(timezone.utc)
    issued = _utc(packet.get("issued_at"), "probe issued_at", errors)
    if issued is not None:
        if issued > now_value + MAX_CLOCK_SKEW: errors.append("probe packet is from the future")
        if now_value - issued > MAX_PROBE_AGE: errors.append("probe packet is stale")
    roles, all_ids = _roles(packet.get("role_identities"), errors)
    attestor = packet.get("attestor")
    if not isinstance(attestor, dict) or set(attestor) != ATTESTOR_FIELDS:
        errors.append("probe attestor identity is malformed")
    else:
        identity, login = attestor.get("id"), attestor.get("login")
        if type(identity) is not int or identity <= 0 or not isinstance(login, str) or not login or attestor.get("role") != "independent_governance_attestor":
            errors.append("probe attestor identity is invalid")
        else:
            if identity != expected_attestor_id or login != expected_attestor_login:
                errors.append("probe attestor does not match externally bound identity")
            if identity in all_ids: errors.append("probe attestor is not independent of operational roles")

    entries = packet.get("probes")
    if not isinstance(entries, list):
        return [*errors, "probe list is absent"]
    observed: dict[str, dict[str, Any]] = {}; observation_ids: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != PROBE_FIELDS:
            errors.append("probe entry field set is not exact"); continue
        probe_id = entry.get("id")
        if not isinstance(probe_id, str) or probe_id not in PROBE_EXPECTATIONS:
            errors.append(f"unknown probe id {probe_id!r}"); continue
        if probe_id in observed:
            errors.append(f"duplicate probe {probe_id}"); continue
        observation_id = entry.get("observation_id")
        if not isinstance(observation_id, str) or not OBSERVATION_ID_RE.fullmatch(observation_id):
            errors.append(f"probe {probe_id} observation id is invalid")
        elif observation_id in observation_ids:
            errors.append(f"probe {probe_id} reuses an observation id")
        else:
            observation_ids.add(observation_id)
        observed[probe_id] = entry
    if set(observed) != set(PROBE_EXPECTATIONS):
        errors.append("probe inventory is not exact")
    for probe_id, entry in observed.items():
        result, operation, role = PROBE_EXPECTATIONS[probe_id]
        if entry.get("result") != result: errors.append(f"probe {probe_id} result mismatch")
        if entry.get("operation") != operation: errors.append(f"probe {probe_id} operation mismatch")
        if entry.get("actor_role") != role: errors.append(f"probe {probe_id} actor role mismatch")
        actor_id, actor_login = entry.get("actor_id"), entry.get("actor_login")
        if type(actor_id) is not int or roles.get(role, {}).get(actor_id) != actor_login:
            errors.append(f"probe {probe_id} actor is not bound to role {role}")
        if entry.get("subject_sha") != main_sha:
            errors.append(f"probe {probe_id} subject SHA is unrelated to current main")
        observed_at = _utc(entry.get("observed_at"), f"probe {probe_id} observed_at", errors)
        if observed_at is not None and issued is not None:
            if observed_at > issued + MAX_CLOCK_SKEW: errors.append(f"probe {probe_id} occurs after issuance")
            if issued - observed_at > MAX_PROBE_AGE: errors.append(f"probe {probe_id} is stale")
    return errors


def _regular(path: Path, label: str) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise GovernanceError(f"{label} is not a regular non-symlink file")
    return path.read_bytes()


def verify_detached_signature(
    packet: Path, signature: Path, public_key: Path, expected_key_sha256: str,
    *, runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    if not SHA256_RE.fullmatch(expected_key_sha256):
        raise GovernanceError("expected probe public-key digest is invalid")
    _regular(packet, "probe packet"); _regular(signature, "probe signature")
    observed = hashlib.sha256(_regular(public_key, "probe public key")).hexdigest()
    if observed != expected_key_sha256:
        raise GovernanceError("probe public-key digest does not match external trust root")
    completed = runner([
        "openssl", "dgst", "-sha256", "-verify", str(public_key),
        "-signature", str(signature), str(packet),
    ], text=True, capture_output=True, check=False)
    if completed.returncode:
        raise GovernanceError("probe detached signature verification failed: " + (completed.stderr or completed.stdout).strip()[-1024:])
    return observed


def _branch_sha(value: Any, label: str) -> str:
    sha = value.get("commit", {}).get("sha") if isinstance(value, dict) else None
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
        raise GovernanceError(f"{label} has no exact commit SHA")
    return sha


def read_current_main_sha(api: Callable[[list[str], dict[str, Any] | None], ApiResult]) -> str:
    value = _require("main branch readback", api([f"repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}"], None))
    return _branch_sha(value, "main branch readback")


def readback(api: Callable[[list[str], dict[str, Any] | None], ApiResult]) -> dict[str, Any]:
    repository = _require("repository readback", api([f"repos/{REPOSITORY}"], None))
    branch = _require("initial main readback", api([f"repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}"], None))
    main_sha = _branch_sha(branch, "initial main readback")
    protection = _require("branch protection readback", api([f"repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}/protection"], None))
    signatures = _require("required-signatures readback", api([f"repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}/protection/required_signatures"], None))
    protection = {**protection, "required_signatures": signatures}
    listed = _require("ruleset list readback", api([f"repos/{REPOSITORY}/rulesets?includes_parents=true"], None))
    matching = [item for item in listed if isinstance(item, dict) and item.get("name") == RULESET_NAME]
    rulesets = [
        _require(f"ruleset {item['id']} readback", api([f"repos/{REPOSITORY}/rulesets/{item['id']}"], None))
        for item in matching if type(item.get("id")) is int
    ]
    accounts = {
        login: _require(f"reviewer {login} readback", api([f"users/{login}"], None))
        for login in REVIEWER_ACCOUNTS
    }
    environments = {
        name: _require(f"environment {name} readback", api([f"repos/{REPOSITORY}/environments/{name}"], None))
        for name in ENVIRONMENTS
    }
    final_branch = _require("final readback main", api([f"repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}"], None))
    final_sha = _branch_sha(final_branch, "final readback main")
    errors = verify_repository_settings(repository) + verify_protection(branch, protection) + verify_reviewer_accounts(accounts)
    if len(rulesets) != 1: errors.append(f"expected one named ruleset, observed {len(rulesets)}")
    else: errors += verify_ruleset(rulesets[0])
    for name, value in environments.items(): errors += verify_environment(name, value, accounts)
    if final_sha != main_sha: errors.append("main advanced during governance readback transaction")
    return {
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repository": REPOSITORY, "main_sha": main_sha,
        "main_sha_after_readback": final_sha,
        "github_actions_app_id": GITHUB_ACTIONS_APP_ID,
        "reviewer_accounts": accounts, "repository_settings": repository,
        "branch": branch, "branch_after_readback": final_branch,
        "protection": protection, "rulesets": rulesets,
        "environments": environments, "verification_errors": errors,
    }


def verify_transaction_final_main(expected_sha: str, observed_sha: str) -> list[str]:
    if not SHA_RE.fullmatch(expected_sha) or not SHA_RE.fullmatch(observed_sha):
        return ["governance transaction main SHA is malformed"]
    return [] if expected_sha == observed_sha else ["main advanced during signed-probe verification transaction"]


def apply(api: Callable[[list[str], dict[str, Any] | None], ApiResult]) -> None:
    current = _require("ruleset discovery", api([f"repos/{REPOSITORY}/rulesets?includes_parents=false"], None))
    matching = [item for item in current if isinstance(item, dict) and item.get("name") == RULESET_NAME and item.get("source_type") in (None, "Repository")]
    if len(matching) > 1: raise GovernanceError("multiple named repository rulesets")
    if matching:
        identity = matching[0].get("id")
        if type(identity) is not int: raise GovernanceError("named ruleset has no numeric id")
        _require("ruleset update", api(["-X", "PUT", f"repos/{REPOSITORY}/rulesets/{identity}"], ruleset_payload()))
    else:
        _require("ruleset creation", api(["-X", "POST", f"repos/{REPOSITORY}/rulesets"], ruleset_payload()))
    _require("classic protection", api(["-X", "PUT", f"repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}/protection"], branch_protection_payload()))
    _require("required signatures", api(["-X", "POST", f"repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}/protection/required_signatures"], None))
    _require("merge settings", api(["-X", "PATCH", f"repos/{REPOSITORY}"], repository_merge_payload()))
    for name in ENVIRONMENTS:
        _require(f"environment {name}", api(["-X", "PUT", f"repos/{REPOSITORY}/environments/{name}"], environment_payload()))


def _accounts() -> dict[str, dict[str, Any]]:
    return {login: {"login": login, "id": identity, "type": "User"} for login, identity in REVIEWER_ACCOUNTS.items()}


def _environment(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "deployment_branch_policy": {"protected_branches": True, "custom_branch_policies": False},
        "protection_rules": [{
            "type": "required_reviewers", "prevent_self_review": True,
            "reviewers": [{"type": "User", "reviewer": {"id": identity, "login": login, "type": "User"}} for login, identity in REVIEWER_ACCOUNTS.items()],
        }],
    }


def static_configuration_errors() -> list[str]:
    protection = branch_protection_payload()
    protection.update({
        "enforce_admins": {"enabled": True},
        "required_conversation_resolution": {"enabled": True},
        "allow_force_pushes": {"enabled": False},
        "allow_deletions": {"enabled": False},
        "required_signatures": {"enabled": True},
    })
    accounts = _accounts()
    errors = verify_ruleset(ruleset_payload()) + verify_protection({"name": DEFAULT_BRANCH, "protected": True}, protection) + verify_reviewer_accounts(accounts)
    for name in ENVIRONMENTS: errors += verify_environment(name, _environment(name), accounts)
    if set(PROBE_EXPECTATIONS) != set(REQUIRED_NEGATIVE_PROBES) | set(REQUIRED_POSITIVE_PROBES):
        errors.append("probe inventory is not closed")
    if "evidence_api_url" in PROBE_FIELDS or "evidence_sha256" in PROBE_FIELDS:
        errors.append("probe schema still makes unverified GitHub-object claims")
    return errors


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output", type=Path, default=Path("artifacts/governance/d0t03-live-readback.json"))
    parser.add_argument("--probe-evidence", type=Path)
    parser.add_argument("--probe-signature", type=Path)
    parser.add_argument("--probe-public-key", type=Path)
    parser.add_argument("--expected-probe-public-key-sha256")
    parser.add_argument("--expected-probe-attestor-id", type=int)
    parser.add_argument("--expected-probe-attestor-login")
    parser.add_argument("--check-config", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.check_config:
        errors = static_configuration_errors()
        for error in errors: print(f"ERROR: {error}", file=sys.stderr)
        if errors: return 1
        print("D0T-03 controller configuration is closed and valid"); return 0
    if args.apply: apply(_run_gh)
    evidence = readback(_run_gh)
    packet = None; probe_errors: list[str] = []; key_digest = None
    required = (
        args.probe_evidence, args.probe_signature, args.probe_public_key,
        args.expected_probe_public_key_sha256, args.expected_probe_attestor_id,
        args.expected_probe_attestor_login,
    )
    if any(item is None for item in required):
        probe_errors.append("signed probe inputs or externally bound attestor identity are absent")
    else:
        try:
            key_digest = verify_detached_signature(
                args.probe_evidence, args.probe_signature, args.probe_public_key,
                args.expected_probe_public_key_sha256,
            )
            packet = strict_json(args.probe_evidence.read_text(encoding="utf-8"))
            if not isinstance(packet, dict): raise GovernanceError("probe root must be an object")
            probe_errors += validate_probe_evidence(
                packet, evidence["main_sha"], signature_verified=True,
                public_key_sha256=key_digest,
                expected_attestor_id=args.expected_probe_attestor_id,
                expected_attestor_login=args.expected_probe_attestor_login,
            )
        except (OSError, UnicodeError, GovernanceError) as error:
            probe_errors.append(str(error))
    final_main_sha = None
    try:
        final_main_sha = read_current_main_sha(_run_gh)
        probe_errors += verify_transaction_final_main(evidence["main_sha"], final_main_sha)
    except GovernanceError as error:
        probe_errors.append(str(error))
    evidence.update({
        "probe_schema_version": PROBE_SCHEMA_VERSION,
        "probe_evidence_authority": PROBE_EVIDENCE_AUTHORITY,
        "probe_evidence": packet, "probe_public_key_sha256": key_digest,
        "final_main_sha": final_main_sha, "probe_verification_errors": probe_errors,
        "all_gaps_closed": not evidence["verification_errors"] and not probe_errors,
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    combined = [*evidence["verification_errors"], *probe_errors]
    for error in combined: print(f"ERROR: {error}", file=sys.stderr)
    if combined: return 1
    print(f"D0T-03 live governance and signed probes verified at {evidence['main_sha']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
