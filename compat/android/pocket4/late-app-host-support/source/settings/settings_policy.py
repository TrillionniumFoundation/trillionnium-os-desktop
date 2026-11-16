"""Exact read-only Settings observations, original page routes and one UI roundtrip."""
import base64
import json

class Policy:
    native_timeout = 45
    def __init__(self, runtime):
        self.r, self.s, self.c = runtime, runtime.session, runtime.c

    def admit(self, argv, timeout, mutation, private):
        c, s = self.c, self.s
        c.need(type(argv) is list and argv and all(type(x) is str and x and '\0' not in x for x in argv)
            and type(timeout) in (int, float) and 5 < timeout <= 70 and type(mutation) is bool,
            'BOUNDED_TYPED_SETTINGS_COMMAND')
        if private:
            c.need(s.ui_dispatch_admission == (argv, timeout, mutation), 'CURRENT_SETTINGS_BACKEND_CALL_ONLY')
            return
        c.need(s.ordinary_admission == (argv, timeout, mutation) or
            mutation is False and self.command(argv, timeout) is False, 'TYPED_ONCE_SETTINGS_ADMISSION')

    def command(self, argv, timeout):
        c, s = self.c, self.s
        reads = [(c.STACKS, 15), (c.FOREGROUND, 6),
            (['/system/bin/date', '+%s'], 8),
            (['/system/bin/dumpsys', 'package', 'com.android.settings'], 20),
            (['/system/bin/dumpsys', 'activity', 'exit-info', 'com.android.settings'], 15),
            (['/system/bin/logcat', '-b', 'events', '-d', '-v', 'epoch', '-t', '2048'], 15),
            (['/system/bin/wm', 'user-rotation', '-d', '0'], 15)]
        for key in ('accelerometer_rotation', 'user_rotation', 'hide_rotation_lock_toggle_for_accessibility'):
            reads.append((['/system/bin/settings', '--user', '0', 'get', 'system', key], 15))
        for command, wanted in reads:
            if argv == command:
                c.need(timeout == wanted, 'EXACT_SETTINGS_READ_TIMEOUT'); return False
        for route in s.active['routes'].values():
            if argv == ['/system/bin/cmd', 'package', 'resolve-activity', '--brief', '--user', '0', '-n', route['component']]:
                c.need(timeout == 15, 'EXACT_ORIGINAL_SETTINGS_ROUTE_RESOLUTION'); return False
        if argv[:2] == ['/system/bin/am', 'start-activity']:
            d = s.driver; pending = d.pending if d is not None else None
            c.need(timeout == 35 and pending is not None and pending['kind'] == 'route'
                and not pending.get('sent') and pending['argv'] == argv
                and d.routes <= s.active['limits']['maximum_routes']
                and (s.phase_name == 'business' or pending.get('restoring') is True),
                'ONE_CURRENT_EXPLICIT_SETTINGS_PAGE_ROUTE')
            expected = ['/system/bin/am', 'start-activity', '-W', '--user', '0', '--display', '0',
                '--task', str(s.primary_task), '--activity-clear-top', '-n', pending['component']]
            c.need(argv == expected and pending['component'] in [r['component'] for r in s.active['routes'].values()],
                'ORIGINAL_SETTINGS_COMPONENT_IN_EXACT_NATIVE_OWNED_TASK')
            pending['sent'] = True
            return True
        if argv[:4] == ['/system/bin/cmd', 'activity', 'stack', 'remove']:
            c.need(timeout == 15 and s.removal_admission is not None
                and argv == s.removal_admission['argv'] and not s.removal_admission['sent'],
                'ONE_EXACT_KNOWN_OWNED_SETTINGS_TASK_REMOVE')
            s.removal_admission['sent'] = True
            return True
        raise RuntimeError('COMMAND_OUTSIDE_ORIGINAL_SETTINGS_SCOPE')

    def observe(self, argv, raw):
        return None

def native_request(c, outer, request, action_used):
    c.need(type(request) is dict and request.get('display') == 0 and request.get('accessibility_mode') == 'none'
        and request.get('expected_package') == outer.get('package') == 'com.android.settings',
        'EXACT_SETTINGS_NATIVE_PACKAGE_DISPLAY')
    if request.get('op') in ('meta', 'dump'):
        c.need(set(request) == {'op', 'expected_package', 'display', 'accessibility_mode'}, 'ONLY_SETTINGS_NATIVE_READ_FIELDS')
        return False
    c.need(not action_used and outer.get('op') == 'click' and outer.get('method') == 'accessibility',
        'ONE_ONLY_SOURCE_BOUND_AUTO_ROTATE_CLICK')
    expected = {k: v for k, v in outer.items() if k in {'op', 'selector', 'display', 'accessibility_mode', 'method'}}
    expected['expected_package'] = outer['package']
    c.need(request == expected, 'UNCHANGED_NATIVE_AUTO_ROTATE_CLICK_PROJECTION')
    return True

def backend_android(c, outer, argv, timeout, action_used):
    if argv == ['/system/bin/screencap', '-p']:
        c.need(timeout == 20, 'ORIGINAL_SCREENSHOT_TIMEOUT'); return False, True
    if len(argv) == 8 and argv[:6] == ['/system/bin/am', 'instrument', '-w', '-r', '-e', 'request'] \
            and argv[-1] == 'local.pocket4.actions.v2/.ActionRunner':
        c.need(timeout == 70, 'ORIGINAL_NATIVE_INSTRUMENTATION_TIMEOUT')
        raw = base64.b64decode(argv[6], validate=True); c.need(len(raw) <= 65536, 'BOUNDED_NATIVE_REQUEST')
        request = c.parse(raw)
        c.need(base64.b64encode(json.dumps(request, ensure_ascii=True, separators=(',', ':')).encode()).decode() == argv[6],
            'UNCHANGED_NATIVE_REQUEST_ENCODING')
        return native_request(c, outer, request, action_used), False
    raise RuntimeError('NO_OTHER_SETTINGS_BACKEND_ANDROID_COMMAND')
