#!/usr/bin/env python3
"""Record the exact kernel invocation and raw QEMU exit code for the smoke run."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
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


ARTIFACT_NAMES = {"-kernel": "kernel.elf", "-initrd": "initramfs.cpio.gz", "-bios": "bios.bin"}


def file_state(info):
    return {name: getattr(info, "st_" + name) for name in
            ("dev", "ino", "mode", "size", "mtime_ns", "ctime_ns")}


def artifact_positions(arguments):
    positions = {}
    for option in ARTIFACT_NAMES:
        found = [index for index, value in enumerate(arguments) if value == option]
        if len(found) != 1:
            raise ValueError(f"{option} must occur exactly once")
        index = found[0] + 1
        if index == len(arguments) or not arguments[index] or arguments[index].startswith("-"):
            raise ValueError(f"{option} requires one explicit artifact path")
        positions[option] = index
    return positions


def capture_artifact(source, destination=None):
    """Read one stable regular-file FD; optionally create a new exclusive copy."""
    descriptor = os.open(source, os.O_RDONLY | os.O_NONBLOCK)
    try:
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode):
            raise ValueError(f"artifact source is not a regular file: {source}")
        state = file_state(before)
        if file_state(os.stat(source)) != state:
            raise ValueError(f"artifact source changed before capture: {source}")
        digest, size = hashlib.sha256(), 0
        output = None
        try:
            if destination is not None:
                output = Path(destination).open("xb")
            while True:
                chunk = os.read(descriptor, 1024 * 1024)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
                if output is not None:
                    output.write(chunk)
            if (file_state(os.fstat(descriptor)) != state or file_state(os.stat(source)) != state
                    or size != before.st_size):
                raise ValueError(f"artifact source changed during capture: {source}")
        finally:
            if output is not None:
                output.close()
        return {"size": size, "sha256": digest.hexdigest(), "stat": state}
    finally:
        os.close(descriptor)


def snapshot_arguments(arguments, destination, record):
    positions = artifact_positions(arguments)
    directory = Path(tempfile.mkdtemp(prefix="artifacts-", dir=destination.parent)).absolute()
    record["snapshot_directory"] = {"path": str(directory), "stat": file_state(directory.stat()),
                                    "ownership": "new private mkdtemp directory; retained as evidence"}
    actual = list(arguments)
    for option, index in positions.items():
        requested = arguments[index]
        source = Path(requested).absolute()
        target = directory / ARTIFACT_NAMES[option]
        captured = capture_artifact(source, target)
        target.chmod(0o400)
        copied = capture_artifact(target)
        if any(copied[key] != captured[key] for key in ("size", "sha256")):
            raise ValueError(f"artifact snapshot differs from captured source: {option}")
        record["artifacts"][option] = {"path": str(target), **copied,
            "source": {"requested_path": requested, "path": str(source), **captured},
            "creation": "exclusive xb; no overwrite or source-path fallback"}
        actual[index] = str(target)
    return actual


def verify_snapshots(artifacts):
    for option in ARTIFACT_NAMES:
        artifact = artifacts[option]
        current = capture_artifact(Path(artifact["path"]))
        if any(current[key] != artifact[key] for key in ("size", "sha256", "stat")):
            raise ValueError(f"artifact snapshot changed: {option}")


def main():
    requested = sys.argv[1:]
    destination = Path(os.environ["A01_QEMU_EVIDENCE"]).absolute()
    record = {"requested_qemu_args": requested, "cwd": os.getcwd(), "artifacts": {},
              "raw_exit_code": None, "timed_out": False, "stage": "artifact_preparation"}
    try:
        artifact_positions(requested)  # Reject malformed requests before even the version probe.
        binary = shutil.which("qemu-system-x86_64")
        if not binary:
            raise ValueError("qemu-system-x86_64 is not installed")
        arguments, inherited, gdb_listener = requested, (), None
        if "A01_GDB_FD" in os.environ:
            arguments, inherited, gdb_listener = inherit_gdb_listener(requested, os.environ["A01_GDB_FD"])
        arguments = snapshot_arguments(arguments, destination, record)
        command = [binary, *arguments]
        record.update(argv=command, shell_command=shlex.join(command),
                      qemu_sha256=hashlib.sha256(Path(binary).read_bytes()).hexdigest())
        if gdb_listener is not None:
            record["gdb_listener"] = gdb_listener
        record["qemu_version"] = subprocess.check_output([binary, "--version"], text=True).strip()
        verify_snapshots(record["artifacts"])
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        record.update(stage="artifact_preparation_failed", error=str(error), recorder_exit_code=1)
        destination.write_text(json.dumps(record, indent=2) + "\n")
        print(f"QEMU artifact preparation rejected: {error}", file=sys.stderr)
        return 1
    try:
        serial_path = serial_log_path(command, Path.cwd())
        record["serial_path"] = str(serial_path)
    except ValueError as error:
        serial_path = None
        record["serial_error"] = str(error)
    started = time.monotonic()
    record["stage"] = "qemu_running"
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
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        record.update(stage="qemu_failed", error=str(error))
    if serial_path is not None:
        try:
            raw_serial = serial_path.read_bytes()
            record["serial_sha256"] = hashlib.sha256(raw_serial).hexdigest()
            record["serial_size"] = len(raw_serial)
        except OSError as error:
            record["serial_error"] = str(error)
    record["duration_seconds"] = round(time.monotonic() - started, 3)
    status = record["raw_exit_code"]
    exit_code = 1 if status is None else status if status >= 0 else 128 - status
    try:
        verify_snapshots(record["artifacts"])
        if status is not None:
            record["stage"] = "complete"
    except (OSError, ValueError) as error:
        record.update(stage="artifact_verification_failed", error=str(error))
        print(f"QEMU artifact verification rejected: {error}", file=sys.stderr)
        exit_code = 1
    record["recorder_exit_code"] = exit_code
    destination.write_text(json.dumps(record, indent=2) + "\n")
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
