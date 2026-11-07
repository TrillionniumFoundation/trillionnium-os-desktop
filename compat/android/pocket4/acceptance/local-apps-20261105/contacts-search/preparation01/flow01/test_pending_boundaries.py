#!/usr/bin/env python3
"""Offline failure-injection checks; no device, UI or Contacts business credit."""
from pathlib import Path
import copy, importlib.util, types, unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value
controller = module(HERE / 'contacts_search01.py', 'search_controller_test')
base = module(ROOT / 'contacts-flow08/contacts_crud11.py', 'original_contacts_flow_test')
verifier = module(ROOT / 'contacts-flow08/verify_contact.py', 'exact_contacts_verifier_test')

def state(name=None):
    if name is None: return {'raw_rows': [], 'marker_rows': [], 'owned': None}
    raw = {'_id': '7', 'contact_id': '8', 'account_name': None, 'account_type': None,
           'data_set': None, 'deleted': '0'}
    row = {'_id': '9', 'raw_contact_id': '7', 'contact_id': '8',
           'mimetype': verifier.NAME_MIME, 'data1': name}
    return {'raw_rows': [{'_id': '7', 'contact_id': '8', 'deleted': '0'}],
            'marker_rows': [row], 'owned': {'name_row': row, 'raw_contact': raw}}

class Trial:
    def __init__(self):
        self.owned = (9001, {851}); self.launches = 1; self.removals = 0
        self.records = []; self.writes = []; self.commands = []; self.result = {}
        self.tx = types.SimpleNamespace(write_new=self.write)
        self.s = types.SimpleNamespace(android=self.command)
        self.close_error = False
        self.last_observation = {'screenshot': {'scope': {'package': base.PACKAGE,
            'activity': base.PACKAGE + '.activities.PeopleActivity'}}}
    def record(self, label, value): self.records.append((label, copy.deepcopy(value)))
    def write(self, path, value, **kwargs): self.writes.append((str(path), copy.deepcopy(value)))
    def command(self, argv, *args): self.commands.append(argv); raise AssertionError('unexpected remote dispatch')
    def close(self):
        self.removals += 1; self.owned = None
        if self.close_error: raise RuntimeError('OWNED_CLOSE_COMPLETION_UNKNOWN')
        self.result['other_tasks_preserved'] = True

class Continuation:
    def __init__(self, trial, package):
        self.pending = None; self.actions = 0; self.nodes = []; self.latest = 'actual-owned-view'
        self.approved_labels = set(); self.approved_contact_names = set(); self.mode = 'ok'
    def step(self, request):
        if self.mode == 'precondition': raise RuntimeError('OBSERVED_CONTROL_CHANGED')
        self.actions += 1; self.pending = request['id']
        if self.mode == 'unknown': raise RuntimeError('NATIVE_TIMEOUT_OUTCOME_UNKNOWN')
        self.pending = None

def control(identifier, text='', **kwargs):
    return {'package': base.PACKAGE, 'visible': True, 'enabled': True, 'resource-id': identifier,
            'text': text, 'content-desc': '', 'class': 'android.widget.Button', 'clickable': True,
            'editable': False, 'password': False, **kwargs}

class Boundaries(unittest.TestCase):
    def setUp(self):
        self.t = Trial(); self.db = state()
        self.v = types.SimpleNamespace(**{k: getattr(verifier, k) for k in
            ('NAME', 'EDITED', 'validate_owned', 'validate_deleted', 'validate_before')})
        self.reads = 0
        def current(_): self.reads += 1; return copy.deepcopy(self.db)
        self.v.current_state = current
        self.result = {'phases': {}}
        self.f = controller.build_flow(base)(self.t, types.SimpleNamespace(Continuation=Continuation), self.v, self.result)
        self.f.owned_tasks = [9001]
        self.node = control(base.PACKAGE + ':id/editor_menu_save_button', 'SAVE')

    def test_unknown_input_blocks_cleanup_before_any_provider_call(self):
        self.f.c.pending = 'unresolved-native'
        with self.assertRaisesRegex(RuntimeError, 'UNKNOWN_INPUT'): self.f.cleanup_fixture_on_failure()
        self.assertEqual((self.reads, self.t.commands, self.t.removals), (0, [], 0))

    def test_unknown_close_blocks_even_when_adapter_lost_task(self):
        self.f.close_pending = 9001; self.t.owned = None
        with self.assertRaisesRegex(RuntimeError, 'UNKNOWN_INPUT'): self.f.close()
        self.assertEqual(self.t.removals, 0)

    def test_database_effect_blocks_normal_close(self):
        self.f.effect_pending = {'kind': 'create', 'tag': 'save-created'}
        with self.assertRaisesRegex(RuntimeError, 'UNKNOWN_INPUT'): self.f.close()
        self.assertEqual(self.t.removals, 0)

    def test_input_ack_is_not_database_commit(self):
        self.f.c.nodes = [self.node]
        def uncommitted(*args): raise RuntimeError('ASYNC_PROVIDER_HAS_NOT_COMMITTED')
        self.f.owned = uncommitted
        with self.assertRaisesRegex(RuntimeError, 'ASYNC_PROVIDER'): self.f.save('save-created')
        self.assertEqual(self.f.c.actions, 1); self.assertIsNone(self.f.c.pending)
        self.assertEqual(self.f.effect_pending['kind'], 'create')
        with self.assertRaisesRegex(RuntimeError, 'UNKNOWN_INPUT'): self.f.close()
        self.assertEqual(self.t.removals, 0)

    def test_committed_db_never_clears_an_unknown_native_input(self):
        self.db = state(self.v.NAME)
        self.f.begin_effect('create', 'save-created', self.v.NAME)
        self.f.commit_tag = None; self.f.c.pending = 'native-timeout'
        with self.assertRaisesRegex(RuntimeError, 'DATABASE_COMMIT_REQUIRES'): self.f.reconcile_database_effect()
        self.assertIsNotNone(self.f.effect_pending); self.assertEqual(self.f.c.pending, 'native-timeout')
        self.assertEqual((self.t.commands, self.t.removals), ([], 0))

    def test_ownership_persisted_at_first_exact_database_claim(self):
        self.db = state(self.v.NAME)
        self.f.owned(self.v.NAME, 'created')
        self.assertTrue(self.f.ownership_journal)
        self.assertEqual(self.result['owned_contact_identity']['raw_contact_id'], '7')
        self.assertEqual(len(self.t.writes), 1)
        self.assertTrue(self.t.writes[0][0].endswith('/owned-contact-claim.json'))
        self.f.owned(self.v.NAME, 'later')
        self.assertEqual(len(self.t.writes), 1)

    def test_uncertain_close_preserves_original_task_identity(self):
        self.t.close_error = True
        with self.assertRaisesRegex(RuntimeError, 'OWNED_CLOSE'): self.f.close()
        self.assertEqual(self.t.owned, (9001, {851})); self.assertEqual(self.f.close_pending, 9001)
        with self.assertRaisesRegex(RuntimeError, 'UNKNOWN_INPUT'): self.f.close()
        self.assertEqual(self.t.removals, 1)

    def test_verified_normal_close_releases_its_fence(self):
        self.f.close()
        self.assertEqual(self.f.closed_tasks, [9001]); self.assertIsNone(self.f.close_pending)
        self.assertIsNone(self.t.owned); self.assertEqual(self.t.removals, 1)

    def test_precondition_before_native_dispatch_releases_only_its_unstarted_effect(self):
        self.f.begin_effect('create', 'save-created', self.v.NAME); self.f.c.mode = 'precondition'
        with self.assertRaisesRegex(RuntimeError, 'OBSERVED_CONTROL_CHANGED'):
            self.f.act('save-created', 'click', self.node)
        self.assertIsNone(self.f.effect_pending); self.assertIsNone(self.f.commit_tag)
        self.assertEqual(self.f.c.actions, 0)

    def test_unknown_dispatch_retains_both_fences_and_is_not_replayed(self):
        self.f.begin_effect('create', 'save-created', self.v.NAME); self.f.c.mode = 'unknown'
        with self.assertRaisesRegex(RuntimeError, 'NATIVE_TIMEOUT'): self.f.act('save-created', 'click', self.node)
        self.assertIsNotNone(self.f.effect_pending); self.assertIsNotNone(self.f.c.pending)
        with self.assertRaisesRegex(RuntimeError, 'UNRESOLVED_DATABASE'): self.f.act('save-created', 'click', self.node)
        self.assertEqual(self.f.c.actions, 1)

    def test_search_field_cannot_escape_the_owned_people_activity(self):
        self.t.last_observation['screenshot']['scope']['activity'] = base.PACKAGE + '.activities.ContactEditorActivity'
        self.f.c.nodes = [control(base.PACKAGE + ':id/observed', '', **{'class': 'android.widget.EditText', 'editable': True})]
        with self.assertRaisesRegex(RuntimeError, 'SEARCH_REQUIRES'): self.f.search_field()
        self.assertEqual(self.f.c.actions, 0)

    def test_search_field_rejects_duplicates_and_wrong_query(self):
        node = control(base.PACKAGE + ':id/observed', 'different', **{'class': 'android.widget.EditText', 'editable': True})
        self.f.c.nodes = [node, dict(node)]
        with self.assertRaisesRegex(RuntimeError, 'NOT_UNIQUE'): self.f.search_field()
        self.f.c.nodes = [node]
        with self.assertRaisesRegex(RuntimeError, 'EXACT_QUERY_TEXT'): self.f.search_field(self.v.EDITED)
        self.assertEqual(self.f.c.actions, 0)

if __name__ == '__main__': unittest.main(verbosity=2)
