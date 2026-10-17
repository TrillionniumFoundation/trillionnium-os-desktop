#!/usr/bin/env python3
"""Run the separate A10 Linux host toolchain and retain a single target cache."""
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parent
env = os.environ.copy()
env["RUSTUP_HOME"] = str(root / "rustup")
env["CARGO_HOME"] = str(root / "cargo")
env["PATH"] = str(root / "cargo/bin") + os.pathsep + env.get("PATH", "")
env["RUSTUP_TOOLCHAIN"] = "1.88.0"
env["CARGO_TARGET_DIR"] = str(root.parent / "r2-host-target")
env["CARGO_INCREMENTAL"] = "0"
env["CARGO_PROFILE_DEV_DEBUG"] = "0"
env["CARGO_PROFILE_TEST_DEBUG"] = "0"
env["CARGO_BUILD_JOBS"] = "2"
env["RUNNER_TEMP"] = str(root / "r2-evidence")
if len(sys.argv) < 2:
    raise SystemExit("usage: run-host-rust.py <command> [args...]")
os.execvpe(sys.argv[1], sys.argv[1:], env)
