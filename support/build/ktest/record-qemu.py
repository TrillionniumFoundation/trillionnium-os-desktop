#!/usr/bin/env python3
"""Run each OSDK ktest guest with an isolated log and a fixed QEMU profile."""
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import sys
import time


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    requested = sys.argv[1:]
    profile = os.environ.get("A01_KTEST_PROFILE", "default")
    crate = os.environ["A01_KTEST_CRATE"]
    test_name = os.environ.get("A01_KTEST_TEST_NAME") or None
    if crate not in ("ostd", "aster-core", "osdk-frame-allocator", "aster-mlsdisk", "aster-block"):
        raise SystemExit("unknown kernel-test crate")
    if profile not in ("default", "permission-attr-smp"):
        raise SystemExit("unknown fixed kernel-test profile")
    if crate in ("osdk-frame-allocator", "aster-mlsdisk", "aster-block") and (profile != "default" or test_name is not None):
        raise SystemExit(f"{crate} requires its complete unfiltered default N0 suite")
    vcpus = 2 if profile == "permission-attr-smp" else 1
    if profile == "permission-attr-smp" and os.environ["A01_KTEST_CRATE"] != "aster-core":
        raise SystemExit("the permission SMP profile is restricted to aster-core")
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
    binary = shutil.which("qemu-system-x86_64")
    if not binary:
        raise SystemExit("qemu-system-x86_64 is not installed")
    command = [binary]
    artifacts = {}
    for option in ("-kernel", "-initrd", "-append"):
        positions = [i for i, item in enumerate(requested) if item == option]
        if len(positions) != (0 if option == "-initrd" and not positions else 1):
            raise SystemExit(f"OSDK must provide a unique {option}")
        if not positions:
            continue
        value = requested[positions[0] + 1]
        if option != "-append":
            path = Path(value).resolve()
            # Invoke the exact path whose bytes are recorded. OSDK's target may
            # be a symlink to an isolated build cache; retain its requested
            # spelling separately, without making the actual receipt ambiguous.
            value = str(path)
            artifacts[option] = {"path": str(path), "size": path.stat().st_size,
                                 "sha256": digest(path)}
        command.extend((option, value))
    firmware = Path("/usr/share/seabios/bios-256k.bin")
    artifacts["-bios"] = {"path": str(firmware), "size": firmware.stat().st_size,
                           "sha256": digest(firmware)}
    command.extend(("-machine", "q35", "-accel", "tcg", "-cpu", "max", "-bios", str(firmware),
                    "-m", "512M", "-smp", str(vcpus), "-nodefaults", "-no-user-config", "-no-reboot",
                    "-nographic", "-display", "none", "-monitor", "none", "-serial", "chardev:serial",
                    "-chardev", f"stdio,id=serial,signal=off,logfile={guest / 'serial.log'}",
                    "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"))
    record = {"schema": 1, "crate": crate, "cwd": os.getcwd(), "test_name": test_name,
              "ktest_profile": profile,
              "requested_osdk_args": requested, "argv": command, "shell_command": shlex.join(command),
              "profile": {"arch": "x86_64", "machine": "q35", "accel": "tcg", "cpu": "max",
                          "vcpus": vcpus, "memory_mib": 512, "network": False, "data_disks": False},
              "qemu_sha256": digest(Path(binary)),
              "qemu_version": subprocess.check_output([binary, "--version"], text=True).strip(),
              "artifacts": artifacts, "raw_exit_code": None, "timed_out": False}
    destination = guest / "qemu.json"
    destination.write_text(json.dumps(record, indent=2) + "\n")
    started = time.monotonic()
    try:
        result = subprocess.run(command, timeout=int(os.environ.get("A01_KTEST_TIMEOUT", "300")))
        record["raw_exit_code"] = result.returncode
    except subprocess.TimeoutExpired:
        record["raw_exit_code"], record["timed_out"] = 124, True
    record["duration_seconds"] = round(time.monotonic() - started, 3)
    serial = guest / "serial.log"
    if serial.exists():
        record["serial_sha256"] = digest(serial)
    destination.write_text(json.dumps(record, indent=2) + "\n")
    status = record["raw_exit_code"]
    return status if status >= 0 else 128 - status


if __name__ == "__main__":
    raise SystemExit(main())
