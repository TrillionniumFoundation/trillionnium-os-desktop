#!/usr/bin/env python3
"""Check the fixed boot profile and its complete recorded raw serial bytes."""
import argparse
import hashlib
import json
from pathlib import Path
import re

ANSI = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)")
MARKERS = (
    "OSTD initialized. Preparing components.",
    "TRILLIONNIUM_A01_INIT_BEGIN",
    "TRILLIONNIUM_A01_CPU_COUNT=1",
    "Successfully booted.",
    "TRILLIONNIUM_A01_BOOT_OK",
)
FATAL_PANICS = (
    "panicked at", "An uncaught panic occurred:", "Uncaught panic:",
    "unknown panic payload! (fatal panic handling error",
    "Non-resettable panic!", "The panic handler panicked",
    "Panicked in `PanicGuard`, aborting the system",
)
ARTIFACTS = ("-kernel", "-initrd", "-bios")


def check_boot(directory, live_artifacts=False):
    qemu = json.loads((directory / "qemu.json").read_text())
    raw_serial = (directory / "serial.log").read_bytes()
    serial_sha256 = hashlib.sha256(raw_serial).hexdigest()
    if not isinstance(qemu, dict) or qemu.get("serial_sha256") != serial_sha256:
        raise ValueError("raw serial log does not match the recorded SHA256")
    if "serial_size" in qemu and qemu["serial_size"] != len(raw_serial):
        raise ValueError("raw serial log size does not match the record")
    if type(qemu.get("raw_exit_code")) is not int or qemu["raw_exit_code"] != 33:
        raise ValueError("QEMU did not exit with raw successful status 33")
    if qemu.get("timed_out") is not False:
        raise ValueError("QEMU timed out or its timeout result is missing")
    artifacts = qemu.get("artifacts")
    if not isinstance(artifacts, dict):
        raise ValueError("missing recorded boot artifacts")
    for option in ARTIFACTS:
        artifact = artifacts.get(option)
        if (not isinstance(artifact, dict)
                or not isinstance(artifact.get("path"), str) or not artifact["path"]
                or type(artifact.get("size")) is not int or artifact["size"] < 0
                or not isinstance(artifact.get("sha256"), str)
                or re.fullmatch(r"[0-9a-f]{64}", artifact["sha256"]) is None):
            raise ValueError(f"missing or invalid artifact path/size/SHA256: {option}")
        if live_artifacts:
            path = Path(artifact["path"])
            if not path.is_absolute():
                cwd = qemu.get("cwd")
                if not isinstance(cwd, str) or not cwd:
                    raise ValueError("relative live artifact requires recorded QEMU cwd")
                path = Path(cwd) / path
            raw = path.read_bytes()
            if len(raw) != artifact["size"] or hashlib.sha256(raw).hexdigest() != artifact["sha256"]:
                raise ValueError(f"live artifact does not match the recorded size/SHA256: {option}")
    serial = ANSI.sub("", raw_serial.decode(errors="replace"))
    for marker in MARKERS:
        if marker not in serial:
            raise ValueError(f"missing guest marker: {marker}")
    if any(marker in serial for marker in FATAL_PANICS):
        raise ValueError("guest kernel panic")
    return {"passed": True, "serial_sha256": serial_sha256, "raw_qemu_exit": 33,
            "live_artifacts_checked": live_artifacts}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--live-artifacts", action="store_true",
                        help="also verify current kernel/initrd/BIOS paths; omit for archived evidence")
    args = parser.parse_args()
    try:
        check_boot(args.directory, args.live_artifacts)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit(f"boot evidence rejected: {error}") from error
    print("PASS: fixed Rust kernel reached single-CPU initramfs and powered off (QEMU exit 33)")


if __name__ == "__main__":
    main()
