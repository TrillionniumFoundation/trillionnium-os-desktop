"""Capabilities and bounded records for this one owned NORMAL attempt."""
import ctypes, errno, hashlib, json, os, select, signal, socket, stat, struct, subprocess, time
from pathlib import Path
from pinned_support import (need, stamp, require_cgroup2, bounded, verify_fd, pinned,
    dead, await_dead, identity, pidfd_pid, atomic_json, counters, NAMES)

MAX_RECORD = 1024 * 1024

# Only this paired Owner16 consumer can receive the new diagnostic extension.
# Ordinary responses and unrelated records retain their original limits.
LEGACY_CONTROL_BYTES = 256 * 1024
INIT_LOG_CAPACITY = 256 * 1024
INIT_LOG_CONTROL_BYTES = 1024 * 1024
INIT_LOG_ACTOR_BYTES = 4 * 1024 * 1024
INIT_LOG_SCOPE = ('generation-private cached init logger; '
                  'fork-before-exec writers not individually attributed')
INIT_LOG_RESPONSE_FIELDS = ('start_response', 'latest_status', 'active_response',
                           'stop_response', 'retained_status', 'failure_cleanup_stop')


def init_log_hex_bytes(response):
    """Validate bounded data, including failed capture; grant no lifecycle effect."""
    need(isinstance(response, dict), 'lifecycle response is not an object')
    audit = response.get('relay_lifecycle')
    if not isinstance(audit, dict) or 'init_log' not in audit:
        return 0
    record = audit['init_log']
    fields = {'schema', 'nonce', 'device', 'inode', 'capacity_bytes',
              'marker_verified_after_held_init_hello', 'retirement_proven_before_capture',
              'observed_writer_offset', 'captured_bytes', 'captured_sha256', 'captured_hex',
              'capacity_reached', 'stream_completeness_claimed', 'exact_writer_per_line_proven',
              'source_scope', 'first_error', 'secondary_errors', 'held_fds_closed'}
    need(isinstance(record, dict) and set(record) == fields,
         'init diagnostic schema fields differ')
    nonce = record['nonce']
    need(type(record['schema']) is int and record['schema'] == 1 and
         type(audit.get('schema')) is int and audit['schema'] == 1 and
         isinstance(nonce, str) and len(nonce) == 64 and
         all(c in '0123456789abcdef' for c in nonce) and nonce == audit.get('nonce'),
         'init diagnostic generation/schema differs')
    need(type(record['capacity_bytes']) is int and record['capacity_bytes'] == INIT_LOG_CAPACITY and
         type(record['captured_bytes']) is int and 0 <= record['captured_bytes'] <= INIT_LOG_CAPACITY,
         'init diagnostic capacity/capture bound differs')
    need(all(type(record[k]) is int and 0 <= record[k] < 2**64 for k in ('device', 'inode')) and
         record['inode'] > 0, 'init diagnostic object identity malformed')
    offset = record['observed_writer_offset']
    need(offset is None or (type(offset) is int and 0 <= offset <= INIT_LOG_CAPACITY),
         'init diagnostic writer offset malformed')
    booleans = ('marker_verified_after_held_init_hello', 'retirement_proven_before_capture',
                'capacity_reached', 'stream_completeness_claimed',
                'exact_writer_per_line_proven', 'held_fds_closed')
    need(all(type(record[k]) is bool for k in booleans) and
         record['stream_completeness_claimed'] is False and
         record['exact_writer_per_line_proven'] is False and record['source_scope'] == INIT_LOG_SCOPE,
         'init diagnostic observation scope differs')
    text = record['captured_hex']; digest = record['captured_sha256']
    need(isinstance(text, str) and len(text) == 2 * record['captured_bytes'] and
         all(c in '0123456789abcdef' for c in text) and isinstance(digest, str) and
         len(digest) == 64 and hashlib.sha256(bytes.fromhex(text)).hexdigest() == digest,
         'init diagnostic full prefix/sha256 differs')
    error = record['first_error']; secondary = record['secondary_errors']
    need(error is None or (isinstance(error, str) and len(error.encode('utf-8')) <= 512),
         'init diagnostic first error bound differs')
    need(isinstance(secondary, list) and len(secondary) <= 4 and
         all(isinstance(x, str) and len(x.encode('utf-8')) <= 512 for x in secondary),
         'init diagnostic secondary error bound differs')
    # False marker/retirement/close or non-null errors stay visible as data.
    # The original producer and lifecycle qualifier decide success separately.
    return len(text)


def decode_lifecycle_response(raw):
    need(0 < len(raw) <= INIT_LOG_CONTROL_BYTES, 'lifecycle response exceeded paired bound')
    value = json.loads(raw)
    credit = init_log_hex_bytes(value)
    need(len(raw) - credit <= LEGACY_CONTROL_BYTES,
         'non-diagnostic lifecycle response exceeded original bound')
    return value


def receive_lifecycle_response(sock):
    raw = bytearray()
    while True:
        part = sock.recv(65536)
        if not part:
            break
        raw.extend(part)
        need(len(raw) <= INIT_LOG_CONTROL_BYTES, 'lifecycle response exceeded paired bound')
    return decode_lifecycle_response(raw)


def read_actor_result(path):
    value, digest = read_json(path, maximum=INIT_LOG_ACTOR_BYTES)
    need(isinstance(value, dict), 'actor result is not an object')
    # Match the original atomic_json writer exactly so whitespace cannot consume
    # the dedicated diagnostic allowance without being counted.
    raw = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    need(hashlib.sha256(raw).hexdigest() == digest, 'actor result writer encoding differs')
    credit = sum(init_log_hex_bytes(value[k]) for k in INIT_LOG_RESPONSE_FIELDS if k in value)
    need(len(raw) - credit <= MAX_RECORD,
         'non-diagnostic actor result exceeded original record bound')
    return value, digest


def file_id(fd):
    st = os.fstat(fd)
    return {'device': st.st_dev, 'inode': st.st_ino}


def digest_fd(fd, expected_size=None):
    before = os.fstat(fd)
    need(stat.S_ISREG(before.st_mode) and 0 < before.st_size <= 2 * 1024**3, 'invalid pinned regular input')
    if expected_size is not None:
        need(before.st_size == expected_size, 'pinned input size differs')
    h = hashlib.sha256()
    off = 0
    while off < before.st_size:
        part = os.pread(fd, min(1024 * 1024, before.st_size - off), off)
        need(part, 'pinned input truncated')
        h.update(part); off += len(part)
    need(os.pread(fd, 1, off) == b'' and stamp(os.fstat(fd)) == stamp(before), 'pinned input changed')
    return h.hexdigest(), before


def read_json(path, digest=None, maximum=MAX_RECORD):
    fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_uid == 0 and before.st_nlink == 1 and
             not before.st_mode & 0o6022 and 0 < before.st_size <= maximum, 'record metadata differs')
        raw = os.read(fd, maximum + 1)
        need(len(raw) == before.st_size and stamp(os.fstat(fd)) == stamp(before), 'record changed')
        sha = hashlib.sha256(raw).hexdigest()
        need(digest is None or digest == sha, 'external record digest differs')
        return json.loads(raw), sha
    finally:
        os.close(fd)


def write_bytes(directory, name, raw, mode=0o444):
    need('/' not in name and name not in ('', '.', '..'), 'not an owned output leaf')
    fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_CLOEXEC | os.O_NOFOLLOW,
                 0o600, dir_fd=directory)
    try:
        view = memoryview(raw)
        while view:
            n = os.write(fd, view); need(n > 0, 'short owned write'); view = view[n:]
        os.fchmod(fd, mode); os.fsync(fd)
    finally:
        os.close(fd)
    os.fsync(directory)


def save(directory, name, value):
    sha = atomic_json(directory, name, value)
    os.chmod(name, 0o444, dir_fd=directory, follow_symlinks=False)
    return sha


def directory(path):
    p = Path(path)
    need(p.is_absolute() and '..' not in p.parts, 'non-normal directory')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in p.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
        out, fd = fd, -1
        return out
    finally:
        if fd >= 0: os.close(fd)


def root_directory(path):
    p = Path(path)
    need(p.is_absolute() and '..' not in p.parts, 'non-normal root-owned path')
    fd = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        for part in p.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=fd)
            os.close(fd); fd = child
            st = os.fstat(fd)
            need(st.st_uid == 0 and st.st_gid == 0 and not st.st_mode & 0o022, 'unsafe root-owned ancestor')
        out, fd = fd, -1
        return out
    finally:
        if fd >= 0: os.close(fd)


def record_error(result, stage, error):
    value = {'stage': stage, 'error': repr(error)}
    result.setdefault('errors', []).append(value)
    result.setdefault('first_error', value)


class Process:
    def __init__(self, pid):
        self.pidfd = self.proc = self.exe = -1
        self.namespaces = []
        try:
            self.pidfd = os.pidfd_open(pid)
            self.value, self.proc = identity(self.pidfd)
            need(self.value['pid'] == pid, 'pidfd lookup differs')
            self.exe = os.open('exe', os.O_RDONLY | os.O_CLOEXEC, dir_fd=self.proc)
            self.exe_sha256, self.exe_stat = digest_fd(self.exe)
            for name in NAMES:
                self.namespaces.append(os.open('ns/' + name, os.O_RDONLY | os.O_CLOEXEC, dir_fd=self.proc))
            self.live()
        except BaseException:
            self.close(); raise

    def live(self):
        need(not dead(self.pidfd) and pidfd_pid(self.pidfd) == self.value['pid'], 'original held process died')
        birth = int(bounded(self.proc, 'stat').decode().rsplit(')', 1)[1].split()[19])
        need(birth == self.value['birth'], 'held process birth changed')

    def observation(self):
        self.live()
        return {'pid': self.value['pid'], 'birth': self.value['birth'],
                'pidfd': file_id(self.pidfd), 'proc_dir': file_id(self.proc)}

    def snapshot(self):
        self.live()
        row = {'process': self.observation(), 'identity': self.value,
               'namespaces': [file_id(fd) for fd in self.namespaces],
               'executable': file_id(self.exe), 'executable_sha256': self.exe_sha256}
        need(stamp(os.fstat(self.exe)) == stamp(self.exe_stat), 'held process executable changed')
        self.live()
        return row

    def signal(self, sig):
        if not dead(self.pidfd): signal.pidfd_send_signal(self.pidfd, sig, None, 0)

    def close(self):
        for fd in self.namespaces: os.close(fd)
        self.namespaces = []
        for name in ('exe', 'proc', 'pidfd'):
            fd = getattr(self, name, -1)
            if fd >= 0: os.close(fd); setattr(self, name, -1)


def own_cgroup():
    rows = [s[3:] for s in Path('/proc/self/cgroup').read_text().splitlines() if s.startswith('0::')]
    need(len(rows) == 1 and rows[0].startswith('/') and '..' not in Path(rows[0]).parts, 'own unified cgroup differs')
    fd = directory('/sys/fs/cgroup' + rows[0]); require_cgroup2(fd)
    need(str(os.getpid()) in bounded(fd, 'cgroup.procs').decode().split(), 'caller is not in its own cgroup')
    return rows[0], fd


def sample_cgroup(fd):
    require_cgroup2(fd)
    names = ('memory.max', 'memory.high', 'memory.swap.max', 'cpu.max', 'pids.max',
             'memory.current', 'memory.peak', 'memory.swap.current', 'memory.swap.peak',
             'memory.events', 'pids.current', 'cgroup.events', 'cgroup.procs')
    return {'identity': file_id(fd), 'values': {name: bounded(fd, name, 65536).decode().strip() for name in names}}


def require_limits(sample, expected):
    need(all(sample['values'][key] == value for key, value in expected.items()), 'owned cgroup envelope differs')


def healthy(before, after):
    need(before['identity'] == after['identity'], 'owned cgroup replaced')
    a, b = (counters(x['values']['memory.events']) for x in (before, after))
    for key in ('max', 'oom', 'oom_kill', 'oom_group_kill'):
        need(key in a and key in b and int(a[key]) == int(b[key]) == 0, 'owned memory limit or OOM event: ' + key)
    need(int(after['values']['memory.peak']) < int(after['values']['memory.max']) and
         int(after['values']['memory.swap.peak']) == 0, 'owned peak/swap envelope failed')


def write_at(fd, name, value):
    need('/' not in name, 'invalid owned cgroup leaf')
    target = os.open(name, os.O_WRONLY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=fd)
    try:
        raw = value.encode(); need(os.write(target, raw) == len(raw), 'short owned cgroup write')
    finally:
        os.close(target)


def make_child(parent, name):
    need('/' not in name and name not in ('', '.', '..'), 'invalid owned child')
    os.mkdir(name, 0o700, dir_fd=parent)
    return os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW, dir_fd=parent)


def parent_death(parent_pid, user=None, groups=()):
    libc = ctypes.CDLL(None, use_errno=True)
    if user is not None:
        os.setgroups(groups); os.setgid(user); os.setuid(user)
        need(libc.prctl(38, 1, 0, 0, 0) == 0, 'private helper NoNewPrivileges failed')
    need(libc.prctl(1, signal.SIGTERM, 0, 0, 0) == 0 and os.getppid() == parent_pid, 'owned parent-death contract failed')


class Child:
    def __init__(self, role, argv, executable_fd, evidence, env, user=None, groups=()):
        self.role = role; self.child = None; self.process = None; self.logs = []
        self.original = {'role': role, 'argv': argv, 'user': user}
        try:
            for name in ('stdout', 'stderr'):
                self.logs.append(os.open(role + '.' + name, os.O_WRONLY | os.O_CREAT | os.O_EXCL |
                    os.O_CLOEXEC | os.O_NOFOLLOW, 0o600, dir_fd=evidence))
            parent = os.getpid()
            self.child = subprocess.Popen(argv, executable='/proc/self/fd/' + str(executable_fd),
                stdin=subprocess.DEVNULL, stdout=self.logs[0], stderr=self.logs[1],
                close_fds=True, pass_fds=(executable_fd,), cwd='/', env=env,
                preexec_fn=lambda: parent_death(parent, user, groups))
            self.process = Process(self.child.pid)
            self.original['initial'] = self.process.snapshot()
        except BaseException as original:
            # Retain the exact Child even when post-spawn pinning fails.
            try: self.stop()
            except BaseException as cleanup_error:
                raise RuntimeError('first spawn failure: ' + repr(original) + '; exact child cleanup failed: ' + repr(cleanup_error)) from original
            raise
        finally:
            for fd in self.logs: os.close(fd)
            self.logs = []

    def stop(self):
        if self.child is None: return {'not_spawned': True}
        forced = False
        if self.child.poll() is None:
            if self.process is not None: self.process.signal(signal.SIGTERM)
            else: self.child.terminate()
            try: self.child.wait(timeout=5)
            except subprocess.TimeoutExpired:
                forced = True
                if self.process is not None: self.process.signal(signal.SIGKILL)
                else: self.child.kill()
                self.child.wait(timeout=3)
        result = {'pid': self.child.pid, 'returncode': self.child.returncode, 'reaped': True, 'forced_kill': forced}
        if self.process is not None:
            need(dead(self.process.pidfd), 'reaped child pidfd still live')
        return result

    def close(self):
        if self.process is not None: self.process.close(); self.process = None


def endpoint(path, process, uid, kind, seconds=20):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        process.live()
        try:
            st = os.stat(path, follow_symlinks=False)
            need(stat.S_ISSOCK(st.st_mode) and st.st_uid == uid, 'endpoint owner/type differs')
            with socket.socket(socket.AF_UNIX, kind) as sock:
                sock.settimeout(1); sock.connect(str(path))
                peer = struct.unpack('3i', sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
                need(peer[:2] == (process.value['pid'], uid), 'endpoint peer differs from held child')
            process.live()
            return {'device': st.st_dev, 'inode': st.st_ino}
        except (FileNotFoundError, ConnectionRefusedError): time.sleep(0.05)
    raise RuntimeError('owned endpoint deadline exceeded: ' + str(path))


def control(path, process, expected_inode, request, seconds=20):
    process.live()
    st = os.stat(path, follow_symlinks=False)
    need({'device': st.st_dev, 'inode': st.st_ino} == expected_inode and stat.S_ISSOCK(st.st_mode), 'control socket replaced')
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(seconds); sock.connect(path)
        peer = struct.unpack('3i', sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        need(peer == (process.value['pid'], 0, 0), 'control peer is not original root producer')
        process.live()
        sock.sendall(json.dumps(request, separators=(',', ':')).encode())
        sock.shutdown(socket.SHUT_WR)
        return receive_lifecycle_response(sock)
