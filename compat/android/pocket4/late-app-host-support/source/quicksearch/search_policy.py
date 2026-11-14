"""Only source-bound QSB observations, Unicode edits, one result tap and one Back."""
import base64
import json

class Policy:
    native_timeout = 45
    def __init__(self, runtime):
        self.r, self.s, self.c = runtime, runtime.session, runtime.c
        self.remove_sent = False

    def admit(self, argv, timeout, mutation, private):
        c, s = self.c, self.s
        c.need(type(argv) is list and argv and all(type(x) is str and x and '\0' not in x for x in argv)
            and type(timeout) in (int, float) and 5 < timeout <= 70 and type(mutation) is bool,
            'BOUNDED_TYPED_SEARCH_COMMAND')
        if private:
            c.need(s.ui_dispatch_admission == (argv, timeout, mutation), 'CURRENT_SEARCH_BACKEND_CALL_ONLY')
            return
        c.need(s.ordinary_admission == (argv, timeout, mutation) or
            mutation is False and self.command(argv, timeout) is False, 'TYPED_ONCE_SEARCH_ADMISSION')

    def command(self, argv, timeout):
        c, s = self.c, self.s
        if argv == c.STACKS:
            c.need(timeout == 15, 'EXACT_TASK_READ_TIMEOUT'); return False
        if argv == c.FOREGROUND:
            c.need(timeout == 6, 'EXACT_FOCUS_READ_TIMEOUT'); return False
        if argv == ['/system/bin/date', '+%s']:
            c.need(timeout == 8, 'EXACT_GUEST_CLOCK_READ'); return False
        profiles = (s.active['target_profile'], s.active['browser_profile'])
        for p in profiles:
            if argv == ['/system/bin/dumpsys', 'package', p['package']]:
                c.need(timeout == 20, 'PACKAGE_IDENTITY_READ_TIMEOUT'); return False
            if argv == ['/system/bin/dumpsys', 'activity', 'exit-info', p['package']]:
                c.need(timeout == 15, 'EXIT_OBSERVER_TIMEOUT'); return False
            if argv == ['/system/bin/logcat', '--uid=' + str(p['uid']), '-b', 'crash', '-d', '-v', 'epoch', '-t', '512']:
                c.need(timeout == 15, 'UID_CRASH_OBSERVER_TIMEOUT'); return False
        if argv == ['/system/bin/logcat', '-b', 'events', '-d', '-v', 'epoch', '-t', '2048']:
            c.need(timeout == 15, 'PACKAGE_ANR_EVENT_OBSERVER_TIMEOUT'); return False
        if argv == s.branch_log_command():
            c.need(timeout == 15, 'SOURCE_TAG_UID_BOUND_BRANCH_READ'); return False
        prefix = ['/system/bin/cmd', 'package', 'resolve-activity', '--brief', '--user', '0',
            '-a', 'android.intent.action.VIEW', '-d']
        if len(argv) == len(prefix) + 1 and argv[:-1] == prefix:
            c.need(timeout == 20 and s.driver is not None and argv[-1] == s.driver.resolve_url
                and s.driver.resolve_url is not None, 'EXACT_ACTUAL_SEARCH_URL_RESOLUTION')
            return False
        if argv[:4] == ['/system/bin/cmd', 'activity', 'stack', 'remove']:
            c.need(timeout == 15 and s.removal_admission is not None
                and argv == s.removal_admission['argv'] and not s.removal_admission['sent'],
                'ONE_EXACT_KNOWN_OWNED_TASK_REMOVE')
            # Ownership was independently established and checked from fresh stacks
            # by the narrow session method. Burn authority before the command.
            s.removal_admission['sent'] = True
            return True
        if argv == ['/system/bin/input', 'keyboard', '-d', '0', 'keyevent', 'KEYCODE_BACK']:
            d = s.driver
            c.need(timeout == 12 and s.phase_name == 'business' and d is not None
                and d.pending is not None and d.pending['kind'] == 'back'
                and d.back_inputs == 1 and not d.pending['sent'] and s.handoff is not None
                and s.ui_role == 'browser', 'ONE_CURRENT_BROWSER_RETURN_KEY')
            focus = d.focus('immediate-back-policy-focus')
            c.need(focus == d.pending['focus'], 'BROWSER_FOCUS_CHANGED_AT_BACK_DISPATCH')
            d.pending['sent'] = True
            return True
        raise RuntimeError('COMMAND_OUTSIDE_ORIGINAL_QUICKSEARCH_BUSINESS_SCOPE')

    def observe(self, argv, raw):
        return None

def native_request(c, outer, request, action_used):
    c.need(type(request) is dict and request.get('display') == 0 and request.get('accessibility_mode') == 'none'
        and request.get('expected_package') == outer.get('package'), 'EXACT_SEARCH_NATIVE_PACKAGE_AND_DISPLAY')
    if request.get('op') in ('meta', 'dump'):
        c.need(set(request) == {'op', 'expected_package', 'display', 'accessibility_mode'}, 'ONLY_NATIVE_READ_FIELDS')
        return False
    c.need(not action_used and outer.get('op') == 'set-text', 'ONE_ONLY_SEARCH_QUERY_NATIVE_EDIT')
    expected = {k: v for k, v in outer.items() if k in {'op', 'selector', 'value', 'display', 'accessibility_mode'}}
    expected['expected_package'] = outer['package']
    c.need(request == expected, 'UNCHANGED_NATIVE_QUERY_EDIT_PROJECTION')
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
    if outer.get('op') == 'snapshot-tap':
        point = outer.get('coords')
        c.need(type(point) is list and len(point) == 2 and all(type(x) is int for x in point)
            and outer.get('input_source') == 'touch' and not action_used and timeout == 30
            and argv == ['/system/bin/input', '-d', '0', 'tap', str(point[0]), str(point[1])],
            'ONE_SOURCE_BOUND_RESULT_SNAPSHOT_TOUCH')
        return True, False
    raise RuntimeError('NO_OTHER_SEARCH_BACKEND_ANDROID_COMMAND')
