#!/usr/bin/env python3
"""Crash and reopen a real SQLite WAL across two Asterinas guest boots.

Only fresh task-owned regular disk images are formatted. No host mount, loop,
device node, network or production process is used. QEMU SIGKILL exercises a
guest-kernel crash; it does not emulate loss of the host/device volatile cache.
"""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import selectors
import shutil
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tests/kernel/control'))
import run_queryabi_guest as cpio

LIMIT = 8 * 1024 * 1024
BOOT = b'echo "TRILLIONNIUM_A01_BOOT_OK"'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + '\n')


def pinned(path, expected, limit):
    require(path.is_file() and not path.is_symlink(), 'input must be a regular non-symlink file')
    require(path.stat().st_size <= limit, 'input exceeds bound')
    data = path.read_bytes()
    require(sha(data) == expected, 'input digest mismatch: ' + str(path))
    return data


def executable(name):
    value = shutil.which(name)
    require(value is not None, 'missing executable: ' + name)
    path = Path(value).resolve(strict=True)
    with path.open('rb') as stream:
        require(stream.read(4) == b'\x7fELF', 'expected actual native tool ELF: ' + name)
    return str(path)


def initramfs(original, probe, phase, nonce):
    require(phase in ('seed', 'seed-uncommitted', 'verify'), 'invalid phase')
    require(re.fullmatch('[0-9a-f]{64}', nonce) is not None, 'invalid nonce')
    entries = cpio.unpack(gzip.decompress(original))
    require(all(name.lstrip('./') != 'bin/sqlite-restart' for name, _, _ in entries), 'probe already present')
    script = (f'/bin/busybox mkdir -p /persist\n'
              f'/bin/busybox mount -t ext2 /dev/vda /persist\n'
              f'if /bin/sqlite-restart {phase} /persist {nonce}; then\n'
              f'    sqlite_code=0\nelse\n    sqlite_code=$?\nfi\n'
              f'echo "SQLITE_RESTART_EXIT=$sqlite_code"\n').encode()
    changed, found = [], 0
    for name, fields, content in entries:
        if name.lstrip('./') == 'init':
            require(content.count(BOOT) == 1 and b'set -eu' in content, 'ambiguous original init')
            content = content.replace(BOOT, script + BOOT)
            found += 1
        changed.append((name, fields, content))
    require(found == 1, 'missing original init')
    fields = [max(item[1][0] for item in entries) + 1, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0]
    changed.append(('bin/sqlite-restart', fields, probe))
    packed = cpio.pack(changed)
    # The shipped newc parser verifies bounded names, sizes and uniqueness.
    require(len(cpio.unpack(packed)) == len(entries) + 1, 'initramfs entries changed')
    return gzip.compress(packed, mtime=0)


def crash_at_ready(command, output, marker, timeout):
    """The direct child remains unreaped until its owned PID is killed."""
    data, cut = bytearray(), False
    started = time.monotonic()
    with output.open('xb') as log, subprocess.Popen(
            command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, start_new_session=True) as process:
        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                while time.monotonic() - started < timeout:
                    if not selector.select(min(0.2, max(0.0, timeout - (time.monotonic() - started)))):
                        continue
                    chunk = os.read(process.stdout.fileno(), 16384)
                    if not chunk:
                        break
                    log.write(chunk)
                    data.extend(chunk)
                    require(len(data) <= LIMIT, 'guest serial exceeds bound')
                    lines = bytes(data).replace(b'\r\n', b'\n').split(b'\n')
                    if marker in lines:
                        require(lines.count(marker) == 1, 'ambiguous crash boundary')
                        process.kill()
                        cut = True
                        break
            if not cut:
                process.kill()
            tail, _ = process.communicate(timeout=10)
            require(len(data) + len(tail) <= LIMIT, 'guest serial exceeds bound')
            log.write(tail)
            data.extend(tail)
            code = process.returncode
        finally:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=10)
    require(cut and code == -signal.SIGKILL, 'guest did not reach the crash boundary before SIGKILL')
    lines = bytes(data).replace(b'\r\n', b'\n').split(b'\n')
    require(lines.count(marker) == 1 and b'TRILLIONNIUM_A01_BOOT_OK' not in lines,
            'guest must not cleanly finish before the crash')
    return {'exit_code': code, 'serial_sha256': sha(data), 'ready_then_sigkill': True}


def reopened(raw, code, nonce):
    lines = raw.replace(b'\r\n', b'\n').split(b'\n')
    marker = f'SQLITE_RESTART_VERIFIED nonce={nonce} committed=32 pending=0 integrity=ok'.encode()
    return (code == 33 and lines.count(marker) == 1 and lines.count(b'SQLITE_RESTART_EXIT=0') == 1
            and lines.count(b'TRILLIONNIUM_A01_BOOT_OK') == 1
            and b'Kernel panic' not in raw and b'SQLITE_RESTART_ERROR' not in raw
            and b'SQLITE_RESTART_REJECTED' not in raw)


def run(args, out, report):
    kernel = pinned(args.kernel, args.expected_kernel_sha256, 64 * 1024 * 1024)
    original = pinned(args.initramfs, cpio.A01_INITRD_SHA, LIMIT)
    require(args.bios.is_file(), 'missing BIOS')
    bios = args.bios.read_bytes()
    require(0 < len(bios) <= 2 * 1024 * 1024, 'invalid BIOS size')
    for name, data in (('kernel.elf', kernel), ('bios.bin', bios)):
        (out / name).write_bytes(data)
    probe = out / 'sqlite-restart'
    compile_args = [executable(args.cc), '-O2', '-std=c11', '-Wall', '-Wextra', '-Werror', '-static',
                    str(Path(__file__).with_name('sqlite_restart_probe.c')),
                    '-lsqlite3', '-lm', '-ldl', '-pthread', '-o', str(probe)]
    with (out / 'compile.log').open('xb') as log:
        result = subprocess.run(compile_args, stdout=log, stderr=subprocess.STDOUT, timeout=120, check=False)
    require(result.returncode == 0, 'strict static SQLite probe build failed')
    probe_bytes = probe.read_bytes()
    qemu, formatter = executable(args.qemu), executable(args.mkfs)
    report.update(kernel_sha256=sha(kernel), original_initramfs_sha256=sha(original),
                  bios_sha256=sha(bios), probe_sha256=sha(probe_bytes), compile_command=compile_args,
                  qemu_version=subprocess.check_output([qemu, '--version'], timeout=10).decode(), cases=[])
    for negative in (False, True):
        case = out / ('negative-omitted-commit' if negative else 'committed')
        case.mkdir()
        image = case / 'disk.raw'
        with image.open('xb') as stream:
            stream.truncate(64 * 1024 * 1024)
        require(',' not in str(image), 'disk path would alter QEMU options')
        format_args = [formatter, '-F', '-q', '-b', '4096', '-I', '256', '-O', 'none', str(image)]
        with (case / 'format.log').open('xb') as log:
            result = subprocess.run(format_args, stdout=log, stderr=subprocess.STDOUT, timeout=30, check=False)
        require(result.returncode == 0, 'fresh regular-file ext2 formatting failed')
        nonce = os.urandom(32).hex()
        phase = 'seed-uncommitted' if negative else 'seed'
        for stage in (phase, 'verify'):
            (case / (stage + '.cpio.gz')).write_bytes(initramfs(original, probe_bytes, stage, nonce))
        common = [qemu, '-kernel', str(out / 'kernel.elf'), '-machine', 'q35', '-accel', 'tcg',
                  '-cpu', 'max', '-bios', str(out / 'bios.bin'), '-m', '512M', '-smp', '1',
                  '-nodefaults', '-no-user-config', '-no-reboot', '-nographic', '-display', 'none',
                  '-monitor', 'none', '-serial', 'stdio', '-nic', 'none',
                  '-append', 'earlycon console=ttyS0 loglevel=info SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --',
                  '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04',
                  '-drive', 'if=none,format=raw,id=sqlite,cache=writeback,file=' + str(image),
                  '-device', 'virtio-blk-pci,bus=pcie.0,addr=0x7,drive=sqlite,disable-legacy=on,disable-modern=off']
        seed_command = common + ['-initrd', str(case / (phase + '.cpio.gz'))]
        verify_command = common + ['-initrd', str(case / 'verify.cpio.gz')]
        save(case / 'input.json', {'nonce': nonce, 'negative': negative, 'format': format_args,
                                  'seed': seed_command, 'verify': verify_command})
        marker = f'SQLITE_RESTART_READY nonce={nonce} committed={0 if negative else 32} pending=16 synchronous=FULL'.encode()
        cut = crash_at_ready(seed_command, case / 'seed.log', marker, args.timeout)
        with (case / 'verify.log').open('xb') as log:
            result = subprocess.run(verify_command, stdin=subprocess.DEVNULL, stdout=log,
                                    stderr=subprocess.STDOUT, timeout=args.timeout, check=False)
        require((case / 'verify.log').stat().st_size <= LIMIT, 'verification serial exceeds bound')
        raw = (case / 'verify.log').read_bytes()
        positive_oracle = reopened(raw, result.returncode, nonce)
        lines = raw.replace(b'\r\n', b'\n').split(b'\n')
        negative_rejected = (not positive_oracle and result.returncode == 33
                             and lines.count(f'SQLITE_RESTART_REJECTED nonce={nonce}'.encode()) == 1
                             and lines.count(b'SQLITE_RESTART_EXIT=20') == 1
                             and lines.count(b'TRILLIONNIUM_A01_BOOT_OK') == 1
                             and b'Kernel panic' not in raw
                             and b'SQLITE_RESTART_ERROR' not in raw)
        value = {'negative_control': negative, 'crash': cut, 'reopen_exit': result.returncode,
                 'positive_oracle': positive_oracle, 'negative_rejected': negative_rejected,
                 'verify_serial_sha256': sha(raw), 'nonce': nonce}
        report['cases'].append(value)
        save(case / 'result.json', value)
        require(negative_rejected if negative else positive_oracle, 'SQLite guest restart assertion failed')
    require(pinned(args.kernel, args.expected_kernel_sha256, 64 * 1024 * 1024) == kernel,
            'kernel input changed')
    report['passed'] = True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--expected-kernel-sha256', required=True)
    parser.add_argument('--initramfs', type=Path, required=True)
    parser.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    parser.add_argument('--qemu', default='qemu-system-x86_64')
    parser.add_argument('--cc', default='cc')
    parser.add_argument('--mkfs', default='mkfs.ext2')
    parser.add_argument('--timeout', type=int, default=120)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    require(re.fullmatch('[0-9a-f]{64}', args.expected_kernel_sha256) is not None, 'invalid kernel digest')
    require(1 <= args.timeout <= 300, 'timeout must be 1..300 seconds')
    out = args.output.absolute()
    require(not out.exists() and not out.is_symlink(), 'output must be new')
    out.mkdir(parents=True, mode=0o700)
    report = {'schema': 'a04.sqlite-guest-restart.v1', 'passed': False,
              'scope': 'SQLite WAL across an abrupt guest-kernel restart on a fresh ext2 disk',
              'physical_power_loss': False, 'volatile_device_cache_loss': False,
              'hepta_original_owner': False, 'runner_sha256': sha(Path(__file__).read_bytes()),
              'probe_source_sha256': sha(Path(__file__).with_name('sqlite_restart_probe.c').read_bytes()),
              'kernel_build_provenance': 'caller must retain original build receipt'}
    try:
        run(args, out, report)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        report['error'] = f'{type(error).__name__}: {error}'
    save(out / 'result.json', report)
    print(json.dumps(report, sort_keys=True))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
