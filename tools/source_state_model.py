"""Closed model for the repository source-tree workspace inventory.

This inventory says which Cargo packages are present in the current source
object. It does not promote those packages into the integrated runtime state.
"""

from __future__ import annotations

import json
import os
import re
import stat
import tomllib
from pathlib import Path
from typing import Any

SOURCE_STATE_PATH = "docs/source-state.v1.json"
SOURCE_STATE_SCHEMA = "trillionnium.desktop.source-state.v1"
MAX_SOURCE_STATE_BYTES = 256 * 1024
EXPECTED_INTEGRATED_MEMBERS = (
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
)


def _closed(value: Any, expected: set[str], label: str, errors: list[str]) -> bool:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return False
    actual = set(value)
    if actual != expected:
        errors.append(
            f"{label} keys are not closed-record compliant; "
            f"missing={sorted(expected - actual)}, unknown={sorted(actual - expected)}"
        )
        return False
    return True


def validate_record(record: Any) -> list[str]:
    errors: list[str] = []
    if not _closed(
        record,
        {"schema", "workspace_members", "claim_ceiling"},
        "source_state",
        errors,
    ):
        return errors
    assert isinstance(record, dict)
    if record["schema"] != SOURCE_STATE_SCHEMA:
        errors.append(f"source_state schema must be {SOURCE_STATE_SCHEMA!r}")
    if record["claim_ceiling"] != "repository_source_tree_only":
        errors.append("source_state claim_ceiling must be 'repository_source_tree_only'")

    members = record["workspace_members"]
    if not isinstance(members, list) or not members:
        errors.append("source_state workspace_members must be a non-empty list")
        return errors
    if any(
        not isinstance(item, str)
        or re.fullmatch(r"(?:apps|crates)/[a-z][a-z0-9-]*", item) is None
        for item in members
    ):
        errors.append("source_state workspace_members contains an invalid repository path")
        return errors
    if len(members) != len(set(members)):
        errors.append("source_state workspace_members contains duplicates")
    if len(members) > 128:
        errors.append("source_state workspace_members exceeds the bounded member count")

    cursor = 0
    for member in members:
        if (
            cursor < len(EXPECTED_INTEGRATED_MEMBERS)
            and member == EXPECTED_INTEGRATED_MEMBERS[cursor]
        ):
            cursor += 1
    if cursor != len(EXPECTED_INTEGRATED_MEMBERS):
        errors.append(
            "source_state workspace_members must retain every integrated member "
            "in canonical relative order"
        )
    return errors


def read_repository_text(root: Path, relative: str) -> str:
    """Read bounded regular repository input without following any child symlink."""
    parts = relative.split("/")
    if (
        not relative or relative.startswith("/") or "\\" in relative
        or any(part in {"", ".", ".."} for part in parts)
    ):
        raise ValueError("invalid repository input path")
    directory = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for component in parts[:-1]:
            child = os.open(component, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                            | os.O_CLOEXEC, dir_fd=directory)
            os.close(directory)
            directory = child
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                     | os.O_CLOEXEC, dir_fd=directory)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_SOURCE_STATE_BYTES:
                raise ValueError(f"repository input must be a bounded regular file: {relative}")
            raw = stream.read(MAX_SOURCE_STATE_BYTES + 1)
            if len(raw) > MAX_SOURCE_STATE_BYTES:
                raise ValueError(f"repository input exceeded byte limit: {relative}")
            return raw.decode("utf-8")
    finally:
        os.close(directory)


def load_record(root: Path) -> tuple[dict[str, Any] | None, list[str]]:

    def reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON key {key!r}")
            result[key] = value
        return result

    try:
        value = json.loads(
            read_repository_text(root, SOURCE_STATE_PATH),
            object_pairs_hook=reject_duplicates,
        )
    except (OSError, UnicodeError, ValueError, RecursionError) as error:
        return None, [f"cannot load source-state inventory: {error}"]
    if not isinstance(value, dict):
        return None, ["source-state inventory must be a JSON object"]
    return value, validate_record(value)


def validate_repository(root: Path) -> list[str]:
    record, errors = load_record(root)
    if record is None:
        return errors
    try:
        members = tomllib.loads(read_repository_text(root, "Cargo.toml"))[
            "workspace"
        ]["members"]
    except (OSError, UnicodeError, KeyError, TypeError, ValueError, RecursionError) as error:
        errors.append(f"cannot read Cargo workspace for source state: {error}")
    else:
        if record.get("workspace_members") != members:
            errors.append("source_state workspace_members differ from Cargo.toml")
    return errors
