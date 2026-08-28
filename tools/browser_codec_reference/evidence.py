"""Deterministic fixtures, negative corpus, and evidence generation."""
from __future__ import annotations

import hashlib, json
from pathlib import Path
from .canonical import CodecError, MAX_BYTES, MAX_DEPTH, PROTOCOL, canonical
from .request import decode_request
from .response import decode_response

def fixtures():
    digest = "a" * 64
    target = {
        "session_generation": 3, "document_generation": 7,
        "semantic_snapshot_revision": 11, "frame_id": "main", "role": "button",
        "accessible_name_sha256": digest, "structural_fingerprint": "b" * 64,
    }
    return [
        {"protocol": PROTOCOL, "request_id": "golden:health:1", "operation": {"type": "health"}},
        {"protocol": PROTOCOL, "request_id": "golden:create:1", "operation": {"type": "session_create", "profile": {"profile_id": "ephemeral-default", "persistence": "ephemeral"}, "ui_mode": "headed"}},
        {"protocol": PROTOCOL, "request_id": "golden:navigate:1", "session_id": "session-1", "session_generation": 3, "operation": {"type": "page_navigate", "target": {"type": "external_https", "url": "https://example.test/path"}, "expected_document_generation": 7}},
        {"protocol": PROTOCOL, "request_id": "golden:click:1", "session_id": "session-1", "session_generation": 3, "operation": {"type": "page_act", "target": target, "action": {"type": "click"}}},
    ]

def self_test():
    tests = []
    def passes(name, function): function(); tests.append(name)
    def rejects(name, function):
        try: function()
        except CodecError: tests.append(name); return
        raise AssertionError(f"{name} did not fail closed")
    health, _, navigate, click = fixtures()
    passes("canonical-roundtrip", lambda: decode_request(canonical(health)))
    rejects("whitespace", lambda: decode_request(b'{ "operation":{"type":"health"},"protocol":"trillionnium.desktop.browser-api.v1","request_id":"x"}'))
    rejects("duplicate-top", lambda: decode_request(b'{"protocol":"x","protocol":"y","request_id":"x","operation":{"type":"health"}}'))
    rejects("duplicate-nested", lambda: decode_request(b'{"operation":{"type":"health","type":"health"},"protocol":"trillionnium.desktop.browser-api.v1","request_id":"x"}'))
    rejects("unknown-top", lambda: decode_request(canonical(health | {"x": 1})))
    rejects("unknown-op-member", lambda: decode_request(canonical(health | {"operation": {"type": "health", "x": 1}})))
    rejects("unbound-has-session", lambda: decode_request(canonical(health | {"session_id": "s", "session_generation": 1})))
    rejects("bound-no-session", lambda: decode_request(canonical({"protocol": PROTOCOL, "request_id": "x", "operation": navigate["operation"]})))
    rejects("partial-session", lambda: decode_request(canonical({key: value for key, value in navigate.items() if key != "session_generation"})))
    rejects("bool-integer", lambda: decode_request(canonical(navigate | {"session_generation": True})))
    stale = json.loads(json.dumps(click)); stale["operation"]["target"]["semantic_snapshot_revision"] = 0
    rejects("snapshot-zero", lambda: decode_request(canonical(stale)))
    bad = json.loads(json.dumps(navigate)); bad["operation"]["target"]["url"] = "http://example.test/"
    rejects("external-http", lambda: decode_request(canonical(bad)))
    bad = json.loads(json.dumps(navigate)); bad["operation"]["target"]["url"] = "https://user@example.test/"
    rejects("external-userinfo", lambda: decode_request(canonical(bad)))
    local = json.loads(json.dumps(navigate)); local["operation"]["target"] = {"type": "local_http_fixture", "url": "http://192.168.1.2/"}
    rejects("fixture-private-lan", lambda: decode_request(canonical(local)))
    passes("navigate-effect", lambda: None if decode_request(canonical(navigate))[1] == "potential_external_effect" else (_ for _ in ()).throw(AssertionError()))
    passes("click-effect", lambda: None if decode_request(canonical(click))[1] == "potential_external_effect" else (_ for _ in ()).throw(AssertionError()))
    scroll = json.loads(json.dumps(click)); scroll["operation"]["action"] = {"type": "scroll", "delta_x": 0, "delta_y": 1}
    passes("scroll-local", lambda: None if decode_request(canonical(scroll))[1] == "local_interaction" else (_ for _ in ()).throw(AssertionError()))
    huge = json.loads(json.dumps(click)); huge["operation"]["action"] = {"type": "type", "text": "界" * 50_000}
    rejects("utf8-byte-bound", lambda: decode_request(canonical(huge)))
    rejects("oversize-before-parse", lambda: decode_request(b" " * (MAX_BYTES + 1)))
    nested = 0
    for _ in range(MAX_DEPTH + 2): nested = [nested]
    rejects("nesting", lambda: canonical(nested)); rejects("float", lambda: canonical({"value": 1.5}))
    success = {"protocol": PROTOCOL, "request_id": "r", "session_id": "s", "session_generation": 1, "ok": True, "result": {"accepted": True}}
    passes("success-response", lambda: decode_response(canonical(success)))
    rejects("success-result-not-object", lambda: decode_response(canonical(success | {"result": []})))
    failure = {"protocol": PROTOCOL, "request_id": "r", "ok": False, "error": {"code": "policy_denied", "message": "no", "retry": "after_explicit_policy_change"}}
    passes("error-response", lambda: decode_response(canonical(failure)))
    rejects("retry-mismatch", lambda: decode_response(canonical({**failure, "error": {**failure["error"], "retry": "never"}})))
    rejects("response-session-partial", lambda: decode_response(canonical(success | {"session_generation": None})))
    return tests

def build_result(contract_path: Path):
    contract_bytes = contract_path.read_bytes(); contract = json.loads(contract_bytes)
    if contract["protocol"] != PROTOCOL: raise CodecError("contract protocol mismatch")
    requests = []
    for value in fixtures():
        encoded = canonical(value); _, effect, digest = decode_request(encoded)
        requests.append({"request_id": value["request_id"], "effect_class": effect, "canonical_sha256": digest, "canonical_utf8": encoded.decode("utf-8")})
    response_values = [
        {"protocol": PROTOCOL, "request_id": "golden:response:ok:1", "session_id": "session-1", "session_generation": 3, "ok": True, "result": {"accepted": True}},
        {"protocol": PROTOCOL, "request_id": "golden:response:error:1", "ok": False, "error": {"code": "policy_denied", "message": "external mutation is disabled", "retry": "after_explicit_policy_change"}},
    ]
    responses = []
    for value in response_values:
        encoded = canonical(value); _, digest = decode_response(encoded)
        responses.append({"request_id": value["request_id"], "canonical_sha256": digest, "canonical_utf8": encoded.decode("utf-8")})
    tests = self_test()
    return {
        "schema": "trillionnium.desktop.browser-codec.reference-result.v1",
        "status": "PASS", "implementation": "python-standard-library-browser-codec-reference",
        "contract_sha256": hashlib.sha256(contract_bytes).hexdigest(), "test_count": len(tests),
        "tests": tests, "requests": requests, "responses": responses,
        "product_listener_created": False, "browser_dispatched": False, "external_effect_authorized": False,
    }
