#!/usr/bin/env python3
"""Fail-closed repository consistency checks for the desktop product."""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []


def fail(message: str) -> None:
    ERRORS.append(message)


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"invalid JSON {path.relative_to(ROOT)}: {error}")
        return {}


def load_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, tomllib.TOMLDecodeError) as error:
        fail(f"invalid TOML {path.relative_to(ROOT)}: {error}")
        return {}


def check_json_files() -> None:
    schema_ids: dict[str, Path] = {}
    for path in sorted(ROOT.rglob("*.json")):
        document = load_json(path)
        if isinstance(document, dict) and "$id" in document:
            schema_id = document["$id"]
            if not isinstance(schema_id, str):
                fail(f"schema id is not a string in {path.relative_to(ROOT)}")
            elif schema_id in schema_ids:
                fail(
                    f"duplicate schema id {schema_id} in "
                    f"{schema_ids[schema_id].relative_to(ROOT)} and {path.relative_to(ROOT)}"
                )
            else:
                schema_ids[schema_id] = path
    expected_schema_count = 4
    if len(schema_ids) != expected_schema_count:
        fail(f"expected {expected_schema_count} JSON schemas, found {len(schema_ids)}")


def check_plan_and_manifests() -> None:
    docs_manifest = load_json(ROOT / "docs/MANIFEST.json")
    state = load_json(ROOT / "manifests/repository-state.json")
    active_plan = docs_manifest.get("active_plan")
    revision = docs_manifest.get("active_plan_revision")
    if not isinstance(active_plan, str):
        fail("docs manifest active_plan is missing")
        return
    plan_path = ROOT / "docs" / active_plan
    if not plan_path.is_file():
        fail(f"active plan does not exist: docs/{active_plan}")
        return
    plan_text = plan_path.read_text(encoding="utf-8")
    for required in [str(revision), "FULL_PRODUCT_REPOSITORY", "D0C-02", "D0A-01"]:
        if required not in plan_text:
            fail(f"active plan is missing required marker {required!r}")
    if state.get("active_plan") != f"docs/{active_plan}":
        fail("repository-state active_plan disagrees with docs manifest")
    if state.get("active_plan_revision") != revision:
        fail("repository-state revision disagrees with docs manifest")
    if docs_manifest.get("repository_mode") != "FULL_PRODUCT_REPOSITORY":
        fail("repository mode is not FULL_PRODUCT_REPOSITORY")
    for path in [
        ROOT / "README.md",
        ROOT / "docs/CURRENT_STATE.md",
        plan_path,
        ROOT / "manifests/repository-state.json",
    ]:
        text = path.read_text(encoding="utf-8")
        if "/data/toshiba-dev/" in text:
            fail(f"normative active file contains a local absolute source path: {path.relative_to(ROOT)}")


def check_workspace() -> None:
    cargo = load_toml(ROOT / "Cargo.toml")
    workspace = cargo.get("workspace", {})
    members = workspace.get("members", [])
    expected_members = [
        "apps/hepta-browserd",
        "crates/trillionnium-contract-core",
        "crates/hepta-browser-contracts",
        "crates/hepta-session-core",
    ]
    if members != expected_members:
        fail(f"workspace members changed without validator update: {members!r}")
    package_names: set[str] = set()
    boundary = load_json(ROOT / "manifests/product-boundary.json")
    graph = boundary.get("desktop_default_graph", {})
    forbidden_names = set(graph.get("forbidden_dependency_names", []))
    forbidden_fragments = tuple(graph.get("forbidden_path_fragments", []))

    for member in members:
        manifest_path = ROOT / member / "Cargo.toml"
        if not manifest_path.is_file():
            fail(f"workspace member is missing Cargo.toml: {member}")
            continue
        manifest = load_toml(manifest_path)
        package = manifest.get("package", {})
        name = package.get("name")
        if not isinstance(name, str):
            fail(f"workspace member has no package name: {member}")
        else:
            package_names.add(name)
        for section_name in ["dependencies", "dev-dependencies", "build-dependencies"]:
            section = manifest.get(section_name, {})
            if not isinstance(section, dict):
                continue
            for dependency_name, specification in section.items():
                if dependency_name in forbidden_names:
                    fail(f"forbidden mobile dependency {dependency_name} in {manifest_path.relative_to(ROOT)}")
                if isinstance(specification, dict):
                    path_value = specification.get("path")
                    if isinstance(path_value, str) and any(fragment in path_value for fragment in forbidden_fragments):
                        fail(f"forbidden mobile path dependency {path_value} in {manifest_path.relative_to(ROOT)}")

    lock = load_toml(ROOT / "Cargo.lock")
    locked_names = {package.get("name") for package in lock.get("package", []) if isinstance(package, dict)}
    if package_names != locked_names:
        fail(f"Cargo.lock package set {sorted(locked_names)} differs from workspace package set {sorted(package_names)}")


def check_toolchain() -> None:
    toolchain = load_toml(ROOT / "rust-toolchain.toml").get("toolchain", {})
    lock = load_json(ROOT / "manifests/rust-toolchain.lock.json")
    if toolchain.get("channel") != lock.get("channel"):
        fail("rust-toolchain.toml channel disagrees with lock manifest")
    if sorted(toolchain.get("components", [])) != sorted(lock.get("components", [])):
        fail("rust toolchain components disagree with lock manifest")


def check_contract_alignment() -> None:
    errors = load_json(ROOT / "contracts/error-codes.v1.json")
    codes = [entry.get("code") for entry in errors.get("codes", []) if isinstance(entry, dict)]
    if len(codes) != len(set(codes)):
        fail("duplicate error codes")
    rust_source = (ROOT / "crates/hepta-browser-contracts/src/lib.rs").read_text(encoding="utf-8")
    for code in codes:
        if not isinstance(code, str) or f'"{code}"' not in rust_source:
            fail(f"error code {code!r} is not represented in Rust BrowserErrorCode")

    browser_schema = load_json(ROOT / "contracts/browser-api.v1.schema.json")
    operation_definitions = {
        name
        for name in browser_schema.get("$defs", {})
        if name
        in {
            "health",
            "session_create",
            "session_snapshot",
            "session_close",
            "page_navigate",
            "page_observe",
            "page_act",
            "page_wait",
            "page_extract",
        }
    }
    for golden in sorted((ROOT / "contracts/golden").glob("*.request.json")):
        request = load_json(golden)
        if request.get("protocol") != "trillionnium.desktop.browser-api.v1":
            fail(f"golden request has wrong protocol: {golden.relative_to(ROOT)}")
        operation_type = request.get("operation", {}).get("type")
        if operation_type not in operation_definitions:
            fail(f"golden request uses unknown operation {operation_type!r}: {golden.relative_to(ROOT)}")


def check_filesystem_shape() -> None:
    for path in ROOT.rglob("*"):
        if path.is_symlink():
            fail(f"symlinks are forbidden in the product baseline: {path.relative_to(ROOT)}")
    required = [
        ".github/workflows/ci.yml",
        ".github/CODEOWNERS",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "LICENSE",
        "contracts/README.md",
        "manifests/README.md",
    ]
    for relative in required:
        if not (ROOT / relative).is_file():
            fail(f"required repository file is missing: {relative}")


def main() -> int:
    check_json_files()
    check_plan_and_manifests()
    check_workspace()
    check_toolchain()
    check_contract_alignment()
    check_filesystem_shape()
    if ERRORS:
        for error in ERRORS:
            print(f"ERROR: {error}", file=sys.stderr)
        print(f"repository validation failed with {len(ERRORS)} error(s)", file=sys.stderr)
        return 1
    print("repository validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
