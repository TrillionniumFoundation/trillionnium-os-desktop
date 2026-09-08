#!/usr/bin/env python3
"""Validate the closed status-facts schema and its exact Markdown projection."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PROJECT_PATH = ROOT / "manifests/project-state.v1.json"
FACTS_PATH = ROOT / "docs/status-facts.v1.json"
PROJECTION_PATH = ROOT / "docs/CURRENT_STATE.md"
SCHEMA = "trillionnium.desktop.status-facts.v1"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
UTC_SECOND = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class DuplicateKey(ValueError):
    pass


def no_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise DuplicateKey(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_object(path: Path) -> dict[str, Any]:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"required regular file missing: {path.relative_to(ROOT)}")
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=no_duplicate_keys)
    except (OSError, UnicodeError, json.JSONDecodeError, DuplicateKey) as error:
        raise ValueError(f"invalid JSON {path.relative_to(ROOT)}: {error}") from error
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path.relative_to(ROOT)}")
    return value


def exact_keys(value: dict[str, Any], expected: set[str], label: str, errors: list[str]) -> None:
    actual = set(value)
    if actual != expected:
        errors.append(f"{label} keys must be exactly {sorted(expected)!r}; got {sorted(actual)!r}")


def nonempty_line(value: Any) -> bool:
    return isinstance(value, str) and bool(value) and "\n" not in value and "\r" not in value


def validate(project: dict[str, Any], facts: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    exact_keys(
        facts,
        {
            "schema",
            "document_updated",
            "projection_subject",
            "workspace_members",
            "governance_observations",
            "unmerged_candidates",
            "pending_actions",
        },
        "status facts",
        errors,
    )
    if facts.get("schema") != SCHEMA:
        errors.append(f"schema must equal {SCHEMA!r}")
    if not DATE.fullmatch(str(facts.get("document_updated", ""))):
        errors.append("document_updated must be YYYY-MM-DD")

    subject = facts.get("projection_subject")
    own_pr: int | None = None
    own_branch: str | None = None
    if not isinstance(subject, dict):
        errors.append("projection_subject must be an object")
    else:
        exact_keys(subject, {"role", "source_candidate"}, "projection_subject", errors)
        if subject.get("role") != "integrated_main":
            errors.append("projection_subject.role must be integrated_main")
        source = subject.get("source_candidate")
        if not isinstance(source, dict):
            errors.append("source_candidate must be an object")
        else:
            exact_keys(source, {"pull_request", "branch"}, "source_candidate", errors)
            own_pr = source.get("pull_request")
            own_branch = source.get("branch")
            if not isinstance(own_pr, int) or own_pr <= 0:
                errors.append("source_candidate.pull_request must be positive")
            if not nonempty_line(own_branch):
                errors.append("source_candidate.branch must be one non-empty line")

    workspace = facts.get("workspace_members")
    if not isinstance(workspace, list) or not workspace or any(not nonempty_line(x) for x in workspace) or len(workspace) != len(set(workspace)):
        errors.append("workspace_members must be a non-empty unique one-line string list")

    observations = facts.get("governance_observations")
    if not isinstance(observations, list):
        errors.append("governance_observations must be a list")
        observations = []
    observation_ids: set[str] = set()
    for index, item in enumerate(observations):
        label = f"governance_observations[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        exact_keys(
            item,
            {
                "id", "kind", "source", "observed_at", "observed_main_sha",
                "validity", "main_protected", "required_status_enforcement", "tracking_issue",
            },
            label,
            errors,
        )
        identifier = item.get("id")
        if not nonempty_line(identifier) or identifier in observation_ids:
            errors.append(f"{label}.id must be unique and non-empty")
        else:
            observation_ids.add(identifier)
        if item.get("kind") != "github_repository_protection":
            errors.append(f"{label}.kind is invalid")
        if item.get("source") != "github_rest_api":
            errors.append(f"{label}.source is invalid")
        if not UTC_SECOND.fullmatch(str(item.get("observed_at", ""))):
            errors.append(f"{label}.observed_at must be an exact UTC second")
        observed_sha = item.get("observed_main_sha")
        if not isinstance(observed_sha, str) or not SHA40.fullmatch(observed_sha) or set(observed_sha) == {"0"}:
            errors.append(f"{label}.observed_main_sha must be a non-zero SHA-40")
        if item.get("validity") != "snapshot_only":
            errors.append(f"{label}.validity must be snapshot_only")
        if not isinstance(item.get("main_protected"), bool):
            errors.append(f"{label}.main_protected must be boolean")
        if item.get("required_status_enforcement") not in {"off", "non_strict", "strict"}:
            errors.append(f"{label}.required_status_enforcement is invalid")
        if not isinstance(item.get("tracking_issue"), int) or item["tracking_issue"] <= 0:
            errors.append(f"{label}.tracking_issue must be positive")

    candidates = facts.get("unmerged_candidates")
    if not isinstance(candidates, list):
        errors.append("unmerged_candidates must be a list")
        candidates = []
    seen_candidates: set[tuple[int, str]] = set()
    for index, item in enumerate(candidates):
        label = f"unmerged_candidates[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        exact_keys(item, {"kind", "number", "branch", "state", "merge_policy"}, label, errors)
        key = (item.get("number"), item.get("branch"))
        if item.get("kind") != "pull_request":
            errors.append(f"{label}.kind must be pull_request")
        if not isinstance(key[0], int) or key[0] <= 0 or not nonempty_line(key[1]):
            errors.append(f"{label} requires a positive number and non-empty branch")
        elif key in seen_candidates:
            errors.append(f"{label} duplicates a candidate")
        else:
            seen_candidates.add(key)
        if item.get("state") != "frozen_draft":
            errors.append(f"{label}.state must be frozen_draft")
        if item.get("merge_policy") != "must_decompose_never_merge_as_unit":
            errors.append(f"{label}.merge_policy must fail closed")

    actions = facts.get("pending_actions")
    if not isinstance(actions, list):
        errors.append("pending_actions must be a list")
        actions = []
    seen_actions: set[str] = set()
    for index, item in enumerate(actions):
        label = f"pending_actions[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        exact_keys(item, {"id", "kind", "target", "summary"}, label, errors)
        identifier = item.get("id")
        if not nonempty_line(identifier) or identifier in seen_actions:
            errors.append(f"{label}.id must be unique and non-empty")
        else:
            seen_actions.add(identifier)
        if item.get("kind") not in {"external_control", "successor_train", "runtime_integration", "installed_image"}:
            errors.append(f"{label}.kind is invalid")
        if not nonempty_line(item.get("summary")):
            errors.append(f"{label}.summary must be one non-empty line")
        target = item.get("target")
        if not isinstance(target, dict):
            errors.append(f"{label}.target must be an object")
            continue
        target_kind = target.get("kind")
        if target_kind == "issue":
            exact_keys(target, {"kind", "number"}, f"{label}.target", errors)
            if not isinstance(target.get("number"), int) or target["number"] <= 0:
                errors.append(f"{label}.target.number must be positive")
        elif target_kind == "pull_request":
            exact_keys(target, {"kind", "number", "branch"}, f"{label}.target", errors)
            if target.get("number") == own_pr or target.get("branch") == own_branch:
                errors.append(f"{label} targets this projection's own pending integration")
            if not isinstance(target.get("number"), int) or target["number"] <= 0 or not nonempty_line(target.get("branch")):
                errors.append(f"{label}.target pull request identity is invalid")
        else:
            errors.append(f"{label}.target.kind must be issue or pull_request")

    for field in ("active_plan_revision", "integrated_implementation_stage"):
        if not nonempty_line(project.get(field)):
            errors.append(f"project-state {field} must be one non-empty line")
    completed = project.get("integrated_completed_work_packages")
    if not isinstance(completed, list) or any(not nonempty_line(x) for x in completed) or len(completed) != len(set(completed)):
        errors.append("project-state integrated_completed_work_packages must be unique strings")
    return errors


def render(project: dict[str, Any], facts: dict[str, Any]) -> str:
    lines = [
        "# TrillionniumOS Desktop — integrated state",
        "",
        "<!-- GENERATED: edit manifests/project-state.v1.json and docs/status-facts.v1.json, then run tools/validate_status_facts.py --write. -->",
        "",
        f"**Updated:** `{facts['document_updated']}`  ",
        f"**Canonical plan:** `{project['active_plan_revision']}`  ",
        f"**Integrated implementation stage:** `{project['integrated_implementation_stage']}`  ",
        "**Status scope:** integrated `main` facts only",
        "",
        "This complete document is generated from closed structured inputs and compared byte-for-byte. Free-form operational claims and paraphrased merge instructions are not accepted here.",
        "",
        "## Integrated work packages",
        "",
    ]
    lines.extend(f"- `{item}`" for item in project.get("integrated_completed_work_packages", []))
    lines += ["", "## Integrated workspace", "", "```text"]
    lines.extend(facts["workspace_members"])
    lines += ["```", "", "## Governance observations", ""]
    if not facts["governance_observations"]:
        lines.append("No governance observation is recorded.")
    else:
        lines += [
            "| ID | Source | Observed at | Observed main | Protected | Required checks | Validity | Tracking |",
            "|---|---|---|---|---:|---|---|---:|",
        ]
        for item in facts["governance_observations"]:
            lines.append(
                f"| `{item['id']}` | `{item['source']}` | `{item['observed_at']}` | `{item['observed_main_sha']}` | "
                f"`{str(item['main_protected']).lower()}` | `{item['required_status_enforcement']}` | `{item['validity']}` | #{item['tracking_issue']} |"
            )
    lines += [
        "",
        "These are identity-bound snapshots, never live authorization. Any ref or settings movement invalidates the corresponding observation.",
        "",
        "## Unmerged candidates",
        "",
        "| Type | Number | Branch | State | Merge policy |",
        "|---|---:|---|---|---|",
    ]
    for item in facts["unmerged_candidates"]:
        lines.append(f"| `{item['kind']}` | #{item['number']} | `{item['branch']}` | `{item['state']}` | `{item['merge_policy']}` |")
    lines += [
        "",
        "Candidate evidence does not transfer to another head, successor, installed image, hardware run, signing ceremony, or release.",
        "",
        "## Next bounded work",
        "",
        "| ID | Class | Target | Action |",
        "|---|---|---|---|",
    ]
    for item in facts["pending_actions"]:
        target = item["target"]
        rendered_target = f"issue #{target['number']}" if target["kind"] == "issue" else f"PR #{target['number']} (`{target['branch']}`)"
        lines.append(f"| `{item['id']}` | `{item['kind']}` | {rendered_target} | {item['summary']} |")
    lines += [
        "",
        "## Interpretation",
        "",
        "The narrower claim always wins. Historical evidence is diagnostic only after an invalidating change.",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", action="store_true", help="rewrite the exact Markdown projection")
    args = parser.parse_args()
    try:
        project = load_object(PROJECT_PATH)
        facts = load_object(FACTS_PATH)
    except ValueError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 1
    errors = validate(project, facts)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    expected = render(project, facts)
    if args.write:
        PROJECTION_PATH.write_text(expected, encoding="utf-8")
    try:
        actual = PROJECTION_PATH.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as error:
        print(f"ERROR: cannot read {PROJECTION_PATH.relative_to(ROOT)}: {error}", file=sys.stderr)
        return 1
    if actual != expected:
        print("ERROR: docs/CURRENT_STATE.md is not the exact closed-schema projection; run with --write", file=sys.stderr)
        return 1
    print("status-facts validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
