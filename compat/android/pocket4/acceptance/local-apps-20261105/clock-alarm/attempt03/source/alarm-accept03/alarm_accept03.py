#!/usr/bin/python3 -I
"""One owned alarm through real Clock UI; default inert, never writes SQL/settings."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import copy
import hashlib
import json
import re
import signal
import time
import types

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/alex/work/pocket4-clock-alarm-accept-20261105-r12-03')
PACKAGE = 'com.android.deskclock'
MAIN = PACKAGE + '.DeskClock'
ALERT = PACKAGE + '.alarms.AlarmActivity'
ALARM_KEY = '0|com.android.deskclock|2147483640|null|10063'
WORK_SECONDS, CLEANUP_SECONDS, MAX_INPUTS = 600, 90, 24
PINS = {
    'base': ('/home/alex/work/pocket4-contacts-session-tools-20261105-r12-01/ui_preflight04.py',
             'd02821d751736a9e3cf275ec0b27383852e24362928fd4257ebb6d3dee7f6a58'),
    'model': (str(HERE / 'read_clock_expired_text02.py'), '93a25eacc015e5e87a12a0cd55a9b97c8a7fd7068dd6c691a56b9c77b2a1af6f'),
    'reader': (str(HERE / 'read_owned_alarm01.py'), '926129def477b063d4003c3c7b3919dba3f15f020ff821fd384befa3395996b8'),
    'timer': ('/home/alex/work/pocket4-clock-session-tools-20261105-r12-01/read_timer.py',
              'c3bf02f38e05ab7a55285ca2245ffe2bda3eb528cc1f85d54723294047948b08'),
    'installer': ('/home/alex/work/pocket4-clock-expired-text-20261105-r12-02/transaction03/clock_install03.py',
                  '0f7d01f428d1b472e48327df66111d22dbd0551dc5a090faf8c4f5627aff1b48'),
}
NATIVE_SHA = 'a5368465d5f6faef3299bf1ba6d6bde268cc8b37c72401c6e668872b24725058'
NODE_KEYS = ('package', 'resource-id', 'class', 'text', 'content-desc', 'hint', 'bounds_array',
             'visible', 'enabled', 'clickable', 'editable', 'password', 'focused', 'selected', 'checked')


def need(ok, why):
    if not ok:
        raise RuntimeError(why)


def stamp():
    return datetime.now(timezone.utc).isoformat()


def load(path, expected):
    raw = Path(path).read_bytes()
    need(hashlib.sha256(raw).hexdigest() == expected, 'FROZEN_ALARM_DEPENDENCY_CHANGED')
    module = types.ModuleType('alarm_private_' + Path(path).stem)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def activity(value):
    return PACKAGE + value if value.startswith('.') else value


def node_identity(node):
    # Native window IDs are per accessibility connection. Real WM tokens are
    # checked independently; every semantic field and geometry remains bound.
    return {key: node.get(key) for key in NODE_KEYS}


def contains(outer, inner):
    return (isinstance(outer, list) and isinstance(inner, list) and len(outer) == len(inner) == 4
        and all(type(x) is int for x in outer + inner)
        and outer[0] <= inner[0] < inner[2] <= outer[2]
        and outer[1] <= inner[1] < inner[3] <= outer[3])


def tasks_map(roots):
    return {row['id']: (row['component'], row['user']) for root in roots.values() for row in root['children']}


def alarm_pending_count(text):
    values = re.findall(r'^  Pending alarms per uid: \[(.*)\]$', text, re.M)
    need(len(values) == 1, 'ACTUAL_PENDING_ALARM_SECTION_UNKNOWN')
    rows = [] if not values[0] else [part.strip() for part in values[0].split(',')]
    parsed = [re.fullmatch(r'([A-Za-z0-9]+):(\d+)', row) for row in rows]
    need(all(parsed) and len(rows) == len({m[1] for m in parsed}), 'PENDING_ALARM_UID_FORMAT_UNKNOWN')
    owned = [int(m[2]) for m in parsed if m[1] in ('u0a63', '10063')]
    need(len(owned) <= 1, 'CLOCK_PENDING_UID_AMBIGUOUS')
    return owned[0] if owned else 0


def active_alarm_record(text, marker):
    lines = text.splitlines()
    need(lines and lines[0] == "Current Notification Manager state (filtered to 'com.android.deskclock'):",
        'EXACT_CLOCK_NOTIFICATION_FILTER_UNKNOWN')
    starts = [i for i, line in enumerate(lines) if line == '  Notification List:']
    need(len(starts) == 1, 'ACTIVE_NOTIFICATION_SECTION_UNKNOWN')
    active = []
    for line in lines[starts[0] + 1:]:
        if line.strip() and not line.startswith('    '):
            break
        active.append(line)
    blocks = re.split(r'(?=^    NotificationRecord\()', '\n'.join(active), flags=re.M)
    need(not blocks[0].strip(), 'ACTIVE_NOTIFICATION_RECORD_FORMAT_UNKNOWN')
    records = [b for b in blocks[1:] if re.search(r'\bkey=' + re.escape(ALARM_KEY) + r'(?:\s|$)', b)]
    need(len(records) <= 1, 'OWNED_ALARM_NOTIFICATION_DUPLICATE')
    if not records:
        return {'present': False, 'active_clock_count': len(blocks) - 1}
    block = records[0]
    valid = (re.search(r'\buid=10063\b', block) is not None and 'user=UserHandle{0}' in block
        and re.search(r'\bchannel=alarmNotification\b', block) is not None
        and re.search(r'\bfullscreenIntent=PendingIntent\{', block) is not None
        and re.search(r'android\.title=String \(' + re.escape(marker) + r'\)', block) is not None)
    return {'present': True, 'source_bound_marker_and_fullscreen_intent': bool(valid),
        'key': ALARM_KEY, 'record_sha256': hashlib.sha256(block.encode()).hexdigest(),
        'active_clock_count': len(blocks) - 1, 'physical_speaker_or_desktop_popup_inferred': False}


class Flow:
    def __init__(self, trial, base, model, reader, result, resources):
        self.t, self.base, self.model, self.m, self.r = trial, base, model, reader, result
        self.reader = reader.Read(trial.s, model)
        self.ids, self.texts = resources['ids'], resources['texts']
        self.nodes, self.latest = [], None
        self.actions = 0
        self.pending = None
        self.effect_pending = None
        self.create_ack = self.label_ack = self.dismiss_ack = self.delete_ack = False
        self.native_tasks, self.normal_closed, self.self_finished = [], [], []
        self.close_pending = None
        self.alert_task = None
        self.alert_binding = None
        self.end = time.monotonic() + WORK_SECONDS - 10
        roots, tasks = self.t.stacks('alarm-baseline-tasks')
        self.baseline, self.baseline_map = set(tasks), tasks_map(roots)
        self.baseline_roots = copy.deepcopy(roots)
        need(not any(row[0].split('/')[0] == PACKAGE for row in self.baseline_map.values()),
            'PREEXISTING_CLOCK_TASK_PRESERVED')
        original = base.exact_leaf
        def exact(roots, task):
            if task == self.alert_task:
                root = roots.get(task)
                return bool(root and root['display'] == root['user'] == 0 and len(root['children']) == 1
                    and root['children'][0] == {'id': task, 'component': self.alert_binding['component'], 'user': 0})
            return original(roots, task)
        base.exact_leaf = exact
        def allowed(current, allow_permission=False):
            expected = ALERT if self.t.owned and self.t.owned[0] == self.alert_task else MAIN
            return bool(self.t.owned and current.get('verified') is True and current.get('user') == 0
                and current.get('package') == PACKAGE and current.get('task') == self.t.owned[0]
                and activity(current.get('activity', '')) == activity(current.get('focused_activity', '')) == expected)
        trial.focus_allowed = allowed

    def topology(self, label):
        roots, tasks = self.t.stacks(label)
        now = tasks_map(roots)
        need(self.baseline <= tasks and all(now.get(k) == v for k, v in self.baseline_map.items())
            and all(roots.get(k) == v for k, v in self.baseline_roots.items()), 'ORIGINAL_TASK_TOPOLOGY_CHANGED')
        return roots, tasks

    def observe(self, label):
        need(time.monotonic() < self.end, 'ALARM_DEADLINE_BEFORE_OBSERVE')
        focus = self.t.ready_focus(allow_permission=False)
        self.nodes = self.t.observe(label, focus)
        self.latest = label
        return focus

    def visible(self):
        return [n for n in self.nodes if n.get('package') == PACKAGE
            and n.get('visible') is True and n.get('enabled') is True]

    def unique(self, predicate, reason):
        nodes = [n for n in self.visible() if predicate(n)]
        need(len(nodes) == 1, reason)
        return nodes[0]

    def by_id(self, ident, editable=False):
        return self.unique(lambda n: n.get('resource-id') == ident and n.get('password') is False
            and n.get('editable') is editable, 'ONE_VISIBLE_CONTROL_REQUIRED_' + ident.rsplit('/', 1)[-1])

    def selector(self, node, empty_field=False):
        value = {'package': PACKAGE, 'class': node['class'], 'enabled': True}
        for field, key in (('id', 'resource-id'), ('text', 'text'), ('desc', 'content-desc')):
            if node.get(key):
                value[field] = node[key]
        if empty_field:
            need(node.get('editable') is True and node.get('password') is False
                and not node.get('text') and not node.get('hint') and type(node.get('focused')) is bool,
                'EXACT_EMPTY_ALARM_LABEL_FIELD_REQUIRED')
            value.update(text='', focused=node['focused'], editable=True)
        need(any(k in value for k in ('id', 'text', 'desc')), 'OBSERVED_SEMANTIC_SELECTOR_REQUIRED')
        return value

    def matches(self, node, selector):
        fields = {'id': 'resource-id', 'text': 'text', 'desc': 'content-desc'}
        return all(node.get(fields.get(k, k)) == v for k, v in selector.items())

    def native(self, label, node, op='click', value=None, mouse=False, empty_field=False, observe_after=True):
        need(self.pending is None and self.close_pending is None and self.effect_pending is None
            and self.actions < MAX_INPUTS and time.monotonic() < self.end,
            'ALARM_INPUT_BUDGET_OR_UNKNOWN')
        need(op in ('click', 'set-text') and not node.get('password'), 'ALARM_INPUT_OPERATION_INVALID')
        if mouse:
            need(label == 'expand-owned' and node.get('text') == self.m.MARKER
                and node.get('editable') is False and node.get('resource-id') != self.ids['label'],
                'MOUSE_ONLY_FOR_EXACT_COLLAPSED_OWNED_LABEL')
        else:
            need(node.get('editable') is True if op == 'set-text' else node.get('clickable') is True,
                'ACTUAL_CONTROL_NOT_ACTIONABLE')
        selector = self.selector(node, empty_field)
        if op == 'set-text':
            need(isinstance(value, str) and 0 < len(value) <= 64, 'OWNED_ALARM_INPUT_VALUE_INVALID')
            selector['editable'] = True
        elif not mouse:
            selector['clickable'] = True
        prior = self.t.last_observation['screenshot']
        self.observe('fresh-%02d-' % (self.actions + 1) + label)
        fresh = [n for n in self.visible() if self.matches(n, selector)]
        need(len(fresh) == 1 and node_identity(fresh[0]) == node_identity(node), 'ALARM_SEMANTIC_CONTROL_CHANGED')
        current = self.t.last_observation['screenshot']
        focus = self.t.ready_focus(allow_permission=False)
        need(prior['scope']['window_token'] == current['scope']['window_token'] == focus['window_token'],
            'ALARM_WINDOW_CHANGED_BEFORE_INPUT')
        self.reader.read(original_digest=True)
        if label in ('label-save', 'alarm-delete', 'expand-owned'):
            bound = self.assert_owned_row_if_main(label)
            if label == 'alarm-delete':
                need(any(node_identity(n) == node_identity(fresh[0]) for n in bound['children']),
                    'DELETE_CONTROL_LEFT_OWNED_ROW')
        if label == 'unlabelled-delete':
            bound = self.row(False)
            need(any(node_identity(n) == node_identity(fresh[0]) for n in bound['children']),
                'UNLABELLED_DELETE_CONTROL_LEFT_OWNED_ROW')
        if empty_field:
            self.label_editor()
        request = {'op': op, 'expected_package': PACKAGE, 'selector': selector,
            'display': 0, 'accessibility_mode': 'none'}
        if op == 'click':
            request['method'] = 'mouse' if mouse else 'accessibility'
        else:
            request['value'] = value
        self.actions += 1
        ident = 'a%02d-' % self.actions + label
        self.pending = ident
        effect = {'create-alarm-save': 'create', 'label-save': 'label',
            'alarm-delete': 'delete', 'unlabelled-delete': 'delete'}.get(label)
        if effect is not None:
            self.effect_pending = {'operation': effect, 'native_request_id': ident,
                'owned_alarm_id': self.reader.alarm_id, 'expected_marker': self.m.MARKER,
                'target': copy.deepcopy(self.reader.target)}
        self.t.record('intent-' + ident, {'native_request': request, 'observed_node': node,
            'wm_focus': focus, 'owned_alarm_id': self.reader.alarm_id,
            'database_effect_intent': copy.deepcopy(self.effect_pending), 'automatic_retry': False})
        self.t.s.guard()
        try:
            response = self.t.s.helper.ui(request)
        except BaseException as error:
            details = getattr(error, 'details', {})
            self.t.record('response-error-' + ident, {'error': type(error).__name__ + ': ' + str(error),
                'details': details, 'automatic_retry': False})
            if details.get('outcome_unknown') is False and details.get('accessibility_mode_restoration_verified') is True:
                self.r.setdefault('explicit_no_effect_inputs', []).append(ident)
                if self.effect_pending is not None:
                    need(self.effect_pending['native_request_id'] == ident, 'DATABASE_EFFECT_OWNER_CHANGED')
                    self.effect_pending = None
                self.pending = None
            raise
        self.t.s.guard()
        self.t.record('response-' + ident, response)
        need(response.get('ok') is True and response.get('performed') == op
            and response.get('outcome_unknown') is not True
            and response.get('accessibility_mode_restoration_verified') is True, 'ALARM_NATIVE_ACK_UNKNOWN')
        if op == 'click':
            need(isinstance(response.get('target'), dict) and isinstance(response.get('actual_target'), dict)
                and self.matches(response['target'], selector) and self.matches(response['actual_target'], selector),
                'ALARM_NATIVE_TARGET_DIFFERS')
        else:
            need(response.get('readback_verified') is True and response.get('password') is False
                and response.get('characters') == len(value), 'ALARM_TEXT_READBACK_UNVERIFIED')
        self.pending = None
        self.r.setdefault('acknowledged_inputs', []).append({'id': ident, 'op': op, 'label': label})
        if observe_after:
            self.observe('after-' + ident)
        return ident

    def complete_effect(self, operation, readback):
        need(self.pending is None and self.effect_pending is not None
            and self.effect_pending['operation'] == operation, 'DATABASE_EFFECT_COMPLETION_ORDER_INVALID')
        self.t.record('database-effect-' + self.effect_pending['native_request_id'], {
            'original_intent': self.effect_pending, 'exact_readback': readback,
            'native_ACK_alone_is_not_completion': True})
        self.effect_pending = None

    def tab(self):
        node = self.unique(lambda n: n.get('class') == 'android.widget.LinearLayout'
            and n.get('content-desc') == 'Alarm' and n.get('text') == '', 'ONE_ACTUAL_ALARM_TAB_REQUIRED')
        if node.get('selected') is not True:
            self.native('alarm-tab', node)
        selected = self.unique(lambda n: n.get('class') == 'android.widget.LinearLayout'
            and n.get('content-desc') == 'Alarm' and n.get('selected') is True,
            'ALARM_TAB_SELECTION_UNVERIFIED')
        need(self.t.last_observation['screenshot']['scope']['activity'] == MAIN,
            'ALARM_TAB_REQUIRES_MAIN_ACTIVITY')
        return selected

    def settle_notice(self):
        for index in range(4):
            if not any(n.get('resource-id') == PACKAGE + ':id/snackbar_text' for n in self.visible()):
                return
            need(index < 3, 'ACTUAL_TRANSIENT_NOTICE_DID_NOT_SETTLE')
            self.observe('notice-%02d-%d' % (self.actions, index))

    def launch(self, label):
        need(self.t.owned is None and self.pending is None and self.close_pending is None
            and self.effect_pending is None and len(self.native_tasks) < 2
            and time.monotonic() < self.end, 'CLOCK_LAUNCH_BUDGET_OR_PENDING')
        count = self.t.launches
        self.pending = 'launch-' + label
        try:
            self.t.launch()
        except BaseException:
            if self.t.launches == count:
                self.pending = None
            raise
        self.native_tasks.append(self.t.owned[0])
        self.pending = None
        self.observe(label)
        self.tab()
        self.settle_notice()

    def close(self):
        if self.t.owned is None:
            return
        need(self.pending is None, 'ALARM_CLOSE_BLOCKED_BY_UNKNOWN_INPUT')
        need(self.close_pending is None, 'ALARM_CLOSE_ALREADY_UNRESOLVED')
        need(self.effect_pending is None, 'ALARM_CLOSE_BLOCKED_BY_UNRESOLVED_DATABASE_EFFECT')
        task = self.t.owned[0]
        before = self.t.removals
        self.close_pending = task
        self.t.close()
        if self.t.removals == before + 1:
            need(self.t.result.get('other_tasks_preserved') is True, 'OWNED_NORMAL_CLOSE_NOT_VERIFIED')
            self.normal_closed.append(task)
        else:
            need(task == self.alert_task and self.dismiss_ack, 'UNEXPLAINED_OWNED_TASK_DISAPPEARANCE')
            self.self_finished.append(task)
        self.close_pending = None

    def row(self, labelled=True):
        anchors = ([self.unique(lambda n: n.get('text') == self.m.MARKER
                    and n.get('editable') is False, 'EXACT_OWNED_ALARM_LABEL_NOT_UNIQUE')]
            if labelled else [self.unique(lambda n: n.get('resource-id') == self.ids['onoff']
                    and n.get('checked') is True, 'SOLE_NEW_ENABLED_ALARM_SWITCH_REQUIRED')])
        containers = []
        for node in self.visible():
            if (node.get('class') not in ('android.widget.LinearLayout', 'android.widget.RelativeLayout',
                    'android.widget.FrameLayout', 'android.view.ViewGroup')
                    or node.get('window_id') != anchors[0].get('window_id')
                    or not all(contains(node.get('bounds_array'), a.get('bounds_array')) for a in anchors)):
                continue
            children = [n for n in self.visible() if n.get('window_id') == node.get('window_id')
                and contains(node['bounds_array'], n.get('bounds_array'))]
            clocks = [n for n in children if n.get('resource-id') == self.ids['clock']]
            switches = [n for n in children if n.get('resource-id') == self.ids['onoff']]
            expanded = not labelled or anchors[0].get('resource-id') == self.ids['label']
            if expanded and (sum(n.get('resource-id') == self.ids['label'] for n in children) != 1
                or sum(n.get('resource-id') == self.ids['delete'] for n in children) != 1):
                continue
            if len(clocks) == len(switches) == 1:
                containers.append((node, children, clocks[0], switches[0]))
        minimal = [item for item in containers if not any(other is not item
            and other[0]['bounds_array'] != item[0]['bounds_array']
            and contains(item[0]['bounds_array'], other[0]['bounds_array']) for other in containers)]
        need(len(minimal) == 1, 'OWNED_ALARM_ROW_CONTAINER_AMBIGUOUS')
        row, children, clock, switch = minimal[0]
        fields = [int(v) for v in re.findall(r'[0-9]+', clock.get('text', ''))]
        expected = self.reader.target
        need(fields in ([expected['hour'], expected['minutes']], [expected['hour'] % 12 or 12, expected['minutes']]),
            'OWNED_ALARM_ROW_TIME_DIFFERS')
        if not labelled:
            need(switch.get('checked') is True, 'NEW_ALARM_ROW_SWITCH_NOT_ENABLED')
        return {'container': row, 'children': children, 'clock': clock, 'switch': switch, 'anchor': anchors[0]}

    def assert_owned_row_if_main(self, label):
        if label == 'label-save':
            self.label_editor()
            return
        need(self.t.last_observation['screenshot']['scope']['activity'] == MAIN,
            'OWNED_TEMPLATE_ACTION_REQUIRES_MAIN')
        current = self.reader.read()
        need(current['alarm']['label'] == self.m.MARKER, 'MARKED_TEMPLATE_REQUIRED_FOR_ROW_ACTION')
        return self.row(True)

    def expanded(self, labelled=True):
        row = self.row(labelled)
        deletes = [n for n in row['children'] if n.get('resource-id') == self.ids['delete']]
        if not deletes and labelled:
            need(row['anchor'].get('resource-id') != self.ids['label'], 'EXPANDED_LABEL_IS_NOT_ROW_EXPAND_CONTROL')
            self.native('expand-owned', row['anchor'], mouse=True)
            row = self.row(True)
            deletes = [n for n in row['children'] if n.get('resource-id') == self.ids['delete']]
        need(len(deletes) == 1 and deletes[0].get('clickable') is True, 'OWNED_EXPANDED_DELETE_REQUIRED')
        return row, deletes[0]

    def label_editor(self):
        need(self.t.last_observation['screenshot']['scope']['activity'] == MAIN,
            'ALARM_LABEL_DIALOG_ACTIVITY_CHANGED')
        self.unique(lambda n: n.get('text') == self.texts['label_message']
            and n.get('editable') is False, 'ACTUAL_ALARM_LABEL_DIALOG_MESSAGE_REQUIRED')
        return self.unique(lambda n: n.get('editable') is True and n.get('password') is False,
            'ONE_ALARM_LABEL_EDITOR_REQUIRED')

    def poll_read(self, label, predicate, claim=False, seconds=5):
        deadline = min(self.end, time.monotonic() + seconds)
        errors = []
        while time.monotonic() < deadline:
            try:
                value = self.reader.read(claim=claim and self.reader.alarm_id is None)
                if predicate(value):
                    self.r['phases'][label] = value
                    self.t.record(label, value)
                    return value
            except RuntimeError as error:
                if str(error) not in ('ONE_NEW_ALARM_REQUIRED', 'NEW_ENABLED_UNLABELLED_ALARM_REQUIRED',
                        'OWNED_INSTANCE_CONTRACT_CHANGED', 'ALARM_SUMMARY_TEMPORARILY_INCONSISTENT'):
                    raise
                errors.append(str(error))
            time.sleep(.25)
        self.t.record(label + '-readback-unresolved', {'transient_read_errors': errors})
        raise RuntimeError('ACKNOWLEDGED_ALARM_EFFECT_NOT_READ_BACK_' + label)

    def create(self):
        add = self.unique(lambda n: n.get('clickable') is True and n.get('editable') is False
            and n.get('content-desc') == self.texts['add'], 'ACTUAL_ADD_ALARM_CONTROL_REQUIRED')
        self.native('open-time-picker', add)
        fields = [n for n in self.visible() if n.get('resource-id') == 'android:id/input_hour' and n.get('editable') is True]
        if not fields:
            toggle = self.unique(lambda n: n.get('resource-id') == 'android:id/toggle_mode'
                and n.get('clickable') is True and n.get('content-desc') == 'Switch to text input mode for the time input.',
                'OBSERVED_TIME_PICKER_TEXT_MODE_REQUIRED')
            self.native('time-text-mode', toggle)
        self.by_id('android:id/input_hour', True)
        self.by_id('android:id/input_minute', True)
        now = self.reader.zone_unchanged()
        self.reader.target = self.m.target_time(now)
        self.r['target'] = self.reader.target
        self.t.record('new-alarm-target', {'now': now, 'target': self.reader.target, 'time_writes': 0})
        period = [n for n in self.visible() if n.get('text') in ('AM', 'PM') and
            (n.get('selected') is True or n.get('checked') is True or n.get('resource-id') == 'android:id/text1')]
        twelve = bool(period)
        if twelve:
            need(len(period) == 1 and period[0]['text'] == ('AM' if self.reader.target['hour'] < 12 else 'PM'),
                'TIME_PICKER_AM_PM_CHANGE_REQUIRES_OBSERVED_ROUTE')
        else:
            need(not any(n.get('resource-id') == 'android:id/am_pm_spinner' for n in self.visible()),
                'TIME_PICKER_PERIOD_UNREADABLE')
        hour = (self.reader.target['hour'] % 12 or 12) if twelve else self.reader.target['hour']
        self.native('set-alarm-hour', self.by_id('android:id/input_hour', True), 'set-text', str(hour))
        self.native('set-alarm-minute', self.by_id('android:id/input_minute', True), 'set-text', str(self.reader.target['minutes']))
        need(self.by_id('android:id/input_hour', True).get('text') in (str(hour), '%02d' % hour)
            and self.by_id('android:id/input_minute', True).get('text') in
                (str(self.reader.target['minutes']), '%02d' % self.reader.target['minutes']),
            'TIME_PICKER_TYPED_TIME_NOT_READ_BACK')
        self.reader.pristine()
        now = self.reader.zone_unchanged()
        need(150 <= self.reader.target['epoch_seconds'] - now['epoch_seconds'] <= 240,
            'INSUFFICIENT_NEW_ALARM_DEADLINE_BEFORE_SAVE')
        save = self.by_id('android:id/button1')
        need(save.get('text', '').casefold() == 'ok' and save.get('clickable') is True,
            'TIME_PICKER_CONFIRM_NOT_OBSERVED')
        self.native('create-alarm-save', save, observe_after=False)
        self.create_ack = True
        created = self.poll_read('created-unlabelled', lambda v: v['alarm'] is not None, claim=True)
        self.complete_effect('create', created)
        self.observe('created-new-template')
        self.settle_notice()
        row, _ = self.expanded(False)
        labels = [n for n in row['children'] if n.get('resource-id') == self.ids['label']
            and n.get('text') == '' and n.get('content-desc') == self.texts['label_description']]
        need(len(labels) == 1, 'NEW_TEMPLATE_LABEL_CONTROL_NOT_BOUND')
        self.native('open-alarm-label', labels[0])
        editor = self.label_editor()
        need(not editor.get('text') and not editor.get('hint'), 'NEW_ALARM_LABEL_IS_NOT_EMPTY')
        self.native('set-alarm-label', editor, 'set-text', self.m.MARKER, empty_field=True)
        need(self.label_editor().get('text') == self.m.MARKER, 'OWNED_LABEL_TEXT_NOT_READ_BACK')
        save = self.by_id('android:id/button1')
        need(save.get('text', '').casefold() == 'ok', 'LABEL_CONFIRM_NOT_OBSERVED')
        self.native('label-save', save, observe_after=False)
        self.label_ack = True
        self.poll_read('created-labelled', lambda v: v['alarm']['label'] == self.m.MARKER
            and len(v['instances']) == 1 and v['instances'][0]['label'] == self.m.MARKER)
        self.r['phases']['frozen-created'] = self.reader.freeze_labelled()
        self.complete_effect('label', self.r['phases']['frozen-created'])
        self.r['owned_alarm_id'] = self.reader.alarm_id
        self.r['owned_instance_id'] = self.reader.instance['_id']
        self.r['owned_instance_uri'] = 'content://com.android.deskclock/instances/' + str(self.reader.instance['_id'])
        self.observe('labelled-template')
        self.row(True)

    def evidence(self, label):
        self.reader.read()
        result = {'observed_utc': stamp(), 'commands': {}}
        for kind, argv in (
            ('scheduler', ['/system/bin/dumpsys', 'alarm']),
            ('services', ['/system/bin/dumpsys', 'activity', 'services', PACKAGE]),
            ('notifications', ['/system/bin/dumpsys', 'notification', '--noredact', '--package', PACKAGE]),
        ):
            raw = self.t.s.android(argv, 12)
            path = ROOT / (label + '-' + kind + '-private.txt')
            self.t.tx.write_new(path, raw)
            item = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'private_path': str(path)}
            if kind == 'scheduler':
                item['clock_uid_current_pending_alarm_count'] = alarm_pending_count(raw.decode())
            elif kind == 'notifications':
                item['alarm_record'] = active_alarm_record(raw.decode(), self.m.MARKER)
            result['commands'][kind] = item
        self.r.setdefault('runtime_evidence', {})[label] = result
        return result

    def wait_fired(self):
        samples = []
        while time.monotonic() < self.end - 80:
            now = self.reader.zone_unchanged()
            value = self.reader.read(original_digest=False)
            need(value['alarm']['label'] == self.m.MARKER and value['alarm']['enabled'] == 1
                and len(value['instances']) == 1, 'SCHEDULED_OWNED_ALARM_CHANGED')
            state = value['instances'][0]['alarm_state']
            samples.append({'epoch_seconds': now['epoch_seconds'], 'state': state})
            if state == 5:
                need(self.reader.target['epoch_seconds'] - 1 <= now['epoch_seconds'] <= self.reader.target['epoch_seconds'] + 30,
                    'ALARM_FIRED_OUTSIDE_OWN_DUE_WINDOW')
                self.r['phases']['fired'] = value
                self.r['actual_firing_verified'] = True
                self.r['firing_samples'] = samples
                return
            if now['epoch_seconds'] > self.reader.target['epoch_seconds'] + 30:
                break
            need(state in (0, 1, 2, 3, 4), 'OWNED_ALARM_CHANGED_TO_NON_FIRING_TERMINAL_STATE')
            time.sleep(2)
        self.r['firing_samples'] = samples
        raise RuntimeError('OWNED_ALARM_DID_NOT_FIRE_WITHIN_DUE_PLUS_30_SECONDS')

    def claim_alert(self):
        need(self.reader.instance is not None and self.t.owned is None and self.pending is None,
            'ALERT_OWNERSHIP_PRECONDITION')
        value = self.reader.read()
        need(len(value['instances']) == 1 and value['instances'][0]['alarm_state'] == 5,
            'ALERT_REQUIRES_THIS_FIRED_INSTANCE')
        roots, tasks = self.topology('possible-alarm-alert')
        extra = tasks - self.baseline
        need(len(extra) == 1, 'ACTUAL_ALARM_ALERT_NOT_ONE_NEW_TASK')
        task = next(iter(extra)); root = roots.get(task)
        need(root and root['display'] == root['user'] == 0 and len(root['children']) == 1
            and root['children'][0]['id'] == task and root['children'][0]['user'] == 0,
            'ALERT_MUST_BE_ONE_NEW_EXACT_ROOT_LEAF')
        component = root['children'][0]['component']
        need(component.split('/')[0] == PACKAGE and activity(component.split('/', 1)[1]) == ALERT,
            'NEW_TASK_IS_NOT_ALARM_ACTIVITY')
        raw = self.t.s.android(['/system/bin/dumpsys', 'activity', 'activities', PACKAGE], 12)
        self.t.tx.write_new(ROOT / 'alert-activity-private.txt', raw)
        blocks = re.split(r'(?=^\s*\* Hist #\d+: ActivityRecord\{)', raw.decode(), flags=re.M)
        matches = [b for b in blocks if re.search(r'^\s*\* Hist #\d+: ActivityRecord\{[^\n]*\bu0 '
            + re.escape(component) + r' t' + str(task) + r'\b', b)]
        uri = self.r['owned_instance_uri']
        need(len(matches) == 1 and re.search(r'Intent \{[^\n]*\bdat=' + re.escape(uri) + r'(?:\s|\})', matches[0]),
            'ALERT_INTENT_NOT_BOUND_TO_EXACT_OWNED_INSTANCE')
        self.alert_task = task
        self.alert_binding = {'task': task, 'component': component, 'uri': uri,
            'activity_dump_sha256': hashlib.sha256(raw).hexdigest(), 'automatically_created': True}
        self.t.owned = (task, set(self.baseline))
        self.r['alert_binding'] = self.alert_binding
        self.observe('actual-alarm-alert')
        title = self.by_id(self.ids['alert_title'])
        need(title.get('text') == self.m.MARKER, 'ALERT_TITLE_NOT_OWNED_MARKER')
        self.r['actual_alarm_window_observed'] = True

    def dismiss(self):
        node = self.by_id(self.ids['dismiss'])
        need(node.get('content-desc', '').casefold() in ('dismiss', 'dismiss alarm')
            and node.get('clickable') is True, 'ACTUAL_ALARM_DISMISS_CONTROL_REQUIRED')
        ident = self.native('dismiss-alarm-once', node, observe_after=False)
        self.dismiss_ack = True
        self.r['dismiss_path'] = {'native_request_id': ident, 'accessibility_mode': 'none',
            'source_condition': 'isEnabled && (isTouchExplorationEnabled || enabled FEEDBACK_GENERIC service)',
            'source_condition_runtime_value_not_assumed': True, 'hint_is_not_dismissal': True}
        value = self.poll_read('dismissed', lambda v: v['alarm']['enabled'] == 0 and not v['instances'], seconds=8)
        need(value['alarm']['label'] == self.m.MARKER, 'DISMISS_CHANGED_OWNED_TEMPLATE_LABEL')
        self.r['actual_dismiss_effect_verified'] = True
        self.close()

    def delete(self, cleanup=False):
        need(self.reader.alarm_id is not None and self.pending is None
            and self.effect_pending is None and not self.delete_ack,
            'DELETE_ONLY_ONCE_FOR_OWNED_TEMPLATE')
        if self.t.owned is None:
            self.launch('cleanup-main' if cleanup else 'reopen-persisted-alarm')
        value = self.reader.read()
        if not cleanup:
            need(value['alarm']['enabled'] == 0 and value['instances'] == []
                and value['alarm'] == self.r['phases']['dismissed']['alarm'], 'REOPEN_CHANGED_DISMISSED_ALARM')
            self.reader.zone_unchanged()
            self.r['phases']['reopened'] = value
            self.r['normal_close_reopen_time_and_timezone_preserved'] = True
        self.observe('own-template-before-delete')
        self.settle_notice()
        labelled = value['alarm']['label'] == self.m.MARKER
        need(labelled or (cleanup and self.create_ack and not self.label_ack
            and value['alarm']['label'] == '' and value['alarm']['enabled'] == 1),
            'DELETE_TEMPLATE_LABEL_NOT_OWNED')
        row, node = self.expanded(labelled)
        need(node.get('text', '').casefold() == 'delete' or node.get('content-desc', '').casefold() in ('delete', 'delete alarm'),
            'ACTUAL_TEMPLATE_DELETE_SEMANTICS_REQUIRED')
        # Unlabelled cleanup still uses the proven one new enabled row; it is
        # never a generic Delete selector detached from that row.
        label = 'alarm-delete' if labelled else 'unlabelled-delete'
        self.native(label, node, observe_after=False)
        self.delete_ack = True
        until = min(self.end, time.monotonic() + 8)
        while time.monotonic() < until:
            summary = self.reader.summary()
            if summary['template_ids'] == self.m.ORIGINAL_IDS and summary['instance_ids'] == []:
                self.r['phases']['deleted'] = self.reader.deleted()
                self.complete_effect('delete', self.r['phases']['deleted'])
                self.r['exact_owned_alarm_deleted'] = True
                return
            time.sleep(.25)
        raise RuntimeError('ACKNOWLEDGED_OWNED_DELETE_NOT_READ_BACK')

    def run(self):
        self.r['phases']['before'] = self.reader.pristine()
        self.launch('initial-main')
        self.create()
        self.evidence('created')
        self.close()
        self.r['phases']['after-normal-close'] = self.reader.read()
        self.reader.zone_unchanged()
        self.evidence('after-normal-close')
        self.wait_fired()
        fired = self.evidence('fired')
        self.r['actual_alarm_notification_posted'] = fired['commands']['notifications']['alarm_record'].get(
            'source_bound_marker_and_fullscreen_intent') is True
        need(self.r['actual_alarm_notification_posted'], 'FIRED_NOTIFICATION_NOT_YET_PROVEN')
        self.claim_alert()
        self.dismiss()
        self.delete()
        self.close()
        self.r['state'] = 'OWNED_ALARM_FIRED_DISMISSED_REOPENED_DELETED'

    def cleanup(self, cleanup_until):
        self.r['cleanup'] = {'original_failure_retained': True, 'new_inputs': 0,
            'pending_retained': self.pending, 'close_pending_retained': self.close_pending,
            'database_effect_pending_retained': self.effect_pending,
            'SQL_or_provider_fallback': False}
        self.end = cleanup_until - 15
        before = self.actions
        if self.pending is not None or self.close_pending is not None or self.effect_pending is not None:
            self.r['cleanup']['state'] = ('UNKNOWN_CLOSE_RETAINED_READ_ONLY' if self.close_pending is not None
                else 'UNRESOLVED_DATABASE_EFFECT_RETAINED_READ_ONLY' if self.effect_pending is not None
                else 'UNKNOWN_INPUT_RETAINED_READ_ONLY')
            self.r['cleanup']['summary_at_read'] = self.reader.summary()
            return
        if self.reader.alarm_id is None:
            self.reader.pristine()
            self.r['cleanup']['no_alarm_created'] = True
            return
        if self.delete_ack:
            self.r['cleanup']['final_read'] = self.reader.deleted()
            return
        value = self.reader.read()
        # A known native Dismiss ACK without its effect may only have shown the
        # hint. Preserve failure, remove only its exact owned alert task, then
        # use the app's Delete callback (which cancels instances before delete).
        if self.t.owned and self.t.owned[0] == self.alert_task:
            self.close()
        if self.t.owned:
            self.observe('cleanup-current-owned-window')
            editable = [n for n in self.visible() if n.get('editable') is True]
            if editable:
                self.label_editor()
                cancel = self.by_id('android:id/button2')
                need(cancel.get('text', '').casefold() == 'cancel', 'CLEANUP_DIALOG_CANCEL_NOT_OBSERVED')
                self.native('cancel-owned-label-dialog', cancel)
        self.delete(cleanup=True)
        self.r['cleanup'].update(new_inputs=self.actions - before, exact_template_removed=True)


def deadline(*unused):
    raise TimeoutError('OWNED_ALARM_LEASE_EXPIRED_NO_REPLAY')


def execute():
    modules = {name: load(*pair) for name, pair in PINS.items()}
    base, model, reader, timer, installer = [modules[name] for name in ('base', 'model', 'reader', 'timer', 'installer')]
    tx = model.load_session()
    need(model.SOURCE_SHA == 'b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
        and tx.ACTIVATION_SHA == '7e490c14586d891f6b121341f879f41c955414c9122e3a68053f04665c12e615',
        'ALARM_REQUIRES_FROZEN_ORIGINAL_12288_PROFILE')
    base.PACKAGE, base.COMPONENT, base.ROOT = PACKAGE, PACKAGE + '/.DeskClock', ROOT
    base.SOURCE, base.SOURCE_SHA = model.SOURCE, model.SOURCE_SHA
    result = {'state': 'FAILED', 'started_utc': stamp(), 'phases': {}, 'source_pins': PINS,
        'business_success_verified': False, 'whole_app_production_ready': False,
        'automatic_retry': False, 'maximum_new_alarms': 1, 'maximum_inputs': MAX_INPUTS,
        'work_seconds': WORK_SECONDS, 'cleanup_seconds': CLEANUP_SECONDS,
        'SQL_write_commands': 0, 'provider_write_commands': 0, 'setting_changes': 0,
        'global_volume_or_ringtone_changes': 0, 'native_accessibility_policy_changes': 0,
        'physical_audio_qualification': False, 'desktop_popup_qualification': False}
    prior = signal.signal(signal.SIGALRM, deadline)
    flow = trial = None
    cleanup_until = None
    try:
        with tx.ui_lock():
            ROOT.mkdir(mode=0o700)
            signal.setitimer(signal.ITIMER_REAL, WORK_SECONDS)
            with tx.CameraSession(ROOT / 'commands') as session:
                before = installer.snapshot(session, tx, model, timer, 'before')
                result['protected_before'] = before
                result['identity_before'] = model.identity(session)
                result['epoch_sha256'] = session.epoch_sha256
                need(result['identity_before']['notifications_granted'], 'CLOCK_NOTIFICATION_PERMISSION_REQUIRED')
                native_path = session.android(['/system/bin/pm', 'path', 'local.pocket4.actions.v2']).decode().splitlines()
                need(len(native_path) == 1 and native_path[0].startswith('package:/data/app/'), 'ACTUAL_NATIVE_RUNNER_PATH_REQUIRED')
                native, _ = session.target.read_file(native_path[0][8:], 128 * 1024)
                need(len(native) == 20847 and hashlib.sha256(native).hexdigest() == NATIVE_SHA,
                    'ACTUAL_NATIVE_ACTION_CONTRACT_CHANGED')
                apk, _ = session.target.read_file(model.APK_PATH, 16 * 1024 * 1024)
                need(hashlib.sha256(apk).hexdigest() == model.APK_SHA, 'CLOCK_RESOURCE_APK_CHANGED')
                resources = reader.resource_contract(apk)
                result['actual_resource_contract'] = resources
                trial = base.Trial(session, tx)
                flow = Flow(trial, base, model, reader, result, resources)
                try:
                    flow.run()
                    result['business_success_verified'] = True
                except BaseException as error:
                    result.update(state='FAILED', error=type(error).__name__ + ': ' + str(error))
                    cleanup_until = time.monotonic() + CLEANUP_SECONDS
                    signal.setitimer(signal.ITIMER_REAL, max(.001, cleanup_until - time.monotonic()))
                    try:
                        flow.evidence('failure')
                    except BaseException as observed:
                        result['failure_evidence_error'] = type(observed).__name__ + ': ' + str(observed)
                    try:
                        flow.cleanup(cleanup_until)
                    except BaseException as cleanup:
                        result['cleanup_error'] = type(cleanup).__name__ + ': ' + str(cleanup)
                finally:
                    if cleanup_until is None:
                        cleanup_until = time.monotonic() + CLEANUP_SECONDS
                    signal.setitimer(signal.ITIMER_REAL, max(.001, cleanup_until - time.monotonic()))
                    try:
                        if flow.pending is None and flow.close_pending is None and flow.effect_pending is None:
                            flow.close()
                        else:
                            result['final_actions_blocked_by_unknown'] = {
                                'input': flow.pending, 'close': flow.close_pending,
                                'database_effect': flow.effect_pending, 'read_only': True}
                        result['final_alarm_readback'] = flow.reader.deleted()
                        final = flow.evidence('final')
                        need(final['commands']['scheduler']['clock_uid_current_pending_alarm_count'] == 0,
                            'CLOCK_SCHEDULER_PENDING_AFTER_CLEANUP')
                        need(final['commands']['notifications']['alarm_record']['present'] is False,
                            'ALARM_NOTIFICATION_REMAINS_AFTER_CLEANUP')
                        result['protected_after'] = installer.snapshot(session, tx, model, timer, 'after')
                        result['identity_after'] = model.identity(session)
                        need(result['identity_before'] == result['identity_after']
                            and installer.preserved(before, result['protected_after'], include_preferences=False),
                            'PROTECTED_CLOCK_STATE_CHANGED')
                        roots, tasks = flow.topology('final-owned-alarm-tasks')
                        need(tasks == flow.baseline and roots == flow.baseline_roots, 'ALARM_TASK_SET_NOT_RESTORED')
                        result['task_set_restored'] = True
                        result['empty_alarm_state_at_final_read'] = True
                        result['owned_alarm_cleanup_verified'] = (flow.pending is None and flow.close_pending is None
                            and flow.effect_pending is None)
                        session.caller_status('alarm-final-caller')
                    except BaseException as final:
                        result['final_guard_error'] = type(final).__name__ + ': ' + str(final)
    except BaseException as error:
        result.update(state='FAILED', outer_error=type(error).__name__ + ': ' + str(error))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, prior)
        if flow is not None:
            result.update(UI_actions=flow.actions, pending_effect=flow.pending, close_pending=flow.close_pending,
                pending_database_effect=flow.effect_pending,
                native_dispatch_attempts=flow.actions, acknowledged_input_count=len(result.get('acknowledged_inputs', [])),
                native_launched_tasks=flow.native_tasks, normally_closed_tasks=flow.normal_closed,
                alert_self_finished_tasks=flow.self_finished, owned_task_remaining=trial.owned,
                creation_native_ACK=flow.create_ack, label_native_ACK=flow.label_ack,
                dismiss_native_ACK=flow.dismiss_ack, delete_native_ACK=flow.delete_ack)
        complete = bool(result.get('business_success_verified') and result.get('actual_firing_verified')
            and result.get('actual_alarm_notification_posted') and result.get('actual_alarm_window_observed')
            and result.get('actual_dismiss_effect_verified') and result.get('normal_close_reopen_time_and_timezone_preserved')
            and result.get('exact_owned_alarm_deleted') and result.get('owned_alarm_cleanup_verified')
            and flow is not None and flow.pending is None and flow.close_pending is None and flow.effect_pending is None
            and len(flow.native_tasks) == 2 and all(task in flow.normal_closed for task in flow.native_tasks)
            and flow.alert_task in flow.normal_closed + flow.self_finished
            and not result.get('final_guard_error') and not result.get('cleanup_error') and not result.get('outer_error'))
        result['business_success_verified'] = complete
        if not complete:
            result['state'] = 'FAILED'
        result['finished_utc'] = stamp()
        if ROOT.is_dir():
            tx.write_new(ROOT / 'result.json', result, alex_readable=True)
        print(json.dumps({key: result.get(key) for key in ('state', 'error', 'outer_error', 'final_guard_error',
            'business_success_verified', 'UI_actions', 'pending_effect', 'pending_database_effect', 'owned_alarm_id',
            'native_launched_tasks', 'normally_closed_tasks', 'owned_alarm_cleanup_verified')}, sort_keys=True))
    return 0 if result['business_success_verified'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    if parser.parse_args().execute:
        raise SystemExit(execute())
    print(json.dumps({'state': 'PLAN_ONLY', 'UI_actions': 0, 'alarm_writes': 0,
        'work_seconds': WORK_SECONDS, 'cleanup_seconds': CLEANUP_SECONDS,
        'maximum_new_alarm': 1, 'maximum_native_inputs': MAX_INPUTS, 'source_pins': PINS}))
