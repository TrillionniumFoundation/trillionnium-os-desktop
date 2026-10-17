#!/usr/bin/env python3
"""Strict wire-request host acceptance against an ACTUAL Rust Session ELF.

No compositor, HOS2 authority or privileged device is exercised here.
"""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time


def require(condition, why):
    if not condition:
        raise AssertionError(why)


def roundtrip(path, request):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as peer:
        peer.settimeout(2.0)
        peer.connect(str(path))
        peer.sendall(request + b"\n")
        raw = bytearray()
        while not raw.endswith(b"\n"):
            chunk = peer.recv(8192)
            require(chunk, "session closed without responding")
            raw.extend(chunk)
            require(len(raw) < 65536, "unbounded Session response")
    return json.loads(raw)


def check(binary_dir):
    binary_dir = Path(binary_dir).resolve()
    session = binary_dir / "trill-session"
    app = binary_dir / "trill-app-window"
    require(session.is_file() and os.access(session, os.X_OK), "missing real Session binary")
    require(app.is_file() and os.access(app, os.X_OK), "missing real AppWindow binary")
    with tempfile.TemporaryDirectory(prefix="a10-strict-wire-") as root:
        runtime = Path(root) / "runtime"
        runtime.mkdir(mode=0o700)
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = str(runtime)
        env.pop("DISPLAY", None)
        env.pop("WAYLAND_DISPLAY", None)
        sock = runtime / "trillionnium-ui/session.sock"
        with open(Path(root) / "session.log", "wb") as logs:
            proc = subprocess.Popen([str(session)], env=env, stdout=logs, stderr=subprocess.STDOUT)
            try:
                for _ in range(100):
                    if sock.is_socket():
                        break
                    require(proc.poll() is None, "Rust Session failed to start")
                    time.sleep(0.05)
                require(sock.is_socket(), "Rust Session did not open its IPC socket")
                initial = roundtrip(sock, b'{"type":"snapshot"}')
                require(initial.get("type") == "snapshot" and not initial["tasks"], "baseline snapshot invalid")
                generation = initial["session_instance"]
                malformed = [
                    b'{"type":"snapshot","data":[1]}',
                    b'{"type":"snapshot","type":"snapshot"}',
                    b'{"type":"snapshot","expected_instance":"decoy"}',
                    (b'{"type":"launch","workspace":"research","app":"notes",'
                     b'"expected_instance":"' + generation.encode() + b'","injected":true}'),
                    (b'{"type":"launch","workspace":"research","workspace":"build",'
                     b'"app":"notes","expected_instance":"' + generation.encode() + b'"}'),
                    (b'{"type":"cancel","id":1,"expected_instance":"' + generation.encode()
                     + b'","id":2}'),
                    (b'{"type":"cancel","id":1,"expected_instance":"' + generation.encode()
                     + b'","unknown":"payload"}'),
                    b'{"type":"not_an_operation"}',
                ]
                for idx, payload in enumerate(malformed):
                    response = roundtrip(sock, payload)
                    require(response.get("type") == "error", f"REJECT_FAIL_CASE_{idx}: {response}")
                    require(response.get("session_instance") == generation, "session generation changed")
                    require("Invalid IPC request" in response.get("message", ""),
                            f"case {idx}: refused for unrelated reason")
                after = roundtrip(sock, b'{"type":"snapshot"}')
                require(after["type"] == "snapshot" and not after["tasks"],
                        "malformed requests changed host task state")
                # A malformed Launch may briefly spawn a child and exit
                # before the following Snapshot. Guard on Session's durable
                # next-id allocation too: the first legitimate host launch
                # must still get ID 1, not silently skip an effected request.
                legitimate = roundtrip(
                    sock,
                    (b'{"type":"launch","workspace":"research","app":"notes",'
                     b'"expected_instance":"' + generation.encode() + b'"}'),
                )
                require(legitimate["type"] == "task", "valid Launch should reach host Session")
                task = legitimate["task"]
                require(task["id"] == 1, "malformed Launch consumed a task ID or spawned a child")
                require(task["workspace"] == "research" and task["app"] == "notes",
                        "valid Launch was rewritten by a forged request")
                # Headless GUI is allowed to fail, but only the Session can
                # observe the actual child outcome. No Hepta success is implied.
                require(task["state"] in ("running", "failed"),
                        "unexpected Session response for real host child")
                if task["state"] == "running":
                    cancel = roundtrip(
                        sock,
                        (b'{"type":"cancel","id":1,"expected_instance":"'
                         + generation.encode() + b'"}'),
                    )
                    require(cancel.get("session_instance") == generation, "Cancel crossed Session instances")
                    child_already_exited = cancel.get("type") == "error"
                    if child_already_exited:
                        # With no display the real AppWindow can fail between
                        # Launch and Cancel. Session refreshes/reaps before
                        # handling Cancel, so it must NOT invent an ACK for a
                        # child it no longer owns. Accept only this exact race
                        # and require the same child's observed FAILED state.
                        require(cancel.get("message") == "No owned live child; no cancellation claimed",
                                f"Cancel failed for an unrelated reason: {cancel}")
                    else:
                        require(cancel.get("type") == "task", f"invalid Cancel response: {cancel}")
                        require(cancel["task"]["id"] == 1 and cancel["task"]["pid"] == task["pid"],
                                "Cancel acknowledged a different child")
                    for _ in range(100):
                        time.sleep(0.02)
                        snapshot = roundtrip(sock, b'{"type":"snapshot"}')
                        require(snapshot["session_instance"] == generation, "cleanup crossed Session instances")
                        last = next(t for t in snapshot["tasks"] if t["id"] == 1)
                        require(last["pid"] == task["pid"], "cleanup changed the owned child PID")
                        if last["state"] in ("cancelled", "failed", "completed"):
                            break
                    else:
                        raise AssertionError("real launched child was not reaped")
                    if child_already_exited:
                        require(last["state"] == "failed" and
                                "Observed non-successful process exit" in last["detail"],
                                "no-live-child rejection lacked the same child's observed headless failure")
                else:
                    require(task["state"] == "failed", "GUI spawn failed with wrong host state")
                valid_cancel = roundtrip(sock, (b'{"type":"cancel","id":999,"expected_instance":"'
                                               + generation.encode() + b'"}'))
                require(valid_cancel["type"] == "error" and "task 999 does not exist" in valid_cancel["message"],
                        "valid Cancel was confused with schema rejection")
                require(proc.poll() is None, "Rust Session died after malformed IPC")
                print("A10 STRICT REQUEST IPC PASS: 8 forged frames rejected, first legitimate Launch remains ID 1, observed child cleanup, typed Cancel")
            finally:
                if proc.poll() is None:
                    proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: a10_test_strict_ipc.py <real Rust binary directory>")
    check(sys.argv[1])
