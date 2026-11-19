"""Independent new-Main component; no historical Session, Main or execute entry."""
from pathlib import Path
import argparse, hashlib, json, os, re, signal, sys, time, types
PROFILE_TX_SHA = 'b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
PROFILE_ACTIVATION_SHA = '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615'
NEW_SHA = 'c8a9d40dbfb3c975748e7c0520515316a5ef573414193e3128efa9ed400665e1'
PROVIDER_SHA = 'eebf12f81981f7d8c59a9b9ed465945818d2ab0208c121d858cbc4e6426f5fff'
READER_SHA = '08400fd889d2373bcefafe60630d0e619dddcb72cb913db4617acb885f2d9705'
ADAPTER_SHA = '21e368ea3369a12339f288eb9f53b1475e555b055289aca782ba5267677e8aca'
ATOMIC_SHA = '1d66de839c05c11983196764d44c518175bc10481cff754b850d6034c8533796'
LEASE_SECONDS = 720
CLEANUP_SECONDS = 90
DRIVER_SHA = '0089da73755fec25fafbb26356a495f0253acb5d2d785e0c05c19a5e37af2bbb'
SEMANTIC_BUTTON_SHA = '7eb435ec8bc555b72f2f82591ea01a580265500e8e18f671140d0a424fecfdc4'
POLICY_SHA = '39ba779c4b81b8fc22487957e3cb501af9a1f5f6dd935e76f83d176828d56e15'
PICKER_SHA = 'c1ac3f5cb26cda0d04f2b2b16ebed06f744b01ce9a29df69aa4a34d77f53902e'
SEGMENTS_SHA = 'a7823b62913c8e187538f543026cd00b52e22044cfc1a0ed27879d0f9b5d9de4'
FIRST_OPEN_SHA = '52a036d242b890905896e9c63ca65acd69e1f09842f0d83ed5fb161ca49a17c9'
NATIVE_PACKAGE = 'local.pocket4.actions.v2'
NATIVE_APK_SHA = 'a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058'
REQUIRED = {'explicit_first_use_local_calendar', 'cancel_unsaved_without_event_write', 'created_in_calendar_ui', 'edited_same_event', 'normal_close_reopen_detail', 'deleted_in_calendar_ui', 'edited_dates_timezone_recurrence', 'later_occurrence_detail_does_not_change_series', 'series_editor_uses_original_start'}

def need(value, reason):
    if not value:
        raise RuntimeError(reason)

def make_flow(m, model, base, probe, policy, picker, segments, prerequisites, emit):

    class CoreFlow(m.Flow):

        def __init__(self, s, tx, base, doc, diag):
            super().__init__(s, tx, base, doc, diag)
            self.model = model.Model(s, self.record)
            self.business_pending = None
            self.policy = policy
            self.picker = picker
            self.diag_chain = segments.Segments(self.diagnostics, diag, self.record)
            self.cleanup_pending = False
            self.cleanup_calls = 0
            self.roles = {}
            self.role_tokens = {}
            self.scrolls = 0
            self.result = {'schema': 'calendar-owned-recurrence-ui-v1', 'state': 'FAILED', 'started_utc': m.stamp(), 'run_id': model.RUN, 'candidate_apk_sha256': NEW_SHA, 'gates': {}, 'ui_roles': [], 'historical_transport_sha256': PROFILE_TX_SHA, 'historical_activation_sha256': PROFILE_ACTIVATION_SHA, 'automatic_retry': False, 'whole_app_production_ready': False, 'package_mutations': 0, 'permission_changes': 0, 'account_operations': 0, 'helper_event_writes': 0, 'provider_write_commands_excluding_empty_calendar_cleanup': 0, 'reader_sha256': READER_SHA, 'private_adapter_sha256': ADAPTER_SHA, 'atomic_empty_delete_review_sha256': ATOMIC_SHA, 'lease_seconds': LEASE_SECONDS, 'cleanup_seconds': CLEANUP_SECONDS}

        def setup(self):
            self.result['guard_before'] = self.s.guard()
            self.result['fresh_prerequisites'] = prerequisites.verify(self.s, self.result['guard_before'])
            self.result['calendar_before'] = self.calendar_identity()
            self.result['provider_before'] = self.doc.identity(self.s, 'com.android.providers.calendar', PROVIDER_SHA, 10017, 37)
            self.result['existing_shell_calendar_permissions'] = self.shell_grants()
            roots, tasks = self.ui.stacks('first-use-baseline')
            need(not any((c['component'].split('/')[0] in (m.CALENDAR, m.PACKAGE) for r in roots.values() for c in r['children'])), 'PREEXISTING_CALENDAR_TASK')
            self.ui.baseline = set(tasks)
            self.result['baseline_task_ids'] = sorted(tasks)
            self.baseline_counts = self.counts('first-use-baseline')
            need(not any(self.baseline_counts.values()), 'FRESH_ZERO_CALENDAR_BASELINE')
            value = self.model.read('baseline')
            self.model.require_empty(value)
            self.before_diag = self.diagnostics.diagnostics('before', 10061)
            now = self.before_diag['guest_seconds']
            need(type(now) in (int, float), 'GUEST_TIME_REQUIRED')
            begin = (int(now) // 86400 + 8) * 86400000 + 12 * 3600000
            self.lease = {'dtstart': begin, 'dtend': begin + 2700000, 'calendar_id': -1, 'event_id': -1}
            self.result['intended_event'] = {'title': model.TITLE, 'edited_title': model.EDITED, 'begin_utc_ms': begin, 'end_utc_ms': begin + 2700000, 'reminders': 0, 'attendees': 0}
            self.result['host_series_preflight'] = model.preflight_series(begin, begin + 2700000)
            self.result['host_preflight_before_first_UI_launch'] = True
            self.phase = 'FIRST_USE'
            self.ui.launch()
            self.observe('first-use-calendar')

        def shell_grants(self):
            raw = self.s.android(['/system/bin/pm', 'list', 'packages', '-U', '--user', '0', 'com.android.shell'], 12).decode()
            need([line for line in raw.splitlines() if line.startswith('package:com.android.shell ')] == ['package:com.android.shell uid:2000'], 'ACTUAL_SHELL_UID_REQUIRED')
            rows = probe.shared_shell_permission_rows(self.s.android(['/system/bin/dumpsys', 'package', 'com.android.shell'], 15).decode())
            need(all((m.permission_granted(rows, name) for name in m.GRANTS)), 'EXISTING_SHELL_CALENDAR_GRANTS_REQUIRED')
            return [row for row in rows if any((row.startswith(name + ':') for name in m.GRANTS))]

        def snapshot(self, label):
            value = self.model.read(label)
            emit({'type': 'owned-provider-observation', 'phase': self.phase, 'value': value, 'business_pending': self.business_pending, 'ui_pending': self.ui.pending})
            return value

        def wait_state(self, kind):
            deadline = time.monotonic() + 35
            for attempt in range(6):
                value = self.model.read('verify-' + kind + '-' + str(attempt + 1))
                try:
                    if kind in ('calendar', 'cancel', 'deleted'):
                        self.model.require_no_event(value)
                    elif kind in ('edited', 'reopened'):
                        self.model.require_series(value)
                    else:
                        self.model.require_event(value, model.TITLE, self.lease['dtstart'], self.lease['dtend'])
                    return value
                except RuntimeError:
                    if attempt == 5 or time.monotonic() + 15 > deadline:
                        raise
                    time.sleep(0.4)
            raise RuntimeError('PROVIDER_STATE_NOT_OBSERVED')

        def finish_business(self, role, proof):
            need(self.business_pending is not None and self.business_pending['role'] == role, 'EXACT_PENDING_BUSINESS_ROLE_REQUIRED')
            token = self.business_pending['token']
            if token in self.ui.pending:
                old = self.ui.pending[token]
                need(old.get('kind') == 'tap', 'UNKNOWN_NONBUSINESS_INPUT_RETAINED')
                self.record('business-input-readback-reconciled', {'token': token, 'original_pending': old, 'proof': proof, 'action_replayed': False, 'original_ack_rewritten': False})
                del self.ui.pending[token]
            need(not self.ui.pending, 'ANOTHER_INPUT_STILL_PENDING')
            self.business_pending = None

        def role_node(self, role, kind, node, value):
            text = node.get('text')
            hint = node.get('hint')
            desc = node.get('content-desc')
            activity = self.obs['focus']['activity']
            if role in policy.NEW_ROLES:
                need(kind == 'tap' and value is None and (self.phase == 'EDITING'), 'ONLY_OWNED_SERIES_PICKER')
                position = policy.CHAIN.index(role)
                need(self.roles.get(policy.CHAIN[position - 1]) == 1, 'PICKER_ROLE_ORDER')
                target, _ = policy.picker(role, self.obs, self.model.series)
                need(node == target, 'PICKER_TARGET_NOT_FROM_CURRENT_EXACT_OBSERVATION')
                return
            if role == 'open-series-probe':
                need(kind == 'tap' and value is None and (self.phase == 'REOPENED') and (activity == m.INFO) and (node.get('class') == 'android.widget.Button') and (text == 'Edit series'), 'EXACT_LATER_OCCURRENCE_EDIT_SERIES_ENTRY')
                return
            if role == 'cancel-series-probe':
                need(kind == 'tap' and value is None and (self.phase == 'SERIES_PROBE') and (activity in (m.EDITOR, m.EDITOR_ALIAS)) and (node.get('class') == 'android.widget.Button') and (text == 'Cancel'), 'UNMODIFIED_SERIES_PROBE_CANCEL_ONLY')
                return
            if role == 'scroll-form':
                need(kind in ('scroll-forward', 'scroll-backward') and value is None and (self.scrolls < 8) and (node.get('scrollable') is True) and (node.get('class') == 'android.widget.ScrollView') and (activity in (m.EDITOR, m.EDITOR_ALIAS, m.INFO)), 'OBSERVED_OWNED_FORM_SCROLL_ONLY')
                return
            buttons = {'open-new': {'New event'}, 'local-open': {'Create local calendar'}, 'local-confirm': {'Create'}, 'cancel-open': {'Cancel'}, 'cancel-confirm': {'Discard'}, 'save-create': {'Save'}, 'open-edit': {'Edit'}, 'save-edit': {'Save'}, 'delete-open': {'Delete'}, 'delete-confirm': {'Delete'}}
            if kind == 'set-text':
                need(node.get('editable') is True and node.get('password') is not True, 'OWNED_EDITABLE_FIELD_REQUIRED')
                allowed = {'local-name': model.CALENDAR_LABEL, 'cancel-title': model.UNSAVED, 'edit-title': model.EDITED}
                need(role in allowed and value == allowed[role], 'ONLY_REVIEWED_OWNED_TEXT')
                if role == 'local-name':
                    need(hint == 'Calendar name' or text == 'On this device', 'LOCAL_NAME_FIELD')
                elif role == 'cancel-title':
                    need(hint == 'Title' or text == 'Title', 'UNSAVED_TITLE_FIELD')
                else:
                    need(text == model.TITLE and activity in (m.EDITOR, m.EDITOR_ALIAS), 'EXACT_EXISTING_TITLE_FIELD')
                return
            need(kind == 'tap' and value is None, 'TAP_OR_REVIEWED_TEXT_ONLY')
            if role == 'open-menu':
                need(activity == m.MAIN and desc == 'More options', 'OWNED_MAIN_OVERFLOW_ONLY')
                return
            if role in ('focus-cancel-title', 'focus-local-name', 'focus-edit-title'):
                need(node.get('editable') is True and (role == 'focus-cancel-title' and (hint == 'Title' or text == 'Title') or (role == 'focus-local-name' and (hint == 'Calendar name' or text == 'On this device')) or (role == 'focus-edit-title' and text == model.TITLE)), 'EXACT_OWNED_FOCUS_FIELD')
                return
            need(role in buttons and (text in buttons[role] or desc in buttons[role]), 'OBSERVED_SEMANTIC_ROLE_MISMATCH')
            need(node.get('clickable') is True, 'CLICKABLE_ROLE_REQUIRED')
            if role == 'open-new':
                need(activity == m.MAIN, 'MAIN_NEW_EVENT_ENTRY_REQUIRED')
            elif role in ('open-edit', 'delete-open'):
                need(activity == m.INFO, 'OWNED_DETAIL_ACTION_REQUIRED')
            else:
                need(activity in (m.EDITOR, m.EDITOR_ALIAS, m.INFO), 'CALENDAR_EDITOR_OR_DETAIL_REQUIRED')
            if role == 'local-confirm':
                need(self.roles.get('local-name') == 1, 'OWNED_LOCAL_LABEL_REQUIRED')
            if role == 'cancel-open':
                need(self.roles.get('cancel-title') == 1, 'ACTUAL_UNSAVED_FORM_CHANGE_REQUIRED')
            if role == 'save-edit':
                need(all((self.roles.get(r) == 1 for r in policy.NEW_ROLES | {'edit-title'})), 'ALL_REVIEWED_SERIES_CHANGES_REQUIRED')
                self.result['edited_form_before_save'] = policy.form_proof(self.obs, self.model.series, model.EDITED)
                unchanged = self.model.read('before-series-save')
                self.model.require_event(unchanged, model.TITLE, self.lease['dtstart'], self.lease['dtend'])
            if role == 'delete-confirm':
                need(any((n.get('resource-id') == 'android:id/alertTitle' and n.get('text') == 'Delete the entire repeating series?' for n in self.obs['nodes'])), 'EXPLICIT_WHOLE_SERIES_DELETE_CONFIRMATION_REQUIRED')
            if role.endswith('confirm'):
                need(node.get('resource-id') == 'android:id/button1', 'POSITIVE_CONFIRMATION_BUTTON_REQUIRED')

        def input_step(self, c):
            need(self.business_pending is None and (not self.ui.pending), 'UNKNOWN_INPUT_READ_ONLY_UNTIL_RECONCILED')
            need(c.get('view') == self.view_id and self.obs is not None, 'LATEST_SNAPSHOT_TOKEN_REQUIRED')
            index = c.get('node')
            need(type(index) is int and 0 <= index < len(self.obs['nodes']), 'OBSERVED_NODE_INDEX')
            role = c.get('role')
            kind = c.get('kind', 'tap')
            node = self.obs['nodes'][index]
            value = c.get('value')
            allowed = {'FIRST_USE': {'open-new', 'open-menu', 'local-open', 'local-name', 'focus-local-name', 'local-confirm'}, 'CANCELLING': {'focus-cancel-title', 'cancel-title', 'cancel-open', 'cancel-confirm'}, 'CREATING': {'save-create'}, 'CREATED': {'open-edit'}, 'EDITING': {'focus-edit-title', 'edit-title', 'save-edit'} | policy.NEW_ROLES, 'REOPENED': {'delete-open', 'delete-confirm', 'open-series-probe'}, 'SERIES_PROBE': {'cancel-series-probe'}}
            if self.phase in allowed:
                allowed[self.phase].add('scroll-form')
            need(role in allowed.get(self.phase, set()) and (role == 'scroll-form' or self.roles.get(role, 0) == 0), 'ONE_ROLE_IN_CURRENT_PHASE_NO_REPLAY')
            self.role_node(role, kind, node, value)
            token = 'core-' + c['id']
            business = role in ('local-confirm', 'save-create', 'save-edit', 'delete-confirm')
            if business:
                self.business_pending = {'role': role, 'token': token}
            self.record('role-intent', {'role': role, 'phase': self.phase, 'token': token, 'node': node, 'kind': kind, 'value': value, 'business_write_expected': business, 'automatic_retry': False})
            if role == 'open-menu':
                base.FILES = m.MAIN
            try:
                if role in policy.MOUSE_ROLES:
                    target, context = policy.picker(role, self.obs, self.model.series)
                    if role == 'repeat-open':
                        base.FILES = activity = self.obs['focus']['activity']
                    picker.input(self.ui, self.obs, token, target, role, context, popup=role == 'repeat-open')
                elif role in policy.DATE_CONFIRM_ROLES:
                    target, context = policy.picker(role, self.obs, self.model.series)
                    self.ui.input(self.obs, token, target, kind=kind, value=value, semantic_context=context)
                else:
                    self.ui.input(self.obs, token, node, kind=kind, value=value, popup=role == 'open-menu')
            except BaseException:
                if token not in self.ui.pending:
                    if business:
                        self.business_pending = None
                else:
                    self.roles[role] = self.roles.get(role, 0) + 1
                    self.role_tokens[role] = token
                    if role == 'scroll-form':
                        self.scrolls += 1
                raise
            self.roles[role] = self.roles.get(role, 0) + 1
            self.role_tokens[role] = token
            if role == 'scroll-form':
                self.scrolls += 1
            self.result['ui_roles'].append({'role': role, 'token': token, 'kind': kind, 'phase': self.phase})
            self.observe('after-' + c['id'])
            if role == 'open-edit':
                need(self.obs['focus']['activity'] in (m.EDITOR, m.EDITOR_ALIAS), 'EDITOR_ROUTE_NOT_OBSERVED')
                self.phase = 'EDITING'
            if role == 'open-series-probe':
                form = policy.form_proof(self.obs, self.model.series, model.EDITED, keep_original=True)
                value = self.model.read('series-editor-readonly')
                self.model.require_series(value)
                self.result['series_editor_probe'] = {'form': form, 'provider': value, 'mutations': 0}
                self.phase = 'SERIES_PROBE'
            if role == 'cancel-series-probe':
                need(self.obs['focus']['activity'] == m.INFO, 'SERIES_CANCEL_DID_NOT_RETURN_TO_DETAIL')
                value = self.model.read('after-series-probe-cancel')
                self.model.require_series(value)
                self.result['gates']['series_editor_uses_original_start'] = {'series_editor': self.result['series_editor_probe'], 'after_cancel_provider': value, 'series_row_unchanged': True, 'no_series_probe_save': True}
                self.phase = 'REOPENED'

        def verify(self, kind):
            if kind == 'calendar':
                need(self.phase == 'FIRST_USE' and self.roles.get('local-confirm') == 1, 'UI_LOCAL_CREATE_REQUIRED')
                value = self.wait_state('calendar')
                self.finish_business('local-confirm', value)
                self.lease['calendar_id'] = self.model.calendar['_id']
                self.result['gates']['explicit_first_use_local_calendar'] = value
                self.phase = 'CANCELLING'
                self.observe('created-calendar-empty-event-form')
                return
            if kind == 'cancel':
                need(self.phase == 'CANCELLING' and self.roles.get('cancel-open') == self.roles.get('cancel-confirm') == 1, 'UI_CANCEL_AND_DISCARD_REQUIRED')
                value = self.wait_state('cancel')
                need(not self.ui.pending, 'CANCEL_INPUT_STILL_UNKNOWN')
                need(self.observe('cancel-returned-to-calendar')['focus']['activity'] == m.MAIN, 'CANCEL_DID_NOT_RETURN_TO_CALENDAR')
                self.result['gates']['cancel_unsaved_without_event_write'] = value
                self.phase = 'CREATING'
                self.route('insert')
                return
            if kind == 'created':
                need(self.phase == 'CREATING' and self.roles.get('save-create') == 1, 'UI_CREATE_SAVE_REQUIRED')
                value = self.wait_state('created')
                self.finish_business('save-create', value)
                self.event_id = self.model.event_id
                self.lease['event_id'] = self.event_id
                self.result['gates']['created_in_calendar_ui'] = value
                oracle = self.result['host_series_preflight']
                need(value['events'][0]['eventTimezone'] == oracle['input_event']['eventTimezone'], 'CREATED_EVENT_TIMEZONE_DIFFERS_FROM_PREFLIGHT')
                self.model.series = model.series_plan(value['events'][0])
                need(self.model.series == oracle['plan'], 'ACTUAL_EVENT_SERIES_PLAN_DIFFERS_FROM_PREFLIGHT')
                self.result['intended_series'] = dict(self.model.series)
                self.phase = 'CREATED'
                self.route('view')
                return
            if kind == 'edited':
                need(self.phase == 'EDITING' and self.roles.get('save-edit') == 1, 'UI_EDIT_SAVE_REQUIRED')
                value = self.wait_state('edited')
                self.finish_business('save-edit', value)
                self.result['gates']['edited_same_event'] = value
                self.result['gates']['edited_dates_timezone_recurrence'] = {'provider': value, 'expected': self.model.series, 'actual_form_before_save': self.result['edited_form_before_save']}
                self.phase = 'EDITED'
                return
            if kind == 'deleted':
                need(self.phase == 'REOPENED' and self.roles.get('delete-open') == self.roles.get('delete-confirm') == 1, 'UI_DELETE_CONFIRMATION_REQUIRED')
                value = self.wait_state('deleted')
                self.finish_business('delete-confirm', value)
                self.result['gates']['deleted_in_calendar_ui'] = value
                self.phase = 'DELETED'
                return
            raise RuntimeError('VERIFICATION_KIND_NOT_ALLOWED')

        def reopen(self):
            need(self.phase == 'EDITED' and (not self.business_pending) and (not self.ui.pending), 'EDIT_NOT_VERIFIED_BEFORE_CLOSE')
            self.ui.close_all()
            need(self.ui.removals == len(self.ui.closed) == 1, 'ONE_NORMAL_CLOSE_REQUIRED')
            value = self.wait_state('edited')
            self.record('closed-series-persistence', value)
            occurrence = self.model.second_occurrence()
            self.ui.launch()
            original_lease = dict(self.lease)
            try:
                self.lease = {**self.lease, 'dtstart': occurrence['begin'], 'dtend': occurrence['end']}
                self.route('view')
            finally:
                self.lease = original_lease
            observed = self.observe('reopened-exact-second-occurrence')
            plan = self.model.series
            day = plan['second_date_text']
            summary = day + ' 12:00 PM – ' + day + ' 12:45 PM · ' + plan['timezone']
            need(observed['focus']['activity'] == m.INFO and all((any((n.get('text') == text for n in observed['nodes'])) for text in (model.EDITED, summary, 'Repeating event.', 'Edit series'))), 'EXACT_LATER_OCCURRENCE_DATE_TIME_OR_SERIES_UI_NOT_VISIBLE')
            value = self.wait_state('reopened')
            self.result['gates']['normal_close_reopen_detail'] = {'provider': value, 'owned_task': observed['focus']['task'], 'expected_detail_summary': summary}
            self.result['gates']['later_occurrence_detail_does_not_change_series'] = {'actual_instance': occurrence, 'provider_after_view': value, 'expected_detail_summary': summary, 'series_original_dtstart': plan['dtstart'], 'selected_occurrence_begin': occurrence['begin']}
            self.phase = 'REOPENED'

        def step(self, c):
            need(isinstance(c, dict) and (not set(c) - {'id', 'op', 'view', 'node', 'kind', 'value', 'role'}), 'COMMAND_SCHEMA')
            ident = c.get('id')
            need(isinstance(ident, str) and re.fullmatch('[a-z][a-z0-9-]{0,39}', ident) and (ident not in self.seen) and (len(self.seen) < 48), 'UNIQUE_BOUNDED_COMMAND_ID')
            self.seen.add(ident)
            self.record('command-' + ident, c)
            op = c.get('op')
            if op == 'abort':
                return False
            if op == 'observe':
                observed = self.observe('observe-' + ident)
                if self.phase == 'CREATED' and self.roles.get('open-edit') == 1 and (not self.ui.pending) and (observed['focus']['activity'] in (m.EDITOR, m.EDITOR_ALIAS)):
                    self.phase = 'EDITING'
                return True
            if op == 'inspect':
                self.snapshot(ident)
                return True
            if op == 'input':
                self.input_step(c)
                return True
            if op in ('verify-calendar', 'verify-cancel', 'verify-created', 'verify-edited', 'verify-deleted'):
                self.verify(op[7:])
                return True
            if op == 'reopen':
                self.reopen()
                return True
            need(op == 'finish' and self.phase == 'DELETED' and (set(self.result['gates']) == REQUIRED) and (not self.business_pending) and (not self.ui.pending), 'ALL_CORE_GATES_REQUIRED')
            self.result['business_scope_completed'] = True
            return False

        def cleanup(self):
            result = {'errors': [], 'calendar_removed': False, 'provider_baseline_restored': False}
            try:
                self.ui.close_all()
            except BaseException as exc:
                result['errors'].append('owned-task:' + type(exc).__name__ + ':' + str(exc))
            try:
                need(not self.ui.owned and (not self.ui.pending) and (not self.business_pending) and (not self.cleanup_pending), 'UNKNOWN_EFFECT_RETAIN_OWNED_FIXTURE')
                value = self.model.read('before-empty-calendar-cleanup')
                if self.model.calendar is None:
                    self.model.require_empty(value)
                    result['calendar_removed'] = True
                else:
                    self.model.require_no_event(value)
                    need('deleted_in_calendar_ui' in self.result['gates'] or self.roles.get('save-create', 0) == 0, 'EVENT_UI_DELETE_NOT_VERIFIED_RETAIN_FIXTURE')
                    uri, where = self.model.deletion_request()
                    need(self.shell_grants() == self.result['existing_shell_calendar_permissions'], 'SHELL_CALENDAR_GRANTS_CHANGED')
                    argv = ['/system/bin/content', 'query', '--user', '0', '--uri', uri, '--projection', '_id', '--where', where]
                    raw = self.s.android(argv, 15).decode()
                    need(raw == 'Row: 0 _id=' + str(self.model.calendar['_id']) + '\n', 'FRESH_GUARDED_CALENDAR_NOT_UNIQUE')
                    self.ui.check_tasks('before-empty-calendar-cleanup')
                    request = ['/system/bin/content', 'delete', '--user', '0', '--uri', uri, '--where', where]
                    self.record('empty-calendar-cleanup-intent', {'argv': request, 'calendar': self.model.calendar, 'expected_events': 0, 'automatic_retry': False, 'provider_internal_side_effect': 'May schedule unsubscribe for this same unregistered LOCAL account; no external account or sync API is used.'})
                    self.cleanup_pending = True
                    self.cleanup_calls += 1
                    output = self.s.android(request, 20).decode()
                    self.record('empty-calendar-cleanup-ack', {'stdout': output})
                    value = self.model.read('after-empty-calendar-cleanup')
                    self.model.require_empty(value)
                    self.cleanup_pending = False
                    result['calendar_removed'] = True
                result['provider_baseline_restored'] = True
            except BaseException as exc:
                result['errors'].append('fixture:' + type(exc).__name__ + ':' + str(exc))
            return result
    return CoreFlow
