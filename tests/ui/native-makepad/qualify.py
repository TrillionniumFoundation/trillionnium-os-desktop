#!/usr/bin/env python3
"""Run existing Makepad/AT-SPI and real IBus tests on entirely owned UI surfaces.

No build, installation, --replace, user-bus connection or owner daemon launch is
performed. This is a virtual X11 keyboard test, not a physical-device verdict.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time

from inventory import inventory

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def verify_build_binary(build, shell, *, packaged=False):
    """Bind the chosen actual ELF to its explicit build or package artifact."""
    kind = "packaged_binaries" if packaged else "binaries"
    entry = build.get(kind, {}).get("trill-shell", {})
    if (build.get("status") != "passed" or build.get("exit_code") != 0
            or entry.get("sha256") != digest(shell)
            or entry.get("bytes") != shell.stat().st_size):
        raise RuntimeError("Actual ELF does not match the successful " + kind + " receipt")
    return kind


def until(probe, description, timeout=15):
    deadline = time.monotonic() + timeout
    error = None
    while time.monotonic() < deadline:
        try:
            result = probe()
            if result:
                return result
        except Exception as caught:
            error = caught
        time.sleep(0.08)
    raise RuntimeError(f"{description}; last error: {error}")


def run(args):
    output = args.output
    if not output.is_absolute() or output.exists() or output.is_symlink() or not output.parent.is_dir():
        raise RuntimeError("--output must be a new absolute directory with an existing parent")
    output.mkdir(mode=0o700)
    report = {"schema": "trill.native-makepad-qualification.v1", "passed": False,
              "started_unix_ms": time.time_ns() // 1_000_000, "children": [], "commands": [],
              "physical_keyboard_qualified": False, "wayland_ime_qualified": False,
              "editable_text_interface_qualified": False, "orca_human_evaluation": False,
              "candidate_position_visually_qualified": False, "font_pixels_visually_qualified": False,
              "system_install_performed": False, "user_bus_accessed": False,
              "original_agentd_started": False, "authenticated_send_qualified": False}
    groups, logs = [], []
    temporary = None
    guard = None

    def save():
        (output / "receipt.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")

    try:
        available = inventory()
        (output / "inventory.json").write_text(json.dumps(available, ensure_ascii=False, indent=2) + "\n")
        required = ("Xvfb", "xauth", "xdotool", "xdpyinfo", "xprop", "setxkbmap",
                    "dbus-daemon", "gdbus", "ibus-daemon", "ibus", "glib-compile-schemas")
        missing = [name for name in required if not available["commands"].get(name)]
        missing += [name for name, path in available["helpers"].items() if path is None]
        missing += [name for name, found in available["python_modules"].items() if not found]
        missing += [name for name in ("Gtk", "Atspi") if not isinstance(available["gi_namespaces"].get(name), str)]
        if missing:
            raise RuntimeError("Missing installed prerequisites: " + ", ".join(missing))
        # Some installed components, including libpinyin, publish their engine
        # list dynamically. Empty static XML is not evidence of absence. The
        # exact engine must appear on our own fresh bus below before input.
        shell = args.shell.resolve(strict=True)
        resources = args.resources.resolve(strict=True)
        if args.request_scoped_paste:
            profile = json.loads((resources / "NATIVE-SDK-SOURCE.json").read_bytes())
            if profile.get("native_ui_feature") != "native-clipboard-sdk":
                raise RuntimeError("PasteText qualification requires the explicit clipboard SDK feature/source bundle")
        smoke = (args.hepta_source / "apps/hepta-control-ui/test/native-accessibility-smoke.py").resolve(strict=True)
        owner_helper = (args.hepta_source / "apps/hepta-control-ui/test/x11_client_owner.py").resolve(strict=True)
        editable = None
        if args.atomic_editable_text:
            editable = (args.hepta_source / "apps/hepta-control-ui/test/native-editable-text-smoke.py").resolve(strict=True)
        with shell.open("rb") as binary:
            if binary.read(4) != b"\x7fELF":
                raise RuntimeError("--shell must name the actual built ELF")
        provenance = {"shell": {"path": str(shell), "bytes": shell.stat().st_size, "sha256": digest(shell)},
                      "resource_inventory_sha256": digest(resources / "NATIVE-ASSETS.json"),
                      "original_atspi_script": {"path": str(smoke), "sha256": digest(smoke)},
                      "original_xres_helper": {"path": str(owner_helper), "sha256": digest(owner_helper)},
                      "harness_files": {path.name: digest(path) for path in HERE.glob("*.py")},
                      "build_source_identity_verified": False}
        if editable is not None:
            provenance["original_atomic_editable_text_script"] = {"path": str(editable), "sha256": digest(editable)}
        if args.build_receipt is not None:
            build = json.loads(args.build_receipt.read_bytes())
            provenance["build_artifact_kind"] = verify_build_binary(
                build, shell, packaged=args.packaged_binary)
            provenance["build_source_identity_verified"] = True
            provenance["build_receipt_sha256"] = digest(args.build_receipt)
            provenance["source_commit"] = build["source_commit"]
            provenance["source_tree"] = build["source_tree"]
            shutil.copyfile(args.build_receipt, output / "build-receipt.json")
        (output / "provenance.json").write_text(json.dumps(provenance, ensure_ascii=False, indent=2) + "\n")
        report["provenance"] = provenance
        guard_path = ROOT / "tests/integration/hepta/run_original_agentd.py"
        spec = importlib.util.spec_from_file_location("original_child_guard", guard_path)
        guard = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(guard)
        if not guard.child_anchor_available():
            raise RuntimeError("Original waitable-child identity anchor is required")
        report["child_guard_sha256"] = digest(guard_path)

        # Short private paths keep all Unix socket addresses below sun_path.
        # XDG is isolated without repurposing HOME or touching host settings.
        temporary = tempfile.TemporaryDirectory(prefix="trill-native-")
        private = Path(temporary.name)
        for name in ("runtime", "config", "cache", "state", "data", "schemas"):
            (private / name).mkdir(mode=0o700)
        display = None
        for _ in range(128):
            number = secrets.randbelow(1800) + 200
            if not Path(f"/tmp/.X{number}-lock").exists() and not Path(f"/tmp/.X11-unix/X{number}").exists():
                display = f":{number}"
                break
        if display is None:
            raise RuntimeError("No unused private display number found")
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8",
               "DISPLAY": display, "XAUTHORITY": str(private / "Xauthority"),
               "DBUS_SESSION_BUS_ADDRESS": f"unix:path={private}/runtime/session-bus",
               "XDG_RUNTIME_DIR": str(private / "runtime"), "XDG_CONFIG_HOME": str(private / "config"),
               "XDG_CACHE_HOME": str(private / "cache"), "XDG_STATE_HOME": str(private / "state"),
               "XDG_DATA_HOME": str(private / "data"), "XDG_CURRENT_DESKTOP": "TRILL_NATIVE_PRIVATE_TEST",
               "GSETTINGS_SCHEMA_DIR": str(private / "schemas"), "GSETTINGS_BACKEND": "memory",
               "XMODIFIERS": "@im=ibus", "GTK_IM_MODULE": "ibus", "QT_IM_MODULE": "ibus",
               "GDK_BACKEND": "x11", "IBUS_USE_PORTAL": "0", "WINIT_UNIX_BACKEND": "x11",
               "LIBGL_ALWAYS_SOFTWARE": "1", "LP_NUM_THREADS": "2", "MESA_SHADER_CACHE_DISABLE": "true",
               "TRILL_UI_MAKEPAD_RESOURCES": str(resources), "TRILL_UI_DRAFT_RECOVERY": "1",
               "PYTHONDONTWRITEBYTECODE": "1"}

        def command(label, argv, *, required=True, environment=None, timeout=8):
            result = subprocess.run(argv, env=environment or env, stdin=subprocess.DEVNULL,
                                    capture_output=True, timeout=timeout)
            number = len(report["commands"])
            if number >= 512:
                raise RuntimeError("Command log bound reached")
            (output / f"{number:03}-{label}.stdout.log").write_bytes(result.stdout)
            (output / f"{number:03}-{label}.stderr.log").write_bytes(result.stderr)
            report["commands"].append({"label": label, "argv": list(map(str, argv)), "exit_code": result.returncode})
            if required and result.returncode != 0:
                raise RuntimeError(f"{label} failed with exit {result.returncode}")
            return result

        def spawn(label, argv):
            stdout = (output / f"{label}.stdout.log").open("xb")
            stderr = (output / f"{label}.stderr.log").open("xb")
            logs.extend((stdout, stderr))
            process = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL, stdout=stdout,
                                       stderr=stderr, start_new_session=True)
            group = guard.ChildGroup(process)
            groups.append((label, group))
            report["children"].append({"label": label, "pid": process.pid, "argv": list(map(str, argv))})
            return group

        def alive(group):
            if group.observe_exit() is not None:
                raise RuntimeError(f"Owned process exited before readiness: {group.process.args}")
            return True

        def stage(label, argv, timeout):
            group = spawn(label, argv)
            group.wait_exit(timeout)
            code = guard.terminate_group(group)
            groups.remove((label, group))
            report.setdefault("stage_exits", []).append({"label": label, "exit_code": code})
            if code != 0:
                raise RuntimeError(f"{label} failed with exit {code}")

        for schema in Path("/usr/share/glib-2.0/schemas").iterdir():
            if schema.name.endswith((".xml", ".gschema.override")) and schema.is_file():
                shutil.copyfile(schema, private / "schemas" / schema.name)
        (private / "schemas/99-trill-native.gschema.override").write_text(
            "[org.freedesktop.ibus.general]\nuse-system-keyboard-layout=true\nuse-xmodmap=false\n")
        command("private-schemas", ["glib-compile-schemas", "--strict", str(private / "schemas")])
        auth = private / "Xauthority"
        auth.touch(mode=0o600)
        cookie = secrets.token_hex(16)
        # Keep the test cookie out of receipts and archived command arguments.
        result = subprocess.run(["xauth", "-f", str(auth), "add", display, ".", cookie],
                                env=env, stdin=subprocess.DEVNULL, capture_output=True, timeout=5)
        if result.returncode != 0:
            raise RuntimeError("Private Xauthority creation failed")
        xserver = spawn("xvfb", ["Xvfb", display, "-nolisten", "tcp", "-screen", "0", "1440x1000x24", "-auth", str(auth)])
        until(lambda: alive(xserver) and command("display-ready", ["xdpyinfo"], required=False).returncode == 0, "Owned Xvfb did not become ready")
        denied = command("display-without-cookie", ["xdpyinfo"], required=False,
                         environment=dict(env, XAUTHORITY=str(private / "missing-cookie")))
        if denied.returncode == 0:
            raise RuntimeError("Owned display accepted an unauthenticated client")
        report["display"] = display
        report["private_display_rejected_missing_cookie"] = True
        command("private-us-keymap", ["setxkbmap", "-layout", "us"])
        bus = spawn("session-bus", ["dbus-daemon", "--session", "--nofork", "--address=" + env["DBUS_SESSION_BUS_ADDRESS"], "--print-address=1"])
        until(lambda: alive(bus) and (private / "runtime/session-bus").is_socket(), "Private D-Bus did not become ready")
        a11y = spawn("accessibility-bus", [available["helpers"]["a11y_bus"], "--launch-immediately", "--a11y=1", "--screen-reader=1"])
        for name in ("IsEnabled", "ScreenReaderEnabled"):
            until(lambda: alive(a11y) and command("private-a11y-" + name, ["gdbus", "call", "--session", "--dest", "org.a11y.Bus",
                "--object-path", "/org/a11y/bus", "--method", "org.freedesktop.DBus.Properties.Set", "org.a11y.Status", name, "<true>"], required=False).returncode == 0,
                "Private accessibility status unavailable")
        ibus = spawn("ibus", ["ibus-daemon", "--xim", "--verbose", "--panel=" + available["helpers"]["ibus_panel"],
                               "--config=" + available["helpers"]["ibus_memconf"], "--cache=none"])
        def registered_engine():
            alive(ibus)
            listed = command("engines-ready", ["ibus", "list-engine", "--name-only"], required=False)
            names = listed.stdout.decode("utf-8").splitlines()
            if listed.returncode == 0 and args.engine in names:
                report["private_bus_registered_engines"] = names
                # The engine registry and the XIM child become ready
                # independently. Require both within this same existing
                # startup deadline before opening the native editor.
                selection = command("xim-selection-ready", ["xprop", "-root", "XIM_SERVERS"], required=False)
                if selection.returncode == 0 and b"@server=ibus" in selection.stdout:
                    report["private_xim_advertised"] = True
                    return True
            return False
        until(registered_engine, "Private IBus engine and XIM selection did not become ready")
        command("initial-english-engine", ["ibus", "engine", "xkb:us::eng"])
        observed = command("xim-selection", ["xprop", "-root", "XIM_SERVERS"])
        if b"@server=ibus" not in observed.stdout:
            raise RuntimeError("Real IBus XIM selection is not advertised on the private display")
        shell_group = spawn("original-makepad-shell", [str(shell), "--renderer", "makepad", "--workspace", "personal", "--page", "conversation"])

        def window():
            alive(shell_group)
            found = command("owned-window", [sys.executable, "-B", str(owner_helper),
                "--pid", str(shell_group.process.pid), "--find-visible"], required=False)
            alive(shell_group)
            if found.returncode not in (0, 1):
                raise RuntimeError("Server-side XRes window ownership query failed")
            observation = json.loads(found.stdout)
            if found.returncode == 0 and observation["matched"]:
                report["window"] = observation["window"]
                return str(observation["window"]["xid"])
            return None
        xid = until(window, "Exactly one original Makepad window did not appear", timeout=30)
        command("owned-window-pid", [sys.executable, "-B", str(owner_helper),
                "--pid", str(shell_group.process.pid), "--window-id", xid])
        alive(shell_group)
        command("owned-window-properties", ["xprop", "-id", xid, "WM_CLASS", "_NET_WM_PID", "WM_NAME"])
        command("owned-window-focus", ["xdotool", "windowfocus", "--sync", xid])
        save()
        stage("original-atspi-smoke", [sys.executable, "-B", str(smoke), "--pid", str(shell_group.process.pid),
              "--window-id", xid, "--output", str(output / "atspi-receipt.json")], 90)
        atspi = json.loads((output / "atspi-receipt.json").read_bytes())
        if atspi.get("passed") is not True:
            raise RuntimeError("Original supported AT-SPI test did not pass")
        if editable is not None:
            stage("original-atomic-editable-text", [sys.executable, "-B", str(editable), "--pid", str(shell_group.process.pid),
                  "--window-id", xid, "--output", str(output / "editable-text-receipt.json")]
                  + (["--request-scoped-paste"] if args.request_scoped_paste else []), 90)
            checked = json.loads((output / "editable-text-receipt.json").read_bytes())
            if checked.get("passed") is not True or checked.get("supported_methods_passed") is not True:
                raise RuntimeError("Original atomic EditableText methods did not pass")
            report["atomic_editable_text_methods_passed"] = True
        stage("original-real-ibus", [sys.executable, "-B", str(HERE / "ibus_client.py"), "--pid", str(shell_group.process.pid),
              "--window-id", xid, "--x11-owner-helper", str(owner_helper),
              "--engine", args.engine, "--state", str(private / "state"), "--output", str(output)]
              + (["--atomic-editable-text"] if editable is not None else []), 90)
        ime = json.loads((output / "ibus-receipt.json").read_bytes())
        if ime.get("passed") is not True:
            raise RuntimeError("Real IBus test did not pass")
        for group in (xserver, bus, a11y, ibus, shell_group):
            alive(group)
        report["supported_atspi_checks_passed"] = True
        report["real_virtual_x11_ibus_checks_passed"] = True
        report["passed"] = True
    except BaseException as error:
        report["error"] = f"{type(error).__name__}: {error}"
        raise
    finally:
        errors = []
        if guard is not None:
            for label, group in reversed(groups):
                try:
                    code = guard.terminate_group(group)
                    report.setdefault("cleanup", []).append({"label": label, "pid": group.process.pid, "exit_code": code})
                except BaseException as error:
                    errors.append(f"{label}: {error}")
        for log in logs:
            log.close()
        if temporary is not None:
            try:
                temporary.cleanup()
                report["private_credentials_and_state_removed"] = True
            except Exception as error:
                errors.append(f"private-state: {error}")
        if errors:
            report["passed"] = False
            report["cleanup_errors"] = errors
        report["finished_unix_ms"] = time.time_ns() // 1_000_000
        save()
        print(json.dumps({"passed": report["passed"], "receipt": str(output / "receipt.json"), "error": report.get("error")}, ensure_ascii=False))
        if errors:
            raise RuntimeError("Owned child/state cleanup failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shell", type=Path, required=True)
    parser.add_argument("--resources", type=Path, required=True)
    parser.add_argument("--hepta-source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engine", default="libpinyin")
    parser.add_argument("--build-receipt", type=Path)
    parser.add_argument("--packaged-binary", action="store_true",
                        help="Bind the installed/packaged ELF to packaged_binaries in the build receipt")
    parser.add_argument("--atomic-editable-text", action="store_true",
                        help="Require the original five atomic EditableText methods; full paste/Orca remain unqualified")
    parser.add_argument("--request-scoped-paste", action="store_true",
                        help="Require a hepta-native-clipboard-sdk binary, exact candidate bundle and real delayed-response PasteText tests")
    arguments = parser.parse_args()
    if arguments.request_scoped_paste and not arguments.atomic_editable_text:
        parser.error("--request-scoped-paste requires --atomic-editable-text")
    if arguments.packaged_binary and arguments.build_receipt is None:
        parser.error("--packaged-binary requires --build-receipt")
    def interrupted(_signal, _frame):
        raise KeyboardInterrupt("Qualification interrupted; cleaning only owned children")
    signal.signal(signal.SIGTERM, interrupted)
    run(arguments)
