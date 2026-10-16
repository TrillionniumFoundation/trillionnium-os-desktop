#!/usr/bin/env python3
"""Replay pinned A01 ELF with a guest-only cgroup diagnostic. No host cgroup writes.
A NOT_ENFORCED observation is a failed resource capability, not a passing OS test.
This does not build a kernel, alter a system disk, or attach host networking.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time

A01 = "b14e46105cd892f5e1186a46f1dcfc1ae270420a"
ELF_SHA = "e884f5e50cf296833276016894a39337cd9ac13bc51f6b1f2dea3cc3a6904b63"
INITRD_SHA = "86be65ab9234cd20ea6ec8d44a12b8765fd7a3e241fde920c71b3621ca0047f3"
BIOS_SHA = "1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735"

def sha(data):
    return hashlib.sha256(data).hexdigest()

def require(ok, message):
    if not ok:
        raise ValueError(message)

def unpack(data):
    """Parse bounded newc into memory; never extract archive paths on the host."""
    require(len(data) <= 16 * 1024 * 1024, "archive exceeds limit")
    entries = []
    pos = 0
    seen = set()
    while True:
        require(pos + 110 <= len(data), "truncated cpio header")
        head = data[pos:pos + 110]
        require(head[:6] == b"070701", "newc expected")
        fields = [int(head[6 + i*8:14 + i*8], 16) for i in range(13)]
        namesize, size = fields[11], fields[6]
        require(1 <= namesize <= 4096, "invalid name length")
        start = pos + 110
        raw = data[start:start + namesize]
        require(len(raw) == namesize and raw[-1:] == b"\0", "truncated name")
        name = raw[:-1].decode("utf-8")
        require(name not in seen, "duplicate archive name")
        seen.add(name)
        start = (start + namesize + 3) & ~3
        require(start + size <= len(data), "truncated file")
        if name == "TRAILER!!!":
            require(size == 0, "bad trailer")
            break
        require(".." not in name.split("/"), "unsafe archive name")
        entries.append((name, fields, data[start:start + size]))
        pos = (start + size + 3) & ~3
    return entries

def pack(entries):
    result = bytearray()
    trailer = [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 11, 0]
    for name, values, content in list(entries) + [("TRAILER!!!", trailer, b"")]:
        fields = list(values)
        raw = name.encode() + b"\0"
        fields[6], fields[11] = len(content), len(raw)
        result += b"070701" + b"".join(f"{x:08x}".encode() for x in fields)
        result += raw
        result += b"\0" * (-len(result) % 4)
        result += content
        result += b"\0" * (-len(result) % 4)
    return bytes(result)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--a01-tree", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--qemu", default="/usr/bin/qemu-system-x86_64")
    ap.add_argument("--bios", type=Path, default=Path("/usr/share/seabios/bios-256k.bin"))
    args = ap.parse_args()
    a01, out = args.a01_tree.resolve(), args.output.resolve()
    require(not out.exists(), "output must be a new directory")
    commit = subprocess.check_output(["git", "-C", str(a01), "rev-parse", "HEAD"], text=True).strip()
    require(commit == A01, "unexpected A01 commit")
    artifacts = a01 / "support/build/evidence/2026-10-16/artifacts"
    elf = gzip.decompress((artifacts / "kernel.elf.gz").read_bytes())
    original = (artifacts / "initramfs.cpio.gz").read_bytes()
    require(sha(elf) == ELF_SHA, "kernel hash mismatch")
    require(sha(original) == INITRD_SHA, "initramfs hash mismatch")
    require(sha(args.bios.read_bytes()) == BIOS_SHA, "firmware hash mismatch")
    out.mkdir(parents=True)
    c = Path(__file__).with_name("cpu_cap_probe.c").resolve()
    compile_argv = ["cc", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-static", str(c), "-o", str(out / "cpu-cap-probe")]
    cp = subprocess.run(compile_argv, capture_output=True, text=True, timeout=30)
    (out / "compile.log").write_text(cp.stdout + cp.stderr)
    require(cp.returncode == 0, "probe compile failed; see compile.log")
    entries = unpack(gzip.decompress(original))
    require(unpack(pack(entries)) == entries, "cpio roundtrip mismatch")
    marker = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
    changed = 0
    new_entries = []
    for name, fields, content in entries:
        if name.lstrip("./") == "init":
            require(content.count(marker) == 1, "unexpected init script")
            content = content.replace(marker, b'/bin/cpu-cap-probe --asterinas-disposable-guest\n' + marker)
            changed += 1
        new_entries.append((name, fields, content))
    require(changed == 1, "missing init")
    fields = [max(e[1][0] for e in entries) + 1, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
    new_entries.append(("bin/cpu-cap-probe", fields, (out / "cpu-cap-probe").read_bytes()))
    marker_fields = [fields[0] + 1, 0o100400, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
    new_entries.append((".hepta-disposable-guest", marker_fields, (ELF_SHA + "\n").encode()))
    initrd = gzip.compress(pack(new_entries), mtime=0)
    (out / "kernel.elf").write_bytes(elf)
    (out / "initramfs.cpio.gz").write_bytes(initrd)
    argv = [args.qemu, "-kernel", str(out / "kernel.elf"), "-initrd", str(out / "initramfs.cpio.gz"),
        "-append", "earlycon console=ttyS0 loglevel=info SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --",
        "-machine", "q35", "-accel", "tcg", "-cpu", "max", "-bios", str(args.bios), "-m", "512M", "-smp", "1",
        "-nodefaults", "-no-user-config", "-no-reboot", "-nographic", "-display", "none", "-monitor", "none",
        "-serial", "stdio", "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"]
    started = time.monotonic()
    try:
        run = subprocess.run(argv, capture_output=True, text=True, timeout=45)
        raw, code, timed_out = run.stdout + run.stderr, run.returncode, False
    except subprocess.TimeoutExpired as exc:
        raw = (exc.stdout or b"").decode(errors="replace") + (exc.stderr or b"").decode(errors="replace")
        code, timed_out = None, True
    (out / "serial.log").write_text(raw)
    clean = re.sub(r"\x1b\[[0-9;]*m", "", raw)
    sample_re = r"ORGAN_CPU_SAMPLE label=(\S+) wall_ns=(\d+) cpu_ns=(\d+) iterations=(\d+) checksum=(\d+)"
    samples = [{"label": m[0], "wall_ns": int(m[1]), "cpu_ns": int(m[2]), "iterations": int(m[3]), "checksum": int(m[4])} for m in re.findall(sample_re, clean)]
    result = {"a01_commit": A01, "kernel_sha256": ELF_SHA, "original_initrd_sha256": INITRD_SHA,
        "diagnostic_initrd_sha256": sha(initrd), "probe_source_sha256": sha(c.read_bytes()), "probe_elf_sha256": sha((out/"cpu-cap-probe").read_bytes()),
        "argv": argv, "compile_argv": compile_argv, "qemu_exit": code, "timed_out": timed_out,
        "elapsed_host_seconds": time.monotonic()-started, "samples": samples,
        "guest_complete": "ORGAN_PROBE_COMPLETE" in clean and "TRILLIONNIUM_A01_BOOT_OK" in clean and code == 33,
        "observed_not_enforced": "ORGAN_CPU_VERDICT=NOT_ENFORCED" in clean,
        "kernel_source_built_here": False, "kernel_modified": False, "hos2_implemented": False,
        "host_cgroup_modified": False, "qualification_passed": False}
    (out/"result.json").write_text(json.dumps(result, indent=2)+"\n")
    print(json.dumps(result, indent=2))
    for line in clean.splitlines():
        if line.startswith("ORGAN_") or "not enforced yet" in line:
            print(line)
    return 0 if result["guest_complete"] else 2

if __name__ == "__main__":
    raise SystemExit(main())
