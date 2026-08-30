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
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import stat
import sys
import time
import tomllib
from typing import Any

from gate_evidence_envelope import load_json_strict

PIN = "670ae8a70801b162e186f81cbb5bdd2d59c39108"
PROBE_NAME = "trillionnium_embedder_probe"
_O_CLOEXEC = getattr(os, "O_CLOEXEC", 0)
_O_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_O_NONBLOCK = getattr(os, "O_NONBLOCK", 0)


def _has_symlink_component(path: Path) -> bool:
    """Return whether an existing lexical component of *path* is a symlink."""

    lexical = Path(os.fspath(path))
    if not lexical.is_absolute():
        lexical = Path.cwd() / lexical
    current = Path(lexical.anchor)
    for component in lexical.parts:
        if component in {lexical.anchor, "", "."}:
            continue
        if component == "..":
            current = current.parent
            continue
        current /= component
        try:
            mode = os.lstat(current).st_mode
        except FileNotFoundError:
            return False
        except OSError as error:
            raise RuntimeError(f"cannot inspect path component: {current}") from error
        if stat.S_ISLNK(mode):
            return True
    return False


def _open_regular(path: Path, label: str, *, writable: bool = False):
    """Open one regular file without following a late symlink replacement."""

    if _has_symlink_component(path):
        raise RuntimeError(f"{label} path contains a symlink: {path}")
    flags = (os.O_WRONLY | os.O_CREAT | os.O_TRUNC) if writable else os.O_RDONLY
    flags |= _O_CLOEXEC | _O_NOFOLLOW | _O_NONBLOCK
    try:
        descriptor = os.open(path, flags, 0o644) if writable else os.open(path, flags)
    except OSError as error:
        raise RuntimeError(f"{label} is absent or unsafe: {path}") from error
    try:
        mode = os.fstat(descriptor).st_mode
        if not stat.S_ISREG(mode):
            raise RuntimeError(f"{label} is not a regular file: {path}")
        return descriptor
    except BaseException:
        os.close(descriptor)
        raise


def read_text_file(path: Path, label: str) -> str:
    descriptor = _open_regular(path, label)
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            try:
                return stream.read().decode("utf-8")
            except UnicodeDecodeError as error:
                raise RuntimeError(f"{label} is not valid UTF-8: {path}") from error
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def write_text_file(path: Path, text: str, label: str) -> None:
    if _has_symlink_component(path):
        raise RuntimeError(f"{label} path contains a symlink: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    if _has_symlink_component(path):
        raise RuntimeError(f"{label} path contains a symlink: {path}")
    descriptor = _open_regular(path, label, writable=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", closefd=True) as stream:
            descriptor = -1
            stream.write(text)
            stream.flush()
            try:
                os.fsync(stream.fileno())
            except OSError:
                pass
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def load_json_file(path: Path, label: str) -> dict[str, Any]:
    descriptor = _open_regular(path, label)
    try:
        with os.fdopen(descriptor, "r", encoding="utf-8", closefd=True) as stream:
            descriptor = -1
            value = load_json_strict(stream)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    if not isinstance(value, dict):
        raise RuntimeError(f"{label} must be a JSON object: {path}")
    return value


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    descriptor = _open_regular(path, "hashed file")
    try:
        with os.fdopen(descriptor, "rb", closefd=True) as stream:
            descriptor = -1
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    finally:
        if descriptor >= 0:
            os.close(descriptor)
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
    write_text_file(
        log_path,
        f"$ {' '.join(command)}\n"
        f"exit={completed.returncode} elapsed_ms={elapsed_ms}\n\n"
        f"{completed.stdout}",
        "qualification command log",
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
    webview = read_text_file(
        servo_root / "components/servo/webview.rs", "Servo WebView source"
    )
    delegate = read_text_file(
        servo_root / "components/servo/webview_delegate.rs",
        "Servo WebView delegate source",
    )
    lib = read_text_file(servo_root / "components/servo/lib.rs", "Servo lib source")
    minimal = read_text_file(
        servo_root / "components/servo/examples/winit_minimal.rs",
        "Servo official winit example",
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
        read_text_file(
            servo_root / "rust-toolchain.toml", "Servo toolchain manifest"
        )
    )["toolchain"]
    channel = document["channel"]
    if re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", channel) is None:
        raise RuntimeError(f"Servo toolchain is not an exact release: {channel}")
    components = sorted(document.get("components", []))
    targets = sorted(document.get("targets", []))
    return channel, components, targets


def required_servo_inputs(servo_root: Path, requirements: dict[str, Any]) -> list[str]:
    """Validate locked Servo input names before reading from the checkout."""

    values = requirements.get("required_inputs")
    if not isinstance(values, list) or not values or any(
        not isinstance(item, str) for item in values
    ):
        raise RuntimeError("Servo requirements manifest has no valid input list")
    selected: list[str] = []
    seen: set[str] = set()
    for item in values:
        relative = PurePosixPath(item)
        if (
            not item
            or "\\" in item
            or "\x00" in item
            or relative.is_absolute()
            or relative.as_posix() != item
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            raise RuntimeError(f"Servo requirements path is unsafe: {item!r}")
        if item in seen:
            raise RuntimeError(f"Servo requirements contain duplicate input: {item!r}")
        seen.add(item)
        candidate = servo_root.joinpath(*relative.parts)
        if _has_symlink_component(candidate):
            raise RuntimeError(f"Servo requirements input contains a symlink: {item}")
        if not candidate.is_file() or candidate.is_symlink():
            raise RuntimeError(f"required Servo input missing or unsafe: {item}")
        selected.append(item)
    return selected


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
    if _has_symlink_component(example_path):
        raise RuntimeError(f"temporary probe path contains a symlink: {example_path}")
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
        if _has_symlink_component(example_path):
            raise RuntimeError(f"temporary probe path became a symlink: {example_path}")
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

    raw_paths = (
        (args.servo_root, "Servo checkout"),
        (args.requirements, "Servo requirements manifest"),
        (args.patch_ledger, "Servo patch ledger"),
        (args.probe_source, "Servo probe source"),
        (args.output, "qualification output"),
        (args.logs, "qualification logs"),
    )
    for path, label in raw_paths:
        if _has_symlink_component(path):
            raise RuntimeError(f"{label} path contains a symlink: {path}")

    servo_root = args.servo_root.resolve()
    if not servo_root.is_dir() or servo_root.is_symlink():
        raise RuntimeError(f"Servo checkout is missing or unsafe: {servo_root}")
    probe_source = args.probe_source.absolute()
    if not probe_source.is_file() or probe_source.is_symlink():
        raise RuntimeError(f"Servo probe source is missing or unsafe: {probe_source}")
    requirements = load_json_file(args.requirements, "Servo requirements manifest")
    patch_ledger = load_json_file(args.patch_ledger, "Servo patch ledger")
    if requirements["servo_commit"] != PIN or patch_ledger["servo_commit"] != PIN:
        raise RuntimeError("repository Servo contracts disagree with the qualification pin")
    if patch_ledger["patch_count"] != 0 or patch_ledger["patches"]:
        raise RuntimeError("D0A-01 requires a zero-delta Servo checkout")

    require_clean_checkout(servo_root)
    input_names = required_servo_inputs(servo_root, requirements)

    channel, components, targets = parse_toolchain(servo_root)
    env = os.environ.copy()
    env["RUSTUP_TOOLCHAIN"] = channel
    env.setdefault("CARGO_TERM_COLOR", "always")

    source_surface = validate_source_surface(servo_root, requirements)
    logs = args.logs.absolute()
    logs.mkdir(parents=True, exist_ok=True)
    if _has_symlink_component(logs) or not logs.is_dir():
        raise RuntimeError(f"qualification logs directory is missing or unsafe: {logs}")
    compile_results = compile_targets(
        servo_root,
        probe_source,
        logs,
        env,
    )

    required_hashes = {
        relative: sha256(servo_root / relative) for relative in input_names
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
    output = args.output.absolute()
    write_text_file(
        output,
        json.dumps(report, indent=2, sort_keys=True) + "\n",
        "qualification output",
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:  # noqa: BLE001 - command-line gate needs one failure path
        print(f"Servo qualification failed: {error}", file=sys.stderr)
        raise
