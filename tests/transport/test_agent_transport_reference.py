from __future__ import annotations

import hashlib
import importlib.util
import json
import socket
import sys
import time
import unittest
from pathlib import Path

from tests.test_agent_port_custody_workflow import trigger_paths

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "tools" / "agent_transport_reference.py"
SPEC = importlib.util.spec_from_file_location("agent_transport_reference", MODULE_PATH)
assert SPEC and SPEC.loader
ref = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = ref
SPEC.loader.exec_module(ref)


class TransportReferenceTests(unittest.TestCase):
    def test_registry_and_workflow_triggers_cover_the_same_inputs(self) -> None:
        registry = json.loads(
            (ROOT / "manifests/gates.v1.json").read_text(encoding="utf-8")
        )
        gate = next(item for item in registry["gates"] if item["id"] == "D0C-02")
        expected = set(gate["invalidation_paths"])
        workflow = (
            ROOT / ".github/workflows/agent-transport-reference.yml"
        ).read_text(encoding="utf-8")
        for event in ("pull_request", "push"):
            actual = trigger_paths(workflow, event)
            self.assertEqual(
                actual,
                expected,
                f"D0C-02 {event} trigger drift: "
                f"missing={sorted(expected - actual)}, "
                f"unregistered={sorted(actual - expected)}",
            )

    def test_permanent_workflow_revalidates_rust_transport_inputs(self) -> None:
        workflow = (
            ROOT / ".github/workflows/agent-transport-reference.yml"
        ).read_text(encoding="utf-8")
        for required in (
            '"crates/hepta-agent-transport/**"',
            '"Cargo.toml"',
            '"Cargo.lock"',
            '"rust-toolchain.toml"',
            '"manifests/cargo-external-allowlist.json"',
            '"tools/validate_repository.py"',
            "cargo fmt --all --check",
            "cargo check --locked -p hepta-agent-transport --all-targets",
            "cargo clippy --locked -p hepta-agent-transport --all-targets",
            "cargo test --locked -p hepta-agent-transport --all-targets",
        ):
            self.assertIn(required, workflow)

        registry = json.loads(
            (ROOT / "manifests/gates.v1.json").read_text(encoding="utf-8")
        )
        gate = next(item for item in registry["gates"] if item["id"] == "D0C-02")
        self.assertIn("tests/transport/**", gate["invalidation_paths"])
        marker = '"tests/transport/**"'
        self.assertGreaterEqual(
            workflow.count(marker),
            2,
            "transport gate must trigger for every transport test on PR and push",
        )

    def test_contract_matches_reference(self) -> None:
        checks = ref.validate_contract(ROOT / "contracts" / "agent-transport.v1.json")
        self.assertTrue(all(checks.values()))

    def test_historical_host_claim_is_explicitly_stale_but_reference_stays_pass(self) -> None:
        contract = json.loads(
            (ROOT / "contracts/agent-transport.v1.json").read_text(encoding="utf-8")
        )
        host = json.loads(
            (ROOT / "docs/evidence/generated/d0c02-rust193-host-result.json").read_text(
                encoding="utf-8"
            )
        )
        validation = contract["validation"]
        claim = host["claim"]
        self.assertEqual(contract["status"], "HOST_VALIDATED_NO_LISTENER")
        self.assertEqual(
            contract["evidence_lifecycle"],
            "STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN",
        )
        self.assertEqual(contract["evidence_freshness"], "STALE_EVIDENCE")
        self.assertFalse(contract["merge_ready"])
        self.assertEqual(validation["evidence_freshness"], "STALE_EVIDENCE")
        self.assertFalse(validation["merge_ready"])
        self.assertEqual(host["evidence_lifecycle"], "STALE_EVIDENCE_REQUIRES_EXACT_HEAD_RERUN")
        self.assertEqual(claim["evidence_freshness"], "STALE_EVIDENCE")
        self.assertFalse(claim["merge_ready"])
        self.assertIn(host["candidate_head"], validation["stale_reason"])
        reference = json.loads(
            (ROOT / "docs/evidence/generated/d0c02-agent-transport-reference-result.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(reference["status"], "PASS")

    def test_deterministic_vector_round_trips(self) -> None:
        vector = ref.deterministic_vector()
        encoded = bytes.fromhex(vector["encoded_hex"])
        decoded = ref.decode_frame_bytes(encoded)
        self.assertEqual(decoded.payload, b"observe")
        self.assertEqual(hashlib.sha256(encoded).hexdigest(), vector["frame_sha256"])

    def test_socketpair_round_trip_and_peer_credentials(self) -> None:
        result = ref.socketpair_round_trip()
        self.assertTrue(result["peer_pid_positive"])
        self.assertTrue(result["peer_uid_gid_match"])
        self.assertEqual(result["response_sha256"], hashlib.sha256(b"ok").hexdigest())

    def test_oversized_length_fails_before_payload_read(self) -> None:
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

    def test_digest_tamper_fails_closed(self) -> None:
        frame = ref.Frame(ref.KIND_REQUEST, 1, bytes([3]) * ref.NONCE_BYTES, b"original")
        encoded = bytearray(ref.encode_frame(frame))
        encoded[-1] ^= 1
        with self.assertRaisesRegex(ref.TransportError, "digest mismatch"):
            ref.decode_frame_bytes(bytes(encoded))

    def test_reserved_flags_fail_closed(self) -> None:
        frame = ref.Frame(ref.KIND_REQUEST, 1, bytes([4]) * ref.NONCE_BYTES, b"x")
        encoded = bytearray(ref.encode_frame(frame))
        encoded[11] = 1
        with self.assertRaisesRegex(ref.TransportError, "reserved flags"):
            ref.decode_frame_bytes(bytes(encoded))

    def test_zero_nonce_fails_closed(self) -> None:
        with self.assertRaisesRegex(ref.TransportError, "all zero"):
            ref.encode_frame(ref.Frame(ref.KIND_REQUEST, 1, bytes(ref.NONCE_BYTES), b"x"))

    def test_unknown_kind_fails_closed(self) -> None:
        frame = bytearray(
            ref.encode_frame(
                ref.Frame(ref.KIND_REQUEST, 1, bytes([5]) * ref.NONCE_BYTES, b"x")
            )
        )
        frame[10] = 99
        with self.assertRaisesRegex(ref.TransportError, "unknown frame kind"):
            ref.decode_frame_bytes(bytes(frame))

    def test_replayed_sequence_fails_closed(self) -> None:
        guard = ref.SequenceGuard()
        guard.accept(1)
        with self.assertRaisesRegex(ref.TransportError, "sequence mismatch"):
            guard.accept(1)

    def test_skipped_sequence_fails_closed(self) -> None:
        guard = ref.SequenceGuard()
        with self.assertRaisesRegex(ref.TransportError, "sequence mismatch"):
            guard.accept(2)

    def test_invalid_magic_fails_closed(self) -> None:
        encoded = bytearray(
            ref.encode_frame(
                ref.Frame(ref.KIND_REQUEST, 1, bytes([6]) * ref.NONCE_BYTES, b"x")
            )
        )
        encoded[0] ^= 1
        with self.assertRaisesRegex(ref.TransportError, "invalid magic"):
            ref.decode_frame_bytes(bytes(encoded))

    def test_unsupported_version_fails_closed(self) -> None:
        encoded = bytearray(
            ref.encode_frame(
                ref.Frame(ref.KIND_REQUEST, 1, bytes([7]) * ref.NONCE_BYTES, b"x")
            )
        )
        encoded[8:10] = (2).to_bytes(2, "big")
        with self.assertRaisesRegex(ref.TransportError, "unsupported version"):
            ref.decode_frame_bytes(bytes(encoded))

    def test_truncated_payload_fails_closed(self) -> None:
        encoded = ref.encode_frame(
            ref.Frame(ref.KIND_REQUEST, 1, bytes([8]) * ref.NONCE_BYTES, b"payload")
        )
        with self.assertRaisesRegex(ref.TransportError, "length does not match"):
            ref.decode_frame_bytes(encoded[:-1])

    def test_absolute_deadline_bounds_header_read(self) -> None:
        writer, reader = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        started = time.monotonic()
        with self.assertRaises(ref.DeadlineExceeded):
            ref.recv_frame(reader, 0.025)
        self.assertLess(time.monotonic() - started, 1.0)
        writer.close()
        reader.close()

    def test_peer_policy_rejects_wrong_uid(self) -> None:
        left, right = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        identity = ref.peer_identity(left)
        policy = ref.PeerPolicy(identity.uid + 1, identity.pid, identity.gid)
        with self.assertRaisesRegex(ref.TransportError, "uid"):
            policy.authorize(ref.peer_identity(right))
        left.close()
        right.close()


if __name__ == "__main__":
    unittest.main()
