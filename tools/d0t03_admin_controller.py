#!/usr/bin/env python3
"""Configure and verify the D0T-03 GitHub governance gate.

The controller is dry-run by default. Applying changes requires an explicitly
provided GitHub CLI authentication context with repository Administration
permission and ``--apply``. It never prints credentials and never treats source
existence as live governance closure.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

REPOSITORY = "TrillionniumFoundation/trillionnium-os-desktop"
DEFAULT_BRANCH = "main"
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


def verify_protection(branch: dict[str, Any], protection: dict[str, Any]) -> list[str]:
    """Return every missing D0T-03 protection property."""

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
            if isinstance(entry, dict)
        }
        if not observed:
            observed = set(checks.get("contexts", []))
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
    return errors


def readback(api: Callable[[list[str], dict[str, Any] | None], ApiResult]) -> dict[str, Any]:
    """Read all live identities needed for D0T-03 evidence."""

    branch = _require_success(
        "main branch readback", api([f"repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}"], None)
    )
    protection = _require_success(
        "branch protection readback",
        api([f"repos/{REPOSITORY}/branches/{DEFAULT_BRANCH}/protection"], None),
    )
    rulesets = _require_success(
        "ruleset readback", api([f"repos/{REPOSITORY}/rulesets"], None)
    )
    environments: dict[str, Any] = {}
    for name in ENVIRONMENTS:
        environments[name] = _require_success(
            f"environment {name} readback",
            api([f"repos/{REPOSITORY}/environments/{name}"], None),
        )
    return {
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "repository": REPOSITORY,
        "main_sha": branch.get("commit", {}).get("sha"),
        "branch": branch,
        "protection": protection,
        "rulesets": rulesets,
        "environments": environments,
        "verification_errors": verify_protection(branch, protection),
    }


def apply(api: Callable[[list[str], dict[str, Any] | None], ApiResult]) -> None:
    """Apply the reviewed controls; every write must succeed before readback."""

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
    parser.add_argument("--apply", action="store_true", help="perform live writes")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts/governance/d0t03-live-readback.json"),
    )
    parser.add_argument(
        "--check-config",
        action="store_true",
        help="validate static payloads without invoking GitHub",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.check_config:
        assert branch_protection_payload()["required_pull_request_reviews"][
            "required_approving_review_count"
        ] == 2
        assert environment_payload()["prevent_self_review"] is True
        assert set(REQUIRED_CHECKS)
        print("D0T-03 controller configuration is closed and valid")
        return 0

    if args.apply:
        apply(_run_gh)
    evidence = readback(_run_gh)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    if evidence["verification_errors"]:
        for error in evidence["verification_errors"]:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"D0T-03 live governance verified at {evidence['main_sha']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
