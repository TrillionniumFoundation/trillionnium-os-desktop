"""The sole executable closed-record contract for repository status."""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any

REGISTRY_PATH = "docs/status-documents.v1.json"
REGISTRY_SCHEMA = "trillionnium.desktop.status-documents.v1"
STATE_SCHEMA = "trillionnium.desktop.integrated-state.v1"
ROLES = {
    "repository_entry": ("README.md", "repository_entry"),
    "integrated": ("docs/CURRENT_STATE.md", "integrated_main"),
    "candidate": ("docs/CANDIDATE_STATUS.md", "candidate_snapshot_and_live_api"),
    "non_claims": ("docs/NON_CLAIMS.md", "not_claimed"),
    "decomposition": ("docs/plan/PR73_DECOMPOSITION.md", "planning_only"),
}
EXPECTED_WORKSPACE_MEMBERS = (
    "apps/hepta-browserd",
    "apps/hepta-agent-portd",
    "crates/hepta-agent-transport",
    "crates/hepta-browser-codec",
    "crates/hepta-agent-port",
    "crates/hepta-peer-attestation",
    "crates/trillionnium-contract-core",
    "crates/hepta-browser-contracts",
    "crates/hepta-session-core",
    "crates/hepta-workspace-composition",
)
CAPABILITIES = {
    "product_boundary_and_dependency_locks": "product-boundary and dependency locks",
    "bounded_contract_primitives": "bounded shared identifiers, revisions, and browser contracts",
    "authenticated_connected_unix_framing": "authenticated framing over an already-connected Unix stream",
    "canonical_bounded_browser_api": "canonical bounded Browser API parsing",
    "exactly_one_request_agent_port": "an exactly-one request AgentPort bridge",
    "local_linux_peer_identity": "local Linux peer identity mechanisms",
    "durable_non_replaying_receipts": "durable non-replaying receipt foundations",
    "deterministic_workspace_composition": "a deterministic trusted-workspace composition model",
    "default_disabled_agent_port": "default-disabled AgentPort service custody",
    "bounded_servo_compile_qualification": "exact-pin Servo compile-compatibility qualification at a bounded claim level",
}
ACTIONS: dict[str, tuple[dict[str, object], str]] = {
    "enable_repository_protection": (
        {"type": "enable_repository_protection", "issue": 76, "target_branch": "main"},
        "enable and independently verify branch protection and rulesets on `{target_branch}` under issue #{issue}",
    ),
    "decompose_frozen_pull_request": (
        {"type": "decompose_frozen_pull_request", "issue": 78, "target_pull_request": 73},
        "decompose frozen PR #{target_pull_request} into bounded successor pull requests under issue #{issue}",
    ),
    "qualify_successor_pull_requests": (
        {"type": "qualify_successor_pull_requests", "issue": 78, "target_set": "bounded_successor_pull_requests"},
        "qualify every member of `{target_set}` on its own exact final head under issue #{issue}",
    ),
    "complete_runtime_vertical_slice": (
        {"type": "complete_runtime_vertical_slice", "issue": 86, "target_component": "agentport_browseractor_servo_receipts"},
        "complete the `{target_component}` vertical slice under issue #{issue}",
    ),
    "qualify_installed_qemu_image": (
        {"type": "qualify_installed_qemu_image", "issue": 88, "target_environment": "exact_installed_qemu_image"},
        "prove the slice in an `{target_environment}` before hardware or release claims under issue #{issue}",
    ),
}
FORBIDDEN = (
    "all_gaps_closed=true",
    "merge_permitted=true",
    "production_release=true",
    "protected_main=true",
)
_SHA = re.compile(r"[0-9a-f]{40}\Z")
_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")


def closed(value: Any, expected: set[str], label: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return False
    actual = set(value)
    if actual != expected:
        errors.append(
            f"{label} keys are not closed-record compliant; "
            f"missing={sorted(expected - actual)}, unknown={sorted(actual - expected)}"
        )
        return False
    return True


def _real_date(value: Any) -> bool:
    if not isinstance(value, str) or not _DATE.fullmatch(value):
        return False
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def _real_utc(value: Any) -> bool:
    if not isinstance(value, str) or not _UTC.fullmatch(value):
        return False
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def validate_integrated_state(record: Any) -> list[str]:
    errors: list[str] = []
    keys = {
        "schema", "updated", "repository_mode", "workspace_members", "capabilities",
        "governance_observation", "frozen_candidate", "next_work",
    }
    if not closed(record, keys, "integrated_state", errors):
        return errors
    assert isinstance(record, dict)
    if record["schema"] != STATE_SCHEMA:
        errors.append(f"integrated_state schema must be {STATE_SCHEMA!r}")
    if not isinstance(record["updated"], str) or not _DATE.fullmatch(record["updated"]):
        errors.append("integrated_state updated must be YYYY-MM-DD")
    elif not _real_date(record["updated"]):
        errors.append("integrated_state updated must be a real canonical date")
    if record["repository_mode"] != "FULL_PRODUCT_REPOSITORY":
        errors.append("integrated_state repository_mode is invalid")
    if record["workspace_members"] != list(EXPECTED_WORKSPACE_MEMBERS):
        errors.append(
            "workspace_members must equal the exact integrated workspace identity "
            f"{list(EXPECTED_WORKSPACE_MEMBERS)!r}"
        )

    capabilities = record["capabilities"]
    if not isinstance(capabilities, list) or any(not isinstance(item, str) for item in capabilities):
        errors.append("capabilities must be a string list")
    else:
        unknown = sorted(set(capabilities) - set(CAPABILITIES))
        if unknown:
            errors.append(f"unknown capabilities: {unknown}")
        if len(capabilities) != len(set(capabilities)):
            errors.append("capabilities contains duplicates")

    observation = record["governance_observation"]
    observation_keys = {
        "kind", "source", "repository", "branch", "observed_at", "observed_main_sha",
        "branch_protected", "required_status_checks", "validity", "invalidation", "tracking_issue",
    }
    if observation is not None and closed(
        observation, observation_keys, "governance_observation", errors
    ):
        assert isinstance(observation, dict)
        fixed = {
            "kind": "github_repository_settings_snapshot",
            "source": "github_rest_api",
            "repository": "TrillionniumFoundation/trillionnium-os-desktop",
            "branch": "main",
            "validity": "snapshot_only",
            "tracking_issue": 76,
        }
        for key, expected in fixed.items():
            if observation[key] != expected:
                errors.append(f"governance_observation {key} must be {expected!r}")
        if not _real_utc(observation["observed_at"]):
            errors.append("governance_observation observed_at is not a real UTC timestamp")
        observed_sha = observation["observed_main_sha"]
        if not isinstance(observed_sha, str) or not _SHA.fullmatch(observed_sha) or set(observed_sha) == {"0"}:
            errors.append("governance_observation lacks valid observed_main_sha")
        if not isinstance(observation["branch_protected"], bool):
            errors.append("governance_observation branch_protected must be boolean")
        if observation["required_status_checks"] not in {"enabled", "disabled"}:
            errors.append("governance_observation required_status_checks is invalid")
        if observation["invalidation"] != ["main_ref_change", "repository_settings_change"]:
            errors.append(
                "governance_observation invalidation must contain each canonical event "
                "exactly once and in canonical order"
            )

    frozen_expected = {
        "kind": "pull_request",
        "pull_request": 73,
        "state": "draft_frozen",
        "decomposition_issue": 78,
        "merge_policy": "never_merge_as_one_unit",
    }
    frozen = record["frozen_candidate"]
    if closed(frozen, set(frozen_expected), "frozen_candidate", errors) and frozen != frozen_expected:
        errors.append(f"frozen_candidate must equal {frozen_expected!r}")

    next_work = record["next_work"]
    if not isinstance(next_work, list):
        errors.append("next_work must be a list")
    else:
        seen: set[str] = set()
        for index, action in enumerate(next_work):
            label = f"next_work[{index}]"
            if not isinstance(action, dict) or not isinstance(action.get("type"), str):
                errors.append(f"{label} must have a string type")
                continue
            action_type = action["type"]
            if action_type not in ACTIONS:
                errors.append(f"{label} has unsupported action type {action_type!r}")
                continue
            expected = ACTIONS[action_type][0]
            if not closed(action, set(expected), label, errors):
                continue
            if action_type in seen:
                errors.append(f"{label} duplicates {action_type!r}")
            seen.add(action_type)
            if action != expected:
                errors.append(f"{label} must equal the exact registered action {expected!r}")
    return errors
