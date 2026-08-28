#!/usr/bin/env python3
"""Independent standard-library reference for the D0C-04 connected AgentPort.

This is not a product listener. It uses an AF_UNIX socketpair, Linux peer
credentials, the fixed transport frame, strict canonical JSON and one handler
invocation to exercise the mechanism/evidence boundary.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import socket
import struct
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

MAGIC = b"HEPTA001"
VERSION = 1
CHALLENGE = 1
REQUEST = 2
RESPONSE = 3
HEADER = struct.Struct("!8sHBBQI32s32s")
MAX_PAYLOAD = 262_144
CHALLENGE_PAYLOAD = b"trillionnium.desktop.agent-transport.v1"
PROTOCOL = "trillionnium.desktop.browser-api.v1"
NONCE = bytes([0x5A]) * 32


class ReferenceError(Exception):
    pass


class DuplicateMember(ReferenceError):
    pass


def sha256(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()


def canonical(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def strict_json(data: bytes) -> Any:
    if not data or len(data) > MAX_PAYLOAD or data.startswith(b"\xef\xbb\xbf"):
        raise ReferenceError("message bound")

    def pairs(values: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in values:
            if key in output:
                raise DuplicateMember(key)
            output[key] = value
        return output

    value = json.loads(data.decode("utf-8"), object_pairs_hook=pairs)
    if canonical(value) != data:
        raise ReferenceError("non-canonical")
    return value


def peer_identity(stream: socket.socket) -> tuple[int, int, int]:
    encoded = stream.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
    pid, uid, gid = struct.unpack("3i", encoded)
    return pid, uid, gid


def write_frame(
    stream: socket.socket,
    kind: int,
    sequence: int,
    nonce: bytes,
    payload: bytes,
) -> None:
    if len(payload) > MAX_PAYLOAD:
        raise ReferenceError("payload too large")
    header = HEADER.pack(
        MAGIC,
        VERSION,
        kind,
        0,
        sequence,
        len(payload),
        nonce,
        sha256(payload),
    )
    stream.sendall(header + payload)


def read_exact(stream: socket.socket, size: int, deadline: float) -> bytes:
    output = bytearray()
    while len(output) < size:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("absolute deadline")
        stream.settimeout(remaining)
        chunk = stream.recv(size - len(output))
        if not chunk:
            raise EOFError("truncated frame")
        output.extend(chunk)
    return bytes(output)


def read_frame(stream: socket.socket, deadline: float) -> tuple[int, int, bytes, bytes]:
    header = read_exact(stream, HEADER.size, deadline)
    magic, version, kind, flags, sequence, length, nonce, digest = HEADER.unpack(header)
    if magic != MAGIC or version != VERSION or flags != 0:
        raise ReferenceError("frame header")
    if length > MAX_PAYLOAD:
        raise ReferenceError("payload too large")
    payload = read_exact(stream, length, deadline)
    if sha256(payload) != digest:
        raise ReferenceError("payload digest")
    return kind, sequence, nonce, payload


def effect_class(request: dict[str, Any]) -> str:
    operation = request["operation"]
    kind = operation["type"]
    if kind in {"health", "session_snapshot", "page_observe", "page_wait", "page_extract"}:
        return "observation"
    if kind in {"session_create", "session_close"}:
        return "local_interaction"
    if kind == "page_act" and operation["action"]["type"] == "scroll":
        return "local_interaction"
    return "potential_external_effect"


def validate_binding(request: dict[str, Any]) -> None:
    if set(request) - {
        "protocol",
        "request_id",
        "session_id",
        "session_generation",
        "deadline_unix_ms",
        "operation",
    }:
        raise ReferenceError("unknown request field")
    if request.get("protocol") != PROTOCOL:
        raise ReferenceError("protocol")
    kind = request["operation"]["type"]
    bound = "session_id" in request or "session_generation" in request
    if kind in {"health", "session_create"}:
        if bound:
            raise ReferenceError("unexpected session binding")
    elif (
        not isinstance(request.get("session_id"), str)
        or isinstance(request.get("session_generation"), bool)
        or not isinstance(request.get("session_generation"), int)
        or request["session_generation"] <= 0
    ):
        raise ReferenceError("missing session binding")


def build_response(request: dict[str, Any], result: dict[str, Any] | None, error: dict[str, Any] | None) -> bytes:
    if (result is None) == (error is None):
        raise ReferenceError("invalid handler shape")
    response: dict[str, Any] = {
        "ok": result is not None,
        "protocol": PROTOCOL,
        "request_id": request["request_id"],
    }
    if "session_id" in request:
        response["session_id"] = request["session_id"]
        response["session_generation"] = request["session_generation"]
    if result is not None:
        response["result"] = result
    else:
        response["error"] = error
    return canonical(response)


@dataclass
class Handler:
    calls: int = 0
    sleep_seconds: float = 0.0
    invalid_shape: bool = False

    def __call__(self, request: dict[str, Any], effect: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        self.calls += 1
        if self.sleep_seconds:
            time.sleep(self.sleep_seconds)
        if self.invalid_shape:
            return {}, {}
        if request["operation"]["type"] == "health":
            return {
                "agent_port_ready": True,
                "browser_runtime_available": False,
                "mechanism_only": True,
            }, None
        if effect == "potential_external_effect":
            return None, {
                "code": "policy_denied",
                "message": "external-effect authority is closed in D0",
                "retry": "after_explicit_policy_change",
            }
        return None, {
            "code": "unsupported",
            "message": "BrowserActor and Servo runtime are not implemented",
            "retry": "after_upgrade",
        }


def serve_once(
    stream: socket.socket,
    expected_uid: int,
    handler: Handler,
    ceiling: float = 1.0,
) -> dict[str, Any]:
    accepted = time.monotonic()
    deadline = accepted + ceiling
    pid, uid, gid = peer_identity(stream)
    if uid != expected_uid:
        raise ReferenceError("peer uid")
    write_frame(stream, CHALLENGE, 0, NONCE, CHALLENGE_PAYLOAD)
    kind, sequence, nonce, payload = read_frame(stream, deadline)
    if kind != REQUEST or sequence != 1 or nonce != NONCE:
        raise ReferenceError("request binding")
    request = strict_json(payload)
    validate_binding(request)
    effect = effect_class(request)
    result, error = handler(request, effect)
    if time.monotonic() >= deadline:
        raise TimeoutError("late handler result")
    response = build_response(request, result, error)
    if time.monotonic() >= deadline:
        raise TimeoutError("late response")
    write_frame(stream, RESPONSE, sequence, nonce, response)
    return {
        "pid": pid,
        "uid": uid,
        "gid": gid,
        "sequence": sequence,
        "request_sha256": sha256(payload).hex(),
        "response_sha256": sha256(response).hex(),
        "effect_class": effect,
    }


def round_trip(request: dict[str, Any], handler: Handler, ceiling: float = 1.0) -> tuple[dict[str, Any], dict[str, Any]]:
    client, server = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    holder: dict[str, Any] = {}
    errors: list[BaseException] = []

    def target() -> None:
        try:
            holder.update(serve_once(server, os.getuid(), handler, ceiling))
        except BaseException as error:  # evidence harness preserves exact failure
            errors.append(error)
        finally:
            server.close()

    thread = threading.Thread(target=target)
    thread.start()
    deadline = time.monotonic() + ceiling
    kind, sequence, nonce, challenge = read_frame(client, deadline)
    assert (kind, sequence, nonce, challenge) == (CHALLENGE, 0, NONCE, CHALLENGE_PAYLOAD)
    payload = canonical(request)
    write_frame(client, REQUEST, 1, nonce, payload)
    kind, sequence, response_nonce, response = read_frame(client, deadline)
    assert (kind, sequence, response_nonce) == (RESPONSE, 1, nonce)
    thread.join()
    client.close()
    if errors:
        raise errors[0]
    return strict_json(response), holder


def health_request() -> dict[str, Any]:
    return {
        "operation": {"type": "health"},
        "protocol": PROTOCOL,
        "request_id": "reference:health:1",
    }


def navigate_request() -> dict[str, Any]:
    return {
        "operation": {
            "expected_document_generation": 1,
            "target": {"type": "external_https", "url": "https://example.com/"},
            "type": "page_navigate",
        },
        "protocol": PROTOCOL,
        "request_id": "reference:navigate:1",
        "session_generation": 1,
        "session_id": "session-reference",
    }


def run_checks() -> dict[str, Any]:
    passed: list[str] = []

    handler = Handler()
    response, evidence = round_trip(health_request(), handler)
    assert handler.calls == 1
    passed.append("exactly_one_dispatch")
    assert response["request_id"] == "reference:health:1" and response["protocol"] == PROTOCOL
    passed.append("request_response_binding")
    assert len(evidence["request_sha256"]) == 64
    passed.append("canonical_request_sha256")
    assert len(evidence["response_sha256"]) == 64
    passed.append("canonical_response_sha256")
    assert evidence["pid"] > 0 and evidence["uid"] == os.getuid()
    passed.append("peer_identity")
    assert evidence["sequence"] == 1
    passed.append("transport_sequence")
    assert evidence["effect_class"] == "observation"
    passed.append("observation_effect_propagation")

    handler = Handler()
    response, evidence = round_trip(navigate_request(), handler)
    assert evidence["effect_class"] == "potential_external_effect"
    passed.append("navigation_effect_propagation")
    assert response["ok"] is False and response["error"]["code"] == "policy_denied"
    passed.append("navigation_default_denial")
    assert response["session_id"] == "session-reference" and response["session_generation"] == 1
    passed.append("response_session_binding")

    client, server = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    late_errors: list[BaseException] = []
    thread = threading.Thread(
        target=lambda: _capture(late_errors, lambda: serve_once(server, os.getuid(), Handler(sleep_seconds=0.03), 0.01))
    )
    thread.start()
    _, _, nonce, _ = read_frame(client, time.monotonic() + 1)
    write_frame(client, REQUEST, 1, nonce, canonical(health_request()))
    thread.join()
    client.close()
    server.close()
    assert late_errors and isinstance(late_errors[0], TimeoutError)
    passed.append("late_result_suppression")

    duplicate = b'{"operation":{"type":"health"},"protocol":"trillionnium.desktop.browser-api.v1","request_id":"a","request_id":"a"}'
    handler = Handler()
    client, server = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    duplicate_errors: list[BaseException] = []
    thread = threading.Thread(target=lambda: _capture(duplicate_errors, lambda: serve_once(server, os.getuid(), handler)))
    thread.start()
    _, _, nonce, _ = read_frame(client, time.monotonic() + 1)
    write_frame(client, REQUEST, 1, nonce, duplicate)
    thread.join()
    client.close()
    server.close()
    assert duplicate_errors and isinstance(duplicate_errors[0], DuplicateMember) and handler.calls == 0
    passed.append("duplicate_rejected_before_handler")

    client, server = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    shape_errors: list[BaseException] = []
    thread = threading.Thread(
        target=lambda: _capture(shape_errors, lambda: serve_once(server, os.getuid(), Handler(invalid_shape=True)))
    )
    thread.start()
    _, _, nonce, _ = read_frame(client, time.monotonic() + 1)
    write_frame(client, REQUEST, 1, nonce, canonical(health_request()))
    thread.join()
    client.close()
    server.close()
    assert shape_errors and isinstance(shape_errors[0], ReferenceError)
    passed.append("invalid_handler_shape_suppression")

    assert len(passed) == 13
    return {
        "schema": "trillionnium.desktop.d0c04-agent-port-bridge-reference-result.v1",
        "status": "PASS",
        "test_count": len(passed),
        "checks": passed,
        "python_source_compilation": "PASS",
        "connected_AF_UNIX_socketpair": "PASS",
        "SO_PEERCRED": "PASS",
        "product_listener_created": False,
        "browser_actor_called": False,
        "servo_called": False,
        "external_effect_authorized": False,
        "claim_level": "independent_reference_not_Rust_product_execution",
    }


def _capture(errors: list[BaseException], action: Callable[[], Any]) -> None:
    try:
        action()
    except BaseException as error:  # evidence harness preserves exact failure
        errors.append(error)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-evidence", type=Path)
    arguments = parser.parse_args()
    result = run_checks()
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if arguments.write_evidence:
        arguments.write_evidence.parent.mkdir(parents=True, exist_ok=True)
        arguments.write_evidence.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
