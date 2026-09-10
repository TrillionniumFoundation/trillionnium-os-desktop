#!/usr/bin/env python3
"""Fail-closed one-to-one Cargo module documentation validator."""

from __future__ import annotations

import json
import stat
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "manifests/modules.v1.json"
SCHEMA = "trillionnium.desktop.modules.v1"
PLAN = "2026-08-29-d6"
MINIMUM_README_BYTES = 3_000
REQUIRED_SECTIONS = (
    "## Status and claim ceiling",
    "## Responsibilities",
    "## Non-responsibilities",
    "## Dependency and call direction",
    "## Public API and binaries",
    "## Configuration and features",
    "## State, concurrency, and failure semantics",
    "## Security invariants",
    "## Testing and evidence",
    "## Operations and troubleshooting",
    "## Compatibility and change protocol",
)
ENTRY_FIELDS = {
    "id", "package", "path", "kind", "status", "claim_ceiling",
    "owner_class", "documentation", "architecture", "contracts", "tests",
    "workflows", "binaries", "features",
}
REFERENCE_FIELDS = ("architecture", "contracts", "tests", "workflows")
TRUE_POLICY_KEYS = {
    "workspace_members_must_match_exactly", "module_readme_required",
    "binary_inventory_must_match_cargo", "feature_inventory_must_match_cargo",
    "references_must_exist", "symlink_paths_forbidden",
    "lower_tier_never_implies_higher_tier", "explicit_binary_targets_only",
    "build_scripts_forbidden",
}


def _duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON member {key!r}")
        value[key] = item
    return value


def _json(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_duplicates)
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        errors.append(f"cannot load {path}: {error}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path} must contain an object")
        return {}
    return value


def _toml(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        errors.append(f"cannot load {path}: {error}")
        return {}


def _safe(root: Path, value: object, label: str, errors: list[str], *, directory: bool = False) -> Path | None:
    if not isinstance(value, str) or not value or "\\" in value:
        errors.append(f"{label} must be a canonical relative path")
        return None
    parts = value.split("/")
    if Path(value).is_absolute() or any(part in {"", ".", ".."} for part in parts):
        errors.append(f"{label} must be a canonical relative path")
        return None
    current = root
    for index, part in enumerate(parts):
        current /= part
        try:
            mode = current.lstat().st_mode
        except OSError as error:
            errors.append(f"{label} is unavailable at {current}: {error}")
            return None
        if stat.S_ISLNK(mode):
            errors.append(f"{label} traverses a symlink at {current}")
            return None
        if index < len(parts) - 1 and not stat.S_ISDIR(mode):
            errors.append(f"{label} parent is not a directory: {current}")
            return None
    if directory and not current.is_dir():
        errors.append(f"{label} is not a directory: {current}")
        return None
    if not directory and not current.is_file():
        errors.append(f"{label} is not a regular file: {current}")
        return None
    return current


def _strings(value: object, label: str, errors: list[str]) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        errors.append(f"{label} must be a list of non-empty strings")
        return []
    result = list(value)
    if len(result) != len(set(result)):
        errors.append(f"{label} contains duplicates")
    return result


def _cargo_bins(cargo: dict[str, Any], label: str, errors: list[str]) -> list[dict[str, Any]]:
    raw = cargo.get("bin", [])
    if not isinstance(raw, list):
        errors.append(f"{label} [[bin]] inventory must be a list")
        return []
    output: list[dict[str, Any]] = []
    for index, entry in enumerate(raw):
        if not isinstance(entry, dict):
            errors.append(f"{label} [[bin]] #{index} is invalid")
            continue
        name, path = entry.get("name"), entry.get("path")
        features = entry.get("required-features", [])
        if not isinstance(name, str) or not isinstance(path, str):
            errors.append(f"{label} [[bin]] #{index} lacks an explicit name/path")
            continue
        if not isinstance(features, list) or any(not isinstance(item, str) for item in features):
            errors.append(f"{label} [[bin]] {name!r} has invalid required-features")
            continue
        output.append({"name": name, "path": path, "required_features": list(features)})
    return output


def _registry_bins(value: object, label: str, errors: list[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        errors.append(f"{label} binaries must be a list")
        return []
    output: list[dict[str, Any]] = []
    expected = {"name", "path", "required_features"}
    for index, entry in enumerate(value):
        if not isinstance(entry, dict) or set(entry) != expected:
            errors.append(f"{label} binary #{index} has an invalid closed schema")
            continue
        name, path, features = entry["name"], entry["path"], entry["required_features"]
        if not isinstance(name, str) or not name or not isinstance(path, str) or not path:
            errors.append(f"{label} binary #{index} has invalid identity")
            continue
        if not isinstance(features, list) or any(not isinstance(item, str) or not item for item in features):
            errors.append(f"{label} binary {name!r} has invalid required_features")
            continue
        output.append({"name": name, "path": path, "required_features": list(features)})
    return output


def _conventional_binaries(root: Path, module: str) -> list[str]:
    base = root / module
    output: list[str] = []
    main = base / "src/main.rs"
    if main.exists() or main.is_symlink():
        output.append("src/main.rs")
    bin_dir = base / "src/bin"
    if bin_dir.exists() and not bin_dir.is_symlink():
        for entry in sorted(bin_dir.iterdir()):
            if entry.is_file() and entry.suffix == ".rs":
                output.append(entry.relative_to(base).as_posix())
            elif entry.is_dir() and (entry / "main.rs").is_file():
                output.append((entry / "main.rs").relative_to(base).as_posix())
    return output


def _policy(registry: dict[str, Any], errors: list[str]) -> None:
    if registry.get("schema") != SCHEMA:
        errors.append(f"module registry schema must be {SCHEMA!r}")
    if registry.get("plan_revision") != PLAN:
        errors.append(f"module registry plan_revision must be {PLAN!r}")
    policy = registry.get("policy")
    if not isinstance(policy, dict):
        errors.append("module registry policy must be an object")
        return
    for key in sorted(TRUE_POLICY_KEYS):
        if policy.get(key) is not True:
            errors.append(f"module registry policy {key!r} must be true")
    if policy.get("minimum_readme_bytes") != MINIMUM_README_BYTES:
        errors.append("module registry minimum_readme_bytes disagrees with validator")
    if policy.get("required_sections") != list(REQUIRED_SECTIONS):
        errors.append("module registry required_sections disagrees with validator")


def validate(root: Path = ROOT, *, integration_checks: bool = True) -> list[str]:
    errors: list[str] = []
    try:
        mode = root.lstat().st_mode
    except OSError as error:
        return [f"repository root unavailable: {error}"]
    if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
        return ["repository root must be a real directory"]

    cargo_path = _safe(root, "Cargo.toml", "root Cargo.toml", errors)
    registry_path = _safe(root, REGISTRY, "module registry", errors)
    if cargo_path is None or registry_path is None:
        return errors
    cargo = _toml(cargo_path, errors)
    registry = _json(registry_path, errors)
    _policy(registry, errors)

    workspace = cargo.get("workspace", {})
    if not isinstance(workspace, dict):
        errors.append("root Cargo.toml has no workspace table")
        workspace = {}
    members = _strings(workspace.get("members"), "workspace members", errors)
    if _strings(workspace.get("default-members"), "default members", errors) != members:
        errors.append("Cargo default-members must exactly equal workspace members")

    entries = registry.get("modules")
    if not isinstance(entries, list):
        errors.append("module registry modules must be a list")
        entries = []
    paths: list[str] = []
    ids: list[str] = []
    packages: list[str] = []

    for index, entry in enumerate(entries):
        label = f"module entry #{index}"
        if not isinstance(entry, dict):
            errors.append(f"{label} is not an object")
            continue
        if set(entry) != ENTRY_FIELDS:
            errors.append(f"{label} fields differ from closed schema")
            continue
        for field in ("id", "package", "path", "kind", "status", "claim_ceiling", "owner_class", "documentation"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                errors.append(f"{label} {field} must be a non-empty string")
        if not all(isinstance(entry.get(key), str) and entry[key] for key in ("id", "package", "path")):
            continue
        module = entry["path"]
        paths.append(module)
        ids.append(entry["id"])
        packages.append(entry["package"])
        module_dir = _safe(root, module, f"{label} path", errors, directory=True)
        manifest_path = _safe(root, f"{module}/Cargo.toml", f"{label} Cargo.toml", errors)
        readme_path = _safe(root, entry["documentation"], f"{label} documentation", errors)
        if entry["documentation"] != f"{module}/README.md":
            errors.append(f"{label} documentation must be {module}/README.md")
        if module_dir is None or manifest_path is None or readme_path is None:
            continue

        module_cargo = _toml(manifest_path, errors)
        package = module_cargo.get("package", {})
        if not isinstance(package, dict) or package.get("name") != entry["package"]:
            errors.append(f"{label} package does not match Cargo package name")
        if isinstance(package, dict):
            if package.get("autobins") is not False:
                errors.append(f"{module} package must set autobins = false")
            if package.get("build") is not False:
                errors.append(f"{module} package must set build = false")
        if (root / module / "build.rs").exists() or (root / module / "build.rs").is_symlink():
            errors.append(f"{module} unregistered build script is forbidden")

        cargo_bins = _cargo_bins(module_cargo, module, errors)
        registry_bins = _registry_bins(entry["binaries"], label, errors)
        if registry_bins != cargo_bins:
            errors.append(f"{label} binary inventory differs from Cargo")
        registered_sources = {item["path"] for item in cargo_bins}
        for source in _conventional_binaries(root, module):
            if source not in registered_sources:
                errors.append(f"{module} unregistered conventional binary source: {source}")
        for binary in registry_bins:
            _safe(root, f"{module}/{binary['path']}", f"{label} binary {binary['name']}", errors)

        cargo_features = list(module_cargo.get("features", {}).keys()) if isinstance(module_cargo.get("features", {}), dict) else []
        features = _strings(entry["features"], f"{label} features", errors)
        if features != cargo_features:
            errors.append(f"{label} features do not match Cargo order")
        for binary in registry_bins:
            unknown = sorted(set(binary["required_features"]) - set(features))
            if unknown:
                errors.append(f"{label} binary {binary['name']} uses unknown features {unknown}")

        for field in REFERENCE_FIELDS:
            values = _strings(entry[field], f"{label} {field}", errors)
            if not values:
                errors.append(f"{label} {field} must not be empty")
            for value in values:
                _safe(root, value, f"{label} {field} reference", errors)

        try:
            raw = readme_path.read_bytes()
            text = raw.decode("utf-8")
        except (OSError, UnicodeError) as error:
            errors.append(f"cannot read {readme_path}: {error}")
            continue
        if len(raw) < MINIMUM_README_BYTES:
            errors.append(f"{label} README is only {len(raw)} bytes; minimum is {MINIMUM_README_BYTES}")
        for section in REQUIRED_SECTIONS:
            if text.count(section) != 1:
                errors.append(f"{label} README must contain exactly one {section!r}")
        if text.count(f"Status: `{entry['status']}`") != 1:
            errors.append(f"{label} README status projection is missing, repeated, or stale")
        if text.count(f"Claim ceiling: `{entry['claim_ceiling']}`") != 1:
            errors.append(f"{label} README claim projection is missing, repeated, or stale")

    if paths != members:
        errors.append("module registry paths must exactly match Cargo workspace order")
    for values, name in ((ids, "ids"), (packages, "packages"), (paths, "paths")):
        if len(values) != len(set(values)):
            errors.append(f"module registry contains duplicate {name}")

    if integration_checks:
        markers = {
            "Makefile": "python3 tools/validate_module_documentation.py",
            ".github/workflows/ci.yml": "python3 tools/validate_module_documentation.py",
            "docs/README.md": "modules/README.md",
            "CONTRIBUTING.md": "validate_module_documentation.py",
        }
        for relative, marker in markers.items():
            path = _safe(root, relative, relative, errors)
            if path is not None and marker not in path.read_text(encoding="utf-8"):
                errors.append(f"{relative} does not reference {marker!r}")
    return errors


def main() -> int:
    errors = validate()
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    if errors:
        print(f"module documentation validation failed ({len(errors)} errors)", file=sys.stderr)
        return 1
    print("module documentation validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
