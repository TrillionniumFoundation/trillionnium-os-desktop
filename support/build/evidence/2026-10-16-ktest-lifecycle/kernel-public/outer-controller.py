#!/usr/bin/env python3
"""Retain an actual A01 public entry invocation; no kernel emulation."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("ktest", "boot"))
    parser.add_argument("--head", required=True)
    args = parser.parse_args()
    scratch = Path(__file__).resolve().parent
    work = scratch / "a01-next6-build"
    command = ([sys.executable, "-I", "support/build/ktest/run.py"] if args.mode == "ktest"
               else ["support/build/kernel.sh", "run_kernel"])
    output = work / "support/build/out" / ("next7-" + args.mode + "-01")
    if output.exists():
        raise SystemExit("new output required")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=work, text=True).strip()
    if head != args.head:
        raise SystemExit("unexpected source HEAD")
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--"], cwd=work).returncode:
        raise SystemExit("tracked source is dirty")
    environment = dict(os.environ)
    selected = {
        "CARGO_HOME": str(scratch / "toolchains/cargo"),
        "RUSTUP_HOME": str(scratch / "toolchains/rustup"),
        "RUSTUP_TOOLCHAIN": "nightly-2026-07-21",
        "CARGO_NET_OFFLINE": "true",
        "CARGO_TARGET_DIR": str(work / "kernel/asterinas/target"),
        "CARGO_BUILD_JOBS": "2",
        "VDSO_LIBRARY_DIR": str(scratch / "linux-vdso"),
        "A01_KTEST_TIMEOUT": "300",
        "A01_QEMU_TIMEOUT": "300",
    }
    if args.mode == "ktest":
        command += ["--output", str(output)]
    else:
        selected["A01_RUN_DIR"] = str(output)
    environment.update(selected)
    environment["PATH"] = selected["CARGO_HOME"] + "/bin:" + environment["PATH"]
    receipt_path = scratch / ("next7-" + args.mode + "-invocation.json")
    log_path = scratch / ("next7-" + args.mode + "-console.log")
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=work, text=True).strip()
    receipt = {
        "schema": 1, "kind": "actual_public_entry_invocation", "mode": args.mode,
        "started_utc": datetime.now(timezone.utc).isoformat(), "source_head": head,
        "source_tree": tree, "argv": command, "cwd": str(work), "environment": selected,
        "git_status": subprocess.check_output(["git", "status", "--short"], cwd=work, text=True),
        "target_cache_reused_from": "next6 actual full kernel/debug/cancel runs; not an empty-target build",
        "controller_sha256": sha(Path(__file__)), "outer_exit_code": None,
    }
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"argv": command, "source": head, "output": str(output)}), flush=True)
    with log_path.open("wb") as log:
        process = subprocess.Popen(command, cwd=work, env=environment, stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT)
        receipt["entry_pid"] = process.pid
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
        for line in process.stdout:
            log.write(line)
            log.flush()
            if any(mark in line for mark in (b"Compiling ", b"Finished ", b"PASS:", b"error:",
                                              b"failed", b"evidence:", b"A01_KERNEL_SUPERVISOR")):
                sys.stdout.write(line.decode(errors="replace"))
                sys.stdout.flush()
        code = process.wait()
    receipt.update(outer_exit_code=code, completed_utc=datetime.now(timezone.utc).isoformat(),
                   console_sha256=sha(log_path), console_size=log_path.stat().st_size,
                   git_status_after=subprocess.check_output(["git", "status", "--short"], cwd=work, text=True))
    receipt_path.write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"actual_outer_exit_code": code, "receipt": str(receipt_path)}), flush=True)
    return code if code >= 0 else 128 - code


if __name__ == "__main__":
    raise SystemExit(main())
