"""Local raw-text controls; no Main, Android, host audio or proc access.

fixtures/origin.json describes the fixed-writer projections and their limits.
The fake session exercises the real AudioRuntime admission methods with actual
raw parser inputs; it supplies no physical or runtime qualification evidence.
"""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import runpy
import sys
import types
import unittest

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests' / 'fixtures'
B = types.SimpleNamespace(**runpy.run_path(str(ROOT / 'source' / 'camera_audio_binding.py')))
R = types.SimpleNamespace(**runpy.run_path(str(ROOT / 'source' / 'camera_audio_runtime.py')))
BEGIN = b'\n ## BEGIN thread dump \n'
END = b'\n ## BEGIN setParameters dump \n'


def raw(name):
    return (FIXTURES / name).read_bytes()


def change(data, old, new):
    if data.count(old) != 1:
        raise AssertionError(('fixture mutation must be exact', old, data.count(old)))
    return data.replace(old, new, 1)


def parsed(name):
    return B.flinger(raw(name))


class RawAdmission(unittest.TestCase):
    def refused(self, data):
        with self.assertRaises(RuntimeError):
            B.flinger(data)

    def test_01_raw_fixture_digests_and_explicit_scope(self):
        origin = json.loads((FIXTURES / 'origin.json').read_bytes())
        self.assertEqual(origin['framework_commit'], B.FRAMEWORK_COMMIT)
        self.assertFalse(origin['runtime_qualified'])
        self.assertEqual(set(origin['files']), {p.name for p in FIXTURES.glob('*.txt')})
        for name, ref in origin['files'].items():
            with self.subTest(name=name):
                self.assertEqual(len(raw(name)), ref['bytes'])
                self.assertEqual(hashlib.sha256(raw(name)).hexdigest(), ref['sha256'])

    def test_02_empty_current_tables_have_positive_thread_witnesses(self):
        value = parsed('idle.txt')
        proof = B.quiescent(value)
        self.assertEqual(proof['observed_threads'], 2)
        self.assertEqual(proof['active_track_count'], 0)
        self.assertEqual(proof['raw_sha256'], hashlib.sha256(raw('idle.txt')).hexdigest())
        self.assertFalse(proof['host_audio_quiescence_qualified'])
        self.assertFalse(proof['continuous_exclusivity_qualified'])
        self.assertFalse(proof['runtime_qualified'])

    def test_03_inactive_foreign_tracks_remain_visible(self):
        value = parsed('inactive-foreign.txt')
        self.assertEqual({r['uid'] for t in value['threads'] for r in t['tracks']}, {10998, 10999})
        self.assertEqual(B.quiescent(value)['active_track_count'], 0)

    def test_04_foreign_active_capture_refuses_quiescence(self):
        with self.assertRaisesRegex(RuntimeError, 'UNEXPECTED_ACTIVE_ANDROID_AUDIO_TRACK'):
            B.quiescent(parsed('foreign-input.txt'))

    def test_05_foreign_active_playback_refuses_quiescence(self):
        with self.assertRaisesRegex(RuntimeError, 'UNEXPECTED_ACTIVE_ANDROID_AUDIO_TRACK'):
            B.quiescent(parsed('foreign-output.txt'))

    def test_06_only_owned_capture_is_admitted_in_capture_sample(self):
        value = parsed('camera.txt')
        selected = B.owned_track(value, direction='Input', uid=10062, pid=2001)
        self.assertEqual((selected['track']['uid'], selected['track']['pid'], selected['track']['source']), (10062, 2001, 5))
        with self.assertRaises(RuntimeError):
            B.quiescent(value)

    def test_07_only_owned_playback_is_admitted_in_playback_sample(self):
        value = parsed('gallery.txt')
        selected = B.owned_track(value, direction='Output', uid=10064, pid=2002)
        self.assertEqual((selected['track']['uid'], selected['track']['pid'], selected['track']['stream']), (10064, 2002, 3))

    def test_08_cross_direction_foreign_activity_refuses_owned_window(self):
        for name, direction, uid, pid in [('camera-foreign-output.txt', 'Input', 10062, 2001),
                                         ('gallery-foreign-input.txt', 'Output', 10064, 2002)]:
            with self.subTest(name=name), self.assertRaisesRegex(RuntimeError, 'ONE_EXCLUSIVE_CURRENT_APP'):
                B.owned_track(parsed(name), direction=direction, uid=uid, pid=pid)

    def test_09_second_capture_uid_refuses_owned_window(self):
        with self.assertRaisesRegex(RuntimeError, 'ONE_EXCLUSIVE_CURRENT_APP'):
            B.owned_track(parsed('camera-second-input.txt'), direction='Input', uid=10062, pid=2001)

    def test_10_same_uid_other_process_is_not_owned(self):
        value = B.flinger(change(raw('camera-second-input.txt'), b'  10999', b'  10062'))
        with self.assertRaisesRegex(RuntimeError, 'ONE_EXCLUSIVE_CURRENT_APP'):
            B.owned_track(value, direction='Input', uid=10062, pid=2001)
        with self.assertRaisesRegex(RuntimeError, 'ONE_EXCLUSIVE_CURRENT_APP'):
            B.owned_track(parsed('camera.txt'), direction='Input', uid=10062, pid=2999)

    def test_11_zero_or_unknown_thread_matches_never_grant_idle(self):
        for body in (b'', b'UNRECOGNIZED CURRENT THREAD GRAMMAR\n', b'Input thread 0x2000, truncated\n'):
            with self.subTest(body=body):
                self.refused(BEGIN + body + END)

    def test_12_bad_header_before_between_or_after_valid_threads_refuses(self):
        data = raw('idle.txt')
        bad = b'Input thread 0x3000, truncated before tid/type\n'
        for mutated in (change(data, BEGIN, BEGIN + bad),
                        change(data, b'\nInput thread', b'\n' + bad + b'Input thread'),
                        change(data, END, bad + END)):
            with self.subTest(data=mutated):
                self.refused(mutated)

    def test_13_indented_or_unknown_direction_header_refuses(self):
        data = raw('idle.txt')
        self.refused(change(data, b'Input thread', b'  Input thread'))
        self.refused(change(data, b'Input thread', b'Capture thread'))

    def test_14_unknown_and_unsupported_kinds_refuse_even_zero_tracks(self):
        for kind in (b'unknown', b'MMAP_CAPTURE', b'UNSEEN'):
            with self.subTest(kind=kind):
                self.refused(change(raw('idle.txt'), b'(RECORD)', b'(' + kind + b')'))
        for kind in (b'MMAP_PLAYBACK', b'BIT_PERFECT'):
            with self.subTest(kind=kind):
                self.refused(change(raw('idle.txt'), b'(MIXER)', b'(' + kind + b')'))

    def test_15_thread_direction_and_pinned_kind_must_agree(self):
        self.refused(change(raw('idle.txt'), b'(RECORD)', b'(MIXER)'))
        self.refused(change(raw('idle.txt'), b'(MIXER)', b'(RECORD)'))

    def test_16_unknown_unindented_hal_or_scheduler_output_refuses(self):
        self.refused(change(raw('idle.txt'), b'  Frames read:', b'UNQUALIFIED HAL DIAGNOSTIC\n  Frames read:'))
        self.refused(change(raw('idle.txt'), END, b'unqualified scheduler output\n' + END))

    def test_17_orphan_effect_chain_section_refuses(self):
        self.refused(change(raw('idle.txt'), END, b'  Orphan Effect Chains\n' + END))

    def test_18_markers_must_be_unique_exact_and_in_order(self):
        self.refused(END + raw('idle.txt'))
        self.refused(change(raw('idle.txt'), BEGIN, BEGIN + BEGIN))
        self.refused(END + BEGIN)
        self.refused(change(raw('idle.txt'), BEGIN, b' ## BEGIN thread dump '))

    def test_19_each_current_thread_requires_its_exact_end(self):
        data = raw('idle.txt')
        self.refused(data.replace(b'  Local log:\n', b'', 1))
        self.refused(data.replace(b'  Local log:\n', b'  Local log: truncated\n', 1))

    def test_20_full_active_row_count_and_table_consistency_are_required(self):
        data = raw('camera.txt')
        for old, new in [(b'1 Tracks of which 1 are active', b'1 Tracks of which 0 are active'),
                         (b'1 Tracks of which 1 are active', b'2 Tracks of which 1 are active'),
                         (b'  10062', b'  unparsed_uid')]:
            with self.subTest(old=old, new=new):
                self.refused(change(data, old, new))
        self.refused(change(data, b'  1 Tracks of which 1 are active\n',
            b'  The following tracks are in the active list but not in the track list\n  1 Tracks of which 1 are active\n'))

    def test_21_historical_rows_cannot_supply_or_hide_current_activity(self):
        old_threads = raw('foreign-input.txt').split(BEGIN, 1)[1].split(END, 1)[0]
        historical = b'Historical Thread Log \n' + b''.join(b'- ' + line + b'\n' for line in old_threads.splitlines())
        value = B.flinger(change(raw('idle.txt'), END, historical + END))
        self.assertTrue(value['historical_thread_log_excluded'])
        self.assertEqual(B.quiescent(value)['active_track_count'], 0)
        self.refused(BEGIN + historical + END)
        self.refused(change(raw('idle.txt'), b'Input thread', b'Historical Thread Log \nInput thread'))

    def test_22_matching_frame_progress_and_both_exclusive_samples_required(self):
        for first, second, direction, uid, pid in [('camera.txt', 'camera-next.txt', 'Input', 10062, 2001),
                                                 ('gallery.txt', 'gallery-next.txt', 'Output', 10064, 2002)]:
            with self.subTest(first=first):
                value = B.advancing(parsed(first), parsed(second), direction=direction, uid=uid, pid=pid, elapsed_ns=200_000_000)
                self.assertEqual(value['track_frames_advanced'], 960)
                self.assertFalse(value['runtime_qualified'])
        for first, second in [('camera-foreign-output.txt', 'camera-next.txt'),
                              ('camera.txt', 'camera-foreign-output.txt')]:
            with self.subTest(first=first, second=second), self.assertRaisesRegex(RuntimeError, 'ONE_EXCLUSIVE_CURRENT_APP'):
                B.advancing(parsed(first), parsed(second), direction='Input', uid=10062, pid=2001, elapsed_ns=200_000_000)

    def test_23_live_dump_failures_and_bounds_still_refuse(self):
        for data in (b'', b'x' * 1048577, b'\xff' + raw('idle.txt'),
                     b'Permission Denial\n' + raw('idle.txt'), b'Thread may be deadlocked\n' + raw('idle.txt')):
            with self.subTest(size=len(data)), self.assertRaises((RuntimeError, UnicodeError)):
                B.flinger(data)


class FakeTransaction:
    def __init__(self):
        self.writes = {}

    def write_new(self, path, data):
        if path.name in self.writes:
            raise AssertionError('duplicate fixture evidence write')
        self.writes[path.name] = data
        return {'path': str(path), 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


class FakeHandle:
    def __init__(self, pid):
        self.identity = {'namespace_pids': [pid], 'host_pid': pid}
        self.stale = False
        self.verifies = 0

    def verify(self):
        self.verifies += 1
        if self.stale:
            raise RuntimeError('STALE_HELD_FIXTURE_PROCESS')


class FakeSession:
    def __init__(self, data):
        self.components = {'camera_audio_binding.py': B}
        self.tx = FakeTransaction()
        self.evidence_root = Path('/fixture-only-no-files-written')
        self.records = {}
        self.android_calls = []
        self.guards = 0
        self.guard_failure_at = None
        self.data = data
        self.phase_ref = {'fixture': 'phase'}
        self.hal_bytes = b'fixture HAL bytes, not a physical artifact'
        self.refs = {}

        def ref(name, value):
            blob = json.dumps(value, sort_keys=True).encode() if type(value) is dict else value
            path = '/fixture/' + name
            self.refs[path] = blob
            return {'path': path, 'bytes': len(blob), 'sha256': hashlib.sha256(blob).hexdigest()}

        hal_ref = ref('hal', self.hal_bytes)
        apex = {'state': 'AUDIO_APEX_QUALIFIED_PENDING_FORMAL_RUNTIME', 'artifact_qualified': True,
                'runtime_qualified': False, 'payload_files': {R.HAL_MEMBER: {'reference': hal_ref}}}
        self.apex = apex
        proof_ref = ref('apex.json', apex)
        files = {p: ref('helper-' + role, ('fixture ' + role).encode()) for role, p in R.HELPERS.items()}
        packet = {'schema': 'pocket4-audio-complete-source-qualification-v1', 'state': 'ACTUAL_SOURCE_QUALIFIED_RUNTIME_PENDING',
                  'runtime_qualified': False, 'candidate_deployed': False, 'original45_whole_app_accepted': 0,
                  'qualified': {k: True for k in R.FLAGS}, 'evidence': {'apex_qualification': proof_ref}, 'files': files}
        life = {'schema': 'pocket4-final-audio-lifecycle-v1', 'helper_paths': {R.UNITS[k]: v for k, v in R.HELPERS.items()},
                'peer_uid': 1041, 'peer_gid': 1041, 'socket_gid': 1041,
                'peer_cgroup': '/system.slice/droidloomd.service',
                'guest_endpoints': ['/dev/socket/droidloom/audio', '/dev/socket/droidloom/audio-input'],
                'source_qualification': ref('packet.json', packet)}
        payload = []
        for p, source in files.items():
            self.refs[p] = self.refs[source['path']]
            payload.append({'install_target': p, 'bytes': source['bytes'], 'sha256': source['sha256']})
        self.baseline = types.SimpleNamespace(docs={'deployment_manifest': {'audio_lifecycle': life, 'payload': payload}})
        self.c = types.SimpleNamespace(parse=json.loads, read_ref=self.read_ref, sha=lambda b: hashlib.sha256(b).hexdigest())
        self.flow = types.SimpleNamespace(scope_ref={'fixture': 'scope'}, view=types.SimpleNamespace(
            target=types.SimpleNamespace(read_file=self.read_hal)))

    def read_ref(self, ref, maximum=33554432):
        blob = self.refs[ref['path']]
        if len(blob) > maximum or len(blob) != ref['bytes'] or hashlib.sha256(blob).hexdigest() != ref['sha256']:
            raise AssertionError('fixture reference mismatch')
        return blob

    def read_hal(self, path, maximum, single_link):
        if (path, maximum, single_link) != (R.HAL, 33554432, True):
            raise AssertionError('unexpected file access')
        return self.hal_bytes, {'fixture': 'hal file identity'}

    def guard(self):
        self.guards += 1
        if self.guards == self.guard_failure_at:
            raise RuntimeError('FIXTURE_MAIN_GENERATION_CHANGED')

    def android(self, argv, timeout):
        if (argv, timeout) != (['/system/bin/dumpsys', 'media.audio_flinger'], 15):
            raise AssertionError('unexpected Android operation')
        self.android_calls.append((list(argv), timeout))
        return self.data

    def host_read(self, *args):
        raise AssertionError('no actual or unmodeled host operation permitted')

    def record(self, label, value):
        if label in self.records:
            raise AssertionError('duplicate fixture record')
        self.records[label] = copy.deepcopy(value)
        return {'fixture_record': label}


class FixtureCredentials:
    """Explicit identity namespace for these synthetic quiescence fixtures."""
    receipt = {'fixture_only': True, 'uid_map': 'identity', 'gid_map': 'identity'}

    def observer_id(self, kind, guest_id):
        if kind not in ('uid', 'gid') or type(guest_id) is not int or not 0 <= guest_id < 4294967295:
            raise AssertionError('invalid synthetic credential request')
        return guest_id


class FakeRuntime(R.AudioRuntime):
    def __init__(self, session):
        super().__init__(session)
        self.hardware_calls = []
        self.bind_calls = []
        self.helper_calls = []
        self.fixture_credentials = FixtureCredentials()

    def credentials(self):
        return self.fixture_credentials

    def hardware(self, label):
        self.hardware_calls.append(label)
        return {role: {'current': {'fixture_route': role}, 'properties': {'fixture': 'unchanged'}} for role in ('input', 'output')}

    def bind_guest(self, key, uid, guest_pid=None):
        self.bind_calls.append((key, uid, guest_pid))
        self.handles[key] = FakeHandle(guest_pid if guest_pid is not None else 1041)
        return self.handles[key]

    def helper(self, role):
        self.helper_calls.append(role)
        self.units[role] = {'value': {'fixture_helper': role}}
        return self.units[role]['value']


class RuntimeAdmission(unittest.TestCase):
    def make(self, name, admitted=False):
        session = FakeSession(raw(name))
        runtime = FakeRuntime(session)
        if admitted:
            runtime.preflight_result = {'fixture': 'previous admission'}
            runtime.hardware_before = runtime.hardware('before')
        return session, runtime

    def test_24_preflight_rejects_foreign_uid_and_keeps_raw_without_admission(self):
        for name in ('foreign-input.txt', 'foreign-output.txt'):
            with self.subTest(name=name):
                s, runtime = self.make(name)
                with self.assertRaisesRegex(RuntimeError, 'UNEXPECTED_ACTIVE_ANDROID_AUDIO_TRACK'):
                    runtime.preflight()
                self.assertIsNone(runtime.preflight_result)
                self.assertEqual(s.records, {})
                self.assertEqual(s.tx.writes, {'audio-flinger-before.txt': raw(name)})
                self.assertEqual(len(s.android_calls), 1)

    def test_25_preflight_has_scoped_raw_bound_evidence_and_no_runtime_claim(self):
        s, runtime = self.make('idle.txt')
        runtime.preflight()
        proof = s.records['current-audio-source-admission']
        self.assertEqual(proof['android_tracks_before']['raw_sha256'], proof['audio_before']['sha256'])
        self.assertLessEqual(proof['started_monotonic_ns'], proof['finished_monotonic_ns'])
        self.assertFalse(proof['runtime_qualified'])
        self.assertNotIn('no_preexisting_camera_or_gallery_audio_tracks', proof)
        self.assertEqual(len(s.android_calls), 1)

    def test_26_existing_source_and_main_generation_gates_remain_required(self):
        s, runtime = self.make('idle.txt')
        s.baseline.docs['deployment_manifest']['audio_lifecycle']['peer_uid'] = 1000
        with self.assertRaisesRegex(RuntimeError, 'EXACT_DEPLOYED_AUDIO_APEX'):
            runtime.preflight()
        self.assertEqual(s.android_calls, [])
        s, runtime = self.make('idle.txt')
        s.guard_failure_at = 1
        with self.assertRaisesRegex(RuntimeError, 'FIXTURE_MAIN_GENERATION_CHANGED'):
            runtime.preflight()
        self.assertEqual(s.tx.writes, {})

    def test_27_snapshot_refuses_foreign_activity_before_any_guest_adoption(self):
        for name, role in [('camera-foreign-output.txt', 'input'), ('gallery-foreign-input.txt', 'output')]:
            with self.subTest(name=name):
                s, runtime = self.make(name, admitted=True)
                with self.assertRaisesRegex(RuntimeError, 'ONE_EXCLUSIVE_CURRENT_APP'):
                    runtime.snapshot(role, 'current')
                self.assertEqual(runtime.bind_calls, [])
                self.assertEqual(runtime.helper_calls, [])
                self.assertEqual(s.records, {})
                self.assertEqual(s.tx.writes, {'current-flinger.txt': raw(name)})

    def test_28_snapshot_retains_held_app_hal_checks_and_scoped_receipt(self):
        s, runtime = self.make('camera.txt', admitted=True)
        proof = runtime.snapshot('input', 'current')
        self.assertEqual(runtime.bind_calls, [('camera', 10062, 2001), ('hal', 1041, None)])
        self.assertEqual(runtime.handles['camera'].verifies, 1)
        self.assertEqual(runtime.handles['hal'].verifies, 1)
        self.assertFalse(proof['host_audio_quiescence_qualified'])
        self.assertFalse(proof['continuous_exclusivity_qualified'])
        self.assertFalse(proof['runtime_qualified'])
        s, runtime = self.make('camera.txt', admitted=True)
        runtime.handles['camera'] = FakeHandle(2001)
        runtime.handles['camera'].stale = True
        with self.assertRaisesRegex(RuntimeError, 'STALE_HELD_FIXTURE_PROCESS'):
            runtime.snapshot('input', 'stale')
        self.assertEqual(s.records, {})
        self.assertEqual(runtime.helper_calls, [])

    def test_29_final_rejects_other_uid_and_preserves_failure_dump(self):
        s, runtime = self.make('foreign-output.txt', admitted=True)
        runtime.windows = {'input': {'fixture': 1}, 'output': {'fixture': 2}}
        with self.assertRaisesRegex(RuntimeError, 'UNEXPECTED_ACTIVE_ANDROID_AUDIO_TRACK'):
            runtime.verify_final()
        self.assertEqual(s.records, {})
        self.assertEqual(runtime.hardware_calls, ['before'])
        self.assertEqual(s.tx.writes, {'audio-flinger-after.txt': raw('foreign-output.txt')})

    def test_30_final_has_all_uid_and_raw_receipt_but_no_host_or_runtime_qualification(self):
        s, runtime = self.make('idle.txt', admitted=True)
        runtime.windows = {'input': {'fixture': 1}, 'output': {'fixture': 2}}
        runtime.verify_final()
        proof = s.records['audio-final']
        self.assertEqual(proof['android_tracks_after']['active_track_count'], 0)
        self.assertEqual(proof['android_tracks_after']['raw_sha256'], proof['audio_after']['sha256'])
        self.assertFalse(proof['android_tracks_after']['host_audio_quiescence_qualified'])
        self.assertEqual((proof['settings_writes'], proof['application_processes_signalled']), (0, 0))
        self.assertFalse(proof['runtime_qualified'])
        self.assertEqual(len(s.android_calls), 1)
        self.assertEqual(s.guards, 2)

    def test_31_unknown_grammar_is_saved_then_refused_by_runtime(self):
        s, runtime = self.make('idle.txt')
        s.data = BEGIN + b'UNRECOGNIZED CURRENT THREAD GRAMMAR\n' + END
        with self.assertRaisesRegex(RuntimeError, 'COMPLETE_NONEMPTY_CURRENT_AUDIO_THREAD_SET'):
            runtime.preflight()
        self.assertEqual(s.tx.writes['audio-flinger-before.txt'], s.data)
        self.assertIsNone(runtime.preflight_result)
        self.assertEqual(s.records, {})


EXPECTED_TESTS = 31


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    successful = result.wasSuccessful() and result.testsRun == EXPECTED_TESTS and not result.skipped and not result.expectedFailures
    report = {'schema': 'local-camera-audio-quiescence-controls-v1', 'expected_tests': EXPECTED_TESTS,
        'tests_run': result.testsRun, 'skipped': len(result.skipped), 'expected_failures': len(result.expectedFailures),
        'unexpected_successes': len(result.unexpectedSuccesses),
        'failures': [(t.id(), e) for t, e in result.failures], 'errors': [(t.id(), e) for t, e in result.errors],
        'passed': successful, 'raw_fixtures': 'fixed C++ writer projections; not observed runtime dumps',
        'Main_accesses': 0, 'Android_executions': 0, 'host_audio_operations': 0,
        'runtime_qualified': False, 'physical_audio_qualified': False, 'host_audio_quiescence_qualified': False,
        'source_sha256': {name: hashlib.sha256((ROOT / 'source' / name).read_bytes()).hexdigest()
                          for name in ('camera_audio_binding.py', 'camera_audio_runtime.py')}}
    if args.report:
        with args.report.open('x') as output:
            json.dump(report, output, indent=2)
            output.write('\n')
    print(json.dumps(report, sort_keys=True))
    return 0 if successful else 1


if __name__ == '__main__':
    raise SystemExit(main())
