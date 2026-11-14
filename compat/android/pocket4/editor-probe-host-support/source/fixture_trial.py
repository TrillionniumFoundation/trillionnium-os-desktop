"""Original two-task observation/removal core, with explicit fresh case bindings.

No historical session is imported. Contacts-only account/data/permission methods
are not included; the two consumers use only the preserved task/UI methods.
"""
from pathlib import Path
import base64, json, re, time

def make_trial(session, transaction, output):
    PACKAGE = session.active['target_profile']['package']
    COMPONENT = session.active['target_profile']['component']
    ROOT = Path(output)
    session.c.need(PACKAGE in ('org.droidloom.qa.editorcontract', 'local.pocket4.fixture'),
                   'ONLY_ORIGINAL_EDITOR03_OR_PROBE03')
    PERMISSION = 'com.android.permissioncontroller'
    STORAGE_PACKAGE = 'com.android.settings'
    STORAGE_ACTIVITY = 'com.android.settings.Settings$ContactsStorageSettingsActivity'
    def require(value, reason):
        if not value:
            raise RuntimeError(reason)

    def parse_stacks(raw):
        roots, tasks = {}, set()
        for block in re.split(r'(?=^RootTask id=)', raw, flags=re.M):
            if not block.startswith('RootTask id='):
                continue
            head = block.splitlines()[0]
            rid = int(re.search(r'^RootTask id=(\d+)\b', head)[1])
            display = int(re.search(r'\bdisplayId=(\d+)\b', head)[1])
            user = int(re.search(r'\buserId=(\d+)\b', head)[1])
            children = []
            for line in block.splitlines():
                match = re.match(r'\s*taskId=(\d+):\s+(\S+)\s+.*?\buserId=(\d+)\b', line)
                require(not re.match(r'\s*taskId=', line) or match is not None, 'UNPARSED_TASK_LINE')
                if match:
                    tid = int(match[1])
                    require(tid not in tasks, 'DUPLICATE_TASK')
                    tasks.add(tid)
                    children.append({'id': tid, 'component': match[2], 'user': int(match[3])})
            require(rid not in roots, 'DUPLICATE_ROOT')
            roots[rid] = {'display': display, 'user': user,
                          'freeform': 'mWindowingMode=freeform' in block, 'children': children}
        require(bool(roots) and bool(tasks), 'UNRECOGNIZED_STACK_LIST')
        return roots, tasks

    def exact_leaf(roots, task):
        root = roots.get(task)
        return bool(root and root['display'] == 0 and root['user'] == 0 and root['freeform']
            and len(root['children']) == 1 and root['children'][0]['id'] == task
            and root['children'][0]['user'] == 0
            and root['children'][0]['component'].split('/')[0] == PACKAGE)

    def focus_metadata(raw):
        focus_lines = [line.strip() for line in raw.splitlines() if 'mCurrentFocus=' in line]
        app_lines = [line.strip() for line in raw.splitlines() if 'mFocusedApp=' in line]
        focus = re.findall(r'mCurrentFocus=Window\{([0-9a-fA-F]+)\s+u(\d+)\s+([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)', raw)
        app = re.findall(r'mFocusedApp=ActivityRecord\{[^\n]*?\bu(\d+)\s+([A-Za-z0-9_.]+)/([A-Za-z0-9_.$]+)\s+t(\d+)\b', raw)
        if len(set(focus_lines)) != 1 or len(set(app_lines)) != 1 or len(set(focus)) != 1 or len(set(app)) != 1:
            return {'verified': False, 'reason': 'FOCUS_OR_ACTIVITY_NOT_UNIQUE',
                    'focus_lines': focus_lines + app_lines}
        token, user, package, activity = focus[0]
        app_user, app_package, app_activity, task = app[0]
        return {'verified': user == app_user == '0' and package == app_package,
                'package': package, 'activity': activity, 'window_token': token.lower(),
                'focused_activity': app_activity, 'task': int(task), 'user': int(user)}

    class Trial:
        def __init__(self, session, tx):
                self.s, self.tx, self.owned = session, tx, None
                self.sequence = self.launches = self.clicks = self.removals = 0
                self.denials = 0
                self.last_observation = None
                self.storage_from_create = None
                self.result = {'state': 'NOT_STARTED', 'ui_launch_calls': 0, 'open_editor_clicks': 0,
                    'contact_field_entries': 0, 'contact_save_calls': 0, 'contact_delete_calls': 0,
                    'account_actions': 0, 'sync_actions': 0, 'whole_app_production_ready': False}

        def record(self, label, value):
                self.sequence += 1
                self.tx.write_new(ROOT / ('%03d-' % self.sequence + label + '.json'), value)

        def stacks(self, label):
                raw = self.s.android(['/system/bin/cmd', 'activity', 'stack', 'list'], 15).decode('utf-8', 'strict')
                roots, tasks = parse_stacks(raw)
                self.record(label, {'raw_stacks': raw, 'task_ids': sorted(tasks)})
                return roots, tasks

        def focus(self, label):
                raw = self.s.android(['/system/bin/dumpsys', 'window', 'displays'], 6).decode('utf-8', 'strict')
                value = focus_metadata(raw)
                self.record(label, value)
                return value

        def focus_allowed(self, current, allow_permission=True):
                if (self.owned is None or current.get('verified') is not True
                        or current.get('task') != self.owned[0]):
                    return False
                if current.get('package') == PACKAGE:
                    return True
                if allow_permission and current.get('package') == PERMISSION:
                    return True
                return bool(self.storage_from_create
                    and self.storage_from_create['owned_task'] == self.owned[0]
                    and current.get('package') == STORAGE_PACKAGE
                    and current.get('activity') == STORAGE_ACTIVITY
                    and current.get('focused_activity') in (STORAGE_ACTIVITY, '.Settings$ContactsStorageSettingsActivity'))

        def ready_focus(self, allow_permission=True):
                require(self.owned is not None, 'FOCUS_REQUIRES_OWNED_TASK')
                task, preserved = self.owned
                deadline = time.monotonic() + 10
                previous = None
                observations = 0
                # A held read has a six-second outer bound. Do not start one unless that
                # bound fits entirely inside the ten-second readiness budget.
                while deadline - time.monotonic() > 6:
                    current = self.focus('wm-focus-readiness')
                    observations += 1
                    valid = self.focus_allowed(current, allow_permission)
                    if valid and current == previous:
                        roots, tasks = self.stacks('ready-owned-task')
                        require(exact_leaf(roots, task) and tasks == preserved | {task}, 'READY_TASK_SCOPE_CHANGED')
                        self.record('wm-focus-ready', {'focus': current, 'observations': observations,
                            'readiness_max_seconds': 10, 'no_launch_replay': True})
                        return current
                    previous = current if valid else None
                    time.sleep(.2)
                raise RuntimeError('OWNED_FOCUS_NOT_READY_WITHIN_BOUNDED_READS')

        def launch(self):
                roots, tasks = self.stacks('before-launch')
                require(not any(child['component'].split('/')[0] == PACKAGE
                                for root in roots.values() for child in root['children']), 'PREEXISTING_CONTACTS_TASK_PRESERVED')
                argv = [*self.tx.ALEX_PREFIX, 'launch', PACKAGE, '--component', COMPONENT, '--json']
                self.record('launch-intent', {'argv': argv, 'automatic_retry': False})
                self.launches += 1
                response = self.s.run_host('contacts-launch', argv, 45)
                require(response['rc'] == 0 and not response['timed_out'] and response['joined'], 'LAUNCH_OUTCOME_UNKNOWN')
                value = json.loads(response['stdout'])
                require(value.get('ok') is True and value.get('state') == 'running' and
                        value.get('host_pid') == self.tx.MAIN_HOST and value.get('outcome_unknown') is not True,
                        'LAUNCH_RECEIPT_UNCERTAIN')
                match = re.fullmatch(r'object=(\d+) composer_display=(\d+) android_display=(\d+) task=(\d+)', value.get('launch', ''))
                require(match is not None and int(match[3]) == 0, 'LAUNCH_TASK_UNIDENTIFIED')
                task = int(match[4])
                require(task not in roots and task not in tasks, 'LAUNCH_TASK_NOT_NEW')
                self.owned = (task, tasks)
                after_roots, after_tasks = self.stacks('after-launch')
                require(exact_leaf(after_roots, task) and after_tasks == tasks | {task}, 'LAUNCH_SCOPE_CHANGED')
                self.result['owned_task'] = task

        def observe(self, label, focus):
                require(self.focus_allowed(focus), 'OBSERVATION_HAS_NO_OWNED_FOCUS')
                self.s.guard()
                value = self.s.helper.dispatch({'op': 'observe', 'package': focus['package'],
                    'window_token': focus['window_token'], 'display': 0, 'accessibility_mode': 'none', 'with_png': True})
                self.s.guard()
                require(isinstance(value, dict), 'OBSERVATION_RESPONSE_INVALID')
                png = value.pop('screenshot_png_base64', None)
                if png is not None:
                    self.tx.write_new(ROOT / (label + '.png'), base64.b64decode(png, validate=True))
                self.record(label, value)
                native = value.get('native', value)
                require(value.get('ok') is True and value.get('outcome_unknown') is not True and
                        native.get('ok') is True and native.get('accessibility_mode_restoration_verified') is True,
                        'OBSERVATION_UNVERIFIED')
                require(value['screenshot']['scope']['package'] == focus['package'] and
                        value['screenshot']['scope']['window_token'] == focus['window_token'], 'OBSERVATION_PACKAGE_CHANGED')
                self.last_observation = value
                return native.get('nodes', [])

        def close(self):
                if self.owned is None:
                    return
                task, preserved = self.owned
                roots, tasks = self.stacks('before-close')
                require(tasks - {task} == preserved, 'OTHER_TASK_SET_CHANGED_NO_CLOSE')
                if task not in roots and task not in tasks:
                    self.owned = None
                    self.result['owned_task_removed'] = True
                    return
                require(exact_leaf(roots, task), 'OWNED_TASK_NOT_EXACT_LEAF_NO_CLOSE')
                command = ['/system/bin/cmd', 'activity', 'stack', 'remove', str(task)]
                self.record('close-intent', {'argv': command, 'automatic_retry': False, 'prelaunch_absent': True})
                self.owned = None
                self.removals += 1
                self.s.android(command, 15)
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    time.sleep(.25)
                    roots, tasks = self.stacks('close-readback')
                    require(tasks - {task} == preserved, 'OTHER_TASK_SET_CHANGED_DURING_CLOSE')
                    if task not in roots and task not in tasks:
                        self.result.update(owned_task_removed=True, other_tasks_preserved=True)
                        return
                    root = roots.get(task)
                    shrinking = bool(root and task not in tasks and root['display'] == 0 and root['user'] == 0
                                     and root['freeform'] and root['children'] == [])
                    require(exact_leaf(roots, task) or shrinking, 'OWNED_TASK_SCOPE_CHANGED_DURING_CLOSE')
                raise RuntimeError('OWNED_CLOSE_COMPLETION_UNKNOWN')

        def owned_foreground(self):
            current = self.ready_focus(allow_permission=False)
            return {key: current[key] for key in ('package', 'activity', 'window_token')}

    return Trial(session, transaction)
