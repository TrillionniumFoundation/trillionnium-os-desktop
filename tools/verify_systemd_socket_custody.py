#!/usr/bin/env python3
"""Fail-closed static audit for AgentPort custody and fixture separation."""

from __future__ import annotations

import json
import pathlib
import sys
import tomllib
from collections import defaultdict

ROOT = pathlib.Path(__file__).resolve().parents[1]
SOCKET = ROOT / "packaging/debian/systemd/hepta-browserd-agent.socket"
SERVICE = ROOT / "packaging/debian/systemd/hepta-browserd-agent@.service"
SYSUSERS = ROOT / "packaging/debian/sysusers.d/trillionnium-desktop.conf"
TMPFILES = ROOT / "packaging/debian/tmpfiles.d/trillionnium-desktop.conf"
PRESET = ROOT / "packaging/debian/systemd-preset/90-trillionnium-desktop.preset"
INSTALL = ROOT / "packaging/debian/hepta-agent-portd.install"
CONTRACT = ROOT / "contracts/agent-port-custody.v1.json"
PORTD = ROOT / "apps/hepta-agent-portd/src/main.rs"
FIXTURE = ROOT / "apps/hepta-agent-portd/src/bin/hepta-agent-port-fixture.rs"
PORTD_CARGO = ROOT / "apps/hepta-agent-portd/Cargo.toml"
ATTESTOR = ROOT / "crates/hepta-peer-attestation/src/lib.rs"
MARKER = "/etc/hepta/enable-agent-port"
SOCKET_PATH = "/run/hepta/browserd/agent.sock"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read(path: pathlib.Path) -> str:
    require(path.is_file(), f"required file missing: {path.relative_to(ROOT)}")
    require(not path.is_symlink(), f"required file is a symlink: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


def parse_unit(path: pathlib.Path) -> dict[str, dict[str, list[str]]]:
    result: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    section: str | None = None
    for line_number, raw in enumerate(read(path).splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            require(section != "", f"empty section in {path}:{line_number}")
            continue
        require(section is not None, f"directive outside section in {path}:{line_number}")
        require("=" in line, f"malformed directive in {path}:{line_number}")
        key, value = line.split("=", 1)
        require(key != "", f"empty directive in {path}:{line_number}")
        result[section][key].append(value)
    return {name: dict(values) for name, values in result.items()}


def one(unit: dict[str, dict[str, list[str]]], section: str, key: str) -> str:
    values = unit.get(section, {}).get(key, [])
    require(len(values) == 1, f"expected exactly one {section}.{key}, got {values!r}")
    return values[0]


def yes(value: str) -> bool:
    return value.lower() in {"yes", "true", "1", "on"}


def audit_socket() -> None:
    unit = parse_unit(SOCKET)
    require(one(unit, "Unit", "ConditionPathExists") == MARKER, "wrong activation marker")
    require(one(unit, "Socket", "ListenStream") == SOCKET_PATH, "wrong socket path")
    require(one(unit, "Socket", "SocketUser") == "hepta-browserd", "wrong socket user")
    require(one(unit, "Socket", "SocketGroup") == "hepta-agent", "wrong socket group")
    require(one(unit, "Socket", "SocketMode") == "0660", "wrong socket mode")
    require(one(unit, "Socket", "DirectoryMode") == "0750", "wrong directory mode")
    require(yes(one(unit, "Socket", "Accept")), "socket must use Accept=yes")
    require(one(unit, "Socket", "Backlog") == "8", "backlog is not bounded")
    require(one(unit, "Socket", "MaxConnections") == "8", "connection count is not bounded")
    require(yes(one(unit, "Socket", "RemoveOnStop")), "socket must be removed on stop")
    listen = one(unit, "Socket", "ListenStream")
    require(not listen.startswith("@"), "abstract socket is forbidden")
    require(":" not in listen, "TCP host:port listener is forbidden")
    require(one(unit, "Install", "WantedBy") == "sockets.target", "unexpected install target")


def audit_service() -> None:
    unit = parse_unit(SERVICE)
    require(one(unit, "Service", "Type") == "exec", "service must use Type=exec")
    require(one(unit, "Service", "User") == "hepta-browserd", "wrong service user")
    require(one(unit, "Service", "Group") == "hepta-browserd", "wrong service group")
    require(one(unit, "Service", "SupplementaryGroups") == "hepta-agent", "wrong socket group")
    require(one(unit, "Service", "ExecStart") == "/usr/libexec/hepta-agent-portd", "wrong product binary")
    require(one(unit, "Service", "StandardInput") == "socket", "accepted stream is not stdin")
    require(one(unit, "Service", "Restart") == "no", "per-connection service must not restart")
    require(one(unit, "Service", "RuntimeMaxSec") in {"25", "25s"}, "runtime ceiling changed")
    require(yes(one(unit, "Service", "NoNewPrivileges")), "NoNewPrivileges is required")
    require(one(unit, "Service", "CapabilityBoundingSet") == "", "capability set is not empty")
    require(one(unit, "Service", "AmbientCapabilities") == "", "ambient capabilities are not empty")
    require(yes(one(unit, "Service", "PrivateNetwork")), "PrivateNetwork is required")
    require(one(unit, "Service", "RestrictAddressFamilies") == "AF_UNIX", "only AF_UNIX is allowed")
    require(one(unit, "Service", "ProtectSystem") == "strict", "ProtectSystem=strict is required")
    require(yes(one(unit, "Service", "ProtectHome")), "ProtectHome is required")
    require(one(unit, "Service", "ProtectProc") == "default", "procfs attestation must remain visible")
    require(one(unit, "Service", "ProcSubset") == "all", "full proc subset is required")
    require(yes(one(unit, "Service", "RestrictNamespaces")), "namespace creation must be blocked")
    require(yes(one(unit, "Service", "LockPersonality")), "personality changes must be blocked")
    require(yes(one(unit, "Service", "MemoryDenyWriteExecute")), "W^X hardening is required")
    filters = unit.get("Service", {}).get("SystemCallFilter", [])
    require(filters and "@system-service" in filters[0] and "pidfd_open" in filters[0], "pidfd allow set missing")
    require(len(filters) >= 2 and filters[-1].startswith("~"), "syscall deny set missing")


def audit_packaging() -> None:
    preset_lines = [
        line.strip()
        for line in read(PRESET).splitlines()
        if line.strip() and not line.startswith("#")
    ]
    require(preset_lines == ["disable hepta-browserd-agent.socket"], "socket preset is not exactly disabled")

    sysusers = read(SYSUSERS)
    for token in (
        "g      hepta-agent",
        "u      hepta-agent",
        "u      hepta-browserd",
        "m      hepta-browserd   hepta-agent",
    ):
        require(token in sysusers, f"sysusers mapping missing {token!r}")

    tmpfiles = read(TMPFILES)
    require(MARKER not in tmpfiles, "tmpfiles must not create the enable marker")
    require("/run/hepta/browserd" in tmpfiles and "0750" in tmpfiles, "runtime directory mapping missing")

    install = read(INSTALL)
    installed = {
        line.split()[0]
        for line in install.splitlines()
        if line.strip() and not line.startswith("#")
    }
    required_sources = {
        "target/release/hepta-agent-portd",
        "packaging/debian/systemd/hepta-browserd-agent.socket",
        "packaging/debian/systemd/hepta-browserd-agent@.service",
        "packaging/debian/sysusers.d/trillionnium-desktop.conf",
        "packaging/debian/tmpfiles.d/trillionnium-desktop.conf",
        "packaging/debian/systemd-preset/90-trillionnium-desktop.preset",
    }
    require(required_sources <= installed, f"install map misses {sorted(required_sources - installed)}")
    require("hepta-agent-port-fixture" not in install, "production package installs fixture binary")
    require(MARKER not in install and "enable-agent-port" not in install, "package ships enable marker")

    for path in ROOT.rglob("*"):
        if path.name == "enable-agent-port":
            raise AssertionError(f"repository contains activation marker: {path.relative_to(ROOT)}")


def audit_source_and_features() -> None:
    portd = read(PORTD)
    fixture = read(FIXTURE)
    attestor = read(ATTESTOR)
    cargo = tomllib.loads(read(PORTD_CARGO))

    for forbidden in (
        "UnixListener",
        "TcpListener",
        "TcpStream",
        "SocketAddr",
        ".bind(",
        "listen(",
        "D0FixtureHandler",
        "hepta_agent_port::",
        "serve_one",
    ):
        require(forbidden not in portd, f"product daemon contains forbidden token {forbidden!r}")
    for required in (
        "F_DUPFD_CLOEXEC",
        "UnixStream::from_raw_fd",
        "local_addr",
        "ProcfsPeerAttestor",
        "PeerRuntimePolicy::for_system_service",
        "ProductHandlerUnavailable",
        "fixture substitution is forbidden",
        "fixture_handler_linked\\\":false",
    ):
        require(required in portd, f"product daemon misses {required!r}")

    for required in (
        "D0FixtureHandler",
        "hepta_agent_port::self_check",
        "fixture_profile\\\":true",
        "product_installable\\\":false",
        "external_effect_authority\\\":false",
    ):
        require(required in fixture, f"fixture binary misses {required!r}")
    for forbidden in ("UnixListener", "TcpListener", ".bind(", "listen("):
        require(forbidden not in fixture, f"fixture contains listener primitive {forbidden!r}")

    features = cargo.get("features", {})
    require(features.get("default") == [], "fixture feature is enabled by default")
    require(features.get("fixture") == ["dep:hepta-agent-port"], "fixture feature mapping changed")
    dependency = cargo.get("dependencies", {}).get("hepta-agent-port")
    require(isinstance(dependency, dict) and dependency.get("optional") is True, "fixture dependency is not optional")
    bins = {entry.get("name"): entry for entry in cargo.get("bin", [])}
    product = bins.get("hepta-agent-portd", {})
    fixture_bin = bins.get("hepta-agent-port-fixture", {})
    require(product.get("path") == "src/main.rs", "product bin path changed")
    require("required-features" not in product, "product binary unexpectedly feature-gated")
    require(fixture_bin.get("path") == "src/bin/hepta-agent-port-fixture.rs", "fixture bin path changed")
    require(fixture_bin.get("required-features") == ["fixture"], "fixture bin is not explicitly feature-gated")

    for required in (
        "SYS_pidfd_open",
        "PeerCredentialDrift",
        "parse_uniform_id_field",
        "parse_unified_cgroup_path",
        "ProcessIdentityChanged",
        "ensure_pidfd_alive",
    ):
        require(required in attestor, f"peer attestor misses {required!r}")


def audit_contract_and_workspace() -> None:
    contract = json.loads(read(CONTRACT))
    require(contract["socket"]["path"] == SOCKET_PATH, "contract socket path drift")
    require(contract["activation"]["preset"] == "disable", "contract preset drift")
    require(contract["activation"]["required_marker"] == MARKER, "contract marker drift")
    require(contract["activation"]["marker_shipped"] is False, "contract claims marker shipped")
    require(contract["activation"]["enabled_by_default"] is False, "contract enables listener")
    require(contract["activation"]["tcp_listener"] is False, "contract enables TCP")
    require(contract["service"]["bind_or_listen_authority"] is False, "service has bind authority")
    require(contract["service"]["requests_per_process"] == 1, "service is not one request")
    dispatch = contract["dispatch"]
    require(dispatch["browser_actor"] is False, "contract claims BrowserActor")
    require(dispatch["servo_runtime"] is False, "contract claims Servo")
    require(dispatch["external_effect_authority"] is False, "contract grants effects")
    require(dispatch["fixture_substitution"] is False, "contract allows fixture substitution")
    require(
        dispatch["activation_without_browser_actor"] == "fail_closed_before_request_decode",
        "product missing-handler behavior changed",
    )
    separation = contract["fixture_separation"]
    require(separation["cargo_feature"] == "fixture", "fixture feature drift")
    require(separation["feature_enabled_by_default"] is False, "fixture defaults on")
    require(separation["production_binary_references_fixture_handler"] is False, "product references fixture")
    require(separation["debian_package_installs_fixture_binary"] is False, "package installs fixture")
    require(separation["external_effect_authority"] is False, "fixture grants effects")

    workspace = tomllib.loads(read(ROOT / "Cargo.toml"))
    members = set(workspace["workspace"]["members"])
    require(
        {"apps/hepta-agent-portd", "crates/hepta-peer-attestation"} <= members,
        "workspace misses AgentPort custody members",
    )
    lock = tomllib.loads(read(ROOT / "Cargo.lock"))
    packages = {package["name"]: package for package in lock["package"]}
    require("hepta-agent-portd" in packages, "lock misses hepta-agent-portd")
    require("hepta-peer-attestation" in packages, "lock misses hepta-peer-attestation")
    for package in lock["package"]:
        if "source" in package:
            require(package.get("checksum"), f"registry package {package['name']} has no checksum")
            require(
                package["source"] == "registry+https://github.com/rust-lang/crates.io-index",
                f"unexpected registry source for {package['name']}",
            )


def main() -> int:
    audit_socket()
    audit_service()
    audit_packaging()
    audit_source_and_features()
    audit_contract_and_workspace()
    print("AgentPort custody and fixture separation audit: PASS")
    print("listener enabled by default: false")
    print("enable marker shipped: false")
    print("product fixture substitution: false")
    print("activation without BrowserActor: fail closed")
    print("fixture Debian installation: false")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, KeyError, TypeError, ValueError, tomllib.TOMLDecodeError) as error:
        print(f"AgentPort custody and fixture separation audit: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
