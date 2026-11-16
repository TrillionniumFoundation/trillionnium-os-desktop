"""New source-bound Flow for same-process original APIs and two new tasks."""
from pathlib import Path


def make_flow(base):
    class SystemFlow(base.Flow):
        def android(self, argv, timeout=20, *, mutation=False):
            self.guard()
            self.policy.admit(list(argv), timeout, mutation, self._private_backend_transport)
            self._android_mutation = mutation
            try:
                route = self.transport if self._private_backend_transport else self.camera_transport
                raw = route(argv, timeout)
                self.command_index = self.bridge.command_index; self.total_commands += 1
                return raw
            finally:
                self._android_mutation = False

        def _bridge(self):
            transport = self.c.packet_module(self.scope, 'webview_transport.py')
            self.bridge = transport.ImageRecorder(self, self.scope_module.RecorderBridge(self, self.bound))
            self._image_transport = False

        def native_launch(self):
            c = self.c
            c.need(self.phase == 'launch' and not self.launch_claimed
                and not (self.root / 'launch-attempted.json').exists(), 'ONE_NATIVE_CALL_IN_THIS_FRESH_SCOPE')
            self.session.action_lock.verify()
            raw, roots, tasks = self.stacks(15)
            c.need(not any(child['component'].split('/')[0] == self.scope['package']
                for root in roots.values() for child in root['children']), 'PREEXISTING_TARGET_TASK_PRESERVED')
            self.session.verify_prelaunch_tasks(roots, tasks)
            pre = c.write_new(self.step / 'prelaunch-stacks.txt', raw.encode())
            c.write_new(self.root / 'launch-attempted.json', {'scope': self.scope,
                'phase_lease': self.phase_lease_ref, 'step': self.step.name, 'automatic_retry': False})
            returned = self.command(c.NATIVE_PREFIX + ['launch', self.scope['package'], '--component',
                self.scope['component'], '--json'], 45, mutation=True, label='One native launch')
            result_ref = c.regular(self.step / ('command-%03d.result.json' % self.bridge.command_index), contents=False)
            actual = c.parse(c.read_ref(result_ref))
            c.need(actual['host_retirement_proved'] is True and actual['evidence_complete'] is True
                and actual['returncode'] == 0 and not actual['timed_out'] and not actual['errors']
                and c.read_ref(actual['stdout']) == returned, 'REAL_NATIVE_RESULT_REQUIRED')
            native = c.write_new(self.step / 'native-launch.json', returned)
            after, _, _ = self.stacks(15)
            post = c.write_new(self.step / 'postlaunch-stacks.txt', after.encode())
            claim_ref = self.scope_module.record_owned_task(self.bound, self.step.name, pre, native, post)
            self.session.task_claims.append(claim_ref)
            self.phase = 'inspect'
            return {'rc': actual['returncode'], 'timed_out': actual['timed_out'],
                'joined': actual['host_retirement_proved'], 'guard_after': True,
                'stdout': returned, 'stderr': c.read_ref(actual['stderr']), 'result': result_ref}

        def set_phase(self, phase_ref):
            phase = self.case_runtime.validate_phase(self.c, self.host_runtime, phase_ref,
                self.scope['phase_plan'], self.plan)
            self.c.need(phase['phase'] == 'final_cleanup', 'ONCE_ORIGINAL_FINAL_CLEANUP_ONLY')
            self.phase_lease_ref = phase_ref
            self.private_context = {'phase_lease': phase_ref, 'session': self.session}
            self.deadline = phase['deadline_monotonic_ns'] / 1000000000
            self.phase = 'cleanup'
            self._new_step('final-cleanup', 'phase', None, False); self._bridge()
            self.guard()

        def begin_api(self, name, request, context):
            previous = self.step, self.bridge, self.command_index
            self._new_step(name, 'same-process-original-api', request,
                request.get('op') in ('click', 'set-text', 'snapshot-tap', 'scroll-forward', 'scroll-backward'), context)
            self._bridge()
            return previous

        def end_api(self, previous):
            self.step, self.bridge, self.command_index = previous
    return SystemFlow
