#!/usr/bin/env python3
"""Preserve the main-based candidate and its newly executed validation receipts."""
from datetime import datetime, timezone
import hashlib
import json
import lzma
import os
from pathlib import Path
import subprocess

ROOT = Path('/workspace/scratch/499c7902de8e')
SOURCE = ROOT / 'r10-fleet-fixture-main-fix'
OLD_SOURCE = ROOT / 'r10-fleet-fixture-fix'
OUT = ROOT / 'r10-evidence/fleet-fixture-main-fix'
OLD_OUT = ROOT / 'r10-evidence/fleet-fixture-fix'
BASE = 'f8c9419df6ddeb36ff8b522a50219981fb8d9345'
HEAD = 'e770156ba8b35c77829d189fc053dc5f9eb69f8b'
TREE = '15a3b89f59052368e28ce5ed4943dc2ab638844b'
OLD_HEAD = '3749e151fd1a39c4b568afdb9e03028974ad86be'
OLD_TREE = 'eb9dc083dfb6f4f57a98f0380683444aba98326a'
CHANGED = 'codex-rs/hepta-fleet/src/authority_port.rs'


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(data):
    return hashlib.sha256(data).hexdigest()


def record(path, root=OUT):
    data = path.read_bytes()
    return {'path': path.relative_to(root).as_posix(), 'bytes': len(data), 'sha256': sha(data)}


def write(name, value):
    with (OUT / name).open('x', encoding='utf-8') as handle:
        handle.write(json.dumps(value, indent=2, ensure_ascii=False) + '\n')


def git(*args, source=SOURCE):
    return subprocess.check_output(['git', '-C', str(source), *args],
                                   env=dict(os.environ, GIT_NO_LAZY_FETCH='1'))


def state(source=SOURCE):
    return {'commit': git('rev-parse', 'HEAD', source=source).decode().strip(),
            'tree': git('rev-parse', 'HEAD^{tree}', source=source).decode().strip(),
            'status_porcelain': git('status', '--porcelain=v1', '--untracked-files=all',
                                    source=source).decode()}


def tree_entries(rev):
    result = {}
    for entry in git('ls-tree', '-r', '-z', '--full-tree', rev).split(b'\0'):
        if not entry:
            continue
        metadata, path = entry.split(b'\t', 1)
        mode, kind, blob = metadata.decode().split()
        result[path.decode()] = {'mode': mode, 'kind': kind, 'git_object': blob}
    return result


started = now()
current = state()
assert current == {'commit': HEAD, 'tree': TREE, 'status_porcelain': ''}
assert git('rev-parse', 'HEAD^').decode().strip() == BASE
assert git('diff', '--name-only', BASE, HEAD).decode().splitlines() == [CHANGED]
git('diff', '--check', BASE, HEAD)
assert git('rev-parse', f'{BASE}:{CHANGED}').decode().strip() == '55e117dafe84709451a638bb8f6bafa41c38bd5a'
assert git('show', f'{HEAD}:{CHANGED}') == git('show', f'{OLD_HEAD}:{CHANGED}')
for name, args in [('source.diff', ['diff', '--binary', '--no-ext-diff', BASE, HEAD]),
                   ('fixture-admission-assert-main.patch', ['format-patch', '-1', '--stdout', HEAD])]:
    with (OUT / name).open('xb') as handle:
        handle.write(git(*args))

old_entries, entries = tree_entries(OLD_HEAD), tree_entries(HEAD)
changes = []
for path in sorted(old_entries.keys() | entries.keys()):
    before, after = old_entries.get(path), entries.get(path)
    if before != after:
        changes.append({'path': path, 'old_candidate': before, 'main_candidate': after})
assert len(changes) == 29
raw_delta = git('diff', '--binary', '--no-ext-diff', '--no-textconv', '--no-renames', OLD_HEAD, HEAD)
compressed = lzma.compress(raw_delta, preset=6)
assert lzma.decompress(compressed) == raw_delta
with (OUT / 'comparison-with-d32-candidate.diff.xz').open('xb') as handle:
    handle.write(compressed)
prefixes = ('codex-rs/hepta-fleet/', 'codex-rs/hepta-contracts/', 'codex-rs/hepta-paths/',
            'codex-rs/.cargo/', 'codex-rs/.config/', '.cargo/')
explicit = {'AGENTS.md', 'justfile', 'scripts/format.py', 'scripts/just-shell.py',
            'scripts/run-nextest.py', 'codex-rs/Cargo.toml', 'codex-rs/Cargo.lock',
            'codex-rs/clippy.toml', 'codex-rs/deny.toml', '.bazelrc', 'rust-toolchain.toml',
            'codex-rs/rust-toolchain.toml', 'rustfmt.toml', 'codex-rs/rustfmt.toml'}
local_inputs = []
for path in sorted(entries):
    if path.startswith(prefixes) or path in explicit:
        assert entries[path] == old_entries.get(path), path
        assert git('show', f'{HEAD}:{path}') == (SOURCE / path).read_bytes(), path
        local_inputs.append(dict(record(SOURCE / path, SOURCE), **entries[path]))
assert any(row['path'] == CHANGED for row in local_inputs)
write('baseline-comparison.json', {
    'schema': 1, 'recorded_at': now(),
    'old_candidate': {'commit': OLD_HEAD, 'tree': OLD_TREE,
                      'parent': '1b0fedb8c2b510106848f6feaf530c9b3698399d',
                      'parent_remote_equivalent': 'd32e795f0d24df89fc57745f6fae70fbd0642eba'},
    'main_candidate': current, 'main_base': BASE,
    'pr_changed_paths_from_main': [CHANGED],
    'all_tracked_input_differences_between_candidates': changes,
    'difference_scope': 'Complete tracked-tree comparison, including file modes and Git object IDs; deletions here describe the baseline comparison, not the one-file main PR.',
    'full_binary_diff': {'raw_bytes': len(raw_delta), 'raw_sha256': sha(raw_delta),
                         'stored': record(OUT / 'comparison-with-d32-candidate.diff.xz')},
    'narrow_crate_and_runner_inputs': local_inputs,
    'all_listed_narrow_inputs_byte_identical_to_old_candidate': True,
    'test_execution': 'New execution at the main candidate; previous d32-based receipts are not reused as results.',
    'external_input_boundary': 'Cargo.lock pins registry/git dependencies; the existing offline cache and isolated target are reused. These are not described as fresh downloads or a cold build.'})

commands = []
for name in ['fmt-01', 'fleet-tests-01', 'fleet-clippy-01']:
    receipt = json.loads((OUT / name / 'receipt.json').read_text())
    assert receipt['exit_code'] == 0 and receipt['source_unchanged']
    assert receipt['source_before']['commit'] == HEAD
    assert receipt['source_before']['tree'] == TREE
    assert receipt['source_before']['status_porcelain'] == ''
    assert record(OUT / name / 'command.log', OUT / name) == receipt['log']
    commands.append({'name': name, 'receipt': record(OUT / name / 'receipt.json'),
                     'argv': receipt['argv'], 'started_at': receipt['started_at'],
                     'completed_at': receipt['completed_at'], 'exit_code': 0,
                     'source_unchanged': True})
test_text = (OUT / 'fleet-tests-01/command.log').read_text()
assert '41 tests run: 41 passed, 0 skipped' in test_text
fixture_line = next(line for line in test_text.splitlines() if 'PASS' in line and
                    'allocation_issue_consumes_exact_live_kernel_authority_lease' in line)
warnings = [line for line in test_text.splitlines() if 'warning:' in line]
clippy = (OUT / 'fleet-clippy-01/command.log').read_text()
assert not any(line.startswith(('warning:', 'error:')) for line in clippy.splitlines())

old_manifest_data = (OLD_OUT / 'files-manifest.json').read_bytes()
assert sha(old_manifest_data) == 'c42b3bc1774bd150d15ea563ce8fc088dd47c23cf0b1919350d912fa495c4232'
old_records = json.loads(old_manifest_data)['files']
for expected in old_records:
    assert record(OLD_OUT / expected['path'], OLD_OUT) == expected
actual_paths = {p.relative_to(OLD_OUT).as_posix() for p in OLD_OUT.rglob('*') if p.is_file()}
assert actual_paths == {r['path'] for r in old_records} | {'files-manifest.json'}
assert state(OLD_SOURCE) == {'commit': OLD_HEAD, 'tree': OLD_TREE, 'status_porcelain': ''}
assert state(ROOT / 'r10-hepta-ci-fix') == {
    'commit': '1b0fedb8c2b510106848f6feaf530c9b3698399d',
    'tree': 'a3e718280a7e17b8c4a226a0232bf18c23fd3586', 'status_porcelain': ''}

tool_data = (OLD_OUT / 'tools-installation.json').read_bytes()
tool_install = json.loads(tool_data)
for tool in tool_install['tools']:
    data = Path(tool['path']).read_bytes()
    assert len(data) == tool['bytes'] and sha(data) == tool['sha256']
with (OUT / 'reused-tools-installation.json').open('xb') as handle:
    handle.write(tool_data)
write('final-validation.json', {
    'schema': 1, 'started_at': started, 'completed_at': now(),
    'status': 'main_candidate_narrow_validation_passed', 'source': current,
    'parent': BASE, 'changed_paths_from_main': [CHANGED],
    'modified_file': record(SOURCE / CHANGED, SOURCE),
    'git_diff_check_exit': 0, 'baseline_comparison': record(OUT / 'baseline-comparison.json'),
    'commands': commands, 'tests': {'run': 41, 'passed': 41, 'failed': 0, 'skipped': 0,
                                   'fixture_pass_line': fixture_line, 'metadata_warnings': warnings},
    'strict_clippy': {'unwrap_used': 'deny', 'expect_used': 'deny', 'exit_code': 0},
    'tool_installation_receipt': record(OUT / 'reused-tools-installation.json'),
    'installed_component_binary_bytes_reverified': True,
    'previous_evidence': {'directory': str(OLD_OUT), 'files': len(actual_paths),
                          'manifest_sha256': sha(old_manifest_data), 'all_bytes_unchanged': True},
    'setup_failure_retained': 'checkout-01.json',
    'limitations': ['Linux x86_64 Cargo validation only; no Bazel, macOS, ARM64 or Windows execution.',
                    'No claim that dependency security debt or Windows sandbox boundary failures are repaired.',
                    'No remote ref, PR, CI workflow, rerun or merge was changed.',
                    'The previous d32-based validation remains a separate immutable execution.']})
assert state() == current
files = [record(path) for path in sorted(OUT.rglob('*')) if path.is_file()
         and path.name != 'files-manifest.json']
write('files-manifest.json', {'schema': 1, 'created_at': now(), 'commit': HEAD, 'tree': TREE,
      'files': files, 'excluded': ['The manifest itself to avoid a recursive digest.',
          'Source checkout, tool installations/downloads, Cargo/Rustup/registry/git caches, target.',
          'Original 20-file candidate evidence (referenced and reverified without modification).']})
print(json.dumps({'source': current, 'files': len(files) + 1,
                  'manifest': record(OUT / 'files-manifest.json'),
                  'validation': record(OUT / 'final-validation.json'),
                  'patch': record(OUT / 'fixture-admission-assert-main.patch'),
                  'tracked_input_differences': len(changes),
                  'narrow_inputs': len(local_inputs)}, indent=2))
