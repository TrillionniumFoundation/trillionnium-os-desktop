#!/usr/bin/env python3
"""Actual isolated Session: incomplete peers cannot occupy the single owner loop.

No graphical session, device, grant or original Hepta owner is started.
"""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time


def require(condition, why):
    if not condition:
        raise AssertionError(why)


def snapshot(path):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2)
        client.connect(str(path))
        started = time.monotonic()
        client.sendall(b'{"type":"snapshot"}\n')
        raw = bytearray()
        while not raw.endswith(b"\n"):
            remaining = 65536 - len(raw)
            require(remaining > 0, "unbounded Session response")
            part = client.recv(remaining)
            require(part, "Session closed a valid snapshot without its reply")
            raw.extend(part)
        response = json.loads(raw)
        require(response["type"] == "snapshot", "valid snapshot was refused")
        require(not response["tasks"], "read-only fixture unexpectedly created a task")
        return time.monotonic() - started, response["session_instance"]


def main():
    binary = Path(sys.argv[1]).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="trill-ipc-fair-") as temporary:
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = temporary
        for key in list(env):
            if key.startswith(("TRILL_HEPTA_", "TRILL_OBJECTIVE_")):
                env.pop(key)
        env.pop("DISPLAY", None)
        env.pop("WAYLAND_DISPLAY", None)
        path = Path(temporary) / "trillionnium-ui/session.sock"
        peers = []
        stop = threading.Event()
        thread = None
        with (Path(temporary) / "session.log").open("wb") as logs:
            process = subprocess.Popen(
                [str(binary)], env=env, stdin=subprocess.DEVNULL,
                stdout=logs, stderr=subprocess.STDOUT
            )
            try:
                deadline = time.monotonic() + 5
                while not path.is_socket():
                    require(process.poll() is None, "isolated Session exited before bind")
                    require(time.monotonic() < deadline, "isolated Session did not bind")
                    time.sleep(0.01)
                _, generation = snapshot(path)
                slow = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                slow.settimeout(1)
                slow.connect(str(path))
                slow.sendall(b'{"type":')
                peers.append(slow)

                def drip():
                    while not stop.wait(0.05):
                        try:
                            slow.sendall(b" ")
                        except OSError:
                            return

                thread = threading.Thread(target=drip)
                thread.start()
                during, observed = snapshot(path)
                require(observed == generation, "Session restarted during partial input")
                # The other request must finish while this incomplete peer is
                # still pending, rather than waiting for its 500 ms expiry.
                slow.setblocking(False)
                try:
                    slow.recv(1)
                except BlockingIOError:
                    pass
                else:
                    raise AssertionError("snapshot waited for the partial peer to close")
                stop.set()
                thread.join(timeout=1)
                require(not thread.is_alive(), "drip fixture failed to stop")
                slow.settimeout(1)
                try:
                    require(slow.recv(1) == b"", "incomplete frame must expire")
                except ConnectionResetError:
                    pass  # Closing a socket with unread partial bytes may reset it.

                for _ in range(32):
                    peer = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
                    peer.settimeout(2)
                    peer.connect(str(path))
                    peers.append(peer)
                crowded, observed = snapshot(path)
                require(observed == generation, "Session restarted under idle peers")
                require(crowded < 1.5, f"idle peers were served serially: {crowded:.3f}s")
                print(json.dumps({
                    "status": "passed",
                    "snapshot_during_partial_input_seconds": during,
                    "snapshot_with_32_idle_peers_seconds": crowded,
                    "same_session_generation": True,
                    "host_only_no_effect_dispatch": True,
                }))
            finally:
                stop.set()
                for peer in peers:
                    peer.close()
                if thread is not None:
                    thread.join(timeout=1)
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)


if __name__ == "__main__":
    main()
