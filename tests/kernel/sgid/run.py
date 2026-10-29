#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Run actual ramfs/tmpfs/ext2 SGID creation probes on an exact ordinary kernel.

The sole disk is a fresh owned 64 MiB ext2 fixture. No host block device or
network is attached. Kernel artifacts are reused only after exact-source checks.
"""
import argparse
import importlib.util
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


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


safety = module("sgid_safety", HERE.parent / "safety/run.py")
persistence = module("sgid_fixture", HERE.parent / "native-persistence/run.py")
safety.PROBES = ("sgid",)
safety.PROBE_ARGS = {}


def execute(args, output, result):
    before = safety.snapshot()
    safety.save(output / "source-before.json", before)
    tree = subprocess.check_output(["git", "rev-parse", "HEAD^{tree}"], cwd=safety.ROOT, text=True).strip()
    artifacts, qemu_hash, provenance = safety.load_product(args.product_evidence.resolve(), before["head"], tree)
    result.update(provenance)
    cc = Path("/usr/bin/gcc")
    source = HERE / "probe.c"
    source_bytes = source.read_bytes()
    command = [str(cc), "-static", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread", str(source), "-o", str(output / "probe")]
    persistence.run_checked(command, output / "compile.log", timeout=60)
    probe = (output / "probe").read_bytes()
    disk, disk_record = persistence.fixture(output)
    nonce = secrets.token_hex(16)
    retained = {"kernel.elf": artifacts["-kernel"], "bios.bin": artifacts["-bios"],
                "initramfs.cpio.gz": safety.initramfs(artifacts["-initrd"], {"sgid": probe}, nonce, args.smp)}
    for name, content in retained.items():
        (output / name).write_bytes(content)
    binary = Path(shutil.which("qemu-system-x86_64") or "missing")
    safety.require(binary.is_file() and persistence.file_digest(binary) == qemu_hash, "QEMU differs from exact product")
    safety.require("," not in str(disk), "QEMU disk path contains comma")
    argv = [str(binary), "-kernel", str(output / "kernel.elf"), "-initrd", str(output / "initramfs.cpio.gz"),
            "-append", "earlycon console=ttyS0 loglevel=warn SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --",
            "-machine", "q35", "-accel", "tcg", "-cpu", "max", "-bios", str(output / "bios.bin"),
            "-m", "512M", "-smp", str(args.smp), "-nodefaults", "-no-user-config", "-no-reboot", "-nographic",
            "-display", "none", "-monitor", "none", "-serial", "stdio", "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04",
            "-drive", f"file={disk},if=none,format=raw,id=sgid-fixture,snapshot=off,cache=writeback",
            "-device", "virtio-blk-pci,disable-legacy=on,disable-modern=off,drive=sgid-fixture"]
    result.update(stage="guest", nonce=nonce, qemu_argv=argv, qemu_sha256=qemu_hash, fixture=disk_record,
                  artifact_sha256={n: safety.digest(d) for n, d in retained.items()},
                  probe_sha256=safety.digest(probe), probe_source_sha256=safety.digest(source_bytes), compiler_argv=command)
    safety.save(output / "result.json", result)
    raw, code, timeout, excessive, elapsed = safety.run_qemu(argv, output, args.timeout)
    text = raw.decode(errors="replace").replace("\r", "")
    rows = [json.loads(line) for line in text.splitlines() if line.startswith('{')]
    checks = [row for row in rows if "case" in row]
    final = safety.snapshot()
    safety.save(output / "source-after-guest.json", final)
    unchanged = (before == final and source.read_bytes() == source_bytes
                 and all((output / n).read_bytes() == d for n, d in retained.items())
                 and (output / "probe").read_bytes() == probe and persistence.file_digest(binary) == qemu_hash
                 and persistence.identity(disk) == disk_record["identity"])
    passed = (unchanged and code == 33 and not timeout and not excessive
              and text.count(f"HEPTA_SAFETY nonce={nonce} probe=sgid exit=0") == 1
              and len(checks) == 130 and all(r.get("passed") is True for r in checks)
              and '"passed":false' not in text)
    result.update(stage="complete", passed=passed, qemu_exit=code, timed_out=timeout, excessive_output=excessive,
                  elapsed_seconds=elapsed, assertions=len(checks), passed_assertions=sum(r.get("passed") is True for r in checks),
                  source_unchanged=before == final, artifacts_unchanged=unchanged,
                  serial_sha256=safety.digest(raw), disk_final_sha256=persistence.file_digest(disk))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--product-evidence", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--smp", choices=(2, 4), type=int, default=2)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    safety.require(1 <= args.timeout <= 120, "timeout must be 1..120 seconds")
    output = args.output.absolute()
    safety.require(not output.exists() and not output.is_symlink(), "output must be new")
    safety.require(not output.resolve().is_relative_to(ROOT), "evidence must be outside source")
    output.mkdir(parents=True, mode=0o700)
    result = {"schema": "hepta.inode-sgid-guest.v1", "passed": False, "stage": "prepare",
              "production_qualified": False, "original_owner_qualified": False, "cross_boot_qualified": False}
    try:
        execute(args, output, result)
    except Exception as error:
        result["error"] = f"{type(error).__name__}: {error}"
    safety.save(output / "result.json", result)
    print(json.dumps(result, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
