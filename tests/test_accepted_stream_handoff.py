"""Closed contract/API correspondence; actual SCM behavior is the Rust corpus."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import re
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "contracts/accepted-stream-handoff.v1.json"
SOURCE = ROOT / "crates/hepta-agent-transport/src/accepted_handoff.rs"


def check_contract(value: dict) -> None:
    expected_keys = {"schema", "status", "platform", "claim_ceiling",
                     "existing_application_protocol_changed", "control", "packet",
                     "original_descriptor", "deadline", "public_api", "ownership", "non_claims"}
    if type(value) is not dict or set(value) != expected_keys:
        raise ValueError("closed handoff contract field set")
    if value["schema"] != "trillionnium.desktop.accepted-stream-handoff.v1" or value["status"] != "SOURCE_CANDIDATE_KERNEL_CUSTODY_ONLY":
        raise ValueError("source scope changed")
    if value["existing_application_protocol_changed"] is not False:
        raise ValueError("application protocol changed")
    expected_false = {"live_process_unit_executable_attestation", "root_owned_pathname_custody",
                      "semantic_principal_or_capability", "cross_uid_live_attestation_qualified",
                      "installed_product_service_handoff", "native_servo_runtime", "product_ready", "activation_changed"}
    if set(value["non_claims"]) != expected_false or any(value["non_claims"][key] is not False for key in expected_false):
        raise ValueError("claim ceiling changed")
    fixed = [("control", "challenge_bytes", 40), ("control", "challenge_nonce_bytes", 32),
             ("control", "maximum_accepted_sockets_per_channel", 64),
             ("packet", "bytes", 128), ("packet", "version", 1),
             ("packet", "application_payload_bytes", 0), ("packet", "caller_identity_or_authorization_fields", 0),
             ("original_descriptor", "rights_count", 1), ("deadline", "maximum_budget_seconds", 20)]
    for group, key, expected in fixed:
        if type(value[group][key]) is not int or value[group][key] != expected:
            raise ValueError(f"fixed handoff bound changed: {group}.{key}")
    for group, key in [("control", "creates_listener"), ("control", "challenge_nonce_public"),
                       ("original_descriptor", "automatic_resend"), ("deadline", "pre_capture_accept_wait_covered"),
                       ("deadline", "renewal_api"), ("ownership", "custody_cloneable"),
                       ("ownership", "received_raw_stream_extraction")]:
        if value[group][key] is not False:
            raise ValueError(f"forbidden authority: {group}.{key}")


class AcceptedStreamHandoffContractTests(unittest.TestCase):
    def setUp(self):
        self.contract = json.loads(CONTRACT.read_text())
        self.source = SOURCE.read_text()

    def test_closed_contract_scope_and_actual_source_constants(self):
        check_contract(self.contract)
        for name, number in [("PACKET_BYTES", 128), ("CHALLENGE_BYTES", 40),
                             ("MAX_HANDOFFS_PER_CHANNEL", 64)]:
            self.assertRegex(self.source, rf"const {name}: usize = {number};")
        self.assertIn("MAX_HANDOFF_BUDGET: Duration = Duration::from_secs(20)", self.source)
        self.assertIn('b"HPTAFD01"', self.source)
        self.assertIn('b"HPTAFDC1"', self.source)
        self.assertEqual(self.contract["control"]["challenge_nonce_source"], "private operating-system getrandom only")

    def test_exact_wire_fields_cover_packet_and_bind_real_kernel_clock_scope(self):
        expected = [("magic", 0, 8), ("version_be", 8, 2), ("reserved_zero", 10, 6),
                    ("sequence_be", 16, 8), ("actual_boot_uuid", 24, 16),
                    ("captured_monotonic_nanos_be", 40, 8), ("fixed_deadline_monotonic_nanos_be", 48, 8),
                    ("original_kernel_socket_cookie_be", 56, 8), ("original_descriptor_device_be", 64, 8),
                    ("original_descriptor_inode_be", 72, 8), ("actual_time_namespace_device_be", 80, 8),
                    ("actual_time_namespace_inode_be", 88, 8), ("receiver_private_challenge", 96, 32)]
        self.assertEqual(self.contract["packet"]["fields"], [dict(name=name, offset=offset, bytes=size) for name, offset, size in expected])
        self.assertEqual(sum(size for _, _, size in expected), 128)
        for token in ("libc::CLOCK_MONOTONIC", "libc::SO_COOKIE", "libc::SO_PEERCRED", "libc::SCM_CREDENTIALS"):
            # PeerIdentity facade is the sole original SO_PEERCRED implementation.
            if token == "libc::SO_PEERCRED":
                self.assertIn(token, (ROOT / "crates/hepta-agent-transport/src/facade/wire.rs").read_text())
            else:
                self.assertIn(token, self.source)
        self.assertIn('"/proc/thread-self/ns/time"', self.source)
        self.assertIn("_time_namespace_file: fs::File", self.source)

    def test_public_signature_inventory_and_private_stream_consumer(self):
        expected = {
            "AcceptedStreamCustody::capture": "(UnixStream, &Path, Duration) -> Result<AcceptedStreamCustody, HandoffError>",
            "HandoffReceiver::from_control": "(OwnedFd, PeerPolicy, &Path) -> Result<HandoffReceiver, HandoffError>",
            "HandoffSender::from_control": "(OwnedFd, PeerPolicy, Duration) -> Result<HandoffSender, HandoffError>",
            "HandoffSender::send": "(&mut self, AcceptedStreamCustody) -> Result<(), HandoffError>",
            "HandoffReceiver::receive": "(&mut self, Duration) -> Result<ReceivedAcceptedStream, HandoffError>",
            "ReceivedAcceptedStream::deadline": "(&self) -> Result<Instant, HandoffError>",
            "ReceivedAcceptedStream::consume_before": "(self, impl FnOnce(UnixStream, Instant) -> T) -> Result<T, HandoffError>",
        }
        self.assertEqual(self.contract["public_api"], expected)
        normalized = re.sub(r"\s+", " ", self.source)
        signatures = [
            "pub fn capture( stream: UnixStream, expected_local_path: &Path, budget: Duration, ) -> Result<Self, HandoffError>",
            "pub fn from_control( control: OwnedFd, policy: PeerPolicy, handshake_budget: Duration, ) -> Result<Self, HandoffError>",
            "pub fn from_control( control: OwnedFd, policy: PeerPolicy, expected_local_path: &Path, ) -> Result<Self, HandoffError>",
            "pub fn send(&mut self, custody: AcceptedStreamCustody) -> Result<(), HandoffError>",
            "pub fn receive( &mut self, wait_budget: Duration, ) -> Result<ReceivedAcceptedStream, HandoffError>",
            "pub fn deadline(&self) -> Result<Instant, HandoffError>",
            "pub fn consume_before<T>( self, dispatch: impl FnOnce(UnixStream, Instant) -> T, ) -> Result<T, HandoffError>",
        ]
        for signature in signatures:
            self.assertIn(signature, normalized)
        public_methods = re.findall(r"pub fn (\w+)(?:<[^>]+>)?\s*\(", self.source)
        self.assertEqual(sorted(public_methods), sorted(["capture", "from_control", "from_control", "send", "receive", "deadline", "consume_before"]))
        self.assertNotIn("pub stream:", self.source)
        self.assertNotIn("pub nonce:", self.source)
        self.assertNotIn("pub deadline:", self.source)
        self.assertNotIn("pub fn renew", self.source)

    def test_contract_mutations_cannot_raise_bounds_or_claims(self):
        for group, key in [("control", "creates_listener"), ("control", "challenge_nonce_public"),
                           ("deadline", "pre_capture_accept_wait_covered"), ("deadline", "renewal_api"),
                           ("ownership", "custody_cloneable"), ("ownership", "received_raw_stream_extraction")]:
            value = copy.deepcopy(self.contract); value[group][key] = True
            with self.subTest(group=group, key=key), self.assertRaises(ValueError):
                check_contract(value)
        for key in self.contract["non_claims"]:
            for bad in (True, 0, "false"):
                value = copy.deepcopy(self.contract); value["non_claims"][key] = bad
                with self.subTest(key=key, bad=bad), self.assertRaises(ValueError):
                    check_contract(value)
        for bad in (True, 129, 128.0, "128"):
            value = copy.deepcopy(self.contract); value["packet"]["bytes"] = bad
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                check_contract(value)
        value = copy.deepcopy(self.contract); value["extra_authority"] = True
        with self.assertRaises(ValueError):
            check_contract(value)

    def test_actual_kernel_corpus_is_unskipped_and_registered_in_ci(self):
        manifest = tomllib.loads((ROOT / "crates/hepta-agent-transport/Cargo.toml").read_text())
        target = next(item for item in manifest["test"] if item["name"] == "accepted_handoff_kernel")
        self.assertIs(target["harness"], False)
        source = (ROOT / "crates/hepta-agent-transport" / target["path"]).read_text()
        self.assertIn('fs::read_dir("/proc/self/fd")', source)
        self.assertIn("libc::fork()", source)
        self.assertIn("[0, 2, 17, 100]", source)
        self.assertIn("kernel_message_credentials_refuse_foreign_fork_writer", source)
        self.assertIn("actual_distinct_process_same_uid_original_stream_handoff", source)
        self.assertNotIn("#[ignore]", source)
        self.assertNotIn("SKIP", source)
        workflow = (ROOT / ".github/workflows/s04-transport-custody.yml").read_text()
        self.assertIn("cargo test --workspace --all-targets --all-features --locked", workflow)
        self.assertEqual(workflow.count('"contracts/accepted-stream-handoff.v1.json"'), 2)
        self.assertEqual(workflow.count("python3 -m unittest discover -s tests -p test_accepted_stream_handoff.py -v"), 2)


if __name__ == "__main__":
    unittest.main()
