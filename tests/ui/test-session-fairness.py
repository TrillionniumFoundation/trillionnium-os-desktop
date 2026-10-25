#!/usr/bin/env python3
"""Actual isolated Session: slow frames cannot monopolize the single state owner."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time


def main():
    binary = Path(sys.argv[1]).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix="trill-ipc-fair-") as temporary:
        env = os.environ.copy()
        env["XDG_RUNTIME_DIR"] = temporary
        for key in list(env):
            if key.startswith("TRILL_HEPTA_"):
                env.pop(key)
        process = subprocess.Popen([str(binary)], env=env, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        path = Path(temporary) / "trillionnium-ui/session.sock"
        peers = []
        try:
            deadline = time.monotonic() + 5
            while not path.exists():
                if process.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError("isolated Session did not start")
                time.sleep(.01)
            slow = socket.socket(socket.AF_UNIX)
            slow.connect(str(path))
            slow.sendall(b"{")
            peers.append(slow)
            stop = threading.Event()
            def drip():
                while not stop.wait(.1):
                    try:
                        slow.sendall(b" ")
                    except OSError:
                        return
            thread = threading.Thread(target=drip)
            thread.start()
            def snapshot():
                with socket.socket(socket.AF_UNIX) as client:
                    client.settimeout(1.5)
                    client.connect(str(path))
                    start = time.monotonic()
                    client.sendall(b'{"type":"snapshot"}\n')
                    raw = b""
                    while not raw.endswith(b"\n"):
                        part = client.recv(65536-len(raw))
                        if not part:
                            raise RuntimeError("Session closed valid request")
                        raw += part
                    if json.loads(raw)["type"] != "snapshot":
                        raise RuntimeError("valid snapshot was refused")
                    return time.monotonic()-start
            time.sleep(.1)
            during = snapshot()
            stop.set()
            thread.join()
            slow.settimeout(1)
            # Total deadline closes the unterminated frame, even after its bytes arrived.
            assert slow.recv(1) == b"", "incomplete frame must expire"
            for _ in range(32):
                peer = socket.socket(socket.AF_UNIX)
                peer.settimeout(2)
                peer.connect(str(path))
                peers.append(peer)
            crowded = snapshot()
            assert during < 1, f"slow client monopolized Session: {during}"
            assert crowded < 1.5, f"bounded peers failed to expire: {crowded}"
            print(json.dumps({"status":"passed", "snapshot_during_drip_seconds":during,
                              "snapshot_with_32_idle_peers_seconds":crowded}))
        finally:
            for peer in peers:
                peer.close()
            process.terminate()
            process.communicate(timeout=3)


if __name__ == "__main__":
    main()
