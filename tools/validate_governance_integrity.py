#!/usr/bin/env python3
"""Validate source-side D0T-03 invariants without claiming live settings.

The validator is dependency-free and fail-closed. It rejects write-capable or
self-modifying GitHub Actions, mutable third-party Action refs, ambiguous check
identities, and drift from the committed governance contract.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_ROOT = ROOT / ".github" / "workflows"
CONTRACT_PATH = ROOT / "contracts" / "repository-governance.v1.json"
FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
USES = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")
TOP_NAME = re.compile(r"^name:\s*['\"]?([^'\"#]+?)['\"]?\s*$")
JOB_KEY = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
JOB_NAME = re.compile(r"^    name:\s*['\"]?([^'\"#]+?)['\"]?\s*$")
WRITE_PERMISSION = re.compile(
    r"^\s*(?:actions|checks|contents|deployments|issues|packages|pages|pull-requests|security-events|statuses)\s*:\s*write\s*$",
    re.MULTILINE,
)
MUTATION_COMMANDS = (
    re.compile(r"(?:^|[;&|]\s*)git\s+(?:push|commit|tag)\b", re.MULTILINE),
    re.compile(r"\bgh\s+pr\s+(?:merge|review)\b"),
    re.compile(r"\bgh\s+release\s+create\b"),
    re.compile(r"api\.github\.com/.+(?:/contents/|/git/refs|/merges|/rulesets|/protection)"),
)


def abort(message: str) -> None:
    raise SystemExit(f"governance-integrity: {message}")


def parse_checks(path: Path, text: str) -> list[tuple[str, str, str]]:
    workflow_name: str | None = None
    in_jobs = False
    current_id: str | None = None
    current_name: str | None = None
    result: list[tuple[str, str, str]] = []

    def flush() -> None:
        nonlocal current_id, current_name
        if current_id is None:
            return
        if workflow_name is None:
            abort(f"{path}: top-level name is required")
        result.append(
            (workflow_name, current_name or current_id, str(path.relative_to(ROOT)))
        )
        current_id = None
        current_name = None

    for line in text.splitlines():
        if workflow_name is None:
            match = TOP_NAME.match(line)
            if match:
                workflow_name = match.group(1).strip()
        if line == "jobs:":
            in_jobs = True
            continue
        if in_jobs and line and not line.startswith(" "):
            flush()
            in_jobs = False
        if not in_jobs:
            continue
        match = JOB_KEY.match(line)
        if match:
            flush()
            current_id = match.group(1)
            continue
        match = JOB_NAME.match(line)
        if match and current_id is not None:
            current_name = match.group(1).strip()
    flush()
    if not result:
        abort(f"{path}: no jobs were parsed")
    return result


def validate_action_refs(path: Path, text: str) -> None:
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = USES.match(line)
        if not match:
            continue
        target = match.group(1).strip("'\"")
        if target.startswith("./"):
            continue
        if "@" not in target:
            abort(f"{path}:{line_number}: action has no ref: {target}")
        ref = target.rsplit("@", 1)[1]
        if not FULL_SHA.fullmatch(ref):
            abort(f"{path}:{line_number}: mutable action ref: {target}")


def validate_authority(path: Path, text: str) -> None:
    if re.search(r"^\s*pull_request_target\s*:", text, re.MULTILINE):
        abort(f"{path}: pull_request_target is forbidden")
    if re.search(r"^\s*permissions\s*:\s*write-all\s*$", text, re.MULTILINE):
        abort(f"{path}: write-all is forbidden")
    if WRITE_PERMISSION.search(text):
        abort(f"{path}: repository write permission is forbidden")
    for pattern in MUTATION_COMMANDS:
        if pattern.search(text):
            abort(f"{path}: branch/repository mutation command is forbidden")


def validate_governance_trigger(path: Path, text: str) -> None:
    if path.name != "governance-integrity.yml":
        return
    if not re.search(r"^\s{2}pull_request\s*:", text, re.MULTILINE):
        abort(f"{path}: governance workflow must run on pull requests")
    if not re.search(r"^\s{2}push\s*:", text, re.MULTILINE):
        abort(f"{path}: governance workflow must run on pushes")
    if re.search(r"^\s{4}paths(?:-ignore)?\s*:", text, re.MULTILINE):
        abort(f"{path}: governance workflow must not use path suppression")
    if "branches: [main]" not in text and "- main" not in text:
        abort(f"{path}: governance workflow must explicitly target main")


def validate_contract(contract: dict[str, object]) -> None:
    if contract.get("schema") != "trillionnium.desktop.repository-governance.v1":
        abort("unexpected governance contract schema")
    if contract.get("work_package") != "D0T-03":
        abort("governance contract must bind D0T-03")
    claim = contract.get("claim_ceiling")
    if not isinstance(claim, dict) or any(value is not False for value in claim.values()):
        abort("source contract must not claim live settings, custody, or release")
    review = contract.get("review")
    if not isinstance(review, dict):
        abort("review policy missing")
    if review.get("minimum_distinct_approver_identities") != 2:
        abort("two distinct approvers are required")
    if review.get("author_self_approval_counts") is not False:
        abort("author self-approval must not count")
    if review.get("organization_team_codeowners_required") is not True:
        abort("organization-team CODEOWNERS must remain required")


def main() -> int:
    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    validate_contract(contract)
    files = sorted((*WORKFLOW_ROOT.glob("*.yml"), *WORKFLOW_ROOT.glob("*.yaml")))
    if not files:
        abort("no workflow files found")

    checks: list[tuple[str, str, str]] = []
    audited: list[str] = []
    for path in files:
        text = path.read_text(encoding="utf-8")
        validate_action_refs(path, text)
        validate_authority(path, text)
        validate_governance_trigger(path, text)
        checks.extend(parse_checks(path, text))
        audited.append(str(path.relative_to(ROOT)))

    by_context: dict[str, list[str]] = {}
    for workflow_name, job_name, source in checks:
        context = f"{workflow_name} / {job_name}"
        by_context.setdefault(context, []).append(source)
    duplicates = {key: value for key, value in by_context.items() if len(value) > 1}
    if duplicates:
        abort(f"ambiguous check contexts: {json.dumps(duplicates, sort_keys=True)}")

    required = contract.get("required_status_contexts")
    if not isinstance(required, list) or not all(isinstance(item, str) for item in required):
        abort("required_status_contexts must be a string list")
    missing = sorted(set(required) - set(by_context))
    if missing:
        abort(f"required contexts not implemented: {missing}")

    result = {
        "schema": "trillionnium.desktop.governance-integrity-result.v1",
        "status": "PASS_SOURCE_POLICY_ONLY",
        "workflow_count": len(audited),
        "check_context_count": len(by_context),
        "required_status_contexts": required,
        "audited_workflows": audited,
        "live_repository_settings_proven": False,
        "independent_human_review_proven": False,
        "signing_key_custody_proven": False,
        "release_readiness_proven": False
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"governance-integrity: {error}", file=sys.stderr)
        raise SystemExit(1) from error
