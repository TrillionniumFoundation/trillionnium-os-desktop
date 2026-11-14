"""Ordinary direct-child capture; every failure retains the actual reap state."""
import errno
import os
import select
import signal
import subprocess
import time


def capture(argv, *, cwd, env, timeout, input_bytes=None):
    started = time.monotonic()
    child = None
    pidfd = None
    out = err = b''
    row = {'argv': argv, 'cwd': str(cwd), 'pid': None, 'returncode': None,
           'timed_out': False, 'actual_parent_reaped': False,
           'pidfd_exit_observed': False, 'pidfd_poll_mask': None,
           'retirement_known': False, 'forced_termination': False,
           'errors': []}

    def failure(stage, exc):
        nonlocal out, err
        if isinstance(exc, subprocess.TimeoutExpired):
            if isinstance(exc.output, bytes):
                out = exc.output
            if isinstance(exc.stderr, bytes):
                err = exc.stderr
        row['errors'].append({'stage': stage, 'type': type(exc).__name__,
                              'errno': getattr(exc, 'errno', None),
                              'message': str(exc)})

    def send(sig):
        if child is None or child.poll() is not None:
            return
        try:
            if pidfd is not None:
                signal.pidfd_send_signal(pidfd, sig)
            else:
                # This is the still-unreaped Popen child, never an adopted PID.
                # Failure to obtain a PIDFD always prevents qualification.
                child.send_signal(sig)
        except ProcessLookupError:
            pass

    try:
        child = subprocess.Popen(argv, cwd=cwd, env=env,
                                 stdin=subprocess.PIPE if input_bytes is not None else subprocess.DEVNULL,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                 close_fds=True)
        row['pid'] = child.pid
        try:
            pidfd = os.pidfd_open(child.pid, 0)
        except BaseException as exc:
            failure('pidfd_open', exc)
            raise
        try:
            out, err = child.communicate(input=input_bytes, timeout=timeout)
        except subprocess.TimeoutExpired as exc:
            row['timed_out'] = True
            failure('communicate_deadline', exc)
            raise
    except BaseException as exc:
        if not row['errors']:
            failure('start_or_communicate', exc)
    finally:
        if child is not None and child.poll() is None:
            row['forced_termination'] = True
            for sig, seconds in ((signal.SIGTERM, 5), (signal.SIGKILL, 5)):
                try:
                    send(sig)
                    out, err = child.communicate(timeout=seconds)
                    break
                except BaseException as exc:
                    failure('retire_' + str(int(sig)), exc)
            # A final timeout remains unknown. Never infer that kill delivery
            # or a missing result is equivalent to an actual child reap.
        elif child is not None:
            try:
                # On a PIDFD setup exception, drain a child which has already
                # exited instead of losing its terminal stdout/stderr.
                if child.stdout is not None and not child.stdout.closed:
                    out, err = child.communicate(timeout=1)
            except BaseException as exc:
                failure('terminal_drain', exc)
        if child is not None:
            row['returncode'] = child.returncode
            row['actual_parent_reaped'] = child.returncode is not None
        if pidfd is not None:
            try:
                poll = select.poll()
                poll.register(pidfd, select.POLLIN)
                events = poll.poll(0)
                mask = 0
                for fd, event in events:
                    if fd != pidfd:
                        raise RuntimeError('unexpected poll object')
                    mask |= event
                row['pidfd_poll_mask'] = mask
                row['pidfd_exit_observed'] = bool(mask & select.POLLIN) and not bool(
                    mask & (select.POLLERR | select.POLLNVAL))
            except BaseException as exc:
                failure('pidfd_terminal_poll', exc)
            finally:
                os.close(pidfd)
        row['retirement_known'] = row['actual_parent_reaped'] and row['pidfd_exit_observed']
        row['elapsed_seconds'] = time.monotonic() - started
    return row, out, err
