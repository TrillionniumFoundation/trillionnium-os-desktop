#!/usr/bin/env python3
"""Record genuine OSDK integration guests while fixing only host VM resources."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import threading
import time


FIRMWARE = Path("/usr/share/seabios/bios-256k.bin")
PROFILE = {"arch": "x86_64", "machine": "q35", "accel": "tcg", "cpu": "max",
           "vcpus": 1, "memory_mib": 512, "network": False, "data_disks": False,
           "firmware": str(FIRMWARE)}


def file_record(path):
    path = Path(path).resolve()
    with path.open("rb") as source:
        digest = hashlib.file_digest(source, "sha256").hexdigest()
    return {"path": str(path), "size": path.stat().st_size, "sha256": digest}


def qemu_options(value):
    """Split QEMU comma options, preserving its doubled-comma escape."""
    fields, current, index = [], [], 0
    while index < len(value):
        if value[index:index + 2] == ",,":
            current.append(",")
            index += 2
        elif value[index] == ",":
            fields.append("".join(current))
            current = []
            index += 1
        else:
            current.append(value[index])
            index += 1
    fields.append("".join(current))
    return fields


def transform_args(requested, guest, cwd):
    """Keep workload/debug/coverage semantics; replace resources and pflash."""
    fixed_values = {"-machine", "-M", "-accel", "-cpu", "-m", "-smp", "-bios",
                    "-display", "-vga"}
    fixed_flags = {"-enable-kvm", "-nographic", "-nodefaults", "-no-user-config"}
    forbidden_values = {"-net", "-netdev", "-nic", "-hda", "-hdb", "-hdc", "-hdd",
                        "-cdrom", "-fda", "-fdb", "-blockdev", "-pflash"}
    values = fixed_values | forbidden_values | {
        "-kernel", "-initrd", "-append", "-drive", "-device", "-chardev", "-serial",
        "-monitor", "-gdb", "-qmp", "-readconfig"}
    result, removed, logs, kernels = [], [], [], 0
    debug_exit, serial_present, stdio_present = False, False, False
    index = 0
    while index < len(requested):
        argument = requested[index]
        key = "-" + argument.lstrip("-") if argument.startswith("-") else argument
        if key in fixed_flags:
            removed.append([argument])
            index += 1
            continue
        if key not in values:
            result.append(argument)
            index += 1
            continue
        if index + 1 == len(requested):
            raise ValueError(f"QEMU option {argument} has no value")
        value = requested[index + 1]
        index += 2
        if key in fixed_values:
            removed.append([argument, value])
            continue
        if key in forbidden_values or key == "-readconfig":
            raise ValueError(f"QEMU profile forbids {argument}: {value}")
        fields = qemu_options(value)
        if key == "-drive":
            if "if=pflash" not in fields:
                raise ValueError(f"QEMU profile forbids a data/boot drive: {value}")
            removed.append([argument, value])
            continue
        if key == "-device":
            if fields[0].startswith(("virtio-net", "e1000", "rtl8139", "ne2k", "vmxnet",
                                     "virtio-blk", "virtio-scsi", "scsi-", "ide-", "nvme")):
                raise ValueError(f"QEMU profile forbids network/disk device: {value}")
            debug_exit |= fields[0] == "isa-debug-exit"
        if key == "-kernel":
            kernels += 1
        if key == "-serial":
            serial_present = True
        if key == "-chardev" and fields[0] == "stdio":
            if stdio_present:
                raise ValueError("multiple stdio chardevs are unsupported")
            stdio_present = True
            logfiles = [field.split("=", 1)[1] for field in fields if field.startswith("logfile=")]
            if len(logfiles) > 1:
                raise ValueError("stdio chardev has multiple logfiles")
            if logfiles:
                log = Path(logfiles[0])
                logs.append(log if log.is_absolute() else cwd / log)
            else:
                log = guest / "serial.log"
                value += ",logfile=" + str(log).replace(",", ",,")
                logs.append(log)
        result.extend((argument, value))
    if kernels != 1:
        raise ValueError("direct integration guest requires exactly one -kernel")
    if not stdio_present:
        # OSDK's templates normally provide their own mux; this is the plain
        # direct-boot fallback, with a distinct id so other chardevs survive.
        identifier = "a01-record-serial"
        if any(identifier in item for item in result):
            raise ValueError("reserved fallback serial chardev id is already used")
        log = guest / "serial.log"
        result.extend(("-chardev", "stdio,id=" + identifier + ",signal=off,logfile="
                       + str(log).replace(",", ",,")))
        logs.append(log)
        if serial_present:
            serial_positions = [i for i, item in enumerate(result) if item in ("-serial", "--serial")]
            if len(serial_positions) != 1 or result[serial_positions[0] + 1] not in ("stdio", "none"):
                raise ValueError("non-stdio serial backend cannot be replaced without changing semantics")
            result[serial_positions[0] + 1] = "chardev:" + identifier
        else:
            result.extend(("-serial", "chardev:" + identifier))
    if not debug_exit:
        result.extend(("-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"))
    result.extend(("-machine", "q35", "-accel", "tcg", "-cpu", "max", "-m", "512M",
                   "-smp", "1", "-bios", str(FIRMWARE), "-nodefaults", "-no-user-config",
                   "-display", "none"))
    return result, logs, removed


def reserve_guest(directory):
    directory.mkdir(parents=True, exist_ok=True)
    index = 1
    while True:
        guest = directory / f"guest-{index:03d}"
        try:
            guest.mkdir()
            return guest
        except FileExistsError:
            index += 1


def tee_stream(source, destination, sink, errors):
    """Drain one pipe in bounded chunks, retaining bytes if forwarding fails."""
    recording, forwarding = True, True
    try:
        while chunk := source.read1(65536):
            if recording:
                try:
                    destination.write(chunk)
                    destination.flush()
                except (OSError, ValueError) as error:
                    errors.append(f"recording {destination.name}: {error}")
                    recording = False
            if forwarding:
                try:
                    sink.write(chunk)
                    sink.flush()
                except (OSError, ValueError) as error:
                    errors.append(f"forwarding QEMU output: {error}")
                    forwarding = False
    except (OSError, ValueError) as error:
        errors.append(f"reading QEMU output: {error}")
    finally:
        source.close()


def main():
    requested, cwd = sys.argv[1:], Path.cwd()
    case = Path(os.environ["A01_OSDK_CASE_OUTPUT"]).resolve()
    guest = reserve_guest(case / "guests")
    destination = guest / "qemu.json"
    record = {"schema": 1, "cwd": str(cwd), "requested_osdk_args": requested,
              "profile": PROFILE, "raw_exit_code": None, "timed_out": False}
    started = time.monotonic()
    status = 125
    try:
        arguments, logs, removed = transform_args(requested, guest, cwd)
        binary = shutil.which("qemu-system-x86_64")
        if not binary:
            raise FileNotFoundError("qemu-system-x86_64 is not installed")
        command = [binary, *arguments]
        artifacts = {"-bios": file_record(FIRMWARE)}
        for option in ("-kernel", "-initrd"):
            positions = [i for i, item in enumerate(arguments) if item == option]
            if len(positions) > 1:
                raise ValueError(f"multiple QEMU {option} arguments")
            if positions:
                artifacts[option] = file_record(arguments[positions[0] + 1])
        timeout = int(os.environ.get("A01_OSDK_GUEST_TIMEOUT", "300"))
        if timeout <= 0:
            raise ValueError("A01_OSDK_GUEST_TIMEOUT must be positive")
        record.update({"argv": command, "shell_command": shlex.join(command),
                       "removed_profile_args": removed, "artifacts": artifacts,
                       "qemu": file_record(binary), "serial_sources": list(map(str, logs)),
                       "qemu_version": subprocess.check_output([binary, "--version"], text=True,
                                                               timeout=10).strip(),
                       "timeout_seconds": timeout})
        destination.write_text(json.dumps(record, indent=2) + "\n")
        stream_paths = {"stdout": guest / "qemu-stdout.log", "stderr": guest / "qemu-stderr.log"}
        stream_errors = []
        with stream_paths["stdout"].open("wb") as stdout_log, \
                stream_paths["stderr"].open("wb") as stderr_log, \
                subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE) as process:
            readers = [threading.Thread(target=tee_stream, args=(source, destination, sink, stream_errors))
                       for source, destination, sink in (
                           (process.stdout, stdout_log, sys.stdout.buffer),
                           (process.stderr, stderr_log, sys.stderr.buffer))]
            for reader in readers:
                reader.start()
            try:
                status = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
                status = 124
                record["timed_out"] = True
            finally:
                # Both pipes are drained concurrently while QEMU runs. Joining
                # only after wait/kill avoids either full pipe blocking QEMU.
                for reader in readers:
                    reader.join()
            record["raw_exit_code"] = process.returncode
        record["stream_logs"] = {name: file_record(path) for name, path in stream_paths.items()}
        if stream_errors:
            record["stream_errors"] = stream_errors
            status = 125
        snapshots = []
        for index, source in enumerate(logs):
            if source.exists():
                target = guest / ("serial.log" if index == 0 else f"serial-{index + 1}.log")
                if source.resolve() != target.resolve():
                    shutil.copyfile(source, target)
                snapshots.append(file_record(target))
        record["serial_logs"] = snapshots
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        status = 125
        record["error"] = f"{type(error).__name__}: {error}"
        print(record["error"], file=sys.stderr)
    record["wrapper_exit_code"] = status if status >= 0 else 128 - status
    record["duration_seconds"] = round(time.monotonic() - started, 3)
    destination.write_text(json.dumps(record, indent=2) + "\n")
    return record["wrapper_exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
