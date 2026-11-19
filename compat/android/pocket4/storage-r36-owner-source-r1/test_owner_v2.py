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
CANDIDATE = HERE / 'candidate-r36-v2-r2' / 'source'


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
        with self.assertRaisesRegex(RuntimeError, 'original-lock custody and source review'):
            scope['rotation_schedule'](self.contract)
        with self.assertRaisesRegex(RuntimeError, 'original-lock custody and source review'):
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
        self.assertTrue(status['owner_cas_publication']['owner_cas_publication_verified'])
        self.assertFalse(status['owner_cas_publication']['owner_acquisition_acceptance_verified'])
        self.assertEqual(status['unresolved_acceptance_semantics'], ['original_lock_custody', 'source_review'])
        self.assertFalse(status['original_operation_bodies_in_source'])
        self.assertFalse(status['candidate_can_seal_or_admit'])

    def test_each_missing_slot_still_blocks_after_other_shape_is_filled(self):
        for key in ('current', 'root_acceptance'):
            with self.subTest(key=key):
                fixture = synthetic_complete_references(self.contract)
                fixture['owner_acquisition'][key] = None
                with self.assertRaises(RuntimeError):
                    owner_v2.validate_storage_owner_v2(fixture)

    def test_origin_version_cannot_replace_full_current_reference(self):
        fixture = synthetic_complete_references(self.contract)
        fixture['owner_acquisition']['current'] = {'path': owner_v2.CURRENT_PATH,
            'bytes': owner_v2.CURRENT_BYTES, 'sha256': owner_v2.CURRENT_SHA256,
            'version': ':'.join(map(str, owner_v2.CURRENT_OBSERVED_VERSION))}
        with self.assertRaisesRegex(RuntimeError, 'actual complete reference required'):
            owner_v2.validate_owner_declaration_v2(fixture)

    def test_synthetic_full_shapes_still_grant_no_runtime_permission(self):
        fixture = synthetic_complete_references(self.contract)
        with self.assertRaisesRegex(RuntimeError, 'unreviewed root_acceptance'):
            owner_v2.validate_storage_owner_v2(fixture)
        result = owner_v2.validate_owner_declaration_v2(fixture)
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
                    owner_v2.validate_owner_declaration_v2(fixture)
        fixture = synthetic_complete_references(self.contract)
        fixture['owner_acquisition']['current']['sha256'] = 'a' * 64
        with self.assertRaises(RuntimeError):
            owner_v2.validate_owner_declaration_v2(fixture)

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
        for key, value in (('nonce', owner_v2.FROZEN_R8_NONCE),
                           ('nonce', owner_v2.FROZEN_R36_R1_NONCE), ('generation', 'e6ac-storage-r8')):
            fixture = synthetic_complete_references(self.contract)
            fixture[key] = value
            with self.assertRaises(RuntimeError):
                owner_v2.validate_owner_declaration_v2(fixture)

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
        with self.assertRaisesRegex(RuntimeError, 'original-lock custody and source review'):
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
        self.assertEqual(changed, {'contract.json', 'rotation_support.py', 'prepare.py', 'admit.py'})

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
                self.assertIn('r8-r36-v2-r2', candidate[key])
        for role in ('server', 'controller', 'client', 'ssh', 'finalize'):
            self.assertNotEqual(old[role + '_unit'], candidate[role + '_unit'])
            self.assertIn(candidate['nonce'], candidate[role + '_description'])
        for key in ('incoming_rotation_paths', 'rotation_inputs_paths', 'role_units'):
            self.assertTrue(all('r8-r36-v2-r2' in value for value in candidate[key].values()))

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


def synthetic_publication():
    """Invented files/IDs/times for parser behavior, never the private CAS bodies."""
    tick = 2**53 + 1001
    root = '/SYNTHETIC-TEST-ONLY/cas'
    def ref(path, raw, inode, stamp, mode=0o100600, uid=1000, device=7):
        return {'path':path, 'bytes':len(raw), 'sha256':hashlib.sha256(raw).hexdigest(),
                'identity':[device, inode, mode, uid, uid, 1, len(raw), stamp, stamp]}
    old = ref('/SYNTHETIC-TEST-ONLY/CURRENT.json', b'synthetic-before\n', 40, tick-100)
    current = ref(old['path'], b'synthetic-after\n', 23, tick+20)
    current['identity'][8] = tick+40
    draft = ref('/SYNTHETIC-TEST-ONLY/prepared/draft.json', b'synthetic-after\n', 1, tick-20, device=9)
    diff = ref('/SYNTHETIC-TEST-ONLY/prepared/diff.json', b'synthetic-diff\n', 2, tick-15,
               mode=0o100400, uid=0, device=9)
    basename = '.CURRENT.r36-owner-' + 'd'*64 + '.tmp'
    temporary = ref(root+'/'+basename, b'synthetic-after\n', 23, tick+20)
    source_sha = hashlib.sha256(b'synthetic-source').hexdigest()
    plan_sha = hashlib.sha256(b'synthetic-plan').hexdigest()
    bodies = {
        'INTENT.json': {'schema':'p4-current-r36-owner-CAS-intent-v1',
            'acquisition_id':'synthetic-test-owner', 'automatic_rollback':False,
            'before':old, 'draft':draft, 'minimal_diff':diff, 'plan_sha256':plan_sha,
            'source_sha256':source_sha, 'temporary_basename':basename,
            'unknown_effect_requires_reconciliation':True},
        'REPLACE-BOUNDARY.json': {'attempted':True,
            'canonical_directory_identity':[7,21,0o40750,0,0,12,4096,tick-100,tick-100],
            'draft_sha256':current['sha256'], 'protected_temporary':temporary,
            'rename_uses_held_directory_FDs':True,
            'temporary_directory_identity':[7,20,0o40700,0,0,2,4096,tick,tick]},
        'RESULT.json': {'automatic_rollback':False, 'current':copy.deepcopy(current),
                        'passed':True, 'protected_held_inode_published':True}}
    reference = {'schema':'p4-current-r36-owner-CAS-publication-v1',
        'directory':{'path':root, 'identity':[7,20,0o40700,0,0,2,4096,tick+50,tick+50]},
        'records':{}}
    for name,inode,stamp in zip(owner_v2.CAS_NAMES,(22,24,25),(tick+10,tick+30,tick+50)):
        reference['records'][name] = ref(root+'/'+name,b'synthetic-placeholder',inode,stamp,mode=0o100400,uid=0)
    fixture = {'reference':reference, 'bodies':bodies, 'old':copy.deepcopy(old),
        'current':current, 'acquisition_id':'synthetic-test-owner',
        'source_sha':source_sha, 'plan_sha':plan_sha}
    reseal_synthetic(fixture)
    return fixture


def reseal_synthetic(fixture):
    fixture['raw'] = {}
    for name,body in fixture['bodies'].items():
        raw = (json.dumps(body,sort_keys=True,indent=2)+'\n').encode()
        fixture['raw'][name] = raw
        ref = fixture['reference']['records'][name]
        ref.update(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
        ref['identity'][6] = len(raw)


class PublicationSemantics(unittest.TestCase):
    def check(self, fixture):
        bodies = owner_v2.publication_payloads(fixture['reference'],fixture['raw'])
        return owner_v2.publication_chain(fixture['reference'],bodies,fixture['acquisition_id'],
            fixture['old'],fixture['current'],fixture['source_sha'],fixture['plan_sha'])

    def test_synthetic_publication_separates_every_missing_acceptance_fact(self):
        fixture = synthetic_publication()
        result = self.check(fixture)
        self.assertTrue(result['owner_cas_publication_verified'])
        self.assertTrue(result['source_check_only'])
        self.assertTrue(all(value is False for key,value in result.items()
                            if key not in ('owner_cas_publication_verified','source_check_only')))
        with self.assertRaises(RuntimeError):
            owner_v2.validate_owner_cas_publication_reference(fixture['reference'])

    def test_raw_bytes_are_checked_without_json_normalization(self):
        for name in owner_v2.CAS_NAMES:
            fixture = synthetic_publication()
            original = fixture['raw'][name]
            variants = [original[:-1], original+b'\n', original.replace(b'  ',b'\t ',1),
                        owner_v2.encoded(fixture['bodies'][name])]
            for variant in variants:
                with self.subTest(name=name,variant_bytes=len(variant)):
                    fixture['raw'][name] = variant
                    with self.assertRaisesRegex(RuntimeError,'raw event bytes'):
                        owner_v2.publication_payloads(fixture['reference'],fixture['raw'])

    def test_event_names_custody_and_native_f9_are_exact(self):
        mutations = [lambda r:r['records'].pop('INTENT.json'),
                     lambda r:r['records'].update({'EXTRA.json':r['records']['INTENT.json']}),
                     lambda r:r['records']['INTENT.json'].update(path='/SYNTHETIC-TEST-ONLY/copy.json')]
        for index,value in [(2,0o100600),(3,1000),(4,1000),(5,2),(7,float(2**53+1011))]:
            mutations.append(lambda r,index=index,value=value:r['records']['INTENT.json']['identity'].__setitem__(index,value))
        mutations += [lambda r:r['records']['RESULT.json']['identity'].__setitem__(1,22),
                      lambda r:r['directory']['identity'].__setitem__(2,0o40755)]
        for number,mutate in enumerate(mutations):
            fixture = synthetic_publication();mutate(fixture['reference'])
            with self.subTest(number=number),self.assertRaises(RuntimeError):
                self.check(fixture)

    def test_acquisition_predecessor_source_and_plan_do_not_drift(self):
        mutations = [lambda b:b.update(acquisition_id='other-owner'),
                     lambda b:b.update(source_sha256='0'*64),lambda b:b.update(plan_sha256='0'*64),
                     lambda b:b.update(automatic_rollback=True),
                     lambda b:b.update(unknown_effect_requires_reconciliation=False),
                     lambda b:b.update(schema='p4-current-r34-owner-CAS-intent-v1'),
                     lambda b:b['before'].update(sha256='0'*64),
                     lambda b:b['before'].update(path='/SYNTHETIC-TEST-ONLY/another-CURRENT.json')]
        for number,mutate in enumerate(mutations):
            fixture=synthetic_publication();mutate(fixture['bodies']['INTENT.json']);reseal_synthetic(fixture)
            with self.subTest(number=number),self.assertRaises(RuntimeError):self.check(fixture)

    def test_held_directory_and_exact_published_inode_are_required(self):
        mutations = [lambda b:b.update(attempted=False),lambda b:b.update(attempted=1),
                     lambda b:b.update(rename_uses_held_directory_FDs=False),
                     lambda b:b.update(draft_sha256='0'*64),
                     lambda b:b['protected_temporary']['identity'].__setitem__(1,777),
                     lambda b:b['protected_temporary']['identity'].__setitem__(5,2),
                     lambda b:b['protected_temporary'].update(path='/SYNTHETIC-TEST-ONLY/other.tmp')]
        for number,mutate in enumerate(mutations):
            fixture=synthetic_publication();mutate(fixture['bodies']['REPLACE-BOUNDARY.json']);reseal_synthetic(fixture)
            with self.subTest(number=number),self.assertRaises(RuntimeError):self.check(fixture)
        for field,value in [('passed',False),('passed',1),('protected_held_inode_published',False),('automatic_rollback',True)]:
            fixture=synthetic_publication();fixture['bodies']['RESULT.json'][field]=value;reseal_synthetic(fixture)
            with self.subTest(field=field,value=value),self.assertRaises(RuntimeError):self.check(fixture)
        fixture=synthetic_publication();fixture['bodies']['RESULT.json']['current']['identity'][8]+=1;reseal_synthetic(fixture)
        with self.assertRaisesRegex(RuntimeError,'independently read CURRENT'):self.check(fixture)

    def test_event_order_cannot_reverse_or_rename_a_directory(self):
        fixture=synthetic_publication()
        fixture['reference']['records']['INTENT.json']['identity'][7:9]=[2**53+9999]*2
        with self.assertRaisesRegex(RuntimeError,'chronology'):self.check(fixture)
        fixture=synthetic_publication()
        fixture['bodies']['REPLACE-BOUNDARY.json']['temporary_directory_identity'][1]=999
        reseal_synthetic(fixture)
        with self.assertRaisesRegex(RuntimeError,'protected original directory'):self.check(fixture)
        fixture=synthetic_publication()
        fixture['bodies']['REPLACE-BOUNDARY.json']['canonical_directory_identity'][1]=20
        reseal_synthetic(fixture)
        with self.assertRaisesRegex(RuntimeError,'distinct canonical directory'):self.check(fixture)

    def test_unknown_fields_duplicate_keys_and_nonfinite_json_are_rejected(self):
        fixture=synthetic_publication();fixture['bodies']['RESULT.json']['source_review_verified']=True
        reseal_synthetic(fixture)
        with self.assertRaises(RuntimeError):self.check(fixture)
        for lead,error in [(b'{"schema":"duplicate",','duplicate event JSON key'),
                           (b'{"unexpected":NaN,','non-finite event JSON number')]:
            fixture=synthetic_publication();name='INTENT.json'
            raw=lead+fixture['raw'][name].lstrip()[1:]
            fixture['raw'][name]=raw;ref=fixture['reference']['records'][name]
            ref.update(bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest());ref['identity'][6]=len(raw)
            with self.subTest(error=error),self.assertRaisesRegex(RuntimeError,error):self.check(fixture)

    def test_exact_observed_references_reject_ns_rebases_and_aliases(self):
        contract=read_contract(CANDIDATE)
        self.assertTrue(owner_v2.validate_owner_declaration_v2(contract)['owner_declaration_consistent'])
        for field,value in [('path',owner_v2.FROZEN_R34_ROOT),('sha256',owner_v2.FROZEN_R34_ROOT_SHA256)]:
            changed=copy.deepcopy(contract);changed['owner_cas_publication']['records']['INTENT.json'][field]=value
            with self.subTest(field=field),self.assertRaises(RuntimeError):
                owner_v2.validate_owner_declaration_v2(changed)
        changed=copy.deepcopy(contract)
        for ref in changed['owner_cas_publication']['records'].values():
            ref['identity'][7]+=1;ref['identity'][8]+=1
        with self.assertRaises(RuntimeError):owner_v2.validate_owner_declaration_v2(changed)

    def test_publication_or_boolean_flags_cannot_fill_root_acceptance(self):
        contract=read_contract(CANDIDATE)
        for value in [owner_v2.publication_reference(),
                      owner_v2.publication_reference()['records']['RESULT.json'],
                      {'original_lock_verified':True,'source_review_verified':True}]:
            changed=copy.deepcopy(contract);changed['owner_acquisition']['root_acceptance']=value
            with self.assertRaisesRegex(RuntimeError,'unreviewed root_acceptance'):
                owner_v2.validate_storage_owner_v2(changed)
        with self.assertRaisesRegex(RuntimeError,'original-lock custody and source review'):
            owner_v2.validate_storage_owner_v2(contract)

    def test_live_adapter_rejects_directory_or_leaf_drift_before_credit(self):
        contract=read_contract(CANDIDATE);calls=[]
        def unexpected_pin(*args,**kwargs):calls.append(args[0]);raise AssertionError('must not read before directory check')
        wrong=list(owner_v2.CAS_DIRECTORY['identity']);wrong[1]+=1
        with self.assertRaisesRegex(RuntimeError,'directory before read'):
            owner_v2.read_owner_cas_publication(contract,unexpected_pin,lambda path:wrong)
        self.assertEqual(calls,[])
        def wrong_leaf(path,expected,limit):
            calls.append(path);changed=copy.deepcopy(expected);changed['identity'][1]+=1
            return changed,b''
        with self.assertRaisesRegex(RuntimeError,'complete original event identity'):
            owner_v2.read_owner_cas_publication(contract,wrong_leaf,lambda path:list(owner_v2.CAS_DIRECTORY['identity']))
        self.assertEqual(calls,[owner_v2.CAS_EVENT_REFS['INTENT.json']['path']])

    def test_two_pass_reader_checks_raw_bytes_full_f9_and_directory_bookends(self):
        fixture = synthetic_publication()
        reference = fixture['reference']

        def observe(variant=None):
            calls, directories = [], []

            def pin(path, expected, limit):
                self.assertEqual(limit, 4096)
                name = pathlib.PurePosixPath(path).name
                self.assertIn(name, owner_v2.CAS_NAMES)
                self.assertEqual(expected, reference['records'][name])
                actual, raw = copy.deepcopy(expected), fixture['raw'][name]
                calls.append(path)
                if len(calls) == 4:
                    if variant == 'same_reported_hash_different_raw':
                        raw = b'[' + raw[1:]
                    elif variant == 'second_pass_inode':
                        actual['identity'][1] += 1
                return actual, raw

            def directory_f9(path):
                self.assertEqual(path, reference['directory']['path'])
                identity = list(reference['directory']['identity'])
                directories.append(path)
                if variant == 'after_directory' and len(directories) == 2:
                    identity[8] += 1
                return identity

            result = owner_v2.read_publication_records(reference, pin, directory_f9)
            self.assertEqual(calls, [reference['records'][name]['path']
                                    for name in owner_v2.CAS_NAMES] * 2)
            self.assertEqual(directories, [reference['directory']['path']] * 2)
            return result

        raw, identity = observe()
        self.assertEqual(raw, fixture['raw'])
        self.assertEqual(identity, reference['directory']['identity'])
        for variant, error in [
                ('same_reported_hash_different_raw', 'complete original event bytes'),
                ('second_pass_inode', 'complete original event identity'),
                ('after_directory', 'directory after read')]:
            with self.subTest(variant=variant), self.assertRaisesRegex(RuntimeError, error):
                observe(variant)

    def test_actual_admit_gate_precedes_all_storage_effects(self):
        contract=read_contract(CANDIDATE)
        tree=ast.parse((CANDIDATE/'admit.py').read_bytes())
        names={'validate_owner_declaration_v2','need','owner_cas_publication_inputs','rotation_schedule'}
        selected=[]
        for node in tree.body:
            call=node.value if isinstance(node,(ast.Assign,ast.Expr)) else None
            if not isinstance(call,ast.Call) or not isinstance(call.func,ast.Name):continue
            if call.func.id not in names:continue
            if call.func.id=='need' and not (len(call.args)==2 and isinstance(call.args[1],ast.Constant) and
                                            call.args[1].value=='fixed root new-storage admission'):continue
            selected.append(node)
            if call.func.id=='rotation_schedule':break
        self.assertEqual(len(selected),4)
        gate=selected[-1].lineno
        for node in ast.walk(tree):
            if not isinstance(node,ast.Call):continue
            name=node.func.id if isinstance(node.func,ast.Name) else node.func.attr if isinstance(node.func,ast.Attribute) else ''
            if name in {'boot_is','check_tools','rotation_inputs','flock','physical_image','offline_image_observation','save'}:
                self.assertGreater(node.lineno,gate,name)
        calls=[]
        def diagnostic(value):calls.append('read-only-publication');return None
        scope=rotation_module(CANDIDATE)
        scope.update(contract=contract,C=pathlib.Path(contract['p4_source']),
                     os=types.SimpleNamespace(getresuid=lambda:(0,0,0),getresgid=lambda:(0,0,0)),
                     owner_cas_publication_inputs=diagnostic)
        with self.assertRaisesRegex(RuntimeError,'original-lock custody and source review'):
            exec(compile(ast.Module(body=selected,type_ignores=[]),'actual_admit_readonly_prefix','exec'),scope)
        self.assertEqual(calls,['read-only-publication'])
        source=(CANDIDATE/'admit.py').read_text()
        self.assertNotIn("['root_acceptance']['path']",source)
        self.assertEqual(source.count('owner_cas_publication_inputs(contract)'),2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
