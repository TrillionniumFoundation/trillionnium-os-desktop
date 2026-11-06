#!/usr/bin/python3 -I
"""Droidloom unshare compatibility with an owned kernel parent-death chain.

Keep the Python launcher PID/executable used by the native supervisor.  The
supervisor's existing forced-stop fallback must kill this exact launcher, not
its process group.  Its directly owned unshare child then receives SIGKILL from
the kernel; unshare --kill-child=KILL retires its own namespace PID 1.

This does not emulate native --forward-signals support.  On older util-linux,
SIGTERM forwarded to a --fork parent may remain blocked until the supervisor's
existing forced-stop fallback.  We do not claim graceful Android shutdown.
"""
import ctypes
import errno
import os
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
NATIVE_UNSHARE = '/usr/bin/unshare'
PR_SET_PDEATHSIG = 1
PR_GET_PDEATHSIG = 2
FORWARDED = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP, signal.SIGQUIT)
# util-linux v2.41.5 uses getopt_long with a leading '+': parsing stops at the
# first command word.  Preserve command arguments and option values verbatim.
LONG_VALUE = frozenset(('map-user', 'map-users', 'map-group', 'map-groups',
                       'propagation', 'setgroups', 'setuid', 'setgid', 'root',
                       'wd', 'monotonic', 'boottime', 'load-interp'))
SHORT_VALUE = frozenset(('-R', '-w', '-S', '-G', '-l'))
_libc = ctypes.CDLL(None, use_errno=True)
_prctl = _libc.prctl
_prctl.argtypes = (ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
                  ctypes.c_ulong, ctypes.c_ulong)
_prctl.restype = ctypes.c_int


def normalise_arguments(arguments):
    """Lower unsupported forwarding only before the native command boundary."""
    if not isinstance(arguments, (list, tuple)) or len(arguments) > 256:
        raise ValueError('ARGUMENT_COUNT')
    if any(not isinstance(arg, str) or '\x00' in arg or len(arg.encode()) > 8192
           for arg in arguments):
        raise ValueError('ARGUMENT_SHAPE')
    result, forward_count, kill_count = [], 0, 0
    index = 0
    while index < len(arguments):
        arg = arguments[index]
        if arg == '--' or not arg.startswith('-') or arg == '-':
            result.extend(arguments[index:])
            break
        if arg == '--forward-signals':
            forward_count += 1
        elif arg == '--kill-child' or arg.startswith('--kill-child='):
            kill_count += 1
            if arg not in ('--kill-child', '--kill-child=TERM', '--kill-child=KILL'):
                raise ValueError('UNREVIEWED_CHILD_DEATH_SIGNAL')
            result.append('--kill-child=KILL')
        else:
            result.append(arg)
            if ((arg.startswith('--') and '=' not in arg and arg[2:] in LONG_VALUE)
                    or arg in SHORT_VALUE):
                index += 1
                if index == len(arguments):
                    raise ValueError('MISSING_NATIVE_OPTION_VALUE')
                result.append(arguments[index])
        index += 1
    if forward_count > 1 or kill_count > 1:
        raise ValueError('DUPLICATE_LIFECYCLE_OPTIONS')
    if forward_count and kill_count != 1:
        raise ValueError('FORWARDING_REQUIRES_EXPLICIT_CHILD_DEATH_CONTRACT')
    return result


def arm_owned_child(expected_parent):
    """Runs in Popen's single-threaded fork child, before its native exec."""
    if expected_parent <= 1:
        raise OSError(errno.ECHILD, 'UNOWNED_PARENT')
    if _prctl(PR_SET_PDEATHSIG, int(signal.SIGKILL), 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'SET_PARENT_DEATH_SIGNAL')
    # The parent may have died between fork and prctl.  Do not execute any
    # namespace operation after adoption by another parent/subreaper.
    if os.getppid() != expected_parent:
        raise OSError(errno.ECHILD, 'PARENT_CHANGED_BEFORE_EXEC')
    actual = ctypes.c_int()
    address = ctypes.cast(ctypes.byref(actual), ctypes.c_void_p).value
    if _prctl(PR_GET_PDEATHSIG, address, 0, 0, 0) != 0 or actual.value != signal.SIGKILL:
        raise OSError(errno.EIO, 'PARENT_DEATH_SIGNAL_NOT_ARMED')


def run(arguments):
    if not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
        raise RuntimeError('OWNED_PIDFD_SUPPORT_REQUIRED')
    native_arguments = normalise_arguments(arguments)
    parent = os.getpid()
    # preexec_fn forces fork here.  This standalone wrapper creates no threads;
    # the libc function is resolved before fork, and the child does not acquire
    # Python-side locks or start another interpreter.
    child = subprocess.Popen([NATIVE_UNSHARE, *native_arguments], close_fds=True,
                             preexec_fn=lambda: arm_owned_child(parent))
    child_fd = None
    previous = {}
    try:
        # An unreaped direct child cannot have its PID reused.  Thereafter all
        # forwarding and error cleanup use this pidfd, never a numeric PID/PGID.
        child_fd = os.pidfd_open(child.pid, 0)

        def forward(signum, _frame):
            try:
                signal.pidfd_send_signal(child_fd, signum, None, 0)
            except ProcessLookupError:
                pass

        for signum in FORWARDED:
            previous[signum] = signal.signal(signum, forward)
        while True:
            try:
                return child.wait()
            except InterruptedError:
                continue
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        try:
            if child.returncode is None and child_fd is not None:
                try:
                    signal.pidfd_send_signal(child_fd, signal.SIGKILL, None, 0)
                except ProcessLookupError:
                    pass
                child.wait(timeout=2)
        finally:
            if child_fd is not None:
                os.close(child_fd)
        # If pidfd acquisition failed, exiting this wrapper still invokes the
        # already armed kernel death link.  There is no PID-based fallback.


def main():
    try:
        rc = run(sys.argv[1:])
        return rc if rc >= 0 else 128 - rc
    except Exception as error:
        print('droidloom unshare compatibility: ' + type(error).__name__ + ': ' + str(error)[:180],
              file=sys.stderr, flush=True)
        return 125


if __name__ == '__main__':
    raise SystemExit(main())
