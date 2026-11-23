"""Run the QSB session's business entry with modeled device responses."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from check_cleanup_phase import common_writer, load_runtime


class SearchCaseTest(unittest.TestCase):
    def setUp(self):
        source = HERE / 'source/qsb_runtime.py'
        session_type, self.clock = load_runtime(source, source.read_bytes())
        self.session = session = object.__new__(session_type)
        common_path = HERE.parent / 'current-canonical-app-main-20261120/bundle/source/shared/app_common.py'
        session.c = common_writer(common_path.read_bytes())

        def read_ref(ref):
            raw = Path(ref['path']).read_bytes()
            session.c.need(len(raw) == ref['bytes'] and session.c.sha(raw) == ref['sha256'], 'fixture reference changed')
            return raw

        session.c.read_ref = read_ref
        session.c.parse = json.loads
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        session.root = Path(self.tmp.name)
        session.base_ref = {'fixture': 'host-only'}
        session.phase_ref = {'phase': 'business'}
        session.profile = types.SimpleNamespace(PACKAGE='com.android.quicksearchbox', QUERIES=('café', '维基百科'))
        session.qsb_task = session.browser_task = session.pending = session.active_api = None
        session.host_cancelled = session.host_retirement_unknown = False
        session.original_roots = None
        session.claimed = {}
        session.removed = []
        session.records = []
        session.native_launches = session.text_edits = session.clicks = session.back_events = 0
        session.started, session.deadline, session.cleanup_deadline = 1000., 1600., 1720.
        session.phase = 'business'
        session.guard = Mock()
        self.log = []
        self.tasks = {7}
        session.stacks = self.stacks
        self.fail_at = None
        self.damage_evidence = False
        self.reopened_query = ''
        self.launch = session.launch
        session.launch = self.fake_launch
        session.observe = self.observe
        session.set_query = self.edit
        session.open_result = self.open_result
        session.return_to_query = self.back
        session.normal_close_qsb = self.close_qsb
        session.observer = types.SimpleNamespace(query=self.check_query)

    def receipt(self, step):
        return self.session.record('fixture-' + step, {'step': step})

    def step(self, name):
        self.log.append(name)
        if self.fail_at == name:
            raise RuntimeError('failure at ' + name)

    def stacks(self):
        return {7: {'children': []}}, set(self.tasks)

    def fake_launch(self):
        s = self.session
        self.step('launch')
        if s.original_roots is None:
            s.original_roots, s.original_tasks = self.stacks()
        s.native_launches += 1
        s.qsb_task = 10 + s.native_launches
        s.claimed[s.qsb_task] = 'owned-qsb'
        self.tasks.add(s.qsb_task)
        return self.receipt('launch-%d' % s.native_launches)

    def observe(self, package, name):
        self.step(name)
        return {'nodes': [self.reopened_query]}, self.receipt(name)

    def edit(self, query):
        s = self.session
        self.step('edit-' + query)
        s.text_edits += 1
        return {}, self.receipt('edit-%d' % s.text_edits)

    def open_result(self):
        s = self.session
        s.pending = {'kind': 'open-result', 'sent': True}
        self.step('open')
        s.clicks += 1
        s.browser_task = 20
        s.claimed[20] = 'owned-browser'
        self.tasks.add(20)
        s.pending = None
        return self.receipt('open')

    def back(self):
        s = self.session
        self.step('back')
        s.back_events += 1
        self.tasks.remove(20)
        s.removed.append(20)
        return self.receipt('back')

    def close_qsb(self, name):
        s = self.session
        self.step(name)
        s.begin_cleanup()
        self.tasks.remove(s.qsb_task)
        s.removed.append(s.qsb_task)
        if name == 'second-close' and self.damage_evidence:
            (s.root / 'fixture-open.json').write_text('{}')
        return self.receipt(name)

    def check_query(self, nodes, profile, value, *, matches, empty):
        self.assertEqual((profile, value, matches, empty), (self.session.profile, '', False, True))
        if nodes != ['']:
            raise RuntimeError('reopened query changed')

    def test_complete_sequence_and_scope(self):
        s = self.session
        report = json.loads(s.c.read_ref(s.run_search_case()))
        self.assertEqual(self.log, ['launch', 'initial-query', 'edit-café', 'edit-维基百科', 'open',
                                   'back', 'edit-', 'first-close', 'launch', 'reopened-query', 'second-close'])
        self.assertEqual(report['observed_scope'], ['search.query', 'search.open'])
        self.assertEqual(report['remaining_business_gates'], ['search.failure'])
        self.assertFalse(report['whole_app_business_accepted'])
        self.assertEqual(self.tasks, {7})
        self.assertEqual(len(report['receipts']), 12)
        for ref in report['receipts'].values():
            s.c.read_ref(ref)

    def test_unknown_click_stops_without_cleanup_or_replay(self):
        self.fail_at = 'open'
        with self.assertRaisesRegex(RuntimeError, 'failure at open'):
            self.session.run_search_case()
        self.assertTrue(self.session.pending['sent'])
        self.assertEqual(self.log[-1], 'open')
        with self.assertRaisesRegex(RuntimeError, 'QSB_CASE_REQUIRES_FRESH_SESSION'):
            self.session.run_search_case()
        self.assertFalse((self.session.root / 'search-case-observations.json').exists())

    def test_known_observation_failure_removes_only_owned_task(self):
        self.fail_at = 'initial-query'
        with self.assertRaisesRegex(RuntimeError, 'failure at initial-query'):
            self.session.run_search_case()
        self.assertEqual(self.log, ['launch', 'initial-query', 'failure-close'])
        self.assertEqual(self.tasks, {7})

    def test_browser_still_live_is_retained(self):
        self.fail_at = 'back'
        with self.assertRaisesRegex(RuntimeError, 'failure at back'):
            self.session.run_search_case()
        self.assertIn(20, self.tasks)
        self.assertNotIn('failure-close', self.log)

    def test_failed_close_is_not_retried(self):
        self.fail_at = 'first-close'
        with self.assertRaisesRegex(RuntimeError, 'failure at first-close'):
            self.session.run_search_case()
        self.assertEqual(self.log[-1], 'first-close')
        self.assertNotIn('failure-close', self.log)

    def test_reopened_query_needs_actual_blank_readback(self):
        self.reopened_query = 'retained-private-query'
        with self.assertRaisesRegex(RuntimeError, 'reopened query changed'):
            self.session.run_search_case()
        self.assertEqual(self.log[-1], 'failure-close')
        self.assertEqual(self.tasks, {7})

    def test_tampered_observation_prevents_success(self):
        self.damage_evidence = True
        with self.assertRaisesRegex(RuntimeError, 'fixture reference changed'):
            self.session.run_search_case()
        self.assertFalse((self.session.root / 'search-case-observations.json').exists())

    def test_durable_once_refuses_new_session_on_same_case_root(self):
        self.session.record('search-case-once', {'fixture': 'previous-case'})
        with self.assertRaises(FileExistsError):
            self.session.run_search_case()
        self.assertEqual(self.log, [])

    def call_entry(self, session, release):
        source = HERE / 'source/qsb_runtime.py'
        spec = importlib.util.spec_from_file_location('qsb_entry_control', source)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        base = session.record('base', {'fixture': 'existing admitted plan'})
        constructor = Mock(return_value=session)
        with patch.object(module, 'make_session_class', return_value=constructor), \
             patch.object(module, 'resource_report') as resource_check:
            result = module.execute(session.c, base, {'original_transport.py': object()},
                                    release, object(), Mock(), Mock())
        self.assertEqual(constructor.call_count, 1)
        self.assertEqual(resource_check.call_count, 2)
        return result

    def test_entry_retires_session_before_terminal_receipt(self):
        s = self.session
        s.close = Mock()
        release = Mock()
        result = json.loads(s.c.read_ref(self.call_entry(s, release)))
        s.close.assert_called_once()
        self.assertEqual(release.guard.call_count, 2)
        self.assertTrue(result['session_closed'])
        self.assertFalse(result['whole_app_business_accepted'])
        s.c.read_ref(result['observations'])

    def test_failed_retirement_never_publishes_terminal_receipt(self):
        s = self.session
        s.close = Mock(side_effect=RuntimeError('incomplete retirement'))
        with self.assertRaisesRegex(RuntimeError, 'incomplete retirement'):
            self.call_entry(s, Mock())
        self.assertTrue((s.root / 'search-case-observations.json').exists())
        self.assertFalse((s.root / 'search-case-result.json').exists())

    def test_changed_release_after_close_never_publishes_terminal_receipt(self):
        s = self.session
        s.close = Mock()
        release = Mock()
        release.guard.side_effect = [None, RuntimeError('release changed')]
        with self.assertRaisesRegex(RuntimeError, 'release changed'):
            self.call_entry(s, release)
        s.close.assert_called_once()
        self.assertFalse((s.root / 'search-case-result.json').exists())

    def test_first_failure_survives_failed_context_close(self):
        s = self.session
        self.fail_at = 'open'
        s.close = Mock(side_effect=OSError('FD close failed'))
        with self.assertRaisesRegex(RuntimeError, 'failure at open') as result:
            self.call_entry(s, Mock())
        self.assertIn('QSB session retirement: FD close failed', result.exception.__notes__)
        self.assertFalse((s.root / 'search-case-result.json').exists())

    def test_launch_claim_names_the_host_command_before_followup_task_read(self):
        # Exercise the actual Session.launch with separate host and observation
        # records. The intervening stack read appends the later transport record.
        s = self.session
        s.c.NATIVE_PREFIX = ['droidloomctl']
        s.allowed_ui_packages = {s.profile.PACKAGE}
        s.profile.COMPONENT = s.profile.PACKAGE + '/.SearchActivity'
        s.view = types.SimpleNamespace(target=types.SimpleNamespace(expected={'pid': 1}))
        s.base = {'baseline': {}, 'qualification': {}}
        s.task = types.SimpleNamespace(native_claim=lambda *args: 11)
        s.focus = Mock()
        def stacks():
            ref = self.receipt('stacks-%d' % len(s.records))
            s.records.append(ref)
            return self.stacks()
        def host(*args):
            s.records.append(self.receipt('native-launch'))
            return {'stdout': b'{}'}
        s.stacks = stacks
        s._host = host
        claim = json.loads(s.c.read_ref(self.launch()))
        self.assertEqual(json.loads(s.c.read_ref(claim['actual_host_result'])), {'step': 'native-launch'})
        self.assertNotEqual(s.records[-1], claim['actual_host_result'])


if __name__ == '__main__':
    unittest.main()
