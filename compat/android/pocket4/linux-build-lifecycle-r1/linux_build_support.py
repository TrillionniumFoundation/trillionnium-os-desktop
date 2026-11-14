"""Fresh Linux build ownership, bounded commands, resources, and file witnesses.

This module has no historical job, PID, cgroup, device, or lock-inode authority.
The caller pins it as source and records each new host observation separately.
"""
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import resource
import select
import signal
import stat
import subprocess
import sys
import time

GIB = 1024 ** 3
PROFILE = {
    'name': 'audio-apex-memory24g-cpu8-jobs6-go5g2-hostreserve5g-work62g-sharedreserve16g-v1',
    'build_memory_max_bytes': 24 * GIB,
    'memory_swap_max_bytes': 0,
    'cpu_quota_percent': 800,
    'cpu_affinity': list(range(8)),
    'normal_requested_jobs': 6,
    'go_memory_limit_bytes': 5 * GIB,
    'go_max_procs': 2,
    'go_gc_percent': 50,
    'host_reserve_bytes': 5 * GIB,
    'fresh_memavailable_minimum_bytes': 29 * GIB,
    'initial_build_work_budget_bytes': 62 * GIB,
    'shared_disk_reserve_bytes': 16 * GIB,
    'fresh_disk_minimum_bytes': 78 * GIB,
    'normal_build_timeout_seconds': 21600,
    'inner_runtime_max_seconds': 22800,
    'outer_timeout_seconds': 28800,
    'outer_memory_max_bytes': 2 * GIB,
    'outer_cpu_quota_percent': 200,
}
CANCELLED = []


def need(value, message):
    if not value:
        raise RuntimeError(message)


def validate_profile(profile):
    need(type(profile) is dict and set(profile) == set(PROFILE), 'complete named desktop profile required')
    for key, expected in PROFILE.items():
        actual = profile[key]
        if type(expected) is int:
            need(type(actual) is int, 'profile integer type differs: ' + key)
        elif type(expected) is list:
            need(type(actual) is list and all(type(x) is int for x in actual), 'CPU list type differs')
        else:
            need(type(actual) is str, 'profile name type differs')
        need(actual == expected, 'desktop profile field differs: ' + key)
    return profile


def identity(info):
    return [getattr(info, key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid',
            'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')]


def file_ref(path, maximum=256 * 1024**2, *, contents=False, copy_to=None):
    path = Path(path)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    output = None
    try:
        before = os.fstat(fd)
        need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
             and 0 <= before.st_size <= maximum, 'bounded single-link regular file required: ' + str(path))
        if copy_to is not None:
            output = os.open(copy_to, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o400)
        digest = hashlib.sha256(); size = 0; chunks = []
        while True:
            block = os.read(fd, 1024**2)
            if not block:
                break
            size += len(block); need(size <= maximum, 'file grew beyond bound'); digest.update(block)
            if contents:
                chunks.append(block)
            if output is not None:
                view = memoryview(block)
                while view:
                    n = os.write(output, view); need(n > 0, 'short snapshot write'); view = view[n:]
        need(size == before.st_size and identity(before) == identity(os.fstat(fd)) == identity(path.lstat()),
             'held source file changed: ' + str(path))
        if output is not None:
            os.fsync(output)
        ref = {'path': str(path), 'bytes': size, 'sha256': digest.hexdigest(), 'identity': identity(before)}
        return (ref, b''.join(chunks)) if contents else ref
    finally:
        if output is not None:
            os.close(output)
        os.close(fd)


def pinned(ref, maximum=256 * 1024**2, *, contents=False):
    need(type(ref) is dict and type(ref.get('bytes')) is int and ref['bytes'] >= 0
         and type(ref.get('sha256')) is str, 'strict file reference required')
    result = file_ref(ref['path'], maximum, contents=contents)
    actual = result[0] if contents else result
    need(all(actual[key] == ref[key] for key in ('path', 'bytes', 'sha256')), 'pinned bytes differ')
    return result


def create(path, value, mode=0o400):
    raw = value if type(value) is bytes else (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, mode)
    try:
        view = memoryview(raw)
        while view:
            n = os.write(fd, view); need(n > 0, 'short evidence write'); view = view[n:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return file_ref(path)


def read_json(path, maximum=8 * 1024**2):
    ref, raw = file_ref(path, maximum, contents=True)
    return json.loads(raw), ref


def load_module(path):
    name = 'owned_' + Path(path).stem
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
    return module


def self_cgroup():
    rows = Path('/proc/self/cgroup').read_text().splitlines()
    need(len(rows) == 1 and rows[0].startswith('0::/'), 'unified actual cgroup required')
    return Path('/sys/fs/cgroup') / rows[0][3:].lstrip('/')


def memavailable():
    rows = Path('/proc/meminfo').read_text().splitlines()
    return int(next(line.split()[1] for line in rows if line.startswith('MemAvailable:'))) * 1024


def disk_free(root):
    value = os.statvfs(root)
    return value.f_bavail * value.f_frsize


def budget_snapshot(cgroup, *, inner):
    row = {name: (cgroup / name).read_text().strip() for name in
           ('memory.max', 'memory.swap.max', 'memory.swap.current', 'cpu.max',
            'memory.current', 'memory.peak', 'memory.events')}
    row.update(affinity=sorted(os.sched_getaffinity(0)), nice=os.getpriority(os.PRIO_PROCESS, 0),
               file_size_rlimit=list(resource.getrlimit(resource.RLIMIT_FSIZE)))
    maximum = PROFILE['build_memory_max_bytes' if inner else 'outer_memory_max_bytes']
    need(row['memory.max'] == str(maximum) and row['memory.swap.current'] == '0', 'actual memory cap/swap differs')
    need(row['cpu.max'] == ('800000 100000' if inner else '200000 100000'), 'actual CPU quota differs')
    if inner:
        need(row['memory.swap.max'] == '0' and row['affinity'] == list(range(8)), 'actual inner affinity/no-swap differs')
    need(row['nice'] >= 10 and row['file_size_rlimit'][0] == resource.RLIM_INFINITY, 'actual nice/file limit differs')
    return row


def event_counts(text):
    return {key: int(value) for key, value in (line.split() for line in text.splitlines())}


def admission(root):
    row = {'observed_ns': time.time_ns(), 'memavailable_bytes': memavailable(), 'disk_free_bytes': disk_free(root)}
    need(row['memavailable_bytes'] >= PROFILE['fresh_memavailable_minimum_bytes'], 'fresh desktop memory is below 24 GiB + 5 GiB reserve')
    need(row['disk_free_bytes'] >= PROFILE['fresh_disk_minimum_bytes'], 'fresh shared disk is below one 62 GiB work budget + 16 GiB reserve')
    return row


def serial_lock(path, owner_uid):
    need(type(owner_uid) is int and owner_uid >= 0, 'strict lock owner UID required')
    path = Path(path)
    need(path.is_absolute(), 'absolute shared serial lock path required')
    fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | os.O_CLOEXEC, 0o600)
    try:
        s = os.fstat(fd)
        need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_uid == os.getuid() == owner_uid
             and stat.S_IMODE(s.st_mode) == 0o600, 'shared serial lock owner/type differs')
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        need(identity(s) == identity(path.lstat()), 'shared serial lock was replaced')
        return fd, {'path': str(path), 'identity': identity(s), 'held_exclusive': True}
    except BaseException:
        os.close(fd); raise


def work_lock_probe(work, expected=None, *, owner_uid):
    need(type(owner_uid) is int and owner_uid >= 0, 'strict work lock owner UID required')
    held = []; rows = []
    try:
        for name in ('package-build.lock', 'aosp-source-update.lock'):
            path = Path(work) / name
            fd = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
            held.append(fd); s = os.fstat(fd)
            need(stat.S_ISREG(s.st_mode) and s.st_nlink == 1 and s.st_uid == owner_uid
                 and stat.S_IMODE(s.st_mode) == 0o600, 'normal work-lock owner/type differs')
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            raw = os.pread(fd, 4097, 0); need(len(raw) <= 4096, 'work-lock content bound')
            need(identity(s) == identity(os.fstat(fd)) == identity(path.lstat()), 'work-lock replaced during probe')
            if expected is not None:
                prior = next(row for row in expected if row['path'] == str(path))
                need((s.st_dev, s.st_ino) == tuple(prior['identity'][:2]), 'normal work-lock inode changed')
            rows.append({'path': str(path), 'identity': identity(s), 'content': raw.decode('ascii'), 'observed_free': True})
        return rows
    finally:
        for fd in held:
            os.close(fd)


def process_identity(pid):
    root = Path('/proc') / str(pid)
    raw = (root / 'stat').read_text()
    return {'pid': pid, 'start_ticks': int(raw[raw.rfind(')') + 2:].split()[19]),
            'exe': os.readlink(root / 'exe'), 'cgroup': (root / 'cgroup').read_text(),
            'argv': [s.decode('utf-8', 'strict') for s in (root / 'cmdline').read_bytes().split(b'\0') if s]}


class OwnedCommands:
    def __init__(self, directory, source_directory):
        self.directory = Path(directory); self.directory.mkdir(mode=0o700)
        self.life = load_module(Path(source_directory) / 'owned_lifecycle.py')
        self.adoption = load_module(Path(source_directory) / 'owned_adoption.py')
        self.records = []

    def run(self, name, argv, timeout, *, env=None, cwd=None, monitor=None, recovery=False):
        need(type(timeout) is int and 0 < timeout <= 21600, 'bounded owned command timeout required')
        output = self.directory / (name + '.stdout'); error = self.directory / (name + '.stderr')
        row = {'name': name, 'argv': argv, 'started_ns': time.time_ns(), 'errors': [],
               'lifecycle': {'child_reaped': False, 'pidfd_closed': True}}
        reaper = self.life.OwnChildReaper(); child = None; pidfd = None; out = err = None
        def remember(exc, stage):
            row['errors'].append({'stage': stage, 'type': type(exc).__name__, 'message': str(exc)})
        try:
            reaper.begin(); reaper.before_command()
            out = output.open('xb'); err = error.open('xb')
            child = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out,
                                     stderr=err, close_fds=True, start_new_session=True)
            pidfd = os.pidfd_open(child.pid, 0); row['lifecycle']['pidfd_closed'] = False
            try:
                row['driver'] = process_identity(child.pid)
            except (FileNotFoundError, ProcessLookupError):
                ended = reaper.peek(child.pid, pidfd)
                need(ended is not None, 'live owned child identity disappeared')
                row['driver'] = {'pid': child.pid, 'exited_before_process_snapshot': True,
                                 'unreaped_kernel_exit': reaper.observed(ended)}
            deadline = time.monotonic() + timeout; poller = select.poll(); poller.register(pidfd, select.POLLIN)
            while True:
                need(recovery or not CANCELLED, 'owned command cancelled')
                need(time.monotonic() < deadline, 'owned command deadline exceeded')
                info = reaper.peek(child.pid, pidfd)
                if info is not None:
                    row['observed_before_reap'] = reaper.observed(info)
                    row['adopted_normal_exit'] = {}
                    self.adoption.reap_exited_adopted(child.pid, reaper.record, row['adopted_normal_exit'], time.monotonic() + 5)
                    break
                need(os.fstat(out.fileno()).st_size <= 256 * 1024**2
                     and os.fstat(err.fileno()).st_size <= 256 * 1024**2, 'owned build log bound exceeded')
                if monitor is not None:
                    monitor(row)
                poller.poll(500)
            need(info.si_code == os.CLD_EXITED and info.si_status == 0, 'owned command exited unsuccessfully')
        except BaseException as exc:
            remember(exc, 'execution')
        finally:
            if reaper.active:
                try:
                    reaper.retire(child, pidfd, row['lifecycle'], remember, time.monotonic() + 30)
                except BaseException as exc:
                    remember(exc, 'retirement')
            if pidfd is not None:
                os.close(pidfd); row['lifecycle']['pidfd_closed'] = True
            for stream in (out, err):
                if stream is not None:
                    stream.flush(); os.fsync(stream.fileno()); stream.close()
            if reaper.active:
                try:
                    reaper.finish()
                except BaseException as exc:
                    remember(exc, 'reaper_finish')
            row['reaper'] = reaper.record
            row['owned_retirement_complete'] = bool(row['lifecycle'].get('child_reaped')
                and row['lifecycle'].get('pidfd_closed') and row['lifecycle'].get('owned_tree_cleanup_complete')
                and row['lifecycle'].get('remaining_owned_children') == []
                and reaper.record.get('final_children_empty') and reaper.record.get('restored'))
            row['finished_ns'] = time.time_ns()
            for key, path in (('stdout', output), ('stderr', error)):
                if path.exists():
                    row[key] = file_ref(path)
            self.records.append(row)
            create(self.directory / (name + '.json'), row)
            print(json.dumps({'command': name, 'returncode': row['lifecycle'].get('returncode'),
                              'owned_retirement_complete': row['owned_retirement_complete'],
                              'errors': row['errors']}), flush=True)
        need(row['owned_retirement_complete'] and not row['errors'], 'owned command failed: ' + name)
        return row


def install_signals():
    def received(number, frame):
        CANCELLED.append({'signal': number, 'observed_ns': time.time_ns()})
    signal.signal(signal.SIGTERM, received); signal.signal(signal.SIGINT, received)
