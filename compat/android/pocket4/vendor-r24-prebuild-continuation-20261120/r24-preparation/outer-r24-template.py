#!/usr/bin/python3
"""Fixed Pocket4 R12 outer supervisor candidate.

This template deliberately refuses production dispatch until its exact bundle
hash is filled by the source/release freeze.  R10 is never imported or run.
The normal R12 build and recovery functions remain in their separately pinned
worker.  This process owns the original serial lock throughout both phases.
"""
import ctypes
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import time
import traceback
import types

ROOT = Path('/home/qq/work/p4-official-vendor-cp3a-20261118-162b-r1')
BUNDLE = ROOT / 'control/vendor-build-20261120-9907-r24/inputs/BUNDLE.json'
BUNDLE_SHA = 'UNFROZEN_SOURCE_ONLY'
OUTER_UNIT = 'p4-cp3a-vendor-supervisor-20261120-9907-r24.service'
BUILD_UNIT = 'p4-cp3a-vendor-20261120-9907-r24.service'
RECOVERY_UNIT = 'p4-cp3a-vendor-20261120-9907-r24-recovery.service'
CONTROL = ROOT / 'control/vendor-build-20261120-9907-r24/actual'
CG_PARENT = Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice')
GIB = 1024 ** 3
PROPERTIES = 'LoadState,ActiveState,SubState,MainPID,ControlGroup,InvocationID,Description,Result,ExecMainCode,ExecMainStatus'
STOP_REQUESTED = False


def require(value, message):
    if not value:
        raise RuntimeError(message)


def f9(s):
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns]


def read_pinned(path, size=None, sha=None, limit=1048576):
    path = Path(path)
    require(path.resolve() == path, 'canonical input path')
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = f9(os.fstat(fd))
        require(stat.S_ISREG(before[2]) and before[5] == 1 and before[6] <= limit,
                'bounded single-link regular input')
        body = bytearray()
        while True:
            block = os.read(fd, 65536)
            if not block:
                break
            body.extend(block)
        require(before == f9(os.fstat(fd)) == f9(path.lstat()), 'changed held input')
        digest = hashlib.sha256(body).hexdigest()
        if size is not None:
            require(len(body) == size, 'exact input length')
        if sha is not None:
            require(digest == sha, 'exact input hash')
        return bytes(body), {'path': str(path), 'f9': before, 'bytes': len(body), 'sha256': digest}
    finally:
        os.close(fd)


def save_new(path, value):
    body = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        view = memoryview(body)
        while view:
            done = os.write(fd, view)
            require(done > 0, 'complete journal write')
            view = view[done:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return {'path': str(path), 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}


class ActualChild:
    """Original Popen child is stored before pidfd_open or any other fallible step.

    No poll()/communicate() reaps it before the final original PIDFD observation.
    Constructor-failure retirement uses only the still-unreaped original child;
    that failure can never receive successful PIDFD qualification.
    """
    def __init__(self, name, argv, stdout, stderr):
        self.name, self.argv = name, [str(x) for x in argv]
        self.stdout, self.stderr = stdout, stderr
        self.child, self.pidfd, self.wait_info = None, None, None
        self.started = False
        self.forced = False
        self.pidfd_failure = None
        self.row = {'name': name, 'argv': self.argv, 'actual_reaped': False,
                    'original_pidfd_held_until_reaped': False}

    def start(self):
        require(not self.started, 'child start is single use')
        self.started = True
        self.child = subprocess.Popen(self.argv, stdin=subprocess.DEVNULL,
                                      stdout=self.stdout, stderr=self.stderr,
                                      start_new_session=True, close_fds=True)
        self.row.update(pid=self.child.pid, started_ns=time.time_ns())
        try:
            self.pidfd = os.pidfd_open(self.child.pid)
        except BaseException as error:
            self.pidfd_failure = repr(error)
            self.row['pidfd_constructor_failure'] = self.pidfd_failure
            raise
        return self

    def exited(self):
        require(self.child is not None, 'original child exists')
        if self.wait_info is not None:
            return True
        if self.pidfd is None:
            info = os.waitid(os.P_PID, self.child.pid,
                             os.WEXITED | os.WNOHANG | os.WNOWAIT)
        else:
            info = os.waitid(os.P_PIDFD, self.pidfd,
                             os.WEXITED | os.WNOHANG | os.WNOWAIT)
        if info is not None:
            require(info.si_pid == self.child.pid and info.si_code in
                    (os.CLD_EXITED, os.CLD_KILLED, os.CLD_DUMPED), 'original exit result')
            self.wait_info = info
        return self.wait_info is not None

    def signal_original(self, sig):
        require(self.child is not None and self.child.returncode is None,
                'signal only original unreaped child')
        if self.pidfd is not None:
            try:
                signal.pidfd_send_signal(self.pidfd, sig)
            except ProcessLookupError:
                pass
        else:
            # Popen has not been polled/waited: the original child cannot have
            # been reaped or its numeric PID reused by this sole parent.
            try:
                os.kill(self.child.pid, sig)
            except ProcessLookupError:
                pass

    def retire(self, deadline, force=False):
        if self.child is None:
            return None
        if self.child.returncode is not None:
            return self.row
        if force and not self.exited():
            self.forced = True
            self.signal_original(signal.SIGTERM)
            gentle = min(deadline, time.monotonic() + 2)
            while not self.exited() and time.monotonic() < gentle:
                time.sleep(0.02)
            if not self.exited():
                self.signal_original(signal.SIGKILL)
        while not self.exited():
            require(time.monotonic() < deadline, 'original child retirement deadline')
            time.sleep(0.02)
        result = self.child.wait(timeout=max(0.001, deadline - time.monotonic()))
        info = self.wait_info
        expected = info.si_status if info.si_code == os.CLD_EXITED else -info.si_status
        require(result == expected, 'waitid and actual reap disagree')
        self.row.update(exit_code=result, actual_reaped=True, forced=self.forced,
                        original_pidfd_held_until_reaped=self.pidfd is not None,
                        waitid={'pid': info.si_pid, 'code': info.si_code, 'status': info.si_status},
                        finished_ns=time.time_ns())
        if self.pidfd is not None:
            os.close(self.pidfd)
            self.pidfd = None
        return self.row


class Supervisor:
    def __init__(self, deadline, generation):
        self.deadline, self.generation = deadline, generation
        self.children, self.phases = [], []
        self.custody = []
        self.counter = 0

    def allowed_units(self):
        return (BUILD_UNIT, RECOVERY_UNIT)

    def phase_spec(self, worker, mode):
        require(mode in ('build', 'recover'), 'fixed phase')
        unit = BUILD_UNIT if mode == 'build' else RECOVERY_UNIT
        limits = ((24, 22, 8, 8192, 28800) if mode == 'build'
                  else (2, 1.5, 2, 512, 1260))
        return unit, limits, list(range(16)), OUTER_UNIT

    def short(self, argv, seconds=15):
        require(time.monotonic() < self.deadline, 'outer original deadline')
        self.counter += 1
        name = 'outer-command-%04d' % self.counter
        paths = [CONTROL / (name + x) for x in ('.stdout', '.stderr')]
        deadline = min(self.deadline, time.monotonic() + seconds)
        with paths[0].open('xb') as out, paths[1].open('xb') as err:
            child = ActualChild(name, argv, out, err)
            self.children.append(child)
            failure = None
            try:
                child.start()
                while not child.exited():
                    require(time.monotonic() < deadline, 'bounded helper deadline')
                    time.sleep(0.02)
            except BaseException as error:
                failure = error
            finally:
                child.retire(min(self.deadline, deadline + 3), force=failure is not None)
            if failure is not None:
                raise failure
            require(child.row['original_pidfd_held_until_reaped'], 'helper PIDFD qualification')
        data = []
        for path in paths:
            body, _ = read_pinned(path, limit=65536)
            data.append(body.decode('utf-8', 'strict'))
        return child.row['exit_code'], data[0], data[1]

    def properties(self, unit):
        require(unit in self.allowed_units(), 'fixed inner unit only')
        code, out, err = self.short(['/usr/bin/systemctl', '--user', 'show', unit,
                                    '--property=' + PROPERTIES])
        require(code == 0, 'actual same-unit status failed: ' + err)
        pairs = [line.split('=', 1) for line in out.splitlines() if '=' in line]
        require(len(pairs) == len({x[0] for x in pairs}), 'unique actual unit properties')
        return dict(pairs)

    def retired(self, unit, properties):
        return (properties.get('LoadState') == 'not-found'
                and properties.get('ActiveState') == 'inactive'
                and properties.get('SubState') == 'dead'
                and properties.get('MainPID') == '0'
                and not properties.get('ControlGroup')
                and not os.path.lexists(CG_PARENT / unit))

    def phase(self, worker, mode, operation_deadline, retirement_deadline):
        unit, limits, affinity, outer_unit = self.phase_spec(worker, mode)
        memory, high, cpus, tasks, seconds = limits
        require(self.retired(unit, self.properties(unit)), 'new generation unit must be absent')
        description = 'Pocket4 R24 ' + self.generation + ' ' + mode
        argv = ['/usr/bin/systemd-run', '--user', '--unit=' + unit,
                '--wait', '--collect', '--pipe', '--service-type=exec',
                '--property=Description=' + description,
                '--property=MemoryMax=' + str(int(memory * GIB)),
                '--property=MemoryHigh=' + str(int(high * GIB)),
                '--property=MemorySwapMax=0', '--property=CPUQuota=' + str(cpus * 100) + '%',
                '--property=CPUAffinity=' + ' '.join(map(str, affinity)),
                '--property=TasksMax=' + str(tasks), '--property=RuntimeMaxSec=' + str(seconds),
                '--property=TimeoutStopSec=30', '--property=KillMode=control-group',
                '--property=Nice=10', '--property=UMask=0077', '--property=Restart=no',
                '--property=Requisite=' + outer_unit, '--property=After=' + outer_unit,
                '--property=PartOf=' + outer_unit,
                '/usr/bin/python3', '-I', '-B', str(worker.SELF), mode]
        row = {'unit': unit, 'mode': mode, 'argv': argv, 'started_ns': time.time_ns(),
               'operation_deadline': operation_deadline, 'retirement_deadline': retirement_deadline,
               'forced_service_retirement': False, 'service_retired': False, 'errors': []}
        self.phases.append(row)
        hold = {'row': row, 'client': None, 'cgroup_fd': None, 'observe': None, 'cancel': None,
                'record_client_boundary': None, 'prove_retired': None}
        self.custody.append(hold)
        cgfd = None
        cg_identity = None
        invocation = None
        client = None
        paths = [CONTROL / ('outer-' + mode + x) for x in ('.stdout', '.stderr')]

        def observe():
            nonlocal cgfd, cg_identity, invocation
            props = self.properties(unit)
            if props.get('LoadState') != 'not-found':
                require(props.get('Description') == description, 'unit generation mismatch')
                actual = props.get('InvocationID', '')
                if not actual:
                    # A transient unit is first loaded, then its start job
                    # receives an InvocationID. This exact observed pre-actor
                    # state is neither an active service nor retirement.
                    require(invocation is None and props.get('ActiveState') == 'inactive'
                            and props.get('SubState') == 'dead' and props.get('MainPID') == '0'
                            and not props.get('ControlGroup') and cgfd is None,
                            'only original pre-actor queued unit may lack invocation')
                    row['original_queued_state_observed'] = True
                    return props
                require(re.fullmatch('[0-9a-f]{32}', actual) is not None, 'actual invocation required')
                if invocation is None:
                    invocation = actual
                require(invocation == actual, 'unit invocation replaced')
                path = CG_PARENT / unit
                actual_path = props.get('ControlGroup')
                if actual_path:
                    require(actual_path == str(path)[len('/sys/fs/cgroup'):], 'fixed unit cgroup')
                    require(path.resolve() == path, 'unit cgroup alias')
                    if cgfd is None:
                        try:
                            cgfd = os.open(path, os.O_PATH | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
                        except FileNotFoundError:
                            final = self.properties(unit)
                            require(self.retired(unit, final), 'cgroup disappeared without actual retirement')
                            return final
                        hold['cgroup_fd'] = cgfd
                        st = os.fstat(cgfd)
                        cg_identity = [st.st_dev, st.st_ino]
                    try:
                        st = path.stat(follow_symlinks=False)
                    except FileNotFoundError:
                        final = self.properties(unit)
                        require(self.retired(unit, final), 'held cgroup disappeared without actual retirement')
                        return final
                    require([st.st_dev, st.st_ino] == cg_identity, 'held cgroup replaced')
            return props

        def cancel():
            row['forced_service_retirement'] = True
            props = observe()
            if not self.retired(unit, props):
                # Stop is issued only while the fixed original invocation and
                # its held cgroup still agree. A late fresh unit cannot execute
                # without this live outer's original serial-lock admission.
                self.short(['/usr/bin/systemctl', '--user', '--no-block', 'stop', unit], 10)
                gentle = min(retirement_deadline - 5, time.monotonic() + 35)
                while time.monotonic() < gentle:
                    if self.retired(unit, observe()):
                        return
                    time.sleep(0.1)
                if cgfd is not None:
                    # Fallback targets the original held cgroup object, never
                    # a PID, reconstructed path, or a later same-name cgroup.
                    fd = os.open('cgroup.kill', os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=cgfd)
                    try:
                        require(os.write(fd, b'1') == 1, 'whole original cgroup kill')
                    finally:
                        os.close(fd)

        def record_client_boundary():
            require(client is not None and client.row['actual_reaped'],
                    'record only original actually reaped client')
            if 'client_retirement_boundary' not in row:
                known_actor = invocation is not None or cg_identity is not None
                row['client_retirement_boundary'] = {
                    'invocation_id': invocation, 'held_cgroup_identity': cg_identity,
                    'original_actor_observed_before_client_reap': known_actor,
                    'original_client_actual_reaped': True,
                    'original_pidfd_held_until_reaped': client.row['original_pidfd_held_until_reaped'],
                    'client_exit_code': client.row.get('exit_code'),
                    'client_forced': client.forced, 'phase_errors': list(row['errors'])}
                # A failed/cancelled client can leave a queued StartTransientUnit
                # request after an instantaneous not-found observation. Never
                # adopt a later actor as proof for this unknown dispatch.
                row['late_start_unresolved'] = (not known_actor and (
                    client.forced or client.row.get('exit_code') != 0
                    or not client.row['original_pidfd_held_until_reaped'] or bool(row['errors'])))

        def prove_retired():
            # Revoke any earlier claim before another fallible observation.
            row['service_retired'] = False
            record_client_boundary()
            require(client.row['original_pidfd_held_until_reaped'],
                    'original client PIDFD retirement proof required')
            require(not row['late_start_unresolved'],
                    'unknown failed dispatch may start late; retain serial and stop original outer')
            props = observe()
            require(self.retired(unit, props), 'final same-unit proof after original client reap')
            row['final_properties'] = props
            row['service_retired'] = True

        hold['observe'], hold['cancel'] = observe, cancel
        hold['record_client_boundary'], hold['prove_retired'] = record_client_boundary, prove_retired

        try:
            with paths[0].open('xb') as out, paths[1].open('xb') as err:
                client = ActualChild('outer-' + mode, argv, out, err)
                hold['client'] = client
                self.children.append(client)
                try:
                    client.start()
                    next_probe = 0.0
                    while not client.exited():
                        require(time.monotonic() < operation_deadline, 'fixed phase operation deadline')
                        require(mode == 'recover' or not STOP_REQUESTED, 'build cancellation requested')
                        if time.monotonic() >= next_probe:
                            observe()
                            next_probe = time.monotonic() + 5
                        time.sleep(0.1)
                    client.retire(retirement_deadline)
                    record_client_boundary()
                except BaseException as error:
                    row['errors'].append(repr(error))
                    cancel()
                finally:
                    row['service_retired'] = False
                    if client.row['actual_reaped']:
                        record_client_boundary()
                    elif client.child is not None and client.exited():
                        client.retire(retirement_deadline)
                        record_client_boundary()
                    while not self.retired(unit, observe()):
                        require(time.monotonic() < retirement_deadline - 3, 'same-unit retirement deadline')
                        if not row['forced_service_retirement']:
                            cancel()
                        time.sleep(0.1)
                    client.retire(retirement_deadline, force=True)
                    record_client_boundary()
                    row['client'] = client.row
                    require(client.row['actual_reaped'], 'original systemd client not reaped')
                    prove_retired()
        finally:
            row.update(invocation_id=invocation, held_cgroup_identity=cg_identity,
                       finished_ns=time.time_ns())
            if cgfd is not None and row['service_retired'] and client is not None and client.row['actual_reaped']:
                os.close(cgfd)
                hold['cgroup_fd'] = None
        row['success'] = (not row['errors'] and not row['forced_service_retirement']
                          and row['client']['exit_code'] == 0
                          and row['client']['original_pidfd_held_until_reaped'])
        return row

    def retire_remaining(self):
        """Keep original custody after any phase/query/journal exception.

        This is retirement only, not a retry of build or recovery.  A failed
        observation does not destroy the held cgroup or original child handle.
        """
        failures = []
        for hold in self.custody:
            row, child = hold['row'], hold['client']
            if child is None:
                continue
            previously_proved = row['service_retired']
            row['service_retired'] = False
            try:
                if child.row['actual_reaped']:
                    hold['record_client_boundary']()
                elif child.child is not None and child.exited():
                    child.retire(self.deadline - 1)
                    hold['record_client_boundary']()
            except BaseException as error:
                failures.append({'unit': row['unit'], 'client_boundary_error': repr(error)})
            if not previously_proved:
                try:
                    hold['cancel']()
                    while True:
                        props = hold['observe']()
                        if self.retired(row['unit'], props):
                            break
                        require(time.monotonic() < self.deadline - 3, 'final original service custody deadline')
                        time.sleep(0.1)
                except BaseException as error:
                    failures.append({'unit': row['unit'], 'error': repr(error)})
                    # A status failure may not prevent retirement of an already
                    # held original cgroup. No path is reopened as a substitute.
                    if hold['cgroup_fd'] is not None:
                        try:
                            fd = os.open('cgroup.kill', os.O_WRONLY | os.O_NOFOLLOW | os.O_CLOEXEC,
                                         dir_fd=hold['cgroup_fd'])
                            try:
                                require(os.write(fd, b'1') == 1, 'final original cgroup kill')
                            finally:
                                os.close(fd)
                        except BaseException as kill_error:
                            failures.append({'unit': row['unit'], 'error': repr(kill_error)})
            try:
                child.retire(self.deadline - 1, force=True)
                hold['record_client_boundary']()
                row['client'] = child.row
                hold['prove_retired']()
            except BaseException as error:
                failures.append({'unit': row['unit'], 'child_error': repr(error)})
            if row['service_retired'] and child.row['actual_reaped'] and hold['cgroup_fd'] is not None:
                os.close(hold['cgroup_fd'])
                hold['cgroup_fd'] = None
        # Includes short systemctl children whose pidfd construction or cleanup
        # may itself have raised. No child is dropped from this original list.
        for child in self.children:
            if child.child is not None and not child.row['actual_reaped']:
                try:
                    child.retire(self.deadline - 1, force=True)
                except BaseException as error:
                    failures.append({'child': child.name, 'error': repr(error)})
        return failures


def stop_requested(_sig, _frame):
    global STOP_REQUESTED
    STOP_REQUESTED = True


def fail_stop_outer(supervisor):
    """Keep original serial custody until systemd has stopped this outer.

    This path never qualifies retirement or resumes source recovery. The exact
    PartOf/After/Requisite transaction covers an unresolved late start.
    """
    try:
        code, out, err = supervisor.short(
            ['/usr/bin/systemctl', '--user', '--no-block', 'stop', OUTER_UNIT], 5)
        save_new(CONTROL / 'outer-fail-stop-request.json', {
            'outer_unit': OUTER_UNIT, 'retirement_unproved': True,
            'source_operations_permitted_after_request': False,
            'stop_client_exit_code': code, 'stdout': out, 'stderr': err,
            'actual_children': [child.row for child in supervisor.children],
            'requested_ns': time.time_ns()})
    finally:
        while True:
            signal.pause()


def execute_phases(supervisor, worker, terminal, serial, serial_identity, deadline):
    """The production phase ordering, also exercised by finite failure controls."""
    try:
        supervisor.phase(worker, 'build', min(time.monotonic() + 28830, deadline - 1380), deadline - 1320)
    except BaseException as error:
        terminal['errors'].append({'stage': 'build', 'error': repr(error), 'traceback': traceback.format_exc()})
    finally:
        terminal['build_retirement_errors'] = supervisor.retire_remaining()
        build_rows = [x for x in supervisor.phases if x['mode'] == 'build']
        require(len(build_rows) == 1 and build_rows[0]['service_retired']
                and build_rows[0].get('client', {}).get('actual_reaped') is True,
                'build custody must retire before any recovery source operation')
        require(f9(os.fstat(serial)) == serial_identity, 'original serial still held')
        save_new(CONTROL / 'build-retirement-before-recovery.json', {
            'schema': 'p4-r24-original-build-retirement-before-recovery-v1',
            'generation': supervisor.generation, 'build_phase': build_rows[0],
            'serial_lock': serial_identity, 'worker_sha256': worker.digest(worker.SELF)['sha256'],
            'original_outer_children': [c.row for c in supervisor.children],
            'observed_ns': time.time_ns()})
        terminal['normal_recovery_attempted'] = True
        supervisor.phase(worker, 'recover', min(time.monotonic() + 1260, deadline - 60), deadline - 10)


def main():
    started = time.monotonic()
    deadline = started + 30300
    require(re.fullmatch('[0-9a-f]{64}', BUNDLE_SHA) is not None,
            'source-only template: actual release and input freeze not yet bound')
    require(os.getuid() == os.geteuid() == 1000 and os.uname().machine == 'x86_64', 'normal qq x86_64')
    require(os.sched_getaffinity(0) == {20}, 'outer CPU20')
    cg = Path('/sys/fs/cgroup') / Path('/proc/self/cgroup').read_text().strip()[4:]
    require(cg == CG_PARENT / OUTER_UNIT, 'original outer unit cgroup')
    limits = {n: (cg / n).read_text().strip() for n in
              ('memory.max', 'memory.high', 'memory.swap.max', 'cpu.max', 'pids.max')}
    require(limits['memory.max'] == str(512 * 1024 ** 2)
            and limits['memory.high'] == str(384 * 1024 ** 2)
            and limits['memory.swap.max'] == '0' and limits['pids.max'] == '128', 'outer resource budget')
    quota, period = map(int, limits['cpu.max'].split())
    require(quota == period, 'outer CPU100%')
    raw, bundle_pin = read_pinned(BUNDLE, sha=BUNDLE_SHA)
    bundle = json.loads(raw)
    require(bundle['schema'] == 'pocket4-vendor-r24-launch-bundle-v1'
            and bundle['dispatch_inputs_frozen'] is True, 'complete frozen bundle')
    body, worker_pin = read_pinned(bundle['worker']['path'], bundle['worker']['bytes'], bundle['worker']['sha256'])
    require(worker_pin['path'] == str(ROOT / 'control/vendor-build-20261120-9907-r24/source.py'), 'fixed successor worker')
    worker = types.ModuleType('pocket4_vendor_r24_worker')
    worker.__file__ = worker_pin['path']
    exec(compile(body, worker.__file__, 'exec'), worker.__dict__)
    require(str(worker.CONTROL) == str(CONTROL) and worker.UNIT + '.service' == BUILD_UNIT
            and worker.RECOVERY_UNIT + '.service' == RECOVERY_UNIT
            and worker.TREE == bundle['source_tree'], 'worker generation and actual source binding')
    require(worker.LOCK_PINS == [(worker.WORK.parent / 'native-full.serial.lock', 60857531),
                               (worker.WORK / 'package-build.lock', 60857480),
                               (worker.WORK / 'aosp-source-update.lock', 60857481)], 'original three lock identities')
    require(not os.path.lexists(CONTROL) and CONTROL.parent.is_dir(), 'fresh R24 control')
    CONTROL.mkdir(mode=0o700)
    supervisor = Supervisor(deadline, os.urandom(16).hex())
    serial = os.open(worker.SERIAL, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    terminal = {'schema': 'pocket4-vendor-r24-supervisor-terminal-v1', 'started_ns': time.time_ns(),
                'production_ready': False, 'runtime_qualified': False, 'installed': False,
                'bundle': bundle_pin, 'worker': worker_pin, 'errors': [], 'normal_recovery_attempted': False,
                'serial_held_through_all_source_operations': False, 'all_owned_units_retired': False}
    build_attempted = False
    serial_locked = False
    signal.signal(signal.SIGTERM, stop_requested)
    signal.signal(signal.SIGINT, stop_requested)
    signal.signal(signal.SIGHUP, stop_requested)
    try:
        worker.check_lock(worker.SERIAL, 60857531)
        fcntl.flock(serial, fcntl.LOCK_EX | fcntl.LOCK_NB)
        serial_locked = True
        serial_identity = f9(os.fstat(serial))
        for path, inode in worker.LOCK_PINS[1:]:
            worker.check_lock(path, inode)
            fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(fd)
        # This original gate remains required; additional current compiler
        # receipts are separately fixed in the successor's retirement function.
        retired = worker.verify_serialized_retirement()
        save_new(CONTROL / 'serialized-heavy-admission.json', retired)
        resources = {'observed_ns': time.time_ns(), 'memory_available': worker.memory_available(),
                     'disk_free': worker.shutil.disk_usage(ROOT).free, 'required_memory': 42 * GIB,
                     'required_disk': 144 * GIB, 'output_growth_cap': 120 * GIB, 'disk_floor': 24 * GIB,
                     'vendor_growth_cap': 118 * GIB, 'all_light_roots_growth_cap': 2 * GIB}
        save_new(CONTROL / 'outer-resource-probe.json', resources)
        require(resources['memory_available'] >= 42 * GIB and resources['disk_free'] >= 144 * GIB,
                'original fresh 42 GiB / 144 GiB admission')
        require(not STOP_REQUESTED and time.monotonic() < deadline - 30060, 'outer admission time/cancellation')
        admission = {'pid': os.getpid(), 'start_ticks': Path('/proc/self/stat').read_text().rsplit(') ', 1)[1].split()[19],
                     'observed_ns': time.time_ns(), 'serial_lock': serial_identity,
                     'locks': [{'path': str(p), 'identity': worker.check_lock(p, i),
                                'held_records': worker.lock_records(p)} for p, i in worker.LOCK_PINS],
                     'script': worker.digest(worker.SELF), 'outer_fixed_budget_seconds': 30300,
                     'outer_deadline_monotonic': deadline, 'supervisor': str(Path(__file__).resolve()),
                     'generation': supervisor.generation, 'new_outer_not_historical_r10_argv': True,
                     **resources}
        save_new(CONTROL / 'outer-admission.json', admission)
        build_attempted = True
        execute_phases(supervisor, worker, terminal, serial, serial_identity, deadline)
        for path, inode in worker.LOCK_PINS[1:]:
            worker.check_lock(path, inode)
            require(not worker.lock_records(path), 'normal source lock remains held')
            fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            finally:
                os.close(fd)
        require(f9(os.fstat(serial)) == serial_identity, 'serial inode bookend')
        terminal['serial_held_through_all_source_operations'] = True
    except BaseException as error:
        terminal['errors'].append({'stage': 'outer', 'error': repr(error), 'traceback': traceback.format_exc()})
    finally:
        terminal['final_retirement_errors'] = supervisor.retire_remaining()
        terminal['phases'] = supervisor.phases
        terminal['children'] = [c.row for c in supervisor.children]
        terminal['original_worker_status_children'] = worker.OBS.get('status_commands', [])
        terminal['all_owned_units_retired'] = all(p['service_retired'] for p in supervisor.phases)
        terminal['all_created_children_reaped'] = (all(c.child is None or c.row['actual_reaped'] for c in supervisor.children)
            and all(r['actual_child_reaped'] and r['original_pidfd_held_until_reaped']
                    for r in terminal['original_worker_status_children']))
        terminal['normal_recovery_verified'] = (len(supervisor.phases) == 2 and supervisor.phases[1].get('success') is True)
        terminal['passed'] = (not terminal['errors'] and not terminal['final_retirement_errors']
                              and len(supervisor.phases) == 2
                              and all(p.get('success') for p in supervisor.phases)
                              and terminal['all_created_children_reaped']
                              and terminal['serial_held_through_all_source_operations'])
        terminal.update(finished_ns=time.time_ns(), build_attempted=build_attempted,
                        serial_lock_acquired=serial_locked, fixed_deadline_exceeded=time.monotonic() >= deadline)
        try:
            save_new(CONTROL / 'outer-terminal.json', terminal)
            print(json.dumps({'passed': terminal['passed'], 'phases': supervisor.phases,
                              'errors': terminal['errors']}), flush=True)
        finally:
            # No source read, recovery, retry, or new phase is permitted after
            # this close. Unqualified terminal states remain explicit blockers.
            if terminal['all_owned_units_retired'] and terminal['all_created_children_reaped']:
                os.close(serial)
            else:
                # Do not voluntarily release source exclusion while owned
                # retirement remains unproved. Stop this exact outer through
                # systemd; PartOf/After stop its exact inner units first. No
                # source operation follows. This is an explicit failure, never
                # a successful recovery or a completed build receipt.
                terminal['retirement_incomplete_fail_stop'] = True
                fail_stop_outer(supervisor)
    return 0 if terminal['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
