#!/usr/bin/env python3
"""Actual Session/facade/UDS integration with an explicit scripted v2 fixture.

This does not start upstream Agentd, submit an objective, or exercise a device.
Only private processes/directories created by this invocation are stopped.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import socket
import subprocess
import sys
import tempfile
import time


ROOT = Path(__file__).resolve().parents[2]
MAX_FRAME = 65_536


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def request(address, message):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
        stream.settimeout(0.75)
        stream.connect(str(address))
        stream.sendall(json.dumps(message, separators=(",", ":")).encode() + b"\n")
        with stream.makefile("rb") as reader:
            frame = reader.readline(MAX_FRAME + 1)
        require(frame.endswith(b"\n") and len(frame) <= MAX_FRAME, "invalid Session frame")
        return json.loads(frame)


def wait_projection(address, process, connection, seconds=8):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        require(process.poll() is None, "Session exited before observation")
        try:
            response = request(address, {"type": "snapshot"})
            if response.get("type") == "snapshot" and response["hepta"]["connection"] == connection:
                return response
        except (OSError, KeyError):
            pass
        time.sleep(0.05)
    raise RuntimeError(f"Session did not report {connection} before the deadline")


def stop(process):
    if process is not None and process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--session", type=Path, required=True, help="compiled trill-session")
    parser.add_argument("--fixture", type=Path, default=ROOT / "tests/integration/hepta/agentd_fixture.py")
    parser.add_argument("--output", type=Path, required=True, help="JSON evidence destination")
    args = parser.parse_args()
    session_binary, fixture_source = args.session.resolve(), args.fixture.resolve()
    require(session_binary.is_file() and os.access(session_binary, os.X_OK), "Session executable missing")
    require(fixture_source.is_file(), "A07 scripted fixture source missing")
    runtime = Path(tempfile.mkdtemp(prefix="trill-hepta-probe-"))
    fixture = session = None
    evidence = {
        "evidence_class": "scripted_socket_fixture_not_hepta_daemon",
        "upstream_agentd_started": False,
        "objective_submitted": False,
        "device_effect_tested": False,
        "session_binary_sha256": digest(session_binary),
        "fixture_source_sha256": digest(fixture_source),
        "started_unix_ms": time.time_ns() // 1_000_000,
    }
    try:
        with (runtime / "fixture.log").open("wb") as fixture_log, (runtime / "session.log").open("wb") as session_log:
            fixture = subprocess.Popen(
                [sys.executable, str(fixture_source)], stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=fixture_log,
            )
            with selectors.DefaultSelector() as selector:
                selector.register(fixture.stdout, selectors.EVENT_READ)
                require(bool(selector.select(timeout=3)), "fixture startup timed out")
            line = fixture.stdout.readline(MAX_FRAME + 1)
            if not line.endswith(b"\n") or len(line) > MAX_FRAME:
                diagnostic = (runtime / "fixture.log").read_text(encoding="utf-8", errors="replace")[-2000:]
                raise RuntimeError(f"invalid fixture configuration; fixture diagnostic: {diagnostic}")
            config = json.loads(line)
            require(config["evidence_class"] == evidence["evidence_class"], "fixture provenance missing")
            require(config["process_id"] == fixture.pid, "fixture process identity mismatch")
            environment = os.environ.copy()
            environment.update({
                "XDG_RUNTIME_DIR": str(runtime),
                "TRILL_HEPTA_AGENTD_SOCKET": config["socket_path"],
                "TRILL_HEPTA_AGENT_ID": config["agent_id"],
                "TRILL_HEPTA_SPAWN_GENERATION": str(config["spawn_generation"]),
                "TRILL_HEPTA_PEER_UID": str(config["peer_uid"]),
            })
            session = subprocess.Popen(
                [str(session_binary)], env=environment, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=session_log,
            )
            address = runtime / "trillionnium-ui/session.sock"
            observed = wait_projection(address, session, "observed")
            projection = observed["hepta"]
            last = projection["last_observation"]
            require(last["agent_id"] == config["agent_id"], "AgentId mismatch")
            require(last["spawn_generation"] == config["spawn_generation"], "generation mismatch")
            require(last["health"]["process_id"] == fixture.pid, "kernel-correlated PID missing")
            require(last["health"]["ready"] and not last["health"]["fenced"], "fixture health mismatch")
            require([event["cursor"] for event in last["events"]] == [1, 2, 3], "fixture events missing")
            require(observed["tasks"] == [], "runtime observation synthesized host work")
            serialized = json.dumps(projection)
            require(all(forbidden not in serialized for forbidden in [
                "socket_path", "home_root", "run_root", "workspace", "/private-fixture/",
            ]), "private Agentd context leaked into renderer projection")
            # An advertised objective.start capability does not create an IPC
            # submission path. The real Session must reject these messages.
            for message in [
                {"type": "objective_start", "text": "test fixture text"},
                {"type": "agentd_rpc", "method": "run_start"},
            ]:
                require(request(address, message).get("type") == "error", "renderer acquired a write path")
            evidence["observed"] = projection
            stop(fixture)
            stale = wait_projection(address, session, "stale")
            stale_last = stale["hepta"]["last_observation"]
            require(stale_last["agent_id"] == last["agent_id"], "stale view lost identity")
            require(stale_last["health"] == last["health"], "stale view invented health")
            require(stale_last["events"] == last["events"], "stale view lost prior event evidence")
            require(stale_last["sampled_unix_ms"] >= last["sampled_unix_ms"], "observation timestamp regressed")
            require(stale["tasks"] == [], "disconnect synthesized task state")
            before = time.monotonic()
            cancelled = request(address, {
                "type": "cancel", "id": 2**64 - 1,
                "expected_instance": stale["session_instance"],
            })
            elapsed_ms = round((time.monotonic() - before) * 1000, 3)
            require(cancelled.get("type") == "error", "unknown host task must be rejected")
            require(elapsed_ms < 750, "Agentd outage blocked host action dispatch")
            evidence["stale"] = stale["hepta"]
            evidence["host_action_after_disconnect_ms"] = elapsed_ms
            evidence["renderer_write_requests_rejected"] = True
            evidence["passed"] = True
    finally:
        stop(session)
        stop(fixture)
        shutil.rmtree(runtime)
    evidence["finished_unix_ms"] = time.time_ns() // 1_000_000
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"PASS: Session/facade/UDS fixture observation and stale-state retention; evidence={args.output}")
    print("This run did not start upstream Agentd, submit an objective, or exercise a device.")


if __name__ == "__main__":
    main()
