#!/usr/bin/python3
"""Exact unchanged process ownership helpers from the published full CI runner."""
import os
from pathlib import Path
import signal
import subprocess
import time

class VERIFY:
    @staticmethod
    def need(ok, message):
        if not ok: raise RuntimeError(message)


def owned_children():
    result = set()
    for task in Path('/proc/self/task').iterdir():
        result.update(int(value) for value in (task / 'children').read_text().split())
    return result


def reap_descendants(grace_seconds=3):
    until = time.monotonic() + grace_seconds
    retired = []
    while True:
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                pid = 0
            if not pid:
                break
            retired.append({'pid':pid, 'wait_status':status, 'forced':False})
        children = owned_children()
        if not children:
            return retired
        if time.monotonic() >= until:
            break
        time.sleep(0.02)
    cleanup_until = time.monotonic() + 10
    while owned_children():
        VERIFY.need(time.monotonic() < cleanup_until, 'owned descendants did not retire within cleanup interval')
        for pid in sorted(owned_children()):
            try:
                fd = os.pidfd_open(pid)
            except ProcessLookupError:
                continue
            try:
                signal.pidfd_send_signal(fd, signal.SIGKILL)
            except ProcessLookupError:
                pass
            finally:
                os.close(fd)
            retired.append({'pid':pid, 'forced':True})
        while True:
            try:
                pid, status = os.waitpid(-1, os.WNOHANG)
            except ChildProcessError:
                break
            if not pid:
                break
            retired.append({'pid':pid, 'wait_status':status, 'reaped':True})
        time.sleep(0.02)
    return retired


def interrupted(signum, frame):
    raise TimeoutError('CI controller interrupted by signal ' + str(signum))


def execute_child(argv, cwd, env, out, err, timeout):
    child = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                             stdout=out, stderr=err, start_new_session=True)
    fd = None; start_ticks = None; error = None; cleanup_errors = []; descendants = []
    try:
        fd = os.pidfd_open(child.pid)
        proc = Path('/proc/'+str(child.pid)+'/stat').read_text()
        start_ticks = int(proc[proc.rfind(')')+2:].split()[19])
        child.wait(timeout=timeout)
    except BaseException as failure:
        error = failure
    finally:
        old_signals = {signum:signal.signal(signum,signal.SIG_IGN) for signum in (signal.SIGTERM,signal.SIGINT)}
        try:
            # The direct child's PID cannot be recycled before this parent reaps it.
            if child.returncode is None:
                for signum in (signal.SIGTERM,signal.SIGKILL):
                    try:
                        os.killpg(child.pid,signum)
                    except ProcessLookupError:
                        pass
                    except BaseException as failure:
                        cleanup_errors.append('group signal: '+repr(failure))
                        try:
                            if fd is not None: signal.pidfd_send_signal(fd,signum)
                            else: child.send_signal(signum)
                        except ProcessLookupError: pass
                        except BaseException as nested: cleanup_errors.append('direct signal: '+repr(nested))
                    try:
                        child.wait(timeout=5)
                        break
                    except subprocess.TimeoutExpired:
                        continue
                    except BaseException as failure:
                        cleanup_errors.append('direct wait: '+repr(failure))
                if child.returncode is None:
                    cleanup_errors.append('original child not reaped after finite cleanup')
            try:
                descendants = reap_descendants()
            except BaseException as failure:
                cleanup_errors.append('descendant retirement: '+repr(failure))
        finally:
            if fd is not None: os.close(fd)
            for signum,handler in old_signals.items(): signal.signal(signum,handler)
    return {'pid':child.pid,'start_ticks':start_ticks,'exit_code':child.returncode,
            'original_pidfd_held_until_reaped':fd is not None and child.returncode is not None,
            'actual_child_reaped':child.returncode is not None,'retired_descendants':descendants,
            'owned_descendants_remaining':len(owned_children()),
            'timed_out':isinstance(error,subprocess.TimeoutExpired),
            'error':None if error is None else {'type':type(error).__name__,'message':str(error)},
            'cleanup_errors':cleanup_errors}
