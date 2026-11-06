#!/usr/bin/env python3
"""Pinned root supervisor for one fixed snapshot or one fixed lifecycle control.

No path, argv, PID, namespace, UID, command or Python body can be selected by
the transport. The two embedded source bodies must match these exact pins.
Root signals only children created by this supervisor or their adopted
descendants; the eight protected Main PIDs are explicitly excluded.
"""
import ctypes
import errno
import hashlib
import json
import os
import resource
import signal
import sys
import time

LIFECYCLE_SHA = '7fe6569f6665d6b710d2207c53e631261d6eb922d37e24ddfe5de15b841f0126'
SNAPSHOT_SHA = '7908f4730c658e0d2f43ca66a810eb6d7033634560fcba2d7d928b380795136e'
MODES = frozenset(('before', 'after', 'control-timeout', 'control-escaped', 'control-pidfd'))
OBSERVATION_SECONDS = 15
RETIREMENT_SECONDS = 5


def require(value, reason):
    if not value:
        raise RuntimeError(reason)


def mask_for_retirement(deadline):
    for number in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(number, signal.SIG_IGN)
    def expired(number, frame):
        raise TimeoutError('root owned retirement watchdog')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, max(0.001, deadline - time.monotonic()))


def control_worker(mode):
    if mode == 'control-pidfd':
        time.sleep(30)
        return
    require(mode in ('control-timeout', 'control-escaped'), 'unknown fixed control mode')
    read_end, write_end = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_end)
        if mode == 'control-escaped':
            os.setsid()
        os.write(write_end, b'R')
        os.close(write_end)
        time.sleep(30)
        os._exit(0)
    os.close(write_end)
    try:
        require(os.read(read_end, 1) == b'R', 'fixed control child readiness failed')
    finally:
        os.close(read_end)
    print('READY %d %d' % (os.getpid(), pid), flush=True)
    if mode == 'control-escaped':
        return
    time.sleep(30)


def qualify_control(mode, command, stdout, stderr, error):
    require(error is not None and command['qualified_success'] is False and
            command['child_started'] and command['child_reaped'] and
            command['owned_tree_cleanup_complete'] and command['remaining_owned_children'] == [] and
            command['all_acquired_fds_closed'] and command['retirement_within_deadline'] and
            command['stdout'].get('complete') and command['stderr'].get('complete') and
            stderr == b'', 'negative lifecycle control did not retire all owned resources')
    first = command['first_error']
    allowed_secondary = {'driver_left_descendants'} if mode == 'control-timeout' else set()
    require(all(item['stage'] in allowed_secondary and item['type'] == 'RuntimeError'
                for item in command['secondary_errors']),
            'negative root control encountered an unrelated secondary failure')
    if mode == 'control-pidfd':
        require(isinstance(error, OSError) and error.errno == errno.EMFILE and
                first['stage'] == 'start_or_wait' and first['errno'] == errno.EMFILE and
                command['returncode'] == -signal.SIGKILL and not command['descendants'],
                'pidfd failure control lost errno or direct child cleanup')
    else:
        fields = stdout.decode('ascii', 'strict').strip().split()
        require(len(fields) == 3 and fields[0] == 'READY' and
                int(fields[1]) == command['pid'] and len(command['descendants']) == 1,
                'fixed control readiness/descendant count differs')
        child = command['descendants'][0]
        require(child['pid'] == int(fields[2]) and child['reaped'] and child['pidfd_closed'] and
                os.WIFSIGNALED(child['wait_status']) and
                os.WTERMSIG(child['wait_status']) == signal.SIGKILL,
                'fixed control descendant not independently reaped')
        if mode == 'control-timeout':
            require(isinstance(error, TimeoutError) and command['timed_out'] and
                    command['returncode'] == -signal.SIGKILL and first['stage'] == 'start_or_wait',
                    'timeout control lost its first failure')
        else:
            require(command['returncode'] == 0 and not command['timed_out'] and
                    child['kill_attempted'] and first['stage'] == 'driver_left_descendants',
                    'escaped descendant control accepted an orphan or changed the first error')


def run(packet, entry_started):
    report = {'schema': 1, 'kind': 'fixed-root-main-snapshot-supervisor02',
              'ok': False, 'mode': None, 'snapshot_qualified': False,
              'control_passed': False, 'root_subreaper': None, 'command': None,
              'child_stdout_utf8': None, 'child_stderr_utf8': None,
              'first_error': None, 'secondary_errors': [],
              'watchdog_observation_seconds': OBSERVATION_SECONDS,
              'watchdog_retirement_seconds': RETIREMENT_SECONDS,
              'Main_actions': 0, 'Android_actions': 0, 'service_actions': 0,
              'arbitrary_privileged_commands_supported': False,
              'snapshot_source_changed': False,
              'old_QA_epoch_invalid': True, 'new_QA_epoch_qualified': False,
              'runtime_authorization_enabled': False, 'production_ready': False}
    first = None
    reaper = None
    lifecycle = None
    phase_error = None
    observation_deadline = entry_started + OBSERVATION_SECONDS
    retirement_limit = observation_deadline + RETIREMENT_SECONDS
    final_deadline = retirement_limit

    def remember(error, stage):
        nonlocal first
        item = {'stage': stage, 'type': type(error).__name__,
                'errno': getattr(error, 'errno', None), 'message': str(error)}
        if first is None:
            first = error
            report['first_error'] = item
        else:
            report['secondary_errors'].append(item)

    try:
        require(os.getresuid() == (0, 0, 0), 'fixed root supervisor requires all root UIDs')
        require(type(packet) is dict and set(packet) ==
                {'schema', 'mode', 'root_source', 'lifecycle_source', 'snapshot_source'} and
                type(packet['schema']) is int and packet['schema'] == 1 and packet['mode'] in MODES,
                'fixed root source packet shape differs')
        mode = packet['mode']
        report['mode'] = mode
        report['root_uids'] = list(os.getresuid())
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        libc = ctypes.CDLL(None, use_errno=True)
        prctl = libc.prctl
        prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                         ctypes.c_ulong, ctypes.c_ulong]
        prctl.restype = ctypes.c_int
        require(prctl(4, 0, 0, 0, 0) == 0 and prctl(3, 0, 0, 0, 0) == 0,
                'root supervisor non-dumpable qualification failed')
        report['dumpable'] = 0
        common = packet['lifecycle_source'].encode('utf-8')
        snapshot = packet['snapshot_source'].encode('utf-8')
        require(hashlib.sha256(common).hexdigest() == LIFECYCLE_SHA and
                hashlib.sha256(snapshot).hexdigest() == SNAPSHOT_SHA,
                'root child/lifecycle source pin differs')
        lifecycle = {'__name__': 'pinned_capture_lifecycle',
                     '__file__': '<pinned-capture-lifecycle>'}
        exec(compile(common, 'capture_lifecycle.py', 'exec'), lifecycle, lifecycle)
        # Compile before starting any child; never import a mutable root path.
        snapshot_code = compile(snapshot, 'main_snapshot.py', 'exec')
        reaper = lifecycle['OwnChildReaper'](lifecycle['PROTECTED_PIDS'])
        report['root_subreaper'] = reaper.record
        reaper.begin()
        require(time.monotonic() < observation_deadline, 'root observation budget elapsed before fork')

        def fixed_worker():
            if mode in ('before', 'after'):
                scope = {'__name__': '__main__', '__file__': '<pinned-readonly-main-snapshot>'}
                exec(snapshot_code, scope, scope)
            else:
                control_worker(mode)

        deadline = min(observation_deadline, time.monotonic() + 1) if mode == 'control-timeout' else observation_deadline
        def factory(input_fd, output_fd, error_fd, bound):
            return lifecycle['fork_fixed'](fixed_worker, input_fd, output_fd, error_fd, bound, deadline)

        def denied_pidfd(pid, flags):
            raise OSError(errno.EMFILE, 'explicit fixed-root pidfd allocation control seam')

        command, stdout, stderr, phase_error = lifecycle['invoke_owned'](
            reaper, factory, b'', deadline, retirement_limit, output_bound=65536,
            pidfd_factory=denied_pidfd if mode == 'control-pidfd' else None,
            cleanup_enter=mask_for_retirement, retirement_grace=RETIREMENT_SECONDS)
        report['command'] = command
        report['child_stdout_utf8'] = stdout.decode('utf-8', 'strict') if stdout is not None else None
        report['child_stderr_utf8'] = stderr.decode('utf-8', 'strict') if stderr is not None else None
        if mode.startswith('control-'):
            qualify_control(mode, command, stdout, stderr, phase_error)
            report['control_passed'] = True
        else:
            if phase_error is not None:
                raise phase_error
            require(command['qualified_success'] and command['returncode'] == 0 and stderr == b'',
                    'fixed root snapshot command failed')
            observation = json.loads(stdout.decode('utf-8', 'strict'))
            require(observation.get('ok') is True and observation['old_QA_epoch_invalid'] is True and
                    observation['new_QA_epoch_qualified'] is False and
                    observation['runtime_authorization_enabled'] is False,
                    'fixed snapshot did not qualify its own read')
            report['snapshot_qualified'] = True
    except BaseException as error:
        remember(error, 'root_supervisor')
    finally:
        # No callback after this point can create another child. Keep the same
        # absolute deadline; finishing/restoring the subreaper never grants more time.
        try:
            final_deadline = (report['command']['retirement_deadline'] if report['command'] is not None
                              else min(retirement_limit, time.monotonic() + RETIREMENT_SECONDS))
            mask_for_retirement(final_deadline)
        except BaseException as error:
            remember(error, 'root_final_retirement_signal_guard')
        if reaper is not None:
            try:
                reaper.finish()
            except BaseException as error:
                remember(error, 'root_subreaper_finish')
        try:
            signal.setitimer(signal.ITIMER_REAL, 0)
            report['watchdog_disarmed_after_retirement'] = True
        except BaseException as error:
            remember(error, 'root_watchdog_disarm')
        report['finished_monotonic'] = time.monotonic()
        report['within_absolute_supervisor_deadline'] = report['finished_monotonic'] <= retirement_limit
        report['within_final_retirement_deadline'] = report['finished_monotonic'] <= final_deadline
        if not (report['within_absolute_supervisor_deadline'] and report['within_final_retirement_deadline']):
            remember(TimeoutError('fixed root supervisor exceeded its absolute deadline'), 'root_final_deadline')
        report['ok'] = (first is None and reaper is not None and reaper.record['restored'] and
                        reaper.record['final_children_empty'] and
                        (report['snapshot_qualified'] or report['control_passed']))
    raw = (json.dumps(report, separators=(',', ':')) + '\n').encode('utf-8')
    require(len(raw) <= 131072, 'root supervisor envelope exceeds bound')
    require(sys.stdout.buffer.write(raw) == len(raw), 'root envelope write incomplete')
    sys.stdout.buffer.flush()
    return 0 if report['ok'] else 1
