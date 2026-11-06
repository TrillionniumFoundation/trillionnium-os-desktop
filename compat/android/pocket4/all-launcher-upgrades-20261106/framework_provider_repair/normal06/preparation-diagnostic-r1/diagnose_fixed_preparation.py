#!/usr/bin/env python3
"""Read the exact build07 preparation once; never call a build entrypoint."""
import errno
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import stat
import sys
import time

CONTROLLER = Path('/home/alex/work/pocket4-metadata-generation-r8-20261104/native-owned-01/typed-ingress-framework-systemui-provider-build-07-20261106/control-source/framework_build.py')
CONTROLLER_BYTES = 68088
CONTROLLER_SHA = 'c446be88a61f7d07c05aff1e3f3bb967bcf969b7fa3de568eb3de4915e59e7da'
PREPARATION_SHA = 'ab286f3939acfeb648a716ca15e5df348fef6b7007eb5651735fe8a7bda96b1c'
PRIOR_JOB = '1a1b20bbc0a-fc05-7c2e'
PRIOR_TERMINAL_SHA = '22c315979504854e249d059762a2ef008fc278c93b26c4a2bd65e0ba0a68bc34'
STAT = ('st_dev', 'st_ino', 'st_mode', 'st_uid', 'st_gid', 'st_nlink', 'st_size', 'st_mtime_ns', 'st_ctime_ns')
DEADLINE_SECONDS = 150


def need(value, message):
    if not value:
        raise RuntimeError(message)


def fixed_source():
    owned = []
    try:
        parent = os.open('/', os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        owned.append(parent)
        for name in CONTROLLER.parts[1:-1]:
            parent = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
            owned.append(parent)
        fd = os.open(CONTROLLER.name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=parent)
        owned.append(fd)
        first = os.fstat(fd)
        need(stat.S_ISREG(first.st_mode) and first.st_nlink == 1 and first.st_uid == 1000 and
             not first.st_mode & 0o022 and first.st_size == CONTROLLER_BYTES, 'FIXED_CONTROLLER_METADATA')
        data = bytearray()
        while len(data) <= CONTROLLER_BYTES:
            part = os.read(fd, min(65536, CONTROLLER_BYTES + 1 - len(data)))
            if not part:
                break
            data.extend(part)
        last = os.fstat(fd)
        current = os.stat(CONTROLLER.name, dir_fd=parent, follow_symlinks=False)
        need(len(data) == CONTROLLER_BYTES and hashlib.sha256(data).hexdigest() == CONTROLLER_SHA and
             all(getattr(first, key) == getattr(last, key) == getattr(current, key) for key in STAT),
             'FIXED_CONTROLLER_BYTES_OR_PATH_CHANGED')
        return bytes(data), {'path': str(CONTROLLER), 'bytes': len(data), 'sha256': CONTROLLER_SHA,
            'identity': {key: str(getattr(first, key)) if key.endswith('_ns') else getattr(first, key) for key in STAT}}
    finally:
        for fd in reversed(owned):
            os.close(fd)


def census():
    found = {}
    for name in os.listdir('/proc/self/fd'):
        try:
            fd = int(name)
            row = os.fstat(fd)
            found[name] = {'target': os.readlink('/proc/self/fd/' + name),
                'identity': [row.st_dev, row.st_ino, row.st_mode, row.st_uid, row.st_gid, row.st_nlink],
                'fd_flags': fcntl.fcntl(fd, fcntl.F_GETFD), 'file_flags': fcntl.fcntl(fd, fcntl.F_GETFL)}
        except OSError as error:
            if error.errno not in (errno.EBADF, errno.ENOENT):
                raise
    return found


def own_children():
    result = []
    for thread in os.listdir('/proc/self/task'):
        raw = (Path('/proc/self/task') / thread / 'children').read_text('ascii')
        result.extend(int(value) for value in raw.split())
    return sorted(set(result))


def failure(error):
    stack = []
    current = error.__traceback__
    while current is not None:
        code = current.tb_frame.f_code
        stack.append({'file': code.co_filename, 'function': code.co_name, 'line': current.tb_lineno})
        current = current.tb_next
    need(len(stack) <= 64, 'BOUNDED_TRACEBACK')
    return {'type': type(error).__name__, 'repr': repr(error), 'errno': getattr(error, 'errno', None),
        'filename': str(error.filename) if getattr(error, 'filename', None) is not None else None,
        'filename2': str(error.filename2) if getattr(error, 'filename2', None) is not None else None,
        'traceback': stack}


def main():
    need(sys.argv[1:] == ['--verify-prepared-once'], 'EXACT_DIAGNOSTIC_ARGUMENTS')
    need(os.getuid() == os.geteuid() == 1000, 'ORIGINAL_UNPRIVILEGED_OPERATOR_ONLY')
    before = census()
    need(set(before) == {'0', '1', '2'}, 'INITIAL_STDIO_ONLY')
    children_before = own_children()
    need(not children_before, 'NO_PREEXISTING_OWNED_CHILDREN')
    opened = 0
    blocked = []
    denied_events = {'subprocess.Popen', 'os.system', 'os.fork', 'os.forkpty', 'os.posix_spawn',
        'os.posix_spawnp', 'os.exec', 'os.kill', 'os.killpg', 'os.mkdir', 'os.rmdir', 'os.remove',
        'os.rename', 'os.link', 'os.symlink', 'os.truncate', 'os.chmod', 'os.chown', 'os.utime',
        'os.setxattr', 'os.removexattr', 'fcntl.flock', 'fcntl.lockf'}
    write_flags = os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND

    def audit(event, args):
        nonlocal opened
        rejected = event in denied_events or event.startswith('socket.')
        if event == 'open':
            opened += 1
            mode, flags = args[1], args[2]
            rejected = bool((isinstance(mode, str) and any(x in mode for x in 'wax+')) or
                            (isinstance(flags, int) and flags & write_flags))
        if rejected:
            blocked.append({'event': event})
            raise RuntimeError('READONLY_DIAGNOSTIC_REJECTED_EVENT:' + event)

    def alarm(signum, frame):
        raise TimeoutError('fixed preparation diagnostic deadline')

    sys.addaudithook(audit)
    previous_handler = signal.signal(signal.SIGALRM, alarm)
    signal.setitimer(signal.ITIMER_REAL, DEADLINE_SECONDS)
    started = time.monotonic()
    result = {'schema': 'pocket4-fixed-build07-readonly-preparation-diagnosis-v1',
        'prior_job_id': PRIOR_JOB, 'prior_fence_terminal_sha256': PRIOR_TERMINAL_SHA,
        'controller_path': str(CONTROLLER), 'controller_sha256': CONTROLLER_SHA,
        'preparation_sha256': PREPARATION_SHA, 'verify_prepared_called': False,
        'verify_prepared_returned': False, 'observed_failure': None, 'secondary_errors': [],
        'build_entrypoint_called': False, 'Main_commands': 0, 'Android_commands': 0,
        'compiler_commands': 0, 'guard_or_lock_calls': 0, 'source_mutations': 0,
        'original_failure_rewritten': False, 'automatic_retry': False,
        'production_ready': False, 'cleanup_eligible': False}
    source_pin = None
    try:
        raw, source_pin = fixed_source()
        scope = {'__name__': 'fixed_build07_readonly_preparation_only', '__file__': str(CONTROLLER)}
        exec(compile(raw, str(CONTROLLER), 'exec'), scope, scope)
        need(scope['PREPARATION_SHA'] == PREPARATION_SHA and
             str(scope['HERE'] / 'framework_build.py') == str(CONTROLLER), 'FIXED_PREPARATION_BINDING')
        result['verify_prepared_called'] = True
        scope['verify_prepared'](PREPARATION_SHA)
        result['verify_prepared_returned'] = True
    except BaseException as error:
        result['observed_failure'] = failure(error)
    finally:
        try:
            unused, after_pin = fixed_source()
            need(source_pin is not None and source_pin == after_pin, 'CONTROLLER_IDENTITY_CHANGED_AFTER_DIAGNOSIS')
            result['controller_pin'] = after_pin
        except BaseException as error:
            result['secondary_errors'].append({'phase': 'source_after', 'error': failure(error)})
        try:
            children_after = own_children()
            after = census()
            result['children_before'] = children_before
            result['children_after'] = children_after
            result['fd_before'] = before
            result['fd_after'] = after
            need(not children_after, 'OWNED_CHILDREN_AFTER_READONLY_DIAGNOSIS')
            need(before == after, 'READONLY_DIAGNOSIS_CHANGED_FD_IDENTITIES')
            result['all_owned_descriptors_closed'] = True
        except BaseException as error:
            result['secondary_errors'].append({'phase': 'resource_closure', 'error': failure(error)})
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous_handler)
    result['blocked_events'] = blocked
    result['observed_open_audit_events'] = opened
    result['seconds'] = time.monotonic() - started
    result['diagnosis_completed'] = result['verify_prepared_called'] and not result['secondary_errors'] and not blocked
    result['state'] = ('PREPARATION_READ_FAILED' if result['observed_failure'] else 'PREPARATION_READ_PASSED') if result['diagnosis_completed'] else 'DIAGNOSIS_FAILED'
    raw = json.dumps(result, sort_keys=True, ensure_ascii=True)
    need(len(raw.encode()) <= 32768, 'BOUNDED_DIAGNOSTIC_RESULT')
    print(raw, flush=True)
    return 0 if result['diagnosis_completed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
