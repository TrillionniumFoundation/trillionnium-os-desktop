"""Independent final-Main flow. No historical Flow is constructed or patched.

The caller supplies the new packet's full guard and original per-App policy.
Only policy-admitted held commands, one native launch and exact owned removal
are available. Each new launch requires a different immutable recorder scope.
"""
import functools
import json
import os
from pathlib import Path
import time
import types

ACTION_LOCK = '/run/lock/android-digitalis-actions.lock'


class Flow:
    def __init__(self, common, scope_ref, phase, step_name, deadline, guard_module,
                 policy_factory, *, private_context=None, external_action_lock=None):
        self.c = common
        self.scope_ref = scope_ref; self.scope = common.parse(common.read_ref(scope_ref))
        self.scope_module, self.modules = common.support(self.scope['support_manifest'])
        self.support_sha256 = self.scope['support_manifest']['sha256']
        self.root = common.private_dir(self.scope['flow_root'])
        self.phase = phase; self.deadline = deadline; self.closed = False
        self.action_attempted = False; self._android_mutation = False
        self._private_backend_transport = False; self.launch_claimed = False
        self.command_index = 0; self.total_commands = 0; self._step_number = 0
        self.private_context = private_context; self.view = None; self.bound = None
        self.external_action_lock = external_action_lock
        self.artifacts = None; self.receipt_witness = None
        self.guard_module = guard_module; self.policy_factory = policy_factory
        self.plan = common.parse(common.read_ref(self.scope['phase_plan']))
        self.identity = common.parse(common.read_ref(self.scope['actual_resolution_receipt']))
        self.helper_identities = [common.parse(common.read_ref(r))
                                  for r in self.scope['installed_helper_receipts']]
        self.tasks = self.scope_module.task_functions()
        self.recorder = types.SimpleNamespace(write_new=common.write_new)
        common.need(type(deadline) in (int, float) and time.monotonic() < deadline,
                    'FRESH_BOUNDED_PHASE_REQUIRED')
        self._new_step(step_name, 'phase', None, False)
        try:
            journal = common.private_dir(self.step / 'held-context', create=True)
            def no_bootstrap_commands(*args):
                raise RuntimeError('FLOW_COMMANDS_REQUIRE_PER_APP_POLICY_AND_RECORDER')
            self.view = common.MainView(self.scope['business_baseline'],
                self.scope['business_qualification'], journal, no_bootstrap_commands,
                support_ref=self.scope['support_manifest'])
            self.baseline_schema = self.view.baseline.value['schema']
            self.binding = types.SimpleNamespace(target=self.view.target)
            self.artifacts = common.HeldArtifacts(self.view.target, [self.identity] + self.helper_identities)
            self.bound = self.scope_module.ScopeBinding(scope_ref=scope_ref,
                baseline_ref=self.scope['business_baseline'],
                qualification_ref=self.scope['business_qualification'],
                support_ref=self.scope['support_manifest'],
                full_guard=functools.partial(guard_module.full_guard, runtime=self))
            guard_module.prepare(runtime=self)
            self.policy = policy_factory(self)
            self.native_timeout = getattr(self.policy, 'native_timeout', 70)
            common.need(self.native_timeout in (45, 70), 'ORIGINAL_PER_APP_NATIVE_TIMEOUT_REQUIRED')
            self._bridge()
            def record(kind, value):
                common.write_new(self.step / ('transport-%03d.%s.json' %
                    (value['sequence'], kind)), value)
            self.transport = self.scope_module.BoundArun(target=self.view.target,
                environment=self.view.environment, binding=self.bound, record=record,
                runner=lambda argv, **options: self.bridge.runner(argv, **options))
            self.guard()
        except BaseException as primary:
            for obj in (self.receipt_witness, self.artifacts, self.view):
                if obj is not None:
                    try:
                        obj.close()
                    except BaseException as secondary:
                        primary.add_note('FLOW_CONSTRUCTION_CLOSE:' + type(secondary).__name__)
            raise

    def _new_step(self, name, operation, request, mutation, extra=None):
        self.c.need(type(name) is str and self.c.re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,63}', name),
                    'EXACT_NEW_STEP_NAME_REQUIRED')
        self.step = self.c.private_dir(self.root / 'steps' / name, create=True)
        self.c.write_new(self.step / 'intent.json', {'scope': self.scope, 'phase': self.phase,
            'operation': operation, 'request': request, 'mutation': mutation,
            'automatic_retry': False, 'case_context': extra})
        self.command_index = 0

    def _bridge(self):
        self.bridge = self.scope_module.RecorderBridge(self, self.bound)

    def clock_phase(self, phase, step_name, phase_lease=None):
        self.c.need(self.plan['kind'] == 'clock_timer' and not self.closed and
                    phase in ('inspect', 'cleanup'), 'ONLY_ORIGINAL_CLOCK_PHASE_TRANSITION')
        if phase_lease is not None:
            lease_module = self.c.packet_module(self.scope, 'app_runtime.py')
            value = lease_module.validate_phase(self.c, phase_lease, self.scope['phase_plan'], self.plan)
            self.c.need(value['phase'] == 'final_cleanup', 'ONLY_ONCE_BOUNDED_CLOCK_FINAL_CLEANUP')
            self.phase_lease_ref = phase_lease
            self.private_context = {'phase_lease': phase_lease}
            self.deadline = value['deadline_monotonic_ns'] / 1000000000
        self.phase = phase
        self._new_step(step_name, 'phase', None, False); self._bridge()
        self.guard()

    def guard(self, attempted=False, *, action_attempted=None):
        attempted = attempted if action_attempted is None else action_attempted
        self.c.need(type(attempted) is bool and not self.closed and
                    time.monotonic() < self.deadline, 'OPEN_ORIGINAL_BOUNDED_PHASE_REQUIRED')
        self.c.match_held(self.view.target, self.view.baseline, self.scope_module)
        return self.bound.guard(action_attempted=attempted)

    def bind(self):
        self.guard()
        return self.binding

    def android(self, argv, timeout=20, *, mutation=False):
        self.guard()
        self.policy.admit(list(argv), timeout, mutation, self._private_backend_transport)
        self._android_mutation = mutation
        try:
            raw = self.transport(argv, timeout)
            self.command_index = self.bridge.command_index
            self.total_commands += 1
            return raw
        finally:
            self._android_mutation = False

    def command(self, argv, timeout, *, mutation=False, label=None):
        expected = self.c.NATIVE_PREFIX + ['launch', self.scope['package'], '--component',
                                         self.scope['component'], '--json']
        self.c.need(self.phase == 'launch' and argv == expected and timeout == self.native_timeout and mutation is True
                    and label == 'One native launch' and not self.launch_claimed,
                    'ONLY_ONE_EXACT_ORIGINAL_NATIVE_LAUNCH')
        self.guard(); self.launch_claimed = True
        raw = self.bridge.command(argv, timeout, mutation=True, label=label)
        self.command_index = self.bridge.command_index; self.total_commands += 1
        return raw

    def stacks(self, timeout=20):
        raw = self.android(self.c.STACKS, timeout).decode('utf-8', 'strict')
        roots, tasks = self.tasks.parse_stacks(raw)
        self.last_stack_task_ids = sorted(tasks)
        return raw, roots, tasks

    def selected_task(self):
        self.guard()
        claim, _ = self.scope_module.load_owned_task(self.bound)
        return {k: claim[k] for k in ('task', 'package', 'epoch_sha256', 'prelaunch_absent',
                'cleanup_allowed', 'launch_step', 'prelaunch_task_ids', 'native_receipt_sha256')}

    def launch_locked(self):
        self.c.need(self.phase == 'launch' and not (self.root / 'launch-attempted.json').exists(),
                    'ONCE_ONLY_NEW_NATIVE_LAUNCH_REQUIRED')
        raw, roots, tasks = self.stacks()
        pre = self.c.write_new(self.step / 'prelaunch-stacks.txt', raw.encode())
        self.c.need(not any(c['component'].split('/')[0] == self.scope['package']
                           for r in roots.values() for c in r['children']),
                    'PREEXISTING_TARGET_TASK_PRESERVED_NO_LAUNCH')
        self.c.write_new(self.root / 'launch-attempted.json', {'scope': self.scope,
            'step': self.step.name, 'automatic_retry': False})
        returned = self.command(self.c.NATIVE_PREFIX + ['launch', self.scope['package'],
            '--component', self.scope['component'], '--json'], self.native_timeout, mutation=True,
            label='One native launch')
        native = self.c.write_new(self.step / 'native-launch.json', returned)
        after, _, _ = self.stacks()
        post = self.c.write_new(self.step / 'postlaunch-stacks.txt', after.encode())
        self.scope_module.record_owned_task(self.bound, self.step.name, pre, native, post)
        return {'native_launch_acknowledged': True, 'cleanup_allowed': True,
                'business_success_verified': False, 'owned_task': self.selected_task()}

    def launch(self):
        if self.plan['kind'] == 'clock_timer':
            self.c.need(self.external_action_lock is not None and
                        self.external_action_lock.ref == self.plan['action_lock'], 'WHOLE_CLOCK_CASE_LOCK_REQUIRED')
            self.external_action_lock.verify()
            return self.launch_locked()
        with self.c.locked(ACTION_LOCK):
            return self.launch_locked()

    def cleanup(self):
        self.c.need(self.phase == 'cleanup', 'EXACT_CLEANUP_PHASE_REQUIRED')
        selected = self.selected_task()
        self.c.need(selected['cleanup_allowed'] is True and selected['prelaunch_absent'] is True
                    and not (self.root / 'cleanup-attempted.json').exists(),
                    'ONCE_ONLY_EXACT_NEW_TASK_CLEANUP_REQUIRED')
        from contextlib import nullcontext
        if self.plan['kind'] == 'clock_timer':
            self.c.need(self.external_action_lock is not None and
                        self.external_action_lock.ref == self.plan['action_lock'], 'ORIGINAL_CLOCK_LOCK_THROUGH_NORMAL_CLOSE')
            self.external_action_lock.verify(); lock = nullcontext()
        else:
            lock = self.c.locked(ACTION_LOCK)
        with lock:
            _, roots, tasks = self.stacks()
            task = selected['task']; expected = set(selected['prelaunch_task_ids'])
            if task not in tasks and task not in roots:
                self.c.need(tasks == expected, 'OTHER_TASKS_CHANGED_WITH_TARGET_ABSENT')
                return {'new_task_already_absent': True, 'removal_attempted': False,
                    'other_tasks_preserved': True, 'task_ids_after': sorted(tasks),
                    'Binder_UID_cleanup_verified': False}
            self.c.need(tasks == expected | {task} and self.tasks.exact_leaf(roots, task, self.scope['package']),
                        'EXACT_OWNED_LEAF_AND_OTHER_TASK_SET_REQUIRED')
            self.c.write_new(self.root / 'cleanup-attempted.json', {'step': self.step.name,
                'selected': selected, 'automatic_retry': False})
            self.android(['/system/bin/cmd', 'activity', 'stack', 'remove', str(task)], 20, mutation=True)
            observations = []
            def record(value):
                observations.append(value)
                self.c.write_new(self.step / ('cleanup-observation-%02d.json' % len(observations)), value)
            def read_stacks(timeout):
                return self.android(self.c.STACKS, timeout).decode('utf-8', 'strict')
            completed = self.tasks.wait_for_removal(read_stacks, task, self.scope['package'], tasks, record)
            self.guard(attempted=True)
            self.c.need(completed['task_ids_after'] == sorted(expected), 'ORIGINAL_OTHER_TASKS_MUST_BE_PRESERVED')
            self.last_stack_task_ids = completed['task_ids_after']
            return {'new_leaf_removed_and_verified': True, 'other_tasks_preserved': True,
                    **completed, 'Binder_UID_cleanup_verified': False}

    def ui(self, request, *, case_context):
        """A new typed UI step; the per-App guard must validate its semantics."""
        self.policy.admit_ui(request, case_context)
        selected = self.selected_task()
        _, roots, _ = self.stacks()
        self.c.need(self.tasks.exact_leaf(roots, selected['task'], self.scope['package']),
                    'FLOW_TASK_SCOPE_CHANGED')
        previous = (self.step, self.bridge, self.command_index); self._step_number += 1
        name = 'ui-%02d-%s' % (self._step_number, request['op'])
        mutation = request['op'] in ('click', 'set-text')
        self._new_step(name, 'ui', request, mutation, case_context); self._bridge()
        try:
            argv = self.modules['business_ui_entry.py'].logical_argv(request, self.scope['package'], self.step)
            returned = self.bridge.command(argv, 90, mutation=mutation, label='Existing android-app CLI')
            self.command_index = self.bridge.command_index; self.total_commands += 1
            result = self.c.parse(returned)
            self.c.need(type(result) is dict and type(result.get('ok')) is bool,
                        'ACTUAL_UI_RESPONSE_OBJECT_REQUIRED')
            # The original Clock continuation must see an unchanged native ACK
            # and an unchanged final post-capture UNKNOWN independently. It is
            # the per-App state machine, not this transport, which reconciles it.
            self.c.write_new(self.step / 'observed-result.json', result)
            return result, self.step
        finally:
            # No automatic follow-up action or task cleanup occurs on failure.
            self.step, self.bridge, self.command_index = previous

    def close(self):
        self.closed = True
        try:
            if self.receipt_witness is not None:
                self.receipt_witness.close()
        finally:
            try:
                if self.artifacts is not None:
                    self.artifacts.close()
            finally:
                if self.view is not None:
                    self.view.close()
