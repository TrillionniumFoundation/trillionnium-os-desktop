"""P2C finite Source correspondence and concrete mutants, no Rust execution."""
import copy
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

from tools import verify_approved_service_product as gate

BASE = 'apps/hepta-browserd/src/product_dispatch/service_product.rs'
COORD = 'apps/hepta-browserd/src/product_dispatch/service_product/coordinator.rs'
LIFE = 'apps/hepta-browserd/src/product_dispatch/service_product/lifecycle.rs'
REPORT = 'apps/hepta-browserd/src/product_dispatch/service_product/report.rs'
WIRE = 'apps/hepta-browserd/src/product_dispatch/service_product/wire.rs'
DENIAL = 'crates/hepta-agent-transport/src/accepted_handoff/connected_denial.rs'


class ServiceProductSourceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texts = gate.inputs()

    def test_actual_full_chain_inventory_and_closed_claims(self):
        gate.validate()
        self.assertEqual(len(gate.EXPECTED['product_public_api']), 9)
        self.assertEqual(len(gate.EXPECTED['product_opaque_types']), 2)
        self.assertEqual(len(gate.EXPECTED['product_diagnostic_enums']), 2)
        self.assertEqual(len(gate.EXPECTED['transport_public_api']), 2)
        self.assertEqual(len(gate.EXPECTED['transport_opaque_types']), 1)
        self.assertEqual(len(gate.EXPECTED['preserved_original_sha256']) + len(gate.EXPECTED['finite_parent_inverse']), 679)
        self.assertFalse(gate.EXPECTED['scope']['actual_rust_compilation'])
        self.assertFalse(gate.EXPECTED['scope']['actual_kernel_corpus'])
        self.assertFalse(gate.EXPECTED['scope']['native60'])
        self.assertFalse(gate.EXPECTED['scope']['G6_approval'])
        self.assertIn('ServiceTerminalSeal', gate.EXPECTED['private_type_inventory'][LIFE])

    def test_complete_parent_inverses_are_exact_and_idempotent(self):
        for path, rule in gate.EXPECTED['finite_parent_inverse'].items():
            restored = gate.parent_source(path, self.texts[path])
            self.assertEqual(len(restored.encode()), rule['parent_bytes'])
            self.assertEqual(gate._sha(restored.encode()), rule['parent_sha256'])
            self.assertEqual(gate.parent_source(path, restored), restored)

    def test_unknown_parent_cannot_normalize(self):
        for path in gate.EXPECTED['finite_parent_inverse']:
            with self.subTest(path=path), self.assertRaises(ValueError):
                gate.parent_source(path, self.texts[path] + '\n// unknown bytes\n')

    def test_parent_view_cannot_replace_actual_complete_object(self):
        for path in gate.EXPECTED['finite_parent_inverse']:
            texts = dict(self.texts)
            texts[path] = gate.parent_source(path, texts[path])
            with self.subTest(path=path), self.assertRaises(ValueError):
                gate.check(gate.EXPECTED, texts)

    def test_caller_changed_hash_cannot_approve_public_receipt_seal(self):
        texts = dict(self.texts)
        texts[LIFE] += '\npub fn observed_native_success() -> bool { true }\n'
        contract = copy.deepcopy(gate.EXPECTED)
        contract['production_sha256'][LIFE] = gate._sha(texts[LIFE].encode())
        with self.assertRaises(ValueError):
            gate.check(contract, texts)

    def test_boolean_integer_alias_and_new_release_claim_refuse(self):
        for key, value in [('default_activation', 0), ('schema', None), ('product_public_api', {})]:
            contract = copy.deepcopy(gate.EXPECTED)
            contract[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                gate.check(contract, self.texts)
        for key in ['installed', 'actual_rust_compilation', 'actual_kernel_corpus', 'native60', 'G6_approval']:
            contract = copy.deepcopy(gate.EXPECTED)
            contract['scope'][key] = True
            with self.subTest(key=key), self.assertRaises(ValueError):
                gate.check(contract, self.texts)

    def test_missing_or_extra_source_refuses(self):
        texts = dict(self.texts)
        texts.pop(WIRE)
        with self.assertRaises(ValueError):
            gate.check(gate.EXPECTED, texts)
        texts = dict(self.texts)
        texts['caller-approved.rs'] = 'pub fn runtime_approved() -> bool { true }'
        with self.assertRaises(ValueError):
            gate.check(gate.EXPECTED, texts)

    def test_original_A_B_P1_whole_source_change_refuses(self):
        paths = [
            'crates/hepta-peer-attestation/src/approved_policy/service_policy/request_bridge.rs',
            'crates/hepta-browser-actor-simulation/src/engine_dispatch/event_loop/service_event_loop.rs',
            'crates/hepta-browser-actor-simulation/src/engine_dispatch/event_loop/service_event_loop/service_actor.rs',
            'Cargo.toml', 'Cargo.lock', 'apps/hepta-browserd/src/main.rs',
        ]
        for path in paths:
            texts = dict(self.texts)
            texts[path] += '\n// substituted original\n'
            with self.subTest(path=path), self.assertRaises(ValueError):
                gate.check(gate.EXPECTED, texts)

    def test_reader_refuses_symlink_hardlink_fifo_and_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'real').write_text('bounded')
            (root / 'link').symlink_to('real')
            os.link(root / 'real', root / 'second')
            os.mkfifo(root / 'fifo')
            for name in ['link', 'real', 'fifo', '.']:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    gate._read(root, name)

    def test_reader_regular_to_fifo_race_refuses_without_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'real').write_text('bounded')
            original_open = os.open
            def substitute(path, flags):
                (root / 'real').rename(root / 'preserved')
                os.mkfifo(root / 'real')
                self.assertTrue(flags & os.O_NONBLOCK)
                return original_open(path, flags)
            with mock.patch.object(gate.os, 'open', side_effect=substitute), self.assertRaises(ValueError):
                gate._read(root, 'real')

    def test_reader_bounded_utf8_and_exact_source_type(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'large').write_bytes(b'x' * 1048577)
            (root / 'binary').write_bytes(b'\xff')
            with self.assertRaises(ValueError):
                gate._read(root, 'large')
            with self.assertRaises(UnicodeError):
                gate._read(root, 'binary')
        with self.assertRaises(ValueError):
            gate.parent_source(COORD, b'caller')

    def test_authored_units_and_compile_fail_examples_are_present_not_runtime_claims(self):
        for path, units in gate.EXPECTED['authored_unit_inventory_NOT_EXECUTED'].items():
            actual = re.findall(r'#\[test\]\s*fn\s+(\w+)', self.texts[path])
            self.assertEqual(actual, units)
        for path, snippets in gate.EXPECTED['compile_fail_inventory_NOT_EXECUTED'].items():
            actual = re.findall(r'```compile_fail(?:,[^\n]+)?\n(.*?)```', self.texts[path], re.S)
            self.assertEqual(actual, snippets)


MUTANTS = [
    (BASE, 'verifier.verify_for_service(session)', 'Ok::<(), ProductDispatchError>(())'),
    (BASE, 'self.cancelled.store(true, Ordering::SeqCst)', 'self.cancelled.store(false, Ordering::SeqCst)'),
    (BASE, 'self.cancelled.load(Ordering::SeqCst)', 'self.token.get().is_some_and(|t| t.is_cancelled())'),
    (BASE, 'self.token.set(token)', 'Ok::<(), CancellationToken>(())'),
    (COORD, 'owner.ensure_current()', 'Ok::<(), ProductDispatchError>(())'),
    (COORD, 'ApprovedServiceRequests::from_owner(owner)', 'requests_from_caller_snapshot(owner)'),
    (COORD, 'self.phase != ServiceProductPhase::Idle', 'false'),
    (COORD, '.bind_control(connection, expected_agent_path)', '.bind_control(new_connection(), expected_agent_path)'),
    (COORD, 'received.original_deadline()', 'Ok::<_, ProductDispatchError>(Instant::now() + Duration::from_secs(20))'),
    (COORD, 'received.consume_with_request_binding', 'consume_caller_observed_binding'),
    (COORD, 'input.binding.verify_for_service(&self.session)', 'verify_foreign_session(&input.binding)'),
    (COORD, 'OriginalConnectedDenial::capture_original(&input.stream)', 'OriginalConnectedDenial::capture_original(&new_agent_stream())'),
    (COORD, 'actor.prepare_original_request(binding, &decoded.context, &decoded.request)', 'actor.legacy_rebind_from_observation()'),
    (COORD, 'actor.retire_prepared_request()', 'Ok::<(), ProductDispatchError>(())'),
    (COORD, '.finish(trace.seal.take())', '.finish(caller_terminal_seal())'),
    (COORD, 'invocation.may_dispatch = true', 'invocation.may_dispatch = false'),
    (COORD, 'lifecycle.requested(invocation)?', 'Ok::<(), ProductDispatchError>(())?'),
    (COORD, 'lifecycle.dispatched(invocation)?', 'Ok::<(), ProductDispatchError>(())?'),
    (COORD, 'lifecycle.completed(invocation, &response)?', 'observed_completion_flag()'),
    (LIFE, '!Arc::ptr_eq(&self.nonce, nonce)', 'false'),
    (LIFE, '!Arc::ptr_eq(&self.writer, writer)', 'false'),
    (LIFE, 'self.deadline != deadline', 'false'),
    (LIFE, 'journal.has_unresolved_receipts()', 'Ok::<_, ProductDispatchError>(false)'),
    (LIFE, 'journal.execution_reconciliation_facts()', 'Ok::<Vec<()>, ProductDispatchError>(Vec::new())'),
    (LIFE, 'self.journal.contains_receipt(request_id)', 'Ok::<_, ProductDispatchError>(false)'),
    (LIFE, 'self.logical_clock.checked_add(1)', 'Some(1)'),
    (LIFE, 'self.failed = true', 'self.failed = false'),
    (LIFE, 'self.journal.append(event)', 'caller_ack_without_storage(event)'),
    (LIFE, 'self.journal.receipt_fact', 'self.journal.inspect_active_segment_fact'),
    (LIFE, 'committed.record_sha256', '[1; 32]'),
    (LIFE, 'Some(lifecycle) != invocation.terminal', 'false'),
    (LIFE, 'self.uncertain = true', 'self.uncertain = false'),
    (REPORT, 'mpsc::sync_channel(1)', 'mpsc::channel()'),
    (REPORT, 'report.poll_cancel()', 'Ok::<_, ProductDispatchError>(token.is_cancelled())'),
    (REPORT, 'report.original_deadline()', 'Ok::<_, ProductDispatchError>(Instant::now() + Duration::from_secs(20))'),
    (REPORT, 'wake.take()', 'replacement_wake.take()'),
    (REPORT, 'seal.consume_report(&nonce, &writer, deadline)', 'caller_report_from_diagnostic()'),
    (REPORT, 'drop(reporter.take())', 'std::mem::forget(reporter.take())'),
    (REPORT, 'drop(custody.take())', 'std::mem::forget(custody.take())'),
    (REPORT, '.is_finished()', '.join().is_ok()'),
    (WIRE, 'ServerConnection::accept', 'caller_authenticated_stream'),
    (WIRE, 'decoded.canonical_bytes != frame.payload', 'false'),
    (WIRE, 'decoded.canonical_sha256 != executable_sha256(&frame.payload)', 'false'),
    (WIRE, 'decoded.context.effective_deadline > self.original_deadline', 'false'),
    (WIRE, 'original_current(verifier, session, decoded.context.effective_deadline)?', 'Ok::<(), ProductDispatchError>(())?'),
    (WIRE, 'response_committed: true', 'response_committed: caller_native_success'),
    (DENIAL, 'stream.try_clone()', 'UnixStream::connect(caller_path)'),
    (DENIAL, 'peer.pid != Some(creator_pid)', 'false'),
    (DENIAL, 'socket_identity(stream.as_raw_fd())? != self.identity', 'false'),
    (DENIAL, 'self.creator_current()?', 'Ok::<(), HandoffError>(())?'),
    (DENIAL, 'Shutdown::Both', 'Shutdown::Write'),
    (DENIAL, 'self.stream.take()', 'self.stream.take().map(|s| s.shutdown(Shutdown::Both))'),
]


def mutation_test(path, old, new):
    def test(self):
        texts = dict(self.texts)
        parts = re.findall(r'"(?:\\.|[^"\\])*"|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|[^\s]', old)
        pattern = r'\s*'.join(re.escape(part) for part in parts)
        self.assertRegex(texts[path], pattern)
        texts[path], count = re.subn(pattern, lambda _: new, texts[path], count=1)
        self.assertEqual(count, 1)
        with self.assertRaises(ValueError):
            gate.check(json.loads(json.dumps(gate.EXPECTED)), texts)
    return test


for index, mutant in enumerate(MUTANTS):
    setattr(ServiceProductSourceTests, 'test_source_mutant_%02d_refuses' % index, mutation_test(*mutant))


if __name__ == '__main__':
    unittest.main()
