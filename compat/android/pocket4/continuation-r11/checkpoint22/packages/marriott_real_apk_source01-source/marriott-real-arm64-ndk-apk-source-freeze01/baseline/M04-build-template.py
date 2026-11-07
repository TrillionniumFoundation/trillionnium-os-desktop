"""Compile fixed Marriott proc-maps ABI tests and existing JNI entry TUs; no Android execution."""
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
    resource.setrlimit(resource.RLIMIT_FSIZE, (262144, 262144))


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
        environment = {'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'LANG': 'C',
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
    require(len(INPUT_FD_EVENTS) < 16384, 'input FD event bound')
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

def dependency_rows(path, target, roots):
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
    require(actual_configs == [target_config],
            'dependency set does not contain only the fixed ARM64 NDK __config_site: '+repr(actual_configs))
    result = {}
    total = 0
    for name in names:
        _, row = read_input(name, roots=roots)
        total += row['bytes']
        require(total <= 134217728, 'one complete dependency set exceeds 128MiB')
        result[name] = row
    return result

def elf_functions(path, expected_machine):
    data, row = read_input(path, 262144, roots=[Path(CFG['root'])])
    require(len(data) >= 64 and data[:7] == b'\x7fELF\x02\x01\x01', 'not ELF64 little endian')
    header = struct.unpack_from('<HHIQQQIHHHHHH', data, 16)
    kind, machine, version = header[:3]
    shoff, shentsize, shnum, shstrndx = header[5], header[10], header[11], header[12]
    require(kind == 1 and machine == expected_machine and version == 1 and
            shentsize == 64 and 0 < shnum <= 4096 and 0 <= shstrndx < shnum and
            shoff >= 64 and shoff + shnum*64 <= len(data), 'ELF REL section bounds differ')
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, shoff+i*64) for i in range(shnum)]
    for section in sections:
        if section[1] != 8:
            require(section[4] <= len(data) and section[5] <= len(data)-section[4],
                    'ELF section outside bounded file')
    tables = [section for section in sections if section[1] == 2]
    require(len(tables) == 1, 'one complete symbol table required')
    table = tables[0]
    require(table[9] == 24 and table[5] % 24 == 0 and 0 <= table[6] < shnum,
            'symbol table record/link differs')
    strings = sections[table[6]]
    require(strings[1] == 3, 'symbol names not a string table')
    strdata = data[strings[4]:strings[4]+strings[5]]
    symbols = []
    for off in range(table[4], table[4]+table[5], 24):
        name, info, other, index, value, size = struct.unpack_from('<IBBHQQ', data, off)
        require(name < len(strdata), 'symbol name outside string table')
        end = strdata.find(b'\0', name)
        require(end >= name, 'unterminated symbol name')
        text = strdata[name:end].decode('utf-8', errors='strict')
        require(len(text) <= 8192, 'symbol name exceeds bound')
        symbols.append({'name':text, 'type':info & 15, 'binding':info >> 4,
                        'defined':index != 0, 'size':size})
    return row, symbols

def main():
    global CHILD_REAPER
    report = {'schema':1, 'kind':CFG['kind'], 'success':False, 'errors':[], 'commands':[],
              'source_only':True, 'Android_objects_executed':False, 'host_test_binary_executed':False,
              'Main_actions':0, 'Android_actions':0, 'installed':False,
              'full_engine_built':False, 'ART_built':False, 'APK_linked':False,
              'feature_default_enabled':False, 'commercial_App_reproduction_asserted':False,
              'first_observed_dependency_sets':True,
              'preprocess_is_dependency_discovery_not_runtime_qualification':True,
              'all_inputs_unchanged':False, 'all_children_reaped':False,
              'root':CFG['root'], 'objects':[], 'source_before':{}, 'dependency_before':{},
              'source_after':{}, 'dependency_after':{}}
    root = Path(CFG['root'])
    aosp = Path(CFG['aosp'])
    created = False
    completed = False
    watch = {}
    resource_ns = {'__name__':'fixed_compile_resource_guard'}
    guard = base64.b64decode(CFG['resource_guard']['base64'], validate=True)
    require(digest(guard) == CFG['resource_guard']['sha256'], 'resource guard pin differs')
    exec(compile(guard, '<original-C16-resource-guard>', 'exec'), resource_ns)
    resources = resource_ns['OwnJobResources'](1073741824)
    report['resource_health'] = resources.record
    try:
        require(os.getuid() == os.geteuid() == 1000, 'ordinary operator only')
        require(CFG['kind'] == 'p4-marriott-proc-readlink-outer-tu-build04' and
                root == Path('/home/alex/work/pocket4-marriott-proc-readlink-outer-tu-04-20261106') and
                aosp == Path('/home/alex/Documents/Codex/2026-10-23/new-chat-2/work/audio-target-build-r1/aosp-source'),
                'fixed work/source root differs')
        resources.begin()
        for parent in (root.parent, *root.parent.parents):
            require(stat.S_ISDIR(parent.lstat().st_mode), 'work parent symlink/non-directory')
        require(not root.exists() and not root.is_symlink(), 'fresh build root already exists')
        os.umask(0o077)
        root.mkdir(mode=0o700)
        created = True
        root_identity = stamp(root.stat())
        (root/'source').mkdir(mode=0o700)
        (root/'tmp').mkdir(mode=0o700)
        for name, spec in CFG['sources'].items():
            require(re.fullmatch('[a-z][a-z0-9_-]*[.](cc|h|json|bp|py)', name) is not None,
                    'source basename not in fixed safe grammar')
            body = base64.b64decode(spec['base64'], validate=True)
            require(len(body) == spec['bytes'] and digest(body) == spec['sha256'],
                    'inline source pin differs')
            create(root/'source'/name, body)
            _, row = read_input(root/'source'/name, expected=spec, roots=[root])
            report['source_before'][name] = row
            watch[str(root/'source'/name)] = row
        compiler = Path(CFG['compiler']['path'])
        _, tool_before = read_input(compiler, 8*1024*1024, CFG['compiler'], roots=[aosp])
        # Record the actual tuple before its gate so any rejection remains diagnosable.
        report['compiler_before'] = tool_before
        watch[str(compiler)] = tool_before
        # C20 actually used this operator-owned 0775 compiler. Bind that full tuple;
        # the original read_input regular-file and single-link gates still apply.
        require(tool_before == dict(CFG['compiler']['actual_C20_tuple'], nlink=1),
                'pinned compiler differs from complete actual C20 tuple')
        manifest_raw, manifest_row = read_input(CFG['candidate_manifest']['path'], 524288,
                                                CFG['candidate_manifest'])
        manifest = json.loads(manifest_raw)
        require(manifest.get('schema') == 1 and len(manifest['files']) == 949,
                'actual candidate07 manifest shape differs')
        for relative, wanted in CFG['candidate_rows'].items():
            require(manifest['files'].get(relative) == wanted, 'candidate07 selected source row differs')
        report['original_candidate_manifest'] = manifest_row
        watch[CFG['candidate_manifest']['path']] = manifest_row
        raw_owner = base64.b64decode(CFG['sources']['raw_owner_reference.h']['base64'], validate=True).decode()
        require('#define BERBERIS_PROCMAPS_RAW_METADATA_OWNER 0' in raw_owner,
                'default ownership feature was changed')
        report['original_default_zero_retained'] = True
        # Match the actual SDK-device STL selection and fixed ARM64 NDK config.
        # These are full actual readback pins, not inferred from the old host closure.
        engineering = (
            ('sdk_stl_selection', 'build/soong/cc/stl.go'),
            ('target_header_selection', 'prebuilts/clang/host/linux-x86/soong/clangprebuilts.go'),
            ('arm64_ndk_config', 'prebuilts/clang/host/linux-x86/clang-r584948b/android_libc++/ndk/aarch64/include/c++/v1/__config_site'),
        )
        report['android_cxx_configuration_before'] = {}
        for role, relative in engineering:
            path = aosp/relative
            spec = CFG['android_cxx_configuration'][role]
            _, row = read_input(path, 65536, spec, roots=[path])
            report['android_cxx_configuration_before'][role] = row
            watch[str(path)] = row
            require(row == spec['actual_tuple'],
                    'fixed Android C++ configuration source tuple differs: '+role)
        ndk_config = aosp/engineering[2][1]
        report['android_cxx_header_selection'] = {
            'sdk_stl':'ndk_libc++_static','arch':'aarch64',
            'first_include_directory':str(ndk_config.parent),
            'only_allowed_config_leaf':str(ndk_config),
            'host_config_authorized':False,'runtime_ABI_qualified':False}
        # These paths are first-observed fixed source inputs, never executed tools.
        # Their complete actual tuples are retained; no historical header qualification is borrowed.
        anchors = [aosp/'external/googletest/googletest/Android.bp',
                   aosp/'external/googletest/googletest/include/gtest/gtest.h',
                   aosp/'libnativehelper/include_jni/jni.h',
                   aosp/'prebuilts/clang/host/linux-x86/clang-r584948b/include/c++/v1/__config']
        report['new_anchor_inputs'] = {}
        for path in anchors:
            data, row = read_input(path, roots=[aosp])
            if path.name == 'Android.bp':
                text = data.decode('utf-8')
                require('name: "libgtest_ndk_c++"' in text and 'export_include_dirs: ["include"]' in text,
                        'fixed actual GTest provider shape differs')
            report['new_anchor_inputs'][str(path)] = row
            watch[str(path)] = row
        roots = [root/'source', ndk_config,
                 aosp/'prebuilts/clang/host/linux-x86/clang-r584948b/include/c++/v1',
                 aosp/'prebuilts/clang/host/linux-x86/clang-r584948b/lib/clang/22/include',
                 aosp/'bionic/libc/include', aosp/'bionic/libc/kernel',
                 aosp/'external/googletest/googletest/include',
                 aosp/'libnativehelper/include_jni']
        includes = [
            ('-I', str(root/'source')),
            ('-isystem', str(ndk_config.parent)),
            ('-isystem', str(aosp/'prebuilts/clang/host/linux-x86/clang-r584948b/include/c++/v1')),
            ('-I', str(aosp/'external/googletest/googletest/include')),
            ('-I', str(aosp/'libnativehelper/include_jni')),
            ('-isystem', str(aosp/'bionic/libc/include')),
            ('-isystem', str(aosp/'bionic/libc/kernel/uapi/asm-arm64')),
            ('-isystem', str(aosp/'bionic/libc/kernel/uapi')),
            ('-isystem', str(aosp/'bionic/libc/kernel/android/scsi')),
            ('-isystem', str(aosp/'bionic/libc/kernel/android/uapi'))]
        common = [str(compiler), '-target','aarch64-linux-android10000','-x','c++','-std=gnu++17',
                  '-nostdinc++','-nostdlibinc','-DANDROID','-D__BIONIC_NO_PAGE_SIZE_MACRO',
                  '-DNDEBUG','-D_FILE_OFFSET_BITS=64','-D_FORTIFY_SOURCE=3','-O2',
                  '-Wall','-Wextra','-Werror','-Wno-deprecated-declarations','-fexceptions',
                  '-fstack-protector-strong','-fPIC','-fvisibility=hidden',
                  '-ffunction-sections','-fdata-sections']
        for flag, path in includes:
            common += [flag,path]
        require(len(CFG['test_names']) == len(set(CFG['test_names'])) == 12 and
                len(CFG['new_test_names']) == len(set(CFG['new_test_names'])) == 9 and
                set(CFG['new_test_names']).issubset(CFG['test_names']),
                'exact three-old plus nine-new test names required')
        CHILD_REAPER = OwnChildReaper()
        report['child_tree_guard'] = CHILD_REAPER.record
        CHILD_REAPER.begin()
        symbols_by_source = {}
        for name in ('proc_self_maps_test.cc','jni_test.cc','jni_test_main.cc'):
            source = root/'source'/name
            object_path = root/(name+'.o')
            before_dep = root/(name+'.preflight.d')
            actual_dep = root/(name+'.actual.d')
            command(report, root, common + ['-M','-MF',str(before_dep),'-MT',name,str(source)], timeout=25)
            before = dependency_rows(before_dep, name, roots)
            require(str(source) in before and str(anchors[1]) in before,
                    'actual source or real GTest header absent from dependency set')
            report['dependency_before'][name] = before
            for path,row in before.items():
                if path in watch:
                    require(watch[path] == row, 'shared dependency changed across TUs')
                watch[path] = row
            command(report, root, common + ['-MD','-MF',str(actual_dep),'-MT',name,
                    '-c',str(source),'-o',str(object_path)], timeout=25)
            after = dependency_rows(actual_dep, name, roots)
            report['dependency_after'][name] = after
            require(before == after, 'actual compiler dependency set/bytes changed')
            row, symbols = elf_functions(object_path, 183)
            symbols_by_source[name] = symbols
            proof = {'source':name, 'artifact':row, 'ELF_machine':183, 'ELF_type':'REL',
                     'dependency_count':len(after), 'executed':False}
            if name == 'proc_self_maps_test.cc':
                proof['emitted_test_body_symbols'] = []
                for test in CFG['test_names']:
                    class_name = 'ProcSelfMaps_'+test+'_Test'
                    mangled = '_ZN12_GLOBAL__N_1'+str(len(class_name))+class_name+'8TestBodyEv'
                    matched = [s for s in symbols if s['name'] == mangled and
                               s['type'] == 2 and s['defined'] and s['size'] > 0]
                    require(len(matched) == 1, 'one defined TestBody missing: '+test)
                    proof['emitted_test_body_symbols'].append(matched[0])
            report['objects'].append(proof)
        entry = symbols_by_source['jni_test.cc']
        main_symbols = symbols_by_source['jni_test_main.cc']
        require(len([s for s in entry if s['name'] ==
                'Java_com_example_ndk_1tests_NdkTests_runTests' and
                s['type'] == 2 and s['defined'] and s['size'] > 0]) == 1,
                'real Java JNI export not compiled')
        actual_run = [s['name'] for s in main_symbols if s['name'].startswith('_ZN8ndk_test11RunAllTestsE')
                      and s['type'] == 2 and s['defined'] and s['size'] > 0]
        require(len(actual_run) == 1 and any(s['name'] == actual_run[0] and not s['defined'] for s in entry),
                'original JNI call and RunAllTests definition differ')
        report['compiled_JNI_symbol_join'] = {'entry':'Java_com_example_ndk_1tests_NdkTests_runTests',
                                               'RunAllTests':actual_run[0], 'link_not_performed':True}
        require(len(report['commands']) == 6 and len(report['objects']) == 3, 'fixed compiler command count differs')
        # mkdir/file writes change directory times, so preserve the stable root identity fields only.
        current_root = stamp(root.stat(follow_symlinks=False))
        require(current_root[:5] == root_identity[:5], 'new owned root identity changed')
        completed = True
    except Exception as error:
        report['errors'].append({'stage':'compile','error':repr(error),'traceback':traceback.format_exc()})
    finally:
        changed = []
        for path, before in watch.items():
            try:
                _, after = read_input(path, 8*1024*1024, before)
                require(after == before, 'final original/source/dependency metadata changed')
                report['source_after'][path] = after
            except Exception as error:
                changed.append({'path':path,'error':repr(error)})
        report['post_input_errors'] = changed
        report['all_inputs_unchanged'] = bool(watch) and not changed
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
    report['all_children_reaped'] = bool(CHILD_REAPER is not None and
        CHILD_REAPER.record['final_children_empty'] and CHILD_REAPER.record['restored'] and
        all((not x['child_started']) or (x['child_reaped'] and x['owned_tree_cleanup_complete'] and
            x['pidfd_closed'] and x['output_fds_closed']) for x in report['commands']))
    report['input_FD_event_count'] = len(INPUT_FD_EVENTS)
    report['input_FD_close_failures'] = [x for x in INPUT_FD_EVENTS if not x['closed']]
    report['all_tracked_input_FDs_closed'] = not report['input_FD_close_failures']
    report['success'] = bool(completed and not report['errors'] and report['all_inputs_unchanged'] and
        report['all_tracked_input_FDs_closed'] and
        report['all_children_reaped'] and resources.record['held_own_cgroup_gate_passed'])
    report['elapsed_seconds'] = time.monotonic()-BUILD_STARTED
    encoded = (json.dumps(report,sort_keys=True,indent=2)+'\n').encode()
    # Retain complete before/after dependency rows, final rechecks and child records.
    # Only the summary and complete file pin go to stdout after create-only storage.
    require(len(encoded) <= 67108864, 'complete compile receipt exceeds bound')
    if created:
        output = root/'build-result.json'
        create(output,encoded,mode=0o400)
        print(json.dumps({'success':report['success'],'path':str(output),'bytes':len(encoded),
                          'sha256':digest(encoded),'first_error':report['errors'][0] if report['errors'] else None}))
    else:
        print(encoded.decode(),end='')
    return 0 if report['success'] else 1

if __name__ == '__main__':
    raise SystemExit(main())
