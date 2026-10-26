#!/usr/bin/env python3
"""Compare Session responsiveness under the same stalled Objective query load.

Runs a real isolated Session against a same-UID/PID, mode-0600 synthetic
endpoint that accepts only availability reads and deliberately sends no reply.
No original owner, Notes bootstrap, app task, grant or device is started.
The default reproduces the old serialized limitation. --expect responsive
requires the fixed host transport; neither mode claims product acceptance.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import threading
import time


def require(condition, reason):
    if not condition:
        raise AssertionError(reason)


def connect(path):
    peer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    peer.settimeout(3)
    peer.connect(str(path))
    return peer


def send(peer, request):
    peer.sendall(json.dumps(request, separators=(",", ":")).encode() + b"\n")


def receive(peer):
    raw = bytearray()
    while not raw.endswith(b"\n"):
        require(len(raw) < 65536, "unbounded fixture response")
        try:
            part = peer.recv(65536 - len(raw))
        except ConnectionResetError:
            return "reset", None
        if not part:
            return "eof", None
        raw.extend(part)
    return "response", json.loads(raw)


def snapshot(peer):
    send(peer, {"type": "snapshot"})
    kind, response = receive(peer)
    require(kind == "response", "uncontended snapshot did not receive a reply")
    require(response["type"] == "snapshot", "uncontended snapshot was refused")
    require(not response["tasks"], "read-only fixture unexpectedly created a task")
    return response["session_instance"]


def reproduce(binary, temporary, report, expected):
    endpoint = Path(temporary) / "synthetic-objective.sock"
    session_path = Path(temporary) / "trillionnium-ui/session.sock"
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("TRILL_") and key not in ("DISPLAY", "WAYLAND_DISPLAY")}
    env.update(XDG_RUNTIME_DIR=temporary, TRILL_OBJECTIVE_HOST_SOCKET=str(endpoint),
               TRILL_OBJECTIVE_HOST_PID=str(os.getpid()))
    stop = threading.Event()
    calls, failures, held, peers = [], [], [], []
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    listener.bind(str(endpoint))
    endpoint.chmod(0o600)
    listener.listen(8)
    listener.settimeout(0.1)

    def stalled_endpoint():
        try:
            while not stop.is_set():
                try:
                    peer, _ = listener.accept()
                except socket.timeout:
                    continue
                held.append(peer)
                peer.settimeout(1)
                pid, uid, _ = struct.unpack("3i", peer.getsockopt(
                    socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
                require(pid == process.pid and uid == os.geteuid(),
                        "synthetic endpoint received an unexpected peer")
                kind, command = receive(peer)
                require(kind == "response" and command == {"type": "availability"},
                        "synthetic endpoint received a non-availability request")
                calls.append(time.monotonic())
                # Keep each accepted stream open: the real bridge must use
                # its own 150 ms timeout rather than an artificial quick EOF.
        except Exception as error:
            failures.append(str(error))

    with (Path(temporary) / "session.log").open("wb") as logs:
        process = subprocess.Popen([str(binary)], env=env, cwd=temporary,
                                   stdin=subprocess.DEVNULL, stdout=logs,
                                   stderr=subprocess.STDOUT, close_fds=True)
        thread = threading.Thread(target=stalled_endpoint)
        thread.start()
        try:
            deadline = time.monotonic() + 5
            while not session_path.is_socket():
                require(process.poll() is None, "isolated Session exited before bind")
                require(time.monotonic() < deadline, "isolated Session did not bind")
                time.sleep(0.01)
            with connect(session_path) as initial:
                generation = snapshot(initial)

            # Connect four query peers, the affected snapshot, then a barrier.
            # The barrier's reply proves all preceding peers were accepted
            # and their original deadlines started; no scheduling sleep is
            # used to claim that they were already in the Session queue.
            for _ in range(5):
                peers.append(connect(session_path))
            with connect(session_path) as barrier:
                require(snapshot(barrier) == generation, "Session generation changed")
            started = time.monotonic()
            for peer in peers[:4]:
                send(peer, {"type": "objective_availability", "expected_instance": generation})
            send(peers[4], {"type": "snapshot"})
            kind, response = receive(peers[4])
            elapsed = time.monotonic() - started
            report.update(snapshot_outcome=kind, snapshot_wait_seconds=elapsed,
                          objective_availability_calls=len(calls),
                          objective_call_offsets_seconds=[value - started for value in calls])
            require(not failures, f"synthetic endpoint failed: {failures}")
            if expected == "serialized":
                require(len(calls) == 4, "fixture did not observe four actual bridge exchanges")
                require(kind in ("eof", "reset") and response is None,
                        "snapshot expiry was not reproduced on this binary/run")
                require(elapsed >= 0.5, "snapshot closed before the expected serialized delay")
                status = "limitation_reproduced"
            else:
                require(kind == "response" and response["type"] == "snapshot",
                        "stalled Objective queries blocked a local snapshot")
                require(response["session_instance"] == generation and not response["tasks"],
                        "snapshot changed generation or fabricated a task")
                require(elapsed < 0.5, "snapshot missed its original exchange allowance")
                query_outcomes = []
                for peer in peers[:4]:
                    query_kind, query = receive(peer)
                    require(query_kind == "response", "bounded Objective query lost its reply")
                    require(query["session_instance"] == generation, "query generation changed")
                    if query["type"] == "objective_transport_rejected":
                        require(query["rejection"] == {"request": {"type": "availability"}, "reason": "capacity"},
                                "capacity must be an exact local availability refusal")
                        query_outcomes.append({"local_transport_rejection": "capacity"})
                    else:
                        require(query["type"] == "objective", "unexpected Objective reply kind")
                        observation = query["observation"]
                        require(observation["client_intent_id"] is None
                                and observation["stage"] == "unavailable"
                                and observation["issue"] == "transport_unknown"
                                and observation["run"] is None,
                                "stalled read asserted an owner result")
                        query_outcomes.append({"stage": observation["stage"], "issue": observation["issue"]})
                require(1 <= len(calls) <= 2, "bounded FIFO admitted too many exchanges")
                require(not failures, f"synthetic endpoint failed: {failures}")
                report.update(query_outcomes=query_outcomes, objective_availability_calls=len(calls),
                              objective_call_offsets_seconds=[value - started for value in calls])
                status = "responsive"
            with connect(session_path) as recovery:
                require(snapshot(recovery) == generation, "Session did not recover in place")
            report.update(status=status, same_session_generation=True,
                          task_count_before=0, task_count_after=0)
        finally:
            stop.set()
            for peer in peers:
                peer.close()
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
            thread.join(timeout=2)
            listener.close()
            for peer in held:
                peer.close()
            require(not thread.is_alive(), "synthetic endpoint did not stop")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session_binary", type=Path)
    parser.add_argument("--expect", choices=("serialized", "responsive"), default="serialized")
    args = parser.parse_args()
    report = {"status": "inconclusive", "profile": "synthetic-stalled-objective-availability",
              "host_only_no_effect_dispatch": True, "production_authority": False,
              "product_acceptance": False, "expectation": args.expect}
    try:
        require(hasattr(socket, "SO_PEERCRED"), "this reproducer requires Linux SO_PEERCRED")
        binary = args.session_binary.resolve(strict=True)
        with binary.open("rb") as handle:
            digest = hashlib.file_digest(handle, "sha256").hexdigest()
        report.update(session_binary=str(binary), session_binary_sha256=digest)
        with tempfile.TemporaryDirectory(prefix="trill-objective-delay-") as temporary:
            reproduce(binary, temporary, report, args.expect)
    except Exception as error:
        report["status"] = "inconclusive"
        report["error"] = str(error)
    print(json.dumps(report, sort_keys=True))
    return 0 if report["status"] in ("limitation_reproduced", "responsive") else 1


if __name__ == "__main__":
    raise SystemExit(main())
