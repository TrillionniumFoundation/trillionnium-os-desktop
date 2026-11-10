#!/usr/bin/python3 -I
"""One local Contacts fixture, observed UI CRUD, owned reopen, exact readback."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import signal
import time
import types

TOOLS = Path('/home/alex/work/pocket4-contacts-session-tools-20261105-r12-01')
ROOT = Path('/home/alex/work/pocket4-contacts-crud-20261105-r12-11')
PUBLIC = TOOLS / 'contacts-crud11-result.json'
PACKAGE = 'com.android.contacts'
PINS = {
    'ui_preflight05.py': '2e99a4d0b2a9f4be7046c3504ec65d754bd91c959cb0f4f1adfe873aa3a16237',
    'session_loop08.py': 'c4a985ddcfe54104a7d90dd4ce8dd44b708016dd44911faa92ac16e3c38a9db3',
    'verify_contact.py': '8b6105eb7e3832577ca9ee55f0b539a233af0f0f67107a0149d5df9cdb8aa681',
}


def require(value, code):
    if not value:
        raise RuntimeError(code)


def load(name):
    path = TOOLS / name
    raw = path.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == PINS[name], 'SOURCE_PIN_CHANGED_' + name)
    module = types.ModuleType('contacts_crud_' + name.replace('.', '_'))
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def expired(signum, frame):
    raise TimeoutError('CRUD_LEASE_EXPIRED_NO_INPUT_REPLAY')


def visible(nodes):
    return [n for n in nodes if n.get('package') == PACKAGE
            and n.get('visible') is True and n.get('enabled') is True]


def one(nodes, predicate, code):
    matches = [n for n in visible(nodes) if predicate(n)]
    require(len(matches) == 1, code)
    return matches[0]


def selector(node):
    result = {}
    for key, native in (('id', 'resource-id'), ('text', 'text'), ('desc', 'content-desc')):
        if node.get(native):
            result[key] = node[native]
    require(result, 'NO_OBSERVED_SEMANTIC_IDENTITY')
    if node.get('class'):
        result['class'] = node['class']
    if node.get('editable') is True:
        result['editable'] = True
    return result


class Flow:
    def __init__(self, trial, loop, verifier, result):
        self.t, self.loop, self.v, self.r = trial, loop, verifier, result
        self.c = loop.Continuation(trial, PACKAGE)
        self.number = 0
        self.deadline = time.monotonic() + 240
        self.created = None
        self.owned_tasks = []
        self.closed_tasks = []

    def act(self, tag, op, node, value=None):
        require(time.monotonic() < self.deadline and self.number < 24 and self.c.pending is None,
                'UI_DEADLINE_BUDGET_OR_PENDING_EFFECT')
        self.number += 1
        request = {'id': 'c%02d-' % self.number + tag, 'op': op,
                   'observation': self.c.latest, 'selector': selector(node)}
        if value is not None:
            request['value'] = value
        self.c.step(request)
        require(time.monotonic() < self.deadline, 'CRUD_DEADLINE_AFTER_INPUT_READBACK')

    def click(self, tag, node, approved_fixture_label=False, contact_list_marker=False):
        if node.get('clickable') is True:
            self.act(tag, 'click', node)
            return
        require(approved_fixture_label and self.created is not None,
                'NONCLICKABLE_LABEL_HAS_NO_VERIFIED_FIXTURE_SCOPE')
        require(node.get('editable') is False and node.get('password') is False,
                'FIXTURE_LABEL_IS_NOT_A_READONLY_LABEL')
        target = (PACKAGE, node.get('resource-id'), node.get('text'))
        if contact_list_marker:
            require(node.get('resource-id') == PACKAGE + ':id/cliv_name_textview'
                and node.get('text') == node.get('content-desc')
                and node.get('text') in (self.v.NAME, self.v.EDITED), 'OWNED_LIST_MARKER_NOT_EXACT')
            self.c.approved_contact_names = {node['text']}
        else:
            self.c.approved_labels = {target}
        try:
            self.act(tag, 'snapshot-tap', node)
        finally:
            self.c.approved_labels = set()
            self.c.approved_contact_names = set()

    def observe(self, tag):
        self.c.observe(tag)

    def launch(self, tag):
        require(time.monotonic() < self.deadline and self.t.owned is None and self.c.pending is None,
                'LAUNCH_DEADLINE_OR_PREVIOUS_OWNED_TASK_OR_INPUT_UNRESOLVED')
        self.c.pending = 'launch-' + tag
        self.t.launch()
        self.owned_tasks.append(self.t.owned[0])
        self.c.pending = None
        self.observe(tag)

    def close(self):
        if self.t.owned is None:
            return
        task = self.t.owned[0]
        before = self.t.removals
        self.t.close()
        require(self.t.removals == before + 1 and self.t.result.get('other_tasks_preserved') is True,
                'OWNED_CLOSE_NOT_VERIFIED')
        self.closed_tasks.append(task)

    def local_editor(self, expected):
        scope = self.t.last_observation['screenshot']['scope']
        require(scope['package'] == PACKAGE and scope['activity'] == PACKAGE + '.activities.ContactEditorActivity',
                'NOT_THE_OBSERVED_CONTACT_EDITOR_ACTIVITY')
        one(self.c.nodes, lambda n: n.get('resource-id') == PACKAGE + ':id/account_name'
            and n.get('text') == 'Device', 'EDITOR_DESTINATION_IS_NOT_DEVICE')
        one(self.c.nodes, lambda n: n.get('resource-id') == PACKAGE + ':id/account_header_container'
            and n.get('content-desc') == 'Saving to\nDevice', 'EDITOR_LOCAL_HEADER_CHANGED')
        return one(self.c.nodes, lambda n: n.get('editable') is True and n.get('password') is False
            and n.get('hint') == 'First name' and n.get('text') == expected,
            'FIRST_NAME_FIELD_NOT_UNIQUE_OR_EXPECTED')

    def save(self, tag):
        node = one(self.c.nodes, lambda n: n.get('resource-id') == PACKAGE + ':id/editor_menu_save_button'
                   and n.get('text') == 'SAVE' and n.get('clickable') is True, 'OBSERVED_SAVE_NOT_UNIQUE')
        self.click(tag, node)

    def owned(self, name, tag):
        failure = None
        for number in range(3):
            state = self.v.current_state(self.t.s)
            self.t.record(tag + '-readback-' + str(number), state)
            try:
                proof = self.v.validate_owned(state, name, self.created)
                self.r['phases'][tag] = {'state': state, 'proof': proof}
                return state
            except RuntimeError as exc:
                if str(exc) != 'OWNED_NAME_NOT_OBSERVED':
                    raise
                failure = exc
                time.sleep(.2)
        raise failure

    def edited_control(self):
        return [n for n in visible(self.c.nodes) if n.get('clickable') is True
                and str(n.get('content-desc', '')).casefold() in ('edit', 'edit contact')]

    def detail(self, name, tag):
        opened = False
        for number in range(3):
            matches = [n for n in visible(self.c.nodes) if n.get('text') == name
                       and n.get('editable') is not True]
            edits = self.edited_control()
            if matches and len(edits) == 1:
                return edits[0]
            scope = self.t.last_observation['screenshot']['scope']
            if (not opened and scope['activity'] == PACKAGE + '.activities.PeopleActivity'
                    and len(matches) == 1):
                self.owned(name, tag + '-before-open')
                self.click(tag + '-open-fixture', matches[0], approved_fixture_label=True, contact_list_marker=True)
                opened = True
            else:
                self.observe(tag + '-detail-read-' + str(number))
        raise RuntimeError('OWNED_FIXTURE_DETAIL_AND_EDIT_CONTROL_NOT_OBSERVED')

    def deleted(self, tag):
        state = self.v.current_state(self.t.s)
        self.t.record(tag, state)
        if state['marker_rows']:
            return False
        proof = self.v.validate_deleted(state, self.created)
        self.r['phases'][tag] = {'state': state, 'proof': proof}
        return True

    def delete_ui(self):
        self.owned(self.v.EDITED, 'before-delete')
        self.detail(self.v.EDITED, 'delete')
        direct = [n for n in visible(self.c.nodes) if n.get('clickable') is True
                  and str(n.get('text') or n.get('content-desc') or '').casefold() in ('delete', 'delete contact')]
        if len(direct) == 1:
            self.click('delete-option', direct[0])
        else:
            require(len(direct) == 0, 'DELETE_ACTION_AMBIGUOUS')
            menu = one(self.c.nodes, lambda n: n.get('clickable') is True
                       and n.get('content-desc') == 'More options', 'OWNED_DETAIL_MORE_OPTIONS_NOT_UNIQUE')
            state = self.owned(self.v.EDITED, 'before-more-options')
            self.t.bind_owned_contact_menu(self.v.validate_owned(state, self.v.EDITED, self.created))
            self.click('more-options', menu)
            option = one(self.c.nodes, lambda n: str(n.get('text', '')).casefold() in ('delete', 'delete contact'),
                         'OBSERVED_DELETE_MENU_ITEM_NOT_UNIQUE')
            self.click('delete-option', option, approved_fixture_label=True)
        if self.deleted('delete-without-confirmation-readback'):
            return
        for number in range(3):
            nodes = visible(self.c.nodes)
            positive = [n for n in nodes if n.get('class') == 'android.widget.Button'
                        and n.get('clickable') is True and str(n.get('text', '')).casefold() in ('delete', 'delete contact')]
            cancel = [n for n in nodes if n.get('class') == 'android.widget.Button'
                      and n.get('clickable') is True and str(n.get('text', '')).casefold() == 'cancel']
            message = [n for n in nodes if n.get('resource-id') in ('android:id/message', 'android:id/alertTitle')
                       and 'contact' in str(n.get('text', '')).casefold()
                       and 'delet' in str(n.get('text', '')).casefold()]
            if len(positive) == len(cancel) == 1 and message:
                self.owned(self.v.EDITED, 'before-delete-confirmation')
                self.click('confirm-delete', positive[0])
                break
            self.observe('delete-confirmation-read-' + str(number))
        else:
            raise RuntimeError('DELETE_CONFIRMATION_NOT_SOURCE_BOUND_TO_OWNED_CONTACT')
        for number in range(3):
            if self.deleted('ui-delete-final-' + str(number)):
                return
            time.sleep(.2)
        raise RuntimeError('UI_DELETE_DID_NOT_REMOVE_THE_OWNED_MARKER')

    def run(self):
        self.launch('initial')
        create = one(self.c.nodes, lambda n: n.get('resource-id') == PACKAGE + ':id/floating_action_button'
                     and n.get('content-desc') == 'Create new contact', 'OBSERVED_CREATE_NOT_UNIQUE')
        self.click('create', create)
        field = self.local_editor('First name')
        self.act('set-name', 'set-text', field, self.v.NAME)
        self.local_editor(self.v.NAME)
        self.save('save-created')
        self.created = self.owned(self.v.NAME, 'created')
        edit = self.detail(self.v.NAME, 'created')
        self.click('edit-owned', edit)
        field = self.local_editor(self.v.NAME)
        self.act('set-edited-name', 'set-text', field, self.v.EDITED)
        self.local_editor(self.v.EDITED)
        self.save('save-edited')
        self.owned(self.v.EDITED, 'edited')
        self.close()
        self.owned(self.v.EDITED, 'persisted-after-owned-close')
        self.launch('reopen-initial')
        require(len(set(self.owned_tasks)) == 2, 'REOPEN_DID_NOT_CREATE_A_NEW_OWNED_TASK')
        self.owned(self.v.EDITED, 'persisted-after-reopen')
        self.detail(self.v.EDITED, 'persisted')
        self.r['persisted_ui_marker_observed_after_reopen'] = True
        self.delete_ui()
        self.r['state'] = 'LOCAL_CONTACT_CRUD_PERSISTENCE_VERIFIED'

    def cleanup_fixture_on_failure(self):
        """Cleanup only this new marker; this fallback never awards a UI pass."""
        state = self.v.current_state(self.t.s)
        self.t.record('failure-reconcile-contact', state)
        if not state['marker_rows']:
            if self.created is None:
                self.v.validate_before(state)
            else:
                self.v.validate_deleted(state, self.created)
            self.r['fixture_cleanup'] = {'method': 'read-only', 'owned_marker_absent': True}
            return
        name = state['owned']['name_row']['data1']
        proof = self.v.validate_owned(state, name, self.created)
        require(name in (self.v.NAME, self.v.EDITED), 'CLEANUP_MARKER_MISMATCH')
        if self.created is None:
            self.created = state
        raw_id, contact_id = proof['raw_contact_id'], proof['contact_id']
        require(re.fullmatch('[1-9][0-9]*', raw_id) and re.fullmatch('[1-9][0-9]*', contact_id),
                'CLEANUP_NUMERIC_OWNED_ID_REQUIRED')
        where = ('_id=' + raw_id + ' AND contact_id=' + contact_id
                 + ' AND account_name IS NULL AND account_type IS NULL AND data_set IS NULL AND deleted=0')
        command = ['/system/bin/content', 'delete', '--user', '0', '--uri',
                   'content://com.android.contacts/raw_contacts', '--where', where]
        self.t.record('owned-fixture-cleanup-intent', {'argv': command, 'marker': name,
            'proof': proof, 'automatic_retry': False, 'does_not_prove_ui_delete': True})
        receipt = {'method': 'exact-owned-provider-fallback', 'input_calls': 1, 'automatic_retry': False,
                   'original_ui_failure_retained': True, 'does_not_prove_ui_delete': True}
        self.r['fixture_cleanup'] = receipt
        try:
            receipt['stdout'] = self.t.s.android(command, 15).decode('utf-8', 'strict')
        except TimeoutError:
            raise
        except BaseException as exc:
            receipt['command_outcome_unknown'] = type(exc).__name__ + ': ' + str(exc)
        after = self.v.current_state(self.t.s)
        receipt['readback'] = self.v.validate_deleted(after, self.created)
        self.t.record('owned-fixture-cleanup-readback', after)


def execute():
    adapter, loop, verifier = (load(name) for name in PINS)
    tx = adapter.load_session()
    adapter.ROOT = ROOT
    loop.emit = lambda value: None
    result = {'state': 'FAILED', 'phases': {}, 'source_pins': PINS, 'automatic_retry': False,
              'business_success_verified': False, 'whole_app_production_ready': False,
              'marker': verifier.NAME, 'edited_marker': verifier.EDITED, 'lease_seconds': 240,
              'failure_fixture_cleanup_seconds': 35, 'owned_close_cleanup_seconds': 35,
              'max_ui_actions': 24, 'max_contacts_created': 1, 'external_sync_actions': 0}
    old_handler = signal.signal(signal.SIGALRM, expired)
    trial = flow = None
    try:
        signal.setitimer(signal.ITIMER_REAL, 240)
        with tx.ui_lock():
            ROOT.mkdir(mode=0o700)
            with tx.CameraSession(ROOT / 'commands') as session:
                trial = adapter.Trial(session, tx)
                flow = Flow(trial, loop, verifier, result)
                try:
                    verifier.identity(session)
                    result['identity_before'] = verifier.PINS
                    result['epoch_sha256'] = session.epoch_sha256
                    result['account_topology_before'] = verifier.unchanged_account_topology(session)
                    result['contacts_before'] = verifier.current_state(session)
                    verifier.validate_before(result['contacts_before'])
                    result['empty_baseline_verified'] = True
                    flow.run()
                    result['account_topology_after'] = verifier.unchanged_account_topology(session)
                    result['business_success_verified'] = True
                except BaseException as exc:
                    result.update(state='FAILED', error=type(exc).__name__ + ': ' + str(exc))
                    signal.setitimer(signal.ITIMER_REAL, 35)
                    try:
                        if result.get('empty_baseline_verified') is True:
                            flow.cleanup_fixture_on_failure()
                    except BaseException as cleanup_error:
                        result['fixture_cleanup_error'] = type(cleanup_error).__name__ + ': ' + str(cleanup_error)
                finally:
                    signal.setitimer(signal.ITIMER_REAL, 35)
                    flow.close()
                    verifier.identity(session)
                    result['identity_after'] = verifier.PINS
                    session.caller_status('contacts-crud-final-caller')
        if result['business_success_verified']:
            require(len(flow.owned_tasks) == len(flow.closed_tasks) == 2
                    and flow.owned_tasks == flow.closed_tasks and flow.c.pending is None,
                    'SUCCESS_REQUIRES_TWO_VERIFIED_OWNED_CLOSES_AND_NO_PENDING_INPUT')
    except BaseException as exc:
        result.update(state='FAILED', business_success_verified=False,
                      terminal_error=type(exc).__name__ + ': ' + str(exc))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
        result.update(ui_actions=flow.c.actions if flow else 0,
                      pending_effect=flow.c.pending if flow else None,
                      owned_tasks=flow.owned_tasks if flow else [],
                      closed_tasks=flow.closed_tasks if flow else [],
                      owned_task_remove_calls=trial.removals if trial else 0)
        if ROOT.is_dir():
            tx.write_new(ROOT / 'result.json', result)
        tx.write_new(PUBLIC, result, alex_readable=True)
        print(json.dumps({k: result.get(k) for k in ('state', 'error', 'terminal_error',
            'fixture_cleanup_error', 'business_success_verified', 'ui_actions', 'pending_effect',
            'owned_tasks', 'closed_tasks', 'owned_task_remove_calls')}, sort_keys=True))
    return 0 if result['business_success_verified'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if args.execute:
        raise SystemExit(execute())
    print(json.dumps({'state': 'PLAN_ONLY', 'ui_actions': 0, 'contact_writes': 0,
                      'source_pins': PINS, 'public_result': str(PUBLIC)}))
