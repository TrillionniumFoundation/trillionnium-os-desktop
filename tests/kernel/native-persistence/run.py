#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Qualify an owned ext2 file across two real kernel boots and QEMU SIGKILL.

The disk is generated inside a fresh private evidence directory. No caller-
supplied disk, host block device, network, Root issuer or ledger is used.
This is VM/process-crash evidence, never a physical-power-loss claim.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import time
import uuid

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent / "safety"))
from run import BOOT_MARKER, digest, pack, require, save, snapshot, unpack

MAX_SERIAL = 2 * 1024 * 1024
DISK_BYTES = 64 * 1024 * 1024
UUID = r"[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}"
ENV = {"PATH": "/usr/bin:/bin", "LC_ALL": "C", "LANG": "C"}


def file_digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def identity(path):
    info = path.lstat()
    require(stat.S_ISREG(info.st_mode) and info.st_nlink == 1 and info.st_uid == os.getuid(),
            "fixture must remain an owned regular single-link file")
    return [info.st_dev, info.st_ino, info.st_size, stat.S_IMODE(info.st_mode)]


def run_checked(argv, log, **kwargs):
    with log.open("xb") as stream:
        result = subprocess.run(argv, stdout=stream, stderr=subprocess.STDOUT, **kwargs)
    require(result.returncode == 0, f"command failed; retained log: {log}")


def fixture(output):
    disk = output / "fixture.ext2"
    descriptor = os.open(disk, os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "wb") as stream:
        stream.truncate(DISK_BYTES)
    tool = Path("/usr/sbin/mke2fs")
    require(tool.is_file(), "system mke2fs unavailable")
    argv = [str(tool), "-q", "-F", "-t", "ext2", "-b", "4096", "-I", "128", "-m", "0",
            "-O", "none,filetype,sparse_super,large_file", "-E", "lazy_itable_init=0",
            "-U", str(uuid.uuid4()), str(disk)]
    run_checked(argv, output / "fixture-create.log", timeout=30)
    require(identity(disk)[2:] == [DISK_BYTES, 0o600], "fixture shape changed")
    return disk, {"path": str(disk), "creation_argv": argv, "mke2fs_sha256": file_digest(tool),
                  "identity": identity(disk), "before_sha256": file_digest(disk),
                  "snapshot": "off", "cache": "writeback", "host_block_device": False}


def ordinary(output, before):
    env = dict(os.environ, A01_RUN_DIR=str(output / "ordinary-boot"), A01_SMP="1", A01_QEMU_TIMEOUT="120")
    for key in ("HEPTA_G1C_TRUSTED_OBSERVE", "HEPTA_G1D_TRUSTED_CONTROL", "HEPTA_TRUSTED_INITIAL_ELF",
                "RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS"):
        env.pop(key, None)
    run_checked([str(ROOT / "support/build/kernel.sh"), "run_kernel"], output / "build.log", cwd=ROOT, env=env)
    require(snapshot() == before, "source changed during ordinary build")
    record = json.loads((output / "ordinary-boot/qemu.json").read_text())
    argv = record["argv"]
    artifacts = {key: (Path(record["cwd"]) / argv[argv.index(key) + 1]).read_bytes()
                 for key in ("-kernel", "-initrd", "-bios")}
    return artifacts, record["qemu_sha256"]


def inject(original, probe, nonce, phase):
    entries = unpack(gzip.decompress(original))
    script = (f"if /bin/native-persistence-probe {nonce} {phase}; then result=0; else result=$?; fi\n"
              f'echo "HEPTA_NATIVE_HARNESS nonce={nonce} phase={phase} exit=$result"\n').encode()
    found = 0
    for index, (name, fields, content) in enumerate(entries):
        if name.lstrip("./") != "init":
            continue
        require(content.count(BOOT_MARKER) == 1 and b"set -eu" in content, "ambiguous ordinary init")
        entries[index] = (name, fields, content.replace(BOOT_MARKER, script + BOOT_MARKER))
        found += 1
    require(found == 1, "ordinary init missing")
    fields = [max(item[1][0] for item in entries) + 1, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
    entries.append(("bin/native-persistence-probe", fields, probe))
    encoded = pack(entries)
    require([(n, d) for n, _, d in unpack(encoded)] == [(n, d) for n, _, d in entries], "cpio roundtrip mismatch")
    return gzip.compress(encoded, mtime=0)


def boot(argv, output, nonce, phase, timeout):
    output.mkdir(mode=0o700)
    killed_at_marker = False
    timed_out = excessive = False
    raw = bytearray()
    started = time.monotonic()
    pattern = re.compile(rf"^HEPTA_NATIVE_DURABLE nonce={nonce} boot_id=({UUID})$", re.M)
    with (output / "serial.log").open("xb") as log, subprocess.Popen(
            argv, env=ENV, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, start_new_session=True) as child:
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                while True:
                    remaining = timeout - (time.monotonic() - started)
                    if remaining <= 0:
                        timed_out = True
                        break
                    if not selector.select(min(remaining, 0.2)):
                        continue
                    block = os.read(child.stdout.fileno(), min(16384, MAX_SERIAL - len(raw) + 1))
                    if not block:
                        break
                    log.write(block)
                    raw.extend(block)
                    if len(raw) > MAX_SERIAL:
                        excessive = True
                        break
                    if phase == "first" and not killed_at_marker and pattern.search(raw.decode(errors="replace").replace("\r", "")):
                        child.kill()
                        killed_at_marker = True
            if timed_out or excessive:
                child.kill()
            code = child.wait(timeout=10)
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=10)
    text = raw.decode(errors="replace").replace("\r", "")
    rows = [json.loads(line) for line in text.splitlines() if line.startswith('{')]
    checks = [row for row in rows if "check" in row]
    expected_checks = 26 if phase == "first" else 24
    clean = (not timed_out and not excessive and '"passed":false' not in text
             and len(checks) == expected_checks and len({row["check"] for row in checks}) == expected_checks
             and all(row.get("passed") is True for row in checks))
    ids = pattern.findall(text)
    reopen = re.findall(rf"^HEPTA_NATIVE_REOPEN nonce={nonce} old_boot_id=({UUID}) new_boot_id=({UUID})$", text, re.M)
    if phase == "first":
        passed = clean and killed_at_marker and code == -signal.SIGKILL and len(ids) == 1
    else:
        passed = (clean and not killed_at_marker and code == 33 and len(reopen) == 1
                  and text.count(f"HEPTA_NATIVE_HARNESS nonce={nonce} phase=second exit=0") == 1
                  and text.count("TRILLIONNIUM_A01_BOOT_OK") == 1)
    result = {"passed": bool(passed), "phase": phase, "qemu_argv": argv, "qemu_exit": code,
              "actual_sigkill_after_durable_marker": killed_at_marker, "timed_out": timed_out,
              "excessive_output": excessive, "elapsed_seconds": round(time.monotonic() - started, 3),
              "serial_sha256": digest(bytes(raw)), "boot_ids": ids, "reopen_ids": reopen,
              "assertions": sum("check" in row and row.get("passed") is True for row in rows),
              "mount_identity": [row for row in rows if row.get("mount_identity") is True]}
    save(output / "result.json", result)
    return result


def execute(args, output, result):
    before = snapshot()
    save(output / "source-before.json", before)
    result.update(source_kind=before["kind"], stage="compile_probe")
    cc = Path("/usr/bin/gcc")
    run_checked([str(cc), "-static", "-std=c11", "-O2", "-Wall", "-Wextra", "-Werror", "-pthread",
                 str(HERE / "probe.c"), "-o", str(output / "probe")], output / "compile.log", timeout=60)
    probe = (output / "probe").read_bytes()
    disk, disk_record = fixture(output)
    result.update(fixture=disk_record, probe_sha256=digest(probe), stage="ordinary_kernel_build")
    save(output / "result.json", result)
    artifacts, qemu_hash = ordinary(output, before)
    names = {"-kernel": "kernel.elf", "-bios": "bios.bin", "-initrd": "ordinary-initramfs.cpio.gz"}
    for key, name in names.items():
        (output / name).write_bytes(artifacts[key])
    binary = Path(shutil.which("qemu-system-x86_64") or "missing")
    require(binary.is_file() and file_digest(binary) == qemu_hash, "QEMU differs from ordinary product boot")
    nonce = secrets.token_hex(16)
    result.update(nonce=nonce, qemu_sha256=qemu_hash,
                  artifact_sha256={names[key]: digest(value) for key, value in artifacts.items()}, guests={})
    require("," not in str(disk), "QEMU disk path cannot contain a comma")
    for phase in ("first", "second"):
        require(identity(disk) == disk_record["identity"], "disk inode or ownership changed")
        image = inject(artifacts["-initrd"], probe, nonce, phase)
        image_path = output / f"{phase}-initramfs.cpio.gz"
        image_path.write_bytes(image)
        argv = [str(binary), "-kernel", str(output / "kernel.elf"), "-initrd", str(image_path),
                "-append", "earlycon console=ttyS0 loglevel=warn SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --",
                "-machine", "q35", "-accel", "tcg", "-cpu", "max", "-bios", str(output / "bios.bin"),
                "-m", "512M", "-smp", "1", "-nodefaults", "-no-user-config", "-no-reboot", "-nographic",
                "-display", "none", "-monitor", "none", "-serial", "stdio",
                "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04",
                "-drive", f"file={disk},if=none,format=raw,id=hepta-store,snapshot=off,cache=writeback",
                "-device", "virtio-blk-pci,disable-legacy=on,disable-modern=off,drive=hepta-store"]
        result["stage"] = phase
        save(output / "result.json", result)
        observed = boot(argv, output / phase, nonce, phase, args.timeout)
        observed["initramfs_sha256"] = digest(image)
        observed["disk_after_sha256"] = file_digest(disk)
        result["guests"][phase] = observed
        save(output / "result.json", result)
        require(observed["passed"], f"{phase} guest failed; actual logs and disk retained")
        require(image_path.read_bytes() == image, "initramfs changed during boot")
        require(identity(disk) == disk_record["identity"], "disk replaced during boot")
    first, second = result["guests"]["first"], result["guests"]["second"]
    require(second["reopen_ids"][0][0] == first["boot_ids"][0]
            and second["reopen_ids"][0][1] != first["boot_ids"][0], "boot identities were not independently recovered")
    require(first["mount_identity"] == second["mount_identity"] and len(first["mount_identity"]) == 1,
            "bind source inode/device identity changed between boots")
    require(disk_record["before_sha256"] != first["disk_after_sha256"], "generated disk did not change")
    final = snapshot()
    save(output / "source-after.json", final)
    require(final == before, "source changed during guest qualification")
    require(all((output / name).read_bytes() == artifacts[key] for key, name in names.items()), "kernel/BIOS changed")
    require(file_digest(binary) == qemu_hash and (output / "probe").read_bytes() == probe, "QEMU/probe changed")
    result.update(passed=True, stage="complete", same_kernel_both_boots=True, source_unchanged=True,
                  artifact_unchanged=True, disk_final_sha256=file_digest(disk))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=int, default=120)
    args = parser.parse_args()
    require(1 <= args.timeout <= 120, "guest timeout must be 1..120 seconds")
    output = args.output.absolute()
    require(not output.exists() and not output.is_symlink(), "output must be a new directory")
    require(not output.resolve().is_relative_to(ROOT.resolve()), "evidence must be outside source")
    output.mkdir(parents=True, mode=0o700)
    result = {"schema": "hepta.native-persistence.v1", "passed": False, "stage": "prepare",
              "production_qualified": False, "physical_power_loss_qualified": False,
              "original_sqlite_qualified": False, "scope": "owned ext2 VM/process crash fixture"}
    save(output / "result.json", result)
    try:
        execute(args, output, result)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        result.update(passed=False, error=f"{type(error).__name__}: {error}")
        if (output / "fixture.ext2").is_file():
            result["disk_failure_sha256"] = file_digest(output / "fixture.ext2")
    save(output / "result.json", result)
    print(json.dumps({"passed": result["passed"], "stage": result["stage"], "output": str(output)}, sort_keys=True))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
