#!/usr/bin/env python3
# SPDX-License-Identifier: MPL-2.0
"""Run real procfs/process privilege checks against a retained ordinary ELF."""
import argparse
import gzip
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_proc_boot_identity import pack, unpack, require, sha

CASES = ('initial_nnp_agrees', 'per_thread_nnp', 'main_thread_nnp_unchanged',
         'child_sets_and_cannot_clear_nnp', 'parent_attests_child_nnp',
         'four_child_uids', 'four_child_gids', 'child_groups_empty',
         'five_child_capsets_zero', 'parent_uid_unchanged',
         'parent_nnp_unchanged', 'exec_preserves_identity')


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
    source = Path(__file__).with_name('proc_process_privileges.c')
    original_c = source.read_bytes()
    compiler = Path(shutil.which('cc')).resolve()
    command = [str(compiler), '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-pthread',
               '-static', str(source), '-o', str(out / 'probe.elf')]
    compiled = subprocess.run(command, capture_output=True, timeout=90)
    (out / 'compile.log').write_bytes(compiled.stdout + compiled.stderr)
    require(compiled.returncode == 0, 'strict probe compilation failed')
    entries = unpack(gzip.decompress(args.initramfs.read_bytes()))
    marker = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
    invocation = (b'if /bin/proc-process-privileges; then\n  echo PRIV_STATUS_PROBE_EXIT=0\n'
                  b'else\n  echo PRIV_STATUS_PROBE_EXIT=$?\nfi\n')
    patched, found = [], 0
    for name, fields, data in entries:
        if name.lstrip('./') == 'init':
            require(data.count(marker) == 1, 'original init completion is not unique')
            data = data.replace(marker, invocation + marker)
            found += 1
        require(name.lstrip('./') != 'bin/proc-process-privileges', 'probe already exists')
        patched.append((name, fields, data))
    require(found == 1, 'original init missing')
    ino = max(item[1][0] for item in entries) + 1
    patched.append(('bin/proc-process-privileges', [ino, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
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
    timed_out = False
    serial = out / 'serial.log'
    with serial.open('wb') as log:
        try:
            code = subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=log,
                                  stderr=subprocess.STDOUT, timeout=120).returncode
        except subprocess.TimeoutExpired:
            code, timed_out = None, True
    require(source.read_bytes() == original_c, 'probe changed during execution')
    text = re.sub(r'\x1b\[[0-9;]*m', '', serial.read_text(errors='replace')).replace('\r', '')
    cases = re.findall(r'^PRIV_STATUS_CASE name=(\S+) pass=([01])$', text, re.M)
    base = (code == 33 and not timed_out and text.count('TRILLIONNIUM_A01_BOOT_OK') == 1
            and not any(marker in text for marker in
                        ('Uncaught panic:', 'An uncaught panic occurred:', 'Non-resettable panic!')))
    passed = (not args.expect_missing and base and tuple(name for name, _ in cases) == CASES
              and all(ok == '1' for _, ok in cases)
              and text.count('PRIV_STATUS_SETUP_CHECK pass=1') == 1
              and text.count('PRIV_STATUS_EXEC_CHECK pass=1') == 1
              and text.count('PRIV_STATUS_COMPLETE cases=12 failures=0') == 1
              and text.count('PRIV_STATUS_PROBE_EXIT=0') == 1 and 'PRIV_STATUS_UNAVAILABLE' not in text)
    negative = (args.expect_missing and base and not cases
                and text.count('PRIV_STATUS_UNAVAILABLE field=NoNewPrivs') == 1
                and text.count('PRIV_STATUS_PROBE_EXIT=1') == 1 and 'PRIV_STATUS_COMPLETE' not in text)
    report = {'schema': 'hepta.native-process-privilege-abi.v1', 'source_head': receipt['source_head'],
              'source_tree': receipt['source_tree'], 'kernel_sha256': sha(args.kernel),
              'ordinary_receipt_sha256': sha(args.ordinary_receipt), 'probe_source_sha256': sha(source),
              'runner_sha256': sha(Path(__file__)),
              'shared_runner_sha256': sha(Path(__file__).with_name('run_proc_boot_identity.py')),
              'probe_sha256': sha(out / 'probe.elf'), 'compiler_sha256': sha(compiler),
              'qemu_sha256': sha(qemu), 'bios_sha256': sha(out / 'bios.bin'),
              'original_initramfs_sha256': sha(args.initramfs),
              'injected_initramfs_sha256': sha(out / 'initramfs.cpio.gz'), 'qemu_argv': argv,
              'compile_argv': command, 'raw_qemu_exit': code, 'timed_out': timed_out,
              'cases': cases, 'serial_sha256': sha(serial), 'guest_deadline_seconds': 120,
              'expected_missing_negative': args.expect_missing, 'passed': passed,
              'negative_control_matched': negative, 'production_authority': False, 'g2_complete': False}
    (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    print(json.dumps({'passed': passed, 'negative_control_matched': negative}))
    return 0 if passed or negative else 1


if __name__ == '__main__':
    raise SystemExit(main())
