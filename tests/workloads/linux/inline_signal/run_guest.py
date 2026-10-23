#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Run the inline signal ownership regression in one disposable QEMU guest.

Uses an isolated 512 MiB single-vCPU guest without host disks or networking. Kernel provenance belongs to the supplied build;
this runner records exact hashes and never calls an old ELF a new source build.
"""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import importlib.util
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
    args = parser.parse_args()
    out = args.output.resolve()
    require(not out.exists(), 'output must be a new directory')
    require(args.kernel.is_file() and args.initramfs.is_file(), 'missing kernel/initramfs')
    require(args.kernel.read_bytes()[:4] == b'\x7fELF', 'expected actual kernel ELF')
    require(',' not in str(out), 'output path must not contain QEMU option separator')
    out.mkdir(parents=True)
    source = Path(__file__).with_name('probe.c')
    compile_argv = ['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-static',
                    str(source), '-o', str(out / 'probe.elf')]
    cp = subprocess.run(compile_argv, capture_output=True, timeout=90)
    (out / 'compile.log').write_bytes(cp.stdout + cp.stderr)
    require(cp.returncode == 0, 'strict probe compilation failed')
    original = args.initramfs.read_bytes()
    entries = unpack(gzip.decompress(original))
    boot = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
    mode = '--disposable-guest'
    invocation = (f'if /bin/inline-signal-probe {mode}; then\n'.encode() +
                  b'  echo INLINE_SIGNAL_PROBE_EXIT=0\nelse\n  echo INLINE_SIGNAL_PROBE_EXIT=$?\nfi\n')
    patched, found = [], 0
    for name, fields, data in entries:
        if name.lstrip('./') == 'init':
            require(data.count(boot) == 1, 'unexpected init script')
            data = data.replace(boot, invocation + boot)
            found += 1
        patched.append((name, fields, data))
    require(found == 1, 'init not found')
    next_ino = max(item[1][0] for item in entries) + 1
    for name, mode, data in [('bin/inline-signal-probe', 0o100755, (out / 'probe.elf').read_bytes()),
                             ('.hepta-disposable-guest', 0o100400, b'inline signal ownership regression\n')]:
        patched.append((name, [next_ino, mode, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0], data))
        next_ino += 1
    archive = pack(patched)
    require(len(unpack(archive)) == len(entries) + 2, 'archive roundtrip failed')
    (out / 'initramfs.cpio.gz').write_bytes(gzip.compress(archive, mtime=0))
    shutil.copyfile(args.kernel, out / 'kernel.elf')
    shutil.copyfile('/usr/share/seabios/bios-256k.bin', out / 'bios.bin')
    argv = ['qemu-system-x86_64', '-kernel', str(out / 'kernel.elf'),
            '-initrd', str(out / 'initramfs.cpio.gz'), '-bios', str(out / 'bios.bin'),
            '-append', 'earlycon console=ttyS0 loglevel=info SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --',
            '-machine', 'q35', '-accel', 'tcg', '-cpu', 'max', '-m', '512M', '-smp', '1',
            '-nodefaults', '-no-user-config', '-no-reboot', '-nographic', '-display', 'none',
            '-monitor', 'none', '-serial', 'stdio', '-nic', 'none',
            '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04']
    began = time.monotonic()
    timeout = False
    with (out / 'serial.log').open('wb') as log:
        try:
            cp = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                timeout=120)
            code = cp.returncode
        except subprocess.TimeoutExpired:
            code, timeout = None, True
    raw = (out / 'serial.log').read_text(errors='replace')
    spec = importlib.util.spec_from_file_location("inline_signal_check", Path(__file__).with_name("check.py"))
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    result = checker.check(raw, code, timeout)
    valid, passed = result['guest_complete'], result['passed']
    report = dict(kernel_sha256=sha(out / 'kernel.elf'), kernel_input=str(args.kernel.resolve()),
                  probe_source_sha256=sha(source), runner_source_sha256=sha(Path(__file__)),
                  checker_source_sha256=sha(Path(__file__).with_name("check.py")),
                  probe_sha256=sha(out / 'probe.elf'),
                  original_initramfs_sha256=sha(args.initramfs), initramfs_sha256=sha(out / 'initramfs.cpio.gz'),
                  bios_sha256=sha(out / 'bios.bin'),
                  compile_argv=compile_argv, qemu_argv=argv,
                  qemu_version=subprocess.check_output(['qemu-system-x86_64', '--version'], text=True),
                  qemu_exit=code, timed_out=timeout, elapsed_seconds=time.monotonic() - began,
                  guest_complete=valid, passed=passed, cases=result['cases'],
                  scope='original standard fault/fatal ownership, permissions, ptrace, dynamic RT and signal reads')
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('kernel_sha256', 'guest_complete', 'passed', 'qemu_exit')}, indent=2))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
