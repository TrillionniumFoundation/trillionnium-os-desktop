#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Exercise native boot identity and existing lifecycle prerequisites twice.

Requires an actual original ordinary-build receipt matching the supplied ELF.
The optional missing-file negative control retains a false positive verdict.
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

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'tests/organ_backend'))
from run_guest_probe import pack, unpack

CASES = ('uuid_format', 'stable_reopen', 'partial_reads', 'eof', 'write_denied',
         'unchanged_after_write', 'fork_same_uuid', 'pidfd_identity',
         'pidfd_alive_not_readable', 'pidfd_exit_readable',
         'clock_boottime_nondecreasing', 'hos2_same_boot')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value, message):
    if not value:
        raise ValueError(message)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--kernel', type=Path, required=True)
    parser.add_argument('--ordinary-receipt', type=Path, required=True)
    parser.add_argument('--expected-receipt-sha256', required=True)
    parser.add_argument('--initramfs', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--expect-missing', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    require(not out.exists(), 'output must be new')
    require(sha(args.ordinary_receipt) == args.expected_receipt_sha256, 'receipt identity mismatch')
    receipt = json.loads(args.ordinary_receipt.read_text())
    require(receipt['passed'] and receipt['source_inputs_unchanged'], 'ordinary source gate failed')
    require(sha(args.kernel) == receipt['kernel_elf_sha256'], 'actual ordinary ELF mismatch')
    require(args.kernel.read_bytes()[:4] == b'\x7fELF', 'not an ELF')
    out.mkdir(parents=True)
    source = Path(__file__).with_name('proc_boot_identity.c')
    original_codec = source.with_name('hos2_queryabi_probe.c')
    compiler = Path(shutil.which('cc')).resolve()
    command = [str(compiler), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-static',
               str(source), '-o', str(out / 'probe.elf')]
    compiled = subprocess.run(command, capture_output=True, timeout=90)
    (out / 'compile.log').write_bytes(compiled.stdout + compiled.stderr)
    require(compiled.returncode == 0, 'strict probe compilation failed')
    entries = unpack(gzip.decompress(args.initramfs.read_bytes()))
    marker = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
    invocation = (b'if /bin/proc-boot-identity --hos2-ioctl 0xC0204802; then\n'
                  b'  echo BOOT_ID_PROBE_EXIT=0\nelse\n  echo BOOT_ID_PROBE_EXIT=$?\nfi\n')
    patched, found = [], 0
    for name, fields, data in entries:
        if name.lstrip('./') == 'init':
            require(data.count(marker) == 1, 'original init completion is not unique')
            data = data.replace(marker, invocation + marker)
            found += 1
        require(name.lstrip('./') != 'bin/proc-boot-identity', 'probe already exists')
        patched.append((name, fields, data))
    require(found == 1, 'original init missing')
    ino = max(item[1][0] for item in entries) + 1
    patched.append(('bin/proc-boot-identity', [ino, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
                    (out / 'probe.elf').read_bytes()))
    archive = pack(patched)
    require(len(unpack(archive)) == len(entries) + 1, 'initramfs roundtrip failed')
    (out / 'initramfs.cpio.gz').write_bytes(gzip.compress(archive, mtime=0))
    shutil.copyfile('/usr/share/seabios/bios-256k.bin', out / 'bios.bin')
    qemu = Path(shutil.which('qemu-system-x86_64')).resolve()
    argv = [str(qemu), '-kernel', str(args.kernel.resolve()), '-initrd', str(out / 'initramfs.cpio.gz'),
            '-bios', str(out / 'bios.bin'), '-append',
            'earlycon console=ttyS0 loglevel=info SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --',
            '-machine', 'q35', '-accel', 'tcg', '-cpu', 'max', '-m', '512M', '-smp', '1',
            '-nodefaults', '-no-user-config', '-no-reboot', '-nographic', '-display', 'none',
            '-monitor', 'none', '-serial', 'stdio', '-nic', 'none',
            '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04']
    boots = []
    for index in range(1 if args.expect_missing else 2):
        timed_out = False
        serial = out / f'boot-{index + 1}.log'
        with serial.open('wb') as log:
            try:
                code = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=log,
                                      stderr=subprocess.STDOUT, timeout=120).returncode
            except subprocess.TimeoutExpired:
                code, timed_out = None, True
        text = re.sub(r'\x1b\[[0-9;]*m', '', serial.read_text(errors='replace')).replace('\r', '')
        cases = re.findall(r'^BOOT_ID_CASE name=(\S+) pass=([01])$', text, re.M)
        uuid = re.findall(r'^BOOT_ID_UUID=([0-9a-f-]{36})$', text, re.M)
        base = (code == 33 and not timed_out and text.count('TRILLIONNIUM_A01_BOOT_OK') == 1
                and not any(marker in text for marker in
                            ('Uncaught panic:', 'An uncaught panic occurred:', 'Non-resettable panic!')))
        positive = (base and tuple(name for name, _ in cases) == CASES and
                    all(ok == '1' for _, ok in cases) and len(uuid) == 1 and
                    text.count('BOOT_ID_COMPLETE cases=12 failures=0') == 1 and
                    text.count('BOOT_ID_PROBE_EXIT=0') == 1 and 'BOOT_ID_UNAVAILABLE' not in text)
        negative = (base and not cases and not uuid and
                    text.count('BOOT_ID_UNAVAILABLE errno=2') == 1 and
                    text.count('BOOT_ID_PROBE_EXIT=1') == 1 and 'BOOT_ID_COMPLETE' not in text)
        boots.append({'raw_qemu_exit': code, 'timed_out': timed_out, 'cases': cases,
                      'uuid': uuid[0] if len(uuid) == 1 else None,
                      'passed': positive, 'missing_file_negative_matched': negative,
                      'serial_sha256': sha(serial)})
    qualified = (not args.expect_missing and all(b['passed'] for b in boots)
                 and boots[0]['uuid'] != boots[1]['uuid'])
    negative = args.expect_missing and boots[0]['missing_file_negative_matched']
    report = {'schema': 'hepta.native-boot-identity-abi.v1', 'source_head': receipt['source_head'],
              'source_tree': receipt['source_tree'], 'kernel_sha256': sha(args.kernel),
              'ordinary_receipt_sha256': sha(args.ordinary_receipt), 'probe_source_sha256': sha(source),
              'original_codec_sha256': sha(original_codec), 'runner_sha256': sha(Path(__file__)),
              'probe_sha256': sha(out / 'probe.elf'), 'compiler_sha256': sha(compiler),
              'qemu_sha256': sha(qemu), 'bios_sha256': sha(out / 'bios.bin'),
              'original_initramfs_sha256': sha(args.initramfs),
              'injected_initramfs_sha256': sha(out / 'initramfs.cpio.gz'), 'qemu_argv': argv,
              'compile_argv': command, 'boots': boots, 'guest_deadline_seconds': 120,
              'expected_missing_negative': args.expect_missing, 'passed': qualified,
              'negative_control_matched': negative, 'production_authority': False,
              'g2_complete': False, 'hardware_or_entropy_qualification': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': qualified, 'negative_control_matched': negative, 'boots': len(boots)}))
    return 0 if qualified or negative else 1


if __name__ == '__main__':
    raise SystemExit(main())
