#!/usr/bin/python3 -I
"""Contacts adapter with one source-bound system contacts-storage transition.

The dedicated Settings activity is accepted only after the same owned Contacts
task produced the acknowledged Create button input. Other Settings pages remain
outside scope. This adapter only observes; a reviewed continuation owns actions.
The standalone preflight keeps its original no-data-write behavior.
"""
from pathlib import Path
import argparse
import base64
import hashlib
import json
import re
import time
import types

SOURCE = Path('/home/alex/work/pocket4-camera-release08-20261105-r12/transaction-tools-01/camera_transaction.py')
SOURCE_SHA = 'b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
ROOT = Path('/home/alex/work/pocket4-contacts-ui-preflight-20261105-r12-05')
PACKAGE = 'com.android.contacts'
PERMISSION = 'com.android.permissioncontroller'
STORAGE_PACKAGE = 'com.android.settings'
STORAGE_ACTIVITY = 'com.android.settings.Settings$ContactsStorageSettingsActivity'
QUICK_ACTIVITY = 'com.android.contacts.quickcontact.QuickContactActivity'
COMPONENT = PACKAGE + '/.activities.PeopleActivity'
APK_PATH = '/product/priv-app/Contacts/Contacts.apk'
APK_SHA = '11f8be5fd46dd79ee4f7524d5d1334e21ce0f9e23892b2940a5b6091e2f349d0'
CREATE_LABELS = {'Create contact', 'Add contact', 'New contact', '创建联系人', '新建联系人', '添加联系人'}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def load_session():
    raw = SOURCE.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == SOURCE_SHA, 'FROZEN_SESSION_CHANGED')
    tx = types.ModuleType('contacts_ui_frozen_session')
    tx.__file__ = str(SOURCE)
    exec(compile(raw, str(SOURCE), 'exec'), tx.__dict__)
    return tx


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


def contacts_popup_metadata(raw):
    """Recognize only the actual owned Contacts overflow window format."""
    lines = [line.strip() for line in raw.splitlines() if 'mCurrentFocus=' in line]
    app_lines = [line.strip() for line in raw.splitlines() if 'mFocusedApp=' in line]
    focus = re.findall(r'mCurrentFocus=Window\{([0-9a-f]+) u0 (PopupWindow:[0-9a-f]+)\}', raw)
    apps = re.findall(r'mFocusedApp=ActivityRecord\{[^\n]*? u0 com\.android\.contacts/([A-Za-z0-9_.$]+) t(\d+)\}', raw)
    if len(set(lines)) != 1 or len(set(app_lines)) != 1 or len(focus) != 1 or len(apps) != 1:
        return None
    activity, task = apps[0]
    if activity not in (QUICK_ACTIVITY, '.quickcontact.QuickContactActivity'):
        return None
    token, title = focus[0]
    return {'verified': True, 'package': PACKAGE, 'activity': QUICK_ACTIVITY,
            'focused_activity': activity, 'window_token': token, 'task': int(task), 'user': 0,
            'window_kind': 'owned_contacts_more_popup', 'actual_window_title': title}


class Trial:
    def __init__(self, session, tx):
        self.s, self.tx, self.owned = session, tx, None
        self.sequence = self.launches = self.clicks = self.removals = 0
        self.denials = 0
        self.last_observation = None
        self.storage_from_create = None
        self.menu_contact = self.menu_from_more = None
        self.s.helper.foreground = self.owned_foreground
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

    def empty_database(self):
        raw = self.s.android(['/system/bin/content', 'query', '--uri',
            'content://com.android.contacts/raw_contacts', '--projection', '_id:contact_id:deleted']).decode('utf-8', 'strict')
        require(raw.strip() == 'No result found.', 'CONTACTS_DATABASE_NOT_EMPTY')
        return True

    def account_topology(self):
        command = ("set -o pipefail; /system/bin/dumpsys account | /system/bin/sed -n "
            "-e 's/^[[:space:]]*Accounts: \\([0-9][0-9]*\\)[[:space:]]*$/Accounts: \\1/p' "
            "-e 's/^[[:space:]]*Account {.*type=\\([^}]*\\)}[[:space:]]*$/AccountType: \\1/p'")
        raw = self.s.android(['/system/bin/sh', '-c', command]).decode('utf-8', 'strict')
        value = {'counts': [int(x) for x in re.findall(r'^Accounts: (\d+)$', raw, re.M)],
                 'types': re.findall(r'^AccountType: (.*)$', raw, re.M)}
        require(value == {'counts': [1], 'types': ['com.ss.android.ugc.aweme']},
                'OBSERVED_ACCOUNT_TOPOLOGY_CHANGED')
        return value

    def identity(self):
        data, _ = self.s.target.read_file(APK_PATH, 16 * 1024 * 1024)
        require(len(data) == 11839391 and hashlib.sha256(data).hexdigest() == APK_SHA, 'CONTACTS_APK_CHANGED')
        paths = self.s.android(['/system/bin/pm', 'path', PACKAGE]).decode('utf-8', 'strict').splitlines()
        require(paths == ['package:' + APK_PATH], 'CONTACTS_ACTIVE_PATH_CHANGED')
        self.s.guard()

    def focus(self, label):
        raw = self.s.android(['/system/bin/dumpsys', 'window', 'displays'], 6).decode('utf-8', 'strict')
        value = focus_metadata(raw)
        if value.get('verified') is not True:
            popup = contacts_popup_metadata(raw)
            grant = self.menu_from_more
            if (popup and grant and self.owned is not None
                    and popup['task'] == self.owned[0] == grant['owned_task']
                    and popup['window_token'] != grant['parent_window_token']
                    and grant.get('popup_window_token') in (None, popup['window_token'])):
                grant['popup_window_token'] = popup['window_token']
                value = popup
        self.record(label, value)
        return value

    def owned_foreground(self):
        # Only this imported helper instance changes. Frozen window_state still
        # requires the native selected window to be focused, type 1 and Contacts;
        # capture still checks it before/after and binds the real popup token.
        value = self.focus('helper-owned-foreground')
        require(self.focus_allowed(value, allow_permission=False), 'HELPER_FOREGROUND_OUTSIDE_OWNED_TASK')
        return {key: value[key] for key in ('package', 'activity', 'window_token')}

    def bind_owned_contact_menu(self, proof):
        require(self.owned is not None and self.menu_contact is None
                and proof.get('name') == 'Pocket4 Local QA r12 9c38f5a1 Edited'
                and proof.get('local_null_account') is True
                and all(re.fullmatch('[1-9][0-9]*', proof.get(key, '')) for key in
                        ('raw_contact_id', 'contact_id', 'name_data_id')),
                'MORE_MENU_REQUIRES_EXACT_OWNED_LOCAL_CONTACT')
        scope = self.last_observation['screenshot']['scope']
        require(scope['package'] == PACKAGE and scope['activity'] == QUICK_ACTIVITY,
                'MORE_MENU_SOURCE_IS_NOT_OWNED_QUICK_CONTACT')
        self.menu_contact = dict(proof)
        self.record('owned-contact-menu-proof', proof)

    def authorize_contacts_menu_from_more(self, acknowledgement):
        target = acknowledgement.get('actual_target', {})
        require(self.menu_contact is not None and self.menu_from_more is None
                and self.owned is not None and acknowledgement.get('ok') is True
                and acknowledgement.get('performed') == 'click'
                and acknowledgement.get('outcome_unknown') is not True
                and acknowledgement.get('accessibility_mode_restoration_verified') is True
                and target.get('package') == PACKAGE
                and target.get('content-desc') == 'More options'
                and target.get('class') == 'android.widget.ImageButton'
                and all(target.get(key) is True for key in ('visible', 'enabled', 'clickable')),
                'CONTACTS_POPUP_HAS_NO_SUCCESSFUL_OWNED_MORE_ACK')
        scope = self.last_observation['screenshot']['scope']
        require(scope['package'] == PACKAGE and scope['activity'] == QUICK_ACTIVITY,
                'MORE_ACK_SOURCE_ACTIVITY_CHANGED')
        self.menu_from_more = {'owned_task': self.owned[0],
            'parent_window_token': scope['window_token'], 'popup_window_token': None,
            'source': 'successful_native_more_options_ack', 'contact': self.menu_contact}
        self.record('authorize-owned-contacts-more-popup', self.menu_from_more)

    def authorize_storage_from_create(self, acknowledgement):
        target = acknowledgement.get('actual_target', {})
        require(acknowledgement.get('ok') is True and acknowledgement.get('performed') == 'click'
                and acknowledgement.get('outcome_unknown') is not True
                and acknowledgement.get('accessibility_mode_restoration_verified') is True
                and target.get('package') == PACKAGE
                and target.get('resource-id') == PACKAGE + ':id/floating_action_button'
                and target.get('content-desc') == 'Create new contact', 'STORAGE_HAS_NO_ACKNOWLEDGED_CONTACTS_CREATE')
        require(self.owned is not None and self.last_observation is not None
                and self.last_observation['screenshot']['scope']['package'] == PACKAGE,
                'STORAGE_SOURCE_OBSERVATION_NOT_CONTACTS')
        self.storage_from_create = {'owned_task': self.owned[0],
            'source': 'acknowledged_contacts_floating_action_button',
            'allowed_activity': STORAGE_ACTIVITY, 'same_task_required': True}
        self.record('authorize-specific-storage-transition', self.storage_from_create)

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

    def deny_optional_notifications(self, nodes, focus):
        require(self.denials == 0 and focus['package'] == PERMISSION, 'NOTIFICATION_DENIAL_SCOPE_INVALID')
        visible = [node for node in nodes if node.get('package') == PERMISSION and node.get('visible') is True]
        messages = [' '.join(str(node.get('text', '')).split()) for node in visible
                    if node.get('resource-id') == PERMISSION + ':id/permission_message']
        allowed_messages = {'Allow Contacts to send you notifications?', 'Allow Contacts to send you notifications'}
        require(len(messages) == 1 and messages[0] in allowed_messages,
                'OTHER_PERMISSION_OR_NOTIFICATION_REQUESTER_NOT_VERIFIED')
        # Trial02 observed this Android build's actual uppercase label and
        # deny-and-dont-ask-again resource. Do not infer a button by position.
        deny_ids = {PERMISSION + ':id/permission_deny_button',
                    PERMISSION + ':id/permission_deny_and_dont_ask_again_button'}
        deny = [node for node in visible if node.get('resource-id') in deny_ids
                and str(node.get('text', '')).replace('’', "'").casefold() in ("don't allow", '不允许')
                and node.get('clickable') is True and node.get('enabled') is True]
        require(len(deny) == 1, 'ONE_CURRENT_NOTIFICATION_DENY_CONTROL_REQUIRED')
        dump = self.s.android(['/system/bin/dumpsys', 'package', PACKAGE]).decode('utf-8', 'strict')
        active = re.findall(r'^Packages:\n(.*?)(?=^\S|\Z)', dump, re.M | re.S)
        require(len(active) == 1 and re.findall(r'^        android\.permission\.POST_NOTIFICATIONS: granted=(true|false),',
                active[0], re.M) == ['false'], 'NOTIFICATION_PERMISSION_PRECONDITION_CHANGED')
        require(self.focus('before-notification-deny') == focus, 'NOTIFICATION_WINDOW_CHANGED')
        bounds = deny[0].get('bounds_array')
        require(isinstance(bounds, list) and len(bounds) == 4 and all(type(x) is int for x in bounds)
                and bounds[0] < bounds[2] and bounds[1] < bounds[3], 'DENY_NODE_BOUNDS_UNKNOWN')
        screenshot = self.last_observation['screenshot']
        require(screenshot['scope']['window_token'] == focus['window_token'] and
                screenshot['scope']['package'] == PERMISSION, 'DENY_OBSERVATION_SCOPE_CHANGED')
        # The native semantics identify the deny button; the existing helper's
        # snapshot API rechecks package/token/full frame/scope/context before
        # one tap. A same-window prompt swap therefore fails STALE_FRAME.
        request = {'op': 'snapshot-tap', 'package': PERMISSION, 'display': 0,
            'accessibility_mode': 'none', 'input_source': 'touch',
            'window_token': focus['window_token'], 'frame_sha256': screenshot['frame_sha256'],
            'scope_sha256': screenshot['scope_sha256'], 'context_token': screenshot['context_token'],
            'coords': [(bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2]}
        self.record('notification-deny-intent', {'request': request, 'observed_message': messages[0],
            'observed_deny_node': deny[0],
            'permission': 'android.permission.POST_NOTIFICATIONS', 'owned_task': self.owned[0],
            'window_token': focus['window_token'], 'automatic_retry': False})
        self.denials += 1
        self.s.guard()
        value = self.s.helper.dispatch(request)
        self.s.guard()
        self.record('notification-deny-response', value)
        require(value.get('ok') is True and value.get('performed') == 'snapshot-tap' and
                value.get('input_command_completed') is True, 'NOTIFICATION_DENY_OUTCOME_UNKNOWN')
        # dispatch can report unknown post-observation when the permission
        # window closes. Preserve that historical fact, do not repeat the click;
        # the next decision requires a new stable owned Contacts observation.
        self.result['notification_original_response_outcome_unknown'] = value.get('outcome_unknown') is True
        self.result['notification_input_command_completed'] = True
        self.result['notification_prompt_semantic_verified'] = messages[0]
        return self.ready_focus(allow_permission=False)

    def open_empty_editor(self, nodes):
        require(self.owned is not None and self.clicks == 0, 'EDITOR_CLICK_LIMIT')
        choices = [node for node in nodes if node.get('package') == PACKAGE and
            all(node.get(k) is True for k in ('visible', 'enabled', 'clickable')) and
            (node.get('text') in CREATE_LABELS or node.get('content-desc') in CREATE_LABELS)]
        require(len(choices) == 1, 'NO_UNIQUE_OBSERVED_CREATE_CONTACT_CONTROL')
        chosen = choices[0]
        selector = {'package': PACKAGE, 'enabled': True, 'clickable': True}
        if chosen.get('resource-id'):
            selector['id'] = chosen['resource-id']
        if chosen.get('text') in CREATE_LABELS:
            selector['text'] = chosen['text']
        if chosen.get('content-desc') in CREATE_LABELS:
            selector['desc'] = chosen['content-desc']
        task, preserved = self.owned
        roots, tasks = self.stacks('before-editor')
        require(exact_leaf(roots, task) and tasks == preserved | {task}, 'EDITOR_TASK_SCOPE_CHANGED')
        request = {'op': 'click', 'package': PACKAGE, 'selector': selector,
                   'method': 'accessibility', 'accessibility_mode': 'none', 'display': 0,
                   'window_token': self.last_observation['screenshot']['scope']['window_token']}
        self.record('open-empty-editor-intent', {'request': request, 'no_field_entry_or_save': True,
                                               'automatic_retry': False})
        self.clicks += 1
        self.s.guard()
        value = self.s.helper.dispatch(request)
        self.s.guard()
        self.record('open-empty-editor-response', value)
        require(value.get('ok') is True and value.get('outcome_unknown') is not True and
                value.get('performed') == 'click', 'EDITOR_CLICK_OUTCOME_UNKNOWN')

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

    def run(self):
        try:
            self.identity()
            self.result['empty_database_before'] = self.empty_database()
            self.result['account_topology_before'] = self.account_topology()
            self.launch()
            focus = self.ready_focus()
            if focus['package'] == PERMISSION:
                permission_nodes = self.observe('owned-permission-window', focus)
                self.result['permission_labels'] = [{k: node[k] for k in
                    ('text', 'content-desc', 'resource-id', 'class', 'clickable', 'enabled', 'visible')
                    if k in node} for node in permission_nodes if node.get('text') or node.get('content-desc')]
                focus = self.deny_optional_notifications(permission_nodes, focus)
            nodes = self.observe('contacts-list', focus)
            self.open_empty_editor(nodes)
            editor_focus = self.ready_focus(allow_permission=False)
            editor = self.observe('empty-editor', editor_focus)
            self.result['editor_labels'] = [{k: node[k] for k in
                ('text', 'content-desc', 'resource-id', 'class', 'hint', 'editable', 'bounds_array',
                 'selected', 'clickable', 'enabled', 'visible')
                if k in node} for node in editor if node.get('text') or node.get('content-desc')
                or node.get('hint') or node.get('editable')]
            self.result['device_label_observed'] = any(re.search(r'\b(?:device|local|phone only)\b',
                str(node.get('text', '')) + ' ' + str(node.get('content-desc', '')), re.I) for node in editor)
            self.result['state'] = 'EMPTY_EDITOR_OBSERVED_REQUIRES_DESTINATION_REVIEW'
        except BaseException as exc:
            self.result.update(state='UI_PREFLIGHT_STOPPED', error=type(exc).__name__ + ': ' + str(exc))
        finally:
            try:
                self.close()
                self.result['empty_database_after'] = self.empty_database()
                self.result['account_topology_after'] = self.account_topology()
                self.identity()
                self.s.caller_status('contacts-final-caller')
            except BaseException as exc:
                self.result.update(state='UI_PREFLIGHT_CLEANUP_OR_READBACK_FAILED',
                                   cleanup_error=type(exc).__name__ + ': ' + str(exc))
            self.result.update(ui_launch_calls=self.launches, open_editor_clicks=self.clicks,
                               notification_deny_calls=self.denials,
                               owned_task_remove_calls=self.removals, source_sha256=SOURCE_SHA,
                               epoch_sha256=self.s.epoch_sha256, automatic_retry=False)
            self.tx.write_new(ROOT / 'result.json', self.result)
        return self.result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not args.execute:
        print(json.dumps({'state': 'PLAN_ONLY', 'scope': __doc__, 'root': str(ROOT)}, indent=2))
        return 0
    tx = load_session()
    with tx.ui_lock():
        ROOT.mkdir(mode=0o700)
        with tx.CameraSession(ROOT / 'commands') as session:
            result = Trial(session, tx).run()
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result['state'] == 'EMPTY_EDITOR_OBSERVED_REQUIRES_DESTINATION_REVIEW' else 1


if __name__ == '__main__':
    raise SystemExit(main())
