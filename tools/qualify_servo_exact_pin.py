#!/usr/bin/env python3
"""Compile-qualify the exact Servo embedder source pin.

This gate compiles Servo's own minimal winit example, a Trillionnium public-API
example, and the official headed servoshell under Servo's declared toolchain
and Cargo.lock. It never starts Servo, a display server, WebDriver, or a network
navigation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import tomllib
from typing import Any

PIN = "670ae8a70801b162e186f81cbb5bdd2d59c39108"
PROBE_NAME = "trillionnium_embedder_probe"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log_path: Path,
) -> subprocess.CompletedProcess[str]:
    started = time.monotonic()
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    elapsed_ms = round((time.monotonic() - started) * 1000)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(
        f"$ {' '.join(command)}\n"
        f"exit={completed.returncode} elapsed_ms={elapsed_ms}\n\n"
        f"{completed.stdout}",
        encoding="utf-8",
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}; "
            f"see {log_path}"
        )
    return completed


def git_output(servo_root: Path, *args: str) -> str:
    return subprocess.check_output(
        ["git", *args], cwd=servo_root, text=True, stderr=subprocess.STDOUT
    ).strip()


def require_regex(text: str, pattern: str, label: str) -> None:
    if re.search(pattern, text, flags=re.MULTILINE) is None:
        raise RuntimeError(f"required Servo API surface missing: {label}")


def require_clean_checkout(servo_root: Path) -> None:
    actual = git_output(servo_root, "rev-parse", "HEAD")
    if actual != PIN:
        raise RuntimeError(f"Servo checkout is {actual}, expected {PIN}")
    if git_output(servo_root, "status", "--porcelain=v1"):
        raise RuntimeError("Servo checkout is not clean")


def validate_source_surface(
    servo_root: Path,
    requirements: dict[str, Any],
) -> dict[str, list[str]]:
    webview = (servo_root / "components/servo/webview.rs").read_text(encoding="utf-8")
    delegate = (servo_root / "components/servo/webview_delegate.rs").read_text(
        encoding="utf-8"
    )
    lib = (servo_root / "components/servo/lib.rs").read_text(encoding="utf-8")
    minimal = (servo_root / "components/servo/examples/winit_minimal.rs").read_text(
        encoding="utf-8"
    )

    for export in [
        "ServoBuilder",
        "WebViewBuilder",
        "WindowRenderingContext",
        "WebViewDelegate",
        "ServoDelegate",
    ]:
        if export not in lib:
            raise RuntimeError(f"Servo public export source does not mention {export}")

    for method in requirements["required_webview_methods"]:
        require_regex(
            webview,
            rf"\bpub\s+fn\s+{re.escape(method)}\b",
            f"WebView::{method}",
        )

    for callback in requirements["required_delegate_callbacks"]:
        require_regex(
            delegate,
            rf"\bfn\s+{re.escape(callback)}\b",
            f"WebViewDelegate::{callback}",
        )

    for fragment in [
        "ServoBuilder::default()",
        ".event_loop_waker(Box::new(WinitEventLoopWaker::new(event_loop)))",
        "WebViewBuilder::new(&servo, rendering_context)",
        "servo.spin_event_loop()",
        "webview.notify_input_event(event)",
        "webview.paint()",
        "webview.rendering_context().present()",
    ]:
        if fragment not in minimal:
            raise RuntimeError(f"official winit_minimal no longer contains: {fragment}")

    return {
        "webview_methods": list(requirements["required_webview_methods"]),
        "delegate_callbacks": list(requirements["required_delegate_callbacks"]),
        "official_minimal_flow": [
            "ServoBuilder::default",
            "EventLoopWaker",
            "WebViewBuilder::new",
            "Servo::spin_event_loop",
            "WebView::notify_input_event",
            "WebView::paint",
            "RenderingContext::present",
        ],
    }


def parse_toolchain(servo_root: Path) -> tuple[str, list[str], list[str]]:
    document = tomllib.loads(
        (servo_root / "rust-toolchain.toml").read_text(encoding="utf-8")
    )["toolchain"]
    channel = document["channel"]
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", channel) is None:
        raise RuntimeError(f"Servo toolchain is not an exact release: {channel}")
    components = sorted(document.get("components", []))
    targets = sorted(document.get("targets", []))
    return channel, components, targets


def compile_targets(
    servo_root: Path,
    probe_source: Path,
    logs: Path,
    env: dict[str, str],
) -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}

    commands = {
        "cargo_metadata_locked": [
            "cargo",
            "metadata",
            "--locked",
            "--no-deps",
            "--format-version",
            "1",
        ],
        "official_winit_minimal": [
            "cargo",
            "check",
            "--locked",
            "-p",
            "servo",
            "--example",
            "winit_minimal",
        ],
        "official_servoshell": [
            "cargo",
            "check",
            "--locked",
            "-p",
            "servoshell",
            "--bin",
            "servoshell",
            "--no-default-features",
            "--features",
            "bundled,default_web_features,max_log_level,js_jit",
        ],
    }

    for name, command in commands.items():
        log = logs / f"{name}.log"
        started = time.monotonic()
        run(command, cwd=servo_root, env=env, log_path=log)
        results[name] = {
            "status": "PASS",
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "log_sha256": sha256(log),
        }

    example_path = servo_root / f"components/servo/examples/{PROBE_NAME}.rs"
    if example_path.exists():
        raise RuntimeError(f"temporary probe path already exists: {example_path}")
    shutil.copy2(probe_source, example_path)
    try:
        log = logs / "trillionnium_embedder_probe.log"
        started = time.monotonic()
        run(
            [
                "cargo",
                "check",
                "--locked",
                "-p",
                "servo",
                "--example",
                PROBE_NAME,
            ],
            cwd=servo_root,
            env=env,
            log_path=log,
        )
        results["trillionnium_embedder_probe"] = {
            "status": "PASS",
            "elapsed_ms": round((time.monotonic() - started) * 1000),
            "log_sha256": sha256(log),
            "source_sha256": sha256(probe_source),
        }
    finally:
        example_path.unlink(missing_ok=True)

    require_clean_checkout(servo_root)
    return results


def command_version(command: list[str], *, cwd: Path, env: dict[str, str]) -> str:
    return subprocess.check_output(command, cwd=cwd, env=env, text=True).strip()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--servo-root", required=True, type=Path)
    parser.add_argument("--requirements", required=True, type=Path)
    parser.add_argument("--patch-ledger", required=True, type=Path)
    parser.add_argument("--probe-source", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--logs", required=True, type=Path)
    args = parser.parse_args()

    servo_root = args.servo_root.resolve()
    requirements = json.loads(args.requirements.read_text(encoding="utf-8"))
    patch_ledger = json.loads(args.patch_ledger.read_text(encoding="utf-8"))
    if requirements["servo_commit"] != PIN or patch_ledger["servo_commit"] != PIN:
        raise RuntimeError("repository Servo contracts disagree with the qualification pin")
    if patch_ledger["patch_count"] != 0 or patch_ledger["patches"]:
        raise RuntimeError("D0A-01 requires a zero-delta Servo checkout")

    require_clean_checkout(servo_root)
    for relative in requirements["required_inputs"]:
        path = servo_root / relative
        if not path.is_file():
            raise RuntimeError(f"required Servo input missing: {relative}")

    channel, components, targets = parse_toolchain(servo_root)
    env = os.environ.copy()
    env["RUSTUP_TOOLCHAIN"] = channel
    env.setdefault("CARGO_TERM_COLOR", "always")

    source_surface = validate_source_surface(servo_root, requirements)
    logs = args.logs.resolve()
    logs.mkdir(parents=True, exist_ok=True)
    compile_results = compile_targets(
        servo_root,
        args.probe_source.resolve(),
        logs,
        env,
    )

    required_hashes = {
        relative: sha256(servo_root / relative)
        for relative in requirements["required_inputs"]
    }
    report = {
        "schema": "trillionnium.desktop.servo-qualification-result.v2",
        "status": "PASS_COMPILE_COMPATIBILITY_ONLY",
        "servo": {
            "repository": "https://github.com/servo/servo",
            "commit": PIN,
            "clean_checkout": True,
            "source_hashes": required_hashes,
            "patch_count": 0,
        },
        "toolchain": {
            "declared_channel": channel,
            "declared_components": components,
            "declared_targets": targets,
            "rustc_version": command_version(
                ["rustc", "--version", "--verbose"], cwd=servo_root, env=env
            ),
            "cargo_version": command_version(
                ["cargo", "--version", "--verbose"], cwd=servo_root, env=env
            ),
        },
        "source_surface": source_surface,
        "compile_results": compile_results,
        "supported_for_d0a02": {
            "builder_initialization": True,
            "event_loop_wake_and_spin": True,
            "one_content_webview": True,
            "render_and_present": True,
            "pointer_keyboard_wheel_input_entry": True,
            "composition_and_input_method_types": True,
            "navigation_callback_and_denial": True,
            "popup_new_webview_callback_and_denial": True,
            "crash_callback": True,
            "screenshot_callback": True,
            "accessibility_tree_update_callback": True,
            "resource_interception_type": True,
        },
        "deferred_or_unproven": [
            "runtime visible first frame",
            "runtime native keyboard pointer wheel and IME delivery",
            "runtime popup denial",
            "runtime content crash recovery",
            "stable semantic element identifier contract for BrowserActor",
            "public arbitrary hit-test query independent of input dispatch",
        ],
        "claims": {
            "servo_started": False,
            "window_created": False,
            "frame_rendered": False,
            "native_input_forwarded": False,
            "ime_forwarded": False,
            "network_navigation_performed": False,
            "web_driver_listener_started": False,
            "debian_image_built": False,
            "product_ready": False,
        },
        "next_gate": "D0A-02 product-owned headed local-fixture runtime",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - command-line gate needs one failure path
        print(f"Servo qualification failed: {error}", file=sys.stderr)
        raise
