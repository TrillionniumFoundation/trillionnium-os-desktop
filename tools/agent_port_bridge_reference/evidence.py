"""Socketpair corpus and evidence generator for the AgentPort bridge."""
from __future__ import annotations

import hashlib, json, socket, threading, time
from pathlib import Path

import agent_transport_reference as transport
import browser_codec_reference as codec
from .core import BridgeError, BridgeOutcome, HandlerReply, call_connected, default_handler, serve_connected

def fixture_request(kind):
    if kind == "health":
        return {"protocol": codec.PROTOCOL, "request_id": "bridge:health:1", "operation": {"type": "health"}}
    if kind == "navigate":
        return {"protocol": codec.PROTOCOL, "request_id":"bridge:navigate:1", "session_id":"session-1", "session_generation":3,
            "operation":{"type":"page_navigate", "target":{"type":"external_https", "url":"https://example.test/path"}, "expected_document_generation":7}}
    raise ValueError(kind)

def run_exchange(request, handler, timeout=2.0):
    client, server = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    client_policy = transport.exact_policy(client); server_policy = transport.exact_policy(server)
    outcomes: list[BridgeOutcome] = []
    thread = threading.Thread(target=lambda: outcomes.append(serve_connected(server, server_policy, handler, timeout)))
    thread.start(); response, response_sha, encoded = call_connected(client, client_policy, request, timeout); client.close()
    thread.join(timeout + 0.5)
    if thread.is_alive() or not outcomes: raise BridgeError("bridge thread did not terminate")
    return response, response_sha, encoded, outcomes[0]

def self_test():
    tests=[]
    def record(name, condition):
        if not condition: raise AssertionError(name)
        tests.append(name)
    response, response_sha, encoded, outcome = run_exchange(fixture_request("health"), default_handler)
    record("health-exactly-once", outcome.handler_invocations == 1 and outcome.response_committed)
    record("health-response-bound", response is not None and response["request_id"] == "bridge:health:1")
    record("request-digest-bound", outcome.canonical_request_sha256 == hashlib.sha256(encoded).hexdigest())
    record("response-digest-bound", response_sha == outcome.canonical_response_sha256)
    record("peer-identity-positive", outcome.peer_pid > 0)
    record("transport-sequence-bound", outcome.transport_sequence == 1)
    record("observation-propagated", outcome.effect_class == "observation")
    response, _, _, outcome = run_exchange(fixture_request("navigate"), default_handler)
    record("navigation-effect-propagated", outcome.effect_class == "potential_external_effect")
    record("navigation-default-deny", response is not None and response["ok"] is False and response["error"]["code"] == "policy_denied")
    record("navigation-session-bound", response is not None and response["session_generation"] == 3 and response["session_id"] == "session-1")
    def late_handler(_request, _context): time.sleep(0.04); return HandlerReply(result={"accepted": True})
    expired = fixture_request("health") | {"deadline_unix_ms": int(time.time() * 1000) + 10}
    response, _, _, outcome = run_exchange(expired, late_handler, 0.25)
    record("late-result-not-committed", response is None and outcome.late_result_discarded and not outcome.response_committed)
    invoked = 0
    def counting_handler(_request, _context):
        nonlocal invoked; invoked += 1; return HandlerReply(result={"accepted": True})
    client, server = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    client_policy = transport.exact_policy(client); server_policy = transport.exact_policy(server); outcomes=[]
    thread = threading.Thread(target=lambda: outcomes.append(serve_connected(server, server_policy, counting_handler, 0.5)))
    thread.start(); challenge = transport.recv_frame(client, 0.5)
    duplicate = b'{"operation":{"type":"health","type":"health"},"protocol":"trillionnium.desktop.browser-api.v1","request_id":"x"}'
    transport.send_frame(client, transport.Frame(transport.KIND_REQUEST, 1, challenge.session_nonce, duplicate), 0.5)
    try: transport.recv_frame(client, 0.5)
    except transport.TransportError: pass
    client.close(); thread.join(1.0)
    record("duplicate-rejected-before-handler", invoked == 0 and outcomes and outcomes[0].handler_invocations == 0)
    response, _, _, outcome = run_exchange(fixture_request("health"), lambda _r, _c: HandlerReply())
    record("invalid-handler-shape-not-committed", response is None and outcome.failure_class == "BridgeError")
    return tests

def build_result(contract_path: Path):
    contract_bytes = contract_path.read_bytes(); contract = json.loads(contract_bytes)
    if contract["schema"] != "trillionnium.desktop.agent-port-bridge.v1": raise BridgeError("bridge contract schema mismatch")
    tests = self_test()
    return {"schema":"trillionnium.desktop.agent-port-bridge.reference-result.v1", "status":"PASS",
        "implementation":"python-standard-library-connected-agent-port-reference",
        "contract_sha256":hashlib.sha256(contract_bytes).hexdigest(), "test_count":len(tests), "tests":tests,
        "product_listener_created":False, "browser_actor_called":False, "servo_called":False, "external_effect_authorized":False}
