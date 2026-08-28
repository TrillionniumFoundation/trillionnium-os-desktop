"""Strict Browser API response validation."""
from __future__ import annotations

import hashlib
from .canonical import CodecError, PROTOCOL, canonical, decode_unique, exact_object, identifier, integer, require_canonical, text

ERROR_RETRY = {
    "invalid_request":"never", "unsupported":"after_upgrade", "policy_denied":"after_explicit_policy_change",
    "stale_session":"recreate_session", "stale_document":"observe_again", "stale_snapshot":"observe_again",
    "queue_full":"bounded_backoff", "human_control_active":"after_human_release", "ime_composition_active":"after_ime_end",
    "modal_blocked":"after_modal_resolution", "navigation_in_progress":"after_navigation",
    "capability_pending":"after_capability_resolution", "cancelled":"caller_decides",
    "deadline_exceeded":"caller_decides", "browser_crashed":"after_recovery",
    "indeterminate":"never_automatic", "internal":"after_diagnosis",
}

def validate_response(value):
    value = exact_object(value, {"protocol", "request_id", "ok"}, {"session_id", "session_generation", "result", "error"})
    if value["protocol"] != PROTOCOL: raise CodecError("protocol mismatch")
    identifier(value["request_id"])
    if type(value["ok"]) is not bool: raise CodecError("ok must be boolean")
    paired = ("session_id" in value, "session_generation" in value)
    if paired[0] != paired[1]: raise CodecError("response session binding must be paired")
    if paired[0]: identifier(value["session_id"]); integer(value["session_generation"], 1)
    if value["ok"]:
        if "result" not in value or "error" in value or not isinstance(value["result"], dict):
            raise CodecError("successful response shape")
    else:
        if "error" not in value or "result" in value: raise CodecError("failed response shape")
        error = exact_object(value["error"], {"code", "message", "retry"}, {"details"})
        code = text(error["code"], 1, 64)
        if code not in ERROR_RETRY or text(error["retry"], 1, 64) != ERROR_RETRY[code]:
            raise CodecError("error retry policy mismatch")
        text(error["message"], 1, 1024)
        if "details" in error and not isinstance(error["details"], dict):
            raise CodecError("error details must be object")

def decode_response(encoded):
    value = decode_unique(encoded)
    if not isinstance(value, dict): raise CodecError("response root must be object")
    validate_response(value); wire = require_canonical(encoded, value, "response")
    return value, hashlib.sha256(wire).hexdigest()

def encode_response(value):
    validate_response(value); return canonical(value)
