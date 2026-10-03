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
        self.assertEqual(len(gate.EXPECTED['preserved_original_sha256']), 672)
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




class JointPhysicalSourceBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texts = gate.inputs()

    def test_actual699_is_physical_and_all12_complete_inverses_are_closed(self):
        self.assertEqual(len(self.texts), 699)
        self.assertEqual(len(gate.EXPECTED['preserved_original_sha256']), 672)
        self.assertEqual(len(gate.CLOSED_JOINT_SOURCE_RULES), 12)
        gate.check(gate.EXPECTED, self.texts)
        for path, rule in gate.CLOSED_JOINT_SOURCE_RULES.items():
            self.assertEqual(gate._read(gate.ROOT, path), self.texts[path])
            restored = gate.joint_parent_source(path, self.texts[path])
            self.assertEqual([len(restored.encode()), gate._sha(restored.encode())],
                             [rule['parent_bytes'], rule['parent_sha256']])
            self.assertEqual(gate.joint_parent_source(path, restored), restored)

    def test_each12_unknown_bytes_and_stale_parent_refuse_actual_physical_stage(self):
        for path in gate.CLOSED_JOINT_SOURCE_RULES:
            for mutant in (self.texts[path] + '\n', self.texts[path] + '// loose EOF\n',
                           '// prefix\n' + self.texts[path],
                           gate.joint_parent_source(path, self.texts[path])):
                texts = dict(self.texts)
                texts[path] = mutant
                with self.subTest(path=path), self.assertRaises(ValueError):
                    gate.check(gate.EXPECTED, texts)
            with self.subTest(path=path), self.assertRaises(ValueError):
                gate.joint_parent_source(path, self.texts[path] + '\n')

    def test_rejected8ac_section_parser_cannot_be_the_current_custody_Source(self):
        for path in ('tools/validate_s04_transport_custody.py', 'tools/verify_systemd_socket_custody.py'):
            self.assertEqual(self.texts[path].count('section = line[1:-1]\n'), 1)
            texts = dict(self.texts)
            texts[path] = texts[path].replace('section = line[1:-1]\n',
                                           'section = line[1:-1].strip()\n', 1)
            with self.subTest(path=path), self.assertRaises(ValueError):
                gate.check(gate.EXPECTED, texts)
            with self.subTest(path=path), self.assertRaises(ValueError):
                gate.joint_parent_source(path, texts[path])

    def test_joint_contract_hash_rebinding_cannot_hide_changed_P1_guard_or_custody(self):
        for path in gate.CLOSED_JOINT_SOURCE_RULES:
            texts = dict(self.texts)
            texts[path] += '\n// caller rebound bytes\n'
            rebound = copy.deepcopy(gate.EXPECTED)
            rebound['joint_parent_inverse12'][path]['complete_bytes'] = len(texts[path].encode())
            rebound['joint_parent_inverse12'][path]['complete_sha256'] = gate._sha(texts[path].encode())
            texts[gate.CONTRACT] = gate.canonical_contract_text(rebound)
            with mock.patch.object(gate, 'EXPECTED', rebound), self.subTest(path=path), self.assertRaises(ValueError):
                gate.check(rebound, texts)
            with mock.patch.object(gate, 'EXPECTED', rebound), self.subTest(path=path), self.assertRaises(ValueError):
                gate.joint_parent_source(path, texts[path])

    def test_all17_full_rebound_mutants_hit_their_original_independent_guard(self):
        canonical = gate.expected_assignment(gate.EXPECTED)
        for index, (path, old, new, occurrence) in enumerate(MUTANTS):
            texts = dict(self.texts)
            offsets = [m.start() for m in re.finditer(re.escape(old), texts[path])]
            self.assertGreater(len(offsets), occurrence)
            offset = offsets[occurrence]
            texts[path] = texts[path][:offset] + new + texts[path][offset + len(old):]
            rebound = rebind_derived_metadata(gate.EXPECTED, texts, self.texts)
            # Rebind the complete physical canonical object and the exact literal
            # envelope too; neither raw bytes nor old checker hashes deny first.
            texts[gate.CONTRACT] = gate.canonical_contract_text(rebound)
            self.assertEqual(texts[gate.TOOL].count(canonical), 1)
            texts[gate.TOOL] = texts[gate.TOOL].replace(canonical, gate.expected_assignment(rebound), 1)
            # Index12 first matches the real authored compile-fail expression:
            # comments preserve Rust semantics but the independent whole inverse
            # rejects its changed Source. Index16 restores the registered d933
            # Makefile; the mandatory physical command guard refuses that view.
            guard = ('P3 unknown complete Source cannot normalize' if index == 12
                     else 'P3 mandatory physical Source gate differs' if index == 16
                     else 'P3 independent closed implementation')
            with mock.patch.object(gate, 'EXPECTED', rebound), self.subTest(index=index, target=guard):
                self.assertEqual(texts[gate.CONTRACT], gate.canonical_contract_text(gate.EXPECTED))
                self.assertEqual(gate._sha(gate.checker_body(texts[gate.TOOL]).encode()),
                                 rebound['checker_nonEXPECTED_whole_sha256'])
                with self.assertRaisesRegex(ValueError, re.escape(guard)):
                    gate.check(rebound, texts)

    def test_C_input_only_history_keeps_P1_Native_B_A_actual_guard_modules(self):
        from tools import verify_approved_service_product as product
        from tools import verify_approved_service_request as original
        actual = original.inputs()
        for path, wanted in original._CONSUME_GUARD_MODULES.items():
            self.assertEqual(actual[path], gate._read(gate.ROOT, path))
            self.assertEqual(original.sha256(actual[path]), wanted)
        for path in gate.CLOSED_JOINT_SOURCE_RULES:
            physical = gate._read(gate.ROOT, path)
            self.assertEqual(product.parent_source(path, physical), physical)
            self.assertEqual(product._read(gate.ROOT, path), gate.joint_parent_source(path, physical))
        original.check(original.EXPECTED, actual)
        product.validate()

    def test_all_four_actual_legacy_reader_stages_keep_exact_older_view(self):
        from tools import verify_approved_service_actor as actor
        from tools import verify_approved_service_runtime as runtime
        from tools import verify_approved_native_startup as native
        for path in gate.EXPECTED['finite_parent_inverse']:
            parent = gate.parent_source(path, self.texts[path])
            self.assertEqual(gate.parent_source(path, parent), parent)
        actor.validate()
        runtime.validate()
        native.validate()

    def test_directory_links_absolute_and_parent_traversal_refuse_before_read(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'real').mkdir()
            (root / 'real' / 'leaf').write_text('bounded')
            (root / 'link').symlink_to(root / 'real', target_is_directory=True)
            (root / 'root-link').symlink_to(root / 'real', target_is_directory=True)
            for source_root, relative in ((root, 'link/leaf'), (root / 'root-link', 'leaf'),
                                          (root, '../real/leaf'), (root, 'real/../real/leaf'),
                                          (root, str(root / 'real' / 'leaf')), (root, 'real//leaf')):
                with self.subTest(relative=relative), self.assertRaises(ValueError):
                    gate._read(source_root, relative)
            self.assertEqual(gate._read(root, 'real/leaf'), 'bounded')

    def test_success_and_failure_readers_close_every_opened_descriptor(self):
        opened, closed = [], []
        original_open, original_close = gate.os.open, gate.os.close
        def tracked_open(*args, **kwargs):
            descriptor = original_open(*args, **kwargs)
            opened.append(descriptor)
            return descriptor
        def tracked_close(descriptor):
            closed.append(descriptor)
            return original_close(descriptor)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'dir').mkdir()
            (root / 'dir' / 'leaf').write_text('bounded')
            (root / 'link').symlink_to(root / 'dir', target_is_directory=True)
            for relative, fails in (('dir/leaf', False), ('link/leaf', True), ('dir/missing', True)):
                opened.clear(); closed.clear()
                with mock.patch.object(gate.os, 'open', tracked_open), mock.patch.object(gate.os, 'close', tracked_close):
                    if fails:
                        with self.assertRaises(ValueError):
                            gate._read(root, relative)
                    else:
                        self.assertEqual(gate._read(root, relative), 'bounded')
                self.assertEqual(sorted(opened), sorted(closed))

    def test_contract_canonical_raw_cannot_accept_loose_EOF_or_only_typed_alias(self):
        for suffix in ('\n', ' ', '\t', '// additional source\n'):
            texts = dict(self.texts)
            texts[gate.CONTRACT] += suffix
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                gate.check(gate.EXPECTED, texts)
        texts = dict(self.texts)
        texts[gate.CONTRACT] = json.dumps(gate.EXPECTED)
        with self.assertRaises(ValueError):
            gate.check(gate.EXPECTED, texts)

    def test_EXPECTED_only_exact_single_line_literal_assignment_is_removable(self):
        current = self.texts[gate.TOOL]
        assignment = gate.expected_assignment(gate.EXPECTED)
        self.assertEqual(current.count(assignment), 1)
        for replacement in (assignment.rstrip('\n') + '; print("extra")\n',
                            assignment.rstrip('\n') + ' # extra\n',
                            assignment.replace('EXPECTED = ', 'OTHER = EXPECTED = ', 1),
                            assignment.replace('json.loads(', 'json.loads(\n', 1),
                            'EXPECTED = dict()\n', assignment.rstrip('\n')):
            with self.subTest(replacement=replacement), self.assertRaises((ValueError, SyntaxError)):
                gate.checker_body(current.replace(assignment, replacement, 1))
            texts = dict(self.texts)
            texts[gate.TOOL] = current.replace(assignment, replacement, 1)
            with self.subTest(full_gate=True), self.assertRaises((ValueError, SyntaxError)):
                gate.check(gate.EXPECTED, texts)
        for suffix in ('\n', '# additional EOF\n'):
            texts = dict(self.texts)
            texts[gate.TOOL] += suffix
            with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                gate.check(gate.EXPECTED, texts)


class CurrentPhysicalIngressBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texts = gate.inputs()

    def _fully_rebound(self, replacements):
        texts = dict(self.texts)
        texts.update(replacements)
        rebound = rebind_derived_metadata(gate.EXPECTED, texts, self.texts)
        # Synchronize every mutable physical classification/whole identity;
        # the independent current16 literal and all other CLOSED code stay fixed.
        for group in ('preserved_original_sha256', 'supplemental_source_sha256'):
            for path in rebound[group]:
                rebound[group][path] = gate._sha(texts[path].encode())
        for group in ('finite_parent_inverse', 'joint_parent_inverse12'):
            for path, rule in rebound[group].items():
                rule['complete_bytes'] = len(texts[path].encode())
                rule['complete_sha256'] = gate._sha(texts[path].encode())
        for path in rebound['joint_current_physical_ingress16']:
            rebound['joint_current_physical_ingress16'][path] = gate._sha(texts[path].encode())
        role = rebound['joint_transport_input_roles']
        raw = texts[role['path']].encode()
        role['current_physical']['bytes'] = len(raw)
        role['current_physical']['sha256'] = gate._sha(raw)
        role['existing_C_exact_inverse2']['complete_bytes'] = len(raw)
        role['existing_C_exact_inverse2']['complete_sha256'] = gate._sha(raw)
        assignment = gate.expected_assignment(gate.EXPECTED)
        self.assertEqual(texts[gate.TOOL].count(assignment), 1)
        texts[gate.TOOL] = texts[gate.TOOL].replace(assignment, gate.expected_assignment(rebound), 1)
        texts[gate.CONTRACT] = gate.canonical_contract_text(rebound)
        return rebound, texts

    def _assert_current_physical_refusal(self, replacements):
        rebound, texts = self._fully_rebound(replacements)
        with mock.patch.object(gate, 'EXPECTED', rebound):
            self.assertEqual(texts[gate.CONTRACT], gate.canonical_contract_text(gate.EXPECTED))
            self.assertEqual(gate._sha(gate.checker_body(texts[gate.TOOL]).encode()),
                             rebound['checker_nonEXPECTED_whole_sha256'])
            with self.assertRaisesRegex(ValueError, '^P3 independent current physical ingress differs$'):
                gate.check(rebound, texts)

    def test_current16_physical_and_exact_two_line_P1_history_are_distinct(self):
        from tools import verify_approved_service_product as product
        from tools import verify_approved_service_request as original
        roles = gate.EXPECTED['joint_transport_input_roles']
        path = roles['path']
        physical = self.texts[path]
        historical = product.parent_source(path, physical)
        self.assertNotEqual(physical, historical)
        self.assertEqual(len(physical.encode()), roles['current_physical']['bytes'])
        self.assertEqual(gate._sha(physical.encode()), roles['current_physical']['sha256'])
        self.assertEqual(len(historical.encode()), roles['historical_P1_input']['bytes'])
        self.assertEqual(gate._sha(historical.encode()), roles['historical_P1_input']['sha256'])
        self.assertEqual(physical.replace('mod connected_denial;\n', '', 1)
                         .replace('pub use connected_denial::OriginalConnectedDenial;\n', '', 1),
                         historical)
        actual = original.inputs()
        self.assertEqual(actual[path], historical)
        original.check(original.EXPECTED, actual)
        gate.check(gate.EXPECTED, self.texts)

    def test_history_missing_exports_and_changed_Rooted_guard_refuse_after_full_rebinding(self):
        from tools import verify_approved_service_product as product
        path = 'crates/hepta-agent-transport/src/accepted_handoff.rs'
        rootpath = 'crates/hepta-peer-attestation/src/control_owner/root_path/service_request.rs'
        current = self.texts[path]
        historical = product.parent_source(path, current)
        deleted = current.replace('mod connected_denial;\n', '', 1)
        deleted = deleted.replace('pub use connected_denial::OriginalConnectedDenial;\n', '', 1)
        self.assertEqual(deleted, historical)
        before = ('        let received = self.inner.receive_service_control(session)?;\n'
                  '        session.ensure_current().map_err(service_error)?;\n'
                  '        Ok(received)\n')
        self.assertEqual(self.texts[rootpath].count(before), 1)
        changed = self.texts[rootpath].replace(before,
                  '        let received = self.inner.receive_service_control(session)?;\n'
                  '        Ok(received)\n', 1)
        for label, replacements in (('whole historical988', {path: historical}),
                                    ('delete both current export lines', {path: deleted}),
                                    ('Rooted final session guard removed', {rootpath: changed})):
            with self.subTest(label=label):
                self._assert_current_physical_refusal(replacements)

    def test_all16_unknown_physical_bytes_refuse_after_all_mutable_metadata_rebinding(self):
        for path in gate.EXPECTED['joint_current_physical_ingress16']:
            with self.subTest(path=path):
                self._assert_current_physical_refusal({path: self.texts[path] + '\n// changed physical Source\n'})

    def test_current16_catalog_rebinding_cannot_replace_the_independent_combo(self):
        texts = dict(self.texts)
        rebound = copy.deepcopy(gate.EXPECTED)
        roles = rebound['joint_transport_input_roles']
        rebound['joint_current_physical_ingress16'][roles['path']] = roles['historical_P1_input']['sha256']
        assignment = gate.expected_assignment(gate.EXPECTED)
        texts[gate.TOOL] = texts[gate.TOOL].replace(assignment, gate.expected_assignment(rebound), 1)
        texts[gate.CONTRACT] = gate.canonical_contract_text(rebound)
        with mock.patch.object(gate, 'EXPECTED', rebound):
            self.assertEqual(texts[gate.CONTRACT], gate.canonical_contract_text(gate.EXPECTED))
            self.assertEqual(gate._sha(gate.checker_body(texts[gate.TOOL]).encode()),
                             rebound['checker_nonEXPECTED_whole_sha256'])
            with self.assertRaisesRegex(ValueError, '^P3 independent current physical ingress catalog differs$'):
                gate.check(rebound, texts)


class CurrentCIPhysicalBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.texts = gate.inputs()

    def _fully_rebound_ci(self, replacements):
        texts = dict(self.texts)
        texts.update(replacements)
        rebound = rebind_derived_metadata(gate.EXPECTED, texts, self.texts)
        for group in ('finite_parent_inverse', 'joint_parent_inverse12', 'ci_parent_inverse18'):
            for path, rule in rebound[group].items():
                rule['complete_bytes'] = len(texts[path].encode())
                rule['complete_sha256'] = gate._sha(texts[path].encode())
        for path in rebound['ci_current_physical23']:
            rebound['ci_current_physical23'][path] = gate._sha(texts[path].encode())
        for path in rebound['ci_parent_inverse18']:
            parent = gate.ci_parent_source(path, self.texts[path])
            rule = inverse(parent, texts[path], rebound['ci_parent_inverse18'][path])
            # inverse() uses character offsets. Rebuild this separate byte policy.
            old, current = parent.splitlines(True), texts[path].splitlines(True)
            oo, no = [0], [0]
            for line in old:
                oo.append(oo[-1] + len(line.encode()))
            for line in current:
                no.append(no[-1] + len(line.encode()))
            rule.pop('edits', None)
            rule['byte_edits'] = []
            for tag, a, b, x, y in difflib.SequenceMatcher(None, old, current, autojunk=False).get_opcodes():
                if tag != 'equal':
                    rule['byte_edits'].append({'complete_start': no[x], 'complete_end': no[y],
                                              'complete_text': ''.join(current[x:y]),
                                              'parent_text': ''.join(old[a:b])})
            rebound['ci_parent_inverse18'][path] = rule
        assignment = gate.expected_assignment(gate.EXPECTED)
        self.assertEqual(texts[gate.TOOL].count(assignment), 1)
        texts[gate.TOOL] = texts[gate.TOOL].replace(assignment, gate.expected_assignment(rebound), 1)
        texts[gate.CONTRACT] = gate.canonical_contract_text(rebound)
        return rebound, texts

    def _assert_ci_refusal(self, replacements):
        rebound, texts = self._fully_rebound_ci(replacements)
        with mock.patch.object(gate, 'EXPECTED', rebound):
            self.assertEqual(texts[gate.CONTRACT], gate.canonical_contract_text(gate.EXPECTED))
            self.assertEqual(gate._sha(gate.checker_body(texts[gate.TOOL]).encode()),
                             rebound['checker_nonEXPECTED_whole_sha256'])
            with self.assertRaisesRegex(ValueError, '^P3 independent current CI physical Source differs$'):
                gate.check(rebound, texts)

    def test_positive_actual699_and_current_CI_checker_are_not_historical_views(self):
        from tools import verify_ci_namespace_python as ci
        gate.check(gate.EXPECTED, self.texts)
        ci.validate(gate.ROOT)
        current = ci.inputs(gate.ROOT)
        self.assertEqual(len(self.texts), 699)
        self.assertEqual(len(gate.EXPECTED['ci_current_physical23']), 23)
        self.assertEqual(len(gate.CLOSED_CI_SOURCE_RULES), 18)
        for path in current:
            self.assertEqual(current[path], self.texts[path])
            self.assertEqual(current[path], gate._read(gate.ROOT, path))
        for path, rule in gate.CLOSED_CI_SOURCE_RULES.items():
            restored = gate.ci_parent_source(path, self.texts[path])
            self.assertNotEqual(restored, self.texts[path])
            self.assertEqual([len(restored.encode()), gate._sha(restored.encode())],
                             [rule['parent_bytes'], rule['parent_sha256']])
            self.assertEqual(gate.ci_parent_source(path, restored), restored)
        historical = dict(current)
        workflow = '.github/workflows/ci.yml'
        historical[workflow] = gate.ci_parent_source(workflow, current[workflow])
        with self.assertRaisesRegex(ValueError, '^reviewed complete CI setup source differs$'):
            ci.check(ci.EXPECTED, historical)

    def test_all23_changed_current_CI_objects_refuse_after_complete_rebinding(self):
        for path in gate.EXPECTED['ci_current_physical23']:
            with self.subTest(path=path):
                self._assert_ci_refusal({path: self.texts[path] + '\n# changed physical CI bytes\n'})

    def test_all18_de44_historical_CI_objects_refuse_as_current_after_complete_rebinding(self):
        for path in gate.CLOSED_CI_SOURCE_RULES:
            with self.subTest(path=path):
                self._assert_ci_refusal({path: gate.ci_parent_source(path, self.texts[path])})

    def test_CI_catalog_only_rebinding_cannot_replace_independent_current23(self):
        rebound = copy.deepcopy(gate.EXPECTED)
        path = '.github/workflows/ci.yml'
        rebound['ci_current_physical23'][path] = gate.CLOSED_CI_SOURCE_RULES[path]['parent_sha256']
        texts = dict(self.texts)
        assignment = gate.expected_assignment(gate.EXPECTED)
        texts[gate.TOOL] = texts[gate.TOOL].replace(assignment, gate.expected_assignment(rebound), 1)
        texts[gate.CONTRACT] = gate.canonical_contract_text(rebound)
        with mock.patch.object(gate, 'EXPECTED', rebound):
            self.assertEqual(gate._sha(gate.checker_body(texts[gate.TOOL]).encode()),
                             rebound['checker_nonEXPECTED_whole_sha256'])
            with self.assertRaisesRegex(ValueError, '^P3 independent current CI physical catalog differs$'):
                gate.check(rebound, texts)


class RetainedFullFiniteHistoryCompositionTests(unittest.TestCase):
    """Current physical success plus exact upstream inverse and rebound denial."""
    @classmethod
    def setUpClass(cls):
        cls.texts = gate.inputs()

    def _readiness_inputs(self):
        from tools import verify_retained_control_readiness as retained
        paths = set(retained.EXPECTED['actual_source_sha256']) | set(retained.EXPECTED['preserved_sha256'])
        return {path: self.texts[path] for path in paths}

    def _refuse_rebound_readiness(self, before, after):
        path = 'tools/verify_retained_control_readiness.py'
        self.assertEqual(self.texts[path].count(before), 1)
        changed = self.texts[path].replace(before, after, 1)
        harness = CurrentCIPhysicalBoundaryTests()
        harness.texts = self.texts
        # All derived catalogs, hashes, byte inverses, EXPECTED source and raw
        # contract are rebound. The separately fixed current23 remains original.
        rebound, texts = harness._fully_rebound_ci({path: changed})
        self.assertEqual(rebound['ci_current_physical23'][path], gate._sha(changed.encode()))
        self.assertEqual(rebound['preserved_original_sha256'][path], gate._sha(changed.encode()))
        self.assertEqual(rebound['ci_parent_inverse18'][path]['complete_sha256'], gate._sha(changed.encode()))
        self.assertEqual(texts[gate.CONTRACT], gate.canonical_contract_text(rebound))
        self.assertEqual(gate._sha(gate.checker_body(texts[gate.TOOL]).encode()),
                         rebound['checker_nonEXPECTED_whole_sha256'])
        with mock.patch.object(gate, 'EXPECTED', rebound):
            with self.assertRaisesRegex(ValueError, '^P3 independent current CI physical Source differs$'):
                gate.check(rebound, texts)

    def test_current_physical_readiness_inputs_reach_complete_success(self):
        from tools import verify_retained_control_readiness as retained
        current = self._readiness_inputs()
        retained.check(copy.deepcopy(retained.EXPECTED), current)
        historical = {path: retained.composition.source(gate.ROOT, path) for path in current}
        retained.check(copy.deepcopy(retained.EXPECTED), historical)

    def test_all_ten_physical_and_Native_views_restore_the_same_original_parent(self):
        from tools import verify_retained_control_readiness as retained
        from tools import verify_approved_service_runtime as runtime
        current = self._readiness_inputs()
        self.assertEqual(len(retained.TRANSFER), 10)
        for path in retained.TRANSFER:
            with self.subTest(path=path):
                normalized = runtime.parent_source(path, current[path])
                native = retained.composition.source(gate.ROOT, path)
                self.assertEqual(normalized, native)
                original = retained.parent_source(path, current[path])
                self.assertEqual(original, retained.parent_source(path, normalized))
                self.assertEqual(gate._sha(original.encode()), retained.EXPECTED['parent_source_sha256'][path])

    def test_unknown_connected_denial_registration_is_not_a_normalizable_current_object(self):
        from tools import verify_retained_control_readiness as retained
        before = 'mod connected_denial;'
        current = self._readiness_inputs()[retained.TRANSPORT]
        self.assertEqual(current.count(before), 1)
        changed = current.replace(before, '// literal decoy: "mod connected_denial;"', 1)
        with self.assertRaisesRegex(ValueError, '^P2C complete parent object differs$'):
            retained.parent_source(retained.TRANSPORT, changed)

    def test_unknown_P1_plumbing_is_not_a_normalizable_current_object(self):
        from tools import verify_retained_control_readiness as retained
        current = self._readiness_inputs()[retained.RETAINED]
        with self.assertRaisesRegex(ValueError, '^complete service bridge source differs$'):
            retained.parent_source(retained.RETAINED, current + '\n// unknown P1 plumbing\n')

    def test_parent_upstream_call_removal_refuses_after_complete_metadata_rebinding(self):
        self._refuse_rebound_readiness(
            '    text = detach_for_readiness(path, service_runtime_parent_source(path, text))\n',
            '    text = detach_for_readiness(path, text)\n')

    def test_parent_upstream_literal_decoy_refuses_after_complete_metadata_rebinding(self):
        self._refuse_rebound_readiness(
            '    text = detach_for_readiness(path, service_runtime_parent_source(path, text))\n',
            '    text = detach_for_readiness(path, text)  # service_runtime_parent_source(path, text)\n')

    def test_check_upstream_call_removal_refuses_after_complete_metadata_rebinding(self):
        self._refuse_rebound_readiness(
            '    texts = {path: detach_for_readiness(path, service_runtime_parent_source(path, text)) for path, text in texts.items()}\n',
            '    texts = {path: detach_for_readiness(path, text) for path, text in texts.items()}\n')

    def test_check_upstream_literal_decoy_refuses_after_complete_metadata_rebinding(self):
        self._refuse_rebound_readiness(
            '    texts = {path: detach_for_readiness(path, service_runtime_parent_source(path, text)) for path, text in texts.items()}\n',
            '    texts = {path: detach_for_readiness(path, text) for path, text in texts.items()}  # service_runtime_parent_source(path, text)\n')


if __name__ == '__main__':
    unittest.main()
