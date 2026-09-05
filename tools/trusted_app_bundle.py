#!/usr/bin/env python3
"""Offline reference verifier for D5 trusted application bundles.

The implementation uses only the Python standard library. It includes a small
RFC 8032 Ed25519 reference implementation so the gate does not acquire network
or package-manager authority. The signing helper exists only for deterministic
fixtures; product signing-key custody is explicitly outside this package.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import os
import re
import stat
import sys
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "contracts" / "trusted-app-bundle.v1.json"

Q = 2**255 - 19
L = 2**252 + 27742317777372353535851937790883648493
D = (-121665 * pow(121666, Q - 2, Q)) % Q
I = pow(2, (Q - 1) // 4, Q)
IDENTITY = (0, 1)
DNS_LABEL = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\Z")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
MAX_MANIFEST_BYTES = 4 * 1024 * 1024


class VerificationError(ValueError):
    """Fail-closed bundle verification error with a stable reason code."""

    def __init__(self, reason: str, detail: str | None = None) -> None:
        super().__init__(reason if detail is None else f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inv(value: int) -> int:
    return pow(value, Q - 2, Q)


def x_recover(y: int) -> int:
    xx = ((y * y - 1) * inv(D * y * y + 1)) % Q
    x = pow(xx, (Q + 3) // 8, Q)
    if (x * x - xx) % Q != 0:
        x = (x * I) % Q
    if (x * x - xx) % Q != 0:
        raise VerificationError("ED25519_POINT_NOT_ON_CURVE")
    return x


def point_add(left: tuple[int, int], right: tuple[int, int]) -> tuple[int, int]:
    x1, y1 = left
    x2, y2 = right
    product = (D * x1 * x2 * y1 * y2) % Q
    x3 = ((x1 * y2 + x2 * y1) * inv(1 + product)) % Q
    y3 = ((y1 * y2 + x1 * x2) * inv(1 - product)) % Q
    return x3, y3


def scalar_mult(point: tuple[int, int], scalar: int) -> tuple[int, int]:
    result = IDENTITY
    addend = point
    value = scalar
    while value:
        if value & 1:
            result = point_add(result, addend)
        addend = point_add(addend, addend)
        value >>= 1
    return result


BASE_Y = (4 * inv(5)) % Q
BASE_X = x_recover(BASE_Y)
if BASE_X & 1:
    BASE_X = Q - BASE_X
BASE = (BASE_X, BASE_Y)


def encode_point(point: tuple[int, int]) -> bytes:
    x, y = point
    return int(y | ((x & 1) << 255)).to_bytes(32, "little")


def decode_point(encoded: bytes) -> tuple[int, int]:
    if len(encoded) != 32:
        raise VerificationError("ED25519_POINT_LENGTH")
    value = int.from_bytes(encoded, "little")
    y = value & ((1 << 255) - 1)
    sign_bit = value >> 255
    if y >= Q:
        raise VerificationError("ED25519_NON_CANONICAL_Y")
    x = x_recover(y)
    if (x & 1) != sign_bit:
        x = Q - x
    point = (x, y)
    if (-x * x + y * y - 1 - D * x * x * y * y) % Q != 0:
        raise VerificationError("ED25519_POINT_NOT_ON_CURVE")
    if encode_point(point) != encoded:
        raise VerificationError("ED25519_NON_CANONICAL_POINT")
    return point


def ed25519_public_from_seed(seed: bytes) -> bytes:
    if len(seed) != 32:
        raise ValueError("Ed25519 fixture seed must contain 32 bytes")
    expanded = bytearray(hashlib.sha512(seed).digest())
    scalar_bytes = expanded[:32]
    scalar_bytes[0] &= 248
    scalar_bytes[31] &= 63
    scalar_bytes[31] |= 64
    scalar = int.from_bytes(scalar_bytes, "little")
    return encode_point(scalar_mult(BASE, scalar))


def ed25519_sign_fixture(seed: bytes, message: bytes) -> bytes:
    """Deterministic RFC 8032 signing helper for non-production test fixtures."""
    if len(seed) != 32:
        raise ValueError("Ed25519 fixture seed must contain 32 bytes")
    expanded = bytearray(hashlib.sha512(seed).digest())
    scalar_bytes = expanded[:32]
    scalar_bytes[0] &= 248
    scalar_bytes[31] &= 63
    scalar_bytes[31] |= 64
    scalar = int.from_bytes(scalar_bytes, "little")
    prefix = bytes(expanded[32:])
    public_key = encode_point(scalar_mult(BASE, scalar))
    nonce = int.from_bytes(hashlib.sha512(prefix + message).digest(), "little") % L
    encoded_r = encode_point(scalar_mult(BASE, nonce))
    challenge = int.from_bytes(
        hashlib.sha512(encoded_r + public_key + message).digest(), "little"
    ) % L
    encoded_s = ((nonce + challenge * scalar) % L).to_bytes(32, "little")
    return encoded_r + encoded_s


def ed25519_verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    try:
        if len(public_key) != 32 or len(signature) != 64:
            return False
        encoded_r = signature[:32]
        scalar_s = int.from_bytes(signature[32:], "little")
        if scalar_s >= L:
            return False
        public_point = decode_point(public_key)
        r_point = decode_point(encoded_r)
        if public_point == IDENTITY or r_point == IDENTITY:
            return False
        if scalar_mult(public_point, L) != IDENTITY:
            return False
        if scalar_mult(r_point, L) != IDENTITY:
            return False
        challenge = int.from_bytes(
            hashlib.sha512(encoded_r + public_key + message).digest(), "little"
        ) % L
        left = scalar_mult(BASE, scalar_s)
        right = point_add(r_point, scalar_mult(public_point, challenge))
        return encode_point(left) == encode_point(right)
    except VerificationError:
        return False


def decode_base64(value: Any, *, expected_bytes: int, reason: str) -> bytes:
    if not isinstance(value, str):
        raise VerificationError(reason, "base64 string required")
    try:
        decoded = base64.b64decode(value, validate=True)
    except (ValueError, base64.binascii.Error) as error:
        raise VerificationError(reason, "invalid base64") from error
    if len(decoded) != expected_bytes:
        raise VerificationError(reason, f"expected {expected_bytes} bytes")
    return decoded


def normalize_path(value: Any, contract: dict[str, Any]) -> str:
    if not isinstance(value, str) or not value:
        raise VerificationError("INVALID_CONTENT_PATH", "non-empty string required")
    if "\\" in value or "\x00" in value:
        raise VerificationError("INVALID_CONTENT_PATH", value)
    if len(value.encode("utf-8")) > int(contract["path_policy"]["maximum_path_bytes"]):
        raise VerificationError("CONTENT_PATH_TOO_LONG", value)
    path = PurePosixPath(value)
    if path.is_absolute():
        raise VerificationError("ABSOLUTE_CONTENT_PATH", value)
    parts = path.parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise VerificationError("CONTENT_PATH_TRAVERSAL", value)
    normalized = "/".join(parts)
    if normalized != value:
        raise VerificationError("NON_CANONICAL_CONTENT_PATH", value)
    return normalized


def file_entry(path: str, data: bytes, media_type: str) -> dict[str, Any]:
    return {
        "path": path,
        "sha256": sha256_hex(data),
        "bytes": len(data),
        "media_type": media_type,
    }


def content_root(entries: Iterable[dict[str, Any]]) -> str:
    normalized: list[tuple[str, str, int]] = []
    seen: set[str] = set()
    for entry in entries:
        path = str(entry["path"])
        digest_value = str(entry["sha256"])
        size = int(entry["bytes"])
        if path in seen:
            raise VerificationError("DUPLICATE_CONTENT_PATH", path)
        if not HEX_64.fullmatch(digest_value) or size < 0:
            raise VerificationError("INVALID_CONTENT_ENTRY", path)
        seen.add(path)
        normalized.append((path, digest_value, size))
    normalized.sort()
    if not normalized:
        return sha256_hex(b"trillionnium.app.empty.v1\x00")
    nodes = [
        hashlib.sha256(
            b"trillionnium.app.leaf.v1\x00"
            + path.encode("utf-8")
            + b"\x00"
            + bytes.fromhex(digest_value)
            + b"\x00"
            + str(size).encode("ascii")
        ).digest()
        for path, digest_value, size in normalized
    ]
    while len(nodes) > 1:
        if len(nodes) % 2:
            nodes.append(nodes[-1])
        nodes = [
            hashlib.sha256(b"trillionnium.app.node.v1\x00" + nodes[index] + nodes[index + 1]).digest()
            for index in range(0, len(nodes), 2)
        ]
    return nodes[0].hex()


def derived_origin(app_id: str, publisher_id: str) -> str:
    """ADR 0004 tuple origin: two distinct bounded DNS labels; never public DNS.

    No normalization, publisher omission, legacy alias, or trailing slash is
    accepted. A root URL may append '/' only after origin authorization.
    """
    for value, reason in ((app_id, "INVALID_APP_ID"), (publisher_id, "INVALID_PUBLISHER_ID")):
        if not isinstance(value, str) or DNS_LABEL.fullmatch(value) is None:
            raise VerificationError(reason)
    return f"https://{app_id}.{publisher_id}.apps.hepta.invalid"


def signed_manifest_payload(manifest: dict[str, Any]) -> bytes:
    unsigned = copy.deepcopy(manifest)
    unsigned.pop("signature", None)
    return canonical_json(unsigned)


def transition_payload(transition: dict[str, Any]) -> bytes:
    value = copy.deepcopy(transition)
    value.pop("signature_by_from_key", None)
    return canonical_json(value)


def parse_csp(value: Any, contract: dict[str, Any]) -> dict[str, list[str]]:
    if not isinstance(value, str) or not value.strip():
        raise VerificationError("CSP_REQUIRED")
    directives: dict[str, list[str]] = {}
    for segment in value.split(";"):
        tokens = segment.strip().split()
        if not tokens:
            continue
        name = tokens[0].lower()
        if name in directives:
            raise VerificationError("DUPLICATE_CSP_DIRECTIVE", name)
        directives[name] = tokens[1:]
    required = contract["csp"]["required_directives"]
    if set(directives) != set(required):
        raise VerificationError("CSP_DIRECTIVE_SET_MISMATCH")
    for name, expected_values in required.items():
        actual = directives[name]
        if len(actual) != len(set(actual)) or set(actual) != set(expected_values):
            raise VerificationError("CSP_VALUE_MISMATCH", name)
    flattened = [token for values in directives.values() for token in values]
    if "*" in flattened or "'unsafe-eval'" in flattened or "'unsafe-inline'" in directives.get("script-src", []):
        raise VerificationError("CSP_UNSAFE_SOURCE")
    for token in flattened:
        if "://" in token:
            raise VerificationError("CSP_EXTERNAL_ORIGIN", token)
    return directives


def load_json(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if len(data) > MAX_MANIFEST_BYTES:
        raise VerificationError("JSON_DOCUMENT_TOO_LARGE", str(path))
    try:
        value = json.loads(data)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise VerificationError("INVALID_JSON", str(path)) from error
    if not isinstance(value, dict):
        raise VerificationError("JSON_OBJECT_REQUIRED", str(path))
    return value


def trust_key(trust_store: dict[str, Any], publisher_id: str, key_id: str, *, require_active: bool = True) -> bytes:
    publishers = trust_store.get("publishers")
    if not isinstance(publishers, dict):
        raise VerificationError("TRUST_STORE_PUBLISHERS_REQUIRED")
    publisher = publishers.get(publisher_id)
    if not isinstance(publisher, dict):
        raise VerificationError("UNKNOWN_PUBLISHER", publisher_id)
    keys = publisher.get("keys")
    if not isinstance(keys, dict):
        raise VerificationError("TRUST_STORE_KEYS_REQUIRED", publisher_id)
    record = keys.get(key_id)
    if not isinstance(record, dict):
        raise VerificationError("UNKNOWN_PUBLISHER_KEY", key_id)
    status_value = record.get("status")
    if require_active and status_value != "active":
        raise VerificationError("PUBLISHER_KEY_NOT_ACTIVE", key_id)
    return decode_base64(
        record.get("public_key_base64"), expected_bytes=32, reason="INVALID_PUBLISHER_PUBLIC_KEY"
    )


def enumerate_content(content_dir: Path, contract: dict[str, Any]) -> dict[str, Path]:
    if not content_dir.is_dir() or content_dir.is_symlink():
        raise VerificationError("UNSAFE_CONTENT_ROOT")
    result: dict[str, Path] = {}
    maximum_files = int(contract["path_policy"]["maximum_file_count"])
    for root, dirs, files in os.walk(content_dir, followlinks=False):
        root_path = Path(root)
        for directory in dirs:
            candidate = root_path / directory
            if candidate.is_symlink():
                raise VerificationError("CONTENT_SYMLINK_REJECTED", str(candidate))
        for name in files:
            candidate = root_path / name
            metadata = candidate.lstat()
            if stat.S_ISLNK(metadata.st_mode):
                raise VerificationError("CONTENT_SYMLINK_REJECTED", str(candidate))
            if not stat.S_ISREG(metadata.st_mode):
                raise VerificationError("NON_REGULAR_CONTENT_REJECTED", str(candidate))
            relative = candidate.relative_to(content_dir).as_posix()
            normalized = normalize_path(relative, contract)
            if normalized in result:
                raise VerificationError("DUPLICATE_CONTENT_PATH", normalized)
            result[normalized] = candidate
            if len(result) > maximum_files:
                raise VerificationError("TOO_MANY_CONTENT_FILES")
    return result


def verify_key_transition(
    manifest: dict[str, Any],
    trust_store: dict[str, Any],
    install_state: dict[str, Any],
    new_public_key: bytes,
) -> None:
    previous_key_id = install_state.get("publisher_key_id")
    new_key_id = manifest["publisher_key_id"]
    if previous_key_id == new_key_id:
        if manifest.get("key_transition") is not None:
            raise VerificationError("UNEXPECTED_KEY_TRANSITION")
        return
    transition = manifest.get("key_transition")
    if not isinstance(transition, dict):
        raise VerificationError("PUBLISHER_KEY_TRANSITION_REQUIRED")
    expected_keys = {
        "schema",
        "from_key_id",
        "to_key_id",
        "to_public_key_sha256",
        "minimum_version",
        "signature_by_from_key",
    }
    if set(transition) != expected_keys:
        raise VerificationError("NON_CANONICAL_KEY_TRANSITION")
    if transition.get("schema") != "trillionnium.desktop.publisher-key-transition.v1":
        raise VerificationError("INVALID_KEY_TRANSITION_SCHEMA")
    if transition.get("from_key_id") != previous_key_id or transition.get("to_key_id") != new_key_id:
        raise VerificationError("KEY_TRANSITION_IDENTITY_MISMATCH")
    if transition.get("to_public_key_sha256") != sha256_hex(new_public_key):
        raise VerificationError("KEY_TRANSITION_PUBLIC_KEY_MISMATCH")
    minimum_version = transition.get("minimum_version")
    if not isinstance(minimum_version, int) or manifest["version"] < minimum_version:
        raise VerificationError("KEY_TRANSITION_VERSION_MISMATCH")
    old_public_key = trust_key(
        trust_store, manifest["publisher_id"], str(previous_key_id), require_active=True
    )
    signature = decode_base64(
        transition.get("signature_by_from_key"),
        expected_bytes=64,
        reason="INVALID_KEY_TRANSITION_SIGNATURE",
    )
    if not ed25519_verify(old_public_key, transition_payload(transition), signature):
        raise VerificationError("KEY_TRANSITION_SIGNATURE_REJECTED")


def verify_bundle(
    manifest: dict[str, Any],
    content_dir: Path,
    trust_store: dict[str, Any],
    contract: dict[str, Any],
    *,
    install_state: dict[str, Any] | None = None,
    now_epoch: int,
) -> dict[str, Any]:
    required_fields = set(contract["manifest_required_fields"])
    if set(manifest) != required_fields:
        raise VerificationError("MANIFEST_FIELD_SET_MISMATCH")
    if manifest.get("schema") != contract["format"]["manifest_schema"]:
        raise VerificationError("MANIFEST_SCHEMA_MISMATCH")

    app_id = manifest.get("app_id")
    publisher_id = manifest.get("publisher_id")
    key_id = manifest.get("publisher_key_id")
    version = manifest.get("version")
    if not isinstance(app_id, str) or not isinstance(publisher_id, str) or not isinstance(key_id, str):
        raise VerificationError("MANIFEST_IDENTITY_FIELDS_REQUIRED")
    if not isinstance(version, int) or version < 1:
        raise VerificationError("INVALID_APP_VERSION")
    if manifest.get("synthetic_origin") != derived_origin(app_id, publisher_id):
        raise VerificationError("SYNTHETIC_ORIGIN_MISMATCH")

    revocation_epoch = trust_store.get("revocation_epoch")
    if not isinstance(revocation_epoch, int) or revocation_epoch < 0:
        raise VerificationError("INVALID_REVOCATION_EPOCH")
    generated_at = trust_store.get("generated_at_epoch")
    expires_at = trust_store.get("expires_at_epoch")
    if not isinstance(generated_at, int) or not isinstance(expires_at, int):
        raise VerificationError("REVOCATION_SNAPSHOT_TIME_REQUIRED")
    if not generated_at <= now_epoch <= expires_at:
        raise VerificationError("REVOCATION_SNAPSHOT_OUTSIDE_VALIDITY")

    public_key = trust_key(trust_store, publisher_id, key_id, require_active=True)
    signature_record = manifest.get("signature")
    if not isinstance(signature_record, dict) or set(signature_record) != {"algorithm", "value_base64"}:
        raise VerificationError("NON_CANONICAL_MANIFEST_SIGNATURE")
    if signature_record.get("algorithm") != "Ed25519":
        raise VerificationError("UNSUPPORTED_SIGNATURE_ALGORITHM")
    signature = decode_base64(
        signature_record.get("value_base64"), expected_bytes=64, reason="INVALID_MANIFEST_SIGNATURE"
    )
    if not ed25519_verify(public_key, signed_manifest_payload(manifest), signature):
        raise VerificationError("MANIFEST_SIGNATURE_REJECTED")

    content_value = manifest.get("content")
    if not isinstance(content_value, list):
        raise VerificationError("CONTENT_MANIFEST_LIST_REQUIRED")
    maximum_files = int(contract["path_policy"]["maximum_file_count"])
    if len(content_value) > maximum_files:
        raise VerificationError("TOO_MANY_CONTENT_FILES")
    declared: dict[str, dict[str, Any]] = {}
    total_bytes = 0
    for item in content_value:
        if not isinstance(item, dict) or set(item) != {"path", "sha256", "bytes", "media_type"}:
            raise VerificationError("NON_CANONICAL_CONTENT_ENTRY")
        path = normalize_path(item.get("path"), contract)
        digest_value = item.get("sha256")
        size = item.get("bytes")
        media_type = item.get("media_type")
        if path in declared:
            raise VerificationError("DUPLICATE_CONTENT_PATH", path)
        if not isinstance(digest_value, str) or not HEX_64.fullmatch(digest_value):
            raise VerificationError("INVALID_CONTENT_DIGEST", path)
        if not isinstance(size, int) or size < 0 or size > int(contract["path_policy"]["maximum_file_bytes"]):
            raise VerificationError("INVALID_CONTENT_SIZE", path)
        if not isinstance(media_type, str) or not media_type or len(media_type) > 128:
            raise VerificationError("INVALID_CONTENT_MEDIA_TYPE", path)
        total_bytes += size
        declared[path] = item
    if total_bytes > int(contract["path_policy"]["maximum_bundle_bytes"]):
        raise VerificationError("BUNDLE_TOO_LARGE")
    computed_root = content_root(content_value)
    if manifest.get("content_root_sha256") != computed_root:
        raise VerificationError("CONTENT_ROOT_MISMATCH")

    actual = enumerate_content(content_dir, contract)
    if set(actual) != set(declared):
        missing = sorted(set(declared) - set(actual))
        extra = sorted(set(actual) - set(declared))
        raise VerificationError("CONTENT_SET_MISMATCH", json.dumps({"missing": missing, "extra": extra}))
    for path, source in actual.items():
        data = source.read_bytes()
        item = declared[path]
        if len(data) != item["bytes"] or sha256_hex(data) != item["sha256"]:
            raise VerificationError("CONTENT_DIGEST_MISMATCH", path)

    entrypoint = normalize_path(manifest.get("entrypoint"), contract)
    if entrypoint not in declared:
        raise VerificationError("ENTRYPOINT_NOT_SIGNED_CONTENT")
    if declared[entrypoint]["media_type"] not in {"text/html", "application/xhtml+xml"}:
        raise VerificationError("ENTRYPOINT_MEDIA_TYPE_REJECTED")
    parse_csp(manifest.get("csp"), contract)

    permissions = manifest.get("permissions")
    if permissions != []:
        raise VerificationError("D5_SYSTEM_PERMISSIONS_NOT_AUTHORIZED")
    storage = manifest.get("storage")
    expected_partition = {"app_id": app_id, "publisher_id": publisher_id}
    if not isinstance(storage, dict) or set(storage) != {"partition_key", "preserve_across_version"}:
        raise VerificationError("NON_CANONICAL_STORAGE_POLICY")
    if storage.get("partition_key") != expected_partition or storage.get("preserve_across_version") is not True:
        raise VerificationError("STORAGE_PARTITION_MISMATCH")

    worker = manifest.get("service_worker")
    if not isinstance(worker, dict) or set(worker) != {"enabled", "script", "scope", "network_fetch", "update_source"}:
        raise VerificationError("NON_CANONICAL_SERVICE_WORKER_POLICY")
    if worker.get("network_fetch") is not False or worker.get("update_source") != "signed_bundle_only":
        raise VerificationError("SERVICE_WORKER_AUTHORITY_WIDENED")
    if worker.get("enabled") is False:
        if worker.get("script") is not None or worker.get("scope") is not None:
            raise VerificationError("DISABLED_SERVICE_WORKER_HAS_RUNTIME_FIELDS")
    elif worker.get("enabled") is True:
        script_path = normalize_path(worker.get("script"), contract)
        scope = worker.get("scope")
        if script_path not in declared:
            raise VerificationError("SERVICE_WORKER_SCRIPT_NOT_SIGNED")
        if not isinstance(scope, str) or not scope.startswith("/") or ".." in PurePosixPath(scope).parts or "\\" in scope:
            raise VerificationError("SERVICE_WORKER_SCOPE_REJECTED")
    else:
        raise VerificationError("SERVICE_WORKER_ENABLED_BOOLEAN_REQUIRED")

    manifest_digest = sha256_hex(canonical_json(manifest))
    revoked_bundles = trust_store.get("revoked_bundle_digests")
    if not isinstance(revoked_bundles, list) or not all(isinstance(item, str) and HEX_64.fullmatch(item) for item in revoked_bundles):
        raise VerificationError("INVALID_REVOKED_BUNDLE_SET")
    if manifest_digest in revoked_bundles:
        raise VerificationError("BUNDLE_REVOKED")

    if install_state is not None:
        if install_state.get("schema") != "trillionnium.desktop.trusted-app-install-state.v1":
            raise VerificationError("INSTALL_STATE_SCHEMA_MISMATCH")
        if install_state.get("app_id") != app_id or install_state.get("publisher_id") != publisher_id:
            raise VerificationError("INSTALL_STATE_IDENTITY_MISMATCH")
        previous_revocation_epoch = install_state.get("revocation_epoch")
        if not isinstance(previous_revocation_epoch, int) or revocation_epoch < previous_revocation_epoch:
            raise VerificationError("STALE_REVOCATION_SNAPSHOT")
        highest = install_state.get("highest_accepted_version")
        previous_root = install_state.get("content_root_sha256")
        if not isinstance(highest, int):
            raise VerificationError("INVALID_INSTALL_VERSION")
        if version < highest:
            raise VerificationError("VERSION_DOWNGRADE_REJECTED")
        if version == highest:
            if previous_root != computed_root or install_state.get("publisher_key_id") != key_id:
                raise VerificationError("SAME_VERSION_CONTENT_OR_KEY_CHANGED")
        verify_key_transition(manifest, trust_store, install_state, public_key)
    elif manifest.get("key_transition") is not None:
        raise VerificationError("INITIAL_INSTALL_MUST_NOT_HAVE_KEY_TRANSITION")

    new_state = {
        "schema": "trillionnium.desktop.trusted-app-install-state.v1",
        "app_id": app_id,
        "publisher_id": publisher_id,
        "publisher_key_id": key_id,
        "highest_accepted_version": version,
        "content_root_sha256": computed_root,
        "manifest_sha256": manifest_digest,
        "revocation_epoch": revocation_epoch,
        "storage_partition_key": expected_partition,
    }
    indicator = {
        "schema": "trillionnium.desktop.trusted-app-indicator.v1",
        "app_id": app_id,
        "version": version,
        "publisher_id": publisher_id,
        "publisher_key_id": key_id,
        "content_root_sha256": computed_root,
        "synthetic_origin": manifest["synthetic_origin"],
        "revocation_epoch": revocation_epoch,
        "trust_state": "OFFLINE_SIGNATURE_AND_CONTENT_VERIFIED",
    }
    indicator["receipt_sha256"] = sha256_hex(canonical_json(indicator))
    return {
        "schema": "trillionnium.desktop.trusted-app-verification-result.v1",
        "status": "PASS_OFFLINE_REFERENCE_VERIFICATION",
        "manifest_sha256": manifest_digest,
        "content_root_sha256": computed_root,
        "file_count": len(declared),
        "bundle_bytes": total_bytes,
        "install_state": new_state,
        "trust_indicator": indicator,
        "network_used": False,
        "product_origin_integrated": False,
        "production_signing_key_custody_proven": False,
        "release_ready": False,
    }


def fixture_csp(contract: dict[str, Any]) -> str:
    return "; ".join(
        f"{name} {' '.join(values)}" for name, values in contract["csp"]["required_directives"].items()
    )


def build_fixture_manifest(
    contract: dict[str, Any],
    content: dict[str, bytes],
    *,
    seed: bytes,
    app_id: str = "notes",
    publisher_id: str = "trillionnium-fixture",
    key_id: str = "fixture-key-1",
    version: int = 1,
    key_transition: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bytes]:
    media = {"index.html": "text/html", "app.js": "text/javascript", "worker.js": "text/javascript"}
    entries = [file_entry(path, data, media.get(path, "application/octet-stream")) for path, data in content.items()]
    manifest: dict[str, Any] = {
        "schema": contract["format"]["manifest_schema"],
        "app_id": app_id,
        "version": version,
        "publisher_id": publisher_id,
        "publisher_key_id": key_id,
        "entrypoint": "index.html",
        "synthetic_origin": derived_origin(app_id, publisher_id),
        "content_root_sha256": content_root(entries),
        "content": entries,
        "csp": fixture_csp(contract),
        "storage": {
            "partition_key": {"app_id": app_id, "publisher_id": publisher_id},
            "preserve_across_version": True,
        },
        "service_worker": {
            "enabled": False,
            "script": None,
            "scope": None,
            "network_fetch": False,
            "update_source": "signed_bundle_only",
        },
        "permissions": [],
        "key_transition": key_transition,
        "signature": {"algorithm": "Ed25519", "value_base64": ""},
    }
    public_key = ed25519_public_from_seed(seed)
    manifest["signature"]["value_base64"] = base64.b64encode(
        ed25519_sign_fixture(seed, signed_manifest_payload(manifest))
    ).decode("ascii")
    return manifest, public_key


def self_test(contract: dict[str, Any]) -> dict[str, Any]:
    # RFC 8032 test vector 1.
    seed = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    expected_public = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")
    expected_signature = bytes.fromhex(
        "e5564300c360ac729086e2cc806e828a84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46bd25bf5f0595bbe24655141438e7a100b"
    )
    if ed25519_public_from_seed(seed) != expected_public:
        raise AssertionError("RFC 8032 public-key vector failed")
    if ed25519_sign_fixture(seed, b"") != expected_signature:
        raise AssertionError("RFC 8032 signing vector failed")
    if not ed25519_verify(expected_public, b"", expected_signature):
        raise AssertionError("RFC 8032 verification vector failed")

    content = {
        "index.html": b"<!doctype html><meta charset=utf-8><script src=app.js></script>",
        "app.js": b"globalThis.trillionniumFixture = true;\n",
    }
    manifest, public_key = build_fixture_manifest(contract, content, seed=seed)
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for relative, data in content.items():
            path = root / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        trust = {
            "schema": "trillionnium.desktop.trust-store.v1",
            "revocation_epoch": 1,
            "generated_at_epoch": 1,
            "expires_at_epoch": 10_000,
            "publishers": {
                manifest["publisher_id"]: {
                    "keys": {
                        manifest["publisher_key_id"]: {
                            "status": "active",
                            "public_key_base64": base64.b64encode(public_key).decode("ascii"),
                        }
                    }
                }
            },
            "revoked_bundle_digests": [],
        }
        result = verify_bundle(manifest, root, trust, contract, now_epoch=100)
    return {
        "schema": "trillionnium.desktop.trusted-app-self-test.v1",
        "status": "PASS_SOURCE_REFERENCE_ONLY",
        "rfc8032_vector": "PASS",
        "offline_bundle_verification": result["status"],
        "content_root_sha256": result["content_root_sha256"],
        "trust_indicator_sha256": result["trust_indicator"]["receipt_sha256"],
        "network_used": False,
        "production_signing_key_custody_proven": False,
        "product_origin_integrated": False,
        "release_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    verify_parser = sub.add_parser("verify")
    verify_parser.add_argument("--manifest", type=Path, required=True)
    verify_parser.add_argument("--content-dir", type=Path, required=True)
    verify_parser.add_argument("--trust-store", type=Path, required=True)
    verify_parser.add_argument("--install-state", type=Path)
    verify_parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    verify_parser.add_argument("--now-epoch", type=int, required=True)
    verify_parser.add_argument("--write-result", type=Path)
    self_parser = sub.add_parser("self-test")
    self_parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    self_parser.add_argument("--write-result", type=Path)
    args = parser.parse_args()

    try:
        contract = load_json(args.contract)
        if contract.get("status") != "SOURCE_CANDIDATE_BLOCKED_UPSTREAM_D4":
            raise VerificationError("D5_CONTRACT_STATUS_WIDENED")
        if args.command == "verify":
            result = verify_bundle(
                load_json(args.manifest),
                args.content_dir,
                load_json(args.trust_store),
                contract,
                install_state=load_json(args.install_state) if args.install_state else None,
                now_epoch=args.now_epoch,
            )
        else:
            result = self_test(contract)
        payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
        if args.write_result:
            args.write_result.parent.mkdir(parents=True, exist_ok=True)
            args.write_result.write_text(payload, encoding="utf-8")
        print(payload, end="")
        return 0
    except VerificationError as error:
        print(json.dumps({"status": "REJECTED", "reason": error.reason, "detail": error.detail}, sort_keys=True), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
