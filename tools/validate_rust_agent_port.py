#!/usr/bin/env python3
"""Fail-closed source/contract audit for the D0C-04 Rust AgentPort candidate."""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CHECKS: list[str] = []


def check(condition: bool, label: str) -> None:
    if not condition:
        raise AssertionError(label)
    CHECKS.append(label)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def load_json(path: str) -> Any:
    return json.loads(read(path))


def load_toml(path: str) -> Any:
    return tomllib.loads(read(path))


def package_map(lock: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {package["name"]: package for package in lock.get("package", [])}


def main() -> int:
    required_paths = [
        "Cargo.toml",
        "Cargo.lock",
        "apps/hepta-browserd/Cargo.toml",
        "apps/hepta-browserd/src/lib.rs",
        "crates/hepta-agent-port/Cargo.toml",
        "crates/hepta-agent-port/README.md",
        "crates/hepta-agent-port/src/lib.rs",
        "crates/hepta-agent-transport/src/lib.rs",
        "crates/hepta-browser-codec/src/lib.rs",
        "contracts/agent-port-rust.v1.json",
        "contracts/agent-port-bridge.v1.json",
        "contracts/agent-transport.v1.json",
        "contracts/browser-codec.v1.json",
        "docs/architecture/RUST_AGENT_PORT.md",
        "docs/evidence/2026-08-28-d0c04-rust-agent-port-source.md",
        "docs/evidence/generated/d0c04-rust-static-validation.json",
    ]
    for path in required_paths:
        check((ROOT / path).is_file(), f"required path exists: {path}")

    workspace = load_toml("Cargo.toml")["workspace"]
    expected_members = [
        "apps/hepta-browserd",
        "crates/hepta-agent-port",
        "crates/hepta-agent-transport",
        "crates/hepta-browser-codec",
        "crates/trillionnium-contract-core",
        "crates/hepta-browser-contracts",
        "crates/hepta-session-core",
    ]
    check(workspace["members"] == expected_members, "workspace members are exact and ordered")
    check(
        workspace["default-members"] == expected_members,
        "workspace default members are exact and ordered",
    )
    check(workspace["resolver"] == "3", "workspace resolver remains 3")

    manifest = load_toml("crates/hepta-agent-port/Cargo.toml")
    check(manifest["package"]["name"] == "hepta-agent-port", "AgentPort package name")
    check(manifest["package"]["publish"] is False, "AgentPort is not published")
    expected_deps = {
        "hepta-agent-transport": {"path": "../hepta-agent-transport"},
        "hepta-browser-codec": {"path": "../hepta-browser-codec"},
        "sha2": "=0.10.9",
    }
    check(manifest["dependencies"] == expected_deps, "AgentPort direct dependencies are exact")

    browserd_manifest = load_toml("apps/hepta-browserd/Cargo.toml")
    browserd_deps = browserd_manifest["dependencies"]
    for dependency in [
        "hepta-agent-port",
        "hepta-agent-transport",
        "hepta-browser-codec",
        "hepta-browser-contracts",
        "hepta-session-core",
        "trillionnium-contract-core",
    ]:
        check(dependency in browserd_deps, f"browserd dependency present: {dependency}")
    check(
        browserd_deps["hepta-agent-port"]["path"] == "../../crates/hepta-agent-port",
        "browserd AgentPort path is exact",
    )

    lock = load_toml("Cargo.lock")
    packages = package_map(lock)
    expected_local = {
        "hepta-agent-port",
        "hepta-agent-transport",
        "hepta-browser-codec",
        "hepta-browser-contracts",
        "hepta-browserd",
        "hepta-session-core",
        "trillionnium-contract-core",
    }
    for name in expected_local:
        check(name in packages, f"lock contains local package: {name}")
        check("source" not in packages[name], f"local package has no registry source: {name}")
        check("checksum" not in packages[name], f"local package has no registry checksum: {name}")
    check(
        set(packages["hepta-agent-port"].get("dependencies", []))
        == {"hepta-agent-transport", "hepta-browser-codec", "sha2"},
        "AgentPort lock dependencies are exact",
    )
    check(
        "hepta-agent-port" in packages["hepta-browserd"].get("dependencies", []),
        "browserd lock depends on AgentPort",
    )
    for package in packages.values():
        source = package.get("source")
        check(
            source is None or source == "registry+https://github.com/rust-lang/crates.io-index",
            f"no Git/non-crates registry dependency: {package['name']}",
        )
        if source is not None:
            check(bool(package.get("checksum")), f"registry checksum present: {package['name']}")

    rust_contract = load_json("contracts/agent-port-rust.v1.json")
    bridge_contract = load_json("contracts/agent-port-bridge.v1.json")
    check(
        rust_contract["schema"] == "trillionnium.desktop.agent-port-rust.v1",
        "Rust contract schema",
    )
    check(rust_contract["stage"] == "TOS-D0C-04", "Rust contract stage")
    check(rust_contract["request_count_per_connection"] == 1, "one request per connection")
    check(rust_contract["handler_invocation_limit"] == 1, "one handler invocation")
    check(rust_contract["dependencies"]["new_registry_packages"] == [], "no new registry packages")
    for key in [
        "listener",
        "browser_actor",
        "servo",
        "capability_grant",
        "external_effect_authorized",
        "automatic_retry",
    ]:
        check(rust_contract["authority"][key] is False, f"Rust authority remains false: {key}")
    check(bridge_contract["listener_created"] is False, "bridge listener remains false")
    check(
        bridge_contract["dispatch"]["maximum_handler_invocations"] == 1,
        "bridge maximum handler invocations",
    )
    check(
        bridge_contract["effect_policy"]["authority_granted"] is False,
        "bridge effect authority remains false",
    )
    for key in [
        "listener_created",
        "browser_actor_called",
        "servo_called",
        "external_effect_authorized",
    ]:
        check(bridge_contract["rust_product"][key] is False, f"Rust product ceiling: {key}")

    source = read("crates/hepta-agent-port/src/lib.rs")
    required_tokens = [
        "pub struct DispatchContext",
        "pub transport_sequence: u64",
        "pub canonical_request_sha256: String",
        "pub effect_class: EffectClass",
        "pub accepted_at: Instant",
        "pub effective_deadline: Instant",
        "pub trait BrowserRequestHandler",
        "pub enum HandlerReply",
        "pub fn serve_connected_once",
        "ServerConnection::accept",
        ".receive_request(",
        "decode_request(&received.payload)",
        "request.effect_class()",
        "handler.handle(&request, &context)",
        "validate_handler_reply(&reply)",
        "BrowserResponse::success",
        "BrowserResponse::failure",
        "encode_response(&response)",
        "sha256_hex(&encoded_response)",
        ".send_response(",
        "minimum_of_server_ceiling_and_request_deadline_converted_once_at_acceptance",
        "LateResultDiscarded",
        "MAX_HANDLER_OBJECT_MEMBERS",
        "MAX_HANDLER_AGGREGATE_ITEMS",
        "MAX_HANDLER_VALUE_DEPTH",
        "MAX_HANDLER_KEY_BYTES",
        "MAX_HANDLER_STRING_BYTES",
        "BrowserErrorCode::PolicyDenied",
        "BrowserErrorCode::Unsupported",
        "browser_runtime_available",
        "external-effect authority is closed in D0",
        "BrowserActor and Servo runtime are not implemented",
        "UnixStream::pair()",
        "duplicate_member_fails_before_handler_invocation",
        "late_handler_result_is_discarded_without_response_commit",
        "oversized_handler_output_is_rejected_without_response_commit",
        "navigation_is_propagated_as_potential_effect_and_denied",
    ]
    for token in required_tokens:
        check(token in source, f"AgentPort source invariant: {token}")

    forbidden_tokens = [
        "UnixListener",
        "TcpListener",
        "TcpStream",
        "bind(",
        "listen(",
        "WebDriver",
        "webdriver",
        "servo::",
        "WebView",
        "BrowserActor",
        "capability_grant(",
        "authorize_external_effect",
        "automatic_retry",
        "tokio::net",
        "std::net::Tcp",
        "unsafe {",
    ]
    for token in forbidden_tokens:
        check(token not in source, f"forbidden AgentPort authority absent: {token}")

    for token in [
        "#![forbid(unsafe_code)]",
        "one request",
        "does not create a listener",
        "does not",
    ]:
        check(token in source, f"source claim boundary: {token}")

    browserd = read("apps/hepta-browserd/src/lib.rs")
    for token in [
        'IMPLEMENTATION_STAGE: &str = "D0R_D0C04_SOURCE"',
        "hepta_agent_transport::self_check()",
        "hepta_browser_codec::self_check()",
        "hepta_agent_port::self_check()",
        "does not bind a",
        "dispatch a BrowserActor",
        "start Servo",
    ]:
        check(token in browserd, f"browserd D0C-04 integration: {token}")

    evidence = load_json("docs/evidence/generated/d0c04-rust-static-validation.json")
    check(evidence["status"] == "PASS_SOURCE_STATIC_ONLY", "static evidence status")
    check(evidence["rust_execution"] == "UNEXECUTED", "Rust execution remains unclaimed")
    for key in [
        "listener_created",
        "browser_actor_created",
        "servo_called",
        "external_effect_authorized",
    ]:
        check(evidence[key] is False, f"evidence claim ceiling: {key}")

    result = {
        "schema": "trillionnium.desktop.d0c04-rust-static-validation.v1",
        "status": "PASS_SOURCE_STATIC_ONLY",
        "checks": len(CHECKS),
        "rust_execution": "UNEXECUTED",
        "listener_created": False,
        "browser_actor_created": False,
        "servo_called": False,
        "external_effect_authorized": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, KeyError, OSError, ValueError, tomllib.TOMLDecodeError) as error:
        print(f"D0C-04 Rust AgentPort validation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
