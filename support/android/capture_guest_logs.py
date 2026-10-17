#!/usr/bin/env python3
"""Capture Android guest boot-chain observations through adb.

Every command is a real observation. A failed command is written to disk and
classified as blocked; it is never converted into a synthetic success.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


STAGES = [
    ("bionic", ["shell", "getprop", "ro.product.cpu.abi"]),
    ("init", ["shell", "getprop", "init.svc.bootanim"]),
    ("binder", ["shell", "ls", "-l", "/dev/binder", "/dev/vndbinder", "/dev/hwbinder"]),
    ("zygote", ["shell", "pidof", "zygote", "zygote64"]),
    ("system_server", ["shell", "pidof", "system_server"]),
    ("art", ["shell", "getprop", "dalvik.vm.usejit"]),
    ("package_manager", ["shell", "cmd", "package", "list", "packages"]),
    ("graphics", ["shell", "dumpsys", "SurfaceFlinger"]),
]


def classify(stage: str, output: str, code: int) -> str:
    if code == 0:
        return "observed"
    lowered = output.lower()
    if stage == "binder" and ("no such file" in lowered or "not found" in lowered):
        return "blocked_missing_binder"
    if stage in {"zygote", "system_server"} and ("no such process" in lowered or not output.strip()):
        return "blocked_service_not_running"
    if stage == "graphics" and ("not found" in lowered or "permission" in lowered):
        return "blocked_graphics_observation"
    return "blocked_command_failure"


def call(adb: str, serial: str | None, args: list[str]) -> tuple[int, str, list[str]]:
    command = [adb]
    if serial:
        command += ["-s", serial]
    command += args
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        return result.returncode, (result.stdout + result.stderr).strip(), command
    except OSError as exc:
        return 127, str(exc), command


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--adb", default=shutil.which("adb"))
    parser.add_argument("--serial", required=True, help="explicit disposable Cuttlefish serial")
    args = parser.parse_args(argv)
    if not args.adb:
        parser.error("adb is required; no fake guest log can be generated")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "schema_version": 1,
        "execution_class": "android-guest-reference",
        "native_android_claim": False,
        "adb": args.adb,
        "serial": args.serial,
        "recorded_at_utc": datetime.now(timezone.utc).isoformat(),
        "stages": [],
    }
    for stage, command_args in STAGES:
        code, output, command = call(args.adb, args.serial, command_args)
        (args.output_dir / f"{stage}.log").write_text(output + "\n", encoding="utf-8")
        report["stages"].append(
            {"stage": stage, "status": classify(stage, output, code), "returncode": code, "command": command, "log": f"{stage}.log"}
        )
    (args.output_dir / "summary.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if all(stage["status"] == "observed" for stage in report["stages"]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
