"""P2A Source correspondence and concrete refusal probes; no Rust execution."""
import copy
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

from tools import verify_approved_service_actor as gate


CORE = 'crates/hepta-browser-actor-simulation/src/engine_dispatch/event_loop/service_event_loop/service_actor.rs'
THIN = 'crates/hepta-browser-actor/src/servo_runtime/service_runtime/service_actor.rs'
BRIDGE = 'crates/hepta-browser-actor-simulation/src/engine_dispatch/event_loop/service_event_loop.rs'
ACTOR_ROOT = 'crates/hepta-browser-actor/src/lib.rs'


class ServiceActorSourceTests(unittest.TestCase):
    def test_actual_complete_contract_and_private_inventory(self):
        gate.validate()
        self.assertEqual(len(gate.EXPECTED['public_api']), 20)
        self.assertEqual(len(gate.EXPECTED['opaque_types']), 2)
        self.assertIn('ServiceScopedRuntime', gate.EXPECTED['private_type_inventory'][CORE])
        self.assertIn('await_final_forward', gate.EXPECTED['private_function_inventory'][CORE])

    def test_linux_service_actor_export_has_exact_linux_cfg_and_no_legacy_escape(self):
        text = gate.inputs()[ACTOR_ROOT]
        blocks = list(re.finditer(r'pub use servo_runtime::\{([^}]*)\};', text))
        self.assertEqual(len(blocks), 2)
        selected = [block for block in blocks if 'ServiceServoBrowserActor' in block.group(1)]
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0], blocks[1])
        self.assertRegex(text[:selected[0].start()], r'#\[cfg\(target_os = "linux"\)\]\s*$')
        legacy = blocks[0].group(0)
        restored = gate.parent_source(ACTOR_ROOT, text)
        self.assertEqual(re.search(r'pub use servo_runtime::\{[^}]*\};', restored).group(0), legacy)

    def test_moving_linux_actor_back_to_unconditional_export_refuses(self):
        texts = gate.inputs()
        text = texts[ACTOR_ROOT]
        self.assertEqual(text.count('ServiceServoBrowserActor,'), 1)
        text = text.replace('ServiceServoBrowserActor, ', '', 1)
        text = text.replace('pub use servo_runtime::{',
                            'pub use servo_runtime::{\n    ServiceServoBrowserActor,', 1)
        first = re.search(r'pub use servo_runtime::\{([^}]*)\};', text)
        self.assertIn('ServiceServoBrowserActor', first.group(1))
        texts[ACTOR_ROOT] = text
        with self.assertRaises(ValueError):
            gate.check(gate.EXPECTED, texts)

    def test_exact_whole_parent_inverses_and_parent_view(self):
        for path, rule in gate.EXPECTED['finite_parent_inverse'].items():
            actual = gate._read(gate.ROOT, path)
            restored = gate.parent_source(path, actual)
            self.assertEqual(len(restored.encode()), rule['parent_bytes'])
            self.assertEqual(gate._sha(restored.encode()), rule['parent_sha256'])
            self.assertEqual(gate.parent_source(path, restored), restored)

    def test_parent_view_cannot_replace_actual_complete_source(self):
        texts = gate.inputs()
        path = next(iter(gate.EXPECTED['finite_parent_inverse']))
        texts[path] = gate.parent_source(path, texts[path])
        with self.assertRaises(ValueError):
            gate.check(gate.EXPECTED, texts)

    def test_unknown_source_cannot_normalize(self):
        for path in gate.EXPECTED['finite_parent_inverse']:
            with self.assertRaises(ValueError):
                gate.parent_source(path, gate._read(gate.ROOT, path) + '\n// unknown\n')

    def test_caller_changed_contract_hash_cannot_approve_raw_getter(self):
        texts = gate.inputs()
        texts[CORE] += '\npub fn raw_actor() -> bool { true }\n'
        contract = copy.deepcopy(gate.EXPECTED)
        contract['production_sha256'][CORE] = gate._sha(texts[CORE].encode())
        with self.assertRaises(ValueError):
            gate.check(contract, texts)

    def test_schema_types_and_scope_claims_are_closed(self):
        for key, value in [('default_activation', 0), ('new_api_count', 21),
                           ('private_type_inventory', {})]:
            contract = copy.deepcopy(gate.EXPECTED)
            contract[key] = value
            with self.assertRaises(ValueError):
                gate.check(contract, gate.inputs())
        contract = copy.deepcopy(gate.EXPECTED)
        contract['scope']['actual_native_consumer'] = True
        with self.assertRaises(ValueError):
            gate.check(contract, gate.inputs())

    def test_missing_and_extra_source_refuse(self):
        texts = gate.inputs()
        texts.pop(CORE)
        with self.assertRaises(ValueError):
            gate.check(gate.EXPECTED, texts)
        texts = gate.inputs()
        texts['observed_approval.rs'] = 'pub fn observed() {}'
        with self.assertRaises(ValueError):
            gate.check(gate.EXPECTED, texts)

    def test_reader_refuses_symlink_hardlink_fifo_and_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'real').write_text('bounded')
            (root / 'link').symlink_to('real')
            os.link(root / 'real', root / 'second')
            os.mkfifo(root / 'fifo')
            for name in ['link', 'second', 'fifo', '.']:
                with self.assertRaises(ValueError):
                    gate._read(root, name)

    def test_reader_regular_to_fifo_race_refuses_without_blocking(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / 'input'
            path.write_text('bounded')
            real_open = os.open

            def replaced_open(value, flags):
                path.unlink()
                os.mkfifo(path)
                self.assertTrue(flags & os.O_NONBLOCK)
                return real_open(value, flags)

            with mock.patch.object(gate.os, 'open', replaced_open):
                with self.assertRaises(ValueError):
                    gate._read(root, 'input')

    def test_reader_refuses_oversize_and_invalid_utf8(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'large').write_bytes(b'x' * 1048577)
            (root / 'binary').write_bytes(b'\xff')
            with self.assertRaises(ValueError):
                gate._read(root, 'large')
            with self.assertRaises(UnicodeError):
                gate._read(root, 'binary')


MUTANTS = [
    (ACTOR_ROOT, 'ServiceServoBrowserActor, ServiceServoRuntimeBridge,',
     'ServiceServoRuntimeBridge,'),
    (CORE, 'inner: BrowserActor<ServiceScopedRuntime>', 'pub inner: BrowserActor<ServiceScopedRuntime>'),
    (CORE, 'inner: EngineThreadRuntime', 'pub inner: EngineThreadRuntime'),
    (CORE, '_binding: ApprovedServiceRequestBinding', '_binding: Option<ApprovedServiceRequestBinding>'),
    (CORE, 'session.ensure_current().map_err(approval_error)?;', 'let _ = session;'),
    (CORE, 'binding.verify_for_service(session)', 'binding.verify_observed_policy(session)'),
    (CORE, 'peer != context.peer', 'false'),
    (CORE, 'previous_principal.is_some_and(|p| p != &principal)', 'false'),
    (CORE, 'context.effective_deadline > original', 'false'),
    (CORE, 'self.prepared.is_some()', 'false'),
    (CORE, '!self.inner.cancellation_tokens.is_empty()', 'false'),
    (CORE, 'self.inner.request_authority.borrow().is_some()', 'false'),
    (CORE, 'self.inner.control_authority.borrow().is_some()', 'false'),
    (CORE, 'self.inner.runtime.scope.runtime_started.load(Ordering::SeqCst)', 'false'),
    (CORE, 'self.inner.runtime.scope = prepared.scope.clone();', 'self.inner.runtime.scope = previous_scope;'),
    (CORE, 'canonical != prepared.scope.original_canonical', 'false'),
    (CORE, 'context.accepted_at != original.accepted_at', 'false'),
    (CORE, 'context.transport_sequence != original.transport_sequence', 'false'),
    (CORE, 'if ui_mode != "headed"', 'if false'),
    (CORE, 'runtime_request.deadline_unix_ms = None;', 'runtime_request.request_id.clear();'),
    (CORE, 'control.deadline != self.scope.dispatch_deadline', 'false'),
    (CORE, 'control.ensure_current_peer()?;', 'control.ensure_active()?;'),
    (CORE, 'await_final_forward(&self.engine, &self.scope, Some(control), None)?;', 'let _ = control;'),
    (CORE, 'await_final_forward(&self.engine, &scope, None, Some(context))', 'Ok::<(), RuntimeFailure>(())'),
    (CORE, 'scope.runtime_finished.load(Ordering::SeqCst)', 'true'),
    (CORE, 'scope.current(engine)?;', 'let _ = engine;'),
    (CORE, 'std::thread::yield_now();', 'return Ok(());'),
    (CORE, 'self.uncertain.store(true, Ordering::SeqCst);', 'self.uncertain.store(false, Ordering::SeqCst);'),
    (CORE, 'self.engine.closed.store(true, Ordering::SeqCst);', 'self.engine.closed.store(false, Ordering::SeqCst);'),
    (CORE, 'original binding must remain through bridge post samples', 'binding can retire at physical send'),
    (CORE, 'closed service does not admit semantic action', 'caller selected semantic action runtime'),
    (BRIDGE, 'original != self.original_canonical', 'false'),
    (BRIDGE, 'expected_engine != self.engine_canonical', 'false'),
    (BRIDGE, 'active.call.control.ensure_active()', 'Ok::<(), RuntimeFailure>(())'),
    (BRIDGE, 'active.scope.runtime_finished.store(true, Ordering::SeqCst);', 'active.scope.runtime_finished.store(false, Ordering::SeqCst);'),
    (THIN, 'inner: ServiceBrowserActorCore', 'pub inner: ServiceBrowserActorCore'),
]


def mutant_test(path, old, new):
    def test(self):
        texts = gate.inputs()
        parts = re.findall(r'"(?:\\.|[^"\\])*"|[A-Za-z_][A-Za-z_0-9]*|[0-9]+|[^\s]', old)
        pattern = r'\s*'.join(re.escape(part) for part in parts)
        self.assertRegex(texts[path], pattern)
        texts[path], count = re.subn(pattern, lambda _: new, texts[path], count=1)
        self.assertEqual(count, 1)
        with self.assertRaises(ValueError):
            gate.check(json.loads(json.dumps(gate.EXPECTED)), texts)
    return test


for index, values in enumerate(MUTANTS):
    setattr(ServiceActorSourceTests, 'test_source_mutant_%02d_refuses' % index, mutant_test(*values))


if __name__ == '__main__':
    unittest.main()
