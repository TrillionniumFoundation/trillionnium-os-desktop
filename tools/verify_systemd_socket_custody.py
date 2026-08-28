#!/usr/bin/env python3
"""Fail-closed static audit for the default-disabled AgentPort systemd boundary."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable


class CustodyError(RuntimeError):
    pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository-root", type=Path, default=Path.cwd())
    return parser.parse_args()


def parse_unit(path: Path) -> dict[str, dict[str, list[str]]]:
    sections: dict[str, dict[str, list[str]]] = {}
    current: str | None = None
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            if not current:
                raise CustodyError(f"{path}:{number}: empty section")
            sections.setdefault(current, {})
            continue
        if current is None or "=" not in line:
            raise CustodyError(f"{path}:{number}: malformed unit line")
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            raise CustodyError(f"{path}:{number}: empty directive")
        sections[current].setdefault(key, []).append(value.strip())
    return sections


def one(
    unit: dict[str, dict[str, list[str]]],
    section: str,
    key: str,
) -> str:
    values = unit.get(section, {}).get(key, [])
    if len(values) != 1:
        raise CustodyError(f"expected one {section}.{key}, found {values!r}")
    return values[0]


def require_equal(
    unit: dict[str, dict[str, list[str]]],
    section: str,
    key: str,
    expected: str,
) -> None:
    actual = one(unit, section, key)
    if actual != expected:
        raise CustodyError(
            f"{section}.{key} is {actual!r}, expected {expected!r}"
        )


def require_blank(
    unit: dict[str, dict[str, list[str]]], section: str, key: str
) -> None:
    require_equal(unit, section, key, "")


def require_absent(
    unit: dict[str, dict[str, list[str]]], section: str, keys: Iterable[str]
) -> None:
    for key in keys:
        if key in unit.get(section, {}):
            raise CustodyError(f"forbidden directive {section}.{key} is present")


def parse_sysusers(path: Path) -> set[tuple[str, str]]:
    entries: set[tuple[str, str]] = set()
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 2:
            raise CustodyError(f"malformed sysusers line: {raw}")
        entries.add((parts[0], parts[1]))
    return entries


def parse_tmpfiles(path: Path) -> dict[str, tuple[str, str, str, str]]:
    entries: dict[str, tuple[str, str, str, str]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) < 5:
            raise CustodyError(f"malformed tmpfiles line: {raw}")
        kind, target, mode, user, group = parts[:5]
        entries[target] = (kind, mode, user, group)
    return entries


def ensure_no_shipped_enable_marker(root: Path, marker: str) -> None:
    marker_relative = marker.lstrip("/")
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        if relative == marker_relative or relative.endswith("/enable-agent-port"):
            raise CustodyError(f"enable marker is shipped as {relative}")
        if path.suffix in {".install", ".links", ".dirs"}:
            text = path.read_text(encoding="utf-8", errors="replace")
            if marker in text or marker_relative in text:
                raise CustodyError(f"install metadata ships enable marker: {relative}")


def main() -> int:
    root = parse_args().repository_root.resolve()
    socket_path = root / "packaging/debian/systemd/hepta-browserd-agent.socket"
    service_path = root / "packaging/debian/systemd/hepta-browserd-agent@.service"
    preset_path = root / "packaging/debian/systemd-preset/90-trillionnium-desktop.preset"
    sysusers_path = root / "packaging/debian/sysusers.d/trillionnium-desktop.conf"
    tmpfiles_path = root / "packaging/debian/tmpfiles.d/trillionnium-desktop.conf"
    install_path = root / "packaging/debian/hepta-agent-portd.install"
    contract_path = root / "contracts/agent-port-custody.v1.json"

    for path in (
        socket_path,
        service_path,
        preset_path,
        sysusers_path,
        tmpfiles_path,
        install_path,
        contract_path,
    ):
        if not path.is_file():
            raise CustodyError(f"missing custody input: {path.relative_to(root)}")

    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    if contract.get("schema") != "trillionnium.desktop.agent-port-custody.v1":
        raise CustodyError("unsupported custody contract schema")
    marker = contract["activation"]["condition_path"]
    if contract["activation"]["enabled_by_default"] is not False:
        raise CustodyError("contract enables listener by default")
    if contract["activation"]["condition_path_shipped"] is not False:
        raise CustodyError("contract claims the enable marker is shipped")
    if contract["socket"]["remote_network"] is not False:
        raise CustodyError("contract allows a remote listener")
    if contract["effect_policy"] if "effect_policy" in contract else False:
        raise CustodyError("custody contract must not embed semantic effect policy")

    socket = parse_unit(socket_path)
    require_equal(socket, "Unit", "ConditionPathExists", marker)
    require_equal(socket, "Socket", "ListenStream", contract["socket"]["path"])
    require_equal(socket, "Socket", "SocketUser", contract["socket"]["owner"])
    require_equal(socket, "Socket", "SocketGroup", contract["socket"]["group"])
    require_equal(socket, "Socket", "SocketMode", contract["socket"]["mode"])
    require_equal(
        socket, "Socket", "DirectoryMode", contract["socket"]["directory_mode"]
    )
    require_equal(socket, "Socket", "Accept", "yes")
    require_equal(socket, "Socket", "Service", contract["service"]["unit"])
    require_equal(socket, "Socket", "Backlog", str(contract["socket"]["backlog"]))
    require_equal(
        socket,
        "Socket",
        "MaxConnections",
        str(contract["socket"]["max_connections"]),
    )
    require_equal(
        socket,
        "Socket",
        "MaxConnectionsPerSource",
        str(contract["socket"]["max_connections_per_source"]),
    )
    require_equal(socket, "Socket", "RemoveOnStop", "yes")
    require_absent(
        socket,
        "Socket",
        ("ListenDatagram", "ListenFIFO", "ListenMessageQueue", "ListenNetlink"),
    )
    listen = one(socket, "Socket", "ListenStream")
    if not listen.startswith("/run/") or ":" in listen or "@" in listen:
        raise CustodyError(f"unsafe AgentPort listener address: {listen}")

    service = parse_unit(service_path)
    require_equal(service, "Service", "User", contract["service"]["user"])
    require_equal(service, "Service", "Group", contract["service"]["group"])
    require_equal(service, "Service", "StandardInput", "socket")
    require_equal(service, "Service", "NoNewPrivileges", "yes")
    require_equal(service, "Service", "PrivateNetwork", "yes")
    require_equal(service, "Service", "RestrictAddressFamilies", "AF_UNIX")
    require_equal(service, "Service", "Restart", "no")
    require_equal(
        service,
        "Service",
        "RuntimeMaxSec",
        f"{contract['service']['runtime_max_seconds']}s",
    )
    require_blank(service, "Service", "CapabilityBoundingSet")
    require_blank(service, "Service", "AmbientCapabilities")
    exec_start = one(service, "Service", "ExecStart")
    expected_tokens = (
        contract["service"]["binary"],
        "--serve-stdio",
        "--socket-path",
        contract["socket"]["path"],
        "--agent-user",
        contract["client_identity"]["user"],
        "--agent-group",
        contract["client_identity"]["group"],
        "--agent-unit",
        contract["client_identity"]["systemd_unit"],
    )
    for token in expected_tokens:
        if token not in exec_start.split():
            raise CustodyError(f"ExecStart is missing locked token {token!r}")
    require_absent(
        service,
        "Service",
        ("EnvironmentFile", "RootDirectoryStartOnly", "PermissionsStartOnly"),
    )

    preset_lines = {
        line.strip()
        for line in preset_path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    expected_preset = f"disable {contract['socket']['unit']}"
    if expected_preset not in preset_lines:
        raise CustodyError(f"missing default-disable preset: {expected_preset}")
    if any(line.startswith("enable ") for line in preset_lines):
        raise CustodyError("desktop preset enables a unit in the D0 custody package")

    sysusers = parse_sysusers(sysusers_path)
    for account in (contract["service"]["user"], contract["client_identity"]["user"]):
        if ("u", account) not in sysusers:
            raise CustodyError(f"missing dedicated sysuser {account}")

    tmpfiles = parse_tmpfiles(tmpfiles_path)
    expected_runtime = (
        "d",
        contract["socket"]["directory_mode"],
        contract["socket"]["owner"],
        contract["socket"]["group"],
    )
    if tmpfiles.get("/run/hepta/browserd") != expected_runtime:
        raise CustodyError("runtime directory custody does not match the contract")

    install_text = install_path.read_text(encoding="utf-8")
    for source in (
        "hepta-agent-portd",
        "hepta-browserd-agent.socket",
        "hepta-browserd-agent@.service",
        "trillionnium-desktop.conf",
        "90-trillionnium-desktop.preset",
    ):
        if source not in install_text:
            raise CustodyError(f"Debian install map omits {source}")
    ensure_no_shipped_enable_marker(root, marker)

    source_text = (root / "apps/hepta-agent-portd/src/main.rs").read_text(
        encoding="utf-8"
    )
    for token in (
        "PeerIdentity::from_stream",
        "ProcfsPeerAttestor::default",
        "PeerRuntimePolicy::for_system_service",
        "verify_local_socket_path",
        "serve_single_request",
        "browser.runtime_unavailable",
    ):
        if token not in source_text:
            raise CustodyError(f"AgentPort service source omits {token}")

    print(
        json.dumps(
            {
                "status": "PASS",
                "schema": contract["schema"],
                "socket": listen,
                "enabled_by_default": False,
                "condition_path_shipped": False,
                "service_user": one(service, "Service", "User"),
                "client_unit": contract["client_identity"]["systemd_unit"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except CustodyError as error:
        print(f"AgentPort custody HOLD: {error}", file=sys.stderr)
        raise SystemExit(2)
