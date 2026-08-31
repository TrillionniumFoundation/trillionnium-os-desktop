#!/usr/bin/env python3
"""Signed immutable A/B update and offline-recovery reference model.

The model never writes a block device, changes a bootloader, reads a network,
or accesses signing keys. Deterministic fixture signing is used only in tests.
"""
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from trusted_app_bundle import (  # noqa: E402
    canonical_json,
    ed25519_public_from_seed,
    ed25519_sign_fixture,
    ed25519_verify,
)

CONTRACT_PATH = ROOT / "contracts" / "recovery-update-reconciliation.v1.json"
HEX_40 = re.compile(r"^[0-9a-f]{40}$")
HEX_64 = re.compile(r"^[0-9a-f]{64}$")
IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
UPDATE_FIELDS = {
    "schema",
    "release_id",
    "issuer_id",
    "issuer_key_id",
    "version",
    "rollback_index",
    "hardware_profile",
    "image_sha256",
    "image_bytes",
    "source_commit",
    "sbom_sha256",
    "provenance_sha256",
    "minimum_current_version",
    "recovery_compatible",
    "signature",
}
RECOVERY_FIELDS = {
    "schema",
    "media_id",
    "issuer_id",
    "issuer_key_id",
    "hardware_profile",
    "image_sha256",
    "image_bytes",
    "minimum_rollback_index",
    "source_commit",
    "provenance_sha256",
    "automatic_destructive_recovery",
    "signature",
}


class UpdateError(ValueError):
    def __init__(self, reason: str, detail: str | None = None) -> None:
        super().__init__(reason if detail is None else f"{reason}: {detail}")
        self.reason = reason
        self.detail = detail


def fail(reason: str, detail: str | None = None) -> None:
    raise UpdateError(reason, detail)


def digest_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def digest_json(value: Any) -> str:
    return digest_bytes(canonical_json(value))


def require_id(value: Any, reason: str) -> str:
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        fail(reason)
    return value


def require_hex(value: Any, pattern: re.Pattern[str], reason: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        fail(reason)
    return value


def signed_payload(manifest: dict[str, Any]) -> bytes:
    value = copy.deepcopy(manifest)
    value.pop("signature", None)
    return canonical_json(value)


def decode_signature(record: Any) -> bytes:
    if not isinstance(record, dict) or set(record) != {"algorithm", "value_base64"}:
        fail("SIGNATURE_FIELD_SET_MISMATCH")
    if record["algorithm"] != "Ed25519":
        fail("SIGNATURE_ALGORITHM_UNSUPPORTED")
    try:
        value = base64.b64decode(record["value_base64"], validate=True)
    except (TypeError, ValueError) as error:
        raise UpdateError("SIGNATURE_BASE64_INVALID") from error
    if len(value) != 64:
        fail("SIGNATURE_LENGTH_INVALID")
    return value


def key_from_trust(
    trust: dict[str, Any],
    group: str,
    issuer_id: str,
    key_id: str,
    now_epoch: int,
) -> bytes:
    if trust.get("schema") != "trillionnium.desktop.update-key-trust.v1":
        fail("UPDATE_TRUST_SCHEMA_MISMATCH")
    issuers = trust.get(group)
    if not isinstance(issuers, dict):
        fail("UPDATE_TRUST_GROUP_MISSING", group)
    issuer = issuers.get(issuer_id)
    if not isinstance(issuer, dict) or set(issuer) != {"keys"}:
        fail("UPDATE_ISSUER_UNKNOWN", issuer_id)
    keys = issuer["keys"]
    record = keys.get(key_id) if isinstance(keys, dict) else None
    if not isinstance(record, dict) or set(record) != {
        "status",
        "public_key_base64",
        "not_before_epoch",
        "expires_at_epoch",
    }:
        fail("UPDATE_KEY_UNKNOWN_OR_INVALID", key_id)
    if record["status"] != "active":
        fail("UPDATE_KEY_NOT_ACTIVE", key_id)
    if not isinstance(record["not_before_epoch"], int) or not isinstance(record["expires_at_epoch"], int):
        fail("UPDATE_KEY_TIME_INVALID")
    if not record["not_before_epoch"] <= now_epoch <= record["expires_at_epoch"]:
        fail("UPDATE_KEY_OUTSIDE_VALIDITY")
    try:
        public = base64.b64decode(record["public_key_base64"], validate=True)
    except (TypeError, ValueError) as error:
        raise UpdateError("UPDATE_PUBLIC_KEY_BASE64_INVALID") from error
    if len(public) != 32:
        fail("UPDATE_PUBLIC_KEY_LENGTH_INVALID")
    return public


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
    if not isinstance(manifest, dict) or set(manifest) != UPDATE_FIELDS:
        fail("UPDATE_MANIFEST_FIELD_SET_MISMATCH")
    if manifest.get("schema") != "trillionnium.desktop.update-manifest.v1":
        fail("UPDATE_MANIFEST_SCHEMA_MISMATCH")
    release_id = require_id(manifest["release_id"], "UPDATE_RELEASE_ID_INVALID")
    issuer_id = require_id(manifest["issuer_id"], "UPDATE_ISSUER_ID_INVALID")
    key_id = require_id(manifest["issuer_key_id"], "UPDATE_KEY_ID_INVALID")
    version = manifest["version"]
    rollback_index = manifest["rollback_index"]
    minimum_current = manifest["minimum_current_version"]
    if not all(isinstance(value, int) and value >= 0 for value in (version, rollback_index, minimum_current)):
        fail("UPDATE_VERSION_FIELDS_INVALID")
    if version <= current_version:
        fail("UPDATE_VERSION_DOWNGRADE_REJECTED")
    if current_version < minimum_current:
        fail("CURRENT_VERSION_BELOW_UPDATE_MINIMUM")
    if rollback_index <= secure_rollback_index:
        fail("ROLLBACK_INDEX_DOWNGRADE_REJECTED")
    if manifest["hardware_profile"] != hardware_profile:
        fail("UPDATE_HARDWARE_PROFILE_MISMATCH")
    if manifest["recovery_compatible"] is not True:
        fail("UPDATE_NOT_RECOVERY_COMPATIBLE")
    image_bytes = manifest["image_bytes"]
    if not isinstance(image_bytes, int) or image_bytes < 1 or image_bytes != len(image):
        fail("UPDATE_IMAGE_SIZE_MISMATCH")
    image_digest = require_hex(manifest["image_sha256"], HEX_64, "UPDATE_IMAGE_DIGEST_INVALID")
    if digest_bytes(image) != image_digest:
        fail("UPDATE_IMAGE_DIGEST_MISMATCH")
    require_hex(manifest["source_commit"], HEX_40, "UPDATE_SOURCE_COMMIT_INVALID")
    require_hex(manifest["sbom_sha256"], HEX_64, "UPDATE_SBOM_DIGEST_INVALID")
    require_hex(manifest["provenance_sha256"], HEX_64, "UPDATE_PROVENANCE_DIGEST_INVALID")
    revoked = trust.get("revoked_release_ids")
    if not isinstance(revoked, list) or not all(isinstance(item, str) for item in revoked):
        fail("REVOKED_RELEASE_SET_INVALID")
    if release_id in revoked:
        fail("UPDATE_RELEASE_REVOKED")
    public = key_from_trust(trust, "update_issuers", issuer_id, key_id, now_epoch)
    if not ed25519_verify(public, signed_payload(manifest), decode_signature(manifest["signature"])):
        fail("UPDATE_SIGNATURE_REJECTED")
    return copy.deepcopy(manifest)


def verify_recovery_media(
    manifest: dict[str, Any],
    image: bytes,
    trust: dict[str, Any],
    *,
    hardware_profile: str,
    secure_rollback_index: int,
    now_epoch: int,
) -> dict[str, Any]:
    if not isinstance(manifest, dict) or set(manifest) != RECOVERY_FIELDS:
        fail("RECOVERY_MANIFEST_FIELD_SET_MISMATCH")
    if manifest.get("schema") != "trillionnium.desktop.recovery-media-manifest.v1":
        fail("RECOVERY_MANIFEST_SCHEMA_MISMATCH")
    require_id(manifest["media_id"], "RECOVERY_MEDIA_ID_INVALID")
    issuer_id = require_id(manifest["issuer_id"], "RECOVERY_ISSUER_ID_INVALID")
    key_id = require_id(manifest["issuer_key_id"], "RECOVERY_KEY_ID_INVALID")
    if manifest["hardware_profile"] != hardware_profile:
        fail("RECOVERY_HARDWARE_PROFILE_MISMATCH")
    minimum = manifest["minimum_rollback_index"]
    if not isinstance(minimum, int) or minimum < secure_rollback_index:
        fail("RECOVERY_ROLLBACK_INDEX_TOO_OLD")
    if manifest["automatic_destructive_recovery"] is not False:
        fail("AUTOMATIC_DESTRUCTIVE_RECOVERY_FORBIDDEN")
    if manifest["image_bytes"] != len(image):
        fail("RECOVERY_IMAGE_SIZE_MISMATCH")
    expected = require_hex(manifest["image_sha256"], HEX_64, "RECOVERY_IMAGE_DIGEST_INVALID")
    if digest_bytes(image) != expected:
        fail("RECOVERY_IMAGE_DIGEST_MISMATCH")
    require_hex(manifest["source_commit"], HEX_40, "RECOVERY_SOURCE_COMMIT_INVALID")
    require_hex(manifest["provenance_sha256"], HEX_64, "RECOVERY_PROVENANCE_DIGEST_INVALID")
    public = key_from_trust(trust, "recovery_issuers", issuer_id, key_id, now_epoch)
    if not ed25519_verify(public, signed_payload(manifest), decode_signature(manifest["signature"])):
        fail("RECOVERY_SIGNATURE_REJECTED")
    return {
        "schema": "trillionnium.desktop.recovery-media-verification.v1",
        "status": "PASS_OFFLINE_REFERENCE_VERIFICATION",
        "media_id": manifest["media_id"],
        "image_sha256": expected,
        "hardware_profile": hardware_profile,
        "minimum_rollback_index": minimum,
        "automatic_destructive_recovery": False,
        "recovery_execution_performed": False,
    }


@dataclass
class Slot:
    state: str
    version: int | None = None
    rollback_index: int | None = None
    image_sha256: str | None = None
    image_bytes: int = 0
    bytes_written: int = 0
    release_id: str | None = None
    source_commit: str | None = None
    sbom_sha256: str | None = None
    provenance_sha256: str | None = None
    sealed: bool = False
    healthy: bool = False


class UpdateJournal:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    @staticmethod
    def record_hash(sequence: int, previous: str, event: dict[str, Any]) -> str:
        return digest_json(
            {
                "sequence": sequence,
                "previous_record_sha256": previous,
                "event": event,
            }
        )

    def append(self, event: dict[str, Any]) -> dict[str, Any]:
        sequence = len(self.records) + 1
        previous = self.records[-1]["record_sha256"] if self.records else "0" * 64
        record = {
            "schema": "trillionnium.desktop.update-journal-record.v1",
            "sequence": sequence,
            "previous_record_sha256": previous,
            "event": copy.deepcopy(event),
        }
        record["record_sha256"] = self.record_hash(sequence, previous, record["event"])
        self.records.append(record)
        return copy.deepcopy(record)

    def serialize(self) -> bytes:
        return b"".join(canonical_json(record) for record in self.records)

    @classmethod
    def parse(cls, data: bytes) -> tuple[list[dict[str, Any]], bool]:
        if not isinstance(data, bytes):
            fail("UPDATE_JOURNAL_BYTES_REQUIRED")
        discarded_tail = False
        complete = data
        if complete and not complete.endswith(b"\n"):
            split = complete.rfind(b"\n")
            complete = complete[: split + 1] if split >= 0 else b""
            discarded_tail = True
        records: list[dict[str, Any]] = []
        previous = "0" * 64
        for sequence, line in enumerate(complete.splitlines(), start=1):
            try:
                record = json.loads(line)
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise UpdateError("UPDATE_JOURNAL_CORRUPT_RECORD") from error
            if not isinstance(record, dict) or set(record) != {
                "schema",
                "sequence",
                "previous_record_sha256",
                "event",
                "record_sha256",
            }:
                fail("UPDATE_JOURNAL_RECORD_FIELD_SET_MISMATCH")
            if record["schema"] != "trillionnium.desktop.update-journal-record.v1":
                fail("UPDATE_JOURNAL_RECORD_SCHEMA_MISMATCH")
            if record["sequence"] != sequence:
                fail("UPDATE_JOURNAL_SEQUENCE_MISMATCH")
            if record["previous_record_sha256"] != previous:
                fail("UPDATE_JOURNAL_PREVIOUS_HASH_MISMATCH")
            expected = cls.record_hash(sequence, previous, record["event"])
            if record["record_sha256"] != expected:
                fail("UPDATE_JOURNAL_RECORD_HASH_MISMATCH")
            records.append(copy.deepcopy(record))
            previous = expected
        return records, discarded_tail


class UpdateEngine:
    def __init__(self) -> None:
        self.hardware_profile = ""
        self.active_slot = "A"
        self.previous_healthy_slot: str | None = None
        self.pending_slot: str | None = None
        self.phase = "uninitialized"
        self.secure_rollback_index = 0
        self.maximum_boot_attempts = 2
        self.boot_attempts = 0
        self.slots = {"A": Slot("empty"), "B": Slot("empty")}
        self.last_outcome = "none"
        self.recovery_media_required = False
        self.journal = UpdateJournal()
        self.discarded_torn_tail = False

    @classmethod
    def bootstrap(
        cls,
        *,
        hardware_profile: str,
        version: int,
        rollback_index: int,
        image_sha256: str,
        image_bytes: int,
        source_commit: str,
        sbom_sha256: str,
        provenance_sha256: str,
    ) -> "UpdateEngine":
        engine = cls()
        event = {
            "kind": "initialize",
            "hardware_profile": hardware_profile,
            "active_slot": "A",
            "version": version,
            "rollback_index": rollback_index,
            "image_sha256": image_sha256,
            "image_bytes": image_bytes,
            "source_commit": source_commit,
            "sbom_sha256": sbom_sha256,
            "provenance_sha256": provenance_sha256,
            "maximum_boot_attempts": 2,
        }
        engine._append(event)
        return engine

    def _append(self, event: dict[str, Any]) -> dict[str, Any]:
        self._apply_event(copy.deepcopy(event))
        return self.journal.append(event)

    def _slot_from_manifest(self, state: str, manifest: dict[str, Any], *, bytes_written: int) -> Slot:
        return Slot(
            state=state,
            version=manifest["version"],
            rollback_index=manifest["rollback_index"],
            image_sha256=manifest["image_sha256"],
            image_bytes=manifest["image_bytes"],
            bytes_written=bytes_written,
            release_id=manifest["release_id"],
            source_commit=manifest["source_commit"],
            sbom_sha256=manifest["sbom_sha256"],
            provenance_sha256=manifest["provenance_sha256"],
            sealed=state in {"sealed", "pending", "booting", "healthy", "failed"},
            healthy=state == "healthy",
        )

    def _apply_event(self, event: dict[str, Any]) -> None:
        if not isinstance(event, dict) or "kind" not in event:
            fail("UPDATE_EVENT_INVALID")
        kind = event["kind"]
        if kind == "initialize":
            expected = {
                "kind",
                "hardware_profile",
                "active_slot",
                "version",
                "rollback_index",
                "image_sha256",
                "image_bytes",
                "source_commit",
                "sbom_sha256",
                "provenance_sha256",
                "maximum_boot_attempts",
            }
            if set(event) != expected or self.phase != "uninitialized":
                fail("UPDATE_INITIALIZE_INVALID")
            if event["active_slot"] not in {"A", "B"}:
                fail("UPDATE_ACTIVE_SLOT_INVALID")
            require_id(event["hardware_profile"], "HARDWARE_PROFILE_INVALID")
            require_hex(event["image_sha256"], HEX_64, "INITIAL_IMAGE_DIGEST_INVALID")
            require_hex(event["source_commit"], HEX_40, "INITIAL_SOURCE_COMMIT_INVALID")
            require_hex(event["sbom_sha256"], HEX_64, "INITIAL_SBOM_DIGEST_INVALID")
            require_hex(event["provenance_sha256"], HEX_64, "INITIAL_PROVENANCE_DIGEST_INVALID")
            if not isinstance(event["version"], int) or event["version"] < 1:
                fail("INITIAL_VERSION_INVALID")
            if not isinstance(event["rollback_index"], int) or event["rollback_index"] < 0:
                fail("INITIAL_ROLLBACK_INDEX_INVALID")
            if not isinstance(event["image_bytes"], int) or event["image_bytes"] < 1:
                fail("INITIAL_IMAGE_SIZE_INVALID")
            if event["maximum_boot_attempts"] != 2:
                fail("BOOT_ATTEMPT_POLICY_CHANGED")
            self.hardware_profile = event["hardware_profile"]
            self.active_slot = event["active_slot"]
            self.secure_rollback_index = event["rollback_index"]
            self.maximum_boot_attempts = event["maximum_boot_attempts"]
            self.slots[self.active_slot] = Slot(
                state="healthy",
                version=event["version"],
                rollback_index=event["rollback_index"],
                image_sha256=event["image_sha256"],
                image_bytes=event["image_bytes"],
                bytes_written=event["image_bytes"],
                release_id="bootstrap",
                source_commit=event["source_commit"],
                sbom_sha256=event["sbom_sha256"],
                provenance_sha256=event["provenance_sha256"],
                sealed=True,
                healthy=True,
            )
            self.phase = "idle"
            return

        if self.phase == "uninitialized":
            fail("UPDATE_ENGINE_NOT_INITIALIZED")
        if kind == "stage_intent":
            if set(event) != {"kind", "target_slot", "manifest"} or self.phase != "idle":
                fail("STAGE_INTENT_INVALID")
            target = event["target_slot"]
            if target not in {"A", "B"} or target == self.active_slot:
                fail("STAGE_TARGET_MUST_BE_INACTIVE")
            manifest = event["manifest"]
            if not isinstance(manifest, dict):
                fail("STAGE_MANIFEST_REQUIRED")
            self.slots[target] = self._slot_from_manifest("partial", manifest, bytes_written=0)
            self.pending_slot = None
            self.previous_healthy_slot = self.active_slot
            self.phase = "staging"
            self.boot_attempts = 0
            self.last_outcome = "stage_started"
            return
        if kind == "write_progress":
            if set(event) != {"kind", "target_slot", "bytes_written"} or self.phase != "staging":
                fail("WRITE_PROGRESS_INVALID")
            slot = self.slots.get(event["target_slot"])
            if slot is None or slot.state != "partial":
                fail("WRITE_TARGET_NOT_PARTIAL")
            value = event["bytes_written"]
            if not isinstance(value, int) or not slot.bytes_written <= value <= slot.image_bytes:
                fail("WRITE_PROGRESS_OUT_OF_RANGE")
            slot.bytes_written = value
            return
        if kind == "seal_slot":
            if set(event) != {"kind", "target_slot"} or self.phase != "staging":
                fail("SEAL_SLOT_INVALID")
            slot = self.slots.get(event["target_slot"])
            if slot is None or slot.state != "partial" or slot.bytes_written != slot.image_bytes:
                fail("SLOT_NOT_FULLY_WRITTEN")
            slot.state = "sealed"
            slot.sealed = True
            self.phase = "sealed_waiting_explicit_pending"
            self.last_outcome = "slot_sealed_not_active"
            return
        if kind == "mark_pending":
            if set(event) != {"kind", "target_slot"} or self.phase != "sealed_waiting_explicit_pending":
                fail("MARK_PENDING_INVALID")
            target = event["target_slot"]
            slot = self.slots.get(target)
            if slot is None or slot.state != "sealed":
                fail("PENDING_SLOT_NOT_SEALED")
            slot.state = "pending"
            self.pending_slot = target
            self.phase = "pending_boot"
            self.last_outcome = "pending_boot"
            return
        if kind == "boot_attempt":
            if set(event) != {"kind", "target_slot", "attempt"} or self.phase != "pending_boot":
                fail("BOOT_ATTEMPT_INVALID")
            if event["target_slot"] != self.pending_slot or event["attempt"] != self.boot_attempts + 1:
                fail("BOOT_ATTEMPT_SEQUENCE_INVALID")
            slot = self.slots[self.pending_slot]
            if slot.state != "pending":
                fail("BOOT_TARGET_NOT_PENDING")
            self.boot_attempts += 1
            slot.state = "booting"
            self.phase = "awaiting_health"
            self.last_outcome = "boot_attempt_started"
            return
        if kind == "health_success":
            if set(event) != {"kind", "target_slot"} or self.phase != "awaiting_health":
                fail("HEALTH_SUCCESS_INVALID")
            target = event["target_slot"]
            if target != self.pending_slot:
                fail("HEALTH_TARGET_MISMATCH")
            slot = self.slots[target]
            if slot.state != "booting" or slot.rollback_index is None:
                fail("HEALTH_TARGET_NOT_BOOTING")
            old = self.active_slot
            self.slots[old].healthy = True
            self.slots[old].state = "healthy"
            slot.state = "healthy"
            slot.healthy = True
            self.active_slot = target
            self.previous_healthy_slot = old
            self.secure_rollback_index = slot.rollback_index
            self.pending_slot = None
            self.phase = "idle"
            self.last_outcome = "update_committed_after_health"
            return
        if kind == "health_failure":
            if set(event) != {"kind", "target_slot", "reason"} or self.phase != "awaiting_health":
                fail("HEALTH_FAILURE_INVALID")
            if event["target_slot"] != self.pending_slot:
                fail("HEALTH_TARGET_MISMATCH")
            if not isinstance(event["reason"], str) or not event["reason"]:
                fail("HEALTH_FAILURE_REASON_REQUIRED")
            self.slots[self.pending_slot].state = "failed"
            self.slots[self.pending_slot].healthy = False
            self.phase = "rollback_required"
            self.last_outcome = "health_failure"
            return
        if kind == "rollback":
            if set(event) != {"kind", "failed_slot", "healthy_slot", "reason"}:
                fail("ROLLBACK_EVENT_FIELD_SET_MISMATCH")
            if self.phase not in {"rollback_required", "awaiting_health", "pending_boot"}:
                fail("ROLLBACK_NOT_REQUIRED")
            if event["healthy_slot"] != self.active_slot or not self.slots[self.active_slot].healthy:
                fail("ROLLBACK_HEALTHY_SLOT_MISMATCH")
            failed_slot = event["failed_slot"]
            if failed_slot not in {"A", "B"} or failed_slot == self.active_slot:
                fail("ROLLBACK_FAILED_SLOT_INVALID")
            self.slots[failed_slot].state = "failed"
            self.slots[failed_slot].healthy = False
            self.pending_slot = None
            self.phase = "idle"
            self.last_outcome = "rolled_back_to_previous_healthy_slot"
            return
        if kind == "discard_partial":
            if set(event) != {"kind", "target_slot", "reason"}:
                fail("DISCARD_PARTIAL_FIELD_SET_MISMATCH")
            target = event["target_slot"]
            slot = self.slots.get(target)
            if target == self.active_slot or slot is None or slot.state != "partial":
                fail("DISCARD_TARGET_NOT_PARTIAL_INACTIVE")
            self.slots[target] = Slot("empty")
            self.pending_slot = None
            self.phase = "idle"
            self.last_outcome = "partial_inactive_slot_discarded"
            return
        fail("UNKNOWN_UPDATE_EVENT", str(kind))

    def current_version(self) -> int:
        value = self.slots[self.active_slot].version
        if value is None:
            fail("ACTIVE_SLOT_VERSION_MISSING")
        return value

    def stage(
        self,
        manifest: dict[str, Any],
        image: bytes,
        trust: dict[str, Any],
        *,
        now_epoch: int,
        available_bytes: int,
        write_limit_bytes: int | None = None,
        stop_after: str | None = None,
    ) -> str:
        verified = verify_update_manifest(
            manifest,
            image,
            trust,
            hardware_profile=self.hardware_profile,
            current_version=self.current_version(),
            secure_rollback_index=self.secure_rollback_index,
            now_epoch=now_epoch,
        )
        if not isinstance(available_bytes, int) or available_bytes < len(image):
            fail("DISK_FULL_BEFORE_STAGE")
        target = "B" if self.active_slot == "A" else "A"
        self._append({"kind": "stage_intent", "target_slot": target, "manifest": verified})
        if stop_after == "stage_intent":
            return "POWER_LOSS_SIMULATED_AFTER_STAGE_INTENT"
        writable = len(image) if write_limit_bytes is None else max(0, min(write_limit_bytes, len(image)))
        self._append({"kind": "write_progress", "target_slot": target, "bytes_written": writable})
        if writable != len(image):
            fail("DISK_FULL_DURING_INACTIVE_SLOT_WRITE")
        if stop_after == "image_write":
            return "POWER_LOSS_SIMULATED_AFTER_IMAGE_WRITE"
        self._append({"kind": "seal_slot", "target_slot": target})
        if stop_after == "slot_seal":
            return "POWER_LOSS_SIMULATED_AFTER_SLOT_SEAL"
        self._append({"kind": "mark_pending", "target_slot": target})
        if stop_after == "pending_marker":
            return "POWER_LOSS_SIMULATED_AFTER_PENDING_MARKER"
        return "STAGED_AND_PENDING_BOOT"

    def explicitly_mark_sealed_pending(self) -> None:
        if self.phase != "sealed_waiting_explicit_pending":
            fail("NO_SEALED_SLOT_WAITING")
        target = "B" if self.active_slot == "A" else "A"
        self._append({"kind": "mark_pending", "target_slot": target})

    def boot_pending(self) -> None:
        if self.pending_slot is None:
            fail("NO_PENDING_UPDATE")
        if self.boot_attempts >= self.maximum_boot_attempts:
            self._append(
                {
                    "kind": "rollback",
                    "failed_slot": self.pending_slot,
                    "healthy_slot": self.active_slot,
                    "reason": "boot_attempt_limit_reached",
                }
            )
            fail("BOOT_ATTEMPT_LIMIT_REACHED")
        self._append(
            {
                "kind": "boot_attempt",
                "target_slot": self.pending_slot,
                "attempt": self.boot_attempts + 1,
            }
        )

    def report_health(self, healthy: bool, reason: str = "health_check_failed") -> None:
        if self.pending_slot is None:
            fail("NO_PENDING_UPDATE")
        target = self.pending_slot
        if healthy:
            self._append({"kind": "health_success", "target_slot": target})
        else:
            self._append(
                {
                    "kind": "health_failure",
                    "target_slot": target,
                    "reason": reason,
                }
            )
            self._append(
                {
                    "kind": "rollback",
                    "failed_slot": target,
                    "healthy_slot": self.active_slot,
                    "reason": reason,
                }
            )

    def recover_after_power_loss(self) -> str:
        inactive = "B" if self.active_slot == "A" else "A"
        slot = self.slots[inactive]
        if slot.state == "partial":
            self._append(
                {
                    "kind": "discard_partial",
                    "target_slot": inactive,
                    "reason": "power_loss_or_incomplete_stage",
                }
            )
            return "RECOVERED_PREVIOUS_HEALTHY_SLOT_PARTIAL_DISCARDED"
        if self.phase == "sealed_waiting_explicit_pending" and slot.state == "sealed":
            return "PREVIOUS_HEALTHY_SLOT_ACTIVE_SEALED_SLOT_REQUIRES_EXPLICIT_PENDING"
        if self.phase == "pending_boot" and slot.state == "pending":
            return "PREVIOUS_HEALTHY_SLOT_ACTIVE_PENDING_BOOT_MAY_RESUME"
        if self.phase == "awaiting_health" and slot.state == "booting":
            if self.boot_attempts >= self.maximum_boot_attempts:
                self._append(
                    {
                        "kind": "rollback",
                        "failed_slot": inactive,
                        "healthy_slot": self.active_slot,
                        "reason": "power_loss_exhausted_boot_attempts",
                    }
                )
                return "ROLLED_BACK_AFTER_BOOT_ATTEMPT_LIMIT"
            slot.state = "pending"
            self.phase = "pending_boot"
            self.last_outcome = "power_loss_during_boot_pending_retry"
            return "PREVIOUS_HEALTHY_SLOT_ACTIVE_PENDING_BOOT_MAY_RETRY"
        return "NO_UPDATE_RECOVERY_ACTION_REQUIRED"

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema": "trillionnium.desktop.ab-update-snapshot.v1",
            "hardware_profile": self.hardware_profile,
            "active_slot": self.active_slot,
            "previous_healthy_slot": self.previous_healthy_slot,
            "pending_slot": self.pending_slot,
            "phase": self.phase,
            "secure_rollback_index": self.secure_rollback_index,
            "maximum_boot_attempts": self.maximum_boot_attempts,
            "boot_attempts": self.boot_attempts,
            "slots": {key: asdict(value) for key, value in sorted(self.slots.items())},
            "last_outcome": self.last_outcome,
            "recovery_media_required": self.recovery_media_required,
            "journal_record_count": len(self.journal.records),
            "journal_head_sha256": self.journal.records[-1]["record_sha256"] if self.journal.records else "0" * 64,
            "discarded_torn_tail": self.discarded_torn_tail,
            "active_slot_written_during_stage": False,
            "network_used": False,
            "signing_key_available_to_updater": False,
        }

    @classmethod
    def recover(cls, data: bytes) -> "UpdateEngine":
        try:
            records, discarded_tail = UpdateJournal.parse(data)
            engine = cls()
            for record in records:
                engine._apply_event(copy.deepcopy(record["event"]))
                engine.journal.records.append(copy.deepcopy(record))
            engine.discarded_torn_tail = discarded_tail
            return engine
        except UpdateError:
            raise

    @classmethod
    def fail_closed_on_corrupt_journal(cls, data: bytes) -> "UpdateEngine":
        try:
            return cls.recover(data)
        except UpdateError:
            engine = cls()
            engine.phase = "recovery_required"
            engine.recovery_media_required = True
            engine.last_outcome = "corrupt_update_journal"
            return engine


def build_update_manifest_fixture(
    seed: bytes,
    image: bytes,
    *,
    version: int = 2,
    rollback_index: int = 2,
    hardware_profile: str = "trillionnium-x86_64-fixture-v1",
    release_id: str = "release-fixture-2",
) -> tuple[dict[str, Any], bytes]:
    manifest: dict[str, Any] = {
        "schema": "trillionnium.desktop.update-manifest.v1",
        "release_id": release_id,
        "issuer_id": "fixture-update-issuer",
        "issuer_key_id": "fixture-update-key-1",
        "version": version,
        "rollback_index": rollback_index,
        "hardware_profile": hardware_profile,
        "image_sha256": digest_bytes(image),
        "image_bytes": len(image),
        "source_commit": hashlib.sha1(b"fixture source").hexdigest(),
        "sbom_sha256": hashlib.sha256(b"fixture sbom").hexdigest(),
        "provenance_sha256": hashlib.sha256(b"fixture provenance").hexdigest(),
        "minimum_current_version": 1,
        "recovery_compatible": True,
        "signature": {"algorithm": "Ed25519", "value_base64": ""},
    }
    manifest["signature"]["value_base64"] = base64.b64encode(
        ed25519_sign_fixture(seed, signed_payload(manifest))
    ).decode("ascii")
    return manifest, ed25519_public_from_seed(seed)


def build_recovery_manifest_fixture(
    seed: bytes,
    image: bytes,
    *,
    hardware_profile: str = "trillionnium-x86_64-fixture-v1",
    minimum_rollback_index: int = 1,
) -> tuple[dict[str, Any], bytes]:
    manifest: dict[str, Any] = {
        "schema": "trillionnium.desktop.recovery-media-manifest.v1",
        "media_id": "recovery-fixture-1",
        "issuer_id": "fixture-recovery-issuer",
        "issuer_key_id": "fixture-recovery-key-1",
        "hardware_profile": hardware_profile,
        "image_sha256": digest_bytes(image),
        "image_bytes": len(image),
        "minimum_rollback_index": minimum_rollback_index,
        "source_commit": hashlib.sha1(b"fixture recovery source").hexdigest(),
        "provenance_sha256": hashlib.sha256(b"fixture recovery provenance").hexdigest(),
        "automatic_destructive_recovery": False,
        "signature": {"algorithm": "Ed25519", "value_base64": ""},
    }
    manifest["signature"]["value_base64"] = base64.b64encode(
        ed25519_sign_fixture(seed, signed_payload(manifest))
    ).decode("ascii")
    return manifest, ed25519_public_from_seed(seed)


def fixture_trust(update_public: bytes, recovery_public: bytes) -> dict[str, Any]:
    def record(public: bytes) -> dict[str, Any]:
        return {
            "status": "active",
            "public_key_base64": base64.b64encode(public).decode("ascii"),
            "not_before_epoch": 1,
            "expires_at_epoch": 1000,
        }

    return {
        "schema": "trillionnium.desktop.update-key-trust.v1",
        "update_issuers": {
            "fixture-update-issuer": {
                "keys": {"fixture-update-key-1": record(update_public)}
            }
        },
        "recovery_issuers": {
            "fixture-recovery-issuer": {
                "keys": {"fixture-recovery-key-1": record(recovery_public)}
            }
        },
        "revoked_release_ids": [],
    }


def fixture_engine() -> UpdateEngine:
    return UpdateEngine.bootstrap(
        hardware_profile="trillionnium-x86_64-fixture-v1",
        version=1,
        rollback_index=1,
        image_sha256=hashlib.sha256(b"healthy image v1").hexdigest(),
        image_bytes=len(b"healthy image v1"),
        source_commit=hashlib.sha1(b"healthy source v1").hexdigest(),
        sbom_sha256=hashlib.sha256(b"healthy sbom v1").hexdigest(),
        provenance_sha256=hashlib.sha256(b"healthy provenance v1").hexdigest(),
    )


def self_test() -> dict[str, Any]:
    seed_update = bytes.fromhex("9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60")
    seed_recovery = bytes.fromhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb")
    image = b"immutable fixture update image v2"
    recovery_image = b"offline recovery fixture image"
    update, update_public = build_update_manifest_fixture(seed_update, image)
    recovery, recovery_public = build_recovery_manifest_fixture(seed_recovery, recovery_image)
    trust = fixture_trust(update_public, recovery_public)
    engine = fixture_engine()
    engine.stage(update, image, trust, now_epoch=100, available_bytes=4096)
    engine.boot_pending()
    engine.report_health(True)
    recovered = UpdateEngine.recover(engine.journal.serialize())
    if recovered.snapshot() != engine.snapshot():
        raise AssertionError("A/B update journal replay diverged")
    recovery_result = verify_recovery_media(
        recovery,
        recovery_image,
        trust,
        hardware_profile=engine.hardware_profile,
        secure_rollback_index=engine.secure_rollback_index,
        now_epoch=100,
    )
    return {
        "schema": "trillionnium.desktop.ab-update-self-test.v1",
        "status": "PASS_SOURCE_REFERENCE_ONLY",
        "active_slot": engine.active_slot,
        "active_version": engine.current_version(),
        "secure_rollback_index": engine.secure_rollback_index,
        "journal_head_sha256": engine.snapshot()["journal_head_sha256"],
        "recovery_media_status": recovery_result["status"],
        "active_slot_written_during_stage": False,
        "bootloader_slot_switch_integrated": False,
        "secure_rollback_counter_integrated": False,
        "production_update_key_enrolled": False,
        "offline_recovery_media_built": False,
        "network_used": False,
        "release_ready": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract", type=Path, default=CONTRACT_PATH)
    parser.add_argument("--write-result", type=Path)
    args = parser.parse_args()
    contract = json.loads(args.contract.read_text(encoding="utf-8"))
    if contract.get("status") != "SOURCE_CANDIDATE_BLOCKED_UPSTREAM_D6":
        raise SystemExit("D7 contract status widened unexpectedly")
    result = self_test()
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.write_result:
        args.write_result.parent.mkdir(parents=True, exist_ok=True)
        args.write_result.write_text(payload, encoding="utf-8")
    print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
