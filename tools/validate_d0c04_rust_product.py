#!/usr/bin/env python3
"""Fail-closed static validation for the D0C-04 Rust product candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_MEMBERS = [
    "apps/hepta-browserd",
    "crates/hepta-agent-transport",
    "crates/hepta-browser-codec",
    "crates/hepta-agent-port",
    "crates/trillionnium-contract-core",
    "crates/hepta-browser-contracts",
    "crates/hepta-session-core",
]
LOCAL_PACKAGES = {
    "hepta-agent-port",
    "hepta-agent-transport",
    "hepta-browser-codec",
    "hepta-browser-contracts",
    "hepta-browserd",
    "hepta-session-core",
    "trillionnium-contract-core",
}
REQUIRED_PATHS = [
    "crates/hepta-agent-port/Cargo.toml",
    "crates/hepta-agent-port/README.md",
    "crates/hepta-agent-port/src/lib.rs",
    "contracts/agent-port-bridge.v1.json",
]


class ValidationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def parse_toml(path: str) -> dict:
    with (ROOT / path).open("rb") as handle:
        return tomllib.load(handle)


def parse_json(path: str) -> dict:
    with (ROOT / path).open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    require(isinstance(value, dict), f"{path} must contain a JSON object")
    return value


def sha256(path: str) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def check_paths(checks: list[str]) -> None:
    for path in REQUIRED_PATHS:
        require((ROOT / path).is_file(), f"required path missing: {path}")
        require(not (ROOT / path).is_symlink(), f"required path is symlink: {path}")
        checks.append(f"path:{path}")


def check_workspace(checks: list[str]) -> None:
    workspace = parse_toml("Cargo.toml").get("workspace", {})
    require(workspace.get("members") == EXPECTED_MEMBERS, "workspace members drifted")
    require(workspace.get("default-members") == EXPECTED_MEMBERS, "default members drifted")
    require(workspace.get("resolver") == "3", "resolver drifted")
    package = workspace.get("package", {})
    require(package.get("edition") == "2024", "edition drifted")
    require(package.get("rust-version") == "1.93", "Rust version drifted")
    checks.extend(["workspace:members", "workspace:default-members", "workspace:toolchain"])


def check_lock(checks: list[str]) -> None:
    packages = parse_toml("Cargo.lock").get("package")
    require(isinstance(packages, list), "Cargo.lock package list missing")
    local = {p.get("name") for p in packages if "source" not in p}
    require(local == LOCAL_PACKAGES, f"local package set drifted: {sorted(local)}")
    allowlist = parse_json("manifests/cargo-external-allowlist.json")
    allowed = {(p["name"], p["version"], p["checksum"]) for p in allowlist["packages"]}
    actual = set()
    for package in packages:
        source = package.get("source")
        if source is None:
            continue
        require(source == "registry+https://github.com/rust-lang/crates.io-index", "non-crates.io source")
        require("checksum" in package, f"checksum missing for {package.get('name')}")
        actual.add((package["name"], package["version"], package["checksum"]))
    require(actual == allowed, "registry closure differs from allowlist")
    expected_direct = {
        "crates/hepta-agent-transport": {"libc": "=0.2.186", "sha2": "=0.10.9"},
        "crates/hepta-browser-codec": {"sha2": "=0.10.9"},
        "crates/hepta-agent-port": {"sha2": "=0.10.9"},
    }
    require(allowlist.get("direct_dependencies") == expected_direct, "direct allowlist drifted")
    for crate, expected in expected_direct.items():
        dependencies = parse_toml(f"{crate}/Cargo.toml").get("dependencies", {})
        for name, version in expected.items():
            require(dependencies.get(name) == version, f"{crate}: {name} pin drifted")
    checks.extend(["lock:local", "lock:registry", "lock:direct"])


def check_manifest(checks: list[str]) -> None:
    manifest = parse_toml("crates/hepta-agent-port/Cargo.toml")
    dependencies = manifest.get("dependencies", {})
    require(manifest.get("package", {}).get("name") == "hepta-agent-port", "wrong package name")
    require(dependencies.get("hepta-agent-transport", {}).get("path") == "../hepta-agent-transport", "transport is not local")
    require(dependencies.get("hepta-browser-codec", {}).get("path") == "../hepta-browser-codec", "codec is not local")
    require(dependencies.get("hepta-browser-contracts", {}).get("path") == "../hepta-browser-contracts", "contracts are not local")
    require(dependencies.get("sha2") == "=0.10.9", "sha2 pin drifted")
    require(set(dependencies) == {"hepta-agent-transport", "hepta-browser-codec", "hepta-browser-contracts", "sha2"}, "unexpected dependency")
    checks.append("agent-port:manifest")


def check_source(checks: list[str]) -> None:
    source = read("crates/hepta-agent-port/src/lib.rs")
    required = [
        "#![forbid(unsafe_code)]",
        "pub fn serve_one<",
        "pub fn serve_one_with_nonce_source<",
        "ServerConnection::accept_with_nonce_source",
        "connection.receive_request",
        "decode_request(&request_frame.payload)",
        "let outcome = handler.handle(&context, &request)?;",
        "let response = bind_response(&request, outcome)?;",
        "connection.send_response(request_frame.sequence",
        "request_effective_deadline",
        "MAX_HANDLER_JSON_DEPTH",
        "MAX_HANDLER_CONTAINER_ITEMS",
        "EffectClass::PotentialExternalEffect",
        "BrowserErrorCode::PolicyDenied",
        "browser_runtime_available",
        "pub fn self_check()",
    ]
    for token in required:
        require(token in source, f"missing source invariant: {token}")
        checks.append(f"source:{token}")
    for token in ["UnixListener", "TcpListener", "servo::", "WebDriver", "webdriver", "tokio::net", "std::process::Command", "unsafe {", "todo!", "unimplemented!"]:
        require(token not in source, f"forbidden source/authority token: {token}")
        checks.append(f"absent:{token}")
    decode_at = source.index("decode_request(&request_frame.payload)")
    handle_at = source.index("let outcome = handler.handle(&context, &request)?;")
    commit_at = source.index("connection.send_response(request_frame.sequence")
    require(decode_at < handle_at < commit_at, "decode/dispatch/commit order drifted")
    require(source.count("handler.handle(&context, &request)?") == 1, "handler call is not exactly one")
    require("NavigationTarget::ExternalHttps(" in source, "navigation fixture does not use active tuple variant")
    require("NavigationTarget::ExternalHttps {" not in source, "stale struct-style navigation variant returned")
    checks.extend(["source:order", "source:exactly-one", "source:navigation-variant"])


def check_contract_and_browserd(checks: list[str]) -> None:
    contract = parse_json("contracts/agent-port-bridge.v1.json")
    require(contract.get("schema") == "trillionnium.desktop.agent-port-bridge.v1", "wrong contract schema")
    require(contract.get("input", {}).get("maximum_requests_per_connection") == 1, "request count drifted")
    require(contract.get("dispatch", {}).get("handler_invocations_per_connection") == "at_most_one", "handler count drifted")
    require(contract.get("response", {}).get("maximum_responses_per_connection") == 1, "response count drifted")
    require(contract.get("listener", {}).get("enabled") is False, "listener opened")
    ceiling = contract.get("effect_ceiling", {})
    require(ceiling.get("external_effect_authorized") is False, "effect authority opened")
    require(ceiling.get("browser_actor_connected") is False, "BrowserActor claim opened")
    require(ceiling.get("servo_called") is False, "Servo claim opened")
    require(contract.get("validation", {}).get("merge_ready") is False, "candidate prematurely merge-ready")
    browserd_manifest = parse_toml("apps/hepta-browserd/Cargo.toml")
    require(browserd_manifest.get("dependencies", {}).get("hepta-agent-port", {}).get("path") == "../../crates/hepta-agent-port", "browserd AgentPort dependency missing")
    browserd = read("apps/hepta-browserd/src/lib.rs")
    require("hepta_agent_port::self_check()" in browserd, "browserd self-check omits AgentPort")
    require('IMPLEMENTATION_STAGE: &str = "D0R_D0C04_SOURCE"' in browserd, "browserd stage drifted")
    checks.extend(["contract:counts", "contract:ceiling", "browserd:dependency", "browserd:self-check"])


def validate() -> dict:
    checks: list[str] = []
    check_paths(checks)
    check_workspace(checks)
    check_lock(checks)
    check_manifest(checks)
    check_source(checks)
    check_contract_and_browserd(checks)
    return {
        "schema": "trillionnium.desktop.d0c04-rust-source-audit.v1",
        "status": "PASS_SOURCE_STATIC_ONLY",
        "checks_passed": len(checks),
        "checks": checks,
        "source_sha256": {
            "agent_port": sha256("crates/hepta-agent-port/src/lib.rs"),
            "contract": sha256("contracts/agent-port-bridge.v1.json"),
            "cargo_lock": sha256("Cargo.lock"),
        },
        "cargo_fmt": "UNEXECUTED",
        "cargo_clippy": "UNEXECUTED",
        "cargo_test": "UNEXECUTED",
        "browserd_self_check": "UNEXECUTED",
        "merge_ready": False,
        "listener_created": False,
        "browser_actor_called": False,
        "servo_called": False,
        "external_effect_authorized": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write", type=Path)
    args = parser.parse_args()
    try:
        result = validate()
    except (ValidationError, OSError, ValueError, tomllib.TOMLDecodeError, json.JSONDecodeError) as error:
        print(f"D0C-04 validation failed: {error}", file=sys.stderr)
        return 1
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.write is not None:
        output = args.write if args.write.is_absolute() else ROOT / args.write
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
