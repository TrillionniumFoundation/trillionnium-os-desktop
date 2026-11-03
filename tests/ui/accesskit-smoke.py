#!/usr/bin/env python3
"""Exercise the shipping native accessibility adapter on a private test bus.

Must be launched by accesskit-smoke.sh, not against the user's desktop.
This does not claim a physical display, screen-reader, or OS IME acceptance.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

import gi

gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, GLib


def descendants(node, depth=0):
    if depth > 16:
        return
    yield node
    for i in range(node.get_child_count()):
        child = node.get_child_at_index(i)
        if child is not None:
            yield from descendants(child, depth + 1)


def until(probe, message, timeout=15):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        context = GLib.MainContext.default()
        while context.pending():
            context.iteration(False)
        value = probe()
        if value:
            return value
        time.sleep(0.05)
    raise AssertionError(message)


def stop(child):
    if child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=5)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app-window", type=Path, required=True)
    args = parser.parse_args()
    # The wrapper creates both surfaces. Never use an inherited Wayland socket.
    env = os.environ.copy()
    env.pop("WAYLAND_DISPLAY", None)
    env.pop("NO_AT_BRIDGE", None)
    env["WINIT_UNIX_BACKEND"] = "x11"
    env["LIBGL_ALWAYS_SOFTWARE"] = "1"
    assert env.get("DBUS_SESSION_BUS_ADDRESS") and env.get("DISPLAY")
    with tempfile.TemporaryDirectory(prefix="trill-atspi-") as runtime:
        env["XDG_RUNTIME_DIR"] = runtime
        with open(Path(runtime) / "bus.log", "w+") as bus_log, open(Path(runtime) / "app.log", "w+") as app_log:
            bus = subprocess.Popen(["/usr/libexec/at-spi-bus-launcher", "--launch-immediately", "--a11y=1", "--screen-reader=1"], env=env, stdout=bus_log, stderr=subprocess.STDOUT)
            app = None
            try:
                # Set only this disposable session's accessibility status.
                # Auto-activation may race the explicit launcher; setting the
                # properties makes readiness independent of that race.
                for property_name in ["IsEnabled", "ScreenReaderEnabled"]:
                    subprocess.run(["gdbus", "call", "--session", "--dest", "org.a11y.Bus", "--object-path", "/org/a11y/bus", "--method", "org.freedesktop.DBus.Properties.Set", "org.a11y.Status", property_name, "<true>"], env=env, check=True, timeout=5, stdout=bus_log, stderr=subprocess.STDOUT)
                Atspi.init()
                desktop = Atspi.get_desktop(0)
                app = subprocess.Popen([str(args.app_window), "--kind", "calculator", "--workspace", "personal", "--task-id", "1"], env=env, stdout=app_log, stderr=subprocess.STDOUT)
                def nodes():
                    assert app.poll() is None, "native app exited during accessibility test"
                    return list(descendants(desktop))
                def named(name):
                    return next((node for node in nodes() if node.get_name() == name), None)
                add = until(lambda: named("+"), "AT-SPI never exposed the native Calculator button")
                assert add.get_role() == Atspi.Role.PUSH_BUTTON
                # Labelled native editors are discoverable. AccessKit 0.17's
                # AT-SPI adapter exposes text/focus, not EditableText SetText;
                # do not claim an unsupported semantic insertion interface.
                for label in ["A", "B"]:
                    edit = until(lambda: next((node for node in nodes() if node.get_name() == label and node.get_role() == Atspi.Role.ENTRY), None), f"missing named editor {label}")
                    assert edit.get_component_iface() is not None
                # Xvfb has no window manager. Give only this test-owned
                # process input focus so the production focus guard remains
                # in force; this does not synthesize a click or key.
                windows = subprocess.check_output(["xdotool", "search", "--onlyvisible", "--pid", str(app.pid)], env=env, timeout=5, text=True).splitlines()
                assert len(windows) == 1, "expected one isolated Calculator window"
                subprocess.run(["xdotool", "windowfocus", "--sync", windows[0]], env=env, check=True, timeout=5)
                assert add.get_component_iface().grab_focus()
                until(lambda: add.get_state_set().contains(Atspi.StateType.FOCUSED), "semantic focus not observed")
                action = add.get_action_iface()
                assert action is not None and action.get_n_actions() > 0
                assert action.do_action(0), "native semantic activation refused"
                until(lambda: named("Invalid number (input remains unchanged)"), "semantic action did not reach Calculator validation")
                print(json.dumps({"status": "passed", "transport": "AT-SPI on private D-Bus/Xvfb", "assertions": ["native button role and label", "labelled editable A/B fields", "semantic click", "observed validation result for empty input"], "physical_screen_reader": "not exercised", "physical_ime": "not exercised"}, indent=2))
            except BaseException:
                for label, log in [("bus", bus_log), ("app", app_log)]:
                    log.seek(0)
                    print(f"{label} log:\n{log.read()}")
                raise
            finally:
                if app is not None:
                    stop(app)
                stop(bus)
                Atspi.exit()


if __name__ == "__main__":
    main()
