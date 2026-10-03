"""Finite source mutation tests, not actual root/kernel/Owner executions."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from tools import verify_approved_service_owner as gate

ROOT = Path(__file__).resolve().parents[1]


class ApprovedServiceOwnerFoundationTests(unittest.TestCase):
    def texts(self):
        return gate.inputs(ROOT)

    def change(self, path, before, after):
        values = self.texts()
        self.assertIn(before, values[path])
        values[path] = values[path].replace(before, after, 1)
        with self.assertRaises(ValueError):
            gate.check(copy.deepcopy(gate.EXPECTED), values)

    def test_actual_finite_source_and_payload_free_cli(self):
        gate.validate(ROOT)
        process = subprocess.run([sys.executable, 'tools/verify_approved_service_owner.py'],
                                 cwd=ROOT, capture_output=True, text=True, check=False)
        self.assertEqual(process.returncode, 0, process.stderr)
        result = json.loads(process.stdout)
        self.assertEqual(result['scope'], 'FOUNDATION_ONLY')
        for key in ['actual_kernel_execution', 'native_sixty_second_health',
                    'installed_activation', 'production_ready']:
            self.assertIs(result[key], False)

    def test_policy_does_not_accept_ownerless_legacy_or_observed_identity(self):
        for before, after in [('fields.len() != 19', 'fields.len() != 13'),
                              ('["control", "agent", "owner"]', '["control", "agent"]'),
                              ('fields["schema"] != SERVICE_SCHEMA', 'false'),
                              ('values[first].principal == values[second].principal', 'false')]:
            with self.subTest(before=before): self.change(gate.CORE, before, after)

    def test_uid_pin_line_bounds_and_duplicate_source_are_closed(self):
        for before in ['fields.insert(k, v).is_some()', 'n == u32::MAX',
                       '!bytes.is_ascii()', '!bytes.ends_with(b"\\n")',
                       'pin.len() != 64', 'bytes.len() > MAX_APPROVED_SERVICE_POLICY_BYTES']:
            with self.subTest(before=before): self.change(gate.CORE, before, 'false')

    def test_socket_cookie_peer_and_cloexec_cannot_be_removed(self):
        for before, after in [('flags & libc::FD_CLOEXEC == 0', 'false'),
                              ('cookie == 0', 'false'),
                              ('peer.pid != Some(pid)', 'false'),
                              ('peer != self.peer', 'false'),
                              ('libc::SO_COOKIE', 'libc::SO_TYPE')]:
            with self.subTest(before=before): self.change(gate.CREATOR, before, after)

    def test_numeric_collision_requires_actual_original_creator_resources(self):
        self.change(gate.CREATOR, 'endpoint.verify()?;', '')
        self.change(gate.CREATOR, 'namespace_identity(&current_pid_namespace()?)?',
                    'self.pid_namespace_identity')
        self.change(gate.CREATOR, 'libc::CLONE_NEWPID', 'libc::CLONE_NEWNS')
        self.change(gate.CREATOR, '/proc/thread-self/ns/pid', '/proc/self/ns/user')

    def test_normal_foreign_pid_guard_stays_first(self):
        self.change(gate.CREATOR,
                    'if self.pid != std::process::id() {',
                    'for endpoint in &self.endpoints { endpoint.verify()?; }\n'
                    '        if self.pid != std::process::id() {')
        self.change(gate.CORE, 'self.state.creator_current()?;', '// no creator check')

    def test_owner_uses_fixed_actual_default_proc_and_original_pidfd(self):
        self.change(gate.CORE, 'ProcfsPeerAttestor::default()', 'caller_attestor')
        self.change(gate.CORE, '.attest(peer, &entry.runtime())',
                    '.attest_with_static_executable_digest(peer, &entry.runtime(), caller_pin)')
        self.change(gate.CORE, '.request_custody()', '.snapshot()')
        self.change(gate.CORE, 'attested.snapshot().executable_sha256 != entry.pin', 'false')

    def test_selection_and_sticky_retirement_cannot_be_renewed(self):
        self.change(gate.CORE, '.compare_exchange(false, true,', '.compare_exchange(true, false,')
        self.change(gate.CORE, 'self.state.retired.store(true, Ordering::SeqCst);', '')
        self.change(gate.CORE, 'self.retired.store(true, Ordering::SeqCst)',
                    'self.retired.store(false, Ordering::SeqCst)')
        self.change(gate.CORE, 'pub struct ApprovedServiceOwnerBinding {',
                    '#[derive(Clone)]\npub struct ApprovedServiceOwnerBinding {')

    def test_root_source_readback_cannot_be_decoyed_or_replaced(self):
        self.change(gate.CORE, 'Identity::named(parent.fd.as_raw_fd(), &self.leaf)? != self.identity',
                    'false')
        self.change(gate.CORE, '<[u8; 32]>::from(Sha256::digest(&data)) != self.digest', 'false')
        self.change(gate.CORE, 'self.original\n                .verify_current()',
                    'self.original\n                .snapshot()')

    def test_old_v1_prefix_tail_and_detached_module_all_refuse(self):
        for path, rule in gate.EXPECTED['legacy_inverse'].items():
            value = self.texts()[path]
            old = value[:-len(rule['tail'])]
            self.assertEqual(gate.legacy_source(path, old), old)
            self.assertEqual(gate.legacy_source(path, value), old)
            for changed in [value + '\nmod unreviewed;\n', old.replace('pub ', 'pub(crate) ', 1),
                            old + rule['tail'].replace('pub use', '// pub use')]:
                with self.subTest(path=path), self.assertRaises(ValueError):
                    gate.legacy_source(path, changed)
            values = self.texts(); values[path] = old
            with self.assertRaises(ValueError): gate.check(gate.EXPECTED, values)

    def test_type_numeric_flags_and_hash_rebinding_do_not_grant_authority(self):
        for group, key, value in [('non_claims', 'production_ready', True),
                                  ('owner', 'caller_attestor_or_snapshot', 0),
                                  ('kernel_corpus', 'source_continuity_seconds_minimum', 20),
                                  ('creator', 'numeric_collision_FD_free', True)]:
            changed = copy.deepcopy(gate.EXPECTED); changed[group][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                gate.check(changed, self.texts())
        values = self.texts(); values[gate.CORE] += '\npub fn forged() {}\n'
        changed = copy.deepcopy(gate.EXPECTED)
        changed['whole_source_sha256'][gate.CORE] = gate.sha256(values[gate.CORE])
        with self.assertRaises(ValueError): gate.check(changed, values)

    def test_duplicate_json_and_bad_magic_literal_do_not_supply_source(self):
        with tempfile.TemporaryDirectory(prefix='approved-service-json-') as directory:
            path = Path(directory) / 'contract.json'
            text = json.dumps(gate.EXPECTED)
            path.write_text(text.replace('"status": "FOUNDATION_SOURCE_ONLY"',
                                         '"status": "FOUNDATION_SOURCE_ONLY", "status": "FOUNDATION_SOURCE_ONLY"'))
            with self.assertRaises(ValueError): gate.source_gate.load(path)
        values = self.texts(); old = values[gate.CORE]
        values[gate.CORE] = 'const DECOY: &str = r###"' + old + '"###;\npub fn forged() {}\n'
        with self.assertRaises(ValueError): gate.check(gate.EXPECTED, values)

    def test_actual_harness_cannot_disable_shorten_or_fake_root_evidence(self):
        path = gate.EXPECTED['kernel_corpus']['path']
        for before, after in [('Duration::from_secs(61)', 'Duration::from_secs(1)'),
                              ('ProcfsPeerAttestor', 'InjectedProcfsPeerAttestor'),
                              ('assert_eq!(status, 0,', 'let _ignored = status; assert_eq!(0, 0,'),
                              ('Err(ApprovedPolicyError::ProcessChanged)', 'Ok(())')]:
            if before == 'ProcfsPeerAttestor':
                # Attestation belongs to core; the harness deliberately has
                # no injected attestor. Pin and default implementation bind it.
                self.assertNotIn(before, self.texts()[path])
            else:
                with self.subTest(before=before): self.change(path, before, after)
        cargo = gate.EXPECTED['cargo_inverse']['path']
        self.change(cargo, 'name = "approved_service_owner_kernel"',
                    'test = false\nname = "approved_service_owner_kernel"')
        self.change('Makefile', '\tpython3 tools/verify_approved_service_owner.py\n', '')


if __name__ == '__main__':
    unittest.main()


class ApprovedServiceOwnerCompositionInverseTests(unittest.TestCase):
    """Source-only whole-profile regression; no root/kernel/health authority."""

    POLICY = 'crates/hepta-peer-attestation/src/approved_policy.rs'
    OLD_CHECKERS = ('tools/verify_approved_composition_scope.py',
                    'tools/verify_approved_constructor_route.py')

    def refuse(self, path, changed):
        values = gate.inputs(ROOT)
        values[path] = changed
        with self.assertRaises(ValueError):
            gate.check(copy.deepcopy(gate.EXPECTED), values)

    def test_complete_original_and_combined_profiles_pass(self):
        combined = gate.inputs(ROOT)
        gate.check(copy.deepcopy(gate.EXPECTED), combined)
        original = gate.receiver_profile_inputs(combined)
        self.assertNotEqual(original['Makefile'], combined['Makefile'])
        self.assertNotEqual(original[self.POLICY], combined[self.POLICY])
        for path in self.OLD_CHECKERS:
            self.assertNotEqual(original[path], combined[path])
        gate.check(copy.deepcopy(gate.EXPECTED), original)

    def test_original_and_combined_parts_cannot_be_mixed(self):
        combined = gate.inputs(ROOT)
        original = gate.receiver_profile_inputs(combined)
        for path in ('Makefile', self.POLICY, *self.OLD_CHECKERS):
            with self.subTest(path=path):
                self.refuse(path, original[path])
                mixed = dict(original)
                mixed[path] = combined[path]
                with self.assertRaises(ValueError):
                    gate.check(copy.deepcopy(gate.EXPECTED), mixed)

    def test_readiness_parent_and_both_old_guards_still_validate(self):
        from tools import verify_retained_control_readiness as readiness
        from tools import verify_approved_composition_scope as composition
        from tools import verify_approved_constructor_route as constructor
        paths = set(readiness.EXPECTED['actual_source_sha256']) | set(readiness.EXPECTED['preserved_sha256'])
        values = {path: readiness.composition.source(ROOT, path) for path in paths}
        readiness.check(copy.deepcopy(readiness.EXPECTED), values)
        for path in (self.POLICY, *self.OLD_CHECKERS):
            restored = gate.detach_for_readiness(path, values[path])
            self.assertEqual(gate.sha256(restored), readiness.EXPECTED['actual_source_sha256'][path])
            parent = readiness.parent_source(path, restored)
            self.assertEqual(gate.sha256(parent), readiness.EXPECTED['parent_source_sha256'][path])
        composition.validate(ROOT)
        constructor.validate(ROOT)

    def test_original_and_receiver_prefixes_have_only_the_exact_tail(self):
        from tools import verify_retained_control_readiness as readiness
        values = gate.inputs(ROOT)
        rule = gate.EXPECTED['legacy_inverse'][self.POLICY]
        receiver = values[self.POLICY][:-len(rule['tail'])]
        original = readiness.parent_source(self.POLICY, receiver)
        for prefix in (receiver, original):
            with self.subTest(bytes=len(prefix.encode())):
                self.assertEqual(gate.legacy_source(self.POLICY, prefix), prefix)
                self.assertEqual(gate.legacy_source(self.POLICY, prefix + rule['tail']), prefix)
                for value in (prefix + ' ', prefix + rule['tail'] * 2,
                              prefix[:-1] + rule['tail'],
                              prefix.replace('impl ApprovedGuard {', 'impl ApprovedGuard\t{', 1) + rule['tail']):
                    with self.assertRaises(ValueError):
                        gate.legacy_source(self.POLICY, value)

    def test_policy_insertion_truncation_and_rewrite_refuse(self):
        value = gate.inputs(ROOT)[self.POLICY]
        for changed in (value + '\n', '\n' + value, value[:-1],
                        value.replace('impl ApprovedGuard {', 'impl ApprovedGuard\t{', 1),
                        value.replace('mod service_policy;', 'mod service_policyX;', 1)):
            with self.subTest(bytes=len(changed.encode())):
                self.refuse(self.POLICY, changed)

    def test_duplicate_tail_and_literal_decoy_refuse(self):
        value = gate.inputs(ROOT)[self.POLICY]
        tail = gate.EXPECTED['legacy_inverse'][self.POLICY]['tail']
        for changed in (value + tail, value[:-len(tail)] + '/*' + tail + '*/',
                        value[:-len(tail)] + tail.replace('pub use', '// pub use', 1)):
            with self.subTest(bytes=len(changed.encode())):
                self.refuse(self.POLICY, changed)

    def test_every_required_make_checker_and_extra_lines_are_closed(self):
        value = gate.inputs(ROOT)['Makefile']
        lines = ('\tpython3 tools/verify_approved_service_owner.py\n',
                 '\tpython3 tools/verify_retained_control_readiness.py\n',
                 '\tpython3 tools/verify_mozjs_authenticated_input.py\n')
        for line in lines:
            self.assertEqual(value.count(line), 1)
            for changed in (value.replace(line, '', 1), value + line,
                            value.replace(line, '# ' + line, 1)):
                with self.subTest(line=line):
                    self.refuse('Makefile', changed)
        self.refuse('Makefile', value + '\n')

    def test_old_checker_hook_removal_duplication_and_rewrite_refuse(self):
        values = gate.inputs(ROOT)
        boundaries = gate.EXPECTED['composition_receiver']['source_boundaries']
        for path in self.OLD_CHECKERS:
            value = values[path]
            block = boundaries[path]['inverse'][0]['actual']
            wrapped = boundaries[path]['inverse'][1]['actual']
            for changed in (value.replace(block, '', 1),
                            value.replace(block, block * 2, 1),
                            value.replace(wrapped, boundaries[path]['inverse'][1]['baseline'], 1),
                            value.replace('inventories = {}', 'inventories = dict()', 1) if path == self.OLD_CHECKERS[0] else value + '\n'):
                with self.subTest(path=path):
                    self.refuse(path, changed)

    def test_detach_boundary_rejects_changes_before_original_readiness_rules(self):
        values = gate.inputs(ROOT)
        for path in (self.POLICY, *self.OLD_CHECKERS):
            for changed in (values[path] + '\n', values[path][:-1], '\n' + values[path]):
                with self.subTest(path=path), self.assertRaises(ValueError):
                    gate.detach_for_readiness(path, changed)

    def test_contract_hash_rebinding_and_unknown_receiver_cannot_supply_authority(self):
        values = gate.inputs(ROOT)
        changed = copy.deepcopy(gate.EXPECTED)
        values[self.POLICY] += '\n'
        changed['composition_receiver']['source_boundaries'][self.POLICY]['composed'] = {
            'bytes': len(values[self.POLICY].encode()), 'sha256': gate.sha256(values[self.POLICY])}
        with self.assertRaises(ValueError):
            gate.check(changed, values)
        changed = copy.deepcopy(gate.EXPECTED)
        changed['composition_receiver']['baseline_head'] = True
        with self.assertRaises(ValueError):
            gate.check(changed, gate.inputs(ROOT))

    def test_non_string_and_subclass_magic_is_not_executed(self):
        class Magic(str):
            def encode(self, *args, **kwargs):
                raise AssertionError('untrusted source conversion executed')
        values = gate.inputs(ROOT)
        for path in ('Makefile', self.POLICY, *self.OLD_CHECKERS):
            for value in (False, b'source', Magic(values[path])):
                with self.subTest(path=path, value_type=type(value).__name__):
                    self.refuse(path, value)
        with self.assertRaises(ValueError):
            gate.legacy_source(self.POLICY, Magic(values[self.POLICY]))

    def test_unlisted_source_changes_still_reach_original_cargo_guard(self):
        values = gate.inputs(ROOT)
        path = gate.EXPECTED['cargo_inverse']['path']
        self.refuse(path, values[path].replace('harness = false', 'test = false\nharness = false', 1))
        self.assertEqual(set(gate.EXPECTED['composition_receiver']['source_boundaries']),
                         {self.POLICY, *self.OLD_CHECKERS})
