#!/usr/bin/env python3
"""Actual Rust Session and Hepta-page layout against a scripted UDS fixture.

Requires an existing test-owned Wayland compositor. A generic Shell first
frame cannot satisfy this probe. This is an egui layout observation, not
upstream Agentd, compositor pixel presentation, a model request or a device
effect. Only child processes and temporary directories owned here are stopped.
"""

import argparse
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
MAX_FRAME = 65_536
PREFIX = b"TRILL_HEPTA_LAYOUT_V1 "
CONFIG_KEYS = (
    "TRILL_HEPTA_AGENTD_SOCKET", "TRILL_HEPTA_AGENT_ID",
    "TRILL_HEPTA_SPAWN_GENERATION", "TRILL_HEPTA_PEER_UID",
)


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


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


def snapshot(address):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
        stream.settimeout(0.75)
        stream.connect(str(address))
        stream.sendall(b'{"type":"snapshot"}\n')
        with stream.makefile("rb") as reader:
            frame = reader.readline(MAX_FRAME + 1)
    require(frame.endswith(b"\n") and len(frame) <= MAX_FRAME, "invalid Session frame")
    value = json.loads(frame)
    require(value.get("type") == "snapshot", "Session did not return a snapshot")
    return value


def wait_observed(address, session):
    deadline = time.monotonic() + 8
    while time.monotonic() < deadline:
        require(session.poll() is None, "Session exited before observation")
        try:
            value = snapshot(address)
            if value["hepta"]["connection"] == "observed":
                return value
        except (OSError, KeyError):
            pass
        time.sleep(0.05)
    raise RuntimeError("Session did not observe the scripted Agentd fixture")


def read_marker(path):
    require(path.stat().st_size <= MAX_FRAME, "Shell stdout exceeded probe bound")
    markers = [line[len(PREFIX):] for line in path.read_bytes().split(b"\n")[:-1] if line.startswith(PREFIX)]
    require(len(markers) <= 1, "Hepta layout marker must be emitted once")
    return json.loads(markers[0]) if markers else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binaries", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="new evidence directory")
    args = parser.parse_args()
    binaries = args.binaries.resolve()
    session_binary, shell_binary = binaries / "trill-session", binaries / "trill-shell"
    fixture_source = ROOT / "tests/integration/hepta/agentd_fixture.py"
    for executable in (session_binary, shell_binary):
        require(executable.is_file() and os.access(executable, os.X_OK), "compiled UI executable missing")
    require(fixture_source.is_file(), "scripted A07 fixture source missing")
    display_name, xdg = os.environ.get("WAYLAND_DISPLAY"), os.environ.get("XDG_RUNTIME_DIR")
    require(display_name and xdg, "test Wayland environment missing")
    display = Path(display_name)
    if not display.is_absolute():
        display = Path(xdg) / display
    display = display.absolute()
    require(stat.S_ISSOCK(display.stat().st_mode), "test compositor path is not a socket")
    output = args.output.resolve()
    require(not output.exists() or not any(output.iterdir()), "evidence directory must be empty")
    output.mkdir(parents=True, exist_ok=True)
    runtime = Path(tempfile.mkdtemp(prefix="trill-hepta-layout-"))
    fixture = session = shell = None
    evidence = {
        "evidence_class": "scripted_socket_fixture_hepta_page_layout_not_daemon",
        "upstream_agentd_started": False,
        "objective_submitted": False,
        "device_effect_tested": False,
        "compositor_pixel_presentation_verified": False,
        "session_binary_sha256": digest(session_binary),
        "shell_binary_sha256": digest(shell_binary),
        "fixture_source_sha256": digest(fixture_source),
        "started_unix_ms": time.time_ns() // 1_000_000,
        "passed": False,
    }
    try:
        with (output / "fixture.stderr.log").open("wb") as fixture_log, \
                (output / "session.stderr.log").open("wb") as session_log, \
                (output / "shell.stdout.log").open("wb") as shell_stdout, \
                (output / "shell.stderr.log").open("wb") as shell_stderr:
            fixture = subprocess.Popen(
                [sys.executable, str(fixture_source)], stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=fixture_log,
            )
            with selectors.DefaultSelector() as selector:
                selector.register(fixture.stdout, selectors.EVENT_READ)
                require(bool(selector.select(timeout=3)), "fixture startup timed out")
            line = fixture.stdout.readline(MAX_FRAME + 1)
            require(line.endswith(b"\n") and len(line) <= MAX_FRAME, "invalid fixture configuration")
            config = json.loads(line)
            require(config["evidence_class"] == "scripted_socket_fixture_not_hepta_daemon", "fixture provenance missing")
            require(config["process_id"] == fixture.pid, "fixture process identity mismatch")
            common_env = os.environ.copy()
            common_env.pop("DISPLAY", None)
            for key in CONFIG_KEYS:
                common_env.pop(key, None)
            common_env.update({"XDG_RUNTIME_DIR": str(runtime), "WAYLAND_DISPLAY": str(display)})
            session_env = common_env.copy()
            session_env.update(dict(zip(CONFIG_KEYS, (
                config["socket_path"], config["agent_id"],
                str(config["spawn_generation"]), str(config["peer_uid"]),
            ))))
            session = subprocess.Popen(
                [str(session_binary)], env=session_env, stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL, stderr=session_log,
            )
            address = runtime / "trillionnium-ui/session.sock"
            first = wait_observed(address, session)
            require(first["tasks"] == [], "observation fabricated a host task")
            shell = subprocess.Popen(
                [str(shell_binary), "--page", "hepta", "--hepta-layout-probe"],
                env=common_env, stdin=subprocess.DEVNULL,
                stdout=shell_stdout, stderr=shell_stderr,
            )
            evidence["session_process_id"] = session.pid
            evidence["shell_process_id"] = shell.pid
            deadline = time.monotonic() + 15
            marker = None
            while time.monotonic() < deadline:
                require(session.poll() is None and shell.poll() is None, "Rust UI process exited before Hepta page layout")
                marker = read_marker(output / "shell.stdout.log")
                if marker is not None:
                    break
                time.sleep(0.05)
            require(marker is not None, "Hepta page never emitted a fresh observed layout; a generic Shell first frame is insufficient")
            require(marker["page"] == "hepta" and marker["connection"] == "observed", "wrong page or connection in layout marker")
            require(marker["agent_id"] == config["agent_id"], "layout AgentId mismatch")
            require(marker["spawn_generation"] == config["spawn_generation"], "layout spawn mismatch")
            require(marker["process_id"] == fixture.pid, "layout kernel-correlated Agentd PID mismatch")
            now_ms = time.time_ns() // 1_000_000
            require(evidence["started_unix_ms"] <= marker["sampled_unix_ms"] <= now_ms, "layout sampling time is outside this run")
            require(now_ms - marker["sampled_unix_ms"] <= 7_000, "layout used an expired observation")
            after = snapshot(address)
            last = after["hepta"]["last_observation"]
            require(after["hepta"]["connection"] == "observed", "Session no longer has an observed projection")
            require(last["agent_id"] == marker["agent_id"] and last["spawn_generation"] == marker["spawn_generation"], "Session/layout source mismatch")
            require(last["current_generation"] == marker["current_generation"], "Session/layout current generation mismatch")
            require(last["health"]["process_id"] == marker["process_id"], "Session/layout peer mismatch")
            require(last["sampled_unix_ms"] >= marker["sampled_unix_ms"], "layout observation is newer than its Session source")
            require(after["tasks"] == [], "Hepta layout synthesized a host task")
            time.sleep(0.2)
            require(shell.poll() is None, "Shell exited after layout")
            require(read_marker(output / "shell.stdout.log") == marker, "layout marker changed or was repeated")
            evidence["hepta_layout"] = marker
            evidence["session_projection_after_layout"] = after["hepta"]
            evidence["passed"] = True
    except Exception as error:
        evidence["failure"] = str(error)
        raise
    finally:
        stop(shell)
        stop(session)
        stop(fixture)
        shutil.rmtree(runtime)
        evidence["finished_unix_ms"] = time.time_ns() // 1_000_000
        (output / "evidence.json").write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print("PASS: actual Rust Hepta-page egui layout consumed a fresh Session projection from the scripted UDS fixture")
    print("Not upstream Agentd, compositor pixel presentation, objective submission or device-effect evidence.")


if __name__ == "__main__":
    main()
