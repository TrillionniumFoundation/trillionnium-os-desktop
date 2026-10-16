"""Probe the unchanged OSDK supervisor using only owned processes and pidfds."""
import errno
import hashlib
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import time
import uuid

BASE = Path(__file__).resolve().parent
BINARY = BASE / "target/debug/a01-daemon-lifecycle-probe"
ROLES = BASE / "roles.py"


def run_case(mode):
    output = BASE / "runs" / mode
    output.mkdir(parents=True, exist_ok=False)
    read_fd, write_fd = os.pipe()
    os.set_blocking(read_fd, False)
    nonce = uuid.uuid4().hex
    argv = [str(BINARY), mode, sys.executable, str(ROLES), str(write_fd), nonce, str(output)]
    record = {
        "mode": mode,
        "command": argv,
        "python": sys.version,
        "binary_sha256": hashlib.sha256(BINARY.read_bytes()).hexdigest(),
        "nonce": nonce,
        "events": [],
        "snapshots": [],
        "cleanup": [],
        "identity_method": "nonce pipe; namespace getpid/getpgrp; pidfd handles; no numeric proc lookup",
    }
    handles = {}
    identities = {}
    pending = b""
    started = time.monotonic()
    proc = None

    def collect():
        nonlocal pending
        while True:
            try:
                data = os.read(read_fd, 65536)
            except BlockingIOError:
                break
            if not data:
                break
            pending += data
            while b"\n" in pending:
                line, pending = pending.split(b"\n", 1)
                event = json.loads(line)
                assert event["nonce"] == nonce
                record["events"].append(event)
                if event["event"] == "leader_spawned":
                    assert event["ppid"] == proc.pid
                    assert event["pgid"] == event["pid"]
                    identities["leader"] = event["pid"]
                    identities["expected_descendant"] = event["child_pid"]
                    identities["descendant"] = event["child_pid"]
                    handles["leader"] = os.pidfd_open(event["pid"])
                    handles["descendant"] = os.pidfd_open(event["child_pid"])
                if "leader" in identities:
                    for ready in record["events"]:
                        if ready["event"] == "descendant_ready":
                            assert ready["pid"] == identities["expected_descendant"]
                            assert ready["ppid"] == identities["leader"]
                            assert ready["pgid"] == identities["leader"]
                            assert ready["ignores_term"]

    def snapshot(label):
        states = {}
        for role, fd in handles.items():
            try:
                os.kill(identities[role], 0)
                kill_zero = {"success": True, "errno": None}
            except OSError as exc:
                kill_zero = {"success": False, "errno": exc.errno}
            states[role] = {
                "namespace_pid": identities[role],
                "pidfd_exited": bool(select.select([fd], [], [], 0)[0]),
                "kill_zero": kill_zero,
            }
        record["snapshots"].append({"label": label, "monotonic": time.monotonic(), "states": states})

    try:
        with (output / "harness.log").open("wb") as log:
            proc = subprocess.Popen(argv, pass_fds=(write_fd,), stdout=log, stderr=log)
            record["harness_namespace_pid"] = proc.pid
            os.close(write_fd)
            write_fd = None
            while proc.poll() is None:
                collect()
                if time.monotonic() - started > 15:
                    raise TimeoutError("owned probe harness exceeded 15 seconds")
                time.sleep(0.01)
            exited = time.monotonic()
            collect()
            record["harness_exit"] = proc.wait()
            record["harness_exited_monotonic"] = exited
            assert set(handles) == {"leader", "descendant"}
            snapshot("immediately_after_supervisor_process_exit")
            observation = 0.3 if mode == "leader_and_descendant_ignore_term" else 6.25
            while time.monotonic() - exited < observation:
                collect()
                time.sleep(0.02)
            collect()
            snapshot("after_observation_interval")
            record["post_supervisor_observation_seconds"] = time.monotonic() - exited
            heartbeats = [e for e in record["events"] if e["event"] == "heartbeat" and e["monotonic"] > exited]
            record["descendant_heartbeats_after_supervisor_exit"] = len(heartbeats)
            record["latest_heartbeat_delay_after_supervisor_exit"] = max(
                (e["monotonic"] - exited for e in heartbeats), default=None
            )
            final = record["snapshots"][-1]["states"]
            record["descendant_outlived_leader_and_supervisor"] = (
                final["leader"]["pidfd_exited"]
                and not final["descendant"]["pidfd_exited"]
                and bool(heartbeats)
            )
    except BaseException as exc:
        record["probe_error"] = {"type": type(exc).__name__, "message": str(exc)}
        raise
    finally:
        # Signal only pidfd identities established from our private nonce pipe.
        for role, fd in handles.items():
            cleanup = {"role": role, "namespace_pid": identities[role]}
            try:
                if select.select([fd], [], [], 0)[0]:
                    cleanup["already_exited"] = True
                else:
                    signal.pidfd_send_signal(fd, signal.SIGKILL)
                    cleanup["signal"] = "SIGKILL via own pidfd"
                    cleanup["exited_within_2_seconds"] = bool(select.select([fd], [], [], 2)[0])
                    assert cleanup["exited_within_2_seconds"]
            except OSError as exc:
                cleanup["errno"] = exc.errno
                if exc.errno != errno.ESRCH:
                    raise
            finally:
                os.close(fd)
                record["cleanup"].append(cleanup)
        if proc is not None and proc.poll() is None:
            proc.kill()  # Direct child handle, never an inferred external PID.
            proc.wait()
        if write_fd is not None:
            os.close(write_fd)
        os.close(read_fd)
        record["duration_seconds"] = time.monotonic() - started
        (output / "result.json").write_text(json.dumps(record, indent=2) + "\n")
    return record


if __name__ == "__main__":
    results = []
    for case in ("leader_dies_on_term", "leader_exits_normally", "leader_and_descendant_ignore_term"):
        result = run_case(case)
        results.append({
            "mode": case,
            "harness_exit": result["harness_exit"],
            "descendant_outlived_leader_and_supervisor": result["descendant_outlived_leader_and_supervisor"],
            "latest_heartbeat_delay_after_supervisor_exit": result["latest_heartbeat_delay_after_supervisor_exit"],
            "cleanup": result["cleanup"],
        })
        print(json.dumps(results[-1]), flush=True)
    (BASE / "summary.json").write_text(json.dumps(results, indent=2) + "\n")
