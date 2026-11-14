"""New case leases and receipt guards; no Android or UI entry at import.

Host process ownership is separate from the Android task claims in
business_scope. These leases never assert Binder App UID retirement.
"""
import hashlib
import os
from pathlib import Path
import re
import stat
import time
import types


class PhaseCommands:
    """Clip actual owned execution to a validated phase's absolute deadline.

    Logical operation limits and held-entry argv remain original. The frozen
    recorder/capture/reaper still owns launch, timeout, retirement and receipt.
    """
    def __init__(self, commands, runtime):
        self.original, self.runtime = commands, runtime

    def __getattr__(self, name):
        return getattr(self.original, name)

    def run_recorded(self, name, argv, timeout, *args, **kwargs):
        remaining = self.runtime.deadline - time.monotonic()
        self.runtime.c.need(remaining > 0, 'ORIGINAL_PHASE_EXPIRED_BEFORE_OWNED_EXECUTION')
        original = self.original; runtime = self.runtime
        evidence = Path(args[0])
        class DeadlineCapture:
            def __init__(self, real):
                self.real = real
            def __getattr__(self, key):
                return getattr(self.real, key)
            def invoke_owned(self, reaper, factory, input_bytes, execution_deadline, observation_deadline, **options):
                phase_deadline = runtime.deadline
                actual = min(execution_deadline, phase_deadline)
                original.write_new(evidence / (name + '.phase-deadline.json'),
                    {'schema': 'pocket4-final-app-absolute-execution-deadline-v1',
                     'original_command_timeout_seconds': timeout,
                     'original_execution_deadline_monotonic': execution_deadline,
                     'original_observation_deadline_monotonic': observation_deadline,
                     'phase_deadline_monotonic': phase_deadline, 'execution_deadline_monotonic': actual,
                     'observation_deadline_monotonic': actual + observation_deadline - execution_deadline,
                     'original_retirement_grace_seconds': options.get('retirement_grace'),
                     'public_capture_source_unchanged': True, 'automatic_retry': False})
                if time.monotonic() >= actual:
                    original.write_new(evidence / (name + '.phase-no-dispatch.json'),
                        {'reason': 'ORIGINAL_PHASE_EXPIRED_BEFORE_ACTUAL_SPAWN',
                         'effective_deadline_monotonic': actual, 'observed_monotonic': time.monotonic(),
                         'factory_called': False, 'automatic_retry': False})
                    raise RuntimeError('ORIGINAL_PHASE_EXPIRED_BEFORE_ACTUAL_SPAWN')
                def bounded_factory(*descriptors):
                    if time.monotonic() >= actual:
                        original.write_new(evidence / (name + '.phase-no-dispatch.json'),
                            {'reason': 'CAPTURE_PREPARATION_EXHAUSTED_ORIGINAL_PHASE',
                             'effective_deadline_monotonic': actual, 'observed_monotonic': time.monotonic(),
                             'factory_called': False, 'automatic_retry': False})
                        raise RuntimeError('ORIGINAL_PHASE_EXPIRED_AT_ACTUAL_FACTORY')
                    return factory(*descriptors)
                invoke = self.real.invoke_owned
                owner = getattr(runtime, 'external_action_lock', None)
                if owner is not None:
                    # The unchanged lifecycle requires one controller thread.
                    # Service the private SCM_RIGHTS socket only from the same
                    # original bounded select loop, never a thread or daemon.
                    real_selectors = invoke.__globals__['selectors']
                    class PumpSelector:
                        def __init__(self):
                            self.actual_selector = real_selectors.DefaultSelector()
                        def __getattr__(self, key):
                            return getattr(self.actual_selector, key)
                        def select(self, timeout=None):
                            owner.pump(actual)
                            remaining = actual - time.monotonic()
                            if remaining <= 0:
                                return []
                            events = self.actual_selector.select(remaining if timeout is None
                                else min(timeout, remaining))
                            owner.pump(actual)
                            return events
                    class PrivateSelectors:
                        def __getattr__(self, key):
                            return getattr(real_selectors, key)
                        DefaultSelector = PumpSelector
                    capture_environment = dict(invoke.__globals__)
                    capture_environment['selectors'] = PrivateSelectors()
                    private_invoke = types.FunctionType(invoke.__code__, capture_environment,
                        invoke.__name__, invoke.__defaults__, invoke.__closure__)
                    private_invoke.__kwdefaults__ = dict(invoke.__kwdefaults__ or {})
                    invoke = private_invoke
                return invoke(reaper, bounded_factory, input_bytes, actual,
                    actual + observation_deadline - execution_deadline, **options)
        # The frozen recorder's code and globals remain unchanged. This private
        # call instance changes only the capture dependency at its exact
        # absolute-deadline API; it never patches the shared helper/module.
        environment = dict(original.run_recorded.__globals__)
        environment['load_capture'] = lambda *a, **kw: DeadlineCapture(original.load_capture(*a, **kw))
        call = types.FunctionType(original.run_recorded.__code__, environment,
            original.run_recorded.__name__, original.run_recorded.__defaults__, original.run_recorded.__closure__)
        call.__kwdefaults__ = dict(original.run_recorded.__kwdefaults__ or {})
        return call(name, argv, timeout, *args, **kwargs)

    def run_cli(self, name, argv, timeout, evidence, guard, *, protected_pids, mutation=False):
        result = self.run_recorded(name, argv, timeout, evidence, guard,
                                  protected_pids=protected_pids, mutation=mutation)
        try:
            return self.original.parse(result.stdout)
        except BaseException as error:
            error.command_observation = result.command_observation
            error.action_attempted = result.command_observation['action_attempted']
            error.outcome_unknown = error.action_attempted; error.automatic_retry = False
            raise


def _read_at(fd, name, limit):
    item = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
    try:
        chunks = []; total = 0
        while True:
            raw = os.read(item, min(65536, limit + 1 - total))
            if not raw:
                break
            chunks.append(raw); total += len(raw)
            if total > limit:
                raise RuntimeError('BOUNDED_HOST_PROCESS_OBSERVATION_REQUIRED')
        return b''.join(chunks)
    finally:
        os.close(item)


def process(common, pid):
    common.need(type(pid) is int and pid > 0, 'EXACT_CASE_HOST_PROCESS_REQUIRED')
    fd = os.open('/proc/' + str(pid), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        def identity():
            raw = _read_at(fd, 'stat', 65536).decode('ascii')
            end = raw.rfind(')'); fields = raw[end + 2:].split()
            common.need(end > 0 and len(fields) >= 20 and int(raw.split(' ', 1)[0]) == pid,
                        'HOST_PROCESS_STAT_INVALID')
            return {'pid': pid, 'parent': int(fields[1]), 'start_ticks': int(fields[19])}
        before = identity(); status = _read_at(fd, 'status', 131072).decode('ascii')
        uids = re.findall(r'^Uid:\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$', status, re.M)
        common.need(len(uids) == 1, 'HOST_OPERATOR_UID_OBSERVATION_REQUIRED')
        command = _read_at(fd, 'cmdline', 131072)
        root_fd = os.open('root', os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC, dir_fd=fd)
        try:
            root = os.fstat(root_fd)
        finally:
            os.close(root_fd)
        namespaces = {name: os.readlink('ns/' + name, dir_fd=fd)
                      for name in ('mnt', 'pid', 'uts', 'ipc', 'net', 'cgroup', 'user')}
        value = {**before, 'uids': [int(x) for x in uids[0]],
            'executable': os.readlink('exe', dir_fd=fd),
            'command_sha256': hashlib.sha256(command).hexdigest(),
            'root': {'device': root.st_dev, 'inode': root.st_ino},
            'namespaces': namespaces, 'cgroup': _read_at(fd, 'cgroup', 65536).decode('ascii').splitlines()}
        common.need(before == identity() and value['uids'] == [0, 0, 0, 0],
                    'STABLE_ROOT_CASE_OPERATOR_REQUIRED')
        return value
    finally:
        os.close(fd)


def boot():
    value = Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if not re.fullmatch('[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', value):
        raise RuntimeError('ACTUAL_BOOT_ID_REQUIRED')
    return value


def descendant_from(common, pid, ancestor):
    """Observe a real parent chain to the still-identical case owner."""
    common.need(process(common, ancestor['pid']) == ancestor, 'CASE_OWNER_PROCESS_CHANGED')
    seen = set()
    for _ in range(32):
        common.need(pid not in seen and pid > 0, 'CASE_OWNER_NOT_IN_REAL_PARENT_CHAIN')
        seen.add(pid); row = process(common, pid)
        if pid == ancestor['pid']:
            common.need(row == ancestor, 'CASE_OWNER_CHANGED_DURING_PARENT_CHAIN_READ')
            return
        pid = row['parent']
    raise RuntimeError('CASE_PARENT_CHAIN_BOUND')


def descendant(common, ancestor):
    return descendant_from(common, os.getpid(), ancestor)


def create_lease(common, base_ref, base):
    root = common.private_dir(base['case_root'])
    seconds = 360 if base['kind'] == 'clock_timer' else 600
    started = time.monotonic_ns()
    value = {'schema': 'pocket4-final-app-case-lease-v1', 'base_plan': base_ref,
        'boot_id': boot(), 'owner': process(common, os.getpid()),
        'started_monotonic_ns': started, 'initial_deadline_monotonic_ns': started + seconds * 1000000000,
        'initial_seconds': seconds, 'automatic_retry': False, 'Binder_UID_cleanup_verified': False}
    return common.write_new(root / 'lease.json', value, 0o400)


def validate_lease(common, ref, base_ref, kind, *, allow_cleanup=False):
    value = common.parse(common.read_ref(ref))
    fields = {'schema', 'base_plan', 'boot_id', 'owner', 'started_monotonic_ns',
              'initial_deadline_monotonic_ns', 'initial_seconds', 'automatic_retry', 'Binder_UID_cleanup_verified'}
    common.need(set(value) == fields and value['schema'] == 'pocket4-final-app-case-lease-v1'
        and value['base_plan'] == base_ref and value['boot_id'] == boot()
        and value['initial_seconds'] == (360 if kind == 'clock_timer' else 600)
        and type(value['started_monotonic_ns']) is int
        and type(value['initial_deadline_monotonic_ns']) is int
        and value['initial_deadline_monotonic_ns'] == value['started_monotonic_ns'] + value['initial_seconds'] * 1000000000
        and value['automatic_retry'] is False and value['Binder_UID_cleanup_verified'] is False,
        'EXACT_FRESH_CASE_OWNER_AND_ORIGINAL_LEASE_REQUIRED')
    now = time.monotonic_ns()
    extra = 35 * 1000000000 if kind == 'clock_timer' and allow_cleanup else 0
    common.need(value['started_monotonic_ns'] <= now < value['initial_deadline_monotonic_ns'] + extra,
                'ORIGINAL_CASE_LEASE_EXPIRED')
    descendant(common, value['owner'])
    return value


def create_phase(common, active_ref, active, phase, *, cleanup_trigger=None):
    """One actual worker/stage, with the original limits and no replay."""
    kind = active['kind']; final = kind == 'clock_timer' and phase == 'final_cleanup'
    lease = validate_lease(common, active['lease'], active['base_plan'], kind, allow_cleanup=final)
    common.need(process(common, os.getpid())['uids'] == [0, 0, 0, 0], 'ROOT_NEW_PHASE_REQUIRED')
    now = time.monotonic_ns()
    if kind == 'clock_timer':
        common.need(phase in ('business', 'final_cleanup'), 'ORIGINAL_CLOCK_STAGE_REQUIRED')
        if final:
            common.need(cleanup_trigger is not None, 'FIXED_CLOCK_CLEANUP_TRIGGER_REQUIRED')
            common.read_ref(cleanup_trigger)
            deadline = min(now + 35 * 1000000000, lease['initial_deadline_monotonic_ns'] + 35 * 1000000000)
            seconds = 35
        else:
            common.need(cleanup_trigger is None, 'NO_UNDECLARED_CLOCK_CLEANUP_TRIGGER')
            deadline = lease['initial_deadline_monotonic_ns']; seconds = 360
    else:
        common.need(phase in active['limits']['phase_seconds'] and cleanup_trigger is None,
                    'ORIGINAL_IHG_PHASE_REQUIRED')
        seconds = active['limits']['phase_seconds'][phase]
        deadline = min(now + seconds * 1000000000, lease['initial_deadline_monotonic_ns'])
    common.need(now < deadline, 'NO_PHASE_AFTER_DEADLINE')
    value = {'schema': 'pocket4-final-app-phase-lease-v1', 'active_plan': active_ref,
        'lease': active['lease'], 'phase': phase, 'owner': process(common, os.getpid()),
        'started_monotonic_ns': now, 'deadline_monotonic_ns': deadline, 'maximum_seconds': seconds,
        'cleanup_trigger': cleanup_trigger, 'automatic_retry': False}
    return common.write_new(Path(active['case_root']) / ('phase-' + phase + '.json'), value, 0o400)


def validate_phase(common, ref, active_ref, active):
    value = common.parse(common.read_ref(ref)); kind = active['kind']
    fields = {'schema', 'active_plan', 'lease', 'phase', 'owner', 'started_monotonic_ns',
              'deadline_monotonic_ns', 'maximum_seconds', 'cleanup_trigger', 'automatic_retry'}
    common.need(set(value) == fields and value['schema'] == 'pocket4-final-app-phase-lease-v1'
        and value['active_plan'] == active_ref and value['lease'] == active['lease']
        and value['automatic_retry'] is False, 'EXACT_NEW_PHASE_LEASE_REQUIRED')
    final = kind == 'clock_timer' and value['phase'] == 'final_cleanup'
    lease = validate_lease(common, active['lease'], active['base_plan'], kind, allow_cleanup=final)
    start, deadline = value['started_monotonic_ns'], value['deadline_monotonic_ns']
    common.need(type(start) is type(deadline) is int and
                lease['started_monotonic_ns'] <= start <= time.monotonic_ns() < deadline,
                'ACTUAL_PHASE_TIME_BOUND_REQUIRED')
    if kind == 'clock_timer':
        common.need(value['phase'] in ('business', 'final_cleanup'), 'ORIGINAL_CLOCK_PHASE_REQUIRED')
        if final:
            common.need(value['maximum_seconds'] == 35 and value['cleanup_trigger'] is not None
                and deadline == min(start + 35 * 1000000000, lease['initial_deadline_monotonic_ns'] + 35 * 1000000000),
                'ONCE_ONLY_ORIGINAL_THIRTY_FIVE_SECOND_CLEANUP')
            common.read_ref(value['cleanup_trigger'])
        else:
            common.need(value['maximum_seconds'] == 360 and value['cleanup_trigger'] is None
                and deadline == lease['initial_deadline_monotonic_ns'], 'ORIGINAL_CLOCK_INITIAL_LEASE')
    else:
        seconds = active['limits']['phase_seconds'].get(value['phase'])
        common.need(seconds in (175, 115) and value['maximum_seconds'] == seconds
            and value['cleanup_trigger'] is None and
            deadline == min(start + seconds * 1000000000, lease['initial_deadline_monotonic_ns']),
            'ORIGINAL_IHG_PHASE_DEADLINE_REQUIRED')
    descendant(common, value['owner'])
    return value


def verify_read(common, row, argv, baseline_ref, qualification_ref):
    """Re-derive a read from actual stdout and the held lease exit evidence."""
    common.need(set(row) == {'logical', 'result', 'transport'}, 'EXACT_HELD_READ_EVIDENCE_REQUIRED')
    logical = row['logical']; result = common.parse(common.read_ref(row['result']))
    transport = common.parse(common.read_ref(row['transport']))
    common.need(logical['argv'] == argv and logical['Android_mutation'] is False
        and transport['logical'] == logical and transport['lease_entered'] is True
        and transport['lease_released'] is True and transport['host_retirement_proved'] is True
        and transport['error_type'] is None and
        transport['post_guard']['business_baseline_sha256'] == baseline_ref['sha256'] and
        transport['post_guard']['business_qualification_sha256'] == qualification_ref['sha256'] and
        result['host_retirement_proved'] is True and result['evidence_complete'] is True
        and result['returncode'] == 0 and result['timed_out'] is False and result['errors'] == []
        and result.get('first_error') is None, 'ACTUAL_RETIRED_READ_WITH_HELD_MAIN_POST_GUARD_REQUIRED')
    common.read_ref(result['stderr'])
    return common.read_ref(result['stdout'])


def normalize_read(common, row):
    return {'logical': row['logical'], 'result': common.regular(row['path'], contents=False),
            'transport': row['transport']}


def prepare(runtime):
    common = runtime.c
    plan_module = common.packet_module(runtime.scope, 'app_plan.py')
    # Validate the full actual install/signature/helper chain once, then keep
    # stable named + held references and the actual guest APK descriptors.
    plan_module.validate(common, runtime.plan, runtime.view.baseline, runtime.scope, semantic=True)
    runtime.receipt_witness = common.EvidenceWitness([
        runtime.scope['phase_plan'], runtime.scope['actual_resolution_receipt'],
        *runtime.scope['installed_helper_receipts'], runtime.plan['helper_build'], runtime.plan['helper_install']])
    common.need(type(runtime.private_context) is dict and set(runtime.private_context) == {'phase_lease'},
                'EXPLICIT_ACTUAL_PHASE_WORKER_CONTEXT_REQUIRED')
    runtime.phase_lease_ref = runtime.private_context['phase_lease']
    value = validate_phase(common, runtime.phase_lease_ref, runtime.scope['phase_plan'], runtime.plan)
    common.need(runtime.deadline == value['deadline_monotonic_ns'] / 1000000000,
                'FLOW_DEADLINE_MUST_BE_ACTUAL_ORIGINAL_PHASE')
    runtime.bound.commands = PhaseCommands(runtime.bound.commands, runtime)


def full(runtime, attempted):
    common = runtime.c
    common.need(type(attempted) is bool and runtime.receipt_witness is not None,
                'PREPARED_COMPLETE_ORIGINAL_CASE_GUARD_REQUIRED')
    runtime.receipt_witness.verify(); runtime.artifacts.verify()
    phase = validate_phase(common, runtime.phase_lease_ref, runtime.scope['phase_plan'], runtime.plan)
    common.need(runtime.deadline == phase['deadline_monotonic_ns'] / 1000000000,
                'FLOW_PHASE_DEADLINE_CHANGED')
    if runtime.plan['kind'] == 'ihg_london':
        common.need(runtime.phase == phase['phase'], 'IHG_PHASE_CANNOT_CHANGE_WITHIN_WORKER')
    else:
        lock_module = common.packet_module(runtime.scope, 'app_action_lock.py')
        lock_module.validate(common, runtime.case_runtime, runtime.plan['action_lock'])
        owner = getattr(runtime, 'external_action_lock', None)
        if owner is not None:
            common.need(owner.ref == runtime.plan['action_lock'], 'FLOW_NOT_USING_ORIGINAL_CASE_ACTION_LOCK')
            owner.verify()
        common.need(runtime.phase in ('launch', 'inspect', 'cleanup') and
            (phase['phase'] == 'business' or runtime.phase != 'launch'), 'CLOCK_FINAL_CLEANUP_CANNOT_LAUNCH')
    if runtime.phase != 'launch':
        runtime.scope_module.load_owned_task(runtime.bound)
    return phase


def bootstrap_entry(entry_context):
    """The outer typed entry has already verified this task source packet."""
    value = entry_context['scope']; ref = value['task_source_manifest']
    raw = Path(ref['path']).read_bytes()
    if len(raw) != ref['bytes'] or hashlib.sha256(raw).hexdigest() != ref['sha256']:
        raise RuntimeError('ENTRY_TASK_SOURCE_REFERENCE_CHANGED')
    import json
    packet = json.loads(raw)
    rows = [r for r in packet['files'] if Path(r['path']).name == 'app_common.py']
    if len(rows) != 1:
        raise RuntimeError('ONE_NEW_APP_COMMON_SOURCE_REQUIRED')
    row = rows[0]; raw = Path(row['path']).read_bytes()
    if len(raw) != row['bytes'] or hashlib.sha256(raw).hexdigest() != row['sha256']:
        raise RuntimeError('ENTRY_APP_COMMON_SOURCE_CHANGED')
    common = types.ModuleType('new_clock_entry_common'); common.__file__ = row['path']
    exec(compile(raw, row['path'], 'exec'), common.__dict__)
    common.read_ref(row); common.read_ref(ref)
    return common
