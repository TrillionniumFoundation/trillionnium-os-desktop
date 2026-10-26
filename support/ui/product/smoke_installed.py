#!/usr/bin/env python3
"""Run real user-systemd/X11 installation acceptance in new private paths.

Requires two distinct real product packages. Never builds fake executables,
changes HOME, imports manager environment, or touches an existing unit.
"""
import argparse
import ctypes as C
import importlib.util
import json
import os
from pathlib import Path
import re
import select
import shutil
import signal
import subprocess
import sys
import time
import uuid

import desktop
import acceptance_identity


def require(value, message):
    if not value:
        raise RuntimeError(message)


def checkpoint():
    workspaces = ("personal", "research", "build")
    return {"version": 3, "active_workspace": "research",
            "drafts": [{"workspace": workspace, "text": "saved " + workspace + " 中文",
                        "contexts": []} for workspace in workspaces],
            "workspaces": [{"workspace": workspace, "rooms": ["unsent " + workspace + " 📝"],
                            "active_room": 0, "contexts": [], "tab": "context"}
                           for workspace in workspaces]}


def verify_migrated_checkpoint(seed, recovered):
    """v3 text becomes v4 anonymous local text, never an attached principal."""
    require(recovered.get("version") == 4, "renderer did not write the v4 checkpoint")
    for key in ("active_workspace", "drafts"):
        require(recovered.get(key) == seed[key], "recovery changed " + key)
    entries = recovered.get("workspaces")
    require(isinstance(entries, list) and len(entries) == len(seed["workspaces"]),
            "recovery lost a workspace")
    for original, entry in zip(seed["workspaces"], entries):
        for key in ("workspace", "contexts", "tab"):
            require(entry.get(key) == original[key], "recovery changed workspace " + key)
        archive = entry.get("local_archive")
        if archive is None:
            require(entry.get("rooms") == original["rooms"]
                    and entry.get("active_room") == original["active_room"],
                    "plain composer recovery lost text or selection")
        else:
            require(archive == {"version": 1, "partitions": [{"principal": None,
                        "rooms": original["rooms"], "active": original["active_room"]}]}
                    and entry.get("rooms") == [] and entry.get("active_room") == 0,
                    "shared composer migration changed anonymous text or principal")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path, help="extracted first real package root")
    parser.add_argument("--upgrade-package", required=True, type=Path, help="extracted distinct release")
    parser.add_argument("--expected-manifest-sha256", required=True, help="trusted first build manifest hash")
    parser.add_argument("--expected-upgrade-manifest-sha256", required=True, help="trusted next build manifest hash")
    parser.add_argument("--expected-desktop", required=True)
    parser.add_argument("--expected-upgrade-desktop", help="defaults to the same build commit")
    parser.add_argument("--expected-hepta", required=True)
    parser.add_argument("--hepta-source", required=True, type=Path,
                        help="original test-helper checkout; independent of the compiled package pin")
    parser.add_argument("--evidence", required=True, type=Path, help="new absolute private directory")
    parser.add_argument("--runtime-root", required=True, type=Path,
                        help="caller-created empty user-owned 0700 short directory for private XDG/TMP paths")
    parser.add_argument("--unit-dir", type=Path, default=Path.home() / ".config/systemd/user")
    parser.add_argument("--renderer", choices=("makepad",), default="makepad")
    parser.add_argument("--makepad-resources", type=Path, help="prepared original bundle, if first package has none")
    parser.add_argument("--cjk-font", type=Path)
    options = parser.parse_args()
    owner_helper = (options.hepta_source / "apps/hepta-control-ui/test/x11_client_owner.py").resolve(strict=True)
    capture_helper = (Path(__file__).resolve().parents[3] / "tests/ui/native-makepad/capture.py").resolve(strict=True)
    output = options.evidence
    require(output.is_absolute() and not output.exists(), "evidence must be a new absolute directory")
    require(options.unit_dir.is_absolute(), "unit directory must be absolute")
    runtime = options.runtime_root
    runtime_identity = acceptance_identity.runtime_root_identity(runtime)
    require(not any(runtime.iterdir()), "--runtime-root must be empty; use a new private directory for each attempt")
    require(not output.resolve().is_relative_to(runtime), "evidence must be outside --runtime-root")
    first = acceptance_identity.pinned_package(options.package, options.expected_manifest_sha256)
    second = acceptance_identity.pinned_package(options.upgrade_package, options.expected_upgrade_manifest_sha256)
    for manifest, expected in ((first, options.expected_desktop),
                               (second, options.expected_upgrade_desktop or options.expected_desktop)):
        require(manifest["desktop_commit"] == expected
                and manifest["hepta_commit"] == options.expected_hepta, "unexpected package source pair")
    require(first["release_id"] != second["release_id"], "upgrade needs a distinct real release id")
    if options.makepad_resources:
        require(options.makepad_resources.is_absolute(), "resource path must be absolute")
        desktop.native_resource_files(options.makepad_resources, options.expected_hepta)
    require(options.makepad_resources or (options.package / "resources").is_dir(),
            "first Makepad package requires the complete original resource bundle")
    require((options.upgrade_package / "resources").is_dir(),
            "upgrade must exercise its complete installed original resource bundle")
    for tool in ("systemctl", "Xvfb", "xdotool", "xwininfo"):
        require(shutil.which(tool), "missing required real host tool: " + tool)
    unit = "trillionnium-desktop-install-" + uuid.uuid4().hex[:12] + "-session.service"
    unit_path = options.unit_dir / unit
    require(not unit_path.exists() and not unit_path.is_symlink(), "dedicated unit already exists")
    dropin_dir = options.unit_dir / (unit + ".d")
    dropin = dropin_dir / "10-isolated-qualification.conf"
    require(not dropin_dir.exists() and not dropin_dir.is_symlink(), "dedicated unit drop-in already exists")
    # Keep the actual manager bus while isolating the application's runtime.
    manager_environment = dict(os.environ)
    bus = manager_environment.get("DBUS_SESSION_BUS_ADDRESS")
    if not bus:
        manager_runtime = manager_environment.get("XDG_RUNTIME_DIR")
        require(manager_runtime and (Path(manager_runtime) / "bus").is_socket(), "no existing user service bus")
        bus = "unix:path=" + str(Path(manager_runtime) / "bus")
    manager_environment["DBUS_SESSION_BUS_ADDRESS"] = bus
    subprocess.run(["systemctl", "--user", "show", "--property=Version", "--value"],
                   env=manager_environment, check=True, capture_output=True, timeout=10)
    def manager_lanes():
        raw = subprocess.run(["systemctl", "--user", "show-environment"], env=manager_environment,
                             check=True, capture_output=True, timeout=10).stdout
        return acceptance_identity.manager_lane_names(raw)
    excluded_lanes = (acceptance_identity.KNOWN_EXECUTION_LANES | manager_lanes()
                      | {key for key in manager_environment if key.startswith(acceptance_identity.LANE_PREFIXES)})
    private_environment = {"XDG_CONFIG_HOME": str(runtime / "config"),
                           "XDG_CACHE_HOME": str(runtime / "cache"), "XDG_DATA_HOME": str(runtime / "data"),
                           "TMPDIR": str(runtime / "tmp")}
    dropin_bytes = ("[Service]\nUnsetEnvironment=" + " ".join(sorted(excluded_lanes))
                   + "\nEnvironment=" + " ".join(desktop.systemd_quote(key + "=" + value)
                                                   for key, value in sorted(private_environment.items())) + "\n").encode()
    output.mkdir(mode=0o700, parents=True)
    prefix, state = output / "installation", runtime / "state"
    for directory in private_environment.values():
        Path(directory).mkdir(mode=0o700)
    state.mkdir(mode=0o700)
    draft_dir = state / "trillionnium-ui"
    draft_dir.mkdir(mode=0o700)
    legacy_draft_file = draft_dir / "workspace-checkpoint-v3.json"
    draft_file = draft_dir / "workspace-checkpoint-v4.json"
    seed = checkpoint()
    original_seed_bytes = desktop.json_bytes(seed)
    desktop.atomic_write(legacy_draft_file, original_seed_bytes)
    retained = draft_dir / "acceptance-user-retained.txt"
    desktop.atomic_write(retained, b"disposable acceptance user data\n")
    config = output / "config/config.json"
    launcher = output / "bin/trillionnium-desktop"
    integration = output / "applications/trillionnium-desktop.desktop"
    env = acceptance_identity.isolated_environment(manager_environment)
    env.update(private_environment)
    env.update({"XDG_RUNTIME_DIR": str(runtime), "XDG_STATE_HOME": str(state),
                "WINIT_UNIX_BACKEND": "x11", "LIBGL_ALWAYS_SOFTWARE": "1",
                "LP_NUM_THREADS": "2", "MESA_SHADER_CACHE_DISABLE": "true"})
    env.pop("WAYLAND_DISPLAY", None)
    env.pop("XAUTHORITY", None)
    report = {"schema_version": 1, "status": "running", "unit": unit,
              "qualification": "isolated-linux-host-installation", "renderer": options.renderer,
              "first_package": first, "upgrade_package": second,
              "expected_manifest_sha256": options.expected_manifest_sha256,
              "expected_upgrade_manifest_sha256": options.expected_upgrade_manifest_sha256,
              "excluded_host_lane_names": sorted(excluded_lanes),
              "harness_sha256": desktop.digest(Path(__file__).read_bytes()),
              "identity_gate_sha256": desktop.digest(Path(acceptance_identity.__file__).read_bytes()),
              "original_xres_helper": {"path": str(owner_helper),
                                       "sha256": desktop.digest(owner_helper.read_bytes())},
              "capture_helper": {"path": str(capture_helper),
                                 "sha256": desktop.digest(capture_helper.read_bytes())},
              "runtime_root_identity": runtime_identity,
              "private_xdg_environment": dict(private_environment, XDG_RUNTIME_DIR=str(runtime), XDG_STATE_HOME=str(state)),
              "production_authority_verified": False, "physical_input_verified": False,
              "human_visual_review_verified": False, "font_pixels_verified": False,
              "checks": {}, "screenshots": [], "commands": []}
    running = []
    display = None
    xvfb = None
    installed = False
    dropin_owned = False
    counter = 0

    def save():
        desktop.atomic_write(output / "acceptance.json", desktop.json_bytes(report))

    def command(label, argv, check=True, timeout=20):
        nonlocal counter
        counter += 1
        result = subprocess.run([str(x) for x in argv], env=env, capture_output=True, timeout=timeout)
        name = f"{counter:03}-{label}"
        (output / (name + ".stdout")).write_bytes(result.stdout)
        (output / (name + ".stderr")).write_bytes(result.stderr)
        report["commands"].append({"label": label, "argv": [str(x) for x in argv],
                                   "exit_code": result.returncode, "log_prefix": name})
        if check:
            require(result.returncode == 0, label + " failed; see " + name + ".stderr")
        return result

    def install_args(package):
        return [sys.executable, package / "desktop.py", "--prefix", prefix, "install",
                "--package", package, "--bin-dir", launcher.parent,
                "--unit-dir", options.unit_dir, "--unit-name", unit,
                "--applications-dir", integration.parent, "--config", config]

    def read_snapshot(label):
        result = command(label, [launcher, "doctor", "--live"])
        value = json.loads(result.stdout)
        require(value["ready"] and value["checks"]["session_service_pid"] > 0,
                "installed Session failed live service ownership check")
        release = desktop.current_release(prefix)
        manifest = desktop.verify_package(release)
        report["checks"][label + "-process"] = acceptance_identity.process_identity(
            value["checks"]["session_service_pid"], release / "bin/trill-session",
            manifest["files"]["bin/trill-session"]["sha256"])
        return value["live_session"]["session_instance"]

    def observe_owned_frame(label, pid, binary_name, deadline, expected_identity=None, expected_window=None):
        # The original 25-second startup deadline covers mapping, ownership and
        # the first nonuniform frame. Xlib capture runs in a bounded child so a
        # stalled XGetImage cannot strand the installation harness.
        handle = os.pidfd_open(pid)
        try:
            acceptance_identity.remaining_timeout(deadline, 25)
            release = desktop.current_release(prefix)
            manifest = desktop.verify_package(release)
            identity = None
            xid = expected_window
            attempts = 0

            def alive():
                if identity is None:
                    # The retained launcher may still be execing the actual
                    # Shell. Its mapped XRes window is the image-check boundary.
                    acceptance_identity.require_live_pidfd(handle, pid)
                else:
                    acceptance_identity.require_same_process(handle, identity)

            def window_observation():
                alive()
                found = command(label + "-xres-owner", [sys.executable, "-B", owner_helper,
                                "--pid", pid, "--find-visible"], check=False,
                                timeout=acceptance_identity.remaining_timeout(deadline, 8))
                alive()
                acceptance_identity.remaining_timeout(deadline, 25)
                require(found.returncode in (0, 1), "original XRes window-owner query failed")
                observation = json.loads(found.stdout)
                observed = acceptance_identity.window_identity(observation, pid, xid)
                require((found.returncode == 0) == (observed is not None), "XRes result disagrees with its exit status")
                return observed, observation

            while True:
                observed, observation = window_observation()
                if observed is not None:
                    xid = observed
                    if identity is None:
                        identity = acceptance_identity.process_identity(pid, release / "bin" / binary_name,
                                                                       manifest["files"]["bin/" + binary_name]["sha256"])
                        require(expected_identity is None or identity == expected_identity,
                                label + " changed its original process identity")
                        if binary_name == "trill-shell":
                            require(identity["argv"][-2:] == ["--renderer", "makepad"], "actual Shell did not select Makepad")
                        alive()
                        report["checks"][label + "-process"] = identity
                    attempts += 1
                    captured = command(label + "-window-pixels", [sys.executable, "-B", capture_helper,
                                       "--window-id", xid, "--raise-window", "--output", output / (label + ".png")],
                                       timeout=acceptance_identity.remaining_timeout(deadline, 8))
                    frame = json.loads(captured.stdout)
                    # Requery the original server-side owner after capturing;
                    # another process or a replacement XID cannot supply proof.
                    confirmed, observation = window_observation()
                    require(confirmed == xid, "owned window disappeared during capture")
                    ready = acceptance_identity.nonuniform_window_frame(frame, xid)
                    report["checks"][label + "-window-owner"] = observation["window"]
                    report["checks"][label + "-window-frame"] = {
                        "nonuniform_owned_pixels": ready, "attempts": attempts,
                        "startup_budget_seconds": 25, "last_capture": frame,
                        "human_visual_review_verified": False}
                    if ready:
                        context = command(label + "-display-context", [sys.executable, "-B", capture_helper,
                                          "--root-context", "--output", output / (label + "-display.png")],
                                          timeout=acceptance_identity.remaining_timeout(deadline, 8))
                        acceptance_identity.require_same_process(handle, identity)
                        acceptance_identity.remaining_timeout(deadline, 25)
                        report["screenshots"].append(dict(frame, role="owned-window-nonuniform-frame", owner_pid=pid))
                        report["screenshots"].append(dict(json.loads(context.stdout), role="private-display-context-only"))
                        return identity, xid
                time.sleep(acceptance_identity.remaining_timeout(deadline, 0.1))
        finally:
            os.close(handle)

    def start_shell(label):
        require(acceptance_identity.runtime_root_identity(runtime) == runtime_identity,
                "caller-owned --runtime-root identity changed")
        require(manager_lanes() <= excluded_lanes, "user manager added an unisolated host lane during qualification")
        log = (output / (label + ".log")).open("wb")
        deadline = time.monotonic() + 25
        process = subprocess.Popen([str(launcher), "run"], env=env, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        log.close()
        running.append(process)
        _, xid = observe_owned_frame(label, process.pid, "trill-shell", deadline)
        return process, xid

    def close_shell(label, process, window):
        require(process.poll() is None, label + " exited before its normal window close")
        command(label + "-close-owner", [sys.executable, "-B", owner_helper,
                "--pid", process.pid, "--window-id", window])
        # Deliver the normal WM_DELETE_WINDOW lifecycle; do not SIGTERM a
        # successful recovery test before its renderer has queued final state.
        class Client(C.Structure):
            _fields_ = [("type", C.c_int), ("serial", C.c_ulong), ("send_event", C.c_int),
                        ("display", C.c_void_p), ("window", C.c_ulong), ("message_type", C.c_ulong),
                        ("format", C.c_int), ("data", C.c_long * 5)]
        class Event(C.Union):
            _fields_ = [("client", Client), ("padding", C.c_long * 24)]
        event = Event()
        event.client.type, event.client.send_event, event.client.format = 33, 1, 32
        event.client.display, event.client.window = display.handle, window
        event.client.message_type = display.lib.XInternAtom(display.handle, b"WM_PROTOCOLS", 0)
        event.client.data[0] = display.lib.XInternAtom(display.handle, b"WM_DELETE_WINDOW", 0)
        send = display.lib.XSendEvent
        send.argtypes, send.restype = [C.c_void_p, C.c_ulong, C.c_int, C.c_long, C.c_void_p], C.c_int
        require(send(display.handle, window, 0, 0, C.byref(event)), "WM_DELETE_WINDOW was not sent")
        display.lib.XFlush(display.handle)
        require(process.wait(timeout=12) == 0, label + " normal close failed")
        require(legacy_draft_file.read_bytes() == original_seed_bytes,
                "migration changed the preserved v3 checkpoint")
        require(draft_file.is_file() and draft_file.stat().st_mode & 0o777 == 0o600,
                "no private v4 renderer checkpoint was written")
        verify_migrated_checkpoint(seed, desktop.read_json(draft_file, 64 * 1024 * 1024))

    def content_hashes():
        return {path.relative_to(state).as_posix(): desktop.digest(path.read_bytes())
                for path in state.rglob("*") if path.is_file()}

    try:
        save()
        read_fd, write_fd = os.pipe()
        log = (output / "xvfb.log").open("wb")
        try:
            xvfb = subprocess.Popen(["Xvfb", "-displayfd", str(write_fd), "-screen", "0", "1440x1000x24",
                                     "-nolisten", "tcp"], env=manager_environment, pass_fds=(write_fd,),
                                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        finally:
            os.close(write_fd)
            log.close()
        try:
            require(select.select([read_fd], [], [], 10)[0], "private Xvfb did not become ready")
            number = os.read(read_fd, 32).decode().strip()
            require(number.isdigit(), "Xvfb returned no private display number")
        finally:
            os.close(read_fd)
        env["DISPLAY"] = ":" + number
        os.environ["DISPLAY"] = env["DISPLAY"]
        helper = Path(__file__).resolve().parents[3] / "tests/ui/x11-ime-client.py"
        spec = importlib.util.spec_from_file_location("owned_x11_capture", helper)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        display = module.Display()
        command("install", install_args(options.package))
        installed = True
        dropin_dir.mkdir(mode=0o700)
        desktop.atomic_write(dropin, dropin_bytes)
        dropin_owned = True
        cfg = desktop.read_json(config)
        cfg["renderer"] = options.renderer
        cfg["makepad_resources"] = str(options.makepad_resources) if options.makepad_resources else None
        cfg["cjk_font"] = str(options.cjk_font) if options.cjk_font else None
        desktop.atomic_write(config, desktop.json_bytes(cfg))
        config_bytes = config.read_bytes()
        report["checks"]["installed_source"] = json.loads(command("doctor-config", [launcher, "doctor"]).stdout)
        process, window = start_shell("shell-first")
        first_session = read_snapshot("doctor-first-live")
        rejected = command("reject-active-upgrade", install_args(options.upgrade_package), check=False)
        require(rejected.returncode != 0 and desktop.current_release(prefix).name == first["release_id"],
                "upgrade did not refuse an active Session")
        report["checks"]["active_upgrade_refused"] = True
        # A real independent application stays under Session across Shell exits.
        ctl = desktop.current_release(prefix) / "bin/trill-ctl"
        notes_deadline = time.monotonic() + 25
        app = json.loads(command("launch-owned-notes", [ctl, "launch", "personal", "notes"],
                                 timeout=acceptance_identity.remaining_timeout(notes_deadline, 20)).stdout)["task"]
        require(app["state"] == "running" and app["pid"], "actual Notes did not start")
        incarnation = app.get("notes_destination", {}).get("incarnation")
        require(isinstance(incarnation, str) and re.fullmatch("[0-9a-f]{32}", incarnation)
                and app["notes_destination"]["original_owner_registered"] is False,
                "isolated Notes lacks its own incarnation or inherited an original-owner registration")
        notes_identity, notes_window = observe_owned_frame("notes-first", app["pid"], "trill-app-window", notes_deadline)
        close_shell("first", process, window)
        require(read_snapshot("doctor-shell-closed") == first_session, "closing Shell replaced Session")
        process, window = start_shell("shell-recovered")
        require(read_snapshot("doctor-shell-recovered") == first_session, "Shell restart changed Session generation")
        notes_deadline = time.monotonic() + 25
        snapshot = json.loads(command("notes-after-shell-restart", [ctl, "snapshot"],
                                      timeout=acceptance_identity.remaining_timeout(notes_deadline, 20)).stdout)
        task = next(task for task in snapshot["tasks"] if task["id"] == app["id"])
        require(task["state"] == "running" and task["pid"] == app["pid"], "Notes did not survive Shell restart")
        require(task.get("notes_destination", {}).get("incarnation") == incarnation,
                "Notes restart changed its application incarnation")
        observe_owned_frame("notes-after-shell-restart", task["pid"], "trill-app-window", notes_deadline,
                            expected_identity=notes_identity, expected_window=notes_window)
        report["checks"]["surviving_notes_process"] = notes_identity
        close_shell("recovered", process, window)
        report["checks"]["shell_restart_same_session_and_notes"] = True
        report["checks"]["all_workspace_checkpoint_recovered"] = True
        report["checks"]["v3_preserved_and_migrated_to_v4"] = True
        command("stop-first-session", [launcher, "stop"])
        before_upgrade = content_hashes()
        command("upgrade", install_args(options.upgrade_package))
        require(desktop.current_release(prefix).name == second["release_id"]
                and config.read_bytes() == config_bytes and content_hashes() == before_upgrade,
                "upgrade changed config/data or did not select the new release")
        # If bundled, verify resources are usable from the installed release,
        # independent of the external preparation directory. This is an
        # explicit temporary config choice, not an upgrade-time rewrite.
        if options.renderer == "makepad" and (desktop.current_release(prefix) / "resources").is_dir():
            bundled = dict(cfg, makepad_resources=None)
            desktop.atomic_write(config, desktop.json_bytes(bundled))
            report["checks"]["bundled_resource_relocation"] = True
        process, window = start_shell("shell-upgraded")
        new_session = read_snapshot("doctor-upgraded-live")
        require(new_session != first_session, "stopped/restarted Session reused its old generation")
        close_shell("upgraded", process, window)
        command("stop-upgraded-session", [launcher, "stop"])
        desktop.atomic_write(config, config_bytes)
        before_rollback = content_hashes()
        command("rollback", [launcher, "rollback"])
        require(desktop.current_release(prefix).name == first["release_id"]
                and config.read_bytes() == config_bytes and content_hashes() == before_rollback,
                "rollback changed user data/config or selected the wrong release")
        process, window = start_shell("shell-rolled-back")
        rolled_session = read_snapshot("doctor-rolled-back-live")
        require(rolled_session not in (first_session, new_session), "rollback reused an old Session incarnation")
        ctl = desktop.current_release(prefix) / "bin/trill-ctl"
        notes_deadline = time.monotonic() + 25
        rolled_notes = json.loads(command("launch-rolled-back-notes", [ctl, "launch", "personal", "notes"],
                                         timeout=acceptance_identity.remaining_timeout(notes_deadline, 20)).stdout)["task"]
        require(rolled_notes["state"] == "running" and rolled_notes["pid"], "rolled-back Notes did not start")
        rolled_notes_identity, _ = observe_owned_frame("notes-rolled-back", rolled_notes["pid"],
                                                       "trill-app-window", notes_deadline)
        report["checks"]["rolled_back_notes_process"] = rolled_notes_identity
        close_shell("rolled-back", process, window)
        command("stop-rolled-back-session", [launcher, "stop"])
        report["checks"]["rollback_actual_makepad_and_notes"] = True
        report["checks"]["upgrade_rollback_preserved_data"] = True
        before_uninstall = content_hashes()
        command("uninstall", [launcher, "uninstall"])
        installed = False
        require(not launcher.exists() and not unit_path.exists() and not integration.exists()
                and not (prefix / "releases").exists(), "uninstall retained managed executable integrations")
        require(config.read_bytes() == config_bytes and content_hashes() == before_uninstall
                and retained.read_bytes() == b"disposable acceptance user data\n", "uninstall deleted user data")
        report["checks"]["uninstall_preserved_config_and_state"] = True
        report["retained_state_sha256"] = before_uninstall
        require(acceptance_identity.runtime_root_identity(runtime) == runtime_identity,
                "caller-owned --runtime-root identity changed")
        report["status"] = "passed"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = str(error)
        raise
    finally:
        for process in running:
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait(timeout=3)
                except (OSError, subprocess.SubprocessError) as error:
                    report.setdefault("cleanup_errors", []).append(str(error))
        try:
            if unit_path.exists():
                # This path was absent at entry; confirm it references our
                # private prefix before issuing even this dedicated stop.
                expected_exec = ("ExecStart=" + desktop.systemd_quote(launcher) + " session\n").encode()
                require(expected_exec in unit_path.read_bytes(), "dedicated unit contents changed")
                stopped = command("cleanup-stop-owned-unit", ["systemctl", "--user", "stop", unit], check=False)
                if installed and stopped.returncode == 0:
                    result = command("cleanup-uninstall", [launcher, "uninstall"], check=False)
                    installed = result.returncode != 0
                if unit_path.exists():
                    report["cleanup_attention"] = "Dedicated unit retained; inspect logs before manual cleanup"
        except Exception as error:
            report.setdefault("cleanup_errors", []).append(str(error))
        if dropin_owned:
            try:
                require(dropin.read_bytes() == dropin_bytes, "dedicated isolation drop-in changed")
                dropin.unlink()
                dropin_dir.rmdir()
                command("cleanup-owned-dropin-reload", ["systemctl", "--user", "daemon-reload"])
            except Exception as error:
                report.setdefault("cleanup_errors", []).append(str(error))
                if report["status"] == "passed":
                    report["status"] = "failed"
        if display:
            display.close()
        if xvfb and xvfb.poll() is None:
            xvfb.terminate()
            try:
                xvfb.wait(timeout=5)
            except subprocess.TimeoutExpired:
                xvfb.kill()
                xvfb.wait(timeout=3)
        report["remaining_owned_shells"] = [process.pid for process in running if process.poll() is None]
        if report["remaining_owned_shells"] or report.get("cleanup_attention") or report.get("cleanup_errors"):
            report["status"] = "failed"
        save()
    print(json.dumps({"status": report["status"], "evidence": str(output / "acceptance.json")}, indent=2))
    require(report["status"] == "passed", "installation qualification cleanup failed; inspect acceptance.json")


if __name__ == "__main__":
    main()
