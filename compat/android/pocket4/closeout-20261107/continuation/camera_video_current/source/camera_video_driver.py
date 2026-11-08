"""One new Camera clip, current CAMCORDER audio, exact-URI Gallery playback.

Three independent native launches own Camera, Gallery and Camera tasks. Every
input is claimed once. The record challenge emitter must exit and be reaped
before the input-only playback observer can start. No audio setting, permission,
provider, account or preexisting media file is written by this controller.
"""
import base64
import copy
import io
import os
from pathlib import Path
import re
import time

CAMERA = 'com.android.camera2'
PLAYER = 'com.android.gallery3d'
MOVIE = PLAYER + '.app.MovieActivity'
SOUND_KEYS = ('volume_alarm', 'volume_ring', 'volume_notification', 'volume_music',
    'alarm_alert', 'notification_sound', 'ringtone', 'accelerometer_rotation', 'user_rotation')

def expanded(package, name):
    return package + name if name.startswith('.') else name

class Driver:
    def __init__(self, session, result):
        self.s = session; self.c = session.c; self.result = result
        self.model = session.components['camera_photo_model.py']
        self.state = session.components['camera_video_state.py']
        self.media = session.components['camera_video_media.py']
        self.player = session.components['camera_player_binding.py']
        self.observations = session.components['camera_observations.py']
        self.owned = self.pending = self.close_pending = self.recording = self.decoder = None
        self.launches = []; self.closes = []; self.provider_windows = []; self.recording_samples = []
        self.ids_before = self.row = self.decoded = self.decode_ref = self.original_mode = None
        self.before = self.before_gallery = self.sound_before = self.diagnostics_before = None
        self.started = self.run_completed = self.cleanup_verified = self.host_unknown = False
        self.initial_tasks = None; self.record_started_ns = self.record_start_ms = self.record_stop_ms = None
        self.provider_cycle_start = None; self.provider_cursor = None; self.audio_input = None
        session.driver = session.case = session.trial = self

    def record(self, label, value):
        return self.s.record(label, value)

    def wait_until(self, deadline):
        self.s.guard()
        while time.monotonic() < deadline:
            self.c.need(time.monotonic() < self.s.deadline, 'CURRENT_VIDEO_PHASE_EXPIRED_DURING_READONLY_WAIT')
            if self.record_started_ns is not None and self.recording is not None and self.recording.state == 'RECORDING':
                self.c.need(time.monotonic_ns() - self.record_started_ns < 19000000000,
                    'FINITE_RECORDING_LEAVES_TIME_FOR_OWN_STOP')
            time.sleep(min(.1, max(0, deadline - time.monotonic())))
        self.s.guard()

    def stacks(self, label):
        raw = self.s.android(self.c.STACKS, 15)
        roots, tasks = self.s.last_stacks
        self.record(label, {'raw': raw.decode('utf-8', 'strict'), 'tasks': sorted(tasks),
            'scope': self.s.flow.scope_ref, 'phase': self.s.phase_ref})
        return roots, tasks

    def launch(self, index):
        s, c = self.s, self.c
        c.need(self.pending is self.close_pending is self.owned is None and index == len(self.launches),
            'ONCE_NEW_NORMAL_VIDEO_TASK')
        if index: s.switch_scope(index)
        roots, tasks = self.stacks('scope-%d-before-launch' % index)
        c.need(roots == s.baseline_roots and tasks == s.baseline_tasks, 'COMPLETE_ORIGINAL_TASKS_BEFORE_EVERY_LAUNCH')
        argv = c.NATIVE_PREFIX + ['launch', s.flow.scope['package'], '--component', s.flow.scope['component'], '--json']
        s.claim_intent('launch', argv); self.pending = 'launch-' + str(index)
        result = s.launch()
        c.need(result['rc'] == 0 and not result['timed_out'] and result['joined'], 'NATIVE_VIDEO_LAUNCH_OUTCOME_UNKNOWN')
        native = c.parse(result['stdout'])
        task = self.model.native_task(native, s.baseline.docs['final_baseline']['daemon_status']['host_pid'])
        claim = s.flow.selected_task()
        c.need(claim['task'] == task and claim['prelaunch_absent'] is True and claim['cleanup_allowed'] is True
            and task not in s.baseline_tasks and task not in self.launches, 'EXACT_NEW_DISTINCT_VIDEO_TASK_CLAIM')
        self.owned = task
        self.stacks('scope-%d-after-launch' % index); s.check_owned_task()
        self.launches.append(task); self.pending = None
        focus = s.owned_foreground()
        self.record('scope-%d-normal-launch' % index, {'task': task, 'scope': s.flow.scope_ref,
            'claim': s.task_claims[-1], 'native': native, 'focus': focus, 'automatic_retry': False})
        return task

    def close_task(self):
        s, c = self.s, self.c
        if self.owned is None: return
        c.need(self.close_pending is None, 'NO_REPEATED_OR_UNKNOWN_TASK_REMOVE')
        task = self.owned; self.stacks('scope-%d-before-close' % s.scope_index); s.check_owned_task()
        argv = ['/system/bin/cmd', 'activity', 'stack', 'remove', str(task)]
        s.claim_intent('remove', argv)
        self.close_pending = {'task': task, 'automatic_retry': False}
        # Independently known task authority is burned before transport. An
        # uncertain recording or VIEW is never cleared by this host operation.
        self.owned = None; s.android(argv, 15)
        deadline = min(time.monotonic() + 8, s.deadline)
        while time.monotonic() < deadline:
            roots, tasks = self.stacks('scope-%d-close-readback' % s.scope_index)
            c.need(tasks - {task} == s.baseline_tasks and {k: v for k, v in roots.items() if k != task} == s.baseline_roots,
                'ALL_OTHER_TASKS_UNCHANGED_DURING_OWNED_REMOVE')
            if task not in roots and task not in tasks:
                self.close_pending = None; self.closes.append(task)
                return self.record('scope-%d-normal-close' % s.scope_index,
                    {'task': task, 'scope': s.flow.scope_ref, 'actual_task_absent': True, 'automatic_retry': False})
            root = roots.get(task)
            shrinking = bool(root and task not in tasks and root['display'] == root['user'] == 0
                and root['freeform'] and root['children'] == [])
            c.need(s.flow.tasks.exact_leaf(roots, task, s.flow.scope['package']) or shrinking,
                'OWNED_TASK_TOPOLOGY_CHANGED_DURING_CLOSE')
            self.wait_until(min(time.monotonic() + .25, deadline))
        raise RuntimeError('CURRENT_VIDEO_TASK_REMOVE_UNKNOWN_NO_REPLAY')

    def mode(self, label):
        raw, metadata = self.s.target.read_file(self.media.PREFERENCES, 131072)
        value = self.media.mode(raw); ref = self.record(label, {**value, 'file': metadata})
        return value['module'], ref

    def ui(self, label, request):
        value = self.s.helper.dispatch(request)
        self.c.need(type(value) is dict, 'ACTUAL_VIDEO_API_OBJECT')
        stored = copy.deepcopy(value); png = stored.pop('screenshot_png_base64', None)
        if png is not None:
            data = base64.b64decode(png, validate=True)
            self.c.need(0 < len(data) <= 33554432, 'ORIGINAL_CURRENT_CAMERA_PNG_BOUND')
            stored['png'] = self.c.write_new(self.s.evidence_root / (label + '.png'), data)
        ref = self.record(label, stored)
        self.c.need(value.get('ok') is True and value.get('outcome_unknown') is not True,
            'VIDEO_UI_UNKNOWN_RETAINS_ONCE_AUTHORITY')
        return value, ref

    def observe_camera(self, label, *, pixels=False):
        self.s.owned_foreground(); before = time.monotonic_ns()
        request = {'op': 'observe' if pixels else 'dump', 'package': CAMERA, 'display': 0}
        if pixels: request.update(accessibility_mode='none', with_png=True)
        value, ref = self.ui(label, request); after = time.monotonic_ns()
        mode, mode_ref = self.mode(label + '-mode'); self.s.owned_foreground()
        if self.recording is not None:
            observed = self.recording.observe(value=value, focus_value=self.s.last_focus, mode=mode,
                monotonic_ns=after, observation_ref=ref)
            self.recording_samples.append({'before_ns': before, 'after_ns': after,
                'clock': observed['clock'], 'mode': mode, 'ref': ref, 'mode_ref': mode_ref})
        if pixels:
            scope = value['screenshot']['scope']
            self.c.need(scope['package'] == CAMERA and scope['window_token'] == self.s.last_focus['window_token'],
                'CURRENT_OWNED_CAMERA_PREVIEW_SCOPE')
        return value, ref

    def click(self, action):
        r = self.recording
        if action in ('start', 'stop'):
            control = self.state.one_control(r._last_native, ident=self.state.SHUTTER)
        elif action in ('mode_menu', 'restore_menu'):
            control = self.state.one_control(r._last_native, ident=self.state.MODE_TOGGLE)
        else:
            control = self.state.one_control(r._last_native,
                description=self.state.VIDEO_DESCRIPTION if action == 'select_video' else self.state.PHOTO_DESCRIPTION)
        request = {'op': 'click', 'package': CAMERA, 'display': 0, 'method': 'accessibility', 'selector': control['selector']}
        self.s.owned_foreground()
        r.claim(action=action, request=request, control=control, focus_value=self.s.last_focus,
            monotonic_ns=time.monotonic_ns())
        value, _ = self.ui('video-' + action + '-return', request); r.dispatch_return(value)
        self.c.need(len(r.attempted) <= self.s.active['limits']['maximum_ui_actions'], 'FINITE_ONCE_VIDEO_INPUTS')

    def await_recording_state(self, wanted, label):
        deadline = min(time.monotonic() + 5, self.s.deadline)
        for i in range(4):
            self.observe_camera(label + '-' + str(i))
            if self.recording.state == wanted and self.recording.pending is None: return
            self.c.need(time.monotonic() < deadline, 'BOUNDED_READONLY_VIDEO_EFFECT_READBACK')
            self.wait_until(min(time.monotonic() + .2, deadline))
        raise RuntimeError('ACTUAL_VIDEO_EFFECT_NOT_OBSERVED_NO_REPLAY')

    def sound(self, label):
        raw = self.s.android(['/system/bin/dumpsys', 'audio'], 15)
        streams = self.s.components['camera_sound_preservation.py'].audio_streams(raw.decode('utf-8', 'strict'))
        settings = {key: self.s.android(['/system/bin/settings', '--user', '0', 'get', 'system', key], 8)
            .decode('utf-8', 'strict').strip() for key in SOUND_KEYS}
        self.c.write_new(self.s.evidence_root / (label + '-audio-service.txt'), raw)
        value = {'streams': streams, 'settings': settings}
        self.record(label + '-sound-preservation', value); return value

    def diagnostics(self, label, package, uid):
        clock = self.s.android(['/system/bin/date', '+%s'], 8).decode().strip()
        self.c.need(clock.isdigit() and abs(time.time() - int(clock)) <= 3, 'ACTUAL_CAMERA_VIDEO_GUEST_CLOCK')
        value = {'package': package, 'uid': uid, 'guest_seconds': int(clock)}
        for key, argv in (
                ('exits', ['/system/bin/dumpsys', 'activity', 'exit-info', package]),
                ('events', ['/system/bin/logcat', '-b', 'events', '-d', '-v', 'epoch', '-t', '2048']),
                ('crash', ['/system/bin/logcat', '--uid=' + str(uid), '-b', 'crash', '-d', '-v', 'epoch', '-t', '512'])):
            raw = self.s.android(argv, 15)
            self.c.need(len(raw) <= 4194304, 'BOUNDED_CURRENT_VIDEO_DIAGNOSTIC')
            value[key] = raw.decode('utf-8', 'strict')
        self.model.exit_events(value['exits']); self.record(label + '-' + package.replace('.', '-'), value)
        return value

    def diagnostic_delta(self, before, after):
        package, uid, since = before['package'], before['uid'], before['guest_seconds']
        self.c.need((after['package'], after['uid']) == (package, uid), 'SAME_CURRENT_VIDEO_DIAGNOSTIC_SCOPE')
        added = self.model.exit_events(after['exits']) - self.model.exit_events(before['exits'])
        self.c.need(all(int(row[2]) == uid and row[4] == package for row in added), 'VIDEO_EXIT_INFO_ATTRIBUTION_DIFFERS')
        fatal = [r for r in added if int(r[3]) in (3, 4, 5, 6, 7)]; counts = {}
        for key, limit in (('crash', 512), ('events', 2048)):
            timed, found = [], []
            for line in after[key].splitlines():
                m = re.match(r'^\s*(\d+\.\d+)\s+', line)
                if m:
                    stamp = float(m[1]); timed.append(stamp)
                    if stamp >= since and (key == 'crash' or re.search(r'\bam_(?:crash|anr)\s*:', line) and package in line):
                        found.append(line)
            self.c.need(len(timed) < limit or min(timed) <= since, 'CURRENT_VIDEO_DIAGNOSTIC_WINDOW_TRUNCATED')
            counts[key] = len(found)
        self.c.need(not fatal and counts == {'crash': 0, 'events': 0}, 'NEW_CAMERA_OR_PLAYER_CRASH_ANR')
        return {'package': package, 'uid': uid, 'new_exit_events': len(added),
            'new_crash_or_anr_exits': len(fatal), 'new_crash_lines': counts, 'clear': True,
            'synchronous_window_observation': True, 'continuous_soak_claim': False}

    def gallery_identity(self, label):
        s, c = self.s, self.c
        raw = s.android(['/system/bin/dumpsys', 'package', PLAYER], 20).decode('utf-8', 'strict')
        blocks = re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)', raw, re.M | re.S)
        c.need(len(blocks) == 1 and re.findall(r'^  Package \[([^]]+)\]', blocks[0], re.M) == [PLAYER],
            'ONE_ACTUAL_INSTALLED_GALLERY_SECTION')
        block = blocks[0]
        def one(pattern):
            rows = re.findall(pattern, block, re.M); c.need(len(rows) == 1, 'EXACT_GALLERY_PACKAGE_FIELD'); return rows[0]
        user = one(r'^    User 0: (.*)$')
        c.need(all(re.search(r'\b' + k + '=' + v + r'\b', user) for k, v in
            (('installed', 'true'), ('hidden', 'false'), ('suspended', 'false'), ('enabled', '[01]'))), 'GALLERY_USER_STATE')
        uid, version = int(one(r'^    appId=(\d+)$')), int(one(r'^    versionCode=(\d+)\b'))
        c.need(uid == 10064 and version == 40030, 'ORIGINAL_CURRENT_GALLERY_IDENTITY')
        paths = s.android(['/system/bin/pm', 'path', PLAYER], 20).decode().splitlines()
        c.need(len(paths) == 1 and paths[0].startswith('package:/data/app/') and paths[0].endswith('/base.apk'),
            'ONE_INSTALLED_CURRENT_GALLERY_APK')
        apk, _ = s.target.read_file(paths[0][8:], 33554432, single_link=True)
        c.need(str(Path(paths[0][8:]).parent) == one(r'^    codePath=(.*)$'), 'ACTUAL_GALLERY_CODE_PATH')
        permissions = re.findall(r'^        (android\.permission\.[A-Z_]+): granted=(true|false), flags=\[(.*?)\]$', block, re.M)
        c.need(permissions and len({r[0] for r in permissions}) == len(permissions), 'COMPLETE_GALLERY_PERMISSION_ROWS')
        dirs = {}
        for key, path in (('ce', '/data/user/0/' + PLAYER), ('de', '/data/user_de/0/' + PLAYER)):
            fd = s.target.open_root(path, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW)
            try: info = os.fstat(fd)
            finally: os.close(fd)
            match = re.search(r'\b' + key + r'DataInode=(\d+)\b', user)
            c.need(match is not None and info.st_ino == int(match[1]) and info.st_uid == info.st_gid == uid,
                'ACTUAL_GALLERY_CE_DE_INODE_AND_OWNER')
            dirs[key] = {k: getattr(info, k) for k in ('st_dev', 'st_ino', 'st_uid', 'st_gid', 'st_mode')}
        value = {'uid': uid, 'version': version, 'directories': dirs, 'permissions': sorted(permissions),
            'first_install_time': one(r'^      firstInstallTime=(.*)$'), 'apk_sha256': c.sha(apk), 'apk_bytes': len(apk)}
        self.record(label + '-gallery-identity', value); return value

    def provider_state(self, label):
        argv = ['/usr/bin/systemctl', 'show', self.s.components['camera_profiles.py'].PROVIDER_UNIT,
            '--property=Id,ActiveState,SubState,MainPID,ControlGroup,InvocationID,FragmentPath,ExecStart']
        raw = self.s.host_observation(label, argv, 10)['stdout'].decode().splitlines()
        fields = [line.split('=', 1) for line in raw]
        self.c.need(fields and all(len(r) == 2 for r in fields) and len({r[0] for r in fields}) == len(fields),
            'EXACT_CURRENT_CAMERA_PROVIDER_STATE')
        value = dict(fields); unit = self.s.components['camera_profiles.py'].PROVIDER_UNIT
        self.c.need(set(value) == {'Id', 'ActiveState', 'SubState', 'MainPID', 'ControlGroup', 'InvocationID', 'FragmentPath', 'ExecStart'}
            and value['Id'] == unit and value['ActiveState'] == 'active' and value['SubState'] == 'running'
            and re.fullmatch('[1-9][0-9]+', value['MainPID']) and re.fullmatch('[0-9a-f]{32}', value['InvocationID'])
            and value['ControlGroup'] == '/system.slice/' + unit and value['FragmentPath'] == '/etc/systemd/system/' + unit
            and '/opt/pocket4-live-camera/manager.py' in value['ExecStart'], 'ACTUAL_CAMERA_PROVIDER_IDENTITY')
        return value

    def prepare_provider(self):
        s = self.s; s.provider = self.provider_state('provider-before')
        s.hardware = self.observations.physical_identity(); s.owner = self.observations.provider_owner()
        self.c.need(s.owner['pid'] == int(s.provider['MainPID']), 'CURRENT_PROVIDER_LOCK_OWNER')
        s.manager_identity = s.host.process(self.c, int(s.provider['MainPID']))
        p = s.components['camera_profiles.py']; raw, _ = s.target.read_file(p.MEDIA_PROVIDER_APK, 16777216, single_link=True)
        self.result.update(provider_before=s.provider, physical_device=s.hardware, provider_owner=s.owner,
            provider_manager=s.manager_identity, host_boot_id=s.host.boot(),
            actual_media_provider={'bytes': len(raw), 'sha256': self.c.sha(raw)})
        camera = s.android(['/system/bin/dumpsys', 'media.camera'], 15).decode('utf-8', 'strict')
        self.c.need(re.search(r'^Active Camera Clients:\s*\n\[\]\s*$', camera, re.M),
            'NO_PREEXISTING_CAMERA_CLIENT_TO_ADOPT_OR_DISTURB')
        self.record('camera-service-before', {'raw': camera})

    def journal(self, cursor=None):
        s = self.s
        argv = ['/usr/bin/journalctl', '-u', s.components['camera_profiles.py'].PROVIDER_UNIT, '--no-pager', '-o', 'json']
        argv += ['--after-cursor', cursor, '-n', '1024'] if cursor is not None else ['-n', '1']
        raw = s.host_observation('provider-journal', argv, 15)['stdout']; rows = self.model.journal_records(raw)
        if cursor is None:
            self.c.need(len(rows) == 1, 'ONE_CURRENT_PROVIDER_CURSOR'); return rows[0]['__CURSOR']
        return rows, raw

    def provider_begin(self):
        self.provider_cursor = self.journal(); self.provider_cycle_start = time.monotonic_ns() // 1000

    def provider_closed(self, label):
        rows, raw = self.journal(self.provider_cursor)
        events = self.observations.journal_events(raw, self.s.provider['InvocationID'],
            int(self.s.provider['MainPID']), self.s.host.boot())
        n = sum(r.get('event') == 'physical_camera_closed' for r in events)
        # Video mode changes may start a new provider connection. Preserve all
        # observed cycles and their exact identities instead of inventing one.
        self.c.need(1 <= n <= 8, 'FINITE_COMPLETE_CAMERA_PROVIDER_CYCLES')
        cycles = self.observations.physical_cycles(events, self.provider_cycle_start, time.monotonic_ns() // 1000, expected=n)
        connected, closed = [], []
        for i, event in enumerate(events):
            if event.get('event') != 'producer': continue
            message = event.get('message', '')
            if m := re.fullmatch(r'Pocket4LiveCamera source_connected session=(\d+) peer_uid=(\d+)', message):
                connected.append((int(m[1]), int(m[2]), i))
            if m := re.fullmatch(r'Pocket4LiveCamera source_closed session=(\d+) frames=(\d+)', message):
                closed.append((int(m[1]), int(m[2]), i))
        self.c.need(len(connected) == len(closed) == n and len({r[0] for r in connected}) == n,
            'ALL_ACTUAL_VIDEO_PRODUCER_SESSIONS_COMPLETE')
        for opened in connected:
            ending = [r for r in closed if r[0] == opened[0]]
            self.c.need(len(ending) == 1 and ending[0][1] >= 2 and ending[0][2] > opened[2],
                'ACTUAL_VIDEO_PRODUCER_FRAMES_AND_NORMAL_CLOSE')
        ref = self.record(label, {'actual_cycles': cycles, 'producer_connections': connected,
            'producer_closes': closed, 'cursor': self.provider_cursor, 'raw_journal': rows,
            'same_device': self.s.hardware, 'same_provider': self.s.provider, 'historical_frames_used': False})
        self.provider_windows.append(ref); return ref

    def ids(self, label):
        raw = self.s.android(['/system/bin/content', 'query', '--user', '0', '--uri', self.media.URI, '--projection', '_id'], 15)
        self.c.need(len(raw) <= 4194304, 'BOUNDED_EXISTING_VIDEO_ID_SET')
        ids = self.model.media_ids(raw); self.record(label, {'video_ids': sorted(ids)}); return ids

    def metadata(self, label):
        self.c.need(self.s.video_id is not None and self.record_start_ms is not None, 'ONLY_ONE_KNOWN_VIDEO_ID')
        raw = self.s.android(['/system/bin/content', 'query', '--user', '0', '--uri',
            self.media.URI + '/' + str(self.s.video_id), '--projection', ':'.join(self.media.VIDEO_FIELDS)], 15)
        ref = self.record(label, {'raw': raw.decode('utf-8', 'strict')})
        value = self.media.video_row(self.model.content_rows, raw, self.s.video_id,
            earliest_ms=self.record_start_ms, latest_ms=self.record_stop_ms)
        return value, ref

    def preserve_clip(self, label):
        self.s.guard(); data, metadata = self.s.target.read_file(self.row['_data'], self.media.MAX_CLIP_BYTES, single_link=True)
        self.c.need(len(data) == self.row['_size'] and self.c.sha(data) == self.row['file_sha256'],
            'SAME_NEW_OWNED_VIDEO_BYTES_AFTER_NORMAL_CLOSE_OR_REOPEN')
        self.s.guard(); return self.record(label, {'uri': self.row['uri'], 'bytes': len(data),
            'sha256': self.c.sha(data), 'actual_guest_file': metadata})

    def record_audio_window(self):
        s = self.s
        s.acoustic.request('emit_prepare')
        first = s.audio.snapshot('input', 'record-first')
        go = s.acoustic.request('emit_go')
        self.wait_until(go['actual_started']['monotonic_ns'] / 1e9 + 2.9)
        emitted = s.acoustic.request('emit_finish'); s.emitter_retired = True
        self.c.need(emitted['leader_reaped'] is True and emitted['exit_code'] == 0
            and emitted['closed']['nonce'] == s.active['audio_nonce'], 'ACTUAL_ONCE_RECORD_EMITTER_RETIRED')
        self.wait_until(first['finished_monotonic_ns'] / 1e9 + 5.1)
        second = s.audio.snapshot('input', 'record-second')
        _, self.audio_input = s.audio.window('input', first, second)
        self.observe_camera('recording-clock-advanced')
        return emitted

    def decode_window(self, emitted):
        start = next(a for a in self.recording.actions if a['action'] == 'start')
        low, high = start['claimed_monotonic_ns'], start['ack_monotonic_ns']
        for row in self.recording_samples:
            clock = row['clock']
            if row['mode'] != '1' or clock is None or clock['seconds'] is None: continue
            low = max(low, row['before_ns'] - (clock['seconds'] + 1) * 1000000000)
            high = min(high, row['after_ns'] - clock['seconds'] * 1000000000)
        self.c.need(low <= high, 'ACTUAL_RECORDING_START_BOUNDARIES_DISAGREE')
        signal_start = emitted['started']['monotonic_ns']
        window = [max(1500, (signal_start - high) // 1000000 + 1500 - 250),
            (signal_start - low + 999999) // 1000000 + 1500 + 500]
        baseline = min(1500, max(1280, window[0] - 250))
        self.record('measured-record-challenge-window', {'start_low_ns': low, 'start_high_ns': high,
            'emitter_started_ns': signal_start, 'tone_window_ms': window, 'baseline_end_ms': baseline,
            'native_start_ack': start['native_ack'], 'observations': self.recording_samples})
        return window, baseline

    def movie_focus(self):
        self.s.owned_foreground(); value = copy.deepcopy(self.s.last_focus)
        self.c.need(value['package'] == PLAYER and expanded(PLAYER, value['activity']) == MOVIE
            and expanded(PLAYER, value['focused_activity']) == MOVIE, 'OWNED_MOVIE_ACTIVITY_REQUIRED')
        return value

    def movie_route(self, label):
        focus = self.movie_focus()
        raw = self.s.android(['/system/bin/dumpsys', 'activity', 'activities', PLAYER], 12).decode('utf-8', 'strict')
        blocks = re.split(r'(?=^[ \t]*\* Hist[ \t]+#\d+: ActivityRecord\{)', raw, flags=re.M)
        pattern = r'^[ \t]*\* Hist[ \t]+#\d+: ActivityRecord\{[^\n]*\bu0 ' + re.escape(PLAYER) + r'/(?:\.app\.MovieActivity|com\.android\.gallery3d\.app\.MovieActivity) t' + str(self.owned) + r'\b'
        values = [b for b in blocks if re.search(pattern, b, re.M)]
        self.c.need(len(values) == 1, 'ONE_CURRENT_OWNED_MOVIE_ACTIVITY_RECORD')
        block = values[0]; token = re.search(r'ActivityRecord\{([0-9a-f]+)\b', block)
        intents = [line.strip() for line in block.splitlines() if re.match(r'\s*Intent \{', line)]
        self.c.need(token is not None and re.findall(r'\blaunchedFromUid=(\d+)\b', block) == ['1000']
            and len(intents) == 1 and re.search(r'\bact=android\.intent\.action\.VIEW\b', intents[0])
            and re.search(r'\bdat=' + re.escape(self.row['uri']) + r'(?:\s|\})', intents[0])
            and re.search(r'\btyp=' + re.escape(self.row['mime_type']) + r'(?:\s|\})', intents[0]), 'ACTUAL_MOVIE_INTENT_NOT_THIS_OWNED_FINALIZED_URI')
        self.c.need(self.movie_focus() == focus, 'MOVIE_ROUTE_WINDOW_CHANGED')
        value = {'focus': focus, 'activity_record_token': token[1], 'uri': self.row['uri'],
            'intent': intents[0], 'caller_uid': 1000, 'scope': self.s.flow.scope_ref, 'phase': self.s.phase_ref}
        return value, self.record(label, value)

    def movie_pixels(self, label):
        focus = self.movie_focus(); before = time.monotonic_ns()
        frame = self.s.helper.capture({'package': PLAYER, 'display': 0, 'accessibility_mode': 'none',
            'window_token': focus['window_token']})
        try:
            after = time.monotonic_ns(); self.c.need(self.movie_focus() == focus, 'MOVIE_PIXEL_WINDOW_CHANGED')
            meta = frame['meta']; image = frame['image']; scope = meta['scope']
            self.c.need(scope['package'] == PLAYER and scope['window_token'] == focus['window_token']
                and expanded(PLAYER, scope['activity']) == MOVIE and image.mode == 'RGB', 'CURRENT_OWNED_MOVIE_PIXELS')
            buffer = io.BytesIO(); image.save(buffer, format='PNG'); raw = buffer.getvalue(); buffer.close()
            self.c.need(len(raw) <= 33554432, 'ORIGINAL_MOVIE_PNG_BOUND')
            picture = self.c.write_new(self.s.evidence_root / (label + '.png'), raw)
            value = {'scope': self.s.flow.scope_ref, 'phase': self.s.phase_ref, 'actual_meta': meta,
                'focus': focus, 'started_monotonic_ns': before, 'finished_monotonic_ns': after,
                'png': picture, 'pixel_sha256': self.c.sha(image.tobytes()), 'size': list(image.size),
                'physical_presented_frame_count_claim': False}
            return value, self.record(label, value)
        finally: frame['image'].close()

    def player_sample(self, label, baseline, guest_pid):
        start = time.monotonic_ns(); raw = self.s.android(['/system/bin/dumpsys', 'media.player'], 15)
        end = time.monotonic_ns(); parsed = self.player.parse(raw)
        selected = self.player.select(parsed, baseline, guest_pid=guest_pid, width=self.row['width'], height=self.row['height'])
        rawref = self.c.write_new(self.s.evidence_root / (label + '-player.txt'), raw)
        return {'parsed': parsed, 'selected': selected, 'started_ns': start, 'finished_ns': end,
            'reference': self.record(label + '-player', {'raw': rawref, 'parsed': parsed, 'selected': selected})}

    def playback(self, emitted):
        s, c = self.s, self.c
        self.launch(1); self.preserve_clip('video-before-player-view')
        base_raw = s.android(['/system/bin/dumpsys', 'media.player'], 15)
        player_baseline = self.player.parse(base_raw)
        c.need(not any(r['uid'] == 10064 for r in player_baseline['clients']), 'NO_PREEXISTING_GALLERY_PLAYER')
        self.record('player-before-owned-view', {'raw': base_raw.decode('utf-8', 'strict'), 'parsed': player_baseline})
        resolved = s.android(s.movie_resolve_argv(), 15).decode().splitlines()
        c.need(resolved in ([PLAYER + '/.app.MovieActivity'], [PLAYER + '/' + MOVIE]), 'EXACT_CURRENT_OWNED_VIDEO_RESOLUTION')
        s.acoustic.request('listen_prepare'); go = s.acoustic.request('listen_go')
        listener_start = go['actual_started']['monotonic_ns']
        argv = s.movie_view_argv(); s.claim_intent('view', argv); self.pending = 'movie-view'
        start = time.monotonic_ns()
        request = self.record('movie-view-current-request', {'uri': self.row['uri'], 'argv': argv,
            'task': self.owned, 'started_monotonic_ns': start, 'automatic_retry': False})
        raw = s.android(argv, 35).decode('utf-8', 'strict'); finish = time.monotonic_ns()
        c.need(re.findall(r'^Status:\s*(\S+)', raw, re.M) == ['ok'] and 'Error:' not in raw and 'Exception' not in raw,
            'ACTUAL_MOVIE_VIEW_OUTCOME_UNKNOWN_NO_REPLAY')
        self.stacks('movie-after-view-task'); s.check_owned_task()
        route, route_ref = self.movie_route('movie-initial-owned-route')
        result = self.record('movie-view-current-result', {'uri': self.row['uri'], 'raw': raw,
            'task': self.owned, 'same_owned_task': True, 'actual_route': route_ref,
            'finished_monotonic_ns': finish, 'automatic_retry': False})
        self.pending = None
        first_audio = s.audio.snapshot('output', 'playback-first')
        guest_pid = first_audio['app']['namespace_pids'][-1]
        first_player = self.player_sample('playback-first', player_baseline, guest_pid)
        first_pixels, first_pixels_ref = self.movie_pixels('playback-first-pixels')
        self.wait_until(first_audio['finished_monotonic_ns'] / 1e9 + 5.1)
        second_audio = s.audio.snapshot('output', 'playback-second')
        second_player = self.player_sample('playback-second', player_baseline, guest_pid)
        second_pixels, second_pixels_ref = self.movie_pixels('playback-second-pixels')
        c.need(first_pixels['focus'] == second_pixels['focus'] == route['focus'], 'SAME_CURRENT_MOVIE_WINDOW_DURING_PLAYBACK')
        progress = self.player.advancing(first_player['parsed'], second_player['parsed'], player_baseline,
            guest_pid=guest_pid, width=self.row['width'], height=self.row['height'],
            elapsed_ns=second_player['finished_ns'] - first_player['finished_ns'])
        _, output_ref = s.audio.window('output', first_audio, second_audio)
        current_route, current_route_ref = self.movie_route('movie-final-owned-route')
        c.need(current_route == route, 'OWNED_MOVIE_ROUTE_CHANGED_DURING_CURRENT_PLAYBACK')
        offset = self.decoded['tone_offset_ms']
        low = (start - listener_start) // 1000000 + offset - 250
        high = (finish - listener_start) // 1000000 + offset + 750
        binding = {'schema': 'pocket4-current-camera-playback-acoustic-binding-v1',
            'plan': s.active['base_plan'], 'active_plan': s.active_ref, 'phase': s.phase_ref,
            'nonce': s.active['audio_nonce'], 'uri': self.row['uri'], 'clip_sha256': self.row['file_sha256'],
            'clip_decode': self.decode_ref, 'view_request': request, 'view_result': result,
            'listener_started_monotonic_ns': listener_start, 'tone_window_ms': [max(1500, low), high],
            'baseline_end_ms': min(1500, max(1280, low - 250)), 'emitter_final': emitted['reference'], 'automatic_retry': False}
        binding_ref = self.record('playback-acoustic-binding', binding)
        listening = s.acoustic.request('listen_finish', {'playback_binding': binding_ref})
        c.need(listening['leader_reaped'] is True and listening['exit_code'] == 0
            and listening['correlation']['matched'] is True and listening['closed']['output_streams_created'] == 0,
            'ACTUAL_INPUT_ONLY_CURRENT_CLIP_PHYSICAL_PLAYBACK')
        close_ref = self.close_task(); self.preserve_clip('video-after-player-close')
        value = {'nonce': s.active['audio_nonce'], 'epoch_sha256': s.active['framework_epoch_sha256'],
            'uri': self.row['uri'], 'file_sha256': self.row['file_sha256'], 'scope': self.recording.scope,
            'phase': self.recording.phase, 'actual_player_scope': s.flow.scope_ref, 'actual_player_phase': s.phase_ref,
            'actual_owned_uri_intent': True, 'actual_video_decoder_outputs_advanced': True,
            'two_current_foreground_pixel_observations': True, 'physical_presented_frame_claim': False,
            'actual_Android_output_session_bound': True, 'physical_playback_nonce_match': True,
            'owned_player_closed': True, 'foreign_tasks_unchanged': True, 'outcome_unknown': False,
            'normal_gallery_launch': s.task_claims[1], 'route': route_ref, 'final_route': current_route_ref,
            'video_decoder_progress': progress, 'pixels': [first_pixels_ref, second_pixels_ref],
            'output_runtime': output_ref, 'acoustic': listening['reference'], 'actual_close': close_ref,
            'filmstrip_menu_covered': False, 'host_emission_during_playback': False}
        return value, self.record('current-owned-video-playback', value)

    def run(self):
        s, c = self.s, self.c
        self.result['guard_before'] = s.guard(); self.before = s.snapshot('acceptance-before')
        c.need(all(self.before['identity']['runtime_permissions'][p]['granted'] is True for p in
            ('android.permission.CAMERA', 'android.permission.RECORD_AUDIO')), 'EXISTING_CAMERA_AND_MIC_PERMISSIONS_REQUIRED')
        self.before_gallery = self.gallery_identity('before'); self.sound_before = self.sound('before')
        self.diagnostics_before = {p: self.diagnostics('diagnostics-before', p, uid)
            for p, uid in ((CAMERA, 10062), (PLAYER, 10064))}
        self.prepare_provider(); s.audio.preflight(); self.ids_before = self.ids('video-ids-before')
        self.initial_tasks = self.stacks('original-tasks-before')[1]; self.started = True
        self.provider_begin(); task = self.launch(0)
        self.recording = self.state.Recording(nonce=s.active['audio_nonce'], scope=s.flow.scope_ref,
            phase=s.phase_ref, epoch_sha256=s.active['framework_epoch_sha256'], task=task, emit=self.record)
        self.observe_camera('camera-initial-preview', pixels=True); self.original_mode = self.recording.initial_mode
        if self.original_mode == '0':
            self.click('mode_menu'); self.observe_camera('video-mode-menu'); self.click('select_video')
            self.await_recording_state('VIDEO_READY', 'video-mode-selected')
        self.record_start_ms = time.time_ns() // 1000000; self.record_started_ns = time.monotonic_ns()
        self.click('start'); self.await_recording_state('RECORDING', 'recording-started')
        emitted = self.record_audio_window()
        self.wait_until(self.record_started_ns / 1e9 + 13)
        self.observe_camera('recording-before-stop'); self.click('stop')
        self.record_stop_ms = time.time_ns() // 1000000
        self.await_recording_state('STOPPED_UNSAVED', 'recording-stopped')
        deadline = min(time.monotonic() + 15, s.deadline); row = row_ref = None
        for index in range(8):
            new_id = self.media.one_new_video(self.ids_before, self.ids('video-ids-after-stop-' + str(index)))
            if new_id is not None:
                c.need(s.video_id in (None, new_id), 'ONCE_NEW_MEDIASTORE_VIDEO_ID'); s.video_id = new_id
                row, row_ref = self.metadata('owned-video-row-' + str(index))
                if row is not None: break
            c.need(time.monotonic() < deadline, 'FINITE_FINALIZED_OWNED_VIDEO_WAIT')
            self.wait_until(min(time.monotonic() + .4, deadline))
        c.need(row is not None, 'NEW_VIDEO_ROW_MUST_FINALIZE_BEFORE_READ_OR_PLAY')
        s.owned_video = row; data, metadata = s.target.read_file(row['_data'], self.media.MAX_CLIP_BYTES, single_link=True)
        row['file_sha256'] = c.sha(data); self.row = s.owned_video = row
        clip_ref = c.write_new(s.evidence_root / 'owned-camera-video.mp4', data, 0o400); del data
        self.record('owned-video-held-copy', {'row': row, 'clip': clip_ref, 'actual_guest_file': metadata})
        window, baseline = self.decode_window(emitted)
        self.decoder = s.components['camera_decode.py'].Decoder(s, clip_ref, row)
        try: self.decoded, self.decode_ref = self.decoder.run(tone_window_ms=window, baseline_end_ms=baseline)
        finally: self.decoder.close()
        self.recording.saved(row, row_ref, self.decoded, self.decode_ref)
        if self.original_mode == '0':
            self.observe_camera('before-original-mode-restore'); self.click('restore_menu')
            self.observe_camera('original-mode-menu'); self.click('restore_photo')
            self.await_recording_state('MODE_RESTORED', 'original-mode-restored')
        self.close_task(); self.provider_closed('recording-provider-closed'); self.preserve_clip('video-after-camera-close')
        playback, playback_ref = self.playback(emitted)
        audio = {'nonce': s.active['audio_nonce'], 'epoch_sha256': s.active['framework_epoch_sha256'],
            'uri': row['uri'], 'file_sha256': row['file_sha256'], 'scope': self.recording.scope, 'phase': self.recording.phase,
            'outcome_unknown': False, 'decoded_own_audio_nonce_match': True, 'CAMCORDER_uid': 10062,
            'actual_HAL_input_session_bound': True, 'actual_physical_source_bound': True,
            'baseline_negative_passed': self.decoded['correlation']['baseline_negative_passed'],
            'decoy_negative_passed': self.decoded['correlation']['decoy_negative_passed'],
            'input_runtime': self.audio_input, 'full_clip_decode': self.decode_ref, 'emitter': emitted['reference']}
        audio_ref = self.record('current-owned-video-audio', audio)
        self.recording.audio_and_playback(audio_ref=audio_ref, audio=audio, playback_ref=playback_ref, playback=playback)
        self.provider_begin(); self.launch(2)
        # Reopening has a new task/scope. It has no input authority from the
        # first Recording state machine, which remains bound to scope zero.
        first_recording, self.recording = self.recording, None
        try:
            value, reopened = self.observe_camera('camera-reopened-preview', pixels=True)
            self.state.native_nodes(value)
            c.need(self.state.recording_clock(value) is None, 'NO_RECORDING_AFTER_NORMAL_REOPEN')
            final_mode, _ = self.mode('camera-reopened-mode')
            c.need(final_mode == self.original_mode, 'ORIGINAL_CAMERA_MODE_PRESERVED_AFTER_REOPEN')
            self.preserve_clip('video-after-camera-reopen'); self.close_task()
        finally: self.recording = first_recording
        self.provider_closed('reopened-provider-closed')
        c.need(self.ids('video-ids-final') == self.ids_before | {row['_id']} and self.stacks('original-tasks-final')[1] == self.initial_tasks,
            'EXACT_ONE_NEW_VIDEO_AND_UNCHANGED_FOREIGN_TASKS')
        c.need(s.snapshot('acceptance-after') == self.before and self.gallery_identity('after') == self.before_gallery,
            'CURRENT_CAMERA_GALLERY_APK_PERMISSIONS_AND_DATA_IDENTITY_PRESERVED')
        c.need(self.sound('after') == self.sound_before and self.provider_state('provider-after') == s.provider,
            'EXISTING_SOUND_ORIENTATION_AND_PROVIDER_UNCHANGED')
        final_audio = s.audio.verify_final()
        diagnostics = {p: self.diagnostic_delta(self.diagnostics_before[p], self.diagnostics('diagnostics-after', p, uid))
            for p, uid in ((CAMERA, 10062), (PLAYER, 10064))}
        c.need(self.launches == self.closes and len(self.launches) == len(set(self.launches)) == 3,
            'THREE_DISTINCT_NATIVE_LAUNCHES_AND_EXACT_NORMAL_CLOSES')
        terminal = self.recording.terminal(final_mode=final_mode, task_closed=True, preserved_state=True,
            host_retired=set(s.acoustic.results) == set(s.components['camera_audio_channel.py'].ORDER))
        c.need(terminal['camera_video_verified'], 'COMPLETE_CURRENT_CAMERA_VIDEO_STATE_MACHINE')
        self.result.update(recording=terminal, full_decode=self.decode_ref, current_audio=audio_ref,
            current_playback=playback_ref, audio_final=final_audio, reopened_preview=reopened,
            native_tasks=list(self.launches), normal_closes=list(self.closes), provider_windows=self.provider_windows,
            current_diagnostic_windows=diagnostics,
            new_media_row=row, owned_clip_retained=True, existing_media_removed=False,
            filmstrip_menu_covered=False, audio_settings_writes=0, permission_writes=0,
            synchronous_observations_only=True, continuous_sampling_or_soak_claim=False)
        self.run_completed = True

    def finish(self):
        # A normal removal can retire an independently owned task. It never
        # retries a start, stop, VIEW or unknown previous task removal.
        if self.owned is not None: self.close_task()
        if self.initial_tasks is not None:
            roots, tasks = self.stacks('final-cleanup-taskset')
            self.c.need(roots == self.s.baseline_roots and tasks == self.initial_tasks, 'FINAL_FOREIGN_TASKS_UNCHANGED')
        if self.ids_before is not None and self.pending is None and (self.recording is None or self.recording.pending is None):
            expected = self.ids_before | ({self.row['_id']} if self.row else set())
            self.c.need(self.ids('final-cleanup-video-ids') == expected, 'FINAL_MEDIA_DELTA_NOT_THIS_KNOWN_VIDEO')
        self.s.caller_status('camera-video-final'); self.result['guard_after'] = self.s.guard()
        self.c.need(self.result['guard_after'] == self.result['guard_before'], 'SAME_CURRENT_MAIN_AFTER_CAMERA_VIDEO')
        self.cleanup_verified = bool(self.owned is None and self.pending is None and self.close_pending is None
            and (self.recording is None or self.recording.pending is None) and not self.host_unknown
            and self.s.acoustic.pending is None)

    def close_local(self):
        if self.decoder is not None: self.decoder.close()
