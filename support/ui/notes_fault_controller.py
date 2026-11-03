#!/usr/bin/env python3
"""Observe or lose one original Notes Applied reply body on Linux x86_64.

An external qualification tool. It sends no request, fabricates no receipt,
changes no syscall result and touches neither the recovery datagram nor store.
"""
import argparse
import errno
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import sys
import tempfile
import time

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
with tempfile.TemporaryDirectory(prefix="trill-fault-source-") as _source_cache:
    _old_cache = sys.pycache_prefix
    try:
        sys.pycache_prefix = _source_cache
        from notes_fault_contract import Refused, Transaction, exact_json, fields, require, uint
        from notes_fault_linux import HeldProcess, HeldEffectSocket, TraceThread, READS, WRITES, SYSGOOD, proc_identity
    finally:
        sys.pycache_prefix = _old_cache


def load_binding(path):
    require(os.getuid() == 0 and os.geteuid() == 0, "actual_uid_zero_required")
    require(path.is_absolute() and path.resolve(strict=True) == path, "binding_path")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        info = os.fstat(fd)
        require(stat.S_ISREG(info.st_mode) and info.st_uid == 0
                and stat.S_IMODE(info.st_mode) == 0o600 and info.st_size <= 16384, "binding_custody")
        data = os.read(fd, 16385)
    finally:
        os.close(fd)
    value = exact_json(data, 16384)
    fields(value, ("schema", "boot_id", "desktop_commit", "hepta_commit", "root", "session", "app",
                   "target", "expected_revision", "text_sha256", "notes_state_dir"))
    require(value["schema"] == "trill.notes.partial-reply-fault.v1", "binding_schema")
    require(Path("/proc/sys/kernel/random/boot_id").read_text().strip() == value["boot_id"], "boot_identity")
    for key in ("desktop_commit", "hepta_commit"):
        require(type(value[key]) is str and re.fullmatch(r"[0-9a-f]{40}", value[key]), "source_identity")
    for role in ("root", "session", "app"):
        process = value[role]
        fields(process, ("pid", "start_ticks", "uid", "gid", "executable", "sha256"))
        require(all(uint(process[key]) for key in ("pid", "start_ticks", "uid", "gid")), "process_identity_types")
        require(1 < process["pid"] < 2**31 and process["uid"] < 2**32 and process["gid"] < 2**32,
                "process_identity_bound")
        require(type(process["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", process["sha256"]), "executable_hash")
    require(value["root"]["uid"] == 0 and value["session"]["uid"] != 0
            and value["app"]["uid"] == value["session"]["uid"], "product_process_roles")
    return value


def state_directory(app, expected):
    # Read no unrelated environment value into the evidence output.
    with Path(f"/proc/{app.pid}/environ").open("rb") as source:
        raw = source.read(65537)
    require(len(raw) <= 65536, "app_environment_bound")
    matches = [entry.split(b"=", 1)[1] for entry in raw.split(b"\0")
               if entry.startswith(b"TRILL_NOTES_STATE_DIR=")]
    require(len(matches) == 1 and os.fsdecode(matches[0]) == expected, "durable_notes_environment")
    path = Path(expected)
    require(path.is_absolute() and path.resolve(strict=True) == path, "notes_state_path")
    info = path.stat()
    require(stat.S_ISDIR(info.st_mode) and info.st_uid == app.identity["uid"][0]
            and stat.S_IMODE(info.st_mode) == 0o700, "notes_state_directory_custody")


def idle_snapshot(app, tid):
    line = Path(f"/proc/{app.pid}/task/{tid}/syscall").read_text().split()
    if len(line) != 9 or line[0] in ("running", "-1"):
        return None
    nr = int(line[0])
    args = [int(value, 16) for value in line[1:7]]
    if nr not in READS or args[2] != 4:
        return None
    return nr, args


def select_effect(app, session):
    candidates = []
    failures = []
    try:
        for item in Path(f"/proc/{app.pid}/task").iterdir():
            if not item.name.isdecimal():
                continue
            birth = proc_identity(app.pid, int(item.name))["start_ticks"]
            snapshot = idle_snapshot(app, int(item.name))
            if snapshot is None:
                continue
            fd = snapshot[1][0]
            try:
                if not os.readlink(f"/proc/{app.pid}/fd/{fd}").startswith("socket:["):
                    continue
                channel = HeldEffectSocket(app, fd, session)
            except Refused:
                continue
            except OSError as error:
                if error.errno in (errno.EPERM, errno.EACCES, errno.ENOSYS):
                    failures.append(error.errno)
                continue
            candidates.append((int(item.name), snapshot, channel, birth))
            require(proc_identity(app.pid, int(item.name))["start_ticks"] == birth, "effect_thread_birth_changed")
        require(len(candidates) == 1, "effect_thread_not_unique" if candidates else
                "effect_socket_inspection_not_permitted" if failures else "no_original_idle_effect_thread")
        return candidates.pop()
    finally:
        for _, _, channel, _ in candidates:
            channel.close()


def run(binding, mode, seconds, cancelled):
    require(os.getuid() == 0 and os.geteuid() == 0, "actual_uid_zero_required")
    require(mode in ("observe", "drop-reply-body") and 0 < seconds <= 180, "controller_scope")
    result = {"schema": "trill.notes.partial-reply-observation.v1", "status": "unexecuted",
              "mode": mode, "action_taken": False, "product_qualified": False,
              "owner_receipt_verified": False, "clock_or_syscall_result_modified": False,
              "desktop_commit": binding["desktop_commit"], "hepta_commit": binding["hepta_commit"],
              "started_monotonic": time.monotonic()}
    deadline = result["started_monotonic"] + seconds
    held, channel, trace = [], None, None
    try:
        for role in ("root", "session", "app"):
            held.append(HeldProcess(binding[role]))
        root, session, app = held
        require(session.identity["ppid"] == root.pid and app.identity["ppid"] == session.pid,
                "original_process_parentage")
        state_directory(app, binding["notes_state_dir"])
        transaction = Transaction(binding["target"], binding["expected_revision"], binding["text_sha256"])
        tid, snapshot, channel, birth = select_effect(app, session)
        trace = TraceThread(app, tid, snapshot, birth)
        pending = trace.attach(deadline)
        result.update(app=app.identity, session=session.identity, root=root.identity, effect_tid=tid,
                      effect_tid_start_ticks=trace.birth, effect_fd=channel.fd, socket_inode=channel.identity.st_ino)
        trace.resume()
        fault_pending = False
        while time.monotonic() < deadline:
            require(not cancelled(), "controller_cancelled")
            status = trace.wait(deadline, cancelled=cancelled)
            stop = os.WSTOPSIG(status)
            if stop != signal.SIGTRAP | SYSGOOD:
                event = status >> 16
                if stop in (signal.SIGSTOP, signal.SIGTSTP, signal.SIGTTIN, signal.SIGTTOU):
                    trace.deliver = stop
                require(event == 0, "unexpected_ptrace_event")
                app.verify(tracer=os.getpid())
                trace.deliver = stop
                trace.resume(stop)
                continue
            phase, value = trace.syscall_info()
            if phase == "entry":
                pending = value
                nr, args = pending["nr"], pending["args"]
                if args[0] == channel.fd and nr in WRITES:
                    channel.verify()
                    require(0 < args[2] <= 2048, "reply_syscall_buffer_bound")
                    if nr == 44:
                        require(args[4] == 0 and args[5] == 0, "reply_sendto_destination")
                    observation = transaction.write_entry(trace.read_memory(args[1], args[2]))
                    if observation is not None:
                        for process in held:
                            process.verify(tracer=os.getpid())
                        trace.verify()
                        channel.verify()
                        require(time.monotonic() < deadline and not cancelled(), "fault_deadline")
                        result["boundary"] = observation
                        if mode == "observe":
                            result["status"] = "boundary_observed_without_fault"
                            break
                        channel.socket.shutdown(socket.SHUT_WR)
                        result.update(action_taken=True, shutdown_monotonic=time.monotonic())
                        fault_pending = True
                elif args[0] == channel.fd and nr in (19, 20, 46, 47, 3):
                    raise Refused("unsupported_or_closing_effect_syscall")
            else:
                require(pending is not None, "unpaired_syscall_exit")
                nr, args = pending["nr"], pending["args"]
                if args[0] == channel.fd:
                    channel.verify()
                    if nr in READS and value > 0:
                        require(value <= args[2] and value <= 8192, "request_syscall_bound")
                        transaction.received(trace.read_memory(args[1], value))
                    elif nr in WRITES:
                        if fault_pending:
                            result["actual_reply_syscall_return"] = value
                            require(value == -errno.EPIPE, "unexpected_post_shutdown_syscall_result")
                            result["status"] = "reply_body_shutdown_observed_epipe"
                            break
                        transaction.write_exit(value)
                    elif nr in READS and value == 0:
                        raise Refused("original_effect_socket_eof")
                pending = None
            trace.resume()
        else:
            raise Refused("controller_deadline")
    except (OSError, ValueError, ChildProcessError) as error:
        result.update(status="fault_outcome_unknown" if result["action_taken"] else "unexecuted",
                      reason=str(error), errno=getattr(error, "errno", None))
    finally:
        if trace is not None:
            trace.close()
            result["tracing"] = {"stops": trace.stops, "total_stopped_seconds": trace.total_pause,
                                 "max_stop_seconds": trace.max_pause, "events": trace.events,
                                 "omitted_events": trace.omitted_events,
                                 "detached": not trace.attached and not trace.stopped}
            if trace.cleanup_failed:
                result["cleanup_requires_attention"] = True
                result["status"] = "cleanup_failed"
        if channel is not None:
            channel.close()
        for process in reversed(held):
            process.close()
        result["finished_monotonic"] = time.monotonic()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding", required=True, type=Path)
    parser.add_argument("--mode", required=True, choices=("observe", "drop-reply-body"))
    parser.add_argument("--seconds", type=float, default=120)
    args = parser.parse_args()
    cancelled = [False]
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, lambda *_: cancelled.__setitem__(0, True))
    try:
        result = run(load_binding(args.binding), args.mode, args.seconds, lambda: cancelled[0])
    except (OSError, ValueError) as error:
        result = {"status": "unexecuted", "action_taken": False, "reason": str(error), "product_qualified": False}
    print(json.dumps(result, sort_keys=True))
    return 0 if result["status"] in ("boundary_observed_without_fault", "reply_body_shutdown_observed_epipe") else 1


if __name__ == "__main__":
    raise SystemExit(main())
