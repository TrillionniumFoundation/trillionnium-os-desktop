#!/usr/bin/python3 -I
"""Continue only the exact paused stopwatch created by the completed 01 trial."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, hashlib, json, re, signal, time, types
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
CONTACT_TOOLS = Path('/home/alex/work/pocket4-contacts-session-tools-20261105-r12-01')
ROOT = Path('/home/alex/work/pocket4-clock-stopwatch-20261105-r12-02')
PUBLIC = HERE / 'clock-stopwatch02-result.json'
ORIGINAL = HERE / 'clock-stopwatch01-result.json'
ORIGINAL_SHA = '9af4d7b19f8687563fc5fbe1bf526024d89e690a46d444d76af35884e52a95ed'
PACKAGE = 'com.android.deskclock'
PREFS = '/data/user_de/0/com.android.deskclock/shared_prefs/com.android.deskclock_preferences.xml'
PINS = {
    str(CONTACT_TOOLS / 'ui_preflight04.py'): 'd02821d751736a9e3cf275ec0b27383852e24362928fd4257ebb6d3dee7f6a58',
    str(CONTACT_TOOLS / 'session_loop07.py'): 'c8cd713f3e323016dbfdce8e41a5c474ac58d365ebcd613dd539fc9568bb7784',
    str(HERE / 'read_clock.py'): 'fd3ffdfbb397b561bf251236c117966ea18b2ca176e4908c6a31ad0db4cc0048',
}


def require(value, code):
    if not value:
        raise RuntimeError(code)


def load(path, pin):
    raw = Path(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == pin, 'STOPWATCH_DEPENDENCY_CHANGED')
    module = types.ModuleType('stopwatch_private_' + Path(path).stem)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def read_watch(session):
    raw, _ = session.target.read_file(PREFS, 1024 * 1024)
    tree = ET.fromstring(raw)
    require(tree.tag == 'map', 'CLOCK_PREFERENCES_FORMAT_UNKNOWN')
    values, timer = {}, []
    for item in tree:
        key = item.get('name', '')
        if key.startswith('sw_'):
            require(key not in values and item.tag in ('int', 'long')
                and re.fullmatch('-?[0-9]+', item.get('value', '')), 'STOPWATCH_VALUE_FORMAT_UNKNOWN')
            values[key] = int(item.get('value'))
        elif 'timer' in key.lower():
            timer.append(ET.tostring(item, encoding='unicode'))
    state = values.get('sw_state', 0)
    require(state in (0, 1, 2), 'STOPWATCH_STATE_UNKNOWN')
    session.guard()
    return {'state': state, 'accumulated_ms': values.get('sw_accum_time', 0),
            'lap_count': values.get('sw_lap_num', 0), 'values': values,
            'timer_content_sha256': hashlib.sha256(json.dumps(sorted(timer)).encode()).hexdigest()}


def alarm_fingerprint(session, model):
    # Filter existing alarm contents to a digest inside Android, before journaling.
    script = ('set -o pipefail; /system/bin/sqlite3 -readonly -json ' + model.DB
        + " 'PRAGMA query_only=ON;BEGIN;SELECT * FROM alarm_templates ORDER BY _id;ROLLBACK;'"
        + ' | /system/bin/sha256sum')
    argv = ['/system/bin/env', '-i'] + [k + '=' + session.environment[k] for k in sorted(session.environment)]
    argv += ['/system/bin/timeout', '-k', '2', '12', '/system/bin/sh', '-c', script]
    with session.target.entry(argv) as (command, descriptors):
        value = session.run_host('clock-template-fingerprint', command, 16, descriptors)
    text = value['stdout'].decode().strip()
    require(value['rc'] == 0 and value['joined'] and not value['timed_out']
        and re.fullmatch('[0-9a-f]{64}  -', text), 'ALARM_FINGERPRINT_UNVERIFIED')
    return text[:64]


def expired(signum, frame):
    raise TimeoutError('STOPWATCH_LEASE_EXPIRED_NO_ACTION_REPLAY')


class Flow:
    def __init__(self, trial, loop, result):
        self.t, self.loop, self.r = trial, loop, result
        self.c = loop.Continuation(trial, PACKAGE)
        self.started = False
        self.number = 0
        self.owned, self.closed = [], []
        self.deadline = time.monotonic() + 240

    def visible(self):
        return [n for n in self.c.nodes if n.get('package') == PACKAGE
                and n.get('visible') is True and n.get('enabled') is True]

    def node(self, labels, button=True):
        allowed = {x.casefold() for x in labels}
        nodes = [n for n in self.visible() if any(str(n.get(k, '')).casefold() in allowed
                  for k in ('text', 'content-desc'))]
        if button:
            nodes = [n for n in nodes if n.get('clickable') is True
                     and n.get('editable') is False and n.get('password') is False]
        elif len(nodes) > 1:
            clickable = [n for n in nodes if n.get('clickable') is True]
            if len(clickable) == 1:
                nodes = clickable
        require(len(nodes) == 1, 'ONE_OBSERVED_CLOCK_CONTROL_REQUIRED_' + '_'.join(labels))
        return nodes[0]

    def stopwatch_tab(self):
        parents = [n for n in self.visible() if n.get('class') == 'android.widget.LinearLayout'
                   and n.get('content-desc') == 'Stopwatch' and n.get('text') == '']
        require(len(parents) == 1, 'ACTUAL_STOPWATCH_TAB_PARENT_NOT_UNIQUE')
        parent = parents[0]
        if parent.get('selected') is True:
            require(type(parent.get('window_id')) is int, 'SELECTED_TAB_WINDOW_ID_REQUIRED')
            box = parent['bounds_array']
            labels = [n for n in self.visible() if n.get('resource-id') == 'android:id/text1'
                and n.get('class') == 'android.widget.TextView' and n.get('text') == 'STOPWATCH'
                and n.get('selected') is True and n.get('window_id') == parent.get('window_id')
                and box[0] <= n['bounds_array'][0] < n['bounds_array'][2] <= box[2]
                and box[1] <= n['bounds_array'][1] < n['bounds_array'][3] <= box[3]]
            require(len(labels) == 1, 'SELECTED_STOPWATCH_TAB_CHILD_NOT_VERIFIED')
            require(sum(n.get('resource-id') == PACKAGE + ':id/stopwatch_time_wrapper'
                        and n.get('window_id') == parent['window_id']
                        for n in self.visible()) == 1, 'SELECTED_STOPWATCH_VIEW_NOT_PRESENT')
        return parent

    def settle_observed_notice(self):
        for number in range(4):
            notices = [n for n in self.visible() if n.get('resource-id') == PACKAGE + ':id/snackbar_text'
                       and n.get('text') == 'Default alarm ringtone is silent']
            if not notices:
                return
            require(number < 3 and time.monotonic() < self.deadline,
                    'OBSERVED_TRANSIENT_NOTICE_DID_NOT_SETTLE')
            self.c.observe('notice-settle-%02d-%d' % (self.number + 1, number))

    def act(self, label, node):
        require(time.monotonic() < self.deadline and self.number < 16 and self.c.pending is None,
                'STOPWATCH_ACTION_BUDGET_OR_PENDING')
        selector = {k: node[n] for k, n in (('id', 'resource-id'), ('text', 'text'), ('desc', 'content-desc'))
                    if node.get(n)}
        require(selector, 'CLOCK_OBSERVED_SEMANTIC_IDENTITY_REQUIRED')
        selector['class'] = node['class']
        self.settle_observed_notice()  # Only reads; no previous action was dispatched.
        fresh = self.loop.candidates(self.c.nodes, selector, PACKAGE)
        require(len(fresh) == 1, 'CLOCK_CONTROL_AFTER_NOTICE_NOT_UNIQUE')
        node = fresh[0]
        if label not in ('stopwatch-tab', 'reopen-stopwatch-tab'):
            require(self.stopwatch_tab().get('selected') is True, 'ACTION_REQUIRES_ACTUAL_SELECTED_STOPWATCH')
        self.number += 1
        op = 'click' if node.get('clickable') is True else 'snapshot-tap'
        if op == 'snapshot-tap':
            require(label in ('stopwatch-tab', 'reopen-stopwatch-tab'), 'ONLY_OBSERVED_TAB_LABEL_TOUCH_ALLOWED')
            self.c.approved_labels = {(PACKAGE, node.get('resource-id'), node.get('text'))}
        try:
            self.c.step({'id': 's%02d-' % self.number + label, 'op': op,
                         'observation': self.c.latest, 'selector': selector})
        finally:
            self.c.approved_labels = set()
        require(time.monotonic() < self.deadline, 'STOPWATCH_DEADLINE_AFTER_INPUT')

    def state(self, label, expected=None):
        for index in range(3):
            value = read_watch(self.t.s)
            self.t.record(label + '-read-' + str(index), value)
            if expected is None or value['state'] == expected:
                self.r['phases'][label] = value
                return value
            time.sleep(.25)
        raise RuntimeError('STOPWATCH_STATE_NOT_READ_BACK_' + label)

    def launch(self, label):
        require(time.monotonic() < self.deadline and self.t.owned is None and self.c.pending is None,
                'STOPWATCH_LAUNCH_DEADLINE_OR_UNRESOLVED_TASK')
        self.c.pending = 'launch-' + label
        self.t.launch(); self.owned.append(self.t.owned[0]); self.c.pending = None
        focus = self.t.ready_focus(allow_permission=True)
        self.c.nodes = self.t.observe(label, focus)
        self.c.latest, self.c.package = label, focus['package']
        require(focus['package'] == PACKAGE, 'CLOCK_PERMISSION_PROMPT_REQUIRES_OWNED_REVIEW')
        tab = self.stopwatch_tab()
        if tab.get('selected') is not True:
            self.act('stopwatch-tab' if len(self.owned) == 1 else 'reopen-stopwatch-tab', tab)

    def close(self):
        if self.t.owned is None:
            return
        task = self.t.owned[0]; before = self.t.removals
        self.t.close()
        require(self.t.removals == before + 1 and self.t.result.get('other_tasks_preserved') is True,
                'STOPWATCH_OWNED_CLOSE_UNVERIFIED')
        self.closed.append(task)

    def run(self):
        paused = self.r['original_owned_paused_state']
        current = self.state('owned-paused-before-reopen', 2)
        require(current == paused and current['accumulated_ms'] == 9170 and current['lap_count'] == 0,
                'ORIGINAL_OWNED_STOPWATCH_CHANGED_NO_INPUT')
        self.started = True  # Ownership comes from the pinned, completed original trial.
        self.launch('reopen-initial')
        require(self.state('owned-paused-after-reopen', 2) == paused, 'REOPEN_CHANGED_OWNED_PAUSED_STATE')
        self.act('resume', self.node(('Start', 'Resume')))
        resumed = self.state('resumed', 1)
        require(resumed['accumulated_ms'] == paused['accumulated_ms']
            and resumed['values'].get('sw_start_time', 0)
                > self.r['original_started_state']['values']['sw_start_time'],
            'RESUME_DID_NOT_CONTINUE_EXACT_OWNED_STOPWATCH')
        time.sleep(.4)
        self.act('pause', self.node(('Pause', 'Stop')))
        later = self.state('paused-after-resume', 2)
        require(later['accumulated_ms'] > paused['accumulated_ms'] and later['lap_count'] == 0,
                'RESUMED_STOPWATCH_DID_NOT_ADVANCE')
        self.act('reset', self.node(('Reset',)))
        reset = self.state('reset', 0)
        require(reset['accumulated_ms'] == reset['lap_count'] == 0 and not reset['values']
                and reset['timer_content_sha256'] == paused['timer_content_sha256'],
                'STOPWATCH_RESET_OR_TIMER_PRESERVATION_UNVERIFIED')
        self.r['state'] = 'OWNED_STOPWATCH_REOPEN_RESUME_PAUSE_RESET_VERIFIED'

    def cleanup(self):
        if not self.started or self.c.pending is not None or self.t.owned is None:
            self.r['cleanup'] = {'new_inputs': 0, 'pending_retained': self.c.pending}
            return
        self.deadline = time.monotonic() + 30
        self.c.observe('failure-owned-stopwatch-observation')
        current = self.state('failure-owned-stopwatch')
        require(current['lap_count'] == 0, 'UNEXPECTED_LAPS_NO_CLEANUP')
        if current['state'] == 1:
            self.act('cleanup-pause', self.node(('Pause', 'Stop')))
            current = self.state('cleanup-paused', 2)
        if current['state'] == 2:
            self.act('cleanup-reset', self.node(('Reset',)))
        reset = self.state('cleanup-reset-readback', 0)
        require(reset['accumulated_ms'] == 0 and not reset['values'], 'CLEANUP_RESET_UNVERIFIED')
        self.r['cleanup'] = {'original_failure_retained': True, 'reset_verified': True}


def execute():
    base, loop, model = [load(path, pin) for path, pin in PINS.items()]
    original_raw = ORIGINAL.read_bytes()
    require(hashlib.sha256(original_raw).hexdigest() == ORIGINAL_SHA, 'ORIGINAL_STOPWATCH_RESULT_CHANGED')
    original = json.loads(original_raw)
    require(original['owned_tasks'] == original['closed_tasks'] == [911, 912]
        and original['pending_effect'] is None and original['ui_actions'] == 3
        and original['phases']['before']['values'] == {}
        and original['watch_final']['state'] == 2 and original['watch_final']['accumulated_ms'] == 9170
        and original['watch_final']['lap_count'] == 0, 'ORIGINAL_STOPWATCH_OWNERSHIP_NOT_VERIFIED')
    tx = model.load_session()
    base.PACKAGE, base.COMPONENT, base.ROOT = PACKAGE, PACKAGE + '/.DeskClock', ROOT
    loop.emit = lambda value: None
    result = {'state': 'FAILED', 'phases': {}, 'business_success_verified': False,
        'whole_app_production_ready': False, 'automatic_retry': False, 'source_pins': PINS,
        'alarm_write_actions': 0, 'timer_write_actions': 0, 'lease_seconds': 240,
        'started_utc': datetime.now(timezone.utc).isoformat(),
        'original_result_sha256': ORIGINAL_SHA, 'original_failed_result_retained': True,
        'original_job': '1a1aae28f48-fc05-4871',
        'original_started_state': original['phases']['started'],
        'original_owned_paused_state': original['watch_final']}

    prior = signal.signal(signal.SIGALRM, expired); trial = flow = None
    try:
        signal.setitimer(signal.ITIMER_REAL, 240)
        with tx.ui_lock():
            ROOT.mkdir(mode=0o700)
            with tx.CameraSession(ROOT / 'commands') as session:
                trial = base.Trial(session, tx)
                flow = Flow(trial, loop, result)
                try:
                    result['identity_before'] = model.identity(session)
                    result['alarms_before'] = model.state(session); model.verify_before(result['alarms_before'])
                    require(result['alarms_before']['template-ids'] == [{'_id': 1}, {'_id': 2}], 'ORIGINAL_TEMPLATE_IDS_CHANGED')
                    result['templates_sha_before'] = alarm_fingerprint(session, model)
                    result['epoch_sha256'] = session.epoch_sha256
                    require(result['identity_before'] == original['identity_after']
                        and session.epoch_sha256 == original['epoch_sha256']
                        and result['alarms_before'] == original['alarms_after']
                        and result['templates_sha_before'] == original['templates_sha_after'],
                        'ORIGINAL_CLOCK_OR_ALARM_BINDING_CHANGED_NO_INPUT')
                    flow.run()
                    result['business_success_verified'] = True
                except BaseException as exc:
                    result.update(state='FAILED', error=type(exc).__name__ + ': ' + str(exc))
                    signal.setitimer(signal.ITIMER_REAL, 35)
                    try:
                        flow.cleanup()
                    except BaseException as cleanup:
                        result['cleanup_error'] = type(cleanup).__name__ + ': ' + str(cleanup)
                finally:
                    signal.setitimer(signal.ITIMER_REAL, 35)
                    flow.close()
                    result['identity_after'] = model.identity(session)
                    result['alarms_after'] = model.state(session)
                    result['templates_sha_after'] = alarm_fingerprint(session, model)
                    result['watch_final'] = read_watch(session)
                    require(result.get('alarms_before') == result['alarms_after']
                        and result.get('templates_sha_before') == result['templates_sha_after'], 'ORIGINAL_ALARMS_CHANGED')
                    session.caller_status('clock-stopwatch-final-caller')
        if result['business_success_verified']:
            require(flow.owned == flow.closed and len(set(flow.owned)) == 1
                    and flow.c.pending is None and result['identity_before'] == result['identity_after'],
                    'STOPWATCH_SUCCESS_REQUIRES_IDENTITY_AND_ONE_NORMAL_CLOSE')
    except BaseException as exc:
        result.update(state='FAILED', business_success_verified=False, terminal_error=type(exc).__name__ + ': ' + str(exc))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, prior)
        result.update(ui_actions=flow.c.actions if flow else 0, pending_effect=flow.c.pending if flow else None,
            owned_tasks=flow.owned if flow else [], closed_tasks=flow.closed if flow else [],
            owned_task_remove_calls=trial.removals if trial else 0, finished_utc=datetime.now(timezone.utc).isoformat())
        if ROOT.is_dir():
            tx.write_new(ROOT / 'result.json', result)
        tx.write_new(PUBLIC, result, alex_readable=True)
        print(json.dumps({k: result.get(k) for k in ('state', 'error', 'terminal_error', 'business_success_verified',
            'ui_actions', 'pending_effect', 'owned_tasks', 'closed_tasks')}))
    return 0 if result['business_success_verified'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    if parser.parse_args().execute:
        raise SystemExit(execute())
    print(json.dumps({'state': 'PLAN_ONLY', 'UI_actions': 0, 'alarm_writes': 0, 'timer_writes': 0}))
