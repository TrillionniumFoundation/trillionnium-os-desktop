"""Exact original QA/Editor reads and once-owned input/removal admissions."""
import base64
import json
import re

class Policy:
    native_timeout = 45
    def __init__(self, runtime):
        self.r = runtime; self.s = runtime.session; self.c = runtime.c
        self.remove_sent = False; self.nonce_sent = False

    def admit(self, argv, timeout, mutation, private):
        c, s = self.c, self.s
        c.need(type(argv) is list and argv and all(type(x) is str and x and '\0' not in x for x in argv)
            and type(timeout) in (int, float) and 5 < timeout <= 70 and type(mutation) is bool,
            'ORIGINAL_FIXTURE_TYPED_COMMAND_REQUIRED')
        if private:
            c.need(s.ui_dispatch_admission == (argv, timeout, mutation), 'ONLY_CURRENT_TYPED_BACKEND_CALL')
            return
        if s.ordinary_admission == (argv, timeout, mutation):
            return
        c.need(mutation is False, 'MUTATIONS_REQUIRE_ONCE_INTENT_ADMISSION')
        c.need(self.command(argv, timeout) is False, 'ORIGINAL_MUTATION_CLASSIFICATION_CHANGED')

    def command(self, argv, timeout):
        c, s, r = self.c, self.s, self.r
        package = s.active['target_profile']['package']; uid = s.active['target_profile']['uid']
        if argv == c.STACKS:
            c.need(timeout == 15, 'ORIGINAL_TASK_READ_TIMEOUT'); return False
        if argv == c.FOREGROUND:
            c.need(timeout == 6, 'ORIGINAL_OWNED_FOCUS_READ_TIMEOUT'); return False
        if argv == ['/system/bin/dumpsys', 'package', package]:
            c.need(timeout == 20, 'ORIGINAL_PACKAGE_IDENTITY_TIMEOUT'); return False
        expected_path = ['/system/bin/pm', 'path'] + (['--user', '0'] if s.kind == 'editor_ui03' else []) + [package]
        if argv == expected_path:
            c.need(timeout == 20, 'ORIGINAL_PACKAGE_PATH_TIMEOUT'); return False
        diagnostics = [(['/system/bin/date', '+%s'], 8),
            (['/system/bin/dumpsys', 'activity', 'exit-info', package], 15),
            (['/system/bin/logcat', '-b', 'events', '-d', '-v', 'epoch', '-t', '2048'], 15),
            (['/system/bin/logcat', '--uid=' + str(uid), '-b', 'crash', '-d', '-v', 'epoch', '-t', '512'], 15)]
        if (argv, timeout) in diagnostics:
            s.original_caller(['fixture_diagnostics.py'], {'diagnostics'}); return False
        if argv[:4] == ['/system/bin/cmd', 'activity', 'stack', 'remove']:
            c.need(len(argv) == 5 and timeout == 15 and re.fullmatch('[1-9][0-9]*', argv[4]),
                   'ORIGINAL_EXACT_TASK_REMOVE')
            selected = r.selected_task(); task = selected['task']
            c.need(int(argv[4]) == task and not self.remove_sent and selected['cleanup_allowed'] is True
                and selected['prelaunch_absent'] is True and s.last_stacks is not None,
                'ONCE_ACTUALLY_NEW_OWNED_TASK_ONLY')
            roots, tasks = s.last_stacks
            c.need(tasks == set(selected['prelaunch_task_ids']) | {task}
                and r.tasks.exact_leaf(roots, task, r.scope['package']), 'FRESH_EXACT_OWNED_LEAF_BEFORE_REMOVE')
            item = s.consume_original_intent('remove', argv)
            c.need(item['caller'] == {'source': 'fixture_trial.py', 'function': 'close'}
                and item['value'].get('prelaunch_absent') is True and s.trial.owned is None,
                'ORIGINAL_TRIAL_BURNS_OWNED_AUTHORITY_BEFORE_ONCE_REMOVE')
            c.write_new(r.root / 'cleanup-attempted.json', {'scope': r.scope_ref, 'phase_lease': r.phase_lease_ref,
                'selected': selected, 'argv': argv, 'automatic_retry': False,
                'unknown_input_not_reconciled_by_task_close': True, 'Binder_UID_cleanup_verified': False})
            self.remove_sent = True
            return True
        if s.kind == 'editor_ui03' and argv[:2] == ['/system/bin/am', 'start-activity']:
            f = s.case; selected = r.selected_task(); task = selected['task']; index = s.scope_index
            run = s.active['run_id'] + '_' + str(index)
            expected = ['/system/bin/am', 'start-activity', '-W', '--user', '0', '--display', '0', '--task',
                str(task), '--activity-clear-top', '-n', s.active['target_profile']['component'], '--es', 'run_id', run]
            c.need(s.phase_name == 'business' and timeout == 35 and argv == expected and not self.nonce_sent
                and f is not None and f.current is not None and f.current.run == run and f.current.intent_submitted
                and f.intent_calls == index + 1 and f.c.pending == 'nonce-launch-' + str(index)
                and s.trial.owned is not None and s.trial.owned[0] == task,
                'ONE_ORIGINAL_NONCE_INTENT_IN_THIS_NEW_OWNED_TASK')
            item = s.consume_original_intent('nonce-route', argv)
            c.need(item['caller'] == {'source': 'fixture_editor.py', 'function': 'start'}, 'ORIGINAL_NONCE_CALLER')
            self.nonce_sent = True
            return True
        if s.kind == 'editor_ui03' and argv[:4] == ['/system/bin/input', 'keyboard', '-d', '0']:
            f = s.case
            c.need(s.phase_name == 'business' and timeout == 12 and len(argv) == 6 and argv[4] == 'keyevent'
                and argv[5] in ('KEYCODE_ENTER', 'KEYCODE_MOVE_END', 'KEYCODE_DEL') and f is not None
                and f.c.pending is not None and 1 <= f.actions <= 20 and s.trial.owned is not None,
                'ONLY_ORIGINAL_ONCE_FOCUSED_EDITOR_KEY')
            item = s.consume_original_intent('keyboard', argv)
            c.need(item['caller'] == {'source': 'fixture_editor.py', 'function': 'key'}
                and item['value']['owned_task'] == r.selected_task()['task'] == s.trial.owned[0],
                'ORIGINAL_KEY_INTENT_AND_NEW_TASK_CLAIM')
            focus = s.trial.focus('immediate-key-policy-focus')
            c.need(focus == item['value']['final_owned_task_focus'], 'EDITOR_FOCUS_CHANGED_AT_ACTUAL_KEY_DISPATCH')
            return True
        raise RuntimeError('COMMAND_NOT_IN_ORIGINAL_EDITOR03_OR_PROBE03')

    def observe(self, argv, raw):
        return None

def native_request(c, outer, request, action_used):
    c.need(type(request) is dict and request.get('display') == 0 and request.get('accessibility_mode') == 'none'
        and request.get('expected_package') == outer.get('package', outer.get('expected_package')),
        'EXACT_ORIGINAL_NATIVE_WINDOW_PACKAGE_SCOPE')
    if request.get('op') in ('meta', 'dump'):
        c.need(set(request) == {'op', 'expected_package', 'display', 'accessibility_mode'},
               'ONLY_ORIGINAL_READONLY_NATIVE_FIELDS')
        return False
    c.need(not action_used and outer.get('op') in ('click', 'set-text'), 'NO_SECOND_OR_UNDECLARED_NATIVE_ACTION')
    expected = {k: v for k, v in outer.items() if k in {'op', 'selector', 'value', 'display', 'accessibility_mode', 'method'}}
    expected['expected_package'] = outer['package']
    c.need(request == expected, 'UNCHANGED_FINAL_BACKEND_NATIVE_PROJECTION_REQUIRED')
    return True

def backend_android(c, outer, argv, timeout, action_used):
    if argv == ['/system/bin/screencap', '-p']:
        c.need(timeout == 20, 'ORIGINAL_SCREENSHOT_TIMEOUT'); return False, True
    if (len(argv) == 8 and argv[:6] == ['/system/bin/am', 'instrument', '-w', '-r', '-e', 'request']
            and argv[-1] == 'local.pocket4.actions.v2/.ActionRunner'):
        c.need(timeout == 70, 'ORIGINAL_NATIVE_INSTRUMENTATION_TIMEOUT')
        raw = base64.b64decode(argv[6], validate=True); c.need(len(raw) <= 65536, 'BOUNDED_ORIGINAL_NATIVE_REQUEST')
        request = c.parse(raw)
        c.need(base64.b64encode(json.dumps(request, ensure_ascii=True, separators=(',', ':')).encode()).decode() == argv[6],
               'ACTUAL_UNCHANGED_NATIVE_REQUEST_ENCODING')
        return native_request(c, outer, request, action_used), False
    raise RuntimeError('NO_OTHER_BACKEND_ANDROID_COMMAND')
