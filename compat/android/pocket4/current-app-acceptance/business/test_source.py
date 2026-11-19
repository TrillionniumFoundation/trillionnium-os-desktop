"""Host tests only: no Android, ADB, account, APK installation or network."""
from pathlib import Path
import ast
import copy
import hashlib
import json
import types
import unittest

ROOT = Path(__file__).resolve().parent
MANIFEST = json.loads((ROOT / 'manifest.json').read_text())

def load(name, raw=None):
    path = ROOT / 'source' / name
    raw = path.read_bytes() if raw is None else raw
    mod = types.ModuleType(name.replace('.', '_'))
    mod.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), mod.__dict__)
    return mod

class CurrentIHGIdentity(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.common = load('app_common.py')
        cls.profile = load('app_profiles.py')
        cls.artifacts = load('ihg_artifacts.py')
        old = (ROOT / 'source/app_profiles.py').read_text()
        for before, after in reversed(MANIFEST['literal_changes']['app_profiles.py']):
            old = old.replace(after, before, 1)
        cls.old_raw = old.encode()
        cls.old = load('app_profiles.py', cls.old_raw)
        cls.current = b'package:com.ihg.apps.android versionCode:50023496 uid:10137\n'
        cls.old_meta = b'package:com.ihg.apps.android versionCode:50023219 uid:10137\n'
        cls.record = [{'bytes': MANIFEST['official_candidate']['bytes'],
            'sha256': MANIFEST['official_candidate']['sha256'],
            'held_file': {'fixture': 'host-only'},
            'stat_file': {'fixture': 'host-only', 'ctime_ns': 0}}]
        cls.target = {'package': 'com.ihg.apps.android', 'uid': 10137,
                      'user': 0, 'version_code': 50023496}

    def test_complete_source_inventory(self):
        rows = MANIFEST['sources']
        self.assertEqual(len(rows), 31)
        self.assertEqual({r['path'] for r in rows},
                         {str(p.relative_to(ROOT)) for p in (ROOT / 'source').iterdir()})
        for row in rows:
            p = ROOT / row['path']
            self.assertFalse(p.is_symlink())
            raw = p.read_bytes()
            self.assertEqual(len(raw), row['bytes'])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), row['sha256'])
            ast.parse(raw, filename=row['path'])

    def test_28_unchanged_files_and_recorded_identity_and_timer_changes(self):
        changed = []
        for row in MANIFEST['sources']:
            raw = (ROOT / row['path']).read_bytes()
            original = MANIFEST['original_sources'][Path(row['path']).name]
            if hashlib.sha256(raw).hexdigest() != original['sha256']:
                changed.append(Path(row['path']).name)
                text = raw.decode()
                for before, after in reversed(MANIFEST['literal_changes'][changed[-1]]):
                    self.assertEqual(text.count(after), 1)
                    text = text.replace(after, before, 1)
                self.assertEqual(hashlib.sha256(text.encode()).hexdigest(), original['sha256'])
                self.assertEqual(len(text.encode()), original['bytes'])
        self.assertEqual(changed, ['app_profiles.py', 'ihg_artifacts.py', 'timer_flow.py'])
        self.assertEqual(sum(map(len, MANIFEST['literal_changes'].values())), 7)

    def test_current_metadata(self):
        self.assertEqual(self.common.package_metadata(self.current, self.profile.IHG), self.target)

    def test_reproduced_old_metadata_guard_failure(self):
        with self.assertRaises(RuntimeError):
            self.common.package_metadata(self.current, self.old.IHG)

    def test_old_and_future_versions_rejected(self):
        for raw in [self.old_meta, self.current.replace(b'50023496', b'50023497')]:
            with self.assertRaises(RuntimeError):
                self.common.package_metadata(raw, self.profile.IHG)

    def test_wrong_uid_rejected(self):
        with self.assertRaises(RuntimeError):
            self.common.package_metadata(self.current.replace(b'10137', b'10138'), self.profile.IHG)

    def test_current_official_artifact(self):
        self.common.validate_artifacts(self.record, self.profile.IHG)

    def test_reproduced_old_artifact_guard_failure(self):
        with self.assertRaises(RuntimeError):
            self.common.validate_artifacts(self.record, self.old.IHG)

    def test_changed_hash_and_size_rejected(self):
        for key, value in [('sha256', '0' * 64), ('bytes', self.record[0]['bytes'] + 1)]:
            altered = copy.deepcopy(self.record)
            altered[0][key] = value
            with self.assertRaises(RuntimeError):
                self.common.validate_artifacts(altered, self.profile.IHG)

    def test_missing_or_extra_apk_rejected(self):
        for rows in [[], self.record * 2]:
            with self.assertRaises(RuntimeError):
                self.common.validate_artifacts(rows, self.profile.IHG)

    def test_artifact_guard_current_identity(self):
        self.artifacts.ArtifactSet(None, {'target': self.target}, None)

    def test_artifact_guard_old_identity_rejected(self):
        with self.assertRaises(RuntimeError):
            self.artifacts.ArtifactSet(None, {'target': {**self.target, 'version_code': 50023219}}, None)

    def test_existing_limits_and_clock_profiles_preserved(self):
        for name in ['CLOCK', 'CLOCK_HELPER', 'CLOCK_LIMITS', 'IHG_LIMITS']:
            self.assertEqual(getattr(self.profile, name), getattr(self.old, name))

    def test_ihg_other_identity_fields_preserved(self):
        self.assertEqual({k: v for k, v in self.profile.IHG.items() if k not in ('version_code', 'apks')},
                         {k: v for k, v in self.old.IHG.items() if k not in ('version_code', 'apks')})

    def test_no_runtime_acceptance_is_claimed(self):
        result = json.loads((ROOT / 'host-result.json').read_text())
        for key in ['runtime_qualified', 'production_ready', 'canonical_selection_changed']:
            self.assertIs(result[key], False)
        for key in ['runtime_accepted', 'Android_actions', 'apps_installed']:
            self.assertEqual(result[key], 0)


class TimerCreationReadback(unittest.TestCase):
    """Synthetic timer-model observations; no transport or Android commands."""

    class Clock:
        def __init__(self):
            self.now = 100.0
            self.sleeps = []

        def monotonic(self):
            return self.now

        def sleep(self, seconds):
            self.sleeps.append(seconds)
            self.now += seconds

    @staticmethod
    def empty():
        return {'ids': [], 'timers': [], 'values': {}, 'stopwatch': {}}

    @staticmethod
    def running():
        return {'ids': [7], 'timers': [{'id': 7, 'state': 1,
            'length_ms': 900000, 'total_length_ms': 900000,
            'last_start_ms': 10000, 'last_wall_ms': 1700000000000,
            'remaining_ms': 899900, 'label': None, 'delete_after_use': False}],
            'values': {}, 'stopwatch': {}}

    def fixture(self, observations, *, old=False, budget=10.0,
                read_seconds=0, uptime_seconds=0):
        raw = (ROOT / 'source/timer_flow.py').read_bytes()
        if old:
            text = raw.decode()
            for before, after in reversed(MANIFEST['literal_changes']['timer_flow.py']):
                self.assertEqual(text.count(after), 1)
                text = text.replace(after, before, 1)
            raw = text.encode()
            self.assertEqual(hashlib.sha256(raw).hexdigest(),
                             MANIFEST['original_sources']['timer_flow.py']['sha256'])
        module = load('timer_flow.py', raw)
        model = load('clock_preservation.py')
        clock = self.Clock()
        module.time = types.SimpleNamespace(monotonic=clock.monotonic, sleep=clock.sleep)
        queued = copy.deepcopy(observations)
        reads, records, schedules = [], [], []
        def read(session):
            reads.append(session)
            clock.now += read_seconds
            value = queued.pop(0)
            if isinstance(value, BaseException):
                raise value
            return value
        def forbid_input(request):
            raise AssertionError('creation readback replayed an input')
        continuation = types.SimpleNamespace(actions=1, pending=None, step=forbid_input)
        trial = types.SimpleNamespace(s=object(), owned=(23, set()),
            record=lambda name, value: records.append((name, copy.deepcopy(value))))
        flow = module.TimerFlow(trial, None, types.SimpleNamespace(read=read,
            empty=model.empty, owned=model.owned), {'phases': {'before': self.empty()}},
            ROOT, lambda t, p: continuation)
        flow.deadline = clock.now + budget
        flow.creation_dispatch_before = 0
        flow.creation_uptime_before = 10000
        flow.effect_pending = {'operation': 'create', 'native_request_id': 't05-create-start',
            'timer_id': None, 'duration_ms': 900000, 'automatic_retry': False}
        def uptime():
            clock.now += uptime_seconds
            return 11000
        flow.uptime = uptime
        flow.observe_scheduler = schedules.append
        return types.SimpleNamespace(flow=flow, clock=clock, queued=queued,
            reads=reads, records=records, schedules=schedules)

    def assert_pending(self, fixture, reads):
        self.assertEqual(len(fixture.reads), reads)
        self.assertIsNone(fixture.flow.timer_id)
        self.assertEqual(fixture.flow.effect_pending['operation'], 'create')
        self.assertEqual(fixture.flow.c.actions, 1)
        self.assertNotIn('created-running', fixture.flow.r['phases'])
        self.assertEqual(fixture.schedules, [])

    def test_original_rejects_empty_before_delayed_running(self):
        fixture = self.fixture([self.empty(), self.running()], old=True)
        with self.assertRaisesRegex(RuntimeError, '^ONE_NEW_TIMER_REQUIRED$'):
            fixture.flow.claim_created()
        self.assert_pending(fixture, 1)
        self.assertEqual(len(fixture.queued), 1)
        self.assertEqual(fixture.clock.sleeps, [])

    def test_immediate_running_needs_no_wait(self):
        fixture = self.fixture([self.running()])
        fixture.flow.claim_created()
        self.assertEqual(len(fixture.reads), 1)
        self.assertEqual(fixture.clock.sleeps, [])
        self.assertEqual(fixture.flow.timer_id, 7)
        self.assertIsNone(fixture.flow.effect_pending)
        self.assertEqual(fixture.flow.c.actions, 1)
        self.assertEqual(fixture.schedules, ['created-running'])

    def test_delayed_persistence_converges_without_replaying_start(self):
        for empty_reads in (1, 2):
            with self.subTest(empty_reads=empty_reads):
                fixture = self.fixture([self.empty()] * empty_reads + [self.running()])
                fixture.flow.claim_created()
                self.assertEqual(len(fixture.reads), empty_reads + 1)
                self.assertEqual(fixture.clock.sleeps, [.25] * empty_reads)
                self.assertEqual(fixture.flow.timer_id, 7)
                self.assertIsNone(fixture.flow.effect_pending)
                self.assertEqual(fixture.flow.c.actions, 1)
                self.assertEqual(fixture.schedules, ['created-running'])
                self.assertEqual(fixture.flow.r['phases']['created-running'], self.running())

    def test_three_empty_reads_retain_pending_and_block_cleanup_inputs(self):
        fixture = self.fixture([self.empty()] * 3 + [self.running()])
        with self.assertRaisesRegex(RuntimeError, '^ACKNOWLEDGED_TIMER_CREATE_NOT_READ_BACK$'):
            fixture.flow.claim_created()
        self.assert_pending(fixture, 3)
        self.assertEqual(fixture.clock.sleeps, [.25, .25])
        self.assertEqual(len(fixture.queued), 1)
        fixture.flow.cleanup(fixture.clock.now + 35)
        self.assert_pending(fixture, 3)
        self.assertEqual(fixture.flow.r['cleanup']['new_inputs'], 0)

    def test_original_deadline_is_checked_before_and_after_reads(self):
        cases = [
            {'budget': 0, 'expected_reads': 0},
            {'budget': .1, 'expected_reads': 1, 'empty_first': True},
            {'budget': .1, 'read_seconds': .2, 'expected_reads': 1},
            {'budget': .1, 'uptime_seconds': .2, 'expected_reads': 1},
        ]
        for case in cases:
            with self.subTest(case=case):
                options = dict(case)
                expected = options.pop('expected_reads')
                first = self.empty() if options.pop('empty_first', False) else self.running()
                fixture = self.fixture([first, self.running()], **options)
                with self.assertRaisesRegex(RuntimeError, '^TIMER_CREATION_READBACK_DEADLINE$'):
                    fixture.flow.claim_created()
                self.assert_pending(fixture, expected)
                self.assertLessEqual(sum(fixture.clock.sleeps), case['budget'] + 1e-12)

    def test_invalid_empty_or_read_error_is_not_retried(self):
        orphan = self.empty()
        orphan['values']['timer_state_7'] = 'orphan'
        stopwatch = self.empty()
        stopwatch['stopwatch']['sw_state'] = 1
        for first in (orphan, stopwatch, RuntimeError('HELD_READ_FAILED')):
            with self.subTest(first=first):
                fixture = self.fixture([first, self.running()])
                with self.assertRaises(RuntimeError):
                    fixture.flow.claim_created()
                self.assert_pending(fixture, 1)
                self.assertEqual(fixture.clock.sleeps, [])
                self.assertEqual(len(fixture.queued), 1)

    def test_nonempty_ambiguity_or_wrong_timer_is_not_retried(self):
        multiple = self.running()
        multiple['ids'].append(8)
        invalid = [multiple]
        for key, value in [('length_ms', 60000), ('total_length_ms', 60000),
                ('state', 4), ('last_start_ms', 9989), ('last_start_ms', 11011),
                ('remaining_ms', 0), ('remaining_ms', 900001), ('label', 'user timer'),
                ('delete_after_use', True)]:
            altered = self.running()
            altered['timers'][0][key] = value
            invalid.append(altered)
        for first in invalid:
            with self.subTest(first=first):
                fixture = self.fixture([first, self.running()])
                with self.assertRaises(RuntimeError):
                    fixture.flow.claim_created()
                self.assert_pending(fixture, 1)
                self.assertEqual(fixture.clock.sleeps, [])
                self.assertEqual(len(fixture.queued), 1)

    def test_unknown_or_multiple_input_has_no_readback_admission(self):
        for change in ('pending', 'actions', 'effect'):
            with self.subTest(change=change):
                fixture = self.fixture([self.running()])
                if change == 'pending':
                    fixture.flow.c.pending = 't05-create-start'
                elif change == 'actions':
                    fixture.flow.c.actions = 2
                else:
                    fixture.flow.effect_pending = {'operation': 'pause'}
                with self.assertRaisesRegex(RuntimeError, '^ONE_ACKNOWLEDGED_CREATE_REQUIRED$'):
                    fixture.flow.claim_created()
                self.assertEqual(fixture.reads, [])
                self.assertEqual(fixture.clock.sleeps, [])
                self.assertIsNone(fixture.flow.timer_id)

if __name__ == '__main__':
    unittest.main(verbosity=2)
