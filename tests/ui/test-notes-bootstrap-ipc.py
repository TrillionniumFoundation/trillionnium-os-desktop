#!/usr/bin/env python3
"""Real Session/App private-FD bootstrap under an explicitly isolated display.

The parent ACK is a transport fixture, not Hepta authority or registration.
The inherited application channel is queried read-only; no grant is fabricated.
"""

import array
import contextlib
import fcntl
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


def require(value, message):
    if not value:
        raise RuntimeError(message)


def encode(value):
    return json.dumps(value, separators=(",", ":")).encode()


def child_identity(pid):
    try:
        stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return int(stat[1]), stat[19], os.readlink(f"/proc/{pid}/exe")
    except (FileNotFoundError, ProcessLookupError):
        return None


def owned_children(proc, app):
    try:
        pids = Path(f"/proc/{proc.pid}/task/{proc.pid}/children").read_text().split()
    except FileNotFoundError:
        return {}
    found = {}
    for value in pids:
        pid = int(value)
        identity = child_identity(pid)
        if identity and identity[0] == proc.pid and identity[2] == str(app):
            found[pid] = identity
    return found


@contextlib.contextmanager
def launched(binary_dir):
    with tempfile.TemporaryDirectory(prefix="trill-private-bootstrap-") as directory:
        root = Path(directory)
        runtime = root / "runtime"
        runtime.mkdir(mode=0o700)
        env = os.environ.copy()
        # Preserve only the exact compositor selected by the owned test
        # harness when the Session receives its separate private runtime.
        display = env.get("WAYLAND_DISPLAY")
        if display and not Path(display).is_absolute():
            env["WAYLAND_DISPLAY"] = str(Path(env["XDG_RUNTIME_DIR"]) / display)
        env["XDG_RUNTIME_DIR"] = str(runtime)
        for name in list(env):
            if name.startswith("TRILL_HEPTA_"):
                env.pop(name)
        parent, child = socket.socketpair(socket.AF_UNIX, socket.SOCK_DGRAM)
        parent.settimeout(4)
        app = binary_dir / "trill-app-window"
        with open(root / "session.log", "wb") as logs:
            proc = subprocess.Popen(
                [str(binary_dir / "trill-session"), "--notes-bootstrap-stdin"],
                stdin=child, stdout=logs, stderr=subprocess.STDOUT, env=env,
            )
            child.close()
            try:
                yield proc, parent, runtime / "trillionnium-ui/session.sock", app
            finally:
                # Only current exact descendants of this owned Session and
                # this built App executable may be stopped. Recheck identity
                # before each signal; terminate Session only after its apps.
                for pid, observed in owned_children(proc, app).items():
                    if child_identity(pid) == observed:
                        try:
                            os.kill(pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                for _ in range(40):
                    if not owned_children(proc, app):
                        break
                    time.sleep(0.025)
                if proc.poll() is None:
                    proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=3)
                parent.close()


def receive_offer(parent):
    descriptors = []
    try:
        raw, ancillary, flags, _ = parent.recvmsg(1025, socket.CMSG_SPACE(32), socket.MSG_CMSG_CLOEXEC)
        for level, kind, data in ancillary:
            require(level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS, "unexpected ancillary type")
            values = array.array("i")
            require(len(data) % values.itemsize == 0, "partial descriptor")
            values.frombytes(data)
            descriptors.extend(values)
        require(not flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC), "truncated bootstrap offer")
        require(0 < len(raw) <= 1024 and len(descriptors) == 1, "bootstrap bound or descriptor count")
        offer = json.loads(raw)
        require(set(offer) == {"schema_version", "action", "target", "destination_id"}, "offer fields")
        require(offer["schema_version"] == 1 and offer["action"] == "offer_notes_target", "offer action")
        identity = offer["target"]
        require(set(identity) == {"session_instance", "task_id", "incarnation"} and identity["task_id"] == 1,
                "only the fixed initial task can bootstrap")
        for key in ("session_instance", "incarnation"):
            require(len(identity[key]) == 32 and all(c in "0123456789abcdef" for c in identity[key]), "identity shape")
        expected = f"trill.notes:{identity['session_instance']}:1:{identity['incarnation']}"
        require(offer["destination_id"] == expected, "destination differs from target")
        fd = descriptors[0]
        require(fcntl.fcntl(fd, fcntl.F_GETFD) & fcntl.FD_CLOEXEC, "received descriptor lacks CLOEXEC")
        stream = socket.socket(fileno=fd)
        descriptors.clear()
        try:
            require(stream.getsockopt(socket.SOL_SOCKET, socket.SO_TYPE) == socket.SOCK_STREAM, "effect type")
            require(stream.family == socket.AF_UNIX and stream.getsockname() == "" and stream.getpeername() == "",
                    "effect is not a private unnamed Unix stream")
        except Exception:
            stream.close()
            raise
        stream.settimeout(2)
        return offer, stream
    finally:
        for fd in descriptors:
            os.close(fd)


def acknowledge(parent, offer, status):
    parent.send(encode({"schema_version": 1, "action": "notes_target_registration",
                        "target": offer["target"], "destination_id": offer["destination_id"], "status": status}))


def roundtrip(path, request):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as channel:
        channel.settimeout(3)
        channel.connect(str(path))
        channel.sendall(encode(request) + b"\n")
        raw = b""
        while not raw.endswith(b"\n"):
            part = channel.recv(65537 - len(raw))
            require(part and len(raw) + len(part) <= 65536, "public response frame bound")
            raw += part
        return json.loads(raw)


def read_exact(channel, length):
    raw = b""
    while len(raw) < length:
        part = channel.recv(length - len(raw))
        require(part, "application channel closed")
        raw += part
    return raw


def check(binary_dir):
    require(sys.platform == "linux", "Linux is required")
    require(os.environ.get("TRILL_NOTES_PROBE_ISOLATED") == "1"
            and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")),
            "run only inside an owned isolated Xvfb/Weston with TRILL_NOTES_PROBE_ISOLATED=1")
    binary_dir = Path(binary_dir).resolve()
    for binary in ("trill-session", "trill-app-window"):
        require(os.access(binary_dir / binary, os.X_OK), f"missing built {binary}")

    with launched(binary_dir) as (proc, parent, path, app):
        offer, endpoint = receive_offer(parent)
        with endpoint:
            initial_children = owned_children(proc, app)
            require(len(initial_children) == 1, "bootstrap must own exactly one initial Notes app")
            acknowledge(parent, offer, "rejected")
            require(proc.wait(timeout=5) != 0, "parent rejection must block Session startup")
            for pid, observed in initial_children.items():
                require(child_identity(pid) != observed, "rejected bootstrap left its Notes process alive")
            require(endpoint.recv(1) == b"", "rejected bootstrap left its effect channel open")

    with launched(binary_dir) as (proc, parent, path, app):
        offer, endpoint = receive_offer(parent)
        with endpoint:
            acknowledge(parent, offer, "attached")
            deadline = time.monotonic() + 10
            while True:
                snapshot = roundtrip(path, {"type": "snapshot"})
                require(snapshot["session_instance"] == offer["target"]["session_instance"], "Session identity changed")
                require(len(snapshot["tasks"]) == 1 and snapshot["tasks"][0]["id"] == 1, "initial task allocation changed")
                first = snapshot["tasks"][0]
                require(first["app"] == "notes" and first["workspace"] == "build", "wrong initial application")
                require(first["notes_destination"]["original_owner_registered"] is True, "private parent ACK not observed")
                require(first["state"] == "running", "initial Notes did not stay running")
                if first["ui_first_frame_unix_ms"] is not None:
                    break
                require(time.monotonic() < deadline, "initial Notes layout timed out")
                time.sleep(0.05)

            # Query the actual application through the received descriptor.
            # This has no mutation text and creates no operation or grant.
            query = {"schema_version": 1, "action": "observe", "target": offer["target"],
                     "operation_id": "qualification-bootstrap-read-only", "payload_sha256": "0" * 64}
            raw = encode(query)
            endpoint.sendall(struct.pack("!I", len(raw)) + raw)
            length = struct.unpack("!I", read_exact(endpoint, 4))[0]
            require(0 < length <= 2048, "application response bound")
            response = json.loads(read_exact(endpoint, length))
            require(response["target"] == offer["target"] and response["operation_id"] == query["operation_id"]
                    and response["payload_sha256"] == query["payload_sha256"], "query response correlation")
            require(response["result"] == {"status": "unknown", "current_revision": 0}, "bootstrap unexpectedly mutated Notes")

            for forged in ({"type": "notes_bootstrap", "fd": 0}, {"type": "offer_notes_target", "target": offer["target"]}):
                require(roundtrip(path, forged)["type"] == "error", "public IPC exposed private bootstrap")
            extra = roundtrip(path, {"type": "launch", "workspace": "research", "app": "notes",
                                     "expected_instance": snapshot["session_instance"]})
            require(extra["type"] == "task" and extra["task"]["id"] == 2, "normal launch allocation changed")
            require(extra["task"]["notes_destination"]["original_owner_registered"] is False,
                    "normal public launch must not export an endpoint")
            for task_id in (1, 2):
                roundtrip(path, {"type": "cancel", "id": task_id, "expected_instance": snapshot["session_instance"]})
            deadline = time.monotonic() + 5
            while True:
                ended = roundtrip(path, {"type": "snapshot"})
                if all(task["state"] in ("cancelled", "completed", "failed") for task in ended["tasks"]):
                    break
                require(time.monotonic() < deadline, "owned Notes cleanup not observed")
                time.sleep(0.05)
            require(not owned_children(proc, app), "owned Notes processes were not reaped")

    print(json.dumps({"profile": "isolated_session_bootstrap_transport_fixture", "private_fd_roundtrip": True,
                      "parent_rejection_blocks_startup_and_reaps_child": True, "initial_task_id": 1,
                      "public_launch_does_not_export": True, "actual_app_read_only_query": True,
                      "document_revision": 0, "hepta_production_owner_run": False,
                      "final_use_authority_run": False, "asterinas_run": False}, sort_keys=True))


if __name__ == "__main__":
    require(len(sys.argv) == 2, "usage: test-notes-bootstrap-ipc.py /absolute/binary/directory")
    check(sys.argv[1])
