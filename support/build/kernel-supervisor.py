#!/usr/bin/env python3
"""Supervise a public kernel.sh call and its complete disposable worker group.

The debug runner bypasses this entry with A01_KERNEL_WORKER=1 because its
existing session owner must remain responsible for every inherited descendant.
"""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time


class ShutdownState:
    """Signal handlers record the first request and never unwind ownership."""
    def __init__(self):
        self.first_signal = None

    def handle(self, signum, _frame):
        if self.first_signal is None:
            self.first_signal = signum


@contextmanager
def interruption_handlers():
    previous = {number: signal.getsignal(number) for number in (signal.SIGINT, signal.SIGTERM)}
    state = ShutdownState()
    try:
        for number in previous:
            signal.signal(number, state.handle)
        yield state
    finally:
        for number, handler in previous.items():
            signal.signal(number, handler)


class OwnedWorker:
    """Keep the direct leader unreaped until its group is terminated."""
    def __init__(self, command, *, env, pass_fds=()):
        self.process = subprocess.Popen(command, env=env, start_new_session=True, pass_fds=pass_fds)
        self.reaped = False
        self.external_reap = False
        self.status = None

    def exited(self):
        if self.reaped:
            return True
        if self.external_reap:
            raise RuntimeError("worker was externally reaped; group signals are disarmed")
        try:
            return os.waitid(os.P_PID, self.process.pid,
                             os.WEXITED | os.WNOHANG | os.WNOWAIT) is not None
        except ChildProcessError as error:
            self.external_reap = True
            raise RuntimeError("worker was externally reaped; group signals are disarmed") from error

    def stop(self, grace=0.1):
        if self.reaped or self.external_reap:
            return self.status
        self.exited()
        try:
            os.killpg(self.process.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        deadline = time.monotonic() + grace
        while time.monotonic() < deadline:
            time.sleep(min(0.01, max(0, deadline - time.monotonic())))
        # WNOWAIT retains the leader identity until both group signals have
        # been sent. ECHILD permanently disarms this entry before signaling.
        self.exited()
        try:
            os.killpg(self.process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        self.status = self.process.wait()
        self.reaped = True
        return self.status

    def wait(self, shutdown):
        while not self.exited():
            if shutdown.first_signal is not None:
                break
            time.sleep(0.05)
        return self.stop()


def exit_status(raw_status, shutdown):
    if shutdown.first_signal is not None:
        return 128 + shutdown.first_signal
    return raw_status if raw_status >= 0 else 128 - raw_status


def inherited_descriptors(target, environment):
    if target != "gdb_server":
        return ()
    value = environment.get("A01_GDB_FD", "")
    if not re.fullmatch(r"[0-9]+", value) or not 64 <= int(value) <= 2**31 - 1:
        raise ValueError("gdb_server requires its owned listener descriptor >=64")
    descriptor = int(value)
    os.fstat(descriptor)
    return (descriptor,)


def main():
    target = sys.argv[1] if len(sys.argv) == 2 else ""
    if target not in ("kernel", "run_kernel", "gdb_server"):
        print("usage: kernel-supervisor.py [kernel|run_kernel|gdb_server]", file=sys.stderr)
        return 2
    environment = dict(os.environ, A01_KERNEL_WORKER="1")
    command = ["bash", str(Path(__file__).with_name("kernel.sh")), target]
    worker = None
    status = 125
    record = {"kind": "kernel_worker_group_supervision", "argv": command,
              "group_owner": "standalone supervisor", "worker_reaped": False,
              "external_reap_disarmed": False}
    with interruption_handlers() as shutdown:
        try:
            descriptors = inherited_descriptors(target, environment)
            record["pass_fds"] = list(descriptors)
            if shutdown.first_signal is None:
                # The handler cannot throw during Popen or before assignment.
                # A request arriving here is checked after ownership exists.
                worker = OwnedWorker(command, env=environment, pass_fds=descriptors)
                record["leader_pid"] = worker.process.pid
                raw = worker.wait(shutdown)
                status = exit_status(raw, shutdown)
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            record["error"] = str(error)
        finally:
            if worker is not None:
                try:
                    worker.stop()
                except (OSError, RuntimeError, subprocess.SubprocessError) as error:
                    record["cleanup_error"] = str(error)
                    status = 125
                record.update(leader_pid=worker.process.pid, raw_worker_exit=worker.status,
                              worker_reaped=worker.reaped, external_reap_disarmed=worker.external_reap)
            status = exit_status(status, shutdown)
            if shutdown.first_signal is not None:
                record["interrupted_by"] = signal.Signals(shutdown.first_signal).name
            record["exit_code"] = status
            print("A01_KERNEL_SUPERVISOR " + json.dumps(record, sort_keys=True), file=sys.stderr)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
