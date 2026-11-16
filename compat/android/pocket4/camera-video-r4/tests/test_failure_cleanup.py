"""Portable source controls using actual methods and local writer projections.

No Main, Android, proc, host audio, subprocess or signal operation is executed.
The real Session.android -> CameraFlow.android -> Policy chain terminates in
an in-memory fixture transport. Actual Evidence/record writes use a temporary
directory. Fixed AudioFlinger text is a minimal C++ writer projection, not an
actual full dumpsys/physical qualification record.
"""
import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import runpy
import sys
import tempfile
import time
import types
import unittest
from unittest import mock

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures'
MANIFEST = json.loads((ROOT / 'source-manifest.json').read_bytes())
SOURCE_ROWS = {row['path']: row for row in MANIFEST['production_files']}
BASELINE_RAW = (ROOT / 'origin-source-manifest.json').read_bytes()
if len(BASELINE_RAW) != 16609 or hashlib.sha256(BASELINE_RAW).hexdigest() != '143424cf8d0b36acc7b193ee1e9349fbf163f18322b4bae038fd227f87884b17':
    raise RuntimeError('exact frozen publication baseline manifest required')
BASELINE_ROWS = {row['path']: row for row in json.loads(BASELINE_RAW)['production_files']}


def need(ok, why):
    if not ok:
        raise RuntimeError(why)


def canonical_ast(value):
    """Keep semantic fields, independent of ast.dump's versioned formatting.

    CPython 3.12 adds empty type_params to functions/classes; 3.13 adds
    default_value=None to type parameters. Their absence has the same meaning
    on earlier interpreters. No other empty or optional fields are discarded.
    """
    if isinstance(value, ast.AST):
        kind = type(value).__name__
        fields = {}
        for key, item in ast.iter_fields(value):
            if (kind in ('FunctionDef', 'AsyncFunctionDef', 'ClassDef')
                    and key == 'type_params' and type(item) is list and not item):
                continue
            if (kind in ('TypeVar', 'ParamSpec', 'TypeVarTuple')
                    and key == 'default_value' and item is None):
                continue
            fields[key] = canonical_ast(item)
        return {'node': kind, 'fields': fields}
    if type(value) is list:
        return [canonical_ast(item) for item in value]
    if value is None or type(value) in (str, int, float, bool):
        # Tag scalar types so bool/int and other equal JSON values cannot alias.
        return {'scalar': type(value).__name__, 'value': value}
    if type(value) is bytes:
        return {'scalar': 'bytes', 'hex': value.hex()}
    if type(value) is complex:
        return {'scalar': 'complex', 'real': value.real, 'imag': value.imag}
    if value is Ellipsis:
        return {'scalar': 'ellipsis'}
    raise TypeError('unsupported AST field type: ' + type(value).__name__)


def load(name):
    path = ROOT / 'source' / name
    raw = path.read_bytes(); expected = SOURCE_ROWS['source/' + name]
    need(len(raw) == expected['bytes'] and hashlib.sha256(raw).hexdigest() == expected['sha256'], 'candidate source pin differs: ' + name)
    return types.SimpleNamespace(**runpy.run_path(str(path)))


R = load('camera_audio_runtime.py')
B = load('camera_audio_binding.py')
D = load('camera_video_driver.py')
C = load('camera_case.py')
BASE = load('camera_base_session.py')
SESSION = load('camera_session.py')
POLICY = load('camera_policy.py')
FLOW = load('camera_flow.py')
APP_FLOW = load('app_flow.py')
CHANNEL = load('camera_audio_channel.py')
SESSION_CLASS = SESSION.make_session(BASE)
FLOW_CLASS = FLOW.make_flow(APP_FLOW)


def raw(name='idle.txt'):
    return (FIXTURES / name).read_bytes()


class Common:
    NATIVE_PREFIX = ['fixture-never-dispatched']
    STACKS = ['/system/bin/am', 'stack', 'list']
    FOREGROUND = ['fixture-never-dispatched-foreground']
    need = staticmethod(need)
    parse = staticmethod(json.loads)

    @staticmethod
    def canonical(value):
        return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()

    def write_new(self, path, value, *unused):
        path = Path(path)
        blob = value if type(value) is bytes else self.canonical(value)
        with path.open('xb') as output:
            output.write(blob)
        return {'path': str(path), 'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest()}

    def read_ref(self, ref, maximum=33554432):
        blob = Path(ref['path']).read_bytes()
        need(len(blob) <= maximum and len(blob) == ref['bytes'] and hashlib.sha256(blob).hexdigest() == ref['sha256'], 'fixture reference drift')
        return blob

    @staticmethod
    def private_dir(path, create=False):
        p = Path(path)
        if create:
            p.mkdir(exist_ok=True)
        need(p.is_dir(), 'fixture directory missing')
        return p


class Acoustic:
    def __init__(self, session):
        self.session = session; self.closed = False; self.pending = None
        self.results = {}; self.sequence = 0; self.verifies = 0; self.fail_verify_at = None
        self.parent_ref = {'fixture': 'same-parent'}

    def verify(self):
        self.verifies += 1
        need(not self.closed and self.verifies != self.fail_verify_at, 'FIXTURE_PARENT_IDENTITY_CHANGED')

    def attach(self, session):
        need(session is self.session, 'fixture session changed')

    def complete(self, role, overrides=None):
        s = self.session
        if not (s.root / 'acoustic-supervisor').exists():
            (s.root / 'acoustic-supervisor').mkdir()
        self.results[role + '_prepare'] = {'fixture': 'started owned role'}
        self.results[role + '_go'] = {'fixture': 'go returned'}
        result = {'role': role, 'parent': self.parent_ref,
                  'phase': s.driver.result['actual_business_phase'],
                  'leader_reaped': True, 'exit_code': 0, 'automatic_retry': False,
                  'pipe_eof': {'stdout': True, 'stderr': True},
                  'closed': {'stream_closed': True, 'nonce': s.active['audio_nonce'], 'runtime_qualified': False}}
        result.update(overrides or {})
        result['reference'] = s.c.write_new(s.root / 'acoustic-supervisor' / (role + '-final.json'), result)
        self.results[role + '_finish'] = result
        self.sequence = len(self.results)

    def close(self):
        self.closed = True


class FixtureFlow(FLOW_CLASS):
    def __init__(self, session):
        self.session = session; self.c = session.c
        self.policy = POLICY.Policy(self)
        self.scope_ref = {'fixture': 'scope'}; self.scope = {'package': 'com.android.camera2'}
        self.bridge = types.SimpleNamespace(command_index=0)
        self.total_commands = self.command_index = 0
        self._private_backend_transport = False; self._android_mutation = False
        self.poisoned = self.closed = False
        self.camera_transport = self.transport = self.receive

    def guard(self, *args, **kwargs):
        need(not self.closed and not self.poisoned and time.monotonic() < self.session.deadline,
             'FIXTURE_HELD_TRANSPORT_OR_PHASE_REFUSED')

    def receive(self, argv, timeout):
        need(argv == ['/system/bin/dumpsys', 'media.audio_flinger'] and timeout == 15
             and self._android_mutation is False, 'unexpected fixture command')
        self.session.android_queries.append((list(argv), timeout))
        self.bridge.command_index += 1
        if self.session.transport_error is not None:
            self.poisoned = True
            raise self.session.transport_error
        return self.session.reply

    def close(self):
        self.closed = True


class FixtureSession(SESSION_CLASS):
    def __init__(self, root, data):
        self.c = Common(); self.root = Path(root).resolve()
        self.evidence_root = self.root / 'evidence'; self.evidence_root.mkdir(exist_ok=True)
        self.reply = data; self.transport_error = None; self.android_queries = []
        self.record_sequence = 0; self.guards = 0; self.fail_guard_at = None
        self.closed = False; self.helper = None
        self.active = {'audio_nonce': 'fixture-only-never-physical-nonce'}
        self.phase_name = 'final_cleanup'; self.phase_ref = {'fixture': 'cleanup-phase'}
        self.phase_value = {'deadline_monotonic_ns': time.monotonic_ns() + 60000000000}
        self.active_api = self.ordinary_admission = self.ui_dispatch_admission = None
        self.source_paths = {'camera_video_driver.py': str(ROOT / 'source/camera_video_driver.py')}
        self.components = {'camera_audio_binding.py': B, 'camera_audio_channel.py': CHANNEL,
                           **{key: types.SimpleNamespace() for key in ('camera_photo_model.py',
                             'camera_video_state.py', 'camera_video_media.py', 'camera_player_binding.py',
                             'camera_observations.py')}}
        self.baseline = types.SimpleNamespace(docs={'final_baseline': {'daemon_status': {'host_pid': 123}}})
        self.flow = FixtureFlow(self); self.tx = BASE.Evidence(self)
        self.acoustic = Acoustic(self)
        self.audio = R.AudioRuntime(self)
        self.audio.preflight_result = {'fixture': 'completed source admission, not actual Main'}
        self.audio.hardware_before = {'fixture': 'admitted hardware projection'}
        result = {'guard_before': {'fixture': 'unchanged Main'}, 'actual_business_phase': {'fixture': 'business-phase'}}
        self.driver = D.Driver(self, result)

    def guard(self, *args, **kwargs):
        self.guards += 1
        need(not self.closed and self.guards != self.fail_guard_at, 'FIXTURE_SESSION_GUARD_REFUSED')
        self.flow.guard()
        return {'fixture': 'unchanged Main'}

    def caller_status(self, label):
        need(label == 'camera-video-final' and self.phase_name == 'final_cleanup', 'fixture cleanup status scope')

    def begin_cleanup(self, trigger):
        # Case lifecycle harness only; real phase source stays byte-identical.
        self.phase_name = 'final_cleanup'
        return self.phase_ref


class Context:
    def __init__(self, *args):
        self.ref = {'fixture': 'context'}
    def close(self):
        pass


class DecodeUnknown(RuntimeError):
    pass


class FailureCleanupControls(unittest.TestCase):
    def make(self, name='idle.txt'):
        temp = tempfile.TemporaryDirectory(prefix='camera-failure-quiet-')
        self.addCleanup(temp.cleanup)
        return FixtureSession(Path(temp.name).resolve(), raw(name))

    def read_proof(self, s):
        return s.c.parse(s.c.read_ref(s.driver.failure_audio_quiet_ref))

    def assert_no_sample(self, s):
        self.assertEqual(s.android_queries, [])
        self.assertFalse(s.driver.failure_audio_quiet_verified)
        self.assertIsNone(s.driver.failure_audio_quiet_ref)
        self.assertFalse((s.evidence_root / 'audio-flinger-failure-cleanup.txt').exists())

    def execute_case(self, s, primary, configure=None):
        c = s.c
        base = {'case_root': str(s.root), 'support_manifest': {'fixture': 'support'},
                'baseline': {'fixture': 'baseline'}, 'qualification': {'fixture': 'qualification'},
                'source_preparation': {'fixture': 'preparation'}}
        base_ref = c.write_new(s.root / 'fixture-base.json', base)
        active_ref = c.write_new(s.root / 'fixture-active.json', {'fixture': 'active'})
        baseline = types.SimpleNamespace(guard=lambda: {'fixture': 'unchanged Main'})
        c.support = lambda ref: ({}, {'business_baseline.py': types.SimpleNamespace(BusinessBaseline=lambda *args: baseline)})
        c.EvidenceWitness = Context
        class BusinessDriver(D.Driver):
            def run(this):
                this.result['guard_before'] = {'fixture': 'unchanged Main'}
                if configure is not None:
                    configure(this)
                raise primary
        components = {
            'camera_plan.py': types.SimpleNamespace(validate=lambda *args: None,
                activate=lambda *args: (active_ref, [])),
            'camera_runtime.py': types.SimpleNamespace(ActionLock=Context, create_lease=lambda *args: {'fixture': 'lease'},
                phase=lambda *args: {'fixture': 'business-phase'}),
            'app_runtime.py': types.SimpleNamespace(process=lambda *args: {'fixture': 'worker'}),
            'camera_session.py': types.SimpleNamespace(make_session=lambda *args: lambda *more: s),
            'camera_base_session.py': BASE, 'camera_video_driver.py': types.SimpleNamespace(Driver=BusinessDriver),
            'camera_decode.py': types.SimpleNamespace(DecodeOutcomeUnknown=DecodeUnknown),
        }
        with mock.patch.object(C.os, 'getuid', return_value=0), mock.patch.object(C.os, 'geteuid', return_value=0), \
             mock.patch.object(C.signal, 'signal'), mock.patch.object(C.signal, 'pthread_sigmask'), \
             mock.patch.object(C.signal, 'sigpending', return_value=set()):
            return C.execute(c, base_ref, components, s.acoustic)[1]

    def test_01_one_final_android_sample_without_fabricated_business_windows(self):
        s = self.make(); s.audio.windows = {'input': {'fixture': 'only completed input window'}}
        before = copy.deepcopy(s.audio.windows)
        s.driver.finish()
        proof = self.read_proof(s)
        self.assertEqual(len(s.android_queries), 1)
        self.assertTrue(s.driver.cleanup_verified)
        self.assertTrue(s.driver.failure_audio_quiet_verified)
        self.assertEqual(s.audio.windows, before)
        self.assertEqual(proof['business_audio_windows_observed'], before)
        self.assertEqual(proof['android_tracks_after']['active_track_count'], 0)
        self.assertEqual(proof['android_tracks_after']['raw_sha256'], proof['audio_after']['sha256'])
        self.assertEqual((s.evidence_root / 'audio-flinger-failure-cleanup.txt').read_bytes(), raw())
        for key in ('host_audio_quiescence_qualified', 'continuous_exclusivity_qualified',
                    'inactive_audio_session_preservation_qualified', 'audio_focus_preservation_qualified',
                    'actual_full_dumpsys_ABI_qualified', 'runtime_qualified', 'whole_app_business_accepted'):
            self.assertIs(proof[key], False)

    def test_02_unknown_or_foreign_active_audio_preserves_raw_and_refuses_quiet(self):
        for name in ('foreign-input.txt', 'foreign-output.txt', 'camera.txt'):
            with self.subTest(name=name):
                s = self.make(name)
                with self.assertRaisesRegex(RuntimeError, 'UNEXPECTED_ACTIVE_ANDROID_AUDIO_TRACK'):
                    s.driver.finish()
                self.assertTrue(s.driver.cleanup_verified)
                self.assertFalse(s.driver.failure_audio_quiet_verified)
                self.assertFalse(s.audio.failure_cleanup_unknown)
                self.assertEqual((s.evidence_root / 'audio-flinger-failure-cleanup.txt').read_bytes(), raw(name))
        s = self.make(); s.reply = b'\n ## BEGIN thread dump \nUNKNOWN CURRENT ABI\n ## BEGIN setParameters dump \n'
        with self.assertRaises(RuntimeError):
            s.driver.finish()
        self.assertEqual((s.evidence_root / 'audio-flinger-failure-cleanup.txt').read_bytes(), s.reply)
        self.assertFalse(s.driver.failure_audio_quiet_verified)
        s = self.make(); s.reply = b'\xffINVALID_UTF8_AUDIO_DUMP'
        with self.assertRaises(UnicodeDecodeError):
            s.driver.finish()
        self.assertEqual((s.evidence_root / 'audio-flinger-failure-cleanup.txt').read_bytes(), s.reply)
        self.assertFalse(s.driver.failure_audio_quiet_verified)

    def test_03_incomplete_audio_preflight_has_zero_additional_query(self):
        for field in ('preflight_result', 'hardware_before'):
            with self.subTest(field=field):
                s = self.make(); setattr(s.audio, field, None)
                with self.assertRaisesRegex(RuntimeError, 'COMPLETE_AUDIO_PREFLIGHT'):
                    s.driver.finish()
                self.assert_no_sample(s)

    def test_04_host_or_decoder_unknown_has_zero_additional_query(self):
        for field in ('host', 'decoder'):
            with self.subTest(field=field):
                s = self.make()
                if field == 'host':
                    s.driver.host_unknown = True
                else:
                    s.driver.decoder = types.SimpleNamespace(unknown=True)
                with self.assertRaisesRegex(RuntimeError, 'KNOWN_TASK_AND_HOST_RETIREMENT'):
                    s.driver.finish()
                self.assert_no_sample(s)

    def test_05_pending_effect_or_remove_has_zero_additional_query(self):
        for field in ('pending', 'close_pending', 'recording'):
            with self.subTest(field=field):
                s = self.make()
                setattr(s.driver, field, types.SimpleNamespace(pending={'fixture': 'unknown'}) if field == 'recording' else {'fixture': 'unknown'})
                with self.assertRaisesRegex(RuntimeError, 'KNOWN_TASK_AND_HOST_RETIREMENT'):
                    s.driver.finish()
                self.assert_no_sample(s)

    def test_06_unfinished_acoustic_role_or_pending_reply_has_zero_query(self):
        for count in (1, 2, 4, 5):
            with self.subTest(prefix=count):
                s = self.make(); s.acoustic.results = {k: {'fixture': 'unfinished'} for k in CHANNEL.ORDER[:count]}; s.acoustic.sequence = count
                with self.assertRaisesRegex(RuntimeError, 'NO_PENDING_OR_UNFINISHED_ACOUSTIC'):
                    s.driver.finish()
                self.assert_no_sample(s)
        s = self.make(); s.acoustic.pending = {'kind': 'emit_finish', 'sent': True}
        with self.assertRaises(RuntimeError):
            s.driver.finish()
        self.assert_no_sample(s)

    def test_07_completed_acoustic_roles_require_exact_private_retirement_records(self):
        s = self.make(); s.acoustic.complete('emit'); s.acoustic.complete('listen')
        s.driver.finish()
        self.assertEqual(set(self.read_proof(s)['acoustic_retirement']), {'emit', 'listen'})
        for field, bad in [('leader_reaped', False), ('exit_code', True), ('pipe_eof', {'stdout': True, 'stderr': False}), ('parent', {'fixture': 'other-parent'})]:
            with self.subTest(field=field):
                s = self.make(); s.acoustic.complete('emit', {field: bad})
                with self.assertRaisesRegex(RuntimeError, 'ACTUAL_RETIRED_CURRENT_ACOUSTIC'):
                    s.driver.finish()
                self.assert_no_sample(s)

    def test_08_transport_failure_is_once_only_unknown_and_never_quiet(self):
        s = self.make(); s.transport_error = RuntimeError('FIXTURE_TRANSPORT_OUTCOME_UNKNOWN')
        with self.assertRaisesRegex(RuntimeError, 'FIXTURE_TRANSPORT_OUTCOME_UNKNOWN'):
            s.driver.finish()
        self.assertEqual(len(s.android_queries), 1)
        self.assertTrue(s.audio.failure_cleanup_attempted)
        self.assertTrue(s.audio.failure_cleanup_unknown)
        self.assertTrue(s.driver.host_unknown)
        self.assertFalse(s.driver.failure_audio_quiet_verified)
        with self.assertRaises(RuntimeError):
            s.driver.finish()
        self.assertEqual(len(s.android_queries), 1)

    def test_09_one_sample_authority_is_burned_even_after_known_nonquiet(self):
        s = self.make('foreign-input.txt')
        with self.assertRaises(RuntimeError):
            s.driver.finish()
        s.reply = raw()
        with self.assertRaisesRegex(RuntimeError, 'ONCE_FAILURE_PATH_AUDIO_SAMPLE_NO_RETRY'):
            s.driver.finish()
        self.assertEqual(len(s.android_queries), 1)
        self.assertFalse(s.driver.failure_audio_quiet_verified)

    def test_10_cleanup_budget_is_not_extended_for_a_sample(self):
        s = self.make(); s.phase_value['deadline_monotonic_ns'] = time.monotonic_ns() + 14000000000
        original = dict(s.phase_value)
        with self.assertRaisesRegex(RuntimeError, 'ORIGINAL_CLEANUP_BUDGET'):
            s.driver.finish()
        self.assertEqual(s.phase_value, original)
        self.assert_no_sample(s)

    def test_11_phase_caller_active_api_and_poison_gates_stay_closed(self):
        s = self.make()
        with self.assertRaisesRegex(RuntimeError, 'TYPED_API_NOT_CALLED'):
            s.audio.verify_failure_cleanup()
        self.assert_no_sample(s)
        for field in ('active_api', 'ordinary_admission', 'ui_dispatch_admission'):
            with self.subTest(field=field):
                s = self.make(); setattr(s, field, {'fixture': 'busy'})
                with self.assertRaisesRegex(RuntimeError, 'ONLY_CURRENT_FINAL_CLEANUP'):
                    s.driver.finish()
                self.assert_no_sample(s)
        s = self.make(); s.phase_name = 'business'
        with self.assertRaises(RuntimeError):
            s.driver.finish()
        self.assert_no_sample(s)
        s = self.make(); s.flow.poisoned = True
        with self.assertRaisesRegex(RuntimeError, 'HELD_TRANSPORT'):
            s.driver.finish()
        self.assert_no_sample(s)

    def test_12_post_sample_guard_failure_keeps_raw_without_success_receipt(self):
        s = self.make(); s.acoustic.fail_verify_at = 2
        with self.assertRaisesRegex(RuntimeError, 'PARENT_IDENTITY_CHANGED'):
            s.driver.finish()
        self.assertEqual(len(s.android_queries), 1)
        self.assertEqual((s.evidence_root / 'audio-flinger-failure-cleanup.txt').read_bytes(), raw())
        self.assertFalse(s.driver.failure_audio_quiet_verified)
        self.assertIsNone(s.driver.failure_audio_quiet_ref)

    def test_13_existing_success_window_gate_and_success_path_are_unchanged(self):
        s = self.make(); s.audio.windows = {'input': {'fixture': 'one window'}}
        with self.assertRaisesRegex(RuntimeError, 'BOTH_CURRENT_HAL_AUDIO_WINDOWS_REQUIRED'):
            s.audio.verify_final()
        self.assert_no_sample(s)
        s.driver.run_completed = True
        s.driver.finish()
        self.assertTrue(s.driver.cleanup_verified)
        self.assert_no_sample(s)

    def test_14_case_preserves_original_error_when_cleanup_sample_rejects(self):
        s = self.make('foreign-output.txt')
        result = self.execute_case(s, RuntimeError('ORIGINAL_BUSINESS_FAILURE'))
        self.assertEqual(result['error']['message'], 'ORIGINAL_BUSINESS_FAILURE')
        self.assertEqual(result['error']['stage'], 'current_camera_video_business')
        self.assertTrue(any('UNEXPECTED_ACTIVE_ANDROID_AUDIO_TRACK' in row['message'] for row in result['secondary_errors']))
        self.assertTrue(result['owned_task_cleanup_verified'])
        self.assertFalse(result['failure_path_android_audio_quiet_verified'])
        self.assertTrue(result['failure_path_android_audio_quiet_attempted'])
        self.assertFalse(result['case_business_success_verified'])
        self.assertFalse(result['runtime_qualified'])
        self.assertEqual((s.evidence_root / 'audio-flinger-failure-cleanup.txt').read_bytes(), raw('foreign-output.txt'))

    def test_15_quiet_sample_does_not_promote_failed_business(self):
        s = self.make(); result = self.execute_case(s, RuntimeError('ORIGINAL_BUSINESS_FAILURE'))
        self.assertTrue(result['failure_path_android_audio_quiet_verified'])
        self.assertEqual(result['error']['message'], 'ORIGINAL_BUSINESS_FAILURE')
        self.assertFalse(result['case_business_success_verified'])
        self.assertFalse(result['whole_app_business_accepted'])
        self.assertFalse(result['runtime_qualified'])
        self.assertEqual(result['state'], 'FAILED_OR_UNKNOWN_RETAINED')

    def test_16_case_preserves_unknown_without_new_query_or_qualification(self):
        s = self.make(); result = self.execute_case(s, DecodeUnknown('ORIGINAL_DECODE_UNKNOWN'))
        self.assert_no_sample(s)
        self.assertTrue(result['outcome_unknown'])
        self.assertFalse(result['failure_path_android_audio_quiet_verified'])
        self.assertFalse(result['case_business_success_verified'])
        self.assertEqual(result['error']['message'], 'ORIGINAL_DECODE_UNKNOWN')
        s = self.make(); s.transport_error = RuntimeError('FIXTURE_TRANSPORT_OUTCOME_UNKNOWN')
        result = self.execute_case(s, RuntimeError('ORIGINAL_BUSINESS_FAILURE'))
        self.assertTrue(result['failure_path_android_audio_quiet_outcome_unknown'])
        self.assertTrue(result['outcome_unknown'])
        self.assertFalse(result['failure_path_android_audio_quiet_verified'])
        self.assertEqual(result['error']['message'], 'ORIGINAL_BUSINESS_FAILURE')

    def test_17_complete_source_inventory_and_22_unchanged_production_files(self):
        self.assertEqual(set(SOURCE_ROWS), {'source/' + f.name for f in (ROOT / 'source').iterdir()})
        self.assertEqual(len(SOURCE_ROWS), 29)
        changed = set()
        for path, row in SOURCE_ROWS.items():
            data = (ROOT / path).read_bytes(); data.decode('utf-8'); compile(data, path, 'exec')
            self.assertEqual((len(data), hashlib.sha256(data).hexdigest()), (row['bytes'], row['sha256']))
            original = BASELINE_ROWS[path]
            if row['sha256'] != original['sha256']:
                changed.add(path)
            else:
                self.assertEqual((row['bytes'], row['sha256']), (original['bytes'], original['sha256']))
        self.assertEqual(changed, {'source/camera_audio_runtime.py', 'source/camera_video_driver.py',
            'source/camera_case.py', 'source/camera_decode.py', 'source/camera_video_state.py',
            'source/camera_audio_binding.py', 'source/camera_base_session.py'})
        expected_owner_merge = {
            'source/camera_decode.py': (16169, '7421cdd38bd45eff8c0697ce11b1372958a4a5f749c8097e3c0203ed5758056b'),
            'source/camera_video_state.py': (21072, '68c6369a068d822b0ea4e849cf2172d0180bbe69b3c576e7aa74ba2f6e7d66fc'),
        }
        for path, pin in expected_owner_merge.items():
            self.assertEqual((SOURCE_ROWS[path]['bytes'], SOURCE_ROWS[path]['sha256']), pin)

    def test_18_reviewed_credentials_preserve_declared_failure_cleanup_bodies(self):
        pins = json.loads((FIXTURES / 'original-ast-pins.json').read_bytes())
        # Keep the original fixture immutable. Only the two explicitly reviewed
        # credential successors use a new baseline for this structural check;
        # all behavioral failure-cleanup controls above continue to execute.
        successor = json.loads((FIXTURES / 'guest-credential-ast-pins.json').read_bytes())
        self.assertEqual(successor['schema'], 'pocket4-reviewed-guest-credential-ast-successor-v1')
        original_raw = (FIXTURES / 'original-ast-pins.json').read_bytes()
        self.assertEqual(successor['original_ast_fixture'], {
            'bytes': len(original_raw), 'sha256': hashlib.sha256(original_raw).hexdigest()})
        self.assertEqual(set(successor['files']), {'camera_audio_runtime.py', 'camera_video_driver.py'})
        for name, expected in successor['files'].items():
            raw_source = (ROOT / 'source' / name).read_bytes()
            self.assertEqual((len(raw_source), hashlib.sha256(raw_source).hexdigest()),
                             (expected['bytes'], expected['sha256']))
            pins[name] = expected
        for name, expected in pins.items():
            tree = ast.parse((ROOT / 'source' / name).read_text())
            if name == 'camera_audio_runtime.py':
                cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'AudioRuntime')
                cls.body = [n for n in cls.body if not isinstance(n, ast.FunctionDef) or n.name != 'verify_failure_cleanup']
                init = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
                removed = [n for n in init.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Attribute) and t.attr == 'failure_cleanup_attempted' for t in n.targets)]
                self.assertEqual(len(removed), 1); init.body.remove(removed[0])
            elif name == 'camera_video_driver.py':
                cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'Driver')
                init = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == '__init__')
                removed = [n for n in init.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Attribute) and t.attr in ('failure_audio_quiet_verified', 'failure_audio_quiet_ref') for t in n.targets)]
                self.assertEqual(len(removed), 2)
                for n in removed: init.body.remove(n)
                finish = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'finish')
                last = finish.body.pop(); self.assertIsInstance(last, ast.If)
                self.assertEqual(ast.dump(last.test), ast.dump(ast.parse('not self.run_completed', mode='eval').body))
            else:
                fields = {'failure_path_android_audio_quiet_verified', 'failure_path_android_audio_quiet_attempted', 'failure_path_android_audio_quiet_outcome_unknown', 'failure_path_android_audio_quiet_evidence'}
                removed_dict = removed_keywords = 0
                for node in ast.walk(tree):
                    if isinstance(node, ast.Dict):
                        kept = [(k, v) for k, v in zip(node.keys, node.values) if not isinstance(k, ast.Constant) or k.value not in fields]
                        removed_dict += len(node.keys) - len(kept); node.keys = [k for k, _ in kept]; node.values = [v for _, v in kept]
                    if isinstance(node, ast.Call):
                        kept = [k for k in node.keywords if k.arg not in fields]
                        removed_keywords += len(node.keywords) - len(kept); node.keywords = kept
                self.assertEqual((removed_dict, removed_keywords), (4, 4))
            self.assertEqual(hashlib.sha256(json.dumps(canonical_ast(tree), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest(), expected['normalized_ast_sha256'], name)


EXPECTED_TESTS = 18

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    start = time.monotonic()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(FailureCleanupControls))
    report = {'schema': 'pocket4-camera-failure-android-quiet-local-controls-v1',
              'tests': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
              'skips': len(result.skipped), 'passed': result.wasSuccessful() and result.testsRun == EXPECTED_TESTS and not result.skipped,
              'elapsed_seconds': time.monotonic() - start, 'executable': sys.executable, 'python': sys.version,
              'Main_actions': 0, 'Android_actions': 0, 'host_audio_actions': 0, 'subprocess_actions': 0,
              'actual_signal_actions': 0, 'runtime_qualified': False,
              'scope': 'actual Camera methods with fixture transport and pinned minimal C++ text projections; no actual device/runtime admission'}
    if args.report:
        with args.report.open('x', encoding='utf-8') as out:
            out.write(json.dumps(report, sort_keys=True, indent=2) + '\n')
    print(json.dumps(report, sort_keys=True))
    raise SystemExit(0 if report['passed'] else 1)
