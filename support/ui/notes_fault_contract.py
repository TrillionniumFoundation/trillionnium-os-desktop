"""Bounded observation of the existing Notes request/reply wire.

This module neither sends requests nor makes an application/owner receipt.
The fault boundary is after the real four-byte length, before any reply body.
"""
import hashlib
import json
import re


class Refused(ValueError):
    pass


def require(condition, reason):
    if not condition:
        raise Refused(reason)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def exact_json(raw, bound):
    require(0 < len(raw) <= bound, "wire_size")
    def pairs(items):
        result = {}
        for key, value in items:
            require(key not in result, "duplicate_json_key")
            result[key] = value
        return result
    def constant(_):
        raise Refused("nonfinite_json")
    try:
        value = json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)
    except (ValueError, UnicodeError) as error:
        raise Refused("invalid_json") from error
    require(type(value) is dict, "json_object_required")
    return value


def fields(value, names):
    require(type(value) is dict and value.keys() == set(names), "wire_fields")


def uint(value):
    return type(value) is int and 0 <= value < 2**64


def target(value):
    fields(value, ("session_instance", "task_id", "incarnation"))
    require(uint(value["task_id"]) and value["task_id"] != 0, "target_task")
    for key in ("session_instance", "incarnation"):
        require(type(value[key]) is str and re.fullmatch(r"[0-9a-f]{32}", value[key]), "target_identity")
    return value


class Transaction:
    """One serial original socket; raw payload hashes never use reserialization."""

    def __init__(self, expected_target, revision, text_sha256):
        self.target = target(expected_target)
        require(uint(revision), "expected_revision")
        require(type(text_sha256) is str and re.fullmatch(r"[0-9a-f]{64}", text_sha256), "expected_text_digest")
        self.revision = revision
        self.text_sha256 = text_sha256
        self._reset()

    def _reset(self):
        self.request_bytes = bytearray()
        self.request_length = None
        self.request = None
        self.selected = False
        self.header = bytearray()
        self.body_sent = 0
        self.response_length = None
        self.pending_write = None

    def received(self, raw):
        require(raw and self.request is None, "unexpected_request_read")
        self.request_bytes.extend(raw)
        require(len(self.request_bytes) <= 8196, "request_bound")
        if len(self.request_bytes) >= 4 and self.request_length is None:
            self.request_length = int.from_bytes(self.request_bytes[:4], "big")
            require(0 < self.request_length <= 8192, "request_length")
        if self.request_length is None:
            return
        require(len(self.request_bytes) <= 4 + self.request_length, "multiple_or_partial_start_frames")
        if len(self.request_bytes) < 4 + self.request_length:
            return
        raw = bytes(self.request_bytes[4:])
        value = exact_json(raw, 8192)
        action = value.get("action")
        require(action == "replace_note", "unsupported_effect_request_action")
        fields(value, ("schema_version", "action", "target", "operation_id", "destination_id", "expected_revision", "text"))
        require(type(value["schema_version"]) is int and value["schema_version"] == 1, "schema_version")
        require(target(value["target"]) == self.target, "request_target_mismatch")
        operation = value["operation_id"]
        require(type(operation) is str and re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", operation), "operation_identity")
        destination = f"trill.notes:{self.target['session_instance']}:{self.target['task_id']}:{self.target['incarnation']}"
        require(value["destination_id"] == destination, "destination_identity")
        require(uint(value["expected_revision"]) and value["expected_revision"] == self.revision, "request_revision_mismatch")
        require(type(value["text"]) is str and len(value["text"].encode()) <= 4096, "text_bound")
        require(digest(value["text"].encode()) == self.text_sha256, "request_text_mismatch")
        self.selected = True
        self.request = value
        self.request_sha256 = digest(raw)

    def write_entry(self, raw):
        """Return an observation only at the complete first Applied body entry."""
        require(self.request is not None and self.pending_write is None, "reply_without_complete_request")
        require(raw, "empty_reply_write")
        if len(self.header) < 4:
            require(len(raw) <= 4 - len(self.header), "reply_header_boundary")
            self.pending_write = ("header", bytes(raw))
            return None
        require(self.response_length is not None, "reply_length_missing")
        require(len(raw) <= self.response_length - self.body_sent, "reply_body_bound")
        self.pending_write = ("body", bytes(raw))
        if not self.selected:
            return None
        require(self.body_sent == 0, "reply_body_already_sent")
        require(len(raw) == self.response_length, "incomplete_applied_body_buffer")
        value = exact_json(raw, 2048)
        fields(value, ("schema_version", "target", "operation_id", "payload_sha256", "result"))
        require(type(value["schema_version"]) is int and value["schema_version"] == 1, "reply_schema")
        require(target(value["target"]) == self.target, "reply_target_mismatch")
        require(value["operation_id"] == self.request["operation_id"], "reply_operation_mismatch")
        require(value["payload_sha256"] == self.request_sha256, "reply_payload_mismatch")
        result = value["result"]
        require(type(result) is dict and result.get("status") == "applied", "selected_reply_not_applied")
        fields(result, ("status", "previous_revision", "revision", "text_sha256"))
        require(uint(result["previous_revision"]) and result["previous_revision"] == self.revision, "applied_predecessor")
        require(uint(result["revision"]) and result["revision"] == self.revision + 1, "applied_revision")
        require(result["text_sha256"] == self.text_sha256, "applied_text_digest")
        return {"boundary": "four_real_header_bytes_zero_body_bytes", "request_bytes": self.request_length,
                "request_sha256": self.request_sha256, "response_bytes": len(raw), "response_sha256": digest(raw),
                "target": self.target, "operation_id": value["operation_id"], "payload_sha256": value["payload_sha256"],
                "result_observed_in_app_buffer": result, "authoritative_owner_receipt": False}

    def write_exit(self, written):
        require(self.pending_write is not None, "unpaired_write_exit")
        kind, raw = self.pending_write
        self.pending_write = None
        require(0 < written <= len(raw), "reply_write_failed_or_invalid")
        if kind == "header":
            self.header.extend(raw[:written])
            if len(self.header) == 4:
                self.response_length = int.from_bytes(self.header, "big")
                require(0 < self.response_length <= 2048, "reply_length")
        else:
            self.body_sent += written
            if self.body_sent == self.response_length:
                self._reset()
