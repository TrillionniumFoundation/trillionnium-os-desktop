#!/usr/bin/env python3
"""Fixed capture lifecycle, derived from actual Owner20 build02 OwnChildReaper.

Only this single-threaded process's kernel-listed unreaped children can be
signalled. No process discovery, Main signals, service changes or environment
overrides are provided. Same-UID root retirement happens inside the separately
pinned root supervisor; outer EPERM is never treated as success.
"""
import ctypes
import errno
import fcntl
import hashlib
import json
import os
import resource
import select
import signal
import stat
import subprocess
import sys
import time

MAX_CHILDREN = 128
PROTECTED_PIDS = frozenset((3268774, 3268779, 3270325, 3270341, 3270350, 3270611, 3588022, 3588024))


def require(value, message):
    if not value:
        raise RuntimeError(message)


def safe_error(error, stage):
    return {'stage': stage, 'type': type(error).__name__,
            'errno': getattr(error, 'errno', None), 'message': str(error)}


class OwnChildReaper:
    """Retire only children of this single-threaded isolated controller."""
    def __init__(self, protected_pids=(), passive_root_wait=False):
        self.pid = os.getpid()
        self.protected_pids = frozenset(protected_pids)
        self.passive_root_wait = passive_root_wait
        self.original = None
        self.changed = False
        self.active = False
        self.record = {'pid': self.pid, 'begin_passed': False, 'restored': False,
                       'final_children_empty': False, 'max_adopted_per_command': 128,
                       'cleanup_deadline_supplied_by_caller': True,
                       'protected_pid_count': len(self.protected_pids),
                       'signals_only_to_kernel_proven_owned_children': True}
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.prctl = self.libc.prctl
        self.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                              ctypes.c_ulong, ctypes.c_ulong]
        self.prctl.restype = ctypes.c_int

    def signal_target(self, pid):
        require(type(pid) is int and 1 < pid < 2**31 and pid != self.pid and
                pid not in self.protected_pids, 'forbidden signal target')
        self.single_thread()

    def flag(self):
        value = ctypes.c_int(-1)
        if self.prctl(37, ctypes.addressof(value), 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'PR_GET_CHILD_SUBREAPER')
        require(value.value in (0, 1), 'invalid own subreaper flag')
        return value.value

    def set_flag(self, value):
        if self.prctl(36, value, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'PR_SET_CHILD_SUBREAPER')

    def single_thread(self):
        require(os.getpid() == self.pid and signal.getsignal(signal.SIGCHLD) == signal.SIG_DFL,
                'controller PID/SIGCHLD ownership changed')
        names = []
        with os.scandir('/proc/%d/task' % self.pid) as rows:
            for row in rows:
                names.append(row.name)
                require(len(names) <= 1, 'controller is no longer single-threaded')
        require(names == [str(self.pid)], 'controller thread identity changed')

    def children(self):
        # Fixed self task only, never an all-/proc or other-actor enumeration.
        fd = os.open('/proc/%d/task/%d/children' % (self.pid, self.pid),
                     os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
        try:
            data = os.read(fd, 8193)
            require(len(data) <= 8192 and os.read(fd, 1) == b'', 'own children list exceeds bound')
        finally:
            os.close(fd)
        fields = data.split()
        require(len(fields) <= 128 and len(fields) == len(set(fields)), 'own child count differs')
        require(all(x.isdigit() and x == str(int(x)).encode() and 0 < int(x) < 2**31
                    for x in fields), 'malformed own children list')
        return [int(x) for x in fields]

    def empty(self):
        self.single_thread()
        require(self.children() == [], 'controller retains child processes')
        try:
            os.waitid(os.P_ALL, 0, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        except ChildProcessError:
            return True
        raise RuntimeError('kernel wait authority did not confirm ECHILD')

    def begin(self):
        require(hasattr(os, 'P_PIDFD') and hasattr(os, 'WNOWAIT'), 'held nonreaping wait unavailable')
        self.empty()
        self.original = self.flag()
        self.record['original_subreaper_flag'] = self.original
        if self.original == 0:
            self.set_flag(1)
            self.changed = True
        require(self.flag() == 1, 'own subreaper did not become active')
        self.active = True
        self.record['begin_passed'] = True

    def before_command(self):
        require(self.active and self.flag() == 1, 'own subreaper not active')
        self.empty()

    def finish(self):
        self.empty()
        self.record['final_children_empty'] = True
        if self.original is not None:
            require(self.flag() == 1, 'own subreaper flag changed during commands')
            if self.changed:
                self.set_flag(self.original)
                self.changed = False
            require(self.flag() == self.original, 'own subreaper flag not restored')
        self.active = False
        self.record['restored'] = True

    @staticmethod
    def peek(pid, pidfd):
        info = os.waitid(os.P_PIDFD if pidfd is not None else os.P_PID,
                         pidfd if pidfd is not None else pid,
                         os.WEXITED | os.WNOHANG | os.WNOWAIT)
        if info is not None:
            require(info.si_pid == pid and info.si_code in
                    (os.CLD_EXITED, os.CLD_KILLED, os.CLD_DUMPED),
                    'owned child wait status differs')
        return info

    @staticmethod
    def observed(info):
        return {'pid': info.si_pid, 'code': info.si_code, 'status': info.si_status}

    def await_exit(self, pid, pidfd, deadline):
        poller = select.poll()
        poller.register(pidfd, select.POLLIN)
        while True:
            info = self.peek(pid, pidfd)
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('owned child exit deadline')
            if info is not None:
                return info
            poller.poll(max(1, min(100, int(remaining * 1000))))

    def retire(self, process, pidfd, record, remember, deadline):
        record['descendants'] = []
        record['owned_tree_cleanup_complete'] = False
        cleanup_started = time.monotonic()
        if process is not None:
            self.retire_leader(process, pidfd, record, remember, deadline)
        # A launch exception can happen after fork but before Popen returns.
        # In that case only this controller's kernel-listed children are used.
        if process is None or record['child_reaped']:
            self.retire_adopted(record, remember, deadline)
        record['cleanup_elapsed_seconds'] = time.monotonic() - cleanup_started
        try:
            record['remaining_owned_children'] = self.children()
        except BaseException as error:
            record['remaining_owned_children'] = None
            record['owned_tree_cleanup_complete'] = False
            remember(error, 'remaining_owned_children')

    def retire_leader(self, process, pidfd, record, remember, deadline):
        try:
            self.signal_target(process.pid)
            # WNOWAIT / direct-child relationship reserves the leader PID until
            # after group signalling. No killpg occurs after leader reaping.
            info = self.peek(process.pid, pidfd)
            record['leader_unreaped_before_group_cleanup'] = True
            record['leader_alive_before_group_cleanup'] = info is None
            if info is not None:
                record['leader_observed_before_reap'] = self.observed(info)
            require(os.getpgid(process.pid) == process.pid and
                    os.getsid(process.pid) == process.pid, 'owned session/group identity changed')
            if info is not None and self.children() == [process.pid]:
                # The unreaped exited leader has no surviving descendants:
                # exit has already reparented any descendants to this subreaper.
                # Do not signal an exited privileged leader merely to reap it.
                record['group_signal_unneeded_exited_only_child'] = True
            else:
                record['owned_group_kill_attempted'] = True
                record['kill_attempted'] = True
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                    record['owned_group_kill_completed'] = True
                except ProcessLookupError:
                    require(info is not None, 'live original group disappeared')
                    record['owned_group_already_absent'] = True
        except BaseException as error:
            remember(error, 'owned_group_cleanup')
            # If group qualification failed, kill only the known direct child.
            try:
                self.signal_target(process.pid)
                if self.peek(process.pid, pidfd) is None:
                    if pidfd is not None:
                        signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                    else:
                        # The successful P_PID wait above proves this is still
                        # this controller's unreaped child, so its PID cannot be reused.
                        process.kill()
                    record['direct_child_fallback_kill_attempted'] = True
            except BaseException as error:
                remember(error, 'direct_child_fallback_cleanup')
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
            record['returncode'] = process.returncode
            record['child_reaped'] = True
        except BaseException as error:
            remember(error, 'reap_direct_child')
    def retire_adopted(self, record, remember, deadline):
        seen = set()
        while True:
            try:
                children = self.children()
                if not children:
                    self.empty()
                    record['owned_tree_cleanup_complete'] = True
                    break
                require(time.monotonic() < deadline, 'adopted child cleanup deadline')
                require(not (set(children) & seen), 'an earlier adopted child was not reaped')
                require(len(seen) + len(children) <= 128, 'adopted child total bound exceeded')
            except BaseException as error:
                remember(error, 'adopted_child_list_or_gate')
                break
            complete = True
            for child in children:
                if time.monotonic() >= deadline:
                    remember(TimeoutError('adopted child cleanup deadline'), 'adopted_child_deadline')
                    complete = False
                    break
                seen.add(child)
                item = {'pid': child, 'kill_attempted': False, 'reaped': False, 'pidfd_closed': True}
                record['descendants'].append(item)
                held = None
                try:
                    # The kernel-listed unreaped direct/adopted child cannot be
                    # reaped by another waiter: this controller is single-threaded.
                    try:
                        held = os.pidfd_open(child, 0)
                        item['pidfd_closed'] = False
                    except BaseException as error:
                        # Keep this failure, but still retire the kernel-proven
                        # unreaped child if descriptor allocation itself failed.
                        item['pidfd_open_error'] = repr(error)
                        remember(error, 'adopted_pidfd_open')
                    self.signal_target(child)
                    info = self.peek(child, held)
                    if info is None:
                        item['kill_attempted'] = True
                        try:
                            if held is not None:
                                signal.pidfd_send_signal(held, signal.SIGKILL)
                            else:
                                os.kill(child, signal.SIGKILL)
                        except PermissionError as error:
                            # Only the outer UID1000 controller permits this
                            # passive wait for its fixed root supervisor. EPERM
                            # remains a failure; it is never cleanup authority.
                            remember(error, 'adopted_child_signal_permission')
                            item['signal_permission_error'] = repr(error)
                            if not self.passive_root_wait:
                                raise
                        if held is not None:
                            info = self.await_exit(child, held, deadline)
                        else:
                            while info is None and time.monotonic() < deadline:
                                time.sleep(0.005)
                                info = self.peek(child, None)
                            require(info is not None, 'owned child fallback wait deadline')
                    item['observed_before_reap'] = self.observed(info)
                    waited, status = os.waitpid(child, os.WNOHANG)
                    require(waited == child, 'observed terminal adopted child was not reaped')
                    item['wait_status'] = status
                    item['reaped'] = True
                except BaseException as error:
                    complete = False
                    item['error'] = repr(error)
                    remember(error, 'adopted_child_cleanup')
                finally:
                    if held is not None:
                        value, held = held, None
                        try:
                            os.close(value)
                            item['pidfd_closed'] = True
                        except BaseException as error:
                            complete = False
                            remember(error, 'adopted_pidfd_close')
            if not complete:
                break
        if record['descendants']:
            # Successful drivers must normally reap their own helpers. Cleanup
            # success is not permission to count orphaned/forced helpers as a
            # successful compilation.
            remember(RuntimeError('driver left descendant processes after its exit'),
                     'driver_left_descendants')


class ForkProcess:
    """A direct child created by our one os.fork; it has not been reaped."""
    def __init__(self, pid):
        self.pid = pid
        self.returncode = None

    def kill(self):
        os.kill(self.pid, signal.SIGKILL)

    def wait(self, timeout):
        deadline = time.monotonic() + max(0, timeout)
        while self.returncode is None:
            waited, status = os.waitpid(self.pid, os.WNOHANG)
            if waited == self.pid:
                self.returncode = os.waitstatus_to_exitcode(status)
                break
            require(waited == 0, 'fork child wait returned another PID')
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired('fixed-owned-fork', timeout)
            time.sleep(min(0.005, max(0, deadline - time.monotonic())))
        return self.returncode


def fork_fixed(worker, input_fd, output_fd, error_fd, output_bound, startup_deadline):
    # Only the caller's fixed snapshot/control callback is supplied. There is
    # no argv, path, user-selected Python or arbitrary privileged task API.
    sys.stdout.flush()
    sys.stderr.flush()
    pid = os.fork()
    if pid:
        child = ForkProcess(pid)
        # Unlike Popen's exec handshake, fork returns before setsid. Observe
        # the new group before returning, without reaping or signalling it.
        while True:
            info = OwnChildReaper.peek(pid, None)
            if (os.getpgid(pid) == pid and os.getsid(pid) == pid) or info is not None:
                return child
            if time.monotonic() >= startup_deadline:
                raise TimeoutError('owned fork session startup deadline')
            time.sleep(0.002)
    try:
        os.setsid()
        for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGALRM):
            signal.signal(number, signal.SIG_DFL)
        signal.setitimer(signal.ITIMER_REAL, 0)
        for original, target in ((input_fd, 0), (output_fd, 1), (error_fd, 2)):
            os.dup2(original, target)
        for fd in (input_fd, output_fd, error_fd):
            if fd > 2:
                os.close(fd)
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_FSIZE, (output_bound, output_bound))
        worker()
        code = 0
    except SystemExit as error:
        code = error.code if type(error.code) is int and 0 <= error.code <= 255 else 1
    except BaseException as error:
        try:
            raw = (json.dumps({'fixed_child_error': type(error).__name__,
                               'errno': getattr(error, 'errno', None)}) + '\n').encode()
            os.write(2, raw)
        except BaseException:
            pass
        code = 1
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except BaseException:
        code = 1
    os._exit(code)


def fd_identity(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_size,
            info.st_mtime_ns, info.st_ctime_ns]


def sealed_input(data, bound, record, remember):
    require(type(data) is bytes and len(data) <= bound, 'owned input exceeds bound')
    fd = os.memfd_create('fixed-capture-input', os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
    record['fd'] = fd
    record['acquired'] = True
    record['closed'] = False
    record['bytes'] = len(data)
    record['sha256'] = hashlib.sha256(data).hexdigest()
    offset = 0
    while offset < len(data):
        count = os.write(fd, data[offset:])
        require(count > 0, 'owned input write made no progress')
        offset += count
    fcntl.fcntl(fd, fcntl.F_ADD_SEALS,
                fcntl.F_SEAL_WRITE | fcntl.F_SEAL_GROW | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_SEAL)
    os.lseek(fd, 0, os.SEEK_SET)
    record['sealed'] = True
    return fd


def read_output(fd, bound):
    before = os.fstat(fd)
    require(stat.S_ISREG(before.st_mode) and 0 <= before.st_size <= bound,
            'owned output exceeds bound')
    os.lseek(fd, 0, os.SEEK_SET)
    raw = bytearray()
    while True:
        part = os.read(fd, min(65536, bound + 1 - len(raw)))
        if not part:
            break
        raw.extend(part)
        require(len(raw) <= bound, 'owned output grew beyond bound')
    require(len(raw) == before.st_size and fd_identity(before) == fd_identity(os.fstat(fd)),
            'owned output changed during read')
    return bytes(raw)


def invoke_owned(reaper, factory, input_bytes, observation_deadline, cleanup_deadline,
                 output_bound=65536, input_bound=196608, pidfd_factory=None,
                 cleanup_enter=None, retirement_grace=None):
    """Run exactly one caller-fixed child, preserving the first failure.

    The observation deadline and final retirement deadline are absolute. A
    timeout never renews a budget. A pidfd allocation failure keeps its errno;
    the kernel-proven unreaped child PID can still be retired without reuse.
    """
    record = {'schema': 1, 'child_started': False, 'child_reaped': False,
              'pid': None, 'returncode': None, 'timed_out': False,
              'kill_attempted': False, 'pidfd_closed': True,
              'owned_tree_cleanup_complete': False, 'descendants': [],
              'remaining_owned_children': None, 'first_error': None,
              'secondary_errors': [], 'observation_deadline': observation_deadline,
              'retirement_deadline': cleanup_deadline, 'all_acquired_fds_closed': False,
              'input': {'acquired': False, 'closed': True},
              'stdout': {'acquired': False, 'closed': True},
              'stderr': {'acquired': False, 'closed': True}}
    first = None
    process = None
    pidfd = None
    ownership_admitted = False
    values = {'input': None, 'stdout': None, 'stderr': None}
    outputs = {'stdout': None, 'stderr': None}

    def remember(error, stage):
        nonlocal first
        item = safe_error(error, stage)
        if first is None:
            first = error
            record['first_error'] = item
        else:
            record['secondary_errors'].append(item)

    try:
        reaper.before_command()
        ownership_admitted = True
        require(time.monotonic() < observation_deadline < cleanup_deadline,
                'owned observation deadline already elapsed')
        values['input'] = sealed_input(input_bytes, input_bound, record['input'], remember)
        for name in ('stdout', 'stderr'):
            value = os.memfd_create('fixed-capture-' + name, os.MFD_CLOEXEC)
            values[name] = value
            record[name].update({'fd': value, 'acquired': True, 'closed': False})
        process = factory(values['input'], values['stdout'], values['stderr'], output_bound)
        record['child_started'] = True
        record['pid'] = process.pid
        reaper.signal_target(process.pid)
        pidfd = (pidfd_factory or os.pidfd_open)(process.pid, 0)
        record['pidfd_closed'] = False
        record['pidfd'] = pidfd
        info = reaper.await_exit(process.pid, pidfd, observation_deadline)
        record['observed_before_reap'] = reaper.observed(info)
        if info.si_code != os.CLD_EXITED or info.si_status != 0:
            remember(RuntimeError('fixed child did not exit zero'), 'child_exit')
    except BaseException as error:
        if isinstance(error, (TimeoutError, subprocess.TimeoutExpired)):
            record['timed_out'] = True
        remember(error, 'start_or_wait')
    finally:
        if retirement_grace is not None:
            cleanup_deadline = min(cleanup_deadline, time.monotonic() + retirement_grace)
        record['retirement_deadline'] = cleanup_deadline
        if cleanup_enter is not None:
            try:
                cleanup_enter(cleanup_deadline)
            except BaseException as error:
                remember(error, 'enter_retirement')
        if ownership_admitted:
            try:
                reaper.retire(process, pidfd, record, remember, cleanup_deadline)
            except BaseException as error:
                remember(error, 'owned_retirement')
        else:
            # A failed empty-child gate authorizes no signal to those children.
            record['ownership_not_admitted_no_retirement'] = True
        if pidfd is not None:
            value, pidfd = pidfd, None
            try:
                os.close(value)
                record['pidfd_closed'] = True
            except BaseException as error:
                remember(error, 'leader_pidfd_close')
        # Read each independent bounded stream even if the other failed.
        for name in ('stdout', 'stderr'):
            fd = values[name]
            if fd is not None:
                try:
                    raw = read_output(fd, output_bound)
                    outputs[name] = raw
                    record[name].update({'bytes': len(raw),
                        'sha256': hashlib.sha256(raw).hexdigest(), 'complete': True})
                except BaseException as error:
                    record[name]['complete'] = False
                    remember(error, name + '_read')
        for name in ('input', 'stdout', 'stderr'):
            # sealed_input may fail after acquiring a descriptor but before it
            # returns. Its record is the acquisition journal in that branch.
            fd = values[name]
            if fd is None and record[name]['acquired'] and not record[name]['closed']:
                fd = record[name]['fd']
            if fd is not None:
                values[name] = None
                try:
                    os.close(fd)
                    record[name]['closed'] = True
                except BaseException as error:
                    remember(error, name + '_close')
        record['all_acquired_fds_closed'] = (record['pidfd_closed'] and
            all(record[name]['closed'] for name in ('input', 'stdout', 'stderr')) and
            all(row['pidfd_closed'] for row in record['descendants']))
        record['finished_monotonic'] = time.monotonic()
        record['retirement_within_deadline'] = record['finished_monotonic'] <= cleanup_deadline
        if not record['retirement_within_deadline']:
            remember(TimeoutError('owned retirement deadline exceeded'), 'retirement_deadline')
        if not (record['child_started'] and record['child_reaped'] and
                record['owned_tree_cleanup_complete'] and record['all_acquired_fds_closed']):
            remember(RuntimeError('owned capture lifecycle incomplete'), 'final_lifecycle_gate')
        record['qualified_success'] = first is None
    return record, outputs['stdout'], outputs['stderr'], first
