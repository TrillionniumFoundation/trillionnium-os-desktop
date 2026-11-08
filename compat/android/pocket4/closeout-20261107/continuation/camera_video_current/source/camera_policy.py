"""Literal reads, once-owned task transitions and the current video controls."""
import base64
import json
import re

CAMERA = 'com.android.camera2'
PLAYER = 'com.android.gallery3d'
VIDEO_URI = 'content://media/external_primary/video/media'

class Policy:
    native_timeout = 45
    def __init__(self, runtime):
        self.r, self.s, self.c = runtime, runtime.session, runtime.c
        self.remove_sent = False; self.view_sent = False

    def admit(self, argv, timeout, mutation, private):
        c, s = self.c, self.s
        c.need(type(argv) is list and argv and all(type(v) is str and v and '\0' not in v for v in argv)
            and type(timeout) in (int, float) and 5 < timeout <= 70 and type(mutation) is bool,
            'TYPED_CURRENT_CAMERA_COMMAND')
        if private:
            c.need(s.ui_dispatch_admission == (argv, timeout, mutation), 'CURRENT_VIDEO_BACKEND_CALL_ONLY')
            return
        if s.ordinary_admission == (argv, timeout, mutation): return
        c.need(mutation is False and self.command(argv, timeout) is False,
            'VIDEO_MUTATION_REQUIRES_CURRENT_ONCE_INTENT')

    def command(self, argv, timeout):
        c, s, r = self.c, self.s, self.r
        if argv == c.STACKS:
            c.need(timeout == 15, 'CURRENT_VIDEO_TASK_BOUND'); return False
        if argv == c.FOREGROUND:
            c.need(timeout == 6, 'CURRENT_VIDEO_WINDOW_BOUND'); return False
        packages = (CAMERA, PLAYER, 'local.pocket4.actions.v2')
        for package in packages:
            if argv in (['/system/bin/pm', 'path', package], ['/system/bin/dumpsys', 'package', package]):
                c.need(timeout == 20, 'CURRENT_VIDEO_IDENTITY_READ_BOUND'); return False
        reads = [(['/system/bin/date', '+%s'], 8),
            (['/system/bin/dumpsys', 'media.camera'], 15),
            (['/system/bin/dumpsys', 'media.audio_flinger'], 15),
            (['/system/bin/dumpsys', 'media.audio_policy'], 15),
            (['/system/bin/dumpsys', 'media.player'], 15),
            (['/system/bin/dumpsys', 'audio'], 15),
            (['/system/bin/dumpsys', 'activity', 'activities'], 15),
            (['/system/bin/dumpsys', 'activity', 'activities', PLAYER], 12),
            (['/system/bin/logcat', '-b', 'events', '-d', '-v', 'epoch', '-t', '2048'], 15)]
        for package in (CAMERA, PLAYER):
            uid = 10062 if package == CAMERA else 10064
            reads.extend([(['/system/bin/dumpsys', 'activity', 'exit-info', package], 15),
                (['/system/bin/logcat', '--uid=' + str(uid), '-b', 'crash', '-d', '-v', 'epoch', '-t', '512'], 15)])
        if (argv, timeout) in reads: return False
        if len(argv) == 5 and argv[:3] == ['/system/bin/settings', '--user', '0']:
            raise RuntimeError('NO_ABBREVIATED_AUDIO_SETTING_COMMAND')
        if len(argv) == 6 and argv[:5] == ['/system/bin/settings', '--user', '0', 'get', 'system']:
            c.need(timeout == 8 and argv[5] in {'volume_alarm', 'volume_ring', 'volume_notification',
                'volume_music', 'alarm_alert', 'notification_sound', 'ringtone', 'accelerometer_rotation',
                'user_rotation'}, 'ONLY_ORIGINAL_READONLY_SOUND_OR_ORIENTATION_VALUES'); return False
        prefix = ['/system/bin/content', 'query', '--user', '0', '--uri']
        if argv[:len(prefix)] == prefix:
            c.need(timeout == 15, 'CURRENT_VIDEO_MEDIA_QUERY_BOUND')
            if argv == prefix + [VIDEO_URI, '--projection', '_id']:
                return False
            c.need(s.video_id is not None and argv == prefix + [VIDEO_URI + '/' + str(s.video_id),
                '--projection', ':'.join(s.components['camera_video_media.py'].VIDEO_FIELDS)],
                'ONLY_THIS_NEWLY_OWNED_VIDEO_METADATA')
            return False
        if argv[:4] == ['/system/bin/cmd', 'package', 'resolve-activity', '--brief']:
            c.need(s.owned_video is not None and timeout == 15 and argv == s.movie_resolve_argv(),
                'ONLY_EXACT_FINALIZED_OWNED_VIDEO_RESOLUTION'); return False
        if argv[:2] == ['/system/bin/am', 'start-activity']:
            c.need(timeout == 35 and s.phase_name == 'business' and s.scope_index == 1
                and s.video_id is not None and s.owned_video is not None and not self.view_sent
                and s.driver.pending == 'movie-view' and s.driver.owned is not None
                and argv == s.movie_view_argv() and s.emitter_retired is True,
                'ONCE_OWNED_FINALIZED_URI_VIEW_AFTER_EMITTER_RETIREMENT')
            s.check_owned_task(); s.consume_intent('view', argv); self.view_sent = True; return True
        if argv[:4] == ['/system/bin/cmd', 'activity', 'stack', 'remove']:
            c.need(len(argv) == 5 and timeout == 15 and re.fullmatch('[1-9][0-9]*', argv[4]),
                'ONE_EXACT_VIDEO_TASK_REMOVE')
            selected = r.selected_task(); task = int(argv[4])
            c.need(task == selected['task'] and not self.remove_sent
                and s.driver.owned is None and s.driver.close_pending == {'task': task, 'automatic_retry': False}
                and selected['cleanup_allowed'] is True and selected['prelaunch_absent'] is True,
                'BURNED_AUTHORITY_FOR_ONLY_ACTUALLY_OWNED_VIDEO_TASK')
            roots, tasks = s.last_stacks
            c.need(tasks == set(selected['prelaunch_task_ids']) | {task}
                and r.tasks.exact_leaf(roots, task, r.scope['package']), 'CURRENT_VIDEO_TASK_AND_ALL_FOREIGN_TASKS')
            s.consume_intent('remove', argv)
            c.write_new(r.root / 'cleanup-attempted.json', {'scope': r.scope_ref,
                'phase_lease': r.phase_lease_ref, 'selected': selected, 'argv': argv,
                'automatic_retry': False, 'Binder_UID_cleanup_verified': False})
            self.remove_sent = True; return True
        raise RuntimeError('COMMAND_OUTSIDE_CURRENT_CAMERA_VIDEO_SCOPE')

    def observe(self, argv, raw):
        return None

def native_request(c, outer, request, action_used):
    package = outer.get('package', outer.get('expected_package'))
    c.need(package in (CAMERA, PLAYER) and type(request) is dict
        and request.get('expected_package') == package and request.get('display') == 0
        and request.get('accessibility_mode', 'none') == 'none', 'EXACT_CURRENT_NATIVE_VIDEO_SCOPE')
    if request.get('op') in ('meta', 'dump'):
        c.need(set(request) <= {'op', 'expected_package', 'display', 'accessibility_mode'}
            and {'op', 'expected_package', 'display'} <= set(request), 'ONLY_NATIVE_VIDEO_READ_FIELDS')
        return False
    c.need(package == CAMERA and not action_used and outer.get('op') == 'click'
        and outer.get('method') == 'accessibility', 'ONLY_CURRENT_ONCE_CAMERA_VIDEO_CONTROL')
    expected = {k: v for k, v in outer.items() if k in {'op', 'selector', 'display', 'accessibility_mode', 'method'}}
    expected['expected_package'] = package
    c.need(request == expected, 'UNCHANGED_VIDEO_NATIVE_PROJECTION'); return True

def backend_android(c, outer, argv, timeout, action_used):
    if argv == ['/system/bin/screencap', '-p']:
        c.need(timeout == 20, 'ORIGINAL_SCREENSHOT_BOUND'); return False, True
    if (len(argv) == 8 and argv[:6] == ['/system/bin/am', 'instrument', '-w', '-r', '-e', 'request']
        and argv[-1] == 'local.pocket4.actions.v2/.ActionRunner'):
        c.need(timeout == 70, 'CURRENT_NATIVE_ACTION_BOUND')
        raw = base64.b64decode(argv[6], validate=True); c.need(len(raw) <= 65536, 'BOUNDED_NATIVE_VIDEO_REQUEST')
        request = c.parse(raw)
        c.need(base64.b64encode(json.dumps(request, ensure_ascii=True, separators=(',', ':')).encode()).decode()
            == argv[6], 'UNCHANGED_NATIVE_REQUEST_ENCODING')
        return native_request(c, outer, request, action_used), False
    raise RuntimeError('NO_OTHER_VIDEO_BACKEND_COMMAND')
