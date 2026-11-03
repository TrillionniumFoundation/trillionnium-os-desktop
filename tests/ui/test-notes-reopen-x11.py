#!/usr/bin/env python3
"""Owned Xvfb/D-Bus Notes reopen UI probe; no live desktop or Hepta effects.

The outer invocation creates the private surfaces. Run only after the isolated
Notes binaries finish building. UI actions edit synthetic local application text.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, type=Path)
    parser.add_argument("--bin-dir", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--owned-private-surfaces", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    repo, binaries, output = args.repo.resolve(strict=True), args.bin_dir.resolve(strict=True), args.output.absolute()
    if not args.owned_private_surfaces:
        output.mkdir(mode=0o700, parents=False, exist_ok=False)
        env = {key: value for key, value in os.environ.items()
               if key not in {"DISPLAY", "WAYLAND_DISPLAY", "DBUS_SESSION_BUS_ADDRESS", "AT_SPI_BUS_ADDRESS",
                              "IBUS_ADDRESS", "NO_AT_BRIDGE"}
               and not key.startswith(("TRILL_HEPTA_", "TRILL_UI_CHAT_"))}
        env.update(WINIT_UNIX_BACKEND="x11", LIBGL_ALWAYS_SOFTWARE="1", TRILL_NOTES_PROBE_ISOLATED="1")
        command = ["dbus-run-session", "--", "xvfb-run", "-a", "-s", "-screen 0 1280x800x24 -nolisten tcp",
                   "/usr/bin/python3", str(Path(__file__).resolve()), "--owned-private-surfaces",
                   "--repo", str(repo), "--bin-dir", str(binaries), "--output", str(output)]
        with (output / "owned-surfaces.log").open("w") as log:
            result = subprocess.run(command, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=150)
        print((output / "owned-surfaces.log").read_text(errors="replace"), flush=True)
        return result.returncode

    assert os.environ.get("TRILL_NOTES_PROBE_ISOLATED") == "1"
    assert os.environ.get("DISPLAY") and os.environ.get("DBUS_SESSION_BUS_ADDRESS")
    import gi
    gi.require_version("Atspi", "2.0")
    from gi.repository import Atspi, GLib
    helper = module("notes_private_helpers", repo / "tests/ui/test-notes-bootstrap-ipc.py")
    capture = module("notes_capture", repo / "tests/ui/native-makepad/capture.py")
    app_binary = binaries / "trill-app-window"
    session_binary = binaries / "trill-session"
    assert all(path.is_file() and os.access(path, os.X_OK) for path in (app_binary, session_binary))
    result = {"schema": "trill.notes-reopen-ui.v1", "passed": False,
              "production_authority": False, "effect_requests": 0,
              "surface": "owned Xvfb and private D-Bus", "captures": [],
              "binary_sha256": {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in (app_binary, session_binary)}}
    result["checkout_at_execution"] = {
        "head": subprocess.check_output(["git", "-C", str(repo), "rev-parse", "HEAD"], text=True).strip(),
        "tracked_diff_sha256": hashlib.sha256(subprocess.check_output(["git", "-C", str(repo), "diff", "--binary"])).hexdigest(),
    }

    def until(probe, message, timeout=15):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            context = GLib.MainContext.default()
            while context.pending():
                context.iteration(False)
            try:
                value = probe()
                if value:
                    return value
            except (FileNotFoundError, ConnectionRefusedError, json.JSONDecodeError, GLib.Error):
                pass
            time.sleep(0.04)
        raise RuntimeError(message)

    def walk(node, depth=0):
        if depth > 18:
            return
        try:
            if node.get_state_set().contains(Atspi.StateType.DEFUNCT):
                return
            yield node
            for index in range(node.get_child_count()):
                child = node.get_child_at_index(index)
                if child is not None:
                    yield from walk(child, depth + 1)
        except GLib.Error:
            return

    def named_button(label):
        return next((node for node in walk(Atspi.get_desktop(0))
                     if node.get_name() == label and node.get_role() == Atspi.Role.PUSH_BUTTON), None)

    def editor():
        return next((node for node in walk(Atspi.get_desktop(0))
                     if node.get_name() == "Notes / 笔记 · try composing Chinese with your host IME"
                     and node.get_state_set().contains(Atspi.StateType.EDITABLE)), None)

    def click(label):
        button = until(lambda: named_button(label), "missing native button: " + label)
        assert button.get_component_iface().grab_focus(), "button focus refused: " + label
        until(lambda: button.get_state_set().contains(Atspi.StateType.FOCUSED), "button focus not observed")
        action = button.get_action_iface()
        assert action is not None and action.get_n_actions() > 0 and action.do_action(0), "native click refused"

    def xdo(*arguments):
        return subprocess.check_output(["xdotool", *arguments], text=True, timeout=6).strip()

    with tempfile.TemporaryDirectory(prefix="trill-notes-reopen-ui-") as folder:
        runtime = Path(folder) / "runtime"
        runtime.mkdir(mode=0o700)
        state = Path(folder) / "notes"
        state.mkdir(mode=0o700)
        env = dict(os.environ, XDG_RUNTIME_DIR=str(runtime), TRILL_NOTES_STATE_DIR=str(state))
        socket_path = runtime / "trillionnium-ui/session.sock"
        session, bus, display = None, None, None
        with (output / "session.log").open("w") as session_log, (output / "a11y-bus.log").open("w") as bus_log:
            try:
                bus = subprocess.Popen(["/usr/libexec/at-spi-bus-launcher", "--launch-immediately", "--a11y=1", "--screen-reader=1"],
                                       env=env, stdout=bus_log, stderr=subprocess.STDOUT)
                for name in ("IsEnabled", "ScreenReaderEnabled"):
                    subprocess.run(["gdbus", "call", "--session", "--dest", "org.a11y.Bus", "--object-path", "/org/a11y/bus",
                        "--method", "org.freedesktop.DBus.Properties.Set", "org.a11y.Status", name, "<true>"],
                        env=env, check=True, timeout=6, stdout=bus_log, stderr=subprocess.STDOUT)
                Atspi.init()
                display = capture.Display()
                session = subprocess.Popen([str(session_binary)], env=env, stdin=subprocess.DEVNULL,
                                           stdout=session_log, stderr=subprocess.STDOUT)
                snapshot = until(lambda: helper.roundtrip(socket_path, {"type": "snapshot"}), "Session did not start")
                instance = snapshot["session_instance"]

                def launch():
                    reply = helper.roundtrip(socket_path, {"type": "launch", "workspace": "personal", "app": "notes",
                                                          "expected_instance": instance})
                    assert reply["type"] == "task"
                    identity = reply["task"]["id"]
                    def ready():
                        task = next(item for item in helper.roundtrip(socket_path, {"type": "snapshot"})["tasks"] if item["id"] == identity)
                        assert task["state"] == "running", task
                        return task if task["ui_first_frame_unix_ms"] is not None else None
                    task = until(ready, "Notes first layout missing")
                    assert task["notes_destination"]["original_owner_registered"] is False
                    pid = task["pid"]
                    observed = helper.child_identity(pid)
                    assert observed and observed[0] == session.pid and observed[2] == str(app_binary)
                    def visible_windows():
                        try:
                            return xdo("search", "--onlyvisible", "--pid", str(pid)).splitlines()
                        except subprocess.CalledProcessError as error:
                            if error.returncode == 1:
                                return None
                            raise
                    windows = until(visible_windows, "owned window missing")
                    assert len(windows) == 1
                    window = windows[0]
                    xdo("windowfocus", "--sync", window)
                    path = state / (instance + "-" + str(identity) + "-" + task["notes_destination"]["incarnation"]) / "document.json"
                    return task, window, path, observed

                def saved(path, expected):
                    def read():
                        value = json.loads(path.read_bytes())
                        return value if value["text"] == expected else None
                    return until(read, "user text was not persisted by the real Notes worker")

                first, first_window, old_path, first_process = launch()
                text = until(editor, "native editable Notes field missing")
                assert text.get_component_iface().grab_focus()
                xdo("type", "--clearmodifiers", "--delay", "3", "Saved ")
                saved(old_path, "Saved ")
                xdo("type", "--clearmodifiers", "--delay", "3", "Notes reopen audit")
                expected = "Saved Notes reopen audit"
                old = saved(old_path, expected)
                assert old["revision"] >= 2 and old["pending_receipt"] is None
                result["captures"].append(display.screenshot(output / "01-original.png", int(first_window)))
                old_bytes = old_path.read_bytes()
                assert helper.child_identity(first["pid"]) == first_process
                xdo("windowclose", first_window)
                until(lambda: helper.child_identity(first["pid"]) != first_process, "normal window close did not exit owned app")
                (output / "original-checkpoint.json").write_bytes(old_bytes)

                second, second_window, new_path, _second_process = launch()
                assert json.loads(new_path.read_bytes())["text"] == ""
                click("打开已保存笔记")
                until(lambda: named_button("打开副本"), "saved document not offered")
                result["captures"].append(display.screenshot(output / "02-picker.png", int(second_window)))
                click("打开副本")
                new = saved(new_path, expected)
                assert new["target"] != old["target"] and new["revision"] == 1
                assert new["pending_receipt"] is None and new["retired_receipt"] is None
                text = until(editor, "restored native editor missing")
                until(lambda: Atspi.Text.get_text(text, 0, -1) == expected, "restored text absent from native accessibility view")
                assert old_path.read_bytes() == old_bytes
                result["captures"].append(display.screenshot(output / "03-restored.png", int(second_window)))
                (output / "restored-checkpoint.json").write_bytes(new_path.read_bytes())
                assert text.get_component_iface().grab_focus()
                xdo("key", "--clearmodifiers", "ctrl+End")
                xdo("type", "--clearmodifiers", "--delay", "3", " continued")
                changed = saved(new_path, expected + " continued")
                assert changed["revision"] > 1 and old_path.read_bytes() == old_bytes
                result.update(passed=True, ordinary_window_close=True, explicit_picker_action=True,
                              source_checkpoint_unchanged=True, fresh_target=True, source_revision=old["revision"],
                              restored_revision=1, new_local_edit_revision=changed["revision"],
                              old_receipts_transferred=False, native_accessibility_readback=True,
                              physical_display=False, real_ime=False, human_pixel_review_required=True)
            except BaseException as error:
                result["error"] = repr(error)
                raise
            finally:
                (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
                if session is not None:
                    for pid, identity in helper.owned_children(session, app_binary).items():
                        try:
                            descriptor = os.pidfd_open(pid)
                        except ProcessLookupError:
                            continue
                        try:
                            if helper.child_identity(pid) == identity:
                                signal.pidfd_send_signal(descriptor, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                        finally:
                            os.close(descriptor)
                    session.terminate()
                    try:
                        session.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        session.kill()
                        session.wait(timeout=5)
                if display is not None:
                    display.close()
                if bus is not None:
                    bus.terminate()
                    try:
                        bus.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        bus.kill()
                        bus.wait(timeout=5)
                Atspi.exit()
    print(json.dumps(result, ensure_ascii=False, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
