#!/usr/bin/env python3
"""Capture real A10 Shell/Notes pixels in a new private software compositor.

This exercises host font loading and a Session-owned native Notes process.
It does not inject text-input events or qualify a live Chinese input method.
The image receipts require visual review; color counts alone do not recognize
Chinese text. Only processes and temporary runtime directories created here
are controlled. No current desktop, font installation or cache is modified.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time

# Import only the already-tested child identity guard; importing this module
# does not execute its original-Agentd harness or create bytecode side files.
sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
GUARD_SOURCE = ROOT / "tests/integration/hepta/run_original_agentd.py"
SPEC = importlib.util.spec_from_file_location("a10_pixel_child_guard", GUARD_SOURCE)
guard = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(guard)


def require(value, message):
    if not value:
        raise RuntimeError(message)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--binaries", type=Path, required=True)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--font-index", type=int, default=0)
    parser.add_argument("--output", type=Path, required=True, help="new evidence directory")
    args = parser.parse_args()
    require(0 <= args.font_index <= 0xFFFFFFFF, "invalid font face index")
    require(guard.child_anchor_available(), "waitable child process identity required")
    from PIL import Image, ImageChops
    binaries = args.binaries.resolve()
    font = args.font.resolve(strict=True)
    require(font.is_file() and font.stat().st_size <= 32 * 1024 * 1024, "font must be a regular file of at most 32 MiB")
    paths = {name: binaries / name for name in ["trill-shell", "trill-session", "trill-app-window", "trill-ctl"]}
    for executable in paths.values():
        require(executable.is_file() and os.access(executable, os.X_OK), "compiled A10 executable missing")
    checkout_commit = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    checkout_tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=ROOT, text=True).strip()
    binary_hashes = {name: digest(path) for name, path in paths.items()}
    output = args.output.resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    runtime = Path(tempfile.mkdtemp(prefix="a10-cjk-pixels-"))
    env = os.environ.copy()
    for name in list(env):
        if name.startswith("TRILL_") or name in ("DISPLAY", "WAYLAND_SOCKET", "EFRAME_SCREENSHOT_TO"):
            env.pop(name)
    env.update({
        "XDG_RUNTIME_DIR": str(runtime), "WAYLAND_DISPLAY": "a10-cjk-private",
        "XDG_STATE_HOME": str(runtime / "state"),
        "XDG_CONFIG_HOME": str(runtime / "config"),
        "XDG_CACHE_HOME": str(runtime / "cache"),
        "LIBGL_ALWAYS_SOFTWARE": "1", "EGL_PLATFORM": "wayland",
        "TRILL_UI_CJK_FONT": str(font), "TRILL_UI_CJK_FONT_INDEX": str(args.font_index),
    })
    report = {
        "evidence_class": "private_pixman_compositor_shell_and_notes_capture",
        "checkout_commit": checkout_commit,
        "checkout_tree": checkout_tree,
        "binary_sha256": binary_hashes,
        "binary_source_qualification": "pair these hashes with the recorded Rust build; checkout identity alone is insufficient",
        "probe_sha256": digest(Path(__file__)), "child_guard_sha256": digest(GUARD_SOURCE),
        "font": {"path": str(font), "face_index": args.font_index, "bytes": font.stat().st_size, "sha256": digest(font)},
        "renderer": "pixman", "visual_review_required": True,
        "real_ime_verified": False, "physical_monitor_or_gpu_verified": False,
        "original_agentd_started": False, "objective_submitted": False,
        "started_unix_ms": time.time_ns() // 1_000_000, "passed": False,
    }
    groups, logs = [], []
    owned_task = session_instance = None
    ctl_number = 0

    def spawn(label, command):
        stdout = (output / (label + ".stdout.log")).open("xb")
        stderr = (output / (label + ".stderr.log")).open("xb")
        logs.extend([stdout, stderr])
        process = subprocess.Popen(command, env=env, cwd=output, stdin=subprocess.DEVNULL,
            stdout=stdout, stderr=stderr, start_new_session=True)
        group = guard.ChildGroup(process)
        groups.append((label, group))
        return group

    def alive(group):
        return group.observe_exit() is None

    def ctl(*arguments):
        nonlocal ctl_number
        ctl_number += 1
        completed = subprocess.run([str(paths["trill-ctl"]), *arguments], env=env,
            stdin=subprocess.DEVNULL, capture_output=True, timeout=3)
        label = f"ctl-{ctl_number:03d}-{arguments[0]}"
        (output / (label + ".stdout.log")).write_bytes(completed.stdout)
        (output / (label + ".stderr.log")).write_bytes(completed.stderr)
        require(completed.returncode == 0, "owned Session command failed: " + arguments[0])
        return json.loads(completed.stdout)

    def capture(label):
        destination = output / label
        destination.mkdir(mode=0o700)
        with (destination / "capture.stdout.log").open("xb") as stdout, (destination / "capture.stderr.log").open("xb") as stderr:
            completed = subprocess.run(["weston-screenshooter"], env=env, cwd=destination,
                stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr, timeout=5)
        require(completed.returncode == 0, "private compositor capture failed")
        pngs = list(destination.glob("*.png"))
        require(len(pngs) == 1, "capture did not produce exactly one PNG")
        with Image.open(pngs[0]) as opened:
            image = opened.convert("RGB")
            require(image.size == (1440, 900), "unexpected compositor pixel size")
            colors = image.getcolors(maxcolors=2_000_000)
            require(colors is not None and len(colors) > 20, "capture lacks rendered color detail")
            details = {"path": str(pngs[0].relative_to(output)), "sha256": digest(pngs[0]),
                "bytes": pngs[0].stat().st_size, "size": list(image.size), "distinct_colors": len(colors)}
        return details, image

    def require_different(before, after):
        # Exclude the compositor's top panel clock. This checks that actual
        # window pixels changed; it is deliberately not an OCR/CJK assertion.
        delta = ImageChops.difference(before, after).crop((0, 40, 1440, 900))
        changed = sum(count for count, color in delta.getcolors(maxcolors=2_000_000) if color != (0, 0, 0))
        require(changed > 10_000, "application capture did not change enough window pixels")
        return changed

    try:
        weston = spawn("weston", ["weston", "--backend=headless-backend.so", "--renderer=pixman",
            "--no-config", "--debug", "--width=1440", "--height=900", "--idle-time=0",
            "--socket=" + env["WAYLAND_DISPLAY"], "--log=" + str(output / "weston.log")])
        for attempt in range(80):
            require(alive(weston), "private compositor exited before readiness")
            if (runtime / env["WAYLAND_DISPLAY"]).is_socket():
                registry = subprocess.run(["wayland-info"], env=env, capture_output=True, timeout=2)
                if registry.returncode == 0:
                    break
            require(attempt < 79, "private compositor registry timed out")
            time.sleep(.05)
        (output / "wayland-registry.stdout.log").write_bytes(registry.stdout)
        (output / "wayland-registry.stderr.log").write_bytes(registry.stderr)
        report["ime_environment"] = {
            "text_input_v3_advertised": b"interface: 'zwp_text_input_manager_v3'" in registry.stdout,
            "text_input_v1_advertised": b"interface: 'zwp_text_input_manager_v1'" in registry.stdout,
            "seat_advertised": b"interface: 'wl_seat'" in registry.stdout,
            "qualification": "registry availability alone never proves an input method",
        }
        require("Using Pixman renderer" in (output / "weston.log").read_text(), "requested software renderer was not observed")
        time.sleep(.35)
        report["background"], background = capture("background")
        session = spawn("session", [str(paths["trill-session"])])
        for attempt in range(80):
            require(alive(session), "private Session exited before socket readiness")
            if (runtime / "trillionnium-ui/session.sock").is_socket():
                break
            require(attempt < 79, "private Session socket timed out")
            time.sleep(.05)
        snapshot = ctl("snapshot")
        session_instance = snapshot["session_instance"]
        require(snapshot["tasks"] == [], "private Session unexpectedly owns pre-existing tasks")
        shell = spawn("shell", [str(paths["trill-shell"])])
        for attempt in range(120):
            require(all(alive(group) for group in [weston, session, shell]), "owned UI process exited before layout")
            if b"TRILL_SHELL_FIRST_FRAME_V1\n" in (output / "shell.stdout.log").read_bytes():
                break
            require(attempt < 119, "Shell layout timed out")
            time.sleep(.05)
        require("TRILL_UI_FONT_V1 loaded=true source=explicit" in (output / "shell.stderr.log").read_text(), "Shell did not validate the selected font")
        time.sleep(.5)
        report["shell"], shell_pixels = capture("shell")
        report["shell"]["changed_pixels_from_background"] = require_different(background, shell_pixels)
        launch = ctl("launch", "personal", "notes")
        require(launch["session_instance"] == session_instance, "Session generation changed")
        owned_task = launch["task"]["id"]
        for attempt in range(100):
            snapshot = ctl("snapshot")
            require(snapshot["session_instance"] == session_instance, "Session generation changed")
            task = next((item for item in snapshot["tasks"] if item["id"] == owned_task), None)
            require(task is not None and task["state"] == "running", "Notes is not a running Session-owned task")
            if task["ui_first_frame_unix_ms"] is not None:
                break
            require(attempt < 99, "Notes layout timed out")
            time.sleep(.05)
        require("TRILL_UI_FONT_V1 loaded=true source=explicit" in (output / "session.stderr.log").read_text(), "Notes did not validate the selected font")
        report["notes_task"] = task
        time.sleep(.5)
        report["notes"], notes_pixels = capture("notes")
        report["notes"]["changed_pixels_from_shell"] = require_different(shell_pixels, notes_pixels)
        require(digest(font) == report["font"]["sha256"], "font file changed during capture")
        report["owned_pids"] = {label: group.process.pid for label, group in groups}
        report["passed"] = True
    except Exception as error:
        report["error"] = str(error)
        raise
    finally:
        report["cleanup"] = []
        if owned_task is not None:
            try:
                ctl("cancel", str(owned_task), session_instance)
                for attempt in range(80):
                    snapshot = ctl("snapshot")
                    require(snapshot["session_instance"] == session_instance, "Session changed during cleanup")
                    task = next(item for item in snapshot["tasks"] if item["id"] == owned_task)
                    if task["state"] == "cancelled":
                        break
                    require(attempt < 79, "Notes cancellation was not observed")
                    time.sleep(.05)
                report["cleanup"].append({"label": "notes", "observed_task": task})
            except Exception as error:
                report["cleanup"].append({"label": "notes", "error": str(error)})
                report["passed"] = False
        for label, group in reversed(groups):
            try:
                report["cleanup"].append({"label": label, "reaped": True, "exit_code": guard.terminate_group(group)})
            except Exception as error:
                report["cleanup"].append({"label": label, "reaped": False, "error": str(error)})
                report["passed"] = False
        for stream in logs:
            stream.close()
        shutil.rmtree(runtime)
        report["finished_unix_ms"] = time.time_ns() // 1_000_000
        (output / "receipt.json").write_text(json.dumps(report, indent=2) + "\n")
    require(report["passed"], "private process cleanup failed")
    print("PASS: private Pixman captured actual Shell and Session-owned Notes windows with the selected font; inspect the PNGs. Live IME is NOT VERIFIED.")


if __name__ == "__main__":
    main()
