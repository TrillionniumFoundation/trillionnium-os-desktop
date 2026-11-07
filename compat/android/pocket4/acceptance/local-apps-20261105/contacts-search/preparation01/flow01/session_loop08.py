#!/usr/bin/python3 -I
"""Private JSONL continuation of the frozen Contacts Trial; inert by default."""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import os
import re
import signal
import sys
import types

ADAPTER_SHA = '2e99a4d0b2a9f4be7046c3504ec65d754bd91c959cb0f4f1adfe873aa3a16237'
TRANSPORT_SHA = 'b2274355ea9acc9d3f82f4e245dceef01aae86e689221744f0fb2afaff679470'
FIELDS = {'id': 'resource-id', 'text': 'text', 'desc': 'content-desc', 'class': 'class',
          'focused': 'focused', 'editable': 'editable'}
NODE_KEYS = tuple(FIELDS.values()) + ('package', 'hint', 'bounds_array', 'enabled', 'visible', 'clickable', 'password')


def require(value, reason):
    if not value:
        raise RuntimeError(reason)

def emit(value):
    print(json.dumps(value, ensure_ascii=True, separators=(',', ':')), flush=True)

def expired(signum, frame):
    raise TimeoutError('SESSION_LEASE_EXPIRED_NO_ACTION_REPLAY')


def candidates(nodes, selector, package):
    require(isinstance(selector, dict) and selector and not set(selector) - set(FIELDS), 'EXACT_SELECTOR_REQUIRED')
    require(any(k in selector for k in ('id', 'text', 'desc')), 'SEMANTIC_IDENTITY_REQUIRED')
    for key, value in selector.items():
        require(type(value) is bool if key in ('focused', 'editable') else
                isinstance(value, str) and 0 < len(value.encode()) <= 4096, 'SELECTOR_VALUE_INVALID')
    return [n for n in nodes if n.get('package') == package and n.get('visible') is True
            and n.get('enabled') is True and all(n.get(FIELDS[k]) == v for k, v in selector.items())]

def node_identity(node):
    return {key: node.get(key) for key in NODE_KEYS}


def post_capture_only(response, acknowledgements, op):
    """The exact installed helper's successful native-click/post-capture split."""
    if op != 'click' or len(acknowledgements) != 1:
        return False
    ack = acknowledgements[0]
    return (ack.get('ok') is True and ack.get('performed') == 'click'
            and ack.get('outcome_unknown') is not True
            and ack.get('accessibility_mode_restoration_verified') is True
            and isinstance(ack.get('target'), dict) and isinstance(ack.get('actual_target'), dict)
            and response.get('ok') is True and response.get('performed') == 'click'
            and response.get('outcome_unknown') is True
            and response.get('post_action_observation_available') is False)


def device_label_container(nodes, label, package):
    if not (package == 'com.android.settings'
            and label.get('resource-id') == 'android:id/title'
            and label.get('text') == 'Device only'
            and label.get('class') == 'android.widget.TextView'):
        return None
    return clickable_container(nodes, label, package)


def clickable_container(nodes, label, package):
    bounds = label.get('bounds_array')
    require(isinstance(bounds, list) and len(bounds) == 4
            and all(type(x) is int for x in bounds), 'DEVICE_LABEL_BOUNDS_INVALID')
    containers = []
    for node in nodes:
        box = node.get('bounds_array')
        if (node.get('package') == package and node.get('window_id') == label.get('window_id')
                and node.get('visible') is True and node.get('enabled') is True
                and node.get('clickable') is True and isinstance(box, list) and len(box) == 4
                and all(type(x) is int for x in box)
                and box[0] <= bounds[0] < bounds[2] <= box[2]
                and box[1] <= bounds[1] < bounds[3] <= box[3]):
            containers.append(node_identity(node))
    require(len(containers) == 1, 'DEVICE_LABEL_CLICKABLE_CONTAINER_NOT_UNIQUE')
    return containers[0]


def owned_contact_list_row(nodes, label, package):
    require(package == 'com.android.contacts' and label.get('package') == package
        and label.get('resource-id') == package + ':id/cliv_name_textview'
        and label.get('class') == 'android.widget.TextView'
        and label.get('text') and label.get('text') == label.get('content-desc')
        and label.get('editable') is False and label.get('password') is False,
        'OWNED_CONTACT_LIST_LABEL_CHANGED')
    bounds = label.get('bounds_array')
    require(isinstance(bounds, list) and len(bounds) == 4 and all(type(x) is int for x in bounds),
        'OWNED_CONTACT_LIST_LABEL_BOUNDS_INVALID')
    def same_window(node):
        return (node.get('package') == package and node.get('window_id') == label.get('window_id')
            and node.get('visible') is True and node.get('enabled') is True)
    def contains(outer, inner):
        return (isinstance(outer, list) and len(outer) == 4 and all(type(x) is int for x in outer)
            and outer[0] <= inner[0] < inner[2] <= outer[2]
            and outer[1] <= inner[1] < inner[3] <= outer[3])
    lists = [n for n in nodes if same_window(n) and n.get('resource-id') == 'android:id/list'
        and n.get('class') == 'android.widget.ListView' and contains(n.get('bounds_array'), bounds)]
    require(len(lists) == 1, 'OWNED_CONTACT_LISTVIEW_NOT_UNIQUE')
    list_box = lists[0]['bounds_array']
    rows = [n for n in nodes if same_window(n) and n.get('class') == 'android.view.ViewGroup'
        and n.get('resource-id') == '' and n.get('clickable') is False
        and contains(n.get('bounds_array'), bounds) and contains(list_box, n['bounds_array'])
        and n['bounds_array'] != list_box]
    require(len(rows) == 1, 'OWNED_CONTACT_LIST_ROW_NOT_UNIQUE')
    return {'kind': 'observed_list_row_touch_no_accessibility_click_claim',
        'list': node_identity(lists[0]), 'row': node_identity(rows[0])}


class Continuation:
    def __init__(self, trial, package):
        self.t, self.package = trial, package
        self.seen, self.latest, self.nodes = {'initial'}, None, []
        self.pending, self.actions = None, 0
        self.approved_labels = set()
        self.approved_contact_names = set()

    def observe(self, label, publish=True):
        focus = self.t.ready_focus(allow_permission=False)
        self.nodes = self.t.observe(label, focus)
        self.package = focus['package']
        self.latest = label
        if publish:
            emit({'id': label, 'state': 'OBSERVED', 'owned_task': self.t.owned[0],
                  'focus': focus, 'nodes': self.nodes, 'screenshot': self.t.last_observation['screenshot']})

    def step(self, request):
        require(isinstance(request, dict) and not set(request) -
                {'id', 'op', 'observation', 'selector', 'value', 'node_index'}, 'REQUEST_SCHEMA_INVALID')
        ident, op = request.get('id'), request.get('op')
        require(isinstance(ident, str) and re.fullmatch('[a-z][a-z0-9-]{0,39}', ident)
                and ident not in self.seen, 'UNIQUE_REQUEST_ID_REQUIRED')
        require(op in ('observe', 'click', 'set-text', 'snapshot-tap', 'close'), 'OP_NOT_ALLOWED')
        self.seen.add(ident)
        self.t.record('request-' + ident, request)
        if op == 'close':
            return False
        if op == 'observe':
            self.observe('view-' + ident)
            return True
        require(request.get('observation') == self.latest and self.pending is None, 'LATEST_OBSERVATION_REQUIRED')
        selector = request.get('selector')
        old = candidates(self.nodes, selector, self.package)
        index = request.get('node_index', 0)
        require(type(index) is int and 0 <= index < len(old), 'OBSERVED_NODE_INDEX_INVALID')
        require((op == 'snapshot-tap') or ('node_index' not in request and len(old) == 1), 'UNIQUE_NATIVE_SELECTOR_REQUIRED')
        chosen = old[index]
        contact_list_binding = None
        if (op == 'snapshot-tap' and chosen.get('text') in self.approved_contact_names):
            require(self.t.last_observation['screenshot']['scope']['activity']
                == 'com.android.contacts.activities.PeopleActivity', 'OWNED_LIST_ACTIVITY_CHANGED')
            contact_list_binding = owned_contact_list_row(self.nodes, chosen, self.package)
        label_container = (device_label_container(self.nodes, chosen, self.package)
            if op == 'snapshot-tap' and self.t.storage_from_create is not None else None)
        if (op == 'snapshot-tap' and label_container is None
                and contact_list_binding is None
                and (self.package, chosen.get('resource-id'), chosen.get('text')) in self.approved_labels):
            require(chosen.get('editable') is False and chosen.get('password') is False,
                    'APPROVED_LABEL_MUST_NOT_BE_AN_INPUT')
            label_container = clickable_container(self.nodes, chosen, self.package)
        require(chosen.get('editable') is True and chosen.get('password') is not True
                if op == 'set-text' else chosen.get('clickable') is True or label_container is not None
                or contact_list_binding is not None,
                'CONTROL_NOT_ACTIONABLE')
        previous = self.t.last_observation['screenshot']
        self.observe('fresh-' + ident, publish=False)
        fresh = candidates(self.nodes, selector, self.package)
        require([node_identity(n) for n in old] == [node_identity(n) for n in fresh], 'OBSERVED_CONTROL_CHANGED')
        if contact_list_binding is not None:
            require(self.t.last_observation['screenshot']['scope']['activity']
                == 'com.android.contacts.activities.PeopleActivity'
                and owned_contact_list_row(self.nodes, fresh[index], self.package) == contact_list_binding,
                'OWNED_CONTACT_LIST_ROW_CHANGED')
        if label_container is not None:
            require(clickable_container(self.nodes, fresh[index], self.package) == label_container,
                    'DEVICE_CLICKABLE_CONTAINER_CHANGED')
        current = self.t.last_observation['screenshot']
        require(current['scope']['window_token'] == previous['scope']['window_token'] and
                current['scope']['package'] == previous['scope']['package'] == self.package, 'WINDOW_CHANGED')
        command = {'op': op, 'package': self.package, 'window_token': current['scope']['window_token'],
                   'display': 0, 'accessibility_mode': 'none'}
        if op == 'snapshot-tap':
            bounds = chosen.get('bounds_array')
            require(isinstance(bounds, list) and len(bounds) == 4 and all(type(x) is int for x in bounds)
                    and bounds[0] < bounds[2] and bounds[1] < bounds[3], 'OBSERVED_BOUNDS_REQUIRED')
            for key in ('frame_sha256', 'scope_sha256', 'context_token'):
                require(previous[key] == current[key], 'REVIEWED_SNAPSHOT_CHANGED')
                command[key] = previous[key]
            command.update(coords=[(bounds[0] + bounds[2]) // 2, (bounds[1] + bounds[3]) // 2], input_source='touch')
        else:
            command['selector'] = dict(selector, package=self.package, enabled=True)
            if op == 'click':
                command.update(method='accessibility')
                command['selector']['clickable'] = True
            else:
                value = request.get('value')
                require(isinstance(value, str) and len(value.encode()) <= 4096, 'TEXT_VALUE_INVALID')
                command['value'] = value
                command['selector']['editable'] = True
        # Recheck owned task and foreground immediately before the one dispatch.
        focus = self.t.ready_focus(allow_permission=False)
        require(focus['window_token'] == current['scope']['window_token'], 'FOCUS_CHANGED_BEFORE_ACTION')
        self.t.record('intent-' + ident, {'command': command, 'node': chosen,
            'observed_label_clickable_container': label_container,
            'owned_contact_list_binding': contact_list_binding, 'automatic_retry': False})
        self.pending = ident
        self.actions += 1
        self.t.s.guard()
        original_ui = self.t.s.helper.ui
        native_ack = []
        def record_native(request):
            value = original_ui(request)
            if request.get('op') == op:
                preserved = copy.deepcopy(value)
                native_ack.append(preserved)
                self.t.record('native-ack-' + ident, preserved)
                if (op == 'click' and chosen.get('package') == 'com.android.contacts'
                        and chosen.get('content-desc') == 'More options'):
                    self.t.authorize_contacts_menu_from_more(preserved)
            return value
        self.t.s.helper.ui = record_native
        try:
            response = self.t.s.helper.dispatch(command)
        finally:
            self.t.s.helper.ui = original_ui
        self.t.s.guard()
        self.t.record('response-' + ident, response)
        if (op == 'click' and len(native_ack) == 1
                and chosen.get('package') == 'com.android.contacts'
                and chosen.get('resource-id') == 'com.android.contacts:id/floating_action_button'
                and chosen.get('content-desc') == 'Create new contact'):
            self.t.authorize_storage_from_create(native_ack[0])
        label_input_completed = ((label_container is not None or contact_list_binding is not None) and op == 'snapshot-tap'
            and response.get('ok') is True and response.get('performed') == 'snapshot-tap'
            and response.get('input_command_completed') is True
            and response.get('outcome_unknown') is True
            and response.get('post_action_observation_available') is False)
        if post_capture_only(response, native_ack, op) or label_input_completed:
            # The original unknown post-capture receipt stays unchanged. Only
            # a new read-only owned-window observation can authorize a new
            # decision; this never replays the old request or proves business success.
            self.observe('reconciled-' + ident)
            self.t.record('reconciliation-' + ident, {'original_request_id': ident,
                'original_outcome_unknown_retained': True, 'native_input_acknowledged': not label_input_completed,
                'input_command_completed': label_input_completed,
                'fresh_observation': self.latest, 'action_replayed': False,
                'business_success_verified': False, 'allows_new_decisions_only': True})
            self.pending = None
            return True
        require(response.get('ok') is True and response.get('performed') == op and
                response.get('outcome_unknown') is not True, 'ACTION_OUTCOME_UNKNOWN_NO_REPLAY')
        if op == 'set-text':
            require(response.get('readback_verified') is True and response.get('password') is False, 'TEXT_READBACK_UNVERIFIED')
        if op == 'snapshot-tap':
            require(response.get('input_command_completed') is True, 'TAP_COMPLETION_UNVERIFIED')
        self.pending = None
        self.observe('after-' + ident)
        return True


def execute(adapter, root):
    tx = adapter.load_session()
    require(adapter.SOURCE_SHA == TRANSPORT_SHA, 'TRANSPORT_PIN_CHANGED')
    root.mkdir(mode=0o700)
    adapter.ROOT = root  # Private imported module only; original adapter is untouched.
    result = {'state': 'FAILED', 'business_success_verified': False, 'whole_app_production_ready': False,
              'automatic_retry': False, 'lease_seconds': 720, 'cleanup_budget_seconds': 35}
    old_handler = signal.signal(signal.SIGALRM, expired)
    trial = continuation = None
    try:
        signal.setitimer(signal.ITIMER_REAL, 720)
        with tx.ui_lock(), tx.CameraSession(root / 'commands') as session:
            trial = adapter.Trial(session, tx)
            continuation = Continuation(trial, adapter.PACKAGE)
            try:
                trial.identity()
                continuation.pending = 'initial-launch'
                trial.launch()
                continuation.pending = None
                continuation.observe('initial')
                for number in range(24):
                    raw = sys.stdin.buffer.readline(16385)
                    require(raw and len(raw) <= 16384 and raw.endswith(b'\n'), 'EOF_OR_REQUEST_TOO_LARGE')
                    if not continuation.step(json.loads(raw)):
                        result['state'] = 'CLOSED_ON_REQUEST'
                        break
                else:
                    raise RuntimeError('REQUEST_LIMIT_REACHED')
            finally:
                signal.setitimer(signal.ITIMER_REAL, 35)
                try:
                    trial.close()
                    require(trial.removals == 1 and trial.result.get('other_tasks_preserved') is True, 'NORMAL_OWNED_CLOSE_UNVERIFIED')
                    session.caller_status('session-final-caller')
                except BaseException as exc:
                    result.update(state='FAILED', cleanup_error=type(exc).__name__ + ': ' + str(exc))
                    raise
        require(continuation.pending is None, 'UNRESOLVED_EFFECT')
    except BaseException as exc:
        result.update(state='FAILED', error=type(exc).__name__ + ': ' + str(exc))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, old_handler)
        result.update(actions=continuation.actions if continuation else 0,
                      pending_effect=continuation.pending if continuation else None,
                      owned_task_remove_calls=trial.removals if trial else 0)
        tx.write_new(root / 'result.json', result)
        emit(result)
    return 0 if result['state'] == 'CLOSED_ON_REQUEST' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--adapter', type=Path)
    parser.add_argument('--root', type=Path)
    args = parser.parse_args()
    if not args.execute:
        emit({'state': 'PLAN_ONLY', 'ui_actions': 0, 'adapter_sha256': ADAPTER_SHA, 'transport_sha256': TRANSPORT_SHA})
        return 0
    require(args.adapter and args.root and args.adapter.is_absolute() and args.root.is_absolute(), 'ABSOLUTE_PATHS_REQUIRED')
    raw = args.adapter.read_bytes()
    require(hashlib.sha256(raw).hexdigest() == ADAPTER_SHA, 'FROZEN_ADAPTER_CHANGED')
    adapter = types.ModuleType('private_contacts_adapter')
    adapter.__file__ = str(args.adapter)
    exec(compile(raw, str(args.adapter), 'exec'), adapter.__dict__)
    os.umask(0o077)
    return execute(adapter, args.root)


if __name__ == '__main__':
    raise SystemExit(main())
