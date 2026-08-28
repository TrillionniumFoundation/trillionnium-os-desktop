"""Connected-stream AgentPort bridge reference core."""
from __future__ import annotations

import dataclasses, hashlib, secrets, socket, time
from typing import Callable

import agent_transport_reference as transport
import browser_codec_reference as codec
from browser_codec_reference.response import ERROR_RETRY

SERVER_CEILING_SECONDS = 2.0

class BridgeError(ValueError): pass

@dataclasses.dataclass(frozen=True, slots=True)
class DispatchContext:
    peer_pid: int
    peer_uid: int
    peer_gid: int
    transport_sequence: int
    canonical_request_sha256: str
    effect_class: str
    accepted_monotonic: float
    effective_deadline_monotonic: float

@dataclasses.dataclass(frozen=True, slots=True)
class HandlerReply:
    result: dict[str, object] | None = None
    error: dict[str, object] | None = None

    def validate(self) -> None:
        if (self.result is None) == (self.error is None):
            raise BridgeError("handler reply must contain exactly one result or error")
        if self.result is not None and not isinstance(self.result, dict):
            raise BridgeError("handler result must be an object")
        if self.error is not None:
            if set(self.error) - {"code", "message", "retry", "details"}:
                raise BridgeError("handler error has unknown members")
            if not {"code", "message", "retry"} <= set(self.error):
                raise BridgeError("handler error is incomplete")
            code = self.error["code"]
            if code not in ERROR_RETRY or self.error["retry"] != ERROR_RETRY[code]:
                raise BridgeError("handler error retry policy mismatch")
            if not isinstance(self.error["message"], str) or not self.error["message"]:
                raise BridgeError("handler error message is invalid")
            if "details" in self.error and not isinstance(self.error["details"], dict):
                raise BridgeError("handler error details must be an object")

@dataclasses.dataclass(frozen=True, slots=True)
class BridgeOutcome:
    peer_pid: int
    request_id: str | None
    transport_sequence: int | None
    canonical_request_sha256: str | None
    canonical_response_sha256: str | None
    effect_class: str | None
    handler_invocations: int
    response_committed: bool
    late_result_discarded: bool
    failure_class: str | None

def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0: raise transport.DeadlineExceeded("bridge deadline expired")
    return remaining

def _effective_deadline(request, accepted_mono, accepted_wall_ms, ceiling):
    deadline = accepted_mono + ceiling
    if "deadline_unix_ms" in request:
        request_remaining = (int(request["deadline_unix_ms"]) - accepted_wall_ms) / 1000.0
        if request_remaining <= 0: raise transport.DeadlineExceeded("request deadline already expired")
        deadline = min(deadline, accepted_mono + request_remaining)
    return deadline

def _response_envelope(request, reply: HandlerReply):
    response = {"protocol": request["protocol"], "request_id": request["request_id"], "ok": reply.result is not None}
    if "session_id" in request:
        response["session_id"] = request["session_id"]
        response["session_generation"] = request["session_generation"]
    if reply.result is not None: response["result"] = reply.result
    else: response["error"] = reply.error
    return response

def serve_connected(
    stream: socket.socket,
    peer_policy: transport.PeerPolicy,
    handler: Callable[[dict[str, object], DispatchContext], HandlerReply],
    server_ceiling_seconds: float = SERVER_CEILING_SECONDS,
) -> BridgeOutcome:
    accepted_mono = time.monotonic(); accepted_wall_ms = int(time.time() * 1000)
    outer_deadline = accepted_mono + server_ceiling_seconds
    peer = transport.peer_identity(stream); peer_policy.authorize(peer)
    nonce = secrets.token_bytes(transport.NONCE_BYTES)
    request_id = None; sequence = None; request_sha = None; effect = None; invocations = 0
    try:
        transport.send_frame(stream, transport.Frame(transport.KIND_CHALLENGE, 0, nonce, transport.CHALLENGE_PAYLOAD), _remaining(outer_deadline))
        frame = transport.recv_frame(stream, _remaining(outer_deadline)); sequence = frame.sequence
        guard = transport.SequenceGuard(); guard.accept(frame.sequence)
        if frame.kind != transport.KIND_REQUEST: raise BridgeError("expected one request frame")
        if frame.session_nonce != nonce: raise BridgeError("request nonce mismatch")
        request, effect, request_sha = codec.decode_request(frame.payload); request_id = str(request["request_id"])
        effective_deadline = _effective_deadline(request, accepted_mono, accepted_wall_ms, server_ceiling_seconds)
        context = DispatchContext(peer.pid, peer.uid, peer.gid, frame.sequence, request_sha, effect, accepted_mono, effective_deadline)
        invocations += 1; reply = handler(request, context); reply.validate()
        if time.monotonic() >= effective_deadline:
            return BridgeOutcome(peer.pid, request_id, sequence, request_sha, None, effect, invocations, False, True, "late_result")
        response = _response_envelope(request, reply); encoded = codec.encode_response(response)
        response_sha = hashlib.sha256(encoded).hexdigest()
        transport.send_frame(stream, transport.Frame(transport.KIND_RESPONSE, frame.sequence, nonce, encoded), _remaining(effective_deadline))
        return BridgeOutcome(peer.pid, request_id, sequence, request_sha, response_sha, effect, invocations, True, False, None)
    except Exception as error:
        return BridgeOutcome(peer.pid, request_id, sequence, request_sha, None, effect, invocations, False, False, type(error).__name__)
    finally:
        stream.close()

def call_connected(stream, peer_policy, request, timeout_seconds=SERVER_CEILING_SECONDS):
    peer_policy.authorize(transport.peer_identity(stream))
    challenge = transport.recv_frame(stream, timeout_seconds)
    if challenge.kind != transport.KIND_CHALLENGE or challenge.sequence != 0: raise BridgeError("invalid challenge frame")
    encoded_request = codec.encode_request(request)
    transport.send_frame(stream, transport.Frame(transport.KIND_REQUEST, 1, challenge.session_nonce, encoded_request), timeout_seconds)
    try: response = transport.recv_frame(stream, timeout_seconds)
    except transport.TransportError: return None, None, encoded_request
    if response.kind != transport.KIND_RESPONSE or response.sequence != 1: raise BridgeError("invalid response frame")
    if response.session_nonce != challenge.session_nonce: raise BridgeError("response nonce mismatch")
    value, digest = codec.decode_response(response.payload)
    return value, digest, encoded_request

def default_handler(request, context: DispatchContext):
    if context.effect_class == "potential_external_effect":
        return HandlerReply(error={"code":"policy_denied", "message":"external mutation is disabled", "retry":"after_explicit_policy_change"})
    return HandlerReply(result={"accepted": True, "operation": request["operation"]["type"]})
