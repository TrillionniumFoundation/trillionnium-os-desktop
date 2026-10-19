#!/usr/bin/env python3
"""Review final-head local ktest serials separately from the first-head run."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shlex
import struct
import subprocess

WORK = Path('/workspace/scratch/499c7902de8e')
ROOT = WORK / 'r12-g1c'
EVIDENCE = WORK / 'r12-evidence'
RUN = EVIDENCE / 'local-final-ktest'
OUT = EVIDENCE / 'g1c-review/final-local-ktest-10420401-review.json'
SOURCE = '104204016dcdea57ab73c091b1edd13008ae9a19'
TREE = '179b076747d19c3e07ee19a665e3968c33c598ce'
PARENT = '72c8dff3f0145a7e16b7095d48a3e7faaf192685'
FORMAT_SOURCE = 'ba0d049a3640ccff4734aa37d8e24eb7b3f61dcf'
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args])


def file_record(path):
    data = path.read_bytes()
    try:
        name = str(path.relative_to(EVIDENCE))
    except ValueError:
        name = str(path)
    return {'path': name, 'bytes': len(data), 'sha256': sha(data)}


def git_record(name):
    data = git('show', SOURCE + ':' + name)
    mode, kind, oid = git('ls-tree', SOURCE, '--', name).decode().split('\t', 1)[0].split()
    assert kind == 'blob'
    assert hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest() == oid
    return {'path': name, 'mode': mode, 'git_blob': oid, 'bytes': len(data), 'sha256': sha(data)}


assert git('rev-parse', SOURCE + '^{tree}').decode().strip() == TREE
assert git('rev-parse', SOURCE + '^').decode().strip() == PARENT
assert git('rev-parse', FORMAT_SOURCE + '^{tree}').decode().strip() == TREE
prior_path = EVIDENCE / 'g1c-review/first-local-ktest-72c8dff3-review.json'
prior_data = prior_path.read_bytes()
assert sha(prior_data) == 'c042bed154d560a41a33a7aebaf0cd4d6d23d0c860a2baed57ce693345f4f69a'
prior = json.loads(prior_data)
attempt_path = EVIDENCE / 'local-host/final-full-ktest-attempt.json'
attempt = json.loads(attempt_path.read_bytes())
assert attempt['source_head'] == SOURCE and attempt['source_tree'] == TREE
assert type(attempt['exit_code']) is int and attempt['exit_code'] == 0
assert attempt['command'] == ['python3', '-I', 'support/build/ktest/run.py', '--skip-osdk-install', '--output', str(RUN)]
assert file_record(EVIDENCE / 'local-host/final-full-ktest.log')['sha256'] == attempt['log_sha256']
environment = json.loads((RUN / 'environment.json').read_bytes())
assert environment['git_head'] == SOURCE and environment['git_status'] == ''
assert environment['test_name'] is None and environment['osdk_install_skipped'] is True
for key in ('toolchain', 'rustc', 'cargo', 'cargo_build_jobs', 'build_inputs_sha256', 'osdk_sha256', 'vdso_sha256'):
    assert environment[key] == prior['environment'][key], key
build_inputs = []
for name, expected_sha in environment['build_inputs_sha256'].items():
    record = git_record(name)
    assert record['sha256'] == expected_sha
    build_inputs.append(record)
source_report = (RUN / 'source-inputs.json').read_bytes()
assert source_report == (EVIDENCE / 'local-full-ktest/source-inputs.json').read_bytes()
for old in prior['source_binding']['checked_upstream_and_derived_files']:
    assert git_record(old['path']) == old

format_files = prior['formatting_review']['files']
changed = sorted(git('diff', '--name-only', PARENT, SOURCE).decode().splitlines())
assert changed == sorted(item['after']['path'] for item in format_files)
for item in format_files:
    assert git_record(item['after']['path']) == item['after']
changed_map = {item['after']['path']: item['after'] for item in format_files}
reviewed_source = []
for old in prior['source_binding']['previously_reviewed_source_files_match_recorded_head']:
    current = git_record(old['path'])
    assert current == changed_map.get(old['path'], old)
    reviewed_source.append(current)

tool_inputs = []
for old in prior['tool_identity_checks']:
    actual = file_record(Path(old['path']))
    assert actual['bytes'] == old['bytes'] and actual['sha256'] == old['sha256']
    tool_inputs.append({**actual, 'matches_first_source_built_tool_identity': True})
commands = json.loads((RUN / 'commands.json').read_bytes())
assert commands == prior['commands'][1:]
assert len(commands) == 2
first_cases = {entry['crate']: entry for entry in prior['independently_enumerated_results']}
first_outputs = {entry['crate']: entry for entry in prior['kernel_output_identity_checks']}
case_results = []
outputs = []
lock_results = []
qemu_inputs = []
for index, (crate, count) in enumerate([('ostd', 221), ('aster-core', 238)]):
    target = RUN / crate
    guest = target / 'guests/guest-001'
    assert sorted(path.name for path in (target / 'guests').iterdir()) == ['guest-001']
    actual_lock = (target / 'generated.Cargo.lock').read_bytes()
    assert actual_lock == (EVIDENCE / 'local-full-ktest' / crate / 'generated.Cargo.lock').read_bytes()
    assert actual_lock == git('show', SOURCE + ':support/build/ktest/locks/' + crate + '.Cargo.lock')
    assert sha(actual_lock) == commands[index]['lock_sha256']
    lock_results.append({'crate': crate, **file_record(target / 'generated.Cargo.lock'),
                         'matches_final_git_and_first_generated_lock': True})
    assert (target / 'osdk-exit-code.txt').read_bytes() == b'0\n'
    build_log = (target / 'osdk-test.log').read_text()
    assert 'Finished `release` profile [optimized]' in build_log
    assert not re.search(r'^error(?:\[|:)', build_log, re.M)
    qemu = json.loads((guest / 'qemu.json').read_bytes())
    first_qemu = json.loads((EVIDENCE / 'local-full-ktest' / crate / 'guests/guest-001/qemu.json').read_bytes())
    assert qemu['crate'] == crate and qemu['profile'] == first_qemu['profile']
    assert type(qemu['raw_exit_code']) is int and qemu['raw_exit_code'] == 33
    assert qemu['timed_out'] is False
    expected_argv = [arg.replace('/local-full-ktest/', '/local-final-ktest/') for arg in first_qemu['argv']]
    assert qemu['argv'] == expected_argv and qemu['shell_command'] == shlex.join(expected_argv)
    assert qemu['requested_osdk_args'] == first_qemu['requested_osdk_args']
    assert qemu['qemu_sha256'] == first_qemu['qemu_sha256']
    assert qemu['qemu_version'] == first_qemu['qemu_version']
    qemu_executable = file_record(Path(qemu['argv'][0]))
    assert qemu_executable['sha256'] == qemu['qemu_sha256']
    bios = qemu['artifacts']['-bios']
    assert bios == first_qemu['artifacts']['-bios']
    bios_input = file_record(Path(bios['path']))
    assert bios_input['sha256'] == bios['sha256'] and bios_input['bytes'] == bios['size']
    qemu_inputs.append({'crate': crate, 'profile': qemu['profile'], 'argv': qemu['argv'],
                        'qemu': qemu_executable, 'bios': bios_input})
    saved = EVIDENCE / 'g1c-review/final-local-inputs-10420401' / (crate + '-osdk-bin.elf')
    output = file_record(saved)
    recorded_output = qemu['artifacts']['-kernel']
    assert output['sha256'] == recorded_output['sha256'] and output['bytes'] == recorded_output['size']
    elf = saved.read_bytes()
    assert elf[:6] == b'\x7fELF\x02\x01' and struct.unpack_from('<HH', elf, 16) == (2, 3)
    outputs.append({'crate': crate, **output, 'matches_original_qemu_record': True,
                    'same_bytes_as_first_head_output': output['sha256'] == first_outputs[crate]['sha256'],
                    'elf_scope': 'ELF64 executable with original OSDK EM_386 multiboot rewrite'})
    raw_serial = (guest / 'serial.log').read_bytes()
    assert sha(raw_serial) == qemu['serial_sha256']
    serial = ANSI.sub('', raw_serial.decode()).replace('\r', '')
    headers = list(re.finditer(r'^running (\d+) tests in crate "([^"]+)"$', serial, re.M))
    assert len(headers) == 1 and headers[0].groups() == (str(count), crate)
    summaries = list(re.finditer(r'^test result: (ok|FAILED)\. (\d+) passed; (\d+) failed; (\d+) filtered out\.$', serial, re.M))
    assert len(summaries) == 1 and summaries[0].groups() == ('ok', str(count), '0', '0')
    assert len(re.findall(r'^\[ktest runner\] running \d+ tests in \d+ crates$', serial, re.M)) == 1
    assert serial.count('[ktest runner] All crates tested.') == 1
    assert summaries[0].end() < serial.index('[ktest runner] All crates tested.')
    fatal_markers = ['An uncaught panic occurred:', 'Uncaught panic:', 'unknown panic payload! (fatal panic handling error',
                     'Non-resettable panic!', 'The panic handler panicked', 'Panicked in `PanicGuard`, aborting the system']
    assert not any(marker in serial for marker in fatal_markers)
    starts = list(re.finditer(r'^test ([A-Za-z_][A-Za-z0-9_:]*) \.\.\.', serial, re.M))
    names = [start[1] for start in starts]
    assert len(names) == len(set(names)) == count
    assert all(name.startswith(crate.replace('-', '_') + '::') for name in names)
    assert set(names) == {entry['name'] for entry in first_cases[crate]['all_cases']}
    cases = []
    skips = []
    for i, start in enumerate(starts):
        end = starts[i + 1].start() if i + 1 < len(starts) else summaries[0].start()
        body = serial[start.end():end].strip()
        assert body.endswith('ok') and not re.search(r'\bFAILED\b', body)
        reasons = re.findall(r'\[skipped: ([^\]]+)\]', body)
        assert len(reasons) <= 1
        case = {'name': start[1], 'reported_result': 'ok', 'soft_skip_reason': reasons[0] if reasons else None}
        cases.append(case)
        if reasons:
            skips.append({'name': start[1], 'reason': reasons[0]})
    assert skips == first_cases[crate]['soft_skip_cases']
    new_names = {case['name'] for case in first_cases[crate]['new_g1c_cases']}
    new_cases = [case for case in cases if case['name'] in new_names]
    assert len(new_cases) == (18 if crate == 'aster-core' else 0)
    report = json.loads((target / 'result.json').read_bytes())
    assert report['passed'] is True and len(report['guests']) == 1
    entry = report['guests'][0]
    assert (entry['declared'], entry['passed'], entry['failed'], entry['filtered'], entry['observed_test_starts'], entry['soft_skipped']) == (count, count, 0, 0, count, len(skips))
    case_results.append({'crate': crate, 'declared': count, 'uniquely_enumerated': len(names),
                         'reported_passed': count, 'failed': 0, 'filtered': 0, 'soft_skipped': len(skips),
                         'exercised_passed_lower_bound': count - len(skips),
                         'raw_qemu_exit_code': qemu['raw_exit_code'], 'osdk_exit_code': 0, 'timed_out': False,
                         'qemu_duration_seconds': qemu['duration_seconds'],
                         'serial': file_record(guest / 'serial.log'),
                         'same_complete_test_name_set_as_first_head': True,
                         'soft_skip_cases': skips, 'new_g1c_cases': new_cases, 'all_cases': cases})
overall = json.loads((RUN / 'result.json').read_bytes())
assert overall['passed'] is True
assert overall['crates'] == [json.loads((RUN / name / 'result.json').read_bytes()) for name in ['ostd', 'aster-core']]
output = {
    'schema_version': 1, 'kind': 'independent_final_local_g1c_ktest_review',
    'reviewer': '/root/g1c_review', 'created_at_utc': datetime.now(timezone.utc).isoformat(),
    'source_head': SOURCE, 'source_tree': TREE, 'parent_head': PARENT,
    'decision': 'Accept the actual local full unfiltered aster-core/OSTD run at final published source 10420401 in the recorded single-vCPU TCG profile. All 18 G1-c cases passed at this source. Original remote A06, ordinary-product and negative-control qualification are not inferred here.',
    'blocking_findings': [],
    'first_run_independent_review': file_record(prior_path),
    'final_attempt': attempt, 'attempt_identity': file_record(attempt_path),
    'final_runner_log': file_record(EVIDENCE / 'local-host/final-full-ktest.log'),
    'formatting_source_binding': {'reviewed_local_head': FORMAT_SOURCE, 'same_tree_as_published_head': True,
                                 'changed_files': changed, 'reviewed_before_after': format_files},
    'source_binding': {'recorded_clean_head': True,
                       'selected_reviewed_source_files_at_final_head': reviewed_source,
                       'build_input_digests_verified_against_final_git': build_inputs,
                       'same_118_checked_upstream_and_derived_files': True,
                       'source_report': file_record(RUN / 'source-inputs.json'),
                       'scope_limit': 'The unchanged original runner reports the clean Git head and checks selected build pins; source-inputs.json is 118 upstream build/manifests inputs, not a complete before/after product source snapshot.'},
    'environment': environment, 'commands': commands,
    'source_built_osdk_reuse': {'install_skipped': True, 'identical_binary_hash': environment['osdk_sha256'],
                               'original_source_install_log': file_record(EVIDENCE / 'local-full-ktest/osdk-install.log')},
    'tool_identity_checks': tool_inputs, 'qemu_input_checks': qemu_inputs,
    'generated_lock_checks': lock_results, 'kernel_output_identity_checks': outputs,
    'qemu_elf_loader_source': git_record('kernel/asterinas/osdk/src/commands/build/bin.rs'),
    'independently_enumerated_results': case_results,
    'retained_run_files': [file_record(path) for path in sorted(RUN.rglob('*')) if path.is_file()],
    'activities': {'product_source_writes': 0, 'new_kernel_builds': 0, 'new_test_runs': 0,
                   'toolchain_installs': 0, 'remote_reads': 0, 'remote_writes': 0,
                   'existing_final_elf_outputs_copied_after_hash_match': 2},
    'scope_limits': ['Original remote A06 not checked here', 'Seven production negative controls not checked here',
                     'Ordinary product boot/QueryAbi and Linux/CPU workload run not checked here',
                     'Object cases are not post-boundary fatal exec injection or full final-exit syscall fixtures',
                     'No static immutable image authentication, native grant or four resource operations enabled',
                     'No expanded SMP, physical-device or mobile qualification'],
}
OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({**file_record(OUT), 'core_passed': 238, 'ostd_reported_passed': 221,
                  'ostd_soft_skips': 3, 'new_g1c_names_passed': 18, 'blocking_findings': 0}))
