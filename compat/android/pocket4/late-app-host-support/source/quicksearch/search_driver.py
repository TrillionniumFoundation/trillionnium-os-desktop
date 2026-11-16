"""Original three QuickSearch gates: live Unicode suggestions, real result handoff, and observed failure branches."""
import copy
import re
import time
from urllib.parse import urlencode

def focus_metadata(raw):
    focus_lines = [line.strip() for line in raw.splitlines() if 'mCurrentFocus=' in line]
    app_lines = [line.strip() for line in raw.splitlines() if 'mFocusedApp=' in line]
    focus = re.findall(r'mCurrentFocus=Window\{([0-9a-fA-F]+)\s+u(\d+)\s+([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)', raw)
    app = re.findall(r'mFocusedApp=ActivityRecord\{[^\n]*?\bu(\d+)\s+([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)\s+t(\d+)\b', raw)
    if len(set(focus_lines)) != 1 or len(set(app_lines)) != 1 or len(set(focus)) != 1 or len(set(app)) != 1:
        return {'verified': False, 'reason': 'FOCUS_OR_ACTIVITY_NOT_UNIQUE', 'focus_lines': focus_lines + app_lines}
    token, user, package, activity = focus[0]
    app_user, app_package, app_activity, task = app[0]
    return {'verified': user == app_user == '0' and package == app_package, 'package': package,
        'activity': activity, 'window_token': token.lower(), 'focused_activity': app_activity,
        'task': int(task), 'user': int(user)}

class Driver:
    def __init__(self, session, result):
        self.s, self.c, self.result = session, session.c, result
        self.h = session.handoff_module
        self.pending = None; self.actions = self.back_inputs = 0
        self.preimages = {}; self.restored = set(); self.query_evidence = []; self.branch_evidence = []
        self.open_evidence = None; self.resolve_url = None; self.latest = None
        session.driver = self
        session.helper.foreground = self.owned_foreground

    def budget(self):
        self.s.guard()
        self.c.need(self.pending is None and self.actions < self.s.active['limits']['maximum_UI_actions'],
            'NO_UNRESOLVED_OR_OVER_BUDGET_SEARCH_INPUT')

    def focus(self, label, *, admit_handoff=False):
        raw = self.s.android(self.c.FOREGROUND, 6).decode('utf-8', 'strict')
        value = focus_metadata(raw); self.s.record(label, {'raw': raw, 'focus': value})
        if admit_handoff:
            return value
        role = self.s.ui_role
        profile = self.s.active['target_profile' if role == 'search' else 'browser_profile']
        task = self.s.primary_task if role == 'search' else None if self.s.handoff is None else self.s.handoff['task']
        expected = self.h.expanded_component(profile['component'])
        self.c.need(value.get('verified') is True and value.get('task') == task and task is not None
            and self.h.expanded_component(value['package'] + '/' + value['activity']) == expected
            and self.h.expanded_component(value['package'] + '/' + value['focused_activity']) == expected,
            'CURRENT_EXACT_OWNED_SEARCH_OR_BROWSER_FOCUS')
        return value

    def owned_foreground(self):
        self.s.verify_current_tasks()
        current = self.focus('owned-api-foreground')
        activity = self.h.expanded_component(current['package'] + '/' + current['activity']).split('/', 1)[1]
        return {'package': current['package'], 'activity': activity, 'window_token': current['window_token']}

    def observe(self, label):
        self.s.verify_current_tasks()
        focus = self.focus(label + '-focus')
        response = self.s.helper.dispatch({'op': 'observe', 'package': focus['package'],
            'window_token': focus['window_token'], 'display': 0, 'accessibility_mode': 'none', 'with_png': True})
        self.s.guard()
        native = response.get('native', {})
        self.c.need(response.get('ok') is True and response.get('outcome_unknown') is not True
            and native.get('ok') is True and native.get('accessibility_mode_restoration_verified') is True
            and type(native.get('nodes')) is list and response['screenshot']['scope']['package'] == focus['package']
            and response['screenshot']['scope']['window_token'] == focus['window_token'], 'ACTUAL_OWNED_SEARCH_UI_OBSERVATION')
        self.latest = {'focus': focus, 'nodes': copy.deepcopy(native['nodes']), 'screenshot': response['screenshot'],
            'actual_api_result': self.s.last_api_receipt}
        self.s.record(label, self.latest)
        return self.latest

    def field(self, observed):
        package = self.s.active['target_profile']['package']
        rows = [n for n in observed['nodes'] if n.get('package') == package
            and n.get('resource-id') == package + ':id/search_src_text' and n.get('visible') is True
            and n.get('enabled') is True and n.get('editable') is True and n.get('password') is False]
        self.c.need(len(rows) == 1 and type(rows[0].get('text')) is str
            and len(rows[0]['text'].encode('utf-8')) <= 4096, 'ONE_ACTUAL_USABLE_UNICODE_QUERY_FIELD')
        return rows[0]

    def set_query(self, value, *, restoring=False):
        self.budget(); observed = self.observe('before-query-input'); node = self.field(observed)
        if node['text'] == value:
            self.s.record('query-already-exact', {'value': value, 'observation': observed['actual_api_result'],
                'input_sent': False, 'restoring': restoring})
            return observed
        profile = self.s.active['target_profile']
        request = {'op': 'set-text', 'package': profile['package'], 'display': 0, 'accessibility_mode': 'none',
            'window_token': observed['focus']['window_token'], 'selector': {'id': profile['package'] + ':id/search_src_text',
                'package': profile['package'], 'editable': True, 'enabled': True}, 'value': value}
        intent = self.s.record('query-edit-intent', {'request': request, 'observed_field': node,
            'before': observed['actual_api_result'], 'restoring': restoring, 'automatic_retry': False})
        self.pending = {'kind': 'query', 'request': request, 'intent': intent, 'restoring': restoring}
        self.actions += 1
        response = self.s.helper.dispatch(request)
        self.s.record('query-edit-response', {'response': response, 'actual_api_result': self.s.last_api_receipt})
        self.c.need(response.get('ok') is True and response.get('performed') == 'set-text'
            and response.get('outcome_unknown') is not True and response.get('readback_verified') is True
            and response.get('password') is False, 'EXACT_NATIVE_UNICODE_READBACK_OR_KEEP_UNKNOWN')
        # Independent visible readback is required even after the native ACK.
        after = self.observe('after-query-input')
        self.c.need(self.field(after)['text'] == value, 'VISIBLE_UNICODE_QUERY_DIFFERS_AFTER_NATIVE_ACK')
        self.pending = None
        return after

    def wait_matches(self, query):
        deadline = min(self.s.deadline, time.monotonic() + 35)
        for index in range(self.s.active['limits']['maximum_read_observations_per_wait']):
            self.c.need(time.monotonic() < deadline, 'LIVE_SEARCH_RESULTS_NOT_AVAILABLE_WITHIN_BOUND')
            observed = self.observe('unicode-results-' + str(index))
            self.c.need(self.field(observed)['text'] == query, 'QUERY_CHANGED_WHILE_AWAITING_REAL_RESULTS')
            rows = self.h.matching_labels(observed['nodes'], self.s.active['target_profile']['package'], query)
            if rows:
                ref = self.s.record('matching-unicode-results', {'query': query, 'matches': rows,
                    'actual_observation': observed['actual_api_result'], 'source': 'actual original Google suggestion UI',
                    'local_results_claimed': False})
                self.query_evidence.append(ref)
                return observed, rows
            time.sleep(.3)
        raise RuntimeError('NO_REAL_MATCHING_UNICODE_RESULT')

    def open_result(self, observed, label, query):
        self.budget(); s, c = self.s, self.c; package = s.active['target_profile']['package']
        binding = self.h.row_binding(observed['nodes'], label, package, query)
        # Read-only resolve uses the exact selected text. Actual opened URL is
        # independently checked below; it is never injected into the browser.
        self.resolve_url = 'https://www.google.com/search?' + urlencode({'q': binding['result_text']})
        resolver = ['/system/bin/cmd', 'package', 'resolve-activity', '--brief', '--user', '0',
            '-a', 'android.intent.action.VIEW', '-d', self.resolve_url]
        resolved = s.android(resolver, 20).decode('utf-8', 'strict').splitlines()
        c.need(len(resolved) == 1 and self.h.expanded_component(resolved[0]) ==
            self.h.expanded_component(s.active['browser_profile']['component']), 'FRESH_UNIQUE_ACTUAL_URL_RECEIVER')
        fresh = self.observe('fresh-result-before-open')
        matches = [n for n in fresh['nodes'] if self.h.stable_node(n) == self.h.stable_node(label)]
        c.need(fresh['focus']['window_token'] == observed['focus']['window_token']
            and len(matches) == 1 and self.h.stable_binding(self.h.row_binding(fresh['nodes'], matches[0], package, query))
            == self.h.stable_binding(binding),
            'KNOWN_RESULT_GEOMETRY_CHANGED_NO_INPUT')
        binding = self.h.row_binding(fresh['nodes'], matches[0], package, query)
        before_roots, before_tasks, before_ref = s.verify_current_tasks()
        shot = fresh['screenshot']; point = binding['coords']; bounds = shot['scope_bounds']
        c.need(bounds[0] <= point[0] < bounds[2] and bounds[1] <= point[1] < bounds[3], 'RESULT_TOUCH_INSIDE_OBSERVED_WINDOW')
        request = {'op': 'snapshot-tap', 'package': package, 'display': 0, 'accessibility_mode': 'none',
            'window_token': fresh['focus']['window_token'], 'input_source': 'touch', 'coords': point,
            **{k: shot[k] for k in ('frame_sha256', 'scope_sha256', 'context_token')}}
        intent = s.record('result-open-intent', {'request': request, 'binding': binding, 'before_tasks': before_ref,
            'actual_resolve_component': resolved[0], 'actual_resolve_url': self.resolve_url, 'automatic_retry': False})
        self.pending = {'kind': 'result', 'request': request, 'binding': binding, 'intent': intent}
        self.actions += 1
        response = s.helper.dispatch(request)
        original_response = s.record('original-result-open-response', {'response': response,
            'actual_api_result': s.last_api_receipt, 'original_outcome_unknown_retained': response.get('outcome_unknown') is True})
        c.need(response.get('ok') is True and response.get('performed') == 'snapshot-tap'
            and response.get('input_command_completed') is True,
            'RESULT_INPUT_COMMAND_UNCERTAIN_NO_REPLAY_NO_HANDOFF_AUTHORITY')
        # Only observations are repeated while the acknowledged handoff settles.
        stop = min(s.deadline, time.monotonic() + 8)
        for _ in range(12):
            focus = self.focus('await-result-browser', admit_handoff=True)
            if focus.get('verified') is True and focus.get('package') == s.active['browser_profile']['package']:
                break
            c.need(time.monotonic() < stop, 'RESULT_BROWSER_FOCUS_DID_NOT_SETTLE')
            time.sleep(.2)
        claim = s.adopt_browser(before_roots, before_tasks, before_ref, response, binding['result_text'], binding)
        browser = self.observe('actual-result-browser')
        urls = [n['text'] for n in browser['nodes'] if n.get('package') == s.active['browser_profile']['package']
            and n.get('resource-id') == s.active['browser_profile']['package'] + ':id/url_field'
            and n.get('visible') is True and n.get('enabled') is True and type(n.get('text')) is str]
        c.need(len(urls) == 1, 'ONE_REAL_OPENED_BROWSER_URL')
        opened = self.h.search_url(urls[0], binding['result_text'])
        # Resolve the actual URL as well, including any original regional host.
        self.resolve_url = urls[0]; actual_resolver = resolver[:-1] + [urls[0]]
        actual_resolved = s.android(actual_resolver, 20).decode('utf-8', 'strict').splitlines()
        c.need(actual_resolved == resolved, 'ACTUAL_OPENED_URL_HANDLER_CHANGED')
        rendered = None; render_deadline = min(s.deadline, time.monotonic() + 35)
        for index in range(s.active['limits']['maximum_read_observations_per_wait']):
            try:
                rendered = self.h.rendered_result(browser['nodes'], s.active['browser_profile']['package'], query)
                break
            except RuntimeError as error:
                if str(error) == 'BROWSER_ERROR_PAGE_IS_NOT_OPENED_RESULT_CONTENT':
                    raise
                c.need(time.monotonic() < render_deadline, 'ACTUAL_RESULT_PAGE_RENDER_DEADLINE')
                time.sleep(.3); browser = self.observe('result-document-readback-' + str(index))
        c.need(rendered is not None, 'ADDRESS_BAR_WITHOUT_RENDERED_RESULT_IS_NOT_BUSINESS_SUCCESS')
        self.open_evidence = s.record('known-result-opened', {'opened': opened, 'query_before_open': query,
            'known_result': binding, 'actual_handoff': s.handoff_ref, 'actual_browser': browser['actual_api_result'],
            'actual_rendered_document': rendered,
            'original_input_response': original_response, 'source_query_not_injected_into_browser': True,
            'native_launch_claim_for_browser': False, 'business_success_verified': False})
        self.pending = None
        self.back(query)

    def back(self, query):
        self.budget(); s, c = self.s, self.c
        c.need(s.ui_role == 'browser' and s.handoff is not None and self.open_evidence is not None
            and self.back_inputs == 0, 'ONE_RETURN_FROM_PROVEN_KNOWN_RESULT')
        observed = self.observe('before-browser-back'); focus = observed['focus']
        request = {'package': focus['package'], 'window_token': focus['window_token'], 'display': 0, 'accessibility_mode': 'none'}
        frame = s.helper.capture(request)
        snapshot = {**request, **{k: frame['meta'][k] for k in ('frame_sha256', 'scope_sha256', 'context_token')}}
        s.helper.validate_snapshot(snapshot, frame)
        current = s.helper.window_state(focus['package'], focus['window_token'], 0, 'none')
        c.need(s.helper.stable_window(current) == s.helper.stable_window(frame['meta']['scope'])
            and self.focus('last-browser-back-focus') == focus, 'FRESH_EXACT_BROWSER_WINDOW_BEFORE_RETURN')
        intent = s.record('browser-back-intent', {'argv': ['/system/bin/input', 'keyboard', '-d', '0', 'keyevent', 'KEYCODE_BACK'],
            'focus': focus, 'handoff': s.handoff_ref, 'actual_open': self.open_evidence, 'automatic_retry': False})
        self.pending = {'kind': 'back', 'focus': focus, 'intent': intent, 'sent': False}
        self.actions += 1; self.back_inputs += 1
        s.android(['/system/bin/input', 'keyboard', '-d', '0', 'keyevent', 'KEYCODE_BACK'], 12)
        deadline = min(s.deadline, time.monotonic() + 8); returned = False
        for _ in range(12):
            now = self.focus('readback-after-browser-back', admit_handoff=True)
            if now.get('verified') is True and now.get('task') == s.primary_task \
                    and now.get('package') == s.active['target_profile']['package']:
                returned = True; break
            c.need(time.monotonic() < deadline, 'BACK_DID_NOT_RETURN_TO_ORIGINAL_QUERY_TASK')
            time.sleep(.2)
        c.need(returned, 'ONE_BACK_COMPLETION_UNVERIFIED_NO_REPEAT')
        s.remove_owned('browser'); s.ui_role = 'search'
        after = self.observe('query-state-after-result-return')
        c.need(self.field(after)['text'] == query, 'QUERY_STATE_CHANGED_AFTER_BROWSER_RETURN')
        self.result['result_return'] = s.record('result-return-verified', {'opened': self.open_evidence,
            'back_intent': intent, 'query': query, 'actual_return': after['actual_api_result'],
            'same_native_search_task': s.primary_task, 'browser_task_retired': True})
        self.pending = None

    def branch(self, query):
        s, c = self.s, self.c
        before = s.android(s.branch_log_command(), 15).decode('utf-8', 'strict')
        since = int(s.android(['/system/bin/date', '+%s'], 8).decode().strip())
        c.need(abs(time.time() - since) <= 3, 'ACTUAL_GUEST_QUERY_BRANCH_CLOCK')
        self.set_query(query)
        deadline = min(s.deadline, time.monotonic() + 35); last_error = None
        for index in range(s.active['limits']['maximum_read_observations_per_wait']):
            observed = self.observe('failure-branch-ui-' + str(index))
            c.need(self.field(observed)['text'] == query, 'FAILURE_BRANCH_QUERY_FIELD_UNUSABLE')
            raw = s.android(s.branch_log_command(), 15).decode('utf-8', 'strict')
            until = int(s.android(['/system/bin/date', '+%s'], 8).decode().strip())
            s.record('actual-branch-log-' + str(index), {'before': before, 'after': raw, 'since': since, 'until': until})
            try:
                branch = self.h.branch_lines(raw, since, until, s.kind, before=before)
            except RuntimeError as error:
                last_error = str(error)
                if time.monotonic() >= deadline:
                    break
                time.sleep(.3); continue
            labels = [n for n in observed['nodes'] if n.get('resource-id') == s.active['target_profile']['package'] + ':id/text1'
                and n.get('visible') is True and n.get('enabled') is True and n.get('text')]
            c.need(not labels, 'ORIGINAL_FAILURE_BRANCH_MUST_NOT_SHOW_STALE_RESULTS')
            branch_ref = s.record('actual-app-failure-branch', {'visible_query_at_observation': query, 'branch': branch,
                'usable_query_field': self.field(observed), 'actual_ui': observed['actual_api_result'],
                'query_request_correlation': False, 'current_query_backend_response_verified': False})
            # The original log has no request identity. Establish usability
            # AFTER that actual app branch with new acknowledged edits, without
            # claiming that the log was caused by the displayed query.
            prior_actions = self.actions
            cleared = self.set_query('')
            c.need(self.actions == prior_actions + 1, 'FAILURE_RECOVERY_CLEAR_MUST_BE_NEW_ACKNOWLEDGED_INPUT')
            alternate = next(q for q in s.active['queries'] if q != query)
            edited = self.set_query(alternate)
            c.need(self.actions == prior_actions + 2, 'FAILURE_RECOVERY_UNICODE_MUST_BE_NEW_ACKNOWLEDGED_INPUT')
            self.branch_evidence.append(s.record('usable-ui-after-app-failure', {'actual_branch': branch_ref,
                'new_clear_readback': cleared['actual_api_result'], 'new_unicode_readback': edited['actual_api_result'],
                'unicode_query': alternate, 'same_owned_task': s.primary_task,
                'query_request_correlation': False, 'current_query_backend_response_verified': False,
                'two_new_native_edits_after_observed_branch': True, 'current_query_response_gate_granted': False}))
            return
        raise RuntimeError('ACTUAL_REQUIRED_NETWORK_BRANCH_NOT_OBSERVED:' + str(last_error))

    def close_round(self):
        self.c.need(self.pending is None, 'UNCERTAIN_INPUT_PREVENTS_QUERY_RESTORE_AND_NEXT_ROUND')
        if self.s.handoff is not None:
            self.s.remove_owned('browser')
        if self.s.primary_task is not None:
            self.s.ui_role = 'search'
            preimage = self.preimages[self.s.scope_index]
            self.set_query(preimage, restoring=True)
            after = self.observe('restored-original-query')
            self.c.need(self.field(after)['text'] == preimage, 'ORIGINAL_QUERY_PREIMAGE_NOT_RESTORED')
            self.restored.add(self.s.scope_index)
            self.s.remove_owned('search')

    def cleanup(self):
        # Known task cleanup does not retroactively resolve an UNKNOWN input.
        if self.pending is None:
            self.close_round()
        else:
            if self.s.handoff is not None:
                self.s.remove_owned('browser')
            if self.s.primary_task is not None:
                self.s.remove_owned('search')

    def run(self):
        s, c = self.s, self.c
        for index, query in enumerate(s.active['queries']):
            selected = s.launch(index)
            initial = self.observe('initial-query-' + str(index)); self.preimages[index] = self.field(initial)['text']
            s.record('query-preimage-' + str(index), {'query': self.preimages[index],
                'actual_ui': initial['actual_api_result'], 'native_task': selected})
            self.set_query('')
            empty = self.observe('empty-query-' + str(index))
            c.need(self.field(empty)['text'] == '' and not any(n.get('resource-id') == s.active['target_profile']['package'] + ':id/text1'
                and n.get('visible') is True and n.get('text') for n in empty['nodes']), 'EMPTY_QUERY_MUST_REMAIN_USABLE_WITHOUT_STALE_RESULTS')
            self.result.setdefault('empty_query_paths', []).append(empty['actual_api_result'])
            if s.kind == 'search_online':
                self.set_query(query); observed, matches = self.wait_matches(query)
                if index == 0:
                    self.open_result(observed, matches[0], query)
            else:
                self.branch(query)
            self.close_round()
        c.need(self.pending is None and self.restored == {0, 1} and s.native_tasks == s.closed_native_tasks
            and len(set(s.native_tasks)) == 2 and s.primary_task is None and s.handoff is None,
            'TWO_DISTINCT_REAL_SEARCH_LIFECYCLES_AND_PREIMAGE_RESTORES')
        if s.kind == 'search_online':
            c.need(len(self.query_evidence) == 2 and self.open_evidence is not None and self.back_inputs == 1
                and self.result.get('result_return') is not None
                and s.companion_tasks == s.closed_companion_tasks and len(s.companion_tasks) == 1,
                'LIVE_UNICODE_RESULTS_AND_COMPLETE_KNOWN_RESULT_RETURN')
        else:
            c.need(len(self.branch_evidence) == 2 and not s.companion_tasks and self.back_inputs == 0,
                'TWO_ACTUAL_ORIGINAL_NETWORK_BRANCH_OBSERVATIONS')
        self.result.update(branch_scope_completed=True, unicode_query_evidence=self.query_evidence,
            actual_failure_branch_evidence=self.branch_evidence, original_search_gates_unchanged=True,
            original_failure_gate_complete=False, whole_app_business_accepted=False)
