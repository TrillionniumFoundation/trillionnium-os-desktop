from pathlib import Path
import difflib
import hashlib
import json
import os
import shutil
import subprocess

ROOT = Path(__file__).resolve().parent
OLD = ROOT / 'producer07-audit-freeze-01'
NEW = ROOT / 'producer07-audit-freeze-02'
REL = 'runtime/droidloom-supervisor/src/relay_lifecycle/audit.rs'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def put(name, raw):
    with (NEW / name).open('xb') as out:
        out.write(raw)


def js(value):
    return (json.dumps(value, indent=2, sort_keys=True) + '\n').encode()


os.umask(0o077)
old_manifest = (OLD / 'manifest.json').read_bytes()
assert sha(old_manifest) == 'c91fcbb5318d01848d00eb533ddef8b4bed4ad53b59c95a54db0e12315bb672d'
for row in json.loads(old_manifest)['files']:
    raw = (OLD / row['path']).read_bytes()
    assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
NEW.mkdir(mode=0o700)
shutil.copytree(OLD / 'source', NEW / 'source', copy_function=shutil.copyfile)
shutil.copytree(OLD / 'baseline-deadline06', NEW / 'baseline-deadline06', copy_function=shutil.copyfile)
before = (OLD / 'source' / REL).read_bytes()
assert sha(before) == 'f142b520b19748c80d466f5dd7b4e4e59f1706e76d3c3f2aecfbf5fc7855389c'
assert before.count(b'let hex = |value: &str, bytes|') == 1
after = before.replace(b'let hex = |value: &str, bytes|', b'let hex = |value: &str, bytes: usize|')
(NEW / 'source' / REL).write_bytes(after)
for name in ['source_controls.py', 'FIELD-SOURCES.md', 'PRIVATE-CELL-NEXT.md']:
    put(name, (OLD / name).read_bytes())
delta = ''.join(difflib.unified_diff(before.decode().splitlines(True), after.decode().splitlines(True),
    fromfile='producer07-audit01/' + REL, tofile='producer07-audit02/' + REL))
put('producer07-audit01-to02.patch', delta.encode())
original_files = {str(p.relative_to(OLD / 'source')): p.read_bytes() for p in (OLD / 'source').rglob('*') if p.is_file()}
new_files = {str(p.relative_to(NEW / 'source')): p.read_bytes() for p in (NEW / 'source').rglob('*') if p.is_file()}
assert set(original_files) == set(new_files) and len(new_files) == 32
assert [p for p in sorted(new_files) if original_files[p] != new_files[p]] == [REL]
assert new_files[REL] == original_files[REL].replace(b'let hex = |value: &str, bytes|', b'let hex = |value: &str, bytes: usize|')
result = subprocess.run(['/usr/bin/python3', str(NEW / 'source_controls.py')], cwd='/', capture_output=True, timeout=30)
put('local-source-controls.stdout', result.stdout)
put('local-source-controls.stderr', result.stderr)
assert result.returncode == 0, result.stderr.decode()
controls = json.loads((NEW / 'source-control-result.json').read_bytes())
inputs = {k: controls[k] for k in ['basis_inputs', 'candidate_inputs', 'changed_inputs']}
inputs.update(schema=1, revision='producer07-audit02', basis='Exact producer06 recovery04 basis; producer07 audit01 actual compile failed E0277; this revision changes only the bytes closure type annotation.')
put('input-manifest.json', js(inputs))
failure = {
    'schema': 1, 'provenance': 'authoritative remote terminal and receipt reported by parent; original full bytes retained by parent',
    'job_id': '1a1a9467daa-fc05-3399', 'terminal': 'failed', 'exit_code': 1, 'durable': True,
    'receipt': {'bytes': 24122, 'sha256': 'e7eff058dd6c00b50fa9b71042c8959c561102ebc17f0511712d373b65d76087'},
    'command00_stdout': {'bytes': 63232, 'sha256': 'a28b8685d9dc8b7a9340f6b4457ec5da57f1332a1966d973d075875e168598fe'},
    'cargo_exit_code': 101, 'timed_out': False, 'error': 'E0277 audit.rs:207: usize length compared with inferred i32 bytes * 2',
    'own_memory_peak': 611508224, 'own_swap_peak': 0, 'own_max_oom_oom_kill': [0, 0, 0],
    'rust_tests_executed': False, 'prior_source_manifest_sha256': sha(old_manifest),
    'prior_git_tree': '58bff669c2dd233e953ce95dbdba6a842bf32f1e',
}
put('prior-audit01-actual-failure-reference.json', js(failure))
put('validation.json', js({
    'schema': 1, 'revision': 'producer07-audit02', 'source_control_checks_passed': controls['check_count'],
    'source_control_receipt_sha256': sha((NEW / 'source-control-result.json').read_bytes()),
    'only_production_change': REL + ': bytes -> bytes: usize', 'unchanged_production_inputs': 31,
    'rust_build_performed': False, 'new_rust_tests_executed': False, 'actual_owner_lifecycle_qualified': False,
    'android_constructor_executed': False, 'main_modified': False, 'prior_failure_preserved': True,
    'source_predicted_relay_library_tests': 23, 'source_predicted_supervisor_library_tests': 119,
    'remote_calls_performed_for_this_revision': False,
}))
readme = '''# Producer07 audit02: exact Rust type correction

The actual audit01 matching build failed with E0277 in audit.rs:207. The closure parameter `bytes` was inferred as i32 while String::len returns usize. This revision adds the explicit `bytes: usize` annotation. The other 31 candidate inputs are byte-for-byte unchanged; the public authority, lifecycle, cleanup, timeout, observation bounds and tests remain unchanged.

The original audit01 source and failed build are preserved. `prior-audit01-actual-failure-reference.json` binds the parent-observed original terminal and full-receipt hashes; it is not a substitute for those original bytes.

This freeze contains the complete 32 candidate inputs, exact 31-input deadline06 basis, full basis-to-candidate patch, narrow audit01-to02 patch, and actual local source/patch controls. No Rust compiler or new Rust test ran locally. Matching compile, ordinary tests, actual Rust Owner and Android constructor qualification remain pending.

`FIELD-SOURCES.md` and `PRIVATE-CELL-NEXT.md` are unchanged from audit01 and continue to define the data-only interface and later private NORMAL scope. No Main or host-network action is authorized by this source freeze.
'''
put('README.md', readme.encode())
files = []
for p in sorted(NEW.rglob('*')):
    if p.is_file():
        raw = p.read_bytes()
        raw.decode('utf-8')
        files.append({'path': str(p.relative_to(NEW)), 'bytes': len(raw), 'sha256': sha(raw), 'encoding': 'utf-8'})
manifest = {'schema': 1, 'revision': 'producer07-audit02', 'ancestor_tree': failure['prior_git_tree'],
    'ancestor_source_manifest_sha256': sha(old_manifest), 'file_count': len(files), 'files': files,
    'rust_or_android_qualification': False}
put('manifest.json', js(manifest))
for p in NEW.rglob('*'):
    if p.is_file(): p.chmod(0o444)
print(json.dumps({'freeze': str(NEW), 'file_count': len(files), 'source_sha256': sha(after), 'source_bytes': len(after),
    'delta_sha256': sha(delta.encode()), 'delta_bytes': len(delta.encode()), 'full_diff_sha256': sha((NEW / 'producer06-to07-audit.patch').read_bytes()),
    'manifest_sha256': sha((NEW / 'manifest.json').read_bytes()), 'manifest_bytes': (NEW / 'manifest.json').stat().st_size,
    'source_controls': json.loads(result.stdout)}))
