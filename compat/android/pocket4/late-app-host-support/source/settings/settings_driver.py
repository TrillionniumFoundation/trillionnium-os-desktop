"""Observe five pages and an explicitly bounded native auto-rotate roundtrip."""
import copy
import time

class Driver:
    def __init__(self, session, result):
        self.s, self.c, self.result = session, session.c, result
        self.model = session.model; self.pending = None; self.actions = self.routes = 0
        self.latest = None; self.preimage = None; self.changed_state = None
        self.dirty = False; self.restored = False; self.roundtrip_evidence = []
        self.page_evidence = []; self.interface_evidence = []; self.closed_rounds = []
        session.driver = self; session.helper.foreground = self.owned_foreground

    def budget(self):
        self.s.guard()
        self.c.need(self.pending is None, 'UNRESOLVED_SETTINGS_INPUT_NO_REPLAY')

    def focus(self, label):
        raw = self.s.android(self.c.FOREGROUND, 6).decode('utf-8', 'strict')
        value = self.model.focus_metadata(raw); self.s.record(label, {'raw': raw, 'focus': value})
        expected = self.model.expanded_component(self.s.current_component)
        self.c.need(value.get('verified') is True and value.get('task') == self.s.primary_task
            and self.s.primary_task is not None
            and self.model.expanded_component(value['package'] + '/' + value['activity']) == expected
            and self.model.expanded_component(value['package'] + '/' + value['focused_activity']) == expected,
            'EXACT_CURRENT_SETTINGS_COMPONENT_TASK_AND_WINDOW')
        return value

    def owned_foreground(self):
        self.s.verify_current_tasks(); value = self.focus('owned-api-foreground')
        return {'package': value['package'],
            'activity': self.model.expanded_component(value['package'] + '/' + value['activity']).split('/', 1)[1],
            'window_token': value['window_token']}

    def observe(self, label):
        self.s.verify_current_tasks(); focus = self.focus(label + '-focus')
        response = self.s.helper.dispatch({'op': 'observe', 'package': 'com.android.settings',
            'window_token': focus['window_token'], 'display': 0, 'accessibility_mode': 'none', 'with_png': True})
        self.s.guard(); native = response.get('native', {})
        self.c.need(response.get('ok') is True and response.get('outcome_unknown') is not True
            and native.get('ok') is True and native.get('accessibility_mode_restoration_verified') is True
            and type(native.get('nodes')) is list
            and response['screenshot']['scope']['package'] == 'com.android.settings'
            and response['screenshot']['scope']['window_token'] == focus['window_token'],
            'ACTUAL_SETTINGS_UI_AND_SCREENSHOT_REQUIRED')
        self.latest = {'focus': focus, 'nodes': copy.deepcopy(native['nodes']),
            'screenshot': response['screenshot'], 'actual_api_result': self.s.last_api_receipt}
        self.s.record(label, self.latest)
        return self.latest

    def route(self, name, *, restoring=False):
        self.budget(); s, c = self.s, self.c; route = s.active['routes'][name]
        component = route['component']
        raw = s.android(['/system/bin/cmd', 'package', 'resolve-activity', '--brief', '--user', '0', '-n', component], 15)
        rows = raw.decode('utf-8', 'strict').splitlines()
        ref = s.record('actual-page-resolution', {'route': name, 'component': component, 'raw': rows})
        c.need(len(rows) == 1 and rows[0].count('/') == 1 and rows[0].startswith('com.android.settings/')
            and self.model.expanded_component(rows[0]) == self.model.expanded_component(component),
            'ORIGINAL_SETTINGS_ROUTE_NOT_AVAILABLE_NO_FALLBACK')
        if s.current_component != component:
            c.need(self.routes < s.active['limits']['maximum_routes'], 'SETTINGS_PAGE_ROUTE_BUDGET')
            s.verify_current_tasks(); focus = self.focus('before-page-route-focus')
            argv = ['/system/bin/am', 'start-activity', '-W', '--user', '0', '--display', '0',
                '--task', str(s.primary_task), '--activity-clear-top', '-n', component]
            intent = s.record('settings-page-route-intent', {'name': name, 'argv': argv, 'resolver': ref,
                'source_component': s.current_component, 'ownership': s.task_claims[-1], 'automatic_retry': False})
            self.pending = {'kind': 'route', 'component': component, 'argv': argv, 'intent': intent,
                'restoring': restoring, 'focus': focus, 'sent': False}
            self.routes += 1
            out = s.android(argv, 35).decode('utf-8', 'strict')
            s.record('settings-page-route-response', {'intent': intent, 'raw': out})
            c.need('Status: ok' in out and 'Error:' not in out and self.pending.get('final_fence_consumed') is True,
                'SETTINGS_ROUTE_ACK_UNKNOWN_NO_REPLAY')
            deadline = min(s.deadline, time.monotonic() + 8); settled = False
            for _ in range(s.active['limits']['maximum_read_observations_per_wait']):
                roots, tasks, task_ref = s.verify_current_tasks()
                raw_focus = s.android(c.FOREGROUND, 6).decode('utf-8', 'strict')
                current = self.model.focus_metadata(raw_focus)
                if self.model.exact_leaf(roots, s.primary_task, component) and current.get('verified') is True \
                        and current.get('task') == s.primary_task \
                        and self.model.expanded_component(current['package'] + '/' + current['activity']) == self.model.expanded_component(component) \
                        and self.model.expanded_component(current['package'] + '/' + current['focused_activity']) == self.model.expanded_component(component):
                    s.current_component = component; settled = True; break
                c.need(time.monotonic() < deadline, 'SETTINGS_ROUTE_DID_NOT_SETTLE')
                time.sleep(.2)
            c.need(settled, 'SETTINGS_ROUTE_NOT_EXACT_SAME_OWNED_TASK')
            observed = self.observe('page-' + name.replace('_', '-'))
            content = self.model.page_content(observed['nodes'], route)
            self.pending = None
        else:
            observed = self.observe('page-' + name.replace('_', '-'))
            content = self.model.page_content(observed['nodes'], route)
        evidence = s.record('page-content-verified', {'route': name, 'source_route': route,
            'actual_resolution': ref, 'actual_UI': observed['actual_api_result'], 'content': content,
            'native_owned_task': s.primary_task, 'scope': s.flow.scope_ref, 'page_settings_changed': False})
        self.page_evidence.append(evidence)
        return observed, evidence

    def read_rotation(self, label, *, allow_transition=False):
        values = {}
        for key in ('accelerometer_rotation', 'user_rotation', 'hide_rotation_lock_toggle_for_accessibility'):
            values[key] = self.s.android(['/system/bin/settings', '--user', '0', 'get', 'system', key], 15).decode('utf-8', 'strict').strip()
        binder = self.s.android(['/system/bin/wm', 'user-rotation', '-d', '0'], 15).decode('utf-8', 'strict')
        display = self.s.android(self.c.FOREGROUND, 6).decode('utf-8', 'strict')
        state = self.model.rotation_state(values, binder, allow_transition=allow_transition)
        state['display_rotation'] = self.model.rotation_display(display)
        state['evidence'] = self.s.record(label, {'state': state, 'raw_binder': binder,
            'raw_display': display, 'direct_setting_writes': 0, 'wm_mutation_commands': 0})
        return state

    @staticmethod
    def rotation_values(state):
        return {k: v for k, v in state.items() if k != 'evidence'}

    def check_ui_rotation(self, observed, state):
        node, selector = self.model.rotation_widget(observed['nodes'])
        self.c.need(node['checked'] == state['auto_rotate'], 'ROTATION_UI_SETTINGS_BINDER_DISAGREE')
        return node, selector

    def toggle_rotation(self, desired, *, restoring=False):
        self.budget(); s, c = self.s, self.c
        c.need(type(desired) is bool and self.actions < s.active['limits']['maximum_UI_actions']
            and self.preimage is not None and s.current_component == s.active['routes']['rotation']['component'],
            'ONE_DECLARED_SETTINGS_ROTATION_OPERATION')
        before = self.read_rotation('before-rotation-input')
        expected = self.changed_state if restoring else self.preimage
        c.need(expected is not None and self.rotation_values(before) == self.rotation_values(expected)
            and before['display_rotation'] == 0 and before['settings']['user_rotation'] == '0'
            and before['auto_rotate'] != desired, 'EXACT_HELD_ROTATION_PREIMAGE_BEFORE_UI_INPUT')
        observed = self.observe('before-rotation-ui')
        node, selector = self.check_ui_rotation(observed, before)
        request = {'op': 'click', 'package': 'com.android.settings', 'display': 0, 'accessibility_mode': 'none',
            'window_token': observed['focus']['window_token'], 'selector': selector, 'method': 'accessibility'}
        intent = s.record('rotation-ui-intent', {'request': request, 'before': before, 'actual_widget': node,
            'desired_auto_rotate': desired, 'restoring': restoring, 'automatic_retry': False})
        self.pending = {'kind': 'rotation', 'request': request, 'intent': intent, 'focus': observed['focus'],
            'restoring': restoring}; self.actions += 1; self.dirty = True
        response = s.helper.dispatch(request)
        context = s.last_api_context
        c.need(context is not None and len(context['native_acks']) == 1
            and context['native_acks'][0]['value'].get('ok') is True
            and context['native_acks'][0]['value'].get('performed') == 'click'
            and context['native_acks'][0]['value'].get('accessibility_mode_restoration_verified') is True
            and response.get('ok') is True and response.get('performed') == 'click'
            and response.get('outcome_unknown') is not True and self.pending.get('final_fence_consumed') is True,
            'ACTUAL_ONCE_ROTATION_NATIVE_ACK_REQUIRED_UNKNOWN_NOT_REPLAYED')
        input_ref = s.last_api_receipt
        deadline = min(s.deadline, time.monotonic() + 8); after = None; ui = None
        for _ in range(s.active['limits']['maximum_read_observations_per_wait']):
            state = self.read_rotation('after-rotation-input', allow_transition=True)
            ui = self.observe('after-rotation-ui')
            widget, _ = self.model.rotation_widget(ui['nodes'])
            if state['consistency_verified'] is True and state['auto_rotate'] == desired and widget['checked'] == desired:
                after = state; break
            c.need(time.monotonic() < deadline, 'ASYNCHRONOUS_ROTATION_EFFECT_NOT_OBSERVED')
            time.sleep(.2)
        c.need(after is not None and after['display_rotation'] == 0 and after['settings']['user_rotation'] == '0'
            and after['settings']['hide_rotation_lock_toggle_for_accessibility'] == '0',
            'ROTATION_EFFECT_OR_UNRELATED_SETTING_DRIFT')
        ref = s.record('rotation-effect-verified', {'intent': intent, 'native_input': input_ref,
            'after': after, 'actual_UI': ui['actual_api_result'], 'Binder_effect_observed': True,
            'restoring': restoring, 'direct_setting_writes': 0})
        self.roundtrip_evidence.append(ref); self.pending = None
        if restoring:
            c.need(self.rotation_values(after) == self.rotation_values(self.preimage), 'FULL_ORIGINAL_ROTATION_PREIMAGE_NOT_RESTORED')
            self.dirty = False; self.restored = True
        else:
            self.changed_state = after
        return after

    def close_round(self):
        self.s.remove_owned(); self.closed_rounds.append(self.s.scope_index)

    def run(self):
        s, c = self.s, self.c
        for index in range(2):
            s.launch(index); self.observe('native-home-' + str(index))
            if self.s.kind == 'settings_pages':
                for name in ('system', 'network', 'display', 'storage', 'applications'):
                    self.route(name)
            elif self.s.kind == 'settings_permissions':
                for name in ('accounts', 'privacy', 'special_access'):
                    _, ref = self.route(name); self.interface_evidence.append(ref)
                # Read-only page existence does not prove an error branch. A
                # later source-bound case must observe the actual relevant
                # unavailable/error UI before the complete original gate opens.
                self.result['permission_account_interfaces_observed'] = True
                self.result['actual_permission_error_branch_observed'] = False
            else:
                observed, _ = self.route('rotation')
                state = self.read_rotation('rotation-round-' + str(index))
                self.check_ui_rotation(observed, state)
                if index == 0:
                    c.need(state['display_rotation'] == 0 and state['settings']['user_rotation'] == '0',
                        'ONLY_NATURAL_ZERO_ROTATION_WITH_EXACT_REVERSIBLE_PREIMAGE')
                    self.preimage = state
                    self.toggle_rotation(not state['auto_rotate'])
                else:
                    c.need(self.changed_state is not None and self.rotation_values(state) == self.rotation_values(self.changed_state),
                        'ACTUAL_REOPEN_ROTATION_PERSISTENCE_REQUIRED')
                    self.result['reopened_rotation_persistence_verified'] = True
                    self.toggle_rotation(self.preimage['auto_rotate'], restoring=True)
            self.close_round()
        self.result['case_scope_completed'] = True

    def cleanup(self):
        # No mutation is replayed after UNKNOWN. Restore only an acknowledged
        # owned delta with the exact still-held value, same Main and own task.
        error = None
        try:
            if self.dirty:
                self.c.need(self.pending is None and self.changed_state is not None and self.s.primary_task is not None,
                    'UNKNOWN_OR_UNOWNED_ROTATION_DELTA_RETAINED_NO_BLIND_RESTORE')
                self.route('rotation', restoring=True)
                self.toggle_rotation(self.preimage['auto_rotate'], restoring=True)
        except BaseException as caught:
            error = caught
        finally:
            try:
                self.s.remove_owned()
            except BaseException as caught:
                if error is None: error = caught
                else: error.add_note('SETTINGS_OWNED_TASK_CLOSE:' + type(caught).__name__)
        if error is not None:
            raise error
