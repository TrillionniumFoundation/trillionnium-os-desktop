"""Independent new-Main component; no historical Session, Main or execute entry."""
from pathlib import Path
import argparse, copy, hashlib, json, os, re, signal, time, types
PACKAGE = 'com.android.contacts'
WORK_SECONDS, CLEANUP_SECONDS, MAX_INPUTS = (240, 60, 24)

def need(ok, code):
    if not ok:
        raise RuntimeError(code)

def make_flow(base, mouse, evidence_root):

    class SearchFlow(base.Flow):

        def __init__(self, trial, loop, verifier, result):
            super().__init__(trial, loop, verifier, result)
            self.deadline = time.monotonic() + WORK_SECONDS
            self.effect_pending = self.close_pending = self.commit_tag = None
            self.delete_dispatched = self.cleanup_dispatched = False
            self.ownership_journal = False

        def click(self, tag, node, approved_fixture_label=False, contact_list_marker=False):
            if tag == 'open-search-result':
                need(approved_fixture_label and contact_list_marker, 'OWNED_RESULT_SCOPE_REQUIRED')
                return mouse.open_search_result(self, tag, node)
            return super().click(tag, node, approved_fixture_label, contact_list_marker)

        def may_mutate(self):
            need(self.c.pending is None and self.close_pending is None and (self.effect_pending is None), 'UNKNOWN_INPUT_CLOSE_OR_DATABASE_EFFECT_NO_NEW_ACTION')

        def act(self, tag, op, node, value=None):
            need(self.close_pending is None, 'UNRESOLVED_CLOSE_BLOCKS_INPUT')
            commit_owned = self.effect_pending is not None
            if self.effect_pending is not None:
                need(self.commit_tag == tag and self.effect_pending['tag'] == tag, 'UNRESOLVED_DATABASE_EFFECT_BLOCKS_INPUT')
                self.commit_tag = None
            else:
                need(self.commit_tag is None, 'ORPHAN_COMMIT_TAG')
            need(self.number < MAX_INPUTS, 'INPUT_BUDGET_EXHAUSTED')
            attempts = self.c.actions
            try:
                return super().act(tag, op, node, value)
            except BaseException:
                if commit_owned and self.c.actions == attempts and (self.c.pending is None):
                    self.t.record('database-not-dispatched-' + tag, {'original_intent': copy.deepcopy(self.effect_pending), 'native_dispatch_count_unchanged': True, 'automatic_retry': False})
                    self.effect_pending = None
                raise

        def launch(self, tag):
            self.may_mutate()
            need(self.t.owned is None and len(self.owned_tasks) < 2 and (time.monotonic() < self.deadline), 'ONLY_TWO_EXACT_OWNED_LAUNCHES_ALLOWED')
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
            task, calls = (ownership[0], self.t.removals)
            self.close_pending = task
            self.t.record('owned-close-fence', {'task': task, 'automatic_retry': False})
            try:
                self.t.close()
                need(self.t.removals == calls + 1 and self.t.result.get('other_tasks_preserved') is True, 'NORMAL_CLOSE_NOT_VERIFIED')
            except BaseException:
                self.t.owned = ownership
                raise
            self.closed_tasks.append(task)
            self.close_pending = None

        def begin_effect(self, kind, tag, expected_name=None):
            self.may_mutate()
            need(time.monotonic() < self.deadline and (kind == 'cleanup' or self.number < MAX_INPUTS), 'NO_COMMIT_INTENT_AFTER_INPUT_BUDGET')
            self.effect_pending = {'kind': kind, 'tag': tag, 'expected_name': expected_name, 'owned': self.v.validate_owned(self.created, self.created['owned']['name_row']['data1']) if self.created else None, 'automatic_retry': False}
            self.commit_tag = tag
            self.t.record('database-intent-' + tag, copy.deepcopy(self.effect_pending))

        def complete_effect(self, proof):
            need(self.c.pending is None and self.effect_pending is not None and (self.commit_tag is None), 'DATABASE_COMMIT_REQUIRES_ACK_AND_EXACT_READBACK')
            self.t.record('database-readback-' + self.effect_pending['tag'], {'intent': copy.deepcopy(self.effect_pending), 'proof': proof, 'input_ACK_alone_is_not_completion': True})
            self.effect_pending = None

        def owned(self, name, tag):
            state = super().owned(name, tag)
            proof = self.v.validate_owned(state, name, self.created)
            if self.created is None:
                self.created = copy.deepcopy(state)
                self.t.tx.write_new(evidence_root / 'owned-contact-claim.json', {'proof': proof, 'state': state, 'initial_name': self.v.NAME, 'edited_name': self.v.EDITED, 'normal_create_calls': 1})
                self.ownership_journal = True
                self.r['owned_contact_identity'] = proof
            return state

        def save(self, tag):
            expected = {'save-created': self.v.NAME, 'save-edited': self.v.EDITED}.get(tag)
            need(expected is not None, 'ONLY_TWO_DECLARED_SAVE_OPERATIONS')
            node = base.one(self.c.nodes, lambda n: n.get('resource-id') == PACKAGE + ':id/editor_menu_save_button' and n.get('text') == 'SAVE' and (n.get('clickable') is True), 'OBSERVED_SAVE_NOT_UNIQUE')
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
                    self.t.tx.write_new(evidence_root / 'owned-contact-claim.json', {'proof': self.v.validate_owned(state, name), 'state': state, 'reconciled_from_original_intent': True})
                    self.ownership_journal = True
                proof = self.v.validate_owned(state, name, self.created)
            else:
                need(self.created is not None, 'DELETE_HAS_NO_DURABLE_OWNERSHIP')
                proof = self.v.validate_deleted(state, self.created)
            self.complete_effect(proof)

        def search_field(self, expected=None):
            scope = self.t.last_observation['screenshot']['scope']
            need(scope['package'] == PACKAGE and scope['activity'] == PACKAGE + '.activities.PeopleActivity', 'SEARCH_REQUIRES_OWNED_PEOPLE_ACTIVITY')
            node = base.one(self.c.nodes, lambda n: n.get('resource-id') == PACKAGE + ':id/search_view' and n.get('class') == 'android.widget.AutoCompleteTextView' and (n.get('editable') is True) and (n.get('password') is False) and (n.get('hint') == 'Search contacts') and (2097152 in n.get('supported_actions', [])), 'OBSERVED_CONTACTS_SEARCH_INPUT_NOT_UNIQUE')
            if expected is not None:
                need(node.get('text') == expected and node.get('showing-hint') is not True, 'EXACT_QUERY_TEXT_NOT_OBSERVED')
            return node

        def search_same_edited_contact(self):
            self.may_mutate()
            self.owned(self.v.EDITED, 'before-search')
            search = base.one(self.c.nodes, lambda n: n.get('resource-id') == PACKAGE + ':id/menu_search' and n.get('content-desc') == 'Search contacts' and (n.get('clickable') is True), 'OBSERVED_CONTACTS_SEARCH_BUTTON_NOT_UNIQUE')
            self.click('open-search', search)
            field = self.search_field()
            need(not field.get('text') or field.get('showing-hint') is True, 'SEARCH_NOT_EMPTY_AT_THIS_FRESH_START')
            self.act('search-edited-name', 'set-text', field, self.v.EDITED)
            until = min(self.deadline, time.monotonic() + 18)
            matched = None
            for attempt in range(4):
                need(time.monotonic() < until, 'SEARCH_RESULT_READ_BUDGET_EXHAUSTED')
                self.search_field(self.v.EDITED)
                rows = [n for n in base.visible(self.c.nodes) if n.get('resource-id') == PACKAGE + ':id/cliv_name_textview' and n.get('text') == n.get('content-desc') == self.v.EDITED]
                need(len(rows) <= 1, 'SEARCH_RESULT_NOT_UNIQUE')
                if rows:
                    matched = rows[0]
                    break
                if attempt < 3:
                    self.observe('search-result-read-' + str(attempt))
            need(matched is not None, 'SEARCH_DID_NOT_RETURN_SAME_EDITED_CONTACT')
            current = self.owned(self.v.EDITED, 'search-result-identity')
            self.r['search_result'] = {'query': self.v.EDITED, 'observed_node': matched, 'observation': self.c.latest, 'screenshot': self.t.last_observation['screenshot'], 'same_contact': self.v.validate_owned(current, self.v.EDITED, self.created)}
            self.click('open-search-result', matched, approved_fixture_label=True, contact_list_marker=True)
            self.detail(self.v.EDITED, 'searched-detail')
            self.owned(self.v.EDITED, 'searched-detail-same-record')
            self.r['edited_contact_found_by_search_and_reopened'] = True

        def delete_ui(self):
            self.may_mutate()
            need(not self.delete_dispatched, 'DELETE_NOT_REPLAYABLE')
            state = self.owned(self.v.EDITED, 'before-delete')
            self.detail(self.v.EDITED, 'delete')
            menu = base.one(self.c.nodes, lambda n: n.get('clickable') is True and n.get('content-desc') == 'More options', 'OWNED_DETAIL_MORE_NOT_UNIQUE')
            self.t.bind_owned_contact_menu(self.v.validate_owned(state, self.v.EDITED, self.created))
            self.click('more-options', menu)
            option = base.one(self.c.nodes, lambda n: str(n.get('text', '')).casefold() in ('delete', 'delete contact'), 'EXACT_DELETE_MENU_NOT_UNIQUE')
            self.click('delete-option', option, approved_fixture_label=True)
            positive = None
            for attempt in range(3):
                nodes = base.visible(self.c.nodes)
                yes = [n for n in nodes if n.get('class') == 'android.widget.Button' and n.get('clickable') is True and (str(n.get('text', '')).casefold() in ('delete', 'delete contact'))]
                cancel = [n for n in nodes if n.get('class') == 'android.widget.Button' and n.get('clickable') is True and (str(n.get('text', '')).casefold() == 'cancel')]
                message = [n for n in nodes if n.get('resource-id') in ('android:id/message', 'android:id/alertTitle') and 'contact' in str(n.get('text', '')).casefold() and ('delet' in str(n.get('text', '')).casefold())]
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
                time.sleep(0.2)
            raise RuntimeError('UI_DELETE_ACK_NOT_DATABASE_COMPLETION')

        def cleanup_fixture_on_failure(self):
            if self.effect_pending is not None:
                self.reconcile_database_effect()
            self.may_mutate()
            state = self.v.current_state(self.t.s)
            self.t.record('failure-owned-contact-readback', state)
            if not state['marker_rows']:
                if self.created is None:
                    self.v.validate_before(state)
                else:
                    self.v.validate_deleted(state, self.created)
                self.r['fixture_cleanup'] = {'method': 'read-only', 'owned_marker_absent': True}
                return
            need(self.created is not None and self.ownership_journal and (not self.cleanup_dispatched), 'EXACT_PERSISTED_CONTACT_OWNERSHIP_REQUIRED_FOR_CLEANUP')
            name = state['owned']['name_row']['data1']
            proof = self.v.validate_owned(state, name, self.created)
            need(name in (self.v.NAME, self.v.EDITED), 'UNEXPECTED_OWNED_NAME')
            raw_id, contact_id = (proof['raw_contact_id'], proof['contact_id'])
            need(re.fullmatch('[1-9][0-9]*', raw_id) and re.fullmatch('[1-9][0-9]*', contact_id), 'OWNED_IDS_REQUIRED')
            where = '_id=' + raw_id + ' AND contact_id=' + contact_id + ' AND account_name IS NULL AND account_type IS NULL AND data_set IS NULL AND deleted=0'
            argv = ['/system/bin/content', 'delete', '--user', '0', '--uri', 'content://com.android.contacts/raw_contacts', '--where', where]
            self.begin_effect('cleanup', 'exact-owned-fallback')
            self.commit_tag = None
            self.cleanup_dispatched = True
            self.t.record('owned-cleanup-intent', {'argv': argv, 'proof': proof, 'automatic_retry': False, 'does_not_prove_UI_delete': True})
            output = self.t.s.android(argv, 15).decode('utf-8', 'strict')
            after = self.v.current_state(self.t.s)
            proof = self.v.validate_deleted(after, self.created)
            self.complete_effect(proof)
            self.r['fixture_cleanup'] = {'method': 'exact-owned-provider-fallback', 'stdout': output, 'readback': proof, 'does_not_prove_UI_delete': True}

        def run(self):
            self.launch('initial')
            create = base.one(self.c.nodes, lambda n: n.get('resource-id') == PACKAGE + ':id/floating_action_button' and n.get('content-desc') == 'Create new contact', 'OBSERVED_CREATE_NOT_UNIQUE')
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
