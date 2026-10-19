#!/usr/bin/python3.12
"""Independently read local and official negative evidence; never run producers."""
from pathlib import Path, PurePosixPath
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import tempfile
import zipfile

BASE = Path('/workspace/scratch/499c7902de8e/r12-evidence')
REPO = Path('/workspace/scratch/499c7902de8e/r12-g1c')
OUT = BASE / 'g1c-lifecycle'
HEAD = '104204016dcdea57ab73c091b1edd13008ae9a19'
TREE = '179b076747d19c3e07ee19a665e3968c33c598ce'
ZIP_SHA = '984adcb6fd87dbef0c4b68223e8bde1811a5e00a31a447c597e20810b073067d'
OLD = Path('/workspace/scratch/499c7902de8e/r11-evidence/pr205-runtime-review')
ENV = dict(os.environ, GIT_NO_LAZY_FETCH='1', GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL='/dev/null')


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


helper = module('r12_independent_serial_parser', OLD / 'review-green-archive.py')
negative_helper = module('r12_independent_tree_and_constants', OLD / 'review-negative-archive.py')
sha = helper.sha
tree_hash = negative_helper.tree_hash
blob = negative_helper.blob


def git(*args):
    return subprocess.check_output(['git', *args], cwd=REPO, env=ENV)


def save(name, report):
    data = (json.dumps(report, ensure_ascii=False, indent=2) + '\n').encode()
    (OUT / name).write_bytes(data)
    print(json.dumps({'report': name, 'bytes': len(data), 'sha256': sha(data),
                      'passed': report.get('passed')}), flush=True)


class Reader:
    def __init__(self, archive=None):
        self.archive = archive
        self.records = {}

    def read(self, name):
        if self.archive:
            info = self.archive.getinfo(name)
            assert info.file_size <= 16 * 1024 * 1024
            data = self.archive.read(name)
            assert len(data) == info.file_size
        else:
            path = BASE / name
            assert path.stat().st_size <= 16 * 1024 * 1024
            data = path.read_bytes()
        self.records[name] = {'path_or_member': name, 'bytes': len(data), 'sha256': sha(data)}
        return data

    def obj(self, name):
        return json.loads(self.read(name))

    def elf(self, name, expected):
        if self.archive:
            assert self.archive.getinfo(name).file_size == expected['size']
            with self.archive.open(name) as stream:
                header = stream.read(64)
            result = {'recorded_sha256': expected['sha256'], 'bytes': expected['size'],
                      'content_hash_independently_verified': False,
                      'method': 'ZIP member length and 64-byte ELF header only; large ELF not extracted or read in full.'}
        else:
            with (BASE / name).open('rb') as stream:
                digest, size, header = helper.stream_sha(stream)
            assert (digest, size) == (expected['sha256'], expected['size'])
            result = {'sha256': digest, 'bytes': size,
                      'content_hash_independently_verified': True}
        assert header[:6] == b'\x7fELF\x02\x01' and header[18:20] == b'\x03\x00'
        return dict(result, path_or_member=name, elf_class=64, e_machine=3)


def patch_copy_check(diff, changed_path, original, expected_row):
    assert re.findall(r'^diff --git a/(\S+) b/(\S+)$', diff.decode(), re.M) == [(changed_path, changed_path)]
    with tempfile.TemporaryDirectory(prefix='r12-negative-text-review-', dir='/tmp') as temp:
        root = Path(temp)
        copied = root / changed_path
        copied.parent.mkdir(parents=True)
        copied.write_bytes(original)
        copied.chmod(int(expected_row['mode'], 8) & 0o777)
        for args in (['git', 'apply', '--check', '-'], ['git', 'apply', '-']):
            call = subprocess.run(args, cwd=root, env=ENV, input=diff,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            assert call.returncode == 0, call.stderr.decode()
        data = copied.read_bytes()
        assert {'mode': expected_row['mode'], 'git_blob': blob(data),
                'sha256': sha(data), 'size': len(data)} == expected_row
        assert [str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()] == [changed_path]


def review_set(reader, green_prefix, prefixes, constants, source, new_names, expected_negative=None):
    green_env = reader.obj(green_prefix + '/environment.json')
    assert green_env['git_head'] == HEAD and green_env['git_status'] == ''
    assert green_env['test_name'] is None and green_env['toolchain'] == 'nightly-2026-07-21'
    assert reader.obj(green_prefix + '/result.json')['passed'] is True
    assert all(source[p]['sha256'] == v for p, v in green_env['build_inputs_sha256'].items())
    green_inputs = reader.obj(green_prefix + '/source-inputs.json')
    assert green_inputs['passed'] and not green_inputs['errors']
    assert all(source['kernel/asterinas/' + p]['sha256'] == v for p, v in green_inputs['input_sha256'].items())
    green_qemu = reader.obj(green_prefix + '/aster-core/guests/guest-001/qemu.json')
    green_raw = reader.read(green_prefix + '/aster-core/guests/guest-001/serial.log')
    green = helper.parse_tests(green_raw, 'aster-core')
    assert green['declared'] == green['passed'] == 238
    assert green['failed'] == green['filtered'] == green['soft_skipped'] == 0
    assert green_qemu['raw_exit_code'] == 33 and green_qemu['timed_out'] is False
    assert green_qemu['serial_sha256'] == sha(green_raw)
    green_names = {t['name'] for t in green['tests']}
    assert len(green_names) == 238 and set(new_names) <= green_names
    source_root = green_qemu['cwd'].removesuffix('/kernel/asterinas')
    green_commands = reader.obj(green_prefix + '/commands.json')
    core_commands = [row for row in green_commands if row.get('cwd', '').endswith('/kernel/asterinas/kernel/core')]
    assert len(core_commands) == 1
    rows, negative_maps = [], {}
    for control, spec in constants['CONTROLS'].items():
        patch_name, patch_sha, changed_path, expected_failed, minimum = spec
        prefix = prefixes[control]
        result = reader.obj(prefix + '/result.json')
        assert result['passed'] is True and result['negative_control_detected'] is True
        assert result['control'] == control and result['product_qualification'] is False
        assert (result['candidate_head'], result['candidate_tree']) == (HEAD, TREE)
        assert result['declared_changed_path'] == changed_path and result['patch_sha256'] == patch_sha
        assert result['raw_qemu_exit'] == 65 and result['original_gate_exit'] == 1 and result['timed_out'] is False
        assert all(result[k] is True for k in ('source_snapshots_unchanged', 'all_other_source_files_unchanged', 'same_osdk_binary_and_source_path'))
        before = reader.obj(prefix + '/candidate-source-before.json')
        after = reader.obj(prefix + '/candidate-source-after.json')
        negative = reader.obj(prefix + '/negative-source-before.json')
        assert before == after and before['files'] == source and (before['head'], before['tree']) == (HEAD, TREE)
        assert negative == reader.obj(prefix + '/negative-source-after.json')
        archived = reader.obj(prefix + '/negative-archive-source.json')
        assert all(archived[k] == negative[k] for k in ('schema', 'head', 'tree', 'files'))
        assert before['root'] == negative['root'] == source_root
        assert set(negative['files']) == set(source)
        assert [p for p in source if source[p] != negative['files'][p]] == [changed_path]
        assert (negative['head'], negative['tree']) == (result['negative_head'], result['negative_tree'])
        assert tree_hash(negative['files']) == result['negative_tree']
        if expected_negative is not None:
            assert negative['files'] == expected_negative[control]
        negative_maps[control] = negative['files']
        declared = reader.read(prefix + '/declared-negative-control.patch')
        applied = reader.read(prefix + '/applied-negative-control.patch')
        assert declared == git('cat-file', 'blob', HEAD + ':tests/organ_backend/' + patch_name)
        assert sha(declared) == patch_sha == source['tests/organ_backend/' + patch_name]['sha256']
        original = git('cat-file', 'blob', HEAD + ':' + changed_path)
        assert (blob(original), sha(original), len(original)) == (source[changed_path]['git_blob'], source[changed_path]['sha256'], source[changed_path]['size'])
        for diff in (declared, applied):
            patch_copy_check(diff, changed_path, original, negative['files'][changed_path])
        env = reader.obj(prefix + '/gate/environment.json')
        assert env['git_head'] == negative['head'] and env['git_status'] == '' and env['test_name'] is None
        assert env['osdk_install_skipped'] is True
        for key in ('toolchain', 'rustc', 'cargo', 'build_inputs_sha256', 'osdk_sha256', 'vdso_sha256', 'cargo_build_jobs'):
            assert env[key] == green_env[key], key
        assert reader.obj(prefix + '/gate/source-inputs.json') == green_inputs
        assert reader.obj(prefix + '/gate/commands.json') == core_commands
        command = reader.obj(prefix + '/command.json')
        assert command['cwd'] == source_root and command['execution_head'] == negative['head']
        assert command['argv'][1:8] == ['-I', '-B', source_root + '/support/build/ktest/run.py', '--crate', 'aster-core', '--skip-osdk-install', '--output']
        assert len(command['argv']) == 9
        qemu = reader.obj(prefix + '/gate/aster-core/guests/guest-001/qemu.json')
        raw = reader.read(prefix + '/gate/aster-core/guests/guest-001/serial.log')
        parsed = helper.parse_tests(raw, 'aster-core')
        names = {t['name'] for t in parsed['tests']}
        failed = sorted(t['name'] for t in parsed['tests'] if t['outcome'] == 'FAILED')
        assert names == green_names and parsed['declared'] == result['total_core_tests'] == 238
        assert parsed['soft_skipped'] == parsed['filtered'] == 0
        assert set(failed) == expected_failed and failed == result['negative_failed']
        assert parsed['passed'] == result['negative_passed'] == 238 - len(expected_failed)
        assert all(t['outcome'] == 'ok' and not t['soft_skip_reasons'] for t in parsed['tests'] if t['name'] in new_names)
        assert result['green_serial_sha256'] == sha(green_raw)
        assert sha(raw) == qemu['serial_sha256'] == result['negative_serial_sha256']
        assert qemu['raw_exit_code'] == 65 and qemu['timed_out'] is False and qemu['crate'] == 'aster-core'
        for key in ('cwd', 'profile', 'requested_osdk_args', 'qemu_sha256', 'qemu_version'):
            assert qemu[key] == green_qemu[key]
        normalize = lambda argv: [re.sub(r'(?<=logfile=)[^,]+', '<serial-path>', arg) for arg in argv]
        assert normalize(qemu['argv']) == normalize(green_qemu['argv'])
        assert qemu['artifacts']['-bios'] == green_qemu['artifacts']['-bios']
        assert reader.obj(prefix + '/original-gate-exit.json') == {'exit_code': 1}
        assert int(reader.read(prefix + '/gate/aster-core/osdk-exit-code.txt')) != 0
        assert reader.read(prefix + '/gate/aster-core/generated.Cargo.lock') == git('cat-file', 'blob', HEAD + ':support/build/ktest/locks/aster-core.Cargo.lock')
        validation = reader.obj(prefix + '/green-core-validation.json')
        assert validation['passed'] == validation['declared'] == validation['observed_test_starts'] == 238
        assert validation['failed'] == validation['filtered'] == validation['soft_skipped'] == 0
        green_art, negative_art = green_qemu['artifacts']['-kernel'], qemu['artifacts']['-kernel']
        assert green_art['path'] == negative_art['path']
        assert result['green_kernel_sha256'] == green_art['sha256']
        assert result['negative_kernel_sha256'] == negative_art['sha256'] != green_art['sha256']
        elfs = [reader.elf(prefix + '/green-core-kernel.elf', green_art),
                reader.elf(prefix + '/negative-control-kernel.elf', negative_art)]
        rows.append({'control': control, 'review_passed': True, 'complete_tests': 238,
                     'passed': parsed['passed'], 'failed': parsed['failed'], 'expected_exact_failed_names': failed,
                     'new_lifecycle_18_all_passed': True, 'filtered': 0, 'soft_skipped': 0,
                     'original_runner_minimum_unchanged': minimum, 'raw_qemu_exit': 65, 'original_gate_exit': 1,
                     'same_toolchain_osdk_source_path_qemu_profile_and_lock_as_green': True,
                     'candidate_restored_exactly': True, 'source_files': len(source),
                     'negative_recorded_head': negative['head'], 'negative_tree_recomputed': negative['tree'],
                     'only_changed_path': changed_path, 'declared_patch_sha256': sha(declared),
                     'applied_patch_sha256': sha(applied), 'both_patches_verified_on_disposable_text_copy': True,
                     'negative_file_map_matches_independent_local_commit': True if expected_negative is not None else None,
                     'local_commit_comparison_method': ('Complete file map equals independently Git-verified local mutation'
                                                        if expected_negative is not None else 'Pending local commit tree verification'),
                     'retained_elf_records': elfs})
        print(json.dumps({'review': 'official' if reader.archive else 'local', 'control': control,
                          'passed': parsed['passed'], 'failed': parsed['failed'], 'new18': True}), flush=True)
    return rows, negative_maps, green_names


def main():
    assert __debug__
    started = datetime.now(timezone.utc).isoformat()
    runner_path = 'tests/organ_backend/run_cpu_owner_negative.py'
    runner = git('cat-file', 'blob', HEAD + ':' + runner_path)
    constants = negative_helper.read_control_constants(runner.decode())
    local = Reader()
    source = local.obj('local-negative/owner-current-slot/candidate-source-before.json')['files']
    assert len(source) == 7346 and tree_hash(source) == TREE
    git_files = {}
    for entry in git('ls-tree', '-r', '-z', HEAD).split(b'\0'):
        if entry:
            metadata, path = entry.split(b'\t', 1)
            mode, kind, object_id = metadata.decode().split()
            assert kind == 'blob'
            git_files[path.decode()] = {'mode': mode, 'git_blob': object_id}
    assert set(git_files) == set(source)
    assert all({k: row[k] for k in ('mode', 'git_blob')} == git_files[p] for p, row in source.items())
    assert sha(runner) == source[runner_path]['sha256']
    old_raw = (OLD / 'green-independent-review/review.json').read_bytes()
    old = json.loads(old_raw)
    assert old['head'] == '4d3011cf9f92e25fc1b0d7371e9cdbbd5a8b7930'
    old_names = {t['name'] for c in old['crates'] if c['crate'] == 'aster-core' for t in c['tests']}
    assert len(old_names) == 220
    baseline = helper.parse_tests(local.read('local-final-ktest/aster-core/guests/guest-001/serial.log'), 'aster-core')
    baseline_names = {t['name'] for t in baseline['tests']}
    new_names = sorted(baseline_names - old_names)
    assert old_names <= baseline_names and len(new_names) == 18
    changed_rust = git('diff', '--name-only', old['head'], HEAD, '--', '*.rs').decode().splitlines()
    declared = {name for path in changed_rust for name in re.findall(r'#\[ktest\]\s*fn\s+(\w+)\s*\(', git('cat-file', 'blob', HEAD + ':' + path).decode())}
    assert all(name.rsplit('::', 1)[1] in declared for name in new_names)
    shared = {'schema': 'a06.independent.seven-negative-review.v1', 'started_at': started,
              'head': HEAD, 'tree': TREE, 'fixed_original_runner_sha256': sha(runner),
              'source_files': len(source), 'source_paths_modes_and_blobs_match_exact_git_tree': True,
              'candidate_tree_independently_recomputed': TREE, 'new_lifecycle_tests': new_names,
              'old_220_reference_sha256': sha(old_raw),
              'independent_parser_sha256': sha((OLD / 'review-green-archive.py').read_bytes()),
              'independent_constant_and_tree_helper_sha256': sha((OLD / 'review-negative-archive.py').read_bytes()),
              'method': 'Independent serial parser plus restricted AST constants; original runner not imported or executed. Only fixed diffs applied to disposable non-repository text copies.'}
    local_prefixes = {c: 'local-negative/' + c for c in constants['CONTROLS']}
    local_rows, local_maps, green_names = review_set(local, 'local-final-ktest', local_prefixes, constants, source, new_names)
    sequence = local.obj('local-negative/sequence.json')
    assert sequence['passed'] is True and (sequence['source_head_after'], sequence['source_tree_after'], sequence['source_status_after']) == (HEAD, TREE, '')
    phases = {p['name']: p for p in sequence['phases']}
    assert phases['original-runner-tests']['exit_code'] == 0
    cleanup = []
    for index, row in enumerate(local_rows):
        control = row['control']; phase = phases[control]
        assert phase['exit_code'] == 0 and phase['candidate_restored'] is True
        assert phase['clean_disposable_worktree_removed'] is True
        command = phase['command']; has_saved = '--green-kernel' in command
        assert has_saved == bool(index)
        if index:
            assert command[command.index('--green-kernel') + 1] == str(BASE / 'local-negative/owner-current-slot/green-core-kernel.elf')
        assert sha(local.read('local-negative/' + control + '.log')) == phase['log_sha256']
        assert sha(local.read('local-negative/' + control + '/result.json')) == phase['result_sha256']
        assert git('rev-parse', row['negative_recorded_head'] + '^{tree}').decode().strip() == row['negative_tree_recomputed']
        assert git('rev-parse', row['negative_recorded_head'] + '^').decode().strip() == HEAD
        row['negative_file_map_matches_independent_local_commit'] = True
        row['local_commit_comparison_method'] = 'Complete snapshot tree independently reconstructed from every path/mode/blob equals the retained local commit tree; its sole parent is the fixed candidate HEAD'
        cleanup.append({'control': control, 'clean_removal_recorded_after_original_runner_restored_candidate': True,
                        'archive_directory_currently_exists': Path(command[command.index('--worktree') + 1]).exists()})
    retention = local.obj('local-negative/commit-retention.json')
    bundle = BASE / 'local-negative' / retention['bundle']
    assert bundle.stat().st_size == retention['bytes'] == 5768
    assert sha(bundle.read_bytes()) == retention['sha256'] == '80a990c09b70fceb0fb1f24054d3b25a9cc2086f5d62c7b64f4330b57e694620'
    for item in retention['refs']:
        expected = next(r for r in local_rows if r['control'] == item['control'])
        assert git('rev-parse', item['ref']).decode().strip() == item['head'] == expected['negative_recorded_head']
    assert len(retention['refs']) == 7
    listed = git('bundle', 'list-heads', str(bundle)).decode().splitlines()
    assert set(listed) == {item['head'] + ' ' + item['ref'] for item in retention['refs']}
    verify = subprocess.run(['git', 'bundle', 'verify', str(bundle)], cwd=REPO, env=ENV,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert verify.returncode == 0
    wrapper = (BASE / 'run-original-negative-sequence.py').read_bytes()
    local_report = dict(shared, kind='independent local original seven controls',
                        controls=local_rows, negative_failed_counts=[r['failed'] for r in local_rows],
                        wrapper_sha256=sha(wrapper),
                        wrapper_review={'original_controls_order_and_acceptance_preserved': True,
                                        'first_live_green_then_six_saved_green': True,
                                        'original_runner_waited_before_restore_checks_and_cleanup': True,
                                        'no_force_worktree_removal': True,
                                        'observed_running_argv': ['python3', '-I', '-B', str(BASE / 'run-original-negative-sequence.py')],
                                        'wrapper_asserts_enabled_in_observed_invocation': True},
                        cleanup_records=cleanup, commit_refs_and_bundle_verified=True,
                        bundle_sha256=retention['sha256'], bundle_bytes=5768,
                        bundle_prerequisite=HEAD, raw_evidence_records=list(local.records.values()),
                        finished_at=datetime.now(timezone.utc).isoformat(), passed=True)
    save('negative-sequence-review.json', local_report)
    api_path = BASE / 'pr207-runtime-review/api-records.json'
    api = json.loads(api_path.read_text())
    assert api['run']['id'] == 39256580996 and api['run']['head_sha'] == HEAD and api['run']['conclusion'] == 'success'
    job = next(j for j in api['jobs']['jobs'] if j['id'] == 118073271911)
    assert job['conclusion'] == 'success' and job['head_sha'] == HEAD
    artifact = next(a for a in api['artifacts']['artifacts'] if a['id'] == 12190114844)
    assert artifact['digest'] == 'sha256:' + ZIP_SHA and artifact['workflow_run']['head_sha'] == HEAD
    archive_path = BASE / 'pr207-runtime-review/original.zip'
    with archive_path.open('rb') as stream:
        archive_hash, archive_size, _ = helper.stream_sha(stream)
    assert archive_hash == ZIP_SHA and archive_size == artifact['size_in_bytes'] == 156126595
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
        assert len(names) == len(set(names)) == 1172
        assert all(not PurePosixPath(n).is_absolute() and '..' not in PurePosixPath(n).parts and '\\' not in n for n in names)
        official = Reader(archive)
        prefixes = {c: '_temp/a06-owner-negative' if c == 'owner-current-slot' else '_temp/a06-clock-handoff-negative/' + c for c in constants['CONTROLS']}
        official_rows, _, official_names = review_set(official, '_temp/a06-ktest', prefixes, constants, source, new_names, expected_negative=local_maps)
        assert official_names == green_names
        official_report = dict(shared, kind='independent official original seven controls',
                               controls=official_rows, negative_failed_counts=[r['failed'] for r in official_rows],
                               api_record_sha256=sha(api_path.read_bytes()),
                               archive={'path': str(archive_path), 'sha256': archive_hash, 'bytes': archive_size,
                                        'members': len(names), 'run_id': 39256580996, 'job_id': 118073271911, 'artifact_id': 12190114844},
                               all_official_mutant_file_maps_equal_git_verified_local_mutants=True,
                               raw_archive_member_records=list(official.records.values()),
                               scope_limits=['All seven complete 238-name suites and all 18 lifecycle tests were parsed from original raw serials. No producer, QEMU or artifact executable ran.',
                                             'Original source/OSDK/QEMU identities are checked against complete original receipts. Host executables absent from the artifact are not rehashed.',
                                             'Official ELF members were not extracted or fully streamed; retained member sizes and 64-byte ELF headers plus recorded SHA identities were checked. The complete ZIP SHA matches the official artifact API digest.',
                                             'Official negative commit objects are not present in the artifact; their complete tree/blob contents are independently checked and equal locally retained original mutations.',
                                             'No broader HOS2 authority, native grants, physical SMP or storage qualification is inferred.'],
                               finished_at=datetime.now(timezone.utc).isoformat(), passed=True)
    save('official-negative-sequence-review.json', official_report)


if __name__ == '__main__':
    main()
