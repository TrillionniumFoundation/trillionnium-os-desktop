#!/usr/bin/env python3
"""Record the exact kernel invocation and raw QEMU exit code for the smoke run."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import subprocess
import sys
import time


def inherit_gdb_listener(arguments, descriptor):
    """Keep the driver's listening socket owned across the QEMU exec."""
    descriptor = int(descriptor)
    if descriptor < 64:
        raise ValueError("GDB listener descriptor must avoid shell-reserved descriptors")
    with socket.socket(fileno=os.dup(descriptor)) as listener:
        if listener.family != socket.AF_INET:
            raise ValueError("GDB descriptor must be an IPv4 loopback socket")
        address = listener.getsockname()
        if address[0] != "127.0.0.1" \
                or listener.getsockopt(socket.SOL_SOCKET, socket.SO_ACCEPTCONN) != 1:
            raise ValueError("GDB descriptor must be a listening IPv4 loopback socket")
    positions = [i for i, value in enumerate(arguments) if value == "-gdb"]
    expected = f"tcp:127.0.0.1:{address[1]}"
    if len(positions) != 1 or positions[0] + 1 == len(arguments) \
            or arguments[positions[0] + 1] != expected or "-S" not in arguments:
        raise ValueError("GDB request must match the owned listener and pause at startup")
    identifier = "a01-kernel-gdb"
    if any(identifier in value for value in arguments):
        raise ValueError("reserved GDB chardev id already exists")
    actual = list(arguments)
    actual[positions[0] + 1] = "chardev:" + identifier
    actual += ["-chardev", f"socket,id={identifier},fd={descriptor},server=on,wait=off"]
    return actual, (descriptor,), {"fd": descriptor, "address": list(address),
                                  "ownership": "inherited listening FD; no port rebind"}


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
    requested = sys.argv[1:]
    arguments, inherited, gdb_listener = requested, (), None
    if "A01_GDB_FD" in os.environ:
        arguments, inherited, gdb_listener = inherit_gdb_listener(requested, os.environ["A01_GDB_FD"])
    command = [binary, *arguments]
    destination = Path(os.environ["A01_QEMU_EVIDENCE"])
    record = {"argv": command, "shell_command": shlex.join(command),
              "cwd": os.getcwd(), "qemu_sha256": hashlib.sha256(Path(binary).read_bytes()).hexdigest(),
              "qemu_version": subprocess.check_output([binary, "--version"], text=True).strip(),
              "artifacts": {}, "raw_exit_code": None, "timed_out": False}
    if gdb_listener is not None:
        record.update({"requested_qemu_args": requested, "gdb_listener": gdb_listener})
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
        with subprocess.Popen(command, pass_fds=inherited) as result:
            record["qemu_pid"] = result.pid
            destination.write_text(json.dumps(record, indent=2) + "\n")
            try:
                record["raw_exit_code"] = result.wait(timeout=int(os.environ.get("A01_QEMU_TIMEOUT", "300")))
            except subprocess.TimeoutExpired:
                result.kill()
                result.wait()
                raise
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
