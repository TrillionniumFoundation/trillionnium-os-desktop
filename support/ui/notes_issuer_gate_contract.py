"""Observe one real issuer frame; never create, verify or sign a grant.

The selected original request and the SignedGrant substring retain their exact
wire bytes. Root's independent same-instance CLI must verify the signature.
"""
import json
import re

from notes_fault_contract import digest, exact_json, fields, require, uint

OPERATION = "runtime.agentd.production_operation"
OPERATIONS = {OPERATION, "runtime.authbus.objective.sign.v1", "runtime.authbus.text.v1",
              "runtime.authbus.human_text.verify.v1"}
MAX_FRAME = 65536


def identifier(value):
    return type(value) is str and re.fullmatch(r"[A-Za-z0-9_.:/-]{1,128}", value) is not None


def octets(value, size, *, nonzero=True):
    require(type(value) is list and len(value) == size
            and all(type(byte) is int and 0 <= byte < 256 for byte in value), "byte_array")
    require(not nonzero or any(value), "zero_digest_or_nonce")
    return value


def binding(value):
    fields(value, ("subject_id", "destination_id", "request_sha256", "scope_sha256", "payload_sha256"))
    require(identifier(value["subject_id"]) and identifier(value["destination_id"]), "binding_identity")
    for key in ("request_sha256", "scope_sha256", "payload_sha256"):
        octets(value[key], 32)
    require(value["destination_id"].startswith("trill.notes:"), "not_a_notes_destination")
    return value


def selector(value):
    fields(value, ("subject_id", "destination_id", "scope_sha256", "exact_binding"))
    require(identifier(value["subject_id"]) and identifier(value["destination_id"])
            and value["destination_id"].startswith("trill.notes:"), "notes_selector_identity")
    octets(value["scope_sha256"], 32)
    if value["exact_binding"] is not None:
        exact = binding(value["exact_binding"])
        require(all(exact[key] == value[key] for key in
                    ("subject_id", "destination_id", "scope_sha256")), "selector_exact_mismatch")
    return value


def head(value):
    fields(value, ("authority_epoch", "revision", "revoked_grant_ids"))
    require(uint(value["authority_epoch"]) and value["authority_epoch"] > 0
            and uint(value["revision"]) and value["revision"] > 0, "head_revision")
    ids = value["revoked_grant_ids"]
    require(type(ids) is list and all(identifier(item) for item in ids)
            and ids == sorted(set(ids)), "head_ids")
    return value


def original_signed(value, expected):
    fields(value, ("grant", "signature"))
    grant = value["grant"]
    fields(grant, ("schema_version", "signer_id", "authority_epoch", "grant_id", "nonce", "binding",
                   "not_before_unix_ms", "expires_at_unix_ms"))
    require(type(grant["schema_version"]) is int and grant["schema_version"] == 1
            and uint(grant["authority_epoch"]) and grant["authority_epoch"] > 0
            and identifier(grant["signer_id"]) and identifier(grant["grant_id"]), "grant_identity")
    require(binding(grant["binding"]) == expected, "grant_request_binding_mismatch")
    octets(grant["nonce"], 32)
    octets(value["signature"], 64, nonzero=False)
    start, end = grant["not_before_unix_ms"], grant["expires_at_unix_ms"]
    require(uint(start) and uint(end) and 0 < end - start <= 300000, "grant_time_shape")
    return grant


def raw_member(raw, name):
    """Extract a top-level member from already strictly validated JSON bytes."""
    text = raw.decode("utf-8")
    decoder, position = json.JSONDecoder(), 0
    while text[position].isspace():
        position += 1
    require(text[position] == "{", "member_object")
    position += 1
    while True:
        while position < len(text) and text[position].isspace():
            position += 1
        key, end = decoder.raw_decode(text, position)
        position = end
        while text[position].isspace():
            position += 1
        require(text[position] == ":", "member_separator")
        position += 1
        while text[position].isspace():
            position += 1
        start = position
        _, position = decoder.raw_decode(text, position)
        if key == name:
            return text[start:position].encode("utf-8")
        while text[position].isspace():
            position += 1
        require(text[position] == ",", "member_not_found")
        position += 1


class IssuerTransaction:
    """Serial framing, starting only at the original idle poll/read-one-byte."""

    def __init__(self, expected_selector):
        self.selector = selector(expected_selector)
        self.completed_other_frames = 0
        self._reset()

    def _reset(self):
        self.request_bytes, self.header = bytearray(), bytearray()
        self.request_length = self.request = self.response_length = self.pending_write = None
        self.body_sent, self.selected, self.first_byte_monotonic = 0, False, None

    def received(self, raw, now):
        require(raw and self.request is None, "unexpected_issuer_read")
        if not self.request_bytes:
            # Root begins its request deadline after this actual read-one exit.
            require(len(raw) == 1, "not_original_first_byte")
            self.first_byte_monotonic = now
        self.request_bytes.extend(raw)
        require(len(self.request_bytes) <= MAX_FRAME + 4, "issuer_request_bound")
        if len(self.request_bytes) >= 4 and self.request_length is None:
            self.request_length = int.from_bytes(self.request_bytes[:4], "big")
            require(0 < self.request_length <= MAX_FRAME, "issuer_request_length")
        if self.request_length is None:
            return
        require(len(self.request_bytes) <= self.request_length + 4, "multiple_issuer_frames")
        if len(self.request_bytes) != self.request_length + 4:
            return
        value = exact_json(bytes(self.request_bytes[4:]), MAX_FRAME)
        require(type(value.get("schema_version")) is int and value["schema_version"] == 1
                and value.get("operation") in OPERATIONS, "unsupported_issuer_request")
        self.request = value
        if value["operation"] == OPERATION:
            fields(value, ("schema_version", "operation", "binding"))
            require(self.request_length <= 16384, "final_use_request_bound")
            actual = binding(value["binding"])
            self.selected = all(actual[key] == self.selector[key] for key in
                                ("subject_id", "destination_id", "scope_sha256"))
            if self.selected:
                exact = self.selector["exact_binding"]
                require(exact is None or exact == actual, "selected_request_exact_mismatch")

    def write_entry(self, raw, length):
        require(self.request is not None and self.pending_write is None, "reply_before_original_request")
        require(0 < length <= MAX_FRAME, "issuer_reply_syscall_bound")
        if len(self.header) < 4:
            require(raw is not None and len(raw) == length <= 4 - len(self.header), "issuer_header_boundary")
            self.pending_write = ("header", bytes(raw), length)
            return None
        require(length <= self.response_length - self.body_sent, "issuer_body_bound")
        self.pending_write = ("body", None, length)
        if not self.selected:
            return None
        require(self.body_sent == 0 and length == self.response_length
                and raw is not None and len(raw) == length, "not_complete_first_grant_body")
        response = exact_json(raw, MAX_FRAME)
        fields(response, ("schema_version", "revocations", "grant", "denial_reason"))
        require(type(response["schema_version"]) is int and response["schema_version"] == 1
                and response["grant"] is not None and response["denial_reason"] is None, "not_a_granted_response")
        actual_binding = self.request["binding"]
        grant = original_signed(response["grant"], actual_binding)
        revocations = head(response["revocations"])
        require(revocations["authority_epoch"] == grant["authority_epoch"]
                and grant["grant_id"] not in revocations["revoked_grant_ids"], "grant_already_revoked_or_wrong_epoch")
        signed_raw = raw_member(raw, "grant")
        require(len(signed_raw) <= 8192, "original_artifact_bound")
        return {"boundary": "four_real_header_bytes_zero_grant_body_bytes",
                "request_raw": bytes(self.request_bytes[4:]), "response_raw": bytes(raw),
                "signed_raw": signed_raw, "signed": response["grant"], "head": revocations,
                "request_sha256": digest(bytes(self.request_bytes[4:])), "response_sha256": digest(raw),
                "signed_grant_sha256": digest(signed_raw), "binding": actual_binding,
                "first_byte_monotonic": self.first_byte_monotonic,
                "fresh_or_unspent_proven_by_parser": False}

    def write_exit(self, count):
        require(self.pending_write is not None, "unpaired_issuer_write")
        kind, raw, length = self.pending_write
        self.pending_write = None
        require(0 < count <= length, "issuer_write_failed")
        if kind == "header":
            self.header.extend(raw[:count])
            if len(self.header) == 4:
                self.response_length = int.from_bytes(self.header, "big")
                require(0 < self.response_length <= MAX_FRAME, "issuer_response_length")
        else:
            self.body_sent += count
            if self.body_sent == self.response_length:
                self.completed_other_frames += 1
                self._reset()
