#!/usr/bin/env python3
"""Record a fixed Linux RLIMIT_NOFILE reference and replay it on an ordinary kernel.

The guest consumes the exact ELF and complete Linux execution record created by
the reference subcommand. Ordinary product build/source validation, pinned boot
inputs and newc processing reuse the reviewed SCM_RIGHTS runner. This additional
37-case profile does not replace the fixed Debian 13 qualification.
"""
import argparse
import gzip
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
COMMON_PATH = Path(__file__).with_name('run_scm_rights_cloexec_guest.py')
common_spec = importlib.util.spec_from_file_location('a04_scm_guest', COMMON_PATH)
common = importlib.util.module_from_spec(common_spec)
common_spec.loader.exec_module(common)
GROUP_PATH = Path(__file__).resolve().parents[2] / 'integration/hepta/run_original_agentd.py'
group_spec = importlib.util.spec_from_file_location('a04_child_group', GROUP_PATH)
groups = importlib.util.module_from_spec(group_spec)
group_spec.loader.exec_module(groups)
require, sha = common.require, common.sha
read_file, read_pinned = common.read_file, common.read_pinned

CASE_ORDER = (
    'open_exhaustion', 'lowered_limit_fd_number', 'zero_limit', 'dup_and_fcntl',
    'open_no_side_effects', 'pipe_one_slot', 'socketpair_one_slot', 'pipe_copyout_fault',
    'socketpair_copyout_fault', 'accept_preserves_queue', 'accept_copyout_fault',
    'socket_limit', 'eventfd_limit', 'timerfd_limit', 'epoll_limit', 'inotify_limit',
    'memfd_limit', 'signalfd_limit_and_update', 'pidfd_open_limit', 'pty_peer_limit',
    'allocators_compete', 'reserved_dup2_collision', 'fork_ignores_reservation',
    'cloexec_marks_reservation', 'shared_table_distinct_limits',
    'stream_rights_none', 'stream_rights_partial', 'stream_rights_peek',
    'stream_rights_copy_fault', 'datagram_rights_none', 'datagram_rights_partial',
    'datagram_rights_peek', 'datagram_rights_copy_fault', 'seqpacket_rights_none',
    'seqpacket_rights_partial', 'seqpacket_rights_peek', 'seqpacket_rights_copy_fault',
)
CASE_COUNT = 37
COMPLETE = 'NOFILE_COMPLETE total=37 passed=37 failed=0'
PROCESS_EXIT = 'NOFILE_PROCESS_EXIT=0'
BOOT_MARKER = common.BOOT_MARKER
PROBE_PATH = 'bin/rlimit-nofile-probe'
LOG_LIMIT = 8 * 1024 * 1024
# The old kernel logs every syscall in the bounded reservation-observer loops.
# Keep Linux logs small, but preserve the complete diagnostic serial stream.
SERIAL_LIMIT = 64 * 1024 * 1024


def log_lines(raw):
    return re.sub(r'\x1b\[[0-9;]*m', '', raw.decode(errors='replace')).splitlines()


def evaluate_probe(raw):
    lines = log_lines(raw)
    pattern = re.compile(r'NOFILE_CASE name=(\w+) result=(PASS|FAIL) line=(\d+)(?: signal=(\d+))?')
    observed = [pattern.fullmatch(line) for line in lines if line.startswith('NOFILE_CASE')]
    parsed = [match.groups() for match in observed if match is not None]
    valid_signals = all(sig is None or result == 'FAIL' and line == '0' and 1 <= int(sig) <= 64
                        for _, result, line, sig in parsed)
    complete = (len(observed) == CASE_COUNT and len(parsed) == CASE_COUNT and valid_signals
                and tuple(item[0] for item in parsed) == CASE_ORDER)
    passed = complete and all(result == 'PASS' and line == '0' and sig is None
                              for _, result, line, sig in parsed)
    summaries = [line for line in lines if line.startswith('NOFILE_COMPLETE')]
    summary = (re.fullmatch(r'NOFILE_COMPLETE total=(\d+) passed=(\d+) failed=(\d+)', summaries[0])
               if len(summaries) == 1 else None)
    totals = tuple(map(int, summary.groups())) if summary else None
    success_count = sum(result == 'PASS' and line == '0' and sig is None
                        for _, result, line, sig in parsed)
    consistent = complete and totals == (CASE_COUNT, success_count, CASE_COUNT - success_count)
    ordered = (summary is not None
               and all(index < lines.index(summaries[0]) for index, line in enumerate(lines)
                       if line.startswith('NOFILE_CASE')))
    no_failure = not any(line.startswith(('NOFILE_ASSERT', 'NOFILE_SETUP')) for line in lines)
    return {'cases': [{'name': name, 'result': result, 'line': int(line),
                       **({'signal': int(sig)} if sig else {})}
                      for name, result, line, sig in parsed],
            'cases_complete': complete, 'cases_passed': passed,
            'summary_totals': totals, 'summary_consistent': consistent,
            'cases_before_summary': ordered, 'no_probe_failure': no_failure,
            'probe_passed': passed and consistent and ordered and no_failure
                            and summaries == [COMPLETE]}


def evaluate_reference(stdout, stderr, code, timed_out):
    result = evaluate_probe(stdout)
    expected = [f'NOFILE_CASE name={name} result=PASS line=0' for name in CASE_ORDER] + [COMPLETE]
    result['passed'] = (type(code) is int and code == 0 and timed_out is False and stderr == b''
                        and stdout == ('\n'.join(expected) + '\n').encode()
                        and result['probe_passed'])
    return result


def evaluate_guest(raw, code, timed_out):
    result = evaluate_probe(raw)
    lines = log_lines(raw)
    exits = [line for line in lines if line.startswith('NOFILE_PROCESS_EXIT=')]
    markers = (COMPLETE, PROCESS_EXIT, BOOT_MARKER)
    exact = exits == [PROCESS_EXIT] and all(lines.count(marker) == 1 for marker in markers)
    ordered = (exact and [lines.index(marker) for marker in markers]
               == sorted(lines.index(marker) for marker in markers))
    parsed_exit = (re.fullmatch(r'NOFILE_PROCESS_EXIT=(-?\d+)', exits[0])
                   if len(exits) == 1 else None)
    no_panic = not re.search(r'(?i)kernel panic|panicked at|fatal exception', '\n'.join(lines))
    result.update(probe_exit=int(parsed_exit.group(1)) if parsed_exit else None,
                  exact_exit_and_boot=exact, ordered_completion=ordered, no_kernel_panic=no_panic,
                  passed=type(code) is int and code == 33 and timed_out is False
                  and result['probe_passed'] and ordered and no_panic)
    return result


def build_initramfs(original, probe):
    entries = common.unpack(gzip.decompress(original))
    require(common.unpack(common.pack(entries)) == entries, 'original newc roundtrip differs')
    marker = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
    injected = b'''if /bin/rlimit-nofile-probe; then
    nofile_probe_exit=0
else
    nofile_probe_exit=$?
fi
echo "NOFILE_PROCESS_EXIT=$nofile_probe_exit"
'''
    changed, found = [], 0
    for name, fields, content in entries:
        require(name.lstrip('./') != PROBE_PATH, 'probe already present')
        if name.lstrip('./') == 'init':
            require(content.count(marker) == 1 and b'set -eu' in content, 'invalid original init')
            content = content.replace(marker, injected + marker)
            fields = fields.copy()
            fields[6] = len(content)
            found += 1
        changed.append((name, fields, content))
    require(found == 1, 'original init is missing or ambiguous')
    ino = max(entry[1][0] for entry in entries) + 1
    changed.append((PROBE_PATH,
                    [ino, 0o100755, 0, 0, 1, 0, len(probe), 0, 0, 0, 0, len(PROBE_PATH) + 1, 0],
                    probe))
    require(common.unpack(common.pack(changed)) == changed, 'injected newc roundtrip differs')
    require(len(changed) == len(entries) + 1, 'initramfs lost original entries')
    return gzip.compress(common.pack(changed), mtime=0)


def require_static_probe(path, probe):
    require(probe[:6] == b'\x7fELF\x02\x01' and probe[18:20] == b'\x3e\x00',
            'probe is not x86_64 ELF')
    headers = subprocess.run(['readelf', '-l', str(path)], capture_output=True, check=True, timeout=10)
    require(b'INTERP' not in headers.stdout, 'probe requires a dynamic interpreter')


def load_reference(directory, expected_sha):
    receipt_bytes = read_file(directory / 'result.json', 1024 * 1024)
    receipt = json.loads(receipt_bytes)
    require(receipt['schema'] == 'a04.rlimit-nofile-linux.v1', 'unknown Linux receipt')
    require(receipt['passed'] is True and receipt['probe_inputs_unchanged'] is True
            and receipt['runner_inputs_unchanged'] is True
            and receipt['process_group_cleanup_completed'] is True,
            'Linux reference did not pass')
    require(receipt['probe_sha256'] == expected_sha, 'Linux reference differs from frozen ELF digest')
    probe = read_pinned(directory / 'probe.elf', expected_sha, 16 * 1024 * 1024)
    require(read_file(directory / 'probe.sha256', 1024) == f'{expected_sha}  probe.elf\n'.encode(),
            'pre-execution Linux digest differs')
    frozen_input = json.loads(read_pinned(directory / 'input.json', receipt['frozen_input_sha256']))
    require(frozen_input['probe_sha256'] == expected_sha
            and frozen_input['schema'] == receipt['schema'], 'pre-execution Linux input differs')
    stdout = read_pinned(directory / 'stdout.log', receipt['stdout_sha256'], LOG_LIMIT)
    stderr = read_pinned(directory / 'stderr.log', receipt['stderr_sha256'], LOG_LIMIT)
    require(read_file(directory / 'exit-code.txt', 64) == f"{receipt['process_exit']}\n".encode(),
            'recorded Linux process exit differs')
    result = evaluate_reference(stdout, stderr, receipt['process_exit'], receipt['timed_out'])
    require(result['passed'], 'Linux reference is incomplete or failed')
    return probe, sha(receipt_bytes)


def reference_process(command, directory, timeout_seconds=100):
    """Run in our private session; finish anchored group cleanup before reaping.

    The fixed C probe never calls setsid. This standalone process is the sole
    reaper of its leader; the shared guard rejects loss of that identity.
    """
    if not groups.child_anchor_available():
        raise groups.GateError('waitable_child_anchor_required_before_spawn')
    timed_out = False
    with (directory / 'stdout.log').open('xb') as stdout, (directory / 'stderr.log').open('xb') as stderr:
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stdout,
                                   stderr=stderr, start_new_session=True)
        group = groups.ChildGroup(process)
        try:
            group.wait_exit(timeout_seconds)
        except subprocess.TimeoutExpired:
            timed_out = True
        except KeyboardInterrupt:
            groups.terminate_group(group)
            raise groups.GateError('reference_interrupted') from None
        # Success and signal exits can both leave descendants. The guard uses
        # WNOWAIT until all TERM/grace/KILL signals finish, then returns the real
        # leader status. Do not call Popen.wait/poll before this cleanup.
        code = groups.terminate_group(group)
    return code, timed_out


def run_reference(args, out, report):
    probe = read_pinned(args.probe_elf, args.expected_probe_sha256, 16 * 1024 * 1024)
    frozen = out / 'probe.elf'
    frozen.write_bytes(probe)
    frozen.chmod(0o700)
    require_static_probe(frozen, probe)
    # Freeze before execution, and execute this private copy instead of the mutable build path.
    (out / 'probe.sha256').write_text(f'{args.expected_probe_sha256}  probe.elf\n')
    report.update(probe_sha256=sha(probe), command=[str(frozen)],
                  host_kernel=os.uname().release, host_arch=os.uname().machine)
    frozen_input = (json.dumps(report, indent=2, sort_keys=True) + '\n').encode()
    (out / 'input.json').write_bytes(frozen_input)
    report['frozen_input_sha256'] = sha(frozen_input)
    start = time.monotonic()
    code, timed_out = reference_process([str(frozen)], out)
    report.update(process_exit=code, timed_out=timed_out, elapsed_seconds=time.monotonic() - start,
                  process_group_cleanup_completed=True)
    (out / 'exit-code.txt').write_text(f'{code}\n')
    stdout = read_file(out / 'stdout.log', LOG_LIMIT)
    stderr = read_file(out / 'stderr.log', LOG_LIMIT)
    report.update(stdout_sha256=sha(stdout), stderr_sha256=sha(stderr))
    report.update(evaluate_reference(stdout, stderr, code, timed_out))
    require(read_file(frozen) == probe, 'reference ELF changed during execution')
    require(read_pinned(args.probe_elf, args.expected_probe_sha256) == probe,
            'build ELF changed during reference execution')
    require(read_file(out / 'input.json') == frozen_input, 'pre-execution input changed during reference')
    require(read_file(out / 'probe.sha256', 1024) == f'{args.expected_probe_sha256}  probe.elf\n'.encode(),
            'pre-execution digest changed during reference')
    report['probe_inputs_unchanged'] = True


def record_guest_run(report, serial, code, timed_out, elapsed_seconds):
    # Preserve actual process facts even if the subsequent bounded log read or
    # verdict fails. QEMU exit alone cannot turn an incomplete record green.
    report.update(passed=False, qemu_exit=code, timed_out=timed_out, elapsed_seconds=elapsed_seconds)
    raw = read_file(serial, SERIAL_LIMIT)
    report.update(serial_sha256=sha(raw), serial_bytes=len(raw))
    report.update(evaluate_guest(raw, code, timed_out))


def run_guest(args, out, report):
    kernel, receipt_sha = common.product_input(args.product_evidence, args.expected_source_head,
                                                args.expected_source_tree)
    probe, reference_sha = load_reference(args.linux_reference, args.expected_probe_sha256)
    original = read_pinned(args.a01_initramfs, common.INITRD_SHA, LOG_LIMIT)
    bios = read_pinned(args.bios, common.BIOS_SHA, 2 * 1024 * 1024)
    initrd = build_initramfs(original, probe)
    inputs = (('kernel.elf', kernel), ('probe.elf', probe), ('bios.bin', bios),
              ('initramfs.cpio.gz', initrd))
    for name, data in inputs:
        (out / name).write_bytes(data)
    require_static_probe(out / 'probe.elf', probe)
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
    report.update(source_head=args.expected_source_head, source_tree=args.expected_source_tree,
                  kernel_sha256=sha(kernel), probe_sha256=sha(probe), bios_sha256=sha(bios),
                  original_initramfs_sha256=sha(original), initramfs_sha256=sha(initrd),
                  product_receipt_sha256=receipt_sha, linux_reference_receipt_sha256=reference_sha,
                  qemu_version=version, qemu_launcher_sha256=sha(Path(binary).read_bytes()),
                  qemu_argv=command)
    start, code, timed_out = time.monotonic(), None, False
    with (out / 'serial.log').open('xb') as log:
        try:
            code = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=log,
                                  stderr=subprocess.STDOUT, timeout=args.timeout, check=False).returncode
        except subprocess.TimeoutExpired:
            timed_out = True
    record_guest_run(report, out / 'serial.log', code, timed_out, time.monotonic() - start)
    for name, data in inputs:
        require(read_file(out / name) == data, f'guest input changed during execution: {name}')
    require(load_reference(args.linux_reference, args.expected_probe_sha256) == (probe, reference_sha),
            'Linux reference changed during guest execution')
    report['guest_inputs_unchanged'] = True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    reference = commands.add_parser('reference', help='Run one already compiled ELF on original Linux')
    reference.add_argument('--probe-elf', type=Path, required=True)
    guest = commands.add_parser('guest', help='Replay exactly the verified Linux reference ELF')
    guest.add_argument('--product-evidence', type=Path, required=True)
    guest.add_argument('--expected-source-head', required=True)
    guest.add_argument('--expected-source-tree', required=True)
    guest.add_argument('--linux-reference', type=Path, required=True)
    guest.add_argument('--a01-initramfs', type=Path, required=True)
    guest.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    guest.add_argument('--qemu', default='qemu-system-x86_64')
    guest.add_argument('--timeout', type=int, default=120)
    for command in (reference, guest):
        command.add_argument('--expected-probe-sha256', required=True)
        command.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    out = args.output.absolute()
    require(not out.exists() and not out.is_symlink(), 'output must be a new directory')
    if args.mode == 'guest':
        require(1 <= args.timeout <= 120, 'timeout must be 1..120 seconds')
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    helpers = (Path(__file__), COMMON_PATH,
               Path(__file__).resolve().parents[2] / 'organ_backend/run_guest_probe.py', GROUP_PATH)
    helper_bytes = {path: read_file(path, 1024 * 1024) for path in helpers}
    report = {'schema': f'a04.rlimit-nofile-{"linux" if args.mode == "reference" else "guest"}.v1',
              'passed': False, 'scope': '37 RLIMIT_NOFILE allocation/receiver cases',
              'pinned_debian13_qualification': False,
              'runner_sha256': sha(helper_bytes[helpers[0]]),
              'product_helper_sha256': sha(helper_bytes[helpers[1]]),
              'cpio_helper_sha256': sha(helper_bytes[helpers[2]]),
              'process_group_helper_sha256': sha(helper_bytes[helpers[3]])}
    try:
        (run_reference if args.mode == 'reference' else run_guest)(args, out, report)
        for path, data in helper_bytes.items():
            require(read_file(path) == data, f'runner/helper changed during execution: {path.name}')
        report['runner_inputs_unchanged'] = True
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, groups.GateError) as error:
        report.update(passed=False, error=f'{type(error).__name__}: {error}')
    (out / 'result.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({key: report[key] for key in
                     ('passed', 'process_exit', 'probe_exit', 'qemu_exit', 'cases_complete', 'error')
                     if key in report}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
