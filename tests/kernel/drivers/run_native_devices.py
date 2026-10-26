#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Exercise actual evdev, boot framebuffer and retained ext2/virtio in QEMU.

The unchanged source-built ordinary kernel is admitted by its original build
receipt and exact source snapshot. The static probe runs only inside two fresh
guest boots. This is virtual-device execution, not physical hardware or G2.
"""

import argparse
from datetime import datetime, timezone
import gzip
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import socket
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "tests/kernel/control"))
import native_devices as evidence
import run_queryabi_guest as initramfs
from run_queryabi_candidate_guest import source_snapshot

require = evidence.require
SEABIOS_SHA = "1a9ea4f17bcfb27bda5728e2c21d9fa074cf7947b9b4910bb28213a735c96735"


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def platform_files(directory):
    require(directory.is_absolute() and directory.resolve(strict=True) == directory and directory.is_dir(),
            "canonical installed GRUB platform directory required")
    files = {str(path.relative_to(directory)): sha(path) for path in sorted(directory.rglob("*"))
             if path.is_file()}
    require("moddep.lst" in files and "multiboot2.mod" in files and "biosdisk.mod" in files,
            "actual BIOS GRUB modules required")
    return files


def command(argv, cwd, log, *, timeout=120):
    with log.open("xb") as output:
        result = subprocess.run(argv, cwd=cwd, env={"PATH": "/usr/bin:/bin:/usr/sbin:/sbin",
                                "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"}, stdin=subprocess.DEVNULL,
                                stdout=output, stderr=subprocess.STDOUT, timeout=timeout)
    require(result.returncode == 0, "actual preparation failed: " + log.name)
    return {"argv": [str(arg) for arg in argv], "cwd": str(cwd), "exit_code": result.returncode,
            "log": log.name, "log_sha256": sha(log)}


def guest_image(original, probe, nonce, mode):
    entries = initramfs.unpack(gzip.decompress(original))
    require(initramfs.unpack(initramfs.pack(entries)) == entries, "original newc roundtrip differs")
    name = "bin/native-driver-probe"
    require(not any(entry[0].lstrip("./") == name for entry in entries), "probe already present")
    result, replaced = [], 0
    for path, fields, data in entries:
        if path.lstrip("./") == "init":
            require(data.count(initramfs.BOOT_MARKER) == 1 and b"set -eu" in data, "original init differs")
            data = data.replace(initramfs.BOOT_MARKER,
                                f"/bin/native-driver-probe {nonce} {mode}\n".encode() + initramfs.BOOT_MARKER)
            replaced += 1
        result.append((path, fields, data))
    require(replaced == 1, "exact original init required")
    inode = max(entry[1][0] for entry in entries) + 1
    result.append((name, [inode, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0], probe))
    packed = initramfs.pack(result)
    require(len(initramfs.unpack(packed)) == len(entries) + 1, "repacked original entries differ")
    return gzip.compress(packed, mtime=0)


class Qmp:
    def __init__(self, directory, process, deadline):
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.buffer = b""
        self.next_id = 0
        self.commands = []
        self.deadline = deadline
        self.directory = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
        try:
            while True:
                require(process.poll() is None, "QEMU exited before its private QMP socket")
                require(time.monotonic() < deadline, "private QMP connection deadline")
                try:
                    self.socket.connect(f"/proc/self/fd/{self.directory}/qmp.sock")
                    break
                except (FileNotFoundError, ConnectionRefusedError):
                    time.sleep(0.02)
            pid, uid, _gid = struct.unpack("3i", self.socket.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
            require(pid == process.pid and uid == os.getuid(), "QMP is not the retained owned QEMU process")
            self.socket.settimeout(max(0.1, min(5, deadline - time.monotonic())))
            greeting = self.message()
            require(set(greeting) == {"QMP"}, "actual QMP greeting required")
            self.call("qmp_capabilities", {})
        except BaseException:
            self.close()
            raise

    def message(self):
        while b"\n" not in self.buffer:
            require(time.monotonic() < self.deadline, "QMP reply deadline")
            block = self.socket.recv(4096)
            require(block and len(self.buffer) + len(block) <= 65536, "bounded complete QMP reply required")
            self.buffer += block
        line, self.buffer = self.buffer.split(b"\n", 1)
        value = json.loads(line)
        require(isinstance(value, dict), "QMP object required")
        return value

    def call(self, name, arguments):
        require(name in ("qmp_capabilities", "screendump", "send-key"), "unreviewed QMP command")
        self.next_id += 1
        request = {"execute": name, "arguments": arguments, "id": self.next_id}
        self.socket.sendall(json.dumps(request).encode() + b"\n")
        for _ in range(32):
            response = self.message()
            if "event" in response:
                continue
            require(response.get("id") == self.next_id and "error" not in response and "return" in response,
                    "QMP command did not succeed")
            self.commands.append({"request": request, "response": response})
            return response["return"]
        raise ValueError("excessive asynchronous QMP events")

    def close(self):
        self.socket.close()
        if self.directory is not None:
            os.close(self.directory)
            self.directory = None


def boot(args, output, mode, nonce, kernel, bios, original, probe, disk):
    directory = output / ("boot-1-write" if mode == "write" else "boot-2-read")
    directory.mkdir(mode=0o700)
    image = guest_image(original, probe, nonce, mode)
    (directory / "initramfs.cpio.gz").write_bytes(image)
    iso_root = directory / "iso-root"
    (iso_root / "boot/grub").mkdir(mode=0o700, parents=True)
    loader = evidence.grub_loader_image(kernel.read_bytes())
    (iso_root / "boot/kernel.elf").write_bytes(loader)
    shutil.copyfile(directory / "initramfs.cpio.gz", iso_root / "boot/initramfs.cpio.gz")
    config = ("serial --unit=0 --speed=115200\nterminal_input serial\nterminal_output serial\n"
              "set timeout=0\nset default=0\ninsmod all_video\nset gfxpayload=1024x768x32\n"
              "menuentry 'Asterinas real virtual devices' {\n"
              " multiboot2 /boot/kernel.elf earlycon console=ttyS0 loglevel=info "
              f"SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin trill_driver_probe={nonce} --\n"
              " set gfxpayload=1024x768x32\n module2 /boot/initramfs.cpio.gz\n boot\n}\n")
    (iso_root / "boot/grub/grub.cfg").write_text(config)
    iso = directory / "devices.iso"
    prepare = command([args.grub_mkrescue, "--xorriso=" + args.xorriso,
                       "--directory=" + str(args.grub_directory), "-o", str(iso), str(iso_root)], directory,
                      directory / "grub-build.log")
    argv = [args.qemu, "-machine", "q35", "-accel", "tcg", "-cpu", "max", "-bios", str(bios),
            "-m", "512M", "-smp", "1", "-nodefaults", "-no-user-config", "-no-reboot",
            "-display", "none", "-vga", "std", "-monitor", "none", "-serial", "stdio",
            "-qmp", "unix:qmp.sock,server=on,wait=off", "-boot", "order=d,strict=on",
            "-drive", "file=devices.iso,media=cdrom,readonly=on,format=raw",
            "-drive", f"file={disk},if=none,id=driver-state,format=raw",
            "-device", "virtio-blk-pci,bus=pcie.0,addr=0x8,drive=driver-state,disable-legacy=on,disable-modern=off",
            "-device", "virtio-keyboard-pci",
            "-device", "isa-debug-exit,iobase=0xf4,iosize=0x04"]
    started = time.monotonic()
    deadline = started + args.timeout
    record = {"mode": mode, "argv": argv, "cwd": str(directory), "prepare": prepare,
              "boot_iso_sha256": sha(iso), "kernel_sha256": sha(kernel), "bios_sha256": sha(bios),
              "grub_loader_image_sha256": hashlib.sha256(loader).hexdigest(),
              "loader_only_changed_bytes": {"offset": 18, "original_hex": "0300", "loaded_hex": "3e00"},
              "kernel_entry_segments_and_all_other_bytes_unchanged": True,
              "probe_sha256": hashlib.sha256(probe).hexdigest(), "initramfs_sha256": hashlib.sha256(image).hexdigest(),
              "disk_before_sha256": sha(disk), "timed_out": False, "passed": False}
    serial = directory / "serial.log"
    qmp = None
    process = None
    try:
        with serial.open("xb") as log:
            process = subprocess.Popen(argv, cwd=directory, stdin=subprocess.DEVNULL,
                                       stdout=log, stderr=subprocess.STDOUT, start_new_session=True, umask=0o077)
            record["owned_qemu_pid"] = process.pid
            qmp = Qmp(directory, process, deadline)
            while True:
                require(process.poll() is None, "guest exited before real devices became ready")
                require(time.monotonic() < deadline, "real device readiness deadline")
                captured = serial.read_bytes()
                require(len(captured) <= evidence.SERIAL_LIMIT, "bounded live serial required")
                if any(line.startswith(evidence.PREFIX) and line.endswith(b"\n")
                       for line in captured.splitlines(keepends=True)):
                    ready = evidence.records(captured, nonce, mode, complete=False)[0]
                    break
                require(b"TRILL_NATIVE_DRIVER_FAIL" not in captured and b"Kernel panic" not in captured
                        and b"ERROR: Uncaught panic" not in captured,
                        "actual device probe failed before readiness")
                time.sleep(0.02)
            qmp.call("screendump", {"filename": "frame.ppm"})
            pixels = evidence.framebuffer_pixels((directory / "frame.ppm").read_bytes())
            record["framebuffer"] = {**pixels, "sha256": sha(directory / "frame.ppm")}
            qmp.call("send-key", {"keys": [{"type": "qcode", "data": "a"}], "hold-time": 100})
            remaining = deadline - time.monotonic()
            require(remaining > 0, "guest execution budget exhausted")
            record["raw_exit_code"] = process.wait(timeout=remaining)
            captured = serial.read_bytes()
            measured = evidence.records(captured, nonce, mode, complete=True)
            require(record["raw_exit_code"] == 33 and captured.count(b"TRILLIONNIUM_A01_BOOT_OK") == 1,
                    "original successful boot/shutdown and exact guest exit required")
            require(measured[0] == ready, "device identities changed after host observation")
            record.update(records=measured, qmp_commands=qmp.commands, passed=True)
    except subprocess.TimeoutExpired:
        record["timed_out"] = True
        raise ValueError("actual device guest timed out")
    finally:
        record["timed_out"] = record["timed_out"] or time.monotonic() >= deadline
        if qmp is not None:
            qmp.close()
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        record.update(seconds=round(time.monotonic() - started, 3), serial_sha256=sha(serial) if serial.exists() else None,
                      disk_after_sha256=sha(disk), owned_qemu_reaped=process is None or process.poll() is not None)
        save(directory / "result.json", record)
    return record


def execute(args, report):
    require(args.output.is_absolute() and args.output.parent.is_dir() and not args.output.exists()
            and not args.output.is_symlink(), "new absolute output directory required")
    require(not args.output.is_relative_to(ROOT) and not args.output.is_relative_to(args.source_root),
            "evidence must be outside both source checkouts")
    for directory in (args.output.parent, args.source_root, args.kernel_inputs, ROOT):
        require(directory.is_absolute() and directory.resolve(strict=True) == directory
                and directory.is_dir(), "canonical existing source/evidence roots required")
    require(not args.output.is_relative_to(args.kernel_inputs), "evidence must not overlap kernel inputs")
    for value in (args.expected_kernel_receipt_sha256, args.expected_qemu_sha256):
        require(re.fullmatch(r"[0-9a-f]{64}", value), "independent full SHA256 required")
    require(sha(args.kernel_inputs / "kernel-build.json") == args.expected_kernel_receipt_sha256,
            "reviewed original kernel receipt differs")
    receipt = json.loads((args.kernel_inputs / "kernel-build.json").read_bytes())
    require(receipt.get("schema") == "hepta.native-original-runtime-build.v1"
            and receipt.get("built") is True and receipt.get("source_clean") is True
            and receipt.get("kernel_profile") == "ordinary-os"
            and receipt.get("ordinary_queryabi", {}).get("passed") is True,
            "actual original source build/ordinary boot/QueryAbi receipt required")
    source = receipt["build_sources"]["desktop"]
    before = source_snapshot(args.source_root, source["head"], source["tree"])
    harness = source_snapshot(ROOT, args.expected_harness_head, args.expected_harness_tree)
    kernel, bios = args.kernel_inputs / "kernel.elf", args.kernel_inputs / "bios.bin"
    require(sha(kernel) == receipt["binary_sha256"]["kernel"] and sha(bios) == SEABIOS_SHA,
            "reviewed actual kernel/SeaBIOS bytes required")
    require(sha(Path(args.qemu)) == args.expected_qemu_sha256, "selected QEMU bytes differ")
    for name in (args.cc, args.grub_mkrescue, args.mke2fs, args.xorriso):
        require(Path(name).is_absolute() and Path(name).is_file(), "explicit installed build tool required")
    args.output.mkdir(mode=0o700)
    report["output_created"] = True
    report.update(kernel_build_receipt_sha256=args.expected_kernel_receipt_sha256,
                  kernel_sources=receipt["sources"], harness={"head": harness["head"], "tree": harness["tree"]},
                  qemu_sha256=args.expected_qemu_sha256)
    report["tools"] = {name: {"path": value, "resolved_path": str(Path(value).resolve(strict=True)),
                              "sha256": sha(Path(value))}
                       for name, value in (("compiler", args.cc), ("grub", args.grub_mkrescue),
                                           ("formatter", args.mke2fs), ("iso_helper", args.xorriso))}
    report["grub_platform"] = {"path": str(args.grub_directory), "files": platform_files(args.grub_directory)}
    save(args.output / "source-before.json", before)
    save(args.output / "harness-before.json", harness)
    probe = args.output / "native-driver-probe"
    report["compile"] = command([args.cc, "-O2", "-std=c11", "-Wall", "-Wextra", "-Werror", "-static",
                                 str(HERE / "native_devices.c"), "-o", str(probe)], ROOT,
                                args.output / "compile.log", timeout=60)
    nonce = os.urandom(32).hex()
    report["nonce"] = nonce
    disk = args.output / "retained-state.raw"
    with disk.open("xb") as stream:
        stream.truncate(64 * 1024 * 1024)
    report["format"] = command([args.mke2fs, "-q", "-t", "ext2", "-F", str(disk)], args.output,
                               args.output / "format.log", timeout=60)
    report["disk_preimage_sha256"] = sha(disk)
    shutil.copyfile(disk, args.output / "retained-state-preimage.raw")
    original = (args.kernel_inputs / "initramfs.cpio.gz").read_bytes()
    require(len(original) <= 8 * 1024 * 1024, "bounded original initramfs required")
    report["boots"] = []
    for mode in ("write", "read"):
        report["boots"].append(boot(args, args.output, mode, nonce, kernel, bios, original, probe.read_bytes(), disk))
        save(args.output / "result.json", report)
    report["retained_storage"] = evidence.retained_boots(report["boots"][0]["records"][0],
                                                       report["boots"][1]["records"][0])
    after = source_snapshot(args.source_root, source["head"], source["tree"])
    harness_after = source_snapshot(ROOT, args.expected_harness_head, args.expected_harness_tree)
    require(before == after and harness == harness_after, "compiled kernel or harness sources changed")
    require(sha(kernel) == receipt["binary_sha256"]["kernel"] and sha(bios) == SEABIOS_SHA
            and sha(Path(args.qemu)) == args.expected_qemu_sha256, "execution inputs changed")
    require(all(sha(Path(item["path"])) == item["sha256"] for item in report["tools"].values()),
            "actual build tool changed during execution")
    require(platform_files(args.grub_directory) == report["grub_platform"]["files"],
            "actual GRUB platform modules changed during execution")
    save(args.output / "source-after.json", after)
    save(args.output / "harness-after.json", harness_after)
    report.update(passed=True, source_inputs_unchanged=True, exact_virtual_devices_qualified=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--expected-harness-head", required=True)
    parser.add_argument("--expected-harness-tree", required=True)
    parser.add_argument("--kernel-inputs", type=Path, required=True)
    parser.add_argument("--expected-kernel-receipt-sha256", required=True)
    parser.add_argument("--qemu", required=True)
    parser.add_argument("--expected-qemu-sha256", required=True)
    parser.add_argument("--cc", default="/usr/bin/gcc")
    parser.add_argument("--grub-mkrescue", default="/usr/bin/grub-mkrescue")
    parser.add_argument("--xorriso", default="/usr/bin/xorriso")
    parser.add_argument("--grub-directory", type=Path, default=Path("/usr/lib/grub/i386-pc"))
    parser.add_argument("--mke2fs", default="/usr/sbin/mke2fs")
    parser.add_argument("--timeout", type=int, choices=range(1, 121), default=90)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {"schema": "trill.native-virtual-device-execution.v1", "passed": False,
              "started_utc": datetime.now(timezone.utc).isoformat(), "physical_hardware_qualified": False,
              "production_authority_qualified": False, "g2_complete": False, "power_loss_qualified": False,
              "native_gui_application_qualified": False, "gpu_acceleration_qualified": False,
              "physical_input_qualified": False}
    if not args.execute:
        print(json.dumps({**report, "status": "disabled; explicit --execute required"}))
        return 0
    try:
        execute(args, report)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report["error"] = type(error).__name__ + ": " + str(error)
    report["finished_utc"] = datetime.now(timezone.utc).isoformat()
    if report.get("output_created"):
        save(args.output / "result.json", report)
    print(json.dumps({key: value for key, value in report.items() if key not in ("boots",)}, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
