"""Original same-process API topology on an actual new ScopeBinding.

One case owner and one action-lock OFD span both independently claimed tasks.
This exposes neither arbitrary host commands nor an arbitrary backend dispatch.
The historical classes are never constructed; explicit new-source factories
provide the preserved semantic state machines.
"""
import base64
import copy
import inspect
import os
from pathlib import Path
import re
import stat
import time
import types


class Evidence:
    def __init__(self, session):
        self.s = session
        self.ALEX_PREFIX = list(session.c.NATIVE_PREFIX)
        self.MAIN_HOST = session.baseline.docs['final_baseline']['daemon_status']['host_pid']
    def write_new(self, path, value, **options):
        s = self.s; path = Path(path)
        s.c.need(not set(options) - {'alex_readable'} and (not options or type(options['alex_readable']) is bool)
            and path.is_relative_to(s.evidence_root) and path.parent.resolve() == path.parent,
            'ONLY_NEW_PRIVATE_CASE_EVIDENCE')
        raw = value if type(value) is bytes else s.c.canonical(value)
        s.c.need(len(raw) <= (33554432 if path.suffix == '.png' else 16777216), 'ORIGINAL_CASE_EVIDENCE_BOUND')
        ref = s.c.write_new(path, raw)
        if type(value) is dict:
            s.note_original_record(ref, value)
        return ref


class TargetReads:
    """Only original package bytes, CE/DE metadata and Calendar DB metadata."""
    def __init__(self, session):
        self.s = session
    def read_file(self, path, maximum, **options):
        s = self.s; s.guard()
        wanted = [a for identity in s.identities for a in identity['artifacts'] if a['guest_path'] == path]
        s.c.need(len(wanted) == 1 and maximum in (65536, 16 * 1024 * 1024, 48 * 1024 * 1024)
            and wanted[0]['bytes'] <= maximum and not set(options) - {'single_link'}
            and (not options or type(options['single_link']) is bool), 'ONLY_APPROVED_ORIGINAL_APP_BYTES')
        raw, metadata = s.flow.view.target.read_file(path, maximum, **options)
        s.c.need(s.c.sha(raw) == wanted[0]['sha256'] and len(raw) == wanted[0]['bytes']
            and metadata == wanted[0]['held_file'], 'SAME_ACTUAL_APPROVED_APP_ARTIFACT')
        s.guard(); return raw, metadata
    def open_root(self, path, flags):
        s = self.s; s.guard()
        directories = {'/data/' + prefix + '/0/' + identity['metadata']['package']
            for identity in s.identities for prefix in ('user', 'user_de')}
        allowed = path in directories and flags == os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        allowed |= (s.kind == 'calendar_reminder' and path == '/data/user/0/com.android.providers.calendar/databases/calendar.db'
                    and flags == os.O_RDONLY | os.O_NOFOLLOW)
        s.c.need(allowed, 'ONLY_ORIGINAL_READONLY_DATA_IDENTITY_FD')
        return s.flow.view.target.open_root(path, flags | os.O_CLOEXEC)


class Session:
    def __init__(self, c, active_ref, active, scopes, phase_ref, action_lock, components, evidence_root):
        self.c, self.active_ref, self.active = c, active_ref, active
        self.scopes, self.phase_ref, self.action_lock = list(scopes), phase_ref, action_lock
        self.components = components; self.kind = active['kind']; self.case = self.trial = self.model = None
        self.evidence_root = c.private_dir(evidence_root)
        self.host = components['app_runtime.py']; self.runtime = components['system_runtime.py']
        self.plan = components['system_plan.py']; self.policy_module = components['system_policy.py']
        self.flow_type = components['system_flow.py'].make_flow(components['app_flow.py'])
        self.transport_module = components['system_transport.py']
        _, modules = c.support(active['support_manifest'])
        self.baseline = modules['business_baseline.py'].BusinessBaseline(active['baseline'], active['qualification'])
        self.identities = [c.parse(c.read_ref(active[key])) for key in ('target_identity', 'provider_identity', 'helper_identity')]
        self.flow = None; self.closed = False; self.scope_index = 0; self.native_launches = 0
        self.task_claims = []; self.last_stacks = None; self.baseline_roots = None; self.baseline_tasks = None
        self.record_sequence = 0; self.api_sequence = 0; self.original_intents = []; self.used_intents = set()
        self.active_api = None; self.ordinary_admission = None; self.ui_dispatch_admission = None
        self.ui_owner = None
        self.phase_name = 'business'; self.phase_value = self.runtime.validate_phase(c, self.host, phase_ref, active_ref, active)
        self.source_paths = {name: str(Path(module.__file__)) for name, module in components.items()}
        self.allowed_ui_packages = {active['target_profile']['package']}
        if self.kind == 'contacts_search':
            self.allowed_ui_packages.add('com.android.settings')
        self.flow = self.new_flow(0)
        try:
            self.scope_module = self.flow.scope_module
            self.target = TargetReads(self); self.tx = Evidence(self)
            self.helper = components['system_ui.py'].OriginalAPIs(self)
        except BaseException as primary:
            try:
                self.flow.close()
            except BaseException as secondary:
                primary.add_note('SYSTEM_SESSION_CONSTRUCTION_CLOSE:' + type(secondary).__name__)
            self.closed = True
            raise

    @property
    def deadline(self):
        return self.phase_value['deadline_monotonic_ns'] / 1000000000

    @property
    def environment(self):
        return dict(self.flow.view.environment)

    def new_flow(self, index):
        flow = self.flow_type(self.c, self.scopes[index], 'launch', 'case-start', self.deadline,
            self.components['system_guard.py'], self.policy_module.Policy,
            private_context={'phase_lease': self.phase_ref, 'session': self})
        try:
            camera = self.transport_module.bound_class(self.c, flow.scope_module, self.active['support_manifest'], 'camera_android')
            root = self.transport_module.bound_class(self.c, flow.scope_module, self.active['support_manifest'], 'calendar_root_sql')
            def make_record(prefix):
                def record(kind, value):
                    self.c.write_new(flow.step / (prefix + '-%03d.%s.json' % (value['sequence'], kind)), value)
                return record
            options = {'target': flow.view.target, 'environment': flow.view.environment, 'binding': flow.bound,
                'runner': lambda argv, **kw: flow.bridge.runner(argv, **kw)}
            flow.camera_transport = camera(**options, record=make_record('camera-transport'))
            flow.root_transport = root(**options, record=make_record('root-sql-transport'))
            return flow
        except BaseException:
            flow.close(); raise

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

    def original_caller(self, names, methods=None):
        frame = inspect.currentframe()
        try:
            for _ in range(16):
                frame = frame.f_back
                if frame is None:
                    break
                for name in names:
                    if frame.f_code.co_filename == self.source_paths.get(name):
                        self.c.need(methods is None or frame.f_code.co_name in methods,
                            'ONLY_ORIGINAL_CASE_API_CALLER')
                        return {'source': name, 'function': frame.f_code.co_name}
            raise RuntimeError('TYPED_API_NOT_CALLED_BY_REVIEWED_ORIGINAL_COMPONENT')
        finally:
            del frame

    def note_original_record(self, ref, value):
        self.record_sequence += 1
        if value.get('automatic_retry') is not False:
            return
        argv = value.get('argv'); request = value.get('command', value.get('request'))
        if (type(argv) is list or type(request) is dict or value.get('method') == 'normal exact owned leaf remove'):
            # This record is a concrete output of the pinned new component's
            # original record method. Only a matching original pending state
            # can consume it, once, in this phase and current case scope.
            caller = self.original_caller([x for x in self.source_paths if x.startswith(('contacts_', 'calendar_'))])
            self.original_intents.append({'ref': ref, 'value': copy.deepcopy(value), 'phase': self.phase_ref,
                'scope': self.flow.scope_ref, 'sequence': self.record_sequence, 'caller': caller})

    def consume_original_intent(self, kind, requested):
        c = self.c; matches = []
        for item in self.original_intents:
            if item['ref']['path'] in self.used_intents or item['phase'] != self.phase_ref:
                continue
            value = item['value']; actual = value.get('argv')
            if kind == 'ui':
                actual = value.get('command', value.get('request'))
            if kind == 'remove' and value.get('method') == 'normal exact owned leaf remove':
                actual = ['/system/bin/cmd', 'activity', 'stack', 'remove', str(value['task'])]
            if actual == requested:
                matches.append(item)
        c.need(len(matches) == 1, 'ONE_UNCONSUMED_ORIGINAL_INTENT_REQUIRED:' + kind)
        item = matches[0]; c.read_ref(item['ref'])
        c.need(kind == 'launch' or item['scope'] == self.flow.scope_ref, 'INTENT_NOT_CURRENT_NEW_TASK_SCOPE')
        self.used_intents.add(item['ref']['path'])
        self.c.write_new(self.flow.step / ('once-intent-%05d.json' % item['sequence']), {
            'kind': kind, 'original': item['ref'], 'original_source': item['caller'],
            'scope': self.flow.scope_ref, 'phase_lease': self.phase_ref, 'automatic_retry': False})
        return item

    def android(self, argv, timeout=20):
        self.guard(); argv = list(argv)
        self.c.need(self.ordinary_admission is None, 'NO_REENTRANT_ORIGINAL_ANDROID_CALL')
        mutate = self.flow.policy.command(argv, timeout)
        self.ordinary_admission = (argv, timeout, mutate)
        try:
            raw = self.flow.android(argv, timeout, mutation=mutate)
            self.flow.policy.observe(argv, raw)
            if argv == self.c.STACKS:
                roots, tasks = self.flow.tasks.parse_stacks(raw.decode('utf-8', 'strict'))
                self.last_stacks = (roots, tasks)
                if self.baseline_tasks is None:
                    self.c.need(not any(x['component'].split('/')[0] == self.active['target_profile']['package']
                        for root in roots.values() for x in root['children']), 'PREEXISTING_TARGET_TASK_PRESERVED')
                    self.baseline_roots, self.baseline_tasks = copy.deepcopy(roots), set(tasks)
            return raw
        finally:
            self.ordinary_admission = None

    def verify_prelaunch_tasks(self, roots, tasks):
        self.c.need(self.phase_name == 'business' and self.baseline_tasks is not None
            and tasks == self.baseline_tasks and 1 <= self.native_launches <= 2, 'SAME_ACTUAL_PREEXISTING_TASK_SET')
        if self.kind == 'contacts_search':
            self.c.need(roots == self.baseline_roots, 'ORIGINAL_CONTACTS_COMPLETE_OTHER_TASK_ROOTS_PRESERVED')

    def run_host(self, label, argv, timeout=20, pass_fds=()):
        self.c.need(not pass_fds and self.active_api is None, 'ONLY_ORIGINAL_ONCE_NATIVE_LAUNCH_HOST_ROUTE')
        expected = self.c.NATIVE_PREFIX + ['launch', self.active['target_profile']['package'], '--component',
            self.active['target_profile']['component'], '--json']
        self.c.need(argv == expected and timeout == 45 and self.phase_name == 'business'
            and self.native_launches < 2 and label == ('contacts-launch' if self.kind == 'contacts_search'
                else 'launch-' + str(self.native_launches + 1)), 'EXACT_ORIGINAL_NATIVE_LAUNCH_PARAMETERS')
        self.consume_original_intent('launch', argv)
        if self.native_launches:
            old = self.flow; selected = old.selected_task()
            self.c.need(old.policy.remove_sent and self.last_stacks is not None
                and selected['task'] not in self.last_stacks[0] and selected['task'] not in self.last_stacks[1]
                and self.last_stacks[1] == self.baseline_tasks, 'FIRST_OWNED_TASK_ACTUALLY_REMOVED_BEFORE_SECOND_SCOPE')
            old.close(); self.scope_index = 1; self.flow = self.new_flow(1)
        self.native_launches += 1
        return self.flow.native_launch()

    def root_query(self, label, argv, timeout):
        c = self.c; c.need(self.kind == 'calendar_reminder' and timeout == 14 and self.active_api is None,
                          'ONLY_ORIGINAL_CALENDAR_ROOT_SQL_ROUTE')
        self.original_caller(['calendar_base.py', 'calendar_model.py'], {'counts', 'read'})
        model = self.model; prefix = ['/system/bin/env', '-i'] + [k + '=' + self.environment[k] for k in sorted(self.environment)]
        prefix += ['/system/bin/timeout', '-k', '2', '10', '/system/bin/sqlite3', '-readonly', '-json', model.DB]
        counts = 'PRAGMA query_only=ON;BEGIN;' + ' UNION ALL '.join(
            "SELECT '" + name + "' AS name,COUNT(*) AS count FROM " + name for name in model.TABLES) + ';ROLLBACK;'
        c.need(argv[:-1] == prefix and argv[-1] in (counts, model.observation_sql())
            and (label == 'calendar-owned-read' or label.startswith('calendar-counts-')),
            'ONLY_TWO_EXACT_ORIGINAL_READONLY_SQL_STATEMENTS')
        self.guard(); f = self.flow
        c.write_new(f.step / ('root-query-%05d.json' % (f.total_commands + 1)),
            {'logical': list(argv), 'timeout': timeout, 'root_read': True, 'Android_mutation': False,
             'phase_lease': self.phase_ref, 'automatic_retry': False})
        raw = f.root_transport(['/system/bin/sqlite3', '-readonly', '-json', model.DB, argv[-1]], 14)
        f.total_commands += 1; result = f.bridge.last_completed
        c.need(result is not None and result.host_tree_retired and not result.host_timed_out
            and result.returncode == 0 and result.stdout == raw, 'ACTUAL_HELD_ROOT_SQL_RESULT')
        return {'rc': result.returncode, 'timed_out': result.host_timed_out, 'joined': result.host_tree_retired,
                'guard_after': True, 'stdout': raw, 'stderr': result.stderr}

    def caller_status(self, label):
        self.c.need(label == ('contacts-search-final' if self.kind == 'contacts_search' else 'calendar-reminder-final')
            and self.phase_name == 'final_cleanup', 'ONLY_ORIGINAL_FINAL_CALLER_STATUS')
        raw = self.flow.bridge.command(self.c.NATIVE_PREFIX + ['status', '--json'], 10,
            mutation=False, label='Original final caller status')
        value = self.c.parse(raw)
        self.c.need(value.get('ok') is True and value.get('state') == 'running'
            and value.get('host_pid') == self.baseline.docs['final_baseline']['daemon_status']['host_pid']
            and 'cell u1000 ' in value.get('message', ''), 'ACTUAL_SAME_USER_AND_FINAL_MAIN_STATUS')
        return value

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

    def verify_original_callback(self, kind, callback, previous):
        c = self.c; fn = getattr(callback, '__func__', callback)
        c.need(hasattr(fn, '__code__'), 'ORIGINAL_SOURCE_CALLBACK_REQUIRED')
        file = fn.__code__.co_filename; name = fn.__code__.co_name
        if kind in ('foreground', 'package_name'):
            owner = getattr(callback, '__self__', None)
            c.need(owner is not None and getattr(owner, 's', None) is self,
                   'ORIGINAL_CALLBACK_BOUND_TO_THIS_ACTUAL_CASE')
            expected = ('contacts_trial.py', 'owned_foreground') if self.kind == 'contacts_search' else (
                'calendar_adapter.py', 'helper_foreground' if kind == 'foreground' else 'helper_package_name')
            c.need((file, name) == (self.source_paths[expected[0]], expected[1])
                and (kind != 'package_name' or self.kind == 'calendar_reminder')
                and (self.ui_owner is None or self.ui_owner is owner), 'ONE_ORIGINAL_OWNED_TASK_CALLBACK_OBJECT')
            self.ui_owner = owner
            return
        allowed = {('contacts_continuation.py', 'record_native'), ('contacts_mouse.py', 'record_native')} if self.kind == 'contacts_search' else {('calendar_picker_mouse.py', 'capture_ack')}
        c.need((file, name) in {(self.source_paths[p], n) for p, n in allowed}
            and not self.helper.ui_stack, 'ONLY_ORIGINAL_SINGLE_NATIVE_OBSERVER_LAYER')
        cells = {key: cell.cell_contents for key, cell in zip(fn.__code__.co_freevars, fn.__closure__ or ())}
        c.need(any(x is previous for x in cells.values()) and any(
            x is self or getattr(x, 's', None) is self or getattr(getattr(x, 't', None), 's', None) is self
            for x in cells.values()), 'OBSERVER_MUST_CALL_THE_UNCHANGED_PREVIOUS_NATIVE_BOUNDARY')

    def validate_ui_foreground(self, value, context):
        c = self.c
        c.need(type(value) is dict and set(value) == {'package', 'activity', 'window_token'}
            and value['package'] in self.allowed_ui_packages and re.fullmatch('[0-9a-f]{1,32}', value['window_token']),
            'ACTUAL_ORIGINAL_OWNED_FOREGROUND_REQUIRED')
        if self.kind == 'contacts_search':
            c.need(self.ui_owner is self.trial and self.trial.owned is not None
                and self.trial.owned[0] == context['owned_task'], 'CONTACTS_CALLBACK_NOT_CURRENT_OWNED_TASK')
            if value['package'] == 'com.android.settings':
                grant = self.trial.storage_from_create
                c.need(grant is not None and grant['owned_task'] == context['owned_task']
                    and value['activity'] == 'com.android.settings.Settings$ContactsStorageSettingsActivity',
                    'CONTACTS_STORAGE_REQUIRES_ORIGINAL_REAL_CREATE_ACK')
        else:
            c.need(self.case is not None and self.ui_owner is self.case.ui and context['owned_task'] in self.case.ui.owned
                and (value['package'], value['activity']) in self.case.ui.allowed,
                'CALENDAR_CALLBACK_NOT_CURRENT_ORIGINAL_ROUTE')
        request = context['request']; package = request.get('package', request.get('expected_package'))
        c.need(value['package'] == package, 'CURRENT_ORIGINAL_API_PACKAGE_CHANGED')
        if not context.get('mutation_sent') and 'window_token' in request:
            c.need(value['window_token'] == request['window_token'], 'OBSERVED_WINDOW_CHANGED_BEFORE_INPUT')
        context['last_foreground'] = copy.deepcopy(value)

    def begin_ui_api(self, api, request):
        c = self.c
        c.need(api in ('capture', 'ui', 'dispatch') and self.case is not None and self.ui_owner is not None
            and self.active_api is None, 'ONLY_BOUND_ORIGINAL_SAME_PROCESS_APIS')
        callers = ['contacts_trial.py', 'contacts_continuation.py', 'contacts_mouse.py'] if self.kind == 'contacts_search' else [
            'calendar_adapter.py', 'calendar_semantic.py', 'calendar_first_open.py', 'calendar_picker_mouse.py']
        caller = self.original_caller(callers)
        package = request.get('package', request.get('expected_package'))
        c.need(package in self.allowed_ui_packages and request.get('display') == 0
            and request.get('accessibility_mode') == 'none', 'EXPLICIT_ORIGINAL_PACKAGE_DISPLAY_MODE')
        operation = request.get('op')
        mutates = operation in ('click', 'set-text', 'snapshot-tap', 'scroll-forward', 'scroll-backward')
        if api == 'capture':
            c.need(operation is None and set(request) <= {'package', 'display', 'accessibility_mode', 'window_token',
                'context_token', 'frame_sha256', 'scope_sha256'} and 'window_token' in request,
                'ONLY_ORIGINAL_WINDOW_BOUND_CAPTURE_ARGUMENTS')
        elif api == 'ui':
            c.need(request == {'op': 'dump', 'expected_package': package, 'display': 0, 'accessibility_mode': 'none'},
                   'DIRECT_NATIVE_API_IS_READONLY_DUMP_ONLY')
        elif not mutates:
            c.need(request == {'op': 'observe', 'package': package, 'window_token': request.get('window_token'),
                'display': 0, 'accessibility_mode': 'none', 'with_png': True}, 'ONLY_ORIGINAL_FULL_OBSERVE_DISPATCH')
        else:
            c.need(self.phase_name == 'business', 'NO_UNDECLARED_UI_INPUT_DURING_ORIGINAL_FINAL_CLEANUP')
            allowed = {'op', 'package', 'display', 'accessibility_mode', 'window_token'}
            allowed |= {'selector', 'value'} if operation == 'set-text' else (
                {'selector', 'method'} if operation == 'click' else (
                {'coords', 'input_source', 'frame_sha256', 'scope_sha256', 'context_token'} if operation == 'snapshot-tap' else {'selector'}))
            c.need(set(request) == allowed and (operation != 'click' or request['method'] in ('accessibility', 'mouse')),
                   'EXACT_ORIGINAL_INPUT_ARGUMENT_SET')
            if self.kind == 'contacts_search':
                f = self.case
                c.need(operation in ('click', 'set-text', 'snapshot-tap') and f.c.pending is not None
                    and f.close_pending is None and 1 <= f.c.actions <= f.number <= 24,
                    'ORIGINAL_CONTACTS_PENDING_ACTION_AND_BUDGET')
                if operation == 'set-text':
                    m = self.components['contacts_model.py']; c.need(request['value'] in (m.NAME, m.EDITED), 'ONLY_ORIGINAL_LOCAL_CONTACT_TEXT')
            else:
                ui = self.case.ui
                c.need(len(ui.pending) == 1 and 1 <= ui.actions <= 20, 'ORIGINAL_CALENDAR_PENDING_INPUT_AND_RESERVED_CLEANUP_BUDGET')
                if operation == 'set-text':
                    m = self.model; c.need(request['value'] == m.CALENDAR_LABEL, 'ONLY_ORIGINAL_CALENDAR_LOGICAL_TEXT')
        self.guard()
        claim, claim_ref = self.flow.scope_module.load_owned_task(self.flow.bound)
        raw = self.android(c.STACKS, 15); roots, tasks = self.flow.tasks.parse_stacks(raw.decode('utf-8', 'strict'))
        c.need(self.flow.tasks.exact_leaf(roots, claim['task'], self.flow.scope['package'])
            and tasks == set(claim['prelaunch_task_ids']) | {claim['task']}, 'CURRENT_EXACT_OWNED_TASK_AND_OTHER_TASK_SET')
        self.api_sequence += 1
        context = {'schema': 'pocket4-final-original-api-context-v1', 'api': api, 'request': copy.deepcopy(request),
            'scope': self.flow.scope_ref, 'phase_lease': self.phase_ref, 'owned_claim': claim_ref,
            'owned_task': claim['task'], 'caller': caller, 'mutation_sent': False,
            'api_sequence': self.api_sequence, 'native_returns': 0, 'automatic_retry': False}
        actual_focus = self.helper.foreground_callback()
        self.validate_ui_foreground(actual_focus, context)
        if mutates:
            item = self.consume_original_intent('ui', request)
            context['original_intent'] = item['ref']
            if operation == 'snapshot-tap':
                node = item['value'].get('node')
                c.need(type(node) is dict and type(node.get('bounds_array')) is list
                    and len(node['bounds_array']) == 4 and all(type(x) is int for x in node['bounds_array']),
                    'ORIGINAL_CURRENT_OBSERVED_NODE_FOR_POINTER_INPUT')
                box = node['bounds_array']; c.need(box[0] < box[2] and box[1] < box[3]
                    and request['coords'] == [(box[0] + box[2]) // 2, (box[1] + box[3]) // 2]
                    and request['input_source'] == 'touch', 'POINTER_COORDINATES_ONLY_FROM_ORIGINAL_CURRENT_NODE')
        previous = self.flow.begin_api('api-%04d-%s' % (self.api_sequence, api), request, context)
        context['_previous'] = previous; self.active_api = context
        return context

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

    def record_native_return(self, request, value, context):
        context['native_returns'] += 1
        try:
            # Encode synchronously before the exact backend mutates this same
            # dict with before/after or post-capture UNKNOWN fields.
            self.c.write_new(self.flow.step / ('native-return-%03d.json' % context['native_returns']),
                {'request': request, 'native_response': value, 'scope': self.flow.scope_ref,
                 'phase_lease': self.phase_ref, 'automatic_retry': False})
        except BaseException as error:
            self.flow.bound.hold(error); self.flow.view.target.seal_admission(); raise

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

    def validate_snapshot_request(self, request, frame):
        self.c.need(self.case is not None and request.get('package') == self.active['target_profile']['package']
            and request.get('display') == 0 and request.get('accessibility_mode') == 'none'
            and request.get('window_token') == frame['meta']['scope']['window_token'],
            'ONLY_THIS_CASE_ISSUED_ORIGINAL_WINDOW_SNAPSHOT')

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
            self.c.write_new(self.flow.step / 'original-api-result.json', {
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
