#!/usr/bin/env python3
"""Run the same precompiled SCM_RIGHTS probe on a reviewed ordinary kernel.

The input kernel must come from the existing A06 product build/boot gate. The
caller supplies its independently reviewed Git identity, not a new kernel hash
allowlist. This probe is an additional compatibility profile, separate from the
fixed Debian 13 ELF/rootfs qualification. No host disks or networking are used.
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
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "organ_backend"))
from run_guest_probe import BIOS_SHA, INITRD_SHA, pack, unpack

MAX_BYTES = 64 * 1024 * 1024
BOOT_MARKER = 'TRILLIONNIUM_A01_BOOT_OK'
COMPLETE = 'SCM_CLOEXEC_COMPLETE total=27 passed=27 failed=0'
SCENARIOS = (
    'plain_receive', 'cloexec_multifd', 'peek_cloexec_then_plain',
    'peek_plain_then_cloexec', 'truncated_control', 'discarded_control',
    'no_control_message', 'credentials_with_rights', 'exec_inheritance',
)
CASE_ORDER = tuple(f'{socket}.{case}' for socket in ('stream', 'datagram', 'seqpacket')
                   for case in SCENARIOS)


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def read_file(path, limit=MAX_BYTES):
    require(path.is_file() and not path.is_symlink(), f'input is not a regular file: {path}')
    require(path.stat().st_size <= limit, f'input exceeds size limit: {path}')
    return path.read_bytes()


def read_pinned(path, digest, limit=MAX_BYTES):
    require(re.fullmatch('[0-9a-f]{64}', digest) is not None, 'invalid SHA256')
    data = read_file(path, limit)
    require(sha(data) == digest, f'input SHA256 differs: {path}')
    return data


def product_input(directory, head, tree):
    require(re.fullmatch('[0-9a-f]{40}', head) is not None, 'invalid reviewed source head')
    require(re.fullmatch('[0-9a-f]{40}', tree) is not None, 'invalid reviewed source tree')
    receipt_bytes = read_file(directory / 'result.json', 1024 * 1024)
    receipt = json.loads(receipt_bytes)
    require(receipt['schema'] == 'a06.g1-queryabi-product-candidate.v1', 'unknown product receipt')
    require(receipt['passed'] is True and receipt['source_inputs_unchanged'] is True
            and receipt['stage'] == 'complete', 'product build/boot gate did not pass')
    require(receipt['product_wrapper_exit'] == 0 and receipt['product_boot_raw_exit'] == 33
            and receipt['qemu_exit'] == 33 and receipt['timed_out'] is False,
            'incomplete ordinary kernel and QueryAbi boot')
    require((receipt['source_head'], receipt['source_tree']) == (head, tree),
            'product receipt differs from independently reviewed source identity')
    snapshots = [json.loads(read_file(directory / name, 8 * 1024 * 1024)) for name in
                 ('source-before.json', 'source-after-boot.json', 'source-after-guest.json')]
    require(snapshots[0] == snapshots[1] == snapshots[2], 'product source snapshots changed')
    require((snapshots[0]['head'], snapshots[0]['tree']) == (head, tree)
            and len(snapshots[0]['files']) == receipt['source_file_count'],
            'product snapshot identity/count differs from receipt')
    kernel = read_pinned(directory / 'product-kernel.elf', receipt['kernel_elf_sha256'])
    require(kernel[:6] == b'\x7fELF\x02\x01' and kernel[18:20] == b'\x03\x00',
            'not the reviewed ordinary x86_64 multiboot ELF')
    return kernel, sha(receipt_bytes)


def build_initramfs(original, probe):
    entries = unpack(gzip.decompress(original))
    require(unpack(pack(entries)) == entries, 'original newc roundtrip differs')
    marker = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
    injected = b'''if /bin/scm-rights-cloexec-probe; then
    scm_probe_exit=0
else
    scm_probe_exit=$?
fi
echo "SCM_CLOEXEC_PROCESS_EXIT=$scm_probe_exit"
'''
    changed, found = [], 0
    for name, fields, content in entries:
        require(name.lstrip('./') != 'bin/scm-rights-cloexec-probe', 'probe already present')
        if name.lstrip('./') == 'init':
            require(content.count(marker) == 1 and b'set -eu' in content, 'invalid original init')
            # Capture the real probe status while permitting a diagnostic RED to
            # shut down normally. The verdict below still requires exit 0.
            content = content.replace(marker, injected + marker)
            found += 1
        changed.append((name, fields, content))
    require(found == 1, 'original init is missing or ambiguous')
    ino = max(e[1][0] for e in entries) + 1
    changed.append(('bin/scm-rights-cloexec-probe',
                    [ino, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0], probe))
    require(len(unpack(pack(changed))) == len(entries) + 1, 'initramfs lost original entries')
    return gzip.compress(pack(changed), mtime=0)


def evaluate(raw, code, timed_out):
    text = re.sub(r'\x1b\[[0-9;]*m', '', raw.decode(errors='replace'))
    lines = text.splitlines()
    pattern = re.compile(r'SCM_CLOEXEC_CASE name=(\S+) result=(PASS|FAIL) line=(\d+)')
    observed = [pattern.fullmatch(line) for line in lines if line.startswith('SCM_CLOEXEC_CASE')]
    parsed = [m.groups() for m in observed if m is not None]
    cases_complete = (len(observed) == 27 and len(parsed) == 27
                      and tuple(item[0] for item in parsed) == CASE_ORDER)
    cases_passed = cases_complete and all(result == 'PASS' and line == '0' for _, result, line in parsed)
    markers = (COMPLETE, 'SCM_CLOEXEC_PROCESS_EXIT=0', BOOT_MARKER)
    exact = (all(lines.count(m) == 1 for m in markers)
             and sum(line.startswith('SCM_CLOEXEC_COMPLETE') for line in lines) == 1
             and sum(line.startswith('SCM_CLOEXEC_PROCESS_EXIT=') for line in lines) == 1)
    ordered = (exact and [lines.index(m) for m in markers] == sorted(lines.index(m) for m in markers)
               and all(i < lines.index(COMPLETE) for i, line in enumerate(lines)
                       if line.startswith('SCM_CLOEXEC_CASE')))
    no_panic = not re.search(r'(?i)kernel panic|panicked at|fatal exception', text)
    no_assertion = not any(line.startswith('SCM_CLOEXEC_ASSERT') for line in lines)
    return {'cases': [{'name': n, 'result': r, 'line': int(l)} for n, r, l in parsed],
            'cases_complete': cases_complete, 'cases_passed': cases_passed,
            'exact_markers': exact, 'ordered_completion': ordered, 'no_kernel_panic': no_panic,
            'no_probe_assertion': no_assertion,
            'passed': type(code) is int and code == 33 and timed_out is False
                      and cases_passed and ordered and no_panic and no_assertion}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--product-evidence', type=Path, required=True)
    parser.add_argument('--expected-source-head', required=True)
    parser.add_argument('--expected-source-tree', required=True)
    parser.add_argument('--probe-elf', type=Path, required=True)
    parser.add_argument('--expected-probe-sha256', required=True)
    parser.add_argument('--a01-initramfs', type=Path, required=True)
    parser.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    parser.add_argument('--qemu', default='qemu-system-x86_64')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=60)
    args = parser.parse_args(argv)
    out = args.output.absolute()
    require(not out.exists() and not out.is_symlink(), 'output must be a new directory')
    require(1 <= args.timeout <= 120, 'timeout must be 1..120 seconds')
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    report = {'schema': 'a04.scm-rights-cloexec-guest.v1', 'passed': False,
              'scope': '27 SCM_RIGHTS/CLOEXEC cases on one ordinary x86_64 kernel',
              'pinned_debian13_qualification': False,
              'source_head': args.expected_source_head, 'source_tree': args.expected_source_tree,
              'runner_sha256': sha(Path(__file__).read_bytes()),
              'cpio_helper_sha256': sha((Path(__file__).resolve().parents[2] /
                                         'organ_backend/run_guest_probe.py').read_bytes())}
    try:
        kernel, receipt_sha = product_input(args.product_evidence, args.expected_source_head, args.expected_source_tree)
        probe = read_pinned(args.probe_elf, args.expected_probe_sha256, 16 * 1024 * 1024)
        require(probe[:6] == b'\x7fELF\x02\x01' and probe[18:20] == b'\x3e\x00', 'probe is not x86_64 ELF')
        headers = subprocess.run(['readelf', '-l', str(args.probe_elf)], capture_output=True, check=True, timeout=10)
        require(b'INTERP' not in headers.stdout, 'probe requires a dynamic interpreter')
        original = read_pinned(args.a01_initramfs, INITRD_SHA, 8 * 1024 * 1024)
        bios = read_pinned(args.bios, BIOS_SHA, 2 * 1024 * 1024)
        initrd = build_initramfs(original, probe)
        for name, data in (('kernel.elf', kernel), ('probe.elf', probe), ('bios.bin', bios), ('initramfs.cpio.gz', initrd)):
            (out / name).write_bytes(data)
        binary = shutil.which(args.qemu)
        require(binary is not None, 'QEMU unavailable')
        version = subprocess.check_output([binary, '--version'], timeout=10).decode()
        require(version.startswith('QEMU emulator version 8.2.2 '), 'unreviewed QEMU version')
        command = [binary, '-kernel', str(out / 'kernel.elf'), '-initrd', str(out / 'initramfs.cpio.gz'),
                   '-append', 'earlycon console=ttyS0 loglevel=info SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --',
                   '-machine', 'q35', '-accel', 'tcg', '-cpu', 'max', '-bios', str(out / 'bios.bin'),
                   '-m', '512M', '-smp', '1', '-nodefaults', '-no-user-config', '-no-reboot',
                   '-nographic', '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
                   '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04']
        report.update(kernel_sha256=sha(kernel), probe_sha256=sha(probe), bios_sha256=sha(bios),
                      original_initramfs_sha256=sha(original), initramfs_sha256=sha(initrd),
                      product_receipt_sha256=receipt_sha, qemu_version=version,
                      qemu_launcher_sha256=sha(Path(binary).read_bytes()), qemu_argv=command)
        start, code, timed_out = time.monotonic(), None, False
        with (out / 'serial.log').open('xb') as log:
            try:
                code = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                      timeout=args.timeout, check=False).returncode
            except subprocess.TimeoutExpired:
                timed_out = True
        raw = read_file(out / 'serial.log', 8 * 1024 * 1024)
        report.update(qemu_exit=code, timed_out=timed_out, elapsed_seconds=time.monotonic() - start,
                      serial_sha256=sha(raw), serial_bytes=len(raw))
        report.update(evaluate(raw, code, timed_out))
        for name, data in (('kernel.elf', kernel), ('probe.elf', probe), ('bios.bin', bios), ('initramfs.cpio.gz', initrd)):
            require(read_file(out / name) == data, f'guest input changed during execution: {name}')
        report['guest_inputs_unchanged'] = True
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report.update(passed=False, error=f'{type(error).__name__}: {error}')
    (out / 'result.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: report[k] for k in ('passed', 'qemu_exit', 'cases_complete', 'error') if k in report}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
