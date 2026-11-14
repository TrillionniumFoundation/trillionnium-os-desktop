"""Fresh Native command ownership; no inherited host, PID, lock or resource authority."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import signal
import stat
import subprocess
import sys
import time
CANCELLED = []

def need(value, message):
    if not value:
        raise RuntimeError(message)

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

def load_module(path):
    name = 'owned_' + Path(path).stem
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec); sys.modules[name] = module; spec.loader.exec_module(module)
    return module

def process_identity(pid):
    root = Path('/proc') / str(pid)
    raw = (root / 'stat').read_text()
    return {'pid': pid, 'start_ticks': int(raw[raw.rfind(')') + 2:].split()[19]),
            'exe': os.readlink(root / 'exe'), 'cgroup': (root / 'cgroup').read_text(),
            'argv': [s.decode('utf-8', 'strict') for s in (root / 'cmdline').read_bytes().split(b'\0') if s]}

def initial_process_observation(pid, pidfd, reaper):
    # /proc/PID/exe disappears during exit before WNOWAIT necessarily reports
    # a waitable child. Keep the same PIDFD and unreaped child while closing
    # that short observation gap. This does not qualify the executed argv.
    deadline = time.monotonic() + 0.5
    poller = select.poll(); poller.register(pidfd, select.POLLIN)
    while True:
        try:
            return process_identity(pid)
        except (FileNotFoundError, ProcessLookupError):
            ended = reaper.peek(pid, pidfd)
            if ended is not None:
                return {'pid': pid, 'exited_before_process_snapshot': True,
                        'unreaped_kernel_exit': reaper.observed(ended)}
            need(time.monotonic() < deadline,
                 'owned process identity and kernel exit remained unavailable')
            poller.poll(10)

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
            row['driver'] = initial_process_observation(child.pid, pidfd, reaper)
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
