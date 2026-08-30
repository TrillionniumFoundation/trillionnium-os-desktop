#!/usr/bin/env python3
"""Fail-closed audit for GitHub Actions authority and required-check identity.

The validator intentionally uses only the Python standard library so it can run
before dependency installation. It validates static repository policy; live
branch protection is verified separately through the GitHub API.
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
CONTRACT = ROOT / "contracts" / "repository-governance.v1.json"

FULL_SHA = re.compile(r"^[0-9a-f]{40}$")
TOP_NAME = re.compile(r"^name:\s*['\"]?([^'\"#]+?)['\"]?\s*$")
JOB_KEY = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$")
JOB_NAME = re.compile(r"^    name:\s*['\"]?([^'\"#]+?)['\"]?\s*$")
USES = re.compile(r"^\s*-?\s*uses:\s*([^\s#]+)")

FORBIDDEN_EVENT = re.compile(r"^\s*pull_request_target\s*:", re.MULTILINE)
FORBIDDEN_AUTHORITY = (
    re.compile(r"^\s*(contents|actions|pull-requests|packages|deployments|security-events)\s*:\s*write\s*$", re.MULTILINE),
    re.compile(r"\bgit\s+(push|commit|tag)\b"),
    re.compile(r"\bgh\s+(pr\s+merge|release\s+create|api\s+.*-(?:X|f|F)\s)"),
    re.compile(r"api\.github\.com/.+(?:git/refs|contents|pulls|merges|rulesets|branches/.+/protection)"),
)

CRITICAL_WORKFLOWS = {
    "ci.yml",
    "agent-port-custody.yml",
    "agent-transport-reference.yml",
    "browser-codec-reference.yml",
    "receipt-journal.yml",
    "servo-exact-pin.yml",
    "servo-headed-runtime.yml",
    "d1-final-qualification.yml",
    "governance-integrity.yml",
}


@dataclass(frozen=True)
class WorkflowIdentity:
    path: Path
    workflow_name: str
    job_id: str
    job_name: str

    @property
    def context(self) -> str:
        return f"{self.workflow_name} / {self.job_name}"


def fail(message: str) -> None:
    raise SystemExit(f"workflow-security: {message}")


def workflow_files() -> list[Path]:
    files = sorted((*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")))
    if not files:
        fail("no workflows found")
    return files


def parse_identities(path: Path, text: str) -> list[WorkflowIdentity]:
    workflow_name: str | None = None
    in_jobs = False
    current_job: tuple[str, str] | None = None
    result: list[WorkflowIdentity] = []

    def flush() -> None:
        nonlocal current_job
        if current_job is not None:
            if workflow_name is None:
                fail(f"{path}: missing top-level workflow name")
            job_id, job_name = current_job
            result.append(WorkflowIdentity(path, workflow_name, job_id, job_name))
            current_job = None

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
            job_id = match.group(1)
            current_job = (job_id, job_id)
            continue
        match = JOB_NAME.match(line)
        if match and current_job is not None:
            current_job = (current_job[0], match.group(1).strip())
    flush()
    if not result:
        fail(f"{path}: no jobs found")
    return result


def validate_action_pins(path: Path, text: str) -> None:
    for line_number, line in enumerate(text.splitlines(), start=1):
        match = USES.match(line)
        if not match:
            continue
        target = match.group(1).strip("'\"")
        if target.startswith("./"):
            continue
        if "@" not in target:
            fail(f"{path}:{line_number}: external action has no immutable ref: {target}")
        _, ref = target.rsplit("@", 1)
        if not FULL_SHA.fullmatch(ref):
            fail(f"{path}:{line_number}: mutable action ref is forbidden: {target}")


def validate_checkout_credentials(path: Path, text: str) -> None:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = USES.match(line)
        if not match or not match.group(1).startswith("actions/checkout@"):
            continue
        block = "\n".join(lines[index + 1 : index + 12])
        if "persist-credentials: false" not in block:
            fail(f"{path}:{index + 1}: checkout must set persist-credentials: false")


def validate_events(path: Path, text: str) -> None:
    if FORBIDDEN_EVENT.search(text):
        fail(f"{path}: pull_request_target is forbidden")
    if path.name in CRITICAL_WORKFLOWS:
        if not re.search(r"^\s*pull_request\s*:", text, re.MULTILINE):
            fail(f"{path}: critical workflow must report on pull requests")
        if not re.search(r"^\s*push\s*:", text, re.MULTILINE):
            fail(f"{path}: critical workflow must report on main pushes")
        if re.search(r"^\s*paths(?:-ignore)?\s*:", text, re.MULTILINE):
            fail(f"{path}: critical workflow must not suppress its required context with path filters")


def validate_authority(path: Path, text: str) -> None:
    for pattern in FORBIDDEN_AUTHORITY:
        if pattern.search(text):
            fail(f"{path}: source/repository mutation authority is forbidden")
    if re.search(r"^\s*permissions\s*:\s*write-all\s*$", text, re.MULTILINE):
        fail(f"{path}: write-all is forbidden")


def main() -> int:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    expected = set(contract["required_status_contexts"])
    identities: list[WorkflowIdentity] = []
    audited: list[str] = []
    for path in workflow_files():
        text = path.read_text(encoding="utf-8")
        validate_action_pins(path, text)
        validate_checkout_credentials(path, text)
        validate_events(path, text)
        validate_authority(path, text)
        identities.extend(parse_identities(path, text))
        audited.append(str(path.relative_to(ROOT)))

    by_context: dict[str, list[str]] = {}
    for item in identities:
        by_context.setdefault(item.context, []).append(str(item.path.relative_to(ROOT)))
    duplicates = {key: value for key, value in by_context.items() if len(value) > 1}
    if duplicates:
        fail(f"duplicate check contexts: {json.dumps(duplicates, sort_keys=True)}")

    actual = set(by_context)
    missing = sorted(expected - actual)
    if missing:
        fail(f"contracted required contexts do not exist: {missing}")

    report = {
        "schema": "trillionnium.desktop.workflow-security-audit.v1",
        "status": "PASS",
        "workflow_count": len(audited),
        "job_context_count": len(actual),
        "required_context_count": len(expected),
        "required_contexts": sorted(expected),
        "audited_workflows": audited,
    }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError) as error:
        print(f"workflow-security: {error}", file=sys.stderr)
        raise SystemExit(1) from error
