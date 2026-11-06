"""Create-only exact Owner18 prepared reader from the retained actual summary."""
import ast
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path('/workspace/scratch/94990735b266')
OLD = ROOT / 'android-owner17-normal01-prepared-reader-01'
OUT = ROOT / 'android-owner18-normal01-prepared-reader-01'
ACTUAL = ROOT / 'root-recovery-20261104-02/evidence/owner18-normal-prepare01/stdout.log'


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def pretty(value):
    return (json.dumps(value, sort_keys=True, indent=2) + '\n').encode()


def main():
    actual = ACTUAL.read_bytes()
    assert len(actual) == 233 and sha(actual) == '1be888827e5e3938622aa4041354547b617a063dfe37143a76756d9d4d4301e0'
    receipt = json.loads(actual)
    assert receipt == {'success': True, 'result_path': '/opt/p4-owner18-normal-20261105-01-state/prepared.json',
        'bytes': 55273, 'sha256': '0e8182f704c6c0f52f914c9d2f46392c646b20062baff3bfc46711dd75123fc7',
        'first_error': None, 'runtime_executed': False}
    original = (OLD / 'read.py').read_bytes()
    assert len(original) == 4839 and sha(original) == '26ae3f1472759be10c019e2317ca042f0926799ee0119a8d62f7eb667ce23aec'
    request_raw = (OLD / 'request.json').read_bytes()
    assert len(request_raw) == 5300 and sha(request_raw) == '404ff0ac01d81b0c21cff24276cfa7024d9b3eac0a6d4f26ae69a97aef8b7286'
    source = original.decode()
    changes = (
        ('p4-owner17-normal-20261105-01-state', 'p4-owner18-normal-20261105-01-state'),
        ('b31dbe0fccd293b05687f28caa7e747f0f5b6092585611c9670ffb86c87d0b8d', receipt['sha256']),
        ('EXPECTED_REPORT_BYTES = 55139', 'EXPECTED_REPORT_BYTES = 55273'),
        ('fixed-owner17-normal01-prepared-read', 'fixed-owner18-normal01-prepared-read'))
    text = source
    for before, after in changes:
        assert text.count(before) == 1
        text = text.replace(before, after)
    inverse = text
    for before, after in reversed(changes):
        assert inverse.count(after) == 1
        inverse = inverse.replace(after, before)
    assert inverse == source and ast.dump(ast.parse(inverse)) == ast.dump(ast.parse(source))
    ast.parse(text); compile(text, '<fixed Owner18 prepared reader>', 'exec')
    request = json.loads(request_raw)
    assert request['stdin'] == source
    request.update(stdin=text, idempotency_key='p4-owner18-normal01-prepared-read01-' + sha(text.encode())[:16])
    assert {k: v for k, v in request.items() if k not in ('stdin', 'idempotency_key')} == {
        k: v for k, v in json.loads(request_raw).items() if k not in ('stdin', 'idempotency_key')}
    validation = {'scope': 'one externally pinned actual root-owned prepared report; collection only',
        'actual_terminal_stdout': {'bytes': len(actual), 'sha256': sha(actual)},
        'path': receipt['result_path'], 'expected_bytes': receipt['bytes'], 'expected_sha256': receipt['sha256'],
        'reader_sha256': sha(text.encode()), 'old_reader_sha256': sha(original),
        'only_four_literals_changed': True, 'inverse_bytes_and_AST_exact': True,
        'original_control_flow_FD_and_resource_gates_unchanged': True,
        'hard_file_bound_bytes': 1048576, 'held_named_and_double_full_read_unchanged': True,
        'runtime_qualification': False, 'collector_executed': False,
        'request_bytes': len(pretty(request)), 'request_sha256': sha(pretty(request)),
        'stdin_bytes': len(text.encode()), 'stdin_sha256': sha(text.encode())}
    files = {'read.py': text.encode(), 'request.json': pretty(request), 'validation.json': pretty(validation),
        'source.diff': ''.join(difflib.unified_diff(source.splitlines(True), text.splitlines(True),
            fromfile='owner17-prepared/read.py', tofile='owner18-prepared/read.py')).encode(),
        'derive_reader.py': Path(__file__).read_bytes()}
    OUT.mkdir(mode=0o700)
    for name, body in files.items():
        with (OUT / name).open('xb') as stream:
            stream.write(body)
    manifest = pretty({'kind': 'owner18_actual_prepared_fixed_reader', 'executed': False,
        'files': [{'path': name, 'bytes': len(body), 'sha256': sha(body)} for name, body in files.items()]})
    with (OUT / 'manifest.json').open('xb') as stream:
        stream.write(manifest)
    print(json.dumps({'root': str(OUT), 'manifest_bytes': len(manifest), 'manifest_sha256': sha(manifest),
        'key': request['idempotency_key'], 'diff_bytes': len(files['source.diff']),
        'diff_sha256': sha(files['source.diff']), **validation}, indent=2))


if __name__ == '__main__':
    main()
