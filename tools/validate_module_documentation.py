#!/usr/bin/env python3
"""Validate one-to-one Cargo module documentation and review inventory."""

from __future__ import annotations

import json
import stat
import sys
import tomllib
from pathlib import Path
from typing import Any

# Resolve only the repository-owned helper for both CLI and importlib test use.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.documentation_claims import validate_claim_projection

ROOT = Path(__file__).resolve().parents[1]
REGISTRY_PATH = "manifests/modules.v1.json"
EXPECTED_SCHEMA = "trillionnium.desktop.modules.v1"
EXPECTED_PLAN_REVISION = "2026-08-29-d6"
MINIMUM_README_BYTES = 3000
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
REFERENCE_FIELDS = ("architecture", "contracts", "tests", "workflows")
REQUIRED_ENTRY_FIELDS = (
    "id",
    "package",
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
    "binaries",
    "features",
)
ALLOWED_KINDS = {"application", "library", "development-application"}


class DuplicateKeyError(ValueError):
    """Raised when JSON contains duplicate object members."""


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


def _load_toml(path: Path, errors: list[str]) -> dict[str, Any]:
    try:
        value = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        errors.append(f"cannot load {path}: {error}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{path} must contain one TOML table")
        return {}
    return value


def _safe_parts(value: object, label: str, errors: list[str]) -> tuple[str, ...] | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{label} must be a non-empty relative POSIX path")
        return None
    if "\\" in value:
        errors.append(f"{label} contains a backslash: {value!r}")
        return None
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        errors.append(f"{label} contains a control character")
        return None
    path = Path(value)
    parts = tuple(value.split("/"))
    if path.is_absolute() or not parts or any(part in {"", ".", ".."} for part in parts):
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
    if expected == "file" and not stat.S_ISREG(metadata.st_mode):
        errors.append(f"{label} is not a regular file: {current}")
        return None
    if expected == "directory" and not stat.S_ISDIR(metadata.st_mode):
        errors.append(f"{label} is not a directory: {current}")
        return None
    return current


def _string_list(value: object, label: str, errors: list[str], *, nonempty: bool) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item for item in value):
        errors.append(f"{label} must be a list of non-empty strings")
        return []
    result = list(value)
    if nonempty and not result:
        errors.append(f"{label} must not be empty")
    if len(result) != len(set(result)):
        errors.append(f"{label} contains duplicates")
    return result


def _cargo_bins(cargo: dict[str, Any], errors: list[str], label: str) -> list[dict[str, Any]]:
    raw = cargo.get("bin", [])
    if raw is None:
        raw = []
    if not isinstance(raw, list):
        errors.append(f"{label} [[bin]] inventory is not a list")
        return []
    result: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            errors.append(f"{label} [[bin]] #{index} is not a table")
            continue
        name = item.get("name")
        path = item.get("path")
        features = item.get("required-features", [])
        if not isinstance(name, str) or not name:
            errors.append(f"{label} [[bin]] #{index} has no name")
            continue
        if not isinstance(path, str) or not path:
            errors.append(f"{label} [[bin]] {name!r} has no explicit path")
            continue
        if not isinstance(features, list) or any(
            not isinstance(feature, str) or not feature for feature in features
        ):
            errors.append(f"{label} [[bin]] {name!r} has invalid required-features")
            continue
        result.append(
            {
                "name": name,
                "path": path,
                "required_features": list(features),
            }
        )
    return result


def _validate_binary_source_inventory(
    root: Path, module_path: str, cargo: dict[str, Any], errors: list[str],
) -> None:
    """Deny Cargo's implicit binary/build execution paths, including orphans."""
    package = cargo.get("package", {})
    if not isinstance(package, dict):
        return
    if package.get("autobins") is not False:
        errors.append(f"{module_path} package must set autobins = false")
    if package.get("build") is not False:
        errors.append(f"{module_path} package must set build = false")
    directory = root / module_path
    if (directory / "build.rs").exists() or (directory / "build.rs").is_symlink():
        errors.append(f"{module_path} unregistered build script is forbidden")
    registered = {item["path"] for item in _cargo_bins(cargo, errors, module_path)}
    candidates: list[Path] = []
    if (directory / "src").is_symlink():
        errors.append(f"{module_path} source directory traverses a symlink")
        return
    main = directory / "src/main.rs"
    if main.exists() or main.is_symlink():
        candidates.append(main)
    bindir = directory / "src/bin"
    if bindir.is_symlink():
        errors.append(f"{module_path} binary discovery directory traverses a symlink")
        return
    if bindir.exists():
        if not bindir.is_dir():
            errors.append(f"{module_path} src/bin is not a directory")
            return
        for entry in sorted(bindir.iterdir()):
            if entry.is_symlink():
                errors.append(f"{module_path} binary source traverses a symlink: {entry.name}")
            elif entry.is_file() and entry.suffix == ".rs":
                candidates.append(entry)
            elif entry.is_dir() and ((entry / "main.rs").exists() or (entry / "main.rs").is_symlink()):
                candidates.append(entry / "main.rs")
    for candidate in candidates:
        relative = candidate.relative_to(directory).as_posix()
        if candidate.is_symlink() or not candidate.is_file():
            errors.append(f"{module_path} binary source must be a regular non-symlink file: {relative}")
        elif relative not in registered:
            errors.append(f"{module_path} unregistered conventional binary source: {relative}")


def _registry_bins(value: object, label: str, errors: list[str]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        errors.append(f"{label} binaries must be a list")
        return []
    result: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"{label} binary #{index} is not an object")
            continue
        if set(item) != {"name", "path", "required_features"}:
            errors.append(
                f"{label} binary #{index} must contain name, path, and required_features only"
            )
            continue
        name = item.get("name")
        path = item.get("path")
        features = item.get("required_features")
        if not isinstance(name, str) or not name:
            errors.append(f"{label} binary #{index} has invalid name")
            continue
        if not isinstance(path, str) or not path:
            errors.append(f"{label} binary {name!r} has invalid path")
            continue
        if not isinstance(features, list) or any(
            not isinstance(feature, str) or not feature for feature in features
        ):
            errors.append(f"{label} binary {name!r} has invalid required_features")
            continue
        if len(features) != len(set(features)):
            errors.append(f"{label} binary {name!r} repeats a required feature")
        result.append(
            {
                "name": name,
                "path": path,
                "required_features": list(features),
            }
        )
    if len([item["name"] for item in result]) != len({item["name"] for item in result}):
        errors.append(f"{label} binaries contain duplicate names")
    return result


def _validate_policy(registry: dict[str, Any], errors: list[str]) -> None:
    if registry.get("schema") != EXPECTED_SCHEMA:
        errors.append(f"module registry schema must be {EXPECTED_SCHEMA!r}")
    if registry.get("plan_revision") != EXPECTED_PLAN_REVISION:
        errors.append(f"module registry plan_revision must be {EXPECTED_PLAN_REVISION!r}")
    policy = registry.get("policy")
    if not isinstance(policy, dict):
        errors.append("module registry policy must be an object")
        return
    required_true = {
        "workspace_members_must_match_exactly",
        "module_readme_required",
        "binary_inventory_must_match_cargo",
        "explicit_binary_targets_only",
        "build_scripts_forbidden",
        "feature_inventory_must_match_cargo",
        "references_must_exist",
        "symlink_paths_forbidden",
        "lower_tier_never_implies_higher_tier",
    }
    for key in sorted(required_true):
        if policy.get(key) is not True:
            errors.append(f"module registry policy {key!r} must be true")
    if policy.get("minimum_readme_bytes") != MINIMUM_README_BYTES:
        errors.append(
            f"module registry minimum_readme_bytes must be {MINIMUM_README_BYTES}"
        )
    if policy.get("required_sections") != list(REQUIRED_SECTIONS):
        errors.append("module registry required_sections disagrees with validator")


def _validate_integration_files(root: Path, errors: list[str]) -> None:
    requirements = {
        "Makefile": "python3 tools/validate_module_documentation.py",
        ".github/workflows/ci.yml": "python3 tools/validate_module_documentation.py",
        "docs/README.md": "modules/README.md",
        "CONTRIBUTING.md": "validate_module_documentation.py",
    }
    for relative, marker in requirements.items():
        path = _path_without_symlinks(
            root, relative, relative, errors, expected="file"
        )
        if path is None:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            errors.append(f"cannot read {relative}: {error}")
            continue
        if marker not in text:
            errors.append(f"{relative} does not invoke/reference {marker!r}")


def validate(root: Path = ROOT, *, integration_checks: bool = True) -> list[str]:
    errors: list[str] = []
    try:
        root_metadata = root.lstat()
    except OSError as error:
        return [f"repository root is unavailable: {error}"]
    if stat.S_ISLNK(root_metadata.st_mode) or not stat.S_ISDIR(root_metadata.st_mode):
        return ["repository root must be a real directory, not a symlink"]

    cargo_path = _path_without_symlinks(
        root, "Cargo.toml", "root Cargo.toml", errors, expected="file"
    )
    registry_path = _path_without_symlinks(
        root, REGISTRY_PATH, "module registry", errors, expected="file"
    )
    if cargo_path is None or registry_path is None:
        return errors

    cargo = _load_toml(cargo_path, errors)
    registry = _load_json(registry_path, errors)
    _validate_policy(registry, errors)

    workspace = cargo.get("workspace")
    if not isinstance(workspace, dict):
        errors.append("root Cargo.toml has no [workspace] table")
        workspace = {}
    members = _string_list(
        workspace.get("members"), "Cargo workspace members", errors, nonempty=True
    )
    default_members = _string_list(
        workspace.get("default-members"),
        "Cargo workspace default-members",
        errors,
        nonempty=True,
    )
    if default_members != members:
        errors.append("Cargo default-members must exactly equal workspace members")

    entries = registry.get("modules")
    if not isinstance(entries, list):
        errors.append("module registry modules must be a list")
        entries = []

    ids: list[str] = []
    packages: list[str] = []
    paths: list[str] = []
    for index, entry in enumerate(entries):
        label = f"module registry entry #{index}"
        if not isinstance(entry, dict):
            errors.append(f"{label} is not an object")
            continue
        missing = [field for field in REQUIRED_ENTRY_FIELDS if field not in entry]
        extra = sorted(set(entry) - set(REQUIRED_ENTRY_FIELDS))
        if missing:
            errors.append(f"{label} is missing fields {missing}")
        if extra:
            errors.append(f"{label} has unknown fields {extra}")
        if missing:
            continue

        module_id = entry.get("id")
        package = entry.get("package")
        module_path = entry.get("path")
        documentation = entry.get("documentation")
        for name, value in (
            ("id", module_id),
            ("package", package),
            ("path", module_path),
            ("status", entry.get("status")),
            ("claim_ceiling", entry.get("claim_ceiling")),
            ("owner_class", entry.get("owner_class")),
        ):
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{label} {name} must be a non-empty string")
        if not all(isinstance(value, str) and value for value in (module_id, package, module_path)):
            continue
        ids.append(module_id)
        packages.append(package)
        paths.append(module_path)

        if entry.get("kind") not in ALLOWED_KINDS:
            errors.append(f"{label} has unsupported kind {entry.get('kind')!r}")
        expected_doc = f"{module_path}/README.md"
        if documentation != expected_doc:
            errors.append(
                f"{label} documentation must be {expected_doc!r}, found {documentation!r}"
            )

        directory = _path_without_symlinks(
            root, module_path, f"{label} path", errors, expected="directory"
        )
        cargo_file = _path_without_symlinks(
            root,
            f"{module_path}/Cargo.toml",
            f"{label} Cargo.toml",
            errors,
            expected="file",
        )
        readme = _path_without_symlinks(
            root, documentation, f"{label} documentation", errors, expected="file"
        )
        if directory is None or cargo_file is None or readme is None:
            continue

        module_cargo = _load_toml(cargo_file, errors)
        _validate_binary_source_inventory(root, module_path, module_cargo, errors)
        package_table = module_cargo.get("package")
        if not isinstance(package_table, dict) or package_table.get("name") != package:
            errors.append(f"{label} package does not match {cargo_file}")
        try:
            readme_bytes = readme.read_bytes()
            readme_text = readme_bytes.decode("utf-8")
        except (OSError, UnicodeError) as error:
            errors.append(f"cannot read {documentation}: {error}")
            readme_text = ""
            readme_bytes = b""
        errors.extend(validate_claim_projection(
            readme_text, entry.get("status"), entry.get("claim_ceiling"),
            kind="module", label=str(documentation),
        ))
        if len(readme_bytes) < MINIMUM_README_BYTES:
            errors.append(
                f"{documentation} is too short: {len(readme_bytes)} < {MINIMUM_README_BYTES}"
            )
        positions: list[int] = []
        for heading in REQUIRED_SECTIONS:
            count = readme_text.count(heading)
            if count != 1:
                errors.append(f"{documentation} must contain {heading!r} exactly once")
            positions.append(readme_text.find(heading))
        if all(position >= 0 for position in positions) and positions != sorted(positions):
            errors.append(f"{documentation} required sections are out of order")
        for marker in (
            f"**Module registry ID:** `{module_id}`",
            f"**Workspace path:** `{module_path}`",
            "**Claim ceiling:**",
            "manifests/modules.v1.json",
        ):
            if marker not in readme_text:
                errors.append(f"{documentation} is missing marker {marker!r}")

        cargo_features_table = module_cargo.get("features", {})
        if not isinstance(cargo_features_table, dict):
            errors.append(f"{cargo_file} [features] must be a table")
            cargo_features_table = {}
        registry_features = _string_list(
            entry.get("features"), f"{label} features", errors, nonempty=False
        )
        cargo_features = list(cargo_features_table.keys())
        if registry_features != cargo_features:
            errors.append(
                f"{label} features {registry_features!r} do not match Cargo {cargo_features!r}"
            )

        cargo_bins = _cargo_bins(module_cargo, errors, str(cargo_file))
        registry_bins = _registry_bins(entry.get("binaries"), label, errors)
        if registry_bins != cargo_bins:
            errors.append(
                f"{label} binary inventory {registry_bins!r} does not match Cargo {cargo_bins!r}"
            )
        for binary in registry_bins:
            _path_without_symlinks(
                root,
                f"{module_path}/{binary['path']}",
                f"{label} binary {binary['name']}",
                errors,
                expected="file",
            )
            for feature in binary["required_features"]:
                if feature not in registry_features:
                    errors.append(
                        f"{label} binary {binary['name']!r} requires unregistered feature {feature!r}"
                    )

        for field in REFERENCE_FIELDS:
            references = _string_list(
                entry.get(field), f"{label} {field}", errors, nonempty=True
            )
            for reference in references:
                _path_without_symlinks(
                    root,
                    reference,
                    f"{label} {field} reference",
                    errors,
                    expected="file",
                )

    for label, values in (("ids", ids), ("packages", packages), ("paths", paths)):
        if len(values) != len(set(values)):
            errors.append(f"module registry contains duplicate {label}")
    if paths != members:
        errors.append(
            "module registry paths must exactly match Cargo workspace order: "
            f"registry={paths!r}, cargo={members!r}"
        )

    index = _path_without_symlinks(
        root, "docs/modules/README.md", "module documentation index", errors, expected="file"
    )
    if index is not None:
        try:
            index_text = index.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            errors.append(f"cannot read module documentation index: {error}")
            index_text = ""
        for package, path in zip(packages, paths):
            marker = f"(../../{path}/README.md)"
            if f"`{package}`" not in index_text or marker not in index_text:
                errors.append(f"module documentation index is missing {package!r}")

    if integration_checks:
        _validate_integration_files(root, errors)
    return errors


def main() -> int:
    errors = validate()
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"module documentation validation failed with {len(errors)} error(s)",
            file=sys.stderr,
        )
        return 1
    print("module documentation validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
