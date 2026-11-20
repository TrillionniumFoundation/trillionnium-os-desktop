#!/usr/bin/env python3
"""Bounded pipes with the unchanged Pocket4 owned-child retirement authority.

The pipe pump follows checkpoint24 fixture_context.py (Git blob
b0f7bf2a855cff9d09b87be6aeee4fb9e643f990, SHA256
368c68728c9af2feb280661731879545bcdbd1f8d363b8a153fcf8e1d7087b4c).
Retirement and child ownership remain in the independently pinned lifecycle.
This module never limits the size of ordinary files written by a command.
"""
import hashlib
import json
import os
from pathlib import Path
import resource
import selectors
import signal
import stat
import subprocess
import sys
import time
import types

SOURCE_LIFECYCLE_PATH = Path('/usr/libexec/droidloom/native-application-leaves/cohorts/cp3a-20261120-apps-r1/source/main/capture_lifecycle.py')
SOURCE_LIFECYCLE_SHA = '6a0ba9438b10740a593e2d90962420e04868465a0fb55c0ce2e03afdb835e877'
PIPE_SOURCE_SHA = '368c68728c9af2feb280661731879545bcdbd1f8d363b8a153fcf8e1d7087b4c'
_source_lifecycle = None


def require(value, message):
    if not value:
        raise RuntimeError(message)


def load_source_lifecycle():
    global _source_lifecycle
    if _source_lifecycle is not None:
        return _source_lifecycle
    fd = os.open(SOURCE_LIFECYCLE_PATH, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= 1024 * 1024,
                'bounded original lifecycle source required')
        raw = bytearray()
        while True:
            part = os.read(fd, min(65536, 1024 * 1024 + 1 - len(raw)))
            if not part:
                break
            raw.extend(part)
            require(len(raw) <= 1024 * 1024, 'original lifecycle source exceeded bound')
        require(hashlib.sha256(raw).hexdigest() == SOURCE_LIFECYCLE_SHA,
                'original lifecycle source changed')
    finally:
        os.close(fd)
    module = types.ModuleType('pocket4_original_owned_capture')
    module.__file__ = str(SOURCE_LIFECYCLE_PATH)
    exec(compile(bytes(raw), str(SOURCE_LIFECYCLE_PATH), 'exec'), module.__dict__)
    _source_lifecycle = module
    return module


def OwnChildReaper(*args, **kwargs):
    return load_source_lifecycle().OwnChildReaper(*args, **kwargs)


def read_output(fd, bound):
    # Used for the native runner's explicitly bounded, private map receipt.
    return load_source_lifecycle().read_output(fd, bound)


def fork_fixed(worker, input_fd, output_fd, error_fd, output_bound, startup_deadline):
    """Original fixed fork/session handshake, with pipe capture instead of FSIZE.

    The caller still supplies only its fixed native snapshot/control worker.
    All ownership checks, waiting and retirement use the original lifecycle.
    """
    life = load_source_lifecycle()
    sys.stdout.flush()
    sys.stderr.flush()
    pid = os.fork()
    if pid:
        child = life.ForkProcess(pid)
        while True:
            info = life.OwnChildReaper.peek(pid, None)
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
        worker()
        code = 0
    except SystemExit as error:
        code = error.code if type(error.code) is int and 0 <= error.code <= 255 else 1
    except BaseException as error:
        try:
            os.write(2, (json.dumps({'fixed_child_error': type(error).__name__,
                                    'errno': getattr(error, 'errno', None)}) + '\n').encode())
        except BaseException:
            pass
        code = 1
    try:
        sys.stdout.flush()
        sys.stderr.flush()
    except BaseException:
        code = 1
    os._exit(code)


def invoke_owned(reaper, factory, input_bytes, observation_deadline, cleanup_deadline,
                 output_bound=65536, input_bound=196608, pidfd_factory=None,
                 cleanup_enter=None, retirement_grace=None):
    """Capture a fixed child, then prove retirement through the original reaper.

    Each stream stores at most output_bound bytes and observes at most one
    additional byte. The first capture error stops all stream reads. Neither
    a timeout nor cleanup renews the observation deadline.
    """
    life = load_source_lifecycle()
    record = {'schema': 2, 'capture_backend': 'bounded-pipes-v1',
              'source_lifecycle_sha256': SOURCE_LIFECYCLE_SHA,
              'pipe_algorithm_source_sha256': PIPE_SOURCE_SHA,
              'child_started': False, 'child_reaped': False, 'pid': None,
              'returncode': None, 'timed_out': False, 'kill_attempted': False,
              'pidfd_closed': True, 'selector_closed': True,
              'owned_tree_cleanup_complete': False, 'descendants': [],
              'remaining_owned_children': None, 'first_error': None, 'secondary_errors': [],
              'observation_deadline': observation_deadline,
              'retirement_deadline': cleanup_deadline, 'all_acquired_fds_closed': False,
              'input': {'acquired': False, 'closed': True},
              'stdout': {'acquired': False, 'closed': True},
              'stderr': {'acquired': False, 'closed': True}}
    capture = {'policy': 'per-stream-prefix-v1', 'maximum_bytes': output_bound,
               'stored_bytes': {'stdout': 0, 'stderr': 0},
               'observed_bytes': {'stdout': 0, 'stderr': 0},
               'EOF': {'stdout': False, 'stderr': False},
               'limit_exceeded': False, 'no_stream_reads_after_capture_failure': True,
               'RLIMIT_FSIZE_modified': False}
    record['output_capture'] = capture
    first = None
    capture_failed = False
    process = pidfd = selector = input_fd = None
    pidfd_registered = False
    ownership_admitted = False
    pipe_values = {}
    buffers = {'stdout': bytearray(), 'stderr': bytearray()}

    def remember(error, stage):
        nonlocal first, capture_failed
        item = life.safe_error(error, stage)
        if first is None:
            first = error
            record['first_error'] = item
        else:
            record['secondary_errors'].append(item)
        if stage != 'child_exit':
            capture_failed = True

    def close_pipe_end(name, side):
        value = pipe_values[name].get(side)
        if value is None:
            return
        pipe_values[name][side] = None
        try:
            os.close(value)
            record[name][side + '_closed'] = True
        except BaseException as error:
            remember(error, name + '_' + side + '_close')
        record[name]['closed'] = all(record[name].get(key) is True
                                     for key in ('read_closed', 'write_closed'))

    def close_read(name):
        value = pipe_values[name].get('read')
        if selector is not None and value is not None:
            try:
                selector.unregister(value)
            except KeyError:
                pass
            except BaseException as error:
                remember(error, name + '_unregister')
        close_pipe_end(name, 'read')

    try:
        reaper.before_command()
        ownership_admitted = True
        require(time.monotonic() < observation_deadline < cleanup_deadline,
                'owned observation deadline already elapsed')
        require(type(output_bound) is int and output_bound in (33554432, 61516460),
                'bounded output limit required')
        capture['RLIMIT_FSIZE_before'] = list(resource.getrlimit(resource.RLIMIT_FSIZE))
        input_fd = life.sealed_input(input_bytes, input_bound, record['input'], remember)
        selector = selectors.DefaultSelector()
        record['selector_closed'] = False
        record['selector_fd'] = selector.fileno()
        for name in ('stdout', 'stderr'):
            read_fd, write_fd = os.pipe2(os.O_CLOEXEC)
            pipe_values[name] = {'read': read_fd, 'write': write_fd}
            record[name].update({'acquired': True, 'closed': False,
                                 'fd': read_fd, 'write_fd': write_fd,
                                 'read_closed': False, 'write_closed': False})
            os.set_blocking(read_fd, False)
            selector.register(read_fd, selectors.EVENT_READ, name)
        process = factory(input_fd, pipe_values['stdout']['write'],
                          pipe_values['stderr']['write'], output_bound)
        record['child_started'] = True
        record['pid'] = process.pid
        for name in ('stdout', 'stderr'):
            close_pipe_end(name, 'write')
        reaper.signal_target(process.pid)
        pidfd = (pidfd_factory or os.pidfd_open)(process.pid, 0)
        record['pidfd_closed'] = False
        record['pidfd'] = pidfd
        selector.register(pidfd, selectors.EVENT_READ, 'leader')
        pidfd_registered = True
        while not capture_failed:
            now = time.monotonic()
            if now >= observation_deadline:
                raise TimeoutError('owned child exit or output EOF deadline')
            info = reaper.peek(process.pid, pidfd)
            if info is not None and 'observed_before_reap' not in record:
                record['observed_before_reap'] = reaper.observed(info)
                if info.si_code != os.CLD_EXITED or info.si_status != 0:
                    remember(RuntimeError('fixed child did not exit zero'), 'child_exit')
            if info is not None and pidfd_registered:
                selector.unregister(pidfd)
                pidfd_registered = False
            if info is not None and all(capture['EOF'].values()):
                break
            for key, _mask in selector.select(min(0.05, observation_deadline - now)):
                if capture_failed:
                    break
                if time.monotonic() >= observation_deadline:
                    raise TimeoutError('owned output observation deadline')
                name = key.data
                if name == 'leader':
                    continue
                remaining = output_bound - len(buffers[name])
                try:
                    part = os.read(key.fd, min(65536, remaining + 1))
                except BlockingIOError:
                    continue
                if not part:
                    capture['EOF'][name] = True
                    close_read(name)
                    continue
                capture['observed_bytes'][name] += len(part)
                buffers[name].extend(part[:remaining])
                capture['stored_bytes'][name] = len(buffers[name])
                if len(part) > remaining:
                    capture['limit_exceeded'] = True
                    remember(RuntimeError(name + ' exceeded per-stream output bound'),
                             name + '_output_bound')
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
            record['ownership_not_admitted_no_retirement'] = True
        if pidfd is not None:
            try:
                os.close(pidfd)
                record['pidfd_closed'] = True
            except BaseException as error:
                remember(error, 'leader_pidfd_close')
        for name in ('stdout', 'stderr'):
            if name in pipe_values:
                close_read(name)
                close_pipe_end(name, 'write')
        if selector is not None:
            try:
                selector.close()
                record['selector_closed'] = True
            except BaseException as error:
                remember(error, 'selector_close')
        if input_fd is None and record['input']['acquired'] and not record['input']['closed']:
            input_fd = record['input']['fd']
        if input_fd is not None:
            try:
                os.close(input_fd)
                record['input']['closed'] = True
            except BaseException as error:
                remember(error, 'input_close')
        try:
            capture['RLIMIT_FSIZE_after'] = list(resource.getrlimit(resource.RLIMIT_FSIZE))
            require(capture.get('RLIMIT_FSIZE_before') == capture['RLIMIT_FSIZE_after'],
                    'ambient file-size limit changed')
        except BaseException as error:
            remember(error, 'file_size_limit_observation')
        record['all_acquired_fds_closed'] = (record['pidfd_closed'] and record['selector_closed']
            and all(record[name]['closed'] for name in ('input', 'stdout', 'stderr'))
            and all(row['pidfd_closed'] for row in record['descendants']))
        record['finished_monotonic'] = time.monotonic()
        record['retirement_within_deadline'] = record['finished_monotonic'] <= cleanup_deadline
        if not record['retirement_within_deadline']:
            remember(TimeoutError('owned retirement deadline exceeded'), 'retirement_deadline')
        if not (record['child_started'] and record['child_reaped']
                and record['owned_tree_cleanup_complete'] and record['all_acquired_fds_closed']):
            remember(RuntimeError('owned capture lifecycle incomplete'), 'final_lifecycle_gate')
        capture['complete'] = all(capture['EOF'].values()) and not capture_failed
        capture['prefix_only'] = not capture['complete']
        record['qualified_success'] = first is None
    output = {}
    for name in ('stdout', 'stderr'):
        output[name] = bytes(buffers[name]) if record[name]['acquired'] else None
        if output[name] is not None:
            record[name].update({'bytes': len(output[name]),
                'sha256': hashlib.sha256(output[name]).hexdigest(),
                'complete': capture['EOF'][name] and not capture_failed})
    return record, output['stdout'], output['stderr'], first
