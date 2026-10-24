#!/usr/bin/env python3
"""Exercise ordinary Notes reopening in an owned Xvfb and private D-Bus session.

This drives the real egui editor and saved-note controls through AT-SPI and
the owned X11 clipboard/keyboard. It does not install a Hepta authority, use a
user's desktop, or qualify physical IME, mobile input or original-writer finality.
"""

import argparse
import contextlib
import ctypes as C
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import select
import shutil
import signal
import struct
import subprocess
import sys
import time


def require(value, message):
    if not value:
        raise RuntimeError(message)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def terminate_child(proc):
    # Popen owns this exact unreaped child; never signal an arbitrary PID/group.
    if proc.poll() is None:
        proc.terminate()
    try:
        proc.wait(timeout=4)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=4)


@contextlib.contextmanager
def isolated_display(output):
    reader, writer = os.pipe()
    with (output / "xvfb.log").open("wb") as log:
        proc = subprocess.Popen(
            ["Xvfb", "-displayfd", str(writer), "-screen", "0", "1280x900x24",
             "-nolisten", "tcp", "-noreset"],
            pass_fds=(writer,), stdout=log, stderr=subprocess.STDOUT,
        )
        os.close(writer)
        try:
            require(select.select([reader], [], [], 12)[0], "owned Xvfb startup deadline")
            display = os.read(reader, 32).decode().strip()
            require(display.isdecimal() and proc.poll() is None, "owned Xvfb startup failed")
            os.environ["DISPLAY"] = ":" + display
            yield proc
        finally:
            os.close(reader)
            terminate_child(proc)


def close_window(owner, window, pid):
    """Send ordinary WM_DELETE_WINDOW to the server-verified owned window."""
    owner.require_pid(window, pid)

    class Data(C.Union):
        _fields_ = [("l", C.c_long * 5)]

    class ClientMessage(C.Structure):
        _fields_ = [("type", C.c_int), ("serial", C.c_ulong), ("send_event", C.c_int),
                    ("display", C.c_void_p), ("window", C.c_ulong),
                    ("message_type", C.c_ulong), ("format", C.c_int), ("data", Data)]

    class Event(C.Union):
        _fields_ = [("client", ClientMessage), ("padding", C.c_long * 24)]

    x11 = owner.x11
    x11.XInternAtom.argtypes, x11.XInternAtom.restype = [C.c_void_p, C.c_char_p, C.c_int], C.c_ulong
    x11.XSendEvent.argtypes, x11.XSendEvent.restype = [C.c_void_p, C.c_ulong, C.c_int, C.c_long, C.POINTER(Event)], C.c_int
    x11.XFlush.argtypes, x11.XFlush.restype = [C.c_void_p], C.c_int
    event = Event()
    event.client.type = 33  # ClientMessage, from Xlib.h.
    event.client.display = owner.handle
    event.client.window = window
    event.client.message_type = x11.XInternAtom(owner.handle, b"WM_PROTOCOLS", 0)
    event.client.format = 32
    event.client.data.l[0] = x11.XInternAtom(owner.handle, b"WM_DELETE_WINDOW", 0)
    require(x11.XSendEvent(owner.handle, window, 0, 0, C.byref(event)), "WM_DELETE_WINDOW dispatch failed")
    x11.XFlush(owner.handle)


def run(args, result):
    import gi
    gi.require_version("Atspi", "2.0")
    gi.require_version("Gtk", "3.0")
    gi.require_version("Gdk", "3.0")
    from gi.repository import Atspi, Gdk, Gio, GLib, Gtk

    bootstrap = load("notes_bootstrap", Path(__file__).with_name("test-notes-bootstrap-ipc.py"))
    crash = load("notes_crash", Path(__file__).with_name("test-notes-crash-recovery.py"))
    xres_path = args.hepta_root / "apps/hepta-control-ui/test/x11_client_owner.py"
    xres = load("notes_xres_owner", xres_path)
    result["xres_helper_sha256"] = digest(xres_path)

    def wait_for(probe, label, timeout=12):
        deadline, last = time.monotonic() + timeout, None
        while time.monotonic() < deadline:
            context = GLib.MainContext.default()
            for _ in range(128):
                if not context.pending():
                    break
                context.iteration(False)
            try:
                value = probe()
                if value:
                    return value
            except Exception as error:
                last = str(error)
            time.sleep(0.025)
        raise RuntimeError(f"{label}: deadline; last error: {last}")

    def walk(node):
        pending = [node]
        for _ in range(4096):
            if not pending:
                return
            item = pending.pop()
            yield item
            pending.extend(item.get_child_at_index(i) for i in range(item.get_child_count())
                           if item.get_child_at_index(i) is not None)
        raise RuntimeError("AT-SPI traversal bound")

    def named(app, name, prefix=False):
        return next((node for node in walk(app)
                     if (node.get_name().startswith(name) if prefix else node.get_name() == name)), None)

    def checkpoint(target):
        folder = f"{target['session_instance']}-{target['task_id']}-{target['incarnation']}"
        return args.output / "notes-state" / folder / "document.json"

    def saved(target, text):
        data = json.loads(checkpoint(target).read_bytes())
        return data if data["text"] == text else None

    def record(name):
        result["checks"].append({"name": name, "passed": True})

    def screenshot(name):
        root = Gdk.get_default_root_window()
        pixels = Gdk.pixbuf_get_from_window(root, 0, 0, root.get_width(), root.get_height())
        require(pixels is not None and len(set(pixels.get_pixels())) > 1, "empty display capture")
        path = args.output / name
        pixels.savev(str(path), "png", [], [])
        result.setdefault("screenshots", []).append({"file": name, "sha256": digest(path)})

    # AccessKit's Unix adapter starts when the accessibility bus is enabled.
    # This is the fresh dbus-run-session bus owned by this fixture, not the
    # desktop user's settings. Set both properties before launching Notes.
    bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    for property_name in ("IsEnabled", "ScreenReaderEnabled"):
        bus.call_sync("org.a11y.Bus", "/org/a11y/bus", "org.freedesktop.DBus.Properties", "Set",
                      GLib.Variant("(ssv)", ("org.a11y.Status", property_name, GLib.Variant("b", True))),
                      None, Gio.DBusCallFlags.NONE, 5000, None)
    status = bus.call_sync("org.a11y.Bus", "/org/a11y/bus", "org.freedesktop.DBus.Properties", "GetAll",
                           GLib.Variant("(s)", ("org.a11y.Status",)), None, Gio.DBusCallFlags.NONE, 5000, None)
    result["owned_a11y_status"] = status.unpack()[0]
    require(all(result["owned_a11y_status"].get(key) is True for key in ("IsEnabled", "ScreenReaderEnabled")),
            "owned accessibility bus was not enabled")
    Atspi.init()
    Gtk.init([])
    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    state = args.output / "notes-state"
    state.mkdir(mode=0o700)
    with bootstrap.launched(args.binary_dir, state) as (session, parent, socket_path, app_binary):
        try:
            offer, effect, recovery = bootstrap.receive_offer(parent)
            with effect, recovery, xres.XResOwner() as owner:
                bootstrap.acknowledge(parent, offer, "attached")
                old_target = offer["target"]

                def snapshot():
                    return bootstrap.roundtrip(socket_path, {"type": "snapshot"})

                def owned_window(task_id):
                    def observe():
                        task = next((t for t in snapshot()["tasks"] if t["id"] == task_id), None)
                        if not task or task["ui_first_frame_unix_ms"] is None:
                            return None
                        for pid, identity in bootstrap.owned_children(session, app_binary).items():
                            raw = Path(f"/proc/{pid}/cmdline").read_bytes().split(b"\0")
                            if b"--task-id" in raw and raw[raw.index(b"--task-id") + 1] == str(task_id).encode():
                                window = owner.find_visible(pid)
                                if window:
                                    return pid, identity, window
                        return None
                    pid, identity, window = wait_for(observe, f"owned Notes task {task_id} window")
                    result.setdefault("windows", []).append(window)
                    return pid, identity, window["xid"]

                def accessible(pid):
                    def locate():
                        desktop = Atspi.get_desktop(0)
                        return next((desktop.get_child_at_index(i) for i in range(desktop.get_child_count())
                                     if desktop.get_child_at_index(i).get_process_id() == pid), None)
                    return wait_for(locate, "exact Notes PID registered with AT-SPI")

                def focus(pid, identity, window, app):
                    require(bootstrap.child_identity(pid) == identity, "Notes child identity changed")
                    owner.require_pid(window, pid)
                    subprocess.run(["xdotool", "windowfocus", "--sync", str(window)], check=True, timeout=4)
                    field = wait_for(lambda: named(app, "Notes / 笔记 · try composing Chinese with your host IME"),
                                     "Notes editor semantic name")
                    require(field.get_component_iface().grab_focus(), "Notes editor focus action refused")
                    wait_for(lambda: field.get_state_set().contains(Atspi.StateType.FOCUSED), "Notes editor focused")
                    return field

                def key(pid, identity, window, value):
                    require(bootstrap.child_identity(pid) == identity, "Notes child identity changed before input")
                    owner.require_pid(window, pid)
                    focused = int(subprocess.check_output(["xdotool", "getwindowfocus"], text=True, timeout=3))
                    require(focused == window, "owned Notes window lost X11 focus")
                    subprocess.run(["xdotool", "key", "--clearmodifiers", value], check=True, timeout=4)

                def click(pid, identity, window, node):
                    require(bootstrap.child_identity(pid) == identity, "Notes child identity changed before action")
                    owner.require_pid(window, pid)
                    # Xvfb has no window manager to focus a newly opened
                    # window. Keep the production ActivationGuard intact.
                    subprocess.run(["xdotool", "windowfocus", "--sync", str(window)], check=True, timeout=4)
                    require(node.get_component_iface().grab_focus(), "Notes control focus refused")
                    wait_for(lambda: node.get_state_set().contains(Atspi.StateType.FOCUSED), "Notes control focused")
                    action = node.get_action_iface()
                    for index in range(action.get_n_actions()):
                        if action.get_action_name(index).lower() in {"click", "press", "activate"}:
                            require(action.do_action(index), "Notes native action refused")
                            return
                    raise RuntimeError(f"No native action for {node.get_name()!r}")

                pid, identity, window = owned_window(1)
                app = accessible(pid)
                request = {"schema_version": 1, "action": "replace_note", "target": old_target,
                           "destination_id": offer["destination_id"], "operation_id": "isolated-reopen-source-effect",
                           "expected_revision": 0, "text": "original isolated transport fixture"}
                raw = bootstrap.encode(request)
                effect.sendall(struct.pack(">I", len(raw)) + raw)
                # Check the checkpoint, without using a forged production grant.
                wait_for(lambda: saved(old_target, request["text"]), "original isolated pending effect persisted")
                field = focus(pid, identity, window, app)
                sample = "普通用户重新打开：中文 e\u0301 👨‍👩‍👧‍👦\n第二行"
                clipboard.set_text(sample, -1)
                key(pid, identity, window, "ctrl+a")
                key(pid, identity, window, "ctrl+v")
                old = wait_for(lambda: saved(old_target, sample), "real native CJK paste persisted")
                require(old["revision"] == 2 and old["pending_receipt"] is not None, "original revision/pending receipt")
                require(Atspi.Text.get_text(field, 0, -1) == sample, "actual editor differs from persisted text")
                old_bytes = checkpoint(old_target).read_bytes()
                screenshot("01-original-note.png")
                record("real-egui-native-CJK-paste-saved-with-original-pending-receipt")
                require(bootstrap.child_identity(pid) == identity, "Notes identity changed before closing")
                close_window(owner, window, pid)
                wait_for(lambda: next(t for t in snapshot()["tasks"] if t["id"] == 1)["state"]
                         in {"completed", "failed", "cancelled"}, "original Notes window reaped by Session")
                require(bootstrap.child_identity(pid) != identity, "old Notes process still owns its lock")
                record("ordinary-WM-DELETE-WINDOW-and-original-Session-reap")

                launched = bootstrap.roundtrip(socket_path, {"type": "launch", "workspace": "build", "app": "notes",
                                              "expected_instance": old_target["session_instance"]})
                require(launched["type"] == "task", "normal Notes launch failed")
                task_id = launched["task"]["id"]
                pid, identity, window = owned_window(task_id)
                app = accessible(pid)
                current = next(t for t in snapshot()["tasks"] if t["id"] == task_id)
                require(not current["notes_destination"]["original_owner_registered"], "ordinary launch inherited registration")
                # The app's original checkpoint is the independent target source.
                new_path = wait_for(lambda: next((p for p in state.glob("*/document.json")
                                                 if json.loads(p.read_bytes())["target"]["task_id"] == task_id), None),
                                    "new Notes checkpoint")
                new_target = json.loads(new_path.read_bytes())["target"]
                require(new_target != old_target and new_target["incarnation"] != old_target["incarnation"], "target identity reused")
                click(pid, identity, window, wait_for(lambda: named(app, "重新打开已保存的笔记"), "saved Notes section"))
                click(pid, identity, window, wait_for(lambda: named(app, "刷新已保存的笔记"), "refresh saved Notes control"))
                button = wait_for(lambda: named(app, "打开：普通用户重新打开：", prefix=True), "actual saved Notes entry")
                click(pid, identity, window, button)
                new = wait_for(lambda: saved(new_target, sample), "ordinary native reopen persisted under new target")
                require(new["revision"] == 1 and new["pending_receipt"] is None
                        and new["retired_receipt"] is None, "predecessor revision or receipts imported")
                require(checkpoint(old_target).read_bytes() == old_bytes, "opening changed original checkpoint")
                screenshot("02-reopened-note.png")
                record("ordinary-saved-note-UI-reopens-only-text-under-fresh-effect-identity")
                field = focus(pid, identity, window, app)
                clipboard.set_text("\n继续编辑", -1)
                key(pid, identity, window, "ctrl+End")
                key(pid, identity, window, "ctrl+v")
                edited = wait_for(lambda: saved(new_target, sample + "\n继续编辑"), "continued native editing persisted")
                require(edited["revision"] == 2 and edited["pending_receipt"] is None, "continued edit revision")
                require(Atspi.Text.get_text(field, 0, -1) == edited["text"], "continued editor readback differs")
                require(checkpoint(old_target).read_bytes() == old_bytes, "continued editing changed original checkpoint")
                record("continued-native-editing-shares-new-local-revision-CAS")
                query = {"schema_version": 1, "action": "observe", "target": old_target,
                         "operation_id": request["operation_id"], "payload_sha256": hashlib.sha256(raw).hexdigest()}
                with crash.recovery_process(args.binary_dir / "trill-notes-recovery", state, old_target) as (channel, _proc):
                    observed, _ = crash.exchange(channel, query)
                require(observed == old["pending_receipt"], "old exact pending receipt was lost or replayed")
                record("independent-original-incarnation-recovery-retains-exact-pending-receipt")
                result.update(old_target=old_target, new_target=new_target, original_checkpoint_sha256=hashlib.sha256(old_bytes).hexdigest(),
                              new_checkpoint_sha256=digest(new_path), new_revision=edited["revision"])
                clipboard.clear()
                screenshot("03-continued-note.png")
        except Exception:
            try:
                screenshot("failure-window.png")
                if "app" in locals():
                    tree = [{"name": node.get_name(), "role": node.get_role_name(),
                             "enabled": node.get_state_set().contains(Atspi.StateType.ENABLED),
                             "focused": node.get_state_set().contains(Atspi.StateType.FOCUSED)}
                            for node in walk(app)]
                    (args.output / "failure-atspi-tree.json").write_text(json.dumps(tree, ensure_ascii=False, indent=2) + "\n")
            except Exception as error:
                result["diagnostic_error"] = str(error)
            raise
        finally:
            log = socket_path.parents[2] / "session.log"
            if log.is_file():
                shutil.copyfile(log, args.output / "session.log")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binary-dir", type=Path, required=True)
    parser.add_argument("--hepta-root", type=Path, required=True)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--private-bus-child", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    for name in ("binary_dir", "hepta_root", "font", "output"):
        setattr(args, name, getattr(args, name).resolve())
    if not args.private_bus_child:
        require(args.font.is_file(), "explicit real CJK font required")
        args.output.mkdir(mode=0o700, parents=False, exist_ok=False)
        pinned = args.output / "bin"
        pinned.mkdir(mode=0o700)
        for name in ("trill-session", "trill-app-window", "trill-notes-recovery"):
            source = args.binary_dir / name
            require(os.access(source, os.X_OK), f"missing built {name}")
            shutil.copy2(source, pinned / name)
            require(digest(source) == digest(pinned / name), "binary changed during private snapshot")
        env = {key: value for key, value in os.environ.items()
               if not key.startswith(("TRILL_", "DBUS_")) and key not in {
                   "DISPLAY", "WAYLAND_DISPLAY", "NO_AT_BRIDGE", "AT_SPI_BUS_ADDRESS",
                   "IBUS_ADDRESS", "SESSION_MANAGER", "XAUTHORITY"}}
        for variable, folder in (("XDG_RUNTIME_DIR", "runtime"), ("XDG_CONFIG_HOME", "config"), ("XDG_DATA_HOME", "data"), ("XDG_STATE_HOME", "state")):
            path = args.output / folder
            path.mkdir(mode=0o700)
            env[variable] = str(path)
        env.update(TRILL_UI_CJK_FONT=str(args.font), TRILL_NOTES_PROBE_ISOLATED="1", WINIT_UNIX_BACKEND="x11", LIBGL_ALWAYS_SOFTWARE="1")
        process = subprocess.Popen(["dbus-run-session", "--", sys.executable, str(Path(__file__).resolve()),
                                    "--binary-dir", str(pinned), "--hepta-root", str(args.hepta_root), "--font", str(args.font),
                                    "--output", str(args.output), "--private-bus-child"], env=env, start_new_session=True)
        try:
            return process.wait(timeout=180)
        finally:
            if process.poll() is None:
                # Only the fresh process group created above belongs to this
                # fixture. Never enumerate or signal another desktop/job.
                require(os.getpgid(process.pid) == process.pid, "private fixture group identity changed")
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=6)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=4)
    def interrupted(_signal, _frame):
        raise RuntimeError("owned Notes qualification interrupted")
    signal.signal(signal.SIGTERM, interrupted)
    signal.signal(signal.SIGINT, interrupted)
    result = {"schema": "trillionnium.notes-ordinary-reopen-window.v1", "passed": False, "checks": [],
              "scope": "owned Xvfb, original Session/egui Notes, AT-SPI, real OS clipboard and synthesized keyboard",
              "physical_ime_qualified": False, "production_authority": False, "original_writer_terminal": False,
              "font": {"path": str(args.font), "sha256": digest(args.font)},
              "harness_sha256": digest(Path(__file__).resolve()),
              "binary_sha256": {name: digest(args.binary_dir / name) for name in ("trill-session", "trill-app-window", "trill-notes-recovery")}}
    try:
        with isolated_display(args.output):
            run(args, result)
        result["passed"] = True
        return 0
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
        return 1
    finally:
        (args.output / "receipt.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    sys.exit(main())
