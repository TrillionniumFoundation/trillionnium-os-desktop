#!/usr/bin/env python3
"""Run the exec argument regression on an ordinary A06 product kernel.

The original product build/boot gate supplies the kernel. This runner compiles
the tracked C regression and injects it into the pinned A01 initramfs. An
optional separately pinned product source permits a before-fix comparison
without claiming that the baseline kernel was built from the new probe source.
"""
import argparse
import gzip
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from run_scm_rights_cloexec_guest import (
    BIOS_SHA, BOOT_MARKER, INITRD_SHA, pack, product_input, read_file,
    read_pinned, require, sha, unpack,
)
sys.path.insert(0, str(ROOT / 'tests/kernel/control'))
from run_queryabi_candidate_guest import source_snapshot

SOURCE = 'kernel/asterinas/test/initramfs/src/regression/process/execve/execve_args.c'
COMMON = 'kernel/asterinas/test/initramfs/src/regression/common/test.h'
GROUPS = (
    ('combined_argv_envp_exact_limit', 2),
    ('argv_alone_exact_limit', 2),
    ('execveat_shares_the_total_limit', 2),
    ('stack_limit_has_a_128k_floor', 2),
    ('stack_limit_uses_one_quarter', 2),
    ('stack_limit_has_a_6m_ceiling', 2),
    ('empty_strings_still_consume_pointer_storage', 2),
    ('single_string_limit_includes_nul', 2),
    ('shebang_replacement_consumes_the_same_budget', 2),
    ('null_vectors_remain_accepted', 1),
)
PROCESS_EXIT = 'EXEC_ARG_BUDGET_PROCESS_EXIT=0'


def build_initramfs(original, probe):
    entries = unpack(gzip.decompress(original))
    require(unpack(pack(entries)) == entries, 'original newc roundtrip differs')
    marker = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
    injected = b'''if /bin/execve-arg-budget; then
    exec_arg_budget_exit=0
else
    exec_arg_budget_exit=$?
fi
echo "EXEC_ARG_BUDGET_PROCESS_EXIT=$exec_arg_budget_exit"
'''
    changed, found = [], 0
    for name, fields, content in entries:
        require(name.lstrip('./') != 'bin/execve-arg-budget', 'probe already present')
        if name.lstrip('./') == 'init':
            require(content.count(marker) == 1 and b'set -eu' in content, 'invalid original init')
            content = content.replace(marker, injected + marker)
            found += 1
        changed.append((name, fields, content))
    require(found == 1, 'original init is missing or ambiguous')
    ino = max(e[1][0] for e in entries) + 1
    changed.append(('bin/execve-arg-budget',
                    [ino, 0o100755, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0], probe))
    require(len(unpack(pack(changed))) == len(entries) + 1, 'initramfs lost original entries')
    return gzip.compress(pack(changed), mtime=0)


def evaluate(raw, code, timed_out):
    text = re.sub(r'\x1b\[[0-9;]*m', '', raw.decode(errors='replace'))
    lines = text.splitlines()
    summary = re.compile(r'test_(\w+) summary: (\d+) tests passed, (\d+) tests failed')
    passed = re.compile(r'test_(\w+): `.*` passed \[got Success\]')
    summaries, counts, unexpected = [], {}, []
    for index, line in enumerate(lines):
        if not line.startswith('test_'):
            continue
        if match := summary.fullmatch(line):
            name, good, bad = match.groups()
            summaries.append((name, int(good), int(bad), index))
        elif match := passed.fullmatch(line):
            name = match.group(1)
            counts.setdefault(name, []).append(index)
        else:
            unexpected.append(line)
    expected = [(name, count, 0) for name, count in GROUPS]
    exact = ([(name, good, bad) for name, good, bad, _ in summaries] == expected
             and set(counts) == {name for name, _ in GROUPS}
             and all(len(counts.get(name, [])) == count for name, count in GROUPS))
    ordered = exact
    previous = -1
    for name, _, _, index in summaries:
        ordered = ordered and all(previous < item < index for item in counts.get(name, []))
        previous = index
    marker_counts = {marker: lines.count(marker) for marker in (PROCESS_EXIT, BOOT_MARKER)}
    markers = (all(count == 1 for count in marker_counts.values())
               and sum(line.startswith('EXEC_ARG_BUDGET_PROCESS_EXIT=') for line in lines) == 1)
    ordered = (ordered and markers and previous < lines.index(PROCESS_EXIT) < lines.index(BOOT_MARKER))
    no_failure = (not unexpected
                  and not re.search(r'(?i)kernel panic|panicked at|fatal exception|fatal error:|unexpected child status=', text))
    return {'groups': [{'name': n, 'passed': p, 'failed': f} for n, p, f, _ in summaries],
            'checks_passed': sum(len(items) for items in counts.values()),
            'exact_case_counts': exact, 'ordered_completion': bool(ordered),
            'marker_counts': marker_counts, 'unexpected_records': unexpected,
            'no_failure': no_failure,
            'passed': type(code) is int and code == 33 and timed_out is False
                      and bool(ordered) and no_failure}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--product-evidence', type=Path, required=True)
    parser.add_argument('--expected-source-head', required=True)
    parser.add_argument('--expected-source-tree', required=True)
    parser.add_argument('--product-source-head')
    parser.add_argument('--product-source-tree')
    parser.add_argument('--a01-initramfs', type=Path, required=True)
    parser.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    parser.add_argument('--qemu', default='qemu-system-x86_64')
    parser.add_argument('--cc', default='cc')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=90)
    args = parser.parse_args(argv)
    out = args.output.absolute()
    require(not out.exists() and not out.is_symlink(), 'output must be a new directory')
    require(not out.resolve().is_relative_to(ROOT.resolve()), 'evidence must be outside the source checkout')
    require(1 <= args.timeout <= 120, 'timeout must be 1..120 seconds')
    require(bool(args.product_source_head) == bool(args.product_source_tree), 'baseline head/tree must be supplied together')
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    product_head = args.product_source_head or args.expected_source_head
    product_tree = args.product_source_tree or args.expected_source_tree
    report = {'schema': 'a06.exec-argument-budget.v1', 'passed': False,
              'scope': '19 exec/execveat argument admission checks on one ordinary x86_64 kernel',
              'probe_source_head': args.expected_source_head, 'probe_source_tree': args.expected_source_tree,
              'product_source_head': product_head, 'product_source_tree': product_tree,
              'memory_controller_qualified': False, 'physical_memory_reserve_qualified': False,
              'runner_sha256': sha(Path(__file__).read_bytes())}
    try:
        before = source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
        for name in (SOURCE, COMMON, 'tests/workloads/linux/run_exec_arg_budget_guest.py',
                     'tests/workloads/linux/run_scm_rights_cloexec_guest.py',
                     'tests/organ_backend/run_guest_probe.py'):
            require(name in before['files'], 'execution input is not tracked by the reviewed commit')
        (out / 'source-before.json').write_text(json.dumps(before, sort_keys=True) + '\n')
        kernel, product_receipt_sha = product_input(args.product_evidence, product_head, product_tree)
        command = [args.cc, '-std=gnu11', '-O2', '-Wall', '-Wextra', '-Werror',
                   '-D__asterinas__', '-static', '-no-pie', str(ROOT / SOURCE), '-o', str(out / 'probe.elf')]
        compiled = subprocess.run(command, capture_output=True, timeout=60, check=False)
        (out / 'compile.log').write_bytes(compiled.stdout + compiled.stderr)
        report.update(compiler_command=command, compile_exit=compiled.returncode,
                      probe_source_sha256=before['files'][SOURCE]['sha256'],
                      common_header_sha256=before['files'][COMMON]['sha256'])
        require(compiled.returncode == 0, 'static C regression compile failed')
        probe = read_file(out / 'probe.elf', 16 * 1024 * 1024)
        headers = subprocess.run(['readelf', '-l', str(out / 'probe.elf')], capture_output=True, check=True, timeout=10)
        require(probe[:6] == b'\x7fELF\x02\x01' and probe[18:20] == b'\x3e\x00'
                and b'INTERP' not in headers.stdout, 'probe is not a static x86_64 ELF')
        original = read_pinned(args.a01_initramfs, INITRD_SHA, 8 * 1024 * 1024)
        bios = read_pinned(args.bios, BIOS_SHA, 2 * 1024 * 1024)
        initrd = build_initramfs(original, probe)
        inputs = {'kernel.elf': kernel, 'probe.elf': probe, 'bios.bin': bios, 'initramfs.cpio.gz': initrd}
        for name, data in inputs.items():
            (out / name).write_bytes(data)
        binary = shutil.which(args.qemu)
        require(binary is not None, 'QEMU unavailable')
        version = subprocess.check_output([binary, '--version'], timeout=10).decode()
        require(version.startswith('QEMU emulator version 8.2.2 '), 'unreviewed QEMU version')
        command = [binary, '-kernel', str(out / 'kernel.elf'), '-initrd', str(out / 'initramfs.cpio.gz'),
                   '-append', 'earlycon console=ttyS0 loglevel=warn SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --',
                   '-machine', 'q35', '-accel', 'tcg', '-cpu', 'max', '-bios', str(out / 'bios.bin'),
                   '-m', '512M', '-smp', '1', '-nodefaults', '-no-user-config', '-no-reboot',
                   '-nographic', '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
                   '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04']
        report.update(product_receipt_sha256=product_receipt_sha, kernel_sha256=sha(kernel),
                      probe_sha256=sha(probe), bios_sha256=sha(bios), initramfs_sha256=sha(initrd),
                      original_initramfs_sha256=sha(original), qemu_version=version,
                      qemu_sha256=sha(Path(binary).read_bytes()), qemu_argv=command)
        start, code, timed_out = time.monotonic(), None, False
        with (out / 'serial.log').open('xb') as log:
            try:
                code = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                      timeout=args.timeout, check=False).returncode
            except subprocess.TimeoutExpired:
                timed_out = True
        raw = read_file(out / 'serial.log', 8 * 1024 * 1024)
        report.update(qemu_exit=code, timed_out=timed_out, elapsed_seconds=time.monotonic() - start,
                      raw_serial_sha256=sha(raw), raw_serial_size=len(raw))
        report.update(evaluate(raw, code, timed_out))
        after = source_snapshot(ROOT, args.expected_source_head, args.expected_source_tree)
        (out / 'source-after.json').write_text(json.dumps(after, sort_keys=True) + '\n')
        require(before == after, 'source changed during the guest')
        for name, data in inputs.items():
            require(read_file(out / name) == data, f'guest input changed: {name}')
        report.update(source_inputs_unchanged=True, guest_inputs_unchanged=True)
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report.update(passed=False, error=f'{type(error).__name__}: {error}')
    (out / 'result.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({k: report[k] for k in ('passed', 'checks_passed', 'qemu_exit', 'error') if k in report}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
