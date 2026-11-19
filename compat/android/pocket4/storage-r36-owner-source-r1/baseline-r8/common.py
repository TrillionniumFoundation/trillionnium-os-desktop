"""Finite, task-owned lifecycle helpers for the reviewed 128 MiB trial."""
import ctypes, errno, fcntl, hashlib, json, os, pathlib, re, select, shlex, signal, stat, subprocess, time

P = pathlib.Path
ENV = {'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8'}
GIB = 1024 ** 3

def need(ok, message):
    if not ok:
        raise RuntimeError(message)

def f9(s):
    return [s.st_dev, s.st_ino, s.st_mode, s.st_uid, s.st_gid, s.st_nlink,
            s.st_size, s.st_mtime_ns, s.st_ctime_ns]

def pin(path, expected=None, limit=64 * 1024 ** 2):
    path = P(path)
    need(path.is_absolute() and path.resolve() == path, 'canonical file: ' + str(path))
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_size <= limit, 'bounded regular file')
        raw = bytearray()
        while chunk := os.read(fd, 1024 ** 2):
            raw.extend(chunk)
        need(len(raw) == before.st_size and f9(before) == f9(os.fstat(fd)) == f9(path.lstat()), 'stable whole read')
        ref = {'path': str(path), 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'identity': f9(before)}
        if expected is not None:
            need(ref['bytes'] == expected['bytes'] and ref['sha256'] == expected['sha256'], 'accepted whole SHA: ' + str(path))
            if 'identity' in expected:
                need(ref['identity'] == expected['identity'], 'accepted F9: ' + str(path))
        return ref, bytes(raw)
    finally:
        os.close(fd)

def save(path, value, mode=0o600):
    path = P(path)
    raw = value if isinstance(value, bytes) else (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
    with os.fdopen(fd, 'wb') as stream:
        os.fchmod(stream.fileno(), mode); stream.write(raw); stream.flush(); os.fsync(stream.fileno())
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    os.fsync(parent); os.close(parent)
    return pin(path)[0]

def mem_available():
    return int(next(x.split()[1] for x in P('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:'))) * 1024

def free_space(path):
    v = os.statvfs(path); return v.f_bavail * v.f_frsize

def digest_file(path, max_bytes):
    path = P(path); fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1 and before.st_size <= max_bytes, 'bounded single-link digest')
        digest = hashlib.sha256(); total = 0
        while chunk := os.read(fd, 1024 ** 2): digest.update(chunk); total += len(chunk)
        need(total == before.st_size and f9(before) == f9(os.fstat(fd)) == f9(path.lstat()), 'whole stable streaming digest')
        return {'path': str(path), 'bytes': total, 'sha256': digest.hexdigest(), 'identity': f9(before),
                'allocated_bytes': before.st_blocks * 512}
    finally: os.close(fd)

def birth(pid):
    return (P('/proc') / str(pid) / 'stat').read_text().rsplit(')', 1)[1].split()[19]

def proc_ref(pid):
    root = P('/proc') / str(pid)
    s = (root / 'status').read_text()
    return {'pid': pid, 'start_ticks': birth(pid), 'cmdline': (root / 'cmdline').read_bytes().split(b'\0')[:-1],
            'cgroup': (root / 'cgroup').read_text(), 'uid': next(x for x in s.splitlines() if x.startswith('Uid:')),
            'gid': next(x for x in s.splitlines() if x.startswith('Gid:'))}

class HeldProcess:
    def __init__(self, pid):
        self.pid = pid; self.pidfd = None; self.procfd = None
        try:
            self.pidfd = os.pidfd_open(pid, 0)
            self.procfd = os.open('/proc/' + str(pid), os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
            self.start = birth(pid)
        except BaseException:
            if self.procfd is not None: os.close(self.procfd); self.procfd = None
            if self.pidfd is not None: os.close(self.pidfd); self.pidfd = None
            raise

    def live(self):
        poll = select.poll(); poll.register(self.pidfd, select.POLLIN | select.POLLHUP)
        return not poll.poll(0)

    def signal(self, sig):
        if self.live():
            signal.pidfd_send_signal(self.pidfd, sig)

    def retired(self, timeout=3):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            poll = select.poll(); poll.register(self.pidfd, select.POLLIN | select.POLLHUP)
            if any(events & select.POLLHUP for _, events in poll.poll(50)):
                try:
                    fd = os.open('stat', os.O_RDONLY | os.O_CLOEXEC, dir_fd=self.procfd)
                except OSError as error:
                    need(error.errno in (errno.ENOENT, errno.ESRCH), 'retired original procdir error')
                    return {'pid': self.pid, 'start_ticks': self.start, 'PIDFD_HUP': True, 'original_procdir_absent': True}
                else:
                    os.close(fd)
        raise RuntimeError('original process not reaped: ' + str(self.pid))

    def close(self):
        os.close(self.pidfd); os.close(self.procfd)

class Commands:
    def __init__(self, directory):
        self.directory = P(directory); self.records = []; self.counter = 0

    def start(self, name, argv, uid=None, pass_fds=()):
        need(re.fullmatch('[a-z0-9-]+', name) is not None, 'fixed command label')
        self.counter += 1; prefix = f'{self.counter:03d}-{name}'
        paths = [self.directory / (prefix + ext) for ext in ('.stdout', '.stderr')]
        streams = [open(p, 'xb', buffering=0) for p in paths]
        kwargs = {} if uid is None else {'user': uid, 'group': uid, 'extra_groups': []}
        environment = dict(ENV)
        if uid == 1000:
            environment['HOME'] = '/home/qian-qi'
        process = None
        try:
            process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=streams[0], stderr=streams[1],
                env=environment, close_fds=True, pass_fds=pass_fds, **kwargs)
            held = HeldProcess(process.pid)
            return {'name': name, 'argv': argv, 'popen': process, 'held': held, 'paths': paths,
                    'streams': streams, 'started': time.monotonic()}
        except BaseException as error:
            if process is not None:
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired: process.kill(); process.wait(timeout=5)
                row = {'name': name, 'argv': argv, 'pid': process.pid, 'exit_code': process.returncode,
                       'waitpid_reaped': True, 'PIDFD_HUP': False, 'monitor_start_error': repr(error)}
                self.records.append(row)
                save(self.directory / (f'command-{len(self.records):03d}.json'), row)
            for stream in streams: os.fsync(stream.fileno()); stream.close()
            raise

    def finish(self, child, timeout, allowed=(0,), stop=False):
        process, held = child['popen'], child['held']; timed_out = False
        if stop: held.signal(signal.SIGTERM)
        try:
            try:
                process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True; held.signal(signal.SIGTERM)
                try: process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    held.signal(signal.SIGKILL); process.wait(timeout=5)
            retired = held.retired()
            for stream in child['streams']:
                os.fsync(stream.fileno()); stream.close()
            refs = [pin(path, limit=4 * 1024 ** 2)[0] for path in child['paths']]
            row = {'name': child['name'], 'argv': child['argv'], **retired, 'exit_code': process.returncode,
                'timed_out': timed_out, 'stdout': refs[0], 'stderr': refs[1],
                'elapsed_seconds': time.monotonic() - child['started']}
            child['finished'] = True
            self.records.append(row); save(self.directory / (f'command-{len(self.records):03d}.json'), row)
            need(not timed_out and process.returncode in allowed, 'actual bounded command failed: ' + child['name'])
            return row
        finally:
            held.close()

    def run(self, name, argv, timeout=20, allowed=(0,), uid=None):
        return self.finish(self.start(name, argv, uid=uid), timeout, allowed)

def output(row):
    return pin(row['stdout']['path'], row['stdout'], limit=4 * 1024 ** 2)[1].decode()

def show(commands, unit):
    row = commands.run('unit-show', ['/usr/bin/systemctl', 'show', unit,
        '--property=Id,LoadState,ActiveState,SubState,MainPID,InvocationID,Description,ControlGroup,User,Group,ExecMainPID,ExecMainCode,ExecMainStatus,ExecMainStartTimestampMonotonic,ExecStart,Result', '--no-pager'])
    return dict(line.split('=', 1) for line in output(row).splitlines() if '=' in line)

def native_identity(commands, unit, description, uid):
    state = show(commands, unit)
    need(state['Id'] == unit and state['Description'] == description and state['MainPID'] == str(os.getpid()) and
         state['User'] == state['Group'] == str(uid) and re.fullmatch('[a-f0-9]{32}', state['InvocationID']) is not None,
         'actual native producer identity')
    group = '/sys/fs/cgroup' + state['ControlGroup']
    need(P('/proc/self/cgroup').read_text().strip() == '0::' + state['ControlGroup'], 'actual owned native cgroup')
    expected_cpus = {6, 7} if uid == 0 else {2, 3}
    limits = {name: (P(group) / name).read_text().strip() for name in
              ('memory.max', 'memory.high', 'memory.swap.max', 'pids.max', 'cpu.max', 'cpuset.cpus.effective')}
    need(limits['memory.max'] == '536870912' and limits['memory.high'] == '402653184' and
         limits['memory.swap.max'] == '0' and limits['pids.max'] == ('128' if uid == 0 else '64') and
         limits['cpu.max'] == '200000 100000' and os.sched_getaffinity(0) == expected_cpus and
         limits['cpuset.cpus.effective'] == ('6-7' if uid == 0 else '2-3'),
         'actual native hard resource ceilings and affinity')
    return {'execution_kind': 'native_systemd_system_unit', 'H_job_id': None, 'unit': unit,
            'InvocationID': state['InvocationID'], 'pid': os.getpid(), 'start_ticks': birth(os.getpid()),
            'cgroup': group, 'boot': P('/proc/sys/kernel/random/boot_id').read_text().strip(), 'state': state, 'limits': limits}

def syncfs(fd):
    library = ctypes.CDLL(None, use_errno=True)
    need(library.syncfs(fd) == 0, 'actual filesystem sync')

def check_tools(contract, host):
    refs = {}
    for name, ref in contract['hosts'][host]['tools'].items():
        need(str(P(ref['path']).resolve()) == ref['resolved'], 'fixed system tool resolution')
        refs[name] = pin(ref['resolved'], ref)[0]
    return refs

def sealed_sources(directory, expected_manifest):
    raw = pin(directory / 'SOURCE-MANIFEST.json')[1]
    need(hashlib.sha256(raw).hexdigest() == expected_manifest, 'exact reviewed source manifest')
    manifest = json.loads(raw); refs = {}
    for name, expected in manifest['files'].items():
        need('/' not in name and not name.startswith('.'), 'finite source names')
        refs[name], _ = pin(directory / name, expected)
        need(refs[name]['identity'][3:6] == [0, 0, 1] and stat.S_IMODE(refs[name]['identity'][2]) == 0o444,
             'sealed root-owned source')
    return manifest, refs

def sources_unchanged(refs):
    for ref in refs.values(): pin(ref['path'], ref)

def load_admission(directory, source_manifest_sha, admission_sha, contract):
    ref, raw = pin(directory / 'ADMISSION.json')
    need(ref['sha256'] == admission_sha and ref['identity'][3:6] == [0, 0, 1] and
         stat.S_IMODE(ref['identity'][2]) == 0o444, 'exact sealed final dispatch admission')
    value = json.loads(raw)
    need(value['schema'] == 'p4-nbd-final-current-admission-v1' and value['source_manifest_sha256'] == source_manifest_sha and
         value['nonce'] == contract['nonce'] and value['canonical']['path'] == contract['canonical']['path'] and
         value['pocket4_boot'] == contract['hosts']['pocket4']['boot'], 'admission binds this source, cohort, canonical path and host')
    contract['canonical'] = value['canonical']
    return ref, value

def boot_is(expected):
    need(P('/proc/sys/kernel/random/boot_id').read_text().strip() == expected, 'same accepted host boot')

def host_mac_state():
    lsm = P('/sys/kernel/security/lsm')
    aa = P('/sys/kernel/security/apparmor/profiles')
    enforce = P('/sys/fs/selinux/enforce')
    return {'boot': P('/proc/sys/kernel/random/boot_id').read_text().strip(), 'kernel': os.uname().release,
            'active_lsm': lsm.read_text() if lsm.exists() else None,
            'apparmor_profiles_sha256': hashlib.sha256(aa.read_bytes()).hexdigest() if aa.exists() else None,
            'selinux_enforce': enforce.read_text() if enforce.exists() else None}

def remove_retired_socket(path, expected):
    path = P(path)
    rows = [line for line in P('/proc/net/unix').read_text().splitlines()[1:]
            if len(line.split(maxsplit=7)) == 8 and line.split(maxsplit=7)[7] == str(path)]
    need(not rows, 'no live Unix socket object before owned pathname cleanup')
    try: before = path.lstat()
    except FileNotFoundError: return {'path': str(path), 'already_absent': True}
    need(stat.S_ISSOCK(before.st_mode) and f9(before) == expected, 'same original retired Unix socket pathname')
    path.unlink()
    directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    os.fsync(directory); os.close(directory)
    need(not os.path.lexists(path), 'owned retired socket pathname absent')
    return {'path': str(path), 'original_f9': expected, 'removed_after_process_retirement': True}

class OwnedUnit:
    def __init__(self, commands, unit, description, uid, argv, directory, properties):
        self.commands = commands; self.unit = unit; self.description = description
        self.argv = argv; self.uid = uid; self.held = None; self.ref = None; self.directory = P(directory)
        state = show(commands, unit)
        need(state.get('LoadState') == 'not-found' and not (P('/sys/fs/cgroup/system.slice') / unit).exists(), 'new native unit absent')
        self.logs = [P(directory) / (unit + ext) for ext in ('.stdout', '.stderr')]
        for path in self.logs: save(path, b'')
        props = ['Type=exec', 'RemainAfterExit=yes', 'User=' + str(uid), 'Group=' + str(uid),
                 'KillMode=control-group', 'UMask=0077', 'LimitCORE=0', 'StandardInput=null',
                 'StandardOutput=append:' + str(self.logs[0]), 'StandardError=append:' + str(self.logs[1])] + properties
        launch = ['/usr/bin/systemd-run', '--unit=' + unit, '--description=' + description]
        for value in props: launch += ['-p', value]
        launch += argv
        self.intent = {'unit': unit, 'description': description, 'uid': uid, 'argv': argv,
                       'actual_systemd_argv': launch, 'H_job_id': None, 'properties': props,
                       'boot': P('/proc/sys/kernel/random/boot_id').read_text().strip(), 'created_monotonic_ns': time.monotonic_ns()}
        save(P(directory) / (unit + '.intent.json'), self.intent)

    def launch(self):
        self.launch_error = None
        try: self.commands.run('start-native-unit-once', self.intent['actual_systemd_argv'], 30)
        except BaseException as error: self.launch_error = repr(error)
        return self.reconcile()

    @classmethod
    def recover(cls, commands, directory, unit):
        intent = json.loads(pin(P(directory) / (unit + '.intent.json'))[1])
        actor = object.__new__(cls); actor.commands = commands; actor.directory = P(directory)
        actor.unit = unit; actor.intent = intent; actor.description = intent['description']; actor.uid = intent['uid']
        actor.argv = intent['argv']; actor.held = None; actor.ref = None; actor.launch_error = None
        actor.logs = [P(directory) / (unit + ext) for ext in ('.stdout', '.stderr')]
        actor.reconcile(); return actor

    def reconcile(self):
        boot_is(self.intent['boot']); deadline = time.monotonic() + 10
        state = show(self.commands, self.unit)
        while state.get('LoadState') != 'not-found' and state.get('MainPID') == '0' and state.get('ExecMainCode') == '0':
            need(time.monotonic() < deadline, 'finite same-unit start reconciliation')
            time.sleep(0.1); state = show(self.commands, self.unit)
        need(state.get('Description') == self.description and state.get('User') == state.get('Group') == str(self.uid),
             'actual original native unit identity')
        actual_argv = re.findall(r'argv\[\]=(.*?) ;', state.get('ExecStart', ''))
        need(len(actual_argv) == 1 and shlex.split(actual_argv[0]) == self.argv and
             int(state['ExecMainStartTimestampMonotonic']) * 1000 >= self.intent['created_monotonic_ns'],
             'actual service-manager command and start belongs to create-only intent')
        self.state = state; self.group = P('/sys/fs/cgroup/system.slice') / self.unit
        live_pid = int(state.get('MainPID', '0')); start = None
        if live_pid:
            if self.held is None: self.held = HeldProcess(live_pid)
            need(self.held.pid == live_pid and self.held.live(), 'held original native main process')
            start = self.held.start; ref = proc_ref(live_pid)
            again = show(self.commands, self.unit)
            need(again['InvocationID'] == state['InvocationID'] and again['MainPID'] == str(live_pid) and
                 ref['cmdline'] == [x.encode() for x in self.argv] and ref['cgroup'].strip() == '0::' + state['ControlGroup'],
                 'bracketed actual foreground native argv and cgroup')
        else:
            need(state['ExecMainCode'] in ('1', '2', '3'), 'real terminal original invocation')
        self.ref = {'unit': self.unit, 'InvocationID': state['InvocationID'], 'pid': live_pid or int(state['ExecMainPID']),
                    'start_ticks': start, 'cgroup': str(self.group), 'argv': self.argv, 'H_job_id': None,
                    'terminal_at_first_observation': not bool(live_pid), 'state': state,
                    'launch_ack_error': self.launch_error}
        actual_path = self.directory / (self.unit + '.actual.json')
        if actual_path.exists():
            previous = json.loads(pin(actual_path)[1])
            need(all(previous[key] == self.ref[key] for key in ('unit', 'InvocationID', 'pid', 'argv')), 'same already observed invocation')
            if previous['start_ticks'] is not None:
                if live_pid: need(self.held.start == previous['start_ticks'], 'original live process generation on re-observation')
                self.ref['start_ticks'] = previous['start_ticks']
        else: save(actual_path, self.ref)
        if not live_pid: return self.ref
        expected = dict(value.split('=', 1) for value in self.intent['properties'])
        self.limits = {name: (self.group / name).read_text().strip() for name in ('memory.max', 'memory.swap.max', 'pids.max', 'cpu.max', 'cpuset.cpus.effective')}
        need(self.limits['memory.max'] == expected['MemoryMax'] and self.limits['memory.swap.max'] == '0' and
             self.limits['pids.max'] == expected['TasksMax'] and self.limits['cpu.max'] == '200000 100000' and
             os.sched_getaffinity(self.held.pid) == {int(x) for x in expected['CPUAffinity'].split()} and
             self.limits['cpuset.cpus.effective'] == expected['AllowedCPUs'].replace(' ', '-'), 'actual child unit ceilings')
        self.ref['limits'] = self.limits
        return self.ref

    def verify_live(self):
        need(self.held is not None and self.held.live() and birth(self.held.pid) == self.held.start, 'held native process remains live')
        state = show(self.commands, self.unit)
        need(state['InvocationID'] == self.ref['InvocationID'] and state['MainPID'] == str(self.held.pid) and
             state['Description'] == self.description and state['ControlGroup'] == self.state['ControlGroup'], 'same live native invocation')
        return state

    def retire(self, stop, expected_exit=None):
        if self.ref is None: self.reconcile()
        before = show(self.commands, self.unit)
        need(before['InvocationID'] == self.ref['InvocationID'] and before['Description'] == self.description,
             'only original native invocation can retire')
        if stop and before['MainPID'] != '0':
            need(before['MainPID'] == str(self.held.pid) and self.held.live(), 'same original live stop target')
            self.held.signal(signal.SIGTERM)
        if self.held is None:
            need(before['MainPID'] == '0' and before['ExecMainCode'] in ('1', '2', '3'), 'actual terminal at first observation')
            proof = {'PIDFD_HUP': None, 'actual_service_manager_terminal': True,
                     'terminal_at_first_observation': True, 'ExecMainPID': before['ExecMainPID']}
        else:
            proof = self.held.retired(10)
        terminal = show(self.commands, self.unit)
        need(terminal.get('InvocationID') == self.ref['InvocationID'] and terminal['MainPID'] == '0',
             'real terminal retained before releasing native unit')
        save(self.commands.directory / (self.unit + '.terminal-before-stop.json'), terminal)
        exit_matches = expected_exit is None or (terminal['ExecMainCode'] == '1' and terminal['ExecMainStatus'] == str(expected_exit))
        if terminal.get('LoadState') != 'not-found':
            need(terminal.get('InvocationID') == self.ref['InvocationID'], 'same terminal native invocation')
            self.commands.run('release-owned-native-unit', ['/usr/bin/systemctl', 'stop', self.unit], 45)
        after = show(self.commands, self.unit)
        if after.get('ActiveState') == 'failed':
            need(after.get('InvocationID') == self.ref['InvocationID'], 'only original failed invocation reset')
            self.commands.run('reset-owned-failed-state', ['/usr/bin/systemctl', 'reset-failed', self.unit], 15)
            after = show(self.commands, self.unit)
        need(after['MainPID'] == '0' and after['ActiveState'] == 'inactive' and not self.group.exists(), 'owned native cgroup gone')
        if self.held is not None: self.held.close(); self.held = None
        return {'actual': self.ref, 'before_stop': before, 'terminal': terminal, 'after': after, **proof,
                'cgroup_absent': True, 'expected_exit_matches': exit_matches, 'logs': [pin(path)[0] for path in self.logs]}
