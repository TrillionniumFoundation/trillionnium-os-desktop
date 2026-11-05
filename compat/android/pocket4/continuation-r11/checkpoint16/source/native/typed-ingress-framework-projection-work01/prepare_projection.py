#!/usr/bin/env python3
"""Compose the frozen typed02 source into a normal framework projection patch.

This is a local source-composition operation. It performs no Java/C++ build,
remote action, source projection in AOSP, or platform authorization.
"""
from pathlib import Path
import difflib
import hashlib
import json
import os
import subprocess

HERE = Path(__file__).resolve().parent
NATIVE = HERE.parent
BASE = NATIVE / 'art-role-typed-ingress-freeze01'
NEXT = NATIVE / 'art-role-typed-explicit-ids-freeze02'
ROOT = 'frameworks/base/'
EXPECTED_MANIFESTS = {
    BASE / 'SOURCE_PINS.json': '73da8babb8cc62e5a841087f6a6937c674bef7ecb877777ddd189ff0696d947a',
    NEXT / 'SOURCE_PINS.json': 'fc0f6fae1773bad5a5290737fb6d0bb988d417ff1815f5ca92509e5299b678f9',
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def read_pin(path, expected):
    data = path.read_bytes()
    if len(data) != expected['bytes'] or digest(data) != expected['sha256']:
        raise RuntimeError('frozen source changed: ' + str(path))
    data.decode('utf-8')
    return data


def pin(path, data):
    return {'path': str(path), 'bytes': len(data), 'sha256': digest(data)}


def main():
    manifests = {}
    for path, expected in EXPECTED_MANIFESTS.items():
        raw = path.read_bytes()
        if digest(raw) != expected:
            raise RuntimeError('frozen manifest changed: ' + str(path))
        manifests[path.parent] = {row['path']: row for row in json.loads(raw)['files']}
    files = {}
    input_rows = []
    for name, expected in manifests[BASE].items():
        if not name.startswith('candidate/' + ROOT):
            continue
        relative = name.removeprefix('candidate/' + ROOT)
        source = BASE / name
        if relative == 'core/java/com/android/internal/os/ZygoteArguments.java':
            source = NEXT / 'candidate/ZygoteArguments.java'
            expected = manifests[NEXT]['candidate/ZygoteArguments.java']
        candidate = read_pin(source, expected)
        old_name = 'preimage/' + ROOT + relative
        if old_name in manifests[BASE]:
            old_path = BASE / old_name
            old = read_pin(old_path, manifests[BASE][old_name])
            input_rows.append(pin(old_path, old))
        else:
            if relative != 'core/jni/droidloom_app_zygote_spec.h':
                raise RuntimeError('unexpected new production source')
            old = None
        files[relative] = (old, candidate)
        input_rows.append(pin(source, candidate))
    if len(files) != 5 or sum(old is None for old, _ in files.values()) != 1:
        raise RuntimeError('exact four replacements and one header required')

    parts = []
    for relative, (old, candidate) in sorted(files.items()):
        parts.extend(difflib.unified_diff(
            [] if old is None else old.decode().splitlines(keepends=True),
            candidate.decode().splitlines(keepends=True),
            fromfile='/dev/null' if old is None else 'a/' + relative,
            tofile='b/' + relative,
        ))
    patch = ''.join(parts).encode()
    patch_path = HERE / 'typed-ingress02-framework.patch'
    with patch_path.open('xb') as stream:
        stream.write(patch)

    control = HERE / 'local-apply-control'
    control.mkdir(mode=0o700)
    for relative, (old, _) in files.items():
        if old is not None:
            path = control / relative
            path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            with path.open('xb') as stream:
                stream.write(old)
    git = Path('/usr/local/bin/git').resolve(strict=True)
    git_before = pin(git, git.read_bytes())
    env = {'PATH': '/usr/bin:/bin', 'LANG': 'C', 'LC_ALL': 'C',
           'GIT_CEILING_DIRECTORIES': str(HERE), 'GIT_CONFIG_NOSYSTEM': '1',
           'GIT_CONFIG_GLOBAL': '/dev/null'}
    commands = []

    def command(arguments):
        argv = [str(git), '-C', str(control), 'apply', *arguments, str(patch_path)]
        result = subprocess.run(argv, env=env, capture_output=True, timeout=10)
        commands.append({'argv': argv, 'returncode': result.returncode,
                         'stdout': result.stdout.decode(), 'stderr': result.stderr.decode()})
        if result.returncode != 0:
            raise RuntimeError('local normal-format git apply failed')

    command(['--check'])
    command([])
    for relative, (_, candidate) in files.items():
        if (control / relative).read_bytes() != candidate:
            raise RuntimeError('applied source differs: ' + relative)
    command(['--reverse', '--check'])
    command(['--reverse'])
    for relative, (old, _) in files.items():
        path = control / relative
        if old is None:
            if path.exists():
                raise RuntimeError('new header survived reverse apply')
        elif path.read_bytes() != old:
            raise RuntimeError('reverse source differs: ' + relative)
    if git_before != pin(git, git.read_bytes()):
        raise RuntimeError('local git changed')
    for row in input_rows:
        read_pin(Path(row['path']), row)
    result = {
        'schema': 1, 'state': 'LOCAL_SOURCE_PROJECTION_COMPOSED_AND_REVERSED',
        'normal_projection_relative_cwd': 'frameworks/base',
        'patch': pin(patch_path, patch), 'source_inputs': input_rows,
        'source_paths': sorted(ROOT + relative for relative in files),
        'commands': commands, 'local_git': git_before,
        'source_inputs_unchanged_after': True, 'candidate_bytes_exact': True,
        'preimage_bytes_restored': True,
        'Java_compiled': False, 'full_Android_TU_compiled': False,
        'normal_builder_integration_implemented': False,
        'actual_Java_module_definition_observed': False,
        'early_role_authorization_enabled': False, 'remote_actions': 0,
    }
    with (HERE / 'local-projection-result.json').open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({key: result[key] for key in ['state', 'patch', 'source_paths',
                      'Java_compiled', 'full_Android_TU_compiled', 'remote_actions']}, indent=2))


if __name__ == '__main__':
    main()
