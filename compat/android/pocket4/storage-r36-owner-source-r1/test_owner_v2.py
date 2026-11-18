"""Offline regression tests. Synthetic references are shape fixtures, not evidence."""
import ast
import copy
import datetime
import hashlib
import io
import json
import pathlib
import sys
import tarfile
import types
import unittest

import owner_acquisition_v2 as owner_v2
import prepare_candidate

HERE = pathlib.Path(__file__).resolve().parent
BASELINE = HERE / 'baseline-r8'
CANDIDATE = HERE / 'candidate-r36-v2-r1' / 'source'


def read_contract(directory):
    return json.loads((directory / 'contract.json').read_bytes())


def need(ok, detail):
    if not ok:
        raise RuntimeError(detail)


def rotation_module(directory):
    manifest = json.loads((directory / 'SOURCE-MANIFEST.json').read_bytes())
    scope = {'C': directory, 'manifest': manifest, 'need': need, 'hashlib': hashlib, 'sys': sys}
    exec(compile((directory / 'rotation_support.py').read_bytes(), str(directory / 'rotation_support.py'), 'exec'), scope)
    return scope


def synthetic_complete_references(contract):
    """Keep the actual CURRENT reference; add a synthetic ROOT only for pure tests."""
    fixture = copy.deepcopy(contract)
    fixture['owner_acquisition']['root_acceptance'] = {
        'path': '/SYNTHETIC-TEST-ONLY/r36-owner-CAS-ROOT.json', 'bytes': 100, 'sha256': 'e' * 64,
        'identity': [66306, 900000, 0o100600, 1000, 1000, 1, 100,
                     1794970664608353433, 1794970664608353434]}
    return fixture


class OwnerRecordV2(unittest.TestCase):
    def setUp(self):
        self.contract = read_contract(CANDIDATE)
        self.old = read_contract(BASELINE)
        self.owner = self.contract['owner_acquisition']['owner']
        self.record = self.contract['owner_acquisition']['record']

    def test_actual_observed_record_consistent_without_permission(self):
        result = owner_v2.validate_owner_record_v2(self.owner, self.record)
        self.assertTrue(result['owner_record_consistent'])
        self.assertTrue(all(value is False for key, value in result.items() if key != 'owner_record_consistent'))
        self.assertEqual(tuple(self.contract['owner_acquisition']['current']['identity']),
                         owner_v2.CURRENT_OBSERVED_IDENTITY)
        self.assertIsNone(self.contract['owner_acquisition']['root_acceptance'])

    def test_v1_and_mixed_acquisitions_rejected(self):
        old = self.old['owner_acquisition']
        for owner, record in ((old['owner'], old['record']), (self.owner, old['record']), (old['owner'], self.record)):
            with self.subTest(owner=owner['generation'], record=record['schema']):
                with self.assertRaises(RuntimeError):
                    owner_v2.validate_owner_record_v2(owner, record)

    def test_exact_nested_v1_and_r35_owner_preserved(self):
        self.assertEqual(self.record['superseded_acquisition_record'], self.old['owner_acquisition']['record'])
        self.assertEqual(self.record['superseded_owner'],
                         dict(self.old['owner_acquisition']['owner'], generation='20261117-e6ac-r35'))
        changed = copy.deepcopy(self.record)
        changed['superseded_acquisition_record']['existing_actor_deadlines_extended'] = True
        with self.assertRaises(RuntimeError):
            owner_v2.validate_owner_record_v2(self.owner, changed)

    def test_changed_or_extended_owner_window_rejected(self):
        changes = {
            'schema': 'p4-independent-foreground-owner-acquisition-v1',
            'generation': '20261118-e6ac-r37', 'acquisition_id': 'different-acquisition',
            'owner_name': 'different-owner', 'active_until_utc': '2026-11-21T01:53:12.988458+00:00',
            'window_started_at_utc': '2026-11-19T01:53:12.988458+00:00',
            'window_seconds': 172801,
        }
        for key, value in changes.items():
            with self.subTest(key=key):
                changed = copy.deepcopy(self.record)
                changed[key] = value
                with self.assertRaises(RuntimeError):
                    owner_v2.validate_owner_record_v2(self.owner, changed)

    def test_budgets_require_exact_native_integer_values(self):
        keys = ('window_seconds', 'maximum_native_budget_seconds', 'native_stop_timeout_seconds',
                'maximum_native_hard_envelope_seconds', 'preparation_reserve_seconds',
                'required_remaining_at_commit_seconds', 'whole_planned_schedule_seconds')
        for key in keys:
            for value in (self.record[key] - 1, float(self.record[key]), True):
                with self.subTest(key=key, value=value):
                    changed = copy.deepcopy(self.record)
                    changed[key] = value
                    with self.assertRaises(RuntimeError):
                        owner_v2.validate_owner_record_v2(self.owner, changed)

    def test_authorization_flags_and_future_bindings_cannot_gain_credit(self):
        keys = ('existing_actor_deadlines_extended', 'existing_storage_deadlines_extended',
                'new_storage_admission_issued', 'fresh_full_B_admitted', 'C_D_admitted', 'production_ready',
                'new_storage_START', 'Android_starts', 'future_storage_source_manifest_sha256',
                'future_full_B_source_manifest_sha256', 'future_storage_binding', 'future_full_B_binding')
        for key in keys:
            with self.subTest(key=key):
                changed = copy.deepcopy(self.record)
                changed[key] = True
                with self.assertRaises(RuntimeError):
                    owner_v2.validate_owner_record_v2(self.owner, changed)

    def test_acquisition_and_retirement_native_integer_precision_retained(self):
        value = self.record['accepted_r8_retirement_ROOT']['identity']
        self.assertEqual(value[7], 1794966414200656927)
        self.assertGreater(value[7], 2**53)
        changed = copy.deepcopy(self.record)
        changed['accepted_r8_retirement_ROOT']['identity'][7] = int(float(value[7]))
        with self.assertRaises(RuntimeError):
            owner_v2.validate_owner_record_v2(self.owner, changed)


class ClosedRuntimeGates(unittest.TestCase):
    def setUp(self):
        self.contract = read_contract(CANDIDATE)

    def test_missing_owner_cas_root_blocks_rotation_and_binding(self):
        scope = rotation_module(CANDIDATE)
        with self.assertRaisesRegex(RuntimeError, 'R36 owner/CAS ROOT acceptance: actual complete reference required'):
            scope['rotation_schedule'](self.contract)
        with self.assertRaisesRegex(RuntimeError, 'R36 owner/CAS ROOT acceptance: actual complete reference required'):
            scope['storage_binding'](self.contract, 'a' * 64, 'b' * 64)

    def test_builder_requires_actual_no_follow_and_bookend_observation(self):
        observation = dict(self.contract['owner_acquisition']['current'],
                           opened_no_follow=True, fd_and_path_bookends_equal=True)
        self.assertEqual(prepare_candidate.verified_current_reference(observation),
                         self.contract['owner_acquisition']['current'])
        for key in ('opened_no_follow', 'fd_and_path_bookends_equal'):
            for value in (False, None, 1):
                with self.subTest(key=key, value=value):
                    bad = dict(observation, **{key: value})
                    with self.assertRaises(RuntimeError):
                        prepare_candidate.verified_current_reference(bad)

    def test_candidate_status_has_only_root_pin_unresolved(self):
        status = json.loads((CANDIDATE.parent / 'CANDIDATE-STATUS.json').read_bytes())
        self.assertEqual(status['unresolved_required_slots'], ['owner_acquisition.root_acceptance'])
        self.assertTrue(status['acquisition_current_reference_actual_read_verified'])
        self.assertFalse(status['owner_cas_root_reference_verified'])
        self.assertFalse(status['candidate_can_seal_or_admit'])

    def test_each_missing_slot_still_blocks_after_other_shape_is_filled(self):
        for key in ('current', 'root_acceptance'):
            with self.subTest(key=key):
                fixture = synthetic_complete_references(self.contract)
                fixture['owner_acquisition'][key] = None
                with self.assertRaisesRegex(RuntimeError, 'actual complete reference required'):
                    owner_v2.validate_storage_owner_v2(fixture)

    def test_origin_version_cannot_replace_full_current_reference(self):
        fixture = synthetic_complete_references(self.contract)
        fixture['owner_acquisition']['current'] = {'path': owner_v2.CURRENT_PATH,
            'bytes': owner_v2.CURRENT_BYTES, 'sha256': owner_v2.CURRENT_SHA256,
            'version': ':'.join(map(str, owner_v2.CURRENT_OBSERVED_VERSION))}
        with self.assertRaisesRegex(RuntimeError, 'actual complete reference required'):
            owner_v2.validate_storage_owner_v2(fixture)

    def test_synthetic_full_shapes_still_grant_no_runtime_permission(self):
        result = owner_v2.validate_storage_owner_v2(synthetic_complete_references(self.contract))
        self.assertTrue(result['source_check_only'])
        for key in ('new_storage_admitted', 'fresh_full_B_admitted', 'production_ready'):
            self.assertFalse(result[key])

    def test_wrong_current_identity_owner_mode_hash_and_version_rejected(self):
        for field, value in ((0, 1), (1, 1), (2, 0o100644), (3, 0), (4, 0), (5, 2),
                             (6, owner_v2.CURRENT_BYTES - 1), (7, 1794970664573351722),
                             (8, 1794970664608353433), (7, float(1794970664573351721))):
            with self.subTest(field=field, value=value):
                fixture = synthetic_complete_references(self.contract)
                fixture['owner_acquisition']['current']['identity'][field] = value
                with self.assertRaises(RuntimeError):
                    owner_v2.validate_storage_owner_v2(fixture)
        fixture = synthetic_complete_references(self.contract)
        fixture['owner_acquisition']['current']['sha256'] = 'a' * 64
        with self.assertRaises(RuntimeError):
            owner_v2.validate_storage_owner_v2(fixture)

    def test_retirement_or_stale_root_cannot_be_owner_cas_acceptance(self):
        for upgrade_metadata in (False, True):
            fixture = synthetic_complete_references(self.contract)
            ref = copy.deepcopy(fixture['owner_acquisition']['record']['accepted_r8_retirement_ROOT'])
            if upgrade_metadata:
                ref['identity'][2:5] = [0o100600, 1000, 1000]
            fixture['owner_acquisition']['root_acceptance'] = ref
            with self.assertRaises(RuntimeError):
                owner_v2.validate_storage_owner_v2(fixture)
        fixture = synthetic_complete_references(self.contract)
        fixture['owner_acquisition']['root_acceptance']['path'] = owner_v2.FROZEN_R34_ROOT
        with self.assertRaises(RuntimeError):
            owner_v2.validate_storage_owner_v2(fixture)
        fixture = synthetic_complete_references(self.contract)
        fixture['owner_acquisition']['root_acceptance']['sha256'] = owner_v2.FROZEN_R34_ROOT_SHA256
        with self.assertRaises(RuntimeError):
            owner_v2.validate_storage_owner_v2(fixture)

    def test_r8_nonce_and_wrong_generation_rejected(self):
        for key, value in (('nonce', owner_v2.FROZEN_R8_NONCE), ('generation', 'e6ac-storage-r8')):
            fixture = synthetic_complete_references(self.contract)
            fixture[key] = value
            with self.assertRaises(RuntimeError):
                owner_v2.validate_storage_owner_v2(fixture)

    def test_prepare_executes_the_same_gate_before_first_target_write(self):
        tree = ast.parse((CANDIDATE / 'prepare.py').read_bytes())
        nodes = []
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'owner_validator' for t in node.targets):
                nodes.append(node)
            elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
                call = node.value
                if isinstance(call.func, ast.Name) and call.func.id == 'exec':
                    nodes.append(node)
                elif isinstance(call.func, ast.Subscript) and isinstance(call.func.value, ast.Name) and call.func.value.id == 'owner_validator':
                    nodes.append(node)
        self.assertEqual(len(nodes), 3)
        first_target_write = next(node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == 'mkdir' and
            isinstance(node.func.value, ast.Name) and node.func.value.id == 'target')
        self.assertLess(nodes[-1].lineno, first_target_write.lineno)
        scope = {'entries': {'owner_acquisition_v2.py': (CANDIDATE / 'owner_acquisition_v2.py').read_bytes()},
                 'contract': self.contract}
        with self.assertRaisesRegex(RuntimeError, 'actual complete reference required'):
            exec(compile(ast.Module(body=nodes, type_ignores=[]), 'isolated_actual_prepare_gate', 'exec'), scope)


class FrozenSourceAndIntegration(unittest.TestCase):
    def test_original_r8_source_manifest_remains_exact(self):
        self.assertEqual(hashlib.sha256((BASELINE / 'SOURCE-MANIFEST.json').read_bytes()).hexdigest(),
                         '91772330fc4f500a6ed0961bf3b0ab5efcab3381a35de647c4470f0919f8fa11')
        self.check_manifest(BASELINE)

    def check_manifest(self, directory):
        manifest = json.loads((directory / 'SOURCE-MANIFEST.json').read_bytes())
        for name, ref in manifest['files'].items():
            with self.subTest(name=name):
                raw = (directory / name).read_bytes()
                self.assertEqual(len(raw), ref['bytes'])
                self.assertEqual(hashlib.sha256(raw).hexdigest(), ref['sha256'])
        return manifest

    def test_candidate_manifest_and_original_caps_preserved(self):
        manifest = self.check_manifest(CANDIDATE)
        self.assertEqual(len(manifest['files']), 30)
        self.assertEqual((CANDIDATE / 'owner_acquisition_v2.py').read_bytes(),
                         (HERE / 'owner_acquisition_v2.py').read_bytes())
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode='w:xz') as archive:
            for name in sorted(set(manifest['files']) | {'SOURCE-MANIFEST.json'}):
                raw = (CANDIDATE / name).read_bytes()
                self.assertLess(len(raw), 65536)
                member = tarfile.TarInfo(name)
                member.size = len(raw)
                archive.addfile(member, io.BytesIO(raw))
        self.assertLessEqual(len(buffer.getvalue()), 262143)

    def test_only_intended_source_files_changed(self):
        changed = {name for name in json.loads((BASELINE / 'SOURCE-MANIFEST.json').read_bytes())['files']
                   if (BASELINE / name).read_bytes() != (CANDIDATE / name).read_bytes()}
        self.assertEqual(changed, {'contract.json', 'rotation_support.py', 'prepare.py'})

    def test_historical_evidence_resource_gates_and_schedule_unchanged(self):
        old, candidate = read_contract(BASELINE), read_contract(CANDIDATE)
        for key in ('transition_originals', 'history_only_previous_transition', 'immediate_predecessor',
                    'offline_ancestor', 'offline_image', 'external_recovery_units',
                    'allocation_lock_path', 'allocation_source_manifest_sha256', 'image_path',
                    'rotation_schedule', 'storage_work_seconds', 'storage_runtime_max_seconds',
                    'storage_stop_seconds', 'p4_fresh_disk_minimum', 'p4_live_disk_reserve',
                    'p4_fresh_memory_minimum', 'p4_live_memory_reserve', 'desktop_fresh_memory_minimum',
                    'desktop_live_memory_reserve', 'desktop_local_disk_minimum', 'volume_prebuild_free_minimum',
                    'initial_ready_fresh_seconds', 'minimum_current_lease_seconds'):
            with self.subTest(key=key):
                self.assertEqual(old[key], candidate[key])
        self.assertEqual(sum(candidate['rotation_schedule'].values()), 140700)

    def test_active_paths_and_units_are_distinct_from_frozen_r8(self):
        old, candidate = read_contract(BASELINE), read_contract(CANDIDATE)
        for key in ('p4_source', 'desktop_source', 'p4_root', 'desktop_root', 'mount_target',
                    'full_source_dir', 'import_source_dir', 'incoming_admission_path', 'export_name'):
            with self.subTest(key=key):
                self.assertNotEqual(old[key], candidate[key])
                self.assertIn('r8-r36-v2-r1', candidate[key])
        for role in ('server', 'controller', 'client', 'ssh', 'finalize'):
            self.assertNotEqual(old[role + '_unit'], candidate[role + '_unit'])
            self.assertIn(candidate['nonce'], candidate[role + '_description'])
        for key in ('incoming_rotation_paths', 'rotation_inputs_paths', 'role_units'):
            self.assertTrue(all('r8-r36-v2-r1' in value for value in candidate[key].values()))

    def test_frozen_r8_pure_schedule_still_valid_but_actual_live_r36_owner_rejected(self):
        old, candidate = read_contract(BASELINE), read_contract(CANDIDATE)
        self.assertEqual(rotation_module(BASELINE)['rotation_schedule'](old)['total_seconds'], 140700)
        tree = ast.parse((BASELINE / 'admit.py').read_bytes())
        call = next(node for node in ast.walk(tree) if isinstance(node, ast.Call) and
                    isinstance(node.func, ast.Name) and node.func.id == 'need' and len(node.args) == 2 and
                    isinstance(node.args[1], ast.Constant) and node.args[1].value == 'actual unexpired foreground owner and generation')
        class FixedDateTime(datetime.datetime):
            @classmethod
            def now(cls, tz=None):
                return cls.fromisoformat('2026-11-18T08:00:00+00:00')
        owner = candidate['owner_acquisition']['owner']
        current = {'continuation_current': {'generation': owner['generation']},
                   'foreground_owner_acquisition_current': candidate['owner_acquisition']['record']}
        scope = {'need': need, 'encoded': owner_v2.encoded, 'owner': owner,
                 'current': current, 'contract': old, 'generation': owner['generation'],
                 'datetime': types.SimpleNamespace(datetime=FixedDateTime, timezone=datetime.timezone)}
        with self.assertRaisesRegex(RuntimeError, 'actual unexpired foreground owner and generation'):
            eval(compile(ast.Expression(body=call), 'actual_frozen_admit_owner_guard', 'eval'), scope)


if __name__ == '__main__':
    unittest.main(verbosity=2)
