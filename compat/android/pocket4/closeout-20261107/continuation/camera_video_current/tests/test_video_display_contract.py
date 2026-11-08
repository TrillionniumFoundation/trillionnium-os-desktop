"""Pure host controls for the frozen video/display consumer.

`valid_receipts` is SYNTHETIC TEST DATA, not a physical video, audio, display,
Main or Android qualification. It exercises the unchanged actual producer
schemas. The source controls use real temporary files, the formal 29-module
preparation/entry and source_packet. They never call Supervisor.run, DBus, a
device, a Main API or an acoustic actor. Only fixture source paths are relocated.
"""
import ast
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]
WRAPPER_SHA256 = 'b0d40754761f53c30f5d8074cb7dec4974c814e35862800d2409dd39da8040d5'
SYNTHETIC_ONLY = 'TEST RECEIPTS ONLY; NO ACTUAL CAMERA/AUDIO/DISPLAY SUCCESS'


def load(path, name):
    module = types.ModuleType(name)
    module.__file__ = str(path)
    exec(compile(path.read_bytes(), str(path), 'exec'), module.__dict__)
    return module


def reference(name):
    raw = ('synthetic-test-receipt:' + name).encode('ascii')
    return {'path': '/synthetic-test-only/' + name, 'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest()}


def valid_receipts():
    """Return a new, explicitly synthetic matching set; do not grant authority.

    Actual owned host controls may replace the PID/identity/reference fields
    with their own measured records. These placeholder references are not read
    from disk and have never represented a real Android or display execution.
    """
    preparation = reference('preparation.json')
    plan_ref = reference('plan.json')
    parent_ref = reference('acoustic-supervisor/parent.json')
    worker_ref = reference('result.json')
    limits = copy.deepcopy(load(ROOT / 'source/camera_profiles.py', 'synthetic_profiles').LIMITS)
    plan = {'case_root': '/synthetic-test-only/case', 'limits': limits,
            'audio_nonce': '123456789abcdef0', 'framework_epoch_sha256': 'a' * 64}
    direct_operator = {'pid': 4101, 'parent': 4100, 'start_ticks': 123456}
    ready_device = {'synthetic_only': True, 'device': '/synthetic-test-only/video0',
                    'major': 81, 'minor': 0, 'inode': 9123}
    parent = {'schema': 'pocket4-current-camera-acoustic-parent-v1', 'plan': plan_ref,
              'preparation': preparation, 'case_root': plan['case_root'], 'limits': limits,
              'nonce': plan['audio_nonce'], 'automatic_retry': False,
              'parent': {**direct_operator, 'uids': [0, 0, 0, 0]}}
    business = {'pid': 4102, 'parent': direct_operator['pid'], 'start_ticks': 123457,
                'uids': [0, 0, 0, 0]}
    actors = {role: {'pid': pid, 'uid': uid, 'child_started': True,
                     'child_reaped': True, 'pidfd_closed': True,
                     'pipe_eof': {'stdout': True, 'stderr': True}, 'returncode': 0,
                     # Actual retire_leader does not populate a per-actor tree
                     # cleanup success. The owning subreaper proves that below.
                     'owned_tree_cleanup_complete': False}
              for role, pid, uid in (('business', 4102, 0), ('emit', 4103, 1000),
                                     ('listen', 4104, 1000))}
    acoustic = {role: {'role': role, 'parent': parent_ref, 'exit_code': 0,
                       'leader_reaped': True, 'pipe_eof': {'stdout': True, 'stderr': True},
                       'automatic_retry': False,
                       **{phase: {'nonce': plan['audio_nonce']} for phase in ('ready', 'started', 'closed')}}
                for role in ('emit', 'listen')}
    supervisor = {'schema': 'pocket4-current-camera-acoustic-supervisor-result-v1',
        'plan': plan_ref, 'preparation': preparation, 'kind': 'camera_video',
        'nonce': plan['audio_nonce'], 'limits': limits, 'inner_result': worker_ref,
        'state': 'CURRENT_CAMERA_VIDEO_SCOPE_VERIFIED_CLEAN',
        'case_business_success_verified': True, 'worker_result_verified': True,
        'outcome_unknown': False, 'whole_app_business_accepted': False,
        'automatic_retry': False, 'automatic_rollback': False, 'error': None,
        'errors': [], 'received_signals': [], 'Main_signals': 0,
        'Android_UI_actions_by_supervisor': 0,
        'cancellation_commit': {'pending_at_commit': [], 'decision_after_all_context_close': True},
        'subreaper': {'begin_passed': True, 'restored': True, 'final_children_empty': True},
        'adopted_retirement': {'owned_tree_cleanup_complete': True, 'descendants': []},
        'control_fd_closed': True, 'selector_closed': True,
        'audio_artifact_descriptors_closed': True, 'held_Main_closed': True,
        'actors': actors, 'business_process': business, 'acoustic_results': acoustic}
    worker = {'schema': 'pocket4-current-camera-video-case-result-v1',
        'plan': plan_ref, 'source_preparation': preparation, 'kind': 'camera_video',
        'state': 'CURRENT_CAMERA_VIDEO_SCOPE_VERIFIED_CLEAN',
        'case_business_success_verified': True, 'outcome_unknown': False,
        'secondary_errors': [], 'error': None, 'runtime_qualified': False,
        'whole_app_business_accepted': False, 'camera_recovery_qualified': False,
        'automatic_retry': False,
        **{key: True for key in ('owned_task_cleanup_verified', 'current_Main_APIs_closed',
            'whole_case_OFD_closed', 'evidence_witness_closed', 'acoustic_channel_closed',
            'owned_decoder_descriptor_closed', 'final_source_and_identity_chain_unchanged')},
        **{key: None for key in ('acoustic_pending', 'pending_business_action',
            'pending_owned_task_remove', 'owned_task_remaining', 'recording_pending')},
        'cancellation_commit': {'received_signals': [], 'pending_at_commit': [],
                                'decision_after_all_context_close': True},
        **{key: ['test-camera-1', 'test-player-2', 'test-camera-3'] for key in
           ('native_launches', 'exact_normal_closes', 'native_tasks', 'normal_closes')},
        'recording': {'state': 'CAMERA_VIDEO_RECORD_AUDIO_PLAYBACK_VERIFIED',
            'camera_video_verified': True, 'outcome_unknown': False, 'pending': None,
            'nonce': plan['audio_nonce'], 'epoch_sha256': plan['framework_epoch_sha256'],
            'original_mode': 'synthetic-original-mode', 'final_mode': 'synthetic-original-mode',
            'owned_task_closed': True, 'preserved_state': True, 'host_retired': True},
        'acoustic_results': copy.deepcopy(acoustic), 'physical_device': ready_device,
        **{key: reference(key + '.json') for key in ('full_decode', 'current_audio', 'current_playback')}}
    claim = {'plan': plan_ref, 'operator': business, 'automatic_retry': False}
    # Detach all aliases, so a negative control cannot accidentally update both
    # sides of a binding. Every valid_receipts() call has independent objects.
    return json.loads(json.dumps(dict(plan_ref=plan_ref, plan=plan, preparation=preparation,
        direct_operator=direct_operator, ready_device=ready_device, parent=parent,
        parent_ref=parent_ref, supervisor=supervisor, worker=worker,
        worker_ref=worker_ref, claim=claim)))


def replace_nested(document, path, value):
    target = document
    for key in path[:-1]:
        target = target[key]
    target[path[-1]] = value


def fd_table():
    result = {}
    for name in os.listdir('/proc/self/fd'):
        try:
            result[int(name)] = os.readlink('/proc/self/fd/' + name)
        except FileNotFoundError:
            pass
    return result


class TerminalContractControls(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        path = ROOT / 'display/video_display_wrapper.py'
        if hashlib.sha256(path.read_bytes()).hexdigest() != WRAPPER_SHA256:
            raise RuntimeError('CONTROLS_REQUIRE_THE_FROZEN_REVIEWED_WRAPPER')
        cls.wrapper = load(path, 'video_terminal_contract_controls')

    def reject(self, path, value, message):
        fixture = valid_receipts()
        replace_nested(fixture, path, value)
        with self.assertRaisesRegex(RuntimeError, message):
            self.wrapper.validate_video_terminals(**fixture)

    def test_synthetic_matching_receipts_accept_only_the_narrow_contract(self):
        fixture = valid_receipts()
        self.assertIn('NO ACTUAL', SYNTHETIC_ONLY)
        self.assertTrue(fixture['ready_device']['synthetic_only'])
        self.assertTrue(self.wrapper.validate_video_terminals(**fixture))
        self.assertTrue(all(not fixture['worker'][key] for key in
            ('runtime_qualified', 'camera_recovery_qualified', 'whole_app_business_accepted')))
        self.assertTrue(all(not row['owned_tree_cleanup_complete']
                            for row in fixture['supervisor']['actors'].values()))

    def test_direct_supervisor_cannot_substitute_for_the_claimed_worker(self):
        fixture = valid_receipts()
        fixture['claim']['operator'] = copy.deepcopy(fixture['parent']['parent'])
        with self.assertRaisesRegex(RuntimeError, 'execute-once claim'):
            self.wrapper.validate_video_terminals(**fixture)
        self.reject(('supervisor', 'business_process', 'parent'), 4100, 'execute-once claim')

    def test_exact_direct_parent_pid_start_and_root_identity_are_required(self):
        for key, value in (('pid', 5001), ('parent', 5000), ('start_ticks', 123455),
                           ('uids', [1000, 1000, 1000, 1000])):
            with self.subTest(key=key):
                self.reject(('parent', 'parent', key), value, 'exact owned root child')

    def test_pending_or_received_cancellation_cannot_commit_success(self):
        mutations = [
            (('supervisor', 'received_signals'), [15], 'successful terminal'),
            (('supervisor', 'cancellation_commit', 'pending_at_commit'), [15], 'cancellation commit'),
            (('supervisor', 'cancellation_commit', 'decision_after_all_context_close'), False, 'cancellation commit'),
            (('worker', 'cancellation_commit', 'received_signals'), [2], 'worker cancelled'),
            (('worker', 'cancellation_commit', 'pending_at_commit'), [15], 'worker cancelled'),
            (('worker', 'cancellation_commit', 'decision_after_all_context_close'), False, 'worker cancelled')]
        for path, value, message in mutations:
            with self.subTest(path=path):
                self.reject(path, value, message)

    def test_physical_identity_must_match_the_owned_display_ready(self):
        self.reject(('worker', 'physical_device', 'inode'), 9124, 'different physical devices')
        self.reject(('ready_device',), None, 'different physical devices')

    def test_each_principal_requires_zero_exit_reap_pidfd_and_complete_pipes(self):
        for role in ('business', 'emit', 'listen'):
            for field, value in (('returncode', 1), ('child_started', False), ('child_reaped', False),
                                 ('pidfd_closed', False), ('pipe_eof', {'stdout': True, 'stderr': False})):
                with self.subTest(role=role, field=field):
                    self.reject(('supervisor', 'actors', role, field), value, 'principal retirement')
        self.reject(('supervisor', 'actors', 'listen', 'pid'), 4103, 'three distinct')
        self.reject(('supervisor', 'actors', 'business', 'uid'), 1000, 'principal retirement')

    def test_owner_retirement_and_all_contexts_are_mandatory(self):
        for path in (('supervisor', 'subreaper', 'restored'),
                     ('supervisor', 'subreaper', 'final_children_empty'),
                     ('supervisor', 'adopted_retirement', 'owned_tree_cleanup_complete'),
                     ('supervisor', 'control_fd_closed'), ('supervisor', 'selector_closed'),
                     ('supervisor', 'audio_artifact_descriptors_closed'), ('supervisor', 'held_Main_closed')):
            with self.subTest(path=path):
                self.reject(path, False, 'retained a child')
        self.reject(('supervisor', 'adopted_retirement', 'descendants'), [{'pid': 5002}], 'retained a child')
        for key in ('owned_task_cleanup_verified', 'current_Main_APIs_closed', 'whole_case_OFD_closed',
                    'evidence_witness_closed', 'acoustic_channel_closed', 'owned_decoder_descriptor_closed',
                    'final_source_and_identity_chain_unchanged'):
            with self.subTest(key=key):
                self.reject(('worker', key), False, 'incomplete contexts')
        for key in ('acoustic_pending', 'pending_business_action', 'pending_owned_task_remove',
                    'owned_task_remaining', 'recording_pending'):
            with self.subTest(key=key):
                self.reject(('worker', key), 'unresolved', 'incomplete contexts')

    def test_three_launches_and_same_recording_nonce_epoch_mode_are_required(self):
        self.reject(('worker', 'native_launches'), ['test-camera-1'] * 3, 'three actual distinct')
        self.reject(('worker', 'exact_normal_closes'), ['test-camera-1'], 'three actual distinct')
        for key, value in (('nonce', 'f' * 16), ('epoch_sha256', 'b' * 64),
                           ('final_mode', 'changed'), ('host_retired', False), ('pending', 'open')):
            with self.subTest(key=key):
                self.reject(('worker', 'recording', key), value, 'recording/playback/state')

    def test_photo_schemas_and_false_success_promotions_are_rejected(self):
        self.reject(('worker', 'schema'), 'pocket4-final-camera-photo-case-result-v1', 'narrow current video')
        self.reject(('supervisor', 'schema'), 'pocket4-final-camera-photo-result-v1', 'successful terminal')
        for key in ('runtime_qualified', 'whole_app_business_accepted', 'camera_recovery_qualified', 'automatic_retry'):
            with self.subTest(key=key):
                self.reject(('worker', key), True, 'narrow current video')
        self.reject(('supervisor', 'whole_app_business_accepted'), True, 'successful terminal')
        self.reject(('supervisor', 'automatic_rollback'), True, 'successful terminal')

    def test_receipt_refs_and_finite_acoustic_phases_bind_exact_parent_and_nonce(self):
        self.reject(('supervisor', 'inner_result', 'sha256'), '0' * 64, 'successful terminal')
        self.reject(('parent', 'plan', 'sha256'), '0' * 64, 'another plan')
        fixture = valid_receipts()
        fixture['supervisor']['acoustic_results']['listen']['closed']['nonce'] = 'f' * 16
        fixture['worker']['acoustic_results'] = copy.deepcopy(fixture['supervisor']['acoustic_results'])
        with self.assertRaisesRegex(RuntimeError, 'finite acoustic receipt'):
            self.wrapper.validate_video_terminals(**fixture)
        self.reject(('worker', 'acoustic_results', 'emit', 'exit_code'), 1, 'disagree on acoustic')


class SourceAndBudgetControls(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='video-display-contract-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name).resolve()
        before = fd_table()
        self.addCleanup(lambda: self.assertEqual(before, fd_table()))
        self.wrapper = load(ROOT / 'display/video_display_wrapper.py', 'isolated_video_display')

    def prepare(self):
        builder = load(ROOT / 'tools/prepare_camera_video.py', 'video_display_source_builder')
        result = builder.prepare(ROOT / 'source', ROOT / 'reviewed-source-inventory.json',
                                 builder.INVENTORY_SHA256, self.root / 'prepared')
        self.preparation = result['preparation']
        packet = self.wrapper.configure_video_preparation(self.preparation['path'], self.preparation['sha256'])
        self.common, self.packet, self.planner = self.wrapper.VIDEO_CONTEXT
        self.assertEqual(packet, self.packet)
        return result

    def source_plan(self):
        # No Main/baseline/identity is qualified. This drives source_packet only.
        c = self.common
        c.FINAL = self.root / 'fixture-final'
        self.wrapper.QUALIFICATION = c.FINAL / 'qualification'
        self.case = self.wrapper.QUALIFICATION / ('business-camera-video-plan-' + '1' * 32)
        source = self.case / 'source'
        source.mkdir(parents=True)
        files = [c.write_new(source / Path(r['path']).name, c.read_ref(r), 0o400) for r in self.packet['files']]
        names = {Path(r['path']).name: r for r in files}
        origins = [self.preparation] + self.packet['files'] + self.packet['origins']
        profiles = self.planner.named(c, self.packet, 'camera_profiles.py')
        tasks = {}
        for role, profile in zip(('camera', 'player'), profiles.profiles('camera_video')[:2]):
            tasks[role] = c.write_new(self.case / ('task-' + role + '.json'), {
                'schema': 'pocket4-final-business-task-source-v1', 'files': copy.deepcopy(files),
                'origins': copy.deepcopy(origins), 'guard_source': names['camera_guard.py'],
                'recorder_source': names['camera_flow.py'], 'target_package': profile['package'],
                'target_uid': profile['uid'], 'old_runtime_authority_transferred': False}, 0o400)
        self.plan = {name: None for name in self.planner.BASE_FIELDS}
        self.plan.update(schema='pocket4-current-camera-video-plan-v1', kind='camera_video',
            case_root=str(self.case), task_source_manifests=tasks, source_preparation=self.preparation,
            limits=profiles.LIMITS, whole_app_business_accepted=False, automatic_retry=False)
        self.plan_ref = c.write_new(self.case / 'plan.json', self.plan, 0o400)
        self.request = {'schema': 'pocket4-camera-video-display-input-v1', 'plan': self.plan_ref,
                        'source_preparation': self.preparation, 'automatic_retry': False,
                        'whole_app_business_accepted': False}
        return c.canonical(self.request)

    def test_formal_configure_reads_exact_graph_once_and_rejects_wrong_pin(self):
        self.prepare()
        self.assertEqual(len(self.packet['files']), 29)
        self.assertEqual(self.wrapper.PREPARATION_REF, self.preparation)
        self.assertEqual(self.wrapper.SOURCES['camera'][1], self.wrapper.VIDEO_ENTRY_PIN[1])
        self.assertFalse(self.packet['runtime_qualified'])
        with self.assertRaisesRegex(RuntimeError, 'one externally reviewed'):
            self.wrapper.configure_video_preparation(self.preparation['path'], self.preparation['sha256'])
        another = load(ROOT / 'display/video_display_wrapper.py', 'wrong_pin_video_display')
        with self.assertRaisesRegex(RuntimeError, 'SHA differs'):
            another.configure_video_preparation(self.preparation['path'], '0' * 64)
        self.assertIsNone(another.VIDEO_CONTEXT)

    def test_previous_inventory_is_rejected_before_loading_any_entry(self):
        self.prepare()
        packet = copy.deepcopy(self.packet)
        packet['source_inventory_sha256'] = '2444a7f3dcbeace9a3a9c5b86d2fc815a59ae965b626ddb80ba99b6f4d13520f'
        path = self.root / 'old-inventory.json'
        raw = self.common.canonical(packet)
        path.write_bytes(raw)
        consumer = load(ROOT / 'display/video_display_wrapper.py', 'old_inventory_consumer')
        with self.assertRaisesRegex(RuntimeError, 'exact reviewed current video preparation required'):
            consumer.configure_video_preparation(path, hashlib.sha256(raw).hexdigest())
        self.assertIsNone(consumer.VIDEO_CONTEXT)
        self.assertIsNone(consumer.PREPARATION_REF)

    def test_previous_entry_pin_is_rejected_with_current_inventory(self):
        self.prepare()
        packet = copy.deepcopy(self.packet)
        entry = next(r for r in packet['files'] if Path(r['path']).name == 'camera_entry.py')
        entry.update(bytes=9807, sha256='ab929997fa08d5acda471cec6219fcbc2eb1edeed2a7b6c7bae189f7abb842a1')
        path = self.root / 'old-entry.json'
        raw = self.common.canonical(packet)
        path.write_bytes(raw)
        consumer = load(ROOT / 'display/video_display_wrapper.py', 'old_entry_consumer')
        with self.assertRaisesRegex(RuntimeError, 'exact current video entry required'):
            consumer.configure_video_preparation(path, hashlib.sha256(raw).hexdigest())
        self.assertIsNone(consumer.VIDEO_CONTEXT)
        self.assertIsNone(consumer.PREPARATION_REF)

    @unittest.skipUnless(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0,
                         'actual constructor intentionally requires root, never simulated')
    def test_actual_source_packet_constructor_reserves_complete_budgets(self):
        self.prepare()
        raw = self.source_plan()
        runner = self.wrapper.Supervisor(raw, self.root / 'output')
        self.assertEqual(runner.operation_deadline - runner.started, 530)
        self.assertEqual(runner.deadline - runner.started, 665)
        self.assertEqual(runner.record['budgets']['video_worker_cleanup_seconds'], 60)
        self.assertEqual(runner.record['budgets']['acoustic_cancellation_grace_seconds'], 90)
        # 20 READY + 510 acoustic + 90 cancel +15 release +5 retire +15
        # independent observer +4 commit reserve. No runtime action follows.
        self.assertGreaterEqual(self.wrapper.WRAPPER_SECONDS, 20 + 510 + 90 + 15 + 5 + 15 + 4)
        self.assertEqual(runner.spec['transaction_id'], 'video-' + '1' * 32)
        self.assertEqual(runner.actors, {})
        self.assertEqual(runner.record['Main_lifecycle_actions'], 0)
        for name in ('execute-once.json', 'result.json', 'evidence', 'acoustic-supervisor'):
            self.assertFalse((self.case / name).exists())

    @unittest.skipUnless(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0,
                         'actual constructor intentionally requires root, never simulated')
    def test_photo_request_replay_and_old_short_budget_are_rejected_before_launch(self):
        self.prepare()
        raw = self.source_plan()
        wrong = dict(self.request, schema='pocket4-camera-photo-display-input-v1')
        with self.assertRaisesRegex(RuntimeError, 'exact current video display request'):
            self.wrapper.Supervisor(self.common.canonical(wrong), self.root / 'output')
        (self.case / 'execute-once.json').write_text('{}\n')
        with self.assertRaisesRegex(RuntimeError, 'execution already begun'):
            self.wrapper.Supervisor(raw, self.root / 'output')
        (self.case / 'execute-once.json').unlink()
        self.plan['limits']['supervisor_seconds'] = 360
        plan_path = self.case / 'plan.json'
        plan_path.chmod(0o600)  # Explicitly mutate this isolated negative fixture.
        plan_path.write_bytes(self.common.canonical(self.plan))
        plan_path.chmod(0o400)
        self.request['plan'] = self.common.regular(plan_path, contents=False)
        with self.assertRaisesRegex(RuntimeError, 'acoustic owner budgets'):
            self.wrapper.Supervisor(self.common.canonical(self.request), self.root / 'output')

    @unittest.skipUnless(os.getuid() == os.geteuid() == os.getgid() == os.getegid() == 0,
                         'actual constructor intentionally requires root, never simulated')
    def test_launch_writes_base_plan_request_before_any_actor_is_allowed(self):
        self.prepare()
        raw = self.source_plan()
        out = self.root / 'output'
        out.mkdir()
        runner = self.wrapper.Supervisor(raw, out)
        entry = Path(self.wrapper.SOURCES['camera'][0])
        fd = os.open(entry, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        self.addCleanup(os.close, fd)
        runner.source_fds = {'camera': fd}
        captured = {}
        class NoActorAllowed(RuntimeError):
            pass
        def stop_before_process(role, argv, pass_fds):
            captured.update(role=role, argv=argv, pass_fds=pass_fds)
            raise NoActorAllowed('TEST BOUNDARY: no process or device action')
        runner.actor = stop_before_process
        with self.assertRaises(NoActorAllowed):
            runner.launch_camera()
        ref = runner.record['video_execution_request']
        self.assertEqual(self.common.parse(self.common.read_ref(ref)), {'base_plan': self.plan_ref})
        self.assertEqual(Path(ref['path']).stat().st_mode & 0o777, 0o400)
        self.assertEqual(captured['role'], 'camera')
        self.assertEqual(captured['pass_fds'], (fd,))
        self.assertEqual(captured['argv'][-5:], ['execute', '--request', ref['path'],
                                               '--expect-request-sha256', ref['sha256']])
        self.assertEqual(runner.actors, {})

    @unittest.skipUnless(os.getuid() == os.geteuid() == 0, 'formal entry intentionally requires root')
    def test_formal_entry_refuses_old_direct_plan_request_without_runtime_actions(self):
        self.prepare()
        self.source_plan()
        path = self.root / 'old-photo-request.json'
        raw = self.common.canonical(self.plan)
        path.write_bytes(raw)
        entry = Path(self.wrapper.SOURCES['camera'][0])
        result = subprocess.run(['/usr/bin/python3', '-I', '-B', str(entry), '--preparation',
            self.preparation['path'], '--expect-preparation-sha256', self.preparation['sha256'],
            'execute', '--request', str(path), '--expect-request-sha256', hashlib.sha256(raw).hexdigest()],
            capture_output=True, timeout=10, check=False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn(b'EXACT_CURRENT_VIDEO_EXECUTION_REQUEST', result.stderr)
        self.assertEqual(result.stdout, b'')
        self.assertFalse((self.case / 'execute-once.json').exists())
        self.assertFalse((self.case / 'acoustic-supervisor').exists())

    def test_generated_owned_methods_and_holder_lease_algorithm_are_unchanged(self):
        def methods(path):
            text = path.read_text()
            cls = next(node for node in ast.parse(text).body
                       if isinstance(node, ast.ClassDef) and node.name == 'Supervisor')
            lines = text.splitlines(True)
            return {node.name: ''.join(lines[node.lineno - 1:node.end_lineno])
                    for node in cls.body if isinstance(node, ast.FunctionDef)}
        original = methods(ROOT / 'provenance/photo_display_wrapper.py')
        current = methods(ROOT / 'display/video_display_wrapper.py')
        changed = {name for name in original if original[name] != current[name]}
        self.assertEqual(changed, {'__init__', 'launch_camera', 'validate_camera_result', 'run'})
        self.assertEqual(len(set(original) - changed), 16)
        old_holder = ast.parse((ROOT / 'provenance/display_holder.py').read_bytes())
        new_holder = ast.parse((ROOT / 'display/display_holder.py').read_bytes())
        constants = [node for node in ast.walk(old_holder) if isinstance(node, ast.Constant) and node.value == 475]
        self.assertEqual(len(constants), 2)
        for node in constants:
            node.value = 665
        self.assertEqual(ast.dump(old_holder, include_attributes=False), ast.dump(new_holder, include_attributes=False))
        self.assertEqual(hashlib.sha256((ROOT / 'display/display_lease.py').read_bytes()).hexdigest(),
                         '81f34cdbc75a2cf4e092a961fe4dce5d23522842c0ec54cdcff4fc9c99e4dbfd')
        self.assertEqual(hashlib.sha256((ROOT / 'display/video_display_wrapper.py').read_bytes()).hexdigest(),
                         WRAPPER_SHA256)


if __name__ == '__main__':
    unittest.main(verbosity=2)
