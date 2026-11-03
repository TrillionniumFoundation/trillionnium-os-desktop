#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Run a bounded owned-process dumpability suite in a disposable 512 MiB guest."""
import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.path.insert(0, str(ROOT / 'tests/organ_backend'))
from run_guest_probe import pack, unpack


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--suite', choices=('lifecycle', 'stat', 'traceme'), required=True)
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
    sources = sorted((HERE / args.suite).glob('*.c'))
    headers = sorted((HERE / args.suite).glob('*.h'))
    require(bool(sources), 'probe sources missing')
    compile_argv = ['cc', '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-static',
                    '-fno-pie', '-no-pie', '-pthread', *map(str, sources), '-o', str(out / 'probe.elf')]
    cp = subprocess.run(compile_argv, capture_output=True, timeout=90)
    (out / 'compile.log').write_bytes(cp.stdout + cp.stderr)
    require(cp.returncode == 0, 'strict probe compilation failed')
    original = args.initramfs.read_bytes()
    entries = unpack(gzip.decompress(original))
    boot = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
    command = '/bin/dumpability-probe' + (' --reset-policy 0' if args.suite == 'lifecycle' else '')
    invocation = (f'if {command}; then\n'.encode() +
                  b'  echo DUMPABLE_LIFECYCLE_EXIT=0\nelse\n  echo DUMPABLE_LIFECYCLE_EXIT=$?\nfi\n')
    patched, found = [], 0
    for name, fields, data in entries:
        if name.lstrip('./') == 'init':
            require(data.count(boot) == 1, 'unexpected init script')
            data = data.replace(boot, invocation + boot)
            found += 1
        patched.append((name, fields, data))
    require(found == 1, 'init not found')
    next_ino = max(item[1][0] for item in entries) + 1
    patched.append(('bin/dumpability-probe',
                    [next_ino, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
                    (out / 'probe.elf').read_bytes()))
    archive = pack(patched)
    require(len(unpack(archive)) == len(entries) + 1, 'archive roundtrip failed')
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
            cp = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=log,
                                stderr=subprocess.STDOUT, timeout=120)
            code = cp.returncode
        except subprocess.TimeoutExpired:
            code, timeout = None, True
    raw = (out / 'serial.log').read_bytes()
    sys.path.insert(0, str(HERE))
    checker_path = HERE / ('traceme_checker.py' if args.suite == 'traceme' else 'lifecycle_checker.py')
    spec = importlib.util.spec_from_file_location('dumpability_check', checker_path)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    result = checker.check(raw, code, timeout)
    report = dict(suite=args.suite, kernel_sha256=sha(out / 'kernel.elf'),
                  kernel_input=str(args.kernel.resolve()),
                  probe_source_sha256={str(p.relative_to(HERE)): sha(p) for p in sources + headers},
                  runner_source_sha256=sha(Path(__file__)),
                  checker_source_sha256={p.name: sha(p) for p in set([checker_path, HERE / 'lifecycle_checker.py'])},
                  probe_sha256=sha(out / 'probe.elf'),
                  original_initramfs_sha256=sha(args.initramfs), initramfs_sha256=sha(out / 'initramfs.cpio.gz'),
                  bios_sha256=sha(out / 'bios.bin'), serial_sha256=sha(out / 'serial.log'),
                  compile_argv=compile_argv, qemu_argv=argv,
                  qemu_version=subprocess.check_output(['qemu-system-x86_64', '--version'], text=True),
                  qemu_exit=code, timed_out=timeout, elapsed_seconds=time.monotonic() - began,
                  oracle=result, passed=result['passed'], production_isolation_qualified=False)
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({k: report[k] for k in ('suite', 'kernel_sha256', 'passed', 'qemu_exit')}, indent=2))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
