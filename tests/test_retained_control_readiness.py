"""Adversarial finite source correspondence; actual kernel targets are separate."""
from __future__ import annotations

import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools import verify_retained_control_readiness as verifier

ROOT = Path(__file__).resolve().parents[1]


class RetainedControlReadinessTests(unittest.TestCase):
    def texts(self):
        paths = set(verifier.EXPECTED["actual_source_sha256"]) | set(verifier.EXPECTED["preserved_sha256"])
        return {path: (ROOT / path).read_text(encoding="utf-8") for path in paths}

    def refuse(self, path, before, after):
        values = self.texts()
        self.assertIn(before, values[path])
        values[path] = values[path].replace(before, after, 1)
        with self.assertRaises(ValueError):
            verifier.check(copy.deepcopy(verifier.EXPECTED), values)

    def test_actual_source_contract_and_cli(self):
        verifier.validate(ROOT)
        result = subprocess.run([sys.executable, str(ROOT / "tools/verify_retained_control_readiness.py")],
                                cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["runtime_qualification"], "PENDING")
        self.assertFalse(json.loads(result.stdout)["idle_permission"])
        self.assertFalse(json.loads(result.stdout)["installed_activation"])

    def test_typed_contract_flags_limits_and_unknown_fields_refuse(self):
        for group, name, changes in [
            ("authority", "idle_full_executable_hash", [0, True]),
            ("authority", "cross_call_executable_cache", [0, True]),
            ("authority", "idle_result_grants_action_or_report_permission", [0, True]),
            ("lifetime", "accepted_seconds_maximum", [True, 20.0, 21]),
            ("qualification", "production_ready", [0, True]),
            ("qualification", "arbitrary_concurrent_same_process_fd_tampering_safe", [0, True]),
        ]:
            for change in changes:
                contract = copy.deepcopy(verifier.EXPECTED)
                contract[group][name] = change
                with self.subTest(group=group, name=name, change=change), self.assertRaises(ValueError):
                    verifier.check(contract, self.texts())
        contract = copy.deepcopy(verifier.EXPECTED)
        contract["authority"]["caller_prechecked"] = True
        with self.assertRaises(ValueError): verifier.check(contract, self.texts())

    def test_duplicate_fields_and_source_hash_rebinding_refuse(self):
        with tempfile.TemporaryDirectory(prefix="control-ready-contract-") as directory:
            path = Path(directory) / "contract.json"
            value = json.dumps(verifier.EXPECTED)
            path.write_text(value.replace('"default_activation": false',
                                           '"default_activation": false, "default_activation": false', 1))
            with self.assertRaises(ValueError): verifier.composition.load(path)
        contract = copy.deepcopy(verifier.EXPECTED)
        contract["actual_source_sha256"][verifier.RETAINED] = "0" * 64
        with self.assertRaises(ValueError): verifier.check(contract, self.texts())

    def test_original_control_identity_captured_at_creation_not_first_idle(self):
        for after in ["", "// let original_identity = OriginalControlIdentity::capture(fd)?;",
                      'let _decoy = "OriginalControlIdentity::capture(fd)?";']:
            with self.subTest(after=after):
                self.refuse(verifier.TRANSPORT, "let original_identity = OriginalControlIdentity::capture(fd)?;", after)
        self.refuse(verifier.TRANSPORT_READINESS, "self.transaction.readiness_enabled = true;",
                    "self.transaction.channel.original_identity = OriginalControlIdentity::capture(self.transaction.verify()?)?;")

    def test_control_identity_cannot_use_agent_cookie_or_caller_snapshot(self):
        self.refuse(verifier.TRANSPORT, "struct OriginalControlIdentity(SocketIdentity);",
                    "pub struct OriginalControlIdentity(SocketIdentity);")
        self.refuse(verifier.RETAINED, "original_identity: self.channel.original_identity,",
                    "original_identity: OriginalControlIdentity(self.identity),")
        self.refuse(verifier.RETAINED, "channel.original_identity.verify(fd)?;", "let _ = self.identity;")

    def test_creation_shape_peer_and_cloexec_stay_before_capture(self):
        self.refuse(verifier.TRANSPORT, "socket_shape(&stream, libc::SOCK_SEQPACKET)?;", "")
        self.refuse(verifier.TRANSPORT, "flags | libc::FD_CLOEXEC", "flags")
        self.refuse(verifier.TRANSPORT, "libc::SO_PASSCRED,", "libc::SO_KEEPALIVE,")

    def test_private_channel_pre_post_identity_and_clocks_cannot_be_dropped(self):
        self.refuse(verifier.RETAINED, "channel.owner()?;\n        let fd = channel.verify()?;", "let fd = channel.verify()?;")
        values = self.texts()
        before = "channel.original_identity.verify(fd)?;"
        self.assertEqual(values[verifier.RETAINED].count(before), 2)
        for count in [1, 2]:
            changed = dict(values)
            changed[verifier.RETAINED] = changed[verifier.RETAINED].replace(before, "", count)
            with self.subTest(count=count), self.assertRaises(ValueError): verifier.check(verifier.EXPECTED, changed)
        self.refuse(verifier.RETAINED, "if Instant::now() >= self.deadline", "if false")

    def test_readiness_does_not_consume_parse_or_send_and_refusal_retires(self):
        self.refuse(verifier.TRANSPORT_READINESS, "readable_now(self.transaction.verify()?)?", "self.transaction.receive(&mut [0; FRAME_BYTES])?")
        self.refuse(verifier.TRANSPORT_READINESS, "self.transaction.readiness_enabled = true;", "self.transaction.readiness_enabled = false;")
        self.refuse(verifier.TRANSPORT_READINESS, "if result.is_err() {\n            self.transaction.channel.retire();",
                    "if result.is_err() {")

    def test_reporting_scope_requires_root_source_and_original_control_role(self):
        self.refuse(verifier.OWNER, "if self.approved.is_empty()", "if self.approved.len() != 2")
        self.refuse(verifier.OWNER, "policy.verify_control_reporting_source(&self.attested)?;", "")
        self.refuse(verifier.POLICY, "if self.role != 0", "if false")
        self.refuse(verifier.POLICY, "snapshot.systemd_unit.as_deref() != Some(entry.unit.as_str())", "false")
        self.refuse(verifier.POLICY, "snapshot.executable_sha256 != entry.pin", "false")

    def test_idle_action_revocation_does_not_become_reporting_revocation(self):
        self.refuse(verifier.PEER_READINESS, ".idle_reporting_scope()?;", ".idle_reporting_scope()?; self.action.ensure_alive()?;")
        self.refuse(verifier.OWNER, "fn idle_reporting_scope(&self) -> Result<Duration, ControlOwnerError> {",
                    "fn idle_reporting_scope(&self) -> Result<Duration, ControlOwnerError> { self.current()?;")

    def test_ready_hup_error_must_use_unchanged_full_raw_poll(self):
        self.refuse(verifier.PEER_READINESS, "if ready { self.poll_cancel() } else { Ok(false) }", "Ok(false)")
        self.refuse(verifier.RETAINED, "events: libc::POLLIN,", "events: 0,")
        self.refuse(verifier.PEER_READINESS, "if checked.is_err() {\n            self.retire()?;", "if checked.is_err() {")

    def test_new_api_cannot_accept_fd_deadline_boolean_or_execution_authority(self):
        for parameter in ["fd: i32", "deadline: Instant", "caller_approved: bool"]:
            with self.subTest(parameter=parameter):
                self.refuse(verifier.TRANSPORT_READINESS, "pub fn cancel_readable_now(&mut self)",
                            "pub fn cancel_readable_now(&mut self, " + parameter + ")")
        self.refuse(verifier.PEER_READINESS, "pub fn poll_cancel_when_readable(&mut self)",
                    "pub fn poll_cancel_when_readable(&mut self, permit: RuntimePermit)")
        self.refuse(verifier.PEER_READINESS, "if ready { self.poll_cancel() }", "if ready { mint_report_permission(); self.poll_cancel() }")

    def test_legacy_factory_and_actual_terminal_full_body_remain(self):
        self.refuse(verifier.MONITOR, "cancel_profile: CancelPollProfile::FullV1,",
                    "cancel_profile: CancelPollProfile::ApprovedReadinessV1,")
        self.refuse(verifier.MONITOR, "retained.send_remote_report(report).map_err(control_error)?;", "")
        self.refuse(verifier.RETAINED, "self.transaction.verify_channel(&channel)?;", "")

    def test_explicit_approved_factory_and_no_cached_exec_or_extended_instant(self):
        self.refuse(verifier.PRODUCT, "cancel_profile: CancelPollProfile::ApprovedReadinessV1,",
                    "cancel_profile: CancelPollProfile::FullV1,")
        self.refuse(verifier.OWNER, "fn idle_reporting_scope(&self) -> Result<Duration, ControlOwnerError> {",
                    "fn idle_reporting_scope(&self) -> Result<Duration, ControlOwnerError> { use_cached_executable();")
        self.refuse(verifier.PEER_READINESS, "remaining(self.owner_pid, self.deadline)?;",
                    "remaining(self.owner_pid, Instant::now() + Duration::from_secs(20))?;")

    def test_detached_report_field_and_old_raw_poll_body_are_exact(self):
        self.refuse(verifier.RETAINED, "original_identity: self.channel.original_identity,", "")
        self.refuse(verifier.RETAINED, "pub fn poll_cancel(&mut self) -> Result<bool, HandoffError> {",
                    "pub fn poll_cancel(&mut self) -> Result<bool, HandoffError> { return Ok(false);")
        self.refuse(verifier.REQUEST, "pub fn send_remote_report(", "pub fn send_caller_report(")

    def test_complete_legacy36_plus_two_versioned_modules_and_compiled_route(self):
        self.assertEqual(len(verifier.EXPECTED["legacy_public_api"]), 36)
        for path, methods in [(verifier.TRANSPORT_READINESS, {"PendingHandoffReceiver::cancel_readable_now", "PendingHandoffSender::report_readable_now"}),
                              (verifier.PEER_READINESS, {"AttestedRetainedReceiver::poll_cancel_when_readable", "AttestedPendingHandoff::poll_retirement_when_readable"})]:
            actual = verifier.composition.rust_inventory(self.texts()[path])["public_api"]
            self.assertEqual(set(actual), methods)
        self.assertEqual(len(verifier.EXPECTED["public_api"]), 4)
        for path in [verifier.RETAINED, verifier.REQUEST]:
            self.refuse(path, "mod readiness;", "// mod readiness;")
        self.refuse(verifier.TRANSPORT_READINESS, "impl PendingHandoffReceiver", "impl CallerReceiver")
        self.refuse(verifier.PEER_READINESS, "impl AttestedRetainedReceiver", "impl CallerReceiver")

    def test_old_case_bodies_cargo_prefix_pin_workflow_and_locks_preserved(self):
        for path in verifier.EXPECTED["preserved_sha256"]:
            with self.subTest(path=path):
                values = self.texts()
                values[path] += "\n"
                with self.assertRaises(ValueError): verifier.check(verifier.EXPECTED, values)
        self.refuse(verifier.CARGO, 'harness = false', 'harness = true')
        values = self.texts()
        values[verifier.CARGO] += '\n[[test]]\nname = "other"\npath = "other.rs"\n'
        with self.assertRaises(ValueError): verifier.check(verifier.EXPECTED, values)

    def test_finite_transfer_cannot_drop_new_gate_or_accept_literal_decoy(self):
        values = self.texts()
        for path in verifier.TRANSFER:
            self.assertEqual(verifier.hashlib.sha256(verifier.parent_source(path, values[path]).encode()).hexdigest(),
                             verifier.EXPECTED["parent_source_sha256"][path])
        path = verifier.REQUEST
        altered = values[path].replace("mod readiness;", '// literal decoy: "mod readiness;"', 1)
        with self.assertRaises(ValueError): verifier.parent_source(path, altered)
        # Legacy scope's comment tolerance is retained; actual new profile's
        # whole source requirement independently refuses additional bytes.
        commented = values[verifier.PRODUCT] + '\n// caller_prechecked\n'
        self.assertTrue(verifier.parent_source(verifier.PRODUCT, commented).endswith('// caller_prechecked\n'))
        changed = dict(values); changed[verifier.PRODUCT] = commented
        with self.assertRaises(ValueError): verifier.check(verifier.EXPECTED, changed)


class SenderReadinessSourceTests(unittest.TestCase):
    """Current physical sender guards; Rust/socket execution is a separate gate."""
    texts = RetainedControlReadinessTests.texts

    def test_sender_current_positive_and_closed_forty_api(self):
        verifier.check(copy.deepcopy(verifier.EXPECTED), self.texts())
        self.assertEqual(len(verifier.EXPECTED["legacy_public_api"]), 36)
        self.assertEqual(len(verifier.EXPECTED["public_api"]), 4)
        self.assertEqual(verifier.EXPECTED["qualification"]["transport_default_parallel_test_groups"], 20)
        self.assertEqual(verifier.EXPECTED["qualification"]["sender_default_proc_host_groups"], 0)
        self.assertFalse(verifier.EXPECTED["qualification"]["sender_default_proc_host_execution_proven"])
        self.assertFalse(verifier.EXPECTED["qualification"]["sender_caller_adopted"])
        self.assertFalse(verifier.EXPECTED["qualification"]["measured_speedup_claim"])
        self.assertFalse(verifier.EXPECTED["qualification"]["production_ready"])

    def test_sender_unknown_current_bytes_rebound_catalog_hits_independent_guard(self):
        from unittest import mock
        for path in verifier.SENDER_SOURCE_SHA256:
            values = self.texts()
            values[path] += "\n"
            rebound = copy.deepcopy(verifier.EXPECTED)
            rebound["actual_source_sha256"][path] = verifier.hashlib.sha256(values[path].encode()).hexdigest()
            with self.subTest(path=path), mock.patch.object(verifier, "EXPECTED", rebound):
                with self.assertRaisesRegex(ValueError, "^independent sender readiness physical Source differs$"):
                    verifier.check(rebound, values)

    def test_sender_order_authority_and_signature_mutations_rebound_to_exact_guard(self):
        from unittest import mock
        cases = [
            (verifier.TRANSPORT_READINESS, "self.transaction.channel.owner()?;", ""),
            (verifier.TRANSPORT_READINESS, "self.transaction.readiness_enabled = true;", "self.transaction.readiness_enabled = false;"),
            (verifier.TRANSPORT_READINESS, "readable_now(self.transaction.verify()?)?", "false"),
            (verifier.TRANSPORT_READINESS, "pub fn report_readable_now(&mut self)", "pub fn report_readable_now(&mut self, fd: i32)"),
            (verifier.PEER_READINESS, "creator(self.owner_pid)?;", ""),
            (verifier.PEER_READINESS, ".idle_reporting_scope()?;", ".current()?;"),
            (verifier.PEER_READINESS, ".report_readable_now()", ".cancel_readable_now()"),
            (verifier.PEER_READINESS, "self.poll_retirement()", "Ok(None)"),
            (verifier.PEER_READINESS, "remaining(self.owner_pid, self.deadline)?;", "remaining(self.owner_pid, Instant::now() + Duration::from_secs(20))?;"),
            (verifier.PEER_READINESS, "self.retire()?;", ""),
            (verifier.PEER_READINESS, "Ok(None)", "mint_report_permission(); Ok(None)"),
        ]
        for path, before, after in cases:
            values = self.texts()
            self.assertIn(before, values[path])
            values[path] = values[path].replace(before, after, 1)
            rebound = copy.deepcopy(verifier.EXPECTED)
            rebound["actual_source_sha256"][path] = verifier.hashlib.sha256(values[path].encode()).hexdigest()
            with self.subTest(path=path, before=before), mock.patch.object(verifier, "EXPECTED", rebound):
                with self.assertRaisesRegex(ValueError, "^independent sender readiness physical Source differs$"):
                    verifier.check(rebound, values)


if __name__ == "__main__":
    unittest.main()
