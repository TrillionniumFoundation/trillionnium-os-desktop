#!/usr/bin/env python3
"""Fail-closed static validation for the D0C-04 Rust product candidate."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
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
    "docs/architecture/CONNECTED_AGENT_PORT_BRIDGE.md",
    "docs/evidence/2026-08-28-d0c04-rust-agent-port.md",
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


def check_required_paths(checks: list[str]) -> None:
    for path in REQUIRED_PATHS:
        require((ROOT / path).is_file(), f"required D0C-04 path is missing: {path}")
        require(not (ROOT / path).is_symlink(), f"required path must not be a symlink: {path}")
        checks.append(f"path:{path}")


def check_workspace(checks: list[str]) -> None:
    cargo = parse_toml("Cargo.toml")
    workspace = cargo.get("workspace", {})
    require(workspace.get("members") == EXPECTED_MEMBERS, "workspace members drifted")
    require(workspace.get("default-members") == EXPECTED_MEMBERS, "default members drifted")
    require(workspace.get("resolver") == "3", "Cargo resolver must remain 3")
    package = workspace.get("package", {})
    require(package.get("edition") == "2024", "workspace edition drifted")
    require(package.get("rust-version") == "1.93", "workspace Rust version drifted")
    checks.extend(["workspace:members", "workspace:default-members", "workspace:toolchain"])


def lock_packages() -> list[dict]:
    packages = parse_toml("Cargo.lock").get("package")
    require(isinstance(packages, list), "Cargo.lock package list is missing")
    return packages


def check_lock_and_allowlist(checks: list[str]) -> None:
    packages = lock_packages()
    names = {package.get("name") for package in packages if "source" not in package}
    require(names == LOCAL_PACKAGES, f"local Cargo package set drifted: {sorted(names)}")

    allowlist = parse_json("manifests/cargo-external-allowlist.json")
    allowed = {
        (package["name"], package["version"], package["checksum"])
        for package in allowlist.get("packages", [])
    }
    actual = set()
    for package in packages:
        source = package.get("source")
        if source is None:
            continue
        require(source == "registry+https://github.com/rust-lang/crates.io-index", "non-crates.io source")
        require("checksum" in package, f"registry package lacks checksum: {package.get('name')}")
        actual.add((package["name"], package["version"], package["checksum"]))
    require(actual == allowed, "Cargo registry closure does not exactly match the allowlist")

    direct = allowlist.get("direct_dependencies", {})
    expected_direct = {
        "crates/hepta-agent-transport": {"libc": "=0.2.186", "sha2": "=0.10.9"},
        "crates/hepta-browser-codec": {"sha2": "=0.10.9"},
        "crates/hepta-agent-port": {"sha2": "=0.10.9"},
    }
    require(direct == expected_direct, "direct dependency allowlist drifted")
    for crate, expected in expected_direct.items():
        dependencies = parse_toml(f"{crate}/Cargo.toml").get("dependencies", {})
        for name, version in expected.items():
            require(dependencies.get(name) == version, f"{crate} dependency {name} is not exact")
    checks.extend(["lock:local-packages", "lock:registry-closure", "lock:direct-dependencies"])


def check_agent_port_manifest(checks: list[str]) -> None:
    manifest = parse_toml("crates/hepta-agent-port/Cargo.toml")
    require(manifest.get("package", {}).get("name") == "hepta-agent-port", "wrong package name")
    dependencies = manifest.get("dependencies", {})
    require(
        dependencies.get("hepta-agent-transport", {}).get("path") == "../hepta-agent-transport",
        "AgentPort must use local transport",
    )
    require(
        dependencies.get("hepta-browser-codec", {}).get("path") == "../hepta-browser-codec",
        "AgentPort must use local codec",
    )
    require(dependencies.get("sha2") == "=0.10.9", "AgentPort sha2 pin drifted")
    require(set(dependencies) == {"hepta-agent-transport", "hepta-browser-codec", "sha2"}, "unexpected AgentPort dependency")
    checks.append("agent-port:manifest")


def require_tokens(source: str, tokens: list[str], prefix: str, checks: list[str]) -> None:
    for token in tokens:
        require(token in source, f"missing {prefix} source invariant: {token}")
        checks.append(f"{prefix}:{token}")


def check_agent_port_source(checks: list[str]) -> None:
    source = read("crates/hepta-agent-port/src/lib.rs")
    require_tokens(
        source,
        [
            "#![forbid(unsafe_code)]",
            "pub fn serve_one<",
            "pub fn serve_one_with_nonce_source<",
            "ServerConnection::accept_with_nonce_source",
            "connection.receive_request",
            "decode_request(&request_frame.payload)",
            "request_effective_deadline",
            "let outcome = handler.handle(&context, &decoded)?;",
            "let response = bind_response(&decoded.value, outcome)?;",
            "connection.send_response(request_frame.sequence",
            "context.remaining()?;",
            "MAX_HANDLER_JSON_DEPTH",
            "MAX_HANDLER_CONTAINER_ITEMS",
            "EffectClass::PotentialExternalEffect",
            "BrowserErrorCode::PolicyDenied",
            "browser_runtime_available",
            "pub fn self_check()",
        ],
        "source",
        checks,
    )
    forbidden = [
        "UnixListener",
        "TcpListener",
        "servo::",
        "webdriver",
        "WebDriver",
        "std::process::Command",
        "tokio::net",
        "unsafe {",
        "todo!",
        "unimplemented!",
    ]
    for token in forbidden:
        require(token not in source, f"forbidden AgentPort authority/source token: {token}")
        checks.append(f"forbidden-absent:{token}")

    handle_position = source.index("let outcome = handler.handle(&context, &decoded)?;")
    decode_position = source.index("decode_request(&request_frame.payload)")
    response_position = source.index("connection.send_response(request_frame.sequence")
    require(decode_position < handle_position < response_position, "decode/dispatch/commit order drifted")
    require(source.count("handler.handle(&context, &decoded)?") == 1, "handler invocation is not exactly one")
    checks.extend(["source:dispatch-order", "source:exactly-one-handler"])


def check_contract(checks: list[str]) -> None:
    contract = parse_json("contracts/agent-port-bridge.v1.json")
    require(contract.get("schema") == "trillionnium.desktop.agent-port-bridge.v1", "wrong bridge schema")
    require(contract.get("input", {}).get("maximum_requests_per_connection") == 1, "request count drifted")
    require(contract.get("dispatch", {}).get("handler_invocations_per_connection") == "at_most_one", "dispatch count drifted")
    require(contract.get("response", {}).get("maximum_responses_per_connection") == 1, "response count drifted")
    require(contract.get("listener", {}).get("enabled") is False, "listener was enabled")
    require(contract.get("effect_ceiling", {}).get("external_effect_authorized") is False, "effect authority opened")
    require(contract.get("effect_ceiling", {}).get("browser_actor_connected") is False, "BrowserActor claim opened")
    require(contract.get("effect_ceiling", {}).get("servo_called") is False, "Servo claim opened")
    require(contract.get("validation", {}).get("merge_ready") is False, "candidate must remain unready")
    checks.extend(["contract:dispatch", "contract:listener", "contract:effect-ceiling", "contract:claim-ceiling"])


def check_browserd_integration(checks: list[str]) -> None:
    manifest = parse_toml("apps/hepta-browserd/Cargo.toml")
    dependencies = manifest.get("dependencies", {})
    require(
        dependencies.get("hepta-agent-port", {}).get("path") == "../../crates/hepta-agent-port",
        "browserd is not linked to AgentPort",
    )
    source = read("apps/hepta-browserd/src/lib.rs")
    require("hepta_agent_port::self_check()" in source, "browserd self-check omits AgentPort")
    require('IMPLEMENTATION_STAGE: &str = "D0R_D0C04_SOURCE"' in source, "browserd stage drifted")
    require("start Servo" not in source.lower(), "browserd claim ceiling drifted")
    checks.extend(["browserd:manifest", "browserd:self-check", "browserd:stage"])


def validate() -> dict:
    checks: list[str] = []
    check_required_paths(checks)
    check_workspace(checks)
    check_lock_and_allowlist(checks)
    check_agent_port_manifest(checks)
    check_agent_port_source(checks)
    check_contract(checks)
    check_browserd_integration(checks)
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
