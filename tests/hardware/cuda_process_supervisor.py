"""Linux process watchdog for disposable CUDA/NVRTC workers (no GPU logic).

Keep the worker group leader UNREAPED until its group has been inspected and
signalled. Reaping first allows the numeric PID/PGID to be recycled, so a
subsequent killpg could affect an unrelated process group. A GPU timeout is
always an unknown effect, never proof that the device was reset.
"""
import math
import os
import signal
import subprocess
import sys
import time


def available():
    return (sys.platform.startswith('linux') and hasattr(os, 'killpg')
            and hasattr(os, 'waitid') and hasattr(os, 'WNOWAIT')
            and os.path.isdir('/proc'))


def _wait_unreaped(process, timeout):
    """Observe child exit without releasing its PID/PGID until cleanup ends."""
    deadline = time.monotonic() + timeout
    flags = os.WEXITED | os.WNOWAIT | os.WNOHANG
    while True:
        # Unlike Popen.wait() or Popen.poll(), WNOWAIT preserves the zombie
        # leader and prevents its numeric process-group identity being reused.
        result = os.waitid(os.P_PID, process.pid, flags)
        if result is not None:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(process.args, timeout)
        time.sleep(min(0.01, remaining))


def _other_group_members(leader_pid):
    """Detect non-leader group members while the leader's PID is still owned.

    None means the procfs inspection could not complete; never accept success
    after a failed inspection. /proc stat's pgrp is field five, after comm.
    """
    try:
        with os.scandir('/proc') as entries:
            for entry in entries:
                if not entry.name.isascii() or not entry.name.isdecimal():
                    continue
                if int(entry.name) == leader_pid:
                    continue
                try:
                    with open(f'/proc/{entry.name}/stat', encoding='ascii') as handle:
                        data = handle.read(4096)
                except FileNotFoundError:
                    continue  # process exited during enumeration
                except OSError:
                    return None
                end = data.rfind(')')
                if end < 0:
                    return None
                fields = data[end + 1:].split()
                if len(fields) < 3:
                    return None
                try:
                    if int(fields[2]) == leader_pid:
                        return True
                except ValueError:
                    return None
    except OSError:
        return None
    return False


def _kill_anchored_group(process, record):
    """Signal only while our child remains alive or WNOWAIT-unreaped."""
    if not os.path.exists(f'/proc/{process.pid}/stat'):
        record['worker_identity_lost'] = True
        return
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    except OSError as exc:
        record['worker_group_kill_error'] = str(exc)


def _reap(process, record):
    try:
        status = process.wait(timeout=0.25)
        record.update(worker_reaped=True, worker_exit_code=status)
        return status
    except subprocess.TimeoutExpired:
        record['unreaped_worker_may_remain'] = True
        return None


def run_worker(argv, timeout_seconds):
    """Run one isolated worker, fail closed on timeout or orphan processes.

    Return (worker exit code, record); 124 means timeout, 125 means a group
    member/identity problem. This is no device-level recovery attestation.
    """
    if not available() or not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
        raise ValueError('OS-supervised positive finite timeout unavailable')
    if not isinstance(argv, (list, tuple)) or not argv or any(
        not isinstance(item, str) or '\x00' in item for item in argv
    ):
        raise ValueError('worker must be nonempty argument-vector strings')
    process = subprocess.Popen(
        list(argv), start_new_session=True, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
    )
    record = {'supervisor': 'linux_waitid_wnowait_killpg',
              'worker_pid': process.pid, 'timeout_seconds': timeout_seconds,
              'worker_reaped': False, 'worker_exit_code': None,
              'timed_out': False, 'effect_result_known': False,
              'device_reset_verified': False}
    try:
        _wait_unreaped(process, timeout_seconds)
        # At this point the leader is an unreaped zombie. An unrelated group
        # cannot reuse its ID while we probe and signal the original group.
        others = _other_group_members(process.pid)
        if others is None:
            record['worker_group_inspection_failed'] = True
        elif others:
            record['worker_group_incomplete'] = True
        # Always kill the anchored group before reaping its leader: a child
        # could fork after the inspection but before cleanup. SIGKILL on an
        # already exited lone leader is harmless.
        _kill_anchored_group(process, record)
        status = _reap(process, record)
        if (status is None or others is not False
                or record.get('worker_group_kill_error')
                or record.get('worker_identity_lost')):
            return 125, record
        return status, record
    except subprocess.TimeoutExpired:
        record['timed_out'] = True
        _kill_anchored_group(process, record)
        try:
            process.kill()
        except ProcessLookupError:
            pass
        _reap(process, record)
        return 124, record
    except BaseException:
        _kill_anchored_group(process, record)
        try:
            process.kill()
        except ProcessLookupError:
            pass
        _reap(process, record)
        raise
