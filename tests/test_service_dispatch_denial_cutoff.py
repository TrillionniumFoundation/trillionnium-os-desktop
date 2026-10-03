"""Actual physical Source mutants; no invented runtime binding or Native claim."""
import copy
import difflib
import json
import os
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

from tools import verify_service_dispatch_denial_cutoff as gate

B = 'crates/hepta-browser-actor-simulation/src/engine_dispatch/event_loop/service_event_loop.rs'
A = 'crates/hepta-browser-actor/src/servo_runtime/service_runtime.rs'
CORE = 'crates/hepta-browser-actor-simulation/src/engine_dispatch/event_loop/service_event_loop/service_actor.rs'


def inverse(parent, complete, old_rule):
    rule = copy.deepcopy(old_rule)
    rule.update(complete_bytes=len(complete.encode()), complete_sha256=gate._sha(complete.encode()))
    rule['edits'] = []
    parent_lines, complete_lines = parent.splitlines(True), complete.splitlines(True)
    parent_offsets, complete_offsets = [0], [0]
    for line in parent_lines:
        parent_offsets.append(parent_offsets[-1] + len(line))
    for line in complete_lines:
        complete_offsets.append(complete_offsets[-1] + len(line))
    for tag, a, b, x, y in difflib.SequenceMatcher(None, parent_lines, complete_lines, autojunk=False).get_opcodes():
        if tag != 'equal':
            a, b, x, y = parent_offsets[a], parent_offsets[b], complete_offsets[x], complete_offsets[y]
            rule['edits'].append({'complete_start': x, 'complete_end': y,
                                  'complete_text': complete[x:y], 'parent_text': parent[a:b]})
    return rule


def rebind_derived_metadata(contract, texts, baseline):
    """Simulate a changed whole contract envelope, hashes, inventories and inverse.

    This deliberately updates every derived physical field, not only a digest.
    The independent hardcoded implementation and inverse policy must still deny.
    """
    rebound = copy.deepcopy(contract)
    for path, rule in contract['finite_parent_inverse'].items():
        parent = gate.parent_source(path, baseline[path])
        rebound['finite_parent_inverse'][path] = inverse(parent, texts[path], rule)
    public, opaque = {}, {}
    for path in rebound['physical_Rust_files3']:
        inventory = gate.parser.rust_inventory(texts[path])
        rebound['all_function_tokens_sha256'][path] = {n: gate._sha(' '.join(b).encode())
                                                     for n, b in inventory['functions'].items()}
        rebound['all_type_inventory'][path] = {
            n: {'kind': s['kind'], 'public': s['public'], 'body': ' '.join(s['body'])}
            for n, s in inventory['types'].items()}
        rebound['public_api_by_file'][path] = inventory['public_api']
        if path in rebound['runtime_Rust_files2']:
            public.update(inventory['public_api'])
            opaque.update({n: ' '.join(s['body']) for n, s in inventory['types'].items() if s['public']})
    rebound['actual_runtime_public_api23'] = public
    rebound['actual_runtime_opaque_types8'] = opaque
    for group in ('preserved_original_sha256', 'supplemental_source_sha256'):
        for path in rebound[group]:
            rebound[group][path] = gate._sha(texts[path].encode())
    rebound['checker_nonEXPECTED_whole_sha256'] = gate._sha(gate.checker_body(texts[gate.TOOL]).encode())
    for path in rebound['new_compile_fail_inventory_NOT_EXECUTED']:
        rebound['new_compile_fail_inventory_NOT_EXECUTED'][path] = re.findall(
            r'```compile_fail,E0596\n(.*?)```', texts[path], re.S)
    return rebound


class ServiceDispatchDenialCutoffTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texts = gate.inputs()

    def test_actual_physical_Source_and_inventory(self):
        gate.validate()
        self.assertEqual(len(gate.EXPECTED['actual_runtime_public_api23']), 23)
        self.assertEqual(len(gate.EXPECTED['actual_runtime_opaque_types8']), 8)
        self.assertEqual(len(gate.EXPECTED['finite_parent_inverse']), 6)
        self.assertEqual(len(gate.EXPECTED['preserved_original_sha256']), 684)
        self.assertFalse(gate.EXPECTED['scope']['installed'])
        self.assertFalse(gate.EXPECTED['scope']['Native5'])
        self.assertFalse(gate.EXPECTED['scope']['Native60'])
        self.assertFalse(gate.EXPECTED['scope']['G6_approval'])

    def test_six_whole_inverses_and_all_historical_views_are_exact(self):
        for path, rule in gate.EXPECTED['finite_parent_inverse'].items():
            parent = gate.parent_source(path, self.texts[path])
            self.assertEqual([len(parent.encode()), gate._sha(parent.encode())],
                             [rule['parent_bytes'], rule['parent_sha256']])
            self.assertEqual(gate.parent_source(path, parent), parent)
            with self.subTest(path=path), self.assertRaises(ValueError):
                gate.parent_source(path, self.texts[path] + '\n// unknown changed bytes\n')

    def test_historical_parent_cannot_replace_actual_physical_input(self):
        for path in gate.EXPECTED['finite_parent_inverse']:
            texts = dict(self.texts)
            texts[path] = gate.parent_source(path, texts[path])
            with self.subTest(path=path), self.assertRaises(ValueError):
                gate.check(gate.EXPECTED, texts)

    def test_independent_normalizer_does_not_trust_rebound_contract(self):
        path = 'Makefile'
        texts = dict(self.texts)
        texts[path] += '# caller altered known object\n'
        rebound = rebind_derived_metadata(gate.EXPECTED, texts, self.texts)
        with mock.patch.object(gate, 'EXPECTED', rebound), self.assertRaises(ValueError):
            gate.parent_source(path, texts[path])

    def test_false_claim_type_alias_and_unknown_fields_refuse(self):
        for field, value in [('default_activation', 0), ('actual_runtime_public_api23', {}), ('schema', None)]:
            contract = copy.deepcopy(gate.EXPECTED)
            contract[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                gate.check(contract, self.texts)
        for field in gate.EXPECTED['scope']:
            if isinstance(gate.EXPECTED['scope'][field], bool) and not gate.EXPECTED['scope'][field]:
                contract = copy.deepcopy(gate.EXPECTED)
                contract['scope'][field] = True
                with self.subTest(field=field), self.assertRaises(ValueError):
                    gate.check(contract, self.texts)

    def test_actual_reader_is_not_a_normalized_parent_view(self):
        for path in gate.EXPECTED['finite_parent_inverse']:
            self.assertEqual(gate._read(gate.ROOT, path), self.texts[path])
        self.assertEqual(gate._read(gate.ROOT, B), self.texts[B])
        self.assertNotEqual(gate._read(gate.ROOT, B), gate.parent_source(B, self.texts[B]))

    def test_reader_symlink_hardlink_fifo_directory_and_bound_refuse(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'regular').write_text('bounded')
            (root / 'symlink').symlink_to('regular')
            os.link(root / 'regular', root / 'hardlink')
            os.mkfifo(root / 'fifo')
            (root / 'large').write_bytes(b'x' * 1048577)
            for name in ('regular', 'symlink', 'hardlink', 'fifo', '.', 'large'):
                with self.subTest(name=name), self.assertRaises(ValueError):
                    gate._read(root, name)

    def test_two_new_borrow_proofs_are_authored_not_executed(self):
        total = 0
        for path, expected in gate.EXPECTED['new_compile_fail_inventory_NOT_EXECUTED'].items():
            actual = re.findall(r'```compile_fail,E0596\n(.*?)```', self.texts[path], re.S)
            self.assertEqual(actual, expected)
            total += len(actual)
        self.assertEqual(total, 2)


MUTANTS = [
    (B, '.min(self.dispatch_deadline)', '.max(self.dispatch_deadline)', 0),
    (B, 'self.check_dispatch_cutoff()?;', 'Ok::<(), RuntimeFailure>(())?;', 0),
    (B, 'self.check_dispatch_cutoff()?;', 'Ok::<(), RuntimeFailure>(())?;', 2),
    (B, '.set(cutoff)', '.set(self.scope.dispatch_deadline)', 0),
    (CORE, 'shortened_deadline: OnceLock::new()', 'shortened_deadline: OnceLock::from(context.effective_deadline)', 0),
    (B, 'scope: scope.clone()', 'scope: caller_new_scope()', 0),
    (B, 'self.engine.creator()?;', 'Ok::<(), RuntimeFailure>(())?;', 0),
    (B, 'inner.request_id() != self.scope.request_id', 'false', 0),
    (B, 'active.scope.check_dispatch_cutoff().and(result)', 'result', 0),
    (B, 'active.scope.current(&self.state)', 'Ok::<(), RuntimeFailure>(())', 2),
    (CORE, 'scope.current(engine)?;', 'Ok::<(), RuntimeFailure>(())?;', 1),
    (B, '.map(|active| active.scope.dispatch_cutoff())', '.map(|active| active.scope.dispatch_deadline)', 0),
    (A, '.shorten_deadline_once(cutoff)', '.shorten_deadline_once(Instant::now())', 0),
    (B, 'scope.dispatch_deadline != call.control.deadline', 'scope.dispatch_cutoff() != call.control.deadline', 0),
    (B, 'shortened_deadline: OnceLock<Instant>', 'shortened_deadline: Instant', 0),
    (B, 'pub fn shorten_deadline_once(', 'pub fn caller_renew_deadline(', 0),
    ('Makefile', '\tpython3 tools/verify_service_dispatch_denial_cutoff.py\n', '', 0),
]


def mutation_test(path, old, new, occurrence):
    def test(self):
        texts = dict(self.texts)
        offsets = [m.start() for m in re.finditer(re.escape(old), texts[path])]
        self.assertGreater(len(offsets), occurrence, 'mutant must target an actual physical expression')
        offset = offsets[occurrence]
        texts[path] = texts[path][:offset] + new + texts[path][offset + len(old):]
        rebound = rebind_derived_metadata(gate.EXPECTED, texts, self.texts)
        with mock.patch.object(gate, 'EXPECTED', rebound), self.assertRaises(ValueError):
            gate.check(rebound, texts)
    return test


for index, mutant in enumerate(MUTANTS):
    setattr(ServiceDispatchDenialCutoffTests, 'test_full_rebinding_source_mutant_%02d_refuses' % index,
            mutation_test(*mutant))


if __name__ == '__main__':
    unittest.main()
