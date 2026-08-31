#!/usr/bin/env python3
"""Validate D8 verification-result receipt integrity and claim ceiling."""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


class HardwareReceiptError(ValueError):
    pass


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def verify_hardware_verification_receipt(result: dict[str, Any]) -> None:
    if not isinstance(result, dict):
        raise HardwareReceiptError("HARDWARE_VERIFICATION_RESULT_OBJECT_REQUIRED")
    required = {
        "schema",
        "status",
        "qualification_id",
        "hardware_profile_id",
        "environment_kind",
        "duration_seconds",
        "metrics",
        "cycles",
        "subsystem_case_counts",
        "security_scenario_count",
        "evidence_manifest_sha256",
        "policy_eligible",
        "physical_hardware_run_completed_by_this_source_gate",
        "independent_hardware_lab_signature_obtained_by_this_source_gate",
        "hardware_beta_promoted",
        "release_ready",
        "verification_receipt_sha256",
    }
    if set(result) != required:
        raise HardwareReceiptError("HARDWARE_VERIFICATION_RESULT_FIELD_SET_MISMATCH")
    if result.get("schema") != "trillionnium.desktop.hardware-qualification-verification-result.v1":
        raise HardwareReceiptError("HARDWARE_VERIFICATION_RESULT_SCHEMA_MISMATCH")
    if result.get("hardware_beta_promoted") is not False:
        raise HardwareReceiptError("SOURCE_VERIFIER_MUST_NOT_PROMOTE_HARDWARE_BETA")
    if result.get("release_ready") is not False:
        raise HardwareReceiptError("SOURCE_VERIFIER_MUST_NOT_CLAIM_RELEASE")
    unsigned = copy.deepcopy(result)
    claimed = unsigned.pop("verification_receipt_sha256")
    actual = hashlib.sha256(canonical_json(unsigned)).hexdigest()
    if claimed != actual:
        raise HardwareReceiptError("HARDWARE_VERIFICATION_RECEIPT_HASH_MISMATCH")
