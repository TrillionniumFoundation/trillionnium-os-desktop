"""Keep an owned process generation separate from its post-exec command.

The caller must retain its child PIDFD until this observation finishes.  An
initial empty cmdline is evidence of an observation, not a different process.
Every accepted current observation must still match the exact frozen argv.
"""
import hashlib
import os
from pathlib import Path
import re
import stat


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def generation(snapshot):
    need(type(snapshot) is dict, 'process identity must be a dictionary')
    for key in ('pid', 'start_ticks'):
        need(type(snapshot.get(key)) is int and snapshot[key] > 0,
             'strict positive process identity integer required: ' + key)
    for key in ('exe', 'cgroup'):
        need(type(snapshot.get(key)) is str and snapshot[key] and '\0' not in snapshot[key],
             'complete process identity string required: ' + key)
    return {key: snapshot[key] for key in ('pid', 'start_ticks', 'exe', 'cgroup')}


def validate_executed_command(initial, current, expected_argv, expected_executable):
    need(type(expected_executable) is str and expected_executable.startswith('/')
         and '\0' not in expected_executable, 'absolute pinned executable required')
    need(type(expected_argv) is list and expected_argv
         and all(type(arg) is str and '\0' not in arg for arg in expected_argv),
         'complete frozen argv strings required')
    need(expected_argv[0] == expected_executable, 'frozen argv executable differs')
    before = generation(initial); after = generation(current)
    need(before == after, 'owned process generation changed')
    need(after['exe'] == expected_executable, 'observed executable differs from pinned command')
    need(type(current.get('argv')) is list
         and all(type(arg) is str and '\0' not in arg for arg in current['argv'])
         and current['argv'] == expected_argv, 'actual post-exec argv differs from frozen command')
    return after


def validate_temporary_environment(raw, expected_directory):
    """Require actual temporary values after the caller bound argv/exe/PIDFD.

    Empty early /proc data never passes this check. Call it at both existing
    effective-input boundaries, after the real exact post-exec command has
    been observed, rather than at the unqualified first process snapshot.
    Only the two scoped values are returned; unrelated environment is omitted.
    """
    need(type(expected_directory) is str and expected_directory.startswith('/')
         and '\0' not in expected_directory, 'absolute exact temporary directory required')
    need(type(raw) is bytes and 0 < len(raw) <= 1024**2 and raw.endswith(b'\0'),
         'bounded complete actual process environment required')
    expected = expected_directory.encode('utf-8')
    observed = {}
    for item in raw.split(b'\0'):
        key, separator, value = item.partition(b'=')
        if key not in (b'TMPDIR', b'GOTMPDIR'):
            continue
        need(separator == b'=' and key not in observed,
             'duplicate or malformed actual temporary environment')
        observed[key] = value
    need(set(observed) == {b'TMPDIR', b'GOTMPDIR'}
         and all(value == expected for value in observed.values()),
         'actual normal driver temporary directory differs')
    return {key.decode(): value.decode('utf-8') for key, value in observed.items()}


def file_identity(info):
    return [getattr(info, name) for name in ('st_dev', 'st_ino', 'st_mode', 'st_uid',
            'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')]


class PinnedExecutable:
    """Hold the named bytes and require /proc/<owned pid>/exe to be that inode."""
    def __init__(self, reference, maximum=64 * 1024**2):
        need(type(reference) is dict and type(reference.get('path')) is str
             and reference['path'].startswith('/') and '\0' not in reference['path'],
             'absolute executable reference required')
        need(type(maximum) is int and maximum > 0
             and type(reference.get('bytes')) is int and 0 < reference['bytes'] <= maximum,
             'bounded exact executable size required')
        need(type(reference.get('sha256')) is str
             and re.fullmatch('[0-9a-f]{64}', reference['sha256']) is not None,
             'exact executable SHA256 required')
        self.reference = {key: reference[key] for key in ('path', 'bytes', 'sha256')}
        self.maximum = maximum; self.named_fd = None; self.executed_fd = None
        self.identity = None; self.pid = None; self.observations = 0

    def __enter__(self):
        try:
            self.named_fd = os.open(self.reference['path'], os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
            before = os.fstat(self.named_fd)
            need(stat.S_ISREG(before.st_mode) and before.st_nlink == 1
                 and before.st_size == self.reference['bytes'], 'pinned executable file shape differs')
            digest = hashlib.sha256(); size = 0
            while True:
                block = os.read(self.named_fd, 1024**2)
                if not block:
                    break
                size += len(block); need(size <= self.maximum, 'executable exceeded its bound')
                digest.update(block)
            self.identity = file_identity(before)
            self.verify_named()
            need(size == self.reference['bytes'] and digest.hexdigest() == self.reference['sha256'],
                 'actual executable bytes differ from frozen pin')
            return self
        except BaseException:
            self.close()
            raise

    def verify_named(self):
        need(self.named_fd is not None and self.identity is not None, 'executable witness is not held')
        need(file_identity(os.fstat(self.named_fd)) == self.identity
             == file_identity(Path(self.reference['path']).lstat()), 'held executable changed')

    def verify_running(self, pid):
        need(type(pid) is int and pid > 0, 'strict owned PID required')
        need(self.pid in (None, pid), 'executable witness belongs to another PID')
        self.verify_named()
        # This one deliberate procfs magic-link resolution observes the running
        # image.  The separately opened named executable never follows a link.
        actual = os.open('/proc/%d/exe' % pid, os.O_RDONLY | os.O_CLOEXEC)
        try:
            need(file_identity(os.fstat(actual)) == self.identity,
                 'running executable inode differs from held pinned executable')
            if self.executed_fd is None:
                self.executed_fd = actual; actual = None; self.pid = pid
            need(file_identity(os.fstat(self.executed_fd)) == self.identity,
                 'held running executable changed')
            self.observations += 1
        finally:
            if actual is not None:
                os.close(actual)

    def record(self):
        need(self.observations >= 2, 'both executable observation boundaries required')
        self.verify_named()
        return {'schema': 'owned-pinned-executable-observation-v1',
                'executable': dict(self.reference), 'identity': list(self.identity),
                'pid': self.pid, 'boundary_observations': self.observations}

    def close(self):
        for attribute in ('executed_fd', 'named_fd'):
            fd = getattr(self, attribute)
            if fd is not None:
                os.close(fd); setattr(self, attribute, None)

    def __exit__(self, kind, value, traceback):
        try:
            if kind is None:
                self.verify_named()
        finally:
            self.close()
