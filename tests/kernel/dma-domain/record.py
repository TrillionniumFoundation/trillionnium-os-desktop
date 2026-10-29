#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Fixed, diskless two-EDU OSTD hardware fixture, invoked by cargo-osdk."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def command(qemu, output, append, smp, iommu, snoop):
    argv = [str(qemu), "-kernel", str(output / "kernel.elf"), "-append", append,
            "-machine", "q35", "-accel", "tcg", "-cpu", "max", "-m", "512M", "-smp", str(smp),
            "-bios", str(output / "bios.bin"), "-nodefaults", "-no-user-config", "-no-reboot",
            "-nographic", "-display", "none", "-monitor", "none", "-serial", "stdio",
            "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04",
            "-device", "edu,addr=5,dma_mask=0xffffffffffffffff",
            "-device", "edu,addr=6,dma_mask=0xffffffffffffffff"]
    if iommu:
        argv += ["-device", f"intel-iommu,caching-mode=on,snoop-control={'on' if snoop else 'off'},device-iotlb=off,intremap=off,aw-bits=39"]
    return argv


def run_guest(kernel, append, output, smp, iommu, snoop=True):
    output.mkdir(exist_ok=False)
    qemu = Path(shutil.which("qemu-system-x86_64") or "missing").resolve()
    bios = Path("/usr/share/seabios/bios-256k.bin")
    shutil.copyfile(kernel, output / "kernel.elf")
    shutil.copyfile(bios, output / "bios.bin")
    argv = command(qemu, output, append, smp, iommu, snoop)
    record = {"schema":"hepta.dma-domain-guest.v1", "argv":argv, "smp":smp, "iommu":iommu,
              "snoop_control":snoop, "production_qualified":False, "kernel_sha256":sha(output / "kernel.elf"),
              "bios_sha256":sha(output / "bios.bin"), "qemu_sha256":sha(qemu), "timed_out":False}
    (output / "qemu.json").write_text(json.dumps(record,indent=2)+"\n")
    start = time.monotonic()
    with (output / "serial.log").open("wb") as log:
        try:
            result = subprocess.run(argv, stdout=log, stderr=subprocess.STDOUT, timeout=180)
            code = result.returncode
        except subprocess.TimeoutExpired:
            code = 124
            record["timed_out"] = True
    record.update(exit=code, elapsed_seconds=round(time.monotonic()-start,3), serial_sha256=sha(output / "serial.log"))
    record["artifacts_unchanged"] = (record["kernel_sha256"] == sha(output / "kernel.elf")
                                     and record["bios_sha256"] == sha(output / "bios.bin")
                                     and record["qemu_sha256"] == sha(qemu))
    (output / "qemu.json").write_text(json.dumps(record,indent=2)+"\n")
    return code


def main():
    args = sys.argv[1:]
    values = {}
    for option in ("-kernel", "-append"):
        if args.count(option) != 1:
            raise SystemExit("OSDK must provide unique kernel and command line")
        values[option] = args[args.index(option)+1]
    return run_guest(Path(values["-kernel"]).resolve(), values["-append"],
                     Path(os.environ["HEPTA_DMA_GUEST_DIR"]), int(os.environ["HEPTA_DMA_SMP"]), True)


if __name__ == "__main__":
    raise SystemExit(main())
