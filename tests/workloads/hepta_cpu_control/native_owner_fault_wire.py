"""Bind actual fault diagnostics to the original HOS2 Install request bytes.

This independently checks the current OS byte codec. It sends no request,
allocates no D, invokes no writer and produces no native execution evidence.
Install frames omit boot/CapSpace identities: the caller must separately bind
the actual FileTransport Process/image and original QueryAbi to the prepared D.
"""
import hashlib
import struct

from native_owner_evidence import digest, integer, request, require


INSTALL_FRAME_BYTES = 96
INSTALL_SUCCESS_RESPONSE_BYTES = 88


def expected_install_wire(request_json):
    """Derive comparison bytes only from the original canonical outbox payload."""
    original = request(request_json)
    sequence = int(original["delivery"]["sequence"], 16)
    raw = bytearray(INSTALL_FRAME_BYTES)
    raw[:4] = b"HOS2"
    struct.pack_into("<HHHHII", raw, 4, 2, 0, 3, 0, 64, 32)
    # Reserved 20..24, request-id high half 32..40, header 56..64 and
    # Install payload 88..96 remain zero, exactly as the original codec.
    struct.pack_into("<Q", raw, 24, sequence)
    struct.pack_into("<QQ", raw, 40, original["manage_slot"], original["manage_generation"])
    struct.pack_into("<QQQ", raw, 64, original["expected_revision"],
                     original["period_ns"], original["cap_ns"])
    return bytes(raw)


def match_install_wire(request_json, actual_wire_sha256, actual_request_bytes, response_capacity):
    """Check original diagnostics; this does not establish syscall or copyout success."""
    expected = expected_install_wire(request_json)
    integer(actual_request_bytes, "actual Install request frame bytes",
            INSTALL_FRAME_BYTES, INSTALL_FRAME_BYTES)
    integer(response_capacity, "actual preserved Install response capacity",
            INSTALL_SUCCESS_RESPONSE_BYTES, (1 << 32) - 1)
    expected_sha = hashlib.sha256(expected).hexdigest()
    require(digest(actual_wire_sha256, "actual FileTransport Install wire") == expected_sha,
            "faulted FileTransport request differs from the entire original K/D wire binding")
    return {"wire_bytes": len(expected), "wire_sha256": expected_sha}
