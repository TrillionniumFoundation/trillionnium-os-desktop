#!/usr/bin/env python3
"""Stable D7 A/B-update facade with deterministic image refusal precedence.

The complete reference model remains in ``ab_update_reference_impl``.  This
facade preserves its public API and CLI while pinning one security-relevant
classification rule: when supplied image bytes differ from the signed image,
the digest mismatch is reported before the derivative byte-count mismatch.
This keeps tamper classification stable when an attacker appends or truncates
bytes and therefore changes both properties at once.

The model remains side-effect free: it writes no block device, changes no
bootloader, reads no network, and accesses no signing key.
"""
from __future__ import annotations

import copy
from typing import Any

import ab_update_reference_impl as _impl
from ab_update_reference_impl import *  # noqa: F401,F403


def verify_update_manifest(
    manifest: dict[str, Any],
    image: bytes,
    trust: dict[str, Any],
    *,
    hardware_profile: str,
    current_version: int,
    secure_rollback_index: int,
    now_epoch: int,
) -> dict[str, Any]:
    """Verify a signed update with stable digest-before-size classification."""

    if not isinstance(manifest, dict) or set(manifest) != _impl.UPDATE_FIELDS:
        _impl.fail("UPDATE_MANIFEST_FIELD_SET_MISMATCH")
    if manifest.get("schema") != "trillionnium.desktop.update-manifest.v1":
        _impl.fail("UPDATE_MANIFEST_SCHEMA_MISMATCH")
    release_id = _impl.require_id(
        manifest["release_id"], "UPDATE_RELEASE_ID_INVALID"
    )
    issuer_id = _impl.require_id(
        manifest["issuer_id"], "UPDATE_ISSUER_ID_INVALID"
    )
    key_id = _impl.require_id(manifest["issuer_key_id"], "UPDATE_KEY_ID_INVALID")
    version = manifest["version"]
    rollback_index = manifest["rollback_index"]
    minimum_current = manifest["minimum_current_version"]
    if not all(
        isinstance(value, int) and value >= 0
        for value in (version, rollback_index, minimum_current)
    ):
        _impl.fail("UPDATE_VERSION_FIELDS_INVALID")
    if version <= current_version:
        _impl.fail("UPDATE_VERSION_DOWNGRADE_REJECTED")
    if current_version < minimum_current:
        _impl.fail("CURRENT_VERSION_BELOW_UPDATE_MINIMUM")
    if rollback_index <= secure_rollback_index:
        _impl.fail("ROLLBACK_INDEX_DOWNGRADE_REJECTED")
    if manifest["hardware_profile"] != hardware_profile:
        _impl.fail("UPDATE_HARDWARE_PROFILE_MISMATCH")
    if manifest["recovery_compatible"] is not True:
        _impl.fail("UPDATE_NOT_RECOVERY_COMPATIBLE")

    image_digest = _impl.require_hex(
        manifest["image_sha256"], _impl.HEX_64, "UPDATE_IMAGE_DIGEST_INVALID"
    )
    if _impl.digest_bytes(image) != image_digest:
        _impl.fail("UPDATE_IMAGE_DIGEST_MISMATCH")
    image_bytes = manifest["image_bytes"]
    if (
        not isinstance(image_bytes, int)
        or image_bytes < 1
        or image_bytes != len(image)
    ):
        _impl.fail("UPDATE_IMAGE_SIZE_MISMATCH")

    _impl.require_hex(
        manifest["source_commit"], _impl.HEX_40, "UPDATE_SOURCE_COMMIT_INVALID"
    )
    _impl.require_hex(
        manifest["sbom_sha256"], _impl.HEX_64, "UPDATE_SBOM_DIGEST_INVALID"
    )
    _impl.require_hex(
        manifest["provenance_sha256"],
        _impl.HEX_64,
        "UPDATE_PROVENANCE_DIGEST_INVALID",
    )
    revoked = trust.get("revoked_release_ids")
    if not isinstance(revoked, list) or not all(
        isinstance(item, str) for item in revoked
    ):
        _impl.fail("REVOKED_RELEASE_SET_INVALID")
    if release_id in revoked:
        _impl.fail("UPDATE_RELEASE_REVOKED")
    public = _impl.key_from_trust(
        trust, "update_issuers", issuer_id, key_id, now_epoch
    )
    if not _impl.ed25519_verify(
        public,
        _impl.signed_payload(manifest),
        _impl.decode_signature(manifest["signature"]),
    ):
        _impl.fail("UPDATE_SIGNATURE_REJECTED")
    return copy.deepcopy(manifest)


# UpdateEngine methods resolve their globals in the implementation module.
# Pin the corrected verifier there so direct imports, tests, self-tests, and the
# command-line entry point all execute one policy.
_impl.verify_update_manifest = verify_update_manifest


if __name__ == "__main__":
    raise SystemExit(_impl.main())
