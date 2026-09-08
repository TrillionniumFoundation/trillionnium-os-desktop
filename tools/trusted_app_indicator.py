#!/usr/bin/env python3
"""Verification helpers for D5 visible trust-indicator receipts."""
from __future__ import annotations

import copy
import hashlib
import json
from typing import Any


class IndicatorError(ValueError):
    pass


def canonical_json(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n").encode("utf-8")


def verify_trust_indicator(indicator: dict[str, Any]) -> None:
    expected_fields = {
        "schema",
        "app_id",
        "version",
        "publisher_id",
        "publisher_key_id",
        "content_root_sha256",
        "synthetic_origin",
        "revocation_epoch",
        "trust_state",
        "receipt_sha256",
    }
    if not isinstance(indicator, dict) or set(indicator) != expected_fields:
        raise IndicatorError("TRUST_INDICATOR_FIELD_SET_MISMATCH")
    if indicator.get("schema") != "trillionnium.desktop.trusted-app-indicator.v1":
        raise IndicatorError("TRUST_INDICATOR_SCHEMA_MISMATCH")
    if indicator.get("trust_state") != "OFFLINE_SIGNATURE_AND_CONTENT_VERIFIED":
        raise IndicatorError("TRUST_INDICATOR_STATE_MISMATCH")
    unsigned = copy.deepcopy(indicator)
    claimed = unsigned.pop("receipt_sha256")
    actual = hashlib.sha256(canonical_json(unsigned)).hexdigest()
    if claimed != actual:
        raise IndicatorError("TRUST_INDICATOR_HASH_MISMATCH")
