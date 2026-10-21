#!/usr/bin/env python3
"""Run each OSDK ktest guest with an isolated log and a fixed QEMU profile."""
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time

SELECTOR_PATH = Path(__file__).resolve().parents[1] / "record-qemu.py"
SELECTOR_SPEC = importlib.util.spec_from_file_location("a01_ktest_input_selectors", SELECTOR_PATH)
SELECTORS = importlib.util.module_from_spec(SELECTOR_SPEC)
SELECTOR_SPEC.loader.exec_module(SELECTORS)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    requested = sys.argv[1:]
    directory = Path(os.environ["A01_KTEST_GUESTS"]).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    index = 1
    while True:
        guest = directory / f"guest-{index:03d}"
        try:
            guest.mkdir()
            break
        except FileExistsError:
            index += 1
    record = {"schema": 1, "crate": os.environ["A01_KTEST_CRATE"], "cwd": os.getcwd(),
              "requested_osdk_args": requested,
              "profile": {"arch": "x86_64", "machine": "q35", "accel": "tcg", "cpu": "max",
                          "vcpus": 1, "memory_mib": 512, "network": False, "data_disks": False},
              "input_selector_source": {"path": str(SELECTOR_PATH), "sha256": digest(SELECTOR_PATH)},
              "artifacts": {}, "raw_exit_code": None, "timed_out": False,
              "timeout_requested": os.environ.get("A01_KTEST_TIMEOUT", "300"),
              "timeout_seconds": None,
              "stage": "artifact_preparation"}
    destination = guest / "qemu.json"
    try:
        timeout = int(record["timeout_requested"])
        if timeout <= 0 or not math.isfinite(timeout):
            raise ValueError("A01_KTEST_TIMEOUT must be a finite positive integer")
        record["timeout_seconds"] = timeout
        arguments = []
        for option in ("-kernel", "-initrd", "-append"):
            positions = [i for i, item in enumerate(requested) if item == option]
            if len(positions) != (0 if option == "-initrd" and not positions else 1):
                raise ValueError(f"OSDK must provide a unique {option}")
            if not positions:
                continue
            index = positions[0] + 1
            if index == len(requested):
                raise ValueError(f"OSDK {option} requires a value")
            arguments.extend((option, requested[index]))
        arguments.extend(("-machine", "q35", "-accel", "tcg", "-cpu", "max",
                          "-bios", "/usr/share/seabios/bios-256k.bin",
                          "-m", "512M", "-smp", "1", "-nodefaults", "-no-user-config", "-no-reboot",
                          "-nographic", "-display", "none", "-monitor", "none", "-serial", "chardev:serial",
                          "-chardev", f"stdio,id=serial,signal=off,logfile={guest / 'serial.log'}",
                          "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"))
        record["requested_fixed_qemu_args"] = list(arguments)
        arguments = SELECTORS.select_bios(arguments, {"-bios": arguments.index("-bios") + 1}, record)
        if "A01_QEMU_DATA_DIR" in os.environ and "-L" in requested:
            # Reject ambiguity using the shared policy before discarding other OSDK options.
            SELECTORS.select_data_directory(requested, record)
        arguments = SELECTORS.select_data_directory(arguments, record)
        binary = shutil.which("qemu-system-x86_64")
        if not binary:
            raise ValueError("qemu-system-x86_64 is not installed")
        command = [binary, *arguments]
        for option in ("-kernel", "-initrd", "-bios"):
            if option in arguments:
                path = Path(arguments[arguments.index(option) + 1]).resolve()
                record["artifacts"][option] = {"path": str(path), **SELECTORS.capture_artifact(path)}
        record.update(argv=command, shell_command=shlex.join(command), qemu_sha256=digest(Path(binary)),
                      qemu_version=subprocess.check_output([binary, "--version"], text=True).strip())
    except (OSError, ValueError, OverflowError, subprocess.SubprocessError) as error:
        record.update(stage="artifact_preparation_failed", error=str(error), recorder_exit_code=1)
        destination.write_text(json.dumps(record, indent=2) + "\n")
        print(f"ktest QEMU input preparation rejected: {error}", file=sys.stderr)
        return 1
    record["stage"] = "qemu_running"
    destination.write_text(json.dumps(record, indent=2) + "\n")
    started = time.monotonic()
    try:
        result = subprocess.run(command, timeout=timeout)
        record["raw_exit_code"] = result.returncode
    except subprocess.TimeoutExpired:
        record["raw_exit_code"], record["timed_out"] = 124, True
    except OSError as error:
        record.update(stage="qemu_failed", error=str(error), recorder_exit_code=1)
        destination.write_text(json.dumps(record, indent=2) + "\n")
        return 1
    record["duration_seconds"] = round(time.monotonic() - started, 3)
    serial = guest / "serial.log"
    if serial.exists():
        record["serial_sha256"] = digest(serial)
    status = record["raw_exit_code"]
    record.update(stage="complete", recorder_exit_code=status if status >= 0 else 128 - status)
    destination.write_text(json.dumps(record, indent=2) + "\n")
    return record["recorder_exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
