#!/usr/bin/python3 -I
"""One UI-created timer: start/pause/reopen/resume/reset/delete; no expiry test."""
from pathlib import Path
from datetime import datetime, timezone
from decimal import Decimal
import argparse, hashlib, json, re, signal, time, types

HERE = Path(__file__).resolve().parent
CONTACT_TOOLS = Path('/home/alex/work/pocket4-contacts-session-tools-20261105-r12-01')
ROOT = Path('/home/alex/work/pocket4-clock-timer-20261105-r12-03')
PUBLIC = HERE / 'clock-timer03-result.json'
PACKAGE = 'com.android.deskclock'
DURATION = 900000  # Fifteen minutes, longer than the whole 360 + 35 second lease.
PINS = {
    'base': (str(CONTACT_TOOLS / 'ui_preflight04.py'), 'd02821d751736a9e3cf275ec0b27383852e24362928fd4257ebb6d3dee7f6a58'),
    'loop': (str(CONTACT_TOOLS / 'session_loop07.py'), 'c8cd713f3e323016dbfdce8e41a5c474ac58d365ebcd613dd539fc9568bb7784'),
    'model': (str(HERE / 'read_clock_expired_text02.py'), '93a25eacc015e5e87a12a0cd55a9b97c8a7fd7068dd6c691a56b9c77b2a1af6f'),
    'shared': ('/home/alex/work/pocket4-clock-session-tools-20261105-r12-01/stopwatch02.py', 'cab5252688463cd0527a3d8e4cb8d9e2b9d498d2cdd3016beda274ba16283cab'),
    'timer': ('/home/alex/work/pocket4-clock-session-tools-20261105-r12-01/read_timer.py', 'c3bf02f38e05ab7a55285ca2245ffe2bda3eb528cc1f85d54723294047948b08'),
}


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def load(path, pin):
    raw = Path(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == pin, 'TIMER_DEPENDENCY_CHANGED')
    module = types.ModuleType('timer_private_' + Path(path).stem)
    module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def expired(signum, frame):
    raise TimeoutError('TIMER_LEASE_EXPIRED_NO_ACTION_REPLAY')


class Flow:
    def __init__(self, trial, loop, timer, result):
        self.t, self.loop, self.m, self.r = trial, loop, timer, result
        self.c = loop.Continuation(trial, PACKAGE)
        self.owned, self.closed = [], []
        self.timer_id = None
        self.creation_dispatch_before = None
        self.creation_uptime_before = None
        self.number = 0
        self.deadline = time.monotonic() + 350

    def visible(self):
        return [n for n in self.c.nodes if n.get('package') == PACKAGE
                and n.get('visible') is True and n.get('enabled') is True]

    def node(self, suffix, labels):
        allowed = {x.casefold() for x in labels}
        nodes = [n for n in self.visible() if n.get('resource-id') == PACKAGE + ':id/' + suffix
            and n.get('clickable') is True and n.get('editable') is False and n.get('password') is False
            and any(str(n.get(k, '')).casefold() in allowed for k in ('text', 'content-desc'))]
        require(len(nodes) == 1, 'ONE_OBSERVED_TIMER_CONTROL_REQUIRED_' + suffix)
        return nodes[0]

    def timer_tab(self):
        require(self.t.last_observation['screenshot']['scope']['activity'] == PACKAGE + '.DeskClock',
                'TIMER_REQUIRES_OWNED_DESKCLOCK_ACTIVITY')
        parents = [n for n in self.visible() if n.get('class') == 'android.widget.LinearLayout'
                   and n.get('content-desc') == 'Timer' and n.get('text') == '']
        require(len(parents) == 1, 'ACTUAL_TIMER_TAB_PARENT_NOT_UNIQUE')
        parent = parents[0]
        if parent.get('selected') is True:
            require(type(parent.get('window_id')) is int, 'SELECTED_TIMER_TAB_WINDOW_REQUIRED')
            box = parent['bounds_array']
            labels = [n for n in self.visible() if n.get('resource-id') == 'android:id/text1'
                and n.get('text') == 'TIMER' and n.get('selected') is True
                and n.get('window_id') == parent['window_id']
                and box[0] <= n['bounds_array'][0] < n['bounds_array'][2] <= box[2]
                and box[1] <= n['bounds_array'][1] < n['bounds_array'][3] <= box[3]]
            require(len(labels) == 1, 'SELECTED_TIMER_TAB_CHILD_NOT_VERIFIED')
        return parent

    def settle_notice(self):
        for attempt in range(4):
            notices = [n for n in self.visible() if n.get('resource-id') == PACKAGE + ':id/snackbar_text'
                       and n.get('text') == 'Default alarm ringtone is silent']
            if not notices:
                return
            require(attempt < 3 and time.monotonic() < self.deadline, 'KNOWN_NOTICE_DID_NOT_SETTLE')
            self.c.observe('notice-%02d-%d' % (self.number + 1, attempt))

    def act(self, label, node, expected_state=None):
        require(time.monotonic() < self.deadline and self.number < 20 and self.c.pending is None,
                'TIMER_ACTION_BUDGET_OR_PENDING')
        selector = {k: node[n] for k, n in (('id', 'resource-id'), ('text', 'text'), ('desc', 'content-desc'))
                    if node.get(n)}
        require(selector, 'OBSERVED_TIMER_SEMANTIC_IDENTITY_REQUIRED')
        selector['class'] = node['class']
        self.settle_notice()
        fresh = self.loop.candidates(self.c.nodes, selector, PACKAGE)
        require(len(fresh) == 1 and fresh[0].get('clickable') is True, 'FRESH_TIMER_CONTROL_NOT_UNIQUE')
        if label not in ('timer-tab', 'reopen-timer-tab'):
            require(self.timer_tab().get('selected') is True, 'ACTUAL_TIMER_TAB_NOT_SELECTED')
        if expected_state is not None:
            require(self.timer_id is not None, 'NO_OWNED_TIMER_FOR_ACTION')
            current = self.m.owned(self.m.read(self.t.s), self.timer_id, DURATION)
            require(current['state'] == expected_state, 'OWNED_TIMER_CHANGED_BEFORE_' + label)
        self.number += 1
        self.c.step({'id': 't%02d-' % self.number + label, 'op': 'click',
                     'observation': self.c.latest, 'selector': selector})
        require(time.monotonic() < self.deadline, 'TIMER_DEADLINE_AFTER_INPUT')

    def setup(self, expected):
        nodes = [n for n in self.visible() if n.get('resource-id') == PACKAGE + ':id/timer_setup_time'
                 and n.get('class') == 'android.widget.TextView']
        require(len(nodes) == 1, 'OBSERVED_TIMER_SETUP_DISPLAY_REQUIRED')
        triples = [[int(x) for x in re.findall('[0-9]+', nodes[0].get(k, ''))]
                   for k in ('text', 'content-desc')]
        require(list(expected) in triples, 'ACTUAL_SETUP_DURATION_DIFFERS')
        self.t.record('setup-%02d' % self.number, {'expected_hms': list(expected), 'observed_node': nodes[0]})

    def uptime(self):
        raw = self.t.s.android(['/system/bin/cat', '/proc/uptime']).decode().strip()
        require(re.fullmatch(r'[0-9]+\.[0-9]+ [0-9]+\.[0-9]+', raw), 'DEVICE_UPTIME_UNKNOWN')
        return int(Decimal(raw.split()[0]) * 1000)

    def read(self, label, expected=None):
        for attempt in range(3):
            value = self.m.read(self.t.s)
            self.t.record(label + '-read-' + str(attempt), value)
            timer = self.m.owned(value, self.timer_id, DURATION) if self.timer_id is not None else None
            if expected is None or (timer is not None and timer['state'] == expected):
                self.r['phases'][label] = value
                if label in ('before', 'paused', 'resumed', 'paused-after-resume', 'deleted'):
                    self.observe_scheduler(label)
                return value
            time.sleep(.25)
        raise RuntimeError('TIMER_STATE_NOT_READ_BACK_' + label)

    def claim_created(self):
        require(self.creation_dispatch_before is not None
                and self.c.actions == self.creation_dispatch_before + 1 and self.c.pending is None,
                'ONE_ACKNOWLEDGED_CREATE_REQUIRED')
        current = self.m.read(self.t.s)
        require(len(current['ids']) == 1 and self.timer_id is None, 'ONE_NEW_TIMER_REQUIRED')
        ident = current['ids'][0]
        timer = self.m.owned(current, ident, DURATION)
        now = self.uptime()
        require(timer['state'] == 1 and self.creation_uptime_before - 10 <= timer['last_start_ms'] <= now + 10
                and 0 < timer['remaining_ms'] <= DURATION, 'NEW_TIMER_CREATION_TIME_NOT_BOUND')
        self.timer_id = ident
        self.r['owned_timer_id'] = ident
        self.r['phases']['created-running'] = current
        self.t.record('owned-timer-created', {'id': ident, 'timer': timer,
            'empty_baseline': self.r['phases']['before'],
            'uptime_before_ms': self.creation_uptime_before, 'uptime_after_ms': now})
        self.observe_scheduler('created-running')

    def observe_scheduler(self, label):
        # Read-only evidence. The existing UI/owned-state guards remain unchanged.
        # Do not confuse removed-alarm history with the active alarm store; retain
        # exact private dumps for a separate, schema-bound cancellation review.
        raw = self.t.s.android(['/system/bin/dumpsys', 'alarm'], 15)
        self.t.tx.write_new(ROOT / (label + '-alarm-private.txt'), raw)
        text = raw.decode('utf-8', 'strict')
        value = {'observed_utc': datetime.now(timezone.utc).isoformat(),
            'uptime_ms': self.uptime(), 'bytes': len(raw),
            'sha256': hashlib.sha256(raw).hexdigest(),
            'selected_clock_lines': [line for line in text.splitlines()
                if PACKAGE in line or re.fullmatch(r'\s*u0a63:\s*', line)],
            'active_store_and_removed_history_not_yet_classified': True}
        self.r.setdefault('scheduler_observations', {})[label] = value
        self.t.record('scheduler-' + label, value)

    def launch(self, label):
        require(time.monotonic() < self.deadline and self.t.owned is None and self.c.pending is None,
                'TIMER_LAUNCH_DEADLINE_OR_PENDING')
        self.c.pending = 'launch-' + label
        self.t.launch(); self.owned.append(self.t.owned[0]); self.c.pending = None
        self.c.observe(label)
        tab = self.timer_tab()
        if tab.get('selected') is not True:
            self.act('timer-tab' if len(self.owned) == 1 else 'reopen-timer-tab', tab)

    def close(self):
        if self.t.owned is None:
            return
        task = self.t.owned[0]; before = self.t.removals
        self.t.close()
        require(self.t.removals == before + 1 and self.t.result.get('other_tasks_preserved') is True,
                'TIMER_NORMAL_OWNED_CLOSE_UNVERIFIED')
        self.closed.append(task)

    def run(self):
        before = self.read('before'); self.m.empty(before)
        self.launch('initial')
        self.setup((0, 0, 0))
        for digit, expected in (('1', (0, 0, 1)), ('5', (0, 0, 15)),
                                ('0', (0, 1, 50)), ('0', (0, 15, 0))):
            self.act('digit-' + digit, self.node('timer_setup_digit_' + digit, (digit,)))
            self.setup(expected)
        self.m.empty(self.read('before-start'))
        self.creation_uptime_before = self.uptime()
        self.creation_dispatch_before = self.c.actions
        self.act('create-start', self.node('fab', ('Start',)))
        self.claim_created()
        self.act('pause', self.node('fab', ('Pause', 'Stop')), 1)
        paused = self.read('paused', 2)
        item = self.m.owned(paused, self.timer_id, DURATION)
        require(0 < item['remaining_ms'] < DURATION
            and item['last_start_ms'] == item['last_wall_ms'] == self.m.UNUSED,
            'TIMER_PAUSE_DID_NOT_PERSIST_POSITIVE_REMAINING_TIME')
        time.sleep(.4)
        require(self.read('paused-stable', 2) == paused, 'PAUSED_TIMER_CONTINUED_CHANGING')
        self.close()
        require(self.read('after-normal-close', 2) == paused, 'CLOSE_CHANGED_PAUSED_TIMER')
        self.launch('reopen')
        require(self.read('after-reopen', 2) == paused, 'REOPEN_CHANGED_PAUSED_TIMER')
        self.act('resume', self.node('fab', ('Start', 'Resume')), 2)
        resumed = self.m.owned(self.read('resumed', 1), self.timer_id, DURATION)
        require(resumed['last_start_ms'] > self.r['phases']['created-running']['timers'][0]['last_start_ms']
            and 0 < resumed['remaining_ms'] <= item['remaining_ms'], 'TIMER_RESUME_DID_NOT_CONTINUE')
        time.sleep(.4)
        self.act('pause-again', self.node('fab', ('Pause', 'Stop')), 1)
        later = self.m.owned(self.read('paused-after-resume', 2), self.timer_id, DURATION)
        require(0 < later['remaining_ms'] < item['remaining_ms'], 'RESUMED_TIMER_DID_NOT_DECREASE')
        self.act('reset', self.node('reset_add', ('Reset',)), 2)
        reset = self.m.owned(self.read('reset', 4), self.timer_id, DURATION)
        require(reset['remaining_ms'] == DURATION
            and reset['last_start_ms'] == reset['last_wall_ms'] == self.m.UNUSED, 'TIMER_RESET_UNVERIFIED')
        self.act('delete', self.node('left_button', ('Delete',)), 4)
        self.timer_id = None
        self.m.empty(self.read('deleted'))
        self.r['state'] = 'OWNED_TIMER_CORE_FLOW_VERIFIED_CLEAN'

    def cleanup(self):
        self.r['cleanup'] = {'original_failure_retained': True, 'new_inputs': 0,
                             'pending_retained': self.c.pending}
        if self.c.pending is not None or self.t.owned is None:
            return
        self.deadline = time.monotonic() + 30
        current = self.m.read(self.t.s)
        if not current['ids']:
            self.m.empty(current)
            self.r['cleanup']['empty_timer_readback'] = True
            return
        if self.timer_id is None:
            self.claim_created()  # Only the one acknowledged creation and its exact uptime window.
        item = self.m.owned(self.m.read(self.t.s), self.timer_id, DURATION)
        require(item['state'] in (1, 2, 4), 'UNEXPECTED_EXPIRED_TIMER_NO_CLEANUP_INPUT')
        self.c.observe('failure-owned-timer')
        actions = self.c.actions
        if item['state'] == 1:
            self.act('cleanup-pause', self.node('fab', ('Pause', 'Stop')), 1)
            item = self.m.owned(self.read('cleanup-paused', 2), self.timer_id, DURATION)
        self.act('cleanup-delete', self.node('left_button', ('Delete',)), item['state'])
        self.timer_id = None
        self.m.empty(self.read('cleanup-deleted'))
        self.r['cleanup'].update(new_inputs=self.c.actions - actions, exact_timer_removed=True)


def execute():
    modules = {name: load(*pin) for name, pin in PINS.items()}
    base, loop, model, shared, timer = [modules[x] for x in ('base', 'loop', 'model', 'shared', 'timer')]
    tx = model.load_session()
    base.PACKAGE, base.COMPONENT, base.ROOT = PACKAGE, PACKAGE + '/.DeskClock', ROOT
    loop.emit = lambda value: None
    result = {'state': 'FAILED', 'phases': {}, 'business_success_verified': False,
        'whole_app_production_ready': False, 'automatic_retry': False, 'source_pins': PINS,
        'alarm_write_actions': 0, 'global_volume_or_ringtone_actions': 0,
        'notification_permission_actions': 0, 'timer_expiry_qualification': False,
        'current_installed_dex_sha256': 'c6721db34c21c5bab07712a6ddc3eaaf9c6617196856f9abf29741c18f956d22',
        'prior_factory_binary_core_result_does_not_qualify_this_run': True,
        'scheduler_cancellation_verified': False,
        'scheduler_cancellation_requires_independent_saved_dump_review': True,
        'lease_seconds': 360, 'cleanup_budget_seconds': 35, 'timer_duration_ms': DURATION,
        'started_utc': datetime.now(timezone.utc).isoformat()}
    prior = signal.signal(signal.SIGALRM, expired); trial = flow = None
    try:
        signal.setitimer(signal.ITIMER_REAL, 360)
        with tx.ui_lock():
            ROOT.mkdir(mode=0o700)
            with tx.CameraSession(ROOT / 'commands') as session:
                trial = base.Trial(session, tx)
                flow = Flow(trial, loop, timer, result)
                try:
                    result['identity_before'] = model.identity(session)
                    result['alarms_before'] = model.state(session); model.verify_before(result['alarms_before'])
                    require(result['alarms_before']['template-ids'] == [{'_id': 1}, {'_id': 2}], 'ORIGINAL_TEMPLATE_IDS_CHANGED')
                    result['templates_sha_before'] = shared.alarm_fingerprint(session, model)
                    require(result['templates_sha_before'] == '655c545ee9487dc380100d6300376d0bb82d0d12beddd96f283ab7814ff19fea',
                            'ORIGINAL_ALARM_CONTENTS_CHANGED')
                    result['epoch_sha256'] = session.epoch_sha256
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
                    result['templates_sha_after'] = shared.alarm_fingerprint(session, model)
                    result['timer_final'] = timer.read(session)
                    require(result.get('alarms_before') == result['alarms_after']
                        and result.get('templates_sha_before') == result['templates_sha_after'], 'ORIGINAL_ALARMS_CHANGED')
                    session.caller_status('clock-timer-final-caller')
        if result['business_success_verified']:
            timer.empty(result['timer_final'])
            require(flow.owned == flow.closed and len(set(flow.owned)) == 2 and flow.c.pending is None
                    and result['identity_before'] == result['identity_after'],
                    'TIMER_SUCCESS_REQUIRES_IDENTITY_AND_TWO_NORMAL_CLOSES')
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
            'ui_actions', 'pending_effect', 'owned_timer_id', 'owned_tasks', 'closed_tasks')}))
    return 0 if result['business_success_verified'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--execute', action='store_true')
    if parser.parse_args().execute:
        raise SystemExit(execute())
    print(json.dumps({'state': 'PLAN_ONLY', 'UI_actions': 0, 'alarm_writes': 0, 'timer_writes': 0}))
