"""Closed structured status model and deterministic integrated-state projection."""

from __future__ import annotations

import json
import re
import tomllib
from pathlib import Path
from typing import Any

REGISTRY_PATH = "docs/status-documents.v1.json"
CONTRACT_PATH = "contracts/status-documents.v1.schema.json"
REGISTRY_SCHEMA = "trillionnium.desktop.status-documents.v1"
STATE_SCHEMA = "trillionnium.desktop.integrated-state.v1"
STATUS_REGISTRY_PATH = REGISTRY_PATH
STATUS_REGISTRY_CONTRACT = CONTRACT_PATH
STATUS_REGISTRY_SCHEMA = REGISTRY_SCHEMA
INTEGRATED_STATE_SCHEMA = STATE_SCHEMA
ROLES = {
    "repository_entry": ("README.md", "repository_entry"),
    "integrated": ("docs/CURRENT_STATE.md", "integrated_main"),
    "candidate": ("docs/CANDIDATE_STATUS.md", "candidate_snapshot_and_live_api"),
    "non_claims": ("docs/NON_CLAIMS.md", "not_claimed"),
    "decomposition": ("docs/plan/PR73_DECOMPOSITION.md", "planning_only"),
}
SHA = re.compile(r"[0-9a-f]{40}\Z")
UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\Z")
DATE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
FORBIDDEN = (
    "all_gaps_closed=true",
    "merge_permitted=true",
    "production_release=true",
    "protected_main=true",
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
ACTIONS: dict[str, tuple[set[str], str, object, str]] = {
    "enable_repository_protection": (
        {"type", "issue", "target_branch"}, "target_branch", "main",
        "enable and independently verify branch protection and rulesets on `{target_branch}` under issue #{issue}",
    ),
    "decompose_frozen_pull_request": (
        {"type", "issue", "target_pull_request"}, "target_pull_request", 73,
        "decompose frozen PR #{target_pull_request} into bounded successor pull requests under issue #{issue}",
    ),
    "qualify_successor_pull_requests": (
        {"type", "issue", "target_set"}, "target_set", "bounded_successor_pull_requests",
        "qualify every member of `{target_set}` on its own exact final head under issue #{issue}",
    ),
    "complete_runtime_vertical_slice": (
        {"type", "issue", "target_component"}, "target_component", "agentport_browseractor_servo_receipts",
        "complete the `{target_component}` vertical slice under issue #{issue}",
    ),
    "qualify_installed_qemu_image": (
        {"type", "issue", "target_environment"}, "target_environment", "exact_installed_qemu_image",
        "prove the slice in an `{target_environment}` before hardware or release claims under issue #{issue}",
    ),
}


def _closed(value: Any, keys: set[str], label: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return False
    actual = set(value)
    if actual != keys:
        errors.append(
            f"{label} keys are not closed-schema compliant; "
            f"missing={sorted(keys - actual)}, unknown={sorted(actual - keys)}"
        )
        return False
    return True


def validate_integrated_state(record: Any) -> list[str]:
    errors: list[str] = []
    keys = {
        "schema", "updated", "repository_mode", "workspace_members", "capabilities",
        "governance_observation", "frozen_candidate", "next_work",
    }
    if not _closed(record, keys, "integrated_state", errors):
        return errors
    assert isinstance(record, dict)
    if record["schema"] != STATE_SCHEMA:
        errors.append(f"integrated_state schema must be {STATE_SCHEMA!r}")
    if not isinstance(record["updated"], str) or not DATE.fullmatch(record["updated"]):
        errors.append("integrated_state updated must be YYYY-MM-DD")
    if record["repository_mode"] != "FULL_PRODUCT_REPOSITORY":
        errors.append("integrated_state repository_mode is invalid")

    members = record["workspace_members"]
    if not isinstance(members, list) or not members or any(not isinstance(x, str) or not x for x in members):
        errors.append("workspace_members must be non-empty strings")
    elif len(members) != len(set(members)):
        errors.append("workspace_members contains duplicates")

    capabilities = record["capabilities"]
    if not isinstance(capabilities, list) or any(not isinstance(x, str) for x in capabilities):
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
    if observation is not None and _closed(observation, observation_keys, "governance_observation", errors):
        assert isinstance(observation, dict)
        fixed = {
            "kind": "github_repository_settings_snapshot",
            "source": "github_rest_api",
            "repository": "TrillionniumFoundation/trillionnium-os-desktop",
            "branch": "main",
            "validity": "snapshot_only",
        }
        for key, expected in fixed.items():
            if observation[key] != expected:
                errors.append(f"governance_observation {key} must be {expected!r}")
        if not isinstance(observation["observed_at"], str) or not UTC.fullmatch(observation["observed_at"]):
            errors.append("governance_observation lacks valid observed_at")
        observed_sha = observation["observed_main_sha"]
        if not isinstance(observed_sha, str) or not SHA.fullmatch(observed_sha) or set(observed_sha) == {"0"}:
            errors.append("governance_observation lacks valid observed_main_sha")
        if not isinstance(observation["branch_protected"], bool):
            errors.append("governance_observation branch_protected must be boolean")
        if observation["required_status_checks"] not in {"enabled", "disabled"}:
            errors.append("governance_observation required_status_checks is invalid")
        if set(observation["invalidation"]) != {"main_ref_change", "repository_settings_change"}:
            errors.append("governance_observation invalidation is incomplete")
        if not isinstance(observation["tracking_issue"], int) or observation["tracking_issue"] <= 0:
            errors.append("governance_observation tracking_issue must be positive")

    frozen = record["frozen_candidate"]
    frozen_keys = {"kind", "pull_request", "state", "decomposition_issue", "merge_policy"}
    if _closed(frozen, frozen_keys, "frozen_candidate", errors):
        expected = {
            "kind": "pull_request", "pull_request": 73, "state": "draft_frozen",
            "decomposition_issue": 78, "merge_policy": "never_merge_as_one_unit",
        }
        assert isinstance(frozen, dict)
        for key, value in expected.items():
            if frozen[key] != value:
                errors.append(f"frozen_candidate {key} must be {value!r}")

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
            keys, target_key, target, _ = ACTIONS[action_type]
            if not _closed(action, keys, label, errors):
                continue
            if action_type in seen:
                errors.append(f"{label} duplicates {action_type!r}")
            seen.add(action_type)
            if not isinstance(action["issue"], int) or action["issue"] <= 0:
                errors.append(f"{label} issue must be positive")
            if action[target_key] != target:
                errors.append(f"{label} {target_key} must be {target!r}")
    return errors


validate_integrated_state_record = validate_integrated_state

def render_integrated_state(project: dict[str, Any], record: dict[str, Any], paths: dict[str, str]) -> str:
    candidate = Path(paths["candidate"]).name
    non_claims = Path(paths["non_claims"]).name
    lines = [
        "<!-- generated from docs/status-documents.v1.json; do not edit by hand -->",
        "# TrillionniumOS Desktop — integrated state", "",
        f"**Updated:** {record['updated']}",
        f"**Canonical plan:** `{project['active_plan_revision']}`",
        f"**Repository mode:** `{record['repository_mode']}`",
        f"**Integrated implementation stage:** `{project['integrated_implementation_stage']}`",
        "**Machine truth:** [`manifests/project-state.v1.json`](../manifests/project-state.v1.json)",
        "**Structured projection record:** [`docs/status-documents.v1.json`](status-documents.v1.json)",
        "**Status scope:** integrated `main` facts only", "",
        f"This file is a deterministic projection of closed structured data. Read [`{candidate}`]({candidate}) for unmerged work and [`{non_claims}`]({non_claims}) for the claim ceiling.", "",
        "## Integrated work packages", "",
        *(f"- `{item}`" for item in project["integrated_completed_work_packages"]), "",
        "An integrated identifier does not widen its recorded claim ceiling.", "",
        "## Integrated workspace", "", "```text", *record["workspace_members"], "```", "",
        "The integrated foundation includes:", "",
        *(f"- {CAPABILITIES[item]}" for item in record["capabilities"]), "",
        "## Local control path", "", "```text",
        "already-connected AF_UNIX stream",
        "  -> kernel peer credentials and bounded authenticated framing",
        "  -> canonical Browser API codec",
        "  -> exactly-one request-bound AgentPort core",
        "  -> local process/service identity checks",
        "  -> durable receipt facts", "```", "",
        "This path does not establish semantic principal authority, production browser dispatch, user consent, capability issuance, or an external effect.", "",
        "## Product fail-closed state", "",
        "Production AgentPort remains disabled by default until a promoted BrowserActor and installed runtime satisfy their gates.",
    ]
    observation = record["governance_observation"]
    if observation is not None:
        protection = "protected" if observation["branch_protected"] else "unprotected"
        lines += ["", "## Repository governance observation", "",
            "**Observation kind:** `github_repository_settings_snapshot`",
            "**Observation source:** `github_rest_api`",
            f"**Observed repository:** `{observation['repository']}`",
            f"**Observed branch:** `{observation['branch']}`",
            f"**Observed at:** `{observation['observed_at']}`",
            f"**Observed main SHA:** `{observation['observed_main_sha']}`",
            "**Observation validity:** `snapshot_only`",
            "**Invalidated by:** `main_ref_change`, `repository_settings_change`", "",
            f"At this identity-bound snapshot, GitHub REST reported `main` as {protection} and required status checks as {observation['required_status_checks']}. Source CODEOWNERS files do not enforce approvals or no-bypass policy. Administrative controls remain tracked by issue #{observation['tracking_issue']}.", "",
            "Operational decisions must read live GitHub state; either declared invalidation event makes this snapshot historical."]
    frozen = record["frozen_candidate"]
    lines += ["", "## Unmerged work", "",
        f"PR #{frozen['pull_request']} is a `{frozen['state']}` candidate governed by issue #{frozen['decomposition_issue']} and policy `{frozen['merge_policy']}`. It is not integrated, and its evidence does not transfer to successors.", "",
        f"The committed candidate snapshot remains in `{candidate}` and is not silently promoted.", "",
        "## Next bounded work", ""]
    for index, action in enumerate(record["next_work"], 1):
        text = ACTIONS[action["type"]][3].format(**action)
        lines.append(f"{index}. {text}{';' if index < len(record['next_work']) else '.'}")
    lines += ["", "## Interpretation", "",
        "The narrower claim wins. Historical evidence cannot replace a current exact-head or exact-main rerun after invalidation.", ""]
    return "\n".join(lines)


def status_projection_errors(project: dict[str, Any], registry: dict[str, Any], documents: dict[str, str]) -> list[str]:
    errors: list[str] = []
    top_keys = {"schema", "project_state", "contract", "documents", "integrated_state"}
    _closed(registry, top_keys, REGISTRY_PATH, errors)
    for key, expected in {
        "schema": REGISTRY_SCHEMA,
        "project_state": "manifests/project-state.v1.json",
        "contract": CONTRACT_PATH,
    }.items():
        if registry.get(key) != expected:
            errors.append(f"{REGISTRY_PATH} {key} must be {expected!r}")
    raw_roles = registry.get("documents")
    if not isinstance(raw_roles, dict):
        return errors + [f"{REGISTRY_PATH} documents must be an object"]
    if set(raw_roles) != set(ROLES):
        errors.append(f"{REGISTRY_PATH} document roles are incomplete")
    paths: dict[str, str] = {}
    for role, (expected_path, expected_scope) in ROLES.items():
        entry = raw_roles.get(role)
        if not _closed(entry, {"path", "scope"}, f"document role {role}", errors):
            continue
        assert isinstance(entry, dict)
        if entry["path"] != expected_path or entry["scope"] != expected_scope:
            errors.append(f"document role {role} identity is invalid")
        paths[role] = entry["path"]
        if entry["path"] not in documents:
            errors.append(f"status document cannot be read: {entry['path']}")
    if len(paths) != len(ROLES) or len(set(paths.values())) != len(ROLES):
        return errors + ["status document roles must resolve uniquely"]

    entry = documents[paths["repository_entry"]]
    integrated = documents[paths["integrated"]]
    candidate = documents[paths["candidate"]]
    non_claims = documents[paths["non_claims"]]
    decomposition = documents[paths["decomposition"]]
    for value in (project.get("active_plan_revision"), project.get("integrated_implementation_stage")):
        if not isinstance(value, str) or value not in entry:
            errors.append(f"repository entry does not project project-state value {value!r}")
    for role in ("integrated", "candidate", "non_claims"):
        if paths[role] not in entry:
            errors.append(f"repository entry does not link {paths[role]}")
    for target in (Path(paths["integrated"]).name, Path(paths["non_claims"]).name):
        if target not in candidate:
            errors.append(f"candidate projection does not link {target}")
    for item in project.get("source_candidate_work_packages", []):
        if not isinstance(item, dict):
            errors.append("project-state candidate must be an object")
            continue
        for token in (f"`{item.get('id')}`", f"`{item.get('branch')}`", f"PR #{item.get('pr')}", f"`{item.get('status')}`"):
            if token not in candidate:
                errors.append(f"candidate projection is missing {token!r}")
    if "live GitHub state" not in candidate or "exact final head" not in candidate:
        errors.append("candidate projection lacks freshness policy")
    for item in project.get("not_claimed", []):
        if f"`{item}`" not in non_claims:
            errors.append(f"non-claims projection is missing {item!r}")
    if "PR #73" not in decomposition or "never merged as one unit" not in decomposition:
        errors.append("decomposition projection does not preserve frozen PR #73")

    record = registry.get("integrated_state")
    record_errors = validate_integrated_state(record)
    errors.extend(record_errors)
    if not record_errors and isinstance(record, dict):
        expected = render_integrated_state(project, record, paths)
        if integrated != expected:
            errors.append(f"{paths['integrated']} is not the exact projection of {REGISTRY_PATH}")
    for role in ("repository_entry", "integrated", "candidate"):
        text = documents[paths[role]].lower()
        for marker in FORBIDDEN:
            if marker in text:
                errors.append(f"{paths[role]} contains forbidden unproven closure marker {marker!r}")
    return errors


def _load_json(path: Path) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates)


def validate_repository(root: Path) -> list[str]:
    try:
        project = _load_json(root / "manifests/project-state.v1.json")
        registry = _load_json(root / REGISTRY_PATH)
        contract = _load_json(root / CONTRACT_PATH)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        return [f"cannot load structured status inputs: {error}"]
    errors: list[str] = []
    if not isinstance(project, dict) or not isinstance(registry, dict) or not isinstance(contract, dict):
        return ["structured status inputs must be JSON objects"]
    if contract.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        errors.append("status contract must use JSON Schema 2020-12")
    if contract.get("$id") != REGISTRY_SCHEMA or contract.get("additionalProperties") is not False:
        errors.append("status contract top level is not closed or has the wrong identity")
    state_schema = contract.get("properties", {}).get("integrated_state", {})
    if isinstance(state_schema, dict) and state_schema.get("$ref") == "#/$defs/integrated_state":
        state_schema = contract.get("$defs", {}).get("integrated_state", {})
    if not isinstance(state_schema, dict) or state_schema.get("additionalProperties") is not False:
        errors.append("status contract integrated_state is not closed")
    documents: dict[str, str] = {}
    for path, _scope in ROLES.values():
        try:
            documents[path] = (root / path).read_text(encoding="utf-8")
        except OSError:
            pass
    errors.extend(status_projection_errors(project, registry, documents))
    record = registry.get("integrated_state")
    if isinstance(record, dict):
        try:
            members = tomllib.loads((root / "Cargo.toml").read_text(encoding="utf-8"))["workspace"]["members"]
        except (OSError, KeyError, tomllib.TOMLDecodeError) as error:
            errors.append(f"cannot read Cargo workspace: {error}")
        else:
            if record.get("workspace_members") != members:
                errors.append("integrated_state workspace_members differ from Cargo.toml")
    return errors
