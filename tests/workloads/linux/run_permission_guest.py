#!/usr/bin/env python3
"""Compare real chmod/chown/mount permission observations on Linux and Asterinas.

Reference execution requires root and a new private Linux mount namespace. The
guest consumes the frozen reference ELF and the existing ordinary product gate.
UID/GID, supplementary groups, capability masks and metadata are checked from
raw observations independently of the C probe's PASS labels. No cases are skipped.
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
SHARED_PATH = Path(__file__).with_name('run_rlimit_nofile_guest.py')
shared_spec = importlib.util.spec_from_file_location('permission_shared', SHARED_PATH)
shared = importlib.util.module_from_spec(shared_spec)
shared_spec.loader.exec_module(shared)
common, groups = shared.common, shared.groups
require, sha, read_file, read_pinned = common.require, common.sha, common.read_file, common.read_pinned
ROOT = Path(__file__).resolve().parents[3]
PROBE_SOURCE = Path(__file__).with_name('permission_probe.c')
SOURCE_FILES = (Path(__file__).resolve(), PROBE_SOURCE, SHARED_PATH.resolve(),
                shared.COMMON_PATH.resolve(), shared.GROUP_PATH.resolve(),
                ROOT / 'tests/organ_backend/run_guest_probe.py')
OWNER, OTHER, MEMBER, FOREIGN = 65534, 65533, 65532, 65531
CAP_CHOWN, CAP_FOWNER, CAP_FSETID, CAP_SYS_ADMIN = 1, 1 << 3, 1 << 4, 1 << 21
LOG_LIMIT = 8 * 1024 * 1024
SERIAL_LIMIT = 64 * 1024 * 1024
PROBE_PATH = 'bin/permission-probe'
PROCESS_EXIT = 'PERMISSION_PROCESS_EXIT=0'
BOOT_MARKER = common.BOOT_MARKER


def file_spec(actor=OTHER, caps=0, member=False, gid=OWNER, mode=0o644,
              final_uid=OWNER, final_gid=None, final_mode=None, error=1, fsuid_owner=False,
              ctime_advance=False):
    return {'actor': actor, 'caps': caps, 'member': member, 'fsuid_owner': fsuid_owner,
            'before': (OWNER, gid, mode),
            'after': (final_uid, gid if final_gid is None else final_gid,
                      mode if final_mode is None else final_mode), 'errno': error, 'mount': None,
            'ctime_advance': ctime_advance}


def mount_spec(kind, actor=OTHER, caps=0, error=1):
    return {'actor': actor, 'caps': caps, 'member': False, 'fsuid_owner': False,
            'errno': error, 'mount': kind}


# This independent oracle is intentionally not generated from the C case table.
SPECS = {
    'chmod_nonowner_path': file_spec(),
    'chmod_nonowner_fd': file_spec(),
    'chmod_nonowner_at': file_spec(),
    'chmod_owner': file_spec(actor=OWNER, final_mode=0o600, error=0),
    'chmod_fowner': file_spec(caps=CAP_FOWNER, final_mode=0o600, error=0),
    'chmod_chown_cap_denied': file_spec(caps=CAP_CHOWN),
    'chmod_owner_sgid_member': file_spec(actor=OWNER, member=True, gid=MEMBER, final_mode=0o2755, error=0),
    'chmod_owner_sgid_nonmember': file_spec(actor=OWNER, gid=MEMBER, final_mode=0o755, error=0),
    'chmod_owner_sgid_fsetid': file_spec(actor=OWNER, caps=CAP_FSETID, gid=MEMBER, final_mode=0o2755, error=0),
    'chown_nonowner_path': file_spec(),
    'chown_nonowner_fd': file_spec(),
    'chown_nonowner_at': file_spec(),
    'chown_nonowner_same_uid': file_spec(),
    'chown_nonowner_noop': file_spec(error=0, ctime_advance=True),
    'chown_owner_uid_denied': file_spec(actor=OWNER),
    'chown_owner_group_primary': file_spec(actor=OWNER, gid=MEMBER, final_gid=OWNER, error=0),
    'chown_owner_group_member': file_spec(actor=OWNER, member=True, final_gid=MEMBER, error=0),
    'chown_owner_group_denied': file_spec(actor=OWNER),
    'chown_cap': file_spec(caps=CAP_CHOWN, final_uid=OTHER, final_gid=FOREIGN, error=0),
    'chown_fowner_denied': file_spec(caps=CAP_FOWNER),
    'chown_regular_clear_setid': file_spec(actor=OWNER, mode=0o6755, final_mode=0o755, error=0),
    'chown_directory_keep_setid': file_spec(actor=OWNER, mode=0o2775, error=0),
    'chmod_fsuid_owner': file_spec(final_mode=0o600, error=0, fsuid_owner=True),
    'mount_nonroot_denied': mount_spec('mount'),
    'mount_root_without_cap_denied': mount_spec('mount', actor=0),
    'mount_sysadmin': mount_spec('mount', caps=CAP_SYS_ADMIN, error=0),
    'umount_nonroot_denied': mount_spec('umount'),
    'umount_root_without_cap_denied': mount_spec('umount', actor=0),
    'umount_sysadmin': mount_spec('umount', caps=CAP_SYS_ADMIN, error=0),
    'mount_missing_path': mount_spec('mount_missing', error=2),
    'umount_missing_path': mount_spec('umount_missing', error=2),
    'pivot_without_cap': mount_spec('pivot'),
}
CASE_ORDER = tuple(SPECS)
CASE_COUNT = len(CASE_ORDER)
COMPLETE = f'PERMISSION_COMPLETE total={CASE_COUNT} passed={CASE_COUNT} failed=0'
OBS_KEYS = ('name ruid euid suid fsuid rgid egid sgid fsgid groups_count group '
            'effective permitted inheritable rc errno before_uid before_gid before_mode '
            'before_ino before_dev before_ctime_sec before_ctime_nsec '
            'after_uid after_gid after_mode after_ino after_dev after_ctime_sec after_ctime_nsec '
            'marker_before marker_after').split()


def parse_observation(line):
    tokens = line.split(' ')
    if tokens[0] != 'PERMISSION_OBSERVATION' or len(tokens) != len(OBS_KEYS) + 1:
        return None
    pairs = [token.split('=', 1) for token in tokens[1:]]
    if any(len(pair) != 2 for pair in pairs) or [pair[0] for pair in pairs] != OBS_KEYS:
        return None
    if not re.fullmatch(r'[a-z0-9_]+', pairs[0][1]):
        return None
    if any(not re.fullmatch(r'-?[0-9]{1,20}', value) for _, value in pairs[1:]):
        return None
    return {key: value if key == 'name' else int(value) for key, value in pairs}


def check_observation(row):
    if row is None or row['name'] not in SPECS:
        return {'name': None if row is None else row['name'], 'passed': False,
                'failed_conditions': ['malformed_or_unknown_observation']}
    spec = SPECS[row['name']]
    actor = spec['actor']
    expected = {'ruid': OWNER if spec['fsuid_owner'] else actor, 'euid': actor,
                'suid': OWNER if spec['fsuid_owner'] else actor,
                'fsuid': OWNER if spec['fsuid_owner'] else actor,
                'rgid': actor, 'egid': actor, 'sgid': actor, 'fsgid': actor,
                'groups_count': int(spec['member']), 'group': MEMBER if spec['member'] else -1,
                'effective': spec['caps'], 'permitted': spec['caps'], 'inheritable': 0,
                'rc': -1 if spec['errno'] else 0, 'errno': spec['errno']}
    failed = [key for key, value in expected.items() if row[key] != value]
    for prefix in ('before', 'after'):
        if not all(0 <= row[f'{prefix}_{key}'] < (1 << 64) for key in ('uid', 'gid', 'ino', 'dev')):
            failed.append(prefix + '_unsigned_metadata')
        if not 0 <= row[prefix + '_mode'] <= 0o7777 or not 0 <= row[prefix + '_ctime_nsec'] < 1000000000:
            failed.append(prefix + '_mode_or_time_range')
    if spec['errno']:
        failed.extend('denied_changed_' + key for key in
                      ('uid', 'gid', 'mode', 'ino', 'dev', 'ctime_sec', 'ctime_nsec')
                      if row['before_' + key] != row['after_' + key])
    if spec['mount'] is None:
        failed.extend('file_identity_changed_' + key for key in ('ino', 'dev')
                      if row['before_' + key] != row['after_' + key])
        if spec['ctime_advance'] and ((row['after_ctime_sec'], row['after_ctime_nsec'])
                                      <= (row['before_ctime_sec'], row['before_ctime_nsec'])):
            failed.append('successful_noop_chown_did_not_advance_ctime')
        for prefix in ('before', 'after'):
            failed.extend(prefix + '_' + key for key, value in zip(('uid', 'gid', 'mode'), spec[prefix])
                          if row[prefix + '_' + key] != value)
        if row['marker_before'] != -1 or row['marker_after'] != -1:
            failed.append('file_marker_values')
    else:
        before = 0 if spec['mount'] == 'umount' else 1
        after = before if spec['errno'] else (1 if spec['mount'] == 'umount' else 0)
        if (row['marker_before'], row['marker_after']) != (before, after):
            failed.append('underlying_mount_marker_visibility')
    return {'name': row['name'], 'passed': not failed, 'failed_conditions': failed}


def evaluate_probe(raw):
    lines = shared.log_lines(raw)
    observations = [parse_observation(line) for line in lines if line.startswith('PERMISSION_OBSERVATION')]
    checks = [check_observation(row) for row in observations]
    pattern = re.compile(r'PERMISSION_CASE name=([a-z0-9_]+) result=(PASS|FAIL) line=(\d+)(?: signal=(\d+))?')
    case_lines = [line for line in lines if line.startswith('PERMISSION_CASE')]
    matches = [pattern.fullmatch(line) for line in case_lines]
    parsed = [match.groups() for match in matches if match]
    complete = (len(observations) == CASE_COUNT and all(row is not None for row in observations)
                and tuple(row['name'] for row in observations) == CASE_ORDER
                and len(matches) == len(parsed) == CASE_COUNT
                and tuple(row[0] for row in parsed) == CASE_ORDER)
    labels_passed = complete and all(status == 'PASS' and line == '0' and sig is None
                                    for _, status, line, sig in parsed)
    summaries = [line for line in lines if line.startswith('PERMISSION_COMPLETE')]
    observed_sequence = []
    for line in lines:
        if line.startswith('PERMISSION_OBSERVATION'):
            observed_sequence.append(('observation', parse_observation(line)))
        elif line.startswith('PERMISSION_CASE'):
            match = pattern.fullmatch(line)
            observed_sequence.append(('case', match.group(1) if match else None))
        elif line.startswith('PERMISSION_COMPLETE'):
            observed_sequence.append(('complete', line))
    expected_sequence = []
    if complete:
        for row in observations:
            expected_sequence.extend([('observation', row), ('case', row['name'])])
        expected_sequence.append(('complete', COMPLETE))
    ordered = complete and observed_sequence == expected_sequence
    no_failure = not any(line.startswith(('PERMISSION_ASSERT', 'PERMISSION_SETUP')) for line in lines)
    known = ('PERMISSION_OBSERVATION ', 'PERMISSION_CASE ', 'PERMISSION_COMPLETE ', 'PERMISSION_PROCESS_EXIT=')
    no_unknown = not any(line.startswith('PERMISSION_') and not line.startswith(known) for line in lines)
    passed = (complete and labels_passed and all(check['passed'] for check in checks)
              and summaries == [COMPLETE] and ordered and no_failure and no_unknown)
    return {'cases': [{'name': n, 'result': r, 'line': int(l), **({'signal': int(s)} if s else {})}
                      for n, r, l, s in parsed], 'observations': observations,
            'observation_checks': checks, 'cases_complete': complete, 'cases_passed': labels_passed,
            'observations_passed': len(checks) == CASE_COUNT and all(c['passed'] for c in checks),
            'ordered_case_observations': ordered, 'summary_markers': summaries,
            'no_probe_failure': no_failure, 'no_unknown_probe_markers': no_unknown, 'probe_passed': passed}


def evaluate_reference(stdout, stderr, code, timed_out):
    result = evaluate_probe(stdout)
    lines = shared.log_lines(stdout)
    exact_stdout = (stdout == ('\n'.join(lines) + '\n').encode()
                    and len(lines) == CASE_COUNT * 2 + 1
                    and all(line.startswith(('PERMISSION_OBSERVATION ', 'PERMISSION_CASE ', 'PERMISSION_COMPLETE '))
                            for line in lines))
    result['passed'] = (type(code) is int and code == 0 and timed_out is False and stderr == b''
                        and result['probe_passed'] and exact_stdout)
    return result


def evaluate_guest(raw, code, timed_out):
    result = evaluate_probe(raw)
    lines = shared.log_lines(raw)
    exits = [line for line in lines if line.startswith('PERMISSION_PROCESS_EXIT=')]
    markers = (COMPLETE, PROCESS_EXIT, BOOT_MARKER)
    exact = exits == [PROCESS_EXIT] and all(lines.count(marker) == 1 for marker in markers)
    ordered = exact and [lines.index(marker) for marker in markers] == sorted(lines.index(marker) for marker in markers)
    no_panic = not re.search(r'(?i)kernel panic|panicked at|fatal exception', '\n'.join(lines))
    result.update(exact_exit_and_boot=exact, ordered_completion=ordered, no_kernel_panic=no_panic,
                  passed=type(code) is int and code == 33 and timed_out is False
                  and result['probe_passed'] and ordered and no_panic)
    return result


def build_initramfs(original, probe):
    entries = common.unpack(gzip.decompress(original))
    require(common.unpack(common.pack(entries)) == entries, 'original newc roundtrip differs')
    marker = b'echo "TRILLIONNIUM_A01_BOOT_OK"'
    injected = b'''if /bin/permission-probe --work-dir /permission-work; then
    permission_probe_exit=0
else
    permission_probe_exit=$?
fi
echo "PERMISSION_PROCESS_EXIT=$permission_probe_exit"
'''
    changed, found = [], 0
    for name, fields, content in entries:
        require(name.lstrip('./') not in (PROBE_PATH, 'permission-work'), 'permission input already present')
        if name.lstrip('./') == 'init':
            require(content.count(marker) == 1 and b'set -eu' in content, 'invalid original init')
            content = content.replace(marker, injected + marker)
            fields = fields.copy()
            fields[6] = len(content)
            found += 1
        changed.append((name, fields, content))
    require(found == 1, 'original init missing or ambiguous')
    ino = max(entry[1][0] for entry in entries) + 1
    changed.append((PROBE_PATH, [ino, 0o100755, 0, 0, 1, 0, len(probe), 0, 0, 0, 0, len(PROBE_PATH) + 1, 0], probe))
    require(common.unpack(common.pack(changed)) == changed, 'injected newc roundtrip differs')
    require(len(changed) == len(entries) + 1, 'initramfs lost original entries')
    return gzip.compress(common.pack(changed), mtime=0)


def source_inputs():
    return {str(path.relative_to(ROOT)): {'bytes': len(raw), 'sha256': sha(raw)}
            for path in SOURCE_FILES for raw in [read_file(path, LOG_LIMIT)]}


def load_reference(directory, expected_sha):
    receipt_bytes = read_file(directory / 'result.json', LOG_LIMIT)
    receipt = json.loads(receipt_bytes)
    require(receipt['schema'] == 'a04.permissions-linux.v1', 'unknown Linux permission receipt')
    require(all(receipt[key] is True for key in ('passed', 'probe_inputs_unchanged', 'runner_inputs_unchanged',
                                                'process_group_cleanup_completed')),
            'Linux permission reference did not pass')
    require(receipt['private_mount_namespace'] is True, 'reference lacked a private mount namespace')
    require(receipt['source_inputs'] == source_inputs(), 'Linux reference source inputs differ')
    require(receipt['probe_sha256'] == expected_sha, 'reference differs from frozen ELF digest')
    probe = read_pinned(directory / 'probe.elf', expected_sha, 16 * 1024 * 1024)
    require(read_file(directory / 'probe.sha256', 1024) == f'{expected_sha}  probe.elf\n'.encode(), 'frozen probe digest changed')
    frozen = json.loads(read_pinned(directory / 'input.json', receipt['frozen_input_sha256'], LOG_LIMIT))
    require(frozen['schema'] == receipt['schema'] and frozen['probe_sha256'] == expected_sha
            and frozen['source_inputs'] == receipt['source_inputs']
            and frozen['command'] == receipt['command'] and frozen['private_mount_namespace'] is True,
            'pre-execution reference input differs')
    stdout = read_pinned(directory / 'stdout.log', receipt['stdout_sha256'], LOG_LIMIT)
    stderr = read_pinned(directory / 'stderr.log', receipt['stderr_sha256'], LOG_LIMIT)
    require(read_file(directory / 'exit-code.txt', 64) == f"{receipt['process_exit']}\n".encode(), 'Linux exit receipt differs')
    result = evaluate_reference(stdout, stderr, receipt['process_exit'], receipt['timed_out'])
    require(result['passed'], 'Linux permission raw observations failed independent validation')
    return probe, sha(receipt_bytes)


def run_reference(args, out, report):
    require(os.geteuid() == 0, 'reference requires root in a disposable Linux CI host')
    probe = read_pinned(args.probe_elf, args.expected_probe_sha256, 16 * 1024 * 1024)
    frozen = out / 'probe.elf'
    frozen.write_bytes(probe)
    frozen.chmod(0o700)
    shared.require_static_probe(frozen, probe)
    unshare = shutil.which('unshare')
    require(unshare is not None, 'unshare is required for isolated mount reference')
    command = [unshare, '--mount', '--propagation', 'private', '--', str(frozen), '--work-dir', str(out / 'work')]
    (out / 'probe.sha256').write_text(f'{args.expected_probe_sha256}  probe.elf\n')
    report.update(probe_sha256=sha(probe), command=command, host_kernel=os.uname().release,
                  host_arch=os.uname().machine, private_mount_namespace=True,
                  unshare_sha256=sha(Path(unshare).read_bytes()))
    frozen_input = (json.dumps(report, indent=2, sort_keys=True) + '\n').encode()
    (out / 'input.json').write_bytes(frozen_input)
    report['frozen_input_sha256'] = sha(frozen_input)
    started = time.monotonic()
    code, timed_out = shared.reference_process(command, out, timeout_seconds=args.timeout)
    report.update(process_exit=code, timed_out=timed_out, elapsed_seconds=time.monotonic() - started,
                  process_group_cleanup_completed=True)
    (out / 'exit-code.txt').write_text(f'{code}\n')
    stdout, stderr = read_file(out / 'stdout.log', LOG_LIMIT), read_file(out / 'stderr.log', LOG_LIMIT)
    report.update(stdout_sha256=sha(stdout), stderr_sha256=sha(stderr), stdout_bytes=len(stdout), stderr_bytes=len(stderr))
    report.update(evaluate_reference(stdout, stderr, code, timed_out))
    require(read_file(frozen) == probe and read_pinned(args.probe_elf, args.expected_probe_sha256) == probe,
            'reference or original probe ELF changed')
    require(read_file(out / 'input.json') == frozen_input, 'pre-execution input changed')
    require(read_file(out / 'probe.sha256', 1024) == f'{args.expected_probe_sha256}  probe.elf\n'.encode(), 'frozen digest changed')
    require(sha(Path(unshare).read_bytes()) == report['unshare_sha256'], 'namespace executable changed')
    report['probe_inputs_unchanged'] = True


def run_guest(args, out, report):
    kernel, product_sha = common.product_input(args.product_evidence, args.expected_source_head, args.expected_source_tree)
    snapshot = json.loads(read_file(args.product_evidence / 'source-before.json', LOG_LIMIT))['files']
    for name, identity in report['source_inputs'].items():
        require(name in snapshot and snapshot[name]['sha256'] == identity['sha256']
                and snapshot[name]['size'] == identity['bytes'], 'permission source is not bound to product snapshot: ' + name)
    probe, reference_sha = load_reference(args.linux_reference, args.expected_probe_sha256)
    original = read_pinned(args.a01_initramfs, common.INITRD_SHA, LOG_LIMIT)
    bios = read_pinned(args.bios, common.BIOS_SHA, 2 * 1024 * 1024)
    initrd = build_initramfs(original, probe)
    inputs = (('kernel.elf', kernel), ('probe.elf', probe), ('bios.bin', bios), ('initramfs.cpio.gz', initrd))
    for name, data in inputs:
        (out / name).write_bytes(data)
    shared.require_static_probe(out / 'probe.elf', probe)
    binary = shutil.which(args.qemu)
    require(binary is not None, 'QEMU unavailable')
    version = subprocess.check_output([binary, '--version'], timeout=10).decode()
    require(version.startswith('QEMU emulator version 8.2.2 '), 'unreviewed QEMU version')
    command = [binary, '-kernel', str(out / 'kernel.elf'), '-initrd', str(out / 'initramfs.cpio.gz'),
               '-append', 'earlycon console=ttyS0 loglevel=info SHELL=/bin/sh LOGNAME=root HOME=/ USER=root PATH=/bin:/sbin --',
               '-machine', 'q35', '-accel', 'tcg', '-cpu', 'max', '-bios', str(out / 'bios.bin'),
               '-m', '512M', '-smp', '1', '-nodefaults', '-no-user-config', '-no-reboot',
               '-nographic', '-display', 'none', '-monitor', 'none', '-serial', 'stdio', '-nic', 'none',
               '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04']
    report.update(source_head=args.expected_source_head, source_tree=args.expected_source_tree,
                  kernel_sha256=sha(kernel), probe_sha256=sha(probe), bios_sha256=sha(bios),
                  original_initramfs_sha256=sha(original), initramfs_sha256=sha(initrd),
                  product_receipt_sha256=product_sha, linux_reference_receipt_sha256=reference_sha,
                  qemu_version=version, qemu_launcher_sha256=sha(Path(binary).read_bytes()), qemu_argv=command)
    started, code, timed_out = time.monotonic(), None, False
    with (out / 'serial.log').open('xb') as log:
        try:
            code = subprocess.run(command, stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                                  timeout=args.timeout, check=False).returncode
        except subprocess.TimeoutExpired:
            timed_out = True
    report.update(passed=False, qemu_exit=code, timed_out=timed_out, elapsed_seconds=time.monotonic() - started)
    raw = read_file(out / 'serial.log', SERIAL_LIMIT)
    report.update(serial_bytes=len(raw), serial_sha256=sha(raw))
    report.update(evaluate_guest(raw, code, timed_out))
    for name, data in inputs:
        require(read_file(out / name) == data, 'guest input changed: ' + name)
    require(load_reference(args.linux_reference, args.expected_probe_sha256) == (probe, reference_sha), 'Linux reference changed')
    require(common.product_input(args.product_evidence, args.expected_source_head, args.expected_source_tree)
            == (kernel, product_sha), 'ordinary product evidence changed')
    require(sha(Path(binary).read_bytes()) == report['qemu_launcher_sha256'], 'QEMU executable changed')
    report['guest_inputs_unchanged'] = True


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='mode', required=True)
    reference = commands.add_parser('reference', help='Execute fixed ELF inside a private Linux mount namespace')
    reference.add_argument('--probe-elf', type=Path, required=True)
    guest = commands.add_parser('guest', help='Run the same verified reference ELF on an ordinary product kernel')
    for name in ('product-evidence', 'linux-reference', 'a01-initramfs'):
        guest.add_argument('--' + name, type=Path, required=True)
    guest.add_argument('--expected-source-head', required=True)
    guest.add_argument('--expected-source-tree', required=True)
    guest.add_argument('--bios', type=Path, default=Path('/usr/share/seabios/bios-256k.bin'))
    guest.add_argument('--qemu', default='qemu-system-x86_64')
    for command in (reference, guest):
        command.add_argument('--expected-probe-sha256', required=True)
        command.add_argument('--output', type=Path, required=True)
        command.add_argument('--timeout', type=int, default=120)
    args = parser.parse_args(argv)
    out = args.output.absolute()
    require(not out.exists() and not out.is_symlink(), 'output must be a new directory')
    require(1 <= args.timeout <= 180, 'timeout must be 1..180 seconds')
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    report = {'schema': f'a04.permissions-{"linux" if args.mode == "reference" else "guest"}.v1',
              'passed': False, 'scope': f'{CASE_COUNT} real chmod/chown/mount credential and metadata cases',
              'pinned_debian13_qualification': False, 'hepta_hos2_qualification': False,
              'source_inputs': source_inputs()}
    try:
        (run_reference if args.mode == 'reference' else run_guest)(args, out, report)
        require(source_inputs() == report['source_inputs'], 'permission source/runner inputs changed')
        report['runner_inputs_unchanged'] = True
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError, groups.GateError) as error:
        report.update(passed=False, error=f'{type(error).__name__}: {error}')
    (out / 'result.json').write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({key: report[key] for key in
                     ('passed', 'process_exit', 'qemu_exit', 'cases_complete', 'observations_passed', 'error') if key in report}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
