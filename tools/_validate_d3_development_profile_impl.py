#!/usr/bin/env python3
"""Validate the isolated persistent D3 development AgentPort profile."""

from __future__ import annotations

import json
import os
import stat
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []


def fail(message: str) -> None:
    ERRORS.append(message)


def _display(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return os.fspath(path)


def _read_regular_text(path: Path) -> str:
    path = Path(path)
    if any(component == ".." for component in path.parts):
        raise OSError(f"validator path contains '..': {path}")
    root = ROOT.resolve(strict=True)
    candidate = path if path.is_absolute() else ROOT / path
    candidate = Path(os.path.abspath(os.fspath(candidate)))
    try:
        candidate.relative_to(root)
    except ValueError as error:
        raise OSError(f"validator path escapes repository root: {path}") from error

    current = Path(candidate.anchor)
    for component in candidate.parts:
        if component == candidate.anchor:
            continue
        current /= component
        metadata = os.lstat(current)
        if stat.S_ISLNK(metadata.st_mode):
            raise OSError(f"validator path contains a symlink: {current}")

    descriptor = os.open(
        candidate,
        os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise OSError(f"validator path is not a regular file: {candidate}")
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=True) as stream:
            descriptor = -1
            return stream.read()
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def require_text(path: Path | str, *markers: str) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        candidate = ROOT / candidate
    try:
        text = _read_regular_text(candidate)
    except (OSError, UnicodeError) as error:
        fail(f"cannot read {_display(candidate)}: {error}")
        return ""
    for marker in markers:
        if marker not in text:
            fail(f"{_display(candidate)} is missing {marker!r}")
    return text


def read_text(relative: str) -> str:
    return require_text(ROOT / relative)


def load_toml(relative: str) -> dict[str, Any] | None:
    error_count = len(ERRORS)
    text = read_text(relative)
    if len(ERRORS) != error_count:
        return None
    try:
        return tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        fail(f"invalid TOML {relative}: {error}")
        return None


def load_json(relative: str) -> dict[str, Any] | None:
    error_count = len(ERRORS)
    text = read_text(relative)
    if len(ERRORS) != error_count:
        return None
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        fail(f"invalid JSON {relative}: {error}")
        return None
    if not isinstance(value, dict):
        fail(f"{relative} must contain an object")
        return None
    return value


def parse_unit(relative: str) -> dict[str, dict[str, list[str]]]:
    sections: dict[str, dict[str, list[str]]] = {}
    current: str | None = None
    for line_number, raw in enumerate(read_text(relative).splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            current = line[1:-1]
            if not current:
                fail(f"{relative}:{line_number} has an empty section")
                continue
            sections.setdefault(current, {})
            continue
        if current is None or "=" not in line:
            fail(f"{relative}:{line_number} has a malformed directive")
            continue
        key, value = line.split("=", 1)
        sections[current].setdefault(key, []).append(value)
    return sections


def one(unit: dict[str, dict[str, list[str]]], section: str, key: str) -> str | None:
    values = unit.get(section, {}).get(key, [])
    if len(values) != 1:
        fail(f"expected exactly one {section}.{key}, got {values!r}")
        return None
    return values[0]


def check_manifest() -> None:
    """Retain the historical validator API for the existing custody tests."""

    manifest = load_toml("apps/hepta-agent-portd/Cargo.toml")
    if manifest is None:
        return
    features = manifest.get("features")
    if not isinstance(features, dict):
        fail("hepta-agent-portd feature table is missing")
        return
    expected = [
        "dep:hepta-agent-port",
        "dep:hepta-browser-codec",
        "dep:hepta-browser-actor",
        "dep:hepta-session-core",
        "hepta-peer-attestation/development-static-attestation",
    ]
    if features.get("development") != expected:
        fail("legacy development binary feature graph changed")
    if features.get("default") != []:
        fail("legacy development feature must remain non-default")


def check_workspace() -> None:
    root = load_toml("Cargo.toml")
    if root is None:
        return
    workspace = root.get("workspace")
    if not isinstance(workspace, dict):
        fail("root Cargo.toml has no workspace table")
        return
    for field in ("members", "default-members"):
        values = workspace.get(field)
        if not isinstance(values, list) or "crates/hepta-d3-development" not in values:
            fail(f"workspace.{field} must include crates/hepta-d3-development")

    crate_relative = "crates/hepta-d3-development/Cargo.toml"
    error_count = len(ERRORS)
    crate_text = read_text(crate_relative)
    if len(ERRORS) != error_count:
        return
    try:
        crate = tomllib.loads(crate_text)
    except tomllib.TOMLDecodeError as error:
        fail(f"invalid D3 Cargo.toml: {error}")
        return
    package = crate.get("package")
    if not isinstance(package, dict) or package.get("name") != "hepta-d3-development":
        fail("D3 development crate package identity is missing")
    features = crate.get("features")
    dependencies = crate.get("dependencies")
    if not isinstance(features, dict) or features.get("default") != []:
        fail("D3 development package must have an empty default feature set")
    if not isinstance(dependencies, dict):
        fail("D3 development crate dependencies are missing")
        return
    expected_local = {
        "hepta-agent-port",
        "hepta-agent-transport",
        "hepta-browser-actor",
        "hepta-browser-codec",
        "hepta-peer-attestation",
        "hepta-session-core",
    }
    if not expected_local <= dependencies.keys():
        fail("D3 development crate does not link the complete typed actor stack")
    if any(
        not isinstance(dependencies.get(name), dict)
        or dependencies[name].get("optional") is not True
        for name in (*sorted(expected_local), "libc")
    ):
        fail("every D3 runtime dependency must remain optional")
    development = features.get("development") if isinstance(features, dict) else None
    if not isinstance(development, list):
        fail("D3 development feature is missing")
    else:
        required = {
            *(f"dep:{name}" for name in expected_local),
            "dep:libc",
            "hepta-peer-attestation/development-static-attestation",
        }
        if set(development) != required:
            fail("D3 development feature graph changed")
        if "hepta-peer-attestation/qualification-static-attestation" in development:
            fail("D3 development package must not enable qualification static attestation")

    bins = crate.get("bin")
    expected_names = {
        "hepta-agent-port-development-sessiond",
        "hepta-agent-d3-fixture",
        "hepta-d3-journal-check",
    }
    if not isinstance(bins, list):
        fail("D3 development crate has no binary declarations")
    else:
        names = {entry.get("name") for entry in bins if isinstance(entry, dict)}
        if names != expected_names:
            fail(f"D3 binary set changed: {sorted(str(name) for name in names)}")
        for entry in bins:
            if isinstance(entry, dict) and entry.get("required-features") != ["development"]:
                fail(f"D3 binary {entry.get('name')!r} is not feature-gated")
    for forbidden in ("qualification-static-attestation", "CAP_SYS_PTRACE"):
        if forbidden in crate_text:
            fail(f"D3 crate unexpectedly contains {forbidden}")


def _joined_sources(relatives: tuple[str, ...]) -> str:
    return "\n".join(read_text(relative) for relative in relatives)


def check_session_daemon() -> None:
    relatives = (
        "crates/hepta-d3-development/src/bin/sessiond.rs",
        "crates/hepta-d3-development/src/sessiond/activation.rs",
        "crates/hepta-d3-development/src/sessiond/service.rs",
        "crates/hepta-d3-development/src/sessiond/storage.rs",
    )
    source = _joined_sources(relatives)
    markers = (
        "LISTEN_PID",
        "LISTEN_FDS",
        "LISTEN_FDNAMES",
        "SO_ACCEPTCONN",
        "UnixListener::from_raw_fd",
        "listener.accept()",
        "BrowserActor<DeterministicLocalRuntime>",
        "ReceiptLifecycleObserver",
        "serve_one_with_observer",
        "attest_with_static_executable_digest",
        "PrincipalBinding::bind_attested",
        "same_peer",
        "reconcile_unresolved",
        "\\\"persistent_actor\\\":true",
        "\\\"one_request_per_connection\\\":true",
        "\\\"product_agent_port_enabled\\\":false",
        "\\\"external_effect_authority\\\":false",
    )
    for marker in markers:
        if marker not in source:
            fail(f"D3 persistent session service is missing {marker!r}")
    for forbidden in (
        "UnixListener::bind",
        "TcpListener",
        "TcpStream",
        "CAP_SYS_PTRACE",
        "qualification-static-attestation",
    ):
        if forbidden in source:
            fail(f"D3 persistent session service must not contain {forbidden}")


def check_fixture_and_journal() -> None:
    fixture = _joined_sources(
        (
            "crates/hepta-d3-development/src/bin/fixture.rs",
            "crates/hepta-d3-development/src/fixture/client.rs",
            "crates/hepta-d3-development/src/fixture/corpus.rs",
            "crates/hepta-d3-development/src/fixture/model.rs",
        )
    )
    for marker in (
        "d3-health",
        "d3-create",
        "d3-navigate-local",
        "d3-observe",
        "d3-wait",
        "d3-extract",
        "d3-stale-document",
        "d3-external-denied",
        "d3-page-act-unsupported",
        "d3-close",
        "d3-post-close-stale",
        "same_process_pid",
        "\\\"persistent_actor_proven\\\":true",
    ):
        if marker not in fixture:
            fail(f"D3 TaskFlow fixture is missing {marker!r}")
    for forbidden in ("UnixListener", "TcpListener", "TcpStream"):
        if forbidden in fixture:
            fail(f"D3 TaskFlow fixture must not contain {forbidden}")

    journal = read_text("crates/hepta-d3-development/src/bin/journal_check.rs")
    for marker in (
        "Requested",
        "Dispatched",
        "is_terminal",
        "\\\"unresolved_receipts\\\":0",
        "\\\"requested_dispatched_terminal_for_every_receipt\\\":true",
        "\\\"potential_external_effects_never_auto_replayed\\\":true",
    ):
        if marker not in journal:
            fail(f"D3 receipt checker is missing {marker!r}")


def check_units() -> None:
    socket_relative = "packaging/debian/systemd/hepta-browserd-agent-development.socket"
    service_relative = "packaging/debian/systemd/hepta-browserd-agent-development.service"
    socket = parse_unit(socket_relative)
    service = parse_unit(service_relative)
    expected_socket = {
        ("Unit", "ConditionPathExists"): "/etc/hepta/enable-agent-port-development",
        ("Socket", "ListenStream"): "/run/hepta/browserd/agent-development.sock",
        ("Socket", "SocketUser"): "hepta-browserd",
        ("Socket", "SocketGroup"): "hepta-agent",
        ("Socket", "SocketMode"): "0660",
        ("Socket", "Accept"): "no",
        ("Socket", "Service"): "hepta-browserd-agent-development.service",
        ("Socket", "FileDescriptorName"): "agent-development",
        ("Socket", "RemoveOnStop"): "yes",
    }
    for (section, key), value in expected_socket.items():
        if one(socket, section, key) != value:
            fail(f"{socket_relative} {section}.{key} must equal {value!r}")

    expected_service = {
        ("Unit", "ConditionPathExists"): "/etc/hepta/enable-agent-port-development",
        ("Unit", "ConditionFileIsExecutable"): "/usr/libexec/hepta-agent",
        ("Service", "User"): "hepta-browserd",
        ("Service", "Group"): "hepta-browserd",
        ("Service", "SupplementaryGroups"): "hepta-agent",
        ("Service", "ExecStart"): "/usr/libexec/hepta-agent-port-development-sessiond --profile development",
        ("Service", "PrivateNetwork"): "yes",
        ("Service", "RestrictAddressFamilies"): "AF_UNIX",
        ("Service", "ProtectProc"): "default",
        ("Service", "ProcSubset"): "all",
        ("Service", "CapabilityBoundingSet"): "",
        ("Service", "AmbientCapabilities"): "",
        ("Service", "StateDirectory"): "hepta-browserd",
    }
    for (section, key), value in expected_service.items():
        if one(service, section, key) != value:
            fail(f"{service_relative} {section}.{key} must equal {value!r}")
    service_text = read_text(service_relative)
    for forbidden in ("StandardInput=socket", "CAP_SYS_PTRACE", "PrivateNetwork=no"):
        if forbidden in service_text:
            fail(f"persistent D3 service must not contain {forbidden}")

    # The historical template remains only for existing source-audit workflows.
    # The canonical Accept=no socket must never reference it, and neither unit
    # may enter the production Debian install map.
    legacy = ROOT / "packaging/debian/systemd/hepta-browserd-agent-development@.service"
    if legacy.exists() and "hepta-browserd-agent-development@.service" in read_text(socket_relative):
        fail("canonical D3 socket still references the per-connection template")
    production_install = read_text("packaging/debian/hepta-agent-portd.install")
    for forbidden in (
        "hepta-agent-port-development-sessiond",
        "hepta-agent-d3-fixture",
        "hepta-d3-journal-check",
        "hepta-browserd-agent-development",
    ):
        if forbidden in production_install:
            fail(f"production install map unexpectedly contains {forbidden}")


def check_contract() -> None:
    contract = load_json("contracts/browser-actor.v1.json")
    if contract is None:
        return
    activation = contract.get("activation")
    if not isinstance(activation, dict):
        fail("browser-actor activation contract is missing")
        return
    expected = {
        "product_agent_port_enabled": False,
        "development_profile_requires_explicit_selection": True,
        "development_binary": "hepta-agent-port-development-sessiond",
        "development_fixture_binary": "hepta-agent-d3-fixture",
        "development_journal_checker": "hepta-d3-journal-check",
        "development_listener_owner": "systemd",
        "development_socket_accept_mode": "accept_no_persistent_service",
        "development_actor_lifetime": "persistent_across_one_request_connections",
        "development_same_peer_pid_required": True,
        "development_marker": "/etc/hepta/enable-agent-port-development",
        "development_socket": "/run/hepta/browserd/agent-development.sock",
        "development_profile_argument": "--profile development",
        "development_static_attestation_available": True,
        "development_cross_uid_procfs_required": False,
        "development_binary_in_production_install_map": False,
        "production_release_authorized": False,
    }
    for key, value in expected.items():
        if activation.get(key) != value:
            fail(f"browser-actor activation.{key} must equal {value!r}")


def main() -> int:
    ERRORS.clear()
    check_manifest()
    check_workspace()
    check_session_daemon()
    check_fixture_and_journal()
    check_units()
    check_contract()
    if ERRORS:
        for error in ERRORS:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"D3 persistent development-profile validation failed with {len(ERRORS)} error(s)",
            file=sys.stderr,
        )
        return 1
    print("D3 persistent development-profile validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
