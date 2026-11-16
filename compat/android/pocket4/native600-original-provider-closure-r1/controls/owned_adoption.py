"""Normally reap only kernel-adopted exited children before strict retirement.

The command leader remains unreaped and held by the caller's pidfd.  This
preserves the existing retirement implementation's process-group ownership.
No signal is sent here; live children still fail at the supplied deadline.
"""
import os
import pathlib
import time

def children():
    pid = os.getpid()
    return [int(x) for x in pathlib.Path(
        f"/proc/{pid}/task/{pid}/children").read_text().split()]

def reap_exited_adopted(leader_pid, reaper_record, record, deadline):
    if not (reaper_record.get("begin_passed") is True
            and reaper_record.get("protected_pid_count") == 0
            and reaper_record.get("pid") == os.getpid()):
        raise RuntimeError("normal adoption reap requires isolated owned subreaper")
    if deadline - time.monotonic() > 5.001:
        raise RuntimeError("normal adoption reap deadline exceeds five seconds")
    record.update({"leader_pid": leader_pid, "leader_reaped_here": False,
                   "signals_sent": 0, "children": [], "deadline": deadline})
    started = time.monotonic()
    while True:
        owned = children()
        if leader_pid not in owned:
            raise RuntimeError("command leader was reaped before owned-group retirement")
        adopted = [pid for pid in owned if pid != leader_pid]
        if len(adopted) > 128:
            raise RuntimeError("normal adoption reap exceeds owned-child bound")
        for pid in adopted:
            fd = os.pidfd_open(pid, 0)
            try:
                info = os.waitid(os.P_PIDFD, fd,
                                 os.WEXITED | os.WNOHANG | os.WNOWAIT)
                if info is None:
                    continue
                actual, status = os.waitpid(pid, os.WNOHANG)
                if actual != pid:
                    raise RuntimeError("observed adopted exit was not reaped")
                record["children"].append({
                    "pid": pid, "observed_code": info.si_code,
                    "observed_status": info.si_status, "wait_status": status,
                    "reaped": True, "pidfd_closed": True})
            finally:
                os.close(fd)
        remaining = [pid for pid in children() if pid != leader_pid]
        record["remaining_adopted_children"] = remaining
        record["elapsed_seconds"] = time.monotonic() - started
        if not remaining:
            record["complete"] = True
            if any(row["wait_status"] != 0 for row in record["children"]):
                raise ChildProcessError("adopted child exited unsuccessfully")
            return
        if time.monotonic() >= deadline:
            record["complete"] = False
            raise TimeoutError("live adopted child exceeded normal five-second reap")
        time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))

