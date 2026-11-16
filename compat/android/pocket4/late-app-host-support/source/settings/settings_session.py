"""Fresh-Main Settings ownership, exact same-task page routes and typed native UI."""
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
        self.host = components['app_runtime.py']; self.runtime = components['settings_runtime.py']
        self.plan = components['settings_plan.py']; self.policy_module = components['settings_policy.py']
        self.model = components['settings_model.py']; self.profiles = components['settings_profiles.py']
        self.flow_type = components['settings_flow.py'].make_flow(components['app_flow.py'])
        self.transport_module = components['settings_transport.py']
        _, support = c.support(active['support_manifest'])
        self.baseline = support['business_baseline.py'].BusinessBaseline(active['baseline'], active['qualification'])
        self.epoch_sha256 = self.baseline.value['framework_epoch']['sha256']
        self.identities = [c.parse(c.read_ref(active[k])) for k in ('target_identity', 'helper_identity')]
        self.flow = None; self.closed = False; self.scope_index = 0; self.native_launches = 0
        self.task_claims = []; self.last_stacks = None; self.baseline_roots = self.baseline_tasks = None
        self.native_tasks = []; self.closed_native_tasks = []; self.primary_task = None
        self.current_component = self.profiles.HOME
        self.sequence = self.api_sequence = self.remove_calls = 0
        self.removal_admission = None; self.ordinary_admission = None; self.ui_dispatch_admission = None
        self.active_api = None; self.last_api_context = None; self.last_api_receipt = None; self.ui_owner = None
        self.phase_name = 'business'; self.phase_value = self.runtime.validate_phase(c, self.host, phase_ref, active_ref, active)
        self.source_paths = {n: str(Path(m.__file__)) for n, m in components.items()}
        self.allowed_ui_packages = {active['target_profile']['package']}
        self.flow = self.new_flow(0)
        try:
            self.scope_module = self.flow.scope_module
            self.helper = components['settings_ui.py'].OriginalAPIs(self)
        except BaseException as primary:
            try:
                self.flow.close()
            except BaseException as secondary:
                primary.add_note('SETTINGS_SESSION_CONSTRUCTION_CLOSE:' + type(secondary).__name__)
            self.closed = True
            raise

    def launch(self, index):
        c = self.c; self.original_caller(['settings_driver.py'], {'run'})
        c.need(self.phase_name == 'business' and self.driver.pending is None and index == self.native_launches
            and index in (0, 1) and self.primary_task is None and self.native_tasks == self.closed_native_tasks,
            'ONE_NEXT_FRESH_NATIVE_SETTINGS_LAUNCH')
        roots, tasks, before_ref = self.stacks('pre-native-launch-' + str(index))
        c.need(roots == self.baseline_roots and tasks == self.baseline_tasks, 'PRESERVE_PREEXISTING_TASKS_BEFORE_LAUNCH')
        if index:
            self.flow.close(); self.scope_index = index; self.flow = self.new_flow(index)
        self.record('native-launch-intent-' + str(index), {'scope': self.flow.scope_ref, 'before': before_ref,
            'original_alias': self.active['target_profile']['component'], 'original_target': self.profiles.HOME,
            'automatic_retry': False})
        self.driver.pending = {'kind': 'native_launch', 'index': index}; self.native_launches += 1
        response = self.flow.native_launch()
        c.need(response['rc'] == 0 and not response['timed_out'] and response['joined'], 'NATIVE_SETTINGS_LAUNCH_UNKNOWN')
        selected = self.flow.selected_task()
        c.need(selected['task'] not in self.native_tasks and set(selected['prelaunch_task_ids']) == self.baseline_tasks
            and selected['prelaunch_absent'] is True and selected['cleanup_allowed'] is True, 'REAL_NEW_NATIVE_SETTINGS_TASK')
        self.primary_task = selected['task']; self.native_tasks.append(self.primary_task)
        self.current_component = self.profiles.HOME
        self.verify_current_tasks()
        self.driver.pending = None
        return selected

    def owned_set(self):
        return set() if self.primary_task is None else {self.primary_task}

    def permitted_current_components(self):
        values = {self.current_component}
        if self.driver is not None and self.driver.pending is not None and self.driver.pending['kind'] == 'route':
            values.add(self.driver.pending['component'])
        return values

    def verify_current_tasks(self, *, permit_absent=None):
        roots, tasks, ref = self.stacks('current-owned-tasks')
        owned = self.owned_set(); expected = self.baseline_tasks | owned
        if permit_absent is None:
            self.c.need(tasks == expected, 'EXACT_CURRENT_SETTINGS_TASK_SET')
        else:
            self.c.need(permit_absent in owned and tasks in (expected, expected - {permit_absent}),
                'ONLY_KNOWN_OWNED_SETTINGS_TASK_MAY_RETIRE')
        self.c.need(self.model.preserved_roots(self.baseline_roots, roots, owned), 'EVERY_PREEXISTING_TASK_PRESERVED')
        if self.primary_task is not None:
            row = roots.get(self.primary_task)
            absent = self.primary_task == permit_absent and self.primary_task not in tasks and (
                row is None or row['display'] == row['user'] == 0 and row['children'] == [])
            self.c.need(absent or any(self.model.exact_leaf(roots, self.primary_task, component)
                for component in self.permitted_current_components()), 'EXACT_OWNED_SETTINGS_COMPONENT_OR_PENDING_ROUTE')
        return roots, tasks, ref

    def last_input_guard(self, runtime, argv, timeout, private):
        c = self.c; d = self.driver
        remove = self.removal_admission is not None and argv == self.removal_admission['argv']
        route = not private and argv[:2] == ['/system/bin/am', 'start-activity']
        click = private and self.active_api is not None and self.active_api['request'].get('op') == 'click'
        if not (remove or route or click):
            return
        c.need(runtime is self.flow and runtime._android_mutation is False and self.primary_task is not None,
            'EXACT_CURRENT_SETTINGS_OWNER_BEFORE_MUTATION')
        raw_tasks = runtime.camera_transport(c.STACKS, 15)
        roots, tasks = runtime.tasks.parse_stacks(raw_tasks.decode('utf-8', 'strict'))
        runtime.command_index = runtime.bridge.command_index; runtime.total_commands += 1
        c.need(tasks == self.baseline_tasks | self.owned_set()
            and self.model.preserved_roots(self.baseline_roots, roots, self.owned_set())
            and any(self.model.exact_leaf(roots, self.primary_task, x) for x in self.permitted_current_components()),
            'OWNED_TASK_OR_FOREIGN_ROOT_CHANGED_AFTER_FLOW_GUARD')
        if remove:
            c.need(not self.removal_admission.get('final_fence_consumed'), 'ONCE_SETTINGS_REMOVE_FENCE')
            self.removal_admission['final_fence_consumed'] = True
            return
        c.need(d is not None and d.pending is not None and not d.pending.get('final_fence_consumed'),
            'ONE_PENDING_SETTINGS_INPUT_FENCE')
        raw_focus = runtime.camera_transport(c.FOREGROUND, 6)
        runtime.command_index = runtime.bridge.command_index; runtime.total_commands += 1
        focus = self.model.focus_metadata(raw_focus.decode('utf-8', 'strict'))
        c.need(focus == d.pending['focus'], 'SETTINGS_FOCUS_CHANGED_AFTER_FLOW_GUARD')
        if route:
            c.need(d.pending['kind'] == 'route' and d.pending['sent'] is True, 'ONE_SOURCE_BOUND_ROUTE_FENCE')
        else:
            c.need(d.pending['kind'] == 'rotation' and d.pending['request'] == self.active_api['request'],
                'ONE_SOURCE_BOUND_ROTATION_FENCE')
        d.pending['final_fence_consumed'] = True
        self.record('last-settings-input-fence', {'pending_intent': d.pending['intent'], 'focus': focus,
            'raw_tasks': raw_tasks.decode('utf-8', 'strict'), 'check_after_Flow_guard': True,
            'atomic_window_targeted_injection_claimed': False})

    def remove_owned(self):
        c = self.c; self.original_caller(['settings_driver.py'], {'close_round', 'cleanup'})
        task = self.primary_task
        if task is None:
            return None
        c.need(self.removal_admission is None, 'ONE_SETTINGS_TASK_RETIREMENT_AT_A_TIME')
        selected = self.flow.selected_task()
        c.need(task == selected['task'] and selected['prelaunch_absent'] is True and selected['cleanup_allowed'] is True,
            'ONLY_REAL_NATIVE_OWNED_SETTINGS_TASK')
        ownership = self.task_claims[-1]
        roots, tasks, before = self.verify_current_tasks(permit_absent=task)
        if task not in roots and task not in tasks:
            receipt = self.record('owned-task-already-retired', {'task': task, 'ownership': ownership,
                'readback': before, 'normal_remove_called': False})
        else:
            c.need(any(self.model.exact_leaf(roots, task, x) for x in self.permitted_current_components()),
                'FRESH_EXACT_SETTINGS_LEAF_BEFORE_REMOVE')
            argv = ['/system/bin/cmd', 'activity', 'stack', 'remove', str(task)]
            intent = self.record('owned-remove-intent', {'task': task, 'ownership': ownership,
                'before_tasks': before, 'argv': argv, 'automatic_retry': False})
            c.write_new(self.flow.root / ('remove-%d-attempted.json' % task), {'intent': intent, 'automatic_retry': False})
            self.removal_admission = {'argv': argv, 'sent': False}; self.remove_calls += 1
            try:
                self.android(argv, 15)
            finally:
                self.removal_admission = None
            stop = min(self.deadline, time.monotonic() + 8); receipt = None
            while time.monotonic() < stop:
                roots, tasks, observed = self.verify_current_tasks(permit_absent=task)
                if task not in roots and task not in tasks:
                    receipt = self.record('owned-remove-completed', {'task': task, 'intent': intent,
                        'after_tasks': observed, 'other_tasks_preserved': True}); break
                time.sleep(.2)
            c.need(receipt is not None, 'SETTINGS_REMOVE_UNKNOWN_NO_REPLAY')
        self.closed_native_tasks.append(task); self.primary_task = None
        return receipt

    def verify_original_callback(self, kind, callback, previous):
        fn = getattr(callback, '__func__', callback)
        self.c.need(kind == 'foreground' and previous is None and self.ui_owner is None
            and getattr(callback, '__self__', None) is self.driver and self.driver is not None
            and fn.__code__.co_filename == self.source_paths['settings_driver.py']
            and fn.__code__.co_name == 'owned_foreground', 'ONE_SOURCE_BOUND_SETTINGS_FOREGROUND_CALLBACK')
        self.ui_owner = self.driver

    def validate_ui_foreground(self, value, context):
        c = self.c
        c.need(type(value) is dict and set(value) == {'package', 'activity', 'window_token'}
            and value['package'] + '/' + value['activity'] == self.model.expanded_component(self.current_component)
            and re.fullmatch('[0-9a-f]{1,32}', value['window_token']) and self.ui_owner is self.driver
            and self.primary_task == context['owned_task'] and value['package'] == context['request']['package'],
            'CURRENT_EXACT_SOURCE_BOUND_SETTINGS_WINDOW')
        if not context.get('mutation_sent'):
            c.need(value['window_token'] == context['request']['window_token']
                and (context.get('observed_focus') is None or value == context['observed_focus']),
                'WINDOW_CHANGED_BEFORE_SETTINGS_INPUT')
        context['last_foreground'] = copy.deepcopy(value)

    def begin_ui_api(self, api, request):
        c = self.c; d = self.driver
        c.need(api == 'dispatch' and d is not None and self.ui_owner is d and self.active_api is None,
            'ONLY_SOURCE_BOUND_SETTINGS_DISPATCH')
        caller = self.original_caller(['settings_driver.py'], {'observe', 'toggle_rotation'})
        c.need(request.get('package') == 'com.android.settings' and request.get('display') == 0
            and request.get('accessibility_mode') == 'none' and type(request.get('window_token')) is str,
            'EXACT_SETTINGS_PACKAGE_WINDOW_DISPLAY')
        mutation = request.get('op') == 'click'
        if not mutation:
            c.need(caller['function'] == 'observe' and request == {'op': 'observe', 'package': 'com.android.settings',
                'window_token': request['window_token'], 'display': 0, 'accessibility_mode': 'none', 'with_png': True},
                'ONLY_CURRENT_SETTINGS_OBSERVATION')
        else:
            c.need(caller['function'] == 'toggle_rotation' and d.pending is not None
                and d.pending['kind'] == 'rotation' and d.pending['request'] == request
                and not d.pending.get('admitted') and d.actions <= self.active['limits']['maximum_UI_actions']
                and self.kind == 'settings_roundtrip' and self.current_component == self.active['routes']['rotation']['component']
                and request.get('method') == 'accessibility'
                and set(request) == {'op', 'package', 'window_token', 'display', 'accessibility_mode', 'selector', 'method'}
                and (self.phase_name == 'business' or d.pending.get('restoring') is True),
                'ONE_EXPLICIT_SOURCE_BOUND_AUTO_ROTATE_UI_CHANGE')
            d.pending['admitted'] = True
        self.guard(); self.verify_current_tasks(); self.api_sequence += 1
        context = {'schema': 'pocket4-settings-ui-context-v1', 'api': api, 'request': copy.deepcopy(request),
            'scope': self.flow.scope_ref, 'phase_lease': self.phase_ref, 'owned_claim': self.task_claims[-1],
            'owned_task': self.primary_task, 'caller': caller, 'mutation_sent': False,
            'api_sequence': self.api_sequence, 'native_returns': 0, 'native_acks': [], 'automatic_retry': False}
        focus = self.helper.foreground_callback(); self.validate_ui_foreground(focus, context)
        context['observed_focus'] = copy.deepcopy(focus)
        if mutation:
            context['actual_source_intent'] = d.pending['intent']
        context['_previous'] = self.flow.begin_api('api-%04d-%s' % (self.api_sequence, api), request, context)
        self.active_api = context
        return context

    def validate_snapshot_request(self, request, frame):
        raise RuntimeError('NO_SETTINGS_SNAPSHOT_INPUT_AUTHORITY')

    def record(self, label, value):
        self.c.need(type(label) is str and re.fullmatch('[a-z0-9][a-z0-9-]{0,60}', label), 'EXACT_SETTINGS_EVIDENCE_NAME')
        self.sequence += 1
        return self.c.write_new(self.evidence_root / ('%04d-' % self.sequence + label + '.json'), value)

    def android(self, argv, timeout=20):
        self.guard(); argv = list(argv)
        self.c.need(self.ordinary_admission is None, 'NO_REENTRANT_SETTINGS_ANDROID_CALL')
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
                        'PREEXISTING_SETTINGS_AND_BROWSER_TASKS_PRESERVED')
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

    def new_flow(self, index):
        flow = self.flow_type(self.c, self.scopes[index], 'launch', 'case-start', self.deadline,
            self.components['settings_guard.py'], self.policy_module.Policy,
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
                            if skip_trial_record and name == 'settings_trial.py' and frame.f_code.co_name == 'record':
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
