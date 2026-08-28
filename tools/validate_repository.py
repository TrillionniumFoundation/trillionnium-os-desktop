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

EXPECTED_WORKSPACE_MEMBERS = [
    "apps/hepta-browserd",
    "crates/hepta-agent-transport",
    "crates/trillionnium-contract-core",
    "crates/hepta-browser-contracts",
    "crates/hepta-session-core",
]

REQUIRED_PATHS = [
    ".github/workflows/ci.yml",
    ".github/CODEOWNERS",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "contracts/README.md",
    "contracts/agent-transport.v1.json",
    "crates/hepta-agent-transport/Cargo.toml",
    "crates/hepta-agent-transport/src/lib.rs",
    "docs/architecture/AUTHENTICATED_AGENT_TRANSPORT.md",
    "docs/evidence/2026-08-28-d0c02-authenticated-uds.md",
    "manifests/cargo-external-allowlist.json",
    "manifests/README.md",
]


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
    if len(schema_ids) != 4:
        fail(f"expected 4 JSON schemas, found {len(schema_ids)}")


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
    if docs_manifest.get("authenticated_agent_listener_implemented") is not False:
        fail("D0C-02 must not claim an authenticated product listener")
    if docs_manifest.get("transport_core_source_present") is not True:
        fail("docs manifest does not record the D0C-02 transport source")
    for path in [
        ROOT / "README.md",
        ROOT / "docs/CURRENT_STATE.md",
        plan_path,
        ROOT / "manifests/repository-state.json",
    ]:
        text = path.read_text(encoding="utf-8")
        if "/data/toshiba-dev/" in text:
            fail(
                "normative active file contains a local absolute source path: "
                f"{path.relative_to(ROOT)}"
            )


def dependency_spec_version(specification: object) -> str | None:
    if isinstance(specification, str):
        return specification
    if isinstance(specification, dict):
        version = specification.get("version")
        return version if isinstance(version, str) else None
    return None


def check_workspace_and_lock() -> None:
    cargo = load_toml(ROOT / "Cargo.toml")
    workspace = cargo.get("workspace", {})
    members = workspace.get("members", [])
    defaults = workspace.get("default-members", [])
    if members != EXPECTED_WORKSPACE_MEMBERS:
        fail(f"workspace members changed without validator update: {members!r}")
    if defaults != EXPECTED_WORKSPACE_MEMBERS:
        fail(f"default workspace members changed without validator update: {defaults!r}")

    boundary = load_json(ROOT / "manifests/product-boundary.json")
    graph = boundary.get("desktop_default_graph", {})
    forbidden_names = set(graph.get("forbidden_dependency_names", []))
    forbidden_fragments = tuple(graph.get("forbidden_path_fragments", []))
    workspace_names: set[str] = set()

    for member in EXPECTED_WORKSPACE_MEMBERS:
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
            workspace_names.add(name)
        for section_name in ("dependencies", "dev-dependencies", "build-dependencies"):
            section = manifest.get(section_name, {})
            if not isinstance(section, dict):
                continue
            for dependency_name, specification in section.items():
                if dependency_name in forbidden_names:
                    fail(
                        f"forbidden mobile dependency {dependency_name} in "
                        f"{manifest_path.relative_to(ROOT)}"
                    )
                if isinstance(specification, dict):
                    path_value = specification.get("path")
                    if isinstance(path_value, str) and any(
                        fragment in path_value for fragment in forbidden_fragments
                    ):
                        fail(
                            f"forbidden mobile path dependency {path_value} in "
                            f"{manifest_path.relative_to(ROOT)}"
                        )

    allowlist = load_json(ROOT / "manifests/cargo-external-allowlist.json")
    allowed_entries = allowlist.get("packages", [])
    allowed: dict[tuple[str, str], str] = {}
    for entry in allowed_entries:
        if not isinstance(entry, dict):
            fail("cargo external allowlist contains a non-object entry")
            continue
        name = entry.get("name")
        version = entry.get("version")
        checksum = entry.get("checksum")
        if not all(isinstance(value, str) for value in (name, version, checksum)):
            fail("cargo external allowlist entry is incomplete")
            continue
        key = (name, version)
        if key in allowed:
            fail(f"duplicate cargo allowlist entry {name} {version}")
        allowed[key] = checksum

    direct = allowlist.get("direct_dependencies", {})
    for member, expected_dependencies in direct.items():
        manifest = load_toml(ROOT / member / "Cargo.toml")
        actual_dependencies = manifest.get("dependencies", {})
        for name, exact_version in expected_dependencies.items():
            actual = dependency_spec_version(actual_dependencies.get(name))
            if actual != exact_version:
                fail(
                    f"{member} dependency {name} must be pinned to {exact_version}, "
                    f"found {actual!r}"
                )

    lock = load_toml(ROOT / "Cargo.lock")
    lock_packages = lock.get("package", [])
    locked_workspace: set[str] = set()
    locked_external: dict[tuple[str, str], str] = {}
    all_names: set[str] = set()

    for package in lock_packages:
        if not isinstance(package, dict):
            fail("Cargo.lock contains a non-object package entry")
            continue
        name = package.get("name")
        version = package.get("version")
        source = package.get("source")
        checksum = package.get("checksum")
        if not isinstance(name, str) or not isinstance(version, str):
            fail("Cargo.lock package is missing name/version")
            continue
        all_names.add(name)
        if source is None:
            locked_workspace.add(name)
            continue
        if source != "registry+https://github.com/rust-lang/crates.io-index":
            fail(f"non-registry Cargo dependency is forbidden: {name} {version} {source}")
            continue
        if not isinstance(checksum, str):
            fail(f"registry package lacks checksum: {name} {version}")
            continue
        key = (name, version)
        if key in locked_external:
            fail(f"duplicate Cargo.lock package {name} {version}")
        locked_external[key] = checksum

    if locked_workspace != workspace_names:
        fail(
            f"Cargo.lock workspace package set {sorted(locked_workspace)} differs from "
            f"workspace package set {sorted(workspace_names)}"
        )
    if locked_external != allowed:
        missing = sorted(set(allowed) - set(locked_external))
        unexpected = sorted(set(locked_external) - set(allowed))
        wrong = sorted(
            key
            for key in set(allowed) & set(locked_external)
            if allowed[key] != locked_external[key]
        )
        fail(
            "Cargo.lock external closure disagrees with allowlist: "
            f"missing={missing}, unexpected={unexpected}, checksum_mismatch={wrong}"
        )

    for package in lock_packages:
        if not isinstance(package, dict):
            continue
        for dependency in package.get("dependencies", []):
            if not isinstance(dependency, str):
                fail("Cargo.lock dependency reference is not a string")
                continue
            dependency_name = dependency.rsplit(" ", 1)[0]
            if dependency_name not in all_names:
                fail(
                    f"Cargo.lock dependency {dependency!r} from {package.get('name')} "
                    "does not resolve"
                )


def check_toolchain() -> None:
    toolchain = load_toml(ROOT / "rust-toolchain.toml").get("toolchain", {})
    lock = load_json(ROOT / "manifests/rust-toolchain.lock.json")
    if toolchain.get("channel") != lock.get("channel"):
        fail("rust-toolchain.toml channel disagrees with lock manifest")
    if sorted(toolchain.get("components", [])) != sorted(lock.get("components", [])):
        fail("rust toolchain components disagree with lock manifest")


def check_contract_alignment() -> None:
    errors = load_json(ROOT / "contracts/error-codes.v1.json")
    codes = [
        entry.get("code")
        for entry in errors.get("codes", [])
        if isinstance(entry, dict)
    ]
    if len(codes) != len(set(codes)):
        fail("duplicate error codes")
    rust_source = (
        ROOT / "crates/hepta-browser-contracts/src/lib.rs"
    ).read_text(encoding="utf-8")
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
            fail(
                f"golden request uses unknown operation {operation_type!r}: "
                f"{golden.relative_to(ROOT)}"
            )

    transport = load_json(ROOT / "contracts/agent-transport.v1.json")
    transport_source = (
        ROOT / "crates/hepta-agent-transport/src/lib.rs"
    ).read_text(encoding="utf-8")
    expected_markers = {
        f'pub const PROTOCOL_MAGIC: [u8; 8] = *b"{transport.get("protocol_magic_ascii")}";',
        f'pub const PROTOCOL_VERSION: u16 = {transport.get("protocol_version")};',
        f'pub const HEADER_BYTES: usize = {transport.get("header_bytes")};',
        f'pub const MAX_PAYLOAD_BYTES: usize = {transport.get("max_payload_bytes"):_};',
    }
    for marker in expected_markers:
        if marker not in transport_source:
            fail(f"transport contract/source mismatch: missing {marker!r}")
    for forbidden in ("UnixListener", "TcpListener", "TcpStream"):
        if forbidden in transport_source:
            fail(f"D0C-02 transport core must not contain {forbidden}")
    if "libc::getsockopt" not in transport_source or "SO_PEERCRED" not in transport_source:
        fail("transport source does not implement kernel peer-credential extraction")
    if "// SAFETY:" not in transport_source:
        fail("transport unsafe FFI lacks an adjacent safety explanation")
    evidence = (
        ROOT / "docs/evidence/2026-08-28-d0c02-authenticated-uds.md"
    ).read_text(encoding="utf-8")
    if "UNEXECUTED" not in evidence or "not merge-ready" not in evidence:
        fail("D0C-02 evidence must record the unexecuted Rust validation ceiling")


def check_filesystem_shape() -> None:
    for path in ROOT.rglob("*"):
        if path.is_symlink():
            fail(
                f"symlinks are forbidden in the product baseline: "
                f"{path.relative_to(ROOT)}"
            )
    for relative in REQUIRED_PATHS:
        if not (ROOT / relative).is_file():
            fail(f"required repository file is missing: {relative}")
    for forbidden in (
        ".github/workflows/materialize-d0c02.yml",
        ".github/workflows/verify-and-merge-d0c02.yml",
    ):
        if (ROOT / forbidden).exists():
            fail(f"one-shot materialization workflow must not ship: {forbidden}")


def main() -> int:
    check_json_files()
    check_plan_and_manifests()
    check_workspace_and_lock()
    check_toolchain()
    check_contract_alignment()
    check_filesystem_shape()
    if ERRORS:
        for error in ERRORS:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"repository validation failed with {len(ERRORS)} error(s)",
            file=sys.stderr,
        )
        return 1
    print("repository validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
