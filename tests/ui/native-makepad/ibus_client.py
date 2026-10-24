#!/usr/bin/env python3
"""Real IBus/XIM pinyin through the owned Makepad window, never injected IME events."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import time

import gi

from capture import Display

gi.require_version("GLib", "2.0")
gi.require_version("Atspi", "2.0")
from gi.repository import Atspi, GLib


def pump():
    context = GLib.MainContext.default()
    for _ in range(128):
        if not context.pending():
            break
        context.iteration(False)


def until(probe, description, timeout=15):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        pump()
        try:
            result = probe()
            if result:
                return result
        except Exception as error:
            last = error
        time.sleep(0.04)
    raise AssertionError(f"{description}; last error: {last}")


def settle(seconds):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        pump()
        time.sleep(0.01)


def walk(root):
    pending = [root]
    for _ in range(4096):
        if not pending:
            return
        node = pending.pop()
        yield node
        for index in reversed(range(node.get_child_count())):
            child = node.get_child_at_index(index)
            if child is not None:
                pending.append(child)
    raise AssertionError("Accessibility tree is unbounded")


def local_text(path):
    snapshot = json.loads(path.read_bytes())
    assert snapshot["version"] == 4 and snapshot["active_workspace"] == "personal"
    entry = next(entry for entry in snapshot["workspaces"] if entry["workspace"] == "personal")
    archive = entry["local_archive"]
    assert archive["version"] == 1
    partition = next(part for part in archive["partitions"] if part["principal"] is None)
    return partition["rooms"][partition["active"]]


def run(args, report):
    xid = int(args.window_id, 0)
    spec = importlib.util.spec_from_file_location("original_xres_owner", args.x11_owner_helper.resolve(strict=True))
    owner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(owner)
    report["x11_owner"] = owner.require_window_pid(xid, args.pid)
    Atspi.init()
    desktop = Atspi.get_desktop(0)
    app = until(lambda: next((desktop.get_child_at_index(i) for i in range(desktop.get_child_count())
                if desktop.get_child_at_index(i).get_process_id() == args.pid), None), "Exact original app did not register")

    def named(name):
        return next((node for node in walk(app) if node.get_name() == name), None)

    def editor():
        return until(lambda: named("Message / 消息"), "Original composer is missing")

    def value():
        return Atspi.Text.get_text(editor(), 0, -1)

    def selected_room():
        # AT-SPI translations differ between versions; state and original role
        # constants avoid depending on the English role-name spelling.
        return next((node for node in walk(app)
                     if node.get_role() == Atspi.Role.LIST_ITEM
                     and node.get_state_set().contains(Atspi.StateType.SELECTED)), None)

    def record(name, **details):
        report["checks"].append({"name": name, "passed": True, **details})

    def key(name):
        owner.require_window_pid(xid, args.pid)
        assert int(subprocess.check_output(["xdotool", "getwindowfocus"], text=True)) == xid
        subprocess.run(["xdotool", "key", "--clearmodifiers", name], check=True, timeout=5)
        report["input"].append({"kind": "XTEST_key", "key": name})

    display = Display()
    try:
        subprocess.run(["xdotool", "windowfocus", "--sync", args.window_id], check=True, timeout=5)
        assert editor().get_component_iface().grab_focus()
        until(lambda: editor().get_state_set().contains(Atspi.StateType.FOCUSED), "Original editor focus was not observed")
        assert value() == "", "A fresh empty local room is required for the IME oracle"
        checkpoint = args.state / "trillionnium-ui" / "workspace-checkpoint-v4.json"
        until(lambda: checkpoint.is_file() and local_text(checkpoint) == "", "Original empty draft checkpoint is not durable")
        before = checkpoint.read_bytes()
        row = until(selected_room, "The selected original room is not exposed")
        initial_title = row.get_name()
        new_draft = until(lambda: named("+ New draft"), "Original draft action missing")
        assert new_draft.get_state_set().contains(Atspi.StateType.ENABLED)
        original_editable = editor().get_editable_text_iface() if args.atomic_editable_text else None
        if args.atomic_editable_text:
            assert original_editable is not None, "Atomic EditableText was requested but is unavailable"
        action = new_draft.get_action_iface()
        action_names = [action.get_action_name(i) for i in range(action.get_n_actions())]
        index = next(i for i, name in enumerate(action_names) if name.lower() in ("click", "press", "activate"))
        subprocess.run(["ibus", "engine", args.engine], check=True, timeout=8)
        observed_engine = subprocess.check_output(["ibus", "engine"], text=True, timeout=8).strip()
        assert observed_engine == args.engine
        report["engine"] = observed_engine
        settle(0.4)
        owner.require_window_pid(xid, args.pid)
        assert int(subprocess.check_output(["xdotool", "getwindowfocus"], text=True)) == xid
        # This is the only text input in the IME sample. Expected Chinese below
        # is never passed to an input API or clipboard.
        subprocess.run(["xdotool", "type", "--clearmodifiers", "--delay", "150", "--", "nihao"], check=True, timeout=8)
        report["input"].append({"kind": "XTEST_ASCII", "text": "nihao"})
        until(lambda: not named("+ New draft").get_state_set().contains(Atspi.StateType.ENABLED),
              "Real IBus preedit did not engage the original composition guard")
        settle(0.15)
        preedit_text = value()
        try:
            action.do_action(index)
        except Exception:
            pass  # Disabled/refused semantic action is the required outcome.
        if original_editable is not None:
            try:
                original_editable.set_text_contents("external request during preedit")
            except Exception:
                pass  # Interface removal or UI-thread composition guard refuses.
            report["input"].append({"kind": "AT-SPI-negative-edit-during-preedit", "text": "external request during preedit"})
        # Longer than the production 500ms recovery cadence: no candidate text
        # may be published. Original row titles derive from committed drafts.
        settle(0.9)
        assert value() == preedit_text, "An external request changed the real preedit buffer"
        assert selected_room().get_name() == initial_title
        assert checkpoint.read_bytes() == before
        assert local_text(checkpoint) == ""
        report["screenshots"].append(display.screenshot(args.output / "ime-preedit-window.png", xid))
        report["screenshots"].append(display.screenshot(args.output / "ime-preedit-display.png"))
        record("real-IBus-preedit-fences-navigation-and-local-checkpoint",
               observed_editor_text=preedit_text, unchanged_committed_room_title=initial_title,
               checkpoint_sha256=hashlib.sha256(before).hexdigest())
        if original_editable is not None:
            record("real-IBus-preedit-refuses-stale-EditableText-mutation")

        key("space")
        until(lambda: value() == "你好", "Original SDK did not commit Chinese from real IBus")
        until(lambda: local_text(checkpoint) == "你好", "Committed Chinese did not reach original local recovery")
        until(lambda: named("+ New draft").get_state_set().contains(Atspi.StateType.ENABLED), "Composition guard remained latched after confirmation")
        assert selected_room().get_name() == "你好"
        record("real-IBus-space-commits-exact-Chinese-to-original-draft")
        report["screenshots"].append(display.screenshot(args.output / "ime-committed-window.png", xid))
        key("ctrl+z")
        until(lambda: value() == "", "Original SDK could not undo the IME commit")
        key("ctrl+shift+z")
        until(lambda: value() == "你好", "Original SDK could not redo the IME commit")
        record("real-IME-commit-original-undo-redo")

        own_focus_window = display.focus_window()
        subprocess.run(["xdotool", "windowfocus", "--sync", str(own_focus_window)], check=True, timeout=5)
        until(lambda: not editor().get_state_set().contains(Atspi.StateType.FOCUSED), "Focus loss did not reach original window")
        assert value() == "你好", "Unfocused visible window lost its accessible text"
        subprocess.run(["xdotool", "windowfocus", "--sync", args.window_id], check=True, timeout=5)
        assert editor().get_component_iface().grab_focus()
        until(lambda: editor().get_state_set().contains(Atspi.StateType.FOCUSED), "Focus did not return to original editor")
        assert value() == "你好"
        record("owned-window-focus-loss-and-return-preserve-Chinese")
        until(lambda: local_text(checkpoint) == "你好", "Final committed draft is not durable")
        assert checkpoint.stat().st_mode & 0o777 == 0o600
        (args.output / "recovery-after-ime.json").write_bytes(checkpoint.read_bytes())
        report["screenshots"].append(display.screenshot(args.output / "ime-final-window.png", xid))
        report["screenshots"].append(display.screenshot(args.output / "ime-final-display.png"))
    except BaseException:
        # Preserve the actual private editor/engine/pixels at the failed cut.
        # Diagnostics never satisfy an assertion or change the input deadline.
        observed = {}
        for name, probe in (
            ("editor_text", lambda: Atspi.Text.get_text(named("Message / 消息"), 0, -1)),
            ("selected_room", lambda: selected_room().get_name()),
            ("new_draft_enabled", lambda: named("+ New draft").get_state_set().contains(Atspi.StateType.ENABLED)),
            ("engine", lambda: subprocess.check_output(["ibus", "engine"], text=True, timeout=5).strip()),
            ("focus_window", lambda: subprocess.check_output(["xdotool", "getwindowfocus"], text=True, timeout=5).strip()),
        ):
            try:
                observed[name] = probe()
            except Exception as error:
                observed[name + "_error"] = str(error)
        report["failure_observation"] = observed
        for name, window in (("ime-failure-window.png", xid), ("ime-failure-display.png", None)):
            try:
                report["screenshots"].append(display.screenshot(args.output / name, window))
            except Exception as error:
                report.setdefault("diagnostic_errors", []).append(str(error))
        raise
    finally:
        display.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pid", type=int, required=True)
    parser.add_argument("--window-id", required=True)
    parser.add_argument("--x11-owner-helper", type=Path, required=True)
    parser.add_argument("--engine", default="libpinyin")
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--atomic-editable-text", action="store_true")
    args = parser.parse_args()
    result = {"schema": "trill.native-real-ibus.v1", "passed": False, "pid": args.pid,
              "checks": [], "input": [], "screenshots": [], "physical_keyboard_qualified": False,
              "unicode_injection_used_for_ime": False, "synthetic_ime_events_used": False,
              "wayland_ime_qualified": False, "orca_human_evaluation": False,
              "oracle": "original AT-SPI editor and selected room title plus original v4 recovery file"}
    try:
        run(args, result)
        result["passed"] = True
    except BaseException as error:
        result["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        (args.output / "ibus-receipt.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
