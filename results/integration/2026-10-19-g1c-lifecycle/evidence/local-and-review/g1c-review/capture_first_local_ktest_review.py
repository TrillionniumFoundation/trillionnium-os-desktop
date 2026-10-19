#!/usr/bin/env python3
"""Independently enumerate and bind the first local G1-c ktest evidence."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import struct
import subprocess
import tomllib

WORK = Path('/workspace/scratch/499c7902de8e')
ROOT = WORK / 'r12-g1c'
EVIDENCE = WORK / 'r12-evidence'
RUN = EVIDENCE / 'local-full-ktest'
OUT = EVIDENCE / 'g1c-review' / 'first-local-ktest-72c8dff3-review.json'
SOURCE = '72c8dff3f0145a7e16b7095d48a3e7faaf192685'
TREE = 'e2089e2350772a6cb965b3131820abea499f767d'
FORMAT_SOURCE = 'ba0d049a3640ccff4734aa37d8e24eb7b3f61dcf'
FORMAT_TREE = '179b076747d19c3e07ee19a665e3968c33c598ce'
TOOLCHAIN = 'nightly-2026-07-21'
UPSTREAM_TREE = '96605cf64aeae2d34f29b97e85eff9315fe10a8e'
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def source_bytes(name, source=SOURCE):
    return git('show', source + ':' + name)


def file_record(path):
    data = path.read_bytes()
    try:
        relative = str(path.relative_to(EVIDENCE))
    except ValueError:
        relative = str(path)
    return {'path': relative, 'bytes': len(data), 'sha256': sha(data)}


def git_record(name, source=SOURCE):
    data = source_bytes(name, source)
    mode, kind, oid = git('ls-tree', source, '--', name).decode().split('\t', 1)[0].split()
    assert kind == 'blob'
    assert hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == oid
    return {'path': name, 'mode': mode, 'git_blob': oid, 'bytes': len(data), 'sha256': sha(data)}


assert git('rev-parse', SOURCE + '^{tree}').decode().strip() == TREE
assert git('rev-parse', FORMAT_SOURCE + '^{tree}').decode().strip() == FORMAT_TREE
assert git('rev-parse', FORMAT_SOURCE + '^').decode().strip() == SOURCE
attempt_path = EVIDENCE / 'local-host/full-ktest-attempt.json'
attempt = json.loads(attempt_path.read_bytes())
assert attempt['source_head'] == SOURCE and attempt['source_tree'] == TREE
phase_records = []
for phase, expected_name, log_name in zip(attempt['phases'], ['prepare-locks', 'full-ktest'],
                                          ['prepare-locks.log', 'full-ktest.log'], strict=True):
    assert phase['name'] == expected_name and type(phase['exit_code']) is int and phase['exit_code'] == 0
    record = file_record(EVIDENCE / 'local-host' / log_name)
    assert record['sha256'] == phase['log_sha256']
    phase_records.append({**phase, 'verified_log': record})

environment = json.loads((RUN / 'environment.json').read_bytes())
assert environment['git_head'] == SOURCE and environment['git_status'] == ''
assert environment['toolchain'] == TOOLCHAIN and environment['cargo_build_jobs'] == '2'
assert environment['test_name'] is None and environment['osdk_install_skipped'] is False
build_inputs = []
for name, expected in environment['build_inputs_sha256'].items():
    item = git_record(name)
    assert item['sha256'] == expected, name
    build_inputs.append(item)

tool_records = []
for executable in ('rustc', 'cargo'):
    path = WORK / ('r12-rustup/toolchains/' + TOOLCHAIN + '-x86_64-unknown-linux-gnu/bin/' + executable)
    version = subprocess.check_output([str(path), '-Vv']).decode()
    assert version == environment[executable]
    tool_records.append({**file_record(path), 'version_matches_record': True, 'version': version})
for name, path in [('osdk_sha256', WORK / 'r12-cargo/bin/cargo-osdk'),
                   ('vdso_sha256', ROOT / 'support/build/out/linux-vdso/vdso_x86_64.so')]:
    item = file_record(path)
    assert item['sha256'] == environment[name]
    tool_records.append({**item, 'matches_environment_key': name})

commands = json.loads((RUN / 'commands.json').read_bytes())
assert len(commands) == 3
assert commands[0]['argv'] == ['cargo', '+' + TOOLCHAIN, 'install', '--locked', 'cargo-osdk', '--path', 'osdk']
assert commands[0]['cwd'] == str(ROOT / 'kernel/asterinas')
assert 'Installed package `cargo-osdk v0.19.0' in (RUN / 'osdk-install.log').read_text()
assert str(WORK / 'r12-cargo/bin/cargo-osdk') in (RUN / 'osdk-install.log').read_text()

source_report = json.loads((RUN / 'source-inputs.json').read_bytes())
assert source_report['commit'] == 'c4b7ed575b7b32773475b194d2ad41fb6d03765b'
assert source_report['tree'] == UPSTREAM_TREE and source_report['toolchain'] == TOOLCHAIN
assert source_report['passed'] is True and source_report['errors'] == []
assert source_report['pristine'] is False and source_report['checked_files'] == 118
pinned_names = []
for row in git('ls-tree', '-r', '-z', UPSTREAM_TREE).split(b'\0'):
    if not row:
        continue
    metadata, name = row.split(b'\t', 1)
    mode, kind, oid = metadata.decode().split()
    name = name.decode()
    if name not in {'Cargo.lock', 'osdk/Cargo.lock', 'rust-toolchain.toml', 'Makefile', 'OSDK.toml', 'LICENSE-MPL'} and not name.endswith('Cargo.toml'):
        continue
    item = git_record('kernel/asterinas/' + name)
    assert item['mode'] == mode and kind == 'blob'
    derived = source_report['downstream_manifests'].get(name, source_report['downstream_locks'].get(name))
    if derived:
        assert derived['upstream_blob'] == oid
        assert sha(git('cat-file', 'blob', oid)) == derived['upstream_sha256']
        assert item['sha256'] == derived['derived_sha256']
    else:
        assert item['git_blob'] == oid
    if name in source_report['input_sha256']:
        assert item['sha256'] == source_report['input_sha256'][name]
    pinned_names.append(item)
assert len(pinned_names) == 118

prior = json.loads((EVIDENCE / 'g1c-review/implementation-review-v1.json').read_bytes())
expected_new_names = []
for case in prior['kernel_test_source_inventory']:
    stem = 'image' if case['path'].endswith('/image.rs') else 'init_proc'
    expected_new_names.append('aster_core::process::process::' + stem + '::tests::' + case['name'])
    assert '#[ktest]' in source_bytes(case['path']).decode()
    assert re.search(r'#\[ktest\]\s*fn\s+' + re.escape(case['name']) + r'\s*\(', source_bytes(case['path']).decode())
assert len(expected_new_names) == len(set(expected_new_names)) == 18
case_results = []
lock_results = []
kernel_outputs = []
seed_lock = tomllib.loads(git('show', UPSTREAM_TREE + ':Cargo.lock').decode())
seed_external = {(p['name'], p['version'], p.get('source')): p.get('checksum')
                 for p in seed_lock['package'] if p.get('source')}
for index, (crate, expected_count, subdir) in enumerate([('ostd', 221, 'ostd'), ('aster-core', 238, 'kernel/core')], 1):
    target = RUN / crate
    guest = target / 'guests/guest-001'
    assert sorted(p.name for p in (target / 'guests').iterdir()) == ['guest-001']
    command = commands[index]
    expected_args = ['cargo', '+' + TOOLCHAIN, 'osdk', 'test', '--release', '--boot-method=vmm-direct',
                     '--grub-boot-protocol=multiboot', '--qemu-exe=' + str(ROOT / 'support/build/ktest/record-qemu.py'),
                     '--kcmd-args=loglevel=error', '--kcmd-args=earlycon', '--kcmd-args=console=ttyS0']
    assert command['argv'] == expected_args and command['cwd'] == str(ROOT / 'kernel/asterinas' / subdir)
    lock = (target / 'generated.Cargo.lock').read_bytes()
    assert lock == source_bytes('support/build/ktest/locks/' + crate + '.Cargo.lock')
    assert lock == (EVIDENCE / 'local-prepared-locks' / (crate + '.Cargo.lock')).read_bytes()
    assert sha(lock) == command['lock_sha256']
    lock_meta_bytes = (EVIDENCE / 'local-prepared-locks' / (crate + '.json')).read_bytes()
    assert lock_meta_bytes == source_bytes('support/build/ktest/locks/' + crate + '.json')
    lock_meta = json.loads(lock_meta_bytes)
    assert lock_meta['normalized_sha256'] == sha(lock) and lock_meta['external_drift'] == []
    assert lock_meta['metadata_exit'] == lock_meta['locked_metadata_exit'] == 0
    packages = tomllib.loads(lock.decode())['package']
    external_count = 0
    for package in packages:
        if package.get('source'):
            key = (package['name'], package['version'], package['source'])
            assert key in seed_external and package.get('checksum') == seed_external[key]
            external_count += 1
    lock_results.append({'crate': crate, 'generated_lock': file_record(target / 'generated.Cargo.lock'),
                         'prepared_lock_metadata': file_record(EVIDENCE / 'local-prepared-locks' / (crate + '.json')),
                         'package_count': len(packages), 'external_packages_matching_original_seed': external_count,
                         'generated_equals_fixed_git_and_prepared_bytes': True, 'external_drift': []})
    assert (target / 'osdk-exit-code.txt').read_bytes() == b'0\n'
    log = (target / 'osdk-test.log').read_text()
    assert 'Finished `release` profile [optimized]' in log
    assert not re.search(r'^error(?:\[|:)', log, re.M)
    qemu = json.loads((guest / 'qemu.json').read_bytes())
    assert qemu['crate'] == crate
    assert type(qemu['raw_exit_code']) is int and qemu['raw_exit_code'] == 33 and qemu['timed_out'] is False
    assert qemu['profile'] == {'arch': 'x86_64', 'machine': 'q35', 'accel': 'tcg', 'cpu': 'max',
                              'vcpus': 1, 'memory_mib': 512, 'network': False, 'data_disks': False}
    kernel_path = str(ROOT / 'kernel/asterinas/target/osdk' / crate / (crate + '-osdk-bin.elf'))
    expected_qemu = ['/usr/bin/qemu-system-x86_64', '-kernel', kernel_path,
                     '-append', 'loglevel=error earlycon console=ttyS0 --',
                     '-machine', 'q35', '-accel', 'tcg', '-cpu', 'max', '-bios', '/usr/share/seabios/bios-256k.bin',
                     '-m', '512M', '-smp', '1', '-nodefaults', '-no-user-config', '-no-reboot', '-nographic',
                     '-display', 'none', '-monitor', 'none', '-serial', 'chardev:serial', '-chardev',
                     'stdio,id=serial,signal=off,logfile=' + str(guest / 'serial.log'),
                     '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04']
    assert qemu['argv'] == expected_qemu and qemu['shell_command'] == shlex.join(expected_qemu)
    assert file_record(Path(qemu['argv'][0]))['sha256'] == qemu['qemu_sha256']
    bios = qemu['artifacts']['-bios']
    assert file_record(Path(bios['path']))['sha256'] == bios['sha256']
    assert Path(bios['path']).stat().st_size == bios['size']
    kernel = qemu['artifacts']['-kernel']
    saved = EVIDENCE / 'g1c-review/first-local-inputs-72c8dff3' / (crate + '-osdk-bin.elf')
    elf = saved.read_bytes()
    assert len(elf) == kernel['size'] and sha(elf) == kernel['sha256']
    assert elf[:6] == b'\x7fELF\x02\x01'
    elf_type, machine = struct.unpack_from('<HH', elf, 16)
    # Original OSDK's multiboot rewrite keeps ELF64 but marks EM_386 for
    # QEMU direct loading; see osdk/src/commands/build/bin.rs::make_elf_for_qemu.
    assert elf_type == 2 and machine == 3
    kernel_outputs.append({'crate': crate, **file_record(saved), 'matches_original_qemu_record': True,
                           'elf_type': elf_type, 'elf_machine': machine,
                           'elf_machine_scope': 'ELF64 marked EM_386 by the original OSDK multiboot loader rewrite',
                           'recorded_build_path': kernel['path']})
    raw = (guest / 'serial.log').read_bytes()
    assert sha(raw) == qemu['serial_sha256']
    serial = ANSI.sub('', raw.decode()).replace('\r', '')
    header = list(re.finditer(r'^running (\d+) tests in crate "([^"]+)"$', serial, re.M))
    assert len(header) == 1 and header[0][1] == str(expected_count) and header[0][2] == crate
    summary = list(re.finditer(r'^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) filtered out\.$', serial, re.M))
    assert len(summary) == 1 and summary[0].groups() == ('ok', str(expected_count), '0', '0')
    assert len(re.findall(r'^\[ktest runner\] running \d+ tests in \d+ crates$', serial, re.M)) == 1
    assert serial.count('[ktest runner] All crates tested.') == 1
    assert summary[0].end() < serial.index('[ktest runner] All crates tested.')
    fatal_markers = ['An uncaught panic occurred:', 'Uncaught panic:', 'unknown panic payload! (fatal panic handling error',
                     'Non-resettable panic!', 'The panic handler panicked', 'Panicked in `PanicGuard`, aborting the system']
    assert not any(marker in serial for marker in fatal_markers)
    # Device logs may start immediately after "..." without an intervening space.
    starts = list(re.finditer(r'^test ([A-Za-z_][A-Za-z0-9_:]*) \.\.\.', serial, re.M))
    names = [m[1] for m in starts]
    assert len(names) == len(set(names)) == expected_count
    assert all(name.startswith(crate.replace('-', '_') + '::') for name in names)
    cases = []
    skips = []
    for i, start in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else summary[0].start()
        body = serial[start.end():end].strip()
        assert body.endswith('ok') and not re.search(r'\bFAILED\b', body)
        reasons = re.findall(r'\[skipped: ([^\]]+)\]', body)
        assert len(reasons) <= 1
        case = {'name': start[1], 'reported_result': 'ok', 'soft_skip_reason': reasons[0] if reasons else None}
        cases.append(case)
        if reasons:
            skips.append({'name': start[1], 'reason': reasons[0]})
    expected_skips = {} if crate == 'aster-core' else {
        'ostd::arch::vm::vmx::test::multiple_vmx_guards_lifecycle': 'VMX unavailable',
        'ostd::arch::vm::vmx::vmcs::test::switch_and_reuse_vmcs': 'VMX unavailable',
        'ostd::vm::gpm_space::test::guest_mapping_lifecycle': 'VMX/EPT invalidation unavailable'}
    assert {x['name']: x['reason'] for x in skips} == expected_skips
    if crate == 'aster-core':
        assert set(expected_new_names) <= set(names)
    reported = json.loads((target / 'result.json').read_bytes())
    assert reported['passed'] is True and len(reported['guests']) == 1
    entry = reported['guests'][0]
    assert (entry['declared'], entry['passed'], entry['failed'], entry['filtered'], entry['observed_test_starts'], entry['soft_skipped']) == (expected_count, expected_count, 0, 0, expected_count, len(skips))
    case_results.append({'crate': crate, 'declared': expected_count, 'uniquely_enumerated': len(names),
                         'reported_passed': expected_count, 'failed': 0, 'filtered': 0,
                         'soft_skipped': len(skips), 'exercised_passed_lower_bound': expected_count - len(skips),
                         'raw_qemu_exit_code': qemu['raw_exit_code'], 'osdk_exit_code': 0,
                         'timed_out': False, 'qemu_duration_seconds': qemu['duration_seconds'],
                         'serial': file_record(guest / 'serial.log'), 'soft_skip_cases': skips,
                         'new_g1c_cases': [case for case in cases if case['name'] in expected_new_names],
                         'all_cases': cases})

expected_changed = {
    'kernel/asterinas/kernel/core/src/device/misc/hepta_control.rs',
    'kernel/asterinas/kernel/core/src/process/process/image.rs',
    'kernel/asterinas/kernel/core/src/process/test_util.rs',
    'tests/spec/test_a05_capspace_nonce.py'}
changed = set(git('diff', '--name-only', SOURCE, FORMAT_SOURCE).decode().splitlines())
assert changed == expected_changed
formatting_records = [{'before': git_record(name), 'after': git_record(name, FORMAT_SOURCE)} for name in sorted(changed)]
format_diff = git('diff', SOURCE, FORMAT_SOURCE)
source_continuity = []
for group in ('source_files', 'additional_reviewed_files', 'preserved_call_path_inputs'):
    for old in prior[group]:
        item = git_record(old['path'])
        assert all(item[key] == old[key] for key in ('bytes', 'sha256', 'git_blob'))
        source_continuity.append(item)

all_receipts = []
for path in sorted(RUN.rglob('*')):
    if path.is_file():
        all_receipts.append(file_record(path))
output = {
    'schema_version': 1, 'kind': 'independent_first_local_g1c_ktest_review',
    'reviewer': '/root/g1c_review', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
    'source_head': SOURCE, 'source_tree': TREE,
    'decision': 'Accept the first local fixed-toolchain full aster-core/OSTD execution at 72c8 within its recorded scope. No blocking source issue found in the four-file formatting delta. Final published source and original A06 qualification remain separate.',
    'blocking_findings': [],
    'phases': phase_records, 'attempt_receipt': file_record(attempt_path),
    'source_binding': {
        'environment_records_clean_head': True,
        'recorded_head_tree_exists_in_git': True,
        'build_input_digests_match_source_head': build_inputs,
        'upstream_build_inputs_independently_matched': 118,
        'checked_upstream_and_derived_files': pinned_names,
        'previously_reviewed_source_files_match_recorded_head': source_continuity,
        'limitation': 'The original runner source-inputs.json checks 118 upstream build/manifests inputs; it is not a complete product source byte/mode snapshot. The runner records clean Git HEAD and selected build input hashes, with the earlier independent selected-source review. No complete before/after all-product snapshot is claimed for this first local run.',
    },
    'environment': environment, 'commands': commands, 'tool_identity_checks': tool_records,
    'lock_identity_checks': lock_results, 'kernel_output_identity_checks': kernel_outputs,
    'qemu_elf_loader_source': git_record('kernel/asterinas/osdk/src/commands/build/bin.rs'),
    'independently_enumerated_results': case_results,
    'new_g1c_test_count': 18,
    'formatting_review': {
        'local_source_head': FORMAT_SOURCE, 'source_tree': FORMAT_TREE, 'parent': SOURCE,
        'diff_bytes': len(format_diff), 'diff_sha256': sha(format_diff),
        'files': formatting_records,
        'assessment': [
            'hepta_control.rs only reorders and nests the same crate imports; exported names and call sites are unchanged.',
            'image.rs only changes layout, adds a block around the identical closure return expression, and removes optional trailing punctuation introduced by the former multiline layout. The same checked_add, orderings, phase assignments and test assertions remain.',
            'test_util.rs only expands the same if-expression over multiple lines.',
            'The host source assertion permits whitespace between self and .epoch; it still requires self.epoch.checked_add(1) in commit_exec, with no runtime or kernel-test change.',
        ],
        'execution_qualification': 'No final-source execution qualification inferred from this first-head run.'
    },
    'retained_receipt_files': all_receipts,
    'activities': {'product_source_writes': 0, 'new_kernel_builds': 0, 'new_test_runs': 0,
                   'toolchain_installs': 0, 'remote_reads': 0, 'remote_writes': 0,
                   'existing_elf_outputs_copied_after_hash_match': 2,
                   'read_only_version_queries': ['rustc -Vv', 'cargo -Vv']},
    'not_qualified_here': ['Final published G1-c head', 'Original remote A06 run', 'Seven production negative controls',
                           'Ordinary product boot and QueryAbi guest', 'Linux/CPU combined workload acceptance',
                           'Static immutable image authentication', 'Native grants or HOS2 resource effects', 'SMP/device/mobile qualification'],
}
OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({**file_record(OUT), 'core_passed': 238, 'ostd_reported_passed': 221,
                  'ostd_soft_skips': 3, 'new_g1c_names_passed': 18, 'blocking_findings': 0}))
