#!/usr/bin/env python3
"""Independent reference implementation for Agent transport v1.

This module intentionally uses only the Python standard library. It is not a
product listener and does not interpret Browser API payloads. It exists to
provide a second implementation of the fixed wire contract and deterministic
fault vectors while the Rust 1.93 execution gate remains unavailable.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import hmac
import json
import socket
import struct
import threading
import time
from pathlib import Path
from typing import Final

PROTOCOL_MAGIC: Final[bytes] = b"HEPTA001"
PROTOCOL_VERSION: Final[int] = 1
HEADER_BYTES: Final[int] = 88
NONCE_BYTES: Final[int] = 32
DIGEST_BYTES: Final[int] = 32
MAX_PAYLOAD_BYTES: Final[int] = 262_144
CHALLENGE_PAYLOAD: Final[bytes] = b"trillionnium.desktop.agent-transport.v1"

KIND_CHALLENGE: Final[int] = 1
KIND_REQUEST: Final[int] = 2
KIND_RESPONSE: Final[int] = 3
KIND_EVENT: Final[int] = 4
KIND_CLOSE: Final[int] = 5
VALID_KINDS: Final[frozenset[int]] = frozenset(
    {KIND_CHALLENGE, KIND_REQUEST, KIND_RESPONSE, KIND_EVENT, KIND_CLOSE}
)

_HEADER = struct.Struct(">8sHBBQI32s32s")
_UCRED = struct.Struct("3i")
assert _HEADER.size == HEADER_BYTES


class TransportError(ValueError):
    """Fail-closed protocol or boundary error."""


class DeadlineExceeded(TransportError):
    """The monotonic absolute deadline expired."""


@dataclasses.dataclass(frozen=True, slots=True)
class PeerIdentity:
    pid: int
    uid: int
    gid: int

    def validate(self) -> None:
        if self.pid <= 0:
            raise TransportError("peer pid must be positive")
        if self.uid < 0 or self.gid < 0:
            raise TransportError("peer uid/gid must be non-negative")


@dataclasses.dataclass(frozen=True, slots=True)
class PeerPolicy:
    expected_uid: int
    expected_pid: int | None = None
    expected_gid: int | None = None

    def authorize(self, actual: PeerIdentity) -> None:
        actual.validate()
        if actual.uid != self.expected_uid:
            raise TransportError("unauthorized peer uid")
        if self.expected_pid is not None and actual.pid != self.expected_pid:
            raise TransportError("unauthorized peer pid")
        if self.expected_gid is not None and actual.gid != self.expected_gid:
            raise TransportError("unauthorized peer gid")


@dataclasses.dataclass(slots=True)
class SequenceGuard:
    expected: int = 1

    def accept(self, actual: int) -> None:
        if actual != self.expected:
            raise TransportError(
                f"sequence mismatch: expected {self.expected}, received {actual}"
            )
        if self.expected == 0xFFFF_FFFF_FFFF_FFFF:
            raise TransportError("sequence space is exhausted")
        self.expected += 1


@dataclasses.dataclass(frozen=True, slots=True)
class Frame:
    kind: int
    sequence: int
    session_nonce: bytes
    payload: bytes

    def validate(self) -> None:
        if self.kind not in VALID_KINDS:
            raise TransportError(f"unknown frame kind: {self.kind}")
        if not 0 <= self.sequence <= 0xFFFF_FFFF_FFFF_FFFF:
            raise TransportError("sequence is outside u64")
        if len(self.session_nonce) != NONCE_BYTES:
            raise TransportError("session nonce has the wrong length")
        if not any(self.session_nonce):
            raise TransportError("session nonce is all zero")
        if len(self.payload) > MAX_PAYLOAD_BYTES:
            raise TransportError("payload exceeds the configured bound")


def payload_digest(payload: bytes) -> bytes:
    return hashlib.sha256(payload).digest()


def encode_frame(frame: Frame) -> bytes:
    frame.validate()
    header = _HEADER.pack(
        PROTOCOL_MAGIC,
        PROTOCOL_VERSION,
        frame.kind,
        0,
        frame.sequence,
        len(frame.payload),
        frame.session_nonce,
        payload_digest(frame.payload),
    )
    return header + frame.payload


def decode_frame_bytes(encoded: bytes) -> Frame:
    if len(encoded) < HEADER_BYTES:
        raise TransportError("truncated header")
    (
        magic,
        version,
        kind,
        reserved_flags,
        sequence,
        payload_length,
        nonce,
        expected_digest,
    ) = _HEADER.unpack(encoded[:HEADER_BYTES])
    if magic != PROTOCOL_MAGIC:
        raise TransportError("invalid magic")
    if version != PROTOCOL_VERSION:
        raise TransportError("unsupported version")
    if kind not in VALID_KINDS:
        raise TransportError("unknown frame kind")
    if reserved_flags != 0:
        raise TransportError("reserved flags must be zero")
    if payload_length > MAX_PAYLOAD_BYTES:
        raise TransportError("advertised payload exceeds the bound")
    if len(encoded) != HEADER_BYTES + payload_length:
        raise TransportError("encoded frame length does not match header")
    payload = encoded[HEADER_BYTES:]
    if not any(nonce):
        raise TransportError("session nonce is all zero")
    if not hmac.compare_digest(payload_digest(payload), expected_digest):
        raise TransportError("payload digest mismatch")
    frame = Frame(kind=kind, sequence=sequence, session_nonce=nonce, payload=payload)
    frame.validate()
    return frame


def peer_identity(sock: socket.socket) -> PeerIdentity:
    if not hasattr(socket, "SO_PEERCRED"):
        raise TransportError("SO_PEERCRED is unavailable")
    encoded = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, _UCRED.size)
    if len(encoded) != _UCRED.size:
        raise TransportError("SO_PEERCRED returned the wrong size")
    identity = PeerIdentity(*_UCRED.unpack(encoded))
    identity.validate()
    return identity


def _remaining(deadline: float) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise DeadlineExceeded("absolute operation deadline expired")
    return remaining


def _recv_exact(sock: socket.socket, length: int, deadline: float) -> bytes:
    chunks: list[bytes] = []
    remaining_bytes = length
    while remaining_bytes:
        sock.settimeout(_remaining(deadline))
        try:
            chunk = sock.recv(remaining_bytes)
        except TimeoutError as error:
            raise DeadlineExceeded("absolute operation deadline expired") from error
        if not chunk:
            raise TransportError("unexpected EOF")
        chunks.append(chunk)
        remaining_bytes -= len(chunk)
    return b"".join(chunks)


def recv_frame(sock: socket.socket, timeout_seconds: float) -> Frame:
    if timeout_seconds <= 0:
        raise DeadlineExceeded("timeout must be positive")
    deadline = time.monotonic() + timeout_seconds
    header = _recv_exact(sock, HEADER_BYTES, deadline)
    (
        magic,
        version,
        kind,
        reserved_flags,
        sequence,
        payload_length,
        nonce,
        expected_digest,
    ) = _HEADER.unpack(header)
    if magic != PROTOCOL_MAGIC:
        raise TransportError("invalid magic")
    if version != PROTOCOL_VERSION:
        raise TransportError("unsupported version")
    if kind not in VALID_KINDS:
        raise TransportError("unknown frame kind")
    if reserved_flags != 0:
        raise TransportError("reserved flags must be zero")
    if payload_length > MAX_PAYLOAD_BYTES:
        raise TransportError("advertised payload exceeds the bound")
    if not any(nonce):
        raise TransportError("session nonce is all zero")
    payload = _recv_exact(sock, payload_length, deadline)
    if not hmac.compare_digest(payload_digest(payload), expected_digest):
        raise TransportError("payload digest mismatch")
    return Frame(kind, sequence, nonce, payload)


def send_frame(sock: socket.socket, frame: Frame, timeout_seconds: float) -> None:
    if timeout_seconds <= 0:
        raise DeadlineExceeded("timeout must be positive")
    encoded = encode_frame(frame)
    deadline = time.monotonic() + timeout_seconds
    offset = 0
    while offset < len(encoded):
        sock.settimeout(_remaining(deadline))
        try:
            written = sock.send(encoded[offset:])
        except TimeoutError as error:
            raise DeadlineExceeded("absolute operation deadline expired") from error
        if written == 0:
            raise TransportError("unexpected EOF")
        offset += written


def exact_policy(sock: socket.socket) -> PeerPolicy:
    identity = peer_identity(sock)
    return PeerPolicy(identity.uid, identity.pid, identity.gid)


def deterministic_vector() -> dict[str, object]:
    frame = Frame(
        kind=KIND_REQUEST,
        sequence=1,
        session_nonce=bytes([7]) * NONCE_BYTES,
        payload=b"observe",
    )
    encoded = encode_frame(frame)
    return {
        "schema": "trillionnium.desktop.agent-transport.vector.v1",
        "description": "deterministic request frame",
        "kind": frame.kind,
        "sequence": frame.sequence,
        "nonce_hex": frame.session_nonce.hex(),
        "payload_utf8": frame.payload.decode("utf-8"),
        "payload_sha256": payload_digest(frame.payload).hex(),
        "frame_sha256": hashlib.sha256(encoded).hexdigest(),
        "encoded_hex": encoded.hex(),
    }


def socketpair_round_trip() -> dict[str, object]:
    client, server = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    timeout = 1.0
    nonce = bytes([0x5A]) * NONCE_BYTES
    client_policy = exact_policy(client)
    server_policy = exact_policy(server)
    observed: dict[str, object] = {}
    failures: list[BaseException] = []

    def serve() -> None:
        try:
            server_policy.authorize(peer_identity(server))
            send_frame(server, Frame(KIND_CHALLENGE, 0, nonce, CHALLENGE_PAYLOAD), timeout)
            request = recv_frame(server, timeout)
            sequence = SequenceGuard()
            sequence.accept(request.sequence)
            if request.kind != KIND_REQUEST or request.session_nonce != nonce:
                raise TransportError("request binding mismatch")
            observed["request_sha256"] = hashlib.sha256(request.payload).hexdigest()
            send_frame(server, Frame(KIND_RESPONSE, request.sequence, nonce, b"ok"), timeout)
        except BaseException as error:
            failures.append(error)

    thread = threading.Thread(target=serve, name="transport-reference-server")
    thread.start()
    client_policy.authorize(peer_identity(client))
    challenge = recv_frame(client, timeout)
    if challenge != Frame(KIND_CHALLENGE, 0, nonce, CHALLENGE_PAYLOAD):
        raise TransportError("challenge mismatch")
    send_frame(client, Frame(KIND_REQUEST, 1, nonce, b"desktop-reference-check"), timeout)
    response = recv_frame(client, timeout)
    if response != Frame(KIND_RESPONSE, 1, nonce, b"ok"):
        raise TransportError("response mismatch")
    thread.join(timeout=timeout)
    if thread.is_alive():
        raise DeadlineExceeded("reference server did not terminate")
    if failures:
        raise failures[0]
    client_identity = peer_identity_from_policy(client_policy)
    server_identity = peer_identity_from_policy(server_policy)
    client.close()
    server.close()
    return {
        "peer_pid_positive": client_identity.pid > 0 and server_identity.pid > 0,
        "peer_uid_gid_match": (client_identity.uid, client_identity.gid)
        == (server_identity.uid, server_identity.gid),
        "request_sha256": observed["request_sha256"],
        "response_sha256": hashlib.sha256(response.payload).hexdigest(),
    }


def peer_identity_from_policy(policy: PeerPolicy) -> PeerIdentity:
    if policy.expected_pid is None or policy.expected_gid is None:
        raise TransportError("policy is not exact")
    return PeerIdentity(policy.expected_pid, policy.expected_uid, policy.expected_gid)


def validate_contract(contract_path: Path) -> dict[str, object]:
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    expected_layout = [
        ("magic", 0, 8),
        ("version_be", 8, 2),
        ("kind", 10, 1),
        ("reserved_flags_zero", 11, 1),
        ("sequence_be", 12, 8),
        ("payload_length_be", 20, 4),
        ("session_nonce", 24, 32),
        ("payload_sha256", 56, 32),
    ]
    actual_layout = [
        (entry["field"], entry["offset"], entry["bytes"])
        for entry in contract["header_layout"]
    ]
    assertions = {
        "magic": contract["protocol_magic_ascii"] == PROTOCOL_MAGIC.decode("ascii"),
        "version": contract["protocol_version"] == PROTOCOL_VERSION,
        "header_bytes": contract["header_bytes"] == HEADER_BYTES,
        "max_payload_bytes": contract["max_payload_bytes"] == MAX_PAYLOAD_BYTES,
        "layout": actual_layout == expected_layout,
        "kinds": set(contract["frame_kinds"].values()) == VALID_KINDS,
        "listener_disabled": contract["listener"]
        == {"enabled": False, "socket_path": None, "public_network": False},
    }
    failed = sorted(key for key, passed in assertions.items() if not passed)
    if failed:
        raise TransportError(f"contract mismatch: {', '.join(failed)}")
    return assertions


def run_self_check(contract_path: Path) -> dict[str, object]:
    contract_assertions = validate_contract(contract_path)
    vector = deterministic_vector()
    decoded = decode_frame_bytes(bytes.fromhex(str(vector["encoded_hex"])))
    if decoded.payload != b"observe":
        raise TransportError("deterministic vector did not round trip")
    round_trip = socketpair_round_trip()
    return {
        "schema": "trillionnium.desktop.agent-transport.reference-result.v1",
        "status": "PASS",
        "implementation": "python-standard-library-independent-reference",
        "reference_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "contract_sha256": hashlib.sha256(contract_path.read_bytes()).hexdigest(),
        "contract_assertions": contract_assertions,
        "deterministic_vector": vector,
        "socketpair_round_trip": round_trip,
        "product_listener_created": False,
        "browser_payload_interpreted": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--contract",
        type=Path,
        default=Path("contracts/agent-transport.v1.json"),
    )
    parser.add_argument("--write-result", type=Path)
    parser.add_argument("--write-vector", type=Path)
    args = parser.parse_args()
    result = run_self_check(args.contract)
    if args.write_result:
        args.write_result.parent.mkdir(parents=True, exist_ok=True)
        args.write_result.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.write_vector:
        args.write_vector.parent.mkdir(parents=True, exist_ok=True)
        args.write_vector.write_text(
            json.dumps(result["deterministic_vector"], indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
