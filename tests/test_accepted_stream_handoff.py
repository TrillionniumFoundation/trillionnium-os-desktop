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
                     "existing_application_protocol_changed", "control", "packet", "product_consumer",
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

    consumer = value["product_consumer"]
    if type(consumer) is not dict or set(consumer) != {"implementation", "status", "platform", "public_api", "ownership", "admission", "non_claims"}:
        raise ValueError("closed product consumer fields")
    if consumer["implementation"] != "apps/hepta-browserd/src/product_dispatch.rs" or consumer["status"] != "SOURCE_CANDIDATE_LIVE_RECEIVER_BRIDGE_ONLY":
        raise ValueError("product receiver scope changed")
    ownership = consumer["ownership"]
    expected_ownership = {"consuming_callback": True, "fixed_absolute_deadline": True,
                          "raw_stream_extraction": False, "renewal_api": False,
                          "caller_principal_issued": False}
    if type(ownership) is not dict or set(ownership) != set(expected_ownership) or any(ownership[key] is not expected for key, expected in expected_ownership.items()):
        raise ValueError("product receiver ownership changed")
    admission = consumer["admission"]
    expected_admission = {"original_peer", "attestor", "shared_private_helper", "deadline_checks",
                          "maximum_remaining_budget_seconds", "preemptive_procfs_syscall_timeout",
                          "late_attestation_result", "handoff_error", "deadline_observation"}
    if type(admission) is not dict or set(admission) != expected_admission:
        raise ValueError("closed product receiver admission fields")
    if type(admission["maximum_remaining_budget_seconds"]) is not int or admission["maximum_remaining_budget_seconds"] != 20 or admission["preemptive_procfs_syscall_timeout"] is not False:
        raise ValueError("product receiver time or syscall claim changed")
    expected_checks = ["before_peer_read", "after_peer_read_before_live_attestation", "after_live_attestation_before_clone", "after_clone", "after_pidfd_liveness", "after_local_setup_before_return"]
    if admission["deadline_checks"] != expected_checks:
        raise ValueError("product receiver absolute deadline checks changed")
    expected_nonclaims = {"approved_principal", "cross_uid_live_attestation_qualified", "installed_product_service_handoff", "native_servo_runtime", "product_ready", "activation_changed"}
    if type(consumer["non_claims"]) is not dict or set(consumer["non_claims"]) != expected_nonclaims or any(item is not False for item in consumer["non_claims"].values()):
        raise ValueError("product receiver claim ceiling changed")
    expected_api = {
        "AcceptedProductConnection::attest": "(UnixStream, ProcfsPeerAttestor, &PeerRuntimePolicy, Duration) -> Result<AcceptedProductConnection, ProductDispatchError>",
        "AcceptedProductConnection::from_received": "(ReceivedAcceptedStream, ProcfsPeerAttestor, &PeerRuntimePolicy) -> Result<AcceptedProductConnection, ProductDispatchError>",
        "AcceptedProductConnection::from_control_received": "(ControlReceivedAcceptedStream, &PeerRuntimePolicy, &str) -> Result<AcceptedProductConnection, ProductDispatchError>",
        "AcceptedProductConnection::deadline": "(&self) -> Result<Instant, ProductDispatchError>",
        "AcceptedProductConnection::cancellation": "(&self) -> ProductConnectionCancellation",
    }
    if consumer["public_api"] != expected_api:
        raise ValueError("closed product receiver API inventory changed")


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
            "AcceptedStreamCustody::capture_before": "(UnixStream, &Path, Instant) -> Result<AcceptedStreamCustody, HandoffError>",
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
            "pub fn capture_before( stream: UnixStream, expected_local_path: &Path, deadline: Instant, ) -> Result<Self, HandoffError>",
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
        self.assertEqual(sorted(public_methods), sorted(["capture_before", "capture", "from_control", "from_control", "send", "receive", "deadline", "consume_before"]))
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

    def test_product_consumer_closed_signatures_and_single_original_deadline_path(self):
        source = (ROOT / "apps/hepta-browserd/src/product_dispatch.rs").read_text()
        normalized = re.sub(r"\s+", " ", source)
        for signature in (
            "pub fn attest( stream: UnixStream, attestor: ProcfsPeerAttestor, policy: &PeerRuntimePolicy, budget: Duration, ) -> Result<Self, ProductDispatchError>",
            "pub fn from_received( received: ReceivedAcceptedStream, attestor: ProcfsPeerAttestor, policy: &PeerRuntimePolicy, ) -> Result<Self, ProductDispatchError>",
            "pub fn deadline(&self) -> Result<Instant, ProductDispatchError>",
            "pub fn cancellation(&self) -> ProductConnectionCancellation",
        ):
            self.assertIn(signature, normalized)
        impl = source.split("impl AcceptedProductConnection {", 1)[1].split("fn product_time_remaining", 1)[0]
        self.assertEqual(re.findall(r"pub fn (\w+)\s*\(", impl), ["attest", "from_received", "from_control_received", "deadline", "cancellation"])
        received = impl.split("pub fn from_received", 1)[1].split("pub fn from_control_received", 1)[0]
        self.assertIn(".consume_before(|stream, deadline|", received)
        self.assertIn("Self::attest_before(stream, attestor, policy, deadline)", received)
        self.assertNotIn("Instant::now", received)
        self.assertNotIn("MAX_PRODUCT_CONNECTION_BUDGET", received)
        self.assertNotIn("Self::attest(", received)
        self.assertIn('#[cfg(target_os = "linux")]\n    pub fn from_received', source)
        helper = impl.split("fn attest_before", 1)[1].split("pub fn deadline", 1)[0]
        self.assertEqual(helper.count("product_time_remaining(deadline)?"), 6)
        self.assertNotIn("checked_add", helper)
        positions = [helper.index(token) for token in [
            "let remaining = product_time_remaining", "PeerIdentity::from_stream", "let peer = peer.map_err", "attestor.attest(peer, policy)", "let attested = attested.map_err", "stream.try_clone()", "let interrupt = interrupt.map_err", ".ensure_alive()", "let connection = Self", "Ok(connection)"]]
        self.assertEqual(positions, sorted(positions))
        getter = impl.split("pub fn deadline", 1)[1].split("pub fn cancellation", 1)[0]
        self.assertLess(getter.index("owner_pid != std::process::id()"), getter.index("cancelled.load"))
        self.assertLess(getter.index("cancelled.load"), getter.index("product_time_remaining(self.deadline)?"))
        self.assertIn("Ok(self.deadline)", getter)
        self.assertNotIn(".lock()", getter)

    def test_product_consumer_nested_claim_api_and_bound_drift_are_refused(self):
        mutations = [("ownership", "consuming_callback", False), ("ownership", "fixed_absolute_deadline", False),
                     ("ownership", "raw_stream_extraction", True), ("ownership", "renewal_api", True),
                     ("ownership", "caller_principal_issued", True), ("admission", "preemptive_procfs_syscall_timeout", True),
                     ("admission", "maximum_remaining_budget_seconds", True), ("admission", "maximum_remaining_budget_seconds", 21)]
        mutations += [("non_claims", key, bad) for key in self.contract["product_consumer"]["non_claims"] for bad in (True, 0, "false")]
        for group, key, bad in mutations:
            value = copy.deepcopy(self.contract); value["product_consumer"][group][key] = bad
            with self.subTest(group=group, key=key, bad=bad), self.assertRaises(ValueError):
                check_contract(value)
        for group in ("ownership", "admission", "non_claims", "public_api"):
            value = copy.deepcopy(self.contract); value["product_consumer"][group]["extra"] = False
            with self.subTest(group=group), self.assertRaises(ValueError):
                check_contract(value)
        for group in ("status", "implementation"):
            value = copy.deepcopy(self.contract); value["product_consumer"][group] = "PRODUCT_READY"
            with self.subTest(group=group), self.assertRaises(ValueError):
                check_contract(value)
        value = copy.deepcopy(self.contract); value["product_consumer"]["admission"]["deadline_checks"].pop()
        with self.assertRaises(ValueError):
            check_contract(value)

    def test_product_receiver_actual_linux_corpus_and_both_source_ci_lanes(self):
        manifest = tomllib.loads((ROOT / "apps/hepta-browserd/Cargo.toml").read_text())
        target = next(item for item in manifest["test"] if item["name"] == "product_handoff_kernel")
        self.assertIs(target["harness"], False)
        source = (ROOT / "apps/hepta-browserd" / target["path"]).read_text()
        for token in ("libc::SOCK_SEQPACKET", "AcceptedStreamCustody::capture", "sender.send(custody)", "receiver.receive(WAIT)", "ProcfsPeerAttestor::default()", "live.child.kill()", "libc::fork()", "libc::_exit(0)", "Duration::from_millis(500)", "connection.deadline().unwrap(),", '"original-peer"'):
            self.assertIn(token, source)
        self.assertNotIn("#[ignore]", source)
        self.assertNotIn("SKIP", source)
        workflow = (ROOT / ".github/workflows/s08-product-servo-runtime.yml").read_text()
        self.assertEqual(workflow.count("cargo test --locked -p hepta-browserd --all-targets"), 2)
        source_ci = (ROOT / ".github/workflows/s04-transport-custody.yml").read_text()
        self.assertEqual(source_ci.count('"apps/hepta-browserd/**"'), 2)
        self.assertIn('branches: [main, "codex/**"]', source_ci)
        self.assertEqual(source_ci.count("cargo test --workspace --all-targets --all-features --locked"), 2)
        self.assertEqual(source_ci.count("python3 -m unittest discover -s tests -p test_accepted_stream_handoff.py -v"), 2)

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
