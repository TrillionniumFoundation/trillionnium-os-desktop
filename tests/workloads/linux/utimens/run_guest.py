#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Run the utimens regression in one disposable QEMU guest.

The disk is a fresh regular file. No host mounts, loop devices, networking, or
host device writes are used. Kernel provenance belongs to the supplied build;
this runner records exact hashes and never calls an old ELF a new source build.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'tests/organ_backend'))
from run_guest_probe import pack, unpack


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--initramfs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect-failure', action='store_true')
    parser.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args()
    out = args.output.resolve()
    require(not out.exists(), 'output must be a new directory')
    require(args.kernel.is_file() and args.initramfs.is_file(), 'missing kernel/initramfs')
    require(args.kernel.read_bytes()[:4] == b'\x7fELF', 'expected actual kernel ELF')
    require(',' not in str(out), 'output path must not contain QEMU option separator')
    out.mkdir(parents=True)
    source = Path(__file__).with_name('utimens_probe.c')
    compile_argv = ['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-static',
                    str(source), '-o', str(out / 'probe.elf')]
    cp = subprocess.run(compile_argv, capture_output=True, timeout=90)
    (out / 'compile.log').write_bytes(cp.stdout + cp.stderr)
    require(cp.returncode == 0, 'strict probe compilation failed')
    original = args.initramfs.read_bytes()
    entries = unpack(gzip.decompress(original))
    boot = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
    mode = '--disposable-guest'
    invocation = (f'if /bin/utimens-probe {mode}; then\n'.encode() +
                  b'  echo UT_PROBE_EXIT=0\nelse\n  echo UT_PROBE_EXIT=$?\nfi\n')
    patched, found = [], 0
    for name, fields, data in entries:
        if name.lstrip('./') == 'init':
            require(data.count(boot) == 1, 'unexpected init script')
            data = data.replace(boot, invocation + boot)
            found += 1
        patched.append((name, fields, data))
    require(found == 1, 'init not found')
    next_ino = max(item[1][0] for item in entries) + 1
    for name, mode, data in [('bin/utimens-probe', 0o100755, (out / 'probe.elf').read_bytes()),
                             ('.hepta-disposable-guest', 0o100400, b'utimens regression\n')]:
        patched.append((name, [next_ino, mode, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0], data))
        next_ino += 1
    archive = pack(patched)
    require(len(unpack(archive)) == len(entries) + 2, 'archive roundtrip failed')
    (out / 'initramfs.cpio.gz').write_bytes(gzip.compress(archive, mtime=0))
    shutil.copyfile(args.kernel, out / 'kernel.elf')
    shutil.copyfile('/usr/share/seabios/bios-256k.bin', out / 'bios.bin')
    seed = out / 'seed-dir'
    seed.mkdir()
    (seed / 'seed').write_bytes(b'RO-SEED!' + bytes(4096 - 8))
    image = out / 'disk.raw'
    with image.open('xb') as stream:
        stream.truncate(32 * 1024 * 1024)
    format_argv = ['mkfs.ext2', '-F', '-q', '-b', '4096', '-I', '256', '-O', 'none,filetype',
                   '-d', str(seed), str(image)]
    cp = subprocess.run(format_argv, capture_output=True, timeout=30)
    (out / 'format.log').write_bytes(cp.stdout + cp.stderr)
    require(cp.returncode == 0, 'formatting fresh regular-file disk failed')
    image_before = sha(image)
    argv = ['qemu-system-x86_64', '-kernel', str(out / 'kernel.elf'),
            '-initrd', str(out / 'initramfs.cpio.gz'), '-bios', str(out / 'bios.bin'),
            '-append', 'earlycon console=ttyS0 loglevel=info SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --',
            '-machine', 'q35', '-accel', 'tcg', '-cpu', 'max', '-m', '512M', '-smp', '1',
            '-nodefaults', '-no-user-config', '-no-reboot', '-nographic', '-display', 'none',
            '-monitor', 'none', '-serial', 'stdio', '-nic', 'none',
            '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04',
            '-drive', 'if=none,format=raw,id=readonly,cache=writeback,file=' + str(image),
            '-device', 'virtio-blk-pci,bus=pcie.0,addr=0x7,drive=readonly,disable-legacy=on,disable-modern=off']
    began = time.monotonic()
    timeout = False
    with (out / 'serial.log').open('wb') as log:
        try:
            cp = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                timeout=args.timeout)
            code = cp.returncode
        except subprocess.TimeoutExpired:
            code, timeout = None, True
    raw = (out / 'serial.log').read_text(errors='replace')
    clean = re.sub(r'\x1b\[[0-9;]*m', '', raw).replace('\r\n', '\n')
    cases = [dict(name=name, passed=passed == '1', actual=int(actual), errno=int(err), unchanged=unchanged == '1', omit_preserved=omit == '1')
             for name, passed, actual, err, unchanged, omit in re.findall(
                 r'^UT_CASE name=(\S+) pass=([01]) actual=(-?\d+) errno=(\d+) unchanged=([01]) omit=([01])$', clean, re.M)]
    complete = re.findall(r'^UT_COMPLETE cases=(\d+) failures=(\d+)$', clean, re.M)
    valid = (code == 33 and not timeout and len(complete) == 1 and
             len(cases) == int(complete[0][0]) and len(cases) == 76 and
             len({case['name'] for case in cases}) == len(cases) and
             sum(not case['passed'] for case in cases) == int(complete[0][1]) and
             clean.count('TRILLIONNIUM_A01_BOOT_OK') == 1)
    disk_unchanged = sha(image) == image_before
    passed = valid and all(case['passed'] for case in cases) and 'UT_PROBE_EXIT=0\n' in clean
    report = dict(kernel_sha256=sha(out / 'kernel.elf'), kernel_input=str(args.kernel.resolve()),
                  probe_source_sha256=sha(source), runner_source_sha256=sha(Path(__file__)),
                  probe_sha256=sha(out / 'probe.elf'),
                  original_initramfs_sha256=sha(args.initramfs), initramfs_sha256=sha(out / 'initramfs.cpio.gz'),
                  bios_sha256=sha(out / 'bios.bin'), disk_before_sha256=image_before, disk_after_sha256=sha(image),
                  compile_argv=compile_argv, format_argv=format_argv, qemu_argv=argv,
                  qemu_version=subprocess.check_output(['qemu-system-x86_64', '--version'], text=True),
                  qemu_exit=code, timed_out=timeout, elapsed_seconds=time.monotonic() - began,
                  guest_complete=valid, passed=passed, disk_unchanged=disk_unchanged, expected_failure=args.expect_failure, cases=cases,
                  scope='tmpfs/ext2 utimens owner, group, capability, descriptor and omitted-time semantics')
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('kernel_sha256', 'guest_complete', 'passed', 'qemu_exit')}, indent=2))
    for case in cases:
        if not case['passed']:
            print(case)
    return 0 if valid and passed != args.expect_failure else 1


if __name__ == '__main__':
    raise SystemExit(main())
