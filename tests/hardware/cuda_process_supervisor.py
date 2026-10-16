"""Bounded, CPU-only Linux process supervisor for CUDA/NVRTC worker CLIs.

Never treats SIGALRM/Python cancellation as a native-call deadline. It
quarantines a worker in its own process session; a timed-out device effect is
unknown even if the process was killed and reaped. No GPU controls here.
"""
import math
import os
import signal
import subprocess
import sys


def available():
    return sys.platform.startswith('linux') and hasattr(os, 'killpg')


def run_worker(argv, timeout_seconds):
    """Return (exitcode, record), or a deadline record with exitcode=124.

    A timeout is always a failure. A child which resists SIGKILL is never
    described as reaped/safely reset. No unbounded output or shell execution.
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
    record = {'supervisor': 'linux_start_new_session_killpg',
              'worker_pid': process.pid, 'timeout_seconds': timeout_seconds,
              'worker_reaped': False, 'worker_exit_code': None,
              'timed_out': False, 'effect_result_known': False,
              'device_reset_verified': False}
    try:
        code = process.wait(timeout=timeout_seconds)
        record.update(worker_reaped=True, worker_exit_code=code)
        return code, record
    except subprocess.TimeoutExpired:
        record['timed_out'] = True
        # Kill the entire owned worker group. Never target the caller's group.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.kill()
        except ProcessLookupError:
            pass
        try:
            code = process.wait(timeout=0.25)
            record.update(worker_reaped=True, worker_exit_code=code)
        except subprocess.TimeoutExpired:
            # A driver stuck in uninterruptible kernel sleep may resist even
            # SIGKILL. The worker effect and lifetime remain UNKNOWN.
            record['unreaped_worker_may_remain'] = True
        return 124, record
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.kill()
        except ProcessLookupError:
            pass
        try:
            code = process.wait(timeout=0.25)
            record.update(worker_reaped=True, worker_exit_code=code)
        except subprocess.TimeoutExpired:
            record['unreaped_worker_may_remain'] = True
        raise
