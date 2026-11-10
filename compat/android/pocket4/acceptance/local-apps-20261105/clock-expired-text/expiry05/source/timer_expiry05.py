#!/usr/bin/python3 -I
"""One UI-created 60-second timer: actual expiry, observed stop, exact deletion."""
from pathlib import Path
from datetime import datetime, timezone
import argparse, copy, hashlib, json, re, signal, time, types

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/alex/work/pocket4-clock-timer-expiry-20261105-r12-05')
PUBLIC = HERE / 'clock-timer-expiry05-result.json'
PACKAGE = 'com.android.deskclock'
ALERT = PACKAGE + '.timer.ExpiredTimersActivity'
DURATION = 60000
PINS = {
    'core': ('/home/alex/work/pocket4-clock-session-tools-20261105-r12-01/timer01.py', '873c5e61a0c87658d81cce5b2a085b3516515a8bbe61e4ba5e18f69d23a3b041'),
    'notifications': ('/home/alex/work/pocket4-clock-session-tools-20261105-r12-01/notification_ui04.py', '1c986fab2058b3270320139a1346260be4e3313a3fdc9dc3dc82e07c52eab85d'),
}
OBSERVER_PINS = {'read_clock_expired_text02.py': '6f996dc4d8544d54520c76121308d7dba0cdbd58bbeda9a06fd84889dc3373b6', 'notify_watch03.py': 'c85831423987f2cd5d1d1d2a37b14f9c3be2f8c6af62986ecafafb9c28a8c436', 'notify_proof.py': '9e8c5df6fda3ac2e80d8674f8717ad7916de99f4b945692c6c8bdccbfcd6ffdb', 'audio_observe.py': '5c6a49c7ee119c457d60072fbd25ea5ff1b23a577ad2504ba5fcbfc3fe01fdac'}
ALARM_SHA = '655c545ee9487dc380100d6300376d0bb82d0d12beddd96f283ab7814ff19fea'


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def load(path, pin):
    raw = Path(path).read_bytes()
    require(hashlib.sha256(raw).hexdigest() == pin, 'EXPIRY_DEPENDENCY_CHANGED')
    module = types.ModuleType('expiry_private_' + Path(path).stem); module.__file__ = str(path)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    return module


def activity(value):
    return PACKAGE + value if value.startswith('.') else value


def timer_owned(value, ident):
    require(value['ids'] == [ident] and len(value['timers']) == 1 and value['stopwatch'] == {},
            'SOLE_OWNED_TIMER_REQUIRED')
    item = value['timers'][0]
    require(item['id'] == ident and item['length_ms'] == DURATION
        and item['label'] in ('', None) and item['delete_after_use'] is False,
        'OWNED_EXPIRY_TIMER_CHANGED')
    require(item['state'] in (1, 2, 3, 4), 'UNEXPECTED_TIMER_STATE')
    if item['state'] == 3:
        # Exact installed Timer.expire(): totalLength=0, remaining<=0, fresh start clocks.
        require(item['total_length_ms'] == 0 and item['remaining_ms'] <= 0
            and item['last_start_ms'] > 0 and item['last_wall_ms'] > 0, 'EXPIRED_TIMER_FIELDS_UNVERIFIED')
    else:
        require(item['total_length_ms'] == DURATION, 'CORE_TIMER_LENGTH_CHANGED')
    return item


def task_map(roots):
    return {c['id']: (c['component'], c['user']) for r in roots.values() for c in r['children']}


def exact_alert(roots, task):
    found = [(r, c) for r in roots.values() for c in r['children'] if c['id'] == task]
    return bool(len(found) == 1 and found[0][0]['display'] == 0 and found[0][0]['user'] == 0
        and found[0][1]['user'] == 0 and found[0][1]['component'].split('/')[0] == PACKAGE
        and activity(found[0][1]['component'].split('/', 1)[1]) == ALERT)


def active_notifications(raw):
    """Only the active list; channel preferences/history are never delivery evidence."""
    lines = raw.splitlines()
    if not lines or lines[0] != "Current Notification Manager state (filtered to 'com.android.deskclock'):":
        return {'parsed': False, 'reason': 'EXACT_FILTER_HEADER_UNKNOWN'}
    starts = [i for i, line in enumerate(lines) if line == '  Notification List:']
    if len(starts) != 1:
        return {'parsed': False, 'reason': 'ACTIVE_LIST_HEADER_UNKNOWN'}
    body = []
    for line in lines[starts[0] + 1:]:
        if line.strip() and not line.startswith('    '):
            break
        body.append(line)
    joined = '\n'.join(body).strip()
    if not joined:
        return {'parsed': True, 'active_count': 0, 'expired_heads_up_count': 0, 'records': []}
    # The active record's own package/user/UID and channel must agree. Redacted
    # notification titles and text are intentionally neither parsed nor published.
    blocks = re.split(r'(?=^    NotificationRecord\()', '\n'.join(body), flags=re.M)
    if blocks[0].strip():
        return {'parsed': False, 'reason': 'ACTIVE_RECORD_SCHEMA_UNKNOWN'}
    records = []
    for block in blocks[1:]:
        header = block.splitlines()[0]
        if (not re.search(r'\bpkg=com\.android\.deskclock\b', header)
                or 'user=UserHandle{0}' not in header or not re.search(r'\buid=10063\b', block)):
            return {'parsed': False, 'reason': 'ACTIVE_RECORD_IDENTITY_UNKNOWN'}
        channel = bool(re.search(r'\bchannel=TimerModelNotification\b', block)
                       or "mId='TimerModelNotification'" in block)
        fullscreen = bool(re.search(r'\bfullscreenIntent=PendingIntent\{', block))
        records.append({'uid': 10063, 'user': 0, 'timer_channel': channel,
                        'full_screen_pending_intent': fullscreen,
                        'record_sha256': hashlib.sha256(block.encode()).hexdigest()})
    return {'parsed': True, 'active_count': len(records),
            'expired_heads_up_count': sum(x['timer_channel'] and x['full_screen_pending_intent'] for x in records),
            'records': records}


def make_flow(core, base, notify, audio, proof):
    class ExpiryFlow(core.Flow):
        def __init__(self, trial, loop, timer, result):
            super().__init__(trial, loop, timer, result)
            self.deadline = time.monotonic() + 230
            self.baseline = self.baseline_map = None
            self.alert_task = None
            self.alert_self_finished = []
            self.stop_dispatched = False
            self.watch = notify.Watch(trial.s, trial.tx, ROOT / "notify-private")
            self.audio = audio.Observe(trial.s, trial.tx, ROOT / "audio-private")
            original_leaf = base.exact_leaf
            base.exact_leaf = lambda roots, task: (exact_alert(roots, task)
                if task == self.alert_task else original_leaf(roots, task))
            original_focus = trial.focus_allowed
            def scoped_focus(current, allow_permission=True):
                if not original_focus(current, False) or current.get('package') != PACKAGE:
                    return False
                expected = ALERT if self.t.owned and self.t.owned[0] == self.alert_task else PACKAGE + '.DeskClock'
                return activity(current.get('activity', '')) == expected and activity(current.get('focused_activity', '')) == expected
            trial.focus_allowed = scoped_focus

        def topology(self, label):
            roots, tasks = self.t.stacks(label)
            if self.baseline is not None:
                now = task_map(roots)
                require(self.baseline <= tasks and all(now.get(k) == v for k, v in self.baseline_map.items()),
                        'PRESERVED_TASK_IDENTITY_CHANGED')
            return roots, tasks

        def launch(self, label):
            require(len(self.owned) < 2, 'MAXIMUM_TWO_NATIVE_CLOCK_LAUNCHES')
            before = self.t.launches
            try:
                super().launch(label)
            except BaseException:
                # A failure before Trial increments launch count is a proven
                # precondition rejection, not an unknown dispatched launch.
                if self.t.launches == before:
                    self.c.pending = None
                raise

        def act(self, label, node, expected_state=None):
            require(self.number < 12, 'EXPIRY_INPUT_BUDGET_EXHAUSTED')
            super().act(label, node, expected_state)

        def read(self, label, expected=None):
            for attempt in range(3):
                value = self.m.read(self.t.s)
                self.t.record(label + '-read-' + str(attempt), value)
                item = timer_owned(value, self.timer_id) if self.timer_id is not None else None
                if expected is None or (item is not None and item['state'] == expected):
                    self.r['phases'][label] = value
                    return value
                time.sleep(.25)
            raise RuntimeError('TIMER_STATE_NOT_READ_BACK_' + label)

        def notifications(self, label):
            raw = self.t.s.android(['/system/bin/dumpsys', 'notification', '--package', PACKAGE], 12)
            self.t.tx.write_new(ROOT / (label + '-notifications.txt'), raw)
            parsed = active_notifications(raw.decode('utf-8', 'strict'))
            parsed.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            self.r.setdefault('notifications', {})[label] = parsed
            return parsed

        def claim_alert(self, cleanup=False):
            roots, tasks = self.topology('possible-expired-alert')
            if tasks == self.baseline:
                return False
            extras = tasks - self.baseline
            require(self.t.owned is None and self.c.pending is None and len(extras) == 1,
                    'NEW_ALERT_TASK_NOT_SOLE_AND_SOURCE_BOUND')
            task = next(iter(extras))
            require(exact_alert(roots, task), 'NEW_TASK_IS_NOT_EXACT_EXPIRED_TIMERS_ACTIVITY')
            item = timer_owned(self.m.read(self.t.s), self.timer_id)
            require(item['state'] == 3 and (self.r.get('actual_expiry_verified') is True
                    or (cleanup and self.r.get('owned_timer_id') == self.timer_id
                        and 'created-running' in self.r['phases'])),
                    'ALERT_REQUIRES_THIS_TIMER_EXPIRED')
            self.alert_task = task
            self.t.owned = (task, set(self.baseline))
            self.r['owned_alert_task'] = task
            self.t.record('source-bound-alert', {'task': task, 'component': ALERT,
                'uid': 10063, 'sole_expired_timer_id': self.timer_id,
                'full_screen_intent_does_not_contain_timer_id': True,
                'other_task_ids': sorted(self.baseline), 'native_launch_performed': False,
                'cleanup_only': cleanup})
            self.c.observe('actual-expired-alert')
            require(self.t.last_observation['screenshot']['scope']['activity'] == ALERT,
                    'OBSERVED_ALERT_ACTIVITY_CHANGED')
            self.r['actual_alert_window_verified'] = not cleanup
            return True

        def observe_service_process(self, label):
            # Read-only evidence; no requirement to invent a PID if the service
            # is absent. Raw logs stay private, selected lines remain Clock-only.
            value = {'observed_utc': datetime.now(timezone.utc).isoformat(),
                     'uptime_ms': self.uptime(), 'commands': {}}
            for kind, argv in (
                ('services', ['/system/bin/dumpsys', 'activity', 'services', PACKAGE]),
                ('events', ['/system/bin/logcat', '-b', 'events', '-d', '-v', 'threadtime', '-t', '1500']),
            ):
                raw = self.t.s.android(argv, 12)
                self.t.tx.write_new(ROOT / (label + '-' + kind + '-private.txt'), raw)
                text = raw.decode('utf-8', 'strict')
                selected = [line for line in text.splitlines() if PACKAGE in line]
                record = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
                          'clock_lines': selected}
                if kind == 'services':
                    record['service_app_process_pids'] = sorted(set(int(x) for x in re.findall(
                        r'(?m)^\s*app=ProcessRecord\{[^\n{}]*? (\d+):com\.android\.deskclock/u0a63\}', text)))
                    record['service_state_lines'] = [line.strip() for line in text.splitlines()
                        if re.match(r'^\s*(app=|startRequested=|isForeground=|startForegroundCount=|fgRequired=)', line)]
                value['commands'][kind] = record
            self.t.s.guard()
            self.r.setdefault('runtime_observations', {})[label] = value

        def wait_expiry(self):
            created = self.r['phases']['created-running']['timers'][0]
            due = created['last_start_ms'] + created['remaining_ms']
            wait_until = min(self.deadline - 60, self.closed_wait_started + DURATION / 1000 + 25)
            samples = []
            while time.monotonic() < wait_until:
                value = self.m.read(self.t.s); item = timer_owned(value, self.timer_id)
                now = self.uptime()
                samples.append({'uptime_ms': now, 'state': item['state']})
                if item['state'] == 3:
                    require(due - 1000 <= item['last_start_ms'] <= now + 10
                            and due - 1000 <= now <= due + 30000, 'EXPIRY_TIME_NOT_BOUND_TO_CREATED_TIMER')
                    self.r['phases']['expired'] = value
                    self.r['expiry_timing'] = {'created_start_ms': created['last_start_ms'],
                        'expected_due_ms': due, 'observed_uptime_ms': now, 'samples': samples}
                    self.r['actual_expiry_verified'] = True
                    return
                require(item['state'] == 1, 'TIMER_CHANGED_DURING_READ_ONLY_WAIT')
                time.sleep(1)
            self.r['expiry_timing'] = {'expected_due_ms': due, 'samples': samples}
            raise RuntimeError('TIMER_DID_NOT_EXPIRE_WITHIN_BOUNDED_WAIT')

        def stop_expired(self, label):
            require(not self.stop_dispatched and self.c.pending is None and self.number < 12
                    and time.monotonic() < self.deadline, 'EXPIRED_STOP_BUDGET_OR_PENDING')
            before = timer_owned(self.m.read(self.t.s), self.timer_id)
            require(before['state'] == 3, 'STOP_REQUIRES_SOLE_OWNED_EXPIRED_TIMER')
            node = self.node('fab', ('Stop', 'Stop timer', 'Stop timers', 'Stop all timers', 'Reset', 'Reset timer', 'Reset timers'))
            selector = {key: node[value] for key, value in (('id', 'resource-id'), ('text', 'text'), ('desc', 'content-desc')) if node.get(value)}
            selector['class'] = node['class']
            previous = self.t.last_observation['screenshot']
            self.c.observe('fresh-' + label, publish=False)
            fresh = self.loop.candidates(self.c.nodes, selector, PACKAGE)
            require(len(fresh) == 1 and self.loop.node_identity(fresh[0]) == self.loop.node_identity(node)
                    and fresh[0].get('clickable') is True, 'EXPIRED_STOP_CONTROL_CHANGED')
            current = self.t.last_observation['screenshot']
            focus = self.t.ready_focus(allow_permission=False)
            require(current['scope']['window_token'] == previous['scope']['window_token'] == focus['window_token'],
                    'EXPIRED_STOP_WINDOW_CHANGED')
            require(timer_owned(self.m.read(self.t.s), self.timer_id)['state'] == 3,
                    'EXPIRED_SET_CHANGED_BEFORE_STOP')
            self.number += 1; ident = 'e%02d-' % self.number + label
            command = {'op': 'click', 'package': PACKAGE, 'window_token': focus['window_token'],
                'display': 0, 'accessibility_mode': 'none', 'method': 'accessibility',
                'selector': dict(selector, package=PACKAGE, enabled=True, clickable=True)}
            self.t.record('intent-' + ident, {'command': command, 'observed_node': node,
                'sole_expired_timer_id': self.timer_id, 'automatic_retry': False})
            self.c.pending = ident; self.c.actions += 1; self.stop_dispatched = True
            original = self.t.s.helper.ui; acknowledgements = []
            def capture_ack(request):
                value = original(request)
                if request.get('op') == 'click':
                    ack = copy.deepcopy(value); acknowledgements.append(ack)
                    self.t.record('native-ack-' + ident, ack)
                return value
            self.t.s.guard(); self.t.s.helper.ui = capture_ack
            try:
                response = self.t.s.helper.dispatch(command)
            finally:
                self.t.s.helper.ui = original
            self.t.s.guard(); self.t.record('response-' + ident, response)
            require(len(acknowledgements) == 1, 'ONE_EXPIRED_STOP_NATIVE_ACK_REQUIRED')
            ack = acknowledgements[0]
            require(ack.get('ok') is True and ack.get('performed') == 'click'
                and ack.get('outcome_unknown') is not True and ack.get('accessibility_mode_restoration_verified') is True
                and ack.get('actual_target', {}).get('package') == PACKAGE
                and ack.get('actual_target', {}).get('resource-id') == PACKAGE + ':id/fab',
                'EXPIRED_STOP_INPUT_ACK_UNKNOWN_NO_REPLAY')
            post_only = self.loop.post_capture_only(response, acknowledgements, 'click')
            require(post_only or (response.get('ok') is True and response.get('performed') == 'click'
                    and response.get('outcome_unknown') is not True), 'EXPIRED_STOP_RESPONSE_UNKNOWN_NO_REPLAY')
            # The installed alert listener resets this sole expired set and
            # finishes itself. Reconcile that exact effect read-only; never
            # demand a new picture of its now-finished original window.
            until = time.monotonic() + 12
            while time.monotonic() < until:
                value = self.m.read(self.t.s); item = timer_owned(value, self.timer_id)
                roots, tasks = self.topology('stop-effect-readback')
                reset = (item['state'] == 4 and item['remaining_ms'] == DURATION
                         and item['last_start_ms'] == item['last_wall_ms'] == self.m.UNUSED)
                alert = self.t.owned[0] == self.alert_task
                if reset and ((alert and tasks == self.baseline) or
                              (not alert and tasks == self.baseline | {self.t.owned[0]})):
                    if alert:
                        require(self.alert_task not in roots and self.alert_task not in tasks,
                                'EXPIRED_ALERT_TASK_STILL_PRESENT')
                        self.alert_self_finished.append(self.alert_task); self.t.owned = None
                    self.r['phases']['stopped-reset'] = value
                    self.r['stop_reconciliation'] = {'request_id': ident, 'native_input_acknowledged': True,
                        'original_outcome_unknown_retained': post_only, 'action_replayed': False,
                        'same_timer_reset_verified': True, 'alert_self_finished': alert}
                    self.c.pending = None
                    if self.t.owned is not None:
                        self.c.observe('after-' + label)
                    return
                time.sleep(.3)
            raise RuntimeError('ACKNOWLEDGED_EXPIRED_STOP_EFFECT_NOT_VERIFIED')

        def close(self):
            if self.t.owned is not None and self.t.owned[0] == self.alert_task:
                # Removing a still-expired alert window would not stop its timer.
                # Only the source-proven Stop + absent-task readback releases it.
                raise RuntimeError('OWNED_ALERT_RETAINED_UNTIL_RESET_AND_SELF_FINISH')
            super().close()

        def delete_reset(self, label):
            if self.t.owned is None:
                self.launch(label + '-main')
            self.c.observe(label + '-reset-timer')
            require(timer_owned(self.read(label + '-before-delete', 4), self.timer_id)['state'] == 4,
                    'DELETE_REQUIRES_THIS_RESET_TIMER')
            self.act(label + '-delete', self.node('left_button', ('Delete',)), 4)
            self.timer_id = None; self.m.empty(self.read(label + '-deleted'))

        def run(self):
            before = self.read('before'); self.m.empty(before)
            initial = self.notifications('before')
            require(initial.get('parsed') is True and initial['active_count'] == 0,
                    'EMPTY_ACTIVE_CLOCK_NOTIFICATION_BASELINE_REQUIRED')
            roots, tasks = self.topology('baseline-tasks')
            self.baseline, self.baseline_map = set(tasks), task_map(roots)
            self.r['notify_watch_start'] = self.watch.start()
            require(self.watch.baseline['record'] is None, 'OLD_EXPIRED_DESKTOP_RECORD_PRESENT')
            self.audio.start()
            self.launch('initial'); self.setup((0, 0, 0))
            for digit, expected in (('1', (0, 0, 1)), ('0', (0, 0, 10)), ('0', (0, 1, 0))):
                self.act('digit-' + digit, self.node('timer_setup_digit_' + digit, (digit,)))
                self.setup(expected)
            self.m.empty(self.read('before-start'))
            self.creation_uptime_before = self.uptime(); self.creation_dispatch_before = self.c.actions
            self.act('create-start', self.node('fab', ('Start',))); self.claim_created()
            self.close()
            self.closed_wait_started = time.monotonic()
            clock_before = time.monotonic_ns(); clock_uptime = self.uptime(); clock_after = time.monotonic_ns()
            clock_basis = {'before_ns':clock_before,'after_ns':clock_after,'uptime_ms':clock_uptime}
            running_raw = self.t.s.android(['/system/bin/dumpsys','notification','--noredact','--package',PACKAGE],12)
            self.t.tx.write_new(ROOT/'running-text-private.txt',running_raw)
            running_text = proof.parse_nms(running_raw)
            self.r['host_notify_running'] = self.watch.snapshot()
            self.r['running_notification_text'] = running_text
            self.observe_service_process('after-owned-close')
            self.wait_expiry()
            self.observe_service_process('actual-expired')
            delivered = self.notifications('expired')
            self.r['notification_posted_verified'] = bool(delivered.get('parsed') is True
                                                          and delivered.get('expired_heads_up_count') == 1)
            def verify_own_expired():
                current = timer_owned(self.m.read(self.t.s), self.timer_id)
                require(current['state'] == 3, 'AUDIO_REQUIRES_THIS_SOLE_EXPIRED_TIMER')
            verify_own_expired()
            self.r['expiry_audio_evidence'] = self.audio.expired(verify_own_expired,
                self.r['expiry_timing']['expected_due_ms'], self.uptime)
            verify_own_expired()
            observed = self.watch.snapshot()
            self.r['host_notify_expired'] = observed
            text_raw = self.t.s.android(['/system/bin/dumpsys','notification','--noredact','--package',PACKAGE],12)
            self.t.tx.write_new(ROOT/'expired-text-private.txt',text_raw)
            self.r['expired_notification_text'] = proof.parse_nms(text_raw)
            self.r['Notify_scope'] = proof.associate(self.r['expired_notification_text'],running_text,
                observed,self.r['host_notify_running'],clock_basis,self.r['expiry_timing']['expected_due_ms'])
            self.r['standard_title_body_to_host_Notify_observed'] = bool(
                self.r['notification_posted_verified'] and self.r['Notify_scope']['verified'])
            self.r['Notify_scope'].update(owned_timer_id=self.timer_id,duration_ms=DURATION,
                snapshot_utc=observed['utc'],expiry_timing=self.r['expiry_timing'])
            self.r['Notify_scope_context'] = {'owned_timer_id':self.timer_id,'duration_ms':DURATION,
                'expired_key':observed['own_state']['key'],'snapshot_utc':observed['utc'],
                'expiry_timing':self.r['expiry_timing'],
                'actual_desktop_popup_observed':False,'absence_is_not_App_failure':True}
            if not self.claim_alert():
                self.launch('expired-main')
                self.r['actual_expired_main_window_verified'] = True
            self.stop_expired('stop-expired')
            self.delete_reset('final')
            after = self.notifications('deleted')
            for attempt in range(2):
                if after.get('parsed') is True and after.get('active_count') == 0:
                    break
                time.sleep(.3)
                after = self.notifications('deleted-readback-' + str(attempt))
            require(after.get('parsed') is True and after['active_count'] == 0,
                    'CLOCK_TIMER_NOTIFICATION_NOT_CLEARED')
            require(self.r['notification_posted_verified'] or self.r.get('actual_alert_window_verified') is True,
                    'EXPIRY_REMINDER_DELIVERY_NOT_VERIFIED')
            self.r['host_notify_after_delete'] = self.watch.snapshot()
            self.r['expired_desktop_state_removed'] = self.r['host_notify_after_delete']['own_state']['record'] is None
            self.r['state'] = 'OWNED_TIMER_EXPIRY_STOP_DELETE_VERIFIED_CLEAN' 

        def cleanup(self):
            self.r['cleanup'] = {'original_failure_retained': True, 'new_inputs': 0,
                                 'pending_retained': self.c.pending}
            if self.c.pending is not None:
                return
            self.deadline = time.monotonic() + 40
            current = self.m.read(self.t.s)
            if not current['ids']:
                self.m.empty(current); self.r['cleanup']['empty_timer_readback'] = True
                return
            if self.timer_id is None:
                self.claim_created()
            item = timer_owned(self.m.read(self.t.s), self.timer_id); before = self.c.actions
            if self.t.owned is None:
                if item['state'] != 3 or not self.claim_alert(cleanup=True):
                    self.launch('cleanup')
            self.c.observe('cleanup-owned-timer')
            if item['state'] == 3:
                self.stop_expired('cleanup-stop-expired'); self.delete_reset('cleanup')
            else:
                if item['state'] == 1:
                    self.act('cleanup-pause', self.node('fab', ('Pause', 'Stop')), 1)
                    item = timer_owned(self.read('cleanup-paused', 2), self.timer_id)
                self.act('cleanup-delete', self.node('left_button', ('Delete',)), item['state'])
                self.timer_id = None; self.m.empty(self.read('cleanup-deleted'))
            self.r['cleanup'].update(new_inputs=self.c.actions - before, exact_timer_removed=True)

    return ExpiryFlow


def expired(signum, frame):
    raise TimeoutError('TIMER_EXPIRY_LEASE_EXPIRED_NO_REPLAY')


def execute():
    core = load(*PINS['core']); notifications = load(*PINS['notifications'])
    notify = load(str(HERE/'notify_watch03.py'), OBSERVER_PINS['notify_watch03.py'])
    proof = load(str(HERE/'notify_proof.py'), OBSERVER_PINS['notify_proof.py'])
    audio = load(str(HERE/'audio_observe.py'), OBSERVER_PINS['audio_observe.py'])
    core.PINS = dict(core.PINS)
    core.PINS['model'] = (str(HERE / 'read_clock_expired_text02.py'), '6f996dc4d8544d54520c76121308d7dba0cdbd58bbeda9a06fd84889dc3373b6')
    core.DURATION = DURATION  # Private module only; frozen timer01 bytes stay unchanged.
    modules = {name: core.load(*pin) for name, pin in core.PINS.items()}
    base, loop, model, shared, timer = [modules[x] for x in ('base', 'loop', 'model', 'shared', 'timer')]
    tx = model.load_session(); base.PACKAGE, base.COMPONENT, base.ROOT = PACKAGE, PACKAGE + '/.DeskClock', ROOT
    loop.emit = lambda value: None
    result = {'state': 'FAILED', 'phases': {}, 'business_success_verified': False,
        'whole_app_production_ready': False, 'audible_output_verified': False,
        'alarm_write_actions': 0, 'global_volume_or_ringtone_actions': 0, 'notification_permission_actions': 0,
        'automatic_retry': False, 'timer_duration_ms': DURATION, 'lease_seconds': 240,
        'cleanup_budget_seconds': 45, 'source_pins': PINS, 'inherited_source_pins': core.PINS,
        'installed_dex_sha256': 'c6721db34c21c5bab07712a6ddc3eaaf9c6617196856f9abf29741c18f956d22',
        'prior_expiry02_original_failure_sha256': '61f2bd63c63f637d858417e89f831bceb107d23432ed4815e0e77a8b5299d0cb',
        'current_install_state': 'INSTALLED_VERIFIED',
        'install_result_sha256': '8c6571736a221d78178bec412fdc771b56ca1dc7655907c7b715afeb87aa1bf6',
        'install_delta_review': 'global intent counter 120 -> 121; all other preference bytes and protected state preserved',
        'started_utc': datetime.now(timezone.utc).isoformat()}
    prior = signal.signal(signal.SIGALRM, expired); trial = flow = None
    cleanup_deadline = None
    try:
        signal.setitimer(signal.ITIMER_REAL, 240)
        with tx.ui_lock():
            ROOT.mkdir(mode=0o700)
            with tx.CameraSession(ROOT / 'commands') as session:
                trial = base.Trial(session, tx); flow = make_flow(core, base, notify, audio, proof)(trial, loop, timer, result)
                try:
                    result['identity_before'] = model.identity(session)
                    require(result['identity_before']['notifications_granted'] is True, 'CLOCK_NOTIFICATIONS_MUST_REMAIN_ENABLED')
                    appop = session.android(['/system/bin/cmd', 'appops', 'get', '--user', '0', PACKAGE, 'POST_NOTIFICATION']).decode()
                    result['appop_before'] = notifications.parse_appop(appop)
                    require(result['appop_before']['allow_verified'] is True, 'CLOCK_APP_OP_MUST_ALLOW')
                    result['alarms_before'] = model.state(session); model.verify_before(result['alarms_before'])
                    require(result['alarms_before']['template-ids'] == [{'_id': 1}, {'_id': 2}], 'OLD_ALARM_IDS_CHANGED')
                    result['templates_sha_before'] = shared.alarm_fingerprint(session, model)
                    require(result['templates_sha_before'] == ALARM_SHA, 'OLD_ALARM_CONTENTS_CHANGED')
                    result['epoch_sha256'] = session.epoch_sha256
                    flow.run(); result['business_success_verified'] = True
                except BaseException as exc:
                    result.update(state='FAILED', error=type(exc).__name__ + ': ' + str(exc))
                    cleanup_deadline = time.monotonic() + 45
                    signal.setitimer(signal.ITIMER_REAL, 45)
                    try:
                        flow.cleanup()
                    except BaseException as clean:
                        result['cleanup_error'] = type(clean).__name__ + ': ' + str(clean)
                finally:
                    if cleanup_deadline is None:
                        cleanup_deadline = time.monotonic() + 45
                    signal.setitimer(signal.ITIMER_REAL, max(.001, cleanup_deadline - time.monotonic()))
                    try:
                        result['notify_watch_child_started'] = flow.watch.process is not None
                        result['notify_watch_stop'] = flow.watch.stop()
                        result['notify_monitor_closed_verified'] = proof.monitor_closed(
                            result['notify_watch_stop'], result['notify_watch_child_started'])
                    except BaseException as observer:
                        result['notify_monitor_closed_verified'] = False
                        result['notify_watch_stop_error'] = type(observer).__name__ + ': ' + str(observer)
                    try:
                        flow.close()
                    except BaseException as close:
                        result['close_error'] = type(close).__name__ + ': ' + str(close)
                    result['timer_final'] = timer.read(session)
                    result['identity_after'] = model.identity(session)
                    result['alarms_after'] = model.state(session)
                    result['templates_sha_after'] = shared.alarm_fingerprint(session, model)
                    appop = session.android(['/system/bin/cmd', 'appops', 'get', '--user', '0', PACKAGE, 'POST_NOTIFICATION']).decode()
                    result['appop_after'] = notifications.parse_appop(appop)
                    require(result['alarms_before'] == result['alarms_after']
                        and result['templates_sha_before'] == result['templates_sha_after'], 'OLD_ALARMS_CHANGED')
                    if flow.baseline is not None:
                        _, final_tasks = flow.topology('terminal-preserved-tasks')
                        result['task_set_restored'] = final_tasks == flow.baseline
                    session.caller_status('clock-expiry-final-caller')
        if result['business_success_verified']:
            timer.empty(result['timer_final'])
            require(flow.owned == flow.closed and len(set(flow.owned)) == 2 and flow.c.pending is None
                and trial.owned is None and result['identity_before'] == result['identity_after']
                and result['appop_after']['allow_verified'] is True and 'close_error' not in result
                and result.get('task_set_restored') is True,
                'EXPIRY_SUCCESS_REQUIRES_IDENTITY_AND_TWO_NORMAL_CLOSES')
            require(result.get('notify_monitor_closed_verified') is True,
                    'NOTIFY_MONITOR_CLEANUP_REQUIRES_CHILD_READER_AND_BOTH_PIPE_EOF')
    except BaseException as exc:
        result.update(state='FAILED', business_success_verified=False,
                      terminal_error=type(exc).__name__ + ': ' + str(exc))
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0); signal.signal(signal.SIGALRM, prior)
        result.update(ui_actions=flow.c.actions if flow else 0, pending_effect=flow.c.pending if flow else None,
            owned_tasks=flow.owned if flow else [], normal_closed_tasks=flow.closed if flow else [],
            alert_tasks_self_finished=flow.alert_self_finished if flow else [],
            owned_task_remaining=trial.owned[0] if trial and trial.owned else None,
            owned_task_remove_calls=trial.removals if trial else 0, finished_utc=datetime.now(timezone.utc).isoformat())
        if ROOT.is_dir():
            tx.write_new(ROOT / 'result.json', result)
        tx.write_new(PUBLIC, result, alex_readable=True)
        print(json.dumps({k: result.get(k) for k in ('state', 'error', 'terminal_error', 'business_success_verified',
            'ui_actions', 'pending_effect', 'owned_timer_id', 'owned_tasks', 'normal_closed_tasks', 'owned_task_remaining')}))
    return 0 if result['business_success_verified'] else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--execute', action='store_true')
    if parser.parse_args().execute:
        raise SystemExit(execute())
    print(json.dumps({'state': 'PLAN_ONLY', 'UI_actions': 0, 'timer_writes': 0, 'alarm_writes': 0}))
