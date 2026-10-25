#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Actual user-page-table, VMO and ext2 cache budget checks in a disposable SMP QEMU guest.

The only disk is a generated 16 MiB fixture with snapshot writes. No host
block devices, personal data or network are exposed to the guest. Results are
working-byte development evidence, not a full memory.max qualification.
"""
import argparse
import gzip
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "safety"))
from run import BOOT_MARKER, digest, pack, require, run_qemu, save, snapshot, unpack


def inject(original, binary, nonce, smp):
    entries = unpack(gzip.decompress(original))
    script = ("if /bin/page-memory-probe; then result=0; else result=$?; fi\n"
              f'echo "HEPTA_PAGE_MEMORY nonce={nonce} exit=$result"\n').encode()
    found = 0
    for index, (name, fields, data) in enumerate(entries):
        if name.lstrip("./") != "init":
            continue
        require(data.count(BOOT_MARKER) == 1 and data.count(b'test "$cpu_count" -eq 1') == 1,
                "ambiguous original ordinary init")
        data = data.replace(b'test "$cpu_count" -eq 1', f'test "$cpu_count" -eq {smp}'.encode())
        entries[index] = (name, fields, data.replace(BOOT_MARKER, script + BOOT_MARKER))
        found += 1
    require(found == 1, "ordinary init missing")
    inode = max(fields[0] for _, fields, _ in entries) + 1
    entries.append(("bin/page-memory-probe", [inode, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0], binary))
    encoded = pack(entries)
    require([(n, d) for n, _, d in unpack(encoded)] == [(n, d) for n, _, d in entries], "cpio roundtrip failed")
    return gzip.compress(encoded, mtime=0)


def run_checked(argv, log, **kwargs):
    with log.open("wb") as output:
        process = subprocess.run(argv, stdout=output, stderr=subprocess.STDOUT, **kwargs)
    require(process.returncode == 0, f"command failed; see {log}")


def prepare_fixture(output):
    tool = Path("/usr/sbin/mke2fs")
    require(tool.is_file(), "system mke2fs is required")
    seed = output / "fixture-inputs"
    seed.mkdir()
    (seed / "cold.bin").write_bytes(b"1" * (64 * 4096))
    (seed / "denied.bin").write_bytes(b"2" * 4096)
    disk = output / "fixture.ext2"
    with disk.open("wb") as stream:
        stream.truncate(16 * 1024 * 1024)
    argv = [str(tool), "-q", "-F", "-t", "ext2", "-b", "4096", "-I", "128",
            "-O", "none,filetype,sparse_super,large_file", "-d", str(seed), str(disk)]
    run_checked(argv, output / "fixture.log", timeout=30)
    return disk, {"argv": argv, "tool_sha256": digest(tool.read_bytes()),
                  "disk_sha256": digest(disk.read_bytes()), "snapshot_writes": True,
                  "seed_sha256": {p.name: digest(p.read_bytes()) for p in seed.iterdir()}}


def ordinary(output, before, reuse):
    names = {"-kernel": "kernel.elf", "-bios": "bios.bin", "-initrd": "ordinary-initramfs.cpio.gz"}
    if reuse:
        receipt = json.loads((reuse / "result.json").read_text())
        require(receipt.get("schema") == "hepta.page-memory-guest.v1"
                and receipt.get("passed") is True and receipt.get("source_unchanged") is True,
                "cannot reuse failed, unknown or drifting page-memory run")
        raw = (reuse / "serial.log").read_bytes()
        require(guest_passed(raw, receipt["nonce"], receipt["qemu_exit"], receipt["timed_out"], receipt["excessive_output"])
                and digest(raw) == receipt["serial_sha256"], "reused guest serial is invalid or changed")
        require(digest((reuse / "initramfs.cpio.gz").read_bytes()) == receipt["initramfs_sha256"]
                and digest((reuse / "probe").read_bytes()) == receipt["probe_sha256"], "reused guest input changed")
        for name in ("source-before.json", "source-after.json"):
            require(json.loads((reuse / name).read_text()) == before, "reused working source differs")
        artifacts = {key: (reuse / name).read_bytes() for key, name in names.items()}
        for key, name in names.items():
            require(digest(artifacts[key]) == receipt["ordinary_sha256"][name], "reused artifact changed")
        return artifacts, {"reuse": str(reuse), "receipt_sha256": digest((reuse / "result.json").read_bytes()), "qemu_sha256": receipt["qemu_sha256"]}
    env = dict(os.environ, A01_RUN_DIR=str(output / "ordinary-boot"), A01_QEMU_TIMEOUT="120", A01_SMP="1")
    for key in ("HEPTA_G1C_TRUSTED_OBSERVE", "HEPTA_G1D_TRUSTED_CONTROL", "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS"):
        env.pop(key, None)
    run_checked([str(ROOT / "support/build/kernel.sh"), "run_kernel"], output / "build.log", cwd=ROOT, env=env)
    require(snapshot() == before, "working source changed during ordinary build")
    qemu = json.loads((output / "ordinary-boot/qemu.json").read_text())
    argv = qemu["argv"]
    artifacts = {key: (Path(qemu["cwd"]) / argv[argv.index(key) + 1]).read_bytes() for key in names}
    return artifacts, {"reuse": None}


def guest_passed(raw, nonce, code, timeout, excessive):
    serial = raw.decode(errors="replace").replace("\r", "")
    return (code == 33 and not timeout and not excessive
            and serial.count(f"HEPTA_PAGE_MEMORY nonce={nonce} exit=0") == 1
            and '"passed":false' not in serial)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--smp", type=int, choices=(2, 4), default=2)
    parser.add_argument("--reuse", type=Path, help="prior successful same-working-source run; no rebuild")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    result = {"schema": "hepta.page-memory-guest.v1", "passed": False, "production_qualified": False, "scope": "private-vmo-cache-and-user-page-table-pages", "smp": args.smp}
    save(output / "result.json", result)
    before = snapshot()
    save(output / "source-before.json", before)
    run_checked(["/usr/bin/gcc-13", "-static", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror",
                 str(HERE / "probe.c"), "-o", str(output / "probe")], output / "compile.log", timeout=60)
    binary = (output / "probe").read_bytes()
    disk, fixture = prepare_fixture(output)
    artifacts, provenance = ordinary(output, before, args.reuse.resolve() if args.reuse else None)
    names = {"-kernel": "kernel.elf", "-bios": "bios.bin", "-initrd": "ordinary-initramfs.cpio.gz"}
    for key, name in names.items():
        (output / name).write_bytes(artifacts[key])
    nonce = secrets.token_hex(16)
    initrd = inject(artifacts["-initrd"], binary, nonce, args.smp)
    (output / "initramfs.cpio.gz").write_bytes(initrd)
    qemu = Path(shutil.which("qemu-system-x86_64") or "missing")
    require(qemu.is_file(), "QEMU missing")
    require(provenance.get("qemu_sha256", digest(qemu.read_bytes())) == digest(qemu.read_bytes()), "reused QEMU changed")
    require("," not in str(disk), "QEMU fixture path cannot contain a comma")
    argv = [str(qemu), "-kernel", str(output / "kernel.elf"), "-initrd", str(output / "initramfs.cpio.gz"),
            "-append", "earlycon console=ttyS0 loglevel=warn SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --",
            "-machine", "q35", "-accel", "tcg", "-cpu", "max", "-bios", str(output / "bios.bin"),
            "-m", "512M", "-smp", str(args.smp), "-nodefaults", "-no-user-config", "-no-reboot", "-nographic",
            "-display", "none", "-monitor", "none", "-serial", "stdio",
            "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04",
            "-drive", f"file={disk},if=none,format=raw,id=page-cache,snapshot=on",
            "-device", "virtio-blk-pci,disable-legacy=on,drive=page-cache"]
    result.update(nonce=nonce, source_kind=before["kind"], provenance=provenance, fixture=fixture,
                  ordinary_sha256={names[key]: digest(data) for key, data in artifacts.items()},
                  initramfs_sha256=digest(initrd), probe_sha256=digest(binary),
                  qemu_sha256=digest(qemu.read_bytes()), qemu_argv=argv)
    save(output / "result.json", result)
    raw, code, timeout, excessive, elapsed = run_qemu(argv, output, 180)
    serial = raw.decode(errors="replace").replace("\r", "")
    after = snapshot()
    save(output / "source-after.json", after)
    unchanged = before == after
    artifact_ok = (all(digest((output / name).read_bytes()) == result["ordinary_sha256"][name] for name in names.values())
                   and digest(disk.read_bytes()) == fixture["disk_sha256"]
                   and (output / "initramfs.cpio.gz").read_bytes() == initrd)
    passed = unchanged and artifact_ok and guest_passed(raw, nonce, code, timeout, excessive)
    result.update(passed=passed, qemu_exit=code, timed_out=timeout, excessive_output=excessive,
                  source_unchanged=unchanged, artifact_unchanged=artifact_ok, elapsed_seconds=elapsed,
                  assertions=serial.count('"passed":true'), failed_assertions=serial.count('"passed":false'),
                  serial_sha256=digest(raw))
    save(output / "result.json", result)
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
