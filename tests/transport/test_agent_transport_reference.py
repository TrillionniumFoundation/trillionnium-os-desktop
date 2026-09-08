from __future__ import annotations

import hashlib
import importlib.util
import json
import socket
import sys
import time
import unittest
from fnmatch import fnmatchcase
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "agent_transport_reference.py"
SPEC = importlib.util.spec_from_file_location("agent_transport_reference", MODULE_PATH)
assert SPEC and SPEC.loader
ref = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ref
SPEC.loader.exec_module(ref)


def trigger_paths(text: str, event: str) -> set[str]:
    result: set[str] = set()
    in_event = False
    in_paths = False
    for line in text.splitlines():
        stripped = line.strip()
        indent = len(line) - len(line.lstrip(" "))
        if not in_event:
            in_event = line == f"  {event}:"
            continue
        if indent == 2 and stripped and not stripped.startswith("#"):
            break
        if not in_paths:
            in_paths = indent == 4 and stripped == "paths:"
            continue
        if indent <= 4 and stripped and not stripped.startswith("-"):
            break
        if indent >= 6 and stripped.startswith("- "):
            value = stripped[2:].split(" #", 1)[0].strip().strip("'\"")
            if value:
                result.add(value)
    return result


class TransportReferenceTests(unittest.TestCase):
    def test_registered_inputs_trigger_both_events(self) -> None:
        registry = json.loads((ROOT / "manifests/gates.v1.json").read_text())
        gate = next(item for item in registry["gates"] if item["id"] == "D0C-02")
        workflow = (ROOT / ".github/workflows/agent-transport-reference.yml").read_text()
        for event in ("pull_request", "push"):
            actual = trigger_paths(workflow, event)
            self.assertTrue(actual)
            for pattern in gate["invalidation_paths"]:
                self.assertTrue(
                    any(fnmatchcase(candidate, pattern) for candidate in actual),
                    f"registered transport input {pattern!r} does not trigger {event}",
                )
            self.assertIn("crates/hepta-agent-transport/**", actual)
            self.assertIn("tests/transport/**", actual)

    def test_contract_and_stale_host_ceiling(self) -> None:
        self.assertTrue(all(ref.validate_contract(ROOT / "contracts/agent-transport.v1.json").values()))
        contract = json.loads((ROOT / "contracts/agent-transport.v1.json").read_text())
        host = json.loads((ROOT / "docs/evidence/generated/d0c02-rust193-host-result.json").read_text())
        self.assertEqual(contract["status"], "HOST_VALIDATED_NO_LISTENER")
        self.assertEqual(contract["evidence_freshness"], "STALE_EVIDENCE")
        self.assertFalse(contract["merge_ready"])
        self.assertEqual(host["claim"]["evidence_freshness"], "STALE_EVIDENCE")
        self.assertFalse(host["claim"]["merge_ready"])
        self.assertIn(host["candidate_head"], contract["validation"]["stale_reason"])

    def test_deterministic_vector_and_socketpair(self) -> None:
        vector = ref.deterministic_vector()
        encoded = bytes.fromhex(vector["encoded_hex"])
        decoded = ref.decode_frame_bytes(encoded)
        self.assertEqual(decoded.payload, b"observe")
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), vector["frame_sha256"])
        result = ref.socketpair_round_trip()
        self.assertTrue(result["peer_pid_positive"])
        self.assertTrue(result["peer_uid_gid_match"])

    def test_frame_ambiguity_and_replay_fail_closed(self) -> None:
        frame = ref.Frame(ref.KIND_REQUEST, 1, bytes([3]) * ref.NONCE_BYTES, b"original")
        encoded = bytearray(ref.encode_frame(frame))
        encoded[-1] ^= 1
        with self.assertRaisesRegex(ref.TransportError, "digest mismatch"):
            ref.decode_frame_bytes(bytes(encoded))
        with self.assertRaisesRegex(ref.TransportError, "all zero"):
            ref.encode_frame(ref.Frame(ref.KIND_REQUEST, 1, bytes(ref.NONCE_BYTES), b"x"))
        guard = ref.SequenceGuard()
        guard.accept(1)
        with self.assertRaisesRegex(ref.TransportError, "sequence mismatch"):
            guard.accept(1)

    def test_length_and_deadline_fail_closed(self) -> None:
        nonce = bytes([2]) * ref.NONCE_BYTES
        header = ref._HEADER.pack(
            ref.PROTOCOL_MAGIC,
            ref.PROTOCOL_VERSION,
            ref.KIND_REQUEST,
            0,
            1,
            ref.MAX_PAYLOAD_BYTES + 1,
            nonce,
            bytes(ref.DIGEST_BYTES),
        )
        with self.assertRaisesRegex(ref.TransportError, "exceeds the bound"):
            ref.decode_frame_bytes(header)
        writer, reader = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        started = time.monotonic()
        try:
            with self.assertRaises(ref.DeadlineExceeded):
                ref.recv_frame(reader, 0.025)
            self.assertLess(time.monotonic() - started, 1.0)
        finally:
            writer.close()
            reader.close()


if __name__ == "__main__":
    unittest.main()
