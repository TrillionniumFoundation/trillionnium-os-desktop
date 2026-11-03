#!/usr/bin/env python3
"""Compile one UDP regression ELF, verify it on Linux, then replay it on A06.

The C regression and its five-second alarm are unchanged. This profile reuses
the existing ordinary product admission, newc codec and anchored child cleanup;
it neither builds a second kernel nor qualifies the original Hepta lifecycle.
"""
import argparse
import gzip
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import time

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
COMMON_PATH = Path(__file__).with_name('run_scm_rights_cloexec_guest.py')
GROUP_PATH = ROOT / 'tests/integration/hepta/run_original_agentd.py'


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


common = load_module('udp_product_admission', COMMON_PATH)
groups = load_module('udp_child_group', GROUP_PATH)
require, sha = common.require, common.sha
read_file, read_pinned = common.read_file, common.read_pinned
SOURCE = 'kernel/asterinas/test/initramfs/src/regression/network/udp_local_error.c'
HEADER = 'kernel/asterinas/test/initramfs/src/regression/common/test.h'
EXPECTED_PATH = Path(__file__).with_name('udp_local_error.expected.stderr')
EXPECTED_SHA = '67178f9fdbe1e761bc9daad11b88f183658fc8ef7693c77db471464a627ac085'
INPUTS = (SOURCE, HEADER, str(Path(__file__).relative_to(ROOT)),
          str(EXPECTED_PATH.relative_to(ROOT)), str(COMMON_PATH.relative_to(ROOT)),
          str(GROUP_PATH.relative_to(ROOT)), 'tests/organ_backend/run_guest_probe.py')
CASES = (
    ('connected_error_is_read_once_and_delivery_recovers', 11),
    ('receive_consumes_error', 7),
    ('send_consumes_error', 8),
    ('unconnected_socket_ignores_port_unreachable_without_recverr', 4),
    ('connected_socket_ignores_errors_for_another_destination', 8),
    ('self_delivery_has_no_error', 5),
)
PROBE_PATH = 'bin/udp-local-error'
BEGIN = 'HEPTA_UDP_LOCAL_BEGIN nonce='
END = 'HEPTA_UDP_LOCAL_END nonce='
BOOT = 'TRILLIONNIUM_A01_BOOT_OK'
LOG_LIMIT = 8 * 1024 * 1024


def save(path, value):
    with path.open('x') as output:
        json.dump(value, output, indent=2, sort_keys=True)
        output.write('\n')


def source_inputs(head, tree):
    def git(*args):
        return subprocess.check_output(['git', *args], cwd=ROOT, timeout=30)
    require(re.fullmatch('[0-9a-f]{40}', head) is not None
            and re.fullmatch('[0-9a-f]{40}', tree) is not None, 'invalid reviewed Git identity')
    require(git('rev-parse', 'HEAD').decode().strip() == head
            and git('rev-parse', 'HEAD^{tree}').decode().strip() == tree, 'source identity differs')
    require(not git('status', '--porcelain', '--untracked-files=all'), 'source is not clean')
    files = {}
    for name in INPUTS:
        data = read_file(ROOT / name, 1024 * 1024)
        require(data == git('show', 'HEAD:' + name), 'uncommitted runtime input: ' + name)
        files[name] = {'size': len(data), 'sha256': sha(data)}
    return {'head': head, 'tree': tree, 'files': files}


def expected_output():
    return read_pinned(EXPECTED_PATH, EXPECTED_SHA, 16384)


def plain_lines(raw):
    return re.sub(rb'\x1b\[[0-?]*[ -/]*[@-~]', b'', raw).decode('utf-8', errors='replace').splitlines()


def evaluate_reference(stdout, stderr, code, timed_out):
    exact = stdout == b'' and stderr == expected_output()
    return {'exact_49_lines': exact, 'check_count': 43 if exact else None,
            'case_counts': list(CASES) if exact else [],
            'passed': type(code) is int and code == 0 and timed_out is False and exact}


def evaluate_guest(raw, code, timed_out, nonce):
    require(re.fullmatch('[0-9a-f]{64}', nonce) is not None, 'invalid guest nonce')
    lines = plain_lines(raw)
    expected = expected_output().decode('ascii').splitlines()
    relevant = [line for line in lines if line.startswith('test_')]
    begin, end = BEGIN + nonce, END + nonce + ' exit=0'
    starts = [line for line in lines if line.startswith(BEGIN)]
    ends = [line for line in lines if line.startswith(END)]
    exact = relevant == expected
    markers = starts == [begin] and ends == [end] and lines.count(BOOT) == 1
    ordered = (markers and lines.index(begin) < lines.index(end) < lines.index(BOOT)
               and all(lines.index(begin) < i < lines.index(end)
                       for i, line in enumerate(lines) if line.startswith('test_')))
    failure = bool(re.search(r'(?i)kernel panic|panicked at|fatal exception|fatal error:|HEPTA_KTRACE',
                             '\n'.join(lines)))
    return {'exact_49_lines': exact, 'check_count': 43 if exact else None,
            'case_counts': list(CASES) if exact else [], 'exact_markers': markers,
            'ordered_completion': ordered, 'no_guest_failure': not failure,
            'passed': type(code) is int and code == 33 and timed_out is False
                      and exact and ordered and not failure}


def require_static_elf(data):
    require(len(data) >= 64 and data[:7] == b'\x7fELF\x02\x01\x01'
            and struct.unpack_from('<HH', data, 16) == (2, 62), 'not a static x86_64 ET_EXEC ELF')
    offset = struct.unpack_from('<Q', data, 32)[0]
    size, count = struct.unpack_from('<HH', data, 54)
    require(size >= 56 and count > 0 and offset + size * count <= len(data), 'invalid ELF headers')
    for index in range(count):
        header = struct.unpack_from('<IIQQQQQQ', data, offset + size * index)
        require(header[0] != 3, 'PT_INTERP is forbidden')
        if header[0] == 2:
            start, length = header[2], header[5]
            require(length % 16 == 0 and start + length <= len(data), 'invalid PT_DYNAMIC')
            terminated = False
            for pos in range(start, start + length, 16):
                tag = struct.unpack_from('<q', data, pos)[0]
                require(tag not in (1, 0x7ffffffd, 0x7fffffff), 'dynamic library dependency is forbidden')
                if tag == 0:
                    terminated = True
                    break
            require(terminated, 'unterminated PT_DYNAMIC')


def execute(command, out, prefix, seconds, env):
    """Retain actual process status before evaluating logs or any success claim."""
    require(groups.child_anchor_available(), 'waitable child anchor required before spawn')
    save(out / (prefix + '-invocation.json'), {'argv': command, 'timeout_seconds': seconds, 'env': env})
    start, timed_out = time.monotonic(), False
    with (out / (prefix + '.stdout.log')).open('xb') as stdout, \
            (out / (prefix + '.stderr.log')).open('xb') as stderr:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                   env=env, start_new_session=True)
        group = groups.ChildGroup(process)
        try:
            group.wait_exit(seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
        except BaseException:
            groups.terminate_group(group)
            raise
        code = groups.terminate_group(group)
    receipt = {'returncode': code, 'timed_out': timed_out,
               'elapsed_seconds': time.monotonic() - start, 'process_group_cleanup_completed': True}
    save(out / (prefix + '-execution.json'), receipt)
    return receipt


def build_initramfs(original, probe, nonce):
    require(re.fullmatch('[0-9a-f]{64}', nonce) is not None, 'invalid guest nonce')
    entries = common.unpack(gzip.decompress(original))
    require(common.unpack(common.pack(entries)) == entries, 'original newc roundtrip differs')
    marker = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
    script = (f'echo "{BEGIN}{nonce}"\n'
              'if LC_ALL=C LANG=C /bin/udp-local-error; then udp_exit=0; else udp_exit=$?; fi\n'
              f'echo "{END}{nonce} exit=$udp_exit"\n').encode()
    changed, count = [], 0
    for name, fields, content in entries:
        require(name.lstrip('./') != PROBE_PATH, 'probe already present')
        if name.lstrip('./') == 'init':
            require(content.count(marker) == 1 and b'set -eu' in content, 'unexpected init')
            content = content.replace(marker, script + marker)
            fields = fields.copy()
            fields[6] = len(content)
            count += 1
        changed.append((name, fields, content))
    require(count == 1, 'missing or ambiguous init')
    inode = max(row[1][0] for row in entries) + 1
    changed.append((PROBE_PATH, [inode, 0o100755, 0, 0, 1, 0, len(probe), 0, 0, 0, 0,
                                 len(PROBE_PATH) + 1, 0], probe))
    require(common.unpack(common.pack(changed)) == changed, 'injected newc roundtrip differs')
    return gzip.compress(common.pack(changed), mtime=0)


def run_reference(args, out, report, snapshot):
    selected_cc = shutil.which(args.cc)
    require(selected_cc is not None, 'C compiler unavailable')
    cc = str(Path(selected_cc).resolve(strict=True))
    temporary = out / 'build-tmp'
    temporary.mkdir()
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C', 'TMPDIR': str(temporary)}
    probe = out / 'probe.elf'
    command = [cc, '-O2', '-std=gnu11', '-Wall', '-Wextra', '-Werror', '-static',
               str(out / 'source' / SOURCE), '-o', str(probe)]
    compiled = execute(command, out, 'compile', 60, env)
    report['compile'] = compiled
    require(type(compiled['returncode']) is int and compiled['returncode'] == 0
            and compiled['timed_out'] is False, 'static compiler failed or timed out')
    data = read_file(probe, 16 * 1024 * 1024)
    require_static_elf(data)
    probe.chmod(0o500)
    digest = sha(data)
    (out / 'probe.sha256').write_text(f'{digest}  probe.elf\n')
    frozen = {'schema': 'a06.udp-local-input.v1', 'source': snapshot,
              'probe_sha256': digest, 'expected_stderr_sha256': EXPECTED_SHA,
              'compiler_sha256': sha(read_file(Path(cc))),
              'compile_execution_sha256': sha(read_file(out / 'compile-execution.json')),
              'compile_invocation_sha256': sha(read_file(out / 'compile-invocation.json')),
              'compile_stdout_sha256': sha(read_file(out / 'compile.stdout.log', LOG_LIMIT)),
              'compile_stderr_sha256': sha(read_file(out / 'compile.stderr.log', LOG_LIMIT))}
    save(out / 'input.json', frozen)
    report.update(probe_sha256=digest, input_sha256=sha(read_file(out / 'input.json')),
                  host_kernel=os.uname().release, host_arch=os.uname().machine)
    run = execute([str(probe)], out, 'process', 15, {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'})
    report['process'] = run
    report['process_invocation_sha256'] = sha(read_file(out / 'process-invocation.json'))
    stdout, stderr = (read_file(out / ('process.' + stream + '.log'), LOG_LIMIT)
                      for stream in ('stdout', 'stderr'))
    report.update(stdout_sha256=sha(stdout), stderr_sha256=sha(stderr))
    report.update(evaluate_reference(stdout, stderr, run['returncode'], run['timed_out']))
    require(read_file(probe) == data and json.loads(read_file(out / 'input.json')) == frozen,
            'frozen reference inputs changed')
    require(read_file(out / 'probe.sha256', 128) == f'{digest}  probe.elf\n'.encode(),
            'pre-execution ELF digest changed')
    report['probe_inputs_unchanged'] = True


def load_reference(directory, digest, snapshot):
    raw = read_file(directory / 'result.json', 2 * 1024 * 1024)
    receipt = json.loads(raw)
    require(receipt['schema'] == 'a06.udp-local-linux.v1' and receipt['passed'] is True
            and receipt['source_inputs_unchanged'] is True and receipt['probe_inputs_unchanged'] is True,
            'Linux reference did not pass')
    require(receipt['source'] == snapshot and receipt['probe_sha256'] == digest,
            'Linux reference source or ELF differs')
    frozen = json.loads(read_pinned(directory / 'input.json', receipt['input_sha256']))
    require(frozen['source'] == snapshot and frozen['probe_sha256'] == digest
            and frozen['expected_stderr_sha256'] == EXPECTED_SHA, 'frozen Linux input differs')
    for name, item in snapshot['files'].items():
        read_pinned(directory / 'source' / name, item['sha256'])
    for name, key in (('compile-invocation.json', 'compile_invocation_sha256'),
                      ('compile.stdout.log', 'compile_stdout_sha256'),
                      ('compile.stderr.log', 'compile_stderr_sha256')):
        read_pinned(directory / name, frozen[key], LOG_LIMIT)
    compiled = json.loads(read_pinned(directory / 'compile-execution.json', frozen['compile_execution_sha256']))
    require(compiled == receipt['compile'] and type(compiled['returncode']) is int
            and compiled['returncode'] == 0 and compiled['timed_out'] is False, 'compiler receipt failed')
    process = json.loads(read_file(directory / 'process-execution.json'))
    read_pinned(directory / 'process-invocation.json', receipt['process_invocation_sha256'])
    require(process == receipt['process'] and process['process_group_cleanup_completed'] is True,
            'actual Linux execution record differs')
    stdout = read_pinned(directory / 'process.stdout.log', receipt['stdout_sha256'], LOG_LIMIT)
    stderr = read_pinned(directory / 'process.stderr.log', receipt['stderr_sha256'], LOG_LIMIT)
    require(evaluate_reference(stdout, stderr, process['returncode'], process['timed_out'])['passed'],
            'actual Linux output or exit failed')
    probe = read_pinned(directory / 'probe.elf', digest, 16 * 1024 * 1024)
    require_static_elf(probe)
    require(read_file(directory / 'probe.sha256', 128) == f'{digest}  probe.elf\n'.encode(),
            'pre-execution Linux digest differs')
    return probe, sha(raw)


def run_guest(args, out, report, snapshot):
    probe, linux_sha = load_reference(args.linux_reference, args.expected_probe_sha256, snapshot)
    kernel, product_sha = common.product_input(args.product_evidence, args.expected_source_head,
                                               args.expected_source_tree)
    product = json.loads(read_file(args.product_evidence / 'result.json'))
    require(product['product_configuration'] == 'ActionChoice::Run; no --cfg ktest'
            and b'HEPTA_KTRACE' not in kernel, 'not the ordinary uninstrumented product')
    require(all(type(product[name]) is int and product[name] == expected for name, expected in
                (('product_wrapper_exit', 0), ('product_boot_raw_exit', 33), ('qemu_exit', 33))),
            'ordinary product exits are not actual integer statuses')
    product_source = json.loads(read_file(args.product_evidence / 'source-before.json'))
    require(all(product_source['files'][name]['sha256'] == item['sha256']
                for name, item in snapshot['files'].items()), 'product runtime source inputs differ')
    original = read_pinned(args.a01_initramfs, common.INITRD_SHA, LOG_LIMIT)
    bios = read_pinned(args.bios, common.BIOS_SHA, 2 * 1024 * 1024)
    nonce = os.urandom(32).hex()
    initrd = build_initramfs(original, probe, nonce)
    inputs = {'kernel.elf': kernel, 'probe.elf': probe, 'bios.bin': bios, 'initramfs.cpio.gz': initrd}
    for name, data in inputs.items():
        (out / name).write_bytes(data)
    selected_qemu = shutil.which(args.qemu)
    require(selected_qemu is not None, 'QEMU unavailable')
    binary = str(Path(selected_qemu).resolve(strict=True))
    version = subprocess.check_output([binary, '--version'], timeout=10).decode()
    require(version.startswith('QEMU emulator version 8.2.2 '), 'unreviewed QEMU version')
    command = [binary, '-kernel', str(out / 'kernel.elf'), '-initrd', str(out / 'initramfs.cpio.gz'),
               '-append', 'earlycon console=ttyS0 loglevel=warn SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --',
               '-machine', 'q35', '-accel', 'tcg', '-cpu', 'max', '-bios', str(out / 'bios.bin'),
               '-m', '512M', '-smp', '1', '-nodefaults', '-no-user-config', '-no-reboot',
               '-nographic', '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
               '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04']
    report.update(kernel_sha256=sha(kernel), probe_sha256=sha(probe), original_initramfs_sha256=sha(original),
                  bios_sha256=sha(bios), initramfs_sha256=sha(initrd), nonce=nonce,
                  product_receipt_sha256=product_sha, linux_reference_receipt_sha256=linux_sha,
                  qemu_version=version, qemu_sha256=sha(read_file(Path(binary))))
    save(out / 'input.json', report)
    run = execute(command, out, 'qemu', 180, {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C'})
    report['qemu'] = run
    # -serial stdio writes guest bytes to stdout; QEMU diagnostics remain separate.
    serial = read_file(out / 'qemu.stdout.log', LOG_LIMIT)
    diagnostics = read_file(out / 'qemu.stderr.log', LOG_LIMIT)
    report.update(serial_sha256=sha(serial), qemu_stderr_sha256=sha(diagnostics))
    report.update(evaluate_guest(serial, run['returncode'], run['timed_out'], nonce))
    for name, data in inputs.items():
        require(read_file(out / name) == data, 'guest input changed: ' + name)
    require(load_reference(args.linux_reference, args.expected_probe_sha256, snapshot) == (probe, linux_sha),
            'Linux reference changed during guest')
    require(common.product_input(args.product_evidence, args.expected_source_head,
                                 args.expected_source_tree) == (kernel, product_sha), 'product changed during guest')
    report['guest_inputs_unchanged'] = True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    reference = commands.add_parser('reference', help='Compile once and run the frozen ELF on Linux')
    reference.add_argument('--cc', default='/usr/bin/gcc-13')
    guest = commands.add_parser('guest', help='Run that same ELF on the existing ordinary A06 product')
    guest.add_argument('--linux-reference', type=Path, required=True)
    guest.add_argument('--expected-probe-sha256', required=True)
    guest.add_argument('--product-evidence', type=Path, required=True)
    guest.add_argument('--a01-initramfs', type=Path, required=True)
    guest.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    guest.add_argument('--qemu', default='/usr/bin/qemu-system-x86_64')
    for command in (reference, guest):
        command.add_argument('--expected-source-head', required=True)
        command.add_argument('--expected-source-tree', required=True)
        command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    out = args.output.absolute()
    require(not out.exists() and not out.is_symlink() and not out.resolve().is_relative_to(ROOT.resolve()),
            'output must be new and outside the source checkout')
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    report = {'schema': f'a06.udp-local-{"linux" if args.mode == "reference" else "guest"}.v1',
              'passed': False, 'scope': '6 local UDP error/delivery cases; 43 checks',
              'original_agentd_lifecycle_qualified': False, 'remote_icmp_qualified': False,
              'production_authority_qualified': False, 'expected_stderr_sha256': EXPECTED_SHA}
    try:
        snapshot = source_inputs(args.expected_source_head, args.expected_source_tree)
        report['source'] = snapshot
        for name, item in snapshot['files'].items():
            target = out / 'source' / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(read_pinned(ROOT / name, item['sha256']))
        (run_reference if args.mode == 'reference' else run_guest)(args, out, report, snapshot)
        require(source_inputs(args.expected_source_head, args.expected_source_tree) == snapshot,
                'source inputs changed during execution')
        for name, item in snapshot['files'].items():
            read_pinned(out / 'source' / name, item['sha256'])
        report['source_inputs_unchanged'] = True
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, groups.GateError) as error:
        report.update(passed=False, error=f'{type(error).__name__}: {error}')
    save(out / 'result.json', report)
    print(json.dumps({key: report[key] for key in ('passed', 'schema', 'exact_49_lines', 'error') if key in report}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
