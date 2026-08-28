"""Strict Browser API request validation and effect classification."""
from __future__ import annotations

import hashlib
from .canonical import (
    CodecError, DNS_RE, PROTOCOL, canonical, decode_unique, exact_object,
    identifier, integer, require_canonical, safe_url, sha256_hex, text,
)

UNBOUND = {"health", "session_create"}
BOUND = {"session_snapshot", "session_close", "page_navigate", "page_observe", "page_act", "page_wait", "page_extract"}

def element_ref(value):
    value = exact_object(
        value,
        {"session_generation", "document_generation", "semantic_snapshot_revision", "frame_id", "structural_fingerprint"},
        {"backend_node_key", "role", "accessible_name_sha256"},
    )
    integer(value["session_generation"], 1); integer(value["document_generation"], 1)
    integer(value["semantic_snapshot_revision"], 1); identifier(value["frame_id"], 64)
    sha256_hex(value["structural_fingerprint"])
    if "backend_node_key" in value: identifier(value["backend_node_key"])
    if "role" in value: text(value["role"], 1, 128)
    if "accessible_name_sha256" in value: sha256_hex(value["accessible_name_sha256"])

def navigation(value):
    value = exact_object(value, {"type"}, {"publisher", "app_id", "url"})
    kind = value["type"]
    if kind == "trusted_shell": exact_object(value, {"type"})
    elif kind == "trusted_app":
        exact_object(value, {"type", "publisher", "app_id"})
        for field in ("publisher", "app_id"):
            if not DNS_RE.fullmatch(text(value[field], 1, 63)): raise CodecError("invalid DNS label")
    elif kind == "external_https":
        exact_object(value, {"type", "url"}); safe_url(value["url"], True)
    elif kind == "local_http_fixture":
        exact_object(value, {"type", "url"}); safe_url(value["url"], False)
    else: raise CodecError("unknown navigation target")

def validate_request(value):
    value = exact_object(
        value,
        {"protocol", "request_id", "operation"},
        {"session_id", "session_generation", "deadline_unix_ms"},
    )
    if value["protocol"] != PROTOCOL: raise CodecError("protocol mismatch")
    identifier(value["request_id"])
    if "deadline_unix_ms" in value: integer(value["deadline_unix_ms"], 0)
    operation = exact_object(
        value["operation"], {"type"},
        {"profile", "ui_mode", "target", "expected_document_generation", "fields", "action", "condition", "timeout_ms", "schema_id"},
    )
    kind = operation["type"]
    paired = ("session_id" in value, "session_generation" in value)
    if paired[0] != paired[1]: raise CodecError("session binding must be paired")
    if kind in UNBOUND:
        if any(paired): raise CodecError("operation must be unbound")
    elif kind in BOUND:
        if not all(paired): raise CodecError("operation requires session binding")
        identifier(value["session_id"]); integer(value["session_generation"], 1)
    else: raise CodecError("unknown operation")

    if kind == "health": exact_object(operation, {"type"})
    elif kind == "session_create":
        exact_object(operation, {"type", "profile", "ui_mode"})
        profile = exact_object(operation["profile"], {"profile_id", "persistence"})
        identifier(profile["profile_id"])
        if profile["persistence"] not in {"ephemeral", "persistent"} or operation["ui_mode"] != "headed":
            raise CodecError("invalid session create")
    elif kind in {"session_snapshot", "session_close"}: exact_object(operation, {"type"})
    elif kind == "page_navigate":
        exact_object(operation, {"type", "target", "expected_document_generation"})
        navigation(operation["target"]); integer(operation["expected_document_generation"], 1)
    elif kind == "page_observe":
        exact_object(operation, {"type", "fields"}); fields = operation["fields"]
        allowed = {"role", "name", "text", "href", "bounds"}
        if not isinstance(fields, list) or not fields or len(fields) != len(set(fields)) or not set(fields) <= allowed:
            raise CodecError("invalid observation fields")
    elif kind == "page_act":
        exact_object(operation, {"type", "target", "action"}); element_ref(operation["target"])
        action = exact_object(operation["action"], {"type"}, {"text", "key", "delta_x", "delta_y", "value"})
        action_kind = action["type"]
        if action_kind == "click": exact_object(action, {"type"})
        elif action_kind == "type": exact_object(action, {"type", "text"}); text(action["text"], 0, 131072)
        elif action_kind == "press": exact_object(action, {"type", "key"}); text(action["key"], 1, 128)
        elif action_kind == "scroll":
            exact_object(action, {"type", "delta_x", "delta_y"})
            integer(action["delta_x"], -1_000_000, 1_000_000); integer(action["delta_y"], -1_000_000, 1_000_000)
        elif action_kind == "select": exact_object(action, {"type", "value"}); text(action["value"], 0, 65536)
        else: raise CodecError("unknown action")
    elif kind == "page_wait":
        exact_object(operation, {"type", "condition", "timeout_ms"}); integer(operation["timeout_ms"], 1, 300000)
        condition = exact_object(operation["condition"], {"type"}, {"url", "target", "text", "quiet_window_ms"})
        condition_kind = condition["type"]
        if condition_kind == "document_ready": exact_object(condition, {"type"})
        elif condition_kind == "url_equals": exact_object(condition, {"type", "url"}); text(condition["url"], 1, 8192)
        elif condition_kind == "element_present": exact_object(condition, {"type", "target"}); element_ref(condition["target"])
        elif condition_kind == "text_present": exact_object(condition, {"type", "text"}); text(condition["text"], 0, 65536)
        elif condition_kind == "network_idle":
            exact_object(condition, {"type", "quiet_window_ms"}); integer(condition["quiet_window_ms"], 1, 60000)
        else: raise CodecError("unknown wait condition")
    elif kind == "page_extract": exact_object(operation, {"type", "schema_id"}); identifier(operation["schema_id"])

    if kind == "page_navigate": return "potential_external_effect"
    if kind == "page_act": return "local_interaction" if operation["action"]["type"] == "scroll" else "potential_external_effect"
    if kind in {"session_create", "session_close"}: return "local_interaction"
    return "observation"

def decode_request(encoded):
    value = decode_unique(encoded)
    if not isinstance(value, dict): raise CodecError("request root must be object")
    effect = validate_request(value); wire = require_canonical(encoded, value, "request")
    return value, effect, hashlib.sha256(wire).hexdigest()

def encode_request(value):
    validate_request(value); return canonical(value)
