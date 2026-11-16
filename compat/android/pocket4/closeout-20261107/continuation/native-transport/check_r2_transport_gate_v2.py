"""Read-only original qualification and synthetic journal controls; never runs Git."""
from pathlib import Path
import copy
import hashlib
import json
import os
import stat
import sys
import time
import types

ROOT = Path('/home/alex/work/pocket4-android-final/native/source-evidence/native-r2-transport-independent-review-20261108-r1')
MODULE = ROOT / 'r2_transport_gate_v2.py'
raw_module = MODULE.read_bytes()
assert hashlib.sha256(raw_module).hexdigest() == '04c0fda522b486ee5bcf9823f440384622b6c17b0fdd01a0b9f5a0165f0a4981'
scope = types.ModuleType('independent_r2_transport_gate')
scope.__file__ = str(MODULE)
exec(compile(raw_module, str(MODULE), 'exec'), scope.__dict__)
rows = []
inputs = {}
aliases = {}

def identity(st):
    return [st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid,
            st.st_nlink, st.st_size, st.st_mtime_ns, st.st_ctime_ns]

def read_exact(pin, expected_path, maximum, allow_empty=False):
    path = Path(expected_path)
    assert pin['path'] == str(path) and path.is_absolute() and '..' not in path.parts
    assert type(pin['bytes']) is int and 0 <= pin['bytes'] <= maximum
    assert allow_empty or pin['bytes'] > 0
    for parent in path.parents:
        assert stat.S_ISDIR(parent.lstat().st_mode), str(parent)
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        before = os.fstat(fd)
        assert stat.S_ISREG(before.st_mode) and before.st_size == pin['bytes']
        alias = None
        if path == scope.NORMAL_CLI:
            assert before.st_nlink == 2 and before.st_uid == before.st_gid == 1000
            assert stat.S_IMODE(before.st_mode) == 0o555
            candidates = [p for p in (path.parent / 'deps').glob('droidloom_source-*')
                          if identity(p.lstat()) == identity(before)]
            assert len(candidates) == 1
            alias = candidates[0]
            aliases[str(path)] = str(alias)
        else:
            assert before.st_nlink == 1
        blocks = []
        total = 0
        while True:
            chunk = os.read(fd, min(1024 * 1024, maximum + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            assert total <= maximum
            blocks.append(chunk)
        raw = b''.join(blocks)
        assert len(raw) == pin['bytes'] and hashlib.sha256(raw).hexdigest() == pin['sha256'], str(path)
        assert identity(before) == identity(os.fstat(fd)) == identity(path.lstat())
        if alias is not None:
            assert identity(alias.lstat()) == identity(before)
        record = {'path': str(path), 'bytes': len(raw), 'sha256': pin['sha256'], 'identity': identity(before)}
        assert str(path) not in inputs or inputs[str(path)] == record
        inputs[str(path)] = record
        return raw
    finally:
        os.close(fd)

def portable(value):
    return {k: value[k] for k in ('path', 'bytes', 'sha256')}

qualified = scope.qualify_normal_cli(read_exact)
classifier = read_exact(scope.R2_CLASSIFIER_SOURCE_PIN, Path(scope.R2_CLASSIFIER_SOURCE_PIN['path']), 65536)
assert b'gnutls recv error (-110): the tls connection was non-properly terminated.' in classifier
qualification = json.loads(read_exact(scope.NORMAL_CLI_QUALIFICATION_PIN,
    Path(scope.NORMAL_CLI_QUALIFICATION_PIN['path']), 65536))
source_manifest_ref = qualification['compiled_source_manifest']
source_manifest = json.loads(read_exact(source_manifest_ref, Path(source_manifest_ref['path']), 128 * 1024))
source_root = Path(source_manifest['source_root'])
assert source_root == scope.RETRY_ROOT / 'source' and source_manifest['file_count'] == 457
expected = {x['path']: x for x in source_manifest['files']}
assert len(expected) == 457 and all(x['kind'] == 'file' for x in expected.values())
actual = set()
for parent, directories, files in os.walk(source_root, followlinks=False):
    for name in directories:
        assert stat.S_ISDIR((Path(parent) / name).lstat().st_mode)
    for name in files:
        actual.add(str((Path(parent) / name).relative_to(source_root)))
assert actual == set(expected)
for relative, row in expected.items():
    path = source_root / relative
    read_exact({'path': str(path), 'bytes': row['bytes'], 'sha256': row['sha256']},
               path, 8 * 1024 * 1024, allow_empty=row['bytes'] == 0)
old_manifest_path = Path('/home/alex/work/pocket4-native-source-transport-retry-20261108-r1/audit/compiled-source-manifest.json')
old_manifest = json.loads(read_exact({'path': str(old_manifest_path), 'bytes': 95069,
    'sha256': 'd7093351ae2eb17a8141dfbe683fcc21e4be7b90a57080809174a616ae0c24dd'}, old_manifest_path, 128 * 1024))
old = {x['path']: x for x in old_manifest['files']}
assert set(old) == set(expected)
changed = sorted(k for k in old if old[k] != expected[k])
assert changed == ['tools/droidloom-source/src/git_retry.rs']
cg = Path('/sys/fs/cgroup/user.slice/user-1000.slice/user@1000.service/app.slice/hepta-runtime-job-1a1bb00c20d-12894-1f01.service')
assert not cg.exists()
rows.append({'case': 'actual_r2_compiler_tests_binary_source_and_retirement_binding', 'passed': True,
             'input_kind': 'actual immutable files', 'source_file_count': 457, 'changed_from_r1': changed})

def qualification_negative(name, target, mutate):
    def synthetic_reader(pin, expected_path, maximum, allow_empty=False):
        raw = read_exact(pin, expected_path, maximum, allow_empty=allow_empty)
        if str(expected_path) == target:
            value = json.loads(raw)
            mutate(value)
            return json.dumps(value).encode()
        return raw
    try:
        scope.qualify_normal_cli(synthetic_reader)
    except (RuntimeError, AssertionError, KeyError) as error:
        rows.append({'case': name, 'passed': True, 'accepted': False,
                     'input_kind': 'synthetic mutation of pinned actual evidence in memory',
                     'rejection': str(error)})
    else:
        raise AssertionError(name + ': unexpected acceptance')

qualification_negative('r1_qualification_is_not_r2', scope.NORMAL_CLI_QUALIFICATION_PIN['path'],
    lambda d: d.update(candidate_root='/home/alex/work/pocket4-native-source-transport-retry-20261108-r1'))
qualification_negative('r1_terminal_cannot_back_r2', scope.NORMAL_CLI_PROCESS_RESULT_PIN['path'],
    lambda d: d['build']['status'].update(job_id='1a1ba9759a7-12894-1bcc'))
qualification_negative('incomplete_H_terminal_cannot_back_r2', scope.NORMAL_CLI_PROCESS_RESULT_PIN['path'],
    lambda d: d['build']['status'].update(output_complete=False))
qualification_negative('wrong_R2_generation_cannot_back_r2', scope.NORMAL_CLI_PROCESS_RESULT_PIN['path'],
    lambda d: d['build']['status'].update(launch_nonce='0' * 32))

GNUTLS = b"fatal: unable to access 'https://android.googlesource.com/platform/packages/services/CrossDeviceSync/': GnuTLS recv error (-110): The TLS connection was non-properly terminated.\n"
CURL = b'error: RPC failed; curl 56 Recv failure: Connection timed out\n'
STEP = {'pid': 4100, 'started_ns': 1000000000, 'finished_ns': 10000000000}

def fixture(stderr=GNUTLS, failures=1):
    rows = [{'schema_version': 1, 'event': 'header', 'process_id': STEP['pid'],
             'at_unix_ms': 1000, 'maximum_attempts': 3, 'retry_operations': ['fetch', 'checkout'],
             'backoff_ms': [1000, 3000], 'lock_sha256': scope.NEW_SHA,
             'destination_hex': str(scope.SOURCE).encode().hex(), 'output_encoding': 'hex',
             'environment_values_logged': False}]
    for index in range(failures + 1):
        attempt = index + 1
        at = 1100 + index * 1100
        start = {'schema_version': 1, 'event': 'attempt_start', 'process_id': STEP['pid'],
                 'command_id': 1, 'attempt': attempt, 'operation': 'fetch', 'at_unix_ms': at,
                 'program_hex': b'git'.hex(), 'argv_hex': [x.hex() for x in [b'-C', b'/fixed/project', b'fetch', b'--depth=1', b'origin', b'pinned']],
                 'cwd_hex': str(scope.C / 'builder-source-r4').encode().hex(),
                 'environment_sha256': 'b' * 64}
        failed = index < failures
        finish = {'schema_version': 1, 'event': 'attempt_finish', 'process_id': STEP['pid'],
                  'command_id': 1, 'attempt': attempt, 'operation': 'fetch', 'at_unix_ms': at + 5,
                  'started_at_unix_ms': at, 'elapsed_ms': 5, 'child_pid': 4200 + index,
                  'signal': None, 'exit_code': 128 if failed else 0,
                  'stdout_hex': b'\0binary\xff'.hex(), 'stderr_hex': stderr.hex() if failed else b''.hex(),
                  'decision': 'transient_retry' if failed else 'success', 'retry': failed,
                  'backoff_ms': (1000 if attempt == 1 else 3000) if failed else 0}
        rows.extend([start, finish])
    return rows

def encode(values):
    return b''.join((json.dumps(x, sort_keys=True) + '\n').encode() for x in values)

def case(name, values, accepted, transform=None):
    raw = encode(values)
    if transform is not None:
        raw = transform(raw)
    try:
        result = scope.validate_transport_journal(raw, STEP)
    except Exception as error:
        assert not accepted, (name, repr(error))
        rows.append({'case': name, 'passed': True, 'accepted': False, 'rejection': str(error),
                     'input_kind': 'synthetic in-memory journal; no source operation'})
    else:
        assert accepted, name
        rows.append({'case': name, 'passed': True, 'accepted': True, 'summary': result,
                     'input_kind': 'synthetic in-memory journal; no source operation'})

case('gnutls_retry_followed_by_actual_success_shape', fixture(), True)
case('curl56_existing_retry_shape_retained', fixture(CURL), True)
case('cached_source_no_git_operations_shape', fixture()[:1], True)
case('wrong_gnutls_error_code_rejected', fixture(GNUTLS.replace(b'(-110)', b'(-54)')), False)
for name, text in [('certificate', b'SSL certificate problem'), ('auth', b'Authentication failed'), ('disk', b'No space left on device')]:
    case('complete_stderr_' + name + '_hard_denial_rejected', fixture(GNUTLS + b'x' * 5000 + text), False)
case('partial_diagnostic_rejected', fixture(b'GnuTLS recv error (-110)'), False)
x = fixture(); x[2]['exit_code'] = 1; case('non128_failure_rejected', x, False)
x = fixture(); x[2]['signal'] = 15; case('signalled_git_rejected', x, False)
x = fixture(); x[3]['argv_hex'][-1] = b'changed'.hex(); case('retry_context_change_rejected', x, False)
case('fourth_attempt_rejected', fixture(failures=3), False)
case('incomplete_journal_rejected', fixture(), False, lambda raw: raw[:-1])
case('no_final_success_rejected', fixture()[:3], False)
x = fixture(); x[0]['lock_sha256'] = '0' * 64; case('other_lock_rejected', x, False)
x = fixture(); x[2]['process_id'] = 1; case('other_process_rejected', x, False)

for path, pin in list(inputs.items()):
    read_exact(portable(pin), Path(path), max(1, pin['bytes']), allow_empty=pin['bytes'] == 0)
assert len(sys.argv) == 2
output = Path(sys.argv[1])
assert output.parent == ROOT and not output.exists()
result = {'schema': 'native-r2-transport-independent-review-v1', 'all_passed': True,
          'passed': len(rows), 'expected': 21, 'rows': rows, 'qualified_existing_cli': qualified,
          'module': {'path': str(MODULE), 'bytes': len(raw_module), 'sha256': hashlib.sha256(raw_module).hexdigest()},
          'r2_binary_alias': aliases, 'input_file_count': len(inputs),
          'input_identities_sha256': hashlib.sha256(json.dumps(inputs, sort_keys=True).encode()).hexdigest(),
          'all_read_inputs_before_after_equal': True, 'source_file_count': 457,
          'source_changed_from_r1': changed, 'observed_ns': time.time_ns(),
          'materializer_invocations': 0, 'source_locks_acquired': False,
          'Rust_compilations': 0, 'Soong_invocations': 0, 'Main_actions': 0, 'Android_actions': 0,
          'actual_Audio316_retirement_qualified': False, 'normal_materialization_qualified': False,
          'source_closure_qualified': False, 'fullpair_execution_admitted': False,
          'runtime_qualified': False, 'actual_source_journal_success_claimed': False,
          'original_R2_four_tests_read_not_rerun_or_reattributed': True}
assert len(rows) == 21
raw = (json.dumps(result, indent=2, sort_keys=True) + '\n').encode()
with output.open('xb') as stream:
    stream.write(raw)
    stream.flush()
    os.fsync(stream.fileno())
print(json.dumps({'all_passed': True, 'passed': len(rows), 'result': {'path': str(output),
    'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()}}))
