#!/usr/bin/env python3
"""Require successful guest evidence independently of Python optimization."""
import json
from pathlib import Path
import sys


def main():
    path = Path(sys.argv[1])
    qemu = json.loads((path / "qemu.json").read_text())
    serial = (path / "serial.log").read_text(errors="replace")
    if qemu["raw_exit_code"] != 33 or qemu["timed_out"]:
        raise SystemExit("QEMU did not exit successfully")
    for marker in ("OSTD initialized. Preparing components.",
                   "TRILLIONNIUM_A01_INIT_BEGIN", "TRILLIONNIUM_A01_CPU_COUNT=1",
                   "Successfully booted.", "TRILLIONNIUM_A01_BOOT_OK"):
        if marker not in serial:
            raise SystemExit(f"missing guest marker: {marker}")
    if any(marker in serial for marker in ("panicked at", "Uncaught panic:")):
        raise SystemExit("guest kernel panic")
    print("PASS: fixed Rust kernel reached single-CPU initramfs and powered off (QEMU exit 33)")


if __name__ == "__main__":
    main()
