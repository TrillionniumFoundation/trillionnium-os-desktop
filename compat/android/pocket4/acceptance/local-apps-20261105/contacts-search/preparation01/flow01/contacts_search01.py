#!/usr/bin/python3 -I
"""Create/edit one local contact, close/reopen, search and delete that same fixture."""
from pathlib import Path
import argparse, copy, hashlib, json, os, re, signal, time, types

TOOLS = Path('/home/alex/work/pocket4-contacts-search-tools-20261105-r12-01')
ROOT = Path('/home/alex/work/pocket4-contacts-search-flow-20261105-r12-01')
PACKAGE = 'com.android.contacts'
PINS = {'contacts_crud11.py': '4de5eace361865990baab07f5bd445df1345a7ae0f579d40356d0913b76a9578', 'ui_preflight05.py': '2e99a4d0b2a9f4be7046c3504ec65d754bd91c959cb0f4f1adfe873aa3a16237', 'session_loop08.py': 'c4a985ddcfe54104a7d90dd4ce8dd44b708016dd44911faa92ac16e3c38a9db3', 'verify_contact.py': '0824a81f2519dab845cd2f5d9e8e8dfe5998e9f13f209d55305a8c27bd0bf3ee'}
WORK_SECONDS, CLEANUP_SECONDS, MAX_INPUTS = 240, 60, 24

def need(ok, code):
    if not ok: raise RuntimeError(code)

def load(name):
    raw = (TOOLS / name).read_bytes()
    need(hashlib.sha256(raw).hexdigest() == PINS[name], 'SOURCE_PIN_CHANGED:' + name)
    module = types.ModuleType('contacts_search_' + name.replace('.', '_'))
    module.__file__ = str(TOOLS / name)
    exec(compile(raw, module.__file__, 'exec'), module.__dict__)
    return module

def expired(signum, frame):
    raise TimeoutError('CONTACTS_SEARCH_LEASE_EXPIRED_NO_REPLAY')

def build_flow(base):
    class SearchFlow(base.Flow):
        def __init__(self, trial, loop, verifier, result):
            super().__init__(trial, loop, verifier, result)
            self.deadline = time.monotonic() + WORK_SECONDS
            self.effect_pending = self.close_pending = self.commit_tag = None
            self.delete_dispatched = self.cleanup_dispatched = False
            self.ownership_journal = False

        def may_mutate(self):
            need(self.c.pending is None and self.close_pending is None and self.effect_pending is None,
                 'UNKNOWN_INPUT_CLOSE_OR_DATABASE_EFFECT_NO_NEW_ACTION')

        def act(self, tag, op, node, value=None):
            need(self.close_pending is None, 'UNRESOLVED_CLOSE_BLOCKS_INPUT')
            commit_owned = self.effect_pending is not None
            if self.effect_pending is not None:
                need(self.commit_tag == tag and self.effect_pending['tag'] == tag,
                     'UNRESOLVED_DATABASE_EFFECT_BLOCKS_INPUT')
                self.commit_tag = None
            else:
                need(self.commit_tag is None, 'ORPHAN_COMMIT_TAG')
            need(self.number < MAX_INPUTS, 'INPUT_BUDGET_EXHAUSTED')
            attempts = self.c.actions
            try:
                return super().act(tag, op, node, value)
            except BaseException:
                if commit_owned and self.c.actions == attempts and self.c.pending is None:
                    # The unchanged continuation increments actions and sets its
                    # pending fence before the sole native dispatch. Equal count
                    # plus no pending proves a failed precondition, not an ACK.
                    self.t.record('database-not-dispatched-' + tag, {
                        'original_intent': copy.deepcopy(self.effect_pending),
                        'native_dispatch_count_unchanged': True, 'automatic_retry': False})
                    self.effect_pending = None
                raise

        def launch(self, tag):
            self.may_mutate()
            need(self.t.owned is None and len(self.owned_tasks) < 2 and time.monotonic() < self.deadline,
                 'ONLY_TWO_EXACT_OWNED_LAUNCHES_ALLOWED')
            calls = self.t.launches
            self.c.pending = 'launch-' + tag
            try:
                self.t.launch()
            except BaseException:
                if self.t.launches == calls:
                    self.c.pending = None
                raise
            need(self.t.owned is not None, 'ACKNOWLEDGED_LAUNCH_HAS_NO_TASK')
            self.owned_tasks.append(self.t.owned[0])
            self.c.pending = None
            self.observe(tag)

        def close(self):
            self.may_mutate()
            if self.t.owned is None:
                return
            ownership = copy.deepcopy(self.t.owned)
            task, calls = ownership[0], self.t.removals
            self.close_pending = task
            self.t.record('owned-close-fence', {'task': task, 'automatic_retry': False})
            try:
                self.t.close()
                need(self.t.removals == calls + 1 and self.t.result.get('other_tasks_preserved') is True,
                     'NORMAL_CLOSE_NOT_VERIFIED')
            except BaseException:
                # The inherited adapter clears its reference before dispatch.
                # Preserve identity and this unresolved fence; never retry close.
                self.t.owned = ownership
                raise
            self.closed_tasks.append(task)
            self.close_pending = None

        def begin_effect(self, kind, tag, expected_name=None):
            self.may_mutate()
            need(time.monotonic() < self.deadline and (kind == 'cleanup' or self.number < MAX_INPUTS),
                 'NO_COMMIT_INTENT_AFTER_INPUT_BUDGET')
            self.effect_pending = {'kind': kind, 'tag': tag, 'expected_name': expected_name,
                                   'owned': self.v.validate_owned(self.created, self.created['owned']['name_row']['data1']) if self.created else None,
                                   'automatic_retry': False}
            self.commit_tag = tag
            self.t.record('database-intent-' + tag, copy.deepcopy(self.effect_pending))

        def complete_effect(self, proof):
            need(self.c.pending is None and self.effect_pending is not None and self.commit_tag is None,
                 'DATABASE_COMMIT_REQUIRES_ACK_AND_EXACT_READBACK')
            self.t.record('database-readback-' + self.effect_pending['tag'], {
                'intent': copy.deepcopy(self.effect_pending), 'proof': proof,
                'input_ACK_alone_is_not_completion': True})
            self.effect_pending = None

        def owned(self, name, tag):
            state = super().owned(name, tag)
            proof = self.v.validate_owned(state, name, self.created)
            if self.created is None:
                self.created = copy.deepcopy(state)
                # Persist identity as soon as the exact DB claim succeeds, before
                # any next UI lookup can fail.
                self.t.tx.write_new(ROOT / 'owned-contact-claim.json', {
                    'proof': proof, 'state': state, 'initial_name': self.v.NAME,
                    'edited_name': self.v.EDITED, 'normal_create_calls': 1})
                self.ownership_journal = True
                self.r['owned_contact_identity'] = proof
            return state

        def save(self, tag):
            expected = {'save-created': self.v.NAME, 'save-edited': self.v.EDITED}.get(tag)
            need(expected is not None, 'ONLY_TWO_DECLARED_SAVE_OPERATIONS')
            node = base.one(self.c.nodes, lambda n: n.get('resource-id') == PACKAGE + ':id/editor_menu_save_button'
                            and n.get('text') == 'SAVE' and n.get('clickable') is True,
                            'OBSERVED_SAVE_NOT_UNIQUE')
            self.begin_effect('create' if self.created is None else 'edit', tag, expected)
            self.click(tag, node)
            state = self.owned(expected, tag + '-committed')
            self.complete_effect(self.v.validate_owned(state, expected, self.created))

        def reconcile_database_effect(self):
            if self.effect_pending is None:
                return
            need(self.commit_tag is None, 'DATABASE_COMMIT_NOT_DISPATCHED_OR_ACK_UNRESOLVED')
            state = self.v.current_state(self.t.s)
            self.t.record('pending-database-read-only', state)
            if self.effect_pending['kind'] in ('create', 'edit'):
                name = self.effect_pending['expected_name']
                self.v.validate_owned(state, name, self.created)
                if self.created is None:
                    self.created = copy.deepcopy(state)
                    self.t.tx.write_new(ROOT / 'owned-contact-claim.json', {
                        'proof': self.v.validate_owned(state, name), 'state': state,
                        'reconciled_from_original_intent': True})
                    self.ownership_journal = True
                proof = self.v.validate_owned(state, name, self.created)
            else:
                need(self.created is not None, 'DELETE_HAS_NO_DURABLE_OWNERSHIP')
                proof = self.v.validate_deleted(state, self.created)
            # A DB observation never clears an unknown native input/close.
            self.complete_effect(proof)

        def search_field(self, expected=None):
            scope = self.t.last_observation['screenshot']['scope']
            need(scope['package'] == PACKAGE and scope['activity'] == PACKAGE + '.activities.PeopleActivity',
                 'SEARCH_REQUIRES_OWNED_PEOPLE_ACTIVITY')
            node = base.one(self.c.nodes, lambda n: n.get('class') == 'android.widget.EditText'
                            and n.get('editable') is True and n.get('password') is False,
                            'OBSERVED_SEARCH_EDIT_TEXT_NOT_UNIQUE')
            need(str(node.get('resource-id', '')).startswith(PACKAGE + ':id/'), 'SEARCH_INPUT_NOT_APP_OWNED')
            if expected is not None:
                need(node.get('text') == expected and node.get('showing-hint') is not True,
                     'EXACT_QUERY_TEXT_NOT_OBSERVED')
            return node

        def search_same_edited_contact(self):
            self.may_mutate()
            self.owned(self.v.EDITED, 'before-search')
            search = base.one(self.c.nodes, lambda n: n.get('resource-id') == PACKAGE + ':id/menu_search'
                              and n.get('content-desc') == 'Search contacts' and n.get('clickable') is True,
                              'OBSERVED_CONTACTS_SEARCH_BUTTON_NOT_UNIQUE')
            self.click('open-search', search)
            field = self.search_field()
            need(not field.get('text') or field.get('showing-hint') is True,
                 'SEARCH_NOT_EMPTY_AT_THIS_FRESH_START')
            self.act('search-edited-name', 'set-text', field, self.v.EDITED)
            until = min(self.deadline, time.monotonic() + 18)
            matched = None
            for attempt in range(4):
                need(time.monotonic() < until, 'SEARCH_RESULT_READ_BUDGET_EXHAUSTED')
                self.search_field(self.v.EDITED)
                rows = [n for n in base.visible(self.c.nodes)
                        if n.get('resource-id') == PACKAGE + ':id/cliv_name_textview'
                        and n.get('text') == n.get('content-desc') == self.v.EDITED]
                need(len(rows) <= 1, 'SEARCH_RESULT_NOT_UNIQUE')
                if rows:
                    matched = rows[0]
                    break
                if attempt < 3:
                    self.observe('search-result-read-' + str(attempt))
            need(matched is not None, 'SEARCH_DID_NOT_RETURN_SAME_EDITED_CONTACT')
            current = self.owned(self.v.EDITED, 'search-result-identity')
            self.r['search_result'] = {'query': self.v.EDITED, 'observed_node': matched,
                'observation': self.c.latest, 'screenshot': self.t.last_observation['screenshot'],
                'same_contact': self.v.validate_owned(current, self.v.EDITED, self.created)}
            self.click('open-search-result', matched, approved_fixture_label=True, contact_list_marker=True)
            self.detail(self.v.EDITED, 'searched-detail')
            self.owned(self.v.EDITED, 'searched-detail-same-record')
            self.r['edited_contact_found_by_search_and_reopened'] = True

        def delete_ui(self):
            self.may_mutate()
            need(not self.delete_dispatched, 'DELETE_NOT_REPLAYABLE')
            state = self.owned(self.v.EDITED, 'before-delete')
            self.detail(self.v.EDITED, 'delete')
            menu = base.one(self.c.nodes, lambda n: n.get('clickable') is True
                            and n.get('content-desc') == 'More options', 'OWNED_DETAIL_MORE_NOT_UNIQUE')
            self.t.bind_owned_contact_menu(self.v.validate_owned(state, self.v.EDITED, self.created))
            self.click('more-options', menu)
            option = base.one(self.c.nodes, lambda n: str(n.get('text', '')).casefold() in ('delete', 'delete contact'),
                              'EXACT_DELETE_MENU_NOT_UNIQUE')
            self.click('delete-option', option, approved_fixture_label=True)
            positive = None
            for attempt in range(3):
                nodes = base.visible(self.c.nodes)
                yes = [n for n in nodes if n.get('class') == 'android.widget.Button' and n.get('clickable') is True
                       and str(n.get('text', '')).casefold() in ('delete', 'delete contact')]
                cancel = [n for n in nodes if n.get('class') == 'android.widget.Button' and n.get('clickable') is True
                          and str(n.get('text', '')).casefold() == 'cancel']
                message = [n for n in nodes if n.get('resource-id') in ('android:id/message', 'android:id/alertTitle')
                           and 'contact' in str(n.get('text', '')).casefold() and 'delet' in str(n.get('text', '')).casefold()]
                if len(yes) == len(cancel) == 1 and message:
                    positive = yes[0]
                    break
                if attempt < 2:
                    self.observe('delete-confirm-read-' + str(attempt))
            need(positive is not None, 'EXACT_CONTACT_DELETE_CONFIRMATION_REQUIRED')
            self.owned(self.v.EDITED, 'before-delete-confirm')
            self.begin_effect('delete', 'confirm-delete')
            self.delete_dispatched = True
            self.click('confirm-delete', positive)
            for attempt in range(3):
                if self.deleted('ui-delete-final-' + str(attempt)):
                    self.complete_effect(self.r['phases']['ui-delete-final-' + str(attempt)]['proof'])
                    self.r['UI_delete_verified'] = True
                    return
                time.sleep(.2)
            raise RuntimeError('UI_DELETE_ACK_NOT_DATABASE_COMPLETION')

        def cleanup_fixture_on_failure(self):
            if self.effect_pending is not None:
                self.reconcile_database_effect()
            self.may_mutate()
            state = self.v.current_state(self.t.s)
            self.t.record('failure-owned-contact-readback', state)
            if not state['marker_rows']:
                if self.created is None: self.v.validate_before(state)
                else: self.v.validate_deleted(state, self.created)
                self.r['fixture_cleanup'] = {'method': 'read-only', 'owned_marker_absent': True}
                return
            # Cleanup is a separate, exact owned fixture action and earns no UI-delete credit.
            need(self.created is not None and self.ownership_journal and not self.cleanup_dispatched,
                 'EXACT_PERSISTED_CONTACT_OWNERSHIP_REQUIRED_FOR_CLEANUP')
            name = state['owned']['name_row']['data1']
            proof = self.v.validate_owned(state, name, self.created)
            need(name in (self.v.NAME, self.v.EDITED), 'UNEXPECTED_OWNED_NAME')
            raw_id, contact_id = proof['raw_contact_id'], proof['contact_id']
            need(re.fullmatch('[1-9][0-9]*', raw_id) and re.fullmatch('[1-9][0-9]*', contact_id), 'OWNED_IDS_REQUIRED')
            where = ('_id=' + raw_id + ' AND contact_id=' + contact_id
                     + ' AND account_name IS NULL AND account_type IS NULL AND data_set IS NULL AND deleted=0')
            argv = ['/system/bin/content', 'delete', '--user', '0', '--uri',
                    'content://com.android.contacts/raw_contacts', '--where', where]
            self.begin_effect('cleanup', 'exact-owned-fallback')
            self.commit_tag = None
            self.cleanup_dispatched = True
            self.t.record('owned-cleanup-intent', {'argv': argv, 'proof': proof, 'automatic_retry': False,
                                                  'does_not_prove_UI_delete': True})
            # A command timeout retains the database fence; no second delete or close follows.
            output = self.t.s.android(argv, 15).decode('utf-8', 'strict')
            after = self.v.current_state(self.t.s)
            proof = self.v.validate_deleted(after, self.created)
            self.complete_effect(proof)
            self.r['fixture_cleanup'] = {'method': 'exact-owned-provider-fallback', 'stdout': output,
                                        'readback': proof, 'does_not_prove_UI_delete': True}

        def run(self):
            self.launch('initial')
            create = base.one(self.c.nodes, lambda n: n.get('resource-id') == PACKAGE + ':id/floating_action_button'
                              and n.get('content-desc') == 'Create new contact', 'OBSERVED_CREATE_NOT_UNIQUE')
            self.click('create', create)
            field = self.local_editor('First name')
            self.act('set-name', 'set-text', field, self.v.NAME)
            self.local_editor(self.v.NAME)
            self.save('save-created')
            self.click('edit-owned', self.detail(self.v.NAME, 'created'))
            field = self.local_editor(self.v.NAME)
            self.act('set-edited-name', 'set-text', field, self.v.EDITED)
            self.local_editor(self.v.EDITED)
            self.save('save-edited')
            self.close()
            self.owned(self.v.EDITED, 'persisted-after-normal-close')
            self.launch('reopen-initial')
            need(len(set(self.owned_tasks)) == 2, 'REOPEN_DID_NOT_CREATE_NEW_OWNED_TASK')
            self.owned(self.v.EDITED, 'persisted-after-reopen')
            self.search_same_edited_contact()
            self.delete_ui()
            self.r['state'] = 'LOCAL_CONTACT_EDITED_CLOSED_REOPENED_SEARCHED_AND_UI_DELETED'
    return SearchFlow

def execute():
    base, adapter, loop, verifier = [load(name) for name in
        ('contacts_crud11.py', 'ui_preflight05.py', 'session_loop08.py', 'verify_contact.py')]
    tx = adapter.load_session()
    need(adapter.SOURCE_SHA == verifier.SESSION_SHA == 'b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
         and tx.ACTIVATION_SHA == '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615', 'ORIGINAL_MAIN_PROFILE_REQUIRED')
    adapter.ROOT = ROOT
    loop.emit = lambda value: None
    result = {'schema': 'contacts-search-owned-flow/v1', 'state': 'FAILED', 'phases': {}, 'source_pins': PINS,
              'started_utc': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
              'automatic_retry': False, 'business_success_verified': False, 'whole_app_production_ready': False,
              'marker': verifier.NAME, 'edited_marker': verifier.EDITED, 'work_seconds': WORK_SECONDS,
              'cleanup_seconds': CLEANUP_SECONDS, 'max_inputs': MAX_INPUTS, 'max_contacts_created': 1,
              'account_or_sync_mutations': 0}
    trial = flow = None
    old = signal.signal(signal.SIGALRM, expired)
    try:
        with tx.ui_lock():
            need(os.geteuid() == 0 and not os.path.lexists(ROOT), 'NEW_OWNED_ROOT_REQUIRED')
            os.umask(0o077); ROOT.mkdir(mode=0o750); os.chown(ROOT, 0, 1000); os.chmod(ROOT, 0o750)
            signal.setitimer(signal.ITIMER_REAL, WORK_SECONDS)
            with tx.CameraSession(ROOT / 'commands') as session:
                trial = adapter.Trial(session, tx)
                flow = build_flow(base)(trial, loop, verifier, result)
                result['guard_before'] = session.guard()
                verifier.identity(session)
                result['account_topology_before'] = verifier.unchanged_account_topology(session)
                roots, tasks = trial.stacks('initial-coordinated-taskset')
                need(tasks == {851}, 'FORMAL_UI_HANDOFF_BASELINE_REQUIRED')
                baseline_roots = copy.deepcopy(roots)
                result['contacts_before'] = verifier.current_state(session)
                verifier.validate_before(result['contacts_before'])
                result['empty_baseline_verified'] = True
                try:
                    flow.run()
                    result['business_success_verified'] = True
                except BaseException as error:
                    result.update(state='FAILED', error=type(error).__name__ + ': ' + str(error))
                    signal.setitimer(signal.ITIMER_REAL, CLEANUP_SECONDS)
                    flow.deadline = time.monotonic() + CLEANUP_SECONDS - 15
                    try:
                        flow.cleanup_fixture_on_failure()
                    except BaseException as cleanup:
                        result['fixture_cleanup_error'] = type(cleanup).__name__ + ': ' + str(cleanup)
                finally:
                    if result.get('business_success_verified'):
                        signal.setitimer(signal.ITIMER_REAL, CLEANUP_SECONDS)
                    try:
                        if flow.c.pending is None and flow.close_pending is None and flow.effect_pending is None:
                            flow.close()
                        else:
                            result['unknown_retained_without_further_mutation'] = True
                        result['contacts_after'] = verifier.current_state(session)
                        if flow.created is None: verifier.validate_before(result['contacts_after'])
                        else: result['deleted_final_proof'] = verifier.validate_deleted(result['contacts_after'], flow.created)
                        result['account_topology_after'] = verifier.unchanged_account_topology(session)
                        verifier.identity(session)
                        final_roots, final_tasks = trial.stacks('final-coordinated-taskset')
                        need(final_tasks == {851} and final_roots == baseline_roots, 'TASK_BASELINE_NOT_RESTORED')
                        session.caller_status('contacts-search-final')
                        result['guard_after'] = session.guard()
                        need(result['guard_after'] == result['guard_before'], 'MAIN_CHANGED')
                        result['cleanup_verified'] = (flow.c.pending is None and flow.close_pending is None
                                                      and flow.effect_pending is None and trial.owned is None)
                    except BaseException as final:
                        result['final_error'] = type(final).__name__ + ': ' + str(final)
    except BaseException as error:
        result.update(state='FAILED', outer_error=type(error).__name__ + ': ' + str(error))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, old)
        if flow is not None:
            result.update(UI_actions=flow.c.actions, pending_input=flow.c.pending, pending_close=flow.close_pending,
                          pending_database_effect=flow.effect_pending, native_launched_tasks=flow.owned_tasks,
                          normally_closed_tasks=flow.closed_tasks, owned_task_remaining=trial.owned,
                          durable_contact_ownership=flow.ownership_journal, provider_cleanup_calls=int(flow.cleanup_dispatched))
        complete = bool(result.get('business_success_verified') and result.get('cleanup_verified')
                        and result.get('edited_contact_found_by_search_and_reopened') and result.get('UI_delete_verified')
                        and flow is not None and len(flow.owned_tasks) == len(flow.closed_tasks) == 2
                        and flow.owned_tasks == flow.closed_tasks and not result.get('fixture_cleanup_error')
                        and not result.get('final_error') and not result.get('outer_error'))
        result['business_success_verified'] = complete
        if not complete: result['state'] = 'FAILED'
        result['finished_utc'] = __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()
        if ROOT.is_dir(): tx.write_new(ROOT / 'result.json', result, alex_readable=True)
        print(json.dumps({k: result.get(k) for k in ('state', 'error', 'outer_error', 'fixture_cleanup_error', 'final_error',
              'business_success_verified', 'cleanup_verified', 'UI_actions', 'pending_input', 'pending_close',
              'pending_database_effect', 'native_launched_tasks', 'normally_closed_tasks', 'provider_cleanup_calls')}, sort_keys=True))
    return 0 if result['business_success_verified'] else 1

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.execute: raise SystemExit(execute())
    print(json.dumps({'state': 'INERT', 'UI_actions': 0, 'provider_mutations': 0, 'whole_app_production_ready': False}))
