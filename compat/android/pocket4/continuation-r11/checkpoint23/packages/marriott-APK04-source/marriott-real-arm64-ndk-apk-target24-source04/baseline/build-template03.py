"""Build the original ARM64 NDK test APK from bound real inputs; never install or run it."""
import base64
import ctypes
import errno
import hashlib
import json
import os
from pathlib import Path
import re
import resource
import select
import shlex
import signal
import stat
import struct
import subprocess
import sys
import time
import traceback
import io
import secrets
import types
import zipfile
import xml.etree.ElementTree as ET

CFG = None  # The immutable packet generator fills this exactly once.
BUILD_STARTED = time.monotonic()
CHILD_REAPER = None
INPUT_FD_EVENTS = []

def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def create(path, data, mode=0o444):
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, 'wb', closefd=False) as stream:
            stream.write(data)
            stream.flush()
            os.fsync(fd)
    finally:
        os.close(fd)


def limit_child_outputs():
    # The fixed compiler/control children inherit a per-regular-file ceiling.
    # The controller's complete result is written outside this child-only limit.
    resource.setrlimit(resource.RLIMIT_FSIZE, (33554432, 33554432))


class OwnChildReaper:
    """Retire only children of this single-threaded isolated controller."""
    def __init__(self):
        self.pid = os.getpid()
        self.original = None
        self.changed = False
        self.active = False
        self.record = {'pid': self.pid, 'begin_passed': False, 'restored': False,
                       'final_children_empty': False, 'max_adopted_per_command': 128,
                       'cleanup_seconds_per_command': 5}
        self.libc = ctypes.CDLL(None, use_errno=True)
        self.prctl = self.libc.prctl
        self.prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                              ctypes.c_ulong, ctypes.c_ulong]
        self.prctl.restype = ctypes.c_int

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
            if info is not None:
                return info
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('owned child exit deadline')
            poller.poll(max(1, min(100, int(remaining * 1000))))

    def retire(self, process, pidfd, record, remember, deadline):
        record['descendants'] = []
        record['owned_tree_cleanup_complete'] = False
        try:
            # WNOWAIT / direct-child relationship reserves the leader PID until
            # after group signalling. No killpg occurs after leader reaping.
            info = self.peek(process.pid, pidfd)
            record['leader_unreaped_before_group_cleanup'] = True
            record['leader_alive_before_group_cleanup'] = info is None
            if info is not None:
                record['leader_observed_before_reap'] = self.observed(info)
            require(os.getpgid(process.pid) == process.pid and
                    os.getsid(process.pid) == process.pid, 'owned session/group identity changed')
            record['owned_group_kill_attempted'] = True
            record['kill_attempted'] = True
            try:
                os.killpg(process.pid, signal.SIGKILL)
                record['owned_group_kill_completed'] = True
            except ProcessLookupError:
                require(info is not None, 'live original group disappeared')
                record['owned_group_already_absent'] = True
        except Exception as error:
            remember(error, 'owned_group_cleanup')
            # If group qualification failed, kill only the known direct child.
            try:
                if self.peek(process.pid, pidfd) is None:
                    if pidfd is not None:
                        signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                    else:
                        # The successful P_PID wait above proves this is still
                        # this controller's unreaped child, so its PID cannot be reused.
                        process.kill()
                    record['direct_child_fallback_kill_attempted'] = True
            except Exception as error:
                remember(error, 'direct_child_fallback_cleanup')
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
            record['returncode'] = process.returncode
            record['child_reaped'] = True
        except Exception as error:
            remember(error, 'reap_direct_child')
        if not record['child_reaped']:
            return
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
            except Exception as error:
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
                    except Exception as error:
                        # Keep this failure, but still retire the kernel-proven
                        # unreaped child if descriptor allocation itself failed.
                        item['pidfd_open_error'] = repr(error)
                        remember(error, 'adopted_pidfd_open')
                    info = self.peek(child, held)
                    if info is None:
                        item['kill_attempted'] = True
                        if held is not None:
                            signal.pidfd_send_signal(held, signal.SIGKILL)
                            info = self.await_exit(child, held, deadline)
                        else:
                            os.kill(child, signal.SIGKILL)
                            while info is None and time.monotonic() < deadline:
                                time.sleep(0.005)
                                info = self.peek(child, None)
                            require(info is not None, 'owned child fallback wait deadline')
                    item['observed_before_reap'] = self.observed(info)
                    waited, status = os.waitpid(child, os.WNOHANG)
                    require(waited == child, 'observed terminal adopted child was not reaped')
                    item['wait_status'] = status
                    item['reaped'] = True
                except Exception as error:
                    complete = False
                    item['error'] = repr(error)
                    remember(error, 'adopted_child_cleanup')
                finally:
                    if held is not None:
                        value, held = held, None
                        try:
                            os.close(value)
                            item['pidfd_closed'] = True
                        except Exception as error:
                            complete = False
                            remember(error, 'adopted_pidfd_close')
            if not complete:
                break
        record['cleanup_elapsed_seconds'] = time.monotonic() - (deadline - 5)
        if record['descendants']:
            # Successful drivers must normally reap their own helpers. Cleanup
            # success is not permission to count orphaned/forced helpers as a
            # successful compilation.
            remember(RuntimeError('driver left descendant processes after its exit'),
                     'driver_left_descendants')


def command(report, root, argv, timeout=25, pidfd_factory=None):
    index = len(report['commands'])
    output = root / ('command%02d.stdout' % index)
    error_path = root / ('command%02d.stderr' % index)
    record = {'argv': argv, 'cwd': str(root), 'timeout_seconds': timeout,
              'timed_out': False, 'child_started': False, 'child_reaped': False,
              'kill_attempted': False, 'pidfd_closed': True, 'output_fds_closed': False,
              'first_error': None, 'secondary_errors': [],
              'owned_tree_cleanup_complete': False}
    report['commands'].append(record)
    process = None
    pidfd = None
    streams = []
    first = None

    def remember(error, stage):
        nonlocal first
        item = {'stage': stage, 'error': repr(error)}
        if first is None:
            first = error
            record['first_error'] = item
        else:
            record['secondary_errors'].append(item)

    try:
        CHILD_REAPER.before_command()
        remaining = CFG['controller_work_seconds'] - (time.monotonic() - BUILD_STARTED)
        require(remaining > 0, 'controller work deadline expired before child admission')
        for path in (output, error_path):
            streams.append(path.open('xb'))
        environment = {'PATH': CFG['java_home']+'/bin:/usr/bin:/bin',
                       'JAVA_HOME': CFG['java_home'], 'LC_ALL': 'C', 'LANG': 'C',
                       'TMPDIR': str(root / 'tmp'), 'PYTHONDONTWRITEBYTECODE': '1'}
        if 'HOME' in os.environ:
            environment['HOME'] = os.environ['HOME']  # Inherit exactly; never repurpose/reset HOME.
        process = subprocess.Popen(argv, cwd=root, stdin=subprocess.DEVNULL,
            stdout=streams[0], stderr=streams[1], close_fds=True, start_new_session=True,
            preexec_fn=limit_child_outputs, env=environment)
        record['pid'] = process.pid
        record['child_started'] = True
        pidfd = (pidfd_factory or os.pidfd_open)(process.pid, 0)
        record['pidfd_closed'] = False
        try:
            info = CHILD_REAPER.await_exit(process.pid, pidfd,
                time.monotonic() + min(timeout, remaining))
            record['leader_observed_without_reap'] = CHILD_REAPER.observed(info)
            if info.si_code != os.CLD_EXITED or info.si_status != 0:
                remember(RuntimeError('original command exited unsuccessfully before cleanup'),
                         'leader_exit_status')
        except TimeoutError:
            record['timed_out'] = True
            raise subprocess.TimeoutExpired(argv, timeout)
    except Exception as error:
        remember(error, 'start_or_wait')
    finally:
        if process is not None:
            cleanup_deadline = time.monotonic() + 5
            try:
                CHILD_REAPER.retire(process, pidfd, record, remember, cleanup_deadline)
            except Exception as error:
                remember(error, 'unexpected_owned_tree_cleanup_error')
                # Do not let an unexpected diagnostic error skip the direct
                # child's final wait. Group/adoption qualification stays false.
                try:
                    if process.returncode is None and CHILD_REAPER.peek(process.pid, pidfd) is None:
                        if pidfd is not None:
                            signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                        else:
                            process.kill()
                except Exception as error:
                    remember(error, 'final_direct_kill')
                try:
                    process.wait(timeout=max(0, cleanup_deadline - time.monotonic()))
                    record['returncode'] = process.returncode
                    record['child_reaped'] = True
                except Exception as error:
                    remember(error, 'final_direct_wait')
        if pidfd is not None:
            value, pidfd = pidfd, None
            try:
                os.close(value)
                record['pidfd_closed'] = True
            except Exception as error:
                remember(error, 'close_pidfd')
        closed = True
        for stream in reversed(streams):
            try:
                stream.close()
            except Exception as error:
                closed = False
                remember(error, 'close_output_file')
        record['output_fds_closed'] = closed
    # Each output is retained independently; a capture error cannot hide the
    # earlier child failure or prevent the other stream from being checked.
    for key, path in [('stdout', output), ('stderr', error_path)]:
        try:
            with path.open('rb') as stream:
                before = os.fstat(stream.fileno())
                require(stat.S_ISREG(before.st_mode) and before.st_size <= 262144,
                        'command output exceeds bound')
                data = stream.read(262145)
                after = os.fstat(stream.fileno())
            require(len(data) == before.st_size and
                    (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_ctime_ns) ==
                    (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_ctime_ns),
                    'command output changed during complete capture')
            record[key + '_bytes'] = len(data)
            record[key + '_sha256'] = digest(data)
            record[key] = data.decode('utf-8')
            record[key + '_complete'] = True
        except Exception as error:
            record[key + '_complete'] = False
            remember(error, 'capture_' + key)
    if first is not None:
        raise first
    require(record.get('returncode') == 0 and record['child_reaped'] and
            record['pidfd_closed'] and record['output_fds_closed'] and
            record['owned_tree_cleanup_complete'] and not record['timed_out'],
            'matching build/control command failed: ' + str(index))
    return record



def tick():
    require(time.monotonic() - BUILD_STARTED < CFG['controller_work_seconds'],
            'compile controller work deadline')

def stamp(s):
    return (s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid,
            s.st_nlink, s.st_size, s.st_mtime_ns, s.st_ctime_ns)

def within(path, roots):
    return any(path == root or path.is_relative_to(root) for root in roots)

def read_input(path, maximum=8*1024*1024, expected=None, roots=None):
    tick()
    original = Path(path)
    resolved = original.resolve(strict=True)
    if roots is not None:
        require(within(resolved, roots),
                'fixed source/dependency root escaped: named='+str(original)+' resolved='+str(resolved))
    require(len(INPUT_FD_EVENTS) < 131072, 'input FD event bound')
    fd = os.open(resolved, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    event = None
    try:
        event = {'fd':fd, 'path':str(original), 'closed':False}
        INPUT_FD_EVENTS.append(event)
        before = os.fstat(fd)
        require(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and
                0 <= before.st_size <= maximum, 'input shape/size differs: '+str(original))
        parts = []
        total = 0
        while True:
            tick()
            data = os.read(fd, min(65536, maximum+1-total))
            if not data:
                break
            parts.append(data)
            total += len(data)
            require(total <= maximum, 'input grew beyond bound')
        data = b''.join(parts)
        after = os.fstat(fd)
        require(len(data) == before.st_size and stamp(before) == stamp(after) and
                original.resolve(strict=True) == resolved and
                stamp(resolved.stat(follow_symlinks=False)) == stamp(after),
                'input held/name changed: '+str(original))
        record = dict(zip(('device','inode','mode','uid','gid','nlink','bytes','mtime_ns','ctime_ns'),
                          stamp(after)))
        record.update(path=str(original), resolved_path=str(resolved), sha256=digest(data))
        if expected is not None:
            require(record['bytes'] == expected['bytes'] and record['sha256'] == expected['sha256'],
                    'input whole-byte pin differs: '+str(original))
        return data, record
    finally:
        primary = sys.exception()
        try:
            os.close(fd)
            if event is not None:
                event['closed'] = True
        except BaseException as close_error:
            if primary is not None:
                primary.add_note('input close failed: '+repr(close_error))
            else:
                raise


def exact_reader_binding(name, kind, specs):
    binding = CFG[name]
    require(type(binding) is dict and set(binding) == {'bytes','sha256','base64','terminal'},
            'actual input reader binding is missing')
    raw = base64.b64decode(binding['base64'], validate=True)
    require(len(raw) == binding['bytes'] and digest(raw) == binding['sha256'] and
            len(raw) <= 1048576, 'actual input reader whole bytes differ')
    terminal = binding['terminal']
    require(type(terminal) is dict and set(terminal) == {'bytes','sha256','base64','job_id'},
            'actual terminal original binding is missing')
    terminal_raw = base64.b64decode(terminal['base64'],validate=True)
    require(0 < len(terminal_raw) <= 32768 and len(terminal_raw) == terminal['bytes'] and
            digest(terminal_raw) == terminal['sha256'],
            'actual terminal whole bytes differ')
    status = json.loads(terminal_raw)
    require(status.get('job_id') == terminal['job_id'] and
            re.fullmatch('[0-9a-f]+-[0-9a-f]+-[0-9a-f]+',terminal['job_id']) is not None and
            status.get('state') == 'succeeded' and status.get('exit_code') == 0 and
            status.get('output_complete') is True and status.get('output_durable') is True and
            status.get('terminal_publication_confirmed') is True and
            status.get('timed_out') is False and status.get('cancelled') is False and
            status.get('automatic_retry') is False and
            all(status['log_synced'][k] is True and status['log_truncated'][k] is False and
                status['log_errors'][k] is None for k in ('stdout','stderr')) and
            status['log_bytes']['stdout'] == {'seen':len(raw),'stored':len(raw)} and
            status['log_bytes']['stderr'] == {'seen':0,'stored':0},
            'actual input reader did not publish a complete successful terminal')
    value = json.loads(raw)
    require(value.get('kind') == kind and value.get('collection_complete') is True and
            value.get('errors') == [] and value.get('first_error') is None and
            value.get('all_tracked_owned_FDs_closed') is True and
            value.get('control_deadline_met') is True and
            value.get('own_resource_interval_qualified') is True and
            all(value.get(k) == 0 for k in
                ('Main_actions','Android_actions','children_started','files_written',
                 'directory_enumerations','network_calls','tool_or_library_executions')),
            'actual fixed input reader did not close its scope')
    return value, qualify_input_rows(value.get('inputs'), specs)


def qualify_input_rows(rows, specs):
    require(type(rows) is list and len(rows) == len(specs), 'exact reader input count')
    by_role = {}
    for actual, spec in zip(rows, specs):
        require(actual.get('role') == spec['role'] and actual.get('path') == spec['path'] and
                actual.get('complete') is True and actual.get('full_reads') == 2 and
                actual.get('error') is None and actual.get('expected_matches') is True and
                actual.get('whole_input_and_identity_unchanged') is True and
                actual.get('owned_leaf_FDs_closed') is True,
                'fixed actual input row differs: '+spec['role'])
        before = actual['before']
        require(all(actual[k] == before for k in
                    ('named_before','named_after','held_after')) and
                actual['bytes'] == before['bytes'] and 0 < actual['bytes'] <= spec['maximum'] and
                re.fullmatch('[0-9a-f]{64}', actual['sha256']) is not None and
                stat.S_ISREG(before['mode']) and before['nlink'] == 1,
                'actual input complete tuple differs: '+spec['role'])
        for k in ('bytes','sha256'):
            if 'expected_'+k in spec:
                require(actual[k] == spec['expected_'+k], 'original expected input pin differs')
        if spec['format'] == 'archive':
            facts = actual['format_facts']
            require(facts.get('format') == 'regular_archive' and
                    facts.get('architecture_qualified') is True and
                    facts.get('all_members_ELF64_AARCH64_REL_LSB') is True and
                    facts.get('external_members_followed') is False and
                    facts.get('LLVM_bitcode_members') == facts.get('other_members') == 0,
                    'actual archive is not a complete ARM64 REL archive')
        elif spec['format'] == 'zip':
            facts = actual['format_facts']
            require(facts.get('all_required_classes_present') is True and
                    set(facts['required_classes']) == set(spec['required_classes']) and
                    all(facts['required_classes'][n].get('present') is True for n in spec['required_classes']),
                    'actual SDK class interfaces incomplete')
        by_role[spec['role']] = actual
    return by_role


def original_sdk22_inputs():
    """Preserve the actual failed attempt while qualifying only its 21 complete observations."""
    binding=CFG['actual_sdk22_failed_original']
    raw=base64.b64decode(binding['base64'],validate=True)
    terminal=base64.b64decode(binding['terminal']['base64'],validate=True)
    require(len(raw)==79928 and digest(raw)==
            'f952b570b665438b367f78fbef0a17232d78ced69463832b9d12b1316a700a83' and
            binding['bytes']==len(raw) and binding['sha256']==digest(raw),
            'original failed SDK22 complete bytes changed')
    require(len(terminal)==730 and digest(terminal)==
            '7c7e8babe91d926cea8f583532ffe7ad517213b024e41db841f1154c8f0671c3',
            'original failed SDK22 terminal changed')
    status=json.loads(terminal)
    require(status['job_id']=='1a1b19b46a3-fc05-79d7' and status['state']=='failed' and
            status['exit_code']==1 and status['output_complete'] is True and
            status['output_durable'] is True and status['terminal_publication_confirmed'] is True and
            status['timed_out'] is False and status['cancelled'] is False and
            status['log_bytes']=={'stdout':{'seen':79928,'stored':79928},
                                  'stderr':{'seen':0,'stored':0}} and
            all(status['log_synced'][k] is True and status['log_truncated'][k] is False and
                status['log_errors'][k] is None for k in ('stdout','stderr')),
            'original failed SDK22 terminal scope changed')
    value=json.loads(raw)
    expected_error={'errno':2,'message':"[Errno 2] No such file or directory: 'soong.variables'",
                    'stage':'input:existing_soong_variables','type':'FileNotFoundError'}
    require(value['kind']=='p4-marriott-arm64-crt-sdk-input-read01' and
            value['collection_complete'] is False and value['errors']==[expected_error] and
            value['first_error']==expected_error and
            value['all_tracked_owned_FDs_closed'] is True and
            value['control_deadline_met'] is True and value['own_resource_interval_qualified'] is True and
            all(value[k]==0 for k in ('Main_actions','Android_actions','children_started',
                'files_written','directory_enumerations','network_calls','tool_or_library_executions')),
            'original SDK22 failure has an additional or different failure')
    specs=CFG['sdk_input_specifications']
    require(len(specs)==len(value['inputs'])==22 and
            all(r['path']==s['path'] and r['role']==s['role']
                for r,s in zip(value['inputs'],specs)),
            'original SDK22 fixed observation order differs')
    failed=[r for r in value['inputs'] if r['role']=='existing_soong_variables']
    require(len(failed)==1 and failed[0]['complete'] is False and
            failed[0]['error']==expected_error and failed[0]['full_reads']==0,
            'original missing configuration was not preserved')
    rows=[r for r in value['inputs'] if r['role']!='existing_soong_variables']
    remaining=[s for s in specs if s['role']!='existing_soong_variables']
    require(len(rows)==len(remaining)==21,'original complete input count differs')
    return value,qualify_input_rows(rows,remaining)


def qualified_sdk_bindings():
    original,prior=original_sdk22_inputs()
    pending=CFG['actual_sdk_configuration']
    require(type(pending) is dict,'new successful fixed configuration observation required')
    raw=base64.b64decode(pending['base64'],validate=True)
    require(len(raw)==pending['bytes'] and digest(raw)==pending['sha256'] and
            0<len(raw)<=1048576,'new configuration original bytes differ')
    candidate=json.loads(raw)
    rows=candidate.get('inputs',[])
    require(type(rows) is list and len(rows)==9,'new configuration input count')
    environment=rows[7].get('format_facts',{})
    product=environment.get('TARGET_PRODUCT')
    require(type(product) is str and
            re.fullmatch('[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}',product) is not None and
            type(environment.get('EMMA_INSTRUMENT',{}).get('effective_true')) is bool,
            'observed product/coverage missing')
    suffix='.coverage' if environment['EMMA_INSTRUMENT']['effective_true'] else ''
    basename='soong.'+product+suffix+'.variables'
    require(environment.get('derived_basename')==basename,'observed derived basename differs')
    derived={'role':'existing_soong_variables','path':CFG['soong_output']+'/'+basename,
             'maximum':1048576,'format':'product_sdk_variables'}
    specs=[*CFG['sdk_configuration_specifications'],derived]
    actual,observed=exact_reader_binding('actual_sdk_configuration',
        'p4-marriott-soong-product-sdk-config-read01',specs)
    require(actual.get('derived_specification')==derived and
            actual.get('derived_candidate_read_attempts')==1 and
            actual.get('candidate_fallbacks')==0 and
            actual.get('original_failed_sdk22')=={
                'bytes':79928,
                'sha256':'f952b570b665438b367f78fbef0a17232d78ced69463832b9d12b1316a700a83',
                'job_id':'1a1b19b46a3-fc05-79d7','terminal_exit_code':1,'qualified_as_whole':False},
            'new observation did not preserve failed source lineage/one-path scope')
    require(observed['existing_soong_variables']['format_facts']['public_product_identity']==
            {'DeviceProduct':product,'Make_suffix':'-'+product+suffix},
            'new configuration product/coverage identity mismatch')
    for role in ('api_levels_source','symbolfile_source','existing_generated_api_map'):
        require(observed[role]['bytes']==prior[role]['bytes'] and
                observed[role]['sha256']==prior[role]['sha256'],
                'previously qualified SDK source/API map content changed')
    merged=dict(prior)
    merged.update(observed)
    effective=[]
    for spec in CFG['sdk_input_specifications']:
        effective.append(derived if spec['role']=='existing_soong_variables' else spec)
    effective.extend(s for s in CFG['sdk_configuration_specifications']
                     if s['role'] not in prior)
    require(len(effective)==27 and len({s['role'] for s in effective})==27,
            'fixed composed SDK source/configuration closure differs')
    return original,actual,merged,effective


def first_observe_apk13(report):
    """A new build's own fixed first observations; no prior reader02 admission is borrowed."""
    spec=CFG['apk13_observer']
    raw=base64.b64decode(spec['base64'],validate=True)
    require(len(raw)==spec['bytes'] and digest(raw)==spec['sha256'],
            'fixed original 13-input observation source differs')
    ns={'__name__':'own_build_apk13_first_observation'}
    exec(compile(raw,'<exact-original-apk13-observer>','exec'),ns)
    require(ns['INPUTS']==CFG['apk_input_specifications'] and
            ns['MAX_TOTAL']==230686720,'original thirteen input scope/bound differs')
    observed={'kind':'own_build_apk13_first_observation','rows':[],
              'prior_reader02_admission_borrowed':False,'source_sha256':spec['sha256'],
              'children_started':0,'Android_actions':0,'Main_actions':0,
              'format_requirements_passed':False,'first_error':None}
    report['apk13_first_observation']=observed
    old_handler=signal.getsignal(signal.SIGALRM)
    require(signal.getitimer(signal.ITIMER_REAL)==(0.0,0.0),'unexpected controller alarm')
    handler_installed=False
    primary=None
    by_role=None
    try:
        signal.signal(signal.SIGALRM,ns['alarm'])
        handler_installed=True
        signal.setitimer(signal.ITIMER_REAL,45.0)
        for index,specification in enumerate(ns['INPUTS']):
            ns['tick']()
            row=ns['observe'](specification)
            observed['rows'].append(row)
            if index<3 and not row['complete']:
                raise RuntimeError('original prior input anchor failed')
            require(time.monotonic()<ns['WORK_END'],'fixed own input observation deadline')
        require(not ns['ERRORS'],'fixed own input observation failed')
        by_role=qualify_input_rows(observed['rows'],CFG['apk_input_specifications'])
        observed['format_requirements_passed']=True
    except BaseException as error:
        primary=error
        ns['error']('own_build_fixed_input_gate',error)
    finally:
        try:
            signal.setitimer(signal.ITIMER_REAL,0.0)
        except BaseException as error:
            ns['error']('cancel_owned_input_alarm',error)
            if primary is None:
                primary=error
            else:
                primary.add_note('cancel_owned_input_alarm: '+repr(error))
        for event in reversed(ns['EVENTS']):
            ns['close'](event)
        if handler_installed:
            try:
                signal.signal(signal.SIGALRM,old_handler)
            except BaseException as error:
                ns['error']('restore_owned_input_alarm_handler',error)
                if primary is None:
                    primary=error
                else:
                    primary.add_note('restore_owned_input_alarm_handler: '+repr(error))
        observed['FD_events']=ns['EVENTS']
        observed['all_tracked_owned_FDs_closed']=all(x['closed'] for x in ns['EVENTS'])
        observed['global_ambient_FD_equality_asserted']=False
        observed['complete_bytes_read']=ns['TOTAL_READ']
        observed['errors']=ns['ERRORS']
        observed['first_error']=ns['ERRORS'][0] if ns['ERRORS'] else None
        observed['elapsed_seconds']=time.monotonic()-ns['START']
        observed['observation_deadline_seconds']=40
        observed['control_deadline_seconds']=45
        observed['control_deadline_met']=time.monotonic()<=ns['END']
    if primary is not None:
        if isinstance(primary,Exception):
            raise primary
        raise RuntimeError('fixed own input observation aborted: '+repr(primary)) from primary
    require(not ns['ERRORS'] and observed['all_tracked_owned_FDs_closed'] and
            observed['control_deadline_met'] and observed['format_requirements_passed'],
            'fixed own input observation resource closure incomplete')
    return by_role


def observe_bound_input(spec, actual, watch, report, role):
    body, row = read_input(spec['path'], spec['maximum'],
                           {'bytes':actual['bytes'],'sha256':actual['sha256']},
                           roots=[Path(spec['path'])])
    expected = dict(actual['before'], path=spec['path'], resolved_path=spec['path'],
                    sha256=actual['sha256'])
    require(row == expected, 'current input no longer equals complete reader tuple: '+role)
    if spec['path'] in watch:
        require(watch[spec['path']] == row, 'shared actual input tuple differs')
    watch[spec['path']] = row
    report['bound_inputs'][role] = row
    return body


def dependency_rows(path, target, roots, cpp):
    raw, _ = read_input(path, 262144, roots=[Path(CFG['root'])])
    text = raw.decode('utf-8').replace('\\\n', ' ')
    require(': ' in text, 'compiler dependency delimiter missing')
    got, payload = text.split(': ', 1)
    require(got.strip() == target, 'compiler dependency target differs')
    names = shlex.split(payload)
    require(0 < len(names) <= 2048 and len(names) == len(set(names)) and
            all(Path(x).is_absolute() for x in names), 'dependency count/absolute name differs')
    target_config = str(Path(CFG['aosp'])/'prebuilts/clang/host/linux-x86/clang-r584948b/android_libc++/ndk/aarch64/include/c++/v1/__config_site')
    actual_configs = [name for name in names if Path(name).name == '__config_site']
    require(actual_configs == ([target_config] if cpp else []),
            'wrong target C++ configuration in dependency set: '+repr(actual_configs))
    result, total = {}, 0
    for name in names:
        _, row = read_input(name, roots=roots)
        total += row['bytes']
        require(total <= 134217728, 'one complete dependency set exceeds 128MiB')
        result[name] = row
    return result


def remember_input(watch, row):
    old = watch.get(row['path'])
    require(old is None or old == row, 'one input changed during this fixed build')
    watch[row['path']] = row


def compile_object(report, root, name, source, flags, roots, watch, cpp=False, require_gtest=False):
    require(re.fullmatch('[a-z][a-z0-9_-]*', name) is not None,
            'fixed object name grammar')
    output = root/'objects'/(name+'.o')
    before_dep = root/'objects'/(name+'.preflight.d')
    after_dep = root/'objects'/(name+'.actual.d')
    common = [CFG['compiler']['path'], *flags]
    command(report,root,common+['-M','-MF',str(before_dep),'-MT',name,str(source)],timeout=45)
    before = dependency_rows(before_dep,name,roots,cpp)
    require(str(source) in before, 'actual translation unit absent from dependencies')
    if require_gtest:
        require(str(Path(CFG['aosp'])/'external/googletest/googletest/include/gtest/gtest.h') in before,
                'original GTest header absent')
    for row in before.values():
        remember_input(watch,row)
    report['dependency_before'][name] = before
    command(report,root,common+['-MD','-MF',str(after_dep),'-MT',name,
                               '-c',str(source),'-o',str(output)],timeout=120)
    after = dependency_rows(after_dep,name,roots,cpp)
    report['dependency_after'][name] = after
    require(before == after, 'actual compiler dependency set/bytes changed')
    row, elf = elf64(output,1)
    remember_input(watch,row)
    report['objects'].append({'name':name,'artifact':row,'machine':183,'type':'REL',
                              'dependency_count':len(after),'executed':False})
    return output, elf


def elf64(path, expected_type):
    data, row = read_input(path,33554432,roots=[Path(CFG['root'])])
    require(len(data)>=64 and data[:7] == b'\x7fELF\x02\x01\x01',
            'expected ELF64 little endian')
    header = struct.unpack_from('<HHIQQQIHHHHHH',data,16)
    kind,machine,version = header[:3]
    phoff,shoff = header[4],header[5]
    phentsize,phnum,shentsize,shnum,shstrndx = header[8:13]
    require(kind == expected_type and machine == 183 and version == 1 and
            shentsize == 64 and 0 < shnum <= 8192 and 0 <= shstrndx < shnum and
            shoff >= 64 and shoff+shnum*64 <= len(data), 'ARM64 ELF header/sections differ')
    sections = [struct.unpack_from('<IIQQQQIIQQ',data,shoff+i*64) for i in range(shnum)]
    for section in sections:
        if section[1] != 8:
            require(section[4] <= len(data) and section[5] <= len(data)-section[4],
                    'ELF section outside complete file')
    tables = [s for s in sections if s[1] in (2,11)]
    require(len([s for s in tables if s[1] == 2]) == 1 and
            len([s for s in tables if s[1] == 11]) == (1 if kind == 3 else 0),
            'complete ELF symbol tables required')
    def string_at(raw,index):
        require(0 <= index < len(raw),'ELF string offset bound')
        end = raw.find(b'\0',index)
        require(index <= end <= index+8192,'ELF string terminator bound')
        return raw[index:end].decode('utf-8','strict')
    symbols, dynamic_symbols = [], []
    for table in tables:
        require(table[9] == 24 and table[5]%24 == 0 and table[5]//24 <= 262144 and
                0 <= table[6] < shnum, 'ELF symbol table record/link bound')
        strings = sections[table[6]]
        require(strings[1] == 3, 'ELF symbol strings require SHT_STRTAB')
        strdata = data[strings[4]:strings[4]+strings[5]]
        target = dynamic_symbols if table[1] == 11 else symbols
        for off in range(table[4],table[4]+table[5],24):
            tick()
            name,info,other,index,value,size = struct.unpack_from('<IBBHQQ',data,off)
            target.append({'name':string_at(strdata,name),'type':info&15,'binding':info>>4,
                           'visibility':other&3,'defined':index!=0,'size':size})
    notes = {'android_sdk_ident':[],'GNU_build_id':[]}
    for section in sections:
        if section[1] != 7:
            continue
        raw = data[section[4]:section[4]+section[5]]
        offset,count = 0,0
        while offset < len(raw):
            require(offset+12 <= len(raw) and count < 4096,'ELF note header bound')
            namesz,descsz,typ = struct.unpack_from('<III',raw,offset)
            offset += 12
            require(namesz <= len(raw)-offset,'ELF note owner bound')
            owner = raw[offset:offset+namesz]
            offset = (offset+namesz+3)&~3
            require(offset <= len(raw) and descsz <= len(raw)-offset,'ELF note descriptor bound')
            desc = raw[offset:offset+descsz]
            offset = (offset+descsz+3)&~3
            require(offset <= len(raw),'ELF note padding bound')
            if owner == b'Android\0' and typ == 1:
                require(descsz >= 4,'Android CRT brand note length')
                notes['android_sdk_ident'].append(struct.unpack_from('<I',desc)[0])
            elif owner == b'GNU\0' and typ == 3:
                require(0 < descsz <= 64,'GNU build ID bound')
                notes['GNU_build_id'].append(desc.hex())
            count += 1
    result = {'symbols':symbols,'dynamic_symbols':dynamic_symbols,
              'needed':[],'soname':None,'runtime_path':[],'text_relocation':False,'notes':notes,
              'GNU_EH_FRAME_program_headers':0}
    if kind == 3:
        require(phentsize == 56 and 0 < phnum <= 128 and
                phoff >= 64 and phoff+phnum*56 <= len(data),'ELF program header bound')
        phdrs = [struct.unpack_from('<IIQQQQQQ',data,phoff+i*56) for i in range(phnum)]
        require(all(p[2] <= len(data) and p[5] <= len(data)-p[2] and p[5] <= p[6]
                    for p in phdrs),'ELF program segment file/memory bound')
        require(any(p[0] == 1 for p in phdrs) and
                not any(p[0] == 1 and p[1]&3 == 3 for p in phdrs) and
                not any(p[0] == 0x6474e551 and p[1]&1 for p in phdrs),
                'ELF W+X load or executable stack')
        result['GNU_EH_FRAME_program_headers']=sum(p[0]==0x6474e550 for p in phdrs)
        dynamics = [s for s in sections if s[1] == 6]
        require(len(dynamics) == 1,'one dynamic section required')
        dynamic = dynamics[0]
        require(dynamic[9] == 16 and dynamic[5]%16 == 0 and
                0 <= dynamic[6] < shnum,'dynamic table bound')
        strings = sections[dynamic[6]]
        require(strings[1] == 3,'dynamic strings required')
        strdata = data[strings[4]:strings[4]+strings[5]]
        terminated = False
        for off in range(dynamic[4],dynamic[4]+dynamic[5],16):
            tag,value = struct.unpack_from('<qQ',data,off)
            if tag == 0:
                terminated = True
                break
            if tag == 1:
                result['needed'].append(string_at(strdata,value))
            elif tag == 14:
                require(result['soname'] is None,'multiple SONAME tags')
                result['soname'] = string_at(strdata,value)
            elif tag in (15,29):
                result['runtime_path'].append(string_at(strdata,value))
            elif tag == 22 or (tag == 30 and value&4):
                result['text_relocation'] = True
        require(terminated and not result['runtime_path'] and not result['text_relocation'] and
                len(result['needed']) == len(set(result['needed'])),
                'dynamic terminator, paths or relocations differ')
    return row,result


def source_module(name, body):
    require(name not in sys.modules, 'fixed source module unexpectedly preloaded')
    module = types.ModuleType(name)
    module.__file__ = '<bound-original-'+name+'>'
    sys.modules[name] = module
    try:
        exec(compile(body,module.__file__,'exec'),module.__dict__)
        return module
    except BaseException:
        if sys.modules.get(name) is module:
            del sys.modules[name]
        raise


def generate_sdk_interfaces(root, report, sdk_bodies, api_map):
    """Use the exact original Soong parser and generator; no replacement SDK implementation."""
    parser = None
    generator = None
    primary = None
    outputs = {}
    try:
        parser = source_module('symbolfile',sdk_bodies['symbolfile_source'])
        generator = source_module('owned_marriott_ndkstubgen',sdk_bodies['ndkstubgen_source'])
        api = parser.decode_api_level('current',api_map)
        require(api == 10000, 'original current API decoding changed')
        for stem in ('libc','libdl','libm','liblog','libz'):
            tick()
            filt = parser.Filter(parser.Arch('arm64'),api,False,False,False,True)
            with io.StringIO(sdk_bodies[stem+'_ndk_map'].decode('utf-8','strict')) as input_map:
                versions = parser.SymbolFileParser(input_map,api_map,filt).parse()
            with io.StringIO() as source, io.StringIO() as version, io.StringIO() as names:
                generator.Generator(source,version,names,filt).write(versions)
                generated = {'c':source.getvalue().encode(),'map':version.getvalue().encode(),
                             'symbols':names.getvalue().encode()}
            require(all(0 < len(v) <= 1048576 for v in generated.values()),
                    'original SDK generated output bound')
            directory = root/'sdk-link-interfaces'/stem
            directory.mkdir(mode=0o700)
            members = {}
            for ext,body in generated.items():
                path = directory/('stub.'+ext)
                create(path,body)
                _,row = read_input(path,1048576,{'bytes':len(body),'sha256':digest(body)},roots=[root])
                members[ext] = row
            outputs[stem] = members
        report['sdk_interface_generation'] = {
            'original_parser_sha256':digest(sdk_bodies['symbolfile_source']),
            'original_generator_sha256':digest(sdk_bodies['ndkstubgen_source']),
            'arch':'arm64','api_argument':'current','decoded_api':api,
            'apex':False,'llndk':False,'systemapi':False,'ndk':True,
            'outputs':outputs,'packaged_or_executed':False,'runtime_implementation':False}
    except BaseException as exc:
        primary = exc
    finally:
        for name,module in (('owned_marriott_ndkstubgen',generator),('symbolfile',parser)):
            if module is not None:
                if sys.modules.get(name) is module:
                    del sys.modules[name]
                else:
                    error = RuntimeError('fixed source module ownership changed: '+name)
                    if primary is None:
                        primary = error
                    else:
                        primary.add_note(repr(error))
    if primary is not None:
        raise primary
    return outputs


def require_dyn_function(elf, name):
    matches = [s for s in elf['dynamic_symbols'] if s['name'] == name and
               s['type'] == 2 and s['defined'] and s['size'] > 0 and
               s['binding'] in (1,2) and s['visibility'] == 0]
    require(len(matches) == 1,'required real DSO export missing: '+name)
    return matches[0]


def qualify_test_registry(elf):
    registry = CFG['registry']['registry']
    require(len(registry) == len(set(registry)) == 23 and
            CFG['registry']['expected_selected_count'] == 12 and
            len(CFG['registry']['expected_selected']) == 12,
            'fixed real test registry size')
    found = {}
    for item in registry:
        suite,test = item.split('.')
        cls = suite+'_'+test+'_Test'
        name = '_ZN'+('12_GLOBAL__N_1' if suite == 'ProcSelfMaps' else '')+str(len(cls))+cls+'8TestBodyEv'
        matches = [s for s in elf['symbols'] if s['name'] == name and s['type'] == 2 and
                   s['defined'] and s['size'] > 0]
        require(len(matches) == 1, 'linked real test body missing: '+item)
        found[item] = matches[0]
    actual = [s['name'] for s in elf['symbols'] if s['type'] == 2 and
              s['defined'] and s['size'] > 0 and s['name'].endswith('_Test8TestBodyEv')]
    require(len(actual) == 23 and set(actual) == {s['name'] for s in found.values()},
            'unexpected or duplicate linked test body')
    return {'expected_count':23,'linked_TestBody_symbols':found,
            'expected_focus_count':12,'test_execution':False,
            'registration_runtime_observed':False,
            'runtime_must_supply_nonempty_original_VerifyTestList':True}

def build_java_apk(report, root, objects, watch):
    tool = {k:v['declared_path'] for k,v in CFG['java_tools'].items()}
    sdk = report['_apk_inputs']
    source_root = root/'source'
    classes,dex,res,private = (root/n for n in ('classes','dex','res','private-signing'))
    for path in (classes,dex,res,private):
        path.mkdir(mode=0o700)
    manifest = source_root/'AndroidManifest.xml'
    raw_manifest,_ = read_input(manifest,65536,roots=[root])
    document = ET.fromstring(raw_manifest)
    attr = '{http://schemas.android.com/apk/res/android}'
    require(document.tag == 'manifest' and document.attrib == {'package':'com.example.ndk_tests'},
            'original NDK manifest package differs')
    permissions = [x.attrib for x in document if x.tag == 'uses-permission']
    require(permissions == [{attr+'name':'android.permission.WRITE_EXTERNAL_STORAGE'},
                            {attr+'name':'android.permission.INTERNET'}],
            'original NDK permissions differ')
    sdks = document.findall('uses-sdk')
    require(len(sdks) == 1 and sdks[0].attrib ==
            {attr+'minSdkVersion':'14',attr+'targetSdkVersion':'23'},
            'original NDK min14/target23 contract changed')
    app = document.findall('application')
    require(len(app)==1 and app[0].attrib == {attr+'label':'NDK Tests',attr+'debuggable':'true'} and
            [x.tag for x in app[0]] == ['uses-library','activity'] and
            app[0][0].attrib == {attr+'name':'android.test.runner'} and
            app[0][1].attrib == {attr+'name':'.NdkTestsActivity'},
            'original NDK application differs')
    instrumentation = document.findall('instrumentation')
    require(len(instrumentation)==1 and instrumentation[0].attrib == {
        attr+'name':'android.test.InstrumentationTestRunner',
        attr+'targetPackage':'com.example.ndk_tests',attr+'label':'Tests for com.example.ndk_tests'},
        'original NDK instrumentation differs')
    classpath = [sdk[n]['path'] for n in
                 ('android_test_runner31','android_test_base31','android_test_mock31')]
    java_sources = [source_root/'java/com/example/ndk_tests'/n
                    for n in ('NdkTests.java','NdkTestsActivity.java')]
    command(report,root,[tool['javac'],'-J-XX:ActiveProcessorCount=1','-J-XX:+UseSerialGC',
        '-J-Xmx256m','-proc:none','-Xmaxerrs','20','-Xmaxwarns','20','-source','8','-target','8',
        '-bootclasspath',tool['android_jar'],'-classpath',':'.join(classpath),
        '-d',str(classes),*[str(p) for p in java_sources]],timeout=60)
    # Enumerate only our fresh, compiler-created output; never source or device directories.
    compiled = sorted(classes.rglob('*.class'))
    require(len(compiled)==2 and {p.relative_to(classes).as_posix() for p in compiled} ==
            {'com/example/ndk_tests/NdkTests.class','com/example/ndk_tests/NdkTestsActivity.class'},
            'exact two original Java classes required')
    for path in compiled:
        body,row=read_input(path,1048576,roots=[root])
        require(body[:4] == b'\xca\xfe\xba\xbe','actual Java class encoding')
        remember_input(watch,row)
    java = [tool['java'],'-XX:ActiveProcessorCount=1','-XX:+UseSerialGC','-Xmx256m']
    args = java+['-cp',tool['r8'],'com.android.tools.r8.D8','--lib',tool['android_jar']]
    for path in classpath:
        args += ['--classpath',path]
    args += ['--min-api','14','--output',str(dex),*[str(p) for p in compiled]]
    command(report,root,args,timeout=60)
    require(sorted(p.name for p in dex.iterdir()) == ['classes.dex'],'exact one DEX output')
    dex_body,dex_row = read_input(dex/'classes.dex',4194304,roots=[root])
    require(dex_body.startswith(b'dex\n'),'actual DEX magic')
    remember_input(watch,dex_row)
    unsigned,aligned,final = (root/n for n in ('unsigned.apk','aligned.apk','ndk-tests.apk'))
    command(report,root,[tool['aapt'],'package','-f','-M',str(manifest),'-S',str(res),
                        '-I',tool['android_jar'],'-F',str(unsigned)],timeout=45)
    with zipfile.ZipFile(unsigned,'a',compression=zipfile.ZIP_DEFLATED) as archive:
        names = archive.namelist()
        require(len(names) == len(set(names)) and
                set(names) <= {'AndroidManifest.xml','resources.arsc'} and
                'AndroidManifest.xml' in names,'original resource APK member set')
        archive.writestr('classes.dex',dex_body)
        for name in ('libberberis_ndk_tests.so','libberberis_ndk_tests_shared_lib.so'):
            body,row = read_input(objects[name],33554432,roots=[root])
            remember_input(watch,row)
            archive.writestr('lib/arm64-v8a/'+name,body)
    # The original APK keeps native libraries compressed and the target23 extraction behavior.
    command(report,root,[tool['zipalign'],'-f','4',str(unsigned),str(aligned)],timeout=45)
    password,store = private/'password.txt',private/'owned.p12'
    create(password,(secrets.token_hex(32)+'\n').encode(),mode=0o600)
    command(report,root,java+['-m','java.base/sun.security.tools.keytool.Main',
        '-genkeypair','-noprompt','-storetype','PKCS12','-keystore',str(store),
        '-storepass:file',str(password),'-alias','marriott-ndk-tests','-keyalg','RSA',
        '-keysize','3072','-validity','3650',
        '-dname','CN=Pocket4 Owned NDK Tests,O=Owned Test,C=US'],timeout=60)
    command(report,root,[tool['apksigner'],'sign','--ks',str(store),'--ks-pass','file:'+str(password),
        '--ks-key-alias','marriott-ndk-tests','--min-sdk-version','14',
        '--v1-signing-enabled','true','--v2-signing-enabled','true',
        '--v3-signing-enabled','true','--out',str(final),str(aligned)],timeout=60)
    signature = command(report,root,[tool['apksigner'],'verify','--verbose','--print-certs',
                                    '--min-sdk-version','14',str(final)],timeout=45)
    certificate = re.findall(r'^Signer #1 certificate SHA-256 digest: ([0-9a-f]{64})\r?$',
                             signature['stdout'],re.M)
    require(len(certificate)==1 and 'Number of signers: 1' in signature['stdout'] and
            re.search(r'^Verified using v1 scheme .*: true\r?$',signature['stdout'],re.M) is not None and
            re.search(r'^Verified using v2 scheme .*: true\r?$',signature['stdout'],re.M) is not None,
            'actual single signer and original minimum-SDK signature schemes required')
    command(report,root,[tool['zipalign'],'-c','4',str(final)],timeout=30)
    badging = command(report,root,[tool['aapt'],'dump','badging',str(final)],timeout=30)['stdout']
    xml = command(report,root,[tool['aapt'],'dump','xmltree',str(final),'AndroidManifest.xml'],
                  timeout=30)['stdout']
    require("package: name='com.example.ndk_tests'" in badging and "sdkVersion:'14'" in badging and
            "targetSdkVersion:'23'" in badging and 'application-debuggable' in badging and
            len(re.findall(r"^native-code: ([^\r\n]*)$",badging,re.M)) == 1 and
            shlex.split(re.findall(r"^native-code: ([^\r\n]*)$",badging,re.M)[0]) == ['arm64-v8a'],
            'actual APK package, SDK or ARM64 architecture differs')
    require(len(re.findall(r'E: instrumentation(?:\s|$)',xml))==1 and
            len(re.findall(r'E: activity(?:\s|$)',xml))==1 and
            'android.test.InstrumentationTestRunner' in xml and
            'android.test.runner' in xml and
            re.search(r'A: android:targetPackage\([^\n]*="com\.example\.ndk_tests"',xml) is not None and
            not any('E: '+x+' ' in xml for x in ('activity-alias','service','receiver','provider')),
            'actual original instrumentation/activity manifest differs')
    apk_body,apk_row=read_input(final,33554432,roots=[root])
    with zipfile.ZipFile(io.BytesIO(apk_body),'r') as archive:
        names=archive.namelist()
        require(len(names)==len(set(names)),'duplicate APK member')
        payload={'AndroidManifest.xml','classes.dex','lib/arm64-v8a/libberberis_ndk_tests.so',
                 'lib/arm64-v8a/libberberis_ndk_tests_shared_lib.so'}
        require(payload <= set(names),'required real APK members absent')
        signatures=[n for n in names if n.startswith('META-INF/')]
        require('META-INF/MANIFEST.MF' in signatures and len(signatures)==3 and
                len([n for n in signatures if re.fullmatch(r'META-INF/[A-Z0-9_-]{1,8}[.]SF',n)])==1 and
                len([n for n in signatures if re.fullmatch(r'META-INF/[A-Z0-9_-]{1,8}[.]RSA',n)])==1 and
                set(names) <= payload|{'resources.arsc'}|set(signatures),
                'APK has extra payload or nonstandard signature entries')
        sf=[n[:-3] for n in signatures if n.endswith('.SF')]
        rsa=[n[:-4] for n in signatures if n.endswith('.RSA')]
        require(sf==rsa,'v1 signer files do not share the same stem')
        require(archive.getinfo('classes.dex').file_size == len(dex_body) and
                archive.read('classes.dex') == dex_body,'packaged DEX bytes differ')
        native=[]
        for name in ('libberberis_ndk_tests.so','libberberis_ndk_tests_shared_lib.so'):
            member=archive.getinfo('lib/arm64-v8a/'+name)
            require(member.file_size <= 33554432 and member.compress_type == zipfile.ZIP_DEFLATED,
                    'native APK member size/compression differs')
            body,row=read_input(objects[name],33554432,roots=[root])
            require(archive.read(member) == body,'packaged native implementation differs')
            native.append({'member':member.filename,'bytes':len(body),'sha256':digest(body)})
    _,final_again=read_input(final,33554432,apk_row,roots=[root])
    require(final_again == apk_row,'final complete APK tuple changed')
    remember_input(watch,apk_row)
    report['APK']=apk_row
    report['APK_contract']={'package':'com.example.ndk_tests','min_sdk':14,'target_sdk':23,
        'instrumentation':'android.test.InstrumentationTestRunner',
        'java_classes':2,'native_members':native,'SDK_interfaces_packaged':False,
        'runtime_executed':False,'signature_certificate_sha256':certificate[0],
        'private_signing_material_body_exported':False,
        'private_signing_paths':['private-signing/password.txt','private-signing/owned.p12'],
        'runtime_must_use_instrumentation_with_nonempty_23_test_list':True,
        'Activity_empty_test_list_route_admitted':False}

def main():
    global CHILD_REAPER
    require(type(CFG) is dict and CFG.get('script_only_pending_actuals') is False,
            'SOURCE_ONLY: exact successful product configuration binding is required before build')
    report={'schema':1,'kind':CFG['kind'],'success':False,'errors':[],'commands':[],
        'Android_actions':0,'Main_actions':0,'installed':False,'ARM64_objects_executed':False,
        'ART_runtime_qualified':False,'feature_default_enabled':False,
        'commercial_App_reproduction_asserted':False,'all_inputs_unchanged':False,
        'root':CFG['root'],'source_before':{},'source_after':{},'bound_inputs':{},
        'dependency_before':{},'dependency_after':{},'objects':[],'linked_libraries':[]}
    root,aosp=Path(CFG['root']),Path(CFG['aosp'])
    created=False
    completed=False
    watch={}
    guard=base64.b64decode(CFG['resource_guard']['base64'],validate=True)
    require(digest(guard)==CFG['resource_guard']['sha256'],'original resource guard differs')
    resource_ns={'__name__':'fixed_apk_resource_guard'}
    exec(compile(guard,'<original-C16-resource-guard>','exec'),resource_ns)
    resources=resource_ns['OwnJobResources'](1073741824)
    report['resource_health']=resources.record
    try:
        require(os.getuid()==os.geteuid()==os.getgid()==os.getegid()==1000,
                'ordinary operator UID/GID1000 required')
        require(CFG['kind']=='p4-marriott-real-arm64-ndk-apk-build03' and
                root==Path('/home/alex/work/pocket4-marriott-real-arm64-ndk-apk-03-20261106') and
                aosp==Path('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source'),
                'fixed new APK build/source root differs')
        require(CFG['java_home']==str(aosp/'prebuilts/jdk/jdk21/linux-x86') and
                CFG['controller_work_seconds']==600,'fixed tool environment/work budget differs')
        original22,actual_config,sdk_inputs,sdk_specs=qualified_sdk_bindings()
        report['input_receipt_lineage']={
            'original_SDK22':{'job':'1a1b19b46a3-fc05-79d7','exit_code':1,
                'collection_complete':False,'accepted_complete_individual_rows':21,
                'first_error':original22['first_error'],
                'sha256':CFG['actual_sdk22_failed_original']['sha256']},
            'new_configuration':{'job':CFG['actual_sdk_configuration']['terminal']['job_id'],
                'exit_code':0,'collection_complete':True,
                'sha256':CFG['actual_sdk_configuration']['sha256']},
            'old_APK13_reader02':'ADMISSION_UNKNOWN_NOT_RETRIED_OR_BORROWED'}
        join=actual_config.get('sdk_configuration_join',{})
        require(join.get('qualified_for_fixed_build_input_binding') is True and
                join.get('generated_api_map_matches_original_algorithm') is True and
                join.get('NDK_current_interface_api_from_original_generator')==10000 and
                join.get('compiler_current_target_preserved')=='aarch64-linux-android10000' and
                join.get('SDK_values_modified') is False,
                'actual original SDK configuration join missing')
        sdk_version=join.get('Platform_sdk_version_observed')
        require(type(sdk_version) is int and 21<=sdk_version<=10000,'observed CRT SDK number required')
        resources.begin()
        for parent in (root.parent,*root.parent.parents):
            require(stat.S_ISDIR(parent.lstat().st_mode),'fixed work parent symlink/non-directory')
        require(not root.exists() and not root.is_symlink(),'new APK root already exists')
        os.umask(0o077)
        root.mkdir(mode=0o700)
        created=True
        root_identity=stamp(root.stat(follow_symlinks=False))
        for name in ('source','tmp','objects','sdk-link-interfaces','libraries'):
            (root/name).mkdir(mode=0o700)
        for relative,spec in CFG['sources'].items():
            path=Path(relative)
            require(not path.is_absolute() and relative==path.as_posix() and
                    len(path.parts)<=8 and all(re.fullmatch('[A-Za-z0-9_.-]+',x) is not None and
                        x not in ('.','..') for x in path.parts),'inline source path grammar')
            body=base64.b64decode(spec['base64'],validate=True)
            require(len(body)==spec['bytes'] and digest(body)==spec['sha256'],
                    'inline source whole pin differs')
            target=root/'source'/relative
            target.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
            create(target,body)
            _,row=read_input(target,1048576,spec,roots=[root])
            report['source_before'][relative]=row
            remember_input(watch,row)
        report['original_default_zero_retained']=False
        raw_owner,_=read_input(root/'source/raw_owner_reference.h',65536,roots=[root])
        require(b'#define BERBERIS_PROCMAPS_RAW_METADATA_OWNER 0' in raw_owner,
                'original translator feature default changed')
        report['original_default_zero_retained']=True
        manifest_body,manifest_row=read_input(CFG['candidate_manifest']['path'],524288,
                                               CFG['candidate_manifest'])
        manifest=json.loads(manifest_body)
        require(manifest.get('schema')==1 and len(manifest['files'])==949,'exact candidate07 manifest shape')
        for path,sha in CFG['candidate_rows'].items():
            require(manifest['files'].get(path)==sha,'candidate07 source reference differs')
        report['candidate07_manifest']=manifest_row
        remember_input(watch,manifest_row)
        _,compiler_row=read_input(CFG['compiler']['path'],8388608,CFG['compiler'],roots=[aosp])
        report['compiler_before']=compiler_row
        remember_input(watch,compiler_row)
        require(compiler_row==dict(CFG['compiler']['actual_C20_tuple'],nlink=1),
                'compiler complete actual C20 tuple differs')
        _,linker_row=read_input(CFG['linker']['path'],83886080,CFG['linker'],roots=[aosp])
        report['linker_before']=linker_row
        remember_input(watch,linker_row)
        require(linker_row==dict(CFG['linker'],nlink=1),
                'linker complete actual C20 tuple differs')
        report['java_tools_before']={}
        for name,spec in CFG['java_tools'].items():
            _,row=read_input(spec['declared_path'],33554432,spec,roots=[Path(spec['path'])])
            require(row['resolved_path']==spec['path'],'fixed original Java tool path mapping differs')
            if name not in ('android_jar','r8'):
                require(row['mode']&0o111,'bound Java/APK tool not executable')
            report['java_tools_before'][name]=row
            remember_input(watch,row)
        apk_inputs=first_observe_apk13(report)
        sdk_bodies={}
        for spec in CFG['apk_input_specifications']:
            observe_bound_input(spec,apk_inputs[spec['role']],watch,report,'APK13:'+spec['role'])
        for spec in sdk_specs:
            sdk_bodies[spec['role']]=observe_bound_input(spec,sdk_inputs[spec['role']],
                                                        watch,report,'SDK22:'+spec['role'])
        variables=json.loads(sdk_bodies['existing_soong_variables'])
        api_map=json.loads(sdk_bodies['existing_generated_api_map'])
        require(variables.get('Platform_sdk_version')==sdk_version and
                api_map==sdk_inputs['existing_generated_api_map']['format_facts']['api_levels'],
                'current full configuration bytes differ from selected actual public values')
        # The full soong.variables body is never serialized into this report.
        report['sdk_configuration']={'Platform_sdk_version':sdk_version,
            'source_sha256':sdk_inputs['existing_soong_variables']['sha256'],
            'api_map_sha256':sdk_inputs['existing_generated_api_map']['sha256'],
            'target':'aarch64-linux-android10000','SDK_values_modified':False,
            'runtime_platform_library_qualification':False}
        for relative,spec in CFG['gtest_sources'].items():
            path=aosp/'external/googletest/googletest'/relative
            _,row=read_input(path,1048576,spec,roots=[path])
            remember_input(watch,row)
        report['original_module_target_rules']={}
        for relative,spec in CFG['module_target_rule_sources'].items():
            path=aosp/relative
            _,row=read_input(path,65536,spec,roots=[path])
            remember_input(watch,row)
            report['original_module_target_rules'][relative]=row
        report['native_module_targets']={
            'original_APK_libraries':{'declared':'current','normalized':10000},
            'libgtest_ndk_c++':{'declared':'9','normalized':21},
            'cpufeatures':{'declared':'minimum','normalized':21},
            'architecture_floor_source':'android.FirstLp64Version',
            'manifest_min_sdk':14,'manifest_target_sdk':23,
            'CRT_brand':sdk_version,'SDK_values_modified':False}
        CHILD_REAPER=OwnChildReaper()
        report['child_tree_guard']=CHILD_REAPER.record
        CHILD_REAPER.begin()
        generated=generate_sdk_interfaces(root,report,sdk_bodies,api_map)
        for members in generated.values():
            for row in members.values():
                remember_input(watch,row)
        ndk_config=Path(sdk_inputs['arm64_ndk_config_anchor']['path'])
        clang=aosp/'prebuilts/clang/host/linux-x86/clang-r584948b'
        gtest=aosp/'external/googletest/googletest'
        cpu=Path(apk_inputs['ndk_cpufeatures_source']['path'])
        roots=[root,ndk_config,clang/'include/c++/v1',clang/'lib/clang/22/include',
               aosp/'bionic/libc/include',aosp/'bionic/libc/kernel',
               gtest/'include',gtest/'src',aosp/'libnativehelper/include_jni',
               *[Path(s['path']) for s in sdk_specs],
               Path(apk_inputs['ndk_cpufeatures_source']['path']),
               Path(apk_inputs['ndk_cpufeatures_header']['path'])]
        bionic_includes=[
            '-isystem',str(aosp/'bionic/libc/include'),
            '-isystem',str(aosp/'bionic/libc/kernel/uapi/asm-arm64'),
            '-isystem',str(aosp/'bionic/libc/kernel/uapi'),
            '-isystem',str(aosp/'bionic/libc/kernel/android/scsi'),
            '-isystem',str(aosp/'bionic/libc/kernel/android/uapi')]
        base=['-target','aarch64-linux-android10000','-nostdlibinc',
              '-DANDROID','-D__BIONIC_NO_PAGE_SIZE_MACRO','-DNDEBUG','-D_FILE_OFFSET_BITS=64',
              '-D_FORTIFY_SOURCE=3','-O2','-ferror-limit=20','-fPIC',
              '-ffunction-sections','-fdata-sections']
        cpp=base+['-x','c++','-std=gnu++17','-nostdinc++','-Wall','-Wextra','-Werror',
                  '-Wno-deprecated-declarations','-fexceptions','-fstack-protector-strong',
                  '-I',str(root/'source'),'-isystem',str(ndk_config.parent),
                  '-isystem',str(clang/'include/c++/v1'),'-I',str(gtest/'include'),
                  '-I',str(gtest),'-I',str(aosp/'libnativehelper/include_jni'),
                  *bionic_includes]
        cflags=base+['-x','c','-std=gnu11','-Wall','-Werror',*bionic_includes]
        asmflags=base+['-x','assembler-with-cpp','-Wall','-Werror',
                       '-I',str(aosp/'bionic/libc'),*bionic_includes]
        lld=[CFG['linker']['path'],'--error-limit=20']
        # Real Bionic source objects, including its observed platform brand.
        begin_path,begin_elf=compile_object(report,root,'crtbegin-so',
            Path(sdk_inputs['bionic_crtbegin_so_c']['path']),cflags+['-Wno-gcc-compat'],
            roots,watch)
        brand_path,brand_elf=compile_object(report,root,'crtbrand',
            Path(sdk_inputs['bionic_crtbrand_S']['path']),
            asmflags+['-DPLATFORM_SDK_VERSION='+str(sdk_version)],roots,watch)
        require(brand_elf['notes']['android_sdk_ident']==[sdk_version],
                'compiled CRT brand does not contain the actual SDK value')
        end_path,end_elf=compile_object(report,root,'crtend-so',
            Path(sdk_inputs['bionic_crtend_so_S']['path']),asmflags,roots,watch)
        combined_begin=root/'objects/crtbegin-combined.o'
        command(report,root,lld+['-m','aarch64elf','-r',str(begin_path),str(brand_path),
                                 '-o',str(combined_begin)],timeout=45)
        combined_row,combined_elf=elf64(combined_begin,1)
        require(combined_elf['notes']['android_sdk_ident']==[sdk_version],'merged real CRT brand differs')
        remember_input(watch,combined_row)
        report['real_CRT']={'begin':combined_row,'end_path':str(end_path),
                           'brand_sdk':sdk_version,'legacy_workaround':False}
        interfaces={}
        original_stub_flags=['-Wno-incompatible-library-redeclaration','-Wno-incomplete-setjmp-declaration',
            '-Wno-builtin-requires-header','-Wno-invalid-noreturn','-Wall','-Werror','-fno-unwind-tables',
            '-fno-builtin']
        for stem,members in generated.items():
            flags=base+['-x','c','-std=gnu11',*original_stub_flags]
            obj,_=compile_object(report,root,'sdk-'+stem,Path(members['c']['path']),
                                  flags,roots,watch)
            interface=root/'sdk-link-interfaces'/stem/(stem+'.so')
            command(report,root,lld+['-m','aarch64elf','-shared','--no-undefined',
                '--build-id=sha1','-z','noexecstack','-soname',stem+'.so',
                '--version-script='+members['map']['path'],str(obj),'-o',str(interface)],timeout=45)
            row,elf=elf64(interface,3)
            require(elf['soname']==stem+'.so' and elf['needed']==[],
                    'SDK interface acquired a runtime dependency')
            symbol_body,_=read_input(members['symbols']['path'],1048576,roots=[root])
            lines=symbol_body.decode('utf-8','strict').splitlines()
            require(lines and lines[0]=='[abi_symbol_list]' and len(lines)>1 and
                    len(lines[1:])==len(set(lines[1:])),'official SDK symbol list shape')
            for name in lines[1:]:
                require(any(s['name']==name and s['defined'] and s['binding'] in (1,2) and
                            s['visibility']==0 for s in elf['dynamic_symbols']),
                        'official SDK link symbol omitted: '+name)
            remember_input(watch,row)
            interfaces[stem]=interface
            report['linked_libraries'].append({'artifact':row,'soname':elf['soname'],
                'needed':elf['needed'],'SDK_link_interface_only':True,
                'packaged_or_executed':False,'official_symbol_count':len(lines)-1})
        # Original libgtest sdk9 and cpufeatures minimum both clamp to
        # the original Soong ARM64 FirstLp64Version=21; APK current stays10000.
        gtest_flags=list(cpp)
        cpu_flags=list(cflags)
        require(gtest_flags[:2]==cpu_flags[:2]==['-target','aarch64-linux-android10000'],
                'original current target flag position differs')
        gtest_flags[1]=cpu_flags[1]='aarch64-linux-android21'
        gtest_obj,_=compile_object(report,root,'gtest-all',gtest/'src/gtest-all.cc',
            gtest_flags+['-Wno-unused-private-field'],roots,watch,cpp=True,require_gtest=True)
        cpu_obj,_=compile_object(report,root,'cpu-features',cpu,
            cpu_flags+['-I',str(cpu.parent)],roots,watch)
        # The pinned original shared_lib.cc has no include directives. Here cpp
        # selects only the dependency __config_site expectation; the compiler
        # flags stay the same C++ flags. Require no configuration header for this
        # one header-free TU; all header-using C++ TUs still require the ARM64 pin.
        shared_obj,shared_elf=compile_object(report,root,'shared-lib',root/'source/shared_lib.cc',
                                            cpp,roots,watch,cpp=False)
        test_objects={}
        object_elf={}
        for name in ('proc_self_maps_test.cc','shared_library_test.cc','user_apk_test.cc',
                     'jni_test.cc','jni_test_main.cc'):
            flags=cpp+['-DTMPFILE_TEMPLATE="/data/data/com.example.ndk_tests/cache/ndk-tests-XXXXXX"']
            path,elf=compile_object(report,root,name.removesuffix('.cc').replace('_','-'),
                root/'source'/name,flags,roots,watch,cpp=True,require_gtest=True)
            test_objects[name]=path
            object_elf[name]=elf
        # The actual JNI TU must still call the actual original native runner.
        entry=object_elf['jni_test.cc']['symbols']
        runner=object_elf['jni_test_main.cc']['symbols']
        run_symbols=[s['name'] for s in runner if s['name'].startswith('_ZN8ndk_test11RunAllTestsE') and
                     s['type']==2 and s['defined'] and s['size']>0]
        require(len(run_symbols)==1 and any(s['name']==run_symbols[0] and not s['defined'] for s in entry),
                'compiled real JNI-to-RunAllTests reference/definition join differs')
        common_link=lld+['-m','aarch64elf','-shared','--no-undefined','--no-as-needed',
            '--build-id=sha1','--hash-style=both','--eh-frame-hdr','--exclude-libs=libunwind.a',
            '-z','noexecstack','-z','relro','-z','now',
            '-z','max-page-size=16384']
        shared_so=root/'libraries/libberberis_ndk_tests_shared_lib.so'
        standard=[str(interfaces[n]) for n in ('libc','libm','libdl')]
        static=[apk_inputs[n]['path'] for n in
                ('ndk_libcxx_static','ndk_libcxxabi','arm64_unwind','arm64_builtins')]
        command(report,root,common_link+['-soname',shared_so.name,str(combined_begin),str(shared_obj),
            '--start-group',*static,'--end-group',*standard,str(end_path),'-o',str(shared_so)],timeout=60)
        shared_row,shared_linked=elf64(shared_so,3)
        require(shared_linked['soname']==shared_so.name and
                sorted(shared_linked['needed'])==['libc.so','libdl.so','libm.so'] and
                shared_linked['notes']['android_sdk_ident']==[sdk_version] and
                len(shared_linked['notes']['GNU_build_id'])==1,
                'real shared helper dynamic/CRT identity differs')
        shared_function=require_dyn_function(shared_linked,'SharedFunction')
        remember_input(watch,shared_row)
        report['linked_libraries'].append({'artifact':shared_row,'soname':shared_linked['soname'],
            'needed':shared_linked['needed'],'notes':shared_linked['notes'],
            'SharedFunction':shared_function,'SDK_link_interface_only':False,'executed':False})
        main_so=root/'libraries/libberberis_ndk_tests.so'
        command(report,root,common_link+['-soname',main_so.name,str(combined_begin),
            *[str(p) for p in test_objects.values()],str(gtest_obj),str(cpu_obj),
            '--start-group',*static,'--end-group',str(shared_so),
            str(interfaces['liblog']),str(interfaces['libz']),*standard,
            str(end_path),'-o',str(main_so)],timeout=60)
        main_row,linked=elf64(main_so,3)
        require(linked['soname']==main_so.name and sorted(linked['needed'])==
            ['libberberis_ndk_tests_shared_lib.so','libc.so','libdl.so','liblog.so','libm.so','libz.so'] and
            linked['notes']['android_sdk_ident']==[sdk_version] and
            len(linked['notes']['GNU_build_id'])==1 and
            linked['GNU_EH_FRAME_program_headers']==1,
            'real test DSO dynamic/CRT identity differs')
        exports={n:require_dyn_function(linked,n) for n in (
            'JNI_OnLoad','Java_com_example_ndk_1tests_NdkTests_runTests',
            'Java_com_example_ndk_1tests_NdkTests_returnInt',
            'Java_com_example_ndk_1tests_NdkTests_returnFloat')}
        report['linked_test_registry']=qualify_test_registry(linked)
        report['compiled_JNI_symbol_join']={'entry':'Java_com_example_ndk_1tests_NdkTests_runTests',
            'RunAllTests':run_symbols[0],'linked':True,'executed':False}
        remember_input(watch,main_row)
        report['linked_libraries'].append({'artifact':main_row,'soname':linked['soname'],
            'needed':linked['needed'],'notes':linked['notes'],'JNI_exports':exports,
            'GNU_EH_FRAME_program_headers':linked['GNU_EH_FRAME_program_headers'],
            'SDK_link_interface_only':False,'executed':False})
        report['_apk_inputs']=apk_inputs
        build_java_apk(report,root,{main_so.name:main_so,shared_so.name:shared_so},watch)
        del report['_apk_inputs']
        require(len(report['commands'])==50 and len(report['objects'])==16 and
                len(report['linked_libraries'])==7,'fixed genuine APK build stage count differs')
        current_root=stamp(root.stat(follow_symlinks=False))
        require(current_root[:5]==root_identity[:5],'new owned build root identity changed')
        completed=True
    except Exception as error:
        report['errors'].append({'stage':'build','error':repr(error),'traceback':traceback.format_exc()})
    finally:
        report.pop('_apk_inputs',None)
        changed=[]
        for path,before in watch.items():
            try:
                _,after=read_input(path,max(8388608,before['bytes']+1),before)
                require(after==before,'final complete original/input/artifact tuple changed')
                report['source_after'][path]=after
            except Exception as error:
                changed.append({'path':path,'error':repr(error)})
        report['post_input_errors']=changed
        report['all_inputs_unchanged']=bool(watch) and not changed
        if CHILD_REAPER is not None:
            try:
                CHILD_REAPER.finish()
            except Exception as error:
                report['errors'].append({'stage':'child_tree_finish','error':repr(error)})
        try:
            resources.finish()
        except Exception as error:
            report['errors'].append({'stage':'resource_finish','error':repr(error)})
        try:
            resources.close()
        except Exception as error:
            report['errors'].append({'stage':'resource_close','error':repr(error)})
    report['all_children_reaped']=bool(CHILD_REAPER is not None and
        CHILD_REAPER.record['final_children_empty'] and CHILD_REAPER.record['restored'] and
        all((not x['child_started']) or (x['child_reaped'] and x['owned_tree_cleanup_complete'] and
            x['pidfd_closed'] and x['output_fds_closed']) for x in report['commands']))
    report['input_FD_event_count']=len(INPUT_FD_EVENTS)
    report['input_FD_close_failures']=[x for x in INPUT_FD_EVENTS if not x['closed']]
    report['all_tracked_input_FDs_closed']=bool(not report['input_FD_close_failures'] and
        report.get('apk13_first_observation',{}).get('all_tracked_owned_FDs_closed'))
    report['success']=bool(completed and not report['errors'] and report['all_inputs_unchanged'] and
        report['all_tracked_input_FDs_closed'] and report['all_children_reaped'] and
        resources.record['held_own_cgroup_gate_passed'])
    report['elapsed_seconds']=time.monotonic()-BUILD_STARTED
    encoded=(json.dumps(report,sort_keys=True,indent=2)+'\n').encode()
    require(len(encoded)<=67108864,'complete APK build receipt exceeds bound')
    if created:
        output=root/'build-result.json'
        create(output,encoded,mode=0o400)
        print(json.dumps({'success':report['success'],'path':str(output),'bytes':len(encoded),
                          'sha256':digest(encoded),
                          'first_error':report['errors'][0] if report['errors'] else None}))
    else:
        print(encoded.decode(),end='')
    return 0 if report['success'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
