#!/usr/bin/env python3
"""Scripted pinned-v2 socket fixture. This is NOT Hepta Agentd or an effect owner.

Launch for a Session → facade → real Linux UDS projection test. The first stdout
line is fixture configuration. Terminate this process to exercise stale state.
Only the four already-supported read methods are recognized. All data is test
data; no model, authorization, operation persistence, or device effect runs.
"""

import json
import os
from pathlib import Path
import shutil
import signal
import socket
import tempfile


ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / "services/hepta-os/tests/fixtures/agentd_v2_payloads.json"
AGENT = "11111111-1111-4111-8111-111111111111"
GENERATION = 7
MAX_FRAME = 65_536


def payload_for(method, fixtures):
    kind = method.get("type")
    if kind == "health" and set(method) == {"type"}:
        payload = fixtures["health"].copy()
        payload["process_id"] = os.getpid()
        return payload
    if kind == "capabilities" and set(method) == {"type"}:
        return fixtures["capabilities"]
    if kind == "events" and set(method) == {"type", "after_cursor", "limit"}:
        after, limit = method["after_cursor"], method["limit"]
        if type(after) is not int or not 0 <= after < 2**64 or type(limit) is not int or not 1 <= limit <= 256:
            raise ValueError("invalid fixture cursor")
        retained = fixtures["events"]["events"]
        page = [event for event in retained if event["cursor"] > after][:limit]
        return {
            "type": "events", "events": page, "gap": False,
            "next_cursor": page[-1]["cursor"] if page else after,
            "latest_cursor": retained[-1]["cursor"],
        }
    if kind == "run_status" and set(method) == {"type", "run_id"}:
        if method["run_id"] == "fixture:run-1":
            return fixtures["run_status"]
        return {"type": "run_status", "run": None}
    raise ValueError("method outside fixture read subset")


def main():
    fixtures = json.loads(FIXTURES.read_text(encoding="utf-8"))
    directory = Path(tempfile.mkdtemp(prefix="hepta-v2-fixture-"))
    address = directory / "control.sock"
    listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    stopping = False

    def stop(_signal, _frame):
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        listener.bind(str(address))
        address.chmod(0o600)
        listener.listen(4)
        listener.settimeout(0.25)
        print(json.dumps({
            "evidence_class": "scripted_socket_fixture_not_hepta_daemon",
            "socket_path": str(address), "agent_id": AGENT,
            "spawn_generation": GENERATION, "peer_uid": os.getuid(), "process_id": os.getpid(),
        }), flush=True)
        while not stopping:
            try:
                connection, _ = listener.accept()
            except TimeoutError:
                continue
            with connection:
                connection.settimeout(2)
                try:
                    with connection.makefile("rb") as reader:
                        frame = reader.readline(MAX_FRAME + 1)
                    if not frame.endswith(b"\n") or len(frame) > MAX_FRAME:
                        continue
                    request = json.loads(frame)
                    if set(request) != {"schema_version", "request_id", "spawn_generation", "method"}:
                        continue
                    if request["schema_version"] != 2 or request["spawn_generation"] != GENERATION:
                        continue
                    payload = payload_for(request["method"], fixtures)
                    response = {
                        "schema_version": 2, "request_id": request["request_id"], "agent_id": AGENT,
                        "spawn_generation": GENERATION, "current_generation": GENERATION,
                        "payload": payload,
                    }
                    connection.sendall(json.dumps(response, separators=(",", ":")).encode() + b"\n")
                except (ValueError, TypeError, KeyError, OSError):
                    # Malformed fixture traffic is discarded, never dispatched.
                    continue
    finally:
        listener.close()
        shutil.rmtree(directory)


if __name__ == "__main__":
    main()
