#!/usr/bin/env python3
"""Hold one original Notes issuer BODY for exact same-Root grant revocation.

External Linux qualification tool; never signs, brokers, retries a mutation,
changes a syscall result or claims a product/consumer acceptance result.
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
with tempfile.TemporaryDirectory(prefix="trill-issuer-source-") as _source_cache:
    _old_cache = sys.pycache_prefix
    try:
        # -B prevents writes but can still execute ignored cached bytecode.
        # A fresh private prefix forces this complete local import closure to source.
        sys.pycache_prefix = _source_cache
        from notes_fault_contract import Refused, digest, exact_json, fields, require, uint
        from notes_fault_linux import HeldProcess, READS, WRITES, SYSGOOD
        from notes_issuer_gate_contract import IssuerTransaction, selector
        from notes_issuer_gate_linux import IssuerTrace, POLLS, select_issuer, poll_descriptors
        from notes_issuer_gate_admin import OriginalRootAdmin, RootFile, private_parent, write_new
    finally:
        sys.pycache_prefix = _old_cache


def scan_to_grant(trace, channel, transaction, arm_end, timeout_ms, cancelled):
    """Return STOPPED at the real complete body syscall entry; no decision here."""
    require(0 < timeout_ms <= 500, "original_request_timeout_bound")
    trace.issuer_body_held = False
    pending = trace.attach(arm_end)
    trace.resume()
    request_end = None
    while time.monotonic() < arm_end:
        end = min(arm_end, request_end) if request_end is not None else arm_end
        require(not cancelled() and time.monotonic() < end, "original_request_deadline")
        status = trace.wait(end, cancelled=cancelled)
        if os.WSTOPSIG(status) != signal.SIGTRAP | SYSGOOD:
            require(status >> 16 == 0, "issuer_ptrace_event")
            trace.resume(trace.deliver)
            continue
        phase, value = trace.syscall_info()
        if phase == "entry":
            pending = value
            nr, args = value["nr"], value["args"]
            if nr in POLLS and args[1] == 2:
                # Only the original socket+owner poll can tighten the request end.
                pair = poll_descriptors(trace.app, (nr, args), idle=False)
                if pair[0] == channel.fd:
                    channel.observe_owner(pair[1])
                    if request_end is not None:
                        request_end = min(request_end, trace.poll_deadline(args, nr, time.monotonic()))
            if args[0] == channel.fd:
                if nr in WRITES:
                    channel.verify()
                    require(0 < args[2] <= 65536, "issuer_write_buffer_bound")
                    if nr == 44:
                        require(args[4] == args[5] == 0, "issuer_sendto_destination")
                    raw = trace.read_frame(args[1], args[2]) if transaction.selected or len(transaction.header) < 4 else None
                    capture = transaction.write_entry(raw, args[2])
                    if capture is not None:
                        trace.issuer_body_held = True
                        trace.selected_capture = capture
                        require(channel.owner_fd is not None, "issuer_original_owner_poll_not_observed")
                        require(request_end is not None and time.monotonic() < request_end, "original_request_deadline")
                        channel.verify(); trace.verify()
                        capture.update(root_request_end_monotonic=request_end,
                                       body_entry_monotonic=time.monotonic(), original_timeout_ms=timeout_ms)
                        return capture, min(request_end, arm_end)
                elif nr in (3, 19, 20, 46, 47, 32, 33, 292):
                    raise Refused("unsupported_or_replacing_issuer_socket_syscall")
        else:
            require(pending is not None, "unpaired_issuer_syscall_exit")
            nr, args = pending["nr"], pending["args"]
            if args[0] == channel.fd:
                channel.verify()
                if nr in READS:
                    if value > 0:
                        require(value <= args[2] and value <= 65536, "issuer_request_read_bound")
                        first = not transaction.request_bytes
                        transaction.received(trace.read_frame(args[1], value), time.monotonic())
                        if first:
                            request_end = min(arm_end, transaction.first_byte_monotonic + timeout_ms / 1000)
                    elif value == 0:
                        raise Refused("original_issuer_socket_eof")
                    else:
                        require(value in (-errno.EAGAIN, -errno.EINTR, -512, -514), "original_issuer_read_error")
                elif nr in WRITES:
                    if value > 0:
                        transaction.write_exit(value)
                        if not transaction.request_bytes:
                            request_end = None
                            require(transaction.completed_other_frames <= 32, "issuer_other_frame_bound")
                    else:
                        require(value in (-errno.EAGAIN, -errno.EINTR, -512, -514), "original_issuer_write_error")
                        transaction.pending_write = None  # Actual zero bytes; original loop alone retries.
            pending = None
        trace.resume()
    raise Refused("issuer_arm_deadline")


def load_binding(path):
    require(os.getuid() == os.geteuid() == 0, "actual_uid_zero_required")
    held = RootFile(path, 16384, private=True)
    try: value = exact_json(held.raw, 16384)
    finally: held.close()
    fields(value, ("schema", "boot_id", "desktop_commit", "hepta_commit", "root", "agentd",
                   "issuer_path", "request_timeout_ms", "selector", "cli_executable", "cli_sha256",
                   "instance_file", "reason_sha256"))
    require(value["schema"] == "trill.notes.original-issuer-gate.v1", "issuer_gate_schema")
    require(value["boot_id"] == Path("/proc/sys/kernel/random/boot_id").read_text().strip(), "issuer_gate_boot")
    for key in ("desktop_commit", "hepta_commit"):
        require(type(value[key]) is str and re.fullmatch(r"[0-9a-f]{40}", value[key]), "issuer_gate_source")
    for key in ("cli_sha256", "reason_sha256"):
        require(type(value[key]) is str and re.fullmatch(r"[0-9a-f]{64}", value[key])
                and value[key] != "0"*64, "issuer_gate_digest")
    require(type(value["request_timeout_ms"]) is int and 0 < value["request_timeout_ms"] <= 500, "issuer_timeout")
    for role in ("root", "agentd"):
        fields(value[role], ("pid", "start_ticks", "uid", "gid", "executable", "sha256"))
        require(all(uint(value[role][key]) for key in ("pid", "start_ticks", "uid", "gid")), "issuer_process_types")
        require(type(value[role]["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", value[role]["sha256"]), "issuer_exe_hash")
    require(value["root"]["uid"] == value["root"]["gid"] == 0 and value["agentd"]["uid"] != 0,
            "issuer_process_roles")
    selector(value["selector"])
    return value


def tool_sources():
    directory = Path(__file__).resolve(strict=True).parent
    names = ("notes_fault_contract.py", "notes_fault_linux.py", "notes_issuer_gate_contract.py",
             "notes_issuer_gate_receipts.py", "notes_issuer_gate_linux.py", "notes_issuer_gate_admin.py",
             "notes_issuer_gate_controller.py")
    result = {}
    for name in names:
        path = directory / name
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            info = os.fstat(fd)
            require(stat.S_ISREG(info.st_mode) and 0 < info.st_size <= 65536, "tool_source_bound")
            raw = os.pread(fd, 65537, 0)
            require(len(raw) == info.st_size, "tool_source_size_changed")
            result[name] = digest(raw)
        finally:
            os.close(fd)
    return result


def run(binding, output, seconds, cancelled):
    require(os.getuid() == os.geteuid() == 0, "actual_uid_zero_required")
    require(0 < seconds <= 180, "issuer_arm_bound")
    private_parent(output.parent)
    output.mkdir(mode=0o700)  # New only; never repair another directory's permissions.
    private_parent(output)
    result = dict(schema="trill.notes.original-issuer-gate-result.v1", product_qualified=False,
                  consumer_first_use_revoked_proven=False, status="unexecuted", body_released=False,
                  body_shutdown=False, mutation_attempted=False, syscall_result_modified=False,
                  desktop_commit=binding["desktop_commit"], hepta_commit=binding["hepta_commit"],
                  started_monotonic=time.monotonic(), tool_sources_before=tool_sources())
    held, channel, trace, admin, capture = [], None, None, None, None
    try:
        for role in ("root", "agentd"):
            held.append(HeldProcess(binding[role]))
        root, agentd = held
        admin = OriginalRootAdmin(binding, root, output)
        tid, idle, channel, birth = select_issuer(root, agentd, binding["issuer_path"])
        trace = IssuerTrace(root, tid, idle, birth)
        result.update(root=root.identity, agentd=agentd.identity, issuer_tid=tid, issuer_tid_birth=birth,
                      issuer_fd=channel.fd, issuer_socket_inode=channel.identity.st_ino,
                      original_idle_syscall=idle[0], original_admin_instance=admin.instance)
        capture, end = scan_to_grant(trace, channel, IssuerTransaction(binding["selector"]),
                                    result["started_monotonic"]+seconds, binding["request_timeout_ms"], cancelled)
        # Only hashes and identities in the public receipt; original bytes in Root0600 artifacts.
        result["capture"] = {key:value for key,value in capture.items() if key not in
                             ("request_raw", "response_raw", "signed_raw", "signed")}
        write_new(output/"original-issuer-request.json", capture["request_raw"])
        write_new(output/"original-issuer-response.json", capture["response_raw"])
        result["admin"] = admin.revoke_held_original(capture, binding["reason_sha256"], end, cancelled)
        channel.verify(); trace.verify()
        for process in held: process.verify(tracer=os.getpid())
        require(time.monotonic() < end and not cancelled(), "original_request_deadline")
        # DETACH resumes THIS untouched body syscall. No registers or results are changed.
        trace.close()
        result.update(body_released=not trace.attached and not trace.stopped,
                      released_monotonic=next((event["detached_monotonic"] for event in reversed(trace.events)
                                              if "detached_monotonic" in event), None),
                      release_cleanup_finished_monotonic=time.monotonic())
        require(not trace.cleanup_failed and not trace.attached, "issuer_release_cleanup_failed")
        require(result["released_monotonic"] is not None and result["released_monotonic"] < end
                and result["release_cleanup_finished_monotonic"] < end and not cancelled(),
                "original_request_deadline_during_detach")
        result["status"] = "original_body_released_after_confirmed_revoke"
    except BaseException as error:
        # Every catchable unwind must reach shutdown-before-detach below.
        # In particular subprocess.TimeoutExpired is not built-in TimeoutError.
        if capture is None and trace is not None:
            capture = getattr(trace, "selected_capture", None)
            if capture is not None:
                result["capture"] = {key:value for key,value in capture.items() if key not in
                                     ("request_raw", "response_raw", "signed_raw", "signed")}
        result.update(status="outcome_unknown" if capture is not None else "unexecuted",
                      reason=str(error), errno=getattr(error,"errno",None))
    finally:
        if trace is not None:
            # A normal release already detached above. Any still-held selected
            # BODY must be shut down before cleanup can resume its syscall,
            # including unexpected exceptions and Python-level cancellation.
            held_for_cleanup = getattr(trace, "issuer_body_held", False) and trace.stopped
            if held_for_cleanup:
                result["status"] = "outcome_unknown"
                try:
                    channel.verify()
                    channel.socket.shutdown(socket.SHUT_WR)
                    result.update(body_shutdown=True, shutdown_monotonic=time.monotonic())
                except BaseException as shutdown_error:
                    result["shutdown_reason"] = str(shutdown_error)
            trace.close()
            result["selected_body_resumed_on_cleanup"] = bool(held_for_cleanup
                and not trace.attached and not trace.stopped)
            result["tracing"] = dict(stops=trace.stops, total_stopped_seconds=trace.total_pause,
                max_stop_seconds=trace.max_pause, events=trace.events, omitted_events=trace.omitted_events,
                detached=not trace.attached and not trace.stopped)
            if trace.cleanup_failed: result["status"]="cleanup_failed"
        if admin is not None:
            result["mutation_attempted"] = admin.mutation_attempted
            result["admin_steps"] = admin.steps
            admin.close()
        if channel is not None: channel.close()
        for process in reversed(held): process.close()
        try:
            result["tool_sources_after"] = tool_sources()
        except (OSError, ValueError) as error:
            result["tool_sources_after"] = None
            result["tool_source_check_error"] = str(error)
        result["tool_source_unchanged"] = result["tool_sources_before"] == result["tool_sources_after"]
        if not result["tool_source_unchanged"]: result["status"] = "tool_source_changed_outcome_unknown"
        result["finished_monotonic"] = time.monotonic()
        write_new(output/"result.json", json.dumps(result, ensure_ascii=False, indent=2).encode()+b"\n")
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binding",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--seconds",type=float,default=120)
    args=parser.parse_args(); cancelled=[False]
    for number in (signal.SIGINT,signal.SIGTERM): signal.signal(number,lambda *_:cancelled.__setitem__(0,True))
    try:
        binding = load_binding(args.binding)
    except (OSError,ValueError) as error:
        result=dict(status="unexecuted",reason=str(error),product_qualified=False,consumer_first_use_revoked_proven=False)
    else:
        try: result=run(binding,args.output,args.seconds,lambda:cancelled[0])
        except (OSError,ValueError) as error:
            result=dict(status="outcome_unknown",reason=str(error),product_qualified=False,
                        consumer_first_use_revoked_proven=False,cleanup_or_evidence_requires_attention=True)
    print(json.dumps(result,sort_keys=True))
    return 0 if result["status"]=="original_body_released_after_confirmed_revoke" else 1


if __name__=="__main__": raise SystemExit(main())
