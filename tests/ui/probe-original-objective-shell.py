#!/usr/bin/env python3
"""Capture one real Rust Shell across three original Objective Session phases.

The separate original_objective_probe owns admission, journal and both Session
instances. This consumer starts only a private Xvfb and one source-bound Shell.
PNG files are real XGetImage captures; every image still requires visual review.
The existing six-phase observer qualification is neither modified nor reused as
an Objective qualification claim.
"""

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import socket
import stat
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


legacy = load_module("original_objective_shell_reviewed_helpers",
    Path(__file__).with_name("probe-original-hepta-shell.py"))
require = legacy.require
digest = legacy.digest
now_ms = legacy.now_ms
positive_integer = legacy.positive_integer
private_directory = legacy.private_directory
acknowledge = legacy.acknowledge
bound_exec = legacy.bound_exec
PIN = legacy.PIN
LAYOUT_PREFIX = legacy.LAYOUT_PREFIX
MAX_FRAME = 65_536
PHASES = ("compiled_run_projected", "old_endpoint_run_stale", "replacement_run_projection_missing")
RUN_FIELDS = ("run_id", "revision", "phase", "authority_epoch", "generation", "terminal_observed", "idempotent")
HOST_TOOLS = ("bwrap", "Xvfb", "xauth", "xdpyinfo", "xdotool", "xprop", "xwininfo", "python3", "ldd")


def host_dependencies(root, shell):
    """Record this host's real tools and linked libraries, not a past package stage.

    The capture binds all of this host's /usr read-only. These hashes describe
    the selected executables and their ldd-resolved dependencies; dynamically
    loaded rendering drivers are exercised only by the subsequent real Shell.
    """
    require(root.is_absolute() and root.resolve(strict=True) == Path("/usr"),
        "explicit current host /usr dependency root required")
    metadata = root.stat()
    require(stat.S_ISDIR(metadata.st_mode) and not metadata.st_mode & 0o022,
        "host dependency root must not be group/world writable")
    files, tool_paths, dependencies = {}, {}, {}

    def record(path):
        resolved = path.resolve(strict=True)
        require(resolved.is_relative_to(root) and resolved.is_file(),
            "host dependency resolves outside the read-only /usr binding")
        value = resolved.stat()
        require(not value.st_mode & 0o022, "host dependency is group/world writable")
        files[str(resolved)] = {"bytes": value.st_size, "sha256": digest(resolved)}
        return resolved

    for name in HOST_TOOLS:
        path = root / "bin" / name
        resolved = record(path)
        require(os.access(resolved, os.X_OK), "host tool is not executable: " + name)
        if name != "ldd":
            with resolved.open("rb") as stream:
                require(stream.read(4) == b"\x7fELF", "native host tool required: " + name)
        tool_paths[name] = {"path": str(path), "resolved": str(resolved)}
    environment = {"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"}
    for name, path in [(name, Path(value["path"])) for name, value in tool_paths.items() if name != "ldd"] + [("trill-shell", shell)]:
        result = subprocess.run([str(root / "bin/ldd"), str(path)], stdin=subprocess.DEVNULL,
            env=environment, capture_output=True, timeout=10)
        require(result.returncode == 0 and len(result.stdout) <= MAX_FRAME
            and len(result.stderr) <= MAX_FRAME and b"not found" not in result.stdout,
            "host-linked dependency check failed: " + name)
        listing = result.stdout.decode("utf-8", errors="strict")
        dependencies[name] = {"argv": [str(root / "bin/ldd"), str(path)], "returncode": result.returncode,
            "stdout": listing, "stderr": result.stderr.decode("utf-8", errors="strict")}
        for line in listing.splitlines():
            match = re.search(r"(?:=>\s+|^\s*)(/[^\s]+)\s+\(", line)
            if match:
                record(Path(match.group(1)))
    return {"schema_version": 1, "source": "explicit_current_host_usr",
        "root": str(root), "recorded_unix_ms": now_ms(), "read_only_bind_required": True,
        "tools": tool_paths, "files": files, "linked_dependencies": dependencies,
        "package_stage_receipt_used": False, "system_install_performed_by_capture": False,
        "dynamic_rendering_driver_scope": "actual_capture_only_no_exhaustive_driver_manifest"}


def verify_dependency_files(report):
    for name, value in report.get("tools", {}).items():
        require(str(Path(value["path"]).resolve(strict=True)) == value["resolved"],
            "recorded host tool path changed during capture: " + name)
    for path, recorded in report["files"].items():
        current = Path(path)
        require(current.stat().st_size == recorded["bytes"] and digest(current) == recorded["sha256"],
            "recorded host dependency changed during capture: " + path)


def read_phase(path):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        metadata = os.fstat(stream.fileno())
        require(stat.S_ISREG(metadata.st_mode) and metadata.st_uid == os.geteuid()
            and stat.S_IMODE(metadata.st_mode) == 0o600 and metadata.st_nlink == 1
            and 0 < metadata.st_size <= MAX_FRAME, "phase must be an owned bounded single-link 0600 file")
        raw = stream.read(MAX_FRAME + 1)
    require(len(raw) <= MAX_FRAME, "phase grew beyond its bound")
    return json.loads(raw), raw


def run_fields(value):
    return {field: value[field] for field in RUN_FIELDS}


def run_history(value):
    # The source monotonic age advances even when the historical receipt does
    # not. Every other field remains exact within the held stale phase.
    return {field: item for field, item in value.items() if field != "sample_age_at_snapshot_ms"}


def projection(value, phase):
    require(value.get("type") == "snapshot" and value.get("tasks") == [],
        "actual task-free Session snapshot required")
    hepta = value["hepta"]
    require(hepta["connection"] == ("stale" if phase == PHASES[1] else "observed"),
        "unexpected original runtime connection state")
    observed = hepta["last_observation"]
    require(isinstance(observed, dict) and re.fullmatch(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", observed["agent_id"]),
        "exact original agent identity required")
    require(all(positive_integer(observed[field]) for field in
        ("spawn_generation", "current_generation", "sampled_unix_ms"))
        and positive_integer(observed["health"]["process_id"]), "bounded original runtime identity required")
    require(observed["health"]["lifecycle"] == "running"
        and observed["health"]["ready"] is True and observed["health"]["promotion_ready"] is True
        and observed["health"]["fenced"] is False and observed["source_changed"] is False
        and observed["history_gap"] is False, "healthy original Running history required")
    require(len(observed["events"]) <= 16 and len(observed["capabilities"]) <= 16,
        "runtime display metadata exceeded bounds")
    run = hepta["run"]
    require(isinstance(run["run_id"], str) and re.fullmatch(r"[A-Za-z0-9._:-]{1,128}", run["run_id"]),
        "bounded known run identity required")
    expected_connection = dict(zip(PHASES, ("observed", "stale", "projection_missing"), strict=True))[phase]
    require(run["connection"] == expected_connection, "unexpected known run connection state")
    require(positive_integer(run["last_attempt_unix_ms"]), "known run attempt timestamp required")
    if phase == PHASES[2]:
        require(run["last_observation"] is None and run["error_code"] == "run_projection_missing"
            and run["observation_gap"] is False and "sample_age_at_snapshot_ms" not in run,
            "fresh replacement must preserve missing-projection semantics")
    else:
        require(type(run.get("sample_age_at_snapshot_ms")) is int
            and 0 <= run["sample_age_at_snapshot_ms"] <= 2**64 - 1,
            "original Session monotonic source age required for a retained sample")
        sample = run["last_observation"]
        require(isinstance(sample, dict) and sample["run_id"] == run["run_id"]
            and sample["phase"] == "admitted" and sample["terminal_observed"] is False
            and type(sample["idempotent"]) is bool
            and all(positive_integer(sample[field]) for field in
                ("revision", "authority_epoch", "generation", "sampled_unix_ms", "observation_sequence")),
            "original nonterminal admitted run fields required")
        require(sample["sampled_unix_ms"] <= run["last_attempt_unix_ms"], "run sample cannot follow completed attempt")
        if phase == PHASES[0]:
            require(run["error_code"] is None and run["observation_gap"] is False,
                "first observed run must be live and gap-free")
        else:
            require(run["observation_gap"] is True and run["error_code"] in
                ("protocol_mismatch", "generation_fenced", "owner_rejected"),
                "old endpoint must retain history as stale")
    return hepta, observed, run


def validate_phase(value, sequence, runtime=None, previous=None):
    require(value.get("event") == "objective_session_phase_observed"
        and type(value.get("sequence")) is int and value.get("sequence") == sequence
        and value.get("phase") == PHASES[sequence - 1],
        "unexpected original Objective phase")
    require(positive_integer(value["session_pid"]) and positive_integer(value["worker_tid"]),
        "positive owned Session/worker identity required")
    require(positive_integer(value["recorded_unix_ms"])
        and type(value["ack_timeout_seconds"]) is int and 1 <= value["ack_timeout_seconds"] <= 120,
        "bounded original phase timestamp and acknowledgment deadline required")
    instance = value["session_instance"]
    require(isinstance(instance, str) and re.fullmatch(r"[0-9a-f]{32}", instance),
        "exact Session instance required")
    current_runtime = Path(value["runtime_dir"])
    require(current_runtime.is_absolute() and current_runtime.name == "objective-ui"
        and current_runtime.parent.parent == Path("/tmp")
        and re.fullmatch(r"ho-[A-Za-z0-9_-]+", current_runtime.parent.name),
        "runtime must be the disposable original Objective probe directory")
    require(Path(value["session_socket_path"]) == current_runtime / "trillionnium-ui/session.sock"
        and (runtime is None or current_runtime == runtime), "one exact disposable Session endpoint required")
    require(value["snapshot"]["session_instance"] == instance
        and value["ack"] == {"sequence": sequence, "phase": value["phase"], "session_instance": instance}
        and value["capture_ack_is_coordination_only"] is True, "phase instance/ack contract changed")
    _, observed, run = projection(value["snapshot"], value["phase"])
    owner = value["original"]
    require(owner["active"] is True and owner["healthy"] is True
        and positive_integer(owner["spawn_generation"]) and positive_integer(owner["process_id"])
        and owner["agent_id"] == observed["agent_id"], "original Supervisor owner identity required")
    if sequence != 2:
        require(observed["spawn_generation"] == owner["spawn_generation"]
            and observed["health"]["process_id"] == owner["process_id"]
            and observed["health"]["ready"] is True and observed["health"]["lifecycle"] == "running",
            "live runtime must match the current original owner")
    if sequence == 1:
        require(run_fields(run["last_observation"]) == run_fields(value["evidence"]["original_run"])
            and run["last_observation"]["generation"] == observed["current_generation"],
            "first run does not match the direct original owner read")
    if previous is not None:
        require(current_runtime == Path(previous["runtime_dir"]), "runtime changed between held phases")
        _, old_observed, old_run = projection(previous["snapshot"], previous["phase"])
        require(owner["agent_id"] == previous["original"]["agent_id"] and run["run_id"] == old_run["run_id"],
            "known agent/run identity changed between phases")
        if sequence == 2:
            require(all(value[field] == previous[field] for field in ("session_pid", "session_instance", "worker_tid"))
                and owner["process_id"] != previous["original"]["process_id"]
                and owner["spawn_generation"] > previous["original"]["spawn_generation"]
                and observed["health"]["process_id"] == old_observed["health"]["process_id"]
                and observed["spawn_generation"] == old_observed["spawn_generation"]
                and run_fields(run["last_observation"]) == run_fields(old_run["last_observation"])
                and value["evidence"]["retained_run_unchanged_across_failed_samples"] is True,
                "owner restart must preserve this Session and its historical run identity")
        else:
            require(value["session_instance"] != previous["session_instance"]
                and value["session_pid"] != previous["session_pid"] and owner == previous["original"]
                and value["evidence"]["missing_projection_is_not_non_admission"] is True
                and value["evidence"]["historical_admission_still_requires_original_journal"] is True,
                "only explicit Session replacement may reveal a missing current projection")
    return current_runtime


def compare_snapshot(actual, phase, sampled_at_ms, prior_projection=None, transport_elapsed_ms=0):
    require(actual["session_instance"] == phase["session_instance"],
        "live Session instance differs from held original Objective phase")
    hepta, observed, run = projection(actual, phase["phase"])
    expected_hepta, expected_observed, expected_run = projection(phase["snapshot"], phase["phase"])
    require(run["run_id"] == expected_run["run_id"], "known run changed across capture")
    if phase["phase"] == PHASES[1]:
        require(observed == expected_observed and run["last_observation"] == expected_run["last_observation"]
            and run["last_attempt_unix_ms"] == expected_run["last_attempt_unix_ms"]
            and run["error_code"] == expected_run["error_code"]
            and run["sample_age_at_snapshot_ms"] >= expected_run["sample_age_at_snapshot_ms"],
            "stale evidence changed or became newly sampled")
        if prior_projection is not None:
            require(hepta["last_observation"] == prior_projection["last_observation"]
                and run_history(run) == run_history(prior_projection["run"])
                and run["sample_age_at_snapshot_ms"] >= prior_projection["run"]["sample_age_at_snapshot_ms"],
                "stale history changed or source age regressed between actual before/after reads")
    else:
        legacy.live_progress(observed, expected_observed, "running")
        require(0 <= sampled_at_ms - observed["sampled_unix_ms"] <= 7000,
            "actual runtime observation is not independently fresh")
        if prior_projection is not None:
            legacy.live_progress(observed, prior_projection["last_observation"], "running")
        if phase["phase"] == PHASES[0]:
            require(type(transport_elapsed_ms) is int and transport_elapsed_ms >= 0
                and run["sample_age_at_snapshot_ms"] + transport_elapsed_ms <= 7000,
                "original run monotonic source age and transport bound are not fresh")
            sample, expected = run["last_observation"], expected_run["last_observation"]
            require(run_fields(sample) == run_fields(expected)
                and sample["sampled_unix_ms"] >= expected["sampled_unix_ms"]
                and sample["observation_sequence"] >= expected["observation_sequence"]
                and 0 <= sampled_at_ms - sample["sampled_unix_ms"] <= 7000,
                "actual original run fields or independent run freshness changed")
            if prior_projection is not None:
                prior = prior_projection["run"]["last_observation"]
                require(run_fields(sample) == run_fields(prior)
                    and sample["sampled_unix_ms"] >= prior["sampled_unix_ms"]
                    and sample["observation_sequence"] >= prior["observation_sequence"],
                    "run observation regressed across the pixel capture")
        require(0 <= sampled_at_ms - run["last_attempt_unix_ms"] <= 7000,
            "run result completion does not belong to a current sample")
    require(hepta["last_attempt_unix_ms"] >= expected_hepta["last_attempt_unix_ms"]
        and 0 <= sampled_at_ms - hepta["last_attempt_unix_ms"] <= 7000,
        "Session runtime attempt did not progress within the held phase")


def actual_snapshot(phase, output, label, prior_projection=None):
    address = Path(phase["session_socket_path"])
    metadata = address.lstat()
    require(stat.S_ISSOCK(metadata.st_mode) and metadata.st_uid == os.geteuid()
        and stat.S_IMODE(metadata.st_mode) == 0o600, "private actual Session socket required")
    started = now_ms()
    started_mono = time.monotonic_ns()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
        stream.settimeout(1.0)
        stream.connect(str(address))
        pid, uid, gid = struct.unpack("3i", stream.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        require(pid == phase["session_pid"] and uid == os.geteuid(),
            "kernel peer identity differs from original probe Session")
        worker = Path("/proc") / str(pid) / "task" / str(phase["worker_tid"])
        require((worker / "comm").read_text().strip() == "hepta-read-only"
            and re.search(r"^Tgid:\s+" + str(pid) + r"$", (worker / "status").read_text(), re.MULTILINE),
            "original probe Session worker is not present in this actual peer process")
        stream.sendall(b'{"type":"snapshot"}\n')
        with stream.makefile("rb") as reader:
            raw = reader.readline(MAX_FRAME + 1)
    ended = now_ms()
    elapsed_ms = (time.monotonic_ns() - started_mono + 999_999) // 1_000_000
    require(raw.endswith(b"\n") and len(raw) <= MAX_FRAME, "invalid bounded Session frame")
    destination = output / (label + ".snapshot.json")
    destination.write_bytes(raw)
    actual = json.loads(raw)
    compare_snapshot(actual, phase, ended, prior_projection, elapsed_ms)
    return {"file": destination.name, "bytes": len(raw), "sha256": digest(destination),
        "started_unix_ms": started, "finished_unix_ms": ended,
        "transport_elapsed_ms_rounded_up": elapsed_ms,
        "peer_pid": pid, "peer_uid": uid, "peer_gid": gid,
        "session_instance": actual["session_instance"], "hepta": actual["hepta"]}


def inside(args):
    output = Path(args.output)
    config = json.loads((output / "capture-config.json").read_text())
    phase_directory = Path(config["phase_dir"])
    runtime = Path(config["runtime_dir"])
    guard = load_module("shell_live_child_guard",
        Path("/test-source/tests/integration/hepta/run_original_agentd.py"))
    capture = load_module("shell_live_x11_capture", Path("/x11-capture.py"))
    require(guard.child_anchor_available(), "waitable child identity required")
    for name in ("cache", "config", "state", "data"):
        (output / name).mkdir(mode=0o700)
    env = dict(os.environ, DISPLAY=":92", XAUTHORITY=str(output / "Xauthority"),
        XDG_RUNTIME_DIR=str(runtime), WINIT_UNIX_BACKEND="x11", XMODIFIERS="@im=none",
        LIBGL_ALWAYS_SOFTWARE="1", LP_NUM_THREADS="2", MESA_SHADER_CACHE_DISABLE="true",
        XDG_CACHE_HOME=str(output / "cache"), XDG_CONFIG_HOME=str(output / "config"),
        XDG_STATE_HOME=str(output / "state"), XDG_DATA_HOME=str(output / "data"))
    require(not any(key.startswith("TRILL_HEPTA_") for key in env),
        "Shell must not receive Agentd endpoint configuration")
    os.environ.update(env)
    report = {"evidence_class": "original_objective_continuous_session_native_shell_capture",
        "started_unix_ms": now_ms(), "capture_passed": False,
        "original_hepta_pin": PIN, "source_provenance": config["provenance"],
        "visual_review_required": True, "visual_review_completed_by_capture": False,
        "layout_marker_scope": "first_runtime_layout_only_known_run_pixels_require_visual_review",
        "capture_api": "XGetImage_actual_private_root_framebuffer",
        "original_agentd_managed_by": "original_objective_probe",
        "session_managed_by": "original_objective_probe",
        "shell_processes_started": 0, "synthetic_agentd_fixture_used": False,
        "renderer_memory_injected": False, "objective_submitted_by_capture": False,
        "model_called": False, "device_effect_tested": False,
        "physical_display_tested": False, "keyboard_input_tested": False,
        "language_scope": "English_Runtime_card", "cjk_ime_tested": False,
        "font_source": "unchanged_eframe_embedded_fonts",
        "shared_pid_namespace": True, "isolated_network_mounts_ipc_uts": True,
        "child_leader_parent_death_signal": "SIGKILL",
        "arbitrary_descendant_parent_death_qualification": False,
        "phases": [], "commands": [], "children": []}
    groups, logs = [], []
    display = None

    def command(label, argv, environment=env, required=True):
        try:
            result = subprocess.run(argv, env=environment, stdin=subprocess.DEVNULL,
                capture_output=True, timeout=8)
        except subprocess.TimeoutExpired as error:
            (output / (label + ".stdout.log")).write_bytes(error.stdout or b"")
            (output / (label + ".stderr.log")).write_bytes(error.stderr or b"")
            report["commands"].append({"label": label, "argv": argv,
                "returncode": None, "timeout_seconds": 8})
            raise
        (output / (label + ".stdout.log")).write_bytes(result.stdout)
        (output / (label + ".stderr.log")).write_bytes(result.stderr)
        report["commands"].append({"label": label, "argv": argv, "returncode": result.returncode})
        require(not required or result.returncode == 0, "display command failed: " + label)
        return result

    def spawn(label, argv):
        stdout = (output / (label + ".stdout.log")).open("xb")
        stderr = (output / (label + ".stderr.log")).open("xb")
        logs.extend((stdout, stderr))
        wrapper = [sys.executable, "-B", str(Path(__file__).resolve()),
            "--parent-pid", str(os.getpid()), "--exec-child", *argv]
        child = subprocess.Popen(wrapper, env=env, stdin=subprocess.DEVNULL,
            stdout=stdout, stderr=stderr, start_new_session=True)
        group = guard.ChildGroup(child)
        groups.append((label, group))
        report["children"].append({"label": label, "pid": child.pid, "argv": argv,
            "exec_wrapper_argv": wrapper, "parent_pid": os.getpid(),
            "parent_death_signal": "SIGKILL"})
        return group

    def alive(group):
        return group.observe_exit() is None

    def save():
        (output / "capture-receipt.json").write_text(json.dumps(report, indent=2) + "\n")

    try:
        auth = output / "Xauthority"
        auth.touch(mode=0o600)
        result = subprocess.run(["xauth", "-f", str(auth), "add", ":92", ".", secrets.token_hex(16)],
            env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=5)
        (output / "xauth.stdout.log").write_bytes(result.stdout)
        (output / "xauth.stderr.log").write_bytes(result.stderr)
        require(result.returncode == 0, "private Xauthority creation failed")
        server = spawn("xvfb", ["Xvfb", ":92", "-nolisten", "tcp", "-screen", "0",
            "1440x1000x24", "-auth", str(auth)])
        for attempt in range(100):
            require(alive(server), "private Xvfb exited")
            result = command(f"display-ready-{attempt:03}", ["xdpyinfo"], required=False)
            if result.returncode == 0:
                break
            require(attempt < 99, "private display readiness timeout")
            time.sleep(0.05)
        denied = command("display-no-cookie", ["xdpyinfo"],
            dict(env, XAUTHORITY=str(output / "absent-cookie")), required=False)
        require(denied.returncode != 0, "private display accepted an unauthenticated client")
        report["private_display_rejects_no_cookie"] = True
        shell = spawn("rust-shell", ["/ui-bin/trill-shell", "--page", "hepta", "--hepta-layout-probe"])
        report["shell_processes_started"] = 1
        report["shell_pid"] = shell.process.pid
        for attempt in range(160):
            require(alive(server) and alive(shell), "owned display/Shell exited before layout")
            raw = (output / "rust-shell.stdout.log").read_bytes()
            markers = [json.loads(line[len(LAYOUT_PREFIX):]) for line in raw.splitlines()
                if line.startswith(LAYOUT_PREFIX)]
            require(len(markers) <= 1, "unexpected repeated one-shot layout marker")
            if markers:
                report["first_runtime_layout"] = markers[0]
                break
            require(attempt < 159, "native first runtime layout timed out")
            time.sleep(0.05)
        for attempt in range(100):
            result = command(f"shell-window-{attempt:03}", ["xdotool", "search", "--all",
                "--onlyvisible", "--pid", str(shell.process.pid), "--class", "^trill-shell$"], required=False)
            ids = result.stdout.decode().split()
            if result.returncode == 0 and len(ids) == 1 and ids[0].isdigit():
                break
            require(attempt < 99, "exactly one actual mapped Shell window required")
            time.sleep(0.05)
        xid = ids[0]

        def check_window(label):
            properties = command(label + "-properties", ["xprop", "-id", xid, "WM_CLASS", "_NET_WM_PID"])
            lines = properties.stdout.decode("utf-8", errors="strict").splitlines()
            require('WM_CLASS(STRING) = "trill-shell", "trill-shell"' in lines
                and f"_NET_WM_PID(CARDINAL) = {shell.process.pid}" in lines,
                "actual window identity mismatch")
            visible = command(label + "-visible", ["xdotool", "search", "--all", "--onlyvisible",
                "--pid", str(shell.process.pid), "--class", "^trill-shell$"])
            require(visible.stdout.decode().split() == [xid], "continuous Shell replaced its actual mapped window")

        check_window("shell-window")
        report["shell_window"] = {"xid": xid, "pid": shell.process.pid, "class": "trill-shell"}
        command("shell-owned-window-size", ["xdotool", "windowsize", xid, "1400", "960"])
        command("shell-owned-window-position", ["xdotool", "windowmove", xid, "20", "20"])
        command("shell-window-tree", ["xwininfo", "-root", "-tree"])
        display = capture.Display()
        previous = None
        for sequence, phase_name in enumerate(PHASES, 1):
            phase_path = phase_directory / ("phase-" + str(sequence) + ".json")
            deadline = time.monotonic() + 150
            while not phase_path.exists():
                require(alive(server) and alive(shell), "continuous Shell exited while waiting for phase")
                require(time.monotonic() < deadline, "original phase timed out: " + phase_name)
                time.sleep(0.05)
            phase, raw = read_phase(phase_path)
            validate_phase(phase, sequence, runtime, previous)
            require(0 <= now_ms() - phase["recorded_unix_ms"] < phase["ack_timeout_seconds"] * 1000,
                "original phase acknowledgment window expired before capture")
            label = f"phase-{sequence}-{phase_name}"
            (output / (label + ".json")).write_bytes(raw)
            item = {"sequence": sequence, "phase": phase_name, "started_unix_ms": now_ms(),
                "phase_file": label + ".json", "phase_sha256": hashlib.sha256(raw).hexdigest(),
                "session_pid": phase["session_pid"], "session_instance": phase["session_instance"],
                "shell_pid": shell.process.pid, "shell_window_xid": xid}
            report["phases"].append(item)
            check_window(label + "-before")
            item["before"] = actual_snapshot(phase, output, label + "-before")
            if sequence == 1:
                marker = report["first_runtime_layout"]
                expected = phase["snapshot"]["hepta"]["last_observation"]
                require(marker["page"] == "hepta" and marker["connection"] == "observed",
                    "first marker was not the actual Hepta page")
                for key in ("agent_id", "spawn_generation", "current_generation"):
                    require(marker[key] == expected[key], "first layout marker identity mismatch")
                require(marker["process_id"] == expected["health"]["process_id"],
                    "first layout marker PID mismatch")
                require(abs(marker["sampled_unix_ms"] - expected["sampled_unix_ms"]) <= 7000,
                    "first layout marker was not contemporaneous with held phase")
            # Shell's existing snapshot poll is 800 ms, repaint is 100 ms.
            # This dwell allows updates; only subsequent visual review proves the pixels
            # actually show this phase. There is no synthetic renderer signal.
            dwell = time.monotonic() + 2.5
            while time.monotonic() < dwell:
                require(alive(server) and alive(shell), "continuous Shell exited during phase")
                time.sleep(0.05)
            item["capture_started_unix_ms"] = now_ms()
            item["screenshot"] = display.screenshot(output / (label + ".png"))
            item["capture_finished_unix_ms"] = now_ms()
            item["after"] = actual_snapshot(phase, output, label + "-after", item["before"]["hepta"])
            check_window(label + "-after")
            require(alive(server) and alive(shell), "Shell exited before phase acknowledgment")
            item["capture_complete"] = True
            item["visual_review_required"] = True
            item["finished_unix_ms"] = now_ms()
            save()
            acknowledge(phase_directory, sequence, phase["ack"])
            item["acknowledged_unix_ms"] = now_ms()
            previous = phase
        require(digest(Path("/ui-bin/trill-shell")) == config["provenance"]["binaries"]["trill-shell"]["sha256"],
            "mounted Shell ELF changed during capture")
        verify_dependency_files(json.loads((output / "host-dependencies.json").read_text()))
        report["same_shell_pid_all_phases"] = True
        report["same_shell_window_all_phases"] = True
        report["capture_passed"] = True
    except BaseException as error:
        report["capture_passed"] = False
        report["error"] = str(error)
        raise
    finally:
        if display is not None:
            display.close()
        cleanup_errors = []
        for label, group in reversed(groups):
            try:
                report.setdefault("cleanup", []).append({"label": label, "pid": group.process.pid,
                    "observed_returncode": guard.terminate_group(group)})
            except BaseException as error:
                cleanup_errors.append(label + ": " + str(error))
        for log in logs:
            log.close()
        if cleanup_errors:
            report["capture_passed"] = False
            report["cleanup_errors"] = cleanup_errors
        report["finished_unix_ms"] = now_ms()
        save()
        print(json.dumps({key: report[key] for key in ("capture_passed", "visual_review_required",
            "shell_processes_started", "finished_unix_ms")}), flush=True)
        require(not cleanup_errors, "owned display/Shell cleanup failed")


def outer(args):
    require(all(value is not None for value in (args.source_root, args.host_usr, args.shell_bin,
        args.build_receipt, args.phase_dir, args.output)),
        "explicit source/host-usr/Shell/build/phase/output inputs required")
    source = args.source_root.resolve(strict=True)
    host_usr = args.host_usr.resolve(strict=True)
    shell = args.shell_bin.resolve(strict=True)
    build = json.loads(args.build_receipt.read_text())
    commands = build["build_commands"]
    require(isinstance(commands, list) and commands
        and all(type(command["exit_code"]) is int and command["exit_code"] == 0 for command in commands)
        and any("build" in command["command"] for command in commands), "actual passing UI build commands required")

    def git(*arguments):
        return subprocess.check_output(["git", "-C", str(source), *arguments],
            stderr=subprocess.PIPE, timeout=15).decode().strip()

    head = git("rev-parse", "HEAD")
    require(not git("status", "--porcelain=v1", "--untracked-files=all"),
        "commit capture code and keep the source checkout clean")
    require(git("rev-parse", build["source_commit"] + "^{tree}") == build["source_tree"],
        "recorded UI source tree mismatch")
    require(git("rev-parse", build["source_commit"] + ":ui") == build["ui_tree"]
        and git("rev-parse", head + ":ui") == build["ui_tree"]
        and digest(source / "ui/Cargo.lock") == build["ui_lock_sha256"],
        "actual Shell UI source or lock differs from its build receipt")
    recorded = build["binaries"]["trill-shell"]
    require(shell.is_file() and os.access(shell, os.X_OK)
        and shell.stat().st_size == recorded["bytes"] and digest(shell) == recorded["sha256"],
        "explicit Shell ELF differs from source build receipt")
    with shell.open("rb") as stream:
        require(stream.read(4) == b"\x7fELF", "native Shell ELF required")
    dependencies = host_dependencies(host_usr, shell)
    provenance = {"harness_commit": head, "harness_tree": git("rev-parse", head + "^{tree}"),
        "production_ui_commit": build["source_commit"], "production_source_tree": build["source_tree"],
        "unchanged_ui_subtree": build["ui_tree"], "ui_lock_sha256": build["ui_lock_sha256"],
        "tracked_sources": {}, "binaries": {"trill-shell": {"path": str(shell),
            "bytes": recorded["bytes"], "sha256": recorded["sha256"]}},
        "build_receipt_sha256": digest(args.build_receipt),
        "font_source": "unchanged_eframe_embedded_fonts_no_external_font_override",
        "original_and_session_elf_binding": "separate_original_objective_probe_report"}
    output = args.output.absolute()
    require(not output.exists() and not output.is_symlink() and output.parent.is_dir()
        and not output.is_relative_to(source), "new output outside the source checkout required")
    output.mkdir(mode=0o700)
    inputs = (
        ("harness", "tests/ui/probe-original-objective-shell.py", "capture-source.py"),
        ("reviewed_helpers", "tests/ui/probe-original-hepta-shell.py", "reviewed-capture-helpers.py"),
        ("pixels", "tests/ui/x11-ime-client.py", "x11-capture-source.py"),
        ("guard", "tests/integration/hepta/run_original_agentd.py", "child-guard-source.py"),
    )
    for role, relative, filename in inputs:
        actual = source / relative
        if role == "harness":
            require(Path(__file__).resolve(strict=True) == actual.resolve(strict=True),
                "capture executable is outside its frozen tracked source")
        raw = actual.read_bytes()
        committed = subprocess.check_output(["git", "-C", str(source), "show", head + ":" + relative],
            stderr=subprocess.PIPE, timeout=15)
        require(raw == committed, "capture dependency differs from frozen source: " + role)
        (output / filename).write_bytes(raw)
        provenance["tracked_sources"][role] = {"path": relative, "git_blob": git("rev-parse", head + ":" + relative),
            "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    (output / "rust-build-receipt.json").write_bytes(args.build_receipt.read_bytes())
    (output / "host-dependencies.json").write_text(json.dumps(dependencies, indent=2) + "\n")
    provenance["host_dependencies_sha256"] = digest(output / "host-dependencies.json")
    phase_directory = args.phase_dir.absolute()
    first_path = phase_directory / "phase-1.json"
    deadline = time.monotonic() + args.startup_timeout
    while not first_path.exists():
        require(time.monotonic() < deadline, "first original Objective Session phase timed out")
        time.sleep(0.05)
    private_directory(phase_directory)
    first, _ = read_phase(first_path)
    runtime = validate_phase(first, 1)
    private_directory(runtime)
    private_directory(runtime.parent)
    config = {"phase_dir": str(phase_directory), "runtime_dir": str(runtime), "provenance": provenance}
    (output / "capture-config.json").write_text(json.dumps(config, indent=2) + "\n")
    command = ["/usr/bin/bwrap", "--unshare-user", "--unshare-ipc", "--unshare-net", "--unshare-uts",
        "--die-with-parent", "--new-session", "--hostname", "a10-original-objective-shell",
        "--ro-bind", str(host_usr), "/usr", "--symlink", "usr/bin", "/bin",
        "--symlink", "usr/sbin", "/sbin", "--symlink", "usr/lib", "/lib", "--symlink", "usr/lib64", "/lib64",
        "--ro-bind", "/etc", "/etc", "--ro-bind", "/proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--dir", "/root", "--dir", "/run", "--bind", str(output), str(output),
        "--bind", str(phase_directory), str(phase_directory), "--ro-bind", str(runtime), str(runtime),
        "--ro-bind", str(shell), "/ui-bin/trill-shell",
        "--ro-bind", str(output / "capture-source.py"), "/test-source/tests/ui/probe-original-objective-shell.py",
        "--ro-bind", str(output / "reviewed-capture-helpers.py"), "/test-source/tests/ui/probe-original-hepta-shell.py",
        "--ro-bind", str(output / "x11-capture-source.py"), "/x11-capture.py",
        "--ro-bind", str(output / "child-guard-source.py"), "/test-source/tests/integration/hepta/run_original_agentd.py",
        "--clearenv", "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "LANG", "C.UTF-8",
        "--setenv", "LC_ALL", "C.UTF-8", "--setenv", "PYTHONDONTWRITEBYTECODE", "1", "--setenv", "TZ", "UTC",
        "--chdir", str(output), "/usr/bin/python3", "-B", "/test-source/tests/ui/probe-original-objective-shell.py",
        "--inside", "--output", str(output)]
    namespace = {"argv": command, "started_unix_ms": now_ms(), "returncode": None,
        "shared_pid_namespace": True, "system_install_performed": False,
        "isolation_requested": "private_user_mount_network_ipc_uts_shared_pid",
        "isolation_succeeded": False, "host_dependencies_sha256": provenance["host_dependencies_sha256"]}
    guard = load_module("objective_shell_outer_guard", output / "child-guard-source.py")
    require(guard.child_anchor_available(), "waitable namespace child identity required")
    with (output / "namespace.stdout.log").open("xb") as stdout, (output / "namespace.stderr.log").open("xb") as stderr:
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, start_new_session=True)
        group = guard.ChildGroup(child)
        try:
            deadline = time.monotonic() + 480
            while group.observe_exit() is None:
                require(time.monotonic() < deadline, "bounded Objective capture namespace timeout")
                time.sleep(0.1)
            namespace["returncode"] = group.reap()
            namespace["isolation_succeeded"] = namespace["returncode"] == 0
        except BaseException as error:
            namespace["error"] = str(error)
            namespace["returncode"] = guard.terminate_group(group)
            raise
        finally:
            namespace["finished_unix_ms"] = now_ms()
            (output / "namespace.json").write_text(json.dumps(namespace, indent=2) + "\n")
    print(json.dumps(namespace, indent=2))
    require(namespace["returncode"] == 0, "actual Objective Shell capture namespace failed")
    require(digest(shell) == recorded["sha256"], "explicit Shell ELF changed during capture")
    verify_dependency_files(dependencies)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inside", action="store_true")
    parser.add_argument("--parent-pid", type=int)
    parser.add_argument("--exec-child", nargs=argparse.REMAINDER)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--host-usr", type=Path, help="explicit current host dependency root; must resolve to /usr")
    parser.add_argument("--shell-bin", type=Path)
    parser.add_argument("--build-receipt", type=Path)
    parser.add_argument("--phase-dir", type=Path)
    parser.add_argument("--startup-timeout", type=int, default=120)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()
    require(1 <= arguments.startup_timeout <= 1200, "bounded startup timeout required")
    if arguments.exec_child is not None:
        bound_exec(arguments.parent_pid, arguments.exec_child)
    else:
        require(arguments.output is not None, "output directory required")
        inside(arguments) if arguments.inside else outer(arguments)
