"""Original current-APK natural expiry/stop/delete; no historical transport."""
from pathlib import Path
from datetime import datetime, timezone
import copy,hashlib,json,re,time
PACKAGE = 'com.android.deskclock'
MAIN = PACKAGE + '.DeskClock'
ALERT = PACKAGE + '.timer.ExpiredTimersActivity'
KEY = '0|com.android.deskclock|2147483644|null|10063'
DURATION = 60000
ALARM_SHA = '655c545ee9487dc380100d6300376d0bb82d0d12beddd96f283ab7814ff19fea'
PREINPUT_ERRORS = frozenset(('AMBIGUOUS_MATCH', 'INCOMPLETE_TREE_NO_ACTION_TAKEN',
    'WINDOW_CHANGED_NO_ACTION_TAKEN', 'WINDOW_BOUNDS_CHANGED_NO_ACTION_TAKEN',
    'TARGET_CHANGED_NO_ACTION_TAKEN', 'AMBIGUOUS_MATCH_NO_ACTION_TAKEN',
    'MATCH_SET_CHANGED_NO_ACTION_TAKEN', 'ACCESSIBILITY_TREE_NOT_READY_NO_ACTION_TAKEN'))

def need(ok, reason):
    if not ok:
        raise RuntimeError(reason)

def sha(raw):
    return hashlib.sha256(raw).hexdigest()

def activity(value):
    return PACKAGE + value if value.startswith('.') else value

def no_input_error(exc, helper):
    detail = getattr(exc, 'details', {})
    # Exact eb24 Python wrapper exposes this native error only after verified
    # restoration. Actual a536 ActionRunner sets actionAttempted BEFORE click;
    # these named branches all occur before that store. Other errors retain both
    # pending effects even if a caller supplied an unsupported false field.
    return (isinstance(exc, helper.ControlError) and str(exc) in PREINPUT_ERRORS
        and detail.get('outcome_unknown') is False and detail.get('automatic_retry') is False
        and detail.get('accessibility_mode_restoration_verified') is True)

def actual_target_matches(target, selector):
    mapping = {'id': 'resource-id', 'text': 'text', 'desc': 'content-desc',
        'class': 'class', 'package': 'package', 'enabled': 'enabled', 'clickable': 'clickable'}
    return isinstance(target, dict) and all(target.get(mapping[k]) == v for k, v in selector.items())

def cleanup_pause_proof(running, paused, uptime_before, uptime_after, unused):
    need(running['state'] == 1 and paused['state'] == 2
         and running['id'] == paused['id'] and running['length_ms'] == paused['length_ms'] == DURATION
         and running['total_length_ms'] == paused['total_length_ms'] == DURATION
         and running['last_start_ms'] > 0 and uptime_before <= uptime_after
         and uptime_before >= running['last_start_ms'] - 10
         and paused['last_start_ms'] == paused['last_wall_ms'] == unused,
         'CLEANUP_PAUSE_ID_OR_CLOCKS_CHANGED')
    # Actual Timer.pause() stores getRemainingTime(), without clamping to zero.
    # Negative values are legitimate when the expiry scheduler has failed. The
    # exact prior start/remaining and two uptime reads bound the permitted value.
    lower = running['remaining_ms'] - max(0, uptime_after - running['last_start_ms']) - 10
    upper = running['remaining_ms'] - max(0, uptime_before - running['last_start_ms']) + 10
    need(lower <= paused['remaining_ms'] <= upper, 'CLEANUP_PAUSE_REMAINING_OUTSIDE_EXACT_CLOCK_INTERVAL')
    return {'before_uptime_ms': uptime_before, 'after_uptime_ms': uptime_after,
        'remaining_lower_bound_ms': lower, 'remaining_upper_bound_ms': upper,
        'actual_remaining_ms': paused['remaining_ms'], 'negative_remaining_is_source_defined': True}

def owned_timer(value, ident, duration):
    need(duration == DURATION and value['ids'] == [ident] and len(value['timers']) == 1
         and value['stopwatch'] == {}, 'SOLE_CURRENT_EXPIRY_TIMER_REQUIRED')
    item = value['timers'][0]
    need(item['id'] == ident and item['length_ms'] == DURATION
         and item['label'] in ('', None) and item['delete_after_use'] is False
         and item['state'] in (1, 2, 3, 4), 'OWNED_TIMER_FIELDS_CHANGED')
    if item['state'] == 3:
        # Same installed Timer.expire contract already observed in expiry05.
        # Only the byte-pinned 433ff current run can qualify this new fixture.
        need(item['total_length_ms'] == 0 and item['remaining_ms'] <= 0
             and item['last_start_ms'] > 0 and item['last_wall_ms'] > 0,
             'EXPIRED_TIMER_FIELDS_NOT_VERIFIED')
    else:
        need(item['total_length_ms'] == DURATION, 'NONEXPIRED_TIMER_LENGTH_CHANGED')
    return item

def exact_alert(roots, task):
    found = [(r, c) for r in roots.values() for c in r['children'] if c['id'] == task]
    return bool(len(found) == 1 and found[0][0]['display'] == 0 and found[0][0]['user'] == 0
        and found[0][1]['user'] == 0 and found[0][1]['component'].split('/')[0] == PACKAGE
        and activity(found[0][1]['component'].split('/', 1)[1]) == ALERT)

def notification_records(raw):
    lines = raw.decode('utf-8', 'strict').splitlines()
    need(lines and lines[0] == "Current Notification Manager state (filtered to 'com.android.deskclock'):",
         'EXACT_CLOCK_NMS_HEADER_REQUIRED')
    starts = [i for i, line in enumerate(lines) if line == '  Notification List:']
    need(len(starts) == 1, 'ACTIVE_NMS_LIST_REQUIRED')
    body = []
    for line in lines[starts[0] + 1:]:
        if line.strip() and not line.startswith('    '):
            break
        body.append(line)
    if not '\n'.join(body).strip():
        return []
    blocks = re.split(r'(?=^    NotificationRecord\()', '\n'.join(body), flags=re.M)
    need(not blocks[0].strip(), 'UNPARSED_ACTIVE_NOTIFICATION')
    records = []
    for block in blocks[1:]:
        header = block.splitlines()[0]
        need(re.search(r'\bpkg=com\.android\.deskclock\b', header)
             and 'user=UserHandle{0}' in header and re.search(r'\buid=10063\b', block),
             'ACTIVE_NOTIFICATION_IDENTITY_CHANGED')
        keys = re.findall(r'\bkey=(0\|com\.android\.deskclock\|[0-9]+\|null\|10063)\b', block)
        need(len(set(keys)) == 1, 'EXACT_ACTIVE_NOTIFICATION_KEY_REQUIRED')
        records.append({'key': keys[0], 'uid': 10063, 'android_user': 0,
            'timer_channel': bool(re.search(r'\bchannel=TimerModelNotification\b', block)
                or "mId='TimerModelNotification'" in block),
            'full_screen_pending_intent_present': bool(re.search(r'\bfullscreenIntent=PendingIntent\{', block)),
            'record_sha256': sha(block.encode()), 'desktop_popup_observed': False})
    return records

def make_flow(core, base):
    class ExpiryFlow(core.Flow):
        def __init__(self, trial, loop, timer, result, evidence_root, continuation_factory):
            super().__init__(trial, loop, timer, result, evidence_root, continuation_factory)
            self.deadline = time.monotonic() + 230
            self.baseline = None
            self.alert_task = None
            self.alert_self_finished = []
            self.stop_dispatched = False
            leaf = base.exact_leaf
            base.exact_leaf = lambda roots, task: exact_alert(roots, task) if task == self.alert_task else leaf(roots, task)
            prior_focus = trial.focus_allowed
            def focus_allowed(current, allow_permission=True):
                if not prior_focus(current, False) or current.get('package') != PACKAGE:
                    return False
                expected = ALERT if self.t.owned and self.t.owned[0] == self.alert_task else MAIN
                return activity(current.get('activity', '')) == expected and activity(current.get('focused_activity', '')) == expected
            trial.focus_allowed = focus_allowed

        def clear(self):
            need(self.c.pending is None and self.effect_pending is None and self.close_pending is None,
                 'UNKNOWN_EXPIRY_INPUT_EFFECT_OR_CLOSE_RETAINED')

        def topology(self, label):
            roots, tasks = self.t.stacks(label)
            if self.baseline is not None:
                need(all(roots.get(k) == v for k, v in self.baseline.items()),
                     'ORIGINAL_TASK_STRUCTURE_CHANGED')
                old_tasks = {c['id'] for r in self.baseline.values() for c in r['children']}
                need(old_tasks <= tasks, 'ORIGINAL_TASK_SET_CHANGED')
            return roots, tasks

        def baseline_tasks(self):
            return {c['id'] for r in self.baseline.values() for c in r['children']}

        def launch(self, label):
            self.clear()
            need(self.t.launches < 2, 'EXPIRY_MAXIMUM_TWO_NATIVE_LAUNCHES')
            before = self.t.launches
            try:
                super().launch(label)
            except BaseException:
                if self.t.launches == before and self.t.owned is None:
                    self.t.record('launch-precondition-no-dispatch', {'label': label, 'native_launch_calls': before})
                    self.c.pending = None
                raise

        def act(self, label, node, expected_state=None):
            need(self.number < 12, 'EXPIRY_INPUT_LIMIT')
            return super().act(label, node, expected_state)

        def notifications(self, label):
            raw = self.t.s.android(['/system/bin/dumpsys', 'notification', '--package', PACKAGE], 12)
            self.t.tx.write_new(self.evidence_root / (label + '-notifications-private.txt'), raw)
            value = {'records': notification_records(raw), 'bytes': len(raw), 'sha256': sha(raw),
                     'observed_uptime_ms': self.uptime(), 'desktop_popup_or_sound_proven': False}
            self.r.setdefault('notifications', {})[label] = value
            return value

        def service(self, label):
            raw = self.t.s.android(['/system/bin/dumpsys', 'activity', 'services', PACKAGE], 12)
            self.t.tx.write_new(self.evidence_root / (label + '-services-private.txt'), raw)
            text = raw.decode('utf-8', 'strict')
            self.r.setdefault('services', {})[label] = {'bytes': len(raw), 'sha256': sha(raw),
                'clock_lines': [line for line in text.splitlines() if PACKAGE in line],
                'actual_app_process_pids': sorted(set(int(x) for x in re.findall(
                    r'(?m)^\s*app=ProcessRecord\{[^\n{}]*? (\d+):com\.android\.deskclock/u0a63\}', text)))}

        def wait_expiry(self):
            self.clear()
            need(self.t.owned is None and self.timer_id is not None, 'CLOSED_OWNED_TIMER_REQUIRED')
            created = self.r['phases']['created-running']['timers'][0]
            due = created['last_start_ms'] + created['remaining_ms']
            samples = []
            while time.monotonic() < self.deadline - 70:
                current = self.m.read(self.t.s)
                item = owned_timer(current, self.timer_id, DURATION)
                now = self.uptime()
                samples.append({'uptime_ms': now, 'state': item['state']})
                self.r['expiry_timing'] = {'expected_due_ms': due, 'samples': samples,
                    'created_start_ms': created['last_start_ms']}
                if item['state'] == 3:
                    need(due - 1000 <= item['last_start_ms'] <= now + 10
                         and due - 1000 <= now <= due + 25000, 'OWNED_EXPIRY_TIME_NOT_BOUND')
                    self.r['phases']['expired'] = current
                    self.r['expiry_timing']['observed_uptime_ms'] = now
                    self.r['actual_expiry_verified'] = True
                    self.t.record('actual-expired-owned-timer', current)
                    return
                need(item['state'] == 1 and now <= due + 25000,
                     'OWNED_TIMER_DID_NOT_EXPIRE_WITHIN_FIXED_GRACE')
                time.sleep(1)
            raise RuntimeError('OWNED_EXPIRY_BOUNDED_WAIT_EXHAUSTED')

        def claim_alert(self, cleanup=False):
            self.clear()
            need(self.t.owned is None, 'ALERT_CLAIM_REQUIRES_CLOSED_NATIVE_TASK')
            roots, tasks = self.topology('possible-expired-alert')
            old = self.baseline_tasks()
            if roots == self.baseline and tasks == old:
                self.r['new_alert_task_observed'] = False
                return False
            extra = tasks - old
            need(len(extra) == 1, 'NEW_ALERT_TASK_MUST_BE_SOLE_AND_SOURCE_BOUND')
            task = next(iter(extra))
            need(exact_alert(roots, task), 'EXTRA_TASK_IS_NOT_OWNED_EXPIRED_TIMER_ALERT')
            item = owned_timer(self.m.read(self.t.s), self.timer_id, DURATION)
            need(item['state'] == 3 and self.r.get('owned_timer_id') == self.timer_id
                 and 'created-running' in self.r['phases'], 'ALERT_HAS_NO_THIS_SOLE_EXPIRED_TIMER')
            self.alert_task = task
            self.t.owned = (task, old)
            self.r['owned_alert_task'] = task
            self.t.record('source-bound-expired-alert', {'task': task, 'activity': ALERT,
                'sole_timer_id': self.timer_id, 'cleanup_only': cleanup,
                'full_screen_intent_has_no_timer_id': True, 'native_launch_performed': False})
            self.c.observe('owned-expired-alert')
            need(activity(self.t.last_observation['screenshot']['scope']['activity']) == ALERT,
                 'OBSERVED_ALERT_ACTIVITY_CHANGED')
            self.r['new_alert_task_observed'] = True
            return True

        def stop(self, label):
            self.clear()
            need(not self.stop_dispatched and self.number < 12 and time.monotonic() < self.deadline,
                 'EXPIRED_STOP_ALREADY_ATTEMPTED_OR_OUTSIDE_BUDGET')
            need(owned_timer(self.m.read(self.t.s), self.timer_id, DURATION)['state'] == 3,
                 'STOP_REQUIRES_THIS_SOLE_EXPIRED_TIMER')
            self.c.observe('fresh-' + label)
            focus = self.t.ready_focus(allow_permission=False)
            need(focus['window_token'] == self.t.last_observation['screenshot']['scope']['window_token'],
                 'EXPIRED_STOP_WINDOW_CHANGED')
            node = self.node('fab', ('Stop', 'Stop timer', 'Stop timers', 'Stop all timers', 'Reset', 'Reset timer', 'Reset timers'))
            selector = {k: node[n] for k, n in (('id', 'resource-id'), ('text', 'text'), ('desc', 'content-desc')) if node.get(n)}
            selector.update({'class': node['class'], 'package': PACKAGE, 'enabled': True, 'clickable': True})
            need(owned_timer(self.m.read(self.t.s), self.timer_id, DURATION)['state'] == 3,
                 'EXPIRED_SET_CHANGED_BEFORE_STOP')
            self.number += 1
            ident = 'e%02d-' % self.number + label
            request = {'op': 'click', 'expected_package': PACKAGE, 'display': 0,
                'accessibility_mode': 'none', 'method': 'accessibility', 'selector': selector}
            # Both journals precede native dispatch. Native ACK never clears the
            # asynchronous timer effect; only exact reset readback does that.
            self.effect_pending = {'operation': 'reset', 'native_request_id': ident,
                'timer_id': self.timer_id, 'duration_ms': DURATION, 'automatic_retry': False}
            self.c.pending = ident
            self.t.record('expiry-stop-intent-' + ident, {'request': request, 'focus': focus,
                'observed_node': node, 'effect': copy.deepcopy(self.effect_pending)})
            need(self.t.ready_focus(allow_permission=False) == focus, 'STOP_PREINPUT_FOCUS_CHANGED')
            self.stop_dispatched = True
            self.c.actions += 1
            self.t.s.guard()
            try:
                reply = self.t.s.helper.ui(request)
            except BaseException as exc:
                details = getattr(exc, 'details', {})
                self.t.record('expiry-stop-exception-' + ident, {'error': str(exc), 'details': details})
                self.t.s.guard()
                if no_input_error(exc, self.t.s.helper):
                    self.t.record('expiry-stop-explicit-no-input', {'intent': self.effect_pending,
                        'automatic_retry': False, 'stop_request_will_not_be_replayed': True})
                    self.c.pending = None
                    self.effect_pending = None
                raise
            self.t.s.guard()
            self.t.record('expiry-stop-native-ack-' + ident, reply)
            target = reply.get('actual_target', {})
            need(reply.get('ok') is True and reply.get('performed') == 'click'
                 and reply.get('outcome_unknown') is not True
                 and reply.get('accessibility_mode_restoration_verified') is True
                 and actual_target_matches(target, selector),
                 'EXPIRED_STOP_ACK_UNKNOWN_NO_REPLAY')
            self.c.pending = None
            until = min(self.deadline, time.monotonic() + 12)
            while time.monotonic() < until:
                value = self.m.read(self.t.s)
                item = owned_timer(value, self.timer_id, DURATION)
                roots, tasks = self.topology('stop-exact-effect-readback')
                reset = (item['state'] == 4 and item['remaining_ms'] == DURATION
                    and item['last_start_ms'] == item['last_wall_ms'] == self.m.UNUSED)
                is_alert = self.t.owned is not None and self.t.owned[0] == self.alert_task
                expected = self.baseline_tasks() if is_alert else self.baseline_tasks() | {self.t.owned[0]}
                if reset and tasks == expected:
                    if is_alert:
                        need(self.alert_task not in roots and roots == self.baseline, 'RESET_ALERT_TASK_NOT_GONE')
                        self.alert_self_finished.append(self.alert_task)
                        self.t.owned = None
                    self.r['phases']['stopped-reset'] = value
                    self.complete_effect('reset', value)
                    self.r['stop_reconciliation'] = {'native_request_id': ident,
                        'input_acknowledged': True, 'same_id_reset_verified': True,
                        'alert_self_finished': is_alert, 'action_replayed': False}
                    if self.t.owned is not None:
                        self.c.observe('after-' + label)
                    return
                time.sleep(.3)
            raise RuntimeError('ACKNOWLEDGED_STOP_RESET_NOT_READ_BACK')

        def close(self):
            self.clear()
            need(self.t.owned is None or self.t.owned[0] != self.alert_task,
                 'EXPIRED_ALERT_RETAINED_UNTIL_RESET_SELF_FINISH')
            return super().close()

        def delete_reset(self, label):
            self.clear()
            if self.t.owned is None:
                self.launch(label + '-main')
            self.c.observe(label + '-reset-timer')
            self.read(label + '-before-delete', 4)
            self.act('delete', self.node('left_button', ('Delete',)), 4)
            self.deleted(label + '-deleted')

        def run(self):
            before = self.read('before')
            self.m.empty(before)
            need(self.notifications('before')['records'] == [], 'ACTIVE_CLOCK_NOTIFICATION_BASELINE_NOT_EMPTY')
            roots, _ = self.topology('original-task-baseline')
            self.baseline = copy.deepcopy(roots)
            self.launch('initial')
            self.setup((0, 0, 0))
            for digit, expected in (('1', (0, 0, 1)), ('0', (0, 0, 10)), ('0', (0, 1, 0))):
                self.act('digit-' + digit, self.node('timer_setup_digit_' + digit, (digit,)))
                self.setup(expected)
            self.m.empty(self.read('before-start'))
            self.creation_uptime_before = self.uptime()
            self.creation_dispatch_before = self.c.actions
            self.act('create-start', self.node('fab', ('Start',)))
            self.claim_created()
            self.close()
            self.service('after-normal-close')
            self.wait_expiry()
            self.service('actual-expired')
            self.observe_scheduler('actual-expired')
            posted = self.notifications('actual-expired')
            own = [r for r in posted['records'] if r['key'] == KEY and r['timer_channel']]
            self.r['actual_expired_notification_posted'] = len(own) == 1
            self.r['full_screen_pending_intent_present'] = len(own) == 1 and own[0]['full_screen_pending_intent_present']
            if not self.claim_alert():
                self.launch('expired-main')
                self.r['actual_expired_main_window_observed'] = True
            self.stop('stop-expired')
            self.delete_reset('final')
            after = self.notifications('deleted')
            for attempt in range(2):
                if not after['records']:
                    break
                time.sleep(.3)
                after = self.notifications('deleted-readback-' + str(attempt))
            need(after['records'] == [], 'OWNED_TIMER_NOTIFICATION_NOT_CLEARED')
            need(self.r['actual_expired_notification_posted'], 'OWNED_EXPIRED_NOTIFICATION_NOT_VERIFIED')
            self.r['state'] = 'CURRENT_CLOCK_TIMER_EXPIRY_STOP_DELETE_VERIFIED_CLEAN'

        def cleanup(self, cleanup_until):
            self.r['cleanup'] = {'original_failure_retained': True, 'new_inputs': 0,
                'input_pending': self.c.pending, 'timer_effect_pending': self.effect_pending,
                'close_pending': self.close_pending}
            if self.c.pending is not None or self.effect_pending is not None or self.close_pending is not None:
                return
            need(time.monotonic() < cleanup_until, 'EXPIRY_CLEANUP_DEADLINE_EXPIRED')
            self.deadline = min(cleanup_until - 5, time.monotonic() + 40)
            current = self.m.read(self.t.s)
            if not current['ids']:
                self.m.empty(current)
                self.r['cleanup']['empty_timer_readback'] = True
                return
            need(self.timer_id is not None and self.r.get('owned_timer_id') == self.timer_id,
                 'NO_DURABLY_CLAIMED_TIMER_NO_CLEANUP_INPUT')
            item = owned_timer(current, self.timer_id, DURATION)
            before = self.c.actions
            if self.t.owned is None:
                if item['state'] != 3 or not self.claim_alert(cleanup=True):
                    self.launch('cleanup')
            self.c.observe('cleanup-owned-timer')
            if item['state'] == 3:
                self.stop('cleanup-stop-expired')
                self.delete_reset('cleanup')
            else:
                if item['state'] == 1:
                    running = copy.deepcopy(item)
                    pause_before = self.uptime()
                    self.act('cleanup-pause', self.node('fab', ('Pause', 'Stop')), 1)
                    item = owned_timer(self.read('cleanup-paused', 2), self.timer_id, DURATION)
                    proof = cleanup_pause_proof(running, item, pause_before, self.uptime(), self.m.UNUSED)
                    self.t.record('cleanup-pause-clock-interval', proof)
                    self.complete_effect('pause', self.r['phases']['cleanup-paused'])
                self.act('cleanup-delete', self.node('left_button', ('Delete',)), item['state'])
                self.deleted('cleanup-deleted')
            self.r['cleanup'].update(new_inputs=self.c.actions - before, exact_timer_removed=True)
    return ExpiryFlow
