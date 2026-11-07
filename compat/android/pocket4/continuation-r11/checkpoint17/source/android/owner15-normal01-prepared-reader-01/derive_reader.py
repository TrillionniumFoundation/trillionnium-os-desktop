"""Derive one exact prepared-report reader; never dispatch or collect."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

BASE = Path('/workspace/scratch/94990735b266')
OLD = BASE / 'lmkd-recovery-20261105-01/owner14-normal01-prepared-read-freeze-01'
OUT = BASE / 'android-owner15-normal01-prepared-reader-01'
ACTUAL = BASE / 'root-recovery-20261104-02/evidence/owner15-normal01-prepare01/stdout.log'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pretty(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def main():
    actual = ACTUAL.read_bytes()
    assert len(actual) == 233 and sha(actual) == '6d5e8adfedfb7f5941d65327ea74e19c0b4a9aa1700485aded77eb78707d5fe7'
    receipt = json.loads(actual)
    assert receipt == {'success': True, 'result_path': '/opt/p4-owner15-normal-20261105-01-state/prepared.json',
        'bytes': 55139, 'sha256': 'cdcf0db96db1c7100c17faa5c4b0926b544f8c41b8da8960e49788dee3926de8',
        'first_error': None, 'runtime_executed': False}
    old_manifest = (OLD / 'manifest.json').read_bytes()
    assert sha(old_manifest) == '8cbfee51c6fdd4d87e838f240b15ed8f687ac30e3196bc264dd91129cc8e811e'
    for row in json.loads(old_manifest)['files']:
        raw = (OLD / row['path']).read_bytes()
        assert len(raw) == row['bytes'] and sha(raw) == row['sha256']
    source = (OLD / 'read.py').read_text()
    assert sha(source.encode()) == '7a6408e2da7d9b0a37ae88ee56d7ba5187fcfa6b4381cf154cc38a7b0b8f5770'
    changes = (
        ('p4-owner14-normal-20261105-01-state', 'p4-owner15-normal-20261105-01-state'),
        ('5771673f20af6833e070da267b0ad9bcbbf58c87e03542104ac57fb9a4466770', receipt['sha256']),
        ('fixed-owner14-normal01-prepared-read', 'fixed-owner15-normal01-prepared-read'),
    )
    text = source
    for before, after in changes:
        assert text.count(before) == 1
        text = text.replace(before, after)
    inverse = text
    for before, after in reversed(changes):
        assert inverse.count(after) == 1
        inverse = inverse.replace(after, before)
    assert inverse == source
    ast.parse(text)
    compile(text, '<fixed Owner15 prepared reader>', 'exec')
    request = json.loads((OLD / 'request.json').read_bytes())
    assert request['stdin'] == source
    request['stdin'] = text
    request['idempotency_key'] = 'p4-owner15-normal01-prepared-read01-' + sha(text.encode())[:16]
    validation = {
        'scope': 'one fixed root-owned actual prepared report; collection only',
        'actual_terminal_stdout': {'bytes': len(actual), 'sha256': sha(actual)},
        'path': receipt['result_path'], 'expected_bytes': receipt['bytes'], 'expected_sha256': receipt['sha256'],
        'reader_sha256': sha(text.encode()), 'old_reader_sha256': sha(source.encode()),
        'only_three_literals_changed': True, 'inverse_transform_exact': True,
        'all_control_flow_and_FD_checks_preserved': True, 'hard_file_bound_bytes': 1048576,
        'exact_file_length_required': 55139, 'held_and_named_identity_checks_preserved': True,
        'double_read_preserved': True, 'runtime_qualification': False, 'collector_executed': False,
        'request_bytes': len(pretty(request)), 'request_sha256': sha(pretty(request)),
        'stdin_bytes': len(text.encode()), 'stdin_sha256': sha(text.encode()),
    }
    members = {'read.py': text.encode(), 'request.json': pretty(request), 'validation.json': pretty(validation),
        'source.diff': ''.join(difflib.unified_diff(source.splitlines(True), text.splitlines(True),
            fromfile='owner14-prepared/read.py', tofile='owner15-prepared/read.py')).encode(),
        'derive_reader.py': Path(__file__).read_bytes()}
    OUT.mkdir(mode=0o700)
    rows = []
    for name, raw in members.items():
        raw.decode('utf-8')
        with (OUT / name).open('xb') as stream:
            stream.write(raw)
        rows.append({'path': name, 'bytes': len(raw), 'sha256': sha(raw)})
    manifest = pretty({'kind': 'owner15_actual_prepared_fixed_reader', 'files': rows, 'executed': False})
    with (OUT / 'manifest.json').open('xb') as stream:
        stream.write(manifest)
    print(json.dumps({'directory': str(OUT), 'manifest_bytes': len(manifest), 'manifest_sha256': sha(manifest),
        'stable_key': request['idempotency_key'], **validation}, sort_keys=True))


if __name__ == '__main__':
    main()
