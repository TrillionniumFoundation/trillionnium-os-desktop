"""Literal Camera photo reads and one durably claimed shutter/owned removal."""
import base64
import json
import re

PACKAGE = 'com.android.camera2'
IMAGE_URI = 'content://media/external/images/media'


class Policy:
    native_timeout = 45

    def __init__(self, runtime):
        self.r = runtime; self.s = runtime.session; self.c = runtime.c
        self.remove_sent = False

    def admit(self, argv, timeout, mutation, private):
        c, s = self.c, self.s
        c.need(type(argv) is list and argv and all(type(v) is str and v and '\0' not in v for v in argv)
            and type(timeout) in (int, float) and 5 < timeout <= 70 and type(mutation) is bool,
            'EXPLICIT_TYPED_CAMERA_COMMAND')
        if private:
            c.need(s.ui_dispatch_admission == (argv, timeout, mutation), 'ONLY_CURRENT_CAMERA_BACKEND_CALL')
            return
        if s.ordinary_admission == (argv, timeout, mutation):
            return
        c.need(mutation is False and self.command(argv, timeout) is False,
               'CAMERA_MUTATION_REQUIRES_ORIGINAL_ONCE_INTENT')

    def command(self, argv, timeout):
        c, s, r = self.c, self.s, self.r
        if argv == c.STACKS:
            c.need(timeout == 15, 'ORIGINAL_CAMERA_TASK_READ_BOUND'); return False
        if argv == c.FOREGROUND:
            c.need(timeout == 6, 'FRESH_CAMERA_WINDOW_READ_BOUND'); return False
        if argv == ['/system/bin/pm', 'path', PACKAGE]:
            c.need(timeout == 20, 'ORIGINAL_CURRENT_CAMERA_APK_PATH_READ'); return False
        if argv == ['/system/bin/dumpsys', 'package', PACKAGE]:
            c.need(timeout == 20, 'ORIGINAL_CURRENT_CAMERA_IDENTITY_READ'); return False
        diagnostics = [(['/system/bin/date', '+%s'], 8),
            (['/system/bin/dumpsys', 'activity', 'exit-info', PACKAGE], 15),
            (['/system/bin/logcat', '-b', 'events', '-d', '-v', 'epoch', '-t', '2048'], 15),
            (['/system/bin/logcat', '--uid=10062', '-b', 'crash', '-d', '-v', 'epoch', '-t', '512'], 15),
            (['/system/bin/dumpsys', 'media.camera'], 15)]
        if (argv, timeout) in diagnostics:
            return False
        prefix = ['/system/bin/content', 'query', '--user', '0', '--uri']
        if argv[:len(prefix)] == prefix:
            c.need(timeout == 15, 'ORIGINAL_CAMERA_MEDIA_QUERY_BOUND')
            if argv == prefix + [IMAGE_URI, '--projection', '_id']:
                return False
            c.need(s.photo_id is not None and argv == prefix + [IMAGE_URI + '/' + str(s.photo_id),
                '--projection', ':'.join(s.components['camera_photo_model.py'].MEDIA_FIELDS)],
                'ONLY_THE_ONCE_NEW_CAMERA_MEDIASTORE_ROW')
            return False
        if argv[:4] == ['/system/bin/cmd', 'activity', 'stack', 'remove']:
            c.need(len(argv) == 5 and timeout == 15 and re.fullmatch('[1-9][0-9]*', argv[4]),
                   'ONE_EXACT_CAMERA_TASK_REMOVE')
            f = s.trial; selected = r.selected_task(); task = selected['task']
            c.need(int(argv[4]) == task and not self.remove_sent and f is not None
                and f.owned is None and f.remove_calls == s.native_launches
                and ('open' if s.native_launches == 1 else 'reopen') + '-remove' in f.pending_effects
                and f.pending_effects <= {'shutter', ('open' if s.native_launches == 1 else 'reopen') + '-remove'}
                and selected['cleanup_allowed'] is True and selected['prelaunch_absent'] is True
                and s.last_stacks is not None, 'ORIGINAL_BURNED_ONCE_AUTHORITY_FOR_THIS_ACTUAL_TASK')
            roots, tasks = s.last_stacks
            c.need(tasks == set(selected['prelaunch_task_ids']) | {task}
                and r.tasks.exact_leaf(roots, task, PACKAGE), 'FRESH_EXACT_CAMERA_LEAF_BEFORE_REMOVE')
            s.consume_original_intent('remove', argv)
            c.write_new(r.root / 'cleanup-attempted.json', {'scope': r.scope_ref,
                'phase_lease': r.phase_lease_ref, 'selected': selected, 'argv': argv,
                'automatic_retry': False, 'Binder_UID_cleanup_verified': False})
            self.remove_sent = True
            return True
        raise RuntimeError('COMMAND_OUTSIDE_ORIGINAL_CAMERA_PHOTO_CASE')

    def observe(self, argv, raw):
        s = self.s; m = s.components['camera_photo_model.py']
        prefix = ['/system/bin/content', 'query', '--user', '0', '--uri']
        if argv == prefix + [IMAGE_URI, '--projection', '_id']:
            ids = m.media_ids(raw)
            if s.image_ids_before is None:
                self.c.need(s.trial is not None and s.trial.shutter_calls == 0,
                            'REAL_PRE_SHUTTER_MEDIASET_FIRST')
                s.image_ids_before = set(ids)
            else:
                new = m.new_image_id(s.image_ids_before, ids)
                if new is not None:
                    self.c.need(s.trial.shutter_calls == 1 and not s.trial.pending_effects
                        and s.case.shutter_seconds is not None and s.photo_id in (None, new),
                        'NEW_PHOTO_ONLY_AFTER_ONE_KNOWN_SHUTTER')
                    s.photo_id = new
        elif argv[:len(prefix)] == prefix and s.photo_id is not None:
            row = m.image_record(raw, s.photo_id, s.case.shutter_seconds)
            if row is not None:
                self.c.need(s.owned_photo is None or row == s.owned_photo,
                            'ONCE_OWNED_PHOTO_ROW_MUST_REMAIN_IDENTICAL')
                s.owned_photo = row


def native_request(c, outer, request, action_used):
    c.need(type(request) is dict and request.get('display') == 0
        and request.get('accessibility_mode', 'none') == 'none'
        and request.get('expected_package') == PACKAGE == outer.get('package', outer.get('expected_package')),
        'EXACT_CAMERA_NATIVE_PACKAGE_DISPLAY_AND_UNCHANGED_ACCESSIBILITY')
    if request.get('op') in ('meta', 'dump'):
        c.need(set(request) <= {'op', 'expected_package', 'display', 'accessibility_mode'}
            and {'op', 'expected_package', 'display'} <= set(request), 'ONLY_NATIVE_CAMERA_READ_FIELDS')
        return False
    c.need(not action_used and outer.get('op') == 'click' and outer.get('method') == 'accessibility'
        and outer.get('selector') == {'id': PACKAGE + ':id/shutter_button', 'enabled': True, 'clickable': True},
        'ONLY_ORIGINAL_ONCE_READY_CAMERA_SHUTTER')
    expected = {key: value for key, value in outer.items()
                if key in {'op', 'selector', 'display', 'accessibility_mode', 'method'}}
    expected['expected_package'] = PACKAGE
    c.need(request == expected, 'UNCHANGED_CAMERA_NATIVE_BACKEND_PROJECTION')
    return True


def backend_android(c, outer, argv, timeout, action_used):
    if argv == ['/system/bin/screencap', '-p']:
        c.need(timeout == 20, 'ORIGINAL_CAMERA_SCREENSHOT_BOUND'); return False, True
    if (len(argv) == 8 and argv[:6] == ['/system/bin/am', 'instrument', '-w', '-r', '-e', 'request']
            and argv[-1] == 'local.pocket4.actions.v2/.ActionRunner'):
        c.need(timeout == 70, 'EXACT_EXISTING_NATIVE_ACTION_TIMEOUT')
        raw = base64.b64decode(argv[6], validate=True); c.need(len(raw) <= 65536, 'BOUNDED_CAMERA_NATIVE_REQUEST')
        request = c.parse(raw)
        c.need(base64.b64encode(json.dumps(request, ensure_ascii=True, separators=(',', ':')).encode()).decode() == argv[6],
               'UNCHANGED_CAMERA_NATIVE_REQUEST_ENCODING')
        return native_request(c, outer, request, action_used), False
    raise RuntimeError('NO_OTHER_CAMERA_PHOTO_BACKEND_COMMAND')
