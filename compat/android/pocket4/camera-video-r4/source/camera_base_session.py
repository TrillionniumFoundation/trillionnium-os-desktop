"""New Camera adapters for the preserved photo state machine.

Two different immutable ScopeBindings own two normal launches. All commands
use the frozen recorder, seven-FD entry and one whole-case action-lock OFD.
No historical CameraSession, old epoch, old PID or old activation is loaded.
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
        self.s = session; self.ALEX_PREFIX = list(session.c.NATIVE_PREFIX)
        self.MAIN_HOST = session.baseline.docs['final_baseline']['daemon_status']['host_pid']

    def write_new(self, path, value, **options):
        s = self.s; path = Path(path)
        s.c.need(not options and path.is_relative_to(s.evidence_root)
            and path.parent.resolve() == path.parent, 'ONLY_PRIVATE_CURRENT_CAMERA_EVIDENCE')
        raw = value if type(value) is bytes else s.c.canonical(value)
        s.c.need(len(raw) <= (33554432 if path.suffix in ('.png', '.jpg') else 16777216),
                 'ORIGINAL_CAMERA_EVIDENCE_BOUNDS')
        ref = s.c.write_new(path, raw)
        if type(value) is dict:
            s.note_original_record(ref, value)
        return ref


class TargetReads:
    def __init__(self, session):
        self.s = session

    def read_file(self, path, maximum, **options):
        s = self.s; s.guard()
        s.c.need(not set(options) - {'single_link'} and
            (not options or options == {'single_link': True}), 'EXACT_CAMERA_READ_OPTIONS')
        wanted = [a for identity in s.identities for a in identity['artifacts'] if a['guest_path'] == path]
        profile = s.components['camera_profiles.py']; model = s.components['camera_photo_model.py']
        if wanted:
            s.c.need(len(wanted) == 1 and maximum == 33554432 and options == {'single_link': True},
                     'ONLY_CURRENT_SIGNED_CAMERA_APK_READ')
        elif path == '/data/user/0/com.android.camera2/shared_prefs/com.android.camera2_preferences.xml':
            s.c.need(maximum == 131072 and not options, 'ONLY_READ_THE_ORIGINAL_CAMERA_MODE_PREFERENCES')
        elif path == profile.MEDIA_PROVIDER_APK:
            s.c.need(maximum == 16777216 and options == {'single_link': True}, 'EXACT_MEDIA_PROVIDER_BYTES')
        else:
            s.c.need(s.photo_id is not None and s.owned_photo is not None
                and path == s.owned_photo['_data'] and maximum == model.MAX_PHOTO
                and not options and s.trial.shutter_calls == 1, 'ONLY_THIS_NEWLY_OWNED_CAMERA_PHOTO')
        raw, metadata = s.flow.view.target.read_file(path, maximum, **options)
        if wanted:
            s.c.need(s.c.sha(raw) == wanted[0]['sha256'] and len(raw) == wanted[0]['bytes']
                and metadata == wanted[0]['held_file'], 'SAME_APPROVED_CAMERA_APK_AND_HELD_FILE')
        elif path == profile.MEDIA_PROVIDER_APK:
            s.c.need(s.c.sha(raw) == profile.MEDIA_PROVIDER_SHA and len(raw) == profile.MEDIA_PROVIDER_BYTES,
                     'EXACT_CURRENT_MEDIA_PROVIDER_APK_BYTES')
        s.guard(); return raw, metadata

    def open_root(self, path, flags):
        s = self.s; s.guard()
        s.c.need(path in ('/data/user/0/com.android.camera2', '/data/user_de/0/com.android.camera2')
            and flags == os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW,
            'ONLY_ORIGINAL_CAMERA_CE_DE_IDENTITY_HANDLES')
        return s.flow.view.target.open_root(path, flags | os.O_CLOEXEC)


class Session:
    def __init__(self, c, active_ref, active, scopes, phase_ref, action_lock, components, evidence_root):
        self.c, self.active_ref, self.active = c, active_ref, active
        self.scopes, self.phase_ref, self.action_lock = list(scopes), phase_ref, action_lock
        self.components = components; self.kind = active['kind']; self.case = self.trial = None
        self.evidence_root = c.private_dir(evidence_root)
        self.host = components['app_runtime.py']; self.runtime = components['camera_runtime.py']
        self.plan = components['camera_plan.py']; self.policy_module = components['camera_policy.py']
        self.flow_type = components['camera_flow.py'].make_flow(components['app_flow.py'])
        self.transport_module = components['camera_transport.py']
        _, modules = c.support(active['support_manifest'])
        self.baseline = modules['business_baseline.py'].BusinessBaseline(active['baseline'], active['qualification'])
        self.identities = [c.parse(c.read_ref(active[key])) for key in ('target_identity', 'helper_identity')]
        self.flow = None; self.helper = None; self.closed = False; self.scope_index = 0; self.native_launches = 0
        self.task_claims = []; self.last_stacks = None; self.baseline_roots = None; self.baseline_tasks = None
        self.record_sequence = 0; self.api_sequence = 0; self.original_intents = []; self.used_intents = set()
        self.active_api = None; self.ordinary_admission = None; self.ui_dispatch_admission = None
        self.ui_owner = None; self.phase_name = 'business'
        self.phase_value = self.runtime.validate_phase(c, self.host, phase_ref, active_ref, active)
        self.source_paths = {name: str(Path(module.__file__)) for name, module in components.items()}
        self.allowed_ui_packages = {active['target_profile']['package']}
        self.image_ids_before = None; self.photo_id = None; self.owned_photo = None
        self.provider = None; self.hardware = None; self.owner = None; self.journal_cursor = None
        self.flow = self.new_flow(0)
        try:
            self.scope_module = self.flow.scope_module; self.target = TargetReads(self); self.tx = Evidence(self)
            self.helper = components['camera_ui.py'].OriginalAPIs(self)
            self.helper.foreground = self.owned_foreground
        except BaseException as primary:
            try:
                self.close()
            except BaseException as secondary:
                primary.add_note('CAMERA_SESSION_CONSTRUCTION_CLOSE:' + type(secondary).__name__)
            raise

    def new_flow(self, index):
        flow = self.flow_type(self.c, self.scopes[index], 'launch', 'case-start', self.deadline,
            self.components['camera_guard.py'], self.policy_module.Policy,
            private_context={'phase_lease': self.phase_ref, 'session': self})
        try:
            cls = self.transport_module.bound_class(self.c, flow.scope_module,
                self.active['support_manifest'], 'camera_android')
            def record(kind, value):
                self.c.write_new(flow.step / ('camera-transport-%03d.%s.json' % (value['sequence'], kind)), value)
            flow.camera_transport = cls(target=flow.view.target, environment=flow.view.environment,
                binding=flow.bound, runner=lambda argv, **kw: flow.bridge.runner(argv, **kw), record=record)
            return flow
        except BaseException:
            flow.close(); raise

    def note_original_record(self, ref, value):
        self.record_sequence += 1
        if value.get('automatic_retry') is not False:
            return
        if type(value.get('argv')) is list or type(value.get('request')) is dict:
            caller = self.original_caller(['camera_photo_trial.py'])
            self.original_intents.append({'ref': ref, 'value': copy.deepcopy(value), 'phase': self.phase_ref,
                'scope': self.flow.scope_ref, 'sequence': self.record_sequence, 'caller': caller})

    def verify_prelaunch_tasks(self, roots, tasks):
        self.c.need(self.phase_name == 'business' and self.baseline_tasks is not None
            and tasks == self.baseline_tasks and roots == self.baseline_roots
            and 1 <= self.native_launches <= 2, 'ORIGINAL_COMPLETE_TASK_BASELINE_BEFORE_EACH_CAMERA_LAUNCH')

    def discover_fixed(self):
        self.guard(); actual = self.baseline.docs['final_baseline']
        return actual['init_host_pid'], dict(self.environment), dict(actual['daemon_status'])

    def run_host(self, label, argv, timeout=20, pass_fds=()):
        self.c.need(not pass_fds and self.active_api is None, 'ONLY_TYPED_CAMERA_HOST_OBSERVATION_OR_LAUNCH')
        expected = self.c.NATIVE_PREFIX + ['launch', 'com.android.camera2', '--component',
            'com.android.camera2/com.android.camera.CameraLauncher', '--json']
        if argv != expected:
            return self.host_observation(label, argv, timeout)
        phase = 'open' if self.native_launches == 0 else 'reopen'
        f = self.trial
        self.c.need(timeout == 45 and self.phase_name == 'business' and self.native_launches < 2
            and label == phase + '-launch' and f is not None and f.owned is None
            and f.launch_calls == self.native_launches + 1 and f.pending_effects == {phase + '-launch'},
            'ORIGINAL_ONCE_NEW_CAMERA_LAUNCH_INTENT')
        self.consume_original_intent('launch', argv)
        if self.native_launches:
            old = self.flow; selected = old.selected_task()
            self.c.need(old.policy.remove_sent and self.last_stacks is not None
                and selected['task'] not in self.last_stacks[0] and selected['task'] not in self.last_stacks[1]
                and self.last_stacks[1] == self.baseline_tasks and self.last_stacks[0] == self.baseline_roots,
                'FIRST_CAMERA_SCOPE_ACTUALLY_RETIRED_BEFORE_NEW_SCOPE')
            old.close(); self.scope_index = 1; self.flow = self.new_flow(1)
        self.native_launches += 1
        return self.flow.native_launch()

    def host_observation(self, label, argv, timeout):
        c = self.c; profile = self.components['camera_profiles.py']
        journal = ['/usr/bin/journalctl', '-u', profile.PROVIDER_UNIT, '--no-pager', '-o', 'json']
        if label == 'provider-journal':
            c.need(timeout == 15 and (argv == journal + ['-n', '1']
                or self.journal_cursor is not None and argv == journal + ['--after-cursor', self.journal_cursor, '-n', '1024']),
                'ONLY_THE_CURRENT_CAMERA_JOURNAL_CURSOR')
        else:
            c.need(label in ('provider-before', 'provider-after') and timeout == 10
                and argv == ['/usr/bin/systemctl', 'show', profile.PROVIDER_UNIT,
                    '--property=Id,ActiveState,SubState,MainPID,ControlGroup,InvocationID,FragmentPath,ExecStart'],
                'ONLY_READ_CURRENT_CAMERA_MANAGER_STATE')
        self.guard()
        raw = self.flow.bridge.command(argv, timeout, mutation=False, label=label)
        ref = c.regular(self.flow.step / ('command-%03d.result.json' % self.flow.bridge.command_index), contents=False)
        value = c.parse(c.read_ref(ref))
        c.need(value['host_retirement_proved'] is True and value['evidence_complete'] is True
            and value['returncode'] == 0 and not value['timed_out'] and not value['errors']
            and c.read_ref(value['stdout']) == raw, 'ACTUAL_RETIRED_CAMERA_HOST_READ')
        if label == 'provider-journal':
            rows = self.components['camera_photo_model.py'].journal_records(raw)
            if argv[-2:] == ['-n', '1']:
                c.need(len(rows) == 1, 'ONE_FRESH_PROVIDER_CURSOR')
                self.journal_cursor = rows[0]['__CURSOR']
        return {'rc': value['returncode'], 'timed_out': value['timed_out'],
                'joined': value['host_retirement_proved'], 'guard_after': True,
                'stdout': raw, 'stderr': c.read_ref(value['stderr']), 'result': ref}

    def snapshot(self, label):
        c = self.c; o = self.components['camera_observations.py']
        c.need(label in ('acceptance-before', 'acceptance-after'), 'ORIGINAL_CAMERA_IDENTITY_SNAPSHOTS_ONLY')
        paths = self.android(['/system/bin/pm', 'path', 'com.android.camera2'], 20).decode('utf-8', 'strict').splitlines()
        c.need(len(paths) == 1 and paths[0].startswith('package:/data/app/') and paths[0].endswith('/base.apk'),
               'ONE_CURRENT_CAMERA_BASE_APK')
        guest = paths[0][len('package:'):]
        raw = self.android(['/system/bin/dumpsys', 'package', 'com.android.camera2'], 20)
        self.tx.write_new(self.evidence_root / (label + '-package.txt'), raw)
        identity = o.parse_identity(raw.decode('utf-8', 'strict'), guest)
        apk, _ = self.target.read_file(guest, 33554432, single_link=True)
        credentials = self.audio.credentials()
        owner_uid, owner_gid = credentials.observer_id('uid', 10062), credentials.observer_id('gid', 10062)
        dirs = {}
        for key, path in [('ce', '/data/user/0/com.android.camera2'), ('de', '/data/user_de/0/com.android.camera2')]:
            fd = self.target.open_root(path, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW)
            try:
                s = os.fstat(fd)
                dirs[key] = {'device': s.st_dev, 'inode': s.st_ino, 'uid': s.st_uid,
                             'gid': s.st_gid, 'mode': stat.S_IMODE(s.st_mode)}
            finally:
                os.close(fd)
            c.need(dirs[key]['uid'] == owner_uid and dirs[key]['gid'] == owner_gid
                and dirs[key]['inode'] == identity[key + '_inode'], 'ORIGINAL_CAMERA_DATA_INODE_UID_GATE')
        credentials.verify(); self.guard()
        value = {'package': 'com.android.camera2', 'epoch_sha256': self.active['framework_epoch_sha256'],
            'guest_credential_map': credentials.receipt,
            'identity': identity, 'directories': dirs, 'apk': {'guest_path': guest, 'bytes': len(apk), 'sha256': c.sha(apk)}}
        self.tx.write_new(self.evidence_root / (label + '.json'), value)
        return value

    def owned_foreground(self):
        c = self.c; f = self.trial
        c.need(f is not None and f.owned is not None, 'CAMERA_FOREGROUND_REQUIRES_ACTUAL_OWNED_TASK')
        raw = self.android(c.FOREGROUND, 6).decode('utf-8', 'strict')
        value = self.components['camera_observations.py'].focus_metadata(raw)
        c.need(value.get('verified') is True and value['task'] == f.owned[0]
            and value['package'] == 'com.android.camera2' and value['user'] == 0
            and value['activity'] in ('com.android.camera.CameraLauncher', 'com.android.camera.CameraActivity')
            and value['focused_activity'] == value['activity'], 'EXACT_CURRENT_CAMERA_TASK_ACTIVITY_WINDOW')
        self.last_focus = value
        return {key: value[key] for key in ('package', 'activity', 'window_token')}

    def verify_original_callback(self, kind, callback, previous):
        fn = getattr(callback, '__func__', None)
        self.c.need(kind == 'foreground' and getattr(callback, '__self__', None) is self
            and fn is not None and fn.__code__.co_filename == self.source_paths['camera_session.py']
            and fn.__code__.co_name == 'owned_foreground' and self.ui_owner is None,
            'ONE_NEW_CAMERA_OWNED_FOREGROUND_CALLBACK')
        self.ui_owner = self

    def validate_ui_foreground(self, value, context):
        c = self.c; focus = self.last_focus
        c.need(type(value) is dict and set(value) == {'package', 'activity', 'window_token'}
            and self.trial.owned is not None and focus['task'] == self.trial.owned[0] == context['owned_task']
            and value == {key: focus[key] for key in ('package', 'activity', 'window_token')}
            and value['package'] == 'com.android.camera2'
            and re.fullmatch('[0-9a-f]{1,32}', value['window_token']), 'FRESH_CAMERA_OWNED_FOREGROUND_BINDING')
        if not context.get('mutation_sent'):
            c.need(value['window_token'] == context['owned_window_token'], 'CAMERA_WINDOW_CHANGED_BEFORE_INPUT')
        context['last_foreground'] = copy.deepcopy(value)

    def begin_ui_api(self, api, request):
        c = self.c; f = self.trial
        c.need(api == 'dispatch' and self.case is not None and f is not None and self.ui_owner is self
            and self.active_api is None and request.get('package') == 'com.android.camera2'
            and request.get('display') == 0 and request.get('accessibility_mode', 'none') == 'none',
            'ONLY_THE_ORIGINAL_CAMERA_PHOTO_UI_SCOPE')
        caller = self.original_caller(['camera_photo_trial.py'])
        op = request.get('op'); mutates = op == 'click'
        allowed = {'op', 'package', 'display'}
        if 'accessibility_mode' in request:
            allowed.add('accessibility_mode')
        if op == 'observe':
            allowed.add('with_png'); c.need(request.get('with_png') is True, 'ORIGINAL_OWNED_PREVIEW_PIXELS')
        elif op == 'click':
            allowed |= {'method', 'selector'}
            c.need(self.phase_name == 'business' and f.shutter_calls == 1 and f.pending_effects == {'shutter'}
                and f.owned is not None and request.get('method') == 'accessibility'
                and request.get('selector') == {'id': 'com.android.camera2:id/shutter_button', 'enabled': True, 'clickable': True},
                'ONE_ORIGINAL_READY_CAMERA_SHUTTER_PENDING')
        else:
            c.need(op == 'dump', 'NO_ADDITIONAL_CAMERA_PHOTO_UI_OPERATION')
        c.need(set(request) == allowed, 'EXACT_ORIGINAL_CAMERA_PHOTO_REQUEST_FIELDS')
        self.guard(); claim, claim_ref = self.flow.scope_module.load_owned_task(self.flow.bound)
        raw = self.android(c.STACKS, 15); roots, tasks = self.flow.tasks.parse_stacks(raw.decode('utf-8', 'strict'))
        c.need(self.flow.tasks.exact_leaf(roots, claim['task'], 'com.android.camera2')
            and tasks == set(claim['prelaunch_task_ids']) | {claim['task']}
            and f.owned is not None and f.owned[0] == claim['task'], 'CURRENT_NEW_CAMERA_CLAIM_AND_COMPLETE_OTHER_TASK_SET')
        actual_focus = self.owned_foreground(); self.api_sequence += 1
        context = {'schema': 'pocket4-final-camera-photo-api-context-v1', 'api': api, 'request': copy.deepcopy(request),
            'scope': self.flow.scope_ref, 'phase_lease': self.phase_ref, 'owned_claim': claim_ref,
            'owned_task': claim['task'], 'owned_window_token': actual_focus['window_token'], 'caller': caller,
            'mutation_sent': False, 'api_sequence': self.api_sequence, 'native_returns': 0, 'automatic_retry': False}
        self.validate_ui_foreground(actual_focus, context)
        if mutates:
            context['original_intent'] = self.consume_original_intent('ui', request)['ref']
        previous = self.flow.begin_api('api-%04d-%s' % (self.api_sequence, api), request, context)
        context['_previous'] = previous; self.active_api = context
        return context

    def validate_native_request(self, request, context, action_used):
        return self.policy_module.native_request(self.c, context['request'], request, action_used)

    def caller_status(self, label):
        self.c.need(label == 'camera-photo-final' and self.phase_name == 'final_cleanup', 'EXACT_CAMERA_FINAL_CALLER_STATUS')
        raw = self.flow.bridge.command(self.c.NATIVE_PREFIX + ['status', '--json'], 10,
            mutation=False, label='Camera final caller status')
        value = self.c.parse(raw)
        self.c.need(value.get('ok') is True and value.get('state') == 'running'
            and value.get('host_pid') == self.baseline.docs['final_baseline']['daemon_status']['host_pid']
            and 'cell u1000 ' in value.get('message', ''), 'SAME_ACTUAL_CAMERA_USER_AND_MAIN')
        return value

    def close(self):
        errors = []
        for obj in (self.helper, self.flow):
            if obj is not None:
                try:
                    obj.close()
                except BaseException as error:
                    errors.append(error)
        self.closed = True
        if errors:
            first = errors[0]
            for error in errors[1:]:
                first.add_note('CAMERA_CONTEXT_CLOSE:' + type(error).__name__)
            raise first

    def guard(self, *, action_attempted=False):
        self.c.need(not self.closed and self.flow is not None, 'OPEN_CURRENT_CAMERA_CASE_SESSION')
        self.flow.guard(action_attempted=action_attempted)
        if self.hardware is not None:
            observation = self.components['camera_observations.py']
            self.c.need(observation.physical_identity() == self.hardware
                and observation.provider_owner() == self.owner
                and self.host.process(self.c, int(self.provider['MainPID'])) == self.manager_identity,
                'SAME_REAL_BUILTIN_CAMERA_AND_CURRENT_MANAGER')
        return self.baseline.guard(action_attempted=action_attempted)

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
            and request.get('display') == 0 and request.get('accessibility_mode', 'none') == 'none'
            and set(request) <= {'op', 'package', 'display', 'accessibility_mode', 'window_token', 'with_png', 'selector',
                'value', 'method', 'coords', 'input_source', 'frame_sha256', 'scope_sha256', 'context_token', 'crop'},
            'ONLY_ORIGINAL_INTERNAL_CAPTURE')
        if not context['mutation_sent']:
            c.need(request == expected, 'PRE_ACTION_CAPTURE_MUST_USE_UNCHANGED_ORIGINAL_REQUEST')
        else:
            c.need(set(request) <= {'package', 'display', 'accessibility_mode', 'crop'}, 'ONLY_ORIGINAL_POST_ACTION_CAPTURE_FIELDS')

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
