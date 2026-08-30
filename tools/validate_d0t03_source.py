#!/usr/bin/env python3
"""Validate the source-controlled half of D0T-03 without fabricating settings."""
from __future__ import annotations

import json
import re
import sys
import os
import stat
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "manifests/repository-governance.v1.json"
CODEOWNERS = ROOT / ".github/CODEOWNERS"
WORKFLOW = ROOT / ".github/workflows/d0t03-source-contract.yml"
SHA = re.compile(r"^[0-9a-f]{40}$")
OWNER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{0,38}$")
CODEOWNER_TOKEN = re.compile(
    r"^@[A-Za-z0-9][A-Za-z0-9_.-]*(?:/[A-Za-z0-9][A-Za-z0-9_.-]*)?$"
)
EXPECTED_CURRENT_CLAIMS = frozenset(
    {
        "protected_main_configured",
        "organization_teams_configured",
        "independent_review_completed",
        "release_environment_configured",
        "d0t03_closed",
    }
)
EXPECTED_DYNAMIC_ACCEPTANCE_REQUIRED = (
    "direct_push_rejected",
    "force_push_rejected",
    "branch_delete_rejected",
    "author_self_approval_not_counted",
    "failing_required_workflow_blocks_merge",
    "approval_dismissed_after_new_push",
    "unresolved_conversation_blocks_merge",
    "independently_approved_green_pull_request_can_merge",
    "production_environment_requires_independent_approval",
)
EXPECTED_REQUIRED_WORKFLOW_REGISTRY = frozenset(
    {
        ".github/workflows/agent-port-custody.yml",
        ".github/workflows/agent-transport-reference.yml",
        ".github/workflows/browser-codec-reference.yml",
        ".github/workflows/ci.yml",
        ".github/workflows/d0t03-source-contract.yml",
        ".github/workflows/d1-final-qualification.yml",
        ".github/workflows/d2i-integrated-image.yml",
        ".github/workflows/governance-integrity.yml",
        ".github/workflows/receipt-journal.yml",
        ".github/workflows/servo-exact-pin.yml",
        ".github/workflows/servo-headed-runtime.yml",
    }
)
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_STRICT_VALIDATOR = None


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def _strict_workflow_validator():
    """Load the dependency-free canonical workflow parser once."""

    global _STRICT_VALIDATOR
    if _STRICT_VALIDATOR is not None:
        return _STRICT_VALIDATOR
    path = Path(__file__).resolve().with_name("validate_governance_integrity.py")
    spec = importlib.util.spec_from_file_location(
        "d0t03_strict_workflow_validator", path
    )
    if spec is None or spec.loader is None:
        fail("strict governance workflow parser is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
    except Exception as error:
        fail(f"strict governance workflow parser is unreadable: {error}")
    _STRICT_VALIDATOR = module
    return module


def _validate_workflow_strict(text: str) -> None:
    """Apply the canonical YAML/model checks to the D0T-03 workflow itself."""

    strict = _strict_workflow_validator()
    try:
        model = strict.parse_yaml_strict(text, source=str(WORKFLOW))
        strict.validate_workflow(WORKFLOW, model)
    except (strict.YamlParseError, ValueError) as error:
        fail(f"D0T-03 workflow fails strict YAML/model validation: {error}")
    except SystemExit as error:
        fail(f"D0T-03 workflow fails strict YAML/model validation: {error}")
    expected_on = {
        "pull_request": {"branches": ["main"]},
        "push": {"branches": ["main"]},
        "workflow_dispatch": None,
    }
    if not isinstance(model, dict) or model.get("on") != expected_on:
        fail("D0T-03 workflow triggers must be exactly pull_request/push on main and workflow_dispatch")
    if model.get("permissions") != {"contents": "read"}:
        fail("D0T-03 workflow permissions must be exactly contents: read")
    runs = []
    for job in model.get("jobs", {}).values():
        if isinstance(job, dict):
            runs.extend(
                step.get("run", "")
                for step in job.get("steps", [])
                if isinstance(step, dict)
            )
    executable = [value for value in runs if isinstance(value, str)]
    required = (
        "python3 tools/validate_repository.py",
        "python3 tools/validate_project_truth.py",
        "python3 tools/validate_d0t03_source.py",
        "python3 tools/validate_governance_integrity.py",
    )
    missing = [
        command
        for command in required
        if not strict._has_command_invocation(executable, command)
    ]
    if missing:
        fail(f"D0T-03 workflow omits executable governance commands: {missing}")


def _has_symlink_component(path: Path) -> bool:
    """Return whether an existing lexical component of *path* is a symlink."""

    lexical = Path(os.fspath(path))
    if not lexical.is_absolute():
        lexical = Path.cwd() / lexical
    current = Path(lexical.anchor)
    for component in lexical.parts:
        if component == lexical.anchor or component == ".":
            continue
        if component == "..":
            current = current.parent
            continue
        current /= component
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            return False
        except OSError as error:
            raise OSError(f"cannot inspect governance path component: {current}") from error
        if stat.S_ISLNK(mode):
            return True
    return False


def _read_source_text(path: Path) -> str:
    """Read a repository source file without following links or traversal."""

    if any(component == ".." for component in path.parts):
        raise OSError(f"governance path contains '..': {path}")
    try:
        path.relative_to(ROOT)
    except ValueError as error:
        raise OSError(f"governance path escapes repository root: {path}") from error
    if _has_symlink_component(path):
        raise OSError(f"governance path contains a symlink: {path}")
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | _O_CLOEXEC | _O_NOFOLLOW)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError(f"governance path is not a regular file: {path}")
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=True) as stream:
            descriptor = None
            return stream.read()
    finally:
        if descriptor is not None:
            os.close(descriptor)


def workflow_path(value: object) -> Path:
    """Validate and resolve one manifest-declared workflow path.

    Workflow paths are security-sensitive manifest data.  Keep the accepted
    grammar deliberately narrower than ``Path`` so traversal, platform
    alternate separators and symlink redirects cannot make the validator read
    a workflow outside the repository's canonical ``.github/workflows`` tree.
    """

    if not isinstance(value, str) or not value:
        fail("required workflow path must be a non-empty string")
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in value):
        fail(f"required workflow path contains a control character: {value!r}")
    if "\\" in value:
        fail(f"required workflow path contains a backslash: {value!r}")
    path = Path(value)
    if path.is_absolute() or value.startswith("//"):
        fail(f"required workflow path must be relative: {value!r}")
    parts = value.split("/")
    if (
        len(parts) < 3
        or parts[0] != ".github"
        or parts[1] != "workflows"
        or any(part in {"", ".", ".."} for part in parts)
    ):
        fail(
            "required workflow path must be a clean path below "
            f".github/workflows: {value!r}"
        )

    if Path(value).suffix.lower() not in {".yml", ".yaml"}:
        fail(f"required workflow path must end in .yml or .yaml: {value!r}")

    candidate = ROOT.joinpath(*parts)
    current = ROOT
    for part in parts:
        current /= part
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            fail(f"required workflow is absent: {value}")
        except OSError as error:
            fail(f"required workflow cannot be inspected: {value}: {error}")
        if stat.S_ISLNK(mode):
            fail(f"required workflow path contains a symlink: {value}")
    if not candidate.is_file():
        fail(f"required workflow is not a regular file: {value}")
    return candidate


def parse_codeowners(text: str) -> list[tuple[str, tuple[str, ...]]]:
    """Parse active CODEOWNERS rules with exact owner-token semantics.

    GitHub applies the last matching rule, so a later broad rule can silently
    shadow a specific rule.  Keep the parser intentionally strict: every
    active rule must have a pattern and at least two distinct ``@owner``
    tokens.  Inline comments begin at a token starting with ``#``; comments
    and substrings are never treated as owners.
    """

    rules: list[tuple[str, tuple[str, ...]]] = []
    for line_number, line in enumerate(text.splitlines(), 1):
        if any(ord(char) < 0x20 and char not in "\t\r" or ord(char) == 0x7F for char in line):
            fail(f"CODEOWNERS line {line_number} contains a control character")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        tokens: list[str] = []
        for token in stripped.split():
            if token.startswith("#"):
                break
            tokens.append(token)
        if len(tokens) < 3:
            fail(
                f"CODEOWNERS active line {line_number} must contain a pattern and "
                "at least two owners"
            )
        pattern, owners = tokens[0], tuple(tokens[1:])
        if not pattern or pattern.startswith("!") or pattern.startswith("@"):
            fail(f"CODEOWNERS line {line_number} has an invalid pattern")
        if len(set(owners)) != len(owners):
            fail(f"CODEOWNERS line {line_number} repeats an owner token")
        if any(CODEOWNER_TOKEN.fullmatch(owner) is None for owner in owners):
            fail(f"CODEOWNERS line {line_number} has a malformed owner token")
        rules.append((pattern, owners))
    if not rules:
        fail("CODEOWNERS has no active rules")
    return rules


def main() -> int:
    try:
        data = json.loads(_read_source_text(MANIFEST))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"governance manifest is unreadable: {error}")
    if not isinstance(data, dict):
        fail("governance manifest must be an object")
    if data.get("schema") != "trillionnium.desktop.repository-governance.v1":
        fail("unexpected governance schema")
    if data.get("work_package") != "D0T-03":
        fail("governance manifest is not bound to D0T-03")
    if data.get("status") != "SOURCE_BOOTSTRAP_READY_REPOSITORY_SETTINGS_REQUIRED":
        fail("source contract must remain fail-closed on repository settings")

    review = data.get("source_review", {})
    if not isinstance(review, dict):
        fail("source_review must be an object")
    owners = review.get("interim_codeowners", [])
    if (
        not isinstance(owners, list)
        or len(owners) < 2
        or any(not isinstance(owner, str) or OWNER.fullmatch(owner) is None for owner in owners)
        or len(set(owners)) != len(owners)
    ):
        fail("at least two distinct interim CODEOWNER identities are required")
    if review.get("minimum_distinct_approver_identities") != 2:
        fail("minimum approval count must be exactly two")
    if review.get("organization_team_codeowners_required_for_closure") is not True:
        fail("team CODEOWNERS must remain mandatory for final closure")
    for key in (
        "stale_approvals_dismissed_required",
        "approval_after_latest_push_required",
        "code_owner_review_required",
        "all_conversations_resolved_required",
    ):
        if review.get(key) is not True:
            fail(f"review control is not fail-closed: {key}")
    if review.get("author_self_approval_counts") is not False:
        fail("author self-approval must not count")
    if review.get("author_self_merge_allowed") is not False:
        fail("author self-merge must remain forbidden")

    try:
        text = _read_source_text(CODEOWNERS)
    except OSError as error:
        fail(f"CODEOWNERS is unreadable: {error}")
    rules = parse_codeowners(text)
    required_tokens = {f"@{owner}" for owner in owners}
    all_tokens = {owner for _, rule_owners in rules for owner in rule_owners}
    missing_tokens = sorted(required_tokens - all_tokens)
    if missing_tokens:
        fail(f"CODEOWNERS is missing exact owner tokens: {missing_tokens}")
    # CODEOWNERS uses last-match-wins semantics.  Requiring the complete
    # interim pair on every active rule ensures no later broad rule can shadow
    # one of the required reviewers for a protected path.
    for pattern, rule_owners in rules:
        missing = sorted(required_tokens - set(rule_owners))
        if missing:
            fail(
                f"CODEOWNERS rule {pattern!r} can shadow required owners: {missing}"
            )

    branch = data.get("main_branch", {})
    if not isinstance(branch, dict):
        fail("main_branch must be an object")
    if branch.get("name") != "main":
        fail("main branch name must remain exactly main")
    for key in (
        "pull_request_required",
        "strict_required_checks",
    ):
        if branch.get(key) is not True:
            fail(f"main branch requirement is disabled: {key}")
    for key in (
        "force_push_allowed",
        "deletion_allowed",
        "administrator_bypass_allowed",
    ):
        if branch.get(key) is not False:
            fail(f"main branch escape hatch is enabled: {key}")
    required_workflows = branch.get("required_workflows", [])
    if (
        not isinstance(required_workflows, list)
        or not required_workflows
        or any(not isinstance(relative, str) for relative in required_workflows)
        or len(required_workflows) != len(set(required_workflows))
    ):
        fail("required workflow registry is empty or duplicated")
    if ".github/workflows/d0t03-source-contract.yml" not in required_workflows:
        fail("required workflow registry must include d0t03-source-contract.yml")
    if set(required_workflows) != EXPECTED_REQUIRED_WORKFLOW_REGISTRY:
        fail("required workflow registry must match the committed workflow inventory")
    for relative in required_workflows:
        workflow_path(relative)

    release = data.get("release", {})
    if not isinstance(release, dict):
        fail("release must be an object")
    if release.get("protected_environment") != "production":
        fail("production protected environment name changed")
    if release.get("minimum_independent_approvers") != 2:
        fail("release approval count must be two")
    if release.get("source_author_may_approve_release") is not False:
        fail("source author may not approve the release")
    if release.get("signing_key_available_to_pull_request_workflows") is not False:
        fail("pull-request workflows must not receive signing keys")
    if release.get("signing_and_source_authority_separated") is not True:
        fail("signing and source authority are not separated")

    dynamic_acceptance = data.get("dynamic_acceptance_required")
    if (
        not isinstance(dynamic_acceptance, list)
        or dynamic_acceptance != list(EXPECTED_DYNAMIC_ACCEPTANCE_REQUIRED)
    ):
        fail("dynamic_acceptance_required must match the bounded acceptance corpus")

    claims = data.get("current_claims", {})
    if (
        not isinstance(claims, dict)
        or set(claims) != EXPECTED_CURRENT_CLAIMS
        or any(type(value) is not bool or value for value in claims.values())
    ):
        fail(
            "source must provide the exact current_claims field set with every "
            "claim explicitly false"
        )
    if data.get("claim_ceiling") != "source_contract_and_interim_two_identity_codeowners_only":
        fail("governance claim ceiling changed")

    try:
        workflow = _read_source_text(WORKFLOW)
    except OSError as error:
        fail(f"D0T-03 workflow is unreadable: {error}")
    if "contents: read" not in workflow or "contents: write" in workflow:
        fail("D0T-03 source workflow is not read-only")
    if "persist-credentials: false" not in workflow:
        fail("D0T-03 checkout must discard credentials")
    for line in workflow.splitlines():
        stripped = line.strip()
        if not stripped.startswith("uses:"):
            continue
        action = stripped.split(":", 1)[1].strip()
        if action.startswith("./"):
            continue
        if "@" not in action or not SHA.fullmatch(action.rsplit("@", 1)[1]):
            fail(f"workflow action is not pinned by SHA: {action}")

    _validate_workflow_strict(workflow)

    print("D0T-03 source governance contract passed; repository settings remain external")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
