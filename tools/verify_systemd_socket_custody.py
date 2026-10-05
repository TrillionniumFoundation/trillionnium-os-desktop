#!/usr/bin/env python3
"""Fail-closed static audit for AgentPort custody and fixture separation."""

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
SOCKET_CUSTODY = ROOT / "packaging/debian/systemd/hepta-browserd-agent.socket.d/10-root-path-custody.conf"
SERVICE_CUSTODY = ROOT / "packaging/debian/systemd/hepta-browserd-agent@.service.d/10-root-path-custody.conf"
SYSUSERS = ROOT / "packaging/debian/sysusers.d/trillionnium-desktop.conf"
TMPFILES = ROOT / "packaging/debian/tmpfiles.d/trillionnium-desktop.conf"
PRESET = ROOT / "packaging/debian/systemd-preset/90-trillionnium-desktop.preset"
INSTALL = ROOT / "packaging/debian/hepta-agent-portd.install"
CONTRACT = ROOT / "contracts/agent-port-custody.v1.json"
PORTD = ROOT / "apps/hepta-agent-portd/src/main.rs"
FIXTURE = ROOT / "apps/hepta-agent-portd/src/bin/hepta-agent-port-fixture.rs"
PORTD_CARGO = ROOT / "apps/hepta-agent-portd/Cargo.toml"
ATTESTOR = ROOT / "crates/hepta-peer-attestation/src/lib.rs"
ATTESTOR_CARGO = ROOT / "crates/hepta-peer-attestation/Cargo.toml"
MARKER = "/etc/hepta/enable-agent-port"
SOCKET_PATH = "/run/hepta/browserd/agent.sock"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def read(path: pathlib.Path) -> str:
    require(path.is_file(), f"required file missing: {path.relative_to(ROOT)}")
    require(not path.is_symlink(), f"required file is a symlink: {path.relative_to(ROOT)}")
    return path.read_text(encoding="utf-8")


_UNIT_KEYS = {
    "Unit": {"Description", "Documentation", "ConditionPathExists", "Requires", "After"},
    "Socket": {"ListenStream", "SocketUser", "SocketGroup", "SocketMode", "DirectoryMode",
               "Accept", "Backlog", "MaxConnections", "RemoveOnStop"},
    "Install": {"WantedBy"},
    "Service": {"Type", "User", "Group", "SupplementaryGroups", "ExecStart", "StandardInput",
                "StandardOutput", "StandardError", "Restart", "RuntimeMaxSec", "TimeoutStopSec",
                "UMask", "NoNewPrivileges", "CapabilityBoundingSet", "AmbientCapabilities",
                "PrivateNetwork", "PrivateTmp", "PrivateDevices", "ProtectSystem", "ProtectHome",
                "ProtectKernelTunables", "ProtectKernelModules", "ProtectKernelLogs",
                "ProtectControlGroups", "ProtectClock", "ProtectHostname", "ProtectProc", "ProcSubset",
                "RestrictAddressFamilies", "RestrictNamespaces", "RestrictRealtime", "RestrictSUIDSGID",
                "LockPersonality", "MemoryDenyWriteExecute", "RemoveIPC", "SystemCallArchitectures",
                "SystemCallFilter", "DevicePolicy", "ReadWritePaths", "ReadOnlyPaths"},
}
_LIST_KEYS = {"SupplementaryGroups", "ReadWritePaths", "ReadOnlyPaths", "SystemCallFilter"}


def parse_unit(path: pathlib.Path) -> dict[str, dict[str, list[str]]]:
    result: dict[str, dict[str, list[str]]] = defaultdict(lambda: defaultdict(list))
    section: str | None = None
    source = read(path)
    require(re.search(r"[^\x09\x0a\x0d\x20-\x7e]", source) is None, "unsupported unit syntax")
    for line_number, raw in enumerate(source.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            require(section in {"Unit", "Socket", "Service", "Install"}, "malformed unit section")
            continue
        require(section is not None, "directive outside section")
        require("=" in line, "malformed unit directive")
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip()
        require(
            key in _UNIT_KEYS[section]
            and re.fullmatch(r"[A-Za-z0-9_./:@~+ \t-]*", value) is not None,
            "unsupported unit syntax",
        )
        require(key in _LIST_KEYS or key not in result[section], "duplicate unit directive")
        result[section][key].append(value)
    return {name: dict(values) for name, values in result.items()}


def one(unit: dict[str, dict[str, list[str]]], section: str, key: str) -> str:
    values = unit.get(section, {}).get(key, [])
    require(len(values) == 1, f"expected exactly one {section}.{key}")
    return values[0]


def yes(value: str) -> bool:
    return value.lower() in {"yes", "true", "1", "on"}


def merge_custody_unit(base: pathlib.Path, dropin: pathlib.Path) -> dict[str, dict[str, list[str]]]:
    unit = parse_unit(base)
    override = parse_unit(dropin)
    section, keys = (
        ("Socket", {"SocketUser", "SocketGroup", "SocketMode", "DirectoryMode"})
        if base == SOCKET
        else ("Service", {"SupplementaryGroups", "ReadWritePaths", "ReadOnlyPaths"})
    )
    require(set(override) == {section} and set(override[section]) == keys,
            "custody drop-in directives changed")
    for key, values in override[section].items():
        require(len(values) == 1, "duplicate custody drop-in directive")
        if section == "Service":
            unit[section].setdefault(key, []).extend(values)
        else:
            unit[section][key] = values
    return unit


def list_value(unit: dict[str, dict[str, list[str]]], section: str, key: str) -> list[str]:
    result: list[str] = []
    for value in unit.get(section, {}).get(key, []):
        if value == "":
            result.clear()
        else:
            result.extend(value.split())
    return result


def sysusers_records(source: str) -> list[tuple[str, ...]]:
    require(re.search(r"[^\x09\x0a\x0d\x20-\x7e]", source) is None, "unsupported configuration syntax")
    records: list[tuple[str, ...]] = []
    for raw in source.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("u"):
            match = re.fullmatch(
                r'u[ \t]+([a-z][a-z0-9-]*)[ \t]+-[ \t]+"([A-Za-z0-9 ._-]+)"'
                r"[ \t]+(/[A-Za-z0-9_./-]+)[ \t]+(/[A-Za-z0-9_./-]+)",
                line,
            )
            require(match is not None, "malformed sysusers record")
            record = ("u", match[1], "-", match[2], match[3], match[4])
        else:
            fields = tuple(line.split())
            require(
                len(fields) == 3
                and fields[0] in {"g", "m"}
                and re.fullmatch(r"[a-z][a-z0-9-]*", fields[1]) is not None
                and (
                    fields[0] == "g" and fields[2] == "-"
                    or fields[0] == "m"
                    and re.fullmatch(r"[a-z][a-z0-9-]*", fields[2]) is not None
                ),
                "malformed sysusers record",
            )
            record = fields
        require(record not in records and not any(
            old[:2] == record[:2] for old in records if record[0] in {"g", "u"}
        ), "duplicate sysusers record")
        records.append(record)
    return records


def tmpfiles_records(source: str) -> list[tuple[str, ...]]:
    require(re.search(r"[^\x09\x0a\x0d\x20-\x7e]", source) is None, "unsupported configuration syntax")
    records: list[tuple[str, ...]] = []
    for raw in source.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = tuple(line.split())
        require(
            len(fields) == 7
            and fields[0] == "d"
            and re.fullmatch(r"/[A-Za-z0-9_./-]+", fields[1]) is not None
            and re.fullmatch(r"0[0-7]{3}", fields[2]) is not None
            and all(re.fullmatch(r"[a-z][a-z0-9-]*", field) is not None for field in fields[3:5])
            and fields[5:] == ("-", "-"),
            "malformed tmpfiles record",
        )
        require(not any(old[1] == fields[1] for old in records), "duplicate tmpfiles path")
        records.append(fields)
    return records


def audit_socket() -> None:
    unit = merge_custody_unit(SOCKET, SOCKET_CUSTODY)
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
    unit = merge_custody_unit(SERVICE, SERVICE_CUSTODY)
    require(one(unit, "Service", "Type") == "exec", "service must use Type=exec")
    require(one(unit, "Service", "User") == "hepta-browserd", "wrong service user")
    require(one(unit, "Service", "Group") == "hepta-browserd", "wrong service group")
    # Empty assignments clear explicit unit lists, not NSS account groups.
    require(list_value(unit, "Service", "SupplementaryGroups") == [], "effective supplementary groups not cleared")
    require(list_value(unit, "Service", "ReadWritePaths") == [], "effective writable paths not cleared")
    require(list_value(unit, "Service", "ReadOnlyPaths") == ["/run/hepta/browserd"], "effective read-only path changed")
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

    sysusers = sysusers_records(read(SYSUSERS))
    require(("g", "hepta-agent", "-") in sysusers and ("g", "hepta-agent-socket", "-") in sysusers,
            "sysusers group mapping changed")
    for account in ("hepta-agent", "hepta-browserd"):
        require(any(record[:2] == ("u", account) for record in sysusers), "sysusers account mapping changed")
    require({record for record in sysusers if record[0] == "m"} == {
        ("m", "hepta-browserd", "hepta-agent"), ("m", "hepta-agent", "hepta-agent-socket"),
    }, "sysusers membership mapping changed")
    require(("m", "hepta-browserd", "hepta-agent") in sysusers, "browser socket access group changed")
    require(("m", "hepta-agent", "hepta-agent-socket") in sysusers, "Agent lacks parent traversal group")
    require(("m", "hepta-browserd", "hepta-agent-socket") not in sysusers,
            "browser mechanism gained parent custody group")

    tmpfiles = tmpfiles_records(read(TMPFILES))
    require(set(tmpfiles) == {
        ("d", "/run/hepta", "0755", "root", "root", "-", "-"),
        ("d", "/run/hepta/browserd", "0750", "root", "hepta-agent-socket", "-", "-"),
        ("d", "/var/lib/hepta-browserd", "0700", "hepta-browserd", "hepta-browserd", "-", "-"),
    }, "root parent custody mapping changed")

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
        "packaging/debian/systemd/hepta-browserd-agent.socket.d/10-root-path-custody.conf",
        "packaging/debian/systemd/hepta-browserd-agent@.service.d/10-root-path-custody.conf",
        "packaging/debian/sysusers.d/trillionnium-desktop.conf",
        "packaging/debian/tmpfiles.d/trillionnium-desktop.conf",
        "packaging/debian/systemd-preset/90-trillionnium-desktop.preset",
    }
    require(required_sources <= installed, f"install map misses {sorted(required_sources - installed)}")
    for path, destination in (
        (SOCKET_CUSTODY, "lib/systemd/system/hepta-browserd-agent.socket.d"),
        (SERVICE_CUSTODY, "lib/systemd/system/hepta-browserd-agent@.service.d"),
    ):
        entries = [line.split() for line in install.splitlines()
                   if line.strip() and not line.lstrip().startswith("#")
                   and line.split()[0] == path.relative_to(ROOT).as_posix()]
        require(entries == [[path.relative_to(ROOT).as_posix(), destination]],
                "custody drop-in installation changed")
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
    attestor_cargo = tomllib.loads(read(ATTESTOR_CARGO))

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
    require(features == {
        "default": [],
        "fixture": [
            "dep:hepta-agent-port",
            "dep:hepta-browser-codec",
            "hepta-peer-attestation/qualification-static-attestation",
        ],
    }, "fixture feature mapping changed")
    dependencies = cargo.get("dependencies", {})
    for name in ("hepta-agent-port", "hepta-browser-codec"):
        dependency = dependencies.get(name)
        require(isinstance(dependency, dict) and dependency.get("optional") is True,
                f"fixture dependency {name} is not optional")
    attestor_dependency = dependencies.get("hepta-peer-attestation")
    require(isinstance(attestor_dependency, dict) and attestor_dependency.get("features", []) == [],
            "product dependency enables peer attestor features")
    attestor_features = attestor_cargo.get("features", {})
    require(attestor_features.get("default") == [], "peer attestor features are enabled by default")
    require(attestor_features.get("qualification-static-attestation") == [],
            "qualification attestation feature mapping changed")
    bins = {entry.get("name"): entry for entry in cargo.get("bin", [])}
    product = bins.get("hepta-agent-portd", {})
    fixture_bin = bins.get("hepta-agent-port-fixture", {})
    require(product.get("path") == "src/main.rs", "product bin path changed")
    require("required-features" not in product, "product binary unexpectedly feature-gated")
    require(fixture_bin.get("path") == "src/bin/hepta-agent-port-fixture.rs", "fixture bin path changed")
    require(fixture_bin.get("required-features") == ["fixture"], "fixture bin is not explicitly feature-gated")
    examples = {entry.get("name"): entry for entry in cargo.get("example", [])}
    d1_fixture = examples.get("hepta-agent-d1-fixture", {})
    require(d1_fixture.get("path") == "examples/hepta-agent-d1-fixture.rs", "D1 fixture example path changed")
    require(d1_fixture.get("required-features") == ["fixture"], "D1 fixture example is not explicitly feature-gated")

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


def _cli_failure_category(error: Exception) -> str:
    # Preserve known feature findings without printing arbitrary parser input.
    known = {
        "fixture feature mapping changed", "fixture dependency hepta-agent-port is not optional",
        "fixture dependency hepta-browser-codec is not optional", "D1 fixture example is not explicitly feature-gated",
        "fixture feature is enabled by default", "peer attestor features are enabled by default",
        "product dependency enables peer attestor features", "malformed unit section",
        "directive outside section", "malformed unit directive", "unsupported unit syntax",
        "duplicate unit directive", "custody drop-in directives changed", "duplicate custody drop-in directive",
        "effective supplementary groups not cleared", "effective writable paths not cleared",
        "effective read-only path changed", "malformed sysusers record", "duplicate sysusers record",
        "malformed tmpfiles record", "duplicate tmpfiles path", "unsupported configuration syntax",
        "sysusers membership mapping changed", "sysusers group mapping changed", "sysusers account mapping changed",
        "browser socket access group changed", "Agent lacks parent traversal group",
        "browser mechanism gained parent custody group", "root parent custody mapping changed",
        "custody drop-in installation changed", "socket preset is not exactly disabled",
        "production package installs fixture binary", "package ships enable marker",
    }
    message = str(error)
    return message if type(error) is AssertionError and message in known else "SOURCE_INVALID"


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
    except (AssertionError, OSError, UnicodeError, KeyError, TypeError, ValueError, tomllib.TOMLDecodeError) as error:
        print("AgentPort custody and fixture separation audit: FAIL: " + _cli_failure_category(error), file=sys.stderr)
        raise SystemExit(1)
