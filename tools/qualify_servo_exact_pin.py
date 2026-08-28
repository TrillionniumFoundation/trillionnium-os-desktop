#!/usr/bin/env python3
"""Compile-qualify the exact Servo embedder source pin.

This tool does not start a browser or bind a listener. It verifies a clean
checkout, compiles Servo's official headed shell, probes public embedding API
paths from an external crate, and writes deterministic machine-readable
compatibility evidence.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import tomllib

PIN = "670ae8a70801b162e186f81cbb5bdd2d59c39108"

SYMBOL_CANDIDATES: dict[str, list[str]] = {
    "Servo": ["servo::Servo"],
    "WebView": ["servo::WebView", "servo::webview::WebView"],
    "WebViewBuilder": ["servo::WebViewBuilder", "servo::webview::WebViewBuilder"],
    "RenderingContext": [
        "servo::RenderingContext",
        "servo::rendering_context::RenderingContext",
    ],
    "EventLoopWaker": [
        "servo::EventLoopWaker",
        "servo::embedder_traits::EventLoopWaker",
    ],
    "ServoDelegate": ["servo::ServoDelegate"],
    "WebViewDelegate": ["servo::WebViewDelegate", "servo::webview::WebViewDelegate"],
}

METHOD_CANDIDATES: dict[str, list[str]] = {
    "webview_builder_constructor": [
        "servo::WebViewBuilder::new",
        "servo::webview::WebViewBuilder::new",
    ],
    "servo_event_loop_entry": [
        "servo::Servo::spin_event_loop",
        "servo::Servo::pump_event_loop",
        "servo::Servo::perform_updates",
        "servo::Servo::run_event_loop",
    ],
}


def run(
    command: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    log: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    log.parent.mkdir(parents=True, exist_ok=True)
    log.write_text(completed.stdout)
    if check and completed.returncode != 0:
        raise RuntimeError(
            f"command failed ({completed.returncode}): {' '.join(command)}; see {log}"
        )
    return completed


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_probe(probe: Path, servo_root: Path, source: str) -> None:
    if probe.exists():
        shutil.rmtree(probe)
    (probe / "src").mkdir(parents=True)
    cargo_toml = f'''[package]
name = "trillionnium-servo-api-probe"
version = "0.0.0"
edition = "2024"
publish = false

[workspace]

[dependencies]
servo = {{ path = "{(servo_root / 'components/servo').as_posix()}" }}
'''
    (probe / "Cargo.toml").write_text(cargo_toml)
    shutil.copy2(servo_root / "Cargo.lock", probe / "Cargo.lock")
    (probe / "src/main.rs").write_text(source)


def compile_source(
    *,
    source: str,
    name: str,
    servo_root: Path,
    work_root: Path,
    env: dict[str, str],
    logs: Path,
) -> bool:
    probe = work_root / name
    write_probe(probe, servo_root, source)
    completed = run(
        ["cargo", "check", "--locked", "--quiet"],
        cwd=probe,
        env=env,
        log=logs / f"{name}.log",
        check=False,
    )
    return completed.returncode == 0


def select_symbol_paths(
    *,
    servo_root: Path,
    work_root: Path,
    env: dict[str, str],
    logs: Path,
) -> dict[str, str]:
    selected: dict[str, str] = {}
    for symbol, candidates in SYMBOL_CANDIDATES.items():
        for index, candidate in enumerate(candidates):
            source = f"use {candidate} as Selected;\nfn main() {{ let _ = core::any::type_name::<Selected>(); }}\n"
            if compile_source(
                source=source,
                name=f"symbol-{symbol.lower()}-{index}",
                servo_root=servo_root,
                work_root=work_root,
                env=env,
                logs=logs,
            ):
                selected[symbol] = candidate
                break
        if symbol not in selected:
            raise RuntimeError(f"no public compile path found for {symbol}")
    return selected


def select_method_paths(
    *,
    servo_root: Path,
    work_root: Path,
    env: dict[str, str],
    logs: Path,
) -> dict[str, str]:
    selected: dict[str, str] = {}
    for purpose, candidates in METHOD_CANDIDATES.items():
        for index, candidate in enumerate(candidates):
            source = f"fn main() {{ let _selected = {candidate}; }}\n"
            if compile_source(
                source=source,
                name=f"method-{purpose}-{index}",
                servo_root=servo_root,
                work_root=work_root,
                env=env,
                logs=logs,
            ):
                selected[purpose] = candidate
                break
        if purpose not in selected:
            raise RuntimeError(f"no public compile path found for {purpose}")
    return selected


def aggregate_source(symbols: dict[str, str], methods: dict[str, str]) -> str:
    imports = "\n".join(
        f"use {path} as {name};" for name, path in sorted(symbols.items())
    )
    type_checks = "\n    ".join(
        f"let _ = core::any::type_name::<{name}>();" for name in sorted(symbols)
    )
    method_checks = "\n    ".join(
        f"let _{name} = {path};" for name, path in sorted(methods.items())
    )
    return f'''// Generated by tools/qualify_servo_exact_pin.py for Servo {PIN}.
{imports}

fn main() {{
    {type_checks}
    {method_checks}
}}
'''


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--servo-root", required=True, type=Path)
    parser.add_argument("--output-manifest", required=True, type=Path)
    parser.add_argument("--output-probe", required=True, type=Path)
    parser.add_argument("--logs", required=True, type=Path)
    args = parser.parse_args()

    servo_root = args.servo_root.resolve()
    output_manifest = args.output_manifest.resolve()
    output_probe = args.output_probe.resolve()
    logs = args.logs.resolve()
    logs.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    head = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=servo_root, text=True
    ).strip()
    if head != PIN:
        raise RuntimeError(f"Servo checkout is {head}, expected {PIN}")
    dirty = subprocess.check_output(
        ["git", "status", "--porcelain=v1"], cwd=servo_root, text=True
    )
    if dirty:
        raise RuntimeError("Servo checkout is not clean")

    required = [
        servo_root / "Cargo.lock",
        servo_root / "Cargo.toml",
        servo_root / "components/servo/Cargo.toml",
        servo_root / "components/servo/lib.rs",
        servo_root / "ports/servoshell/Cargo.toml",
        servo_root / "rust-toolchain.toml",
    ]
    for path in required:
        if not path.is_file():
            raise RuntimeError(f"required Servo input missing: {path}")

    toolchain = tomllib.loads((servo_root / "rust-toolchain.toml").read_text())
    channel = toolchain["toolchain"]["channel"]

    run(
        [
            "cargo",
            "check",
            "--manifest-path",
            str(servo_root / "ports/servoshell/Cargo.toml"),
            "--locked",
        ],
        cwd=servo_root,
        env=env,
        log=logs / "servoshell-cargo-check.log",
    )

    with tempfile.TemporaryDirectory(prefix="trillionnium-servo-probe-") as temp:
        work_root = Path(temp)
        symbols = select_symbol_paths(
            servo_root=servo_root,
            work_root=work_root,
            env=env,
            logs=logs,
        )
        methods = select_method_paths(
            servo_root=servo_root,
            work_root=work_root,
            env=env,
            logs=logs,
        )
        source = aggregate_source(symbols, methods)
        if not compile_source(
            source=source,
            name="aggregate",
            servo_root=servo_root,
            work_root=work_root,
            env=env,
            logs=logs,
        ):
            raise RuntimeError("aggregate external Servo API probe did not compile")

    output_probe.parent.mkdir(parents=True, exist_ok=True)
    output_probe.write_text(source)

    manifest = {
        "schema": "trillionnium.desktop.servo-embedder-compat.v2",
        "status": "PASS_COMPILE_COMPATIBILITY_ONLY",
        "servo_repository": "https://github.com/servo/servo",
        "servo_commit": PIN,
        "servo_toolchain_channel": channel,
        "source_hashes": {
            str(path.relative_to(servo_root)): sha256(path) for path in required
        },
        "public_symbol_paths": symbols,
        "public_method_paths": methods,
        "checks": {
            "exact_clean_checkout": "PASS",
            "official_headed_servoshell_cargo_check_locked": "PASS",
            "individual_external_api_probes": "PASS",
            "aggregate_external_api_probe": "PASS",
        },
        "claims": {
            "servo_started": False,
            "window_created": False,
            "frame_rendered": False,
            "native_input_forwarded": False,
            "ime_forwarded": False,
            "network_navigation_performed": False,
            "web_driver_listener_started": False,
        },
        "next_gate": "D0A-02 headed trusted-shell/content composition and local first frame",
    }
    output_manifest.parent.mkdir(parents=True, exist_ok=True)
    output_manifest.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
