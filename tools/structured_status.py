"""Deterministic projection and repository adapter for the closed status model."""

from __future__ import annotations

import importlib.util
import json
import tomllib
from pathlib import Path
from typing import Any


def _load_model():
    path = Path(__file__).with_name("structured_status_model.py")
    spec = importlib.util.spec_from_file_location("structured_status_model", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MODEL = _load_model()
STATUS_REGISTRY_PATH = _MODEL.REGISTRY_PATH
STATUS_REGISTRY_SCHEMA = _MODEL.REGISTRY_SCHEMA
INTEGRATED_STATE_SCHEMA = _MODEL.STATE_SCHEMA
EXPECTED_WORKSPACE_MEMBERS = _MODEL.EXPECTED_WORKSPACE_MEMBERS
validate_integrated_state_record = _MODEL.validate_integrated_state


def render_integrated_state(
    project: dict[str, Any], record: dict[str, Any], paths: dict[str, str]
) -> str:
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
        *(f"- {_MODEL.CAPABILITIES[item]}" for item in record["capabilities"]), "",
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
        lines += [
            "", "## Repository governance observation", "",
            "**Observation kind:** `github_repository_settings_snapshot`",
            "**Observation source:** `github_rest_api`",
            f"**Observed repository:** `{observation['repository']}`",
            f"**Observed branch:** `{observation['branch']}`",
            f"**Observed at:** `{observation['observed_at']}`",
            f"**Observed main SHA:** `{observation['observed_main_sha']}`",
            "**Observation validity:** `snapshot_only`",
            "**Invalidated by:** `main_ref_change`, `repository_settings_change`", "",
            f"At this identity-bound snapshot, GitHub REST reported `main` as {protection} and required status checks as {observation['required_status_checks']}. Source CODEOWNERS files do not enforce approvals or no-bypass policy. Administrative controls remain tracked by issue #{observation['tracking_issue']}.", "",
            "Operational decisions must read live GitHub state; either declared invalidation event makes this snapshot historical.",
        ]
    frozen = record["frozen_candidate"]
    lines += [
        "", "## Unmerged work", "",
        f"PR #{frozen['pull_request']} is a `{frozen['state']}` candidate governed by issue #{frozen['decomposition_issue']} and policy `{frozen['merge_policy']}`. It is not integrated, and its evidence does not transfer to successors.", "",
        f"The committed candidate snapshot remains in `{candidate}` and is not silently promoted.", "",
        "## Next bounded work", "",
    ]
    for index, action in enumerate(record["next_work"], 1):
        text = _MODEL.ACTIONS[action["type"]][1].format(**action)
        suffix = ";" if index < len(record["next_work"]) else "."
        lines.append(f"{index}. {text}{suffix}")
    lines += [
        "", "## Interpretation", "",
        "The narrower claim wins. Historical evidence cannot replace a current exact-head or exact-main rerun after invalidation.", "",
    ]
    return "\n".join(lines)


def status_projection_errors(
    project: dict[str, Any], registry: dict[str, Any], documents: dict[str, str]
) -> list[str]:
    errors: list[str] = []
    _MODEL.closed(
        registry,
        {"schema", "project_state", "documents", "integrated_state"},
        _MODEL.REGISTRY_PATH,
        errors,
    )
    if registry.get("schema") != _MODEL.REGISTRY_SCHEMA:
        errors.append(f"{_MODEL.REGISTRY_PATH} schema must be {_MODEL.REGISTRY_SCHEMA!r}")
    if registry.get("project_state") != "manifests/project-state.v1.json":
        errors.append(f"{_MODEL.REGISTRY_PATH} project_state is invalid")

    raw_roles = registry.get("documents")
    if not isinstance(raw_roles, dict):
        return errors + [f"{_MODEL.REGISTRY_PATH} documents must be an object"]
    if set(raw_roles) != set(_MODEL.ROLES):
        errors.append(f"{_MODEL.REGISTRY_PATH} document roles are incomplete")
    paths: dict[str, str] = {}
    for role, (expected_path, expected_scope) in _MODEL.ROLES.items():
        entry = raw_roles.get(role)
        if not _MODEL.closed(entry, {"path", "scope"}, f"document role {role}", errors):
            continue
        assert isinstance(entry, dict)
        if entry != {"path": expected_path, "scope": expected_scope}:
            errors.append(f"document role {role} identity is invalid")
        paths[role] = entry["path"]
        if entry["path"] not in documents:
            errors.append(f"status document cannot be read: {entry['path']}")
    if len(paths) != len(_MODEL.ROLES) or len(set(paths.values())) != len(_MODEL.ROLES):
        return errors + ["status document roles must resolve uniquely"]

    entry = documents[paths["repository_entry"]]
    integrated = documents[paths["integrated"]]
    candidate = documents[paths["candidate"]]
    non_claims = documents[paths["non_claims"]]
    decomposition = documents[paths["decomposition"]]
    for value in (
        project.get("active_plan_revision"),
        project.get("integrated_implementation_stage"),
    ):
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
        for token in (
            f"`{item.get('id')}`",
            f"`{item.get('branch')}`",
            f"PR #{item.get('pr')}",
            f"`{item.get('status')}`",
        ):
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
    record_errors = _MODEL.validate_integrated_state(record)
    errors.extend(record_errors)
    if not record_errors and isinstance(record, dict):
        expected = render_integrated_state(project, record, paths)
        if integrated != expected:
            errors.append(
                f"{paths['integrated']} is not the exact projection of {_MODEL.REGISTRY_PATH}"
            )
    for role in ("repository_entry", "integrated", "candidate"):
        lowered = documents[paths[role]].lower()
        for marker in _MODEL.FORBIDDEN:
            if marker in lowered:
                errors.append(
                    f"{paths[role]} contains forbidden unproven closure marker {marker!r}"
                )
    return errors


def _load_json(path: Path) -> Any:
    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    return json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=reject_duplicates
    )


def validate_repository(root: Path) -> list[str]:
    try:
        project = _load_json(root / "manifests/project-state.v1.json")
        registry = _load_json(root / _MODEL.REGISTRY_PATH)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        return [f"cannot load structured status inputs: {error}"]
    if not isinstance(project, dict) or not isinstance(registry, dict):
        return ["structured status inputs must be JSON objects"]

    documents: dict[str, str] = {}
    for path, _scope in _MODEL.ROLES.values():
        try:
            documents[path] = (root / path).read_text(encoding="utf-8")
        except OSError:
            pass
    errors = status_projection_errors(project, registry, documents)
    record = registry.get("integrated_state")
    if isinstance(record, dict):
        try:
            members = tomllib.loads(
                (root / "Cargo.toml").read_text(encoding="utf-8")
            )["workspace"]["members"]
        except (OSError, KeyError, tomllib.TOMLDecodeError) as error:
            errors.append(f"cannot read Cargo workspace: {error}")
        else:
            if record.get("workspace_members") != members:
                errors.append("integrated_state workspace_members differ from Cargo.toml")
    return errors
