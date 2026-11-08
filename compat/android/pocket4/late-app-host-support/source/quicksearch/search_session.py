"""Same-process final Main session with distinct native and implicit browser task ownership."""
import base64
import copy
import inspect
import os
from pathlib import Path
import re
import time
import types

class Session:
    def __init__(self, c, active_ref, active, scopes, phase_ref, action_lock, components, evidence_root):
        self.c, self.active_ref, self.active = c, active_ref, active
        self.scopes, self.phase_ref, self.action_lock = list(scopes), phase_ref, action_lock
        self.components = components; self.kind = active['kind']; self.driver = None
        self.evidence_root = c.private_dir(evidence_root)
        self.host = components['app_runtime.py']; self.runtime = components['search_runtime.py']
        self.plan = components['search_plan.py']; self.policy_module = components['search_policy.py']
        self.handoff_module = components['search_handoff.py']
        self.flow_type = components['search_flow.py'].make_flow(components['app_flow.py'])
        self.transport_module = components['search_transport.py']
        _, support = c.support(active['support_manifest'])
        self.baseline = support['business_baseline.py'].BusinessBaseline(active['baseline'], active['qualification'])
        self.epoch_sha256 = self.baseline.value['framework_epoch']['sha256']
        self.identities = [c.parse(c.read_ref(active[k])) for k in ('target_identity', 'helper_identity', 'browser_identity')]
        self.flow = None; self.closed = False; self.scope_index = 0; self.native_launches = 0
        self.task_claims = []; self.last_stacks = None; self.baseline_roots = self.baseline_tasks = None
        self.native_tasks = []; self.closed_native_tasks = []; self.companion_tasks = []; self.closed_companion_tasks = []
        self.primary_task = None; self.handoff = self.handoff_ref = None; self.ui_role = 'search'
        self.sequence = self.api_sequence = self.remove_calls = 0
        self.removal_admission = None; self.ordinary_admission = None; self.ui_dispatch_admission = None
        self.active_api = None; self.last_api_context = None; self.last_api_receipt = None; self.ui_owner = None
        self.phase_name = 'business'; self.phase_value = self.runtime.validate_phase(c, self.host, phase_ref, active_ref, active)
        self.source_paths = {n: str(Path(m.__file__)) for n, m in components.items()}
        self.allowed_ui_packages = {active['target_profile']['package'], active['browser_profile']['package']}
        self.flow = self.new_flow(0)
        try:
            self.scope_module = self.flow.scope_module
            self.helper = components['search_ui.py'].OriginalAPIs(self)
        except BaseException as primary:
            try:
                self.flow.close()
            except BaseException as secondary:
                primary.add_note('SEARCH_SESSION_CONSTRUCTION_CLOSE:' + type(secondary).__name__)
            self.closed = True
            raise

    def record(self, label, value):
        self.c.need(type(label) is str and re.fullmatch('[a-z0-9][a-z0-9-]{0,60}', label), 'EXACT_SEARCH_EVIDENCE_NAME')
        self.sequence += 1
        return self.c.write_new(self.evidence_root / ('%04d-' % self.sequence + label + '.json'), value)

    def branch_log_command(self):
        return ['/system/bin/logcat', '--uid=' + str(self.active['target_profile']['uid']), '-b', 'main',
            '-d', '-v', 'epoch', '-t', '512', 'GoogleSearch:I', '*:S']

    def last_input_guard(self, runtime, argv, timeout, private):
        """Fresh task/window check after this Flow guard, before global input.

        These two hard-coded reads use the held ordinary transport directly;
        they cannot recurse into a pending mutation admission. The inherited
        transport still verifies Main/source itself. This is a last-observed
        fence, not an atomic-window-targeted guarantee for Android global input.
        """
        c = self.c
        back = argv == ['/system/bin/input', 'keyboard', '-d', '0', 'keyevent', 'KEYCODE_BACK']
        tap = private and self.active_api is not None and self.active_api['request'].get('op') == 'snapshot-tap' \
            and argv[:4] == ['/system/bin/input', '-d', '0', 'tap']
        if not (back or tap):
            return
        c.need(runtime is self.flow and self.driver is not None and self.driver.pending is not None,
            'LAST_INPUT_FENCE_MUST_BELONG_TO_THIS_ONCE_PENDING_ACTION')
        c.need(runtime._android_mutation is False, 'NO_MUTATION_FLAG_DURING_FINAL_READONLY_INPUT_FENCE')
        # The physical command/lease/retirement receipts come from the unchanged
        # bound transport; no shell command or Android mutation is added here.
        raw_tasks = runtime.camera_transport(c.STACKS, 15)
        raw_focus = runtime.camera_transport(c.FOREGROUND, 6)
        runtime.command_index = runtime.bridge.command_index; runtime.total_commands += 2
        roots, tasks = runtime.tasks.parse_stacks(raw_tasks.decode('utf-8', 'strict'))
        focus = self.components['search_driver.py'].focus_metadata(raw_focus.decode('utf-8', 'strict'))
        owned = self.owned_set()
        c.need(tasks == self.baseline_tasks | owned
            and self.handoff_module.preserved_roots(self.baseline_roots, roots, owned),
            'TASK_SET_CHANGED_AFTER_FLOW_GUARD_BEFORE_GLOBAL_INPUT')
        for task, profile, native in ((self.primary_task, self.active['target_profile'], True),
                (None if self.handoff is None else self.handoff['task'], self.active['browser_profile'], False)):
            if task is not None:
                c.need(self.handoff_module.exact_leaf(roots, task, profile['component'], native=native),
                    'OWNED_LEAF_CHANGED_BEFORE_GLOBAL_INPUT')
        if back:
            expected = self.driver.pending['focus']
            c.need(self.driver.pending['kind'] == 'back' and self.driver.pending['sent'] is True
                and not self.driver.pending.get('final_fence_consumed') and focus == expected,
                'BACK_WINDOW_CHANGED_AFTER_FLOW_GUARD')
        else:
            context = self.active_api; expected = context['observed_focus']
            observed = {k: focus.get(k) for k in ('package', 'activity', 'window_token')}
            if observed['package'] and observed['activity']:
                observed['activity'] = self.handoff_module.expanded_component(observed['package'] + '/' + observed['activity']).split('/', 1)[1]
            c.need(self.driver.pending['kind'] == 'result' and focus.get('verified') is True
                and focus.get('task') == self.primary_task and observed == expected
                and not self.driver.pending.get('final_fence_consumed'), 'RESULT_WINDOW_CHANGED_AFTER_FLOW_GUARD')
        self.driver.pending['final_fence_consumed'] = True
        self.record('last-global-input-fence', {'pending_intent': self.driver.pending['intent'],
            'raw_tasks': raw_tasks.decode('utf-8', 'strict'), 'actual_focus': focus,
            'scope': self.flow.scope_ref, 'phase': self.phase_ref, 'automatic_retry': False,
            'check_after_Flow_guard': True, 'atomic_window_targeted_injection_claimed': False})

    def android(self, argv, timeout=20):
        self.guard(); argv = list(argv)
        self.c.need(self.ordinary_admission is None, 'NO_REENTRANT_SEARCH_ANDROID_CALL')
        mutates = self.flow.policy.command(argv, timeout)
        self.ordinary_admission = (argv, timeout, mutates)
        try:
            raw = self.flow.android(argv, timeout, mutation=mutates)
            if argv == self.c.STACKS:
                roots, tasks = self.flow.tasks.parse_stacks(raw.decode('utf-8', 'strict'))
                self.last_stacks = (roots, tasks)
                if self.baseline_tasks is None:
                    packages = self.allowed_ui_packages
                    self.c.need(not any(x['component'].split('/')[0] in packages for r in roots.values() for x in r['children']),
                        'PREEXISTING_SEARCH_AND_BROWSER_TASKS_PRESERVED')
                    self.baseline_roots, self.baseline_tasks = copy.deepcopy(roots), set(tasks)
            return raw
        finally:
            self.ordinary_admission = None

    def stacks(self, label):
        raw = self.android(self.c.STACKS, 15).decode('utf-8', 'strict')
        roots, tasks = self.flow.tasks.parse_stacks(raw)
        ref = self.record(label, {'raw_stacks': raw, 'task_ids': sorted(tasks)})
        return roots, tasks, ref

    def verify_prelaunch_tasks(self, roots, tasks):
        self.c.need(self.phase_name == 'business' and self.baseline_tasks is not None
            and tasks == self.baseline_tasks and roots == self.baseline_roots
            and 1 <= self.native_launches <= 2, 'UNCHANGED_ACTUAL_PREEXISTING_TASKS')

    def launch(self, index):
        c = self.c; self.original_caller(['search_driver.py'], {'run'})
        c.need(self.phase_name == 'business' and self.driver.pending is None and index == self.native_launches
            and index in (0, 1) and self.primary_task is None and self.handoff is None
            and self.native_tasks == self.closed_native_tasks, 'ONE_NEXT_FRESH_NATIVE_SEARCH_LAUNCH')
        roots, tasks, before_ref = self.stacks('pre-native-launch-' + str(index))
        c.need(roots == self.baseline_roots and tasks == self.baseline_tasks, 'PRESERVE_PREEXISTING_TASKS_BEFORE_LAUNCH')
        if index:
            self.flow.close(); self.scope_index = index; self.flow = self.new_flow(index)
        self.record('native-launch-intent-' + str(index), {'scope': self.flow.scope_ref, 'before': before_ref,
            'argv': c.NATIVE_PREFIX + ['launch', self.active['target_profile']['package'], '--component',
                self.active['target_profile']['component'], '--json'], 'automatic_retry': False})
        self.driver.pending = {'kind': 'native_launch', 'index': index}; self.native_launches += 1
        response = self.flow.native_launch()
        c.need(response['rc'] == 0 and not response['timed_out'] and response['joined'], 'NATIVE_SEARCH_LAUNCH_UNKNOWN')
        selected = self.flow.selected_task()
        c.need(selected['task'] not in self.native_tasks and set(selected['prelaunch_task_ids']) == self.baseline_tasks
            and selected['prelaunch_absent'] is True and selected['cleanup_allowed'] is True, 'REAL_NEW_NATIVE_SEARCH_TASK')
        self.primary_task = selected['task']; self.native_tasks.append(self.primary_task)
        self.driver.pending = None; self.ui_role = 'search'
        return selected

    def owned_set(self):
        values = set()
        if self.primary_task is not None:
            values.add(self.primary_task)
        if self.handoff is not None:
            values.add(self.handoff['task'])
        return values

    def verify_current_tasks(self, *, permit_absent=None):
        roots, tasks, ref = self.stacks('current-owned-tasks')
        owned = self.owned_set(); expected = self.baseline_tasks | owned
        if permit_absent is not None:
            self.c.need(permit_absent in owned, 'ONLY_KNOWN_OWNED_TASK_MAY_RETIRE')
            self.c.need(tasks in (expected, expected - {permit_absent}), 'NO_UNRELATED_TASK_DELTA_DURING_RETIREMENT')
        else:
            self.c.need(tasks == expected, 'EXACT_CURRENT_SEARCH_AND_COMPANION_TASK_SET')
        self.c.need(self.handoff_module.preserved_roots(self.baseline_roots, roots, owned),
            'EVERY_PREEXISTING_TASK_COMPONENT_AND_ROOT_PRESERVED')
        for task, profile, native in ((self.primary_task, self.active['target_profile'], True),
                (None if self.handoff is None else self.handoff['task'], self.active['browser_profile'], False)):
            if task is None:
                continue
            if task == permit_absent and task not in roots and task not in tasks:
                continue
            row = roots.get(task)
            shrinking = task == permit_absent and task not in tasks and row and row['display'] == row['user'] == 0 \
                and row['children'] == []
            self.c.need(shrinking or self.handoff_module.exact_leaf(roots, task, profile['component'], native=native),
                'CURRENT_OWNED_EXCLUSIVE_LEAF_CHANGED')
        return roots, tasks, ref

    def adopt_browser(self, before_roots, before_tasks, before_ref, response, result_text, binding):
        c = self.c; self.original_caller(['search_driver.py'], {'open_result'})
        c.need(self.kind == 'search_online' and self.scope_index == 0 and self.handoff is None
            and not self.companion_tasks and self.driver.pending is not None
            and self.driver.pending['kind'] == 'result' and self.last_api_context is not None
            and self.last_api_context['request'] == self.driver.pending['request']
            and self.last_api_context['mutation_sent'] is True, 'ONE_ACTUAL_UNREPLAYED_RESULT_INPUT')
        roots, tasks, after_ref = self.stacks('post-result-handoff-tasks')
        focus = self.driver.focus('post-result-handoff-focus', admit_handoff=True)
        claim = self.handoff_module.adopt(before_roots, before_tasks, roots, tasks, self.primary_task,
            self.active['target_profile'], self.active['browser_profile'], response, focus)
        claim.update(schema='pocket4-quicksearch-actual-result-handoff-v1', scope=self.flow.scope_ref,
            phase_lease=self.phase_ref, framework_epoch_sha256=self.epoch_sha256,
            browser_identity=self.active['browser_identity'], native_primary_claim=self.task_claims[-1],
            before_tasks=before_ref, after_tasks=after_ref, actual_input_result=self.last_api_receipt,
            actual_result_binding=binding, result_text=result_text, actual_focus=focus, automatic_retry=False)
        self.handoff_ref = self.record('actual-browser-handoff', claim)
        self.handoff = claim; self.companion_tasks.append(claim['task']); self.ui_role = 'browser'
        return claim

    def remove_owned(self, role):
        c = self.c; self.original_caller(['search_driver.py'], {'close_round', 'back', 'cleanup'})
        c.need(role in ('search', 'browser') and self.removal_admission is None, 'EXACT_INDEPENDENT_TASK_CLEANUP_ROLE')
        task = self.primary_task if role == 'search' else None if self.handoff is None else self.handoff['task']
        if task is None:
            return None
        c.need(role == 'browser' or self.handoff is None, 'COMPANION_MUST_RETIRE_BEFORE_PRIMARY')
        if role == 'search':
            selected = self.flow.selected_task()
            c.need(task == selected['task'] and selected['prelaunch_absent'] is True and selected['cleanup_allowed'] is True,
                'ONLY_REAL_NATIVE_OWNED_PRIMARY')
            ownership = self.task_claims[-1]
        else:
            c.need(self.handoff['actual_new_exclusive_leaf'] is True and self.handoff['native_launch_receipt'] is None,
                'ONLY_SEPARATE_PROVEN_BROWSER_HANDOFF')
            ownership = self.handoff_ref; c.read_ref(ownership)
        roots, tasks, before = self.verify_current_tasks(permit_absent=task)
        if task not in roots and task not in tasks:
            receipt = self.record('owned-task-already-retired', {'task': task, 'role': role, 'ownership': ownership,
                'readback': before, 'normal_remove_called': False, 'other_tasks_preserved': True})
        else:
            profile = self.active['target_profile' if role == 'search' else 'browser_profile']
            c.need(self.handoff_module.exact_leaf(roots, task, profile['component'], native=role == 'search'),
                'FRESH_EXACT_LEAF_BEFORE_ONE_REMOVE')
            argv = ['/system/bin/cmd', 'activity', 'stack', 'remove', str(task)]
            intent = self.record('owned-remove-intent', {'task': task, 'role': role, 'ownership': ownership,
                'before_tasks': before, 'argv': argv, 'automatic_retry': False})
            # A second attempt is impossible even if the transport becomes UNKNOWN.
            c.write_new(self.flow.root / ('remove-%d-attempted.json' % task), {'intent': intent, 'automatic_retry': False})
            self.removal_admission = {'argv': argv, 'sent': False}; self.remove_calls += 1
            try:
                self.android(argv, 15)
            finally:
                self.removal_admission = None
            limit = min(self.deadline, time.monotonic() + 8)
            receipt = None
            while time.monotonic() < limit:
                roots, tasks, observed = self.verify_current_tasks(permit_absent=task)
                if task not in roots and task not in tasks:
                    receipt = self.record('owned-remove-completed', {'task': task, 'role': role,
                        'intent': intent, 'after_tasks': observed, 'other_tasks_preserved': True})
                    break
                time.sleep(.2)
            c.need(receipt is not None, 'OWNED_TASK_REMOVE_COMPLETION_UNKNOWN_NO_REPLAY')
        if role == 'search':
            self.closed_native_tasks.append(task); self.primary_task = None
        else:
            self.closed_companion_tasks.append(task); self.handoff = self.handoff_ref = None; self.ui_role = 'search'
        return receipt

    def verify_original_callback(self, kind, callback, previous):
        fn = getattr(callback, '__func__', callback)
        self.c.need(kind == 'foreground' and previous is None and self.ui_owner is None
            and getattr(callback, '__self__', None) is self.driver and self.driver is not None
            and fn.__code__.co_filename == self.source_paths['search_driver.py']
            and fn.__code__.co_name == 'owned_foreground', 'ONE_SOURCE_BOUND_SEARCH_FOREGROUND_CALLBACK')
        self.ui_owner = self.driver

    def validate_ui_foreground(self, value, context):
        c = self.c; role = context['role']; p = self.active['target_profile' if role == 'search' else 'browser_profile']
        component = self.handoff_module.expanded_component(p['component'])
        task = self.primary_task if role == 'search' else None if self.handoff is None else self.handoff['task']
        c.need(type(value) is dict and set(value) == {'package', 'activity', 'window_token'}
            and value['package'] + '/' + value['activity'] == component
            and re.fullmatch('[0-9a-f]{1,32}', value['window_token']) and self.ui_owner is self.driver
            and self.ui_role == role and task == context['owned_task'], 'CURRENT_EXACT_SOURCE_BOUND_SEARCH_WINDOW')
        c.need(value['package'] == context['request']['package'], 'API_PACKAGE_CHANGED')
        if not context.get('mutation_sent'):
            c.need(value['window_token'] == context['request']['window_token']
                and (context.get('observed_focus') is None or value == context['observed_focus']),
                'WINDOW_CHANGED_BEFORE_SEARCH_INPUT')
        context['last_foreground'] = copy.deepcopy(value)

    def begin_ui_api(self, api, request):
        c = self.c; d = self.driver
        c.need(api in ('capture', 'dispatch', 'window_state') and d is not None and self.ui_owner is d
            and self.active_api is None, 'ONLY_SOURCE_BOUND_SEARCH_UI_API')
        caller = self.original_caller(['search_driver.py'], {'observe', 'set_query', 'open_result', 'back'})
        role = self.ui_role; p = self.active['target_profile' if role == 'search' else 'browser_profile']
        c.need(request.get('package') == p['package'] and request.get('display') == 0
            and request.get('accessibility_mode') == 'none' and type(request.get('window_token')) is str,
            'EXACT_SEARCH_ROLE_WINDOW_AND_DISPLAY')
        op = request.get('op'); mutation = op in ('set-text', 'snapshot-tap')
        if api in ('capture', 'window_state'):
            c.need(caller['function'] == 'back' and role == 'browser'
                and set(request) == {'package', 'window_token', 'display', 'accessibility_mode'},
                'ONLY_FRESH_BROWSER_BACK_CAPTURE')
        elif not mutation:
            c.need(caller['function'] == 'observe' and request == {'op': 'observe', 'package': p['package'],
                'window_token': request['window_token'], 'display': 0, 'accessibility_mode': 'none', 'with_png': True},
                'ONLY_CURRENT_SEARCH_OR_BROWSER_OBSERVATION')
        else:
            c.need(role == 'search' and d.pending is not None and d.pending.get('request') == request
                and not d.pending.get('admitted') and d.actions <= self.active['limits']['maximum_UI_actions'],
                'ONE_BOUNDED_SOURCE_BOUND_QUERY_OR_RESULT_INPUT')
            if op == 'set-text':
                c.need(caller['function'] == 'set_query'
                    and set(request) == {'op', 'package', 'window_token', 'display', 'accessibility_mode', 'selector', 'value'}
                    and request['selector'] == {'id': p['package'] + ':id/search_src_text', 'package': p['package'],
                        'editable': True, 'enabled': True}
                    and (request['value'] in ['', *self.active['queries']] or
                        d.pending.get('restoring') is True and request['value'] == d.preimages[self.scope_index])
                    and (self.phase_name == 'business' or d.pending.get('restoring') is True), 'ONLY_EXACT_QUERY_TEXT_OR_HELD_PREIMAGE')
            else:
                c.need(self.phase_name == 'business' and caller['function'] == 'open_result'
                    and self.kind == 'search_online' and self.scope_index == 0 and len(self.companion_tasks) == 0
                    and set(request) == {'op', 'package', 'window_token', 'display', 'accessibility_mode', 'input_source',
                        'frame_sha256', 'scope_sha256', 'context_token', 'coords'}
                    and request['input_source'] == 'touch' and request['coords'] == d.pending['binding']['coords'],
                    'ONE_ACTUAL_RESULT_LABEL_SNAPSHOT_TOUCH')
            d.pending['admitted'] = True
        self.guard(); self.verify_current_tasks()
        ownership = self.task_claims[-1] if role == 'search' else self.handoff_ref
        task = self.primary_task if role == 'search' else self.handoff['task']
        self.api_sequence += 1
        context = {'schema': 'pocket4-quicksearch-ui-context-v1', 'api': api, 'request': copy.deepcopy(request),
            'scope': self.flow.scope_ref, 'phase_lease': self.phase_ref, 'owned_claim': ownership, 'owned_task': task,
            'role': role, 'caller': caller, 'mutation_sent': False, 'api_sequence': self.api_sequence,
            'native_returns': 0, 'native_acks': [], 'automatic_retry': False}
        focus = self.helper.foreground_callback(); self.validate_ui_foreground(focus, context)
        context['observed_focus'] = copy.deepcopy(focus)
        if mutation:
            context['actual_source_intent'] = d.pending['intent']
        context['_previous'] = self.flow.begin_api('api-%04d-%s' % (self.api_sequence, api), request, context)
        self.active_api = context
        return context

    def record_native_return(self, request, value, context):
        context['native_returns'] += 1
        try:
            ref = self.c.write_new(self.flow.step / ('native-return-%03d.json' % context['native_returns']),
                {'request': request, 'native_response': value, 'scope': self.flow.scope_ref,
                    'phase_lease': self.phase_ref, 'automatic_retry': False})
            if request.get('op') == context['request'].get('op'):
                context['native_acks'].append({'ref': ref, 'value': copy.deepcopy(value)})
        except BaseException as error:
            self.flow.bound.hold(error); self.flow.view.target.seal_admission(); raise

    def validate_snapshot_request(self, request, frame):
        self.c.need(self.driver is not None and request.get('package') == self.active['browser_profile']['package']
            and self.ui_role == 'browser' and request.get('display') == 0
            and request.get('accessibility_mode') == 'none'
            and request.get('window_token') == frame['meta']['scope']['window_token'], 'CURRENT_BROWSER_BACK_SNAPSHOT_ONLY')

    def new_flow(self, index):
        flow = self.flow_type(self.c, self.scopes[index], 'launch', 'case-start', self.deadline,
            self.components['search_guard.py'], self.policy_module.Policy,
            private_context={'phase_lease': self.phase_ref, 'session': self})
        try:
            original = self.transport_module.bound_class(self.c, flow.scope_module, self.active['support_manifest'], 'camera_android')
            def record(kind, value):
                self.c.write_new(flow.step / ('ordinary-transport-%03d.%s.json' % (value['sequence'], kind)), value)
            flow.camera_transport = original(target=flow.view.target, environment=flow.view.environment,
                binding=flow.bound, runner=lambda argv, **kw: flow.bridge.runner(argv, **kw), record=record)
            return flow
        except BaseException:
            flow.close(); raise

    @property
    def deadline(self):
            return self.phase_value['deadline_monotonic_ns'] / 1000000000

    @property
    def environment(self):
            return dict(self.flow.view.environment)

    def verify_runtime(self, flow):
            c = self.c
            c.need(not self.closed and flow.plan == self.active and flow.scope_ref in self.scopes
                and flow.scope['phase_plan'] == self.active_ref and flow.phase_lease_ref == self.phase_ref
                and flow.deadline == self.deadline and flow.session is self
                and self.action_lock.ref == self.active['action_lock'], 'EXACT_SAME_PROCESS_CASE_FLOW_AND_PHASE')
            self.action_lock.verify()

    def guard(self, *, action_attempted=False):
            self.c.need(not self.closed and self.flow is not None, 'OPEN_NEW_SYSTEM_CASE_SESSION')
            self.flow.guard(action_attempted=action_attempted)
            return self.baseline.guard(action_attempted=action_attempted)

    def original_caller(self, names, methods=None, *, skip_trial_record=False):
            frame = inspect.currentframe()
            try:
                for _ in range(16):
                    frame = frame.f_back
                    if frame is None:
                        break
                    for name in names:
                        if frame.f_code.co_filename == self.source_paths.get(name):
                            # Trial.record is the unchanged observational writer.
                            # An intent belongs to its actual original launch,
                            # close, continuation step or Editor action caller.
                            if skip_trial_record and name == 'search_trial.py' and frame.f_code.co_name == 'record':
                                continue
                            self.c.need(methods is None or frame.f_code.co_name in methods,
                                'ONLY_ORIGINAL_CASE_API_CALLER')
                            return {'source': name, 'function': frame.f_code.co_name}
                raise RuntimeError('TYPED_API_NOT_CALLED_BY_REVIEWED_ORIGINAL_COMPONENT')
            finally:
                del frame

    def begin_cleanup(self, trigger):
            self.c.need(self.phase_name == 'business' and self.active_api is None, 'ONCE_ORIGINAL_CLEANUP_SWITCH')
            ref = self.runtime.phase(self.c, self.host, self.active_ref, self.active, 'final_cleanup', trigger)
            phase = self.runtime.validate_phase(self.c, self.host, ref, self.active_ref, self.active)
            self.phase_ref, self.phase_value, self.phase_name = ref, phase, 'final_cleanup'
            self.flow.set_phase(ref)
            return ref

    def verify_final_consumers(self, app, backend):
            self.c.need(self.c.regular(app['path'], contents=False) == app
                and self.c.regular(backend['path'], contents=False) == backend,
                'ACTUAL_FINAL_QUALIFIED_UI_CLIENT_AND_BACKEND_REQUIRED')
            self.baseline.guard()

    def ui_guard(self, *, action_attempted=False):
            self.guard(action_attempted=action_attempted)
            self.c.need(self.active_api is None or self.active_api['scope'] == self.flow.scope_ref
                and self.active_api['phase_lease'] == self.phase_ref, 'API_SCOPE_OR_PHASE_CHANGED')

    def validate_internal_capture(self, request, context):
            c = self.c; expected = context['request']
            c.need(type(request) is dict and request.get('package') == expected.get('package', expected.get('expected_package'))
                and request.get('display') == 0 and request.get('accessibility_mode') == 'none'
                and set(request) <= {'op', 'package', 'display', 'accessibility_mode', 'window_token', 'with_png', 'selector',
                    'value', 'method', 'coords', 'input_source', 'frame_sha256', 'scope_sha256', 'context_token', 'crop'},
                'ONLY_ORIGINAL_INTERNAL_CAPTURE')
            if not context['mutation_sent']:
                c.need(request == expected, 'PRE_ACTION_CAPTURE_MUST_USE_UNCHANGED_ORIGINAL_REQUEST')
            else:
                c.need(set(request) <= {'package', 'display', 'accessibility_mode', 'crop'}, 'ONLY_ORIGINAL_POST_ACTION_CAPTURE_FIELDS')

    def validate_native_request(self, request, context, action_used):
            return self.policy_module.native_request(self.c, context['request'], request, action_used)

    def admit_ui_android(self, argv, timeout, context, action_used):
            self.c.need(context is self.active_api, 'CURRENT_ORIGINAL_API_CONTEXT_REQUIRED')
            return self.policy_module.backend_android(self.c, context['request'], argv, timeout, action_used)

    def ui_android(self, argv, timeout, context, *, mutation=False, image=False):
            f = self.flow
            self.c.need(context is self.active_api and self.ui_dispatch_admission is None, 'ONE_TYPED_BACKEND_CALL_AT_A_TIME')
            self.ui_dispatch_admission = (argv, timeout, mutation)
            if mutation:
                self.c.need(not context['mutation_sent'], 'ONE_MUTATION_PER_ORIGINAL_API_NO_REPLAY')
                context['mutation_sent'] = True
            f._private_backend_transport = True; f._image_transport = image
            try:
                return f.android(argv, timeout, mutation=mutation)
            finally:
                f._private_backend_transport = False; f._image_transport = False; self.ui_dispatch_admission = None

    def ui_readiness(self, argv, options, context):
            self.c.need(context is self.active_api, 'CURRENT_API_READINESS_ONLY')
            raw = self.flow.bridge.command(argv, 8, mutation=False, label='Original backend readiness')
            result = self.c.parse(self.c.regular(self.flow.step /
                ('command-%03d.result.json' % self.flow.bridge.command_index))[0])
            self.c.need(result['returncode'] == 0 and result['host_retirement_proved'] is True
                and result['evidence_complete'] is True and self.c.read_ref(result['stdout']) == raw,
                'ACTUAL_RETIRED_READINESS_RESULT')
            return types.SimpleNamespace(stdout=raw, stderr=self.c.read_ref(result['stderr']), returncode=result['returncode'])

    def finish_ui_api(self, context, api, request, value, first, *, action_attempted):
            try:
                self.c.need(context is self.active_api, 'SAME_ORIGINAL_API_COMPLETION')
                result = value
                if api == 'capture' and value is not None:
                    result = {'meta': value['meta'], 'image': {'mode': value['image'].mode,
                        'width': value['image'].width, 'height': value['image'].height,
                        'pixel_sha256': self.helper.module.image_sha(value['image'])}}
                elif type(value) is dict and 'screenshot_png_base64' in value:
                    data = base64.b64decode(value['screenshot_png_base64'], validate=True)
                    self.c.need(len(data) <= 33554432, 'ORIGINAL_OBSERVATION_PNG_FILE_BOUND')
                    result = dict(value); result.pop('screenshot_png_base64')
                    result['recorded_png'] = self.c.write_new(self.flow.step / 'observation.png', data)
                self.last_api_receipt = self.c.write_new(self.flow.step / 'original-api-result.json', {
                    'schema': 'pocket4-final-original-api-result-v1', 'scope': self.flow.scope_ref,
                    'phase_lease': self.phase_ref, 'api': api, 'request': request, 'result': result,
                    'native_return_records': context['native_returns'], 'action_attempted': action_attempted,
                    'original_error': None if first is None else {'type': type(first).__name__, 'message': str(first),
                        'details': getattr(first, 'details', None)},
                    'unchanged_native_return_recorded_before_postcapture': True,
                    'automatic_retry': False, 'whole_app_business_accepted': False})
            except BaseException as error:
                self.flow.bound.hold(error); self.flow.view.target.seal_admission(); raise
            finally:
                self.last_api_context = context
                self.flow.end_api(context['_previous']); self.active_api = None

    def close(self):
            first = None
            try:
                self.helper.close()
            except BaseException as error:
                first = error
            try:
                self.flow.close()
            except BaseException as error:
                if first is None:
                    first = error
                else:
                    first.add_note('SYSTEM_FLOW_CLOSE:' + type(error).__name__)
            self.closed = True
            if first is not None:
                raise first
