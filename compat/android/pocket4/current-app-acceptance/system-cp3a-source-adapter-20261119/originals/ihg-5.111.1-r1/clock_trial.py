"""Fresh Clock Trial adapter for the unchanged timer and continuation logic."""
from pathlib import Path
import re
import time
import types

PACKAGE = 'com.android.deskclock'


class Trial:
    def __init__(self, common, active_ref, active, scopes, session, phase_ref, action_lock):
        self.c, self.plan_ref, self.plan, self.scopes = common, active_ref, active, scopes
        self.s, self.phase_ref, self.action_lock = session, phase_ref, action_lock
        self.root = common.private_dir(Path(active['case_root']) / 'events', create=True)
        common.private_dir(Path(active['case_root']) / 'action-claims', create=True)
        self.tx = types.SimpleNamespace(write_new=common.write_new)
        self.owned = None; self.removals = 0; self.launches = 0; self.sequence = 0
        self.last_observation = None; self.storage_from_create = None
        self.flow = None; self.flow_lock = None; self.history = {}; self.observations = {}
        self.focus_ref = None; self.latest_intent = None; self.continuation = None
        self.result = {'state': 'NOT_STARTED', 'other_tasks_preserved': False,
                       'whole_app_production_ready': False, 'Binder_UID_cleanup_verified': False}
        self.scope_value = common.parse(common.read_ref(scopes[0]))
        self.runtime = common.packet_module(self.scope_value, 'app_runtime.py')
        self.flow_module = common.packet_module(self.scope_value, 'app_flow.py')
        self.guard_module = common.packet_module(self.scope_value, 'clock_guard.py')
        self.policy_module = common.packet_module(self.scope_value, 'clock_policy.py')
        self.focus_module = common.packet_module(self.scope_value, 'clock_focus.py')
        self.backend = Backend(self)

    def record(self, label, value):
        self.c.need(type(label) is str and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,119}', label),
                    'BOUNDED_PRIVATE_CLOCK_EVENT_NAME')
        self.sequence += 1
        ref = self.c.write_new(self.root / ('%04d-' % self.sequence + label + '.json'), value)
        self.history[label] = ref
        if label.startswith('intent-t'):
            self.latest_intent = (label[len('intent-'):], ref)
        return ref

    def phase(self):
        return self.runtime.validate_phase(self.c, self.phase_ref, self.plan_ref, self.plan)

    def launch(self):
        self.c.need(self.owned is None and self.flow is None and self.launches < 2 and
            self.phase()['phase'] == 'business', 'TWO_INDEPENDENT_ORIGINAL_CLOCK_LAUNCH_SCOPES_ONLY')
        self.action_lock.verify()
        ref = self.scopes[self.launches]; scope = self.c.parse(self.c.read_ref(ref))
        lock = self.c.locked(Path(scope['flow_root']) / 'flow.lock')
        lock.__enter__(); self.flow_lock = lock
        self.launches += 1  # A failed launch cannot reuse this scope or nonce.
        self.flow = self.flow_module.Flow(self.c, ref, 'launch', 'launch',
            self.phase()['deadline_monotonic_ns'] / 1000000000, self.guard_module,
            lambda runtime: self.policy_module.Policy(runtime),
            private_context={'phase_lease': self.phase_ref}, external_action_lock=self.action_lock)
        result = self.flow.launch(); selected = self.flow.selected_task()
        self.c.need(result['native_launch_acknowledged'] is True and result['cleanup_allowed'] is True,
                    'ACTUAL_NEW_CLOCK_NATIVE_LAUNCH_REQUIRED')
        self.owned = (selected['task'], set(selected['prelaunch_task_ids']))
        self.result['owned_task'] = selected['task']; self.record('launch-%d' % self.launches, result)
        self.flow.clock_phase('inspect', 'inspect')

    def close(self):
        self.c.need(self.owned is not None and self.flow is not None, 'OWNED_CLOCK_TASK_REQUIRED_FOR_CLOSE')
        self.flow.clock_phase('cleanup', 'cleanup')
        result = self.flow.cleanup()
        self.c.need(result.get('new_leaf_removed_and_verified') is True and
            result.get('other_tasks_preserved') is True and
            result['task_ids_after'] == sorted(self.owned[1]), 'ORIGINAL_NORMAL_CLOCK_TASK_REMOVAL_REQUIRED')
        self.record('closed-task-' + str(self.owned[0]), result)
        self.removals += 1; self.result['other_tasks_preserved'] = True
        self.flow.artifacts.revalidate(); self.flow.guard(attempted=True)
        self.release_flow(); self.owned = None; self.focus_ref = None

    def release_flow(self):
        """Only host FDs/locks; this method sends no Android task operation."""
        primary = None
        if self.flow is not None:
            try:
                self.flow.close()
            except BaseException as error:
                primary = error
            finally:
                self.flow = None
        if self.flow_lock is not None:
            try:
                self.flow_lock.__exit__(None, None, None)
            except BaseException as error:
                primary = primary or error
            finally:
                self.flow_lock = None
        if primary is not None:
            raise primary

    def begin_final_cleanup(self, phase_ref):
        value = self.runtime.validate_phase(self.c, phase_ref, self.plan_ref, self.plan)
        self.c.need(value['phase'] == 'final_cleanup', 'EXACT_ORIGINAL_FINAL_CLEANUP_WINDOW')
        self.phase_ref = phase_ref; self.s.deadline = value['deadline_monotonic_ns'] / 1000000000
        if self.flow is not None:
            self.flow.clock_phase('inspect', 'final-inspect', phase_ref)

    def ready_focus(self, allow_permission=False):
        self.c.need(allow_permission is False and self.owned is not None and self.flow is not None,
                    'CLOCK_FOCUS_REQUIRES_ONLY_ITS_ACTUAL_OWNED_TASK')
        task, preserved = self.owned; deadline = time.monotonic() + 10
        previous = None; previous_row = None; count = 0
        while deadline - time.monotonic() > 6:
            raw = self.s.android(self.c.FOREGROUND, 6)
            row = self.s.last_command; current = self.focus_module.focus_metadata(raw.decode('utf-8', 'strict'))
            count += 1; self.record('wm-focus-readiness', {'observation': current, 'actual_command': row})
            valid = (current.get('verified') is True and current.get('task') == task
                and current.get('package') == PACKAGE and current.get('activity') == PACKAGE + '.DeskClock')
            if valid and current == previous:
                stacks = self.s.android(self.c.STACKS, 15); stack_row = self.s.last_command
                roots, tasks = self.flow.tasks.parse_stacks(stacks.decode('utf-8', 'strict'))
                self.c.need(self.flow.tasks.exact_leaf(roots, task, PACKAGE) and tasks == preserved | {task},
                            'ORIGINAL_CLOCK_READY_TASK_SCOPE_CHANGED')
                value = {'schema': 'pocket4-final-clock-focus-v1', 'scope_sha256': self.flow.scope_ref['sha256'],
                    'phase_lease': self.phase_ref, 'focus': current, 'reads': [previous_row, row], 'stacks': stack_row}
                self.focus_ref = self.record('wm-focus-ready', value)
                self.guard_module.verify_focus(self.flow, self.focus_ref, self.flow.selected_task())
                return current
            previous, previous_row = (current, row) if valid else (None, None)
            time.sleep(.2)
        raise RuntimeError('OWNED_FOCUS_NOT_READY_WITHIN_BOUNDED_READS')

    def _ui_context(self, operation, *, action_claim=None, observation=None, previous=None):
        self.c.need(self.flow is not None and self.owned is not None and self.focus_ref is not None,
                    'EXACT_OBSERVED_OWNED_CLOCK_UI_CONTEXT')
        _, claim_ref = self.flow.scope_module.load_owned_task(self.flow.bound)
        step = self.flow.root / 'steps' / ('ui-%02d-%s' % (self.flow._step_number + 1, operation))
        argv = self.flow.modules['business_ui_entry.py'].entry_argv(self.flow.scope_ref, 'backend', step.name, 'command-001')
        grant = self.action_lock.authorize(self.flow.scope_ref, step, self.phase_ref, argv)
        return {'schema': 'pocket4-final-clock-ui-context-v1', 'phase_lease': self.phase_ref,
            'focus': self.focus_ref, 'owned_claim': claim_ref, 'observation': observation,
            'previous_observation': previous, 'action_claim': action_claim, 'action_lock_grant': grant}, step

    def observe(self, label, focus):
        self.c.need(self.flow is not None and self.owned is not None and focus.get('task') == self.owned[0]
            and focus.get('package') == PACKAGE, 'CLOCK_OBSERVATION_REQUIRES_ACTUAL_OWNED_FOCUS')
        self.s.guard()
        context, wanted = self._ui_context('observe')
        value, step = self.flow.ui({'op': 'observe', 'accessibility_mode': 'none'}, case_context=context)
        self.c.need(step == wanted, 'EXACT_NEW_OBSERVATION_STEP')
        native = value.get('native', value)
        self.c.need(value.get('ok') is True and value.get('outcome_unknown') is not True
            and native.get('ok') is True and native.get('accessibility_mode_restoration_verified') is True
            and value['screenshot']['scope']['package'] == focus['package']
            and value['screenshot']['scope']['window_token'] == focus['window_token'], 'ORIGINAL_CLOCK_OBSERVATION_UNVERIFIED')
        result_ref = self.c.regular(step / 'observed-result.json', contents=False)
        png = self.c.regular(step / 'observation.png', 32 * 1024 * 1024, contents=False)
        observed = {'schema': 'pocket4-final-clock-observation-v1', 'scope_sha256': self.flow.scope_ref['sha256'],
            'focus': self.focus_ref, 'result': result_ref, 'png': png, 'label': label}
        self.observations[label] = self.record(label, observed)
        self.last_observation = value
        self.guard_module.verify_observation(self.flow, self.observations[label], self.flow.selected_task())
        self.s.guard()
        return native.get('nodes', [])


class Backend:
    def __init__(self, trial):
        self.t = trial

    def dispatch(self, command, native_observer):
        t = self.t; c = t.c
        c.need(t.latest_intent is not None and t.continuation is not None and
            t.continuation.pending == t.latest_intent[0] and callable(native_observer),
            'ACTUAL_PENDING_ORIGINAL_CONTINUATION_REQUIRED')
        ident, intent_ref = t.latest_intent
        request_ref = t.history['request-' + ident]; request = c.parse(c.read_ref(request_ref))
        intent = c.parse(c.read_ref(intent_ref))
        c.need(command == intent['command'] and command['op'] == 'click', 'UNCHANGED_ORIGINAL_NATIVE_CLICK_INTENT')
        old_ref = t.observations[request['observation']]
        current_ref = t.observations[t.continuation.latest]
        step = t.flow.root / 'steps' / ('ui-%02d-click' % (t.flow._step_number + 1))
        claim = {'schema': 'pocket4-final-clock-action-claim-v1', 'scope_sha256': t.flow.scope_ref['sha256'],
            'ui_step': str(step), 'number': int(ident[1:3]), 'id': ident, 'request': request_ref, 'intent': intent_ref,
            'observation': current_ref, 'previous_observation': old_ref, 'automatic_retry': False}
        claim_ref = c.write_new(Path(t.plan['case_root']) / 'action-claims' / (ident + '.json'), claim, 0o400)
        context, wanted = t._ui_context('click', action_claim=claim_ref, observation=current_ref, previous=old_ref)
        c.need(step == wanted, 'ONE_EXACT_ORIGINAL_CLICK_STEP')
        typed = {k: command[k] for k in ('op', 'selector', 'accessibility_mode', 'method')}
        primary = None
        try:
            response, observed_step = t.flow.ui(typed, case_context=context)
            c.need(observed_step == step, 'ACTUAL_TYPED_CLICK_STEP_CHANGED')
        except BaseException as error:
            primary = error
        try:
            self.deliver_native(step, context, native_observer)
        except BaseException as error:
            if primary is None:
                primary = error
            else:
                primary.add_note('ACTUAL_NATIVE_BOUNDARY_READ:' + type(error).__name__)
        if primary is not None:
            raise primary
        return response

    def deliver_native(self, step, context, observer):
        t = self.t; c = t.c
        parent = c.parse(c.regular(step / 'command-001.result.json')[0])
        c.need(parent['host_retirement_proved'] is True and parent['evidence_complete'] is True,
                'UNRETIRED_UI_CHILD_CANNOT_PROVIDE_RECONCILED_NATIVE_ACK')
        parent_intent = c.regular(step / 'command-001.intent.json', contents=False)
        journal = step / 'command-001-bound'; found = []
        for path in sorted(journal.glob('native-ui-*.boundary.json')):
            ref = c.regular(path, contents=False); value = c.parse(c.read_ref(ref))
            if value['mutation'] is not True:
                continue
            c.need(value['schema'] == 'pocket4-final-original-native-ui-return-v1'
                and value['scope_sha256'] == t.flow.scope_ref['sha256']
                and value['parent_intent_sha256'] == parent_intent['sha256']
                and value['observation'] == context['observation']
                and value['automatic_retry'] is False and value['business_success_verified'] is False
                and Path(value['request']['path']).parent == journal
                and Path(value['response']['path']).parent == journal, 'ACTUAL_ORIGINAL_NATIVE_UI_RETURN_CHAIN')
            request = c.parse(c.read_ref(value['request'])); response = c.parse(c.read_ref(value['response']))
            c.need(request.get('op') == 'click', 'ONLY_ORIGINAL_CLOCK_NATIVE_CLICK_BOUNDARY')
            found.append((request, response, ref))
        c.need(len(found) <= 1, 'ONE_NATIVE_CLICK_RETURN_NO_REPLAY')
        for request, response, ref in found:
            t.record('actual-native-boundary-' + t.latest_intent[0], ref)
            observer(request, response)  # Unchanged literal native return, even if final capture failed.
