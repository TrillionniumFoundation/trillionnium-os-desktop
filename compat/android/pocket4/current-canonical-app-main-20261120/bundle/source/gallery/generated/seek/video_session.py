"""Current-Main adapter for the original owned silent-video business case.

The qualified rotation transport supplies bounded children, held seven-FD
leases, private raw image capture, the action-lock OFD and context retirement.
All package, task, media and UI admissions here are specific to the video case.
"""
import copy
import os
from pathlib import Path
import re
import types

GALLERY = 'com.android.gallery3d'
NATIVE = 'local.pocket4.actions.v2'
PACKAGE = 'org.droidloom.qa.media.r12.nc92c3d79180955ef'
GALLERY_SHA = '835fe119745324276457b4434fc39f25b633e752c822d2fc9be40eb4b2d45439'
NATIVE_SHA = 'a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058'
CALLERS = ['video_flow.py', 'video_seek.py', 'video_base.py', 'video_ui.py', 'video_fixture.py',
           'video_runtime.py', 'video_identity.py', 'video_diagnostics.py']


def expand(activity):
    return GALLERY + activity if activity.startswith('.') else activity


def make_session_class(shared, api):
    class Evidence(shared.Evidence):
        def read_regular(self, path, expected, maximum):
            s = self.s; package = s.components['video_fixture.py']
            s.c.need(Path(path) == package.APK and expected == package.APK_SHA and maximum == 1048576,
                'ONLY_ORIGINAL_VIDEO_HELPER_APK_HOST_READ')
            raw, ref = s.c.regular(path, maximum)
            s.c.need(ref['sha256'] == expected and len(raw) == 139532, 'ORIGINAL_VIDEO_FIXTURE_APK_CHANGED')
            return raw

    class TargetReads:
        def __init__(self, session):
            self.s = session

        def read_file(self, path, maximum, **options):
            s = self.s; s.guard(); package = s.components['video_fixture.py']; policy = s.components['video_policy.py']
            wanted = [(pkg, value) for pkg, value in s.apk_paths.items() if value == path]
            expected = None
            if wanted:
                s.c.need(len(wanted) == 1 and maximum == 16777216, 'ONE_CURRENT_VIDEO_INSTALLED_APK_PATH')
                expected = {GALLERY: GALLERY_SHA, NATIVE: NATIVE_SHA, PACKAGE: package.APK_SHA}[wanted[0][0]]
            elif path == policy.STAGE:
                s.c.need(maximum == 1048576 and s.case is not None and s.case.fixture.staged is not None,
                    'ONLY_THIS_CREATE_ONLY_STAGED_VIDEO_APK'); expected = package.APK_SHA
            else:
                s.c.need(path == '/data/user/0/' + PACKAGE + '/shared_prefs/owned-media-' + policy.RUN + '-video.xml'
                    and maximum == 16384 and s.case is not None and s.case.fixture.installed is not None,
                    'ONLY_ORIGINAL_OWNED_VIDEO_PRIVATE_STATE')
            s.c.need(options == {'single_link': True}, 'ORIGINAL_VIDEO_SINGLE_LINK_READ')
            raw, metadata = s.view.target.read_file(path, maximum, **options)
            if expected is not None:
                s.c.need(s.c.sha(raw) == expected, 'EXACT_ORIGINAL_OR_CURRENT_VIDEO_APK_BYTES')
            s.guard(); return raw, metadata

        def open_root(self, path, flags):
            s = self.s; s.guard()
            paths = {'/storage/emulated/0/DCIM', '/data/local/tmp'}
            paths |= {'/data/' + prefix + '/0/' + pkg for pkg in (GALLERY, NATIVE, PACKAGE)
                      for prefix in ('user', 'user_de')}
            s.c.need(path in paths and flags == os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW,
                'ONLY_ORIGINAL_VIDEO_EXACT_DIRECTORY_FD_SCOPE')
            return s.view.target.open_root(path, flags | os.O_CLOEXEC)

    class Session(shared.Session):
        def __init__(self, c, support, held, request, root, components, action_lock, image_capture,
                     source_guard, prior_ref, business_deadline):
            self.c = self.common = c; self.support = support; self.held = held
            self.request = request; self.root = Path(root); self.components = components
            self.action_lock = action_lock; self.image_capture = image_capture; self.image_custody_ref = image_capture.reference
            self.source_guard = source_guard; self.prior_ref = prior_ref
            self.business_deadline = self.deadline = business_deadline; self.phase = 'business'
            self.closed = False; self.view = self.peer = self.helper = self.case = None
            self.command_index = self.api_sequence = self.native_launches = 0
            self.records = []; self.intents = []; self.used_intents = set()
            self.active_api = self.ui_owner = self.last_focus = self.last_stacks = None
            self.last_native_dump = self.last_native_dump_ref = None
            self.claimed_tasks = {}; self.launch_receipts = {}
            self.apk_paths = {}; self.gallery_uid = None; self.image_identity = None
            self.pm_help_ref = None; self.pm_help_reading = False
            self.possible_effect = self.host_cancelled = self.host_retirement_unknown = False
            self.allowed_ui_packages = {GALLERY}
            self.source_paths = {key: value.__file__ for key, value in components.items()}
            self.journal = c.private_dir(self.root / 'commands', create=True)
            self.api_root = c.private_dir(self.root / 'api', create=True)
            self.phase_ref = c.write_new(self.root / 'phase-business.json', {
                'schema': 'pocket4-gallery-current-video-phase-v1', 'phase': self.phase,
                'baseline': request['baseline'], 'qualification': request['qualification'],
                'image_custody': self.image_custody_ref, 'owner_pid': os.getpid(),
                'deadline_monotonic': self.deadline, 'business_seconds': 600, 'cleanup_seconds': 120})
            try:
                def no_view_dispatch(*unused):
                    raise RuntimeError('ALL_VIDEO_COMMANDS_REQUIRE_CURRENT_TYPED_TRANSPORT')
                self.view = c.MainView(request['baseline'], request['qualification'], self.journal,
                                      no_view_dispatch, support_ref=c.SUPPORT_REF)
                self.observation = image_capture.bind(self.view)
                self.apk_paths[GALLERY] = self.observation['apks'][0]['path']; self.gallery_uid = self.observation['uid']
                self.baseline = self.view.baseline; self.environment = self.view.environment
                self.commands = self.view.commands; self.scope_module = self.view.scope
                identity = self.baseline.value['framework_epoch']['binding']['processes']['system_server']
                self.peer = held.HeldZygoteRoot(identity, self.deadline)
                self.epoch_sha256 = c.sha(c.canonical(self.baseline.value['framework_epoch']))
                self.target = TargetReads(self); self.tx = Evidence(self)
                self.policy = components['video_policy.py'].Policy(self)
                self.guard(); self.helper = api.OriginalAPIs(self)
            except BaseException:
                self.close(); raise

        def note_original_record(self, ref, value):
            caller = self.original_caller(CALLERS, skip=('record',))
            if caller == {'source': 'video_ui.py', 'function': 'focus'} and 'verified' in value:
                self.last_focus = copy.deepcopy(value)
            if caller == {'source': 'video_flow.py', 'function': 'native_controls'} and 'native' in value:
                self.last_native_dump = copy.deepcopy(value); self.last_native_dump_ref = ref
            if caller == {'source': 'video_ui.py', 'function': 'observe'}:
                focus = self.last_focus
                self.c.need(focus is not None and value.get('ok') is True
                    and value.get('outcome_unknown') is not True
                    and value['native'].get('ok') is True
                    and value['native'].get('accessibility_mode_restoration_verified') is True
                    and value['screenshot']['scope']['package'] == focus['package'] == GALLERY
                    and value['screenshot']['scope']['window_token'] == focus['window_token'],
                    'ORIGINAL_VIDEO_OBSERVATION_MUST_MATCH_CURRENT_MOVIE_FOCUS')
                self.last_native_dump = {'focus': copy.deepcopy(focus), 'native': copy.deepcopy(value['native'])}
                self.last_native_dump_ref = ref
            if value.get('automatic_retry') is False and (type(value.get('argv')) is list
                    or type(value.get('request')) is dict or value.get('package') == PACKAGE and 'identity' in value):
                self.intents.append({'ref': ref, 'value': copy.deepcopy(value), 'caller': caller, 'phase': self.phase_ref})

        def consume_intent(self, kind, wanted):
            matches = []
            for item in self.intents:
                if item['ref']['path'] in self.used_intents or item['phase'] != self.phase_ref:
                    continue
                value = item['value']; found = value.get('argv', value.get('request'))
                if kind == 'helper-uninstall' and value.get('package') == PACKAGE and 'identity' in value:
                    found = ['/system/bin/pm', 'uninstall', PACKAGE]
                if found == wanted:
                    matches.append(item)
            self.c.need(len(matches) == 1, 'ONE_CURRENT_ORIGINAL_VIDEO_DURABLE_INTENT:' + kind)
            item = matches[0]; self.c.read_ref(item['ref']); self.used_intents.add(item['ref']['path'])
            self.c.write_new(self.journal / ('once-%04d.json' % len(self.used_intents)), {
                'kind': kind, 'intent': item['ref'], 'original_caller': item['caller'],
                'phase': self.phase_ref, 'automatic_retry': False})
            return item

        def root_query(self, label, command, timeout):
            self.original_caller(['video_base.py'], {'query'})
            command = self.policy.root_sql(label, command, timeout)
            return self._transport('original-video-' + label, command[-5:], 14, root=True)

        def run_host(self, label, argv, timeout=20, pass_fds=()):
            self.original_caller(['video_ui.py'], {'launch'})
            f = self.case; wanted = list(self.c.NATIVE_PREFIX) + ['launch', GALLERY, '--component', GALLERY + '/.app.GalleryActivity', '--json']
            self.c.need(not pass_fds and self.phase == 'business' and self.active_api is None
                and label == 'contacts-launch' and timeout == 45 and argv == wanted and self.native_launches < 2
                and f.ui.launches == self.native_launches + 1 and f.ui.owned is None
                and f.pending == 'native-launch-' + str(self.native_launches) and self.last_stacks is not None
                and f.fixture.installed is not None and f.media is not None
                and f.media['sha256'] == self.components['video_policy.py'].VIDEO_SHA
                and f.native_launches == f.closed and len(f.closed) == self.native_launches,
                'ONCE_ORIGINAL_VIDEO_NATIVE_LAUNCH')
            roots, tasks = self.last_stacks
            self.c.need(not any(child['component'].split('/')[0] == GALLERY for row in roots.values() for child in row['children']),
                'PREEXISTING_GALLERY_TASK_IS_PRESERVED')
            self.consume_intent('launch', argv); self.native_launches += 1
            value = self._host('video-launch-' + str(self.native_launches), argv, timeout, True)
            native = self.c.parse(value['stdout'])
            match = re.fullmatch(r'object=(\d+) composer_display=(\d+) android_display=(\d+) task=(\d+)', native.get('launch', ''))
            self.c.need(native.get('ok') is True and native.get('state') == 'running'
                and native.get('host_pid') == self.tx.MAIN_HOST and native.get('outcome_unknown') is not True
                and match and match[3] == '0' and int(match[4]) not in roots and int(match[4]) not in tasks
                and int(match[4]) not in self.claimed_tasks, 'ACTUAL_NEW_VIDEO_TASK_FROM_NATIVE_RECEIPT')
            task = int(match[4]); self.launch_receipts[task] = self.c.write_new(self.root / ('launch-%d-scope.json' % self.native_launches), {
                'schema': 'pocket4-gallery-current-owned-video-launch-v1', 'baseline': self.request['baseline'],
                'qualification': self.request['qualification'], 'image_custody': self.image_custody_ref,
                'phase': self.phase_ref, 'native': native, 'task': task, 'prelaunch_tasks': sorted(tasks),
                'component': [GALLERY, GALLERY + '.app.GalleryActivity'], 'automatic_retry': False})
            return value

        def observe_owned_task(self):
            if self.case is None or self.case.ui.owned is None:
                return
            task, preserved = self.case.ui.owned
            if task in self.claimed_tasks:
                return
            self.c.need(task in self.launch_receipts and self.last_stacks is not None,
                'VIDEO_TASK_NEEDS_ACTUAL_CURRENT_NATIVE_LAUNCH')
            ref = self.launch_receipts[task]; claim = self.c.parse(self.c.read_ref(ref))
            roots, tasks = self.last_stacks
            self.c.need(claim['task'] == task and set(claim['prelaunch_tasks']) == preserved
                and task not in preserved and tasks == preserved | {task}
                and self.components['video_ui.py'].exact_leaf(roots, task), 'ACTUAL_NEW_VIDEO_LEAF_MATCHES_RECEIPT')
            self.claimed_tasks[task] = {**claim, 'source_ref': ref}

        def check_owned_task(self):
            f = self.case; self.c.need(f is not None and f.ui.owned is not None and self.last_stacks is not None,
                'CURRENT_VIDEO_TASK_SCOPE_REQUIRED')
            task, preserved = f.ui.owned; roots, tasks = self.last_stacks
            self.c.need(task in self.claimed_tasks and self.claimed_tasks[task]['prelaunch_tasks'] == sorted(preserved)
                and tasks == preserved | {task} and self.components['video_ui.py'].exact_leaf(roots, task),
                'CURRENT_EXACT_VIDEO_OWNED_LEAF_AND_PRESERVED_TASKS')
            return task

        def prior_cleanup(self):
            v = self.c.parse(self.c.read_ref(self.prior_ref))
            self.c.need(v['state'] == 'VIDEO_PLAY_PAUSE_RESUME_REOPEN_CLEANUP_VERIFIED'
                and v['run'] == 'c92c3d79180955ef' and v['temporary_package'] == PACKAGE
                and not v['cleanup']['errors'] and v['cleanup']['video_deleted'] is True
                and v['cleanup']['package_absent'] is True and v['cleanup']['staged_apk_removed'] is True
                and v['owned_directory_removed'] is True and v['original_media_preserved'] is True
                and v['pending_effect'] is None and v['close_pending'] is None
                and v['install_pending'] is False and v['uninstall_pending'] is False
                and v['owned_tasks'] == v['normal_closed_tasks'] and len(v['normal_closed_tasks']) == 2,
                'ORIGINAL_VIDEO_OWNED_EFFECTS_MUST_HAVE_COMPLETE_CLEANUP')
            return {'prior': self.prior_ref, 'prior_cleanup_complete': True,
                'historical_runtime_authority_transferred': False, 'fresh_live_namespace_and_helper_absence_still_required': True}

        def runtime_observer_session(self):
            self.original_caller(['video_flow.py'], {'setup'}); self.guard()
            return types.SimpleNamespace(target=self.view.target, held=self.held, guard=self.guard,
                current_deadline=lambda: self.deadline, gallery_uid=self.gallery_uid)

        def pm_no_replace_proof(self):
            self.original_caller(['video_fixture.py'], {'install'})
            self.c.need(self.pm_help_ref is None and not self.pm_help_reading, 'ONE_FRESH_VIDEO_PM_HELP_QUERY')
            before = self.guard(); self.pm_help_reading = True
            try:
                raw = self.android(['/system/bin/pm', 'help'], 15)
            finally:
                self.pm_help_reading = False
            lines = [line for line in raw.decode('utf-8', 'strict').splitlines() if re.match(r'\s*-R:', line)]
            self.c.need([line.strip() for line in lines] == ['-R: disallow replacement of existing application'],
                'CURRENT_VIDEO_CREATE_ONLY_PM_FLAG_REQUIRED')
            proof = {'state': 'ACTUAL_NO_REPLACE_FLAG_VERIFIED', 'no_replace_flag': '-R',
                'guard_before': before, 'guard_after': self.guard(), 'actual_flag_lines': lines,
                'ui_actions': 0, 'package_mutations': 0,
                'actual_help': self.c.write_new(self.root / 'pm-help.stdout', raw), 'historical_runtime_authority_transferred': False}
            self.c.need(proof['guard_before'] == proof['guard_after'], 'MAIN_CHANGED_DURING_VIDEO_PM_HELP')
            self.pm_help_ref = self.c.write_new(self.root / 'pm-create-only-proof.json', proof)
            return proof

        def verify_original_callback(self, kind, callback, previous):
            fn = getattr(callback, '__func__', None); owner = getattr(callback, '__self__', None)
            self.c.need(kind == 'foreground' and fn is not None and owner is not None and owner.s is self
                and fn.__code__.co_filename == self.source_paths['video_ui.py']
                and fn.__code__.co_name == 'helper_foreground' and self.ui_owner is None,
                'ONE_ORIGINAL_VIDEO_CURRENT_OWNED_FOREGROUND_CALLBACK')
            self.ui_owner = owner

        def begin_ui_api(self, name, request):
            c, f = self.c, self.case
            c.need(f is not None and self.ui_owner is f.ui and self.active_api is None
                and name in {'capture', 'ui', 'dispatch'}, 'BOUND_ORIGINAL_VIDEO_API_ONLY')
            caller = self.original_caller(['video_flow.py', 'video_ui.py', 'video_seek.py'])
            c.need(request.get('package', request.get('expected_package')) == GALLERY
                and request.get('display') == 0 and request.get('accessibility_mode') == 'none',
                'EXACT_ORIGINAL_VIDEO_API_PACKAGE_AND_DISPLAY')
            mutation = name == 'ui' and request.get('op') == 'click'
            if name == 'capture':
                c.need(caller == {'source': 'video_flow.py', 'function': 'capture_frame'}
                    and set(request) == {'package', 'display', 'accessibility_mode', 'window_token'},
                    'ONLY_ORIGINAL_OWNED_VIDEO_FRAME_CAPTURE')
            elif name == 'dispatch':
                c.need(caller == {'source': 'video_ui.py', 'function': 'observe'}
                    and request == {'op': 'observe', 'package': GALLERY, 'display': 0,
                        'accessibility_mode': 'none', 'window_token': request.get('window_token'), 'with_png': True},
                    'ONLY_ORIGINAL_VIDEO_OBSERVATION_DISPATCH')
            elif not mutation:
                c.need(caller == {'source': 'video_flow.py', 'function': 'native_controls'}
                    and request == {'op': 'dump', 'expected_package': GALLERY, 'display': 0, 'accessibility_mode': 'none'},
                    'ONLY_ORIGINAL_NATIVE_VIDEO_CONTROL_DUMP')
            else:
                c.need(self.phase == 'business' and 1 <= f.inputs <= 12 and f.pending in {'show-controls-native', 'pause', 'resume', 'seek-midpoint'}
                    and set(request) == {'op', 'expected_package', 'display', 'accessibility_mode', 'method', 'selector'},
                    'ONLY_ORIGINAL_BOUNDED_VIDEO_CONTROL_ACTIONS')
                expected_caller = ({'source': 'video_seek.py', 'function': 'seek_midpoint'} if f.pending == 'seek-midpoint'
                    else {'source': 'video_flow.py', 'function': 'ensure_controls'} if f.pending == 'show-controls-native'
                    else {'source': 'video_flow.py', 'function': 'click_control'})
                c.need(caller == expected_caller, 'EXACT_ORIGINAL_OR_REVIEWED_SEEK_ACTION_CALLER')
            self.guard(); f.ui.stacks('api-current-owned-video-task'); task = self.check_owned_task()
            actual = self.helper.foreground_callback(); focus = self.last_focus
            c.need(focus is not None and expand(focus['activity']) == GALLERY + '.app.MovieActivity'
                and expand(focus['focused_activity']) == GALLERY + '.app.MovieActivity', 'ONLY_ACTUAL_OWNED_MOVIE_WINDOW')
            self.api_sequence += 1
            context = {'schema': 'pocket4-gallery-current-video-api-context-v1', 'api': name,
                'request': copy.deepcopy(request), 'phase': self.phase_ref, 'owned_task': task,
                'claim': self.claimed_tasks[task]['source_ref'], 'caller': caller, 'api_sequence': self.api_sequence,
                'mutation_sent': False, 'native_returns': 0, 'automatic_retry': False}
            self.validate_ui_foreground(actual, context)
            if mutation:
                item = self.consume_intent('ui', request); context['original_intent'] = item['ref']
                self.validate_control_intent(request, item['value'], f.pending)
                context['observed_focus'] = copy.deepcopy(item['value']['focus'])
                self.validate_ui_foreground(actual, context)
            context['output'] = str(c.private_dir(self.api_root / ('api-%04d' % self.api_sequence), create=True))
            c.write_new(Path(context['output']) / 'context.json', context)
            self.active_api = context; return context

        def validate_control_intent(self, request, value, pending):
            c = self.c; c.need(self.last_native_dump is not None and self.last_native_dump_ref is not None,
                'ACTUAL_ORIGINAL_NATIVE_CONTROL_OBSERVATION_REQUIRED')
            c.read_ref(self.last_native_dump_ref)
            node = value.get('observed_video_view', value.get('observed_control'))
            c.need(type(node) is dict and node in self.last_native_dump['native'].get('nodes', [])
                and value['focus'] == self.last_native_dump['focus'] == self.last_focus
                and node.get('package') == GALLERY and node.get('visible') is True and node.get('enabled') is True,
                'VIDEO_CONTROL_MUST_BE_THE_ORIGINAL_ACTUAL_OBSERVED_NODE')
            if pending == 'seek-midpoint':
                f = self.case; seek = self.components['video_seek.py']
                c.need(request['method'] == 'mouse' and request['selector'] == {'package': GALLERY,
                    'class': 'android.view.View', 'desc': seek.DESCRIPTION, 'enabled': True, 'clickable': False}
                    and node.get('class') == 'android.view.View' and node.get('content-desc') == seek.DESCRIPTION
                    and node.get('clickable') is False and node.get('important_for_accessibility') is True
                    and f.seek_attempts == 1 and len(f.result['pixel_rounds']) == 1
                    and f.result['pixel_rounds'][0].get('normal_close_verified') is True
                    and len(f.native_launches) == 2 and f.native_launches[0] == f.closed[0]
                    and value.get('expected_seek_second') == 30,
                    'ONE_REVIEWED_MIDPOINT_SEEK_ON_ACTUAL_SECOND_ROUND_TIMEBAR')
            elif pending == 'show-controls-native':
                c.need(request['method'] == 'mouse' and request['selector'] == {'package': GALLERY,
                    'id': GALLERY + ':id/surface_view', 'class': 'android.widget.VideoView',
                    'enabled': True, 'focused': True, 'clickable': False}
                    and node.get('resource-id') == GALLERY + ':id/surface_view'
                    and node.get('class') == 'android.widget.VideoView' and node.get('focused') is True
                    and node.get('clickable') is False, 'ONLY_ORIGINAL_OBSERVED_VIDEO_SHOW_CONTROLS')
            else:
                labels = self.components['video_flow.py'].PAUSE_LABELS if pending == 'pause' else self.components['video_flow.py'].PLAY_LABELS
                c.need(request['method'] == 'accessibility' and node.get('content-desc') in labels
                    and node.get('class') == 'android.widget.ImageView' and node.get('clickable') is True
                    and request['selector'] == {'package': GALLERY, 'class': 'android.widget.ImageView',
                        'desc': node['content-desc'], 'clickable': True, 'enabled': True},
                    'ONLY_ORIGINAL_OBSERVED_PLAY_PAUSE_CONTROL')

        def validate_ui_foreground(self, value, context):
            f, focus = self.case, self.last_focus
            self.c.need(type(value) is dict and set(value) == {'package', 'activity', 'window_token'}
                and focus is not None and focus.get('verified') is True and f.ui.owned is not None
                and focus['task'] == f.ui.owned[0] == context['owned_task'] and focus['task'] in self.claimed_tasks
                and focus['package'] == GALLERY and expand(focus['activity']) == GALLERY + '.app.MovieActivity'
                and expand(focus['focused_activity']) == GALLERY + '.app.MovieActivity'
                and value == {k: focus[k] for k in ('package', 'activity', 'window_token')},
                'ACTUAL_ORIGINAL_CURRENT_OWNED_VIDEO_FOREGROUND')
            if not context['mutation_sent'] and 'observed_focus' in context:
                self.c.need(focus == context['observed_focus']
                    and value['window_token'] == context['observed_focus']['window_token'],
                    'OBSERVED_VIDEO_CONTROL_WINDOW_CHANGED_BEFORE_INPUT')
            if not context['mutation_sent'] and 'window_token' in context['request']:
                self.c.need(value['window_token'] == context['request']['window_token'], 'ORIGINAL_VIDEO_WINDOW_CHANGED')

        def validate_native_request(self, request, context, action_used):
            return self.components['video_policy.py'].native_request(self.c, context['request'], request, action_used)

        def admit_ui_android(self, argv, timeout, context, action_used):
            self.c.need(context is self.active_api, 'CURRENT_VIDEO_API_CONTEXT_REQUIRED')
            return self.components['video_policy.py'].backend_android(self.c, context['request'], argv, timeout, action_used)

        def caller_status(self, label):
            self.original_caller(['video_case.py'], {'execute'})
            self.c.need(label == 'gallery-video-final' and self.phase == 'final_cleanup', 'ONLY_ORIGINAL_VIDEO_FINAL_CALLER')
            value = self.c.parse(self._host(label, list(self.c.NATIVE_PREFIX) + ['status', '--json'], 10)['stdout'])
            self.c.need(value.get('ok') is True and value.get('state') == 'running'
                and value.get('host_pid') == self.tx.MAIN_HOST and 'cell u1000 ' in value.get('message', ''),
                'SAME_FINAL_MAIN_AND_VIDEO_CALLER_UID')
            return value

    return Session
