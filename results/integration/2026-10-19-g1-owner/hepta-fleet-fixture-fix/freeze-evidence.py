#!/usr/bin/env python3
"""Freeze existing narrow-validation evidence; never build or edit the checkout."""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess

ROOT = Path('/workspace/scratch/499c7902de8e')
SOURCE = ROOT / 'r10-fleet-fixture-fix'
OUT = ROOT / 'r10-evidence/fleet-fixture-fix'
BASE = '1b0fedb8c2b510106848f6feaf530c9b3698399d'
HEAD = '3749e151fd1a39c4b568afdb9e03028974ad86be'
TREE = 'eb9dc083dfb6f4f57a98f0380683444aba98326a'
CHANGED = 'codex-rs/hepta-fleet/src/authority_port.rs'


def record(path, root=OUT):
    data = path.read_bytes()
    return {'path': path.relative_to(root).as_posix(), 'bytes': len(data),
            'sha256': hashlib.sha256(data).hexdigest()}


def git(*args, source=SOURCE):
    env = dict(os.environ, GIT_NO_LAZY_FETCH='1')
    return subprocess.check_output(['git', '-C', str(source), *args], env=env)


def state(source):
    return {'commit': git('rev-parse', 'HEAD', source=source).decode().strip(),
            'tree': git('rev-parse', 'HEAD^{tree}', source=source).decode().strip(),
            'status_porcelain': git('status', '--porcelain=v1', '--untracked-files=all',
                                    source=source).decode()}


def write(name, value):
    path = OUT / name
    with path.open('x', encoding='utf-8') as handle:
        handle.write(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


started = datetime.datetime.now(datetime.timezone.utc).isoformat()
source = state(SOURCE)
assert source == {'commit': HEAD, 'tree': TREE, 'status_porcelain': ''}, source
assert git('rev-parse', 'HEAD^').decode().strip() == BASE
changed = git('diff', '--name-only', BASE, HEAD).decode().splitlines()
assert changed == [CHANGED], changed
git('diff', '--check', BASE, HEAD)
for name, args in [('source.diff', ['diff', '--binary', BASE, HEAD]),
                   ('fixture-admission-assert.patch', ['format-patch', '-1', '--stdout', HEAD])]:
    with (OUT / name).open('xb') as handle:
        handle.write(git(*args))

commands = []
for name in ['fmt-01', 'fleet-tests-01', 'fleet-clippy-01']:
    receipt_path = OUT / name / 'receipt.json'
    receipt = json.loads(receipt_path.read_text())
    assert receipt['exit_code'] == 0
    assert record(OUT / name / 'command.log', OUT / name) == receipt['log']
    if name != 'fmt-01':
        assert receipt['source_unchanged']
        assert receipt['source_before']['commit'] == HEAD
        assert receipt['source_before']['tree'] == TREE
        assert receipt['source_before']['status_porcelain'] == ''
    commands.append({'receipt': record(receipt_path), 'name': name,
                     'argv': receipt['argv'], 'started_at': receipt['started_at'],
                     'completed_at': receipt['completed_at'], 'exit_code': receipt['exit_code'],
                     'source_unchanged': receipt['source_unchanged']})
tests = (OUT / 'fleet-tests-01/command.log').read_text()
assert '41 tests run: 41 passed, 0 skipped' in tests
fixture_line = next(line for line in tests.splitlines() if
                    'PASS' in line and 'allocation_issue_consumes_exact_live_kernel_authority_lease' in line)
warnings = [line for line in tests.splitlines() if 'warning:' in line]
clippy = (OUT / 'fleet-clippy-01/command.log').read_text()
assert not any(line.startswith(('warning:', 'error:')) for line in clippy.splitlines())

baseline_blobs = {}
for rev in ['f8c9419df6ddeb36ff8b522a50219981fb8d9345',
            '2be5fc052ae7b2e9fb08c68a3ae7e5a218ad37d5', BASE]:
    baseline_blobs[rev] = git('rev-parse', f'{rev}:{CHANGED}').decode().strip()
assert set(baseline_blobs.values()) == {'55e117dafe84709451a638bb8f6bafa41c38bd5a'}
unchanged = []
for name in ['codex-rs/Cargo.lock', 'codex-rs/Cargo.toml', 'codex-rs/deny.toml',
             'codex-rs/clippy.toml', '.bazelrc', 'AGENTS.md']:
    current = (SOURCE / name).read_bytes()
    assert current == git('show', f'{BASE}:{name}')
    unchanged.append(record(SOURCE / name, SOURCE))
original = state(ROOT / 'r10-hepta-ci-fix')
assert original == {'commit': BASE, 'tree': 'a3e718280a7e17b8c4a226a0232bf18c23fd3586',
                    'status_porcelain': ''}, original

frozen = []
for name, expected in [
        ('security-debt-package', 'd7606ca14b4d7924f063cf2b32e4806164fe7b2565e362426c95e929adc4fa5f'),
        ('bazel-followup-package', '1017903c2c4330d5f84dd11b83a7c22bc20bde4655cbcb125d10bbd4650a53c7')]:
    directory = ROOT / 'r10-evidence/owner-ci' / name
    manifest_record = record(directory / 'artifact-manifest.json', directory)
    assert manifest_record['sha256'] == expected
    manifest = json.loads((directory / 'artifact-manifest.json').read_text())
    entries = [manifest[key] for key in ['archive', 'files_manifest', 'packaging_helper']]
    entries += manifest['primary_copies']
    for entry in entries:
        assert record(directory / entry['path'], directory) == {
            key: entry[key] for key in ['path', 'bytes', 'sha256']}
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob('*') if p.is_file()}
    expected_paths = {entry['path'] for entry in entries} | {'artifact-manifest.json'}
    assert actual == expected_paths, (actual, expected_paths)
    frozen.append({'directory': str(directory), 'files_verified': len(actual),
                   'artifact_manifest': manifest_record, 'all_delivery_bytes_unchanged': True})

write('final-validation.json', {
    'schema': 1, 'started_at': started,
    'completed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'status': 'narrow_validation_passed', 'source': source, 'parent_commit': BASE,
    'base_remote_equivalent': 'd32e795f0d24df89fc57745f6fae70fbd0642eba',
    'changed_paths': changed, 'changed_source': record(SOURCE / CHANGED, SOURCE),
    'original_helper_blobs': baseline_blobs, 'git_diff_check_exit': 0,
    'commands': commands, 'tests': {'run': 41, 'passed': 41, 'failed': 0, 'skipped': 0,
                                   'fixture_pass_line': fixture_line,
                                   'metadata_warnings': warnings},
    'strict_clippy': {'unwrap_used': 'deny', 'expect_used': 'deny', 'exit_code': 0,
                      'warning_or_error_diagnostic_lines': 0},
    'unchanged_policy_lock_and_instructions': unchanged,
    'original_worktree': original, 'frozen_packages': frozen,
    'limitations': ['Linux x86_64 Cargo validation only; no Bazel CI replay.',
                    'No macOS, ARM64, or Windows run was performed for this patch.',
                    'Windows sandbox boundary failures and dependency security debt remain unresolved.',
                    'Original remote d32 CI failures remain valid observations.',
                    'No GitHub ref, PR, workflow, gate, dependency, or policy was changed.']})
assert state(SOURCE) == source
files = [record(path) for path in sorted(OUT.rglob('*')) if path.is_file()
         and path.name != 'files-manifest.json']
write('files-manifest.json', {'schema': 1,
      'created_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
      'source_commit': HEAD, 'source_tree': TREE,
      'excluded': ['The manifest itself to avoid a recursive digest.',
                   'Installed tool binaries and download archives outside this evidence directory.',
                   'Cargo/Rustup/registry/git caches and the isolated target directory.',
                   'Full source checkout and unrelated frozen evidence packages.'],
      'files': files})
print(json.dumps({'source': source, 'files': len(files) + 1,
                  'manifest': record(OUT / 'files-manifest.json'),
                  'validation': record(OUT / 'final-validation.json'),
                  'patch': record(OUT / 'fixture-admission-assert.patch')}, indent=2))
