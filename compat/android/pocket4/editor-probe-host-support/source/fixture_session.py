"""Fresh-Main same-process session for original Editor03 and Probe03.

One existing action-lock OFD spans both new task scopes. Original recorded
intents and pending states gate each mutation; no arbitrary dispatch or root
write command is exposed. Local record deletion remains in the original
Editor Evidence method, using only exact nonce-owned held descriptors.
"""
import base64, copy, inspect, os, re, stat, time, types
from pathlib import Path

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
    def __init__(self, session):
        self.s = session

    def read_file(self, path, maximum, **options):
        s = self.s; s.guard()
        s.c.need(maximum == 65536 and not set(options) - {'single_link'}
            and (not options or type(options['single_link']) is bool), 'EXACT_ORIGINAL_FIXTURE_READ_BOUND')
        wanted = [a for a in s.identities[0]['artifacts'] if a['guest_path'] == path]
        if wanted:
            s.c.need(len(wanted) == 1, 'ONE_ACTUAL_TARGET_APK')
            raw, metadata = s.flow.view.target.read_file(path, maximum, **options)
            s.c.need(len(raw) == wanted[0]['bytes'] and s.c.sha(raw) == wanted[0]['sha256']
                and metadata == wanted[0]['held_file'], 'SAME_ACTUAL_APPROVED_APK')
        else:
            s.editor_record_path(path, reading=True)
            raw, metadata = s.flow.view.target.read_file(path, maximum, **options)
        s.guard(); return raw, metadata

    def open_root(self, path, flags):
        s = self.s; s.guard(); s.editor_record_path(path, flags=flags)
        return s.flow.view.target.open_root(path, flags | os.O_CLOEXEC)

class Session:
    def __init__(self, c, active_ref, active, scopes, phase_ref, action_lock, components, evidence_root):
        self.c, self.active_ref, self.active = c, active_ref, active
        self.scopes, self.phase_ref, self.action_lock = list(scopes), phase_ref, action_lock
        self.components = components; self.kind = active['kind']; self.case = self.trial = None
        self.evidence_root = c.private_dir(evidence_root)
        self.host = components['app_runtime.py']; self.runtime = components['fixture_runtime.py']
        self.plan = components['fixture_plan.py']; self.policy_module = components['fixture_policy.py']
        self.flow_type = components['fixture_flow.py'].make_flow(components['app_flow.py'])
        self.transport_module = components['fixture_transport.py']
        _, modules = c.support(active['support_manifest'])
        self.baseline = modules['business_baseline.py'].BusinessBaseline(active['baseline'], active['qualification'])
        self.epoch_sha256 = self.baseline.value['framework_epoch']['sha256']
        self.identities = [c.parse(c.read_ref(active[key])) for key in ('target_identity', 'helper_identity')]
        self.flow = None; self.closed = False; self.scope_index = 0; self.native_launches = 0
        self.task_claims = []; self.last_stacks = None; self.baseline_roots = None; self.baseline_tasks = None
        self.record_sequence = 0; self.api_sequence = 0; self.original_intents = []; self.used_intents = set()
        self.active_api = None; self.ordinary_admission = None; self.ui_dispatch_admission = None; self.ui_owner = None
        self.phase_name = 'business'; self.phase_value = self.runtime.validate_phase(c, self.host, phase_ref, active_ref, active)
        self.source_paths = {name: str(Path(module.__file__)) for name, module in components.items()}
        self.allowed_ui_packages = {active['target_profile']['package']}
        self.flow = self.new_flow(0)
        try:
            self.scope_module = self.flow.scope_module; self.target = TargetReads(self); self.tx = Evidence(self)
            self.helper = components['fixture_ui.py'].OriginalAPIs(self)
        except BaseException as primary:
            try: self.flow.close()
            except BaseException as secondary: primary.add_note('FIXTURE_CONSTRUCTION_CLOSE:' + type(secondary).__name__)
            self.closed = True; raise

    def new_flow(self, index):
        flow = self.flow_type(self.c, self.scopes[index], 'launch', 'case-start', self.deadline,
            self.components['fixture_guard.py'], self.policy_module.Policy,
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

    def editor_record_path(self, path, *, reading=False, flags=None):
        c = self.c; c.need(self.kind == 'editor_ui03' and self.case is not None, 'ONLY_ORIGINAL_EDITOR_OWNED_RECORDS')
        call = self.original_caller(['fixture_editor.py'], {'absent', 'read', 'cleanup'})
        directory = '/data/user/0/org.droidloom.qa.editorcontract/files/editor-contract-v1'
        runs = [self.active['run_id'] + '_' + str(k) for k in range(2)]
        if reading:
            c.need(path in {directory + '/' + run + '.json' for run in runs} and call['function'] == 'read'
                and any(ev.run + '.json' == Path(path).name and ev.intent_submitted for ev in self.case.evidence),
                'ONLY_THIS_RUN_AFTER_ACKNOWLEDGED_NONCE_INTENT_RECORD')
            return
        if path == directory:
            c.need(call['function'] == 'cleanup' and self.trial.owned is None
                and self.case.c.pending is None and flags == os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                'EDITOR_RECORD_DELETE_REQUIRES_CLOSED_KNOWN_TASK_AND_NO_PENDING_INPUT')
        else:
            c.need(call['function'] == 'absent' and self.phase_name == 'business'
                and path in {directory + '/' + run + suffix for run in runs for suffix in ('.claim', '.json', '.json.new', '.json.bak')}
                and flags == os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                'EXACT_NEW_EDITOR_NONCE_PREEXISTENCE_READ_ONLY')

    def note_original_record(self, ref, value):
        self.record_sequence += 1
        if value.get('automatic_retry') is not False:
            return
        if type(value.get('argv')) is list or type(value.get('command', value.get('request'))) is dict:
            caller = self.original_caller(['fixture_trial.py', 'fixture_continuation.py', 'fixture_editor.py', 'fixture_probe.py'],
                skip_trial_record=True)
            self.original_intents.append({'ref': ref, 'value': copy.deepcopy(value), 'phase': self.phase_ref,
                'scope': self.flow.scope_ref, 'sequence': self.record_sequence, 'caller': caller})

    def verify_prelaunch_tasks(self, roots, tasks):
        self.c.need(self.phase_name == 'business' and self.baseline_tasks is not None
            and tasks == self.baseline_tasks and 1 <= self.native_launches <= 2, 'SAME_ACTUAL_PREEXISTING_TASK_SET')

    def run_host(self, label, argv, timeout=20, pass_fds=()):
        expected = self.c.NATIVE_PREFIX + ['launch', self.active['target_profile']['package'], '--component',
            self.active['target_profile']['component'], '--json']
        pending = ('native-launch-' if self.kind == 'editor_ui03' else 'launch-') + str(self.native_launches)
        self.c.need(not pass_fds and self.active_api is None and argv == expected and timeout == 45
            and self.phase_name == 'business' and self.native_launches < 2 and label == 'contacts-launch'
            and self.case is not None and self.case.c.pending == pending,
            'EXACT_ORIGINAL_ONCE_NATIVE_LAUNCH_IN_PENDING_FLOW')
        item = self.consume_original_intent('launch', argv)
        self.c.need(item['caller'] == {'source': 'fixture_trial.py', 'function': 'launch'}, 'ORIGINAL_TRIAL_LAUNCH_CALLER')
        if self.native_launches:
            old = self.flow; selected = old.selected_task()
            self.c.need(old.policy.remove_sent and self.last_stacks is not None and self.trial.owned is None
                and selected['task'] not in self.last_stacks[0] and selected['task'] not in self.last_stacks[1]
                and self.last_stacks[1] == self.baseline_tasks, 'FIRST_TASK_ACTUALLY_REMOVED_BEFORE_SECOND_SCOPE')
            old.close(); self.scope_index = 1; self.flow = self.new_flow(1)
        self.native_launches += 1
        return self.flow.native_launch()

    def caller_status(self, label):
        self.c.need(self.phase_name == 'final_cleanup' and label in ('probe-final-caller', 'editor-final-caller'),
                    'ONLY_ORIGINAL_FINAL_CALLER_STATUS')
        raw = self.flow.bridge.command(self.c.NATIVE_PREFIX + ['status', '--json'], 10,
            mutation=False, label='Original final caller status')
        value = self.c.parse(raw)
        self.c.need(value.get('ok') is True and value.get('state') == 'running'
            and value.get('host_pid') == self.baseline.docs['final_baseline']['daemon_status']['host_pid']
            and 'cell u1000 ' in value.get('message', ''), 'ACTUAL_SAME_USER_AND_FINAL_MAIN_STATUS')
        return value

    def verify_original_callback(self, kind, callback, previous):
        c = self.c; fn = getattr(callback, '__func__', callback)
        c.need(hasattr(fn, '__code__'), 'ORIGINAL_SOURCE_CALLBACK_REQUIRED')
        if kind == 'foreground':
            owner = getattr(callback, '__self__', None)
            c.need(owner is self.trial and owner.s is self and fn.__code__.co_filename == self.source_paths['fixture_trial.py']
                and fn.__code__.co_name == 'owned_foreground' and self.ui_owner is None,
                'ONE_THIS_TRIAL_OWNED_FOREGROUND_CALLBACK')
            self.ui_owner = owner; return
        c.need(kind == 'native_observer' and fn.__code__.co_filename == self.source_paths['fixture_continuation.py']
            and fn.__code__.co_name == 'record_native' and not self.helper.ui_stack,
            'ONLY_ORIGINAL_SINGLE_NATIVE_OBSERVER_LAYER')
        cells = {k: cell.cell_contents for k, cell in zip(fn.__code__.co_freevars, fn.__closure__ or ())}
        c.need(any(x is previous for x in cells.values()) and any(getattr(getattr(x, 't', None), 's', None) is self
            for x in cells.values()), 'OBSERVER_MUST_CALL_UNCHANGED_PREVIOUS_NATIVE_BOUNDARY')

    def validate_ui_foreground(self, value, context):
        c = self.c; profile = self.active['target_profile']; activity = profile['component'].split('/')[1]
        if activity.startswith('.'):
            activity = profile['package'] + activity
        c.need(type(value) is dict and set(value) == {'package', 'activity', 'window_token'}
            and value['package'] == profile['package'] and value['activity'] == activity
            and re.fullmatch('[0-9a-f]{1,32}', value['window_token'])
            and self.ui_owner is self.trial and self.trial.owned is not None
            and self.trial.owned[0] == context['owned_task'], 'CURRENT_ORIGINAL_EXACT_OWNED_WINDOW')
        expected = context['request']
        c.need(value['package'] == expected['package'], 'ORIGINAL_API_PACKAGE_CHANGED')
        if not context.get('mutation_sent'):
            c.need(value['window_token'] == expected['window_token']
                and (context.get('observed_focus') is None or value == context['observed_focus']),
                'OBSERVED_WINDOW_CHANGED_BEFORE_INPUT')
        context['last_foreground'] = copy.deepcopy(value)

    def begin_ui_api(self, api, request):
        c = self.c; f = self.case
        c.need(api in ('capture', 'dispatch', 'window_state') and f is not None and self.ui_owner is self.trial
            and self.active_api is None, 'ONLY_BOUND_ORIGINAL_FIXTURE_APIS')
        caller = self.original_caller(['fixture_trial.py', 'fixture_continuation.py', 'fixture_editor.py'])
        c.need(request.get('package') in self.allowed_ui_packages and request.get('display') == 0
            and request.get('accessibility_mode') == 'none' and type(request.get('window_token')) is str,
            'EXPLICIT_ORIGINAL_PACKAGE_DISPLAY_MODE_WINDOW')
        operation = request.get('op'); mutates = operation in ('click', 'set-text')
        if api in ('capture', 'window_state'):
            c.need(self.kind == 'editor_ui03' and caller == {'source': 'fixture_editor.py', 'function': 'key'}
                and set(request) == {'package', 'window_token', 'display', 'accessibility_mode'},
                'ONLY_ORIGINAL_EDITOR_FOCUSED_KEY_CAPTURE_AND_WINDOW_READ')
        elif not mutates:
            c.need(request == {'op': 'observe', 'package': request['package'], 'window_token': request['window_token'],
                'display': 0, 'accessibility_mode': 'none', 'with_png': True}, 'ONLY_ORIGINAL_OBSERVE_DISPATCH')
        else:
            allowed = {'op', 'package', 'display', 'accessibility_mode', 'window_token', 'selector'}
            allowed |= {'value'} if operation == 'set-text' else {'method'}
            c.need(self.phase_name == 'business' and set(request) == allowed and f.c.pending is not None
                and 1 <= f.c.actions <= self.active['limits']['maximum_UI_actions']
                and caller == {'source': 'fixture_continuation.py', 'function': 'step'},
                'ORIGINAL_PENDING_CONTINUATION_WITHIN_ACTION_BUDGET')
            if self.kind == 'qa_probe03':
                selector = request['selector']; ident = selector.get('id'); package = request['package']; index = self.native_launches - 1
                c.need(index in (0, 1), 'CURRENT_ORIGINAL_ROUND')
                if operation == 'click':
                    c.need(ident == package + ':id/confirm' and request['method'] == 'accessibility', 'ONLY_ORIGINAL_CONFIRM_CONTROL')
                else:
                    values = {package + ':id/editor': ('', 'Pocket4 QA r12 7d2ab6f9 round%d 中文 café 😀' % index),
                              package + ':id/other_editor': ('', 'Owned second field %d Ω' % index)}
                    c.need(ident in values and request['value'] in values[ident], 'ONLY_ORIGINAL_TWO_FIELD_VALUES')
            else:
                c.need(operation == 'set-text' and request['value'] in ('', 'Pocket4 editor %d 中文 café 😀' % (self.native_launches - 1))
                    and request['selector'].get('editable') is True and request['selector'].get('focused') is True,
                    'ONLY_ORIGINAL_FOCUSED_EDITOR_TEXT')
        self.guard(); claim, claim_ref = self.flow.scope_module.load_owned_task(self.flow.bound)
        raw = self.android(c.STACKS, 15); roots, tasks = self.flow.tasks.parse_stacks(raw.decode('utf-8', 'strict'))
        c.need(self.flow.tasks.exact_leaf(roots, claim['task'], self.flow.scope['package'])
            and tasks == set(claim['prelaunch_task_ids']) | {claim['task']}, 'CURRENT_EXACT_OWNED_TASK_SET')
        self.api_sequence += 1
        context = {'schema': 'pocket4-final-original-api-context-v1', 'api': api, 'request': copy.deepcopy(request),
            'scope': self.flow.scope_ref, 'phase_lease': self.phase_ref, 'owned_claim': claim_ref,
            'owned_task': claim['task'], 'caller': caller, 'mutation_sent': False, 'api_sequence': self.api_sequence,
            'native_returns': 0, 'automatic_retry': False}
        focus = self.helper.foreground_callback(); self.validate_ui_foreground(focus, context)
        context['observed_focus'] = copy.deepcopy(focus)
        if mutates:
            context['original_intent'] = self.consume_original_intent('ui', request)['ref']
        context['_previous'] = self.flow.begin_api('api-%04d-%s' % (self.api_sequence, api), request, context)
        self.active_api = context
        return context


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
                            if skip_trial_record and name == 'fixture_trial.py' and frame.f_code.co_name == 'record':
                                continue
                            self.c.need(methods is None or frame.f_code.co_name in methods,
                                'ONLY_ORIGINAL_CASE_API_CALLER')
                            return {'source': name, 'function': frame.f_code.co_name}
                raise RuntimeError('TYPED_API_NOT_CALLED_BY_REVIEWED_ORIGINAL_COMPONENT')
            finally:
                del frame

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
