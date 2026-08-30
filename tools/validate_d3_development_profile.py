#!/usr/bin/env python3
"""Validate the opt-in D3 development AgentPort profile.

The production custody validator intentionally proves that the shipped daemon
is default-disabled and fixture-free.  This companion validator proves the
opposite, narrowly scoped property for the explicitly selected development
binary: the typed BrowserActor and receipt observer are wired behind a marker
and an inherited AF_UNIX socket, with no listener or external-effect path.
"""

from __future__ import annotations

import os
import stat
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def fail(message: str) -> None:
    ERRORS.append(message)


def _has_symlink_component(path: Path) -> bool:
    """Return whether an existing lexical path component is a symlink.

    A tracked symlink can otherwise make this source validator inspect files
    outside the checked-out repository.  Keep ``..`` segments lexical while
    walking so ``link/../file`` cannot erase the link before ``lstat``.
    """

    lexical = Path(os.fspath(path))
    if not lexical.is_absolute():
        lexical = Path.cwd() / lexical
    current = Path(lexical.anchor)
    for component in lexical.parts:
        if component == lexical.anchor or component == ".":
            continue
        if component == "..":
            current = current.parent
            continue
        current /= component
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            return False
        except OSError as error:
            raise OSError(f"cannot inspect validator path component: {current}") from error
        if stat.S_ISLNK(mode):
            return True
    return False


def _read_regular_text(path: Path) -> str:
    """Read one repository file without following symlink components."""

    if any(component == ".." for component in path.parts):
        raise OSError(f"validator path contains '..': {path}")
    try:
        path.relative_to(ROOT)
    except ValueError as error:
        raise OSError(f"validator path escapes repository root: {path}") from error
    if _has_symlink_component(path):
        raise OSError(f"validator path contains a symlink: {path}")
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | _O_CLOEXEC | _O_NOFOLLOW)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError(f"validator path is not a regular file: {path}")
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=True) as stream:
            descriptor = None
            return stream.read()
    finally:
        if descriptor is not None:
            os.close(descriptor)


def require_text(path: Path, *markers: str) -> str:
    try:
        text = _read_regular_text(path)
    except OSError as error:
        fail(f"cannot read {path.relative_to(ROOT)}: {error}")
        return ""
    for marker in markers:
        if marker not in text:
            fail(f"{path.relative_to(ROOT)} is missing {marker!r}")
    return text


def check_manifest() -> None:
    path = ROOT / "apps/hepta-agent-portd/Cargo.toml"
    try:
        manifest = tomllib.loads(_read_regular_text(path))
    except (OSError, tomllib.TOMLDecodeError) as error:
        fail(f"invalid {path.relative_to(ROOT)}: {error}")
        return

    features = manifest.get("features", {})
    if "development" not in features:
        fail("hepta-agent-portd has no development Cargo feature")
    elif features["development"] != [
        "dep:hepta-agent-port",
        "dep:hepta-browser-codec",
        "dep:hepta-browser-actor",
        "dep:hepta-session-core",
    ]:
        fail(
            "development feature must link only the typed actor/codec/port/session crates"
        )
    if "hepta-peer-attestation/qualification-static-attestation" in features.get(
        "development", []
    ):
        fail(
            "development feature must not enable qualification-static-attestation"
        )
    if features.get("default") != []:
        fail("development profile must not become a default Cargo feature")

    binaries = manifest.get("bin", [])
    development_bins = [
        binary
        for binary in binaries
        if isinstance(binary, dict)
        and binary.get("name") == "hepta-agent-port-developmentd"
    ]
    if len(development_bins) != 1:
        fail("development binary declaration is missing or duplicated")
    else:
        required = development_bins[0].get("required-features")
        if required != ["development"]:
            fail("development binary must require only the development feature")

    production_bins = [
        binary
        for binary in binaries
        if isinstance(binary, dict) and binary.get("name") == "hepta-agent-portd"
    ]
    if len(production_bins) != 1:
        fail("production hepta-agent-portd declaration is missing or duplicated")


def check_sources() -> None:
    development = require_text(
        ROOT / "apps/hepta-agent-portd/src/bin/hepta-agent-port-developmentd.rs",
        "DEVELOPMENT_MARKER_PATH",
        "--profile development",
        "ProcfsPeerAttestor",
        "PrincipalBinding::bind_attested",
        "BrowserActor",
        "DeterministicLocalRuntime",
        "receipt_observer",
        "serve_one_with_observer",
        "ReceiptJournal",
        "listener_created\\\":false",
        "external_effect_authority\\\":false",
        "development_only\\\":true",
        "product_agent_port_connected\\\":false",
        "integrated_image_qualified\\\":false",
        "browser_actor_wired\\\":true",
        "browser_actor_dispatch_exercised\\\":true",
        "browser_actor_connected\\\":false",
        "receipt_observer_wired\\\":true",
        "receipt_observer_connected\\\":false",
        "attestation_exercised\\\":false",
        "journal_exercised\\\":false",
        "scope\\\":\\\"source_wiring_only",
    )
    for forbidden in (
        "UnixListener",
        "TcpListener",
        "TcpStream",
        "D0FixtureHandler",
        "attest_with_static_executable_digest",
        "hash_trusted_executable",
        "qualification-static-attestation",
    ):
        if forbidden in development:
            fail(f"development binary must not contain {forbidden}")

    actor = require_text(
        ROOT / "crates/hepta-browser-actor/src/lib.rs",
        "dispatch_page_act",
        "semantic frame/structure re-resolution is unavailable",
    )
    if "fn dispatch_page_act" not in actor:
        fail("BrowserActor runtime must expose the semantic PageAct resolver hook")

    production = require_text(
        ROOT / "apps/hepta-agent-portd/src/main.rs",
        "ProductHandlerUnavailable",
        "fixture_handler_linked\\\":false",
    )
    # The production source may document that BrowserActor is intentionally
    # absent; reject only dependency/code references, not those comments.
    for forbidden in (
        "use hepta_browser_actor",
        "hepta_browser_actor::",
        "DeterministicLocalRuntime::",
        "ReceiptJournal::",
        "serve_one_with_observer(",
        "attest_with_static_executable_digest",
        "hash_trusted_executable",
        "qualification-static-attestation",
    ):
        if forbidden in production:
            fail(f"production daemon unexpectedly links development symbol {forbidden}")


def check_units() -> None:
    socket = require_text(
        ROOT / "packaging/debian/systemd/hepta-browserd-agent-development.socket",
        "ConditionPathExists=/etc/hepta/enable-agent-port-development",
        "ListenStream=/run/hepta/browserd/agent-development.sock",
        "Accept=yes",
        "RemoveOnStop=yes",
    )
    if "ListenDatagram" in socket or "ListenFIFO" in socket:
        fail("development socket must be a stream-only socket")

    service = require_text(
        ROOT / "packaging/debian/systemd/hepta-browserd-agent-development@.service",
        "ConditionPathExists=/etc/hepta/enable-agent-port-development",
        "Requires=hepta-browserd-agent-development.socket",
        "StandardInput=socket",
        "ExecStart=/usr/libexec/hepta-agent-port-developmentd --profile development",
        "EnvironmentFile=-/etc/hepta/agent-port-development.conf",
        "PrivateNetwork=yes",
        "RestrictAddressFamilies=AF_UNIX",
        "ReadWritePaths=/run/hepta/browserd /var/lib/hepta-browserd/development",
    )
    if "Tcp" in service or "WebDriver" in service:
        fail("development service must not expose TCP/WebDriver authority")
    # The development service deliberately runs as hepta-browserd while its
    # attested peer is hepta-agent.  Linux's PTRACE_MODE_READ_FSCREDS policy
    # therefore blocks the live /proc/<pid>/exe refresh across those UIDs;
    # supplementary group membership is not a substitute for ptrace access.
    for marker in (
        "User=hepta-browserd",
        "Group=hepta-browserd",
        "SupplementaryGroups=hepta-agent",
        "CapabilityBoundingSet=",
    ):
        if marker not in service:
            fail(f"development service must retain cross-UID blocker marker {marker!r}")
    if "CAP_SYS_PTRACE" in service:
        fail("development service must not grant CAP_SYS_PTRACE to bypass the blocker")

    install_map = require_text(ROOT / "packaging/debian/hepta-agent-portd.install")
    if "developmentd" in install_map or "development@" in install_map:
        fail("production install map must exclude the development profile")

    require_text(
        ROOT / "packaging/debian/development/README.md",
        "cargo build --release --locked -p hepta-agent-portd",
        "enable-agent-port-development",
        "HEPTA_D3_EXPECTED_EXECUTABLE_SHA256",
        "agent-development.sock",
        "PrincipalBinding::bind_attested",
    )


def check_contract() -> None:
    import json

    path = ROOT / "contracts/browser-actor.v1.json"
    try:
        contract = json.loads(_read_regular_text(path))
    except (OSError, json.JSONDecodeError) as error:
        fail(f"invalid {path.relative_to(ROOT)}: {error}")
        return
    activation = contract.get("activation", {})
    expected = {
        "product_agent_port_enabled": False,
        "development_profile_requires_explicit_selection": True,
        "development_binary": "hepta-agent-port-developmentd",
        "development_cargo_feature": "development",
        "development_marker": "/etc/hepta/enable-agent-port-development",
        "development_socket": "/run/hepta/browserd/agent-development.sock",
        "development_profile_argument": "--profile development",
        "development_requires_expected_executable_sha256": True,
        "development_live_activation_status": "BLOCKED_UPSTREAM_CROSS_UID_PROCFS",
        "development_source_wiring_only": True,
        "development_static_attestation_available": False,
        "development_static_attestation_scope": "d1_qualification_only",
        "development_service_user": "hepta-browserd",
        "development_expected_peer_user": "hepta-agent",
        "development_blocker": "cross-UID /proc/<pid>/exe reads require PTRACE_MODE_READ_FSCREDS; the development service has no CAP_SYS_PTRACE",
        "development_binary_in_production_install_map": False,
        "listener_created_by_actor_crate": False,
        "production_release_authorized": False,
    }
    for key, value in expected.items():
        if activation.get(key) != value:
            fail(f"browser-actor activation.{key} must equal {value!r}")
    resolution = contract.get("browser_actor", {}).get("semantic_reference_resolution", {})
    resolution_expected = {
        "required_for_page_act": True,
        "runtime_hook": "PageRuntime::dispatch_page_act",
        "atomic_resolve_and_act": True,
        "default_without_resolver": "unsupported",
        "deterministic_local_runtime_page_act": "unsupported",
        "promotion_requires_servo_resolver": True,
    }
    for key, value in resolution_expected.items():
        if resolution.get(key) != value:
            fail(f"browser-actor semantic_reference_resolution.{key} must equal {value!r}")


def main() -> int:
    check_manifest()
    check_sources()
    check_units()
    check_contract()
    if ERRORS:
        for error in ERRORS:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"D3 development-profile validation failed with {len(ERRORS)} error(s)",
            file=sys.stderr,
        )
        return 1
    print("D3 development-profile validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
