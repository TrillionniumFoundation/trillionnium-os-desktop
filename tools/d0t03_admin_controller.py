#!/usr/bin/env python3
"""Configure and verify the D0T-03 GitHub governance gate.

The controller is dry-run/static-validation oriented by default. Applying
changes requires an explicitly authenticated GitHub CLI context with repository
Administration permission and ``--apply``. Source presence, a successful write,
or configuration readback alone never counts as D0T-03 closure: the controller
also validates an independently produced positive/negative probe packet bound
to the exact current ``main`` SHA.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable

REPOSITORY = "TrillionniumFoundation/trillionnium-os-desktop"
DEFAULT_BRANCH = "main"
RULESET_NAME = "TrillionniumOS protected default branch"
REVIEWERS = (273670192, 273673612)
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
                        {"context": context} for context in REQUIRED_CHECKS
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
                {"context": context, "app_id": -1} for context in REQUIRED_CHECKS
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
        "reviewers": [{"type": "User", "id": reviewer} for reviewer in REVIEWERS],
        "deployment_branch_policy": {
            "protected_branches": True,
            "custom_branch_policies": False,
        },
    }


def repository_merge_payload() -> dict[str, Any]:
    """Return repository merge settings required by the bounded merge train."""

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
            continue
        rule_type = entry["type"]
        if rule_type in result:
            raise GovernanceError(f"duplicate ruleset rule {rule_type!r}")
        result[rule_type] = entry
    return result


def verify_ruleset(ruleset: dict[str, Any]) -> list[str]:
    """Return every weakening observed in a full ruleset readback."""

    errors: list[str] = []
    if ruleset.get("name") != RULESET_NAME:
        errors.append("named repository ruleset is absent")
    if ruleset.get("target") != "branch":
        errors.append("ruleset does not target branches")
    if ruleset.get("enforcement") != "active":
        errors.append("ruleset is not active")
    if ruleset.get("bypass_actors") not in ([], None):
        errors.append("ruleset contains bypass actors")

    conditions = ruleset.get("conditions")
    includes: set[str] = set()
    excludes: set[str] = set()
    if isinstance(conditions, dict):
        ref_name = conditions.get("ref_name")
        if isinstance(ref_name, dict):
            includes = {item for item in ref_name.get("include", []) if isinstance(item, str)}
            excludes = {item for item in ref_name.get("exclude", []) if isinstance(item, str)}
    if "~DEFAULT_BRANCH" not in includes and f"refs/heads/{DEFAULT_BRANCH}" not in includes:
        errors.append("ruleset does not include the default branch")
    if "~DEFAULT_BRANCH" in excludes or f"refs/heads/{DEFAULT_BRANCH}" in excludes:
        errors.append("ruleset excludes the default branch")

    try:
        rules = _rule_map(ruleset.get("rules", []))
    except GovernanceError as error:
        errors.append(str(error))
        rules = {}
    for required in ("deletion", "non_fast_forward", "required_signatures"):
        if required not in rules:
            errors.append(f"ruleset rule {required} is absent")

    pull_request = rules.get("pull_request", {}).get("parameters", {})
    expected_pull_request = {
        "dismiss_stale_reviews_on_push": True,
        "require_code_owner_review": True,
        "require_last_push_approval": True,
        "required_review_thread_resolution": True,
    }
    if not isinstance(pull_request, dict):
        errors.append("pull-request ruleset parameters are absent")
    else:
        for key, expected in expected_pull_request.items():
            if pull_request.get(key) is not expected:
                errors.append(f"ruleset pull-request control {key} is not {expected}")
        if pull_request.get("required_approving_review_count", 0) < 2:
            errors.append("ruleset requires fewer than two approvals")
        if set(pull_request.get("allowed_merge_methods", [])) != {"merge"}:
            errors.append("ruleset does not restrict the stacked train to merge commits")

    statuses = rules.get("required_status_checks", {}).get("parameters", {})
    if not isinstance(statuses, dict):
        errors.append("required-status ruleset parameters are absent")
    else:
        if statuses.get("strict_required_status_checks_policy") is not True:
            errors.append("ruleset status checks are not strict with the live base")
        if statuses.get("do_not_enforce_on_create") is not False:
            errors.append("ruleset status checks are not enforced on creation")
        observed = {
            item.get("context")
            for item in statuses.get("required_status_checks", [])
            if isinstance(item, dict) and isinstance(item.get("context"), str)
        }
        missing = sorted(set(REQUIRED_CHECKS) - observed)
        if missing:
            errors.append(f"ruleset required checks missing: {missing}")
    return errors


def verify_protection(branch: dict[str, Any], protection: dict[str, Any]) -> list[str]:
    """Return every missing D0T-03 classic-protection property."""

    errors: list[str] = []
    if branch.get("name") != DEFAULT_BRANCH or branch.get("protected") is not True:
        errors.append("main is not reported protected")

    checks = protection.get("required_status_checks")
    if not isinstance(checks, dict) or checks.get("strict") is not True:
        errors.append("strict required status checks are absent")
    else:
        observed = {
            entry.get("context")
            for entry in checks.get("checks", [])
            if isinstance(entry, dict) and isinstance(entry.get("context"), str)
        }
        if not observed:
            observed = {
                context for context in checks.get("contexts", []) if isinstance(context, str)
            }
        missing = sorted(set(REQUIRED_CHECKS) - observed)
        if missing:
            errors.append(f"required checks missing: {missing}")

    reviews = protection.get("required_pull_request_reviews")
    if not isinstance(reviews, dict):
        errors.append("required pull-request reviews are absent")
    else:
        expected = {
            "dismiss_stale_reviews": True,
            "require_code_owner_reviews": True,
            "require_last_push_approval": True,
        }
        for key, value in expected.items():
            if reviews.get(key) is not value:
                errors.append(f"review control {key} is not {value}")
        if reviews.get("required_approving_review_count", 0) < 2:
            errors.append("fewer than two approvals are required")

    for key in ("enforce_admins", "required_conversation_resolution"):
        value = protection.get(key)
        if not isinstance(value, dict) or value.get("enabled") is not True:
            errors.append(f"{key} is not enabled")
    for key in ("allow_force_pushes", "allow_deletions"):
        value = protection.get(key)
        if isinstance(value, dict) and value.get("enabled") is True:
            errors.append(f"{key} remains enabled")
    signatures = protection.get("required_signatures")
    if isinstance(signatures, dict) and signatures.get("enabled") is not True:
        errors.append("required commit signatures are not enabled")
    return errors


def verify_environment(name: str, environment: dict[str, Any]) -> list[str]:
    """Return every weakening in one protected-environment readback."""

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

    reviewer_rule: dict[str, Any] | None = None
    for rule in environment.get("protection_rules", []):
        if isinstance(rule, dict) and rule.get("type") == "required_reviewers":
            if reviewer_rule is not None:
                errors.append(f"environment {name} has duplicate reviewer rules")
                break
            reviewer_rule = rule
    if reviewer_rule is None:
        errors.append(f"environment {name} required-reviewer rule is absent")
    else:
        if reviewer_rule.get("prevent_self_review") is not True:
            errors.append(f"environment {name} permits self review")
        observed: set[int] = set()
        for entry in reviewer_rule.get("reviewers", []):
            if not isinstance(entry, dict):
                continue
            reviewer = entry.get("reviewer")
            candidate = reviewer.get("id") if isinstance(reviewer, dict) else entry.get("id")
            if isinstance(candidate, int):
                observed.add(candidate)
        missing = sorted(set(REVIEWERS) - observed)
        if missing:
            errors.append(f"environment {name} reviewers missing: {missing}")
    return errors


def verify_repository_settings(repository: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    expected = repository_merge_payload()
    for key, value in expected.items():
        if repository.get(key) is not value:
            errors.append(f"repository setting {key} is not {value}")
    return errors


def validate_probe_evidence(packet: dict[str, Any], main_sha: str) -> list[str]:
    """Validate an independently captured D0T-03 probe packet.

    The controller deliberately does not perform destructive attempts against
    the production default branch. The packet must come from restricted test
    identities and GitHub's policy-evaluation/merge/deployment paths.
    """

    errors: list[str] = []
    if packet.get("schema_version") != 1:
        errors.append("probe schema_version is not 1")
    if packet.get("repository") != REPOSITORY:
        errors.append("probe repository identity mismatch")
    if packet.get("main_sha") != main_sha:
        errors.append("probe packet is not bound to the current main SHA")
    if not isinstance(packet.get("observed_at"), str) or not packet["observed_at"]:
        errors.append("probe observed_at is absent")

    expected_results = {
        **{probe: "rejected" for probe in REQUIRED_NEGATIVE_PROBES},
        **{probe: "succeeded" for probe in REQUIRED_POSITIVE_PROBES},
    }
    observed: dict[str, dict[str, Any]] = {}
    for probe in packet.get("probes", []):
        if not isinstance(probe, dict) or not isinstance(probe.get("id"), str):
            errors.append("probe entry is not a keyed object")
            continue
        probe_id = probe["id"]
        if probe_id in observed:
            errors.append(f"duplicate probe {probe_id}")
            continue
        observed[probe_id] = probe
    for probe_id, result in expected_results.items():
        probe = observed.get(probe_id)
        if probe is None:
            errors.append(f"required probe {probe_id} is absent")
            continue
        if probe.get("result") != result:
            errors.append(f"probe {probe_id} result is not {result}")
        if not isinstance(probe.get("actor_id"), int) or probe["actor_id"] <= 0:
            errors.append(f"probe {probe_id} actor_id is invalid")
        if not isinstance(probe.get("actor_login"), str) or not probe["actor_login"]:
            errors.append(f"probe {probe_id} actor_login is absent")
        if not isinstance(probe.get("observed_at"), str) or not probe["observed_at"]:
            errors.append(f"probe {probe_id} observed_at is absent")
        if not isinstance(probe.get("evidence_url"), str) or not probe["evidence_url"].startswith(
            "https://github.com/"
        ):
            errors.append(f"probe {probe_id} evidence_url is invalid")

    roles = packet.get("role_identities")
    if not isinstance(roles, dict):
        errors.append("role_identities is absent")
    else:
        seen: dict[int, str] = {}
        for role in SEPARATED_ROLES:
            values = roles.get(role)
            if not isinstance(values, list) or not values:
                errors.append(f"role {role} has no bound identity")
                continue
            role_ids: set[int] = set()
            for value in values:
                if not isinstance(value, int) or value <= 0:
                    errors.append(f"role {role} contains an invalid identity")
                    continue
                if value in role_ids:
                    errors.append(f"role {role} contains duplicate identity {value}")
                    continue
                role_ids.add(value)
                other = seen.get(value)
                if other is not None and other != role:
                    errors.append(f"identity {value} is shared by roles {other} and {role}")
                else:
                    seen[value] = role
    return errors


def readback(api: Callable[[list[str], dict[str, Any] | None], ApiResult]) -> dict[str, Any]:
    """Read every live identity needed for D0T-03 evidence."""

    repository = _require_success(
        "repository readback", api([f"repos/{REPOSITORY}"], None)
    )
    branch = _require_success(
        "main branch readback", api([f"repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}"], None)
    )
    protection = _require_success(
        "branch protection readback",
        api([f"repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}/protection"], None),
    )
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
        if isinstance(ruleset_id, int):
            full_rulesets.append(
                _require_success(
                    f"ruleset {ruleset_id} readback",
                    api([f"repos/{REPOSITORY}/rulesets/{ruleset_id}"], None),
                )
            )
    environments: dict[str, Any] = {}
    for name in ENVIRONMENTS:
        environments[name] = _require_success(
            f"environment {name} readback",
            api([f"repos/{REPOSITORY}/environments/{name}"], None),
        )

    errors = verify_repository_settings(repository)
    errors.extend(verify_protection(branch, protection))
    if len(full_rulesets) != 1:
        errors.append(f"expected one active named repository ruleset, observed {len(full_rulesets)}")
    elif full_rulesets:
        errors.extend(verify_ruleset(full_rulesets[0]))
    for name, environment in environments.items():
        errors.extend(verify_environment(name, environment))
    return {
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repository": REPOSITORY,
        "main_sha": branch.get("commit", {}).get("sha"),
        "repository_settings": repository,
        "branch": branch,
        "protection": protection,
        "rulesets": full_rulesets,
        "environments": environments,
        "verification_errors": errors,
    }


def apply(api: Callable[[list[str], dict[str, Any] | None], ApiResult]) -> None:
    """Apply reviewed controls; every write must succeed before readback."""

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
        if not isinstance(ruleset_id, int):
            raise GovernanceError("named repository ruleset has no numeric id")
        _require_success(
            "repository ruleset update",
            api(["-X", "PUT", f"repos/{REPOSITORY}/rulesets/{ruleset_id}"], ruleset_payload()),
        )
    else:
        _require_success(
            "repository ruleset creation",
            api(["-X", "POST", f"repos/{REPOSITORY}/rulesets"], ruleset_payload()),
        )

    _require_success(
        "classic branch protection",
        api(
            ["-X", "PUT", f"repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}/protection"],
            branch_protection_payload(),
        ),
    )
    _require_success(
        "required commit signatures",
        api(
            [
                "-X",
                "POST",
                f"repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}/protection/required_signatures",
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
    parser.add_argument("--apply", action="store_true", help="perform live administration writes")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/governance/d0t03-live-readback.json"),
    )
    parser.add_argument(
        "--probe-evidence",
        type=Path,
        help="strict JSON packet containing independent positive/negative probes",
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="validate static payloads without invoking GitHub",
    )
    return parser.parse_args()


def static_configuration_errors() -> list[str]:
    errors: list[str] = []
    errors.extend(verify_ruleset(ruleset_payload()))
    protection = branch_protection_payload()
    synthetic_readback = {
        **protection,
        "enforce_admins": {"enabled": protection["enforce_admins"]},
        "required_conversation_resolution": {
            "enabled": protection["required_conversation_resolution"]
        },
        "allow_force_pushes": {"enabled": protection["allow_force_pushes"]},
        "allow_deletions": {"enabled": protection["allow_deletions"]},
        "required_signatures": {"enabled": True},
    }
    errors.extend(
        verify_protection(
            {"name": DEFAULT_BRANCH, "protected": True}, synthetic_readback
        )
    )
    if environment_payload()["prevent_self_review"] is not True:
        errors.append("environment self-review prevention is absent")
    if set(REQUIRED_CHECKS) != {
        "repository-contracts",
        "rust",
        "repository-contracts-prospective-merge",
        "rust-prospective-merge",
    }:
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
    probe_errors: list[str]
    if args.probe_evidence is None:
        probe_errors = ["independent positive/negative probe packet is absent"]
        probe_packet: dict[str, Any] | None = None
    else:
        loaded = strict_json(args.probe_evidence.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            raise GovernanceError("probe evidence root must be an object")
        probe_packet = loaded
        probe_errors = validate_probe_evidence(loaded, str(evidence.get("main_sha")))
    evidence["probe_evidence"] = probe_packet
    evidence["probe_verification_errors"] = probe_errors
    evidence["all_gaps_closed"] = not evidence["verification_errors"] and not probe_errors

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
    print(f"D0T-03 live governance and independent probes verified at {evidence['main_sha']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
