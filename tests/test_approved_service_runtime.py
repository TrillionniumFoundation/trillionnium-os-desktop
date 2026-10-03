"""P2B bounded Source refusals. No Rust, process or native qualification."""
import copy
import json
import os
from pathlib import Path
import re
import tempfile
import unittest

from tools import verify_approved_service_runtime as gate


class ServiceRuntimeSourceTests(unittest.TestCase):
    def test_actual_complete_source_contract(self):
        gate.validate()

    def test_actual_21_api_and_8_opaque_inventory(self):
        self.assertEqual(len(gate.EXPECTED['public_api']), 21)
        self.assertEqual(len(gate.EXPECTED['opaque_types']), 8)
        self.assertFalse(gate.EXPECTED['scope']['public_registration_api'])
        self.assertFalse(gate.EXPECTED['scope']['actor_coordinator_managed_factory_installed_activation'])

    def test_complete_parent_inverse_restores_every_byte(self):
        for path, rule in gate.EXPECTED['finite_parent_inverse'].items():
            actual = gate._read(gate.ROOT, path)
            restored = gate.parent_source(path, actual).encode()
            self.assertEqual(len(restored), rule['parent_bytes'])
            self.assertEqual(gate._sha(restored), rule['parent_sha256'])
            self.assertEqual(gate.parent_source(path, restored.decode()), restored.decode())

    def test_unknown_complete_parent_never_normalizes(self):
        for path in gate.EXPECTED['finite_parent_inverse']:
            with self.assertRaises(ValueError):
                gate.parent_source(path, gate._read(gate.ROOT, path) + '\n// unreviewed\n')

    def test_self_changed_contract_source_hash_does_not_approve_mutation(self):
        texts = gate.inputs()
        path = next(iter(gate.EXPECTED['production_sha256']))
        texts[path] += '\npub fn fabricated_approval() -> bool { true }\n'
        contract = copy.deepcopy(gate.EXPECTED)
        contract['production_sha256'][path] = gate._sha(texts[path].encode())
        with self.assertRaises(ValueError):
            gate.check(contract, texts)

    def test_boolean_integer_schema_alias_refuses(self):
        contract = copy.deepcopy(gate.EXPECTED)
        contract['default_activation'] = 0
        with self.assertRaises(ValueError):
            gate.check(contract, gate.inputs())

    def test_missing_source_refuses(self):
        texts = gate.inputs()
        texts.pop(next(iter(texts)))
        with self.assertRaises(ValueError):
            gate.check(gate.EXPECTED, texts)

    def test_unknown_source_refuses(self):
        texts = gate.inputs()
        texts['fake.rs'] = 'pub fn observed_principal() {}'
        with self.assertRaises(ValueError):
            gate.check(gate.EXPECTED, texts)

    def test_source_reader_refuses_symlink_and_hardlink(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'real').write_text('bounded')
            (root / 'link').symlink_to('real')
            with self.assertRaises(ValueError):
                gate._read(root, 'link')
            os.link(root / 'real', root / 'second')
            with self.assertRaises(ValueError):
                gate._read(root, 'second')

    def test_source_reader_refuses_size_and_non_utf8(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'large').write_bytes(b'x' * 1048577)
            with self.assertRaises(ValueError):
                gate._read(root, 'large')
            (root / 'binary').write_bytes(b'\xff')
            with self.assertRaises(UnicodeError):
                gate._read(root, 'binary')


SIMULATION = 'crates/hepta-browser-actor-simulation/src/engine_dispatch/event_loop/service_event_loop.rs'
SERVO = 'crates/hepta-browser-actor/src/servo_runtime/service_runtime.rs'
MUTANTS = [
    (SIMULATION, 'self.session.ensure_current()', 'Ok::<(), hepta_peer_attestation::ApprovedPolicyError>(())'),
    (SIMULATION, 'session: OnceLock<Arc<ApprovedServiceSessionVerifier>>',
     'session: Mutex<Option<Arc<ApprovedServiceSessionVerifier>>>'),
    (SIMULATION, 'self.service_current()?;', 'self.creator()?;'),
    (SIMULATION, 'if self.session.get().is_none()', 'if false'),
    (SIMULATION, 'let bound = engine.session.get().ok_or(RuntimeFailure::PeerIdentityRevoked)?;',
     'let bound = engine.session.wait();'),
    (SIMULATION, 'original_deadline != self.original_deadline', 'false'),
    (SIMULATION, '!Arc::ptr_eq(&origin, engine)', 'false'),
    (SIMULATION, '!Arc::ptr_eq(&registration.nonce, &scope.nonce)', 'false'),
    (SIMULATION, 'scope.dispatch_deadline != call.control.deadline', 'false'),
    (SIMULATION, 'scope.operation != call.request.operation', 'false'),
    (SIMULATION, 'self.dispatch_deadline > self.original_deadline', 'false'),
    (SIMULATION, 'EngineUrlScope::ClosedImmutableReadOnly', 'EngineUrlScope::D3Local'),
    (SIMULATION, 'active.scope.current(&self.state)', 'Ok::<(), RuntimeFailure>(())'),
    (SIMULATION, 'let current = active.call.control.ensure_active()\n            .and_then(|()| active.scope.current(&self.state));',
     'let current = active.scope.current(&self.state);'),
    (SIMULATION, '.and_then(|reply| active.scope.current(&self.state).map(|()| reply))',
     '.or_else(|_| Ok(RuntimeReply { result: Default::default(), current_url: None }))'),
    (SIMULATION, 'self.state.closed.store(true, Ordering::SeqCst)', 'self.state.closed.store(false, Ordering::SeqCst)'),
    (SIMULATION, 'session: OnceLock::new()', 'session: caller_session'),
    (SIMULATION, 'inner: Option<EngineThreadRuntime>', 'pub inner: Option<EngineThreadRuntime>'),
    (SIMULATION, 'inner: Option<EngineCompletion>', 'pub inner: Option<EngineCompletion>'),
    (SERVO, 'inner: Option<ServiceEngineEndpoint>', 'pub inner: Option<ServiceEngineEndpoint>'),
    (SERVO, 'inner: ServiceEngineCompletion', 'pub inner: ServiceEngineCompletion'),
    (SERVO, 'self.inner.ensure_current_request()', 'Ok::<(), RuntimeFailure>(())'),
    (SERVO, 'completion.complete(Err(RuntimeFailure::PolicyDenied("closed service mapping refused",)))',
     'completion.complete(Ok(RuntimeReply { result: Default::default(), current_url: None }))'),
]


def mutation_test(path, old, new):
    def test(self):
        texts = gate.inputs()
        # Rustfmt may break a fixed expression across lines. Match only its
        # exact identifiers/punctuation and literal bytes, allowing whitespace.
        parts = re.findall(r'"(?:\\.|[^"\\])*"|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|[^\s]', old)
        pattern = r'\s*'.join(re.escape(part) for part in parts)
        self.assertRegex(texts[path], pattern)
        texts[path], count = re.subn(pattern, lambda _: new, texts[path], count=1)
        self.assertEqual(count, 1)
        with self.assertRaises(ValueError):
            gate.check(json.loads(json.dumps(gate.EXPECTED)), texts)
    return test


for index, values in enumerate(MUTANTS):
    setattr(ServiceRuntimeSourceTests, 'test_source_mutant_%02d_refuses' % index, mutation_test(*values))


if __name__ == '__main__':
    unittest.main()
