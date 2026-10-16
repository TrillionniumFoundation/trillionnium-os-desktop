#!/usr/bin/env python3
"""Record the exact kernel invocation and raw QEMU exit code for the smoke run."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time


def serial_log_path(arguments, cwd):
    """Use the serial chardev's explicit logfile, or this profile's qemu.log."""
    serial_ids = set()
    logs = {}
    for index, option in enumerate(arguments[:-1]):
        value = arguments[index + 1]
        if option == "-serial" and value.startswith("chardev:"):
            serial_ids.add(value.removeprefix("chardev:"))
        elif option == "-chardev":
            fields = dict(part.split("=", 1) for part in value.split(",") if "=" in part)
            if "id" in fields and "logfile" in fields:
                logs[fields["id"]] = fields["logfile"]
    selected = {logs[serial_id] for serial_id in serial_ids if serial_id in logs}
    if serial_ids and len(selected) != 1:
        raise ValueError("serial chardev must identify one raw logfile")
    path = Path(next(iter(selected)) if selected else "qemu.log")
    return path if path.is_absolute() else cwd / path


def main():
    binary = shutil.which("qemu-system-x86_64")
    if not binary:
        raise SystemExit("qemu-system-x86_64 is not installed")
    command = [binary, *sys.argv[1:]]
    destination = Path(os.environ["A01_QEMU_EVIDENCE"])
    record = {"argv": command, "shell_command": shlex.join(command),
              "cwd": os.getcwd(), "qemu_sha256": hashlib.sha256(Path(binary).read_bytes()).hexdigest(),
              "qemu_version": subprocess.check_output([binary, "--version"], text=True).strip(),
              "artifacts": {}, "raw_exit_code": None, "timed_out": False}
    for option in ("-kernel", "-initrd", "-bios"):
        if option in command:
            path = Path(command[command.index(option) + 1])
            raw = path.read_bytes()
            record["artifacts"][option] = {"path": str(path), "size": len(raw),
                "sha256": hashlib.sha256(raw).hexdigest()}
    try:
        serial_path = serial_log_path(command, Path.cwd())
        record["serial_path"] = str(serial_path)
    except ValueError as error:
        serial_path = None
        record["serial_error"] = str(error)
    started = time.monotonic()
    destination.write_text(json.dumps(record, indent=2) + "\n")
    try:
        result = subprocess.run(command, timeout=int(os.environ.get("A01_QEMU_TIMEOUT", "300")))
        record["raw_exit_code"] = result.returncode
    except subprocess.TimeoutExpired:
        record["raw_exit_code"] = 124
        record["timed_out"] = True
    if serial_path is not None:
        try:
            raw_serial = serial_path.read_bytes()
            record["serial_sha256"] = hashlib.sha256(raw_serial).hexdigest()
            record["serial_size"] = len(raw_serial)
        except OSError as error:
            record["serial_error"] = str(error)
    record["duration_seconds"] = round(time.monotonic() - started, 3)
    destination.write_text(json.dumps(record, indent=2) + "\n")
    return record["raw_exit_code"] if record["raw_exit_code"] >= 0 else 128 - record["raw_exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
