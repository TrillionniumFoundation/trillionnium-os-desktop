#!/usr/bin/env python3
"""Validate non-Cargo component inventory and technical documentation."""

from __future__ import annotations

import json
import os
import stat
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = "manifests/components.v1.json"
INDEX_PATH = "docs/components/README.md"
EXPECTED_SCHEMA = "trillionnium.desktop.components.v1"
EXPECTED_PLAN_REVISION = "2026-08-29-d6"
MINIMUM_DOCUMENTATION_BYTES = 2000
REQUIRED_SECTIONS = (
    "## Status and claim ceiling",
    "## Responsibilities",
    "## Non-responsibilities",
    "## Dependency and call direction",
    "## Public interfaces and entrypoints",
    "## Configuration and features",
    "## State, concurrency, and failure semantics",
    "## Security invariants",
    "## Testing and evidence",
    "## Operations and troubleshooting",
    "## Compatibility and change protocol",
)
REQUIRED_ENTRY_FIELDS = {
    "id",
    "path",
    "kind",
    "status",
    "claim_ceiling",
    "owner_class",
    "documentation",
    "architecture",
    "contracts",
    "tests",
    "workflows",
    "entrypoints",
    "security_invariants",
}
ALLOWED_KINDS = {
    "automation",
    "contract-catalog",
    "documentation",
    "experiment",
    "manifest-catalog",
    "packaging",
    "platform-boundary",
    "runtime-boundary",
    "service-boundary",
    "test-system",
    "toolchain",
    "worker-boundary",
}
EXPANDED_TOP_LEVEL = {"experiments", "packaging"}
EXCLUDED_TOP_LEVEL = {".git", "apps", "crates", "target"}
INTEGRATION_MARKERS = {
    "Makefile": "python3 tools/validate_component_documentation.py",
    ".github/workflows/ci.yml": "python3 tools/validate_component_documentation.py",
    "CONTRIBUTING.md": "validate_component_documentation.py",
    "README.md": "validate_component_documentation.py",
    "docs/README.md": "components/README.md",
}


class DuplicateKeyError(ValueError):
    """Raised when a policy JSON object repeats a member name."""


def _object_no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise DuplicateKeyError(f"duplicate JSON member {key!r}")
        value[key] = item
    return value


def _load_json(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_object_no_duplicates,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, DuplicateKeyError) as error:
        errors.append(f"cannot load {path}: {error}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path} must contain one JSON object")
        return {}
    return value


def _safe_parts(value: object, label: str, errors: list[str]) -> tuple[str, ...] | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{label} must be a non-empty relative POSIX path")
        return None
    if value.startswith("/") or "\\" in value:
        errors.append(f"{label} must be a repository-relative POSIX path: {value!r}")
        return None
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        errors.append(f"{label} contains a control character")
        return None
    parts = tuple(value.split("/"))
    if not parts or any(part in {"", ".", ".."} for part in parts):
        errors.append(f"{label} is not a canonical relative path: {value!r}")
        return None
    return parts


def _path_without_symlinks(
    root: Path,
    relative: object,
    label: str,
    errors: list[str],
    *,
    expected: str,
) -> Path | None:
    parts = _safe_parts(relative, label, errors)
    if parts is None:
        return None
    current = root
    for index, part in enumerate(parts):
        current = current / part
        try:
            metadata = current.lstat()
        except OSError as error:
            errors.append(f"{label} is unavailable at {current}: {error}")
            return None
        if stat.S_ISLNK(metadata.st_mode):
            errors.append(f"{label} traverses a symlink at {current}")
            return None
        if index < len(parts) - 1 and not stat.S_ISDIR(metadata.st_mode):
            errors.append(f"{label} parent is not a directory: {current}")
            return None
    try:
        metadata = current.lstat()
    except OSError as error:
        errors.append(f"{label} is unavailable at {current}: {error}")
        return None
    expected_mode = stat.S_ISREG if expected == "file" else stat.S_ISDIR
    if not expected_mode(metadata.st_mode):
        errors.append(f"{label} is not a {expected}: {current}")
        return None
    return current


def _contains_regular_file(path: Path) -> bool:
    for current, directory_names, file_names in os.walk(path, followlinks=False):
        current_path = Path(current)
        directory_names[:] = [
            name
            for name in directory_names
            if not (current_path / name).is_symlink() and name != "__pycache__"
        ]
        for name in file_names:
            candidate = current_path / name
            try:
                if candidate.is_symlink():
                    continue
                if candidate.is_file():
                    return True
            except OSError:
                continue
    return False


def discover_component_paths(root: Path) -> list[str]:
    """Discover the repository's non-Cargo component boundaries.

    Root Cargo members are governed by ``modules.v1.json``.  Every other
    top-level source/governance directory is one component, except experiments
    and packaging, whose immediate child directories are independent evidence
    or installation boundaries.
    """

    result: list[str] = []
    for entry in sorted(root.iterdir(), key=lambda path: path.name):
        name = entry.name
        if name in EXCLUDED_TOP_LEVEL or name == "__pycache__":
            continue
        if name.startswith(".") and name != ".github":
            continue
        if not entry.is_dir() or entry.is_symlink():
            continue
        if name in EXPANDED_TOP_LEVEL:
            for child in sorted(entry.iterdir(), key=lambda path: path.name):
                if child.is_dir() and not child.is_symlink() and _contains_regular_file(child):
                    result.append(child.relative_to(root).as_posix())
            continue
        if _contains_regular_file(entry):
            result.append(name)
    return result


def _string_list(
    value: object,
    label: str,
    errors: list[str],
    *,
    minimum: int,
) -> list[str]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item for item in value
    ):
        errors.append(f"{label} must be a list of non-empty strings")
        return []
    result = list(value)
    if len(result) < minimum:
        errors.append(f"{label} must contain at least {minimum} item(s)")
    if len(result) != len(set(result)):
        errors.append(f"{label} contains duplicates")
    return result


def _validate_policy(registry: dict[str, Any], errors: list[str]) -> None:
    if registry.get("schema") != EXPECTED_SCHEMA:
        errors.append(f"component registry schema must be {EXPECTED_SCHEMA!r}")
    if registry.get("plan_revision") != EXPECTED_PLAN_REVISION:
        errors.append(
            f"component registry plan_revision must be {EXPECTED_PLAN_REVISION!r}"
        )
    policy = registry.get("policy")
    if not isinstance(policy, dict):
        errors.append("component registry policy must be an object")
        return
    required_true = {
        "non_cargo_components_must_match_discovery",
        "component_documentation_required",
        "references_must_exist",
        "symlink_paths_forbidden",
        "security_invariants_required",
        "lower_tier_never_implies_higher_tier",
    }
    for key in sorted(required_true):
        if policy.get(key) is not True:
            errors.append(f"component registry policy {key!r} must be true")
    if policy.get("minimum_documentation_bytes") != MINIMUM_DOCUMENTATION_BYTES:
        errors.append(
            "component registry minimum_documentation_bytes must be "
            f"{MINIMUM_DOCUMENTATION_BYTES}"
        )
    if policy.get("required_sections") != list(REQUIRED_SECTIONS):
        errors.append("component registry required_sections disagree with validator")


def validate(root: Path = ROOT, *, expected_paths: set[str] | None = None) -> list[str]:
    errors: list[str] = []
    registry_path = _path_without_symlinks(
        root, REGISTRY_PATH, "component registry", errors, expected="file"
    )
    if registry_path is None:
        return errors
    registry = _load_json(registry_path, errors)
    _validate_policy(registry, errors)

    raw_components = registry.get("components")
    if not isinstance(raw_components, list):
        errors.append("component registry components must be a list")
        return errors

    discovered = (
        sorted(expected_paths)
        if expected_paths is not None
        else discover_component_paths(root)
    )
    registered_paths: list[str] = []
    registered_ids: list[str] = []

    for index, component in enumerate(raw_components):
        label = f"component #{index}"
        if not isinstance(component, dict):
            errors.append(f"{label} must be an object")
            continue
        missing = sorted(REQUIRED_ENTRY_FIELDS - set(component))
        unknown = sorted(set(component) - REQUIRED_ENTRY_FIELDS)
        if missing:
            errors.append(f"{label} is missing required fields: {missing}")
        if unknown:
            errors.append(f"{label} has unknown fields: {unknown}")

        component_id = component.get("id")
        if not isinstance(component_id, str) or not component_id:
            errors.append(f"{label} id must be a non-empty string")
            component_id = f"index-{index}"
        registered_ids.append(component_id)

        path_value = component.get("path")
        path_parts = _safe_parts(path_value, f"{component_id} path", errors)
        if path_parts is None:
            continue
        path_text = "/".join(path_parts)
        registered_paths.append(path_text)
        component_path = _path_without_symlinks(
            root,
            path_text,
            f"{component_id} component path",
            errors,
            expected="directory",
        )

        kind = component.get("kind")
        if kind not in ALLOWED_KINDS:
            errors.append(f"{component_id} has unsupported kind {kind!r}")
        for field in ("status", "claim_ceiling", "owner_class"):
            if not isinstance(component.get(field), str) or not component[field].strip():
                errors.append(f"{component_id} {field} must be a non-empty string")

        expected_documentation = f"{path_text}/README.md"
        documentation = component.get("documentation")
        if documentation != expected_documentation:
            errors.append(
                f"{component_id} documentation must be {expected_documentation!r}"
            )
        documentation_path = _path_without_symlinks(
            root,
            documentation,
            f"{component_id} documentation",
            errors,
            expected="file",
        )
        if documentation_path is not None:
            try:
                raw = documentation_path.read_bytes()
                text = raw.decode("utf-8")
            except (OSError, UnicodeError) as error:
                errors.append(f"cannot read {component_id} documentation: {error}")
            else:
                if len(raw) < MINIMUM_DOCUMENTATION_BYTES:
                    errors.append(
                        f"{component_id} documentation is too short: {len(raw)} bytes"
                    )
                for heading in REQUIRED_SECTIONS:
                    if heading not in text:
                        errors.append(
                            f"{component_id} documentation is missing {heading!r}"
                        )
                markers = (
                    f"**Component registry ID:** `{component_id}`",
                    f"**Component path:** `{path_text}`",
                    f"**Owner class:** `{component.get('owner_class')}`",
                    "**Claim ceiling:**",
                    "manifests/components.v1.json",
                )
                for marker in markers:
                    if marker not in text:
                        errors.append(
                            f"{component_id} documentation is missing marker {marker!r}"
                        )

        references = {
            "architecture": 1,
            "contracts": 1,
            "tests": 1,
            "workflows": 1,
            "entrypoints": 0,
        }
        for field, minimum in references.items():
            values = _string_list(
                component.get(field),
                f"{component_id} {field}",
                errors,
                minimum=minimum,
            )
            for reference_index, reference in enumerate(values):
                _path_without_symlinks(
                    root,
                    reference,
                    f"{component_id} {field}[{reference_index}]",
                    errors,
                    expected="file",
                )

        _string_list(
            component.get("security_invariants"),
            f"{component_id} security_invariants",
            errors,
            minimum=2,
        )
        if component_path is not None and not _contains_regular_file(component_path):
            errors.append(f"{component_id} component path contains no regular files")

    if len(registered_ids) != len(set(registered_ids)):
        errors.append("component registry contains duplicate ids")
    if len(registered_paths) != len(set(registered_paths)):
        errors.append("component registry contains duplicate paths")
    if registered_paths != discovered:
        errors.append(
            "component registry paths must exactly match non-Cargo discovery order: "
            f"registered={registered_paths!r}, discovered={discovered!r}"
        )

    index_path = _path_without_symlinks(
        root, INDEX_PATH, "component documentation index", errors, expected="file"
    )
    if index_path is not None:
        try:
            index_text = index_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            errors.append(f"cannot read component documentation index: {error}")
        else:
            if "manifests/components.v1.json" not in index_text:
                errors.append("component documentation index omits registry path")
            for component in raw_components:
                if not isinstance(component, dict):
                    continue
                component_id = component.get("id")
                documentation = component.get("documentation")
                if isinstance(component_id, str) and component_id not in index_text:
                    errors.append(
                        f"component documentation index is missing {component_id!r}"
                    )
                if isinstance(documentation, str) and documentation not in index_text:
                    errors.append(
                        f"component documentation index is missing {documentation!r}"
                    )

    for relative, marker in INTEGRATION_MARKERS.items():
        path = _path_without_symlinks(
            root, relative, f"integration file {relative}", errors, expected="file"
        )
        if path is None:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            errors.append(f"cannot read integration file {relative}: {error}")
            continue
        if marker not in text:
            errors.append(f"integration file {relative} is missing {marker!r}")
    return errors


def main() -> int:
    errors = validate(ROOT)
    if errors:
        print(
            f"component documentation validation failed with {len(errors)} error(s)",
            file=sys.stderr,
        )
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print("component documentation validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
