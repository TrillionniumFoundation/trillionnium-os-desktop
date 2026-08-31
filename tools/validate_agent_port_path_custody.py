#!/usr/bin/env python3
"""Verify root-owned AgentPort pathname custody and effective unit overrides."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path
from typing import Iterable

DEFAULT_ROOT = Path(__file__).resolve().parents[1]
SOCKET_DIRECTORY = "/run/hepta/browserd"
SOCKET_GROUP = "hepta-agent-socket"
PRODUCT_SOCKET = "packaging/debian/systemd/hepta-browserd-agent.socket"
PRODUCT_SOCKET_DROPIN = "packaging/debian/systemd/hepta-browserd-agent.socket.d/10-root-path-custody.conf"
PRODUCT_SERVICE = "packaging/debian/systemd/hepta-browserd-agent@.service"
PRODUCT_SERVICE_DROPIN = "packaging/debian/systemd/hepta-browserd-agent@.service.d/10-root-path-custody.conf"
DEVELOPMENT_SOCKET = "packaging/debian/systemd/hepta-browserd-agent-development.socket"
DEVELOPMENT_SOCKET_DROPIN = "packaging/debian/systemd/hepta-browserd-agent-development.socket.d/10-root-path-custody.conf"
DEVELOPMENT_SERVICE = "packaging/debian/systemd/hepta-browserd-agent-development@.service"
DEVELOPMENT_SERVICE_DROPIN = "packaging/debian/systemd/hepta-browserd-agent-development@.service.d/10-root-path-custody.conf"
TMPFILES = "packaging/debian/tmpfiles.d/trillionnium-desktop.conf"
SYSUSERS = "packaging/debian/sysusers.d/trillionnium-desktop.conf"
INSTALL = "packaging/debian/hepta-agent-portd.install"
CONTRACT = "contracts/agent-port-custody.v1.json"
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


class PolicyError(ValueError):
    """Stable fail-closed source-policy error."""


def read_regular_text(root: Path, relative: str) -> str:
    if not relative or relative.startswith("/") or "\\" in relative:
        raise PolicyError(f"unsafe repository path: {relative!r}")
    parts = relative.split("/")
    if any(part in {"", ".", ".."} for part in parts):
        raise PolicyError(f"unsafe repository path component: {relative!r}")
    root = root.resolve(strict=True)
    path = root.joinpath(*parts)
    current = root
    for part in parts:
        current /= part
        try:
            metadata = os.lstat(current)
        except OSError as error:
            raise PolicyError(f"cannot inspect {relative}: {error}") from error
        if stat.S_ISLNK(metadata.st_mode):
            raise PolicyError(f"repository path contains symlink: {relative}")
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | _O_CLOEXEC | _O_NOFOLLOW)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise PolicyError(f"repository path is not a regular file: {relative}")
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=True) as stream:
            descriptor = None
            return stream.read()
    except (OSError, UnicodeError) as error:
        raise PolicyError(f"cannot read {relative}: {error}") from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def parse_unit(text: str, *, label: str) -> list[tuple[str, str, str]]:
    """Parse ordered systemd assignments while preserving list resets."""
    assignments: list[tuple[str, str, str]] = []
    section: str | None = None
    for line_number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("#", ";")):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1]
            if not section:
                raise PolicyError(f"{label}:{line_number}: empty section")
            continue
        if section is None or "=" not in line:
            raise PolicyError(f"{label}:{line_number}: malformed assignment")
        key, value = line.split("=", 1)
        if not key or any(character.isspace() for character in key):
            raise PolicyError(f"{label}:{line_number}: invalid key")
        assignments.append((section, key, value))
    return assignments


def merge_units(texts: Iterable[tuple[str, str]]) -> list[tuple[str, str, str]]:
    merged: list[tuple[str, str, str]] = []
    for label, text in texts:
        merged.extend(parse_unit(text, label=label))
    return merged


def last_value(assignments: Iterable[tuple[str, str, str]], section: str, key: str) -> str | None:
    value: str | None = None
    for candidate_section, candidate_key, candidate_value in assignments:
        if candidate_section == section and candidate_key == key:
            value = candidate_value
    return value


def list_value(assignments: Iterable[tuple[str, str, str]], section: str, key: str) -> list[str]:
    result: list[str] = []
    for candidate_section, candidate_key, candidate_value in assignments:
        if candidate_section != section or candidate_key != key:
            continue
        if candidate_value == "":
            result.clear()
        else:
            result.extend(candidate_value.split())
    return result


def non_comment_lines(text: str) -> list[str]:
    return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def require_equal(actual: object, expected: object, message: str) -> None:
    if actual != expected:
        raise PolicyError(f"{message}: expected {expected!r}, found {actual!r}")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise PolicyError(message)


def merged_unit(root: Path, base: str, dropin: str) -> list[tuple[str, str, str]]:
    return merge_units([(base, read_regular_text(root, base)), (dropin, read_regular_text(root, dropin))])


def validate(root: Path = DEFAULT_ROOT) -> dict[str, object]:
    root = root.resolve(strict=True)
    product_socket = merged_unit(root, PRODUCT_SOCKET, PRODUCT_SOCKET_DROPIN)
    development_socket = merged_unit(root, DEVELOPMENT_SOCKET, DEVELOPMENT_SOCKET_DROPIN)
    product_service = merged_unit(root, PRODUCT_SERVICE, PRODUCT_SERVICE_DROPIN)
    development_service = merged_unit(root, DEVELOPMENT_SERVICE, DEVELOPMENT_SERVICE_DROPIN)

    for label, unit, expected_path in (
        ("product", product_socket, "/run/hepta/browserd/agent.sock"),
        ("development", development_socket, "/run/hepta/browserd/agent-development.sock"),
    ):
        require_equal(last_value(unit, "Socket", "ListenStream"), expected_path, f"{label} socket path drift")
        require_equal(last_value(unit, "Socket", "SocketUser"), "root", f"{label} socket must be root-owned")
        require_equal(last_value(unit, "Socket", "SocketGroup"), SOCKET_GROUP, f"{label} socket client group drift")
        require_equal(last_value(unit, "Socket", "SocketMode"), "0660", f"{label} socket mode drift")
        require_equal(last_value(unit, "Socket", "DirectoryMode"), "0750", f"{label} directory mode drift")

    require_equal(list_value(product_service, "Service", "ReadWritePaths"), [], "product service retains writable socket path")
    require_equal(list_value(product_service, "Service", "ReadOnlyPaths"), [SOCKET_DIRECTORY], "product read-only path set drift")
    require_equal(list_value(product_service, "Service", "SupplementaryGroups"), [], "product explicit supplementary groups were not reset")
    require_equal(list_value(development_service, "Service", "ReadWritePaths"), ["/var/lib/hepta-browserd/development"], "development writable path set drift")
    require_equal(list_value(development_service, "Service", "ReadOnlyPaths"), [SOCKET_DIRECTORY, "/usr/libexec/hepta-agent"], "development read-only path set drift")
    require_equal(list_value(development_service, "Service", "SupplementaryGroups"), [], "development explicit supplementary groups were not reset")

    rows = [line.split() for line in non_comment_lines(read_regular_text(root, TMPFILES))]
    runtime_rows = [row for row in rows if len(row) >= 5 and row[1] == SOCKET_DIRECTORY]
    require_equal(len(runtime_rows), 1, "runtime directory row count")
    runtime = runtime_rows[0]
    require_equal(runtime[:5], ["d", SOCKET_DIRECTORY, "0750", "root", SOCKET_GROUP], "runtime directory custody drift")

    fields = [line.split() for line in non_comment_lines(read_regular_text(root, SYSUSERS))]
    require(any(row[:2] == ["g", SOCKET_GROUP] for row in fields), "dedicated socket group is missing")
    require(any(len(row) >= 3 and row[:3] == ["m", "hepta-agent", SOCKET_GROUP] for row in fields), "Agent client is not enrolled in socket group")
    require(not any(len(row) >= 3 and row[:3] == ["m", "hepta-browserd", SOCKET_GROUP] for row in fields), "browser mechanism belongs to socket custody group")

    installed_sources = {line.split()[0] for line in non_comment_lines(read_regular_text(root, INSTALL))}
    require(PRODUCT_SOCKET_DROPIN in installed_sources, "production package omits socket custody drop-in")
    require(PRODUCT_SERVICE_DROPIN in installed_sources, "production package omits service custody drop-in")
    require(DEVELOPMENT_SOCKET_DROPIN not in installed_sources and DEVELOPMENT_SERVICE_DROPIN not in installed_sources, "production package installs development custody drop-ins")

    try:
        contract = json.loads(read_regular_text(root, CONTRACT))
    except json.JSONDecodeError as error:
        raise PolicyError(f"invalid custody contract JSON: {error}") from error
    custody = contract.get("path_custody")
    require(isinstance(custody, dict), "contract path_custody object is missing")
    expected = {
        "socket_owner": "root",
        "socket_group": SOCKET_GROUP,
        "directory_owner": "root",
        "directory_group": SOCKET_GROUP,
        "directory_mode": "0750",
        "browser_service_in_socket_group": False,
        "browser_service_socket_directory_access": "read_only",
        "browser_service_socket_path_mutation_authority": False,
        "development_profile_in_production_install_map": False,
    }
    for key, expected_value in expected.items():
        require_equal(custody.get(key), expected_value, f"contract path_custody.{key}")

    return {
        "schema": "trillionnium.desktop.agent-port-path-custody-result.v1",
        "status": "PASS_SOURCE_POLICY",
        "socket_directory": SOCKET_DIRECTORY,
        "socket_owner": "root",
        "socket_group": SOCKET_GROUP,
        "directory_owner": "root",
        "directory_group": SOCKET_GROUP,
        "product_service_socket_path_mutation_authority": False,
        "development_service_socket_path_mutation_authority": False,
        "product_dropins_installed": True,
        "development_dropins_in_production_install_map": False,
        "listener_enabled_by_default": False,
        "external_effect_authority": False,
        "promotion_authoritative": False,
    }


def canonical_json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--write-result", type=Path)
    args = parser.parse_args(argv)
    encoded = canonical_json(validate(args.root))
    if args.write_result is not None:
        destination = args.write_result
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists() or destination.is_symlink():
            raise PolicyError("result destination already exists")
        descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL | _O_CLOEXEC | _O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=True) as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
    sys.stdout.write(encoded)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, PolicyError) as error:
        print(f"AgentPort pathname custody validation failed: {error}", file=sys.stderr)
        raise SystemExit(1)
