"""Shared fail-closed I/O, artifact, and receipt primitives for D3 evidence."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
from typing import Any

from trusted_app_bundle import canonical_json

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "contracts" / "d3-integrated-runtime-evidence.v1.json"
SHA40 = re.compile(r"^[0-9a-f]{40}$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
TOKEN = re.compile(r"^[A-Za-z0-9/][A-Za-z0-9_.:@/-]{0,255}$")
ZERO_SHA256 = "0" * 64
MAX_JSON_BYTES = 8 * 1024 * 1024
MAX_ARTIFACT_BYTES = 256 * 1024 * 1024

def _has_symlink_component(path: Path) -> bool:
    lexical = path if path.is_absolute() else Path.cwd() / path
    current = Path(lexical.anchor)
    for component in lexical.parts:
        if component in {lexical.anchor, "."}:
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
            raise EvidenceError("PATH_COMPONENT_INSPECTION_FAILED", str(current)) from error
        if stat.S_ISLNK(mode):
            return True
    return False


class EvidenceError(ValueError):
    def __init__(self, reason: str, detail: str | None = None) -> None:
        super().__init__(reason if detail is None else f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def _reject_duplicate_members(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise EvidenceError("DUPLICATE_JSON_MEMBER", key)
        result[key] = value
    return result


def _read_regular_file(path: Path, *, maximum: int = MAX_JSON_BYTES) -> bytes:
    if _has_symlink_component(path):
        raise EvidenceError("UNSAFE_FILE_TYPE", str(path))
    try:
        metadata = path.lstat()
    except OSError as error:
        raise EvidenceError("FILE_UNAVAILABLE", str(path)) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise EvidenceError("UNSAFE_FILE_TYPE", str(path))
    if metadata.st_size > maximum:
        raise EvidenceError("FILE_TOO_LARGE", str(path))
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    descriptor: int | None = None
    try:
        descriptor = os.open(path, os.O_RDONLY | nofollow | cloexec)
        current = os.fstat(descriptor)
        if not stat.S_ISREG(current.st_mode):
            raise EvidenceError("UNSAFE_FILE_TYPE", str(path))
        if current.st_size > maximum:
            raise EvidenceError("FILE_TOO_LARGE", str(path))
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
        if len(data) > maximum:
            raise EvidenceError("FILE_TOO_LARGE", str(path))
        return data
    except OSError as error:
        raise EvidenceError("FILE_READ_FAILED", str(path)) from error
    finally:
        if descriptor is not None:
            os.close(descriptor)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(
            _read_regular_file(path), object_pairs_hook=_reject_duplicate_members
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise EvidenceError("INVALID_JSON", str(path)) from error
    if not isinstance(value, dict):
        raise EvidenceError("JSON_OBJECT_REQUIRED", str(path))
    return value


def require_dict(value: Any, reason: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise EvidenceError(reason)
    return value


def require_list(value: Any, reason: str) -> list[Any]:
    if not isinstance(value, list):
        raise EvidenceError(reason)
    return value


def require_bool(value: Any, expected: bool, reason: str) -> None:
    if value is not expected:
        raise EvidenceError(reason)


def require_token(value: Any, reason: str) -> str:
    if not isinstance(value, str) or TOKEN.fullmatch(value) is None:
        raise EvidenceError(reason)
    return value


def require_sha40(value: Any, reason: str, *, nonzero: bool = True) -> str:
    if not isinstance(value, str) or SHA40.fullmatch(value) is None:
        raise EvidenceError(reason)
    if nonzero and value == "0" * 40:
        raise EvidenceError(reason)
    return value


def require_sha256(value: Any, reason: str, *, nonzero: bool = True) -> str:
    if not isinstance(value, str) or SHA256.fullmatch(value) is None:
        raise EvidenceError(reason)
    if nonzero and value == ZERO_SHA256:
        raise EvidenceError(reason)
    return value


def normalize_artifact_path(value: Any) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise EvidenceError("INVALID_ARTIFACT_PATH")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise EvidenceError("INVALID_ARTIFACT_PATH", value)
    normalized = "/".join(path.parts)
    if normalized != value:
        raise EvidenceError("NON_CANONICAL_ARTIFACT_PATH", value)
    return normalized


def sha256_file(path: Path) -> tuple[str, int]:
    data = _read_regular_file(path, maximum=MAX_ARTIFACT_BYTES)
    return hashlib.sha256(data).hexdigest(), len(data)


def enumerate_artifacts(root: Path) -> dict[str, Path]:
    if _has_symlink_component(root):
        raise EvidenceError("UNSAFE_ARTIFACT_ROOT", str(root))
    try:
        metadata = root.lstat()
    except OSError as error:
        raise EvidenceError("ARTIFACT_ROOT_UNAVAILABLE", str(root)) from error
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISDIR(metadata.st_mode):
        raise EvidenceError("UNSAFE_ARTIFACT_ROOT", str(root))
    result: dict[str, Path] = {}
    for current, directories, files in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        for name in directories:
            candidate = current_path / name
            mode = candidate.lstat().st_mode
            if stat.S_ISLNK(mode) or not stat.S_ISDIR(mode):
                raise EvidenceError("UNSAFE_ARTIFACT_DIRECTORY", str(candidate))
        for name in files:
            candidate = current_path / name
            relative = normalize_artifact_path(candidate.relative_to(root).as_posix())
            if relative in result:
                raise EvidenceError("DUPLICATE_ARTIFACT_PATH", relative)
            result[relative] = candidate
    return result


def verify_artifacts(
    evidence: dict[str, Any], contract: dict[str, Any], artifact_root: Path
) -> int:
    declarations = require_list(evidence.get("artifacts"), "ARTIFACT_LIST_REQUIRED")
    declared: dict[str, tuple[str, int]] = {}
    for entry in declarations:
        record = require_dict(entry, "INVALID_ARTIFACT_RECORD")
        if set(record) != {"path", "sha256", "bytes"}:
            raise EvidenceError("INVALID_ARTIFACT_RECORD_SHAPE")
        path = normalize_artifact_path(record.get("path"))
        if path in declared:
            raise EvidenceError("DUPLICATE_ARTIFACT_PATH", path)
        digest = require_sha256(record.get("sha256"), "INVALID_ARTIFACT_SHA256")
        byte_count = record.get("bytes")
        if isinstance(byte_count, bool) or not isinstance(byte_count, int) or byte_count < 0:
            raise EvidenceError("INVALID_ARTIFACT_SIZE", path)
        declared[path] = (digest, byte_count)

    required = set(require_list(contract.get("required_artifacts"), "CONTRACT_ARTIFACTS_REQUIRED"))
    if set(declared) != required:
        raise EvidenceError("ARTIFACT_DECLARATION_SET_MISMATCH")
    actual = enumerate_artifacts(artifact_root)
    if set(actual) != required:
        raise EvidenceError("ARTIFACT_DIRECTORY_SET_MISMATCH")
    for path in sorted(required):
        digest, byte_count = sha256_file(actual[path])
        if (digest, byte_count) != declared[path]:
            raise EvidenceError("ARTIFACT_DIGEST_OR_SIZE_MISMATCH", path)
    return len(actual)


def receipt_record_hash(record: dict[str, Any]) -> str:
    unsigned = dict(record)
    unsigned.pop("record_hash", None)
    return hashlib.sha256(canonical_json(unsigned)).hexdigest()


def build_receipt_chain(operation_id: str, terminal: str) -> dict[str, Any]:
    previous = ZERO_SHA256
    records: list[dict[str, Any]] = []
    for sequence, event in enumerate(("requested", "dispatched", terminal), 1):
        record = {
            "sequence": sequence,
            "operation_id": operation_id,
            "event": event,
            "previous_hash": previous,
            "fsync_committed": True,
        }
        record["record_hash"] = receipt_record_hash(record)
        previous = record["record_hash"]
        records.append(record)
    return {"operation_id": operation_id, "records": records}


def verify_receipt_chain(chain: Any, terminal: str) -> None:
    value = require_dict(chain, "INVALID_RECEIPT_CHAIN")
    operation_id = require_token(value.get("operation_id"), "INVALID_OPERATION_ID")
    records = require_list(value.get("records"), "RECEIPT_RECORDS_REQUIRED")
    if len(records) != 3:
        raise EvidenceError("RECEIPT_RECORD_COUNT_MISMATCH", operation_id)
    expected_events = ["requested", "dispatched", terminal]
    previous = ZERO_SHA256
    for index, item in enumerate(records, 1):
        record = require_dict(item, "INVALID_RECEIPT_RECORD")
        if record.get("sequence") != index:
            raise EvidenceError("RECEIPT_SEQUENCE_MISMATCH", operation_id)
        if record.get("operation_id") != operation_id:
            raise EvidenceError("RECEIPT_OPERATION_MISMATCH", operation_id)
        if record.get("event") != expected_events[index - 1]:
            raise EvidenceError("RECEIPT_EVENT_ORDER_MISMATCH", operation_id)
        if record.get("previous_hash") != previous:
            raise EvidenceError("RECEIPT_PREVIOUS_HASH_MISMATCH", operation_id)
        require_bool(record.get("fsync_committed"), True, "RECEIPT_NOT_FSYNC_COMMITTED")
        actual_hash = require_sha256(record.get("record_hash"), "INVALID_RECEIPT_HASH")
        if actual_hash != receipt_record_hash(record):
            raise EvidenceError("RECEIPT_HASH_MISMATCH", operation_id)
        previous = actual_hash


def verify_receipts(evidence: dict[str, Any], contract: dict[str, Any]) -> int:
    receipts = require_dict(evidence.get("receipts"), "RECEIPTS_REQUIRED")
    require_bool(
        receipts.get("requested_fsync_before_dispatch"),
        True,
        "REQUESTED_NOT_DURABLE_BEFORE_DISPATCH",
    )
    require_bool(
        receipts.get("terminal_fsync_before_response"),
        True,
        "TERMINAL_NOT_DURABLE_BEFORE_RESPONSE",
    )
    require_bool(receipts.get("automatic_replay"), False, "AUTOMATIC_REPLAY_FORBIDDEN")
    require_bool(
        receipts.get("indeterminate_requires_reconciliation"),
        True,
        "INDETERMINATE_RECONCILIATION_REQUIRED",
    )
    chains = require_list(receipts.get("chains"), "RECEIPT_CHAINS_REQUIRED")
    terminals = require_list(
        contract.get("required_receipt_terminals"), "CONTRACT_TERMINALS_REQUIRED"
    )
    if len(chains) != len(terminals):
        raise EvidenceError("RECEIPT_CHAIN_COUNT_MISMATCH")
    by_terminal: dict[str, Any] = {}
    for chain in chains:
        value = require_dict(chain, "INVALID_RECEIPT_CHAIN")
        records = require_list(value.get("records"), "RECEIPT_RECORDS_REQUIRED")
        if len(records) != 3 or not isinstance(records[-1], dict):
            raise EvidenceError("INVALID_RECEIPT_CHAIN")
        terminal = records[-1].get("event")
        if not isinstance(terminal, str) or terminal in by_terminal:
            raise EvidenceError("DUPLICATE_OR_INVALID_RECEIPT_TERMINAL")
        by_terminal[terminal] = chain
    if set(by_terminal) != set(terminals):
        raise EvidenceError("RECEIPT_TERMINAL_SET_MISMATCH")
    for terminal in terminals:
        verify_receipt_chain(by_terminal[terminal], terminal)
    return len(chains)


