"""Verify fixed inputs and real patch round trips; never compile or use devices."""
from pathlib import Path
import hashlib
import json
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parent


def digest(body):
    return hashlib.sha256(body).hexdigest()


def checked(command, cwd):
    result = subprocess.run(command, cwd=cwd, capture_output=True, check=False)
    record = {
        'argv': command,
        'exit_code': result.returncode,
        'stdout_bytes': len(result.stdout),
        'stdout_sha256': digest(result.stdout),
        'stderr_bytes': len(result.stderr),
        'stderr_sha256': digest(result.stderr),
    }
    if result.returncode:
        raise RuntimeError(json.dumps(record) + '\n' + result.stderr.decode(errors='replace'))
    return record


def main():
    inputs_raw = (ROOT / 'INPUTS.json').read_bytes()
    manifest_raw = (ROOT / 'MANIFEST.json').read_bytes()
    inputs = json.loads(inputs_raw)
    manifest = json.loads(manifest_raw)
    base = ROOT / 'base/linux-6.18.64'
    candidate = ROOT / 'candidate'
    before = {}
    for entry in inputs['files']:
        name = entry['path'].removeprefix(inputs['kernel_root'] + '/')
        assert name != entry['path']
        body = (base / name).read_bytes()
        assert len(body) == entry['size'] and digest(body) == entry['sha256']
        before[name] = body
    assert len(before) == 12
    assert manifest['inputs'] == {'bytes': len(inputs_raw), 'sha256': digest(inputs_raw)}
    patch = (ROOT / 'K0a.patch').read_bytes()
    assert manifest['patch'] == {'bytes': len(patch), 'sha256': digest(patch)}
    expected_paths = {
        'block/Kconfig', 'block/Makefile',
        'block/p4_private_loop_actor.c', 'include/linux/p4_private_loop_actor.h',
    }
    assert {row['path'] for row in manifest['files']} == expected_paths
    assert len(manifest['files']) == len(expected_paths)
    for row in manifest['files']:
        name = row['path']
        body = (candidate / name).read_bytes()
        assert row['after'] == {'bytes': len(body), 'sha256': digest(body)}
        old = before.get(name)
        assert row['before'] == (None if old is None else {'bytes': len(old), 'sha256': digest(old)})

    records = []
    with tempfile.TemporaryDirectory(prefix='k0a-source-roundtrip-') as temporary:
        work = Path(temporary)
        for name, body in before.items():
            target = work / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(body)
        records.append(checked(['git', 'apply', '--check', '--whitespace=error-all', str(ROOT / 'K0a.patch')], work))
        records.append(checked(['git', 'apply', '--whitespace=error-all', str(ROOT / 'K0a.patch')], work))
        for name in expected_paths:
            assert (work / name).read_bytes() == (candidate / name).read_bytes(), name
        for name in before.keys() - expected_paths:
            assert (work / name).read_bytes() == before[name], name
        records.append(checked(['git', 'apply', '--check', '--reverse', '--whitespace=error-all', str(ROOT / 'K0a.patch')], work))
        records.append(checked(['git', 'apply', '--reverse', '--whitespace=error-all', str(ROOT / 'K0a.patch')], work))
        for name, body in before.items():
            assert (work / name).read_bytes() == body, name
        for name in expected_paths - before.keys():
            assert not (work / name).exists(), name
        remaining = {str(p.relative_to(work)) for p in work.rglob('*') if p.is_file()}
        assert remaining == set(before)

    compile((ROOT / 'prepare.py').read_bytes(), str(ROOT / 'prepare.py'), 'exec')
    result = {
        'schema': 'p4-private-loop-k0a-source-patch-verification-v1',
        'state': 'PINNED_INPUTS_AND_REAL_PATCH_ROUND_TRIP_VERIFIED',
        'inputs': {'bytes': len(inputs_raw), 'sha256': digest(inputs_raw)},
        'manifest': {'bytes': len(manifest_raw), 'sha256': digest(manifest_raw)},
        'patch': {'bytes': len(patch), 'sha256': digest(patch)},
        'pinned_complete_input_files': len(before),
        'changed_or_added_candidate_files': len(expected_paths),
        'other_input_files_unchanged_forward': len(before.keys() - expected_paths),
        'all_original_files_restored_reverse': True,
        'added_files_absent_after_reverse': True,
        'commands': records,
        'prepare_python_syntax_valid': True,
        'C_compiler_executed': False,
        'kernel_runtime_tests_executed': False,
        'kernel_loaded': False,
        'device_operations_executed': False,
        'Android_started': False,
        'runtime_qualified': False,
        'production_ready': False,
    }
    raw = (json.dumps(result, sort_keys=True, indent=2) + '\n').encode()
    (ROOT / 'STATIC-VERIFICATION.json').write_bytes(raw)
    print(json.dumps({'bytes': len(raw), 'sha256': digest(raw), 'state': result['state']}))


if __name__ == '__main__':
    main()
