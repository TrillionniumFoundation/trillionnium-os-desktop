"""Three fresh package scopes and a same-process typed Camera/Player facade.

The unchanged seven-FD transport, held identities, absolute phase deadlines and
whole-case OFD are reused. A separate parent owns finite acoustic siblings.
"""
import copy
import inspect
import os
from pathlib import Path
import re
import stat
import time

CAMERA = 'com.android.camera2'
PLAYER = 'com.android.gallery3d'

def expand(package, activity):
    return package + activity if activity.startswith('.') else activity

def make_session(base):
    class Session(base.Session):
        def __init__(self, c, active_ref, active, scopes, phase_ref, action_lock,
                     components, evidence_root, acoustic):
            self.c, self.active_ref, self.active = c, active_ref, active
            self.scopes, self.phase_ref, self.action_lock = list(scopes), phase_ref, action_lock
            self.components = components; self.kind = active['kind']; self.case = self.trial = self.driver = None
            self.evidence_root = c.private_dir(evidence_root)
            self.root = Path(active['case_root'])
            self.host = components['app_runtime.py']; self.runtime = components['camera_runtime.py']
            self.plan = components['camera_plan.py']; self.policy_module = components['camera_policy.py']
            self.flow_type = components['camera_flow.py'].make_flow(components['app_flow.py'])
            self.transport_module = components['camera_transport.py']; self.acoustic = acoustic
            _, modules = c.support(active['support_manifest'])
            self.baseline = modules['business_baseline.py'].BusinessBaseline(active['baseline'], active['qualification'])
            self.identities = [c.parse(c.read_ref(active[k])) for k in self.plan.IDENTITIES]
            self.flow = self.helper = None; self.closed = False; self.scope_index = 0; self.native_launches = 0
            self.task_claims = []; self.last_stacks = self.baseline_roots = self.baseline_tasks = None
            self.record_sequence = self.api_sequence = 0; self.original_intents = []; self.used_intents = set()
            self.active_api = self.ordinary_admission = self.ui_dispatch_admission = self.ui_owner = None
            self.phase_name = 'business'; self.phase_value = self.runtime.validate_phase(c, self.host,
                phase_ref, active_ref, active)
            self.source_paths = {name: str(Path(module.__file__)) for name, module in components.items()}
            self.allowed_ui_packages = {CAMERA, PLAYER}; self.last_focus = None
            self.video_id = self.owned_video = None; self.emitter_retired = False
            self.provider = self.hardware = self.owner = self.journal_cursor = None
            self.flow = self.new_flow(0)
            try:
                self.scope_module = self.flow.scope_module
                self.target = TargetReads(self); self.tx = base.Evidence(self)
                self.helper = components['camera_ui.py'].OriginalAPIs(self)
                self.helper.foreground = self.owned_foreground
                self.audio = components['camera_audio_runtime.py'].AudioRuntime(self)
            except BaseException as primary:
                try: self.close()
                except BaseException as secondary: primary.add_note('VIDEO_CONSTRUCTION_CLOSE:' + repr(secondary))
                raise

        def record(self, label, value):
            self.c.need(re.fullmatch('[a-zA-Z0-9_-]{1,96}', label), 'BOUNDED_VIDEO_EVIDENCE_LABEL')
            self.record_sequence += 1
            self.c.need(self.record_sequence <= 1024, 'FINITE_VIDEO_EVIDENCE_RECORDS')
            return self.c.write_new(self.evidence_root / ('%04d-%s.json' % (self.record_sequence, label)), value)

        def note_original_record(self, ref, value):
            return None

        def claim_intent(self, kind, argv):
            self.original_caller(['camera_video_driver.py'])
            self.c.need(kind in ('launch', 'view', 'remove'), 'EXPLICIT_CURRENT_VIDEO_INTENT_KIND')
            row = {'kind': kind, 'argv': list(argv), 'scope': self.flow.scope_ref,
                'phase': self.phase_ref, 'sequence': len(self.original_intents) + 1, 'automatic_retry': False}
            row['ref'] = self.record('once-' + kind + '-intent', row)
            self.original_intents.append(copy.deepcopy(row)); return row['ref']

        def consume_intent(self, kind, argv):
            rows = [r for r in self.original_intents if r['kind'] == kind and r['argv'] == argv
                and r['scope'] == self.flow.scope_ref and r['phase'] == self.phase_ref
                and r['ref']['path'] not in self.used_intents]
            self.c.need(len(rows) == 1, 'ONE_CURRENT_VIDEO_INTENT_WITHOUT_REPLAY')
            row = rows[0]; self.c.read_ref(row['ref']); self.used_intents.add(row['ref']['path'])
            self.record('consumed-' + kind, {'intent': row['ref'], 'scope': self.flow.scope_ref,
                'phase': self.phase_ref, 'automatic_retry': False}); return row

        def verify_prelaunch_tasks(self, roots, tasks):
            self.c.need(self.phase_name == 'business' and self.baseline_tasks is not None
                and roots == self.baseline_roots and tasks == self.baseline_tasks
                and self.native_launches == self.scope_index + 1 <= 3,
                'EVERY_NORMAL_LAUNCH_REQUIRES_EXACT_ORIGINAL_TASK_BASELINE')

        def switch_scope(self, index):
            self.original_caller(['camera_video_driver.py'], {'launch'})
            self.c.need(index == self.scope_index + 1 and index in (1, 2)
                and self.driver.owned is None and self.driver.close_pending is None
                and self.flow.policy.remove_sent and self.last_stacks == (self.baseline_roots, self.baseline_tasks),
                'ACTUAL_OLD_BINDER_TASK_RETIREMENT_BEFORE_NEXT_SCOPE')
            old = self.flow; old.close(); self.scope_index = index
            self.flow = self.new_flow(index); self.scope_module = self.flow.scope_module

        def launch(self):
            self.original_caller(['camera_video_driver.py'], {'launch'})
            expected = self.c.NATIVE_PREFIX + ['launch', self.flow.scope['package'], '--component',
                self.flow.scope['component'], '--json']
            self.c.need(self.phase_name == 'business' and self.native_launches == self.scope_index
                and self.driver.owned is None and self.driver.pending == 'launch-' + str(self.scope_index),
                'ONCE_NORMAL_LAUNCH_IN_THIS_PACKAGE_SCOPE')
            self.consume_intent('launch', expected); self.native_launches += 1
            return self.flow.native_launch()

        def android(self, argv, timeout=20):
            self.guard(); argv = list(argv)
            self.c.need(self.ordinary_admission is None, 'NO_REENTRANT_VIDEO_ANDROID_COMMAND')
            mutation = self.flow.policy.command(argv, timeout); self.ordinary_admission = (argv, timeout, mutation)
            try:
                raw = self.flow.android(argv, timeout, mutation=mutation)
                if argv == self.c.STACKS:
                    roots, tasks = self.flow.tasks.parse_stacks(raw.decode('utf-8', 'strict'))
                    if self.baseline_tasks is None:
                        self.c.need(not any(x['component'].split('/')[0] in (CAMERA, PLAYER)
                            for r in roots.values() for x in r['children']), 'PREEXISTING_CAMERA_AND_GALLERY_TASKS_PRESERVED')
                        self.baseline_roots, self.baseline_tasks = copy.deepcopy(roots), set(tasks)
                    self.last_stacks = (roots, tasks)
                return raw
            finally:
                self.ordinary_admission = None

        def check_owned_task(self):
            c = self.c; f = self.driver
            c.need(f is not None and f.owned is not None and self.last_stacks is not None,
                'ACTUAL_CURRENT_VIDEO_TASK_REQUIRED')
            claim = self.flow.selected_task(); roots, tasks = self.last_stacks; task = f.owned
            c.need(task == claim['task'] and task not in self.baseline_tasks
                and set(claim['prelaunch_task_ids']) == self.baseline_tasks
                and tasks == self.baseline_tasks | {task}
                and self.flow.tasks.exact_leaf(roots, task, self.flow.scope['package'])
                and {k: v for k, v in roots.items() if k != task} == self.baseline_roots,
                'EXACT_OWNED_VIDEO_LEAF_AND_UNCHANGED_FOREIGN_TASKS')
            return task

        def owned_foreground(self):
            self.c.need(self.driver is not None and self.driver.owned is not None, 'CURRENT_OWNED_VIDEO_FOREGROUND')
            raw = self.android(self.c.FOREGROUND, 6).decode('utf-8', 'strict')
            value = self.components['camera_observations.py'].focus_metadata(raw)
            package = self.flow.scope['package']
            activity = expand(package, value.get('activity', ''))
            focused = expand(package, value.get('focused_activity', ''))
            allowed = ({'com.android.camera.CameraLauncher', 'com.android.camera.CameraActivity'}
                if package == CAMERA else {PLAYER + '.app.GalleryActivity', PLAYER + '.app.MovieActivity'})
            self.c.need(value.get('verified') is True and value['task'] == self.driver.owned
                and value['package'] == package and value['user'] == 0 and activity in allowed and focused == activity,
                'EXACT_CURRENT_CAMERA_OR_PLAYER_ACTIVITY')
            self.last_focus = value
            return {k: value[k] for k in ('package', 'activity', 'window_token')}

        def verify_original_callback(self, kind, callback, previous):
            fn = getattr(callback, '__func__', None)
            self.c.need(kind == 'foreground' and getattr(callback, '__self__', None) is self
                and fn is not None and fn.__code__.co_filename == self.source_paths['camera_session.py']
                and fn.__code__.co_name == 'owned_foreground' and self.ui_owner is None,
                'ONE_CURRENT_VIDEO_FOREGROUND_CALLBACK')
            self.ui_owner = self

        def validate_ui_foreground(self, value, context):
            c, focus = self.c, self.last_focus
            c.need(type(value) is dict and set(value) == {'package', 'activity', 'window_token'}
                and self.driver.owned is not None and focus['task'] == self.driver.owned == context['owned_task']
                and value == {k: focus[k] for k in ('package', 'activity', 'window_token')}
                and value['package'] == self.flow.scope['package']
                and re.fullmatch('[0-9a-f]{1,32}', value['window_token']), 'CURRENT_OWNED_VIDEO_WINDOW')
            if not context.get('mutation_sent'):
                c.need(value['window_token'] == context['owned_window_token']
                    and focus == context['observed_focus'], 'VIDEO_WINDOW_CHANGED_BEFORE_NATIVE_INPUT')
            context['last_foreground'] = copy.deepcopy(value)

        def begin_ui_api(self, api, request):
            c = self.c; package = self.flow.scope['package']; f = self.driver
            c.need(self.ui_owner is self and f is not None and self.active_api is None
                and request.get('package', request.get('expected_package')) == package
                and request.get('display') == 0 and request.get('accessibility_mode', 'none') == 'none',
                'ONLY_CURRENT_VIDEO_TYPED_API')
            caller = self.original_caller(['camera_video_driver.py'])
            op = request.get('op'); mutates = api == 'dispatch' and op == 'click'
            if api == 'capture':
                c.need(package == PLAYER and f.pending is None
                    and set(request) == {'package', 'display', 'accessibility_mode', 'window_token'},
                    'ONLY_CURRENT_OWNED_MOVIE_FRAME_CAPTURE')
            else:
                c.need(api == 'dispatch' and op in ('observe', 'dump', 'click'), 'NO_OTHER_CAMERA_VIDEO_API')
                fields = {'op', 'package', 'display'}
                if 'accessibility_mode' in request: fields.add('accessibility_mode')
                if op == 'observe':
                    fields.add('with_png'); c.need(request.get('with_png') is True, 'CURRENT_VIDEO_PIXELS')
                elif mutates:
                    fields |= {'method', 'selector'}
                    c.need(package == CAMERA and self.phase_name == 'business'
                        and self.scope_index == 0 and f.recording is not None
                        and f.recording.pending is not None and request == f.recording.pending['request'],
                        'EXACT_ONCE_DURABLE_VIDEO_CONTROL')
                c.need(set(request) == fields, 'EXACT_VIDEO_API_FIELDS')
            self.guard(); self.android(c.STACKS, 15); task = self.check_owned_task()
            actual = self.owned_foreground(); observed = copy.deepcopy(self.last_focus)
            if mutates:
                c.need(observed == f.recording.pending['observed_focus'], 'CLAIMED_VIDEO_WINDOW_DRIFT')
                c.read_ref(f.recording.pending['intent_ref'])
            self.api_sequence += 1
            context = {'schema': 'pocket4-current-camera-video-api-v1', 'api': api, 'request': copy.deepcopy(request),
                'scope': self.flow.scope_ref, 'phase_lease': self.phase_ref, 'owned_task': task,
                'owned_window_token': actual['window_token'], 'observed_focus': observed,
                'caller': caller, 'mutation_sent': False, 'api_sequence': self.api_sequence,
                'native_returns': 0, 'automatic_retry': False}
            self.validate_ui_foreground(actual, context)
            if mutates: context['original_intent'] = f.recording.pending['intent_ref']
            previous = self.flow.begin_api('api-%04d-%s' % (self.api_sequence, api), request, context)
            context['_previous'] = previous; self.active_api = context
            return context

        def record_native_return(self, request, value, context):
            context['native_returns'] += 1
            try:
                boundary = self.c.write_new(self.flow.step / ('native-return-%03d.json' % context['native_returns']),
                    {'request': request, 'native_response': value, 'scope': self.flow.scope_ref,
                        'phase_lease': self.phase_ref, 'automatic_retry': False})
                if request.get('op') == 'click':
                    self.c.need(self.driver.recording is not None and context['native_returns'] >= 1,
                        'KNOWN_CURRENT_VIDEO_RECORDING_STATE')
                    self.driver.recording.native_return(request=request, reply=value,
                        monotonic_ns=time.monotonic_ns(), boundary_ref=boundary)
            except BaseException as error:
                self.flow.bound.hold(error); self.flow.view.target.seal_admission(); raise

        def movie_resolve_argv(self):
            self.c.need(self.owned_video is not None, 'NO_RESOLVE_OF_UNOWNED_VIDEO')
            return ['/system/bin/cmd', 'package', 'resolve-activity', '--brief', '--user', '0',
                '-a', 'android.intent.action.VIEW', '-d', self.owned_video['uri'], '-t', self.owned_video['mime_type'],
                '-n', PLAYER + '/.app.MovieActivity']

        def movie_view_argv(self):
            task = self.driver.owned; self.c.need(type(task) is int and task > 0, 'OWNED_PLAYER_TASK')
            return ['/system/bin/am', 'start-activity', '-W', '--user', '0', '--display', '0', '--task', str(task),
                '--activity-clear-top', '-a', 'android.intent.action.VIEW', '-d', self.owned_video['uri'],
                '-t', self.owned_video['mime_type'], '--ez', 'android.intent.extra.finishOnCompletion', 'false',
                '-n', PLAYER + '/.app.MovieActivity']

        def host_read(self, label, argv, timeout):
            self.original_caller(['camera_audio_runtime.py'])
            self.audio.admit_host(label, argv, timeout); self.guard()
            raw = self.flow.bridge.command(argv, timeout, mutation=False, label=label)
            ref = self.c.regular(self.flow.step / ('command-%03d.result.json' % self.flow.bridge.command_index), contents=False)
            value = self.c.parse(self.c.read_ref(ref))
            self.c.need(value['host_retirement_proved'] is True and value['evidence_complete'] is True
                and value['returncode'] == 0 and not value['timed_out'] and not value['errors']
                and self.c.read_ref(value['stdout']) == raw, 'ACTUAL_RETIRED_VIDEO_HOST_OBSERVATION')
            return raw, ref

        def caller_status(self, label):
            self.c.need(label == 'camera-video-final' and self.phase_name == 'final_cleanup', 'EXACT_FINAL_VIDEO_CALLER')
            raw = self.flow.bridge.command(self.c.NATIVE_PREFIX + ['status', '--json'], 10,
                mutation=False, label='Camera video final caller status')
            value = self.c.parse(raw)
            self.c.need(value.get('ok') is True and value.get('state') == 'running'
                and value.get('host_pid') == self.baseline.docs['final_baseline']['daemon_status']['host_pid']
                and 'cell u1000 ' in value.get('message', ''), 'UNCHANGED_ACTUAL_VIDEO_MAIN')
            return value

        def close(self):
            first = None
            audio = getattr(self, 'audio', None)
            if audio is not None:
                try: audio.close()
                except BaseException as error: first = error
            try: super().close()
            except BaseException as error:
                if first is None: first = error
                else: first.add_note('OTHER_CURRENT_VIDEO_CONTEXT_CLOSE:' + repr(error))
            if first is not None: raise first
    return Session

class TargetReads:
    def __init__(self, session): self.s = session
    def read_file(self, path, maximum, **options):
        s = self.s; s.guard(); p = s.components['camera_profiles.py']
        wanted = [a for identity in s.identities for a in identity['artifacts'] if a['guest_path'] == path]
        if wanted:
            s.c.need(len(wanted) == 1 and maximum == 33554432 and options == {'single_link': True},
                'CURRENT_SIGNED_VIDEO_APP_APK_ONLY')
        elif path == '/data/user/0/com.android.camera2/shared_prefs/com.android.camera2_preferences.xml':
            s.c.need(maximum == 131072 and not options, 'ONLY_ORIGINAL_READONLY_CAMERA_MODE')
        elif path == p.MEDIA_PROVIDER_APK:
            s.c.need(maximum == 16777216 and options == {'single_link': True}, 'EXACT_MEDIA_PROVIDER_APK')
        else:
            s.c.need(s.owned_video is not None and s.owned_video['is_pending'] == 0
                and path == s.owned_video['_data'] and maximum == 134217728 and options == {'single_link': True},
                'ONLY_THIS_ONCE_FINALIZED_OWNED_CLIP')
        raw, metadata = s.flow.view.target.read_file(path, maximum, **options)
        if wanted:
            s.c.need(s.c.sha(raw) == wanted[0]['sha256'] and len(raw) == wanted[0]['bytes']
                and metadata == wanted[0]['held_file'], 'SAME_APPROVED_VIDEO_APK_AND_HELD_FILE')
        elif path == p.MEDIA_PROVIDER_APK:
            s.c.need(len(raw) == p.MEDIA_PROVIDER_BYTES and s.c.sha(raw) == p.MEDIA_PROVIDER_SHA,
                'ORIGINAL_CURRENT_MEDIA_PROVIDER_BYTES')
        elif s.owned_video is not None and path == s.owned_video['_data']:
            s.c.need(len(raw) == s.owned_video['_size'], 'OWNED_CLIP_SIZE_DIFFERS_FROM_FINAL_MEDIASTORE')
        s.guard(); return raw, metadata

    def open_root(self, path, flags):
        s = self.s; s.guard()
        s.c.need(path in tuple('/data/' + root + '/0/' + package for root in ('user', 'user_de')
            for package in (CAMERA, PLAYER)) and flags == os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW,
            'ONLY_CURRENT_CAMERA_PLAYER_DATA_IDENTITY_HANDLES')
        return s.flow.view.target.open_root(path, flags | os.O_CLOEXEC)
