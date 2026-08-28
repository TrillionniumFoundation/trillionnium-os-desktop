#!/usr/bin/env python3
"""Fail-closed static audit for D0C-05 AgentPort socket custody."""

from __future__ import annotations

import json
import pathlib
import re
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
ATTESTOR = ROOT / "crates/hepta-peer-attestation/src/lib.rs"
MARKER = "/etc/hepta/enable-agent-port"
SOCKET_PATH = "/run/hepta/browserd/agent.sock"


def fail(message: str) -> None:
    raise AssertionError(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


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
    return {section: dict(values) for section, values in result.items()}


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
    require(one(unit, "Socket", "Backlog") == "8", "backlog is not bounded to 8")
    require(one(unit, "Socket", "MaxConnections") == "8", "connections are not bounded to 8")
    require(yes(one(unit, "Socket", "RemoveOnStop")), "socket must be removed on stop")
    forbidden = {
        "ListenDatagram",
        "ListenSequentialPacket",
        "ListenNetlink",
        "ListenMessageQueue",
        "ListenFIFO",
        "ListenSpecial",
        "ListenUSBFunction",
    }
    present = forbidden.intersection(unit.get("Socket", {}))
    require(not present, f"forbidden listener directives present: {sorted(present)}")
    listen = one(unit, "Socket", "ListenStream")
    require(not listen.startswith("@"), "abstract AF_UNIX socket is forbidden")
    require(":" not in listen, "TCP/host:port listener is forbidden")
    require(one(unit, "Install", "WantedBy") == "sockets.target", "unexpected install target")


def audit_service() -> None:
    unit = parse_unit(SERVICE)
    require(one(unit, "Service", "Type") == "exec", "service must use Type=exec")
    require(one(unit, "Service", "User") == "hepta-browserd", "wrong service user")
    require(one(unit, "Service", "Group") == "hepta-browserd", "wrong service group")
    require(
        one(unit, "Service", "SupplementaryGroups") == "hepta-agent",
        "service must retain only the Agent socket group",
    )
    require(one(unit, "Service", "ExecStart") == "/usr/libexec/hepta-agent-portd", "wrong binary")
    require(one(unit, "Service", "StandardInput") == "socket", "accepted stream is not stdin")
    require(one(unit, "Service", "Restart") == "no", "per-connection service must not restart")
    require(one(unit, "Service", "RuntimeMaxSec") in {"25", "25s"}, "runtime ceiling changed")
    require(yes(one(unit, "Service", "NoNewPrivileges")), "NoNewPrivileges is required")
    require(one(unit, "Service", "CapabilityBoundingSet") == "", "capability bounding set is not empty")
    require(one(unit, "Service", "AmbientCapabilities") == "", "ambient capabilities are not empty")
    require(yes(one(unit, "Service", "PrivateNetwork")), "PrivateNetwork is required")
    require(one(unit, "Service", "RestrictAddressFamilies") == "AF_UNIX", "only AF_UNIX is allowed")
    require(one(unit, "Service", "ProtectSystem") == "strict", "ProtectSystem=strict is required")
    require(yes(one(unit, "Service", "ProtectHome")), "ProtectHome is required")
    require(one(unit, "Service", "ProtectProc") == "default", "procfs attestation must remain visible")
    require(one(unit, "Service", "ProcSubset") == "all", "procfs attestation requires full proc subset")
    require(yes(one(unit, "Service", "RestrictNamespaces")), "namespace creation must be blocked")
    require(yes(one(unit, "Service", "LockPersonality")), "personality changes must be blocked")
    require(yes(one(unit, "Service", "MemoryDenyWriteExecute")), "W^X hardening is required")
    positive = " ".join(unit.get("Service", {}).get("SystemCallFilter", [])[:-1])
    negative = unit.get("Service", {}).get("SystemCallFilter", [])[-1:]
    require("@system-service" in positive and "pidfd_open" in positive, "syscall allow set misses pidfd_open")
    require(negative and negative[0].startswith("~"), "syscall deny set is missing")


def audit_packaging() -> None:
    preset_lines = [line.strip() for line in read(PRESET).splitlines() if line.strip() and not line.startswith("#")]
    require(preset_lines == ["disable hepta-browserd-agent.socket"], "socket preset is not exactly disabled")

    sysusers = read(SYSUSERS)
    for token in ("g      hepta-agent", "u      hepta-agent", "u      hepta-browserd", "m      hepta-browserd   hepta-agent"):
        require(token in sysusers, f"sysusers mapping missing {token!r}")

    tmpfiles = read(TMPFILES)
    require(MARKER not in tmpfiles, "tmpfiles must not create the enable marker")
    require("/run/hepta/browserd" in tmpfiles and "0750" in tmpfiles, "runtime directory mapping is missing")

    install = read(INSTALL)
    required_sources = {
        "target/release/hepta-agent-portd",
        "packaging/debian/systemd/hepta-browserd-agent.socket",
        "packaging/debian/systemd/hepta-browserd-agent@.service",
        "packaging/debian/sysusers.d/trillionnium-desktop.conf",
        "packaging/debian/tmpfiles.d/trillionnium-desktop.conf",
        "packaging/debian/systemd-preset/90-trillionnium-desktop.preset",
    }
    installed = {line.split()[0] for line in install.splitlines() if line.strip() and not line.startswith("#")}
    require(required_sources <= installed, f"install map misses {sorted(required_sources - installed)}")
    require(MARKER not in install and "enable-agent-port" not in install, "package ships an enable marker")

    for path in ROOT.rglob("*"):
        if path.name == "enable-agent-port":
            fail(f"repository contains forbidden activation marker: {path.relative_to(ROOT)}")


def audit_source() -> None:
    portd = read(PORTD)
    attestor = read(ATTESTOR)
    for forbidden in ("UnixListener", "TcpListener", "TcpStream", "SocketAddr", ".bind(", "listen("):
        require(forbidden not in portd, f"connection service contains listener/network primitive {forbidden!r}")
    for required in (
        "F_DUPFD_CLOEXEC",
        "UnixStream::from_raw_fd",
        "local_addr",
        "ProcfsPeerAttestor",
        "PeerRuntimePolicy::for_system_service",
        "serve_one",
        "D0FixtureHandler",
    ):
        require(required in portd, f"connection service misses {required!r}")
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
    require(contract["activation"]["marker_shipped"] is False, "contract claims marker is shipped")
    require(contract["activation"]["enabled_by_default"] is False, "contract enables listener")
    require(contract["activation"]["tcp_listener"] is False, "contract enables TCP")
    require(contract["service"]["bind_or_listen_authority"] is False, "service has bind authority")
    require(contract["service"]["requests_per_process"] == 1, "service is not one-request")
    require(contract["dispatch"]["browser_actor"] is False, "contract claims BrowserActor")
    require(contract["dispatch"]["servo_runtime"] is False, "contract claims Servo")
    require(contract["dispatch"]["external_effect_authority"] is False, "contract grants effects")

    workspace = tomllib.loads(read(ROOT / "Cargo.toml"))
    members = set(workspace["workspace"]["members"])
    required_members = {"apps/hepta-agent-portd", "crates/hepta-peer-attestation"}
    require(required_members <= members, f"workspace misses {sorted(required_members - members)}")

    lock = tomllib.loads(read(ROOT / "Cargo.lock"))
    packages = {package["name"]: package for package in lock["package"]}
    require("hepta-agent-portd" in packages, "lock misses hepta-agent-portd")
    require("hepta-peer-attestation" in packages, "lock misses hepta-peer-attestation")
    registry = {
        (package["name"], package["version"], package.get("checksum"))
        for package in lock["package"]
        if "source" in package
    }
    for name, version, checksum in registry:
        require(checksum, f"registry package {name} {version} has no checksum")
        require(
            packages[name]["source"] == "registry+https://github.com/rust-lang/crates.io-index",
            f"unexpected registry source for {name}",
        )


def main() -> int:
    audit_socket()
    audit_service()
    audit_packaging()
    audit_source()
    audit_contract_and_workspace()
    print("D0C-05 AgentPort custody audit: PASS")
    print("listener enabled by default: false")
    print("enable marker shipped: false")
    print("TCP/WebDriver listener: false")
    print("BrowserActor/Servo/effect authority: false")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, KeyError, TypeError, ValueError, tomllib.TOMLDecodeError) as error:
        print(f"D0C-05 AgentPort custody audit: FAIL: {error}", file=sys.stderr)
        raise SystemExit(1)
