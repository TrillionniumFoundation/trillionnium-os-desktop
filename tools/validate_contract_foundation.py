#!/usr/bin/env python3
"""Validate the bounded S02 contract foundation without executing product code."""

from __future__ import annotations

import json
import re
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONSTRAINTS = ROOT / "contracts/contract-core-constraints.v1.json"
CORE_SOURCE = ROOT / "crates/trillionnium-contract-core/src/lib.rs"
BROWSER_SOURCE = ROOT / "crates/hepta-browser-contracts/src/lib.rs"
SESSION_MACHINE = ROOT / "crates/hepta-session-core/src/machine.rs"
CORE_MANIFEST = ROOT / "crates/trillionnium-contract-core/Cargo.toml"
BROWSER_MANIFEST = ROOT / "crates/hepta-browser-contracts/Cargo.toml"

ERRORS: list[str] = []


def fail(message: str) -> None:
    ERRORS.append(message)


def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key {key!r}")
        result[key] = value
    return result


def load_constraints() -> dict[str, Any]:
    try:
        value = json.loads(
            CONSTRAINTS.read_text(encoding="utf-8"),
            object_pairs_hook=reject_duplicate_keys,
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as error:
        fail(f"invalid contract constraint registry: {error}")
        return {}
    if not isinstance(value, dict):
        fail("contract constraint registry must be a JSON object")
        return {}
    return value


def require_text(text: str, needle: str, label: str) -> None:
    if needle not in text:
        fail(f"{label} is missing {needle!r}")


def check_manifests() -> None:
    core = tomllib.loads(CORE_MANIFEST.read_text(encoding="utf-8"))
    browser = tomllib.loads(BROWSER_MANIFEST.read_text(encoding="utf-8"))

    for label, manifest in (("contract core", core), ("browser contracts", browser)):
        package = manifest.get("package", {})
        if package.get("autobins") is not False:
            fail(f"{label} must disable Cargo binary auto-discovery")
        if package.get("build") is not False:
            fail(f"{label} must disable package build scripts")

    if core.get("dependencies"):
        fail("contract core must not gain dependencies")
    if browser.get("dependencies") != {
        "trillionnium-contract-core": {"path": "../trillionnium-contract-core"}
    }:
        fail("browser contracts dependency graph changed")


def check_registry_alignment(registry: dict[str, Any]) -> None:
    core = CORE_SOURCE.read_text(encoding="utf-8")
    browser = BROWSER_SOURCE.read_text(encoding="utf-8")
    session = SESSION_MACHINE.read_text(encoding="utf-8")

    if registry.get("schema") != "trillionnium.desktop.contract-core-constraints.v1":
        fail("unexpected contract constraint schema")

    identifiers = registry.get("bounded_identifiers", {})
    constants = {
        "MAX_REQUEST_ID_BYTES": identifiers.get("request_id_max_utf8_bytes"),
        "MAX_SESSION_ID_BYTES": identifiers.get("session_id_max_utf8_bytes"),
        "MAX_LEASE_ID_BYTES": identifiers.get("lease_id_max_utf8_bytes"),
    }
    for name, value in constants.items():
        require_text(core, f"pub const {name}: usize = {value};", "contract core")

    digest = registry.get("sha256_hex", {})
    if digest.get("length_ascii_bytes") != 64:
        fail("SHA-256 textual length must remain 64 bytes")
    require_text(core, "value.len() != 64", "contract core")
    require_text(core, "matches!(byte, b'a'..=b'f')", "contract core")

    dns = registry.get("dns_label", {})
    if dns.get("max_ascii_bytes") != 63:
        fail("DNS-label maximum must remain 63 bytes")
    require_text(core, "bytes.len() <= 63", "contract core")
    require_text(browser, "TrustedAppIdentity", "browser contracts")

    revisions = registry.get("revision_clock", {})
    if revisions.get("counter_type") != "u64":
        fail("revision counters must remain u64")
    if revisions.get("overflow_policy") != "error_before_any_state_change":
        fail("revision overflow policy must be fail-closed and atomic")
    initial = revisions.get("initial", {})
    for field, value in initial.items():
        require_text(core, f"{field}: {value}", "contract core")

    if "saturating_add" in core:
        fail("contract core silently saturates a security-relevant revision")
    for method in (
        "on_dom_commit",
        "on_semantic_snapshot",
        "on_navigation_commit",
        "on_process_recovery",
    ):
        if re.search(
            rf"pub fn {method}\(&mut self\) -> Result<\(\), RevisionError>",
            core,
        ) is None:
            fail(f"{method} must return Result<(), RevisionError>")

    require_text(session, ".map_err(TransitionError::RevisionExhausted)?", "session machine")
    if "now_ms.saturating_add" in session:
        fail("session lease time silently saturates")
    if session.count(".checked_add(") < 2:
        fail("session lease acquisition and extension must check time overflow")


def check_documentation() -> None:
    required = {
        "crates/trillionnium-contract-core/README.md": (
            "## Responsibilities",
            "## Overflow and atomicity",
            "## Compatibility and change protocol",
        ),
        "crates/hepta-browser-contracts/README.md": (
            "## Responsibilities",
            "## Versioning and unknown values",
            "## Compatibility and change protocol",
        ),
    }
    for relative, headings in required.items():
        path = ROOT / relative
        if not path.is_file():
            fail(f"missing module documentation: {relative}")
            continue
        text = path.read_text(encoding="utf-8")
        for heading in headings:
            require_text(text, heading, relative)


def main() -> int:
    registry = load_constraints()
    check_manifests()
    check_registry_alignment(registry)
    check_documentation()

    if ERRORS:
        for error in ERRORS:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"contract foundation validation failed with {len(ERRORS)} error(s)",
            file=sys.stderr,
        )
        return 1

    print("contract foundation validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
