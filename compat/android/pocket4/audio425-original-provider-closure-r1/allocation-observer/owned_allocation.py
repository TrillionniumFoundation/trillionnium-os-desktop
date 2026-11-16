"""Bounded, complete du observations of an explicit one or two owned roots.

A nonzero or partial scan is never an allocation measurement. Only a complete
exit-zero scan of every unchanged required root identity can satisfy the caller's gate.
The caller supplies the unchanged disk/memory/cancellation checkpoint.
"""
import ctypes
import hashlib
import json
import math
import os
from pathlib import Path
import select
import signal
import stat
import subprocess
import time

MAX_ATTEMPTS = 3
TOTAL_DEADLINE_SECONDS = 30
LOG_LIMIT_BYTES = 4 * 1024**2


def need(value, message):
    if not value:
        raise RuntimeError(message)


def stable_directory(info):
    return [info.st_dev, info.st_ino, info.st_mode, info.st_uid, info.st_gid]


def file_identity(info):
    return [getattr(info, key) for key in ('st_dev', 'st_ino', 'st_mode', 'st_uid',
            'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')]


def held_reference(fd, path, maximum, *, single_link=True, contents=False):
    path = Path(path); before = os.fstat(fd)
    need(stat.S_ISREG(before.st_mode) and (not single_link or before.st_nlink == 1)
         and 0 <= before.st_size <= maximum, 'bounded regular observer input required')
    digest = hashlib.sha256(); size = 0; chunks = []
    while True:
        block = os.pread(fd, min(1024**2, maximum + 1 - size), size)
        if not block:
            break
        size += len(block)
        need(size <= maximum, 'observer input grew beyond bound')
        digest.update(block)
        if contents:
            chunks.append(block)
    need(size == before.st_size and file_identity(before) == file_identity(os.fstat(fd)) ==
         file_identity(path.lstat()), 'held observer input changed')
    ref = {'path': str(path), 'bytes': size, 'sha256': digest.hexdigest()}
    return (ref, b''.join(chunks)) if contents else ref


def reference(path, maximum=LOG_LIMIT_BYTES, *, contents=False):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        return held_reference(fd, path, maximum, contents=contents)
    finally:
        os.close(fd)


def system_du_alias():
    # Ubuntu's package-managed du can be a symlink to the uutils executable.
    # Record that exact alias; directory operands remain strictly no-follow.
    path = Path('/usr/bin/du'); info = path.lstat()
    need(info.st_uid == 0 and (stat.S_ISLNK(info.st_mode) or
         (stat.S_ISREG(info.st_mode) and not info.st_mode & 0o022)),
         'du alias must be owned by the system package manager')
    resolved = path.resolve(strict=True)
    need(resolved.is_absolute() and str(resolved).startswith('/usr/'),
         'normal system du resolved outside the system tool tree')
    actual = resolved.lstat()
    need(stat.S_ISREG(actual.st_mode) and actual.st_uid == 0
         and not actual.st_mode & 0o6022, 'resolved du must be an immutable-permission ordinary system executable')
    return {'path': str(path), 'identity': file_identity(info),
            'symlink_target': os.readlink(path) if stat.S_ISLNK(info.st_mode) else None,
            'resolved_path': str(resolved), 'resolved_identity': file_identity(actual)}


def create(path, value):
    raw = (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC, 0o400)
    try:
        view = memoryview(raw)
        while view:
            size = os.write(fd, view); need(size > 0, 'short observer evidence write')
            view = view[size:]
        os.fsync(fd)
    finally:
        os.close(fd)
    return reference(path)


def decode_complete(stdout, operands, *, required_roots=2):
    need(type(stdout) is bytes and stdout.endswith(b'\0'), 'complete NUL-terminated du output required')
    rows = stdout[:-1].split(b'\0'); expected = [os.fsencode(x) for x in operands]
    need(type(required_roots) is int and required_roots in (1, 2)
         and len(rows) == len(expected) == required_roots and len(set(expected)) == required_roots,
         'one complete allocation per distinct root required')
    result = []
    for raw, operand in zip(rows, expected):
        fields = raw.split(b'\t', 1)
        need(len(fields) == 2 and fields[0].isdigit() and fields[1] == operand,
             'du output root or nonnegative byte count differs')
        result.append(int(fields[0]))
    return result


def retryable_disappearance(returncode, stderr):
    # Observed GNU and uutils C-locale diagnostics justify a retry, never a pass.
    if type(returncode) is not int or returncode != 1 or type(stderr) is not bytes:
        return False
    lines = stderr.splitlines()
    return bool(lines) and all(line.startswith((b"/usr/bin/du: cannot access ", b"du: cannot access "))
        and line.endswith(b': No such file or directory') for line in lines)


def _parent_death(parent):
    libc = ctypes.CDLL(None, use_errno=True)
    if libc.prctl(1, signal.SIGKILL, 0, 0, 0) != 0 or os.getppid() != parent:
        os._exit(127)


def run_leaf(argv, executable_fd, directory_fds, directory, deadline, checkpoint):
    """Run and reap exactly one FD-bound leaf executable, also during failures."""
    directory = Path(directory); directory.mkdir(mode=0o700)
    out_path = directory / 'stdout'; err_path = directory / 'stderr'
    row = {'argv': list(argv), 'started_ns': time.time_ns(), 'returncode': None,
           'timed_out': False, 'child_reaped': False, 'pidfd_closed': False,
           'errors': [], 'command_executable_via_held_fd': True}
    child = None; pidfd = None; stdout = None; stderr = None
    try:
        checkpoint()
        stdout = open(out_path, 'xb'); stderr = open(err_path, 'xb')
        parent = os.getpid()
        child = subprocess.Popen(argv, executable='/proc/self/fd/' + str(executable_fd),
            env={'PATH': '/usr/bin:/bin', 'LC_ALL': 'C', 'LANG': 'C'},
            stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
            close_fds=True, pass_fds=(executable_fd, *directory_fds),
            start_new_session=True, preexec_fn=lambda: _parent_death(parent))
        row['pid'] = child.pid
        pidfd = os.pidfd_open(child.pid, 0)
        poller = select.poll(); poller.register(pidfd, select.POLLIN)
        while True:
            checkpoint()
            need(os.fstat(stdout.fileno()).st_size <= LOG_LIMIT_BYTES
                 and os.fstat(stderr.fileno()).st_size <= LOG_LIMIT_BYTES,
                 'allocation observer log bound exceeded')
            if time.monotonic() >= deadline:
                row['timed_out'] = True
                raise RuntimeError('allocation observation total deadline exceeded')
            status = os.waitid(os.P_PIDFD, pidfd, os.WEXITED | os.WNOHANG | os.WNOWAIT)
            if status is not None:
                row['observed_before_reap'] = {'si_code': status.si_code, 'si_status': status.si_status}
                break
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                row['timed_out'] = True
                raise RuntimeError('allocation observation total deadline exceeded')
            poller.poll(max(1, min(200, int(remaining * 1000))))
    except BaseException as error:
        row['errors'].append({'type': type(error).__name__, 'message': str(error)})
    finally:
        if child is not None:
            try:
                if child.poll() is None:
                    if pidfd is not None:
                        signal.pidfd_send_signal(pidfd, signal.SIGKILL)
                    else:
                        # An unreaped Popen child retains this PID; no name scan.
                        child.kill()
                row['returncode'] = child.wait(timeout=5)
                row['child_reaped'] = True
            except BaseException as error:
                row['errors'].append({'stage': 'retirement', 'type': type(error).__name__, 'message': str(error)})
        if pidfd is not None:
            os.close(pidfd); row['pidfd_closed'] = True
        for stream in (stdout, stderr):
            if stream is not None:
                stream.flush(); os.fsync(stream.fileno()); stream.close()
        row['finished_ns'] = time.time_ns()
        for name, path in (('stdout', out_path), ('stderr', err_path)):
            if path.exists():
                try:
                    # Recheck after the child is reaped: its final write may have
                    # raced the last live loop check. Never read an overbound log.
                    row[name] = reference(path, LOG_LIMIT_BYTES)
                except BaseException as error:
                    row[name] = {'path': str(path), 'bytes': path.lstat().st_size,
                                 'qualified_reference': False}
                    row['errors'].append({'stage': 'final_' + name, 'type': type(error).__name__, 'message': str(error)})
        row['record'] = create(directory / 'result.json', row)
    return row


class AllocationObserver:
    def __init__(self, roots, directory, checkpoint, *, deadline_seconds=TOTAL_DEADLINE_SECONDS, required_roots=2):
        need(type(deadline_seconds) in (int, float) and math.isfinite(deadline_seconds)
             and 0 < deadline_seconds <= TOTAL_DEADLINE_SECONDS, 'bounded allocation deadline required')
        need(type(required_roots) is int and required_roots in (1, 2),
             'explicit one-root or two-root contract required')
        self.required_roots = required_roots
        self.roots = tuple(Path(x) for x in roots)
        need(len(self.roots) == required_roots and len(set(self.roots)) == required_roots
             and all(x.is_absolute() for x in self.roots)
             and not any(a in b.parents for a in self.roots for b in self.roots if a != b),
             'exact required number of absolute nonoverlapping allocation roots required')
        self.directory = Path(directory); self.directory.mkdir(mode=0o700)
        self.checkpoint = checkpoint; self.deadline_seconds = deadline_seconds
        self.fds = []; self.identities = []; self.records = []; self.du_fd = None
        try:
            for path in self.roots:
                fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
                self.fds.append(fd); info = os.fstat(fd)
                need(stat.S_ISDIR(info.st_mode) and info.st_uid == os.geteuid(),
                     'allocation root must be an owned real directory')
                self.identities.append(stable_directory(info))
            self.du_alias = system_du_alias()
            self.du_fd = os.open(self.du_alias['resolved_path'], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            self.du_ref = held_reference(self.du_fd, self.du_alias['resolved_path'], 128 * 1024**2,
                                         single_link=False)
            self.verify_executable()
            self.operands = ['/proc/self/fd/' + str(fd) for fd in self.fds]
            self.verify_roots()
        except BaseException:
            self.close(); raise

    def close(self):
        for fd in self.fds:
            os.close(fd)
        self.fds = []
        if self.du_fd is not None:
            os.close(self.du_fd); self.du_fd = None

    def verify_roots(self):
        need(len(self.fds) == self.required_roots, 'allocation root descriptors are not held')
        for path, fd, expected in zip(self.roots, self.fds, self.identities):
            need(stable_directory(os.fstat(fd)) == expected == stable_directory(path.lstat()),
                 'allocation root identity changed')

    def _checkpoint(self):
        self.verify_roots(); self.checkpoint()

    def verify_executable(self):
        need(system_du_alias() == self.du_alias
             and file_identity(os.fstat(self.du_fd)) == self.du_alias['resolved_identity']
             and held_reference(self.du_fd, self.du_alias['resolved_path'], 128 * 1024**2,
                                single_link=False) == self.du_ref,
             'package alias or held du executable bytes/identity changed')

    def observe(self):
        number = len(self.records)
        directory = self.directory / ('observation-%05d' % number); directory.mkdir(mode=0o700)
        row = {'schema': 'owned-complete-allocation-observation-v1', 'state': 'STARTED',
               'started_ns': time.time_ns(), 'roots': [str(x) for x in self.roots],
               'root_identities': self.identities, 'required_root_count': self.required_roots,
               'du_executable': self.du_ref,
               'du_package_alias': self.du_alias,
               'timeout_seconds': self.deadline_seconds, 'maximum_attempts': MAX_ATTEMPTS,
               'attempts': [], 'complete': False, 'partial_output_accepted': False, 'errors': []}
        deadline = time.monotonic() + self.deadline_seconds
        try:
            self._checkpoint()
            self.verify_executable()
            argv = ['/usr/bin/du', '--summarize', '--one-file-system', '--block-size=1',
                    '--null', '--dereference-args', '--', *self.operands]
            for attempt in range(MAX_ATTEMPTS):
                need(time.monotonic() < deadline, 'allocation observation total deadline exceeded')
                command = run_leaf(argv, self.du_fd, tuple(self.fds), directory / ('attempt-%d' % attempt),
                                   deadline, self._checkpoint)
                row['attempts'].append(command)
                need(command['child_reaped'] and command['pidfd_closed'] and not command['errors'],
                     'allocation observer command or retirement failed')
                self._checkpoint()
                captured = {}
                for name in ('stdout', 'stderr'):
                    actual, captured[name] = reference(command[name]['path'], LOG_LIMIT_BYTES, contents=True)
                    need(actual == command[name], 'completed allocation log changed')
                stdout = captured['stdout']; stderr = captured['stderr']
                if command['returncode'] == 0:
                    need(not stderr, 'successful allocation scan has unexpected stderr')
                    counts = decode_complete(stdout, self.operands, required_roots=self.required_roots)
                    row['allocation_by_root_bytes'] = dict(zip(row['roots'], counts))
                    row['allocated_bytes'] = sum(counts)
                    row['complete'] = True; row['state'] = 'COMPLETE'
                    break
                need(retryable_disappearance(command['returncode'], stderr),
                     'non-retryable allocation observation failed; exact stderr retained')
            need(row['complete'], 'allocation observation did not obtain a complete successful scan')
            self.verify_executable()
            self._checkpoint()
        except BaseException as error:
            row['state'] = 'FAILED'
            row['complete'] = False
            row['errors'].append({'type': type(error).__name__, 'message': str(error)})
        finally:
            row['finished_ns'] = time.time_ns()
            ref = create(directory / 'result.json', row)
            self.records.append(ref)
        need(row['complete'] and row['state'] == 'COMPLETE' and not row['errors'],
             'owned allocation observation failed: ' + ref['path'])
        return row['allocated_bytes'], ref
