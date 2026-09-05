#!/usr/bin/env python3
"""Fail-closed repository consistency checks for the desktop product."""

from __future__ import annotations

import json
import os
import re
import stat
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []
SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")
# Reject both rooted and drive-relative Windows spellings.  The latter
# (C:foo) is not absolute on POSIX but is resolved relative to a drive's
# current directory on Windows, so accepting it would make the policy
# platform-dependent.
WINDOWS_ABSOLUTE = re.compile(r"^(?:[A-Za-z]:|[\\/]{2})")

EXPECTED_WORKSPACE_MEMBERS = [
    "apps/hepta-browserd",
    "apps/hepta-agent-portd",
    "crates/hepta-agent-transport",
    "crates/hepta-browser-codec",
    "crates/hepta-agent-port",
    "crates/hepta-peer-attestation",
    "crates/trillionnium-contract-core",
    "crates/hepta-browser-contracts",
    "crates/hepta-session-core",
    "crates/hepta-workspace-composition",
    "crates/hepta-browser-actor",
]

REQUIRED_PATHS = [
    ".github/workflows/ci.yml",
    ".github/CODEOWNERS",
    "SECURITY.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "contracts/README.md",
    "contracts/agent-transport.v1.json",
    "contracts/browser-codec.v1.json",
    "contracts/browser-wire.v1.schema.json",
    "contracts/browser-response.v1.schema.json",
    "crates/hepta-agent-transport/Cargo.toml",
    "crates/hepta-agent-transport/src/lib.rs",
    "crates/hepta-browser-codec/Cargo.toml",
    "crates/hepta-browser-codec/src/lib.rs",
    "crates/hepta-agent-port/Cargo.toml",
    "crates/hepta-agent-port/README.md",
    "crates/hepta-agent-port/src/lib.rs",
    "contracts/agent-port-bridge.v1.json",
    "docs/architecture/CONNECTED_AGENT_PORT_BRIDGE.md",
    "docs/evidence/2026-08-28-d0c04-rust-agent-port.md",
    "docs/evidence/generated/d0c04-rust193-host-result.json",
    "docs/plan/D0C04_EXECUTION_CHECKPOINT-2026-08-28.md",
    "manifests/d0c04-candidate.json",
    "tools/validate_d0c04_rust_product.py",
    "docs/architecture/AUTHENTICATED_AGENT_TRANSPORT.md",
    "docs/architecture/CANONICAL_BROWSER_CODEC.md",
    "docs/architecture/RUST_BROWSER_CODEC.md",
    "docs/evidence/2026-08-28-d0c02-authenticated-uds.md",
    "docs/evidence/2026-08-28-d0c03-rust-product-codec-source.md",
    "tools/validate_rust_browser_codec.py",
    "manifests/cargo-external-allowlist.json",
    "manifests/README.md",
    ".github/workflows/agent-port-custody.yml",
    "apps/hepta-agent-portd/Cargo.toml",
    "apps/hepta-agent-portd/src/main.rs",
    "contracts/agent-port-custody.v1.json",
    "crates/hepta-peer-attestation/Cargo.toml",
    "crates/hepta-peer-attestation/src/lib.rs",
    "docs/architecture/SYSTEMD_AGENT_PORT_CUSTODY.md",
    "docs/evidence/2026-08-29-d0c05-systemd-socket-custody.md",
    "docs/evidence/generated/d0c06-rust193-host-result.json",
    "packaging/debian/hepta-agent-portd.install",
    "packaging/debian/systemd/hepta-browserd-agent.socket",
    "packaging/debian/systemd/hepta-browserd-agent@.service",
    "packaging/debian/sysusers.d/trillionnium-desktop.conf",
    "packaging/debian/tmpfiles.d/trillionnium-desktop.conf",
    "packaging/debian/systemd-preset/90-trillionnium-desktop.preset",
    "tools/verify_systemd_socket_custody.py",
    "contracts/workspace-composition.v1.json",
    "crates/hepta-workspace-composition/Cargo.toml",
    "crates/hepta-workspace-composition/src/lib.rs",
    "crates/hepta-workspace-composition/src/model.rs",
    "crates/hepta-workspace-composition/src/tests.rs",
    "docs/architecture/TRUSTED_WORKSPACE_COMPOSITION.md",
    "crates/hepta-browser-actor/Cargo.toml",
    "crates/hepta-browser-actor/src/lib.rs",
    "contracts/browser-actor.v1.json",
    "docs/architecture/PAGE_OWNER_BROWSER_ACTOR.md",
    "tests/test_validate_project_truth.py",
    "tools/gate_evidence_envelope.py",
    "tools/qualify_servo_exact_pin_evidence.py",
    ".github/workflows/d0t03-source-contract.yml",
    ".github/workflows/governance-integrity.yml",
    "contracts/repository-governance.v1.json",
    "docs/release/D0T03_GOVERNANCE_BOOTSTRAP.md",
    "docs/security/D0T03_REPOSITORY_GOVERNANCE.md",
    "manifests/repository-governance.v1.json",
    "tools/validate_d0t03_source.py",
    "tools/validate_governance_integrity.py",
]

D0C05_EVIDENCE_LIFECYCLE = "STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN"
D0C05_EVIDENCE_FRESHNESS = "STALE_EVIDENCE"
D0C05_HISTORICAL_HEAD = "7be7121b1d2593a0e708ec9ade189ef84ab245da"
D0C05_STALE_REASON_MARKERS = (
    "D0C-05",
    D0C05_HISTORICAL_HEAD,
    "exact candidate head",
    "Rerun",
)
D0C06_EVIDENCE_RELATIVE = "docs/evidence/generated/d0c06-rust193-host-result.json"
D0C06_HISTORICAL_HEAD = "25d2d5882018b9974fc360aaf646128c6b6f175f"
D0C06_HISTORICAL_TREE_SHA = "b475213da8269c39ab7cc4dbfd33d0958da3a108"
D0C06_EVIDENCE_LIFECYCLE = "STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN"
D0C06_EVIDENCE_FRESHNESS = "STALE_EVIDENCE"
D0C06_STATUS = "HOST_VALIDATED_NO_EXECUTION_OR_REPLAY_AUTHORITY"
D0C06_STALE_REASON = (
    "D0C-06 receipt-journal host result "
    "25d2d5882018b9974fc360aaf646128c6b6f175f was recorded before the current "
    "candidate tree. Rerun receipt-journal on the exact candidate head, then "
    "update the bound evidence and merge_ready flag under independent review."
)


def fail(message: str) -> None:
    ERRORS.append(message)


def is_sha256_hex(value: object) -> bool:
    """Return whether *value* is the canonical lowercase SHA-256 encoding."""

    return isinstance(value, str) and SHA256_HEX.fullmatch(value) is not None


def safe_relative_path(value: object, *, base: Path, label: str) -> Path | None:
    """Resolve an untrusted repository path without leaving *base*.

    Manifest paths are data, not trusted code.  Reject absolute, traversal,
    control-character, and platform-ambiguous spellings before touching the
    filesystem.  Existing symlink components are rejected as well: otherwise
    a path that is lexically inside the repository could redirect validation
    to an attacker-controlled file outside it.
    """

    if not isinstance(value, str) or not value:
        fail(f"{label} must be a non-empty relative path")
        return None
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        fail(f"{label} contains a control character")
        return None
    # Cargo and the repository manifests use POSIX paths.  Reject backslashes
    # rather than relying on host-specific Path parsing (a Windows runner would
    # otherwise interpret them as separators).
    if "\\" in value:
        fail(f"{label} contains a backslash separator")
        return None
    if WINDOWS_ABSOLUTE.match(value) or Path(value).is_absolute():
        fail(f"{label} must be relative: {value!r}")
        return None
    raw_parts = value.split("/")
    if not raw_parts or any(part in {"", ".", ".."} for part in raw_parts):
        fail(f"{label} contains an unsafe path component: {value!r}")
        return None

    try:
        base_path = base.resolve(strict=True)
    except OSError as error:
        fail(f"{label} base is unavailable: {error}")
        return None
    if base.is_symlink():
        fail(f"{label} base is a symlink: {base}")
        return None

    candidate = base_path.joinpath(*raw_parts)
    current = base_path
    try:
        for part in raw_parts:
            current /= part
            if current.is_symlink():
                fail(f"{label} contains a symlink component: {value!r}")
                return None
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(base_path)
    except (OSError, RuntimeError, ValueError) as error:
        fail(f"{label} escapes its trusted base: {value!r} ({error})")
        return None
    return candidate


def _has_symlink_component(path: Path) -> bool:
    """Return whether an existing lexical component of *path* is a symlink."""

    # Do not call resolve/abspath here: normalising link/../target before
    # lstat would erase the very symlink component this check protects.
    lexical = Path(os.fspath(path))
    if not lexical.is_absolute():
        lexical = Path.cwd() / lexical
    current = Path(lexical.anchor)
    for component in lexical.parts:
        if component == lexical.anchor:
            continue
        if component == ".":
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
            raise OSError(f"cannot inspect path component {current}") from error
        if stat.S_ISLNK(mode):
            return True
    return False


def _read_bytes_nofollow(path: Path) -> bytes:
    """Read a repository input without following links or leaving ``ROOT``.

    Repository manifests, contracts, and lockfiles drive policy decisions.
    A pathname-only ``read_text`` would allow a symlink (or a final-component
    swap) to substitute an attacker-controlled file before the validator's
    later checks run.  Walk existing components lexically, open with
    ``O_NOFOLLOW``, and verify the descriptor is a regular file.
    """

    path = Path(path)
    if any(component == ".." for component in path.parts):
        raise OSError(f"repository path contains '..': {path}")
    try:
        root = ROOT.resolve(strict=True)
        candidate = path if path.is_absolute() else Path.cwd() / path
        candidate = Path(os.path.abspath(os.fspath(candidate)))
        candidate.relative_to(root)
    except (OSError, RuntimeError, ValueError) as error:
        raise OSError(f"repository path escapes trusted root: {path}") from error
    if _has_symlink_component(candidate):
        raise OSError(f"repository path contains a symlink: {path}")

    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(candidate, os.O_RDONLY | nofollow | cloexec)
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode):
            raise OSError(f"repository path is not a regular file: {path}")
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = None
            return stream.read()
    finally:
        if descriptor is not None:
            os.close(descriptor)


def _read_text_nofollow(path: Path) -> str:
    return _read_bytes_nofollow(path).decode("utf-8")


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return os.fspath(path)


def safe_workspace_dependency_path(
    value: object, *, manifest_path: Path, label: str
) -> Path | None:
    """Resolve a Cargo path dependency while allowing safe parent segments.

    Cargo manifests legitimately refer to sibling workspace crates with
    parent segments. Unlike safe_relative_path, this helper permits those
    segments but requires the resolved target to remain below the repository
    root and rejects symlinked components.
    """

    if not isinstance(value, str) or not value:
        fail(f"{label} must be a non-empty relative path")
        return None
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        fail(f"{label} contains a control character")
        return None
    if "\\" in value or WINDOWS_ABSOLUTE.match(value) or Path(value).is_absolute():
        fail(f"{label} must be a portable relative path: {value!r}")
        return None
    try:
        root_path = ROOT.resolve(strict=True)
        candidate = manifest_path.parent / value
        lexical = Path(os.path.abspath(os.fspath(candidate)))
        if _has_symlink_component(lexical):
            fail(f"{label} contains a symlink component: {value!r}")
            return None
        resolved = candidate.resolve(strict=False)
        resolved.relative_to(root_path)
    except (OSError, RuntimeError, ValueError) as error:
        fail(f"{label} escapes the repository root: {value!r} ({error})")
        return None
    if not resolved.is_dir():
        fail(f"{label} does not resolve to a directory: {value!r}")
        return None
    return resolved


def load_json(path: Path) -> Any:
    try:
        return json.loads(_read_text_nofollow(path))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        fail(f"invalid JSON {_display_path(path)}: {error}")
        return {}


def load_toml(path: Path) -> dict[str, Any]:
    try:
        return tomllib.loads(_read_text_nofollow(path))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as error:
        fail(f"invalid TOML {_display_path(path)}: {error}")
        return {}


def check_d0c06_generated_evidence() -> None:
    """Require the D0C-06 machine snapshot to remain stale and bounded.

    The artifact is historical provenance, not a current promotion result.
    Keep capability status and evidence freshness orthogonal while ensuring the
    generated record cannot silently turn into a current or authoritative
    claim.
    """

    artifact = load_json(ROOT / D0C06_EVIDENCE_RELATIVE)
    if not isinstance(artifact, dict):
        fail("D0C-06 generated evidence must be an object")
        return
    if artifact.get("status") != D0C06_STATUS:
        fail("D0C-06 generated evidence capability status drift")
    if artifact.get("evidence_lifecycle") != D0C06_EVIDENCE_LIFECYCLE:
        fail("D0C-06 generated evidence must require exact-head rerun")
    if artifact.get("evidence_freshness") != D0C06_EVIDENCE_FRESHNESS:
        fail("D0C-06 generated evidence freshness must be STALE_EVIDENCE")
    if artifact.get("merge_ready") is not False:
        fail("D0C-06 generated evidence must clear merge_ready")
    if artifact.get("stale_reason") != D0C06_STALE_REASON:
        fail("D0C-06 generated evidence stale_reason drift")
    if artifact.get("validated_source_head") != D0C06_HISTORICAL_HEAD:
        fail("D0C-06 generated evidence historical source head drift")
    if artifact.get("validated_tree_sha") != D0C06_HISTORICAL_TREE_SHA:
        fail("D0C-06 generated evidence historical tree digest drift")
    ceiling = artifact.get("claim_ceiling")
    expected_claims = {
        "browser_actor_bound",
        "servo_called",
        "agent_listener_enabled",
        "external_effect_authorized",
        "automatic_replay_available",
        "product_ready",
    }
    if not isinstance(ceiling, dict) or set(ceiling) != expected_claims:
        fail("D0C-06 generated evidence claim_ceiling keys drift")
    elif any(type(value) is not bool or value is not False for value in ceiling.values()):
        fail("D0C-06 generated evidence claim_ceiling must remain all false")
    authority = artifact.get("authority")
    if not isinstance(authority, dict) or any(
        type(value) is not bool or value is not False for value in authority.values()
    ):
        fail("D0C-06 generated evidence authority must remain all false")


EXPECTED_JSON_SCHEMAS = {
    "https://schemas.trillionnium.org/desktop/app-manifest.v1.schema.json": "contracts/app-manifest.v1.schema.json",
    "https://schemas.trillionnium.org/desktop/browser-api.v1.schema.json": "contracts/browser-api.v1.schema.json",
    "https://schemas.trillionnium.org/desktop/browser-response.v1.schema.json": "contracts/browser-response.v1.schema.json",
    "https://schemas.trillionnium.org/desktop/browser-wire.v1.schema.json": "contracts/browser-wire.v1.schema.json",
    "https://schemas.trillionnium.org/desktop/capability-permit.v1.schema.json": "contracts/capability-permit.v1.schema.json",
    "https://schemas.trillionnium.org/desktop/capability-permit.v2.schema.json": "contracts/capability-permit.v2.schema.json",
    "https://schemas.trillionnium.org/desktop/receipt.v1.schema.json": "contracts/receipt.v1.schema.json",
}


def check_json_files() -> None:
    schema_ids: dict[str, Path] = {}
    for path in sorted(ROOT.rglob("*.json")):
        document = load_json(path)
        if isinstance(document, dict) and "$id" in document:
            schema_id = document["$id"]
            if not isinstance(schema_id, str):
                fail(f"schema id is not a string in {path.relative_to(ROOT)}")
            elif schema_id in schema_ids:
                fail(
                    f"duplicate schema id {schema_id} in "
                    f"{schema_ids[schema_id].relative_to(ROOT)} and {path.relative_to(ROOT)}"
                )
            else:
                schema_ids[schema_id] = path
    actual = {key: path.relative_to(ROOT).as_posix() for key, path in schema_ids.items()}
    if actual != EXPECTED_JSON_SCHEMAS:
        fail("JSON schema identity/path inventory mismatch")


def check_plan_and_manifests() -> None:
    docs_manifest = load_json(ROOT / "docs/MANIFEST.json")
    state = load_json(ROOT / "manifests/repository-state.json")
    active_plan = docs_manifest.get("active_plan")
    revision = docs_manifest.get("active_plan_revision")
    if not isinstance(active_plan, str):
        fail("docs manifest active_plan is missing")
        return
    plan_path = safe_relative_path(
        active_plan,
        base=ROOT / "docs",
        label="docs manifest active_plan",
    )
    if plan_path is None:
        return
    try:
        plan_text = _read_text_nofollow(plan_path)
    except (OSError, UnicodeError) as error:
        fail(f"active plan is missing or unsafe: docs/{active_plan}: {error}")
        return
    for required in [str(revision), "FULL_PRODUCT_REPOSITORY", "D0C-02", "D0A-01"]:
        if required not in plan_text:
            fail(f"active plan is missing required marker {required!r}")
    if state.get("active_plan") != f"docs/{active_plan}":
        fail("repository-state active_plan disagrees with docs manifest")
    if state.get("active_plan_revision") != revision:
        fail("repository-state revision disagrees with docs manifest")
    if docs_manifest.get("repository_mode") != "FULL_PRODUCT_REPOSITORY":
        fail("repository mode is not FULL_PRODUCT_REPOSITORY")
    if docs_manifest.get("authenticated_agent_listener_implemented") is not True:
        fail("docs manifest does not record the D0C-05 custody implementation")
    if docs_manifest.get("authenticated_agent_listener_enabled") is not False:
        fail("the product Agent listener must remain disabled before the D1/D3 gate")
    if docs_manifest.get("agent_port_enable_marker_shipped") is not False:
        fail("the product must not ship the AgentPort enable marker")
    custody = load_json(ROOT / "contracts/agent-port-custody.v1.json")
    if custody.get("status") != "HOST_VALIDATED_DEFAULT_DISABLED_NO_PRODUCT_LISTENER":
        fail("D0C-05 custody contract is not host validated")
    activation = custody.get("activation", {})
    if activation.get("enabled_by_default") is not False:
        fail("D0C-05 custody enables the socket by default")
    if activation.get("marker_shipped") is not False:
        fail("D0C-05 custody ships the enable marker")
    if activation.get("tcp_listener") is not False:
        fail("D0C-05 custody exposes TCP")
    custody_validation = custody.get("host_validation", {})
    custody_evidence = load_json(
        ROOT / "docs/evidence/generated/d0c05-rust193-host-result.json"
    )
    custody_current = (
        custody.get("evidence_lifecycle") in (None, "CURRENT")
        and custody_validation.get("evidence_lifecycle") in (None, "CURRENT")
        and custody_validation.get("evidence_freshness") in (None, "CURRENT")
        and custody_validation.get("merge_ready") is True
        and custody_evidence.get("evidence_lifecycle") in (None, "CURRENT")
        and custody_evidence.get("evidence_freshness") in (None, "CURRENT")
        and custody_evidence.get("merge_ready") is True
    )
    if custody_current:
        if custody_validation.get("validated_source_head") != custody_evidence.get(
            "validated_source_head"
        ):
            fail("D0C-05 custody and host evidence heads disagree")
    else:
        if custody.get("evidence_lifecycle") != D0C05_EVIDENCE_LIFECYCLE:
            fail("stale D0C-05 custody must declare its evidence lifecycle")
        if custody_validation.get("evidence_lifecycle") != D0C05_EVIDENCE_LIFECYCLE:
            fail("stale D0C-05 host validation must declare its evidence lifecycle")
        if custody_validation.get("evidence_freshness") != D0C05_EVIDENCE_FRESHNESS:
            fail("stale D0C-05 host validation must declare evidence freshness")
        if custody_validation.get("merge_ready") is not False:
            fail("stale D0C-05 host validation must clear merge_ready")
        if custody_evidence.get("evidence_lifecycle") != D0C05_EVIDENCE_LIFECYCLE:
            fail("stale D0C-05 machine evidence must declare its evidence lifecycle")
        if custody_evidence.get("evidence_freshness") != D0C05_EVIDENCE_FRESHNESS:
            fail("stale D0C-05 machine evidence must declare evidence freshness")
        if custody_evidence.get("merge_ready") is not False:
            fail("stale D0C-05 machine evidence must clear merge_ready")
        stale_reason = custody_validation.get("stale_reason")
        evidence_reason = custody_evidence.get("stale_reason")
        for label, reason in (
            ("contract", stale_reason),
            ("machine evidence", evidence_reason),
        ):
            if not isinstance(reason, str) or any(
                marker not in reason for marker in D0C05_STALE_REASON_MARKERS
            ):
                fail(
                    f"stale D0C-05 {label} must carry the actionable exact-head "
                    "rerun reason"
                )
        if custody_validation.get("validated_source_head") != D0C05_HISTORICAL_HEAD:
            fail("D0C-05 stale contract host head drifted from the recorded result")
        if custody_evidence.get("validated_source_head") != D0C05_HISTORICAL_HEAD:
            fail("D0C-05 stale machine evidence head drifted from the recorded result")
    if docs_manifest.get("agent_port_systemd_custody_exact_head_rust_validation") is not custody_current:
        fail(
            "docs manifest D0C-05 custody exact-head flag disagrees with host "
            "evidence freshness"
        )
    if docs_manifest.get("agent_port_systemd_custody_host_evidence_freshness") != (
        "CURRENT" if custody_current else D0C05_EVIDENCE_FRESHNESS
    ):
        fail("docs manifest D0C-05 custody evidence freshness is inconsistent")
    expected_custody_lifecycle = (
        "CURRENT" if custody_current else D0C05_EVIDENCE_LIFECYCLE
    )
    expected_custody_freshness = "CURRENT" if custody_current else D0C05_EVIDENCE_FRESHNESS
    expected_custody_merge_ready = custody_current
    docs_custody_rows = [
        entry
        for entry in docs_manifest.get("implementation_checkpoints", [])
        if isinstance(entry, dict) and entry.get("id") == "TOS-D0C-05"
    ]
    repository_custody_rows = [
        entry
        for entry in state.get("host_validated_work_packages", [])
        if isinstance(entry, dict) and entry.get("id") == "D0C-05"
    ]
    if len(docs_custody_rows) != 1:
        fail("docs manifest must contain exactly one TOS-D0C-05 checkpoint")
    if len(repository_custody_rows) != 1:
        fail("repository-state must contain exactly one D0C-05 evidence entry")
    for label, row in (
        ("docs manifest TOS-D0C-05", docs_custody_rows[0] if docs_custody_rows else None),
        ("repository-state D0C-05", repository_custody_rows[0] if repository_custody_rows else None),
    ):
        if row is None:
            continue
        if row.get("evidence_lifecycle") != expected_custody_lifecycle:
            fail(f"{label} evidence lifecycle is inconsistent")
        if row.get("evidence_freshness") != expected_custody_freshness:
            fail(f"{label} evidence freshness is inconsistent")
        if row.get("merge_ready") is not expected_custody_merge_ready:
            fail(f"{label} merge_ready is inconsistent")
        if not custody_current:
            reason = row.get("stale_reason")
            if not isinstance(reason, str) or any(
                marker not in reason for marker in D0C05_STALE_REASON_MARKERS
            ):
                fail(f"{label} lacks an actionable exact-head rerun reason")
    if docs_manifest.get("transport_core_source_present") is not True:
        fail("docs manifest does not record the D0C-02 transport source")
    transport_evidence = load_json(
        ROOT / "docs/evidence/generated/d0c02-rust193-host-result.json"
    )
    transport_claim = transport_evidence.get("claim", {})
    transport_contract = load_json(ROOT / "contracts/agent-transport.v1.json")
    transport_validation = transport_contract.get("validation", {})
    transport_current = (
        transport_evidence.get("status") == "PASS_HOST_VALIDATED_NO_LISTENER"
        and transport_claim.get("merge_ready") is True
        and transport_evidence.get("evidence_lifecycle") in (None, "CURRENT")
        and transport_evidence.get("evidence_freshness") in (None, "CURRENT")
    )
    transport_contract_current = (
        transport_contract.get("status") == "HOST_VALIDATED_NO_LISTENER"
        and transport_contract.get("evidence_lifecycle") in (None, "CURRENT")
        and transport_contract.get("evidence_freshness") in (None, "CURRENT")
        and transport_contract.get("merge_ready") in (None, True)
        and transport_validation.get("merge_ready") is True
        and transport_validation.get("evidence_freshness") in (None, "CURRENT")
    )
    if transport_contract_current is not transport_current:
        fail(
            "D0C-02 transport contract status disagrees with the host evidence "
            "freshness"
        )
    if transport_current:
        if transport_claim.get("evidence_freshness") not in (None, "CURRENT"):
            fail("current D0C-02 evidence carries a non-current claim freshness")
    else:
        if transport_contract.get("status") != "HOST_VALIDATED_NO_LISTENER":
            fail(
                "stale D0C-02 evidence must retain the HOST_VALIDATED_NO_LISTENER "
                "capability status"
            )
        if transport_contract.get("evidence_lifecycle") != D0C05_EVIDENCE_LIFECYCLE:
            fail("stale D0C-02 contract must declare its exact-head rerun lifecycle")
        if transport_contract.get("evidence_freshness") != D0C05_EVIDENCE_FRESHNESS:
            fail("stale D0C-02 contract must declare top-level evidence freshness")
        if transport_contract.get("merge_ready") is not False:
            fail("stale D0C-02 contract must clear top-level merge_ready")
        if transport_validation.get("evidence_freshness") != "STALE_EVIDENCE":
            fail("stale D0C-02 evidence must set contract evidence_freshness")
        if transport_validation.get("merge_ready") is not False:
            fail("stale D0C-02 evidence must clear contract merge_ready")
        if transport_claim.get("evidence_freshness") != "STALE_EVIDENCE":
            fail("stale D0C-02 evidence must set the generated claim freshness")
        if transport_claim.get("merge_ready") is not False:
            fail("stale D0C-02 evidence must clear generated claim merge_ready")
        stale_reason = transport_validation.get("stale_reason")
        candidate_head = transport_evidence.get("candidate_head")
        if (
            not isinstance(stale_reason, str)
            or not isinstance(candidate_head, str)
            or candidate_head not in stale_reason
            or "exact candidate head" not in stale_reason
        ):
            fail("stale D0C-02 evidence must carry an actionable exact-head reason")
    if docs_manifest.get("transport_exact_head_rust_validation") is not transport_current:
        fail(
            "docs manifest transport exact-head flag disagrees with the "
            "D0C-02 host evidence freshness"
        )
    if docs_manifest.get("transport_host_evidence_freshness") != (
        "CURRENT" if transport_current else "STALE_EVIDENCE"
    ):
        fail("docs manifest transport evidence freshness is inconsistent")
    codec_contract = load_json(ROOT / "contracts/browser-codec.v1.json")
    codec_validation = codec_contract.get("validation", {})
    codec_current = (
        codec_contract.get("status") == "HOST_VALIDATED_RUST_1_93_NO_DISPATCH"
        and codec_contract.get("evidence_lifecycle") in (None, "CURRENT")
        and codec_contract.get("evidence_freshness") in (None, "CURRENT")
        and codec_contract.get("merge_ready") in (None, True)
        and codec_validation.get("merge_ready") is True
        and codec_validation.get("evidence_freshness") in (None, "CURRENT")
    )
    if docs_manifest.get("browser_codec_exact_head_rust_validation") is not codec_current:
        fail(
            "docs manifest browser codec exact-head flag disagrees with the "
            "codec contract evidence freshness"
        )
    if docs_manifest.get("browser_codec_host_evidence_freshness") != (
        "CURRENT" if codec_current else "STALE_EVIDENCE"
    ):
        fail("docs manifest browser codec evidence freshness is inconsistent")
    if docs_manifest.get("browser_codec_source_audit") is not True:
        fail("docs manifest does not record the current browser codec source audit")
    agent_port_contract = load_json(ROOT / "contracts/agent-port-bridge.v1.json")
    agent_port_validation = agent_port_contract.get("validation", {})
    agent_port_current = (
        agent_port_contract.get("status") == "HOST_VALIDATED_NO_LISTENER_NO_BROWSER_ACTOR"
        and agent_port_validation.get("merge_ready") is True
        and agent_port_validation.get("evidence_freshness") in (None, "CURRENT")
    )
    if docs_manifest.get("agent_port_exact_head_rust_validation") is not agent_port_current:
        fail(
            "docs manifest AgentPort exact-head flag disagrees with the "
            "AgentPort bridge contract evidence freshness"
        )
    if docs_manifest.get("agent_port_host_evidence_freshness") != (
        "CURRENT" if agent_port_current else "STALE_EVIDENCE"
    ):
        fail("docs manifest AgentPort evidence freshness is inconsistent")
    for path in [
        ROOT / "README.md",
        ROOT / "docs/CURRENT_STATE.md",
        plan_path,
        ROOT / "manifests/repository-state.json",
    ]:
        try:
            text = _read_text_nofollow(path)
        except (OSError, UnicodeError) as error:
            fail(f"normative file is missing or unsafe: {_display_path(path)}: {error}")
            continue
        if "/data/toshiba-dev/" in text:
            fail(
                "normative active file contains a local absolute source path: "
                f"{path.relative_to(ROOT)}"
            )


def dependency_spec_version(specification: object) -> str | None:
    if isinstance(specification, str):
        return specification
    if isinstance(specification, dict):
        version = specification.get("version")
        return version if isinstance(version, str) else None
    return None


def index_lock_packages(lock: object) -> dict[str, list[dict[str, Any]]]:
    """Index lockfile packages without folding distinct package records.

    Cargo identifies a package by ``(name, version, source)``.  Keeping only
    ``{name: package}`` (or even ``{(name, version): package}``) silently drops
    records when a crate is present at multiple versions or sources.  That is
    unsafe for a repository validator: an attacker could append a duplicate
    record with a different dependency list/checksum and rely on whichever
    record happens to win the dictionary comprehension.  Preserve every
    record and fail closed on duplicate identities or malformed identity
    fields.  Callers can then apply their own policy for source/versions.
    """

    if not isinstance(lock, dict):
        raise AssertionError("Cargo.lock root must be an object")
    entries = lock.get("package")
    if not isinstance(entries, list):
        raise AssertionError("Cargo.lock package list is missing")

    by_name: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str, str | None]] = set()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            raise AssertionError(f"Cargo.lock package {index} is not an object")
        name = entry.get("name")
        version = entry.get("version")
        source = entry.get("source")
        if not isinstance(name, str) or not name:
            raise AssertionError(f"Cargo.lock package {index} has invalid name")
        if not isinstance(version, str) or not version:
            raise AssertionError(f"Cargo.lock package {name} has invalid version")
        if source is not None and (not isinstance(source, str) or not source):
            raise AssertionError(f"Cargo.lock package {name} has invalid source")
        identity = (name, version, source)
        if identity in seen:
            raise AssertionError(
                "Cargo.lock contains duplicate package identity "
                f"(name={name!r}, version={version!r}, source={source!r})"
            )
        seen.add(identity)
        by_name.setdefault(name, []).append(entry)
    return by_name


def check_workspace_and_lock() -> None:
    cargo = load_toml(ROOT / "Cargo.toml")
    workspace = cargo.get("workspace", {})
    members = workspace.get("members", [])
    defaults = workspace.get("default-members", [])
    if members != EXPECTED_WORKSPACE_MEMBERS:
        fail(f"workspace members changed without validator update: {members!r}")
    if defaults != EXPECTED_WORKSPACE_MEMBERS:
        fail(f"default workspace members changed without validator update: {defaults!r}")

    boundary = load_json(ROOT / "manifests/product-boundary.json")
    graph = boundary.get("desktop_default_graph", {})
    forbidden_names = set(graph.get("forbidden_dependency_names", []))
    forbidden_fragments = tuple(graph.get("forbidden_path_fragments", []))
    workspace_names: set[str] = set()

    for member in EXPECTED_WORKSPACE_MEMBERS:
        manifest_path = ROOT / member / "Cargo.toml"
        if not manifest_path.is_file() or manifest_path.is_symlink():
            # Keep the explicit diagnostic in addition to the safe loader's
            # error so callers can distinguish a missing workspace member.
            fail(f"workspace member Cargo.toml is missing or unsafe: {member}")
            continue
        manifest = load_toml(manifest_path)
        package = manifest.get("package", {})
        name = package.get("name")
        if not isinstance(name, str):
            fail(f"workspace member has no package name: {member}")
        else:
            workspace_names.add(name)
        for section_name in ("dependencies", "dev-dependencies", "build-dependencies"):
            section = manifest.get(section_name, {})
            if not isinstance(section, dict):
                continue
            for dependency_name, specification in section.items():
                if dependency_name in forbidden_names:
                    fail(
                        f"forbidden mobile dependency {dependency_name} in "
                        f"{manifest_path.relative_to(ROOT)}"
                    )
                if isinstance(specification, dict):
                    path_value = specification.get("path")
                    if "path" in specification:
                        safe_workspace_dependency_path(
                            path_value,
                            manifest_path=manifest_path,
                            label=(
                                "workspace path dependency "
                                f"{dependency_name} in {manifest_path.relative_to(ROOT)}"
                            ),
                        )
                    if isinstance(path_value, str) and any(
                        fragment in path_value for fragment in forbidden_fragments
                    ):
                        fail(
                            f"forbidden mobile path dependency {path_value} in "
                            f"{manifest_path.relative_to(ROOT)}"
                        )

    allowlist = load_json(ROOT / "manifests/cargo-external-allowlist.json")
    allowed_entries = allowlist.get("packages", [])
    allowed: dict[tuple[str, str], str] = {}
    for entry in allowed_entries:
        if not isinstance(entry, dict):
            fail("cargo external allowlist contains a non-object entry")
            continue
        name = entry.get("name")
        version = entry.get("version")
        checksum = entry.get("checksum")
        if not all(isinstance(value, str) for value in (name, version, checksum)):
            fail("cargo external allowlist entry is incomplete")
            continue
        if not is_sha256_hex(checksum):
            fail(
                "cargo external allowlist checksum must be exactly 64 lowercase "
                f"hex characters: {name} {version}"
            )
        key = (name, version)
        if key in allowed:
            fail(f"duplicate cargo allowlist entry {name} {version}")
        allowed[key] = checksum

    direct = allowlist.get("direct_dependencies", {})
    if not isinstance(direct, dict):
        fail("cargo external allowlist direct_dependencies must be an object")
        direct = {}
    for member, expected_dependencies in direct.items():
        member_manifest = safe_relative_path(
            f"{member}/Cargo.toml" if isinstance(member, str) else member,
            base=ROOT,
            label="cargo direct dependency manifest",
        )
        if member_manifest is None:
            continue
        if not isinstance(member, str) or member not in EXPECTED_WORKSPACE_MEMBERS:
            fail(f"cargo direct dependency member is not a workspace member: {member!r}")
            continue
        if not member_manifest.is_file() or member_manifest.is_symlink():
            fail(f"cargo direct dependency manifest is missing or unsafe: {member}/Cargo.toml")
            continue
        if not isinstance(expected_dependencies, dict):
            fail(f"cargo direct dependency allowlist is not an object: {member}")
            continue
        manifest = load_toml(member_manifest)
        actual_dependencies = manifest.get("dependencies", {})
        for name, exact_version in expected_dependencies.items():
            if not isinstance(name, str) or not isinstance(exact_version, str):
                fail(f"cargo direct dependency entry is malformed: {member}")
                continue
            actual = dependency_spec_version(actual_dependencies.get(name))
            if actual != exact_version:
                fail(
                    f"{member} dependency {name} must be pinned to {exact_version}, "
                    f"found {actual!r}"
                )

    lock = load_toml(ROOT / "Cargo.lock")
    try:
        packages_by_name = index_lock_packages(lock)
    except AssertionError as error:
        # Keep this validator's aggregate-error contract while ensuring a
        # malformed/ambiguous lockfile can never be treated as an empty one.
        fail(str(error))
        return
    lock_packages = [
        package for packages in packages_by_name.values() for package in packages
    ]
    locked_workspace: set[str] = set()
    locked_external: dict[tuple[str, str], str] = {}
    all_names: set[str] = set()
    workspace_versions: dict[str, str] = {}

    for package in lock_packages:
        if not isinstance(package, dict):
            fail("Cargo.lock contains a non-object package entry")
            continue
        name = package.get("name")
        version = package.get("version")
        source = package.get("source")
        checksum = package.get("checksum")
        if not isinstance(name, str) or not isinstance(version, str):
            fail("Cargo.lock package is missing name/version")
            continue
        all_names.add(name)
        if source is None:
            previous_version = workspace_versions.get(name)
            if previous_version is not None:
                fail(
                    "Cargo.lock contains multiple local package records for "
                    f"{name!r}: versions {previous_version!r} and {version!r}"
                )
            else:
                workspace_versions[name] = version
            locked_workspace.add(name)
            continue
        if source != "registry+https://github.com/rust-lang/crates.io-index":
            fail(f"non-registry Cargo dependency is forbidden: {name} {version} {source}")
            continue
        if not isinstance(checksum, str):
            fail(f"registry package lacks checksum: {name} {version}")
            continue
        if not is_sha256_hex(checksum):
            fail(
                "Cargo.lock registry checksum must be exactly 64 lowercase "
                f"hex characters: {name} {version}"
            )
            continue
        key = (name, version)
        # index_lock_packages has already rejected duplicate complete
        # identities.  This map is deliberately keyed by (name, version)
        # because this repository permits only the single crates.io source for
        # external packages; retain the explicit collision check in case that
        # policy changes later.
        if key in locked_external:
            fail(f"duplicate Cargo.lock package {name} {version}")
        locked_external[key] = checksum

    if locked_workspace != workspace_names:
        fail(
            f"Cargo.lock workspace package set {sorted(locked_workspace)} differs from "
            f"workspace package set {sorted(workspace_names)}"
        )
    if locked_external != allowed:
        missing = sorted(set(allowed) - set(locked_external))
        unexpected = sorted(set(locked_external) - set(allowed))
        wrong = sorted(
            key
            for key in set(allowed) & set(locked_external)
            if allowed[key] != locked_external[key]
        )
        fail(
            "Cargo.lock external closure disagrees with allowlist: "
            f"missing={missing}, unexpected={unexpected}, checksum_mismatch={wrong}"
        )

    for package in lock_packages:
        if not isinstance(package, dict):
            continue
        for dependency in package.get("dependencies", []):
            if not isinstance(dependency, str):
                fail("Cargo.lock dependency reference is not a string")
                continue
            dependency_name = dependency.rsplit(" ", 1)[0]
            if dependency_name not in all_names:
                fail(
                    f"Cargo.lock dependency {dependency!r} from {package.get('name')} "
                    "does not resolve"
                )


def check_toolchain() -> None:
    toolchain = load_toml(ROOT / "rust-toolchain.toml").get("toolchain", {})
    lock = load_json(ROOT / "manifests/rust-toolchain.lock.json")
    if toolchain.get("channel") != lock.get("channel"):
        fail("rust-toolchain.toml channel disagrees with lock manifest")
    if sorted(toolchain.get("components", [])) != sorted(lock.get("components", [])):
        fail("rust toolchain components disagree with lock manifest")


def check_contract_alignment() -> None:
    errors = load_json(ROOT / "contracts/error-codes.v1.json")
    codes = [
        entry.get("code")
        for entry in errors.get("codes", [])
        if isinstance(entry, dict)
    ]
    if len(codes) != len(set(codes)):
        fail("duplicate error codes")
    try:
        rust_source = _read_text_nofollow(
            ROOT / "crates/hepta-browser-contracts/src/lib.rs"
        )
    except (OSError, UnicodeError) as error:
        fail(f"browser contracts source is missing or unsafe: {error}")
        rust_source = ""
    for code in codes:
        if not isinstance(code, str) or f'"{code}"' not in rust_source:
            fail(f"error code {code!r} is not represented in Rust BrowserErrorCode")

    browser_schema = load_json(ROOT / "contracts/browser-api.v1.schema.json")
    operation_definitions = {
        name
        for name in browser_schema.get("$defs", {})
        if name
        in {
            "health",
            "session_create",
            "session_snapshot",
            "session_close",
            "page_navigate",
            "page_observe",
            "page_act",
            "page_wait",
            "page_extract",
        }
    }
    for golden in sorted((ROOT / "contracts/golden").glob("*.request.json")):
        request = load_json(golden)
        if request.get("protocol") != "trillionnium.desktop.browser-api.v1":
            fail(f"golden request has wrong protocol: {golden.relative_to(ROOT)}")
        operation_type = request.get("operation", {}).get("type")
        if operation_type not in operation_definitions:
            fail(
                f"golden request uses unknown operation {operation_type!r}: "
                f"{golden.relative_to(ROOT)}"
            )

    transport = load_json(ROOT / "contracts/agent-transport.v1.json")
    try:
        transport_source = _read_text_nofollow(
            ROOT / "crates/hepta-agent-transport/src/lib.rs"
        )
    except (OSError, UnicodeError) as error:
        fail(f"transport source is missing or unsafe: {error}")
        transport_source = ""
    expected_markers = {
        f'pub const PROTOCOL_MAGIC: [u8; 8] = *b"{transport.get("protocol_magic_ascii")}";',
        f'pub const PROTOCOL_VERSION: u16 = {transport.get("protocol_version")};',
        f'pub const HEADER_BYTES: usize = {transport.get("header_bytes")};',
        f'pub const MAX_PAYLOAD_BYTES: usize = {transport.get("max_payload_bytes"):_};',
    }
    for marker in expected_markers:
        if marker not in transport_source:
            fail(f"transport contract/source mismatch: missing {marker!r}")
    for forbidden in ("UnixListener", "TcpListener", "TcpStream"):
        if forbidden in transport_source:
            fail(f"D0C-02 transport core must not contain {forbidden}")
    if "libc::getsockopt" not in transport_source or "SO_PEERCRED" not in transport_source:
        fail("transport source does not implement kernel peer-credential extraction")
    if "// SAFETY:" not in transport_source:
        fail("transport unsafe FFI lacks an adjacent safety explanation")
    transport_evidence = load_json(
        ROOT / "docs/evidence/generated/d0c02-rust193-host-result.json"
    )
    if transport_evidence.get("status") != "PASS_HOST_VALIDATED_NO_LISTENER":
        fail("D0C-02 machine evidence is not host validated")
    authority = transport_evidence.get("authority", {})
    if authority.get("listener_created") is not False:
        fail("D0C-02 machine evidence claims a product listener")
    if authority.get("browser_actor_called") is not False:
        fail("D0C-02 machine evidence claims BrowserActor dispatch")
    if authority.get("servo_called") is not False:
        fail("D0C-02 machine evidence claims Servo execution")
    if authority.get("external_effect_authorized") is not False:
        fail("D0C-02 machine evidence claims effect authority")


def check_filesystem_shape() -> None:
    for path in ROOT.rglob("*"):
        if path.is_symlink():
            fail(
                f"symlinks are forbidden in the product baseline: "
                f"{path.relative_to(ROOT)}"
            )
    for relative in REQUIRED_PATHS:
        try:
            _read_bytes_nofollow(ROOT / relative)
        except (OSError, UnicodeError) as error:
            fail(f"required repository file is missing or unsafe: {relative}: {error}")
    for forbidden in (
        ".github/workflows/materialize-d0c02.yml",
        ".github/workflows/verify-and-merge-d0c02.yml",
    ):
        if (ROOT / forbidden).exists():
            fail(f"one-shot materialization workflow must not ship: {forbidden}")


def main() -> int:
    check_json_files()
    check_d0c06_generated_evidence()
    check_plan_and_manifests()
    check_workspace_and_lock()
    check_toolchain()
    check_contract_alignment()
    check_filesystem_shape()
    if ERRORS:
        for error in ERRORS:
            print(f"ERROR: {error}", file=sys.stderr)
        print(
            f"repository validation failed with {len(ERRORS)} error(s)",
            file=sys.stderr,
        )
        return 1
    print("repository validation passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
