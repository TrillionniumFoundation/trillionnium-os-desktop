#!/usr/bin/env python3
"""Capture one native Shell across original Agentd / persistent Session phases.

The A07 original probe owns Agentd, its Session processes, and the six phase
barriers. This consumer starts only a private Xvfb and one unchanged Shell.
Each image is a real X framebuffer capture with same-process Session snapshots
before and after. The old one-shot Shell marker qualifies only the first
runtime layout. All six images require independent visual review; an ack is
coordination, never renderer or original-runtime evidence by itself.
"""

import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import signal
import socket
import stat
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
PHASES = (
    "starting", "running", "draining", "old_spawn_stale",
    "recovered_running", "stopped_stale",
)
MAX_FRAME = 65_536
LAYOUT_PREFIX = b"TRILL_HEPTA_LAYOUT_V1 "
PIN = "f8c9419df6ddeb36ff8b522a50219981fb8d9345"
FONT_SHA256 = "27251f8f257e831f4b876408a7d0ef88ae2c18fe0cbb6780bd18fe6bad8ddb10"


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def now_ms():
    return time.time_ns() // 1_000_000


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def private_directory(path):
    value = path.lstat()
    require(path.is_absolute() and stat.S_ISDIR(value.st_mode)
        and value.st_uid == os.geteuid()
        and stat.S_IMODE(value.st_mode) == 0o700,
        "owned absolute private directory required: " + str(path))


def read_phase(path):
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
        value = os.fstat(stream.fileno())
        require(stat.S_ISREG(value.st_mode) and value.st_uid == os.geteuid()
            and stat.S_IMODE(value.st_mode) == 0o600
            and 0 < value.st_size <= MAX_FRAME,
            "phase must be an owned bounded 0600 regular file")
        raw = stream.read(MAX_FRAME + 1)
    require(len(raw) <= MAX_FRAME, "phase grew beyond its bound")
    return json.loads(raw), raw


def positive_integer(value):
    return type(value) is int and value > 0


def phase_projection(value, phase):
    require(value.get("type") == "snapshot", "actual Session snapshot required")
    require(value.get("tasks") == [], "capture must not launch or inherit host applications")
    projection = value["hepta"]
    stale = phase in ("old_spawn_stale", "stopped_stale")
    require(projection["connection"] == ("stale" if stale else "observed"),
        "wrong connection state for phase " + phase)
    observed = projection["last_observation"]
    require(isinstance(observed, dict), "last successful observation missing")
    require(re.fullmatch(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        observed["agent_id"]), "original AgentId must be an exact UUID")
    for key in ("spawn_generation", "current_generation", "sampled_unix_ms"):
        require(positive_integer(observed[key]), "invalid runtime identity/time: " + key)
    health = observed["health"]
    require(positive_integer(health["process_id"]), "invalid original Agentd PID")
    lifecycles = {
        "starting": ("starting",), "running": ("running",), "draining": ("draining",),
        "old_spawn_stale": ("draining",), "recovered_running": ("running",),
        # The original stop_slot first prepares Running -> Draining. A live
        # Session may observe this real final transition before disconnection.
        "stopped_stale": ("running", "draining"),
    }[phase]
    lifecycle = health["lifecycle"]
    require(lifecycle in lifecycles, "wrong retained/observed lifecycle")
    require(all(type(health[key]) is bool for key in ("ready", "promotion_ready", "fenced")),
        "runtime health flags must be exact booleans")
    require(health["ready"] == (lifecycle == "running"),
        "runtime readiness does not match lifecycle")
    if lifecycle in ("running", "draining"):
        require(health["promotion_ready"] == (lifecycle == "running"),
            "runtime promotion readiness does not match lifecycle")
    offset = {"starting": 0, "running": 1, "draining": 2}[lifecycle]
    require(observed["current_generation"] == observed["spawn_generation"] + offset,
        "wrong original lifecycle generation")
    require(len(observed["events"]) <= 16 and len(observed["capabilities"]) <= 16,
        "Session projection exceeded its bounded display window")
    require(observed["source_changed"] is False and observed["history_gap"] is False,
        "bounded phase cannot qualify a changed source or incomplete event history")
    require(projection.get("error_code") if stale else projection.get("error_code") is None,
        "wrong diagnostic state")
    return projection, observed


def validate_phase(value, sequence, runtime=None, previous=None):
    require(value.get("event") == "session_phase_observed"
        and value.get("sequence") == sequence
        and value.get("phase") == PHASES[sequence - 1], "unexpected original-probe phase")
    require(positive_integer(value["session_pid"]), "positive actual Session PID required")
    instance = value["session_instance"]
    require(isinstance(instance, str) and 0 < len(instance) <= 128,
        "bounded Session instance required")
    current_runtime = Path(value["runtime_dir"])
    require(current_runtime.is_absolute(), "absolute trusted runtime path required")
    require(Path(value["session_socket_path"])
        == current_runtime / "trillionnium-ui/session.sock", "unexpected Session socket path")
    require(runtime is None or runtime == current_runtime, "runtime path changed under the Shell")
    require(value["snapshot"]["session_instance"] == instance,
        "phase snapshot belongs to a different Session instance")
    phase_projection(value["snapshot"], value["phase"])
    require(value["ack"] == {"sequence": sequence, "phase": value["phase"],
        "session_instance": instance}, "unexpected ack contract")
    if previous is not None:
        replacement = sequence == 5
        require((previous["session_instance"] != instance) == replacement,
            "Session instance continuity/replacement mismatch")
        require((previous["session_pid"] != value["session_pid"]) == replacement,
            "Session process continuity/replacement mismatch")
        _, old = phase_projection(previous["snapshot"], previous["phase"])
        _, current = phase_projection(value["snapshot"], value["phase"])
        require(current["agent_id"] == old["agent_id"], "original AgentId changed")
        require((current["health"]["process_id"] != old["health"]["process_id"]) == replacement,
            "original process continuity/replacement mismatch")
        if replacement:
            require(current["spawn_generation"] > old["spawn_generation"],
                "replacement did not advance original spawn")
        else:
            require(current["spawn_generation"] == old["spawn_generation"],
                "original spawn changed without explicit Session replacement")
    return current_runtime


def live_progress(observed, previous, phase):
    for key in ("agent_id", "spawn_generation", "current_generation", "capabilities",
            "capabilities_truncated", "events_omitted_from_view", "source_changed", "history_gap"):
        require(observed[key] == previous[key], "live runtime metadata changed: " + key)
    for key in ("process_id", "lifecycle", "ready", "fenced"):
        require(observed["health"][key] == previous["health"][key],
            "live runtime health changed: " + key)
    old_promotion = previous["health"]["promotion_ready"]
    promotion = observed["health"]["promotion_ready"]
    require(promotion == old_promotion
        or (phase == "starting" and old_promotion is False and promotion is True),
        "live runtime promotion readiness regressed or changed outside Starting")
    # Health and Events are separate original RPCs. Do not require readiness
    # and app_server_ready to appear in the same observation. Within this
    # bounded phase, the retained event prefix and cursor progress stay exact.
    require(observed["sampled_unix_ms"] >= previous["sampled_unix_ms"],
        "live Session observation went backwards")
    for key in ("next_cursor", "latest_cursor"):
        require(type(observed[key]) is int and observed[key] >= previous[key],
            "live event cursor regressed: " + key)
    require(observed["next_cursor"] <= observed["latest_cursor"], "event cursor exceeds latest")
    events, prior_events = observed["events"], previous["events"]
    require(events[:len(prior_events)] == prior_events, "live event history replaced its held prefix")
    cursors = [event["cursor"] for event in events]
    require(all(positive_integer(cursor) for cursor in cursors)
        and all(left < right for left, right in zip(cursors, cursors[1:])),
        "event metadata cursor order is invalid")
    require(observed["next_cursor"] == (cursors[-1] if cursors else 0),
        "next cursor does not match the complete bounded event window")
    require(all(event["cursor"] > previous["next_cursor"] for event in events[len(prior_events):]),
        "new event metadata reused a consumed cursor")


def compare_snapshot(actual, phase, sampled_at_ms, prior_projection=None):
    require(actual["session_instance"] == phase["session_instance"],
        "live Session instance differs from held phase")
    projection, observed = phase_projection(actual, phase["phase"])
    _, expected = phase_projection(phase["snapshot"], phase["phase"])
    require(observed["sampled_unix_ms"] <= sampled_at_ms, "future observation timestamp")
    if projection["connection"] == "observed":
        live_progress(observed, expected, phase["phase"])
        if prior_projection is not None:
            require(prior_projection["connection"] == "observed", "prior capture snapshot was not live")
            live_progress(observed, prior_projection["last_observation"], phase["phase"])
        require(sampled_at_ms - observed["sampled_unix_ms"] <= 7000,
            "live observed projection expired")
    else:
        require(observed == expected, "stale Session replaced its retained successful observation")
        if prior_projection is not None:
            require(observed == prior_projection["last_observation"],
                "stale Session changed its observation across capture")


def actual_snapshot(phase, output, label, prior_projection=None):
    address = Path(phase["session_socket_path"])
    metadata = address.lstat()
    require(stat.S_ISSOCK(metadata.st_mode) and metadata.st_uid == os.geteuid()
        and stat.S_IMODE(metadata.st_mode) == 0o600, "private actual Session socket required")
    started = now_ms()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
        stream.settimeout(1.0)
        stream.connect(str(address))
        pid, uid, gid = struct.unpack("3i", stream.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        require(pid == phase["session_pid"] and uid == os.geteuid(),
            "kernel peer identity does not match held Session process")
        stream.sendall(b'{"type":"snapshot"}\n')
        with stream.makefile("rb") as reader:
            raw = reader.readline(MAX_FRAME + 1)
    ended = now_ms()
    require(raw.endswith(b"\n") and len(raw) <= MAX_FRAME, "invalid Session frame")
    destination = output / (label + ".snapshot.json")
    destination.write_bytes(raw)
    actual = json.loads(raw)
    compare_snapshot(actual, phase, ended, prior_projection)
    return {"file": destination.name, "bytes": len(raw), "sha256": digest(destination),
        "started_unix_ms": started, "finished_unix_ms": ended,
        "peer_pid": pid, "peer_uid": uid, "peer_gid": gid,
        "session_instance": actual["session_instance"], "hepta": actual["hepta"]}


def acknowledge(directory, sequence, value):
    target = directory / ("ack-" + str(sequence) + ".json")
    temporary = directory / (".capture-ack-" + secrets.token_hex(8))
    with os.fdopen(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as stream:
        stream.write((json.dumps(value, separators=(",", ":")) + "\n").encode())
        stream.flush()
        os.fsync(stream.fileno())
    try:
        # Atomic no-replace rename leaves nlink=1 throughout publication, as
        # the producer requires. A link+unlink pair has a two-link race.
        libc = ctypes.CDLL(None, use_errno=True)
        rename = libc.renameat2
        rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int,
            ctypes.c_char_p, ctypes.c_uint]
        rename.restype = ctypes.c_int
        if rename(-100, os.fsencode(temporary), -100, os.fsencode(target), 1) != 0:
            error = ctypes.get_errno()
            raise OSError(error, os.strerror(error), str(target))
    finally:
        if temporary.exists():
            temporary.unlink()


def bound_exec(parent_pid, argv):
    """Fresh single-threaded wrapper; no preexec_fn in the capture parent."""
    require(positive_integer(parent_pid) and argv, "explicit parent and child argv required")
    libc = ctypes.CDLL(None, use_errno=True)
    prctl = libc.prctl
    prctl.argtypes = [ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_ulong]
    prctl.restype = ctypes.c_int
    require(prctl(1, signal.SIGKILL, 0, 0, 0) == 0, "PR_SET_PDEATHSIG failed")
    require(os.getppid() == parent_pid, "capture parent exited before death signal was armed")
    # The expected parent cannot disappear between this check and exec without
    # the kernel delivering SIGKILL. Normal exec preserves the setting/PID.
    os.execvpe(argv[0], argv, os.environ)


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
        TRILL_UI_CJK_FONT="/test-fonts/CJK.ttf", TRILL_UI_CJK_FONT_INDEX="0",
        XDG_CACHE_HOME=str(output / "cache"), XDG_CONFIG_HOME=str(output / "config"),
        XDG_STATE_HOME=str(output / "state"), XDG_DATA_HOME=str(output / "data"))
    require(not any(key.startswith("TRILL_HEPTA_") for key in env),
        "Shell must not receive Agentd endpoint configuration")
    os.environ.update(env)
    report = {"evidence_class": "original_agentd_continuous_session_native_shell_capture",
        "started_unix_ms": now_ms(), "capture_passed": False,
        "original_hepta_pin": PIN, "source_provenance": config["provenance"],
        "visual_review_required": True, "visual_review_completed_by_capture": False,
        "layout_marker_scope": "first_observed_runtime_layout_only",
        "capture_api": "XGetImage_actual_private_root_framebuffer",
        "original_agentd_managed_by": "A07_original_agentd_probe",
        "session_managed_by": "A07_original_agentd_probe",
        "shell_processes_started": 0, "synthetic_agentd_fixture_used": False,
        "renderer_memory_injected": False, "objective_submitted": False,
        "model_called": False, "device_effect_tested": False,
        "physical_display_tested": False, "keyboard_input_tested": False,
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
        (output / "fonts.conf").write_text('<?xml version="1.0"?>\n'
            '<!DOCTYPE fontconfig SYSTEM "fonts.dtd">\n<fontconfig>'
            '<dir>/test-fonts</dir><cachedir>' + str(output / "cache/fontconfig")
            + '</cachedir></fontconfig>\n')
        env["FONTCONFIG_FILE"] = str(output / "fonts.conf")
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
        properties = command("shell-window-properties", ["xprop", "-id", xid, "WM_CLASS", "_NET_WM_PID"])
        require(b"trill-shell" in properties.stdout and str(shell.process.pid).encode() in properties.stdout,
            "actual window identity mismatch")
        report["shell_window"] = {"xid": xid, "pid": shell.process.pid, "class": "trill-shell"}
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
            label = f"phase-{sequence}-{phase_name}"
            (output / (label + ".json")).write_bytes(raw)
            item = {"sequence": sequence, "phase": phase_name, "started_unix_ms": now_ms(),
                "phase_file": label + ".json", "phase_sha256": hashlib.sha256(raw).hexdigest(),
                "session_pid": phase["session_pid"], "session_instance": phase["session_instance"],
                "shell_pid": shell.process.pid, "shell_window_xid": xid}
            report["phases"].append(item)
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
            # This dwell allows updates; only visual review proves the pixels
            # actually show this phase. There is no synthetic renderer signal.
            dwell = time.monotonic() + 2.5
            while time.monotonic() < dwell:
                require(alive(server) and alive(shell), "continuous Shell exited during phase")
                time.sleep(0.05)
            item["capture_started_unix_ms"] = now_ms()
            item["screenshot"] = display.screenshot(output / (label + ".png"))
            item["capture_finished_unix_ms"] = now_ms()
            item["after"] = actual_snapshot(phase, output, label + "-after", item["before"]["hepta"])
            require(alive(server) and alive(shell), "Shell exited before phase acknowledgment")
            item["capture_complete"] = True
            item["visual_review_required"] = True
            item["finished_unix_ms"] = now_ms()
            save()
            acknowledge(phase_directory, sequence, phase["ack"])
            item["acknowledged_unix_ms"] = now_ms()
            previous = phase
        report["capture_passed"] = True
        report["same_shell_pid_all_phases"] = True
        report["same_shell_window_all_phases"] = True
    except BaseException as error:
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
    source = args.source_root.resolve(strict=True)
    base = args.packages.resolve(strict=True)
    private_directory(base)
    stage = base / "package-stage.json"
    staged = json.loads(stage.read_text())
    require(staged["passed"] and len(staged["items"]) == 44, "verified R5 package stage missing")
    require((base / "merged/usr").is_dir(), "existing private package merge required")
    build = json.loads(args.build_receipt.read_text())
    require(build["status"] == "passed" and build["exit_code"] == 0, "passing UI ELF build receipt required")

    def git(*arguments):
        return subprocess.check_output(["git", "-C", str(source), *arguments],
            stderr=subprocess.PIPE, timeout=15).decode().strip()

    head = git("rev-parse", "HEAD")
    require(not git("status", "--porcelain=v1", "--untracked-files=all"),
        "commit capture harness and keep its source checkout clean")
    require(git("rev-parse", build["source_commit"] + "^{tree}") == build["source_tree"],
        "recorded production source tree mismatch")
    ui_tree = git("rev-parse", build["source_commit"] + ":ui")
    require(git("rev-parse", head + ":ui") == ui_tree, "actual UI source differs from recorded ELF source")
    provenance = {"harness_commit": head, "harness_tree": git("rev-parse", head + "^{tree}"),
        "production_ui_commit": build["source_commit"], "production_source_tree": build["source_tree"],
        "unchanged_ui_subtree": ui_tree, "tracked_sources": {}, "binaries": {},
        "package_stage_sha256": digest(stage), "font_sha256": digest(args.font)}
    # Session links this path dependency outside :ui. Its original source
    # and manifest must match the recorded build, not just the renderer tree.
    provenance["unchanged_session_path_dependency"] = {}
    for relative in ("services/hepta-os/src", "services/hepta-os/Cargo.toml", "services/hepta-os/Cargo.lock"):
        built = git("rev-parse", build["source_commit"] + ":" + relative)
        require(git("rev-parse", head + ":" + relative) == built,
            "Session path dependency differs from recorded ELF source: " + relative)
        provenance["unchanged_session_path_dependency"][relative] = built
    require(provenance["font_sha256"] == FONT_SHA256, "unexpected private test font bytes")
    for name in ("trill-shell", "trill-session", "trill-ctl"):
        binary = args.bin_dir / name
        recorded = build["binaries"][name]
        require(binary.is_file() and os.access(binary, os.X_OK)
            and binary.stat().st_size == recorded["bytes"] and digest(binary) == recorded["sha256"],
            "actual ELF differs from source build receipt: " + name)
        provenance["binaries"][name] = recorded
    output = args.output.absolute()
    require(not output.exists() and not output.is_symlink() and output.parent.is_dir(),
        "new output directory with existing parent required")
    output.mkdir(mode=0o700)
    for role, relative, filename in (
        ("harness", "tests/ui/probe-original-hepta-shell.py", "capture-source.py"),
        ("pixels", "tests/ui/x11-ime-client.py", "x11-capture-source.py"),
        ("guard", "tests/integration/hepta/run_original_agentd.py", "child-guard-source.py"),
    ):
        actual = source / relative
        if role == "harness":
            require(Path(__file__).resolve(strict=True) == actual.resolve(strict=True),
                "capture executable is outside its frozen tracked source")
        raw = actual.read_bytes()
        committed = subprocess.check_output(["git", "-C", str(source), "show", head + ":" + relative],
            stderr=subprocess.PIPE, timeout=15)
        require(raw == committed, "capture dependency differs from frozen source: " + role)
        (output / filename).write_bytes(raw)
        provenance["tracked_sources"][role] = {"path": relative,
            "git_blob": git("rev-parse", head + ":" + relative),
            "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)}
    (output / "rust-build-receipt.json").write_bytes(args.build_receipt.read_bytes())
    (output / "package-stage.json").write_bytes(stage.read_bytes())
    phase_directory = args.phase_dir.absolute()
    first_path = phase_directory / "phase-1.json"
    deadline = time.monotonic() + args.startup_timeout
    while not first_path.exists():
        require(time.monotonic() < deadline, "first original Session phase timed out")
        time.sleep(0.05)
    private_directory(phase_directory)
    first, _ = read_phase(first_path)
    runtime = validate_phase(first, 1)
    private_directory(runtime)
    config = {"phase_dir": str(phase_directory), "runtime_dir": str(runtime), "provenance": provenance}
    (output / "capture-config.json").write_text(json.dumps(config, indent=2) + "\n")
    command = ["/usr/bin/bwrap", "--unshare-user", "--unshare-ipc", "--unshare-net", "--unshare-uts",
        "--die-with-parent", "--new-session", "--hostname", "a10-original-hepta-shell",
        "--ro-bind", "/usr", "/host/usr", "--ro-bind", str(base / "packages"), "/a10-packages",
        "--ro-bind", str(base / "merged/usr"), "/usr", "--symlink", "usr/bin", "/bin",
        "--symlink", "usr/sbin", "/sbin", "--symlink", "usr/lib", "/lib",
        "--symlink", "usr/lib64", "/lib64", "--ro-bind", "/etc", "/etc",
        "--ro-bind", "/proc", "/proc", "--dev", "/dev", "--tmpfs", "/tmp",
        "--dir", "/root", "--dir", "/run", "--bind", str(output), str(output),
        "--bind", str(phase_directory), str(phase_directory), "--ro-bind", str(runtime), str(runtime),
        "--ro-bind", str(args.bin_dir), "/ui-bin", "--ro-bind", str(args.font), "/test-fonts/CJK.ttf",
        "--ro-bind", str(output / "capture-source.py"), "/test-source/tests/ui/probe-original-hepta-shell.py",
        "--ro-bind", str(output / "x11-capture-source.py"), "/x11-capture.py",
        "--ro-bind", str(output / "child-guard-source.py"),
        "/test-source/tests/integration/hepta/run_original_agentd.py",
        "--clearenv", "--setenv", "PATH", "/usr/bin:/bin", "--setenv", "LANG", "C.UTF-8",
        "--setenv", "LC_ALL", "C.UTF-8", "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
        "--setenv", "TZ", "UTC", "--chdir", str(output), "/usr/bin/python3", "-B",
        "/test-source/tests/ui/probe-original-hepta-shell.py", "--inside", "--output", str(output)]
    namespace = {"argv": command, "started_unix_ms": now_ms(), "returncode": None,
        "shared_pid_namespace": True, "system_install_performed": False}
    guard = load_module("shell_live_outer_guard", output / "child-guard-source.py")
    require(guard.child_anchor_available(), "waitable namespace child identity required")
    with (output / "namespace.stdout.log").open("xb") as stdout, (output / "namespace.stderr.log").open("xb") as stderr:
        child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout,
            stderr=stderr, start_new_session=True)
        group = guard.ChildGroup(child)
        try:
            deadline = time.monotonic() + 960
            while group.observe_exit() is None:
                require(time.monotonic() < deadline, "bounded capture namespace timeout")
                time.sleep(0.1)
            namespace["returncode"] = group.reap()
        except BaseException as error:
            namespace["error"] = str(error)
            namespace["returncode"] = guard.terminate_group(group)
            raise
        finally:
            namespace["finished_unix_ms"] = now_ms()
            (output / "namespace.json").write_text(json.dumps(namespace, indent=2) + "\n")
    print(json.dumps(namespace, indent=2))
    require(namespace["returncode"] == 0, "actual Shell capture namespace failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inside", action="store_true")
    parser.add_argument("--parent-pid", type=int)
    parser.add_argument("--exec-child", nargs=argparse.REMAINDER)
    parser.add_argument("--source-root", type=Path, default=ROOT)
    parser.add_argument("--packages", type=Path)
    parser.add_argument("--bin-dir", type=Path)
    parser.add_argument("--build-receipt", type=Path)
    parser.add_argument("--font", type=Path)
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
