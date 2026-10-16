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
            record["artifacts"][option] = {"path": str(path), "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    started = time.monotonic()
    destination.write_text(json.dumps(record, indent=2) + "\n")
    try:
        result = subprocess.run(command, timeout=int(os.environ.get("A01_QEMU_TIMEOUT", "300")))
        record["raw_exit_code"] = result.returncode
    except subprocess.TimeoutExpired:
        record["raw_exit_code"] = 124
        record["timed_out"] = True
    record["duration_seconds"] = round(time.monotonic() - started, 3)
    destination.write_text(json.dumps(record, indent=2) + "\n")
    return record["raw_exit_code"] if record["raw_exit_code"] >= 0 else 128 - record["raw_exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
