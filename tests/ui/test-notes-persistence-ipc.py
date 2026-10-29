#!/usr/bin/env python3
"""Real Notes app + Session under a privately owned Weston.

The parent is an explicit transport fixture, NOT a Hepta issuer/durable writer.
Verifies application durability and wire recovery through independent sockets.
"""
import array
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import struct
import subprocess
import sys
import tempfile
import time


def check(value, message):
    if not value:
        raise RuntimeError(message)


def encode(value):
    return json.dumps(value, separators=(",", ":")).encode()


def digest(value):
    return hashlib.sha256(value).hexdigest()


def read_exact(channel, count):
    data = b""
    while len(data) < count:
        part = channel.recv(count-len(data))
        check(part, "effect reply closed")
        data += part
    return data


def effect(channel, raw):
    channel.sendall(struct.pack("!I", len(raw))+raw)
    count = struct.unpack("!I", read_exact(channel, 4))[0]
    check(0 < count <= 2048, "reply bound")
    return read_exact(channel, count)


def recover(channel, query):
    channel.send(encode(query))
    raw = channel.recv(2049)
    check(0 < len(raw) <= 2048, "recovery reply bound")
    return raw


def offer(channel):
    raw, ancillary, flags, _ = channel.recvmsg(1025, socket.CMSG_SPACE(8), socket.MSG_CMSG_CLOEXEC)
    descriptors = []
    for level, kind, data in ancillary:
        check(level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS, "unexpected ancillary")
        values = array.array("i")
        values.frombytes(data)
        descriptors.extend(values)
    try:
        check(not flags & (socket.MSG_CTRUNC | socket.MSG_TRUNC), "bootstrap truncation")
        check(len(descriptors) == 2, "v2 must transfer exactly two channels")
        value = json.loads(raw)
        check(value["schema_version"] == 2 and value["action"] == "offer_notes_target", "v2 offer")
        streams = [socket.socket(fileno=fd) for fd in descriptors]
        descriptors.clear()
        for stream, kind in zip(streams, [socket.SOCK_STREAM, socket.SOCK_DGRAM]):
            check(stream.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) == kind, "descriptor order/type")
            check(stream.getsockname() == stream.getpeername() == "", "private unnamed endpoint")
            stream.settimeout(3)
        channel.send(encode({"schema_version":2,"action":"notes_target_registration",
            "target":value["target"],"destination_id":value["destination_id"],"status":"attached"}))
        return value, streams
    finally:
        for fd in descriptors:
            os.close(fd)


def snapshot(path):
    with socket.socket(socket.AF_UNIX) as channel:
        channel.settimeout(3)
        channel.connect(str(path))
        channel.sendall(b'{"type":"snapshot"}\n')
        raw = b""
        while not raw.endswith(b"\n"):
            part = channel.recv(65536-len(raw))
            check(part, "snapshot closed or exceeded response bound")
            raw += part
        return json.loads(raw)


def main():
    binaries = Path(sys.argv[1]).resolve(strict=True)
    output = Path(sys.argv[2]).resolve()
    output.mkdir(parents=True, exist_ok=True)
    trace = []
    report = {"scope":"real Linux app durability; transport fixture only, no Hepta grant/ledger", "steps":[]}
    with tempfile.TemporaryDirectory(prefix="notes-durable-") as temporary:
        root = Path(temporary)
        report["temporary_storage"] = {"path": str(root), "device": root.stat().st_dev}
        report["binaries_sha256"] = {
            name: digest((binaries/name).read_bytes())
            for name in ("trill-session", "trill-app-window")
        }
        display_root = root/"display"
        display_root.mkdir(mode=0o700)
        env = os.environ.copy()
        for key in list(env):
            if key.startswith("TRILL_HEPTA_") or key.startswith("TRILL_NOTES_"):
                env.pop(key)
        env.pop("DISPLAY", None)
        env["XDG_RUNTIME_DIR"] = str(display_root)
        env["WAYLAND_DISPLAY"] = "notes-test"
        env["LIBGL_ALWAYS_SOFTWARE"] = "1"
        env["XDG_STATE_HOME"] = str(root/"state")
        with open(output/"weston.stdout", "wb") as logs:
            weston = subprocess.Popen(["weston", "--backend=headless-backend.so", "--renderer=pixman",
                "--no-config", "--socket=notes-test", "--idle-time=0", f"--log={output/'weston.log'}"],
                env=env, stdout=logs, stderr=subprocess.STDOUT)
            sessions = []
            channels = []
            log_handles = []
            current_recovery = None
            current_target = None
            last_effect = None
            public = None
            def record(event, **values):
                trace.append({"monotonic":time.monotonic(), "event":event, **values})
                (output/"trace.json").write_text(json.dumps(trace, indent=2)+"\n")
            def traced_effect(channel, raw):
                nonlocal last_effect
                last_effect = raw
                record("effect_start", request=json.loads(raw), payload_sha256=digest(raw))
                reply = effect(channel, raw)
                record("effect_reply", response=json.loads(reply))
                return reply
            def traced_recover(channel, query):
                record("recovery_start", request=query)
                reply = recover(channel, query)
                record("recovery_reply", response=json.loads(reply))
                return reply
            def process_diagnostics(proc):
                result = {"pid":proc.pid, "exit_code":proc.poll(), "processes":{}}
                pids = [proc.pid]
                children = Path(f"/proc/{proc.pid}/task/{proc.pid}/children")
                try:
                    pids.extend(int(pid) for pid in children.read_text().split())
                except OSError as error:
                    result["children_error"] = repr(error)
                for pid in pids:
                    process = {"threads":{}, "fds":{}}
                    result["processes"][str(pid)] = process
                    proc_dir = Path(f"/proc/{pid}")
                    for name in ("status", "io", "schedstat"):
                        try:
                            process[name] = (proc_dir/name).read_text()
                        except OSError as error:
                            process[name] = repr(error)
                    for thread in (proc_dir/"task").glob("*"):
                        values = {}
                        for name in ("comm", "wchan", "syscall"):
                            try:
                                values[name] = (thread/name).read_text()
                            except OSError as error:
                                values[name] = repr(error)
                        process["threads"][thread.name] = values
                    for fd in (proc_dir/"fd").glob("*"):
                        try:
                            process["fds"][fd.name] = os.readlink(fd)
                        except OSError as error:
                            process["fds"][fd.name] = repr(error)
                return result
            def stop(proc):
                if proc.poll() is None:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(timeout=3)
            try:
                deadline = time.monotonic()+8
                while not (display_root/"notes-test").exists():
                    check(weston.poll() is None and time.monotonic() < deadline, "owned Weston failed")
                    time.sleep(.025)
                env["WAYLAND_DISPLAY"] = str(display_root/"notes-test")
                def launch(number, reopen=False):
                    runtime = root/f"runtime{number}"
                    runtime.mkdir(mode=0o700)
                    child_env = env.copy()
                    child_env["XDG_RUNTIME_DIR"] = str(runtime)
                    parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
                    parent.settimeout(5)
                    log = open(output/f"session{number}.log", "wb")
                    log_handles.append(log)
                    proc = subprocess.Popen([str(binaries/"trill-session"), "--notes-bootstrap-v2-stdin",
                        "--notes-document" if reopen else "--notes-new-document", str(root/"document")],
                        env=child_env, stdin=child, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                    sessions.append(proc)
                    child.close()
                    value, endpoints = offer(parent)
                    parent.close()
                    channels.extend(endpoints)
                    public = runtime/"trillionnium-ui/session.sock"
                    deadline = time.monotonic()+20
                    while True:
                        state = snapshot(public)
                        tasks = state.get("tasks", [])
                        if tasks and tasks[0].get("ui_first_frame_unix_ms") is not None:
                            break
                        check(proc.poll() is None and time.monotonic() < deadline, f"app layout did not become ready: {state}")
                        check(not tasks or tasks[0]["state"] not in ("failed", "completed", "cancelled"), f"app exited: {state}")
                        time.sleep(.025)
                    return proc, value, endpoints[0], endpoints[1], public
                proc, first, write, recovery, public = launch(1)
                current_recovery, current_target = recovery, first["target"]
                def read_state(channel, target):
                    request_id = os.urandom(16).hex()
                    value = json.loads(traced_recover(channel, {"schema_version":1,"action":"read_document_state",
                        "target":target,"request_id":request_id}))
                    check(value["target"] == target and value["request_id"] == request_id, "readback binding")
                    return value
                initial = read_state(recovery, first["target"])
                check(initial["revision"] == 0, "new document revision")
                def payload(target, operation, revision, text):
                    return encode({"schema_version":1,"action":"replace_note","target":target,
                        "destination_id":f"trill.notes:{target['session_instance']}:{target['task_id']}:{target['incarnation']}",
                        "operation_id":operation,"expected_revision":revision,"text":text})
                first_raw = payload(first["target"], "durable.first", 0, "First durable 中文")
                receipt1 = traced_effect(write, first_raw)
                check(json.loads(receipt1)["result"]["status"] == "applied", "first applied")
                check(traced_effect(write, first_raw) == receipt1, "duplicate must replay exact receipt")
                second_raw = payload(first["target"], "durable.lost-ack", 1, "Recovered document 中文")
                pending = json.loads(traced_effect(write, second_raw))
                check(pending["result"]["reason"] == "receipt_pending", "unacknowledged receipt must fence next edit")
                ack1 = {"schema_version":1,"action":"acknowledge_terminal","target":first["target"],
                    "operation_id":"durable.first","payload_sha256":digest(first_raw),"receipt_sha256":digest(receipt1)}
                check(json.loads(traced_recover(recovery, ack1))["status"] == "released", "terminal ACK")
                write.sendall(struct.pack("!I", len(second_raw))+second_raw)
                write.close()  # Deliberately lose effect reply; recovery is independent.
                query = {"schema_version":1,"action":"observe","target":first["target"],
                    "operation_id":"durable.lost-ack","payload_sha256":digest(second_raw)}
                deadline = time.monotonic()+3
                while True:
                    receipt2 = traced_recover(recovery, query)
                    if json.loads(receipt2)["result"]["status"] == "applied":
                        break
                    check(time.monotonic() < deadline, "lost ACK read-only reconciliation")
                    time.sleep(.025)
                before = read_state(recovery, first["target"])
                check(before["revision"] == 2 and before["text_sha256"] == digest("Recovered document 中文".encode()), "independent document readback")
                snap = snapshot(public)
                child_pid = snap["tasks"][0]["pid"]
                check(str(child_pid) in Path(f"/proc/{proc.pid}/task/{proc.pid}/children").read_text().split(), "kill only Session-owned app")
                os.kill(child_pid, signal.SIGKILL)
                deadline = time.monotonic()+4
                while Path(f"/proc/{child_pid}").exists():
                    check(time.monotonic() < deadline, "Session did not reap killed app")
                    time.sleep(.025)
                stop(proc)
                proc2, second, write2, recovery2, public = launch(2, True)
                current_recovery, current_target = recovery2, second["target"]
                check(second["target"] != first["target"], "reopen must use fresh target incarnation")
                after = read_state(recovery2, second["target"])
                check(after["revision"] == before["revision"] and after["text_sha256"] == before["text_sha256"], "crash restored document")
                check(traced_recover(recovery2, query) == receipt2, "old target receipt must survive process kill byte-for-byte")
                refusal = json.loads(traced_effect(write2, second_raw))
                check(refusal["result"]["reason"] == "target_mismatch", "old effect cannot migrate to new process")
                ack2 = {"schema_version":1,"action":"acknowledge_terminal","target":first["target"],
                    "operation_id":"durable.lost-ack","payload_sha256":digest(second_raw),"receipt_sha256":digest(receipt2)}
                check(json.loads(traced_recover(recovery2, ack2))["status"] == "released", "recovered owner ACK")
                check(json.loads(traced_recover(recovery2, ack2))["status"] == "already_released", "lost terminal ACK idempotent")
                report.update(status="passed", first_target=first["target"], reopened_target=second["target"],
                    before_kill=before, after_reopen=after, exact_receipt_sha256=digest(receipt2),
                    steps=["real app apply", "exact duplicate", "receipt pending fence", "terminal ACK",
                           "lost reply", "independent readback", "SIGKILL and reap", "new-incarnation reopen",
                           "old-target exact reconciliation", "old-effect refusal", "idempotent retirement"])
            except BaseException as failure:
                report.update(status="failed", error=repr(failure))
                diagnostics = {"processes":[process_diagnostics(proc) for proc in sessions],
                               "store":{}}
                for path in (root/"document").glob("*"):
                    try:
                        raw = path.read_bytes()
                        diagnostics["store"][path.name] = {
                            "bytes":len(raw), "sha256":digest(raw),
                            "state":json.loads(raw) if raw else None,
                        }
                    except (OSError, ValueError) as error:
                        diagnostics["store"][path.name] = {"error":repr(error)}
                if public is not None:
                    try:
                        diagnostics["snapshot"] = snapshot(public)
                    except Exception as error:
                        diagnostics["snapshot_error"] = repr(error)
                if current_recovery is not None:
                    queries = [{"schema_version":1,"action":"read_document_state",
                                "target":current_target,"request_id":os.urandom(16).hex()}]
                    if last_effect is not None:
                        request = json.loads(last_effect)
                        queries.append({"schema_version":1,"action":"observe",
                                        "target":request["target"],
                                        "operation_id":request["operation_id"],
                                        "payload_sha256":digest(last_effect)})
                    diagnostics["readonly_recovery"] = []
                    for query in queries:
                        try:
                            response = json.loads(traced_recover(current_recovery, query))
                            diagnostics["readonly_recovery"].append({"query":query,"response":response})
                        except Exception as error:
                            diagnostics["readonly_recovery"].append({"query":query,"error":repr(error)})
                (output/"failure-diagnostics.json").write_text(json.dumps(diagnostics, indent=2)+"\n")
                (output/"result.json").write_text(json.dumps(report, indent=2)+"\n")
                raise
            finally:
                for proc in sessions:
                    stop(proc)
                for channel in channels:
                    channel.close()
                for log in log_handles:
                    log.close()
                weston.terminate()
                weston.wait(timeout=5)
    (output/"result.json").write_text(json.dumps(report, indent=2)+"\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
